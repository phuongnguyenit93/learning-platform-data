# `Runtime.version()` và `Runtime.Version` — đọc, phân tích và so sánh phiên bản Java

**Chủ đề:** Tiến hóa API từ Java 9 đến Java hiện đại. Bài học tập trung vào `Runtime.version()` và lớp bất biến `java.lang.Runtime.Version`: cách đọc phiên bản Java đang chạy, hiểu các thành phần của version string, so sánh các phiên bản và đưa ra quyết định tương thích. Các ví dụ Java dùng API còn được hỗ trợ, biên dịch ở mức Java 17+.

> **Điểm cốt lõi:** `Runtime.version()` trả về **phiên bản của Java runtime đang thực thi chương trình** dưới dạng đối tượng `Runtime.Version`. Bạn có thể lấy `feature()`, `update()`, `pre()`, `build()`, hoặc so sánh bằng `compareTo()` / `compareToIgnoreOptional()` thay vì tự tách chuỗi `"java.version"` bằng dấu chấm.

## 1. Vì sao Java cần một API phiên bản có cấu trúc?

Trước đây, ứng dụng thường dựa vào chuỗi `"java.version"` của system properties và tự xử lý dấu chấm, `_`, `-` hoặc tiền tố `1.`. Cách đó dễ lỗi khi định dạng version thay đổi và không xử lý nhất quán thông tin build, pre-release hay vendor. **Java 9** giới thiệu `Runtime.version()`, lớp `Runtime.Version` và cơ chế version-string mới (JEP 223).

**Từ Java 10**, Java chuyển sang mô hình phát hành theo thời gian, làm rõ ý nghĩa các trường `$FEATURE.$INTERIM.$UPDATE.$PATCH` (JEP 322). Do đó, tài liệu hiện hành khuyên dùng **`feature()` / `interim()` / `update()` / `patch()`**. Các accessor tên cũ `major()` / `minor()` / `security()` đã **deprecated từ Java 10**: đừng lấy chúng làm API trung tâm cho mã mới.

Ví dụ một runtime có thể báo:

```text
21.0.2+13-LTS
```

Đây không phải một số thực hay một chuỗi bạn có thể so bằng thứ tự từ điển. Các phần mang ý nghĩa riêng: `21` là feature release, `0` là interim, `2` là update, `13` là build, `LTS` là thông tin bổ sung do nhà phân phối cung cấp.

### Sự khác nhau giữa ba đối tượng

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Java runtime hiện tại** | `Runtime.version()` | Phiên bản JVM/JRE đang chạy **chính tiến trình này**. |
| **Một phiên bản Java được parse** | `Runtime.Version.parse("21.0.2+13-LTS")` | Đối tượng dữ liệu đại diện cho chuỗi phiên bản hợp lệ, **không cần** máy đã cài Java 21. |
| **Bộ biên dịch** | `javac --version` | Phiên bản compiler trên PATH; có thể khác runtime thực thi chương trình. |

`Runtime.Version` là **value-based class**: nên so giá trị với `equals(...)` hoặc `compareTo(...)`, không dùng `==` để so phiên bản và không dùng đối tượng này làm khóa cho `synchronized`.

## 2. Mẫu version-string hiện hành

Phần số phiên bản thông thường theo cấu trúc:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

| Thành phần | Ý nghĩa trên Java 10+ | Ví dụ từ `21.0.2` |
| --- | --- | --- |
| `$FEATURE` | Tăng khi phát hành một feature release mới của Java. | `21` |
| `$INTERIM` | Dành cho các đợt phát hành tương thích, không thay đổi API chuẩn theo định nghĩa scheme. | `0` |
| `$UPDATE` | Tăng cho các update release sửa lỗi, vấn đề bảo mật hoặc hồi quy. | `2` |
| `$PATCH` | Dành cho emergency patch release. | `0` nếu vắng mặt |

Các số có thể được rút gọn nếu các thành phần cuối đều bằng `0`. Bởi vậy **`21`** là chuỗi hợp lệ với feature `21`, interim/update/patch đều bằng `0`. **`21.0.2`** hợp lệ và có `.version()` bằng `[21, 0, 2]` — danh sách giữ số `0` ở giữa. **`21.0.0` không hợp lệ** theo cú pháp vì kết thúc bằng thành phần `0`; phiên bản tương ứng phải biểu diễn thành `21`.

Một số ví dụ hợp lệ theo schema:

```text
17
21.0.2
21.0.2+13
21.0.2+13-LTS
25-ea
25+8
25.0.1.1
```

Các thành phần thứ năm trở đi có thể tồn tại cho phần mở rộng của implementation, không nên mặc định mọi chuỗi phiên bản chỉ có bốn số. Những dấu chấm trong chuỗi **không** có ngữ nghĩa như dấu thập phân.

### Phần đuôi của version string

Thông tin ngoài số phiên bản được biểu diễn bằng các thành phần **tùy chọn**:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
```

Đây là sơ đồ đơn giản của các dạng hợp lệ trong Javadoc, với:

- `$VNUM`: phần số như `21.0.2`.
- `$PRE`: nhãn trước phát hành chính thức, chẳng hạn `ea` hoặc `internal`.
- `$BUILD`: số build, chẳng hạn `13`.
- `$OPT`: thông tin định danh bổ sung như `LTS` hoặc nhãn do vendor phát hành.

**Cẩn thận với dấu `-`:** trong `25-ea`, `ea` là **pre-release**. Trong `25+-ea`, `ea` thuộc **optional metadata**. Cách parse được quy định theo cú pháp, không thể phân loại bằng cách tìm một dấu gạch nối bất kỳ.

Nhãn `LTS` trong `21.0.2+13-LTS` là metadata, không phải bằng chứng độc lập rằng runtime nhận hỗ trợ bảo mật đến một ngày cụ thể. Chính sách vòng đời sản phẩm thuộc về nhà phân phối và hợp đồng hỗ trợ.

## 3. API quan trọng của `Runtime.Version`

Lớp này nằm trong `java.lang.Runtime`, nên không cần import riêng hoặc thêm dependency Maven/Gradle.

| API | Kiểu kết quả | Cách hiểu |
| --- | --- | --- |
| `Runtime.version()` | `Runtime.Version` | **Static** method của `Runtime`; thông tin runtime đang chạy. |
| `Runtime.Version.parse(String)` | `Runtime.Version` | Parse một chuỗi theo cú pháp phiên bản Java; báo lỗi nếu không hợp lệ. |
| `v.feature()` | `int` | Feature release, ví dụ `21`. |
| `v.interim()` | `int` | Interim component; trả `0` nếu vắng mặt. |
| `v.update()` | `int` | Update component; trả `0` nếu vắng mặt. |
| `v.patch()` | `int` | Patch component; trả `0` nếu vắng mặt. |
| `v.version()` | `List<Integer>` | Danh sách các số của phần `$VNUM`, không thể chỉnh sửa. |
| `v.pre()` | `Optional<String>` | Nhãn pre-release, có thể không có. |
| `v.build()` | `Optional<Integer>` | Số build, có thể không có. |
| `v.optional()` | `Optional<String>` | Phần metadata bổ sung, có thể không có. |
| `v.compareTo(other)` | `int` | So theo **toàn bộ** thành phần có thứ tự của phiên bản. |
| `v.compareToIgnoreOptional(other)` | `int` | So sánh nhưng **bỏ qua chỉ phần `$OPT`**. |
| `v.equals(other)` | `boolean` | Kiểm tra hai giá trị phiên bản bằng nhau toàn phần. |
| `v.equalsIgnoreOptional(other)` | `boolean` | Kiểm tra bằng nhau khi bỏ qua `$OPT`. |
| `v.toString()` | `String` | Biểu diễn lại phiên bản dưới dạng chuỗi. |

Các method `feature/interim/update/patch` có **`@since 10`**. Trong một bài học thuộc nhóm Java 9, cần hiểu rõ sự tiến hóa này: API `Runtime.Version` có từ Java 9, còn những accessor kể trên là cách tiếp cận **đang được khuyến nghị cho Java 10 trở đi**. Đây là lý do ví dụ sử dụng Java 17+ thay vì cố dạy getter đời đầu.

**Phân biệt tên gần giống:**

```java
Runtime.Version current = Runtime.version();  // Phiên bản runtime hiện tại.
java.util.List<Integer> numbers = current.version(); // Danh sách phần số.
```

`Runtime.version()` là phương thức `static` của `Runtime`; `current.version()` là phương thức **instance** của `Runtime.Version`.

### `Optional` không nên được thay bằng mặc định giả

Nếu `pre()` hoặc `optional()` vắng mặt, hãy dùng `.isPresent()`, `.orElse(...)` hoặc xử lý `Optional` rõ ràng. Với `build()`, việc không có build **không có nghĩa** build thực sự bằng `0`. `orElse(-1)` trong demo chỉ dùng để hiển thị dễ đọc; khi tạo policy hãy phân biệt vắng mặt với số cụ thể.

## 4. Ví dụ Java chạy độc lập: phân tích, lấy trường và so sánh

Tạo tệp `VersionDemo.java`:

```java
public class VersionDemo {
    public static void main(String[] args) {
        Runtime.Version v = Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version other = Runtime.Version.parse("21.0.2+13-vendor");
        Runtime.Version ea = Runtime.Version.parse("25-ea");
        Runtime.Version final25 = Runtime.Version.parse("25");

        System.out.println("Numbers: " + v.version());
        System.out.println("Feature: " + v.feature());
        System.out.println("Interim: " + v.interim());
        System.out.println("Update: " + v.update());
        System.out.println("Patch: " + v.patch());
        System.out.println("Pre: " + v.pre().orElse("none"));
        System.out.println("Build: " + v.build().orElse(-1));
        System.out.println("Optional: " + v.optional().orElse("none"));
        System.out.println("Ignore optional equality: "
                + v.equalsIgnoreOptional(other));
        System.out.println("Strict equality: " + v.equals(other));
        System.out.println("Ignore optional order: "
                + v.compareToIgnoreOptional(other));
        System.out.println("Final after EA: "
                + (final25.compareTo(ea) > 0));

        try {
            Runtime.Version.parse("21.0.0");
            System.out.println("Bad input accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("Trailing-zero rejected");
        }

        Runtime.Version current = Runtime.version();
        System.out.println("Runtime feature >= 17: "
                + (current.feature() >= 17));
        System.out.println("Minimum 21 reached: "
                + (current.compareToIgnoreOptional(
                        Runtime.Version.parse("21")) >= 0));
    }
}
```

Biên dịch và chạy từ thư mục chứa file, bằng JDK 17 trở lên:

```bash
javac --release 17 VersionDemo.java
java VersionDemo
```

**Kết quả thực nghiệm trên OpenJDK 24**:

```text
Numbers: [21, 0, 2]
Feature: 21
Interim: 0
Update: 2
Patch: 0
Pre: none
Build: 13
Optional: LTS
Ignore optional equality: true
Strict equality: false
Ignore optional order: 0
Final after EA: true
Trailing-zero rejected
Runtime feature >= 17: true
Minimum 21 reached: true
```

Hai dòng cuối **phụ thuộc runtime thực đang chạy**. Chẳng hạn `Minimum 21 reached` là `false` trên Java 17 hoặc Java 20, và `true` trên Java 21 trở lên có version được so phù hợp. Các dòng trước dùng chuỗi phiên bản cố định, nên có đầu ra xác định.

**Điều bạn vừa kiểm tra:**

1. `parse("21.0.2+13-LTS")` tạo đối tượng phiên bản hợp lệ; **máy không cần đang chạy JDK 21** để parse.
2. `version()` là `[21, 0, 2]`, trong khi `patch()` bằng `0` vì patch component bị lược ở cuối.
3. `pre()` vắng mặt, `build()` có số `13` và `optional()` là chuỗi `LTS`.
4. `equalsIgnoreOptional(other)` là `true` vì hai phiên bản chỉ khác phần metadata cuối: `LTS` và `vendor`. `equals(other)` là `false` vì so toàn bộ.
5. `compareToIgnoreOptional(...)` trả `0` dù hai phần optional khác nhau.
6. Phiên bản ổn định `25` được xếp sau pre-release `25-ea`.
7. `"21.0.0"` bị từ chối: không phải cứ “có dấu chấm” là version string hợp lệ.
8. `Runtime.version()` đọc **runtime đang thực thi**, không đọc giá trị `v` vừa parse.

## 5. Quy tắc so sánh phiên bản

`Runtime.Version` triển khai `Comparable<Runtime.Version>`; **không** nên dùng `String.compareTo()` để so Java versions. Các thành phần so sánh theo thứ tự:

1. **Version number**: so các số theo giá trị số nguyên từng vị trí, thay vì theo ký tự. Vì thế `21` lớn hơn `9`.
2. **Pre-release**: với cùng version number, bản có nhãn `pre` được xếp **trước** bản không có `pre` (bản ổn định).
3. **Build number**: với version number và pre-release tương đương, so số build theo giá trị số học; một phiên bản không có build được xếp trước phiên bản có build.
4. **Optional metadata**: `compareTo` còn so phần optional; `compareToIgnoreOptional` bỏ qua phần này.

Ví dụ:

| So sánh | Kết quả | Lý do |
| --- | --- | --- |
| `Runtime.Version.parse("9")` với `"21"` | `< 0` | So số `9` và `21`, không so chữ cái. |
| `"21.0.1"` với `"21.0.2"` | `< 0` | Update `1` nhỏ hơn `2`. |
| `"25-ea"` với `"25"` | `< 0` | Pre-release đứng trước bản ổn định cùng số. |
| `"21.0.2"` với `"21.0.2+13"` | `< 0` | Bản không build đứng trước bản có build khi các phần trước bằng nhau. |
| `"21.0.2+13-LTS"` với `"21.0.2+13-vendor"` | `compareTo` khác `0` | Optional metadata khác nhau. |
| Hai phiên bản ở dòng trên | `compareToIgnoreOptional == 0` | Chỉ bỏ qua `$OPT` là `LTS` và `vendor`. |
| `"21.0.2"` với `"21.0.2.1"` | `< 0` | Thành phần patch cuối của vế phải lớn hơn. |

**Điểm cần nhớ:** `compareToIgnoreOptional` **vẫn xét** số version, pre-release và build number. Tên của nó **không có nghĩa** “bỏ qua tất cả suffix”. Nếu muốn policy chỉ kiểm tra **feature release** (ví dụ Java 17+), hãy so `feature()`; nếu cần phiên bản update tối thiểu, dùng một đối tượng `Runtime.Version` đã parse và xác định rõ có cần phân biệt build hay không.

### Khớp cách so sánh và cách kiểm tra bằng nhau

- Dùng `compareTo()` cùng với `equals()` khi mọi thông tin, kể cả vendor optional metadata, đều có ý nghĩa.
- Dùng `compareToIgnoreOptional()` cùng với `equalsIgnoreOptional()` nếu bạn đã quyết định `$OPT` không có ý nghĩa đối với policy.
- Không lưu `Runtime.Version` trong `HashSet` rồi giả định `equalsIgnoreOptional()` là ngữ nghĩa của `HashSet`: collection mặc định dùng `equals()` và `hashCode()`, tức so **đầy đủ**. Nếu muốn nhóm theo quy tắc khác, phải tạo canonical key/comparator phù hợp với cấu trúc dữ liệu.
- Đừng dùng `==` để so hai `Runtime.Version`; lớp này có ngữ nghĩa dựa trên **giá trị**, không dựa trên identity.

## 6. Khi nào chỉ cần `feature()`, khi nào cần cả update/build?

**Tình huống A — tối thiểu Java 17 để chạy một ứng dụng:**

```java
Runtime.Version running = Runtime.version();
if (running.feature() < 17) {
    throw new IllegalStateException(
            "Application needs Java 17 or newer");
}
```

Đây là đoạn **minh họa** nằm trong phương thức. Nó có ích khi chỉ cần kiểm tra **dòng tính năng** Java và ứng dụng thực sự được xây dựng để chạy trên các dòng đó. Điều kiện không tự xác định patch bảo mật hay tình trạng support của bản phân phối.

**Tình huống B — yêu cầu update release tối thiểu:**

```java
Runtime.Version current = Runtime.version();
Runtime.Version minimum = Runtime.Version.parse("21.0.2");

if (current.compareToIgnoreOptional(minimum) < 0) {
    throw new IllegalStateException("Runtime update is too old");
}
```

Đoạn minh họa này chạy trong một phương thức. Logic sẽ coi các phiên bản `21.0.2+BUILD` không nhỏ hơn mốc `21.0.2`, vì build là thành phần so **sau** phần số. Nhưng nó cũng chấp nhận các feature release mới hơn 21 khi so theo thứ tự: quyết định ấy có thể đúng cho *minimum version*, nhưng không phù hợp khi cần pin **đúng một dòng Java**.

Nếu policy là **cần Java 21 và update >= 2**, hãy kiểm tra feature **và** update rõ ràng:

```java
Runtime.Version v = Runtime.version();
boolean isRequestedFamily = v.feature() == 21;
boolean updateEnough = v.update() >= 2;
boolean accepted = isRequestedFamily && updateEnough && v.pre().isEmpty();
```

Đoạn này cố ý giới hạn vào feature 21 và loại pre-release; **nó không tự đảm bảo** một vendor build cụ thể đã vá tất cả CVE. Chính sách bảo mật phải tham chiếu thông báo của nhà cung cấp runtime, ngày phát hành, cấu hình và hệ thống vá lỗi.

**Tình huống C — tùy chọn tính năng theo runtime:**

```java
Runtime.Version v = Runtime.version();
if (v.feature() >= 21) {
    System.out.println("Runtime is in the Java 21+ family");
}
```

Có thể dùng để điều chỉnh logging hoặc chọn một đường code đã được biên dịch hợp lệ cho runtime. Nhưng nếu chương trình **trực tiếp tham chiếu** tới một API hoặc cú pháp chỉ có ở Java 21 trong source được biên dịch bằng `javac --release 17`, lỗi có thể xảy ra **ngay lúc compile**, trước khi điều kiện chạy. Kiểm tra runtime không khiến API mới xuất hiện trên JDK cũ.

## 7. Liên hệ `Runtime.version()`, `java --version` và `System.getProperty`

Thực tế có nhiều vị trí hiển thị phiên bản Java:

```bash
java --version
javac --version
```

Và trong Java:

```java
Runtime.Version current = Runtime.version();
String javaVersion = System.getProperty("java.version");
String vendor = System.getProperty("java.vendor");
String javaHome = System.getProperty("java.home");
```

| Nguồn | Đang mô tả gì? | Dùng khi nào? |
| --- | --- | --- |
| `Runtime.version()` | Đối tượng phiên bản **của runtime đang chạy**. | So sánh cấu trúc, kiểm tra minimum version. |
| `System.getProperty("java.version")` | Chuỗi phiên bản Java runtime. | Log/diagnostic hoặc tương thích với code cũ. |
| `System.getProperty("java.version.date")` | Chuỗi ngày phát hành (nếu có, theo hợp đồng JDK). | Chẩn đoán/hỗ trợ chính sách; không thay kiểm tra cập nhật thực tế. |
| `System.getProperty("java.vendor")` | Nhà phân phối Java runtime. | Theo dõi môi trường triển khai. |
| `System.getProperty("java.vendor.version")` | Thông tin phiên bản riêng do vendor cung cấp, có thể vắng. | Chẩn đoán đặc thù cho nhà cung cấp. |
| `java --version` | Phiên bản chương trình `java` được gọi ở terminal. | Kiểm tra PATH/installation của shell đang dùng. |
| `javac --version` | Phiên bản compiler được gọi ở terminal. | Kiểm tra toolchain build. |

Trong môi trường có nhiều JDK/JRE, `java --version` của terminal có thể **khác** runtime mà IDE, service wrapper, build system hoặc container thực sự dùng. Khi phân tích lỗi production, log `Runtime.version()`, `java.vendor` và `java.home` trên **chính tiến trình ứng dụng**, tránh suy ra từ một máy khác.

**Sự phân biệt quan trọng:** `Runtime.Version.parse("25")` chỉ tạo dữ liệu phiên bản Java 25 hợp lệ; nó không nâng cấp JVM và không chứng minh code có quyền dùng API Java 25 khi đang chạy trên Java 17.

## 8. Xử lý lỗi parse và dữ liệu đầu vào không hợp lệ

`Runtime.Version.parse(String)` **xác thực cú pháp**, không cố dò một Java runtime đang cài trên máy. Một chuỗi hợp cú pháp có thể đại diện cho phiên bản chưa được phát hành hoặc metadata ví dụ; parse thành công không chứng minh nó tồn tại thực.

Các lỗi cần xét:

| Input/vấn đề | Hành vi/chú ý |
| --- | --- |
| `parse("21")` | Hợp lệ. |
| `parse("21.0.2+13-LTS")` | Hợp lệ. |
| `parse("21.0.0")` | Không hợp lệ vì trailing zero trong `$VNUM`. |
| `parse("21.01")` | Không hợp lệ do số có leading zero. |
| `parse("version 21")` | Không hợp lệ vì chứa tiền tố không thuộc grammar. |
| `parse(null)` | Ném `NullPointerException`. |
| Một component quá lớn để biểu diễn bằng `Integer` | Có thể ném `NumberFormatException`. |
| Chuỗi bất kỳ như `"v1.2.3"` từ hệ thống khác | Không mặc nhiên thuộc định dạng Java runtime version. |

Mã defensive khi nhận chuỗi phiên bản từ cấu hình:

```java
static Runtime.Version parseConfiguredVersion(String text) {
    try {
        return Runtime.Version.parse(text);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid Java version configuration: " + text, ex);
    }
}
```

Đây là **method độc lập để đặt trong một class Java**; cần gọi nó từ một nơi xử lý configuration hợp lệ. `NumberFormatException` là subtype của `IllegalArgumentException` nên catch này cũng xử lý trường hợp component vượt kích thước số nguyên. Một giá trị `null` cần được xử lý riêng nếu dữ liệu đầu vào có thể null.

**Không làm sạch đầu vào bằng cách tùy ý cắt sau dấu `-` hoặc `+` rồi parse:** như vậy có thể biến pre-release thành stable, bỏ thông tin build hoặc đọc sai ý nghĩa. Nếu bạn nhận output dài của `java --version`, hãy dùng **API có cấu trúc bên trong Java process**; nếu bắt buộc parse log bên ngoài, xác định rõ định dạng và nguồn cung cấp.

## 9. Phiên bản Java và tính tương thích khi biên dịch/triển khai

Một người mới học dễ rơi vào bẫy “runtime mới hơn nên chắc chắn chạy được” hoặc “đã có `Runtime.version()` nên có thể dùng mọi API đời mới”. Cần tách ít nhất bốn lớp:

1. **Source language level:** file `.java` đang dùng cú pháp gì; `--release` điều khiển mức ngôn ngữ và API nền tảng mà compiler được phép tham chiếu.
2. **Class-file version:** bytecode đã biên dịch yêu cầu JVM tối thiểu có thể tải nó. Nếu runtime quá cũ, có thể gặp `UnsupportedClassVersionError`.
3. **API availability:** một method/class có thể chỉ xuất hiện từ JDK sau; ngay cả khi bytecode load được, việc gọi API không tồn tại cũng có thể gây `NoSuchMethodError`/`NoClassDefFoundError`, tùy cách biên dịch và triển khai.
4. **Runtime behavior và dependencies:** thư viện/JNI/driver/agent, native OS, module access, preview features và các thay đổi platform đều có thể ảnh hưởng. `feature() >= 17` không thay thế kiểm thử tích hợp.

**Thực hành khuyến nghị:** Nếu mục tiêu support từ Java 17, biên dịch bằng:

```bash
javac --release 17 VersionDemo.java
```

Rồi thực sự chạy test trên các JDK được hỗ trợ, gồm ít nhất baseline và các dòng mục tiêu khác. Lệnh `--release` ngăn source Java 17 tham chiếu API platform chỉ được thêm ở Java mới hơn, trong khi `Runtime.version()` giúp ứng dụng quan sát runtime đang chạy.

Với thư viện phát hành cho nhiều Java features, có thể dùng cơ chế multi-release JAR hoặc phân nhánh implementation khi thật sự cần, nhưng `Runtime.version()` chỉ là **tín hiệu lựa chọn**. Không trông cậy vào một điều kiện `if` để làm một class chứa bytecode/APIs không tương thích có thể tải trên JVM cũ.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`Runtime.version()` trả về `String`.” | Giá trị trả về là `Runtime.Version`. | Gọi accessor có cấu trúc, `toString()` nếu cần log. |
| “`Runtime.Version.parse("21")` yêu cầu máy phải cài JDK 21.” | Parse là xử lý dữ liệu, không mở JVM khác. | Dùng parse cho version literals; dùng `Runtime.version()` cho JVM đang chạy. |
| “Java 9 có `feature()`.” | Accessor này được thêm từ Java 10. | Dạy API hiện hành và đặt baseline Java 17+. |
| “`major()/minor()/security()` là lựa chọn mới.” | Ba method đã deprecated từ Java 10. | Dùng `feature()/interim()/update()/patch()`. |
| “Có thể dùng `String.compareTo()` cho `"9"` và `"21"`.” | Thứ tự chữ khác thứ tự số. | Dùng `Version.compareTo(...)`. |
| “`version()` luôn trả đúng 4 số.” | Các phần số cuối bằng 0 được lược bỏ; có thể có phần mở rộng. | Dùng accessor hoặc xử lý danh sách đúng độ dài. |
| “`compareToIgnoreOptional()` bỏ qua cả build/pre.” | Nó chỉ bỏ qua `$OPT`. | Chọn đúng mức so sánh theo policy. |
| “`LTS` trong `optional()` bảo đảm nhà cung cấp còn hỗ trợ.” | Metadata không thay thế thông báo/vòng đời support. | Xác minh policy hỗ trợ từ vendor. |
| “`pre().isEmpty()` đồng nghĩa version đã an toàn.” | Không có pre label chưa chứng minh đủ security patches. | Theo dõi bản update và advisories cụ thể. |
| “Dùng `==` để so version.” | `Runtime.Version` là value-based. | Dùng `equals()` hoặc `compareTo()`. |
| “Kết quả `java --version` ở shell chính là runtime của service.” | PATH/IDE/container có thể dùng Java khác. | Ghi `Runtime.version()` trong service. |
| “`Runtime.version()` có thể bật API mới trên JVM cũ.” | Kiểm tra version không thay thế compile/class-loading. | Biên dịch, đóng gói, kiểm thử theo baseline và các JDK mục tiêu. |

## 11. Bài tập và kiểm tra kiến thức

1. Parse `"17.0.12+7"` rồi cho biết `feature`, `interim`, `update`, `patch`, `build` và `pre`. Tại sao `version()` chỉ có ba số?
2. So `"21-ea"` và `"21"` bằng `compareTo`. Tại sao code chỉ kiểm tra `feature() == 21` có thể nhận cả pre-release?
3. Hai chuỗi `"21.0.2+13-LTS"` và `"21.0.2+13-vendor"` khác nhau theo `equals()` không? Theo `equalsIgnoreOptional()` thì sao?
4. Vì sao `"21.0.0"` không phải version string hợp lệ, nhưng `Runtime.Version.parse("21").update()` vẫn trả `0`?
5. Một thư viện đặt yêu cầu Java 17+ và biên dịch bằng `javac --release 17`. Ngoài phép so `feature`, còn phải kiểm tra gì khi đóng gói và triển khai?
6. Khi production báo `Runtime.version() == 21.0.2+13` nhưng shell báo `java --version` là JDK 25, bạn cần điều tra vấn đề nào trước?
7. Với một policy chỉ so “phiên bản số” và không quan tâm vendor suffix, có thể dùng `compareToIgnoreOptional()` ngay không? Hãy suy nghĩ xem method vẫn xét pre-release và build number như thế nào.

**Định hướng đáp án:** (1) `17,0,12,0,7` và pre vắng, vì số patch cuối bằng 0 bị bỏ; (2) EA trước GA cùng feature, nên cần quan tâm `pre()` khi policy yêu cầu GA; (3) `equals` khác, `equalsIgnoreOptional` bằng; (4) grammar không cho trailing zero dù accessor có thể trả zero mặc định; (5) API/classfile/runtime/dependencies; (6) toolchain và PATH của service khác shell; (7) chỉ bỏ optional vendor metadata, chưa bỏ build/pre.

## 12. Tài liệu chính thức, còn áp dụng

- [Oracle Java SE 26 — `java.lang.Runtime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html) — `Runtime.version()` trả `Runtime.Version`.
- [Oracle Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html) — grammar, các accessor, parse, compare và semantics của value-based object.
- [Oracle Java SE 27 — Version-String Format](https://docs.oracle.com/en/java/javase/27/install/version-string-format.html) — mô hình `$FEATURE.$INTERIM.$UPDATE.$PATCH` hiện hành.
- [Oracle Java SE 27 — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html) — lịch sử thay đổi version scheme từ JDK 9 sang JDK 10+.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322) — lý do chuyển sang tên `feature/interim/update/patch`.
- [Oracle Java SE 17 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html) — baseline API đã đủ để chạy ví dụ.

**Ghi nhớ:** Để đọc phiên bản Java đang chạy, chọn `Runtime.version()`; để xử lý một phiên bản khác, chọn `Runtime.Version.parse(...)`. Khi so sánh, xác định bạn quan tâm **feature**, **update**, **pre-release**, **build** hay cả **optional metadata**, rồi dùng API tương ứng. Không cần xây trình phân tích version string thủ công, và không phụ thuộc các getter đã deprecated.
