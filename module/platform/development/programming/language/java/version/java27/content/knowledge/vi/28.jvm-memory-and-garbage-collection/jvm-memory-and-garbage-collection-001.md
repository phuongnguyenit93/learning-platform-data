# Bytecode, class file và kiểm tra bằng javap

> **Phạm vi:** Java 27 — chương **JVM, bộ nhớ và thu gom rác**. Bài học tập trung vào đường đi từ mã nguồn Java tới **JVM bytecode**, cấu trúc file `.class`, cách đọc output của `javap` và ứng dụng khi chẩn đoán lỗi build/runtime. Java SE 27 quy định class-file **major version 71**; các ví dụ sử dụng tính năng chính thức, không cần preview. `javap` giúp hiểu bytecode tĩnh nhưng **không phải công cụ đo heap, garbage collection hay mã máy JIT đã tối ưu**.

## 1. Từ mã nguồn Java tới chương trình chạy trên JVM

Một chương trình Java thường đi qua các bước khái niệm:

~~~text
       Mã nguồn Java (.java)
                │
                │ javac: parse, type-check, lower, emit
                ▼
      Class files (.class)
       │  class metadata
       │  constant pool
       │  method bytecode / attributes
       ▼
    Class loading + linking
    (verify, prepare, resolve)
                │
                ▼
       Class initialization
                │
                ▼
     JVM thực thi bytecode
     ├─ interpreter
     └─ JIT compilation thành machine code khi phù hợp
                │
                ▼
    Đối tượng và dữ liệu lúc chạy
     ├─ heap / GC-managed objects
     ├─ frames, operand stacks, locals
     └─ runtime metadata, native resources
~~~

Sơ đồ diễn đạt tổng quan, không khẳng định JVM phải resolve **mọi** symbolic reference hoặc compile JIT **mọi** method trước khi chạy. Java Virtual Machine Specification (JVMS) cho phép nhiều quyết định linking/execution xảy ra vào thời điểm thích hợp theo hợp đồng.

Một số điểm không nên nhầm:

- **Java source** là đầu vào thông thường của `javac`.
- **Bytecode** là bộ chỉ thị của JVM, độc lập với instruction set của x86/ARM.
- **Class file** là định dạng nhị phân chuẩn để mang bytecode **và** metadata; nó không đơn thuần là một mảng opcode.
- **Class loader** xác định lớp nào được nạp trong runtime; cùng tên class có thể liên quan tới class loader khác nhau.
- **Verifier** kiểm tra ràng buộc class file/bytecode để bảo toàn các quy tắc của JVM.
- **Interpreter/JIT** quyết định cách thực thi bytecode; `javap` hiển thị bytecode trong artifact, không hiển thị assembly do JIT tạo ra.
- **GC** thu gom các đối tượng thuộc phạm vi quản lý bộ nhớ của JVM; việc đọc `new` trong bytecode không cho biết chính xác một object sẽ được cấp phát ở đâu hoặc có bị optimizer loại bỏ hay không.

### 1.1. Một source file có thể sinh nhiều class files

Một `.java` không nhất thiết tương ứng đúng một `.class`. Ví dụ source chứa outer class, nested class hoặc local class có thể tạo thêm các class files. Lambda hiện đại thường được triển khai qua `invokedynamic` và runtime linkage; **không** nên mặc định mỗi lambda có một file `$Lambda.class` nằm trên đĩa.

Các tệp đặc biệt:

- `module-info.java` → `module-info.class` biểu diễn module descriptor.
- `package-info.java` có thể sinh `package-info.class` khi có metadata package.
- Một `record` vẫn là class theo ngữ nghĩa JVM nhưng có thể mang `Record` attribute để mô tả components.
- Class/interface có thể mang attributes như `NestMembers`, `PermittedSubclasses` tùy cấu trúc ngôn ngữ.

## 2. Bài thực hành chung: biên dịch và xem một class

Tạo file **ví dụ** `src/demo/InspectMe.java`:

~~~java
package demo;

public final class InspectMe {
    private InspectMe() {
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static int clampToZero(int number) {
        if (number < 0) {
            return 0;
        }
        return number;
    }

    public static String greeting(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) {
        int total = add(2, 3);
        System.out.println(greeting("Java " + total));
    }
}
~~~

Ví dụ chỉ dùng JDK, không phụ thuộc thư viện ngoài. Tạo sẵn thư mục `src/demo/` và file `InspectMe.java` như mô tả, sau đó chạy từ thư mục cha chứa `src/`.

### 2.1. Xác định đúng JDK

~~~bash
java -version
javac -version
javap -version
~~~

Ba lệnh phải trỏ tới công cụ JDK phù hợp; trong môi trường nhiều JDK, `java`, `javac` và `javap` trên PATH có thể không cùng phiên bản. Khi debug một artifact, cần biết chính xác JDK đã tạo nó và JDK đang chạy ứng dụng.

### 2.2. Biên dịch vào thư mục riêng

~~~bash
javac -g -parameters -d out src/demo/InspectMe.java
~~~

Ý nghĩa:

- `-d out`: đưa class files vào output root `out/`, theo đường dẫn package.
- `-g`: tạo debug information như source file, line numbers và local variable tables.
- `-parameters`: giữ tên formal parameters trong `MethodParameters` attribute phục vụ reflection/công cụ liên quan.
- Không khai báo `--enable-preview`; ví dụ này không yêu cầu preview.

Kết quả dự kiến:

~~~text
out/
└── demo/
    └── InspectMe.class
~~~

Nếu lệnh biên dịch thành công, chạy:

~~~bash
java --class-path out demo.InspectMe
~~~

Kết quả:

~~~text
Xin chào, Java 5
~~~

Chạy thử xác nhận logic cơ bản. Để **nhìn bytecode**, tiếp tục dùng `javap`.

### 2.3. Lệnh javap cơ bản

~~~bash
javap --class-path out demo.InspectMe
~~~

Không có tùy chọn khác, `javap` hiển thị khai báo class và những thành viên theo quyền hiển thị mặc định. Để thấy mọi thành viên, kể cả private constructor:

~~~bash
javap --class-path out -p demo.InspectMe
~~~

Để disassemble bytecode của các method:

~~~bash
javap --class-path out -c -p demo.InspectMe
~~~

Để thấy thêm class-file header, constant pool, attributes và metadata:

~~~bash
javap --class-path out -v -p demo.InspectMe
~~~

**Quan trọng:** `javap` đọc class file/bytecode, không chạy `main()` và không thay thế trình biên dịch. Output là cấu trúc của artifact đang được chọn, không phải kết quả JIT/profile tại runtime.

## 3. Cấu trúc nhị phân của một class file

JVMS §4 mô tả một class file với cấu trúc khái niệm:

~~~text
ClassFile
├── magic (u4)
├── minor_version (u2)
├── major_version (u2)
├── constant_pool_count (u2)
├── constant_pool entries
├── access_flags (u2)
├── this_class / super_class
├── interfaces
├── fields
├── methods
└── attributes
~~~

`u1`, `u2` và `u4` trong đặc tả là đại lượng không dấu, có kích thước lần lượt 1, 2 và 4 byte. Dữ liệu trên đĩa dùng định dạng nhị phân theo JVMS chứ không phải văn bản giống output `javap -v`.

| Thành phần | Vai trò |
| --- | --- |
| `magic` | Dấu định dạng class file; cố định là `0xCAFEBABE` |
| `minor_version` + `major_version` | Version của định dạng class file |
| `constant_pool` | Bảng ký hiệu/hằng số: class, method/field refs, string, numeric constants, method handles... |
| `access_flags` | Cờ class/interface như `ACC_PUBLIC`, `ACC_FINAL`, `ACC_INTERFACE`... |
| `this_class`/`super_class` | Tham chiếu tới tên class hiện tại/superclass thông qua constant pool |
| `interfaces` | Những interface được khai báo triển khai/kế thừa |
| `fields` | Tên, descriptor, access flags và attributes của fields |
| `methods` | Methods, constructors, descriptors, attributes và `Code` khi có |
| `attributes` | Metadata mở rộng; phạm vi và ý nghĩa phụ thuộc loại attribute |

File `.class` không phải file mã nguồn đã “đổi phần mở rộng”. Những biểu thức, block và cấu trúc cú pháp cấp cao có thể đã được biên dịch thành nhánh, lời gọi method và metadata khác. Một vài thông tin source có thể đã mất vĩnh viễn.

### 3.1. Magic number và class-file version

Phần đầu của một class file thông thường:

~~~text
CA FE BA BE  00 00  00 47  ...
│            │      │
│            │      └─ major 0x0047 = 71 (Java 27)
│            └─ minor 0x0000 = 0
└─ magic 0xCAFEBABE
~~~

Các byte minh họa được viết theo thứ tự **big-endian** của file. Có thể xác minh bằng:

~~~bash
javap -v out/demo/InspectMe.class
~~~

Với `javac` JDK 27 biên dịch mặc định (không dùng `--release` cũ và không preview), bản ghi `javap -v` dự kiến có:

~~~text
minor version: 0
major version: 71
~~~

Đây là **version class file**, không phải phiên bản GC, phiên bản máy ảo HotSpot, kích cỡ object trên heap hay phiên bản của dependency manager.

### 3.2. Bảng class-file major versions thường gặp

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| **Java 27** | **71** |

Java 27 hỗ trợ đọc các class files với major version hợp lệ trong phạm vi được JVMS 27 định nghĩa. Một JVM cũ hơn **không** chạy được class file yêu cầu version mới hơn chỉ vì tên API quen thuộc.

### 3.3. Minor version 65535 và preview

Với class-file version hiện đại, `minor_version = 65535` dùng để đánh dấu phụ thuộc vào preview features của **đúng Java release đó**. Ví dụ class file `71.65535` gắn với preview của Java 27 và cần chạy trên đúng phiên bản cùng preview enabled.

**Bài học này không dùng preview features.** Trong ví dụ bình thường, mục tiêu là `71.0`. Đừng thay đổi minor version thủ công để “sửa” lỗi tương thích hoặc cố chạy class file preview của release khác.

### 3.4. Vì sao class file có constant pool?

Thay vì ghi đầy đủ tên class, method, string tại mỗi bytecode instruction, class file dùng nhiều **chỉ số vào constant pool**:

~~~text
constant_pool:
  #1 = Methodref ... demo/InspectMe.add:(II)I
  #2 = Class     ... java/lang/System
  #3 = Fieldref  ... java/lang/System.out:Ljava/io/PrintStream;
  ... (chỉ minh họa ý nghĩa, chỉ số và thứ tự thật có thể khác)
~~~

Khi gặp lệnh `invokestatic #1` hoặc `getstatic #3`, JVM sử dụng symbolic reference tương ứng để phục vụ linkage/resolution. Dòng `#1` **không phải địa chỉ bộ nhớ của method trong process**.

Constant pool **trong class file** và **runtime constant pool** thuộc hai mô hình khác nhau (metadata on disk vs runtime representation). Đừng xem bảng từ `javap -v` như một heap dump hoặc danh sách tất cả object đang sống.

## 4. Bytecode của JVM vận hành theo operand stack

JVM là một máy ảo có instruction set thiên về **stack-based operations**. Mỗi lần gọi method tạo một **frame** logic chứa:

- **Local variables array**: các slot cho tham số và biến cục bộ/giá trị tạm.
- **Operand stack**: chỗ tạm chứa operands và kết quả khi các instruction đang thực thi.
- Thông tin hỗ trợ thực thi, liên kết và trả về theo JVMS.

### 4.1. Đọc bytecode của phép cộng

Phương thức trong ví dụ:

~~~java
public static int add(int a, int b) {
    return a + b;
}
~~~

Chạy:

~~~bash
javap --class-path out -c -p demo.InspectMe
~~~

Phần `add` dự kiến tương tự:

~~~text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

Diễn giải:

| Offset | Instruction | Tác dụng |
| ---: | --- | --- |
| 0 | `iload_0` | Lấy `int` ở local slot 0 (`a`) đưa lên operand stack |
| 1 | `iload_1` | Lấy `int` ở slot 1 (`b`) đưa lên stack |
| 2 | `iadd` | Pop hai giá trị `int`, tính tổng, push kết quả |
| 3 | `ireturn` | Pop kết quả `int` và trả về caller |

~~~text
Bắt đầu:  locals=[a=2, b=3]    stack=[]
iload_0: locals=[a=2, b=3]    stack=[2]
iload_1: locals=[a=2, b=3]    stack=[2,3]
iadd:    locals=[a=2, b=3]    stack=[5]
ireturn:                          trả về 5
~~~

Các số trước dấu `:` là **bytecode offsets trong Code array**, không phải số dòng mã nguồn. Không coi offset luôn tăng đúng 1; instruction khác có thể mang operands và chiếm nhiều bytes.

### 4.2. max_stack, max_locals và args_size

Trong `javap -v` có thể thấy:

~~~text
Code:
  stack=2, locals=2, args_size=2
~~~

Đối với `add(int,int)`:

- `stack=2`: operand stack cần tối đa hai slots ở các đường chạy bytecode hợp lệ.
- `locals=2`: local variable array có hai slots.
- `args_size=2`: số slots của tham số method trong layout này.

Một slot không đồng nghĩa “một biến Java source”. Các kiểu `long` và `double` chiếm **hai** local variable slots; các giá trị primitive/reference khác thường chiếm một slot. Với instance method, `this` nằm ở local slot 0; với static method như `add` thì không có `this`.

Các con số này **không** cho biết dung lượng stack thực tế của OS thread hay kích cỡ memory allocation khi JVM tối ưu hóa runtime.

### 4.3. Những nhóm bytecode phổ biến

| Nhóm | Instruction ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đẩy hằng | `iconst_0`, `bipush`, `ldc` | Đưa giá trị/hằng số vào operand stack |
| Load/store locals | `iload`, `aload_0`, `istore`, `astore` | Di chuyển giá trị giữa locals và stack |
| Số học | `iadd`, `imul`, `ladd` | Tính toán theo loại primitive |
| Rẽ nhánh | `ifeq`, `if_icmplt`, `goto` | Điều khiển control flow |
| Switch | `tableswitch`, `lookupswitch` | Phân nhánh theo nhãn số nguyên |
| Đọc/ghi field | `getfield`, `putfield`, `getstatic` | Làm việc với field |
| Tạo object | `new`, `dup`, `invokespecial` | Khởi tạo instance theo semantics của JVM |
| Gọi method | `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial` | Link/gọi các kiểu method |
| Dynamic linkage | `invokedynamic` | Call site có bootstrap/linkage động |
| Return/throw | `ireturn`, `areturn`, `return`, `athrow` | Trả giá trị, trả void hoặc ném exception |
| Monitor | `monitorenter`, `monitorexit` | Vào/ra intrinsic monitor trong synchronized statement |

Lệnh `getstatic java/lang/System.out` lấy reference tới output stream; `invokevirtual java/io/PrintStream.println` thường dùng để gọi method `println`. Chú thích của `javap` giúp đọc symbolic references; đừng dựa vào số hiệu `#n` như một phần API ổn định.

## 5. Cách đọc if/else, vòng lặp và control flow

Xem phương thức:

~~~java
public static int clampToZero(int number) {
    if (number < 0) {
        return 0;
    }
    return number;
}
~~~

Một cách biên dịch hợp lệ với `javac` có thể có hình dạng:

~~~text
0: iload_0
1: ifge          6
4: iconst_0
5: ireturn
6: iload_0
7: ireturn
~~~

Ý nghĩa:

1. `iload_0` đưa `number` lên operand stack.
2. `ifge 6` so sánh với 0: nếu lớn hơn hoặc bằng 0 thì nhảy tới offset 6.
3. Nếu âm, push 0 và trả về.
4. Nếu không âm, load `number` và trả về.

**Không đọc `ifge` như một `if` của source theo từng ký tự.** Compiler có thể đảo điều kiện, thêm `goto` hoặc chọn layout khác; điều quan trọng là control flow và kết quả tương đương.

### 5.1. Loop không có opcode riêng mang tên for hoặc while

Ví dụ:

~~~java
public static int sumUpTo(int n) {
    int total = 0;
    for (int i = 1; i <= n; i++) {
        total += i;
    }
    return total;
}
~~~

`javap -c` thường thể hiện vòng lặp bằng load/compare, conditional branch, `iinc` để tăng biến đếm và `goto` để trở về đầu vòng. Không có instruction đặc biệt `for` hoặc `while`.

Tại mức bytecode, hai chương trình Java source dùng `for` và `while` có thể tạo ra control flow rất giống nhau. Đây là ví dụ vì sao **không thể khôi phục một cách duy nhất mã nguồn ban đầu** từ output disassemble.

### 5.2. switch thường là tableswitch hoặc lookupswitch

Với switch trên `int`, compiler có thể chọn:

- `tableswitch`: thích hợp khi tập nhãn case đủ dày.
- `lookupswitch`: thích hợp khi nhãn case thưa.

Lựa chọn thực tế thuộc compiler, không nên khẳng định mỗi source `switch` bắt buộc được ánh xạ thành một opcode cụ thể. Switch trên `String` hay pattern matching có thể liên quan nhiều bước lowering và lời gọi hỗ trợ khác; phân tích bytecode cần xét compiler version và tính năng ngôn ngữ đã sử dụng.

## 6. Constant pool: xem symbolic references thực tế

Chạy:

~~~bash
javap --class-path out -v -p demo.InspectMe
~~~

Một số mục thường thấy trong vùng `Constant pool:`:

~~~text
Constant pool:
   #... = Utf8               demo/InspectMe
   #... = Class              #...
   #... = Utf8               java/lang/Object
   #... = NameAndType        #...:#...
   #... = Methodref          #.../#...
   #... = Fieldref           #.../#...
   #... = String             #...
   #... = InvokeDynamic      #...:#...
~~~

Các dấu `#...` là **ký hiệu minh họa**; index, thứ tự và nội dung đầy đủ do `javac` sinh ra nên thay đổi theo nguồn, release và flags biên dịch.

| Loại entry | Vai trò |
| --- | --- |
| `CONSTANT_Utf8` | Chuỗi bytes mô tả tên, descriptor, literal text và metadata (modified UTF-8 của class-file format) |
| `CONSTANT_Class` | Ký hiệu class/interface hoặc array type |
| `CONSTANT_NameAndType` | Ghép tên method/field và descriptor |
| `CONSTANT_Fieldref` | Tham chiếu tượng trưng đến field |
| `CONSTANT_Methodref` | Tham chiếu tượng trưng đến method/class |
| `CONSTANT_InterfaceMethodref` | Tham chiếu method của interface |
| `CONSTANT_String` | Constant string literal |
| `CONSTANT_Integer/Float/Long/Double` | Hằng số số tương ứng |
| `CONSTANT_MethodHandle` | Mô tả method handle |
| `CONSTANT_MethodType` | Mô tả kiểu method |
| `CONSTANT_Dynamic` | Hằng được tính qua bootstrap method |
| `CONSTANT_InvokeDynamic` | Call site được linked động, ví dụ lambda/string concatenation |
| `CONSTANT_Module/Package` | Tên module/package trong metadata có liên quan |

**Đừng nhầm `CONSTANT_String` với một object `String` chắc chắn đã được cấp phát trên heap ngay lúc class được compile.** Constant pool là cấu trúc metadata; việc runtime materialize các giá trị và quản lý chúng là một chuyện khác.

### 6.1. Constant pool dùng index bắt đầu từ 1

JVMS quy định constant pool dùng index phù hợp từ `1`; vị trí `0` không phải một constant pool entry bình thường. Entry `long` và `double` trong class-file constant pool sử dụng **hai chỉ số** trong bảng dù dữ liệu của entry được chứa tại chỉ số đầu tiên; chỉ số theo sau không được dùng như entry độc lập.

Vì vậy, không cần kỳ vọng index `#1, #2, #3, ...` đều tương ứng liên tục với các object tượng trưng riêng biệt khi nhìn output.

### 6.2. Tham chiếu được resolve khi nào?

Một bytecode như `invokestatic #15` dùng thông tin tượng trưng về owner/name/descriptor từ constant pool. Khi thực thi hoặc linking, JVM phải resolve được tham chiếu đó theo Java access, method resolution và class-loading rules.

JVM có thể thực hiện một số việc resolution sớm hoặc muộn trong giới hạn JVMS. **Không** hiểu mọi entry constant pool đều lập tức trỏ tới method/field đã được load khi process bắt đầu.

Hệ quả chẩn đoán:

- Class `A` có thể load thành công nhưng thất bại khi đến một đường code thật sự sử dụng `B` còn thiếu.
- Một lỗi `NoSuchMethodError` có thể phản ánh runtime thư viện có method descriptor khác bản dùng khi compile.
- Tham chiếu tới package không export trên module path có thể dẫn tới lỗi truy cập dù tên class đúng.

## 7. Descriptor: chữ ký nhị phân không phải tên Java source

JVM dùng **descriptors** để mô tả kiểu fields và methods. Descriptor là một ngôn ngữ ký hiệu cụ thể, không dùng đúng cú pháp generic type parameters của Java source.

### 7.1. Kiểu primitive

| Java type | Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` (return type) | `V` |

Ví dụ `int` được ký hiệu bằng `I`; `long` là `J`, **không** phải `L`.

### 7.2. Object và array descriptors

| Java type | Descriptor |
| --- | --- |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `String[]` | `[Ljava/lang/String;` |
| `demo.InspectMe` | `Ldemo/InspectMe;` |

Trong descriptor:

- Dấu `/` phân chia tên package ở dạng internal name.
- Cặp `L...;` mô tả class/interface reference.
- Mỗi dấu `[` thêm một chiều của array.

Đây là **ký pháp của JVMS**, không phải đường dẫn filesystem. Vì vậy `Ljava/lang/String;` là descriptor cho kiểu, không phải đường dẫn file mang tên `String;`.

### 7.3. Method descriptors

Cấu trúc tổng quát:

~~~text
(ParameterTypes)ReturnType
~~~

Ví dụ:

| Java method | JVM descriptor |
| --- | --- |
| `int add(int, int)` | `(II)I` |
| `void print(String)` | `(Ljava/lang/String;)V` |
| `String name()` | `()Ljava/lang/String;` |
| `void main(String[])` | `([Ljava/lang/String;)V` |
| `boolean accept(int[], long)` | `([IJ)Z` |

Xem descriptor trực tiếp:

~~~bash
javap --class-path out -s -p demo.InspectMe
~~~

Ví dụ phần `add`:

~~~text
public static int add(int, int);
  descriptor: (II)I
~~~

Trong JVM, **tên method + descriptor** tham gia xác định chữ ký ở cấp bytecode. Vì vậy, thay đổi kiểu tham số, kiểu trả về hoặc cách generic type erasure diễn ra có thể ảnh hưởng **binary compatibility** ngay cả khi tên method vẫn giống.

### 7.4. Type erasure và Signature attribute

Ví dụ Java generics:

~~~java
public static java.util.List<String> names() {
    return java.util.List.of("An", "Bình");
}
~~~

Descriptor ở cấp JVM dùng kiểu đã erasure, chẳng hạn:

~~~text
()Ljava/util/List;
~~~

Thông tin generic `List<String>` có thể được giữ trong `Signature` attribute, ví dụ:

~~~text
()Ljava/util/List<Ljava/lang/String;>;
~~~

Nói cách khác:

- **Descriptor** cần thiết cho type/method linkage ở JVM.
- **Signature attribute** chứa generic metadata để tools/reflection hiểu kiểu nguồn chi tiết hơn khi có.
- JVM không biến `List<String>` thành runtime array những object đã được kiểm tra kiểu phần tử tự động qua descriptor.

Khi debug `NoSuchMethodError`, ưu tiên đối chiếu **method name + descriptor** giữa artifact compile và artifact runtime, không chỉ nhìn lời khai báo Java mà IDE hiển thị.

## 8. Đọc method invocation và object creation

Các opcode gọi method có ý nghĩa khác nhau:

| Opcode | Ví dụ sử dụng | Ý nghĩa cốt lõi |
| --- | --- | --- |
| `invokestatic` | `InspectMe.add(2,3)` | Gọi static method |
| `invokevirtual` | `printer.println(...)` | Gọi virtual instance method |
| `invokeinterface` | Gọi `List.size()` qua reference kiểu interface | Lời gọi trên interface |
| `invokespecial` | Constructor `<init>`, một số private/super calls | Lời gọi có semantics đặc biệt |
| `invokedynamic` | Lambda hoặc string concatenation | Call site được tạo/liên kết bằng bootstrap protocol |

Với một `new SomeClass()`, chuỗi bytecode điển hình có thể là:

~~~text
new           #...   // class SomeClass
dup
invokespecial #...   // SomeClass."<init>":()V
~~~

- `new` tạo reference đến một đối tượng chưa hoàn tất khởi tạo.
- `dup` nhân đôi reference trên operand stack để có thể còn giữ sau lời gọi constructor.
- `invokespecial <init>` thực hiện constructor initialization semantics.

Đây là cách đọc bytecode **về mặt ngữ nghĩa**; đường cấp phát runtime cụ thể có thể bị JIT tối ưu hóa. Không suy ra cứ có `new` thì nhất thiết phải có một allocation sống đến lần GC tiếp theo.

### 8.1. Đọc field access

Ví dụ:

~~~java
final class Counter {
    private int value;

    int next() {
        return ++value;
    }
}
~~~

Bytecode thường sử dụng `aload_0` để nạp `this`, `getfield` để đọc `value`, một số lệnh tính toán và `putfield` để ghi lại. Điều đó giúp thấy `++value` **không tự động nguyên tử giữa nhiều threads**; bytecode nhiều bước không đồng nghĩa có synchronization.

Tuy nhiên, chỉ nhìn lệnh bytecode không đủ để kết luận toàn bộ tính an toàn luồng: phải xét monitor, volatile access, atomics, happens-before và các đường code khác.

### 8.2. Instance method, constructor và static initializer

Khi xem `javap -p -c`:

- Constructor hiển thị theo cú pháp Java class name ở header, nhưng trong constant pool/method name là `<init>`.
- Class initialization logic được đặt trong một method đặc biệt `<clinit>` nếu có.
- Instance methods có `this` ở local slot 0; static methods không có.
- Compiler có thể thêm các method private/synthetic hoặc bridge methods để giữ semantics, đặc biệt với generics/lambda và nested constructs.

**Không** tìm một method tên `<clinit>` cho mọi class; nếu không có khởi tạo tĩnh cần thực thi, class file có thể không chứa method đó.

## 9. invokedynamic, lambda và nối chuỗi hiện đại

Java hiện đại có nhiều cấu trúc cấp ngôn ngữ không ánh xạ một-một thành một bộ opcode đơn giản.

### 9.1. String concatenation có thể dùng invokedynamic

Phương thức:

~~~java
public static String greeting(String name) {
    return "Xin chào, " + name;
}
~~~

Khi biên dịch bằng `javac` hiện đại, bytecode thường dùng `invokedynamic` để tạo call site nối chuỗi, với bootstrap method liên quan `java.lang.invoke.StringConcatFactory`.

Một đoạn output minh họa:

~~~text
aload_0
invokedynamic #... // makeConcatWithConstants:(Ljava/lang/String;)Ljava/lang/String;
areturn
~~~

Đây là **hình dạng thường gặp**, không phải cam kết mọi compiler và mọi biểu thức nối chuỗi đều dùng cùng một instruction/index. Compiler có thể constant-fold biểu thức mà tất cả thành phần là hằng số.

Lệnh `invokedynamic` không có nghĩa chương trình bắt buộc nạp thư viện bên ngoài. Đây là một phần chính thức của JVM instruction set.

### 9.2. Lambda cũng có thể qua invokedynamic

Tạo file `src/demo/LambdaDemo.java` với nội dung đầy đủ:

~~~java
package demo;

import java.util.function.IntUnaryOperator;

public final class LambdaDemo {
    public static int calculate(int input) {
        IntUnaryOperator twice = n -> n * 2;
        return twice.applyAsInt(input);
    }
}
~~~

Khi chạy:

~~~bash
javac -g -d out src/demo/LambdaDemo.java
javap --class-path out -c -p -v demo.LambdaDemo
~~~

`javap` có thể hiển thị:

- `invokedynamic` tạo functional interface instance/call site.
- `BootstrapMethods` liên quan `LambdaMetafactory`.
- Method synthetic dạng `lambda$calculate$...` cho body lambda, tùy cách compiler sinh bytecode.

**Đừng suy luận mỗi lambda sẽ có một class file riêng trên đĩa** hoặc `lambda$...` là tên method phải có ở mọi compiler/JDK. Chỉ các semantics được đặc tả mới là hợp đồng.

### 9.3. BootstrapMethods không phải lời gọi Java thông thường

`BootstrapMethods` attribute chứa thông tin bootstrap phục vụ liên kết các dynamic constants/call sites. Khi phân tích `invokedynamic`:

1. Xem constant pool entry `InvokeDynamic`.
2. Xem `BootstrapMethods` để biết bootstrap method handle và arguments liên quan.
3. Đối chiếu descriptor của call site.
4. Phân biệt mã Java source với bytecode do compiler tạo để hiện thực ngữ nghĩa của lambda/string concat.

Đây là góc nhìn hữu ích khi đọc code do compiler/tool sinh, nhưng **không phải profiling**. `javap` không nói JIT cuối cùng đã inline call site đó hay chưa.

## 10. Các class-file attributes đáng biết

`javap -v` thường hiển thị nhiều attributes ngoài danh sách bytecode. Chúng mang thông tin phụ trợ cho verifier, debugger, reflection và các đặc điểm của ngôn ngữ.

| Attribute | Chức năng |
| --- | --- |
| `Code` | Bytecode, max stack/locals, exception table và attributes bên trong method |
| `SourceFile` | Tên file nguồn ở mức metadata |
| `LineNumberTable` | Ánh xạ bytecode offsets về các dòng source |
| `LocalVariableTable` | Tên, scope, slot và descriptor biến cục bộ khi có debug info |
| `LocalVariableTypeTable` | Generic signatures của local variables khi được lưu |
| `StackMapTable` | Verification type frames để hỗ trợ bytecode verification |
| `Signature` | Kiểu generic đã được lưu trong metadata |
| `RuntimeVisibleAnnotations` | Annotation metadata có thể nhìn bằng reflection tại runtime |
| `RuntimeInvisibleAnnotations` | Metadata annotation không trực tiếp hiển thị qua runtime reflection thông thường |
| `MethodParameters` | Thông tin tên/flags của formal parameters khi compiler ghi |
| `Exceptions` | Checked exception types khai báo trong method signature |
| `BootstrapMethods` | Tham số bootstrap cho dynamic call sites/constants |
| `NestHost`, `NestMembers` | Quan hệ nestmates của các lớp |
| `Record` | Metadata record components |
| `PermittedSubclasses` | Tập direct subclasses được phép của sealed class/interface |
| `Module` | Descriptor thông tin module trong `module-info.class` |

**Không phải class file nào cũng chứa tất cả attributes.** Sự xuất hiện phụ thuộc loại class, compiler flags, release, các annotation được khai báo và cấu trúc nguồn. Ví dụ một method `abstract` hoặc `native` không có `Code` attribute giống method có body Java thông thường.

### 10.1. StackMapTable và bytecode verifier

`StackMapTable` mô tả trạng thái verification types của locals/operand stack tại một số vị trí control flow. Nó giúp JVM type-check bytecode và bảo đảm các đường chạy hợp lệ theo những ràng buộc của JVMS.

Với output `javap -v`, có thể thấy:

~~~text
StackMapTable: number_of_entries = ...
  frame_type = ...
~~~

Đây không phải heap stack trace hoặc danh sách stack frame **đang chạy**. Một `StackMapTable` là **metadata tĩnh trong class file**; runtime stack frames thuộc execution state.

Nếu một method không có `StackMapTable` được in ra, đừng tự kết luận class file không hợp lệ: JVMS có quy tắc về implicit stack map trong nhiều trường hợp.

### 10.2. Debug information giúp stack trace và debugger

Biên dịch:

~~~bash
javac -g -d out src/demo/InspectMe.java
javap -l -c --class-path out demo.InspectMe
~~~

`javap -l` in line tables và local variable tables **nếu chúng hiện diện**. Khi biên dịch `-g:none`, có thể không còn đủ line/source/local information để debugger hiển thị như mong đợi.

Không nhầm:

- `LineNumberTable`: mapping từ bytecode instruction đến dòng mã nguồn.
- `LocalVariableTable`: tên và phạm vi của biến cục bộ.
- `MethodParameters`: metadata formal parameters, có thể thêm qua `-parameters`.
- `Code`: bytecode và thông tin thực thi cần thiết, không phụ thuộc việc có đủ debug symbols hay không.

Xóa debug info không làm bytecode tự an toàn hơn, nhanh hơn hoặc đổi nghĩa của chương trình; nó chủ yếu làm giảm metadata hữu ích khi quan sát/debug và có thể ảnh hưởng độ chi tiết stack traces.

### 10.3. Records và sealed classes trong class file

Ví dụ:

~~~java
package demo;

public record Point(int x, int y) {}
~~~

Sau khi biên dịch `Point.java`:

~~~bash
javap --class-path out -v -p demo.Point
~~~

Bạn có thể thấy `Record` attribute và các method/fields được record declaration tạo ra. Các method như `equals`, `hashCode`, `toString` có thể được hiện thực thông qua `invokedynamic`/bootstrap support của JDK thay vì hàng chục lệnh so sánh theo từng component tự viết.

Với sealed hierarchy:

~~~java
package demo;

public sealed interface Shape permits Circle {}
final class Circle implements Shape {}
~~~

Biên dịch thích hợp có thể tạo `PermittedSubclasses` attribute trên class file của `Shape`; nó diễn đạt giới hạn direct subclasses theo ngữ nghĩa sealed type. Nếu class được biên dịch thành hai file `Shape.class` và `Circle.class`, hãy xem **đúng class file** khi tìm attribute.

### 10.4. synchronized method khác synchronized block

~~~java
public synchronized void increment() {
    value++;
}
~~~

Một synchronized **method** thường được đánh dấu `ACC_SYNCHRONIZED` trong method access flags; không cần đợi thấy `monitorenter` trực tiếp trong `Code` của method.

Ngược lại, đối với:

~~~java
public void increment() {
    synchronized (lock) {
        value++;
    }
}
~~~

Compiler thường dùng `monitorenter`/`monitorexit` và exceptional control flow cần thiết để nhả monitor khi có lỗi. Đây là ví dụ cho thấy **cùng semantics cấp Java có thể được biểu diễn bằng các cấu trúc class file khác nhau**.

## 11. Exception table, try/catch và try-with-resources

Xét method:

~~~java
public static int safeDivide(int value, int divisor) {
    try {
        return value / divisor;
    } catch (ArithmeticException failure) {
        return 0;
    }
}
~~~

Khi `javap -c -v`, phần `Code` có thể chứa:

~~~text
Exception table:
   from    to  target type
    ...   ...   ...   Class java/lang/ArithmeticException
~~~

Mỗi handler mô tả khoảng bytecode được bảo vệ và vị trí xử lý exception. Các cột `from`/`to` là **bytecode offsets**, không phải số dòng source.

### 11.1. try-with-resources được lowering thành cleanup paths

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String load(Path path) throws IOException {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Compiler phải bảo toàn semantics gọi `close()` và suppressed exceptions theo Java language rules. Bytecode có thể chứa các exception handlers, lệnh gọi `close`, `Throwable.addSuppressed` và các nhánh cleanup. `javap -c -p -v` hữu ích để hiểu vì sao một source `try-with-resources` ngắn lại tạo bytecode nhiều hơn dự kiến.

Đừng xóa exception handlers khi viết công cụ biến đổi class file: làm vậy có thể thay đổi cách trả tài nguyên và biến lỗi.

### 11.2. Thấy nhiều nhánh không đồng nghĩa ứng dụng sẽ chậm

Bytecode có thể chứa nhánh ngoại lệ và cleanup dài, nhưng đường chạy bình thường có thể ít instruction hơn và JIT có nhiều cơ hội tối ưu. Dung lượng class file hoặc số lệnh disassemble **không phải thước đo trực tiếp** throughput, allocation rate hoặc GC overhead.

## 12. Bộ công cụ javap: chọn option theo câu hỏi cần trả lời

| Lệnh/option | Thông tin nhận được | Dùng khi |
| --- | --- | --- |
| `javap demo.InspectMe` | Khai báo và thành viên theo quyền mặc định | Kiểm tra API bề mặt |
| `-p`/`-private` | Bao gồm cả private members | Tìm constructor/helper/synthetic |
| `-c` | Disassemble JVM instructions trong methods | Đọc control flow/field/method access |
| `-v`/`-verbose` | Constant pool, flags, descriptors, attributes và chi tiết khác | Điều tra classfile version, signature, linkage |
| `-s` | Method/field JVM descriptors | Điều tra binary compatibility |
| `-l` | Line/local-variable tables | Đối chiếu bytecode offset với source |
| `-constants` | Hằng `static final` | Xem compile-time constants |
| `-sysinfo` | Path, size, timestamp và SHA-256 hash của class được chọn | Xác nhận đang đọc artifact nào |
| `-verify` | Thông tin xác minh class bổ sung | Điều tra verification metadata |
| `--class-path`/`-cp` | Chỉ đường tìm user classes/JAR | Class không ở current directory |
| `--module-path` + `--module` | Chọn named module chứa class | Ứng dụng dùng JPMS |
| `--multi-release` | Chọn version khi xem multi-release JAR | JAR chứa nhiều biến thể bytecode |
| `-version`, `--help` | Kiểm tra phiên bản và cách dùng công cụ | Nhiều JDK hoặc không chắc option |

Manpage Java 27 cho phép truyền tên fully qualified class, path tới file `.class` hoặc URL `jar:file:` trỏ tới entry trong JAR, tùy yêu cầu.

Ví dụ kết hợp thông dụng:

~~~bash
javap -c -l -p -s --class-path out demo.InspectMe
javap -v -p --class-path out demo.InspectMe
javap -sysinfo out/demo/InspectMe.class
~~~

**Cảnh báo:** `javap -verify` in thêm thông tin verification theo chức năng của công cụ; không nên coi output đó là bằng chứng rằng **mọi đường chạy runtime**, mọi dependency và mọi vấn đề bảo mật đã được kiểm chứng.

## 13. Xem class trong JAR, module và thư viện JDK

Đọc class của chính dự án:

~~~bash
javap --class-path out -c -p demo.InspectMe
~~~

Khi artifact được đóng gói:

~~~bash
jar --create --file inspect-demo.jar -C out .
javap --class-path inspect-demo.jar -c -p demo.InspectMe
~~~

Lệnh `jar --create` tạo JAR có các class hiện hữu từ output root; nó không tự động compile source. Cần chạy `javac` thành công trước khi package.

### 13.1. Xác minh JAR và class file thật

~~~bash
jar --list --file inspect-demo.jar
javap -sysinfo --class-path inspect-demo.jar demo.InspectMe
~~~

`jar --list` cho biết entries trong archive; `javap -sysinfo` hỗ trợ xác minh path/size/timestamp và hash của class được xem.

Cách làm này hữu ích khi production đang chạy bản JAR khác bản developer tưởng đã deploy. Nhưng **hash của file .class** không phải hash toàn bộ JAR; nếu muốn so sánh artifact deploy, cần kiểm tra cả artifact và các entry liên quan.

### 13.2. Chọn class từ module path

Với một named module `com.acme.tools` được đóng gói trong `mods/` và class `com.acme.api.Tool`:

~~~bash
javap --module-path mods --module com.acme.tools -c com.acme.api.Tool
~~~

Với class thuộc JDK system module:

~~~bash
javap --module java.base java.lang.String
~~~

Những câu lệnh này chỉ minh họa cách **chọn đúng module**, không có nghĩa `com.acme.tools` đã hiện diện trong mọi dự án. Nếu class thuộc module khác, thay bằng tên module thực tế.

Một descriptor riêng `module-info.class` có thể được kiểm tra từ file đã biên dịch:

~~~bash
javap -v mods/com.acme.tools/module-info.class
~~~

Nó chứa metadata module như requires/exports/opens dưới dạng `Module` attribute, không phải class có method `main`.

### 13.3. Classpath trong Windows và Unix

Nếu có nhiều thư viện trên classpath:

~~~powershell
# Windows PowerShell:
javap --class-path "out;lib/tool.jar" -c demo.InspectMe
~~~

~~~bash
# Linux/macOS:
javap --class-path "out:lib/tool.jar" -c demo.InspectMe
~~~

Tuy nhiên khi phân tích một class được đóng gói trong JAR, chỉ đường dẫn đến JAR đó đã đủ nếu bytecode không yêu cầu tra cứu thêm các class khác để in thông tin đang xét. Nếu không thấy class, cần xem package FQN, output root, JAR content và classpath thật.

### 13.4. Multi-release JAR: một tên class, nhiều bytecode variants

Một **multi-release JAR** có thể chứa base class file và các phiên bản trong:

~~~text
META-INF/versions/21/...
META-INF/versions/25/...
META-INF/versions/27/...
~~~

Tùy vị trí thực tế, những entry được JVM lựa chọn theo runtime version có thể khác base entry. Vì vậy, khi debug lỗi phiên bản hoặc behavior chỉ xuất hiện trên một JDK, cần biết `javap` đang đọc **entry nào**.

JDK 27 `javap` có option `--multi-release <version>`, nhưng tài liệu công cụ cũng lưu ý các giới hạn trong cách dùng class-path form với multi-release JAR. **Không suy ra** chỉ từ `--class-path lib.jar` rằng output luôn là variant được Java 27 load tại runtime. Kiểm tra `jar --list`, lựa chọn version cụ thể, hoặc dùng URL trỏ tới entry chính xác trong JAR khi cần phân tích một variant; đối chiếu lệnh `javap --help` của đúng JDK.

**Điểm nền tảng:** cùng FQN `com.acme.lib.Api` có thể tương ứng nhiều bytecode trong một artifact. Chẩn đoán phải bám đúng variant và JDK đang chạy.

## 14. Dùng javap để phân tích lỗi build/runtime

### 14.1. UnsupportedClassVersionError

Triệu chứng:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 71.0)
~~~

Nguyên nhân: artifact đòi **class-file major version 71** (Java 27) nhưng JVM đang chạy không hỗ trợ class-file version này.

Cách kiểm tra:

~~~bash
java -version
javac -version
javap -v path/to/Suspect.class
~~~

Cách sửa đúng:

- Chạy ứng dụng trên runtime hỗ trợ major version cần thiết, **hoặc**
- Compile lại bằng `javac --release <supported-version>` nếu mã nguồn và APIs dùng thật sự tương thích với release đích.

Không sửa thủ công `major_version` bằng hex editor. Nếu bytecode sử dụng instruction, class-file attributes hoặc APIs mới, đổi số version không biến chúng thành hợp lệ cho JVM cũ.

### 14.2. NoSuchMethodError và binary incompatibility

Giả sử ứng dụng được compile với thư viện có:

~~~java
public static String format(String value);
~~~

Nhưng tại runtime, JAR được tìm thấy lại chỉ cung cấp:

~~~java
public static String format(Object value);
~~~

Hai methods khác **descriptor**:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
(Ljava/lang/Object;)Ljava/lang/String;
~~~

Tùy cách call site được compile/link, việc thiếu method có đúng name+descriptor có thể dẫn tới `NoSuchMethodError` khi liên kết hoặc gọi.

Cách kiểm tra:

~~~bash
javap -s -p --class-path lib/expected.jar com.acme.Formatters
javap -s -p --class-path lib/runtime.jar com.acme.Formatters
~~~

Đối chiếu method name, parameters, return descriptor, static/instance flags và dependency version. Một lỗi linkage có thể đến từ method đã bị xóa, đổi descriptor, đổi class owner hoặc cấu trúc classpath/module khác với môi trường compile.

**Lưu ý:** `NoSuchMethodError` là lỗi **binary compatibility**, không phải lỗi syntax mà `javac` có thể tự động phát hiện khi bạn dùng runtime JAR khác compile JAR.

### 14.3. NoSuchFieldError và IncompatibleClassChangeError

Cùng cách tiếp cận:

~~~bash
javap -p -s -v --class-path lib/runtime.jar com.acme.Settings
~~~

Kiểm tra field có đúng owner/name/descriptor và access flags không; field static/instance có thay đổi không; một class/interface có bị đổi đặc tính liên kết không. `IncompatibleClassChangeError` có các subtype thể hiện vi phạm giả định binary compatibility giữa compile và runtime artifacts.

Không chỉ nhìn Java source mới trong repository rồi mặc định runtime đang chạy đúng source đó; hãy xem artifact được deploy.

### 14.4. ClassNotFoundException và NoClassDefFoundError

Hai lỗi này không giống nhau:

- `ClassNotFoundException`: thường xuất hiện từ API class loading có khai báo checked exception như `Class.forName` khi không tìm được tên class yêu cầu.
- `NoClassDefFoundError`: runtime không thể tìm/định nghĩa một class cần thiết trong quá trình liên kết hoặc chạy code đã biên dịch; cũng có thể liên quan lỗi khởi tạo class trước đó.

`javap` giúp kiểm tra class có thật trong JAR/module đang xét, tên package/FQN và references của caller. Nhưng để xác định class loader nào đã dùng JAR nào, cần xem **runtime classpath/module configuration** và logs/diagnostics của class loading nếu cần.

Không gom mọi lỗi class loading thành “thiếu Maven dependency”; đôi khi artifact có class nhưng runtime chọn phiên bản/loader khác.

### 14.5. VerifyError, ClassFormatError và malformed bytecode

Một class file không hợp lệ có thể gặp:

- `ClassFormatError`: nội dung hoặc cấu trúc class file vi phạm yêu cầu định dạng.
- `VerifyError`: bytecode không vượt qua verification theo ràng buộc của JVM.
- `UnsupportedClassVersionError`: version không được runtime hỗ trợ.

Những tình huống này có thể đến từ bytecode transformation, instrumentation, code generator hoặc artifact bị hỏng. Các bước:

1. Xác định **đúng file** mà JVM load.
2. Dùng `javap -v -p -c` xem header, flags, descriptors, Code, exception table và StackMapTable.
3. Nếu có bytecode transformer/agent, so sánh output trước–sau transformation.
4. Xác nhận class-file target version với JVM chạy.
5. Không “fix” bằng cách bỏ verification hoặc sửa bytes ngẫu nhiên.

`javap` không tự bảo đảm class được JVM chấp nhận ở runtime; nó là công cụ quan sát và phân tích, không thay thế verifier.

## 15. Biên dịch tương thích bằng --release

Java 27 có thể biên dịch code dành cho một Java release cũ được `javac --release` hỗ trợ. Ví dụ với code không dùng API mới:

~~~bash
javac --release 21 -g -d out21 src/demo/InspectMe.java
javap -v out21/demo/InspectMe.class
~~~

Class-file target ở ví dụ sẽ có **major version 65** (Java 21), không phải 71. Ngoài việc chọn class-file target, `--release 21` còn yêu cầu compiler áp giới hạn **ngôn ngữ và API của release 21** cho compilation.

Đây là lý do dùng `--release` thường an toàn hơn chỉ đặt một tuỳ chọn target bytecode riêng khi cần phát hành cho runtime cũ: tạo file version cũ là **chưa đủ** nếu mã còn tham chiếu API JDK mới mà runtime 21 không có.

### 15.1. Compatibility có nhiều tầng

| Tầng | Câu hỏi cần xác minh |
| --- | --- |
| Ngôn ngữ | Source syntax có thuộc release đích không? |
| Class-file format | Runtime có hỗ trợ major/minor version của artifact không? |
| Java SE APIs | Các API chuẩn được dùng có tồn tại ở release đích không? |
| Library ABI | Third-party JAR có đúng class/method/field descriptors không? |
| Class/module loading | Runtime có tìm đúng class và export package phù hợp không? |
| Runtime behavior | Native libraries, reflection, resources, service providers có tương thích không? |

Một class file `65.0` chỉ xác nhận phiên bản định dạng tương ứng Java 21; **không tự chứng minh** các third-party dependencies và mọi runtime behavior đều tương thích Java 21.

### 15.2. Major version của classfile và version của tool có thể khác

Ví dụ `javap` từ JDK 27 có thể inspect một file target Java 21 được sinh bằng `--release 21`. Ngược lại, một `javap` hoặc JVM quá cũ có thể không đọc được class-file version 71.

Hãy ghi rõ:

- Version của `javac` sinh artifact.
- Target `--release` (nếu có).
- Major/minor version quan sát từ class file.
- Version của `java` đang chạy artifact.
- Version của `javap` dùng để phân tích.

## 16. Từ bytecode tới bộ nhớ JVM và GC: những gì javap không nói

Chủ đề nằm trong chương **JVM, bộ nhớ và thu gom rác**, nhưng cần phân biệt rạch ròi bytecode tĩnh với dữ liệu runtime.

### 16.1. JVM stack frame không phải heap allocation

Một method có `max_stack=2` không có nghĩa:

- Mỗi lần gọi method dùng **2 bytes** stack.
- Method tạo đúng 2 heap objects.
- Garbage collector sẽ thu gom hai object.
- Method có lượng RAM cố định từ output `javap`.

`max_stack` là **giới hạn chiều sâu operand stack theo đơn vị slots logic của bytecode**. Local variables và operand stack là thành phần abstract execution frame, không trực tiếp là một phép đo footprint máy thật. JIT có thể dùng registers, stack slots và tối ưu hóa theo implementation.

### 16.2. Có opcode new chưa chắc object được cấp phát như ta tưởng

Ví dụ:

~~~java
public static int compute() {
    var point = new Point(2, 3);
    return point.x() + point.y();
}
~~~

Bytecode có thể biểu diễn việc tạo `Point`, gọi constructor/accessors, đọc fields. Nhưng trong runtime thật, một JIT có thể tối ưu hóa theo phân tích escape và loại bỏ/biến đổi allocation trong trường hợp hợp lệ.

Do đó:

- `javap` giúp thấy **compiler emitted** gì.
- Không chứng minh số lượng heap allocations **sau JIT optimization**.
- Không có đủ dữ liệu để kết luận GC có nguyên nhân từ một method cụ thể.
- Muốn đánh giá allocation/GC, dùng profiling/runtime metrics/JFR/GC logs với workload thực.

Ví dụ `Point` ở đây là một record `record Point(int x,int y){}` được khai báo trong cùng ngữ cảnh/chương trình khi thử nghiệm.

### 16.3. Class metadata và class loading

Class file là artifact trên disk/JAR. Khi load, JVM tạo runtime representation của class, constant pool, method/field metadata theo đặc tả và triển khai thực tế. Với HotSpot, nhiều class metadata được quản lý trong khu vực **metaspace**; object `java.lang.Class` dùng ở Java-level lại có ngữ nghĩa object thông thường.

Đừng suy rằng toàn bộ bytes của `.class` được chép nguyên vẹn vào Java heap. Cũng đừng cho rằng kích cỡ `.class` trên disk bằng lượng metaspace sử dụng. Nếu nghi class-loader leak/metaspace pressure, cần dùng công cụ runtime và xác định lifecycle của class loaders, không chỉ `javap -v`.

### 16.4. Muốn điều tra runtime/GC nên dùng công cụ khác

| Câu hỏi | Công cụ/nguồn phù hợp |
| --- | --- |
| Classfile version, method descriptor, bytecode | `javap -v -p -c` |
| Class nào được load và từ đâu | Class-loading logs, classpath/module diagnostics |
| Heap và GC behavior | GC unified logging, JFR GC events, JVM metrics |
| Những object nào đang sống | Heap dump/heap histogram và analyzer phù hợp |
| CPU/JIT hot spots | JFR profiling/diagnostics, benchmark có kiểm soát |
| Classloader/metaspace behavior | Runtime VM diagnostics/JFR/classloader metrics |

Ví dụ để bật GC log khi thực hành với HotSpot/JDK 27:

~~~bash
java -Xlog:gc --class-path out demo.InspectMe
~~~

Lệnh này **chạy chương trình** và log các GC events phù hợp, khác hoàn toàn với `javap` chỉ đọc class file. Một chương trình chạy rất ngắn có thể không phát sinh GC event đáng kể; đừng dùng demo một lần để rút kết luận tuning GC.

## 17. Java Class-File API: lựa chọn cho phân tích bằng code

Ngoài `javap`, Java SE hiện đại có **Class-File API** trong package `java.lang.classfile`. API này được chuẩn hóa ở **JDK 24 (JEP 484)** và tiếp tục có trong Java 27.

Nó cho phép viết công cụ:

- Parse class files thành mô hình có cấu trúc.
- Duyệt methods, attributes và code elements.
- Biến đổi hoặc sinh class files hợp lệ theo API.
- Xây tooling, instrumentation hoặc static analysis có kiểm soát.

`javap` vẫn là lựa chọn tốt để **inspect thủ công** vì không cần viết chương trình parser. Class-File API thích hợp khi cần phân tích hoặc biến đổi số lượng class files lớn theo cách lập trình.

Không dùng byte-pattern replacement thủ công trên binary `.class` để thay method descriptor hay instruction: class-file format có constant pool, offsets, exception tables, stack maps và nhiều ràng buộc. Việc tạo/transform bytecode cần bảo toàn tính hợp lệ của những cấu trúc đó.

## 18. Quy trình kiểm tra class file theo từng tình huống

### 18.1. Tôi muốn biết file này thuộc Java version nào

~~~bash
javap -v path/to/Example.class
~~~

Tìm `minor version` và `major version`. Với Java 27 bình thường, `71.0`. Nếu artifact trong JAR, hãy xác nhận **entry đúng** đã được chọn trước khi so sánh với runtime.

### 18.2. Tôi muốn biết method nào được expose

~~~bash
javap -p --class-path app.jar com.acme.api.Example
~~~

`-p` bao gồm private; bỏ `-p` để quan sát gần hơn bề mặt API theo mặc định. Với named module, còn cần kiểm tra `exports` và readability: `public` method không tự được module khác truy cập nếu package chưa export.

### 18.3. Tôi muốn biết tại sao code lại gọi nhầm method

~~~bash
javap -s -v --class-path app.jar com.acme.api.Example
~~~

Đối chiếu owner, name và descriptor với runtime JAR. Kiểm tra classpath order/module path và nội dung artifact production, không suy từ source branch hiện tại.

### 18.4. Tôi muốn biết dòng code nào tương ứng một offset

~~~bash
javap -c -l -p --class-path out demo.InspectMe
~~~

Cần class có line debug information phù hợp, thường compile với `-g`. Nếu bị strip debug metadata, `LineNumberTable` hoặc biến cục bộ có thể không còn.

### 18.5. Tôi muốn xem generated code của lambda, record, sealed

~~~bash
javap -v -p -c --class-path out demo.LambdaDemo
javap -v -p -c --class-path out demo.Point
~~~

Tìm `invokedynamic`, `BootstrapMethods`, `Record`, `PermittedSubclasses` tùy ví dụ. Không ép mọi tính năng phải tạo đúng cùng một attribute nếu source/class type không phù hợp.

### 18.6. Tôi muốn biết lỗi runtime có phải do GC không

Không thể trả lời từ `javap`. Xác minh trước:

- Class đúng, method đúng, artifact đúng? → `javap`.
- Độ trễ/CPU/heap/GC thay đổi thế nào? → JFR/GC logs/metrics.
- Một object có còn được giữ sống? → heap profiling và reference graph.
- Class loader có được unload không? → class-loader/runtime diagnostics.

Các câu hỏi thuộc **những cấp độ quan sát khác nhau**; không thay thế lẫn nhau.

## 19. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách sửa tư duy |
| --- | --- | --- |
| `.class` chỉ là source code được đổi extension | Class file là nhị phân chuẩn, gồm bytecode và metadata | Xem JVMS §4 và `javap -v` |
| Bytecode là mã máy x86/ARM | JVM instruction set độc lập phần cứng | JIT mới có thể sinh machine code runtime |
| Major version 71 nghĩa là GC 71 | Nó là class-file version của Java 27 | Phân biệt format version và VM/GC version |
| JVM 21 đọc mọi class Java 27 | JVM cũ không hỗ trợ major 71 | Compile bằng `--release 21` khi source/API tương thích |
| `javap` là decompiler phục hồi Java source chính xác | Disassembler không phục hồi được đầy đủ source ban đầu | Dùng source chính chủ hoặc decompiler với giới hạn hiểu rõ |
| Mọi lambda có file `$Lambda.class` trên disk | Thường dùng `invokedynamic`/runtime linkage | Xem `BootstrapMethods` và compiler output thật |
| Method có source `synchronized` phải có `monitorenter` | Synchronized method có thể dùng `ACC_SYNCHRONIZED` | Xem method flags lẫn Code |
| `StackMapTable` là stack trace runtime | Đó là verifier metadata tĩnh | Dùng runtime diagnostics để lấy stack trace |
| Constant pool là tất cả objects trong heap | Đó là metadata/hằng/symbolic refs của class | Đừng dùng constant pool để kết luận heap usage |
| `new` bytecode chứng minh heap allocation xảy ra | JIT có thể tối ưu allocation | Đo profiling trên runtime/workload thật |
| `max_stack=2` nghĩa là 2 bytes RAM | Số slots logic của JVM operand stack | Đọc JVMS frame model |
| `javap -c` hiển thị chính xác JIT assembly | Chỉ hiển thị classfile bytecode | Dùng JIT/runtime tools nếu cần |
| `javap -l` luôn cho tên local variables | Cần thông tin debug được biên dịch vào | Compile `-g` khi phù hợp |
| Tên class có trong JAR nghĩa là JVM load nó | Còn classpath/module/classloader resolution | Kiểm tra đúng runtime configuration |
| `NoSuchMethodError` là lỗi cú pháp source | Thường là binary mismatch giữa compile/runtime | So sánh method descriptors của artifacts |
| Chỉnh bytes version là cách chạy trên JVM cũ | Không biến APIs/instructions mới thành cũ | Dùng `--release` và kiểm thử runtime đích |
| Nối chuỗi luôn dùng `new StringBuilder()` | Javac hiện đại có thể dùng `invokedynamic` | Đọc output của compiler đang dùng |
| JAR multi-release chỉ có một phiên bản class | Có thể có base và versioned entries | Kiểm tra đúng entry khi phân tích |
| File nhỏ hơn luôn chạy nhanh hơn | Performance phụ thuộc runtime, JIT, I/O, GC | Benchmark/measure thay vì suy từ class size |

## 20. Checklist khi review bytecode trên Java 27

- [ ] Đã xác nhận version chính xác của `java`, `javac` và `javap`.
- [ ] Đã lấy **đúng file .class hoặc JAR** mà ứng dụng thực sự chạy.
- [ ] Nếu class trong module, đã xác nhận module name và module path.
- [ ] Nếu artifact multi-release, đã xác nhận base hay versioned entry.
- [ ] Đã đọc `minor version`/`major version` và biết Java 27 tương ứng major 71.
- [ ] Không dùng preview minor 65535 khi bài toán không yêu cầu preview.
- [ ] Đã phân biệt bytecode offsets với source line numbers.
- [ ] Đã hiểu operand stack, local slots và method descriptors.
- [ ] Không xem số constant pool index như địa chỉ runtime.
- [ ] Khi có binary mismatch, đã đối chiếu owner/name/descriptor/flags.
- [ ] Đã xem `Code`, exception table và attributes khi debug cleanup/control flow.
- [ ] Đã dùng `-g`/`-parameters` phù hợp khi cần source/debug metadata.
- [ ] Không giả định compiler khác/version khác phải tạo bytecode giống từng byte.
- [ ] Đã phân biệt `Record`, `PermittedSubclasses` và `BootstrapMethods` theo trường hợp.
- [ ] Không suy diễn JIT code, heap allocation và GC từ mỗi opcode `new`.
- [ ] Nếu phát hành cho Java cũ, đã dùng `--release` và kiểm thử trên runtime đích.
- [ ] Không chỉnh thủ công bytes hoặc tắt verification chỉ để né `VerifyError`.
- [ ] Khi nghi GC/performance, đã dùng công cụ runtime thực tế thay vì chỉ `javap`.
- [ ] Có lưu lại lệnh tái hiện, JDK version, artifact hash và đầu ra cần thiết cho điều tra.

## 21. Tài liệu chuẩn và API đang được hỗ trợ

- [JVMS Java SE 27 — Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html) — `ClassFile` structure, constant pool, descriptors, attributes và verification.
- [JVMS Java SE 27 — Chapter 6: The Java Virtual Machine Instruction Set](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-6.html) — semantics của từng JVM opcode.
- [JVMS Java SE 27 — Chapter 2: The Structure of the Java Virtual Machine](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-2.html) — frames, operand stack, local variables, run-time data areas.
- [JVMS Java SE 27 — Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-5.html) — class loading, resolution và initialization.
- [Java SE 27 — javap Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html) — `-c`, `-v`, `-p`, `-s`, `-l`, module/class path, multi-release options.
- [Java SE 27 — javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`, `-g`, `-parameters`, `-d`.
- [Java SE 27 — jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — kiểm tra và đóng gói JAR.
- [Java SE 27 API — ClassFile](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html) — Class-File API chính thức dùng phân tích/generate/transform.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484) — API chuẩn từ JDK 24.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280) — string concatenation qua `invokedynamic`.
- [Java SE 27 — java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — runtime classpath, modules và tùy chọn chẩn đoán.
- [Java SE 27 — jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — diagnostics cho JVM đang chạy; bổ sung cho `javap`.

**Kết luận:** Bytecode là instruction set của JVM, còn `.class` là container nhị phân có **constant pool, version, method/field descriptors, Code và attributes**. Trên Java 27, class-file major version thông thường là **71**, có thể kiểm tra trực tiếp bằng `javap -v`. Sử dụng `javap -c -p -s -l -v` một cách có mục đích giúp điều tra compiler output, binary compatibility, class loading và cách ngôn ngữ được lowering. Nhưng `javap` **không mô tả chính xác allocation, GC, JIT hoặc trạng thái bộ nhớ runtime**; những câu hỏi đó cần công cụ quan sát JVM đang thực thi.
