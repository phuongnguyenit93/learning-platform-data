# Dùng javap để xem khai báo, descriptor và bytecode trong Java

Sau khi `javac` biên dịch một tệp `.java` thành `.class`, **mã nguồn đã được chuyển thành cấu trúc class file**: tên lớp, superclass/interface, field, method, kiểu nhị phân, modifiers, constant pool, thuộc tính và các lệnh bytecode. Công cụ **`javap`** trong JDK cho phép đọc những thông tin này mà không phải tự giải mã từng byte của class file.

Bài thuộc nhóm **Kiểm chứng đầu ra** của Java Advance – compilation. Mục tiêu không phải “dịch ngược bytecode thành đúng mã Java gốc”, mà là **xác minh compiler thực sự đã sinh gì**: lớp có member và quyền truy cập như dự kiến không, kiểu trả về/tham số xuất hiện trong **descriptor** ra sao, generics được giữ ở **Signature** hay bị erasure, bytecode dùng những instruction nào, và khi nào xuất hiện bridge method hoặc `invokedynamic`.

Các ví dụ dựa trên Java 17, dùng `javac --release 17` và `javap` của JDK. Kết quả minh họa được kiểm chứng với JDK 24.0.2 biên dịch target 17. Các chỉ số trong constant pool, offset lệnh hoặc một số chi tiết bytecode có thể thay đổi khi đổi compiler/JDK/options; cần phân biệt **cấu trúc và ý nghĩa ổn định** với **cách compiler cụ thể triển khai**.

## 1. javap là gì và được dùng khi nào?

`javap` là **class-file disassembler/inspector** đi kèm JDK, đọc file `.class`, không trực tiếp biên dịch nguồn. Nó có thể:

- Liệt kê các khai báo class/interface, field, constructor và method.
- Hiển thị private members với `-p`.
- Hiển thị JVM **descriptors** với `-s`.
- Disassemble các **instruction** của method có `Code` attribute với `-c`.
- Hiển thị class-file metadata, constant pool, access flags, attributes, bootstrap information với `-v`.
- Hiển thị line number/local variable tables nếu có thông tin debug phù hợp, dùng `-l` kết hợp `-c` hoặc `-v`.
- Hiển thị giá trị compile-time constants với `-constants`.
- Hiển thị checksum/đường dẫn class file với `-sysinfo`.

Một vài tình huống thực tế:

| Câu hỏi | Hướng dùng javap |
|---|---|
| Artifact có method mình tưởng đã compile không? | `javap -p` |
| API binary có chữ ký gì? | `javap -p -s` |
| Compiler sinh toán tử, lời gọi và return thế nào? | `javap -c` |
| Có bridge method do generic/override không? | `javap -p -v` |
| Class thuộc target Java nào? | `javap -v` để đọc major/minor version |
| Có generic Signature dù descriptor đã erasure? | `javap -v`, đối chiếu `descriptor` và `Signature` |
| Bytecode có `invokedynamic` không? | `javap -c` rồi `-v` xem `BootstrapMethods` |
| Dòng nguồn/biến cục bộ gắn opcode nào? | Biên dịch `-g` rồi `javap -c -l` |

**Giới hạn:** `javap` không chứng minh chương trình không có lỗi runtime, không thay thế unit tests và không khôi phục chính xác comments, format, cách viết cú pháp hay ý định nghiệp vụ của source ban đầu.

## 2. Cú pháp cơ bản và cách xác định đúng class cần đọc

Các lệnh điển hình:

~~~sh
javap -classpath out lesson.bytecode.BytecodeSample
javap -classpath out -p -s lesson.bytecode.BytecodeSample
javap -classpath out -c lesson.bytecode.BytecodeSample
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

Với binary name `lesson.bytecode.BytecodeSample`, classpath phải chứa **gốc cây package**: nếu bytecode nằm ở `out/lesson/bytecode/BytecodeSample.class`, thì đặt classpath là **`out`**, không phải `out/lesson/bytecode`.

Có thể truyền path class file trực tiếp:

~~~sh
javap -p -s out/lesson/bytecode/BytecodeSample.class
~~~

Cũng có thể đọc class từ một JAR ở classpath:

~~~sh
javap -classpath artifacts/example.jar -p -s lesson.bytecode.BytecodeSample
~~~

Lệnh JAR trên là ví dụ cú pháp: phải thay `artifacts/example.jar` bằng JAR thật chứa class đó. `javap` **không tự tìm mọi JAR trong dự án**, cũng không tự lấy dependency từ Maven Central hoặc Gradle cache chỉ vì biết tên class.

### 2.1. Kiểm tra JDK và tránh đọc nhầm class cũ

Trước khi kiểm tra, nên chạy:

~~~sh
javac -version
java -version
javap -version
~~~

Sau đó kiểm tra nơi xuất bytecode: `javac -d out` tạo cây output theo package. Nếu một project có nhiều thư mục `target/classes`, `build/classes`, JAR hay module khác nhau, hãy chỉ rõ đường dẫn thay vì dựa vào current directory hoặc biến môi trường.

`javap` có thể đọc thành công **một bản class không phải artifact bạn định kiểm chứng**. Khi gặp kết quả khác source, trước hết tìm binary/path/JAR thực sự được chọn, rồi mới nghi compiler làm sai.

### 2.2. Khác gì so với javac và java?

- **javac**: kiểm tra/biên dịch source thành class file.
- **javap**: kiểm tra cấu trúc class file đã có.
- **java**: khởi chạy và thực thi chương trình trên JVM.

Không thể dùng `javap -c SomeSource.java` như cách chính để disassemble mã nguồn chưa compile. Hãy compile class trước hoặc trỏ tới một class file có sẵn.

## 3. Dự án mẫu Java 17 có field, method, generics và lời gọi

Tạo cấu trúc:

~~~text
project/
├── src/
│   └── lesson/bytecode/
│       ├── BytecodeSample.java
│       ├── Provider.java
│       └── StringProvider.java
└── out/             # tạo khi compile
~~~

Mở terminal tại thư mục `project`, lưu ba file theo đúng tên. Những file chứa public type phải khớp tên public class/interface.

### 3.1. BytecodeSample.java

~~~java
package lesson.bytecode;

import java.util.List;

public final class BytecodeSample {
    public static final int LIMIT = 10;
    private final String name;

    public BytecodeSample(String name) {
        this.name = name;
    }

    public int sum(int left, int right) {
        return left + right;
    }

    public String greeting(String guest) {
        return name + ":" + guest;
    }

    public List<String> names() {
        return List.of(name);
    }

    public static void main(String[] args) {
        BytecodeSample sample = new BytecodeSample("Lan");
        System.out.println(sample.sum(2, 3));
        System.out.println(sample.greeting("Mai"));
    }
}
~~~

Lớp này có:

- `public static final` constant `LIMIT`.
- `private final String name` để quan sát `-p`.
- Constructor nhận String.
- Method `sum(int,int)` phù hợp với descriptor `(II)I`.
- Method `greeting(String)` thực hiện nối chuỗi để quan sát một cách compiler có thể dùng `invokedynamic`.
- Method `names()` trả `List<String>` để so generic `Signature` với erased descriptor.
- Main để kiểm chứng stdout runtime.

### 3.2. Provider.java và StringProvider.java

Tạo **src/lesson/bytecode/Provider.java**:

~~~java
package lesson.bytecode;

public interface Provider<T> {
    T get();
}
~~~

Tạo **src/lesson/bytecode/StringProvider.java**:

~~~java
package lesson.bytecode;

public final class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "ok";
    }
}
~~~

Hai kiểu này giúp quan sát **type erasure** và **bridge method**: interface generic khai báo `T get()`, implementation trả String; compiler cần bảo toàn tương thích với lời gọi thông qua kiểu đã erasure.

### 3.3. Biên dịch và chạy

Linux/macOS:

~~~sh
mkdir -p out
javac --release 17 -encoding UTF-8 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
java -cp out lesson.bytecode.BytecodeSample
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -encoding UTF-8 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
java -cp out lesson.bytecode.BytecodeSample
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
5
Lan:Mai
~~~

`-g` yêu cầu tạo thêm thông tin debug (đặc biệt các bảng local variables và source line) để dùng ở phần `-l`. `--release 17` chọn ngôn ngữ/API và class-file target Java 17, mặc dù JDK dùng để chạy javac có thể mới hơn.

## 4. Bước đầu tiên: javap mặc định liệt kê khai báo

Chạy:

~~~sh
javap -classpath out lesson.bytecode.BytecodeSample
~~~

Phần output đã kiểm chứng:

~~~text
Compiled from "BytecodeSample.java"
public final class lesson.bytecode.BytecodeSample {
  public static final int LIMIT;
  public lesson.bytecode.BytecodeSample(java.lang.String);
  public int sum(int, int);
  public java.lang.String greeting(java.lang.String);
  public java.util.List<java.lang.String> names();
  public static void main(java.lang.String[]);
}
~~~

Những thông tin đáng chú ý:

1. Tên đầy đủ của class là `lesson.bytecode.BytecodeSample`.
2. `public final` của class và `public` của các members xuất hiện trong khai báo.
3. Constructor mang tên class và nhận một String.
4. `sum` có hai tham số int, trả int.
5. `names` ở dạng khai báo có thể hiển thị `List<String>`, vì javap đọc thêm thông tin metadata generic khi có.
6. Field `private final String name` **chưa hiện** trong danh sách mặc định; cần `-p`.

Văn bản này là một **bản trình bày từ class file**, không phải source code nguyên thủy. Nó không chứa thân các method, comment, thứ tự khai báo ở mọi trường hợp hay lựa chọn cú pháp ban đầu.

## 5. Xem đầy đủ thành viên với -p

Chạy:

~~~sh
javap -classpath out -p lesson.bytecode.BytecodeSample
~~~

Trong danh sách có thêm:

~~~text
private final java.lang.String name;
~~~

`-p` (cũng có dạng `-private`) hiển thị mọi thành viên, bao gồm private. Phân biệt với các lựa chọn hiển thị theo mức truy cập khác:

| Tùy chọn | Mục đích |
|---|---|
| Không truyền modifier | Hiển thị các thành viên thông thường theo mặc định của javap, không đầy đủ private |
| `-public` | Chỉ hiển thị thành viên public |
| `-protected` | Hiển thị các thành viên protected và public |
| `-package` | Hiển thị các thành viên từ package access trở lên |
| `-p` hoặc `-private` | Hiển thị tất cả, gồm private |

Khi kiểm tra **binary API được công khai**, có thể xem `-public -s`. Khi kiểm tra cấu trúc thực của class, dùng `-p -s` để tránh bỏ sót private fields/methods và các members được compiler sinh.

### 5.1. Xem giá trị constant với -constants

~~~sh
javap -classpath out -constants lesson.bytecode.BytecodeSample
~~~

Một dòng đáng chú ý:

~~~text
public static final int LIMIT = 10;
~~~

Không nhầm `-constants` với việc đánh giá mọi field `final` tại runtime. Tùy chọn này trình bày **constant values có sẵn trong class-file metadata** khi phù hợp, chẳng hạn constant variable theo quy tắc Java. Với field `private final String name` chỉ được gán ở constructor, không có giá trị constant compile-time để in tương tự.

## 6. Descriptor là gì? Tại sao khác khai báo Java?

**JVM descriptor** là chuỗi mã hóa **kiểu ở mức class-file/binary linkage**, dùng trong mô tả field và chữ ký method. Nó không viết theo cú pháp Java source thông thường. Công cụ `javap -s` hiển thị các descriptor này.

Chạy:

~~~sh
javap -classpath out -p -s lesson.bytecode.BytecodeSample
~~~

Một phần đã kiểm chứng:

~~~text
public static final int LIMIT;
  descriptor: I

private final java.lang.String name;
  descriptor: Ljava/lang/String;

public lesson.bytecode.BytecodeSample(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public int sum(int, int);
  descriptor: (II)I

public java.lang.String greeting(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.util.List<java.lang.String> names();
  descriptor: ()Ljava/util/List;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

Descriptor phản ánh những kiểu JVM dùng để phân giải method/field, không phải việc method đang tính toán gì.

### 6.1. Bảng mã kiểu primitive

| Kiểu Java | Field descriptor |
|---|---|
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` | `V`, chỉ dùng ở vị trí return của method descriptor |

`I` là int, không phải Integer. `J` là long, không phải một tên class. `V` có ý nghĩa method trả void, không được đặt làm field type.

### 6.2. Descriptor cho tham chiếu và mảng

- `Ljava/lang/String;`: tham chiếu tới class `java.lang.String`.
- `Ljava/util/List;`: tham chiếu tới interface `java.util.List`.
- `[I`: mảng một chiều của int (`int[]`).
- `[[I`: mảng hai chiều của int (`int[][]`).
- `[Ljava/lang/String;`: mảng String (`String[]`).
- `[[Ljava/lang/String;`: mảng hai chiều String.

Tên kiểu trong object descriptor sử dụng **slash** thay dấu chấm và kết thúc bằng **semicolon**. Dấu `[` biểu thị thêm một chiều mảng. Với class lồng nhau, binary name có thể chứa dấu `$` như `Outer$Inner`.

### 6.3. Descriptor cho phương thức

Khuôn mẫu:

~~~text
(<descriptors của các tham số theo thứ tự>)<descriptor kiểu trả về>
~~~

Ví dụ:

| Java method | Descriptor |
|---|---|
| `void run()` | `()V` |
| `int sum(int a, int b)` | `(II)I` |
| `String greeting(String s)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `void main(String[] args)` | `([Ljava/lang/String;)V` |
| `long compute(int[] a, boolean b)` | `([IZ)J` |
| `String[][] matrix()` | `()[[Ljava/lang/String;` |

Giải mã `(II)I`: mở `(`, hai tham số int `I I`, đóng `)`, return int `I`. Giải mã `([Ljava/lang/String;)V`: một tham số là mảng String, method trả void.

Constructor trong bytecode có tên đặc biệt `<init>`, return descriptor là `V`. Ví dụ `(Ljava/lang/String;)V` biểu diễn constructor nhận String. `<clinit>` là class initialization method nếu cần; nó khác constructor và thường không xuất hiện như method Java nguồn thông thường.

### 6.4. Descriptor không giữ generic type arguments

`names()` được trình bày ở dạng Java với return `List<String>` nhưng descriptor là:

~~~text
()Ljava/util/List;
~~~

Lý do: **type erasure**. JVM descriptor dùng kiểu thô của `List`, không có phần `<String>`. Một thuộc tính bổ trợ tên **`Signature`** có thể giữ thông tin generic cho compiler/reflection công cụ. Đừng kết luận generics đã “biến mất hoàn toàn khỏi class file” chỉ vì descriptor không chứa type argument.

## 7. Phân biệt descriptor với Signature attribute

Chạy:

~~~sh
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

Trong phần method `names`, output đã kiểm chứng có:

~~~text
descriptor: ()Ljava/util/List;
Signature: #67
~~~

Ở phần bình luận của entry tương ứng, `javap` cho thấy nội dung generic:

~~~text
()Ljava/util/List<Ljava/lang/String;>;
~~~

Ý nghĩa:

- **descriptor**: dạng JVM dùng cho method linkage sau erasure, `()Ljava/util/List;`.
- **Signature**: metadata generic bổ trợ, thể hiện `List<String>`.
- **Khả năng tương thích nhị phân**: không thể giả định hai methods chỉ khác type argument generic tạo thành hai overload hợp lệ; erasure có thể làm trùng chữ ký.

Ví dụ, không thể khai báo đồng thời `void f(List<String> x)` và `void f(List<Integer> x)` trong cùng class chỉ để phân biệt bằng generic type arguments: sau erasure cả hai có parameter type `List`.

### 7.1. Return type và sự khác biệt khi override

Descriptor của method chứa **return type**, dù quy tắc overload Java source không đơn giản cho phép hai method chỉ khác kiểu trả về. Compiler có thể tạo **bridge method** để duy trì polymorphism khi generics/covariant return thay đổi cách mô tả binary. Phần 10 sẽ minh họa điều này bằng class riêng.

## 8. Xem bytecode với -c: đọc JVM operand stack

Chạy:

~~~sh
javap -classpath out -c lesson.bytecode.BytecodeSample
~~~

Trong method `sum`, output đã kiểm chứng:

~~~text
public int sum(int, int);
  Code:
     0: iload_1
     1: iload_2
     2: iadd
     3: ireturn
~~~

JVM dùng máy ảo **operand stack** cho nhiều instruction. Ta có thể mô phỏng:

| Offset | Opcode | Stack trước → sau |
|---|---|---|
| 0 | `iload_1` | `[] → [left]` |
| 1 | `iload_2` | `[left] → [left, right]` |
| 2 | `iadd` | `[left, right] → [left + right]` |
| 3 | `ireturn` | Lấy int khỏi stack, trả về caller |

Trong instance method, local slot **0** thường chứa `this`, còn tham số int `left` và `right` nằm ở slot 1 và 2. Opcode `iload_1` không phải “đọc dòng 1 của source” mà là **đọc local variable slot 1**.

`iadd` cộng hai giá trị int trên operand stack và đẩy kết quả int. `ireturn` dùng cho phương thức trả int (và một số kiểu nhỏ được đại diện theo int trong bytecode). Method trả reference thường dùng `areturn`; method trả void dùng `return`.

### 8.1. Offset không phải số dòng Java

Các số `0, 1, 2, 3` trước dấu hai chấm là **bytecode offsets** trong Code attribute, không phải thứ tự source line. Instruction có độ dài khác nhau, nên offset không nhất thiết tăng mỗi lần một đơn vị. Khi dùng `-g` và `-c -l`, có thể đối chiếu instruction với LineNumberTable.

### 8.2. Constructor có invokespecial và putfield

Phần constructor của BytecodeSample có đoạn:

~~~text
0: aload_0
1: invokespecial #1     // Method java/lang/Object."<init>":()V
4: aload_0
5: aload_1
6: putfield      #7     // Field name:Ljava/lang/String;
9: return
~~~

Diễn giải:

1. `aload_0` lấy `this` lên stack.
2. `invokespecial` gọi constructor superclass `Object.<init>`.
3. `aload_0` và `aload_1` lấy đối tượng và tham số String.
4. `putfield` ghi tham số vào instance field `name`.
5. `return` kết thúc constructor.

Các chỉ số `#1`, `#7` là **constant-pool references** trong class đang đọc, không phải “id phương thức” ổn định giữa hai lần biên dịch. Có thể xem ý nghĩa entry tương ứng bằng `javap -v`.

### 8.3. Các opcode thường gặp

| Opcode | Ý nghĩa |
|---|---|
| `aload_n`, `iload_n` | Đẩy reference/int từ local slot lên operand stack |
| `astore_n`, `istore_n` | Ghi reference/int từ stack vào local slot |
| `iconst_0`, `iconst_1`, ... | Đẩy hằng int nhỏ |
| `ldc` | Nạp constant pool constant có thể dùng với lệnh này |
| `getfield`, `putfield` | Đọc/ghi instance field |
| `getstatic`, `putstatic` | Đọc/ghi static field |
| `new`, `dup` | Tạo object và nhân đôi giá trị đỉnh stack |
| `invokestatic` | Gọi static method |
| `invokevirtual` | Gọi virtual instance method |
| `invokespecial` | Gọi một số instance method đặc biệt, gồm constructor |
| `invokeinterface` | Gọi interface method |
| `invokedynamic` | Dynamic call site được liên kết theo bootstrap method |
| `iadd` | Cộng hai int trên stack |
| `ireturn`, `areturn`, `return` | Return kiểu int, reference hoặc void |
| `ifeq`, `if_icmpge`, `goto` | Điều khiển luồng/nhảy |

Không suy rằng cứ có lời gọi interface trong source là compiler luôn dùng cùng một opcode trong mọi tình huống. Cách chọn instruction còn phụ thuộc loại method, kiểu tĩnh, language rules và kết quả biên dịch.

## 9. String concatenation và invokedynamic

Method mẫu:

~~~java
public String greeting(String guest) {
    return name + ":" + guest;
}
~~~

Với javac target Java 17 trong lần kiểm chứng, disassembly chính là:

~~~text
0: aload_0
1: getfield      #7    // Field name:Ljava/lang/String;
4: aload_1
5: invokedynamic #13, 0 // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
10: areturn
~~~

Compiler dùng một **invokedynamic call site** cho phép runtime thiết lập chiến lược nối chuỗi thích hợp. Khi xem `javap -v`, phần constant pool và `BootstrapMethods` có thông tin về bootstrap method, trong trường hợp triển khai này liên quan `java.lang.invoke.StringConcatFactory`.

Đừng nhầm lệnh `invokedynamic` với việc source “gọi một hàm tên invokedynamic”. Đây là một instruction trong class file. Tương tự, thấy `invokedynamic` không tự chứng minh có lambda; Java hiện đại dùng nó cho nhiều mục đích, gồm nối chuỗi.

Các javac/JDK/target khác có thể sinh bytecode nối chuỗi theo cách khác (chẳng hạn dùng StringBuilder hoặc cơ chế khác). **Kết quả nghĩa vụ quan sát** vẫn là `Lan:Mai` khi chạy ví dụ; hình thức bytecode là một lựa chọn có thể thay đổi.

## 10. Bridge method và synthetic method do compiler sinh

Đọc class StringProvider của phần 3:

~~~sh
javap -classpath out -p -s lesson.bytecode.StringProvider
~~~

Phần có ý nghĩa đã kiểm chứng:

~~~text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
~~~

Tại sao source chỉ khai báo một method `get()` nhưng output có **hai**? Vì interface `Provider<T>` sau erasure có method liên quan `Object get()`, còn implementation khai báo `String get()`. Compiler sinh một **bridge method** để lời gọi thông qua dạng binary của interface vẫn tới implementation phù hợp.

Dùng:

~~~sh
javap -classpath out -p -v lesson.bytecode.StringProvider
~~~

Với method `Object get()`, output đã kiểm chứng có:

~~~text
descriptor: ()Ljava/lang/Object;
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

`ACC_BRIDGE` xác định method là bridge; `ACC_SYNTHETIC` cho biết nó được compiler tạo và không trực tiếp tương ứng khai báo method nguồn thông thường.

Mô hình ý tưởng của bridge có thể xem như:

~~~java
// Mã minh họa khái niệm, KHÔNG phải Java source có thể tự khai báo
// đồng thời hai phương thức get() chỉ khác return type.
public Object get() {
    return get(); // chuyển đến phiên bản String get() theo binary descriptor
}
~~~

Không sao chép đoạn minh họa trên vào class thật: Java source **không cho phép** overload hai method chỉ khác return type; bridge tồn tại ở cấp class file, được compiler phát sinh theo quy tắc binary linkage. Muốn biết opcode thực tế của bridge, dùng `javap -p -c` trên class đã compile.

### 10.1. Vì sao bridge quan trọng khi kiểm tra API?

Khi nâng phiên bản thư viện, thay generic superclass/interface hoặc covariant return, bridge methods có thể ảnh hưởng **binary compatibility**. Nếu chỉ đọc source mà không xem class file, có thể không thấy method synthetic giúp consumer binary cũ còn gọi được đúng hành vi.

Cũng cần chú ý bytecode có thể chứa methods/fields synthetic khác, chẳng hạn do một số cấu trúc Java hoặc compiler transformation. Không gọi mọi method compiler sinh là “mã độc” hay “thừa”; phải đọc flags và vai trò của nó.

## 11. Dùng -v để xem class-file metadata

~~~sh
javap -classpath out -v lesson.bytecode.BytecodeSample
~~~

`-v` (verbose) cho nhiều thông tin hơn `-c`:

- Đường classfile, kích thước và metadata đọc được.
- Major/minor version, class access flags.
- Constant pool entries.
- Khai báo field/method cùng descriptor, flags và các attributes.
- Code, StackMapTable hoặc thông tin verification khi có.
- LineNumberTable/LocalVariableTable nếu class chứa debug info.
- Signature, SourceFile, InnerClasses, BootstrapMethods... khi có.

Phần header **đã kiểm chứng** cho target Java 17:

~~~text
minor version: 0
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
~~~

**Major 61 là Java 17.** Dù compiler tool hiện tại có thể là JDK 24, `javac --release 17` chọn format class file phù hợp với Java 17. Đây là một cách kiểm chứng đầu ra không bị nhầm với phiên bản javac đang chạy.

Với class file preview language/VM của một release, minor version có thể được đánh dấu đặc biệt (65535) theo đặc tả. Đừng mặc định mọi class compile với cờ preview đều có marker đó nếu thực tế class không dùng preview. Muốn phân tích preview nên đối chiếu đúng JDK và tính năng.

### 11.1. Constant pool references

Trong disassembly, đoạn:

~~~text
invokevirtual #34    // Method sum:(II)I
~~~

dẫn tới một entry trong constant pool. `#34` là **index của constant pool trong chính class file**, không phải số phương thức ổn định. Khi compiler tạo bytecode khác hoặc sắp xếp constant pool khác, index có thể đổi dù method đích về nghĩa vẫn là `sum(int,int)`.

Khi dùng `-v`, bạn có thể lần từ instruction tới constant-pool entry, rồi tới class name và NameAndType/descriptor tương ứng. Đây là cách kiểm tra một lỗi `NoSuchMethodError` hoặc một nghi vấn code đang gọi nhầm binary API.

### 11.2. Access flags

Javap hiển thị các cờ như:

- `ACC_PUBLIC`, `ACC_PRIVATE`, `ACC_PROTECTED`.
- `ACC_STATIC`, `ACC_FINAL`.
- `ACC_ABSTRACT`, `ACC_INTERFACE`.
- `ACC_BRIDGE`, `ACC_SYNTHETIC` trong những trường hợp phù hợp.

Chú ý **mã cờ class và method có ngữ cảnh khác nhau**; đừng suy luận máy móc chỉ từ số hex. `javap` đã diễn giải tên flag, thường dễ đọc hơn raw access_flags.

### 11.3. Những thuộc tính tùy loại class

Nếu compile record, sealed class, lambda, nestmates, generic signatures hoặc các module artifacts, `-v` có thể cho thấy attributes như `Record`, `PermittedSubclasses`, `NestHost`/`NestMembers`, `BootstrapMethods` hoặc `Module` tùy cấu trúc. Những attributes này không bắt buộc tồn tại trong mọi class. Đừng chờ chúng xuất hiện trên BytecodeSample nếu source không dùng tính năng tương ứng.

## 12. Đọc line number và local variables bằng -c -l

Nếu muốn biết bytecode map tới dòng source nào và local slots mang tên gì, biên dịch với thông tin debug:

~~~sh
javac --release 17 -g -d out src/lesson/bytecode/BytecodeSample.java src/lesson/bytecode/Provider.java src/lesson/bytecode/StringProvider.java
~~~

Sau đó chạy:

~~~sh
javap -classpath out -c -l lesson.bytecode.BytecodeSample
~~~

`-l` yêu cầu hiển thị line/local-variable tables **khi có**, và trong javap kiểm chứng cần kết hợp `-c` hoặc `-v` để hiển thị đúng bảng. Lệnh `javap -l` đơn lẻ trên JDK đã thử phát cảnh báo dạng:

~~~text
Warning: bad combination of options: -l without -c, line number and local variable tables will not be printed
~~~

Vì vậy, hướng dẫn thực hành dùng **`-c -l`**. Nếu bảng local variables không có, hãy kiểm tra bạn đã thực sự compile **`-g`** và đang đọc đúng output file. Các thông tin debug có thể bị công cụ tối ưu hóa/obfuscation loại bỏ ở artifact phát hành.

### 12.1. LocalVariableTable không định nghĩa logic của phương thức

`LocalVariableTable` có thể chứa tên `left`, `right`, slot, start/length range và descriptor cho biến cục bộ. Nó chủ yếu hỗ trợ debug/tooling; JVM không bắt buộc cần những tên biến nguồn đó để thực thi phương thức.

Ví dụ với method:

~~~java
public int sum(int left, int right) {
    int result = left + right;
    return result;
}
~~~

Nếu compile `-g`, bytecode có thể cho thấy:

~~~text
0: iload_1
1: iload_2
2: iadd
3: istore_3
4: iload_3
5: ireturn
~~~

Và LocalVariableTable có `left` slot 1, `right` slot 2, `result` slot 3. **Đoạn này là biến thể khác** so với method sum trong BytecodeSample gốc, vì ở đây có biến trung gian `result`. Nó đã được kiểm chứng bằng một class Example riêng. Đừng ghép nhầm kết quả của hai phiên bản nguồn rồi cho rằng javap mâu thuẫn.

### 12.2. SourceFile, LineNumberTable và LocalVariableTable khác nhau

| Attribute | Vai trò |
|---|---|
| `SourceFile` | Tên source file được gắn trong class |
| `LineNumberTable` | Ánh xạ các bytecode offsets tới source lines |
| `LocalVariableTable` | Tên, slot, range và descriptor của local variables |
| `LocalVariableTypeTable` | Có thể chứa generic signature của local variable khi phù hợp |
| `Signature` | Metadata generic cho class/member |

Có nguồn compile không kèm `-g` vẫn có thể có thông tin dòng ở mức mặc định, nhưng **đừng đảm bảo mọi debug table luôn tồn tại**. Compiler flags và công cụ xử lý class file quyết định metadata thực được giữ.

## 13. Phân biệt -s, -c, -v và -p

Bốn option giải quyết những câu hỏi khác nhau:

| Lệnh | Thông tin chính |
|---|---|
| `javap MyClass` | Khai báo dễ đọc theo Java |
| `javap -p MyClass` | Bao gồm thành viên private |
| `javap -s MyClass` | JVM descriptors |
| `javap -c MyClass` | Method bytecode disassembly |
| `javap -v MyClass` | Toàn bộ metadata chi tiết |
| `javap -p -s MyClass` | Toàn bộ member declarations và descriptors |
| `javap -p -c MyClass` | Bytecode cả private methods (nếu có Code) |
| `javap -c -l MyClass` | Instruction cùng line/local-variable tables khi có |
| `javap -constants MyClass` | Constant values được compiler ghi |
| `javap -sysinfo MyClass` | Thông tin artifact, size/checksum khi hỗ trợ |

Khi cần đối chiếu API binary, thường bắt đầu **`-p -s`**. Khi cần tìm hành vi đã compile, thêm **`-c`**. Chỉ bật **`-v`** khi cần đọc constant pool, flags, generic Signature, bootstrap hay metadata sâu, vì output khá dài và dễ bỏ qua điểm chính.

## 14. Dùng javap để kiểm tra JAR, module và dependency

### 14.1. Class từ JAR

Giả sử đã đóng gói các class vào JAR:

~~~sh
jar --create --file artifacts/sample.jar -C out .
javap -classpath artifacts/sample.jar -p -s lesson.bytecode.BytecodeSample
~~~

Tạo thư mục `artifacts` trước khi chạy lệnh. Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
~~~

Linux/macOS: `mkdir -p artifacts`.

Dùng `jar --list --file artifacts/sample.jar` để xác minh JAR có entry `lesson/bytecode/BytecodeSample.class`. Nếu javap báo class not found, thường do trỏ sai gốc classpath, sai binary name hoặc JAR thực tế không có class; đừng vội kết luận compiler không tạo class.

### 14.2. Class thuộc named module

Với JPMS, javap hỗ trợ các tùy chọn liên quan module như **`--module-path`**, **`--module`** hoặc **`-m`**, tùy cú pháp công cụ:

~~~sh
javap --module-path mods --module demo.library -p demo.library.api.Greeting
~~~

Đây là lệnh minh họa cho một project **có module demo.library thật** tại `mods`, không phải lệnh chạy trực tiếp với BytecodeSample (vì dự án mẫu không có module-info.java). Cần chỉ đúng module và class thuộc module ấy.

Đừng dùng classpath và module path thay thế lẫn nhau một cách máy móc. Nếu class nằm trong named module, hãy xác minh module path và việc module được tìm/resolved theo cơ chế của javap.

### 14.3. Kiểm tra đúng phiên bản thư viện trước khi chạy

Một ứng dụng được compile với method `greeting(String)` nhưng chạy với JAR không còn descriptor tương ứng có thể gặp `NoSuchMethodError`. Khi đó có thể so:

~~~sh
javap -classpath compile-libs/api.jar -p -s some.package.Library
javap -classpath runtime-libs/api.jar -p -s some.package.Library
~~~

Hai đường JAR và class name trong ví dụ trên là **placeholder** cần thay bằng artifact thật; mục tiêu là đối chiếu **tên binary, static/instance, params và return descriptor** của các bản API, không chỉ tên method nhìn từ source.

`javap` chỉ cho biết class file bạn đang đọc. Nó **không chứng minh** JVM sản phẩm đang nạp chính class file đó; cần kiểm tra runtime classpath/module path hoặc class loading logs khi xác minh bản thực sự được nạp.

## 15. Đọc bytecode mà không suy diễn quá mức

Có một số bẫy khi quan sát javap:

1. **Bytecode không phải source.** Compiler có thể biến đổi cấu trúc và sinh bridge/synthetic members.
2. **Một biểu thức Java không nhất thiết tương ứng một opcode.** Nối chuỗi có thể dùng invokedynamic, lời gọi có thể cần nhiều load/cast instructions.
3. **Không đồng nhất offset với line number.** Offset là vị trí bytecode trong Code attribute.
4. **Không coi constant pool index là ổn định.** `#13`, `#34` có thể đổi.
5. **Không suy thời gian chạy từ số instructions.** JVM có interpreter/JIT, optimization, inlining, GC và các đặc tính runtime khác.
6. **Không đoán generic types từ descriptor đơn thuần.** Đọc Signature khi cần.
7. **Không nghĩ synthetic/bridge là bug.** Chúng thường cần để giữ tương thích.
8. **Không cho rằng private members không tồn tại chỉ vì javap mặc định không in.** Dùng -p.
9. **Không kết luận JVM sẽ thực thi đúng tất cả nhánh chỉ vì javap đọc được class.** Bytecode vẫn có thể ném ngoại lệ/runtime linkage errors.
10. **Không xem output javap như hợp đồng format tuyệt đối giữa JDK.** Sử dụng assertions về semantics thay vì so toàn bộ text tùy phiên bản.

### 15.1. Trường hợp bất ngờ: source có annotation hoặc generic nhưng bytecode không giống source

Annotation có `RetentionPolicy.SOURCE` có thể không được ghi vào class file; javap -v không thấy nó ở runtime-visible annotations. Với generic return `List<String>`, descriptor lại là `Ljava/util/List;` nhưng Signature attribute có thể giữ type argument. Hai ví dụ này minh họa lý do cần hiểu **cách compiler lưu metadata**, không chỉ nhìn cú pháp nguồn.

### 15.2. Khi nào nên xem -v thay vì chỉ -c?

Dùng `-v` nếu muốn biết:

- Class target có phải Java 17 (major 61) không.
- Access flags của bridge method là gì.
- Runtime annotations hay generic signatures được lưu ở đâu.
- Method references dẫn tới constant pool entries nào.
- Bootstrap method cho invokedynamic là gì.
- Class có Record/PermittedSubclasses/NestMembers/Module attributes không.

Dùng `-c` nếu chỉ cần hiểu các opcode của một method và thứ tự stack operations. Dùng `-s` nếu chỉ kiểm tra binary descriptor, vì ít nhiễu hơn.

## 16. Quy trình kiểm chứng đầu ra có thể tái lập

Giả sử vừa sửa một method Java. Thay vì mở ngay bytecode rất dài, tiến hành có thứ tự:

**Bước 1 — Cố định JDK và nguồn.** Ghi `javac -version`; compile source đã xác nhận, target với `--release` phù hợp.

**Bước 2 — Dùng output riêng.** `javac -d out ...`, không trộn với bản `.class` từ build trước. Tránh vô tình đọc JAR cũ.

**Bước 3 — Kiểm tra class tồn tại.** Kiểm tra đường `out/package/Class.class` hoặc entry trong JAR.

**Bước 4 — Liệt kê API.** `javap -classpath out -p -s FullyQualifiedClass`; so declarations/descriptors với kỳ vọng.

**Bước 5 — Kiểm tra bytecode cần thiết.** `javap -classpath out -c FullyQualifiedClass`; tìm method/opcode và lời gọi quan trọng.

**Bước 6 — Xem metadata sâu nếu cần.** `javap -v` cho class version, constant pool, Signature, bridge/synthetic flags, BootstrapMethods.

**Bước 7 — Gắn với nguồn.** Compile -g nếu cần, dùng `javap -c -l`; so line/slot. Nhớ local names là debug info và có thể vắng.

**Bước 8 — Chạy thật.** `java -cp out FullyQualifiedClass` hoặc chạy bằng đúng launcher/module của dự án, so stdout/test cases. Javap không thay runtime validation.

**Bước 9 — Đối chiếu bản phân phối.** Nếu đóng gói JAR, kiểm tra lại chính JAR phát hành; một class trong thư mục out không đảm bảo class đó nằm trong artifact cuối.

**Bước 10 — Ghi nhận kết quả.** Lưu compiler target, artifact hash, signatures quan trọng và test output; không nên dựa vào constant pool indices có thể thay đổi.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `Error: class not found` | Sai classpath/binary name, class chưa compile | Xác minh `-d out` và cây package |
| Javap in API cũ | Đọc JAR/class file cũ | Chỉ rõ đường classpath và artifact, rebuild sạch output thuộc dự án |
| Không thấy private field | Dùng javap mặc định | Thêm -p |
| Không thấy descriptor | Chưa thêm -s | Dùng -p -s |
| Không thấy method body | Chưa thêm -c hoặc method không có Code | Dùng -c, hiểu abstract/native methods không có Code |
| Không thấy local variable name | Thiếu debug info hoặc chưa dùng đúng flags | Compile -g; dùng -c -l |
| `-l` riêng báo bad combination | Cần kết hợp disassembly/verbose | Dùng -c -l hoặc -v |
| Chữ ký generic khác descriptor | JVM dùng erasure | So thêm Signature attribute với -v |
| Có method Object get() lạ | Compiler tạo bridge | Xem ACC_BRIDGE, ACC_SYNTHETIC trong -v |
| Major version khác mong đợi | Compile target không đúng | Kiểm tra --release, javac -version, JAR thật |
| `NoSuchMethodError` khi chạy dù javap có method | Có thể đang xem khác binary/runtime artifact hoặc signature không khớp | So runtime class loading và descriptor |
| Bytecode khác khi đổi JDK | Compiler strategy/options thay đổi | So cùng target nhưng kiểm chứng semantic thay vì index tuyệt đối |

## 18. Bài tập tự luyện

**Bài 1 — Dự đoán descriptor.** Hãy viết descriptor cho `int[] values()`, `void log(String, long)`, và `String[][] find(boolean)`. Đáp án: `()[I`, `(Ljava/lang/String;J)V`, `(Z)[[Ljava/lang/String;`.

**Bài 2 — So quyền truy cập.** Chạy javap mặc định và javap -p trên BytecodeSample. Vì sao field `name` chỉ xuất hiện ở lần thứ hai?

**Bài 3 — Trace stack.** Dùng `javap -c` cho sum; mô tả stack sau iload_1, iload_2, iadd và ireturn. Thử sửa thành `left - right`, compile lại và tìm opcode tương ứng.

**Bài 4 — Generic erasure.** Với names(), vì sao descriptor trả List mà khai báo javap hiển thị List<String>? Tìm Signature trong -v.

**Bài 5 — Bridge.** Với StringProvider, tìm cả String get() và Object get(). Từ cờ ACC_BRIDGE/ACC_SYNTHETIC, giải thích vì sao source không có hai khai báo nhưng class file có.

**Bài 6 — invokedynamic.** Đọc bytecode greeting() và BootstrapMethods trong -v. Tìm thông tin StringConcatFactory. Giải thích tại sao không thể giả định mọi phép cộng chuỗi đều dùng cùng opcode trên mọi compiler.

**Bài 7 — Major version.** Biên dịch target Java 17, kiểm tra major 61. Sau đó biên dịch target khác mà JDK bạn hỗ trợ, quan sát version và thảo luận khả năng JVM cũ có đọc class mới không.

**Bài 8 — Debug info.** Compile một method có biến result bằng -g, xem -c -l. Compile lại khi tắt debug metadata và so LocalVariableTable; tại sao runtime vẫn có thể chạy đúng?

**Bài 9 — Artifact thực.** Đóng sample thành JAR, chạy javap từ JAR thay vì thư mục out. Nếu kết quả khác, hãy kiểm tra JAR có đóng đúng class mới nhất không.

**Bài 10 — Triệu chứng NoSuchMethodError.** Tạo hai phiên bản library có method cùng tên nhưng descriptors khác. Dùng javap -p -s so binary signatures, rồi giải thích vì sao class nhìn vẫn tồn tại nhưng JVM không tìm được method cũ.

## 19. Checklist nhanh khi dùng javap

- [ ] Đang đọc đúng class, package, JAR hoặc module?
- [ ] Biết rõ target của javac và major/minor trong class?
- [ ] Đã dùng -p nếu cần private members?
- [ ] Đã dùng -s để kiểm tra descriptors thay vì đoán từ source?
- [ ] Có phân biệt generic Signature với erased descriptor?
- [ ] Đã dùng -c và hiểu operand stack, local slots và offsets?
- [ ] Có dùng -v khi cần constant pool, flags, bootstrap hay synthetic members?
- [ ] Đã biên dịch -g và dùng -c -l nếu cần debug tables?
- [ ] Có nhớ output có thể khác theo compiler/options nhưng vẫn cùng semantics?
- [ ] Đã chạy ứng dụng/test và kiểm tra artifact thực tế được phân phối?

**Kết luận:** `javap` là công cụ xác minh **kết quả biên dịch ở cấp class file**. Đọc **khai báo** để kiểm tra API, **descriptor** để kiểm tra dạng nhị phân mà JVM liên kết, **bytecode** để hiểu instructions và luồng stack, và **verbose attributes** để phân tích generics, bridge/synthetic methods, invokedynamic hay version. Hiểu đủ các tầng này giúp bạn điều tra khác biệt giữa Java source, JAR đã phát hành và hành vi runtime thay vì đoán từ tên method.

## 20. Tài liệu tham khảo

- Oracle Java SE 17, `The javap Command`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle Java SE 17, `The javac Command`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- The Java Virtual Machine Specification, `Field Descriptors` và `Method Descriptors`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3
- The Java Virtual Machine Specification, `Class File Format` và `Attributes`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- The Java Virtual Machine Specification, `Instructions`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- The Java Language Specification, `Erasure`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6

Để tự kiểm chứng, hãy bắt đầu bằng mã nguồn và lệnh Java 17 ở phần 3; sau đó đối chiếu output `javap` theo từng tùy chọn thay vì chỉ đọc phần giải thích.
