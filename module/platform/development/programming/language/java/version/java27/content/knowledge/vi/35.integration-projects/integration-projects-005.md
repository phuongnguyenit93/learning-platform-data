# Tạo bản phân phối ứng dụng có CI, runtime image và tài liệu vận hành

Một ứng dụng Java có mã nguồn đúng và chạy được bằng IDE vẫn chưa phải là **bản phân phối** có thể giao cho người vận hành. Khi đưa ứng dụng lên máy mới, còn phải trả lời những câu hỏi thực tế: dùng JDK nào, artifact nào tương thích hệ điều hành, cách khởi động, kiểm tra hoạt động, lấy log, quản lý cấu hình, cập nhật khi có bản vá bảo mật, rollback nếu phát hành lỗi và xác minh artifact đến từ pipeline đáng tin cậy ra sao?

Bài học trong chương **Thực hành tích hợp**, thuộc module **Java 27 và các kiến thức liên quan**, xây dựng một ví dụ xuyên suốt từ source code đến bản phân phối. Phạm vi tập trung vào các công cụ **đang được JDK 27 hỗ trợ**: `javac`, `jar`, `jdeps`, `jlink`, `jpackage`, JPMS, API I/O hiện hành và workflow CI. Không dùng Java Web Start, `jre` cài sẵn trên máy đích, mô hình Applet hay những cơ chế phát hành đã lỗi thời.

**Lưu ý vòng đời:** Java 27 là bản phát hành tính năng, **không phải LTS**. Khi chọn Java 27 để triển khai, đội vận hành cần có lịch nâng cấp theo bản phát hành kế tiếp, theo dõi thông báo bảo mật của JDK vendor và kiểm tra chính sách hỗ trợ. Đối với sản phẩm đòi hỏi nhịp nâng cấp chậm, có thể cân nhắc một bản JDK LTS phù hợp; nhưng toàn bộ bài này minh họa Java 27 đúng yêu cầu module.

## 1. Kết quả cần tạo ra

Sau bài học, một dự án thực tế có thể có:

1. **Mã nguồn Java modular** với `module-info.java` và entry point ổn định.
2. **Build artifact**: modular JAR đã compile, có version và checksum.
3. **Automated checks**: compile, kiểm tra đầu vào/đầu ra, negative tests và smoke test trên runtime image.
4. **Custom runtime image** được tạo bằng `jlink`, chứa các module cần thiết thay vì yêu cầu người dùng cài một JDK bên ngoài.
5. **Application image** được tạo bằng `jpackage`, có launcher và runtime đã đóng gói; có thể phát triển thành installer theo OS.
6. **CI pipeline** chạy trên Linux, Windows và macOS theo build matrix; chỉ phát hành khi các kiểm tra bắt buộc qua.
7. **Tài liệu vận hành (runbook)**: cài, chạy, cấu hình, chẩn đoán, cập nhật, rollback và gỡ cài đặt.
8. **Release metadata**: version, JDK vendor/build, OS/architecture, hash, nguồn build và những điều kiện tương thích.

### 1.1. Luồng tổng thể

~~~mermaid
flowchart LR
    S[Java source + tests] --> C[Compile]
    C --> J[Modular JAR]
    J --> T[Automated checks]
    T --> L[jlink runtime image]
    L --> R[Runtime smoke test]
    R --> P[jpackage app image]
    P --> V[Packaged launcher smoke test]
    V --> A[Archive, hashes, release metadata]
    A --> O[Install, operate, monitor, rollback]
~~~

**Quy tắc chất lượng:** nếu application image chưa từng được chạy thử trên hệ điều hành mục tiêu, thì việc `javac` thành công mới chứng minh tính đúng đắn ở mức compile, chưa chứng minh gói phát hành sử dụng được.

## 2. Các artifact phải phân biệt

| Thành phần | Ví dụ | Cấu trúc/chức năng | Có chạy ngay trên mọi hệ điều hành? |
|---|---|---|---|
| **Source** | `.java` và `module-info.java` | Dùng khi phát triển và kiểm tra | Không, cần compiler/runtime |
| **Modular JAR** | `com.example.ship.jar` | Classes/resources + module descriptor | Có thể cần Java 27 đúng và dependencies |
| **Custom runtime image** | `build/runtime/` | Runtime được `jlink` tạo cho một OS/CPU/JDK build | Không cross-platform |
| **Application image** | `ShipCli/` hoặc `ShipCli.app/` | Launcher + runtime + payload | Đặc thù hệ điều hành và kiến trúc |
| **Native installer** | `.msi`, `.dmg`, `.deb`, ... | Cơ chế cài đặt theo OS | Đặc thù host và công cụ đóng gói |
| **Release archive** | `.tar.gz`, `.zip` | Phương tiện truyền app image | Phải bảo toàn permissions/metadata phù hợp |
| **Runbook** | `RUNBOOK.md` | Chỉ dẫn vận hành, sự cố và khôi phục | Mang tính logic, cần điều chỉnh theo OS |
| **Manifest/hash** | `SHA256SUMS`, metadata release | Kiểm chứng nguồn/phiên bản/tính toàn vẹn | Cần được tin cậy theo kênh phân phối |

Một **runtime image** không đồng nghĩa **native-image executable** của một toolchain AOT khác. `jlink` tạo một Java runtime theo module graph; HotSpot, GC, class loading và các đặc trưng JVM vẫn tồn tại theo runtime image tương ứng.

## 3. Ví dụ dự án: ShipCli xử lý đơn hàng TSV

Chúng ta dùng một ứng dụng dòng lệnh giả định tên **ShipCli**. Nó đọc một file TSV chứa mã hàng và số lượng, tính tổng, ghi báo cáo UTF-8, có chế độ tự kiểm tra và xuất version. TSV được chọn để bài tập tập trung vào **quy trình phát hành** chứ không phải viết một CSV parser đầy đủ.

### 3.1. Các lệnh công khai

~~~text
ShipCli --health
ShipCli --version
ShipCli --report <input.tsv> <output.txt>
~~~

Quy ước exit code:

| Mã | Ý nghĩa |
|---|---|
| `0` | Thành công |
| `2` | Cú pháp hoặc dữ liệu đầu vào không hợp lệ |
| `3` | Lỗi I/O khi đọc/ghi dữ liệu |

**Contract:** đầu vào TSV có header chính xác `sku<TAB>quantity`, một mã hàng ASCII an toàn và số lượng nguyên dương trên mỗi dòng. Đây không phải giao thức CSV chuẩn đầy đủ; nếu nghiệp vụ có quoted fields, Unicode SKU hoặc trường rỗng hợp lệ, cần định nghĩa parser/schema và tests riêng.

### 3.2. Cây thư mục đề xuất

~~~text
ship-cli/
├── src/
│   ├── module-info.java
│   └── com/example/ship/Main.java
├── fixtures/
│   ├── valid.tsv
│   └── invalid.tsv
├── docs/
│   ├── RUNBOOK.md
│   └── RELEASE.md
├── .github/
│   └── workflows/
│       └── ci.yml
└── build/                 (được tạo trong build; không commit)
    ├── classes/
    ├── mods/
    ├── checks/
    ├── runtime/
    ├── packages/
    └── dist/
~~~

Những file trong cây là **mẫu tổ chức** của dự án thực hành. Trong bài này, mã nguồn, workflow và runbook được trình bày đầy đủ để có thể tự tạo chúng trong dự án riêng. Chúng không được tự ghi ra repository khác trong quá trình biên soạn bài Knowledge.

## 4. module-info.java và lựa chọn modular project

### 4.1. Mô tả module

Nội dung `src/module-info.java`:

~~~java
module com.example.ship {
    // Ứng dụng chỉ dùng các API thuộc java.base.
    // Không cần requires java.base vì đây là module mặc định.
}
~~~

Module có tên rõ giúp:

- Kiểm soát dependency qua `requires` khi dự án phát triển.
- Đưa artifact vào module graph có thể phân tích bằng `jdeps`.
- Sử dụng `jlink --add-modules com.example.ship` để đóng gói chính module ứng dụng cùng runtime.
- Tạo launcher bằng tên module/main class, không phụ thuộc vào classpath ngẫu nhiên.

Nếu một thư viện bên thứ ba chỉ có **automatic module**, nó có thể không link được thành image bằng `jlink` như một explicit module. Khi đó cần giải quyết module descriptor/provider, dùng dependency có module support hoặc chọn chiến lược đóng gói khác. Không thêm `--add-opens` hàng loạt chỉ để che sai module graph.

### 4.2. Không cần module opens cho CLI này

`Main` không cần export package và không dùng reflection framework. Vì vậy module descriptor tối giản là đủ. Khi ứng dụng tích hợp JSON mapping framework/DI cần reflective access, `opens` phải được đánh giá **theo package và module framework thực sự**.

Không tự động thêm `open module ...` hoặc `--add-opens ALL-UNNAMED` vào mọi sản phẩm, vì điều đó làm yếu encapsulation mà không có lợi ích nếu không cần.

## 5. Mã nguồn Java hoàn chỉnh: Main.java

Lưu dưới `src/com/example/ship/Main.java`:

~~~java
package com.example.ship;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.regex.Pattern;

public final class Main {

    private static final String VERSION = "1.0.0";

    private static final Pattern SKU =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private Main() {}

    public static void main(String[] args) {
        int exitCode = run(args, System.out, System.err);

        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    static int run(String[] args,
                   PrintStream out,
                   PrintStream err) {

        if (args.length == 1 && args[0].equals("--health")) {
            out.println("status=UP");
            return 0;
        }

        if (args.length == 1 && args[0].equals("--version")) {
            out.println("app=ShipCli");
            out.println("version=" + VERSION);
            out.println("java=" + Runtime.version().feature());
            return 0;
        }

        if (args.length != 3 || !args[0].equals("--report")) {
            err.println(
                    "Usage: --health | --version | --report "
                            + "<input.tsv> <output.txt>");
            return 2;
        }

        Path input = Path.of(args[1]).toAbsolutePath().normalize();
        Path output = Path.of(args[2]).toAbsolutePath().normalize();

        if (input.equals(output)) {
            err.println("Input and output must differ");
            return 2;
        }

        try {
            Summary summary = summarize(input);
            writeReport(output, summary);

            out.println("report=CREATED");
            out.println("records=" + summary.records());
            out.println("total_units=" + summary.totalUnits());

            return 0;
        } catch (IllegalArgumentException | ArithmeticException error) {
            err.println("Invalid data: " + error.getMessage());
            return 2;
        } catch (IOException error) {
            err.println("I/O failure: " + error.getMessage());
            return 3;
        }
    }

    private record Summary(int records, long totalUnits) {
        String toText() {
            return "records=" + records + "\n"
                    + "total_units=" + totalUnits + "\n";
        }
    }

    private static Summary summarize(Path input)
            throws IOException {

        try (BufferedReader reader =
                     Files.newBufferedReader(
                             input, StandardCharsets.UTF_8)) {

            String header = reader.readLine();
            if (!"sku\tquantity".equals(header)) {
                throw new IllegalArgumentException(
                        "Expected header: sku<TAB>quantity");
            }

            int records = 0;
            long totalUnits = 0L;
            String line;

            while ((line = reader.readLine()) != null) {
                int tab = line.indexOf('\t');

                if (tab <= 0 || tab != line.lastIndexOf('\t')) {
                    throw new IllegalArgumentException(
                            "Expected two TSV columns");
                }

                String sku = line.substring(0, tab);
                String rawQuantity = line.substring(tab + 1);

                if (!SKU.matcher(sku).matches()) {
                    throw new IllegalArgumentException(
                            "Invalid SKU: " + sku);
                }

                long quantity = Long.parseLong(rawQuantity);
                if (quantity <= 0) {
                    throw new IllegalArgumentException(
                            "Quantity must be positive");
                }

                records = Math.addExact(records, 1);
                totalUnits = Math.addExact(totalUnits, quantity);
            }

            if (records == 0) {
                throw new IllegalArgumentException(
                        "At least one record is required");
            }

            return new Summary(records, totalUnits);
        }
    }

    private static void writeReport(
            Path output, Summary summary) throws IOException {

        Path parent = output.getParent();
        if (parent == null || !Files.isDirectory(parent)) {
            throw new IOException("Output directory is missing");
        }

        // Temp file nằm cùng thư mục đích để hỗ trợ atomic rename.
        Path temporary =
                Files.createTempFile(parent, ".ship-", ".tmp");

        try {
            Files.writeString(
                    temporary,
                    summary.toText(),
                    StandardCharsets.UTF_8);

            Files.move(
                    temporary,
                    output,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

### 5.1. Những quyết định thiết kế cần lưu ý

- **UTF-8 tường minh:** không phụ thuộc default charset của hệ điều hành.
- **Định dạng TSV tối giản:** chỉ hai cột, không có quoted tabs; parser này chỉ phù hợp contract đã định nghĩa.
- **Kiểm tra input:** SKU có tập ký tự rõ, quantity dương, `Math.addExact` phát hiện overflow thay vì trả tổng sai.
- **Exit codes:** thuận tiện cho shell, monitoring và automation.
- **Resource ownership:** `BufferedReader` được đóng bởi `try`-with-resources.
- **Ghi qua temp file:** hạn chế trường hợp tạo report nửa chừng. `ATOMIC_MOVE` chỉ hoạt động khi filesystem/OS hỗ trợ; nếu không, method thất bại và dọn file tạm, **không âm thầm hạ xuống ghi trực tiếp không nguyên tử**.
- **Report hiện có:** ví dụ cho phép ghi đè target vì người gọi đã chỉ rõ output; sản phẩm thật cần contract phù hợp khi overwrite, locking, backup và độ an toàn trước symlink.
- **Không giữ dữ liệu vào List:** xử lý theo dòng, phù hợp với file lớn hơn demo, nhưng vẫn phải áp dụng giới hạn file size/row count theo nghiệp vụ thật.

### 5.2. Giới hạn security của ví dụ

Đây là CLI dùng với file do **người vận hành tin cậy** chỉ định. Không nên mở nó thành HTTP API nhận đường dẫn tùy ý rồi dùng quyền của service để ghi report, vì sẽ có nguy cơ path traversal, overwrite, symlink attack và lộ file.

Nếu output đến từ dữ liệu không tin cậy, phải giới hạn vào một data directory được phép, kiểm tra permissions, xử lý symlink/race và tránh ghi đè file ngoài scope.

## 6. Định nghĩa input/output và test cases

File `fixtures/valid.tsv` chứa hai cột, phân cách bằng **ký tự tab thật**:

~~~text
sku	quantity
book-01	2
pen-02	5
~~~

Kỳ vọng output `report.txt`:

~~~text
records=2
total_units=7
~~~

File `fixtures/invalid.tsv`:

~~~text
sku	quantity
book-01	-1
~~~

Kỳ vọng: exit code `2` và không tạo report mới.

### 6.1. Các ca kiểm tra cơ bản

| Trường hợp | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Health | `--health` | `status=UP`, exit `0` |
| Version | `--version` | App version và JDK feature |
| Report chuẩn | TSV hợp lệ | `records=2`, `total_units=7` |
| Header sai | Không phải `sku<TAB>quantity` | Exit `2` |
| Quantity âm/không phải số | `-1`, `abc` | Exit `2` |
| TSV dư cột | Hai tab trên một dòng | Exit `2` |
| Không có dòng dữ liệu | Chỉ có header | Exit `2` |
| Source thiếu | Đường dẫn không tồn tại | Exit `3` |
| Output directory thiếu | Thư mục đích không tồn tại | Exit `3` |
| Input trùng output | Cùng path chuẩn hóa | Exit `2` |
| Tổng số vượt giới hạn `long` | Nhiều quantity rất lớn | Exit `2` |
| Filesystem không hỗ trợ atomic move | Target không hỗ trợ `ATOMIC_MOVE` | Exit `3`, không hoàn thành báo cáo |

**Lưu ý:** `--health` ở ví dụ chỉ kiểm tra entry point/khả năng chạy của CLI, không chứng minh database hay external services của một hệ thống server đang sẵn sàng. Khi chuyển thành dịch vụ thực, liveness và readiness phải có semantics riêng.

## 7. Biên dịch thành modular JAR với JDK 27

Các lệnh dưới đây minh họa trên shell Bash của Linux/macOS, hoặc Bash có sẵn trên GitHub-hosted Windows runner. Chúng giả định đang ở **thư mục gốc dự án**, và JDK 27 có trong `PATH`.

~~~bash
java --version
javac --version

mkdir -p build/classes build/mods

javac --release 27 \
      -encoding UTF-8 \
      -Xlint:all \
      -d build/classes \
      src/module-info.java \
      src/com/example/ship/Main.java

jar --create \
    --file build/mods/com.example.ship.jar \
    --main-class com.example.ship.Main \
    -C build/classes .
~~~

`javac --release 27` yêu cầu JDK compiler có khả năng compile Java 27 và đảm bảo source/class API phù hợp target 27. `--release 27` không có nghĩa JAR này chạy trên Java 21 hay tự chứa một JVM.

Sau khi tạo JAR, xác minh:

~~~bash
jar --describe-module \
    --file build/mods/com.example.ship.jar

java --module-path build/mods \
     --module com.example.ship/com.example.ship.Main \
     --health
~~~

Vì `jar --main-class` đặt module main class, ở một số lệnh có thể rút gọn sang `--module com.example.ship`; bài vẫn dùng `module/main-class` tường minh cho dễ đọc.

### 7.1. Không hardcode JAVA_HOME của máy dev

Pipeline phải thiết lập JDK được yêu cầu và in `java --version` / `javac --version` vào log. Trên CI hoặc máy developer nhiều JDK, `JAVA_HOME` và `PATH` có thể trỏ tới phiên bản khác nhau; kiểm tra trước khi build để tránh artifact không đúng release.

### 7.2. Test khả năng load trước khi link

Modular JAR compile xong phải chạy được trên JDK thường, trước khi xây runtime image. Nếu lỗi `FindException` hoặc `NoClassDefFoundError`, chẩn đoán module graph/dependency đầu tiên; không đổ lỗi cho `jlink` khi ngay cả app gốc chưa chạy được.

## 8. Tự động hóa smoke tests không cần thư viện test bên ngoài

Trong ví dụ tích hợp này, có thể dùng các phép kiểm tra black-box để giữ project nhỏ và độc lập build tool.

~~~bash
mkdir -p build/checks

java --module-path build/mods \
     --module com.example.ship/com.example.ship.Main \
     --health > build/checks/health.txt

grep -Fx 'status=UP' build/checks/health.txt

printf 'sku\tquantity\nbook-01\t2\npen-02\t5\n' \
    > build/checks/input.tsv

java --module-path build/mods \
     --module com.example.ship/com.example.ship.Main \
     --report \
     build/checks/input.tsv \
     build/checks/report.txt

grep -Fx 'records=2' build/checks/report.txt
grep -Fx 'total_units=7' build/checks/report.txt
~~~

Để kiểm tra mã lỗi, shell phải **thật sự kiểm tra exit status**:

~~~bash
printf 'sku\tquantity\nbad\t-1\n' \
    > build/checks/invalid.tsv

if java --module-path build/mods \
        --module com.example.ship/com.example.ship.Main \
        --report \
        build/checks/invalid.tsv \
        build/checks/invalid-report.txt; then
    echo "ERROR: invalid input unexpectedly succeeded"
    exit 1
fi

if test -e build/checks/invalid-report.txt; then
    echo "ERROR: invalid input created a report"
    exit 1
fi
~~~

Lệnh `if ...; then` ở đây chỉ kiểm tra **bất kỳ nonzero exit code**. Với một CI production-quality, nên kiểm tra **chính xác exit code 2**, diagnostic message và file output không bị thay đổi nếu đã tồn tại.

### 8.1. Kiểm thử thật vẫn cần JUnit

Black-box smoke tests không thay unit tests cho parser, overflow, symlink race, cancellation hoặc error paths. Khi dự án phát triển, bổ sung **JUnit Jupiter phiên bản hiện hành**, integration tests có dữ liệu riêng và kiểm thử regression ở boundaries.

Không nên dùng `Thread.sleep`, retry mù hoặc tăng timeout để biến một test không ổn định thành pass.

## 9. Kiểm tra module graph bằng jdeps

`jdeps` phân tích dependencies từ bytecode. Với modular JAR:

~~~bash
jdeps --module-path build/mods \
      --module com.example.ship \
      --list-deps
~~~

Với ứng dụng đơn giản này, dependency chính dự kiến là `java.base`. Để tìm module list đưa vào `jlink` trong trường hợp classpath/dependency phức tạp:

~~~bash
jdeps --print-module-deps \
      --module-path build/mods \
      build/mods/com.example.ship.jar
~~~

**Không coi kết quả static analysis là bảo đảm đầy đủ mọi runtime dependency.** Reflection, `ServiceLoader`, JDBC driver, locale data, TLS provider, agent và plugin load động có thể yêu cầu những module mà `jdeps` không thấy.

Nếu ứng dụng sử dụng service providers được phát hiện động, xem xét `jlink --bind-services` hoặc liệt kê provider modules có chủ đích và **đo kích thước image** sau thay đổi. `--bind-services` có thể kéo thêm module không cần, nên không bật theo phản xạ.

### 9.1. Kiểm tra modules có trong runtime

Sau khi link:

~~~bash
build/runtime/bin/java --list-modules
~~~

Module list chứng minh image có những module đã link, **không** tự chứng minh mọi nhánh ứng dụng đều chạy. Phải có smoke/integration tests trên runtime image thật.

## 10. Tạo custom runtime image bằng jlink

Từ modular JAR đã build:

~~~bash
jlink \
    --module-path build/mods \
    --add-modules com.example.ship \
    --launcher ship-cli=com.example.ship/com.example.ship.Main \
    --output build/runtime \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=zip-6
~~~

Lệnh trên sử dụng các option `jlink` hiện hành được JDK 27 hỗ trợ. `--compress=zip-6` dùng cú pháp mới, không dùng các giá trị `--compress=1`/`2` đã deprecated. Các lệnh này giả định thư mục `build/runtime` **chưa tồn tại** hoặc đã được pipeline dọn hợp lệ trước khi chạy; `jlink` không ghi đè một image có sẵn theo cách tùy ý.

### 10.1. Những gì jlink làm

- Xây image từ `com.example.ship` và các module transitively required.
- Đặt JDK runtime components và launcher ở `build/runtime`.
- Loại bỏ debug metadata/header/manual files theo option đã chọn.
- Chỉ tạo image cho **OS và CPU architecture của JDK đang dùng**; nó không cross-compile thành runtime Windows khi chạy trên Linux.
- Không tự xử lý mọi file dữ liệu, thư viện native, license, cấu hình hoặc service scripts của ứng dụng.

### 10.2. Smoke test trực tiếp launcher mới

~~~bash
build/runtime/bin/ship-cli --health
build/runtime/bin/ship-cli --version

build/runtime/bin/ship-cli \
    --report build/checks/input.tsv \
    build/checks/linked-report.txt

grep -Fx 'total_units=7' build/checks/linked-report.txt
~~~

Trên Windows, launcher có hậu tố `.exe` và đường dẫn có thể dùng slash/backslash theo shell. Không kiểm tra thành công chỉ bằng sự tồn tại của `build/runtime/bin/java`; cần chạy **chính entry point của ứng dụng**.

### 10.3. Vì sao không chỉ phát JAR?

Phát JAR vẫn hợp lý khi môi trường vận hành có JDK/JRE do đội platform quản lý tập trung. Custom runtime image phù hợp khi muốn:

- Bớt giả định người dùng cuối đã cài Java đúng version.
- Kiểm soát chính xác bộ modules/JDK build đi kèm.
- Tạo installation dễ sao chép và chạy.
- Giảm footprint so với full JDK trong nhiều trường hợp.

Đổi lại, image phải được build và cập nhật cho từng target, bao gồm **các security patches của JDK**. Dùng image tự đóng gói nghĩa là đội phát hành chịu trách nhiệm đưa các bản vá runtime đến người dùng.

## 11. jpackage: tạo application image có launcher

### 11.1. App image so với native installer

`jpackage --type app-image` tạo một thư mục ứng dụng có launcher và runtime/payload. Nó **không phải** một installer `.deb`, `.msi` hay `.dmg`.

Các định dạng native installer mà `jpackage` hỗ trợ phụ thuộc OS:

| OS build | Định dạng thường dùng |
|---|---|
| Windows | `exe`, `msi` |
| macOS | `dmg`, `pkg` |
| Linux | `deb`, `rpm` |
| Tất cả OS được hỗ trợ | `app-image` |

Oracle mô tả rõ: **jpackage không hỗ trợ cross-platform packaging**. Tạo gói dành cho Windows trên Windows, macOS trên macOS, Linux trên Linux. Việc ký/notarize/gắn metadata installer còn phụ thuộc toolchain và chứng chỉ nền tảng.

### 11.2. Đóng gói từ runtime đã tạo

~~~bash
mkdir -p build/packages

jpackage \
    --type app-image \
    --name ShipCli \
    --app-version 1.0.0 \
    --module com.example.ship/com.example.ship.Main \
    --runtime-image build/runtime \
    --dest build/packages
~~~

Ở đây custom runtime `build/runtime` đã chứa module ứng dụng, nên `jpackage` có thể dùng `--module` và `--runtime-image` mà không cần tạo lại image qua jlink.

**Không đồng thời trộn** `--main-jar` và `--module`: một cái cho launch classpath/non-modular, cái còn lại cho ứng dụng modular. Cũng không nhầm `--input` (payload files) với `--runtime-image` (JVM runtime đã link).

### 11.3. Ví dụ đường dẫn launcher dự kiến

~~~text
Linux:
  build/packages/ShipCli/bin/ShipCli

Windows:
  build/packages/ShipCli/ShipCli.exe

macOS:
  build/packages/ShipCli.app/Contents/MacOS/ShipCli
~~~

Đây là layout phổ biến cho `jpackage` app image; cần xác minh output thật của bản JDK/OS đang build. Nếu muốn ứng dụng luôn chạy headless ở Windows và có console phù hợp, xem xét `--win-console` cho launcher theo yêu cầu. Một app CLI trên macOS có thể cần hình thức phân phối phù hợp hơn `.app` nếu người dùng muốn chạy trong terminal.

### 11.4. Cho jpackage tự link runtime

Nếu không cần tự kiểm soát `jlink`, có thể đơn giản hóa:

~~~bash
jpackage \
    --type app-image \
    --name ShipCli \
    --app-version 1.0.0 \
    --module-path build/mods \
    --module com.example.ship/com.example.ship.Main \
    --dest build/packages
~~~

Khi không truyền `--runtime-image`, `jpackage` có thể gọi `jlink` và dùng các `--jlink-options` đã cấu hình.

**Chọn một trong hai:** (a) tự tạo runtime rồi pass vào `jpackage`, hoặc (b) để `jpackage` tự tạo runtime. Không cần tạo hai runtime vô ích trong một build chỉ để được xem là “đã dùng cả hai công cụ”.

## 12. Kiểm tra bản phân phối hoàn chỉnh

### 12.1. Kiểm tra khác với source build

Sau khi `jpackage` chạy thành công, smoke test phải dùng **launcher từ app image**, không phải `java -cp` từ JDK build.

Ví dụ Linux:

~~~bash
build/packages/ShipCli/bin/ShipCli --health
build/packages/ShipCli/bin/ShipCli --version

build/packages/ShipCli/bin/ShipCli \
    --report build/checks/input.tsv \
    build/checks/packaged-report.txt

grep -Fx 'total_units=7' \
    build/checks/packaged-report.txt
~~~

Windows và macOS dùng launcher tương ứng. Bản có GUI/installer nên có automation kiểm tra launch sau cài đặt, quyền và khả năng gỡ bỏ riêng.

### 12.2. Kiểm tra cả lỗi

Thử các trường hợp quan trọng:

- Chạy ở working directory khác thư mục cài đặt.
- Chạy khi `JAVA_HOME` không trỏ tới JDK 27 (vì app image có runtime riêng).
- Tên đường dẫn chứa khoảng trắng và Unicode.
- File nguồn không tồn tại, output directory không writable.
- User không có quyền ghi vào thư mục cài đặt.
- File output cũ tồn tại, overwrite được cho phép hoặc bị cấm theo contract.
- Ứng dụng bị dừng giữa quá trình ghi report.
- Máy cài cùng lúc hai phiên bản, muốn rollback.
- JDK/OS security policy, Gatekeeper/SmartScreen/signature nếu phát installer.

Một smoke test `--health` duy nhất là điểm bắt đầu, không đủ để khẳng định toàn bộ gói hoạt động trong production.

## 13. CI pipeline: tách verify và packaging

### 13.1. Các quality gates tối thiểu

Một workflow CI đáng tin nên:

1. Tải source từ commit xác định.
2. Cài **JDK 27** từ distribution được chọn và in version.
3. Compile với cảnh báo phù hợp.
4. Tạo modular JAR.
5. Chạy test đầu vào hợp lệ và đầu vào không hợp lệ.
6. Link runtime image và chạy launcher test.
7. Package app image theo host OS.
8. Smoke test launcher từ gói.
9. Archive artifact và lưu metadata/version/checksum.
10. Chỉ chạy bước publish/release trên branch/tag được bảo vệ và có quyền hợp lệ.

CI **không đồng nghĩa CD**. Build artifact từ pull request không tự được publish cho người dùng cuối. Quyền release cần tách khỏi quyền chạy test của untrusted contributions.

### 13.2. Workflow GitHub Actions ví dụ

Tài liệu hiện hành của GitHub hỗ trợ `actions/checkout@v7`, `actions/setup-java@v6` và `actions/upload-artifact@v7` trên hosted runners tương thích. Khi áp dụng vào hệ thống công ty, nên **pin immutable commit SHA** theo security policy thay vì chỉ dùng floating major tag. Workflow mẫu dưới đây chỉ chạy build/đóng gói, **không publish release**.

Giả sử lưu thành `.github/workflows/ci.yml`:

~~~yaml
name: Java 27 build and package

on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '27'

      - name: Compile, package JAR and smoke tests
        shell: bash
        run: |
          set -euo pipefail
          java --version
          mkdir -p build/classes build/mods build/checks

          javac --release 27 -encoding UTF-8 -Xlint:all \
            -d build/classes \
            src/module-info.java \
            src/com/example/ship/Main.java

          jar --create \
            --file build/mods/com.example.ship.jar \
            --main-class com.example.ship.Main \
            -C build/classes .

          java --module-path build/mods \
            -m com.example.ship/com.example.ship.Main \
            --health | grep -Fx 'status=UP'

          printf 'sku\tquantity\nbook-01\t2\npen-02\t5\n' \
            > build/checks/input.tsv

          java --module-path build/mods \
            -m com.example.ship/com.example.ship.Main \
            --report \
            build/checks/input.tsv \
            build/checks/report.txt

          grep -Fx 'records=2' build/checks/report.txt
          grep -Fx 'total_units=7' build/checks/report.txt

          printf 'sku\tquantity\nbad\t-1\n' \
            > build/checks/invalid.tsv

          if java --module-path build/mods \
              -m com.example.ship/com.example.ship.Main \
              --report \
              build/checks/invalid.tsv \
              build/checks/invalid-report.txt; then
            echo "Expected invalid input failure"
            exit 1
          fi

          test ! -e build/checks/invalid-report.txt

  package:
    needs: verify
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '27'

      - name: Compile, link and package
        shell: bash
        run: |
          set -euo pipefail
          java --version
          mkdir -p build/classes build/mods build/packages build/dist

          javac --release 27 -encoding UTF-8 \
            -d build/classes \
            src/module-info.java \
            src/com/example/ship/Main.java

          jar --create \
            --file build/mods/com.example.ship.jar \
            --main-class com.example.ship.Main \
            -C build/classes .

          jlink \
            --module-path build/mods \
            --add-modules com.example.ship \
            --launcher ship-cli=com.example.ship/com.example.ship.Main \
            --output build/runtime \
            --strip-debug --no-header-files --no-man-pages \
            --compress=zip-6

          if [[ "$RUNNER_OS" == "Windows" ]]; then
            build/runtime/bin/ship-cli.exe --health |
              grep -Fx 'status=UP'
          else
            build/runtime/bin/ship-cli --health |
              grep -Fx 'status=UP'
          fi

          jpackage \
            --type app-image \
            --name ShipCli \
            --app-version 1.0.0 \
            --module com.example.ship/com.example.ship.Main \
            --runtime-image build/runtime \
            --dest build/packages

          case "$RUNNER_OS" in
            Windows)
              build/packages/ShipCli/ShipCli.exe --health |
                grep -Fx 'status=UP'
              pwsh -NoProfile -Command \
                "Compress-Archive -Path 'build/packages/ShipCli' -DestinationPath 'build/dist/ShipCli-windows.zip'"
              ;;
            macOS)
              build/packages/ShipCli.app/Contents/MacOS/ShipCli --health |
                grep -Fx 'status=UP'
              tar -czf build/dist/ShipCli-macos.tar.gz \
                -C build/packages ShipCli.app
              ;;
            Linux)
              build/packages/ShipCli/bin/ShipCli --health |
                grep -Fx 'status=UP'
              tar -czf build/dist/ShipCli-linux.tar.gz \
                -C build/packages ShipCli
              ;;
          esac

      - name: Upload packaged image
        uses: actions/upload-artifact@v7
        with:
          name: shipcli-${{ matrix.os }}
          path: build/dist/
          if-no-files-found: error
~~~

### 13.3. Giới hạn và điều kiện của workflow mẫu

- Workflow cần **JDK 27 distribution đã công bố** cho OS/architecture của runner; nếu distribution chưa có cho target, job phải fail rõ ràng và đội build chọn distribution khác có hỗ trợ.
- Các hosted runners cần phiên bản runner tương thích với action Node.js hiện hành, đặc biệt khi dùng self-hosted runners.
- `shell: bash` trên Windows-hosted runner sử dụng Bash đi kèm môi trường Git for Windows, không phải mặc định PowerShell.
- `jpackage` app image trên macOS có layout `.app`; installer cho người dùng cuối có thể yêu cầu signing/notarization riêng.
- `Compress-Archive` là công cụ PowerShell trên Windows runner; tarballs ở Unix-like giúp bảo toàn mode bit của launcher tốt hơn upload raw folder.
- App image chưa được kiểm tra **sau cài đặt installer** và chưa có mã ký. Không dùng kết quả pipeline này làm bằng chứng “đã sẵn sàng phân phối public” nếu môi trường yêu cầu installer/codesigning/SBOM.
- CI mẫu biên dịch lại trên từng OS để tạo artifact riêng; Java bytecode về nguyên tắc đa nền tảng, nhưng runtime image và native launcher **không** đa nền tảng.
- Build lại JAR trên từng host có thể khác metadata/timestamp. **Reproducible build** cần thiết lập riêng về timestamp, input ordering và toolchain pinning.

## 14. Vì sao CI phải package trên từng hệ điều hành?

### 14.1. Không dùng jpackage Linux tạo Windows MSI

`jpackage` tạo package theo cơ chế native host; không hỗ trợ cross-platform output. `jlink` cũng tạo runtime image theo target OS/architecture của JDK đang sử dụng.

~~~mermaid
flowchart TD
    S[Source + pinned JDK requirements] --> L[Linux job]
    S --> W[Windows job]
    S --> M[macOS job]
    L --> LA[Linux runtime + app image]
    W --> WA[Windows runtime + app image]
    M --> MA[macOS runtime + .app]
~~~

Nếu phải hỗ trợ `linux-aarch64` bên cạnh `linux-x86_64`, cần thêm runner/môi trường build cho architecture đó. **Không gán nhãn artifact chỉ dựa trên OS** khi sản phẩm thật hỗ trợ nhiều kiến trúc.

### 14.2. Khi nào chỉ cần một build target?

Nếu sản phẩm chỉ triển khai trên Linux x86_64 trong một container chuẩn hóa, build matrix Windows/macOS có thể là chi phí không cần thiết. Chọn matrix theo **supported platforms contract**, không theo danh sách OS dài nhất có thể.

Ngược lại, một app desktop bán cho người dùng nhiều hệ điều hành cần kiểm thử packaging, permissions, UX và update/uninstall trên từng hệ.

## 15. Tạo installer cho hệ điều hành mục tiêu

### 15.1. Các ví dụ độc lập với app-image

Trên **Windows** đã có toolchain cần thiết:

~~~bash
jpackage --type msi \
    --name ShipCli \
    --app-version 1.0.0 \
    --module-path build/mods \
    --module com.example.ship/com.example.ship.Main \
    --dest build/installers
~~~

Trên **macOS**:

~~~bash
jpackage --type dmg \
    --name ShipCli \
    --app-version 1.0.0 \
    --module-path build/mods \
    --module com.example.ship/com.example.ship.Main \
    --dest build/installers
~~~

Trên **Linux** có công cụ `deb` tương ứng:

~~~bash
jpackage --type deb \
    --name ShipCli \
    --app-version 1.0.0 \
    --module-path build/mods \
    --module com.example.ship/com.example.ship.Main \
    --dest build/installers
~~~

Các ví dụ trên cho `jpackage` **tự link runtime**. Nếu muốn installer dùng chính runtime đã link và smoke-test trước đó, có thể dùng `--runtime-image build/runtime`, `--module ...` và các option installer thích hợp theo tài liệu target OS.

Không chạy lệnh Windows MSI trên Linux rồi xem đó là tình huống tool “không tương thích Java 27”: vấn đề là host OS và native packaging prerequisites.

### 15.2. Signing và notarization là bước riêng

Một ứng dụng macOS phân phối rộng thường cần codesigning/notarization theo chính sách Apple. Windows installer có thể cần mã ký để xây niềm tin và giảm cảnh báo SmartScreen; Linux package repositories có cơ chế ký và xác thực metadata riêng.

**Không đưa private signing key vào mã nguồn hoặc artifact pull request.** CI release nên dùng secret store, protected environments, quyền hạn tối thiểu và approval khi cần. Không chạy signing step chứa secrets trên untrusted fork PR.

## 16. Đóng gói cấu hình, dữ liệu và native dependencies

### 16.1. Tách immutable app và mutable data

Một installation nên có ranh giới:

~~~text
Application image (immutable theo release):
  runtime/
  launcher/
  application modules/
  static resources/

Operator-owned data (không ghi đè khi update):
  config/
  input/
  output/
  logs/
  state/
~~~

Ứng dụng ví dụ nhận đường dẫn input/output qua tham số; nó không ghi dữ liệu vào thư mục runtime. Đây là lựa chọn tốt cho khả năng cập nhật và rollback, vì app image có thể được thay mà không đụng dữ liệu nghiệp vụ.

### 16.2. Cấu hình nên truyền thế nào?

Ứng dụng có thể nhận:

- CLI arguments cho mỗi lần chạy.
- Environment variables cho đường dẫn, feature switches không nhạy cảm.
- Config file nằm ngoài app image do người vận hành sở hữu.
- Secret manager cho tokens/passwords, không lưu secret trong JAR hoặc runtime image.

Tránh ghi toàn bộ environment hoặc command line có thể chứa secret ra log. Nếu ứng dụng có cấu hình bắt buộc, fail fast với thông báo **không rò giá trị nhạy cảm**.

### 16.3. Native libraries

Nếu ứng dụng có JNI/FFM, phải đóng gói binary phù hợp OS/CPU/ABI và cấp native access theo chính sách runtime khi dùng restricted operations. `jlink` không biến `.so` thành `.dll` hay tự xử lý phụ thuộc OS loader.

Bản phân phối nên kiểm tra tính toàn vẹn native dependencies, licence và file permissions. Những ứng dụng Java-only như ShipCli tránh được một phần độ phức tạp này.

## 17. Release metadata, checksum và artifact provenance

### 17.1. Thông tin tối thiểu của một release

Một metadata record nên ghi:

~~~yaml
application: ShipCli
version: 1.0.0
javaFeature: 27
jdkVendor: "<distribution-name>"
jdkBuild: "<exact java --version output>"
os: "<linux|windows|macos>"
architecture: "<x86_64|aarch64|...>"
sourceCommit: "<git-sha>"
sourceTag: "<tag>"
artifactName: "<release-archive-filename>"
sha256: "<actual-calculated-hash>"
buildTimestampUtc: "<ISO-8601 timestamp>"
buildWorkflowRun: "<CI-run-id>"
~~~

Đây là **schema đề xuất** cho release metadata; các placeholder chỉ được thay bằng giá trị thực của pipeline. Không thêm field vào YAML Knowledge mà Prime giao: metadata minh họa này dành cho hệ thống phát hành riêng.

### 17.2. Checksum không đồng nghĩa chữ ký số

- **SHA-256 hash**: phát hiện artifact bị thay đổi so với giá trị đã biết.
- **Digital signature**: giúp kiểm chứng artifact/metadata do chủ thể được tin cậy phát hành (nếu key và chain-of-trust được bảo vệ).
- **Artifact attestation / provenance**: bổ sung thông tin artifact được build từ source/workflow nào.
- **SBOM**: liệt kê dependency components để theo dõi licenses/vulnerabilities.

Nếu attacker có thể sửa cả artifact lẫn file SHA256SUMS trong cùng kênh chưa được bảo vệ, checksum riêng không chống giả mạo. Cần kiểm tra checksum qua kênh tin cậy hoặc xác minh chữ ký.

### 17.3. Đo hash theo OS

Ví dụ Linux:

~~~bash
sha256sum build/dist/ShipCli-linux.tar.gz
~~~

macOS:

~~~bash
shasum -a 256 build/dist/ShipCli-macos.tar.gz
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build/dist/ShipCli-windows.zip -Algorithm SHA256
~~~

Không ghi một chuỗi hash giả vào runbook rồi yêu cầu người dùng tin theo. Release thật phải ghi giá trị do pipeline tính cho **đúng artifact được upload**, sau khi archive đã hoàn tất.

## 18. Tạo tài liệu vận hành (RUNBOOK.md)

Một bản phân phối có thể chạy tốt ở CI nhưng khó vận hành nếu không có hướng dẫn. Runbook nên dễ đọc tại thời điểm sự cố, với lệnh **copy/paste được khi đã thay các placeholder** và điều kiện tương ứng OS.

### 18.1. Runbook mẫu: thông tin release

~~~markdown
# ShipCli — Runbook

## Phiên bản và nền tảng
- Ứng dụng: ShipCli 1.0.0
- Java: Runtime image tích hợp từ JDK 27
- OS/architecture: dùng artifact phù hợp máy nhận
- Đầu vào: TSV UTF-8, header sku<TAB>quantity
- Đầu ra: TXT UTF-8, hai dòng records và total_units
- Thư mục data: thư mục do operator chọn, ngoài app image

## Điều kiện trước khi cài
1. Kiểm tra OS và architecture của máy.
2. Kiểm tra checksum/signature của archive qua metadata release tin cậy.
3. Đảm bảo có quyền execute launcher và quyền đọc/ghi thư mục data.
4. Chọn nơi đặt app image không bị ứng dụng thường xuyên ghi đè.

## Chạy thử
- Linux: ./ShipCli/bin/ShipCli --health
- Windows: .\ShipCli\ShipCli.exe --health
- macOS: ./ShipCli.app/Contents/MacOS/ShipCli --health

Kết quả mong đợi: status=UP và exit code 0.
~~~

### 18.2. Runbook mẫu: tạo báo cáo

~~~markdown
## Tạo báo cáo
1. Chuẩn bị file input.tsv ở một đường dẫn có quyền đọc.
2. Tạo trước thư mục output (ví dụ data/out/).
3. Chạy launcher của hệ điều hành với:
   --report <path-to-input.tsv> <path-to-output.txt>
4. Kiểm tra exit code, output file và tổng đơn vị.

Mã lỗi:
- 0: thành công
- 2: tham số hoặc dữ liệu không hợp lệ
- 3: lỗi I/O

Không chạy CLI với đặc quyền quản trị chỉ để ghi được vào thư mục cài.
Kiểm tra quyền của thư mục dữ liệu trước.
~~~

### 18.3. Runbook mẫu: cập nhật và rollback

~~~markdown
## Update
1. Tải bản phân phối mới từ kênh chính thức.
2. Kiểm tra chữ ký/hash và nền tảng.
3. Chạy smoke test trong staging.
4. Lưu bản phát hành cũ để rollback.
5. Dừng công việc đang xử lý trước khi thay launcher/image.
6. Cài bản mới ở một versioned directory riêng.
7. Kiểm tra --version, --health và report thử với fixture.
8. Chuyển alias/symlink hoặc đường dẫn vận hành sang phiên bản mới.
9. Theo dõi mã lỗi/log/metrics trong khoảng giám sát quy định.

## Rollback
1. Ngừng nhận công việc mới và kết thúc tác vụ đang chạy an toàn.
2. Trả alias/path sang bản cũ còn được hỗ trợ.
3. Kiểm tra app version và chạy smoke test.
4. Kiểm tra dữ liệu/định dạng output có còn tương thích không.
5. Ghi nhận sự cố và mở bản điều tra nguyên nhân gốc.
~~~

Không mặc định rollback ứng dụng kéo theo **rollback dữ liệu**. Nếu release mới có thay đổi schema hoặc ghi dữ liệu không tương thích, cần rollback plan có backward compatibility và migration/data recovery riêng.

## 19. Quy trình khởi động, dừng và mã lỗi

### 19.1. Quyền sở hữu process

Đối với CLI chạy theo lô, runbook phải xác định:

- Người chạy hoặc scheduler sở hữu process.
- Input đến từ đâu, output được lưu ở đâu.
- Khi nào một run được xem là thành công.
- Retry có an toàn/idempotent không.
- Nếu nhận SIGTERM hoặc stop request, dữ liệu đang ghi cần xử lý ra sao.

Ở ví dụ ShipCli, ghi output qua temp file và atomic move giúp tránh một số trường hợp output bị cắt giữa chừng, nhưng không bảo đảm **end-to-end exactly-once processing**. Một scheduled job retry nhiều lần có thể vẫn ghi đè file output theo contract hiện tại.

### 19.2. Không dùng health check giả cho dependency thật

`--health` trong ShipCli có nghĩa “entry point hoạt động”. Với service có database, queue hoặc external API, cần phân biệt:

- **Liveness:** tiến trình có nên được restart hay không.
- **Readiness:** tiến trình có thể nhận workload mới hay không.
- **Startup probe:** cho phép thời gian khởi động, tránh restart vòng lặp.
- **Business smoke:** một giao dịch thực hoặc synthetic transaction có thể hoàn tất không.

Một API trả HTTP 200 ở `/health` không phải bằng chứng mọi dependency đã sẵn sàng hoặc mọi chức năng hoạt động.

## 20. Observability và diagnostics khi bản phân phối lỗi

### 20.1. Bộ thông tin sự cố tối thiểu

Một incident report có thể gồm:

~~~text
Application version:
Artifact checksum:
JDK vendor / exact runtime build:
OS / architecture:
Command + arguments (redact secrets):
Exit code:
Start timestamp UTC:
Last successful run:
Input schema version:
Error messages and stack traces:
Available disk space:
File permissions:
Relevant logs:
Rollback attempted?:
~~~

Không ghi mật khẩu, token, PII hoặc dữ liệu nội bộ không cần thiết vào issue tracker.

### 20.2. Lệnh chẩn đoán JDK runtime image

Nếu image được tạo bằng `jlink`, một số developer tools như `jcmd`, `jfr`, `jstack` **có thể không được đưa vào image** tùy lựa chọn modules/flags. Đừng yêu cầu operator chạy `jcmd` trong image tối giản rồi mặc định nó có sẵn.

Có thể dùng JDK 27 riêng của đội vận hành trên máy chẩn đoán phù hợp nếu attach được, hoặc cấu hình image bổ sung tool cần thiết một cách có chủ đích. Trong môi trường container, giới hạn process attach và permissions có thể ngăn chẩn đoán.

### 20.3. Log có cấu trúc hơn in stacktrace tràn lan

ShipCli demo dùng stdout/stderr. Trong ứng dụng thật:

- Log sự kiện có timestamp UTC, level, error code và correlation/run ID.
- Phân biệt lỗi người dùng (tham số sai) với lỗi hệ thống (disk full, permissions).
- Giới hạn dữ liệu nhạy cảm trong log.
- Định nghĩa nơi tập trung log và thời gian lưu trữ.
- Tránh log spam trong vòng lặp xử lý file hàng triệu dòng.

Đối với lỗi mở file, chỉ viết “I/O failure” thường chưa đủ; log có thể gồm path đã được redact theo policy và cause của exception ở kênh diagnostics dành cho operator.

## 21. Quản lý bản vá runtime và vòng đời Java 27

### 21.1. Runtime image cần được rebuild khi cập nhật JDK

Khi đóng gói runtime cùng ứng dụng, không chỉ update `JAVA_HOME` trên máy người dùng là đủ. Một bản runtime image cũ vẫn chứa binaries/libraries của JDK build cũ.

Quy trình khi có bản vá bảo mật:

1. Nâng JDK vendor/build mà CI dùng.
2. Rebuild modular JAR nếu phù hợp và tạo runtime image mới.
3. Tạo lại app image/installer trên từng target.
4. Chạy smoke/regression/security tests.
5. Tạo checksum/metadata mới và phát hành theo quy trình.
6. Xác minh người dùng hoặc hệ thống vận hành đã nhận image mới.

### 21.2. Java 27 không phải LTS

Khi chọn Java 27 cho production, cần tính trước mốc nâng lên phiên bản feature tiếp theo hoặc chính sách hỗ trợ phù hợp. Không khóa runtime image JDK 27 trong một package rồi mặc định nó sẽ được vá lâu dài giống bản LTS.

Mỗi release cần xác định **JDK build cụ thể** và ngày đánh giá cập nhật. Điều này càng quan trọng khi ứng dụng nhúng TLS/crypto/runtime libraries đi kèm JDK.

## 22. Reproducible builds và supply-chain security

### 22.1. Những yếu tố làm artifact khác giữa hai lần build

Dù source giống nhau, bytes của JAR/runtime image có thể khác do:

- Timestamp và entry metadata trong ZIP/JAR.
- Thứ tự các resource và dependency.
- Compiler flags và JDK vendor/build.
- OS/architecture của runtime image.
- Native packaging metadata, generated installer IDs.
- Nguồn dữ liệu download và các action/tool không pin.

Do đó, **hash khác không tự động chứng minh artifact bị thay mã nguồn**. Muốn reproducible build phải điều khiển đầu vào và metadata theo build tool tương ứng.

### 22.2. Pin dependencies và quyền CI

- Pin library versions và lock/checksum dependencies.
- Với GitHub Actions, pin commit SHA khi policy yêu cầu để tránh tag trôi.
- Dùng `permissions: contents: read` cho build/test thông thường.
- Tách quyền tạo release/publish khỏi PR builds.
- Không phát hành artifact từ fork PR bằng token có quyền ghi.
- Kiểm soát self-hosted runner không dùng lại workspace/secrets giữa code tin cậy và untrusted code.
- Đánh giá SBOM, provenance/attestation và signature theo môi trường triển khai.

### 22.3. Quyền ứng dụng tại máy đích

Không chạy ứng dụng với root/Administrator nếu không cần. Cho dữ liệu vào một data directory riêng, hạn chế quyền ghi vào app image, bảo vệ thư mục chứa binary và tránh cho attacker thay executable/library trước khi load.

## 23. Thiết kế phát hành theo từng giai đoạn

### 23.1. Chỉ build và upload

Bước đầu, chạy CI cho mỗi pull request và branch nhưng **chỉ tạo artifact thử nghiệm**. Chưa ký/publish ra public package repositories.

### 23.2. Release candidate

Khi tạo tag release candidate:

- Build từ commit/tag cố định.
- Kiểm tra đúng JDK vendor/version.
- Chạy integration tests theo target OS.
- Tính hash và phát hành bản kiểm thử cho staging/pilot group.
- Ghi nhận version/changelog/known issues.

### 23.3. Chính thức phát hành

Chỉ release sau approval/quality gates theo tổ chức. Phát hành đúng artifact đã kiểm tra, đừng rebuild âm thầm bằng toolchain khác ngay trước khi publish mà không test lại.

### 23.4. Sau phát hành

Theo dõi error rate, startup failures, reports, installer failures và số client cập nhật thành công. Khi phát hiện lỗi, có rollback procedure và khả năng giữ artifact cũ trong phạm vi chính sách bảo mật.

## 24. Bài tập mở rộng sau bản CLI đơn giản

Để nâng cấp dự án thực hành từ demo lên sản phẩm tích hợp:

1. **JUnit tests:** tách parser/formatter thành các class độc lập, thêm parameterized tests, property-based inputs và giới hạn file.
2. **Configuration:** config file có schema và validation, secrets lấy từ secret manager.
3. **Observability:** structured logging, metrics và correlation IDs.
4. **Persistence:** dùng JDBC DataSource và transaction ownership nếu cần DB, không giữ kết nối trong vòng xử lý dài vô hạn.
5. **REST API:** nếu cần HTTP, dùng một server framework hiện hành có module graph/dependency được đóng gói đúng.
6. **Scheduling:** chạy qua scheduler/service manager thay vì viết vòng lặp vô hạn trong CLI.
7. **Delivery:** build native installers và ký theo platform.
8. **SBOM:** tạo component inventory và scan CVEs trong CI.
9. **Upgrade:** chuyển dữ liệu và config theo versioned migration có rollback rules.
10. **Multi-architecture:** bổ sung ARM64 runners/build targets và kiểm tra binary dependencies.
11. **Performance:** đo startup/memory/cpu của custom image so với full JDK; không giả định image nhỏ sẽ chạy nhanh hơn mọi trường hợp.
12. **Reliability:** tạo test fault injection cho disk-full, permissions, unavailable dependency và termination signal.

## 25. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ phát JAR rồi yêu cầu người dùng tự tìm JDK | Lỗi version và support | Nêu rõ runtime requirement hoặc đóng gói image |
| Xem `jlink` là native compiler | Hiểu sai định dạng sản phẩm | `jlink` tạo custom Java runtime |
| Tưởng `jpackage` build Windows installer trên Linux | Không có cross-platform support | Build matrix theo OS |
| Dùng automatic modules không link được | `jlink` lỗi ở module graph | Kiểm tra explicit modules/packaging strategy |
| Chạy smoke test chỉ bằng `java -cp` | Bỏ sót lỗi launcher/image | Test `build/runtime/bin/...` và app image |
| Tưởng có `app-image` là đã có installer ký số | Thiếu cài đặt/signature/notarization | Tạo installer và kiểm tra signing riêng |
| Đưa mutable data vào app image | Update làm mất hoặc ghi đè dữ liệu | Tách data/config/log khỏi installation |
| Ghi secrets vào JAR/config tĩnh trong release | Rò bí mật khó thu hồi | Secret manager và quyền tối thiểu |
| Chọn `jdeps` output làm bảo đảm đủ module | Lỡ reflection/service provider | Integration tests và `jlink --bind-services` có kiểm soát |
| Không pin JDK build | Artifact/behavior khác nhau | Ghi exact vendor/build và kiểm tra release |
| Upload raw executable folder không bảo toàn mode | Linux/macOS launcher mất executable bit | Dùng tar/package giữ quyền hoặc installer |
| Chỉ kiểm tra file archive tồn tại | Artifact có thể không chạy | Test launcher và hash/checksum |
| Dùng checksum từ file không thuộc artifact cuối | Hash sai | Hash **sau** archive cuối cùng |
| Dùng floating CI action tags không đánh giá risk | Supply-chain drift | Pin immutable SHA theo security policy |
| CI có secrets trên untrusted PR | Lộ credentials | Separate release pipeline, permissions tối thiểu |
| Tạo runtime image một lần rồi không cập nhật | Không nhận security patch JDK | Rebuild khi JDK update |
| Chỉ thử Linux nhưng quảng cáo hỗ trợ 3 OS | Gói có thể lỗi ở nền tảng khác | Smoke/integration matrix đúng contract |
| Không có runbook rollback | Khó phục hồi khi release lỗi | Versioned installs, hướng dẫn rollback rõ |
| Dựa vào `--health` demo cho readiness DB | Báo khỏe giả | Thiết kế liveness/readiness/business checks riêng |
| Coi demo parser TSV là CSV parser đầy đủ | Đọc sai quoted fields/Unicode | Dùng parser/schema phù hợp nghiệp vụ |
| Không giới hạn quyền file/output | Có thể ghi đè tài nguyên ngoài ý muốn | Whitelist directories, filesystem permissions |
| Tự nhận Maven/Gradle/JUnit đã chạy | Báo cáo kiểm thử sai | Phân biệt lệnh mẫu, test thực và QA downstream |

## 26. Checklist trước khi bàn giao một release

- [ ] Module descriptor, main class và app version nhất quán?
- [ ] JDK 27 vendor/build ghi lại, không dùng JDK ngẫu nhiên?
- [ ] Build thành modular JAR, `jar --describe-module` hợp lệ?
- [ ] `jdeps` không báo dependency bất ngờ, module graph đầy đủ?
- [ ] Test hợp lệ/không hợp lệ/exit codes đều qua?
- [ ] Runtime `jlink` được tạo cho đúng OS/CPU?
- [ ] Runtime launcher đã chạy qua smoke test?
- [ ] App image `jpackage` được tạo đúng host?
- [ ] Launcher **trong app image** được chạy thử?
- [ ] Artifact giữ permissions cần thiết sau archive/upload/download?
- [ ] Hash được tính trên **artifact cuối** và lưu ở kênh tin cậy?
- [ ] Source commit, version, JDK build, CI run ID có trong release metadata?
- [ ] Signing/notarization/attestation phù hợp target?
- [ ] Third-party dependency licenses/SBOM/CVE checks hoàn tất?
- [ ] Không chứa password/token/secret trong image hoặc log?
- [ ] Config và data có vị trí tách khỏi installation?
- [ ] Runbook nêu đủ install, run, status, logs, errors, backup, update, rollback?
- [ ] Production không dùng `root`/Admin nếu không cần?
- [ ] Có kế hoạch vá runtime image khi JDK phát hành security update?
- [ ] Có release approval và rollback owner rõ ràng?
- [ ] Có kiểm thử sau cài đặt thực tế trên supported platforms?
- [ ] Có kết quả đo startup/footprint thay vì tuyên bố không có bằng chứng?

## 27. Câu hỏi tự kiểm tra

1. Modular JAR, custom runtime image và app image khác nhau như thế nào?
2. Vì sao dùng `jlink` không tạo ra executable native độc lập JVM?
3. `module-info.java` giúp ích gì cho phân phối ứng dụng?
4. Vì sao một automatic module có thể không phù hợp khi link bằng `jlink`?
5. Kết quả `jdeps --print-module-deps` có bảo đảm mọi runtime dependency được đóng gói không?
6. `--launcher ship-cli=com.example.ship/com.example.ship.Main` tạo điều gì?
7. Khi nào nên dùng `jpackage --runtime-image` thay vì để `jpackage` tự gọi `jlink`?
8. `jpackage --type app-image` khác `--type msi` hoặc `--type dmg` ra sao?
9. Vì sao cần matrix OS/architecture thay vì copy cùng runtime image sang các OS?
10. Vì sao CI phải chạy launcher đóng gói chứ không chỉ `java --module-path`?
11. Bản CLI demo `--health` xác minh điều gì và **không** xác minh điều gì?
12. `ATOMIC_MOVE` có bảo đảm hoạt động trên mọi filesystem không?
13. Nếu output directory không có quyền ghi, exit code nào được định nghĩa?
14. Vì sao nên tách config/data/log khỏi app image?
15. Tại sao upload raw folder trên CI có thể làm mất executable mode bits?
16. Vì sao SHA-256 checksum không thay chữ ký số?
17. Metadata release cần ghi những thông tin gì để tái hiện/rollback?
18. Java 27 là LTS hay feature release? Điều này ảnh hưởng lịch nâng cấp như thế nào?
19. Vì sao phải rebuild runtime image khi có security patch JDK?
20. CI khác CD ở đâu? Vì sao workflow cho PR không nên có quyền ký phát hành?
21. Nếu ứng dụng dùng reflection hoặc ServiceLoader, vì sao jdeps có thể bỏ sót module?
22. Có thể phát hành một installer Linux tạo từ Windows runner bằng jpackage không?
23. Khi ứng dụng chuyển từ Java-only sang JNI/FFM, cần bổ sung những kiểm tra gì?
24. Một runbook hỗ trợ xử lý incident cần những thông tin gì?
25. Khi rollback app, tại sao không mặc định dữ liệu/schema cũng rollback được?
26. Những chỉ số thực tế nào chứng minh custom runtime image mang lại lợi ích?

## 28. Nguồn tham khảo chính thức và hiện hành

- [Java SE 27 — jlink Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): `--module-path`, `--add-modules`, `--launcher`, `--compress=zip-6`, `--bind-services` và custom runtime images.
- [Java SE 27 — jpackage Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html): app image, host-specific installer, `--runtime-image`, `--module`, `--module-path` và launcher options.
- [Java SE 27 — jdeps Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): `--list-deps`, `--print-module-deps` và phân tích dependency.
- [Java SE 27 — javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, `-encoding` và compiler diagnostics.
- [Java SE 27 — jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html): modular JAR, `--main-class` và `--describe-module`.
- [Java SE 27 — java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--module-path`, `--module`, runtime options và module resolution.
- [Java SE 27 API — Module](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Module.html): runtime module identity và JPMS.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): UTF-8 I/O, temporary files, atomic moves và filesystem exceptions.
- [Java SE 27 API — Path](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): filesystem paths và normalization.
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): mốc phát hành, cập nhật và phân biệt LTS/feature release.
- [GitHub — actions/setup-java](https://github.com/actions/setup-java): JDK distribution/version management trên CI; ví dụ `actions/setup-java@v6`.
- [GitHub — actions/checkout](https://github.com/actions/checkout): lấy source vào workflow.
- [GitHub — actions/upload-artifact](https://github.com/actions/upload-artifact): lưu build outputs; ví dụ `actions/upload-artifact@v7`.
- [GitHub Docs — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): matrix, runner, permissions, shells và workflow conditions.
- [GitHub Docs — Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/use-artifact-attestations): provenance cho artifact xuất từ pipeline.
- [OpenSSF — SLSA](https://slsa.dev/): mô hình đánh giá độ tin cậy của quy trình build và provenance.

**Ranh giới bước viết Knowledge:** ví dụ trong bài là một thiết kế và bộ lệnh để người học đưa vào dự án thực hành. Chưa có file code, workflow CI hay installer thật nào được tạo bên ngoài hai đường dẫn bài Knowledge đã được giao; việc build, chạy tests, kiểm chứng installer và vòng QA chuyên môn tiếp theo thuộc các bước sau của quy trình module.
