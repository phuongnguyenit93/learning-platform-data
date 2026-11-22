# Xem khai báo class bằng javap

javap là công cụ dòng lệnh đi kèm JDK, dùng để đọc cấu trúc của lớp Java đã biên dịch. Khi cần biết một class có modifier nào, kế thừa lớp nào, triển khai interface nào, có constructor, field và method gì, javap giúp xem thông tin trực tiếp từ file .class hoặc thư viện JAR.

Công cụ này hữu ích khi đọc API của thư viện bên thứ ba, kiểm tra artifact sau khi build, điều tra lỗi liên kết giữa các lớp, xác minh chữ ký phương thức và so sánh hai phiên bản thư viện. javap hiển thị khai báo theo dạng gần giống mã nguồn Java, đồng thời có thể hiển thị descriptor và metadata ở mức bytecode.

## 1. javap đọc gì?

Mã nguồn Java được biên dịch thành bytecode trong các file .class. File class lưu thông tin về:

- Tên lớp, package và các modifier như public, abstract hoặc final.
- Lớp cha và các interface mà lớp triển khai.
- Constructor, field và method.
- Kiểu dữ liệu, tham số, kiểu trả về và mức truy cập của thành viên.
- Các thuộc tính bổ sung như generic Signature, annotation, constant value, thông tin debug và bytecode của method.

javap đọc những thông tin này và trình bày theo nhiều mức chi tiết. Khi chỉ cần xem API công khai, dùng chế độ lọc thành viên. Khi cần điều tra chữ ký JVM, dùng -s. Khi cần xem metadata sâu hơn, dùng -v.

javap làm việc với bytecode đã biên dịch. Nó không cần file .java gốc, nhưng cũng không tái tạo đầy đủ mã nguồn ban đầu: comment, cách đặt tên biến cục bộ khi không có debug metadata, cấu trúc biểu thức ban đầu và nhiều chi tiết định dạng nguồn không được lưu trong class file.

## 2. Cài đặt và kiểm tra javap

javap là một công cụ của JDK. Nếu máy đã cài JDK và thư mục bin của JDK có trong PATH, có thể gọi trực tiếp:

~~~bash
javap --version
javap --help
~~~

Kiểm tra phiên bản Java và compiler để biết môi trường đang dùng:

~~~bash
java -version
javac -version
javap --version
~~~

Trên Windows, có thể xác định executable đang được gọi bằng:

~~~powershell
where.exe javap
~~~

Trên Linux hoặc macOS:

~~~bash
type -a javap
~~~

Nếu javap không được nhận diện, kiểm tra PATH có chứa thư mục bin của JDK hay không. Không nhầm javap với java: java khởi chạy ứng dụng, javac biên dịch mã nguồn, còn javap đọc cấu trúc file class.

## 3. Cú pháp cơ bản

Cú pháp phổ biến:

~~~bash
javap [options] class
~~~

Đối số class thường là tên nhị phân đầy đủ của lớp, bao gồm package. Ví dụ:

~~~bash
javap java.lang.String
javap java.util.ArrayList
~~~

Với lớp của dự án, javap cần biết nơi tìm file .class. Dùng classpath:

~~~bash
javap -classpath out com.acme.model.Customer
~~~

Trong ví dụ này:

- out là thư mục gốc chứa cây package đã biên dịch.
- com.acme.model.Customer là tên nhị phân đầy đủ của lớp.
- Không nối tên package bằng dấu gạch chéo khi truyền tên lớp theo dạng class name.
- Không cần thêm phần mở rộng .class khi truyền tên nhị phân đầy đủ.

Có thể truyền trực tiếp đường dẫn tới file class trong một số tình huống, ví dụ:

~~~bash
javap -private out/com/acme/model/Customer.class
~~~

Cách dùng class name kết hợp với -classpath thường thuận tiện hơn khi lớp nằm trong cấu trúc package hoặc khi kiểm tra JAR.

## 4. Ví dụ thực hành: xem khai báo một class

Tạo cấu trúc thư mục:

~~~text
javap-demo/
└── src/
    └── com/
        └── acme/
            └── model/
                └── Customer.java
~~~

Tệp src/com/acme/model/Customer.java:

~~~java
package com.acme.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public static Customer guest() {
        return new Customer("Guest");
    }
}
~~~

Biên dịch từ thư mục javap-demo:

~~~bash
javac -d out src/com/acme/model/Customer.java
~~~

Sau khi biên dịch, file class được tạo tại:

~~~text
out/com/acme/model/Customer.class
~~~

Xem khai báo lớp:

~~~bash
javap -classpath out com.acme.model.Customer
~~~

Kết quả điển hình:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  public com.acme.model.Customer(java.lang.String);
  public java.lang.String name();
  public static com.acme.model.Customer guest();
}
~~~

Từ kết quả này có thể đọc được:

- Lớp có tên đầy đủ là com.acme.model.Customer.
- Lớp có modifier public và final.
- Constructor nhận một tham số String.
- Method name() trả về String.
- Method guest() là static và trả về Customer.

Mặc định, javap không hiển thị field private trong kết quả này. Muốn xem cả field và thành viên private, cần dùng tùy chọn -private.

## 5. Lọc thành viên theo mức truy cập

Một trong những tác vụ thường gặp là kiểm tra API mà lớp cung cấp cho mã bên ngoài. javap có các tùy chọn lọc theo visibility:

| Tùy chọn | Thành viên được hiển thị |
|---|---|
| -public | Chỉ public class và public member. |
| -protected | public và protected. |
| -package | public, protected và package-private. Đây là mức mặc định. |
| -private | Tất cả mức truy cập, bao gồm private. |
| -p | Viết tắt của -private. |

Ví dụ chỉ xem API public:

~~~bash
javap -public -classpath out com.acme.model.Customer
~~~

Xem cả public và protected:

~~~bash
javap -protected -classpath out com.acme.model.Customer
~~~

Xem các thành viên package-private trở lên:

~~~bash
javap -package -classpath out com.acme.model.Customer
~~~

Xem đầy đủ các thành viên:

~~~bash
javap -private -classpath out com.acme.model.Customer
~~~

Với class Customer ở trên, kết quả của -private có thể có dạng:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  private final java.lang.String name;
  public com.acme.model.Customer(java.lang.String);
  public java.lang.String name();
  public static com.acme.model.Customer guest();
}
~~~

Field name có mức truy cập private nên chỉ xuất hiện khi dùng -private hoặc -p. Đây là cách nhanh để kiểm tra một thư viện có field/method nội bộ nào, hoặc xác nhận một thành viên có thực sự public như tài liệu mô tả hay không.

Lưu ý: javap chỉ hiển thị thông tin class file. Modifier private giúp giới hạn truy cập theo quy tắc Java, nhưng không phải cơ chế mã hóa hay bảo vệ nội dung file class khỏi việc kiểm tra.

## 6. Đọc class header, superclass và interface

Phần đầu của kết quả javap mô tả khai báo lớp. Ví dụ:

~~~text
public abstract class com.acme.service.BaseService
    extends com.acme.service.AbstractComponent
    implements com.acme.service.Reloadable, java.io.Closeable
~~~

Có thể đọc được:

- public: lớp có thể được truy cập từ package khác nếu module/package cho phép.
- abstract: không thể tạo instance trực tiếp bằng constructor thông thường.
- extends: lớp cha trực tiếp.
- implements: các interface được triển khai.

Với interface, kết quả có thể hiển thị dạng:

~~~text
public interface com.acme.service.Reloadable
~~~

Với enum hoặc record, javap thể hiện cấu trúc class file tương ứng; lớp record thường có superclass là java.lang.Record và các accessor được sinh cho component. Một số thành viên được compiler sinh tự động có thể xuất hiện khi xem đầy đủ.

Không nên kết luận chỉ dựa trên một dòng header. Dùng -private hoặc -v nếu cần kiểm tra constructor, field, method được sinh tự động, bridge method hoặc metadata của class.

## 7. Xem chữ ký JVM bằng -s

Tùy chọn -s yêu cầu javap hiển thị internal type signature, thường được gọi là JVM descriptor, bên dưới mỗi field hoặc method.

~~~bash
javap -s -classpath out com.acme.model.Customer
~~~

Ví dụ kết quả:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  public com.acme.model.Customer(java.lang.String);
    descriptor: (Ljava/lang/String;)V
  public java.lang.String name();
    descriptor: ()Ljava/lang/String;
  public static com.acme.model.Customer guest();
    descriptor: ()Lcom/acme/model/Customer;
}
~~~

Descriptor mô tả kiểu tham số và kiểu trả về theo định dạng JVM. Các ký hiệu cơ bản:

| Ký hiệu | Kiểu Java |
|---|---|
| B | byte |
| C | char |
| D | double |
| F | float |
| I | int |
| J | long |
| S | short |
| Z | boolean |
| V | void |
| Lpackage/Type; | Kiểu tham chiếu |
| [ | Mảng |

Với method, descriptor có dạng:

~~~text
(parameter-descriptors)return-descriptor
~~~

Ví dụ:

- ()V: không có tham số, trả về void.
- (I)I: nhận int, trả về int.
- (Ljava/lang/String;)V: nhận String, trả về void.
- ([Ljava/lang/String;)V: nhận mảng String, trả về void.

Descriptor hữu ích khi điều tra lỗi liên kết như NoSuchMethodError. JVM xác định method theo tên và descriptor; chỉ thay đổi kiểu tham số hoặc kiểu trả về có thể làm descriptor thay đổi, dù tên method không đổi.

## 8. Phân biệt generic Signature và descriptor

Generic trong Java được triển khai chủ yếu bằng type erasure. Vì vậy, descriptor của method generic thường chứa kiểu sau khi xóa tham số kiểu, trong khi generic Signature attribute lưu thêm thông tin kiểu tổng quát để compiler và reflection sử dụng khi phù hợp.

Ví dụ, tệp src/com/acme/model/Registry.java:

~~~java
package com.acme.model;

import java.util.List;

public class Registry<T> {
    private final List<T> entries;

    public Registry(List<T> entries) {
        this.entries = entries;
    }

    public T first() {
        return entries.get(0);
    }
}
~~~

Biên dịch:

~~~bash
javac -d out src/com/acme/model/Registry.java
~~~

Xem descriptor:

~~~bash
javap -s -classpath out com.acme.model.Registry
~~~

Method first() có descriptor sau type erasure tương đương:

~~~text
descriptor: ()Ljava/lang/Object;
~~~

Vì T bị xóa thành Object theo quy tắc erasure trong ví dụ này.

Để xem generic Signature attribute và metadata chi tiết:

~~~bash
javap -v -classpath out com.acme.model.Registry
~~~

Trong output verbose, tìm các dòng có nhãn Signature. Chúng cho biết thông tin generic được lưu trong class file. Không nên nhầm descriptor với generic Signature: descriptor phục vụ liên kết ở mức JVM, còn Signature giữ thêm thông tin kiểu tổng quát.

## 9. Xem constant và field static final

Tùy chọn -constants hiển thị giá trị của các trường static final có constant value trong class file:

~~~bash
javap -constants -classpath out com.acme.config.AppConfig
~~~

Ví dụ nguồn:

~~~java
package com.acme.config;

public class AppConfig {
    public static final int RETRY_LIMIT = 3;
    public static final String MODE = "SAFE";
}
~~~

Sau khi biên dịch, javap -constants có thể hiển thị giá trị:

~~~text
public class com.acme.config.AppConfig {
  public static final int RETRY_LIMIT = 3;
  public static final java.lang.String MODE = "SAFE";
}
~~~

Tùy chọn này hữu ích khi kiểm tra constant được đóng gói vào thư viện, xác minh giá trị mặc định hoặc điều tra thay đổi hằng số giữa hai phiên bản artifact.

Không phải mọi field static final đều có ConstantValue attribute. Giá trị được khởi tạo bằng biểu thức runtime có thể không được hiển thị theo cách này. Hãy xem cả bytecode của static initializer nếu cần hiểu cách khởi tạo.

## 10. Xem thông tin chi tiết bằng -v

Tùy chọn -v (verbose) yêu cầu javap hiển thị nhiều thông tin class file hơn, bao gồm:

- Minor/major version của class file.
- Access flags của lớp và thành viên.
- Constant pool.
- Field và method descriptor.
- Attribute như Signature, Exceptions, RuntimeVisibleAnnotations.
- StackMapTable và các metadata phục vụ kiểm tra bytecode.
- Một số thông tin liên quan tới bootstrap method hoặc inner class.

Ví dụ:

~~~bash
javap -v -classpath out com.acme.model.Customer
~~~

Output verbose có thể rất dài. Khi điều tra một chi tiết cụ thể, tìm các nhãn như Classfile, major version, flags, descriptor, Signature, RuntimeVisibleAnnotations hoặc ConstantValue.

Phiên bản class file giúp xác định compiler đã tạo bytecode cho mức Java nào. Ví dụ, Java 17 dùng major version 61. Nếu một runtime quá cũ cố nạp class file có major version cao hơn mức hỗ trợ, có thể gặp UnsupportedClassVersionError.

Không nên dùng -v như lựa chọn mặc định khi chỉ cần xem API. Output chi tiết dễ gây nhiễu và khó so sánh; bắt đầu bằng -public hoặc -private, sau đó thêm -s hoặc -v khi có câu hỏi cụ thể.

## 11. Xem bytecode và debug metadata

Mục tiêu chính của bài này là xem khai báo class, nhưng javap còn hỗ trợ một số chế độ để kiểm tra cách method được biên dịch:

| Tùy chọn | Công dụng |
|---|---|
| -c | Hiển thị bytecode instructions của từng method. |
| -l | Hiển thị line number table và local variable table nếu có. |
| -s | Hiển thị descriptor của field và method. |
| -v | Hiển thị thông tin class file chi tiết. |

Ví dụ:

~~~bash
javap -c -classpath out com.acme.model.Customer
javap -l -classpath out com.acme.model.Customer
~~~

-c hữu ích khi kiểm tra method gọi API nào, compiler tạo lệnh invoke nào hoặc một biểu thức được biên dịch ra sao. -l hữu ích khi cần xem thông tin dòng nguồn và biến cục bộ đã được lưu trong debug metadata.

Thông tin local variable có thể không xuất hiện nếu compiler không tạo metadata tương ứng. Khi cần, biên dịch với javac -g để yêu cầu ghi thông tin debug:

~~~bash
javac -g -d out src/com/acme/model/Customer.java
~~~

Tùy chọn -g ảnh hưởng metadata debug trong class file; nó không thay đổi khai báo API public của lớp. Để xem lại các thông tin này, dùng javap -l hoặc javap -v.

## 12. Xem class trong JAR và thư viện bên ngoài

javap có thể đọc class nằm trong JAR bằng cách đưa JAR vào classpath.

Ví dụ:

~~~bash
javap -classpath lib/customer-api.jar -public com.acme.api.Customer
~~~

Nếu cần kết hợp thư mục output với nhiều JAR:

~~~bash
javap -classpath "out:lib/api.jar:lib/common.jar" -private com.acme.api.Customer
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
javap -classpath "out;lib/api.jar;lib/common.jar" -private com.acme.api.Customer
~~~

Trên Linux và macOS, dấu phân cách classpath là dấu hai chấm. Hãy đặt toàn bộ giá trị classpath trong dấu nháy để shell truyền thành một đối số, đặc biệt khi đường dẫn có khoảng trắng.

Có thể kiểm tra lớp trong thư viện nền tảng:

~~~bash
javap -public java.util.ArrayList
~~~

Khi kiểm tra class trong named module, javap hỗ trợ các tùy chọn module path và module. Cú pháp cụ thể có thể xem bằng:

~~~bash
javap --help
~~~

Phân biệt classpath và module path: classpath tìm lớp theo cơ chế class loader truyền thống; module path tìm các module đã đóng gói hoặc module directory theo JPMS. Chọn đúng cách tra cứu theo cách thư viện được phân phối.

## 13. Overload, constructor và nested class

Một lớp có thể có nhiều method cùng tên nhưng khác danh sách tham số. javap hiển thị từng overload riêng:

~~~java
package com.acme.math;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public long add(long a, long b) {
        return a + b;
    }
}
~~~

Sau khi biên dịch, xem descriptor:

~~~bash
javap -s -classpath out com.acme.math.Calculator
~~~

Hai method add có descriptor khác nhau:

~~~text
add(int, int)   -> (II)I
add(long, long) -> (JJ)J
~~~

Constructor cũng xuất hiện trong danh sách member. Constructor không có kiểu trả về trong cách viết Java, nhưng descriptor JVM của nó luôn kết thúc bằng V vì constructor có tên đặc biệt <init> và không trả về giá trị.

Lớp lồng nhau thường được biên dịch thành file class riêng với tên nhị phân chứa dấu $. Ví dụ, lớp com.acme.Outer có nested class Inner có thể được kiểm tra bằng:

~~~bash
javap -private -classpath out 'com.acme.Outer$Inner'
~~~

Dấu nháy giúp shell không diễn giải ký tự $ như biến. Trên PowerShell, chuỗi trong dấu nháy đơn cũng giữ nguyên ký tự này.

## 14. Dùng javap để so sánh API giữa hai phiên bản

Khi nâng cấp thư viện, có thể xem khai báo của cùng một lớp trong hai JAR khác nhau:

~~~bash
javap -public -s -classpath old-api.jar com.acme.api.Client
javap -public -s -classpath new-api.jar com.acme.api.Client
~~~

So sánh kết quả để phát hiện:

- Method public bị xóa hoặc đổi tên.
- Kiểu tham số hoặc kiểu trả về thay đổi.
- Constructor bị thay đổi.
- Field public/static bị thay đổi.
- Lớp đổi superclass hoặc interface.
- Descriptor không còn tương thích với bytecode của client cũ.

Nếu cần so sánh tự động, có thể chuyển output ra file rồi dùng công cụ diff của hệ điều hành:

~~~bash
javap -public -s -classpath old-api.jar com.acme.api.Client > old.txt
javap -public -s -classpath new-api.jar com.acme.api.Client > new.txt
diff -u old.txt new.txt
~~~

Trên PowerShell, có thể lưu output bằng toán tử chuyển hướng và so sánh bằng Compare-Object. Khi so sánh, hãy dùng cùng phiên bản javap và cùng tùy chọn để giảm khác biệt không liên quan.

javap là công cụ kiểm tra hữu ích nhưng không phải bộ kiểm tra binary compatibility hoàn chỉnh. Đối với thư viện có yêu cầu tương thích nghiêm ngặt, nên kết hợp công cụ phân tích API chuyên dụng, kiểm thử client thực tế và quy trình quản lý phiên bản.

## 15. Lỗi thường gặp khi dùng javap

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Error: class not found | Tên lớp sai hoặc classpath không trỏ tới package root/JAR chứa lớp. | Kiểm tra tên nhị phân đầy đủ và đường dẫn classpath. |
| javap không tìm thấy file class vừa biên dịch | Đầu ra javac nằm ở thư mục khác hoặc dùng sai package path. | Kiểm tra tùy chọn -d của javac và dùng đúng classpath root. |
| Chỉ thấy method public, không thấy field private | javap đang dùng mức hiển thị mặc định hoặc -public. | Thêm -private hoặc -p. |
| Không thấy generic type như mong đợi trong descriptor | Descriptor JVM dùng type erasure. | Dùng -v và tìm Signature attribute. |
| Không thấy giá trị static final | Field không có constant value attribute hoặc chưa dùng -constants. | Dùng -constants và kiểm tra cách field được khởi tạo. |
| Không có tên biến cục bộ hoặc số dòng nguồn | Class file không chứa debug metadata tương ứng. | Biên dịch với -g rồi xem bằng -l hoặc -v. |
| Output quá dài và khó đọc | Dùng -v hoặc -c trong khi chỉ cần khai báo. | Bắt đầu bằng -public, -protected hoặc -private; thêm tùy chọn khi cần. |
| Nhầm lớp lồng nhau | Dùng tên source-level thay cho binary name. | Dùng tên nhị phân có dấu $ và đặt trong dấu nháy. |
| Không đọc được lớp trong module | Dùng classpath cho artifact được phân phối theo module hoặc thiếu module path. | Kiểm tra cách đóng gói và dùng tùy chọn module phù hợp. |

## 16. Quy trình kiểm tra khai báo class

Khi nhận một class hoặc thư viện cần điều tra, có thể làm theo trình tự:

1. Xác định file .class, JAR hoặc module chứa lớp.
2. Xác định tên package và tên nhị phân đầy đủ của class.
3. Dùng -classpath hoặc module path phù hợp để javap tìm đúng artifact.
4. Bắt đầu bằng -public để xem API bên ngoài.
5. Dùng -protected hoặc -package khi cần xem thêm mức truy cập.
6. Dùng -private để kiểm tra toàn bộ field, constructor và method.
7. Dùng -s để xác minh descriptor của method/field.
8. Dùng -constants để kiểm tra hằng số được lưu trong class file.
9. Dùng -v khi cần generic Signature, annotation, class file version hoặc access flags.
10. Dùng -c và -l khi cần kiểm tra bytecode và debug metadata.
11. Khi nâng cấp thư viện, so sánh khai báo của hai artifact bằng cùng tùy chọn và cùng phiên bản javap.

## 17. Ghi nhớ

javap giúp nhìn thấy cấu trúc thực tế của class file sau khi biên dịch. Đối với việc xem khai báo class, các tùy chọn quan trọng nhất là -public, -protected, -package và -private để lọc thành viên; -s để đọc descriptor; -constants để xem hằng số; và -v để kiểm tra metadata sâu hơn.

Khi biết cách chọn đúng classpath, dùng tên nhị phân đầy đủ và phân biệt descriptor với generic Signature, nhà phát triển có thể kiểm tra API của chính dự án hoặc thư viện bên ngoài, xác minh thay đổi giữa các phiên bản và tìm nguyên nhân của lỗi liên kết mà không cần mã nguồn gốc.
