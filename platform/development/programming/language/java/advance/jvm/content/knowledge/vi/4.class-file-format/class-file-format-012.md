# Đọc `javap -c -v -s -l` để nối cấu trúc class với mã Java

## 1. Vì sao cần đọc `javap`?

Mã nguồn Java cho bạn biết **ý định lập trình**: khai báo class, trường, phương thức, kiểu dữ liệu, điều kiện và lời gọi. File `.class` cho JVM biết **cấu trúc nhị phân và mã lệnh cần thực thi**. Công cụ `javap` của JDK giúp nhìn từ class file trở lại những cấu trúc và hành vi có liên quan tới source.

Hãy nghĩ đến một hành trình:

~~~text
BytecodeTour.java
      |
      | javac -g BytecodeTour.java
      v
BytecodeTour.class
      |
      +--- header, major version, access flags, this/super_class
      +--- constant pool, fields[], methods[], attributes[]
      +--- Code: bytecode + max_stack + max_locals + exception table
      +--- debug attributes: LineNumberTable, LocalVariableTable
      |
      | javap -c -v -s -l -p BytecodeTour
      v
Bản đọc được của bytecode, descriptors, metadata và debug tables
      |
      v
Đối chiếu lại: dòng source -> BCI -> opcode -> constant-pool entry
~~~

**`javap` là disassembler, không phải decompiler đầy đủ.** Nó hiển thị những thông tin có thật trong class file, nhưng không bảo đảm khôi phục nguyên văn source ban đầu, mọi tên biến, chú thích, cách viết lambda hay biểu thức gốc. Các chỉ số constant pool và bytecode offset phụ thuộc compiler, phiên bản Java và tùy chọn biên dịch.

Mục tiêu thực hành của bài:

1. Chạy được một ví dụ Java 17+ và xác định stdout.
2. Dùng `-c` để nối `if`, phép cộng và `return` với lệnh bytecode.
3. Dùng `-s` để hiểu descriptor của field, constructor và method.
4. Dùng `-v` để đọc header, constant pool, access flags, `Code`, các attribute và liên kết như `#12`.
5. Dùng `-l` và `javac -g` để nối source line và local variable với **BCI** (bytecode index).
6. Biết giới hạn của việc suy ngược từ class file về source.

## 2. Bốn tùy chọn trọng tâm và những cờ bổ trợ

| Tùy chọn | Thông tin chính | Câu hỏi trả lời |
| --- | --- | --- |
| **`-c`** | Disassemble `Code` thành opcode bytecode, offset, operand, branch target và lời gọi | “Đoạn Java này hạ thành các lệnh gì?” |
| **`-v`** hoặc `-verbose` | Metadata chi tiết: phiên bản class, flags, constant pool, descriptors, attributes, thông tin `Code`, stack maps… | “Class file thực tế lưu những gì?” |
| **`-s`** | **JVM type descriptors** cho field và method | “Kiểu dữ liệu, tham số, kiểu trả về được mã hóa thế nào?” |
| **`-l`** | `LineNumberTable` và `LocalVariableTable` **nếu có** | “BCI tương ứng dòng source/biến local nào?” |
| `-p` hoặc `-private` | Hiện **mọi** members, kể cả private | “Tại sao method/field private không xuất hiện mặc định?” |
| `-classpath` / `-cp` | Chỉ nơi tìm class/JAR người dùng | “Đang disassemble class được biên dịch ở đâu?” |
| `--module` / `-m` | Chọn module chứa class khi duyệt named modules | “Class nằm trong module nào?” |
| `--multi-release N` | Hỗ trợ chọn phiên bản phù hợp khi phân tích multi-release JAR | “Mình có đang đọc đúng biến thể class cho Java N?” |
| `-sysinfo` | In thông tin file như đường dẫn, kích thước, ngày và hash theo bản công cụ | “Đang kiểm tra đúng file chưa?” |

Lệnh kết hợp được sử dụng trong bài:

~~~bash
javap -c -v -s -l -p BytecodeTour
~~~

**Các tùy chọn có phần thông tin chồng nhau.** Chẳng hạn `-v` đã có thể hiển thị descriptor và debug attributes; `-s`, `-l` vẫn hữu ích khi bạn muốn học từng góc nhìn riêng. Khi dùng tất cả cùng lúc, đầu ra có thể dài và lặp lại một số thông tin. Không có nghĩa bốn cờ tạo nên bốn file kết quả hay bốn giai đoạn chạy JVM.

Lệnh nhanh theo nhu cầu:

~~~bash
javap BytecodeTour
javap -p BytecodeTour
javap -c -p BytecodeTour
javap -s -p BytecodeTour
javap -l -p BytecodeTour
javap -v -p BytecodeTour
~~~

**Chú ý dấu `-l`:** đó là chữ **L thường** (*line/local*), không phải số 1 hoặc chữ I hoa. `javap` nhận **tên class** đã có trên classpath hoặc đường dẫn đến file `.class`. Đừng chạy `javap BytecodeTour.java` rồi chờ chương trình biên dịch source; việc biên dịch là trách nhiệm của `javac`.

## 3. Ví dụ chạy được: một source, nhiều góc nhìn class file

Tạo file **`BytecodeTour.java`** trong thư mục mới:

~~~java
public class BytecodeTour {
    private final String label;

    public BytecodeTour(String label) {
        this.label = label;
    }

    public int compute(int left, int right) {
        int sum = left + right;
        if (sum > 10) {
            return sum * 2;
        }
        return sum + 1;
    }

    public String message(int value) {
        return label + ":" + value;
    }

    public static void main(String[] args) {
        BytecodeTour tour = new BytecodeTour("JVM");
        int result = tour.compute(4, 8);
        System.out.println(tour.message(result));
    }
}
~~~

Biên dịch bằng **JDK 17 trở lên** với **đầy đủ debug metadata** và chạy:

~~~bash
javac -g BytecodeTour.java
java BytecodeTour
~~~

**Stdout chính xác:**

~~~text
JVM:24
~~~

Vì `compute(4,8)` có `sum = 12`, điều kiện `12 > 10` đúng nên trả về `24`. `message(24)` tạo `"JVM:24"`. Lệnh `-g` trong `javac` bật mọi thông tin debug thông thường, gồm cả tên local variables cần để `javap -l` hiển thị.

Trong cùng thư mục, chạy:

~~~bash
javap -c -v -s -l -p BytecodeTour
~~~

Bạn sẽ thấy rất nhiều dòng; cách đọc hiệu quả là chia ra các tầng **header → constant pool → member descriptors → Code → debug tables → attributes**.

### Quan hệ của source với các thành phần class file

| Dòng/khái niệm Java | Nơi quan sát trong class file |
| --- | --- |
| `public class BytecodeTour` | `this_class`, `flags: ACC_PUBLIC, ACC_SUPER` (theo build thông dụng) |
| Không ghi `extends` | `super_class` tham chiếu `java/lang/Object` |
| `private final String label` | Một `field_info` với flags `ACC_PRIVATE, ACC_FINAL` và descriptor `Ljava/lang/String;` |
| `BytecodeTour(String label)` | `method_info` tên đặc biệt `<init>`, descriptor `(Ljava/lang/String;)V` |
| `int compute(int,int)` | `method_info` tên `compute`, descriptor `(II)I`, `Code` có `iadd`/so sánh/`ireturn` |
| `String message(int)` | `method_info` tên `message`, descriptor `(I)Ljava/lang/String;` |
| `static void main(String[])` | `method_info` tên `main`, descriptor `([Ljava/lang/String;)V` |
| `new BytecodeTour("JVM")` | Bytecode cấp phát và constructor call (`new`, `dup`, `invokespecial`) |
| `System.out.println(...)` | `getstatic` và `invokevirtual` trỏ đến constant pool |
| Dòng và biến local trong `compute` | `LineNumberTable` / `LocalVariableTable` khi có debug info |

**Không suy luận rằng bytecode luôn giống Java source theo tỷ lệ “một câu lệnh Java = một opcode”.** Một biểu thức Java thường cần nhiều bytecode; một số hằng được compiler gộp/inline; một số lambda, nối chuỗi, switch và thao tác generic tạo ra bytecode hoặc method tổng hợp mà người viết không thấy trong source.

## 4. Đọc `-c`: từ điều kiện Java sang operand stack và branch

Chạy:

~~~bash
javap -c -p BytecodeTour
~~~

Tập trung vào phương thức `compute(int,int)`. Với `javac` phiên bản hiện đại, bạn thường quan sát một chuỗi **tương đương** như sau (đã rút gọn thành các lệnh quan trọng; offset và cách sinh branch có thể khác theo compiler):

~~~text
public int compute(int, int);
  Code:
       0: iload_1
       1: iload_2
       2: iadd
       3: istore_3
       4: iload_3
       5: bipush        10
       7: if_icmple     14
      10: iload_3
      11: iconst_2
      12: imul
      13: ireturn
      14: iload_3
      15: iconst_1
      16: iadd
      17: ireturn
~~~

Đây là **ví dụ disassembly minh họa cho logic**, không phải cam kết mọi bản `javac` xuất ra đúng từng BCI ở trên. Điểm quan trọng là dòng source và ý nghĩa opcode:

- `iload_1`, `iload_2`: lấy `left` và `right` từ **local variable slots 1 và 2** đưa lên operand stack.
- `iadd`: lấy hai `int` từ operand stack, tính `left + right`, đẩy kết quả.
- `istore_3`: ghi `sum` vào **local slot 3**.
- `bipush 10`: đẩy hằng số nguyên 10 lên operand stack.
- `if_icmple 14`: so sánh hai `int`. Nếu `sum <= 10` thì nhảy đến BCI 14; ngược lại tiếp tục nhánh `sum > 10`.
- `iconst_2; imul; ireturn`: nhân `sum * 2` và trả về `int` từ method.
- `iconst_1; iadd; ireturn`: nhánh còn lại trả về `sum + 1`.

**BCI** là **bytecode index**: offset byte bên trong `Code.code[]` của một method, không phải thứ tự dòng Java và cũng không phải địa chỉ lệnh CPU. Một opcode có thể dùng nhiều byte nên BCI không nhất thiết tăng từng 1. Operand branch mà `javap` in là **địa chỉ đích trong phương thức**, không phải số dòng source.

### Mô phỏng operand stack

Tại thời điểm bắt đầu `compute` (instance method):

~~~text
Local variables:
  slot 0 : this (BytecodeTour)
  slot 1 : left = 4
  slot 2 : right = 8
  slot 3 : sum (chưa gán tại đầu method)

Operand stack (vùng trừu tượng):
  []                       ; trước iload_1
  [4]                      ; sau iload_1
  [4, 8]                   ; sau iload_2
  [12]                     ; sau iadd
  []                       ; sau istore_3
  [12, 10]                 ; trước if_icmple
~~~

Nếu điều kiện “`sum <= 10`” **sai**, VM đi qua các lệnh nhân 2, rồi `ireturn` trả `24`. Nếu điều kiện đúng, VM nhảy đến nhánh trả `sum + 1`. Local slot **không phải** biến Java ở cấp source một cách vĩnh viễn: compiler được tái sử dụng slot khi phạm vi sống không trùng nhau.

### Constructor và entry method trong `-c`

Ở constructor `BytecodeTour(String)`, bạn sẽ gặp chuỗi ý nghĩa:

~~~text
aload_0                  ; this
invokespecial ...        ; gọi Object.<init>()
aload_0                  ; this
aload_1                  ; label argument
putfield ...             ; gán this.label
return
~~~

Trong `main`, việc tạo object thường thể hiện bởi:

~~~text
new ... BytecodeTour
dup
ldc ... "JVM"
invokespecial ... BytecodeTour."<init>"
~~~

`new` tạo object, `dup` giữ một bản tham chiếu trên operand stack để dùng sau constructor call, `ldc` nạp một hằng (ở đây là chuỗi), còn `invokespecial` gọi constructor. Những lệnh này giúp nối ý nghĩa `new BytecodeTour("JVM")` với class file. Đừng nhầm `return` của constructor `void` với `ireturn` của `compute` trả `int`.

## 5. Đọc `-s`: descriptors và sự khác biệt với kiểu Java

Chạy:

~~~bash
javap -s -p BytecodeTour
~~~

Các descriptor quan trọng bạn cần tìm:

~~~text
private final java.lang.String label;
  descriptor: Ljava/lang/String;

public BytecodeTour(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public int compute(int, int);
  descriptor: (II)I

public java.lang.String message(int);
  descriptor: (I)Ljava/lang/String;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

Từng ký hiệu được giải nghĩa theo **JVMS `4.3`**:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `B` / `C` / `D` / `F` | `byte` / `char` / `double` / `float` |
| `I` / `J` / `S` / `Z` | `int` / `long` / `short` / `boolean` |
| `V` | `void` — chỉ dùng làm kết quả method descriptor |
| `Lpkg/ClassName;` | Một reference type, tên trong JVM dùng dấu `/` |
| `[I` | Mảng `int[]` |
| `[Ljava/lang/String;` | Mảng `String[]` |
| `(II)I` | Hai tham số `int`, kết quả `int` |
| `([Ljava/lang/String;)V` | Một `String[]`, kết quả `void` |

Ví dụ `(Ljava/lang/String;I)J` là method nhận `String` và `int`, trả về `long`. Số lượng ký tự descriptor **không** bằng số lượng local-variable slots: một `long`/`double` chiếm hai local slots trong model JVM, còn một `reference` hay `int` thường một slot.

### Field descriptor khác method descriptor

- Field có **một** ký hiệu kiểu: `Ljava/lang/String;`, `I`, `[I`.
- Method có **dấu ngoặc bao quanh tham số** rồi tới return descriptor: `(II)I`.
- Constructor `<init>` có method descriptor trả về `V` dù constructor không khai báo kiểu trả về trong source.
- `-s` cho **descriptors** đã erase generics. Để thấy generic type như `List<String>`, đọc thêm `Signature` attribute (nếu có) trong `-v`.

Đừng coi `-s` là tùy chọn “in phương thức Java source hoàn chỉnh”: descriptors không nói tên tham số, code, exception logic hay comment.

## 6. Đọc `-v`: header, constant pool và attributes

Chạy:

~~~bash
javap -v -p BytecodeTour
~~~

### 6.1. Header/class identity

Phần đầu thường có:

~~~text
Classfile .../BytecodeTour.class
  Last modified ...; size ... bytes
  SHA-256 checksum ...
  Compiled from "BytecodeTour.java"
public class BytecodeTour
  minor version: 0
  major version: ...
  flags: (...) ACC_PUBLIC, ACC_SUPER
  this_class: #...           // BytecodeTour
  super_class: #...          // java/lang/Object
  interfaces: 0, fields: 1, methods: ..., attributes: ...
~~~

Những dòng đường dẫn, thời gian, checksum, file size, constant-pool index, method count và version là **đầu ra phụ thuộc bản dựng**. Với `javac` Java 17 mặc định, major version thường là **61**; Java 21 mặc định **65**, Java 25 mặc định **69**. Khi dùng `javac --release 17` trên JDK mới, class vẫn có thể là major 61 vì target bytecode được hạ về Java 17.

`this_class` và `super_class` là **chỉ số constant pool**, còn flags thể hiện đặc tính class. Field `label` cũng có flags riêng (`ACC_PRIVATE, ACC_FINAL`); method `compute` có `ACC_PUBLIC`. Không đọc nhầm cờ cấp class với cờ cấp method/field.

### 6.2. Constant pool: nối một chỉ số với ý nghĩa

`Constant pool` có thể chứa các loại entry như:

| Loại entry | Nội dung |
| --- | --- |
| `Utf8` | Tên class, tên method, descriptor, chuỗi literal và metadata tên |
| `Class` | Tham chiếu tới tên class/interface |
| `NameAndType` | Tên thành viên kèm descriptor |
| `Fieldref` | Tham chiếu field được dùng trong bytecode |
| `Methodref` / `InterfaceMethodref` | Tham chiếu phương thức class/interface |
| `String` / `Integer` / các numeric constants | Hằng mà bytecode có thể sử dụng |
| `InvokeDynamic` | Call site động; được liên kết với bootstrap method |
| `MethodHandle` / `MethodType` | Thành phần mô tả liên kết, bootstrap hoặc method handle |

Một vài dòng dạng sơ đồ:

~~~text
#3  = Class              #4         // java/lang/Object
#4  = Utf8               java/lang/Object
#17 = Fieldref           #...#...   // BytecodeTour.label:Ljava/lang/String;
#21 = Methodref          #...#...   // BytecodeTour."<init>":(Ljava/lang/String;)V
#30 = Utf8               compute
#31 = Utf8               (II)I
~~~

Các con số `#3`, `#17`, `#21`… trong sơ đồ **không bảo đảm** khớp file bạn sinh: chúng chỉ minh họa loại entry. Hãy lấy **index thực tế** của một lệnh trong `javap -c` và đối chiếu **cùng số đó** trong phần `Constant pool` của output `-v`.

Ví dụ nhìn thấy:

~~~text
... getfield  #17  // Field label:Ljava/lang/String;
~~~

Đọc theo chuỗi:

1. `getfield` là opcode lấy **instance field** từ một object reference.
2. `#17` là chỉ số constant pool **do compiler sinh trong file đang xem**.
3. Entry tại `#17` là `Fieldref`; nó liên hệ class owner, tên `label` và descriptor `Ljava/lang/String;`.
4. Muốn biết câu lệnh Java nào dẫn tới opcode này, quay sang `LineNumberTable` và source.

**`#17` không phải địa chỉ heap, không phải line 17 và không phải local slot 17.** Cùng ký hiệu `#N` còn xuất hiện ở bootstrap methods, descriptors và thuộc tính khác; luôn đọc tiêu đề của bảng.

### 6.3. Thông tin `Code` của một phương thức

Trong `-v`, một method có thân bytecode thường có:

~~~text
Code:
  stack=2, locals=4, args_size=3
  0: iload_1
  1: iload_2
  ...
LineNumberTable:
  ...
LocalVariableTable:
  ...
StackMapTable:
  ...
~~~

Ý nghĩa:

- `stack=2`: `max_stack` của method, tức số **operand-stack slots tối đa** mà bytecode của method cần (ví dụ minh họa `compute` này cần 2).
- `locals=4`: `max_locals` gồm slot 0 của `this`, slot 1–2 của `left`/`right` và slot 3 của `sum`.
- `args_size=3`: số slot dùng cho tham số theo JVM invocation frame: `this` + hai tham số `int`. Một static method không có slot `this`; `long` và `double` chiếm hai slots.
- `StackMapTable`: mô tả các frame kiểu dùng để **xác minh bytecode** tại các điểm control flow; **không** phải Java stack trace khi ứng dụng ném exception.
- `Exception table` (nếu method có vùng bắt ngoại lệ): xác định protected ranges, target handlers và catch type.

Các con số ở đây phụ thuộc phương thức được chọn, và phần `StackMapTable` có thể khác theo phiên bản class/compiler. Nếu không có nhánh exception trong `compute`, bạn không cần tìm một exception handler vô cớ.

### 6.4. Phân biệt các attributes

| Attribute | Thuộc vị trí | Dùng để |
| --- | --- | --- |
| `SourceFile` | Cấp class | Tên file nguồn; không chứa toàn bộ source |
| `Code` | Bên trong `method_info` thích hợp | Bytecode, `max_stack`, `max_locals`, exception table, code attributes |
| `LineNumberTable` | Bên trong `Code` | Ánh xạ một số **BCI → số dòng source** |
| `LocalVariableTable` | Bên trong `Code` | Tên, loại, slot, khoảng BCI còn hiệu lực của biến local |
| `LocalVariableTypeTable` | Bên trong `Code` | Generic signature của local variables khi có |
| `Signature` | Class/field/method thích hợp | Thông tin generics đã bị erase khỏi descriptor JVM |
| `Exceptions` | Method | Các checked-exception types khai báo trong `throws` |
| `BootstrapMethods` | Cấp class | Metadata bootstrap cho dynamic constants / invokedynamic |
| `StackMapTable` | Bên trong `Code` | Khai báo các type-verification frames |

Không phải mọi `.class` đều có mọi attribute. Nhiều mục optional, phụ thuộc source, debug options, Java release, compiler và tối ưu. Công cụ phân tích cần phân biệt **thiếu debug metadata** với **class file bị lỗi**.

## 7. Đọc `-l`: nối BCI với line number và local variable

Đây là bước biến bản bytecode thành lời giải thích dễ hiểu cho người học.

### 7.1. `LineNumberTable` cho biết điều gì?

Ở method `compute`, một `LineNumberTable` có thể thể hiện ý như:

~~~text
LineNumberTable:
  line <dòng khai báo sum>: 0
  line <dòng if>: 4
  line <dòng return sum * 2>: 10
  line <dòng return sum + 1>: 14
~~~

Các nhãn `<dòng ...>` ở đây là **minh họa quan hệ**, không phải dòng output thật của `javap`. Công cụ sẽ in **số dòng nguyên** trong `BytecodeTour.java` và BCI bắt đầu tương ứng. Một dòng Java có thể sinh nhiều opcode, đôi khi hai dòng source liên quan cùng một khoảng BCI, và compiler có thể bỏ một số dòng không cần lệnh.

Theo JVMS, `LineNumberTable` là metadata **tùy chọn**. Nó cho debugger/tracing biết BCI liên quan đến dòng source nào; bản thân nó **không chứa source code** và không cam kết mọi opcode có một dòng Java khác nhau.

### 7.2. `LocalVariableTable` cho biết điều gì?

Khi biên dịch bằng `javac -g`, bạn có thể thấy vùng mô tả dạng:

~~~text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
  ...    ...      0   this   LBytecodeTour;
  ...    ...      1   left   I
  ...    ...      2   right  I
  ...    ...      3   sum    I
~~~

Đây cũng là **sơ đồ giá trị**, không phải dump cụ thể về Start/Length. Bảng cần đọc như sau:

- `Start` là BCI đầu khoảng tồn tại của local variable.
- `Length` là số bytecode-unit của phạm vi sống: thông thường biến có hiệu lực trong khoảng **[Start, Start + Length)**.
- `Slot` là chỉ số vùng local variables của frame, **không phải số dòng Java**.
- `Name` là tên local được compiler lưu để hỗ trợ debug.
- `Signature` trong output của bảng này thường là **field descriptor**; với generic local variables, có thể có `LocalVariableTypeTable` để giữ thông tin generic.

Ví dụ, `slot 3` chứa `sum` trong `compute`. Nếu compiler tái sử dụng slot 3 cho một local variable khác ở đoạn code không trùng phạm vi, bảng có thể có **hai entry cùng Slot nhưng khác Start/Length/Name**. Không có mâu thuẫn: local slots là vùng lưu trữ được quản lý theo bytecode scope chứ không phải định danh biến source vĩnh viễn.

### 7.3. Vì sao `-l` có thể không thấy tên local variables?

Điểm mấu chốt: debug attributes **không bắt buộc** trong class file. `javac` mặc định thường chỉ ghi một phần debug metadata (ví dụ file nguồn và line numbers), còn **local variable names** có thể không được ghi trừ khi bật tùy chọn thích hợp.

So sánh ba cách biên dịch (mỗi lần lệnh sau **ghi đè BytecodeTour.class** trong cùng thư mục; làm tuần tự và xem output ngay sau mỗi lần):

~~~bash
javac -g:none BytecodeTour.java
javap -l -p BytecodeTour

javac -g:lines,source BytecodeTour.java
javap -l -p BytecodeTour

javac -g BytecodeTour.java
javap -l -p BytecodeTour
~~~

Kỳ vọng về metadata:

| Biên dịch | `LineNumberTable` | `LocalVariableTable` |
| --- | --- | --- |
| `javac -g:none` | Thường **không có** | Thường **không có** |
| `javac -g:lines,source` | Có khi method có code tương ứng | Không có local-name debug table do option này |
| `javac -g` | Có khi áp dụng | Có cho các local/parameters compiler giữ metadata |

Đừng suy “không có LocalVariableTable = method không có biến local”. JVM vẫn có `max_locals` và vẫn thực thi `iload`/`istore`; **chỉ tên và phạm vi ánh xạ từ source bị lược bỏ**. Tên tham số cũng có thể được giữ qua `MethodParameters` nếu dùng `javac -parameters`, độc lập phần nào với `LocalVariableTable`; hai attribute có chức năng không hoàn toàn giống nhau.

Để làm lại bài chính sau các lần so sánh:

~~~bash
javac -g BytecodeTour.java
javap -c -v -s -l -p BytecodeTour
~~~

## 8. Nối cả bốn tùy chọn thành một quy trình đọc

Khi muốn giải thích vì sao lời gọi `compute(4,8)` trả `24`, hãy lần theo đúng thứ tự sau:

**Bước 1 — từ source nhận diện method.** `public int compute(int left, int right)` nhận hai `int`, trả `int`.

**Bước 2 — dùng `-s` xác định descriptor.** Tìm `compute` với `(II)I`. Nếu class có nhiều overload, descriptor giúp chọn đúng method, tránh nhầm `compute(long,long)`.

**Bước 3 — dùng `-c` theo operand stack.** Tìm `iload_1` và `iload_2`, `iadd`, `istore_3`, các lệnh so sánh, hai nhánh `ireturn`. Thử giá trị 4 và 8 để suy kết quả 24.

**Bước 4 — dùng `-v` hiểu operands.** Nếu có `getfield #N`, `invokevirtual #M` hoặc `invokedynamic #K`, tra entries `#N`/`#M`/`#K` trong constant pool và các bootstrap attributes liên quan. Biết chính xác owner/name/descriptor thay vì đoán từ mnemonic.

**Bước 5 — dùng `-l` kiểm tra ánh xạ source.** Tìm BCI tương ứng dòng `sum`/`if`/`return` và slot của `left`, `right`, `sum`. Nếu metadata thiếu, bật `-g` rồi biên dịch lại khi bạn có source và có quyền; không giả vờ rằng `javap` tự hồi sinh tên biến.

**Bước 6 — tách bằng chứng khỏi suy luận.** Bytecode là bằng chứng về cấu trúc class file **đã được compiler tạo ra**; không bảo đảm JVM thực thi từng opcode bằng đúng một lệnh CPU. JVM có thể interpreter hoặc JIT-compile tùy VM, nhưng các hành vi quan sát phải đúng yêu cầu của Java/JVMS.

### Sơ đồ đối chiếu cho một biểu thức

~~~text
Source Java:
    int sum = left + right;
          |
          v
Method descriptor (-s):
    compute(II)I
          |
          v
Bytecode (-c):
    iload_1 -> iload_2 -> iadd -> istore_3
          |
          v
Debug info (-l, nếu có):
    BCI 0 -> dòng source có phép cộng
    slots: 1=left, 2=right, 3=sum
          |
          v
Verbose (-v):
    Code { max_stack, max_locals, LineNumberTable,
           LocalVariableTable, StackMapTable, ... }
~~~

Điểm tinh tế: biểu thức `left + right` chỉ thao tác local ints, nên những lệnh `iload` và `iadd` **không cần** constant-pool entry cho mỗi biến. Ngược lại, `getfield`/`invokevirtual`/`new` thường tham chiếu constant pool vì chúng cần biết class/field/method được gọi.

## 9. Một số mẫu opcode thường gặp và ý nghĩa Java

| Java source minh họa | Bytecode thường gặp | Cách diễn giải |
| --- | --- | --- |
| `int x = a + b;` | `iload`, `iadd`, `istore` | Nạp, cộng, lưu số nguyên |
| `if (x > 10)` | `iload`, `bipush`, `if_icmple` | Nhảy theo **điều kiện đảo** để bỏ qua nhánh true |
| `return x;` trong method `int` | `iload`, `ireturn` | Trả `int` về caller |
| `new Foo()` | `new`, `dup`, `invokespecial <init>` | Cấp phát và khởi tạo object |
| `obj.name` | `aload`, `getfield` | Đọc instance field |
| `Foo.count` | `getstatic` | Đọc static field |
| `obj.work()` | `invokevirtual` hoặc cơ chế invoke phù hợp | Gọi method, dispatch phụ thuộc kiểu và opcode |
| `Interface m = ...; m.work()` | Có thể `invokeinterface` | Gọi qua interface reference |
| `System.out.println(x)` | `getstatic`, `invokevirtual` | Lấy `PrintStream` rồi gọi method |
| `label + ":" + value` | Có thể `invokedynamic` với `StringConcatFactory` trên compiler hiện đại | Nối chuỗi không nhất thiết dựng `StringBuilder` như compiler cũ |
| `try/catch` | `Exception table` + handlers | Mô tả phạm vi exception; không chỉ nhìn opcode branch |
| `switch` trên số nguyên | `tableswitch` hoặc `lookupswitch` | Lựa chọn nhánh theo giá trị, tùy mật độ case |

Bảng này mô tả **khuynh hướng biên dịch**, không phải hợp đồng “một cấu trúc source luôn đúng một chuỗi opcode”. Compiler có thể thay đổi chiến lược mà vẫn tạo class hợp lệ. Đặc biệt, đừng xem việc không thấy `StringBuilder` là lỗi: từ Java 9, compiler thường dùng `invokedynamic` cho nối chuỗi.

## 10. Mở rộng: generics và bridge method làm class khác source

Source Java dùng generics nhưng JVM thực thi dựa trên descriptors và, khi cần, compiler-generated bridge methods. Ví dụ này chạy độc lập bằng Java 17+; tạo file **`BridgeDemo.java`**:

~~~java
interface Handler<T> {
    T process(T input);
}

final class TextHandler implements Handler<String> {
    @Override
    public String process(String input) {
        return input + "!";
    }
}

public class BridgeDemo {
    public static void main(String[] args) {
        Handler<String> handler = new TextHandler();
        System.out.println(handler.process("ok"));
    }
}
~~~

~~~bash
javac -g BridgeDemo.java
java BridgeDemo
javap -c -v -s -l -p TextHandler
~~~

**Stdout chương trình:**

~~~text
ok!
~~~

Hãy tìm trong `TextHandler.class`:

- Method thực do source khai báo, có descriptor `(Ljava/lang/String;)Ljava/lang/String;`.
- Một **bridge method** do compiler tạo để đáp ứng hợp đồng kiểu sau generic erasure, mang flags như `ACC_BRIDGE` và `ACC_SYNTHETIC`; descriptor thường là `(Ljava/lang/Object;)Ljava/lang/Object;`.
- Bytecode của bridge có thể `checkcast` từ `Object` sang `String` rồi gọi method thực `process(String)`.
- `Signature` attribute lưu generic type information của `Handler<String>`, trong khi JVM method descriptors dùng erased types.

Ví dụ này minh họa tại sao **`methods_count` và `javap -p` có thể cho thấy phương thức không xuất hiện trực tiếp trong source**. Để hiểu class file, bạn cần nhìn đồng thời `flags`, `descriptor`, `Signature`, `Code` và các quan hệ kế thừa/triển khai.

## 11. Đọc class trong package, JAR và module

### Class nằm trong package

Nếu source khai báo `package demo;` và tên class là `demo.BytecodeTour`, biên dịch vào thư mục `out` (thư mục `out` phải tồn tại hoặc tạo trước) rồi dùng **fully qualified class name**:

~~~bash
javac -g -d out src/demo/BytecodeTour.java
java -cp out demo.BytecodeTour
javap -c -v -s -l -p -classpath out demo.BytecodeTour
~~~

Lệnh minh họa này **giả định bạn đã chuyển ví dụ vào file `src/demo/BytecodeTour.java` và thêm `package demo;` ở đầu**; không chạy nguyên xi với file `BytecodeTour.java` không có package từ mục 3.

### Class nằm trong JAR

~~~bash
javap -c -v -s -l -p -classpath app.jar demo.BytecodeTour
~~~

Không cần khởi chạy JAR để xem class. Nếu ứng dụng có nhiều JAR phụ thuộc, bảo đảm class path bạn đang dùng trỏ tới đúng binary cần phân tích. Nếu là **multi-release JAR**, lưu ý có thể tồn tại biến thể class khác nhau cho các phiên bản Java; hãy xác định đúng entry/phiên bản và dùng tùy chọn `--multi-release` (khi được JDK hỗ trợ) hoặc chỉ định chính xác file class cần xem. Đừng lấy bản base rồi kết luận đó là bản code đang được runtime dùng nếu JAR có versioned entries.

### Class thuộc module của JDK

~~~bash
javap -v -p --module java.base java.lang.String
~~~

Ở đây `--module java.base` giúp chọn module; `java.lang.String` là tên class. Output rất dài và phụ thuộc bản JDK. Đây là bài tập đọc **một class thực của JDK**, không bắt buộc phải hiểu mọi chi tiết của source implementation.

## 12. Các ngộ nhận phổ biến

1. **“`javap -c` chạy bytecode.”** Không. Nó **disassemble** class file; chạy chương trình dùng `java`.
2. **“`javap` luôn khôi phục source Java gốc.”** Không. Source comments, nhiều tên local, biểu thức ban đầu hoặc code đã tối ưu có thể không còn đủ thông tin.
3. **“BCI 17 là dòng source 17.”** Không. BCI là vị trí bytecode, phải dùng `LineNumberTable` mới ánh xạ được sang dòng source khi metadata có mặt.
4. **“`#17` trong `getfield #17` là local slot 17.”** Không. Dấu `#` chỉ **constant-pool index** trong ngữ cảnh này.
5. **“`javap -s` hiển thị chữ ký generic đầy đủ.”** Chủ yếu là **JVM descriptors** đã erase; thông tin generics bổ sung nằm ở `Signature`/`LocalVariableTypeTable` khi được ghi.
6. **“Không có `LocalVariableTable` thì method không có biến local.”** Sai. `max_locals` và bytecode hoạt động bình thường; thiếu metadata debug không ngăn JVM chạy.
7. **“`-v` và `-l` yêu cầu runtime có debug agent.”** Không. Chúng đọc metadata từ class file; việc bảng local/line có hay không phụ thuộc quá trình biên dịch.
8. **“`stack=2` là VM có đúng hai Java stack frames.”** Sai. `max_stack` là số **operand stack slots** tối đa của **một method**.
9. **“Lệnh `invokevirtual` luôn thấy method owner là class của object runtime.”** Không nhất thiết. Constant pool lưu symbolic method reference; runtime dispatch có thể chọn implementation của subclass.
10. **“`javap` nhìn thấy đúng JIT machine code HotSpot đang chạy.”** Sai. `javap` xem **class-file bytecode**; JIT-compiled native code là tầng runtime khác.
11. **“Có `main` trong class nên `javap` tự gọi main.”** Sai. `javap` đọc `method_info`, không thực thi thân method.
12. **“Đầu ra `javap` ở mọi JDK giống nhau từng index và opcode.”** Sai. Biến thể compiler/target version có thể thay đổi constant pool, bytecode và metadata mà vẫn giữ ngữ nghĩa ứng dụng.

## 13. Tự kiểm tra

**Câu 1.** Lệnh nào dùng để vừa xem bytecode vừa xem constant pool, descriptor và line/local tables?  
**Đáp án:** `javap -c -v -s -l -p ClassName`, với lưu ý metadata debug có thể thiếu.

**Câu 2.** `(II)I` và `([Ljava/lang/String;)V` lần lượt nghĩa gì?  
**Đáp án:** Method nhận 2 `int`, trả `int`; method nhận một `String[]`, trả `void`.

**Câu 3.** Trong method instance `compute(int,int)`, slot 0 thường chứa gì?  
**Đáp án:** Tham chiếu `this`. Hai `int` parameters nằm ở slot 1/2; local `sum` có thể ở slot 3.

**Câu 4.** Đầu ra có `5: bipush 10` và `7: if_icmple 14`. Số 5 và 7 là dòng Java?  
**Đáp án:** Không, đó là **BCI**. Địa chỉ 14 là branch target BCI do `javap` trình bày.

**Câu 5.** Tại sao `-l` không hiện `left`, `right` mặc dù bytecode có `iload_1` và `iload_2`?  
**Đáp án:** Có thể class không chứa `LocalVariableTable` do compiler không được bật `-g:vars` hoặc `-g`. Slots vẫn tồn tại; tên local có thể thiếu.

**Câu 6.** `-s` hiện descriptor của `List<String>` là gì và xem generic ở đâu?  
**Đáp án:** Descriptor thường là `Ljava/util/List;` do erasure. Tra `Signature` attribute trong `-v` nếu được compiler ghi.

**Câu 7.** Tại sao `TextHandler` có thể có hai method `process` dù source chỉ viết một?  
**Đáp án:** Compiler tạo **synthetic bridge** phục vụ generic interface method sau erasure.

**Câu 8.** Chỉ có `javap -c`, có thể biết chính xác native assembly do HotSpot JIT tạo không?  
**Đáp án:** Không. `-c` hiển thị JVM bytecode từ class file, không phải máy lệnh native sau JIT.

## 14. Tài liệu chuẩn

- [Oracle JDK 25 — `javap` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): các tùy chọn `-c`, `-v`, `-s`, `-l`, `-p`, classpath/module và multi-release.
- [dev.java — `javap`, the Disassembler](https://dev.java/learn/jvm/tools/core/javap/): ví dụ và cách đọc disassembly trong hệ công cụ JDK.
- [JVMS Java SE 25 — Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): `ClassFile`, constant pool, descriptors, access flags, `Code`, `Signature`, `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable` và `StackMapTable`.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): các mã như `I`, `J`, `L...;`, `[` và dấu ngoặc của method descriptor.
- [JVMS Java SE 25 — `4.7.3` Code](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, bytecode, exception table và code attributes.
- [JVMS Java SE 25 — `4.7.12` LineNumberTable](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.12): ánh xạ BCI sang line number.
- [JVMS Java SE 25 — `4.7.13` LocalVariableTable](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.13): local slots, tên biến, descriptor và phạm vi.
- [Oracle JDK 25 — `javac` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): cách dùng `-g`, `-g:lines,vars,source`, `-g:none` và `--release`.

**Cách học hiệu quả:** Đọc **một phương thức** mỗi lần theo chuỗi **source → descriptor (`-s`) → bytecode (`-c`) → constant pool và attributes (`-v`) → BCI, dòng và local slots (`-l`)**. Ghi nhận những gì được class file thực sự lưu, sau đó mới suy luận về Java source hoặc cách JVM thực thi.