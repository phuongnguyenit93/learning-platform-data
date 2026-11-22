# pre(), build() và optional() trong Runtime.Version (Java 10+)

## 1. Bài toán: một phiên bản Java có nhiều phần thông tin khác nhau

Khi kiểm tra JDK hoặc JVM, bạn có thể gặp các chuỗi như:

```text
10
10-ea
10+-ea
10-ea+5
17.0.10+7-LTS
21+35
```

Các chuỗi đều giống “số phiên bản”, nhưng chúng **không nói cùng một điều**:

- `10` chỉ mang **số phiên bản** (*version number*).
- `10-ea` có nhãn **pre-release** là `ea`.
- `10+-ea` có thông tin **optional** là `ea`, **không có** nhãn pre-release.
- `10-ea+5` mang cả nhãn pre-release `ea` và **build number** `5`.
- `17.0.10+7-LTS` mang số phiên bản `17.0.10`, **build** `7` và nhãn bổ sung `LTS`.
- `21+35` có FEATURE=21 và build=35, không có pre-release hay optional data.

Từ Java 9, `java.lang.Runtime.Version` đã biểu diễn một version string có cấu trúc. Với mô hình **time-based release versioning** được làm rõ trong Java 10 (JEP 322), lớp này tiếp tục là cách chuẩn để **phân tích và so sánh phiên bản Java** thay vì cắt chuỗi bằng các dấu `.`, `-`, `+` theo cảm tính.

Ba phương thức là trọng tâm:

```java
java.util.Optional<String> pre = version.pre();
java.util.Optional<Integer> build = version.build();
java.util.Optional<String> extra = version.optional();
```

`version` ở đây là một biến kiểu `Runtime.Version` đã được tạo hợp lệ. Đây là **đoạn minh họa trong thân phương thức**, không phải một chương trình độc lập.

### Mục tiêu bài học

Sau bài này bạn cần:

1. Phân biệt **version number**, **pre-release identifier**, **build number** và **optional metadata**.
2. Đọc đúng kiểu kết quả của `pre()`, `build()` và `optional()`.
3. Phân biệt chắc chắn `10-ea` với `10+-ea`.
4. Tránh nhầm `build()` với `feature()` hoặc `update()`.
5. Sử dụng `Optional` an toàn khi thiếu một thành phần.
6. Hiểu ảnh hưởng của pre/build/optional đến `compareTo()`, `compareToIgnoreOptional()`, `equals()` và `equalsIgnoreOptional()`.
7. Phân biệt phiên bản **được parse từ văn bản** với phiên bản **runtime thực sự đang chạy**.
8. Không suy diễn hợp đồng LTS, tính ổn định hay bảo mật chỉ từ một nhãn chuỗi.

Những kiến thức được trình bày đều **còn áp dụng trong Java hiện đại**. Ví dụ đầy đủ có thể biên dịch với `javac --release 10` và không sử dụng các accessor Java đã deprecated.

## 2. Runtime.Version là gì?

`Runtime.Version` là một nested class của `java.lang.Runtime`, mô tả **một version string của Java SE implementation**. Bạn có thể lấy object này từ hai nguồn chủ yếu:

```java
// A. Phiên bản của JVM đang chạy chính đoạn code hiện tại:
Runtime.Version actualRuntime = Runtime.version();

// B. Một chuỗi cụ thể cần phân tích:
Runtime.Version example = Runtime.Version.parse("21.0.2+13-LTS");
```

Hai cách có ý nghĩa khác nhau:

- `Runtime.version()` đọc phiên bản của **runtime hiện tại**.
- `Runtime.Version.parse(text)` chỉ **phân tích text bạn cung cấp**. Nó không kiểm tra rằng JDK tương ứng đã được cài, không tải JDK, không xác nhận bản phát hành có thật, không xác nhận hợp đồng hỗ trợ của vendor.

Ví dụ phân tích `"25.0.1+8-LTS"` trên một JVM 17 hoặc 24 **không biến JVM đó thành Java 25**. Đây là một cách biểu diễn version string, không phải chức năng chuyển đổi runtime.

Một số accessor liên quan:

| API | Kiểu trả về | Nội dung |
| --- | --- | --- |
| `feature()` | `int` | Số feature release, ví dụ 21 |
| `interim()` | `int` | Phần INTERIM hoặc 0 khi không có |
| `update()` | `int` | Phần UPDATE hoặc 0 khi không có |
| `patch()` | `int` | Phần PATCH hoặc 0 khi không có |
| `version()` | `List<Integer>` | Dãy các thành phần **số**, không gồm pre/build/optional |
| **`pre()`** | **`Optional<String>`** | Nhãn pre-release, khi có |
| **`build()`** | **`Optional<Integer>`** | Build number, khi có |
| **`optional()`** | **`Optional<String>`** | Thông tin build bổ sung, khi có |
| `toString()` | `String` | Chuỗi biểu diễn phiên bản |

**Lưu ý quan trọng:** `version()` không phải là “mọi thứ trong version string”; nó chỉ chứa dãy số. Muốn biết có `ea`, build hay hậu tố bổ sung, phải đọc đúng các accessor riêng.

## 3. Ngữ pháp version string và vị trí của pre/build/optional

Theo Javadoc `Runtime.Version` và JEP 322, một version string được tạo từ `$VNUM` (dãy số phiên bản) và các phần bổ sung tùy chọn theo một trong ba dạng:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM+-$OPT
```

Trong đó:

- `$VNUM`: dãy các số cách nhau bằng dấu chấm; không có thành phần 0 **ở cuối**. Bốn phần đầu có vai trò FEATURE.INTERIM.UPDATE.PATCH.
- `$PRE`: pre-release identifier gồm chữ và số ASCII, ví dụ `ea` hay `internal`.
- `$BUILD`: một số nguyên không âm, ví dụ `0`, `5` hoặc `35`; không phải số bản cập nhật `UPDATE`.
- `$OPT`: thông tin định danh build bổ sung do implementor lựa chọn, ví dụ `LTS` hoặc `lab`.

**Chú ý dấu phân cách**:

- Dấu `-` **ngay sau VNUM** trong `10-ea` mở đầu **PRE**.
- Dấu `+` ngay sau VNUM trong `21+35` mở đầu **BUILD** bằng số.
- Dấu `-` **sau số BUILD** trong `17+35-LTS` mở đầu **OPT**.
- Cặp `+-` trong `10+-ea` mở đầu **OPT** mà **không có BUILD**.
- Nếu đã có PRE nhưng không có BUILD, dạng `11-internal-lab` có PRE=`internal` và OPT=`lab`.

Suy ra: dấu `-` **không phải lúc nào cũng giới thiệu pre-release**. Cần xem **nó nằm ở đâu trong cấu trúc chuỗi**.

### Ví dụ định vị thành phần

| Chuỗi | `pre()` | `build()` | `optional()` |
| --- | --- | --- | --- |
| `10` | trống | trống | trống |
| `10-ea` | `ea` | trống | trống |
| `10+-ea` | trống | trống | `ea` |
| `10-ea+5` | `ea` | `5` | trống |
| `11-internal-lab` | `internal` | trống | `lab` |
| `17.0.10+7-LTS` | trống | `7` | `LTS` |
| `21+35` | trống | `35` | trống |
| `21.0.2+13-vendor` | trống | `13` | `vendor` |

Những chuỗi này là **fixture phục vụ học API parse**; sự hiện diện của một chuỗi hợp lệ không chứng minh đã có bản phát hành chính thức mang định danh đó.

## 4. pre(): nhận diện nhãn pre-release

Chữ ký:

```java
public java.util.Optional<String> pre()
```

`pre()` trả `Optional<String>` chứa nhãn pre-release nếu chuỗi có thành phần `$PRE`. Nếu không có, trả `Optional.empty()`.

```java
Runtime.Version candidate = Runtime.Version.parse("21-ea+12");
System.out.println(candidate.pre().orElse("none")); // ea

Runtime.Version version = Runtime.Version.parse("21+12");
System.out.println(version.pre().orElse("none")); // none
```

`ea` thường dùng cho *early access*; `internal` thường dùng cho build phát triển nội bộ. Nhưng đặc tả cho phép nhãn chữ/số thích hợp và **không buộc tất cả provider dùng đúng cùng một từ** để chỉ trạng thái hỗ trợ hay tiến trình phát hành.

### Khi có pre-release, đây là điều API cam kết

- Về **phân tích cú pháp**, label tồn tại trong `pre()`.
- Về **so sánh version**, nếu các thành phần số giống nhau, một version **có PRE** được xem là **nhỏ hơn** một version không có PRE.
- Một nhãn PRE toàn chữ số được so sánh theo giá trị số; một nhãn không thuần số dùng thứ tự từ vựng theo hợp đồng `compareTo`.

Ví dụ:

```java
var early = Runtime.Version.parse("21-ea+20");
var general = Runtime.Version.parse("21+1");

System.out.println(early.compareTo(general) < 0); // true
```

Build 20 của bản có PRE **không khiến nó lớn hơn** bản không PRE nhưng build 1, vì quy tắc so sánh xét PRE **trước** BUILD.

### Những điều không nên suy ra từ pre()

- `pre().isEmpty()` **không tự chứng minh** một artifact đã được GA chính thức hoặc đã được vendor bảo đảm hỗ trợ.
- `pre()` chỉ là thông tin version string, **không truy vấn website phát hành hay chữ ký số**.
- `ea` không phải một thang đo chất lượng được chuẩn hóa giữa mọi nhà cung cấp.
- Chỉ nhìn PRE không đủ để xác định build này có phù hợp deployment production, license hay bảo mật hay không.

Nếu hệ thống có chính sách chặn pre-release, đó là **quy tắc nghiệp vụ của hệ thống**, cần kết hợp metadata vendor, nguồn artifact và các kênh phát hành được tổ chức phê duyệt.

## 5. build(): số build của version string

Chữ ký:

```java
public java.util.Optional<Integer> build()
```

Khi version string có phần `+$BUILD` với số hợp lệ, `build()` trả `Optional<Integer>`. Nếu không có build, phương thức trả Optional rỗng.

```java
var a = Runtime.Version.parse("21+35");
System.out.println(a.build().orElse(-1)); // 35

var b = Runtime.Version.parse("21");
System.out.println(b.build().isPresent()); // false
```

**Không nhầm** `build()` với:

- `feature()`: feature release counter.
- `update()`: bản cập nhật trên một nhánh.
- `patch()`: bộ đếm emergency patch.
- Class-file version/Java language target của `javac`.
- Build number của chính ứng dụng đang chạy (có thể hoàn toàn khác).

Ví dụ:

```java
Runtime.Version v = Runtime.Version.parse("17.0.10+7-LTS");

System.out.println(v.feature());  // 17
System.out.println(v.update());   // 10
System.out.println(v.build().orElse(-1)); // 7
```

Ở đây `UPDATE=10` nhưng `BUILD=7`. Không có phép đồng nhất “update lần thứ 10 tức build số 10”.

### Build absent không phải build zero

`Optional.empty()` biểu diễn **không có thành phần BUILD** trong chuỗi. Nó khác với một thành phần BUILD có giá trị số `0`, vì ngữ pháp cho phép `$BUILD=0`.

Ví dụ minh họa có thể parse:

```java
var noBuild = Runtime.Version.parse("21");
var buildZero = Runtime.Version.parse("21+0");

System.out.println(noBuild.build().isPresent()); // false
System.out.println(buildZero.build().orElse(-1)); // 0
```

Do đó không dùng `build().orElse(0)` rồi coi 0 có nghĩa “không có build” khi ứng dụng cần giữ sự phân biệt. Dùng `isPresent()`, `map(...)` hoặc một mô hình kết quả lưu cả trạng thái có/không.

### Build number không phải tài khoản cập nhật

Javadoc mô tả build number tăng theo các lần build được promote và được reset theo quy tắc khi phần VNUM thay đổi. Không lấy BUILD để kết luận số bản vá bảo mật, số CVE đã xử lý, mức ổn định hoặc tổng số commit. Muốn biết nội dung bản phát hành, đọc release notes và security advisories của **đúng distribution**.

## 6. optional(): thông tin build bổ sung

Chữ ký:

```java
public java.util.Optional<String> optional()
```

`optional()` trả về phần `$OPT` nếu có. Nó là **thông tin định danh bổ sung** của build, ví dụ:

```java
var release = Runtime.Version.parse("17.0.10+7-LTS");
System.out.println(release.optional().orElse("none")); // LTS

var internal = Runtime.Version.parse("11-internal-lab");
System.out.println(internal.optional().orElse("none")); // lab
```

Các ý chính:

- `$OPT` không thuộc bốn phần tử FEATURE/INTERIM/UPDATE/PATCH.
- `$OPT` **không nhất thiết là một nhãn pre-release**.
- `$OPT` có thể chứa thông tin do vendor/implementor cung cấp; không có một tập giá trị cố định dùng chung cho mọi distribution.
- Chỉ khi **chuỗi thật sự có phần optional**, `optional().isPresent()` mới true.

### optional() có thể tồn tại mà build() rỗng

Trường hợp đặc biệt:

```java
var v = Runtime.Version.parse("10+-ea");

System.out.println(v.pre().orElse("none"));      // none
System.out.println(v.build().isPresent());        // false
System.out.println(v.optional().orElse("none"));  // ea
```

`10+-ea` có OPT=`ea` và không có PRE. Đừng viết mã “nếu chuỗi chứa chữ ea thì chắc chắn là pre-release”. Vị trí cấu trúc quan trọng hơn sự xuất hiện của một substring.

### Ý nghĩa của nhãn LTS trong optional

JEP 322 có mô tả quy ước để implementor có thể đưa `LTS` vào thông tin optional đối với các dòng được hỗ trợ dài hạn. Ví dụ:

```text
21.0.2+13-LTS
```

Ở mức parse, thông tin chỉ là:

```text
pre = absent
build = 13
optional = LTS
```

Nó **không phải một chứng chỉ hỗ trợ dài hạn**. Thời gian hỗ trợ thực tế, điều khoản thương mại, bản cập nhật security và việc phân phối artifact phụ thuộc vendor, dòng JDK, chương trình hỗ trợ và thời điểm kiểm tra.

**Không dùng** `version.optional().orElse("").contains("LTS")` như điều kiện duy nhất để lựa chọn runtime production. Một distribution có thể có chu kỳ hỗ trợ khác hoặc cách trình bày metadata khác. Hãy dựa vào support roadmap của đúng nhà cung cấp.

## 7. Tình huống cực dễ sai: 10-ea và 10+-ea

So sánh hai chuỗi:

```java
var x = Runtime.Version.parse("10-ea");
var y = Runtime.Version.parse("10+-ea");
```

Kết quả:

| Câu hỏi | `10-ea` | `10+-ea` |
| --- | --- | --- |
| Có nhãn PRE không? | Có: `ea` | Không |
| Có BUILD không? | Không | Không |
| Có OPT không? | Không | Có: `ea` |
| `pre().isPresent()` | `true` | `false` |
| `optional().isPresent()` | `false` | `true` |

Đây là một ví dụ được Javadoc `Runtime.Version` nêu rõ. Dù hai chuỗi chứa cùng chữ `ea`, **ý nghĩa cấu trúc khác nhau**.

Anti-pattern:

```java
boolean isEarly = version.toString().contains("ea");
```

Cách này không phân biệt PRE với OPT; còn có thể bắt nhầm một chuỗi bổ sung mà người tạo build dùng cho mục đích khác.

Nếu muốn kiểm tra chính nhãn PRE:

```java
boolean hasEaPreLabel = version.pre()
        .map("ea"::equals)
        .orElse(false);
```

Đây chỉ là một **feature check trên metadata đã parse**, không thay thế kiểm chứng kênh phát hành hoặc chính sách triển khai.

## 8. Xử lý ba Optional an toàn và đúng kiểu

Ba method **không trả `null`**, mà trả object `Optional` có/không chứa giá trị.

Điểm khác biệt về generic type:

```java
java.util.Optional<String> pre = version.pre();
java.util.Optional<Integer> build = version.build();
java.util.Optional<String> extra = version.optional();
```

Vì `build()` là `Optional<Integer>`, đoạn sau **không biên dịch**:

```java
// SAI:
// String label = version.build().orElse("unknown");
// Expected Integer, not String.
```

Cách chuyển sang chuỗi đúng:

```java
String label = version.build()
        .map(String::valueOf)
        .orElse("unknown");
```

Nếu muốn log version đã được phân tích:

```java
static String metadata(Runtime.Version version) {
    String pre = version.pre().orElse("-");
    String build = version.build()
            .map(String::valueOf)
            .orElse("-");
    String optional = version.optional().orElse("-");

    return "pre=" + pre + ", build=" + build
            + ", optional=" + optional;
}
```

Đây là một phương thức minh họa để đặt trong class, có thể gọi với object Version hợp lệ.

### Không gọi Optional.get() vô điều kiện

```java
// Có thể ném NoSuchElementException nếu không có build:
// int n = version.build().get();
```

Cách thích hợp hơn:

```java
version.build().ifPresent(n -> System.out.println("build=" + n));
```

Hoặc:

```java
int n = version.build()
        .orElseThrow(() -> new IllegalArgumentException(
                "Build number is required by this operation"));
```

Chỉ sử dụng `orElseThrow` khi **nghiệp vụ thật sự yêu cầu** build number. Một version string không có BUILD vẫn có thể hợp lệ, như `"10"`; thiếu build **không phải mặc định là lỗi parse**.

### Không đánh đồng thiếu giá trị với chuỗi rỗng

Theo ngữ pháp, một field metadata có mặt cần chứa giá trị hợp lệ. `Optional.empty()` từ `pre()/build()/optional()` nghĩa là **không có thành phần đó**, không phải một String rỗng do parser “điền mặc định”.

Chính sách dữ liệu có thể xuất chuỗi `"<absent>"` hoặc `"none"` cho người xem, nhưng phải hiểu đây là **nhãn do ứng dụng tự chọn**, không phải một phần của version gốc.

## 9. So sánh phiên bản: vì sao optional() có thể thay đổi kết quả?

`Runtime.Version` có hai cách so sánh chính:

```java
int full = a.compareTo(b);
int withoutExtra = a.compareToIgnoreOptional(b);
```

Theo Javadoc, `compareTo()` xét lần lượt:

1. Dãy **version numbers**.
2. **Pre-release identifier**.
3. **Build number**.
4. **Optional information**.

Cụ thể:

- Version có PRE đứng **trước** version không PRE nếu dãy số giống nhau.
- Nhãn PRE toàn số được so theo số; nhãn không thuần số được so từ vựng.
- Version **không có BUILD** nhỏ hơn version có BUILD nếu các phần trước bằng nhau.
- OPT được so từ vựng; version có OPT lớn hơn version không có OPT nếu các phần trước bằng nhau.

Dạng `compareToIgnoreOptional` giữ logic so sánh như trên **nhưng bỏ qua chỉ thành phần OPT**. Nó vẫn xét **version numbers, PRE và BUILD**.

### Ví dụ hai build chỉ khác OPT

```java
Runtime.Version a = Runtime.Version.parse("21.0.2+13-LTS");
Runtime.Version b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equals(b));                     // false
System.out.println(a.equalsIgnoreOptional(b));       // true
System.out.println(a.compareTo(b) != 0);             // true
System.out.println(a.compareToIgnoreOptional(b) == 0); // true
```

Hai version có cùng VNUM và BUILD, không PRE; chỉ khác OPT. Vì vậy:

- So sánh **full version** cho biết hai chuỗi không hoàn toàn giống.
- So sánh **ignore optional** cho biết các phần còn lại tương đương theo API.

Điều này hữu ích khi bạn muốn so sánh nhánh và build theo quy tắc định nghĩa mà bỏ qua nhãn mô tả bổ sung. Nhưng nó **không** có nghĩa hai artifact binary giống nhau hoặc có cùng nội dung bảo mật.

### Trường hợp khác BUILD thì vẫn khác sau ignore optional

```java
var x = Runtime.Version.parse("21+13-LTS");
var y = Runtime.Version.parse("21+14-vendor");

System.out.println(x.compareToIgnoreOptional(y) < 0); // true
```

Vì BUILD=13 khác BUILD=14, bỏ qua OPT cũng không làm hai version bằng nhau.

### Trường hợp khác PRE cũng vẫn khác

```java
var ea = Runtime.Version.parse("21-ea+20-LTS");
var ga = Runtime.Version.parse("21+1-vendor");

System.out.println(ea.compareToIgnoreOptional(ga) < 0); // true
```

Dù bỏ qua `LTS`/`vendor`, bản có PRE vẫn đứng trước bản không có PRE.

## 10. equals() và equalsIgnoreOptional(): đừng dùng lẫn với hashCode

Hai phương thức:

```java
boolean exactlyEqual = a.equals(b);
boolean equalExceptOpt = a.equalsIgnoreOptional(b);
```

có **hợp đồng khác nhau**:

- `equals(...)` so sánh các version theo **toàn bộ version string** mà đối tượng biểu diễn.
- `equalsIgnoreOptional(...)` bỏ qua **chỉ optional build information**.
- `compareTo(...)` tương thích với `equals(...)`.
- `compareToIgnoreOptional(...)` tương thích với `equalsIgnoreOptional(...)`.

**Không dùng `equalsIgnoreOptional` như thể nó là `equals` của object khi xây khóa `HashMap<Runtime.Version,...>` hoặc `HashSet<Runtime.Version>`.** Các cấu trúc hash dùng `equals()/hashCode()` toàn phần; hai Version có OPT khác nhau vẫn là hai khóa khác theo hợp đồng đối tượng.

Nếu một ứng dụng thực sự cần nhóm các version “bằng nhau khi bỏ qua OPT”, hãy định nghĩa một **khóa chuẩn hóa riêng** phù hợp với chính sách (ví dụ giữ version numbers, PRE, BUILD và bỏ OPT) hoặc một comparator có mục đích rõ ràng. Đảm bảo `equals` và `hashCode` của kiểu khóa chuẩn hóa nhất quán.

`Runtime.Version` là một **value-based class**. Không dựa vào `==`, identity hash code hay khóa đồng bộ trên một instance Version; dùng so sánh giá trị được API cung cấp.

## 11. Version number, build, pre và optional đều có giới hạn ý nghĩa

Một số giả định sai cần tránh khi thiết kế chính sách kiểm thử hoặc deployment:

| Thông tin | Biết được | **Không tự biết được** |
| --- | --- | --- |
| `feature()` | Nhánh Java feature, ví dụ 21 | Tất cả API chạy được trên vendor cụ thể |
| `update()` | Bộ đếm update trên nhánh | Số lượng CVE đã sửa hoặc mức an toàn tuyệt đối |
| `pre()` | Nhãn pre-release nếu có | Tình trạng GA/support được ký xác nhận bên ngoài |
| `build()` | Số build nếu chuỗi có | Thứ tự phát hành xuyên mọi vendor, chất lượng hoặc checksum artifact |
| `optional()` | Nhãn thông tin bổ sung | Hợp đồng LTS, nguồn cung ứng đáng tin hay support end date |
| `toString()` | Chuỗi version đầy đủ được đối tượng biểu diễn | Tự xác minh build đã được cài hoặc binary tải từ vendor nào |

Version string **không phải một chứng thư** về authenticity, support entitlement, license hoặc security. Những điều đó phải được xác định từ artifact ký số, nguồn download/registry, SBOM, changelog, advisory, roadmap và chính sách tổ chức tùy mục tiêu.

Có thể dùng version metadata trong log chẩn đoán, nhưng để kiểm tra provenance/reproducibility của runtime, thường còn cần **vendor, distribution, image digest, build ID hoặc package metadata**. Chỉ lưu chuỗi `"21.0.2+13"` không đủ chứng minh hai JVM từ hai vendor là một binary giống hệt.

## 12. Chương trình Java 10+ hoàn chỉnh và stdout đã kiểm chứng

Tạo tệp **`RuntimeVersionMetadataDemo.java`**:

```java
public final class RuntimeVersionMetadataDemo {
    static void inspect(String text) {
        Runtime.Version v = Runtime.Version.parse(text);
        String pre = v.pre().orElse("<absent>");
        String build = v.build().map(String::valueOf).orElse("<absent>");
        String optional = v.optional().orElse("<absent>");
        System.out.println(text + " -> pre=" + pre
                + ", build=" + build
                + ", optional=" + optional);
    }

    public static void main(String[] args) {
        inspect("10");
        inspect("10-ea");
        inspect("10+-ea");
        inspect("10-ea+5");
        inspect("11-internal-lab");
        inspect("17.0.10+7-LTS");
        inspect("21+35");

        Runtime.Version a = Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version b = Runtime.Version.parse("21.0.2+13-vendor");
        System.out.println("equalsFull=" + a.equals(b));
        System.out.println("equalsIgnoreOptional=" + a.equalsIgnoreOptional(b));
        System.out.println("compareFullNonzero=" + (a.compareTo(b) != 0));
        System.out.println("compareIgnoreOptionalZero="
                + (a.compareToIgnoreOptional(b) == 0));

        Runtime.Version early = Runtime.Version.parse("21-ea+20");
        Runtime.Version ga = Runtime.Version.parse("21+1");
        System.out.println("earlyLessThanGA=" + (early.compareTo(ga) < 0));

        Runtime.Version build13 = Runtime.Version.parse("21+13");
        Runtime.Version build14 = Runtime.Version.parse("21+14");
        System.out.println("build13LessThan14=" + (build13.compareTo(build14) < 0));
        System.out.println("noBuildLessThanBuild=" +
                (Runtime.Version.parse("21").compareTo(build13) < 0));
        System.out.println("versionNumbersOnly=" + a.version());
        System.out.println("feature=" + a.feature() + ", update=" + a.update());

        System.out.println("runtimeFeaturePositive=" + (Runtime.version().feature() >= 10));

        try {
            Runtime.Version.parse("21.0.0");
            System.out.println("badSyntax=unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("badSyntax=IllegalArgumentException");
        }
    }
}
```

Biên dịch bằng JDK hỗ trợ `--release 10`:

```bash
javac --release 10 RuntimeVersionMetadataDemo.java
java RuntimeVersionMetadataDemo
```

**Stdout chính xác đã kiểm chứng qua biên dịch và chạy:**

```text
10 -> pre=<absent>, build=<absent>, optional=<absent>
10-ea -> pre=ea, build=<absent>, optional=<absent>
10+-ea -> pre=<absent>, build=<absent>, optional=ea
10-ea+5 -> pre=ea, build=5, optional=<absent>
11-internal-lab -> pre=internal, build=<absent>, optional=lab
17.0.10+7-LTS -> pre=<absent>, build=7, optional=LTS
21+35 -> pre=<absent>, build=35, optional=<absent>
equalsFull=false
equalsIgnoreOptional=true
compareFullNonzero=true
compareIgnoreOptionalZero=true
earlyLessThanGA=true
build13LessThan14=true
noBuildLessThanBuild=true
versionNumbersOnly=[21, 0, 2]
feature=21, update=2
runtimeFeaturePositive=true
badSyntax=IllegalArgumentException
```

### Phân tích kết quả

1. **Ba giá trị trống ở `10`**: hợp lệ; không phải parser thất bại.
2. **`10-ea`**: PRE=`ea`, BUILD và OPT không có.
3. **`10+-ea`**: không có PRE, không có BUILD, OPT=`ea`. Đây là cặp đối chiếu quan trọng nhất của bài.
4. **`10-ea+5`**: PRE=`ea` và BUILD=5, nhưng không có OPT.
5. **`11-internal-lab`**: PRE=`internal`, OPT=`lab` dù không có BUILD.
6. **`17.0.10+7-LTS`**: BUILD=7 và OPT=`LTS`. Số UPDATE=10 thuộc VNUM, không thuộc BUILD.
7. **`equalsFull=false` nhưng `equalsIgnoreOptional=true`**: hai phiên bản chỉ khác OPT; so sánh đầy đủ và so sánh bỏ OPT cần được lựa chọn có chủ đích.
8. **`earlyLessThanGA=true`**: nhãn PRE được xét trước BUILD trong cách so sánh.
9. **`build13LessThan14=true` và `noBuildLessThanBuild=true`**: BUILD được so theo số và tình trạng không có BUILD cũng có quy tắc thứ tự.
10. **`versionNumbersOnly=[21, 0, 2]`**: accessor `version()` không trả về `13` hay `LTS`; hai thông tin đó được đọc qua accessor riêng.
11. **`runtimeFeaturePositive=true`**: chương trình đang chạy trên JDK mới đủ để thực thi mã được biên dịch cho Java 10. Đây không phải con số phiên bản thực tế; muốn biết chính xác hãy in `Runtime.version()`.
12. **`badSyntax=IllegalArgumentException`**: `21.0.0` không hợp lệ vì version number không được có các thành phần zero ở cuối.

Trong chương trình, chuỗi `<absent>` là **nhãn do ví dụ tự đặt cho Optional.empty**, không phải một phần của version string thật. Các version như `21.0.2+13-vendor` là mẫu parse hợp lệ, không có hàm ý rằng một vendor cụ thể đã phát hành artifact đó.

## 13. parse() thất bại: cú pháp sai khác với thiếu metadata

`Runtime.Version.parse(String)` được thiết kế để phân tích một chuỗi version **hợp lệ theo ngữ pháp Java**. Nếu chuỗi không hợp lệ, nó không trả object rỗng rồi cho bạn kiểm tra PRE/BUILD/OPT; nó ném ngoại lệ.

Ví dụ:

```java
try {
    Runtime.Version.parse("21.0.0");
} catch (IllegalArgumentException invalid) {
    System.out.println("Invalid version syntax");
}
```

Một số nhóm lỗi cần nhận diện theo Javadoc:

- Chuỗi rỗng, thiếu phần số VERSION hoặc cấu trúc dấu `+/-` không đúng: `IllegalArgumentException`.
- Truyền `null`: `NullPointerException`.
- Phần số version hoặc build vượt khả năng biểu diễn bằng `Integer`: `NumberFormatException` (một subclass của `IllegalArgumentException`).

Ví dụ chuỗi `21.0.0` không hợp lệ vì `VNUM` không cho trailing zeros. Chuỗi `21.0.2` có số 0 **ở giữa** và phần cuối là 2, nên hợp lệ.

**Phân biệt hai trạng thái:**

1. `parse("21")` thành công, sau đó `pre()/build()/optional()` đều rỗng — **version hợp lệ, metadata không có**.
2. `parse("21.0.0")` ném exception — **chuỗi version không hợp lệ**.

Không xử lý cả hai bằng “version không có build” vì một trong hai là vấn đề dữ liệu đầu vào.

### Không tự viết parser bằng split khi đã có API chuẩn

Anti-pattern:

```java
// Không đủ cho ngữ pháp đầy đủ:
String[] pieces = text.split("-");
String[] nums = pieces[0].split("\\.");
```

Cách này khó phân biệt `10-ea`, `10+-ea`, `10-ea+5` và `21+35-LTS`; lại phải tự xử lý integer, thứ tự, optional metadata và lỗi cú pháp. Với **Java runtime version string**, ưu tiên `Runtime.Version.parse(text)` và các accessor tương ứng.

Không áp dụng parser này cho mọi “version” của phần mềm khác: Maven artifact version, SemVer của một thư viện hoặc tag riêng của Docker có thể dùng quy tắc khác. `Runtime.Version` mô tả **version string của Java platform implementation**, không phải trình phân tích tổng quát mọi format version ngoài hệ sinh thái này.

## 14. Ví dụ thực hành: tạo nhãn chẩn đoán cho runtime hiện tại

Trong application startup hoặc health diagnostics, có thể đọc:

```java
static String runtimeLabel() {
    Runtime.Version v = Runtime.version();
    String buildText = v.build()
            .map(String::valueOf)
            .orElse("not reported");
    String preText = v.pre().orElse("none");
    String optionalText = v.optional().orElse("none");

    return "feature=" + v.feature()
            + ", update=" + v.update()
            + ", pre=" + preText
            + ", build=" + buildText
            + ", optional=" + optionalText;
}
```

Hàm này **không thay thế** thông tin khác như vendor, môi trường triển khai hoặc package ID, nhưng giúp phân loại báo lỗi “đang chạy một feature/update/build nào” dễ hơn.

Nếu cần lưu chuỗi version nguyên bản, có thể dùng:

```java
String fullVersion = Runtime.version().toString();
```

Và khi kiểm tra bằng lệnh:

```bash
java --version
javac --version
```

hãy nhớ `java` (runtime) và `javac` (compiler) trên `PATH` có thể trỏ đến các bản cài khác nhau. Khi chạy trong container, thông tin phải lấy **ở trong container hoặc service đang chạy**, không chỉ từ máy phát triển.

### Tách môi trường build và runtime

`javac --release 10` giới hạn mức ngôn ngữ, class file và Java SE API mà compiler cho phép sử dụng, **không** chứng minh một JVM 10 đang chạy chương trình. `Runtime.version()` mới nói về runtime hiện tại. Khi cần xác nhận tương thích thật, chạy test trên các JDK mục tiêu theo policy của dự án.

Đối với ứng dụng phụ thuộc vào feature mới, `feature()` có thể hỗ trợ kiểm tra version, nhưng trước khi giới hạn hoặc mở tính năng vẫn cần xét **API thực sự tồn tại**, preview/flags, hệ điều hành và vendor. Chuỗi OPTIONAL không phải feature flag chuẩn của Java SE.

## 15. So sánh và phân nhóm version: lựa chọn chính sách đúng

Giả sử hệ thống nhận từ nhiều nguồn ba chuỗi:

```text
21.0.2+13-LTS
21.0.2+13-vendor
21.0.2+14-vendor
```

Có ba câu hỏi khác nhau:

**A. “Chuỗi version có giống toàn bộ không?”**

Dùng `equals()`. `+13-LTS` và `+13-vendor` được xem là **khác nhau**.

**B. “Cùng VERSION + PRE + BUILD, bỏ qua nhãn bổ sung?”**

Dùng `equalsIgnoreOptional()` hoặc `compareToIgnoreOptional()==0`. Hai chuỗi `+13-LTS` và `+13-vendor` được xem là tương đương **theo phép so sánh này**, còn `+14-vendor` vẫn khác.

**C. “Hai binary có cùng nội dung và cùng chính sách support không?”**

**Không thể quyết định chỉ từ những method trên.** Cần metadata artifact, vendor, checksum/signature và thông tin bảo trì từ nguồn có thẩm quyền.

Lựa chọn sai giữa A/B/C dễ tạo lỗi:

- Dùng so sánh full metadata để quyết định một update bảo mật mới hơn có thể bị ảnh hưởng bởi chuỗi OPT không liên quan.
- Dùng compareIgnoreOptional cho định danh binary chính xác có thể bỏ qua một khác biệt vendor mà dự án thực sự quan tâm.
- Chỉ so `feature()` và bỏ qua `update()`, dẫn tới coi hai mức vá bảo mật trong cùng nhánh là như nhau.
- Coi `optional().isPresent()` là “mới hơn” theo nghĩa hỗ trợ; comparator chỉ định nghĩa **thứ tự phiên bản**, không phải mức độ bảo trì hay độ an toàn.

Chọn comparator theo **mục tiêu dữ liệu**, không theo kết quả dễ đọc nhất.

## 16. Những sai lầm phổ biến

**Sai lầm 1 — Nghĩ bất kỳ `ea` nào trong string cũng là pre-release.** `10+-ea` có OPT=`ea`, PRE rỗng. Dùng `pre()`.

**Sai lầm 2 — Nghĩ cả ba accessor trả String.** `build()` trả `Optional<Integer>`, không phải `Optional<String>`.

**Sai lầm 3 — Gọi `get()` khi Optional có thể rỗng.** Version `10` là hợp lệ nhưng không có PRE/BUILD/OPT; `get()` vô điều kiện có thể ném `NoSuchElementException`.

**Sai lầm 4 — Đặt `build().orElse(0)` rồi coi 0 là “không có build”.** BUILD=0 có thể hợp lệ. Nếu cần phân biệt, giữ Optional.

**Sai lầm 5 — Coi `build()` là UPDATE.** `17.0.10+7-LTS` có UPDATE=10 nhưng BUILD=7.

**Sai lầm 6 — Nghĩ `optional()` chỉ có thể là `LTS`.** Đây là dữ liệu build bổ sung và có thể mang chuỗi khác.

**Sai lầm 7 — Coi nhãn `LTS` là hợp đồng support hợp lệ ở mọi nơi.** Chính sách support cần xác minh với nhà cung cấp/distribution cụ thể.

**Sai lầm 8 — Coi `equalsIgnoreOptional()` đồng nhất với `equals()`.** So sánh ignore OPT không thể thay thế object equality trong HashMap/HashSet.

**Sai lầm 9 — Nghĩ compareIgnoreOptional bỏ luôn build.** Không. Nó **chỉ** bỏ qua OPT; PRE và BUILD vẫn được so.

**Sai lầm 10 — So build/pre bằng thứ tự xuất hiện trong chuỗi hoặc `String.compareTo`.** Hãy dùng `Runtime.Version.compareTo` hoặc accessor phù hợp. Với PRE, quy tắc so sánh còn phân biệt chuỗi toàn chữ số và chuỗi khác.

**Sai lầm 11 — Nghĩ `Runtime.Version.parse(...)` cho biết runtime thực tế.** Không, nó parse chuỗi truyền vào. Dùng `Runtime.version()`.

**Sai lầm 12 — Nghĩ string có build là JDK đã GA.** Không. Chuỗi `10-ea+5` có cả pre-release lẫn build.

**Sai lầm 13 — Tự cắt chuỗi bằng dấu `-` mà bỏ qua ký hiệu `+-`.** Dễ gán OPT nhầm thành PRE.

**Sai lầm 14 — Đánh đồng parser thất bại với thiếu metadata.** `21` parse thành công và BUILD trống; `21.0.0` không hợp lệ.

**Sai lầm 15 — Dùng Version object làm khóa đồng bộ hoặc so `==`.** `Runtime.Version` là value-based; nên dùng các phép so sánh giá trị.

**Sai lầm 16 — Lưu mỗi chuỗi Java version rồi coi đó là bằng chứng provenance.** Khi cần bảo đảm artifact, phải xác minh đúng vendor/build binary/image.

## 17. Checklist code review và kiểm thử

- [ ] Biết rõ dữ liệu đang đọc là **Java runtime version string**, không phải SemVer ngẫu nhiên của một thư viện.
- [ ] `Runtime.Version.parse` được dùng để phân tích text, `Runtime.version()` để lấy JVM thực tế.
- [ ] Đã phân biệt VNUM với PRE, BUILD và OPT.
- [ ] Không nhầm `10-ea` với `10+-ea`.
- [ ] Đã xử lý `Optional.empty()` hợp lệ cho từng method.
- [ ] `build()` được sử dụng như `Optional<Integer>`, không phải String.
- [ ] Không dùng 0 làm sentinel vô điều kiện khi cần phân biệt BUILD=0.
- [ ] Không nhầm BUILD với FEATURE/UPDATE/PATCH.
- [ ] Với `equalsIgnoreOptional`, đã xác định rõ vì sao OPT không quan trọng cho câu hỏi nghiệp vụ.
- [ ] Với khóa hash hoặc định danh binary, vẫn dùng semantics phù hợp của `equals()/hashCode()` hoặc khóa riêng.
- [ ] So sánh version bằng API chuẩn, không bằng thứ tự ký tự thô.
- [ ] LTS hoặc mức hỗ trợ không được quyết định chỉ theo `optional()`.
- [ ] Đã test đầu vào thiếu metadata nhưng hợp lệ và đầu vào sai cú pháp.
- [ ] Có test trường hợp có PRE+BUILD, BUILD+OPT và PRE+OPT không BUILD.
- [ ] Log/diagnostics dùng runtime của **tiến trình thực sự**, không máy khác.
- [ ] Kế hoạch deployment vẫn kiểm tra JDK vendor, artifact ID và release notes.

## 18. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `Runtime.Version.parse("10").build()` trả gì?

**Đáp án:** `Optional.empty()`. Không có BUILD không làm `10` thành chuỗi version không hợp lệ.

**Câu 2.** `pre()` và `optional()` có cùng kiểu trả về không?

**Đáp án:** Có, cả hai là `Optional<String>`; nhưng chúng mang **hai vị trí/ngữ nghĩa khác nhau** trong version string.

**Câu 3.** `build()` trả `Optional<String>` hay `Optional<Integer>`?

**Đáp án:** `Optional<Integer>`, vì build number là một số nguyên theo ngữ pháp version string.

**Câu 4.** `10-ea` và `10+-ea` cùng có `ea`. Có cùng PRE không?

**Đáp án:** Không. `10-ea` có PRE=`ea`; `10+-ea` có PRE rỗng và OPT=`ea`.

**Câu 5.** Trong `17.0.10+7-LTS`, số 10 và số 7 có nghĩa gì?

**Đáp án:** `10` là UPDATE, nằm trong version number; `7` là BUILD, nằm sau dấu cộng.

**Câu 6.** Nếu `optional()` có `LTS`, có thể kết luận vendor phải cung cấp bản vá thêm đúng 8 năm không?

**Đáp án:** Không. Optional metadata không quy định thời hạn/điều khoản hỗ trợ. Cần kiểm tra roadmap và chính sách vendor.

**Câu 7.** Tại sao `21-ea+20` có thể đứng trước `21+1`?

**Đáp án:** Khi VNUM bằng nhau, PRE được xét trước BUILD. Version có PRE đứng trước version không PRE, bất kể build 20 lớn hơn 1.

**Câu 8.** `equalsIgnoreOptional()` có bỏ qua số BUILD không?

**Đáp án:** Không. Nó chỉ bỏ qua OPT. Hai version có BUILD khác nhau vẫn khác nhau.

**Câu 9.** `equalsIgnoreOptional()` cho true nhưng `HashSet<Runtime.Version>` vẫn chứa hai phần tử. Có phải Java lỗi không?

**Đáp án:** Không. HashSet dùng `equals()/hashCode()` toàn phần; nó không sử dụng phép `equalsIgnoreOptional()`.

**Câu 10.** `Runtime.Version.parse("21.0.0")` có thành công rồi trả UPDATE=0 không?

**Đáp án:** Không. Version number không được có các zero ở cuối; chuỗi này không hợp lệ và parser ném exception.

**Câu 11.** Muốn in BUILD hoặc `"not supplied"` từ `Optional<Integer>`, cú pháp nào đúng?

**Đáp án:** `version.build().map(String::valueOf).orElse("not supplied")`.

**Câu 12.** Có nên dùng `version.toString().contains("ea")` để phát hiện PRE không?

**Đáp án:** Không. OPT có thể chứa `ea`; nên dùng `version.pre()` với chính sách nhãn phù hợp.

**Câu 13.** `Runtime.Version.parse("25.0.1+8-LTS")` có làm tiến trình chạy Java 25 không?

**Đáp án:** Không. Nó chỉ phân tích String. `Runtime.version()` trả version của JVM hiện đang chạy.

**Câu 14.** Khi có hai JDK cùng feature/update/build nhưng khác vendor metadata, có bảo đảm hai binary giống nhau không?

**Đáp án:** Không. Java Version object không kiểm chứng binary artifact, vendor, chữ ký số hay nội dung security patch.

## 19. Tài liệu chính thức còn áp dụng

- [Java SE 25 — Runtime.Version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): ngữ pháp PRE/BUILD/OPT, các phương thức `pre()/build()/optional()`, `compareToIgnoreOptional()` và `equalsIgnoreOptional()`.
- [Java SE 25 — Runtime.version()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#version()): lấy phiên bản runtime thực sự.
- [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình FEATURE.INTERIM.UPDATE.PATCH và cách đặt version string từ Java 10.
- [Java SE 25 — Optional<T>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): xử lý có/không có thành phần metadata một cách an toàn.
- [Java SE 25 — Comparable<T>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html): khái niệm thứ tự có hợp đồng rõ, tránh tự so sánh chuỗi phiên bản.
- [Java SE 25 — Object.equals/hashCode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html): vì sao `equalsIgnoreOptional` không phải object equality dùng bởi hash-based collections.

**Kết luận:** `Runtime.Version.pre()` trả nhãn **pre-release** nếu có, `build()` trả **số build** nếu có, còn `optional()` trả **thông tin build bổ sung** nếu có. Cả ba đều dùng `Optional` và có thể rỗng ở một chuỗi Java version hoàn toàn hợp lệ. Việc hiểu chính xác dấu `-`, `+` và `+-`, cùng sự khác biệt giữa so sánh đầy đủ và bỏ OPT, giúp kiểm tra Java runtime một cách đúng hợp đồng — không nhầm pre-release, build metadata và chính sách hỗ trợ.
