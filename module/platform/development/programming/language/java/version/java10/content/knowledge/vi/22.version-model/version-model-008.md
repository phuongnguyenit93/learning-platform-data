# Giới hạn của việc so sánh phiên bản bằng chuỗi trong Java 10

## 1. Vấn đề cốt lõi

Phiên bản của Java có thể được biểu diễn thành chuỗi như `"9"`, `"10"`, `"17.0.2"`, `"17.0.10"` hoặc `"21-ea"`. Nếu ứng dụng so sánh chúng bằng `String.compareTo`, kết quả có thể **ngược hoàn toàn với thứ tự phiên bản thực tế**.

Ví dụ:

~~~java
System.out.println("9".compareTo("10") > 0); // true
~~~

`String.compareTo` nói chuỗi `"9"` lớn hơn `"10"` vì ký tự đầu `'9'` lớn hơn `'1'`. Nhưng theo phiên bản Java, **9 cũ hơn 10**. Không có lỗi trong `String.compareTo`; lỗi nằm ở chỗ ứng dụng dùng **thứ tự từ điển** (*lexicographic*) để thay cho **thứ tự phiên bản**.

Với các phiên bản Java 10+ và hiện đại, mô hình trong **JEP 322 — Time-Based Release Versioning** sử dụng các thành phần số, nhãn pre-release, build number và thông tin build bổ sung. Java cung cấp lớp **`Runtime.Version`** để parse và so sánh theo hợp đồng này.

Bài học tập trung vào **giới hạn của việc so sánh phiên bản bằng chuỗi**, đặt trong ngữ cảnh **mô hình phiên bản Java 10**. Mọi API được khuyến nghị đều còn được sử dụng; những tên API deprecated chỉ được nêu để biết **tránh dùng**.

### Mục tiêu học tập

- Phân biệt thứ tự lexicographic với thứ tự **numeric components**.
- Phân tích lỗi với `9/10`, `17.0.10/17.0.2`, `+2/+10` và `-ea` so với bản chính thức.
- Hiểu những thành phần `FEATURE.INTERIM.UPDATE.PATCH` trong Java 10+.
- Sử dụng `Runtime.Version.parse`, `compareTo` và `compareToIgnoreOptional` đúng ngữ nghĩa.
- Đọc các accessor `feature()`, `interim()`, `update()`, `patch()`, `pre()`, `build()` và `optional()`.
- Hiểu một Java version string khác với SemVer của thư viện, nhãn Maven, bản phân phối vendor hoặc output CLI.
- Tách kiểm tra phiên bản JVM đang chạy khỏi việc bảo đảm tương thích API, bytecode, tính năng preview và cập nhật bảo mật.
- Viết kiểm thử Java 17+ mà stdout không phụ thuộc vào phiên bản JVM cụ thể trong một môi trường đã định.

## 2. `String.compareTo` làm gì và không làm gì?

`String.compareTo(String)` so sánh từng **đơn vị mã UTF-16** từ trái sang phải và trả một số âm/0/dương theo thứ tự ký tự; không có bước phân tích chuỗi thành các số nguyên.

~~~text
"9"    bắt đầu bằng '9'
"10"   bắt đầu bằng '1'

'9' > '1'  ->  "9".compareTo("10") > 0
 9  < 10   ->  Runtime.Version("9") < Runtime.Version("10")
~~~

Các ví dụ gây sai:

| Chuỗi A | Chuỗi B | `String.compareTo` | Thứ tự phiên bản Java đúng |
| --- | --- | --- | --- |
| `9` | `10` | A lớn hơn B | A nhỏ hơn B |
| `10.0.10` | `10.0.2` | A nhỏ hơn B | A lớn hơn B |
| `17.0.10` | `17.0.2` | A nhỏ hơn B | A lớn hơn B |
| `21+2` | `21+10` | A lớn hơn B | A nhỏ hơn B |
| `21-ea` | `21` | A lớn hơn B | A nhỏ hơn B |

Ví dụ với update:

~~~java
System.out.println("17.0.10".compareTo("17.0.2") < 0); // true
~~~

Khi gặp phần sau `17.0.`, phép so sánh ký tự thấy `'1' < '2'` nên kết luận `"17.0.10"` nhỏ hơn `"17.0.2"`. Nhưng **update 10** phải lớn hơn **update 2**.

### 2.1. Không sửa được bằng cách bỏ qua chữ hoa/chữ thường

`String.compareToIgnoreCase` vẫn là so sánh chuỗi; nó không biến `"10"` thành số 10. `equalsIgnoreCase` cũng chỉ kiểm tra sự bằng nhau của ký tự theo quy tắc case, không biết thứ tự phiên bản.

### 2.2. Không sửa được bằng cách xét độ dài chuỗi

Một chuỗi dài hơn có thể là bản mới hơn, nhưng **không phải quy tắc hợp lệ**: `21-ea` dài hơn `21` mà lại là pre-release cũ hơn bản chính thức. Số lượng dấu chấm, số ký tự và việc có suffix không đủ để định thứ tự.

### 2.3. Tại sao dùng `Collections.sort` mặc định cũng nguy hiểm?

Nếu bạn viết:

~~~java
var versions = new java.util.ArrayList<>(
        java.util.List.of("9", "10", "17.0.2", "17.0.10"));
java.util.Collections.sort(versions);
System.out.println(versions);
~~~

bạn đang yêu cầu **sort các String**, nên nó dùng thứ tự ký tự; không có phép màu nhận dạng version. Kết quả có thể xếp `10` trước `9` hoặc `17.0.10` trước `17.0.2`, trái với ý định.

Thay đổi đơn thuần từ `Collections.sort` sang `List.sort(String::compareTo)` không thay đổi bản chất comparator.

## 3. Mô hình phiên bản Java từ Java 10

Theo **JEP 322**, version number có các thành phần:

~~~text
FEATURE.INTERIM.UPDATE.PATCH
~~~

| Thành phần | Vai trò trong mô hình dựa trên thời gian | Phương thức |
| --- | --- | --- |
| `FEATURE` | Bộ đếm phát hành tính năng. | `feature()` |
| `INTERIM` | Bộ đếm phát hành trung gian. | `interim()` |
| `UPDATE` | Bộ đếm bản cập nhật, sửa lỗi và bảo mật theo nhánh. | `update()` |
| `PATCH` | Bộ đếm bản vá khẩn cấp nếu được phát hành. | `patch()` |

Ví dụ:

~~~text
21.0.2
│  │ └─ UPDATE = 2
│  └─── INTERIM = 0
└────── FEATURE = 21

PATCH bị lược bỏ -> patch() = 0
~~~

**Không nhầm** các thành phần này với bộ ba `major.minor.patch` của mọi thư viện SemVer. JEP 322 dùng mô hình phát hành theo thời gian, không tuyên bố rằng tăng `FEATURE` tương đương tăng SemVer major trong mọi tình huống tương thích.

### 3.1. Version number không có số 0 ở cuối

Theo đặc tả, dãy số của version number **không chứa phần tử 0 cuối chuỗi**:

~~~text
21          hợp lệ
21.0.2      hợp lệ
21.0.2.1    hợp lệ
21.0.0      không hợp lệ với Runtime.Version.parse
17.0        không hợp lệ với Runtime.Version.parse
~~~

Khi một thành phần không được ghi trong chuỗi, getter tương ứng trả 0:

~~~java
var version = Runtime.Version.parse("21.0.2");
System.out.println(version.interim()); // 0
System.out.println(version.patch());   // 0
~~~

`version.version()` trả danh sách số **đã xuất hiện**, ví dụ `[21, 0, 2]`, không tự thêm phần tử 0 cuối. Không nên parse một chuỗi kết thúc bằng `.0` rồi tin rằng Java sẽ tự chuẩn hóa; `Runtime.Version.parse` có quyền từ chối.

### 3.2. Các thành phần vượt quá bốn vị trí

Bốn thành phần đầu có tên và ý nghĩa chuẩn, nhưng phiên bản Java còn có thể chứa thêm thành phần do nhà triển khai dùng. `Runtime.Version.compareTo` so sánh **dãy số** chứ không phải chỉ bốn ô do bạn tự tách.

~~~text
10.0.2 < 10.0.2.1
~~~

Nếu hai dãy giống nhau ở các phần đã tồn tại mà một dãy có thêm thành phần số khác 0, dãy dài hơn lớn hơn theo quy tắc so sánh của API.

## 4. Cú pháp đầy đủ của Java version string

Ngoài version number (`VNUM`), chuỗi có thể mang **pre-release** (`PRE`), **build** (`BUILD`) và **optional build information** (`OPT`).

Các dạng chính được JavaDoc quy định:

~~~text
VNUM(-PRE)?+BUILD(-OPT)?
VNUM-PRE(-OPT)?
VNUM(+-OPT)?
~~~

Một số chuỗi hợp lệ:

~~~text
10
10-ea
10+2
10.0.2
10.0.2.1
17.0.10+7
21.0.2+13-LTS
21+-LTS
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `VNUM` | `21.0.2` | Dãy số phiên bản. |
| `PRE` | `ea` trong `21-ea` | Nhãn bản đang trước phát hành chính thức. |
| `BUILD` | `13` trong `21.0.2+13` | Số build, so sánh **theo số**. |
| `OPT` | `LTS` trong `21.0.2+13-LTS` | Thông tin nhận diện build thêm, tùy chọn. |

**Bẫy tách chuỗi:** dấu `-` có thể nằm trong phần `PRE` hoặc `OPT`; đừng cắt tại dấu gạch ngang đầu tiên rồi mặc định mọi thứ phía sau là pre-release.

### 4.1. Quy tắc ưu tiên khi so sánh

Theo `Runtime.Version.compareTo`, các thành phần được xét tuần tự:

1. Các **version numbers**, so sánh số nguyên theo từng vị trí.
2. **Pre-release**: khi version number bằng nhau, bản có `PRE` thấp hơn bản không có `PRE`.
3. **Build number**: khi các phần trước bằng nhau, build được so **theo số**.
4. **Optional build information**: được xét sau cùng nếu dùng `compareTo` đầy đủ.

`String.compareTo` không biết bất kỳ ưu tiên nào trong danh sách trên; nó chỉ xét ký tự từ trái sang phải.

### 4.2. Pre-release không đồng nghĩa “mới hơn vì chuỗi dài”

~~~java
var preview = Runtime.Version.parse("21-ea");
var ga = Runtime.Version.parse("21");

System.out.println(preview.compareTo(ga) < 0); // true
~~~

`String.compareTo` có thể đặt `"21-ea"` sau `"21"` bởi chuỗi dài hơn. Nhưng Java version model đặt pre-release **trước** release chính thức cùng version number.

Nhãn `-ea` ở đây chỉ là **thông tin pre-release**; không phải công tắc tự bật preview features. Việc cho phép sử dụng preview language features có cơ chế compile/runtime riêng.

### 4.3. Build number cũng cần số học

~~~java
var build2 = Runtime.Version.parse("21+2");
var build10 = Runtime.Version.parse("21+10");

System.out.println(build2.compareTo(build10) < 0); // true
~~~

Phép so sánh chuỗi thấy ký tự `'2'` lớn hơn `'1'`, còn `Runtime.Version` hiểu build 2 nhỏ hơn build 10.

### 4.4. Pre-release bằng số và bằng chữ

Theo JavaDoc, các pre-release identifiers hoàn toàn là số được so **theo số**; các nhãn không thuần số được so lexicographically. Nhãn số đứng trước nhãn không phải số theo quy tắc Java. Không áp dụng máy móc quy tắc của SemVer từ một thư viện khác lên Java version strings.

## 5. Dùng `Runtime.Version` đúng mục đích

`Runtime.Version` là lớp chuẩn trong `java.lang` biểu diễn version string của Java SE implementation, có từ Java 9; Java 10 bổ sung các getter `feature()`, `interim()`, `update()` và `patch()`.

~~~java
Runtime.Version a = Runtime.Version.parse("17.0.2");
Runtime.Version b = Runtime.Version.parse("17.0.10");

System.out.println(a.compareTo(b) < 0); // true
~~~

Với hai chuỗi hợp lệ, `compareTo` trả kết quả **đúng theo version ordering**, không phải theo lexicographic của String.

Một phương thức tiện ích:

~~~java
static boolean isAtLeast(String actual, String required) {
    Runtime.Version a = Runtime.Version.parse(actual);
    Runtime.Version b = Runtime.Version.parse(required);
    return a.compareTo(b) >= 0;
}
~~~

Hãy dùng phương thức này nếu các chuỗi đầu vào **thực sự tuân cú pháp JDK version**, và policy nghiệp vụ chấp nhận thứ tự bao gồm pre-release, build và optional build information.

### 5.1. `compareTo` chỉ cam kết dấu âm/0/dương

Không nên viết:

~~~java
// PHẢN MẪU:
boolean older = a.compareTo(b) == -1;
~~~

Java không cam kết mỗi comparator chỉ trả -1, 0, 1. Hãy viết:

~~~java
boolean older = a.compareTo(b) < 0;
boolean sameOrder = a.compareTo(b) == 0;
boolean newer = a.compareTo(b) > 0;
~~~

Điều này áp dụng cho `Comparable`/`Comparator` nói chung, không chỉ `Runtime.Version`.

### 5.2. `equals` và `==` không đồng nghĩa

`Runtime.Version` là **value-based class**. Hai instance mô tả cùng một phiên bản có thể là hai object riêng nhưng vẫn có cùng giá trị.

~~~java
var a = Runtime.Version.parse("21.0.2");
var b = Runtime.Version.parse("21.0.2");
System.out.println(a.equals(b)); // true
~~~

Không dùng `a == b` để quyết định version bằng nhau; không lấy đối tượng version làm khóa synchronization. `equals` hoặc `compareTo` được chọn theo hợp đồng dữ liệu.

### 5.3. Đọc thông tin phiên bản theo kiểu dữ liệu rõ ràng

~~~java
var release = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(release.feature());               // 21
System.out.println(release.interim());               // 0
System.out.println(release.update());                // 2
System.out.println(release.patch());                 // 0
System.out.println(release.version());               // [21, 0, 2]
System.out.println(release.pre().orElse("(none)"));   // (none)
System.out.println(release.build().orElse(-1));       // 13
System.out.println(release.optional().orElse("none"));// LTS
~~~

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `feature()` | `int` | Feature counter. |
| `interim()` | `int` | Interim counter; 0 nếu thiếu. |
| `update()` | `int` | Update counter; 0 nếu thiếu. |
| `patch()` | `int` | Patch counter; 0 nếu thiếu. |
| `version()` | `List<Integer>` | Dãy số version number, không thể sửa cấu trúc. |
| `pre()` | `Optional<String>` | Pre-release identifier nếu có. |
| `build()` | `Optional<Integer>` | Build number nếu có. |
| `optional()` | `Optional<String>` | Optional build information nếu có. |

Không gọi `pre().get()`, `build().get()` hay `optional().get()` khi chưa biết Optional có giá trị hay không. `Optional.empty()` là trạng thái hợp lệ của metadata này.

## 6. `compareToIgnoreOptional` và `equalsIgnoreOptional`

Giả sử hai bản build có cùng version number và build number nhưng optional metadata khác nhau:

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-Custom");

System.out.println(a.equals(b));               // false
System.out.println(a.equalsIgnoreOptional(b)); // true
~~~

Theo `Runtime.Version.compareTo` đầy đủ, `OPT` được so lexicographically sau các phần trước, nên hai chuỗi không coi là bằng nhau theo `equals`. Khi dùng `compareToIgnoreOptional`, Java **bỏ qua đúng optional build information**:

~~~java
System.out.println(a.compareToIgnoreOptional(b) == 0); // true
~~~

**Không nhầm tên phương thức:** `compareToIgnoreOptional` **không** có nghĩa “bỏ qua mọi phần sau version number”. Nó **vẫn xét**:

- Các số phiên bản.
- Nhãn pre-release.
- Build number.

Nó chỉ bỏ qua phần `OPT`. Một version `21-ea` và `21` **vẫn khác nhau** khi gọi `compareToIgnoreOptional` vì `ea` là pre-release.

### 6.1. Chọn comparator theo nghiệp vụ

Dùng `compareTo` khi muốn bảo toàn **toàn bộ thứ tự** gồm optional build metadata. Dùng `compareToIgnoreOptional` khi dữ liệu chỉ khác nhãn bổ sung và bạn **đã quyết định** những nhãn đó không ảnh hưởng kết quả so sánh.

Những trường hợp inventory, forensic, quản lý bản build và chẩn đoán theo vendor có thể cần lưu/so sánh **đầy đủ metadata**. Không tự bỏ `OPT` chỉ vì nó trông giống chuỗi trang trí.

### 6.2. Cẩn thận với `TreeSet` và `TreeMap`

Collection có thứ tự dùng comparator để xác định khi nào hai key được coi là trùng:

~~~java
var versions = new java.util.TreeSet<Runtime.Version>(
        Runtime.Version::compareToIgnoreOptional);

versions.add(Runtime.Version.parse("21.0.2+13-LTS"));
versions.add(Runtime.Version.parse("21.0.2+13-Custom"));

System.out.println(versions.size()); // 1
~~~

Vì comparator bỏ `OPT`, hai version trên được xem là **trùng theo comparator**, dù `equals` đầy đủ trả `false`. Nếu mục tiêu giữ chính xác mỗi bản build vendor khác nhau, đừng dùng comparator bỏ metadata cho khóa của một tập/map có thứ tự.

Hãy dùng **`equalsIgnoreOptional`** khi kiểm tra tương đương theo chính policy `compareToIgnoreOptional`; dùng `equals` khi policy yêu cầu version string đầy đủ.

## 7. Vì sao tự `split` chuỗi phiên bản rất dễ sai?

Một phản mẫu:

~~~java
// PHẢN MẪU: không giải quyết các hậu tố của JDK version string.
int feature = Integer.parseInt(versionText.split("\\.")[0]);
~~~

Nó có thể hoạt động với `21.0.2`, nhưng:

- `21-ea` không có dấu chấm; token đầu là `21-ea`, không parse được int.
- `21+13` có build suffix ngay sau số feature.
- `21.0.2+13-LTS` cần phân tích số, pre-release/build/optional theo ngữ pháp.
- `21.0.0` **không hợp lệ** theo JDK version grammar, dù nhiều parser tự chế vẫn nhận.
- Chỉ lấy feature không đủ khi cần so hai bản cập nhật `17.0.2` và `17.0.10`.
- Số thành phần có thể nhiều hơn bốn; logic chỉ đọc “ba số đầu” có thể làm mất thứ tự.

Đừng dùng một regex được viết vội để thay cho `Runtime.Version.parse` nếu chính phiên bản Java là dữ liệu cần xử lý.

### 7.1. Đầu vào không hợp lệ phải được báo rõ

`Runtime.Version.parse(String)` có thể ném:

| Ngoại lệ | Khi nào |
| --- | --- |
| `IllegalArgumentException` | Chuỗi không thể diễn giải thành Java version hợp lệ. |
| `NumberFormatException` | Thành phần số vượt phạm vi `Integer`; đây là subclass của `IllegalArgumentException`. |
| `NullPointerException` | Đối số `s` là `null`. |

Ví dụ những chuỗi không hợp lệ:

~~~text
17.0.0
21+01
1.8.0_321
abc
~~~

Các chuỗi đó chỉ dùng để **minh họa validation**, không phải hướng dẫn dùng cách đặt phiên bản cũ.

Một hàm báo lỗi có ngữ cảnh:

~~~java
static Runtime.Version parseRequired(String value) {
    java.util.Objects.requireNonNull(value, "value");
    try {
        return Runtime.Version.parse(value);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid Java runtime version: " + value, ex);
    }
}
~~~

Không bắt mọi lỗi rồi trả “version 0” hoặc phiên bản “mới nhất” một cách âm thầm; fallback không có contract có thể làm sai chính sách deployment.

### 7.2. Parser chuẩn không phải bộ xử lý mọi loại version

`Runtime.Version.parse` không nhận một cách tùy ý:

- Toàn bộ nhiều dòng output của `java --version`.
- Bất kỳ chuỗi có chữ `v` đứng trước, nếu hệ thống khác tự định dạng như vậy.
- Nhãn theo phiên bản Maven, npm, Docker image, package hoặc release nội bộ.
- Các tiền tố tên sản phẩm, commit, ngày build hoặc thông tin marketing.
- Một SemVer có tập nhãn pre-release/build khác ngữ pháp Java.

Đầu vào theo định dạng nào thì phải được parse theo **chính định dạng đó**. Không cố “đoán” bằng cách xóa ngẫu nhiên các dấu `-`, dấu `+` hoặc ký tự chữ khỏi chuỗi.

## 8. Lấy phiên bản JVM đang chạy bằng `Runtime.version()`

Nếu mục tiêu là hỏi phiên bản **Java runtime của chính tiến trình hiện tại**, Java có API có cấu trúc:

~~~java
Runtime.Version running = Runtime.version();
int feature = running.feature();
~~~

Không cần đọc `System.getProperty("java.version")` rồi so sánh bằng ký tự; cũng không cần parse toàn bộ stdout của `java -version`.

Một yêu cầu đơn giản:

~~~java
boolean atLeast17 = Runtime.version().feature() >= 17;
~~~

Đây là **kiểm tra feature counter**, phù hợp nếu nghiệp vụ chỉ hỏi feature release tối thiểu. Nếu cần so update, patch, pre-release hay build, dùng dữ liệu có cấu trúc và policy thích hợp.

### 8.1. Runtime hiện tại không phải phiên bản của mọi tool liên quan

`Runtime.version()` cho biết **JVM đang thực thi code này**, không bảo đảm:

- `javac` đang được cấu hình cùng JDK.
- IDE hoặc build tool dùng cùng JVM với ứng dụng production.
- Target bytecode của ứng dụng đã được đặt đúng phiên bản.
- Mọi thư viện đang dùng hỗ trợ runtime đó.
- Các API nằm trong module không được đóng gói vào custom runtime image đã có sẵn.
- Preview features được bật bằng cờ thích hợp.

Khi cần xác định **runtime support matrix**, quản lý cả compile target, class file version, dependency compatibility và kiểm thử thực tế trên các JVM được hỗ trợ.

### 8.2. Không parse toàn bộ output `java --version`

Lệnh CLI thường hiển thị tên implementation, release date, build và thông tin VM trên nhiều dòng. Toàn bộ output **không phải một Java version string** theo ngữ pháp của `Runtime.Version.parse`.

Trong code Java, dùng `Runtime.version()`. Trong CI/script, dùng nguồn dữ liệu có cấu trúc hoặc trích trường phiên bản đúng contract; không so sánh nguyên khối stdout bằng `String.compareTo`.

## 9. Java version ordering không đủ để quyết định tính tương thích

Một phiên bản có feature counter cao hơn không tự cam kết **mọi ứng dụng cũ** chạy đúng với bất kỳ cấu hình nào.

| Câu hỏi | Dữ liệu/cơ chế thích hợp |
| --- | --- |
| JVM hiện tại là feature release nào? | `Runtime.version().feature()`. |
| Hai phiên bản Java theo JEP 322 xếp trước/sau ra sao? | `Runtime.Version.compareTo`. |
| Hai build chỉ khác `OPT` có thể coi tương đương theo một policy không? | `compareToIgnoreOptional` và `equalsIgnoreOptional`. |
| Ứng dụng biên dịch cho Java 17 chạy trên 17 không? | Cấu hình `javac --release` và thử nghiệm tích hợp. |
| Module/API cụ thể có được cung cấp không? | Kiểm tra module, API availability và runtime configuration. |
| Một tính năng preview có sẵn không? | Phiên bản + cấu hình compile/run preview tương ứng. |
| JDK đã có bản vá bảo mật cụ thể chưa? | Advisory của vendor, bản update/backport và cấu hình liên quan. |
| Artifact thư viện có phiên bản nào mới hơn? | Semantics phiên bản của hệ sinh thái thư viện đó. |

### 9.1. Vì sao feature version không phải chứng nhận bảo mật?

Một bản cập nhật cho nhánh Java cũ có thể được nhà cung cấp backport bản vá. Một nhánh Java mới có thể có policy hỗ trợ khác hoặc còn thiếu bản cập nhật theo kênh phân phối.

Do đó, `Runtime.Version.compareTo` có thể giúp **định thứ tự theo mô hình JDK**, nhưng không phải “bằng chứng duy nhất” để kết luận một JVM đã xử lý **CVE cụ thể**, được hỗ trợ LTS hay đáp ứng tiêu chuẩn tuân thủ của tổ chức.

### 9.2. Version number không phải điều kiện đủ cho source/binary compatibility

Không chỉ xét số feature khi bật/tắt chức năng. Ví dụ code dùng một API mới có thể cần target compiler phù hợp; class file được compile cho version cao hơn có thể **không load được trên JVM thấp hơn**, trước khi chương trình kịp chạy kiểm tra `Runtime.version()`.

Nếu hỗ trợ nhiều JVM, hãy tổ chức packaging và test cho các môi trường đó, thay vì chỉ thêm một `if (feature >= 17)` trong một class đã biên dịch bằng class-file format không tương thích.

## 10. `Runtime.Version` không thay comparator của hệ sinh thái khác

Có nhiều hệ thống versioning:

| Nguồn phiên bản | Ví dụ | Có nên áp dụng `Runtime.Version`? |
| --- | --- | --- |
| Java/JDK theo JEP 322 | `21.0.2+13-LTS` | **Có**, nếu đúng cú pháp. |
| Thư viện theo SemVer | `1.2.3-alpha.1+meta` | **Không mặc định**; ngữ pháp và precedence khác. |
| Maven artifact version | `2.0.0-RC1` | Cần comparator theo Maven/artifact policy. |
| Docker image tag | `release-2024-01` | Tag có thể là định danh tùy ý. |
| Android API level | Số API level | Kiểm tra theo API-level semantics. |
| Release nội bộ | `build_2024_11` | Dùng hợp đồng riêng của hệ thống đó. |

Nếu cần so sánh phiên bản dependency, hãy xem bộ công cụ quản lý dependency hoặc thư viện comparator đúng semantic. **Một String có các chữ số và dấu chấm không nhất thiết là Java version string.**

### 10.1. Zero-padding không phải giải pháp tổng quát

Có thể nghĩ tới biến `9` thành `09`, `10` giữ nguyên `10` rồi so String. Cách này chỉ hoạt động dưới những ràng buộc rất hẹp về độ rộng từng thành phần, số lượng thành phần và việc không có suffix. Nó không giải quyết pre-release, build, optional metadata hoặc cú pháp không hợp lệ.

Khi đã đủ khả năng chuẩn hóa thành phần chính xác, biểu diễn bằng **kiểu phiên bản có cấu trúc** vẫn rõ ràng hơn.

### 10.2. Comparator tự viết bằng phép trừ có thể tràn

~~~java
// PHẢN MẪU nếu hai số có thể rất lớn:
int result = leftFeature - rightFeature;
~~~

Dùng `Integer.compare(leftFeature, rightFeature)` nếu thật sự cần so số nguyên. Với Java version strings, dùng comparator chuẩn `Runtime.Version.compareTo` để không phải tự tái triển khai logic pre/build/optional.

## 11. Chương trình Java 17+ hoàn chỉnh đã kiểm chứng

Chương trình dùng cùng hai chuỗi ở mỗi cặp để so **lexicographic** và **version-aware**; đọc thành phần, kiểm tra optional metadata và bắt parser errors. Các phần đầu ra không phụ thuộc build cụ thể của JVM ngoại trừ hai phép kiểm tra đã ghi rõ yêu cầu Java 17+.

Tạo file **`JavaVersionComparisonDemo.java`**:

~~~java
import java.util.List;

public class JavaVersionComparisonDemo {
    static Runtime.Version v(String text) {
        return Runtime.Version.parse(text);
    }

    static String symbol(int comparison) {
        return comparison < 0 ? "<" : comparison > 0 ? ">" : "=";
    }

    static void compare(String left, String right) {
        System.out.println(left + " ? " + right + " : text=" +
                symbol(left.compareTo(right)) + ", version=" +
                symbol(v(left).compareTo(v(right))));
    }

    public static void main(String[] args) {
        compare("9", "10");
        compare("10.0.10", "10.0.2");
        compare("17.0.10", "17.0.2");
        compare("21+2", "21+10");
        compare("21-ea", "21");
        compare("10.0.2", "10.0.2.1");

        Runtime.Version release = v("21.0.2+13-LTS");
        System.out.println("feature=" + release.feature());
        System.out.println("interim=" + release.interim());
        System.out.println("update=" + release.update());
        System.out.println("patch=" + release.patch());
        System.out.println("numbers=" + release.version());
        System.out.println("pre=" + release.pre().orElse("(none)"));
        System.out.println("build=" + release.build().orElse(-1));
        System.out.println("optional=" + release.optional().orElse("(none)"));

        Runtime.Version vendorA = v("21.0.2+13-LTS");
        Runtime.Version vendorB = v("21.0.2+13-Custom");
        System.out.println("vendor full-equal=" + vendorA.equals(vendorB));
        System.out.println("vendor ignore-optional-equal=" +
                vendorA.equalsIgnoreOptional(vendorB));
        System.out.println("vendor compareTo=" +
                symbol(vendorA.compareTo(vendorB)));
        System.out.println("vendor compare-ignore-optional=" +
                symbol(vendorA.compareToIgnoreOptional(vendorB)));

        for (String input : List.of(
                "17.0.0", "1.8.0_321", "21+01", "abc")) {
            try {
                v(input);
                System.out.println("parsed unexpected: " + input);
            } catch (IllegalArgumentException ex) {
                System.out.println("invalid=" + input);
            }
        }

        System.out.println("running-feature-positive=" +
                (Runtime.version().feature() > 0));
        System.out.println("at-least-17=" +
                (Runtime.version().compareTo(v("17")) >= 0));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac -encoding UTF-8 JavaVersionComparisonDemo.java
java JavaVersionComparisonDemo
~~~

**Stdout đã kiểm chứng bằng JDK 24:**

~~~text
9 ? 10 : text=>, version=<
10.0.10 ? 10.0.2 : text=<, version=>
17.0.10 ? 17.0.2 : text=<, version=>
21+2 ? 21+10 : text=>, version=<
21-ea ? 21 : text=>, version=<
10.0.2 ? 10.0.2.1 : text=<, version=<
feature=21
interim=0
update=2
patch=0
numbers=[21, 0, 2]
pre=(none)
build=13
optional=LTS
vendor full-equal=false
vendor ignore-optional-equal=true
vendor compareTo=>
vendor compare-ignore-optional==
invalid=17.0.0
invalid=1.8.0_321
invalid=21+01
invalid=abc
running-feature-positive=true
at-least-17=true
~~~

### 11.1. Ý nghĩa một số dòng quan trọng

- `9 ? 10 : text=>, version=<`: String so sai thứ tự phiên bản vì so ký tự.
- `17.0.10 ? 17.0.2 : text=<, version=>`: update 10 lớn hơn update 2.
- `21+2 ? 21+10 : text=>, version=<`: build number được so theo số.
- `21-ea ? 21 : text=>, version=<`: pre-release thấp hơn bản chính thức.
- `numbers=[21, 0, 2]`: các phần của version number thực sự xuất hiện trong chuỗi.
- `vendor full-equal=false`, `vendor ignore-optional-equal=true`: cùng version/build nhưng khác optional metadata.
- `vendor compareTo=>`, `vendor compare-ignore-optional==`: minh họa hai comparator có **chính sách khác nhau**.
- `invalid=...`: parser từ chối các chuỗi không tuân cú pháp Java version.
- `at-least-17=true`: đúng trên JDK 24 kiểm thử và bất kỳ JVM Java 17+ hỗ trợ code này; **không suy rộng** sang mọi môi trường JVM.

Hàm `symbol` chuyển kết quả comparator sang `<`, `=`, `>` để không giả định `compareTo` luôn trả chính xác -1 hoặc +1.

## 12. Áp dụng vào code thực tế

### 12.1. Kiểm tra yêu cầu feature tối thiểu

~~~java
static void requireFeatureAtLeast(int requiredFeature) {
    int current = Runtime.version().feature();
    if (current < requiredFeature) {
        throw new IllegalStateException(
                "Requires Java feature " + requiredFeature
                        + ", current feature " + current);
    }
}
~~~

Đây là phép kiểm tra **số feature**, không phải điều kiện đủ cho compatibility khi build class đã không chạy trên JVM cũ. Muốn phát hành thư viện đa Java, cần cấu hình build và kiểm thử theo support matrix.

### 12.2. Kiểm tra tối thiểu một update có cấu trúc

~~~java
var minimum = Runtime.Version.parse("17.0.10");
boolean meetsVersionOrder =
        Runtime.version().compareTo(minimum) >= 0;
~~~

Nếu chính sách chỉ chấp nhận **nhánh 17**, cần kiểm tra thêm `Runtime.version().feature() == 17`. Ngược lại, những nhánh cao hơn cũng có thể vượt ngưỡng theo comparator JDK.

Với một lỗ hổng cụ thể, comparator không đủ để khẳng định đã được vá; phải xem bulletin/patch matrix theo vendor.

### 12.3. Sort danh sách Java version strings

~~~java
var versions = new java.util.ArrayList<>(
        java.util.List.of("17.0.10", "17.0.2", "21", "9", "10")
);

versions.sort(
        java.util.Comparator.comparing(Runtime.Version::parse)
);

System.out.println(versions);
// [9, 10, 17.0.2, 17.0.10, 21]
~~~

Ví dụ chỉ hợp lệ khi các chuỗi đầu vào là **Java version strings đúng cú pháp**. Với danh sách lớn, có thể parse và cache các `Runtime.Version` thay vì parse lặp lại trong comparator.

### 12.4. Chính sách dữ liệu nên tách rạch ròi

~~~text
JDK runtime version       -> Runtime.Version
Feature-only gate         -> Runtime.version().feature()
Dependency SemVer         -> parser/comparator của ecosystem
Build artifact identifier -> metadata riêng
Security patch decision   -> vendor advisory + bản build cụ thể
~~~

Không tạo một phương thức tên `compareAnyVersion` rồi dùng cùng logic cho mọi loại dữ liệu kể trên.

## 13. Chiến lược kiểm thử

Những cặp nên có trong unit tests:

| A | B | `Runtime.Version.compareTo` |
| --- | --- | --- |
| `9` | `10` | `A < B` |
| `10.0.10` | `10.0.2` | `A > B` |
| `17.0.10` | `17.0.2` | `A > B` |
| `21+2` | `21+10` | `A < B` |
| `21-ea` | `21` | `A < B` |
| `10.0.2` | `10.0.2.1` | `A < B` |

Ngoài ra hãy kiểm tra:

- Parser từ chối `17.0.0`, `21+01` và chuỗi không phải Java version.
- `feature()`/`interim()`/`update()`/`patch()` trả đúng giá trị khi một thành phần vắng mặt.
- `pre()`/`build()`/`optional()` có hoặc không có giá trị đúng trường hợp.
- `compareToIgnoreOptional` không bỏ `PRE` hay `BUILD`.
- `equalsIgnoreOptional` và `equals` được dùng đúng chính sách.
- `TreeSet` có comparator bỏ optional chỉ giữ một trong các value bị coi là trùng.
- Thử với dữ liệu JVM thật mà không phụ thuộc vào chuỗi version cố định của máy CI.

### 13.1. Quy tắc của một comparator đúng

Đối với custom comparator, cần tính nhất quán và truyền bắc cầu:

- Nếu `a < b` và `b < c` thì `a < c`.
- Kết quả so `a` với `b` có dấu ngược với so `b` với `a`.
- Cùng hai giá trị không đổi nên cho kết quả ổn định.
- `compare(a,b)==0` phải có ý nghĩa trùng hợp với chính sách dữ liệu.

`Runtime.Version` đã triển khai những quy tắc theo đặc tả version Java. Tự split và so từng trường mà quên pre/build/optional có thể gây lỗi khó kiểm chứng.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Dùng `String.compareTo` cho version Java. | Đảo thứ tự các thành phần có nhiều chữ số. | `Runtime.Version.parse` + `compareTo`. |
| Dùng `compareToIgnoreCase`. | Chỉ thay case, không thay logic version. | Chọn comparator đúng đặc tả. |
| Cho rằng `21-ea` lớn hơn `21`. | Pre-release bị coi là mới hơn GA. | Dùng quy tắc `PRE` của JDK. |
| Coi build `+2` lớn hơn `+10`. | So ký tự, không so số. | Để `Runtime.Version` so build. |
| Cố ép mọi phần về ba số bằng `split`. | Mất pre-release, build, metadata và thành phần bổ sung. | Parser/typed getters. |
| Cho `17.0.0` là chuỗi JDK version hợp lệ. | `Runtime.Version.parse` từ chối. | Dùng biểu diễn canonical phù hợp. |
| Dùng các getter deprecated `major`/`minor`/`security`. | Tên cũ không phản ánh mô hình Java 10. | `feature`/`interim`/`update`. |
| Hiểu `compareToIgnoreOptional` là bỏ mọi suffix. | Có thể bỏ nhầm pre-release/build. | Nó chỉ bỏ `OPT`. |
| So `compareTo(...) == -1`. | Không đúng hợp đồng Comparator. | Kiểm tra dấu `<0`. |
| So `Runtime.Version` bằng `==`. | So tham chiếu của value-based class. | `equals` hoặc comparator. |
| Dùng `Runtime.Version` cho SemVer thư viện. | Version grammar khác nhau. | Comparator theo ecosystem. |
| Dùng version feature để kết luận đã vá bảo mật. | Vendor/backport/patch data có thể khác. | Advisory và metadata bản build. |
| Tin runtime feature đủ là mọi API/bytecode chạy. | Còn module/flags/dependencies/compile target. | Kiểm thử tương thích thực tế. |
| Dùng phép trừ hai số trong comparator tùy biến. | Có thể tràn số nguyên. | `Integer.compare`. |

## 15. Bài tập có đáp án

**Câu 1.** Vì sao `"9".compareTo("10") > 0` nhưng Java 9 cũ hơn Java 10?

**Đáp án:** String so ký tự `'9'` và `'1'`, không so số nguyên 9 và 10. Sử dụng `Runtime.Version.parse("9").compareTo(Runtime.Version.parse("10")) < 0`.

**Câu 2.** So đúng `17.0.2` và `17.0.10`.

**Đáp án:** `17.0.2 < 17.0.10` vì update 2 nhỏ hơn update 10; `String.compareTo` có thể xếp ngược.

**Câu 3.** `21-ea` và `21`: bản nào đứng trước?

**Đáp án:** `21-ea` thấp hơn bản không có nhãn pre-release là `21`.

**Câu 4.** Build `21+2` có mới hơn `21+10` không?

**Đáp án:** Không. Build 2 < build 10; không được dùng chữ số đầu của thành phần build để so.

**Câu 5.** Với `Runtime.Version.parse("21.0.2+13-LTS")`, các getter cho kết quả gì?

**Đáp án:** `feature=21`, `interim=0`, `update=2`, `patch=0`, `version=[21,0,2]`, `build=13`, `optional="LTS"`, `pre` vắng mặt.

**Câu 6.** `Runtime.Version.parse("17.0.0")` có hợp lệ không?

**Đáp án:** Không. Version number không có trailing zero components. Dùng `"17"` nếu muốn biểu diễn phiên bản với những thành phần sau bằng 0.

**Câu 7.** `compareToIgnoreOptional` có bỏ nhãn `-ea` không?

**Đáp án:** Không, vì `-ea` là `PRE`. Nó chỉ bỏ thông tin `OPT`; vẫn xét các phần số, pre-release và build number.

**Câu 8.** Vì sao TreeSet dùng comparator bỏ optional có thể làm mất một bản vendor?

**Đáp án:** Comparator có thể trả 0 cho hai version chỉ khác `OPT`, và TreeSet xem chúng là một giá trị theo comparator. Nếu cần giữ đủ bản build vendor, chọn policy khác.

**Câu 9.** Muốn kiểm tra feature JVM đang chạy từ Java 17 trở lên, dùng gì?

**Đáp án:** `Runtime.version().feature() >= 17`. Vẫn cần kiểm tra class file/preview/modules/dependencies riêng.

**Câu 10.** Dùng `Runtime.Version.parse` để so Maven release `1.2.3-RC1` với `1.2.3` được không?

**Đáp án:** Không nên mặc định. Dùng parser/comparator theo semantics của Maven hoặc thư viện cụ thể.

**Câu 11.** Nếu build `A` có feature nhỏ hơn build `B`, có thể kết luận `B` đã vá một CVE không?

**Đáp án:** Không. Cần bulletin bảo mật và bản cập nhật cụ thể của vendor; feature counter không phải chứng chỉ an toàn.

**Câu 12.** `compareTo` trả `-3` có vi phạm hợp đồng không?

**Đáp án:** Không. Hợp đồng chỉ yêu cầu số âm/0/dương. Viết `a.compareTo(b) < 0` thay vì `== -1`.

## 16. Checklist áp dụng

- [ ] Tôi chắc chắn dữ liệu đầu vào là **version string Java/JDK**, không phải một SemVer hoặc tag khác.
- [ ] Tôi dùng `Runtime.Version.parse` khi cần so sánh JDK version strings.
- [ ] Tôi không dùng `String.compareTo` hoặc `compareToIgnoreCase` để chọn phiên bản Java mới hơn.
- [ ] Tôi hiểu các thành phần `FEATURE.INTERIM.UPDATE.PATCH` và ý nghĩa mới từ Java 10.
- [ ] Tôi không dùng getter phiên bản deprecated trong code mới.
- [ ] Tôi xử lý pre-release/build/optional theo chính sách có chủ đích.
- [ ] Tôi không nhầm `compareToIgnoreOptional` với việc bỏ toàn bộ suffix.
- [ ] Tôi không coi `21.0.0` là định dạng JDK chuẩn để parse.
- [ ] Tôi bắt/báo lỗi input không hợp lệ, không âm thầm thay bằng version ngẫu nhiên.
- [ ] Tôi dùng `Runtime.version()` nếu chỉ cần biết JVM của tiến trình đang chạy.
- [ ] Nếu chỉ xét feature, tôi không suy ra tương thích bytecode hay preview/module support.
- [ ] Tôi không dùng version ordering làm bằng chứng duy nhất về security/LTS.
- [ ] Tôi không dùng `Runtime.Version` cho dependency có version grammar khác.
- [ ] Tôi kiểm tra kết quả comparator bằng dấu, không so chính xác ±1.
- [ ] Tôi tránh reference equality và synchronization trên đối tượng `Runtime.Version`.
- [ ] Tôi kiểm thử đủ các cặp numeric update, build, pre-release và optional metadata.
- [ ] Tôi nêu rõ chính sách tương đương trong `TreeSet`/`TreeMap` nếu dùng comparator bỏ optional.

## 17. Tài liệu chính thức còn hiệu lực

1. [Oracle Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): version grammar, `parse`, `compareTo`, `compareToIgnoreOptional`, các thành phần số, pre/build/optional và tính value-based.
2. [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): định nghĩa `FEATURE.INTERIM.UPDATE.PATCH` áp dụng từ Java 10 và động cơ của mô hình thời gian.
3. [Oracle Java SE 26 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#version()): lấy phiên bản Java runtime đang chạy.
4. [Oracle Java SE 26 — `String.compareTo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#compareTo(java.lang.String)): thứ tự lexicographic của String.
5. [Oracle Java SE 26 — `Comparable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Comparable.html): ý nghĩa giá trị âm/0/dương và thứ tự tự nhiên.
6. [Oracle Java SE 26 — `Comparator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): comparator theo key và các quy tắc về thứ tự.
7. [Oracle Java SE 26 — `TreeSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html): tác động của comparator tới tính trùng lặp trong sorted set.
8. [Oracle Java SE 26 — `Optional`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html): cách đọc thành phần pre/build/optional khi có thể vắng mặt.
9. [OpenJDK JEP 223 — New Version-String Scheme](https://openjdk.org/jeps/223): nền tảng của version grammar được JEP 322 tinh chỉnh.

**Kết luận:** `String.compareTo` dùng thứ tự ký tự, **không hiểu số phiên bản**. Nó có thể xếp sai `"9"`/`"10"`, update `"17.0.10"`/`"17.0.2"`, build `"+2"`/`"+10"` hoặc phiên bản preview `"21-ea"`. Với Java version strings theo mô hình Java 10+, dùng **`Runtime.Version.parse` cùng `compareTo`**; nếu chỉ hỏi feature của JVM đang chạy, dùng **`Runtime.version().feature()`**. Những phiên bản của thư viện/hệ sinh thái khác phải được so bằng **quy tắc riêng**, và thứ tự số phiên bản không thay thế đánh giá tương thích hay bản vá bảo mật.