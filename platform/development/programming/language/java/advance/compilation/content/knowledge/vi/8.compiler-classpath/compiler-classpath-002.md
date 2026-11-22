# Dùng thư mục class và tệp JAR làm phụ thuộc

Một chương trình Java hiếm khi chỉ có một lớp. Lớp `Main` có thể gọi `NumberUtils` do nhóm tự viết, lớp từ một thư viện ngoài hoặc nhiều thành phần đã được biên dịch trước. Để **biên dịch** mã tham chiếu tới các lớp ấy, `javac` cần biết nơi tìm các kiểu/phương thức được khai báo; để **chạy** chương trình, JVM cũng cần tìm được các lớp phụ thuộc tương ứng.

**Classpath** là danh sách vị trí mà công cụ Java dùng để tìm các lớp và tài nguyên trên đường dẫn lớp (class path). Với mã chạy ở **unnamed module** theo cơ chế classpath truyền thống, mỗi mục thường là **thư mục gốc của các tệp `.class`** hoặc **một tệp JAR**. Bài này thực hành cả hai dạng, giải thích cấu trúc package, cách dùng `-cp`/`-classpath` và lỗi thường gặp khi compile classpath khác runtime classpath.

Ví dụ xuyên suốt: một thư viện `demo.tools.NumberUtils` có phương thức nhân đôi; ứng dụng `demo.app.Main` gọi phương thức đó để in `Kết quả: 14`. Bạn sẽ biên dịch và chạy ứng dụng một lần bằng **thư mục chứa class**, rồi một lần bằng **JAR chứa cùng lớp**.

## 1. Classpath là danh sách những gốc tìm kiếm gì?

Khi mã dùng lớp `demo.tools.NumberUtils`, tên đầy đủ (fully qualified class name) được ánh xạ với đường dẫn tương đối:

~~~text
demo.tools.NumberUtils
          |
          v
demo/tools/NumberUtils.class
~~~

Công cụ Java ghép **mỗi phần tử classpath** với đường dẫn tương đối theo package để tìm tệp lớp. Ví dụ:

~~~text
out/lib/                           <- một classpath root
  demo/
    tools/
      NumberUtils.class

lib/math-utils.jar                 <- một classpath entry khác
  demo/tools/NumberUtils.class     <- entry bên trong JAR
~~~

Khi truyền `out/lib`, công cụ tìm `out/lib/demo/tools/NumberUtils.class`. Khi truyền `lib/math-utils.jar`, nó tìm entry `demo/tools/NumberUtils.class` **bên trong JAR**.

**Không truyền thư mục `out/lib/demo/tools` làm classpath root** nếu lớp có package `demo.tools`. Làm thế sẽ khiến công cụ tìm đường dẫn sai. Phần tử classpath là **gốc phía trên cây package**, không phải thư mục chứa trực tiếp class cuối cùng.

Một mục classpath có thể là:

| Mục | Ví dụ | Công dụng |
| --- | --- | --- |
| Thư mục class | `out/lib` | Tìm lớp và resource theo cấu trúc package bên dưới thư mục |
| Tệp JAR | `lib/math-utils.jar` | Tìm entry class/resource trong archive |
| Nhiều mục | `out/app:out/lib` trên Unix | Tìm trong các vị trí chỉ định |
| Wildcard JAR | `lib/*` | Bao gồm các JAR trực tiếp trong thư mục `lib`; không tìm JAR ở mọi thư mục con |

Một thư mục chứa nhiều JAR **không tự động làm các JAR đó nằm trong classpath** khi bạn chỉ truyền đường dẫn thư mục. Muốn dùng từng JAR, hãy liệt kê tệp tương ứng hoặc dùng wildcard `lib/*`.

### Từ khóa `import` không tải hay nạp thư viện

Câu:

~~~java
import demo.tools.NumberUtils;
~~~

giúp mã nguồn dùng tên ngắn `NumberUtils` theo quy tắc phân giải tên của Java. Nó **không tải thư viện từ Internet, không đưa JAR vào classpath và không bảo đảm lớp tồn tại**. Nếu không có class tương ứng trên compile classpath (hoặc một đầu vào nguồn thích hợp cho `javac`), bạn vẫn gặp lỗi biên dịch.

Maven và Gradle có thể tải dependency từ repository, nhưng hành vi đó do **công cụ quản lý dependency** thực hiện. Sau khi tải, chúng cấu hình classpath cho trình biên dịch/runtime; `import` chỉ là một cấu trúc của ngôn ngữ.

## 2. Chuẩn bị dự án nhỏ có thư viện và ứng dụng

Tạo các thư mục/tệp theo cây sau, với chính xác nội dung và tên package:

~~~text
classpath-demo/
├── libsrc/
│   └── demo/
│       └── tools/
│           └── NumberUtils.java
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
├── out/
│   ├── lib/               (sản phẩm biên dịch thư viện)
│   └── app/               (sản phẩm biên dịch ứng dụng)
└── lib/                   (vị trí chứa JAR sau khi đóng gói)
~~~

Các thư mục `out/lib`, `out/app` và `lib` là đầu ra/thư mục chứa artifact; trước khi chạy lệnh `javac -d`/`jar --file`, chúng phải tồn tại. Trong một shell Unix/macOS, từ thư mục `classpath-demo` có thể chạy:

~~~sh
mkdir -p out/lib out/app lib
~~~

Trên Windows PowerShell, nếu thư mục chưa tồn tại, có thể tạo bằng:

~~~powershell
New-Item -ItemType Directory -Force out/lib, out/app, lib | Out-Null
~~~

Hai lệnh trên là hai lựa chọn theo hệ điều hành, **không cần chạy cả hai**. Để tạo `libsrc/demo/tools` và `appsrc/demo/app`, bạn có thể dùng IDE/trình soạn thảo tạo package, hoặc tạo thư mục trước khi lưu các tệp nguồn. Mọi lệnh tiếp theo chạy từ gốc `classpath-demo`.

**Tệp `libsrc/demo/tools/NumberUtils.java`:**

~~~java
package demo.tools;

public final class NumberUtils {
    private NumberUtils() {
    }

    public static int doubleOf(int number) {
        return number * 2;
    }
}
~~~

Lớp này `public`, phương thức `doubleOf` là `public static` nên mã ứng dụng ở package khác có thể gọi trực tiếp mà không cần tạo đối tượng `NumberUtils`. Constructor `private` ngăn tạo instance không cần thiết.

**Tệp `appsrc/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.tools.NumberUtils;

public class Main {
    public static void main(String[] args) {
        int input = 7;
        int result = NumberUtils.doubleOf(input);
        System.out.println("Kết quả: " + result);
    }
}
~~~

`Main` và `NumberUtils` là hai lớp ở hai package khác nhau. `Main` có phụ thuộc **lúc biên dịch** vào khai báo `NumberUtils.doubleOf(int)` và có phụ thuộc **lúc chạy** vào bytecode phù hợp của `NumberUtils`.

## 3. Cách 1: Dùng thư mục chứa `.class` làm dependency

### Bước 1 — Biên dịch thư viện

~~~sh
javac -encoding UTF-8 -d out/lib libsrc/demo/tools/NumberUtils.java
~~~

`-d out/lib` yêu cầu trình biên dịch đặt sản phẩm vào thư mục đầu ra đó, đồng thời tạo cấu trúc package bên trong. Kết quả chính:

~~~text
out/lib/
└── demo/
    └── tools/
        └── NumberUtils.class
~~~

Đến đây ứng dụng chưa được biên dịch. `out/lib` là **classpath root** của lớp thư viện.

### Bước 2 — Biên dịch ứng dụng với thư mục thư viện

~~~sh
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
~~~

Trong lệnh này:

- `-cp out/lib` (tương đương `-classpath out/lib`) cho `javac` biết nơi tìm khai báo của `demo.tools.NumberUtils`.
- `-d out/app` đặt `Main.class` vào `out/app/demo/app/`.
- `appsrc/demo/app/Main.java` là tệp nguồn ứng dụng đang biên dịch.
- Trình biên dịch dùng lớp thư viện đã biên dịch; lệnh này **không đóng gói thư viện vào `Main.class`**.

Kết quả chính:

~~~text
out/
├── lib/
│   └── demo/tools/NumberUtils.class
└── app/
    └── demo/app/Main.class
~~~

### Bước 3 — Chạy ứng dụng với cả hai classpath root

Dấu phân tách giữa **các phần tử classpath** phụ thuộc hệ điều hành. Trên Linux/macOS dùng dấu hai chấm `:`:

~~~sh
java -cp "out/app:out/lib" demo.app.Main
~~~

Trên Windows (Command Prompt hoặc PowerShell) dùng dấu chấm phẩy `;`:

~~~powershell
java -cp "out/app;out/lib" demo.app.Main
~~~

Chạy **một** lệnh phù hợp với môi trường. Kết quả:

~~~text
Kết quả: 14
~~~

Vì `demo.app.Main` nằm ở `out/app` và `demo.tools.NumberUtils` nằm ở `out/lib`, JVM cần thấy **cả hai gốc**. Tên lớp truyền cho `java` là `demo.app.Main`, không phải `Main.class` hoặc `out/app/demo/app/Main.class`.

Có thể đảo thứ tự hai root trong ví dụ này vì không trùng lớp; nhưng **thứ tự classpath có thể ảnh hưởng việc lớp/tài nguyên nào được tìm thấy trước nếu có các bản trùng tên**. Vì vậy không nên dựa vào thứ tự ngẫu nhiên của các artifact.

## 4. Cách 2: Đóng gói lớp thư viện thành JAR

JAR (Java Archive) là định dạng archive dựa trên ZIP, dùng để nhóm tệp lớp, resource và metadata. Trong tình huống này, chúng ta chỉ đóng gói **thư viện**; `Main.class` vẫn giữ trong `out/app`.

Từ gốc `classpath-demo`, sau khi đã biên dịch thư viện và tạo thư mục `lib`, chạy:

~~~sh
jar --create --file lib/math-utils.jar -C out/lib .
~~~

Giải thích:

- `jar --create` tạo archive mới.
- `--file lib/math-utils.jar` chỉ tên JAR đầu ra.
- `-C out/lib .` chuyển ngữ cảnh lấy tệp sang `out/lib` và đưa toàn bộ nội dung tại đó vào archive. Không đưa chuỗi `out/lib` vào đường dẫn mỗi entry.
- Kết quả JAR chứa `demo/tools/NumberUtils.class` theo đúng cấu trúc package (và manifest do công cụ tạo).

Kiểm tra danh sách entry:

~~~sh
jar --list --file lib/math-utils.jar
~~~

Trong danh sách cần có:

~~~text
demo/tools/NumberUtils.class
~~~

Lệnh `jar --list` có thể in thêm entry như `META-INF/` và `META-INF/MANIFEST.MF`; thứ tự trình bày không phải điều ta dùng để xác định tính đúng. Nếu JAR chứa đường dẫn `out/lib/demo/tools/NumberUtils.class` thay vì `demo/tools/NumberUtils.class`, cách đóng gói đã sai đối với package và classpath root mong muốn.

### Biên dịch ứng dụng với JAR thay cho thư mục class

~~~sh
javac -encoding UTF-8 -cp lib/math-utils.jar -d out/app appsrc/demo/app/Main.java
~~~

Chính xác cùng mã nguồn ứng dụng; chỉ đổi **đầu vào dependency từ thư mục `out/lib` sang JAR**. Khi tìm `demo.tools.NumberUtils`, `javac` đọc entry trong archive.

Chạy trên Linux/macOS:

~~~sh
java -cp "out/app:lib/math-utils.jar" demo.app.Main
~~~

Chạy trên Windows:

~~~powershell
java -cp "out/app;lib/math-utils.jar" demo.app.Main
~~~

Stdout vẫn là:

~~~text
Kết quả: 14
~~~

**Một JAR dùng làm dependency không nhất thiết phải chạy độc lập bằng `java -jar`.** JAR thư viện này không cần `Main-Class`, vì nhiệm vụ của nó là cung cấp lớp `NumberUtils` cho ứng dụng. Lệnh `java -jar lib/math-utils.jar` không phải cách thử đúng chức năng thư viện khi JAR không có điểm vào ứng dụng.

### Chúng ta có vừa tạo “fat JAR” hay không?

**Chưa.** `lib/math-utils.jar` chỉ chứa lớp thư viện. `Main.class` còn ở ngoài, trong `out/app`; runtime classpath vẫn phải chỉ đủ hai nơi.

Một fat/uber JAR (nếu được đóng gói đúng) có thể gom nhiều lớp/phụ thuộc vào một artifact, nhưng đó là **chiến lược đóng gói khác**. Trong bài này, điều cần hiểu là một JAR có thể là **một phần tử classpath**, tương đương về vai trò tìm lớp với một thư mục gốc chứa `.class`.

## 5. Compile classpath khác runtime classpath

Hai lệnh sau giải quyết hai câu hỏi khác nhau:

| Giai đoạn | Lệnh ví dụ | Cần tìm gì? |
| --- | --- | --- |
| Biên dịch | `javac -cp lib/math-utils.jar -d out/app appsrc/demo/app/Main.java` | Khai báo lớp, phương thức, kiểu mà `Main.java` dùng |
| Chạy | `java -cp "out/app:lib/math-utils.jar" demo.app.Main` | Bytecode thực tế để JVM nạp và thực thi các lớp |

`javac` kiểm tra được lời gọi `NumberUtils.doubleOf(int)` dựa trên thư viện compile-time. Nhưng khi chạy, JVM phải **tìm lại lớp** từ runtime classpath. `javac` không sao chép mọi dependency vào classfile ứng dụng.

Giả sử biên dịch thành công với JAR nhưng thử chạy **thiếu JAR**:

~~~sh
java -cp out/app demo.app.Main
~~~

Lệnh này giống nhau trên Windows và Unix vì chỉ có **một** phần tử classpath. JVM tìm được `demo.app.Main` nhưng khi mã gọi `NumberUtils`, JVM không tìm thấy lớp thư viện và có thể ném lỗi dạng:

~~~text
java.lang.NoClassDefFoundError: demo/tools/NumberUtils
~~~

Thông báo đầy đủ và stack trace tùy JDK; phần quan trọng là **thư viện có mặt khi compile nhưng vắng mặt lúc chạy**. Thêm lại classpath chứa thư viện thì giải quyết trường hợp cụ thể đó.

Nếu ngay từ đầu biên dịch `Main.java` mà thiếu dependency, bạn thường thấy lỗi như:

~~~text
package demo.tools does not exist
~~~

hoặc lỗi liên quan không tìm thấy ký hiệu `NumberUtils`. Đó là lỗi **compile classpath**, khác với `NoClassDefFoundError` lúc chạy.

### Phân biệt thêm các lỗi phổ biến

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| `package demo.tools does not exist` | Compiler không tìm được package trên nguồn/classpath phù hợp |
| `cannot find symbol` cho `NumberUtils` | Sai tên/`import`, thiếu class hoặc dependency không nằm trong compile classpath |
| `Could not find or load main class demo.app.Main` | Sai tên lớp chính hoặc thiếu `out/app` trong runtime classpath |
| `NoClassDefFoundError: demo/tools/NumberUtils` | Có mã gọi lớp nhưng lớp không sẵn sàng để nạp ở runtime; kiểm tra JAR/root/phụ thuộc |
| `ClassNotFoundException` | Thường liên quan nạp lớp động qua API, hoặc là nguyên nhân bên trong lỗi nạp lớp |
| `NoSuchMethodError` | Có thể do lúc chạy dùng một phiên bản thư viện khác chữ ký so với lúc biên dịch |
| `UnsupportedClassVersionError` | Runtime không hiểu phiên bản classfile vừa biên dịch |

**Không phải mọi `NoClassDefFoundError` đều có một nguyên nhân duy nhất.** Ngoài vắng class, lỗi khởi tạo lớp thất bại trước đó cũng có thể dẫn tới `NoClassDefFoundError` ở lần sử dụng sau. Muốn chẩn đoán chính xác, đọc toàn bộ exception/cause, kiểm tra artifact và các dependency thực tế.

## 6. Cách ghi nhiều dependency cùng lúc

Khi ứng dụng có nhiều thư mục class và JAR, các mục classpath nối với nhau bằng ký tự phân tách của hệ điều hành:

- **Unix/Linux/macOS:** `:`
- **Windows:** `;`

Ví dụ trên Unix:

~~~sh
javac -cp "out/lib:lib/math-utils.jar" -d out/app appsrc/demo/app/Main.java
java -cp "out/app:out/lib:lib/math-utils.jar" demo.app.Main
~~~

Trên Windows:

~~~powershell
javac -cp "out/lib;lib/math-utils.jar" -d out/app appsrc/demo/app/Main.java
java -cp "out/app;out/lib;lib/math-utils.jar" demo.app.Main
~~~

Trong ví dụ chính, đưa **cả thư mục lẫn JAR chứa cùng lớp** là dư thừa và có thể gây nhầm phiên bản; các lệnh trên chỉ minh họa cú pháp khi có nhiều mục. Trong dự án thật, chỉ thêm những dependency cần dùng, tránh một lớp xuất hiện ở nhiều nơi trên classpath.

### Wildcard cho nhiều JAR trong một thư mục

Nếu thư mục `lib` chứa một hoặc nhiều tệp JAR trực tiếp, có thể dùng `lib/*` trong classpath. Trên Unix:

~~~sh
javac -cp "lib/*" -d out/app appsrc/demo/app/Main.java
java -cp "out/app:lib/*" demo.app.Main
~~~

Trên Windows:

~~~powershell
javac -cp "lib/*" -d out/app appsrc/demo/app/Main.java
java -cp "out/app;lib/*" demo.app.Main
~~~

Dấu ngoặc kép trong ví dụ giúp **shell không tự mở rộng wildcard** trước khi công cụ Java xử lý nó. Classpath wildcard của Java áp dụng cho các JAR trực tiếp dưới thư mục được chỉ định, không tự tìm class rời ở đó và **không đệ quy vào thư mục con**. Nó cũng không cam kết thứ tự chọn các JAR theo tên; tránh dùng wildcard nếu có nhiều bản cùng lớp cần kiểm soát chặt.

**Đừng viết `-cp lib` rồi kỳ vọng JVM tự đọc toàn bộ `lib/*.jar`.** `lib` là một thư mục classpath root, còn `lib/*` biểu thị các tệp JAR trực tiếp trong nó.

### Khi nào cần thêm dấu `.`?

Nếu bạn đặt classfile của ứng dụng ngay tại classpath root là thư mục làm việc hiện tại, có thể chỉ định `.`:

~~~sh
java -cp ".:lib/math-utils.jar" demo.app.Main
~~~

Trên Windows:

~~~powershell
java -cp ".;lib/math-utils.jar" demo.app.Main
~~~

Đây là ví dụ về **cú pháp classpath**; nó chỉ tìm thấy `demo.app.Main` nếu cấu trúc `demo/app/Main.class` thật sự nằm dưới thư mục hiện tại. Với cây bài học này, class `Main` nằm trong `out/app` nên cần dùng `out/app`, không dùng `.` thay thế tùy tiện.

Khi **không cung cấp `-cp`** và không cấu hình `CLASSPATH`, classpath ứng dụng mặc định thường là thư mục hiện tại. Khi đã cung cấp `-cp`, bạn đã quy định danh sách tìm kiếm mới; **`.` không tự được cộng thêm**. Nếu cần thư mục hiện tại, hãy thêm rõ `.` vào danh sách. Một biến môi trường `CLASSPATH` có thể ảnh hưởng khi không có `-cp`; để bài học và CI có tính tái lập, ưu tiên cấu hình tường minh.

## 7. Package, tên lớp và đường dẫn: ba yếu tố phải khớp

Trong ví dụ, câu:

~~~java
package demo.tools;
~~~

khiến tên lớp thư viện là `demo.tools.NumberUtils`. Với đầu ra biên dịch bằng `-d out/lib`, đường dẫn lớp là `out/lib/demo/tools/NumberUtils.class`. Với JAR, entry là `demo/tools/NumberUtils.class`.

Bốn lỗi dễ mắc:

1. **Trỏ vào thư mục quá sâu:** `-cp out/lib/demo/tools` thay vì `-cp out/lib` làm JVM/compiler tìm sai đường dẫn package.
2. **Truyền đường dẫn tệp lớp cho `java`:** `java out/app/demo/app/Main.class` không phải cách gọi main class chuẩn; phải dùng `java -cp out/app demo.app.Main`.
3. **Đóng gói cả thư mục ngoài vào JAR:** Archive có entry `out/lib/demo/tools/NumberUtils.class` sẽ không khớp đường dẫn tìm lớp `demo/tools/NumberUtils.class`.
4. **Chỉ có đúng `import` nhưng thiếu dependency:** `import` không tạo lớp; phải có tệp nguồn/class/JAR trên đường tìm kiếm thích hợp.

Lưu ý rằng **đường dẫn tệp nguồn** và **đường dẫn đầu ra theo package** là hai khái niệm khác nhau. Convention `appsrc/demo/app/Main.java` giúp con người quản lý mã, còn `javac -d out/app` quyết định bố cục classfile đầu ra. Dù có thể tổ chức source theo cách khác trong vài trường hợp, dự án nên giữ cấu trúc tương ứng package để công cụ build và IDE dễ hiểu.

## 8. Tài nguyên không phải `.class` cũng có thể ở classpath

Một JAR hoặc thư mục classpath có thể chứa file cấu hình/resource. Ví dụ nếu có resource `config/message.txt` dưới gốc `out/lib` hoặc trong JAR dưới entry `config/message.txt`, mã dùng class loader có thể đọc bằng tên resource tương ứng:

~~~java
try (var in = Main.class.getClassLoader().getResourceAsStream("config/message.txt")) {
    if (in == null) {
        throw new IllegalStateException("Khong tim thay resource");
    }
    // Đọc InputStream theo encoding và định dạng phù hợp.
}
~~~

Đây là **đoạn mã minh họa đặt bên trong phương thức cho phép ném/ xử lý exception**; chưa phải một chương trình độc lập và không dùng trong lệnh `Main` của thí nghiệm. Nó cho thấy classpath không chỉ phục vụ lớp. Khi chạy thật, resource cũng cần được đưa vào output folder/JAR; việc resource tồn tại trong `src` không có nghĩa nó tự xuất hiện trong artifact đã biên dịch.

JAR đóng gói các file resource theo đúng đường dẫn entry. Không nên xây đường dẫn filesystem tới một resource bên trong JAR rồi giả định nó luôn là file vật lý riêng lẻ.

## 9. Mối liên hệ với Gradle/Maven và JPMS

Trong dự án lớn, hiếm khi viết tay classpath. Maven/Gradle xác định dependency, tải artifact nếu cần, và cung cấp đường dẫn classpath phù hợp cho từng nhiệm vụ.

- **Compile classpath** chứa các kiểu/API cần để biên dịch mã nguồn.
- **Runtime classpath** chứa các lớp/resource cần khi khởi động và chạy ứng dụng.
- Các cấu hình dependency như `implementation`, `compileOnly`, `runtimeOnly` (trong Gradle Java plugin) có ý nghĩa khác nhau đối với những tập đường dẫn này. Đừng suy rằng mọi dependency có tại compile-time đều sẽ có ở runtime.

Ví dụ tình huống: một thư viện đánh dấu `compileOnly` cho phép code biên dịch với API đó, nhưng bản phân phối phải được cấu hình để API có mặt bằng cách khác lúc chạy nếu code thực sự cần tới nó.

Từ Java 9, **Java Platform Module System (JPMS)** đưa thêm khái niệm **module path**. Ví dụ học này dùng **classpath truyền thống (unnamed module)** nên các lệnh `-cp` là phù hợp. Với một **named module** có `module-info.java`, việc tìm dependency có thể cần `--module-path` và `requires` tương ứng. Classpath và module path không phải hai tên gọi tùy ý cho cùng một cơ chế.

### JAR được truyền cho `java -jar` thì sao?

Trong lệnh `java -jar app.jar`, JVM khởi động ứng dụng theo thông tin main class trong manifest của JAR; **classpath ứng dụng từ `-cp` không được áp dụng theo cách như khi khởi chạy bằng tên lớp**. Dependency bên ngoài có thể được khai báo qua manifest `Class-Path` hoặc giải quyết bằng cơ chế launcher/packaging phù hợp.

Vì vậy, việc ví dụ này chạy được với:

~~~sh
java -cp "out/app:lib/math-utils.jar" demo.app.Main
~~~

không có nghĩa bạn có thể đổi tùy tiện thành `java -jar lib/math-utils.jar`. JAR đó là **thư viện**, không chứa lớp main của ứng dụng.

## 10. Khi gặp lỗi, kiểm tra có phương pháp

Nếu build hoặc chạy thất bại, hãy thực hiện kiểm tra theo đúng giai đoạn:

**A. Khi `javac` báo không tìm thấy package hoặc lớp:**

1. Xem chính xác tên package và chữ hoa/chữ thường của lớp.
2. Kiểm tra tệp `.class` đã tồn tại trong thư mục đúng (ví dụ `out/lib/demo/tools/NumberUtils.class`) hay đã nằm trong JAR.
3. Đối chiếu classpath root: truyền `out/lib` hoặc `lib/math-utils.jar`, không truyền thư mục package quá sâu.
4. Xác định bạn đang chạy `javac` từ thư mục nào: mọi đường dẫn tương đối được giải theo thư mục làm việc của process.
5. Nếu dùng công cụ build, kiểm tra dependency được khai báo cho đúng source set/cấu hình biên dịch.

**B. Khi `java` không tìm được main class:**

1. Kiểm tra `out/app/demo/app/Main.class` có tồn tại.
2. Dùng tên `demo.app.Main` chứ không dùng đường dẫn tới `.class`.
3. Đưa **root `out/app`** vào runtime classpath.
4. Kiểm tra đúng class có phương thức `public static void main(String[] args)` trong ví dụ này.

**C. Khi tìm được main nhưng báo thiếu phụ thuộc:**

1. Đảm bảo `out/lib` hoặc `lib/math-utils.jar` có trong **runtime classpath**, không chỉ compile classpath.
2. Nếu truyền JAR, dùng `jar --list --file ...` để xác minh entry và tên package.
3. Kiểm tra các dependency mà chính JAR thư viện cần; một JAR thường không tự đóng gói tất cả JAR nó phụ thuộc.
4. So sánh version của JAR lúc biên dịch và lúc chạy; sai khác có thể gây lỗi liên kết hoặc thay đổi hành vi.

**D. Khi lớp đúng nhưng ứng dụng vẫn trả kết quả sai:**

Classpath chỉ quyết định nơi tìm định nghĩa lớp/resource; nó **không xác nhận thuật toán đúng**. Khi đã nạp đúng lớp, hãy kiểm thử logic, dữ liệu đầu vào và cấu hình runtime.

Một cách đơn giản để tránh nhầm file cũ trong thí nghiệm là dọn riêng các thư mục đầu ra của chính bài này rồi biên dịch tuần tự theo đúng lệnh. Khi làm việc trong repo có dữ liệu người khác, chỉ xóa artifact do bạn tạo và có quyền quản lý.

## 11. Thực hành củng cố

**Bài 1 — Class directory.** Dùng hai tệp nguồn trong bài, biên dịch thư viện vào `out/lib` và ứng dụng vào `out/app`. Chạy với hai root và xác nhận stdout `Kết quả: 14`. Thử bỏ `out/lib` khỏi runtime classpath; ghi nhận lỗi và giải thích tại sao biên dịch đã thành công.

**Bài 2 — JAR.** Tạo `lib/math-utils.jar`, xác minh entry `demo/tools/NumberUtils.class` bằng `jar --list`. Biên dịch lại ứng dụng bằng `-cp lib/math-utils.jar` và chạy với JAR trên classpath. Giải thích tại sao kết quả không đổi.

**Bài 3 — Sai root.** Thay `-cp out/lib` bằng `-cp out/lib/demo/tools` trong lệnh biên dịch ứng dụng và dự đoán lỗi. Chỉ ra đường dẫn mà `javac` muốn tìm theo package và classpath root đã chọn.

**Bài 4 — Nhiều dependency.** Thêm một JAR phụ mới trực tiếp vào `lib`. So sánh việc liệt kê hai JAR riêng với `lib/*`. Giải thích vì sao wildcard không bảo đảm thứ tự khi hai JAR chứa cùng một lớp.

**Bài 5 — Kiểm chứng môi trường.** Viết hai lệnh `java -cp` tương đương cho Unix và Windows khi có ba root là `out/app`, `out/lib` và `lib/math-utils.jar`. Chỉ rõ ký tự phân tách.

**Bài 6 — Phân biệt compile và runtime.** Giả sử build qua nhưng `java` báo `NoClassDefFoundError` cho `NumberUtils`. Xác định ba vị trí đầu tiên cần kiểm tra và đề xuất lệnh chạy đúng với cây thư mục hiện tại.

### Câu hỏi tự đánh giá

1. **Classpath root của `demo.tools.NumberUtils` trong `out/lib/demo/tools/NumberUtils.class` là đâu?** — `out/lib`.
2. **Tại sao JAR có thể làm dependency dù không có `Main-Class`?** — Nó chỉ cần cung cấp lớp/resource cho chương trình khác; không phải ứng dụng tự chạy.
3. **`import` có làm Maven/Gradle tải thư viện không?** — Không; dependency do cấu hình build và công cụ quản lý.
4. **Vì sao cần dependency ở runtime dù đã có ở compile-time?** — `javac` kiểm tra/biên dịch bằng thư viện, nhưng JVM phải nạp được lớp thật khi thực thi.
5. **Trên Windows dùng dấu gì để tách các mục classpath?** — `;`; Unix/Linux/macOS dùng `:`.
6. **`lib` và `lib/*` khác nhau thế nào?** — Một bên là thư mục root để tìm class/resource rời; bên kia mở rộng các JAR trực tiếp trong thư mục.
7. **Classpath và module path có giống nhau không?** — Không; named modules dùng cơ chế/module descriptor riêng của JPMS.

**Kết nối kiến thức:** Khi hiểu thư mục class, JAR và classpath root, bạn có thể phân tích rõ ba lỗi khác nhau: **không biên dịch được vì thiếu dependency**, **biên dịch được nhưng JVM không nạp được lớp**, và **nạp được lớp nhưng runtime dùng một phiên bản thư viện khác**. Đây là nền tảng để làm việc với thư viện Java, dependency management và quá trình đóng gói/triển khai.