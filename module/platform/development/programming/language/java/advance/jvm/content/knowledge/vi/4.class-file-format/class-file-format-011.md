# Giới hạn kích thước phương thức, constant pool và các ràng buộc định dạng tệp class

## 1. Mục tiêu

Tệp **.class** có một cấu trúc nhị phân cụ thể, không phải một kho dữ liệu có thể mở rộng vô hạn. Nhiều trường trong định dạng này dùng số nguyên không dấu 8, 16 hoặc 32 bit; kích thước của chúng và những quy tắc kiểm tra hợp lệ tạo ra giới hạn đối với bytecode, constant pool, phương thức, tham số và metadata. Các giới hạn này ảnh hưởng rõ nhất đến code generation, annotation processing, compiler, proxy, bytecode instrumentation và các lớp Java quá lớn do công cụ sinh ra.

Sau bài học, bạn có thể:

- Giải thích vì sao mã bytecode của **một phương thức có Code attribute** không được vượt **65.535 byte**.
- Đọc chính xác ý nghĩa **constant_pool_count**, phân biệt số slot, số entry thực và số literal trong mã nguồn.
- Phân biệt **giới hạn của một chuỗi CONSTANT_Utf8** theo số byte Modified UTF-8 với giới hạn ký tự Java.
- Nhận biết giới hạn tham số phương thức, local variable slots, operand stack, số field/method và số chiều mảng.
- Phân biệt lỗi do **định dạng class file**, lỗi **xác minh bytecode**, lỗi **liên kết** và giới hạn tài nguyên thực tế.
- Dùng **javac**, **javap** và chương trình Java 17+ để kiểm tra class header, constant pool và dữ liệu liên quan.
- Biết cách chia nhỏ code sinh tự động khi chạm giới hạn, đồng thời không nhầm “chia phương thức” với “giảm constant pool”.

## 2. Tại sao cần nhìn cấu trúc class file?

Trong Java source, một lớp có thể chứa rất nhiều dòng, nhiều biểu thức hoặc hằng chuỗi. Nhưng JVM không chạy trực tiếp văn bản Java; trình biên dịch tạo cấu trúc **ClassFile** gồm header, constant pool, khai báo field, khai báo method, attributes và nhiều tham chiếu bằng chỉ số.

Sơ đồ rút gọn:

~~~text
ClassFile
  u4 magic                      = 0xCAFEBABE
  u2 minor_version
  u2 major_version
  u2 constant_pool_count
  cp_info constant_pool[constant_pool_count - 1]
  u2 access_flags
  u2 this_class
  u2 super_class
  u2 interfaces_count
  u2 interfaces[interfaces_count]
  u2 fields_count
  field_info fields[fields_count]
  u2 methods_count
  method_info methods[methods_count]
  u2 attributes_count
  attribute_info attributes[attributes_count]
~~~

Các ký hiệu số nguyên không dấu:

| Ký hiệu | Số byte | Miền số có thể mã hóa | Ví dụ sử dụng |
| --- | ---: | ---: | --- |
| **u1** | 1 | 0–255 | Constant-pool tag, opcode, số chiều trong instruction **multianewarray** |
| **u2** | 2 | 0–65535 | **constant_pool_count**, **methods_count**, **max_locals**, nhiều chỉ số |
| **u4** | 4 | 0–4294967295 | **magic**, **attribute_length**, **code_length** ở mức khai báo trường |

**Điểm mấu chốt:** miền số của trường nhị phân là **điều kiện cần**, chưa đủ để kết luận mọi giá trị đó đều hợp lệ. Chẳng hạn **code_length** được lưu bằng **u4**, nhưng JVMS quy định nó phải **lớn hơn 0 và nhỏ hơn 65536**. Vì vậy không thể dùng toàn bộ miền u4 cho phần instruction của một phương thức.

Class file còn có quy tắc kiểm tra phiên bản, index, kiểu entry, cú pháp tên/descriptor, vị trí attributes, bytecode instruction, control flow và stack types. Một tệp có đúng magic và các độ dài nằm trong giới hạn vẫn có thể không hợp lệ.

## 3. Giới hạn code của một phương thức: 65.535 byte

Mã thực thi của phương thức thông thường nằm trong **Code attribute** của **method_info**:

~~~text
Code_attribute {
  u2 attribute_name_index;
  u4 attribute_length;
  u2 max_stack;
  u2 max_locals;
  u4 code_length;
  u1 code[code_length];
  u2 exception_table_length;
  exception_table_entry exception_table[exception_table_length];
  u2 attributes_count;
  attribute_info attributes[attributes_count];
}
~~~

Theo **JVMS §4.7.3**:

- **code_length** là số byte của mảng **code[]**.
- **code_length phải từ 1 đến 65.535 byte**, tính cả operand bytes, không chỉ tính một byte opcode cho mỗi instruction.
- **Code attribute** của phương thức có thân Java/bytecode thông thường chứa đúng một phần mã theo cấu trúc được yêu cầu. Phương thức **abstract** và **native** không có Code attribute.
- **attribute_length** là kích thước payload attribute, không phải số byte instructions; nó còn bao gồm các trường **max_stack**, **max_locals**, exception table và nested attributes.
- **LineNumberTable**, **LocalVariableTable**, **StackMapTable**... là metadata nằm trong/đi kèm Code attribute theo cấu trúc quy định; chúng không được tính vào **code_length** của mảng instructions.

### 3.1. Giới hạn theo bytecode, không phải số dòng Java

Ví dụ hai phương thức cùng có 100 dòng source vẫn có thể tạo ra số byte instruction rất khác nhau:

- Một phép gán hằng ngắn có thể dùng instruction 1 byte.
- Lệnh nạp một constant-pool reference có thể cần nhiều byte.
- **invokevirtual**, **invokestatic**, **new**, **getfield**, **putfield**, **ldc_w**... có opcode và operand chiếm nhiều byte.
- **tableswitch/lookupswitch** có phần căn chỉnh/padding và dữ liệu nhánh khiến kích thước tăng nhanh.
- Lambda, string concatenation, try/finally, switch, pattern matching hoặc compiler-generated code có thể đưa thêm instructions và metadata.

Do đó, đếm dòng **.java** không cho biết trực tiếp có vượt giới hạn **code_length** hay không. Một method source rất dài đôi khi biên dịch được; một method được sinh bằng hàng ngàn nhánh/statement có thể gặp lỗi “**code too large**”.

### 3.2. 65.535 byte là giới hạn cho một method, không phải cả class

Một class file có thể chứa nhiều phương thức, mỗi phương thức có Code attribute riêng. Giới hạn **code_length** áp dụng độc lập cho từng phương thức có mã. Nó **không có nghĩa** cả tệp **.class** chỉ được 64 KiB hoặc JVM không thể chứa một phương thức dài hơn 64 KiB mã máy JIT.

So sánh:

| Đối tượng | Giới hạn liên quan |
| --- | --- |
| Bytecode instructions của **một** method | **1–65.535 byte** trong **Code.code[]** |
| Toàn bộ **Code attribute** | Có phần header, exception table, nested attributes; không đồng nhất với **code_length** |
| Toàn bộ tệp **.class** | Không có giới hạn chung “64 KiB” từ **code_length** |
| Mã máy sau JIT | Chi tiết của runtime/JIT, không bị đồng nhất với trường **Code.code_length** |

Một method lớn hơn ngưỡng không được “cứu” bằng cách tăng **-Xmx**; đây là giới hạn của định dạng bytecode, không phải lỗi thiếu heap.

### 3.3. Exception handler ở biên code_length

Exception table dùng **start_pc**, **end_pc** và **handler_pc** kiểu **u2**; khoảng được bảo vệ là **[start_pc, end_pc)**, tức gồm đầu và không gồm cuối. **end_pc** có thể bằng **code_length**.

Vì **code_length** tối đa 65.535 và instruction được đánh chỉ số byte từ 0, handler ở sát biên có thể gặp ràng buộc khó xử lý khi đoạn try phải bao trùm instruction cuối cùng. JVMS ghi nhận giới hạn lịch sử của việc dùng exclusive **end_pc**; trong thực hành công cụ sinh bytecode cần kiểm tra kỹ vùng handler, target offset và các mốc 65.535/65.536 thay vì chỉ đảm bảo tổng số byte không vượt ngưỡng.

## 4. Constant pool: giới hạn slot và ý nghĩa của count

Mỗi class/interface có một **constant pool** chứa các cấu trúc biểu diễn tên class, kiểu, chuỗi, số, tham chiếu field/method, dynamic constants, invokedynamic, method handle và những metadata có liên quan. Chúng không đơn giản là danh sách các literal được khai báo trong code nguồn.

Trong class header:

~~~text
u2 constant_pool_count;
cp_info constant_pool[constant_pool_count - 1];
~~~

Quy tắc:

- **constant_pool_count** lưu bằng **u2**, vì vậy giá trị lớn nhất có thể biểu diễn là **65.535**.
- Chỉ số hợp lệ của các entry thông thường nằm trong khoảng **1 đến constant_pool_count - 1**.
- **Index 0 không đại diện cho một constant-pool entry thực**; nó có ý nghĩa riêng ở vài cấu trúc tham chiếu.
- Nếu **constant_pool_count = 65.535**, các vị trí có thể đánh chỉ số trong bảng là **1...65.534**, tức nhiều nhất **65.534 slot sau vị trí 0**.
- Entry **CONSTANT_Long** và **CONSTANT_Double** chiếm **hai vị trí liên tiếp** trong cách đánh chỉ số constant pool, dù cấu trúc dữ liệu chỉ chiếm một cp_info thực. Vị trí ngay sau entry này bị dành riêng, không phải entry độc lập có thể truy cập.

Đây là khác biệt quan trọng giữa câu mô tả ngắn “giới hạn constant pool là 65.535” (giới hạn trường count) và phép tính chính xác **65.534 vị trí có chỉ số**, trong đó một số vị trí có thể là slot dự trữ sau long/double.

### 4.1. Ví dụ đánh số và long/double

Giả sử một phần bảng được ghi như sau:

~~~text
#1  Utf8          "Example"
#2  Class         #1
#3  Utf8          "answer"
#4  Integer       42
#5  Long          9000000000
#6  (reserved by Long entry at #5)
#7  Utf8          "main"
...
~~~

Entry **#5** chiếm hai slot **#5 và #6**, nên entry tiếp theo là **#7**. Một parser class file phải tăng chỉ số thêm hai sau **CONSTANT_Long**/**CONSTANT_Double**, nếu không mọi index tiếp theo sẽ bị lệch.

**Không** cộng thêm một entry thực cho slot dự trữ khi thống kê số cp_info được mã hóa trên byte stream; nhưng phải tính nó khi kiểm tra số slot/chỉ số.

### 4.2. Constant pool không đếm số lần dùng hằng trong mã nguồn

Một chuỗi literal xuất hiện nhiều lần có thể tái dùng constant-pool entry tương ứng. Ngược lại, một lời gọi method có thể cần nhiều entry: ví dụ **Class**, **Utf8** tên class, **NameAndType**, **Utf8** tên method, **Utf8** descriptor và **Methodref**. Chúng có thể tái sử dụng nhau hoặc được compiler/tool tạo mới tùy trường hợp.

Vì vậy:

- “100.000 lần dùng một literal” không nhất thiết tạo 100.000 constant-pool entries.
- “10.000 dòng code” không cho biết có bao nhiêu constant-pool slots.
- Một class sinh ra chứa rất nhiều **field/method names**, **method descriptors**, **literals** hoặc **dynamic call sites** có thể tràn constant pool dù mỗi method riêng lẻ ngắn.
- Việc **chia một method thành nhiều method trong cùng một class** giúp giảm **code_length** cho từng method, nhưng **không bảo đảm** constant pool của **class** nhỏ đi; thậm chí có thể cần thêm tên và Methodref.

### 4.3. Những loại entry tiêu biểu

| Constant-pool tag | Nội dung chính | Chiếm slot |
| --- | --- | ---: |
| **CONSTANT_Utf8** (1) | Tên, descriptor, văn bản metadata theo Modified UTF-8 | 1 |
| **CONSTANT_Integer** (3), **Float** (4) | Hằng số tương ứng | 1 |
| **CONSTANT_Long** (5), **Double** (6) | Hằng số 64 bit | **2** |
| **CONSTANT_Class** (7) | Tham chiếu tên class/interface hoặc mảng theo quy tắc class file | 1 |
| **CONSTANT_String** (8) | Tham chiếu literal String qua Utf8 entry | 1 |
| **CONSTANT_Fieldref** (9) | Symbolic reference tới field | 1 |
| **CONSTANT_Methodref** (10) | Symbolic reference tới class method | 1 |
| **CONSTANT_InterfaceMethodref** (11) | Symbolic reference tới interface method | 1 |
| **CONSTANT_NameAndType** (12) | Ghép tên và descriptor | 1 |
| **CONSTANT_MethodHandle** (15), **MethodType** (16) | Thành phần method handle và method type | 1 |
| **CONSTANT_Dynamic** (17), **InvokeDynamic** (18) | Dynamic constant / call site có bootstrap | 1 |

Một “slot” trong bảng không có nghĩa các entry có cùng kích thước byte trên disk. **Utf8** có độ dài thay đổi; **Long** dùng hai slot index nhưng byte payload thuộc một entry, và **Class/NameAndType** còn tham chiếu những entry khác.

## 5. CONSTANT_Utf8: giới hạn 65.535 **byte**, không phải 65.535 ký tự

Trong constant pool, tên field/method, descriptor, string text và nhiều metadata được lưu bằng **CONSTANT_Utf8_info**:

~~~text
CONSTANT_Utf8_info {
  u1 tag;         // 1
  u2 length;      // số byte của bytes[], không tính tag và length
  u1 bytes[length];
}
~~~

Điều quan trọng:

- **length tối đa 65.535 byte** do lưu bằng **u2**.
- Nội dung dùng **Modified UTF-8 (MUTF-8)** của class file.
- Dữ liệu **không** kết thúc bằng byte NUL.
- Ký tự Unicode có thể sử dụng nhiều byte; số ký tự Java, số Unicode code points và số byte MUTF-8 là các phép đếm khác nhau.
- Giới hạn áp dụng cho **mỗi entry CONSTANT_Utf8**, không phải tổng kích thước mọi chuỗi trong class.

### 5.1. Modified UTF-8 khác UTF-8 thông thường ở đâu?

Ví dụ:

| Giá trị chuỗi | Độ dài Java UTF-16 code units | Số byte MUTF-8 |
| --- | ---: | ---: |
| **A** | 1 | 1 |
| **é** | 1 | 2 |
| **中** | 1 | 3 |
| Ký tự **U+0000** | 1 | 2 |
| **😀** (ký tự ngoài BMP) | 2 | **6** |

Với U+0000, MUTF-8 mã hóa thành hai byte **C0 80**, không đặt một byte 0 trong dữ liệu. Với emoji ngoài Basic Multilingual Plane, MUTF-8 dùng hai mã UTF-16 surrogate, mỗi mã chiếm ba byte; khác UTF-8 thông thường vốn có thể mã hóa emoji thành bốn byte.

Hệ quả:

- 65.535 chữ **A** có thể vừa 65.535 byte MUTF-8, nhưng một ký tự thêm sẽ vượt giới hạn của một Utf8 entry.
- 32.768 ký tự **é** chiếm 65.536 byte MUTF-8, vượt giới hạn dù số phần tử UTF-16 mới là 32.768.
- Một **String** runtime có thể dài hơn giới hạn một CONSTANT_Utf8 entry vì được tạo động, ghép từ nhiều hằng hoặc đọc từ dữ liệu ngoài; đừng nhầm giới hạn lưu một literal trong class file với giới hạn toàn bộ String trên heap.

### 5.2. Đừng tự động dùng UTF-8 chuẩn để dự đoán độ dài

Một generator có thể sai khi:

1. Đếm **String.length()** rồi kết luận đó là số byte trong CONSTANT_Utf8.
2. Dùng UTF-8 tiêu chuẩn của **String.getBytes(StandardCharsets.UTF_8)** để đo hằng chứa NUL hoặc emoji.
3. Dùng số code point mà bỏ qua surrogate pairs.
4. Cắt chuỗi MUTF-8 giữa một mã được mã hóa nhiều byte để vừa giới hạn.

Cần dùng bộ mã hóa MUTF-8 đúng contract. **DataOutputStream.writeUTF** trong Java SE là công cụ minh họa thuận tiện vì nó ghi một trường độ dài **u2** rồi chuỗi theo Modified UTF-8. Cấu trúc tổng thể **không phải toàn bộ CONSTANT_Utf8_info** vì constant pool còn có **tag = 1**, nhưng cách tính byte và giới hạn length là tương ứng.

## 6. Ví dụ thực hành 1: kiểm tra Modified UTF-8

Tạo tệp **ModifiedUtfLimitDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UTFDataFormatException;

public class ModifiedUtfLimitDemo {
    static int encodedLength(String value) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeUTF(value);
        }
        byte[] bytes = buffer.toByteArray();
        return ((bytes[0] & 0xFF) << 8) | (bytes[1] & 0xFF);
    }

    public static void main(String[] args) throws IOException {
        System.out.println("ascii=" + encodedLength("A".repeat(65535)));
        System.out.println("nul=" + encodedLength(String.valueOf((char) 0)));
        System.out.println("emoji=" + encodedLength("😀"));

        try {
            encodedLength("A".repeat(65536));
            System.out.println("tooLong=unexpected");
        } catch (UTFDataFormatException expected) {
            System.out.println("tooLong=UTFDataFormatException");
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 ModifiedUtfLimitDemo.java
java ModifiedUtfLimitDemo
~~~

**Stdout:**

~~~text
ascii=65535
nul=2
emoji=6
tooLong=UTFDataFormatException
~~~

Giải thích: **DataOutputStream.writeUTF** ghi hai byte length theo thứ tự big-endian rồi chuỗi MUTF-8. Chương trình đọc hai byte này như số nguyên không dấu. Với **65536** chữ A, số byte không còn vừa **u2** nên API ném **UTFDataFormatException**.

Đây là minh họa giới hạn **một MUTF-8 payload**, không phải một cách tự tạo hoặc đo toàn bộ constant pool của class file đang chạy.

## 7. Giới hạn số field, method, interface và attribute

Ngoài Code và constant pool, nhiều bảng trong ClassFile sử dụng count dạng **u2**:

| Vùng | Trường đếm | Ý nghĩa giới hạn định dạng |
| --- | --- | --- |
| Field do class/interface **khai báo** | **fields_count** | Tối đa **65.535** phần tử **field_info** trong bảng |
| Method do class/interface **khai báo** | **methods_count** | Tối đa **65.535** phần tử **method_info** trong bảng |
| Direct superinterfaces | **interfaces_count** | Tối đa **65.535** phần tử |
| Class-level attributes | **attributes_count** | Số mục attribute trong bảng hiện tại tối đa 65.535 theo u2 |
| Các attribute tables bên trong field/method/Code | Các trường **attributes_count** riêng | Chịu giới hạn riêng và các quy tắc hiện diện/không trùng lặp |

**Fields_count và methods_count không bao gồm thành viên chỉ được thừa kế**. Ngược lại, các phương thức được compiler sinh trong chính class (ví dụ synthetic/bridge khi cần) vẫn góp vào số mục thực tế của **methods[]**.

Một con số nằm trong khoảng u2 **không bảo đảm class hợp lệ**:

- Field/method phải có tên, descriptor, flags và constraints phù hợp.
- Không thể tùy ý khai báo hai field với cùng name+descriptor hoặc hai method với cùng name+descriptor trong một class file.
- Một số attribute chỉ xuất hiện trong vị trí nhất định, có đúng số lần cho phép, và có cấu trúc riêng.
- Interface và class có quy tắc class-file validation khác nhau ở một số flags/attributes.
- Số lượng thành viên “được phép biểu diễn” khác năng lực hợp lý của compiler, runtime và tài nguyên máy thực.

Khi một code generator tạo quá nhiều thành viên trong **cùng một class**, có thể cần tạo thêm helper classes. Nhưng chuyển bớt method sang class khác cũng phải giữ đúng access, initialization, class loading và API contract.

## 8. max_locals và max_stack: slot của frame JVM

Mỗi Code attribute có:

~~~text
u2 max_stack;
u2 max_locals;
~~~

Các trường này mô tả nhu cầu frame theo mô hình JVM:

- **max_locals**: số vị trí local variable slots dành cho frame. Giới hạn tối đa **65.535 slots**.
- **max_stack**: độ sâu tối đa của operand stack, được đo theo units/slots trong mô hình đặc tả. Giới hạn tối đa **65.535 units**.
- Một giá trị **long** hoặc **double** chiếm **2 units** trong tính toán **max_locals/max_stack**.
- Các kiểu category 1 như int, float hoặc reference chiếm **1 unit**.
- Với instance method, local slot đầu thường chứa tham chiếu **this**; các tham số tiếp theo chiếm số slot theo loại.

Ví dụ khái quát:

~~~java
// Ví dụ phương thức instance, không phải chương trình Java độc lập.
class Calculator {
    long combine(int a, long b, double c) {
        long result = a + b;
        return result + (long) c;
    }
}
~~~

Vào method **combine**:

~~~text
Local slots lúc vào method:
  slot 0     this               (1)
  slot 1     int a              (1)
  slots 2-3  long b             (2)
  slots 4-5  double c           (2)
  slots ...  các local khác do compiler bố trí
~~~

Vì vậy chỉ riêng receiver và ba tham số đã cần **6 slots** ở đầu frame. Không nên nói rằng **long/double** là “một local” khi kiểm tra giới hạn u2 này.

Có giới hạn về index: với **max_locals = N**, local thuộc category 1 có chỉ số cao nhất **N - 1**, còn một giá trị long/double cần hai slots nên chỉ số bắt đầu cao nhất là **N - 2**. Instruction **wide** giúp mã hóa các local indexes lớn hơn dạng instruction thông thường, nhưng **không bãi bỏ giới hạn max_locals**.

**Không suy ra bộ nhớ:** slot trong JVM frame là đơn vị trừu tượng, không phải cam kết từng slot luôn tiêu thụ đúng bốn byte native memory.

## 9. Giới hạn tham số: 255 parameter units

**Method descriptor** biểu diễn kiểu tham số và trả về, ví dụ:

~~~text
(IJLjava/lang/String;)V
 | | |                  |
 int long String       return void
~~~

Theo **JVMS §4.3.3**, tổng độ dài danh sách tham số phải **không quá 255 parameter units**:

- **int, byte, short, char, boolean, float, reference hoặc array**: mỗi tham số tính **1 unit**.
- **long, double**: mỗi tham số tính **2 units**.
- Với lời gọi instance/interface method, tính thêm **1 unit** cho **this** ngầm.
- Với static method, không có receiver **this** ngầm theo quy tắc này.

Bởi vậy giới hạn thực dụng:

| Dạng method | Tổng units tham số khai báo tối đa theo descriptor/invocation |
| --- | --- |
| Static method | **255 units** |
| Instance/interface method | **254 units** tham số khai báo + **1 unit this** |
| Static có 128 tham số long | 256 units, vượt giới hạn |
| Static có 127 tham số long và 1 tham số int | 255 units, vừa về parameter units |
| Instance có 127 tham số long | 254 + 1 this = 255 units, vừa về parameter units |

Các ví dụ trên chỉ kiểm tra phép đếm parameter units; một khai báo cụ thể còn phải đáp ứng các ràng buộc tên, descriptor, class file và ngôn ngữ Java. Giá trị trả về **long/double** không được cộng vào độ dài danh sách tham số.

Chỉ nhìn **số lượng dấu phẩy** trong Java source sẽ cho kết quả sai nếu method có **long/double** hoặc là instance method. **varargs** như **String... values** chỉ là một array parameter về mặt descriptor nên tính **1 unit**, dù lúc gọi có thể truyền nhiều phần tử.

**Độc lập với max_locals:** giới hạn 255 đơn vị tham số và giới hạn 65.535 local slots là hai ràng buộc khác nhau; một method có ít tham số vẫn có thể dùng rất nhiều biến cục bộ, và không được dùng dung lượng max_locals để vượt giới hạn descriptor.

## 10. Ràng buộc về số chiều mảng

JVM cho phép mảng có tối đa **255 dimensions** theo định dạng và constraints của instruction, nhất là **multianewarray**:

~~~text
[I             int[]
[[I            int[][]
[[[I           int[][][]
[Ljava/lang/String;  String[]
~~~

Mỗi dấu **[** ứng với một chiều trong array descriptor. Mã lệnh **multianewarray** mang một operand **dimensions** dạng **u1**, có giá trị thích hợp từ 1 đến số chiều của array class được tham chiếu.

Giới hạn **255** là giới hạn biểu diễn/tập lệnh. Nó không có nghĩa việc tạo mảng 255 chiều luôn khả thi về heap, stack hay business logic. JVM có thể phải tuân theo các ràng buộc verifier và cấp phát; một chương trình hợp lệ vẫn có thể thất bại do tài nguyên.

## 11. Phiên bản class file và các điều kiện định dạng khác

Class header dùng:

~~~text
magic          u4 = CAFEBABE
minor_version  u2
major_version  u2
~~~

Ví dụ, class file mục tiêu **Java 17** dùng **major version 61**; Java 21 dùng **65**. Runtime chỉ có thể tải định dạng và tính năng mà phiên bản JVM của nó hỗ trợ. Class file phiên bản mới đưa vào runtime cũ thường dẫn tới **UnsupportedClassVersionError**.

**Phiên bản class file không giống giới hạn code_length**: tạo class file với major mới hơn không tự nâng giới hạn Code attribute lên hàng megabyte. Khi triển khai bytecode generator, phải tuân cả version-specific rules, constant-pool tags/attributes và các constraint của class file.

Ngoài độ dài có một số ràng buộc cấu trúc cốt lõi:

1. **Magic, version** phải hợp lệ đối với runtime mục tiêu.
2. Mọi chỉ số **constant pool** được tham chiếu phải nằm trong phạm vi và trỏ đúng **tag/type** mà cấu trúc yêu cầu.
3. Tên class, field, method và **descriptors** phải theo grammar JVM, ví dụ field descriptor **I**, **Ljava/lang/String;**, method descriptor **(I)V**.
4. Các chỉ số trong **Code** phải tham chiếu đúng operand, local variables, exception table và instruction boundaries.
5. Branch targets phải nhảy tới vị trí đầu instruction hợp lệ, không nhảy vào giữa operands hoặc vượt vùng **code[]**.
6. Stack/local typing tại điểm nối control flow phải hợp lệ theo quy tắc bytecode verification; StackMapTable dùng khi yêu cầu bởi phiên bản/kiểu xác minh tương ứng.
7. Những attributes cần cho việc hiểu class file phải đúng vị trí, đúng version và đúng constraints; một số metadata tùy chọn có thể bị bỏ qua theo đặc tả.
8. **Concrete method** phải có Code attribute hợp lệ; method **native/abstract** không có Code attribute.

Các điều kiện này giải thích vì sao một tệp có các counter trong phạm vi u2/u4 vẫn có thể bị JVM từ chối.

### 11.1. attribute_length có u4 nhưng không giúp tăng bytecode method

Một attribute có **u2 attribute_name_index** và **u4 attribute_length**. Dung lượng 32 bit của phần payload không có nghĩa **Code.code_length** cũng được phép dài tới 2^32-1 byte. **Code** có ràng buộc riêng **1–65.535 byte**.

Nhiều metadata như debug tables và annotation content có thể đóng góp kích thước vào class file, nhưng không phải bytecode instructions. Đừng lẫn **kích thước file .class**, **kích thước Code attribute**, **số byte của code[]** và **dung lượng constant pool**.

## 12. Ví dụ thực hành 2: đọc header của chính class file

Tạo tệp **ClassHeaderLimitDemo.java**:

~~~java
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;

public class ClassHeaderLimitDemo {
    static int sumBefore(int limit) {
        int result = 0;
        for (int i = 0; i < limit; i++) {
            result += i;
        }
        return result;
    }

    public static void main(String[] args) throws IOException {
        try (InputStream raw =
                     ClassHeaderLimitDemo.class.getResourceAsStream(
                             "/ClassHeaderLimitDemo.class")) {
            if (raw == null) {
                throw new IllegalStateException("Cannot locate class file");
            }
            DataInputStream in = new DataInputStream(raw);

            int magic = in.readInt();
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            int constantPoolCount = in.readUnsignedShort();

            System.out.printf("magic=%08X%n", magic);
            System.out.println("major=" + major);
            System.out.println("minor=" + minor);
            System.out.println("constantPoolNonEmpty=" + (constantPoolCount > 1));
            System.out.println("sumBefore5=" + sumBefore(5));
        }
    }
}
~~~

Biên dịch cho Java 17 và chạy bằng JVM tương thích:

~~~bash
javac --release 17 -encoding UTF-8 ClassHeaderLimitDemo.java
java ClassHeaderLimitDemo
~~~

**Stdout chính xác khi dùng lệnh trên:**

~~~text
magic=CAFEBABE
major=61
minor=0
constantPoolNonEmpty=true
sumBefore5=10
~~~

Giải thích:

- **readInt()** đọc magic 4 byte, được in theo dạng hex 8 chữ số.
- **readUnsignedShort()** đọc lần lượt minor, major, **constant_pool_count** theo đúng thứ tự header.
- **--release 17** tạo class file major **61** và, khi không dùng preview, minor **0**.
- Class này có constant pool không rỗng; **constantPoolNonEmpty** là **true**.
- **sumBefore(5)** cộng **0 + 1 + 2 + 3 + 4 = 10**.

Chương trình đọc **constant_pool_count**, nhưng chỉ in một kiểm tra boolean để stdout ổn định giữa các compiler. Khi thực hành, bạn có thể tự thêm:

~~~java
// Dòng minh họa thêm vào main để xem giá trị thực:
System.out.println("constant_pool_count=" + constantPoolCount);
~~~

Con số được in khi thêm dòng này có thể thay đổi theo compiler, tối ưu và những sửa đổi trên mã. Nếu muốn phân tích toàn bộ constant pool, phải đọc lần lượt từng **tag** và dung lượng của tag, đồng thời bỏ qua vị trí dành riêng cho **Long/Double**. Không thể coi toàn bộ constant pool là một mảng giá trị có kích thước cố định.

## 13. Xác minh bằng javap

Dùng class file vừa biên dịch:

~~~bash
javap -verbose ClassHeaderLimitDemo
javap -c -p ClassHeaderLimitDemo
javap -s -p ClassHeaderLimitDemo
~~~

Với **javap -verbose**, hãy tìm:

- **major version: 61**, **minor version: 0**;
- Những entry **#n = Utf8**, **Class**, **Methodref**, **NameAndType**... trong **Constant pool**;
- Trong phần **Code**, các chỉ số bytecode và thông tin **stack=...**, **locals=...**, **args_size=...**;
- Các attributes phụ như **LineNumberTable**, **StackMapTable** (nếu compiler sinh).

**javap -c** giải mã opcode và operand; offset bên trái instruction là vị trí byte trong code, không phải số thứ tự dòng source. Để lấy **code_length** chính xác, cần parse trực tiếp trường **Code.code_length** hoặc dùng công cụ bytecode chuyên dụng; không nên lấy “số dòng output” của javap làm code_length.

**javap -s** cho descriptors để kiểm tra parameter types khi có nhiều tham số **long/double**. Nếu dùng công cụ ASM hoặc bytecode library, nhớ phân biệt giới hạn theo slot, độ dài instruction array và cặp index/tag của constant pool.

## 14. Lỗi vượt giới hạn: xảy ra ở bước nào?

Một số lỗi liên quan nhưng ý nghĩa khác nhau:

| Hiện tượng | Khả năng nguyên nhân | Hướng xác minh |
| --- | --- | --- |
| Compiler báo **code too large** hoặc tương tự | **Một method** có instruction bytes vượt giới hạn | Xác định method nào, đo Code byte length, tách luồng xử lý |
| Compiler báo **too many constants** hoặc tương tự | Constant pool của **một class** không chứa thêm đủ entry/slot | Đếm constant pool và loại entry, phân bổ code/data sang class khác |
| Compiler báo chuỗi UTF-8 quá dài | Một Utf8 entry vượt **65.535 byte MUTF-8** | Đo số byte MUTF-8, chia dữ liệu thành nhiều phần để ghép runtime |
| Compiler từ chối method có quá nhiều tham số | Method descriptor/invocation vượt **255 units** hoặc có ràng buộc source/tool riêng | Tính long/double = 2 và this = 1 cho instance |
| **ClassFormatError** khi nạp class | Cấu trúc class file không hợp lệ: count/index/tag/descriptor/attribute... | Kiểm tra byte stream, spec, generator và phiên bản class file |
| **VerifyError** | Bytecode có vấn đề về stack/local types, control flow, frames hoặc ràng buộc xác minh | Kiểm tra StackMapTable, stack heights, branch target, opcode |
| **UnsupportedClassVersionError** | Runtime không hỗ trợ class-file version yêu cầu | Kiểm tra major/minor và phiên bản JVM |
| **NoClassDefFoundError** / lỗi liên kết khác | Thiếu dependency hoặc tham chiếu không giải quyết được | Kiểm tra classpath/module path và binary compatibility |
| **OutOfMemoryError** | Thiếu tài nguyên runtime theo một cơ chế cụ thể | Quan sát heap/metaspace/native memory; không suy ngay là tràn constant pool |

Tên thông báo compiler có thể thay đổi giữa các phiên bản hoặc công cụ; không nên gán một thông báo duy nhất thành yêu cầu chuẩn của JVM. Trái lại, **ClassFormatError**, **VerifyError**, **UnsupportedClassVersionError** là các loại lỗi Java có ý nghĩa định danh tương ứng; thời điểm xuất hiện có thể phụ thuộc vào quá trình loading/linking/verification.

**Lưu ý:** Nếu tự sinh tệp class không hợp lệ, không cần thực thi nó để “kiểm tra lỗi” trên hệ thống quan trọng. Hãy ưu tiên dùng parser/verifier chuyên dụng trong môi trường thử nghiệm, rồi chạy trên JVM mục tiêu khi đã đủ điều kiện.

## 15. Những cách giảm độ phức tạp class file

### 15.1. Khi một phương thức vượt code_length

Cách phù hợp thường là **chia method lớn thành các helper methods** có trách nhiệm rõ ràng, đảm bảo thứ tự điều khiển, exception semantics, synchronization, visibility và side effects không đổi.

Ví dụ thay vì sinh một phương thức có hàng nghìn công đoạn nối tiếp:

~~~java
// Minh họa cấu trúc trước khi chia:
static void processAll() {
    // hàng nghìn statement do generator sinh
}
~~~

Tách thành các đoạn:

~~~java
// Minh họa cấu trúc sau khi chia:
static void processAll() {
    processPart1();
    processPart2();
    processPart3();
}

static void processPart1() { /* công việc phần 1 */ }
static void processPart2() { /* công việc phần 2 */ }
static void processPart3() { /* công việc phần 3 */ }
~~~

Đây là minh họa phương án tổ chức mã, **không phải chương trình độc lập**. Nếu logic ban đầu có một **try/finally**, một trạng thái local được chia sẻ hoặc một nhánh **break/continue/return**, việc tách method cần thiết kế cách truyền state và giữ nguyên hành vi. Không thể tách bằng cách cắt tùy ý ở mỗi 10.000 dòng.

Khi cắt bớt code của một method, hãy biên dịch lại và kiểm tra **code_length** bằng công cụ thực tế. Không suy ra chỉ cần giảm số dòng đến một ngưỡng bất kỳ.

### 15.2. Khi constant pool của class vượt giới hạn

Các lựa chọn:

- Phân chia generated code sang **nhiều class** thay vì dồn vào một class.
- Loại bỏ những string/descriptor/member references dư thừa nếu generator tạo trùng mà công cụ có thể tái sử dụng.
- Đưa khối dữ liệu lớn mang tính nghiệp vụ sang **resource file** hoặc định dạng dữ liệu phù hợp, thay vì mã hóa mọi mục thành field/literal riêng trong class file.
- Đổi cách biểu diễn bảng tra cứu sinh ra, dùng cấu trúc dữ liệu runtime được khởi tạo từ nguồn rõ ràng, nếu điều đó phù hợp yêu cầu khởi tạo/hiệu năng.
- Đo số **slot** và từng loại constant-pool entry sau mỗi lần sinh, đừng chỉ đo số method hoặc số literal.

**Tách method nhưng giữ nguyên một class** chưa chắc giúp constant pool; những helper mới còn có thể làm tăng **Utf8 tên method** và **Methodref**.

### 15.3. Khi một hằng chuỗi/metadata quá dài

Nếu một literal không vừa **CONSTANT_Utf8**, có thể chia dữ liệu và ghép tại runtime hoặc đọc từ một resource. Cần chú ý **thời điểm** nối chuỗi: compiler có thể gộp các biểu thức hằng thành một literal lớn hơn nếu chỉ viết:

~~~java
// Minh họa: các thành phần đều là constant expression.
// Compiler có thể gộp chúng thành một string literal.
static final String TEXT = "part1" + "part2";
~~~

Nếu dùng cách chia, hãy xác nhận bytecode/constant pool cuối cùng thật sự có các payload nhỏ hơn ngưỡng và kết quả runtime khôi phục chính xác dữ liệu. Với dữ liệu văn bản lớn, resource thường dễ quản lý hơn generated source quá dài.

### 15.4. Khi method có quá nhiều tham số

Có thể chuyển một nhóm tham số liên quan thành object/record phù hợp, hoặc thiết kế API nhận một cấu trúc dữ liệu có validation rõ. Đừng tự đổi 200 tham số thành một array nếu việc đó làm mất contract, tên trường, kiểu dữ liệu hoặc logic sử dụng.

Mỗi quyết định cần cân bằng ABI/binary compatibility, khả năng đọc hiểu, serialization, nullability và performance. Các giới hạn class file là điều kiện kỹ thuật; refactoring phải giữ đúng hợp đồng ứng dụng.

## 16. Bẫy thường gặp

1. **“Một method có tối đa 65.535 dòng.”** Sai; giới hạn áp dụng cho **byte trong Code.code[]**, không phải dòng Java.
2. **“code_length là u4 nên một method có thể chứa 4 GiB bytecode.”** Sai; JVMS quy định **code_length < 65.536**.
3. **“Một class file không được lớn hơn 64 KiB.”** Sai; giới hạn 64 KiB thuộc một vùng code của một method, không phải tổng kích thước class file.
4. **“constant_pool_count = 65535 nghĩa là có 65535 literal.”** Sai; index bắt đầu 1, mức tối đa số slot có chỉ số là 65534, và constant pool chứa nhiều loại cấu trúc.
5. **“Một Long chỉ dùng một slot vì nó là một constant.”** Sai ở cách đánh chỉ số; **CONSTANT_Long/Double** chiếm hai slot.
6. **“65535 ký tự Unicode luôn vừa một Utf8 entry.”** Sai; giới hạn là **65.535 byte MUTF-8**, có thể ít ký tự hơn rất nhiều.
7. **“long/double chỉ là một tham số.”** Đúng về số tham số Java được viết, nhưng mỗi cái chiếm **2 parameter units** khi tính giới hạn JVM.
8. **“Tăng heap sẽ sửa lỗi code too large hoặc constant pool too large.”** Không; đây là giới hạn biểu diễn của class file.
9. **“Chia phương thức luôn giải quyết mọi trường hợp.”** Không; nó giải quyết code_length khi thực hiện đúng, còn class-level constant pool có thể vẫn vượt giới hạn.
10. **“ClassFormatError và VerifyError là một.”** Không; kiểm tra cấu trúc và xác minh kiểu/control flow là các phạm trù liên quan nhưng khác nhau.
11. **“Số field, method thừa kế cộng vào fields_count/methods_count.”** Không; các bảng đó chứa member được khai báo trong class file tương ứng.
12. **“Đã đúng count thì class chắc chắn chạy.”** Không; còn version, descriptor, flags, references, attributes, verification, linking và dependency.

## 17. Bài tập tự kiểm tra

**Câu 1.** Code attribute có **code_length = 65536** nhưng **attribute_length** vẫn vừa u4. Nó hợp lệ không?

**Đáp án:** Không. Trường **code_length** được lưu bằng u4 nhưng đặc tả giới hạn giá trị hợp lệ trong khoảng **1–65535**.

**Câu 2.** Với **constant_pool_count = 100**, các chỉ số thường hợp lệ có miền nào?

**Đáp án:** **1–99**; vị trí 0 không là entry thường. Nếu có **Long/Double**, slot tiếp ngay sau entry đó bị dành riêng và không chứa cp_info độc lập.

**Câu 3.** Vì sao 32.768 ký tự **é** có thể vượt giới hạn một Utf8 entry?

**Đáp án:** Mỗi **é** chiếm **2 byte MUTF-8**, tổng **65.536 byte**, lớn hơn mức u2 cho phép **65.535**.

**Câu 4.** Một static method có 127 tham số **double** và một **int**. Parameter length bằng bao nhiêu?

**Đáp án:** **127 × 2 + 1 = 255 units**, vừa giới hạn descriptor đối với static method, giả sử các ràng buộc khác được thỏa mãn.

**Câu 5.** Cũng tập tham số trên nhưng là instance method thì sao?

**Đáp án:** Phải tính thêm **this** = 1 unit, thành **256**, vượt giới hạn.

**Câu 6.** Một phương thức có khoảng 20.000 dòng Java nhưng code_length chỉ 50.000 byte; một phương thức khác có 5.000 dòng nhưng code_length 66.000 byte. Phương thức nào không hợp lệ theo giới hạn Code?

**Đáp án:** Phương thức thứ hai; tiêu chí là **số byte instructions**, không phải số dòng source.

**Câu 7.** Nếu tách một generated method lớn thành 20 helper method trong cùng một class, constant pool có chắc giảm?

**Đáp án:** Không. Nó có thể tăng do tên helper và symbolic references mới. Muốn giảm constant pool class-level phải xét tổng entry/slot của class và thường cần phân bổ sang nhiều class hoặc thay cách lưu dữ liệu.

**Câu 8.** **max_locals** có giá trị 20. Có thể đặt một **double** bắt đầu ở local slot index 19 không?

**Đáp án:** Không; **double** chiếm hai slot. Slot bắt đầu cao nhất là **18** nếu **max_locals = 20**.

**Câu 9.** JVM báo **UnsupportedClassVersionError** khi nhận class file mới. Có nên giảm **Code.code_length** để sửa không?

**Đáp án:** Không giải quyết đúng nguyên nhân. Cần chạy runtime hỗ trợ class-file version hoặc biên dịch với **--release**/target phù hợp cùng các API tương thích.

**Câu 10.** Một class file có **major=61**, **constant_pool_count=20**, mọi counts đều không vượt u2. Đã đủ kết luận hợp lệ chưa?

**Đáp án:** Chưa. Còn phải kiểm tra từng tag, index, descriptor, flags, attributes, Code, stack frames, targets và các ràng buộc định dạng/xác minh khác.

## 18. Checklist dành cho compiler, bytecode generator và người đọc class file

- **Xác định đơn vị đo:** byte trong code[], slot constant pool, byte MUTF-8, parameter units, local slots hay toàn bộ file.
- **Đo sau khi sinh bytecode thực:** nhiều compiler tối ưu/sinh helper, synthetic methods và metadata nên số dòng Java không đủ.
- **Mỗi method:** bảo đảm **code_length 1–65535**, branch/handler offset hợp lệ, max_stack/max_locals nhất quán và StackMapTable đúng nếu cần.
- **Mỗi class:** bảo đảm **constant_pool_count ≤ 65535**, index/tag hợp lệ; nhớ slot trống sau Long/Double và giới hạn số field/method/interface.
- **Mỗi Utf8 entry:** kiểm tra **MUTF-8 encoded bytes ≤ 65535**; đừng dùng Java String.length() làm đại diện độ dài byte.
- **Mỗi descriptor:** kiểm tra cú pháp và tối đa **255 parameter units**, có tính this đối với instance/interface invocation.
- **Mảng:** tối đa **255 chiều** trong các ràng buộc liên quan.
- **Phiên bản:** sinh class-file major/minor và attributes/tags mà JVM đích hỗ trợ.
- **QA:** dùng **javap -v/-c/-s**, parser/class verifier thích hợp và test chạy thực trên JDK mục tiêu; phân biệt lỗi format, verification và linking.
- **Khi vượt giới hạn:** tách method/class hoặc đưa dữ liệu sang resource theo đúng giới hạn bị chạm; kiểm tra lại hành vi và kích thước sản phẩm sau biên dịch.

### Tài liệu chuẩn

- **Java Virtual Machine Specification (Java SE 17), §4.1 — The ClassFile Structure**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1
- **§4.3.3 — Method Descriptors**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3
- **§4.4 — The Constant Pool**, đặc biệt §4.4.5 Long/Double và §4.4.7 Utf8: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- **§4.7.3 — The Code Attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3
- **§4.9 — Constraints on Java Virtual Machine Code**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.9
- **§4.11 — Limitations of the Java Virtual Machine**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.11

**Ghi nhớ:** giới hạn **65.535 byte** áp dụng cho instruction array của **một phương thức**, còn constant pool là tài nguyên dùng chung **trong một class** với **constant_pool_count u2**, slot đánh số từ 1 và quy tắc Long/Double chiếm hai slot. Một **CONSTANT_Utf8** chỉ chứa tối đa **65.535 byte Modified UTF-8**. Những giới hạn 255 parameter units, 65.535 local/stack units, 255 chiều mảng và các ràng buộc descriptor/verification là các lớp kiểm tra độc lập. Muốn xử lý đúng lỗi, hãy xác định **vùng nào của định dạng đã vượt ngưỡng**, rồi sửa tại đúng ranh giới đó.
