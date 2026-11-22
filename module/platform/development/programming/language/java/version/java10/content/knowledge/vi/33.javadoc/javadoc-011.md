# Kiểm tra kết quả tài liệu bằng công cụ Javadoc đang được hỗ trợ (Java 10+)

## 1. Mục tiêu: tài liệu API “build được” chưa đủ để được phát hành

Khi một thư viện Java công bố API, tài liệu do `javadoc` sinh ra thường là thứ người dùng đọc trước khi gọi phương thức. Một đợt build có thể tạo được HTML, nhưng vẫn còn các lỗi:

- `{@link ...}` trỏ tới type hoặc method không tồn tại;
- `@param` ghi sai tên tham số hoặc bỏ sót `@return`;
- HTML không hợp lệ, thẻ bị lồng sai hoặc thiếu thông tin accessibility;
- tên package/class không xuất hiện trên trang dự kiến;
- liên kết trong bộ HTML bị hỏng sau khi deploy;
- chú thích tiếng Việt bị sai encoding;
- một số API public thiếu mô tả, ví dụ code không còn đúng;
- output chứa file thừa hoặc mã nguồn private bị xuất bản ngoài ý muốn.

**Bài học này hướng dẫn quy trình kiểm chứng tài liệu API thực sự**, không chỉ nhớ cách viết `/** ... */`. Trọng tâm là công cụ `javadoc` hiện hành của JDK, các cờ kiểm tra **DocLint**, `-Werror`, kiểm tra cấu trúc HTML đầu ra, đối chiếu tài liệu với code, rồi đưa các bước đó vào CI/CD.

Bối cảnh: chủ đề cha **Javadoc**, trong module **Java 10**. Javadoc đã có từ trước Java 10 và tiếp tục được hỗ trợ trên JDK mới; không sử dụng công cụ/flag đã lỗi thời chỉ vì xuất hiện trong hướng dẫn cũ.

### Kết luận cần nắm

1. **`javadoc` là công cụ chính thức vẫn được hỗ trợ để tạo API docs từ Java source**, dùng standard doclet mặc định để xuất HTML.
2. **`-Xdoclint:all`** bật đầy đủ nhóm kiểm tra tài liệu, còn **`-Werror`** làm build thất bại khi có warnings.
3. **Exit code = 0** xác nhận lệnh Javadoc hoàn tất theo các quy tắc được bật; nó **không tự chứng minh mọi HTML page, mọi external link hay mọi mô tả nghiệp vụ đều đúng**.
4. Cần thêm **kiểm tra artifacts sau build** (file, trang, anchors, nội dung tiếng Việt, links) và **manual/release review**.
5. Hãy dùng **JDK hiện hành** để chạy tool và `--release` phù hợp với API mục tiêu; `--release 17` không biến layout HTML sinh bởi JDK 24 thành layout của JDK 17.
6. Đặt ngưỡng chất lượng vào **CI gate** trước khi xuất bản lên website hoặc tạo Javadoc JAR.

## 2. Công cụ Javadoc hiện hành gồm những gì?

### 2.1. `javadoc` CLI

Theo tài liệu **Oracle Java SE 27 — The javadoc Command**:

```text
javadoc [options] [packagenames] [sourcefiles] [@files]
```

Công cụ đọc **source declarations và documentation comments**, chuyển chúng vào một **doclet**, trong đó **standard doclet** tạo HTML API documentation.

Các dạng input thường gặp:

- một hoặc nhiều `.java` source files;
- package names hoặc `-subpackages`;
- named modules với `--module-source-path`/`--module` khi phù hợp;
- options từ command-line hoặc file arguments `@options-file`.

Kết quả HTML được ghi vào một **output directory**, thường có `index.html`, các trang class/interface, `package-summary.html`, index/search resources và metadata liên kết.

**Đừng nhầm `javadoc` với `javac`:** `javac` biên dịch source thành class files, còn `javadoc` tạo **documentation artifacts**. Build phát hành nên chạy cả compiler/tests lẫn Javadoc, vì một bước không thay thế hoàn toàn bước kia.

### 2.2. `DocLint`

**DocLint** là hệ thống kiểm tra vấn đề trong Java documentation comments. Nó có thể phát hiện sai tài liệu theo những nhóm:

| Nhóm | Kiểm tra |
| --- | --- |
| `accessibility` | Vấn đề tiếp cận: ảnh thiếu alt, bảng thiếu thông tin phù hợp... |
| `html` | Lồng thẻ HTML sai, cấu trúc markup có vấn đề |
| `missing` | Thiếu comment, `@param`, `@return` hoặc tags cần thiết |
| `reference` | `{@link}`, `@see`, `@param`, `@throws` trỏ/đặt tên sai |
| `syntax` | Cú pháp Javadoc, dấu HTML special characters chưa escape, invalid tags |

Dùng:

```bash
javadoc -Xdoclint:all ...
```

hoặc chọn nhóm:

```bash
javadoc -Xdoclint:html,syntax,reference ...
```

Để bật tất cả trừ một nhóm:

```bash
javadoc -Xdoclint:all,-missing ...
```

**Khuyến nghị kiểm tra chất lượng API public:** giữ `missing` cùng các nhóm còn lại, thay vì bỏ nhóm chỉ để giảm warning count. Nhóm `missing` thường phát hiện những chỗ tài liệu public chưa hoàn chỉnh mà compiler Java không báo.

DocLint đã được bật cho các checks khuyến nghị theo Javadoc hiện hành; **cấu hình `-Xdoclint:all` rõ ràng** giúp CI thể hiện policy nghiêm ngặt và dễ kiểm toán.

### 2.3. `-Werror`

```bash
javadoc -Werror ...
```

Khi có warnings, `-Werror` báo lỗi và làm bước kiểm tra thất bại. Ví dụ method public có `@param` nhưng thiếu `@return` có thể chỉ sinh **warning** trong DocLint `missing`; khi bật `-Werror`, pipeline phải xử lý warning trước khi phát hành.

**Không** kết luận `-Werror` thay thế unit test hoặc external link validation. Nó chỉ đổi cách **các warnings mà Javadoc thực sự phát hiện** ảnh hưởng tới kết quả lệnh.

### 2.4. `-quiet`

```bash
javadoc -quiet ...
```

Giảm các dòng log tiến độ để dễ đọc warning/error. **`-quiet` không phải một cách tắt DocLint**; các warnings/errors vẫn được báo. Khi cần chẩn đoán chi tiết, bỏ `-quiet` hoặc cân nhắc `-verbose`.

### 2.5. `-Xdoclint:none` có nên dùng?

```text
-Xdoclint:none
```

Cờ này **tắt kiểm tra DocLint**, nên có thể làm lỗi documentation đi qua mà không phát hiện. Đây **không phải khuyến nghị** khi mục tiêu là **kiểm tra kết quả tài liệu**.

Nếu một project lớn đang có nhiều warnings cũ, nên tạo kế hoạch sửa theo nhóm, baseline rõ ràng hoặc tách phạm vi cần kiểm tra, thay vì chọn bỏ sạch validation. Với tài liệu API mới, dùng `-Xdoclint:all -Werror` từ đầu là thói quen tốt.

### 2.6. Javadoc tool giúp phát hiện lỗi nhưng không phải bộ kiểm định HTML tổng quát

Oracle mô tả rõ DocLint chỉ phát hiện **các lỗi thường gặp**, không bảo đảm đầy đủ như một HTML conformance validator. Nó cũng không tự xác minh mọi URL tới mạng Internet vẫn sống, và càng không thể xác minh mọi mô tả hiệu năng/nghiệp vụ có đúng hay không.

Vì vậy quy trình đúng phải có nhiều lớp kiểm tra:

```text
source review / javac / unit tests
                  |
        javadoc + DocLint + -Werror
                  |
           generated HTML checks
                  |
        link check + manual preview
                  |
           release/publish gate
```

## 3. Những tùy chọn CLI thiết yếu để kiểm tra kết quả

| Tùy chọn | Tác dụng hiện hành | Lưu ý |
| --- | --- | --- |
| `-d docs/api` | Ghi HTML vào một thư mục đích | Không ghi vào `src` hoặc trộn với Java `.class` |
| `-sourcepath src` | Nơi tìm Java sources theo package | Hữu ích với dự án non-modular |
| `-subpackages dev.lesson.docs` | Duyệt packages bên dưới gốc chỉ định | Phải chọn đúng namespace |
| `--release 17` | Chọn ngữ nghĩa/API của platform release đích | Không thay đổi phiên bản executable `javadoc` |
| `-encoding UTF-8` | Encoding của input source/comments | Tránh hỏng tiếng Việt |
| `-docencoding UTF-8` | Encoding của output HTML | Đồng bộ với input |
| `-Xdoclint:all` | Kiểm tra đầy đủ các nhóm DocLint | Nên bật cho release docs |
| `-Werror` | Coi mọi warning được báo là lỗi của build | Dùng trong CI |
| `-quiet` | Giảm log tiến độ | Không tắt warnings/errors |
| `-public` | Chỉ document các public classes/members | Phù hợp public API release |
| `-protected` | Public + protected (mặc định) | Phù hợp thư viện có protected extension points |
| `-private` | Bao gồm cả members private | Cẩn trọng với tài liệu nội bộ |
| `-link URL` | Tạo links tới docs ngoài, cần metadata có thể truy cập | Có network/caching concerns |
| `-linkoffline URL PATH` | Link ra docs ngoài, dùng metadata local | Hữu ích CI offline |
| `--no-platform-links` | Không tạo links tự động tới platform docs | Dùng để demo/test offline |
| `-linksource` | Tạo trang HTML source code | Có thể làm lộ implementation/private source |
| `-doctitle "..."` | Tiêu đề tài liệu | Chỉ là trình bày |
| `-overview overview.md` | Nội dung trang overview (JDK hiện hành hỗ trợ Markdown) | Phụ thuộc JDK tool version |
| `--version` | In phiên bản công cụ | Kiểm tra đúng JDK |
| `--help`, `--help-extra` | Xem options tại chính JDK đang dùng | Tránh copy flag legacy |

**Phân biệt encoding:** `-encoding` xử lý source input; `-docencoding`/`-charset` liên quan output HTML. Các tùy chọn output cần đồng nhất theo hợp đồng của Javadoc, tránh tạo header khai báo một encoding trong khi bytes được ghi bằng encoding khác. Bài thực hành đặt rõ `UTF-8` cho cả input/output.

### 3.1. Không dùng một số cờ Javadoc cũ như thói quen

Trên JDK hiện hành:

- `-html5` chỉ còn là **no-op** giữ vì tương thích; HTML hiện đại là mặc định.
- `--no-frames` **không còn được hỗ trợ** và có thể sinh warning.
- `-footer` không còn được hỗ trợ như các hướng dẫn rất cũ.
- `-docfilessubdirs` không còn cần thiết cho cách copy `doc-files` hiện hành.

**Không xây CI mới dựa vào những cờ chỉ có ý nghĩa trong Javadoc thời HTML frames**. Luôn chạy `javadoc --help` của toolchain đang được pin, đọc warnings khi nâng JDK.

### 3.2. `--release 17` không đồng nghĩa “chạy công cụ JDK 17”

Giả sử môi trường có **JDK 24** nhưng bạn gắn `--release 17`:

- Javadoc kiểm tra source/API references theo Java 17.
- Output HTML/JS/CSS được sinh bởi **standard doclet của JDK 24**, không phải standard doclet của JDK 17.
- Các thay đổi về HTML structure, search index và style giữa các JDK có thể tồn tại.
- Nếu muốn so snapshot HTML byte-for-byte, cần **pin đúng phiên bản JDK/tool**, không chỉ pin `--release`.

Trong bài, các assertions HTML được xác minh bằng JDK 24.0.2; khi nâng toolchain, hãy điều chỉnh các assertions nhạy cảm với HTML layout khi cần.

## 4. Project thực hành: tạo tài liệu và kiểm tra một public API

Bài có **hai mục tiêu kiểm chứng độc lập**:

1. Một lần chạy Javadoc tốt phải tạo HTML không có DocLint warnings/errors.
2. Một lần chạy Javadoc trên source cố ý có lỗi phải thất bại, chứng minh CI gate thật sự chặn tài liệu lỗi.

Tất cả ví dụ compile/test bằng **Java 17+**, không phụ thuộc network. Các thư mục output nằm ngoài source để dễ xóa/rebuild.

### 4.1. Cấu trúc thư mục

```text
javadoc-lab/
├── src/
│   └── dev/lesson/docs/
│       ├── package-info.java
│       └── InvoiceMath.java
├── DocSiteAudit.java
├── bad/
│   └── dev/lesson/broken/
│       └── BadDocs.java
├── warning/
│   └── dev/lesson/warning/
│       └── WarnDocs.java
├── build/
│   └── classes/
└── docs/
    ├── api/
    ├── bad/
    └── warning/
```

**Các file `bad`/`warning` chỉ dùng cho negative tests**; không publish `docs/bad`/`docs/warning` cùng tài liệu thành công. Đặt chúng ngoài source root `src` để lần Javadoc chính không vô tình duyệt vào những package cố ý sai.

### 4.2. `package-info.java`: mô tả package

Lưu file `src/dev/lesson/docs/package-info.java`:

```java
/**
 * Tài liệu API minh họa cho bài thực hành kiểm chứng Javadoc.
 *
 * <p>Điểm vào: {@link dev.lesson.docs.InvoiceMath}.
 */
package dev.lesson.docs;
```

**Vì sao dùng `package-info.java`?** Đây là vị trí chuẩn để mô tả package trong tài liệu API. Khi chạy Javadoc đúng, bạn có thể mở `dev/lesson/docs/package-summary.html` để thấy phần mô tả package và liên kết tới class.

**Không dùng file `package.html` cũ như lựa chọn mặc định cho project mới**. `package-info.java` tích hợp tốt hơn vào Java source và toolchain đang được hỗ trợ.

### 4.3. `InvoiceMath.java`: API có đủ tags và links

Lưu file `src/dev/lesson/docs/InvoiceMath.java`:

```java
package dev.lesson.docs;

/**
 * Tính tiền đơn giản cho tài liệu API.
 *
 * <p>Ví dụ: {@code InvoiceMath.total(3, 200) == 600}.
 * <p>Xem {@link InvoiceMath#total(int, long)}.
 *
 * @since 1.0
 */
public final class InvoiceMath {
    private InvoiceMath() {
        throw new AssertionError("No instances");
    }

    /**
     * Tính tổng tiền trước thuế.
     *
     * @param quantity số lượng, không được âm
     * @param price giá đơn vị, không được âm
     * @return tích của số lượng và giá
     * @throws IllegalArgumentException nếu quantity hoặc price âm
     * @throws ArithmeticException nếu phép nhân bị tràn long
     */
    public static long total(int quantity, long price) {
        if (quantity < 0 || price < 0) {
            throw new IllegalArgumentException("negative argument");
        }
        return Math.multiplyExact(quantity, price);
    }
}
```

### 4.4. Giải thích các tags trong ví dụ

| Đoạn Javadoc | Vai trò |
| --- | --- |
| `/** ... */` ngay trước class | Documentation comment được tool phân tích |
| `<p>` | Tạo đoạn HTML đúng ngữ nghĩa; đừng lồng sai |
| `{@code ...}` | Hiển thị đoạn code và escape ký tự cần thiết |
| `{@link InvoiceMath#total(int, long)}` | Tạo liên kết tới chính method có signature ấy |
| `@since 1.0` | Ghi mốc version API xuất hiện |
| `@param quantity`, `@param price` | Mô tả đúng tên parameters trong method |
| `@return` | Mô tả kết quả phép tính |
| `@throws IllegalArgumentException` | Mô tả điều kiện đầu vào âm |
| `@throws ArithmeticException` | Mô tả overflow của `Math.multiplyExact` |

**Không chỉ viết tags cho đủ số lượng.** Mô tả phải khớp implementation:

- `quantity` và `price` không được âm, đúng như code.
- `Math.multiplyExact` có thể throw `ArithmeticException` nếu tích vượt giới hạn `long`.
- `InvoiceMath.total(3, 200)` trả `600`.
- Chúng ta không claim decimal money precision/rounding cho phương thức ví dụ. Trong ứng dụng tài chính thật cần định nghĩa đơn vị tiền (ví dụ minor units), cách làm tròn, domain invariants và dùng cấu trúc phù hợp.

### 4.5. Biên dịch Java riêng để kiểm tra code

Trong thư mục `javadoc-lab`:

POSIX shell:

```bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes \
  src/dev/lesson/docs/package-info.java \
  src/dev/lesson/docs/InvoiceMath.java
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/classes
javac --release 17 -encoding UTF-8 -d build/classes src/dev/lesson/docs/package-info.java src/dev/lesson/docs/InvoiceMath.java
```

**Lý do:** kiểm tra code có compile theo target Java 17 trước khi dựng tài liệu. `javadoc` có thể báo lỗi source/reference, nhưng nó **không thay thế compile-time checks và runtime unit tests**.

## 5. Chạy Javadoc nghiêm ngặt cho tài liệu chính

Tại thư mục `javadoc-lab`, trên POSIX:

```bash
javadoc --release 17 \
  -encoding UTF-8 -docencoding UTF-8 \
  -d docs/api -sourcepath src -subpackages dev.lesson.docs \
  -Xdoclint:all -Werror -quiet --no-platform-links -public
```

PowerShell/CMD dùng một dòng:

```powershell
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -d docs/api -sourcepath src -subpackages dev.lesson.docs -Xdoclint:all -Werror -quiet --no-platform-links -public
```

### 5.1. Từng phần của lệnh làm gì?

- `--release 17`: chọn môi trường Java 17 của source/platform APIs.
- `-encoding UTF-8`: đọc comment có dấu tiếng Việt đúng.
- `-docencoding UTF-8`: ghi HTML output đúng Unicode.
- `-d docs/api`: nơi lưu site được tạo.
- `-sourcepath src`: Java package source root.
- `-subpackages dev.lesson.docs`: tạo docs cho package và descendants của namespace đó.
- `-Xdoclint:all`: bật đủ 5 nhóm kiểm tra.
- `-Werror`: warnings thành build failure.
- `-quiet`: giảm progress output, không bỏ warnings/errors.
- `--no-platform-links`: không tạo links tự động ra platform docs, giúp demo chạy ổn định offline.
- `-public`: chỉ public APIs xuất hiện. Constructor private của `InvoiceMath` không được đưa vào API public docs.

**Đừng tự suy rằng `-public` là đúng cho mọi library.** Nếu người dùng cần các protected extension points, dùng mức visibility phù hợp, thường là `-protected` (mặc định), và kiểm tra các API cần công khai.

### 5.2. Kết quả đã kiểm thử trên OpenJDK 24.0.2

Với hai Java source ở trên:

```text
javadoc exit code = 0
```

Khi dùng `-quiet`, lệnh thành công có thể không in progress output. **Không chép một console transcript cố định của Javadoc** vì các đường dẫn, số dòng, locale và JDK version làm warnings/diagnostics khác nhau.

Thay vào đó, kiểm tra:

1. Exit code **0**.
2. Không có warning/error bị bỏ qua.
3. Thư mục `docs/api` có những HTML artifacts bắt buộc.
4. Trang class chứa nội dung và liên kết cần thiết.
5. Không xuất bản output từ các negative tests.
6. Chạy review trực quan và link checks trước release.

### 5.3. Những file chính được tạo

Trong bài đã kiểm thử, tồn tại:

```text
docs/api/index.html
docs/api/dev/lesson/docs/package-summary.html
docs/api/dev/lesson/docs/InvoiceMath.html
docs/api/index-all.html
docs/api/element-list
docs/api/search.html
```

Có thêm CSS, scripts, assets và các index khác do Javadoc sinh. **Không lập danh sách cứng mọi file output cho mọi JDK**: việc tạo thêm/bớt tài nguyên thay đổi theo standard doclet version và options.

### 5.4. Kiểm tra trang Javadoc không chỉ kiểm tra file có tồn tại

Một file `InvoiceMath.html` có thể có thật nhưng thiếu chữ tiếng Việt, thiếu method summary hoặc local link sai. Vì vậy phần tiếp theo viết một **Java 17+ audit program** để đọc HTML và xác minh những điểm quan trọng.

## 6. Chương trình Java 17+ kiểm tra HTML được sinh

Lưu file `DocSiteAudit.java` ở gốc project:

```java
import dev.lesson.docs.InvoiceMath;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class DocSiteAudit {
    public static void main(String[] args) throws Exception {
        Path site = Path.of("docs/api");
        Path packagePage = site.resolve("dev/lesson/docs/package-summary.html");
        Path classPage = site.resolve("dev/lesson/docs/InvoiceMath.html");

        String classHtml = Files.readString(classPage, StandardCharsets.UTF_8);
        String packageHtml = Files.readString(packagePage, StandardCharsets.UTF_8);
        String lowerHtml = classHtml.toLowerCase(Locale.ROOT);

        System.out.println("indexExists=" +
                Files.isRegularFile(site.resolve("index.html")));
        System.out.println("packagePageExists=" + Files.isRegularFile(packagePage));
        System.out.println("classPageExists=" + Files.isRegularFile(classPage));
        System.out.println("indexAllExists=" +
                Files.isRegularFile(site.resolve("index-all.html")));
        System.out.println("elementListExists=" +
                Files.isRegularFile(site.resolve("element-list")));
        System.out.println("searchPageExists=" +
                Files.isRegularFile(site.resolve("search.html")));
        System.out.println("utf8Charset=" +
                lowerHtml.contains("charset=utf-8"));
        System.out.println("vietnameseText=" +
                classHtml.contains("Tính tổng tiền trước thuế."));
        System.out.println("methodAnchorExists=" +
                classHtml.contains("id=\"total(int,long)\""));
        System.out.println("localMethodLinkExists=" +
                classHtml.contains("href=\"#total(int,long)\""));
        System.out.println("packageLinksClass=" +
                packageHtml.contains("InvoiceMath.html"));
        System.out.println("exampleMatchesImplementation=" +
                (InvoiceMath.total(3, 200) == 600));
    }
}
```

### 6.1. Biên dịch/chạy audit

Sau khi đã chạy cả `javac` và `javadoc` ở trên:

```bash
javac --release 17 -encoding UTF-8 \
  -cp build/classes -d build/classes DocSiteAudit.java
java -cp build/classes DocSiteAudit
```

PowerShell/CMD:

```powershell
javac --release 17 -encoding UTF-8 -cp build/classes -d build/classes DocSiteAudit.java
java -cp build/classes DocSiteAudit
```

**Stdout chính xác trên OpenJDK 24.0.2 với bộ HTML sinh từ lệnh phần 5:**

```text
indexExists=true
packagePageExists=true
classPageExists=true
indexAllExists=true
elementListExists=true
searchPageExists=true
utf8Charset=true
vietnameseText=true
methodAnchorExists=true
localMethodLinkExists=true
packageLinksClass=true
exampleMatchesImplementation=true
```

Đây là **output từ source và generated HTML của lab đã kiểm chứng**, không phải dự đoán tất cả site Javadoc. Các assertions kiểm tra chuỗi HTML như `id="total(int,long)"` phụ thuộc cấu trúc output của JDK 24; Javadoc ở JDK khác có thể đổi markup trong khi site vẫn đúng về chức năng. Sau khi nâng JDK, điều chỉnh HTML assertions có chủ đích thay vì mặc định cho rằng JDK mới sinh lỗi.

### 6.2. Mỗi assertion chứng minh được điều gì?

| Assert | Kiểm tra |
| --- | --- |
| `indexExists` | Có entry page |
| `packagePageExists` | Có trang package tương ứng |
| `classPageExists` | Class public được sinh thành HTML |
| `indexAllExists` | Có trang chỉ mục API |
| `elementListExists` | Có metadata phục vụ cross-document links |
| `searchPageExists` | Có trang search của standard doclet trong JDK test |
| `utf8Charset` | HTML có khai báo UTF-8 theo format của JDK test |
| `vietnameseText` | Nội dung mô tả có dấu tiếng Việt không bị mất |
| `methodAnchorExists` | Có anchor cho method `total(int,long)` |
| `localMethodLinkExists` | Có link nội bộ trỏ tới method |
| `packageLinksClass` | Trang package nhắc và liên kết tới class |
| `exampleMatchesImplementation` | Một ví dụ trong docs phù hợp code thật |

### 6.3. Giới hạn của audit

Chương trình **không**:

- parse/validate toàn bộ HTML theo HTML Living Standard;
- đánh giá chuẩn WCAG về accessibility;
- click/resolve mọi relative URL trong site;
- gọi HTTP để phát hiện external 404, redirect hoặc TLS errors;
- so tất cả docs với unit tests và behavior của mọi method;
- kiểm tra security của script/CSS assets hoặc nội dung do người viết cố ý nhúng.

Đây là **kiểm thử tối thiểu có giá trị học tập**, cần kết hợp thêm tools phù hợp trước khi publish library thật. Nếu muốn hard-fail CI khi một assertion false, thay `System.out.println` bằng logic ném `AssertionError` hoặc exit code nonzero tương ứng, không chỉ in bảng boolean rồi mặc nhiên coi test đã pass.

**Một điểm rất quan trọng:** phiên bản `DocSiteAudit` hiện tại in `true/false` và sẽ ném exception khi thiếu file đã đọc, nhưng **không tự ném lỗi khi một assertion ra false**. Vì vậy CI cần có lớp assert riêng hoặc kiểm tra stdout để thực sự fail khi kết quả sai; không nhầm “stdout có false” với “process exit nonzero”. Mục 11 mô tả cách biến điều đó thành release gate.

## 7. Negative tests: chứng minh DocLint và `-Werror` thực sự phát hiện lỗi

Bộ test chỉ tốt nếu nó **fail đúng lúc**. Sau khi có một site hợp lệ, tạo riêng hai trường hợp lỗi để xác minh các flags đang thực sự hoạt động.

### 7.1. Lỗi liên kết không tồn tại

Lưu file `bad/dev/lesson/broken/BadDocs.java`:

```java
package dev.lesson.broken;

/**
 * Ví dụ hỏng: {@link TypeThatDoesNotExist}.
 */
public final class BadDocs {
    /**
     * Phương thức có tham số mô tả không tồn tại.
     * @param absent tên tham số không có trong chữ ký
     */
    public void ping() {}
}
```

Chạy:

```bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 \
  -d docs/bad -sourcepath bad -subpackages dev.lesson.broken \
  -Xdoclint:all -Werror -quiet --no-platform-links -public
```

**Kết quả quan sát trên OpenJDK 24.0.2:**

```text
Exit code: 1 (nonzero)
Có thông báo: reference not found
```

Có thể kèm những chẩn đoán khác, chẳng hạn `@param absent` không khớp method `ping()`. Đường dẫn/line number của error thay đổi theo thư mục và compiler locale; **không copy một stacktrace “chính xác” vào tài liệu**.

Đây là lỗi thuộc nhóm **`reference`**: link không resolve được đến type trong phạm vi nguồn/classpath/module path.

### 7.2. Missing `@return`: warning thành build failure

Lưu file `warning/dev/lesson/warning/WarnDocs.java`:

```java
package dev.lesson.warning;

/** Lớp cố tình thiếu chú thích để thử cảnh báo. */
public final class WarnDocs {
    /**
     * Nhân đôi một giá trị.
     * @param value giá trị đầu vào
     */
    public static int twice(int value) {
        return value * 2;
    }
}
```

Chạy:

```bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 \
  -d docs/warning -sourcepath warning -subpackages dev.lesson.warning \
  -Xdoclint:all -Werror -quiet --no-platform-links -public
```

**Kết quả quan sát trên OpenJDK 24.0.2:**

```text
Exit code: 1 (nonzero)
Có thông báo: no @return
```

Vì method `twice` trả `int` nhưng Javadoc không có `@return`, nhóm `missing` phát hiện warning. `-Werror` khiến lệnh thất bại.

**Sửa đúng:** thêm `@return` mô tả giá trị thực sự trả về, không bỏ `-Werror` hoặc tắt `missing` một cách vội vã.

### 7.3. Vì sao không xuất bản các trang từ negative tests?

Khi Javadoc gặp lỗi, output directory có thể đã được tạo ra **một phần**. Một CI pipeline không được publish chỉ vì thư mục `docs/bad` hay `docs/warning` tồn tại; phải dùng **exit status** và chỉ đưa artifacts của job thành công qua publish stage.

Bởi vậy các negative tests luôn ghi vào thư mục tách biệt với `docs/api`.

### 7.4. Bảng hành vi đã được kiểm thử

| Đầu vào | Kiểm tra | Kết quả |
| --- | --- | --- |
| `src/dev/lesson/docs` hợp lệ | `-Xdoclint:all -Werror` | Exit **0**, sinh trang API |
| `BadDocs` có broken `{@link}` | `-Xdoclint:all -Werror` | Exit **1**, `reference not found` |
| `WarnDocs` thiếu `@return` | `-Xdoclint:all -Werror` | Exit **1**, `no @return` |

Một JDK khác có thể dùng exit code nonzero khác hoặc wording diagnostics khác, nhưng mục tiêu kiểm thử là **good exit 0 / bad exit nonzero**, không phải hard-code một mã lỗi duy nhất.

## 8. Xác minh nội dung trang HTML bằng mắt và máy

### 8.1. Mở đúng output site

Sau khi Javadoc chạy thành công, mở:

```text
docs/api/index.html
docs/api/dev/lesson/docs/package-summary.html
docs/api/dev/lesson/docs/InvoiceMath.html
```

Một đợt review cần xem:

- title của trang có đúng tên thư viện/package không;
- navigation sidebar/index/search có hoạt động;
- chữ tiếng Việt có hiển thị đúng dấu;
- method `total` có đầy đủ description, parameters, return, throws;
- link trong `{@link InvoiceMath#total(int,long)}` mở đúng method;
- có để lọt internal API hoặc thông tin nhạy cảm ra public docs không;
- CSS, icon, search assets tải đủ khi site được host ở URL thực;
- không có duplicate package pages từ quá trình copy artifacts cũ.

**Lưu ý:** một số tính năng search/JS có thể hoạt động khác khi mở `file://` so với khi được host trên một web server. Khi release, nên kiểm tra ở môi trường tương tự cách site sẽ được phục vụ.

### 8.2. Kiểm tra local links tự động

Một link checker có thể duyệt tất cả `href`/`src` trong HTML để xem relative targets có tồn tại và anchor IDs có khớp. Tuy nhiên, cần:

- chuẩn hóa các đường dẫn tương đối từ vị trí file chứa link;
- bỏ fragment trước khi tìm file, sau đó kiểm tra `id`/anchor;
- xử lý URL encoding đúng;
- nhận biết các querystrings do search/navigation dùng;
- phân biệt `mailto:`, `https:`, `javascript:` và fragment-only links;
- không coi một URL ngoài lỗi tạm thời là chứng cứ bị phá hủy source docs ngay lập tức.

Bài lab chỉ kiểm tra vài links trọng điểm bằng `DocSiteAudit`. Với dự án lớn, dùng link validator được duy trì và phiên bản được pin trong CI.

### 8.3. Kiểm tra external links có chính sách rõ

`-link URL` liên kết tới bộ docs bên ngoài và có thể cần lấy `element-list`/`package-list` tại build time. Một CI offline hoặc mạng thiếu ổn định có thể fail khi link metadata không thể tải.

`-linkoffline URL LOCAL_DOCS` cho phép cung cấp metadata tại đường dẫn local, nhưng cần bảo đảm base URL và metadata **đúng version của API**.

Cả hai cơ chế **không tự bảo đảm** mọi trang trên Internet sẽ tồn tại mãi. Một bộ link-checking độc lập nên có:

- timeout/retry giới hạn;
- allowlist hoặc policy với các domains đáng tin;
- cache/metadata pinning khi có thể;
- report lỗi rõ từng URL;
- exception có expiry nếu external site tạm thời chặn requests;
- không tự động “sửa” URL sang một site không kiểm soát.

### 8.4. Javadoc có search/index nhưng search không chứng minh coverage

Có trang `search.html` hoặc index metadata không tự bảo đảm mọi public API đã được document. Nguyên nhân có thể:

- `-subpackages` bỏ sót một namespace;
- `-public` ẩn các protected extension points cần được mô tả;
- module/package không được export/chọn vào phạm vi;
- source root bị truyền sai;
- `@hidden` có chủ đích loại phần tử khỏi docs;
- build lấy sai nhánh code hoặc source generated khác release artifact.

Vì vậy, ngoài kiểm tra files, phải **đối chiếu danh sách API thực tế** trong JAR/class/module với scope đã xuất bản. Có thể dùng `javap -public`, build metadata hoặc một ABI-report tool để kiểm tra không bỏ sót các public APIs quan trọng.

## 9. Dùng `javadoc -Xdoclint` đúng mức chặt

### 9.1. Sửa lỗi tại nguồn thay vì dập cảnh báo

Một số tình huống:

| Vấn đề | Cách sửa |
| --- | --- |
| `@param count` nhưng tham số Java tên `quantity` | Sửa tag khớp parameter |
| Method non-void thiếu `@return` | Viết rõ kết quả/đơn vị/giới hạn |
| `{@link UnknownType}` | Sửa type name, import/package, classpath/module path |
| `@throws` mô tả exception sai | Kiểm tra API contract và exception thật |
| Dùng `<`/`>` thô trong comment | Dùng `{@code ...}` hoặc escape HTML phù hợp |
| Table/ảnh thiếu accessibility metadata | Bổ sung caption/alt theo ngữ nghĩa |
| Link external bị 404 | Sửa URL đúng version, kiểm tra nguồn chính thức |
| Tài liệu API dịch sai | Sửa comment/source, review kỹ thuật/biên tập |
| Sai charset tiếng Việt | Đồng bộ encoding đầu vào/HTML output |
| Thiếu public class docs | Kiểm tra comment, visibility, scope/source path |

**Không coi mọi DocLint warning là “false positive”.** Trước khi suppress, xác nhận nguyên nhân thực và phạm vi tác động.

### 9.2. `@SuppressWarnings` chỉ nên dùng có lý do

Javadoc hiện hành có thể hiểu các suppression names như:

```java
@SuppressWarnings("doclint:missing")
```

Điều này có thể suppress một nhóm vấn đề trên declaration và các phần lexical bên trong, nhưng cũng làm người dùng **không còn thấy warning thực**. Chỉ dùng khi có policy rõ và vấn đề thật sự không áp dụng được; không dùng một `@SuppressWarnings("doclint")` trên package/module để “xóa sạch” nợ tài liệu.

Đối với public API mới, một quy tắc tốt hơn là **viết đầy đủ docs** thay vì dập cảnh báo.

### 9.3. Thứ tự sửa lỗi có ích

1. **Reference/syntax errors** để javadoc chạy và links hợp lệ.
2. **HTML/accessibility** để output tiêu chuẩn và đọc được.
3. **Missing comments/param/return/throws** để public API đầy đủ.
4. **Semantic review** để docs đúng implementation và expected behavior.
5. **External link/site review** trước xuất bản.

Không có lý do kỹ thuật để dừng ở bước 1 và tuyên bố docs “đạt chất lượng production” khi các bước còn lại chưa làm.

## 10. Quality gate trong CI/CD

### 10.1. Điều kiện pass đề xuất

Một release job chỉ được publish API docs khi:

- compiler/tests cho source tương ứng thành công;
- `javadoc -Xdoclint:all -Werror` trả exit code **0**;
- các artifacts bắt buộc tồn tại và không rỗng;
- `DocSiteAudit`/HTML-link checker được cấu hình **fail nếu assertion sai**;
- documentation scope đúng release public API;
- external links được kiểm tra theo policy;
- site preview/acceptance review xong nếu dự án yêu cầu.

**Không** coi “thư mục docs có HTML” là success nếu lệnh Javadoc trả nonzero.

### 10.2. POSIX shell

```bash
set -euo pipefail

mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes \
  src/dev/lesson/docs/package-info.java \
  src/dev/lesson/docs/InvoiceMath.java

javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 \
  -d docs/api -sourcepath src -subpackages dev.lesson.docs \
  -Xdoclint:all -Werror -quiet --no-platform-links -public

javac --release 17 -encoding UTF-8 \
  -cp build/classes -d build/classes DocSiteAudit.java
java -cp build/classes DocSiteAudit
```

**Quan trọng:** bản `DocSiteAudit` in booleans; `set -e` chỉ kiểm soát exit status. Trong CI thật cần **assert boolean values hoặc biến script kiểm tra output thành nonzero** nếu có `false`. Không coi script mẫu trên là gate hoàn chỉnh cho custom HTML assertions cho đến khi thêm bước đó.

### 10.3. PowerShell

```powershell
New-Item -ItemType Directory -Force -Path build/classes

javac --release 17 -encoding UTF-8 -d build/classes src/dev/lesson/docs/package-info.java src/dev/lesson/docs/InvoiceMath.java
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -d docs/api -sourcepath src -subpackages dev.lesson.docs -Xdoclint:all -Werror -quiet --no-platform-links -public
if ($LASTEXITCODE -ne 0) { throw "Javadoc failed" }

javac --release 17 -encoding UTF-8 -cp build/classes -d build/classes DocSiteAudit.java
if ($LASTEXITCODE -ne 0) { throw "Audit compilation failed" }

java -cp build/classes DocSiteAudit
if ($LASTEXITCODE -ne 0) { throw "Audit runtime failed" }
```

Tương tự, cần bổ sung assertion gate cho từng boolean trong audit thay vì chỉ in chúng; trong các JDK PowerShell/native stderr combinations, cách trình bày diagnostics có thể khác nhưng `$LASTEXITCODE` mới là dấu hiệu lệnh native thất bại.

### 10.4. Để audit thực sự làm CI fail

Thay vì chỉ:

```java
System.out.println("classPageExists=" + Files.isRegularFile(classPage));
```

có thể viết:

```java
if (!Files.isRegularFile(classPage)) {
    throw new AssertionError("Missing Javadoc class page: " + classPage);
}
```

Đây là đoạn code **minh họa**, không thay đổi chương trình `DocSiteAudit` ở phần 6. Khi có assertion sai, JVM thoát nonzero, CI sẽ không publish site.

**Cách tổng quát:** một test framework như JUnit cũng có thể cung cấp `assertTrue`/`assertEquals` và báo test failure rõ ràng; nhưng chương trình Java 17+ trong bài chỉ dùng JDK API để chạy độc lập.

### 10.5. Không phát hành site “nửa cũ nửa mới”

Khi build docs vào cùng một output directory tồn tại từ release trước, các file HTML cũ có thể còn lại nếu standard doclet không xóa những file không còn thuộc source. Để kiểm chứng chính xác:

- sinh vào **directory mới hoặc đã dọn sạch**;
- chạy DocLint/audit;
- chỉ publish sau khi toàn bộ job pass;
- đưa nguyên thư mục output đã xác minh lên site theo **atomic deploy/replace** nếu có thể.

Không xóa/sửa dữ liệu production bừa bãi; việc dọn output chỉ thuộc build workspace. Đừng trộn docs của hai JDK/source versions rồi kiểm tra thiếu sót sau.

## 11. Kiểm tra API behavior, không chỉ HTML

Tài liệu API tốt cần phản ánh đúng behavior mà người dùng dựa vào:

- `@param` đúng đơn vị và điều kiện input;
- `@return` đúng giá trị và trường hợp biên;
- `@throws` đúng điều kiện lỗi;
- thread-safety/immutability/nullability được mô tả nếu quan trọng;
- `@since` đúng release;
- deprecated APIs được mô tả và có hướng thay thế;
- examples thực sự compile/run khi cần.

Trong demo:

```java
InvoiceMath.total(3, 200) == 600
```

đã được chạy bằng Java code từ `DocSiteAudit`. Nhưng một example đơn giản **không chứng minh mọi case**. Unit tests cho:

- `quantity=0`;
- input âm;
- overflow của `Math.multiplyExact`;
- cực trị `int/long`;

cần được thêm khi library tiến tới production.

### 11.1. Test Javadoc và test ứng dụng hỗ trợ lẫn nhau

Unit tests không tìm được tất cả links hỏng trong HTML; DocLint không xác minh đầy đủ tất cả branch behavior của code. Dùng cả hai để bắt hai loại lỗi **khác nhau**.

Một tác giả có thể viết `@return always positive` trong khi code có thể trả 0; Javadoc vẫn chạy pass nếu tags và syntax đúng. Đây là **semantic bug của tài liệu**, cần review/test chứ không thể trông chờ DocLint.

### 11.2. Semantic versioning và docs

Nếu public method đổi signature hoặc behavior, phải cập nhật:

- Javadoc comments và `@throws`;
- examples;
- links/anchors đến method bị đổi;
- migration notes;
- API compatibility policy;
- generated docs site và tests.

Không để docs mô tả method phiên bản mới nhưng link tới package index của phiên bản cũ. Đặt version tag trên site hoặc triển khai docs theo từng version nếu có nhiều bản được hỗ trợ.

## 12. Modular projects và API visibility

Ví dụ dùng **classpath/non-modular source**, nhưng một project thật có thể dùng Java Platform Module System (JPMS).

Với named modules, `javadoc` có tùy chọn:

- `--module-source-path`;
- `--module`;
- `--module-path`;
- `--show-module-contents`;
- `--show-packages`;
- `--show-types` và `--show-members`.

**Không lấy y nguyên `-sourcepath src -subpackages...` của lab để áp lên mọi multi-module build.** Phải xác nhận module descriptors, exported packages và visibility policy, rồi kiểm tra generated module index/pages tương ứng.

### 12.1. Public vs protected vs private

`-public` tài liệu hóa public APIs; `-protected` (mặc định) bao gồm public và protected. Nếu thư viện được thiết kế cho subclassing, protected extension hooks có thể rất quan trọng; chọn `-protected` khi đó thay vì `-public`.

`-private` có thể dùng cho **internal docs**, nhưng không nên publish lên website công khai nếu chứa thiết kế nội bộ hoặc thông tin nhạy cảm.

### 12.2. `-linksource` có thể phơi bày private source

Theo tài liệu Javadoc hiện hành, `-linksource` tạo HTML cho **source files** và có thể hiển thị cả private implementation details, **ngay cả khi public API docs không liệt kê private members**.

Vì vậy:

- Không bật `-linksource` mù quáng khi sinh docs public cho mã độc quyền.
- Review output thật trước khi publish.
- Không để keys, tokens hoặc dữ liệu nhạy cảm trong source/comments.
- Phân biệt docs công khai và docs kỹ thuật chỉ dùng nội bộ.

### 12.3. Modern Javadoc comments

Các khả năng hiện hành gồm `{@link}`, `{@code}`, `{@summary}` và với JDK có hỗ trợ **`{@snippet}`** (được đưa vào từ JDK 18). Nếu project biên soạn bằng JDK 17, **không copy các tags của JDK mới mà chưa kiểm tra hỗ trợ**.

Bài dùng `{@code}` và `{@link}` để chạy trên `--release 17` và kiểm thử bằng JDK 24. Không dùng những cơ chế Javadoc HTML4/frames đã bị gỡ.

## 13. Lỗi phổ biến khi kiểm chứng Javadoc

**Lỗi 1 — “Lệnh tạo HTML không ném exception nên docs hoàn chỉnh.”**  
Sai. Cần DocLint warnings, exit code, nội dung output, links và review.

**Lỗi 2 — “`-quiet` tắt tất cả cảnh báo.”**  
Sai. Nó chủ yếu giảm log tiến độ.

**Lỗi 3 — “`-Werror` kiểm tra link trên Internet.”**  
Sai. Nó nâng mức severity của warnings được Javadoc phát hiện, không phải web crawler.

**Lỗi 4 — “`-Xdoclint:none` giúp tài liệu sạch lỗi.”**  
Sai. Nó tắt kiểm tra, không sửa nguồn lỗi.

**Lỗi 5 — “`-Xdoclint:all` là HTML validator đầy đủ.”**  
Sai. DocLint chỉ bắt những lỗi thường gặp.

**Lỗi 6 — “Chỉ cần nhìn `index.html`.”**  
Sai. Có thể thiếu class/package pages hoặc method links.

**Lỗi 7 — “Một broken `{@link}` chỉ gây warning không cần sửa.”**  
Không đúng trong nhiều trường hợp; DocLint reference issues thường gây error và CI strict phải fail.

**Lỗi 8 — “Method non-void không cần `@return` nếu Java code compile.”**  
Không đúng cho API documentation quality. DocLint `missing` có thể cảnh báo.

**Lỗi 9 — “`--release 17` chạy standard doclet của JDK 17.”**  
Sai. Nó chọn target platform/source semantics, còn HTML generator là JDK tool đang chạy.

**Lỗi 10 — “DocLint không thấy lỗi thì links external đều hoạt động.”**  
Sai. Cần link checking độc lập.

**Lỗi 11 — “`-public` luôn xuất mọi API quan trọng.”**  
Không phải cho thư viện có protected extension points.

**Lỗi 12 — “Có file `search.html` nghĩa mọi class đều hiện trong docs.”**  
Sai. Còn source scope, module exports và visibility.

**Lỗi 13 — “Thêm `-linksource` vô hại với private code.”**  
Sai. Nó có thể xuất bản source code của private implementation.

**Lỗi 14 — “Javadoc command là compiler Java hoàn chỉnh.”**  
Sai. Vẫn cần compile unit tests và runtime/behavior tests.

**Lỗi 15 — “Thư mục docs/bad tồn tại thì negative test đã pass.”**  
Sai. Negative test đúng phải kiểm tra **nonzero exit code**.

**Lỗi 16 — “Có stdout `foo=false` nhưng Java process exit 0 là CI đã fail.”**  
Sai. Phải ném assertion hoặc cho CI parse output và trả nonzero.

**Lỗi 17 — “HTML string assertions bền vững qua mọi JDK.”**  
Không. Markup/layout có thể thay đổi khi standard doclet cập nhật; test theo user-facing semantics khi có thể.

**Lỗi 18 — “HTML chưa lỗi trên máy dev thì publish lên CDN chắc chắn ổn.”**  
Sai. Relative paths, URL base, caching, JS/CSS và hosting config có thể gây lỗi khi deploy.

**Lỗi 19 — “Đổi encoding output là đủ nếu source tiếng Việt đang đọc sai.”**  
Sai. Phải cấu hình đúng input `-encoding` trước.

**Lỗi 20 — “Có warning trong Javadoc thì bỏ `-Werror` để release nhanh hơn.”**  
Sai. Nên sửa nguồn hoặc áp policy ngoại lệ có phê duyệt và thời hạn, không hạ chất lượng mặc định.

**Lỗi 21 — “`-html5` cần bật để JDK 27 sinh HTML5.”**  
Không. Javadoc hiện hành coi nó là no-op tương thích.

**Lỗi 22 — “Publish docs/API mà không cần chốt JDK toolchain.”**  
Sai. Kết quả HTML/links có thể khác giữa các JDK; pin toolchain để có build tái lập.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Công cụ chính thức hiện hành tạo API HTML từ Java comments là gì?  
**Đáp án:** `javadoc` với standard doclet.

**Câu 2.** `-d docs/api` dùng làm gì?  
**Đáp án:** Chọn thư mục output của HTML artifacts.

**Câu 3.** `-Xdoclint:all` bao gồm các nhóm nào?  
**Đáp án:** Accessibility, HTML, missing, reference và syntax.

**Câu 4.** `-Werror` có ý nghĩa gì?  
**Đáp án:** Báo lỗi build khi Javadoc phát hiện warnings.

**Câu 5.** `-quiet` có vô hiệu hóa warnings không?  
**Đáp án:** Không.

**Câu 6.** Vì sao `-Xdoclint:none` không phải giải pháp quality?  
**Đáp án:** Nó tắt validation thay vì sửa lỗi.

**Câu 7.** Tài liệu của một method public có `@param` đúng nhưng thiếu `@return` sẽ bị phát hiện ở nhóm nào?  
**Đáp án:** `missing`.

**Câu 8.** `{@link NoSuchType}` bị lỗi thuộc nhóm nào?  
**Đáp án:** `reference`.

**Câu 9.** Làm sao phân biệt Javadoc build thành công hay thất bại trên CI?  
**Đáp án:** Kiểm tra exit status, không chỉ kiểm tra thư mục output.

**Câu 10.** Java `DocSiteAudit` trong bài kiểm tra gì?  
**Đáp án:** Pages/files, UTF-8, nội dung tiếng Việt, method anchors/internal links và một example behavior.

**Câu 11.** Tại sao vẫn phải test links bên ngoài Javadoc?  
**Đáp án:** DocLint không phải HTTP link crawler và không bảo đảm tất cả external URLs hợp lệ.

**Câu 12.** `--release 17` có làm output HTML luôn giống JDK 17 không?  
**Đáp án:** Không, layout do phiên bản `javadoc` executable quyết định.

**Câu 13.** `-linkoffline` khác `-link` chủ yếu ở đâu?  
**Đáp án:** Dùng metadata local cho các link tới external Javadoc docs thay vì cần lấy metadata ở remote URL lúc build.

**Câu 14.** Vì sao `package-info.java` quan trọng?  
**Đáp án:** Nó mô tả package và tạo nội dung cho package documentation page.

**Câu 15.** Có nên bật `-linksource` công khai cho mã nguồn đóng không?  
**Đáp án:** Không mặc định; nó có thể phơi bày private source.

**Câu 16.** Một code example trong docs sai logic có chắc bị DocLint phát hiện không?  
**Đáp án:** Không. Cần compilation/behavior tests và review.

**Câu 17.** Trước publish phải làm gì với output dir từng có docs cũ?  
**Đáp án:** Sinh vào thư mục sạch, kiểm tra rồi deploy artifacts đã pass; không trộn docs releases.

**Câu 18.** Muốn CI thật sự fail khi audit in `classPageExists=false` thì phải làm sao?  
**Đáp án:** Ném `AssertionError`/assertion framework hoặc có bước CI parse false rồi trả nonzero.

**Câu 19.** Những loại lỗi nào có thể xuất hiện sau khi deploy dù local Javadoc pass?  
**Đáp án:** Relative links, URL base, caching, JS assets, external links và hosting behavior.

**Câu 20.** Javadoc từ Java 10 có còn phù hợp không?  
**Đáp án:** Có, `javadoc` vẫn được hỗ trợ, nhưng dùng cờ và tính năng JDK mới; tránh flags HTML4/frames cũ.

## 15. Checklist phát hành API documentation

- [ ] Ghi nhận JDK/toolchain version và input/source API version.
- [ ] Compile Java source và chạy unit tests theo target.
- [ ] Chạy `javadoc -Xdoclint:all -Werror`; fail khi exit nonzero.
- [ ] Đặt output vào thư mục sạch, ngoài source.
- [ ] Có `index.html`, package/class pages, index/search metadata cần thiết.
- [ ] Chữ tiếng Việt đúng UTF-8.
- [ ] Trang class thể hiện đúng public API, parameters, return, throws.
- [ ] Nội bộ `{@link}` trỏ đúng method/class; external links được kiểm tra phù hợp.
- [ ] Doc site preview hoạt động trên hosting tương tự production.
- [ ] Không vô tình xuất bản private implementation thông qua `-linksource`.
- [ ] Không dùng `-Xdoclint:none` để né warning chưa sửa.
- [ ] Custom QA assertions **trả nonzero khi fail**, không chỉ in `false`.
- [ ] Đảm bảo docs và binary artifacts cùng source release.
- [ ] Publish chỉ sau khi mọi gate thành công.

## 16. Ghi nhớ

1. **`javadoc` vẫn là công cụ chính thức hiện hành** để tạo API docs; Java 10 là bối cảnh module, không phải lý do dùng flags cũ.
2. **`-Xdoclint:all` kiểm tra tài liệu** theo nhóm accessibility, html, missing, reference, syntax.
3. **`-Werror` biến warnings thành build failure**, hữu ích trong CI nghiêm ngặt.
4. **`-quiet` không tắt cảnh báo**; `-Xdoclint:none` thì có, nên tránh khi quality là mục tiêu.
5. **Exit code 0 chỉ là cổng đầu tiên**; cần kiểm tra HTML artifacts, anchors, links, UTF-8 và API behavior.
6. Dùng **`-d`, `-sourcepath`, `-subpackages`, `--release`, `-encoding`, `-docencoding`** đúng phạm vi.
7. Với target Java 17 nhưng chạy Javadoc JDK 24, **HTML generator vẫn là JDK 24**; pin toolchain để tests HTML ổn định.
8. **Broken `{@link}` và thiếu `@return`** đã được kiểm thử làm Javadoc strict thất bại.
9. **Kiểm tra docs không thay thế compile/unit tests hoặc external URL checks**.
10. Generated docs phải được **review và publish cùng release API**, không rò rỉ private source, không bỏ qua warnings chỉ để pipeline xanh.

## Tài liệu tham khảo chính thức và hiện hành

- Oracle **Java SE 27 — The javadoc Command**: `-Xdoclint`, `-Werror`, `-quiet`, output doclet, linking, Java comments, `-html5` no-op, `--no-frames` unsupported: https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html
- Oracle **Java SE 10 — javadoc tool**: tài liệu lịch sử để hiểu ngữ cảnh Java 10, không ưu tiên options lỗi thời: https://docs.oracle.com/javase/10/tools/javadoc.htm
- Oracle **JavaDoc Documentation Comment Specification for the Standard Doclet**: các block/inline tags và mô tả: https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html
- Oracle **JDK 27 — The javac Command**: `--release`/`-encoding` kiểm tra source: https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html
- JDK **DocTree/Doclet API — jdk.javadoc.doclet**: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/package-summary.html
- OpenJDK **JEP 413 — Code Snippets in Java API Documentation** (JDK 18+): https://openjdk.org/jeps/413
