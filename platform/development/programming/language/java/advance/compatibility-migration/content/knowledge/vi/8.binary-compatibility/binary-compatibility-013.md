# Thử nghiệm bên sử dụng cũ với thư viện mới mà không biên dịch lại

Trong Java migration, một thư viện có thể được nâng cấp, biên dịch thành công và vượt qua toàn bộ unit test nhưng vẫn làm hỏng những ứng dụng đang sử dụng bản cũ. Lý do là các ứng dụng đó đã được biên dịch thành bytecode với những tham chiếu đến class, method và field của phiên bản thư viện trước. Khi chỉ thay JAR ở môi trường chạy, JVM phải liên kết bytecode cũ với định nghĩa mới. Những lỗi như NoSuchMethodError, NoSuchFieldError hoặc IncompatibleClassChangeError có thể chỉ xuất hiện lúc chương trình thật sự thực hiện thao tác liên quan.

**Thử nghiệm bên sử dụng cũ với thư viện mới mà không biên dịch lại** (old-consumer binary compatibility test) là cách giữ nguyên artifact của consumer đã được biên dịch với thư viện phiên bản cũ, sau đó chạy chính artifact đó với thư viện phiên bản mới trên classpath hoặc module path. Mục tiêu là xác minh một consumer đã phát hành vẫn có thể liên kết và thực thi khi dependency được thay thế, đúng với phạm vi tương thích nhị phân mà thư viện tuyên bố hỗ trợ.

Điểm cốt lõi là **khóa bytecode của consumer**. Nếu biên dịch lại consumer với thư viện mới, ta đã thay đổi đối tượng kiểm thử: compiler có thể tạo các symbolic reference khác, phát hiện một số lỗi trước khi chạy, hoặc vô tình che mất lỗi mà consumer đang triển khai ngoài thực tế sẽ gặp.

## 1. Phân biệt tương thích nhị phân với biên dịch lại và tương thích hành vi

Một thay đổi API có thể ảnh hưởng đến các loại tương thích theo cách khác nhau:

| Góc kiểm tra | Câu hỏi | Cách thử |
|---|---|---|
| Source compatibility | Source của consumer cũ có biên dịch lại được với thư viện mới không? | Biên dịch source cũ với thư viện mới |
| Binary compatibility | Class/JAR của consumer cũ có chạy được với thư viện mới mà không biên dịch lại không? | Giữ nguyên consumer artifact; thay JAR thư viện lúc runtime |
| Behavioral compatibility | Kết quả, exception, trạng thái và side effect có tiếp tục đáp ứng hợp đồng không? | Chạy các tình huống hành vi trên thư viện mới và so sánh hợp đồng |
| Runtime/class-file compatibility | JVM đích có đọc được bytecode của các artifact không? | Kiểm tra class-file major version và chạy trên JDK đích |

Một thư viện có thể giữ chữ ký nhị phân và cho phép consumer cũ chạy, nhưng đổi quy tắc làm tròn hoặc thứ tự kết quả. Khi đó binary compatibility được giữ, còn behavioral compatibility có thể bị phá vỡ. Ngược lại, source consumer có thể biên dịch lại với code mới sau khi developer sửa lời gọi API, nhưng artifact consumer cũ vẫn bị lỗi khi chỉ thay thư viện.

Ví dụ, một method cũ:

~~~java
public String findName(long id);
~~~

được đổi thành:

~~~java
public CharSequence findName(long id);
~~~

Hai method nhìn giống nhau về tên và tham số ở source, và String là một subtype của CharSequence. Nhưng JVM method descriptor còn chứa **kiểu trả về**: lời gọi từ consumer cũ có thể yêu cầu descriptor (J)Ljava/lang/String; trong khi class mới chỉ cung cấp (J)Ljava/lang/CharSequence;. Nếu không còn method với descriptor cũ, runtime có thể ném NoSuchMethodError.

Điều quan trọng trong một bản migration là định nghĩa chính xác cam kết hỗ trợ: nhóm consumer nào, phiên bản consumer nào, JDK nào, và thay thế artifact nào được phép mà không cần build lại.

## 2. Vì sao Java có thể lỗi ở thời điểm chạy?

Khi javac biên dịch consumer, class file chứa các symbolic reference đến type, method và field, thường thông qua constant pool. JVM không bắt buộc phải liên kết tất cả tham chiếu ngay khi process khởi động; một số tham chiếu được phân giải khi class được tải, xác minh hoặc khi một đường code được thực thi.

Một lời gọi có thể được mã hóa theo thông tin gồm:

- **Binary name của class:** ví dụ com.example.api.PriceService.
- **Tên method:** ví dụ calculate.
- **Method descriptor:** danh sách kiểu tham số cùng kiểu trả về ở dạng JVM.
- **Loại invocation:** ví dụ invokevirtual, invokestatic, invokeinterface hoặc invokespecial.
- **Quy tắc access và inheritance:** method có thể truy cập được không, có tồn tại trong hierarchy phù hợp không.

Field cũng được tham chiếu theo owner, tên, descriptor và quy tắc static/instance. Việc đổi một field instance thành static có thể khiến bytecode cũ dùng getfield trong khi field mới chỉ được truy cập qua getstatic. Đây là dạng thay đổi cấu trúc ở cấp JVM, dù tên field vẫn còn.

Compiler kiểm tra API dựa trên classpath ở thời điểm build. JVM liên kết dựa trên class thực tế mà class loader tìm thấy lúc chạy. Khi hai tập class khác nhau, một lỗi linkage có thể xuất hiện mặc dù bản build consumer cũ từng thành công.

### 2.1. Các lỗi linkage thường gặp

| Lỗi | Khả năng thường gặp khi thay thư viện | Bằng chứng cần xem |
|---|---|---|
| NoSuchMethodError | Method hoặc constructor cũ đã bị xóa; thay descriptor, kiểu trả về hoặc overload | Descriptor của lời gọi trong consumer và method hiện có trong thư viện mới |
| NoSuchFieldError | Field cũ bị xóa/đổi tên hoặc đổi field descriptor | Field reference trong constant pool và khai báo field của JAR mới |
| IncompatibleClassChangeError | Thay đổi bất tương thích về class/interface, static/instance hoặc hình thức truy cập thành viên | Instruction gọi và cấu trúc class của cả hai version |
| IllegalAccessError | Thành viên hoặc class không còn truy cập được theo quy tắc runtime | Access flags, package, module và class loader |
| AbstractMethodError | Lời gọi đến method cần triển khai nhưng runtime không tìm được implementation cụ thể | Class/interface hierarchy và các version thực tế được nạp |
| NoClassDefFoundError | Class cần thiết không còn tìm thấy, hoặc khởi tạo class trước đó đã thất bại | Class loading log, cause gốc và runtime dependency graph |
| UnsupportedClassVersionError | Thư viện mới có class-file version cao hơn JVM đích hỗ trợ | Major/minor version của class bằng javap và JDK runtime |

Lỗi ở trên thường kế thừa LinkageError, nhưng không nên xem chúng là cùng một nguyên nhân. Ví dụ, nâng JDK có thể xử lý UnsupportedClassVersionError nhưng không giải quyết việc method cũ đã bị xóa. Thay classpath có thể giải quyết NoClassDefFoundError mà không sửa một API binary break thật sự.

### 2.2. Không có exception chưa chắc đã tương thích

Một số thay đổi không gây lỗi liên kết nhưng vẫn phá hợp đồng consumer. Đặc biệt, hằng compile-time có thể được javac đưa trực tiếp vào bytecode của consumer:

~~~java
public static final int MAX_RETRIES = 3;
~~~

Nếu library v2 đổi thành 5, consumer cũ có thể tiếp tục dùng giá trị 3 đã được inline khi biên dịch. JVM không cần đọc field ở runtime tại vị trí đó, nên có thể không ném NoSuchFieldError. Kết quả của phép thử binary vẫn có thể là “chạy được”, nhưng hành vi có thể sai kỳ vọng nếu thư viện yêu cầu giá trị mới phải được áp dụng.

Do đó, phép thử phải vừa phát hiện linkage failure vừa kiểm tra các hành vi công khai có ý nghĩa. Một ứng dụng có thể khởi động thành công nhưng các đường code chưa chạy vẫn ẩn lỗi.

## 3. Thiết kế phép thử chuẩn

Ta cần ba artifact được nhận diện rõ ràng:

| Artifact | Được tạo bằng gì? | Sử dụng khi nào? |
|---|---|---|
| library-v1.jar | Build của thư viện cũ đã được consumer dùng | Biên dịch consumer cũ và chạy baseline |
| consumer-v1.jar | Build **một lần** từ source consumer, classpath khi compile chứa library-v1.jar | Dùng nguyên vẹn trong cả phép thử baseline và migration |
| library-v2.jar | Build của phiên bản thư viện mới đang đánh giá | Thay thế library-v1.jar ở runtime mà không build lại consumer |

Luồng kiểm thử:

~~~text
      source consumer cũ         source library v1
               |                       |
               | compile với v1        | build
               v                       v
       consumer-v1.jar <---------- library-v1.jar
               |
               | giữ nguyên checksum
               |
      +--------+---------------------+
      |                              |
      v                              v
 Run A (baseline)              Run B (migration)
 consumer-v1.jar               consumer-v1.jar
 library-v1.jar                library-v2.jar
      |                              |
      v                              v
 Lưu kết quả                    Quan sát linkage,
 tham chiếu                     hành vi và lỗi
~~~

Trong Run B, library-v1.jar phải được loại khỏi runtime classpath của ứng dụng. Chỉ thêm library-v2.jar vào cuối classpath có cả v1 dễ khiến JVM vẫn nạp class từ v1 và cho kết quả dương tính giả.

Để phép thử có giá trị, cần giữ cố định các yếu tố khác càng nhiều càng tốt: JDK, cấu hình hệ thống, dữ liệu test và các dependency không thuộc migration. Khi cần nâng JDK đồng thời, nên có các phép thử tách riêng để xác định lỗi do thư viện hay runtime.

## 4. Ví dụ hoàn chỉnh: consumer cũ bị lỗi với thư viện mới

Ví dụ dùng JDK có công cụ javac, java và jar. Cấu trúc thư mục:

~~~text
binary-compat-lab/
├── lib-v1/src/demo/api/MessageFormatter.java
├── lib-v2/src/demo/api/MessageFormatter.java
├── consumer/src/demo/client/Main.java
└── out/
~~~

### 4.1. Viết thư viện v1

File lib-v1/src/demo/api/MessageFormatter.java:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

Method công khai có tên format, một tham số String và kiểu trả về String. Đây là API mà consumer sẽ tham chiếu khi compile.

### 4.2. Viết consumer và biên dịch đúng một lần

File consumer/src/demo/client/Main.java:

~~~java
package demo.client;

import demo.api.MessageFormatter;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("An"));
    }
}
~~~

Từ thư mục binary-compat-lab, thực hiện trên Linux/macOS:

~~~bash
mkdir -p out/classes-v1 out/classes-consumer out/classes-v2

javac -d out/classes-v1 lib-v1/src/demo/api/MessageFormatter.java
jar --create --file out/library-v1.jar -C out/classes-v1 .

javac -cp out/library-v1.jar \
  -d out/classes-consumer \
  consumer/src/demo/client/Main.java
jar --create --file out/consumer-v1.jar -C out/classes-consumer .
~~~

Đối số -cp ở bước biên dịch consumer trỏ đến **library-v1.jar**. Đây là điều kiện của bài thử: bytecode consumer phải được tạo dựa trên API cũ.

Chạy baseline:

~~~bash
java -cp "out/consumer-v1.jar:out/library-v1.jar" demo.client.Main
~~~

Kết quả mong đợi:

~~~text
Hello, An
~~~

Trên Windows, dùng dấu chấm phẩy để phân cách các mục trong classpath:

~~~powershell
java -cp "out/consumer-v1.jar;out/library-v1.jar" demo.client.Main
~~~

Sau bước này, không chạy lại javac trên source consumer cho đến khi phép thử binary compatibility kết thúc.

### 4.3. Thay đổi API không tương thích trong thư viện v2

Giả sử library v2 đổi tham số của method từ String thành Object và bỏ method cũ. File lib-v2/src/demo/api/MessageFormatter.java:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(Object name) {
        return "Hello, " + name;
    }
}
~~~

Hai method nhận Object và String có quan hệ overload ở source level, nhưng descriptor JVM khác nhau. Consumer đã biên dịch không tự đổi lời gọi sang overload Object.

Chỉ biên dịch và đóng gói thư viện v2:

~~~bash
javac -d out/classes-v2 lib-v2/src/demo/api/MessageFormatter.java
jar --create --file out/library-v2.jar -C out/classes-v2 .
~~~

Chạy consumer cũ với thư viện mới:

~~~bash
java -cp "out/consumer-v1.jar:out/library-v2.jar" demo.client.Main
~~~

Trên Windows:

~~~powershell
java -cp "out/consumer-v1.jar;out/library-v2.jar" demo.client.Main
~~~

JVM có thể phát lỗi tương tự:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String demo.api.MessageFormatter.format(java.lang.String)'
    at demo.client.Main.main(Main.java:...)
~~~

Nguyên nhân không phải vì Object không nhận được String; vấn đề là bytecode của Main vẫn yêu cầu method có descriptor (Ljava/lang/String;)Ljava/lang/String;, trong khi library v2 chỉ có (Ljava/lang/Object;)Ljava/lang/String;.

### 4.4. Sửa v2 để giữ hợp đồng nhị phân

Một hướng tương thích là giữ nguyên method cũ và bổ sung overload mới:

~~~java
package demo.api;

public class MessageFormatter {
    public String format(String name) {
        return format((Object) name);
    }

    public String format(Object name) {
        return "Hello, " + name;
    }
}
~~~

Sau khi build lại **chỉ library-v2.jar**, consumer-v1.jar cũ có thể liên kết với method format(String) và chạy lại bình thường. Việc bổ sung overload có thể tạo những vấn đề source compatibility khác khi consumer được biên dịch lại, nhưng phép thử binary đang xét chỉ yêu cầu consumer cũ có thể chạy với API mới.

Thay vì sửa source consumer, ta đã sửa thư viện để tiếp tục cung cấp hợp đồng cấp bytecode mà consumer thực tế dùng.

## 5. Dùng javap để chứng minh đúng method descriptor

Lỗi linkage có thể khó hiểu khi source code hiện tại nhìn “gần giống” API cũ. javap cho phép kiểm tra chính class file đã biên dịch.

Đọc bytecode và constant pool của consumer:

~~~bash
javap -verbose -classpath out/consumer-v1.jar demo.client.Main
~~~

Tìm Methodref tới demo/api/MessageFormatter.format và descriptor của nó. Với ví dụ trên, descriptor dự kiến là:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

So sánh chữ ký class ở hai thư viện:

~~~bash
javap -s -classpath out/library-v1.jar demo.api.MessageFormatter
javap -s -classpath out/library-v2.jar demo.api.MessageFormatter
~~~

Một bản v1 cung cấp:

~~~text
public java.lang.String format(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

Trong khi bản v2 không tương thích chỉ có:

~~~text
public java.lang.String format(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/String;
~~~

Có thể xem instruction của consumer:

~~~bash
javap -c -classpath out/consumer-v1.jar demo.client.Main
~~~

Khi consumer dùng invokevirtual trỏ đến method descriptor cũ, việc thư viện mới có một method cùng tên nhưng khác tham số không đáp ứng symbolic reference đó.

Trong trường hợp đổi static/instance, kiểm tra thêm instruction như invokestatic và invokevirtual. Trong trường hợp field, xem getfield, getstatic, putfield hoặc putstatic. Với method khai báo qua interface, xem invokeinterface và hierarchy mới.

### 5.1. Lưu checksum để bảo đảm consumer không bị build lại

Trước và sau phép thử, có thể tính SHA-256 của consumer artifact:

Linux/macOS:

~~~bash
sha256sum out/consumer-v1.jar
~~~

PowerShell:

~~~powershell
Get-FileHash out/consumer-v1.jar -Algorithm SHA256
~~~

Hai giá trị phải giống nhau trong phép thử giữ nguyên consumer artifact. Nên lưu checksum cùng build id, version và thời điểm tạo artifact. Nếu file consumer thay đổi, phép thử cần được thiết lập lại với bản đã đóng băng.

## 6. Những thay đổi API cần kiểm tra bằng consumer cũ

Không phải mọi thay đổi source đều phá binary compatibility. Cần tập trung vào những sửa đổi có thể ảnh hưởng symbolic reference hoặc quy tắc liên kết của JVM.

| Thay đổi trong thư viện mới | Rủi ro đối với bytecode consumer cũ | Cách tạo tình huống kiểm thử |
|---|---|---|
| Xóa hoặc đổi tên public method | Không còn method theo descriptor cũ | Gọi method từ consumer JAR cũ |
| Đổi kiểu tham số, thứ tự tham số hoặc kiểu trả về | Method descriptor khác | Dùng javap so sánh Methodref |
| Xóa constructor hoặc đổi tham số constructor | Lỗi khi bytecode gọi invokespecial để tạo object | Tạo object theo constructor cũ |
| Đổi method static thành instance, hoặc ngược lại | Loại invocation không còn phù hợp | Gọi method cũ từ consumer |
| Xóa/đổi tên field hoặc đổi field type | Không còn field reference tương ứng | Đọc/ghi field từ bytecode cũ |
| Đổi field instance thành static, hoặc ngược lại | Loại field access không còn phù hợp | Đọc/ghi field trong consumer |
| Giảm khả năng truy cập của class/member | JVM từ chối truy cập | Gọi API cũ từ package/module của consumer |
| Đổi class thành interface hoặc ngược lại | Thay đổi loại type mà bytecode đang tham chiếu | Instantiate/cast/gọi method qua type cũ |
| Đổi superclass hoặc interface hierarchy | Thay đổi khả năng resolve method và assignability | Gọi method kế thừa hoặc ép kiểu |
| Thay đổi interface liên quan implementation cũ | Có thể xuất hiện AbstractMethodError ở luồng sử dụng mới | Dùng implementation cũ với thư viện/API mới |

Không nên khẳng định tất cả các thay đổi ở bảng đều luôn tạo lỗi trong mọi trường hợp; kết quả phụ thuộc chính xác cấu trúc class, quan hệ kế thừa và loại symbolic reference đã được biên dịch. Ví dụ, một method bị chuyển sang superclass mới đôi khi vẫn được resolve thành công, còn một thay đổi cùng tên khác lại phá descriptor.

### 6.1. Generic, erasure và bridge method

Với Java generic, JVM làm việc chủ yếu với erased descriptor; một số method tổng hợp (bridge method) được compiler tạo để giữ semantics dispatch sau khi type erasure. Nếu thay generic hierarchy hoặc kiểu trả về covariant mà không giữ bridge method cần thiết, consumer cũ có thể gọi vào descriptor không còn tồn tại.

Đừng chỉ nhìn source của thư viện. Dùng javap -p -s -verbose để thấy cả bridge/synthetic method mà javac đã tạo. Nếu cần duy trì ABI, đôi khi phải giữ một method chuyển tiếp hoặc thay đổi thiết kế để compiler tiếp tục tạo bridge thích hợp.

### 6.2. Public constant và enum

Như đã nêu, constant expression có thể được inline vào consumer. Đổi giá trị của public static final primitive hoặc String constant có thể không tạo LinkageError, nhưng consumer cũ vẫn sử dụng giá trị trước đây. Enum có thể ảnh hưởng hành vi switch, serialization và tên hằng; việc xóa một enum constant mà consumer cũ dùng có thể phá những đường code liên quan.

Với các thay đổi như vậy, bổ sung test hành vi và test dữ liệu, thay vì chỉ xem thành công của bước nạp class.

### 6.3. Reflection, ServiceLoader và cấu hình

Một consumer có thể nạp class bằng Class.forName, ServiceLoader, dependency injection hoặc tên khai báo trong file cấu hình. Lỗi có thể không hiện ra trong danh sách method reference của bytecode consumer. Vì vậy cần chạy các luồng khởi tạo plugin, service discovery, serializer, mapper và framework đang dùng.

Binary compatibility của Java API không bảo đảm các hợp đồng dữ liệu, serialization hoặc phản chiếu vẫn tương thích. Nếu thư viện có các ranh giới đó, cần các phép thử riêng bổ sung.

## 7. Không để build tool tự biên dịch lại consumer

Trong project thực tế, thao tác này dễ bị sai khi dùng build đa module: chạy một task test của project có thể kéo theo compileJava của consumer rồi âm thầm biên dịch consumer với API mới. Kết quả khi đó là source compatibility test hoặc integration test của bản mới, không còn là phép thử consumer cũ.

### 7.1. Nguyên tắc chung

- Dùng consumer JAR/class file đã được phát hành, hoặc build consumer từ baseline v1 rồi lưu riêng như một fixture bất biến.
- Không khai báo consumer dưới dạng project dependency được build lại trong cùng đợt chạy.
- Runtime classpath phải chứa library v2 và các runtime dependency tương ứng; loại bỏ library v1 và bản trùng của các class thuộc library.
- Không đặt source consumer trong source set sẽ được compile khi chạy task test.
- Ghi lại đúng classpath, module path và JDK đích của process thực thi.
- Giữ fixture consumer cũ qua nhiều phiên bản library mới nếu thư viện cam kết hỗ trợ nhiều generation consumer.

### 7.2. Với Gradle

Nếu consumer cũ đã được publish thành một JAR, có thể tạo configuration riêng cho runtime test. Ví dụ khái niệm với Groovy DSL:

~~~groovy
configurations {
    binaryCompatRuntime
}

dependencies {
    binaryCompatRuntime("com.example:legacy-consumer:1.0.0")
    binaryCompatRuntime("com.example:library:2.0.0")
}

tasks.register("runOldConsumer", JavaExec) {
    classpath = configurations.binaryCompatRuntime
    mainClass = "com.example.client.Main"
}
~~~

Khi dùng đoạn này, cần kiểm tra transitive dependency: legacy-consumer có thể kéo library v1; Gradle thường giải quyết conflict cùng group/artifact bằng chọn một version, nhưng constraint, classifier, shaded JAR hoặc tọa độ khác nhau có thể khiến hai implementation tồn tại cùng lúc. Kiểm tra đúng configuration:

~~~bash
./gradlew dependencies --configuration binaryCompatRuntime
./gradlew dependencyInsight \
  --configuration binaryCompatRuntime \
  --dependency library
~~~

Sau đó mới chạy task với classpath đã xác minh. Tên task, dependency coordinates và main class trong ví dụ cần thay bằng project thật. Consumer fixture phải là artifact nhị phân cố định; nếu khai báo project(":consumer") và Gradle build lại project đó, điều kiện “không biên dịch lại” có thể bị vi phạm.

Với thư viện đang phát triển chưa publish, có thể dùng task riêng tạo classpath từ file JAR của build hiện tại và file consumer fixture đã khóa. Cần xác minh library v2 đã được build trước khi chạy, nhưng không chạy compile consumer.

### 7.3. Với Maven

Tạo một module hoặc project harness chuyên chạy consumer binary cũ, khai báo dependency consumer version cũ và library version mới. Maven sẽ resolve dependency graph theo quy tắc dependency mediation; cần kiểm tra version library được chọn:

~~~bash
mvn dependency:tree
mvn dependency:build-classpath
~~~

Nếu consumer artifact transitively yêu cầu library v1, có thể dùng dependencyManagement hoặc exclusion hợp lý để bảo đảm runtime nhận version v2 duy nhất. Sau khi xác nhận classpath, chạy main class của JAR consumer cũ bằng java hoặc cơ chế thực thi Maven phù hợp.

Nếu dùng Maven reactor build đồng thời cả source consumer, cần tách fixture ra ngoài reactor hoặc bảo đảm target chạy không kích hoạt compile consumer. Một lượt mvn test trên project source hiện tại không tự chứng minh consumer binary từ release cũ chạy được.

### 7.4. Với modular application

Nếu ứng dụng dùng Java Platform Module System (JPMS), cần dựng đúng module path, module name và launch command. Thư viện mới có thể giữ class/method nhưng thay module descriptor, exports hoặc requires và làm consumer cũ thất bại khi resolve module.

Ví dụ:

~~~bash
java --module-path "mods" \
  --module com.example.consumer/com.example.client.Main
~~~

Các artifact trong mods phải đại diện cho consumer cũ và phiên bản library mới. Không thay module path bằng classpath nếu deployment thực tế chạy trên module path, vì hai chế độ có các quy tắc resolution và access khác nhau.

## 8. Một bộ test cần chạy những gì?

Chỉ gọi main và kiểm tra exit code 0 là mức kiểm tra khói ban đầu. Vì JVM có thể phân giải method hoặc nạp class theo nhu cầu, cần chủ động thực thi những API consumer cũ từng dùng.

### 8.1. Nhóm kịch bản tối thiểu

1. **Baseline:** consumer-v1.jar + library-v1.jar. Xác nhận fixture và dữ liệu thử vốn hoạt động.
2. **Migration:** consumer-v1.jar + library-v2.jar. Giữ đúng consumer artifact và thay duy nhất thư viện/những runtime dependency cần thiết.
3. **Khởi tạo:** nạp class, khởi tạo đối tượng, gọi các constructor và static factory cũ.
4. **Phương thức:** gọi các API công khai đại diện, gồm method overload, generic và inherited method có liên quan.
5. **Field/constant:** đọc/ghi field công khai theo hợp đồng và kiểm tra các giá trị có thể inline.
6. **Interface:** khởi tạo và gọi implementation cũ qua interface mà thư viện mới công bố.
7. **Lỗi:** kiểm tra các nhánh exception, không tìm thấy dữ liệu, invalid input và timeout khi có cam kết.
8. **Framework:** kích hoạt reflection, serializer, annotation scanning, ServiceLoader hoặc plugin lifecycle nếu hệ thống sử dụng.
9. **Runtime đích:** chạy trên JDK thấp nhất còn nằm trong phạm vi hỗ trợ, không chỉ JDK của CI.

Tùy đặc điểm hệ thống, có thể cần test thêm concurrency, transaction, IO, TLS hoặc native integration. Nhưng không nên mở rộng ngẫu nhiên: mỗi trường hợp cần gắn với API hoặc hợp đồng consumer thực tế phụ thuộc.

### 8.2. Dùng dữ liệu và kết quả tham chiếu

Trong baseline, lưu output hoặc trạng thái kỳ vọng theo hợp đồng: giá trị trả về, loại exception, trạng thái database, số event, hoặc side effect quan trọng. Trong phép chạy migration, so sánh kết quả đó với cam kết. Nếu semantics được cố ý thay đổi, tài liệu cần nêu consumer cũ có được phép tiếp tục hoạt động theo semantics mới hay phải migrate.

Nên phân loại báo cáo thành:

| Kết quả | Diễn giải |
|---|---|
| Pass binary và pass behavior | Consumer cũ liên kết được, các tình huống đã kiểm tra tiếp tục đáp ứng hợp đồng |
| Fail linkage | API/bytecode/classpath/module không liên kết được; cần tìm nguyên nhân |
| Pass linkage, fail behavior | Không có lỗi liên kết nhưng semantics hoặc kết quả đã thay đổi |
| Fail runtime environment | JVM, config, native dependency hoặc hệ thống ngoài không phù hợp; cần phân biệt với binary API break |
| Untested path | Chưa chạy đường code có thể nạp API đó; chưa đủ bằng chứng để khẳng định tương thích |

Điểm “untested path” rất quan trọng. Một phép thử pass chỉ xác nhận những đường thực thi được test và môi trường đã dùng; nó không thể tự chứng minh mọi class trong dependency graph sẽ chạy an toàn.

## 9. Xác định chính xác class được JVM nạp

Trong migration, một lỗi phổ biến là test tưởng dùng library v2 nhưng JVM lại nạp class từ library v1, fat JAR cũ, thư mục build hoặc class loader của application server. Lúc đó test pass không phản ánh việc thay JAR như mong muốn.

Trên HotSpot/OpenJDK JDK 9 trở lên, có thể bật class loading log ở môi trường kiểm thử:

~~~bash
java -Xlog:class+load=info \
  -cp "out/consumer-v1.jar:out/library-v2.jar" \
  demo.client.Main
~~~

Với JDK 8, cú pháp quen thuộc:

~~~bash
java -verbose:class \
  -cp "out/consumer-v1.jar:out/library-v2.jar" \
  demo.client.Main
~~~

Kiểm tra source location của demo.api.MessageFormatter và các class có nghi ngờ. Log thường cho biết đường dẫn file JAR/class mà JVM đã dùng. Nếu class được nạp bởi custom loader hoặc từ nested JAR, cần đối chiếu thêm với cơ chế packaging/loader của framework.

Tránh chỉ xem file trùng tên trong thư mục cache. Hãy ghi lại artifact đang chạy bằng group/artifact/version, file path và checksum nếu có.

### 9.1. Kiểm tra class-file version của thư viện

~~~bash
javap -verbose -classpath out/library-v2.jar demo.api.MessageFormatter
~~~

Tìm major version và minor version. Nếu library v2 chứa class yêu cầu JDK cao hơn runtime đã công bố, consumer cũ có thể lỗi UnsupportedClassVersionError trước khi đi đến kiểm tra descriptor. Với multi-release JAR, cần xem view phù hợp với JDK đích; một entry Java 21 trong META-INF/versions/21 không tự khiến Java 17 bị lỗi nếu thư viện đóng gói đúng multi-release và có implementation phù hợp.

## 10. Tự động hóa phép thử trong CI/CD

Có thể đưa old-consumer test thành một compatibility lane riêng, bên cạnh unit test và integration test của thư viện mới.

~~~text
Release cũ / fixture đã lưu
          |
          v
 consumer-v1.jar + checksum  ------+
                                    |
 Build library mới                  |
          |                         |
          v                         v
   library-v2.jar ----------> Compatibility harness
                                     |
                      +--------------+-------------+
                      |              |             |
                      v              v             v
                    JDK 17         JDK 21       ...JDK khác
                      |              |             |
                      +--------------+-------------+
                                     |
                                     v
                        Linkage + behavior report
~~~

Một pipeline phù hợp có thể:

1. Tải hoặc materialize consumer binary fixture từ release cũ; kiểm tra checksum.
2. Build library v2 bằng toolchain đã khai báo.
3. Dựng classpath/module path với consumer cũ và library mới; loại library cũ.
4. Ghi JDK vendor/version và danh sách dependency runtime đã resolve.
5. Chạy harness trên các JDK được tuyên bố hỗ trợ và lưu stdout/stderr/exit status.
6. Phân loại lỗi liên kết, lỗi hành vi, lỗi môi trường và đường code chưa được thực thi.
7. Publish báo cáo/artefact chẩn đoán cho reviewer, đồng thời che secret trong log.

Nếu cần kiểm tra nhiều version consumer cũ, tạo ma trận rõ: consumer 1.x, 2.x, các bản còn nằm trong cam kết hỗ trợ và library đích 3.x. Tránh tạo ma trận vô hạn; dùng chính sách support window để chọn các phiên bản đại diện hoặc các release phải được hỗ trợ.

Ví dụ ma trận:

| Consumer binary | Library runtime | JDK | Mục đích |
|---|---|---|---|
| consumer 1.4 (đã compile với lib 1.4) | lib 1.4 | Java 17 | Baseline |
| consumer 1.4 (giữ nguyên) | lib 2.0 | Java 17 | Kiểm tra binary compatibility |
| consumer 1.4 (giữ nguyên) | lib 2.0 | Java 21 | Kiểm tra trên JDK mới |
| consumer 2.0 (compile với lib 2.0) | lib 2.0 | Java 21 | Control của API mới, không thay thế phép thử consumer cũ |

Hàng cuối giúp kiểm tra release mới hoạt động với consumer mới, nhưng không thể dùng nó làm bằng chứng consumer cũ vẫn chạy.

## 11. Kết hợp kiểm tra tĩnh và kiểm tra chạy thực tế

Các công cụ so sánh API nhị phân như japicmp, Revapi hoặc các bộ công cụ ABI khác có thể so sánh thư viện v1 và v2 để phát hiện những thay đổi công khai đáng chú ý. Chúng giúp sàng lọc thay đổi trước khi chạy consumer, nhưng vẫn cần phép thử trên artifact consumer thật vì:

- Classpath/module path thực tế có thể khác graph mà công cụ tĩnh giả định.
- Reflection và framework có thể tạo dependency ở runtime không hiện ra qua public method signature.
- Một thay đổi có thể hợp lệ theo quy tắc binary compatibility nhưng vi phạm hành vi.
- Dependency bắc cầu, native library và JDK có thể gây lỗi lúc chạy.
- Class loading theo nhu cầu khiến lỗi chỉ xuất hiện trong một đường code cụ thể.

Một quy trình hợp lý là dùng công cụ so sánh ABI để biết rủi ro cần chú ý, dùng javap để xác nhận descriptor khi có nghi ngờ, và dùng old-consumer runtime harness để chứng minh artifact triển khai cũ có thể tiếp tục chạy trong môi trường mục tiêu.

### 11.1. Tìm nguyên nhân khi test thất bại

Khi gặp LinkageError, hãy lưu đầy đủ stack trace và đi theo thứ tự:

1. Xác nhận consumer JAR có checksum đúng bản trước migration.
2. Xác nhận JVM đang chạy có đúng version/vendor và module path/classpath không.
3. Xác nhận class của thư viện được nạp từ đúng library v2, không phải bản v1 hoặc bản trùng trong fat JAR.
4. Dùng javap trên consumer để xem symbolic reference và instruction gây lỗi.
5. Dùng javap trên library v2 để xem method/field descriptor, access flags và hierarchy hiện có.
6. Đối chiếu với API cũ để xác định thay đổi nào làm tham chiếu không resolve.
7. Chọn sửa tại thư viện, lớp adapter, dependency selection hoặc tuyên bố version compatibility; chạy lại trường hợp liên quan.

Không sửa consumer source để làm phép thử cũ pass, vì hành động đó làm mất khả năng phát hiện breaking change đối với ứng dụng đã triển khai.

## 12. Những sai lầm thường gặp

- **Biên dịch lại consumer trong cùng build:** test pass nhưng đã đánh mất bytecode cũ cần kiểm tra.
- **Giữ cả library v1 và v2 trên classpath:** class loader có thể chọn v1, khiến kết luận sai.
- **Chỉ test với JDK của developer hoặc CI:** bỏ sót runtime thấp nhất mà sản phẩm còn cam kết hỗ trợ.
- **Chỉ khởi động ứng dụng:** các method và class có thể chưa được JVM nạp hoặc resolve.
- **Chỉ so sánh tên method và tham số ở source:** JVM descriptor còn liên quan kiểu trả về, static/instance, access và hierarchy.
- **Chỉ dựa vào compile thành công của thư viện:** không xác minh consumer binary cũ có liên kết được.
- **Chỉ dựa vào công cụ so sánh API:** không kiểm tra classpath, module, reflection, dependency hoặc hành vi thực tế.
- **Quên field constant inlining:** consumer cũ có thể tiếp tục sử dụng giá trị compile-time cũ dù library đã đổi.
- **Dùng artifact không có provenance:** không biết consumer thực sự đã compile với thư viện nào hoặc runtime đã nạp bản nào.
- **Không ghi phiên bản các dependency bắc cầu:** một lỗi phát sinh từ transitives bị chẩn đoán nhầm là lỗi của public library.
- **Trộn thay đổi JDK và thư viện rồi kết luận một nguyên nhân:** khó phân biệt runtime issue với ABI break.

## 13. Checklist trước khi công bố tương thích nhị phân

- [ ] Đã xác định các phiên bản consumer cũ còn nằm trong phạm vi hỗ trợ.
- [ ] Đã lưu consumer binary từ release trước, cùng build id và checksum.
- [ ] Consumer được biên dịch với library v1 và không được biên dịch lại trong test migration.
- [ ] Baseline consumer-v1 + library-v1 chạy thành công trên môi trường tham chiếu.
- [ ] Run migration chỉ dùng consumer-v1 + library-v2 và dependency runtime tương ứng.
- [ ] Đã xác minh không có library v1/class trùng được JVM nạp trong test migration.
- [ ] Đã chạy test trên JDK thấp nhất còn được hỗ trợ.
- [ ] Đã thực thi API đại diện, constructor, field, interface, reflection và các đường code lazy-loaded có liên quan.
- [ ] Đã kiểm tra LinkageError và phân biệt rõ lỗi môi trường, class-file version và API linkage.
- [ ] Đã so sánh hành vi công khai cần bảo toàn bên cạnh việc chỉ kiểm tra không có exception.
- [ ] Đã lưu classpath/module path, artifact versions, checksum, lệnh chạy và kết quả.
- [ ] Những trường hợp chưa thử hoặc breaking change được công bố rõ cùng kế hoạch migration cho consumer.

## 14. Kết luận

Muốn xác minh tương thích nhị phân trong Java migration, cần chạy **đúng bytecode consumer đã phát hành** với **JAR thư viện mới** và không biên dịch consumer lại. Phép thử này phản ánh điều sẽ xảy ra khi một ứng dụng đang triển khai chỉ thay dependency trong môi trường chạy. Kết hợp baseline cũ, runtime classpath sạch, kiểm tra method/field descriptor bằng javap, các đường code thực tế và ma trận JDK giúp phát hiện lỗi linkage trước khi phát hành. Khi không thể giữ API binary cũ, cần công bố thay đổi tương thích, cung cấp adapter hoặc yêu cầu consumer rebuild/migrate theo lộ trình cụ thể.
