# Chế độ `-Xshare:auto` và khả năng tiếp tục khi không dùng được kho CDS/AppCDS (Java 10+)

## 1. Bài toán vận hành: kho chia sẻ lớp không dùng được thì JVM có phải dừng?

Trong các ứng dụng Java triển khai lên container, VM hoặc máy chủ, chúng ta thường muốn JVM **khởi động nhanh** nhờ Class Data Sharing (CDS) và Application Class-Data Sharing (AppCDS). Nhưng kho dữ liệu lớp (*shared archive*, thường là tệp `.jsa`) có thể bị thiếu, không đọc được, không hợp lệ hoặc không tương thích với bản JDK đang chạy.

Câu hỏi trực tiếp của bài này là:

> Nếu JVM **không thể dùng kho CDS/AppCDS**, cấu hình `-Xshare:auto` có cho ứng dụng **tiếp tục khởi động theo cơ chế tải lớp bình thường** hay không?

**Trả lời:** Với HotSpot/OpenJDK hiện hành, **có** trong trường hợp kho CDS không sử dụng được: `-Xshare:auto` ưu tiên nạp dữ liệu lớp đã lưu nếu có thể; nếu kho bị thiếu hoặc bị từ chối, JVM **bỏ qua lợi ích CDS và tiếp tục tải lớp thông thường**. CDS là cơ chế tối ưu khởi động/bộ nhớ, không phải điều kiện bắt buộc để chương trình hoạt động.

Điều này khác hẳn `-Xshare:on`, chế độ **bắt buộc dùng dữ liệu chia sẻ** và có thể **dừng khởi tạo JVM** nếu không dùng được kho, cùng `-Xshare:off`, chế độ **không thử dùng dữ liệu chia sẻ**.

Ví dụ kiểm tra nhanh với một đường dẫn archive chắc chắn không tồn tại:

```bash
java -Xshare:auto -XX:SharedArchiveFile=missing-cds-test.jsa -version
```

Trên HotSpot tương thích, JVM vẫn in thông tin phiên bản rồi thoát thành công. Tệp `missing-cds-test.jsa` **không được tự tạo chỉ vì bạn dùng `-Xshare:auto`**.

Đối chứng:

```bash
java -Xshare:on -XX:SharedArchiveFile=missing-cds-test.jsa -version
```

Với cùng kho bị thiếu, HotSpot **không thể đáp ứng yêu cầu bắt buộc dùng CDS**, nên khởi tạo JVM thất bại; exit code khác `0`. Nội dung stderr cụ thể phụ thuộc bản JDK.

**Không suy luận quá mức:** `-Xshare:auto` chỉ xử lý việc **CDS không khả dụng** theo cơ chế fallback; nó **không** bảo đảm chương trình chạy tiếp nếu classpath thiếu JAR, ứng dụng có lỗi trong `main`, JVM thiếu bộ nhớ hoặc lỗi triển khai độc lập với CDS.

## 2. CDS và AppCDS là gì?

**CDS (Class Data Sharing)** lưu dữ liệu lớp đã được xử lý trước vào một archive để JVM có thể ánh xạ (*map*) và dùng lại trong các lần khởi động sau. Thay vì luôn phải xử lý dữ liệu lớp từ đầu, JVM có thể đọc một dạng đã tối ưu cho HotSpot.

**AppCDS** mở rộng cơ chế đó để có thể lưu **các lớp ứng dụng và thư viện ứng dụng phù hợp**, không chỉ những lớp nền tảng JDK. AppCDS được giới thiệu ở **Java 10** (OpenJDK JEP 310) và vẫn là một khả năng hữu ích trong các bản JDK hiện hành.

Sơ đồ:

```text
                       JVM khởi động
                            |
                            v
             Có yêu cầu dùng CDS/AppCDS?
                    /              \
               -Xshare:off       auto / on
                   |                 |
                   v                 v
            Không thử CDS      Kiểm tra archive
                   |                 |
                   |           +-----+------+
                   |           |            |
                   |       Dùng được    Không dùng được
                   |           |            |
                   |           v            v
                   |       Nạp lớp từ   auto: fallback
                   |       shared data      |
                   |                        +--> nạp lớp thông thường
                   |                     on: khởi tạo thất bại
                   v
            Nạp lớp thông thường
                   |
                   v
             Chạy ứng dụng
```

Đây là sơ đồ **khái niệm**: JVM còn có thể dùng kết hợp các lớp từ archive và các lớp tải bình thường; không phải mọi lớp ứng dụng luôn được lưu hoặc luôn đủ điều kiện dùng từ archive.

Các lợi ích có thể có:

- Giảm thời gian khởi động do tái sử dụng dữ liệu lớp đã chuẩn bị.
- Giảm một phần chi phí bộ nhớ liên quan metadata và có thể dùng chung trang ánh xạ giữa nhiều JVM.
- Tối ưu các ứng dụng có startup nhạy cảm, nhất là khi có nhiều lớp được tải sớm.

**Không phải:** lưu dữ liệu nghiệp vụ, cache object trong Java heap, thay thế database, bảo đảm class loading không bao giờ xảy ra, hay tự động tối ưu mọi ứng dụng với mức tăng tốc cố định. Độ lợi phụ thuộc workload, archive, bản JDK, container và cấu hình chạy.

## 3. Ba chế độ `-Xshare` cần phân biệt

| Chế độ | JVM làm gì? | Nếu kho không sử dụng được | Mục đích phổ biến |
| --- | --- | --- | --- |
| **`-Xshare:auto`** | Thử dùng CDS khi có thể | **Fallback**, tải lớp theo cách bình thường | Mặc định/thường phù hợp production |
| **`-Xshare:on`** | **Yêu cầu** dùng dữ liệu chia sẻ | **Báo lỗi và không khởi động** khi không thể đáp ứng | Chẩn đoán, kiểm thử archive |
| **`-Xshare:off`** | Không thử dùng CDS | Vẫn nạp lớp bình thường, bất kể có kho hay không | Đối chứng hiệu năng, cô lập lỗi CDS |

Lệnh tương ứng:

```bash
java -Xshare:auto -jar app.jar
java -Xshare:on   -jar app.jar
java -Xshare:off  -jar app.jar
```

Các ví dụ giả sử có một `app.jar` hợp lệ, executable và có Java runtime hỗ trợ CDS.

### Vì sao `auto` hợp lý trong production?

Vì **lợi ích hiệu năng không nên trở thành điểm hỏng chức năng bắt buộc**. Nếu image/volume thiếu archive hoặc sau đợt nâng JDK archive cũ không còn tương thích, JVM có thể bỏ qua tối ưu đó và ứng dụng tiếp tục tải lớp.

### Vì sao `on` không nên dùng production?

Tài liệu launcher `java` hiện hành của Oracle nói `-Xshare:on` là **chế độ dùng cho kiểm thử** và **không nên sử dụng trong production**. Khi cấu hình, archive hoặc JDK thay đổi, chế độ yêu cầu CDS có thể làm JVM **dừng lúc startup**, biến một tính năng tối ưu tùy chọn thành nguyên nhân gây gián đoạn dịch vụ.

### `off` có nghĩa gì?

`-Xshare:off` tắt việc thử dùng dữ liệu lớp chia sẻ. Nó phù hợp làm baseline để đo thời gian khởi động hoặc để tách riêng hiện tượng do CDS gây ra. Nó **không** “xóa archive” và **không** phải giải pháp tăng tốc.

## 4. `auto` là cơ chế dùng được thì dùng, không phải tự tạo archive

Hai từ **auto** rất dễ bị hiểu sai:

1. **`-Xshare:auto`**: *tự động sử dụng kho CDS nếu có thể*, nếu không thì chạy cơ chế bình thường.
2. **`-XX:+AutoCreateSharedArchive`**: một **tùy chọn khác** của HotSpot giúp tạo/tái tạo dynamic CDS archive theo điều kiện nhất định.

**`-Xshare:auto` không đồng nghĩa “archive bị thiếu thì JVM tự sinh file mới”**.

Ví dụ:

```bash
java -Xshare:auto -XX:SharedArchiveFile=missing.jsa -version
```

Nói chung lệnh trên không tạo `missing.jsa`; JVM kiểm tra và fallback khi archive không tồn tại.

Ngược lại, một cách dùng tùy chọn **tạo archive** trên những JDK hiện hành có hỗ trợ `-XX:+AutoCreateSharedArchive` là:

```bash
java -XX:+AutoCreateSharedArchive \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar com.example.Main
```

Lệnh giả định JAR và lớp chính phù hợp, chạy trên shell có hỗ trợ dấu `\` để nối dòng. Khi archive không có, JVM có thể tạo **dynamic archive ở lúc thoát** để lần sau dùng; khi archive do JDK khác tạo, khả năng làm mới còn phụ thuộc quy tắc phiên bản cụ thể. **Chỉ dùng sau khi xác nhận chính bản JDK và kiểu đóng gói của ứng dụng hỗ trợ.**

Tài liệu Java SE 25/27 cũng nêu những tối ưu AOT cache hiện đại. Đây là các cơ chế khác hoặc mở rộng so với CDS truyền thống; **đừng đánh đồng mọi AOT cache với `-Xshare:auto` hay giả định mọi archive đều được quản lý như nhau**.

## 5. Kho mặc định và archive AppCDS tùy chỉnh là hai khái niệm

Trên nhiều bản phân phối HotSpot/JDK mới, JVM đã có sẵn một **CDS archive mặc định** chứa dữ liệu một số lớp JDK thường dùng. Theo tài liệu Oracle, từ **JDK 12** Oracle JDK cung cấp archive mặc định được đóng gói sẵn.

Thường gặp đường dẫn như:

```text
Linux/macOS:  $JAVA_HOME/lib/server/classes.jsa
Windows:      %JAVA_HOME%\bin\server\classes.jsa
```

Đây là **vị trí thông thường**, không phải cam kết mọi bản phân phối, kiến trúc hay image container đều có đúng đường dẫn đó.

Nếu không chỉ định archive tùy chỉnh, HotSpot có thể tự dùng archive mặc định khi được phép:

```bash
java -Xshare:auto -version
```

Muốn yêu cầu dùng một archive được tạo cho ứng dụng:

```bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar com.example.Main
```

**Điểm khác nhau:** default CDS archive chủ yếu gắn với JDK và các lớp nền tảng; một archive AppCDS chứa thêm những lớp ứng dụng/thư viện đã được ghi nhận. Trong một số cấu hình có **base static archive** và **dynamic archive** xếp lớp phía trên.

Định dạng `-XX:SharedArchiveFile` có thể nhận một hoặc hai archive theo hợp đồng của JDK:

```text
-XX:SharedArchiveFile=static_archive:dynamic_archive
```

Trên **Windows**, khi liệt kê hai file trong cú pháp đó, dấu phân cách là dấu chấm phẩy `;` thay cho dấu hai chấm `:`. Tài liệu mới còn cho phép bỏ phần base trong nhiều trường hợp vì dynamic archive lưu thông tin base của nó.

**Không tự suy luận rằng chỉ cần đặt `-XX:SharedArchiveFile` là ứng dụng đã dùng AppCDS.** Cần xác nhận archive tồn tại, tương thích, đã được nạp và thực sự có lớp ứng dụng được load từ đó.

## 6. Những lý do thực tế khiến archive không dùng được

| Nguyên nhân | Biểu hiện vận hành | Hành vi mong đợi với `-Xshare:auto` |
| --- | --- | --- |
| Tệp `.jsa` không tồn tại | Path sai, chưa generate, không mount volume | JVM bỏ qua CDS archive và có thể tiếp tục |
| Archive hỏng/không hợp lệ | File bị cắt, sai định dạng, không thể map | Bỏ qua cơ chế chia sẻ nếu lỗi thuộc phạm vi CDS |
| Archive từ JDK/build khác | JVM báo metadata/đặc điểm archive không tương thích | Fallback thay vì bắt buộc dùng archive |
| Thay đổi cấu hình JVM quan trọng | Tham số VM tạo và dùng archive không tương thích | Có thể vô hiệu hóa toàn bộ hoặc một phần tối ưu CDS |
| JAR/classpath/module path thay đổi | Archive không còn tương ứng class source | Một số hoặc toàn bộ archived classes không dùng được |
| Môi trường container khác | Image có runtime mới nhưng archive từ image cũ | Không nên dựa trên archive cũ |
| Quyền truy cập/ánh xạ file | OS không cho đọc/map archive | Cần log chẩn đoán; CDS có thể bị bỏ qua |
| Một số tùy chọn module đặc biệt | CDS có thể bị tắt bởi chính lựa chọn VM | Ứng dụng vẫn nạp lớp bình thường nếu không có lỗi khác |

**Cần nói chính xác:** không phải mọi khác biệt classpath/JAR khiến **JVM dừng hoặc toàn bộ archive bị từ chối**. Một số tình huống JVM vẫn dùng archive nền tảng nhưng không dùng những lớp ứng dụng không khớp. Kết quả phụ thuộc loại archive, JDK, module options và mức độ sai khác.

**Thay đổi JDK build:** archive CDS chứa dữ liệu nội bộ phụ thuộc **bản build JDK**, không phải dữ liệu trao đổi di động tùy ý giữa mọi JVM. Tạo archive theo đúng runtime image/container được triển khai, hoặc dùng cơ chế làm mới được nhà cung cấp hỗ trợ.

**Thay đổi JAR:** archive có thể dựa vào thông tin về những JAR ở lúc tạo. Khi bạn build lại JAR hoặc đổi nguồn class, archive cũ có thể không còn dùng được; hãy tái tạo archive trong quy trình release hoặc chọn cơ chế tự quản lý có kiểm soát.

## 7. Luồng fallback thực sự

Khi khởi động với `-Xshare:auto`, có thể hình dung:

```text
1. Đọc cấu hình JVM và đường dẫn archive (mặc định hoặc chỉ định).
2. Thử mở, kiểm tra header/metadata và map archive hợp lệ.
3a. Nếu phù hợp: dùng dữ liệu chia sẻ cho các lớp đủ điều kiện.
3b. Nếu không phù hợp: bỏ lợi ích CDS liên quan, nạp lớp bình thường.
4. Tiếp tục khởi tạo JVM, tải lớp chính và gọi main nếu không có lỗi khác.
```

Trên JDK 21 đã được kiểm chứng trong trường hợp **archive cố ý không tồn tại**, với:

```bash
java -Xshare:auto \
     -XX:SharedArchiveFile=/tmp/does-not-exist.jsa \
     -version
```

Kết quả lệnh thành công và thông tin `java -version` vẫn được in. Khi thêm logging:

```bash
java -Xshare:auto \
     -XX:SharedArchiveFile=/tmp/does-not-exist.jsa \
     -Xlog:cds=info -version
```

Log HotSpot cho biết archive chỉ định không tìm thấy, nhưng JVM **không coi đây là lỗi fatal khi ở chế độ auto**.

**Không hardcode nguyên dòng log cho mọi JDK:** đường dẫn, timestamp, mức log, tiếng Anh và nội dung diagnostic có thể khác giữa phiên bản/vendor. Kiểm tra **exit code**, chương trình có vào `main` không và các thông tin log quan trọng, thay vì chỉ ghép một chuỗi error message cố định.

## 8. Phân biệt hai loại “tiếp tục chạy”

Có ít nhất hai tình huống:

### 8.1. Không dùng được toàn bộ archive chỉ định

Ví dụ file `missing.jsa` không có hoặc hỏng. Với `auto`, VM có thể từ chối nó và dùng class loading bình thường. Trường hợp này là **fallback toàn bộ cho archive đó**.

### 8.2. Archive còn dùng được một phần

Ví dụ base JDK CDS hợp lệ nhưng một số lớp ứng dụng không thể dùng do JAR thay đổi, classpath không còn khớp hoặc option module khác. JVM có thể vẫn dùng một số dữ liệu chia sẻ, còn các lớp khác nạp bình thường.

Vì vậy, “process chạy thành công” **không chứng minh AppCDS đã áp dụng cho mọi lớp**, và “không thấy class ứng dụng lấy từ archive” **không đồng nghĩa JVM không dùng default CDS cho lớp JDK**.

Nếu mục tiêu là **kiểm thử hiệu quả AppCDS**, hãy đo thực sự có lớp nào được nạp từ `shared objects file` và có tác động đến startup hay không. Nếu mục tiêu là **không ngắt dịch vụ khi archive bị lỗi**, hãy kiểm tra khả năng chạy tiếp dưới `-Xshare:auto`.

## 9. Hướng dẫn kiểm tra nhanh trên dòng lệnh

Trước tiên xác nhận JDK/VM:

```bash
java -version
```

Lệnh `java -version` không cần ứng dụng, phù hợp kiểm tra riêng giai đoạn JVM startup.

### Trường hợp 1: cho phép fallback

```bash
java -Xshare:auto -XX:SharedArchiveFile=missing-cds-test.jsa -version
```

**Dự kiến trên HotSpot:** exit code `0`, thông tin phiên bản vẫn được in; điều kiện là đường dẫn thực sự không có archive.

### Trường hợp 2: yêu cầu bắt buộc CDS

```bash
java -Xshare:on -XX:SharedArchiveFile=missing-cds-test.jsa -version
```

**Dự kiến:** exit code **khác 0**, báo lỗi liên quan việc không thể dùng shared archive; chương trình Java sẽ không bắt đầu nếu dùng thay `-version` bằng một main class.

### Trường hợp 3: tắt CDS chủ động

```bash
java -Xshare:off -XX:SharedArchiveFile=missing-cds-test.jsa -version
```

**Dự kiến:** exit code `0`, không thử dùng CDS, không cần file archive. Đây là baseline hữu ích để loại trừ ảnh hưởng CDS.

### Kiểm tra exit code

Trong **Bash/sh**, ngay sau lệnh cần kiểm tra:

```bash
echo $?
```

Trong **PowerShell**, sau khi gọi Java:

```powershell
$LASTEXITCODE
```

**Cảnh báo:** đừng chạy một lệnh khác trước khi lấy exit code, vì kết quả trạng thái có thể bị thay thế. Và đừng chạy `-Xshare:on` trong production chỉ để “bảo đảm hiệu năng”: đó là một chế độ **cố tình fail fast cho mục đích test**.

## 10. Chương trình Java 17+ tự kiểm thử cả ba chế độ

Để không phụ thuộc tên file archive có vô tình tồn tại ở thư mục làm việc hay không, ví dụ sau **tạo một thư mục tạm riêng**, chọn đường dẫn `missing.jsa` chưa có, rồi khởi động ba tiến trình JVM con.

Mỗi JVM con chạy **chính class test này** với đối số `--child` và chỉ in `APP_OK` nếu VM đã khởi động đến `main`. Chương trình không phụ thuộc thông điệp lỗi cụ thể của HotSpot; nó kiểm tra exit code và việc ứng dụng đã vào `main` hay chưa.

Tạo tệp `AppCdsFallbackProbe.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public final class AppCdsFallbackProbe {

    record Outcome(int exitCode, boolean reachedMain) { }

    static Outcome launch(String mode, Path missingArchive)
            throws Exception {

        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win") ? "java.exe" : "java";

        String javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin", executable).toString();

        List<String> command = List.of(
                javaExecutable,
                "-Xshare:" + mode,
                "-XX:SharedArchiveFile=" + missingArchive,
                "-cp", System.getProperty("java.class.path"),
                AppCdsFallbackProbe.class.getName(),
                "--child");

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        String result = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8);

        int exit = process.waitFor();

        return new Outcome(
                exit,
                result.contains("APP_OK"));
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--child")) {
            System.out.println("APP_OK");
            return;
        }

        Path directory =
                Files.createTempDirectory("cds-fallback-");
        Path missing = directory.resolve("missing.jsa");

        try {
            Outcome auto = launch("auto", missing);
            Outcome on = launch("on", missing);
            Outcome off = launch("off", missing);

            System.out.println("archive.exists="
                    + Files.exists(missing));
            System.out.println("auto.exitZero="
                    + (auto.exitCode() == 0));
            System.out.println("auto.reachedMain="
                    + auto.reachedMain());
            System.out.println("on.exitNonzero="
                    + (on.exitCode() != 0));
            System.out.println("on.reachedMain="
                    + on.reachedMain());
            System.out.println("off.exitZero="
                    + (off.exitCode() == 0));
            System.out.println("off.reachedMain="
                    + off.reachedMain());

            boolean passed =
                    !Files.exists(missing)
                    && auto.exitCode() == 0
                    && auto.reachedMain()
                    && on.exitCode() != 0
                    && !on.reachedMain()
                    && off.exitCode() == 0
                    && off.reachedMain();

            if (!passed) {
                throw new AssertionError(
                        "CDS launch check failed");
            }

            System.out.println("tests=PASS");
        } finally {
            Files.deleteIfExists(missing);
            Files.delete(directory);
        }
    }
}
```

Biên dịch/chạy với **JDK 17+ có HotSpot/OpenJDK**:

```bash
javac --release 17 AppCdsFallbackProbe.java
java AppCdsFallbackProbe
```

Kết quả **đã chạy và kiểm chứng trên OpenJDK 21**:

```text
archive.exists=false
auto.exitZero=true
auto.reachedMain=true
on.exitNonzero=true
on.reachedMain=false
off.exitZero=true
off.reachedMain=true
tests=PASS
```

**Đọc kết quả:**

1. `archive.exists=false` xác nhận archive cố ý không có trước và sau ba lần chạy; `-Xshare:auto` đơn lẻ không tự tạo file.
2. `auto.exitZero=true`, `auto.reachedMain=true`: JVM bỏ qua vấn đề archive và ứng dụng vẫn vào được `main`.
3. `on.exitNonzero=true`, `on.reachedMain=false`: VM không thể đáp ứng yêu cầu bắt buộc dùng CDS và **dừng trước khi vào code ứng dụng**.
4. `off.exitZero=true`, `off.reachedMain=true`: tắt CDS vẫn chạy bình thường, không cần archive.
5. `tests=PASS` chỉ in khi tất cả điều kiện kiểm thử trên thỏa.

Ví dụ không tạo/archive một JAR ứng dụng vì mục tiêu của nó chỉ là **so sánh chính sách khởi động khi một archive được chỉ định bị thiếu**; đây **không phải** một benchmark chứng minh AppCDS lưu được class của ứng dụng. Để kiểm tra điều đó cần tạo kho ứng dụng hợp lệ và dùng class-loading log theo phần sau.

Chương trình dùng `ProcessBuilder` để chọn chính Java executable thuộc `java.home` của tiến trình cha, tránh tình trạng shell lấy một bản Java khác trên `PATH`. Khi sử dụng JVM/vendor khác HotSpot, một số flag hoặc hành vi có thể khác; hãy chạy lại test trên **runtime image của sản phẩm**, không xem ví dụ là hợp đồng của mọi JVM trên thế giới.

Thư mục tạm dùng cho phép thử được xóa trong `finally`. Không chạy test này trong một môi trường cấm tạo thư mục tạm hoặc cấm process con trừ khi đã chuẩn bị quyền phù hợp.

## 11. Cách xác nhận JVM có thật sự dùng archive hay không

Ứng dụng khởi động thành công không đủ để chứng minh CDS đã được bật và đã **nạp class từ archive**. Dùng **JVM Unified Logging** của HotSpot:

### Xem việc mở/map CDS archive

```bash
java -Xshare:auto -Xlog:cds=info -version
```

Khi archive mặc định dùng được, log có thể chứa các dòng báo **trying to map**, **Opened archive** hoặc **Mapped ... region** và đường dẫn tệp thực tế. Cấu trúc log không cố định giữa các JDK.

Nếu cố tình dùng archive thiếu:

```bash
java -Xshare:auto \
     -XX:SharedArchiveFile=missing-cds-test.jsa \
     -Xlog:cds=info -version
```

Trên OpenJDK 21 đã kiểm chứng, log nêu rằng archive chỉ định không tìm thấy và không thể dùng shared archive, **nhưng JVM vẫn in thông tin phiên bản**.

### Xem lớp được tải từ nguồn nào

```bash
java -Xshare:auto -Xlog:class+load=info -jar app.jar
```

Khi một lớp được nạp từ shared archive trên HotSpot, log có thể ghi `source: shared objects file`. Khi nạp bình thường, log có thể ghi nguồn module image hoặc JAR tương ứng.

**Phải phân biệt lớp JDK và lớp ứng dụng:** tìm thấy `java.lang.Object source: shared objects file` chứng minh có sử dụng **CDS cho lớp JDK** nhưng **chưa** chứng minh lớp của ứng dụng đã được lưu trong AppCDS. Nếu mục tiêu là kiểm chứng AppCDS, hãy tìm tên những class riêng của ứng dụng trong log.

**Không nên bật verbose class-load log liên tục ở production** nếu không có mục đích, vì số dòng rất lớn và có chi phí I/O. Dùng ở staging hoặc một khoảng chẩn đoán có kiểm soát.

## 12. Archive AppCDS cần phù hợp bản JDK và classpath

Tài liệu launcher `java` hiện hành nêu một số ràng buộc quan trọng với CDS archives:

- **Archive phụ thuộc vào JDK build**; đừng sao chép archive từ một bản JDK khác rồi mong nó luôn dùng được.
- **JAR cần khớp với lúc tạo archive**; thay JAR có thể làm archive không dùng được.
- **Classpath khi tạo archive và khi chạy** phải đáp ứng các điều kiện tương thích được quy định; với các mode AppCDS phổ biến, tạo archive từ JAR đóng gói sẽ thuận lợi hơn việc dựa vào những thư mục lớp triển khai dạng exploded.
- Những tùy chọn module/path đặc biệt có thể làm CDS **bị vô hiệu hóa** hoặc chỉ dùng một phần.
- Một archive AppCDS có thể chứa thông tin liên quan base archive; cần giữ đúng sự kết hợp khi triển khai.

Đừng chỉ kiểm tra một file `.jsa` tồn tại; **tồn tại khác với dùng được**.

Ví dụ môi trường container:

```text
Build image:
  JDK build A
  app.jar version 1
  app.jsa sinh theo A + app.jar version 1

Deploy image khác:
  JDK build B
  app.jar version 2
  app.jsa vẫn từ image trước
```

Trong tình huống này, kho không còn đảm bảo tương thích. Với `-Xshare:auto`, ứng dụng có thể vẫn startup bình thường, **nhưng mất lợi ích CDS**, nên startup time hoặc footprint có thể thay đổi.

**Biện pháp đúng:** tạo/tái tạo archive như một phần của artifact/image tương ứng runtime mới, hoặc áp dụng cơ chế tạo archive tự động được chính bản JDK hỗ trợ. Không đổi sang `-Xshare:on` trong production để “ép” JVM dùng một archive không hợp lệ.

## 13. Kiểm tra AppCDS theo đường chạy đóng gói thực tế

Trong môi trường đã đóng gói ứng dụng thành JAR, một workflow hiện hành của HotSpot có thể sử dụng **dynamic CDS archive**:

```bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar com.example.Main
```

Lệnh này chạy ứng dụng và tạo dynamic archive khi JVM kết thúc theo điều kiện hỗ trợ. Trong lần chạy tiếp theo:

```bash
java -Xshare:auto \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar com.example.Main
```

Đây là **workflow minh họa**: `app.jar`, `com.example.Main` và việc ứng dụng kết thúc bình thường là các điều kiện giả định. Bạn phải xem tài liệu của **bản JDK thực tế** vì các tùy chọn archive và AOT đã tiếp tục phát triển.

Đối với nhiều JDK mới, có thể cân nhắc `-XX:+AutoCreateSharedArchive` để giảm công đoạn tạo/sử dụng archive. Tài liệu Java SE 25 nêu rằng nó có thể tạo archive khi chưa có, và làm mới một số archive được tạo bởi JDK từ 19 trở lên khi JDK build thay đổi. **Không suy rộng khả năng đó cho mọi archive cũ** hoặc coi `-Xshare:auto` đã làm việc tương tự.

Với một số ứng dụng container hoặc framework, cơ chế AOT cache từ JDK mới cũng có thể phù hợp hơn dynamic CDS truyền thống. Hãy đánh giá **đúng runtime được triển khai**, không làm theo quy trình lịch sử từ Java 10 nếu JDK hiện tại đã cung cấp cách triển khai phù hợp hơn.

## 14. Vì sao không nên viết “nếu auto thì mọi lỗi khởi động đều được bỏ qua”?

`-Xshare:auto` cho phép **bỏ qua cơ chế tối ưu CDS không khả dụng**, không phải cấu hình **bỏ qua các lỗi của JVM hay ứng dụng**.

Những lỗi sau **vẫn có thể làm JVM hoặc chương trình thất bại**, cho dù auto đang bật:

| Lỗi | Ví dụ | Vì sao auto không giải quyết |
| --- | --- | --- |
| Lớp chính không tồn tại | Sai `-cp` hoặc `-jar` | Class loader không tìm được chương trình |
| Dependency thiếu | `NoClassDefFoundError` | Archive không thay thế dependency/runtime classpath |
| Phiên bản bytecode không hợp lệ | `UnsupportedClassVersionError` | JVM đích không hiểu định dạng `.class` |
| API không có lúc chạy | `NoSuchMethodError` | Lệch JDK/dependency |
| Tham số JVM không hợp lệ | Flag không được hỗ trợ | Lỗi parsing option, không phải chỉ lỗi CDS |
| Bộ nhớ/tài nguyên không đủ | Không thể cấp phát heap/metaspace | Không được bảo đảm bởi fallback |
| `main` ném exception | Cấu hình ứng dụng sai, lỗi I/O | CDS không sửa logic ứng dụng |
| Archive độc hại/file không tin cậy | Tệp không được kiểm soát nguồn | Cần giải quyết provenance/security, không chỉ fallback |

**Ví dụ:** khi `-Xshare:auto` chạy nhưng `app.jar` biến mất khỏi container, việc archive bị bỏ qua không thể tự dựng lại lớp chính của ứng dụng. Vì vậy phải tách **sự cố tối ưu startup** khỏi **sự cố chức năng triển khai**.

Không dùng tỷ lệ lỗi CDS thấp như chỉ số chứng minh hệ thống đang an toàn hoặc đầy đủ dependency.

## 15. Cách xử lý sự cố: ba mục tiêu khác nhau

### A. Muốn dịch vụ luôn startup dù archive bị lỗi

Giữ chế độ `-Xshare:auto` (hoặc mặc định tương ứng của HotSpot), xác nhận không còn tùy chọn **bắt buộc** dùng CDS, và theo dõi startup thực tế.

### B. Muốn biết archive có thực sự dùng được hay không

Trên **staging/test**, thêm logging `-Xlog:cds=info` và `-Xlog:class+load=info`, xem những lớp nào nạp từ shared objects. Nếu cần **kiểm tra fail-fast có chủ đích**, có thể dùng `-Xshare:on` trên môi trường kiểm thử có quyền kiểm soát archive.

Không lấy `-Xshare:on` làm policy production chỉ vì nó giúp bắt lỗi archive sớm.

### C. Muốn chứng minh AppCDS đang cải thiện hiệu năng

So sánh các lần khởi động tương đương:

```text
A. -Xshare:off   (không dùng CDS)
B. -Xshare:auto  (có archive tương thích)
C. -Xshare:auto  (archive bị thiếu -> fallback)
```

Giữ cùng JDK/container, classpath, dependency, CPU, memory limit, workload và cơ chế warmup thích hợp; đo nhiều lần. Chỉ dùng `-Xshare:on` như một phép kiểm tra phụ để xác nhận tính khả dụng của archive trong môi trường test, **không** như baseline ứng dụng production.

Điều cần đo có thể gồm thời gian từ khởi động process đến mốc **ready** của ứng dụng, không chỉ thời điểm in dòng đầu của JVM; đồng thời xem memory footprint, số lớp nạp từ archive và tài nguyên container.

## 16. Quan sát fallback trong production mà không gây gián đoạn

`-Xshare:auto` được thiết kế để fail-safe, nhưng vì vậy nó cũng có thể **che một regression hiệu năng**: ứng dụng vẫn chạy nên readiness/health check xanh, nhưng thời gian startup tăng sau đợt nâng JDK hoặc khi volume archive không còn.

Các biện pháp vận hành hữu ích:

1. Trong CI hoặc staging, chạy ít nhất một kiểm tra **archive hợp lệ** và xác nhận lớp quan trọng được load từ shared data nếu đó là mục tiêu của AppCDS.
2. Ghi nhận JDK vendor/build, container image digest, đường dẫn archive và artifact version được dùng để tạo kho.
3. Bật log `cds=info` theo chính sách quan sát phù hợp và lưu lại trong giai đoạn phân tích sự cố.
4. Đặt cảnh báo trên **startup latency** hoặc tiêu chí performance đã chọn, không chỉ kiểm tra process còn sống.
5. Giữ cách triển khai ứng dụng không phụ thuộc việc kho CDS tồn tại.
6. Nếu archive bị thiếu/mismatch, **tái tạo đúng archive** hoặc thay cách phát hành; không ép `on` trong môi trường sản xuất.
7. Dùng `-Xshare:off` làm thí nghiệm đối chứng khi cần xác định sự cố có liên quan CDS hay không.

**Không tự sinh cảnh báo critical chỉ vì một dòng log nói archive không được dùng** nếu hệ thống đã cho phép fallback; mức độ ưu tiên nên phụ thuộc tác động hiệu năng và chính sách sản phẩm. Tuy nhiên, một startup latency tăng rõ rệt có thể là dấu hiệu cần hành động.

## 17. Quyền truy cập, bảo mật và provenance của archive

Vì shared archive là một artifact phụ thuộc runtime và chứa metadata liên quan mã ứng dụng, hãy quản lý nó như một thành phần của **quy trình build/deploy được tin cậy**:

- Tạo trong build/staging được kiểm soát, không nhận file tùy tiện từ nguồn không xác thực.
- Không để một tiến trình không được tin cậy sửa archive trong lúc ứng dụng khác sử dụng.
- Đặt quyền đọc phù hợp cho user chạy JVM và hạn chế quyền ghi trong production.
- Gắn archive với đúng build JDK, image và artifact phiên bản ứng dụng.
- Đo và quản lý dung lượng lưu trữ; shared archive không nhất thiết nhỏ hơn toàn bộ JAR.
- Không xem `-Xshare:auto` như công cụ xác minh chữ ký hoặc nguồn gốc file.

Nếu một kho độc hại hoặc không đáng tin cậy xuất hiện, giải pháp không phải “auto sẽ tự bỏ qua”. Hợp đồng fallback áp dụng khi archive **không dùng được**; nó không thay quy trình xác thực, kiểm soát nguồn và bảo vệ file. Hãy dùng filesystem image/permissions và quy trình phát hành đáng tin cậy.

## 18. Một số tình huống vận hành thường gặp

### Tình huống 1: volume mount chứa `app.jsa` bị mất

Startup command:

```bash
java -Xshare:auto -XX:SharedArchiveFile=/opt/app/app.jsa \
     -cp /opt/app/app.jar com.example.Main
```

Nếu archive không còn, JVM có thể fallback để tiếp tục chạy; **thời gian khởi động có thể tăng**. Kiểm tra log CDS và readiness; sửa đường dẫn/mount hoặc tạo lại archive ở pipeline.

### Tình huống 2: nâng JDK nhưng quên làm mới archive

Vì archive có tính phụ thuộc build JDK, bản cũ có thể bị từ chối. `auto` giúp giảm rủi ro outage do riêng CDS, nhưng không tự bảo đảm **mức hiệu năng cũ**. Tạo lại archive theo runtime image mới và kiểm tra lại.

### Tình huống 3: cùng một JDK nhưng JAR ứng dụng đổi

Archive ứng dụng có thể không khớp với JAR mới. Các lớp có thể phải nạp theo cách bình thường hoặc các phần tối ưu liên quan không được sử dụng. Hãy build archive **theo artifact đã đóng gói chính thức**, không chỉ theo tên file giống nhau.

### Tình huống 4: cần kiểm thử việc archive được sử dụng

Trong một môi trường test cô lập:

```bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa \
     -Xlog:cds=info -cp app.jar com.example.Main
```

Lệnh này có thể **fail khi không dùng được archive**. Nó hữu ích để phát hiện vấn đề sớm; **không đưa nguyên cách gọi này vào production**. Đồng thời xem `class+load` nếu mục tiêu là xác minh **lớp ứng dụng cụ thể** lấy từ archive.

### Tình huống 5: thử tắt CDS để khoanh vùng lỗi

```bash
java -Xshare:off -cp app.jar com.example.Main
```

Nếu lỗi chỉ xảy ra khi dùng một archive cụ thể, đối chứng `off` có thể giúp thu hẹp phạm vi. Nhưng `off` không giải quyết lỗi logic ứng dụng và thường làm mất lợi ích CDS.

## 19. Các lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`-Xshare:auto` bắt buộc phải có `.jsa`.” | **Không**; dùng khi có thể, fallback khi không dùng được |
| “Auto nghĩa là tự động tạo archive.” | **Không**; cần cơ chế tạo archive riêng như `-XX:+AutoCreateSharedArchive` khi hỗ trợ |
| “`-Xshare:on` tốt hơn auto cho production.” | `on` có thể làm JVM không startup nếu kho lỗi; Oracle khuyến cáo **chỉ dùng test** |
| “`-Xshare:off` làm JVM không tải lớp.” | `off` chỉ tắt **CDS**, JVM vẫn tải lớp thông thường |
| “Process startup thành công chứng tỏ AppCDS hoạt động.” | Có thể đã fallback hoặc chỉ dùng base CDS |
| “Thấy `java.lang.Object` từ shared objects chứng minh lớp của app đã archive.” | Điều đó mới chứng minh **lớp JDK** được chia sẻ; phải kiểm tra lớp ứng dụng riêng |
| “Archive copy sang JDK build mới chắc chắn dùng được.” | CDS archive phụ thuộc bản build, có thể mismatch |
| “Jar file đổi mà tên giống nhau thì archive vẫn hợp lệ.” | Metadata/classpath/JAR thay đổi có thể làm kho không dùng được |
| “CDS là cache các Java object trong heap.” | CDS tối ưu **dữ liệu lớp**, không lưu session/business state |
| “Fallback đồng nghĩa mọi loại startup error đều được bỏ qua.” | Chỉ áp dụng vấn đề dùng CDS, không xử lý JAR thiếu hoặc code lỗi |
| “CDS enabled thì mọi lớp đều lấy từ archive.” | Có giới hạn eligibility, classpath, runtime metadata và provider |
| “Mức tăng tốc là cố định ở mọi app.” | Phụ thuộc runtime, cách đo, class count và workload |
| “`-Xshare:on` exit code nonzero nghĩa code `main` lỗi.” | JVM có thể thất bại **trước `main`** vì CDS |
| “Vừa thấy file `.jsa` trên disk là archive đang được dùng.” | Phải quan sát mapping/class-load logs |
| “Auto đảm bảo không thể có crash nào liên quan JVM.” | Không có bảo đảm tuyệt đối trước mọi lỗi native/runtime |
| “Nên dùng tùy chọn AppCDS lịch sử không còn hiện hành.” | Dựa vào tài liệu của JDK hiện dùng, không sao chép flag cũ |

## 20. Bài tập tự kiểm tra

### Bài 1: dự đoán khi kho bị thiếu

```bash
java -Xshare:auto -XX:SharedArchiveFile=absent.jsa -version
java -Xshare:on   -XX:SharedArchiveFile=absent.jsa -version
java -Xshare:off  -XX:SharedArchiveFile=absent.jsa -version
```

**Hỏi:** chế độ nào có thể chạy khi kho CDS chắc chắn không tồn tại?

**Đáp án:** `auto` và `off` trên HotSpot hiện hành. `auto` fallback, `off` không thử CDS. `on` yêu cầu kho dùng được và có thể dừng VM với exit code khác 0.

### Bài 2: “auto” có tự tạo file?

**Hỏi:** sau khi chạy `java -Xshare:auto -XX:SharedArchiveFile=new.jsa -version`, có thể kết luận `new.jsa` được tạo không?

**Đáp án:** **Không.** `-Xshare:auto` chỉ quản lý việc dùng archive khi có thể. Muốn tạo archive cần workflow/tùy chọn khác, ví dụ `-XX:ArchiveClassesAtExit` hoặc `-XX:+AutoCreateSharedArchive` trên JDK hỗ trợ.

### Bài 3: startup xanh nhưng chậm hơn

**Hỏi:** sau nâng JDK, dịch vụ vẫn healthy nhưng thời gian startup tăng mạnh; log nói archive cũ không được dùng. Có phải `-Xshare:auto` bị lỗi không?

**Đáp án:** Không nhất thiết. `auto` đã thực hiện chính sách fail-safe như mong đợi; phần bị mất là **tối ưu hiệu năng**. Cần tạo kho tương thích JDK mới, kiểm tra lớp nạp từ archive và đo lại.

### Bài 4: test thành công có chứng minh AppCDS?

**Hỏi:** JVM `-Xshare:on` startup thành công và log thấy `java.lang.String` đến từ shared objects. Đã chứng minh **lớp ứng dụng** nằm trong kho chưa?

**Đáp án:** **Chưa.** Cần kiểm tra log của chính những lớp ứng dụng đã kỳ vọng được lưu. `-Xshare:on` chỉ ép cơ chế CDS khả dụng; không tự chứng minh AppCDS chứa mọi class.

### Bài 5: phân biệt lỗi chức năng

**Hỏi:** một JAR bắt buộc biến mất, `main` gặp `NoClassDefFoundError`, nhưng startup command có `-Xshare:auto`. Ứng dụng có được fallback để tiếp tục bình thường không?

**Đáp án:** Không. Fallback CDS không tạo lại dependency bị thiếu; phải sửa packaging/classpath.

### Bài 6: tối ưu vận hành hay fail fast?

**Hỏi:** môi trường staging muốn phát hiện ngay nếu không dùng được archive, còn production cần không phụ thuộc archive để đáp ứng readiness. Nên chọn gì?

**Đáp án:** Staging có thể dùng `-Xshare:on` kèm logging để **chẩn đoán**. Production dùng `-Xshare:auto` hoặc mặc định tương đương, quản lý archive theo build và theo dõi startup performance.

## 21. Checklist áp dụng trong deployment thực tế

1. Xác định **CDS archive mặc định** hay **AppCDS archive của ứng dụng** đang được dùng.
2. Nếu ưu tiên sẵn sàng dịch vụ, dùng `-Xshare:auto` (hoặc mặc định tương đương trên HotSpot hiện hành).
3. Tránh dùng `-Xshare:on` trong production; dành nó cho kiểm thử yêu cầu archive.
4. Không nhầm `auto` với `AutoCreateSharedArchive`; nếu muốn tạo/tái tạo kho, chọn workflow phù hợp JDK.
5. Tạo archive bằng **đúng runtime build** tương ứng image triển khai.
6. Rà soát classpath, module path và JAR sau mỗi release.
7. Không đặt giả định “có file là có sharing”; kiểm tra `-Xlog:cds=info` và `-Xlog:class+load=info`.
8. Khi fallback xảy ra, xác nhận JVM đã tới `main`/readiness và ứng dụng hoạt động, không chỉ nhìn mỗi log.
9. Tách lỗi CDS khỏi thiếu dependency, unsupported classfile, lỗi ứng dụng và lỗi tài nguyên khác.
10. Dùng `-Xshare:off` làm baseline khi điều tra hiệu năng.
11. Đo nhiều lần trong cùng môi trường; theo dõi startup latency và memory thay vì đoán mức cải thiện.
12. Giữ quyền truy cập archive và nguồn build tin cậy; không dựa vào `auto` như cơ chế bảo mật.
13. Xem version và tài liệu của **JDK thực tế**; những tùy chọn lưu trữ/AOT tiếp tục phát triển.
14. Nếu deploy dùng container, đi cùng image digest và app artifact tương thích; tránh mount archive từ build không khớp.
15. Định nghĩa policy rõ: **archive lỗi thì cảnh báo performance** hay **không được phép deploy**; đừng biến chế độ test thành policy startup production.

## Kết luận

**`-Xshare:auto` ưu tiên dùng dữ liệu lớp chia sẻ khi có thể và tiếp tục khởi động bình thường khi archive CDS/AppCDS không sử dụng được**. Tính chất *fail-safe* này giúp phân tách chức năng chính của ứng dụng khỏi một cơ chế tối ưu startup.

Ngược lại, **`-Xshare:on` yêu cầu CDS và có thể làm JVM dừng trước `main`**; tài liệu Oracle khuyến cáo chỉ dùng để kiểm thử, không dùng production. **`-Xshare:off` tắt thử dùng CDS** và hữu ích làm đối chứng.

Đừng hiểu rằng `auto` tự tạo archive, sửa thiếu dependency hay chứng minh ứng dụng thật sự lấy lớp từ AppCDS. Hãy kiểm tra log `cds`/`class+load`, quản lý archive tương thích với JDK và artifact, đo latency startup và tiếp tục test trên runtime/image triển khai thực tế. Đây là hành vi và cách vận hành **vẫn còn áp dụng trong Java/HotSpot hiện đại**, không phụ thuộc flag AppCDS đã lỗi thời.

## Tài liệu tham khảo chính thức và còn hiệu lực

- [Oracle Java SE 27 — `java` launcher, `-Xshare:auto/on/off` và Application Class Data Sharing](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): mô tả auto dùng shared data khi có thể, on bắt buộc dùng và không khuyến nghị production, off tắt CDS; hướng dẫn archives, dynamic dumps và cấu hình.
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): CDS mặc định từ JDK 12 trong Oracle JDK, AppCDS, startup và cách điều khiển ba chế độ.
- [Dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/): giải thích `auto` fail-safe và cách quan sát/debug khi archive không có hoặc không hợp lệ.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mốc AppCDS được bổ sung ở Java 10.
- [Oracle Java SE 25 — Creating Dynamic CDS Archive with `-XX:+AutoCreateSharedArchive`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cơ chế tự tạo/tái tạo dynamic archive và các giới hạn về JDK build.
- [Oracle Java SE 27 — JVM Unified Logging, `-Xlog`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): chẩn đoán `-Xlog:cds=info` và `-Xlog:class+load=info`.
