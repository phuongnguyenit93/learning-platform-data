# Runtime.Version.parse và kiểm tra chuỗi phiên bản

## 1. Khi nào nên dùng Runtime.Version.parse?

Một ứng dụng Java đôi khi phải đọc thông tin phiên bản JDK từ tệp cấu hình, thông báo chẩn đoán, một bản kê môi trường hoặc yêu cầu tương thích. Thay vì tự tách chuỗi như `"21.0.2+13-LTS"` thành từng đoạn rồi đoán ý nghĩa, Java cung cấp API:

~~~java
Runtime.Version version = Runtime.Version.parse("21.0.2+13-LTS");
~~~

`Runtime.Version.parse(String)` kiểm tra chuỗi có tuân thủ định dạng **Java runtime version string** và tạo đối tượng `Runtime.Version` để đọc, so sánh từng thành phần.

~~~java
System.out.println(version.feature()); // 21
System.out.println(version.interim()); // 0
System.out.println(version.update());  // 2
System.out.println(version.patch());   // 0
System.out.println(version.build().orElse(-1)); // 13
System.out.println(version.optional().orElse("")); // LTS
~~~

Phương thức `Runtime.version()` khác hẳn: nó trả đối tượng mô tả **JVM đang chạy**, không parse một chuỗi do ứng dụng tự đưa vào.

**Mốc phiên bản:** lớp `Runtime.Version` cùng `parse(String)` xuất hiện từ Java 9. Từ Java 10, mô hình phiên bản dựa trên thời gian của **JEP 322** chuẩn hóa bốn tên thành phần `FEATURE`, `INTERIM`, `UPDATE`, `PATCH` và các accessor tương ứng. Những API đó vẫn được hỗ trợ trong Java hiện đại. Chương trình mẫu bên dưới chạy được trên **Java 17+**.

**Giới hạn quan trọng:** parse thành công chỉ chứng minh chuỗi **hợp lệ về cú pháp**. Nó không xác nhận bản JDK có thật, còn được nhà phân phối hỗ trợ, đã được vá mọi lỗ hổng hoặc tương thích với dự án.

## 2. Ngữ pháp của version number: VNUM

Phần cốt lõi của chuỗi là một **version number** (ký hiệu `$VNUM`) gồm các thành phần số nguyên, phân cách bằng dấu chấm.

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

Bốn vị trí đầu có ý nghĩa theo JEP 322:

| Vị trí | Tên | Mục đích |
| --- | --- | --- |
| 1 | `FEATURE` | Bộ đếm phát hành tính năng |
| 2 | `INTERIM` | Bộ đếm phát hành trung gian |
| 3 | `UPDATE` | Bộ đếm bản cập nhật tương thích |
| 4 | `PATCH` | Bộ đếm bản vá khẩn cấp |
| 5 trở đi | Phần bổ sung | Do nhà triển khai JDK sử dụng theo quy ước riêng |

Không nhất thiết phải nhập đủ bốn vị trí. Thành phần vắng mặt ở cuối có giá trị logic bằng `0` khi đọc qua accessor.

~~~java
Runtime.Version featureOnly = Runtime.Version.parse("21");
Runtime.Version updated = Runtime.Version.parse("21.0.2");
Runtime.Version patched = Runtime.Version.parse("21.0.2.1");

System.out.println(featureOnly.update()); // 0
System.out.println(updated.update());     // 2
System.out.println(patched.patch());      // 1
~~~

### Điều kiện về cách viết

Theo Javadoc và JEP 322, phần `$VNUM` có mẫu:

~~~text
[1-9][0-9]*((\.0)*\.[1-9][0-9]*)*
~~~

Ý nghĩa:

1. Thành phần đầu tiên là **số nguyên dương**, không được là `0`.
2. Các phần tử phân cách bằng một dấu chấm `.`.
3. Một phần tử có thể là `0` hoặc là số dương **không có số 0 ở đầu**.
4. Phần tử **cuối cùng** trong version number phải khác 0.
5. Dãy có thể dài hơn bốn thành phần, nhưng mỗi thành phần phải biểu diễn được bằng một số nguyên `int`.
6. Dấu cách, ký tự âm, dấu chấm thừa hoặc phần tử rỗng không hợp lệ.

Ví dụ chuỗi VNUM hợp lệ theo cú pháp:

~~~text
10
17
21
21.0.1
21.0.2
21.0.2.1
21.2
21.0.0.1
21.0.2.1.5
~~~

**Chú ý:** `21.2` hoặc `21.0.2.1.5` là ví dụ **có thể parse về mặt cú pháp**, không khẳng định có bản JDK được phát hành với số đó.

### Không có số 0 ở cuối

~~~text
21.0
21.0.0
21.0.2.0
~~~

Ba chuỗi trên đều không đúng dạng canonical của số phiên bản Java. Cách viết hợp lệ tương ứng là `21`, `21` và `21.0.2`.

~~~java
try {
    Runtime.Version.parse("21.0.2.0");
} catch (IllegalArgumentException expected) {
    System.out.println("trailing-zero rejected");
}
~~~

### Số 0 ở giữa phải giữ

~~~text
21.0.2 -> INTERIM=0, UPDATE=2
21.2   -> INTERIM=2, UPDATE=0
~~~

Hai chuỗi có nghĩa **khác nhau**. Đừng xóa toàn bộ ký tự `0` rồi cho rằng đang chuẩn hóa một version string.

~~~java
var a = Runtime.Version.parse("21.0.2");
var b = Runtime.Version.parse("21.2");

System.out.println(a.interim()); // 0
System.out.println(a.update());  // 2
System.out.println(b.interim()); // 2
System.out.println(b.update());  // 0
~~~

### Số 0 ở đầu phần tử không được phép

~~~text
021
21.01
21.0.02
21.00.2
~~~

`21.0.2` hợp lệ vì thành phần thứ hai là số `0` đúng quy tắc. `21.00.2` không hợp lệ vì `00` có số 0 dư đầu thành phần. Không tự động bỏ các số 0 này khi kiểm dữ liệu cấu hình nếu chính sách đòi đầu vào đúng format.

## 3. Cấu trúc version string: PRE, BUILD và OPT

Version **number** là dãy số. Version **string** còn có thể mang metadata về trạng thái pre-release, số build và thông tin tùy chọn.

Theo đặc tả `Runtime.Version`, version string tuân theo một trong các dạng:

~~~text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
~~~

Dấu `?` trong bản mô tả nghĩa là **không bắt buộc có phần đó**.

| Thành phần | Vai trò | Ví dụ | Method đọc |
| --- | --- | --- | --- |
| `$VNUM` | Dãy số phiên bản | `21.0.2` | `version()` và bốn accessor |
| `$PRE` | Nhãn pre-release | `ea` | `pre()` |
| `$BUILD` | Số bản build | `13` | `build()` |
| `$OPT` | Thông tin build tùy chọn | `LTS` | `optional()` |

### 3.1. PRE không phải INTERIM

~~~java
Runtime.Version early = Runtime.Version.parse("21-ea+3");

System.out.println(early.feature()); // 21
System.out.println(early.pre().orElse("")); // ea
System.out.println(early.build().orElse(-1)); // 3
~~~

`-ea` là dấu hiệu pre-release thường gặp. Nó không thay `FEATURE` hoặc `INTERIM`. Parser không tự đánh giá bản build đó có được chấp nhận dùng trong production hay không.

Phần `$PRE` theo cú pháp gồm ký tự chữ/số ASCII, ví dụ `ea` hoặc `internal`. Có nhiều nhãn phù hợp cú pháp; không suy rằng tất cả nhãn đó đều được công bố trong một phiên bản thực.

### 3.2. BUILD không phải UPDATE hay PATCH

~~~java
var release = Runtime.Version.parse("21.0.2+13");

System.out.println(release.update()); // 2
System.out.println(release.patch());  // 0
System.out.println(release.build().orElse(-1)); // 13
~~~

Dấu `+` mở phần build number. Số `13` ở đây **không** phải thành phần thứ tư của VNUM. Build number có thể là `0` hoặc số dương không có leading zero.

~~~text
21+0    -> hợp lệ về cú pháp, BUILD=0
21+13   -> hợp lệ về cú pháp, BUILD=13
21+01   -> không hợp lệ: số build có leading zero
~~~

### 3.3. OPT và ký hiệu LTS

~~~java
var v = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(v.build().orElse(-1)); // 13
System.out.println(v.optional().orElse("")); // LTS
~~~

`$OPT` là metadata bổ sung do nhà triển khai cung cấp. Ký hiệu `LTS` trong một chuỗi version có thể được dùng để thể hiện chế độ hỗ trợ dài hạn theo nhà phân phối. Tuy nhiên **việc parse thấy LTS không bảo đảm thời hạn hỗ trợ, lịch vá hoặc chính sách bản quyền** của một gói JDK nào đó.

Định dạng còn cho phép trường hợp metadata tùy chọn mà không có build number, ví dụ `21+-LTS`. Không tự đặt quy tắc “sau dấu cộng luôn phải có số build” nếu xử lý đầy đủ format JEP 322.

### 3.4. Các dạng thường gặp

~~~text
21
21.0.2
21.0.2.1
21-ea
21-ea+3
21.0.2+13
21.0.2+13-LTS
21+-LTS
~~~

`Runtime.Version.parse` kiểm tra cấu trúc theo JDK, không kết nối internet và không đối chiếu với danh sách phát hành của Oracle, OpenJDK hay bất kỳ nhà cung cấp nào khác.

## 4. Những chuỗi sai phải bị từ chối

Một bộ kiểm thử tốt cần cả input hợp lệ lẫn input sai:

| Input | Nguyên nhân sai |
| --- | --- |
| Chuỗi rỗng | Không có FEATURE |
| `0` | Thành phần đầu phải dương |
| `021` | FEATURE có leading zero |
| `21.01` | Thành phần sau dấu chấm có leading zero |
| `21.0` | Số 0 ở cuối |
| `21.0.2.0` | Số 0 ở cuối |
| `21..2` | Có thành phần rỗng |
| `21.` | Kết thúc bằng dấu chấm |
| `.21` | Bắt đầu bằng dấu chấm |
| `21.-2` | Có số âm |
| `21+01` | BUILD có leading zero |
| `21 ` | Có khoảng trắng không thuộc ngữ pháp |
| `2147483648` | Thành phần số không biểu diễn được bởi `Integer` |

Trong những trường hợp sai ngữ pháp, `parse` ném `IllegalArgumentException`; nếu một số quá lớn, nó có thể ném `NumberFormatException` theo Javadoc.

Đừng viết hàm tự chia chuỗi bằng regex đơn giản rồi quyết định chỉ bằng số lượng dấu chấm. Cú pháp có `PRE`, `BUILD`, `OPT`, số 0 ở giữa và số 0 cuối, vì vậy cách tự tách thường dễ sai.

### Thông điệp cho người dùng

Nếu người dùng nhập một version string sai, nên báo rõ định dạng ví dụ như `21`, `21.0.2`, `21-ea+3` thay vì âm thầm đổi nó sang một version khác. Việc tự `trim()`, bỏ số 0 hoặc viết lại dấu phân cách chỉ nên là **chính sách chuẩn hóa riêng có công bố** của hệ thống.

## 5. Xử lý ngoại lệ của Runtime.Version.parse

Các loại exception quan trọng theo Javadoc:

- `IllegalArgumentException`: chuỗi không diễn giải được như version string hợp lệ.
- `NullPointerException`: đối số truyền vào bằng `null`.
- `NumberFormatException`: một phần tử số của VNUM hoặc BUILD không chuyển thành `Integer` được. `NumberFormatException` **kế thừa `IllegalArgumentException`**.

~~~java
// Mã minh họa trong một phương thức, input được khai báo từ ngoài.
try {
    Runtime.Version version = Runtime.Version.parse(input);
    // Sử dụng version nếu parse thành công.
} catch (NumberFormatException overflow) {
    // Số quá lớn để chuyển thành Integer.
} catch (IllegalArgumentException invalid) {
    // Dữ liệu không phù hợp cú pháp phiên bản Java.
} catch (NullPointerException missing) {
    // Chuỗi truyền vào là null.
}
~~~

**Thứ tự catch quan trọng:** `NumberFormatException` phải đứng trước `IllegalArgumentException` nếu muốn xử lý riêng. Nếu chỉ cần báo “invalid version string”, có thể bắt `IllegalArgumentException` cho cả trường hợp sai ngữ pháp và tràn số.

### Hàm validate cú pháp bằng parser chuẩn

~~~java
static boolean isValidJavaVersionString(String text) {
    if (text == null) {
        return false;
    }

    try {
        Runtime.Version.parse(text);
        return true;
    } catch (IllegalArgumentException invalid) {
        return false;
    }
}
~~~

Helper trả `false` với null theo hợp đồng do ứng dụng định nghĩa; bản thân `Runtime.Version.parse(null)` sẽ ném `NullPointerException` nếu gọi trực tiếp.

### Tránh parse nhiều lần vô ích

Nếu cần lấy nhiều trường sau khi kiểm tra, giữ đối tượng đã parse:

~~~java
Runtime.Version parsed = Runtime.Version.parse(text);

int feature = parsed.feature();
int update = parsed.update();
String pre = parsed.pre().orElse("");
~~~

Đừng gọi `parse(text)` lặp lại cho mỗi accessor. Với nguồn input không tin cậy, ứng dụng còn có thể đặt giới hạn độ dài hợp lý (theo chính sách riêng) để tránh xử lý một chuỗi khổng lồ.

## 6. API đọc thành phần sau khi parse

### 6.1. FEATURE, INTERIM, UPDATE và PATCH

~~~java
Runtime.Version v = Runtime.Version.parse("21.0.2.1");

System.out.println(v.feature()); // 21
System.out.println(v.interim()); // 0
System.out.println(v.update()); // 2
System.out.println(v.patch()); // 1
~~~

Mỗi accessor trả một `int`. Với phần tử cuối bị lược (ví dụ PATCH của `21.0.2`), accessor trả `0`.

Những phương thức mang tên cũ `major()`, `minor()` và `security()` đã được đánh dấu **deprecated từ Java 10** vì không phản ánh đúng mô hình hiện tại. Code mới nên dùng bốn tên ở trên.

### 6.2. version() chỉ trả các phần tử đã hiện diện trong VNUM

~~~java
Runtime.Version v = Runtime.Version.parse("21.0.2");

System.out.println(v.version()); // [21, 0, 2]
System.out.println(v.version().size()); // 3
System.out.println(v.patch()); // 0
~~~

Danh sách `version()` là **unmodifiable** và không tự chèn giá trị 0 cho các vị trí vắng ở cuối. Không coi số phần tử của danh sách là luôn bằng bốn.

### 6.3. PRE, BUILD và OPT là Optional

~~~java
Runtime.Version v = Runtime.Version.parse("21-ea+3");

System.out.println(v.pre().orElse("none")); // ea
System.out.println(v.build().orElse(-1)); // 3
System.out.println(v.optional().orElse("none")); // none
~~~

Các phần `PRE`, `BUILD`, `OPT` có thể không xuất hiện. Hãy sử dụng `isPresent()` hoặc `orElse(...)` thay vì gọi `get()` một cách không kiểm soát trên Optional rỗng.

### 6.4. So với phiên bản đang chạy

~~~java
Runtime.Version running = Runtime.version();

System.out.println(running.feature());
System.out.println(running.update());
~~~

Đây là giá trị **phụ thuộc máy chạy**, nên không có một stdout số cụ thể chung cho mọi môi trường. Chương trình hoàn chỉnh phía dưới dùng chuỗi mẫu cố định để tránh phụ thuộc JDK thực đang cài.

## 7. So sánh Runtime.Version đúng cách

### Không so version như String

~~~java
String newer = "21.0.10";
String older = "21.0.9";

System.out.println(newer.compareTo(older) > 0); // false
System.out.println(
        Runtime.Version.parse(newer).compareTo(
                Runtime.Version.parse(older)) > 0
); // true
~~~

`String.compareTo` so ký tự theo thứ tự từ điển; nó không hiểu số nguyên `10` phải lớn hơn `9`. `Runtime.Version.compareTo` so thành phần theo ngữ nghĩa phiên bản JDK.

### PRE làm phiên bản trước GA có thứ tự thấp hơn

~~~java
var early = Runtime.Version.parse("21-ea+3");
var release = Runtime.Version.parse("21");

System.out.println(early.compareTo(release) < 0); // true
~~~

Cùng VNUM, phiên bản có `PRE` được xem là nhỏ hơn phiên bản không có `PRE`.

### Build và OPT là thành phần cần hiểu khi so

Theo Javadoc, `compareTo` xét dãy số phiên bản, PRE, BUILD và metadata OPT theo thứ tự ưu tiên. Đừng tự so `update()` riêng lẻ mà bỏ qua FEATURE, PRE hoặc PATCH.

Hai version sau khác nhau về `OPT`:

~~~java
var withOpt = Runtime.Version.parse("21.0.2+13-LTS");
var withoutOpt = Runtime.Version.parse("21.0.2+13");

System.out.println(withOpt.equals(withoutOpt)); // false
System.out.println(
        withOpt.equalsIgnoreOptional(withoutOpt)
); // true
System.out.println(
        withOpt.compareToIgnoreOptional(withoutOpt) == 0
); // true
~~~

`compareToIgnoreOptional` chỉ bỏ qua **optional build information**, không có nghĩa bỏ qua `PRE` hoặc BUILD. Khi dùng kết quả để sắp xếp, nên kết hợp với phương thức equality phù hợp (`equals` với `compareTo` hoặc `equalsIgnoreOptional` với `compareToIgnoreOptional`).

### Không suy từ compareTo sang tính tương thích

Một version số cao hơn có thể mang những thay đổi API/JVM khác. `compareTo` đưa ra **thứ tự version string**, không chứng minh ứng dụng sẽ chạy được hoặc một CVE đã được xử lý. Muốn ra quyết định triển khai, cần dùng yêu cầu FEATURE, release notes, test ứng dụng và thông tin nhà phân phối.

## 8. Sau parse còn cần validation nghiệp vụ

`Runtime.Version.parse("21-ea+3")` thành công vì cú pháp hợp lệ. Tuy nhiên một hệ thống có thể chỉ muốn chạy trên các bản JDK chính thức và không chấp nhận pre-release.

~~~java
// Mã minh họa: chính sách ứng dụng yêu cầu FEATURE >= 17
// và từ chối bất kỳ chuỗi nào có phần PRE.
static Runtime.Version requireAllowed(String text) {
    Runtime.Version v = Runtime.Version.parse(text);

    if (v.feature() < 17) {
        throw new IllegalArgumentException("feature too old");
    }
    if (v.pre().isPresent()) {
        throw new IllegalArgumentException("pre-release denied");
    }
    return v;
}
~~~

Hai điều kiện này là **quy tắc riêng của ứng dụng**. Không nên mô tả `21-ea+3` là “invalid version string” chỉ vì chính sách không cho dùng bản early access.

Tương tự:

- Parser không xác nhận một bản phát hành **có thật**.
- Parser không tự kiểm tra **CVE/security advisories**.
- Parser không kiểm tra **LTS support window**.
- Parser không kiểm tra **tính tương thích bytecode và thư viện** của chương trình.
- Parser không khẳng định phiên bản trong file cấu hình chính là runtime thực tế của máy.

Nếu cần xác nhận nhà phân phối hoặc bản vá, hãy kết hợp release notes/catal​og phù hợp và giá trị `Runtime.version()` của môi trường thật. Đừng gộp lỗi không kết nối được nguồn thông tin thành “version syntax invalid”.

### Version trong cấu hình khác version đang chạy

~~~java
Runtime.Version required = Runtime.Version.parse("17");
Runtime.Version running = Runtime.version();

if (running.feature() < required.feature()) {
    throw new IllegalStateException("Java feature is too old");
}
~~~

Đây là một cách **kiểm ở runtime** khi code có thể thực thi tới điều kiện. Nếu class đã biên dịch thành bytecode Java 17, JVM cũ có thể báo `UnsupportedClassVersionError` trước khi method được gọi. `javac --release 17` và `Runtime.version()` giải quyết hai câu hỏi khác nhau: **khả năng biên dịch nhắm API/bytecode** và **phiên bản JVM thực khi chạy**.

## 9. Chương trình Java 17+ hoàn chỉnh và stdout xác định

Chương trình dùng các chuỗi cố định nên không phụ thuộc JDK 17/21/phiên bản mới hơn đang cài. Nó kiểm các nhóm:

- Parse FEATURE/UPDATE/PATCH.
- PRE/BUILD/OPT.
- So sánh numeric và lexicographic.
- So sánh bỏ qua optional metadata.
- Kiểm chính sách cấm pre-release và FEATURE thấp.
- Từ chối input sai, null và số vượt `Integer.MAX_VALUE`.
- Danh sách `version()` là unmodifiable.

Lưu tệp đúng tên **`VersionStringValidationDemo.java`**:

~~~java
import java.util.List;

public class VersionStringValidationDemo {

    static String parts(Runtime.Version v) {
        return v.feature() + "|"
                + v.interim() + "|"
                + v.update() + "|"
                + v.patch();
    }

    static boolean isValid(String text) {
        if (text == null) {
            return false;
        }
        try {
            Runtime.Version.parse(text);
            return true;
        } catch (IllegalArgumentException invalid) {
            return false;
        }
    }

    static Runtime.Version requireAllowed(String text) {
        Runtime.Version v = Runtime.Version.parse(text);
        if (v.feature() < 17) {
            throw new IllegalArgumentException("feature too old");
        }
        if (v.pre().isPresent()) {
            throw new IllegalArgumentException("pre-release denied");
        }
        return v;
    }

    public static void main(String[] args) {
        var onlyFeature = Runtime.Version.parse("21");
        var updated = Runtime.Version.parse("21.0.2");
        var patched = Runtime.Version.parse("21.0.2.1");

        System.out.println("onlyFeature=" + parts(onlyFeature));
        System.out.println("updated=" + parts(updated));
        System.out.println("patched=" + parts(patched));
        System.out.println("numericParts=" + updated.version());

        var early = Runtime.Version.parse("21-ea+3");
        System.out.println("pre=" + early.pre().orElse("none"));
        System.out.println("preBuild=" + early.build().orElse(-1));

        var withOpt = Runtime.Version.parse("21.0.2+13-LTS");
        var withoutOpt = Runtime.Version.parse("21.0.2+13");

        System.out.println("build=" + withOpt.build().orElse(-1));
        System.out.println("optional="
                + withOpt.optional().orElse("none"));
        System.out.println("fullEqual=" + withOpt.equals(withoutOpt));
        System.out.println("ignoreOptionalEqual="
                + withOpt.equalsIgnoreOptional(withoutOpt));

        System.out.println("numericGreater="
                + (Runtime.Version.parse("21.0.10").compareTo(
                        Runtime.Version.parse("21.0.9")) > 0));
        System.out.println("lexicalGreater="
                + ("21.0.10".compareTo("21.0.9") > 0));
        System.out.println("earlyLessThanGA="
                + (early.compareTo(onlyFeature) < 0));

        System.out.println("validExample=" + isValid("21.0.2"));
        System.out.println("policyAccepted="
                + (requireAllowed("21.0.2").feature() == 21));

        try {
            requireAllowed("21-ea+3");
        } catch (IllegalArgumentException expected) {
            System.out.println("preDenied=true");
        }

        try {
            requireAllowed("11.0.2");
        } catch (IllegalArgumentException expected) {
            System.out.println("featureDenied=true");
        }

        var invalid = List.of(
                "0", "021", "21.0",
                "21.0.2.0", "21..2", "21+01"
        );
        int rejected = 0;
        for (String text : invalid) {
            if (!isValid(text)) {
                rejected++;
            }
        }
        System.out.println("invalidRejected=" + rejected);
        System.out.println("nullRejected=" + !isValid(null));

        boolean overflowRejected = false;
        try {
            Runtime.Version.parse("2147483648");
        } catch (NumberFormatException expected) {
            overflowRejected = true;
        }
        System.out.println("overflowRejected="
                + overflowRejected);

        boolean immutable = false;
        try {
            updated.version().add(100);
        } catch (UnsupportedOperationException expected) {
            immutable = true;
        }
        System.out.println("partsImmutable=" + immutable);
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 VersionStringValidationDemo.java
java VersionStringValidationDemo
~~~

**Stdout chính xác:**

~~~text
onlyFeature=21|0|0|0
updated=21|0|2|0
patched=21|0|2|1
numericParts=[21, 0, 2]
pre=ea
preBuild=3
build=13
optional=LTS
fullEqual=false
ignoreOptionalEqual=true
numericGreater=true
lexicalGreater=false
earlyLessThanGA=true
validExample=true
policyAccepted=true
preDenied=true
featureDenied=true
invalidRejected=6
nullRejected=true
overflowRejected=true
partsImmutable=true
~~~

### Giải thích từng nhóm kết quả

1. `parts` là hàm **định dạng để học**, in cả bốn accessor. `21|0|0|0` không phải chuỗi version canonical; đầu vào của parser là `21`.
2. `numericParts` chỉ chứa những thành phần số thực sự có trong VNUM `21.0.2`, không tự thêm phần tử PATCH=0.
3. `21-ea+3` có `PRE=ea`, `BUILD=3`. Số `3` không bị nhầm với UPDATE hoặc PATCH.
4. Hai Version có cùng VNUM và BUILD nhưng khác `OPT` cho `fullEqual=false` và `ignoreOptionalEqual=true`.
5. `numericGreater=true` còn `lexicalGreater=false` chứng minh việc so chuỗi là sai với phiên bản số có số lượng chữ số khác nhau.
6. Pre-release được so thấp hơn bản không có PRE cùng VNUM, nên `earlyLessThanGA=true`.
7. `validExample` và `policyAccepted` cùng true; ngược lại `preDenied` và `featureDenied` là những trường hợp **parse hợp lệ nhưng vi phạm chính sách**.
8. Sáu input không hợp lệ bị từ chối. Helper tự coi null là invalid, còn `Runtime.Version.parse(null)` trực tiếp sẽ ném `NullPointerException`.
9. Giá trị số `2147483648` vượt `Integer.MAX_VALUE`, dẫn tới `NumberFormatException` theo hợp đồng parse.
10. `version()` trả danh sách unmodifiable nên phép `add` ném `UnsupportedOperationException`.

Chương trình không dựa vào `Runtime.version()` thật để tạo output, không cần mạng hay thư viện ngoài và không khẳng định các chuỗi mẫu là bản JDK được phát hành thực tế.

## 10. Kiểm thử đầu vào: test matrix nên có

| Nhóm | Input | Mong đợi |
| --- | --- | --- |
| FEATURE đơn | `21` | Parse được, các phần tử sau mặc định 0 |
| UPDATE | `21.0.2` | Parse được, update=2 |
| PATCH | `21.0.2.1` | Parse được, patch=1 |
| PRE | `21-ea` | Parse được, pre=ea |
| PRE và BUILD | `21-ea+3` | Parse được, build=3 |
| BUILD và OPT | `21.0.2+13-LTS` | Parse được, build=13, opt=LTS |
| BUILD bằng 0 | `21+0` | Hợp lệ |
| VNUM nhiều vị trí | `21.0.2.1.5` | Hợp lệ về cú pháp |
| FEATURE=0 | `0` | IllegalArgumentException |
| Leading zero | `021`, `21.01` | IllegalArgumentException |
| Trailing zero | `21.0`, `21.0.2.0` | IllegalArgumentException |
| Dấu chấm liên tiếp | `21..2` | IllegalArgumentException |
| BUILD dẫn số 0 | `21+01` | IllegalArgumentException |
| Empty | `""` | IllegalArgumentException |
| Null | `null` | NullPointerException |
| Vượt miền số | `2147483648` | NumberFormatException |
| Pre-release bị chính sách cấm | `21-ea` | Parse thành công, validation nghiệp vụ từ chối |

**Kiểm thử exception:** nên kiểm **loại** ngoại lệ thay vì khẳng định message mặc định của JDK có nội dung nguyên văn không thay đổi qua mọi bản phát hành. Với API ứng dụng, có thể tạo lỗi domain riêng có message và mã lỗi ổn định cho caller.

### Chuỗi có whitespace

Parser không nhận `" 21"` hay `"21 "` theo ngữ pháp chuẩn. Nếu ứng dụng muốn chấp nhận người dùng vô tình nhập khoảng trắng, `trim()` trước parse là một quyết định chuẩn hóa **có chủ đích**, không phải hành vi của `Runtime.Version.parse`.

~~~java
// Chỉ áp dụng khi hợp đồng input cho phép xóa khoảng trắng đầu/cuối.
String clean = rawInput.trim();
Runtime.Version parsed = Runtime.Version.parse(clean);
~~~

Không nên tự động đổi `21.0.2.0` thành `21.0.2` mà không ghi nhận lỗi format, đặc biệt trong các quy trình xác nhận và triển khai.

## 11. Các sai lầm hay gặp

| Cách hiểu sai | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| `parse(String)` chỉ mới có từ Java 10 | Nó đã có từ Java 9; Java 10 bổ sung mô hình/tên accessor chính | Hiểu đúng mốc API và áp dụng quy tắc JEP 322 |
| `21.0.2.0` là dạng đủ bốn số bắt buộc | Không có trailing zero trong VNUM | Dùng `21.0.2` |
| `21.2` giống `21.0.2` | INTERIM và UPDATE khác vị trí | Giữ số 0 ở giữa |
| `+13` nghĩa UPDATE=13 | BUILD nằm ngoài số phiên bản | Đọc `build()` |
| `-ea` là PATCH | PRE là metadata pre-release | Đọc `pre()` |
| Parser xác thực bản JDK thực tế | Parser chỉ kiểm định dạng | Xác minh release/vendor khi cần |
| `LTS` bảo đảm hỗ trợ đến một ngày cụ thể | Metadata không có chính sách support | Kiểm thông tin nhà phân phối |
| `String.compareTo` đủ để sắp version | Nó so ký tự, không phải numeric components | Dùng `Runtime.Version.compareTo` |
| `version()` luôn có đúng bốn phần tử | Danh sách chỉ chứa phần hiện diện | Dùng accessor cho phần bị lược |
| Bắt `IllegalArgumentException` mà không cần xét null | NullPointerException là loại khác | Kiểm null/handle riêng |
| NumberFormatException không liên quan IllegalArgumentException | Nó là subclass | Bắt cụ thể trước nếu cần |
| Parse được là chắc chắn chạy được | Còn bytecode, API, thư viện, config | Thử khả năng tương thích thực tế |
| `Runtime.version()` đọc cấu hình do user nhập | Nó trả phiên bản runtime đang chạy | Dùng `parse(text)` cho chuỗi cấu hình |
| Java parser phù hợp mọi SemVer của thư viện | Quy tắc các hệ khác nhau | Chọn parser đúng chuẩn nguồn |
| Tự xây regex đơn giản để thay parser | Dễ sai PRE/BUILD/OPT và quy tắc số 0 | Dùng parser chuẩn của JDK |

## 12. Checklist cho code review

1. Xác định input là Java Platform version string theo JEP 322, không phải phiên bản thư viện tùy ý.
2. Dùng `Runtime.Version.parse(text)` khi đọc chuỗi, `Runtime.version()` khi kiểm JVM đang chạy.
3. Không có số 0 dư đầu thành phần, không có số 0 ở cuối VNUM và không xóa số 0 nằm giữa.
4. Kiểm và xử lý input null đúng hợp đồng của phương thức.
5. Xử lý `IllegalArgumentException` và `NumberFormatException` theo mức phân loại cần thiết.
6. Parse một lần, giữ đối tượng Version để đọc nhiều accessor.
7. Đọc đúng `feature()`, `interim()`, `update()`, `patch()` và `pre/build/optional`.
8. Tránh các accessor cũ đã deprecated; không dùng số `minor` theo mô hình trước Java 10.
9. Khi so sánh, dùng `compareTo` hoặc `compareToIgnoreOptional` theo chính sách, không so String.
10. Chỉ dùng version string để xác định **cú pháp/metadata**, không suy ra sự tồn tại của bản phát hành.
11. Kiểm chính sách nghiệp vụ sau parse: FEATURE tối thiểu, có/không PRE, vendor và mức hỗ trợ.
12. Với ngưỡng patch/security, tham khảo bản build, vendor và advisory thật trước khi quyết định.
13. Test đủ: valid VNUM, PRE/BUILD/OPT, trailing/leading zero, dấu chấm lỗi, null, overflow.
14. Nếu lưu kết quả parse vào cache hoặc báo cáo, giữ thông tin đầy đủ cần thiết, không chỉ lấy FEATURE.
15. Với input không tin cậy, đặt giới hạn kích thước thích hợp trước khi parse để tránh xử lý chuỗi quá lớn.

### Câu hỏi tự đánh giá

**Câu 1.** `Runtime.Version.parse("21.0.2")` cho bốn accessor chính bao nhiêu?

**Đáp án:** `feature=21`, `interim=0`, `update=2`, `patch=0`.

**Câu 2.** `Runtime.Version.parse("21.0.2.0")` có hợp lệ không?

**Đáp án:** Không, vì VNUM không cho phép số 0 ở cuối.

**Câu 3.** `21.2` có phải cách rút gọn của `21.0.2`?

**Đáp án:** Không; số thứ hai là INTERIM, số thứ ba là UPDATE.

**Câu 4.** `21-ea+3` có UPDATE=3 không?

**Đáp án:** Không. `PRE=ea` và `BUILD=3`, còn UPDATE vắng mặt nên bằng 0.

**Câu 5.** `Runtime.Version.parse(null)` ném gì?

**Đáp án:** `NullPointerException`.

**Câu 6.** Một số quá lớn so với `Integer.MAX_VALUE` gây gì?

**Đáp án:** `NumberFormatException` theo Javadoc.

**Câu 7.** Vì sao `"21.0.10".compareTo("21.0.9")` không được dùng?

**Đáp án:** Vì so chuỗi theo ký tự cho kết luận khác thứ tự số nguyên; dùng `Runtime.Version.compareTo`.

**Câu 8.** `Runtime.Version.parse("21-ea")` thành công có nghĩa mọi ứng dụng buộc phải chấp nhận bản EA?

**Đáp án:** Không; parser chỉ kiểm cú pháp. Ứng dụng có thể từ chối bằng chính sách `pre().isPresent()`.

**Câu 9.** `version().size()` của `Runtime.Version.parse("21")` là bao nhiêu?

**Đáp án:** `1`, dù các accessor sau FEATURE trả 0.

**Câu 10.** Khi nào dùng `compareToIgnoreOptional`?

**Đáp án:** Khi muốn so phiên bản và bỏ qua riêng phần `OPT` trong optional metadata, vẫn xét VNUM/PRE/BUILD.

**Câu 11.** Parse thành công chuỗi `21.0.2+13-LTS` có chứng minh bản này còn được vendor vá bảo mật?

**Đáp án:** Không. Cần kiểm chính sách hỗ trợ/release notes/advisory từ nhà phân phối cụ thể.

**Câu 12.** Làm sao lấy phiên bản JVM thực đang chạy?

**Đáp án:** Gọi `Runtime.version()`. `parse("21")` chỉ đọc chuỗi do ứng dụng cung cấp, không ảnh hưởng hoặc xác nhận môi trường thực.

## 13. Tài liệu chính thức vẫn áp dụng

- [Oracle Java SE 17 — Runtime.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): ngữ pháp số/string phiên bản, `parse`, ngoại lệ, các accessor, compare và `version()`.
- [Oracle Java SE 26 — Runtime.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): Javadoc hiện đại xác nhận những API kể trên vẫn được hỗ trợ.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình FEATURE/INTERIM/UPDATE/PATCH từ Java 10 và các dạng version string.
- [Oracle Java SE 17 — Runtime.version()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#version()): API lấy phiên bản JVM thực tại thời điểm chạy.
- [Oracle Java SE 17 — NumberFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NumberFormatException.html): trường hợp parse một thành phần số không phù hợp phạm vi số nguyên.
- [Oracle Java SE 17 — Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): lệnh `java --version` để chẩn đoán runtime thực tế.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release` để chọn mức ngôn ngữ/API và class-file khi biên dịch.

**Tổng kết:** `Runtime.Version.parse(String)` là parser chuẩn khi cần kiểm tra **cú pháp chuỗi phiên bản Java Platform** và chuyển nó thành một đối tượng có thể đọc/so sánh. Giữ nguyên ý nghĩa vị trí số, phân biệt VNUM với PRE/BUILD/OPT, xử lý input null và số sai định dạng rõ ràng. Sau khi parse, hãy xác định riêng **chính sách ứng dụng** và **tình trạng hỗ trợ/khả năng triển khai thực tế** thay vì coi mọi chuỗi hợp lệ là phiên bản nên sử dụng.