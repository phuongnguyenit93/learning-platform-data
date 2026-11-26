# Constant pool, mô tả hằng và các tham chiếu ký hiệu trong bytecode

Constant pool là bảng dữ liệu trong mỗi Java class file. Bảng này lưu các giá trị hằng và thông tin ký hiệu mà bytecode cần dùng, chẳng hạn tên lớp, tên trường, tên phương thức, descriptor, chuỗi, số và các điểm liên kết động. Thay vì nhúng địa chỉ bộ nhớ hoặc bố cục đối tượng tại thời điểm biên dịch, bytecode tham chiếu tới các mục trong constant pool bằng chỉ số. JVM dùng các thông tin đó để nạp, phân giải và liên kết lớp, trường, phương thức hoặc call site khi cần.

Class-File API cung cấp mô hình Java có kiểu cho constant pool. API xuất hiện ở dạng preview trong JDK 22 qua JEP 457, preview lần thứ hai trong JDK 23 qua JEP 466 và trở thành API chính thức từ JDK 24 qua JEP 484. Trên JDK 24 trở lên, có thể dùng `java.lang.classfile` và `java.lang.classfile.constantpool` mà không cần bật preview. Bài này tập trung vào cấu trúc constant pool hiện hành và cách đọc các mục bằng API ổn định.

## 1. Constant pool nằm ở đâu trong class file?

Một class file có cấu trúc tổng quát gồm phần header, constant pool, thông tin truy cập và lớp cha, danh sách interface, field, method và attribute. Trong header, `constant_pool_count` cho biết giới hạn chỉ số của bảng. Các mục hợp lệ bắt đầu từ index 1; index 0 được dành riêng để biểu diễn trường hợp không có tham chiếu.

Mỗi mục constant pool bắt đầu bằng một byte `tag` cho biết loại mục, tiếp theo là dữ liệu có cấu trúc theo loại đó. Các mục có thể tham chiếu tới mục khác trong cùng bảng. Ví dụ, một tham chiếu phương thức kết hợp mục mô tả lớp sở hữu với mục chứa tên và descriptor của phương thức.

Một chi tiết của định dạng class file cần nhớ: `CONSTANT_Long` và `CONSTANT_Double` chiếm hai slot liên tiếp. Slot kế tiếp sau chúng không thể được dùng làm một mục độc lập. Vì vậy, chỉ số constant pool không phải số lượng mục có thể lặp liên tiếp mà không có khoảng trống; `PoolEntry.width()` của Class-File API cho biết một mục chiếm một hay hai slot.

## 2. Các nhóm mục constant pool hiện hành

Định dạng class file hiện hành định nghĩa 17 loại constant pool entry. Có thể chia chúng theo mục đích như sau:

| Nhóm | Loại entry | Ý nghĩa |
| --- | --- | --- |
| Văn bản và tên | `CONSTANT_Utf8` | Chuỗi Modified UTF-8 dùng cho tên, descriptor, chuỗi và dữ liệu văn bản trong class file. |
| Giá trị số | `CONSTANT_Integer`, `CONSTANT_Float`, `CONSTANT_Long`, `CONSTANT_Double` | Các giá trị số nguyên và số thực. `Long` và `Double` chiếm hai slot. |
| Kiểu và chuỗi | `CONSTANT_Class`, `CONSTANT_String` | Tham chiếu kiểu lớp/interface/array và string literal. |
| Mô tả thành viên | `CONSTANT_NameAndType` | Tên trường hoặc phương thức cùng descriptor của nó. |
| Tham chiếu thành viên | `CONSTANT_Fieldref`, `CONSTANT_Methodref`, `CONSTANT_InterfaceMethodref` | Tham chiếu ký hiệu tới trường, phương thức lớp hoặc phương thức interface. |
| Method handle và method type | `CONSTANT_MethodHandle`, `CONSTANT_MethodType` | Mô tả tham chiếu tới thành viên và kiểu chữ ký phương thức. |
| Liên kết động | `CONSTANT_Dynamic`, `CONSTANT_InvokeDynamic` | Hằng hoặc call site được tạo thông qua bootstrap method. |
| Module | `CONSTANT_Module`, `CONSTANT_Package` | Tên module và package trong class file có thông tin module. |

Các loại entry này đều còn xuất hiện trong class file Java hiện đại. Một số loại đã được bổ sung ở các phiên bản Java sau này: method handle, method type và invoke dynamic từ Java 7; module và package từ Java 9; dynamic constant từ Java 11. Khi đọc class file cũ, không phải loại entry nào cũng có thể xuất hiện vì mỗi loại chỉ hợp lệ từ phiên bản class file đã định nghĩa nó.

`CONSTANT_Utf8` dùng Modified UTF-8 theo đặc tả class file, không phải UTF-8 tiêu chuẩn mà ứng dụng thường dùng khi đọc file văn bản. Vì thế, khi phân tích class file nên để Class-File API giải mã mục này thay vì tự đọc byte và giả định encoding.

## 3. Giá trị hằng và mô tả kiểu

Không phải mọi mục trong constant pool đều là giá trị sẽ được đẩy trực tiếp lên operand stack. Một số mục là mô tả hoặc thành phần để JVM tìm một lớp hay thành viên. Có thể phân biệt ba trường hợp:

- **Giá trị có thể nạp:** số, chuỗi, class literal, method handle, method type và dynamic constant có thể được bytecode nạp để sử dụng.
- **Mô tả ký hiệu:** tên lớp, tên thành viên, descriptor và tham chiếu tới thành viên khác; chúng hỗ trợ JVM phân giải liên kết.
- **Thông tin bootstrap:** method handle và các đối số đi kèm trong `BootstrapMethods` dùng để tạo hằng hoặc call site động.

Ví dụ, câu lệnh Java:

```java
String label = "ready";
int retryLimit = 3;
long timeout = 30_000L;
```

có thể khiến compiler đưa các mục biểu diễn chuỗi và số vào constant pool. String literal được biểu diễn bằng `CONSTANT_String` trỏ tới `CONSTANT_Utf8`. Với số, compiler có thể dùng hằng nhúng trực tiếp trong instruction như `iconst_3`, `bipush` hoặc `sipush`, hoặc dùng mục số trong constant pool rồi nạp bằng `ldc`/`ldc_w`. `long` và `double` không có nhiều dạng hằng nhúng trực tiếp; ngoài `lconst_0`, `lconst_1`, `dconst_0` và `dconst_1`, các giá trị khác thường được nạp bằng `ldc2_w`.

Class literal như `String.class` cũng được biểu diễn bằng một `CONSTANT_Class` và có thể được nạp bằng `ldc`. `CONSTANT_Class` không chỉ dành cho class literal; nó còn được dùng làm kiểu tham chiếu trong các lệnh như `new`, `checkcast`, `instanceof` và trong tham chiếu thành viên.

## 4. Symbolic reference: lớp, thành viên, tên và descriptor

Một symbolic reference mô tả một thành viên theo danh tính của nó, không chứa địa chỉ trực tiếp tới vùng nhớ hoặc mã máy. Với tham chiếu thành viên, constant pool thường kết hợp hai thành phần:

```text
Fieldref / Methodref / InterfaceMethodref
    ├── ClassEntry: lớp hoặc interface sở hữu
    └── NameAndTypeEntry
          ├── Utf8Entry: tên thành viên
          └── Utf8Entry: descriptor
```

Ví dụ một tham chiếu phương thức có thể được hiểu như sau:

```text
java/io/PrintStream.println:(Ljava/lang/String;)V
```

Nó chỉ ra lớp sở hữu `java/io/PrintStream`, tên phương thức `println` và descriptor `(Ljava/lang/String;)V`. Descriptor cho biết phương thức nhận một `String` và trả về `void`. JVM dùng thông tin này trong quá trình resolution để tìm thành viên phù hợp theo quy tắc của JVM, access control và class loader.

### Descriptor của field và method

Descriptor là biểu diễn kiểu ở cấp class file. Một số ký hiệu thường gặp:

| Kiểu Java | Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `float` | `F` |
| `long` | `J` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

Descriptor của phương thức có dạng `(tham-số...)kiểu-trả-về`. Ví dụ:

```text
(Ljava/lang/String;I)Z
```

nghĩa là phương thức nhận `String` và `int`, trả về `boolean`. Với constructor, tên trong constant pool là `<init>` và descriptor vẫn mô tả tham số cùng kiểu trả về `V`.

### Ba loại tham chiếu thành viên

| Entry | Tham chiếu tới | Bytecode thường dùng |
| --- | --- | --- |
| `Fieldref` | Field của class hoặc kiểu được mô tả như class | `getfield`, `putfield`, `getstatic`, `putstatic` |
| `Methodref` | Method của class | `invokevirtual`, `invokestatic`, `invokespecial` theo quy tắc tương ứng |
| `InterfaceMethodref` | Method của interface | `invokeinterface`; một số dạng `invokestatic` hoặc `invokespecial` trên interface cũng có thể tham chiếu loại này |

Ví dụ `getstatic` không chứa tên trường dạng text trực tiếp. Operand của nó là chỉ số tới một `Fieldref`. Từ entry này, JVM xác định lớp sở hữu, tên field và descriptor, rồi thực hiện resolution. Tương tự, `invokevirtual` dùng symbolic reference tới method; lựa chọn implementation cuối cùng còn chịu cơ chế dynamic dispatch theo class thực tế của receiver.

## 5. MethodHandle, MethodType và liên kết động

`CONSTANT_MethodHandle` mô tả một handle tới field hoặc method. Nó chứa reference kind, cho biết cách truy cập hoặc gọi thành viên, cùng một tham chiếu tới `Fieldref`, `Methodref` hoặc `InterfaceMethodref` thích hợp. `CONSTANT_MethodType` lưu method descriptor và được biểu diễn trong API bằng `MethodTypeDesc`.

Hai loại entry này là nền tảng cho các cơ chế như `java.lang.invoke` và bootstrap method. Chúng cũng xuất hiện trong class file do compiler tạo ra cho lambda expression, method reference và các cấu trúc cần call site linh hoạt.

### CONSTANT_Dynamic và CONSTANT_InvokeDynamic

`CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic` không lưu sẵn giá trị cuối hoặc đích gọi cố định theo cách của hằng số thông thường. Chúng tham chiếu tới một bootstrap method trong attribute `BootstrapMethods` và một `NameAndType`:

- `CONSTANT_Dynamic` đại diện cho một hằng được tính khi JVM resolve entry, theo descriptor của field.
- `CONSTANT_InvokeDynamic` đại diện cho một call site được tạo khi JVM resolve entry, theo method descriptor.

Ví dụ, lambda expression thường được compiler biểu diễn bằng `invokedynamic` kết hợp với bootstrap method như `LambdaMetafactory`. String concatenation trong class file hiện đại cũng có thể dùng `invokedynamic` và bootstrap method tương ứng. Đây là chi tiết triển khai của compiler và class file, không nên dựa vào một chuỗi bytecode cố định để nhận diện mọi lambda hoặc phép nối chuỗi.

Với `CONSTANT_Dynamic`, lệnh `ldc` có thể kích hoạt quá trình resolve và đẩy giá trị đã được bootstrap tạo ra lên stack. Với `CONSTANT_InvokeDynamic`, lệnh `invokedynamic` dùng call site đã được bootstrap liên kết để thực hiện lời gọi. Vì vậy, khi đọc constant pool, cần xem thêm bảng bootstrap method để hiểu đầy đủ các tham chiếu động.

## 6. Đọc constant pool bằng Class-File API

Class-File API chính thức từ JDK 24 nằm trong module `java.base`, package `java.lang.classfile` và `java.lang.classfile.constantpool`. `ClassFile.parse(byte[])` phân tích byte array thành `ClassModel`; `ClassModel.constantPool()` cung cấp góc nhìn chỉ đọc về constant pool.

Ví dụ sau đọc một file `.class`, duyệt các entry và in ra các thông tin ký hiệu quan trọng:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.constantpool.ClassEntry;
import java.lang.classfile.constantpool.ConstantPool;
import java.lang.classfile.constantpool.MemberRefEntry;
import java.lang.classfile.constantpool.NameAndTypeEntry;
import java.lang.classfile.constantpool.PoolEntry;
import java.lang.classfile.constantpool.StringEntry;
import java.lang.classfile.constantpool.Utf8Entry;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConstantPoolInspector {
    public static void main(String[] args) throws IOException {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassModel classModel = ClassFile.of().parse(bytes);
        ConstantPool constantPool = classModel.constantPool();

        System.out.println("Class: " + classModel.thisClass().asInternalName());

        for (PoolEntry entry : constantPool) {
            String detail = describe(entry);
            System.out.printf("#%-4d tag=%-2d width=%d %s%n",
                    entry.index(), entry.tag(), entry.width(), detail);
        }
    }

    private static String describe(PoolEntry entry) {
        if (entry instanceof Utf8Entry utf8) {
            return "UTF8 " + utf8.stringValue();
        }
        if (entry instanceof StringEntry stringEntry) {
            return "STRING " + stringEntry.stringValue();
        }
        if (entry instanceof ClassEntry classEntry) {
            return "CLASS " + classEntry.asInternalName();
        }
        if (entry instanceof NameAndTypeEntry nameAndType) {
            return "NAME_AND_TYPE " + nameAndType.name().stringValue()
                    + " : " + nameAndType.type().stringValue();
        }
        if (entry instanceof MemberRefEntry memberRef) {
            return "MEMBER_REF " + memberRef.owner().asInternalName()
                    + "." + memberRef.name().stringValue()
                    + " : " + memberRef.type().stringValue();
        }
        return "tag=" + entry.tag();
    }
}
```

Chạy ví dụ trên JDK 24 trở lên với đường dẫn class file:

```bash
javac ConstantPoolInspector.java
java ConstantPoolInspector path/to/Example.class
```

`PoolEntry.index()` là chỉ số trong constant pool, `tag()` là tag theo định dạng class file và `width()` là số slot mà entry chiếm. `Utf8Entry.stringValue()` trả về nội dung đã giải mã. `ClassEntry.asInternalName()` trả về tên lớp ở dạng nội bộ, ví dụ `java/lang/String`. `MemberRefEntry` cho phép xem lớp sở hữu, tên thành viên và descriptor.

Constant pool được đọc theo kiểu lazy: nội dung entry chỉ được mở rộng khi cần. Vì vậy, lỗi dữ liệu class file không hợp lệ có thể xuất hiện khi truy cập một entry, không nhất thiết xuất hiện ngay lúc gọi `parse`. Khi chỉ cần so sánh văn bản, API có các phương thức như `Utf8Entry.equalsString(String)` để tránh chuyển đổi toàn bộ entry thành `String` không cần thiết.

### Truy cập theo index

Khi bytecode operand cung cấp một constant pool index, có thể dùng `entryByIndex` để lấy entry. Nếu biết trước loại entry mong đợi, overload có tham số `Class<T>` giúp kiểm tra kiểu:

```java
var pool = classModel.constantPool();
PoolEntry entry = pool.entryByIndex(12);

// Khi biết index 12 phải là tham chiếu method:
var methodRef = pool.entryByIndex(12,
        java.lang.classfile.constantpool.MethodRefEntry.class);
System.out.println(methodRef.owner().asInternalName());
System.out.println(methodRef.name().stringValue());
System.out.println(methodRef.type().stringValue());
```

Index `12` ở đây chỉ là ví dụ. Index thật phải lấy từ operand của bytecode hoặc từ entry đã đọc. Index 0, index ngoài giới hạn hoặc slot không sử dụng sau `LongEntry`/`DoubleEntry` sẽ không hợp lệ. Không nên giả định một index luôn chỉ cùng entry giữa hai lần biên dịch khác nhau.

## 7. Tạo và biến đổi constant pool bằng API

Khi tạo class file, phần lớn trường hợp không cần tự thêm từng entry hoặc tự tính chỉ số. Các builder của Class-File API nhận thông tin ký hiệu như `ClassDesc`, `MethodTypeDesc`, tên và descriptor; `ConstantPoolBuilder` tự tạo hoặc tái sử dụng entry phù hợp.

`ConstantPoolBuilder` cung cấp quyền đọc và ghi cho constant pool đang xây dựng. Việc thêm entry là append-only và idempotent: index mới tăng dần, còn lời gọi tạo một entry tương đương có thể trả lại entry đã có. Khi transform một class file, API cũng có cơ chế chia sẻ constant pool từ class gốc để tái sử dụng dữ liệu và giảm việc sao chép không cần thiết.

Nên ưu tiên các factory method nhận thông tin ký hiệu đã có kiểu thay vì tự ghép `Utf8Entry`, `ClassEntry` và `NameAndTypeEntry` bằng tay. Cách này giúp API kiểm tra kiểu và descriptor, đồng thời tránh lỗi do tham chiếu nhầm index. Chỉ làm việc trực tiếp với entry cấp thấp khi cần đọc phân tích class file hoặc khi thật sự cần kiểm soát cấu trúc constant pool.

Một nguyên tắc quan trọng khi transform là không coi chỉ số constant pool là định danh bền vững. Builder có thể thêm, tái sử dụng hoặc chuyển đổi entry tương đương; class file được sinh ra có thể có index khác với đầu vào nhưng vẫn giữ ngữ nghĩa. Hãy tham chiếu entry thông qua object API hoặc descriptor ký hiệu, không hard-code index trong logic ứng dụng.

## 8. Những điểm cần cẩn trọng khi phân tích bytecode

1. **Không nhầm UTF-8 với string literal.** `Utf8Entry` có thể là tên lớp, tên field, descriptor, attribute text hoặc nội dung phục vụ một `StringEntry`; không phải mọi UTF8 entry đều là chuỗi Java được nạp ở runtime.
2. **Không nhầm symbolic reference với object reference.** `Fieldref` và `Methodref` mô tả thành viên cần phân giải; chúng không chứa địa chỉ instance hoặc địa chỉ mã native.
3. **Không giả định index liên tiếp.** `Long` và `Double` chiếm hai slot; index kế tiếp bị bỏ trống. Index 0 cũng không hợp lệ.
4. **Đọc descriptor cùng owner.** Tên `get` hoặc `valueOf` không đủ xác định method; cần cả lớp sở hữu và method descriptor.
5. **Theo dõi bootstrap method khi gặp dynamic entry.** `Dynamic` và `InvokeDynamic` không thể hiểu đầy đủ chỉ bằng `NameAndType`; cần xem bootstrap method table và arguments.
6. **Không giả định thứ tự hoặc index ổn định sau transform.** Hãy dùng Class-File API và các entry có kiểu thay vì thao tác byte offset thủ công khi không có lý do đặc biệt.
7. **Xử lý class file không tin cậy cẩn thận.** Việc parse có thể phát hiện lỗi cấu trúc theo từng bước lazy access. Công cụ phân tích nên xử lý exception và giới hạn tài nguyên khi đọc file đầu vào không rõ nguồn gốc.

Constant pool là lớp liên kết giữa bytecode và các thực thể Java được mô tả bằng tên cùng descriptor. Nắm được cấu trúc entry và quan hệ symbolic reference giúp đọc bytecode, phân tích dependency, xây dựng công cụ kiểm tra hoặc transform class file. Với ứng dụng hiện đại, Class-File API từ JDK 24 trở lên là cách tiếp cận có kiểu và an toàn hơn so với tự phân tích từng byte của class file.

## Tài liệu tham khảo

- [JEP 457: Class-File API (Preview)](https://openjdk.org/jeps/457) — lần preview đầu tiên trong JDK 22.
- [JEP 466: Class-File API (Second Preview)](https://openjdk.org/jeps/466) — lần preview thứ hai trong JDK 23.
- [JEP 484: Class-File API](https://openjdk.org/jeps/484) — hoàn thiện API trong JDK 24.
- [Class-File API, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/package-summary.html) — mô hình parse, build và transform class file.
- [ConstantPool, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/constantpool/ConstantPool.html) — đọc constant pool theo index.
- [PoolEntry, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/constantpool/PoolEntry.html) — tag, index và width của entry.
- [Constant pool package, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/constantpool/package-summary.html) — các kiểu entry và cách đọc/ghi constant pool.
- [JVM Specification, Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html) — định dạng constant pool và các cấu trúc class file.
