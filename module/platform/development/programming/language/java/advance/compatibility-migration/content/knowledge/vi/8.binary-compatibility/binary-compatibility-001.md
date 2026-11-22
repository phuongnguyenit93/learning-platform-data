# Tên nhị phân, symbolic reference và quá trình liên kết lớp

Một ứng dụng Java không gọi class và method bằng cách tra cứu source code mỗi khi chạy. Sau khi biên dịch, bytecode lưu các tham chiếu tới kiểu, field và method theo tên cùng descriptor. Khi ứng dụng được nạp và chạy với các phiên bản thư viện khác nhau, JVM phải tìm đúng class, xác định đúng thành viên và kiểm tra rằng các tham chiếu đó vẫn hợp lệ. Đây là nền tảng của **binary compatibility** và cũng là lý do một thay đổi nhỏ trong thư viện có thể chỉ phát sinh lỗi khi ứng dụng chạy.

Để hiểu lỗi liên kết khi migration, cần phân biệt ba khái niệm: **binary name** là tên định danh lớp ở mức nhị phân; **symbolic reference** là tham chiếu được ghi trong class file tới một lớp hoặc thành viên; **linking** là quá trình JVM kiểm tra và phân giải các tham chiếu đó để có thể thực thi bytecode.

## 1. Tên lớp ở các tầng khác nhau

Một kiểu Java có thể được biểu diễn bằng nhiều dạng tên tùy ngữ cảnh. Không nên nhầm tên dùng trong source code với tên mà class file hoặc JVM sử dụng.

### 1.1. Tên trong source code

Tên source thường là tên đơn giản hoặc tên được viết kèm package. Ví dụ:

~~~java
package com.example.billing;

public class Invoice {
    public static class LineItem {
    }
}
~~~

Trong source, lớp ngoài được tham chiếu bằng `Invoice`, còn lớp thành viên có thể được viết là `Invoice.LineItem` trong phạm vi phù hợp hoặc `com.example.billing.Invoice.LineItem` khi cần tên đầy đủ.

### 1.2. Binary name

Theo quy tắc đặt tên nhị phân của Java, binary name là tên lớp được dùng trong các cấu trúc nhị phân và nhiều API reflection/class loading. Với lớp top-level trong package, binary name thường giống fully qualified name trong source:

~~~text
com.example.billing.Invoice
~~~

Với member class, dấu chấm phân tách lớp ngoài và lớp thành viên được biểu diễn bằng `$` trong binary name:

~~~text
com.example.billing.Invoice$LineItem
~~~

Tên của local class và anonymous class cũng có dạng được mã hóa dựa trên lớp bao ngoài và có thể chứa số do compiler sinh ra. Không nên coi những tên nội bộ này là API ổn định để ứng dụng khác tự ghép chuỗi hoặc lưu lâu dài.

Binary name không bao gồm phần mở rộng `.class` và không phải đường dẫn file. Nó là tên logic dùng để nhận diện kiểu trong không gian class loader.

### 1.3. Internal name trong class file

Trong constant pool của class file, tên lớp thường được biểu diễn theo dạng internal name, dùng dấu `/` để phân tách package:

~~~text
com/example/billing/Invoice
com/example/billing/Invoice$LineItem
~~~

Có thể hình dung sự khác nhau:

| Dạng | Ví dụ |
|---|---|
| Tên source đầy đủ | `com.example.billing.Invoice.LineItem` |
| Binary name | `com.example.billing.Invoice$LineItem` |
| Internal name | `com/example/billing/Invoice$LineItem` |
| File class thường gặp | `com/example/billing/Invoice$LineItem.class` |

Đường dẫn file JAR thường tương ứng với internal name cộng `.class`, nhưng đó là cách lưu trữ artifact. Class loader có thể lấy bytecode từ JAR, thư mục, network hoặc nguồn tùy chỉnh; không phải mọi lớp đều phải tồn tại dưới dạng file trên filesystem.

### 1.4. Descriptor của field và method

Descriptor mô tả kiểu dữ liệu ở dạng JVM. Nó khác binary name vì nó biểu diễn kiểu của một field hoặc chữ ký method.

Một số descriptor cơ bản:

| Java type | JVM descriptor |
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
| `Invoice` | `Lcom/example/billing/Invoice;` |
| `String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |

Method descriptor đặt các kiểu tham số trong dấu ngoặc đơn, sau đó là kiểu trả về. Ví dụ:

~~~text
(Ljava/lang/String;I)Ljava/math/BigDecimal;
~~~

Descriptor trên mô tả method nhận `String` và `int`, trả về `BigDecimal`. Kiểu trả về cũng là một phần của descriptor JVM, dù Java source không cho phép overload chỉ khác kiểu trả về.

Descriptor có ý nghĩa trực tiếp khi phân giải method/field. Nếu một thư viện thay đổi kiểu trả về, kiểu tham số hoặc kiểu field, tham chiếu được biên dịch trong consumer có thể không còn khớp với thành viên trong phiên bản mới.

## 2. Class file lưu symbolic reference như thế nào?

Sau khi biên dịch, class file có cấu trúc gồm header, version, access flags, thông tin class/interface, field, method và **constant pool**. Constant pool chứa các hằng số và tham chiếu mà bytecode sử dụng.

Một symbolic reference không nhất thiết là địa chỉ bộ nhớ của class hoặc method. Nó mô tả đối tượng cần tìm bằng tên và descriptor. JVM sẽ phân giải tham chiếu đó trong môi trường runtime, nơi class loader, module và các class đã được nạp quyết định kết quả.

### 2.1. Các loại constant pool entry liên quan

Một số loại entry quan trọng trong class file gồm:

- `CONSTANT_Class`: tham chiếu tới class/interface hoặc kiểu mảng.
- `CONSTANT_Fieldref`: tham chiếu tới field của một class.
- `CONSTANT_Methodref`: tham chiếu tới method của class.
- `CONSTANT_InterfaceMethodref`: tham chiếu tới method của interface.
- `CONSTANT_NameAndType`: ghép tên thành viên với descriptor.
- `CONSTANT_MethodHandle`: biểu diễn method handle trỏ tới field hoặc method reference.
- `CONSTANT_MethodType`: lưu method descriptor cho method handle/dynamic invocation.
- `CONSTANT_InvokeDynamic`: liên kết lời gọi động thông qua bootstrap method.
- `CONSTANT_Dynamic`: biểu diễn hằng số được liên kết động thông qua bootstrap method.

Các entry này liên kết với nhau. Ví dụ, một `CONSTANT_Methodref` xác định class sở hữu method và một `NameAndType` chứa tên cùng descriptor của method đó.

### 2.2. Ví dụ symbolic reference

Giả sử thư viện cung cấp:

~~~java
package com.example.payment;

public class PaymentClient {
    public String status(String paymentId) {
        return "PENDING";
    }
}
~~~

Consumer gọi method:

~~~java
PaymentClient client = new PaymentClient();
String value = client.status("P-100");
~~~

Bytecode consumer cần tham chiếu tới class `com.example.payment.PaymentClient` và method `status` với descriptor nhận một `String`, trả về `String`:

~~~text
com/example/payment/PaymentClient
status
(Ljava/lang/String;)Ljava/lang/String;
~~~

Khi consumer chạy với JAR mới, JVM cần tìm class đúng tên và method đúng descriptor trong class hierarchy phù hợp. Nếu JAR mới chỉ còn method `status(String)` trả về `Optional<String>`, descriptor đã thay đổi và tham chiếu cũ không còn được đáp ứng. Consumer cũ có thể gặp `NoSuchMethodError` khi JVM phân giải hoặc thực thi lời gọi đó.

### 2.3. Symbolic reference không phải tên method đơn lẻ

Tên `status` chưa đủ để xác định method. Cùng một class có thể có nhiều overload:

~~~java
public String status(String id) { ... }
public String status(long id) { ... }
~~~

Hai method có cùng tên nhưng descriptor khác nhau. Tương tự, một field reference cần class sở hữu, tên field và descriptor kiểu field. Vì vậy, chỉ tìm tên method trong source hoặc `javap` là chưa đủ; cần kiểm tra descriptor và owner class.

## 3. Bytecode sử dụng symbolic reference ở đâu?

Bytecode chứa các instruction tham chiếu tới constant pool. Các nhóm instruction thường gặp gồm:

| Nhóm instruction | Ví dụ | Tham chiếu được sử dụng |
|---|---|---|
| Tạo object | `new` | Class reference |
| Gọi method instance | `invokevirtual` | Method reference |
| Gọi method interface | `invokeinterface` | Interface method reference |
| Gọi static method | `invokestatic` | Method reference |
| Gọi constructor/private/super method | `invokespecial` | Method reference |
| Đọc/ghi static field | `getstatic`, `putstatic` | Field reference |
| Đọc/ghi instance field | `getfield`, `putfield` | Field reference |
| Gọi động | `invokedynamic` | InvokeDynamic entry và bootstrap method |

Với `invokedynamic`, JVM dùng bootstrap method để liên kết call site. Lambda expression và một số cơ chế ngôn ngữ/thư viện có thể sử dụng instruction này. Vì thế, phân tích class file hiện đại không thể chỉ tìm `invokevirtual` và `invokestatic`.

Các tham chiếu tới class/interface cũng xuất hiện trong khai báo superclass, interface, field type, method descriptor, exception table, annotation và attribute khác. Một thay đổi kiểu có thể ảnh hưởng nhiều vị trí chứ không chỉ lời gọi method rõ ràng trong source.

## 4. Quá trình loading, linking và initialization

JVM không đơn giản đọc một file `.class` rồi chạy ngay. Vòng đời lớp gồm các giai đoạn có quan hệ với nhau: loading, linking và initialization. Linking thường được chia thành verification, preparation và resolution.

~~~text
             Class bytes / binary representation
                         |
                         v
                      Loading
                         |
                         v
                       Linking
             +-----------+-----------+
             |           |           |
             v           v           v
         Verification Preparation Resolution
             |           |           |
             +-----------+-----------+
                         |
                         v
                  Initialization
                         |
                         v
                    Execution
~~~

Sơ đồ mô tả quan hệ khái niệm. Trong thực tế, JVM có thể trì hoãn một số bước resolution cho tới khi tham chiếu được sử dụng; không nhất thiết mọi symbolic reference đều được phân giải ngay khi class được load.

### 4.1. Loading

Loading là quá trình tìm biểu diễn nhị phân của class/interface theo binary name và tạo đối tượng `Class` tương ứng trong JVM.

Class loader có thể lấy bytecode từ:

- Thư mục class output.
- JAR hoặc module.
- Classpath/module path.
- Network hoặc nguồn tùy chỉnh.
- Byte array được định nghĩa qua custom class loader.

Các loader nền tảng thường gặp là bootstrap class loader, platform class loader và application class loader. Ứng dụng cũng có thể có custom class loader, plugin loader hoặc loader do framework tạo.

Mô hình delegation thường cho phép loader hỏi parent trước khi tự tìm class, nhưng không phải mọi loader đều tuân theo cùng một chính sách. Khi điều tra lỗi, cần biết loader nào thực sự định nghĩa class.

### 4.2. Class identity và class loader

Một điểm rất quan trọng: **identity của một class tại runtime được xác định bởi binary name và defining class loader**. Hai class cùng binary name nhưng được định nghĩa bởi hai loader khác nhau có thể là hai kiểu không tương thích.

Ví dụ, hai plugin cùng đóng gói `com.example.api.Message` trong các class loader riêng. Dù tên class giống hệt nhau, object của plugin A có thể không cast được sang kiểu `Message` do plugin B định nghĩa. Lỗi có thể hiển thị dạng `ClassCastException` với thông báo hai class cùng tên nhưng thuộc các loader khác nhau.

Runtime package cũng gắn với defining loader. Vì vậy, package name giống nhau không tự bảo đảm hai class thuộc cùng runtime package hoặc có quyền truy cập package-private lẫn nhau.

Khi khảo sát migration, cần kiểm tra custom class loader, plugin isolation, application server, OSGi hoặc framework hot reload nếu hệ thống sử dụng các cơ chế đó.

### 4.3. Verification

Verification kiểm tra class file có cấu trúc hợp lệ và bytecode có tuân thủ các ràng buộc an toàn của JVM hay không. Quá trình này giúp phát hiện class file hỏng, operand stack/local variable không hợp lệ, kiểu dữ liệu không phù hợp hoặc luồng điều khiển bytecode vi phạm quy tắc.

Một số lỗi liên quan có thể là `VerifyError`. Lỗi này có thể xuất hiện khi class được tạo bởi bytecode generator, enhancer, agent hoặc compiler không tạo bytecode phù hợp với verifier của JVM mới.

Nếu ứng dụng dùng ASM, Byte Buddy, Javassist, CGLIB hoặc công cụ instrumentation, hãy kiểm tra phiên bản và ma trận hỗ trợ JDK. Những công cụ này có thể tạo hoặc biến đổi class file, do đó cần theo kịp class file version và quy tắc verifier mới.

### 4.4. Preparation

Preparation tạo các field `static` và đặt chúng về giá trị mặc định theo kiểu dữ liệu. Các constant variable có `ConstantValue` attribute được xử lý theo quy tắc của JVM trong giai đoạn này.

Không nhầm preparation với việc chạy các câu lệnh khởi tạo static trong source. Các biểu thức và static initializer thông thường được thực thi ở giai đoạn initialization thông qua method đặc biệt `<clinit>` nếu class có nội dung cần khởi tạo.

### 4.5. Resolution

Resolution chuyển symbolic reference trong constant pool thành tham chiếu runtime tới class/interface, field, method hoặc method handle tương ứng. Đây là giai đoạn liên quan trực tiếp đến nhiều lỗi binary compatibility.

Ví dụ, khi bytecode yêu cầu `PaymentClient.status(String):String`, JVM cần:

1. Tìm class/interface được nêu trong reference.
2. Tìm thành viên có tên và descriptor tương ứng theo quy tắc lookup của JVM.
3. Kiểm tra quyền truy cập và các điều kiện liên quan.
4. Xác nhận cách sử dụng phù hợp với loại thành viên và instruction.

Nếu không tìm thấy thành viên, không truy cập được hoặc cấu trúc class không phù hợp với instruction, JVM có thể phát sinh linkage error. Resolution có thể được thực hiện sớm hoặc trì hoãn; vì vậy một ứng dụng có thể khởi động thành công nhưng chỉ lỗi khi một đường code hiếm được chạy.

### 4.6. Initialization

Initialization thực thi các static field initializer và static initializer trong `<clinit>`. Nó xảy ra khi class được sử dụng theo những điều kiện kích hoạt initialization mà JVM quy định, chẳng hạn tạo instance, gọi static method hoặc truy cập một static field không phải constant variable.

Nếu initialization thất bại, lần đầu có thể nhận `ExceptionInInitializerError` khi nguyên nhân là exception trong initializer; những lần sử dụng sau có thể nhận `NoClassDefFoundError` vì class đã ở trạng thái initialization error. Vì vậy, `NoClassDefFoundError` không phải lúc nào cũng có nghĩa file JAR bị thiếu; cần xem nguyên nhân đầu tiên trong stack trace.

## 5. Phân giải class, field và method

Các symbolic reference khác nhau có quy tắc phân giải riêng. Nắm ý tưởng chung giúp đọc lỗi và so sánh binary giữa hai bản phát hành.

### 5.1. Class/interface resolution

JVM tìm class/interface theo binary name trong ngữ cảnh loader đã được xác định bởi class đang chứa symbolic reference và quy tắc loading. Kết quả phải thỏa mãn các ràng buộc về loại, quyền truy cập và module liên quan.

Nếu class không thể được tìm thấy trong quá trình tải theo yêu cầu của một symbolic reference, có thể phát sinh `NoClassDefFoundError`. Nếu ứng dụng gọi API reflection như `Class.forName` hoặc `ClassLoader.loadClass` và không tìm thấy tên được yêu cầu, API đó có thể ném `ClassNotFoundException`. Hai lỗi có liên quan nhưng xuất hiện ở các cơ chế và ngữ cảnh khác nhau.

### 5.2. Field resolution

Field reference xác định class/interface sở hữu, tên field và descriptor. JVM tìm field theo quy tắc lookup trong class và các kiểu cha/interface liên quan.

Các lỗi thường gặp:

- `NoSuchFieldError`: field được tham chiếu không còn tồn tại với tên/descriptor cần thiết.
- `IllegalAccessError`: field tồn tại nhưng bytecode không có quyền truy cập theo quy tắc runtime.
- `IncompatibleClassChangeError`: cách sử dụng field không còn phù hợp với cấu trúc class, ví dụ kỳ vọng static nhưng thành viên thực tế không còn static.

Thay đổi field từ `public` sang `private`, đổi kiểu hoặc thay đổi static/instance có thể phá vỡ consumer đã biên dịch.

### 5.3. Method resolution

Method reference chứa owner type, tên method và descriptor. JVM áp dụng quy tắc lookup tương ứng với class method hoặc interface method. Sau khi resolution thành công, instruction gọi method còn có thể thực hiện lựa chọn implementation dựa trên receiver hoặc loại invocation.

Các lỗi thường gặp:

- `NoSuchMethodError`: không tìm thấy method với tên và descriptor được tham chiếu.
- `IllegalAccessError`: method tồn tại nhưng không thể truy cập.
- `AbstractMethodError`: lời gọi cần implementation nhưng runtime object không cung cấp implementation phù hợp.
- `IncompatibleClassChangeError`: class/interface hoặc static/instance assumption không còn khớp với bytecode.
- `BootstrapMethodError`: bootstrap method của `invokedynamic` hoặc dynamic constant thất bại khi liên kết.

Ví dụ, nếu một thư viện đổi method từ instance sang static nhưng consumer cũ vẫn chứa `invokevirtual`, cấu trúc runtime không còn phù hợp với instruction đã biên dịch. Tương tự, thay đổi interface hierarchy có thể ảnh hưởng method dispatch dù tên method vẫn còn.

## 6. Liên hệ với binary compatibility khi nâng dependency

Binary compatibility trả lời liệu bytecode đã biên dịch với phiên bản cũ có thể liên kết với phiên bản mới mà không cần biên dịch lại hay không. Vì symbolic reference chứa owner, name và descriptor, thay đổi các thành phần này có thể phá vỡ liên kết.

Giả sử phiên bản 1 của thư viện có:

~~~java
package com.example.customer;

public class CustomerClient {
    public Customer find(String id) {
        return null;
    }
}
~~~

Consumer được biên dịch với descriptor method:

~~~text
find(Ljava/lang/String;)Lcom/example/customer/Customer;
~~~

Phiên bản 2 đổi kiểu trả về:

~~~java
public Optional<Customer> find(String id) {
    return Optional.empty();
}
~~~

Ở Java source, không thể khai báo đồng thời hai method chỉ khác kiểu trả về. Trong bytecode, kiểu trả về nằm trong method descriptor, vì vậy descriptor của phiên bản mới khác descriptor mà consumer cũ tham chiếu. Khi consumer cũ chạy với JAR mới, JVM có thể không tìm được method cũ và phát sinh `NoSuchMethodError`.

Một cách chuyển đổi có thể giữ method cũ và bổ sung method mới với tên khác, ví dụ `findOptional`, hoặc giữ API cũ trong giai đoạn deprecation. Việc chọn cách nào phụ thuộc hợp đồng và ngữ nghĩa; không nên chỉ đổi return type rồi kỳ vọng JVM tự chuyển đổi.

Các thay đổi khác cũng cần xem xét:

- Đổi package/class name làm binary name thay đổi.
- Đổi tên nested class có thể thay binary name chứa `$`.
- Xóa constructor làm reference `<init>` không còn được đáp ứng.
- Đổi kiểu field làm descriptor không khớp.
- Thay class bằng interface hoặc ngược lại làm thay đổi cách resolution/invocation.
- Đổi access modifier có thể làm consumer mất quyền truy cập.
- Thay hierarchy có thể làm thay đổi lookup và dispatch.

## 7. Quan sát binary name và symbolic reference bằng công cụ

`javap` là công cụ cơ bản để xem class file và bytecode. Các option thường dùng:

~~~bash
javap -classpath path/to/library.jar -p com.example.payment.PaymentClient
javap -classpath path/to/library.jar -v -c -s com.example.payment.PaymentClient
~~~

- `-p` hiển thị thành viên gồm cả mức truy cập không public.
- `-v` hiển thị thông tin chi tiết như constant pool và attribute.
- `-c` hiển thị bytecode instruction.
- `-s` hiển thị internal type signatures/descriptors.

Trong output verbose, có thể thấy `CONSTANT_Class`, `CONSTANT_Methodref`, `CONSTANT_Fieldref`, `NameAndType` và các descriptor. Đây là bằng chứng trực tiếp để so sánh consumer đã biên dịch đang tham chiếu tới API nào.

Có thể kiểm tra nội dung JAR bằng:

~~~bash
jar tf path/to/library.jar
~~~

Lệnh này liệt kê entry trong JAR. So sánh danh sách class giữa hai bản phát hành giúp tìm class bị thêm/xóa, nhưng không phát hiện thay đổi chữ ký bên trong class. Vì vậy cần kết hợp `javap` hoặc công cụ API comparison như japicmp/Revapi.

Để tìm dependency class-level của ứng dụng, có thể dùng:

~~~bash
jdeps -verbose:class path/to/application.jar
~~~

Kết quả giúp xác định class của ứng dụng phụ thuộc vào package/class nào. Đây không phải báo cáo đầy đủ về mọi lời gọi động hoặc reflection; cần kết hợp source search, runtime trace và test.

## 8. Điều tra lỗi liên kết khi chạy

Khi ứng dụng gặp linkage error sau khi thay JAR hoặc JDK, hãy tìm nguyên nhân đầu tiên thay vì chỉ xử lý exception cuối cùng được log.

Quy trình điều tra:

1. Ghi nhận exception/error đầy đủ, class và method đầu tiên phát sinh lỗi.
2. Xác định class consumer đã được biên dịch với phiên bản dependency nào.
3. Xác định JAR/class thực tế được JVM nạp ở runtime.
4. Dùng `javap -v -c -s` kiểm tra symbolic reference trong consumer.
5. Dùng `javap` trên provider runtime để kiểm tra class/member và descriptor hiện có.
6. Kiểm tra class loader, module path, dependency conflict và thứ tự classpath.
7. Tái hiện với đúng artifact cũ/mới và một test tối thiểu.
8. Chọn cách sửa: giữ API tương thích, nâng consumer, điều chỉnh dependency resolution hoặc tách phiên bản hợp đồng.

Trên JDK hỗ trợ unified logging, có thể bật log nạp class để xác định nguồn class:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Với JDK cũ hơn chưa hỗ trợ unified logging, có thể dùng `-verbose:class` theo tài liệu của runtime đó. Log class loading có thể khá lớn; nên lọc theo class liên quan và tránh bật lâu trong môi trường production nếu chưa đánh giá dung lượng log.

Một đoạn chẩn đoán trong code cũng có thể in class loader và code source:

~~~java
Class<?> type = PaymentClient.class;

System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
System.out.println("source=" + type.getProtectionDomain()
        .getCodeSource());
~~~

Đây là ví dụ phục vụ chẩn đoán trong môi trường phù hợp. Code source có thể là `null` tùy cách class được định nghĩa; không nên coi nó là thông tin luôn có.

## 9. Class loader và các lỗi tưởng như trùng tên

Class identity tại runtime gắn với binary name và defining class loader. Nếu hai plugin hoặc hai ứng dụng con cùng nạp một class có tên `com.example.api.Message` từ hai loader khác nhau, JVM có thể coi đó là hai kiểu riêng biệt.

Điều này thường xuất hiện trong:

- Application server có class loader riêng cho từng deployment.
- Plugin architecture và hệ thống extension.
- OSGi hoặc module container.
- Framework hot reload/devtools.
- Ứng dụng đóng gói trùng dependency trong nhiều module/plugin.

Một tình huống điển hình là method nhận `Message` do loader A định nghĩa nhưng caller truyền object `Message` do loader B định nghĩa. Có thể xảy ra `ClassCastException`, loader constraint violation hoặc lỗi linkage khác. Chỉ kiểm tra tên class trong JAR là chưa đủ; cần kiểm tra defining loader và nguồn class thực tế.

Khi thiết kế module/plugin, cần xác định rõ class nào được chia sẻ qua parent loader, class nào được cô lập và dependency nào chỉ được đóng gói một lần. Không nên giải quyết xung đột bằng cách loại bỏ JAR ngẫu nhiên khỏi classpath mà không hiểu ownership của API.

## 10. Checklist kiểm tra binary name và linking trong migration

- [ ] Đã xác định binary name và internal name của class liên quan.
- [ ] Đã phân biệt binary name với method/field descriptor.
- [ ] Đã xác định symbolic reference trong constant pool của consumer.
- [ ] Đã kiểm tra class, field, method, constructor và hierarchy ở provider mới.
- [ ] Đã xem xét các instruction gọi/đọc/ghi tương ứng.
- [ ] Đã phân biệt loading, verification, preparation, resolution và initialization.
- [ ] Đã kiểm tra class loader, module và nguồn JAR thực tế.
- [ ] Đã xem xét `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `AbstractMethodError` và các linkage error liên quan.
- [ ] Đã kiểm tra binary cũ chạy với dependency mới khi đó là yêu cầu.
- [ ] Đã kiểm tra source consumer biên dịch lại với API mới.
- [ ] Đã kết hợp API diff với integration test và kiểm thử hành vi.
- [ ] Đã ghi baseline artifact, runtime classpath và bằng chứng điều tra.

## 11. Kết luận

Binary name xác định tên lớp ở mức nhị phân; descriptor xác định kiểu của field hoặc chữ ký method; symbolic reference trong constant pool nối bytecode với các class và thành viên mà nó cần. JVM nạp class qua class loader, thực hiện linking gồm verification, preparation và resolution, rồi initialization trước khi class được sử dụng theo các điều kiện tương ứng.

Khi migration thư viện hoặc JDK, thay đổi binary name, descriptor, access, class hierarchy hoặc class loader có thể khiến tham chiếu đã biên dịch không còn liên kết được. Dùng `javap`, `jar`, `jdeps`, log class loading và kiểm thử consumer cũ giúp xác định chính xác nguồn lỗi. Kết hợp những bằng chứng này với API comparison và test runtime sẽ giúp đánh giá binary compatibility có cơ sở thay vì chỉ dựa vào việc source code còn biên dịch được.
