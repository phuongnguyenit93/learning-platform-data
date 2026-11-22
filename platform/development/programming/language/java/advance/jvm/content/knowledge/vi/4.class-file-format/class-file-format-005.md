# Access flags, lớp cha, giao diện, trường và phương thức trong tệp `.class`

## 1. Mục tiêu và vị trí của các thành phần

Tệp `.class` không đơn thuần chứa một danh sách lệnh bytecode. Nó còn mô tả **danh tính lớp**, các **đặc điểm truy cập/loại lớp**, **lớp cha trực tiếp**, **các giao diện trực tiếp**, **các trường khai báo** và **các phương thức khai báo**. JVM dựa vào thông tin này để nạp, liên kết, xác minh, kiểm tra truy cập, thực thi và phản chiếu (reflection) đối với chương trình.

Bài này tập trung vào sáu thành phần của cấu trúc `ClassFile` trong **JVMS `4.1`**: `access_flags`, `this_class`, `super_class`, `interfaces[]`, `fields[]` và `methods[]`. Chúng dùng nhiều chỉ số trỏ vào **constant pool** và chứa các bảng con có cấu trúc riêng.

Sau khi học, bạn sẽ đọc được đầu ra `javap -v -p` để trả lời:

- Đây là `class`, `interface`, `enum`, annotation interface hay `module-info`? Loại nào là `public`, `final`, `abstract`?
- Lớp này trực tiếp `extends` và `implements` ai? Vì sao `super_class` của interface vẫn là `java/lang/Object`?
- Field và method nào được **khai báo trực tiếp** trong tệp, và thành viên nào chỉ được **kế thừa**?
- Flag `ACC_FINAL` của lớp/field/method có khác nhau không? Vì sao giá trị bit `0x0040` không thể hiểu nếu chưa biết nó thuộc bảng nào?
- Constructor `<init>`, class initializer `<clinit>`, field descriptor, method descriptor và `Code` attribute được biểu diễn ở đâu?
- Những trường hợp đặc biệt như `record`, `sealed class`, compiler-generated bridge method và `module-info.class` nên đọc thế nào?

## 2. Bản đồ cấu trúc `ClassFile`

Một tệp class hợp lệ có khung nhị phân (lược đồ đúng theo JVMS; `u1`, `u2`, `u4` lần lượt là các số không dấu 1, 2, 4 byte):

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

Trình tự xuất hiện ở trên là **thứ tự dữ liệu trong file**, không phải thứ tự VM “thực thi các phần”. `magic` thông thường là `0xCAFEBABE`; `major_version` giúp nhận biết mức class-file format (ví dụ Java 17 → major 61, Java 21 → 65, Java 25 → 69). `constant_pool` chứa các biểu diễn tên, chuỗi, descriptor, tham chiếu lớp/field/method… mà các bảng phía sau liên hệ bằng **index**.

| Mục | Dạng dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `access_flags` | `u2` bitmask | Các thuộc tính của **class/interface/module đang định nghĩa** |
| `this_class` | `u2` constant-pool index | Danh tính của chính class/interface này |
| `super_class` | `u2` constant-pool index hoặc 0 trong trường hợp đặc biệt | **Superclass trực tiếp** ở cấp class-file format |
| `interfaces_count`, `interfaces[]` | `u2` count và dãy index | Danh sách **direct superinterfaces** |
| `fields_count`, `fields[]` | count và dãy `field_info` | Các field **được khai báo** trong class/interface |
| `methods_count`, `methods[]` | count và dãy `method_info` | Các method/constructor/class initializer **được khai báo** |
| `attributes[]` cuối file | dãy `attribute_info` | Metadata ở cấp lớp như `SourceFile`, `Signature`, `Record`, `PermittedSubclasses`… |

**Nguyên tắc đọc:** `this_class`, `super_class`, từng phần tử `interfaces[]` là **chỉ số** tới `CONSTANT_Class_info` trong constant pool, không phải tên viết thẳng vào các trường `u2`. `fields[]` và `methods[]` lại chứa **các cấu trúc con**, mỗi cấu trúc cũng trỏ về constant pool để giải nghĩa tên và descriptor.

~~~text
ClassFile
  |
  +-- access_flags: ACC_PUBLIC | ACC_FINAL | ACC_SUPER
  +-- this_class -------> constant_pool[#X] = Class "demo/ClassLayout"
  +-- super_class ------> constant_pool[#Y] = Class "demo/Base"
  +-- interfaces[] -----> constant_pool[#A] = Class "demo/Labeled"
  |                    -> constant_pool[#B] = Class "java/io/Serializable"
  +-- fields[] ---------> field_info { flags, name_index, descriptor_index, attributes[] }
  +-- methods[] --------> method_info { flags, name_index, descriptor_index, attributes[] }
  +-- attributes[] -----> SourceFile, Signature, Record, ...
~~~

`#X`, `#Y`, `#A`, `#B` chỉ là **ký hiệu minh họa**: số index thực tế do compiler và nội dung class file quyết định.

## 3. `access_flags` của class/interface

`access_flags` là mặt nạ bit 16-bit: mỗi bit cho biết một quyền truy cập hoặc đặc điểm của **class/interface/module**. Nhiều cờ có thể cùng bật, nhưng JVMS có các quy tắc giới hạn tổ hợp.

| Cờ cấp class | Giá trị hex | Diễn giải đúng |
| --- | --- | --- |
| `ACC_PUBLIC` | `0x0001` | Class/interface được khai báo `public` |
| `ACC_FINAL` | `0x0010` | Class không thể bị subclass |
| `ACC_SUPER` | `0x0020` | Cờ tương thích lịch sử với ngữ nghĩa `invokespecial` |
| `ACC_INTERFACE` | `0x0200` | Đây là interface, không phải class thông thường |
| `ACC_ABSTRACT` | `0x0400` | Abstract, không được khởi tạo instance trực tiếp |
| `ACC_SYNTHETIC` | `0x1000` | Loại được compiler sinh, không tương ứng trực tiếp khai báo source |
| `ACC_ANNOTATION` | `0x2000` | Đây là annotation interface |
| `ACC_ENUM` | `0x4000` | Liên quan kiểu enum theo quy tắc JVMS |
| `ACC_MODULE` | `0x8000` | Tệp đặc biệt mô tả module, không phải class/interface thông thường |

Một class được khai báo `public final class ClassLayout` thường có `ACC_PUBLIC`, `ACC_FINAL` và `ACC_SUPER` trong file do `javac` hiện đại sinh. Để minh họa bitmask:

~~~text
ACC_PUBLIC = 0x0001
ACC_FINAL  = 0x0010
ACC_SUPER  = 0x0020
-------------------
Tổng       = 0x0031
~~~

Khi thấy `flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER`, bạn đang nhìn **quyền và đặc điểm của lớp**, chứ không phải flags của field hay method.

Các quy tắc đáng nhớ:

- `ACC_INTERFACE` yêu cầu `ACC_ABSTRACT`; interface không thể đồng thời đặt `ACC_FINAL` hay `ACC_SUPER`. Annotation interface đồng thời có `ACC_ANNOTATION` và `ACC_INTERFACE`.
- Class bình thường không được vừa `ACC_FINAL` vừa `ACC_ABSTRACT`.
- `ACC_SUPER` là cờ lịch sử; từ Java SE 8 trở đi, JVM coi cờ này như được bật cho mọi class file bất kể bit lưu trong file. **Không** dùng việc có/không có flag này để kết luận source có từ khóa `super`.
- `ACC_MODULE` là trường hợp đặc biệt của `module-info.class` với quy tắc cấu trúc riêng: flag này không được kết hợp với các cờ class khác.

### Những đặc điểm hiện đại không phải cờ class thông thường

- **Record** (`record Point(int x, int y) {}`) sử dụng **`Record` attribute** và các quy tắc cấu trúc tương ứng. Đừng tự coi `ACC_RECORD` là một bit `access_flags` chính thức trong bảng `ClassFile` của JVMS: một số thư viện bytecode có thể dùng hằng `ACC_RECORD` nội bộ hoặc dạng pseudo flag cho việc biểu diễn metadata.
- **Sealed class/interface** dùng **`PermittedSubclasses` attribute** để lưu danh sách các lớp con được phép; không có `ACC_SEALED` trong bảng access flags ở `4.1`.
- **Nest-based access** dùng metadata như `NestHost`/`NestMembers`, liên quan kiểm tra truy cập `private`; không suy từ `ACC_PRIVATE` của một “top-level class” (top-level class không có flag `ACC_PRIVATE` ở đây).
- `ACC_SYNTHETIC` của **class** chỉ nói về class do compiler sinh; `ACC_SYNTHETIC` còn có thể xuất hiện với field/method theo bảng tương ứng.

## 4. `this_class` và `super_class`: phân biệt chính mình với cha trực tiếp

### `this_class`

`this_class` bắt buộc trỏ tới một `CONSTANT_Class_info` biểu diễn **lớp hoặc interface đang được định nghĩa**. Tên nội bộ thường dùng dấu `/` thay dấu chấm:

~~~text
Source: package demo; public class App { }
Binary name: demo.App
JVM internal name: demo/App
Field descriptor (tham chiếu App): Ldemo/App;
~~~

`demo/App` trong constant pool là tên kiểu ở dạng nội bộ; `Ldemo/App;` lại là **field descriptor**. Phải phân biệt chúng vì cú pháp và vị trí sử dụng khác nhau.

### `super_class`

Trong class thông thường, `super_class` trỏ tới `CONSTANT_Class_info` của **direct superclass**:

~~~java
class Animal { }
class Dog extends Animal { }
class Poodle extends Dog { }
~~~

Với `Poodle.class`:

~~~text
this_class  -> Poodle
super_class -> Dog
~~~

`Animal` là **superclass gián tiếp**, không nằm trực tiếp trong `super_class` của `Poodle.class`. JVM biết chuỗi kế thừa bằng cách đi tiếp sang `Dog.class` rồi tra superclass của `Dog`.

Các trường hợp đặc biệt quan trọng:

1. **`java/lang/Object`**: class thông thường duy nhất không có direct superclass, nên `super_class = 0`.
2. **Interface**: trong **class-file format**, `super_class` của interface trỏ tới `java/lang/Object`. Điều này **không có nghĩa** interface `extends Object` trong source Java; direct superinterfaces nằm ở `interfaces[]`.
3. **`module-info.class` với `ACC_MODULE`**: `super_class = 0` theo quy tắc riêng và `interfaces_count = fields_count = methods_count = 0`. Đừng áp dụng quy tắc “chỉ Object có super_class 0” vào module descriptor mà bỏ qua ngoại lệ này.

Với một class không ghi `extends` trong source, superclass thông thường là `java/lang/Object`. `final` class có thể **kế thừa** một lớp khác nhưng không cho lớp thứ ba kế thừa chính nó.

## 5. `interfaces_count` và `interfaces[]`

`interfaces_count` là số lượng **direct superinterfaces**. Mảng `interfaces[]` chứa từng **index** tới `CONSTANT_Class_info` tương ứng, giữ **thứ tự từ trái qua phải trong source** theo JVMS.

Ví dụ:

~~~java
interface Identified {
    long id();
}

interface Named {
    String name();
}

class Base implements Identified {
    @Override public long id() { return 1; }
}

class Item extends Base implements Named, java.io.Serializable {
    @Override public String name() { return "Item"; }
}
~~~

Với `Item.class`:

~~~text
this_class    = Item
super_class   = Base
interfaces[]  = [Named, java/io/Serializable]
interfaces_count = 2
~~~

**`Identified` không xuất hiện trong `Item.class.interfaces[]`**, dù `Item` kế thừa việc triển khai interface đó qua `Base`. Bạn cần đọc `Base.class` để thấy quan hệ `Base implements Identified`.

Nếu một interface viết `interface B extends A, C`, file của `B` có `super_class -> java/lang/Object` nhưng `interfaces[] -> [A, C]`. Đây là cấu trúc cấp bytecode; không suy ngược rằng Java source cho phép class `extends` nhiều lớp cha: Java chỉ cho **một superclass trực tiếp**, nhưng có thể nhiều interface.

Các phần tử `interfaces[]` không chứa phương thức triển khai. Bảng này chỉ định **quan hệ kiểu trực tiếp**; các method riêng thuộc `methods[]` của từng loại tương ứng.

## 6. `fields[]`: các field khai báo trực tiếp

Mỗi field có một `field_info` độc lập theo JVMS `4.5`:

~~~text
field_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

`name_index` trỏ tới tên field dạng `CONSTANT_Utf8_info`, còn `descriptor_index` trỏ tới descriptor biểu diễn **kiểu dữ liệu ở cấp JVM**. Các attribute cho biết metadata bổ sung như `ConstantValue`, `Signature`, annotations hoặc thông tin deprecation.

| Field Java | Descriptor | Cờ tiêu biểu |
| --- | --- | --- |
| `private int count;` | `I` | `ACC_PRIVATE` |
| `public static final long MAX = 10L;` | `J` | `ACC_PUBLIC, ACC_STATIC, ACC_FINAL` |
| `volatile boolean running;` | `Z` | `ACC_VOLATILE` |
| `transient String secret;` | `Ljava/lang/String;` | `ACC_TRANSIENT` |
| `String[] names;` | `[Ljava/lang/String;` | theo modifier |
| `List<String> items;` | `Ljava/util/List;` | `Signature` có thể giữ generic signature |

Các cờ field chính:

| Tên cờ | Hex | Ngữ nghĩa |
| --- | --- | --- |
| `ACC_PUBLIC` / `ACC_PRIVATE` / `ACC_PROTECTED` | `0x0001` / `0x0002` / `0x0004` | Quyền truy cập field |
| `ACC_STATIC` | `0x0008` | Field thuộc class thay vì mỗi instance |
| `ACC_FINAL` | `0x0010` | Field có ràng buộc gán của final |
| `ACC_VOLATILE` | `0x0040` | Field volatile với ngữ nghĩa bộ nhớ Java |
| `ACC_TRANSIENT` | `0x0080` | Field transient, có ý nghĩa cho cơ chế serialization liên quan |
| `ACC_SYNTHETIC` | `0x1000` | Field do compiler sinh |
| `ACC_ENUM` | `0x4000` | Field đại diện hằng của enum |

**Các giới hạn:** một field không thể đồng thời `public` và `private`; cũng không thể đồng thời `ACC_FINAL` và `ACC_VOLATILE`. Các field được khai báo trong interface phải có `ACC_PUBLIC`, `ACC_STATIC` và `ACC_FINAL` (có thể thêm `ACC_SYNTHETIC` theo quy tắc).

### Field khai báo, field kế thừa và giá trị khởi tạo

`fields[]` của một class chỉ chứa các field **được khai báo trong class đó**, không nhét lại field kế thừa từ cha. `new Child()` có thể có state thuộc `Base` và `Child` nhưng `Child.class.fields[]` vẫn chỉ liệt kê phần khai báo trong `Child`.

`ACC_STATIC | ACC_FINAL` **không tự chứng minh** có `ConstantValue` attribute: chỉ một số hằng compile-time phù hợp dùng attribute này. Những initializer khác có thể được compiler đưa vào `<clinit>` với static field, hoặc `<init>`/instance initializer với instance field. `field_info` định nghĩa field và metadata; không phải chứa toàn bộ logic thực thi hàm gán giá trị.

Ví dụ `static int created;` có giá trị mặc định `0` ở preparation và không cần `<clinit>` chỉ để nhận 0. Còn `static int created = calculate();` thường phát sinh code khởi tạo class.

## 7. `methods[]`: method và các hàm khởi tạo đặc biệt

Mỗi phần tử `method_info` theo JVMS `4.6`:

~~~text
method_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

`name_index` cho biết tên, `descriptor_index` cho biết **tham số và kiểu trả về**. Cú pháp method descriptor:

~~~text
(ParameterDescriptors)ReturnDescriptor

()V                      -> void noArgs()
(I)I                     -> int f(int)
(JLjava/lang/String;)V   -> void g(long, String)
([Ljava/lang/String;)V   -> void main(String[])
()Ljava/lang/String;     -> String get()
~~~

| Cờ cấp method | Hex | Diễn giải |
| --- | --- | --- |
| `ACC_PUBLIC` / `ACC_PRIVATE` / `ACC_PROTECTED` | `0x0001` / `0x0002` / `0x0004` | Quyền truy cập method |
| `ACC_STATIC` | `0x0008` | Static method |
| `ACC_FINAL` | `0x0010` | Không được override method này |
| `ACC_SYNCHRONIZED` | `0x0020` | Thực thi có cơ chế monitor khi invoke |
| `ACC_BRIDGE` | `0x0040` | Bridge method do compiler sinh |
| `ACC_VARARGS` | `0x0080` | Method khai báo varargs |
| `ACC_NATIVE` | `0x0100` | Có phần triển khai native |
| `ACC_ABSTRACT` | `0x0400` | Không có thân method |
| `ACC_SYNTHETIC` | `0x1000` | Method do compiler sinh |
| `ACC_STRICT` | `0x0800` trong class major 46–60 | Flag lịch sử của `strictfp`; không còn có ý nghĩa đó ở major ngoài khoảng này |

Đọc bit theo **ngữ cảnh** là cực kỳ quan trọng:

- `0x0020` ở **class flags** là `ACC_SUPER`, ở **method flags** là `ACC_SYNCHRONIZED`.
- `0x0040` ở **field flags** là `ACC_VOLATILE`, còn ở **method flags** là `ACC_BRIDGE`.
- `0x0080` ở **field flags** là `ACC_TRANSIENT`, còn ở **method flags** là `ACC_VARARGS`.
- `ACC_FINAL` xuất hiện ở cả class/field/method, nhưng mang ràng buộc tương ứng từng loại; không được suy luận tất cả là một thao tác runtime giống nhau.

### `Code` attribute, abstract và native

Với method thông thường không có `ACC_ABSTRACT` hoặc `ACC_NATIVE`, implementation được mô tả bằng **`Code` attribute** (bytecode, stack/locals, exception table và một số metadata). `abstract` method không có body để lưu bytecode; `native` method triển khai theo cơ chế native chứ không có `Code` như Java method thông thường.

Một tệp `.class` có thể khai báo:

- `<init>`: **instance initialization method**, tương ứng constructor ở cấp JVM, descriptor có kiểu trả về `V`; mỗi constructor overload có descriptor riêng.
- `<clinit>`: **class/interface initialization method**, compiler sinh khi cần thực thi static initialization; không phải method bạn gọi bằng Java source như `obj.<clinit>()`.
- `main`: chỉ là tên một method trong `methods[]`. Việc launcher chọn `main` làm điểm vào là luật khởi chạy riêng, không khiến method này trở thành mục đặc biệt trong format `ClassFile`.

`methods[]` cũng chỉ chứa **phương thức khai báo** trong class/interface đó, không chép các method kế thừa. Một `default method` do interface định nghĩa thuộc `methods[]` **của interface**, và một class chỉ kế thừa implementation đó không nhất thiết có cùng `method_info` trong file của mình.

### Generics, overload và bridge method

JVM sử dụng **descriptor** để xác định field/method type. Với `List<String>`, descriptor JVM thông thường là `Ljava/util/List;` sau type erasure; thông tin generic có thể được giữ qua **`Signature` attribute**, không trở thành một descriptor runtime dạng `List<String>`.

Overload được phân biệt bởi descriptor khác nhau. Trong class file, không có hai `field_info` cùng **name + descriptor**, và không có hai `method_info` cùng **name + descriptor**. Vì descriptor method chứa **kiểu trả về**, bytecode và ngôn ngữ Java không hoàn toàn cùng quy tắc đánh giá một “chữ ký” hợp lệ; đừng tự áp dụng nguyên tắc overload source Java như quy tắc toàn diện của class-file verifier.

Đối với generic overriding hoặc covariant return, compiler có thể phát sinh **bridge method** để giữ dispatch đúng sau erasure. Một bridge thường mang `ACC_BRIDGE | ACC_SYNTHETIC`, có method descriptor riêng và `Code` chuyển tiếp đến implementation thật. Đây là lý do `javap -p -v` đôi khi hiển thị nhiều method hơn số method rõ ràng trong source.

## 8. Ví dụ Java 17+: đọc một class từ source đến `javap`

Tạo file `ClassLayout.java` trong thư mục trống. Đoạn code sau **biên dịch và chạy độc lập bằng Java 17+**:

~~~java
interface Labeled {
    String label();

    default String formatted() {
        return "[" + label() + "]";
    }
}

abstract class Base {
    protected final long id;

    Base(long id) {
        this.id = id;
    }

    public long id() {
        return id;
    }
}

public final class ClassLayout extends Base
        implements Labeled, java.io.Serializable {

    private static final long serialVersionUID = 1L;
    private static int created;
    private final String name;

    public ClassLayout(long id, String name) {
        super(id);
        this.name = name;
        created++;
    }

    @Override
    public String label() {
        return name;
    }

    public int score(int bonus) {
        return name.length() + bonus;
    }

    public static int created() {
        return created;
    }

    public static void main(String[] args) {
        ClassLayout item = new ClassLayout(7L, "JVM");
        System.out.println(item.formatted());
        System.out.println("id=" + item.id()
                + ",score=" + item.score(2)
                + ",created=" + created());
    }
}
~~~

Chạy:

~~~bash
javac ClassLayout.java
java ClassLayout
~~~

**Stdout chính xác:**

~~~text
[JVM]
id=7,score=5,created=1
~~~

Giải thích: `ClassLayout` thừa hưởng `id()` và field `id` từ `Base`, triển khai `label()`, kế thừa default `formatted()` của `Labeled`, có field `name` của riêng mình. Constructor tăng `created` một lần. `"JVM".length() + 2 = 5`.

Khi `javac ClassLayout.java` chạy, thư mục sẽ có các file `Labeled.class`, `Base.class`, `ClassLayout.class`; mỗi class/interface có **ClassFile riêng**. Class `Base` không bị “nhét nguyên” vào `ClassLayout.class`.

### Dùng `javap` để đọc cấu trúc

~~~bash
javap -p ClassLayout
javap -v -p ClassLayout
javap -v -p Base
javap -v -p Labeled
javap -c -p ClassLayout
~~~

`-p` cho thấy cả thành viên `private`, `-v` cho metadata/constant pool/descriptor/flags/attributes, `-c` disassemble `Code`. Output đầy đủ gồm nhiều `#index`, BCI và constant pool entries có thể thay đổi theo phiên bản compiler; vì vậy bên dưới là **những quan hệ cần kiểm chứng**, không khẳng định từng dòng output byte-for-byte giống trên mọi JDK.

| Vị trí kiểm tra | Điều nên quan sát với `ClassLayout.class` |
| --- | --- |
| Class header/flags | `public final class ClassLayout extends Base implements Labeled, java.io.Serializable`; cờ tương ứng `ACC_PUBLIC`, `ACC_FINAL` và thường `ACC_SUPER` |
| `this_class` | Constant-pool `Class` trỏ tới `ClassLayout` |
| `super_class` | Constant-pool `Class` trỏ tới `Base`, **không phải `java/lang/Object`** |
| `interfaces[]` | Hai direct interfaces: `Labeled` và `java/io/Serializable` theo thứ tự source |
| `fields[]` | `serialVersionUID`, `created`, `name` được khai báo trực tiếp |
| `methods[]` | Constructor `<init>`, `label`, `score`, `created`, `main`; các compiler-generated members khác chỉ khi compiler cần |
| `Code` của constructor | Gọi `Base.<init>(long)`, gán `name` và tăng `created` |
| `Code` của `main` | Tạo `ClassLayout`, gọi `formatted`, `id`, `score` và in kết quả |

Những gì **không nên tìm trong `ClassLayout.class` như phần tử khai báo của nó**:

- Field `id`: thuộc `Base.fields[]`.
- Method `id()`: thuộc `Base.methods[]`.
- Default `formatted()`: thuộc `Labeled.methods[]`; `ClassLayout` không override method đó.
- `java/lang/Object` như `super_class` trực tiếp: class này extends `Base`, còn `Base` mới trực tiếp extends `Object`.

### Descriptor thật của các method/field

| Khai báo | Descriptor của bản trong `ClassLayout.class` |
| --- | --- |
| `private static final long serialVersionUID` | `J` |
| `private static int created` | `I` |
| `private final String name` | `Ljava/lang/String;` |
| `ClassLayout(long, String)` | `(JLjava/lang/String;)V` |
| `String label()` | `()Ljava/lang/String;` |
| `int score(int bonus)` | `(I)I` |
| `static int created()` | `()I` |
| `static void main(String[])` | `([Ljava/lang/String;)V` |

`serialVersionUID` là compile-time constant `long` và thường có `ConstantValue: long 1l`, còn `created` được mặc định bằng 0 và tăng trong constructor. Không suy từ hai field cùng `static` rằng chúng phải có cùng attribute hoặc cùng code khởi tạo.

### Đọc một field và một method dưới dạng schematic

Đầu ra dưới đây **rút gọn để học cấu trúc**; không phải dump thực tế:

~~~text
fields_count: 3
  field_info:
    access_flags: ACC_PRIVATE | ACC_FINAL
    name_index:        #... -> Utf8 "name"
    descriptor_index:  #... -> Utf8 "Ljava/lang/String;"
    attributes: ...

methods_count: ...
  method_info:
    access_flags: ACC_PUBLIC
    name_index:        #... -> Utf8 "score"
    descriptor_index:  #... -> Utf8 "(I)I"
    attributes:
      Code -> bytecode, max_stack, max_locals, exception_table, ...
~~~

Mỗi `#...` là index vào constant pool, khác với các offset bytecode in ra bởi `javap -c`.

## 9. Trường hợp có thể gây bất ngờ trong file thật

### A. Giao diện kế thừa giao diện

~~~java
interface Root { void root(); }
interface Left extends Root { }
interface Right extends Root { }
interface Combined extends Left, Right { }
~~~

`Combined.class` có `super_class -> java/lang/Object` và `interfaces[] -> [Left, Right]`. `Root` là tổ tiên giao diện **gián tiếp**, không tự động xuất hiện trong danh sách direct superinterfaces. `Combined.methods[]` có thể **không khai báo method mới nào** vì `root()` được kế thừa.

### B. `enum` và annotation interface

Enum có class-level `ACC_ENUM`; những field đại diện từng enum constant cũng có `ACC_ENUM` **ở field flags**. Annotation interface có `ACC_INTERFACE`, `ACC_ABSTRACT` và `ACC_ANNOTATION`; các method mô tả phần tử annotation, khác với method instance thông thường của class. Khi gặp flags, hãy đọc theo **loại tệp** đang phân tích.

### C. Record và sealed class

~~~java
record Coordinate(int x, int y) { }

sealed interface Shape permits Circle, Rectangle { }
record Circle(double radius) implements Shape { }
record Rectangle(double width, double height) implements Shape { }
~~~

Đây là **ví dụ source Java 17+**, nhưng không phải chương trình có `main` để chạy trực tiếp. Với record, kiểm tra `Record` attribute, superclass `java/lang/Record`, component metadata, fields/accessor methods được compiler sinh. Với sealed interface, tra `PermittedSubclasses` attribute. **Không** tìm `ACC_RECORD` hoặc `ACC_SEALED` trong bảng class-level `access_flags` của JVMS `4.1`.

### D. Method do compiler tạo

Khi xem source generics/bridge, lambda hoặc nested class, `methods_count` không nhất thiết bằng số lời khai báo method trong source. Compiler có thể sinh method bổ trợ `ACC_SYNTHETIC`, `ACC_BRIDGE`, và các attributes metadata khác. Khi đọc `javap`, hãy tách **khai báo có thật trong class file** khỏi **khai báo bạn thấy trong source**.

### E. Module descriptor

`module-info.class` là cấu trúc đặc biệt. Nó dùng `ACC_MODULE`, `this_class = module-info`, `super_class = 0`, và `interfaces_count = fields_count = methods_count = 0`, đồng thời chứa `Module` attribute theo quy tắc đặc tả. Nếu công cụ parser nghĩ đây là class kế thừa `Object` thông thường hoặc luôn đòi có constructor, parser đang đọc sai trường hợp `ACC_MODULE`.

## 10. Những lỗi phổ biến khi phân tích hoặc viết parser

| Lỗi | Sửa cách hiểu |
| --- | --- |
| Coi số `this_class`/`super_class` là chuỗi tên đã mã hóa | Đó là **index** tới `CONSTANT_Class_info` trong constant pool |
| Cho rằng `super_class` bằng 0 nghĩa class không có cha trong mọi trường hợp | `Object` là class thông thường có zero; `module-info.class` có quy tắc đặc biệt |
| Nghĩ `interfaces[]` liệt kê mọi interface đã kế thừa qua superclass | Chỉ liệt kê **direct superinterfaces** của class/interface đang đọc |
| Nhìn `fields[]` thiếu field cha và kết luận object không có state đó | Field cha thuộc `fields[]` của superclass, không được copy vào class con |
| Coi `methods[]` là tất cả method mà object có thể gọi | Chỉ các method khai báo trong class; inherited/default methods nằm nơi định nghĩa |
| Diễn giải `0x0040` không xét cấu trúc | Là `ACC_VOLATILE` với field, `ACC_BRIDGE` với method |
| Coi `ACC_SUPER` là source `super` hoặc class đang extends lớp nào | Nó là cờ lịch sử của `invokespecial`; hãy đọc `super_class` để biết cha trực tiếp |
| Tìm `ACC_RECORD` hay `ACC_SEALED` trong JVMS ClassFile flags | Kiểm tra `Record` và `PermittedSubclasses` attributes |
| Mặc định field `static final` luôn có giá trị trong `ConstantValue` | Chỉ một số hằng phù hợp; static initialization khác có thể nằm ở `<clinit>` |
| Nghĩ `main` là trường đặc biệt của `ClassFile` bên ngoài `methods[]` | `main` là một `method_info` thông thường, được launcher chọn theo luật entry |
| Đồng nhất method descriptor với generic signature | Descriptor dùng kiểu JVM sau erasure; `Signature` có thể bổ sung metadata generic |
| Dùng `javap -c` để suy toàn bộ API và metadata | Kết hợp `javap -v -p` để thấy flags, descriptors, constant pool và attributes |

## 11. Quy trình thực hành và checklist đọc class file

Khi nhận một tệp `.class` bất kỳ, trình tự này giúp phân tích có hệ thống:

1. **Kiểm tra nguồn và phiên bản file:** `javap -verbose TênClass`, tìm `major version`, `minor version`, `this_class` và `flags`.
2. **Đọc danh tính/quan hệ kiểu:** xác nhận `this_class`, `super_class`, `interfaces_count` và thứ tự `interfaces[]`; nếu có nghi vấn kế thừa, mở thêm file superclass/interface.
3. **Đọc access flags đúng bảng:** class ở JVMS `4.1`; field ở `4.5`; method ở `4.6`. Không diễn giải bit mask xuyên bảng.
4. **Tách members:** `fields_count`/`methods_count` có bao nhiêu phần tử khai báo thực tế; so với source và các inherited members.
5. **Đọc descriptors:** chuyển ký hiệu `I`, `J`, `Ljava/lang/String;`, `[I`, `(I)I` sang kiểu dữ liệu tương ứng.
6. **Đọc attributes theo nơi chúng thuộc về:** `ConstantValue` ở field; `Code` ở method thực thi; `Signature` cho generics; `Record`, `PermittedSubclasses`, `Nest*` ở cấp loại theo đặc tả.
7. **Nếu lỗi link/verify/access:** đối chiếu class-file version, cấu trúc constant pool, quy tắc tổ hợp flags, descriptor và quyền truy cập runtime. Đừng suy từ source mà bỏ qua class-file thực tế.

Lệnh thường dùng (Java 17+):

~~~bash
javap -help
javap -p ClassLayout
javap -v -p ClassLayout
javap -c -p ClassLayout
javap -v -p Labeled
~~~

Nếu class nằm trong package hoặc JAR, sử dụng fully qualified name với classpath:

~~~bash
javap -v -p -classpath app.jar demo.ClassLayout
~~~

`javap` là công cụ quan sát class file, không cần chạy `main`. Với file không rõ nguồn, hãy ưu tiên kiểm tra offline và không tải/chạy các lớp chỉ để “xem thử”. Đầu ra `javap` không phải một bản dump nguyên byte, nhưng phù hợp để học các quan hệ cấu trúc nói trên.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `ClassLayout` extends `Base`, `Base` extends `Object`. `ClassLayout.class.super_class` là gì?  
**Đáp án:** `Base`. `Object` là ancestor gián tiếp của `ClassLayout`.

**Câu 2.** `ClassLayout` chỉ trực tiếp implements `Labeled` và `Serializable`. `interfaces_count` bằng bao nhiêu?  
**Đáp án:** 2, vì đếm các **direct superinterfaces** trong file của chính lớp đó.

**Câu 3.** Tại sao `ClassLayout.methods[]` không nhất thiết chứa `formatted()`?  
**Đáp án:** Vì `formatted()` là default method được khai báo trong `Labeled`; class kế thừa implementation qua giao diện, không cần một `method_info` cho method đó nếu không override.

**Câu 4.** Nếu thấy `0x0020` trong flags của class và method, nghĩa giống nhau không?  
**Đáp án:** Không. Class: `ACC_SUPER`; method: `ACC_SYNCHRONIZED`.

**Câu 5.** `private final String name` có descriptor và flag chính nào?  
**Đáp án:** Descriptor `Ljava/lang/String;`, các cờ `ACC_PRIVATE` và `ACC_FINAL`.

**Câu 6.** Vì sao `main([Ljava/lang/String;)V` vẫn nằm trong `methods[]`?  
**Đáp án:** Vì `main` là method của class; launcher chọn nó làm entry nhưng format class không tạo bảng `main` riêng.

**Câu 7.** Khi đọc `record` hoặc `sealed class`, tìm bit `ACC_RECORD`/`ACC_SEALED` có đúng không?  
**Đáp án:** Không trong bảng `ClassFile.access_flags` chuẩn. Xem `Record`/`PermittedSubclasses` attributes và metadata liên quan.

**Câu 8.** Vì sao generics `List<String>` thường hiện descriptor `Ljava/util/List;`?  
**Đáp án:** Descriptor JVM sử dụng kiểu erased; `Signature` attribute có thể lưu thêm thông tin kiểu generic.

## 13. Tài liệu chuẩn để tra cứu

- [JVMS Java SE 25 — `4.1` The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.1): toàn bộ khung class file, class `access_flags`, `this_class`, `super_class`, `interfaces`, `fields` và `methods`.
- [JVMS Java SE 25 — `4.2` Names](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.2): tên dạng nội bộ và tên nhị phân.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): field descriptors và method descriptors.
- [JVMS Java SE 25 — `4.5` Fields](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.5): `field_info`, flags, ràng buộc static/final/volatile và interface fields.
- [JVMS Java SE 25 — `4.6` Methods](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.6): `method_info`, flags, phương thức `<init>`/`<clinit>`.
- [JVMS Java SE 25 — `4.7` Attributes](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7): `Code`, `ConstantValue`, `Signature`, `Record`, `PermittedSubclasses` và các metadata khác.
- [Java `javap` manual, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): các tùy chọn `-v`, `-p`, `-c` và cách kiểm tra binary.
- [Java SE Specifications](https://docs.oracle.com/javase/specs/): chọn đúng release của JVMS nếu đang phân tích class file do JDK khác tạo ra.

**Ghi nhớ:** `access_flags` mô tả **tính chất loại đang khai báo**; `this_class`/`super_class`/`interfaces[]` mô tả **danh tính và quan hệ trực tiếp** thông qua constant pool; `fields[]` và `methods[]` mô tả **thành viên được khai báo tại chính loại đó**. Đọc cùng descriptors và attributes sẽ giúp bạn hiểu cấu trúc class file mà không đánh đồng nó với cú pháp source Java.