# Phân biệt phụ thuộc lúc biên dịch với phụ thuộc lúc chạy trong Java

Khi biên dịch ứng dụng Java, `javac` cần tìm được các **kiểu, phương thức và trường** mà mã nguồn tham chiếu; khi chạy, JVM cần tìm được **các lớp và tài nguyên thực sự được sử dụng**. Hai tập nhu cầu này liên quan chặt chẽ nhưng không giống nhau. Vì vậy, một chương trình có thể biên dịch thành công rồi lỗi `NoClassDefFoundError` khi chạy; ngược lại, một plugin được nạp bằng reflection có thể không cần xuất hiện trên compile classpath của ứng dụng nhưng lại bắt buộc hiện diện lúc nạp plugin.

Trong nhóm kiến thức **Classpath** của Java Advance – compilation, bài này giải thích ranh giới giữa compile-time dependency và runtime dependency, cách `javac` và `java` tìm lớp, các trường hợp phụ thuộc trực tiếp/gián tiếp, binary compatibility, dynamic loading và cách tổ chức dependency trong dự án thực tế. Ví dụ được viết cho **Java 17 trở lên**, có lệnh thực hành và kết quả đã kiểm chứng.

## 1. Hai giai đoạn, hai câu hỏi khác nhau

**Phụ thuộc lúc biên dịch (compile-time dependency)** là thành phần mà trình biên dịch cần để xác định các tên kiểu, chữ ký phương thức, ràng buộc truy cập, generics, annotation hoặc các yêu cầu biên dịch khác. Trong ứng dụng đơn giản, đó thường là một thư mục chứa `.class` hoặc một JAR trên classpath của `javac`.

**Phụ thuộc lúc chạy (runtime dependency)** là thành phần mà JVM, class loader hoặc cơ chế chạy ứng dụng cần để nạp/link/khởi tạo các lớp, gọi phương thức, truy cập tài nguyên hoặc thực hiện các chức năng thực tế. Một thành phần có thể cần khi chạy nhưng không cần trực tiếp để biên dịch nguồn ứng dụng.

| Câu hỏi | Biên dịch bằng javac | Chạy bằng java/JVM |
|---|---|---|
| Đầu vào chính | Các tệp `.java` cùng các khai báo kiểu/API liên quan | Bytecode `.class`, JAR, tài nguyên và cấu hình chạy |
| Nhiệm vụ | Phân giải tên, kiểm tra kiểu, chọn chữ ký, tạo bytecode | Nạp lớp, liên kết, khởi tạo, thực thi bytecode |
| Đường dẫn thường dùng | `javac -cp ...`, `-sourcepath ...`, `--module-path ...` | `java -cp ...`, `--module-path ...`, module/class loader |
| Khi thiếu thành phần | `package ... does not exist`, `cannot find symbol` hoặc lỗi biên dịch khác | `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, lỗi tài nguyên hoặc lỗi khởi tạo |
| Khi nào phát hiện? | Trước khi chạy chương trình | Khi JVM hoặc logic ứng dụng thực sự cần thành phần tương ứng |

Cách hình dung cho trường hợp dùng classpath thông thường:

~~~text
Nguồn ứng dụng .java --(javac + compile classpath)--> .class
                                                     |
                                                     v
                                         (java + runtime classpath)
                                                     |
                                                     v
                                              Chương trình chạy
~~~

**Không có quy tắc rằng hai classpath bắt buộc giống hệt nhau.** Điều cần bảo đảm là tập dependency phù hợp với từng giai đoạn, và những bản thư viện mà bytecode sử dụng phải tương thích khi chạy.

### 1.1. Kiểu tham chiếu trực tiếp và phụ thuộc có thể phát sinh gián tiếp

Nếu mã nguồn gọi `Greeter.message("Java")`, `javac` cần biết `Greeter` và chữ ký `message(String)`. Nếu mã chạy đến lệnh gọi đó, JVM cũng cần định vị `Greeter` có phương thức phù hợp. Đây là trường hợp **cần ở cả hai giai đoạn**.

Nếu ứng dụng chỉ dùng `Class.forName("ext.Extension")` với tên lớp là chuỗi, mã không cần tham chiếu trực tiếp tới kiểu `ext.Extension` lúc biên dịch. Nhưng nếu runtime chạy đến lệnh nạp lớp, thành phần chứa `ext.Extension` phải có thể được class loader tương ứng tìm thấy. Đây là ví dụ về **phụ thuộc chỉ phát sinh lúc chạy**.

Nếu compiler dùng một annotation processor để sinh mã khi build, processor có thể chỉ cần xuất hiện trong giai đoạn biên dịch, còn mã ứng dụng đã biên dịch không cần processor lúc chạy. Đây là dạng **build/compile-only tool dependency**, miễn rằng API/lớp khác mà chương trình thực sự dùng được cung cấp phù hợp.

## 2. Cần hiểu đúng classpath là gì

**Classpath** là tập các gốc tìm lớp và tài nguyên trên class path. Một phần tử có thể là thư mục gốc của cây package hoặc tệp JAR. Ví dụ, nếu lớp khai báo:

~~~java
package lib;
public final class Greeter { }
~~~

thì một thư mục classpath `lib-classes` cần chứa `lib-classes/lib/Greeter.class`. Nếu dùng JAR, bên trong JAR phải có entry `lib/Greeter.class`. Đường dẫn classpath **không** trỏ tới thư mục package `lib` bên dưới gốc, và tên kiểu đầy đủ là `lib.Greeter`.

`-classpath`, `-cp` và `--class-path` là các dạng chỉ định classpath. Chúng phải được cung cấp cho đúng tiến trình:

~~~sh
javac -cp artifacts/greeter.jar -d app-classes app-src/app/Main.java
java -cp "<runtime-classpath>" app.Main
~~~

Trong lệnh thứ nhất, `-cp` thuộc **javac** và phục vụ biên dịch. Trong lệnh thứ hai, `-cp` thuộc **java** và phục vụ chạy. Lệnh `javac -d app-classes` chỉ quy định nơi ghi bytecode, **không tự đặt** `app-classes` thành runtime classpath cho lệnh `java` sau đó.

Dấu phân cách giữa **các phần tử** classpath khác nhau theo hệ điều hành:

- Windows: `;` — ví dụ `"app-classes;artifacts/greeter.jar"`.
- Linux/macOS: `:` — ví dụ `"app-classes:artifacts/greeter.jar"`.

Nên đặt chuỗi có dấu phân cách trong dấu nháy. Các ví dụ dưới đây ghi rõ lệnh cho hai môi trường để không nhầm với ký tự `:` trong tên ổ đĩa Windows.

**Classpath không tự tìm mọi JAR trong mọi thư mục con.** Wildcard dạng `libs/*` có thể dùng cho các JAR trực tiếp trong thư mục `libs` theo quy tắc Java launcher/compiler, nhưng không đệ quy qua thư mục con; thứ tự mở rộng các JAR không nên được dùng như một cam kết lựa chọn phiên bản. Việc tự chỉ định từng JAR hoặc để build tool quản lý thường rõ ràng hơn.

## 3. Ví dụ hoàn chỉnh: phụ thuộc cần ở cả compile time và runtime

Hãy tạo cấu trúc sau trong một thư mục `project`:

~~~text
project/
├── lib-src/
│   └── lib/
│       └── Greeter.java
├── app-src/
│   └── app/
│       └── Main.java
├── lib-classes/            # tạo khi thực hành
├── app-classes/            # tạo khi thực hành
└── artifacts/
    └── greeter.jar         # tạo khi thực hành
~~~

### 3.1. Mã thư viện

Tệp `lib-src/lib/Greeter.java`:

~~~java
package lib;

public final class Greeter {
    public static String message(String name) {
        return "Hello, " + name;
    }
}
~~~

Đây là một class công khai có phương thức tĩnh trả về `String`. Tên đầy đủ để tham chiếu là `lib.Greeter`.

### 3.2. Mã ứng dụng

Tệp `app-src/app/Main.java`:

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Before call");
        System.out.println(Greeter.message("Java"));
    }
}
~~~

`Main` có **phụ thuộc tĩnh trực tiếp** vào `lib.Greeter`: mã nguồn có dòng `import` và lời gọi tới phương thức của kiểu đó. `import` chỉ tham gia giải quyết tên; tự nó không tải JAR vào build.

### 3.3. Tạo class của thư viện và đóng gói JAR

Mở terminal tại thư mục `project`. Trên Linux/macOS:

~~~sh
mkdir -p lib-classes app-classes artifacts
javac --release 17 -encoding UTF-8 -d lib-classes lib-src/lib/Greeter.java
jar --create --file artifacts/greeter.jar -C lib-classes .
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path lib-classes, app-classes, artifacts | Out-Null
javac --release 17 -encoding UTF-8 -d lib-classes lib-src/lib/Greeter.java
jar --create --file artifacts/greeter.jar -C lib-classes .
~~~

Công cụ `jar` đi kèm JDK. Tùy chọn `-C lib-classes .` đóng gói nội dung cây lớp theo package, nhờ đó JAR chứa `lib/Greeter.class`. Các lệnh giả định `javac` và `jar` đã có trên PATH và sử dụng JDK hỗ trợ `--release 17`.

### 3.4. Biên dịch ứng dụng với dependency

Lệnh giống nhau trên hai hệ điều hành vì compile classpath chỉ có một phần tử:

~~~sh
javac --release 17 -encoding UTF-8 -cp artifacts/greeter.jar -d app-classes app-src/app/Main.java
~~~

`javac` phải đọc được chữ ký `Greeter.message(String)` trong `artifacts/greeter.jar` để biết lời gọi hợp lệ và trả `String`. Kết quả biên dịch của ứng dụng là `app-classes/app/Main.class`.

### 3.5. Chạy với đúng runtime dependency

Windows PowerShell hoặc cmd:

~~~powershell
java -cp "app-classes;artifacts/greeter.jar" app.Main
~~~

Linux/macOS:

~~~sh
java -cp "app-classes:artifacts/greeter.jar" app.Main
~~~

**Stdout chính xác**:

~~~text
Before call
Hello, Java
~~~

Ở runtime, JVM cần cả `app.Main` và `lib.Greeter`. Việc `javac` vừa dùng `greeter.jar` trước đó không tự chuyển nó vào classpath khi chạy. Hai câu lệnh có cấu hình classpath **độc lập**.

## 4. Thiếu dependency ở lúc biên dịch: compile-time failure

Giữ nguyên các tệp nguồn, nhưng thử biên dịch ứng dụng **không cung cấp Greeter** trên compile classpath/source path:

~~~sh
javac --release 17 -encoding UTF-8 -d app-classes app-src/app/Main.java
~~~

Nếu không có `lib.Greeter` trên đường tìm lớp/nguồn khác của môi trường (ví dụ biến `CLASSPATH` được đặt sẵn), compiler từ chối. Những thông báo tiêu biểu đã kiểm chứng:

~~~text
error: package lib does not exist
error: cannot find symbol
~~~

Compiler không tìm được khai báo kiểu để kiểm tra `Greeter.message("Java")`. **Đây là lỗi compile time**: chương trình chưa có bytecode ứng dụng mới hợp lệ để chạy.

Khắc phục: thêm đường dẫn tới thư viện `-cp artifacts/greeter.jar`, hoặc truyền một bộ nguồn phù hợp cho cùng lượt `javac`, hoặc cấu hình dependency bằng build tool. Việc chỉ thêm JAR vào runtime classpath của `java` **không sửa được** lỗi của `javac` ở lượt biên dịch vừa nêu.

Đừng kết luận classpath thiếu chỉ từ riêng dòng `cannot find symbol`: tên sai, sai package, sai chữ hoa/thường hoặc quyền truy cập cũng có thể là nguyên nhân. Cần đọc đầy đủ tên ký hiệu và nơi compiler tìm kiếm.

## 5. Thiếu dependency lúc chạy: runtime linkage failure

Sau khi đã biên dịch `Main.class` thành công theo phần 3, cố tình **bỏ `greeter.jar` khỏi runtime classpath**, nhưng giữ `app-classes`:

~~~sh
java -cp app-classes app.Main
~~~

Kết quả khi chạy chương trình trên JDK được dùng để kiểm chứng:

~~~text
Before call
Exception in thread "main" java.lang.NoClassDefFoundError: lib/Greeter
~~~

Stack trace thường còn có nguyên nhân dạng:

~~~text
Caused by: java.lang.ClassNotFoundException: lib.Greeter
~~~

**Giải thích chính xác:** `app.Main` đã được nạp và thực thi phần đầu. Khi JVM cần giải quyết tham chiếu đến `lib.Greeter`, class loader không tìm được định nghĩa lớp. `NoClassDefFoundError` là một `LinkageError` tại runtime; có thể có `ClassNotFoundException` nằm ở phần nguyên nhân. Thứ tự thời điểm JVM giải quyết các symbolic reference có phạm vi cho phép theo đặc tả, nên không nên cam kết mọi JVM đều in được một dòng trước khi lỗi trong tất cả cấu trúc chương trình. Ví dụ cụ thể này đã được kiểm chứng in `Before call` rồi lỗi.

Sửa đúng nguyên nhân: chạy với `app-classes` **và** `artifacts/greeter.jar` trên runtime classpath. Chỉ biên dịch lại ứng dụng mà không cung cấp JAR lúc chạy không giải quyết được tình huống thiếu định nghĩa lớp.

### 5.1. ClassNotFoundException khác NoClassDefFoundError thế nào?

- `ClassNotFoundException` là **checked exception**, thường xuất hiện khi code/chương trình gọi API nạp lớp theo tên, ví dụ `Class.forName("ext.Extension")`, và class loader không tìm thấy.
- `NoClassDefFoundError` là một **Error** khi JVM cần định nghĩa một lớp nhưng không có lớp đó theo cách tải/link được yêu cầu; nguyên nhân có thể là lớp thiếu ở runtime, hoặc một lỗi khởi tạo lớp trước đó. Không phải cứ thấy `NoClassDefFoundError` là chắc chắn do quên thêm JAR.
- `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `IncompatibleClassChangeError` có thể cho thấy **bytecode được biên dịch với một API nhưng khi chạy thấy một API/cấu trúc khác**.

Cần xem phần `Caused by` và chữ ký đầy đủ trong stack trace. Lỗi nạp lớp khi khởi tạo có thể phát sinh `ExceptionInInitializerError` ở lần đầu và `NoClassDefFoundError` ở lần sử dụng sau, ngay cả khi tệp `.class` vẫn tồn tại.

## 6. Có JAR lúc chạy nhưng sai phiên bản: binary compatibility

Giả sử ứng dụng ở phần 3 được biên dịch với API:

~~~java
public static String message(String name)
~~~

Nhưng khi chạy, ứng dụng vô tình nhận một JAR khác, trong đó `lib.Greeter` đã đổi thành:

~~~java
public static String message()
~~~

Tên lớp `lib.Greeter` vẫn tồn tại, nhưng **chữ ký phương thức không còn khớp với bytecode gọi cũ**. JVM có thể báo `NoSuchMethodError`.

### 6.1. Thử nghiệm với thư viện v2 không tương thích

Tạo `lib-v2-src/lib/Greeter.java`:

~~~java
package lib;

public final class Greeter {
    public static String message() {
        return "changed API";
    }
}
~~~

Tạo thư mục `lib-v2-classes` rồi biên dịch/đóng JAR khác tên:

~~~sh
javac --release 17 -encoding UTF-8 -d lib-v2-classes lib-v2-src/lib/Greeter.java
jar --create --file artifacts/greeter-v2.jar -C lib-v2-classes .
~~~

Lưu ý `lib-v2-classes` phải được tạo trước khi chạy lệnh; dùng `mkdir -p lib-v2-classes` trên Linux/macOS hoặc `New-Item -ItemType Directory -Force -Path lib-v2-classes` trên PowerShell. **Không biên dịch lại** `app.Main`: ta muốn giữ bytecode đã compile với API v1.

Windows:

~~~powershell
java -cp "app-classes;artifacts/greeter-v2.jar" app.Main
~~~

Linux/macOS:

~~~sh
java -cp "app-classes:artifacts/greeter-v2.jar" app.Main
~~~

Lệnh bị lỗi **`java.lang.NoSuchMethodError`**, do runtime `lib.Greeter` không còn phương thức tĩnh có tên, tham số và kiểu trả về mà bytecode cũ tham chiếu. Đây **không phải** lỗi `cannot find symbol` lúc biên dịch, vì lần biên dịch ứng dụng đã thành công với API v1.

Một JAR khác phiên bản không phải lúc nào cũng gây lỗi; lỗi xảy ra khi những thay đổi làm **phá vỡ tương thích nhị phân** với phần bytecode thực sự được dùng. Thêm một phương thức mới thường khác về tác động so với xóa/đổi chữ ký phương thức đang được gọi. Không nên phỏng đoán tính tương thích chỉ dựa vào nhãn “v2” hay số phiên bản semantic versioning.

## 7. Phụ thuộc chỉ cần lúc chạy: reflection và plugin

Một ứng dụng có thể chỉ biết tên lớp dưới dạng chuỗi rồi nạp lớp khi chạy. Vì tên lớp chưa được nhắc đến như **kiểu Java** trong khai báo/lời gọi, `javac` không cần đọc định nghĩa của lớp đích để kiểm tra câu lệnh `Class.forName`.

### 7.1. Lớp plugin

Tạo `plugin-src/ext/Extension.java`:

~~~java
package ext;

public final class Extension {
    @Override
    public String toString() {
        return "plugin loaded";
    }
}
~~~

Biên dịch plugin và đóng gói:

~~~sh
javac --release 17 -encoding UTF-8 -d plugin-classes plugin-src/ext/Extension.java
jar --create --file artifacts/extension.jar -C plugin-classes .
~~~

Tạo thư mục `plugin-classes` trước khi gọi `javac`.

### 7.2. Ứng dụng không import kiểu plugin

Tạo `reflect-src/app/ReflectMain.java`:

~~~java
package app;

public final class ReflectMain {
    public static void main(String[] args) throws Exception {
        System.out.println(
            Class.forName("ext.Extension")
                .getDeclaredConstructor()
                .newInstance()
        );
    }
}
~~~

Biên dịch ứng dụng **không cần** `extension.jar` trên compile classpath:

~~~sh
javac --release 17 -encoding UTF-8 -d reflect-classes reflect-src/app/ReflectMain.java
~~~

Tạo `reflect-classes` trước khi compile. Mã chỉ sử dụng API Java như `Class` và reflection; tên `ext.Extension` là chuỗi dữ liệu trong source. `javac` không dùng chuỗi này như khai báo kiểu cần phân giải.

Khi chạy, phải cung cấp JAR plugin. Windows:

~~~powershell
java -cp "reflect-classes;artifacts/extension.jar" app.ReflectMain
~~~

Linux/macOS:

~~~sh
java -cp "reflect-classes:artifacts/extension.jar" app.ReflectMain
~~~

Stdout đã kiểm chứng:

~~~text
plugin loaded
~~~

Nếu thiếu `extension.jar` và chạy `java -cp reflect-classes app.ReflectMain`, ứng dụng gặp:

~~~text
java.lang.ClassNotFoundException: ext.Extension
~~~

Ví dụ này thể hiện **runtime-only dependency** trong ứng dụng. Trong hệ plugin thực tế, lớp plugin có thể được nạp bởi class loader riêng hoặc Java module layer, không nhất thiết bởi application classpath; vẫn phải đảm bảo loader đó có thể tìm định nghĩa lớp. Việc dùng `Class.forName` với tên lớp tồn tại cũng không tự đảm bảo constructor công khai, module access, hoặc mọi dependency của plugin đều có sẵn.

### 7.3. ServiceLoader và cơ chế phát hiện implementation

Java `ServiceLoader` là một ví dụ khác của runtime extensibility. Ứng dụng thường compile dựa trên **service interface**, còn implementation có thể được thêm khi chạy và đăng ký qua `META-INF/services/<service-interface>` trong JAR trên classpath, hoặc khai báo `provides ... with ...` trong named module.

Điều kiện quan trọng:

- API/interface phải được ứng dụng nhận biết ở giai đoạn biên dịch nếu code tham chiếu trực tiếp tới interface đó.
- Provider implementation và thông tin đăng ký phải sẵn có ở runtime trong môi trường class loader/module phù hợp.
- Không tìm thấy provider có thể dẫn đến việc danh sách provider trống; cấu hình sai hoặc provider không nạp/khởi tạo được có thể dẫn đến `ServiceConfigurationError`.

Đừng đánh đồng mọi runtime-only dependency với reflection: tài nguyên cấu hình, logging backend, JDBC driver, native library và provider/plugin cũng có thể thuộc tập dependency chỉ phát sinh trong một đường thực thi hoặc một cơ chế nạp động cụ thể.

## 8. Dependency phục vụ biên dịch mà không cần lúc chạy

Chiều ngược lại cũng tồn tại. Một số công cụ/phụ thuộc dùng để tạo hoặc kiểm tra bytecode, rồi không cần thiết khi chạy ứng dụng đã được biên dịch đúng.

### 8.1. Annotation processor

Annotation processor chạy trong tiến trình biên dịch để đọc annotation/model và có thể sinh tệp Java hoặc tài nguyên. Ví dụ một processor tự tạo class, tạo mã mapping hoặc kiểm tra quy tắc compile-time. Khi mã sinh ra đã biên dịch, **processor implementation** thường không cần nằm trên runtime classpath. Tuy nhiên, các class mà mã sinh ra tham chiếu trực tiếp **vẫn phải** có ở runtime.

Trong cấu hình dự án, nên phân biệt **annotation processor path** với application compile classpath. Với `javac`, `-processorpath` (hoặc `--processor-path`) chỉ nơi tìm annotation processors trên classpath; khi sử dụng Java modules có những tùy chọn processor module path riêng tùy JDK. Cấu hình processor không có nghĩa thêm toàn bộ dependency của processor vào runtime.

JDK 17 có các hành vi mặc định về phát hiện processor khác một số JDK mới hơn; khi cần build tái lập, nên khai báo processor cần chạy một cách tường minh thay vì dựa vào thiết lập máy hoặc dự đoán mặc định cho mọi JDK.

### 8.2. API chỉ dùng trong source và các điều kiện bảo đảm

Một dependency chứa annotation chỉ có `RetentionPolicy.SOURCE` có thể cần để compiler xử lý source nhưng annotation đó không được ghi vào class file để runtime tra cứu. Tương tự, một tool API hoặc thư viện sinh mã có thể chỉ cần trong lúc build nếu không có bytecode runtime nào phụ thuộc vào nó.

**Cẩn thận:** chỉ vì mã biên dịch thành công khi dùng một thư viện không có nghĩa thư viện đó không cần runtime. Đặc biệt, các API annotation với retention `RUNTIME`, bytecode chứa tham chiếu kiểu hoặc mã được sinh ra có thể vẫn cần dependency đó. Phải kiểm tra nhu cầu thực của bytecode, cơ chế reflection và quá trình nạp lớp.

Những phần tử kiểu `compileOnly` của build tool chỉ phù hợp khi môi trường chạy **đã cung cấp API/lớp cần thiết** (ví dụ container/server), hoặc khi chúng thực sự không còn được dùng ở runtime. Nếu khai báo `compileOnly` cho một thư viện mà mã ứng dụng vẫn gọi lúc chạy, rất dễ tạo lỗi thiếu lớp.

## 9. Phụ thuộc trực tiếp, gián tiếp và triển khai nhiều JAR

Giả sử:

~~~text
Application
    |
    v
library-a.jar  --->  library-b.jar
                     |
                     v
                 library-c.jar
~~~

Ứng dụng chỉ import lớp `a.Service`, nhưng khi chạy `a.Service` lại cần `b.Parser` rồi `c.Codec`. **Runtime dependency set** phải bao gồm những thành phần thực sự cần thiết trên các nhánh được thực thi. Không phải cứ thêm `library-a.jar` là class loader tự có `library-b.jar` hay `library-c.jar`.

Một JAR thông thường chứa bytecode/tài nguyên của chính nó; nó **không tự động nhúng** toàn bộ các dependency Maven/Gradle, trừ khi đóng gói theo dạng fat/uber JAR hoặc cơ chế đóng gói đặc biệt. File `pom.xml` của một artifact dùng cho dependency resolution ở build tool, nhưng JVM `java -cp path/to/lib.jar` không tự lấy thêm các thư viện transitive từ Maven Central chỉ vì đọc tên JAR.

### 9.1. Vì sao biên dịch có thể thành công dù runtime thiếu transitive dependency?

Compiler có thể kiểm tra lời gọi chỉ cần API hiện có trong `library-a.jar`, chưa cần đi sâu vào mọi implementation hoặc nhánh runtime mà `a.Service` có thể thực thi. Khi thực thi, code trong A kích hoạt một lớp ở B; nếu B không được nạp, runtime có thể phát sinh lỗi.

Ngược lại, `javac` **có thể cũng cần dependency gián tiếp ngay lúc biên dịch** nếu chữ ký public, superclass, interface, annotation hoặc thông tin generic mà compiler phải xử lý chứa kiểu từ B. Vì vậy không có quy tắc “transitive dependency chỉ cần khi chạy”. Cần xét API thực tế và các lớp mà `javac` phải đọc.

### 9.2. Cùng tên lớp ở nhiều JAR: không nên dựa vào thứ tự

Nếu có hai JAR đều chứa `lib.Greeter`, runtime có thể tải một định nghĩa khác với bản mà compiler đã dùng, tùy class loader, thứ tự classpath và cấu hình môi trường. Không có lời bảo đảm rằng “bản mới nhất thắng”. Đây là nguồn lỗi khó tìm như `NoSuchMethodError`.

Để tránh:

1. Chỉ cho một phiên bản phù hợp của mỗi thư viện xuất hiện trong đường nạp tương ứng, nếu thiết kế không yêu cầu cách ly.
2. Giữ compile và runtime resolution nhất quán; dùng dependency locking/BOM/version constraints phù hợp với build tool.
3. Kiểm tra dependency tree và artifact thực tế được đóng gói.
4. Đối với plugin cần nhiều phiên bản song song, cân nhắc class loader isolation, shading/relocation hoặc module boundaries đã được thiết kế và kiểm thử.

### 9.3. Lớp JDK có cần đưa vào classpath?

Các API thuộc nền tảng Java, chẳng hạn `java.lang.String` và `java.util.List`, đến từ các Java platform modules (ví dụ `java.base`) có trong JDK/runtime phù hợp; không cần chép `rt.jar` của Java 8 vào classpath JDK 17. Với Java 9+, các module hệ thống và `--release` quản lý phần API nền tảng theo mô hình hiện đại.

Nhưng **library bên thứ ba** như JDBC driver cụ thể, HTTP client ngoài JDK hoặc framework không tự trở thành một phần của Java runtime. Đừng nhầm API chuẩn `java.sql` với JAR driver của một cơ sở dữ liệu riêng.

## 10. Phân biệt classpath và module path

Các ví dụ ở phần 3–7 chạy trên **classpath** (unnamed module). Khi dự án có `module-info.java`, Java Platform Module System (JPMS) bổ sung quy tắc **module readability, exports/opens và module resolution**.

~~~java
// Ví dụ minh họa module-info.java, không phải tệp của bài chạy ở trên.
module app.module {
    requires lib.module;
}
~~~

Tùy dự án, module `lib.module` có thể `exports lib.api;` để module khác sử dụng API. `requires` cho biết module dependency; `exports` quyết định package API được truy cập tại compile time và runtime theo quy tắc module. Reflection sâu có thể cần `opens` hoặc cấu hình mở phù hợp.

- Compile module bằng `javac --module-path ...` và cấu hình nguồn/module thích hợp.
- Run module bằng `java --module-path ... -m app.module/<main-class>`.
- Không tự cho rằng `-cp` và `--module-path` có thể thay thế cho nhau.
- Một module tồn tại trên module path chưa chắc đã được resolved cho một cấu hình chạy cụ thể.
- Trên JPMS, phụ thuộc module có thể là yêu cầu ở compile time, runtime hoặc cả hai, tùy `requires`, `requires static`, cơ chế resolution và cách chương trình sử dụng module.

Đây là minh họa phạm vi khái niệm; ví dụ hoàn chỉnh phần 3 không có `module-info.java`. Các vấn đề như automatic modules, qualified exports và module layers cần xem cấu hình thực của ứng dụng.

## 11. Khi chạy bằng JAR: -cp khác -jar

Với chương trình gọi trực tiếp class main:

~~~sh
java -cp "app-classes:artifacts/greeter.jar" app.Main
~~~

(đường phân cách ví dụ là Linux/macOS), application classpath do `-cp` xác định. Nhưng khi chạy:

~~~sh
java -jar app.jar
~~~

Java launcher dùng **entry point** từ manifest của JAR (ví dụ `Main-Class`) và bỏ qua cách chỉ định user classpath bằng `-cp` cho kiểu launch `-jar`. Những entry `Class-Path` hợp lệ trong manifest có thể cung cấp thêm đường dẫn, nhưng không thay bằng việc “gắn `-cp` trước `-jar`”.

Fat JAR/bootable JAR của framework có thể sử dụng launcher/class loader riêng để nạp nested JARs. Vì thế không thể khẳng định mọi file `app.jar` đều hoạt động giống một JAR thuần. Muốn phân tích runtime dependency, cần biết **cách đóng gói và cơ chế khởi chạy thực tế**.

Không nên nhầm classpath khi chạy với đường dẫn tài nguyên tương đối dựa vào working directory. Một tệp `config/application.properties` trên filesystem cần được truy cập theo quy tắc đường dẫn của chương trình; resource đặt trong JAR nên nạp bằng API resource/class loader phù hợp.

## 12. Scope dependency trong Gradle và Maven

Build tool giúp phân loại các nhu cầu khác nhau, tránh việc tự nối mọi JAR vào cả hai classpath. Các ví dụ sau là **minh họa cú pháp build**, không phải phần của dự án Java nhỏ ở phần 3.

### 12.1. Gradle Java plugin

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:core:1.0'
    compileOnly 'org.example:provided-api:1.0'
    runtimeOnly 'org.example:runtime-provider:1.0'
    annotationProcessor 'org.example:code-generator:1.0'
}
~~~

Các tọa độ `org.example` trên chỉ để minh họa ý nghĩa configuration, **không phải artifact được bảo đảm có trên Maven Central**.

| Configuration | Ý nghĩa chính |
|---|---|
| `implementation` | Thư viện dùng cho compile classpath của chính module và thường có trong runtime classpath của module |
| `compileOnly` | Cần khi biên dịch, không tự thêm vào runtime |
| `runtimeOnly` | Cần khi chạy, không tự thêm vào compile classpath |
| `annotationProcessor` | Dependency cho annotation processor path của quá trình compile |
| `testImplementation` | Dành cho biên dịch/chạy test theo cấu hình Java plugin |
| `testRuntimeOnly` | Dành riêng runtime của test |

Nếu dùng plugin `java-library`, `api` giúp khai báo dependency nằm trong **public API** mà consumer cũng cần khi biên dịch. `implementation` thường biểu thị chi tiết triển khai mà consumer không nên buộc phải phụ thuộc trực tiếp. Việc chọn `api`/ `implementation` liên quan đến cách công khai dependency qua các project/module, **không đồng nhất** với phân biệt runtime-only.

Có thể xem classpath và dependency resolution bằng các task Gradle:

~~~sh
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows dùng `gradlew.bat` thay cho `./gradlew` nếu phù hợp. Tên configuration thực tế có thể khác theo plugin/source set. Đầu ra dependency tree cho biết build tool chọn những gì; vẫn cần kiểm tra bản phân phối thực tế nếu đóng gói bằng plugin khác.

### 12.2. Maven scopes

Maven dùng `scope` để mô tả mục đích dependency trong model build. Các scope phổ biến:

| Scope Maven | Ý nghĩa khái quát |
|---|---|
| `compile` | Mặc định; thường có trên compile, test và runtime classpaths |
| `provided` | Có khi biên dịch/test; môi trường chạy dự kiến cung cấp dependency, không được đóng vào artifact theo cách thông thường |
| `runtime` | Không cần để biên dịch nguồn trực tiếp của module; có khi chạy/test |
| `test` | Chỉ phục vụ source/test classpath, không là dependency runtime của ứng dụng chính |
| `system` | Cần đường dẫn hệ thống chỉ định riêng; thường nên tránh vì kém tái lập |

Maven và Gradle có quy tắc transitivity, conflict resolution và packaging khác nhau. Không nên áp một bảng “scope này lúc nào cũng có trong JAR” cho mọi plugin đóng gói. Chẳng hạn plain JAR do Java plugin tạo ra không tự nhúng tất cả runtime dependencies; một Spring Boot executable JAR lại có layout và loader riêng.

## 13. Chẩn đoán lỗi khi compile chạy khác nhau

| Triệu chứng | Giai đoạn và nguyên nhân có thể | Hướng xác minh |
|---|---|---|
| `package lib does not exist` | Compile: `javac` không tìm thấy package | So `javac -cp`, nguồn và JAR chứa `lib/Greeter.class` |
| `cannot find symbol: Greeter` | Compile: không resolve được ký hiệu | Kiểm tra import, package, classpath/sourcepath, quyền truy cập |
| `NoClassDefFoundError: lib/Greeter` | Runtime: JVM không có định nghĩa lớp khi cần, hoặc lỗi khởi tạo lớp trước đó | Kiểm tra `java -cp`, nội dung JAR, `Caused by` |
| `ClassNotFoundException: ext.Extension` | Runtime: nạp lớp theo tên bị thất bại | Kiểm tra tên lớp, class loader, plugin JAR/module và đường nạp |
| `NoSuchMethodError` | Runtime linkage: chữ ký phương thức được tham chiếu không có trong lớp thấy lúc chạy | Xác minh compile API và runtime binary/version |
| `NoSuchFieldError` | Runtime linkage: field bị đổi/xóa hoặc không khớp | Kiểm tra binary compatibility và các JAR trùng kiểu |
| `IllegalAccessError` | Runtime: vi phạm yêu cầu truy cập lúc liên kết sau thay đổi binary/module | So compile/runtime access và các thay đổi module/API |
| `UnsupportedClassVersionError` | Runtime: bytecode class file được tạo cho phiên bản Java cao hơn runtime hỗ trợ | Kiểm tra `javac -version`, `java -version`, `--release` |
| `ServiceConfigurationError` | Runtime: ServiceLoader không xử lý được provider được cấu hình | Kiểm tra metadata provider, constructor, class loader và dependency |
| Chạy IDE được nhưng terminal lỗi | Classpath/working directory/JDK khác nhau | So chính xác câu lệnh, dependency tree và run configuration |

### 13.1. Bộ lệnh kiểm tra thực tế

Những lệnh sau phù hợp khi làm việc trong dự án ví dụ:

~~~sh
javac -version
java -version
jar --list --file artifacts/greeter.jar
~~~

Tìm entry `lib/Greeter.class` trong danh sách JAR. Trên hệ thống dùng classpath, kiểm tra cách lớp được nạp bằng `-verbose:class` khi thực sự cần:

~~~sh
java -verbose:class -cp "<application-and-library-classpath>" app.Main
~~~

Tùy chọn này có thể in rất nhiều dòng. Thay chuỗi placeholder bằng classpath **thật của môi trường**, với dấu phân cách đúng hệ điều hành. Có thể dùng `javap` để xem chữ ký class đã biên dịch:

~~~sh
javap -classpath artifacts/greeter.jar lib.Greeter
~~~

Nếu hiển thị `message(java.lang.String)` ở JAR dùng khi compile nhưng chỉ `message()` ở JAR dùng khi chạy, đã có bằng chứng về binary mismatch. Dùng `javap -c` khi cần xem bytecode gọi method nào; đừng đánh giá chỉ theo tên file JAR.

### 13.2. Thứ tự điều tra hiệu quả

1. **Phân biệt compile lỗi hay runtime lỗi.** Nếu `javac` không thành công, chưa kết luận về runtime classpath.
2. **Xác định lớp/field/method cần tìm.** Đọc tên đầy đủ trong thông báo và stack trace.
3. **Kiểm tra JDK và đường dẫn.** `java` và `javac` có cùng phiên bản mục tiêu không; working directory có đúng không?
4. **Kiểm tra các classpaths thực tế.** Lệnh compile truyền `-cp` gì? Lệnh run truyền `-cp` gì? Biến `CLASSPATH` hoặc build tool có chèn giá trị không?
5. **Kiểm tra nội dung và phiên bản JAR.** Có class path entry đúng vị trí? Có hai JAR chứa cùng class không?
6. **Kiểm tra dependency gián tiếp.** Runtime implementation A có gọi B/C không? Các dependency có được phân phối cùng ứng dụng không?
7. **Kiểm tra cơ chế nạp động.** Reflection, ServiceLoader, class loader plugin, container hoặc module layer có phạm vi tìm riêng không?
8. **Rebuild/repackage nhất quán.** Tránh chạy bytecode/JAR cũ sau khi API đã đổi; nếu cần xóa output, chỉ làm sạch đúng thư mục generated của build.

## 14. Những hiểu nhầm cần tránh

**“Đã import class thì JVM tự tìm được JAR.”** Sai. `import` là cú pháp nguồn; JVM chạy bytecode, class loader phải có đường đến class thực sự.

**“Compile pass nghĩa là chạy chắc chắn pass.”** Sai. Runtime có thể thiếu lớp, thiếu tài nguyên, lỗi khởi tạo, lỗi linkage, ngoại lệ hoặc lỗi logic.

**“Thư viện runtime-only là thư viện không được dùng trong Java.”** Sai. Nó có thể được dùng thông qua reflection, provider API hoặc implementation của thư viện khác.

**“Tất cả dependency bắc cầu chỉ cần runtime.”** Sai. API public của thư viện có thể làm compiler cần thêm một kiểu từ dependency bắc cầu ngay lúc compile.

**“Chỉ cần copy JAR mới cùng tên vào thư mục libs là an toàn.”** Sai. Compile binary có thể không tương thích với runtime binary mặc dù tên JAR/package/class vẫn giống.

**“Có Java 17 thì classpath tự có mọi thư viện.”** Sai. Java platform API khác với JAR của các thư viện bên thứ ba.

**“Khi chạy -jar, cứ thêm -cp là được.”** Sai với cơ chế launcher thông thường: `-jar` lấy entry point và classpath theo cơ chế launch/manifest thay vì user classpath `-cp` theo cách chạy main class thông thường.

**“Một lớp chỉ có thể được nạp ngay lúc khởi động.”** Sai. JVM có thể nạp/link khi cần, và ứng dụng có thể chủ động tải class động; thời điểm lỗi có thể phụ thuộc đường thực thi.

## 15. Bài tập thực hành

### Bài 1 — Bỏ JAR ở từng giai đoạn

Dùng dự án ở phần 3. Thử ba tình huống:

1. Có `greeter.jar` trong compile classpath nhưng bỏ khỏi runtime classpath.
2. Bỏ JAR khỏi compile classpath nhưng vẫn có tệp JAR trong máy.
3. Có JAR ở cả hai giai đoạn.

Dự đoán lần nào `javac` báo lỗi, lần nào `java` báo lỗi, lần nào in hai dòng kết quả. Giải thích vì sao chỉ **có file trên đĩa** không đủ; chương trình phải được cấu hình để tìm file đó.

### Bài 2 — Thay API mà không biên dịch lại ứng dụng

Biên dịch ứng dụng với `greeter.jar` v1, rồi đổi runtime sang `greeter-v2.jar` như phần 6. Giải thích vì sao `NoSuchMethodError` khác `ClassNotFoundException`: trong trường hợp này class `Greeter` đã được tìm thấy, nhưng chữ ký method mà bytecode kỳ vọng không còn.

### Bài 3 — Runtime-only plugin

Biên dịch `ReflectMain.java` không cần `extension.jar`. Chạy có và không có JAR plugin. Dự đoán thời điểm JVM xử lý chuỗi tên `ext.Extension` và loại lỗi khi không tìm được lớp. Thử sửa chuỗi tên lớp sai một chữ; xem kết quả.

### Bài 4 — Dependency tree

Với một dự án Gradle/Maven có vài thư viện, liệt kê dependency compile và runtime. Chọn một thư viện chỉ dùng qua provider, một thư viện ứng dụng import trực tiếp và một processor. Giải thích vì sao ba thư viện được cấu hình khác nhau.

### Bài 5 — Kiểm tra JAR có trùng lớp

Tạo hai JAR cùng chứa `lib.Greeter` nhưng chữ ký khác nhau. Thử chạy với một JAR mỗi lần. Sau đó kiểm tra nội dung bằng `jar --list` hoặc `javap`. Trong ứng dụng thật, hãy dùng dependency resolution để chọn phiên bản duy nhất phù hợp thay vì trông chờ vào thứ tự classpath.

## 16. Checklist trước khi bàn giao một ứng dụng Java

- **Compile:** Đã cung cấp đầy đủ các API, kiểu, annotation processor, source path hoặc module path mà `javac` thực sự cần.
- **Run:** Đã đóng gói/cung cấp mọi class, implementation và tài nguyên được những đường thực thi quan trọng sử dụng.
- **Version:** Dependency compile và runtime tương thích về binary/API; không có JAR trùng lớp ngoài ý muốn.
- **Launch:** Đã xác định ứng dụng dùng `java -cp`, `java -jar`, module path hay custom class loader và cấu hình đường nạp theo đúng cơ chế.
- **Environment:** Runtime JDK hỗ trợ bytecode; working directory và cấu hình môi trường phù hợp.
- **Validation:** Kiểm tra cả `javac` thành công **lẫn** khởi chạy/tình huống runtime có dependency động, không chỉ dừng ở build success.
- **Reproducibility:** Dùng Gradle/Maven, khóa hoặc quản lý phiên bản cần thiết và xác thực artifact đã phát hành.

Phân biệt hai loại phụ thuộc giúp bạn đặt đúng câu hỏi khi gặp lỗi: **`javac` thiếu định nghĩa để hiểu mã nguồn, hay JVM thiếu (hoặc nhận sai) định nghĩa để thực thi bytecode?** Trả lời câu hỏi đó là bước đầu tiên để xử lý đúng classpath, build configuration và cách đóng gói ứng dụng.
