# Thiết lập `-cp`, `--class-path` và biến `CLASSPATH` trong Java

## 1. Classpath là gì, dùng để làm gì?

**Classpath** (*đường dẫn tìm kiếm lớp*) là danh sách các vị trí mà công cụ Java sử dụng để tìm **class của ứng dụng và thư viện trên classpath**, thông thường gồm thư mục chứa các tệp `.class`, tệp `.jar` hoặc `.zip`. Đây không phải đường dẫn tới Java source tùy ý, cũng không phải toàn bộ nơi JVM có thể tìm mọi lớp: JVM còn có các loader nền tảng, module path và các custom class loader khác.

Trong cách khởi chạy một chương trình Java cổ điển:

~~~text
                 java launcher
                       |
            Chọn effective classpath
                       |
           +-----------+------------+
           |                        |
   Thư mục class gốc          JAR/ZIP chứa class
   out/classes/               lib/feature.jar
           |                        |
           +-----------+------------+
                       |
          Application/System ClassLoader
                       |
              tìm class theo tên
              demo.Main -> demo/Main.class
~~~

Ví dụ chương trình cần lớp `demo.Main` và `util.Helper`. Nếu class files nằm ở:

~~~text
project/
├── out/
│   ├── app/demo/Main.class
│   └── lib/util/Helper.class
└── lib/helper.jar
~~~

thì đường dẫn classpath có thể chứa **`out/app` và `out/lib`**. Tên lớp `demo.Main` được ánh xạ tương đối thành `demo/Main.class`. Nếu chỉ thêm đường dẫn `out/app/demo`, JVM sẽ tìm sai vị trí cho tên `demo.Main`; **classpath entry phải là gốc của cây package**.

Đối với JAR, entry ngay trong kho lưu trữ cũng phải có đường dẫn package tương ứng, ví dụ `util/Helper.class`. Truyền trực tiếp đường dẫn tới một tệp `.class` cụ thể không phải cách thiết lập classpath chuẩn cho class có package.

## 2. Ba tùy chọn `-cp`, `-classpath`, `--class-path`

Với **`java` launcher** và **`javac` compiler**, ba cách viết sau là các tên tùy chọn tương đương để chỉ định classpath của user:

~~~bash
java -cp out/classes demo.Main
java -classpath out/classes demo.Main
java --class-path out/classes demo.Main
~~~

Dùng một trong ba cách là đủ. Cú pháp tổng quát:

~~~text
java [JVM options] -cp <classpath> <fully.qualified.MainClass> [app arguments]
javac -cp <classpath> -d <output-directory> <source-files>
~~~

Các dấu ngoặc nhọn/ngoặc nhọn góc trong sơ đồ trên là **ký hiệu mô tả**, không nhập nguyên văn. `-cp` là tùy chọn của trình chạy hoặc trình biên dịch, cần đặt trước tên lớp chính khi chạy class mode. Nếu đặt ở **sau** `demo.Main`, nó sẽ thành đối số `String[] args` của ứng dụng thay vì cấu hình cho launcher.

| Tùy chọn | Công cụ | Ý nghĩa |
| --- | --- | --- |
| `-cp path` | `java`, `javac` | Viết ngắn; tiện dùng trong terminal/script. |
| `-classpath path` | `java`, `javac` | Tên dài tương đương với `-cp`. |
| `--class-path path` | `java`, `javac` | Dạng tùy chọn dài; dễ đọc trong script. |
| `-d output` | `javac` | Nơi **ghi file `.class` đầu ra**; **không tự** thêm vị trí này vào runtime classpath. |

Hãy phân biệt **classpath để biên dịch** với **classpath lúc chạy**:

- `javac -cp ...`: compiler dùng các thư mục/JAR để kiểm tra và resolve kiểu khi biên dịch.
- `java -cp ...`: JVM dùng các nguồn tại runtime để tìm class chính và các dependency do system/application loader cần.
- Hai danh sách này thường liên quan nhưng **không tự đồng bộ**. Biên dịch thành công không có nghĩa runtime tìm đủ JAR.
- Khi đã tự chỉ định classpath, phải đưa thư mục chứa class đầu ra và dependency cần thiết vào danh sách một cách rõ ràng.

## 3. Ghép nhiều đường dẫn: dấu phân cách theo hệ điều hành

Một classpath là **một giá trị** có thể chứa nhiều phần tử. Ký tự ngăn cách do **hệ điều hành** quy định:

| Hệ điều hành | Path separator | Ví dụ |
| --- | --- | --- |
| Windows (PowerShell hoặc cmd) | `;` | `out\app;out\lib;lib\helper.jar` |
| Linux/macOS | `:` | `out/app:out/lib:lib/helper.jar` |

Ví dụ chạy trên Windows PowerShell:

~~~powershell
java -cp "out\app;out\lib" demo.Main
java --class-path "out\app;lib\helper.jar" demo.Main
~~~

Ví dụ tương ứng trên Linux/macOS:

~~~bash
java -cp "out/app:out/lib" demo.Main
java --class-path "out/app:lib/helper.jar" demo.Main
~~~

**Nên đặt toàn bộ classpath trong dấu nháy** khi có khoảng trắng hoặc ký tự mà shell có thể xử lý riêng. Đặc biệt trên PowerShell, dấu `;` ngoài chuỗi được dùng để ngăn các lệnh, nên chuỗi classpath có nhiều phần tử phải được trích dẫn.

Đường dẫn tương đối được giải quyết từ **thư mục làm việc hiện tại** của tiến trình, không tự động từ thư mục chứa `Main.class` hay một source `.java`. Đổi working directory có thể làm cùng một lệnh đột nhiên không tìm thấy lớp.

**Không sử dụng dấu `:` để nối path trên Windows** (vì còn xuất hiện ở ký tự ổ đĩa như `C:`), và cũng đừng bê nguyên dấu `;` từ Windows sang shell Unix.

## 4. Biến môi trường `CLASSPATH` được áp dụng khi nào?

`CLASSPATH` là **biến môi trường** mà Java launcher và compiler có thể đọc để lấy user classpath **khi không có tùy chọn classpath tường minh**.

Quy tắc ưu tiên thực tế cho class mode cổ điển:

~~~text
Có -cp / -classpath / --class-path tường minh?
             |
       +-----+------+
       |            |
      Có           Không
       |            |
       v            v
Dùng giá trị    CLASSPATH có được đặt?
ở command           |
line             +---+---+
                 |       |
                Có      Không
                 |       |
                 v       v
           Dùng CLASSPATH  Dùng "."
~~~

Nếu `-cp` hiện diện, nó **ghi đè giá trị effective user classpath từ biến `CLASSPATH`** trong lệnh đó; hai giá trị không được tự nối với nhau. Nếu cả tùy chọn và biến không được đặt, classpath người dùng mặc định là **thư mục hiện tại `.`**.

Ví dụ:

~~~text
CLASSPATH=out/app:out/lib
java -cp out/other demo.Main
~~~

Lời gọi cuối sẽ **không** tự thêm `out/app:out/lib` vào `out/other`. Nếu cần chúng, hãy liệt kê đủ trong giá trị `-cp`. Cũng lưu ý classpath tường minh **không tự thêm `.`**, nên nếu cần current directory thì viết nó ra:

~~~bash
java -cp ".:lib/helper.jar" demo.Main       # Linux/macOS
~~~

Trên Windows là `java -cp ".;lib\helper.jar" demo.Main`.

### Thiết lập trong Windows PowerShell

~~~powershell
$env:CLASSPATH = "out\app;out\lib"
java demo.Main
~~~

Thiết lập này áp dụng cho **phiên PowerShell hiện tại** và các process được nó khởi tạo. Muốn bỏ biến trong phiên hiện tại:

~~~powershell
Remove-Item Env:CLASSPATH
~~~

Nếu chỉ muốn xem giá trị đang áp dụng:

~~~powershell
$env:CLASSPATH
~~~

Trong Command Prompt (`cmd.exe`) tương ứng:

~~~bat
set CLASSPATH=out\app;out\lib
java demo.Main
set CLASSPATH=
~~~

### Thiết lập trong Bash/zsh trên Linux hoặc macOS

~~~bash
export CLASSPATH="out/app:out/lib"
java demo.Main
unset CLASSPATH
~~~

Biến chỉ ảnh hưởng các process Java được khởi chạy từ môi trường đó. Thay đổi `CLASSPATH` sau khi JVM đã bắt đầu **không tự cập nhật** classpath của JVM đang chạy.

**Khuyến nghị:** ưu tiên `-cp` hoặc `--class-path` tường minh trong command, task build, hoặc script của dự án. Một biến `CLASSPATH` toàn cục thường gây lỗi khó tái hiện khi nhiều dự án cần thư viện khác nhau. Tài liệu `javac` của Oracle cũng khuyến nghị không cần đặt biến này khi có thể truyền tùy chọn rõ ràng.

## 5. Ví dụ Java 17+ hoàn chỉnh: compile classpath và runtime classpath

Bài thực hành gồm **hai class ở hai package khác nhau**. Không cần framework hay dependency ngoài JDK.

Tạo cấu trúc nguồn:

~~~text
example/
└── src/
    ├── util/
    │   └── Helper.java
    └── demo/
        └── Main.java
~~~

### `src/util/Helper.java`

~~~java
package util;

public class Helper {
    public static String message() {
        return "Hello from helper";
    }
}
~~~

### `src/demo/Main.java`

~~~java
package demo;

import util.Helper;

public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

**Lưu ý:** hai đoạn trên là **hai tệp source độc lập**, phải tạo ở đúng đường dẫn và package tương ứng.

### Chạy trên Windows PowerShell

Đứng trong thư mục `example`:

~~~powershell
New-Item -ItemType Directory -Force out\lib, out\app | Out-Null

javac -d out\lib src\util\Helper.java
javac -cp out\lib -d out\app src\demo\Main.java

java -cp "out\app;out\lib" demo.Main
java --class-path "out\app;out\lib" demo.Main
~~~

Cả hai lệnh `java` đều in:

~~~text
Hello from helper
~~~

Giải thích:

1. Lệnh `javac -d out\lib src\util\Helper.java` tạo `out/lib/util/Helper.class`.
2. Lệnh biên dịch `Main` phải dùng `-cp out\lib` để compiler tìm được kiểu `util.Helper`. Đồng thời `-d out\app` đưa class chính vào `out/app/demo/Main.class`.
3. Khi chạy, `java` phải thấy **cả** `out\app` (nơi có `demo.Main`) và `out\lib` (nơi có `util.Helper`).
4. Tên lớp chính là **`demo.Main`**, không phải `Main` và không phải `out\app\demo\Main.class`.

Thử cách dùng biến môi trường trong PowerShell:

~~~powershell
$env:CLASSPATH = "out\app;out\lib"
java demo.Main
Remove-Item Env:CLASSPATH
~~~

Kết quả vẫn là:

~~~text
Hello from helper
~~~

Nếu muốn dùng `CLASSPATH` để biên dịch, biến cũng có thể làm classpath mặc định của `javac`; nhưng ví dụ cố ý dùng `-cp` lúc compile để tránh phụ thuộc trạng thái máy.

### Chạy trên Linux/macOS

Đứng trong thư mục `example` có hai file source đã tạo:

~~~bash
mkdir -p out/lib out/app

javac -d out/lib src/util/Helper.java
javac -cp out/lib -d out/app src/demo/Main.java

java -cp "out/app:out/lib" demo.Main
java --class-path "out/app:out/lib" demo.Main
~~~

Kết quả của mỗi lệnh chạy là:

~~~text
Hello from helper
~~~

Phiên shell dùng biến môi trường:

~~~bash
export CLASSPATH="out/app:out/lib"
java demo.Main
unset CLASSPATH
~~~

Kết quả:

~~~text
Hello from helper
~~~

**Đã kiểm chứng:** mã Java trên biên dịch và chạy được bằng JDK hiện đại trên Windows với cả `-cp`, `--class-path` và `CLASSPATH`. Dạng Linux/macOS chỉ thay dấu phân cách và dấu gạch đường dẫn theo cú pháp hệ điều hành.

## 6. Dùng file JAR và wildcard `lib/*`

Một classpath entry có thể là một **JAR** cụ thể:

~~~powershell
java -cp "out\app;lib\helper.jar" demo.Main  # Windows
~~~

~~~bash
java -cp "out/app:lib/helper.jar" demo.Main   # Linux/macOS
~~~

Để thử chính ví dụ phần 5, trước hết đóng gói class `util.Helper` đã biên dịch:

~~~powershell
New-Item -ItemType Directory -Force lib | Out-Null
jar --create --file lib\helper.jar -C out\lib .
java -cp "out\app;lib\helper.jar" demo.Main
~~~

Lệnh trên chạy trên Windows PowerShell và in `Hello from helper`. Tương ứng Linux/macOS:

~~~bash
mkdir -p lib
jar --create --file lib/helper.jar -C out/lib .
java -cp "out/app:lib/helper.jar" demo.Main
~~~

**Nếu có nhiều JAR trong cùng thư mục**, Java launcher hỗ trợ phần tử wildcard có **basename đúng bằng dấu `*`**:

~~~powershell
java -cp "out\app;lib\*" demo.Main   # Windows
~~~

~~~bash
java -cp "out/app:lib/*" demo.Main    # Linux/macOS
~~~

Các điểm cần hiểu chính xác về wildcard:

- `lib/*` mở rộng thành **các JAR có đuôi `.jar` hoặc `.JAR` nằm trực tiếp trong `lib`**, không tìm JAR ở thư mục con một cách đệ quy.
- `lib/*` **không tự thêm** thư mục `lib` làm classpath entry cho các tệp `.class` rời. Nếu có `lib/com/example/X.class`, phải thêm chính thư mục `lib`.
- Thứ tự các JAR khi mở rộng wildcard **không được bảo đảm**. Nếu nhiều JAR chứa lớp cùng binary name, hành vi có thể phụ thuộc thứ tự dò thực tế và dẫn đến lỗi phiên bản.
- Không dùng wildcard như một phép tìm file bất kỳ `lib/special-*.jar`; hãy chỉ định tên JAR cụ thể hoặc dùng `lib/*` theo quy tắc của Java.
- Đặt `lib/*` trong dấu nháy để **shell không tự mở rộng** wildcard theo quy tắc của nó trước khi Java launcher xử lý.

Tương tự, có thể sử dụng wildcard trong giá trị `CLASSPATH`, nhưng vẫn cần chú ý dấu phân cách và không nên để một thư viện phụ thuộc vào thứ tự không xác định.

## 7. Thứ tự phần tử trong classpath có ý nghĩa gì?

Thông thường application loader tìm các nguồn theo một thứ tự xác định bởi classpath hiệu lực (đồng thời tuân theo chính sách ủy quyền tới loader cha). Nếu hai JAR cùng chứa `com/example/Util.class`, class được định nghĩa có thể đến từ JAR được xét trước; các phiên bản cùng tên nhưng bytecode khác nhau là nguyên nhân phổ biến của lỗi linkage như `NoSuchMethodError`.

Ví dụ:

~~~bash
java -cp "app:lib/api-v1.jar:lib/api-v2.jar" demo.Main
~~~

Không nên dùng việc đặt nhiều bản một thư viện trên classpath làm cơ chế chọn phiên bản. Hãy bảo đảm danh sách dependency và phiên bản nhất quán, đặc biệt khi dùng `lib/*` vì thứ tự mở rộng JAR không được bảo đảm.

Tuy nhiên, **thứ tự classpath không vượt qua mọi chính sách class loader**: parent-first có thể ưu tiên một lớp đã được định nghĩa ở loader cha; custom loader có thể dùng chiến lược khác. Classpath chủ yếu mô tả **nguồn tìm kiếm** cho loader/công cụ liên quan, không thay đổi danh tính kiểu đã được định nghĩa bởi loader khác.

## 8. `java -jar` không dùng classpath theo cách class mode

Đây là trường hợp nhiều người gặp lỗi:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

Khi dùng **`java -jar app.jar`**, Java launcher chọn JAR thực thi có `Main-Class` trong `META-INF/MANIFEST.MF`. Theo tài liệu launcher, các thiết lập classpath thông thường như `-cp`/biến `CLASSPATH` **không được áp dụng làm user classpath của JAR mode**. Vì vậy đừng kỳ vọng ví dụ trên thêm mọi JAR ở `lib/*` cho ứng dụng `-jar`.

Muốn chạy với classpath rõ ràng và biết tên lớp chứa `main`, dùng **class mode**:

~~~powershell
java -cp "app.jar;lib\*" com.example.Main  # Windows
~~~

~~~bash
java -cp "app.jar:lib/*" com.example.Main   # Linux/macOS
~~~

Trong trường hợp thật, cần thay `com.example.Main` bằng binary name đúng của lớp chứa `public static void main(String[] args)`.

Một **executable JAR** còn có thể khai báo thuộc tính `Class-Path` trong manifest để tham chiếu tới JAR phụ thuộc (thường là các URL tương đối tới vị trí JAR), theo quy tắc manifest của JAR. Cơ chế đó khác với việc truyền `-cp` để thêm thư viện cho `-jar`.

Các JAR của framework có launcher riêng hoặc nested JAR loader (ví dụ JAR đóng gói theo kiểu framework) có thể thêm cơ chế tìm phụ thuộc không trùng với classpath truyền thống; cần đọc hợp đồng của launcher đó, tránh suy luận chỉ từ tên tệp `.jar`.

## 9. Classpath khác với module path và custom loader

Từ Java 9, Java có **Java Platform Module System**:

| Khái niệm | Dùng cho | Thiết lập ví dụ |
| --- | --- | --- |
| Classpath | Class/JAR chạy ở chế độ classpath, thuộc **unnamed module** của loader tương ứng. | `java -cp "out:lib/*" demo.Main` |
| Module path | Đường tìm **named modules** được resolve theo module system. | `java --module-path mods --module example.module/com.example.Main` |
| Custom loader URLs | Nguồn riêng của một loader do ứng dụng tạo. | `new URLClassLoader(urls, parent)` |

Lớp chỉ đặt trên **module path** không mặc nhiên trở thành class trên classpath, và ngược lại. Một class trong JAR do custom `URLClassLoader` đọc không nhất thiết xuất hiện trên `java.class.path`. Tương tự, những lớp được bootstrap/platform loader nạp không phải vì bạn đã liệt kê mọi module JDK trong `-cp`.

Nếu học về parent delegation: `-cp`/ `CLASSPATH` chủ yếu ảnh hưởng nguồn tìm của **system/application loader** khi khởi chạy class mode. Không nên coi đó là lệnh yêu cầu loader cha quét nguồn phụ thuộc của mọi loader con.

## 10. Phân biệt classpath với các đường dẫn Java khác

Những tùy chọn dễ bị nhầm:

- **`-d output` của `javac`**: nơi lưu kết quả compile, không phải classpath lúc chạy.
- **`--source-path` của `javac`**: nơi compiler có thể tìm source files khi cần, khác nơi tìm compiled classes/JAR.
- **`--module-path` / `-p`**: nơi tìm named modules, khác `--class-path`.
- **`PATH` của hệ điều hành**: nơi shell tìm chương trình thực thi `java` hoặc `javac`; không cho JVM biết `demo.Main` nằm ở đâu.
- **`JAVA_HOME`**: thường trỏ tới cài đặt JDK, không phải classpath.
- **`CLASSPATH`**: biến môi trường tùy chọn làm mặc định cho công cụ Java khi không được override; không quyết định JVM chọn JDK nào.
- **`java.library.path`**: liên quan tìm native libraries (JNI), khác đường tìm tệp `.class`.

Nếu gõ `java -version` thành công nhưng `java demo.Main` báo không thấy main class, `PATH` đã có thể ổn trong khi classpath hoặc tên lớp chính vẫn sai.

## 11. Kiểm tra runtime và xử lý lỗi thường gặp

### 11.1. Kiểm tra classpath đang dùng

Trong chương trình:

~~~java
System.out.println(System.getProperty("java.class.path"));
~~~

Đây là **một dòng minh họa**, có thể đặt trong phương thức `main` để xem đường tìm kiếm classpath do launcher khai báo. Kết quả hữu ích khi debug, nhưng **không đại diện toàn bộ** nguồn từ bootstrap/platform/module path hoặc custom loaders. Đặc biệt, đừng dùng nó để kết luận một plugin do loader riêng nạp đã nằm trên system classpath.

Trên terminal, có thể dùng thêm:

~~~bash
java -XshowSettings:properties -version
~~~

Tìm thuộc tính `java.class.path` trong phần property settings. Ngoài ra `java -verbose:class ...` hoặc tùy chọn log class loading thích hợp giúp quan sát nguồn lớp được nạp, nhưng output nhiều và không nên dùng như cách dự đoán mọi đường tìm class tiềm năng.

### 11.2. Lỗi sai classpath phổ biến

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Error: Could not find or load main class demo.Main` | Thiếu thư mục gốc chứa `demo/Main.class`, sai package hoặc sai tên lớp chính. | Xem cây file, dùng `-cp out/app demo.Main`, kiểm tra `package demo;`. |
| `ClassNotFoundException` | Mã hoặc loader không tìm được lớp có binary name được yêu cầu. | Kiểm tra nguồn của **loader đang tìm**, classpath/module path, tên binary name. |
| `NoClassDefFoundError` khi đang chạy | Dependency không còn thấy ở runtime dù compile thành công; cũng có thể do khởi tạo lớp trước đó thất bại. | Kiểm tra classpath runtime, cause/stack trace và lệnh thực thi thực tế. |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Runtime chọn phiên bản thư viện không tương thích với lúc biên dịch. | Kiểm tra trùng JAR, phiên bản và thứ tự classpath. |
| Command chạy ở thư mục A được, sang B thì lỗi | Dùng đường dẫn tương đối từ working directory. | Dùng absolute path hoặc nhất quán `cd` tới project root. |
| Chạy `-cp lib/*` mà class chính không thấy | Wildcard chỉ chọn JAR, không thêm `out/app` hoặc thư mục `.class` rời. | Thêm gốc class chính rõ ràng vào chuỗi classpath. |
| Đặt `CLASSPATH` rồi chạy `-cp ...` mà biến dường như bị bỏ qua | Tùy chọn CLI override biến môi trường. | Dùng một cấu hình classpath tường minh chứa đủ phần tử. |
| `java -cp ... -jar app.jar` vẫn thiếu dependency | JAR mode không lấy user classpath từ `-cp`. | Dùng manifest `Class-Path`, launcher của app hoặc chạy class mode. |
| Windows lỗi khi copy command Linux | Sai dấu phân cách `:` thay vì `;`, hoặc thiếu quote trong PowerShell. | Dùng `;` và bọc toàn chuỗi bằng dấu nháy trên Windows. |

### 11.3. Checklist tự kiểm tra

1. **Có chạy class mode hay `-jar` mode?** Nếu là `-jar`, xem manifest và cơ chế đóng gói JAR.
2. **Đã thêm thư mục gốc của package?** Ví dụ `demo.Main` đòi `<root>/demo/Main.class`.
3. **Compile classpath và runtime classpath có khớp nhu cầu?** Runtime phải tìm được thư viện thật sự được tham chiếu.
4. **Có một `-cp` / `--class-path` tường minh?** Nếu có, đừng trông chờ `CLASSPATH` tự nối vào.
5. **Có vô tình bỏ quên `.`?** Khi classpath chỉ định rõ, current directory không tự xuất hiện nếu bạn không thêm.
6. **Separator hợp OS và shell chưa?** Windows `;`, Linux/macOS `:`, thường quote toàn bộ chuỗi.
7. **Có JAR trùng class/phiên bản?** Tránh dựa vào thứ tự wildcard không xác định.
8. **Có custom loader/module path không?** Lớp ở nguồn khác không nhất thiết nằm trong user classpath.
9. **Đang dùng build tool?** Maven/Gradle/IDE thường tự sinh runtime classpath; cần kiểm tra lệnh Java thực mà chúng khởi chạy thay vì đoán bằng biến máy.

## 12. Câu hỏi ôn tập

**Câu 1:** Trên Windows, `CLASSPATH=out\app;out\lib` đã đặt, nhưng chạy `java -cp out\app demo.Main` gặp `NoClassDefFoundError` đối với `util.Helper`. Vì sao?

**Đáp:** `-cp out\app` override `CLASSPATH`, nên system classpath không có `out\lib`. Sửa thành `java -cp "out\app;out\lib" demo.Main`.

**Câu 2:** Dùng `-cp lib/*` có tự tìm mọi JAR con trong `lib/a/` và mọi `.class` rời dưới `lib` không?

**Đáp:** Không. Wildcard chỉ mở rộng các JAR trực tiếp trong `lib`, không đệ quy; muốn tìm class rời phải thêm chính thư mục gốc class.

**Câu 3:** Vì sao `javac -cp lib/helper.jar` thành công mà `java -cp out/app demo.Main` lại lỗi?

**Đáp:** Compiler có JAR lúc biên dịch nhưng JVM không có cùng dependency ở runtime. Thêm JAR vào runtime classpath.

**Câu 4:** `java -jar app.jar` và `java -cp "app.jar:lib/*" com.example.Main` có tương đương không?

**Đáp:** Không. JAR mode dùng manifest/main-class của JAR và cách giải dependency riêng; class mode chọn tên lớp chính cùng classpath tường minh.

## Tài liệu chính thức

- [Java SE 21 – Lệnh `java`, tùy chọn `--class-path`, wildcard và `-jar`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 – Lệnh `javac`, `-cp`, biến `CLASSPATH` và `-d`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 – `ClassLoader` và parent delegation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
