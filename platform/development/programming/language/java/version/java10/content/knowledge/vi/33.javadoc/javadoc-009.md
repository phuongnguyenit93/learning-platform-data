# Liên kết tài liệu ngoài và kiểm tra lỗi truy cập trong Javadoc

*Chủ đề Java 10 — Javadoc. Bài này hướng dẫn cách tạo liên kết từ API documentation tới lớp/phương thức của thư viện ngoài, tới bộ Javadoc của module khác và tới trang web HTTP(S), đồng thời kiểm tra lỗi tham chiếu, metadata không đọc được, link hỏng, quyền truy cập và các vấn đề phát hành. Chỉ dùng những cơ chế còn phù hợp ở Java 17+, Java 21 và JDK 25. Các chương trình mẫu biên dịch bằng `--release 17` và đã được chạy trên HotSpot JDK 24.*

## 1. Hiểu đúng chữ “liên kết ngoài” trước khi viết Javadoc

Trong một trang Javadoc, người đọc có thể thấy ba dạng link:

| Loại | Ví dụ | Công cụ chịu trách nhiệm |
| --- | --- | --- |
| Tham chiếu **Java element** | `{@link demo.api.Part}`, `{@link java.util.List}` | Javadoc parser, name/type resolution, DocLint |
| Liên kết tới bộ **Javadoc khác** | `-link URL` hoặc `-linkoffline URL DIR` | Standard doclet và file `element-list` |
| Liên kết **webpage thông thường** | `<a href="https://openjdk.org/jeps/286">JEP 286</a>` | HTML; phải có HTTP/access checker riêng |

**Điểm quan trọng:** build Javadoc trả exit code `0` không bảo đảm mọi URL được mở bằng browser đều có HTTP `200`. Javadoc có thể sinh một `href` trỏ đến host không tồn tại mà không cần kết nối đến host đó, đặc biệt khi dùng `-linkoffline`.

Ngược lại, việc website trả `403 Forbidden` là vấn đề quyền truy cập HTTP, **không có cùng nghĩa** với lỗi Javadoc `reference not found`. Và DocLint nhóm `accessibility` kiểm **trợ năng web**, không kiểm HTTP 403.

### 1.1. Bốn tầng cần kiểm riêng

~~~text
Java source và dependency symbols
       │
       ▼
Javadoc comment reference resolution
       │
       ▼
Generated HTML href + đúng module/package/member fragment
       │
       ▼
Website/publication HTTP status, TLS, authentication, redirects
~~~

Để một liên kết trong tài liệu công khai hoạt động, cả bốn tầng liên quan đều phải đúng. Lỗi ở tầng nào thì sửa ở tầng đó; không nên tắt DocLint hay TLS certificate validation để làm pipeline xanh.

## 2. Cơ chế Javadoc hiện hành

JDK có hai công cụ tách biệt:

~~~bash
javac --release 17 ...
javadoc -d docs ...
~~~

- `javac` biên dịch Java source và kiểm Java language/type rules.
- `javadoc` đọc source declarations, documentation comments và các dependencies để sinh trang HTML API documentation.
- Standard doclet tạo trang types/members, index/navigation và metadata như `element-list`.
- `javac` có thể PASS dù trong documentation comment xuất hiện tên class không tồn tại; `javadoc` có thể FAIL khi xử lý reference sai.
- `-Werror` của `javadoc` nâng warnings thành lỗi build; những reference errors nghiêm trọng vốn có thể làm Javadoc nonzero mà **không cần** `-Werror`.

Java 10 không phải phiên bản đầu tiên có `@see` hay `{@link}`. Những kỹ thuật đó đã tồn tại trước Java 10 và **vẫn đang được sử dụng** trong JDK hiện đại, nên phù hợp với module Java 10 theo ghi chú yêu cầu tránh nội dung lỗi thời.

## 3. `{@link}`, `{@linkplain}`, `@see` và link HTML

### 3.1. Inline link tới Java type

~~~java
/**
 * Tạo nhãn từ {@link demo.api.Part}.
 * Xem thêm {@link java.util.List}.
 */
public final class Catalog { }
~~~

`{@link demo.api.Part}` khiến Javadoc cố gắng resolve `demo.api.Part` như một **Java program element**. Nếu `Part` ở dependency ngoài, công cụ cần biết type qua classpath/module path và có thể dùng external docs metadata để tạo URL tới trang `Part.html`.

Cú pháp có label:

~~~java
/** Dùng {@link demo.api.Part#code() mã định danh}. */
~~~

`demo.api.Part#code()` là reference tới method; `mã định danh` là label người đọc thấy. Với overloaded methods, cần mô tả signature khớp với API thật. Sai method name hoặc parameter types có thể dẫn đến lỗi `reference not found`.

### 3.2. `{@linkplain}` và khả năng đọc câu văn

~~~java
/** Trả về {@linkplain java.util.List danh sách phần tử}. */
~~~

`{@linkplain}` dùng cùng cơ chế tham chiếu Java elements nhưng phần label hiển thị ở dạng chữ thường thay vì mặc định kiểu code. Dùng khi câu văn tự nhiên cần liên kết chứ không chủ ý định dạng một tên API như đoạn code.

### 3.3. `@see` là block tag

~~~java
/**
 * Xử lý một đối tượng Part.
 *
 * @see demo.api.Part
 * @see demo.api.Part#code()
 */
public final class Catalog { }
~~~

`@see` đặt trong phần block tags, tạo mục “See Also” theo standard doclet. `{@link}` là tag inline xuất hiện trong câu văn. Đừng đổi vị trí hai loại tag một cách tùy tiện.

### 3.4. Website ngoài không phải Java element

~~~java
/**
 * Đọc <a href="https://openjdk.org/jeps/286">JEP 286</a>.
 *
 * @see <a href="https://openjdk.org/jeps/286">JEP chính thức</a>
 */
public final class Catalog { }
~~~

Đối với một HTTP URL tự do, dùng HTML anchor. Không viết:

~~~java
/** Không đúng: {@link https://openjdk.org/jeps/286} */
~~~

Đoạn cuối **cố ý sai** vì `{@link}` không phải cơ chế biến mọi chuỗi URL thành link web. Cần phân biệt một symbol như `java.util.List` với trang như `https://openjdk.org/jeps/286`.

### 3.5. Chọn label rõ ràng

Đặt tên link có ý nghĩa, ví dụ “Tài liệu JDK 25 về Javadoc” thay cho “xem ở đây”. Điều này giúp người đọc và screen readers. Đừng đưa URL quá dài làm text nếu có thể mô tả nội dung đích ngắn gọn, chính xác.

Nếu cần mở tab mới, kiểm chính sách security/accessibility trước khi thêm `target="_blank"`; cân nhắc `rel="noopener noreferrer"`. Đối với API docs thông thường, một link chuẩn với text mô tả thường đủ.

## 4. `-link` — liên kết với bộ Javadoc ở địa chỉ có thể đọc

Tùy chọn còn được hỗ trợ:

~~~bash
javadoc -d docs \
  -link https://docs.oracle.com/en/java/javase/25/docs/api/ \
  -sourcepath src some.package
~~~

`some.package` ở đây là tên package minh họa phải tồn tại trong source tree của dự án.

`-link URL` yêu cầu Javadoc sử dụng **metadata của bộ Javadoc ngoài** tại directory URL để map các external Java elements thành đường dẫn tương ứng. URL cần trỏ tới **gốc bộ API docs**, không phải trực tiếp tới `Part.html` hoặc một `index.html` riêng lẻ.

Một số yêu cầu:

1. Bộ docs ngoài đã được sinh bằng Javadoc tương thích và có metadata như `element-list`.
2. Máy build có thể đọc metadata ở địa chỉ đó nếu dùng `-link` trực tiếp.
3. Symbols vẫn phải resolve được nhờ source/classpath/module path phù hợp.
4. Base URL nhúng vào `href` phải đúng path cuối cùng khi xuất bản.
5. Bộ metadata và bộ HTML trên server phải **cùng phiên bản dependency**.

**Không** hiểu `-link` như lệnh tải toàn bộ website/docs ngoài. Nó có thể cần đọc index metadata tại build, nhưng browser vẫn phải truy cập HTML đích sau khi publish.

### 4.1. Nhiều bộ docs

Có thể sử dụng nhiều lựa chọn `-link` hoặc `-linkoffline` khi API liên quan nhiều thư viện. Trong trường hợp packages trùng, modules khác nhau, version khác nhau, kiểm generated targets thật. Đừng mặc định rằng một type sẽ luôn được gắn đúng base URL khi hai bộ docs cùng tuyên bố sở hữu tên package.

### 4.2. Relative URLs

Nếu hai bộ API docs được publish cạnh nhau:

~~~text
site/
  library-api/
  client-api/
~~~

có thể dùng liên kết tương đối thay vì absolute URLs. Nhưng URL tương đối phải được hiểu từ **vị trí trang HTML đã publish**, không được tự động suy theo thư mục source. Nếu CI/CD chuyển riêng một bộ docs sang prefix/CDN mới thì relative links có thể hỏng.

## 5. `-linkoffline` — URL cho người đọc và thư mục metadata cho máy build

Cú pháp:

~~~bash
javadoc -linkoffline PUBLIC_BASE_URL LOCAL_EXTERNAL_DOC_DIR ...
~~~

Hai arguments có nhiệm vụ khác nhau:

- `PUBLIC_BASE_URL`: địa chỉ được nhúng vào `href` của generated HTML.
- `LOCAL_EXTERNAL_DOC_DIR`: vị trí mà máy build đọc metadata `element-list` của external API docs.

Ví dụ:

~~~text
Metadata có ở máy build:
  /ci/cache/library-docs/element-list
  /ci/cache/library-docs/demo/api/Part.html

URL dự định dùng sau khi public:
  https://docs.example.invalid/api/

Javadoc:
  -linkoffline https://docs.example.invalid/api/ /ci/cache/library-docs
~~~

**`docs.example.invalid` là domain giả**, được dùng để chứng minh Javadoc có thể tạo HTML hyperlinks khi không truy cập Internet. Nó **không** phải địa chỉ được phép tuyên bố là đang hoạt động. Đối với release thật, thay bằng base URL thực sự đã publish và chạy HTTP link validation riêng.

### 5.1. Tham số thứ hai là thư mục, không phải path file

Đúng:

~~~bash
javadoc -linkoffline https://example.invalid/api/ ./libdocs ...
~~~

Sai:

~~~bash
javadoc -linkoffline https://example.invalid/api/ ./libdocs/element-list ...
~~~

Trong cách dùng đúng, `libdocs` là **directory chứa `element-list`**. Standard doclet tự đọc file index từ đó. Đừng truyền path chỉ thẳng vào `element-list`.

### 5.2. Offline build không đồng nghĩa offline browsing

`-linkoffline` tránh dependency vào website ngoài **khi tạo Javadoc**. Nhưng generated HTML có thể vẫn chứa `https://...` links; người đọc cần network/quyền vào host ấy để mở.

Nếu ứng dụng phải cung cấp tài liệu xem hoàn toàn offline, cần phân phối cả external HTML docs và dùng relative links/layout đúng, không chỉ sao chép `element-list`.

### 5.3. Không tự bịa danh sách elements

File `element-list` được Javadoc sinh từ bộ API docs tương ứng, chứa packages và (nếu phù hợp) module metadata. Không sửa/bịa file để né lỗi; lấy đúng artifact hoặc regenerate docs từ dependency thật.

### 5.4. Version mismatch có thể tạo link “có vẻ đúng”

Giả sử `element-list` của thư viện v2, URL lại trỏ HTML v1. Javadoc có thể tạo `href` nhưng trang/member không tồn tại. Khi release, pin **cùng version** cho binary dependencies, Javadoc metadata và published docs.

## 6. Ba đường cấu hình không thể thay thế nhau

| Lựa chọn | Dùng để làm gì? |
| --- | --- |
| `-classpath classes` | Tìm Java type/member definitions cần để resolve signatures và references ở ứng dụng non-modular |
| `-sourcepath clisrc` | Tìm Java sources/packages đang được tạo docs |
| `-linkoffline URL libdocs` | Map external Java types thành hyperlinks nhờ metadata |
| `-d clientdocs` | Thư mục output HTML/metadata |
| `--module-path ...` | Resolve module dependencies ở dự án JPMS |
| `--module-source-path ...` | Tìm modular Java source tree |
| `-Xdoclint:all` | Kiểm doc comments, Java refs, markup và những nhóm lỗi liên quan |
| `-Werror` | Cho warnings tác động tới trạng thái build |

`-linkoffline` **không** tự động cung cấp dependency classes để compiler hoặc Javadoc type resolver sử dụng. Nếu `Part` không có trên classpath/module path, link metadata có thể hiện diện mà `{@link Part#code()}` vẫn không resolve.

## 7. Ví dụ thực hành: tạo hai bộ Javadoc liên kết chéo

Ví dụ đã kiểm thử trên **HotSpot JDK 24**, dùng Java source tương thích `--release 17`.

### 7.1. Cấu trúc thư mục

~~~text
project/
  libsrc/
    demo/api/Part.java
  clisrc/
    demo/client/Catalog.java
  classes/
  libdocs/
    element-list
    demo/api/Part.html
  clientdocs/
    demo/client/Catalog.html
    index.html
~~~

Các thư mục `classes`, `libdocs` và `clientdocs` là output; trong quy trình build sạch, tạo chúng bằng build script thay vì commit bản generated HTML không được quản lý vào source tree.

### 7.2. `libsrc/demo/api/Part.java`

~~~java
package demo.api;

/** Public demo API for local Javadoc cross-links. */
public final class Part {
    private final String code;

    /**
     * Creates a part.
     *
     * @param code text of the identifier
     */
    public Part(String code) {
        this.code = code;
    }

    /**
     * Returns its identifier.
     *
     * @return identifier string
     */
    public String code() {
        return code;
    }
}
~~~

Class này thuộc library bên ngoài **từ góc nhìn consumer**. Trong demo ta có source để tạo một bộ external Javadoc dùng làm nguồn `element-list` hợp lệ.

### 7.3. `clisrc/demo/client/Catalog.java`

~~~java
package demo.client;

import demo.api.Part;

/**
 * Client links to {@link demo.api.Part}, its
 * {@link demo.api.Part#code()},
 * and a standard {@link java.util.List}.
 * Read the <a href="https://openjdk.org/jeps/286">official JEP page</a>.
 *
 * @see demo.api.Part
 * @see <a href="https://openjdk.org/jeps/286">JEP 286</a>
 */
public final class Catalog {
    private Catalog() { }

    /**
     * Builds a safe display label.
     *
     * @param part supplied part
     * @return the part code
     * @throws IllegalArgumentException when part is null
     */
    public static String label(Part part) {
        if (part == null) {
            throw new IllegalArgumentException("part");
        }
        return part.code();
    }
}
~~~

Chương trình này **không có main**; đây là API library class để biên dịch và sinh Javadoc, không phải Java app để gọi trực tiếp bằng `java demo.client.Catalog`. Source code đã được compile thành công.

### 7.4. Compile theo thứ tự dependency

Trong thư mục `project`:

~~~bash
mkdir -p classes

javac --release 17 -d classes \
  libsrc/demo/api/Part.java

javac --release 17 -cp classes -d classes \
  clisrc/demo/client/Catalog.java
~~~

`javac` cần external `Part.class` được tạo trước; việc có `element-list` chưa giúp giải quyết Java compiler dependency.

### 7.5. Sinh Javadoc library

~~~bash
javadoc -quiet -Xdoclint:all -Werror --no-platform-links \
  -d libdocs \
  -sourcepath libsrc \
  demo.api
~~~

`--no-platform-links` là tùy chọn có **hai dấu gạch đầu dòng**, đã kiểm tra trên JDK 24. Trong demo nó ngăn truy cập/liên kết platform docs để bài test chỉ kiểm external library links cục bộ. Đây không phải lựa chọn buộc dùng cho production docs.

Sau khi lệnh chạy xong:

~~~bash
cat libdocs/element-list
~~~

Nội dung chính xác ở bản test:

~~~text
demo.api
~~~

### 7.6. Sinh Javadoc consumer với local metadata

~~~bash
javadoc -quiet -Xdoclint:all -Werror --no-platform-links \
  -d clientdocs \
  -sourcepath clisrc \
  -classpath classes \
  -linkoffline https://example.invalid/api/ libdocs \
  demo.client
~~~

Kết quả chạy thử: **hai lệnh Javadoc đều exit code 0**. Generated HTML ở `clientdocs/demo/client/Catalog.html` chứa:

- `https://example.invalid/api/` làm prefix external API href.
- `Part.html` của Java class bên ngoài.
- Anchor `#code()` của method `Part#code()`.
- `https://openjdk.org/jeps/286` từ raw HTML link trong source.
- `index.html` của bộ consumer docs.

### 7.7. Kết quả kiểm bằng script tại môi trường thử nghiệm

~~~text
generated element-list = True
external API href prefix present = True
external Part link present = True
external Part method member present = True
raw external page href present = True
index.html generated = True
~~~

Đây là những dòng **kiểm tra boolean của script**, không phải stdout của Java source. Vì `example.invalid` không hoạt động trên Internet, bài test này chỉ xác minh **Javadoc link generation** và **cấu trúc HTML**, chưa xác minh HTTP reachability.

### 7.8. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Path classes -Force | Out-Null

javac --release 17 -d classes libsrc/demo/api/Part.java

javac --release 17 -cp classes -d classes clisrc/demo/client/Catalog.java

javadoc -quiet -Xdoclint:all -Werror --no-platform-links -d libdocs -sourcepath libsrc demo.api

javadoc -quiet -Xdoclint:all -Werror --no-platform-links -d clientdocs -sourcepath clisrc -classpath classes -linkoffline https://example.invalid/api/ libdocs demo.client

Test-Path libdocs/element-list
Test-Path clientdocs/demo/client/Catalog.html
Get-Content libdocs/element-list
~~~

Kiểm `$LASTEXITCODE` ngay sau mỗi `javac`/`javadoc`. Việc file HTML đã được tạo không đủ chứng minh job thành công, vì Javadoc có thể ghi một phần output trước khi báo error.

## 8. Làm gì với `{@link}` trỏ đến symbol sai?

### 8.1. DocLint reference checking

Dùng:

~~~bash
javadoc -Xdoclint:reference -d docs ...
~~~

hoặc bật toàn bộ kiểm tra:

~~~bash
javadoc -Xdoclint:all -Werror -d docs ...
~~~

Javadoc hiện hành có các DocLint groups:

| Group | Kiểm điều gì? | Ví dụ |
| --- | --- | --- |
| `reference` | Tham chiếu tới Java elements, parameters | Method không tồn tại, `@param` sai |
| `syntax` | Cú pháp Javadoc comments/tags | Dấu không escape, tag sai dạng |
| `html` | HTML markup | Tag chưa đóng, lồng không hợp lệ |
| `accessibility` | Trợ năng nội dung HTML | Ảnh thiếu alt, bảng không rõ cấu trúc |
| `missing` | Comments/tags còn thiếu | Thiếu doc, `@return` ở public method |

`-Xdoclint:all` phát hiện nhiều vấn đề nhưng **không thay một bộ HTML/accessibility link crawler toàn diện**. Đặc biệt, nó không theo dõi HTTP response của tùy ý `href="https://..."`.

### 8.2. Chương trình cố ý có link sai

~~~java
// File: Broken.java — minh họa lỗi tài liệu
package demo.client;

/**
 * Invalid Java doc reference:
 * {@link java.util.List#methodThatDoesNotExist()}.
 */
public final class Broken {
    private Broken() { }
}
~~~

Đoạn `{@link ...}` trên nằm trong comment; Java source có thể compile thành công, nhưng Javadoc sẽ cố tìm member đó và không thấy.

~~~bash
javadoc -quiet -Xdoclint:all -Werror --no-platform-links \
  -d broken-docs Broken.java
~~~

Trong lần thử trên JDK 24, kết quả có:

~~~text
error: reference not found
1 error
~~~

Lệnh trả exit code **khác 0**. **`-Werror` không phải nguyên nhân duy nhất**: reference lỗi đã được Javadoc coi là error trong thử nghiệm.

### 8.3. Sửa reference đúng cách

- Xem class/package có thật không.
- Kiểm method name, overload và parameter types.
- Xem method có bị xóa/đổi tên ở version dependency đang build không.
- Kiểm classpath/module path của Javadoc process.
- Kiểm access level của element và cấu hình doclet release.
- Kiểm external metadata đúng version để sinh href hợp lệ.
- Đừng chỉ thay link bằng một URL random hoặc tắt toàn bộ DocLint để che lỗi.

## 9. Thiếu `element-list` gây lỗi build riêng

Với:

~~~bash
javadoc -quiet -Xdoclint:all -Werror --no-platform-links \
  -d docs \
  -linkoffline https://example.invalid/api/ ./missing-index \
  Valid.java
~~~

nếu thư mục `missing-index` không có metadata, Javadoc 24 báo dạng:

~~~text
error: Error reading file: .../missing-index/element-list
1 error
~~~

và exit code nonzero. Dấu `...` thay đường dẫn filesystem biến thiên.

Đây là lỗi **không đọc được metadata** tại máy build, không phải bằng chứng host `example.invalid` đã bị HTTP404: URL public này không cần được truy cập khi chạy `-linkoffline`.

### 9.1. Quy trình xử lý metadata không đọc được

1. Kiểm tham số thứ hai thực sự là **directory**.
2. Kiểm thư mục chứa `element-list` do Javadoc tạo.
3. Kiểm quyền đọc/mount path trong runner hoặc container.
4. Kiểm working directory và đường relative path.
5. Kiểm version của metadata khớp dependency.
6. Nếu thư viện modular, kiểm module/package entries.
7. Không bịa `element-list` thủ công, không thay bằng trỏ tới HTML page.

### 9.2. Khi dùng `-link` trực tiếp

Lỗi network như DNS, TLS, proxy, HTTP status hoặc host không cho đọc metadata có thể làm Javadoc báo lỗi “fetch/reading URL”. Với `-link`, hãy xác minh URL base thực và server có cho truy cập `element-list` hay không. Với CI restricted network, cân nhắc `-linkoffline` và một artifact metadata đã pin version.

## 10. Vì sao build PASS nhưng đường link trên web vẫn hỏng?

Một docs source:

~~~java
/**
 * Đọc <a href="https://example.invalid/deleted">hướng dẫn ngoài</a>.
 */
public final class ReferenceGuide { /* ... */ }
~~~

có thể là HTML hợp lệ đối với Javadoc dù URL `example.invalid` không tồn tại. **DocLint không gọi HTTP GET/HEAD tới mọi trang web** để bảo đảm chúng mở được.

Sự khác nhau cần ghi rõ:

| Kiểm tra | PASS chứng minh | PASS chưa chứng minh |
| --- | --- | --- |
| `javac --release 17` | Source Java hợp lệ | Javadoc comments đúng |
| Javadoc + DocLint | Comment/reference theo phạm vi kiểm hợp lệ | URL ngoài thực sự reachable |
| Static HTML href check | `href` có mặt và được dựng theo metadata | Website online/đúng version |
| HTTP GET status 200 | Request cụ thể nhận được 200 | Fragment, content, quyền người khác |
| Browser user A mở được | User A có quyền trong session đó | Anonymous/CI/user B cũng đọc được |

### 10.1. Fragment không được gửi trong HTTP request

Một URL tới method:

~~~text
https://docs.example.invalid/api/demo/api/Part.html#code()
~~~

gồm đường đến `Part.html` và fragment `#code()`. Browser xử lý fragment ở client; HTTP request đến server **không chứa fragment**.

Vì vậy Javadoc có thể tạo fragment sai; HTTP checker nhận 200 cho `Part.html` mà người đọc vẫn không nhảy đến method. Muốn kiểm hoàn chỉnh cần parse HTML target và xác định `id`/anchor tương ứng.

### 10.2. Sai version vẫn có thể trả HTTP200

Website có thể phục vụ `Part.html` của v1 với method không còn đúng v2. Thậm chí trang trả 200 nhưng nội dung thuộc API khác. Để kiểm documentation integrity, cần pin version và kiểm đúng title/member signature/anchors, không chỉ status code.

## 11. HTTP status và lỗi truy cập người đọc gặp

| Tình trạng | Nghĩa thường gặp | Không nên kết luận quá mức |
| --- | --- | --- |
| `200 OK` | Server trả content cho request | Fragment, nội dung, ACL cho mọi user đều đúng |
| `301/308` | Redirect dài hạn | URL gốc không cần cập nhật |
| `302/307` | Redirect tạm | Đích cuối chắc chắn là API docs |
| `401 Unauthorized` | Cần authentication hợp lệ | URL đã bị xóa |
| `403 Forbidden` | Không được phép truy cập theo ACL/WAF/SSO | Link chắc chắn không tồn tại |
| `404 Not Found` | Đường dẫn không được tìm thấy | Không có bản mới/redirect thay thế |
| `410 Gone` | Resource đã được chủ thể phục vụ báo bị loại bỏ | Không cần cập nhật docs |
| `429 Too Many Requests` | Đang bị rate-limit | Server hỏng vĩnh viễn |
| `500/502/503/504` | Backend/upstream lỗi hoặc tạm unavailable | Sai JavaDoc symbol |
| Không có HTTP response | DNS, TLS, proxy, TCP, timeout | Đương nhiên là 404 |

Khi cần test public docs, dùng **anonymous request** thay vì cookie/SSO của developer. Khi cần test internal docs, dùng service account/role được cấp phép thay vì bypass auth. Một URL có thể hoạt động với nhân viên nội bộ nhưng trả HTTP403 cho external audience.

### 11.1. HTTP200 không bảo đảm trang là docs thật

Website có thể trả HTTP200 với màn hình login, soft-404 “page not found”, shell app chưa load API docs hoặc redirect về trang chủ. Kiểm title/heading/content khi sản phẩm cần chất lượng tài liệu cao.

### 11.2. Redirect cần giới hạn

HTTP redirect chain có thể dài, vòng lặp, sai URL version, chuyển từ HTTPS sang HTTP hoặc chuyển origin đòi credentials. Link checker nên giới hạn redirect count và không tự gửi token/header nhạy cảm sang origin mới.

## 12. Ví dụ HTTP checker xác định 200/403/404/302 mà không gọi Internet

Để minh họa chính xác “lỗi truy cập”, có thể dùng Java `HttpClient` kết nối tới HTTP server **trên loopback**. Server test thuộc module JDK `jdk.httpserver`, không phải Java SE module bắt buộc cho runtime production, nên phần này dành cho môi trường có đầy đủ JDK.

### 12.1. File `DocLinkStatusDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class DocLinkStatusDemo {
    private static void respond(
            HttpExchange exchange, int code, String body)
            throws java.io.IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(code, data.length);
        try (var out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/ok",
                ex -> respond(ex, 200, "API documentation"));
        server.createContext("/forbidden",
                ex -> respond(ex, 403, "Access denied"));
        server.createContext("/missing",
                ex -> respond(ex, 404, "Not found"));
        server.createContext("/redirect", ex -> {
            ex.getResponseHeaders().set("Location", "/ok");
            ex.sendResponseHeaders(302, -1);
            ex.close();
        });

        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();

            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");

            for (String path : new String[] {
                    "ok", "forbidden", "missing", "redirect"
            }) {
                HttpRequest request = HttpRequest.newBuilder(
                                root.resolve(path))
                        .timeout(Duration.ofSeconds(3))
                        .GET()
                        .build();

                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding());

                System.out.println(path + " status = "
                        + response.statusCode());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

### 12.2. Lệnh biên dịch/chạy

~~~bash
javac --release 17 --add-modules jdk.httpserver \
  DocLinkStatusDemo.java

java --add-modules jdk.httpserver DocLinkStatusDemo
~~~

**Stdout chính xác trên HotSpot JDK 24 đã kiểm thử:**

~~~text
ok status = 200
forbidden status = 403
missing status = 404
redirect status = 200
~~~

- `/ok` phục vụ HTTP200.
- `/forbidden` trả HTTP403 cho request (test mô phỏng quyền bị từ chối).
- `/missing` trả HTTP404.
- `/redirect` trả 302 và header `Location: /ok`, `HttpClient.Redirect.NORMAL` theo redirect nên thấy **status cuối = 200**.

Chương trình chỉ kết nối `127.0.0.1`, dùng cổng động, đóng server trong `finally`. Không nên đọc output của nó như bằng chứng trạng thái hiện tại của một website thật.

### 12.3. Những phần chưa có trong một HTTP crawler production

Demo chỉ là smoke-test status. Khi xây checker production cần bổ sung:

- Allowlist host/scheme để giảm nguy cơ SSRF.
- Timeout, max redirects, concurrency cap, retry có backoff.
- Tránh tự gửi Authorization/cookies qua cross-origin redirects.
- Phân biệt DNS exception, TLS exception, timeout và HTTP status.
- Kiểm content-type, version/heading và fragment khi có yêu cầu.
- Không log HTML private documents hoặc credentials.
- Không làm nặng external websites bằng hàng nghìn concurrent requests.
- Tôn trọng authentication, permissions và chính sách crawling.

## 13. Kiểm các liên kết ngoài bằng `curl`

Khi có quyền gọi mạng công khai, có thể dùng:

~~~bash
curl --head --location --max-time 10 \
  --silent --show-error \
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html
~~~

Hoặc kiểm GET:

~~~bash
curl --location --max-time 10 \
  --silent --show-error --output /dev/null \
  --write-out '%{http_code} %{url_effective}\n' \
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html
~~~

Lệnh GET chỉ là **hướng dẫn điều tra**, không phải output JDK test trong bài. `curl` mặc định có thể exit 0 dù HTTP status là 404 nếu không bật các lựa chọn tương ứng; kiểm **cả tool exit code và HTTP status**.

### 13.1. HEAD405 không nhất thiết là link hỏng

Nhiều server hỗ trợ GET nhưng không hỗ trợ HEAD và trả `405 Method Not Allowed`. Nếu HEAD thất bại, thử GET an toàn với timeout và giới hạn kích thước. Đừng sửa/xóa link chỉ vì HEAD405.

### 13.2. Auth, proxy và TLS

Nếu Javadoc metadata qua `-link` hoặc HTTP link checker không truy cập được web host:

- HTTP401/403: kiểm ACL, SSO, service-account role.
- HTTPS certificate error: kiểm JDK/system truststore, certificate chain, proxy.
- DNS/timeout: kiểm CI runner network egress, DNS, corporate proxy.
- Rate-limit 429: giảm tần suất/retry có giới hạn.
- URL 404: kiểm path/version/document move.

Không tắt TLS verification bằng `curl -k` hoặc TrustManager “trust all” để làm check xanh. Điều đó tạo rủi ro bị MITM và che hỏng cấu hình CA.

## 14. DocLint `accessibility` không phải “HTTP access denied”

Đây là sự nhầm lẫn phổ biến vì tiếng Anh cùng có từ “access”:

~~~text
DocLint accessibility
   → Trợ năng: ảnh có alt không? bảng có cấu trúc phù hợp không?

Java private/protected accessibility
   → Kiểm tra visibility và public API khi tạo links

HTTP 403 accessibility/authorization
   → Người gửi request không được server cấp quyền

Network reachability
   → DNS, TCP, proxy, TLS, timeout
~~~

Bốn trường hợp này khác nhau. Lỗi nào cũng cần được đưa đúng owner: người viết Javadoc, người maintain library API, quản trị docs server/IAM hoặc người vận hành network.

### 14.1. Liên kết đến private methods

Nếu method của library là `private`, public docs thông thường không publish nó. Một reference như `{@link SomeClass#hidden()}` có thể không tạo được external public link phù hợp. Cần kiểm visibility và doclet exposure:

~~~text
-public
-protected
-package
-private
~~~

Các options này chọn phạm vi Java elements được đưa vào generated API docs. Không tự bật `-private` trên public docs để né một broken reference, vì có thể lộ implementation details hoặc API không được hỗ trợ.

### 14.2. Public API link nên ổn định

Cố gắng link tới API công khai được hỗ trợ, không tới method private hay class nội bộ. Nếu cần mô tả implementation chi tiết, sử dụng prose và đúng publication scope; đừng giả vờ nội bộ là một public contract.

## 15. Java module (JPMS) và Javadoc linking

Trong Java 9+ modular projects, external docs có thể có module structure và `element-list` ghi module names. Khi đó:

~~~java
module demo.library {
    exports demo.api;
}
~~~

là một **module-info snippet minh họa**, không phải chương trình biên dịch độc lập nếu không có source module tree. Javadoc có thể cần `--module-source-path`, `--module-path` và `--module`.

Cần kiểm:

1. Dependency module có được resolve không.
2. Package cần document có được export/phù hợp không.
3. `element-list` của docs ngoài là đúng module/version không.
4. URL generated có module prefix khi bộ docs đích dùng layout modular không.
5. Docs của modular vs non-modular library có mismatch không.

Option `--link-modularity-mismatch warn|info` có thể điều chỉnh mức báo bất đồng modularity. Không dùng nó như một cách che warning cấu hình sai; trước hết sửa metadata/dependency structure.

## 16. Tài liệu JDK platform và target release

Standard doclet của JDK hiện đại có cơ chế tạo links tới Java platform API docs phù hợp. Trong demo, dùng:

~~~text
--no-platform-links
~~~

để cách ly mạng và chỉ kiểm link tới external demo library. Trong public docs thật, thường muốn có links tới platform API phù hợp Java baseline của thư viện.

Nếu thư viện hỗ trợ Java17 thì URL platform phù hợp có thể là:

~~~text
https://docs.oracle.com/en/java/javase/17/docs/api/
~~~

Khi muốn document API được build với Java25, chọn nguồn tài liệu tương thích Java25. Không nên link đến một method chỉ có ở JDK25 rồi khiến người dùng Java17 hiểu nhầm rằng method đó có mặt trên runtime của họ.

Standard doclet còn hỗ trợ `--link-platform-properties` trên những bản JDK tương ứng để ánh xạ release sang URL platform docs; xem manual của chính JDK đang chạy, không đặt file format tùy ý rồi kỳ vọng mọi JDK hiểu.

## 17. JDK mới có Markdown documentation comments, nhưng không dùng cho Java17 demo

JEP 467 thêm **Markdown Documentation Comments** từ JDK23. Trong toolchain hỗ trợ có thể viết:

~~~java
/// Xem [java.util.List] cho API Java.
/// Tham khảo [OpenJDK](https://openjdk.org/).
public final class Notes { }
~~~

Đây là ví dụ cho **JDK23+**, **không nằm trong ví dụ `javac --release 17`**. Với Java17, dùng dạng `/** ... */` có `{@link}` và HTML anchors như phần trước.

Hai phân loại link vẫn giữ nguyên: `[java.util.List]` là Java-element link theo dạng Markdown của Javadoc, còn `[OpenJDK](https://openjdk.org/)` là URL ngoài. DocLint và HTTP access validation vẫn cần xét riêng.

## 18. Quy trình CI/CD chuẩn cho docs chất lượng

Nên tách các công việc:

~~~text
Bước A: javac --release 17 compile + dependency resolution
   ↓
Bước B: javadoc -Xdoclint:all -Werror
        (source docs + local external element-list)
   ↓
Bước C: verify generated HTML, relative links, member fragments
   ↓
Bước D: publish docs lên staging
   ↓
Bước E: HTTP link checking với đúng audience, timeout/auth
   ↓
Bước F: review, promote release, có rollback
~~~

### 18.1. Khi nào fail pipeline?

- Java reference sai hoặc missing `element-list` được pin: **fail docs build**.
- Internal document trả HTTP403 cho anonymous nhưng policy yêu cầu chỉ internal: không gắn “broken” thiếu context; test bằng authorized identity.
- Public URL trả HTTP404 ổn định: **fail publication validation** hoặc ghi issue sửa link trước release theo policy.
- HTTP429/503 tạm thời: retry/backoff có giới hạn, phân biệt flaky failure với broken link thực.
- Member fragment thiếu: kiểm symbol/signature/metadata version, không chỉ sửa web status.
- Link tới private endpoint bị nhúng trong public docs: **review security/publication scope**.

### 18.2. Cần pin external docs version

Một build của client dùng `Part.class` từ library v2 nên nhận metadata `element-list` từ docs v2 và nhúng base URL đến docs v2. Không nên dùng metadata v2 với HTML v1, vì link tới member mới có thể 404 hoặc trỏ nhầm code.

### 18.3. Không nhúng credentials vào Javadoc comments

Không để signed URLs còn thời hạn dài, API keys, bearer tokens, session cookies hoặc internal share links không được duyệt trong comments. Generated HTML có thể được công khai và cache ở CDN, khiến dữ liệu nhạy cảm bị lộ.

### 18.4. External URLs từ dữ liệu không tin cậy

Nếu link checker trong CI nhận danh sách URL do người ngoài nhập, cần chống SSRF trước khi truy cập. Ngay cả các redirects cũng phải được kiểm nếu không muốn network-reachable CI runner truy cập tài nguyên nội bộ không được phép.

## 19. Ma trận chẩn đoán lỗi

| Triệu chứng | Nguồn lỗi ưu tiên kiểm | Cách xử lý |
| --- | --- | --- |
| `reference not found` | Java element, signature, classpath/module path | Sửa symbol/typography/version |
| `cannot find symbol` trong javac | Java source/dependency | Cấp đúng class/module |
| `Error reading file .../element-list` | Metadata path của `-linkoffline` | Trỏ directory có index, permissions |
| Lỗi fetch URL metadata | `-link` tới server/network | Kiểm URL doc root, HTTP/DNS/TLS/proxy |
| Java type hiển thị như text thay vì link | Missing metadata/visibility/option | Kiểm generated HTML và link map |
| Class page HTTP200, method anchor hỏng | Member fragment/version | Kiểm actual HTML element IDs |
| Link public trả 404 | Website/path/version | Tìm đúng URL mới/cập nhật base |
| Link internal trả 403 | Identity/ACL/SSO | Kiểm role và publication audience |
| Link trả 401 | Authentication | Dùng credential đã cấp hợp lệ |
| Link trả 429 | Rate limit | Giới hạn concurrency/backoff |
| Link trả 503 | Service outage | Kiểm thời gian, retry có giới hạn |
| curl HEAD trả 405 | HTTP method support | Thử GET an toàn, đừng xóa link |
| Browser được, CI không | Egress, proxy, SSO, IP | So môi trường/identity |
| Docs build PASS nhưng page thiếu | Publish missing artifact | Kiểm deploy/CDN/layout |
| Relative links hỏng sau chuyển site | Base path thay đổi | Sửa publish layout/relative URL |
| DocLint accessibility warning | Markup trợ năng | Sửa HTML semantics, không sửa HTTP |
| JDK platform API link sai release | Platform doc version | Pin URL/release tương thích |
| Module mismatch warning | JPMS docs/library metadata | Sửa module resolution/metadata |
| Public docs chứa link private | Publication/security | Thay bằng public source hoặc policy rõ |

**Đừng chỉ đọc một exception và suy toàn bộ hệ thống.** Javadoc reference errors và HTTP access failures là hai lớp độc lập, có thể xảy ra đồng thời.

## 20. Các ngộ nhận thường gặp

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “`{@link https://...}` là syntax chuẩn cho URL.” | `{@link}` trỏ Java elements, URL web dùng HTML anchor. |
| “`@see` dùng ở mọi chỗ giống `{@link}`.” | `@see` là block tag, `{@link}` inline. |
| “`-link` dùng URL `Part.html`.” | Nó cần base docs directory có metadata. |
| “`-linkoffline` có hai URL giống vai trò.” | Tham số 1 là public href, tham số 2 là thư mục metadata. |
| “Có element-list tức mọi class docs đều có HTTP200.” | Không; index không kiểm website. |
| “`-linkoffline` tải hết HTML ngoài về.” | Không, chỉ giúp mapping links khi build. |
| “`-linkoffline` cấp compiler classpath.” | Không; Java symbols cần dependency classes/sources. |
| “Javadoc exit0 thì mọi link URL mở được.” | Không; raw HTTP links không tự được live-check. |
| “HTTP200 nghĩa fragment `#code()` còn tồn tại.” | Không; fragment không được gửi trong request. |
| “HTTP403 = URL đã bị xóa.” | Có thể do IAM, SSO, WAF, IP policy. |
| “DocLint `accessibility` phát hiện 403.” | Nó kiểm web accessibility, không kiểm HTTP authorization. |
| “`-Werror` tự gửi requests để check links.” | Chỉ nâng warnings của Javadoc thành lỗi build. |
| “`javac` pass thì docs không có reference error.” | Docs comments có thể chứa symbol sai. |
| “Cứ dùng `-Xdoclint:none` cho đơn giản.” | Che lỗi docs thật, không nên mặc định. |
| “Java private members luôn có public Javadoc link.” | Visibility và publish scope khác nhau. |
| “HTTP HEAD405 nghĩa GET cũng hỏng.” | Nhiều website không hỗ trợ HEAD. |
| “HTTP302 luôn có nghĩa link ổn.” | Cần xem URL cuối và nội dung. |
| “Một version element-list dùng được cho mọi release library.” | Metadata/HTML mismatch có thể làm hỏng anchors. |
| “`--no-platform-links` bắt buộc khi xuất API docs.” | Chỉ dùng khi phù hợp, demo dùng để tránh network. |
| “`///` Markdown docs có từ Java10.” | Đây là hỗ trợ từ JDK23+. |
| “Đổi cờ Javadoc có thể tự cấp quyền đọc website private.” | Cần sửa IAM/ACL hoặc đúng audience, không bypass auth. |
| “Tắt TLS verification giúp sửa link.” | Gây rủi ro MITM và che lỗi CA/proxy. |

## 21. Bài tập có đáp án

### Bài 1. Phân biệt cú pháp

**Đề:** Với `java.util.List` và trang `https://openjdk.org/jeps/286`, nên dùng gì?

**Đáp án:** `{@link java.util.List}` cho Java type; `<a href="https://openjdk.org/jeps/286">JEP 286</a>` cho trang web.

### Bài 2. Method reference

**Đề:** `{@link demo.api.Part#code()}` phải đáp ứng điều kiện nào?

**Đáp án:** Type/method resolve được, signature đúng, metadata/docs ngoài có map phù hợp và method được publish dưới version chính xác.

### Bài 3. Offline CI

**Đề:** CI không truy cập docs host nhưng có `libdocs/element-list`. Sử dụng gì?

**Đáp án:** `-linkoffline PUBLIC_URL libdocs`, tách URL cuối cho browser khỏi directory metadata ở CI.

### Bài 4. Thư mục hay file?

**Đề:** Trong `-linkoffline URL DIR`, `DIR` nên là `libdocs` hay `libdocs/element-list`?

**Đáp án:** `libdocs` (thư mục chứa index).

### Bài 5. Domain giả

**Đề:** Javadoc link tới `https://example.invalid/api/` và trả exit0. Có nghĩa host tồn tại?

**Đáp án:** Không. Domain được dùng giả lập; Javadoc tạo href mà không bảo đảm host reachable.

### Bài 6. Bad Java reference

**Đề:** `{@link java.util.List#methodThatDoesNotExist()}` sẽ thế nào?

**Đáp án:** Trên JDK24 test, Javadoc báo `reference not found` và exit nonzero.

### Bài 7. Missing index

**Đề:** Missing `element-list` trong `-linkoffline` có phải chứng minh URL đích HTTP404 không?

**Đáp án:** Không. Đó là lỗi đọc metadata local; URL online chưa cần được truy cập.

### Bài 8. `-Werror`

**Đề:** Tại sao thêm `-Werror`?

**Đáp án:** Cho warnings tác động đến trạng thái build; Java reference errors có thể đã đủ khiến Javadoc fail không cần nó.

### Bài 9. HTTP403

**Đề:** Public docs link trả 403 trên CI. Có nên tự động đổi link sang URL khác?

**Đáp án:** Chưa đủ thông tin; kiểm identity, SSO, proxy/WAF, allowlist và audience trước.

### Bài 10. HTTP404

**Đề:** Link `/api/v1/Part.html` 404 còn `/api/v2/Part.html` 200. Cần làm gì?

**Đáp án:** Xác minh dependency/version, dùng metadata cùng v2, sửa public URL hoặc hướng dẫn migration.

### Bài 11. HTTP200 nhưng method không có

**Đề:** Tại sao GET `Part.html` 200 nhưng `#code()` vẫn hỏng?

**Đáp án:** Fragment là thông tin client-side, không được HTTP server kiểm; cần kiểm HTML IDs.

### Bài 12. Local redirect

**Đề:** Demo `redirect status=200` nhưng `/redirect` gửi 302; tại sao?

**Đáp án:** `HttpClient.Redirect.NORMAL` theo Location sang `/ok`, nơi trả 200.

### Bài 13. HEAD405

**Đề:** Curl HEAD 405 có nghĩa external docs chắc chắn hỏng không?

**Đáp án:** Không; thử GET có kiểm soát vì server có thể không hỗ trợ HEAD.

### Bài 14. Accessibility

**Đề:** `-Xdoclint:accessibility` tìm lỗi HTTP401/403?

**Đáp án:** Không, nó kiểm HTML trợ năng.

### Bài 15. Dependency

**Đề:** Chỉ đưa `libdocs` vào `-linkoffline` mà không có `Part.class` thì bảo đảm compile/Javadoc type resolution?

**Đáp án:** Không. Cần classpath/module path hoặc sources phù hợp.

### Bài 16. Version pinning

**Đề:** Dùng metadata library v3 nhưng publish URL docs v2 có an toàn?

**Đáp án:** Không chắc; method/fragment/package paths có thể không khớp. Đồng bộ versions.

### Bài 17. Platform docs

**Đề:** `--no-platform-links` làm gì trong demo?

**Đáp án:** Tránh sinh Java platform links để giảm phụ thuộc mạng; không phải default khuyến nghị cho docs production.

### Bài 18. Javadoc và Java compile

**Đề:** `javac --release 17` PASS nhưng `javadoc -Xdoclint:all` FAIL có mâu thuẫn?

**Đáp án:** Không. Java compiler kiểm code, Javadoc kiểm comments/references/HTML.

### Bài 19. Private Java API

**Đề:** Link đến private method trong public API docs có phải lỗi HTTP403?

**Đáp án:** Không; đây là visibility/publish scope vấn đề Java, không phải server authorization.

### Bài 20. Markdown documentation

**Đề:** Có thể dùng `/// See [java.util.List]` với demo Java17 không?

**Đáp án:** Không dùng trong demo; Markdown Javadoc comments được hỗ trợ ở JDK23+.

### Bài 21. HTTP link checker security

**Đề:** Vì sao không cho người ngoài nhập tùy ý URL để CI server kiểm?

**Đáp án:** SSRF có thể cho phép truy cập dịch vụ nội bộ qua runner; cần allowlist host/scheme và xử lý redirects.

### Bài 22. Quy trình release

**Đề:** Chỉ Javadoc exit0 đã đủ công bố API docs không?

**Đáp án:** Không. Kiểm generated HTML, relative links/fragments, publish staging và HTTP access theo đúng user role.

## 22. Checklist review và publish

- [ ] Biết link nào là Java symbol, link nào là docs-site base, link nào là arbitrary URL?
- [ ] Dùng `{@link}`/`{@linkplain}` cho Java elements, `<a href>` cho webpages?
- [ ] Các Java type/method references có fully-qualified name/signature đúng?
- [ ] Phân biệt `@see` block tag với `{@link}` inline tag?
- [ ] Có compiled dependencies trên classpath/module path của Javadoc process?
- [ ] Có đúng `-sourcepath`, `--module-source-path` theo build mode?
- [ ] `-link`/`-linkoffline` đều trỏ tới docs root, không phải class HTML page?
- [ ] Tham số hai `-linkoffline` là thư mục chứa `element-list`?
- [ ] Metadata được Javadoc sinh và cùng version external dependency?
- [ ] Có chạy `-Xdoclint:all -Werror` hoặc policy docs nghiêm tương ứng?
- [ ] Có không tắt toàn bộ DocLint chỉ vì warnings?
- [ ] Có không nhầm DocLint accessibility với HTTP access?
- [ ] Có phân loại `reference not found` và `element-list` I/O failure?
- [ ] Có kiểm generated HTML href thực, không chỉ javadoc exit0?
- [ ] Có kiểm local relative links, public version paths, redirects?
- [ ] Có kiểm member fragments/DOM IDs, không chỉ HTTP200?
- [ ] Có test anonymous cho public docs?
- [ ] Có kiểm SSO/service-account role cho internal docs?
- [ ] Có không nhúng secrets/signed URLs vào generated docs?
- [ ] Có link checker giới hạn redirects/timeouts/concurrency/backoff?
- [ ] Có không gộp HTTP403 và HTTP404 thành cùng “link dead”?
- [ ] Có không coi HEAD405 là GET failure?
- [ ] Có chống SSRF và credential leakage qua redirects?
- [ ] Có xác minh CA/TLS/proxy thay vì tắt certificate verification?
- [ ] Có kiểm modularity/layout khi dùng JPMS?
- [ ] Có pin JDK platform API docs theo Java baseline?
- [ ] Có phân biệt syntax JDK23+ `///` với Java17 Javadoc comments?
- [ ] Có staging link validation riêng trước promotion?
- [ ] Có owner, log, thời điểm và cách rollback khi link ngoài hỏng?

## 23. Tài liệu chính thức còn áp dụng

- [JDK 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): `-link`, `-linkoffline`, `--no-platform-links`, `-Werror`, `-Xdoclint` và options standard doclet hiện hành.
- [JDK 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): các flags và cơ chế tương thích với Java17 baseline.
- [JDK 25 — Documentation Comment Specification for Standard Doclet](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): `@see`, `{@link}`, `{@linkplain}`, Java references và HTML anchors.
- [JDK 25 — JavaDoc Tool](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-tool.html): Standard doclet, DocLint, nhấn mạnh cần proofread generated documentation.
- [Java SE 25 — `HttpClient`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP request, redirects và connection timeout.
- [Java SE 25 — `HttpRequest`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.html): HTTP methods và timeout mỗi request.
- [JDK 25 — `HttpServer`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): JDK module `jdk.httpserver` dùng làm loopback server test.
- [JEP 467 — Markdown Documentation Comments (JDK 23)](https://openjdk.org/jeps/467): hỗ trợ `///` và links Markdown mới vẫn áp dụng ở JDK hiện hành.
- [JDK 25 — Markdown in Documentation Comments](https://docs.oracle.com/en/java/javase/25/javadoc/using-markdown-documentation-comments.html): Java-element vs URL links trong Markdown Javadoc.
- [JDK 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release` và khác biệt DocLint giữa compiler và Javadoc.
- [JDK 25 — Package com.sun.source.doctree](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/doctree/package-summary.html): nếu cần xây tooling phân tích doc comments theo AST.

**Ghi nhớ:** Một external Javadoc link có thể **được tạo đúng** nhưng **không truy cập được**. `-link` đọc metadata từ docs URL; `-linkoffline` dùng metadata có sẵn, không chứng minh public URL hoạt động. `-Xdoclint:all -Werror` kiểm Java references và markup; HTTP/access checks phải là bước riêng sau build/publish, có phân loại 401/403/404, redirects, page version và method fragments. Không dùng cách tắt DocLint/TLS hoặc mở quyền private docs bừa bãi để “sửa link”.