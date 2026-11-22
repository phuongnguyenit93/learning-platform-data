# `Runtime.Version.feature()`, `interim()`, `update()` và `patch()` trong Java 10+

*Chủ đề Java 10 — `Runtime.Version`. Bài học tập trung vào bốn phương thức `feature()`, `interim()`, `update()` và `patch()`, ý nghĩa từng thành phần trong mô hình phiên bản dựa trên thời gian từ Java 10, cách lấy phiên bản JVM thực tế, parse/so sánh phiên bản và các trường hợp dễ nhầm. Kiến thức dùng API vẫn còn hiệu lực trên Java 17+ và JDK hiện đại.*

## 1. Vì sao Java 10 cần cách đọc phiên bản mới?

Từ Java 10, hệ sinh thái Java dùng sơ đồ phiên bản **theo chu kỳ phát hành** (*time-based release versioning*) được mô tả trong **JEP 322**. Bốn phần đầu của số phiên bản có ý nghĩa:

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

Ví dụ:

~~~text
17.0.10.1
│  │ │  └─ PATCH = 1
│  │ └──── UPDATE = 10
│  └────── INTERIM = 0
└───────── FEATURE = 17
~~~

Java 10 bổ sung bốn phương thức truy cập rõ ngữ nghĩa trên `java.lang.Runtime.Version`:

~~~java
int feature = version.feature();
int interim = version.interim();
int update  = version.update();
int patch   = version.patch();
~~~

Các thành phần **không đồng nghĩa**:

- `feature()`: phiên bản tính năng/nhánh phát hành Java, ví dụ `17`, `21`, `25`.
- `interim()`: số đếm phát hành trung gian, thường bằng `0` trong mô hình phát hành sáu tháng đã sử dụng.
- `update()`: số đếm phát hành cập nhật trên cùng nhánh feature, ví dụ `10` của `17.0.10`.
- `patch()`: số đếm bản vá khẩn cấp, tương ứng phần thứ tư khi có.

**Quan trọng:** Đây là bốn **số nguyên có vị trí xác định trong số phiên bản**, không phải mô hình Semantic Versioning (SemVer) gồm major/minor/patch. Chúng cũng **không đo số lượng tính năng**, **không đo số lỗ hổng**, và không tự nói một JDK còn được vendor hỗ trợ hay không.

## 2. Hai API đầu vào: `Runtime.version()` và `Runtime.Version.parse(...)`

### 2.1. Đọc phiên bản của Java runtime đang chạy

~~~java
Runtime.Version actual = Runtime.version();

System.out.println(actual.feature());
System.out.println(actual.interim());
System.out.println(actual.update());
System.out.println(actual.patch());
~~~

`Runtime.version()` trả đối tượng `Runtime.Version` mô tả **Java runtime hiện đang thực thi chương trình**. Không cần tự cắt chuỗi từ output của `java --version`.

Điều này đặc biệt hữu ích khi logic của ứng dụng cần kiểm tra **feature level của JVM đang chạy**.

~~~java
if (Runtime.version().feature() < 17) {
    throw new IllegalStateException("Java 17+ is required");
}
~~~

Trong ví dụ này, kiểm tra feature chỉ nói về **dòng phát hành**, không chứng minh mọi class/module/preview feature của Java 17 đều tự động khả dụng khi compiler/module configuration khác nhau.

**Không nhầm:**

- `Runtime.version()` → phiên bản runtime **đang chạy**.
- `javac --release 17` → biên dịch theo platform API và định dạng class được chỉ định cho Java 17 (nếu JDK compiler hỗ trợ tùy chọn ấy).
- `javac -version` → phiên bản **compiler** được gọi ở terminal.
- `java --version` → phiên bản **launcher/runtime** được gọi trong môi trường terminal.

Một chương trình được biên dịch với `--release 17` rồi chạy trên JDK 24 vẫn có `Runtime.version().feature() == 24` trong môi trường ấy. Tùy chọn biên dịch không làm runtime tự giả vờ là phiên bản 17.

### 2.2. Phân tích một chuỗi phiên bản hợp lệ

~~~java
Runtime.Version parsed = Runtime.Version.parse("17.0.10.1");

System.out.println(parsed.feature()); // 17
System.out.println(parsed.interim()); // 0
System.out.println(parsed.update());  // 10
System.out.println(parsed.patch());   // 1
~~~

`Runtime.Version.parse(String)` nhận **chuỗi phiên bản Java theo grammar của lớp này** và tạo một đối tượng để truy vấn hoặc so sánh.

Điều này phù hợp với dữ liệu cấu hình, log của JVM hoặc metadata Java deployment **đã tuân thủ đúng format**, chứ không phải parser tổng quát cho mọi kiểu phiên bản thư viện như `1.2.3-SNAPSHOT` hay `v1.2.3`.

**Phân biệt dữ liệu thực tế và ví dụ cú pháp:** Những chuỗi mẫu trong bài có thể là phiên bản giả định để giải thích cấu trúc. `parse(...)` chỉ xác nhận **cú pháp và khả năng biểu diễn số**, không kiểm tra một bản build tương ứng từng được phát hành công khai.

## 3. Ý nghĩa của bốn thành phần theo JEP 322

| Thành phần | Vị trí | Phương thức | Giá trị vắng mặt | Ý nghĩa |
| --- | ---: | --- | ---: | --- |
| `$FEATURE` | 1 | `feature()` | Không được thiếu | Bộ đếm feature release |
| `$INTERIM` | 2 | `interim()` | `0` | Bộ đếm interim release |
| `$UPDATE` | 3 | `update()` | `0` | Bộ đếm update release |
| `$PATCH` | 4 | `patch()` | `0` | Bộ đếm emergency patch release |

Tất cả bốn getter trả `int` — **không phải `OptionalInt` hoặc `Optional<Integer>`**. Khi phần thứ hai, ba hoặc bốn không xuất hiện trong chuỗi phiên bản hợp lệ, getter tương ứng trả **0**.

### 3.1. `feature()` — đếm lần phát hành tính năng

Ví dụ:

~~~java
Runtime.Version.parse("17").feature();      // 17
Runtime.Version.parse("21.0.4").feature();   // 21
Runtime.Version.parse("25-ea+9").feature();  // 25
~~~

`feature()` cho biết nhánh phát hành Java, không phải có 17/21/25 feature trong JDK đó. Trong mô hình phát hành định kỳ, bộ đếm tăng theo mỗi feature release; một bản cập nhật của cùng nhánh sẽ **không** đổi feature counter.

Cách dùng đúng thường là **feature-level gate**:

~~~java
boolean isJava17OrNewer = Runtime.version().feature() >= 17;
~~~

Không dùng `String.startsWith("17")` vì nó là so sánh văn bản, không phân tích thành phần có cấu trúc.

### 3.2. `interim()` — phát hành trung gian

JEP 322 dành một vị trí cho các đợt phát hành nằm giữa feature release và update release. Nó phục vụ mô hình có thể có đợt phát hành **tương thích** bao gồm sửa lỗi/cải tiến nhưng không tạo một feature release mới.

Ví dụ giả định để dễ nhìn:

~~~java
Runtime.Version v = Runtime.Version.parse("21.1.2.3");

System.out.println(v.feature()); // 21
System.out.println(v.interim()); // 1
System.out.println(v.update());  // 2
System.out.println(v.patch());   // 3
~~~

**Đây là chuỗi hợp lệ theo cú pháp, không khẳng định đã có JDK 21.1.2.3 chính thức.** Trong mô hình phát hành JDK thông dụng theo chu kỳ sáu tháng, `interim()` phần lớn là `0`. Đừng vì dữ liệu thực tế chủ yếu có `0` mà cho rằng phương thức vô dụng, đã bị bỏ hoặc có thể xóa khỏi bộ phân tích dữ liệu tương lai.

### 3.3. `update()` — số đếm đợt cập nhật

Ví dụ:

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.10");

System.out.println(v.feature()); // 17
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 10
System.out.println(v.patch());   // 0
~~~

Các đợt update tập trung sửa lỗi, regression và các vấn đề bảo mật trong mô hình release. Nhưng **không nên diễn giải số `10` là 10 bản vá CVE**, 10 tháng kể từ ngày ra mắt hoặc một “mức an toàn” có thể so chéo không cần ngữ cảnh.

- `17.0.10` là update counter `10` trên nhánh feature 17.
- `21.0.2` là update counter `2` trên nhánh feature 21.
- Không lấy `10 > 2` để nói Java 17 “mới hơn” Java 21: cần so sánh **đầy đủ số phiên bản** hoặc tuân thủ tiêu chí bảo mật/hỗ trợ của từng nhánh.

### 3.4. `patch()` — bản vá khẩn cấp

Ví dụ:

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.10.1");

System.out.println(v.feature()); // 17
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 10
System.out.println(v.patch());   // 1
~~~

`patch()` đọc phần thứ tư, được dành cho đợt sửa chữa khẩn cấp trong sơ đồ JEP 322.

**Phân biệt `patch` với `build`:** số đứng sau dấu `+` không phải phần thứ tư. Ví dụ:

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.10+7");

System.out.println(v.patch());                 // 0
System.out.println(v.build().orElse(-1));      // 7
~~~

Ở chuỗi này, `+7` là **build number**, không phải `patch=7`. Nhiều câu trả lời sai xuất phát từ việc lấy phần “cuối cùng” của một chuỗi phiên bản mà không biết nó nằm trước hay sau `+`.

## 4. Vì sao `17` là phiên bản hợp lệ, nhưng `17.0.0` không hợp lệ?

JEP 322 yêu cầu **phần tử số cuối cùng không được là 0**. Các thành phần có giá trị 0 **ở cuối** được **bỏ đi khỏi chuỗi**.

Ví dụ:

| Chuỗi | `feature()` | `interim()` | `update()` | `patch()` | Hợp lệ? |
| --- | ---: | ---: | ---: | ---: | --- |
| `17` | 17 | 0 | 0 | 0 | Có |
| `17.0.10` | 17 | 0 | 10 | 0 | Có |
| `17.0.10.1` | 17 | 0 | 10 | 1 | Có |
| `21.1` | 21 | 1 | 0 | 0 | Có về cú pháp |
| `21.0.0.1` | 21 | 0 | 0 | 1 | Có về cú pháp |
| `17.0` | — | — | — | — | Không: zero ở cuối |
| `17.0.0` | — | — | — | — | Không: zero ở cuối |
| `17.0.10.0` | — | — | — | — | Không: zero ở cuối |
| `17.00.10` | — | — | — | — | Không: số có leading zero |
| `17.0.10.` | — | — | — | — | Không: phần tử cuối bị thiếu |

Các `0` **nằm ở giữa** là hợp lệ nếu cần để định vị thành phần phía sau khác 0:

~~~java
Runtime.Version.parse("21.0.0.1"); // Hợp lệ: patch=1
Runtime.Version.parse("17.0.10");  // Hợp lệ: update=10
~~~

Còn `Runtime.Version.parse("17.0.0")` có thể ném `IllegalArgumentException`; không nên tự chèn các `.0` vào đuôi trước khi parse.

**Khái niệm cần tách:** Getter trả 0 cho một thành phần **vắng mặt**, nhưng không vì thế mà grammar yêu cầu viết tất cả các phần tử có giá trị 0 vào chuỗi.

### 4.1. Phương thức `version()` cho biết chính xác các phần tử có mặt

~~~java
var v = Runtime.Version.parse("17.0.10");

System.out.println(v.version()); // [17, 0, 10]
System.out.println(v.patch());   // 0
~~~

`version()` trả `List<Integer>` **không thể sửa** chứa những số **thực sự xuất hiện** trong `$VNUM`. Vì vậy, danh sách `[17, 0, 10]` có **3 phần tử**, còn `patch()` vẫn trả 0.

Không truy cập `v.version().get(3)` một cách mù quáng; với ví dụ trên nó gây `IndexOutOfBoundsException`, dù getter `patch()` an toàn.

### 4.2. Phiên bản có thể có phần tử thứ năm trở đi

Javadoc cho phép số phiên bản có nhiều hơn bốn phần tử; bốn phần đầu được chuẩn hóa ý nghĩa, còn các phần tử sau có thể được downstream JDK implementors dùng cho thông tin riêng.

Do đó, **không** viết parser bằng cách khẳng định `version().size() <= 4`. Tuy nhiên, khi logic chỉ cần bốn khái niệm chính từ JEP 322, hãy dùng bốn getter tường minh và hiểu rằng metadata bổ sung có thể cần chính sách riêng.

Không tự suy diễn phần tử thứ năm là một loại `patch()` mới theo định nghĩa chính thức.

## 5. `Runtime.Version` đã tồn tại từ Java 9, nhưng bốn getter có từ Java 10

Điểm lịch sử quan trọng để hiểu tên API:

- `java.lang.Runtime.Version` có từ Java 9; đây là lớp biểu diễn và so sánh phiên bản runtime.
- `feature()`, `interim()`, `update()`, `patch()` được giới thiệu với Java 10 để thể hiện rõ mô hình JEP 322.
- Các tên cũ `major()`, `minor()`, `security()` được đánh dấu **deprecated từ Java 10** vì thuật ngữ cũ không mô tả tốt sơ đồ mới.

Nếu viết kiến thức/ứng dụng **mới**, nên dùng:

~~~java
version.feature();
version.interim();
version.update();
version.patch();
~~~

Không nên dùng trong code mới:

~~~java
// Các tên lịch sử đã deprecated; chỉ nêu để nhận diện mã cũ.
version.major();
version.minor();
version.security();
~~~

Ba lời gọi cũ còn tồn tại vì khả năng tương thích, nhưng ý nghĩa được ánh xạ sang các thành phần tương ứng; sử dụng chúng trong một bài hướng dẫn hiện đại dễ làm người học hiểu sai `major/minor/security` theo semantics cũ.

**Đặc biệt:** `security()` không có nghĩa “trả số cấp độ an toàn” — trong mô hình Java 10, nó là tên deprecated cho vị trí `update()`. Đừng thiết kế kiểm tra bảo mật bằng cách gọi một phương thức tên `security()` rồi so giá trị.

## 6. Version number khác với version string đầy đủ

Một chuỗi phiên bản Java có thể chứa ba nhóm thông tin ngoài `$VNUM`:

~~~text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+- $OPT)?
~~~

Dòng cuối ở đây được viết tách bằng khoảng trắng để dễ nhìn ý tưởng; **cú pháp thực tế không có khoảng trắng** và là `$VNUM(+-$OPT)?`. Có thể tham khảo các ví dụ hợp lệ dưới đây.

Các loại thông tin:

| Phần | Ví dụ | Phương thức | Kiểu trả |
| --- | --- | --- | --- |
| Version number | `17.0.10.1` | `version()` và bốn getter | `List<Integer>`, `int` |
| Pre-release | `-ea` trong `21-ea+12` | `pre()` | `Optional<String>` |
| Build number | `+12` trong `21-ea+12` | `build()` | `Optional<Integer>` |
| Optional build information | `-LTS` trong `17.0.10+7-LTS` | `optional()` | `Optional<String>` |

Ví dụ:

~~~java
var v = Runtime.Version.parse("21-ea+12");

System.out.println(v.feature());          // 21
System.out.println(v.interim());          // 0
System.out.println(v.update());           // 0
System.out.println(v.patch());            // 0
System.out.println(v.pre().orElse("none")); // ea
System.out.println(v.build().orElse(-1));   // 12
~~~

Các getter số không bao gồm `ea` hoặc `build=12`. `21-ea+12` và `21` đều có `feature=21`, nhưng **không** phải cùng cấp ổn định phát hành: bản early-access có `pre=ea`.

### 6.1. Bản ổn định và bản early-access

~~~java
var ea = Runtime.Version.parse("21-ea+12");
var ga = Runtime.Version.parse("21");

System.out.println(ea.compareTo(ga) < 0); // true
~~~

`Runtime.Version.compareTo` có quy tắc ưu tiên **pre-release đứng trước release không có pre-release** khi các số phiên bản giống nhau. Đây là lý do chỉ so `feature()` không đủ nếu nhiệm vụ là **kiểm tra dòng GA đủ ổn định để chạy production**.

### 6.2. Build number không phải patch number

~~~java
var v = Runtime.Version.parse("17.0.10+7");

System.out.println(v.update()); // 10
System.out.println(v.patch());  // 0
System.out.println(v.build());  // Optional[7]
~~~

Trong việc hiển thị bản build cho vận hành, có thể cần cả `toString()` hoặc `build()`. Nhưng khi chỉ muốn kiểm tra feature/update/patch, dùng getter có tên, đừng tách dấu chấm trong một chuỗi chứa hậu tố `+7`.

### 6.3. Optional information và nhãn LTS

~~~java
var v = Runtime.Version.parse("17.0.10+7-LTS");

System.out.println(v.optional().orElse("none")); // LTS
~~~

`-LTS` ở đây thuộc `$OPT`. Nó **không phải một con số thứ năm** trong `$VNUM`. Nhãn tùy chọn do implementor cung cấp cũng **không tự đảm bảo** một JVM của bạn đang nhận hỗ trợ, có đủ CVE fixes mới nhất hoặc được vendor cấp entitlement hỗ trợ.

Một hệ thống quản trị nên kiểm tra cả nhà cung cấp, chu kỳ cập nhật, chính sách hỗ trợ và advisory thực tế thay vì kết luận chỉ từ một nhãn trong chuỗi.

## 7. So sánh số phiên bản: không dùng thứ tự từ điển của String

### 7.1. Sai lầm dễ gặp

~~~java
String a = "17.0.10";
String b = "17.0.2";

System.out.println(a.compareTo(b) > 0); // false
~~~

So sánh chuỗi ký tự nhìn thấy `"1"` đứng trước `"2"` ở vị trí thành phần update, nên không đại diện cho thứ tự **số học** của các phần tử.

### 7.2. Dùng `Runtime.Version.compareTo`

~~~java
var first = Runtime.Version.parse("17.0.10");
var second = Runtime.Version.parse("17.0.2");

System.out.println(first.compareTo(second) > 0); // true
~~~

`compareTo` hiểu cấu trúc phiên bản, lần lượt so các phần tử số từ trái qua phải rồi xét pre-release, build number và optional build information theo contract.

Các ví dụ về thứ tự thành phần số:

~~~text
17.0.2      < 17.0.10
17.0.10     < 17.0.10.1
17.0.10     < 17.1
17.0.10     < 21
21          < 21.0.0.1
~~~

Một phần bị thiếu được xem là nhỏ hơn phần có thêm ở phía đối chiếu theo quy tắc so sánh các chuỗi số trong Javadoc. `17.0.10` thấp hơn `17.0.10.1` vì bản thứ hai có patch=1.

### 7.3. Pre-release, build và optional cũng tham gia so sánh

`compareTo` không chỉ so bốn getter. Khi số version bằng nhau, nó xem:

1. Pre-release identifiers.
2. Build number.
3. Optional build information.

Ví dụ:

~~~java
Version.parse("21-ea+12").compareTo(Version.parse("21")) < 0
Version.parse("17+7").compareTo(Version.parse("17")) > 0
~~~

Đây là các biểu thức đặt trong lớp có import `java.lang.Runtime.Version`, không phải file Java độc lập. Thứ tự xây dựng do API định nghĩa; đừng áp dụng luật SemVer từ một thư viện khác rồi tin rằng Java dùng cùng quy tắc cho mọi hậu tố.

### 7.4. `compareToIgnoreOptional` chỉ bỏ qua optional build info

~~~java
var withLabel = Runtime.Version.parse("17.0.10+7-LTS");
var withoutLabel = Runtime.Version.parse("17.0.10+7");

System.out.println(withLabel.equals(withoutLabel)); // false
System.out.println(withLabel.equalsIgnoreOptional(withoutLabel)); // true
System.out.println(withLabel.compareToIgnoreOptional(withoutLabel)); // 0
~~~

`compareToIgnoreOptional` **chỉ bỏ qua `$OPT`** (thông tin xây dựng tùy chọn). Nó **không** mặc nhiên bỏ qua `$BUILD` hoặc `$PRE`, và không biến `17.0.10` thành `17.0.10.1`.

Nên dùng theo cặp nhất quán:

- `compareTo` ↔ `equals`.
- `compareToIgnoreOptional` ↔ `equalsIgnoreOptional`.

Đừng thay thế `equals(Object)` bằng so sánh String đã bỏ hậu tố theo quy tắc tùy ý; có thể làm sai hợp đồng khi số version hoặc thông tin build khác nhau.

## 8. Chương trình hoàn chỉnh Java 17+, đã biên dịch và chạy kiểm thử

Chương trình in các getter theo từng loại chuỗi, so sánh update/patch, pre-release, build và optional metadata, kiểm tra một số chuỗi sai grammar. Nó dùng phiên bản **giả định** để chứng minh thứ tự `interim/patch`, không khẳng định mọi số trong ví dụ đều là release từng tồn tại.

~~~java
// File: RuntimeVersionPartsDemo.java
import java.lang.Runtime.Version;
import java.util.List;

public class RuntimeVersionPartsDemo {
    static void show(String text) {
        Version version = Version.parse(text);
        System.out.printf(
                "%s -> feature=%d interim=%d update=%d patch=%d parts=%s%n",
                text,
                version.feature(),
                version.interim(),
                version.update(),
                version.patch(),
                version.version());
    }

    public static void main(String[] args) {
        for (String s : List.of(
                "17", "17.0.10", "17.0.10.1",
                "21.1.2.3", "21.0.0.1")) {
            show(s);
        }

        Version oldUpdate = Version.parse("17.0.2");
        Version newUpdate = Version.parse("17.0.10");
        System.out.println("17.0.10 newer than 17.0.2 = "
                + (newUpdate.compareTo(oldUpdate) > 0));
        System.out.println("patch newer than update = "
                + (Version.parse("17.0.10.1").compareTo(newUpdate) > 0));
        System.out.println("feature gate >= 17 = "
                + (Runtime.version().feature() >= 17));

        Version ea = Version.parse("21-ea+12");
        Version ga = Version.parse("21");
        System.out.println("early access older than GA = "
                + (ea.compareTo(ga) < 0));
        System.out.println("EA pre = " + ea.pre().orElse("none"));
        System.out.println("EA build = " + ea.build().orElse(-1));

        Version withOptional = Version.parse("17.0.10+7-LTS");
        Version withoutOptional = Version.parse("17.0.10+7");
        System.out.println("optional info = "
                + withOptional.optional().orElse("none"));
        System.out.println("full equality = "
                + withOptional.equals(withoutOptional));
        System.out.println("ignore optional equality = "
                + withOptional.equalsIgnoreOptional(withoutOptional));
        System.out.println("ignore optional comparison = "
                + withOptional.compareToIgnoreOptional(withoutOptional));

        System.out.println("number parts count = "
                + newUpdate.version().size());
        System.out.println("absent patch = " + newUpdate.patch());
        System.out.println("release17 with build is ordered later than bare = "
                + (Version.parse("17+7").compareTo(Version.parse("17")) > 0));

        for (String bad : List.of(
                "17.0.0", "17.00.1", "1.8.0_402", "17.0.10.")) {
            try {
                Version.parse(bad);
                System.out.println("invalid " + bad + " = accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid " + bad + " = rejected");
            }
        }
    }
}
~~~

Lưu đúng tên file `RuntimeVersionPartsDemo.java` và chạy với Java 17+:

~~~bash
javac --release 17 RuntimeVersionPartsDemo.java
java RuntimeVersionPartsDemo
~~~

**Stdout đã được kiểm chứng trên JDK 24, biên dịch target Java 17:**

~~~text
17 -> feature=17 interim=0 update=0 patch=0 parts=[17]
17.0.10 -> feature=17 interim=0 update=10 patch=0 parts=[17, 0, 10]
17.0.10.1 -> feature=17 interim=0 update=10 patch=1 parts=[17, 0, 10, 1]
21.1.2.3 -> feature=21 interim=1 update=2 patch=3 parts=[21, 1, 2, 3]
21.0.0.1 -> feature=21 interim=0 update=0 patch=1 parts=[21, 0, 0, 1]
17.0.10 newer than 17.0.2 = true
patch newer than update = true
feature gate >= 17 = true
early access older than GA = true
EA pre = ea
EA build = 12
optional info = LTS
full equality = false
ignore optional equality = true
ignore optional comparison = 0
number parts count = 3
absent patch = 0
release17 with build is ordered later than bare = true
invalid 17.0.0 = rejected
invalid 17.00.1 = rejected
invalid 1.8.0_402 = rejected
invalid 17.0.10. = rejected
~~~

### Giải thích kết quả từng nhóm

**Nhóm 1 — Bốn getter:** `17` chỉ có phần tử feature nhưng interim/update/patch vẫn là 0. `17.0.10` có update=10, patch=0. `17.0.10.1` có patch=1. `21.1.2.3` minh họa đủ cả bốn phần tử, không hàm ý đó là một release thực tế. `21.0.0.1` hợp lệ do có patch khác 0 dù giữa chuỗi chứa hai zero.

**Nhóm 2 — So sánh số:** `compareTo` dùng số nguyên cho từng thành phần nên `17.0.10 > 17.0.2`, khác so sánh chuỗi; `17.0.10.1 > 17.0.10` vì patch=1. `Runtime.version().feature() >=17` đúng trong môi trường chạy Java 17+.

**Nhóm 3 — Early access:** `pre=ea` và `build=12` là metadata của `21-ea+12`, trong khi bốn getter số vẫn phản ánh feature 21, các phần còn lại bằng 0. So sánh `ea` với `GA` cho thấy bản có pre-release đứng trước bản không có pre-release cùng số phiên bản.

**Nhóm 4 — Optional:** `17.0.10+7-LTS` khác `17.0.10+7` nếu so toàn chuỗi bằng `equals`, nhưng `equalsIgnoreOptional` là true và `compareToIgnoreOptional` là 0. Đó là cách API quản lý riêng hậu tố tùy chọn.

**Nhóm 5 — Không tự nhét patch vào danh sách:** `newUpdate.version().size()` là 3, nhưng `newUpdate.patch()` vẫn trả 0. Danh sách biểu diễn thành phần **hiện hữu**; getter cung cấp giá trị 0 logic khi vắng mặt.

**Nhóm 6 — Bản dựng:** `17+7` có build info, được so sau `17` theo hợp đồng `compareTo`. `+7` không phải patch=7.

**Nhóm 7 — Chuỗi sai:** `17.0.0` không hợp lệ vì zero ở cuối, `17.00.1` có leading zero, `1.8.0_402` là format khác grammar JEP 322, `17.0.10.` có phần tử trống. Trên JDK thử nghiệm, `Version.parse` từ chối cả bốn bằng `IllegalArgumentException`.

**Ghi chú về khả năng tái lập:** Chương trình chỉ in các kết quả có kỳ vọng ổn định trên JDK 17+, không in `Runtime.version().toString()` trực tiếp vì chuỗi ấy khác giữa các máy và nhà cung cấp. Lời gọi runtime thật chỉ được kiểm tra ngưỡng `>=17`, đúng với yêu cầu môi trường chạy mẫu.

## 9. Những quy tắc dùng trong ứng dụng thực tế

### 9.1. Kiểm tra phiên bản feature tối thiểu

Một ứng dụng chỉ hỗ trợ JDK 17 trở lên có thể kiểm tra khi khởi động:

~~~java
static void requireJavaFeature(int minFeature) {
    var current = Runtime.version();
    if (current.feature() < minFeature) {
        throw new IllegalStateException(
                "Requires Java " + minFeature
                + "+; current runtime: " + current);
    }
}
~~~

Đây là phương thức trong một lớp; không cần import cho `java.lang.Runtime` hoặc `IllegalStateException`. Nó dùng `feature()` thay vì cắt ký tự từ chuỗi `java.version`.

Nhưng việc `Runtime.version().feature() >=17` **không đảm bảo toàn bộ API/library/module application muốn dùng tồn tại**. Bạn còn cần target compiler phù hợp, module dependencies, JDK/JRE distribution và feature flags tương ứng. Chẳng hạn, preview feature có chính sách riêng, không tự được kích hoạt chỉ nhờ version lớn.

### 9.2. Kiểm tra tối thiểu cả update/patch

Nếu chính sách của ứng dụng yêu cầu một minimum Java release cụ thể, có thể dùng:

~~~java
Runtime.Version minimum = Runtime.Version.parse("17.0.10");

if (Runtime.version().compareTo(minimum) < 0) {
    throw new IllegalStateException(
            "Java runtime is older than required minimum");
}
~~~

Đây là một **kiểm tra số phiên bản**, không phải công cụ kiểm toán hỗ trợ bảo mật tự động. Nhân viên vận hành phải chỉ định minimum theo nhánh/version thực tế và các thông báo hỗ trợ/security advisory liên quan.

**Cẩn trọng với `compareTo`:** cùng số phiên bản nhưng khác `pre`/`build`/`optional` vẫn có thứ tự theo contract. Khi chính sách yêu cầu **GA/stable** và một số update tối thiểu, phải kiểm tra `pre().isEmpty()` nếu áp dụng, cùng logic so số phù hợp. Không quyết định “đủ bảo mật” chỉ vì so với một chuỗi `$VNUM` theo từ điển.

### 9.3. Với một bản update trên cùng nhánh

Có thể diễn đạt yêu cầu “nhánh 17 và update từ 10 trở lên” bằng một predicate có tên:

~~~java
static boolean hasRequired17Update(Runtime.Version v) {
    return v.feature() == 17
            && v.interim() == 0
            && (v.update() > 10
                    || (v.update() == 10 && v.patch() >= 0))
            && v.pre().isEmpty();
}
~~~

Đây là **mã minh họa cách tách các thành phần**, không phải một security policy hoàn chỉnh. Vì `patch()` luôn không âm đối với version hợp lệ, nhánh `patch() >= 0` ở ví dụ thực chất không thêm ràng buộc; trong ứng dụng thật, nên đơn giản hóa thành `v.update() >= 10` và chỉ dùng `patch()` nếu policy cần ngưỡng patch cụ thể, chẳng hạn cùng update 10 thì phải có patch ít nhất 1.

Nếu có nhiều nhánh JDK được hỗ trợ song song, một bộ điều kiện cố định theo feature 17 sẽ không phù hợp cho các JVM feature 21/25. Thiết kế danh sách minimum version **cho từng nhánh** hoặc chuẩn hóa theo hệ quản trị runtime của tổ chức.

### 9.4. Kiểm tra điều kiện cần patch cụ thể

Ví dụ giả định một policy yêu cầu ít nhất `17.0.10.1` trong nhánh `17`:

~~~java
var required = Runtime.Version.parse("17.0.10.1");
var current = Runtime.version();

boolean qualifies = current.compareTo(required) >= 0;
~~~

Policy này so thứ tự số phiên bản toàn phần nhưng không thể thay xác minh vendor/build và security patchset thực tế. Chỉ dùng khi yêu cầu được định nghĩa đủ rõ. Đặc biệt, một vendor có thể backport một fix vào dòng build riêng; số phiên bản đơn lẻ không phải lời khẳng định về mọi bản vá đã tích hợp.

## 10. Kiểm tra GA, EA và build metadata

### 10.1. `pre()` không phải một thành phần trong `$VNUM`

~~~java
var version = Runtime.Version.parse("21-ea+12");

System.out.println(version.feature());    // 21
System.out.println(version.pre());        // Optional[ea]
~~~

Một bản EA có cùng feature counter với GA. Nếu chính sách yêu cầu stable release, **không dùng chỉ `feature()` để kiểm tra**. Cần hiểu `pre()` hoặc nguồn thông tin GA của deployment.

### 10.2. `build()` không phải số cập nhật

~~~java
var version = Runtime.Version.parse("17.0.10+7");

System.out.println(version.update());     // 10
System.out.println(version.patch());      // 0
System.out.println(version.build());      // Optional[7]
~~~

Không xem `+7` là patch 7. Nếu hai bản build cùng `$VNUM` có build number khác, `compareTo` có thể phân biệt chúng theo contract.

### 10.3. `optional()` và thông tin vendor

~~~java
var version = Runtime.Version.parse("17.0.10+7-LTS");

System.out.println(version.optional().orElse("")); // LTS
~~~

Không trộn optional build info với feature/interim/update/patch. `equalsIgnoreOptional` có thể được dùng khi nghiệp vụ muốn so phiên bản **bỏ qua metadata tùy chọn**, nhưng nếu bạn cần phân biệt distribution/vendor, bỏ metadata có thể làm mất dữ liệu quan trọng.

### 10.4. `Runtime.Version` là value-based class

Javadoc mô tả `Runtime.Version` là một **value-based class**: hãy so giá trị bằng `equals`/`compareTo`, không dựa vào `==`, identity hash code hoặc đồng bộ `synchronized(version)`. Hai đối tượng có cùng thông tin version về mặt logic có thể được xem tương đương theo giá trị mà không cần cùng tham chiếu.

## 11. Phân biệt phiên bản Java với phiên bản thư viện và hệ điều hành

`Runtime.Version` chỉ định nghĩa cú pháp và ngữ nghĩa cho **Java runtime/Java SE version strings**, không phải parser của tất cả:

- Maven artifact version, ví dụ `1.2.3-SNAPSHOT`.
- NPM package semver, ví dụ `1.2.3-beta.1`.
- Docker image tag hoặc suffix OS-specific.
- Phiên bản sản phẩm backend do đội phát triển tự định nghĩa.
- Chuỗi `java -version` cũ có thể mang syntax không tương thích JEP 322.
- Các dòng metadata không có cấu trúc trong manifest.

Nếu cần parse version thư viện, dùng một kiểu/parser theo **hợp đồng phiên bản của chính thư viện ấy**, không ép mọi chuỗi đi qua `Runtime.Version.parse`.

Ví dụ chuỗi `1.8.0_402` của cách đặt tên lịch sử **không phải chuỗi hợp lệ theo JEP 322**, nên ví dụ biên dịch Java 17 ở mục 8 đã xác nhận `Version.parse` từ chối. Kiến thức hiện tại không cần dùng bộ API major/minor/security deprecated để phân tích các chuỗi ấy.

### 11.1. Không đo version bằng biểu thức regular expression tự đặt

Cách làm yếu:

~~~java
String[] fields = System.getProperty("java.version").split("\\.");
int update = Integer.parseInt(fields[2]);
~~~

Đây là đoạn minh họa **cách dễ sai**, không nên dùng. Với một runtime chỉ có version `17`, `fields[2]` không tồn tại. Với suffix `+build`, `fields[2]` có thể không hoàn toàn là chữ số. Đối với version strings đã có API chuẩn, dùng `Runtime.version()` hoặc `Runtime.Version.parse`, rồi chọn đúng getter.

### 11.2. Không phụ thuộc kích thước chuỗi

`"17.0.10"` dài hơn `"21"` nhưng không lớn hơn về thứ tự phiên bản. So sánh độ dài chuỗi, padding bằng zero, biểu thức regex tự viết hoặc tách theo dấu chấm rồi so chuỗi là những nguồn lỗi có thể tránh.

## 12. Trường hợp lỗi của `parse(String)` và xử lý an toàn

Javadoc của `Runtime.Version.parse` chỉ ra:

- `IllegalArgumentException` nếu chuỗi không thể diễn giải thành version string hợp lệ.
- `NullPointerException` nếu đầu vào `null`.
- `NumberFormatException` nếu một phần tử hoặc số build vượt miền biểu diễn `Integer`. Lưu ý `NumberFormatException` là subtype của `IllegalArgumentException`.

Ví dụ:

~~~java
try {
    var v = Runtime.Version.parse(input);
    // Xử lý v đã hợp lệ.
} catch (IllegalArgumentException invalidVersion) {
    // Báo cấu hình sai hoặc lỗi dữ liệu đầu vào tùy ngữ cảnh.
}
~~~

Đây là **đoạn code bên trong phương thức**, cần có biến `input`. Nếu muốn phân biệt null với grammar lỗi, validate null trước rồi bắt `IllegalArgumentException`.

### 12.1. Chuỗi có zero ở cuối

~~~java
Runtime.Version.parse("17.0.0"); // IllegalArgumentException
~~~

Không tìm cách sửa bằng một quy tắc auto-trim chung khi không nắm hợp đồng nguồn. Nếu input đến từ một hệ thống cũ, hãy định nghĩa một bước **chuyển đổi format có kiểm soát** và có test; không để parser âm thầm đoán tên version.

### 12.2. Số quá lớn

Một component ngoài khoảng int có thể phát sinh `NumberFormatException`. Tránh tự bắt ngoại lệ này rồi ép về 0: dữ liệu đầu vào thực sự không thể biểu diễn bằng API được chọn.

### 12.3. Dữ liệu không đáng tin từ bên ngoài

Nếu client gửi một chuỗi phiên bản tùy ý, có thể giới hạn chiều dài trước khi parse và báo lỗi rõ. Một chuỗi khớp grammar **không chứng minh client đang chạy đúng phiên bản ấy**; chuỗi có thể do client tự báo. Đối với yêu cầu bảo mật/runtime, nguồn xác thực và policy vẫn quan trọng.

## 13. Thiết kế test theo điều kiện có ý nghĩa

Để code quản trị phiên bản có độ tin cậy tốt, test những lớp trường hợp sau:

| Loại | Ví dụ | Điều cần khẳng định |
| --- | --- | --- |
| Chỉ feature | `"17"` | Bốn getter `17,0,0,0` |
| Có update | `"17.0.10"` | `update=10`, `patch=0` |
| Có patch | `"17.0.10.1"` | `patch=1` |
| Interim giả định | `"21.1.2.3"` | `interim=1` |
| Zero ở giữa | `"21.0.0.1"` | Hợp lệ vì số cuối khác 0 |
| Zero ở đuôi | `"17.0.0"` | Parse bị từ chối |
| Leading zero | `"17.00.1"` | Parse bị từ chối |
| Pre-release | `"21-ea+12"` | `pre=ea`, build=12, đứng trước GA |
| Optional | `"17.0.10+7-LTS"` | `optional=LTS`, ignoreOptional có ý nghĩa |
| Số update 2 chữ số | `"17.0.10"` vs `"17.0.2"` | So theo số: 10 > 2 |
| Java runtime thực | `Runtime.version()` | Feature đúng **runtime** của máy test, không hardcode số |
| Metadata build | `"17+7"` vs `"17"` | `compareTo` xét build |
| Kiểu legacy | `"1.8.0_402"` | Không phải version string mới hợp lệ |

**Tính portable:** Tránh hardcode `Runtime.version().feature() == 24` trong unit test phải chạy trên nhiều JDK. Tách test parser `Version.parse` theo chuỗi cố định khỏi test actual runtime. Chương trình mục 8 đã theo nguyên tắc đó.

### 13.1. Không viết test dựa trên output tùy biến của vendor

Một runtime có thể có thông tin build, optional info hoặc nhãn vendor riêng. Điều cần test là **nghĩa của getter và logic nghiệp vụ**, không phải tất cả vendor đều cho cùng `Runtime.version().toString()`.

Khi điều kiện vận hành cần chính xác một build, đặt requirement theo **cả distribution/vendor/build** và xác minh từ nguồn đáng tin. `Runtime.Version` có thể giúp parse/so sánh cấu trúc, nhưng nó không thay thế danh sách bản vá vendor được chấp thuận.

## 14. So sánh bốn getter với `version()`, `pre()`, `build()`, `optional()`

| API | Kiểu trả | Dùng khi |
| --- | --- | --- |
| `feature()` | `int` | Kiểm tra feature release |
| `interim()` | `int` | Đọc interim counter |
| `update()` | `int` | Đọc update counter |
| `patch()` | `int` | Đọc emergency patch counter |
| `version()` | `List<Integer>` unmodifiable | Cần đầy đủ thành phần số xuất hiện, kể cả phần thứ năm trở đi |
| `pre()` | `Optional<String>` | Phân biệt EA và không có pre-release |
| `build()` | `Optional<Integer>` | Lấy build number sau `+` |
| `optional()` | `Optional<String>` | Lấy hậu tố bổ sung |
| `compareTo(...)` | `int` | So sánh đầy đủ |
| `compareToIgnoreOptional(...)` | `int` | So sánh bỏ qua optional build info |

**Tại sao getter trả 0 thay vì Optional?** Bốn thành phần định vị logic luôn có nghĩa theo sơ đồ, ngay cả khi chuỗi rút gọn bỏ zero ở cuối. `feature` bắt buộc; interim/update/patch thiếu được xem là 0. Ngược lại, pre/build/optional là metadata **thực sự có hoặc không**, nên dùng `Optional`.

## 15. Các ngộ nhận và lỗi cần tránh

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “`feature()` là tổng số tính năng mới của Java.” | Không; là bộ đếm feature release. |
| “`interim()` luôn trả 0 theo API.” | Thường là 0 trong release phổ biến, nhưng API vẫn cho giá trị khác theo grammar. |
| “`update()` là số CVE đã sửa.” | Không; là bộ đếm phát hành cập nhật. |
| “`patch()` lấy số sau dấu `+`.” | Không; patch là phần số thứ tư trước dấu `+`. |
| “`17.0.10` có patch 10.” | Không; update=10, patch=0. |
| “`17.0.10.1` có update=1.” | Không; update=10, patch=1. |
| “Version hợp lệ luôn gồm đúng bốn phần tử.” | Không; có thể rút gọn zero cuối hoặc có phần tử thứ năm do implementor dùng. |
| “Muốn getter patch=0 thì phải ghi `.0` ở cuối.” | Không; zero cuối không được ghi theo grammar mới. |
| “`17.0.0` là cách viết tương đương `17` được `Version.parse` chấp nhận.” | Không; cuối cùng không được là zero. |
| “`version().size()` luôn bằng 4.” | Không; `17.0.10` chỉ có 3 phần tử. |
| “`version().get(3)` và `patch()` luôn như nhau về khả năng truy cập.” | Không; get(3) có thể lỗi vì thiếu phần tử; patch() trả 0. |
| “Dùng `String.compareTo` để xếp phiên bản Java.” | Sai, ví dụ 17.0.10 với 17.0.2. |
| “`major()`, `minor()`, `security()` là API nên ưu tiên cho code mới.” | Đã deprecated từ Java 10; dùng bốn getter có ngữ nghĩa mới. |
| “`Runtime.version()` đọc target của `javac --release`.” | Không; nó đọc Java runtime đang chạy. |
| “`feature>=21` nghĩa là chắc chắn GA, không cần xét `pre`.” | EA có thể có cùng feature; phải xét `pre` theo policy. |
| “`compareToIgnoreOptional` bỏ mọi metadata.” | Chỉ bỏ optional build info, không bỏ build/pre. |
| “Nhãn LTS trong optional chứng minh runtime có mọi security fix mới nhất.” | Không; còn vendor, support line và advisory thực tế. |
| “`Version.parse` xác thực bản release thực sự tồn tại.” | Không; nó xác thực grammar và số theo API. |
| “Dùng Runtime.Version parse mọi phiên bản thư viện khác nhau.” | Không; đây là schema Java SE/JDK. |
| “Bản update lớn hơn trên nhánh cũ luôn an toàn hơn feature mới.” | Không thể kết luận như vậy từ một thành phần. |
| “Runtime.Version object dùng làm lock cũng được.” | Lớp value-based, không nên dựa vào identity/synchronization. |

## 16. Câu hỏi và bài tập có lời giải

### Bài 1 — Chỉ có feature

~~~java
var v = Runtime.Version.parse("21");
~~~

**Hỏi:** Bốn getter cho giá trị nào?

**Đáp án:** `feature=21`, `interim=0`, `update=0`, `patch=0`. Các zero không cần xuất hiện trong chuỗi.

### Bài 2 — Số cập nhật

~~~java
var v = Runtime.Version.parse("17.0.10");
~~~

**Đáp án:** `feature=17`, `interim=0`, `update=10`, `patch=0`.

### Bài 3 — Số patch

~~~java
var v = Runtime.Version.parse("17.0.10.1");
~~~

**Đáp án:** `patch=1`; `update=10`. Đừng đảo vị trí hai trường.

### Bài 4 — Interim

~~~java
var v = Runtime.Version.parse("21.1.2.3");
~~~

**Đáp án:** `interim=1`, `update=2`, `patch=3`. Đây là chuỗi minh họa grammar, không chứng minh có bản JDK công khai tương ứng.

### Bài 5 — Zero ở giữa

~~~java
var v = Runtime.Version.parse("21.0.0.1");
~~~

**Đáp án:** Hợp lệ. Các số zero ở giữa định vị `patch=1`. Quy tắc cấm zero **ở phần tử cuối**, không cấm zero nội bộ.

### Bài 6 — Zero cuối

~~~java
Runtime.Version.parse("21.0.0");
~~~

**Đáp án:** `IllegalArgumentException` vì version number có trailing zeros. Dùng chuỗi `"21"` nếu ba thành phần sau bằng 0.

### Bài 7 — Build hay patch?

~~~java
var v = Runtime.Version.parse("17.0.10+7");
~~~

**Đáp án:** `patch=0`, `build().orElse(-1)=7`. `+7` không phải emergency patch.

### Bài 8 — Early access

~~~java
var v = Runtime.Version.parse("21-ea+12");
~~~

**Đáp án:** `feature=21` và `pre=ea`, `build=12`. Bản EA được xếp trước bản GA `21` khi so `compareTo`.

### Bài 9 — So sánh chuỗi

`"17.0.10"` và `"17.0.2"`: bản nào lớn hơn?

**Đáp án:** `17.0.10` lớn hơn, vì update 10 > 2. Dùng `Version.parse(...).compareTo(...)`, không dùng `String.compareTo`.

### Bài 10 — Optional LTS

`Version.parse("17.0.10+7-LTS")` và `Version.parse("17.0.10+7")` có `equals` bằng nhau không?

**Đáp án:** Không theo `equals` đầy đủ; nhưng `equalsIgnoreOptional` cho true và `compareToIgnoreOptional` cho 0 vì bỏ qua `$OPT`. `build=7` vẫn có ý nghĩa.

### Bài 11 — Lấy phần thứ tư trực tiếp từ `version()`

~~~java
var v = Runtime.Version.parse("17.0.10");
var fourth = v.version().get(3);
~~~

**Đáp án:** Ném `IndexOutOfBoundsException` do list chỉ có 3 phần tử. Dùng `v.patch()` để nhận 0 an toàn.

### Bài 12 — Feature runtime vs compiler

Biên dịch bằng JDK 24 với `javac --release 17` rồi chạy `java` của JDK 24. `Runtime.version().feature()` trả gì?

**Đáp án:** `24`, vì đó là phiên bản runtime đang thực thi. `--release 17` không đổi phiên bản JVM chạy. Nếu chạy trên JDK 17, kết quả sẽ là 17.

### Bài 13 — Parse chuỗi legacy

~~~java
Runtime.Version.parse("1.8.0_402");
~~~

**Đáp án:** Chuỗi này không theo format version hiện hành JEP 322, nên không được chấp nhận. Nếu ứng dụng thật cần hỗ trợ dữ liệu legacy, hãy viết lớp chuyển đổi theo nguồn và contract riêng, không khuyến nghị một API deprecated như giải pháp chung.

### Bài 14 — Kiểm tra đầu vào null

~~~java
Runtime.Version.parse(null);
~~~

**Đáp án:** `NullPointerException`. Kiểm tra input bắt buộc trước parse nếu muốn một thông báo lỗi cấu hình thân thiện.

### Bài 15 — Phân biệt parser và release thực

`Runtime.Version.parse("21.1.2.3")` thành công có chứng minh bản ấy được nhà cung cấp phát hành không?

**Đáp án:** Không. Parser chỉ kiểm tra cú pháp, không truy cập danh mục release thực tế.

### Bài 16 — Security policy

Ứng dụng đang chạy trên version có `feature=17` và `update=10`. Có thể kết luận JVM đã có mọi bản sửa bảo mật mới nhất không?

**Đáp án:** Không. Cần xét patch, build, vendor, thời điểm, bản sửa được backport và các thông báo bảo mật/cập nhật thật. Bốn getter chỉ mã hóa thành phần số phiên bản.

## 17. Checklist dành cho người học và code review

- [ ] Có dùng `Runtime.version()` để lấy phiên bản runtime thật thay vì tự parse `java.version` không?
- [ ] Có dùng `feature()`, `interim()`, `update()`, `patch()` theo ngữ nghĩa JEP 322 không?
- [ ] Có hiểu `update()` là phần thứ ba và `patch()` là phần thứ tư không?
- [ ] Có hiểu getter trả 0 khi interim/update/patch vắng mặt, không yêu cầu chuỗi đủ bốn số không?
- [ ] Có nhớ grammar cấm trailing zero, ví dụ `17.0.0` không hợp lệ không?
- [ ] Có nhớ `17.0.10` có list `[17,0,10]`, không thể gọi `get(3)` không?
- [ ] Có phân biệt `+7` build number với patch number không?
- [ ] Có phân biệt `-ea` pre-release với feature level không?
- [ ] Có cân nhắc `pre()` khi policy yêu cầu GA/stable không?
- [ ] Có dùng `Version.compareTo` thay vì `String.compareTo` khi cần thứ tự số phiên bản không?
- [ ] Nếu bỏ optional info, có dùng `compareToIgnoreOptional`/`equalsIgnoreOptional` nhất quán không?
- [ ] Có tránh deprecated `major()`, `minor()`, `security()` trong code mới không?
- [ ] Có phân biệt version Java với version thư viện dùng format khác không?
- [ ] Có biết `parse` không kiểm tra release thực sự tồn tại không?
- [ ] Có phân biệt source/target compiler version với runtime version không?
- [ ] Có tránh dùng số version như một bằng chứng tuyệt đối của trạng thái vá bảo mật không?
- [ ] Nếu cần minimum update, có kiểm tra cả feature line, pre-release và policy build/vendor phù hợp không?
- [ ] Có test các ca feature-only, update, patch, interim, build, EA, optional và malformed string không?
- [ ] Có tránh hardcode phiên bản của máy CI trong stdout khi chương trình cần chạy trên nhiều JDK không?
- [ ] Có xem `Runtime.Version` là value-based object, không dùng làm monitor lock hoặc so identity không?

## 18. Tài liệu chính thức còn hiệu lực

- [Java SE 25 API — `Runtime.Version`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): mô hình `$FEATURE.$INTERIM.$UPDATE.$PATCH`, getter `feature/interim/update/patch` (Since: 10), quy tắc `version()`, `parse`, `pre/build/optional`, `compareTo` và `equalsIgnoreOptional`.
- [Java SE 17 API — `Runtime.Version`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): xác nhận các phương thức này hiện diện trong Java 17 và có thể chạy chương trình mục 8 với `--release 17`.
- [Java SE API — `Runtime.version()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#version()): lấy thông tin phiên bản runtime đang thực thi chương trình.
- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): bốn thành phần, chu kỳ phát hành theo thời gian và định nghĩa tên mới từ Java 10.
- [Oracle Java Version-String Format](https://docs.oracle.com/en/java/javase/25/install/version-string-format.html): cách đọc version string Java 10+, quy tắc bỏ số 0 ở cuối và vị trí update/patch.
- [Java SE API — `System.getProperty`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#getProperty(java.lang.String)): truy xuất property runtime khi thật sự cần, nhưng `Runtime.version()` phù hợp hơn với kiểm tra có cấu trúc.
- [Java SE API — `Optional`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): xử lý metadata `pre()`, `build()` và `optional()` không có mặt mà không dùng null tùy tiện.

**Kết luận:** `Runtime.Version` biến chuỗi phiên bản Java thành các giá trị có cấu trúc. `feature()`, `interim()`, `update()` và `patch()` lấy **bốn thành phần số đầu tiên**, trả `0` cho những thành phần sau feature không có mặt. Phần `+BUILD` và `-OPT` **không phải patch**. Để so sánh đúng, dùng `compareTo`, không dùng so sánh String; để xử lý môi trường thật, lấy `Runtime.version()`. Khi đánh giá hỗ trợ/bảo mật, cần dữ liệu vendor và chính sách cập nhật bên ngoài bốn con số — đừng biến một version getter thành một phán đoán an toàn tuyệt đối.