# Cấu trúc ClassFile tối thiểu cần biết

**ClassFile** là cấu trúc nhị phân chuẩn dùng để biểu diễn định nghĩa một class hoặc interface cho Java Virtual Machine (JVM). Khi biên dịch mã Java, trình biên dịch thường tạo tệp có đuôi `.class`; class loader có thể cung cấp những byte tương ứng để JVM nạp, kiểm tra, liên kết rồi sử dụng định nghĩa kiểu.

Muốn hiểu class loader tìm và định nghĩa lớp như thế nào, cần biết trong một ClassFile có những gì: **phiên bản**, **constant pool**, **thông tin định danh và quan hệ kiểu**, **trường**, **phương thức** và **thuộc tính**. Không cần tự viết một JVM hay học thuộc toàn bộ opcode để đọc cấu trúc ở mức nền tảng.

> **Phân biệt:** “ClassFile” là định dạng dữ liệu do đặc tả JVM quy định. “Tệp `.class`” là một cách lưu dữ liệu định dạng ấy. Bytecode cũng có thể được cung cấp từ JAR, bộ nhớ hoặc nguồn khác; không bắt buộc JVM phải đọc một tệp rời có sẵn trên đĩa.

## 1. Nhìn tổng thể: ClassFile chứa gì?

Đặc tả JVM mô tả cấu trúc cơ bản như sau (ký pháp mô tả định dạng, **không phải code Java để chạy**):

~~~text
ClassFile {
    u4             magic;
    u2             minor_version;
    u2             major_version;
    u2             constant_pool_count;
    cp_info        constant_pool[constant_pool_count - 1];
    u2             access_flags;
    u2             this_class;
    u2             super_class;
    u2             interfaces_count;
    u2             interfaces[interfaces_count];
    u2             fields_count;
    field_info     fields[fields_count];
    u2             methods_count;
    method_info    methods[methods_count];
    u2             attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Các phần xuất hiện **đúng theo thứ tự trên** trong luồng byte của ClassFile. Một số phần có độ dài cố định, còn constant pool, danh sách interfaces/fields/methods và attributes có độ dài phụ thuộc dữ liệu.

| Thành phần | Ý nghĩa cốt lõi |
| --- | --- |
| `magic` | Dấu hiệu nhận biết định dạng ClassFile. |
| `minor_version`, `major_version` | Phiên bản định dạng bytecode mà JVM phải hỗ trợ. |
| `constant_pool_count`, `constant_pool` | Bảng chứa tên, descriptor, chuỗi/hằng và tham chiếu ký hiệu tới lớp, trường, phương thức. |
| `access_flags` | Cờ mô tả loại/thuộc tính của kiểu: class, interface, public, abstract, final… |
| `this_class` | Chỉ mục trỏ vào constant pool để chỉ ra tên nhị phân của kiểu hiện tại. |
| `super_class` | Chỉ mục chỉ superclass trực tiếp khi có; có trường hợp bằng 0. |
| `interfaces_count`, `interfaces` | Danh sách interface trực tiếp được lớp implements hoặc interface extends. |
| `fields_count`, `fields` | Metadata của các trường được khai báo trong chính kiểu. |
| `methods_count`, `methods` | Metadata của các phương thức được khai báo trong chính kiểu, gồm constructor/method khởi tạo tĩnh khi hiện diện. |
| `attributes_count`, `attributes` | Metadata mở rộng ở mức ClassFile như thông tin nguồn, record, nestmate, sealed class… |

**Điểm dễ nhầm:** Bảng trên chỉ trình bày các thành phần cấp cao nhất. Một `field_info`, `method_info` hay `Code` cũng có các thuộc tính con, chứ không phải tất cả đều nằm trực tiếp trong `ClassFile.attributes`.

### Kiểu `u1`, `u2`, `u4` là gì?

Đây là **số nguyên không dấu** dùng trong đặc tả cấu trúc nhị phân:

- `u1`: 1 byte, từ 0 đến 255.
- `u2`: 2 byte, từ 0 đến 65.535.
- `u4`: 4 byte, từ 0 đến 4.294.967.295.

Các đại lượng nhiều byte được lưu theo thứ tự **big-endian** (byte có trọng số lớn nhất trước). Ví dụ, `CA FE BA BE` là bốn byte nối tiếp, không phải chuỗi ký tự “CAFEBABE” lưu theo UTF-8.

## 2. Phần đầu file: Magic number và phiên bản

Bốn byte đầu tiên có giá trị cố định:

~~~text
Offset (hex)  Byte                 Giải thích
0x00          CA FE BA BE          magic = 0xCAFEBABE
0x04          00 00                minor_version = 0
0x06          00 3D                major_version = 61 (ví dụ class target Java 17)
0x08          ...                  constant_pool_count, rồi constant_pool
~~~

Hai cặp `00 00` và `00 3D` là ví dụ điển hình khi biên dịch với **`javac --release 17`** bằng bản JDK hỗ trợ tùy chọn đó; không phải mọi tệp ClassFile đều có cùng phiên bản.

Một vài phiên bản phổ biến:

| Mục tiêu bytecode | `major_version` |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Các bản Java thường tăng major version khi phát hành. JVM không hỗ trợ major version của ClassFile có thể ném **`UnsupportedClassVersionError`** lúc nạp. Ví dụ, JVM chỉ hỗ trợ đến Java 17 sẽ không nạp được một class thực sự được biên dịch target Java 21 (major 65).

**Lưu ý:** Phiên bản ClassFile phản ánh **mục tiêu biên dịch**, không nhất thiết bản JDK mà người lập trình đã dùng để chạy `javac`. Khi xây dựng thư viện cho JVM cũ, `javac --release N` còn giới hạn API theo release đích, phù hợp hơn việc suy diễn chỉ từ tên tệp hoặc môi trường máy lập trình.

## 3. Constant pool: bảng liên kết bằng chỉ mục

**Constant pool** là phần trung tâm của ClassFile: nhiều vị trí trong file lưu một **chỉ mục** trỏ tới một mục ở bảng này thay vì lặp lại toàn bộ tên hoặc tham chiếu. Vì thế, cần hiểu nó như một bảng có kiểu bản ghi khác nhau; chữ “constant” không có nghĩa bảng chỉ chứa số hay chuỗi hằng.

Những loại mục thường gặp:

| Tag / loại mục | Dùng để biểu diễn |
| --- | --- |
| `CONSTANT_Utf8` | Chuỗi dùng cho tên, descriptor và văn bản metadata (mã hóa theo **modified UTF-8** của class file). |
| `CONSTANT_Class` | Tham chiếu tên kiểu, thường đi qua một mục `Utf8`. |
| `CONSTANT_NameAndType` | Cặp tên + descriptor của một trường/phương thức. |
| `CONSTANT_Fieldref` | Tham chiếu ký hiệu tới trường được khai báo trên một lớp/interface thích hợp. |
| `CONSTANT_Methodref` / `CONSTANT_InterfaceMethodref` | Tham chiếu ký hiệu tới phương thức. |
| `CONSTANT_String` | Hằng chuỗi dựa vào mục `Utf8`. |
| `CONSTANT_Integer`, `Float`, `Long`, `Double` | Giá trị số được mã hóa trong ClassFile. |
| `CONSTANT_MethodHandle`, `MethodType`, `InvokeDynamic`, `Dynamic` | Hỗ trợ method handle, lời gọi động và hằng động. |
| `CONSTANT_Module`, `Package` | Metadata module/package trong ClassFile phù hợp. |

Ví dụ với lời gọi `System.out.println(...)`, constant pool có thể chứa chuỗi/tham chiếu ký hiệu phục vụ việc tìm `java/lang/System`, trường `out`, kiểu `java/io/PrintStream` và phương thức `println`. **Các chỉ mục `#1`, `#2`… do trình biên dịch tạo và có thể khác nhau giữa các lần biên dịch/công cụ**; không nên học thuộc số thứ tự từ một bản `javap`.

### Quy tắc đánh chỉ mục dễ sai

- `constant_pool_count` là số **lớn hơn chỉ mục hợp lệ lớn nhất một đơn vị**; mục 0 không phải một `cp_info` bình thường có thể truy cập.
- Phần lớn mục chiếm một chỉ mục. `CONSTANT_Long` và `CONSTANT_Double` chiếm **hai vị trí chỉ mục liên tiếp**, nhưng vị trí thứ hai **không chứa một `cp_info` độc lập**. Vì vậy, không thể lặp đơn giản `count - 1` lần đọc bản ghi rồi cho rằng offset đúng với mọi ClassFile.
- Một bản ghi tham chiếu tên/kiểu thường chứa **chỉ mục trỏ tới bản ghi khác**, không nhúng nguyên văn tên ngay trong bản ghi tham chiếu.
- Constant pool không phải bảng object Java đã được khởi tạo. Các tham chiếu ký hiệu được JVM **resolve** theo quy tắc linking khi cần; nhiều mục vẫn chỉ là dữ liệu biểu diễn ký hiệu trong ClassFile.

Ví dụ chuỗi `"Hello"` trong mã nguồn có thể dẫn đến mục `CONSTANT_String` tham chiếu `CONSTANT_Utf8` chứa ký tự `Hello`. Nhưng string literal, field descriptor và generic metadata không phải cùng một thứ chỉ vì chúng đều xuất hiện trong constant pool.

## 4. Metadata nhận diện kiểu và quan hệ kế thừa

Sau constant pool là:

~~~text
access_flags
this_class
super_class
interfaces_count
interfaces[]
~~~

**`access_flags`** là tập cờ bit. Ở lớp thông thường, có thể gặp `ACC_PUBLIC`, `ACC_FINAL`, `ACC_SUPER`, `ACC_ABSTRACT`; interface có `ACC_INTERFACE` cùng những cờ phù hợp khác. `ACC_SUPER` là cờ có ý nghĩa lịch sử/liên quan ngữ nghĩa gọi phương thức; **không phải** “đường dẫn đến superclass”.

**`this_class`** trỏ tới một `CONSTANT_Class` trong constant pool, từ đó lấy **tên nội bộ** của lớp, ví dụ `com/example/Task`. Khi viết Java ta thường dùng tên nhị phân `com.example.Task`. Dấu `/` trong tên nội bộ khác dấu `.` trong code Java.

**`super_class`** thông thường trỏ đến `CONSTANT_Class` của lớp cha trực tiếp, kể cả `java/lang/Object` khi lớp không khai báo `extends`. Với chính `java/lang/Object`, giá trị là 0; ClassFile module (`ACC_MODULE`) cũng có ràng buộc đặc biệt đối với trường này.

**`interfaces`** chứa các chỉ mục `CONSTANT_Class` mô tả interface được khai báo trực tiếp. Đây không phải danh sách đệ quy tất cả interface mà kiểu nhận từ cha.

Ví dụ, đoạn Java:

~~~java
interface Runner {
    void run();
}

class Job implements Runner {
    @Override
    public void run() {}
}
~~~

sẽ dẫn đến các ClassFile riêng cho `Runner` và `Job`. Ở định nghĩa `Job`, metadata sẽ chỉ ra tên `Job`, superclass trực tiếp `java/lang/Object`, và interface trực tiếp `Runner`. Các tên nằm trong constant pool của **ClassFile tương ứng**, không phải một constant pool dùng chung cho mọi lớp trong cùng JAR.

## 5. Fields: lưu cấu trúc trường, không lưu sẵn object instance

Một phần tử `field_info` có cấu trúc khái quát:

~~~text
field_info {
    u2             access_flags;
    u2             name_index;
    u2             descriptor_index;
    u2             attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Ví dụ khai báo:

~~~java
private int count;
private static final int LIMIT = 10;
~~~

Metadata trường có tên `count`, `LIMIT`, cờ quyền truy cập, cờ `static`/`final` tương ứng và **descriptor**:

- `I` là `int`; `Z` là `boolean`; `J` là `long`; `D` là `double`.
- `Ljava/lang/String;` là tham chiếu tới `java.lang.String`.
- `[I` là mảng `int[]`; `[Ljava/lang/String;` là `String[]`.

Trường hằng phù hợp có thể có thuộc tính `ConstantValue`, chẳng hạn `static final int LIMIT = 10`. Điều này **không** có nghĩa mọi phép gán field được ghi thành byte dữ liệu object trong ClassFile. Giá trị của trường instance thuộc về **đối tượng khi chạy**; các bước khởi tạo và phép gán không hằng có thể được thực thi bằng bytecode.

Ngoài ra, **descriptor** là mô tả kiểu JVM dùng khi liên kết. Kiểu generic như `List<String>` không có dạng generic đầy đủ trong field descriptor; metadata generic nếu cần có thể nằm ở thuộc tính `Signature`. Vì vậy, trình xem ClassFile thường có cả descriptor kiểu xóa (`erasure`) và thuộc tính bổ sung.

## 6. Methods: tên, descriptor và bytecode thực thi

Một `method_info` cũng chứa `access_flags`, `name_index`, `descriptor_index` và tập thuộc tính. Những tên đặc biệt cần nhận ra:

- `<init>`: phương thức khởi tạo instance do JVM gọi khi thực hiện quá trình tạo instance; đây là tên đặc biệt ở mức ClassFile cho constructor.
- `<clinit>`: phương thức khởi tạo lớp/interface (nếu được sinh ra) chứa logic khởi tạo tĩnh cần thực thi.
- Những method thông thường: ví dụ `sum`, `main`, `run`.

Một **method descriptor** có dạng `(tham_số)kiểu_trả_về`:

| Khai báo Java | Descriptor JVM |
| --- | --- |
| `int sum(int value)` | `(I)I` |
| `void say(String text)` | `(Ljava/lang/String;)V` |
| `static void main(String[] args)` | `([Ljava/lang/String;)V` |
| `long total(int[] numbers, boolean active)` | `([IZ)J` |

Ký hiệu `V` biểu thị `void`. Descriptor ghi **kiểu tham số và kiểu trả về**, không ghi tên biến; generic type arguments không có trong descriptor thông thường.

### Thuộc tính `Code`: bytecode nằm ở đâu?

Phương thức Java có phần thân bytecode trong ClassFile thông thường dùng một thuộc tính **`Code`** nằm bên trong `method_info.attributes`. Cấu trúc rút gọn:

~~~text
method_info
  ├── access_flags / name_index / descriptor_index
  └── attributes[]
       └── Code
            ├── max_stack
            ├── max_locals
            ├── code_length + code[]      ← các opcode và operand
            ├── exception_table[]         ← vùng xử lý ngoại lệ
            └── attributes[]              ← ví dụ LineNumberTable, StackMapTable
~~~

- `max_stack`: độ sâu tối đa của **operand stack** cần thiết để thực thi method.
- `max_locals`: số slot tối đa của **local variables** dành cho method; `long`/`double` chiếm hai slot.
- `code[]`: dãy bytecode instruction và operand; ví dụ `iload`, `iadd`, `ireturn`, `invokevirtual`.
- `exception_table[]`: bảng ánh xạ vùng code và handler, dùng cả cho cấu trúc `try`/`catch`/`finally` sau biên dịch.
- Thuộc tính con giúp kiểm tra kiểu và debug, tùy trình biên dịch/tùy chọn biên dịch.

**Không phải method nào cũng có `Code`.** Method `abstract` hoặc `native` không có thân bytecode trong ClassFile theo cách này. Constructor và static initializer được biên dịch thành method có code khi tương ứng hiện diện.

## 7. Attributes: cơ chế mở rộng định dạng

`attribute_info` có dạng chung:

~~~text
attribute_info {
    u2 attribute_name_index;  // trỏ đến Utf8 trong constant pool
    u4 attribute_length;      // số byte dữ liệu của attribute
    u1 info[attribute_length];
}
~~~

**Tên attribute** được tra trong constant pool. Mỗi loại attribute lại định nghĩa cấu trúc riêng của `info[]`. Vì vậy, trình đọc ClassFile cần dựa vào tên và độ dài để giải mã; không được giả định mọi attribute đều chứa bytecode.

Các attribute có ý nghĩa học tập:

| Attribute | Vị trí thường gặp | Vai trò |
| --- | --- | --- |
| `Code` | Method | Bytecode, stack/locals, exception handlers và attribute lồng nhau. |
| `ConstantValue` | Field | Giá trị hằng của trường tĩnh phù hợp. |
| `Exceptions` | Method | Danh sách loại exception được khai báo trong `throws` (khác exception table xử lý tại runtime). |
| `SourceFile` | Class | Tên tệp nguồn để hỗ trợ công cụ. |
| `LineNumberTable`, `LocalVariableTable` | Bên trong `Code` | Metadata debug, có thể bị lược bỏ. |
| `StackMapTable` | Bên trong `Code` | Frame phục vụ kiểm tra type của bytecode theo quy tắc JVM. |
| `Signature` | Class/Field/Method | Metadata kiểu generic khi cần, bổ sung cho descriptor. |
| `RuntimeVisibleAnnotations` | Nhiều vị trí hợp lệ | Annotation có khả năng truy cập tại runtime theo quy tắc retention. |
| `BootstrapMethods` | Class | Dữ liệu bootstrap phục vụ `invokedynamic` và dynamic constants. |
| `Record`, `PermittedSubclasses` | Class | Metadata record và sealed hierarchy khi áp dụng. |

Cấu trúc ClassFile phát triển qua các phiên bản JVM; **không phải tệp nào cũng có tất cả attribute**. Một số attribute đặc biệt chỉ hợp lệ tại vị trí nhất định hoặc với phiên bản ClassFile tương ứng. Java reflection cũng không phơi bày nguyên vẹn mọi byte trong ClassFile.

## 8. Thực hành Java 17+: biên dịch và đọc bằng `javap`

Tạo tệp **`ClassFileLayout.java`**:

~~~java
public class ClassFileLayout {
    private static final int BASE = 7;
    private int total;

    public int sum(int amount) {
        total += amount + BASE;
        return total;
    }

    public static void main(String[] args) {
        ClassFileLayout example = new ClassFileLayout();
        System.out.println(example.sum(5));
    }
}
~~~

Dùng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ClassFileLayout.java
java ClassFileLayout
javap -v -p ClassFileLayout
~~~

Đầu ra của lệnh `java ClassFileLayout` **chính xác** là:

~~~text
12
~~~

Lệnh `javap -v -p` in nhiều thông tin phụ thuộc trình biên dịch/công cụ, vì vậy thay vì giả định mọi chỉ mục `#...` giống nhau, hãy **tìm các thành phần sau** trong output:

1. **Header** với `major version: 61` do đã dùng `--release 17`; tên class `ClassFileLayout` và superclass `java/lang/Object`.
2. **Constant pool** gồm tên class, tên trường, tên method, descriptor và tham chiếu cần thiết cho `System.out.println`, constructor… Các mục có thứ tự/đánh số do công cụ quyết định.
3. **Fields** của `BASE` và `total`. `BASE` có descriptor `I`, cờ `ACC_PRIVATE`, `ACC_STATIC`, `ACC_FINAL` và có thể xem `ConstantValue: int 7`.
4. **Methods** bao gồm constructor `<init>`, `sum` với descriptor `(I)I`, và `main` với `([Ljava/lang/String;)V`.
5. **Code** của `sum`: tải trạng thái/đối số, tính `amount + BASE`, ghi lại `total` rồi trả số nguyên. Do `BASE` là compile-time constant, bytecode có thể dùng trực tiếp giá trị `7`; không cần luôn đọc trường `BASE` bằng `getstatic`.
6. **Attributes**: các mục như `Code`, `LineNumberTable` hoặc `SourceFile` có thể xuất hiện theo tùy chọn biên dịch.

Nếu chỉ muốn xem bytecode từng method cho dễ đọc, chạy thêm:

~~~bash
javap -c -p ClassFileLayout
~~~

Lưu ý: `javap` là **công cụ giải mã và trình bày**, không phải JVM đang thực thi các opcode vừa in ra. Định dạng hiển thị (comment, chỉ mục, offset và chi tiết metadata) có thể thay đổi giữa công cụ/JDK.

### Đọc 10 byte đầu bằng Java (tùy chọn)

Nếu muốn tự xác nhận header bằng API chuẩn, tạo tệp **`ClassFileHeader.java`** trong cùng thư mục:

~~~java
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.IOException;

public class ClassFileHeader {
    public static void main(String[] args) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new FileInputStream("ClassFileLayout.class"))) {
            int magic = in.readInt();
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            int poolCount = in.readUnsignedShort();

            System.out.printf("Magic: %08X%n", magic);
            System.out.println("Minor: " + minor);
            System.out.println("Major: " + major);
            System.out.println("Constant pool count: " + poolCount);
        }
    }
}
~~~

Chạy sau khi đã có `ClassFileLayout.class`:

~~~bash
javac --release 17 ClassFileHeader.java
java ClassFileHeader
~~~

**Ba dòng đầu** được xác định khi target là Java 17 và bytecode không dùng chế độ preview:

~~~text
Magic: CAFEBABE
Minor: 0
Major: 61
~~~

Chương trình còn in `Constant pool count: <một số nguyên dương>`; không cố định số này vì có thể khác nhau giữa các trình biên dịch. `DataInputStream` đọc dữ liệu nhiều byte theo big-endian, phù hợp cấu trúc header ClassFile. Đoạn này mới chỉ minh họa việc **đọc header**, chưa xác minh mọi tag, độ dài và chỉ mục trong file.

## 9. ClassFile liên hệ với class loader như thế nào?

Một luồng xử lý khái quát:

~~~text
.java --javac--> bytecode có cấu trúc ClassFile
                       │
                 tệp .class / JAR
                 hoặc bytecode từ nguồn khác
                       │
                       ▼
               class loader cung cấp byte
                       │
                       ▼
                 JVM định nghĩa class
                       │
                  verification
                preparation/resolution
                       │
                initialization khi cần
                       ▼
                    Sử dụng kiểu
~~~

Class loader giúp JVM **tìm dữ liệu để định nghĩa lớp**; còn JVM chịu trách nhiệm diễn giải đúng định dạng ClassFile, kiểm tra tính hợp lệ, liên kết và thực hiện khởi tạo theo các quy tắc của nó. Mức độ thực hiện sớm hay muộn của một số bước có thể khác nhau giữa JVM miễn giữ đúng ngữ nghĩa bắt buộc.

- `ClassNotFoundException`: thường xuất hiện khi mã gọi API tìm lớp theo tên nhưng loader không tìm được.
- `ClassFormatError`: dữ liệu biểu diễn class sai định dạng mà JVM yêu cầu.
- `UnsupportedClassVersionError`: major/minor version không được JVM đang dùng hỗ trợ.
- `VerifyError`: bytecode không đáp ứng quy tắc kiểm tra kiểu/cấu trúc tại giai đoạn verification.
- `NoClassDefFoundError`: việc JVM cần một định nghĩa lớp đã tham chiếu không thành công, có thể do thiếu dependency hoặc lớp đã khởi tạo thất bại trước đó.

Đọc **cause** và pha lỗi thực tế giúp phân biệt không tìm thấy tệp/JAR với định dạng ClassFile sai hoặc bytecode không hợp lệ.

## 10. Các hiểu nhầm phổ biến

**“ClassFile chỉ là danh sách opcode.”** Sai. Opcode nằm trong thuộc tính `Code` của method phù hợp. ClassFile còn có version, constant pool, metadata kiểu, fields, methods và nhiều attributes khác.

**“Constant pool là vùng chứa mọi giá trị runtime của chương trình.”** Sai. Đây là bảng biểu diễn ký hiệu/hằng trong định dạng class; dữ liệu instance và trạng thái thực thi không được lưu nguyên vẹn tại đây.

**“Đọc `major_version` là biết ứng dụng chạy được trên JVM ấy.”** Chưa đủ. Major version hợp lệ là điều kiện cần để nạp một class, nhưng bytecode vẫn có thể sai, dependency không có, API không tương thích, hoặc module/access không cho phép hoạt động mong muốn.

**“Một file ClassFile chứa tất cả class lồng và các lớp được tham chiếu.”** Sai. Class/interface thường có định nghĩa ClassFile riêng; class lồng xuất hiện dưới tên như `Outer$Inner`, và quan hệ giữa chúng có thể có metadata bổ sung. Tham chiếu tới lớp khác trong constant pool **không nhúng** bytecode của lớp ấy vào ClassFile đang xét.

**“Mọi method đều có `Code` và mọi attribute đều là debug.”** Sai. Method abstract/native không có Code theo cách bình thường; nhiều attribute mang ý nghĩa JVM như `StackMapTable`, `BootstrapMethods`, `NestHost` hoặc `PermittedSubclasses`.

**“Thứ tự các mục constant pool và bytecode luôn giống nhau nếu source giống nhau.”** Sai. Các bản trình biên dịch và cấu hình build có thể sinh biểu diễn khác mà vẫn tuân thủ đặc tả và giữ cùng hành vi cần thiết.

## 11. Tự kiểm tra

1. **Bốn byte đầu của ClassFile là gì?** — `CA FE BA BE`, tức magic `0xCAFEBABE`.
2. **Java 17 target thông thường có major version bao nhiêu?** — `61`.
3. **Vì sao `constant_pool_count` không nhất thiết bằng số mục cp_info được lưu cộng 1 theo cách đếm đơn giản?** — Vì các mục `Long`/`Double` chiếm hai slot chỉ mục và slot thứ hai không chứa cp_info độc lập.
4. **Một method `int sum(int x)` có descriptor nào?** — `(I)I`; tên tham số `x` không nằm trong descriptor.
5. **Bytecode của method ở đâu?** — Trong `Code` attribute thuộc `method_info` khi method có code; không phải ở `ClassFile.attributes` chung.
6. **Làm sao xem phiên bản ClassFile, constant pool và metadata bằng công cụ chuẩn?** — Biên dịch `javac --release 17`, rồi dùng `javap -v -p TenLop`.

## Ghi nhớ

Một **ClassFile** có phần đầu `CAFEBABE + version`, theo sau là **constant pool**, **flags + định danh/quan hệ kiểu**, **fields**, **methods** và **attributes**. Constant pool giúp tham chiếu ký hiệu bằng chỉ mục; `Code` attribute lưu bytecode của những method có thân phù hợp; còn class loader và JVM phối hợp đưa định nghĩa này vào môi trường thực thi. Nắm được cấu trúc trên và biết đọc `javap -v` là đủ để bắt đầu tìm hiểu class loading, linking, bytecode và các lỗi định dạng/phiên bản trong Java.

**Tài liệu chuẩn để tra cứu khi cần chi tiết từng tag/attribute:** *Java Virtual Machine Specification, Chapter 4 — The class File Format* (Java SE 17): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
