# Phân tích chuỗi phiên bản bằng `Runtime.Version` (Java 10+)

## 1. Mục tiêu và kết quả cần đạt

Khi một chương trình Java cần kiểm tra phiên bản JDK, phân loại bản **early access** hoặc **general availability**, đọc **build number**, đối chiếu các bản cập nhật và quyết định có đáp ứng một yêu cầu về phiên bản hay không, không nên tự tách chuỗi bằng `split("\\.")` rồi so sánh từng đoạn theo kiểu chuỗi.

Java cung cấp **`java.lang.Runtime.Version`**, một kiểu dữ liệu chuyên để biểu diễn, phân tích và so sánh **chuỗi phiên bản của Java SE/JDK**. API này có từ **Java 9**, nhưng từ **Java 10** — theo **JEP 322: Time-Based Release Versioning** — có các accessor phù hợp hơn với mô hình phát hành theo thời gian: `feature()`, `interim()`, `update()` và `patch()`.

Ví dụ:

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.10+7-LTS");

int feature = v.feature();                 // 17
int interim = v.interim();                 // 0
int update = v.update();                   // 10
int patch = v.patch();                     // 0

int build = v.build().orElse(-1);          // 7
String extra = v.optional().orElse("");   // "LTS"
~~~

Đoạn trên **minh họa API trong một phương thức**, không phải chương trình Java độc lập. Các phương thức trả về `Optional` được xử lý an toàn mà không gọi `get()` khi có thể vắng mặt.

**Kết luận cốt lõi:**

- Dùng **`Runtime.Version.parse(String)`** để phân tích **chuỗi phiên bản đúng định dạng Java**.
- Dùng **`feature()`, `interim()`, `update()`, `patch()`** để lấy các phần số theo ngữ nghĩa Java 10 trở lên.
- Dùng **`pre()`, `build()`, `optional()`** để đọc metadata xuất hiện sau phần số.
- Dùng **`compareTo()`** hoặc **`compareToIgnoreOptional()`** thay vì so sánh text.
- Dùng **`Runtime.version()`** để lấy version của JVM **đang chạy**, không phải phân tích `java -version` bằng regex.
- Khi chỉ kiểm tra **mốc tính năng ngôn ngữ/API**, có thể dùng **`Runtime.version().feature()`**; không nên để build metadata làm sai logic eligibility.
- **Không dùng** các accessor `major()`, `minor()`, `security()` trong code mới: chúng được đánh dấu **deprecated từ Java 10** do tên gọi không còn mô tả đúng mô hình phát hành.

Bài học dùng API còn được tài liệu **Java SE 26** duy trì và có bài kiểm thử thật với **JDK 24.0.2**, source biên dịch qua `javac --release 10`.

## 2. Phân biệt phiên bản của JDK và kiểu `Runtime.Version`

Hai lời gọi khác nhau:

~~~java
// Phiên bản Java runtime mà tiến trình này đang sử dụng:
Runtime.Version running = Runtime.version();

// Một phiên bản bất kỳ từ chuỗi được cung cấp:
Runtime.Version expected = Runtime.Version.parse("17.0.10+7-LTS");
~~~

- **`Runtime.version()`** hỏi **JVM hiện tại**; mỗi môi trường JDK có thể cho kết quả khác.
- **`Runtime.Version.parse(...)`** tạo đối tượng từ **dữ liệu bạn đưa vào**; không cần cài một JDK có phiên bản trùng với chuỗi đó.
- Việc parse thành công **không chứng minh** một phiên JDK như vậy đã được phát hành thật, còn được hỗ trợ hay có đầy đủ bản vá.

Ví dụ `Runtime.Version.parse("10.0.2+13-LTS")` là **chuỗi hợp lệ về mặt cú pháp**, nhưng **“LTS” trong input không làm Java 10 trở thành một bản LTS thực tế**. Tập bài test có thể dùng chuỗi giả định để kiểm tra parser, nhưng không được biến dữ liệu thử nghiệm thành tuyên bố về hỗ trợ sản phẩm.

**Không trộn với phiên bản ứng dụng/thư viện:** `Runtime.Version` được thiết kế cho **Java platform release strings**, không phải parser tổng quát cho npm, Maven, Gradle hoặc Semantic Versioning của mọi sản phẩm.

## 3. Vì sao Java 10 thay đổi cách gọi các thành phần?

Mô hình phiên bản Java từ JDK 9 theo **JEP 223** và điều chỉnh ở JDK 10 theo **JEP 322** để thích hợp với các đợt phát hành theo lịch.

Mẫu ý nghĩa của bốn thành phần số đầu tiên:

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

| Thành phần | Phương thức hiện hành | Ý nghĩa |
| --- | --- | --- |
| `FEATURE` | `feature()` | Bộ đếm feature releases; được tăng qua các feature releases theo mô hình Java |
| `INTERIM` | `interim()` | Bộ đếm các interim releases mang sửa lỗi/cải tiến tương thích, không đổi chuẩn API |
| `UPDATE` | `update()` | Bộ đếm các update releases, thường chứa sửa lỗi bảo mật, regression, vấn đề mới |
| `PATCH` | `patch()` | Bộ đếm emergency patch releases khi cần sửa sự cố quan trọng |

**Đừng suy rằng cả bốn thành phần luôn được in.** Một bản như `17` chỉ có phần `FEATURE` trong chuỗi, nhưng các accessor còn lại vẫn trả `0`.

Ví dụ:

~~~text
10                    FEATURE=10, INTERIM=0, UPDATE=0, PATCH=0
10.0.2                FEATURE=10, INTERIM=0, UPDATE=2, PATCH=0
10.0.0.1              FEATURE=10, INTERIM=0, UPDATE=0, PATCH=1
17.0.10               FEATURE=17, INTERIM=0, UPDATE=10, PATCH=0
~~~

**Quan trọng về lịch sử API:**

- Lớp `Runtime.Version` và `parse`/`version`/`pre`/`build`/`optional` đã có từ Java 9.
- Các accessor **`feature()`, `interim()`, `update()`, `patch()`** được thêm ở Java 10.
- `major()`, `minor()` và `security()` bị đánh dấu deprecated từ Java 10, vì các tên này dễ gây hiểu nhầm theo cơ chế update mới.
- Trong code Java hiện đại, ưu tiên **`feature()/interim()/update()/patch()`**; không viết bài dựa trên tên `security()` hay suy rằng thành phần thứ ba chỉ tăng trong bản cập nhật bảo mật.

**Chú ý:** “feature version” **không đồng nghĩa** với việc tất cả những feature đang có trong bản mới đều có thể sử dụng ngay trong code của bạn; có thể còn phụ thuộc module, platform, preview policy và runtime/environment.

## 4. Ngữ pháp phần số (`VNUM`)

Theo Java SE 26 `Runtime.Version` Javadoc:

~~~text
VNUM = [1-9][0-9]*((\.0)*\.[1-9][0-9]*)*
~~~

Ý nghĩa:

1. Phần đầu tiên là một số nguyên dương, không có số `0` ở đầu.
2. Các thành phần phân tách bằng dấu chấm `.`.
3. Các thành phần giữa có thể là `0`.
4. **Thành phần cuối không được là `0`**; các số `0` ở đuôi được bỏ đi.
5. Nếu phần số dài hơn bốn thành phần, các thành phần thứ năm trở đi dành cho implementation/vendor-specific patch information.
6. Mỗi số phải biểu diễn được bằng `int` khi parser Java chuyển đổi; chuỗi chứa số vượt giới hạn có thể gây `NumberFormatException`.

Bảng:

| Chuỗi | Kết quả | Lý do |
| --- | --- | --- |
| `10` | Hợp lệ | FEATURE=10 |
| `10.0.2` | Hợp lệ | Số `0` ở giữa, cuối là `2` |
| `10.0.0.1` | Hợp lệ | Các số `0` ở giữa, cuối là `1` |
| `10.0` | **Không hợp lệ** | Số `0` ở đuôi |
| `10.0.0` | **Không hợp lệ** | Số `0` ở đuôi |
| `10.01` | **Không hợp lệ** | Thành phần `01` có leading zero |
| `010` | **Không hợp lệ** | FEATURE bắt đầu bằng `0` |
| `0` | **Không hợp lệ** | FEATURE phải lớn hơn `0` |
| `10..2` | **Không hợp lệ** | Thiếu một thành phần số |
| `10.2147483648` | **Tràn số** | Thành phần không biểu diễn được bằng `Integer` |

**Đã kiểm chứng** các trường hợp trên với `Runtime.Version.parse` trong JDK 24.2. Đặc biệt, `10.0` bị từ chối, không tự biến thành `10`. Nếu bạn nhận một chuỗi không chuẩn từ nguồn ngoài, đừng tự ý chuẩn hóa nó rồi coi đó là thông tin chính thức của JDK.

### `version()` không phải lúc nào cũng có bốn phần tử

~~~java
Runtime.Version.parse("10").version();       // [10]
Runtime.Version.parse("10.0.2").version();   // [10, 0, 2]
~~~

`version()` trả về một **`List<Integer>` không thể sửa**. Nếu `interim()` hoặc `patch()` trả 0 vì phần tử thiếu, **list không nhất thiết tự thêm số 0 vào cuối**.

Điều này tránh nhầm lẫn khi in debug logs hoặc lưu cấu trúc phiên bản vào cơ sở dữ liệu.

## 5. Ngữ pháp chuỗi phiên bản đầy đủ (`VSTR`)

Ngoài `VNUM`, một chuỗi có thể gồm **pre-release**, **build number** và **optional build information**.

Theo Java SE 26, các dạng chủ yếu:

~~~text
VNUM(-PRE)?+BUILD(-OPT)?
VNUM-PRE(-OPT)?
VNUM(+-OPT)?
~~~

Trong đó:

- **`PRE`** là pre-release identifier, chỉ gồm chữ cái Latin và chữ số; ví dụ `ea`, `internal`.
- **`BUILD`** là số không âm, không có leading zeros (trừ số `0` độc lập).
- **`OPT`** là metadata tùy chọn, gồm chữ/số, dấu trừ hoặc dấu chấm trong phạm vi ngữ pháp Java.

Bảng kiểm tra:

| Input | `pre()` | `build()` | `optional()` |
| --- | --- | --- | --- |
| `10` | Rỗng | Rỗng | Rỗng |
| `10-ea` | `ea` | Rỗng | Rỗng |
| `10-ea+13` | `ea` | `13` | Rỗng |
| `10-ea-internal` | `ea` | Rỗng | `internal` |
| `10+0` | Rỗng | `0` | Rỗng |
| `10+13` | Rỗng | `13` | Rỗng |
| `10+13-LTS` | Rỗng | `13` | `LTS` |
| `10+-ea` | Rỗng | Rỗng | `ea` |
| `17.0.10+7-LTS` | Rỗng | `7` | `LTS` |

Những chuỗi này được **parse thành công** trong các phép thử với JDK 24.

### Sự khác biệt khó thấy: `10-ea` và `10+-ea`

- **`10-ea`**: dấu `-` ngay sau phần số cho biết `pre() = Optional["ea"]`.
- **`10+-ea`**: tổ hợp `+-` tương ứng **optional information** không có build number; `optional() = Optional["ea"]`, còn `pre()` rỗng.

Hai chuỗi **không đồng nghĩa**, dù đều có chữ `ea`. Không tự xây parser bằng cách kiểm tra `s.contains("-ea")` để xác định early-access.

### Vì sao có `-LTS`?

Theo JEP 322, nhà triển khai một dòng JDK có hỗ trợ dài hạn **có thể** cho `OPT` bắt đầu bằng `LTS` (ví dụ `17.0.10+7-LTS`).

Nhưng:

- Metadata `optional()=="LTS"` **không chứng nhận** chính sách cập nhật bảo mật hiện tại của vendor.
- Việc một chuỗi **có cú pháp hợp lệ** không chứng minh đó là release chính thức hoặc nhánh vẫn nhận bản vá.
- Các vendors có thể công bố `java.vendor.version` và thông tin sản phẩm ngoài định dạng chính.
- Khi ra quyết định support/security, phải kết hợp **release notes, build vendor, support agreement và ngày phát hành**; không chỉ nhìn suffix.

## 6. Những đầu vào không hợp lệ

Ví dụ đã kiểm chứng:

~~~text
""                 -> NumberFormatException   (JDK 24 đã thử)
"010"              -> IllegalArgumentException
"10.0"             -> IllegalArgumentException
"10.0.0"           -> IllegalArgumentException
"10..2"            -> IllegalArgumentException
"10+01"            -> IllegalArgumentException
"10+"              -> IllegalArgumentException
"10-ea+"           -> IllegalArgumentException
"10-rc.1"          -> IllegalArgumentException
"v10"              -> IllegalArgumentException
"1.8.0_402"        -> IllegalArgumentException
"10.2147483648"    -> NumberFormatException
"10+2147483648"    -> NumberFormatException
null               -> NullPointerException
~~~

Đây là **kết quả cụ thể trên JDK 24.0.2**, không nên xây ứng dụng dựa trên chi tiết message của exception, vì message có thể thay đổi.

**Hợp đồng API:**

- `IllegalArgumentException` khi không đọc được chuỗi thành phiên bản hợp lệ.
- `NumberFormatException` khi một numeric element hoặc build number không fit `Integer`. Đây là **lớp con của `IllegalArgumentException`**, nên một catch `IllegalArgumentException` cũng bắt được nó.
- `NullPointerException` khi input là `null`.

**Đừng gọi `Runtime.Version.parse` như một bước “tự sửa lỗi” cho đầu vào sai.** Parser cần input đúng format.

### Tại sao `1.8.0_402` bị từ chối?

Đây là dạng chuỗi **cũ** của dòng Java 8, không tuân theo ngữ pháp Java 9+/10+. `Runtime.Version` **không được thiết kế** để parse toàn bộ lịch sử version formats của Java. Nếu một hệ thống thật cần nhận nhiều version schemas, hãy thiết kế policy phân loại nguồn và chuyển đổi định dạng có kiểm chứng, thay vì “strip 1.8_” bằng regex đơn giản mà không hiểu vendor/version.

**Đặc biệt:** theo Special Note của module, phần hướng dẫn chính dùng cách Java hiện hành; không đề xuất quay về cơ chế parse `java.version` từ Java 8 như đường mặc định.

## 7. Các phương thức quan trọng của `Runtime.Version`

| API | Kiểu trả về | Mục đích |
| --- | --- | --- |
| `Runtime.Version.parse(String)` | `Runtime.Version` | Parse chuỗi version |
| `Runtime.version()` | `Runtime.Version` | Version JVM đang chạy |
| `feature()` | `int` | Feature release number |
| `interim()` | `int` | Interim release component hoặc 0 |
| `update()` | `int` | Update release component hoặc 0 |
| `patch()` | `int` | Emergency patch component hoặc 0 |
| `version()` | `List<Integer>` | Danh sách số trong VNUM, **không thể sửa** |
| `pre()` | `Optional<String>` | Pre-release identifier |
| `build()` | `Optional<Integer>` | Build number |
| `optional()` | `Optional<String>` | Optional build metadata |
| `compareTo(Version)` | `int` | So sánh tất cả các thành phần theo thứ tự ưu tiên |
| `compareToIgnoreOptional(Version)` | `int` | Bỏ qua **OPT**, vẫn xét numeric/pre/build |
| `equals(Object)` | `boolean` | Hai chuỗi version tương đương hoàn toàn |
| `equalsIgnoreOptional(Object)` | `boolean` | So sánh hai version mà bỏ qua OPT |
| `toString()` | `String` | Trả biểu diễn chuỗi version |

**Không dùng `major()/minor()/security()` cho code mới.** Chúng chỉ còn đó để tương thích những code đã dùng API cũ; tên và ngữ nghĩa dễ khiến người học hiểu sai cập nhật Java.

### Mẹo `Optional`

Không giả định luôn có build và suffix:

~~~java
Runtime.Version v = Runtime.Version.parse("10");
int build = v.build().orElse(-1);            // -1
String pre = v.pre().orElse("<none>");       // "<none>"
String extra = v.optional().orElse("");     // ""
~~~

`build()` trả `Optional<Integer>` chứ không phải `int`; `pre()`/`optional()` trả `Optional<String>`.

**Không dùng `v.build().get()` không điều kiện** — với `10`, Optional rỗng và `get()` ném `NoSuchElementException`.

## 8. Chương trình tổng hợp chạy được: `VersionParsingDemo.java`

Ví dụ sau là **một chương trình Java độc lập**, minh họa các kỹ thuật quan trọng:

- Parse version có số, build và OPT.
- Đọc đủ `feature/interim/update/patch` và `version()`.
- Phân biệt pre-release, build và optional.
- So sánh đúng theo `Runtime.Version` và sắp xếp có thứ tự.
- Thử các input sai và bắt exception có chủ đích.
- Kiểm tra danh sách `version()` không thể sửa.
- Nhận diện version JVM đang chạy **không hard-code phiên bản máy**.

Lưu thành **`VersionParsingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class VersionParsingDemo {
    public static void main(String[] args) {
        Runtime.Version v =
                Runtime.Version.parse("10.0.2+13-LTS");

        System.out.println("original=" + v);
        System.out.println("feature=" + v.feature());
        System.out.println("interim=" + v.interim());
        System.out.println("update=" + v.update());
        System.out.println("patch=" + v.patch());
        System.out.println("versionNumbers=" + v.version());
        System.out.println("pre=" + v.pre().orElse("<none>"));
        System.out.println("build="
                + v.build().map(Object::toString).orElse("<none>"));
        System.out.println("optional="
                + v.optional().orElse("<none>"));

        Runtime.Version early = Runtime.Version.parse("10-ea");
        Runtime.Version ga = Runtime.Version.parse("10");
        Runtime.Version built = Runtime.Version.parse("10+13");
        Runtime.Version longTerm =
                Runtime.Version.parse("10+13-LTS");
        Runtime.Version optionalOnly =
                Runtime.Version.parse("10+-ea");

        System.out.println("earlyBeforeGA="
                + (early.compareTo(ga) < 0));
        System.out.println("gaBeforeBuild="
                + (ga.compareTo(built) < 0));
        System.out.println("buildNineBeforeTen="
                + (Runtime.Version.parse("10+9")
                        .compareTo(Runtime.Version.parse("10+10")) < 0));
        System.out.println("compareFullDifferent="
                + (built.compareTo(longTerm) != 0));
        System.out.println("equalsFull="
                + built.equals(longTerm));
        System.out.println("equalsIgnoreOptional="
                + built.equalsIgnoreOptional(longTerm));
        System.out.println("compareIgnoreOptional="
                + built.compareToIgnoreOptional(longTerm));
        System.out.println("optOnlyPre="
                + optionalOnly.pre().orElse("<none>"));
        System.out.println("optOnlyOptional="
                + optionalOnly.optional().orElse("<none>"));
        System.out.println("numericCompare="
                + (Runtime.Version.parse("10.0.4")
                        .compareTo(Runtime.Version.parse("10.1.2")) < 0));
        System.out.println("patchPresent="
                + Runtime.Version.parse("10.0.0.1").patch());

        List<Runtime.Version> values = new ArrayList<>();
        for (String s : new String[] {
                "10.0.2+13", "10", "10-ea", "10.0.2+12",
                "10.0.2+13-LTS"}) {
            values.add(Runtime.Version.parse(s));
        }
        Collections.sort(values);
        System.out.println("sorted=" + values);

        for (String invalid : new String[] {
                "", "010", "10.0", "10..2", "10+01", "10 ",
                "10.2147483648", "10+2147483648"
        }) {
            try {
                Runtime.Version.parse(invalid);
                System.out.println(
                        "invalidUnexpectedlyParsed=" + invalid);
            } catch (IllegalArgumentException e) {
                System.out.println("invalid[" + invalid + "]="
                        + e.getClass().getSimpleName());
            }
        }
        try {
            Runtime.Version.parse(null);
        } catch (NullPointerException e) {
            System.out.println("nullInput=NullPointerException");
        }
        try {
            v.version().add(99);
        } catch (UnsupportedOperationException e) {
            System.out.println("versionListUnmodifiable=true");
        }
        System.out.println("runtimeAtLeast10="
                + (Runtime.version().feature() >= 10));
    }
}
~~~

**Giải thích một số lựa chọn thiết kế:**

- Toàn bộ input version cố định trong ví dụ dùng để cho **stdout xác định** khi chạy JDK 10+.
- `Runtime.version()` chỉ được dùng cho biểu thức `feature() >= 10`, nên output boolean này là `true` khi chạy trên JVM 10+; không in chính xác `Runtime.version().toString()` vì nó phụ thuộc JDK đang cài.
- `longTerm` trong demo chỉ là biến tên để minh họa suffix `LTS`; **`10+13-LTS` là chuỗi thử cú pháp, không xác nhận Java 10 được hỗ trợ LTS thực tế**.
- Chúng ta so sánh dấu của `compareTo` bằng `< 0`, `!= 0` thay vì dựa vào một số âm/dương cụ thể. API chỉ cam kết **âm, 0 hoặc dương**, không cam kết đúng `-1` hoặc `1`.
- `Collections.sort(values)` dùng `Runtime.Version.compareTo` thông qua natural ordering.
- Các exception test chỉ in **tên lớp exception**; message không có dạng ổn định bắt buộc.

## 9. Biên dịch theo Java 10 và chạy

Với một JDK có `javac` hỗ trợ release 10:

~~~bash
mkdir out10
javac --release 10 -encoding UTF-8 -d out10 VersionParsingDemo.java
java -cp out10 VersionParsingDemo
~~~

Câu lệnh `mkdir out10` tạo output directory (thực hiện khi thư mục chưa có). `--release 10` yêu cầu compiler ràng buộc **cú pháp, bytecode và platform APIs** theo Java 10.

**Thực nghiệm:** mã trên đã được biên dịch thật bằng **`javac 24.0.2 --release 10`**, chạy bằng JDK 24 **hai lần cho cùng output**, và `javap -verbose` xác nhận:

~~~text
major version: 54
~~~

Đó là class-file major version của **Java 10**. Tuy nhiên, thực nghiệm **không cài một JVM Java 10 riêng để chạy**; chỉ xác nhận source API/bytecode Java 10 và việc chạy trên JDK 24.

### Stdout đã kiểm thử hai lần trên JDK 24

~~~text
original=10.0.2+13-LTS
feature=10
interim=0
update=2
patch=0
versionNumbers=[10, 0, 2]
pre=<none>
build=13
optional=LTS
earlyBeforeGA=true
gaBeforeBuild=true
buildNineBeforeTen=true
compareFullDifferent=true
equalsFull=false
equalsIgnoreOptional=true
compareIgnoreOptional=0
optOnlyPre=<none>
optOnlyOptional=ea
numericCompare=true
patchPresent=1
sorted=[10-ea, 10, 10.0.2+12, 10.0.2+13, 10.0.2+13-LTS]
invalid[]=NumberFormatException
invalid[010]=IllegalArgumentException
invalid[10.0]=IllegalArgumentException
invalid[10..2]=IllegalArgumentException
invalid[10+01]=IllegalArgumentException
invalid[10 ]=IllegalArgumentException
invalid[10.2147483648]=NumberFormatException
invalid[10+2147483648]=NumberFormatException
nullInput=NullPointerException
versionListUnmodifiable=true
runtimeAtLeast10=true
~~~

### Đọc output

- `feature=10`, `interim=0`, `update=2`, `patch=0`: dữ liệu từ `10.0.2`.
- `versionNumbers=[10, 0, 2]`: danh sách số thực trong input, **không tự thêm patch=0**.
- `pre=<none>`: chuỗi test `10.0.2+13-LTS` không có pre-release.
- `build=13`: số sau dấu `+`.
- `optional=LTS`: metadata thêm sau build.
- `earlyBeforeGA=true`: bản `10-ea` được xếp trước `10`.
- `gaBeforeBuild=true`: theo quy tắc của `Runtime.Version.compareTo`, `10` không có build nhỏ hơn `10+13`.
- `buildNineBeforeTen=true`: build được so sánh **như số**, nên `9 < 10`.
- `equalsFull=false` và `equalsIgnoreOptional=true`: khác nhau đúng ở `OPT`.
- `compareIgnoreOptional=0`: chỉ bỏ qua `OPT`, không bỏ qua pre-release/build.
- `optOnlyPre=<none>` và `optOnlyOptional=ea` xác nhận `10+-ea` không giống `10-ea`.
- `numericCompare=true`: `10.0.4` nhỏ hơn `10.1.2` theo từng component.
- `patchPresent=1`: `10.0.0.1` có patch component.
- Dòng `sorted` thể hiện thứ tự natural sorting theo API.
- Các dòng `invalid` kiểm tra cách parser xử lý chuỗi không hợp lệ/tràn số.
- `versionListUnmodifiable=true`: `version()` không cho sửa danh sách.
- `runtimeAtLeast10=true`: điều kiện đúng với JVM JDK 24 trong lab; không tiết lộ version string phụ thuộc máy.

## 10. Thuật toán so sánh `compareTo` — không phải so chuỗi

Javadoc Java SE 26 xác định thứ tự ưu tiên khi so sánh hai `Runtime.Version` như sau:

1. **Version number sequence** (các số của `VNUM`).
2. **Pre-release identifier (`PRE`)**.
3. **Build number (`BUILD`)**.
4. **Optional build information (`OPT`)**, trừ khi gọi phương thức bỏ qua phần này.

### 10.1. Số trước, không phải thứ tự từ điển

~~~java
Runtime.Version a = Runtime.Version.parse("10.0.9");
Runtime.Version b = Runtime.Version.parse("10.0.10");

boolean older = a.compareTo(b) < 0; // true
~~~

Nếu đem so `"10.0.9".compareTo("10.0.10")`, phép so từ điển có thể cho quyết định ngược, vì ký tự `'9'` đứng sau `'1'`. Version parser so các **số nguyên**.

### 10.2. Nếu hai số đầu bằng nhau

~~~text
10.0.2  < 10.0.2.1
10.0.4  < 10.1.2
10      < 10.0.2
~~~

Khi dãy số thứ nhất ngắn hơn, những thành phần thiếu được xem là nhỏ hơn thành phần tương ứng của dãy dài hơn theo quy tắc `Runtime.Version`. Không tự ghép chữ số rồi so các chuỗi như `"10.0.2"` và `"10.0.2.1"`.

### 10.3. Pre-release thấp hơn bản không có PRE

~~~text
10-ea < 10
10-ea+13 < 10+13
~~~

Theo Javadoc, hai pre-release identifiers toàn chữ số được so số học, các định danh không hoàn toàn là số so lexicographic; numeric identifiers được xem là thấp hơn nonnumeric identifiers. **Đây là quy tắc của Java Runtime.Version**, không tự suy nó giống hoàn toàn SemVer của một sản phẩm khác.

### 10.4. Build number cũng tham gia ordering

~~~text
10 < 10+1 < 10+9 < 10+10
~~~

Phần build được so theo **số nguyên**, không phải chuỗi.

### 10.5. OPT nằm cuối

~~~text
10+13 < 10+13-LTS
~~~

Khi các phần khác ngang nhau, version **có optional metadata** được xem là lớn hơn version không có. Nếu cả hai cùng có `OPT`, Java dùng thứ tự từ điển cho metadata.

**Cảnh báo:** thứ tự trên là semantics của **API comparator**, không được diễn giải rằng suffix `LTS` tự làm build “được hỗ trợ an toàn hơn” hoặc security-patched hơn.

## 11. `compareToIgnoreOptional` chỉ bỏ qua một phần

Hai chuỗi:

~~~text
10+13
10+13-LTS
~~~

khác nhau ở `OPT`.

~~~java
Runtime.Version a = Runtime.Version.parse("10+13");
Runtime.Version b = Runtime.Version.parse("10+13-LTS");

boolean sameFull = a.equals(b);                  // false
boolean sameWithoutOpt = a.equalsIgnoreOptional(b); // true
int c = a.compareToIgnoreOptional(b);           // 0
~~~

**`compareToIgnoreOptional` không bỏ qua mọi metadata**; nó chỉ bỏ qua **`OPT`**, nhưng vẫn xét:

- `VNUM` (feature/interim/update/patch và các phần thêm).
- `PRE` (early access).
- `BUILD`.

Ví dụ:

~~~text
10+13  và 10+14  -> KHÁC khi compareToIgnoreOptional
10-ea  và 10     -> KHÁC khi compareToIgnoreOptional
10+13  và 10+13-LTS -> BẰNG khi compareToIgnoreOptional
~~~

Trong bài toán so sánh hai builds cùng release, đôi khi bạn muốn bỏ suffix vendor-specific; lúc đó dùng `compareToIgnoreOptional` **đồng bộ** với `equalsIgnoreOptional`.

**Không dùng `equalsIgnoreOptional` như một “equals” thay thế không suy nghĩ trong `HashSet` hoặc `HashMap`**. `hashCode()` là hợp đồng gắn với `equals(Object)`, không phải cơ chế chuẩn hóa tùy ý bỏ metadata. Nếu cần một key chuẩn hóa bỏ `OPT`, hãy thiết kế một value key riêng với `equals`/`hashCode` nhất quán.

## 12. `Runtime.Version` là value-based class

Tài liệu Java SE 26 ghi rõ `Runtime.Version` là **value-based class**. Do đó nên:

- Coi các đối tượng `Version` biểu diễn cùng một giá trị là **tương đương theo `equals`**.
- Không dựa vào `==` để suy luận hai lần parse có trả về cùng object hay không.
- Không dùng các đối tượng `Version` làm monitor cho `synchronized` hoặc `wait/notify`.
- Không đặt logic lên `System.identityHashCode(version)`.

Ví dụ đúng:

~~~java
Runtime.Version a = Runtime.Version.parse("10.0.2+13");
Runtime.Version b = Runtime.Version.parse("10.0.2+13");

boolean sameVersion = a.equals(b); // true
~~~

**Không khẳng định `a == b` sẽ luôn đúng hoặc sai**, vì identity không phải hợp đồng mà ứng dụng được phép dựa vào đối với value-based class.

## 13. Xử lý lỗi parse an toàn ở biên hệ thống

Dữ liệu phiên bản có thể đến từ cấu hình, manifest, API request, kết quả chẩn đoán hoặc một nguồn máy khác. Một chương trình production phải quyết định rõ:

1. Có chấp nhận `null` không?
2. Có trim khoảng trắng không, hay báo lỗi strict?
3. Có cần phân biệt invalid syntax và numeric overflow không?
4. Có giới hạn độ dài input và ghi logs an toàn không?
5. Có yêu cầu Java platform version đúng grammar, hay một version scheme khác?

Một hàm wrapper đơn giản:

~~~java
import java.util.Optional;

public final class VersionInput {
    private VersionInput() { }

    public static Optional<Runtime.Version> tryParse(String text) {
        if (text == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(Runtime.Version.parse(text));
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }
    }
}
~~~

Đây là **một class đầy đủ để biên dịch**, nhưng **không có `main`/stdout**. Hàm này giữ quy tắc **strict**: `" 10 "` bị coi là không hợp lệ, không tự sửa bằng `trim()`.

Nếu sản phẩm muốn cho phép khoảng trắng do người dùng nhập, có thể chủ động dùng `text.strip()` trước khi parse **trên JDK 11+** hoặc `trim()` với semantics phù hợp khi target Java 10. Điều đó phải được mô tả là **quy tắc làm sạch dữ liệu của ứng dụng**, không phải behavior tự động của parser.

**Không catch `Exception` rồi lặng lẽ biến mọi lỗi hệ thống thành “version invalid”**. Trong wrapper trên, `IllegalArgumentException` bao gồm `NumberFormatException` cho số tràn; `NullPointerException` được xử lý trước ở đầu vào. Những lỗi khác không nên bị che giấu.

### Phân biệt parse fail với “không đạt yêu cầu”

- `parse("10.0")` không hợp lệ: **invalid input**.
- `parse("10.0.2")` hợp lệ nhưng nhỏ hơn yêu cầu `17`: **valid but not eligible**.
- `Runtime.version()` trên một JDK hiện hành có version cao hơn: **runtime version observed**, không phải bằng chứng rằng một dependency tùy ý đã hoạt động.

Không dùng một boolean duy nhất cho cả ba trạng thái trong diagnostics nếu người vận hành cần biết phải sửa input hay nâng runtime.

## 14. Cách kiểm tra tính năng theo Java release

Nếu yêu cầu **feature version ≥ 17**, điều kiện phù hợp:

~~~java
if (Runtime.version().feature() < 17) {
    throw new IllegalStateException(
            "This application requires Java feature release 17 or later");
}
~~~

Mảnh code này thích hợp **trong một method**; phần source bao quanh phải được compile theo runtime tối thiểu thực sự hỗ trợ API. Trên Java 10 trở lên, `feature()` có sẵn.

### Vì sao không nên luôn dùng `compareTo("17")`?

Giả sử runtime là `17-ea`. Theo `compareTo`, bản pre-release đứng **trước** bản `17` GA, dù `feature() == 17`. Nếu policy của bạn chỉ cần **language feature level**, có thể dùng `feature()`; nếu policy yêu cầu **GA releases**, cần kiểm tra `pre().isEmpty()` và support policy riêng.

~~~java
Runtime.Version current = Runtime.version();

boolean hasFeatureLevel = current.feature() >= 17;
boolean isGaLike = current.pre().isEmpty();
~~~

**Không nói “không có `pre()` chắc chắn là GA được phát hành chính thức và có hỗ trợ”**. Đây chỉ là dấu hiệu trong version string. Xác minh vendor/build/support status riêng.

### Nếu yêu cầu một update-level cụ thể

Ví dụ chính sách đòi Java 17.0.10 hoặc mới hơn trong **cùng family/vendor được xác minh**:

~~~java
Runtime.Version minimum =
        Runtime.Version.parse("17.0.10");

Runtime.Version candidate =
        Runtime.Version.parse("17.0.11");

boolean newer = candidate.compareTo(minimum) >= 0; // true
~~~

**Cảnh báo:** việc so sánh version trong Java **không tự chứng minh** mọi security fix được đưa vào mọi vendor build, vì downstream vendors có thể backport/bổ sung patch theo chính sách riêng. Với compliance/security, tham khảo **JDK vendor advisories, release dates và bản vá**.

## 15. Đọc version hiện hành đúng cách

API chuẩn:

~~~java
Runtime.Version running = Runtime.version();

System.out.println(running.feature());
System.out.println(running.update());
System.out.println(running.pre().orElse("<none>"));
~~~

Ở đây stdout **phụ thuộc runtime đang chạy**, nên bài không bịa một kết quả cố định.

Các cách thay thế khác cần phân biệt:

| Nguồn | Mục đích | Hạn chế |
| --- | --- | --- |
| `Runtime.version()` | Đối tượng version JVM hiện tại | Dành cho version Java platform, không cho thư viện khác |
| `System.getProperty("java.version")` | Chuỗi version JVM dưới dạng property | Nếu muốn phân tích, cần chắc format phù hợp trước khi parse |
| `System.getProperty("java.runtime.version")` | Runtime build identification string | Có thể gồm vendor/build details; không phải chuỗi SemVer chung |
| `java --version` ở shell | Kiểm tra launcher và môi trường OS | Là **human-readable output**, không phải input sạch cho `Runtime.Version.parse` |
| `java.version.date` | Ngày GA/theo metadata Java release | Không thay thế version components |
| `java.vendor.version` | Thông tin do vendor đặt nếu có | Có thể không theo grammar `Runtime.Version` |

**Ưu tiên `Runtime.version()` khi đang ở trong Java process.** Không mở một subprocess chỉ để chạy `java -version`, rồi trích một vài ký tự bằng regex nếu Java runtime đã có API version typed.

## 16. Vì sao không dùng `String.compareTo`?

Chuỗi:

~~~text
10.0.9
10.0.10
~~~

Nếu so lexical:

~~~java
"10.0.9".compareTo("10.0.10")
~~~

ký tự `9` có thể được xem là lớn hơn `1`, dẫn đến một kết luận sai về thứ tự phiên bản.

Đúng:

~~~java
Runtime.Version a = Runtime.Version.parse("10.0.9");
Runtime.Version b = Runtime.Version.parse("10.0.10");

if (a.compareTo(b) < 0) {
    System.out.println("older");
}
~~~

**Stdout của mảnh code khi đặt trong một method và chạy:**

~~~text
older
~~~

Mặc dù ứng dụng có thể tự viết comparator theo numeric components, việc tự parse có thể bỏ sót **PRE/BUILD/OPT**, thêm phần số thứ năm, zero normalization, số tràn và syntax error. Với chuỗi phiên bản Java hiện hành, **tận dụng API chuẩn**.

## 17. Sorting các phiên bản

Với một danh sách:

~~~java
List<Runtime.Version> versions = new ArrayList<>();

for (String s : new String[]{
        "10.0.2+13", "10", "10-ea",
        "10.0.2+12", "10.0.2+13-LTS"}) {
    versions.add(Runtime.Version.parse(s));
}

Collections.sort(versions);
System.out.println(versions);
~~~

Đây là **mảnh code bên trong một method**, với imports `java.util.List`, `ArrayList` và `Collections`.

**Stdout đã kiểm chứng:**

~~~text
[10-ea, 10, 10.0.2+12, 10.0.2+13, 10.0.2+13-LTS]
~~~

**Khi muốn bỏ metadata `OPT` trong ordering**, chọn comparator thống nhất:

~~~java
versions.sort(Runtime.Version::compareToIgnoreOptional);
~~~

**Lưu ý:** comparator bỏ `OPT` có thể trả 0 cho hai đối tượng mà `equals` trả false. Trong `TreeSet`/`TreeMap`, cách này có thể khiến hai chuỗi khác nhau chỉ ở optional metadata được xem như cùng một key theo comparator. Chỉ dùng khi đó **thật sự là chính sách mong muốn**, và ghi rõ logic deduplication trong thiết kế.

## 18. Các chuỗi phiên bản với phần số thứ năm

Java SE 26 `Runtime.Version` cho phép phần `VNUM` có **độ dài tùy ý** với nguyên tắc cú pháp và `int`. Bốn thành phần đầu có ngữ nghĩa chuẩn `feature/interim/update/patch`; **thành phần thứ năm trở đi** dành cho nhà triển khai Java platform để biểu thị patch/revision riêng.

Ví dụ minh họa:

~~~text
17.0.10.2.5
~~~

Nếu chuỗi hợp lệ:

~~~java
Runtime.Version v =
        Runtime.Version.parse("17.0.10.2.5");

System.out.println(v.feature());  // 17
System.out.println(v.interim());  // 0
System.out.println(v.update());   // 10
System.out.println(v.patch());    // 2
System.out.println(v.version());  // [17, 0, 10, 2, 5]
~~~

**Đây là mảnh code minh họa**, không nói đây là một bản JDK thực được phát hành. Dùng `version()` nếu cần xử lý các thành phần vượt bốn phần đầu, và đừng tự gán ý nghĩa “security level” cho từng phần vendor-specific.

## 19. So sánh với Semantic Versioning của ứng dụng

Nhiều hệ sinh thái dùng SemVer với hình thức kiểu `1.2.3-beta.2+build.4`. **Đừng mặc định parser của `Runtime.Version` chấp nhận mọi chuỗi đó**, vì các grammar và comparison rules có khác biệt.

| Vấn đề | `Runtime.Version` cho Java platform | Một thư viện SemVer |
| --- | --- | --- |
| Cấu trúc số | JEP 322 `FEATURE.INTERIM.UPDATE.PATCH` | Thường major.minor.patch |
| Số phần tử | Có thể có 1, 3, 4 hoặc nhiều hơn, với quy tắc bỏ trailing zeros | Phụ thuộc SemVer spec/library |
| Pre-release | `-ea`, `-internal` và các định dạng theo Java | Có thể cho dấu chấm trong identifiers |
| Build metadata | `+BUILD` có numeric build counter | Thường `+metadata` free-form |
| Comparison | Java so `VNUM` rồi PRE/BUILD/OPT | SemVer rules khác, đặc biệt metadata ordering |
| Dữ liệu phù hợp | JDK/Java runtime release string | Phiên bản ứng dụng/thư viện theo SemVer |

**Không dùng `Runtime.Version` để thay thế Maven `ComparableVersion`, Gradle module version parser hoặc các thư viện SemVer chuyên biệt.** Chỉ sử dụng đúng domain của nó.

Một ví dụ ranh giới: `1.8.0_402` là kiểu chuỗi Java lịch sử và không được `Runtime.Version.parse` hiện hành chấp nhận; điều đó không phải bug khi dùng API đúng mục đích.

## 20. Những hiểu lầm phổ biến

| Hiểu sai | Diễn giải đúng |
| --- | --- |
| “`Runtime.Version` chỉ xuất hiện ở Java 10.” | Lớp có từ Java 9; các accessor mới `feature/interim/update/patch` từ Java 10. |
| “`feature()` chính là `major()` nên cứ dùng major.” | `major()` deprecated từ Java 10; dùng `feature()` cho ý nghĩa phát hành mới. |
| “Mọi version phải đủ 4 phần số.” | `10` hợp lệ, các accessor thiếu trả 0. |
| “`10.0` được chuẩn hóa thành `10`.” | `10.0` bị parse từ chối vì trailing zero. |
| “`10-ea` và `10+-ea` giống nhau.” | Cái đầu có PRE, cái sau có OPT. |
| “`10+13-LTS` chắc chắn là JDK 10 LTS.” | Chuỗi hợp lệ về syntax nhưng suffix không chứng minh bản phát hành/support status. |
| “`compareToIgnoreOptional` bỏ cả PRE, BUILD và OPT.” | Nó chỉ bỏ OPT, vẫn so PRE và BUILD. |
| “`String.compareTo` đủ để so phiên bản.” | Sai khi so các numeric components như `10.0.9` và `10.0.10`. |
| “`version()` là list cố định 4 số.” | List phản ánh số phần tử thật trong VNUM và không thể sửa. |
| “`build()` luôn có số.” | Trả `Optional<Integer>`, có thể rỗng. |
| “`optional()` có giá trị nghĩa là pre-release.” | `optional()` khác `pre()`. |
| “`parse(null)` giống như parse chuỗi rỗng.” | `null` ném NPE; chuỗi rỗng là invalid number/syntax. |
| “`NumberFormatException` hoàn toàn khác `IllegalArgumentException`.” | NFE là lớp con của IAE. |
| “`compareTo` luôn trả -1, 0, 1.” | API chỉ cam kết âm, 0 hoặc dương. |
| “Hai version bằng nhau phải là cùng object `==`.” | Value-based class; dùng `equals`. |
| “Có `LTS` là ứng dụng đã có đủ security fixes.” | Version metadata không thay release notes/support policy. |
| “Code compile `--release 10` là đã test trên JVM 10.” | Compile target và runtime test là hai bước khác nhau. |
| “Parser dùng được cho mọi product version.” | Domain là Java platform version strings, không phải mọi SemVer. |
| “Phần thứ ba tên `security` thì luôn chỉ tăng khi có bản vá bảo mật.” | Java 10 dùng `update()` vì update releases không chỉ có security changes. |

## 21. Chẩn đoán lỗi thường gặp

### 21.1. `IllegalArgumentException` khi parse

Kiểm tra input có:

- Leading zero: `010`, `10.01`.
- Trailing zero: `10.0`, `10.0.0`.
- Dấu phân cách sai: `10..2`.
- Build number có leading zero: `10+01`.
- Dấu `+` thiếu nội dung: `10+`.
- Pre-release sai grammar: `10-rc.1`.
- Whitespace vô ý: `" 10 "`.
- Version scheme không phải Java 9+: `1.8.0_402`.

**Không bỏ dấu chấm/khác biệt bằng thao tác chuỗi bừa bãi** để ép parser chấp nhận. Nếu cần xử lý data from old format, chuyển đổi bằng một module adapter riêng có test.

### 21.2. `NumberFormatException`

Số của `VNUM` hoặc `BUILD` quá lớn để biểu diễn bằng `Integer`:

~~~text
10.2147483648
10+2147483648
~~~

Nên đặt giới hạn input length nếu dữ liệu đến từ bên ngoài và ghi log có cấu trúc, không ghi toàn bộ payload không kiểm soát. `Runtime.Version` tự xử lý ràng buộc số; không cần dùng `Double`, `BigDecimal` hoặc parse numeric riêng chỉ để so phiên bản Java.

### 21.3. `NullPointerException`

`Runtime.Version.parse(null)` không trả Optional rỗng; API ném NPE. Xác thực null **trước** khi gọi.

### 21.4. `NoSuchMethodError: Runtime.Version.feature()` trên runtime quá cũ

`feature()` có từ Java 10. Nếu một class được tạo không ràng buộc API theo target và chạy trên runtime thấp hơn Java 10, method có thể không tồn tại. Với code dự định chạy trên Java 10 trở lên, dùng `javac --release 10` để khóa platform API và bytecode; đồng thời chạy test trên môi trường phù hợp khi có yêu cầu compatibility thực sự.

### 21.5. Lỗi khác do parse `java -version`

Launcher output có vendor, ngày phát hành, VM name và formatting riêng; nó **không phải một version string đơn lẻ đã được chuẩn hóa để truyền nguyên vào `parse`**. Trong Java process, dùng `Runtime.version()`. Với công cụ bên ngoài process, chọn nguồn dữ liệu đã cấu trúc hoặc chỉ trích phiên bản bằng giao thức/contract cụ thể của công cụ đó.

## 22. Bài tập tự kiểm tra

### Bài 1 — parse feature

**Đề:** Parse `"10.0.2+13"`. `feature()`, `interim()` và `update()` là gì?

**Đáp án:** `10`, `0`, `2`.

### Bài 2 — patch

**Đề:** `"10.0.0.1"` có `patch()` là bao nhiêu?

**Đáp án:** `1`. Đây là `VNUM` hợp lệ vì phần cuối khác `0`.

### Bài 3 — thiếu thành phần

**Đề:** `Runtime.Version.parse("17").patch()` và `.version()` bằng gì?

**Đáp án:** `patch() == 0`; `version() == [17]`.

### Bài 4 — trailing zero

**Đề:** Vì sao `"17.0.0"` không hợp lệ?

**Đáp án:** VNUM không được có trailing zero components; chỉ `17` đại diện phần số không chứa update/patch nào khác 0.

### Bài 5 — early access

**Đề:** `"17-ea"` có `pre()` giá trị gì, có lớn hơn `"17"` không?

**Đáp án:** `pre() = "ea"`; theo `compareTo` bản có PRE **thấp hơn** bản không có PRE.

### Bài 6 — optional-only

**Đề:** `"10+-ea"` có `pre()` là `ea` không?

**Đáp án:** Không. `pre()` rỗng; `optional()` chứa `ea`.

### Bài 7 — build

**Đề:** `"10+9"` và `"10+10"`, cái nào lớn hơn?

**Đáp án:** `10+10`; build numbers so theo số, không theo text.

### Bài 8 — metadata

**Đề:** `"10+13"` và `"10+13-LTS"` có bằng nhau theo `equalsIgnoreOptional`?

**Đáp án:** Có; nhưng `equals` trả false.

### Bài 9 — so sánh update

**Đề:** `"17.0.9"` và `"17.0.10"`, cái nào mới hơn theo API?

**Đáp án:** `17.0.10`, vì 10 > 9 ở update component.

### Bài 10 — parse exception

**Đề:** `parse("010")` ném loại gì? `parse(null)` thì sao?

**Đáp án:** Input `010` không hợp lệ, `IllegalArgumentException`; `null` ném `NullPointerException`.

### Bài 11 — số tràn

**Đề:** `parse("17+2147483648")`?

**Đáp án:** `NumberFormatException` vì build number vượt `Integer.MAX_VALUE`.

### Bài 12 — feature eligibility

**Đề:** Kiểm tra JVM đang chạy có feature-level ít nhất Java 21 mà không phụ thuộc build metadata như thế nào?

**Đáp án:** `Runtime.version().feature() >= 21`. Sau đó đánh giá policy GA/security/support riêng.

### Bài 13 — List bất biến

**Đề:** Có thể thực hiện `v.version().add(99)` không?

**Đáp án:** Không; `version()` trả unmodifiable `List`, ném `UnsupportedOperationException` nếu thêm.

### Bài 14 — hỗ trợ LTS

**Đề:** Vì sao không thể từ `optional()=="LTS"` suy một JDK đã có đủ bản vá bảo mật?

**Đáp án:** LTS là metadata vendor/build; tình trạng hỗ trợ và bản vá phải kiểm chứng từ vendor/release notes/contract, không từ parser.

### Bài 15 — so sánh ignore optional

**Đề:** `compareToIgnoreOptional` của `10-ea` với `10` có trả 0 vì đã bỏ metadata không?

**Đáp án:** Không. PRE vẫn được xét; nó chỉ bỏ OPT.

### Bài 16 — ưu tiên phiên bản thật

**Đề:** `Runtime.version()` và `Runtime.Version.parse("26")` khác nhau ở điểm nào?

**Đáp án:** `Runtime.version()` đọc version JVM đang chạy; `parse("26")` chỉ tạo đối tượng từ string, không chứng minh runtime hiện tại là JDK 26.

### Bài 17 — class-file compatibility

**Đề:** Biên dịch `VersionParsingDemo` với `--release 10` tạo class major mấy?

**Đáp án:** **54**, đã kiểm thử bằng `javap` trên JDK 24.

### Bài 18 — version string scheme

**Đề:** `Runtime.Version.parse("1.8.0_402")` có hoạt động không?

**Đáp án:** Không theo grammar version Java 9+/10+; cần một adapter khác nếu thật sự phải xử lý định dạng lịch sử.

## 23. Checklist kiểm thử và triển khai

- [ ] Xác định input là **Java platform version string** chứ không phải product SemVer bất kỳ.
- [ ] Với JVM đang chạy, ưu tiên **`Runtime.version()`**.
- [ ] Với input chuỗi, dùng **`Runtime.Version.parse(String)`**.
- [ ] Đã hiểu `FEATURE.INTERIM.UPDATE.PATCH` và các thành phần bị lược khi bằng 0 ở cuối.
- [ ] Không dùng các accessor deprecated `major/minor/security` cho code mới.
- [ ] Dùng `Optional` an toàn cho `pre/build/optional`.
- [ ] Hiểu `10-ea` và `10+-ea` là hai trường hợp khác.
- [ ] Không tự gán `LTS` thành tình trạng bảo mật/hỗ trợ đã được chứng nhận.
- [ ] Khi so sánh, dùng `compareTo` hoặc `compareToIgnoreOptional` theo policy.
- [ ] Không dùng `String.compareTo` cho các numeric version parts.
- [ ] Không trộn `equals` với `equalsIgnoreOptional` hoặc `TreeSet` comparator theo cách gây mất bản ghi ngoài ý muốn.
- [ ] Không dùng identity hoặc `synchronized(version)` vì đây là value-based class.
- [ ] Trước parse xử lý `null` và chính sách whitespace.
- [ ] Bắt các lỗi cú pháp và tràn số có chủ đích.
- [ ] Thử các input hợp lệ/không hợp lệ từ dữ liệu thực.
- [ ] Với feature gating, dùng `feature()` thay vì ép `compareTo` có build metadata.
- [ ] Với yêu cầu security/support, kết hợp vendor release notes, build và patch policy.
- [ ] Với Java 10 compatibility, dùng `javac --release 10` trên JDK compiler còn hỗ trợ.
- [ ] Xác minh major bytecode 54 và chạy smoke tests ở runtime thích hợp nếu có yêu cầu.
- [ ] Ghi log structured version fields, không chỉ copy output human-readable của launcher.

## 24. Tổng kết

**`Runtime.Version` là API Java chuẩn để phân tích, so sánh và đọc metadata của các chuỗi version Java SE/JDK hiện hành.** Nó được giới thiệu từ Java 9, sau đó được điều chỉnh cho mô hình phát hành Java 10 theo JEP 322 với các accessor `feature()`, `interim()`, `update()` và `patch()`.

Một phiên bản có thể chỉ gồm `VNUM` hoặc thêm `PRE`, `BUILD` và `OPT`. Các thành phần này **không thể xử lý đúng bằng cách tách dấu chấm rồi so từ điển**. API chuẩn kiểm tra ngữ pháp, so numeric parts, áp thứ tự pre-release/build/optional và cung cấp `Optional` rõ ràng.

**Khi kiểm tra JVM hiện tại, dùng `Runtime.version()`.** Khi cần đọc string, dùng `Runtime.Version.parse(...)` và bắt lỗi hợp lý. Dùng `compareToIgnoreOptional` chỉ khi thật sự muốn bỏ `OPT`; đừng nhầm nó bỏ toàn bộ pre-release/build.

Cuối cùng, **parse hợp lệ không chứng minh một bản JDK được hỗ trợ**, suffix LTS không tự bảo đảm security updates, và việc compile `--release 10` không tự thay cho thử nghiệm trên runtime đích.

### Nguồn tham khảo chính thức còn áp dụng

1. [Oracle Java SE 26 — `Runtime.Version` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): grammar `VNUM/VSTR`, parse exceptions, accessor `feature/interim/update/patch`, `version()/pre()/build()/optional()`, compareTo và value-based behavior.
2. [Oracle Java SE 26 — `Runtime` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#version()): `Runtime.version()` đọc phiên bản JVM hiện hành.
3. [OpenJDK — JEP 322: Time-Based Release Versioning](https://cr.openjdk.org/~mr/jdk/jeps/322-time-based-release-versioning.html): ngữ nghĩa `FEATURE.INTERIM.UPDATE.PATCH` và thay đổi API từ Java 10.
4. [OpenJDK — JEP 223: New Version-String Scheme](https://openjdk.org/jeps/223): nguồn gốc sơ đồ chuỗi version từ Java 9.
5. [Oracle Java SE 10 — `Runtime.Version` Javadoc](https://docs.oracle.com/javase/10/docs/api/java/lang/Runtime.Version.html): các accessor mới có "Since: 10" và deprecations từ Java 10.
6. [Oracle Java SE 26 — `javac` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--release 10` khi được hỗ trợ để nhắm source/API/class-file Java 10.
7. [Oracle Java SE 26 — JVM Specification, class-file versions](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/se4/html/jvms-4.html): định dạng bytecode và class-file version.
8. [Oracle Java Migration Guide — New Version-String Scheme](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): Java 10 điều chỉnh phiên bản JEP 322, khác định dạng Java 8.
