# Đọc constant pool và thuộc tính class ở mức phục vụ kiểm chứng

Khi kiểm tra kết quả biên dịch Java, đọc mỗi mã nguồn `.java` hoặc chạy thử chương trình chưa đủ để biết **compiler thực sự đã ghi gì vào `.class`**. Một class file chứa **constant pool** (bảng các hằng và tham chiếu ký hiệu), thông tin phiên bản, class/field/method descriptors, access flags, bytecode và nhiều **attributes** mang metadata cho verifier, runtime, reflection và công cụ phân tích. Hiểu chúng ở mức vừa đủ giúp phát hiện sai target Java, mất annotations, signature generic không đúng, bytecode tham chiếu dependency ngoài dự kiến, hoặc những thuộc tính cần thiết của `record`, `sealed`, `invokedynamic`.

Mục tiêu bài học là **kiểm chứng output**, không phải viết lại một trình đọc toàn bộ Java Class File Format. Ta sử dụng công cụ `javap` của JDK 17+, cách đối chiếu với Java Virtual Machine Specification (JVMS), các ví dụ tự biên dịch và những tiêu chí PASS/FAIL có thể xác nhận. **Không kết luận dựa vào số thứ tự `#n` hoặc sự hiện diện của đúng một lệnh bytecode cụ thể nếu đó chỉ là lựa chọn implementation của `javac`.**

## 1. Đường đi từ source tới dữ liệu cần kiểm chứng

~~~text
Source Java + --release / -g / -parameters / processors
                         │
                         ▼
                 javac compilation
                         │
                         ▼
                   class file (.class)
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
     Header/version  Constant pool  Class/field/method
                                   + attributes
           │             │             │
           └─────────────┼─────────────┘
                         ▼
         javap -v / -c / -s / -p / -l
                         │
                         ▼
      So chính sách: target, API, metadata,
       dependency, access, code, module, ...
                         │
                  PASS hoặc FAIL
~~~

Lệnh `javap` **phân tích class file tĩnh** và in thông tin; nó không tự thực thi `main`, không chứng minh mọi dependency runtime đều có mặt, và không cho biết JIT đã tối ưu native machine code ra sao. Khi mục tiêu là chạy đúng nghiệp vụ, cần unit/integration/runtime test **bổ sung**, không thay bằng đọc constant pool.

Năm câu hỏi thực dụng:

1. File có đúng **major/minor version** cho Java đích không?
2. Class có đúng **tên binary, superclass, interfaces, access flags và method/field descriptors** không?
3. Có các **symbolic references** tới class/method/field và bootstrap handles dự kiến không?
4. Các **attributes** cần cho reflection, generic tooling, records, sealed types, debug hoặc annotation processing có mặt đúng chỗ không?
5. Kết quả có phù hợp **chính sách phát hành** của ứng dụng không, thay vì chỉ khác biệt text của `javap` so với lần build khác?

## 2. ClassFile: cấu trúc tổng thể của một tệp .class

Cấu trúc khái quát theo JVMS §4.1:

~~~text
ClassFile {
    u4 magic;
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    u2 interfaces[interfaces_count];
    u2 fields_count;
    field_info fields[fields_count];
    u2 methods_count;
    method_info methods[methods_count];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Đây là **mô hình cấu trúc theo đặc tả**, không phải một `.java` có thể chạy. `u1`, `u2`, `u4` lần lượt là các đại lượng unsigned dài 1, 2 và 4 byte; các giá trị nhiều byte trong class file theo **big-endian**. Magic là `0xCAFEBABE`. `constant_pool_count` gồm một phần tử dự trữ ở chỉ số 0; các constant pool indexes hợp lệ thường bắt đầu từ 1.

**Phân biệt các tầng dữ liệu:**

| Thành phần | Diễn giải khi kiểm chứng |
| --- | --- |
| `magic` và version | File class hợp lệ ở mức nhận dạng, target JVM tối thiểu về định dạng |
| `constant_pool` | Symbolic references, literals và thông tin liên kết của bytecode/metadata |
| `access_flags` | Các đặc tính như `public`, `final`, `interface`, `abstract`; diễn giải theo loại structure |
| `this_class`, `super_class`, `interfaces` | Danh tính và quan hệ kiểu ở mức binary |
| `fields` và `methods` | Thành viên với tên, descriptor, flags và attributes riêng |
| `attributes` | Metadata/bytecode mở rộng theo vị trí, format và yêu cầu riêng từng attribute |

Không nên nhầm **constant pool trong file** với **runtime constant pool** thuộc cơ chế nạp class của JVM; chúng liên quan nhưng nằm ở các giai đoạn khác nhau. Đọc `javap -v` cho thấy thông tin class file trước khi runtime thực hiện resolution.

## 3. Ví dụ Java 17+ đầy đủ để đọc constant pool và attributes

Tạo tệp **`VerifySample.java`**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@interface Reviewed {
    String value();
}

@Reviewed("class-level")
public final class VerifySample<T extends Number> {
    public static final int LIMIT = 42;
    private final T value;

    public VerifySample(T value) {
        this.value = Objects.requireNonNull(value);
    }

    public String label(String prefix) {
        return prefix + ":" + value;
    }

    public static void main(String[] args) {
        VerifySample<Integer> sample = new VerifySample<>(7);
        System.out.println(sample.label("n"));
    }
}
~~~

Class `VerifySample` sử dụng có chủ ý: hằng compile-time `LIMIT`, field generic `T extends Number`, phương thức generic-aware và phép nối chuỗi động, annotation có retention `RUNTIME`, constructor, class/method/field access flags. Source chỉ gồm một tệp với hai top-level types; lớp annotation `Reviewed` không `public`, nên cách tổ chức tệp hợp lệ.

Biên dịch từ thư mục chứa source bằng JDK 17+:

~~~bash
mkdir -p out
javac --release 17 -g -parameters -d out VerifySample.java
java -cp out VerifySample
~~~

Stdout của lệnh `java`:

~~~text
n:7
~~~

Output sau compile thông thường có `out/VerifySample.class` và `out/Reviewed.class`. Dù có cả hai class trong một source file, **mỗi top-level type là một class file riêng**. Vì source không khai `package`, các class nằm ngay dưới `out`. Nếu chọn cách đặt `package demo;`, tên và đường dẫn class sẽ đổi tương ứng.

Đọc class đã biên dịch:

~~~bash
javap -classpath out -v -p -c -s VerifySample
~~~

Các option có mục tiêu cụ thể:

- `-classpath out`: đảm bảo `javap` tìm đúng file class vừa biên dịch.
- `-v` / `-verbose`: in nhiều thông tin class file, gồm constant pool, version, access flags và attributes.
- `-p` / `-private`: hiển thị cả thành viên private; nếu bỏ qua có thể không thấy `value`.
- `-c`: disassemble các lệnh trong `Code` attribute ở method có code.
- `-s`: in **descriptor** nội bộ của field/method, giúp nhận ra erased types.
- `-l`: option khác để in line/local variable tables; với `-v` nhiều thông tin debug đã được hiển thị.

**Không so khớp nguyên văn toàn bộ bản in giữa các JDK**. Tên format, comment, số lượng entry, thứ tự constant pool và cách compiler hạ nối chuỗi có thể khác. Hãy kiểm tra **những thuộc tính có ý nghĩa theo yêu cầu**.

## 4. Cách đọc constant pool trong javap -v

Một đoạn ngắn mang tính **minh họa định dạng**:

~~~text
Constant pool:
   #1 = Methodref          #2.#3     // java/lang/Object."<init>":()V
   #2 = Class              #4        // java/lang/Object
   #3 = NameAndType        #5:#6     // "<init>":()V
   #4 = Utf8               java/lang/Object
   #5 = Utf8               <init>
   #6 = Utf8               ()V
~~~

Chỉ số `#1` tới `#6` ở đây **không phải output cam kết** của `VerifySample.class`. Lệnh `javap` thật sẽ cho một tập entry phong phú hơn và thứ tự có thể khác. Mục đích là học cách lần theo **tham chiếu từ một entry tới các entry khác**.

Diễn giải:

1. `Methodref` mô tả tham chiếu tới method hoặc constructor.
2. Nó trỏ đến một `Class` chứa tên class có dạng JVM internal `java/lang/Object`.
3. Nó cũng trỏ đến `NameAndType`, biểu diễn cặp **tên** và **descriptor** của method.
4. `Utf8` chứa chuỗi tên hoặc descriptor đã mã hóa theo định dạng class file.
5. Comment sau `//` là phần diễn giải hỗ trợ con người của `javap`; nó không phải dữ liệu nguyên xi lưu trong một trường comment của constant pool.

Ví dụ `()V` nghĩa là method **không tham số**, trả về **void**. `<init>` là tên đặc biệt của instance initialization method. Mối liên kết này giúp kiểm tra lời gọi constructor/method ở bytecode được tham chiếu tới **symbol nào**, chứ không chỉ tên Java ngắn.

### Bảng entry quan trọng

| Dạng trong `javap` | JVMS constant | Khi nào cần quan sát? |
| --- | --- | --- |
| `Utf8` | `CONSTANT_Utf8` | Tên, descriptors, attribute names và nhiều literal văn bản |
| `Integer`, `Float` | `CONSTANT_Integer`, `CONSTANT_Float` | Giá trị literal số nguyên 32-bit/số thực 32-bit |
| `Long`, `Double` | `CONSTANT_Long`, `CONSTANT_Double` | Literal số 64-bit; chiếm hai chỉ số pool |
| `Class` | `CONSTANT_Class` | Symbolic reference tới class/interface/array type |
| `String` | `CONSTANT_String` | String literal dùng qua constant pool |
| `Fieldref` | `CONSTANT_Fieldref` | Tham chiếu field |
| `Methodref` | `CONSTANT_Methodref` | Tham chiếu class method |
| `InterfaceMethodref` | `CONSTANT_InterfaceMethodref` | Tham chiếu interface method |
| `NameAndType` | `CONSTANT_NameAndType` | Tên member và descriptor đi cùng |
| `MethodHandle` | `CONSTANT_MethodHandle` | Handle với reference kind/target |
| `MethodType` | `CONSTANT_MethodType` | Mô tả kiểu method |
| `InvokeDynamic` | `CONSTANT_InvokeDynamic` | Dynamic call site, liên kết qua bootstrap method |
| `Dynamic` | `CONSTANT_Dynamic` | Dynamically computed constant |
| `Module`, `Package` | `CONSTANT_Module`, `CONSTANT_Package` | Module descriptor và package names khi phù hợp |

**Không hiểu `String` trong pool là instance String đã được tạo sẵn trong bộ nhớ trước khi chạy**. Constant pool chứa thông tin class-file; việc resolution, intern, initialization hoặc bootstrap liên quan được JVM xử lý ở runtime theo quy tắc thích hợp.

**Long/Double chiếm hai slot:** sau entry `CONSTANT_Long` hoặc `CONSTANT_Double`, chỉ số kế tiếp không phải entry hợp lệ độc lập. Vì thế khi viết custom parser không được giả định có đúng một entry hợp lệ tại mọi `#n` từ 1 tới `constant_pool_count - 1`.

**Utf8 dùng modified UTF-8** theo Class File Format, không được mặc định cùng cách mã hóa byte của `StandardCharsets.UTF_8` trong mọi trường hợp. Khi xây parser nhị phân cần tuân theo đặc tả; đọc text bằng `javap` thường đơn giản, an toàn và đủ cho mục tiêu xác minh.

## 5. Tham chiếu ký hiệu, descriptor và tên kiểu

Một `Fieldref` hoặc `Methodref` **không chứa đối tượng Java đang chạy**. Nó biểu diễn một **symbolic reference**: class sở hữu, tên member và descriptor. JVM có thể giải resolution lúc nạp/liên kết hoặc khi instruction thật sự cần, theo các quy tắc tương ứng.

Dấu `/` và dấu `.` có ý nghĩa khác:

- Java source: `java.lang.String`.
- JVM internal name thường thấy: `java/lang/String`.
- Descriptor của một reference type: `Ljava/lang/String;`.
- Descriptor của array of String: `[Ljava/lang/String;`.

Bảng descriptor cơ bản:

| Kiểu Java | Field descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

`V` biểu diễn `void` **chỉ khi là return descriptor** của method, không phải kiểu field.

Một descriptor phương thức gồm **các parameter types trong cặp ngoặc** rồi tới return type:

~~~text
()V
(I)J
(Ljava/lang/String;I)Z
([Ljava/lang/String;)V
~~~

Các ví dụ lần lượt nghĩa là: không tham số, trả void; nhận int, trả long; nhận String và int, trả boolean; nhận String array, trả void.

### Generic type không nằm nguyên trong descriptor

Ở `VerifySample<T extends Number>`:

~~~java
private final T value;
public String label(String prefix) { ... }
~~~

Field `value` sẽ có descriptor tương ứng type erasure của `T`, ở đây là `Ljava/lang/Number;`, **không phải `TT;` như một runtime descriptor riêng**. Thông tin generic `T` có thể nằm trong **`Signature` attribute**.

Vì vậy:

- **Descriptor** dùng cho liên kết và hình dạng JVM của field/method.
- **Signature** bổ sung thông tin generic được quy định cho các công cụ như reflection/generic-aware tooling.
- Generic metadata không làm JVM tự kiểm tra mọi element `List<String>` là String lúc runtime; erasure vẫn phải được hiểu đúng.

Đừng so sánh signature generics bằng cách nhìn mỗi phần `descriptor:`, vì nó có thể chỉ cho thấy kiểu sau erasure.

## 6. Đọc access flags và cấu trúc class

Trong `javap -v`, phần đầu thường có:

~~~text
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
this_class: #...                         // VerifySample
super_class: #...                        // java/lang/Object
~~~

Đây là **minh họa ý nghĩa**, các `#...` không phải chỉ số thực và dòng flags có thể khác cách hiển thị theo compiler/target. Java 17 class file bình thường có major 61, minor 0. Các flags của class khác flags của method/field.

Thông tin nên xác minh:

- `ACC_PUBLIC`/`ACC_PRIVATE`/`ACC_PROTECTED`: mức truy cập ở những structure hợp lệ.
- `ACC_FINAL`, `ACC_ABSTRACT`, `ACC_INTERFACE`, `ACC_ANNOTATION`, `ACC_ENUM`, `ACC_MODULE`: đặc tính class/interface/annotation/module.
- `ACC_STATIC`, `ACC_SYNCHRONIZED`, `ACC_NATIVE`, `ACC_BRIDGE`, `ACC_VARARGS`: ý nghĩa khác nhau ở thành viên/phương thức.
- `ACC_SYNTHETIC` hay `Synthetic` attribute: phần compiler tạo ra mà source không viết trực tiếp, tùy version/cơ chế.
- `this_class`, `super_class`, `interfaces`: danh tính binary/type hierarchy.

**Không diễn giải mọi flag giống nhau ở mọi nơi.** Ví dụ `ACC_SUPER` gắn với class file theo JVMS; không có nghĩa class là Java `super` keyword. Một interface không có quan hệ class hierarchy giống class concrete. Module descriptor trong `module-info.class` có quy tắc riêng.

Nếu nghi một public API bị thay đổi, hãy đối chiếu **danh sách fields/methods, tên, descriptor và access flags**, rồi mới xét generic signature hoặc annotation metadata. Nhiều lỗi `NoSuchMethodError` bắt nguồn từ binary signature/descriptor không còn trùng với lời gọi đã compile.

## 7. Attributes là gì và nằm ở đâu?

`attribute_info` có header chung:

~~~text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
~~~

`attribute_name_index` là chỉ số trỏ tới một `CONSTANT_Utf8` mang **tên attribute**. `attribute_length` tính **số byte của phần info**, không gồm sáu byte header. Nội dung `info` của mỗi attribute phải đọc theo định nghĩa riêng; không có một parser chung có thể hiểu mọi attribute chỉ bằng cách biết tên.

Attributes có thể xuất hiện trên:

- **ClassFile** — class-level metadata như `SourceFile`, `Signature`, `BootstrapMethods`, `Record`, `PermittedSubclasses`.
- **field_info** — như `ConstantValue`, `Signature`, runtime annotations trên field.
- **method_info** — như `Code`, `Exceptions`, `Signature`, `MethodParameters` và annotation metadata.
- **Code_attribute** — các attribute lồng trong code như `LineNumberTable`, `LocalVariableTable`, `StackMapTable`.
- **record_component_info** — component metadata được định nghĩa cho record.

Một attribute có tên đúng nhưng đặt sai location, không thỏa độ dài/ràng buộc hoặc chứa chỉ số pool bất hợp lệ không trở thành hợp lệ chỉ vì `javap` nhìn thấy chuỗi tên. Để xác minh chính thức phải theo JVMS version mục tiêu.

## 8. Những attributes quan trọng nhất cho kiểm chứng output

| Attribute | Đọc ở đâu và phục vụ việc gì? |
| --- | --- |
| `Code` | Bytecode và thông tin thực thi method; không áp dụng như code body cho abstract/native methods |
| `ConstantValue` | Giá trị khởi tạo đặc biệt cho field `static` constant theo điều kiện JVMS |
| `Signature` | Generic signature của class/field/method khi cần metadata ngoài descriptor |
| `Exceptions` | Các checked/declared exceptions được nêu trong method declaration |
| `SourceFile` | Tên source file gắn với class; không phải đường dẫn đầy đủ đáng tin của workspace |
| `LineNumberTable` | Ánh xạ bytecode offset tới dòng nguồn, hỗ trợ stack trace/debug |
| `LocalVariableTable` | Metadata về local variables khi được compiler tạo |
| `LocalVariableTypeTable` | Generic local-variable metadata trong trường hợp phù hợp |
| `MethodParameters` | Tên/flags của formal parameters ở mức class file |
| `RuntimeVisibleAnnotations` | Annotation đủ điều kiện được runtime reflection nhìn thấy |
| `RuntimeInvisibleAnnotations` | Annotation được lưu trong class nhưng không thuộc nhóm runtime-visible |
| `AnnotationDefault` | Default value của element trong annotation type declaration |
| `BootstrapMethods` | Thông số bootstrap của `invokedynamic` và `CONSTANT_Dynamic` |
| `StackMapTable` | Các verification type frames, hỗ trợ class verification |
| `InnerClasses` | Quan hệ nested/member class metadata theo spec |
| `EnclosingMethod` | Method/class bao quanh local/anonymous class khi cần |
| `NestHost`, `NestMembers` | Nest-based access control (Java 11+) |
| `Record` | Metadata record components (Java 16+) |
| `PermittedSubclasses` | Danh sách subtype được phép của sealed class/interface (Java 17+) |
| `Module`, `ModulePackages`, `ModuleMainClass` | Metadata trong `module-info.class` theo vị trí/ràng buộc riêng |

Sự **vắng mặt** một attribute **không luôn là lỗi**:

- Method không có local variables hữu ích hoặc compiler không được yêu cầu debug vars thì có thể không có `LocalVariableTable`.
- Không có dynamic call site/constant thì không cần `BootstrapMethods`.
- Không có annotation `RUNTIME` thì không cần `RuntimeVisibleAnnotations`.
- Một class thường không phải record sẽ không có `Record`.
- Một class không tham gia sealed hierarchy phù hợp sẽ không có `PermittedSubclasses`.
- Một method không cần stack map frames được mã hóa bổ sung có thể không có `StackMapTable` được in như người học kỳ vọng.

**Kiểm chứng có điều kiện** theo loại class và source/target/options, không bắt buộc mọi file `.class` đều chứa cùng một bộ attributes.

## 9. Kiểm chứng ConstantValue và hằng compile-time

Trong source mẫu:

~~~java
public static final int LIMIT = 42;
~~~

`javac` có thể ghi attribute `ConstantValue` cho field `LIMIT` để biểu diễn constant variable được xác định tại compile time. Khi xem:

~~~bash
javap -classpath out -p -v VerifySample
~~~

hãy tìm phần field `LIMIT` cùng đoạn tương đương:

~~~text
descriptor: I
flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
ConstantValue: int 42
~~~

Đây là **các tính chất cần kiểm tra**; thứ tự/dòng bao quanh phụ thuộc `javap`. `ConstantValue` khác `Code` của class initializer. Không phải **mọi field `static final`** đều có `ConstantValue`: ví dụ field được khởi tạo bằng `new Object()` phải có logic runtime và không thể biểu diễn như constant primitive/String theo quy tắc tương ứng.

Hệ quả với binary compatibility: giá trị hằng compile-time primitive/String có thể được nhúng vào class của consumer khi biên dịch, nên đổi hằng trong library nhưng không rebuild consumer có thể cho hành vi “giá trị cũ”. Khi kiểm chứng release, ngoài xem `ConstantValue` hãy cân nhắc rebuild các consumers phụ thuộc constant.

## 10. Kiểm chứng Code attribute và bytecode method

Một `method_info` có thể chứa `Code` attribute với:

~~~text
Code {
    max_stack
    max_locals
    code_length
    code[code_length]
    exception_table
    attributes
}
~~~

Mẫu trên mô tả **các trường chính** của `Code_attribute`, không đủ là source definition để biên dịch. `Code` lưu bytecode JVM (không phải assembly CPU), giới hạn operand stack, local variable slots, exception handlers và attributes lồng.

Với source:

~~~java
public String label(String prefix) {
    return prefix + ":" + value;
}
~~~

Java 17 `javac` thường sử dụng `invokedynamic` cho nối chuỗi động theo cơ chế JEP 280. `javap -c -v` có thể in instruction `invokedynamic` trong `label` và entry `InvokeDynamic` ở constant pool. Nhưng đây là **lựa chọn code generation của compiler cụ thể**; kết quả nghiệp vụ bắt buộc là phương thức nối giá trị đúng, không phải mọi compiler đều sinh cùng instruction sequence.

Khi phân tích:

1. Xác định đúng method bằng **tên + descriptor**.
2. Đọc `Code` và instruction offsets.
3. Theo dõi operand stack, local slots và symbolic references đến fields/methods.
4. Kiểm tra exception table và handler nếu source có try/catch/finally.
5. Khi có `invokedynamic`, xem `BootstrapMethods`/method handles.
6. Không suy ra JIT inlining hoặc machine code đã chạy từ bản in `javap`.

`max_stack`/`max_locals` phản ánh giới hạn cho JVM bytecode ở method; chúng **không** phải số lượng object Java trên heap, và không trực tiếp chứng minh hiệu năng tốt/xấu.

### Exceptions không giống exception table

- Attribute `Exceptions` trên `method_info` ghi những exception classes được method **khai báo `throws`** theo format.
- **Exception table** nằm bên trong `Code`, mô tả vùng bytecode được bảo vệ và handler offsets.
- Một method có thể ném unchecked exception dù không có `Exceptions` attribute; đừng tìm `NullPointerException` trong `Exceptions` rồi kết luận “method không bao giờ ném NPE”.

## 11. Kiểm chứng tên tham số, dòng nguồn và biến local

Chính xác những debug attributes nào xuất hiện phụ thuộc compiler flags:

~~~bash
javac --release 17 -g -parameters -d out VerifySample.java
javap -classpath out -l -p VerifySample
javap -classpath out -v -p VerifySample
~~~

`-g` yêu cầu tạo debug information gồm dòng nguồn và local variables theo mức compiler hỗ trợ. `-parameters` yêu cầu metadata tên formal parameters để phản ánh qua core reflection ở những trường hợp hợp lệ; kết quả thường liên quan `MethodParameters` attribute.

Phân biệt ba thông tin:

| Thông tin | Attribute | Dùng để |
| --- | --- | --- |
| Source line mapping | `LineNumberTable` | Stack traces, breakpoints, mapping bytecode ↔ dòng |
| Local variable names/ranges | `LocalVariableTable` | Debugger hiển thị local slots/phạm vi sống |
| Formal parameter names/flags | `MethodParameters` | Reflection về tên parameters, phân tích parameter metadata |

**`MethodParameters` không đồng nghĩa `LocalVariableTable`**. Khi cần tên parameter qua reflection (ví dụ framework binding dựa vào parameter names), chỉ bật `-g` chưa phải cách bảo đảm tương đương với `-parameters`. Ngược lại, `-parameters` không yêu cầu toàn bộ local debug information của method.

Một class file đã bị shrink/obfuscate hoặc build với option khác có thể mất/đổi metadata, dù code vẫn chạy; vì thế kiểm chứng phải áp dụng trên **artifact cuối phát hành**, không chỉ `.class` tạm trước packaging.

## 12. Kiểm chứng generics qua Signature

Generic ở Java phần lớn dùng **erasure**, nên descriptor thường không giữ đầy đủ tham số kiểu. Ở `VerifySample<T extends Number>`, dấu hiệu cần đọc:

- Class có `Signature` mô tả type parameter `T` và bound `Number`.
- Field `value` có descriptor theo erasure (`Ljava/lang/Number;`).
- Field `value` có thể có `Signature` diễn đạt reference tới type variable `T`.
- Code của method hoạt động trên JVM reference types phù hợp với erasure.

Lệnh:

~~~bash
javap -classpath out -p -s -v VerifySample
~~~

Cần **không nhầm**:

~~~text
descriptor: Ljava/lang/Number;
Signature: ... TT; ...
~~~

Hai dòng là **ý nghĩa minh họa**, không phải transcript xác định toàn bộ comment hoặc chỉ số pool. `TT;` trong grammar signature biểu diễn **type variable T**, không phải một JVM field descriptor thông thường.

Nếu bạn kiểm tra một public generic API, đối chiếu **cả descriptor và Signature**. Descriptor cần cho binary linkage; Signature giúp generic-aware tools hiểu tham số kiểu. Một class file có Signature bị lỗi grammar hoặc không nhất quán có thể khiến reflection/generic tooling thất bại ngay cả khi một số bytecode vẫn có vẻ nạp được.

**Đừng suy ra** class file chứa một runtime specialization riêng cho `VerifySample<Integer>` chỉ vì source có generic type argument. Đó không phải cách erasure thông thường trong Java.

## 13. Kiểm chứng annotation retention

Trong source mẫu, annotation type:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Reviewed {
    String value();
}
~~~

và class dùng:

~~~java
@Reviewed("class-level")
public final class VerifySample<T extends Number> { ... }
~~~

Vì retention là `RUNTIME`, `VerifySample.class` phải chứa metadata annotation runtime-visible phù hợp, có thể quan sát qua `javap -v` trong `RuntimeVisibleAnnotations`. Không nên chỉ tìm literal `"class-level"` trong constant pool rồi kết luận annotation chắc chắn tồn tại; string có thể xuất hiện vì lý do khác.

Thử đối chiếu với code reflection — tệp **`AnnotationCheck.java`**:

~~~java
public class AnnotationCheck {
    public static void main(String[] args) {
        Reviewed a = VerifySample.class.getAnnotation(Reviewed.class);
        System.out.println(a == null ? "missing" : a.value());
    }
}
~~~

Sau khi đã build `VerifySample.java`:

~~~bash
javac --release 17 -cp out -d out AnnotationCheck.java
java -cp out AnnotationCheck
~~~

Stdout chính xác:

~~~text
class-level
~~~

Đây là **kiểm thử runtime có phạm vi**, bổ sung cho kiểm chứng tĩnh `RuntimeVisibleAnnotations`.

Ba retention cần phân biệt:

- `SOURCE`: compiler xử lý nhưng annotation không cần lưu trong class file.
- `CLASS`: annotation có thể được giữ lại trong class file dưới nhóm **runtime-invisible** và không được core reflection nhìn thấy theo cách thông thường.
- `RUNTIME`: annotation có thể được runtime reflection truy vấn qua API tương ứng.

**Không phải mọi annotation trên source đều xuất hiện trong `RuntimeVisibleAnnotations`**. Type annotations còn có các attribute riêng (`RuntimeVisibleTypeAnnotations`, `RuntimeInvisibleTypeAnnotations`). Để audit, cần biết annotation target và retention, không chỉ tìm một tên attribute duy nhất.

## 14. invokedynamic, MethodHandle và BootstrapMethods

`InvokeDynamic` trong constant pool biểu diễn một call site được liên kết qua bootstrap method. Nó khác với `Methodref`/`InterfaceMethodref` truyền thống. `BootstrapMethods` cung cấp bootstrap method handles cùng bootstrap arguments được nhắc tới bởi các dynamic call sites hoặc dynamic constants.

Khung quan hệ:

~~~text
Instruction invokedynamic #n
             │
             ▼
CONSTANT_InvokeDynamic_info
      │            │
      ▼            ▼
bootstrap index  NameAndType
      │
      ▼
BootstrapMethods attribute
      ├── CONSTANT_MethodHandle
      └── bootstrap arguments (0..n)
~~~

Trên OpenJDK `javac` Java 17, nối chuỗi động có thể dùng `java/lang/invoke/StringConcatFactory`. Lambda expressions thường dùng `invokedynamic` với bootstrap phù hợp (như `LambdaMetafactory`). **Tên bootstrap và sequence cụ thể không thay thế quy tắc ngữ nghĩa Java**; compiler mới có thể đổi representation trong giới hạn class format/behavior.

Điểm xác minh quan trọng từ JVMS: class file có `CONSTANT_InvokeDynamic` hoặc `CONSTANT_Dynamic` tương ứng cần `BootstrapMethods` attribute hợp lệ theo quy định. Thấy `BootstrapMethods` không chứng minh một lambda cụ thể đã chạy hoặc đã được JIT tối ưu; đó là **metadata liên kết**.

**Phân biệt `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`:**

- `Dynamic` mô tả *constant* được tính thông qua bootstrap khi resolution thích hợp.
- `InvokeDynamic` mô tả *dynamic call site* cho invocation.

Không kết luận có `Dynamic` chỉ từ việc source chứa một biểu thức không phải compile-time constant; nhiều biểu thức runtime bình thường không cần constant-dynamic entry.

## 15. Record attribute: kiểm chứng record Java 17

Tạo **`Point.java`**:

~~~java
public record Point(int x, int y) {
    public static void main(String[] args) {
        System.out.println(new Point(2, 3));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -d out Point.java
java -cp out Point
javap -classpath out -v -p Point
~~~

Stdout nghiệp vụ:

~~~text
Point[x=2, y=3]
~~~

Với target Java 17, class file của `Point` cần biểu diễn record theo JVMS, bao gồm **`Record` attribute** mô tả record components. Khi đọc `javap -v`, xem từng component name/descriptor, và kiểm tra các thành viên generated như canonical constructor, accessors cùng các method `equals`/`hashCode`/`toString` tương ứng.

**Không nên kết luận record chỉ bằng việc superclass là `java.lang.Record`**: điều kiện class-file/metadata cần được xét theo JVMS và ngữ nghĩa. Một loại reflection test khác là `Point.class.isRecord()` và `getRecordComponents()` ở runtime phù hợp. `Record` attribute có từ class-file major 60 (Java 16) và phù hợp với ví dụ Java 17.

Một compiler có thể phát `BootstrapMethods` do các method record được sinh (ví dụ cơ chế `ObjectMethods`), nhưng số lượng/index pool cụ thể không phải yêu cầu QA ổn định.

## 16. PermittedSubclasses: kiểm chứng sealed hierarchy

Tạo hai file Java 17:

**`Shape.java`**

~~~java
public sealed interface Shape permits Circle {
}
~~~

**`Circle.java`**

~~~java
public record Circle(int radius) implements Shape {
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out Shape.java Circle.java
javap -classpath out -v Shape
javap -classpath out -v Circle
~~~

Trong `Shape.class`, tìm **`PermittedSubclasses`** liệt kê `Circle` theo symbolic class names. Ở `Circle.class`, tìm dấu hiệu record và việc implement `Shape`. Đây là cách xác nhận sealed hierarchy trong **class file thực tế**, không chỉ source có keyword `sealed`.

`PermittedSubclasses` xuất hiện trong class file major 61+ theo JVMS Java 17. Nó **không nhất thiết** xuất hiện trong mỗi implementation `final` hoặc `record` nằm dưới sealed parent; attribute quan trọng ở sealed class/interface **khai báo tập permitted direct subclasses**.

Nếu class implement `Shape` không thuộc danh sách được permit, JVM có thể từ chối quan hệ kiểu khi nạp/liên kết theo ràng buộc sealed class, ngoài việc compiler đã kiểm tra từ source. Đừng cố sửa bytecode/attribute thủ công để vượt quy tắc này.

## 17. Module attribute: module-info.class khác class thường

Với Java modules (JPMS), file `module-info.class` chứa module descriptor chứ không phải class ứng dụng thông thường. Tạo ví dụ:

~~~text
module-demo/
└── src/
    ├── module-info.java
    └── demo/api/Greeter.java
~~~

**`src/module-info.java`**

~~~java
module demo.greeter {
    exports demo.api;
}
~~~

**`src/demo/api/Greeter.java`**

~~~java
package demo.api;

public final class Greeter {
    private Greeter() {}

    public static String greet() {
        return "ok";
    }
}
~~~

Từ thư mục `module-demo`:

~~~bash
mkdir -p mods/demo.greeter
javac --release 17 -d mods/demo.greeter \
  src/module-info.java src/demo/api/Greeter.java
javap -v mods/demo.greeter/module-info.class
~~~

`module-info.class` có cấu trúc/flags riêng như `ACC_MODULE` và **`Module` attribute**. Thông tin có thể gồm module name, version, requires, exports, opens, uses, provides theo descriptor và các lựa chọn đóng gói. `ModulePackages`/`ModuleMainClass` có những điều kiện phát sinh riêng (ví dụ các công cụ đóng gói/module tooling), không bắt buộc mọi module descriptor có cả hai.

Dùng `javap -v `module-info.class`` để kiểm tra binary descriptor thực phát, hoặc các công cụ quản lý module/JAR như `jar --describe-module` khi phù hợp. Không nhầm `exports` với `opens`: một package được export cho ordinary public type access không tự cho phép mọi deep-reflection access.

Nếu class app dùng classpath, module graph runtime còn phụ thuộc `--module-path` và roots. Một `Module` attribute đúng không bảo đảm lệnh `java` đã resolve module và mọi dependency cần thiết.

## 18. NestHost, NestMembers và InnerClasses

Một source chứa nested class có thể sinh nhiều class files, ví dụ:

~~~java
public class Outer {
    private int secret = 21;

    public class Inner {
        public int doubleSecret() {
            return secret * 2;
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        System.out.println(outer.new Inner().doubleSecret());
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out Outer.java
java -cp out Outer
javap -classpath out -v -p Outer
javap -classpath out -v -p 'Outer$Inner'
~~~

Stdout:

~~~text
42
~~~

Trên shell Bash, dấu nháy đơn quanh `Outer$Inner` tránh việc `$Inner` bị shell mở rộng như biến môi trường. Trên PowerShell cũng có thể dùng single quote. Tệp `Outer$Inner.class` và `Outer.class` có metadata cho nested/nest relationships theo compiler/JVMS.

**`InnerClasses`** mô tả quan hệ lồng nhau phục vụ metadata/ngôn ngữ. **`NestHost`/`NestMembers`** hỗ trợ nest-based access control từ Java 11; vì thế Java 17 compiler thường không cần tạo synthetic accessor chỉ để một nestmate truy cập private member theo những trường hợp đủ điều kiện.

Đừng hiểu tên `InnerClasses` là danh sách mọi anonymous/local/method type chắc chắn có trong mọi hoàn cảnh. Kiểm tra class file thực và phân biệt **Java lexical nesting**, **class-file nest membership**, và **binary names có ký tự `$`**.

## 19. Class-file version là kiểm tra đầu tiên

Tệp class có `major`/`minor`:

| Java release | Major thông dụng |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Với code Java 17 thông thường không dùng preview, expected **major 61, minor 0** sau:

~~~bash
javac --release 17 -d out VerifySample.java
javap -classpath out -v VerifySample
~~~

Chú ý `--release 17` **không buộc tất cả thư viện bên ngoài** trên classpath cũng là major 61 hoặc thấp hơn. Phải kiểm tra dependency artifacts nếu sản phẩm tuyên bố chạy trên Java 17.

Các class file dùng preview features có quy tắc đặc biệt về `minor_version = 65535` và runtime tương ứng; **không đưa preview artifact vào ma trận tương thích phổ thông** mà không nêu rõ version/`--enable-preview`.

### Java 17 program đọc ba trường đầu của header

Tệp **`HeaderCheck.java`**:

~~~java
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class HeaderCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass one .class path");
        }

        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();

            System.out.printf(
                    "magic=%08X minor=%d major=%d%n",
                    magic, minor, major);
        }
    }
}
~~~

Biên dịch `VerifySample.java` trước, rồi chạy:

~~~bash
javac --release 17 HeaderCheck.java
java HeaderCheck out/VerifySample.class
~~~

Stdout:

~~~text
magic=CAFEBABE minor=0 major=61
~~~

Đoạn này **chỉ kiểm tra 8 byte đầu**, không parse constant pool, không xác nhận toàn bộ class hợp lệ hay runtime-loadable. Nếu file ngắn quá, stream sẽ ném exception; nếu chứa magic/version hợp lệ nhưng phần sau hỏng, `HeaderCheck` vẫn có thể in số bình thường. Đây là một smoke check định dạng rất hẹp, không thay verifier hoặc `javap`.

## 20. Khi cần so class files từ hai build

Một nhiệm vụ thực tế: hai bản build cùng source nhưng thay đổi JDK, flags hoặc dependency có output khác nhau. Phân loại trước khi kết luận lỗi:

| Khác biệt quan sát | Ý nghĩa khả dĩ |
| --- | --- |
| Major version đổi | Target `--release`/`-target` hoặc JDK compiler config đổi |
| Descriptor API public đổi | Nguy cơ binary incompatibility |
| `Signature` đổi nhưng descriptor giữ | Generic metadata/API semantics/tooling có thể đổi |
| `MethodParameters` mất | Framework dựa parameter reflection có thể bị ảnh hưởng |
| `RuntimeVisibleAnnotations` mất | Reflection hoặc dependency injection/serialization có thể thay đổi |
| `LineNumberTable`/`LocalVariableTable` đổi | Debug metadata/obfuscation/compiler flags đổi |
| Constant pool index đổi | Thường là layout/detail; bản thân `#n` đổi chưa chứng minh hành vi đổi |
| `BootstrapMethods` đổi | Compiler strategy/dynamic linkage metadata đổi, cần xem sâu trước kết luận |
| `Code` instruction sequence khác | Có thể compiler implementation/lowering khác; cần kiểm thử behavior |
| `PermittedSubclasses` hoặc `Record` đổi | Cần xác minh language-level binary contract |
| `Module` exports/requires đổi | Module graph và accessibility có thể bị ảnh hưởng |

**Kiểm tra trên đúng artifact phát hành.** Nếu Gradle/Maven tạo JAR, shade, obfuscate, multi-release entries hoặc instrument coverage sau khi `javac` chạy, class file trong release JAR có thể khác bản ở intermediate output directory.

Để xem một class trong JAR:

~~~bash
jar tf app.jar
javap -classpath app.jar -v -p demo.App
~~~

Hai lệnh là **mẫu**: thay `app.jar` và `demo.App` bằng artifact/class thực tế. `jar tf` liệt kê entries; `javap` đọc class được chỉ định, không quét hết JAR. Với multi-release JAR, cần chú ý những bản `META-INF/versions/N` mà runtime tương ứng chọn; một class base không đại diện toàn bộ versions.

## 21. Ma trận PASS/FAIL nên kiểm tra những gì?

| Tiêu chí | Công cụ | PASS khi |
| --- | --- | --- |
| Header, Java target | `javap -v` hoặc đọc header | Major/minor phù hợp chính sách; không có preview ngoài ý muốn |
| Public binary API | `javap -p -s`, API diff | Descriptor và access flags đúng bản phát hành |
| Hằng compile-time | `javap -v` | `ConstantValue` đúng khi yêu cầu |
| Generic contract | `javap -v -s` | `Signature` đúng và nhất quán với descriptor |
| Runtime annotation | `javap -v` + reflection test | Annotation hiện diện và đọc được khi retention/target yêu cầu |
| Bytecode/verifier metadata | `javap -v -c` + JVM test | Output hợp lệ; JVM load/test được theo môi trường hỗ trợ |
| Lambda/concat linkage | `javap -v` + JVM test | Bootstrap metadata hợp lệ, behavior runtime đúng |
| Record/sealed | `javap -v` + runtime reflection | `Record`/`PermittedSubclasses` và semantics đúng |
| Module descriptor | `javap module-info.class` / `jar --describe-module` | Requires/exports/opens phù hợp module API |
| Dependencies | `jdeps` và runtime test | Các module/JAR/API cần dùng hiện diện, không nhầm runtime target |

Đối với một thư viện, xem class files của **public API surface** rất quan trọng. Nhưng kiểm chứng hệ thống vẫn cần run tests để bắt lỗi reflection, serialization, classpath, native libraries, service loading hoặc dữ liệu nghiệp vụ.

## 22. Những điều không nên suy luận từ constant pool

**“Constant pool có tên class `com/foo/Bar` tức chương trình chắc chắn sẽ load Bar.”** Sai. Entry có thể được nhắc tới bởi nhánh không bao giờ chạy, metadata, reflection hoặc bytecode khác. JVM không phải eager resolve mọi symbolic reference theo cách người học tưởng.

**“Một tên String xuất hiện là annotation chắc chắn còn.”** Sai. Cần đọc đúng attribute có annotation entries và retention/visibility.

**“Thấy `InvokeDynamic` là code đã được JIT tối ưu.”** Sai. `invokedynamic` là instruction/call-site linkage trong class file; JIT là lớp tối ưu runtime khác.

**“`Signature` mô tả generic nên JVM runtime kiểm tra `List<String>`.”** Sai. Java generics chủ yếu là erasure; type metadata không tự bảo đảm mọi phần tử có kiểu String.

**“Classfile major 61 là ứng dụng đã tương thích Java 17.”** Chưa đủ. Dependency classes, platform API, runtime module graph, preview, native code, container image và JVM flags đều cần kiểm tra.

**“Cùng source, constant pool indexes khác nên đã thay logic.”** Sai. Số thứ tự constant pool, cách sắp xếp và chi tiết codegen có thể khác nhau mà semantic behavior tương đương.

**“Mọi method đều phải có Code, mọi class phải có StackMapTable.”** Sai. Abstract/native methods không có code body thông thường; `StackMapTable` được áp dụng theo ràng buộc cụ thể cho code/version.

## 23. Quy trình kiểm chứng một artifact trong dự án thật

1. Ghi **JDK compiler version, `--release`, build tool flags** và commit/dependency lock của nguồn.
2. Biên dịch tới output directory sạch; kiểm tra exit code, không coi file cũ là kết quả mới.
3. Dùng `javap -v -p -c -s` trên những classes cần audit, bắt đầu bằng class public và type mới.
4. Đọc header/major/minor, `this_class`, access flags, superclass/interfaces.
5. Đọc constant pool theo **symbolic references**, không phụ thuộc số `#n` cố định.
6. Đọc field/method descriptor, generic Signature và annotations cần cho API contract.
7. Kiểm tra attributes đặc thù: `ConstantValue`, `Code`, `StackMapTable`, `BootstrapMethods`, `Record`, `PermittedSubclasses`, `Module`.
8. Nếu output cần tương thích runtime cũ, test **bằng Java runtime thấp nhất**, cùng release artifact và toàn bộ dependencies.
9. Chạy unit/integration tests và reflection tests khi thuộc tính metadata ảnh hưởng hành vi.
10. Nếu so hai build, ưu tiên **semantic diffs** của public descriptors/attributes, không so cứng toàn bộ `javap` text hoặc class bytes trừ khi chính sách yêu cầu reproducible builds.

### Bộ lệnh kiểm chứng tối thiểu cho ví dụ

~~~bash
javac --release 17 -g -parameters -d out VerifySample.java
javap -classpath out -v -p -c -s VerifySample
javap -classpath out -v Reviewed
java -cp out VerifySample
~~~

Trên ví dụ này, kiểm tra được: major version 61, `LIMIT` với `ConstantValue: int 42`, metadata generic, annotation runtime-visible, method bytecode, và stdout `n:7`. Với `Reviewed.class`, bạn có thể xem `AnnotationDefault` nếu annotation type khai báo default value; demo hiện tại không khai báo default nên **không cần attribute đó**.

## 24. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `#15 = Methodref ...` trong build A và `#29 = Methodref ...` trong build B chưa đủ để báo lỗi?  
**Trả lời:** Số index chỉ là vị trí trong constant pool. Phải so symbolic target (class, name, descriptor) và ý nghĩa sử dụng.

**Câu 2.** `descriptor: Ljava/lang/Number;` và generic `T extends Number` có mâu thuẫn không?  
**Trả lời:** Không. Descriptor phản ánh erasure; `Signature` có thể lưu metadata type variable `T`.

**Câu 3.** Tại sao cần `MethodParameters` nếu framework phải đọc parameter names qua reflection?  
**Trả lời:** Đó là metadata formal parameters tương ứng với compiler option `-parameters`; `LocalVariableTable` của debug information không thay thế hoàn toàn.

**Câu 4.** Nếu annotation có retention `SOURCE`, việc không thấy nó trong `RuntimeVisibleAnnotations` là lỗi không?  
**Trả lời:** Không. SOURCE annotation phục vụ compiler và thường không được lưu vào class file.

**Câu 5.** `BootstrapMethods` có nghĩa JIT đã chạy không?  
**Trả lời:** Không. Đây là metadata hỗ trợ dynamic linkage trong class file.

**Câu 6.** Muốn audit sealed Java 17 class/interface nên tìm gì?  
**Trả lời:** `PermittedSubclasses` ở sealed parent cùng danh sách permitted direct subclasses; kiểm tra quan hệ và runtime behavior phù hợp.

**Câu 7.** `Record` attribute có thể xuất hiện trong `VerifySample` class thường không?  
**Trả lời:** Không phải kỳ vọng; nó dành cho class file đại diện record. Hãy kiểm chứng `Point.class` của record example.

**Câu 8.** Major 61 có bảo đảm thư viện chạy Java 17 với mọi dependency không?  
**Trả lời:** Không. Cần kiểm tra dependency class-file versions và chạy tests trên runtime Java 17 thật.

**Câu 9.** Vì sao `Exceptions` attribute và `exception_table` không giống nhau?  
**Trả lời:** Một cái mô tả declared exceptions của method, còn exception table bên trong `Code` mô tả handlers cho bytecode ranges.

**Câu 10.** Tại sao một chương trình đọc 8 byte header không thay được `javap` hoặc bytecode verifier?  
**Trả lời:** Nó chỉ xác minh magic/major/minor; không kiểm tra constant pool, attributes, instruction constraints hoặc dependency resolution.

## 25. Ghi nhớ và tài liệu chính thức

- **Constant pool** là bảng symbolic references/literals dùng bởi class file; `#n` là chỉ số, không phải định danh API ổn định.
- **Descriptors** mô tả field/method types ở mức JVM; **Signature** giữ thêm generic metadata khi cần.
- **Attributes** có vị trí và contract riêng; kiểm tra sự có mặt/giá trị theo source, compiler flags và class-file version, không dùng checklist cứng cho mọi class.
- **`javap -v -p -c -s`** là công cụ quan sát nhanh; code tests và runtime checks phải bổ sung khi khẳng định ứng dụng hoạt động.
- Với Java 17 không preview, **major 61, minor 0** là dấu hiệu target; không đủ bảo đảm toàn ứng dụng portable.
- Khi audit release, ưu tiên public API, annotations, module/record/sealed metadata và dependency graph hơn thay đổi thứ tự pool.

Tài liệu gốc để đối chiếu theo phiên bản:

- [Java SE 17 JVMS §4.1 — ClassFile structure](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [Java SE 17 JVMS §4.4 — The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4).
- [Java SE 17 JVMS §4.7 — Attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7).
- [Oracle Java 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Java SE 17 JVMS §4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3).
