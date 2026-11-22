# Classpath và cách class được tìm kiếm truyền thống

Trong Java truyền thống, **classpath** là tập các thư mục và tệp lưu trữ mà trình biên dịch hoặc runtime sử dụng để tìm class và tài nguyên của ứng dụng. Trước Java Platform Module System (JPMS), phần lớn ứng dụng Java chỉ cần sắp xếp các file **.class** và **.jar** trên classpath rồi chạy một class chứa phương thức **main**. Kể cả từ Java 9 trở đi, cách chạy classpath vẫn được hỗ trợ và đặc biệt phổ biến trong các dự án sử dụng thư viện chưa modular hóa.

Bài học này giải thích classpath thực sự là gì, tên package được chuyển thành đường dẫn bytecode ra sao, class loader tìm và định nghĩa class như thế nào, vì sao classpath lúc biên dịch có thể khác lúc chạy, và cách xử lý lỗi khi thiếu hoặc trùng phiên bản thư viện.

## 1. Classpath chứa những gì?

Một mục classpath có thể là thư mục gốc của cây package hoặc một JAR chứa bytecode và resource:

~~~text
demo/
  out/
    com/example/app/Main.class
    com/example/util/Printer.class
  lib/
    json.jar
    logging.jar
~~~

Nếu classpath chứa thư mục **out**, runtime có thể tìm class **com.example.app.Main** từ file:

~~~text
out/com/example/app/Main.class
~~~

Đối với tên class **com.example.util.Printer**, đường dẫn tương ứng là:

~~~text
out/com/example/util/Printer.class
~~~

Các mục classpath không phải module descriptor. Chúng không nói thư viện nào phụ thuộc vào thư viện nào và không giới hạn các package public theo chỉ thị **exports** của JPMS. Vì vậy, classpath dễ dùng nhưng ít thể hiện được cấu trúc dependency ở cấp kiến trúc.

Các dạng thường gặp:

| Mục classpath | Cách sử dụng |
|---|---|
| **out** | Thư mục gốc chứa các class đã biên dịch. |
| **lib/util.jar** | JAR chứa class và resource của một thư viện. |
| **lib/*** | Wildcard được Java launcher hỗ trợ để đưa các JAR trực tiếp trong thư mục lib vào classpath. |
| **.** | Thư mục làm việc hiện tại. |
| **config** | Thư mục có thể chứa resource và các file class nếu tổ chức đúng đường dẫn. |

## 2. Tên class và đường dẫn bytecode

Xét source:

~~~java
package com.example.util;

public final class Printer {
    private Printer() {
    }

    public static void print(String text) {
        System.out.println(text);
    }
}
~~~

Tên đầy đủ của class là **com.example.util.Printer**. Đó là **binary name** dùng bởi các API nạp class. Trong một layout package thông thường, class loader tìm resource có tên:

~~~text
com/example/util/Printer.class
~~~

Đây là đường dẫn tương đối so với gốc classpath. Do đó, nếu file class nằm dưới thư mục **out**, mục classpath phải là **out**, không phải **out/com/example/util**.

Phân biệt bốn khái niệm:

- **Package:** com.example.util.
- **Simple name:** Printer.
- **Binary name:** com.example.util.Printer.
- **Đường dẫn .class tương đối:** com/example/util/Printer.class.

Sự nhầm lẫn giữa classpath root và package directory là nguyên nhân phổ biến của lỗi **Could not find or load main class**.

## 3. Ví dụ biên dịch và chạy chương trình

Tạo hai file:

~~~text
src/
  com/example/util/Printer.java
  com/example/app/Main.java
~~~

File **Main.java**:

~~~java
package com.example.app;

import com.example.util.Printer;

public final class Main {
    public static void main(String[] args) {
        Printer.print("Hello classpath");
    }
}
~~~

File **Printer.java** là class ở ví dụ trước. Biên dịch cả hai:

~~~bash
javac -d out \
      src/com/example/util/Printer.java \
      src/com/example/app/Main.java
~~~

Chạy:

~~~bash
java -cp out com.example.app.Main
~~~

Kết quả dự kiến:

~~~text
Hello classpath
~~~

Ở đây:

1. **javac** dịch source thành bytecode và đặt output trong cây thư mục phù hợp với package.
2. **-cp out** yêu cầu runtime sử dụng **out** làm một nguồn tìm class.
3. **com.example.app.Main** là binary name của main class.
4. JVM nạp class cần thiết và gọi phương thức main.
5. Khi Main sử dụng Printer, runtime phải tìm được Printer trong phạm vi của class loader.

Không cần biên dịch mọi class vào cùng một thư mục, nhưng những thư mục và JAR cần thiết phải được đưa vào classpath hiệu lực khi chạy.

## 4. Classpath khi biên dịch khác classpath khi chạy

Cả **javac** và **java** đều có tùy chọn **-cp** hoặc **-classpath**, nhưng mỗi công cụ dùng danh sách này vào mục đích khác nhau:

| Công cụ | Vai trò |
|---|---|
| **javac** | Tìm các class và thư viện để phân tích kiểu, kiểm tra tham chiếu và biên dịch source. |
| **java** | Tìm bytecode và resource khi chương trình được thực thi. |

Giả sử **Printer** đã được đóng gói trong **lib/util.jar**. Khi biên dịch Main:

~~~bash
javac -cp lib/util.jar \
      -d app-out \
      src/com/example/app/Main.java
~~~

Khi chạy, cần cả output của app và thư viện:

~~~bash
java -cp "app-out:lib/util.jar" com.example.app.Main
~~~

Nếu runtime chỉ nhận:

~~~bash
java -cp app-out com.example.app.Main
~~~

thì Main có thể được tìm thấy nhưng JVM vẫn không tìm được Printer khi cần. Trường hợp này có thể dẫn tới **NoClassDefFoundError**.

**Biên dịch thành công không có nghĩa runtime classpath đã đủ.** Build tool cũng không tự bảo đảm mọi JAR từng có lúc biên dịch được đưa vào tiến trình Java thực tế.

## 5. Dấu phân cách trên Windows và Unix

Các mục classpath được ngăn cách bằng ký tự phụ thuộc hệ điều hành.

Linux hoặc macOS:

~~~bash
java -cp "out:lib/a.jar:lib/b.jar" com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "out;lib/a.jar;lib/b.jar" com.example.app.Main
~~~

| Hệ điều hành | Ký tự phân cách giữa các mục |
|---|---|
| Linux | Dấu hai chấm |
| macOS | Dấu hai chấm |
| Windows | Dấu chấm phẩy |

Đường dẫn trong chuỗi classpath có thể là tương đối hoặc tuyệt đối. Đối với đường dẫn tương đối, hãy chú ý **working directory** của tiến trình chạy Java.

Dấu nháy kép giúp shell truyền cả chuỗi classpath làm một đối số. Đây là điều đặc biệt hữu ích khi đường dẫn có khoảng trắng hoặc ký tự đặc biệt.

Không nên nhầm dấu chấm trong tên Java package với ký tự phân cách giữa các mục classpath.

## 6. Classpath mặc định và biến môi trường CLASSPATH

Khi chạy theo chế độ classpath mà không chỉ định **-cp**, Java launcher có thể dùng biến môi trường **CLASSPATH** nếu biến này được đặt. Nếu không có cấu hình classpath tường minh hoặc biến môi trường có hiệu lực, mặc định thông thường là thư mục làm việc hiện hành (**.**).

Ví dụ:

~~~bash
java com.example.app.Main
~~~

Lệnh trên chỉ thành công nếu classpath hiệu lực chứa đúng class file của **com.example.app.Main**.

Để tránh phụ thuộc máy đang chạy, nên viết rõ:

~~~bash
java -cp out com.example.app.Main
~~~

Nếu cần thêm thư mục hiện hành, hãy thêm nó vào danh sách theo cách tường minh:

~~~bash
java -cp ".:lib/util.jar" com.example.app.Main
~~~

Windows:

~~~powershell
java -cp ".;lib/util.jar" com.example.app.Main
~~~

Khi truyền **-cp**, đừng mặc định biến **CLASSPATH** hoặc dấu chấm được tự động nối thêm. Trong CI, IDE và môi trường triển khai, cấu hình tường minh giúp lệnh chạy dễ tái hiện hơn.

## 7. Wildcard và thư mục chứa JAR

Java launcher hỗ trợ wildcard classpath:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Windows:

~~~powershell
java -cp "out;lib/*" com.example.app.Main
~~~

Wildcard đưa các JAR được hỗ trợ nằm **trực tiếp** trong thư mục **lib** vào danh sách classpath.

Điều cần nhớ:

- **-cp lib** chỉ đưa thư mục lib vào classpath; nó không có nghĩa quét tất cả JAR trong đó.
- **-cp lib/*** là cú pháp wildcard cho các JAR trực tiếp bên trong lib.
- Wildcard không tự tìm đệ quy xuống các thư mục con.
- Thứ tự mở rộng các JAR qua wildcard không nên được xem là một hợp đồng ổn định để quyết định chọn version thư viện.

Nếu hai JAR có cùng class, việc dựa vào thứ tự wildcard để chọn JAR nào thắng sẽ khiến ứng dụng khó tái hiện và khó kiểm soát.

## 8. JAR lưu class như thế nào?

JAR là archive chứa các mục được tổ chức theo đường dẫn. Sau khi biên dịch **Printer.class** vào **out**, đóng gói:

~~~bash
jar --create \
    --file lib/util.jar \
    -C out com/example/util
~~~

Bên trong archive có thể gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/example/util/Printer.class
~~~

Java không cần giải nén JAR trước khi tìm class: class loader thích hợp có thể đọc class và resource từ archive.

Kiểm tra thành phần JAR:

~~~bash
jar --list --file lib/util.jar
~~~

Nếu file bị đóng gói sai thành:

~~~text
out/com/example/util/Printer.class
~~~

trong khi runtime cần:

~~~text
com/example/util/Printer.class
~~~

thì class loader thông thường có thể không tìm thấy Printer, dù JAR vẫn mở được.

Khi gặp lỗi thiếu class, luôn kiểm tra **tên class**, **vị trí classpath root** và **đường dẫn entry bên trong JAR**.

## 9. java -cp khác java -jar

Có hai cách khởi chạy phổ biến.

Chỉ định classpath và main class:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Hoặc dùng một executable JAR có manifest:

~~~bash
java -jar app.jar
~~~

Trong kiểu thứ hai, manifest thường có dòng:

~~~text
Main-Class: com.example.app.Main
~~~

Với **java -jar**, launcher dùng JAR làm nguồn ứng dụng và không xử lý **-cp** hoặc **CLASSPATH** như cơ chế bổ sung classpath thường dùng cho cách chạy bằng tên main class.

Nếu cần dependency nằm ngoài executable JAR, manifest có thể khai báo **Class-Path**:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/util.jar lib/logging.jar
~~~

Các mục manifest Class-Path dùng quy tắc URL của manifest, thường được giải quyết tương đối từ JAR chứa manifest. Chúng không dùng cách phân tách các mục như chuỗi truyền vào **-cp**.

Khi điều tra lỗi chỉ xuất hiện với **java -jar**, hãy kiểm tra manifest và cách đóng gói dependency, thay vì chỉ thêm **-cp** rồi giả định launcher sẽ dùng nó.

## 10. Class loader là thành phần thực sự tìm bytecode

Classpath mô tả **nguồn tìm kiếm**; **class loader** thực hiện việc tìm và nạp class từ những nguồn nó quản lý.

Một số loader tiêu biểu trong Java hiện đại:

| Loader | Vai trò chính |
|---|---|
| Bootstrap loader | Nạp các class nền tảng cốt lõi của Java runtime. |
| Platform loader | Phục vụ các phần của nền tảng Java theo thiết kế runtime. |
| Application/system loader | Thường chịu trách nhiệm nạp class của ứng dụng từ application classpath. |
| Custom loader | Được framework hoặc ứng dụng triển khai để nạp plugin, bytecode động hoặc nguồn tùy biến. |

Ví dụ xem loader:

~~~java
public final class LoaderInfo {
    public static void main(String[] args) {
        System.out.println(LoaderInfo.class.getClassLoader());
        System.out.println(ClassLoader.getSystemClassLoader());
        System.out.println(ClassLoader.getPlatformClassLoader());
        System.out.println(String.class.getClassLoader());
    }
}
~~~

Đối với những class được bootstrap loader nạp, **getClassLoader()** có thể trả về **null**. Điều này là biểu diễn của API, không phải bằng chứng rằng JVM không có bootstrap loader.

Từ Java 9 trở đi, cấu trúc runtime và triển khai loader không hoàn toàn giống Java 8. Đừng giả định app class loader luôn là **URLClassLoader** hoặc mọi class JDK đều đến từ file **rt.jar**.

## 11. Parent delegation: cơ chế ủy quyền truyền thống

Nhiều class loader sử dụng mô hình **parent-first** qua **ClassLoader.loadClass(...)**. Quy trình mặc định được diễn giải đơn giản:

1. Kiểm tra class đã được nạp bởi loader hiện tại chưa.
2. Nếu chưa, thử ủy quyền cho parent loader.
3. Nếu parent không tìm được, loader tìm trong nguồn của chính nó, thường qua **findClass(...)**.
4. Nếu tìm được bytecode phù hợp, loader định nghĩa class.
5. Nếu không tìm được, quá trình có thể kết thúc bằng **ClassNotFoundException**.

Sơ đồ:

~~~text
loadClass("com.example.util.Printer")
                 |
                 v
         Đã được nạp chưa?
            /          \
          Có           Chưa
          |             |
       Trả về      Hỏi parent loader
                        |
                 Parent không tìm được
                        |
                   findClass(...)
                     /     \
                  Thành    Không
                  công     tìm thấy
                    |         |
                 Class<?>   ClassNotFoundException
~~~

Parent delegation hỗ trợ tái sử dụng các class của nền tảng Java và tránh tình trạng class ở application classpath vô tình thay thế các class cốt lõi.

Tuy nhiên, custom class loader không bắt buộc luôn áp dụng đúng thứ tự parent-first. Framework plugin, application server hoặc container có thể sử dụng chiến lược riêng. Khi gặp trùng class, cần xác định loader cụ thể đang thực hiện việc tìm class.

## 12. loadClass, Class.forName và defineClass

Ba API/cơ chế này có liên quan nhưng khác mục đích.

**ClassLoader.loadClass(String)**:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> type = loader.loadClass("com.example.util.Printer");
System.out.println(type.getName());
~~~

Nó yêu cầu loader trả về hoặc nạp class theo tên nhị phân; thao tác này thông thường không tự khởi tạo class chỉ vì được gọi.

**Class.forName(String)**:

~~~java
Class<?> type = Class.forName("com.example.util.Printer");
~~~

Overload một tham số có hành vi tìm class và thường dẫn đến khởi tạo class theo quy tắc của API.

Nếu muốn trì hoãn initialization:

~~~java
Class<?> type = Class.forName(
    "com.example.util.Printer",
    false,
    ClassLoader.getSystemClassLoader()
);
~~~

**defineClass(...)** là thao tác nội bộ phù hợp của class loader để biến bytecode thành định nghĩa class được JVM quản lý. Code ứng dụng thông thường không cần gọi trực tiếp.

Việc class được tìm thấy, được định nghĩa, được liên kết (**linking**) và được khởi tạo (**initialization**) là các giai đoạn có thể xảy ra ở những thời điểm khác nhau. Một class không nhất thiết được khởi tạo ngay khi class loader đã trả về đối tượng **Class<?>**.

## 13. Class loading thường diễn ra theo nhu cầu

JVM không nhất thiết nạp mọi class từ tất cả JAR có trên classpath khi khởi động.

Ví dụ:

~~~java
public final class Main {
    public static void main(String[] args) {
        System.out.println("Start");

        if (args.length > 0) {
            OptionalFeature.execute();
        }
    }
}
~~~

Nếu nhánh sử dụng OptionalFeature không được thực thi, runtime có thể chưa cần nạp hoặc giải quyết toàn bộ class và dependency của tính năng này.

Vì vậy, một ứng dụng có thể chạy đến main thành công dù một thư viện chỉ được dùng ở chức năng hiếm gặp đang thiếu khỏi runtime classpath. Khi chức năng đó được gọi, ứng dụng mới báo lỗi.

Để kiểm tra dependency đầy đủ, không chỉ khởi động main: phải chạy các đường nghiệp vụ sử dụng những thư viện quan trọng.

## 14. Class trùng và thứ tự tìm class

Giả sử:

~~~text
lib/
  old-client.jar
  new-client.jar
~~~

Cả hai chứa:

~~~text
com/example/client/Client.class
~~~

Trong một class loader tìm theo danh sách classpath có thứ tự, nguồn được tìm trước có thể **che khuất** class cùng tên ở nguồn được tìm sau.

Ví dụ:

~~~bash
java -cp "lib/old-client.jar:lib/new-client.jar:app.jar" \
     com.example.app.Main
~~~

Khi thay đổi thứ tự, class có thể được nạp từ phiên bản khác trong mô hình loader tương ứng. Khi có wildcard, manifest dependency hoặc custom loader, không nên suy luận một quy tắc duy nhất áp dụng cho mọi môi trường.

Hệ quả có thể là:

- **NoSuchMethodError** vì code được compile với API mới nhưng runtime lấy class cũ.
- **NoSuchFieldError** vì field dự kiến không còn trong binary runtime.
- **AbstractMethodError** do class/interface không còn tương thích.
- Behavior thay đổi theo JAR được chọn ngoài ý muốn.

Không nên coi việc đảo thứ tự JAR là sửa lỗi dài hạn. Hãy xác định dependency trùng và loại bỏ xung đột ở cấu hình build hoặc phân phối.

## 15. Định danh class còn phụ thuộc class loader

Trong JVM, cùng một tên binary class vẫn có thể đại diện cho hai kiểu khác nhau nếu chúng được **định nghĩa bởi hai class loader khác nhau**.

Ví dụ host và plugin đều có file:

~~~text
com/acme/plugin/Widget.class
~~~

Nếu hai loader độc lập định nghĩa riêng class này, các đối tượng **Class<?>** không phải cùng một runtime type, dù **getName()** trả về cùng chuỗi.

Hiện tượng có thể dẫn đến lỗi cast hoặc linkage khó hiểu. Để quan sát:

~~~java
System.out.println(obj.getClass().getName());
System.out.println(obj.getClass().getClassLoader());
System.out.println(ExpectedType.class.getClassLoader());
~~~

Khi thiết kế plugin, nên đặt các interface dùng chung vào một loader được host và plugin chia sẻ, thay vì đóng gói riêng một bản API trong mỗi plugin loader.

## 16. Resource cũng được tìm trên classpath

Classpath không chỉ dành cho bytecode. Nó có thể chứa các file cấu hình, template và dữ liệu được ứng dụng đọc như resource.

Ví dụ:

~~~text
out/
  com/example/app/Main.class
  config/default.properties
~~~

Đọc resource:

~~~java
import java.io.InputStream;
import java.util.Properties;

public final class ConfigReader {
    public static Properties load() throws Exception {
        ClassLoader loader = ConfigReader.class.getClassLoader();

        try (InputStream input =
                 loader.getResourceAsStream("config/default.properties")) {
            if (input == null) {
                throw new IllegalStateException("Thiếu default.properties");
            }

            Properties result = new Properties();
            result.load(input);
            return result;
        }
    }
}
~~~

**getResourceAsStream(...)** tìm resource theo quy tắc của loader, không tìm tùy ý trên toàn bộ ổ đĩa.

Cần phân biệt API của **ClassLoader.getResourceAsStream(...)** với **Class.getResourceAsStream(...)**: cách hiểu đường dẫn tương đối và đường dẫn bắt đầu bằng dấu gạch chéo có thể khác nhau.

Khi build JAR, phải xác nhận resource thật sự được copy vào output; có file trong cây source chưa đủ để runtime tìm thấy nó.

## 17. ServiceLoader trong thế giới classpath

Classpath còn hỗ trợ các quy ước tìm metadata. Một ví dụ là **ServiceLoader**.

Nếu service interface là:

~~~text
com.example.spi.Plugin
~~~

JAR provider trên classpath có thể chứa:

~~~text
META-INF/services/com.example.spi.Plugin
~~~

với nội dung:

~~~text
com.example.impl.DefaultPlugin
~~~

Khi code gọi:

~~~java
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);

for (Plugin plugin : loader) {
    plugin.execute();
}
~~~

ServiceLoader có thể đọc các cấu hình service phù hợp từ phạm vi tìm kiếm của class loader để khám phá provider.

Trong ứng dụng có custom loader, provider JAR nằm ngoài classpath của loader đang dùng có thể không được tìm thấy, dù file JAR có mặt trên đĩa. Đây là vấn đề về **nguồn tìm của loader**, không phải tên service interface.

JPMS bổ sung hình thức khai báo **uses** và **provides ... with ...** trong module descriptor, giúp quản lý service ở cấp named module.

## 18. Chẩn đoán ClassNotFoundException và NoClassDefFoundError

Hai lỗi thường gặp nhất khi classpath bị thiếu hoặc khác dự kiến là:

**ClassNotFoundException:** API nạp class theo tên, chẳng hạn **Class.forName(...)**, không tìm được định nghĩa class phù hợp.

~~~java
Class.forName("com.example.driver.MissingDriver");
~~~

**NoClassDefFoundError:** JVM cần một class tại runtime nhưng không thể có định nghĩa class cần thiết, hoặc class từng gặp vấn đề khi khởi tạo; lỗi có thể xuất hiện khi liên kết một class đã biên dịch.

Ví dụ code Main đã compile với:

~~~java
Printer.print("Test");
~~~

nhưng runtime classpath không có Printer.

| Lỗi | Điểm cần kiểm tra |
|---|---|
| **ClassNotFoundException** | Tên binary có đúng? Loader nào tìm? JAR có nằm trong nguồn loader quản lý? |
| **NoClassDefFoundError** | Dependency runtime còn thiếu? Có cause liên quan initialization không? |
| **UnsupportedClassVersionError** | Class được biên dịch cho Java mới hơn runtime? |
| **NoSuchMethodError** | Runtime đang dùng bản class khác bản lúc compile? |
| **ClassCastException** lạ | Hai class trùng tên có cùng defining loader không? |
| **Could not find or load main class** | Classpath root, package, main class và output directory có chính xác không? |

Đọc toàn bộ stack trace và phần **Caused by** để tránh chẩn đoán nhầm.

## 19. Các công cụ kiểm tra classpath

**Kiểm tra JAR có chứa class không:**

~~~bash
jar --list --file lib/util.jar
~~~

Tìm file class đúng đường dẫn:

~~~text
com/example/util/Printer.class
~~~

**Dùng javap để quan sát class đã biên dịch:**

~~~bash
javap -classpath out com.example.app.Main
~~~

**Bật log nạp class trên JDK hiện đại:**

~~~bash
java -Xlog:class+load=info \
     -cp "out:lib/*" \
     com.example.app.Main
~~~

Tùy chọn **-verbose:class** cũng có thể giúp quan sát hoạt động tải class trên các phiên bản Java hỗ trợ.

**In loader và nguồn code khi có class:**

~~~java
Class<?> type = Class.forName("com.example.util.Printer");

System.out.println(type.getClassLoader());

var domain = type.getProtectionDomain();
if (domain != null) {
    System.out.println(domain.getCodeSource());
}
~~~

Thông tin **CodeSource** có thể hỗ trợ tìm vị trí class đến từ đâu nếu loader cung cấp metadata tương ứng; giá trị này không phải lúc nào cũng hiện diện.

**Đối chiếu build configuration:** Kiểm tra runtime dependency graph của Maven/Gradle và lệnh JVM thực tế do IDE, script hoặc container chạy.

## 20. Classpath khác module path ở điểm nào?

Java 9 đưa **JPMS** vào nền tảng và bổ sung **module path**. Classpath vẫn tồn tại, nhưng hai cơ chế có mục tiêu khác nhau.

| Khía cạnh | Classpath truyền thống | Module path / JPMS |
|---|---|---|
| Đơn vị chính | Class và resource được tìm qua class loader. | Named module có descriptor và module graph. |
| Dependency | Do build tool và classpath thực tế quyết định. | **requires**, **requires transitive**, **requires static**. |
| Công bố package | Không có module directive riêng để giới hạn package public giữa các JAR trên classpath. | **exports** công bố API package cho module khác. |
| Deep reflection | Chịu quy tắc Java access và các giới hạn runtime. | **opens** điều khiển deep reflection giữa named modules. |
| JAR truyền thống | Nằm trong unnamed module khi chạy trên classpath trong môi trường JPMS. | Có thể được coi là automatic module trên module path nếu không có module-info.class. |
| Resolution | Chủ yếu dựa trên nguồn tìm class của loader. | Giải module graph trước khi chương trình chạy. |

Chạy theo classpath:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Chạy theo named module:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Không nên xem việc đổi **-cp** thành **--module-path** chỉ là một thay đổi cú pháp. Named module có cơ chế resolution và kiểm soát exports/opens ở cấp module mà các JAR trên classpath truyền thống không có.

## 21. Những hiểu nhầm phổ biến

**“Classpath phải trỏ đến thư mục chứa trực tiếp Main.class.”** Không đúng nếu Main có package: phải trỏ vào gốc cây package để binary name ánh xạ đúng.

**“Đưa lib vào classpath sẽ tự động nhận tất cả JAR dưới lib.”** Không đúng; cần liệt kê JAR hoặc dùng wildcard do launcher hỗ trợ.

**“Class có mặt trong một JAR thì mọi class loader đều tìm thấy.”** Không đúng; JAR phải thuộc phạm vi tìm kiếm của loader phù hợp.

**“Javac thành công nghĩa là runtime đủ dependency.”** Không đúng; classpath của hai giai đoạn có thể khác nhau.

**“JVM nạp mọi class của tất cả JAR lúc bắt đầu.”** Không đúng; nhiều class chỉ được nạp khi cần.

**“Hai class có cùng binary name luôn tương đương.”** Không đúng nếu defining class loader khác nhau.

**“java -jar luôn sử dụng -cp để bổ sung các thư viện ngoài.”** Không đúng; cần hiểu quy tắc của JAR manifest hoặc cách đóng gói.

**“Classpath và module path giống nhau.”** Không đúng; module path là nguồn tham gia JPMS resolution, còn classpath truyền thống không tự tạo named module riêng cho mỗi JAR.

## 22. Checklist thực hành

- Xác định đúng binary name và package của main class.
- Đặt classpath tại gốc cây thư mục chứa package của class.
- Kiểm tra cả compile classpath và runtime classpath.
- Dùng đúng dấu phân tách classpath theo hệ điều hành.
- Phân biệt thư mục **lib** với wildcard cho các JAR bên trong.
- Đóng gói JAR sao cho entry class có đúng đường dẫn tương ứng binary name.
- Phân biệt chạy bằng **java -cp ... Main** và **java -jar app.jar**.
- Không phụ thuộc vào thứ tự JAR để giải quyết dependency xung đột.
- Quan sát class loader khi class trùng hoặc cast lỗi bất thường.
- Xem stack trace để phân biệt lỗi không tìm thấy class với lỗi liên kết.
- Kiểm tra classpath của JVM thực tế do IDE hoặc build tool khởi tạo.
- Khi chuyển sang JPMS, tìm hiểu thêm module resolution, **module-info.java** và ranh giới API.

**Classpath** giải quyết việc tìm kiếm bytecode và resource trong mô hình Java truyền thống. Từ tên binary class, class loader tìm dữ liệu trong những nguồn mà nó quản lý, thường theo cơ chế parent delegation, rồi định nghĩa class để JVM liên kết và sử dụng. Nắm chắc classpath root, các lệnh **javac/java**, JAR packaging và class loader giúp chẩn đoán lỗi dependency chính xác hơn, đồng thời tạo nền tảng để hiểu sự khác biệt khi dùng **module path** của JPMS.