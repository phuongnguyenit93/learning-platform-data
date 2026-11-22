# Thuộc tính class file cho module, nestmate, record và sealed class

Một tệp Java `.class` chứa nhiều hơn danh sách phương thức và các chỉ thị bytecode. **Class-file attributes** lưu metadata bổ sung để JVM kiểm soát quyền truy cập, mô tả một module, nhận diện record components hoặc kiểm tra những lớp được phép kế thừa. Bốn nhóm quan trọng trong Java hiện đại là **`Module` / `ModulePackages` / `ModuleMainClass`**, **`NestHost` / `NestMembers`**, **`Record`** và **`PermittedSubclasses`**.

Các thuộc tính này dễ bị nhầm với modifier trong source. Chẳng hạn, Java dùng từ khóa `sealed`, nhưng không có bit `ACC_SEALED` tương ứng trong `access_flags`: class file dùng `PermittedSubclasses`. Tương tự, `record` được phản ánh qua `Record` attribute; `module-info.class` là class file dạng đặc biệt có bit `ACC_MODULE`, không phải lớp Java thông thường có `main`.

Bài học đặt mỗi thuộc tính trong cấu trúc class file, giải thích ràng buộc runtime, quan hệ với mã Java và cách đọc bằng `javap`. Ví dụ sử dụng **Java 17+** (bốn nhóm đều đã là tính năng chuẩn trong Java 17).

## 1. Nhìn attributes đúng vị trí trong `ClassFile`

Theo Java Virtual Machine Specification (JVMS), class file có dạng giản lược:

```text
ClassFile
├── magic, minor_version, major_version
├── constant_pool[]           // tên, kiểu, descriptor, symbol references...
├── access_flags              // ACC_PUBLIC, ACC_FINAL, ACC_MODULE, ...
├── this_class, super_class, interfaces[]
├── fields[]                  // field_info, có attributes riêng
├── methods[]                 // method_info, Code và attributes riêng
└── attributes[]              // thuộc tính cấp CLASS
    ├── Module | ModulePackages | ModuleMainClass
    ├── NestHost | NestMembers
    ├── Record
    ├── PermittedSubclasses
    └── các thuộc tính cấp class khác nếu có
```

Đây là mô hình minh họa các **khả năng**, không phải một class file thực tế nhất thiết chứa tất cả thuộc tính trên. `module-info.class` có ràng buộc riêng, và `NestHost` không đồng thời xuất hiện với `NestMembers` trên cùng class file.

Mỗi attribute nói chung có phần đầu:

```text
u2 attribute_name_index    // index trong constant pool, trỏ tới tên UTF-8
u4 attribute_length        // số byte nội dung, không tính 6 byte header
... payload ...            // cấu trúc khác nhau theo từng attribute
```

`u2` và `u4` là số nguyên không dấu theo độ rộng 2 hoặc 4 byte trong định dạng JVM, không phải kiểu khai báo field Java. `javap -v` đọc dữ liệu nhị phân và diễn giải ra tên/giá trị dễ hiểu; source file không lưu nguyên văn mọi modifier thành chuỗi Java.

### 1.1. Bảng bốn nhóm cần ghi nhớ

| Nhóm | Attribute trong class file | Dùng từ phiên bản class file chính thức | Ý nghĩa chính |
| --- | --- | --- | --- |
| Module | `Module`, `ModulePackages`, `ModuleMainClass` | **53.0 / Java 9** | Module descriptor và metadata về package/main class |
| Nestmate | `NestHost`, `NestMembers` | **55.0 / Java 11** | Khai báo quan hệ nest để kiểm tra quyền `private` |
| Record | `Record` | **60.0 / Java 16** | Khai báo record class và danh sách record components |
| Sealed class/interface | `PermittedSubclasses` | **61.0 / Java 17** | Liệt kê các loại được phép trực tiếp `extends` / `implements` |

Các mốc trên là **class-file format version mà attribute được định nghĩa chính thức**, không có nghĩa trước đó hoàn toàn không có preview source nào: record và sealed từng trải qua giai đoạn preview ở các JDK trước khi trở thành chuẩn. Preview class file có quy tắc phiên bản/`--enable-preview` riêng; không coi bytecode preview của bản trước tương thích tự động với bản sau.

### 1.2. Attribute và access flag khác nhau

- **Access flag** là bit trong `access_flags`. Ví dụ `ACC_MODULE` nhận diện module descriptor, còn `ACC_FINAL` thể hiện lớp không thể bị kế thừa.
- **Attribute** là cấu trúc có tên, độ dài, payload riêng. `Record` và `PermittedSubclasses` thuộc nhóm này.
- **`InnerClasses`** mô tả thông tin về nested/member classes để các công cụ hiểu cấu trúc nguồn; nó **không thay thế** `NestHost`/`NestMembers` trong quyết định quyền truy cập `private` ở JVM Java 11+.
- `Record` attribute không thay cho `fields[]` và `methods[]`; chúng vẫn tồn tại để mô tả field, constructor và accessor thực tế.

Mỗi attribute có **vị trí được phép xuất hiện**, số lần tối đa và giới hạn tương thích. Không thể chèn tùy tiện một `Module` attribute vào method và mong JVM hiểu đó là module.

## 2. Module attributes: mô tả ranh giới module ở cấp class file

Java Platform Module System (JPMS, Java 9) giới thiệu `module-info.java`. Biên dịch file này tạo **`module-info.class`**, một class file có cấu trúc dành riêng cho module descriptor.

Ví dụ source:

```java
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
    opens com.example.catalog.internal to com.example.consumer;
    uses com.example.catalog.spi.Provider;
    provides com.example.catalog.spi.Provider
        with com.example.catalog.internal.DefaultProvider;
}
```

Đây là **đoạn minh họa cú pháp module descriptor**, không thể tự biên dịch nếu thiếu các package, kiểu và module được tham chiếu. Ví dụ chạy đầy đủ xuất hiện ở mục 7.

Tương ứng, `Module` attribute ghi những nhóm dữ liệu:

| Thành phần trong `Module` | Vai trò |
| --- | --- |
| `module_name_index`, `module_flags`, `module_version_index` | Tên và metadata của module |
| `requires[]` | Module được yêu cầu, cờ như `transitive`/`static` khi áp dụng, thông tin version tùy chọn |
| `exports[]` | Package được xuất cho module khác, có thể xuất có điều kiện |
| `opens[]` | Package mở cho deep reflection theo điều kiện khai báo |
| `uses[]` | Service interface được khai báo sử dụng |
| `provides[]` | Service và danh sách provider implementations |

Tên module trong `Module` được tham chiếu qua mục `CONSTANT_Module_info` của constant pool; package qua `CONSTANT_Package_info`, khác `CONSTANT_Class_info` thường thấy ở tên lớp. `requires java.logging` là metadata quan hệ module, **không phải một lệnh bytecode gọi logging**.

### 2.1. `ACC_MODULE` và ràng buộc của `module-info.class`

Khi `ACC_MODULE` được bật:

- `this_class` biểu thị tên đặc biệt **`module-info`**.
- Không được đồng thời bật các access flags khác trong `access_flags`.
- `super_class`, số interfaces, fields và methods bằng **0**. `module-info.class` không có constructor Java thông thường, không có phương thức `main()` hay instance.
- Có **đúng một `Module` attribute** theo ràng buộc class file loại module; một số attributes khác được phép, trong đó có `ModulePackages` và `ModuleMainClass`.
- Cần class-file format tối thiểu **53.0** (Java 9).

Vì vậy, `module-info.class` **không phải** `com.example.ModuleInfo` có thể `new` hoặc gọi như class thông thường. JVM/toolchain dùng descriptor đó để hiểu **module**, cùng với quá trình resolution/layer configuration của JPMS.

### 2.2. `ModulePackages` khác `exports` thế nào?

`ModulePackages` ghi **danh sách package thuộc module** theo cơ chế của class-file attribute. Danh sách có thể bao gồm package **không được exports hay opens**, trong khi `Module.exports[]` chỉ nói về package **được phép truy cập theo quan hệ module**.

- `exports p.api`: cho phép truy cập các public types trong package được xuất từ các module đọc được module này.
- `opens p.internal`: mở khả năng deep reflection theo chính sách module, không biến toàn bộ kiểu thành public API compile-time.
- `ModulePackages`: phản ánh membership/package inventory; **không cấp quyền đọc, exports hay opens**.

`ModulePackages` **có thể không xuất hiện** trong `module-info.class` đơn giản do `javac` tạo. Các bước đóng gói/công cụ khác (chẳng hạn công cụ JAR hoặc runtime image) có thể bổ sung metadata cần thiết. **Không kết luận module không có package** chỉ vì không nhìn thấy attribute này.

### 2.3. `ModuleMainClass` có phải `Main-Class` của JAR?

`ModuleMainClass` là class-file attribute chỉ định **main class của module** nếu thông tin này được lưu trong module descriptor. Nó **khác vị trí lưu** với `Main-Class` trong `META-INF/MANIFEST.MF` của JAR truyền thống.

`module-info.java` **không khai báo main class bằng cú pháp `main` của module descriptor**. Thông tin này có thể được công cụ đóng gói bổ sung, chẳng hạn khi tạo modular JAR với tùy chọn main class phù hợp. Khi không có `ModuleMainClass`, một module vẫn có thể chạy bằng cách **chỉ rõ module và class chính**:

```bash
java --module-path out -m com.example.catalog/com.example.catalog.Main
```

Đây là cú pháp minh họa; chương trình chạy hoàn chỉnh với tên module khác được hướng dẫn ở mục 7. Không phải mọi `module-info.class` đều có `ModuleMainClass`, và không nên lẫn metadata class file với tên file/classpath của ứng dụng.

## 3. Nestmate attributes: quyền private của các lớp cùng nest

Trước Java 11, khi một nested class do `javac` biên dịch cần truy cập member `private` của enclosing class, compiler thường phải tạo **synthetic access methods** (ví dụ các bridge mang tên kiểu `access$000`) để bytecode có thể truy cập hợp lệ. Từ Java 11, JVM hiểu **nestmates**: các lớp thuộc **cùng một nest hợp lệ** được quyền truy cập private members của nhau.

### 3.1. Hai attributes bổ trợ nhau

- **`NestMembers`** nằm trong class file của **nest host**, chứa danh sách các lớp/interface được **phép tuyên bố** là thành viên của nest.
- **`NestHost`** nằm trong class file của **thành viên**, chỉ định class làm host.
- Host **tự là một thành viên** của nest do nó quản lý, không phải khai báo nó trong danh sách `NestMembers`.
- Một class file không được chứa đồng thời **`NestHost` và `NestMembers`**.

Ví dụ Java:

```java
public class Vault {
    private int secret = 42;

    static class Reader {
        int read(Vault value) {
            return value.secret;
        }
    }
}
```

Với `javac` Java 17:

```text
Vault.class
  NestMembers:
    Vault$Reader

Vault$Reader.class
  NestHost:
    class Vault
```

Đây là **sơ đồ các dòng liên quan**, không phải toàn bộ output cố định từ `javap -v`. `Reader` có thể truy cập `private int secret` của `Vault` nhờ quan hệ nest được JVM xác nhận, thay vì buộc compiler tạo accessor public/package-visible.

### 3.2. Không chỉ cần tên host trên một phía

JVM không tin vô điều kiện mọi class tự khai `NestHost: SomeHost`. Khi kiểm tra nest membership, các class phải thỏa điều kiện đặc tả như **cùng runtime package** và thông tin host–member được xác thực theo quy tắc `NestHost`/`NestMembers`.

**Runtime package** gắn với tên package **và defining class loader**; hai lớp có cùng dòng `package com.example;` nhưng bị định nghĩa bởi loader khác nhau chưa chắc thuộc cùng runtime package. Nestmate không mở quyền `private` xuyên loader/package một cách tùy ý.

Điều kiện tương trợ này ngăn một class file ngoài ý muốn giả danh là nestmate để đọc private field của class khác. Nếu bị phá vỡ, quá trình access check hoặc class loading/linking có thể thất bại bằng lỗi kiểu như `IllegalAccessError` hoặc `IncompatibleClassChangeError`, tùy trường hợp chính xác.

### 3.3. Khác với `InnerClasses` và `EnclosingMethod`

| Metadata | Câu hỏi nó trả lời |
| --- | --- |
| `InnerClasses` | Kiểu này được khai báo/lưu quan hệ nested/member như thế nào? |
| `EnclosingMethod` | Kiểu local/anonymous này được bao trong phương thức hay constructor nào? |
| `NestHost` / `NestMembers` | Những class nào được JVM công nhận cùng nest để kiểm tra `private` access? |

Vì vậy “class có tên `Outer$Inner`” **không tự động** có mọi quyền private; dấu `$` chỉ là tên được compiler thường sử dụng. Với Java 11+, **nest metadata hợp lệ** mới là nền tảng của quyền truy cập private giữa các class files.

Reflection cung cấp `Class.getNestHost()`, `getNestMembers()`, `isNestmateOf(...)` để quan sát kết quả nhìn từ JVM, không chỉ đọc các chuỗi tên trong source.

## 4. `Record` attribute: metadata của record components

`record` là cấu trúc ngôn ngữ được chuẩn hóa từ **Java 16**. Ví dụ:

```java
public record Point(int x, int y) {}
```

Biên dịch ra `Point.class` vẫn có **class file thông thường** với constructor, các private final instance fields `x`, `y`, accessor methods `x()`, `y()` và các method `equals`, `hashCode`, `toString` theo hợp đồng record.

Điểm đặc biệt là có **`Record` attribute** ở cấp `ClassFile`, biểu diễn danh sách record components. `Record` không chứa “mọi phương thức” hay toàn bộ source record; nó chủ yếu mô tả tên/kiểu và attributes đi kèm component.

### 4.1. Dữ liệu của một `Record` attribute

```text
Record_attribute
├── attribute_name_index
├── attribute_length
├── components_count
└── components[]
    ├── name_index
    ├── descriptor_index
    ├── attributes_count
    └── attributes[]   // ví dụ Signature, annotations...
```

Với `Point(int x, int y)`:

| Component | Name | JVM field descriptor |
| --- | --- | --- |
| 1 | `x` | `I` (int) |
| 2 | `y` | `I` (int) |

Với `record User(String name, long id) {}`, descriptors tương ứng là `Ljava/lang/String;` và `J`. Nếu component có kiểu generic, `Signature` attribute có thể bổ sung thông tin generic bên cạnh descriptor đã erasure.

**Record component** là khái niệm trong header của record. Nó có quan hệ với một field, accessor và constructor parameter tương ứng trong mô hình Java, nhưng **không phải** `field_info` hay `method_info`. Vì vậy Java Reflection có `getRecordComponents()` riêng thay vì buộc suy luận components từ tất cả declared fields.

### 4.2. Không có `ACC_RECORD` trong JVMS Java 17

Trong `access_flags` của class file ở JVMS 17 **không có bit `ACC_RECORD` chính thức**. Class của một Java record thường có `ACC_FINAL` theo quy tắc ngôn ngữ và kế thừa `java.lang.Record`; **`Record` attribute** đánh dấu cấu trúc record và components.

Cần phân biệt:

- `ACC_FINAL` không đủ để kết luận class là record; rất nhiều class final bình thường không phải record.
- Một class kế thừa `java.lang.Record` và có `Record` attribute trong class file phù hợp với cách records được biên dịch; **không suy ra record chỉ từ tên file hoặc từ `final`**.
- Method `Class.isRecord()` và `getRecordComponents()` là API thích hợp để quan sát record metadata tại runtime.
- Record component names/types nằm trong attribute theo hợp đồng class-file, không phụ thuộc vào việc có bật `javac -g` để giữ debug local variables.

### 4.3. Những gì `Record` KHÔNG thay thế

`Record` không “tự chứa bytecode” của canonical constructor, accessor, `equals`, `hashCode` hoặc `toString`. Compiler vẫn sinh method/field structures; JVM runtime/library phối hợp thực thi theo class và bytecode bình thường.

Trên các JDK phổ biến, code do `javac` sinh cho các method record có thể sử dụng `invokedynamic` và `java.lang.runtime.ObjectMethods` để hiện thực `equals`/`hashCode`/`toString`. Đây là **chi tiết codegen có thể quan sát**, không phải quy tắc “`Record` attribute chứa sẵn thuật toán hash”.

Không phải mọi annotation trên component được lưu cùng một vị trí: tùy `@Target`, annotation có thể áp dụng cho record component, field, accessor hoặc constructor parameter theo quy tắc ngôn ngữ. Khi inspect phải xem đúng vị trí metadata.

## 5. `PermittedSubclasses`: sealed class/interface cho phép ai kế thừa?

`sealed` trở thành tính năng chuẩn ở **Java 17**. Ví dụ:

```java
public sealed interface Shape permits Circle, Rectangle {}

final class Circle implements Shape {}

final class Rectangle implements Shape {}
```

Về mặt source, `permits Circle, Rectangle` nói hai loại này có thể **trực tiếp** `implements Shape`. Trong class file của `Shape`, metadata `PermittedSubclasses` chứa các tham chiếu `CONSTANT_Class_info` tương ứng.

```text
Shape.class
  PermittedSubclasses:
    Circle
    Rectangle
```

### 5.1. Không có bit `ACC_SEALED`

JVMS dùng **sự hiện diện của `PermittedSubclasses`** trên class/interface để thể hiện ranh giới sealed. Không có `ACC_SEALED` được định nghĩa như đối ứng trực tiếp của modifier `sealed`.

- `final class`: không cho lớp khác kế thừa, dùng `ACC_FINAL`; không được đồng thời có `PermittedSubclasses`.
- `sealed class/interface`: cho phép một danh sách cụ thể các **direct subclasses/direct subinterfaces**, dùng `PermittedSubclasses`.
- `non-sealed`: thể hiện sự mở rộng trở lại nhánh không còn bị giới hạn bởi parent sealed; **không có bit `ACC_NON_SEALED`**. Runtime biểu diễn các giới hạn và modifier hiện có theo cấu trúc class thông thường.

Một lớp được phép trực tiếp kế thừa sealed parent trong **mã nguồn Java** thường phải khai báo một trong `final`, `sealed` hoặc `non-sealed` (record mặc định final); những quy tắc source và bytecode của class cuối cùng có thể khác cách biểu đạt.

### 5.2. Direct, không phải mọi hậu duệ

Giả sử:

```java
sealed interface Command permits ReadCommand, WriteCommand {}

non-sealed class ReadCommand implements Command {}

final class WriteCommand implements Command {}

final class SpecialRead extends ReadCommand {}
```

`PermittedSubclasses` của `Command` chứa **ReadCommand** và **WriteCommand**, **không cần** chứa `SpecialRead` vì `SpecialRead` chỉ là cháu kế thừa qua một nhánh `non-sealed`.

Nếu một class không có trong `PermittedSubclasses` mà cố gắng **trực tiếp** kế thừa/implement sealed parent, JVM phải từ chối theo cơ chế class derivation/linking. Đó không chỉ là kiểm tra cú pháp của `javac`: metadata giúp ràng buộc cả khi JVM nạp class files đã được biên dịch/chỉnh sửa ngoài bộ compiler thông thường.

### 5.3. Ràng buộc module và package

Đối với source Java:

- Nếu sealed parent thuộc **named module**, các direct permitted subclasses phải ở **cùng module**.
- Nếu sealed parent thuộc **unnamed module**, các direct permitted subclasses phải ở **cùng package**.
- Điều kiện Java source còn yêu cầu các subtypes trực tiếp hợp lệ, accessibility và đặc điểm modifier tương ứng.

Trong runtime, JVM kiểm tra thêm quan hệ trực tiếp, tính hợp lệ của class-loader/runtime-module/package theo JVMS. Không thể chỉ chép tên vào `PermittedSubclasses` để vượt qua ranh giới module/package hoặc private access.

### 5.4. Reflection

Với một sealed class/interface, `Class.isSealed()` cho biết tình trạng sealed; `Class.getPermittedSubclasses()` trả mảng `Class<?>` cho các lớp được cho phép theo runtime. Đây không phải danh sách mọi đối tượng hoặc mọi subclass gián tiếp trong heap.

**Thứ tự duyệt mảng** có thể phản ánh metadata/runtime, nhưng bài học không nên dùng thứ tự như một quy tắc sắp xếp nghiệp vụ. Nếu cần kết quả ổn định theo tên, ứng dụng phải tự sắp xếp.

## 6. Một source Java 17 minh họa nestmate + record + sealed

Tạo tệp **`ClassAttributeDemo.java`**:

```java
public class ClassAttributeDemo {

    private final String secret = "OK";

    static class Reader {
        static String read(ClassAttributeDemo owner) {
            return owner.secret;
        }
    }

    sealed interface Shape permits Point, Circle {}

    record Point(int x, int y) implements Shape {}

    record Circle(int radius) implements Shape {}

    public static void main(String[] args) {
        ClassAttributeDemo owner = new ClassAttributeDemo();
        Point point = new Point(2, 3);

        System.out.println("nestmate=" + Reader.read(owner));
        System.out.println("record=" + point);
        System.out.println("record-components=" +
                Point.class.getRecordComponents().length);
        System.out.println("sealed=" + Shape.class.isSealed());
        System.out.println("permitted=" +
                Shape.class.getPermittedSubclasses().length);
    }
}
```

Biên dịch/chạy với **JDK 17+**:

```bash
javac ClassAttributeDemo.java
java ClassAttributeDemo
```

Stdout chính xác:

```text
nestmate=OK
record=Point[x=2, y=3]
record-components=2
sealed=true
permitted=2
```

**Vì sao đúng?**

1. `Reader` là nested class, có thể đọc `private String secret` của enclosing class nhờ quan hệ nestmate.
2. `Point` là record, có hai components `x` và `y`; mặc định `toString()` biểu diễn chúng dưới dạng `Point[x=2, y=3]`.
3. `Shape` là sealed interface; danh sách hai direct permitted implementations là `Point` và `Circle`.
4. Hai record implementations mặc định final theo source record, phù hợp quy tắc direct subclass của sealed parent.
5. Ví dụ không dùng module descriptor; ba nhóm metadata nest/record/sealed có thể xuất hiện trong class files trên **classpath**, độc lập với việc chương trình có named module hay không.

### 6.1. Các class files được tạo

Một compiler `javac` theo cách thường gặp sẽ tạo:

```text
ClassAttributeDemo.class
ClassAttributeDemo$Reader.class
ClassAttributeDemo$Shape.class
ClassAttributeDemo$Point.class
ClassAttributeDemo$Circle.class
```

Dấu `$` là ký pháp tên nhị phân thông thường cho nested types do compiler tạo, không phải một attribute. File cụ thể tùy compiler, và thông tin thuộc tính quan trọng nằm **bên trong** các file.

Đọc metadata:

```bash
javap -v -p ClassAttributeDemo
javap -v -p 'ClassAttributeDemo$Reader'
javap -v -p 'ClassAttributeDemo$Point'
javap -v -p 'ClassAttributeDemo$Shape'
```

Trên shell PowerShell hoặc POSIX, dấu nháy đơn bảo vệ `$` khỏi biến shell. Trong một số môi trường, `javap` chấp nhận cả tên nhị phân và đường dẫn file `.class`. Ở đây đã dùng tên nhị phân, bao gồm dấu `$`.

Dự kiến tìm:

| Inspect | Metadata quan trọng |
| --- | --- |
| `ClassAttributeDemo` | `NestMembers` liệt kê nested types do compiler nạp vào nest |
| `ClassAttributeDemo$Reader` | `NestHost: ClassAttributeDemo` |
| `ClassAttributeDemo$Point` | `Record` chứa components `x:I` và `y:I`; `NestHost` cho nested type |
| `ClassAttributeDemo$Shape` | `PermittedSubclasses` liệt kê `...$Point` và `...$Circle`; cũng có `NestHost` |
| `ClassAttributeDemo$Circle` | `Record` có component `radius:I` |

`javap` có thể bổ sung constant pool, `InnerClasses`, method code, bootstrap metadata, `SourceFile` và nhiều thông tin khác. **Không đòi output chỉ chứa những dòng liệt kê ở bảng**; đây là trọng tâm cần tìm.

### 6.2. Dòng metadata và runtime liên hệ thế nào?

```text
Mã nguồn Java 17
  │
  ├─ class Outer + nested Reader
  │     └─ ClassFile: NestMembers / NestHost
  │               └─ JVM dùng để xét private access
  │
  ├─ record Point
  │     └─ ClassFile: Record (component names + descriptors)
  │               └─ Reflection đọc getRecordComponents()
  │
  └─ sealed interface Shape
        └─ ClassFile: PermittedSubclasses
                  └─ JVM kiểm tra direct subtype được phép
```

Một class file có thể có **nhiều attributes cùng lúc**. `Point` vừa là **record** vừa là **nest member**, và là direct subtype được liệt kê trong `Shape`. `PermittedSubclasses` nằm tại **parent `Shape`**, không phải tại từng record implementer chỉ vì nó được phép.

## 7. Ví dụ Java 17 độc lập: tạo `module-info.class`

Để thấy nhóm `Module*` rõ ràng, dùng dự án nhỏ riêng có hai file:

```text
src/
├── module-info.java
└── demo/
    └── api/
        └── Hello.java
```

**`src/module-info.java`**:

```java
module demo.catalog {
    exports demo.api;
}
```

**`src/demo/api/Hello.java`**:

```java
package demo.api;

public class Hello {
    public static void main(String[] args) {
        System.out.println("module=" + Hello.class.getModule().getName());
    }
}
```

Ở thư mục chứa `src`, dùng JDK 17+:

```bash
javac -d out src/module-info.java src/demo/api/Hello.java
java --module-path out -m demo.catalog/demo.api.Hello
javap -v out/module-info.class
```

Stdout từ **lệnh `java`**:

```text
module=demo.catalog
```

Lệnh `javap` sinh output phân tích class file, trong đó tìm `ACC_MODULE`, `Module`, `module-info`, phần export `demo.api` và phụ thuộc `java.base` được compiler/module descriptor phản ánh. Hai lệnh `java` và `javap` không có “stdout chung” cố định, nên ở trên chỉ ghi rõ kết quả của lệnh chạy ứng dụng.

**Giải thích chi tiết:**

- `javac` sinh `out/module-info.class` và `out/demo/api/Hello.class`.
- `module-info.class` mang thông tin module `demo.catalog` với package được export là `demo.api`.
- `Hello.class` là class thông thường chứa method `main`; `module-info.class` không chứa chương trình chạy.
- `Hello.class.getModule().getName()` phản ánh module runtime của class, trả `demo.catalog` trong cách chạy này.
- Không bắt buộc có `ModuleMainClass`: lệnh `java -m demo.catalog/demo.api.Hello` đã chỉ rõ tên main class.
- Nếu `javap -v out/module-info.class` không hiển thị `ModulePackages`, điều đó không có nghĩa module không có package; attribute này có thể được công cụ đóng gói bổ sung.

Ví dụ này không cần Maven/Gradle, module path chỉ trỏ tới **thư mục output** của một module đã được biên dịch. Với ứng dụng nhiều module, bố cục thư mục/module path và các phần `requires` sẽ phức tạp hơn.

## 8. Đọc class file và nhận biết từng nhóm bằng `javap`

`javap` là công cụ đi kèm JDK, cho phép hiển thị thuộc tính theo dạng text. Một quy trình thực tế:

1. Xác định **đúng file `.class`** mà JVM/toolchain sẽ dùng. Trong JAR có thể có nhiều bản class theo `META-INF/versions/`.
2. Chạy `javap -v -p` cho class cụ thể. `-v` in thêm các attributes, `-p` gồm private members.
3. Kiểm tra `major version` và `minor version` để biết release class file. Class có `Record` được định nghĩa chuẩn từ 60.0, `PermittedSubclasses` từ 61.0.
4. Phân biệt **name của attribute** và **dữ liệu tham chiếu trong constant pool**: nhiều `#123` là index, không phải ID ổn định giữa hai lần biên dịch.
5. Nếu cần kiểm chứng runtime, dùng Reflection hoặc thử nạp/chạy chương trình trên JDK hỗ trợ; class file chỉ là một phần của hành vi thực tế.

Ví dụ đọc output rút gọn:

```text
ClassAttributeDemo$Shape
  major version: 61
  ...
  NestHost: class ClassAttributeDemo
  PermittedSubclasses:
    ClassAttributeDemo$Point
    ClassAttributeDemo$Circle
```

Đây là **trích xuất minh họa** để chỉ cách tìm thuộc tính, không cam kết thứ tự/indent/khoảng trắng chính xác trong mọi bản `javap`.

### 8.1. Cẩn thận khi tìm bằng chuỗi

Nếu `javap` chỉ in chữ “Record” trong **constant pool**, đó chưa chắc là bằng chứng đã có **`Record` attribute** ở cấp class; constant pool chứa rất nhiều chuỗi và tên dùng bởi code. Hãy xác nhận nó xuất hiện trong **attributes section** tương ứng và có cấu trúc components.

Tương tự:

- Chữ `sealed` trong source không tương đương một access flag có tên `ACC_SEALED`.
- Một `ClassFile` có `InnerClasses` không tự đảm bảo nest access.
- Tên `Module` xuất hiện như tên Java package/identifier trong bytecode không có nghĩa file là `module-info.class`.
- `Record` không phải “record object lưu trong constant pool”; nó là metadata cấp class.

## 9. Tương thích JDK và lỗi hay gặp

| Tình huống | Lý do | Cách chẩn đoán |
| --- | --- | --- |
| Chạy class Java 17 (`major 61`) trên JVM Java 11 (đến 55) | Class-file version quá mới | `java -version`, `javap -v`, `UnsupportedClassVersionError` |
| Chạy class record được biên dịch Java 16+ trên JDK cũ | Thiếu hỗ trợ định dạng/language/runtime cho record | Kiểm tra major, toolchain và `java.lang.Record` |
| Class file dùng `PermittedSubclasses` sai/không hợp lệ | JVMS yêu cầu cấu trúc attribute và direct subtype hợp lệ | `javap -v`, class generation, lỗi verification/linkage |
| Nested class truy cập `private` nhưng nest metadata không khớp | Nest membership không được JVM xác nhận | Kiểm tra `NestHost`, `NestMembers`, runtime package/loader |
| Một class file vừa có `NestHost` và `NestMembers` | Vi phạm ràng buộc định dạng | Sửa class generator/instrumentation |
| `module-info.class` chứa method/field bình thường | Vi phạm ràng buộc `ACC_MODULE` | Sửa compiler/generator; inspect `module-info.class` |
| Không thấy `ModulePackages` sau `javac` | Đây có thể là attribute tùy chọn do packaging bổ sung | Kiểm tra metadata cuối cùng trong JAR/image |
| Reflection thấy record components nhưng code không tìm field bằng tên dự đoán | Component, field và method là các cấu trúc khác nhau | Dùng `getRecordComponents()`; inspect class fields/methods |
| `Class.isSealed()` đúng nhưng danh sách subtype không đúng kỳ vọng | Metadata lưu **direct permitted subclasses**, không phải mọi hậu duệ | Inspect `PermittedSubclasses` ở parent |

**Ranh giới quan trọng:** các attributes này giúp JVM hiểu class, nhưng không làm một JDK cũ đột nhiên hiểu cú pháp hoặc class format mới. Một chương trình cần support Java 11 không thể giữ nguyên bytecode record/sealed Java 17 rồi chỉ thay cờ lúc chạy. Muốn hỗ trợ runtime cũ, phải thay đổi cách triển khai và biên dịch phù hợp.

### 9.1. Attributes chưa được runtime cũ biết đến

JVMS có quy tắc với các attributes định nghĩa mới: JVM nhận biết các predefined attributes theo version mà nó hỗ trợ. Tuy nhiên **không được suy ra** JVM cũ sẽ an toàn bỏ qua class mới chỉ vì attribute lạ: nó còn kiểm tra **major version**, cấu trúc class và các ràng buộc khác. Với class format mới, lỗi version thường xảy ra **trước khi** chương trình có thể tiếp tục xử lý metadata.

Vì vậy không có quy trình hợp lệ kiểu “xóa dòng `Record` khỏi file Java 17 rồi đổi major thành 55 để chạy Java 11”. Chỉnh bytecode nhị phân thủ công có thể phá hỏng constant pool, constructor contract, references và những yếu tố khác.

## 10. Các lỗi hiểu sai phổ biến

1. **“`record` được biểu diễn bằng flag `ACC_RECORD`.”** Không có flag chuẩn như vậy trong JVMS 17; `Record` là class-level attribute.
2. **“`sealed` được biểu diễn bằng flag `ACC_SEALED`.”** Không; `PermittedSubclasses` ở sealed parent xác định tập direct permitted subtypes.
3. **“Mọi nested class đều là nestmate chỉ vì tên có dấu `$`.”** Không; runtime áp dụng kiểm tra nest theo metadata và các điều kiện package/loader.
4. **“`NestMembers` cho phép class kế thừa nhau.”** Không; nó phục vụ quan hệ nest/private access, không phải inheritance.
5. **“`PermittedSubclasses` liệt kê tất cả descendants.”** Không; danh sách là direct subtypes được phép, nhánh `non-sealed` có thể có hậu duệ tiếp.
6. **“`Record` chứa bytecode của `equals`, `hashCode` và `toString`.”** Không; methods và code nằm ở cấu trúc phương thức/implementation.
7. **“`ModulePackages` là danh sách mọi package được export.”** Không; nó có thể gồm cả package nội bộ không export.
8. **“`ModuleMainClass` phải có mới chạy được module.”** Không; Java launcher có thể nhận main class tường minh.
9. **“`module-info.class` là một class thường có thể tạo object.”** Không; `ACC_MODULE` đi cùng các ràng buộc cấu trúc đặc biệt.
10. **“Nếu JVM thấy tên attribute mới thì chắc chắn sẽ nạp được bytecode mới.”** Không; major/minor và toàn bộ cấu trúc/đặc tả vẫn phải tương thích.
11. **“`InnerClasses` là cơ chế duy nhất cho truy cập private của nested class trong Java 17.”** Không; `NestHost`/`NestMembers` là nền tảng kiểm tra nestmate.
12. **“Mọi class file của một Java program đều có đủ bốn nhóm thuộc tính.”** Không; chỉ có metadata áp dụng cho cấu trúc đã biên dịch.

## 11. Bài tập thực hành và đáp án

**Câu 1.** `module-info.class` báo flag `ACC_MODULE` và có `Module` attribute. Nó có thể chứa `public static void main` không?

**Đáp án:** Không. Class file module descriptor có cấu trúc đặc biệt với `methods_count = 0`. Main class của ứng dụng, nếu có, là class khác; metadata `ModuleMainClass` cũng không tạo method `main`.

**Câu 2.** `Outer$Inner.class` có `NestHost: Outer`, nhưng class `Outer` không chấp nhận thành viên đó. Có được tự động truy cập `private` của `Outer` không?

**Đáp án:** Không. JVM cần xác thực quan hệ nest hợp lệ (kèm điều kiện package/loader). Một khai báo một phía không trao quyền private tùy ý.

**Câu 3.** Trong `record Book(String name, int pages) {}`, `Record` attribute có bao nhiêu components và descriptors nào?

**Đáp án:** Hai components: `name` có descriptor `Ljava/lang/String;`, `pages` có descriptor `I`. Fields/accessors tương ứng được mô tả ở những cấu trúc class-file khác.

**Câu 4.** Sealed interface `Shape permits Circle, Rectangle` có lớp `SpecialCircle extends Circle` ở nhánh `non-sealed Circle`. `PermittedSubclasses` của `Shape` có bắt buộc liệt kê `SpecialCircle` không?

**Đáp án:** Không. Chỉ hai direct permitted implementations `Circle` và `Rectangle`; `SpecialCircle` không phải direct subtype của `Shape`.

**Câu 5.** Nếu cần đọc danh sách record components qua Reflection, chọn `getDeclaredFields()` hay `getRecordComponents()`?

**Đáp án:** Dùng `getRecordComponents()` để lấy **record components**. `getDeclaredFields()` trả field declarations, một khái niệm khác.

**Câu 6.** Tại sao file có `major version: 55` không thể dựa vào `PermittedSubclasses` chuẩn Java 17 để đảm bảo sealed enforcement?

**Đáp án:** `PermittedSubclasses` được định nghĩa chính thức từ class-file version **61.0** (Java 17). JVM hiểu major 55 (Java 11) không có hợp đồng runtime sealed tương ứng.

**Câu 7.** Một `module-info.class` không có `ModulePackages` nhưng có `Module.exports[]`. Có phải lỗi biên dịch không?

**Đáp án:** Không nhất thiết. `ModulePackages` là metadata bổ sung có thể xuất hiện do packaging; `Module` có thể chứa thông tin exports dù không có `ModulePackages` trong file vừa biên dịch.

## 12. Ghi nhớ

- **`Module`** mô tả quan hệ module (requires/exports/opens/uses/provides), còn **`ModulePackages`** và **`ModuleMainClass`** là metadata module bổ sung. Chúng nằm trong class-file descriptor `module-info.class` với **`ACC_MODULE`**.
- **`NestHost` / `NestMembers`** giúp JVM xác nhận nestmates và cho phép truy cập private có kiểm soát; không thay thế logic kế thừa và không tự phát sinh từ tên `$`.
- **`Record`** lưu record components và thông tin liên quan; record vẫn có fields/methods/constructors thực sự. **Không có `ACC_RECORD` chuẩn ở JVMS 17**.
- **`PermittedSubclasses`** cho phép JVM xác minh **direct subtype** của sealed class/interface; **không có `ACC_SEALED`**.
- Đọc đúng cả **class-file version, constant pool, access flags và class-level attributes**, rồi xác nhận hành vi bằng `javap`/Reflection. Đó là cách nối các modifier Java hiện đại với ràng buộc mà JVM thực sự hiểu.

### Tài liệu tham khảo

- [JVMS Java SE 17 — ClassFile structure (`4.1`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 17 — Predefined attributes (`4.7`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7).
- [JVMS Java SE 17 — Module (`4.7.25`), ModulePackages (`4.7.26), ModuleMainClass (`4.7.27)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.25).
- [JVMS Java SE 17 — NestHost (`4.7.28), NestMembers (`4.7.29)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.28).
- [JVMS Java SE 17 — Record (`4.7.30`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.30).
- [JVMS Java SE 17 — PermittedSubclasses (`4.7.31`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.31).
- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
