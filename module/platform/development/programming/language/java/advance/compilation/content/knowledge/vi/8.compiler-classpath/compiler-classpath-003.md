# Phân biệt \`import\` với cấu hình classpath trong Java

Khi một tệp Java cần dùng lớp ở package khác, người mới học thường viết \`import\` rồi cho rằng compiler sẽ tự tìm hoặc tải thư viện. Ngược lại, có người thêm JAR vào classpath nhưng mã vẫn báo \`cannot find symbol\` vì dùng tên lớp chưa được khai báo hoặc nhập đúng cách. Hai cơ chế này xử lý **hai câu hỏi khác nhau**:

- **\`import\`** là khai báo trong **mã nguồn**, giúp Java tham chiếu kiểu hoặc thành viên \`static\` bằng **tên ngắn** (simple name) thay vì phải viết tên đủ điều kiện.
- **Classpath** là cấu hình cho **trình biên dịch và trình khởi chạy**, cho biết nơi tìm các định nghĩa lớp và tài nguyên cần thiết khi biên dịch/chạy ứng dụng không sử dụng named module theo JPMS.

Một câu dễ nhớ: **\`import\` giúp viết tên; classpath giúp tìm mã của lớp**. Cả hai có thể cần thiết trong một dự án, nhưng sự hiện diện của cái này không tự tạo cái kia.

## 1. Tên lớp, package, import và classpath

Giả sử có lớp:

~~~java
package library;

public final class Greeting {
    private Greeting() {}

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Lớp có **simple name** là \`Greeting\`; tên đầy đủ theo package là \`library.Greeting\`. Nếu một tệp thuộc package \`app\` muốn dùng lớp này, có hai cách viết.

**Dùng \`import\` để rút gọn tên:**

~~~java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

**Không \`import\`, dùng tên đủ điều kiện:**

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(library.Greeting.message("Mai"));
    }
}
~~~

Hai cách đều hợp lệ **nếu \`library.Greeting\` tồn tại và truy cập được từ quá trình biên dịch**. Đổi cách viết tên không ảnh hưởng đến sự tồn tại của lớp trong thư viện.

Trong cả hai cách, \`javac\` vẫn phải tìm được định nghĩa \`library.Greeting\`: từ nguồn được chỉ định/nguồn tìm thấy theo quy tắc source path, từ class file trong classpath, hoặc cơ chế module thích hợp. Chỉ một dòng \`import library.Greeting;\` **không phải chỉ thị tải library từ mạng hoặc thêm JAR vào classpath**.

## 2. \`import\` thực sự làm gì?

Java Language Specification (JLS) quy định import declaration giúp dùng simple name để chỉ kiểu hoặc static member đã có khả năng truy cập. \`import\` được compiler phân tích khi xử lý **compilation unit** (tệp nguồn đang biên dịch).

| Cú pháp | Hiệu ứng trong mã nguồn | Có thêm thư viện vào classpath? |
| --- | --- | --- |
| \`import java.util.List;\` | Cho phép viết \`List\` thay vì \`java.util.List\` | Không |
| \`import java.util.*;\` | Cho phép dùng simple name của các kiểu phù hợp trong package \`java.util\` khi cần | Không |
| \`import static java.lang.Math.max;\` | Cho phép gọi \`max(3, 5)\` khi không có xung đột tên | Không |
| \`import static java.lang.Math.*;\` | Đưa các static member đủ điều kiện vào phạm vi tìm kiếm tên | Không |
| Không import, viết \`java.util.List<String>\` | Dùng tên đủ điều kiện trực tiếp | Không |

Các điểm quan trọng:

1. **\`import\` không copy code** của một class vào tệp nguồn, không tự giải nén JAR, không tự tải Maven dependency và không thay đổi cách JVM tìm class ở runtime.
2. **Phạm vi của import là tệp nguồn chứa khai báo ấy**, không tự áp dụng cho mọi tệp cùng package. Hai tệp trong package \`app\` vẫn có import riêng nếu cần simple name từ package khác.
3. **Import không trao thêm quyền truy cập.** Một class \`package-private\` ở package khác vẫn không thể truy cập chỉ vì đã viết import; trong named module, package không được \`exports\` cũng không trở thành công khai nhờ import.
4. **Import không bắt buộc** nếu dùng fully qualified name, nhưng cả hai cách đều cần compiler có thể tìm và truy cập type.
5. Các kiểu trong **cùng package** thường có thể được gọi bằng simple name mà không cần import. Các kiểu phù hợp thuộc **\`java.lang\`** cũng có cơ chế import-on-demand ngầm theo JLS; ví dụ \`String\`, \`System\`, \`Math\`.

Ví dụ dễ thấy với thư viện chuẩn:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BasicImport {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println(names.get(0));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -d out BasicImport.java
java -cp out BasicImport
~~~

Kết quả:

~~~text
Lan
~~~

Trong ví dụ này các lớp \`java.util\` thuộc nền tảng Java được JDK cung cấp, nên không cần thêm JAR bên ngoài. **Không nên suy ra mọi package trong \`import\` đều có sẵn trong JDK.**

### 2.1. Import-on-demand không tìm mọi package con

Khai báo:

~~~java
import java.util.*;
~~~

không có nghĩa tự import mọi lớp thuộc những package con như \`java.util.concurrent\`. Muốn dùng \`ExecutorService\` bằng simple name, cần import thích hợp:

~~~java
import java.util.concurrent.ExecutorService;
~~~

hoặc dùng \`java.util.concurrent.ExecutorService\` đầy đủ.

Dấu \`*\` trong import-on-demand là **quy tắc đặt tên của ngôn ngữ**, không phải wildcard đường dẫn classpath và không phải glob duyệt toàn bộ JAR.

### 2.2. Import không cứu được xung đột tên

Ví dụ:

~~~java
import java.sql.*;
import java.util.*;

// Date d;  // Không rõ là java.sql.Date hay java.util.Date
~~~

Hai package cùng cung cấp kiểu tên \`Date\`, nên simple name trở nên mơ hồ trong ngữ cảnh này. Dùng tên đủ điều kiện như \`java.time.LocalDate\` hoặc \`java.util.Date\`/ \`java.sql.Date\` theo đúng ý định, hoặc thêm một single-type import hợp lệ để định danh cụ thể. Sửa classpath không phải phương pháp giải quyết xung đột tên ở ví dụ này.

### 2.3. Import static cũng không phải nạp thư viện

~~~java
import static java.lang.Math.max;

public class StaticImport {
    public static void main(String[] args) {
        System.out.println(max(3, 5));
    }
}
~~~

Kết quả chạy:

~~~text
5
~~~

\`import static\` chỉ giúp viết \`max(...)\` thay cho \`Math.max(...)\`. Nếu static member nằm trong JAR bên ngoài, JAR đó vẫn phải có mặt trên đường tìm lớp phù hợp.

## 3. Classpath là gì?

Classpath, viết tắt của **class search path**, là danh sách các vị trí mà công cụ Java có thể dùng để tìm class và resource trên cơ chế classpath. Một mục trong classpath thường là:

- **Thư mục gốc của cây package** chứa các tệp \`.class\`.
- **Tệp \`.jar\`** (hoặc ZIP tương thích) chứa các entry class/resource.
- **Nhiều mục** được ghép theo dấu phân cách hệ điều hành.

Ví dụ một thư mục class output:

~~~text
out/
└── library/
    └── Greeting.class
~~~

Muốn tìm class tên \`library.Greeting\`, classpath cần chứa **\`out\`**, là **gốc cây package**, chứ không phải \`out/library\`. Từ classpath root \`out\`, công cụ có thể tra tên có dạng \`library/Greeting.class\`.

Với JAR:

~~~text
greeting.jar
└── library/Greeting.class
~~~

Classpath phải tham chiếu **tệp JAR**, ví dụ \`-cp greeting.jar\`, hoặc dùng wildcard JAR trong thư mục chứa nó khi muốn tìm nhiều JAR.

### 3.1. Hai công đoạn có classpath riêng

**Classpath lúc biên dịch** của \`javac\` giúp xác định các class/interface cần để kiểm tra mã nguồn, chữ ký method, generic type và khả năng truy cập. **Classpath lúc chạy** của \`java\` giúp JVM/class loader tìm bytecode cần thực thi.

Hai câu lệnh này có nhiệm vụ riêng:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
java -cp "out/app:out/lib" app.Main
~~~

Trong lệnh đầu, \`out/lib\` giúp **javac** thấy thư viện khi biên dịch \`Main.java\`. Trong lệnh sau, cả **out/app** (class chính) và **out/lib** (dependency) phải có ở runtime. Dấu \`:\` trong lệnh \`java\` ở trên dành cho **Linux/macOS**; **Windows dùng dấu \`;\`**, xem phần 4.

**Cấu hình compiler thành công không tự bảo đảm runtime cũng được cấu hình.** Với Java chạy theo classpath, lỗi runtime thường xảy ra vì classpath chạy thiếu một dependency đã có lúc compile, hoặc có phiên bản JAR không tương thích.

### 3.2. Các tùy chọn thường gặp

| Lựa chọn | Dùng ở đâu | Ý nghĩa |
| --- | --- | --- |
| \`javac -cp PATH\` | Compile time | Nơi tìm compiled dependency và theo quy tắc của javac có thể tìm nguồn nếu không chỉ rõ source path |
| \`javac -classpath PATH\` | Compile time | Đồng nghĩa với \`-cp\` |
| \`javac --class-path PATH\` | Compile time | Cách viết dài hơn |
| \`java -cp PATH Main\` | Runtime | Nơi launcher tìm main class và các dependency theo classpath |
| \`java --class-path PATH Main\` | Runtime | Cách viết dài hơn |
| \`javac -d out\` | Compile time | Nơi ghi class files đầu ra; không tự thay thế \`-cp\` |
| \`javac --source-path src\` | Compile time | Nơi tìm các tệp nguồn bổ sung theo cơ chế source path; khác với classpath class file |
| \`java --module-path PATH -m module/class\` | Runtime JPMS | Đường tìm named module, là cơ chế khác với classpath thông thường |

Đường dẫn trong \`-cp\` có thể gồm nhiều thư mục/JAR. Dấu phân cách:

- **Linux/macOS:** dấu hai chấm \`:\`, ví dụ \`"out/app:out/lib"\`.
- **Windows:** dấu chấm phẩy \`;\`, ví dụ \`"out/app;out/lib"\`.

Trên Windows PowerShell nên đặt danh sách classpath trong dấu nháy để dấu \`;\` không bị shell coi là ranh giới lệnh. Khi chạy shell script đa nền tảng, hãy cấu hình dấu phân cách phù hợp hệ điều hành.

## 4. Ví dụ đầy đủ: import đúng nhưng không có classpath thì vẫn lỗi

Đây là bài thực hành trọng tâm, dùng Java 17+. Cấu trúc dự án:

~~~text
demo/
└── src/
    ├── lib/
    │   └── library/
    │       └── Greeting.java
    └── app/
        └── app/
            └── Main.java
~~~

Tạo **src/lib/library/Greeting.java**:

~~~java
package library;

public final class Greeting {
    private Greeting() {}

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Tạo **src/app/app/Main.java**:

~~~java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

Thực hiện từ thư mục **demo**. Đầu tiên biên dịch riêng thư viện:

~~~bash
javac -d out/lib src/lib/library/Greeting.java
~~~

Lúc này:

~~~text
out/
└── lib/
    └── library/
        └── Greeting.class
~~~

### 4.1. Thử compile app mà không truyền thư viện vào classpath

Giả sử không có bản sao \`library.Greeting\` ở classpath mặc định, chạy:

~~~bash
javac -d out/app src/app/app/Main.java
~~~

Lệnh **không biên dịch được**, dù file Main có dòng \`import library.Greeting;\`. Compiler không tìm được package/type \`library.Greeting\` trên các vị trí tìm kiếm được cấu hình. Thông báo có thể chứa:

~~~text
package library does not exist
cannot find symbol
~~~

Đây là **minh họa phần thông điệp lỗi**, không phải toàn bộ stderr bất biến trên mọi phiên bản javac. Một môi trường đã tự đặt \`CLASSPATH\` hoặc còn nguồn/class ở vị trí mặc định có thể làm kết quả khác; vì thế trong bài thực hành nên dùng thư mục sạch và biết rõ classpath của máy.

### 4.2. Thêm classpath ở bước compile

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

Lệnh này **biên dịch thành công**. Javac thấy \`out/lib/library/Greeting.class\`, xác minh method \`Greeting.message(String)\`, rồi ghi \`out/app/app/Main.class\`.

Nếu đang ở **Linux/macOS**, chạy:

~~~bash
java -cp "out/app:out/lib" app.Main
~~~

Nếu đang ở **Windows PowerShell hoặc CMD**, chạy:

~~~powershell
java -cp "out/app;out/lib" app.Main
~~~

Cả hai cho stdout:

~~~text
Xin chào, Mai!
~~~

Tên truyền cho \`java\` là **\`app.Main\`**, không phải đường dẫn tệp \`app/Main.class\`. Classpath đưa công cụ đến gốc package; cú pháp tên lớp dùng dấu chấm theo tên package.

### 4.3. Thiếu dependency ở runtime dù compile đã thành công

Giữ nguyên class output vừa biên dịch nhưng **bỏ thư viện** khỏi runtime classpath:

~~~bash
java -cp out/app app.Main
~~~

Launcher có thể tìm được \`app.Main\` từ \`out/app\`, nhưng khi phương thức \`main\` cần \`library.Greeting\`, class loader không có đường tìm \`Greeting.class\`. Trường hợp cụ thể này thường thất bại với **NoClassDefFoundError** liên quan \`library/Greeting\` (nguyên nhân gốc là thiếu dependency ở runtime).

Cần sửa **runtime classpath**, không sửa \`import\`, vì mã đã compile và import không có hiệu lực tự tìm JAR lúc chạy.

### 4.4. Ngược lại: bỏ import nhưng vẫn chạy khi classpath đúng

Đổi **src/app/app/Main.java** thành:

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(library.Greeting.message("Mai"));
    }
}
~~~

Biên dịch lại:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

Và chạy bằng một trong các lệnh runtime đầy đủ ở phần 4.2. Kết quả vẫn là:

~~~text
Xin chào, Mai!
~~~

Trong phiên bản này **không có import**. Tên đầy đủ \`library.Greeting\` thay thế cho \`Greeting\`, nhưng dependency vẫn nằm trên classpath lúc biên dịch/chạy.

**Hai phép thử trên chứng minh sự độc lập giữa cách tham chiếu tên và đường tìm bytecode:** import đúng vẫn có thể thiếu classpath; classpath đúng vẫn dùng được khi không có import nhờ tên đủ điều kiện.

## 5. Điều gì xảy ra khi classpath đúng nhưng vẫn thiếu import?

Đổi lại file Main thành phiên bản sau:

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

Lệnh:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

vẫn không biên dịch được: compiler tìm được thư viện trên classpath, nhưng **simple name \`Greeting\` không được đưa vào phạm vi tên có thể sử dụng** ở compilation unit này. Javac thường báo \`cannot find symbol\` đối với \`Greeting\`.

Có hai cách sửa hợp lệ:

1. Viết \`import library.Greeting;\` sau \`package app;\` và trước khai báo class.
2. Viết \`library.Greeting.message("Mai")\` ngay tại điểm sử dụng.

Không cần đổi \`-cp\` vì đường tìm library đã đúng. Trong IDE, thao tác **Organize Imports** hoặc **Add Import** giải quyết kiểu lỗi tên ngắn thiếu import, còn cấu hình dependencies giải quyết kiểu lỗi không tìm thấy thư viện.

## 6. Dùng JAR thay vì thư mục class

Trong dự án thật, library thường được phân phối dưới dạng JAR. Từ cấu trúc ví dụ phần 4, sau khi đã biên dịch \`Greeting.class\`, có thể đóng gói bằng công cụ \`jar\` của JDK:

~~~bash
jar --create --file greeting.jar -C out/lib .
~~~

JAR này chứa entry \`library/Greeting.class\`. Khi đó không cần đưa \`out/lib\` vào classpath; sử dụng JAR thay thế.

Compile app:

~~~bash
javac -cp greeting.jar -d out/app src/app/app/Main.java
~~~

Chạy trên Linux/macOS:

~~~bash
java -cp "out/app:greeting.jar" app.Main
~~~

Chạy trên Windows:

~~~powershell
java -cp "out/app;greeting.jar" app.Main
~~~

Kết quả vẫn là:

~~~text
Xin chào, Mai!
~~~

Đường dẫn tương đối như \`greeting.jar\` được tính từ **thư mục làm việc** tại nơi gọi lệnh. Nếu chuyển nơi chạy chương trình mà không cập nhật đường dẫn, classpath có thể trỏ sai. Việc import trong \`Main.java\` vẫn giữ nguyên vì tên package/class không đổi.

### 6.1. Wildcard JAR của classpath khác với import wildcard

Giả sử có thư mục \`libs\` chứa \`greeting.jar\` và một JAR khác. Runtime có thể sử dụng:

~~~bash
# Linux/macOS
java -cp "out/app:libs/*" app.Main
~~~

~~~powershell
# Windows
java -cp "out/app;libs/*" app.Main
~~~

Dấu \`*\` ở đây là tiện ích classpath được launcher hỗ trợ để đưa các **.jar/.JAR trực tiếp trong thư mục libs** vào đường tìm kiếm; không phải tìm đệ quy các thư mục con và thứ tự các JAR được mở rộng không được bảo đảm. Nó **khác hoàn toàn** với \`import library.*;\`, vốn chỉ ảnh hưởng cách viết simple name của kiểu trong package.

Nên dùng dependency manager hoặc classpath tường minh khi phiên bản JAR và thứ tự nạp quan trọng.

## 7. Default classpath, CLASSPATH và thư mục làm việc

Nếu không chỉ định \`-cp\`/ \`--class-path\`, trong trường hợp classpath thường, \`javac\` và \`java\` có thể dùng biến môi trường **CLASSPATH** nếu được đặt; nếu không thì classpath người dùng mặc định là **thư mục làm việc hiện tại (\`.\`)**. Cách mặc định này giải thích vì sao một ví dụ một tệp đôi khi chạy được, còn cùng lệnh ở thư mục khác thì thất bại.

**Ưu tiên chỉ định \`-cp\` rõ ràng** trong ví dụ, lệnh CI và tài liệu. Điều này tránh sự khác biệt giữa các máy khi có CLASSPATH do môi trường thiết lập từ trước.

Ví dụ:

~~~text
project/
├── out/
│   └── app/
│       └── Main.class
└── src/
    └── app/
        └── Main.java
~~~

Nếu class chứa package \`app\` được ghi dưới \`out/app/Main.class\`, classpath root cần là \`out\`, lệnh chạy là:

~~~bash
java -cp out app.Main
~~~

Chạy \`java app.Main\` từ \`project\` khi classpath mặc định chỉ là \`.\` sẽ không thấy tệp trong **out**. Thêm \`import app.Main;\` vào một source file khác cũng không khiến launcher tự tìm class ở out.

**Lưu ý \`-cp\` được cung cấp sẽ ghi đè classpath lấy từ biến CLASSPATH**, nên nếu muốn cả vị trí mặc định hoặc thư viện khác, hãy liệt kê rõ các mục cần thiết.

## 8. Classpath và sourcepath cũng khác nhau

Khi compiler chưa có \`.class\` của một type nhưng có source tương ứng, javac có cơ chế tìm và biên dịch nguồn bổ sung. Hai tùy chọn phục vụ việc tìm kiếm khác nhau:

- **\`--class-path\` / \`-cp\`**: tìm compiled class/JAR dependencies, và theo cấu hình mặc định của javac có thể được dùng để tìm source nếu **không** chỉ định source path.
- **\`--source-path\` / \`-sourcepath\`**: chỉ rõ nơi tìm **các tệp .java bổ sung** khi compiler cần chúng.

Ví dụ một source root chứa:

~~~text
src/
├── app/
│   └── Main.java
└── library/
    └── Greeting.java
~~~

Có thể biên dịch rõ ràng cả hai nguồn:

~~~bash
javac -d out src/library/Greeting.java src/app/Main.java
~~~

Hoặc cấu hình source path để javac tìm nguồn bổ sung:

~~~bash
javac -sourcepath src -d out src/app/Main.java
~~~

Trong biến thể thứ hai, **Main.java** phải tham chiếu \`library.Greeting\` bằng import hoặc tên đầy đủ như thường lệ. \`-sourcepath src\` giúp compiler tìm \`src/library/Greeting.java\`. **Không có chuyện sourcepath tự viết import**.

Đừng mặc định \`-cp\` là cách chuẩn để build toàn bộ source tree. Với dự án lớn, build tool quản lý source sets, các nguồn cần biên dịch, output, dependency, annotation processing và incremental compilation rõ hơn.

## 9. Java platform, thư viện bên ngoài và công cụ build

### 9.1. Vì sao java.util thường không cần -cp JAR riêng?

Các API tiêu chuẩn như \`java.util.List\`, \`java.time.LocalDate\`, \`java.lang.String\` được JDK/Java runtime cung cấp qua các module nền tảng. Khi biên dịch chương trình trên **classpath thông thường**, javac đã có đường truy cập đến những API nền tảng thích hợp mà chương trình được phép dùng.

Ví dụ:

~~~java
import java.time.LocalDate;

public class TodayExample {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);
        System.out.println(date);
    }
}
~~~

Compile/chạy:

~~~bash
javac -d out TodayExample.java
java -cp out TodayExample
~~~

Stdout:

~~~text
2026-10-28
~~~

Không có JAR ngoài dự án nào cần thêm cho \`java.time\`. Nhưng với package của thư viện bên thứ ba, ví dụ \`com.vendor.client\` do dependency ngoài cung cấp, **chỉ import tên đó chưa đủ**: phải đưa dependency thật vào quá trình compile và runtime theo cách phù hợp.

### 9.2. Maven/Gradle kết nối dependency với compiler

Trong dự án sử dụng Maven hoặc Gradle, người lập trình thường khai báo dependency trong cấu hình build thay vì viết tay chuỗi \`-cp\` dài. Build tool sẽ giải quyết artifact, cấu hình đường tìm class/JAR theo từng scope và truyền chúng vào compiler hoặc task chạy.

**Gradle Java plugin (minh họa cấu hình build.gradle):**

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:library-name:1.2.3'
}
~~~

Đây là **mã minh họa**, sử dụng tọa độ artifact giả định để thể hiện cấu trúc Gradle; không khẳng định artifact đó có trên repository. Khi dùng dự án thật, thay bằng dependency hợp lệ và repository được cấu hình. \`implementation\` thường đưa dependency vào compilation/runtime classpath của main source set theo cấu hình của Java plugin, nhưng tác động chính xác lên consumer API còn phụ thuộc cách đóng gói và plugin.

Sau khi khai báo dependency hợp lệ, source file **vẫn cần import** nếu muốn dùng simple name của type bên package khác. Nếu viết tên đầy đủ, import có thể bỏ. **Thêm import không tự chỉnh build.gradle**, và **thêm dependency không tự viết import vào từng tệp .java**.

## 10. Classpath khác module path và requires trong JPMS

Từ Java 9, **Java Platform Module System (JPMS)** cho phép tổ chức các package vào named module. Khi module có \`module-info.java\`, truy cập type từ module khác liên quan đến **module readability** và **exports**.

Ví dụ minh họa hai descriptor, không phải toàn bộ dự án runnable:

~~~java
// module-info.java của module thư viện
module example.library {
    exports library;
}
~~~

~~~java
// module-info.java của module ứng dụng
module example.app {
    requires example.library;
}
~~~

Tệp Java của ứng dụng vẫn có thể viết:

~~~java
import library.Greeting;
~~~

Nhưng import không thay \`requires example.library;\`, không thay \`exports library;\`, và cũng không thay **--module-path** khi đóng gói/khởi chạy theo named module. Mỗi cơ chế có trách nhiệm riêng:

| Cơ chế | Trả lời câu hỏi |
| --- | --- |
| \`import library.Greeting;\` | “Trong source này, viết \`Greeting\` như tên ngắn được không?” |
| \`-cp path\` | “Với chương trình dựa trên classpath, những class/JAR nào được dùng để compile/run?” |
| \`--module-path path\` | “Những module nào có thể được tìm thấy để resolve?” |
| \`requires example.library;\` | “Module hiện tại đọc module thư viện nào?” |
| \`exports library;\` | “Module thư viện cho phép module khác truy cập public type của package nào?” |

**Khả năng tìm thấy type không đồng nghĩa được phép truy cập type.** Nếu class package-private hoặc package nằm trong named module không exports tới caller, import không thể bỏ qua các quy tắc truy cập. Ngược lại, requires/exports đúng vẫn cần đưa module vào module path hoặc hình thức module resolution tương ứng.

Trong JDK mới hơn có cú pháp **module import** cho một số kịch bản thuận tiện, nhưng đó vẫn là khái niệm về phạm vi tên và không đồng nghĩa tải dependency hoặc sửa classpath; các ví dụ Java 17+ ở trên dùng cú pháp import thông thường.

## 11. Các lỗi thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân thường gặp | Điểm cần kiểm tra |
| --- | --- | --- |
| \`package library does not exist\` khi compile | Dependency/source không ở vị trí mà javac tìm thấy | \`-cp\`, \`-sourcepath\`, đường dẫn JAR, package path |
| \`cannot find symbol: Greeting\` | Simple name không được khai báo/import, hoặc compiler không tìm được định nghĩa | Import/tên đủ điều kiện **và** classpath |
| \`class file for ... not found\` | Thiếu class cần để phân tích chữ ký dependency | Compile classpath, JAR phụ thuộc gián tiếp |
| \`Could not find or load main class app.Main\` | Runtime classpath không chứa đúng main class hoặc truyền sai tên | Runtime \`-cp\`, classpath root, package, main class name |
| \`NoClassDefFoundError\` khi chạy | Class từng được nhắc tới nhưng không nạp được lúc runtime; có thể do JAR thiếu hoặc lỗi khởi tạo | Runtime classpath, nguyên nhân gốc của stack trace |
| \`ClassNotFoundException\` | API nạp class bằng tên không tìm được class phù hợp | Tên đầy đủ, class loader và runtime classpath |
| \`NoSuchMethodError\` | Có class ở runtime nhưng phiên bản khác với API lúc compile | Trùng JAR, thứ tự classpath, phiên bản dependency |
| Import trùng tên \`Date\` | Mâu thuẫn tên giữa nhiều type cùng simple name | Single-type import hoặc tên đủ điều kiện |
| Chạy được trong IDE nhưng lỗi trong terminal | IDE đã tự thêm dependency/output vào classpath | Sao chép đúng runtime classpath hoặc dùng build tool |
| Thêm JAR vào build nhưng chạy \`java -cp out ...\` thiếu thư viện | Classpath biên dịch và chạy khác nhau | Truyền đầy đủ entries khi khởi chạy |

Các triệu chứng không luôn có một nguyên nhân duy nhất. Đặc biệt \`NoClassDefFoundError\` có thể do nguyên nhân khởi tạo lớp hoặc class loader khác, nên hãy đọc **cause** trong stack trace; không tự kết luận mọi \`NoClassDefFoundError\` đều do thiếu JAR.

### 11.1. Kiểm tra theo thứ tự nào?

Nếu một lớp bên ngoài không dùng được:

1. Xác nhận **tên package và public type** trong source/JAR; đừng đoán từ tên JAR. Tệp \`Greeting.class\` cần nằm đúng cây package như \`library/Greeting.class\`.
2. Xác định lỗi là **compile-time** hay **runtime**. Khi javac báo lỗi, xem **compile classpath**; khi java báo lỗi, xem **runtime classpath**.
3. Thử dùng **fully qualified name** ngay trong source. Nếu cách này hợp lệ khi compile, lỗi trước đó có thể chỉ là vấn đề import/tên ngắn.
4. Nếu dùng fully qualified name vẫn không thấy type, kiểm tra **đường dẫn dependency, phiên bản JAR, khả năng truy cập** và source path/module path thích hợp.
5. Đảm bảo classpath trỏ đến **gốc package**, không trỏ trực tiếp thư mục của class khi tên lớp có package.
6. Nếu dùng Maven/Gradle, xem đường dependency thực tế của source set/task; không sửa từng lệnh chạy bằng tay rồi quên cấu hình build.
7. Khi gặp duplicate class trong nhiều JAR, kiểm tra artifact/classpath thực tế. Thứ tự tìm kiếm có thể ảnh hưởng class được nạp, nhưng không nên dùng thứ tự để che xung đột phiên bản.

### 11.2. Dùng lệnh nào để quan sát?

Tùy quy mô dự án:

~~~bash
javac -verbose -cp out/lib -d out/app src/app/app/Main.java
~~~

\`-verbose\` giúp quan sát tệp/class được javac xử lý. Output nhiều dòng và phụ thuộc JDK nên không cố định trong bài.

~~~bash
java -XshowSettings:properties -version
~~~

Lệnh này có thể hiển thị các system properties, trong đó có thông tin liên quan đến \`java.class.path\` trong môi trường chạy; thông tin chính xác phụ thuộc runtime và tham số được dùng.

~~~bash
jar --list --file greeting.jar
~~~

Dùng để kiểm tra package path và nội dung JAR, giúp phân biệt “JAR đã được thêm” với “JAR thật sự chứa class cần tìm”.

Các câu lệnh trên chỉ là công cụ chẩn đoán. Đọc output trong môi trường thật vì classpath, locale và phiên bản JDK khác nhau.

## 12. Những hiểu nhầm thường gặp

1. **“Có import là Java tự tải thư viện.”** Không. Import chỉ được phân tích trong source; download/resolve dependency thuộc build tool hoặc quy trình cung cấp JAR.
2. **“Thêm JAR vào classpath thì khỏi cần import.”** Chỉ đúng nếu dùng tên đủ điều kiện hoặc type đã sẵn trong phạm vi tên. Dùng simple name từ package khác thường cần import.
3. **“Mỗi lần biên dịch cùng một classpath thì runtime tự nhớ nó.”** Không. Lệnh \`javac -cp\` và \`java -cp\` là hai lần cấu hình riêng.
4. **“\`import library.*\` là đưa mọi JAR vào classpath.”** Không. Dấu sao của import chỉ nói về tập kiểu theo package, không chỉnh đường tìm class.
5. **“Classpath luôn trỏ đến thư mục chứa tệp .class.”** Nó phải trỏ đúng **gốc cây package**; với \`library.Greeting\`, đường dẫn tương đối được tìm là \`library/Greeting.class\`.
6. **“\`-d out\` đã đủ để compiler tìm phụ thuộc.”** \`-d\` chọn nơi xuất bytecode; \`-cp\` chọn nơi tìm compiled dependency.
7. **“Bỏ import là đổi bytecode hoặc cách class loader tìm JAR.”** Hai hình thức \`Greeting\` qua import và \`library.Greeting\` đầy đủ có thể tham chiếu cùng một type; import không được lưu như một cấu hình classpath runtime.
8. **“Classpath là toàn bộ cơ chế dependency trong Java 9+.”** Named modules có module path, requires/exports và quy tắc JPMS riêng.
9. **“IDE chạy được thì mọi lệnh java đều chạy được.”** IDE thường tự tính compile/run classpath; cần tái hiện cấu hình khi chạy ngoài IDE.
10. **“Đổi import sửa được lỗi NoClassDefFoundError.”** Lỗi lúc chạy thường liên quan nạp/khởi tạo class, trong khi import chỉ có vai trò tại compile time.

## 13. Bài tập tự thực hành

**Bài 1: Chứng minh import không thay classpath.** Dùng hai tệp **Greeting.java** và **Main.java** ở phần 4. Compile thư viện. Thử compile app không có \`-cp out/lib\`, rồi thêm \`-cp out/lib\`. Ghi lại khác biệt.

**Bài 2: Chứng minh classpath không bắt buộc import.** Xóa \`import library.Greeting;\`, thay lời gọi bằng \`library.Greeting.message("Mai")\`. Compile/run với classpath đúng, xác minh stdout giữ nguyên.

**Bài 3: Tạo lỗi tên đơn giản.** Giữ classpath đúng nhưng viết \`Greeting.message("Mai")\` mà không import. Ghi lại diagnostic \`cannot find symbol\`; sửa theo một trong hai cách phù hợp.

**Bài 4: Phân biệt compile và runtime classpath.** Compile thành công rồi chạy \`java -cp out/app app.Main\` khi thư viện chỉ ở \`out/lib\`. Xác định dependency bị thiếu. Sau đó chạy với cả hai entry.

**Bài 5: Đóng gói JAR.** Tạo \`greeting.jar\`, biên dịch app với \`-cp greeting.jar\` và chạy với \`-cp\` có cả app output và JAR. Kiểm tra entry \`library/Greeting.class\` bằng \`jar --list\`.

**Bài 6: Suy luận về wildcard.** Với \`import java.util.*;\`, hãy giải thích vì sao \`List\` có thể dùng bằng simple name nhưng \`ExecutorService\` vẫn cần import riêng hoặc tên đủ điều kiện.

## 14. Câu hỏi tự kiểm tra

- \`import\` được compiler dùng ở giai đoạn nào? Classpath được javac/java dùng để làm gì?
- Vì sao \`import library.Greeting;\` không tự thêm \`greeting.jar\` vào dependency list?
- Một source file có thể dùng class ở package khác mà không viết import không? Bằng cách nào?
- Vì sao \`javac -cp out/lib\` không bảo đảm \`java -cp out/app app.Main\` chạy thành công?
- Với class \`library.Greeting\` trong \`out/lib/library/Greeting.class\`, classpath entry phải là gì?
- Điểm khác nhau giữa \`import java.util.*;\` và \`java -cp "libs/*" ...\` là gì?
- Vì sao \`javac -d out\` và \`javac -cp out\` không thể thay thế nhau?
- Trong JPMS, vì sao \`import\` không thể thay \`requires\` và \`exports\`?
- Nếu chương trình chỉ chạy trong IDE nhưng lỗi ở terminal, bạn sẽ kiểm tra compile và runtime classpath như thế nào?

## 15. Tài liệu tham khảo chính thức

- **Java Language Specification 21, §7.5 – Import Declarations:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5
- **Java Language Specification 21, §6 – Names:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html
- **Oracle Java 21, The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java 21, The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Java Platform Module System, JLS §7.7 – Module Declarations:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7

**Ghi nhớ:** \`import\` kiểm soát **cách gọi tên** lớp hoặc static member trong một tệp nguồn; classpath kiểm soát **nơi javac và java tìm class/JAR**. Lỗi của chúng cần được xử lý tại đúng vị trí: thiếu import thì sửa tên tham chiếu; thiếu compile/runtime dependency thì sửa cấu hình đường tìm lớp.