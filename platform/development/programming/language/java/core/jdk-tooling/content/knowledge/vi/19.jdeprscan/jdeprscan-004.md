# Quét JAR bằng jdeprscan

**`jdeprscan`** là công cụ dòng lệnh đi kèm JDK, dùng để quét class file, thư mục class hoặc tệp JAR nhằm tìm những chỗ sử dụng API Java đã được đánh dấu deprecated. Công cụ đặc biệt hữu ích khi kiểm tra thư viện hoặc ứng dụng đã biên dịch mà không còn đầy đủ mã nguồn, hoặc khi chuẩn bị nâng cấp lên một phiên bản JDK mới.

Khi truyền một JAR cho `jdeprscan`, công cụ đọc các class file trong archive và báo những tham chiếu đến API deprecated của nền tảng Java mà nó nhận diện được. Nó không sửa bytecode, không thay thế API cũ và không tự động xác nhận ứng dụng tương thích với JDK mới.

## 1. Vì sao cần quét JAR?

Java duy trì khả năng tương thích trong thời gian dài, nhưng một số API cũ có thể được thay thế, đánh dấu deprecated hoặc dự kiến loại bỏ trong phiên bản tương lai.

Một JAR có thể được build từ lâu và vẫn chứa tham chiếu đến API đã deprecated. Nếu chỉ kiểm tra mã nguồn hiện tại, nhóm phát triển có thể bỏ sót:

- Thư viện nội bộ đã được biên dịch từ trước.
- Dependency đóng gói cùng ứng dụng.
- Class file được tạo bởi một quy trình build khác.
- API deprecated được sử dụng trong mã nguồn mà hiện không còn được biên dịch thường xuyên.
- API đã được đánh dấu *deprecated for removal* và có nguy cơ biến mất trong JDK tương lai.

Quét JAR giúp lập danh sách những vị trí cần xem xét trước khi nâng cấp JDK, thay dependency hoặc phát hành phiên bản mới.

Các tình huống sử dụng phổ biến:

- Kiểm tra JAR của ứng dụng trước khi nâng JDK.
- Kiểm tra thư viện nội bộ hoặc thư viện bên thứ ba đã biên dịch.
- Tìm API deprecated trong artifact phát hành.
- Tìm API được đánh dấu for removal.
- Kiểm tra nhiều JAR trong quy trình CI hoặc trước một đợt migration.

## 2. jdeprscan kiểm tra những gì?

`jdeprscan` phân tích bytecode và đối chiếu các tham chiếu được phát hiện với danh sách API deprecated của nền tảng Java theo phiên bản được chọn.

Công cụ có thể nhận các loại đầu vào:

- Thư mục chứa cây package và class file.
- Tệp JAR.
- Tệp class riêng lẻ.
- Tên lớp đầy đủ (fully qualified class name).

Công cụ tập trung vào API deprecated của Java SE/JDK. Nó không phải bộ quét tổng quát cho mọi annotation `@Deprecated` trong thư viện bên thứ ba hoặc mã nguồn riêng của tổ chức.

Cần phân biệt:

| Công cụ | Đầu vào chính | Mục đích |
| --- | --- | --- |
| `jdeprscan` | JAR, class file, thư mục class hoặc tên lớp | Quét bytecode để tìm sử dụng API deprecated của JDK |
| `javac -Xlint:deprecation` | Mã nguồn đang biên dịch | Cảnh báo khi mã nguồn sử dụng API deprecated mà compiler nhận diện |
| `javadoc` | Mã nguồn và documentation comment | Tạo tài liệu API |
| `jdeps` | Class file, JAR hoặc module | Phân tích phụ thuộc giữa class/package/module |

`jdeprscan` hữu ích khi artifact đã được build và bạn muốn kiểm tra chính binary đó. Nếu còn mã nguồn, nên kết hợp với cảnh báo compiler để phát hiện vấn đề ngay trong quá trình build.

## 3. Kiểm tra và xem trợ giúp

`jdeprscan` là công cụ của JDK. Kiểm tra môi trường:

```bash
java -version
javac -version
jdeprscan --version
```

Xem toàn bộ cú pháp:

```bash
jdeprscan --help
```

Nếu terminal không nhận diện lệnh:

- Kiểm tra máy đã cài JDK đầy đủ.
- Kiểm tra thư mục `bin` của JDK có trong `PATH`.
- Kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK.
- Mở terminal mới sau khi thay đổi biến môi trường.

Có thể gọi trực tiếp công cụ từ thư mục `bin` của JDK. Danh sách release được hỗ trợ bởi `--release` phụ thuộc phiên bản `jdeprscan`; hãy xem `jdeprscan --help` trên đúng JDK đang dùng.

## 4. Cú pháp cơ bản để quét JAR

Cú pháp:

```text
jdeprscan [options] {dir|jar|class} ...
```

Quét một JAR:

```bash
jdeprscan app.jar
```

Quét nhiều JAR trong cùng một lần gọi:

```bash
jdeprscan app.jar lib/helper.jar lib/legacy-client.jar
```

Chọn phiên bản API để đối chiếu:

```bash
jdeprscan --release 17 app.jar
```

Bật thông tin xử lý chi tiết:

```bash
jdeprscan --verbose app.jar
```

Trong đó:

- `app.jar`: JAR cần kiểm tra.
- `--release 17`: đối chiếu với tập API deprecated của Java SE 17.
- `--verbose`: hiển thị thêm thông tin trong quá trình xử lý.

`--release` chọn phiên bản API dùng để đánh giá trạng thái deprecated. Nó không biên dịch lại JAR, không thay đổi major version của class file và không biến JAR thành artifact tương thích với phiên bản đó.

Nếu bỏ `--release`, công cụ sử dụng tập API của JDK đang chạy `jdeprscan`.

## 5. Ví dụ hoàn chỉnh: tạo JAR có dùng API deprecated

Ví dụ dưới đây sử dụng `java.util.Date.getYear()`, một method đã deprecated. Mục tiêu là tạo JAR có tham chiếu đó rồi quét bằng `jdeprscan`.

Cấu trúc dự án:

```text
project/
  src/
    com/
      example/
        audit/
          LegacyApiUse.java
  out/
  dist/
```

Tạo tệp **`src/com/example/audit/LegacyApiUse.java`**:

```java
package com.example.audit;

import java.util.Date;

public final class LegacyApiUse {
    private LegacyApiUse() {
    }

    public static int legacyYear(Date date) {
        return date.getYear();
    }
}
```

Method `Date.getYear()` trả về năm tính từ 1900 và đã được deprecated. Ví dụ cố ý giữ lời gọi này để tạo một bytecode có thể được `jdeprscan` phát hiện.

### Bước 1: Biên dịch class

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force out, dist | Out-Null
javac --release 17 -Xlint:deprecation -d out src/com/example/audit/LegacyApiUse.java
```

**macOS/Linux:**

```bash
mkdir -p out dist
javac --release 17 -Xlint:deprecation -d out src/com/example/audit/LegacyApiUse.java
```

Compiler phát warning về việc sử dụng API deprecated. Dùng `-Xlint:deprecation` để yêu cầu chẩn đoán chi tiết hơn.

Class file được tạo tại:

```text
out/
  com/
    example/
      audit/
        LegacyApiUse.class
```

### Bước 2: Đóng gói thành JAR

Chạy:

```bash
jar --create --file dist/legacy-app.jar -C out .
```

Kiểm tra nội dung:

```bash
jar --list --file dist/legacy-app.jar
```

Danh sách cần có:

```text
com/example/audit/LegacyApiUse.class
```

### Bước 3: Quét JAR

Đối chiếu với API Java 17:

```bash
jdeprscan --release 17 dist/legacy-app.jar
```

Công cụ sẽ báo class có tham chiếu đến method deprecated. Output minh họa có dạng:

```text
class com/example/audit/LegacyApiUse uses deprecated method java/util/Date.getYear()I
```

Cách trình bày chính xác có thể khác theo phiên bản JDK. Nội dung quan trọng là class chứa tham chiếu và API deprecated được chỉ ra.

Ví dụ này chỉ cần biên dịch class và đóng gói JAR; không cần chạy chương trình để `jdeprscan` phát hiện tham chiếu trong bytecode.

## 6. Chọn phiên bản API với --release

Tùy chọn `--release` cho phép chọn phiên bản Java SE dùng làm mốc kiểm tra:

```bash
jdeprscan --release 17 app.jar
```

Điều này hữu ích khi:

- Ứng dụng được build để hỗ trợ Java 17.
- Muốn đánh giá trạng thái deprecated theo API của một release cụ thể.
- Muốn so sánh kết quả khi nâng baseline từ Java 17 lên Java 21 hoặc release mới hơn.
- Muốn kiểm tra API đã deprecated ở phiên bản mục tiêu, thay vì chỉ theo JDK đang cài trên máy.

Ví dụ so sánh:

```bash
jdeprscan --release 17 app.jar
jdeprscan --release 21 app.jar
```

Một API có thể có trạng thái hoặc metadata khác nhau giữa các release. Vì vậy, kết quả quét phụ thuộc phiên bản API được chọn.

**Không nhầm `--release` của jdeprscan với `javac --release`:**

- `javac --release 17` giới hạn ngôn ngữ, bytecode và API nền tảng mà compiler dùng để biên dịch.
- `jdeprscan --release 17` chọn tập API deprecated của Java 17 để đối chiếu khi quét binary.

Nếu công cụ cài đặt không hỗ trợ release cần kiểm tra, hãy dùng phiên bản JDK có hỗ trợ release đó hoặc kiểm tra danh sách bằng `jdeprscan --help`.

## 7. Chỉ tìm API deprecated for removal

Một số API được đánh dấu không chỉ deprecated mà còn *for removal*. Điều này cho biết API có thể bị loại bỏ trong một release tương lai.

Ví dụ trong mã nguồn:

```java
@Deprecated(since = "1.2", forRemoval = true)
public void oldOperation() {
    // ...
}
```

Tùy chọn `--for-removal` giới hạn kết quả quét hoặc danh sách API ở những API được đánh dấu for removal trong tập API đang xét.

Quét JAR:

```bash
jdeprscan --for-removal app.jar
```

Kết hợp với release cụ thể:

```bash
jdeprscan --release 24 --for-removal app.jar
```

Liệt kê các API for removal:

```bash
jdeprscan --for-removal --list
```

Lưu ý:

- `--for-removal` lọc kết quả; nó không có nghĩa là công cụ tự xóa API khỏi JAR.
- Trạng thái for removal phụ thuộc release được chọn.
- Một API có thể deprecated trong release cũ nhưng chỉ được đánh dấu for removal ở release mới hơn.
- Một số release cũ không hỗ trợ kết hợp với `--for-removal`; xem `jdeprscan --help` để biết giới hạn của phiên bản đang dùng.

Khi lập kế hoạch nâng JDK, nên ưu tiên xử lý các kết quả for removal vì chúng thể hiện rủi ro tương thích cao hơn.

## 8. Liệt kê danh sách API deprecated bằng --list

Tùy chọn `--list` hiển thị tập API deprecated mà công cụ biết theo release được chọn. Đây là chế độ liệt kê, không phải chế độ quét JAR.

Liệt kê theo JDK hiện tại:

```bash
jdeprscan --list
```

Liệt kê theo Java 17:

```bash
jdeprscan --release 17 --list
```

Chỉ liệt kê API for removal:

```bash
jdeprscan --for-removal --list
```

Có thể dùng lệnh này để:

- Tra cứu API deprecated trong một release.
- Kiểm tra một API có thuộc danh sách deprecated hay không.
- Xác định API nào được đánh dấu for removal.
- Hiểu vì sao kết quả quét thay đổi khi đổi `--release`.

Không truyền JAR, class hoặc thư mục đích khi dùng `--list`; chế độ này chỉ in danh sách API, không quét artifact.

## 9. Quét thư mục class và class file riêng lẻ

Ngoài JAR, có thể quét thư mục chứa class file:

```bash
jdeprscan --release 17 out
```

Công cụ xử lý các class trong cây thư mục package bên dưới thư mục được chỉ định.

Có thể chỉ định một class file:

```bash
jdeprscan --release 17 out/com/example/audit/LegacyApiUse.class
```

Hoặc tên lớp đầy đủ:

```bash
jdeprscan --release 17 com.example.audit.LegacyApiUse
```

Với lớp lồng nhau, tên lớp dùng dấu `$` để phân cách, ví dụ:

```bash
jdeprscan 'com.example.Outer$Inner'
```

Đặt tên chứa `$` trong dấu nháy để shell không diễn giải ký tự này như biến.

Quét thư mục class hữu ích khi muốn kiểm tra output của compiler trước khi đóng gói JAR. Quét JAR hữu ích khi muốn kiểm tra chính artifact sẽ được phát hành.

## 10. Phân giải dependency bằng --class-path

Khi class được quét tham chiếu đến các kiểu khác, `jdeprscan` có thể cần tìm những class phụ thuộc để phân giải tham chiếu. Dùng `--class-path` để cung cấp vị trí JAR hoặc thư mục dependency.

Ví dụ:

```text
project/
  app.jar
  lib/
    helper.jar
    common.jar
```

Quét JAR ứng dụng và cung cấp dependency:

```bash
jdeprscan --release 17 --class-path "lib/helper.jar;lib/common.jar" app.jar
```

Trên Windows, classpath dùng dấu chấm phẩy:

```powershell
jdeprscan --release 17 --class-path "lib\helper.jar;lib\common.jar" app.jar
```

Trên macOS/Linux, classpath dùng dấu hai chấm:

```bash
jdeprscan --release 17 --class-path "lib/helper.jar:lib/common.jar" app.jar
```

`--class-path` cung cấp dependency để phân giải kiểu. Nó không có nghĩa là tất cả JAR trên classpath đều tự động trở thành mục tiêu quét. Nếu muốn kiểm tra deprecated API trong `helper.jar`, hãy truyền JAR đó như một đối số quét riêng:

```bash
jdeprscan --release 17 --class-path "lib/common.jar" app.jar lib/helper.jar
```

## 11. Các tùy chọn thường dùng

| Tùy chọn | Công dụng |
| --- | --- |
| `--release <release>` | Chọn phiên bản Java SE cung cấp tập API deprecated để đối chiếu |
| `--for-removal` | Chỉ quét hoặc liệt kê API deprecated for removal |
| `--class-path <path>` | Cung cấp đường dẫn tìm dependency để phân giải class |
| `--list` hoặc `-l` | Liệt kê API deprecated, không quét target |
| `--verbose` hoặc `-v` | Hiển thị thông tin xử lý chi tiết |
| `--version` | In phiên bản ngắn của công cụ |
| `--full-version` | In đầy đủ chuỗi phiên bản |
| `--help` hoặc `-h` | Hiển thị trợ giúp |

Ví dụ kết hợp:

```bash
jdeprscan --release 17 --for-removal --verbose --class-path "lib/helper.jar" app.jar
```

Lệnh trên kiểm tra các API for removal theo Java 17, bật thông tin chi tiết và cung cấp dependency để phân giải.

## 12. Đọc và xử lý kết quả quét

Kết quả của `jdeprscan` thường chỉ ra:

- Class trong artifact có sử dụng API deprecated.
- Loại thành viên được sử dụng, chẳng hạn method hoặc field.
- Tên class/package sở hữu API deprecated.
- Tên method/field và descriptor JVM nếu có.

Ví dụ minh họa:

```text
class com/example/audit/LegacyApiUse uses deprecated method java/util/Date.getYear()I
```

Có thể đọc kết quả như sau:

- `com/example/audit/LegacyApiUse`: class trong JAR có lời gọi cần xem xét.
- `java/util/Date`: class thuộc JDK sở hữu API.
- `getYear()`: method deprecated.
- `I`: descriptor JVM cho biết method trả về `int`.

Khi phát hiện một kết quả:

1. Xác định class trong artifact đang gọi API.
2. Tìm mã nguồn tương ứng nếu có.
3. Đọc tài liệu API của release đang dùng để hiểu lý do deprecated.
4. Kiểm tra API thay thế được đề xuất.
5. Sửa mã nguồn hoặc nâng dependency.
6. Build lại JAR.
7. Quét lại bằng cùng release để so sánh kết quả.

`jdeprscan` phát hiện vị trí tham chiếu nhưng không tự chọn replacement API phù hợp với nghiệp vụ. Việc thay thế cần xét hành vi, timezone, nullability, hiệu năng và tương thích của ứng dụng.

## 13. Ví dụ thay API deprecated

Trong ví dụ trước, `Date.getYear()` trả về số năm tính từ 1900. Với `java.util.Date`, có thể chuyển sang `java.time` để lấy năm theo ngày lịch và timezone được chọn.

Ví dụ:

```java
package com.example.audit;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

public final class ModernDateUse {
    private ModernDateUse() {
    }

    public static int year(Date date) {
        return date.toInstant()
            .atZone(ZoneId.systemDefault())
            .toLocalDate()
            .getYear();
    }

    public static int fixedDateYear() {
        return LocalDate.of(2025, 1, 1).getYear();
    }
}
```

Đoạn mã này dùng `java.time` thay cho `Date.getYear()`. Khi chuyển đổi dữ liệu thời gian, hãy chọn timezone phù hợp với nghiệp vụ; `ZoneId.systemDefault()` phụ thuộc cấu hình máy chạy và có thể không phù hợp với hệ thống cần timezone cố định.

Sau khi thay API, biên dịch lại và tạo JAR mới:

```bash
javac --release 17 -d out src/com/example/audit/ModernDateUse.java
jar --create --file dist/modern-app.jar -C out .
jdeprscan --release 17 dist/modern-app.jar
```

Nếu không còn tham chiếu đến API deprecated trong phần class được quét, công cụ sẽ không báo kết quả tương ứng. Điều này không có nghĩa toàn bộ dependency của ứng dụng đã sạch deprecated API; cần quét các artifact liên quan theo phạm vi mong muốn.

## 14. Những giới hạn cần hiểu

`jdeprscan` là công cụ phân tích tĩnh trên class file. Vì vậy:

- Nó không chạy ứng dụng và không kiểm tra đường đi thực thi ở runtime.
- Nó không thay thế unit test hoặc integration test.
- Nó không tự sửa API deprecated.
- Nó không quét mọi JAR dependency chỉ vì chúng xuất hiện trong `--class-path`; truyền riêng từng artifact cần kiểm tra.
- Nó tập trung vào deprecated API của nền tảng Java/JDK, không phải công cụ kiểm kê mọi API deprecated của thư viện bên thứ ba.
- Các lời gọi được hình thành động qua reflection, tên class/method lấy từ cấu hình hoặc cơ chế nạp lớp động có thể không được nhận diện như tham chiếu bytecode trực tiếp.
- Nếu thiếu dependency để phân giải class, kết quả có thể kèm thông tin không phân giải được; bổ sung classpath phù hợp và xem lại cảnh báo.

Do đó, một lần quét không có kết quả không chứng minh ứng dụng hoàn toàn không có rủi ro khi nâng JDK. Hãy kết hợp kiểm tra binary, mã nguồn, dependency, test và tài liệu migration của JDK.

## 15. Tích hợp quét JAR vào quy trình CI

Có thể thêm `jdeprscan` sau bước build artifact:

1. Build ứng dụng và dependency.
2. Tạo JAR phát hành.
3. Chạy `jdeprscan --release <baseline> app.jar`.
4. Lưu kết quả scan làm artifact/log.
5. Review các API deprecated mới xuất hiện.
6. Quét với `--for-removal` để ưu tiên rủi ro cao.
7. Sửa mã nguồn hoặc cập nhật dependency.
8. Build lại và quét lại trước khi phát hành.

Ví dụ lệnh kiểm tra:

```bash
jdeprscan --release 17 --for-removal app.jar
jdeprscan --release 17 app.jar
```

Không nên giả định mọi kết quả match tự động làm tiến trình `jdeprscan` trả exit code khác 0. Nếu chính sách CI yêu cầu build thất bại khi phát hiện deprecated API, cần kiểm tra output bằng script hoặc dùng thêm `javac -Xlint:deprecation -Werror` ở bước biên dịch source. Hãy phân biệt lỗi của công cụ, lỗi phân giải dependency và kết quả tìm thấy API deprecated.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jdeprscan` không được nhận diện | Chưa cài JDK hoặc `PATH` chưa có thư mục `bin` | Kiểm tra `JAVA_HOME` và `PATH` |
| Không có kết quả dù source có warning | JAR đang quét không chứa class vừa build hoặc tham chiếu không thuộc danh sách API mà tool nhận diện | Kiểm tra đúng artifact bằng `jar --list` và chọn release phù hợp |
| API xuất hiện ở release này nhưng không ở release khác | Trạng thái deprecated thay đổi theo API release | Dùng `--release` phù hợp với baseline cần đánh giá |
| Không phân giải được dependency | Thiếu classpath cần thiết | Bổ sung `--class-path` |
| Quét app.jar nhưng không thấy API trong helper.jar | Dependency không tự động trở thành target được quét | Truyền helper.jar riêng như đối số |
| Muốn tìm API for removal nhưng kết quả quá rộng | Chưa dùng bộ lọc for removal | Thêm `--for-removal` và chọn release phù hợp |
| Dùng `--list` nhưng muốn quét JAR | `--list` chỉ liệt kê danh sách API | Bỏ `--list` và truyền JAR làm target |
| Lệnh báo release không hợp lệ | JDK hiện tại không hỗ trợ release được chọn hoặc tùy chọn kết hợp không hợp lệ | Kiểm tra `jdeprscan --help` |
| Không phát hiện lời gọi qua reflection | Tên API được tạo hoặc nạp động khi chạy | Kiểm tra source/configuration và bổ sung test/runtime analysis |

## 17. Quy trình quét JAR đề xuất

Khi đánh giá một ứng dụng trước khi nâng cấp JDK:

1. Xác định JAR chính và toàn bộ dependency cần kiểm tra.
2. Xác định baseline Java hiện tại và phiên bản JDK dự định nâng lên.
3. Dùng `jdeprscan --release <baseline> app.jar` để lập baseline deprecated API.
4. Quét từng dependency JAR quan trọng; dùng `--class-path` để hỗ trợ phân giải.
5. Dùng `--for-removal` để tìm API có nguy cơ bị loại bỏ.
6. Đối chiếu kết quả với source và tài liệu API của release tương ứng.
7. Thay API deprecated hoặc nâng dependency lên phiên bản đã xử lý.
8. Build lại artifact và quét lại.
9. Bổ sung compiler warning `-Xlint:deprecation` và chính sách `-Werror` cho source build khi phù hợp.
10. Chạy test trên JDK mục tiêu để kiểm tra tương thích thực tế.

Lưu kết quả scan cùng phiên bản JAR, phiên bản JDK và release được chọn để có thể so sánh giữa các lần build.

## 18. Ghi nhớ

- `jdeprscan` quét bytecode trong JAR, class file hoặc thư mục để tìm sử dụng API deprecated của JDK.
- Dùng `jdeprscan app.jar` để quét JAR.
- Dùng `--release` để chọn phiên bản API làm mốc đánh giá.
- Dùng `--for-removal` để tập trung vào API deprecated có kế hoạch loại bỏ.
- Dùng `--list` để xem danh sách API deprecated; chế độ này không quét artifact.
- Dùng `--class-path` để cung cấp dependency cho việc phân giải class.
- Dependency cần được truyền riêng nếu muốn quét chính dependency đó.
- `jdeprscan` không sửa JAR và không thay thế test hoặc kiểm tra runtime.
- Kết hợp quét binary, compiler warning, cập nhật dependency và test trên JDK mục tiêu để giảm rủi ro nâng cấp.

Khi đưa `jdeprscan` vào quy trình kiểm tra artifact, nhóm phát triển có thể phát hiện sớm việc sử dụng API JDK deprecated, ưu tiên các API for removal và chuẩn bị nâng cấp Java có kiểm soát.
