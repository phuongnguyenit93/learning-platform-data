# Quét phụ thuộc vào API Java SE đã deprecated bằng jdeprscan (Java 9+)

## 1. Vì sao cần jdeprscan khi nâng phiên bản Java?

Một ứng dụng có thể đã biên dịch thành nhiều file `.class` hoặc JAR từ lâu. Khi chuyển lên JDK mới, các file bytecode đó có thể vẫn gọi một API Java SE được đánh dấu `@Deprecated`, thậm chí `@Deprecated(forRemoval=true)`. Nếu chỉ chạy `javac` cho source vừa thay đổi, đội phát triển có thể không thấy cảnh báo đến từ dependency JAR không được biên dịch lại.

**`jdeprscan`** là công cụ phân tích tĩnh của JDK, có từ Java 9 và **vẫn được cung cấp trong các JDK hiện đại**. Nó kiểm tra class/JAR đã biên dịch và báo **tham chiếu đến API Java SE đang deprecated** theo bộ thông tin của phiên bản Java SE được chọn. Nó rất hữu ích khi chuẩn bị nâng JDK, kiểm toán thư viện binary hoặc tìm điểm cần thay thế bằng API được hỗ trợ.

Ba điều phải hiểu trước khi dùng:

1. Công cụ phân tích **bytecode hiện có**, không tự chạy ứng dụng, không phải compiler và không sửa source.
2. Nó tập trung **deprecated API của Java SE**, không phải tất cả các API trong thư viện Maven/Gradle của bên thứ ba, không phải công cụ quét lỗ hổng bảo mật.
3. **Scan sạch không bảo đảm chạy được trên JDK đích**: dependency có thể đã bị xóa, dùng reflection, module không tương thích hoặc hành vi runtime thay đổi. Cần kiểm tra tài liệu migration, build và tests bổ sung.

Mặc dù đề bài thuộc kiến thức Java 9, cách dùng `jdeprscan` hiện nay là một bước **thường xuyên trong quy trình tiến hóa Java API**, không phải công cụ lịch sử đã bị bỏ.

## 2. Phân biệt deprecated API, for-removal và API đã bị xóa

| Trạng thái | Điều đó có nghĩa gì? | Cách xử lý |
| --- | --- | --- |
| API không deprecated | API không bị đánh dấu deprecated trong release đang xem | Vẫn kiểm tra compatibility khi thay JDK |
| `@Deprecated` | API không còn được khuyến nghị dùng mới; có thể có giải pháp thay thế | Đánh giá thay thế và test hành vi |
| `@Deprecated(forRemoval=true)` | Chủ sở hữu API thông báo dự kiến có thể xóa trong release tương lai | Ưu tiên xử lý khi lập kế hoạch nâng JDK |
| API **đã bị xóa** khỏi JDK đích | Bytecode/source sử dụng API đó có thể gây lỗi linkage hoặc compilation | Đọc removed-APIs/migration guide của phiên bản đích, sửa code và test |
| API nội bộ JDK không được hỗ trợ | Có thể bị encapsulate hoặc thay đổi ngoài phạm vi chuẩn Java SE | Dùng `jdeps --jdk-internals` và chuyển sang API được hỗ trợ |

`forRemoval=true` **không tự ấn định một phiên bản xóa cụ thể**. Việc một API bị deprecated ở JDK A cũng không chứng minh nó vẫn có mặt ở JDK B. Đặc biệt, khi API **đã bị xóa**, nó không còn xuất hiện như API đang deprecated trong release B. Vì vậy, ngoài scan deprecations, cần xem **migration guide** và chạy compatibility test trên JDK đích.

Chỉ dùng **API hiện hành** cho mã mới. Trong bài này có một lời gọi deprecated `java.util.Date.getYear()` **duy nhất để tạo dữ liệu thử cho scanner**; đây không phải phương pháp lập trình được khuyến nghị. Mã thay thế bằng `java.time` được trình bày cùng ví dụ.

## 3. Sự khác nhau giữa jdeprscan, javac và jdeps

| Công cụ | Phân tích gì? | Tình huống thích hợp |
| --- | --- | --- |
| `javac -Xlint:deprecation` | Lời gọi deprecated khi đang biên dịch source | Phát hiện ở mã đang sửa và compile; warning có thể bị suppress |
| **`jdeprscan`** | Tham chiếu **Java SE deprecated API** trong file `.class`/JAR đã biên dịch | Quét build artifact, thư viện binary, chuẩn bị nâng JDK |
| `jdeps` | Phụ thuộc class/package/module; tùy chọn `--jdk-internals` kiểm tra JDK internal APIs | Phân tích module graph, phụ thuộc JDK nội bộ, hỗ trợ migrate JPMS |
| Dependency tree/SBOM scanner | Thư viện và version ở cấp build artifact, CVE theo dữ liệu advisory | Lập inventory dependency và theo dõi lỗ hổng |

Ví dụ, nếu code có `@SuppressWarnings("deprecation")`, compiler không cảnh báo ở vị trí đó. Nhưng class file vẫn chứa tham chiếu đến method deprecated, nên `jdeprscan` **có thể phát hiện**. Ngược lại, nếu thư viện ngoài Java SE đánh dấu method của chính nó bằng `@Deprecated`, scanner JDK **không có nhiệm vụ báo mọi deprecation đó**.

`jdeprscan` cũng không đọc mọi chuỗi gọi động qua reflection hoặc tên class được sinh lúc runtime; đây là lý do cần thực thi integration tests, nhất là khi framework có class loading tùy chỉnh.

## 4. Cú pháp và các tùy chọn hiện hành

Cú pháp chuẩn của lệnh:

```text
jdeprscan [options] {dir|jar|class} ...
```

`dir` là thư mục chứa cây package với file `.class`; `jar` là file JAR; `class` có thể là class file hoặc tên class fully-qualified có thể phân giải được. Lệnh chạy từ terminal với JDK **đã cài công cụ `jdeprscan`**, không chỉ JRE tối giản. Trên Windows/Linux/macOS, nếu có nhiều JDK, kiểm tra JDK nào đang đứng đầu `PATH`.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--help` hoặc `-h` | In cú pháp và danh sách `--release` mà **scanner đang chạy** hỗ trợ |
| `--version` / `--full-version` | In phiên bản scanner; ghi vào báo cáo |
| `--release N` | Chọn **tập deprecated Java SE API của release N** để so sánh với bytecode |
| `--for-removal` | Chỉ báo deprecations được đánh dấu sẽ có thể bị loại bỏ |
| `--class-path PATH` | Cung cấp đường dẫn để phân giải các class phụ thuộc khi scan |
| `--list` hoặc `-l` | In danh sách deprecated APIs của release; **không quét class**, nên không thêm `dir`/JAR |
| `--verbose` / `-v` | Thêm thông tin quá trình xử lý để chẩn đoán |

Các lệnh cơ bản:

```bash
jdeprscan --help
jdeprscan --version
jdeprscan --release 24 out
jdeprscan --release 24 --for-removal out
jdeprscan --release 24 --list
jdeprscan --release 24 --for-removal --list
```

Số `24` được dùng vì **ví dụ đã kiểm thử trên JDK 24**. Nó **không phải mức release duy nhất**. Nếu muốn đánh giá JDK 26, hãy dùng một phiên bản `jdeprscan` có hỗ trợ `--release 26`, xác nhận qua `--help`; không gọi lệnh đó bằng JDK 24 rồi giả định nó phải chấp nhận. Tập API deprecated thay đổi theo release.

**Lưu ý:** `jdeprscan --release 24` không biên dịch lại Java 24 và không mô phỏng runtime Java 24. Nó chỉ chọn **mốc deprecation**. `javac --release 17`, trái lại, đặt target ngôn ngữ/API/bytecode khi compile source bằng một javac phù hợp.

## 5. Ví dụ Java 17+ độc lập có một lời gọi deprecated để quét

Tạo thư mục `jdeprscan-demo`, file `DeprecationScanDemo.java`. Đoạn code này **cố ý** chứa method deprecated để tạo kết quả có thể kiểm chứng. Các dự án mới không nên copy method `oldYear`.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.util.Date;

/**
 * Chỉ minh họa bytecode cần quét; đừng dùng getYear trong mã mới.
 */
public final class DeprecationScanDemo {
    @SuppressWarnings("deprecation")
    static int oldYear(Date date) {
        return date.getYear() + 1900;
    }

    static int modernYear(Date date) {
        return date.toInstant().atZone(ZoneId.systemDefault()).getYear();
    }

    public static void main(String[] args) {
        Date sample = Date.from(Instant.parse("2024-07-01T12:00:00Z"));
        System.out.println("Old year: " + oldYear(sample));
        System.out.println("Modern year: " + modernYear(sample));
    }
}
```

Giải thích:

- `Date.getYear()` là API deprecated (kết quả cũ bằng `năm - 1900` theo timezone mặc định). Lời gọi này là **fixture kiểm thử công cụ**.
- `@SuppressWarnings("deprecation")` ẩn cảnh báo compiler ở method, **không xóa lời gọi trong bytecode**. Scanner vẫn tìm thấy tham chiếu.
- `modernYear` là hướng thay thế hiện hành: lấy `Instant`, áp dụng một `ZoneId`, rồi lấy năm bằng `java.time`. Trong ứng dụng thật, nên xác định timezone theo quy tắc nghiệp vụ thay vì luôn dùng timezone của máy.
- Mốc giữa năm 2024 được chọn để output dễ kiểm chứng với các timezone phổ biến và hợp lệ; dữ liệu sát thời khắc chuyển năm cần kiểm tra timezone rõ ràng.

### 5.1. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 -d out DeprecationScanDemo.java
java -cp out DeprecationScanDemo
```

Stdout đã kiểm thử:

```text
Old year: 2024
Modern year: 2024
```

### 5.2. Quét directory chứa class

```bash
jdeprscan --release 24 out
```

Output đã kiểm thử trên JDK 24:

```text
Directory out:
class DeprecationScanDemo uses deprecated method java/util/Date::getYear()I
```

Lời giải thích output: `DeprecationScanDemo` là **class chứa tham chiếu**; `java/util/Date::getYear()I` là tên/số hiệu method theo **JVM descriptor**, trong đó `I` là kiểu trả về `int`. Output cơ bản không phải source file và line number. Nếu cần tìm vị trí, xem source hoặc dùng `javap -c` để đọc disassembly của class.

### 5.3. Chỉ quét API deprecated for removal

```bash
jdeprscan --release 24 --for-removal out
```

Với đúng fixture trên, output:

```text
Directory out:
```

Không có dòng `uses deprecated` vì `Date.getYear()` ở release kiểm thử **không được đánh dấu `forRemoval=true`**. Kết quả này chỉ phản ánh mốc Java 24, không nói rằng method chắc chắn tồn tại mãi mãi.

**Một chi tiết quan trọng cho CI:** cả lệnh scan có phát hiện `getYear` lẫn lệnh chỉ lọc for-removal **đều trả exit code 0** trong kiểm thử. Vì vậy, exit status thành công có thể chỉ có nghĩa **scanner thực thi được**. Nếu chính sách CI muốn chặn deprecation, phải xem **kết quả phát hiện**, không chỉ `$?` hoặc `$LASTEXITCODE`.

### 5.4. Quét JAR và file class

```bash
jar --create --file demo.jar -C out .
jdeprscan --release 24 demo.jar
jdeprscan --release 24 out/DeprecationScanDemo.class
```

Output cho JAR được thử nghiệm:

```text
Jar file demo.jar:
class DeprecationScanDemo uses deprecated method java/util/Date::getYear()I
```

Còn quét file class:

```text
class DeprecationScanDemo uses deprecated method java/util/Date::getYear()I
```

Mọi lệnh ở mục 5 đã được chạy thử bằng **JDK 24** với source biên dịch bởi `javac --release 17`. Vì đây là phân tích **bytecode**, việc scan không phụ thuộc việc chương trình có gọi `oldYear` trong một test runtime hay không: chỉ cần tham chiếu hiện diện trong class file mà scanner quét.

## 6. Áp dụng trên project Maven, Gradle và JAR bên thứ ba

### 6.1. Quét mã ứng dụng

Với thư mục build điển hình:

```bash
# Maven, sau khi compile:
jdeprscan --release 24 target/classes

# Gradle Java plugin, sau khi classes:
jdeprscan --release 24 build/classes/java/main
```

Đường dẫn trên là **ví dụ phổ biến**, không phải quy định mọi project đều dùng đúng layout đó. Với multi-module project hoặc source sets khác nhau, quét tất cả phần bytecode dự kiến phân phối. Luôn build lại trước khi scan để tránh báo kết quả từ `.class` cũ đã bị bỏ trong source.

### 6.2. Quét artifact JAR cuối cùng

```bash
jdeprscan --release 24 target/my-app.jar
jdeprscan --release 24 --for-removal lib/vendor-driver.jar
```

Hai file JAR là tên minh họa; thay bằng **đúng đường dẫn artifact thực tế**. Nếu dùng thin JAR, dependency thường ở những file JAR riêng. Scan ứng dụng **không tự quét toàn bộ JAR có trên classpath như các scan targets**. Cần xác định tập thư viện runtime từ dependency tree/lockfile/packaging rồi scan từng JAR (hoặc artifact đóng gói chứa chúng).

Một JAR bên thứ ba có thể có lời gọi Java SE deprecated dù ứng dụng của bạn không gọi trực tiếp. Không nên âm thầm sửa binary; thường cần nâng phiên bản thư viện từ vendor, kiểm tra support matrix và chạy integration tests sau khi nâng.

### 6.3. Phân giải dependency với `--class-path`

Khi scanner không tìm thấy class phụ thuộc của artifact, cung cấp classpath tương ứng với runtime:

```bash
# Linux/macOS: dấu hai chấm để phân cách các entry
jdeprscan --release 24 --class-path "lib/a.jar:lib/b.jar" target/my-app.jar
```

```powershell
# Windows: dấu chấm phẩy để phân cách các entry
jdeprscan --release 24 --class-path "lib/a.jar;lib/b.jar" target/my-app.jar
```

`--class-path` dùng để **phân giải** class mà bytecode đang tham chiếu; nó không biến mọi dependency ở đó thành target riêng để báo. Muốn quét `lib/a.jar`, hãy đưa JAR ấy vào đối số quét. Nếu xuất hiện `error: cannot find class ...`, kết quả chưa đầy đủ; bổ sung dependency và chạy lại.

Với module path, multi-release JAR hoặc class loader tùy biến, cần xét đúng cấu trúc runtime/artifact và khả năng của **phiên bản scanner đang sử dụng**. Công cụ không thể mô phỏng mọi hành vi tải class động của ứng dụng.

## 7. `--release` là mốc so sánh, không phải bảo đảm tương thích

Giả sử đội vận hành định nâng từ JDK 17 lên JDK mới:

1. Xác định **release đích**, JDK dùng để scan và phiên bản artifact cần kiểm tra.
2. Lấy scanner có hỗ trợ `--release <đích>`, xem `jdeprscan --help`.
3. Quét directory/JAR của ứng dụng **cùng dependency runtime**.
4. Chạy cả scan toàn bộ và scan `--for-removal`.
5. Dựa vào tài liệu chuẩn để thay API; thử lại trên JDK đích.
6. Kiểm tra riêng **removed APIs** trong migration guide; scanner deprecation không cung cấp danh sách đủ các API đã mất.

Lý do bước 6 quan trọng: nếu một method từng được báo deprecated ở JDK 17 nhưng **đã bị xóa ở JDK đích**, nó có thể không còn thuộc danh sách deprecated đang hiện diện ở release đích. Scan sạch với mốc mới không khẳng định binary có thể liên kết với method đã biến mất. Khi cần, đối chiếu bản phát hành ngay **trước khi bị xóa** và thử compile/run với JDK mục tiêu.

### Thay thế một API có thể làm đổi hành vi

Với fixture `Date.getYear()`:

**Đoạn cũ chỉ để nhận diện deprecation:**

```java
@SuppressWarnings("deprecation")
int year = date.getYear() + 1900;
```

**Đoạn dùng API hiện hành:**

```java
int year = date.toInstant()
        .atZone(ZoneId.systemDefault())
        .getYear();
```

Hai đoạn là **mảnh mã minh họa** cần biến `Date date` và các import tương ứng. Nếu business logic xử lý lịch địa phương ở timezone cụ thể, dùng `ZoneId.of("...")` mà hệ thống quy định; nếu xử lý timestamp, dùng `Instant` và chỉ chuyển sang local date khi cần. Bài học quan trọng: **thay deprecated API phải giữ đúng ngữ nghĩa và test dữ liệu biên**, không đổi tên phương thức theo kiểu cơ học.

## 8. Đọc output và xử lý lỗi quét

| Triệu chứng | Ý nghĩa thường gặp | Hành động |
| --- | --- | --- |
| `class X uses deprecated method Y` | Class X tham chiếu Java SE method deprecated Y | Xem source, docs mới, đánh giá thay thế |
| Có findings ở scan thường nhưng trống với `--for-removal` | API deprecated nhưng chưa được đánh dấu for-removal ở release đang dùng | Lập kế hoạch sửa, theo dõi release đích |
| `error: cannot find class ...` | Thiếu class để scanner phân giải | Thêm `--class-path`/module dependency phù hợp, scan lại |
| Scanner không nhận `--release N` | JDK đang dùng không hỗ trợ release N | Chạy scanner từ JDK mới hơn, xem `--help` |
| Có findings nhưng exit code = 0 | Lệnh thực thi thành công dù phát hiện deprecated API | CI phải phân tích report, không chỉ exit code |
| JAR scan sạch nhưng dependency khác vẫn lỗi | Chưa scan hết artifact runtime hoặc lỗi không thuộc phạm vi deprecation | Scan đúng dependency set và chạy integration tests |
| Method được gọi qua reflection không được báo | Phụ thuộc động không thể xác định đầy đủ bằng bytecode tĩnh | Review cấu hình/reflection và kiểm thử |
| Không tìm thấy deprecated method của thư viện thứ ba | Công cụ tập trung Java SE deprecated API | Dùng compiler/linter/tài liệu vendor cho thư viện đó |
| Method từng deprecated đã bị xóa | API không còn là phần tử deprecated đang tồn tại ở release mới | Đọc migration guide, tìm API đã bị loại, compile/run thử |

Đừng nhầm `--list` với “list những phương thức ứng dụng đang dùng”: `--list` in danh sách **Java SE APIs được đánh dấu deprecated trong release**, không scan target. Để tìm class/JAR thật sự dùng API nào, bỏ `--list` và truyền đúng target.

## 9. Đưa vào CI có kiểm soát

Một quy trình CI hữu ích là **ghi lại deprecation findings** cùng thông tin môi trường; tùy rủi ro mà chặn:

- **Giai đoạn quan sát:** lưu báo cáo sau mỗi build, lập baseline. Không tự fail mọi deprecated API khi project lớn chưa có kế hoạch migrate.
- **Giai đoạn ưu tiên:** fail khi phát sinh finding **for-removal** mới, hoặc khi nâng JDK làm thay đổi mức rủi ro.
- **Giai đoạn cải thiện:** loại dần baseline cũ; nâng thư viện vendor và bảo đảm build/test xanh trên JDK đích.

Một script Bash **minh họa** cho policy “không có bất kỳ `uses deprecated` nào” (chạy khi `out` tồn tại, scanner hỗ trợ mốc 24):

```bash
set -euo pipefail
jdeprscan --release 24 out > jdeprscan-report.txt 2>&1

# Chỉ ví dụ policy đọc dạng output của scanner đã kiểm thử.
if grep -q "uses deprecated" jdeprscan-report.txt; then
  echo "Phát hiện Java SE deprecated API"
  cat jdeprscan-report.txt
  exit 1
fi
echo "Không có dòng deprecated API được scanner báo"
```

Script này không thay thế parser đáng tin cho toàn bộ khả năng scanner ở các JDK khác nhau. Khi đưa vào CI:

1. Kiểm thử parser với bản `jdeprscan` **đã khóa phiên bản**; format message có thể thay đổi.
2. Ghi **stdout/stderr**, exit status, `--release`, `--for-removal` và version tool trong log/artifact.
3. **Không bỏ qua lỗi phân giải**. Nếu scanner báo `cannot find class` hoặc exception, phải xử lý là scan không đầy đủ, không coi là “không có findings”.
4. Phân biệt kết quả từ **mã do nhóm sở hữu** và từ **JAR vendor**; ưu tiên nâng thư viện do vendor hỗ trợ.
5. Đừng thay integration tests bằng scan: chạy test trên JDK đích, chú ý module exports, reflection, class loader, native dependencies.
6. Không dùng `System.exit(0)` hay cách suppress log để biến finding thành “PASS”; nếu chấp nhận exception, cần owner và lý do.

Trong PowerShell, `$LASTEXITCODE` cho biết tiến trình đã kết thúc với mã gì; như thử nghiệm trên, mã 0 khi có finding không đồng nghĩa project không dùng API deprecated. Với policy CI cụ thể, nên dùng script có test để đọc dòng phát hiện thay vì giả định exit code.

## 10. Quy trình review sau khi có finding

Một báo cáo nên lưu ít nhất:

| Trường | Nội dung |
| --- | --- |
| `Scanner JDK` | Ví dụ JDK 24 và output `jdeprscan --version` |
| `Target release` | Java SE release được chọn qua `--release` |
| `Artifact` | Thư mục/JAR được quét, hash/phiên bản build nếu cần |
| `Classpath` | Dependency JAR cần để phân giải các class |
| `Finding` | Class gọi và chữ ký Java SE API deprecated |
| `Risk` | Thường / for-removal / API đã bị xóa trong JDK đích |
| `Ownership` | Source do nhóm sửa hay JAR vendor |
| `Plan` | API thay thế, phiên bản library nâng, tests cần chạy |
| `Verification` | Build, scan lại, unit/integration tests trên JDK đích |

Khi tìm thấy finding, đi theo thứ tự:

1. Xác định nguồn bytecode: class do mình xây dựng, dependency bên ngoài hay binary được đóng gói lại.
2. Đọc **Javadoc** của API được báo và release notes/migration guide của JDK đích.
3. Xác định **hành vi thật sự mà ứng dụng cần**: dữ liệu đầu vào/đầu ra, checked exceptions, timezone, concurrency, security...
4. Chọn replacement **còn được hỗ trợ hiện nay**, tránh chuyển từ API deprecated sang API JDK nội bộ.
5. Thay source hoặc nâng dependency, build lại artifact sạch và scan **artifact mới**.
6. Viết regression tests cho hành vi, test JDK đích và lưu report mới.

Nếu scanner chỉ biết một class có reference mà không thấy source line, đọc source package hoặc:

```bash
javap -c -classpath out DeprecationScanDemo
```

Lệnh `javap -c` hiển thị bytecode để xác định nơi có `invokevirtual java/util/Date.getYear`. Đây là công cụ phân tích bổ trợ; kết quả biên dịch có thể chứa synthetic methods, nên vẫn cần đối chiếu source và ý nghĩa thực tế của lời gọi.

## 11. Giới hạn quan trọng và lỗi tư duy thường gặp

- **“Scan không báo gì, vậy nâng JDK chắc chắn thành công.”** Sai: deprecation chỉ là một nhóm vấn đề. API đã gỡ bỏ, lỗi linkage, access module, native code và thay đổi hành vi cần kiểm chứng riêng.
- **“Thêm `@SuppressWarnings` là giải quyết xong.”** Sai: annotation chỉ thay cảnh báo compiler; bytecode vẫn phụ thuộc vào API bị deprecated.
- **“Quét một JAR ứng dụng đã quét luôn mọi dependency.”** Không đúng với thin JAR; cần xác định và quét từng artifact liên quan.
- **“Chỉ cần `--class-path` chứa JAR vendor là scanner báo tất cả deprecated usage của JAR đó.”** Classpath chủ yếu giúp phân giải; muốn quét bytecode vendor, đưa JAR làm **target scan**.
- **“`--for-removal` trống nghĩa là không còn công nợ.”** Nó chỉ loại bỏ findings thuộc nhóm chưa được đánh dấu for-removal; scan thường có thể vẫn còn deprecations.
- **“`jdeprscan` phát hiện cả third-party annotations, mọi API bị xóa và lỗ hổng CVE.”** Sai phạm vi; dùng công cụ đúng bài toán.
- **“`--release` của `jdeprscan` tương đương `--release` của `javac`.”** Hai flag cùng tên nhưng khác ý nghĩa; một cái chọn danh sách deprecated, một cái ràng buộc biên dịch.
- **“Chỉ kiểm tra phiên bản JDK đang chạy ứng dụng.”** Với kế hoạch nâng JDK, phải dùng một scanner biết các API deprecated của **release mục tiêu**.
- **“Chỉ đổi phương thức deprecated sang tên mới.”** Phải kiểm tra semantic compatibility; ví dụ thao tác năm/thời gian cần chọn timezone nghiệp vụ.
- **“API bị đánh dấu for-removal sẽ chắc chắn bị xóa ở JDK kế tiếp.”** Không có quy luật đó; theo dõi thông báo chính thức.

## 12. Checklist cho một lần nâng JDK

1. Chốt JDK nguồn, JDK đích, version dependency và artifact phát hành.
2. Kiểm tra `jdeprscan --help`, `--version`; chọn scanner có hỗ trợ release đích.
3. Compile/package ứng dụng; quét đúng thư mục class và từng JAR runtime cần kiểm tra.
4. Bổ sung `--class-path` để xử lý thiếu class; không coi scan lỗi là clean.
5. Chạy cả quét deprecated và `--for-removal`; lưu báo cáo đầy đủ.
6. Đọc migration guide của JDK đích để phát hiện API **đã xóa** và các thay đổi ngoài deprecation.
7. Phân loại finding theo mức rủi ro và owner; ưu tiên mã bị đánh dấu for-removal.
8. Chọn supported replacement hoặc nâng vendor dependency; kiểm tra hành vi.
9. Build/scan lại bytecode mới; chạy unit, integration và compatibility tests trên JDK đích.
10. Gắn việc chấp nhận rủi ro với một baseline và trách nhiệm cụ thể trong CI.

## 13. Tài liệu chính thống còn giá trị sử dụng

- Oracle JDK: [The jdeprscan Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html) — cú pháp, dạng input, `--class-path`, `--release`, `--for-removal` và phạm vi Java SE API.
- Oracle JDK Migration Guide: [Running jdeprscan](https://docs.oracle.com/en/java/javase/22/core/running-jdeprscan.html) — lý do quét binary dependency và rủi ro khi API đã bị gỡ bỏ.
- Oracle Java SE 26: [Deprecated API List](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html) — danh sách deprecations theo release.
- Oracle JDK 26 Migration Guide: [Removed APIs](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html) — API đã xóa và các lưu ý nâng JDK.
- Oracle Java SE 25: [java.util.Date](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Date.html) — `getYear()` deprecated, chỉ dùng làm fixture ở bài này.
- Oracle JDK Tool Specifications: [jdeps](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html) — phân tích class/package/module dependencies và JDK internal API.
