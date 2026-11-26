# Chuyển ví dụ Java 22 sang JDK mục tiêu và quản lý yêu cầu --enable-preview

## 1. Xác định đích trước khi chuyển mã

Trong chương **Đồng thời có cấu trúc** của module `JAVA_VERSION_JAVA22`, việc đọc ví dụ Java 22 giúp hiểu nguồn gốc của cách tổ chức tác vụ. Khi áp dụng vào Java hiện đại, cần chuyển cả **hợp đồng API** lẫn **cấu hình biên dịch và thực thi**.

Bài này chọn **JDK 27 làm đích minh họa**, theo mốc tài liệu ngày 25/11/2026. Structured Concurrency trong JDK 27 vẫn là **preview lần thứ bảy**, theo JEP 533. Đừng suy ra rằng API đã chính thức chỉ vì đã xuất hiện qua nhiều phiên bản. [Oracle: thay đổi trong JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

Nếu dự án chọn JDK khác, hãy dùng Javadoc của đúng phiên bản đó. Các số `27` trong bài đi cùng API JDK 27; thay chúng bằng `25` hoặc `26` chưa tạo ra một bản chuyển đổi hợp lệ.

Hai công việc cần được phân biệt:

| Công việc | Câu hỏi cần trả lời |
| --- | --- |
| Chuyển mã nguồn | Tên kiểu, phương thức, policy, kết quả và exception đã thay đổi thế nào? |
| Quản lý preview | Compiler và các JVM nào cần bật preview, dùng JDK nào? |

Một ví dụ chỉ hoàn tất việc chuyển đổi khi cả hai phần cùng đúng.

## 2. Preview gắn với phiên bản JDK

Để biên dịch mã dùng preview của phiên bản `N`, dùng compiler JDK `N` với `--enable-preview` và `--release N` hoặc `-source N`. Khi chạy, JVM cũng phải được bật preview. Bật ở compiler không tự bật cho tiến trình chạy chương trình. [Oracle: Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html).

Với đích của bài:

```text
Mã đã chuyển sang API JDK 27
    → javac JDK 27 + --release 27 + --enable-preview
    → bytecode mới
    → JVM JDK 27 + --enable-preview
```

Không dùng `javac` JDK 27 với `--enable-preview --release 22` để yêu cầu tái hiện preview của Java 22. Khả năng biên dịch cho một bản Java cũ bằng `--release` không đồng nghĩa hỗ trợ preview cũ. [Oracle: javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

### Vì sao phải biên dịch lại?

Class file phụ thuộc preview được đánh dấu bằng minor version `65535`. JVM Java 27 chỉ chấp nhận dạng preview của chính Java 27 khi preview được bật; nó không nạp class file preview của phiên bản cũ bằng cách thêm cờ này. Vì vậy, JAR chứa bytecode preview Java 22 không trở thành ứng dụng JDK 27 chỉ nhờ đổi lệnh khởi động. [JVMS 27, §4.1](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.1).

Cần giữ mã nguồn, sửa theo API đích và tạo lại artifact. Khi chẩn đoán, hãy phân biệt bytecode quá mới đối với JVM đang chạy với bytecode preview không đúng phiên bản hoặc chưa được phép nạp.

## 3. Đọc ví dụ Java 22 để xác định policy cần giữ

Một dấu hiệu thường gặp trong ví dụ Java 22 là đoạn sau:

```java
// Dấu hiệu nhận diện API Java 22 cần chuyển.
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    // fork các tác vụ cần đủ kết quả
    scope.join().throwIfFailed();
    // đọc kết quả thành công
}
```

`ShutdownOnFailure` biểu đạt yêu cầu: cần tất cả kết quả; một tác vụ lỗi thì phần việc chưa hoàn tất không còn cần thiết. Trong API này, chờ bằng `join()` và kiểm tra thất bại bằng `throwIfFailed()` là hai thao tác tách biệt. Đoạn trên phục vụ nhận diện mã cần chuyển, không phải mẫu đích để viết chương trình mới. [Javadoc Java 22: ShutdownOnFailure](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.ShutdownOnFailure.html).

Trước khi sửa, ghi rõ ý định của ví dụ:

- Công việc cha cần mọi kết quả hay chỉ một kết quả thành công?
- Một lỗi có làm hủy các tác vụ còn lại không?
- Timeout tính theo deadline nào?
- Bên gọi đang bắt loại exception nào?

Những câu trả lời này quyết định cách chuyển. Đừng chỉ tìm và thay tên lớp.

## 4. Những điểm chuyển quan trọng sang API JDK 27

| Thành phần trong mã Java 22 | Cách thể hiện trên đích JDK 27 |
| --- | --- |
| `new StructuredTaskScope.ShutdownOnFailure()` | `StructuredTaskScope.open()` với policy mặc định cần mọi tác vụ thành công |
| `scope.join().throwIfFailed()` | `scope.join()`; policy mặc định ném `ExecutionException` nếu có tác vụ thất bại |
| Lớp con của `StructuredTaskScope` để định nghĩa policy | Thiết kế bằng `StructuredTaskScope.Joiner` theo hợp đồng đích |
| Kiểu scope với một tham số generic | API JDK 27 có `StructuredTaskScope<T, R, R_X>`; trong biến cục bộ thường dùng `var` |

Ở JDK 27, `T` mô tả kiểu kết quả tác vụ con, `R` là kết quả của join, `R_X` là kiểu exception theo joiner. `StructuredTaskScope` là interface được mở qua factory, nên thay constructor bằng factory chỉ là một phần của việc chuyển. [Javadoc JDK 27: StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

### Không đồng nhất scope cơ sở Java 22 với policy mặc định JDK 27

Scope cơ sở Java 22 chờ nhóm tác vụ và cho mã gọi tự xử lý kết quả hoặc lỗi. Nó không mặc nhiên có policy của `ShutdownOnFailure`. [Javadoc Java 22: StructuredTaskScope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Nếu mã cũ cần thu cả thành công lẫn thất bại, có thể xem xét `Joiner.<T>allUntil(task -> false)` trên JDK 27 rồi xử lý các handle theo trạng thái. Nếu chỉ cần một kết quả thành công, xem xét `Joiner.<T>anySuccessfulOrThrow()`. Nếu cần danh sách mọi giá trị thành công, `allSuccessfulOrThrow()` trả `List<T>` theo thứ tự fork. [Javadoc JDK 27: Joiner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

Đây là lựa chọn theo nghiệp vụ, không phải các phép thay thế giống nhau cho mọi ví dụ.

## 5. Ví dụ đích hoàn chỉnh trên JDK 27

Giả sử màn hình tổng quan cần tên khách hàng và số đơn hàng. Một trong hai công việc thất bại thì không tạo kết quả tổng quan. Lưu thành `MigrationDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

public class MigrationDemo {
    record Dashboard(String customer, int orders) {}

    static String loadCustomer() throws InterruptedException {
        Thread.sleep(60);
        return "Lan";
    }

    static int loadOrders(boolean fail) throws InterruptedException {
        Thread.sleep(120);
        if (fail) {
            throw new IllegalStateException("orders unavailable");
        }
        return 4;
    }

    static Dashboard loadDashboard(boolean fail)
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            Subtask<String> customer = scope.fork(MigrationDemo::loadCustomer);
            Subtask<Integer> orders = scope.fork(() -> loadOrders(fail));

            scope.join();

            return new Dashboard(customer.get(), orders.get());
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        boolean fail = args.length > 0 && args[0].equals("fail");
        System.out.println(loadDashboard(fail));
    }
}
```

Các phương thức dùng `Thread.sleep` để mô phỏng chờ; không gọi hệ thống bên ngoài.

So với dấu hiệu Java 22 ở mục 3, ví dụ đã đổi cách mở scope và đưa xử lý thất bại vào `join()`. Hai `get()` vẫn nằm sau join. Trong mã owner, `Subtask.get()` không thay thế bước chờ và chỉ đọc được kết quả thành công theo hợp đồng. [Javadoc JDK 27: Subtask](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

## 6. Chạy trực tiếp để xác nhận cấu hình JDK

Đầu tiên, kiểm tra các executable mà terminal tìm được:

```powershell
java --version
javac --version
Get-Command java, javac | Select-Object Name, Source
```

Các lệnh phía dưới giả định cả `java` lẫn `javac` đều thuộc JDK 27. Biên dịch vào thư mục đầu ra riêng:

```powershell
javac --enable-preview --release 27 -encoding UTF-8 -d out MigrationDemo.java
java --enable-preview --class-path out MigrationDemo
```

Kết quả dự kiến:

```text
Dashboard[customer=Lan, orders=4]
```

Quan sát nhánh thất bại:

```powershell
java --enable-preview --class-path out MigrationDemo fail
```

Lần này chương trình không in một `Dashboard` thành công; exception từ join có nguyên nhân là lỗi `orders unavailable`. Stack trace cụ thể có thể khác giữa các bản JDK.

Có thể dùng `-Xlint:preview` khi biên dịch để xem vị trí sử dụng preview:

```powershell
javac --enable-preview --release 27 -Xlint:preview -d out MigrationDemo.java
```

`-Xlint:preview` phục vụ chẩn đoán; nó không thay thế `--enable-preview`. [Oracle: tùy chọn javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

Khi chạy từ nguồn, compiler được launcher gọi trong cùng chế độ:

```powershell
java --enable-preview --source 27 MigrationDemo.java
```

Nếu đã đóng gói ứng dụng thành JAR có điểm vào, cờ vẫn thuộc JVM:

```powershell
java --enable-preview -jar application.jar
```

Các tùy chọn launcher đặt trước tên lớp, tên tệp nguồn hoặc `-jar`. Cờ đặt sau tên lớp hay JAR trở thành đối số chương trình và không bật preview cho JVM. [Oracle: lệnh java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

## 7. Chuyển timeout và xử lý lỗi theo API đích

Ví dụ Java 22 có thể dùng `joinUntil(Instant deadline)`. Đích JDK 27 cấu hình timeout bằng `Configuration.withTimeout(Duration)` khi mở scope. Nếu cần giữ deadline tuyệt đối, tính ngân sách còn lại gần lúc mở scope và xử lý trường hợp đã hết hạn; không chỉ đổi tên phương thức. [Javadoc Java 22: joinUntil](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.ShutdownOnFailure.html#joinUntil(java.time.Instant)), [Javadoc JDK 27: Configuration](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html).

Ví dụ phương thức bổ sung trong `MigrationDemo`, thêm import `java.time.Duration`:

```java
static Dashboard loadDashboard(Duration timeout, boolean fail)
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open(
            config -> config.withTimeout(timeout))) {
        Subtask<String> customer = scope.fork(MigrationDemo::loadCustomer);
        Subtask<Integer> orders = scope.fork(() -> loadOrders(fail));

        scope.join();
        return new Dashboard(customer.get(), orders.get());
    }
}
```

Trên policy mặc định JDK 27, timeout dẫn tới `ExecutionException` có cause là `StructuredTaskScope.CancelledByTimeoutException`. Vì vậy, nhánh bắt `TimeoutException` của mã Java 22 cần được xem lại cùng lời gọi chờ. [Javadoc JDK 27: CancelledByTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Không dùng thời lượng cấu hình làm cam kết về thời gian tối đa của cả phương thức. `close()` vẫn chờ các luồng con kết thúc; tác vụ cần phản hồi interruption để việc dọn scope có thể hoàn tất. [Javadoc JDK 27: close](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()).

## 8. Maven: cấu hình compiler và JVM test riêng

Nếu đưa ví dụ vào dự án Maven, đặt nguồn ở `src/main/java/MigrationDemo.java`. Đoạn cấu hình dưới đây dành cho Maven chạy bằng **JDK 27**, không có toolchain hoặc JVM test ghi đè sang JDK khác. Ghép vào các phần tương ứng của POM hiện có:

```xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <enablePreview>true</enablePreview>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <argLine>--enable-preview</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Compiler Plugin cung cấp `enablePreview` và cấu hình release; điều này không cấu hình JVM test. Surefire truyền `argLine` cho JVM được fork để chạy test. Nếu dự án đã dùng `argLine` cho agent hoặc coverage, ghép thêm cờ vào cấu hình hiện có. [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html), [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html).

Kiểm tra JDK thực sự bằng `mvn --version`. Nếu dùng toolchain, kiểm tra thêm compiler và JVM test do toolchain chọn; không suy ra chúng từ riêng phiên bản JVM chạy Maven.

`argLine` chỉ có tác dụng với test được fork. Nếu cấu hình chạy test ngay trong JVM Maven, cờ phải có từ lúc khởi động JVM đó. Với integration test chạy bằng một runner khác, cấu hình tương ứng cho runner ấy. Cấu hình test cũng không tự truyền vào lệnh chạy JAR khi triển khai.

## 9. Gradle: toolchain và ba loại task

Với Gradle, phân biệt JDK chạy Gradle với toolchain biên dịch/chạy mã dự án. Bảng tương thích chính thức ghi nhận hỗ trợ Java 27 từ Gradle **9.8.0** cho toolchain và chạy Gradle. Hãy đối chiếu phiên bản wrapper của dự án. [Gradle: Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

Ví dụ `build.gradle.kts` cho ứng dụng học tập, nguồn đặt ở `src/main/java/MigrationDemo.java`:

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(27))
    }
}

application {
    mainClass.set("MigrationDemo")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
```

`JavaCompile` áp dụng cho biên dịch, `Test` cho JVM test và `JavaExec` cho các lần chạy theo loại task đó. Chỉ cấu hình compiler là chưa đủ. [Gradle: bật Java preview features](https://docs.gradle.org/current/userguide/building_java_projects.html#sec:java_preview_features).

Với ví dụ này, task `run` dùng cấu hình `JavaExec`. Nếu phân phối bằng start script hoặc một entrypoint bên ngoài Gradle, thêm cờ vào cấu hình khởi chạy tương ứng; việc task `run` thành công không chứng minh lệnh triển khai đã có cờ.

## 10. IDE, CI và môi trường chạy phải cùng hợp đồng

Có thể dùng bảng sau làm bản ghi cấu hình của ứng dụng mẫu:

| Thành phần | Giá trị cần xác nhận |
| --- | --- |
| API tham chiếu | Javadoc JDK 27 |
| Compiler thực sự | JDK 27 |
| Mức release | `27` |
| Tùy chọn compiler | Có `--enable-preview` |
| JVM test | JDK 27, có `--enable-preview` |
| JVM ứng dụng | JDK 27, có `--enable-preview` |
| Build tool | Phiên bản tương thích; toolchain được kiểm soát |

Trong IDE, SDK dự án, mức ngôn ngữ, cấu hình test và VM options của ứng dụng là các thiết lập cần kiểm tra riêng. Không đặt cờ JVM vào ô đối số chương trình.

Trong CI, ghi nhận JDK được chọn cho compiler và test, sau đó build lại từ nguồn. Khi chuyển JDK, tránh trộn đầu ra biên dịch của nhiều phiên bản trong cùng artifact. Môi trường chạy phải được kiểm tra bằng chính entrypoint dùng để khởi động ứng dụng, thay vì dựa vào một lần chạy thành công trong IDE.

Một sự cố điển hình là máy phát triển biên dịch được, CI test được nhưng container thất bại. Khi đó, kiểm tra JVM và tham số của container trước khi thay đổi logic tác vụ.

## 11. Chẩn đoán theo lớp lỗi

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Không tìm thấy `ShutdownOnFailure` trên JDK đích | Mã vẫn dùng API Java 22; chuyển API theo policy |
| Không thể dùng `join().throwIfFailed()` | Hợp đồng join của đích đã khác; tách việc đọc kết quả và xử lý exception đúng phiên bản |
| Compiler báo preview chưa được bật | Kiểm tra lệnh compiler thực sự và `enablePreview`/compiler arguments |
| Báo preview chỉ được hỗ trợ cho release hiện tại | Đối chiếu compiler với release; không bật preview cũ qua compiler mới |
| Chạy báo không cho phép class file preview | Kiểm tra JVM nhận `--enable-preview` và đúng feature version |
| Test lỗi nhưng compile thành công | Kiểm tra JVM test riêng, đặc biệt Surefire hoặc Gradle `Test` |
| JVM không hỗ trợ phiên bản class file | Kiểm tra JDK đã tạo bytecode và JVM thực sự đang nạp nó |
| Chạy được nhưng kết quả hoặc cách hủy đã đổi | So sánh policy, outcome, timeout và cause của exception |

Với class file cần điều tra, có thể xem thông tin phiên bản bằng công cụ `javap` của JDK:

```powershell
javap -verbose -classpath out MigrationDemo |
    Select-String 'major version|minor version'
```

Đánh dấu preview là đặc điểm của class file phụ thuộc preview, không phải bằng chứng mọi lớp trong cùng JAR đều được đánh dấu giống nhau. Dùng kết quả này để đối chiếu quy tắc nạp class file, không để sửa bytecode nhằm bỏ yêu cầu preview.

## 12. Đánh giá kết quả chuyển đổi theo hành vi

Đối với ví dụ `MigrationDemo`, một lượt kiểm tra chuyển đổi nên bao gồm các tình huống sau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Cả hai tác vụ thành công | Tạo đúng `Dashboard`; không đọc handle trước join |
| Tác vụ đơn hàng thất bại | Không tạo kết quả thành công; giữ nguyên nhân lỗi để bên gọi xử lý |
| Owner bị interrupt hoặc scope hết hạn | Hành vi dừng và kiểu lỗi phù hợp hợp đồng đích |
| Tác vụ đang dọn tài nguyên khi bị hủy | Phạm vi không kết thúc trước khi luồng con dừng |
| Chạy bằng entrypoint triển khai | Đúng JDK và cờ preview, không chỉ đúng trong IDE |

Nếu môi trường dự án không cho phép preview, cần chọn cách triển khai bằng API đã ổn định và thiết kế quản lý tác vụ tương ứng. Việc xóa riêng cờ không biến mã còn tham chiếu Structured Concurrency preview thành mã ổn định.

Khi một phiên bản đích tương lai chính thức hóa tính năng, hãy kiểm tra tài liệu và mọi chỗ dùng preview khác trước khi bỏ cờ, rồi biên dịch lại. Quyết định đó dựa trên API và artifact thực tế của dự án, không dựa riêng vào tên tính năng trong bài Java 22.
