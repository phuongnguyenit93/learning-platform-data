# Constant pool trong tệp class: hằng số, tên kiểu và tham chiếu ký hiệu

## Mục tiêu

Khi biên dịch mã nguồn Java, `javac` tạo tệp `.class` chứa bytecode cùng nhiều bảng và thuộc tính mô tả lớp. Một thành phần trung tâm là **constant pool**: bảng có chỉ mục dùng để mô tả giá trị hằng, chuỗi ký tự, tên lớp, tên trường/phương thức, kiểu dữ liệu và các tham chiếu ký hiệu. Dù gọi là “pool hằng”, nó **không chỉ chứa những giá trị bất biến như số và chuỗi**.

Sau bài học, bạn có thể:

- Chỉ ra vị trí và cấu trúc `constant_pool` trong `ClassFile`, phân biệt **class-file constant pool** với **run-time constant pool**.
- Đọc các nhóm mục quan trọng: `Utf8`, `Integer`, `Long`, `Class`, `String`, `NameAndType`, `Fieldref`, `Methodref`, `InterfaceMethodref` và nhóm phục vụ liên kết động.
- Giải thích chuỗi tham chiếu `Methodref → Class + NameAndType → Utf8`, cách dùng *internal name* và *descriptor*.
- Hiểu bytecode `ldc`, `getstatic`, `invokestatic`, `invokevirtual` truy cập constant pool như thế nào, khi nào JVM cần **resolution**.
- Tự biên dịch Java 17+, quan sát bảng bằng `javap -v` và phân tích lỗi liên kết thường gặp mà không nhầm với lỗi cú pháp.

## 1. Constant pool dùng để làm gì?

Bytecode JVM chủ yếu làm việc với operand stack, local variables và các toán hạng có định dạng gọn. Nó **không mã hóa địa chỉ bộ nhớ cuối cùng của mọi lớp, trường và phương thức** trong từng lệnh. Thay vào đó, các lệnh có thể tham chiếu **một chỉ mục** trong constant pool của lớp hiện hành.

Ví dụ về ý tưởng:

~~~text
getstatic    #18   // tham chiếu ký hiệu đến System.out
ldc          #24   // nạp hằng String
invokevirtual #30  // tham chiếu ký hiệu đến PrintStream.println
~~~

Đây là **minh họa**; các số `#18`, `#24`, `#30` chỉ là ví dụ, **không phải chỉ số ổn định** của một class cụ thể. `javac` và các công cụ có thể sắp xếp mục constant pool khác nhau.

Constant pool giúp **chia sẻ thông tin trong cùng tệp lớp** và biểu diễn các phụ thuộc dưới dạng ký hiệu (tên, loại, descriptor). Khi JVM nạp/liên kết và thực thi lớp, nó có thể chuyển những ký hiệu đó thành thực thể runtime tương ứng.

Phân biệt ngay ba thuật ngữ:

| Thuật ngữ | Nằm ở đâu/vai trò | Điều dễ nhầm |
| --- | --- | --- |
| **Class-file constant pool** | Bảng `constant_pool` được mã hóa trực tiếp bên trong mỗi tệp `.class` | Không chỉ gồm literal; còn có tên kiểu và tham chiếu đến field/method. |
| **Run-time constant pool** | Cấu trúc runtime được tạo từ constant pool khi JVM tạo một lớp/interface; về mặt đặc tả là thành phần của **method area** | Có thể chứa trạng thái/thông tin đã resolve; không đồng nghĩa một bảng String duy nhất toàn JVM. |
| **String intern pool** | Cơ chế canonicalization cho các đối tượng `String`, được `String.intern()` và string literal sử dụng theo quy tắc Java | Không đồng nghĩa bảng `CONSTANT_String` của từng class file. |

Mỗi class file sở hữu constant pool của **chính nó**. Hai lớp đều nhắc đến `java/lang/String` có thể có **hai mục `CONSTANT_Class` riêng** trong hai class file. Không vì cùng tên mà mặc định chúng tham chiếu một vị trí vật lý chung trong tệp hoặc trong bộ nhớ JVM.

## 2. Vị trí bảng trong cấu trúc ClassFile

Theo Java Virtual Machine Specification (JVMS), một `ClassFile` có bố cục khái quát:

~~~text
ClassFile {
    u4 magic;                  // 0xCAFEBABE
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    ...
    fields[];
    methods[];
    attributes[];
}
~~~

Đây là **sơ đồ rút gọn**; cấu trúc đầy đủ còn có các bộ đếm và mảng con tương ứng với interfaces, fields, methods, attributes. Ký hiệu `u1`, `u2`, `u4` là số nguyên không dấu có độ rộng lần lượt 1, 2, 4 byte; thứ tự byte của định dạng class file là **big-endian**.

- `magic` là `0xCAFEBABE`, nhận diện class file.
- `major_version`/`minor_version` cho biết **phiên bản định dạng class file**, không phải bản thân phiên bản JDK đã cài. Java 17 thường tạo major **61**; Java 21 thường tạo major **65** với target mặc định tương ứng.
- `constant_pool_count` là một `u2`; chỉ số hợp lệ của các vị trí constant pool chạy từ **1** đến **`constant_pool_count - 1`**. **Chỉ số 0 không phải một entry**.
- Mỗi entry vật lý bắt đầu bằng một `tag` 1 byte, tiếp theo là trường dữ liệu thay đổi theo loại entry.
- Các vị trí sau một mục `CONSTANT_Long` hoặc `CONSTANT_Double` có quy tắc đặc biệt: **mỗi giá trị loại này chiếm hai vị trí chỉ số liên tiếp**, nhưng chỉ có một entry dữ liệu thực. Vị trí kế tiếp là không dùng được. Vì vậy không được suy luận số entry lưu thực bằng `constant_pool_count - 1` trong mọi trường hợp.

### Ví dụ vị trí chỉ mục có khoảng trống

~~~text
constant_pool_count = 8
#1 Utf8     "Sample"
#2 Class    name_index = 1
#3 Long     3000000000
#4 <không dùng: vị trí sau Long>
#5 Utf8     "java/lang/Object"
#6 Class    name_index = 5
#7 Utf8     "<init>"
~~~

Ví dụ minh họa cấu trúc chỉ số, **không phải toàn bộ một class file hợp lệ**. Với `Long` ở `#3`, bytecode không được tham chiếu entry `#4`. Cùng quy tắc áp dụng cho `Double`; những mục khác chỉ chiếm một chỉ số.

Một số field trong cấu trúc `ClassFile` cũng tham chiếu pool. Ví dụ `this_class` và `super_class` chứa chỉ mục đến entry `CONSTANT_Class`; tên của class được đi tiếp qua entry `CONSTANT_Utf8`.

## 3. Các loại entry trong constant pool

JVMS định nghĩa **17 loại tag** ở định dạng class file hiện đại. Không phải class file nào cũng chứa đủ chúng; loại xuất hiện tùy nguồn, compiler, mục đích của class, target và những tính năng bytecode đã sử dụng.

| Tag (thập phân) | Tên entry | Ý nghĩa chính |
| --- | --- | --- |
| 1 | `CONSTANT_Utf8` | Văn bản dưới dạng **modified UTF-8**: tên, descriptor, tên thuộc tính, text của literal... |
| 3 | `CONSTANT_Integer` | Hằng số số nguyên 32-bit (cũng có thể dùng cho giá trị `boolean`, `byte`, `short`, `char` theo encoding thích hợp). |
| 4 | `CONSTANT_Float` | Hằng số dấu phẩy động 32-bit. |
| 5 | `CONSTANT_Long` | Hằng số nguyên 64-bit; chiếm hai vị trí chỉ số. |
| 6 | `CONSTANT_Double` | Hằng số dấu phẩy động 64-bit; chiếm hai vị trí chỉ số. |
| 7 | `CONSTANT_Class` | Tham chiếu ký hiệu đến kiểu lớp/interface hoặc descriptor kiểu mảng theo quy định. |
| 8 | `CONSTANT_String` | Hằng tham chiếu đối tượng `String`; trỏ tới nội dung ở `CONSTANT_Utf8`. |
| 9 | `CONSTANT_Fieldref` | Tham chiếu ký hiệu đến trường của lớp/interface. |
| 10 | `CONSTANT_Methodref` | Tham chiếu ký hiệu đến phương thức (hoặc constructor) của class theo quy định. |
| 11 | `CONSTANT_InterfaceMethodref` | Tham chiếu ký hiệu đến phương thức của interface. |
| 12 | `CONSTANT_NameAndType` | Ghép tên member/call site với **descriptor** kiểu trường hoặc phương thức. |
| 15 | `CONSTANT_MethodHandle` | Mô tả method handle với reference kind và reference index. |
| 16 | `CONSTANT_MethodType` | Mô tả kiểu phương thức qua descriptor. |
| 17 | `CONSTANT_Dynamic` | Hằng động (*dynamic constant*) được tính và liên kết bằng bootstrap method. |
| 18 | `CONSTANT_InvokeDynamic` | Call site động dùng bởi lệnh `invokedynamic` và bootstrap method. |
| 19 | `CONSTANT_Module` | Mô tả tên module, thường dùng với `module-info.class`. |
| 20 | `CONSTANT_Package` | Mô tả tên package, thường dùng với `module-info.class`. |

**Tag không liên tục**: không có nghĩa mọi số từ 1 đến 20 đều hợp lệ; ví dụ 2, 13 và 14 **không được dùng** trong bảng loại ở trên.

Một nhóm hỗ trợ liên kết động (`MethodHandle`, `MethodType`, `Dynamic`, `InvokeDynamic`) sẽ được giải thích kỹ ở phần sau. Không nên hiểu chữ “constant” trong `CONSTANT_InvokeDynamic` là một literal có thể nạp bằng `ldc`: đó là mô tả *điểm gọi động*.

### `CONSTANT_Utf8` và modified UTF-8

`CONSTANT_Utf8_info` có `length` kiểu `u2` và một dãy byte được mã hóa theo **modified UTF-8** của JVM. Điều này **không hoàn toàn giống UTF-8 tiêu chuẩn**; cách biểu diễn null character và một số đơn vị UTF-16 khác nhau. Giới hạn của trường là **65.535 byte mã hóa**, không phải 65.535 ký tự Java hoặc ký tự Unicode. Khi tự đọc file nhị phân, phải dùng đúng quy tắc modified UTF-8, độ dài byte và chỉ mục; không tùy ý dùng decoder UTF-8 thông thường.

Một entry `Utf8` chỉ chứa văn bản; nó **không tự động là đối tượng `String` Java**. Nó có thể đại diện tên lớp, tên trường, descriptor, tên thuộc tính hoặc phần text mà `CONSTANT_String` tham chiếu.

## 4. Tên kiểu: `Class` và internal name

Ví dụ một lớp Java:

~~~java
package org.example;

public class Invoice {
}
~~~

Đây là mã nguồn minh họa riêng. Trong mã Java, tên đầy đủ của lớp là `org.example.Invoice`. Trong **internal name** của JVM, dấu chấm phân cách package được biểu diễn bằng dấu gạch chéo:

~~~text
Tên Java:        org.example.Invoice
JVM internal:    org/example/Invoice

Một dạng mục constant pool:
#10 = Class             #11
#11 = Utf8              org/example/Invoice
~~~

Chỉ số `#10`/`#11` **minh họa**. `CONSTANT_Class` chứa `name_index` trỏ đến `CONSTANT_Utf8` lưu tên; nó **không chứa toàn bộ đối tượng `java.lang.Class` ở dạng serialized**.

Với kiểu mảng, tên trong `CONSTANT_Class` có thể dùng **array descriptor**, ví dụ `[Ljava/lang/String;` (mảng `String[]`), theo yêu cầu cụ thể của JVMS. Một class file cũng có thể chứa tên kiểu phụ thuộc như `java/lang/Object`, `java/lang/System`, `java/io/PrintStream` nếu cần.

### Class identity còn phụ thuộc class loader

**Tên giống nhau chưa đủ để bảo đảm cùng một lớp runtime.** Khi JVM nạp lớp, danh tính của class/interface gắn với **binary name và defining class loader**. Hai class loader khác nhau có thể định nghĩa hai lớp có cùng tên binary nhưng là hai kiểu khác nhau. Vì vậy quá trình resolve một `CONSTANT_Class` còn phụ thuộc bối cảnh lớp đang tham chiếu và quy tắc nạp/liên kết, không chỉ nội dung text tên lớp.

## 5. Tên trường/phương thức và descriptor: `NameAndType`

Để liên kết tới member, JVM cần nhiều hơn chỉ tên. Một tên như `print` hoặc `value` không nói đủ thông tin về kiểu tham số, kiểu trả về hay kiểu trường.

**Field descriptor** ký hiệu kiểu của một trường; **method descriptor** mã hóa danh sách kiểu tham số và kiểu trả về. Một số ký hiệu cơ bản:

| Descriptor | Kiểu Java tương ứng |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `V` | `void` (chỉ hợp lệ ở vị trí kiểu trả về phương thức, không phải kiểu trường/tham số) |
| `Ljava/lang/String;` | Tham chiếu `java.lang.String` |
| `[I` | `int[]` |
| `[[Ljava/lang/String;` | `String[][]` |

Ví dụ:

~~~java
int count;
long sum(int a, long b) { return a + b; }
String join(String s, int n) { return s + n; }
~~~

Đoạn code chỉ minh họa các member bên trong một class, không phải chương trình độc lập. Các descriptor tương ứng:

~~~text
count : I
sum   : (IJ)J
join  : (Ljava/lang/String;I)Ljava/lang/String;
main  : ([Ljava/lang/String;)V
~~~

Phân tích `(IJ)J`:
- Dấu ngoặc `(...)` bao các kiểu tham số, theo thứ tự `int` (`I`) và `long` (`J`).
- Phần sau dấu `)` là kiểu trả về `long` (`J`).
- Descriptor **không chứa tên tham số Java**, chú thích, generic source-level hoặc keyword `public`/`static`.

Generics được **erase** ở mức descriptor JVM thông thường: ví dụ `List<String>` thường được biểu diễn bằng kiểu thô `Ljava/util/List;` trong field/method descriptor. Thông tin generic khai báo có thể xuất hiện ở thuộc tính `Signature` riêng, không phải một kiểu descriptor mới kiểu `List<String>`.

### `NameAndType` tham chiếu hai `Utf8`

Một mục `CONSTANT_NameAndType` có hai chỉ mục:
- `name_index` → `CONSTANT_Utf8` chứa tên, ví dụ `println`.
- `descriptor_index` → `CONSTANT_Utf8` chứa descriptor, ví dụ `(Ljava/lang/String;)V`.

Từ đó, `CONSTANT_Methodref`/`Fieldref` kết hợp **Class** với **NameAndType** để xác định ký hiệu đầy đủ.

## 6. Cấu trúc tham chiếu ký hiệu `Fieldref`, `Methodref`, `InterfaceMethodref`

Giả sử có lời gọi Java:

~~~java
System.out.println("Hello");
~~~

Đây là một lệnh minh họa bên trong một phương thức Java. Nó cần truy cập trường tĩnh `java.lang.System.out`, sau đó gọi phương thức `java.io.PrintStream.println(String)`.

Một đồ thị minh họa:

~~~text
Fieldref: java/lang/System.out:Ljava/io/PrintStream;
  |
  +--> Class #A ---------> Utf8 "java/lang/System"
  |
  +--> NameAndType #B ---> Utf8 "out"
                         +-> Utf8 "Ljava/io/PrintStream;"

Methodref: java/io/PrintStream.println:(Ljava/lang/String;)V
  |
  +--> Class #C ---------> Utf8 "java/io/PrintStream"
  |
  +--> NameAndType #D ---> Utf8 "println"
                         +-> Utf8 "(Ljava/lang/String;)V"
~~~

Các nhãn `#A`, `#B`, `#C`, `#D` là placeholder giải thích **quan hệ**, không phải chỉ số thực của class file.

Tại dạng nhị phân:
- `CONSTANT_Fieldref_info`, `CONSTANT_Methodref_info` và `CONSTANT_InterfaceMethodref_info` đều chứa `class_index` và `name_and_type_index`.
- `class_index` trỏ tới `CONSTANT_Class`; `name_and_type_index` trỏ tới `CONSTANT_NameAndType`.
- Điểm khác nhau của ba loại phản ánh **quy tắc resolve/loại member** cho trường, phương thức lớp hoặc phương thức interface.
- **Phương thức overload** có thể có cùng tên nhưng descriptor khác nhau, nên tên `println` không đủ để chỉ chính xác overload.
- Constructor dùng tên JVM đặc biệt `<init>` với descriptor trả về `V`; class initializer `<clinit>` có vai trò riêng trong cấu trúc method, không phải một constructor thông thường.

**Symbolic reference** là bộ thông tin “lớp nào, tên gì, descriptor gì”, **không phải địa chỉ thực tế** của phương thức/trường trong process. Tên và descriptor được lấy từ constant pool để JVM resolve trong bối cảnh nạp/liên kết thích hợp.

## 7. Ví dụ đầy đủ: biên dịch, xem constant pool bằng `javap`

Tạo đúng tệp **`ConstantPoolDemo.java`**:

~~~java
public final class ConstantPoolDemo {
    private static final String CATEGORY = "JVM";
    private static final long BASE = 3_000_000_000L;

    public static long add(long delta) {
        return BASE + delta;
    }

    public static void main(String[] args) {
        String source = "class-file";
        long result = add(7L);

        System.out.println(CATEGORY);
        System.out.println(source);
        System.out.println(result);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 ConstantPoolDemo.java
java ConstantPoolDemo
~~~

**Stdout chính xác:**

~~~text
JVM
class-file
3000000007
~~~

Vì sao kết quả như vậy? `BASE` là hằng `long` có giá trị 3.000.000.000; phương thức `add(7L)` trả 3.000.000.007. Hai chuỗi `"JVM"` và `"class-file"` được in trước kết quả số.

Quan sát file đã biên dịch:

~~~bash
javap -v -p ConstantPoolDemo
javap -c -p ConstantPoolDemo
javap -s -p ConstantPoolDemo
~~~

Ý nghĩa:
- `javap -v`: hiển thị metadata class file, phiên bản và bảng **Constant pool**, cùng chi tiết mã/attributes.
- `-p`: hiển thị cả member private.
- `-c`: disassemble bytecode của phương thức.
- `-s`: in **descriptor** JVM của field/method.

Bạn nên nhận diện **các dạng** mục, thay vì học thuộc số index cụ thể. Với compiler Java thông thường, kết quả quan sát có thể bao gồm:

| Dạng mục/bytecode | Nguồn gốc trong ví dụ | Điều cần quan sát |
| --- | --- | --- |
| `CONSTANT_Class`, `CONSTANT_Utf8` | `ConstantPoolDemo`, `java/lang/Object`, `java/lang/System`, `java/io/PrintStream` | Lớp được tham chiếu qua tên internal. |
| `CONSTANT_String` → `CONSTANT_Utf8` | `"JVM"` và `"class-file"` | `String` tham chiếu đến entry text; lệnh `ldc` có thể nạp string literal. |
| `CONSTANT_Long` | `3_000_000_000L` và `7L` | Hằng 64-bit được nạp bằng `ldc2_w` nếu compiler phát lệnh nạp trực tiếp. |
| `CONSTANT_Fieldref` | `java/lang/System.out` | Bytecode `getstatic` tham chiếu tới trường tĩnh. |
| `CONSTANT_Methodref` | `ConstantPoolDemo.add`, `PrintStream.println` | `invokestatic`, `invokevirtual` chỉ mục đến các method reference. |
| `CONSTANT_NameAndType` | `out:Ljava/io/PrintStream;`, `add:(J)J`, `println:(J)V` | Phân biệt tên member với descriptor. |
| `ConstantValue` attribute | `CATEGORY` và `BASE` là compile-time constants | Giá trị hằng của field được lưu thông qua attribute riêng tham chiếu vào pool; các cách tối ưu có thể inline ở call site. |

**Không sao chép nguyên số `#N` từ một máy làm chuẩn học liệu.** Compiler/JDK/target hoặc phương án sinh bytecode khác nhau có thể tạo chỉ số, thứ tự, lượng entry và instruction khác nhau mà chương trình vẫn đúng.

### Đọc đường đi từ bytecode đến constant pool

Trong `main` của chương trình trên, các bytecode dạng:

~~~text
ldc          #N   // chuỗi "class-file" hoặc "JVM"
ldc2_w       #N   // giá trị long lớn
invokestatic #N   // ConstantPoolDemo.add:(J)J
getstatic    #N   // java/lang/System.out
invokevirtual #N  // PrintStream.println overload tương ứng
~~~

là **đường đi có thể quan sát tùy nơi compiler chọn instruction**, không phải dump exact của `javap`. Để xác định thực tế, tìm số `#N` trên lệnh disassembly rồi tìm cùng số trong bảng `Constant pool`. Trong bản in của `javap`, chú thích bên phải thường đã resolve các chỉ mục ở mức hiển thị thành dạng đọc được như `Method ConstantPoolDemo.add:(J)J`.

Đặc biệt, `CATEGORY` và `BASE` là **compile-time constant variables** (`static final` với initializer hằng phù hợp). Compiler có thể **inline** giá trị sử dụng, khiến `main` hoặc `add` không dùng lệnh `getstatic` cho chính các field này; sự tồn tại của field trong class file không có nghĩa mọi chỗ đọc nó đều phải có `CONSTANT_Fieldref` tương ứng.

## 8. Giá trị nào thật sự cần entry và bytecode nào tham chiếu pool?

Không phải mọi literal nguồn Java đều sinh một entry constant pool để nạp bằng `ldc`.

Ví dụ:

~~~java
int zero = 0;
int small = 5;
int medium = 100;
long large = 3_000_000_000L;
String name = "JVM";
~~~

Đoạn code minh họa bên trong một phương thức. Compiler thường có thể phát:
- `iconst_0`, `iconst_5` cho các số nguyên nhỏ.
- `bipush` hoặc `sipush` để mang một giá trị nguyên ngắn **ngay trong instruction**.
- `ldc` hoặc `ldc_w` cho hằng tải từ pool (số nguyên/float, String, class literal, method type/handle hoặc dynamic constant phù hợp).
- `ldc2_w` cho `long`/`double` (hoặc dynamic constant có kiểu 64-bit phù hợp).
- Một số giá trị `long`/`double` nhỏ như 0 hoặc 1 có **instruction riêng** (`lconst_0`, `dconst_1`) nên không cần mục pool để nạp literal đó.

Đừng kết luận “không thấy số 5 trong constant pool là compiler mất dữ liệu”; có thể giá trị đã nằm trong opcode. Ngược lại, `CONSTANT_Integer` không nhất thiết chỉ phục vụ biến `int` trong mã Java: đặc tả class file dùng loại hằng này cho nhiều kiểu nguyên nhỏ hơn khi phù hợp.

**`ldc` vs `ldc_w`:** hai lệnh nạp hằng với operand chỉ mục có độ rộng khác nhau (1 byte và 2 byte). `ldc2_w` dùng hai byte chỉ mục để nạp một giá trị category 2 như `long`/`double`. Chữ `w` ở đây liên quan **độ rộng chỉ mục**, không có nghĩa một chuỗi hay số tự chuyển sang “precision lớn hơn”.

## 9. Constant pool trong file và quá trình resolve trong JVM

Khi nạp lớp, JVM tạo cấu trúc run-time constant pool tương ứng. Các **symbolic references** cần được liên kết với lớp, trường, phương thức hoặc thực thể call site thực tế. Resolution là một phần của **linking**; các bước lớn trong vòng đời lớp là:

~~~text
.class trên disk
    |
    v
Loading: tạo cấu trúc runtime của class/interface
    |
    v
Linking:
    +-- Verification: kiểm tra tính hợp lệ/các ràng buộc
    +-- Preparation: chuẩn bị biến static với giá trị mặc định
    +-- Resolution: ánh xạ tham chiếu ký hiệu sang thực thể cụ thể
    |
    v
Initialization: chạy class initialization khi có tác nhân kích hoạt
    |
    v
Execution: bytecode dùng constant pool và kết quả liên kết
~~~

Sơ đồ mang tính khái niệm: JVM có thể **resolve theo nhu cầu** hoặc **resolve sớm**, miễn tuân thủ thời điểm báo lỗi/hành vi theo đặc tả. Vì vậy **không được khẳng định mọi `Methodref` và `Fieldref` đều resolve hết ngay khi class được load**, cũng không được khẳng định resolution chỉ xảy ra sau khi bắt đầu thực thi một instruction cụ thể.

### Ví dụ resolution method reference

Để chạy lời gọi đến một phương thức như `PrintStream.println(String)`, VM phải:
1. Đọc một `CONSTANT_Methodref` từ run-time constant pool của lớp đang thực thi.
2. Tìm tên kiểu chủ sở hữu bằng `Class` và tên/descriptor bằng `NameAndType`.
3. Theo quy tắc class loading, access control và method resolution, xác định kiểu và member phù hợp hoặc báo lỗi liên kết.
4. Khi instruction được thực thi, áp dụng semantics của loại invoke, trong đó `invokevirtual` còn có cơ chế **chọn phương thức thực thi** dựa vào kiểu receiver tại runtime.

**Resolution và virtual dispatch không phải một khái niệm.** Resolution xác lập ý nghĩa tham chiếu ký hiệu; runtime method selection (ví dụ virtual method dispatch) quyết định implementation nào sẽ chạy trên receiver cụ thể.

Tương tự, `CONSTANT_Fieldref` không chứa “offset cố định” đáng tin cậy của field trong mọi đối tượng. JVM triển khai có thể lưu cache/quickening khác nhau, nhưng đó là chi tiết thực thi, không phải định dạng gốc của file.

### Những lỗi linking liên quan

| Lỗi | Tình huống thường gặp |
| --- | --- |
| `NoClassDefFoundError` | Lớp cần được định nghĩa/khởi tạo không sẵn có tại runtime hoặc không thể nạp/khởi tạo theo yêu cầu; phải xem nguyên nhân gốc. |
| `NoSuchFieldError` | Bytecode tham chiếu field với tên/descriptor nhưng bản class runtime không còn field phù hợp. |
| `NoSuchMethodError` | Bytecode tham chiếu method với tên/descriptor nhưng runtime không tìm thấy method phù hợp, thường do dependency không tương thích nhị phân. |
| `IllegalAccessError` | Link tới class/member không được phép truy cập theo các quy tắc runtime, dù mã nguồn có thể từng biên dịch với cấu hình khác. |
| `IncompatibleClassChangeError` | Dạng class/member thay đổi không tương thích, ví dụ khác static/instance hoặc class/interface. |
| `ClassFormatError` | Dữ liệu class file không thỏa định dạng/constraints khi JVM cố nạp. |
| `VerifyError` | Vi phạm kiểm tra tính hợp lệ của bytecode trong quá trình xác minh. |
| `BootstrapMethodError` | Bootstrap của hằng/call site động bị lỗi theo điều kiện đặc tả. |

Các lỗi trên không đơn giản là “chuỗi sai trong constant pool”. Nên xác minh **JAR thực tế trên classpath/module path, phiên bản bytecode, phiên bản dependency và class loader**. Một chương trình biên dịch thành công có thể vẫn liên kết thất bại nếu runtime cung cấp API khác bộ đã dùng lúc compile.

## 10. Liên kết động: MethodHandle, MethodType, InvokeDynamic và Dynamic

Các ngôn ngữ và tính năng JVM hiện đại cần biểu diễn những liên kết linh hoạt hơn tham chiếu `Methodref` thông thường:

- **`CONSTANT_MethodHandle` (tag 15):** mô tả một method handle, gồm `reference_kind` và `reference_index` trỏ đến loại reference thích hợp. Đây là mô tả liên kết theo semantics method handle, không nhất thiết là lời gọi trực tiếp.
- **`CONSTANT_MethodType` (tag 16):** trỏ đến một `Utf8` chứa **method descriptor**, ví dụ `(I)Ljava/lang/String;`.
- **`CONSTANT_InvokeDynamic` (tag 18):** mô tả **call site động**: bootstrap method index và `NameAndType`. Bytecode `invokedynamic` dùng entry này; JVM thực hiện bootstrap/link để tạo `CallSite` tương ứng.
- **`CONSTANT_Dynamic` (tag 17):** mô tả một **giá trị hằng được tính tại thời điểm resolution**, cũng dùng bootstrap và `NameAndType`, nhưng name-and-type descriptor ở đây là **field descriptor** của giá trị, khác với method descriptor của `InvokeDynamic`.

`CONSTANT_InvokeDynamic` có từ Java 7/JVM class file major 51; `CONSTANT_Dynamic` có từ Java 11/class file major 55. **Chúng không giống nhau**: một bên là *call site* để gọi, bên kia là *giá trị hằng* có thể tải.

### Vai trò của `BootstrapMethods` attribute

Nếu class file có `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic`, nó phải có đúng **một** thuộc tính `BootstrapMethods` ở cấp class. Thuộc tính này chứa bảng các mục bootstrap:

~~~text
BootstrapMethods:
  bootstrap_method_ref  -> CONSTANT_MethodHandle
  bootstrap_arguments[] -> các entry hằng có loại được phép
~~~

Trường `bootstrap_method_attr_index` trong `CONSTANT_InvokeDynamic`/`CONSTANT_Dynamic` trỏ đến **chỉ số bắt đầu từ 0 trong bảng bootstrap_methods** của attribute, **không phải** một chỉ mục constant pool. Trong khi đó `bootstrap_method_ref` bên trong attribute là chỉ mục đến `CONSTANT_MethodHandle` của constant pool. Hai loại chỉ số cần phân biệt rõ khi đọc file.

**Bootstrap method** thực hiện liên kết thực sự theo contract của loại dynamic entry; một constant pool entry là thông tin mô tả, không phải toàn bộ logic Java trực tiếp được nhúng trong entry.

### Ví dụ Java 17 với lambda và string concatenation

Tạo tệp **`DynamicPoolDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class DynamicPoolDemo {
    public static void main(String[] args) {
        IntUnaryOperator increment = value -> value + 1;
        int result = increment.applyAsInt(4);
        System.out.println("result=" + result);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 DynamicPoolDemo.java
java DynamicPoolDemo
javap -v -p DynamicPoolDemo
~~~

**Stdout của ứng dụng:**

~~~text
result=5
~~~

Khi dùng **`javac` thông thường cho Java 17**, lambda thường được phát qua `invokedynamic` với bootstrap liên quan đến `LambdaMetafactory`; string concatenation thường dùng `invokedynamic` với bootstrap liên quan đến `StringConcatFactory`. Trong output `javap -v`, tìm `InvokeDynamic`, `MethodHandle`, `MethodType` và attribute `BootstrapMethods` để thấy các tham chiếu liên quan.

**Không cần Java source chứa từ khóa `invokedynamic`.** Đây là instruction của JVM; compiler chọn cách dùng. Không phải bytecode `invokedynamic` nào cũng là lambda; các mục trong constant pool phản ánh thực tế **của file được biên dịch**, không đủ để kết luận duy nhất một cú pháp Java nguồn.

## 11. `CONSTANT_Module` và `CONSTANT_Package`

Kể từ Java 9 (class file major 53), constant pool còn có hai loại để hỗ trợ hệ thống module:

- `CONSTANT_Module`: trỏ tới `Utf8` chứa tên module.
- `CONSTANT_Package`: trỏ tới `Utf8` chứa tên package ở dạng nội bộ phù hợp quy định.

Các mục này thường xuất hiện trong **`module-info.class`**, cùng attribute `Module` và các cấu trúc liên quan. Ví dụ mô tả module:

~~~java
module org.example.payments {
    exports org.example.payments.api;
    requires java.logging;
}
~~~

Đây là nội dung minh họa của **`module-info.java`**; muốn biên dịch cần cấu trúc module/source thích hợp và package export phải tồn tại. Khi xem `javap -v module-info.class`, ta có thể thấy `Module`/`Package` entries. Không nên yêu cầu mọi class Java không mô đun đều có những tag này.

## 12. Constant pool và thuộc tính khác trong class file

Có nhiều tên/metadata **được tham chiếu qua constant pool nhưng dữ liệu không nằm hoàn toàn trong constant pool**:

- **`ConstantValue`:** attribute của một field, có `constantvalue_index` trỏ tới giá trị trong pool. Nó mô tả giá trị hằng ban đầu của một field phù hợp; constant variables còn có thể bị compiler inline khi được sử dụng nơi khác.
- **`Code`:** attribute của method chứa bytecode, max stack/locals, exception table và attributes lồng. Lệnh trong `Code` dùng một số chỉ mục constant pool làm operand.
- **`Signature`:** có thể lưu thông tin generic source-level mà descriptor đã erase; giá trị text nằm ở `Utf8` được trỏ tới, không thay đổi ngữ nghĩa field/method descriptor chuẩn.
- **`SourceFile`, `LineNumberTable`, `LocalVariableTable`:** phục vụ nguồn/debug nếu có; các tên attribute và nhiều chuỗi nằm trong `Utf8`, nhưng thông tin chi tiết ở attribute riêng.
- **`StackMapTable`:** hỗ trợ type checking của verifier qua các frame; có thể tham chiếu kiểu theo constant pool nhưng không “biến thành” một entry hằng đơn lẻ.
- **Annotation attributes** và những attribute khác có thể dùng các chỉ mục đến `Utf8`, class/const entry theo format cụ thể.

Như vậy, **constant pool là bảng tham chiếu có cấu trúc cho toàn class file**, không phải nơi lưu bytecode, thông tin debug, object graph hay toàn bộ metadata trong một khối duy nhất.

### Có phải compiler luôn sinh một entry cho mỗi lần xuất hiện literal?

Không. Compiler có thể:
- Dùng lại cùng entry constant pool cho những chỗ dùng giống nhau khi hợp lệ.
- Inline giá trị compile-time constant hoặc tính trước biểu thức hằng.
- Dùng instruction với immediate operand, không qua pool.
- Sinh thông tin phụ, synthetic method, bootstrap arguments khi biên dịch lambda, nối chuỗi, record hoặc tính năng khác.
- Dùng các entry `Utf8` riêng cho cùng văn bản hoặc sắp xếp khác nhau; không nên viết công cụ dựa trên thứ tự bất biến.

Đặc tả mô tả **định dạng hợp lệ và semantics**, không hứa một layout `#1, #2, #3,...` cố định cho cùng mã nguồn ở mọi compiler.

## 13. Chuỗi literal và String intern pool: ví dụ tránh nhầm lẫn

Một `CONSTANT_String` trong class file chứa chỉ mục tới `CONSTANT_Utf8` cho nội dung literal. Khi JVM resolve hằng String phù hợp, chương trình nhận **tham chiếu đến một đối tượng `String`** theo semantics của string literal/interning; entry trong file **không phải byte array đóng gói đối tượng String runtime**.

Ví dụ đầy đủ **`StringPoolContrast.java`**:

~~~java
public class StringPoolContrast {
    public static void main(String[] args) {
        String a = "hello";
        String b = "hello";
        String c = new String("hello");

        System.out.println(a == b);
        System.out.println(a == c);
        System.out.println(a.equals(c));
        System.out.println(a == c.intern());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 StringPoolContrast.java
java StringPoolContrast
~~~

**Stdout:**

~~~text
true
false
true
true
~~~

Giải thích:
- Hai literal `"hello"` được canonicalize theo quy tắc string literal nên `a == b` đúng.
- `new String("hello")` tạo đối tượng khác nên `a == c` sai.
- `a.equals(c)` so sánh nội dung và đúng.
- `c.intern()` trả tham chiếu canonicalized của chuỗi đó nên `a == c.intern()` đúng.

**Không kết luận “mọi `Utf8` entry được intern thành String Java”.** Hầu hết entry `Utf8` trong class file có thể chỉ là tên lớp, descriptor, field hoặc attribute; cơ chế intern dành cho chuỗi runtime là một khái niệm riêng.

## 14. Các vấn đề thường gặp khi đọc `javap` hoặc tự xử lý class file

| Hiện tượng | Nguyên nhân/giải thích đúng | Cách kiểm tra |
| --- | --- | --- |
| Thấy `Methodref #A.#B` nhưng không thấy ngay tên phương thức | `Methodref` trỏ gián tiếp qua `Class` + `NameAndType`, rồi tới `Utf8` | Theo từng chỉ mục hoặc đọc comment của `javap -v`. |
| Chỉ số bắt đầu từ `#1` và có chỗ trống sau `Long` | Chỉ số 0 không hợp lệ; `Long`/`Double` chiếm hai slot | Đọc `constant_pool_count` và đặc tả `4.4.5`. |
| Có chuỗi literal nhưng không thấy dữ liệu String object | Class file lưu `CONSTANT_String` → `Utf8`, không lưu object heap | Tách khái niệm file constant pool với heap/String intern. |
| Biên dịch `5` nhưng constant pool không có `Integer 5` | `iconst_5` có thể đặt literal ngay trong opcode | Dùng `javap -c` xem instruction. |
| Field `static final` xuất hiện nhưng không thấy `getstatic` tại nơi dùng | Compile-time constant có thể bị inline | Xem `ConstantValue` và lệnh thật ở call site. |
| Chỉ số `#N` khác máy khác dù stdout như nhau | Compiler, target, công cụ tạo class file có thể thay layout | Đừng hardcode chỉ số pool vào bài kiểm thử. |
| `InvokeDynamic` có bootstrap index 0, tưởng là `#0` | BootstrapMethods index bắt đầu từ 0, khác chỉ số constant pool | Đọc đúng hai bảng. |
| Thấy `Ljava/util/List;` nhưng không thấy `String` trong descriptor generic | Type erasure; generic có thể nằm ở `Signature` | Dùng `javap -v -s -p`. |
| `NoSuchMethodError` xuất hiện dù compile đã thành công | Bản class runtime có member khác với bản dùng khi compile | So JAR/dependency, descriptor, class loader và module path. |
| Tự parse class file bị sai khi gặp tiếng Việt hoặc ký tự null | `Utf8` dùng modified UTF-8 với `length` byte | Đọc cấu trúc `u2 length` rồi decode đúng MUTF-8. |
| Công cụ parse gặp tag 17/18/19/20 không nhận ra | Parser cũ chưa hỗ trợ class file hiện đại | Nâng thư viện/parser và tôn trọng version/tag tương ứng. |
| Dùng tên `java.lang.String` trực tiếp làm internal name | JVM dùng `java/lang/String` trong Class/descriptor | Chuyển đúng binary/internal name theo định dạng. |

### Cách điều tra lỗi liên kết

Khi có lỗi như `NoSuchMethodError`, đừng sửa tùy tiện source chỉ vì lỗi có chữ *method*. Xác định:

1. Lỗi nhắc **owner class**, **method name** và **descriptor** nào.
2. Class nào phát sinh lời gọi? Trong bytecode của class đó, `javap -c -v` chỉ đến `Methodref` hoặc `InterfaceMethodref` nào.
3. Runtime thực sự nạp **phiên bản class/JAR** nào, bằng class loader nào; kiểm tra classpath/module path và các bản dependency trùng.
4. Bản class đích có đúng method với descriptor/access/staticness phù hợp hay không.
5. Build lại và chạy cùng tập artifact runtime. Lỗi nhị phân do thay thư viện mà không tái biên dịch caller có thể không xuất hiện lúc compile source của một module độc lập.

Một method trùng tên nhưng **khác descriptor** không được xem là cùng member để liên kết. Đây là một trong những lý do constant pool lưu **tên và kiểu** thành hai thành phần rõ ràng.

## 15. Tự kiểm tra

**Câu 1.** Constant pool trong `.class` có chỉ chứa số nguyên và String literal không?

**Đáp án:** Không. Nó còn chứa `Utf8` names, `Class`, `NameAndType`, field/method/interface method references, các entry phục vụ liên kết động và module.

**Câu 2.** Một `CONSTANT_Methodref` đủ để biết lớp, tên method, kiểu tham số và kiểu trả về bằng cách nào?

**Đáp án:** Từ `class_index` đến `CONSTANT_Class`/`Utf8` để lấy owner; từ `name_and_type_index` đến `CONSTANT_NameAndType`/hai `Utf8` để lấy tên và method descriptor.

**Câu 3.** Vì sao `Long` trong constant pool khiến một chỉ số tiếp theo không dùng được?

**Đáp án:** Định dạng class file quy định `CONSTANT_Long` và `CONSTANT_Double` chiếm **hai slot chỉ số**, dù là một entry có dữ liệu; slot kế tiếp không được tham chiếu.

**Câu 4.** `java/lang/String` và `Ljava/lang/String;` có giống vai trò không?

**Đáp án:** `java/lang/String` là internal name của lớp; `Ljava/lang/String;` là **field descriptor** cho kiểu tham chiếu đến lớp ấy. Descriptor có thêm `L` và `;`.

**Câu 5.** `(IJ)J` biểu diễn method như thế nào?

**Đáp án:** Hai tham số `int` và `long`, kiểu trả về `long`. Tên method và tên tham số không nằm trong chuỗi descriptor này.

**Câu 6.** Vì sao không nên hardcode `#12` ở `javap` thành “lời gọi println” trong một công cụ?

**Đáp án:** Thứ tự/chỉ số pool là chi tiết class file cụ thể, compiler có thể sinh layout khác. Phải đọc entry/chỉ mục thực tế từ chính file.

**Câu 7.** Trường `static final long BASE = 3_000_000_000L;` luôn gây `getstatic` ở mọi chỗ dùng không?

**Đáp án:** Không. Giá trị compile-time constant có thể được inline; nơi sử dụng có thể dùng `ldc2_w` thay vì `getstatic` của field.

**Câu 8.** `CONSTANT_InvokeDynamic` khác `CONSTANT_Dynamic` thế nào?

**Đáp án:** `InvokeDynamic` mô tả **điểm gọi động** để instruction `invokedynamic` liên kết ra `CallSite`; `Dynamic` mô tả **giá trị hằng động** có kiểu field descriptor, được tính khi resolution thông qua bootstrap.

**Câu 9.** Bootstrap index 0 có phải truy cập `constant_pool[0]` không?

**Đáp án:** Không. `bootstrap_method_attr_index` là chỉ số bắt đầu từ **0** trong danh sách bootstrap methods của attribute; constant pool bắt đầu từ **1**.

**Câu 10.** Cùng tên `com/example/Plugin` có bảo đảm cùng class runtime không?

**Đáp án:** Không. Class identity phụ thuộc cả defining class loader. Hai loader có thể định nghĩa những lớp cùng tên nhưng khác danh tính runtime.

## 16. Ghi nhớ trọng tâm

~~~text
ClassFile
  |
  +-- constant_pool (#1 .. #count-1)
  |      |
  |      +-- Literal       : Integer / Float / Long / Double / String
  |      +-- Text          : Utf8 (MUTF-8)
  |      +-- Type          : Class, Module, Package
  |      +-- Member symbols: Class + NameAndType -> Fieldref/Methodref/InterfaceMethodref
  |      +-- Dynamic links : MethodHandle/MethodType/Dynamic/InvokeDynamic
  |
  +-- fields / methods / Code / attributes
               |
               +-- tham chiếu chỉ mục pool

JVM: Loading -> Linking (bao gồm Resolution) -> Initialization -> Execution
        |
        +-- run-time constant pool và liên kết tham chiếu ký hiệu
~~~

**Ý chính:** constant pool là **bảng cấu trúc ký hiệu và hằng số** giúp class file biểu diễn phụ thuộc một cách độc lập với layout bộ nhớ runtime. Hiểu đường đi `Fieldref/Methodref → Class + NameAndType → Utf8`, cách descriptor mã hóa kiểu và cách JVM resolve là nền tảng để đọc `javap`, điều tra lỗi linking và tìm hiểu bytecode nâng cao.

## Tài liệu tham khảo chính thức

- [JVMS Java SE 21 — `4.1` The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 21 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3).
- [JVMS Java SE 21 — `4.4` The Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4).
- [JVMS Java SE 21 — `4.7.23` BootstrapMethods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23).
- [JVMS Java SE 21 — `5.1` The Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.1).
- [JVMS Java SE 21 — `5.4 Linking, đặc biệt `5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3).
- [JDK 21 — javap tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
