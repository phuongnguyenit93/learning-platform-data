# Classpath là gì và trình biên dịch Java tìm kiểu như thế nào?

Khi biên dịch một file Java, `javac` phải xác định **mọi kiểu** mà chương trình sử dụng: các kiểu khai báo trong file hiện tại, các lớp có sẵn của nền tảng Java và những lớp từ source hoặc thư viện bên ngoài. **Classpath** là tập các vị trí mà công cụ Java có thể tìm những class thuộc cơ chế classpath. Với `javac`, nó là một đầu vào quan trọng cho quá trình **phân giải tên, tìm khai báo kiểu và kiểm tra kiểu**; với lệnh `java`, nó là một trong các nguồn để tìm class khi ứng dụng chạy.

Hiểu classpath giúp giải thích vì sao một chương trình biên dịch được trên IDE nhưng không biên dịch được trên terminal, vì sao thêm `import` không sửa được lỗi thiếu thư viện, vì sao compiler thấy được `.class` nhưng lúc chạy vẫn báo `NoClassDefFoundError`, và vì sao thay đổi thứ tự các JAR có thể làm kết quả khác đi.

Bài học tập trung vào chương trình Java 17+ **không khai báo module** trước; phần cuối phân biệt classpath với module path trong JPMS.

## 1. Classpath là gì?

Một classpath có thể chứa nhiều **classpath entry**. Những entry phổ biến là:

- Một thư mục gốc chứa các file `.class` được xếp theo tên package, chẳng hạn `build/classes/java/main`.
- Một file `.jar` chứa các file `.class`, ví dụ `lib/utility.jar`.
- Một thư mục gốc chứa source `.java` khi `javac` được phép dùng classpath để tìm source (xem `-sourcepath`).
- Một số dạng entry đặc biệt được Java tool chấp nhận, như wildcard `lib/*` cho các JAR trực tiếp bên trong thư mục.

Ví dụ một class có tên đầy đủ `com.example.tool.Parser` được biên dịch thành:

```text
classes/
└── com/
    └── example/
        └── tool/
            └── Parser.class
```

Classpath entry phải là **`classes`**, vì công cụ nối phần package `com/example/tool/Parser.class` vào *gốc classpath*. Nếu truyền `classes/com/example/tool` thay vì `classes`, việc tra cứu `com.example.tool.Parser` thường thất bại.

Tương tự, JAR là gốc chứa package path:

```text
utility.jar
└── com/
    └── example/
        └── tool/
            └── Parser.class
```

Trong mã nguồn, `import com.example.tool.Parser;` làm tên đơn `Parser` khả dụng theo quy tắc import. **`import` không tải JAR, không thêm directory vào classpath và không tạo class còn thiếu**. Compiler vẫn phải tìm được định nghĩa của `com.example.tool.Parser` từ các input hợp lệ.

## 2. Classpath được dùng ở hai thời điểm khác nhau

Có hai lệnh khác nhau, nên có hai việc tìm kiếm khác nhau:

| Thời điểm | Lệnh ví dụ | Công cụ cần tìm | Kết quả |
| --- | --- | --- | --- |
| **Biên dịch** | `javac -cp lib/example.jar -d out src/Main.java` | Khai báo kiểu, method, field, superclass, interface của dependency | Kiểm tra cú pháp/ngữ nghĩa, sinh file `.class` |
| **Chạy** | `java -cp "out:lib/example.jar" Main` (macOS/Linux) | Các class cần nạp để khởi động và thực thi chương trình | JVM nạp, liên kết và thực thi class |

Classpath cho compiler **không được tự động chuyển** thành classpath cho Java launcher trong lần chạy sau. Nếu compiler đọc được `lib/example.jar` nhưng runtime chỉ dùng `-cp out`, chương trình có thể thất bại khi cần class trong JAR.

Ngược lại, thêm JAR vào classpath runtime không giúp sửa lỗi `javac` báo `package ... does not exist` nếu JAR ấy không nằm trên đường tìm kiếm lúc biên dịch.

Lưu ý: cú pháp dấu phân cách entry phụ thuộc hệ điều hành:

- **Windows:** dấu chấm phẩy `;`, chẳng hạn `"out;lib\example.jar"` (ký tự `;` thực tế là dấu phân cách; không cần dấu gạch chéo ngược trước nó).
- **macOS/Linux:** dấu hai chấm `:`, chẳng hạn `"out:lib/example.jar"`.
- Tên path có khoảng trắng nên đặt trong dấu nháy kép phù hợp với shell.

Đừng nhầm dấu `.` dùng làm classpath entry (thư mục làm việc hiện tại) với dấu chấm phân cách package trong tên class như `com.example.Main`.

## 3. `javac` tìm định nghĩa kiểu ra sao?

Giả sử trong nguồn có:

```java
package demo.app;

import demo.lib.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

Khi xử lý `demo.lib.Message`, compiler cần tìm khai báo của kiểu đó. Có thể hình dung luồng xử lý đối với một project dùng classpath:

```text
Main.java (đầu vào tường minh)
      |
      v
Phân tích cú pháp và ghi nhận khai báo
      |
      v
Tham chiếu demo.lib.Message
      |
      +--> Kiểu đã được khai báo trong compilation unit?
      |
      +--> Kiểu của nền tảng Java hoặc kiểu có thể thấy theo module?
      |
      +--> Kiểu tìm thấy trên classpath (.class, JAR)?
      |
      +--> Source tương ứng tìm thấy trên source path
             hoặc classpath khi không cấu hình source path?
      |
      v
Đọc định nghĩa, kiểm tra accessibility và kiểu
      |
      +--> Hợp lệ: tiếp tục biên dịch
      |
      +--> Không thấy/không hợp lệ: diagnostic
```

Đây là sơ đồ **khái niệm**, không phải danh sách chính xác các lời gọi nội bộ của mọi phiên bản `javac`. Compiler có thể trì hoãn hoàn thiện kiểu, đọc metadata từ class file và duyệt quan hệ kế thừa.

Điểm quan trọng:

1. Compiler cần *thông tin khai báo* để xác minh một tham chiếu, không nhất thiết phải có source cho mọi dependency.
2. Một `.class` trong JAR có thể cung cấp tên, modifier, superclass, interface, field và method đủ cho việc kiểm tra phần lớn lời gọi; không cần đọc source gốc của thư viện.
3. Classpath là **danh sách vị trí tìm kiếm**, không phải sơ đồ quan hệ phụ thuộc ở mức Maven/Gradle.
4. Có class file chưa đủ nếu quyền truy cập, chữ ký, kiểu hoặc ranh giới module làm tham chiếu không hợp lệ.

## 4. Ví dụ Java 17+: biên dịch thư viện rồi biên dịch ứng dụng

Tạo các file và thư mục dưới đây (tên folder thể hiện package):

```text
classpath-lab/
├── libsrc/
│   └── demo/
│       └── lib/
│           └── Message.java
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
└── out/
    ├── lib/            (ban đầu trống)
    └── app/            (ban đầu trống)
```

Nội dung `libsrc/demo/lib/Message.java`:

```java
package demo.lib;

public final class Message {
    private Message() {}

    public static String text() {
        return "classpath works";
    }
}
```

Nội dung `appsrc/demo/app/Main.java`:

```java
package demo.app;

import demo.lib.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

Chạy các lệnh sau **từ thư mục `classpath-lab`**; trước đó tạo `out/lib` và `out/app`. Trên macOS/Linux:

```bash
mkdir -p out/lib out/app
javac -encoding UTF-8 -d out/lib libsrc/demo/lib/Message.java
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
java -cp "out/app:out/lib" demo.app.Main
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/lib, out/app | Out-Null
javac -encoding UTF-8 -d out/lib libsrc/demo/lib/Message.java
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
java -cp "out/app;out/lib" demo.app.Main
```

Stdout chính xác ở cả hai hệ điều hành:

```text
classpath works
```

Sau hai lệnh `javac`, các class file quan trọng nằm ở:

```text
out/lib/demo/lib/Message.class
out/app/demo/app/Main.class
```

Phân tích từng lệnh:

- `javac -d out/lib ...Message.java` biên dịch thư viện. `-d` chọn **thư mục output**, không phải classpath dùng để tìm dependency.
- `javac -cp out/lib -d out/app ...Main.java` cho phép compiler đọc `Message.class`. Nếu bỏ `-cp out/lib` trong môi trường không có đường tìm kiếm khác phù hợp, `javac` không tìm được `demo.lib.Message`.
- `java -cp "out/app:out/lib" demo.app.Main` cung cấp **cả** class chứa `main` và class của thư viện. Với Windows, dùng dấu `;`.
- Chạy `java` bằng **tên binary class** `demo.app.Main`, không phải `appsrc/demo/app/Main.java` hay `demo/app/Main.class` ở chế độ launcher bằng classpath này.

Thí nghiệm: chạy `java -cp out/app demo.app.Main` sau khi đã biên dịch. JVM có thể nạp `Main`, nhưng sẽ thất bại khi cần `demo.lib.Message` vì runtime classpath không có `out/lib`. Thông báo thường là `NoClassDefFoundError: demo/lib/Message`; chi tiết stack trace có thể khác theo JDK.

## 5. Khi dependency được đóng gói thành JAR

Một JAR thông thường chứa cấu trúc package và file `.class`. Từ ví dụ trên, có thể đóng gói thư viện:

```bash
jar --create --file out/message.jar -C out/lib .
```

Sau đó compiler có thể dùng JAR thay vì thư mục:

```bash
javac -encoding UTF-8 -cp out/message.jar -d out/app appsrc/demo/app/Main.java
```

Chạy trên macOS/Linux:

```bash
java -cp "out/app:out/message.jar" demo.app.Main
```

Chạy trên Windows:

```powershell
java -cp "out/app;out/message.jar" demo.app.Main
```

Stdout vẫn là:

```text
classpath works
```

`jar -C out/lib .` thay thư mục làm việc *bên trong thao tác đóng gói*, nên JAR có đường dẫn `demo/lib/Message.class` ở gốc. Nếu vô tình gói luôn tiền tố `out/lib` vào JAR, compiler sẽ không tìm thấy class theo tên package mong đợi.

Có thể kiểm tra nội dung JAR bằng:

```bash
jar --list --file out/message.jar
```

Hãy tìm `demo/lib/Message.class` trong danh sách. Manifest và các mục phụ có thể xuất hiện thêm.

Đối với phụ thuộc từ thư viện của bên thứ ba, Maven/Gradle thường tải và cấu hình JAR hoặc module tương ứng. Khi gọi `javac` trực tiếp, chính người gọi cần cung cấp các file tương ứng trên đường tìm kiếm hợp lệ.

## 6. `-cp`, `-classpath` và `--class-path`

Ba cú pháp sau dùng để chỉ định user classpath cho `javac`:

```bash
javac -cp out/lib -d out/app appsrc/demo/app/Main.java
javac -classpath out/lib -d out/app appsrc/demo/app/Main.java
javac --class-path out/lib -d out/app appsrc/demo/app/Main.java
```

Chúng có cùng ý nghĩa đối với ví dụ này. Các entry được viết thành một tham số đường dẫn duy nhất, cách nhau bằng `:` trên hệ Unix hoặc `;` trên Windows.

Ví dụ nhiều directory/JAR trên macOS/Linux:

```bash
javac -cp "out/lib:lib/a.jar:lib/b.jar" -d out/app appsrc/demo/app/Main.java
```

Tương đương trên Windows PowerShell:

```powershell
javac -cp "out/lib;lib/a.jar;lib/b.jar" -d out/app appsrc/demo/app/Main.java
```

Một số quy tắc cần nhớ:

- `-cp` tường minh **thay thế** user classpath lấy từ biến môi trường `CLASSPATH` trong lệnh đó; nó không mặc nhiên nối thêm.
- Nếu không chỉ định `-cp`, công cụ có thể lấy user classpath từ `CLASSPATH` nếu biến ấy được thiết lập; nếu không, mặc định thường là thư mục làm việc hiện tại `.`.
- Khi đã chỉ định `-cp`, **`.` không được tự thêm vào danh sách theo ý người dùng**. Muốn dùng cả current directory, thêm `.` như một entry riêng.
- `-d out/app` không tự đưa `out/app` vào user classpath để compiler tìm lớp đã biên dịch; cần chỉ định nguồn/classpath phù hợp cho lần compile phụ thuộc.
- Classpath không tự tải thư viện từ mạng và không tự đọc file khai báo dependency của Maven/Gradle.

Để tránh máy phát triển và CI nhìn thấy tập thư viện khác nhau, nên khai báo classpath và toolchain rõ trong build thay vì dựa vào `CLASSPATH` toàn cục.

## 7. `-sourcepath`: nơi tìm nguồn bổ sung

`-sourcepath` (hoặc `--source-path`) dành cho vị trí mà `javac` tìm **source file `.java` bổ sung** khi cần khai báo của một kiểu.

Chạy từ thư mục `classpath-lab` trong ví dụ:

```bash
javac -encoding UTF-8 -sourcepath libsrc -d out/implicit appsrc/demo/app/Main.java
```

Trước đó cần tạo thư mục `out/implicit` rỗng. `javac` nhận một source tường minh `Main.java`; khi cần `demo.lib.Message`, nó có thể tìm `libsrc/demo/lib/Message.java` trên source path. Với hành vi sinh class ngầm mặc định, compiler có thể tạo cả:

```text
out/implicit/demo/app/Main.class
out/implicit/demo/lib/Message.class
```

Trong ví dụ này, lời gọi `java -cp out/implicit demo.app.Main` sẽ in:

```text
classpath works
```

Những điểm khác nhau cần ghi nhớ:

| Tham số | Chứa gì | Chức năng chính |
| --- | --- | --- |
| `-cp` | Thư mục/JAR chứa class, và có thể source khi không đặt source path riêng | Tìm kiểu đã biên dịch trên user classpath |
| `-sourcepath` | Gốc thư mục source theo package | Tìm thêm file `.java` phục vụ biên dịch |
| `-d` | Thư mục output | Ghi file `.class` được tạo |
| `-processorpath` | Nơi tìm annotation processor | Cấu hình processor discovery ở các JDK/chế độ tương ứng |
| `--module-path` | Thư mục/JAR module | Tìm named modules theo hệ JPMS |

Khi biên dịch chương trình theo classpath, nếu **không chỉ định source path**, `javac` có thể tìm source trong user classpath. Nếu cả source và class của cùng một kiểu tồn tại, mặc định compiler thường ưu tiên file mới hơn theo timestamp; `-Xprefer:source` có thể thay đổi lựa chọn này. Vì vậy, chồng source tree và build output cũ lên cùng một đường tìm kiếm có thể khiến kết quả lệ thuộc thời điểm sửa file.

## 8. Biên dịch ngầm có liên quan classpath nhưng không đồng nghĩa classpath

Giả sử lệnh chỉ liệt kê:

```bash
javac -sourcepath libsrc -d out/implicit appsrc/demo/app/Main.java
```

`Main.java` là **nguồn tường minh**. `Message.java` được tìm thấy vì `Main` cần khai báo `Message`, nên đó là **nguồn phụ thuộc được phát hiện ngầm**.

`javac` có tùy chọn:

- `-implicit:class`: cho phép sinh `.class` cho các file nguồn được phát hiện ngầm.
- `-implicit:none`: không sinh `.class` cho những file nguồn được phát hiện ngầm; compiler **vẫn có thể đọc chúng để phân tích và kiểm tra kiểu**.

Đối với ví dụ này, nếu chạy từ output rỗng:

```bash
javac -sourcepath libsrc -implicit:none -d out/none appsrc/demo/app/Main.java
```

thì thường chỉ có `out/none/demo/app/Main.class`. Runtime `java -cp out/none demo.app.Main` có thể báo thiếu `Message`. Nếu liệt kê **cả hai file nguồn tường minh** thì `-implicit:none` không chặn việc biên dịch `Message.java`:

```bash
javac -implicit:none -d out/together libsrc/demo/lib/Message.java appsrc/demo/app/Main.java
```

Cần tạo thư mục `out/none` và `out/together` trước khi chạy. Các thử nghiệm phải tách output và khởi đầu từ thư mục trống để class file cũ không che kết quả.

Sự phân biệt này giải thích vì sao “compiler tìm thấy khai báo trên source path” và “runtime đã có class file” là hai mệnh đề độc lập.

## 9. Thứ tự các entry và nguy cơ trùng lớp

Khi classpath có nhiều vị trí chứa cùng một tên binary class, thứ tự tìm kiếm có thể quyết định phiên bản nào được tìm thấy. Ví dụ:

```text
lib/old.jar  -> demo.lib.Message
lib/new.jar  -> demo.lib.Message
```

Nếu hai JAR cùng được thêm vào classpath, việc trùng tên có thể che khuất một phiên bản khác. Thứ tự entry có thể khiến compiler hoặc runtime dùng bản khác dự kiến.

Không nên giải quyết dependency conflict chỉ bằng cách “đổi chỗ JAR thử tới khi hết lỗi”. Cần kiểm tra:

1. **Tên class/package bị trùng** ở thư viện nào.
2. **Version** và chữ ký method thực tế được dùng khi compile.
3. **Classpath thực tế** của lệnh compiler, test runner và launcher.
4. **Graph dependency** do công cụ build tạo, gồm các transitive dependencies.
5. Các kỹ thuật đóng gói như shading/relocation nếu dự án có nhu cầu và hiểu rõ tác động.

Ví dụ `NoSuchMethodError` lúc runtime có thể xuất hiện khi lúc compile dùng một phiên bản class có method cần thiết nhưng runtime nạp phiên bản khác không có method/chữ ký đó. Đây là lỗi **binary compatibility/classpath mismatch**, không đơn thuần là lỗi cú pháp trong source.

Khi dùng wildcard `lib/*`, tập JAR được thêm vào có thể thay đổi theo nội dung thư mục; thứ tự JAR được mở rộng không được bảo đảm. Không nên dựa vào thứ tự wildcard để chọn “đúng phiên bản” nếu có class trùng nhau.

## 10. Wildcard và thư mục JAR: hiểu đúng phạm vi

Cú pháp classpath như:

```bash
javac -cp "lib/*" -d out appsrc/demo/app/Main.java
```

có thể đưa các JAR **trực tiếp nằm trong** thư mục `lib` vào user classpath. Điều này khác với:

- `-cp lib`: đưa chính thư mục `lib` vào classpath để tìm `lib/demo/pkg/Name.class`; không tự mở mọi JAR bên trong.
- `-cp "lib/*"`: thêm các JAR trực tiếp của `lib`; không phải quét đệ quy mọi thư mục con.
- `-cp "lib/a.jar"`: chọn chính xác một JAR.
- `-cp "."`: tìm class theo package path từ thư mục hiện tại; không đồng nghĩa tìm mọi tệp JAR ở đây.

Đặt `lib/*` trong dấu nháy ở shell để tránh shell tự mở rộng thành nhiều đối số; Java tool sẽ xử lý wildcard classpath theo cơ chế của nó. Không nhầm wildcard classpath với glob `**/*.jar` của shell hoặc với việc liệt kê source `*.java`.

Nếu vừa muốn dùng thư mục class của ứng dụng vừa muốn tất cả JAR trong `lib`, macOS/Linux:

```bash
java -cp "out/app:lib/*" demo.app.Main
```

Windows:

```powershell
java -cp "out/app;lib/*" demo.app.Main
```

Lưu ý: ví dụ chạy được khi `lib/*` thực sự bao gồm JAR có chứa `demo.lib.Message`. Ở phần thực hành trước, JAR được tạo tại `out/message.jar`, nên phải chuyển hoặc sao chép JAR ấy vào `lib` nếu muốn áp dụng ví dụ này; không mặc định tệp ở đó đã tồn tại.

## 11. Compiler tìm class của JDK ở đâu?

Các lớp nền tảng như `java.lang.String`, `java.util.List` hay `java.nio.file.Path` không đòi thêm `rt.jar` vào classpath của Java 17+. Từ Java 9 trở đi, các lớp của Java SE nằm trong các **platform modules**, ví dụ `java.base`.

`javac` biết cách tìm những API nền tảng phù hợp với JDK/cấu hình biên dịch. Chẳng hạn:

```java
import java.util.List;

class Example {
    List<String> values = List.of("one", "two");
}
```

Đoạn trên sử dụng `List` từ `java.base`, không phải một JAR do người dùng thêm vào `-cp`.

Khi biên dịch cho một phiên bản Java khác, dùng `--release` để giới hạn cả cú pháp và tập API Java SE có sẵn theo release được chọn:

```bash
javac --release 17 -d out Example.java
```

Điều này khác với việc chỉ chạy compiler bằng JDK 21 rồi mặc nhiên cho rằng các API Java 21 sẽ tương thích với Java 17. `--release 17` không tự giải quyết phiên bản của các thư viện bên thứ ba nằm trên classpath: dependency ấy cũng phải tương thích với target runtime.

## 12. Classpath và module path trong Java 9+

Từ khi có Java Platform Module System (JPMS), classpath vẫn được hỗ trợ. Những class nằm trên classpath thông thường thuộc **unnamed module** theo ngữ cảnh class loader tương ứng; các named module được tìm và cấu hình chủ yếu qua **module path** và quy tắc `requires`/`exports`.

| Khái niệm | Classpath | Module path |
| --- | --- | --- |
| Cơ chế chính | Tìm class theo package/binary name | Tìm module và giải quyết module graph |
| Metadata khai báo module | Không yêu cầu `module-info.class` | Named module có descriptor; JAR không có descriptor có thể dùng làm automatic module trong các ngữ cảnh phù hợp |
| Giới hạn phụ thuộc | Chủ yếu tên, class loader, access modifiers | Thêm module readability và package exports/opens |
| Lệnh thường gặp | `-cp`/`--class-path` | `-p`/`--module-path` |
| Khởi chạy | `java -cp ... main.Class` | `java --module-path ... --module module/name` |

Không đúng khi nói “thêm JAR vào `-cp` luôn làm một named module đọc được mọi class trong JAR”. Named module có ràng buộc *readability* và export riêng. Với dự án có `module-info.java`, hãy kiểm tra quy tắc JPMS và cách build tool giải quyết dependency.

Ngược lại, nếu đang học project Java nhỏ không có `module-info.java`, classpath là mô hình phù hợp và không cần chuyển sang module path chỉ để sử dụng một JAR.

## 13. Khi chạy JAR với `java -jar` thì sao?

`java -cp ... com.example.Main` và `java -jar app.jar` là hai cách khởi động có contract khác nhau:

- `java -cp "app.jar:lib/a.jar" com.example.Main` dùng classpath do bạn cung cấp và tên main class tường minh.
- `java -jar app.jar` chọn main class từ manifest của JAR. Trong chế độ này, user classpath từ `-cp`/`CLASSPATH` không được dùng để chọn class ứng dụng; dependency bên ngoài có thể phải được khai báo qua manifest `Class-Path` hoặc được đóng gói theo cách khác, hoặc dùng launcher phù hợp.

Một ứng dụng fat/uber JAR có thể đóng gói dependency khác với một JAR thông thường. Không phải mọi `app.jar` đều độc lập chạy được chỉ vì nó chứa `Main.class`.

Khi xử lý lỗi `ClassNotFoundException` hay `NoClassDefFoundError` dưới `java -jar`, cần kiểm tra manifest, cách đóng gói và launcher trước khi thêm `-cp` một cách vô hiệu.

## 14. Những lỗi classpath thường gặp và cách xác định nguyên nhân

| Triệu chứng | Ý nghĩa có thể | Kiểm tra và sửa |
| --- | --- | --- |
| `package demo.lib does not exist` khi `javac` | Không có định nghĩa package/type ở đường tìm kiếm phù hợp | Kiểm tra JAR/class đã build, classpath compile, gốc package |
| `cannot find symbol: class Message` | Không phân giải được tên ở vị trí dùng | Kiểm tra import, package, source/classpath và typo |
| `class file for X not found` | Đang thiếu thông tin của một kiểu phụ thuộc, có thể là transitive dependency | Kiểm tra dependency gián tiếp và phiên bản JAR |
| `Error: Could not find or load main class demo.app.Main` | Launcher không tìm/nạp được main class | Kiểm tra `-cp` chứa `out/app`, tên binary class và class file |
| `NoClassDefFoundError: demo/lib/Message` | Một class cần lúc chạy không khả dụng hoặc không thể định nghĩa/nạp | Kiểm tra runtime classpath, đóng gói; đọc nguyên nhân gốc trong stack trace |
| `NoSuchMethodError` | Class lúc chạy không có method/chữ ký bytecode dự kiến | Kiểm tra JAR version, class trùng tên, binary compatibility |
| Chạy trong IDE được, terminal lỗi | IDE bổ sung source/classpath/module path tự động | Đọc lệnh compiler/launcher thực tế hoặc cấu hình run của IDE |
| Dùng `-cp lib` mà không thấy class bên trong `lib/a.jar` | Thư mục classpath không tự bung JAR | Dùng `-cp lib/a.jar` hoặc `-cp "lib/*"` |
| Source/package “đúng” nhưng compiler vẫn không tìm được | Gốc đường dẫn sai hoặc sai chữ hoa/thường | Đảm bảo `package demo.lib` khớp đường dẫn dưới classpath/source root |
| Máy này build được, máy khác lỗi | Environment classpath, JDK, output cũ, timestamp, dependency khác | Cấu hình toolchain, đường dẫn tường minh, build sạch |

Một `ClassNotFoundException` thường được API nạp class báo khi không tìm thấy tên class được yêu cầu; `NoClassDefFoundError` là lỗi liên kết/định nghĩa class tại runtime và có thể có nguyên nhân khác ngoài “thiếu JAR”. Phải đọc chuỗi nguyên nhân đầy đủ thay vì chỉ nhìn một dòng lỗi.

## 15. Cách debug đường tìm kiếm của `javac`

Khi compiler không tìm thấy type, đi theo quy trình:

1. **Ghi tên đầy đủ của type.** `demo.lib.Message` khác `Message`; kiểm tra `package` và `import`.
2. **Xác định file chứa class.** Đó là `out/lib/demo/lib/Message.class`, `lib/message.jar` hay `libsrc/demo/lib/Message.java`?
3. **Kiểm tra gốc đường dẫn.** Entry phải là `out/lib` hoặc `lib/message.jar`, không phải thư mục package cuối.
4. **Xem đầy đủ compiler command.** Chú ý `-cp`, `-sourcepath`, `--module-path`, `--release`, thư mục làm việc và Java toolchain.
5. **Kiểm tra thứ tự/các class trùng nhau.** Nếu nhiều JAR chứa cùng một binary name, cần biết phiên bản compiler chọn.
6. **Kiểm tra source và class cũ.** Một class file từ build trước hoặc một source mới hơn có thể thay đổi quyết định của compiler.
7. **Bật log compiler khi cần.** `javac -verbose` in thông tin những file được parse/load/write; diagnostic có thể khác theo JDK, không dùng log như output cố định.
8. **Biên dịch lại trong output sạch.** Tránh sử dụng class files còn sót như bằng chứng rằng lần biên dịch hiện tại tạo được dependency.
9. **Chạy với runtime classpath được khai báo rõ.** Đừng suy ra classpath runtime từ classpath compile.

Ví dụ để kiểm tra class trong JAR:

```bash
jar --list --file out/message.jar
```

Ví dụ để kiểm tra bytecode, sau khi có đúng classpath:

```bash
javap -classpath out/message.jar demo.lib.Message
```

`javap` đọc khai báo từ class file; không thay thế compiler và cũng không chứng minh JVM runtime sẽ chọn đúng JAR khi classpath khác nhau.

Nếu nghi ngờ class nạp từ vị trí không mong muốn, Java launcher có thể in log nạp lớp với `-Xlog:class+load=info` trên JDK hỗ trợ unified logging; lượng log rất lớn nên chỉ dùng để chẩn đoán và lọc đúng tên lớp quan tâm.

## 16. Các lỗi tổ chức mã nguồn liên quan classpath

**Sai cấp thư mục:** đặt `demo/lib/Message.class` vào `out/lib/demo/lib` rồi thêm `out/lib/demo` vào classpath. Compiler sẽ tìm `out/lib/demo/demo/lib/Message.class` và thất bại. Sửa entry về `out/lib`.

**Tưởng package được suy từ folder:** chỉ tạo file `src/demo/lib/Message.java` nhưng nội dung khai báo `package other;`. Đường tìm kiếm dựa vào tên package được khai báo, không chỉ tên folder nhìn thấy trong IDE. Source path và package phải nhất quán theo cấu trúc dự án.

**Thư viện chưa được build:** `import` viết đúng nhưng `.class`/JAR không tồn tại. Cần biên dịch dependency hoặc đưa artifact phù hợp vào classpath trước.

**Thiếu phụ thuộc bắc cầu:** một thư viện có thể chứa method dùng một kiểu khác trong chữ ký hay supertypes. Compiler cần truy cập đủ metadata của kiểu liên quan ngay cả khi source của ứng dụng không nhắc trực tiếp kiểu đó.

**Compile/runtime lệch phiên bản:** biên dịch bằng JDK mới hoặc JAR mới, runtime lại dùng class/JVM cũ. `UnsupportedClassVersionError` có thể chỉ ra class file yêu cầu JVM mới hơn; `NoSuchMethodError` có thể chỉ ra dependency binary không khớp.

**Dùng đường dẫn tương đối ở sai working directory:** `-cp lib/a.jar` phụ thuộc thư mục làm việc khi gọi lệnh. Scripts CI/IDE chạy ở thư mục khác sẽ trỏ tới file khác hoặc không tồn tại.

**Dựa vào classpath toàn cục:** biến `CLASSPATH` làm lệnh trên máy người viết chạy được nhưng có thể không tồn tại ở CI. Build tool nên tạo classpath một cách lặp lại và minh bạch.

## 17. Classpath trong Maven và Gradle

Maven và Gradle cung cấp mô hình dependency cao hơn mức `javac -cp`. Chúng resolve artifact, phiên bản, dependency bắc cầu, source set và task; sau đó cung cấp classpath phù hợp cho compiler/test runner/launcher.

Ví dụ Maven (một thư viện chỉ để minh họa cú pháp dependency):

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

Ví dụ Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Các ví dụ cấu hình chỉ minh họa cách khai báo dependency, **không phải** phần cần thiết để chạy chương trình `Message`/`Main` bên trên. Version thực tế phải được chọn theo dự án và kiểm tra tính tương thích với JDK.

Các configuration như `implementation`, `compileOnly`, `runtimeOnly`, `testImplementation` trong Gradle có ý nghĩa khác nhau. Chẳng hạn dependency chỉ có trong compile classpath có thể không hiện diện khi chạy nếu runtime không được cấu hình tương ứng. Maven cũng phân biệt scopes như `compile`, `provided`, `runtime` và `test`. Những lựa chọn này tác động tới classpath đầu ra của từng bước, không phải chỉ tới việc IDE hiển thị import.

Dùng cơ chế của build tool để xem dependency tree và classpath của task thay vì tự nối JAR vào các task tùy tiện, nhất là ở dự án lớn.

## 18. Câu hỏi tự luyện có đáp án

**1.** `demo.lib.Message` nằm ở `build/classes/demo/lib/Message.class`. Entry nào phải thêm vào classpath? **`build/classes`**, vì nó là gốc chứa đường dẫn package.

**2.** Vì sao `import demo.lib.Message;` không sửa được lỗi thiếu `Message.class`? Vì `import` chỉ hỗ trợ phân giải tên ở source, không tự tạo hay tải thư viện.

**3.** Compile `Main.java` bằng `-cp out/lib` thành công, nhưng `java -cp out/app demo.app.Main` thất bại. Vì sao? Runtime classpath thiếu `out/lib`; compiler và launcher là hai lệnh độc lập.

**4.** `-d out/app` có tự đưa `out/app` vào compile classpath không? **Không.** Nó là output directory. Khi cần tìm các class đã biên dịch, phải khai báo classpath phù hợp.

**5.** `-cp lib` có tự tìm mọi `lib/*.jar` không? **Không.** Dùng một JAR cụ thể hoặc `"lib/*"` nếu muốn mở rộng những JAR trực tiếp trong thư mục.

**6.** Nếu không cấu hình `-sourcepath`, compiler có thể tìm source ở đâu? Với chương trình dùng classpath, `javac` có thể tìm cả `.java` trên user classpath.

**7.** `-implicit:none` có ngăn compiler đọc mọi `.java` từ source path không? **Không.** Nó điều khiển việc sinh class file cho nguồn phát hiện ngầm.

**8.** Vì sao hai phiên bản của cùng một class nằm ở hai JAR là nguy cơ? Thứ tự tìm kiếm và sự khác nhau giữa compile/runtime classpath có thể làm compiler/JVM chọn định nghĩa khác dự kiến.

**9.** Vì sao lớp `java.lang.String` không cần một `string.jar` trong `-cp`? Vì class nền tảng được cung cấp qua runtime/platform modules của JDK.

**10.** Khi chương trình có `module-info.java`, chỉ thêm JAR vào `-cp` đã đủ chưa? Không thể khẳng định; named module còn có module readability và package exports, nên cần xét `--module-path` và descriptor.

## 19. Nguyên tắc nhớ lâu

Để compiler tìm được kiểu, cần xác định **tên đầy đủ của kiểu**, **nơi lưu định nghĩa của kiểu**, và **đường tìm kiếm tương ứng**. Classpath entry là gốc package hoặc JAR, `-sourcepath` dành cho source bổ sung, `-d` dành cho output; chúng không thay thế nhau. `javac` cần dependency ở **compile time**, còn `java` cần dependency ở **runtime**. Khi khác biệt xuất hiện, hãy kiểm tra đúng lệnh, gốc thư mục, thứ tự các entry, bản JAR và output sạch.

Tham khảo chính thức:

- [`javac` JDK 21 — Configuring a Compilation / Searching for Module, Package and Type Declarations](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [`java` JDK 21 — Java Application Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [JLS `7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html).
- [JLS `6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html).
