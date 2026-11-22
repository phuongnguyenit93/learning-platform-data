# Constant pool trong Java Class File

## 1. Constant pool là gì?

Khi javac biên dịch một tệp Java, compiler tạo ra tệp bytecode có phần cấu trúc gọi là **constant pool** (bảng hằng số). Đây là bảng dữ liệu được đánh chỉ số, lưu các giá trị hằng và thông tin mà bytecode cần tham chiếu, chẳng hạn:

- Tên lớp, interface, field và method.
- Descriptor mô tả kiểu dữ liệu và chữ ký phương thức.
- String literal và hằng số số học.
- Symbolic reference đến lớp, field, method và interface method.
- Method handle, method type, dynamic constant và thông tin liên quan đến invokedynamic.
- Tên module và package trong class file có dùng module system.

Constant pool là một phần của định dạng class file được đặc tả trong JVM Specification. JVM dựa vào bảng này để hiểu bytecode, nạp lớp và liên kết các tham chiếu khi chạy chương trình.

Không nên hiểu constant pool đơn giản là danh sách mọi biến hoặc mọi đối tượng của chương trình. Nó là cấu trúc dữ liệu của class file, gồm các entry có kiểu rõ ràng và có thể tham chiếu lẫn nhau bằng chỉ số. Các đối tượng Java thực tế được tạo trong bộ nhớ khi chương trình chạy; constant pool không phải vùng heap chứa toàn bộ object.

## 2. Constant pool nằm ở đâu trong class file?

Một class file có cấu trúc tổng quát như sau:

~~~text
ClassFile {
    magic
    minor_version
    major_version
    constant_pool_count
    constant_pool[]
    access_flags
    this_class
    super_class
    interfaces_count
    interfaces[]
    fields_count
    fields[]
    methods_count
    methods[]
    attributes_count
    attributes[]
}
~~~

Các thành phần đầu tiên có vai trò:

- **magic**: giá trị nhận diện class file, luôn là 0xCAFEBABE.
- **minor_version** và **major_version**: phiên bản định dạng class file.
- **constant_pool_count**: số lượng mục trong bảng cộng thêm một, theo quy tắc đánh chỉ số của class file.
- **constant_pool[]**: các entry hằng số và symbolic reference.
- **this_class** và **super_class**: chỉ số trỏ đến entry kiểu Class trong constant pool.
- Các trường, phương thức và attribute có thể tiếp tục tham chiếu đến entry trong constant pool.

Constant pool xuất hiện ngay sau các trường magic và version. Nó được dùng xuyên suốt class file: tên lớp, tên phương thức, descriptor, bytecode và nhiều attribute đều có thể chứa chỉ số trỏ về bảng này.

Ví dụ, với class file được tạo bởi javac --release 17, công cụ javap hiển thị major version là **61**. Phiên bản class file cho biết định dạng bytecode mục tiêu; nó không phải số lượng entry trong constant pool.

## 3. Cách đánh chỉ số và các quy tắc quan trọng

Constant pool dùng chỉ số bắt đầu từ **1**. Chỉ số 0 không đại diện cho một entry hợp lệ. Trường constant_pool_count có giá trị bằng số chỉ số có thể biểu diễn cộng một theo cấu trúc định dạng; các entry hợp lệ nằm trong khoảng từ 1 đến constant_pool_count - 1, có xét quy tắc entry chiếm hai slot.

Một số điểm cần nhớ:

1. Mỗi entry bắt đầu bằng một byte **tag** để xác định loại dữ liệu.
2. Các trường tiếp theo của entry có độ dài và ý nghĩa phụ thuộc tag.
3. Entry có thể tham chiếu entry khác bằng chỉ số.
4. **CONSTANT_Long** và **CONSTANT_Double** chiếm hai vị trí chỉ số liên tiếp. Vị trí thứ hai không phải một entry độc lập và không được tham chiếu như entry thông thường.
5. Không được giả định chỉ số constant pool giống nhau giữa hai lần biên dịch. Compiler có thể sắp xếp hoặc thêm entry theo cách khác.

Ví dụ minh họa:

~~~text
#10 = Class       #12
#12 = Utf8        demo/OrderService
#13 = Utf8        save
#14 = Utf8        (Ljava/lang/String;)V
#11 = NameAndType #13:#14
#9  = Methodref   #10.#11
~~~

Đây là cách biểu diễn khái niệm: entry Methodref kết hợp entry Class với entry NameAndType; NameAndType kết hợp tên method với descriptor. Các số #9, #10... chỉ có ý nghĩa trong class file cụ thể.

## 4. Các loại constant pool entry thường gặp

Mỗi entry có một tag số nguyên xác định cấu trúc. Các tag dưới đây thuộc định dạng class file hiện đại; một số tag được bổ sung ở các phiên bản Java sau.

| Tag | Tên entry | Công dụng |
|---:|---|---|
| 1 | CONSTANT_Utf8 | Lưu chuỗi dùng cho tên, descriptor và nội dung văn bản |
| 3 | CONSTANT_Integer | Hằng số nguyên 32 bit |
| 4 | CONSTANT_Float | Hằng số dấu phẩy động 32 bit |
| 5 | CONSTANT_Long | Hằng số nguyên 64 bit, chiếm hai slot |
| 6 | CONSTANT_Double | Hằng số dấu phẩy động 64 bit, chiếm hai slot |
| 7 | CONSTANT_Class | Tham chiếu tên lớp hoặc interface |
| 8 | CONSTANT_String | Tham chiếu một String literal |
| 9 | CONSTANT_Fieldref | Tham chiếu field của một lớp |
| 10 | CONSTANT_Methodref | Tham chiếu method của một lớp |
| 11 | CONSTANT_InterfaceMethodref | Tham chiếu method của interface |
| 12 | CONSTANT_NameAndType | Ghép tên thành viên với descriptor |
| 15 | CONSTANT_MethodHandle | Mô tả method handle |
| 16 | CONSTANT_MethodType | Mô tả kiểu phương thức |
| 17 | CONSTANT_Dynamic | Hằng số được liên kết động qua bootstrap method |
| 18 | CONSTANT_InvokeDynamic | Điểm gọi động được liên kết qua bootstrap method |
| 19 | CONSTANT_Module | Tên module |
| 20 | CONSTANT_Package | Tên package trong ngữ cảnh module |

Một số nhóm entry được bổ sung theo phiên bản class file:

- **MethodHandle**, **MethodType** và **InvokeDynamic** xuất hiện từ Java 7 (class file version 51).
- **Module** và **Package** xuất hiện từ Java 9 (version 53).
- **Dynamic** xuất hiện từ Java 11 (version 55).

Các JVM và compiler cũ không nhất thiết hiểu tag được bổ sung ở phiên bản mới. Khi class file dùng entry mới, runtime phải hỗ trợ phiên bản định dạng tương ứng.

## 5. CONSTANT_Utf8, Class và String

### CONSTANT_Utf8

**CONSTANT_Utf8** lưu chuỗi được class file dùng cho tên lớp, tên phương thức, tên field, descriptor, tên attribute và một số hằng văn bản khác.

Tên tag là Utf8 nhưng dữ liệu được mã hóa theo **Modified UTF-8** của định dạng class file, không nên mặc định đây là UTF-8 thông thường của mọi hệ thống. Công cụ như javap giải mã và hiển thị nội dung dễ đọc.

Ví dụ:

~~~text
#12 = Utf8  demo/OrderService
#13 = Utf8  save
#14 = Utf8  (Ljava/lang/String;)V
~~~

### CONSTANT_Class

Entry **CONSTANT_Class** trỏ đến một entry Utf8 chứa tên lớp hoặc interface. Với tên lớp thông thường, tên nội bộ dùng dấu gạch chéo / thay cho dấu chấm .

Ví dụ:

~~~text
#10 = Class  #12  // demo/OrderService
#12 = Utf8         // demo/OrderService
~~~

Một descriptor của kiểu tham chiếu có dạng Ljava/lang/String;. Descriptor của mảng, primitive và method tuân theo quy tắc riêng của JVM.

### CONSTANT_String

Entry **CONSTANT_String** trỏ đến entry Utf8 chứa nội dung String literal:

~~~text
#40 = String  #41  // JDK
#41 = Utf8          // JDK
~~~

Entry String trong class file không phải bản thân một object String được lưu trong bảng bytecode. Khi JVM xử lý string literal, nó tạo hoặc sử dụng đối tượng String canonical theo quy tắc của Java; các string literal tương đương được intern.

**String pool** thường được nhắc đến khi nói về String.intern() là cơ chế canonical hóa đối tượng String trong runtime. Nó có liên quan đến việc xử lý string literal, nhưng không đồng nhất với cấu trúc constant_pool trong file .class.

## 6. Symbolic reference: Fieldref, Methodref và NameAndType

Constant pool lưu nhiều tham chiếu theo tên và descriptor thay vì địa chỉ bộ nhớ trực tiếp. Những tham chiếu đó được gọi là **symbolic reference**.

### CONSTANT_NameAndType

Entry này kết hợp:

- Chỉ số đến Utf8 chứa tên field hoặc method.
- Chỉ số đến Utf8 chứa descriptor.

Ví dụ:

~~~text
#13 = Utf8         name
#14 = Utf8         Ljava/lang/String;
#11 = NameAndType  #13:#14  // name:Ljava/lang/String;
~~~

Descriptor Ljava/lang/String; mô tả một field có kiểu java.lang.String.

Với method, descriptor chứa danh sách kiểu tham số trong ngoặc và kiểu trả về ở phía sau. Ví dụ (I)Ljava/lang/String; nghĩa là nhận một tham số int và trả về String. ()V nghĩa là không có tham số và trả về void.

### CONSTANT_Fieldref

Entry **Fieldref** kết hợp lớp khai báo field với NameAndType:

~~~text
#9 = Fieldref  #10.#11  // demo/OrderService.name:Ljava/lang/String;
~~~

Bytecode như getfield, putfield, getstatic và putstatic sử dụng chỉ số tham chiếu field phù hợp.

### CONSTANT_Methodref và InterfaceMethodref

**Methodref** dùng cho tham chiếu method của lớp; **InterfaceMethodref** dùng cho tham chiếu method của interface. Chúng kết hợp tên lớp/interface với tên method và descriptor.

Các lệnh bytecode như invokevirtual, invokespecial, invokestatic và invokeinterface tham chiếu đến entry tương ứng trong constant pool. Việc tìm lớp, kiểm tra quyền truy cập và phân giải method được JVM thực hiện theo quy tắc liên kết của nó.

Symbolic reference giúp class file không phải lưu địa chỉ RAM của method hoặc field. Địa chỉ thực tế và cấu trúc runtime chỉ có thể được xác định trong quá trình nạp, liên kết và thực thi.

## 7. CONSTANT_Integer, Float, Long và Double

Constant pool có entry dành cho các giá trị số:

- **Integer**: giá trị nguyên 32 bit.
- **Float**: giá trị floating-point 32 bit.
- **Long**: giá trị nguyên 64 bit.
- **Double**: giá trị floating-point 64 bit.

Ví dụ:

~~~text
#38 = Integer 42
#39 = Float   3.14f
#40 = Long    9000000000l
#42 = Double  2.71828d
~~~

Long và Double chiếm hai slot trong bảng. Ví dụ sau một entry Long, chỉ số kế tiếp được dành riêng và không chứa entry độc lập. Vì vậy, không thể luôn đếm số dòng javap để suy ra constant_pool_count.

Không phải mọi số trong mã nguồn đều bắt buộc có entry constant pool. Compiler có thể dùng các lệnh bytecode với toán hạng trực tiếp như iconst, bipush hoặc sipush cho các giá trị phù hợp. Các giá trị khác có thể được nạp bằng ldc, ldc_w hoặc ldc2_w.

## 8. ConstantValue và compile-time constant

Class file có attribute **ConstantValue** để cung cấp giá trị khởi tạo cho một số field static. Attribute này không phải tag entry độc lập trong constant pool; trường constantvalue_index của nó trỏ đến entry hằng số thích hợp.

Ví dụ:

~~~java
public class Constants {
    public static final int LIMIT = 42;
    public static final String LABEL = "JDK";
    public static final Integer BOXED = 42;
}
~~~

Với javap -v, phần field có thể hiển thị:

~~~text
static final int LIMIT;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 42

static final java.lang.String LABEL;
  descriptor: Ljava/lang/String;
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: String JDK
~~~

Java định nghĩa **constant variable** là biến final có kiểu primitive hoặc String và được khởi tạo bằng constant expression. LIMIT và LABEL trong ví dụ là constant variable; BOXED không phải vì kiểu của nó là Integer, không phải primitive hay String.

Compiler có thể đưa giá trị của constant variable trực tiếp vào bytecode của lớp sử dụng. Điều này thường được gọi là **constant inlining**.

Ví dụ:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println(Constants.LIMIT);
        System.out.println(Constants.LABEL);
        System.out.println(Constants.BOXED);
    }
}
~~~

Khi xem bytecode của Client, có thể thấy dạng tương tự:

~~~text
bipush        42
ldc           // String JDK
getstatic     // demo/Constants.BOXED:Ljava/lang/Integer;
~~~

Hai giá trị primitive và String được nhúng vào bytecode của Client; trường Integer vẫn được đọc qua field reference lúc chạy.

Hệ quả quan trọng: nếu thư viện thay đổi giá trị public static final là constant variable, các client đã biên dịch trước đó có thể vẫn giữ giá trị cũ. Cần biên dịch lại các client phụ thuộc để cập nhật giá trị được inline. Đây là một vấn đề tương thích nhị phân cần cân nhắc khi thiết kế API thư viện.

## 9. Runtime constant pool là gì?

Khi JVM tạo runtime representation cho một lớp hoặc interface, nó có một **runtime constant pool** tương ứng. Runtime constant pool được xây dựng từ cấu trúc constant_pool trong class file và phục vụ việc nạp, liên kết, phân giải symbolic reference và xử lý các giá trị động.

Phân biệt hai khái niệm:

| Class-file constant_pool | Runtime constant pool |
|---|---|
| Nằm trong tệp .class | Tồn tại trong runtime representation của lớp/interface |
| Có cấu trúc entry và chỉ số theo JVM Specification | Được JVM tạo từ class file khi lớp được tạo |
| Lưu giá trị hằng và symbolic reference | Dùng trong quá trình liên kết và thực thi |
| Có thể được kiểm tra bằng javap -v | Không thể đọc trực tiếp như một bảng class file đã lưu trên đĩa |

Runtime constant pool không phải một bản sao byte-for-byte mà ứng dụng có thể chỉnh sửa trực tiếp. JVM có thể biểu diễn các tham chiếu đã phân giải theo cách nội bộ riêng.

Trong quá trình **resolution**, JVM biến symbolic reference thành tham chiếu runtime thích hợp, chẳng hạn xác định lớp, field hoặc method được chỉ ra. Việc phân giải có thể được thực hiện sớm hoặc trì hoãn tùy cách JVM triển khai, trong giới hạn quy định của JVM Specification.

Nếu tham chiếu không thể được phân giải, JVM có thể ném lỗi liên kết tương ứng như NoClassDefFoundError, NoSuchFieldError, NoSuchMethodError hoặc lỗi truy cập. Vì vậy, một class file có thể biên dịch thành công nhưng vẫn thất bại khi chạy nếu dependency hoặc API thực tế không tương thích.

## 10. MethodHandle, MethodType, Dynamic và InvokeDynamic

Các phiên bản Java mới mở rộng constant pool để hỗ trợ cơ chế gọi động và liên kết linh hoạt.

### MethodHandle và MethodType

**CONSTANT_MethodHandle** mô tả một handle trỏ đến field hoặc method theo một loại tham chiếu xác định. **CONSTANT_MethodType** mô tả kiểu chữ ký phương thức.

Các cấu trúc này là nền tảng cho API java.lang.invoke, bao gồm MethodHandle và MethodType. Chúng cho phép runtime biểu diễn thao tác gọi method một cách linh hoạt mà không chỉ dựa trên cơ chế invoke truyền thống.

### InvokeDynamic

**CONSTANT_InvokeDynamic** mô tả một call site được liên kết thông qua bootstrap method. Entry này chứa chỉ số đến mục bootstrap trong attribute BootstrapMethods và chỉ số NameAndType mô tả tên cùng descriptor của call site.

Bytecode invokedynamic tham chiếu đến entry InvokeDynamic. Khi liên kết call site, JVM gọi bootstrap method để nhận một CallSite và dùng target method handle của call site đó cho các lần gọi tiếp theo.

Một trường hợp dễ quan sát là nối chuỗi trong javac hiện đại. Từ Java 9, javac thường biên dịch string concatenation bằng invokedynamic và bootstrap method của StringConcatFactory. Đây là chi tiết triển khai compiler/runtime; không nên giả định mọi compiler hoặc mọi phiên bản luôn sinh bytecode giống hệt nhau.

### BootstrapMethods attribute

Attribute **BootstrapMethods** nằm trong danh sách attribute cấp lớp. Nó chứa các bootstrap method handle và các đối số bootstrap được tham chiếu bởi entry Dynamic hoặc InvokeDynamic.

Ví dụ đầu ra javap có thể hiển thị:

~~~text
#15 = InvokeDynamic #0:#16
#51 = MethodHandle ... StringConcatFactory.makeConcatWithConstants
...
BootstrapMethods:
  0: REF_invokeStatic StringConcatFactory.makeConcatWithConstants
     Method arguments:
       #49 Hello, \u0001 #\u0001 JDK 42
~~~

Các ký hiệu \u0001 trong recipe của StringConcatFactory đánh dấu vị trí nhận giá trị động. Đây là một ví dụ về cách compiler biểu diễn phép nối chuỗi; ứng dụng không cần tự tạo các entry này.

### Dynamic constant

**CONSTANT_Dynamic** (thường gọi là condy) mô tả một hằng số được tính hoặc liên kết qua bootstrap method. Nó khác InvokeDynamic: Dynamic tạo ra một giá trị hằng cho constant pool; InvokeDynamic tạo ra một call site cho thao tác gọi.

Dynamic constant được thêm vào class file từ Java 11. Nó hỗ trợ các giá trị có thể khởi tạo động mà vẫn được biểu diễn như hằng số trong constant pool.

## 11. Cách bytecode sử dụng constant pool

Nhiều lệnh bytecode chứa chỉ số constant pool:

| Lệnh | Công dụng thường gặp |
|---|---|
| ldc, ldc_w | Nạp một hằng số từ constant pool |
| ldc2_w | Nạp hằng Long hoặc Double |
| getfield, putfield | Đọc/ghi field instance qua Fieldref |
| getstatic, putstatic | Đọc/ghi field static qua Fieldref |
| invokevirtual | Gọi method instance qua Methodref |
| invokespecial | Gọi constructor hoặc method đặc biệt |
| invokestatic | Gọi method static |
| invokeinterface | Gọi method interface |
| invokedynamic | Gọi call site được liên kết động |

Khi javap hiển thị:

~~~text
5: getfield      #9  // Field name:Ljava/lang/String;
12: invokevirtual #26 // Method greet:(I)Ljava/lang/String;
~~~

Chỉ số #9 hoặc #26 trỏ đến entry trong constant pool của chính class file đang xem. Comment phía sau là cách javap giải mã entry thành tên field hoặc method để người đọc dễ hiểu.

Không nên lưu các số #9, #26 từ một lần biên dịch vào tài liệu như thể chúng cố định. Khi thay đổi source code, compiler version hoặc tùy chọn biên dịch, thứ tự entry có thể thay đổi.

## 12. Thực hành: biên dịch và xem constant pool bằng javap

Tạo cấu trúc thư mục:

~~~text
project/
  src/
    demo/
      ConstantPoolDemo.java
  out/
~~~

Tạo file src/demo/ConstantPoolDemo.java:

~~~java
package demo;

public class ConstantPoolDemo {
    static final int LIMIT = 42;
    static final String LABEL = "JDK";
    private String name = "Ada";

    public String greet(int number) {
        return "Hello, " + name + " #" + number + " " + LABEL + " " + LIMIT;
    }

    public static void main(String[] args) {
        System.out.println(new ConstantPoolDemo().greet(7));
    }
}
~~~

Biên dịch với mục tiêu Java 17:

~~~bash
javac --release 17 -d out src/demo/ConstantPoolDemo.java
~~~

Chạy:

~~~bash
java -cp out demo.ConstantPoolDemo
~~~

Kết quả chính xác:

~~~text
Hello, Ada #7 JDK 42
~~~

Xem constant pool và các attribute:

~~~bash
javap -v -cp out demo.ConstantPoolDemo
~~~

Hoặc xem đồng thời bytecode và constant pool:

~~~bash
javap -c -v -cp out demo.ConstantPoolDemo
~~~

Trong kết quả, tìm phần Constant pool:. Một lần biên dịch với javac tương thích Java 17 có thể cho các entry tương tự:

~~~text
#1  = Methodref       #2.#3
#2  = Class           #4             // java/lang/Object
#7  = String          #8             // Ada
#9  = Fieldref        #10.#11        // demo/ConstantPoolDemo.name:Ljava/lang/String;
#15 = InvokeDynamic   #0:#16         // makeConcatWithConstants
#35 = Utf8            LIMIT
#38 = Integer         42
#39 = Utf8            LABEL
#41 = Utf8            JDK
#48 = Utf8            BootstrapMethods
~~~

Các chỉ số và số lượng entry có thể khác giữa compiler version hoặc tùy chọn biên dịch. Hãy tập trung vào tag và quan hệ tham chiếu, không phụ thuộc số thứ tự cụ thể.

Ở phần khai báo field, javap có thể hiển thị:

~~~text
static final int LIMIT;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 42

static final java.lang.String LABEL;
  descriptor: Ljava/lang/String;
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: String JDK
~~~

Ở phần method greet, có thể quan sát lệnh getfield đọc trường name và lệnh invokedynamic thực hiện nối chuỗi. Attribute BootstrapMethods ở cuối class file cho biết bootstrap method được sử dụng.

## 13. Những hiểu nhầm thường gặp

### Constant pool chính là String pool

Không đúng. Constant pool là bảng entry trong class file. String pool là cơ chế runtime liên quan đến việc intern và tái sử dụng String canonical. Entry CONSTANT_String có thể dẫn đến việc JVM tạo hoặc lấy String literal đã intern, nhưng hai khái niệm có vai trò khác nhau.

### Mọi literal đều bắt buộc nằm trong constant pool

Không đúng. Compiler có thể dùng lệnh bytecode chứa trực tiếp giá trị nhỏ như iconst_0, bipush hoặc sipush. Các giá trị khác có thể dùng ldc và constant pool. Cách biểu diễn phụ thuộc loại giá trị và lựa chọn compiler.

### Constant pool chứa địa chỉ RAM của method

Không đúng. Fieldref và Methodref là symbolic reference gồm tên lớp, tên thành viên và descriptor. JVM phân giải chúng trong quá trình liên kết; class file không chứa địa chỉ RAM cố định.

### Constant pool của mọi class là một bảng dùng chung

Không đúng. Mỗi class file có constant pool riêng. Khi một lớp hoặc interface được tạo trong JVM, nó có runtime constant pool tương ứng. Các lớp có thể tham chiếu đến cùng một kiểu hoặc chuỗi, nhưng điều đó không biến các bảng class-file thành một bảng chung.

### Số thứ tự #n là cố định

Không đúng. Chỉ số chỉ có ý nghĩa trong một class file cụ thể. Không dùng chỉ số constant pool để nhận diện một method giữa các bản build; hãy đọc tag, tên, descriptor và nội dung được javap giải mã.

### Thay đổi constant trong thư viện sẽ tự cập nhật mọi ứng dụng

Không đúng với compile-time constant được inline. Client đã biên dịch có thể chứa giá trị cũ ngay trong bytecode. Cần biên dịch lại client để nhận giá trị mới.

## 14. Checklist khi phân tích constant pool

- [ ] Xác định class file và phiên bản bằng javap -v.
- [ ] Tìm phần Constant pool: và nhận diện tag của entry.
- [ ] Phân biệt Utf8, Class, String, NameAndType và các symbolic reference.
- [ ] Nhớ Long và Double chiếm hai slot.
- [ ] Đọc descriptor để hiểu kiểu field và chữ ký method.
- [ ] Dùng javap -c -v để nối chỉ số constant pool với lệnh bytecode.
- [ ] Kiểm tra ConstantValue khi phân tích static final constant variable.
- [ ] Nhận diện InvokeDynamic, MethodHandle và BootstrapMethods khi phân tích lambda hoặc string concatenation.
- [ ] Phân biệt class-file constant_pool, runtime constant pool và String pool.
- [ ] Không phụ thuộc vào chỉ số #n giữa các lần build.
- [ ] Khi thay đổi compile-time constant trong thư viện, xem xét việc biên dịch lại client.
