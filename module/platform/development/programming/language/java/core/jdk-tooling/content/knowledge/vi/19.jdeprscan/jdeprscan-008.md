# Xử lý cảnh báo deprecated bằng jdeprscan

`jdeprscan` là công cụ dòng lệnh đi kèm JDK để quét class file, thư mục class và JAR nhằm tìm tham chiếu đến các API Java SE đã bị đánh dấu deprecated. Công cụ hữu ích khi chuẩn bị nâng cấp JDK, đánh giá thư viện cũ và ưu tiên xử lý API có nguy cơ bị loại bỏ.

`jdeprscan` phân tích bytecode tĩnh; nó không chạy ứng dụng và không tự sửa mã nguồn. Kết quả cho biết class nào tham chiếu đến API deprecated nào. Người phát triển cần tìm vị trí nguồn, đọc tài liệu migration, chọn API thay thế, sửa code hoặc nâng dependency rồi quét lại và kiểm thử.

Cần phân biệt:

- `jdeprscan` tìm tham chiếu trong bytecode đến API deprecated của nền tảng Java.
- `javac -Xlint:deprecation` và `-Xlint:removal` cảnh báo khi biên dịch source có sử dụng API deprecated.
- Javadoc và migration guide giải thích vì sao API bị deprecated, API thay thế và lưu ý chuyển đổi.

Kết hợp các cách này giúp phát hiện vấn đề trong source đang biên dịch và tham chiếu đã tồn tại trong binary dependency.

## 1. Deprecated API là gì?

Một API được đánh dấu deprecated khi nhà phát triển nền tảng hoặc thư viện khuyến nghị không dùng API đó trong code mới. API có thể vẫn hoạt động, nhưng có thể có thiết kế lỗi thời, vấn đề bảo mật, hành vi khó bảo trì hoặc một API thay thế tốt hơn.

Annotation `@Deprecated` đánh dấu một declaration:

```java
@Deprecated
public void oldOperation() {
    // Legacy implementation
}
```

Từ Java 9, annotation có thêm thuộc tính `since` và `forRemoval`:

```java
@Deprecated(since = "17", forRemoval = true)
public void legacyOperation() {
    // API is planned for removal
}
```

- `since` ghi phiên bản mà API bắt đầu bị deprecated.
- `forRemoval = false` hoặc không khai báo cho biết API deprecated nhưng chưa được đánh dấu rõ là sẽ loại bỏ.
- `forRemoval = true` thể hiện ý định loại bỏ API trong một bản phát hành tương lai.

Trong Javadoc, tag `@deprecated` cung cấp giải thích cho người dùng và nên nêu API thay thế:

```java
/**
 * Performs the legacy operation.
 *
 * @deprecated Use {@link #newOperation()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    newOperation();
}
```

Annotation cung cấp metadata cho compiler/tooling; tag Javadoc giải thích lý do và hướng chuyển đổi cho người đọc tài liệu.

Deprecated không đồng nghĩa với đã bị xóa. API có thể tiếp tục tồn tại nhiều phiên bản sau khi bị deprecated. Tuy nhiên, API có `forRemoval = true` cần được ưu tiên xử lý vì rủi ro bị loại bỏ cao hơn.

## 2. jdeprscan kiểm tra điều gì?

`jdeprscan` quét các class file trong đầu vào và đối chiếu tham chiếu được tìm thấy với danh sách API deprecated của Java SE trong release được chọn.

Đầu vào có thể là:

- Một file `.class`.
- Một thư mục chứa class file.
- Một file JAR.
- Một tập class hoặc archive được chỉ định trên dòng lệnh.

Công cụ có thể tìm tham chiếu đến method, constructor, field hoặc type deprecated. Kết quả thường chỉ ra class chứa tham chiếu và API deprecated được sử dụng. Định dạng thông báo chi tiết có thể thay đổi theo phiên bản JDK.

Phạm vi quan trọng:

- `jdeprscan` tập trung vào API deprecated của nền tảng Java SE/JDK.
- Nó không phải công cụ tổng quát để tìm mọi API deprecated trong thư viện bên thứ ba.
- Nó phân tích bytecode, không đọc ý nghĩa của toàn bộ source code.
- Nó không thực thi ứng dụng và không kiểm tra mọi đường chạy runtime.
- Nó có thể tìm tham chiếu trong method không được gọi ở lần chạy thông thường, vì bytecode vẫn tồn tại trong class file.

Nếu cần kiểm tra API deprecated của thư viện bên thứ ba hoặc API nội bộ của tổ chức, hãy dùng compiler warning, tài liệu thư viện, IDE inspection hoặc static-analysis rule phù hợp.

## 3. Khởi động và xem trợ giúp

`jdeprscan` được cung cấp cùng JDK. Kiểm tra phiên bản và trợ giúp:

```sh
jdeprscan --version
jdeprscan --help
```

Cú pháp tổng quát:

```text
jdeprscan [options] {dir|jar|class}
```

Quét một JAR:

```sh
jdeprscan app.jar
```

Quét thư mục class file:

```sh
jdeprscan build/classes
```

Quét một class cụ thể:

```sh
jdeprscan build/classes/com/example/LegacyService.class
```

Nếu không chỉ định release, công cụ dùng tập API của JDK hiện tại theo quy tắc của phiên bản tool. Khi kiểm tra nâng cấp, nên chỉ định rõ release để kết quả có thể tái lập.

## 4. Chọn release API bằng --release

Tùy chọn `--release` chọn Java SE release dùng làm mốc kiểm tra API deprecated:

```sh
jdeprscan --release 17 app.jar
```

Danh sách release được hỗ trợ phụ thuộc JDK đang chạy `jdeprscan`. Xem `jdeprscan --help` để biết giá trị hợp lệ.

Chọn release theo mục tiêu:

| Mục tiêu | Cách chọn |
|---|---|
| Kiểm tra API deprecated theo JDK hiện tại | Dùng release tương ứng với JDK hiện tại hoặc bỏ tùy chọn nếu phù hợp |
| Kiểm tra ứng dụng chạy trên Java 17 | Dùng `--release 17` |
| Chuẩn bị nâng ứng dụng từ Java 17 lên Java 21 | Dùng `--release 21` để phát hiện API đã deprecated trong nền tảng đích |
| So sánh thay đổi qua các release | Chạy nhiều lần với từng release được hỗ trợ |

Ví dụ khi chuẩn bị nâng lên Java 21:

```sh
jdeprscan --release 21 app.jar
jdeprscan --release 21 --for-removal app.jar
```

Lệnh thứ nhất tìm API deprecated theo release 21; lệnh thứ hai tập trung vào API được đánh dấu for removal trong release đó. Nếu chỉ quét theo release cũ, bạn có thể bỏ sót API mới bị deprecated trong release đích.

## 5. Chỉ tìm API deprecated for removal

Tùy chọn `--for-removal` giới hạn kết quả vào những API được đánh dấu sẽ bị loại bỏ:

```sh
jdeprscan --for-removal --release 21 app.jar
```

Dùng tùy chọn này để lập danh sách ưu tiên cho kế hoạch nâng cấp. Những API này cần được xử lý sớm hơn API deprecated thông thường.

Có thể xem danh sách API deprecated của release mà không quét ứng dụng cụ thể bằng `--list`:

```sh
jdeprscan --list --release 21
```

Chỉ liệt kê API for removal:

```sh
jdeprscan --list --for-removal --release 21
```

Các lệnh `--list` hữu ích khi tra cứu một API hoặc lập danh sách thay đổi giữa các release. Kết quả phụ thuộc JDK và release được chỉ định.

## 6. Đọc kết quả quét

Một finding thường cho biết:

1. Tên class file có tham chiếu.
2. Loại tham chiếu, chẳng hạn method hoặc field.
3. Tên API và chữ ký mà class file sử dụng.
4. Trạng thái deprecated/for-removal theo release được chọn.

Ví dụ minh họa về nội dung finding:

```text
LegacyDateExample uses deprecated method
java/util/Date::getYear()I
```

Đây là cách diễn giải rút gọn; định dạng đầu ra thực tế có thể khác giữa các phiên bản JDK.

Khi đọc một finding, hãy xác định:

- Tham chiếu đến API nào?
- API được deprecated từ release nào?
- Có được đánh dấu for removal không?
- Class nào tạo ra tham chiếu?
- Class đó thuộc source ứng dụng hay thư viện bên thứ ba?
- API thay thế có giữ nguyên ngữ nghĩa và hành vi cần thiết không?

Không nên chỉ đếm số warning. Một tham chiếu trong thư viện cũ có thể ảnh hưởng nhiều ứng dụng; một API deprecated nằm trong nhánh code ít dùng có thể có mức ưu tiên khác. Kết hợp finding với mức độ sử dụng, khả năng cập nhật và kế hoạch phát hành.

## 7. Ví dụ phát hiện API deprecated trong source

Method `Date.getYear()` là API cũ đã deprecated. Nó trả về năm trừ đi 1900, nên code cũ thường phải cộng thêm 1900 để có năm đầy đủ.

Tạo tệp `src/LegacyDateExample.java`:

```java
import java.util.Date;

public class LegacyDateExample {
    public static int year(Date date) {
        return date.getYear() + 1900;
    }

    public static void main(String[] args) {
        System.out.println(year(new Date(1592222400000L)));
    }
}
```

Biên dịch với cảnh báo deprecation:

```sh
javac -Xlint:deprecation -d out src/LegacyDateExample.java
```

Compiler sẽ cảnh báo về việc sử dụng `Date.getYear()`. Sau khi có class file, quét:

```sh
jdeprscan --release 21 out
```

Kết quả xác định class `LegacyDateExample` có tham chiếu đến method deprecated `java.util.Date.getYear()`. Chi tiết định dạng có thể khác theo JDK.

Chạy chương trình cũ:

```sh
java -cp out LegacyDateExample
```

Stdout:

```text
2020
```

Ví dụ dùng một instant giữa năm 2020 để kết quả của `Date.getYear()` ổn định ở cùng năm trên các timezone thông dụng. Method cũ vẫn phụ thuộc timezone mặc định; không nên dùng nó cho logic ngày giờ mới.

## 8. Thay API deprecated bằng java.time

Với code mới, nên dùng Java Date and Time API trong `java.time` thay cho thao tác ngày giờ cũ.

Tạo tệp `src/ModernDateExample.java`:

```java
import java.time.ZoneId;
import java.util.Date;

public class ModernDateExample {
    public static int year(Date date) {
        return date.toInstant()
                   .atZone(ZoneId.of("UTC"))
                   .getYear();
    }

    public static void main(String[] args) {
        System.out.println(year(new Date(1592222400000L)));
    }
}
```

Biên dịch và chạy:

```sh
javac -d out src/ModernDateExample.java
java -cp out ModernDateExample
```

Stdout:

```text
2020
```

Code mới chuyển `Date` thành `Instant` rồi chuyển instant sang UTC trước khi lấy năm. Chọn UTC làm cho ví dụ có kết quả ổn định, không phụ thuộc timezone mặc định của máy.

Khi thay API ngày giờ, không được bỏ qua timezone. Nếu nghiệp vụ cần năm theo timezone người dùng hoặc địa điểm kinh doanh, hãy dùng `ZoneId` tương ứng thay vì luôn dùng UTC. Thay API cần giữ nguyên ý nghĩa nghiệp vụ, không chỉ làm warning biến mất.

## 9. Xử lý một finding theo từng bước

Khi `jdeprscan` báo một API deprecated, thực hiện:

1. **Xác định vị trí:** ghi lại class, method/field và chữ ký được báo.
2. **Tìm source:** tìm declaration hoặc lời gọi tương ứng trong mã nguồn.
3. **Đọc tài liệu:** mở Javadoc của API và đọc phần `@deprecated`, replacement hoặc migration guide.
4. **Đánh giá mức độ:** xác định API có `forRemoval` không, phiên bản bắt đầu deprecated và runtime mục tiêu.
5. **Chọn replacement:** ưu tiên API được hỗ trợ chính thức và giữ đúng semantics.
6. **Sửa code:** cập nhật method, import, kiểu dữ liệu và xử lý ngoại lệ liên quan.
7. **Kiểm thử:** thêm test cho kết quả, giá trị biên, timezone, encoding, resource hoặc hành vi có thể thay đổi.
8. **Quét lại:** biên dịch lại và chạy `jdeprscan` trên artifact mới.
9. **Ghi nhận:** lưu finding còn lại, lý do chưa xử lý và phiên bản dự kiến nâng cấp.

Nếu API không có replacement trực tiếp, hãy tìm migration guide hoặc thiết kế lại phần chức năng. Đừng tạo wrapper chỉ đổi tên nhưng vẫn gọi API deprecated bên dưới; finding trong bytecode vẫn còn.

## 10. Xử lý warning từ thư viện bên thứ ba

Một finding có thể đến từ class file của thư viện ngoài, không phải source do đội dự án sở hữu.

Quy trình:

- Xác định JAR chứa class được báo.
- Xem phiên bản thư viện hiện tại và phiên bản mới nhất tương thích.
- Đọc changelog/migration guide của nhà cung cấp.
- Nâng dependency nếu phiên bản mới đã thay API deprecated.
- Nếu không có bản sửa, đánh giá rủi ro và tìm thư viện thay thế.
- Chạy integration test sau khi nâng phiên bản.

`--class-path` giúp `jdeprscan` phân giải dependency cần thiết khi phân tích:

```sh
jdeprscan --release 21 --class-path "lib/*" app.jar
```

Trên Windows, dấu phân tách nhiều mục classpath là dấu chấm phẩy; Linux/macOS dùng dấu hai chấm.

Lưu ý: `--class-path` cung cấp dependency để phân giải tham chiếu. Nó không có nghĩa tất cả JAR trên classpath đều tự động được quét như đầu vào. Nếu muốn quét một thư viện, truyền chính JAR đó làm đối tượng cần phân tích:

```sh
jdeprscan --release 21 lib/legacy-library.jar
```

Nếu thư viện là binary của bên thứ ba, đội ứng dụng có thể không sửa được bytecode. Khi đó cần nâng phiên bản, thay thư viện hoặc ghi nhận rủi ro còn lại; không nên chỉnh sửa JAR đã phát hành tùy tiện.

## 11. Phân biệt cảnh báo source với finding trong binary

`jdeprscan` và compiler có vai trò bổ sung:

| Công cụ | Thời điểm | Phạm vi chính |
|---|---|---|
| `javac -Xlint:deprecation` | Khi biên dịch source | Lời gọi deprecated mà compiler nhìn thấy trong source đang biên dịch |
| `javac -Xlint:removal` | Khi biên dịch source | Lời gọi API được đánh dấu for removal |
| `jdeprscan` | Sau khi có class/JAR | Tham chiếu deprecated được lưu trong bytecode |
| IDE inspection | Trong lúc phát triển | Source và dependency theo khả năng IDE |
| Javadoc/migration guide | Khi điều tra | Lý do deprecated và hướng thay thế |

Bật compiler warning:

```sh
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
```

Nếu muốn build thất bại khi có warning, có thể cân nhắc `-Werror` sau khi xử lý warning hiện tại:

```sh
javac -Xlint:deprecation -Xlint:removal -Werror -d out src/com/example/*.java
```

`-Werror` biến warning của compiler thành lỗi build. Đây là chính sách build, không phải tùy chọn của `jdeprscan`. Kiểm tra cú pháp wildcard theo shell đang dùng; PowerShell không mở rộng wildcard cho mọi native command theo cách giống Bash.

## 12. Giới hạn của phân tích tĩnh

`jdeprscan` hữu ích nhưng không thể thay thế kiểm thử runtime. Những trường hợp có thể không được phát hiện đầy đủ:

- Tên lớp hoặc method được lưu trong chuỗi rồi dùng qua reflection.
- Class được tải bằng `Class.forName` với tên lấy từ cấu hình.
- Plugin được phát hiện và tải động.
- Bytecode được sinh trong runtime.
- Native code gọi vào Java hoặc sử dụng API qua JNI.
- Code path chỉ được kích hoạt theo cấu hình hoặc dữ liệu đặc biệt.

Ví dụ:

```java
String className = configuration.get("implementation.class");
Class<?> implementation = Class.forName(className);
```

Nếu giá trị cấu hình trỏ đến một lớp có sử dụng API deprecated, `jdeprscan` có thể không suy ra mối liên hệ từ chuỗi cấu hình này. Hãy kiểm tra plugin, file cấu hình và integration test.

Ngược lại, công cụ có thể báo tham chiếu trong method chưa được gọi ở runtime. Đây không nhất thiết là false positive: bytecode vẫn chứa tham chiếu và có thể được kích hoạt sau này.

## 13. Deprecated API trong module và multi-release JAR

Khi quét module hoặc JAR có dependency ngoài, cung cấp module path phù hợp:

```sh
jdeprscan --release 21 --module-path "mods:lib" app.jar
```

`--module-path` giúp công cụ tìm các module cần thiết để phân giải tham chiếu. Trên Windows, dùng dấu chấm phẩy để phân tách module path.

Với multi-release JAR, chọn phiên bản class cần phân tích bằng `--multi-release`:

```sh
jdeprscan --release 21 --multi-release 17 library.jar
```

Tùy chọn này yêu cầu công cụ xem phần versioned entry phù hợp trong multi-release JAR. Chọn release tương ứng với cấu hình runtime đang đánh giá và xác nhận archive được đánh dấu `Multi-Release: true` trong manifest.

Nếu thư viện chứa nhiều implementation theo Java release, dependency deprecated có thể khác nhau giữa base entry và versioned entry. Không dùng kết quả của một release để khẳng định mọi phiên bản đều sạch.

## 14. Tích hợp jdeprscan vào quy trình nâng cấp

Một quy trình kiểm tra trong CI có thể gồm:

1. Biên dịch ứng dụng bằng JDK mục tiêu.
2. Bật compiler warning cho deprecation và removal.
3. Tạo JAR hoặc thư mục class đầu ra.
4. Chạy `jdeprscan` với `--release` đúng mục tiêu.
5. Chạy thêm `--for-removal` để lập danh sách ưu tiên.
6. Quét các JAR nội bộ hoặc thư viện quan trọng riêng.
7. Lưu log như artifact của pipeline.
8. Chạy unit test và integration test trên runtime mục tiêu.
9. So sánh finding với baseline của nhánh chính.
10. Chặn việc thêm finding mới theo chính sách của dự án.

Ví dụ script Linux/macOS:

```sh
set -e
rm -rf out
mkdir -p out
javac -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
jdeprscan --release 21 out
jdeprscan --for-removal --release 21 out
```

Script minh họa thứ tự compile rồi scan. Trong dự án nhiều package/module, hãy dùng cấu hình build thực tế thay cho wildcard đơn giản. `jdeprscan` không tự quyết định mức độ nghiêm trọng cho từng finding; CI cần quy tắc riêng để so sánh và xử lý kết quả.

Với Maven hoặc Gradle, có thể thêm bước chạy công cụ vào task/plugin hoặc pipeline sau khi artifact được tạo. Bảo đảm `jdeprscan` đến từ JDK mục tiêu, không vô tình chạy bản JDK khác với bản dùng để build.

## 15. Xử lý API deprecated của chính dự án

Nếu dự án phát hành thư viện riêng và muốn đánh dấu API cũ để người dùng chuyển đổi, khai báo annotation cùng Javadoc:

```java
/**
 * Creates a legacy client.
 *
 * @deprecated Use {@link #createClient()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public static Client createLegacyClient() {
    return createClient();
}

/**
 * Creates a supported client.
 *
 * @return a new client
 */
public static Client createClient() {
    return new Client();
}
```

Nguyên tắc:

- Ghi release bắt đầu deprecated bằng `since`.
- Dùng `forRemoval = true` chỉ khi có kế hoạch loại bỏ thực sự.
- Javadoc tag `@deprecated` giải thích replacement.
- Giữ hành vi tương thích trong giai đoạn chuyển tiếp nếu chính sách API yêu cầu.
- Có thể ghi migration guide và mốc dự kiến loại bỏ.

`jdeprscan` không phải công cụ tổng quát để quét mọi annotation deprecated do thư viện riêng định nghĩa. Để kiểm tra việc sử dụng API deprecated nội bộ, dựa vào compiler warning khi biên dịch client source, IDE/static analysis và test của dự án.

## 16. Không che warning bằng suppression

Java hỗ trợ `@SuppressWarnings("deprecation")` và các warning category liên quan trong compiler. Chỉ nên dùng suppression khi có lý do cụ thể, phạm vi hẹp và có ghi chú giải thích.

Ví dụ:

```java
@SuppressWarnings("deprecation")
static int legacyYear(java.util.Date date) {
    return date.getYear() + 1900;
}
```

Suppression có thể làm compiler ngừng cảnh báo cho đoạn source đó. Nó không thay thế API, không thay đổi bytecode và không khiến `jdeprscan` bỏ qua tham chiếu đã được biên dịch.

Nếu buộc phải giữ API cũ trong giai đoạn chuyển tiếp:

- Cô lập lời gọi trong một method nhỏ.
- Ghi rõ lý do và kế hoạch loại bỏ.
- Thêm test bảo đảm hành vi tương thích.
- Theo dõi release mà API có thể bị loại bỏ.
- Không suppress toàn bộ package hoặc project nếu chỉ có một vị trí đặc biệt.

Đối với API đã bị loại bỏ khỏi JDK mục tiêu, suppression không giúp code biên dịch hoặc chạy được. Cần thay thế API hoặc thay đổi dependency/runtime.

## 17. Lỗi thường gặp khi dùng jdeprscan

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có finding nhưng compiler vẫn cảnh báo | Source hoặc thư viện dùng API deprecated ngoài phạm vi Java SE mà jdeprscan nhận diện | Dùng compiler lint và công cụ phân tích thư viện |
| Không tìm thấy class/dependency | Classpath hoặc module path thiếu JAR | Bổ sung đúng dependency và kiểm tra đường dẫn |
| Finding chỉ đến class trong thư viện ngoài | Binary dependency sử dụng API deprecated | Nâng dependency hoặc thay thư viện |
| Kết quả khác khi đổi JDK | Danh sách API deprecated thay đổi theo release | Ghi rõ JDK và dùng `--release` tường minh |
| Không thấy API được gọi qua reflection | Tham chiếu chỉ tồn tại dưới dạng chuỗi/cấu hình | Kiểm tra cấu hình, plugin và runtime test |
| Quét JAR nhưng bỏ sót class versioned | Multi-release JAR chưa được phân tích theo release phù hợp | Dùng `--multi-release` |
| Dùng --for-removal nhưng vẫn thấy ít finding | Chỉ API được đánh dấu for removal mới được báo | Chạy thêm lượt không có tùy chọn này để xem toàn bộ deprecated API |
| Đã suppress compiler warning nhưng jdeprscan vẫn báo | Suppression không xóa tham chiếu trong bytecode | Thay API hoặc chấp nhận/ghi nhận finding có kiểm soát |
| Ứng dụng chạy trên JDK cũ nhưng lỗi trên JDK mới | API đã bị loại bỏ hoặc thay đổi hành vi | Quét theo release đích và kiểm thử migration |
| Chỉ quét JAR ứng dụng mà bỏ qua dependency | Dependency không được truyền như đầu vào cần quét | Quét riêng artifact thuộc phạm vi kiểm soát |

Khi công cụ báo lỗi phân giải, kiểm tra classpath/module path trước khi kết luận API không tồn tại. Khi công cụ không báo finding, vẫn cần kiểm tra reflection và dependency ngoài vì phân tích tĩnh có giới hạn.

## 18. Checklist xử lý cảnh báo

- [ ] Đã xác định JDK và release API cần kiểm tra.
- [ ] Đã chạy `jdeprscan` trên class directory hoặc JAR mới nhất.
- [ ] Đã chạy thêm `--for-removal` để ưu tiên API có nguy cơ bị loại bỏ.
- [ ] Đã đọc class và symbol được nêu trong từng finding.
- [ ] Đã xác định finding thuộc source dự án hay thư viện ngoài.
- [ ] Đã đọc Javadoc/migration guide của API deprecated.
- [ ] Đã chọn replacement giữ đúng semantics, timezone và xử lý lỗi.
- [ ] Đã nâng hoặc thay dependency nếu finding đến từ thư viện bên thứ ba.
- [ ] Đã xem xét reflection, service provider, plugin và class loading động.
- [ ] Đã bật compiler warning `-Xlint:deprecation` và `-Xlint:removal`.
- [ ] Đã biên dịch lại và quét lại artifact sau khi sửa.
- [ ] Đã chạy unit test và integration test trên JDK mục tiêu.
- [ ] Finding còn lại có lý do, owner và kế hoạch xử lý rõ ràng.

## 19. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jdeprscan` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html
- Oracle Java Language Specification — Annotations and `@Deprecated`: https://docs.oracle.com/javase/specs/
- Oracle Java API Documentation — `java.lang.Deprecated`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html

`jdeprscan` giúp phát hiện sớm tham chiếu đến API Java đã deprecated trước khi nâng cấp JDK. Khi đọc finding theo release, ưu tiên API for removal, thay thế bằng API được hỗ trợ và kiểm thử lại trên runtime mục tiêu, đội phát triển có thể giảm rủi ro tương thích và tránh để dependency cũ trở thành trở ngại trong các lần nâng cấp tiếp theo.