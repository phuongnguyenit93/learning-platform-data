# Đọc thông tin JDK từ `java --version` (Java 10+)

## 1. Mục tiêu bài học

Để biết **lệnh `java` trong terminal đang trỏ đến bản Java nào**, cách nhanh nhất trên các JDK hiện đại là:

~~~bash
java --version
~~~

Lệnh hiển thị thông tin phiên bản của Java launcher/runtime được tìm thấy trong môi trường lệnh hiện tại, rồi **thoát mà không chạy chương trình ứng dụng**. Những thông tin thường thấy gồm **số phiên bản**, **nhà phân phối**, **ngày phát hành bản build**, **môi trường runtime**, **máy ảo Java (JVM)** và **số build**.

Tuy nhiên, không nên kết luận rằng máy chỉ cài đúng một JDK, IDE dùng cùng JDK, hoặc có sẵn trình biên dịch `javac` chỉ từ một lần chạy `java --version`.

Sau bài học, bạn sẽ có thể:

1. Chạy `java --version` và đọc đúng từng phần của kết quả.
2. Hiểu **mô hình đánh số phiên bản từ Java 10**, với `FEATURE.INTERIM.UPDATE.PATCH` và thông tin pre-release/build.
3. Phân biệt `java --version`, `java -version`, `javac --version` và phiên bản Java thực tế mà ứng dụng chạy.
4. Xác định vì sao `PATH`, `JAVA_HOME`, IDE hoặc build tool có thể dùng những JDK khác nhau.
5. Kiểm tra phiên bản bằng API Java hiện đại: `Runtime.version()` và `Runtime.Version`.
6. Tránh parse kết quả terminal theo một mẫu cứng không portable.
7. Xác định ranh giới: thông tin phiên bản **không tự chứng minh** bản cài đặt có đủ module, công cụ phát triển, hỗ trợ LTS hoặc bản vá bảo mật mới nhất.

**Phạm vi:** Bài thuộc nhóm **Mô hình phiên bản**, trong chủ đề **Java 10**, với trọng tâm là **đọc thông tin JDK từ `java --version`**. Các kiến thức bên dưới vẫn được dùng trong JDK hiện đại. Chương trình minh họa độc lập được viết để biên dịch/chạy bằng **Java 17 trở lên**.

## 2. Chạy lệnh và nhận biết kết quả

Mở Terminal, Command Prompt hoặc PowerShell rồi nhập:

~~~bash
java --version
~~~

Ví dụ **minh họa**, không phải đầu ra bắt buộc của máy bạn:

~~~text
openjdk 17.0.12 2024-07-16
OpenJDK Runtime Environment (build 17.0.12+7)
OpenJDK 64-Bit Server VM (build 17.0.12+7, mixed mode, sharing)
~~~

Đây là **một ví dụ về dạng output của một bản OpenJDK**, không phải cam kết mọi JDK luôn in đúng ba dòng hoặc đúng chuỗi này. Với Oracle JDK, Eclipse Temurin, Microsoft Build of OpenJDK, Amazon Corretto, GraalVM hay những nhà phân phối khác, phần nhãn sản phẩm, VM, build, ngày và các thông tin bổ sung có thể khác nhau.

### Cách đọc ví dụ trên

| Thành phần | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Tên sản phẩm | `openjdk` | Nhãn sản phẩm/runtime được nhà phân phối sử dụng |
| Version | `17.0.12` | Feature 17, interim 0, update 12; không có phần patch khác 0 |
| Ngày | `2024-07-16` | Ngày liên quan tới bản phát hành được hiển thị, không phải ngày hiện tại của hệ thống |
| Runtime | `OpenJDK Runtime Environment` | Mô tả môi trường thực thi |
| Build | `17.0.12+7` | Version `17.0.12` và **số build 7**, không phải version `17.0.12.7` |
| VM | `OpenJDK 64-Bit Server VM` | Thông tin về JVM được triển khai |
| VM mode | `mixed mode, sharing` | Những chi tiết về chế độ JVM, phụ thuộc implementation |

**Điểm cần ghi nhớ:** các dòng hiển thị cho biết **chương trình `java` vừa được gọi đang sử dụng runtime nào**. Nó không tự liệt kê toàn bộ các JDK đã cài trong máy, không khẳng định `javac` tồn tại, và không tự cho biết một dự án cụ thể đã được biên dịch cho phiên bản nào.

### Một output Java 10 có thể khác như thế nào?

Ở dòng phiên bản của một bản Java 10, **feature = 10**. Những mẫu số có thể gặp theo mô hình Java 10:

~~~text
10
10.0.1
10.0.2
10.0.2+13
10-ea+3
~~~

Đây là **những ví dụ về chuỗi phiên bản**, không phải năm dòng mà `java --version` chắc chắn sẽ in. `-ea` thể hiện pre-release; `+13` thể hiện build number trong mẫu có nó.

Không nên cố dựng một output Java 10 cụ thể rồi yêu cầu mọi nhà phân phối hiện nay phải giống nguyên văn. Cách đọc **cấu trúc thông tin** hữu ích hơn ghi nhớ một dòng mẫu.

## 3. Mô hình phiên bản từ Java 10: JEP 322

Từ **JDK 10**, JEP 322 (*Time-Based Release Versioning*) xác định ý nghĩa chính của bốn thành phần trong số phiên bản:

~~~text
FEATURE.INTERIM.UPDATE.PATCH
~~~

| Thành phần | Vai trò | Ví dụ với `17.0.12` |
| --- | --- | --- |
| `FEATURE` | Số **feature release**; tăng ở mỗi kỳ phát hành tính năng | `17` |
| `INTERIM` | Số interim release dành cho các thay đổi tương thích trong mô hình | `0` |
| `UPDATE` | Số update release, thường chứa sửa lỗi và bản vá | `12` |
| `PATCH` | Số emergency patch release nếu cần | Ngầm hiểu `0` khi không xuất hiện |

**Không phải mọi thành phần đều phải xuất hiện trong chuỗi.** Các thành phần `0` cuối được bỏ đi:

~~~text
10           → feature=10, interim=0, update=0, patch=0
10.0.2       → feature=10, interim=0, update=2, patch=0
17.0.12      → feature=17, interim=0, update=12, patch=0
21.0.4       → feature=21, interim=0, update=4, patch=0
~~~

Những chuỗi trên là ví dụ giải thích **version-number semantics**, không nói rằng đó là phiên bản đang chạy trên máy của người đọc.

### `10` không phải `1.10`

Trong mô hình hiện đại, **Java 10 có feature number `10`**, Java 17 có `17`, Java 21 có `21`. Không gắn thêm tiền tố `1.` trước feature number.

Nếu cần hỗ trợ một hệ thống cũ có cách hiển thị phiên bản lịch sử khác, hãy xử lý riêng yêu cầu tương thích đó. Đối với bài học và code Java 10+ hiện tại, **dùng `feature()`** thay cho việc suy luận từ những tiền tố kiểu cũ.

### `FEATURE` không phải mức độ thay đổi nhỏ/lớn của SemVer

Dù có nhiều đoạn số phân cách bằng dấu chấm, mô hình JDK không đơn giản là **semantic versioning `major.minor.patch`** theo mọi quy tắc thông dụng của thư viện. Các thành phần có ý nghĩa được JEP 322 quy định.

Ví dụ:
- `17.0.12`: **feature 17**, update 12.
- `21.0.4`: **feature 21**, update 4.
- Không so sánh toàn bộ chuỗi bằng thứ tự từ điển: chuỗi `"9"` có thể xếp sau `"17"` theo thứ tự chữ cái, dù phiên bản số `9` thấp hơn `17`.

Trong Java, dùng `Runtime.Version` để phân tích và so sánh phiên bản **hợp cú pháp**, thay vì tự viết phép so sánh chuỗi tùy tiện.

## 4. Đọc phần pre-release, build và thông tin tùy chọn

Bên cạnh số phiên bản, một Java version string có thể mang thông tin **pre-release** và **build**.

Mẫu tổng quát, rút gọn:

~~~text
VNUM[-PRE][+BUILD[-OPT]]
~~~

Các dạng hợp lệ có thể bao gồm những biến thể về optional metadata theo đặc tả `Runtime.Version`. Không nên coi dòng trên là regex hoàn chỉnh cho mọi biến thể của version-string grammar.

| Ví dụ | Phân tích | Lưu ý |
| --- | --- | --- |
| `10` | Version number chỉ có feature 10 | Các thành phần thiếu có giá trị 0 khi truy vấn qua API |
| `10.0.2+13` | Update 2, build 13 | `13` sau `+` là build, **không phải patch** |
| `17.0.12+7-LTS` | Feature 17, update 12, build 7, optional `LTS` | Nhãn optional do bản phát hành/nhà phân phối cung cấp |
| `21-ea+3` | Feature 21, pre-release `ea`, build 3 | `ea` thường chỉ early access, không phải bản GA |

**Dấu `+` trong version-string không đồng nghĩa phép cộng số phiên bản.** Nó đánh dấu phần build theo grammar của Java. Không cố parse `17.0.12+7` thành bốn số bằng cách thay `+` bằng dấu chấm.

### Ý nghĩa của nhãn LTS

Một số nhà phân phối ghi chữ `LTS` hoặc thông tin liên quan trong output. Đây là **thông tin về dòng hỗ trợ/phân phối**, không tự chứng minh quyền hỗ trợ của người dùng, hợp đồng bảo trì hay bản patch mới nhất.

Trong thực tế:
- Cần biết **nhà cung cấp/distribution**, version đầy đủ và build.
- Cần kiểm tra **chính sách hỗ trợ và thông báo bảo mật của nhà cung cấp** đối với bản cài đặt đang dùng.
- Không dùng việc xuất hiện hoặc vắng mặt nhãn `LTS` làm phép kiểm tra an ninh duy nhất.

### Số build không đồng nhất giữa mọi nhà phân phối

Hai runtime cùng feature/update vẫn có thể khác **vendor**, JVM implementation, patch downstream hoặc thông tin build. Do đó, kết quả `java --version` không chỉ có một khuôn in duy nhất.

Khi ghi log sự cố, lưu **toàn bộ output gốc** và đường dẫn thực của launcher thay vì chỉ sao chép feature number.

## 5. `java --version` khác gì `java -version`?

Trên JDK hiện đại, hai câu lệnh đều dùng để hiển thị thông tin version rồi **thoát**:

~~~bash
java --version
java -version
~~~

Khác biệt quan trọng theo đặc tả `java` launcher trong JDK hiện đại:

| Lệnh | Dòng dữ liệu thông thường | Ý nghĩa |
| --- | --- | --- |
| `java --version` | **stdout** | In thông tin sản phẩm/version và thoát |
| `java -version` | **stderr** | In thông tin sản phẩm/version và thoát |
| `java --show-version` | **stdout** | In version rồi **tiếp tục chạy chương trình** nếu có main class/JAR |
| `java -showversion` | **stderr** | In version rồi **tiếp tục chạy chương trình** nếu có |

Sự khác nhau giữa `stdout` và `stderr` có ý nghĩa khi ghi file, pipe hoặc tự động hóa. Với lệnh dùng để lấy version trong terminal, **`java --version` thường dễ thu stdout hơn**.

Ví dụ trên shell POSIX (Linux/macOS), khi không có thông báo khác xen vào:

~~~bash
java --version > java-version.txt
~~~

Dòng lệnh này chuyển **stdout** sang tệp `java-version.txt`. Với `java -version`, vì version thường được in ra **stderr**, phép chuyển chỉ `stdout` như trên có thể không lưu các dòng version vào tệp.

Nếu cần thu cả output trong một hệ thống tự động hóa, hãy đọc đúng hai luồng stdout/stderr, không giả định mọi runtime/vendor in cùng một tập thông báo. Launcher có thể ghi thông báo hoặc cảnh báo khác ở stderr, kể cả khi version chính được in ở stdout.

### Lệnh không chạy `main`

~~~bash
java --version
~~~

Lệnh này **không biên dịch một tệp `.java`**, không thực hiện `main(String[] args)`, không chạy unit test và không kiểm tra toàn bộ phụ thuộc của dự án. Nó là phép **nhận diện runtime/launcher**.

Nếu muốn vừa thấy version vừa chạy chương trình, dùng tùy chọn show-version tương ứng và cung cấp main class/JAR. Đừng nhầm `--version` với `--show-version` trong script.

## 6. `java` không phải `javac`: biết runtime chưa đủ biết JDK

Hai công cụ có vai trò khác nhau:

- **`java`**: launcher dùng để thực thi ứng dụng Java trên runtime/JVM phù hợp.
- **`javac`**: trình biên dịch Java source code thành bytecode.

Kiểm tra độc lập:

~~~bash
java --version
javac --version
~~~

Ví dụ một máy có cả hai bản cùng dòng feature:

~~~text
$ java --version
openjdk 17.0.12 ...
...

$ javac --version
javac 17.0.12
~~~

**Đây chỉ là output minh họa**; dấu `...` biểu thị những phần khác nhau tùy hệ thống, không phải bản xuất chuẩn để copy vào test.

### Vì sao cần kiểm tra cả hai?

- Một môi trường có thể chạy được `java` nhưng **không có `javac` trên PATH**, chẳng hạn runtime image tối giản.
- `java` và `javac` có thể đến từ **hai thư mục cài đặt khác nhau** nếu PATH được cấu hình không nhất quán.
- IDE có thể dùng một JDK cho project, còn terminal dùng JDK khác.
- Maven/Gradle có thể sử dụng **Java toolchain** không trùng với bản Java mà shell tự chọn.
- Trong container, image build và image runtime có thể khác nhau.

Không nói rằng chỉ cần `java --version` thành công là **cả bộ JDK phát triển đầy đủ đã được cài đặt và có thể sử dụng**. Muốn xác minh compiler thực sự có sẵn, chạy `javac --version`; nếu phải biên dịch dự án, hãy chạy một tác vụ build thực.

### Khác biệt giữa phiên bản JDK chạy compiler và phiên bản bytecode mục tiêu

Một JDK mới hơn có thể biên dịch mã cho mục tiêu Java cũ hơn với cờ `--release` khi mục tiêu được JDK đó hỗ trợ:

~~~bash
javac --release 17 Example.java
~~~

Đây là **ví dụ cú pháp**, giả sử có tệp `Example.java`. Nó không có nghĩa `java --version` của máy sẽ đổi thành 17; cờ `--release 17` yêu cầu compiler giới hạn API/ngôn ngữ và class-file target theo Java 17.

Ngược lại, `java --version` là thông tin về launcher/runtime **đang gọi**, không phải bằng chứng chương trình của bạn được build với cờ `--release` nào.

## 7. `PATH`, `JAVA_HOME` và lý do nhiều bản JDK dễ bị nhầm

Khi gõ:

~~~bash
java --version
~~~

Shell dùng quy tắc tìm executable, thường dựa vào **PATH** hoặc cơ chế command resolution tương đương. Biến **`JAVA_HOME`** có thể được ứng dụng/build tool sử dụng, nhưng **không tự bảo đảm** rằng câu lệnh `java` trần sẽ gọi `JAVA_HOME/bin/java`.

### Linux và macOS

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
java --version
javac --version
~~~

Đây là các lệnh kiểm tra trong shell POSIX. `command -v` cho biết command được shell tìm thấy, nhưng kết quả có thể là một symlink hoặc shim/version manager chứ không nhất thiết là đường dẫn vật lý cuối cùng.

Để thử trực tiếp bản Java tại `JAVA_HOME` đã cấu hình, nếu thư mục đó hợp lệ:

~~~bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
~~~

Nếu `JAVA_HOME` không được đặt hoặc trỏ sai thư mục, hai câu trên có thể thất bại. Đây là bước **kiểm tra**, không phải thao tác sửa cấu hình.

### Windows PowerShell

~~~powershell
Get-Command java
Get-Command javac
where.exe java
where.exe javac
$env:JAVA_HOME
java --version
javac --version
~~~

Trong PowerShell, **`where` đơn lẻ** có thể là alias của `Where-Object`; vì vậy dùng **`where.exe`** khi muốn gọi chương trình tìm executable của Windows.

Nếu `JAVA_HOME` đã cấu hình đúng:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\javac.exe" --version
~~~

Ký tự **`&`** trong PowerShell ở đây là *call operator* để thực thi đường dẫn có thể chứa khoảng trắng. Nó không có nghĩa nối hai lệnh với nhau.

### Cách điều tra khi kết quả không như dự kiến

Nếu dự án yêu cầu Java 17 nhưng terminal hiển thị Java 21:
1. Xem `java --version` và `javac --version`.
2. Xem executable thực được chọn bằng `command -v java` hoặc `Get-Command java`/`where.exe java`.
3. Kiểm tra `JAVA_HOME` và thư mục `bin` của JDK mong muốn.
4. Kiểm tra cấu hình IDE, Maven/Gradle toolchain và runtime mà ứng dụng thực sự dùng.
5. Chỉ thay đổi PATH/JAVA_HOME khi có yêu cầu nghiệp vụ rõ ràng; một hệ thống có thể cố ý giữ nhiều JDK để build và chạy các dự án khác nhau.

**Ghi nhớ:** Một kết quả `java --version` chỉ cho biết **một lệnh trong một phiên shell**, không phải toàn bộ trạng thái Java của máy.

## 8. Đọc phiên bản từ bên trong Java: `Runtime.version()`

Đối với một ứng dụng đang chạy, thay vì khởi động một `java` khác từ shell rồi parse output vendor-specific, bạn có thể dùng:

~~~java
Runtime.Version current = Runtime.version();
System.out.println(current);
System.out.println(current.feature());
~~~

Đây là đoạn mã minh họa trong phương thức Java. `Runtime.version()` cung cấp thông tin phiên bản của runtime **chính ứng dụng hiện tại đang chạy**.

Đặc biệt, từ **Java 10**, `Runtime.Version` có các accessor hiện đại:
- `feature()` — feature release;
- `interim()` — interim release;
- `update()` — update release;
- `patch()` — emergency patch release;
- `version()` — danh sách các thành phần phiên bản;
- `pre()`, `build()`, `optional()` — thông tin phụ dạng `Optional`.

Ví dụ:

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.12+7-LTS");

System.out.println(v.feature());             // 17
System.out.println(v.interim());             // 0
System.out.println(v.update());              // 12
System.out.println(v.patch());               // 0
System.out.println(v.build().orElse(-1));    // 7
System.out.println(v.optional().orElse("")); // LTS
~~~

Đoạn này **phân tích chuỗi ví dụ đã biết**, không phụ thuộc bản JDK của người đọc. Lệnh `Runtime.Version.parse(...)` yêu cầu chuỗi phiên bản hợp cú pháp; không đưa trực tiếp **toàn bộ ba dòng output `java --version`** vào hàm parse.

### Vì sao `feature()` tốt hơn `major()`?

Từ Java 10, `Runtime.Version.major()`, `minor()` và `security()` đã bị **deprecated** vì tên cũ không còn phù hợp với ý nghĩa phiên bản theo JEP 322. Mã Java hiện đại nên dùng:
- `feature()` thay vì `major()`;
- `interim()` thay vì `minor()`;
- `update()` thay vì `security()`.

Điều này trực tiếp đáp ứng Special Note của module: **chỉ sử dụng cách làm còn áp dụng và được khuyến nghị trong Java hiện đại**.

### Kiểm tra phiên bản tối thiểu

Nếu yêu cầu của ứng dụng là chạy trên **Java 17+**, xét feature number:

~~~java
int requiredFeature = 17;

if (Runtime.version().feature() < requiredFeature) {
    throw new IllegalStateException(
            "This application requires Java " + requiredFeature + " or newer");
}
~~~

Đây là **snippet** chứ không phải một chương trình độc lập.

Lưu ý: nếu bytecode được build bằng class-file version mới hơn mức runtime có thể tải, JVM có thể ném `UnsupportedClassVersionError` **trước khi đoạn kiểm tra trong `main` chạy**. Vì thế một check trong Java **không thay thế** việc chọn đúng runtime và target của compiler.

Đối với yêu cầu bảo mật như “phải có ít nhất update X của dòng Y”, chỉ so sánh `feature()` là chưa đủ. Hãy xác định rõ chính sách update/vendor, build cần thiết, và kiểm tra theo nguồn hỗ trợ tương ứng.

## 9. Chương trình Java 17+ hoàn chỉnh, với stdout xác định

Chương trình dưới đây được chia làm hai phần:
- **Mặc định, không đối số:** phân tích các version string mẫu cố định, cho stdout tái lập được.
- **Có đối số `--current`:** in metadata của runtime **thực sự đang chạy**, nên output phần này phụ thuộc máy/JDK/vendor.

Tạo tệp **JdkVersionReaderDemo.java**:

~~~java
public class JdkVersionReaderDemo {

    private static void showSamples() {
        Runtime.Version v10 = Runtime.Version.parse("10");
        Runtime.Version v10Update = Runtime.Version.parse("10.0.2+13");
        Runtime.Version v17 = Runtime.Version.parse("17.0.12+7-LTS");
        Runtime.Version v21Early = Runtime.Version.parse("21-ea+3");

        System.out.println("feature(10) = " + v10.feature());
        System.out.println("interim(10) = " + v10.interim());
        System.out.println("update(10) = " + v10.update());
        System.out.println("patch(10) = " + v10.patch());

        System.out.println("components(10.0.2) = "
                + v10Update.version());
        System.out.println("update(10.0.2) = "
                + v10Update.update());
        System.out.println("build(10.0.2+13) = "
                + v10Update.build().orElse(-1));

        System.out.println("feature(17) = " + v17.feature());
        System.out.println("update(17.0.12) = " + v17.update());
        System.out.println("optional(17) = "
                + v17.optional().orElse("-"));
        System.out.println("pre(21-ea) = "
                + v21Early.pre().orElse("-"));

        System.out.println("10 earlier than 17 = "
                + (v10.compareTo(v17) < 0));
        System.out.println("17 meets minimum 17 = "
                + (v17.feature() >= 17));
    }

    private static void showCurrentRuntime() {
        Runtime.Version current = Runtime.version();

        System.out.println("=== Current runtime (environment-dependent) ===");
        System.out.println("runtime version = " + current);
        System.out.println("runtime feature = " + current.feature());
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.runtime.version = "
                + System.getProperty("java.runtime.version"));
        System.out.println("java.specification.version = "
                + System.getProperty("java.specification.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name = "
                + System.getProperty("java.vm.name"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
    }

    public static void main(String[] args) {
        showSamples();

        if (args.length > 0 && "--current".equals(args[0])) {
            showCurrentRuntime();
        }
    }
}
~~~

Biên dịch bằng JDK 17+:

~~~bash
javac --release 17 JdkVersionReaderDemo.java
java JdkVersionReaderDemo
~~~

**Đầu ra chính xác khi không truyền đối số:**

~~~text
feature(10) = 10
interim(10) = 0
update(10) = 0
patch(10) = 0
components(10.0.2) = [10, 0, 2]
update(10.0.2) = 2
build(10.0.2+13) = 13
feature(17) = 17
update(17.0.12) = 12
optional(17) = LTS
pre(21-ea) = ea
10 earlier than 17 = true
17 meets minimum 17 = true
~~~

Để in cả thông tin runtime thực:

~~~bash
java JdkVersionReaderDemo --current
~~~

Khi có `--current`, 13 dòng mẫu phía trên vẫn xuất hiện, sau đó thêm:

~~~text
=== Current runtime (environment-dependent) ===
runtime version = ...
runtime feature = ...
java.version = ...
java.runtime.version = ...
java.specification.version = ...
java.vendor = ...
java.vm.name = ...
java.home = ...
~~~

Các dấu `...` ở đây **chỉ là ký hiệu cho dữ liệu môi trường, không phải giá trị đầu ra cố định**. Chúng sẽ khác nhau giữa các bản Java, vendor, OS và cách cài đặt.

### Vì sao ví dụ này đáng tin hơn parse ba dòng terminal bằng regex?

1. `Runtime.Version.parse` giải thích **cấu trúc version** bằng API có hợp đồng, không cắt chuỗi tùy tiện.
2. `feature`, `update`, `patch` trả `int`, cho phép so sánh số học.
3. `pre()`, `build()`, `optional()` trả `Optional`, tránh giả định version string nào cũng có các trường này.
4. `Runtime.version()` lấy version của **runtime đang thực thi chính chương trình**, không khởi động thêm một executable khác trên PATH.
5. Các thuộc tính `java.vendor`, `java.vm.name`, `java.home` giúp chẩn đoán môi trường thực tế.
6. Chỉ phần `--current` phụ thuộc môi trường; đầu ra từ các version mẫu cố định không thay đổi theo máy.

**Giới hạn:** `java.home` là đường dẫn runtime đang sử dụng, không chứng minh rằng một terminal khác có PATH giống hệt, cũng không phải bằng chứng duy nhất rằng một compiler `javac` sẽ tồn tại ở vị trí nào.

## 10. Đọc và so sánh version bằng API thay vì tự cắt chuỗi

### Không so sánh bằng từ điển

~~~java
String left = "9";
String right = "17";

System.out.println(left.compareTo(right) > 0); // true
~~~

Với so sánh **chuỗi ký tự**, ký tự đầu `9` xếp sau `1`, nhưng **Java feature 9** rõ ràng thấp hơn **feature 17**.

Đối với version hợp cú pháp:

~~~java
Runtime.Version v9 = Runtime.Version.parse("9");
Runtime.Version v17 = Runtime.Version.parse("17");

System.out.println(v9.compareTo(v17) < 0); // true
~~~

Mặc dù bài tập trung Java 10+, việc dùng chuỗi `"9"` ở đây chỉ là **một ví dụ số học để chỉ ra lỗi so sánh chuỗi**, không khuyến nghị sử dụng JDK 9 cho môi trường hiện tại.

### Chọn tiêu chí so sánh phù hợp

Có hai câu hỏi khác nhau:

- **“Ứng dụng cần ít nhất Java 17?”** Có thể kiểm tra `Runtime.version().feature() >= 17`.
- **“Ứng dụng cần một bản cập nhật bảo mật cụ thể của một vendor?”** Phải xét đầy đủ dòng phiên bản, update/build/vendor và chính sách của hệ thống; kiểm tra feature đơn độc không đủ.

`Runtime.Version.compareTo` so sánh các thành phần version và thông tin liên quan theo hợp đồng, nhưng **không phải bộ kiểm tra lỗ hổng bảo mật hoặc tính hợp lệ của mọi chính sách hỗ trợ**.

### `Runtime.Version.parse` không nhận nguyên cả output

Một ví dụ output đầu tiên của launcher có thể là:

~~~text
openjdk 17.0.12 2024-07-16
~~~

Không gọi:

~~~java
Runtime.Version.parse("openjdk 17.0.12 2024-07-16");
~~~

Cách này **không hợp cú pháp một version string**, vì còn chứa nhãn sản phẩm và ngày. Nếu cần thu version từ công cụ bên ngoài:
- Trước hết xác định bạn cần **feature**, **version đầy đủ**, **vendor** hay cả build.
- Nếu code đang chạy trong Java, **ưu tiên `Runtime.version()`**.
- Nếu hệ thống orchestration cần kiểm tra một Java executable bên ngoài, gọi trực tiếp executable đã xác định và xử lý output theo giao kèo của công cụ/nhà phân phối; tránh giả định tất cả vendor có cấu trúc chuỗi cố định.

## 11. Một số lệnh bổ sung để chẩn đoán môi trường

| Cần biết | Lệnh/API | Lưu ý |
| --- | --- | --- |
| Version runtime được terminal gọi | `java --version` | Thường stdout, thoát sau khi in |
| Version runtime theo cú pháp cũ của launcher | `java -version` | Được hỗ trợ, thường stderr |
| Version trình biên dịch được terminal gọi | `javac --version` | Không chứng minh `java` trỏ cùng thư mục |
| Đường dẫn `java` trong shell POSIX | `command -v java` | Có thể trỏ shim/symlink |
| Đường dẫn `java` trên Windows | `where.exe java` hoặc `Get-Command java` | Phụ thuộc PATH/PATHEXT và command resolution |
| Runtime version **trong process đang chạy** | `Runtime.version()` | Đáng tin hơn shell ngoài để nhận diện process |
| Runtime vendor | `System.getProperty("java.vendor")` | Có thể khác dòng tên sản phẩm in ở terminal |
| Runtime home | `System.getProperty("java.home")` | Không nhất thiết bằng `JAVA_HOME` được đặt ở terminal |
| Java specification version | `System.getProperty("java.specification.version")` | Thể hiện spec Java, không phải toàn bộ build string |
| Xem cấu hình JVM chi tiết | `java -XshowSettings:properties -version` | Output nhiều; cách hiển thị phụ thuộc launcher/JDK |

Tùy chọn `-XshowSettings:properties` hữu ích để nhìn các thuộc tính hệ thống khi chẩn đoán. Nó **không thay thế** `java --version` cho câu hỏi đơn giản “Java runtime hiện tại là bản nào”.

### Có nhiều phiên bản là bình thường

Một máy có thể cố ý dùng:
- Một JDK mới để **biên dịch** với `javac --release 17`.
- Một Java 17 runtime để **chạy** ứng dụng ở production.
- Một JDK khác do IDE hoặc test runner lựa chọn.

Do đó, nếu test báo lỗi chỉ ở IDE nhưng terminal `java --version` đúng, hãy kiểm tra cấu hình **runtime cho tác vụ thật**, không chỉ thay PATH theo phản xạ.

## 12. Kịch bản lỗi thực tế và cách kiểm tra

### Tình huống 1 — Terminal báo `java: command not found`

Nguyên nhân có thể là executable chưa cài, PATH không chứa thư mục `bin`, shell chưa làm mới môi trường, hoặc cài đặt bị sai. `JAVA_HOME` có thể đang đúng nhưng PATH vẫn chưa trỏ đến `bin`.

**Cách xử lý:** xác định đường dẫn Java mong muốn, thử executable bằng đường dẫn đầy đủ, rồi kiểm tra cấu hình shell. Không kết luận rằng Java chưa được cài chỉ vì lệnh trần không được tìm thấy.

### Tình huống 2 — `java --version` và `javac --version` khác feature

Ví dụ đầu ra cho thấy Java runtime feature 17, compiler feature 21. Hệ thống vẫn có thể hoạt động hợp lệ nếu dùng compiler 21 để build cho mục tiêu 17 với `--release 17`, nhưng cũng có thể là cấu hình PATH sai.

**Cách kiểm tra:** xác định mục tiêu build/runtime của dự án, xem đường dẫn từng executable và chạy build thực thay vì suy đoán.

### Tình huống 3 — IDE dùng JDK khác terminal

Đây là tình huống phổ biến trong các môi trường có nhiều JDK. `java --version` chỉ kiểm tra terminal, còn IDE có project SDK, run configuration hoặc build toolchain riêng.

**Cách kiểm tra:** in `Runtime.version()` và `java.home` từ **quá trình do IDE chạy**. Khi cần, so sánh với kết quả terminal.

### Tình huống 4 — Thấy chữ `LTS` và nghĩ đã có mọi bản vá

Nhãn hỗ trợ **không phải chứng nhận bảo mật**. Một dòng LTS có nhiều bản update khác nhau; vendor và phạm vi hỗ trợ cũng khác.

**Cách xử lý:** ghi lại **version đầy đủ**, build và vendor; đối chiếu thông báo cập nhật từ nhà cung cấp tương ứng.

### Tình huống 5 — Build báo `UnsupportedClassVersionError`

Lỗi này thường cho thấy runtime đang cố tải một class-file version mà nó không hỗ trợ. Có thể compiler hoặc dependencies được build với target cao hơn runtime hiện tại.

**Cách kiểm tra:** đối chiếu `java --version` của **runtime thực chạy**, `javac --version`, cờ `--release`/toolchain, và class-file target của artifact. Chỉ tăng một biến phiên bản in ra ngoài terminal chưa chắc sửa đúng task chạy.

### Tình huống 6 — `java -version > file.txt` tạo file rỗng

Vì `-version` có thể viết version ra **stderr** theo đặc tả JDK hiện đại, trong khi `>` chỉ chuyển hướng stdout ở shell thông thường.

**Cách xử lý:** dùng `java --version > file.txt` khi muốn thu stdout của lệnh version, hoặc thu stderr theo nhu cầu; giữ thông tin lỗi và mã thoát khi viết script.

### Tình huống 7 — Script chấp nhận feature 17 nhưng không phát hiện build sai

Kiểm tra `feature() >= 17` chỉ xác nhận điều kiện feature tối thiểu. Nó không xác nhận rằng update/build chứa bản vá cụ thể.

**Cách xử lý:** tách **chính sách feature compatibility** khỏi **chính sách bảo mật/vendor patch level**. Những điều kiện này có thể cần dữ liệu bên ngoài `Runtime.Version`.

### Tình huống 8 — Parse dòng đầu output bằng một regex cố định

Các distribution có thể thêm/bớt tiền tố `java`/`openjdk`, nhãn `LTS`, ngày hoặc metadata. Regex viết riêng cho một ví dụ có thể thất bại khi chạy trên vendor khác.

**Cách xử lý:** sử dụng API Java chuẩn khi kiểm tra process hiện tại; trong scripts quản lý JDK ngoài, cố định executable/toolchain hoặc dùng cơ chế phát hiện version do hệ thống build quản lý.

## 13. Checklist kiểm tra phiên bản JDK trong dự án

Trước khi quyết định “máy đã có đúng Java”, trả lời lần lượt:

1. **Đang chạy lệnh trong môi trường nào?** Terminal host, container, CI, máy ảo, IDE hay runtime của ứng dụng?
2. **`java --version` đang báo feature nào?** Đọc đúng con số đầu của version-number.
3. **Đã ghi lại build và vendor chưa?** Cần thiết nếu lỗi có thể khác theo bản phát hành.
4. **Đã kiểm tra `javac --version` khi cần compile chưa?** Runtime không chứng minh compiler.
5. **Đã tìm executable thực qua PATH chưa?** Tránh nhầm launcher từ một JDK khác.
6. **`JAVA_HOME` và đường dẫn Java đang chạy có cùng nguồn không?** Không mặc nhiên bằng nhau.
7. **Build tool có toolchain riêng không?** Nếu có, kiểm tra đúng JDK mà toolchain chọn.
8. **Artifact đã được build cho target nào?** `--release`/class-file version không suy ra từ runtime.
9. **Ứng dụng thực sự đang chạy runtime nào?** Có thể in `Runtime.version()` và `java.home` từ process.
10. **Đầu ra của phiên bản có pre-release `ea` hoặc build đặc biệt không?** Đừng dùng bản chưa ổn định cho môi trường đòi hỏi bản GA nếu không được phép.
11. **Có cần một bản cập nhật bảo mật cụ thể không?** Kiểm tra vendor/support/patch policy, không chỉ `FEATURE`.
12. **Script có giả định stdout hay stderr không?** `java --version` và `java -version` khác nhau theo hợp đồng của launcher hiện đại.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Lệnh nào xem nhanh phiên bản của Java launcher/runtime được shell hiện tại tìm thấy?

**Đáp án:** `java --version`.

**Câu 2.** `java --version` có chứng minh rằng `javac` tồn tại và cùng phiên bản không?

**Đáp án:** Không. Cần kiểm tra độc lập bằng `javac --version` và đường dẫn của từng executable.

**Câu 3.** Chuỗi `17.0.12` được hiểu như thế nào?

**Đáp án:** `FEATURE=17`, `INTERIM=0`, `UPDATE=12`, `PATCH=0` (không được ghi vì giá trị 0 ở cuối).

**Câu 4.** Trong `10.0.2+13`, số `13` có phải patch number không?

**Đáp án:** Không. Nó là **build number**. Update là `2`; patch không được ghi nên có giá trị 0.

**Câu 5.** `21-ea+3` cho biết điều gì?

**Đáp án:** Feature 21; pre-release identifier `ea` (thường là early access); build 3. Đây là ví dụ về version string, không xác nhận bản đó đang được cài trên máy.

**Câu 6.** Vì sao `java --version` không đủ để khẳng định ứng dụng chạy từ IDE đang dùng đúng JDK?

**Đáp án:** IDE hoặc build tool có cấu hình launcher/toolchain khác với PATH của terminal. Cần kiểm tra từ chính process được IDE chạy.

**Câu 7.** Lệnh nào in thông tin version rồi **thoát** qua stdout trên launcher JDK hiện đại?

**Đáp án:** `java --version`. `java -version` cũng thoát nhưng in version ra stderr theo đặc tả hiện đại.

**Câu 8.** API nào lấy feature number của **runtime đang chạy trong ứng dụng**?

**Đáp án:** `Runtime.version().feature()`.

**Câu 9.** Vì sao không nên dùng `String.compareTo` để xếp `"9"` và `"17"`?

**Đáp án:** So sánh chuỗi là thứ tự từ điển, không phải thứ tự số. Dùng `Runtime.Version` để so sánh các version hợp cú pháp.

**Câu 10.** `java --version` có tự kiểm tra rằng máy đang ở bản vá bảo mật mới nhất không?

**Đáp án:** Không. Lệnh chỉ báo phiên bản đang gọi; muốn đánh giá cập nhật phải xét vendor, build và thông báo hỗ trợ/bảo mật có hiệu lực.

**Câu 11.** `javac --release 17` có làm `java --version` trên máy thành 17 không?

**Đáp án:** Không. Cờ compiler điều khiển target của quá trình biên dịch; nó không đổi launcher Java được terminal tìm thấy.

**Câu 12.** Tại sao một đoạn code dùng `Runtime.version().feature() < 17` có thể không chạy được trên Java quá cũ?

**Đáp án:** Nếu class-file version của ứng dụng cao hơn runtime hỗ trợ, JVM có thể không tải lớp, ném `UnsupportedClassVersionError` trước khi code kiểm tra trong `main` được thực thi.

## 15. Ghi nhớ cuối bài

1. **`java --version`** là cách phổ biến và hiện hành để đọc thông tin **launcher/runtime Java đang được terminal gọi**, rồi thoát.
2. Output có thể chứa **version, nhà phân phối, ngày, runtime/JVM và build**; không giả định tất cả vendor dùng đúng một khuôn ba dòng.
3. Từ **Java 10, JEP 322** xác định ý nghĩa của `FEATURE.INTERIM.UPDATE.PATCH`; các phần `0` cuối được bỏ, còn `+BUILD` và `-PRE` có vai trò riêng.
4. **`java --version` thường dùng stdout**, còn `java -version` dùng stderr theo launcher hiện đại; quan trọng khi redirect/log.
5. **`java` là launcher; `javac` là compiler**. Muốn biết JDK phát triển có sẵn phải kiểm tra thêm `javac --version`.
6. Kết quả chịu ảnh hưởng bởi **PATH/command resolution**; `JAVA_HOME`, IDE, Maven/Gradle và ứng dụng có thể dùng JDK khác.
7. Với code Java cần kiểm tra phiên bản của **chính process hiện tại**, ưu tiên **`Runtime.version()`**, `feature()`, `update()`, `patch()` và các thuộc tính hệ thống thích hợp, không tự parse toàn bộ output terminal theo regex cứng.
8. **Đọc được số phiên bản không tự chứng minh tính tương thích, mức hỗ trợ LTS hay trạng thái bản vá bảo mật**. Những yêu cầu này cần xác minh thêm bằng cấu hình build/runtime và chính sách nhà cung cấp.

**Tài liệu tham khảo chính thức, còn áp dụng:**
- [Oracle Java SE 17 — `java` launcher, `--version`, `-version`, `--show-version`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java SE 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Oracle Java SE 17 — `Runtime.Version`, `feature()`, `update()`, `patch()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html).
- [Oracle Java SE 17 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html).
- [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322).
- [Oracle JDK Installation Guide — Version-String Format](https://docs.oracle.com/en/java/javase/17/install/version-string-format.html).
