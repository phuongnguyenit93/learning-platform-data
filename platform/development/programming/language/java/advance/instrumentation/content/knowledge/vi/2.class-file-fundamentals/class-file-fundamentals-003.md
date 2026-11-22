# Tên lớp nội bộ, descriptor của trường, phương thức và kiểu mảng trong JVM class file

Khi đọc file `.class` bằng `javap` hoặc viết công cụ instrumentation bằng ASM, ta không làm việc trực tiếp với cách viết kiểu của mã nguồn Java. JVM dùng **tên lớp nội bộ** (*internal name*) để định danh lớp/giao diện và **descriptor** để mô tả kiểu trường, danh sách tham số và kiểu trả về của phương thức. Phân biệt đúng ba dạng này là điều kiện để đọc constant pool, tra cứu thành viên và tạo bytecode hợp lệ.

Sau bài này, bạn cần tự chuyển đổi được kiểu Java sang descriptor và ngược lại, đọc descriptor của phương thức từ trái sang phải, hiểu cách mảng và lớp lồng nhau được mã hóa, và dùng đúng `owner/name/descriptor` khi instrument bytecode.

## 1. Ba cách biểu diễn dễ bị nhầm lẫn

| Ngữ cảnh | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên trong mã Java | `java.lang.String` | Cách viết quen thuộc trong source |
| *Binary name* | `java.util.Map$Entry` | Tên nhị phân của lớp lồng `Map.Entry` |
| *Internal name* | `java/lang/String`, `java/util/Map$Entry` | Binary name có dấu `.` ngăn cách package được thay bằng `/` |
| *Field descriptor* | `Ljava/lang/String;`, `[I` | Mã hóa **một kiểu** |
| *Method descriptor* | `(Ljava/lang/String;[I)V` | Mã hóa **các tham số và kiểu trả về** |

Ví dụ `java.lang.String` là một tên lớp thông thường; `java/lang/String` là internal name; còn `Ljava/lang/String;` là descriptor của kiểu tham chiếu `String`. Chữ `L` mở đầu và dấu `;` kết thúc là **một phần của descriptor**, không thuộc internal name.

Với lớp lồng nhau:

- Trong source: `java.util.Map.Entry`.
- Binary name: `java.util.Map$Entry`.
- Internal name: `java/util/Map$Entry`.
- Field descriptor: `Ljava/util/Map$Entry;`.

Dấu `$` có thể xuất hiện trong binary name do trình biên dịch mã hóa lớp thành viên, lớp cục bộ hoặc lớp vô danh. **Không tự thay `$` bằng `/` hoặc `.`** khi tạo internal name. Lớp ở default package như `Example` có internal name `Example` và object descriptor `LExample;`.

**Ở đâu dùng tên nào?** Trong file class, mục `CONSTANT_Class_info` đại diện lớp/giao diện thường dùng internal name, chẳng hạn `java/lang/String`; nếu nó đại diện **kiểu mảng**, tên lưu ở đó có dạng array descriptor, chẳng hạn `[[I` hoặc `[Ljava/lang/String;`. Trường `field_info.descriptor_index` và `method_info.descriptor_index` trỏ tới chuỗi UTF-8 trong constant pool mô tả field/method. Các mục tham chiếu `CONSTANT_Fieldref_info`, `CONSTANT_Methodref_info` và `CONSTANT_InterfaceMethodref_info` cũng gắn tên thành viên với descriptor thông qua `CONSTANT_NameAndType_info`.

## 2. Ngữ pháp descriptor và bảng mã kiểu nguyên thủy

Có thể đọc cú pháp cốt lõi của JVM theo dạng rút gọn:

~~~text
FieldDescriptor   ::= FieldType
FieldType         ::= BaseType | ObjectType | ArrayType
BaseType          ::= B | C | D | F | I | J | S | Z
ObjectType        ::= L InternalClassName ;
ArrayType         ::= [ FieldType

MethodDescriptor  ::= ( FieldType* ) ReturnType
ReturnType        ::= FieldType | V
~~~

Trong ngữ pháp trên, phần chữ nằm giữa `L` và `;` phải là tên lớp/giao diện dạng nội bộ. Dấu `[` có thể lặp để biểu diễn nhiều chiều mảng. Các dấu ngoặc trong method descriptor là ký tự bắt buộc; không có dấu phẩy, khoảng trắng hoặc tên tham số.

| Mã | Kiểu Java | Mã | Kiểu Java |
| --- | --- | --- | --- |
| `B` | `byte` | `C` | `char` |
| `D` | `double` | `F` | `float` |
| `I` | `int` | `J` | `long` |
| `S` | `short` | `Z` | `boolean` |

Cần nhớ hai điểm: `J` đại diện `long` (không phải `L`), còn `L` mở đầu kiểu đối tượng. `V` có nghĩa `void` nhưng **chỉ được phép ở vị trí return type của method descriptor**. Một field, một tham số hay phần tử mảng không thể có descriptor `V`.

Ví dụ về **field descriptor**:

| Khai báo kiểu | Descriptor | Cách đọc |
| --- | --- | --- |
| `int` | `I` | Một giá trị nguyên |
| `long` | `J` | Một giá trị long |
| `boolean` | `Z` | Một giá trị boolean |
| `String` | `Ljava/lang/String;` | Tham chiếu tới `java.lang.String` |
| `Object` | `Ljava/lang/Object;` | Tham chiếu tới `java.lang.Object` |
| `Runnable` | `Ljava/lang/Runnable;` | Tham chiếu tới một interface, cú pháp giống class |
| `Map.Entry` | `Ljava/util/Map$Entry;` | Tham chiếu tới lớp lồng nhau |

Tên field như `count` hoặc `values` **không nằm trong descriptor**. Chẳng hạn, `private int count;` có tên `count` và descriptor `I`, được lưu ở các trường tương ứng trong cấu trúc `field_info`.

## 3. Descriptor cho kiểu mảng

Mỗi ký tự `[` ở **đầu** descriptor thêm **một chiều mảng**, sau đó là descriptor của kiểu phần tử cuối cùng:

| Java | Array descriptor |
| --- | --- |
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `double[][][]` | `[[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Map.Entry[]` | `[Ljava/util/Map$Entry;` |
| `int[][][]` | `[[[I` |

Ví dụ `[[Ljava/lang/String;` được đọc theo ba bước: `[` đầu tiên là chiều 1, `[` thứ hai là chiều 2, và `Ljava/lang/String;` là kiểu phần tử `String`; kết quả là `String[][]`. Với `[[I`, kiểu phần tử cuối cùng là `int`, nên đây là `int[][]`.

Một số quy tắc quan trọng:

1. **Mảng vẫn là kiểu tham chiếu**, dù phần tử là primitive. Descriptor của `int[]` là `[I`, không phải `L[I;`.
2. Không dùng ký hiệu `[]` ở cuối: `Ljava/lang/String;[]` không hợp lệ. Chiều mảng phải nằm **ở đầu**: `[Ljava/lang/String;`.
3. Mảng đối tượng dùng `[L...;`, mảng primitive dùng `[` kèm mã primitive. `[V` không hợp lệ vì không tồn tại mảng `void`.
4. Theo JVM Specification, descriptor của kiểu mảng hợp lệ có **tối đa 255 chiều**. Đây là giới hạn của định dạng JVM, không phải khuyến nghị thiết kế mảng nhiều chiều.

Lưu ý sự khác nhau giữa API reflection và descriptor: `String[][].class.getName()` trả về `[[Ljava.lang.String;` (dấu chấm ở tên lớp trong chuỗi tên nhị phân của mảng), trong khi `String[][].class.descriptorString()` trả về `[[Ljava/lang/String;` đúng cú pháp descriptor của class file. Do đó đừng lấy chuỗi từ `Class.getName()` của mảng rồi coi nó luôn là descriptor JVM.

## 4. Method descriptor: tham số và kết quả trả về

Dạng chung:

~~~text
(<descriptor-tham-số-1><descriptor-tham-số-2>...)<descriptor-trả-về>
~~~

Sau `(` đến trước `)` là **các kiểu tham số theo đúng thứ tự khai báo**; sau `)` là **một kiểu trả về** hoặc `V`. Khi không có tham số, cặp ngoặc là `()`. Không ghi tên phương thức, tên tham số, `throws`, modifier `public/static` hay generic type argument vào descriptor.

| Phương thức Java | Descriptor |
| --- | --- |
| `void run()` | `()V` |
| `int doubleIt(int value)` | `(I)I` |
| `String trim(String input)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `long sum(int[] values, long seed)` | `([IJ)J` |
| `String[][] merge(String[] a, int[][] b)` | `([Ljava/lang/String;[[I)[[Ljava/lang/String;` |
| `public static void main(String[] args)` | `([Ljava/lang/String;)V` |

Đọc `(IDLjava/lang/Thread;)Ljava/lang/Object;`:

1. Gặp `(`: bắt đầu các tham số.
2. `I`: tham số thứ nhất là `int`.
3. `D`: tham số thứ hai là `double`.
4. `Ljava/lang/Thread;`: tham số thứ ba là `java.lang.Thread`.
5. Gặp `)`: kết thúc danh sách tham số.
6. `Ljava/lang/Object;`: kết quả trả về là `java.lang.Object`.

Kết quả tương ứng với `Object m(int i, double d, Thread t)`. Vì `L...;` có độ dài thay đổi, phải đọc đến dấu `;` thay vì coi mỗi ký tự là một kiểu. Với ký tự `[`, tiếp tục đọc tới hết descriptor của phần tử để xác định **một tham số mảng**.

**Receiver `this` không được viết vào method descriptor.** Một instance method `String name()` vẫn có descriptor `()Ljava/lang/String;`, dù khi gọi bằng `invokevirtual` JVM còn tiêu thụ một tham chiếu receiver trên operand stack. Phương thức `static` cùng danh sách tham số và kiểu trả về cũng có descriptor giống như vậy; modifier `static` được biểu diễn qua access flag, không qua descriptor.

**Constructor** trong class file có tên đặc biệt `<init>` và return descriptor `V`. Constructor `Example(int x)` tương ứng `<init>(I)V`. Trình khởi tạo lớp `<clinit>`, nếu có, sử dụng descriptor `()V`. Hai tên này thuộc phần **name**, còn `(I)V` hay `()V` mới là phần **descriptor**.

### Giới hạn tham số 255 đơn vị

JVM giới hạn tổng *độ dài tham số* của một method descriptor không quá **255 đơn vị**. `long` và `double` đóng góp **2 đơn vị** mỗi tham số; các kiểu khác, kể cả mảng hoặc tham chiếu, đóng góp **1 đơn vị**. Với instance/interface method, còn tính thêm **1 đơn vị cho `this`**, mặc dù `this` không xuất hiện trong chuỗi descriptor. Vì vậy một instance method có tối đa 254 tham số `int`, hoặc ít hơn nếu dùng `long`/`double`. Giới hạn này cũng giải thích vì sao việc thêm tham số khi instrument một method có chữ ký rất lớn có thể làm class file không hợp lệ.

## 5. Descriptor và generic Signature là hai lớp thông tin khác nhau

JVM descriptor diễn tả các kiểu sau **type erasure**, nên không giữ đối số generic như `String` trong `List<String>`. Ví dụ:

~~~java
private java.util.List<String> names;

public java.util.List<String> copy(java.util.List<String> input) {
    return input;
}
~~~

- Field descriptor của `names`: `Ljava/util/List;`.
- Method descriptor của `copy`: `(Ljava/util/List;)Ljava/util/List;`.
- Thông tin `<String>` có thể được giữ ở thuộc tính `Signature` của class file, với **ngữ pháp signature riêng**.

Không đưa chuỗi `Ljava/util/List<Ljava/lang/String;>;` vào chỗ cần **field descriptor**: đó là cú pháp generic signature, không phải descriptor hợp lệ. Tương tự, mã `T...;` có ý nghĩa trong generic signature nhưng không phải một mã kiểu primitive/object/array của field descriptor. Khi tra cứu method bằng bytecode API, phải dùng descriptor đã erasure phù hợp.

Nếu generic type variable không có bound cụ thể, erasure thông thường là `Object`; nếu có bound là class/interface, erasure theo bound đầu thích hợp. Vì thế muốn suy ra descriptor của generic method đúng cách, cần biết chữ ký đã erasure, không chép nguyên cú pháp `<T>` từ source.

## 6. Quan sát descriptor bằng công cụ JDK

Tạo tệp `DescriptorWalkthrough.java` với mã sau. Ví dụ này chỉ dùng API của JDK 17 trở lên, không cần thư viện bên ngoài:

~~~java
import java.lang.invoke.MethodType;
import java.util.Map;

public class DescriptorWalkthrough {
    public static void main(String[] args) {
        System.out.println(Map.Entry.class.getName());
        System.out.println(Map.Entry.class.getName().replace('.', '/'));
        System.out.println(String.class.descriptorString());
        System.out.println(int[][].class.descriptorString());
        System.out.println(String[][].class.getName());
        System.out.println(String[][].class.descriptorString());

        MethodType type =
                MethodType.methodType(long.class, int[].class, long.class);
        System.out.println(type.descriptorString());

        MethodType parsed = MethodType.fromMethodDescriptorString(
                "([IJ)J", DescriptorWalkthrough.class.getClassLoader());
        System.out.println(parsed.parameterCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DescriptorWalkthrough.java
java DescriptorWalkthrough
~~~

Stdout chính xác:

~~~text
java.util.Map$Entry
java/util/Map$Entry
Ljava/lang/String;
[[I
[[Ljava.lang.String;
[[Ljava/lang/String;
([IJ)J
2
~~~

Ý nghĩa: `Class.descriptorString()` trả đúng descriptor cho primitive, object và array; `MethodType.descriptorString()` cho descriptor của **kiểu phương thức**; `MethodType.fromMethodDescriptorString(...)` đọc một method descriptor và giải quyết kiểu tham chiếu qua class loader được cung cấp. Với lớp không tìm được khi phân tích descriptor, việc phân giải type có thể thất bại.

Để nhìn trực tiếp thông tin được biên dịch vào class file, tạo `BytecodeFixture.java`:

~~~java
public class BytecodeFixture {
    private String[] labels;
    private int[][] points;

    public static long sum(int[] values, long initial) {
        long result = initial;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    public String[][] wrap(String[] values) {
        return new String[][] { values };
    }
}
~~~

Chạy:

~~~bash
javac BytecodeFixture.java
javap -p -s BytecodeFixture
javap -v BytecodeFixture
~~~

Trong kết quả `javap -p -s`, hãy tìm những dòng descriptor sau (bên cạnh tên field/method tương ứng):

~~~text
labels  -> [Ljava/lang/String;
points  -> [[I
BytecodeFixture() -> ()V
sum(int[], long) -> ([IJ)J
wrap(String[]) -> ([Ljava/lang/String;)[[Ljava/lang/String;
~~~

Các dòng trên là **bảng đối chiếu đã rút gọn**, không phải bản sao nguyên văn định dạng output của `javap`. Lệnh `javap -v` hiển thị thêm constant pool, access flags, `descriptor:` và bytecode instructions để kiểm chứng liên hệ giữa tên, descriptor và lệnh gọi.

## 7. Ứng dụng trực tiếp khi instrumentation với ASM

ASM sử dụng đúng các dạng tên của JVM. Trong các lời gọi như `visitFieldInsn` và `visitMethodInsn`, cần tách bạch:

- `owner`: internal name của lớp sở hữu thành viên, ví dụ `java/lang/System`.
- `name`: tên thành viên, ví dụ `out` hoặc `println`.
- `descriptor`: field descriptor nếu là field, hoặc method descriptor nếu là method.
- `opcode`/`isInterface`: cách truy cập field hoặc gọi method; hai giá trị này **không mã hóa vào descriptor**.

Ví dụ mảnh code ASM sau minh họa bytecode tương đương `System.out.println("Hello");`. Đây là **đoạn API minh họa**, cần dự án có thư viện ASM và một `MethodVisitor mv` hợp lệ; không phải chương trình Java độc lập:

~~~java
mv.visitFieldInsn(
        Opcodes.GETSTATIC,
        "java/lang/System",
        "out",
        "Ljava/io/PrintStream;");

mv.visitLdcInsn("Hello");

mv.visitMethodInsn(
        Opcodes.INVOKEVIRTUAL,
        "java/io/PrintStream",
        "println",
        "(Ljava/lang/String;)V",
        false);
~~~

Diễn giải operand stack: `GETSTATIC` đẩy tham chiếu `PrintStream` lên stack; `LDC` đẩy chuỗi `String`; `INVOKEVIRTUAL` tiêu thụ receiver + một `String` và trả `void`. Descriptor của trường `out` là `Ljava/io/PrintStream;`, còn descriptor của `println(String)` là `(Ljava/lang/String;)V`. Nếu nhầm `owner` thành `Ljava/io/PrintStream;`, nhầm kiểu field thành method descriptor, hoặc dùng `java.io.PrintStream` ở nơi cần internal name, công cụ có thể sinh tham chiếu không khớp định dạng hoặc không resolve được.

Để tránh ghép chuỗi sai, ASM cung cấp `org.objectweb.asm.Type` với các hàm như `Type.getInternalName(SomeClass.class)`, `Type.getDescriptor(SomeClass.class)` và `Type.getMethodDescriptor(...)`. Đây là API **của thư viện ASM**, không thuộc JDK. Kiểm tra vẫn cần thiết vì descriptor hợp lệ về cú pháp chưa bảo đảm lời gọi dùng đúng opcode, receiver, kiểu trên operand stack hoặc StackMap frames. Khi instrument một lời gọi đang có sẵn, hãy đọc descriptor gốc, xác định thứ tự tham số và kiểu kết quả, sau đó duy trì trạng thái stack phù hợp.

### Cách phân tích lỗi thường gặp

| Hiện tượng | Điều nên kiểm tra |
| --- | --- |
| `NoSuchMethodError` | Có đúng owner + name + **method descriptor đầy đủ** (gồm kiểu trả về) không? |
| `NoSuchFieldError` | Có đúng owner + field name + field descriptor không? |
| `ClassNotFoundException` khi dùng reflection | `Class.forName("java.lang.String")` cần tên nhị phân có dấu `.`, không phải `java/lang/String` |
| `ClassFormatError` hoặc `VerifyError` | Descriptor có hợp lệ không; lệnh gọi, operand stack, local variables và frames có tương thích không? |
| Instrumentation không bắt được method overload | Bộ lọc có so sánh đúng **name + descriptor** thay vì chỉ tên không? |

Một phương thức overload tên `process` có thể có `(I)V` và `(Ljava/lang/String;)V`; chỉ so sánh `process` là chưa đủ. Trong mã nguồn Java không thể overload chỉ dựa vào return type, nhưng **method descriptor ở cấp JVM vẫn chứa return type**, nên phải giữ nó khi tra cứu/gọi ở bytecode level.

## 8. Checklist chuyển đổi nhanh và lỗi cú pháp

**Từ kiểu Java sang field descriptor:** (1) primitive → mã một chữ; (2) class/interface → `L` + internal name + `;`; (3) mảng → thêm `[` ở đầu cho từng chiều. Với method, ghép lần lượt descriptor các tham số vào trong `(...)` rồi nối descriptor của return type (hoặc `V`).

**Từ descriptor sang Java:** (1) nếu bắt đầu bằng `[`, đếm số chiều; (2) đọc mã primitive hoặc cặp `L...;`; (3) đổi `/` trong internal name về `.` khi trình bày tên đầy đủ; (4) nếu là method, phân tách phần trước và sau `)`. Không tách `L...;` tại dấu `/` vì toàn bộ từ `L` đến `;` chỉ là **một kiểu**.

| Chuỗi | Đánh giá |
| --- | --- |
| `Ljava/lang/String;` | Hợp lệ: object field descriptor |
| `[Ljava/lang/String;` | Hợp lệ: array field descriptor |
| `([I)V` | Hợp lệ: method nhận `int[]` và trả `void` |
| `java.lang.String` | Không phải internal name hay field descriptor |
| `Ljava.lang.String;` | Sai: tên lớp trong descriptor phải dùng `/` giữa package |
| `V` làm field/parameter | Sai: `void` chỉ hợp lệ ở return type |
| `[V` | Sai: không có `void[]` |
| `(I, J)V` | Sai: descriptor không có dấu phẩy/khoảng trắng |
| `()Ljava/lang/String` | Sai: thiếu `;` kết thúc object type |
| `Ljava/util/List<Ljava/lang/String;>;` | Không phải field descriptor; đây là dạng generic signature |

Một descriptor hợp lệ phải **được đọc hết chuỗi** mà không dư ký tự. Ví dụ `I;` sai vì `I` đã là một field descriptor hoàn chỉnh; dấu `;` chỉ dùng để kết thúc `L...;`. Không có quy tắc thêm `;` sau mã primitive hoặc sau một array primitive như `[[I`.

## 9. Bài tập tự kiểm tra

1. Giải mã `(IJ[Ljava/lang/String;)V` thành danh sách tham số và kiểu trả về.
2. Viết descriptor cho `static String[][] combine(int[] a, boolean enabled, Map.Entry<String, Integer> e)`.
3. Xác định field descriptor cho `double[][]`, `Thread[]` và `long[][][]`.
4. Cho lời gọi `visitMethodInsn(INVOKESTATIC, "java/lang/System", "nanoTime", "()J", false)`, method nhận bao nhiêu tham số và trả về kiểu gì?
5. Giải thích vì sao `String[].class.getName()` và `String[].class.descriptorString()` khác nhau.

**Đáp án đối chiếu:**

1. `int`, `long`, `String[]` → `void`. Phần `[Ljava/lang/String;` là một tham số.
2. `([IZLjava/util/Map$Entry;)[[Ljava/lang/String;`. Type argument `<String, Integer>` bị erasure ở descriptor.
3. Lần lượt `[[D`, `[Ljava/lang/Thread;`, `[[[J`.
4. Không có tham số; trả `long` (`J`). Vì là `INVOKESTATIC` nên không có receiver `this`.
5. `getName()` trả tên nhị phân của array class (ví dụ `[Ljava.lang.String;`); `descriptorString()` trả cú pháp descriptor trong class file (`[Ljava/lang/String;`).

Để học sâu hơn từ đặc tả chính thức, tra cứu *Java Virtual Machine Specification (Java SE 21)*, [§4.2.1 — Binary Class and Interface Names](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.2.1), [§4.3.2 — Field Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2) và [§4.3.3 — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3).
