# Xem verbose output bằng javap

## 1. Mục đích của javap -verbose

**javap** là công cụ đi kèm JDK để đọc và trình bày thông tin của Java class file. Tùy chọn **-v** hoặc **-verbose** yêu cầu javap hiển thị nhiều chi tiết của class file, giúp quan sát cấu trúc mà JVM sử dụng khi nạp và thực thi lớp.

Lệnh cơ bản:

~~~bash
javap -v demo.Sample
~~~

Lệnh này yêu cầu javap tìm lớp demo.Sample trên classpath mặc định rồi in thông tin chi tiết. Trong dự án, nên chỉ rõ thư mục chứa class file:

~~~bash
javap -classpath out -v demo.Sample
~~~

Verbose output hữu ích khi cần:

- Kiểm tra class file được biên dịch cho phiên bản Java nào.
- Xem tên lớp, superclass, interface và access flags.
- Đọc constant pool và các tham chiếu đến class, field, method.
- Kiểm tra descriptor của field và method.
- Quan sát bytecode trong thuộc tính Code.
- Xem exception table, StackMapTable và các thuộc tính debug.
- Xác nhận annotation, generic signature, record, sealed class hoặc module metadata.
- Điều tra khác biệt giữa source code và class file thực tế được đóng gói.

Cần phân biệt **javap -verbose** với **javac -verbose**. javac -verbose in thông tin hoạt động trong quá trình biên dịch, ví dụ compiler đọc source/class hoặc ghi class file. javap -verbose đọc một class file đã tồn tại và trình bày cấu trúc bên trong nó. Hai lệnh phục vụ hai giai đoạn khác nhau.

javap không chạy static initializer, constructor hay method của lớp đang kiểm tra. Nó đọc cấu trúc bytecode và metadata từ class file; muốn kiểm tra hành vi khi chạy, vẫn cần khởi chạy chương trình hoặc viết test.

## 2. Tạo class file để quan sát

Tạo source file tại src/demo/VerboseSample.java:

~~~java
package demo;

public class VerboseSample {
    public static final int MAX_RETRIES = 3;

    private final String name;

    public VerboseSample(String name) {
        this.name = name;
    }

    public int add(int left, int right) {
        int result = left + right;
        return result;
    }

    public String greeting() {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        VerboseSample sample = new VerboseSample("Java");
        System.out.println(sample.greeting());
        System.out.println("sum=" + sample.add(2, 3));
    }
}
~~~

Từ thư mục gốc dự án, biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 -g -parameters -d out src/demo/VerboseSample.java
~~~

Ý nghĩa các tùy chọn:

- **--release 17:** biên dịch theo API và định dạng bytecode của Java 17.
- **-encoding UTF-8:** đọc source theo UTF-8.
- **-g:** sinh đầy đủ thông tin debug, gồm source/line và local variable information.
- **-parameters:** lưu tên tham số method/constructor để reflection có thể truy xuất.
- **-d out:** ghi class file vào thư mục out, theo cấu trúc package.

Sau khi compile, cấu trúc đầu ra gồm:

~~~text
project/
├── src/
│   └── demo/
│       └── VerboseSample.java
└── out/
    └── demo/
        └── VerboseSample.class
~~~

Chạy chương trình để có kết quả đối chiếu:

~~~bash
java -cp out demo.VerboseSample
~~~

Stdout:

~~~text
Hello, Java
sum=5
~~~

Bây giờ xem class file bằng javap:

~~~bash
javap -classpath out -v -p demo.VerboseSample
~~~

Tùy chọn **-p** hoặc **-private** yêu cầu hiển thị cả thành viên private. Nếu bỏ -p, javap thường chỉ hiển thị các thành viên public/protected theo chế độ mặc định của công cụ. Nội dung verbose cụ thể có thể khác đôi chút giữa các phiên bản JDK, nhưng các nhóm thông tin chính vẫn có ý nghĩa tương ứng.

## 3. Đọc phần mở đầu: class identity và version

Ở đầu verbose output, javap trình bày tên lớp, minor/major version, access flags, tên lớp hiện tại, superclass và interfaces.

Một đoạn minh họa:

~~~text
Classfile .../out/demo/VerboseSample.class
  Last modified ...; size ...
  SHA-256 checksum ...
  Compiled from "VerboseSample.java"
public class demo.VerboseSample
  minor version: 0
  major version: 61
  flags: (0x0021) ACC_PUBLIC, ACC_SUPER
  this_class: ...
  super_class: ...
  interfaces: 0, fields: ..., methods: ...
~~~

Đây là ví dụ minh họa hình dạng output; đường dẫn, checksum, index và số lượng cụ thể phụ thuộc file thực tế.

### Class file version

Hai trường version quan trọng:

- **minor version:** phiên bản phụ của class file.
- **major version:** phiên bản chính của class file.

Một số major version phổ biến:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu class file được biên dịch bằng JDK mới hơn runtime đang chạy, JVM cũ có thể từ chối nạp lớp với lỗi UnsupportedClassVersionError. Vì vậy, major version giúp xác định bytecode đòi hỏi runtime ở mức nào.

Không nên chỉ nhìn version của JDK đang cài trên máy build. Điều quan trọng là release/target thực sự được dùng khi tạo class file. Tùy chọn javac --release giúp khóa API và bytecode theo release đích.

### Access flags

Flags mô tả thuộc tính truy cập hoặc đặc điểm của class/member. Một số flag thường gặp:

- **ACC_PUBLIC:** lớp hoặc thành viên có quyền truy cập public.
- **ACC_FINAL:** lớp không thể được kế thừa hoặc thành viên không thể bị override/ghi đè theo ngữ cảnh tương ứng.
- **ACC_ABSTRACT:** lớp hoặc method abstract.
- **ACC_INTERFACE:** đây là interface.
- **ACC_ENUM:** đây là enum.
- **ACC_ANNOTATION:** đây là annotation type.
- **ACC_SUPER:** flag liên quan đến quy tắc gọi superclass method trong JVM.
- **ACC_SYNTHETIC:** thành phần do compiler sinh ra, không xuất hiện trực tiếp như khai báo source thông thường.
- **ACC_BRIDGE:** bridge method được compiler tạo để bảo đảm dispatch đúng trong một số tình huống generic/covariant return.

Không phải mọi flag đều hợp lệ cho mọi loại cấu trúc. Cần đọc flag theo ngữ cảnh class, field hay method.

## 4. Constant pool: bảng tham chiếu trung tâm

Một phần lớn verbose output là **Constant pool**. Đây là bảng các hằng và symbolic reference mà bytecode sử dụng. Các lệnh bytecode thường tham chiếu đến entry bằng index thay vì lặp lại toàn bộ tên class, tên method hoặc chuỗi.

Ví dụ minh họa:

~~~text
Constant pool:
  #1 = Methodref          #2.#3
  #2 = Class              #4
  #3 = NameAndType        #5:#6
  #4 = Utf8               java/lang/Object
  #5 = Utf8               <init>
  #6 = Utf8               ()V
  ...
~~~

Các index chỉ mang tính minh họa. Khi đọc output thật, hãy lần theo index để hiểu một tham chiếu đang trỏ đến class, tên method và descriptor nào.

Các loại constant pool entry thường gặp:

| Tag | Ý nghĩa |
|---|---|
| Utf8 | Chuỗi được lưu trong class file, dùng cho tên, descriptor và metadata. |
| Integer, Float | Hằng số số nguyên và số thực 32-bit. |
| Long, Double | Hằng số 64-bit; chiếm hai vị trí index trong constant pool theo định dạng class file. |
| Class | Tham chiếu đến tên một class hoặc interface. |
| String | Tham chiếu đến chuỗi hằng. |
| Fieldref | Symbolic reference đến field của class/interface. |
| Methodref | Symbolic reference đến method của class. |
| InterfaceMethodref | Symbolic reference đến method của interface. |
| NameAndType | Kết hợp tên với descriptor. |
| MethodHandle, MethodType | Metadata phục vụ method handle và method type. |
| Dynamic, InvokeDynamic | Hằng động và lời gọi động, thường liên quan đến bootstrap method. |
| Module, Package | Tham chiếu module và package trong class file modular. |

Ví dụ, khi thấy Methodref, có thể lần theo entry để tìm owner class, method name và descriptor. Khi thấy InvokeDynamic, hãy xem thêm BootstrapMethods để hiểu bootstrap method được liên kết với lời gọi động đó.

Constant pool không phải danh sách biến runtime và cũng không phải danh sách toàn bộ object sẽ được tạo khi chương trình chạy. Đây là cấu trúc symbolic/hằng phục vụ việc liên kết và thực thi bytecode.

## 5. Descriptor: kiểu dữ liệu ở cấp JVM

Verbose output hiển thị descriptor của field và method. Descriptor là biểu diễn kiểu theo định dạng class file, không giống cú pháp Java source.

Một số ký hiệu kiểu cơ bản:

| Descriptor | Kiểu Java |
|---|---|
| B | byte |
| C | char |
| D | double |
| F | float |
| I | int |
| J | long |
| S | short |
| Z | boolean |
| V | void, chỉ dùng làm kiểu trả về |
| Ljava/lang/String; | java.lang.String |
| [I | int[] |
| [Ljava/lang/String; | String[] |

Ví dụ descriptor method:

~~~text
(Ljava/lang/String;II)I
~~~

Có thể đọc như sau:

- Phần trong ngoặc là danh sách tham số.
- Ljava/lang/String; là một tham số String.
- Hai ký tự I tiếp theo là hai tham số int.
- Ký tự sau dấu đóng ngoặc là kiểu trả về; I nghĩa là int.

Một method Java có dạng:

~~~java
public int add(int left, int right)
~~~

sẽ có descriptor tương ứng:

~~~text
(II)I
~~~

Một constructor nhận String có descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Constructor không trả về object theo descriptor; nó có kiểu trả về V (void) trong biểu diễn method của JVM.

### Descriptor và generic Signature

Generic type bị type erasure trong phần descriptor dùng để liên kết JVM. Ví dụ:

~~~java
List<String> names;
~~~

Descriptor của field là:

~~~text
Ljava/util/List;
~~~

Thông tin generic có thể được lưu riêng trong thuộc tính **Signature**, nếu có. Vì vậy, khi verbose output hiển thị Signature chứa java/util/List<java/lang/String;>, đó là metadata generic bổ sung, không phải descriptor runtime thay thế.

Sự khác biệt này rất quan trọng khi kiểm tra reflection, bridge method, generic API hoặc tương thích binary.

## 6. Fields và thuộc tính của field

Sau phần class header và constant pool, javap trình bày danh sách field. Mỗi field có thể có access flags, descriptor và các attribute riêng.

Ví dụ field:

~~~java
public static final int MAX_RETRIES = 3;
private final String name;
~~~

Trong verbose output có thể thấy cấu trúc tương tự:

~~~text
public static final int MAX_RETRIES;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 3

private final java.lang.String name;
  descriptor: Ljava/lang/String;
  flags: ACC_PRIVATE, ACC_FINAL
~~~

**ConstantValue** lưu giá trị hằng cho field phù hợp, thường là static final primitive hoặc String có giá trị compile-time constant. Nó không phải attribute được dùng cho mọi field final.

Một số attribute field khác có thể gặp:

- **Signature:** generic signature.
- **RuntimeVisibleAnnotations:** annotation được giữ để runtime reflection đọc.
- **RuntimeInvisibleAnnotations:** annotation không được yêu cầu giữ để runtime reflection, nhưng vẫn có thể được compiler/tool sử dụng.
- **Synthetic:** đánh dấu field do compiler sinh hoặc có tính chất synthetic.

Nếu source có hằng số compile-time, compiler có thể inline giá trị đó vào class file của nơi sử dụng. Khi kiểm tra thay đổi hằng số giữa các module/JAR, cần hiểu rằng chỉ thay class khai báo hằng chưa chắc khiến client đã biên dịch trước nhận giá trị mới; client có thể phải compile lại.

## 7. Methods và Code attribute

Mỗi method có tên, descriptor, access flags và các attribute liên quan. Method có phần thân thường chứa attribute **Code**.

Ví dụ source:

~~~java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
~~~

Verbose output có thể chứa phần tương tự:

~~~text
public int add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC
  Code:
    stack=2, locals=4, args_size=3
       0: iload_1
       1: iload_2
       2: iadd
       3: istore_3
       4: iload_3
       5: ireturn
~~~

Offset và instruction minh họa cho một phương thức đơn giản. Tên local variable và bố cục cụ thể có thể thay đổi theo compiler/debug option.

Các trường trong Code:

- **stack:** số slot tối đa cần trên operand stack của method.
- **locals:** số slot local variable cần trong frame.
- **args_size:** số slot tham số theo biểu diễn mà javap hiển thị; với instance method, slot 0 là this.
- **code_length:** số byte bytecode của method.
- **Exception table:** các vùng bytecode có handler xử lý exception.
- **Nested attributes:** metadata bổ sung như LineNumberTable, LocalVariableTable và StackMapTable.

Bytecode thao tác trên operand stack. Ví dụ iload_1 nạp local variable vào stack, iadd lấy hai giá trị int và đẩy kết quả, istore_3 lưu kết quả vào local slot, ireturn trả giá trị int.

Đây là bytecode ở cấp JVM, không phải mã assembly của CPU. JVM có thể diễn giải bytecode hoặc biên dịch thành mã máy bằng JIT tùy runtime.

## 8. Exception table và StackMapTable

Trong Code attribute, verbose output có thể trình bày exception table:

~~~text
Exception table:
  from    to  target type
     0     8    12   Class java/lang/Exception
~~~

Các cột mô tả khoảng bytecode được bảo vệ, vị trí handler và loại exception được bắt. Khoảng bytecode và offset trong bảng có ý nghĩa theo định dạng JVM; không nên diễn giải chúng như số dòng source.

**StackMapTable** chứa các stack map frame phục vụ bytecode verification. JVM dùng thông tin này trong quá trình xác minh kiểu của operand stack và local variables tại các điểm điều khiển quan trọng.

Khi đọc StackMapTable:

- Frame thể hiện trạng thái kiểu của stack/local tại một bytecode offset.
- Verification type có thể là integer, float, long, double, null, uninitializedThis, object hoặc uninitialized object.
- Object type tham chiếu đến class phù hợp trong constant pool.
- Frame giúp verifier xác minh các nhánh điều khiển và trạng thái stack có nhất quán hay không.

StackMapTable không phải log runtime và không cho biết một nhánh đã thực sự chạy. Nó là metadata tĩnh phục vụ bytecode verification.

Nếu bytecode được tạo thủ công hoặc biến đổi bằng bytecode tool, StackMapTable sai có thể làm JVM từ chối nạp class với VerifyError. Khi đó, cần kiểm tra bytecode và frame metadata, không chỉ source code.

## 9. Debug attributes: line number và local variable

Thông tin debug giúp liên kết bytecode với source. Tùy cách biên dịch, verbose output có thể chứa:

- **SourceFile:** tên source file liên quan.
- **LineNumberTable:** ánh xạ bytecode offset sang số dòng source.
- **LocalVariableTable:** tên local variable, descriptor, slot index và phạm vi hiệu lực.
- **LocalVariableTypeTable:** generic signature của local variable khi có.
- **MethodParameters:** tên tham số và cờ liên quan nếu compiler lưu bằng -parameters.

Có thể biên dịch với các lựa chọn khác nhau:

~~~bash
javac --release 17 -g -parameters -d out src/demo/VerboseSample.java
~~~

Để bỏ toàn bộ debug information:

~~~bash
javac --release 17 -g:none -d out src/demo/VerboseSample.java
~~~

Để chọn một số nhóm debug information:

~~~bash
javac --release 17 -g:source,lines -d out src/demo/VerboseSample.java
~~~

Mặc định javac thường giữ source file và line number information, nhưng không nhất thiết lưu tên local variable. Tùy chọn -g bật đầy đủ debug information; -parameters lưu tên formal parameter cho reflection.

Không có LocalVariableTable không có nghĩa local variable không tồn tại trong bytecode. Compiler vẫn cấp slot cần thiết trong frame; chỉ là tên và phạm vi debug có thể không được lưu.

## 10. Annotation, generic và các attribute mở rộng

Verbose output còn cho thấy nhiều loại attribute mô tả cấu trúc Java nâng cao.

| Attribute | Vai trò |
|---|---|
| Signature | Generic signature của class, field hoặc method. |
| Exceptions | Danh sách checked exception được khai báo trong throws. |
| RuntimeVisibleAnnotations | Annotation được giữ để runtime đọc. |
| RuntimeInvisibleAnnotations | Annotation không có retention runtime nhưng được lưu trong class file. |
| RuntimeVisibleParameterAnnotations | Annotation trên tham số có thể đọc tại runtime. |
| AnnotationDefault | Giá trị mặc định của element trong annotation type. |
| MethodParameters | Tên và modifier metadata của tham số method/constructor. |
| InnerClasses | Thông tin về nested/inner class. |
| EnclosingMethod | Method hoặc constructor bao quanh một local/anonymous class. |
| NestHost / NestMembers | Metadata về nestmate access giữa các class liên quan. |
| Record | Metadata của record class. |
| PermittedSubclasses | Danh sách subclass được phép của sealed class/interface. |
| Module | Module descriptor metadata trong class file modular. |
| BootstrapMethods | Bootstrap method được dùng bởi invokedynamic hoặc dynamic constant. |

Các attribute không xuất hiện trong mọi class. Ví dụ, Record chỉ có ở record class; PermittedSubclasses chỉ liên quan đến sealed type; Module xuất hiện trong module descriptor.

Với lambda hoặc string concatenation, có thể gặp **InvokeDynamic** trong constant pool và **BootstrapMethods** trong class attribute. javac có thể dùng invokedynamic để liên kết hành vi ở runtime thông qua bootstrap method. Không nên kỳ vọng mọi biểu thức lambda hoặc nối chuỗi sẽ được biểu diễn thành một lời gọi method trực tiếp giống source.

## 11. Những tùy chọn javap thường dùng cùng verbose

Verbose output rất chi tiết. Có thể kết hợp các tùy chọn khác để tập trung vào thông tin cần kiểm tra.

| Tùy chọn | Công dụng |
|---|---|
| -v hoặc -verbose | Hiển thị thông tin class file chi tiết. |
| -p hoặc -private | Hiển thị mọi class member, kể cả private. |
| -c | Disassemble bytecode của method. |
| -l | In line number và local variable tables. |
| -s | In internal type signatures/descriptors. |
| -constants | Hiển thị giá trị hằng static final phù hợp. |
| -sysinfo | Hiển thị thông tin hệ thống của class file như đường dẫn, kích thước, thời gian và checksum. |
| -classpath hoặc --class-path | Chỉ định nơi tìm class. |
| -module-path | Chỉ định module path khi tra cứu lớp trong module. |
| -version | Hiển thị phiên bản javap. |

Ví dụ:

~~~bash
javap -classpath out -p -c demo.VerboseSample
~~~

Chỉ tập trung vào khai báo thành viên và bytecode.

~~~bash
javap -classpath out -p -l demo.VerboseSample
~~~

Quan sát line number và local variable table.

~~~bash
javap -classpath out -p -s demo.VerboseSample
~~~

Quan sát descriptor của field và method.

~~~bash
javap -classpath out -p -constants demo.VerboseSample
~~~

Kiểm tra giá trị constant field.

~~~bash
javap -classpath out -v -p demo.VerboseSample > verbose-output.txt
~~~

Lưu toàn bộ verbose output để tìm kiếm hoặc so sánh.

Trên PowerShell cũng có thể redirect:

~~~powershell
javap -classpath out -v -p demo.VerboseSample *> verbose-output.txt
~~~

Nên chọn tùy chọn theo câu hỏi cần trả lời. Khi điều tra class file, thường bắt đầu bằng -v -p, sau đó dùng -c, -l hoặc -s để đọc sâu phần liên quan.

## 12. Đọc class từ JAR và module path

javap có thể đọc class không chỉ từ thư mục output mà còn từ JAR hoặc module.

Nếu JAR nằm ở thư mục lib:

~~~bash
javap -classpath lib/example.jar -v -p com.example.Service
~~~

Nếu cần kiểm tra class thuộc module trên module path:

~~~bash
javap --module-path mods --module com.example.app/com.example.app.Main -v
~~~

Cú pháp module có dạng module-name/class-name. Với module JDK, có thể kiểm tra một class trong module cụ thể:

~~~bash
javap --module java.base -p -s java.lang.String
~~~

Hãy chỉ rõ classpath hoặc module path để tránh javap vô tình đọc một class cùng tên từ vị trí khác. Khi có nhiều phiên bản của cùng một thư viện, kiểm tra đúng JAR thực sự được ứng dụng sử dụng.

Với class trong JAR đa phiên bản (multi-release JAR), việc chọn entry có thể phụ thuộc phiên bản JDK và cách javap được gọi. Khi cần kiểm tra chính xác entry version-specific, hãy xem cấu trúc JAR và tùy chọn javap hỗ trợ trên JDK đang dùng; đừng mặc định rằng mọi công cụ luôn chọn cùng một entry.

## 13. Quy trình điều tra bằng verbose output

Một quy trình thực tế:

1. **Xác định artifact:** tìm đúng class file/JAR mà ứng dụng đang chạy, không chỉ lấy file từ thư mục build gần nhất.
2. **Xác nhận toolchain:** ghi nhận phiên bản JDK/javap và cách artifact được tạo.
3. **In cấu trúc tổng quát:** dùng javap -v -p để xem class version, flags, fields, methods và attributes.
4. **Đọc constant pool và descriptor:** xác định symbolic reference, owner, tên method và kiểu tham số/trả về.
5. **Đọc Code:** dùng -c hoặc phần Code trong verbose để theo dõi bytecode và control flow.
6. **Đọc debug/verification metadata:** xem LineNumberTable, LocalVariableTable, StackMapTable khi điều tra lỗi liên quan.
7. **So sánh artifact:** nếu có hai bản class, lưu output riêng rồi so sánh để tìm thay đổi.
8. **Đối chiếu runtime:** kiểm tra classpath/module path và class thực tế được nạp nếu output không khớp hành vi ứng dụng.

Để so sánh hai artifact:

~~~bash
javap -classpath old.jar -v -p com.example.Service > old.txt
javap -classpath new.jar -v -p com.example.Service > new.txt
~~~

Sau đó dùng công cụ diff của hệ điều hành hoặc IDE. Hãy lưu ý output có thể chứa đường dẫn, timestamp, checksum và index constant pool thay đổi do build; không phải mọi dòng khác nhau đều có nghĩa API hay hành vi đã đổi.

Khi cần so sánh binary compatibility, hãy tập trung vào class/member access, descriptor, superclass/interface, generic signature, checked exceptions, annotation và các thuộc tính ảnh hưởng đến liên kết. Một diff text đơn giản chỉ là manh mối; cần đánh giá theo contract và runtime.

## 14. Lỗi thường gặp khi đọc verbose output

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| javap không tìm thấy class | Classpath sai hoặc dùng tên class không đúng package. | Chỉ rõ -classpath và tên binary đầy đủ. |
| Xem nhầm class cũ | Có nhiều JAR/thư mục chứa cùng tên class. | Kiểm tra nguồn artifact và dùng classpath tối thiểu, rõ ràng. |
| Không thấy private field/method | Chưa dùng -p. | Thêm -p hoặc -private. |
| Không thấy tên local variable | Compile thiếu local-variable debug info. | Biên dịch lại với -g hoặc -g:vars. |
| Không thấy tên tham số reflection | Chưa biên dịch với -parameters. | Bật -parameters và compile lại. |
| Chỉ thấy descriptor khó đọc | Descriptor dùng ký hiệu JVM thay cho cú pháp Java. | Đối chiếu bảng descriptor hoặc dùng javap -s. |
| Không hiểu InvokeDynamic | Chưa đọc BootstrapMethods hoặc constant pool entry liên quan. | Lần theo bootstrap method và dynamic entry. |
| JVM từ chối class version | Artifact mới hơn runtime. | Kiểm tra major version và release đích. |
| javap báo lỗi class file | File không phải class hợp lệ, bị hỏng hoặc quá mới với javap đang dùng. | Xác minh artifact và dùng JDK đủ mới để đọc. |
| Output quá dài | Verbose in mọi metadata và constant pool. | Redirect ra file, tìm theo tên method/attribute hoặc dùng -c/-l/-s phù hợp. |

Không nên sửa trực tiếp bytecode chỉ vì một dòng verbose output có vẻ bất thường. Hãy xác định compiler, source, processor, toolchain và artifact đầu vào trước khi thay đổi.

## 15. Checklist khi xem javap verbose output

- [ ] Đã xác định đúng class file hoặc JAR cần kiểm tra.
- [ ] Đã chỉ rõ classpath/module path để tránh đọc nhầm class.
- [ ] Đã ghi nhận phiên bản javap/JDK.
- [ ] Đã kiểm tra major/minor version và access flags.
- [ ] Đã hiểu cách lần theo index trong constant pool.
- [ ] Đã đọc descriptor của field/method và phân biệt với generic Signature.
- [ ] Đã kiểm tra Code, bytecode, exception table và StackMapTable khi cần.
- [ ] Đã kiểm tra debug attributes và hiểu ảnh hưởng của -g/-parameters.
- [ ] Đã xem annotation, record, sealed hoặc module attributes nếu lớp sử dụng.
- [ ] Đã phân biệt javap -verbose với javac -verbose.
- [ ] Đã đối chiếu class file với runtime/build configuration trước khi kết luận.
- [ ] Đã kiểm soát log verbose để tránh làm lộ thông tin nhạy cảm trong constant pool hoặc đường dẫn nội bộ.

javap -verbose giúp nhìn sâu vào cấu trúc class file mà JVM sử dụng. Khi đọc theo thứ tự class version, flags, constant pool, descriptors, fields, methods và attributes, bạn có thể giải thích bytecode được tạo ra, xác định metadata bị thiếu và điều tra khác biệt giữa source với artifact thực tế.