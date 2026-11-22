# Javadoc `--override-methods`: phân biệt chế độ `summary` và `detail` (Java 10+)

## 1. Mục tiêu bài học

Khi sinh tài liệu API Java, một lớp con có thể **ghi đè (override)** rất nhiều phương thức từ lớp cha hoặc interface. Không phải lần override nào cũng thay đổi **hợp đồng API**: có phương thức chỉ tối ưu implementation nhưng giữ nguyên ý nghĩa, còn có phương thức bổ sung hành vi/điều kiện riêng cần người đọc thấy rõ.

Javadoc cung cấp tùy chọn chuẩn của **standard doclet**:

```bash
javadoc --override-methods detail ...
javadoc --override-methods summary ...
```

Hai chế độ điều khiển **cách trình bày các phương thức được override** trên trang tài liệu HTML được sinh ra.

- `detail`: trình bày phương thức override trong **phần chi tiết** của lớp, kể cả nhiều phương thức không thay đổi mô tả/hợp đồng. **Đây là mặc định**.
- `summary`: cho phép **thu gọn các override không làm thay đổi đặc tả API** về cách hiển thị tổng quan/nhóm phương thức thừa kế, giúp trang lớp con đỡ lặp lại nội dung. **Những override có đặc tả riêng vẫn có thể xuất hiện trong Method Details**.
- Tùy chọn này chỉ đổi **đầu ra tài liệu của standard doclet**; nó **không** sửa mã nguồn, không đổi dispatch tại runtime, không loại bỏ phương thức khỏi `.class` và không biến override thành inheritance.
- `summary` **không** có nghĩa “chỉ tạo trang tóm tắt, bỏ mọi phần chi tiết”; `detail` cũng **không** có nghĩa “sinh tài liệu cho cả private methods”.

Đây là cách sử dụng **vẫn được Oracle JDK 25 document hóa và chạy được trên JDK 24**. Bài tập thực nghiệm có đầy đủ mã Java 17+, ba lệnh `javadoc`, cách đọc HTML, một chương trình tự kiểm tra và kết quả đã xác minh.

**Điểm mấu chốt:** muốn kiểm soát tài liệu của lớp nhiều override, trước hết phải phân biệt **override giữ nguyên specification** với **override bổ sung specification riêng**. Hai chế độ không đơn giản là bật/tắt toàn bộ phần Method Detail.

## 2. Vì sao Javadoc cần tùy chọn này?

Xét một thư viện có lớp cơ sở `BaseService` cung cấp 30 phương thức. Lớp con `SpecialService` override 20 phương thức để ghi log, caching hoặc tối ưu hiệu năng nhưng **không thay đổi hợp đồng**; đồng thời nó override thêm một phương thức mà **hành vi được công bố khác**.

Nếu mọi override đều có khu vực chi tiết giống nhau, trang Javadoc của lớp con có thể dài và gây khó tìm các thay đổi thực sự đáng chú ý.

Vì vậy standard doclet cho phép lựa chọn một cách diễn đạt:

```text
Tài liệu lớp con SpecialService
|
+-- Method Summary
|     |
|     +-- Các phương thức lớp con cung cấp
|     +-- Các phương thức được kế thừa / override theo cách trình bày
|
+-- Method Details
      |
      +-- detail: override giữ nguyên spec cũng có detail
      +-- summary: override giữ nguyên spec có thể được thu gọn
      +-- cả hai: override có spec riêng vẫn được mô tả chi tiết
      +-- cả hai: phương thức mới của lớp con có detail
```

Sơ đồ chỉ mô tả ý nghĩa, không cam kết Javadoc HTML luôn có đúng một bảng hoặc tiêu đề tiếng Anh giống nhau. **Phiên bản JDK khác có thể đổi CSS, tab, anchor, heading**, nhưng hợp đồng của tùy chọn và mục đích học bài vẫn như trên.

### Đối tượng sử dụng

- Người viết thư viện muốn trang API của lớp con **ngắn và dễ tập trung**.
- Người làm tài liệu cần **so sánh Javadoc** trước và sau khi chuyển mode.
- Đội CI/CD muốn sinh API reference có layout nhất quán.
- Người bảo trì cần biết **khi nào một override cần bổ sung tài liệu riêng**, tránh ẩn thay đổi hành vi quan trọng.
- Người học Java 10 muốn hiểu một khả năng Javadoc được bổ sung trong giai đoạn Java 10 và vẫn dùng được trong JDK hiện hành.

Không nên chọn chế độ dựa trên tên flag mà không xem HTML thực; với thư viện public API, **trải nghiệm đọc tài liệu** mới là tiêu chí.

## 3. Cú pháp hiện hành và giá trị hợp lệ

Trong tài liệu Oracle JDK 25, cú pháp của standard doclet:

```text
--override-methods (detail|summary)
```

Nó có đúng hai mode:

| Mode | Ý nghĩa | Thực trạng |
| --- | --- | --- |
| `detail` | Tài liệu phương thức override trong phần chi tiết, kể cả các override chỉ kế thừa mô tả | **Mặc định** |
| `summary` | Giảm chi tiết lặp lại cho override không đổi đặc tả; nhóm/tóm tắt thay thế | **Tùy chọn chủ động** |

Các lệnh đều dùng được với standard doclet được kiểm chứng:

```bash
javadoc -d docs-detail --override-methods detail ...
javadoc -d docs-summary --override-methods summary ...
javadoc -d docs-default ...
```

Ở đây `...` đại diện các tham số source/package hợp lệ, không phải ký tự cần gõ nguyên vào terminal.

Cách viết GNU-style với dấu bằng cũng được Javadoc hiện hành hỗ trợ cho các long options:

```bash
javadoc --override-methods=summary -d docs-summary ...
```

**Không bỏ giá trị mode**, và không tự đặt `all`/`none`/`full` làm mode thứ ba. Nếu cung cấp giá trị không được chấp nhận, tool sẽ báo lỗi sử dụng, chứ không im lặng chọn mode khác.

**Lưu ý thuật ngữ lịch sử:** tài liệu phát hành JDK 10 từng nhắc cách viết cũ `--overridden-methods`. Trong bài học và lệnh cho **JDK hiện hành**, hãy theo đúng tên đang được launcher manual công bố: **`--override-methods`**. Không khuyến nghị sao chép syntax từ tài liệu cũ mà không kiểm tra JDK đang chạy.

## 4. `detail` — chế độ mặc định

Lệnh:

```bash
javadoc --override-methods detail -d docs-detail \
        -sourcepath src sample
```

Ở chế độ `detail`, các override của lớp con được mô tả trong **Method Details**. Người đọc có thể thấy chữ ký, mô tả, tham số/trả về và liên kết về phương thức mà nó ghi đè theo dữ liệu của standard doclet.

Điều này thuận tiện khi:

- Cần xem **từng phương thức override** mà không phụ thuộc cách nhóm summary.
- Muốn audit tài liệu lớp con theo method declaration.
- Đội duy trì API quen đọc vùng “Overrides” hoặc “Specified by” trong Method Details.
- Muốn bảo toàn layout chi tiết mặc định khi so sánh bằng hình hoặc HTML.

**Không đồng nghĩa** tất cả phương thức *được kế thừa nhưng không hề được override* của lớp con cũng xuất hiện thành từng đoạn chi tiết trong trang lớp con. Các phương thức đó thường được liên kết đến trang khai báo gốc ở superclass/interface. Cần phân biệt **overridden** với **inherited unchanged**.

Nếu không truyền option, default là `detail`:

```bash
javadoc -d docs-default -sourcepath src sample
```

Không nên khẳng định HTML của hai lệnh luôn **byte-for-byte giống nhau**: time stamps, liên kết vị trí output, metadata và các lựa chọn khác có thể tạo khác biệt. Điều đáng kiểm tra là **cách bố trí overridden methods**.

## 5. `summary` — thu gọn override không đổi đặc tả

Lệnh:

```bash
javadoc --override-methods summary -d docs-summary \
        -sourcepath src sample
```

Với một override **chỉ thừa hưởng hợp đồng tài liệu cũ**, Javadoc có thể nhóm nó vào khu vực phương thức kế thừa hoặc hiển thị nó như một mục summary thay vì tạo **Method Details** riêng cho lớp con.

Ví dụ một lớp con giữ nguyên tác dụng `normalize(String)` của lớp cha:

```java
/** {@inheritDoc} */
@Override
public String normalize(String value) {
    return value.strip();
}
```

Đây là một phương thức **minh họa trong lớp con**. Nếu documentation comment của lớp cha đã mô tả đầy đủ cách normalize, override này có thể không cần viết lại cùng hợp đồng ở phần chi tiết.

**Nhưng** với override viết **specification riêng**, ví dụ:

```java
/**
 * Returns the specialized mode instead of the base mode.
 *
 * @return the specialized mode
 */
@Override
public String mode() {
    return "special";
}
```

standard doclet vẫn có thể giữ **Method Details** cho phương thức đó ngay cả khi mode là `summary`, vì nội dung này không đơn thuần là lặp lại từ lớp cha.

**Đây là sự khác biệt quan trọng nhất của bài:** `summary` không phải quy tắc xóa tất cả đoạn chi tiết của tất cả method có `@Override`.

Trong thực nghiệm JDK 24 bên dưới, `normalize(String)` được thu gọn, nhưng `mode()` vẫn được trình bày chi tiết. `extra()` là phương thức hoàn toàn mới và cũng vẫn có chi tiết.

## 6. Ba khái niệm dễ nhầm: override, inherited method và Javadoc inheritance

| Khái niệm | Xảy ra ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Java overriding** | Ngôn ngữ/JVM | Lớp con cung cấp implementation cho instance method tương ứng |
| **Inherited but not overridden** | Quan hệ lớp/interface | Lớp con dùng phương thức có sẵn, không khai báo lại |
| **Javadoc comment inheritance** | Công cụ tài liệu | Mượn mô tả, `@param`, `@return`, `@throws` từ declaration được override nếu hợp lệ |
| **`--override-methods`** | Standard doclet | Quyết định cách bố trí HTML của overridden methods |

Ví dụ:

```java
class Base {
    public String name() { return "base"; }
    public String tag()  { return "tag"; }
}
class Child extends Base {
    @Override
    public String name() { return "child"; }
}
```

`Child.name()` là **override**; `Child.tag()` là **method được kế thừa nhưng không override**.

Tùy chọn Javadoc không sửa điều đó. Nếu ở `summary` và HTML của `Child` không còn một khối `Method Details` cho `name()`, bản thân mã Java **vẫn override** và runtime dispatch **vẫn gọi implementation của Child** theo quy tắc Java.

**Không dùng hình thức Javadoc để suy ra bytecode/API symbol đã bị xóa.** Để kiểm tra binary API, dùng build/tests, `javap` hoặc API compatibility checker phù hợp. Javadoc ở đây chỉ sinh mô tả HTML.

## 7. Vai trò của `@Override` và `{@inheritDoc}`

Hai cú pháp rất khác nhau:

### `@Override`

```java
@Override
public String normalize(String value) {
    return value.strip();
}
```

Đây là **annotation** được compiler kiểm tra để xác nhận method thật sự override/implement theo quy tắc ngôn ngữ. Nó không tự tạo nội dung documentation comment và không phải một cách chọn `summary` hay `detail`.

Nếu không có `@Override` nhưng method thực sự override hợp lệ, Javadoc vẫn có thể nhận biết quan hệ từ khai báo kiểu/method. **Không coi có annotation là điều kiện duy nhất để mode hoạt động.** Tuy nhiên, nên dùng `@Override` trong code mới để compiler cảnh báo khi tên/chữ ký không còn khớp.

### `{@inheritDoc}`

```java
/** {@inheritDoc} */
@Override
public String normalize(String value) {
    return value.strip();
}
```

Đây là **inline tag trong Javadoc comment**, nói rằng phần mô tả tương ứng được **kế thừa từ method được override** nếu hợp lệ. Nó không tạo ra implementation và không thay dispatch tại runtime.

Trong Javadoc hiện hành, nếu một method override bỏ thiếu một số phần documentation, các phần như **main description, `@param`, `@return` và `@throws`** có thể được **kế thừa ngầm** khi nguồn có sẵn và điều kiện hợp lệ. Theo đặc tả JDK 25, comment chỉ gồm `{@inheritDoc}` chủ động kế thừa **main description**, còn các mục khác có thể được kế thừa theo cơ chế omission.

**Lỗi thường gặp:** viết `{@inheritDoc}` ở một method **không override method nào có phần tương ứng**. Javadoc có thể báo lỗi DocLint/inheritance vì không xác định được nguồn mô tả hợp lệ.

**Lưu ý tinh tế:** một method có annotation `@Override` không đồng nghĩa nội dung documentation **không thay đổi hợp đồng**. Nếu override có đặc tả mới, cần document rõ khác biệt. Trong `summary`, standard doclet có thể giữ phần chi tiết cho nó, như ví dụ `mode()`.

## 8. Ví dụ đầy đủ: `BaseService` và `SpecialService`

Chúng ta sẽ tạo package `sample` gồm hai lớp, có ba kiểu method đáng quan sát:

- `normalize(String)`: lớp con override nhưng **kế thừa tài liệu** qua `{@inheritDoc}`.
- `mode()`: lớp con override và **mô tả hợp đồng riêng**.
- `extra()`: phương thức **mới**, không override.
- `inheritedOnly()`: method lớp cha không override, được **kế thừa nguyên**.

Cấu trúc thư mục:

```text
javadoc-override-demo/
├── src/
│   └── sample/
│       ├── BaseService.java
│       └── SpecialService.java
├── DocLayoutCheck.java
├── bin/                 (được tạo sau khi biên dịch)
├── detail/              (được javadoc tạo)
├── summary/             (được javadoc tạo)
└── default/             (được javadoc tạo)
```

Phần này chỉ cần **JDK 17+**, không cần Maven/Gradle hoặc thư viện ngoài. Các file và thư mục `bin/detail/summary/default` dùng cho ví dụ, không phải file có sẵn.

### 8.1. `src/sample/BaseService.java`

```java
package sample;

/** API for formatting and reporting. */
public class BaseService {
    /** Creates a base service. */
    public BaseService() { }

    /**
     * Removes surrounding whitespace from the supplied value.
     *
     * @param value input text
     * @return text without surrounding whitespace
     */
    public String normalize(String value) {
        return value.strip();
    }

    /**
     * Returns the standard service mode.
     *
     * @return the default mode
     */
    public String mode() {
        return "base";
    }

    /**
     * Returns a base-only marker.
     *
     * @return the inherited marker
     */
    public String inheritedOnly() {
        return "inherited";
    }
}
```

Chú ý ở Javadoc cha:

- `normalize` có **main description**, `@param` và `@return` đầy đủ. Đó là nguồn tài liệu cho `{@inheritDoc}` ở lớp con.
- `mode` trả giá trị mode mặc định, lớp con sẽ có mô tả khác.
- `inheritedOnly` là method mà lớp con **không khai báo lại**.
- Mỗi constructor public có Javadoc để `-Xdoclint:all` không báo thiếu mô tả constructor.

Đoạn mã dùng `String.strip()`, API hợp lệ trong Java 17+. Đây không phải cách tính whitespace cho mọi locale; đó chỉ là một behavior đơn giản để tập trung vào Javadoc.

### 8.2. `src/sample/SpecialService.java`

```java
package sample;

/** Specialized service with one documented override. */
public class SpecialService extends BaseService {
    /** Creates a special service. */
    public SpecialService() { }

    /** {@inheritDoc} */
    @Override
    public String normalize(String value) {
        return value.strip();
    }

    /**
     * Returns the specialized mode instead of the base mode.
     *
     * @return the specialized mode
     */
    @Override
    public String mode() {
        return "special";
    }

    /**
     * Returns the extra feature label.
     *
     * @return the extra label
     */
    public String extra() {
        return "extra";
    }
}
```

**Cách phân loại từng declaration:**

| Phương thức | Java relation | Tài liệu trong lớp con | Kỳ vọng khi `summary` |
| --- | --- | --- | --- |
| `normalize(String)` | Override | Chỉ `{@inheritDoc}`, cùng hợp đồng | Không cần khối Method Details riêng |
| `mode()` | Override | Mô tả/`@return` chuyên biệt | **Vẫn có** Method Details |
| `extra()` | Phương thức mới | Mô tả/`@return` riêng | **Vẫn có** Method Details |
| `inheritedOnly()` | Kế thừa, không override | Không có declaration ở lớp con | Không có Method Details ở lớp con |

**Quan trọng:** `normalize` thật sự override và gọi `String.strip()` ở cả cha/con, nên ý nghĩa code tương thích mô tả kế thừa. `mode()` trả mode mới, nên **tài liệu riêng** là có chủ đích; không nên ghi `{@inheritDoc}` đơn thuần rồi làm người đọc tin rằng hợp đồng luôn giống cha.

## 9. Sinh Javadoc ở cả ba chế độ

Đứng tại thư mục gốc `javadoc-override-demo` sau khi đã tạo hai file. Chạy:

```bash
javadoc -quiet -Xdoclint:all \
  --release 17 -encoding UTF-8 -notimestamp \
  -d detail --override-methods detail \
  -sourcepath src sample

javadoc -quiet -Xdoclint:all \
  --release 17 -encoding UTF-8 -notimestamp \
  -d summary --override-methods summary \
  -sourcepath src sample

javadoc -quiet -Xdoclint:all \
  --release 17 -encoding UTF-8 -notimestamp \
  -d default \
  -sourcepath src sample
```

Đây là các lệnh **Bash/sh**; nếu dùng PowerShell hoặc Windows CMD, có thể viết **mỗi lệnh trên một dòng** (không dùng `\` để xuống dòng):

```text
javadoc -quiet -Xdoclint:all --release 17 -encoding UTF-8 -notimestamp -d detail --override-methods detail -sourcepath src sample
javadoc -quiet -Xdoclint:all --release 17 -encoding UTF-8 -notimestamp -d summary --override-methods summary -sourcepath src sample
javadoc -quiet -Xdoclint:all --release 17 -encoding UTF-8 -notimestamp -d default -sourcepath src sample
```

**Giải thích từng option:**

| Option | Mục đích |
| --- | --- |
| `-quiet` | Giảm thông báo tiến trình, vẫn để warning/error có thể thấy |
| `-Xdoclint:all` | Phát hiện vấn đề documentation comment/link/HTML theo nhóm lint |
| `--release 17` | Xử lý source/API tương ứng release đích trong JDK có hỗ trợ |
| `-encoding UTF-8` | Xác định encoding của Java source comments |
| `-notimestamp` | Bỏ timestamp trong HTML comment để dễ so sánh output |
| `-d detail`/`summary`/`default` | **Ba thư mục HTML độc lập**, tránh ghi đè kết quả |
| `--override-methods detail` hoặc `summary` | Điều khiển bố cục override |
| `-sourcepath src sample` | Tìm nguồn của package `sample` trong `src` |

Sau khi chạy, mở bằng trình duyệt cục bộ:

```text
detail/sample/SpecialService.html
summary/sample/SpecialService.html
default/sample/SpecialService.html
```

**Không trộn lẫn đầu ra của ba lần chạy trong cùng thư mục.** Javadoc ghi HTML, stylesheet, index và một số file khác; ghi chồng làm phép so sánh khó tin cậy, nhất là khi file cũ còn tồn tại.

Javadoc hiện đại có thể tạo navigation/search UI khác bản cũ. Cần phân biệt phần **Method Summary** và **Method Details** thay vì đòi đúng vị trí pixel hoặc CSS class của một phiên bản JDK duy nhất.

## 10. Kết quả quan sát trên JDK 24 với source ở mục 8

Các file Java được chạy qua `javac --release 17` và Javadoc HotSpot JDK 24.0.2. Khi so hai trang `SpecialService.html`:

| Method trên trang `SpecialService` | `detail` | `summary` |
| --- | --- | --- |
| `normalize(String)`, chỉ `{@inheritDoc}` | Có Method Details | **Không** có Method Details riêng |
| `mode()`, comment đặc thù lớp con | Có Method Details | **Có** Method Details |
| `extra()`, method mới | Có Method Details | **Có** Method Details |
| `inheritedOnly()`, thừa kế nguyên | Không có Method Details riêng | Không có Method Details riêng |

Mặc định không truyền `--override-methods` tương đương `detail` về **quy tắc bố trí overridden methods**, và trong test JDK 24 có Method Details cho `normalize(String)`.

**Điểm dễ sai:** Nếu chỉ nhìn hai method `normalize` và `extra` rồi kết luận “summary xóa mọi override”, bạn sẽ bỏ qua `mode()` — chính nó chứng minh **override có hợp đồng riêng vẫn được tài liệu hóa chi tiết**.

**Không phải mất API:** Phương thức `normalize` vẫn nằm trong source, được `javac` biên dịch và được gọi khi code runtime dispatch. Chỉ có **khối tài liệu chi tiết trên trang HTML lớp con** được thu gọn.

**Không phải mất mô tả hoàn toàn:** Javadoc vẫn có cơ chế hiển thị/tìm được phương thức và tài liệu ở cấp thừa kế/tóm tắt; khi cần thông tin hợp đồng gốc, xem trang `BaseService`. Cách link/tab cụ thể thay đổi theo doclet version, nên phải xem trang HTML được sinh bởi JDK của dự án.

## 11. Chương trình Java 17+ kiểm tra sự khác biệt HTML

Vì nội dung Javadoc là **HTML**, ta không thể xác nhận mode có hiệu lực bằng cách chạy `java SpecialService` rồi xem stdout. Cần kiểm tra **đầu ra của công cụ tài liệu**.

Chương trình dưới đây là một **smoke test giới hạn cho HTML của JDK 24 đang kiểm chứng**, không phải HTML parser tổng quát. Nó tìm anchor của những phương thức trong **vùng Method Details**, qua các `id` mà standard doclet phát hành ở phiên bản đã thử.

Tạo file `DocLayoutCheck.java` tại gốc `javadoc-override-demo`:

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class DocLayoutCheck {

    static boolean detailed(Path page, String signature)
            throws Exception {
        String html = Files.readString(page);
        int methodDetail = html.indexOf("id=\"method-detail\"");
        return methodDetail >= 0
                && html.indexOf(
                        "id=\"" + signature + "\"",
                        methodDetail) >= 0;
    }

    static void require(boolean passed, String message) {
        if (!passed) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]);

        Path detail = root.resolve(
                "detail/sample/SpecialService.html");
        Path summary = root.resolve(
                "summary/sample/SpecialService.html");
        Path defaults = root.resolve(
                "default/sample/SpecialService.html");

        boolean dNormalized = detailed(
                detail, "normalize(java.lang.String)");
        boolean sNormalized = detailed(
                summary, "normalize(java.lang.String)");
        boolean dMode = detailed(detail, "mode()");
        boolean sMode = detailed(summary, "mode()");
        boolean sExtra = detailed(summary, "extra()");
        boolean defaultNormalized = detailed(
                defaults, "normalize(java.lang.String)");

        boolean inheritedNoDetail =
                !detailed(detail, "inheritedOnly()")
                && !detailed(summary, "inheritedOnly()");

        System.out.println(
                "detail.normalizeInDetails=" + dNormalized);
        System.out.println(
                "summary.normalizeInDetails=" + sNormalized);
        System.out.println(
                "detail.modeInDetails=" + dMode);
        System.out.println(
                "summary.modeInDetails=" + sMode);
        System.out.println(
                "summary.extraInDetails=" + sExtra);
        System.out.println(
                "default.normalizeInDetails=" + defaultNormalized);
        System.out.println(
                "inheritedOnly.hasNoDetails=" + inheritedNoDetail);

        require(dNormalized
                        && !sNormalized
                        && dMode
                        && sMode
                        && sExtra
                        && defaultNormalized
                        && inheritedNoDetail,
                "Unexpected javadoc method layout");

        System.out.println("tests=PASS");
    }
}
```

Lệnh biên dịch và chạy (sau khi đã sinh đủ ba thư mục HTML):

```bash
javac --release 17 -d bin DocLayoutCheck.java
java -cp bin DocLayoutCheck .
```

Đây là output **thực tế đã kiểm chứng trên JDK 24**:

```text
detail.normalizeInDetails=true
summary.normalizeInDetails=false
detail.modeInDetails=true
summary.modeInDetails=true
summary.extraInDetails=true
default.normalizeInDetails=true
inheritedOnly.hasNoDetails=true
tests=PASS
```

**Giải thích:**

1. `detail.normalizeInDetails=true`: override kế thừa comment vẫn có detail ở mode mặc định.
2. `summary.normalizeInDetails=false`: override không thay đổi specification được thu gọn.
3. `detail.modeInDetails=true` và `summary.modeInDetails=true`: override có comment hợp đồng riêng **vẫn được giữ detail**.
4. `summary.extraInDetails=true`: method mới có detail bình thường.
5. `default.normalizeInDetails=true`: default match mode `detail` theo ý nghĩa thiết yếu.
6. `inheritedOnly.hasNoDetails=true`: method không override không bị ép thành detail riêng ở trang con.
7. `tests=PASS`: các điều kiện quan sát được thỏa trong cấu hình JDK đã thử.

**Quan trọng với CI:** anchor strings, bố cục HTML và class/id có thể thay đổi theo JDK/doclet. Không khuyến nghị giữ script substring này làm **tiêu chuẩn lâu dài** cho mọi Javadoc release. Trong sản phẩm, test cấu trúc HTML bằng công cụ phân tích DOM phù hợp, hoặc dùng snapshot test đã được quản lý theo version, đồng thời kiểm tra đầy đủ hyperlink và nội dung. Script trên là phép **minh họa có thể tái lập với JDK 24**.

Chương trình kiểm tra layout không tự sửa tài liệu, không ghi vào source Javadoc và không cần mạng.

## 12. Nếu method override có comment mới nhưng chỉ đổi cách triển khai?

Ví dụ một subclass dùng thuật toán nhanh hơn nhưng **hợp đồng công bố cho người dùng không đổi**:

```java
/** {@inheritDoc} */
@Override
public String normalize(String value) {
    return value.strip();
}
```

Đây là ứng viên thích hợp cho `summary`. Nhưng nếu comment lớp con nêu điều kiện/ràng buộc mới, ví dụ độ dài tối đa hoặc trạng thái exception khác, thì cần mô tả cụ thể:

```java
/**
 * Returns a specialized label for this service.
 *
 * @return the specialized label
 */
@Override
public String mode() {
    return "special";
}
```

Khi dùng `summary`, Javadoc đã thử trên JDK 24 **vẫn giữ detail** cho override đó. Vì vậy không phải **cứ annotation `@Override` là bị gộp**.

**Không cố viết lại comment chỉ để ép layout** nếu điều đó làm tài liệu không còn phản ánh hành vi thực. Nội dung đúng của API contract quan trọng hơn việc giấu một method vào mục tóm tắt.

Nếu một override **đổi preconditions, postconditions hoặc checked exception behavior**, xem thêm quy tắc Java overriding và nghĩa của API contract; không chỉ dựa vào mode Javadoc để quyết định việc thay đổi có tương thích hay không.

## 13. `{@inheritDoc}` và implicit inheritance: tránh nhầm nguồn tài liệu

Đặc tả Oracle JDK 25 về doc-comment inheritance đưa ra các nguyên tắc:

- Một overriding method có thể kế thừa **main description**, ``@param`, ``@return` và ``@throws` tương ứng nếu nguồn tài liệu hợp lệ.
- Nếu comment bỏ thiếu một mục có thể được kế thừa, Javadoc coi mục đó như được cung cấp qua `{@inheritDoc}`.
- Comment chỉ chứa `{@inheritDoc}` chủ động ghi phần **main description**; các mục khác được kế thừa theo omission nếu đủ điều kiện.
- Khi không có method cha hợp lệ hoặc thiếu nội dung tương ứng để inherit, Javadoc có thể báo lỗi, không nên giấu bằng `-quiet`.
- `@Override` là annotation ngôn ngữ; `{@inheritDoc}` là tag tài liệu; chúng giải quyết hai bài toán khác nhau.

Ví dụ `BaseService.normalize` có:

```java
/**
 * Removes surrounding whitespace from the supplied value.
 *
 * @param value input text
 * @return text without surrounding whitespace
 */
public String normalize(String value) {
    return value.strip();
}
```

Và `SpecialService.normalize`:

```java
/** {@inheritDoc} */
@Override
public String normalize(String value) {
    return value.strip();
}
```

Khi sinh doc với `-Xdoclint:all` trong môi trường đã thử, phương thức con có thể nhận mô tả kế thừa hợp lệ. Trong mode `summary`, doclet quyết định hiển thị ngắn gọn, nhưng **việc Javadoc inheritance không ngừng hoạt động**.

**Lưu ý về mã nguồn:** nếu lớp cha nằm trong dependency binary và source/documentation của nó không sẵn có trên source path hoặc external docs, không thể mặc định mọi đoạn Javadoc sẽ được kế thừa. Oracle mô tả khi dùng `inheritDoc`, **source file** chứa tài liệu cần kế thừa phải có thể truy cập theo source path phù hợp. Khi thiếu, việc tổng hợp API docs có thể lỗi hoặc mất mô tả; phải sửa nguồn documentation, không chỉ đổi `summary/detail`.

## 14. Khi nào nên chọn `detail`?

Chọn `detail` hoặc giữ default nếu:

- Tài liệu dành cho người bảo trì implementation, muốn xem mỗi overriding declaration tại lớp con.
- Cần audit class hierarchy theo các method override cụ thể.
- Đội review sử dụng liên kết trực tiếp tới **Method Details** của lớp con.
- Muốn tránh thay đổi anchor/layout đáng kể khi đang có liên kết tài liệu ở ngoài.
- Số lượng override không quá nhiều, nên detail không gây rối.
- Có yêu cầu xuất bản tài liệu chi tiết và muốn cấu hình explicit dễ đọc trong build.

Ví dụ:

```bash
javadoc -Xdoclint:all --override-methods detail \
  -d build/docs/api -sourcepath src sample
```

Trong dự án thực, nên khóa release target, encoding và tham số build cùng toolchain JDK; không dựa vào máy developer ngẫu nhiên. `detail` là mode mặc định theo manual JDK 25, nhưng ghi rõ trong pipeline có thể giúp người đọc hiểu chủ đích.

**Không có nghĩa detail “luôn nhiều thông tin hơn về specification thực tế”**. Nếu overriding method chỉ inherit mô tả, một đoạn detail lặp lại có thể không cung cấp thêm thông tin hữu ích so với trang cha.

## 15. Khi nào nên chọn `summary`?

Chọn `summary` nếu:

- API có nhiều lớp con override những method **giữ nguyên hợp đồng**.
- Người dùng thư viện cần thấy **khác biệt có ý nghĩa**, không phải hàng chục đoạn lặp cùng Javadoc.
- Muốn trang subclass dễ điều hướng tới các phương thức được bổ sung hoặc thay đổi specification.
- Đã xem HTML sinh ra và xác nhận những override quan trọng **vẫn có mô tả đúng mức**.
- Có test/snapshot cho documentation quality theo JDK đang dùng.

Ví dụ:

```bash
javadoc -Xdoclint:all --override-methods summary \
  -d build/docs/api -sourcepath src sample
```

**Không khuyến nghị** chọn summary mà không xem output khi có method công bố điều kiện mới. Nếu tài liệu đặc thù bị thu gọn ngoài ý muốn vì comment sai/thiếu, cần chỉnh comment để phản ánh đúng API contract trước khi xuất bản.

**Không nên tuyên bố summary làm output JAR nhỏ hơn, chương trình chạy nhanh hơn hay rút bớt code.** Đây là cấu hình của quá trình tạo **HTML reference**, không phải tối ưu runtime.

## 16. Đọc đúng trang Javadoc được sinh

Sau khi mở `summary/sample/SpecialService.html`:

1. Tìm **Method Summary**.
2. Xem mục liên quan phương thức được **declared/inherited**.
3. Xác định có thể tìm hoặc nhấp đến `normalize(String)` và tới tài liệu nguồn ở `BaseService` hay không.
4. Cuộn xuống **Method Details**.
5. Kiểm tra `mode()` vẫn có phần mô tả riêng.
6. Kiểm tra `extra()` có detail vì là method mới.
7. So với `detail/sample/SpecialService.html` để nhìn khác biệt của `normalize(String)`.
8. Xem `default/sample/SpecialService.html` để đối chiếu default.

**Đừng dùng việc một method không có heading detail riêng làm kết luận “method biến mất khỏi public API”.** Hãy nhìn cả phương thức trong phần tóm tắt, liên kết tới nguồn kế thừa và source code.

Trong standard doclet, “Overrides” và “Specified by” có ý nghĩa khác nhau theo quan hệ superclass và interface; nếu khối detailed documentation bị thu gọn, vị trí các nhãn/liên kết tương ứng cũng có thể khác. Điều đó là **trình bày**, không phải thay đổi quan hệ inheritance/implementation.

### Ba mức kiểm tra

- **Nội dung:** comment có đủ, đúng nghĩa, link tới method/parameter hợp lệ?
- **Bố cục:** override vô nghĩa có được thu gọn, override đặc thù còn chi tiết?
- **Khả năng sử dụng:** search, index, link và navigation vẫn dẫn người đọc tới API cần tìm?

Không nên chỉ đếm số ký tự HTML vì output thay đổi do các yếu tố khác như styling, version và index metadata.

## 17. Kết hợp với `-Xdoclint:all` và `-Werror`

Javadoc hiện đại hỗ trợ **DocLint** để phát hiện vấn đề của documentation comments; có thể dùng:

```bash
javadoc -Xdoclint:all --override-methods summary \
  -d docs -sourcepath src sample
```

Nếu dự án yêu cầu không có warning, có thể bật thêm:

```bash
javadoc -Xdoclint:all -Werror \
  --override-methods summary \
  -d docs -sourcepath src sample
```

**Lưu ý về `-Werror`:** flag sẽ báo lỗi khi có warning, bao gồm cả những cảnh báo không trực tiếp liên quan `--override-methods`. Với dự án đang tồn đọng lỗi comment, cần xử lý warning có chủ đích; không bật `-quiet` để che cảnh báo và cũng không lạm dụng tắt toàn bộ DocLint.

Các vấn đề thường gặp:

- `{@inheritDoc}` không tìm được comment cha hợp lệ.
- Thiếu `@param` hoặc `@return` của non-overriding method.
- Link Javadoc `{@link ...}` sai.
- Dùng HTML sai cấu trúc trong doc comment.
- Comment mô tả khác hành vi thật (DocLint không thể tự hiểu mọi semantics, nên review thủ công vẫn cần).

**Tác dụng của `--override-methods` không bao gồm tự sửa những lỗi này**. Chỉ đổi vị trí mô tả; chất lượng văn bản Javadoc vẫn do tác giả và quy trình QA đảm bảo.

## 18. Dùng trong Maven hoặc Gradle ở thời điểm hiện hành

Lệnh `javadoc` là chuẩn nền để hiểu; trong dự án thật nên truyền options qua cấu hình công cụ build và khóa **JDK toolchain**.

### Maven Javadoc Plugin

Maven Javadoc Plugin có cơ chế khai báo **additional options** cho executable Javadoc của JDK đang dùng. Các tên cấu hình plugin có thể thay đổi theo phiên bản plugin; cần tra **tài liệu plugin của phiên bản thực tế** khi triển khai. Một cách ít mơ hồ là kiểm tra **effective Javadoc command**/plugin configuration rồi xác nhận nó có:

```text
--override-methods summary
```

Và chạy doc generation bằng **JDK được chọn trong build/toolchains**; đừng trộn compiler JDK 17 với một Javadoc binary không rõ version rồi so layout.

Không copy XML plugin không được chứng thực bởi version hiện dùng. Cách xác nhận đúng là xem tài liệu Maven Javadoc Plugin tương ứng, sinh HTML và kiểm tra kết quả.

### Gradle Javadoc task

Gradle có `Javadoc` task và có thể thêm options của Javadoc tool. Cách cấu hình phụ thuộc Gradle version, JVM toolchain và loại option (boolean, string, multivalue); nên kiểm tra generated command line và output theo docs Gradle hiện tại.

Về mục tiêu, cần đạt:

```text
Javadoc task executes a JDK javadoc tool
  with --override-methods summary
  on the intended source tree and release
  then writes HTML to a deterministic output directory
```

Không coi việc Gradle/Maven có task tên “javadoc” là bằng chứng flag của **standard doclet** đã được truyền đúng. **Kiểm tra HTML thực** theo một ví dụ override đã biết.

### CI repeatability

Nếu tài liệu là deliverable, nên xác định:

- JDK vendor/build cho tool `javadoc`.
- Source/release target.
- Encoding UTF-8 cho comments.
- Tên mode explicit.
- Output directory sạch, không sót HTML của build cũ.
- Kết quả `-Xdoclint:all` và cảnh báo.
- Snapshot/HTML inspection cho vài class đại diện.

Tùy chọn này là **định dạng tài liệu**, không phải một phần của cách đóng gói bytecode.

## 19. Những lỗi hiểu nhầm thường gặp

| Cách hiểu sai | Thực tế | Cách kiểm tra |
| --- | --- | --- |
| “`summary` xóa hết mọi override khỏi Method Details.” | Override có specification riêng **có thể vẫn ở detail** | `mode()` trong ví dụ |
| “`detail` nghĩa là Javadoc cho mọi private method.” | Đây là chế độ bố trí override, không phải visibility | Dùng `--show-members`/`-private` khi cần theo policy |
| “Mặc định là summary.” | Theo manual JDK 25, **mặc định là detail** | Sinh doc không flag và so với detail |
| “`--override-methods=full` là mode hợp lệ.” | Chỉ `summary` hoặc `detail` | Xem `javadoc --help` của JDK |
| “`@Override` và `{@inheritDoc}` tương đương.” | Một cái annotation Java, một cái Javadoc tag | Kiểm tra compilation và generated docs |
| “Không có `@Override` thì Javadoc không biết có override.” | Quan hệ override do khai báo kiểu/method quyết định | Xem signature và JLS |
| “`summary` làm Java dispatch gọi method cha.” | Javadoc không tác động runtime | Chạy unit test dispatch |
| “Method ở summary nghĩa code method bị xóa.” | Chỉ thay layout HTML | Kiểm tra `javap`/source |
| “`-Xdoclint:all` là lựa chọn thứ ba của override-methods.” | DocLint là nhóm flag độc lập | Đọc lệnh Javadoc |
| “Mọi override đều có comment kế thừa hợp lệ.” | Có thể thiếu nguồn docs hoặc thay đổi contract | Review `{@inheritDoc}` |
| “Inherited method và overridden method giống nhau.” | Một loại không khai báo lại, loại kia có declaration mới | Nhìn `extends`/`@Override` |
| “Chỉ cần số lượng Method Details ít hơn thì QA đạt.” | Cần thấy thay đổi đúng method, spec còn đủ, links hoạt động | Test positive/negative |
| “HTML anchor sẽ cố định trên mọi JDK tương lai.” | Doclet có thể đổi cấu trúc output | Test theo toolchain; ưu tiên DOM |
| “Chuyển mode giúp giảm dung lượng JAR.” | Sinh documentation HTML, không tác động compiled artifact | So bytecode/output JAR |
| “Đặt `-quiet` là không có warning.” | `-quiet` chỉ giảm thông báo bình thường | Kiểm tra exit code, dùng DocLint/Werror |
| “Cần dùng JDK 10 vì tùy chọn xuất hiện từ Java 10.” | Flag còn dùng được trên JDK mới | Chạy JDK được bảo trì |

## 20. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài 1: dự đoán chi tiết của method kế thừa comment

Một lớp con có:

```java
/** {@inheritDoc} */
@Override
public String normalize(String value) {
    return value.strip();
}
```

**Hỏi:** sau khi sinh `--override-methods summary`, nó có bắt buộc còn một Method Details riêng không?

**Đáp án:** Không. Trong ví dụ JDK 24 đã kiểm chứng, method chỉ thừa hưởng specification được thu gọn, không có detail riêng trên trang lớp con; ở `detail` thì có.

### Bài 2: override có mô tả riêng

```java
/**
 * Returns the specialized mode instead of the base mode.
 * @return the specialized mode
 */
@Override public String mode() {
    return "special";
}
```

**Hỏi:** `summary` có chắc xóa detail của method này không?

**Đáp án:** Không. Trong ví dụ đã thử, `mode()` vẫn nằm ở Method Details vì có đặc tả chuyên biệt. Điều này cho thấy logic của doclet **không chỉ dựa vào annotation `@Override`**.

### Bài 3: method được kế thừa không override

`BaseService` có `inheritedOnly()`; `SpecialService` không khai báo lại.

**Hỏi:** vì sao cả `detail` và `summary` đều không cần khối detail riêng của method đó trên trang `SpecialService`?

**Đáp án:** Vì đó là method **được kế thừa nguyên**, không phải override declared in subclass. Người đọc có thể xem tài liệu ở superclass.

### Bài 4: `@Override` và `{@inheritDoc}`

**Hỏi:** annotation và Javadoc tag khác nhau thế nào?

**Đáp án:** `@Override` giúp compiler kiểm tra một method thật sự override; `{@inheritDoc}` yêu cầu kế thừa phần comment thích hợp. Cả hai **không** chọn mode; mode do tham số `javadoc` quyết định.

### Bài 5: default

```bash
javadoc -d docs -sourcepath src sample
```

**Hỏi:** JDK 25 standard doclet mặc định chọn mode gì?

**Đáp án:** `detail`. Thêm `--override-methods detail` chủ yếu làm quyết định ấy rõ ràng trong script.

### Bài 6: yêu cầu build reproducible

**Hỏi:** hai lần sinh doc khác mode nhưng cùng thư mục `-d docs`, sau đó kiểm tra số h3 trong HTML. Có đáng tin không?

**Đáp án:** Không nên. File còn sót từ run trước hoặc metadata khác có thể làm phép đo nhiễu. Dùng **hai output directories sạch**, cùng JDK/source/options trừ mode, rồi so vùng Method Details của class đại diện.

### Bài 7: bài tập mở rộng interface

Tạo interface `Formatter` có method `format(String)` và một class implements nó. Dùng `{@inheritDoc}` ở implementation; sinh hai mode và kiểm tra cách Javadoc hiển thị `Specified by` hoặc liên kết tới interface method.

**Đáp án tham khảo:** Quan hệ “implements/overrides method interface” là quan hệ type system; Javadoc có thể sinh nhãn `Specified by` trong detailed documentation. Khi thay mode, bố cục/link có thể khác nhưng method implementation **không bị xóa**. Trước khi kết luận trường hợp cụ thể, hãy kiểm tra HTML đầu ra của JDK/standard doclet đang dùng.

### Bài 8: API docs trong thư viện public

**Hỏi:** thư viện có nhiều override chỉ khác implementation, tài liệu lớp con dài nhưng người đọc cần thấy method có hợp đồng thay đổi. Nên thử mode nào?

**Đáp án:** Thử `summary`, kết hợp review các method thay đổi specification và kiểm tra links/DocLint. Không chuyển mode mà bỏ review documentation comments.

## 21. Checklist QA trước khi xuất bản Javadoc

1. Dùng **JDK javadoc hiện hành**, kiểm tra toolchain và `javadoc --help`.
2. Dùng đúng option **`--override-methods`**, giá trị `detail` hoặc `summary`.
3. Biết mặc định là `detail`; ghi explicit nếu pipeline cần rõ.
4. Xác định source/package path và target release, encoding.
5. Phân biệt method override, inherited unchanged và method mới.
6. Đảm bảo method override có **specification riêng** được mô tả đầy đủ.
7. Nếu dùng `{@inheritDoc}`, xác nhận nguồn comment cha có thể được tìm thấy và hợp lệ.
8. Sinh riêng hai bộ output `detail`/`summary`, không ghi đè.
9. So **Method Summary** và **Method Details** của vài class đại diện.
10. Kiểm tra override không đổi spec được thu gọn như mong đợi ở mode `summary`.
11. Kiểm tra override có spec riêng **vẫn có detail** và nội dung chính xác.
12. Kiểm tra method mới và inherited-only vẫn được điều hướng đúng.
13. Dùng `-Xdoclint:all` để tìm lỗi documentation; xem warning/error thực.
14. Nếu dùng `-Werror`, xem đó là policy build riêng, không phải chế độ thứ ba của override.
15. Không diễn giải việc thiếu một HTML anchor thành việc Java API/bytecode bị xóa.
16. Nếu kiểm thử HTML tự động, **khóa JDK/doclet version** hoặc dùng parser/snapshot có bảo trì.
17. Khi đổi mode trên public docs, kiểm tra những **external deep links** cũ tới method details.
18. Xác nhận generated docs không lộ mã nội bộ ngoài ý định do các option khác như `-linksource`.
19. Chỉ chọn mode sau khi xem chất lượng tài liệu thật; không tối ưu số dòng HTML bằng mọi giá.

## Kết luận

`--override-methods` là tùy chọn **standard doclet của Javadoc** điều khiển cách hiển thị các **phương thức đã được override**:

- **`detail` (mặc định):** các override được trình bày trong phần Method Details.
- **`summary`:** thu gọn nhiều override **không đổi API specification**, để trang lớp con tập trung vào API đáng chú ý; một override **có mô tả riêng vẫn có thể được giữ Method Details**.
- Hai mode **không thay đổi code Java, quan hệ override, runtime dispatch, bytecode, visibility hay hoạt động của GC/JVM**.

Ví dụ Java 17+ đã được sinh và kiểm tra trên JDK 24: `normalize()` với `{@inheritDoc}` bị thu gọn ở `summary`, `mode()` với specification riêng và `extra()` vẫn có detail, còn default trùng với `detail` về bố cục cần kiểm tra. Đây là kiến thức **vẫn áp dụng trong Javadoc hiện đại** và giúp đội dự án chọn cách trình bày tài liệu API chính xác thay vì sao chép những option hoặc giả định lỗi thời.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 — `javadoc` command, `--override-methods (detail|summary)`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): hai mode được hỗ trợ, mode mặc định `detail` và các tùy chọn standard doclet.
- [Oracle Java SE 25 — JavaDoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): `{@inheritDoc}`, comment inheritance by omission, main description/`@param`/`@return`/`@throws` và quy tắc overriding methods.
- [Oracle Java SE 25 — Standard Doclet Output](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): mối quan hệ method inheritance, “Overrides” và “Specified by”.
- [Oracle Java SE 25 — API Help](https://docs.oracle.com/en/java/javase/25/docs/api/help-doc.html): bố cục Method Summary, Method Details và trang API HTML.
- [Oracle JDK 10 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): bối cảnh lịch sử việc bổ sung tùy chọn nhóm overriding methods; với code hiện nay dùng tên option ở JDK 25 manual.
- [Java SE 17 — `String.strip()` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip()): phương thức Java 17+ dùng trong ví dụ demo.
