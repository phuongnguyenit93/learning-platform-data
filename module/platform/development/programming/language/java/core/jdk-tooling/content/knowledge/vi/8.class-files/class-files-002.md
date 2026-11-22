# Class file structure

**Class file** là định dạng nhị phân chuẩn mà Java compiler tạo ra để JVM có thể nạp, kiểm tra và thực thi lớp. Tệp thường có phần mở rộng `.class`, nhưng bản thân định dạng không phải mã máy của một bộ xử lý cụ thể. Nó chứa bytecode, thông tin kiểu, bảng hằng số và metadata mô tả lớp, trường, phương thức cùng các thuộc tính liên quan.

Cấu trúc class file được định nghĩa trong *Java Virtual Machine Specification (JVMS)*. Nhờ có một định dạng thống nhất, bytecode được biên dịch trên một hệ điều hành có thể chạy trên hệ điều hành khác khi JVM đích hỗ trợ đúng phiên bản class file và các API/phụ thuộc mà chương trình cần.

## 1. Nhìn tổng thể một class file

Một class file có thứ tự thành phần cố định:

```text
ClassFile
├── magic
├── minor_version
├── major_version
├── constant_pool
├── access_flags
├── this_class
├── super_class
├── interfaces
├── fields
├── methods
└── attributes
```

Ý nghĩa từng phần:

| Thành phần | Vai trò |
|---|---|
| `magic` | Nhận diện tệp đúng định dạng class file |
| `minor_version`, `major_version` | Xác định phiên bản định dạng class file |
| `constant_pool` | Chứa tên lớp, tên trường/phương thức, chuỗi, kiểu dữ liệu và các tham chiếu hằng số |
| `access_flags` | Các cờ mô tả loại lớp và quyền truy cập |
| `this_class` | Chỉ mục trong constant pool xác định lớp đang được mô tả |
| `super_class` | Chỉ mục xác định lớp cha trực tiếp |
| `interfaces` | Danh sách interface mà lớp triển khai |
| `fields` | Danh sách trường được khai báo |
| `methods` | Danh sách phương thức và constructor |
| `attributes` | Metadata mở rộng ở cấp lớp, trường, phương thức hoặc mã bytecode |

Các trường số nguyên của định dạng class file được lưu theo thứ tự byte lớn trước (big-endian). Một số kiểu dữ liệu cơ bản trong đặc tả:

- `u1`: số nguyên không dấu dài 1 byte.
- `u2`: số nguyên không dấu dài 2 byte.
- `u4`: số nguyên không dấu dài 4 byte.

Các mục phức tạp hơn được xây dựng từ các trường này. Ví dụ, `attribute_length` là một `u4`, cho biết số byte trong phần dữ liệu của attribute.

## 2. Magic number và phiên bản

Bốn byte đầu tiên của class file là magic number:

```text
0xCAFEBABE
```

Magic number giúp JVM và công cụ phân tích nhận ra dữ liệu có phải class file hay không. Nếu tệp bị hỏng, bị cắt hoặc không phải class file, JVM có thể báo lỗi định dạng như `ClassFormatError`.

Ngay sau magic number là:

- `minor_version`: phiên bản phụ.
- `major_version`: phiên bản chính của định dạng class file.

Một số major version thường gặp:

| Java platform | Class file major version |
|---:|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, class file có major version 61 tương ứng với Java 17. Một JVM Java 17 không thể nạp class file yêu cầu major version cao hơn mà JVM đó hỗ trợ.

Từ Java 12, class file dùng minor version đặc biệt 65535 để đánh dấu bytecode phụ thuộc preview feature của đúng phiên bản Java đó. Muốn chạy loại class file này, runtime cần bật `--enable-preview` và phải cùng release tương ứng. Không nên coi minor version 65535 là một phiên bản Java thông thường.

## 3. Constant pool

`constant_pool` là bảng hằng số trung tâm của class file. Nhiều phần khác trong tệp không lưu tên lớp hoặc tên phương thức lặp đi lặp lại; chúng lưu chỉ mục trỏ đến mục thích hợp trong constant pool.

Ví dụ, phần mô tả lớp có thể tham chiếu một mục `CONSTANT_Class_info`, mục này lại trỏ đến mục `CONSTANT_Utf8_info` chứa tên lớp. Tên phương thức và descriptor cũng được tổ chức theo cách tham chiếu tương tự.

### 3.1. Cấu trúc bảng

Class file có trường `constant_pool_count` cho biết số lượng vị trí trong bảng, bao gồm vị trí 0 không được sử dụng. Các mục hợp lệ thường được đánh chỉ số bắt đầu từ 1.

Mỗi mục bắt đầu bằng một byte `tag` xác định loại mục, sau đó là dữ liệu riêng cho loại đó. Một số tag phổ biến:

| Tag | Loại mục | Nội dung khái quát |
|---:|---|---|
| 1 | `CONSTANT_Utf8` | Chuỗi theo định dạng Modified UTF-8 |
| 3 | `CONSTANT_Integer` | Hằng số số nguyên 32-bit |
| 4 | `CONSTANT_Float` | Hằng số dấu phẩy động 32-bit |
| 5 | `CONSTANT_Long` | Hằng số số nguyên 64-bit |
| 6 | `CONSTANT_Double` | Hằng số dấu phẩy động 64-bit |
| 7 | `CONSTANT_Class` | Tham chiếu tên lớp hoặc interface |
| 8 | `CONSTANT_String` | Tham chiếu chuỗi |
| 9 | `CONSTANT_Fieldref` | Tham chiếu trường |
| 10 | `CONSTANT_Methodref` | Tham chiếu phương thức lớp |
| 11 | `CONSTANT_InterfaceMethodref` | Tham chiếu phương thức interface |
| 12 | `CONSTANT_NameAndType` | Cặp tên và descriptor |
| 15 | `CONSTANT_MethodHandle` | Tham chiếu method handle |
| 16 | `CONSTANT_MethodType` | Descriptor của kiểu phương thức |
| 17 | `CONSTANT_Dynamic` | Hằng số động |
| 18 | `CONSTANT_InvokeDynamic` | Tham chiếu lời gọi động |
| 19 | `CONSTANT_Module` | Tên module |
| 20 | `CONSTANT_Package` | Tên package |

Các tag hợp lệ phụ thuộc phiên bản class file. Không phải mọi JDK cũ đều hiểu các loại constant pool được bổ sung trong những phiên bản mới.

### 3.2. Quan hệ tham chiếu

Ví dụ, một mục `CONSTANT_Methodref` không lưu toàn bộ tên lớp, tên phương thức và kiểu tham số thành một chuỗi duy nhất. Nó tham chiếu:

1. `class_index`: mục `CONSTANT_Class` chỉ lớp sở hữu phương thức.
2. `name_and_type_index`: mục `CONSTANT_NameAndType` mô tả tên và descriptor của phương thức.

Cách tổ chức này giúp nhiều thành phần dùng chung các chuỗi và thông tin kiểu. Khi đọc `javap -verbose`, bạn sẽ thấy các mục constant pool cùng chỉ mục của chúng.

`CONSTANT_Long` và `CONSTANT_Double` chiếm hai vị trí chỉ mục trong constant pool; vị trí tiếp theo sau chúng không thể được dùng như một mục độc lập. Đây là một chi tiết dễ gây lỗi khi tự viết bộ phân tích class file.

Chuỗi trong mục `CONSTANT_Utf8` dùng **Modified UTF-8** theo đặc tả class file, không hoàn toàn giống UTF-8 tiêu chuẩn. Khi dùng thư viện phân tích class file, hãy để thư viện xử lý encoding này thay vì tự giải mã byte bằng một giả định đơn giản.

## 4. Access flags, this_class và super_class

Sau constant pool là các trường mô tả lớp:

- `access_flags`: các cờ như public, final, interface, abstract, enum, annotation hoặc module.
- `this_class`: chỉ mục `CONSTANT_Class` xác định tên lớp đang được mô tả.
- `super_class`: chỉ mục `CONSTANT_Class` của lớp cha trực tiếp.

Một số cờ thường gặp:

| Cờ | Ý nghĩa |
|---|---|
| `ACC_PUBLIC` | Lớp có quyền truy cập public |
| `ACC_FINAL` | Lớp không thể được kế thừa |
| `ACC_SUPER` | Bật ngữ nghĩa gọi phương thức cha theo quy tắc JVM hiện đại |
| `ACC_INTERFACE` | Đây là interface |
| `ACC_ABSTRACT` | Lớp hoặc interface abstract |
| `ACC_ANNOTATION` | Đây là kiểu annotation |
| `ACC_ENUM` | Đây là kiểu enum |
| `ACC_MODULE` | Class file mô tả module |

Các cờ được phép và cách diễn giải còn phụ thuộc loại cấu trúc. Cùng một bit có thể có ý nghĩa khác nhau trong ngữ cảnh lớp, trường hoặc phương thức.

Với `java.lang.Object`, trường `super_class` bằng 0 vì đây là lớp gốc không có superclass. Với lớp thông thường, chỉ mục này tham chiếu lớp cha trực tiếp. `this_class` và `super_class` không lưu tên dạng văn bản trực tiếp; chúng trỏ tới constant pool.

## 5. Interfaces, fields và methods

### 5.1. Interfaces

Phần `interfaces_count` cho biết số interface mà lớp triển khai. Sau đó là mảng `interfaces`, mỗi phần tử là chỉ mục `CONSTANT_Class`.

Ví dụ:

```java
public class ReportService implements Runnable, AutoCloseable {
    @Override
    public void run() {
    }

    @Override
    public void close() {
    }
}
```

Class file của `ReportService` có các tham chiếu đến `Runnable` và `AutoCloseable` trong bảng interfaces. Các phương thức thực thi interface được mô tả trong bảng methods.

### 5.2. Fields

`fields_count` cho biết số trường được khai báo trong lớp. Mỗi `field_info` mô tả:

- Access flags như public, private, protected, static, final, volatile hoặc transient.
- `name_index`: tên trường trong constant pool.
- `descriptor_index`: descriptor biểu diễn kiểu trường.
- Danh sách attributes bổ sung, ví dụ `ConstantValue`, `Signature` hoặc annotation.

Ví dụ:

```java
public class Account {
    private long id;
    public static final int MAX_RETRY = 3;
}
```

Trường `id` có descriptor `J` (long); `MAX_RETRY` có descriptor `I` (int). Hằng số phù hợp có thể được biểu diễn bằng attribute `ConstantValue`.

### 5.3. Methods

`methods_count` cho biết số phương thức và constructor được mô tả. Mỗi `method_info` có:

- Access flags như public, private, static, final, abstract, synchronized hoặc native.
- `name_index`: tên phương thức; constructor dùng tên đặc biệt `<init>`, class initializer dùng `<clinit>`.
- `descriptor_index`: descriptor mô tả tham số và kiểu trả về.
- Danh sách attributes, thường gồm `Code` với phương thức có phần thân bytecode.

Ví dụ:

```java
public int add(int left, int right) {
    return left + right;
}
```

Descriptor của phương thức là:

```text
(II)I
```

Hai chữ `I` trong ngoặc là hai tham số kiểu int; chữ `I` sau ngoặc là kiểu trả về int.

Một số descriptor cơ bản:

| Kiểu Java | Descriptor |
|---|---|
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` | `V` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Descriptor là một phần quan trọng trong liên kết phương thức. Hai phương thức có cùng tên nhưng khác tham số sẽ có descriptor khác nhau. Kiểu generic thường không nằm trong descriptor JVM sau type erasure; thông tin generic có thể được giữ riêng trong attribute `Signature`.

## 6. Attribute: phần mở rộng của class file

Sau phần fields và methods là `attributes_count` và danh sách attributes ở cấp lớp. Mỗi attribute có cấu trúc chung:

```text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
```

- `attribute_name_index` trỏ đến mục `CONSTANT_Utf8` chứa tên attribute.
- `attribute_length` là độ dài phần dữ liệu.
- `info` chứa dữ liệu riêng theo loại attribute.

Attribute có thể xuất hiện ở nhiều cấp: class, field, method và trong Code attribute. Một số attribute quan trọng:

| Attribute | Mục đích |
|---|---|
| `SourceFile` | Ghi tên tệp nguồn gốc |
| `SourceDebugExtension` | Thông tin debug mở rộng |
| `InnerClasses` | Mô tả quan hệ lớp lồng nhau |
| `EnclosingMethod` | Mô tả lớp cục bộ/lớp vô danh nằm trong phương thức hoặc initializer nào |
| `NestHost`, `NestMembers` | Biểu diễn quan hệ nestmate |
| `Signature` | Lưu chữ ký generic |
| `ConstantValue` | Giá trị hằng số của trường phù hợp |
| `Exceptions` | Danh sách exception được khai báo trong throws |
| `RuntimeVisibleAnnotations` | Annotation cần giữ để runtime đọc được |
| `RuntimeInvisibleAnnotations` | Annotation không được yêu cầu giữ hiển thị ở runtime |
| `BootstrapMethods` | Thông tin bootstrap cho dynamic call site và dynamic constant |
| `Record` | Metadata cho record class |
| `PermittedSubclasses` | Danh sách lớp con được phép của sealed class |
| `Module` | Metadata khai báo module trong `module-info.class` |

Attribute cho phép định dạng class file mở rộng theo thời gian mà không cần thay đổi khung cơ bản. JVM bỏ qua một số attribute không bắt buộc mà nó không cần xử lý; các attribute có ý nghĩa bắt buộc theo đặc tả phải được xử lý đúng.

Không phải mọi comment trong mã nguồn đều xuất hiện trong class file. Comment thông thường bị loại bỏ khi biên dịch. Thông tin source, line number, local variable hoặc annotation chỉ tồn tại khi compiler tạo attribute tương ứng và theo retention/configuration của chúng.

## 7. Code attribute và bytecode của phương thức

Phương thức có phần thân thực thi thường chứa attribute `Code`. Đây là nơi lưu bytecode của phương thức.

Cấu trúc rút gọn:

```text
Code_attribute
├── max_stack
├── max_locals
├── code_length
├── code[]
├── exception_table
└── attributes
```

Các trường chính:

- `max_stack`: độ sâu tối đa của operand stack cần cho phương thức.
- `max_locals`: số slot cần cho biến cục bộ và tham số.
- `code_length`: số byte trong mảng bytecode.
- `code[]`: chuỗi lệnh JVM.
- `exception_table`: vùng bắt exception và vị trí handler.
- `attributes`: metadata của phần code, chẳng hạn line number, local variable và stack map.

JVM là máy stack-based. Nhiều lệnh đọc toán hạng từ operand stack, thực hiện phép toán rồi đẩy kết quả trở lại stack. Một số lệnh thao tác với local variable slots, tạo đối tượng, gọi phương thức, truy cập trường hoặc điều khiển luồng.

Ví dụ mã nguồn:

```java
public class MathBox {
    public static int add(int a, int b) {
        return a + b;
    }
}
```

Biên dịch và xem bytecode:

```sh
javac MathBox.java
javap -c MathBox
```

Kết quả bytecode cụ thể phụ thuộc JDK và cách biên dịch, nhưng phần thân thường có các lệnh tải hai biến cục bộ lên operand stack, cộng số nguyên và trả kết quả. Không nên suy luận rằng bytecode của mọi phiên bản compiler luôn giống hệt nhau về từng chỉ mục hoặc thứ tự lệnh.

Một số attribute thường nằm bên trong Code:

- `LineNumberTable`: ánh xạ offset bytecode với số dòng nguồn để debugger hiển thị vị trí gần đúng.
- `LocalVariableTable`: tên và phạm vi biến cục bộ nếu compiler tạo thông tin này.
- `LocalVariableTypeTable`: thông tin kiểu generic cho biến cục bộ khi có.
- `StackMapTable`: các frame phục vụ kiểm tra kiểu và xác minh luồng điều khiển.

Phương thức abstract và native không có phần thân bytecode thông thường, vì vậy không có Code attribute như phương thức concrete. Với method abstract, hành vi được triển khai bởi lớp con; với method native, phần thực thi nằm ngoài bytecode Java, thường qua JNI hoặc cơ chế native khác.

## 8. Bytecode verification và class loading

Khi JVM nạp một lớp, class file được xử lý theo các bước của cơ chế loading, linking và initialization. Ở mức khái quát:

1. **Loading:** tìm class file từ classpath, module path hoặc một class loader khác và tạo biểu diễn lớp trong JVM.
2. **Verification:** kiểm tra class file có hợp lệ và bytecode có tuân thủ các quy tắc an toàn kiểu của JVM hay không.
3. **Preparation:** cấp phát vùng nhớ cho biến static và gán giá trị mặc định theo quy tắc JVM.
4. **Resolution:** chuyển các tham chiếu symbolic trong constant pool thành tham chiếu trực tiếp khi cần.
5. **Initialization:** thực hiện khởi tạo lớp, bao gồm class initializer `<clinit>` khi có.

Verification kiểm tra nhiều điều kiện như cấu trúc lệnh, kiểu dữ liệu trên operand stack, tính hợp lệ của nhánh điều khiển và quan hệ giữa các frame. `StackMapTable` hỗ trợ quá trình này trên các phiên bản class file hiện đại.

Việc `javac` tạo class file thành công là một lớp kiểm tra; JVM vẫn thực hiện kiểm tra khi nạp và liên kết. Một class file hỏng hoặc được tạo thủ công không tuân thủ đặc tả có thể gây `ClassFormatError`, `VerifyError` hoặc lỗi liên kết khác.

Không nên dùng bytecode được sửa tùy tiện như một cách thay thế cho mã nguồn và quy trình build có kiểm soát.

## 9. Ví dụ thực hành: xem cấu trúc class file

Tạo `Sample.java`:

```java
public class Sample {
    private final String name;

    public Sample(String name) {
        this.name = name;
    }

    public String greeting() {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println(new Sample("JVM").greeting());
    }
}
```

Biên dịch:

```sh
javac -g -parameters Sample.java
```

Chạy chương trình:

```sh
java Sample
```

Kết quả:

```text
Hello, JVM
```

Xem các thành viên:

```sh
javap -p Sample
```

Xem bytecode:

```sh
javap -c -p Sample
```

Xem toàn bộ thông tin chi tiết:

```sh
javap -verbose -p Sample
```

Trong kết quả verbose, hãy tìm các phần:

- `Classfile`: đường dẫn và thông tin tệp.
- `minor version` và `major version`: phiên bản class file.
- `Constant pool`: các hằng số và tham chiếu.
- `flags`: access flags của lớp.
- `this_class`, `super_class`: lớp hiện tại và lớp cha.
- `fields`: trường `name`.
- `methods`: constructor, `greeting` và `main`.
- `Code`: bytecode, max stack, max locals và exception table.
- `LineNumberTable`, `LocalVariableTable`: thông tin debug nếu được sinh.

Các con số offset, constant pool index và bytecode cụ thể không phải giao diện ổn định để dựa vào giữa các phiên bản compiler. Hãy tập trung vào quan hệ và ý nghĩa cấu trúc thay vì ghi nhớ chỉ mục cố định.

## 10. Class file đặc biệt và tính năng ngôn ngữ hiện đại

Class file không chỉ mô tả lớp Java thông thường.

**Interface:** được đánh dấu bằng access flag phù hợp và có thể chứa method abstract, default, static hoặc private tùy phiên bản Java.

**Enum:** dùng metadata/cờ enum và thường được compiler sinh thêm các phương thức, trường hỗ trợ như `values()` hoặc `valueOf()`.

**Annotation:** là một dạng interface đặc biệt với metadata mô tả annotation element.

**Record:** class file chứa metadata `Record` mô tả các record component. Compiler cũng tạo các thành viên tương ứng theo quy tắc của record.

**Sealed class/interface:** attribute `PermittedSubclasses` ghi các lớp con được phép.

**Nested class:** các lớp lồng nhau được biểu diễn bằng class file riêng khi có định nghĩa lớp tương ứng; attribute `InnerClasses` và các metadata liên quan mô tả quan hệ giữa chúng.

**Module:** tệp `module-info.class` dùng để lưu khai báo module, có access flag `ACC_MODULE` và attribute `Module`. Đây không phải một lớp ứng dụng thông thường có phương thức main.

Các metadata trên giúp JVM và công cụ hiểu cấu trúc ngôn ngữ cấp cao sau khi đã chuyển thành định dạng class file.

## 11. Những giới hạn và lưu ý khi phân tích class file

- **Không phải bytecode là mã máy:** bytecode là lệnh của JVM; JVM có thể diễn giải hoặc JIT compile trong runtime.
- **Không có toàn bộ mã nguồn:** tên biến cục bộ và số dòng chỉ có nếu thông tin debug tương ứng được lưu. Comment thông thường không được giữ.
- **Generic bị type erasure:** descriptor dùng kiểu đã xóa; một số thông tin generic được lưu trong attribute `Signature`.
- **Tên nội bộ khác tên hiển thị:** tên lớp trong constant pool thường dùng dấu gạch chéo, ví dụ `java/lang/String`, trong khi tên Java dùng dấu chấm.
- **Class file phụ thuộc phiên bản:** JVM cũ có thể không hiểu major version hoặc tag/attribute mới.
- **Không nên sửa binary trực tiếp:** thay đổi sai offset, length, constant pool index hoặc stack map có thể làm class file không hợp lệ.
- **Không phải class file nào cũng có Code attribute:** interface method abstract và native method là các ví dụ không có thân bytecode thông thường.
- **Không phải mọi attribute đều có cùng phạm vi:** một attribute chỉ hợp lệ ở vị trí cụ thể theo JVMS.

Một bộ phân tích class file phải đọc đúng thứ tự, hiểu tag và phiên bản, xử lý chỉ mục constant pool, bỏ qua hoặc giải mã attribute theo đặc tả, và kiểm tra giới hạn độ dài. Nếu cần thao tác bytecode trong dự án, nên dùng thư viện chuyên dụng như ASM thay vì tự sửa byte array bằng các offset giả định.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassFormatError: Truncated class file` | Tệp bị cắt hoặc dữ liệu binary không đầy đủ | Tạo lại artifact từ build sạch; kiểm tra quá trình copy/download |
| `ClassFormatError: Bad magic number` | JVM nhận tệp không phải class file hợp lệ hoặc tệp đã bị hỏng | Xác minh classpath và nội dung artifact; không đổi phần mở rộng để giả làm class file |
| `UnsupportedClassVersionError` | Major version class file mới hơn JVM đang chạy | Dùng runtime đủ mới hoặc biên dịch theo release thấp hơn |
| `VerifyError` | Bytecode hoặc metadata xác minh không hợp lệ | Build lại bằng compiler chuẩn; nếu dùng bytecode instrumentation, kiểm tra frame và stack map |
| `NoClassDefFoundError` | Thiếu lớp phụ thuộc lúc nạp hoặc lớp không thể khởi tạo theo tình huống cụ thể | Kiểm tra classpath/module path, dependency và lỗi khởi tạo trước đó |
| `ClassNotFoundException` | Class loader không tìm được lớp theo tên yêu cầu | Kiểm tra tên lớp đầy đủ và vị trí output root |
| `javap` báo class not found | Classpath cho javap không đúng hoặc class file chưa được tạo | Dùng `javap -classpath out com.example.App` và xác nhận output root |
| Không thấy tên biến trong kết quả | Compiler không tạo LocalVariableTable | Biên dịch với `-g` và xem lại thông tin debug |
| Tệp `.class` cũ còn tồn tại | Compiler không dọn những class file không còn được sinh ở lượt mới | Chạy clean và biên dịch lại trong thư mục output rỗng |

## 13. Checklist đọc một class file

Khi phân tích một class file, hãy đi theo thứ tự:

1. Xác nhận magic number là `CAFEBABE`.
2. Đọc major/minor version để biết định dạng và khả năng tương thích.
3. Xem constant pool, tìm tên lớp, superclass, interface và các tham chiếu.
4. Đọc access flags để xác định loại lớp.
5. Kiểm tra interfaces, fields và methods.
6. Với method concrete, xem Code attribute và bytecode.
7. Kiểm tra attributes như Signature, Exceptions, annotations, InnerClasses hoặc Record.
8. Xem StackMapTable và thông tin debug khi cần phân tích verification hoặc debug.
9. Đối chiếu classpath/module path và dependency khi JVM không nạp được lớp.

Class file là cầu nối giữa mã nguồn Java và JVM. Khi nắm được magic number, phiên bản, constant pool, bảng lớp/trường/phương thức, Code attribute và metadata, bạn có thể đọc kết quả compiler, hiểu lỗi nạp lớp và phân tích bytecode có hệ thống thay vì chỉ nhìn tệp `.class` như một khối dữ liệu nhị phân.