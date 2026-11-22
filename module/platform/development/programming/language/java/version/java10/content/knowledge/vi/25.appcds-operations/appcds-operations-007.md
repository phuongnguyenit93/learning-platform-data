# Chế độ `-Xshare:on` trong kiểm tra yêu cầu dùng kho lưu trữ CDS/AppCDS

**Chủ đề:** Vận hành AppCDS — Java 10 và các JDK hiện đại.

**`-Xshare:on` là chế độ kiểm tra nghiêm ngặt (*fail-fast*) đối với Class Data Sharing (CDS).** Khi dùng cờ này, HotSpot JVM được yêu cầu **phải sử dụng được dữ liệu lớp chia sẻ**; nếu CDS archive cần thiết không dùng được, JVM sẽ báo lỗi và **thoát ngay khi khởi tạo**, thay vì lặng lẽ chạy như khi không có archive. Đây là cơ chế hữu ích cho **kiểm thử quy trình tạo và sử dụng CDS/AppCDS archive**, nhưng **không nên dùng mặc định trong production**.

Điểm phân biệt quan trọng: **`-Xshare:on` không tự tạo archive, cũng không tự đảm bảo từng lớp ứng dụng đã được archive**. Nó yêu cầu CDS khả dụng theo cấu hình. Nếu bạn muốn chứng minh **AppCDS** thực sự giúp tải một lớp ứng dụng như `ArchiveCheck` từ archive, phải thêm `-XX:SharedArchiveFile=app.jsa` phù hợp và **kiểm tra log class loading của chính lớp ứng dụng đó**.

AppCDS (*Application Class-Data Sharing*) được giới thiệu trong **Java 10 (JEP 310)** để mở rộng chia sẻ dữ liệu lớp tới các lớp do ứng dụng/thư viện cung cấp. Ý tưởng CDS và chế độ `-Xshare:on` vẫn có trong JDK hiện hành. Trong bài, mã ứng dụng được kiểm thử với `javac --release 10`; riêng quy trình tạo **dynamic archive** `-XX:ArchiveClassesAtExit` có từ **JDK 13**, vì vậy cần runtime JDK 13+ để làm theo toàn bộ thí nghiệm. Thí nghiệm đã chạy thành công trên **OpenJDK 24.0.2**.

## 1. Ba chế độ CDS cần biết

Launcher `java` có nhóm lựa chọn `-Xshare:mode`:

| Chế độ | Hành vi | Nếu archive không sử dụng được | Phạm vi sử dụng |
| --- | --- | --- | --- |
| `-Xshare:auto` | Thử dùng shared class data nếu có thể; đây là chế độ mặc định trong phần lớn JDK hiện đại | Có thể **bỏ qua archive và tiếp tục khởi động ứng dụng** | **Phù hợp vận hành thông thường** khi cần fallback |
| **`-Xshare:on`** | **Yêu cầu CDS phải hoạt động** | **In lỗi và thoát khỏi quá trình khởi tạo JVM** | **Kiểm thử/diagnostic**, không phải cờ mặc định production |
| `-Xshare:off` | Không sử dụng class data sharing | Chạy theo đường tải class thông thường, không dùng archive | **Baseline/đối chứng** và điều tra lỗi CDS |

Ngoài ba chế độ trên, `-Xshare:dump` có mục đích **tạo static CDS archive**, không phải cách diễn đạt “bật CDS nghiêm ngặt” để chạy ứng dụng. Phải phân biệt `dump` với `on`.

### Khi nào lựa chọn nghiêm ngặt hữu ích?

Một pipeline CI tạo `app.jsa` từ đúng JAR, rồi khởi chạy:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

Nếu JVM không sử dụng được archive, việc trả về mã lỗi khác 0 giúp **phát hiện lỗi triển khai ngay tại bước kiểm thử**. Không phải đợi đo startup nhanh/chậm một cách không chắc chắn.

Tuy nhiên, nếu chỉ chạy:

~~~bash
java -Xshare:on -cp app.jar ArchiveCheck
~~~

và JDK có default CDS archive hợp lệ, JVM có thể chạy thành công **dù `ArchiveCheck` vẫn được đọc từ `app.jar`**. Đây là lý do **không nên coi exit code 0 của `-Xshare:on` là một phép kiểm tra đầy đủ rằng lớp ứng dụng đang được AppCDS chia sẻ**.

## 2. “Kho” ở đây là dữ liệu gì?

Trong bối cảnh Java CDS, **archive** là tệp chứa dữ liệu lớp đã được JVM chuẩn bị sẵn, thường có phần mở rộng `.jsa`. JVM có thể ánh xạ một phần dữ liệu đó từ file thay vì lặp lại toàn bộ công việc chuẩn bị metadata class ở mỗi lần chạy.

~~~text
ỨNG DỤNG KHÔNG DÙNG ARCHIVE
  app.jar -> đọc class -> JVM xử lý metadata -> main()

ỨNG DỤNG DÙNG APP CDS
  app.jar + app.jsa
          |
          | JVM kiểm tra tính tương thích của archive
          v
       Nạp dữ liệu class từ shared archive khi phù hợp
          |
          +-> Những class không có trong archive vẫn tải bình thường
          v
         main()

VỚI -Xshare:on VÀ ARCHIVE BỊ THIẾU/SAI
  JVM khởi tạo -> không dùng được shared archive -> lỗi + exit
  main() KHÔNG được chạy trong ca kiểm thử lỗi khởi tạo
~~~

Điểm cần hiểu:

- **CDS** giúp chia sẻ dữ liệu cấu trúc lớp phù hợp, thường giảm một phần startup time và có thể giảm memory footprint giữa nhiều JVM trên cùng host.
- **AppCDS** mở rộng phạm vi dữ liệu lớp sang **application/library classes**; nó không biến object trên Java heap thành trạng thái chia sẻ giữa các tiến trình.
- **`-Xshare:on`** là điều kiện về **khả năng dùng CDS**, không phải cờ tạo archive, không phải trình benchmark và không phải công cụ bắt buộc mọi class đều đã vào archive.
- Tệp `app.jsa` gắn với **JDK build** và các điều kiện về classpath/JAR/module path; không có cam kết một tệp archive chạy được trên mọi JDK, hệ điều hành hoặc bản ứng dụng.

### Default CDS archive không phải custom AppCDS archive

Nhiều bản JDK hiện đại có **default CDS archive** của các lớp nền tảng, thường đi kèm JDK. Trong cấu hình đó:

- Chạy `java -Xshare:on -cp app.jar ArchiveCheck` có thể thành công do **archive mặc định của JDK** sử dụng được.
- Thành công trên **không tự nói rằng `ArchiveCheck` và lớp con của nó ở trong archive**.
- Để kiểm tra AppCDS, hãy tạo hoặc cung cấp **archive ứng dụng** rồi kiểm tra `source` trong `-Xlog:class+load=info` cho class cần quan tâm.

**Ghi nhớ:** “**yêu cầu có CDS**” và “**chứng minh các lớp ứng dụng đang dùng AppCDS**” là hai mệnh đề khác nhau. Cả hai đều có thể hữu ích trong QA, nhưng phải có phép thử tương ứng.

## 3. Chương trình Java 10 dùng để kiểm tra

Tạo file **`ArchiveCheck.java`**:

~~~java
public class ArchiveCheck {
    static final class Service {
        String greet() {
            return "Hello, AppCDS";
        }
    }

    public static void main(String[] args) {
        System.out.println("app-started=true");
        System.out.println("message=" + new Service().greet());
    }
}
~~~

Chương trình cố tình đơn giản:

- `ArchiveCheck` là **class ứng dụng**, không phải class lõi của JDK.
- `ArchiveCheck.Service` là một class do ứng dụng tự định nghĩa và được nạp khi dùng lần đầu.
- `app-started=true` là **dấu hiệu kiểm tra `main()` đã chạy**. Nếu JVM thoát trước khi khởi tạo do chế độ CDS nghiêm ngặt, dấu hiệu này **không được xuất hiện**.
- `message=Hello, AppCDS` giúp xác nhận logic ứng dụng vẫn hoạt động giống nhau khi có/không có CDS.

### Biên dịch ở mức source/API Java 10

Tại thư mục có `ArchiveCheck.java`, chạy:

~~~bash
javac --release 10 ArchiveCheck.java
jar --create --file app.jar ArchiveCheck.class ArchiveCheck$Service.class
~~~

**Lưu ý về shell:** ở Unix shell, ký tự `$` có thể bị coi là phép thay biến; khi chạy lệnh `jar` thủ công trên bash, đặt tên class chứa `$` trong dấu nháy đơn: `'ArchiveCheck$Service.class'`. Trên PowerShell cũng nên đặt tên này trong nháy đơn cho rõ. Nếu shell xử lý `$` khác nhau, dùng lệnh tạo JAR theo cách bao trọn thư mục build mà không làm thay đổi tên file.

Một cách **cross-platform an toàn hơn** là biên dịch vào thư mục `classes` rồi đóng gói toàn bộ:

~~~bash
mkdir classes
javac --release 10 -d classes ArchiveCheck.java
jar --create --file app.jar -C classes .
~~~

**Đây là bộ lệnh nên dùng cho bài thực hành.** Trên Windows PowerShell, `mkdir` tạo thư mục; nếu `classes` đã có sẵn, không cần tạo lại. Trên Unix tương tự.

`--release 10` chỉ xác lập mục tiêu **cú pháp, bytecode và API công khai** khi biên dịch. Nó **không biến JDK 10 thành JDK 13** và không làm cờ `ArchiveClassesAtExit` xuất hiện trên runtime Java 10. Phần AppCDS dynamic bên dưới phải chạy bằng **JDK runtime có hỗ trợ cờ này**.

### Chạy không dùng chia sẻ để có baseline

~~~bash
java -Xshare:off -cp app.jar ArchiveCheck
~~~

**Stdout:**

~~~text
app-started=true
message=Hello, AppCDS
~~~

Các dòng stdout này **không đổi** khi dùng đúng archive. AppCDS nhằm giảm công việc chuẩn bị lớp, chứ không đổi kết quả logic của `main()`.

## 4. Tạo archive ứng dụng bằng dynamic AppCDS (JDK 13+)

Một cách dễ kiểm tra `-Xshare:on` là tạo **dynamic archive** từ chính lần chạy ứng dụng.

### Bước 1 — Training run

~~~bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar ArchiveCheck
~~~

Ứng dụng in:

~~~text
app-started=true
message=Hello, AppCDS
~~~

Sau khi JVM thoát bình thường và việc tạo archive thành công, tệp **`app.jsa`** xuất hiện. Tệp thường chứa dữ liệu các lớp đủ điều kiện được nạp trong lần chạy thử. **Đừng giả định mọi class trong JAR đều được đưa vào archive**; đây là lý do nên tập cho training workload đi qua code quan trọng.

**Điều kiện chính:** cùng JDK build phù hợp, cùng JAR và classpath theo quy định, ứng dụng thoát theo cách cho phép dump archive, đường dẫn có quyền ghi và không có cấu hình làm vô hiệu CDS.

### Bước 2 — Chạy với archive và chế độ bắt buộc

~~~bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

Nếu archive dùng được, **exit code là 0** và stdout vẫn là:

~~~text
app-started=true
message=Hello, AppCDS
~~~

Trong môi trường kiểm thử JDK 24.0.2, cặp lệnh training/replay trên đã thành công. Nhưng để biết **lớp ứng dụng thực sự được chia sẻ**, phải xem nguồn class trong log.

### Bước 3 — Xác nhận các class ứng dụng load từ archive

~~~bash
java -Xshare:on -Xlog:class+load=info:file=cds-loaded.log:tags,level -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

Mở `cds-loaded.log`, tìm dòng chứa `ArchiveCheck`. Kết quả trong thí nghiệm JDK 24.0.2:

~~~text
[info][class,load] ArchiveCheck source: shared objects file (top)
[info][class,load] ArchiveCheck$Service source: shared objects file (top)
~~~

`source: shared objects file (top)` là dấu hiệu **lớp ứng dụng được tải từ tầng archive động**. Tên hiển thị hoặc hậu tố `(top)` có thể phụ thuộc loại archive và phiên bản JVM; cần tìm ý nghĩa nguồn class, không bắt mọi JDK phải in đúng nguyên văn tất cả chuỗi log.

**Nếu chỉ có log cho `java.lang.String` hoặc các lớp lõi được chia sẻ, điều đó chưa đủ để xác nhận AppCDS chứa class ứng dụng.** Phép thử này cần tìm **`ArchiveCheck` và `ArchiveCheck$Service`**.

## 5. Kiểm thử lỗi cố ý: archive không tồn tại

Phần quan trọng nhất của `-Xshare:on` là hành vi **không fallback**.

Giả sử thư mục đang chạy **chưa có** file `not-created.jsa`. Chạy:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=not-created.jsa -cp app.jar ArchiveCheck
~~~

**Kỳ vọng chính xác về hành vi:**

1. JVM không thể sử dụng archive được yêu cầu.
2. Startup JVM thất bại, **exit code khác 0**.
3. Phần thân `main()` **không được chạy**: stdout ứng dụng không có `app-started=true`.
4. JVM in thông báo lỗi khởi tạo hoặc lỗi archive. **Không được hard-code chính xác từng chữ của thông báo**, vì có thể khác theo JDK/platform.

**Ví dụ thông báo quan sát trên OpenJDK 24.0.2:**

~~~text
Error occurred during initialization of VM
Unable to use shared archive: invalid archive
Class data sharing is inconsistent with other specified options.
~~~

Thí nghiệm ghi nhận mã thoát **1** trên JDK kiểm thử, nhưng unit/integration test nên assert **`exitCode != 0`**, thay vì mặc định mọi JDK và mọi lỗi đều trả đúng số 1.

### Vì sao thử nghiệm “missing archive” tốt cho CI?

- **Có tính quyết định:** không phụ thuộc đo thời gian startup hay trạng thái warm cache.
- **Có thể kiểm tra tự động:** mã thoát khác 0 và sentinel từ `main()` không xuất hiện.
- **Chứng minh ý nghĩa `-Xshare:on`:** cùng JAR và cùng JDK, thay đổi duy nhất là archive cần thiết bị thiếu.
- **Nhưng không đủ chứng minh AppCDS class coverage:** một archive hợp lệ có thể được JVM sử dụng thành công dù không chứa mọi class ứng dụng. Thử nghiệm positive phải thêm kiểm tra `class+load`.

**Không cố tạo hoặc ghi đè file system không thuộc quyền thử nghiệm.** Chỉ thực hiện các ca negative trong thư mục tạm, tên archive riêng và có dọn dẹp. Với production, **không dùng `-Xshare:on` như health check thường trực** vì một cache thiếu có thể làm dịch vụ không khởi động.

## 6. So sánh trực tiếp với `-Xshare:auto` khi archive thiếu

Dùng cùng JAR, cùng file archive không tồn tại, đổi `on` thành `auto`:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=not-created.jsa -cp app.jar ArchiveCheck
~~~

**Trên JDK 24.0.2 đã kiểm thử**, ứng dụng **vẫn chạy**, có exit code 0 và in:

~~~text
app-started=true
message=Hello, AppCDS
~~~

Diễn giải: chế độ `auto` **cho phép JVM tiếp tục không dùng custom archive khi archive đó không khả dụng**. Điều này là hành vi fallback có ích trong production, nhưng **không có nghĩa JVM đã dùng AppCDS**. Với một default CDS archive khác, JVM có thể dùng chia sẻ lớp nền tảng hoặc không; chỉ dựa vào stdout thì không biết.

Đừng ghép `-Xshare:auto` với giả định nó sẽ **tự tạo file bị thiếu**. `auto` chỉ điều khiển chế độ **thử dùng chia sẻ**. Muốn tự động tạo dynamic archive khi chưa có, JDK hiện đại có cờ riêng:

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=app-auto.jsa -cp app.jar ArchiveCheck
~~~

`-XX:+AutoCreateSharedArchive` có từ **JDK 19**. Nó có workflow tạo archive lúc thoát nếu cần, khác với `-Xshare:auto`; **không dùng cờ JDK 19 trên Java 10**. Chi tiết trường hợp archive cũ/không tương thích và thời điểm tạo lại phụ thuộc JDK, nên luôn đối chiếu tài liệu runtime đang dùng.

### Dùng `-Xshare:off` làm đối chứng

~~~bash
java -Xshare:off -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

Trong thí nghiệm JDK 24.0.2, dù `app.jsa` **tồn tại và hợp lệ**, `-Xshare:off` làm ứng dụng chạy **không sử dụng dữ liệu lớp chia sẻ**. Khi bật log class load, `ArchiveCheck` và class `Service` được nạp từ file `app.jar`, không từ `shared objects file`.

Tuy nhiên, `-Xshare:off` chỉ là **chế độ đối chứng/diagnostic**, không phải đề nghị tối ưu hiệu năng cho ứng dụng chạy bình thường.

## 7. Ma trận kiểm thử có thể dùng cho QA

| Case | Lệnh CDS | Archive được chỉ định | Kết quả kỳ vọng | Điều case chứng minh |
| --- | --- | --- | --- | --- |
| 1 | `-Xshare:off` | Không yêu cầu | Exit 0, `main` chạy | Baseline không dùng CDS |
| 2 | Training `-XX:ArchiveClassesAtExit=app.jsa` | Tạo từ workload ứng dụng | Exit 0, file archive xuất hiện | Quy trình tạo archive hoạt động |
| 3 | `-Xshare:on` | `app.jsa` hợp lệ | Exit 0, `main` chạy | CDS bắt buộc dùng được |
| 4 | `-Xshare:on` + `-Xlog:class+load=info` | `app.jsa` hợp lệ | Class `ArchiveCheck` xuất hiện với source shared archive | AppCDS thực sự chứa class ứng dụng |
| 5 | `-Xshare:on` | `not-created.jsa` thiếu | Exit khác 0, `main` không chạy | **Chế độ nghiêm ngặt không fallback** |
| 6 | `-Xshare:auto` | `not-created.jsa` thiếu | Exit 0, `main` chạy trong môi trường kiểm thử | Fallback khi cache không sẵn có |
| 7 | `-Xshare:off` | `app.jsa` hợp lệ | Exit 0; class ứng dụng tải từ JAR | Cờ `off` vô hiệu chia sẻ |
| 8 | `-Xshare:on` | Không chỉ định archive ứng dụng | Có thể exit 0 nhờ default CDS, nhưng class app từ JAR | **CDS thành công không suy ra AppCDS thành công** |

**Đọc ma trận cẩn thận:** dòng 8 phụ thuộc môi trường có **default CDS archive** hợp lệ, phổ biến trên nhiều JDK hiện đại; không áp đặt cho mọi bản phân phối/VM. Trên JDK 24.0.2 trong thí nghiệm, dòng này exit 0 nhưng class `ArchiveCheck` được tải từ JAR.

Một phép QA mạnh thường cần **cả negative test số 5** và **positive test số 4**: một bên đảm bảo **không fallback khi yêu cầu**, một bên đảm bảo **đúng lớp ứng dụng đã vào archive**.

## 8. Chương trình Java 10 kiểm thử tự động các chế độ

Nếu muốn đưa hành vi của `-Xshare:on` vào test có thể chạy lại, thay vì kiểm tra bằng mắt, hãy dùng `ProcessBuilder` của Java standard library. Chương trình bên dưới khởi tạo các tiến trình JVM con, lấy exit code và đọc log. Nó **không** sửa cấu hình global của JVM đang chạy test.

### Chuẩn bị

- Đặt file `ArchiveCheck.java` ở mục 3 cùng thư mục với file `CdsModeHarness.java`.
- Biên dịch cả hai bằng JDK hỗ trợ `--release 10`.
- Tạo `app.jar` chỉ chứa class `ArchiveCheck` và class lồng `Service`.
- Chạy `CdsModeHarness` trong thư mục chứa `app.jar`, đồng thời bảo đảm chưa có file `not-created.jsa`.
- Runtime dùng cho test phải là **JDK 13+** vì workflow dynamic archive và hỗ trợ `-Xlog`; bài đã thử trên JDK 24.0.2.

### Tệp `CdsModeHarness.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class CdsModeHarness {
    static final class Result {
        final int exitCode;
        final String output;

        Result(int exitCode, String output) {
            this.exitCode = exitCode;
            this.output = output;
        }

        boolean mainRan() {
            return output.contains("app-started=true");
        }

        boolean applicationClassShared() {
            return output.contains(
                    "ArchiveCheck source: shared objects file");
        }
    }

    static Result run(String... args) throws Exception {
        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";

        List<String> command = new ArrayList<>();
        command.add(Paths.get(
                System.getProperty("java.home"),
                "bin", executable).toString());
        command.addAll(Arrays.asList(args));

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        ByteArrayOutputStream captured = new ByteArrayOutputStream();
        try (InputStream input = process.getInputStream()) {
            byte[] buffer = new byte[4096];
            int amount;
            while ((amount = input.read(buffer)) != -1) {
                captured.write(buffer, 0, amount);
            }
        }

        int exitCode = process.waitFor();
        return new Result(exitCode, new String(
                captured.toByteArray(), StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        Result baseline = run(
                "-Xshare:off",
                "-cp", "app.jar", "ArchiveCheck");

        Result train = run(
                "-XX:ArchiveClassesAtExit=app.jsa",
                "-cp", "app.jar", "ArchiveCheck");

        Result strict = run(
                "-Xshare:on",
                "-Xlog:class+load=info",
                "-XX:SharedArchiveFile=app.jsa",
                "-cp", "app.jar", "ArchiveCheck");

        Result missingStrict = run(
                "-Xshare:on",
                "-XX:SharedArchiveFile=not-created.jsa",
                "-cp", "app.jar", "ArchiveCheck");

        Result missingAuto = run(
                "-Xshare:auto",
                "-XX:SharedArchiveFile=not-created.jsa",
                "-cp", "app.jar", "ArchiveCheck");

        Result existingOff = run(
                "-Xshare:off",
                "-Xlog:class+load=info",
                "-XX:SharedArchiveFile=app.jsa",
                "-cp", "app.jar", "ArchiveCheck");

        Result defaultOn = run(
                "-Xshare:on",
                "-Xlog:class+load=info",
                "-cp", "app.jar", "ArchiveCheck");

        System.out.println("baseline-ok=" +
                (baseline.exitCode == 0 && baseline.mainRan()));

        System.out.println("archive-created=" +
                (train.exitCode == 0
                        && Files.isRegularFile(Paths.get("app.jsa"))));

        System.out.println("strict-valid-ok=" +
                (strict.exitCode == 0 && strict.mainRan()));

        System.out.println("strict-app-class-shared=" +
                strict.applicationClassShared());

        System.out.println("strict-missing-fails=" +
                (missingStrict.exitCode != 0));

        System.out.println("strict-missing-main-not-run=" +
                !missingStrict.mainRan());

        System.out.println("auto-missing-fallback=" +
                (missingAuto.exitCode == 0 && missingAuto.mainRan()));

        System.out.println("off-valid-archive-ignored=" +
                (existingOff.exitCode == 0
                        && existingOff.mainRan()
                        && !existingOff.applicationClassShared()));

        System.out.println("default-on-not-appcds-proof=" +
                (defaultOn.exitCode == 0
                        && defaultOn.mainRan()
                        && !defaultOn.applicationClassShared()));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
mkdir classes
javac --release 10 -d classes ArchiveCheck.java CdsModeHarness.java
jar --create --file app.jar -C classes .
java -cp classes CdsModeHarness
~~~

Nếu trước đó đã tạo thư mục `classes`, chỉ cần dùng lại. Với demo này, cả `ArchiveCheck` và `CdsModeHarness` nằm trong `classes`; việc đóng cả hai vào JAR **không làm thay đổi logic kiểm thử**, dù cũng có thể tạo JAR chỉ chứa `ArchiveCheck.class` và `ArchiveCheck$Service.class`. Nếu đóng toàn bộ vào JAR như lệnh trên, JVM training chỉ archive class thực sự được nạp bởi ứng dụng, không có nghĩa mọi class trong JAR đều tự động được archive.

**Stdout đã kiểm chứng trên OpenJDK 24.0.2:**

~~~text
baseline-ok=true
archive-created=true
strict-valid-ok=true
strict-app-class-shared=true
strict-missing-fails=true
strict-missing-main-not-run=true
auto-missing-fallback=true
off-valid-archive-ignored=true
default-on-not-appcds-proof=true
~~~

### Đọc từng assertion

- `baseline-ok=true`: ứng dụng chạy bình thường khi tắt CDS.
- `archive-created=true`: training run thành công và tạo `app.jsa`.
- `strict-valid-ok=true`: `-Xshare:on` với archive hợp lệ chạy được.
- `strict-app-class-shared=true`: unified logging nhìn thấy `ArchiveCheck` có nguồn `shared objects file`.
- `strict-missing-fails=true`: archive bị thiếu khiến JVM nghiêm ngặt trả exit code khác 0.
- `strict-missing-main-not-run=true`: sentinel của `main()` không xuất hiện ở lần khởi tạo thất bại.
- `auto-missing-fallback=true`: `-Xshare:auto` cho phép ứng dụng chạy trong thử nghiệm dù không có custom archive.
- `off-valid-archive-ignored=true`: có file archive nhưng `-Xshare:off` không dùng nó.
- `default-on-not-appcds-proof=true`: `-Xshare:on` chỉ dùng default CDS vẫn có thể chạy mà lớp `ArchiveCheck` không lấy từ archive ứng dụng.

**Giới hạn portability:** assertion cuối được thiết kế để chứng minh trạng thái **JDK 24.0.2 với default CDS archive bình thường và JAR kiểm thử không có sẵn trong default archive**. Nó **không phải một bất biến mà mọi JDK phải in `true`**. Các assertion liên quan source log cũng phụ thuộc cách JVM ghi unified logging. Nếu viết bộ kiểm thử cho đa vendor, hãy bổ sung điều kiện nhận biết implementation và dùng log token phù hợp.

Với ứng dụng lớn, `-Xlog:class+load=info` có thể sinh lượng log rất nhiều. Harness ở đây thu log trong bộ nhớ vì **demo cực nhỏ**; test thực tế nên ghi vào file, giới hạn log hoặc sử dụng công cụ chuyên dụng thay vì thu không giới hạn stdout/stderr vào `ByteArrayOutputStream`.

## 9. Sự khác nhau giữa thành công của JVM và độ phủ archive ứng dụng

Một archive dùng được không cần chứa **mọi class trong JAR**. Những class chưa xuất hiện trong training workload hoặc không đủ điều kiện có thể được nạp bình thường từ JAR trong lúc JVM vẫn dùng CDS cho các class khác.

Vì thế, trong một bài kiểm tra có thể tách thành các mức:

| Mức kiểm tra | Phép đo | Mệnh đề có thể khẳng định |
| --- | --- | --- |
| A — Có CDS khả dụng | `-Xshare:on` kết thúc thành công với archive tương thích | Có thể sử dụng một CDS archive phù hợp |
| B — Có đúng archive ứng dụng | `-XX:SharedArchiveFile=app.jsa`, không lỗi sử dụng archive | Archive được yêu cầu không bị từ chối trong cấu hình |
| C — Lớp ứng dụng quan trọng được chia sẻ | `-Xlog:class+load` cho `ArchiveCheck` và `Service` có `source: shared objects file` | **Những class được kiểm tra** thực sự lấy từ archive |
| D — Ứng dụng đúng chức năng | Exit 0, stdout/functional test phù hợp | Kết quả chương trình sau khi dùng CDS vẫn đúng |
| E — Có lợi ích hiệu năng | Benchmark lặp lại với baseline tương đương | Tác động hiệu năng đo được trong workload cụ thể |

**Không nhảy từ A hoặc B sang E**: test nghiêm ngặt không phải phép đo hiệu năng, cũng không bảo đảm mọi class được chia sẻ. Một archive rất lớn cũng không chứng minh ứng dụng chắc chắn nhanh hơn.

### Khi thử nghiệm với JAR không đổi

Để so sánh đúng, giữ cố định:

- **JDK distribution/build**: dùng cùng runtime build khi training và replay.
- **Class path/JAR contents**: không cập nhật lại `app.jar` sau khi tạo `app.jsa` mà chưa tạo lại archive.
- **Tham số module và JVM quan trọng**: các lựa chọn có thể ảnh hưởng tính tương thích của cache.
- **Workload startup**: không so lần gọi database khác nhau rồi quy toàn bộ chênh lệch cho CDS.
- **OS/kiến trúc và container image**: archive của một môi trường không có bảo đảm portable sang môi trường khác.
- **Chế độ log**: bật log để xác nhận; tắt logging nhiều dòng trong các lần benchmark latency thực tế.

## 10. Những trường hợp `-Xshare:on` có thể giúp tìm lỗi

### Archive bị thiếu hoặc sai đường dẫn

Nguyên nhân có thể là pipeline quên đóng gói `.jsa`, đường dẫn tương đối thay đổi theo working directory, container volume khác nhau hoặc tên file sai. `-Xshare:on` sẽ khiến lỗi hiển thị sớm khi JVM không dùng được archive.

### Archive từ JDK build khác

CDS archive gắn với một JDK build nhất định. Thay JDK mà không tạo lại archive có thể khiến archive không tương thích. `-Xshare:on` được thiết kế **báo lỗi và thoát** khi không thể dùng CDS, thay vì yên lặng chuyển đường tải class khác.

### JAR/classpath/module configuration thay đổi

Lệnh training và lệnh chạy có thể khác nhau vì cập nhật JAR, classpath, modular JAR hoặc module option. Một số thay đổi vẫn được JVM hỗ trợ (ví dụ điều kiện prefix classpath trong tài liệu), số khác khiến archive bị từ chối hoặc vô hiệu từng phần. **Không khẳng định mọi thay đổi classpath đều gây lỗi**, cũng không bỏ qua việc kiểm tra tính tương thích.

### Cấu hình JVM làm vô hiệu CDS

Có những VM options hoặc trường hợp runtime khiến CDS không được sử dụng. Ví dụ tài liệu JDK 25 nêu một số tùy chọn module như `--patch-module`, `--upgrade-module-path`, `--limit-modules` có thể làm CDS bị vô hiệu. Với `-Xshare:on`, tình huống không thể dùng CDS có thể **khiến khởi tạo thất bại**. Hãy so sánh cấu hình JVM lúc tạo và lúc chạy archive.

### Class application chưa có trong archive

Đây là trường hợp **khác**: `-Xshare:on` vẫn có thể thành công vì archive hợp lệ và các class nền tảng được dùng. Nếu class ứng dụng quan trọng không được archive, cần **xem log tải class** và điều chỉnh training workload, chứ không dựa vào việc strict mode trả exit 0.

## 11. Vì sao `-Xshare:on` không phù hợp mặc định trong production?

Oracle mô tả `-Xshare:on` là lựa chọn **chỉ phục vụ kiểm thử**. Nếu archive bị thiếu, đổi JDK hoặc gặp VM parameter không tương thích, JVM có thể **thoát bất ngờ trong quá trình startup**. Điều này biến **một tối ưu hiệu năng tùy chọn** thành **điểm lỗi có thể làm dịch vụ ngừng khởi động**.

Trong vận hành thông thường:

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

hoặc cấu hình phù hợp với JDK hiện tại, cho phép **best-effort sharing**. Với nhiều JDK, `-Xshare:auto` vốn là mặc định nên có thể không cần ghi cờ; thêm cờ khi muốn tài liệu triển khai rõ ràng.

**Quy trình đề xuất:**

1. **Tạo archive trong CI/CD** với đúng artifact và JDK mục tiêu.
2. **Kiểm tra trong môi trường kiểm thử** bằng `-Xshare:on` với archive tương thích.
3. **Xác nhận class ứng dụng** dùng archive qua `-Xlog:class+load`.
4. **Chạy functional test** để chắc ngữ nghĩa ứng dụng không đổi.
5. **Đóng gói archive bất biến**, phân phối cùng đúng JAR/JDK build.
6. **Ở production, ưu tiên `auto`/mặc định** nếu yêu cầu hệ thống là tiếp tục chạy khi archive không khả dụng.
7. **Theo dõi startup và log** để biết có mất tối ưu do archive fallback không.
8. **Tạo lại/kiểm tra lại archive** sau khi nâng JDK, đổi dependency JAR hoặc cấu hình module.
9. **Không dùng `-Xshare:on` như một yêu cầu sản phẩm bắt buộc** trừ khi có quyết định vận hành đặc biệt được đánh giá rủi ro và không mâu thuẫn hướng dẫn vendor.

**Điểm cần cân bằng:** `auto` có thể che việc CDS bị vô hiệu nếu không có monitoring. Cách xử lý không phải ép mọi production JVM vào chế độ fail-fast, mà là **kiểm tra nghiêm ngặt trong CI, đo và giám sát trong production**.

## 12. Các lệnh bị nhầm lẫn trong tài liệu cũ

AppCDS xuất hiện từ Java 10; một số tài liệu/đoạn script cũ nhắc đến các cờ mà JDK hiện đại không còn dùng theo cách ban đầu. Với Special Note yêu cầu **chỉ kiến thức hiện còn áp dụng**, thực hành trong bài **không sử dụng** các cờ mở khóa thương mại hoặc cờ AppCDS cũ như `-XX:+UnlockCommercialFeatures` hoặc `-XX:+UseAppCDS`.

Thay vào đó, nhận biết các cờ hiện còn hữu ích:

| Cờ | Công dụng đúng |
| --- | --- |
| **`-Xshare:on`** | **Yêu cầu CDS hoạt động; không hoạt động thì fail-fast** |
| `-Xshare:auto` | Thử dùng CDS, cho phép fallback nếu không dùng được |
| `-Xshare:off` | Tắt CDS để đối chứng/chẩn đoán |
| `-XX:SharedArchiveFile=app.jsa` | Chọn file archive chia sẻ để dùng khi chạy |
| `-XX:ArchiveClassesAtExit=app.jsa` | Tạo dynamic archive khi JVM thoát, từ JDK 13 |
| `-XX:+AutoCreateSharedArchive` | Tự tạo/tái sử dụng archive theo workflow có từ JDK 19 |
| `-Xshare:dump` | Tạo static CDS archive trong workflow thích hợp |
| `-Xlog:class+load=info` | Ghi log nguồn tải class để xác nhận class app được chia sẻ |

**Không suy ra rằng mọi cờ ở bảng có sẵn trong chính runtime Java 10**. `-Xshare:on` và cơ chế AppCDS gốc từ Java 10 vẫn liên quan; dynamic/auto-create là các cải tiến được đưa vào **những JDK sau**.

### AOT cache không đồng nghĩa `-Xshare:on`

Các JDK mới hơn có **AOT cache** với khả năng tối ưu mở rộng so với CDS truyền thống. Chẳng hạn từ JDK 24 có cơ chế AOT cache (JEP 483), JDK 25 bổ sung tiện ích dòng lệnh và tối ưu mới. Đó là **hướng tối ưu bổ sung**; không dùng `-Xshare:on` làm phép thử thay thế cho mọi tùy chọn AOT cache. Nếu ứng dụng chuyển sang workflow AOT mới, hãy đọc tài liệu đúng phiên bản JDK về `-XX:AOTCache`/`-XX:AOTCacheOutput` và phép kiểm tra tương ứng.

Nói cách khác, **đề bài này là kiểm tra nghiêm ngặt sử dụng kho CDS/AppCDS**. Không được hứa rằng chế độ đó sẽ bắt buộc mọi AOT artifact khác cũng xuất hiện và được dùng.

## 13. Khắc phục lỗi thường gặp

| Hiện tượng | Suy luận đúng | Cách xử lý |
| --- | --- | --- |
| `-Xshare:on` với `missing.jsa` thoát mã lỗi | Không sử dụng được archive yêu cầu, **chưa chạy main** | Kiểm tra file/path/quyền/JDK; tạo lại hoặc chọn file đúng |
| `-Xshare:auto` với `missing.jsa` vẫn chạy | Fallback hoạt động, **không chứng minh AppCDS đã dùng** | Xem log CDS/class load và kiểm tra archive |
| `-Xshare:on` không chỉ định `app.jsa` vẫn thành công | Có thể dùng default CDS archive | Muốn kiểm tra AppCDS, chỉ định custom archive và soi class ứng dụng |
| JVM chạy với `app.jsa` nhưng class `ArchiveCheck` từ JAR | Archive không chứa hoặc không dùng được entry class đó | Xem training workload, archive provenance, log và tương thích |
| Có file `app.jsa` nhưng không giảm startup | File tồn tại không bảo đảm lợi ích quan sát được | Đo workload nhiều lần; phân biệt CDS mặc định/AppCDS |
| Training không tạo `app.jsa` | Cờ không hỗ trợ/JVM không thoát phù hợp/đường ghi sai | Kiểm tra JDK version, stderr/exit code, quyền ghi |
| Sau đổi JDK hoặc JAR thì strict mode thất bại | Archive có thể không tương thích | Tạo lại cùng JDK build và artifact mới |
| Mọi test qua nhưng production mất archive | Pipeline/artifact path khác giữa môi trường | Kiểm tra deployment, monitoring, không ép strict production |
| `-Xshare:off` vẫn chạy nhưng bị chậm hơn | Baseline cố tình tắt chia sẻ | Chỉ dùng off cho đối chứng/debug, không suy ra tính năng lỗi |
| Log có quá nhiều dòng `java.*` từ archive | Class nền tảng được share, nhưng chưa chứng minh AppCDS | Lọc class do ứng dụng tạo |
| Log chỉ in source `file:.../app.jar` cho app class | Class đó được đọc từ JAR trong lượt đang đo | Kiểm tra archive generation/loading |
| App bị kill trước khi JVM thoát bình thường | Dynamic archive có thể chưa được ghi | Tạo training run có kết thúc kiểm soát |
| CI assert đúng nguyên văn dòng lỗi JVM | Dễ vỡ khi khác JDK/vendor/platform | Assert exitCode != 0, main không chạy; lưu diagnostics bổ sung |

### Phân loại lỗi thay vì bắt đại mọi trường hợp

Không viết một test đơn giản kiểu “**nếu ứng dụng chạy thì archive tốt**”. Ít nhất cần phân loại:

- **Startup fail-fast:** mã thoát khác 0 khi yêu cầu CDS nghiêm ngặt.
- **Startup thành công nhưng thiếu AppCDS:** mã thoát 0, nhưng class ứng dụng không được load từ archive.
- **Startup thành công và class đã được chia sẻ:** mã thoát 0 và log source tương ứng.
- **Ứng dụng đúng chức năng:** kiểm tra nghiệp vụ không đổi.
- **Có lợi ích đo được:** benchmark startup/footprint có đối chứng.

Các lớp kết quả này nên được báo tách biệt trong QA hoặc deployment dashboard thay vì gộp vào một cột `CDS=true/false` mơ hồ.

## 14. Kiểm tra hiệu năng không dùng strict mode làm phép đo

`-Xshare:on` hữu ích để **bắt cấu hình archive không hợp lệ**, nhưng không cho biết mức tiết kiệm bao nhiêu.

Một benchmark có ý nghĩa nên phân biệt:

~~~bash
# Đối chứng 1: không dùng CDS
java -Xshare:off -cp app.jar ArchiveCheck

# Đối chứng 2: cấu hình mặc định của JDK (có thể dùng default CDS)
java -cp app.jar ArchiveCheck

# AppCDS: chọn archive đã tạo
java -XX:SharedArchiveFile=app.jsa -cp app.jar ArchiveCheck
~~~

**Đây là các lệnh minh họa tình huống so sánh**, không phải script đo latency tự động. Để đo:

1. Dùng cùng JDK, CPU, memory, filesystem, JAR và workload.
2. Khởi chạy đủ số lần, ghi thời gian đến mốc ứng dụng sẵn sàng, phân biệt cold/warm OS page cache khi có ý nghĩa.
3. Đo memory phù hợp nếu mục tiêu là chia sẻ metadata giữa nhiều JVM, không cộng RSS một cách máy móc.
4. Không bật unified logging chi tiết trong các lượt benchmark cuối vì log tạo overhead.
5. Đánh giá biến động thống kê, không dựa vào một lần khởi động nhanh hơn để tuyên bố lợi ích.
6. Giữ test `-Xshare:on` **trong bước xác minh tính hợp lệ archive**, không nhầm với điều kiện tối ưu hiệu năng.

AppCDS **không thay thế cache dữ liệu nghiệp vụ** và không làm tất cả Java heap objects của các tiến trình dùng chung một vùng nhớ. Bản chất là tối ưu cách JVM chuẩn bị và truy cập **dữ liệu lớp**.

## 15. Câu hỏi tự kiểm tra

1. `-Xshare:on` có ý nghĩa gì khác `-Xshare:auto`?
2. Nếu archive cần dùng không tồn tại, trong chế độ `-Xshare:on` JVM sẽ chạy `main()` rồi cảnh báo hay thất bại trước đó?
3. Vì sao `-Xshare:on` chạy thành công **không đủ** chứng minh các class ứng dụng đã nằm trong AppCDS archive?
4. `-XX:SharedArchiveFile=app.jsa` làm gì? Nó có tự tạo `app.jsa` không?
5. `-XX:ArchiveClassesAtExit=app.jsa` có từ JDK nào? Có thể dùng y nguyên trên Java 10 không?
6. Lệnh nào cho phép quan sát class `ArchiveCheck` có nguồn `shared objects file`?
7. `-Xshare:off` có còn nạp lớp ứng dụng bình thường khi tệp `app.jsa` tồn tại không?
8. Vì sao không nên hard-code mọi từ trong thông báo lỗi `-Xshare:on` với archive thiếu?
9. `-Xshare:auto` có đồng nghĩa với `-XX:+AutoCreateSharedArchive` không?
10. Tại sao archive tạo bằng JDK/JAR cũ có thể cần tạo lại?
11. Khi một JVM có default CDS archive, dùng `-Xshare:on` mà không chỉ định custom archive có thể thành công không?
12. Bên cạnh exit code, cần kiểm tra thêm gì để chứng minh **AppCDS** của lớp ứng dụng?
13. AppCDS có chia sẻ mutable static field giữa hai JVM không?
14. Có nên bật `-Xshare:on` mặc định trên mọi production pod không?
15. Một archive tương thích nhưng không làm startup nhanh hơn có nghĩa `-Xshare:on` sai hợp đồng không?
16. Đâu là khác biệt giữa chức năng kiểm thử CDS strict mode và AOT cache trên JDK mới?

**Đáp án:**

1. `on` **yêu cầu CDS phải dùng được**, lỗi thì fail-fast; `auto` **thử dùng nếu có thể**, có fallback.
2. JVM thất bại trong startup khi không thể dùng archive, không chạy `main()` trong ca lỗi được kiểm tra.
3. Vì archive hợp lệ có thể chứa class nền tảng nhưng không chứa class ứng dụng mong muốn.
4. Chỉ định archive để JVM dùng; **không tự tạo archive**. Tạo archive dùng workflow/cờ riêng.
5. JDK 13; **không có trên Java 10**.
6. `-Xlog:class+load=info` và lọc đúng class ứng dụng.
7. Có; tải class theo đường thông thường từ JAR, không dùng CDS.
8. Thông điệp khác nhau theo version/vendor/OS; dùng exit code và sentinel main làm assertion ổn định hơn.
9. Không; một bên là chế độ thử dùng CDS, bên kia là chức năng tạo archive tự động có từ JDK 19.
10. Vì archive gắn với build JVM, JAR/classpath và cấu hình phù hợp.
11. Có, và trường hợp đó **không chứng minh** AppCDS class coverage.
12. Log nguồn class là `shared objects file` cho class ứng dụng cụ thể, cộng test chức năng.
13. Không; trạng thái runtime/heap riêng cho từng JVM.
14. Không; Oracle mô tả strict mode chỉ dành cho kiểm thử và có thể làm service không khởi động khi cache có vấn đề.
15. Không; strict mode xác minh yêu cầu sử dụng CDS, còn hiệu năng phải được đo riêng.
16. Strict mode kiểm tra khả năng dùng shared class data; AOT cache mới có phạm vi và điều khiển riêng theo JDK.

## 16. Checklist QA trước khi hoàn tất bài thực hành

- [ ] Đã dùng **JDK runtime hỗ trợ dynamic AppCDS (JDK 13+)** cho `ArchiveClassesAtExit`; source có thể biên dịch bằng `--release 10`.
- [ ] Class ứng dụng được đóng vào JAR; các lệnh dùng nhất quán `-cp app.jar ArchiveCheck`.
- [ ] Lệnh training chạy với exit code 0 và tạo tệp `app.jsa`.
- [ ] Lần dùng archive có `-XX:SharedArchiveFile=app.jsa` và `-Xshare:on`, startup thành công.
- [ ] Unified log cho thấy `ArchiveCheck` thực sự có `source: shared objects file`.
- [ ] Ca negative dùng một file archive **chắc chắn không tồn tại**.
- [ ] Ca negative với `-Xshare:on` cho **exit code khác 0** và **không có `app-started=true`**.
- [ ] Cùng file thiếu với `-Xshare:auto` cho phép ứng dụng chạy trong môi trường được hỗ trợ.
- [ ] `-Xshare:off` với archive hợp lệ vẫn chạy app nhưng không load lớp từ shared archive.
- [ ] Đã phân biệt **default CDS dùng được** với **AppCDS class coverage**.
- [ ] Không dùng `-Xshare:on` như lựa chọn mặc định production.
- [ ] Không dùng cờ thương mại/AppCDS cũ đã obsolete.
- [ ] Không đo hiệu năng bằng đúng một lần chạy có logging nặng.
- [ ] Có quy trình kiểm tra/tạo lại archive sau đổi JDK, JAR hoặc điều kiện classpath/module.
- [ ] Có giới hạn quyền ghi vào archive, tránh để artifact bị sửa ngoài pipeline kiểm soát.
- [ ] Nếu dùng AOT cache mới, có bài kiểm thử và tài liệu riêng theo đúng phiên bản JDK.

## 17. Tham khảo tài liệu chính thức, còn áp dụng

- **Oracle JDK 25 — Class Data Sharing, các chế độ `-Xshare:off`, `on`, `auto` và cảnh báo chỉ dùng `on` để test:** https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html
- **Oracle JDK 25 — `java` launcher, CDS/AppCDS, `-XX:SharedArchiveFile`, static/dynamic/auto archives, classpath/module restrictions:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **OpenJDK JDK `java` command source — `-Xshare:on` và các phiên bản chế độ CDS hiện hành:** https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md
- **OpenJDK — JEP 310, Application Class-Data Sharing (Java 10):** https://openjdk.org/jeps/310
- **OpenJDK — JEP 350, Dynamic CDS Archives (JDK 13):** https://openjdk.org/jeps/350
- **Dev.java — CDS and AppCDS in HotSpot, ví dụ vận hành và source logs:** https://dev.java/learn/jvm/cps-appcds/
- **OpenJDK — JEP 483, Ahead-of-Time Class Loading & Linking (JDK 24), để phân biệt AOT cache với AppCDS:** https://openjdk.org/jeps/483

**Kết luận:** `-Xshare:on` là chế độ **bắt buộc CDS hoạt động trong một lượt kiểm thử**: archive không dùng được thì JVM báo lỗi và thoát, **không tự fallback**. Nhưng `on` **không tự tạo archive** và **không bắt buộc mọi class ứng dụng nằm trong archive**; để chứng minh AppCDS, phải chỉ định kho ứng dụng và kiểm tra log của class ứng dụng. Dùng chế độ này trong **CI/QA**, còn production thường dùng `auto`/mặc định và giám sát fallback để tránh biến một tối ưu tùy chọn thành nguyên nhân làm ứng dụng không thể khởi động.