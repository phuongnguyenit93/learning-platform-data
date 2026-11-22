# Tích hợp jdeprscan vào CI

`jdeprscan` là công cụ static analysis đi kèm JDK, dùng để quét bytecode trong thư mục class hoặc JAR và tìm các lần sử dụng API Java SE đã bị deprecated. Đưa công cụ này vào CI giúp phát hiện sớm những API có thể bị loại bỏ trong các bản JDK tương lai, kể cả khi source không được biên dịch lại thường xuyên, warning đã bị suppress hoặc ứng dụng phụ thuộc vào thư viện chỉ được phân phối dưới dạng binary.

Một pipeline hiệu quả thường kết hợp hai lớp kiểm tra:

- `javac -Xlint:deprecation -Xlint:removal` phát hiện việc sử dụng API deprecated trong source được biên dịch ở lần build hiện tại.
- `jdeprscan` kiểm tra bytecode đã tạo ra, bao gồm các class/JAR có thể không được biên dịch lại từ source trong pipeline đó.

## 1. Vì sao chạy jdeprscan trong CI?

Deprecation là tín hiệu yêu cầu người dùng chuyển sang API thay thế. API deprecated thông thường có thể vẫn tồn tại lâu dài; API được đánh dấu `forRemoval=true` đã đủ điều kiện để bị loại bỏ trong một bản phát hành tương lai.

Nếu ứng dụng tiếp tục tham chiếu API đó sau khi API bị xóa, chương trình có thể không liên kết hoặc chạy được trên JDK mới. Vì vậy, phát hiện trước khi nâng JDK giúp nhóm phát triển có thời gian thay thế API và kiểm thử.

`jdeprscan` đặc biệt hữu ích trong các trường hợp:

- Một số module hoặc thư viện nhị phân không được biên dịch lại ở mọi lần nâng JDK.
- Source đã dùng `@SuppressWarnings("deprecation")` hoặc `@SuppressWarnings("removal")`.
- Ứng dụng sử dụng JAR do nhóm khác cung cấp.
- Nhóm muốn kiểm tra artifact thực tế sẽ phát hành, thay vì chỉ xem source hiện tại.
- Nhóm đang chuẩn bị nâng từ một JDK sang bản mới hơn.

### 1.1. jdeprscan kiểm tra gì?

Công cụ đọc bytecode để tìm các tham chiếu tới API deprecated do Java SE định nghĩa. Nó có thể nhận các đầu vào:

- Thư mục chứa cây package/class.
- Tệp JAR.
- Tệp `.class`.
- Tên class fully qualified, ví dụ `java.lang.Thread`.
- Tên nested class dùng dấu `$`, ví dụ `java.lang.Thread$State`.

`jdeprscan` không quét source code và không báo các API deprecated do thư viện bên thứ ba tự định nghĩa. Nếu cần kiểm tra deprecated API của framework hoặc thư viện nội bộ, cần bổ sung compiler warning, công cụ phân tích hoặc quy tắc riêng của dự án.

## 2. Phân biệt compiler warnings và bytecode scan

Hai cơ chế bổ sung cho nhau:

| Cơ chế | Đầu vào | Phát hiện | Giới hạn |
|---|---|---|---|
| `javac -Xlint:deprecation` | Source được biên dịch trong lần build | API deprecated thông thường | Không kiểm tra các JAR nhị phân không được biên dịch lại |
| `javac -Xlint:removal` | Source được biên dịch trong lần build | API deprecated for removal | Chỉ áp dụng cho source đang được biên dịch |
| `jdeprscan` | Class file, thư mục class hoặc JAR | Tham chiếu bytecode tới API deprecated của Java SE | Không báo deprecated API riêng của thư viện bên thứ ba |

Có thể bật cả hai loại warning của compiler:

~~~bash
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
~~~

Trong JDK 21, warning `removal` được bật mặc định; ghi rõ tùy chọn giúp chính sách build dễ đọc và nhất quán. Nếu dự án đã sẵn sàng chặn mọi warning, có thể thêm `-Werror`:

~~~bash
javac -Xlint:deprecation -Xlint:removal -Werror -d out src/com/example/*.java
~~~

`-Werror` khiến compiler kết thúc với lỗi khi có warning. Chỉ bật sau khi nhóm đã xử lý hoặc thiết lập baseline cho warning hiện có.

Một số đoạn code được suppress vẫn tạo bytecode tham chiếu API deprecated. Đây là lý do nên chạy `jdeprscan` sau bước compile/package, ngay cả khi compiler không phát warning.

## 3. Chọn JDK và release để quét

Dùng `jdeprscan` thuộc JDK mà pipeline đã pin. Kiểm tra phiên bản và các release mà công cụ hỗ trợ:

~~~bash
jdeprscan --version
jdeprscan --help
~~~

Tùy chọn `--release` chọn bộ API Java SE được dùng để xác định deprecation. Ví dụ, khi đánh giá artifact cho Java SE 21:

~~~bash
jdeprscan --release 21 target/my-app.jar
~~~

Hãy chọn release theo mục tiêu kiểm tra:

- Kiểm tra ứng dụng đang chạy trên Java 21: dùng `--release 21`.
- Chuẩn bị nâng ứng dụng lên Java 21: quét với bộ API Java SE 21 để thấy các deprecation liên quan tới mục tiêu nâng cấp.
- Duy trì nhiều runtime target: chạy các lượt quét riêng cho từng release được JDK của pipeline hỗ trợ.

Danh sách release hợp lệ thay đổi theo phiên bản JDK. Xem `jdeprscan --help` của chính toolchain CI; không giả định mọi JDK hỗ trợ cùng một dải release.

## 4. Ưu tiên API deprecated for removal

Dùng `--for-removal` để chỉ báo các API đã được đánh dấu có thể bị loại bỏ trong tương lai:

~~~bash
jdeprscan --release 21 --for-removal target/my-app.jar
~~~

Đây là kiểm tra có mức ưu tiên cao cho CI vì những tham chiếu này có nguy cơ làm ứng dụng không tương thích với JDK tương lai. Tùy chọn này không kết hợp được với các release 6, 7 hoặc 8.

Có thể kết hợp hai lượt:

~~~bash
# Tất cả API Java SE deprecated
jdeprscan --release 21 target/my-app.jar

# Chỉ API deprecated for removal
jdeprscan --release 21 --for-removal target/my-app.jar
~~~

Lượt thứ nhất giúp nhóm theo dõi toàn bộ nợ deprecation. Lượt thứ hai có thể được dùng làm quality gate nghiêm ngặt hơn.

Để liệt kê các API deprecated của một release mà không quét artifact:

~~~bash
jdeprscan --release 21 --list
~~~

Chỉ liệt kê API deprecated for removal:

~~~bash
jdeprscan --release 21 --list --for-removal
~~~

Khi dùng `--list`, không truyền thêm JAR, thư mục hoặc class cần quét. `--list` chỉ in danh sách API; nó không thực hiện scan.

## 5. Đưa artifact và dependency vào lượt quét

Nên quét artifact sau khi build thành công:

~~~text
Checkout source
      |
      v
Set up pinned JDK
      |
      v
Compile + run tests
      |
      v
Package JAR / class directory
      |
      v
Run jdeprscan
      |
      v
Save report + apply CI policy
      |
      v
Publish artifact
~~~

Ví dụ quét JAR:

~~~bash
jdeprscan --release 21 target/my-app.jar
~~~

Hoặc quét thư mục class:

~~~bash
jdeprscan --release 21 target/classes
~~~

### 5.1. Cung cấp class path khi cần

`jdeprscan` cần phân giải được các class mà artifact đang quét phụ thuộc vào. Dùng `--class-path` để cung cấp thư mục hoặc JAR phụ thuộc:

~~~bash
jdeprscan \
  --release 21 \
  --class-path "target/classes:lib/a.jar:lib/b.jar" \
  target/my-app.jar
~~~

Trên Linux/macOS, các phần tử class path được ngăn cách bằng dấu `:`. Trên Windows, dùng dấu `;`:

~~~powershell
jdeprscan --release 21 --class-path "target\classes;lib\a.jar;lib\b.jar" target\my-app.jar
~~~

Nếu công cụ không tìm được class phụ thuộc, có thể xuất hiện thông báo dạng:

~~~text
error: cannot find class ...
~~~

Hãy bổ sung dependency còn thiếu vào class path rồi quét lại. Không bỏ qua lỗi này và xem lượt scan là thành công, vì kết quả khi thiếu dependency có thể không đầy đủ.

Lưu ý: `--class-path` giúp phân giải dependency khi phân tích; nó không có nghĩa `jdeprscan` tự quét nội dung của mọi JAR trong class path. Nếu muốn kiểm tra cả bytecode của một thư viện nhị phân, hãy truyền chính JAR đó như một đầu vào scan riêng.

## 6. Hiểu kết quả của jdeprscan

Ví dụ đầu ra:

~~~text
Jar file app.jar:
class DeprecatedApis uses deprecated method java/util/Date::getYear()I
class DeprecatedApis uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Cách đọc:

- `Jar file app.jar:` cho biết artifact đang được xử lý.
- `DeprecatedApis` là class có tham chiếu tới API deprecated.
- `java/util/Date::getYear()I` chỉ ra class và method được sử dụng.
- `java/lang/Thread::stop()V` là method `stop()` nhận không tham số và trả về `void`.
- `(forRemoval=true)` cho biết API được đánh dấu có thể bị loại bỏ.

Một số ký hiệu trong descriptor bytecode:

| Ký hiệu | Ý nghĩa |
|---|---|
| `I` | `int` |
| `J` | `long` |
| `D` | `double` |
| `V` | `void` |
| `L...;` | Kiểu tham chiếu |
| `<init>` | Constructor |

Có thể thêm `--verbose` để xem thông tin xử lý chi tiết hơn:

~~~bash
jdeprscan --verbose --release 21 target/my-app.jar
~~~

### 6.1. Exit code không thay thế việc đọc kết quả

Không nên mặc định rằng CLI sẽ trả exit code khác 0 chỉ vì tìm thấy deprecated API. Trong thử nghiệm với JDK 24.0.2, lượt scan tìm thấy `Date.getYear()` và `Thread.stop()` nhưng lệnh vẫn kết thúc với exit code 0.

Vì vậy, CI cần có chính sách riêng:

- Chạy tool và lưu stdout/stderr thành report.
- Coi lỗi tool hoặc lỗi phân giải dependency là build failure.
- Kiểm tra report để phát hiện dòng `uses deprecated`.
- Chọn cách xử lý finding: chặn ngay, so sánh với baseline hoặc chỉ cảnh báo trong giai đoạn đầu.

CLI không có tùy chọn `--fail-on-warning` tương đương compiler. Nếu cần hard gate, wrapper của pipeline phải chuyển finding thành trạng thái thất bại.

## 7. Ví dụ Java hoàn chỉnh để thử trong CI

Ví dụ này cố ý tham chiếu một API deprecated thông thường và một API deprecated for removal. Các method chứa tham chiếu chỉ được compile và scan; chương trình không gọi chúng khi chạy.

Tệp `src/DeprecatedApiFixture.java`:

~~~java
import java.util.Date;

public final class DeprecatedApiFixture {
    public static void main(String[] args) {
        System.out.println("Deprecation scan fixture ready");
    }

    static int ordinaryDeprecatedApi() {
        return new Date().getYear();
    }

    static void deprecatedForRemoval(Thread thread) {
        thread.stop();
    }
}
~~~

Biên dịch và đóng gói:

~~~bash
mkdir -p out

javac -Xlint:deprecation -Xlint:removal -d out \
  src/DeprecatedApiFixture.java

jar --create --file app.jar -C out .
~~~

Chạy chương trình:

~~~bash
java -cp app.jar DeprecatedApiFixture
~~~

Stdout chính xác:

~~~text
Deprecation scan fixture ready
~~~

Quét toàn bộ API deprecated:

~~~bash
jdeprscan --release 21 app.jar
~~~

Đầu ra chứa các tham chiếu tương ứng với `Date.getYear()` và `Thread.stop()`. Khi chỉ quét API for removal:

~~~bash
jdeprscan --release 21 --for-removal app.jar
~~~

Đầu ra chỉ còn tham chiếu tới `Thread.stop()`:

~~~text
Jar file app.jar:
class DeprecatedApiFixture uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Đây là fixture kiểm thử hành vi của pipeline. Trong ứng dụng thật, hãy thay API deprecated bằng API được khuyến nghị và không gọi các method nguy hiểm trong fixture.

## 8. Ví dụ hard gate trong GitHub Actions

Ví dụ dưới đây giả định Maven tạo artifact `target/my-app.jar`, runner là Ubuntu và project chưa có baseline deprecation. Thay tên JAR theo artifact thực tế của dự án.

~~~yaml
name: Java deprecation scan

on:
  pull_request:
  push:
    branches: [main]

jobs:
  build-and-scan:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven

      - name: Build and test
        run: ./mvnw -B verify

      - name: Scan deprecated Java SE APIs
        shell: bash
        run: |
          set -euo pipefail

          JAR="target/my-app.jar"
          REPORT="target/reports/jdeprscan.txt"

          mkdir -p target/reports

          if ! jdeprscan --release 21 "$JAR" > "$REPORT" 2>&1; then
            cat "$REPORT"
            echo "jdeprscan could not complete"
            exit 2
          fi

          cat "$REPORT"

          if grep -Eq ' uses deprecated |^error:' "$REPORT"; then
            echo "Deprecated Java SE API usage found"
            exit 1
          fi
~~~

Các phần chính:

- `setup-java` cố định JDK 21 để build và scan dùng cùng toolchain.
- `mvnw verify` tạo artifact sau khi chạy test.
- Report được lưu ở `target/reports/jdeprscan.txt` để có thể upload thành CI artifact.
- Lỗi thực thi tool hoặc dependency resolution làm job thất bại.
- `grep` biến dòng finding thành hard failure vì scanner có thể trả exit code 0 dù đã tìm thấy API deprecated.

Mẫu trên là Bash cho runner Linux. Với Windows runner, dùng PowerShell hoặc script riêng; không dùng dấu phân cách class path kiểu Unix.

### 8.1. Thêm class path cho dependency

Nếu artifact cần dependency để phân giải class, thêm danh sách JAR đã được build system resolve:

~~~bash
jdeprscan \
  --release 21 \
  --class-path "target/classes:lib/a.jar:lib/b.jar" \
  target/my-app.jar
~~~

Đối với Maven hoặc Gradle, hãy tạo class path từ cấu hình dependency của build, tránh duy trì một danh sách JAR thủ công có thể lệch với runtime.

### 8.2. Quét nhiều artifact trong multi-module build

Mỗi module phát hành một JAR riêng có thể được scan riêng:

~~~bash
jdeprscan --release 21 module-a/target/module-a.jar
jdeprscan --release 21 module-b/target/module-b.jar
jdeprscan --release 21 module-c/target/module-c.jar
~~~

Lưu report riêng theo module hoặc gộp output trước khi áp dụng policy. Việc một module đã được scan không có nghĩa các JAR của module khác hoặc third-party dependency đã được scan.

## 9. Quản lý baseline để không chặn toàn bộ nhóm ngay lập tức

Một codebase lâu năm có thể đã có nhiều deprecation finding. Chặn toàn bộ ngay từ lần đầu có thể khiến CI không thể áp dụng thực tế.

Có thể triển khai theo giai đoạn:

1. Chạy scan và lưu report làm baseline ban đầu.
2. Review các finding, phân loại theo module và mức độ ưu tiên.
3. Chặn mọi finding mới so với baseline.
4. Tạo ticket và thời hạn xử lý cho finding cũ.
5. Xóa dòng baseline khi API đã được thay thế.
6. Tăng mức kiểm soát, ví dụ không cho phép bất kỳ API nào `forRemoval=true`.

Baseline nên được version control cùng source và gắn với release/JDK target. Khi nâng `--release` hoặc thay JDK scan, tạo baseline mới có review vì tập API deprecated có thể thay đổi.

Không nên chỉ so sánh tổng số warning. Một finding cũ có thể biến mất trong khi một finding nguy hiểm mới xuất hiện; nên so sánh từng dòng đã chuẩn hóa theo class và API được gọi.

## 10. Tích hợp với Maven và Gradle

### 10.1. Maven

Cách đơn giản nhất là thêm bước gọi `jdeprscan` sau khi `mvn verify` tạo JAR:

~~~bash
./mvnw -B verify
jdeprscan --release 21 target/my-app.jar
~~~

Apache có Maven JDeprScan Plugin với goal `jdeprscan:jdeprscan` để quét main classes và goal `jdeprscan:test-jdeprscan` để quét test classes. Plugin có tham số `failOnWarning`, `release` và `forRemoval`; tài liệu plugin ghi `failOnWarning` mặc định là `true`.

Lưu ý plugin được Apache đánh dấu là alpha release. Kiểm tra mức độ ổn định, phiên bản và compatibility của plugin trước khi dùng làm cổng phát hành chính thức. Nếu không muốn thêm plugin alpha vào build, gọi executable JDK trong CI là cách trực tiếp hơn.

### 10.2. Gradle

Sau khi tạo JAR:

~~~bash
./gradlew clean test jar
jdeprscan --release 21 build/libs/my-app-1.0.jar
~~~

Tên JAR phụ thuộc `rootProject.name`, version và cấu hình archive của dự án. Trong pipeline thật, lấy đường dẫn từ output task `jar` thay vì hard-code tên artifact nếu dự án thường xuyên đổi version.

Có thể đặt lệnh scan trong script dùng chung của repository rồi gọi script đó từ GitHub Actions, Jenkins, GitLab CI hoặc Azure Pipelines.

## 11. Chính sách CI nên áp dụng

Một chính sách cân bằng có thể chia thành hai mức:

| Mức | Kiểm tra | Hành vi CI |
|---|---|---|
| Bắt buộc | Không có lỗi scan, không thiếu dependency, không có finding mới | Build phải pass |
| Ưu tiên cao | Không có API `forRemoval=true` | Chặn release hoặc yêu cầu review ngoại lệ |
| Theo dõi | Các API deprecated thông thường còn trong baseline | Lưu report và theo dõi kế hoạch thay thế |
| Mở rộng | Deprecated API của thư viện bên thứ ba | Dùng compiler warning hoặc công cụ kiểm tra dependency riêng |

Không cần coi mọi API deprecated là sự cố production ngay lập tức. Tuy nhiên, API `forRemoval=true` cần được xử lý sớm hơn vì nó có thể biến thành lỗi tương thích khi nâng JDK.

## 12. Lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Scan không tìm thấy class | Class path thiếu dependency | Thêm toàn bộ dependency cần thiết vào `--class-path` |
| CI báo pass dù report có deprecated API | Chỉ kiểm tra exit code của `jdeprscan` | Parse report hoặc dùng plugin có `failOnWarning` |
| Scan local và CI cho kết quả khác | Dùng JDK/release khác nhau | Pin JDK và đặt `--release` rõ ràng |
| Không thấy API deprecated của thư viện ngoài | `jdeprscan` chỉ nhận diện API deprecated do Java SE định nghĩa | Bổ sung compiler warning hoặc công cụ phù hợp cho thư viện |
| Không thấy API trong source | Source chưa được compile hoặc artifact scan không phải artifact mới nhất | Đảm bảo build thành công và scan đúng JAR |
| Scan ứng dụng nhưng không thấy vấn đề trong dependency JAR | Class path chỉ giúp resolve type, không tự quét mọi JAR phụ thuộc | Truyền từng JAR cần kiểm tra như đầu vào scan riêng |
| `--for-removal` không chạy với một release cũ | Release 6, 7 hoặc 8 không tương thích tùy chọn này | Chọn release được hỗ trợ và kiểm tra `jdeprscan --help` |
| Finding cũ làm CI thất bại quá nhiều | Chưa có baseline hoặc policy chuyển đổi | Lưu baseline có review, chặn finding mới trước |
| Report trống nhưng artifact chưa được tạo đúng | Quét nhầm đường dẫn hoặc nhầm module | Kiểm tra artifact path, module list và build output |

## 13. Checklist trước khi bật CI gate

- [ ] Toolchain JDK được pin rõ ràng.
- [ ] Build và test chạy trước bước scan.
- [ ] `jdeprscan` nhận đúng JAR hoặc class directory mới nhất.
- [ ] `--release` khớp mục tiêu runtime/migration.
- [ ] `--class-path` có đủ dependency cần phân giải.
- [ ] Lỗi `cannot find class` được coi là lỗi scan.
- [ ] Report được lưu để nhóm có thể review.
- [ ] CI có chính sách xử lý finding, không chỉ dựa vào exit code.
- [ ] API `forRemoval=true` có mức ưu tiên xử lý cao.
- [ ] Các JAR cần kiểm tra trong multi-module build đều được đưa vào scan.
- [ ] Third-party deprecation được xử lý bằng cơ chế kiểm tra phù hợp.
- [ ] Baseline được review và cập nhật khi nâng JDK target.

## 14. Ghi nhớ

`jdeprscan` là bước kiểm tra bytecode nên đặt sau compile/package trong CI. Nó phát hiện tham chiếu tới API deprecated do Java SE định nghĩa, đặc biệt hữu ích cho binary dependency, code có warning bị suppress và kế hoạch nâng JDK.

Dùng `--release` để chọn bộ API cần kiểm tra, `--for-removal` để tập trung vào API có thể bị loại bỏ, và `--class-path` để phân giải dependency. Kết hợp với `javac -Xlint:deprecation -Xlint:removal`, lưu report và định nghĩa rõ policy để biến finding thành cảnh báo hoặc build failure. Khi cần chặn lỗi mới mà vẫn duy trì được codebase cũ, hãy quản lý baseline theo từng API thay vì chỉ đếm tổng warning.

Tài liệu tham khảo:

- [The jdeprscan Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html)
- [Java SE 21 Core Libraries Developer Guide — Enhanced Deprecation and Running jdeprscan](https://docs.oracle.com/en/java/javase/21/core/java-core-libraries-developer-guide.pdf)
- [Oracle JDK 21 Migration Guide — Removed APIs and deprecated-for-removal checks](https://docs.oracle.com/en/java/javase/21/migrate/jdk-migration-guide.pdf)
- [Apache Maven JDeprScan Plugin — Goals and configuration](https://maven.apache.org/plugins/maven-jdeprscan-plugin/)