# Thu nhỏ ví dụ lỗi và so sánh cấu hình IDE với dòng lệnh

## Mục tiêu

Sau bài học, bạn có thể:

1. Biến một lỗi Java chỉ xảy ra trong dự án lớn thành **ví dụ tái hiện tối thiểu** (*minimal reproducible example*, MRE) mà người khác chạy lại được.
2. Phân biệt lỗi lúc **biên dịch**, **khởi động/nạp lớp**, **thực thi** và **kiểm thử** trước khi lựa chọn công cụ chẩn đoán.
3. So sánh môi trường hiệu lực trong IDE với terminal: **JDK/javac**, release level, classpath/module path, dependency, annotation processor, working directory, argument, encoding, biến môi trường và thư mục output.
4. Tái hiện một trường hợp **IDE chạy được nhưng lệnh `javac`/`java` thất bại** vì phụ thuộc chỉ có ở classpath của IDE; sửa bằng cách khai báo đầu vào đầy đủ thay vì chữa triệu chứng.
5. Lập báo cáo lỗi có lệnh chạy, đầu ra, phiên bản công cụ và thay đổi nhỏ nhất để chứng minh nguyên nhân.

Bài học sử dụng Java 17+, shell và trình soạn thảo văn bản. IDE có thể là IntelliJ IDEA, Eclipse hoặc VS Code với Java extensions; tên tùy chọn cụ thể giữa các IDE có thể khác, nhưng nguyên tắc kiểm chứng vẫn giống nhau.

## 1. Chẩn đoán bằng bằng chứng, không bằng phỏng đoán

Một câu như “trong IDE chạy được nhưng terminal lỗi” mô tả **triệu chứng**, chưa cho biết nguyên nhân. IDE thường làm nhiều việc thay bạn: chọn compiler, xác định nguồn, resolve dependency, tạo output, truyền runtime classpath, chọn working directory, chạy annotation processor và có thể ủy quyền build cho Gradle/Maven. Terminal chỉ thực hiện đúng những lệnh, biến môi trường và đường dẫn mà bạn cung cấp.

Vì vậy, hai nút “Run” và câu lệnh `java App` chưa chắc là hai lần thực thi cùng một chương trình trong cùng một môi trường.

Cách tiếp cận tốt là kiểm tra một giả thuyết có thể bị bác bỏ:

- Giả thuyết: “Terminal thiếu class của module thư viện”.
- Bằng chứng kiểm tra: Biên dịch thư viện vào output riêng, thêm output đó vào compile classpath và runtime classpath.
- Kết quả mong đợi: Compiler hết báo `package ... does not exist` và JVM chạy ra kết quả định trước.
- Điều không thể suy ra: “Mọi khác biệt giữa IDE và terminal đều do classpath”.

Mục tiêu của MRE là **giữ đủ thành phần để lỗi còn tái hiện**, đồng thời loại bỏ yếu tố không liên quan cho đến khi bạn chỉ còn một khác biệt quyết định.

## 2. Phân loại lỗi theo thời điểm phát sinh

| Giai đoạn | Dấu hiệu thường gặp | Câu hỏi cần đặt |
| --- | --- | --- |
| **Compile-time** | `cannot find symbol`, `package ... does not exist`, `incompatible types`, `release version ... not supported` | Đúng source, đúng compiler, đúng release và compile classpath chưa? |
| **Launch/class loading** | `Could not find or load main class`, `ClassNotFoundException`, `NoClassDefFoundError` | Tên lớp đầy đủ và runtime classpath/module path có đúng không? |
| **Linkage/runtime** | `NoSuchMethodError`, `UnsupportedClassVersionError`, exception từ ứng dụng | Bytecode/dependency nào được JVM nạp? Runtime có tương thích không? |
| **Test-time** | Assertion fail, lỗi fixture, test pass trong IDE nhưng fail CI | Cùng test engine, dữ liệu, timezone, working directory và cấu hình không? |
| **Build-tool/configuration** | Task không tìm thấy, dependency resolve fail, output không mới | IDE có delegate build sang Gradle/Maven không? Build profile/toolchain nào đang hoạt động? |

Không phải mọi exception xuất hiện lúc chạy đều là “lỗi runtime classpath”. Ví dụ, `NullPointerException` trong nghiệp vụ và `NoClassDefFoundError` do thiếu dependency yêu cầu hai chiến lược điều tra rất khác nhau.

**Quy tắc đầu tiên:** lưu nguyên văn lệnh vừa chạy, lỗi đầu tiên có ý nghĩa, exit code, phiên bản compiler/runtime và thư mục hiện tại. Đừng chỉ chụp dòng cuối của stack trace.

## 3. MRE là gì và như thế nào là đủ nhỏ?

Một MRE tốt có bốn thuộc tính:

- **Minimal:** chỉ giữ source, cấu hình, dependency, input và thao tác thực sự cần để lỗi xuất hiện.
- **Reproducible:** có lệnh hoặc quy trình rõ ràng để người khác chạy lại từ trạng thái sạch.
- **Complete:** không phụ thuộc vào một file/JAR bí mật, biến môi trường chưa mô tả hoặc trạng thái IDE mà người nhận không có.
- **Observable:** có expected behavior, actual behavior hoặc diagnostic đặc trưng để biết lỗi còn xảy ra.

MRE không đồng nghĩa với việc ép mọi lỗi còn một file. Nếu lỗi do khác biệt classpath giữa hai module, **hai source file và hai output directory** có thể là MRE nhỏ nhất giữ được nguyên nhân. Việc bỏ module thư viện chỉ để “cho ngắn” sẽ đánh mất chính lỗi cần kiểm tra.

### 3.1 Quy trình thu nhỏ có kiểm soát

1. **Đóng băng triệu chứng:** ghi tên test/method, câu lệnh, stack trace hoặc compiler diagnostic, expected và actual.
2. **Tạo bản sao để điều tra:** làm việc trong project nhỏ hoặc nhánh riêng; không phá source chính để thử giả thuyết.
3. **Xác định pha lỗi:** compile, launch, link, chạy logic hay test.
4. **Loại bỏ theo nhóm:** thử bỏ từng framework/config không cần thiết, file không liên quan, annotation, resource, module hoặc lớp trung gian.
5. **Sau mỗi lần loại bỏ, chạy lại:** nếu lỗi mất, khôi phục phần vừa bỏ hoặc chia nhỏ phần ấy; nếu lỗi còn, giữ phiên bản đơn giản hơn.
6. **Cố định môi trường:** nêu chính xác JDK, compiler options, dependency và bước xây dựng output.
7. **Kiểm thử giả thuyết bằng một thay đổi:** ví dụ chỉ thêm output thư viện vào classpath, không đồng thời đổi JDK và sửa source.
8. **Giữ cả bản lỗi và bản sửa:** để thấy điều kiện nào làm vấn đề xuất hiện/biến mất.

Mô hình quyết định:

~~~text
Lỗi còn tái hiện với dữ liệu/logic hiện tại?
        |
        +-- Không --> Khôi phục phần vừa loại bỏ, tìm ranh giới gây lỗi
        |
        +-- Có ----> Có thể bỏ thêm một thành phần không liên quan?
                          |
                          +-- Có --> Bỏ rồi chạy lại
                          |
                          +-- Không --> Ghi nhận MRE và xác minh từ build sạch
~~~

Đây là kỹ thuật **delta debugging** ở mức thủ công. Với bug xảy ra ngẫu nhiên, cần ghi thêm seed, số lần thử, concurrency, scheduler và điều kiện môi trường; đừng tuyên bố “đã hết lỗi” chỉ vì một lần không tái hiện.

### 3.2 Đừng làm mất điều kiện gây lỗi

Ví dụ lỗi chỉ xuất hiện sau khi đổi version JAR: nếu thu nhỏ bằng cách xóa JAR đó và thay bằng code mock không tương đương, MRE có thể chạy bình thường nhưng không còn đại diện cho vấn đề ban đầu.

Với lỗi chỉ trong IDE, cần giữ ít nhất phần thông tin về **IDE run/build configuration** tạo khác biệt. Với lỗi file path, cần giữ relative path và working directory; với lỗi encoding, cần giữ byte/encoding và lệnh đọc file.

### 3.3 Ghi actual, expected và mức độ chắc chắn

Một mẫu ghi nhận:

~~~text
Môi trường: JDK 17, terminal tại thư mục gốc dự án
Lệnh: javac --release 17 -cp out/empty -d out/app src/app/Main.java
Expected (giả thuyết đã khai báo đủ dependency): compile thành công
Actual: lỗi package lib does not exist / cannot find symbol
Kiểm tra: output lib chứa lib/Greeter.class; compile classpath hiện tại thiếu out/lib
Kết luận: thiếu compile-time dependency trong lệnh tái hiện
~~~

Kết luận trên chỉ hợp lý sau khi thử thêm đúng dependency và quan sát kết quả. Một compiler diagnostic đơn lẻ không chứng minh được mọi nguyên nhân có thể có.

## 4. Tạo MRE: lỗi classpath giữa IDE và terminal

Ví dụ gồm **hai file Java 17+** và không dùng thư viện bên thứ ba. Ý tưởng: một IDE có thể tự thêm output của module thư viện vào classpath khi biết quan hệ module; còn lệnh terminal chỉ compile module ứng dụng nên báo không tìm thấy package.

### 4.1 Cấu trúc project

Tạo project `ide-cli-repro`:

~~~text
ide-cli-repro/
├── src/
│   ├── lib/
│   │   └── Greeter.java
│   └── app/
│       └── Main.java
└── out/
    ├── lib/
    ├── app/
    └── empty/
~~~

Ba thư mục `out` là output tách biệt; chúng phải được tạo mới và giữ rõ mục đích. Từ thư mục gốc project, tạo thư mục nếu chưa có:

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force src/lib, src/app, out/lib, out/app, out/empty | Out-Null
~~~

**Bash/Zsh:**

~~~bash
mkdir -p src/lib src/app out/lib out/app out/empty
~~~

Nếu source đã tồn tại, lệnh `-Force` hoặc `-p` không tự xóa nội dung source. Thí nghiệm sạch nhất là thực hiện trong một project mới.

### 4.2 Source thư viện: `src/lib/Greeter.java`

~~~java
package lib;

public final class Greeter {
    private Greeter() {
    }

    public static String message(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

File có một top-level public class `Greeter` và tên package `lib`. Compiler sẽ sinh `lib/Greeter.class` dưới output root.

### 4.3 Source ứng dụng: `src/app/Main.java`

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Greeter.message(name));
    }
}
~~~

`Main` tham chiếu `lib.Greeter`. Compiler phải biết ký hiệu đó từ **source được cung cấp** hoặc **class file/JAR trên compiler classpath**.

### 4.4 Tái hiện lỗi khi chỉ compile ứng dụng

Trước khi biên dịch thư viện, đứng ở gốc project và chạy:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java
~~~

Khi `out/empty` không có `lib/Greeter.class` và không có nguồn `lib` trên đường tìm kiếm compiler, lệnh sẽ thất bại. Diagnostic thường có ý nghĩa:

~~~text
package lib does not exist
cannot find symbol
~~~

Đừng chép nguyên cả stderr này thành “output chắc chắn”: định dạng, số dòng và vị trí dấu mũ phụ thuộc JDK. Điều ổn định là **lệnh không biên dịch thành công vì `lib.Greeter` không resolve được**.

Nếu IDE của bạn chạy dự án tương đương và tự động build module `lib`, nó có thể hoàn tất vì IDE cung cấp thêm dependency mà lệnh terminal chưa có. Không phải IDE “thông minh hơn compiler” về cú pháp; **tập đầu vào khác nhau**.

### 4.5 Sửa nguyên nhân bằng compile classpath đúng

Trước tiên compile thư viện:

~~~bash
javac --release 17 -encoding UTF-8 -d out/lib src/lib/Greeter.java
~~~

Sau đó compile ứng dụng với dependency được khai báo:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

`-cp out/lib` là **compiler classpath**, còn `-d out/app` là **thư mục đầu ra** của ứng dụng. Không nhầm hai vai trò này. Class file có cấu trúc:

~~~text
out/
├── lib/
│   └── lib/
│       └── Greeter.class
└── app/
    └── app/
        └── Main.class
~~~

Phần `lib/lib` không phải lỗi: `out/lib` là **output root**, còn `lib/Greeter.class` là package-relative path.

### 4.6 Chạy trên Linux/macOS

~~~bash
java -cp "out/app:out/lib" app.Main Minh
~~~

Stdout:

~~~text
Xin chao, Minh!
~~~

### 4.7 Chạy trên Windows

Trong PowerShell hoặc CMD:

~~~powershell
java -cp "out/app;out/lib" app.Main Minh
~~~

Stdout vẫn là:

~~~text
Xin chao, Minh!
~~~

Dấu phân cách **nhiều entry classpath** trên Linux/macOS là dấu hai chấm (`:`), trên Windows là dấu chấm phẩy (`;`). Tên lớp `app.Main` không chứa dấu slash và không có hậu tố `.class`.

### 4.8 Chỉ cung cấp runtime classpath của ứng dụng: lỗi khác

Bây giờ chạy:

~~~bash
java -cp out/app app.Main Minh
~~~

Lúc này JVM tìm thấy `app.Main` nhưng không tìm thấy `lib.Greeter` khi cần dùng. Thường xuất hiện `NoClassDefFoundError: lib/Greeter` với nguyên nhân liên quan `ClassNotFoundException`. Stack trace cụ thể không phải phần output cố định của bài.

**So sánh hai lỗi:**

- `javac ... -cp out/empty ...`: thiếu dependency **khi biên dịch**, thường `package ... does not exist`.
- `java -cp out/app app.Main`: thiếu dependency **khi chạy**, thường `NoClassDefFoundError`.

IDE có thể cấu hình compile classpath đúng nhưng run configuration lại dùng runtime classpath thiếu thư viện, hoặc ngược lại. Vì vậy cần kiểm tra **cả hai**.

## 5. Phân tích MRE: cái gì là tối thiểu, cái gì không?

Trong ví dụ trên, ta có thể bỏ hệ thống logging, framework, file cấu hình, test runner và các class unrelated, nhưng cần giữ:

- `Greeter.java`: định nghĩa dependency.
- `Main.java`: code có lời gọi tới dependency.
- Ít nhất **hai cấu hình compile classpath**: thiếu `out/lib` và có `out/lib`.
- Runtime classpath riêng để cho thấy lỗi ở pha nạp lớp.
- Lệnh compile và output root để người khác không chạy nhầm class cũ.

Bỏ hẳn `Greeter` và tạo một method cùng tên trong `Main` sẽ không còn chứng minh điều cần tìm. MRE phải đủ nhỏ **nhưng vẫn giữ quan hệ nhân quả**.

### 5.1 Vì sao cần output sạch?

Một output directory đã từng chứa `lib/Greeter.class` có thể khiến lần compile mới tình cờ thành công nếu classpath trỏ tới nó. Khi chẩn đoán thiếu dependency, hãy tạo **output mới** và dùng một classpath chỉ gồm đầu vào dự kiến.

Tương tự, nếu bạn biên dịch `Main` rồi sửa source nhưng không build lại, lệnh `java` có thể đang chạy bytecode cũ. Đây là nguyên nhân phổ biến của “IDE đã sửa rồi nhưng terminal vẫn in kết quả cũ”.

Không phải cứ xóa toàn bộ workspace mới có build sạch. Hãy chỉ dọn **thư mục output được phép dọn**; không xóa source, cache hệ thống hoặc thư mục dùng chung một cách mù quáng. Trong bài thực hành, dùng một project và các output directory mới ngay từ đầu giúp tránh thao tác xóa nguy hiểm.

### 5.2 Khi nào một file mới là MRE đúng?

Nếu lỗi chỉ là `NullPointerException` do một biến null trong method, MRE một file thường đủ. Nếu lỗi do **hai bản JAR cùng tên class** hoặc **resource path của IDE**, cần giữ cấu trúc tối thiểu tương ứng. Kích thước nhỏ nhất là mức **không thể bỏ thêm mà lỗi vẫn đúng với nguyên nhân cần khảo sát**, không phải mục tiêu đếm số dòng.

## 6. So sánh cấu hình IDE và terminal theo ma trận

Hãy so sánh **giá trị hiệu lực**, không chỉ tên setting. Một IDE có thể có Project SDK, Module SDK, Gradle JVM, compiler compliance level và Run Configuration JRE là những mục khác nhau.

| Trục kiểm tra | Trong IDE nên xác minh | Ở terminal nên xác minh | Sai khác gây ra |
| --- | --- | --- | --- |
| **JDK của compiler** | SDK/toolchain dùng lúc build, có delegate build không | `javac -version`; executable của `javac` | Tính năng ngôn ngữ/API khác; compiler không hỗ trợ cờ |
| **JVM chạy ứng dụng** | JRE/JDK trong Run Configuration | `java -version`; executable được gọi | `UnsupportedClassVersionError` hoặc khác behavior |
| **Source/release/target** | Language level, compiler release/compliance | `javac --release 17 ...`, flags thực tế | Source compile một nơi nhưng lỗi nơi khác |
| **Compile classpath** | Module dependencies, external libraries, generated classes | `javac -cp ...` / `--class-path` | `package ... does not exist`, `cannot find symbol` |
| **Runtime classpath** | Run configuration, module/JAR selection | `java -cp ...` / `java -jar ...` | `NoClassDefFoundError`, nạp version sai |
| **Module path** | Java module dependencies, run config | `--module-path`, `--module`, `--add-modules` khi phù hợp | Module không đọc/không export package |
| **Annotation processors** | Bật/tắt processors, processor path, generated sources | `-processorpath`, `-processor`, `-proc:none`, build tool | Class/generated code thiếu hoặc khác |
| **Output/build cache** | Build/rebuild, source set, incremental output | `-d`, clean output, đường dẫn class được nạp | Tệp `.class` cũ che lỗi |
| **Working directory** | Working directory của Run Configuration | `pwd`/`Get-Location` | File tương đối không tìm thấy |
| **Arguments** | Program arguments vs VM options | Các đối số sau main class; flags trước main class | Đầu vào khác; flag bị hiểu thành data |
| **Environment** | Environment variables, profile, credentials | `PATH`, `JAVA_HOME` và biến liên quan | Chạy khác resource/service |
| **Encoding/locale/timezone** | Editor encoding, file encoding, VM properties | `-encoding UTF-8`; console locale/settings | Ký tự tiếng Việt hỏng, sort/date khác |
| **Build tool/profile** | IDE build nội bộ hay gọi Maven/Gradle | `mvn ...` / `gradlew ...`; profiles/tasks | Hai pipeline xử lý các đầu vào khác nhau |

Không phải mục nào cũng cần so ngay. Hãy ưu tiên theo pha lỗi: compiler báo symbol thiếu thì kiểm tra compiler options và compile classpath; ứng dụng chỉ lỗi khi đọc file thì kiểm tra working directory/file content trước.

## 7. Lấy bằng chứng compiler và runtime đang được dùng

### 7.1 Windows PowerShell

~~~powershell
Get-Location
Get-Command java
Get-Command javac
java -version
javac -version
~~~

`Get-Command` giúp thấy đường dẫn executable được shell resolve. Một bản JDK do IDE chọn có thể **khác** bản được tìm qua `PATH` trong terminal.

### 7.2 Linux/macOS Bash/Zsh

~~~bash
pwd
command -v java
command -v javac
java -version
javac -version
~~~

Nếu có nhiều JDK, hãy ghi đường dẫn đầy đủ tới `java` và `javac` của mỗi môi trường. `JAVA_HOME` hữu ích nhưng không bảo đảm lệnh `java` trong `PATH` sử dụng chính thư mục đó.

### 7.3 Chụp cấu hình Java runtime

~~~bash
java -XshowSettings:properties -version
~~~

Lệnh này in thông tin runtime như `java.home`, `java.version`, `java.class.path`, `file.encoding`, `user.dir` và các property khác (tùy JDK), thường ra stderr. Khi chia sẻ log, **lọc thông tin nhạy cảm** như tên tài khoản, đường dẫn cá nhân hoặc token có trong cấu hình môi trường.

Với chương trình Java, cũng có thể kiểm tra một property cụ thể:

~~~java
System.out.println(System.getProperty("user.dir"));
System.out.println(System.getProperty("java.class.path"));
~~~

Hai dòng trên là **đoạn mã minh họa trong method**; giá trị in ra phụ thuộc nơi chương trình được chạy và classpath thực tế, không có stdout chung cố định.

### 7.4 Chẩn đoán compiler chi tiết hơn

~~~bash
javac -Xdiags:verbose --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java
~~~

`-Xdiags:verbose` làm diagnostic chi tiết hơn ở những tình huống compiler hỗ trợ. `javac -verbose` giúp thấy compiler đang nạp và ghi những source/class file nào, nhưng output có thể dài:

~~~bash
javac -verbose --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

Khi đang nghi ngờ một class cũ, danh sách file mà compiler **loading** từ đâu có giá trị hơn việc chỉ nhìn thông báo “build successful”.

### 7.5 Chẩn đoán nguồn class ở runtime

Trên HotSpot có unified logging (như nhiều bản JDK 17+), có thể dùng:

~~~bash
java -Xlog:class+load=info -cp "out/app:out/lib" app.Main Minh
~~~

Lệnh trên dùng **classpath separator của Linux/macOS**; trên Windows đổi sang `"out/app;out/lib"`. Log class loading rất dài và chi tiết phụ thuộc JVM. Hãy tìm đường dẫn/source của `app.Main` và `lib.Greeter`, không học thuộc từng dòng log.

Với chương trình có nhiều class trùng tên trong các JAR, thông tin nơi nạp class giúp kiểm chứng liệu runtime dùng đúng version dependency không.

## 8. MRE thứ hai: working directory khác nhau

Không phải mọi khác biệt IDE/CLI là classpath. IDE Run Configuration có thể đặt working directory là thư mục project, module hoặc một thư mục khác; terminal dùng thư mục bạn đang `cd` tới.

Tạo file **`src/WorkingDirDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class WorkingDirDemo {
    public static void main(String[] args) throws Exception {
        Path config = Path.of("settings.txt");
        System.out.println(Files.readString(config).strip());
    }
}
~~~

Tạo file **`settings.txt`** ngay ở **gốc project** với đúng nội dung:

~~~text
mode=demo
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 -d out/app src/WorkingDirDemo.java
~~~

Chạy từ **gốc project**:

~~~bash
java -cp out/app WorkingDirDemo
~~~

Stdout:

~~~text
mode=demo
~~~

Nếu IDE chạy cùng class nhưng working directory là thư mục khác không chứa `settings.txt`, chương trình có thể báo `NoSuchFileException: settings.txt`. Bytecode và JDK vẫn giống nhau; nguyên nhân là **đường dẫn tương đối được resolve dựa trên working directory**, không phải vị trí file source.

**Cách kiểm tra:** xem working directory trong Run Configuration; ở terminal chạy `pwd` hoặc `Get-Location`. Nếu mục đích là đọc file bên ngoài, hãy khai báo đường dẫn rõ ràng và xử lý lỗi file thiếu. Nếu mục đích là resource đóng gói trong JAR, nên dùng classpath resource API thay vì mặc định đó là file nằm cạnh source.

### Đường dẫn đến class không tự đặt working directory

Dù bạn chạy:

~~~bash
java -cp out/app WorkingDirDemo
~~~

thì `out/app` là nơi launcher tìm class, **không tự làm `user.dir` đổi thành `out/app`**. Đây là hai khái niệm độc lập.

### Lưu ý về encoding

`Files.readString(Path)` đọc file theo UTF-8 trong ví dụ Java 17. `javac -encoding UTF-8` điều khiển cách compiler giải mã **mã nguồn**; nó không thay nội dung hoặc vị trí `settings.txt`. Đừng cố sửa `NoSuchFileException` bằng cách thay source encoding.

## 9. MRE thứ ba: source level và JDK không thống nhất

Tạo file **`src/LanguageProbe.java`**:

~~~java
public class LanguageProbe {
    public static void main(String[] args) {
        var total = 4 + 5;
        System.out.println(total);
    }
}
~~~

`var` cho local variable type inference từ Java 10. Biên dịch bằng JDK 17+ với release 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out/app src/LanguageProbe.java
java -cp out/app LanguageProbe
~~~

Stdout:

~~~text
9
~~~

Thử mục tiêu Java 8:

~~~bash
javac --release 8 -encoding UTF-8 -d out/empty src/LanguageProbe.java
~~~

Compiler sẽ từ chối dùng `var` theo cấp ngôn ngữ Java 8; diagnostic cụ thể tùy JDK. Nếu IDE cấu hình language level 17 nhưng command line của build tool nhắm Java 8, hành vi khác nhau là hợp lý.

Lưu ý: thư mục `out/empty` ở lệnh này chỉ là output thử nghiệm; nó không ảnh hưởng tới bản `LanguageProbe.class` đã build ở `out/app`. Một kết quả chạy được từ class cũ **không chứng minh** câu lệnh compile Java 8 vừa thành công.

### `-source/-target` khác `--release`

Nếu compiler chạy trên JDK mới hơn runtime đích, chỉ đặt source/target có thể không đủ để ràng buộc **Java platform APIs**. Ví dụ code có cú pháp Java 17 nhưng gọi API chỉ có trong Java 21 có thể biên dịch khi dùng compiler JDK 21 với `-source 17 -target 17`, dù chạy trên JVM 17 sẽ lỗi linkage. `--release 17` mới yêu cầu compiler kiểm tra cấp ngôn ngữ, platform API Java 17 và class-file target 17.

Khi so cấu hình IDE và terminal, hãy ghi rõ **cả bản javac lẫn flags**. Không dùng mỗi con số “language level” để suy ra đúng runtime compatibility.

## 10. Annotation processor, generated sources và build pipeline

Có những lỗi không tái hiện khi bạn chỉ copy source vào một file Java vì project thật dùng **annotation processing hoặc code generation**.

Ví dụ một thư viện có thể sinh source phụ từ annotation lúc compile; IDE bật annotation processor còn `javac` thủ công không có processor trên processor path. Lúc đó một class generated sẽ không tồn tại.

Các điểm cần kiểm tra:

1. Processor có được bật trong IDE/build tool không?
2. Processor artifact có nằm trên **processor path** hoặc cấu hình annotation-processing phù hợp không?
3. Generated source được ghi vào đâu?
4. Compiler đang đọc **generated source mới** hay artifact cũ?
5. Có phần source nào do build step chạy **trước** `javac` tạo ra không?

Tùy chọn `javac -proc:none` vô hiệu hóa annotation processing ở những compiler hỗ trợ. Nó hữu ích như một **phép thử cô lập nguyên nhân**, nhưng không phải cách sửa nếu ứng dụng thật cần generated classes.

Ví dụ minh họa sự khác biệt về lệnh:

~~~bash
javac -proc:none --release 17 -d out/app src/app/Main.java
~~~

Lệnh này thuộc dạng mẫu so sánh cờ; với MRE `app.Main`, bạn vẫn cần compile classpath `out/lib` để resolve `lib.Greeter`. Không nên chạy nó rồi kết luận annotation processor là nguyên nhân của lỗi classpath đang thử.

**Không nhầm:** một annotation như `@Override` không tự đòi hỏi annotation processor. Chỉ các processor được cấu hình và được kích hoạt trong quá trình build mới tham gia sinh source/class theo cơ chế tương ứng.

### Khi nào cần giữ framework/build tool trong MRE?

Nếu lỗi xuất phát từ code generator, plugin, processor hoặc dependency resolution, MRE tối thiểu **có thể phải giữ** một `pom.xml`/`build.gradle` thu gọn cùng đúng version công cụ. Một file `Main.java` không tái hiện vấn đề về build task order hoặc generated sources.

Mục tiêu không phải loại bỏ mọi công cụ, mà là **giữ đúng phần công cụ cần để lỗi vẫn tái hiện**.

## 11. IDE build khác build tool trong terminal

Một IDE có thể:

- Biên dịch bằng compiler nội bộ hoặc gọi chính `javac` của JDK mà IDE đã chọn.
- Delegate build/run/test sang Gradle.
- Import Maven model nhưng sử dụng cấu hình run/test riêng.
- Có cache/incremental build, generated sources và module output directory.

Vì thế, câu hỏi “IDE có cùng cấu hình với `javac` không?” đôi khi chưa đủ; cần xác định **IDE thực sự chạy compiler nào và bằng task/flags nào**.

### 11.1 Với Gradle

Một dự án Gradle Java thường có những yếu tố: Java toolchain, `JavaCompile` tasks, `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, `sourceSets` và các task thực thi. Nếu IDE delegate sang Gradle thì log của Gradle là nguồn quan trọng để tìm compiler task và đầu vào.

Ví dụ lệnh từ project có Gradle Wrapper:

~~~bash
./gradlew clean classes
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean classes
.\gradlew.bat test
~~~

Các task chỉ tồn tại nếu plugin/build tương ứng cấu hình chúng. `clean` dọn output mà Gradle quản lý, nhưng không tự đảm bảo mọi thư viện ngoài hệ thống hoặc biến môi trường được đồng nhất.

Để xem compiler options trong build script, cần kiểm tra `options.release`, Java toolchain và mọi `options.compilerArgs` liên quan. Đừng tự đoán vì cửa sổ IDE hiện “JDK 17” thì tất cả Gradle tasks đều chạy compiler đó.

### 11.2 Với Maven

Khi project có Maven, có thể so:

~~~bash
mvn clean compile
mvn test
~~~

Kiểm tra effective plugin configuration, Maven Compiler Plugin `release`, dependencies và profiles đang hoạt động. IDE import Maven project có thể tự xây classpath theo model, còn lệnh javac thủ công không tự đọc `pom.xml`.

Ví dụ, lệnh:

~~~bash
javac -d out/app src/app/Main.java
~~~

**không tự tải dependencies được khai báo trong Maven POM**. Để tạo MRE cho một lỗi dependency, cần hoặc dùng Maven build tối giản hoặc tự tạo compile classpath chứa chính xác những dependency cần so sánh.

### 11.3 So sánh hai lần build như một thí nghiệm

Ghi rõ:

| Câu hỏi | IDE | CLI / build tool |
| --- | --- | --- |
| File nguồn được compile? | Module/source set nào | Danh sách file hoặc task nguồn nào |
| Java compiler? | Project SDK/Gradle JVM và task | Đường dẫn `javac` hoặc toolchain |
| Release/source level? | Setting hiệu lực | `--release`, compiler config |
| Compile dependencies? | Module/library mapping | `-cp` hoặc dependency graph |
| Output root? | IDE output directory | `-d` hoặc build output |
| Run JDK? | Run Configuration JRE | Binary `java` đang gọi |
| Program args và VM args? | Các ô cấu hình riêng | Vị trí từng tham số trên command line |
| Working directory? | Working directory setting | `pwd`/`Get-Location` |
| Generated sources? | Processor và output generated | Processor task/path và output |
| Clean hay incremental? | Rebuild/Invalidate policy | Clean output hoặc task clean |

Sau đó thay **một khác biệt quan trọng** ở CLI để xem lỗi biến mất hay không. Việc đồng thời đổi JDK, cache, dependency và working directory sẽ khiến kết quả khó giải thích vì không biết yếu tố nào thực sự quyết định.

## 12. Lệnh chạy và thứ tự tham số cần khớp

Một ví dụ dễ gây hiểu nhầm:

~~~bash
java -cp out/app app.Main Minh
~~~

Trong lời gọi này:

- `-cp out/app` là **tùy chọn launcher** và giá trị classpath.
- `app.Main` là **fully qualified name** của lớp có `main`.
- `Minh` là đối số chương trình, nằm trong `args[0]`.

Nhưng ở:

~~~bash
java app.Main -cp out/app Minh
~~~

sau tên `app.Main`, các token được truyền vào ứng dụng như program arguments. `-cp` không còn cấu hình launcher nữa. Nếu môi trường vốn không có classpath đúng, lệnh có thể không nạp được class hoặc chạy sai với đối số lạ.

Khi so IDE với terminal, cần tách **VM options** khỏi **Program arguments**. Đổi vị trí hai nhóm có thể khiến bạn nghĩ mã thay đổi hành vi mặc dù chỉ đang truyền cấu hình sai thời điểm.

### IDE chạy test thay vì main

Nút “Run Test” có thể gọi JUnit/TestNG hoặc runner của Gradle/Maven, tạo classpath và fixture riêng. Lệnh `java -cp ... app.Main` là chương trình khác về entrypoint. Nếu lỗi chỉ ở test, MRE nên bao gồm **test class và test runner phù hợp**; không thể kết luận từ việc chương trình main chạy bình thường.

## 13. Tránh lỗi “mã đã sửa nhưng terminal vẫn chạy bản cũ”

IDE có thể tự compile khi nhấn Run, còn lệnh `java` thuần túy **không compile `.java`** đang nằm trong project. Nếu bạn sửa `src/app/Main.java` rồi chỉ chạy `java -cp out/app app.Main`, JVM vẫn nạp `Main.class` đã tạo từ lần compile trước.

Quy trình đúng khi source thay đổi:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

Sau đó chạy bằng classpath chứa cả app và lib theo hệ điều hành.

Lưu ý: `java path/to/File.java` có **source-file mode** trên các JDK hỗ trợ, nhưng đó là một cách chạy khác. Đừng âm thầm chuyển giữa `java -cp ... app.Main` và `java src/app/Main.java` trong cùng thí nghiệm mà không ghi lại sự khác biệt; source-file mode có quy tắc và giới hạn riêng về classpath, package và compilation.

### Class cùng tên ở nhiều thư mục

Nếu class `app.Main` xuất hiện cả trong `out/app` và một JAR cũ, Java class loading có thể lựa chọn theo classpath và class loader. Khi một lần chạy in kết quả cũ, hãy kiểm tra class nguồn được nạp bằng log hoặc bằng một marker đơn giản trong ví dụ mới; đừng đoán rằng JVM nhất định chạy file `.class` bạn vừa nhìn thấy.

## 14. Lỗi phổ biến khi thu nhỏ và đối chiếu môi trường

| Biểu hiện | Sai lầm khi chẩn đoán | Hướng đúng |
| --- | --- | --- |
| Xóa bớt class thì lỗi “biến mất” | Tưởng bug được giải quyết, thực ra đã loại bỏ đường code gây lỗi | Khôi phục phần tối thiểu khiến lỗi quay lại |
| IDE compile được, `javac` báo thiếu symbol | Chỉ sửa import hoặc tạo class giả | So sánh compile classpath và source set |
| CLI compile được, `java` lỗi `NoClassDefFoundError` | Tiếp tục thêm cờ cho compiler | Kiểm tra runtime classpath/module path |
| IDE không thấy file cấu hình | Đổi source encoding hoặc làm lại dependency | So sánh working directory và file path |
| Source level khác nhau | Chỉ nhìn `java -version` | Kiểm tra `javac -version` và compiler flags |
| Lỗi chỉ trong CI | Coi CI sai mà bỏ qua local cache | Tái hiện từ clean checkout/output và dependency đã khai báo |
| Sau khi sửa, output không đổi | Cho rằng JVM bỏ qua source | Biên dịch lại, kiểm tra output/class được nạp |
| Annotation-generated class thiếu | Viết tay class mới trong MRE để chạy qua | Giữ processor/task tối thiểu và so processing config |
| Cùng tên class nhưng hai bản JAR | Chỉ xem tên file mà không xem version/path | Theo dõi nguồn class loading và dependency graph |
| Sửa đồng thời 5 settings rồi hết lỗi | Kết luận quá mức về một nguyên nhân | Thử lại mỗi biến riêng để xác định quan hệ nhân quả |
| Báo cáo lỗi không có lệnh tái hiện | Người khác không thể xác minh | Gửi source tối thiểu, command, JDK, expected/actual |
| Copy log có token hoặc đường dẫn riêng | Lộ thông tin không cần thiết | Ẩn secret và thông tin nhạy cảm, giữ phần đủ cho debug |

## 15. Quy trình làm việc hiệu quả cho một bug thực tế

### Bước 1 — Ghi bản lỗi gốc

Sao chép log lỗi có phần root cause, ghi IDE/version nếu có, JDK compiler/runtime, build tool, OS, branch/commit khi phù hợp và cách kích hoạt lỗi. Không đánh đồng “lỗi khi click Run” với “lỗi compiler”.

### Bước 2 — Xác định giai đoạn

Hỏi lần lượt: IDE/build tool đã compile xong chưa? JVM có nạp được main class không? Lỗi xảy ra ngay lúc class loading hay sau khi code nghiệp vụ chạy? Có chạy cùng input không?

Nếu compiler chưa hoàn thành, việc đổi runtime VM options thường không giải quyết lỗi `cannot find symbol`.

### Bước 3 — Thiết lập baseline bằng dòng lệnh

Từ thư mục dự án, in:

~~~bash
java -version
javac -version
~~~

Dùng đường dẫn và classpath tường minh để compile và run. Nếu dự án dựa vào Gradle/Maven, chạy đúng task build của hệ thống để có baseline. Ghi output và exit status, không chỉ trạng thái giao diện IDE.

### Bước 4 — Thu nhỏ

Bỏ từng dependency, module, class, method hoặc đoạn code không liên quan; mỗi lần thay đổi đều chạy lại. Khi lỗi biến mất, xác định thay đổi cuối cùng, khôi phục một phần để tìm điều kiện thiết yếu.

### Bước 5 — Đối chiếu ma trận

Dựa vào pha lỗi mà chọn trục tương ứng: compiler JDK, `--release`, source path, compile classpath, output; hoặc JVM, runtime classpath, working directory, VM args, program args, environment.

### Bước 6 — Thử đúng một biến

Với MRE ở mục 4, khác biệt duy nhất cần thử là **thêm `out/lib` vào compile classpath**. Nếu compile từ lỗi thành thành công, đó là bằng chứng hỗ trợ giả thuyết dependency bị thiếu. Sau đó thử thêm `out/lib` vào runtime classpath để kiểm tra giai đoạn chạy.

### Bước 7 — Xác minh từ trạng thái sạch và trên môi trường cần hỗ trợ

Dùng output mới, dependency version được khóa và compiler/runtime được ghi nhận. Nếu lỗi của bạn là CI-only hoặc môi trường production-only, cần thử trong điều kiện tương đương thay vì chỉ trong IDE máy local.

### Bước 8 — Viết regression test hoặc guard

Khi nguyên nhân đã được xác minh, thêm test hoặc kiểm tra cấu hình tương ứng: build clean, test classpath, smoke test dưới runtime đích, hoặc assertion cho input làm lộ lỗi. Điều này giúp phát hiện việc cấu hình bị thay đổi trong tương lai.

## 16. Mẫu báo cáo lỗi có thể chuyển cho đồng đội

~~~text
Tiêu đề:
  Compile trong IDE thành công nhưng javac CLI không tìm thấy lib.Greeter.

Môi trường:
  JDK: 17 (cả javac và java)
  OS / shell: ghi loại thực tế
  Working directory: <thư mục gốc ide-cli-repro>
  Build mode: CLI javac trực tiếp (không Gradle/Maven)

Source:
  src/lib/Greeter.java
  src/app/Main.java

Lệnh tái hiện lỗi:
  javac --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java

Actual:
  Compile thất bại: package lib does not exist / cannot find symbol.

Expected:
  Nếu đã cung cấp dependency của module lib, compile phải thành công.

Thử nghiệm phân biệt:
  javac --release 17 -encoding UTF-8 -d out/lib src/lib/Greeter.java
  javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java

Kết quả:
  Lệnh compile ứng dụng thứ hai thành công.
  Chạy java với out/app và out/lib cho "Xin chao, Minh!"

Nhận định:
  Cấu hình compile classpath dòng lệnh thiếu module lib.
  IDE có thể đã bổ sung output module lib theo project model;
  cần xác minh điều này từ cấu hình IDE thực tế.
~~~

Đây là mẫu báo cáo **của bài thực hành**, không phải thông tin về một môi trường cụ thể đã được kiểm tra. Khi báo cáo lỗi thật, thay các dòng placeholder bằng giá trị đã quan sát; không đưa credential, khóa API hay dữ liệu cá nhân vào log.

## 17. Bài tập tự thực hành

### Bài 1 — Phân biệt hai lỗi cùng một project

Với `src/lib/Greeter.java` và `src/app/Main.java`:

1. Compile ứng dụng mà `-cp` chỉ tới `out/empty`.
2. Compile thư viện, rồi compile ứng dụng với `-cp out/lib`.
3. Chạy ứng dụng chỉ với `out/app`.
4. Chạy lại với cả `out/app` và `out/lib`.

**Đáp án:** (1) compile-time thiếu symbol; (2) compile thành công; (3) runtime không thấy `lib.Greeter`; (4) chương trình in `Xin chao, Minh!` khi truyền đối số `Minh`. Hai lỗi (1) và (3) xảy ra ở những pha khác nhau.

### Bài 2 — Giải thích classpath root

Vì sao đúng là:

~~~bash
javac -cp out/lib -d out/app src/app/Main.java
~~~

mà không dùng `-cp out/lib/lib`?

**Đáp án:** `out/lib` là classpath root, bên dưới có đường dẫn package `lib/Greeter.class`. Compiler/JVM nối tên package tương ứng vào root để tìm class.

### Bài 3 — Cùng bytecode, working directory khác

Dùng `WorkingDirDemo` và `settings.txt`. Vì sao chạy từ project root thành công nhưng chạy từ một thư mục khác có thể gặp `NoSuchFileException`?

**Đáp án:** `Path.of("settings.txt")` là đường dẫn tương đối, phụ thuộc working directory. Đây không phải lỗi classpath của `WorkingDirDemo.class`.

### Bài 4 — Source level không khớp

Build `LanguageProbe` với `--release 17` rồi thử `--release 8`. Vì sao trong IDE source có thể hợp lệ nhưng compiler CLI từ chối?

**Đáp án:** IDE hoặc build task đang dùng language level khác. `var` được hỗ trợ từ Java 10, không thuộc Java 8.

### Bài 5 — Thu nhỏ lỗi dependency

Một dự án gồm 40 class, 5 thư viện và 3 module. Lỗi thực tế là không tìm thấy `lib.Greeter` khi compile `app.Main`. Bạn sẽ giữ những gì trong MRE?

**Đáp án:** Giữ source phụ thuộc và source ứng dụng, lệnh compile cho module thư viện, lệnh compile cho ứng dụng, classpath sai/đúng và output root. Bỏ các class, JAR, resource, test không góp phần làm lỗi xuất hiện. Nếu lỗi cần build tool, giữ file cấu hình nhỏ nhất tái hiện đúng quan hệ dependency.

### Bài 6 — Xác định nguyên nhân thay vì chỉ “đã chạy”

IDE và CLI khác nhau ở cả JDK, classpath và working directory. Sau khi sửa cả ba, lỗi mất. Bạn có thể kết luận classpath là nguyên nhân duy nhất chưa?

**Đáp án:** Chưa. Cần thử từng thay đổi riêng hoặc tạo MRE cố định hai biến còn lại để biết yếu tố quyết định.

### Bài 7 — Chẩn đoán tệp class cũ

Bạn đã xóa source `OldApi.java` nhưng ứng dụng vẫn resolve `OldApi` trong terminal. Hãy nêu giả thuyết và phép thử an toàn.

**Đáp án:** Có thể `OldApi.class` cũ còn trong compile classpath hoặc JAR. Tạo thư mục output **mới**, compile với dependency được khai báo rõ và kiểm tra file/JAR đang được nạp. Không xóa bừa những thư mục dùng chung.

## 18. Checklist hoàn thành

- [ ] Tôi đã nêu rõ **expected** và **actual**.
- [ ] Tôi đã phân loại lỗi đúng pha: compile, launch, runtime hay test.
- [ ] MRE chỉ giữ những source/dependency/config cần để lỗi còn xuất hiện.
- [ ] Người khác có thể tạo output sạch và chạy lại lệnh từ đầu.
- [ ] Tôi biết compiler `javac` và JVM `java` đang dùng phiên bản nào.
- [ ] Tôi đã đối chiếu compiler classpath và runtime classpath.
- [ ] Tôi đã kiểm tra working directory, program arguments và VM options.
- [ ] Khi có build tool, tôi biết IDE đang delegate hay compile nội bộ.
- [ ] Tôi không suy luận từ output class cũ hoặc môi trường không được khai báo.
- [ ] Tôi đã thử một biến mỗi lần và giữ bằng chứng trước/sau.
- [ ] Tôi đã loại bỏ secret và thông tin nhạy cảm khỏi log chia sẻ.
- [ ] Tôi có kiểm thử/biện pháp ngăn lỗi tái diễn.

## Ghi nhớ

**MRE không chỉ là code ngắn; nó là một thí nghiệm đủ dữ kiện để tái hiện nguyên nhân.** Khi IDE và dòng lệnh cho kết quả khác nhau, hãy kiểm tra **cấu hình hiệu lực**: compiler, JDK, release, compile/runtime classpath, working directory, arguments, build tool, generated sources và output. Thu nhỏ lỗi từng bước, thay một biến mỗi lần và xác minh trên build sạch sẽ đáng tin cậy hơn việc sửa tùy tiện cho đến khi chương trình tình cờ chạy được.