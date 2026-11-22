# `NestHost` và `NestMembers` trong class file — nest-based access control từ Java 11

## 1. Vấn đề mà Java 11 giải quyết

Trong Java source, một class bên trong (`nested class`), class bao ngoài (`enclosing class`) và các class lồng cùng một class có thể tham chiếu đến thành viên `private` của nhau khi luật truy cập của ngôn ngữ cho phép.

Ví dụ:

```java
public class Example {
    private static int secret = 42;

    static class Reader {
        static int read() {
            return secret;  // Hợp lệ trong Java source.
        }
    }
}
```

Mỗi class được biên dịch thành **một class file riêng**, chẳng hạn `Example.class` và `Example$Reader.class`. Ở các target cũ hơn Java 11, JVM không hiểu quan hệ truy cập `private` giữa hai class file khác nhau theo nghĩa này; `javac` thường phải tạo **synthetic accessor methods** để thực hiện lời gọi qua một trung gian có mức truy cập phù hợp.

Từ **Java 11, JEP 181 — Nest-Based Access Control**, JVM hiểu khái niệm **nest**: một tập các class/interface cho phép truy cập trực tiếp vào `private` members của nhau. Quan hệ ấy được khai báo bằng **hai thuộc tính ở cấp `ClassFile`**:

- **`NestHost`:** class thành viên khai báo **ai là host của nest mà nó thuộc về**.
- **`NestMembers`:** class host công bố **những class/interface nào được phép làm thành viên nest của nó**.

Điểm quyết định: **khai báo hai chiều và JVM xác thực quan hệ**, không phải một class tùy tiện tự nhận mình thuộc nest của class khác. Cả hai thuộc tính bắt đầu từ **class-file major version 55.0**, tương ứng Java 11, và tiếp tục có hiệu lực trong JVM hiện hành.

**Trọng tâm bài:** định dạng hai attributes, quan hệ host–members, điều kiện xác thực membership, liên hệ với quyền `private`, cách dùng `javap -v` và `Class.getNestHost/getNestMembers/isNestmateOf`, binary compatibility khi build/mix class files, và cách phân biệt nest metadata với metadata lồng nhau truyền thống.

> **Bản chất:** `NestHost` và `NestMembers` là **binary metadata được JVM sử dụng cho access control**, không phải Java annotations hay một API cho phép mọi class trong cùng package đọc `private` của nhau.

## 2. Hình dung một nest

Giả sử source:

```java
public class Vault {
    private static String rootSecret = "ROOT";

    static class Reader {
        private static String ownSecret = "READER";
    }

    static class Writer {
        private static String ownSecret = "WRITER";
    }
}
```

Thông thường `javac --release 11 Vault.java` sinh:

```text
Vault.java
   |
   +-- Vault.class           (nest host)
   +-- Vault$Reader.class    (nest member)
   +-- Vault$Writer.class    (nest member)
```

Metadata về mặt ý nghĩa:

```text
Vault.class
  NestMembers:
    Vault$Reader
    Vault$Writer

Vault$Reader.class
  NestHost: class Vault

Vault$Writer.class
  NestHost: class Vault
```

JVM cho phép `Vault`, `Vault$Reader` và `Vault$Writer` là **nestmates**, nên `private` có thể được truy cập từ bytecode của những class ấy theo luật truy cập khác liên quan. Với Java source, bộ biên dịch vẫn kiểm tra chính sách của ngôn ngữ; việc JVM hỗ trợ private nestmate access không biến các biểu thức Java source vốn bị cấm thành hợp lệ.

**Host cũng là một thành viên** của nest do nó host, nhưng `NestMembers` trên host thường **chỉ liệt kê các class/interface còn lại**, không cần lặp chính host. Một class **không có** `NestHost` được coi là nest host của chính nó. Nếu cũng không liệt kê `NestMembers`, nó là một **singleton nest**.

### Quan hệ một chiều không đủ

```text
Reader  --NestHost--> Vault
Vault   --NestMembers--> Reader, Writer
Writer  --NestHost--> Vault

=> Reader, Vault, Writer có thể cùng một nest nếu điều kiện
   run-time package và xác thực metadata được thỏa mãn.
```

Nếu chỉ có `Reader.NestHost=Vault` nhưng `Vault` **không** liệt kê `Reader`, quan hệ **không được chấp nhận**. Đây là ràng buộc bảo mật quan trọng: người tạo một class file không thể chỉ ghi `NestHost` trỏ tới class có dữ liệu riêng tư rồi nhận quyền đọc `private`.

## 3. `ClassFile` chứa attributes ở đâu?

Cấu trúc `ClassFile` theo JVMS `4.1`:

```text
ClassFile {
    u4             magic;               // 0xCAFEBABE
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
```

`NestHost` và `NestMembers` nằm trong **`attributes[]` của toàn `ClassFile`**, không nằm trong một `field_info` hoặc `method_info` cụ thể.

Một attribute nói chung:

```text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
```

`attribute_name_index` trỏ tới `CONSTANT_Utf8_info` trong constant pool, chứa tên literal `"NestHost"` hoặc `"NestMembers"`. Các field còn lại của hai loại attribute được trình bày ở phần 4 và 5.

| Thành phần | Ý nghĩa | Không nên nhầm |
| --- | --- | --- |
| `major_version=55` | Bytecode format Java 11 | Không đồng nghĩa Java source phải có cú pháp mới |
| `constant_pool` | Chứa symbolic references, class names, attribute-name UTF8... | Không phải danh sách permission tự nó |
| `ClassFile.attributes[]` | Metadata của toàn class/interface | Không phải runtime annotation |
| `NestHost` | Thành viên tuyên bố host | Không phải superclass |
| `NestMembers` | Host công bố authorized members | Không phải danh sách mọi subclass |
| `InnerClasses` | Metadata phản ánh một quan hệ class/member trong source/binary | Không thay thế nest authorization |
| `EnclosingMethod` | Metadata của local/anonymous class với lexical enclosing method nếu có | Không định nghĩa nest host |

Class-file format sử dụng **big-endian** cho các giá trị nhiều byte `u2`, `u4`. Với `u2`, giá trị là unsigned 16-bit; `u4` là unsigned 32-bit. Tính các offset phải theo **cấu trúc đang parse**, vì constant pool chứa các entry với độ dài khác nhau.

## 4. Định dạng nhị phân `NestHost_attribute`

Theo JVMS `4.7.28`:

```text
NestHost_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 host_class_index;
}
```

Diễn giải:

| Field | Kích thước | Ràng buộc / ý nghĩa |
| --- | --- | --- |
| `attribute_name_index` | 2 byte | Index hợp lệ vào constant pool; entry phải là `CONSTANT_Utf8_info("NestHost")` |
| `attribute_length` | 4 byte | **Bằng 2**, vì payload chỉ có một `u2` |
| `host_class_index` | 2 byte | Index hợp lệ vào constant pool, entry kiểu `CONSTANT_Class_info` chỉ tới host được khai báo |

**Tổng kích thước cấu trúc `NestHost_attribute`:** 2 + 4 + 2 = **8 byte** trong vùng attributes (chưa tính constant pool entries). Trường `attribute_length` mang giá trị **2**, vì nó **không** tính 6 byte header của attribute.

### Ví dụ đọc qua `javap -v`

Giả sử file `NestAttributesDemo$A.class` được biên dịch Java 11:

```text
NestHost: class NestAttributesDemo
```

Dòng này là cách `javap` hiển thị tham chiếu từ `host_class_index` đến class host. Một số bản `javap` có thể có khác biệt cách trình bày chi tiết constant-pool index, nhưng ý nghĩa attribute không đổi.

### Điều `NestHost` không làm

- Không chứa public/private key hay dữ liệu xác thực của một người dùng.
- Không đổi Java superclass hoặc inheritance graph.
- Không đồng nghĩa class có tên `$Inner`; nest host được quyết định qua metadata, không suy luận từ ký tự `$`.
- Không biến các class **cùng package** thành nestmates nếu host chưa cho phép.
- Không bảo đảm JVM đã tải hoặc xác minh host ngay khi class file được đọc; điều kiện có thể được xử lý khi cần access control/reflection.

## 5. Định dạng nhị phân `NestMembers_attribute`

Theo JVMS `4.7.29`:

```text
NestMembers_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 number_of_classes;
    u2 classes[number_of_classes];
}
```

Diễn giải:

| Field | Kích thước | Ràng buộc / ý nghĩa |
| --- | --- | --- |
| `attribute_name_index` | 2 byte | Chỉ tới `CONSTANT_Utf8_info("NestMembers")` |
| `attribute_length` | 4 byte | **2 + 2 × number_of_classes** |
| `number_of_classes` | 2 byte | Số entries nằm trong mảng `classes[]` |
| `classes[]` | 2 byte mỗi entry | Mỗi giá trị là index vào `CONSTANT_Class_info` của một member được host cho phép |

Nếu host liệt kê **hai thành viên**, `number_of_classes=2`, `attribute_length=2+2×2=6`. Tổng số byte cấu trúc attribute là **2+4+6=12**, không bao gồm constant pool.

Nếu có n members, phần payload không phải một array chứa trực tiếp các chuỗi binary name; nó chứa **n constant-pool indexes**, mỗi index dẫn tới `CONSTANT_Class_info` và sau đó tới tên class/interface.

### Vì sao `NestMembers` thường không liệt kê chính host?

Host vốn đã thuộc nest của chính nó theo định nghĩa. `NestMembers` dùng để **authorize các class/interface khác** tuyên bố mình thuộc host. Khi bạn gọi `getNestMembers()` ở Java reflection, **host lại xuất hiện** trong mảng kết quả, vì API trả **toàn bộ thành viên của nest** chứ không sao chép nguyên văn mảng indices trong attribute.

### Các điều kiện cấu trúc

JVMS quy định:

- Trong một `ClassFile`, mỗi attribute **`NestHost`** có **tối đa một** instance.
- Tương tự, `NestMembers` có **tối đa một** instance.
- **Không được có cả `NestHost` và `NestMembers` trong cùng một `ClassFile`**. Host không đồng thời khai rằng nó là member của một host khác.
- Hai attributes là những thuộc tính được định nghĩa **từ class-file version 55.0 (Java 11)**.
- `NestMembers` liệt kê những class/interface mà host **cho phép yêu cầu membership**; **điều kiện ngược lại vẫn phải thỏa**: mỗi member thực sự cần có `NestHost` trỏ tới đúng host và phải cùng run-time package.
- Các entries không đáp ứng điều kiện của JVMS bị bỏ qua khi kiểm tra access tương ứng; không có chuyện host liệt kê một tên bất kỳ là đủ để cấp private access.
- Một host có `NestMembers` không cần biến danh sách thành quan hệ source-level inner classes; metadata có ý nghĩa security trực tiếp với VM.

**Không dùng một tool sửa file class để chèn/sửa `NestMembers` mà thiếu kiểm tra bảo toàn quan hệ hai chiều.** Lỗi có thể xuất hiện ở runtime khi resolving các lời truy cập `private`, dù việc đóng gói JAR hoặc biên dịch phía caller trước đó có vẻ thành công.

## 6. Quy trình JVM xác nhận nestmate access

JVMS `5.4.4 — Access Control` mô tả một **nestmate test** khi bytecode của class D tham chiếu một `private` field/method được khai báo bởi class C.

Về mặt khái niệm:

```text
isNestmate(D, C):

  Nếu D == C:
      thành công

  Host_D = resolveNestHost(D)
  Host_C = resolveNestHost(C)

  Nếu Host_D và Host_C là CÙNG một run-time class/interface:
      thành công
  Ngược lại:
      từ chối private access
```

Trong bước `resolveNestHost(M)`:

1. Nếu `M` **không có** `NestHost`, thì host của `M` là chính `M`.
2. Nếu có `NestHost`, JVM resolve `host_class_index` thành một class/interface `H`.
3. Kiểm tra `H` và `M` nằm trong **cùng run-time package**.
4. Kiểm tra `H` có attribute `NestMembers`.
5. Kiểm tra attribute `NestMembers` của `H` **liệt kê đúng tên class/interface M**.
6. Nếu mọi điều kiện thỏa, `H` là host hợp lệ. Nếu không, membership không hợp lệ; quá trình access sẽ thất bại theo cơ chế JVMS.

### "Cùng run-time package" không đơn giản là cùng chuỗi package

Trong JVMS, một run-time package phụ thuộc **tên package và defining class loader**. Hai class cùng `package demo;` nhưng do **hai defining class loaders khác nhau** tạo ra là thuộc **hai run-time packages khác nhau**. Các constraints của module layer có thể liên quan vì mỗi run-time package thuộc một run-time module tương ứng.

Vì vậy, không thể qua mặt private access bằng cách:

```text
Tạo một class tên "demo.Vault$Injected"
Đặt package là "demo"
Viết NestHost trỏ tới "demo.Vault"
Load qua class loader khác
```

Một cái tên giống nhau không có nghĩa là cùng runtime identity. Ngoài class loader, host phải **authorize membership** qua `NestMembers`; đây là rào cản chính của cơ chế này.

### Khi metadata không nhất quán sẽ ra lỗi gì?

Theo JVMS Java 11, khi resolve nest host có attribute `NestHost` mà host không cùng run-time package, hoặc không có `NestMembers`, hoặc không liệt kê member, kiểm tra có thể dẫn tới **`IncompatibleClassChangeError`**. Khi một truy cập `private` thực tế bị từ chối, bạn cũng có thể quan sát **`IllegalAccessError`**; class này là một **subclass của `IncompatibleClassChangeError`**.

Các lỗi loading/linking khác như `NoClassDefFoundError` hoặc `ClassFormatError` có thể xảy ra tùy loại metadata sai/missing class file và thời điểm JVM phát hiện. Không nên ghi cứng mọi lỗi nest phải đúng một exception duy nhất.

**Quan trọng:** điều kiện được đánh giá khi cần resolution/access control; không bắt buộc JVM từ chối mọi class file có thông tin không khớp **ngay lúc class được load**, vì có nhiều thời điểm liên kết hợp lệ. Một chương trình có thể chạy đến đoạn sử dụng private reference rồi mới phát sinh lỗi.

## 7. Ví dụ Java 11 hoàn chỉnh: host, member, sibling và class cùng package

Tạo file **`NestAttributesDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public final class NestAttributesDemo {
    private static final String SECRET = "HOST";

    private static String readA() {
        return A.hidden();
    }

    static final class A {
        private static String hidden() {
            return "A";
        }

        static String readHost() {
            return SECRET;
        }

        static String readB() {
            return B.hidden();
        }
    }

    static final class B {
        private static String hidden() {
            return "B";
        }
    }

    public static void main(String[] args) {
        System.out.println("crossPrivate=" + readA() + ","
                + A.readHost() + "," + A.readB());

        System.out.println("host=" +
                A.class.getNestHost().getSimpleName());

        System.out.println("hostOfHost=" +
                NestAttributesDemo.class.getNestHost().getSimpleName());

        System.out.println("siblingNestmates=" +
                A.class.isNestmateOf(B.class));

        System.out.println("nearbyNestmate=" +
                A.class.isNestmateOf(Nearby.class));

        System.out.println("members=" +
                Arrays.stream(NestAttributesDemo.class.getNestMembers())
                        .map(Class::getName)
                        .sorted()
                        .collect(Collectors.joining(",")));

        System.out.println("nearbyHost=" +
                Nearby.class.getNestHost().getSimpleName());
    }
}

class Nearby { }
```

**Chạy với JDK 11+**:

```bash
javac --release 11 NestAttributesDemo.java
java NestAttributesDemo
```

**Stdout đã kiểm chứng bằng biên dịch `--release 11` và chạy:**

```text
crossPrivate=A,HOST,B
host=NestAttributesDemo
hostOfHost=NestAttributesDemo
siblingNestmates=true
nearbyNestmate=false
members=NestAttributesDemo,NestAttributesDemo$A,NestAttributesDemo$B
nearbyHost=Nearby
```

### Giải thích

- `readA()` là private method ở host, đọc `A.hidden()` là private method ở member. `A.readB()` đọc private method ở **sibling** `B`. `A.readHost()` truy cập private field của host. Ba hướng đều hợp lệ vì chung nest và Java source cho phép.
- `A.class.getNestHost()` trả `NestAttributesDemo.class` vì `A` ghi `NestHost` trỏ đến host.
- Host tự là nest host của chính nó: `getNestHost()` trên `NestAttributesDemo.class` trả chính class đó.
- `A.class.isNestmateOf(B.class)` là `true` do hai class có cùng host hợp lệ.
- `Nearby` có cùng **unnamed package** trong ví dụ nhưng **không** được liệt kê trong `NestMembers` và không khai `NestHost`. Nó là singleton nest của chính nó; `A.class.isNestmateOf(Nearby.class)` là `false`.
- `getNestMembers()` có host và hai members; ví dụ **sắp xếp theo tên** để stdout ổn định. Javadoc không bảo đảm thứ tự của các phần tử sau host.
- Không dùng `getNestMembers().length == 3` làm phép xác thực mọi chương trình lồng nhau; số class trong nest có thể bao gồm local/anonymous/interface khác nhau tùy source/bytecode.

## 8. Xem trực tiếp `NestHost` và `NestMembers` bằng `javap -v`

Sau `javac --release 11 NestAttributesDemo.java`, trong thư mục chứa các `.class`:

```bash
javap -v NestAttributesDemo
javap -v 'NestAttributesDemo$A'
javap -v 'NestAttributesDemo$B'
javap -p NestAttributesDemo
```

Với PowerShell cũng dùng chuỗi được quote bằng dấu nháy đơn để dấu `$` của binary name không bị diễn giải như biến:

```powershell
javap -v NestAttributesDemo
javap -v 'NestAttributesDemo$A'
javap -v 'NestAttributesDemo$B'
javap -p NestAttributesDemo
```

Phần trích quan trọng từ output đã kiểm tra:

```text
# javap -v NestAttributesDemo
major version: 55
...
NestMembers:
  NestAttributesDemo$B
  NestAttributesDemo$A

# javap -v 'NestAttributesDemo$A'
major version: 55
...
NestHost: class NestAttributesDemo
```

Vị trí và thứ tự hiển thị `NestMembers` phụ thuộc phiên bản compiler và thứ tự nội bộ, **không phải thứ tự bắt buộc của JVMS**. Không cần bytecode inspector phải in A trước B. Để test set membership, so sánh tên như một tập hợp hoặc sắp xếp rõ ràng.

### Kiểm tra hướng truy cập trực tiếp

Trong `javap -c -p NestAttributesDemo`, method `readA()` có thể hiển thị lời gọi trực tiếp kiểu:

```text
invokestatic  #... // Method NestAttributesDemo$A.hidden:()Ljava/lang/String;
```

Với class `NestAttributesDemo$A`, code đọc `SECRET` và gọi `B.hidden()` có symbolic references liên quan. `javac --release 11` **không cần sinh synthetic accessor chỉ để vượt `private` qua nest** trong trường hợp này.

Để xem methods và modifiers (bao gồm compiler-generated ones):

```bash
javap -p NestAttributesDemo
javap -p 'NestAttributesDemo$A'
```

**Không dùng sự vắng mặt của mọi method có `ACC_SYNTHETIC` để kết luận build lỗi hay đúng:** compiler vẫn có thể tạo synthetic members cho **những mục đích khác**. Điều được chứng minh ở ví dụ là direct private nestmate access có thể thực hiện **mà không cần accessor nhân tạo kiểu `access$000` cho chính việc truy cập này**.

### Lưu ý khi lọc log

`javap -v` có thể hiển thị tên `NestHost`/`NestMembers` trong **constant pool** và trong **attribute section**. Đừng xem một dòng literal `Utf8 NestHost` trong constant pool là bằng chứng attribute đã được gắn đúng vị trí; xem cả phần attributes thực tế.

## 9. Đọc `major_version`: Java 11 khác Java 8 ở chỗ nào?

| Java target | Major version | Nest attributes do compiler có thể phát ra? | Cơ chế private cross-class thường gặp |
| --- | --- | --- | --- |
| `--release 8` | **52** | **Không có `NestHost/NestMembers`** | Synthetic accessors ở một số pattern lồng nhau |
| `--release 10` | **54** | Chưa có hai attributes mới | Synthetic accessors khi cần |
| `--release 11` | **55** | **Có** | JVM hiểu nestmates và cho direct private access |
| JDK hiện hành với target mới hơn | Lớn hơn 55 | Cơ chế nest tiếp tục có hiệu lực | Các compiler/runtime hiện đại sử dụng nest metadata theo nhu cầu |

**Đây không phải lời khuyên tiếp tục nhắm Java 8:** chỉ là đối chiếu lịch sử để hiểu vì sao metadata `NestHost/NestMembers` tồn tại trong class file hiện đại và vì sao bytecode cùng một source có thể khác nhau giữa build targets.

Ví dụ Java 8 nhỏ, chỉ để khảo sát:

```java
public final class LegacyAccessDemo {
    private static String secret = "HOST";

    static class Inner {
        static String read() {
            return secret;
        }
    }

    public static void main(String[] args) {
        System.out.println(Inner.read());
    }
}
```

Biên dịch riêng vào thư mục `legacy` để không lẫn class files:

```bash
javac --release 8 -d legacy LegacyAccessDemo.java
javap -p -classpath legacy LegacyAccessDemo
javap -v -classpath legacy LegacyAccessDemo
```

Trên compiler thử nghiệm, `javap -p` hiện:

```text
public final class LegacyAccessDemo {
  private static java.lang.String secret;
  public LegacyAccessDemo();
  public static void main(java.lang.String[]);
  static java.lang.String access$000();
  static {};
}
```

Và `javap -v` có:

```text
major version: 52
```

Không có `NestMembers` vì target 8 không thể mang thuộc tính định nghĩa từ version 55. Compiler tạo `access$000()` làm trung gian đọc private field của host. Java 11 trực tiếp hóa quyền truy cập tương ứng ở VM level bằng metadata mới.

**Không trộn compile output từ hai target tùy tiện**: một số class file mang nest attributes, một số không, dù có cùng package và tên host. Nếu cần tương thích với Java 8 runtime, phải dùng build target hỗ trợ Java 8 và chấp nhận cơ chế codegen tương ứng. Một `class` có major 55 **không chạy được trên JVM chỉ hỗ trợ tối đa major 52**.

## 10. `InnerClasses`, `EnclosingMethod` và Nest attributes không phải một thứ

Trước Java 11, class file đã có `InnerClasses` và `EnclosingMethod`. Nhưng đây **không phải bằng chứng một class được cấp private nestmate access** theo JVMS mới.

| Attribute/API | Ý nghĩa | Có được dùng để authorize `private` nest access? |
| --- | --- | --- |
| `InnerClasses` | Thông tin về nested/member class declarations, outer/inner name/access flags | **Không trực tiếp** |
| `EnclosingMethod` | Thông tin lexical enclosing method/constructor của local/anonymous class | **Không** |
| `NestHost` | Member chỉ định nest host | **Có, kết hợp host authorization** |
| `NestMembers` | Host công bố authorized members | **Có, kết hợp member declaration** |
| `Class.getDeclaringClass()` | Liên hệ declaration của member class theo reflection | **Không đồng nghĩa nest host** |
| `Class.getEnclosingClass()/getEnclosingMethod()` | Liên hệ lexical enclosing context | **Không đồng nghĩa nest authorization** |
| `Class.getNestHost()/getNestMembers()/isNestmateOf()` | Quan sát nest runtime đã được JVMS/API xác định | Phù hợp kiểm tra nest, subject to loading/validation |

**Điểm quan trọng:** một class local hoặc anonymous có thể **nằm trong nest** dù không được `getDeclaredClasses()` của outer class liệt kê. Ngược lại, tên chứa `$`, quan hệ superclass hay nằm cùng package không tự tạo membership.

### Ví dụ Java 11: member, local và anonymous

Lưu **`NestLocalDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestLocalDemo {
    private static int hidden = 7;

    interface Named {
        int read();
    }

    static class Member {
        static int read() {
            return hidden;
        }
    }

    public static void main(String[] args) {
        class Local implements Named {
            public int read() {
                return hidden;
            }
        }

        Named anonymous = new Named() {
            public int read() {
                return hidden;
            }
        };

        System.out.println("local=" + new Local().read());
        System.out.println("anonymous=" + anonymous.read());

        System.out.println("declared=" +
                Arrays.stream(NestLocalDemo.class.getDeclaredClasses())
                        .map(Class::getName)
                        .sorted()
                        .collect(Collectors.joining(",")));

        System.out.println("nestMembers=" +
                Arrays.stream(NestLocalDemo.class.getNestMembers())
                        .map(Class::getName)
                        .sorted()
                        .collect(Collectors.joining(",")));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 NestLocalDemo.java
java NestLocalDemo
```

**Stdout đã kiểm chứng:**

```text
local=7
anonymous=7
declared=NestLocalDemo$Member,NestLocalDemo$Named
nestMembers=NestLocalDemo,NestLocalDemo$1,NestLocalDemo$1Local,NestLocalDemo$Member,NestLocalDemo$Named
```

Giải thích:

- `getDeclaredClasses()` chỉ trả **member classes/interfaces đã khai báo** theo contract reflection (ở đây `Member` và `Named`); nó không trả local class `Local` hay anonymous class.
- `getNestMembers()` bao gồm host và những nestmates mà compiler đã ghi metadata, ở đây có `NestLocalDemo$1` (anonymous) và `NestLocalDemo$1Local` (local).
- Tên synthetic/numeric của local/anonymous classes là chi tiết compiler; không hard-code vào logic ứng dụng.
- `javap -v NestLocalDemo` có thể hiện cả local/anonymous trong `NestMembers`.
- **Số thành viên và tên binary** có thể thay đổi nếu bạn chỉnh source hoặc compiler phát ra các class khác; ngữ nghĩa chính là quan hệ nest chứ không phải literal tên.

## 11. Reflection API của `java.lang.Class`: ba phương thức từ Java 11

### `Class<?> getNestHost()`

Trả class/interface được coi là **host** của nest chứa receiver. Nếu một class không có `NestHost`, host là chính nó; đối với array classes, primitive types và `void`, kết quả là chính `Class` được hỏi.

```java
Class<?> host = NestAttributesDemo.A.class.getNestHost();
System.out.println(host == NestAttributesDemo.class); // true
```

**Edge case:** theo Javadoc Java 11, nếu có linkage error khi truy xuất host hoặc host không liệt kê receiver là member, `getNestHost()` có thể coi receiver là một **singleton nest** và trả `this`. Đừng xem kết quả fallback ấy là “class file chắc chắn hợp lệ cho mọi private access”.

### `Class<?>[] getNestMembers()`

Trả các class/interface nằm trong nest. Phần tử **đầu tiên** của mảng là nest host, còn thứ tự các phần tử còn lại **không được quy định**; có thể có duplicates theo API. Với class đơn lẻ, array, primitive, `void`, kết quả có thể chỉ chứa `this`.

```java
Class<?>[] members = NestAttributesDemo.class.getNestMembers();
System.out.println(members[0] == NestAttributesDemo.class); // true
```

Method có thể ném `LinkageError` nếu gặp vấn đề khi loading/validating nest member hoặc host, theo Javadoc. Dùng nó trong công cụ inspection nên bắt/report lỗi rõ ràng, không nuốt rồi tự khẳng định metadata hợp lệ.

### `boolean isNestmateOf(Class<?> other)`

Trả `true` khi hai class/interface thuộc **cùng nest** và `false` nếu không. Trong ví dụ:

```java
boolean sameNest = NestAttributesDemo.A.class
        .isNestmateOf(NestAttributesDemo.B.class);
boolean differentNest = NestAttributesDemo.A.class
        .isNestmateOf(Nearby.class);

System.out.println(sameNest);      // true
System.out.println(differentNest); // false
```

Đừng hiểu `isNestmateOf` là “class có cùng package”, “class là superclass/subclass” hoặc “class có cùng dấu `$` trong tên”. Nó dựa trên identity của nest host theo JVM.

### Reflection không phải bytecode parser

`Class.getNestMembers()` không trả các `u2` constant-pool indexes hoặc giá trị thô `attribute_length`. Nó trả **runtime Class objects sau resolution/validation**. Muốn xem định dạng thô, dùng `javap -v` hoặc công cụ bytecode/class-file parser hiểu major version và JVMS tương ứng.

Trong JDK mới hơn, có API `java.lang.classfile` (ra đời sau Java 11) hỗ trợ thao tác class files; **đừng đưa nó vào chương trình phải chạy bằng `--release 11`**. Đối với mục tiêu bài này, `javap -v` và `Class` APIs của Java 11 là đủ.

## 12. Class-file metadata không tương ứng 1:1 với cú pháp Java

Trong source, lập trình viên tạo nested/member/local/anonymous classes theo những quy tắc ngôn ngữ. Trong class file, JVM vận hành trên **classes và interfaces** độc lập, được liên kết bằng metadata.

Do đó có một vài ranh giới cần biết:

- Compiler Java thường chọn outermost enclosing class làm host cho các nested/local/anonymous classes liên quan, nhưng **khái niệm nest là thuộc JVM metadata**, không thể chỉ phân tích dấu `$` trong binary name để suy ra chắc chắn.
- `NestMembers` host có thể liệt kê các classes không xuất hiện trong `Class.getDeclaredClasses()` vì local/anonymous không phải member classes theo ngữ nghĩa reflection.
- Một subclass của `Vault` nằm ở class file khác **không tự trở thành nestmate** chỉ vì inheritance. `protected`/`public` accessibility là cơ chế khác.
- Một top-level class `Nearby` trong cùng package **không tự gia nhập nest** do cùng package.
- Chỉ sửa `InnerClasses` để nói `Nearby` là nested class **không cấp private access**; JVM dựa vào `NestHost`/`NestMembers` và run-time package.
- Với class-loader transformer hoặc bytecode weaving, phải bảo đảm metadata host/member nhất quán khi rename/move/repackage các classes. Không còn đủ để sửa mỗi `InnerClasses`.

**Bảo mật:** việc một class có thể đọc `private` của class khác theo metadata không có nghĩa tất cả mã nguồn cùng module có quyền đó. Nest membership là một phần của JVM access control, còn JPMS module boundaries, reflection access, `MethodHandles.Lookup` privileges và class-loader identity có quy tắc liên quan nhưng không thể xem là được “tự động mở”.

## 13. Tại sao metadata hai chiều cần thiết cho an toàn?

Giả định một kẻ nào đó có thể cung cấp bytecode `Attacker.class` và muốn đọc `private` của `Vault.class`. Nếu JVM chỉ kiểm tra `Attacker.NestHost=Vault`, kẻ đó có thể tự khai mình là member.

Java 11 yêu cầu thêm sự đồng ý của host qua `Vault.NestMembers`:

```text
Attacker.class:
  NestHost: Vault

Vault.class:
  NestMembers: [Vault$Reader, Vault$Writer]

Kiểm tra:
  Attacker có mặt trong Vault.NestMembers?  NO
  => Không thể chứng minh Attacker thuộc nest của Vault
  => Không có quyền private nestmate access
```

Kể cả nếu đổi tên `Attacker` thành `Vault$Attacker`, **tên binary không cấp quyền**. Nếu host không liệt kê nó thì vẫn bị từ chối.

Nếu hai class được nạp qua **different defining class loaders**, dù package string giống nhau, điều kiện **same run-time package** cũng không thỏa. Đây là một lý do cần quan tâm class-loader identity khi chạy plugin architectures, application servers và instrumentation agents.

### Cẩn thận: host có thể cho phép member tùy ý trong cùng run-time package

Metadata về nest là **binary contract**. Khi một hệ thống có quyền xây dựng cả host lẫn member class files, nó có thể chủ động tổ chức nest khác với hình dạng source thông thường nếu đáp ứng JVMS. Vì vậy không nên dựa vào một giả định “chỉ class có tên `Outer$Inner` mới được nestmate”.

Ở mức bảo vệ thư viện, không tin một artifact bytecode không được kiểm chứng, và đừng chạy một agent/plugin không tin cậy có quyền thay toàn bộ class files của hệ thống. Nest verification không thay thế code signing, artifact integrity, supply-chain controls hoặc sandbox/isolation.

## 14. Chẩn đoán `IllegalAccessError`/`IncompatibleClassChangeError` sau khi build

Một tình huống thường gặp với code generation hoặc incremental build:

1. Biên dịch `Host` cùng `Host$Member` trên Java 11; host có `NestMembers`, member có `NestHost`.
2. Sau đó deploy một bản `Host.class` cũ hoặc khác nhưng vẫn dùng `Host$Member.class` từ build mới.
3. Member gọi trực tiếp một `private` method/field của host.
4. Khi JVM kiểm tra quyền, metadata thiếu/không nhất quán, nên member không có quyền truy cập đó và có thể gặp linkage/access error.

Trong một phép thử có chủ đích: giữ lại `BrokenNest$Inner.class` đã biên dịch Java 11 nhưng thay `BrokenNest.class` bằng một file cùng tên không liệt kê nest member. Bản gốc cho:

```text
value=42
```

Sau khi trộn artifacts, bản thử phát sinh lỗi dạng:

```text
java.lang.IllegalAccessError:
  class BrokenNest$Inner tried to access private field
  BrokenNest.secret
  ... current type is not listed as a nest member
```

Đây là kết quả của một **fixture trộn class files không tương thích**, không phải một cách thiết kế ứng dụng. `IllegalAccessError` kế thừa từ `IncompatibleClassChangeError`; message chính xác là implementation-dependent và không nên viết test phụ thuộc toàn bộ chuỗi message.

### Cách điều tra thực tế

1. Xem class nào trực tiếp gây lỗi trong stack trace, class nào là target field/method `private`.
2. Với **đúng JAR/build đang chạy**, trích xuất/inspection `javap -v -classpath your.jar 'package.Host'` và `'package.Host$Inner'`.
3. Kiểm tra `major version`: class file target 11 hay 8, compiler version, multi-release JAR variant nếu có.
4. Kiểm tra member có `NestHost` trỏ tới host; host có `NestMembers` liệt kê đúng member; cả hai ở cùng run-time package/defining loader.
5. Kiểm tra classpath/module path có duplicate classes/JARs, shaded packages, incremental build stale output hoặc code transformers chưa xử lý attributes.
6. Clean-build **toàn bộ** module/JAR liên quan với một target phù hợp; tránh chỉ rebuild riêng member mà vẫn giữ host cũ.
7. Chạy lại unit/integration tests trong class-loader/module environment đúng deployment; không chỉ chạy một nguồn `.java` độc lập.
8. Không sửa lỗi bằng cách biến tất cả fields thành `public`, bỏ access checks hoặc vô hiệu hóa module integrity. Đó là workaround làm yếu encapsulation và che nguyên nhân.

**Lưu ý công cụ:** một số bytecode tools cũ không hiểu class-file version 55 hoặc không bảo toàn `NestHost/NestMembers` khi rewrite. Chỉ dùng phiên bản thư viện bytecode hỗ trợ target runtime và giữ nguyên/điều chỉnh đầy đủ metadata có ý nghĩa bảo mật.

## 15. Hướng dẫn kiểm tra bằng `javap` trong JAR/package

Các lệnh hữu ích:

```bash
# Class-path chứa đúng artifact đã deploy
javap -v -classpath app.jar 'com.example.Outer'

javap -v -classpath app.jar 'com.example.Outer$Inner'

# Chỉ xem declarations, kể cả private/synthetic members
javap -p -classpath app.jar 'com.example.Outer'

# Xem bytecode của các method
javap -c -p -classpath app.jar 'com.example.Outer$Inner'
```

Với class có **module** hoặc runtime image, cần chỉ rõ module path phù hợp cho `javap`. Không đoán JAR phiên bản nào đang được nạp nếu có nhiều class loaders: hãy lấy bằng chứng đường dẫn class resource/module/class loader từ deployment diagnostics, rồi inspection đúng binary.

### Những gì cần ghi nhận trong bug report

- JDK/runtime và compiler version; `javac --release` đã dùng.
- `major version` của host và members.
- `NestMembers` trên host, `NestHost` trên các members.
- Binary names và defining class loaders (đặc biệt khi plugin/container).
- JPMS module names nếu module boundaries liên quan.
- Stack trace đầy đủ và private access đang được resolving.
- Quy trình build/shading/instrumentation và thời điểm artifacts có thể bị trộn.
- Nếu binary được build cho Java 8: đây là **khác target**, đừng đòi có nest attributes trong class-file major 52.

Không đính kèm binary chưa kiểm duyệt hoặc dữ liệu nhạy cảm trong bug report công khai.

## 16. Những vấn đề thường bị nhầm

| Nhận định | Kết luận đúng |
| --- | --- |
| `NestHost` là superclass | **Sai**; đó là host của nest, không phải inheritance |
| `NestMembers` liệt kê mọi subclass | **Sai**; liệt kê authorized nest members |
| Một class có `NestHost` là tự được truy cập `private` | **Sai**; host phải liệt kê nó và điều kiện runtime package phải hợp lệ |
| Cùng tên package là đủ | **Sai**; cần cùng run-time package (package name + defining loader) và reciprocity |
| Mỗi class trong package đều là nestmate | **Sai**; `Nearby` cùng package vẫn độc lập |
| `InnerClasses` xác nhận nest membership | **Sai**; nó là metadata về nesting, không phải hai chiều permission |
| `EnclosingMethod` có thể thay `NestHost` | **Sai** |
| `getDeclaredClasses()` và `getNestMembers()` giống nhau | **Sai**; local/anonymous có thể thuộc nest nhưng không phải declared members |
| Host có `NestMembers` thì cũng phải có `NestHost` | **Sai**; JVMS cấm cả hai attribute trên cùng class |
| Host phải được liệt kê trong `NestMembers` | **Không**; host tự là member của nest mình |
| `NestMembers` trên host quyết định thứ tự reflection array | **Không**; JVM API chỉ bảo đảm host ở vị trí đầu, thứ tự phần sau không định nghĩa |
| Class file Java 8 có thể ghi `NestHost` hợp lệ | **Không**, attribute được định nghĩa từ major 55 |
| Tạo `Outer$Injected.class` cùng package sẽ có private access | **Không**; tên và package không đủ |
| `getNestHost()` luôn throw với metadata sai | **Không hẳn**; Java 11 reflection có hành vi fallback về singleton trong một số trường hợp |
| `javap -v` có chữ NestHost trong constant pool là đủ | **Không**; phải thấy attribute thực ở class-level |
| Nestmates cho phép mọi reflective access | **Không**; reflection và JPMS có luật accessibility riêng |
| Java 11 không cần compiler-generated methods nào | **Không**; chỉ loại bỏ nhu cầu accessors cho một số private nest accesses |
| Compile `--release 11` thì JDK 8 runtime chạy được | **Không**; major 55 vượt quá mức hỗ trợ của Java 8 |
| Thay đổi `NestHost` bằng binary patch luôn được chấp nhận | **Không**; JVM kiểm tra reciprocity/run-time package và các constraint |
| Một member của nest có thể làm host của nest thứ hai bằng cách ghi cả hai attributes | **Không**; cùng ClassFile không được có cả hai |

## 17. Câu hỏi tự kiểm tra — có đáp án

**1.** `NestHost` và `NestMembers` xuất hiện từ class-file major version nào?

**Đáp án:** **55.0**, Java 11. Cả hai là attributes trong `ClassFile.attributes[]`.

**2.** `NestHost_attribute.attribute_length` có giá trị bao nhiêu và vì sao?

**Đáp án:** **2**, vì payload chỉ gồm một `u2 host_class_index`; sáu byte header không được tính vào `attribute_length`.

**3.** Nếu `NestMembers` có 3 entries, `attribute_length` bao nhiêu?

**Đáp án:** `2+2×3=8` byte (gồm `u2 number_of_classes` và 3 `u2` indices). Tổng cả header của attribute là 14 byte.

**4.** Class `A` ghi `NestHost=B` nhưng `B.NestMembers` không có `A`. `A` có thể đọc `private` của `B` nhờ `NestHost` không?

**Đáp án:** Không. JVM đòi hỏi xác thực hai chiều và cùng run-time package; thiếu host authorization dẫn tới access/linkage failure.

**5.** Một class có `NestMembers` nhưng không có `NestHost` thì host là ai?

**Đáp án:** Chính class ấy. Nó là host của nest chứa các authorized members trong `NestMembers`.

**6.** Một class không có cả hai attributes là nestmate với ai?

**Đáp án:** Nó là một singleton nest của chính mình (không tự có nestmate class khác). JVM vẫn coi class ấy có nest host là chính nó.

**7.** `getNestMembers()` có bắt buộc trả theo thứ tự ghi trong attribute không?

**Đáp án:** Không. Javadoc bảo đảm phần tử 0 là host; các phần tử khác có thứ tự không xác định và duplicates được phép.

**8.** `getDeclaredClasses()` có liệt kê anonymous/local classes trong nest không?

**Đáp án:** Không theo ý nghĩa declared member class. Ví dụ `NestLocalDemo` cho thấy `getNestMembers()` có anonymous/local, còn `getDeclaredClasses()` không có chúng.

**9.** Có thể xem `NestHost` bằng lệnh nào?

**Đáp án:** `javap -v 'NestAttributesDemo$A'` (hoặc tên binary fully-qualified). Với PowerShell/POSIX shell, quote tên để tránh `$` expansion.

**10.** Vì sao `Class.getNestHost()` trên member có thể trả chính nó dù class file khai host khác?

**Đáp án:** Theo Java 11 API, trong một số lỗi linkage hoặc host không công nhận membership, reflection coi class đó là singleton nest và trả `this`; đây không phải bằng chứng metadata gốc đã hợp lệ.

**11.** Java 11 cho phép `A` đọc `B.privateMethod()` dù không có quan hệ subclass, khi nào?

**Đáp án:** Khi `A` và `B` thực sự thuộc cùng nest được JVM công nhận và quy tắc Java source/runtime liên quan cho phép. Quan hệ này không yêu cầu inheritance.

**12.** `Nearby` cùng package với `NestAttributesDemo` nhưng `isNestmateOf` là `false` vì sao?

**Đáp án:** Cùng package chỉ là một điều kiện cần cho membership; `Nearby` không có `NestHost` hợp lệ tới host và không được host authorize.

**13.** Hai class cùng package name nhưng defining class loaders khác nhau có được coi là cùng run-time package không?

**Đáp án:** Không. Run-time package được quyết định bởi **tên package và defining loader**.

**14.** `InnerClasses` và `NestMembers` khác nhau thế nào?

**Đáp án:** `InnerClasses` mô tả quan hệ declaration/nesting; `NestMembers` là danh sách authorized nest members để JVM sử dụng trong private access control, kết hợp `NestHost`.

**15.** Tại sao `javac --release 8` có thể sinh `access$000` cho class lồng?

**Đáp án:** Class-file 52 không có nest attributes; compiler target cũ phải tạo synthetic accessor trong một số trường hợp để vượt private access giữa hai class files.

**16.** Một lỗi `IllegalAccessError` báo “not listed as a nest member” sau deploy gợi ý điều gì?

**Đáp án:** Host/member class files bị build/shade/đóng gói không đồng bộ hoặc class loader/runtime package thay đổi. Inspection hai đầu `NestHost/NestMembers` trên đúng runtime artifacts và clean rebuild.

**17.** Một class file có đồng thời `NestHost` và `NestMembers` có hợp lệ không?

**Đáp án:** Không. JVMS `4.7.29` không cho phép cùng tồn tại trong một `ClassFile`.

**18.** Có thể thay đổi `private` member thành `public` để né mọi lỗi metadata không?

**Đáp án:** Đó là một cách phá encapsulation, không phải hướng sửa được khuyến nghị. Cần bảo toàn class-file metadata đúng và build/repackage một cách nhất quán.

**19.** Tại sao `NestMembers` attribute không cần liệt kê host nhưng `Class.getNestMembers()` lại trả cả host?

**Đáp án:** Attribute cấp danh sách **các thành viên khác được host công nhận**, còn API phản ánh **toàn bộ nest**, nơi host mặc nhiên là một thành viên.

**20.** Nếu compiler sinh một local class `Host$1Local` và một anonymous class `Host$1`, những class này có thể nằm trong `NestMembers` không?

**Đáp án:** Có. Ví dụ kiểm chứng Java 11 đã cho thấy cả hai; đừng giới hạn membership ở những tên có `$Inner` được khai báo trực tiếp trong class body.

## 18. Tài liệu chính thức và vẫn còn hiệu lực

- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): mục tiêu, thay đổi JVM/class file và mô hình nest-based private access được đưa vào Java 11.
- [Java SE 11 JVMS `4.1 — ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.1): định dạng header, constant pool, class-level attributes và major 55.
- [Java SE 11 JVMS `4.7.28 — NestHost](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28): định dạng binary, `attribute_length=2`, `host_class_index`.
- [Java SE 11 JVMS `4.7.29 — NestMembers](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29): danh sách members, `attribute_length=2+2*n`, quy tắc tối đa một attribute và không kết hợp với `NestHost` trên cùng class.
- [Java SE 11 JVMS `5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4): nestmate test, xác thực run-time package, điều kiện host authorization và lỗi access/linkage.
- [Oracle Java SE 11 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getNestHost()`, `getNestMembers()`, `isNestmateOf()` (có từ Java 11), đặc điểm reflection và xử lý lỗi.
- [Java SE 26 JVMS `4.7.28–29](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): các nest attributes vẫn là thành phần của class-file specification hiện hành; không phải API lỗi thời.
- [Java SE 26 JVMS `5.4.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-5.html#jvms-5.4.4): quy tắc nestmate access tiếp tục áp dụng.
- [Oracle Java SE 11 — `javap`](https://docs.oracle.com/en/java/javase/11/tools/javap.html): dùng `-v` để xem class-file attributes, `-p` để xem private members và `-c` để xem bytecode.

**Ghi nhớ:** `NestHost` trả lời **“tôi thuộc nest do ai host?”**; `NestMembers` trả lời **“host công nhận những class/interface nào là thành viên?”**. JVM chỉ cấp `private` nestmate access khi **cả hai phía nhất quán và cùng run-time package**. Để kiểm tra thực tế, biên dịch Java 11 bằng `javac --release 11`, dùng `javap -v` xem hai attributes và các reflection APIs từ Java 11; không đồng nhất nest với inheritance, package hoặc `InnerClasses`.