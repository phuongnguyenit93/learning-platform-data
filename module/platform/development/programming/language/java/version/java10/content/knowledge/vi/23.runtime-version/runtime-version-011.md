# Thay cách tách chuỗi thủ công bằng hợp đồng `Runtime.Version` (Java 10+)

## 1. Bài toán: vì sao `split(".")` hoặc lấy số đầu chuỗi dễ sai?

Khi viết chương trình cần kiểm tra phiên bản Java đang chạy, nhiều người xử lý trực tiếp chuỗi:

```java
String version = System.getProperty("java.version");
// Không nên dựa vào giả định rằng format luôn là "major.minor.patch".
String first = version.split("\\.")[0];
int number = Integer.parseInt(first);
```

Đây là đoạn mã minh họa trong một phương thức. Nó **không phải cách khuyến nghị** để nhận phiên bản Java hiện đại. Với các chuỗi như:

```text
17
17.0.10
17.0.10+7-LTS
21-ea+5
```

thao tác tách chuỗi phải tự xử lý dấu `.`, `-`, `+`, nhãn pre-release, build number và phần tùy chọn của nhà phát hành. Nó cũng rất dễ nhầm **so sánh văn bản** với **so sánh phiên bản**: về mặt chữ, `"17.0.10"` nhỏ hơn `"17.0.9"` khi so từ trái sang phải, trong khi về phiên bản số, **bản update 10 lớn hơn bản update 9**.

Java đã cung cấp đối tượng chính thức để giải quyết bài toán này:

- `Runtime.version()`: lấy thông tin phiên bản **JVM đang thực sự chạy chương trình**.
- `Runtime.Version.parse(String)`: phân tích **một chuỗi phiên bản hợp lệ theo quy ước Java SE** thành object có cấu trúc.
- Các accessor `feature()`, `interim()`, `update()`, `patch()`, `pre()`, `build()`, `optional()`.
- `compareTo` và `compareToIgnoreOptional` để so sánh theo thứ tự phiên bản, thay vì so sánh chuỗi theo thứ tự chữ cái.

`Runtime.Version` là một lớp có từ Java 9; những accessor `feature()`, `interim()`, `update()`, `patch()` được bổ sung trong **Java 10** để phản ánh mô hình phát hành theo thời gian. Các API này **vẫn đang áp dụng trong Java hiện đại**.

**Thông điệp chính:** nếu cần **số phiên bản feature** của Java đang chạy, dùng `Runtime.version().feature()`; nếu cần đọc **một Java version string theo cú pháp chuẩn**, dùng `Runtime.Version.parse(...)`. Không tự cắt chuỗi chỉ để tạo lại những thành phần mà API đã có.

## 2. Phân biệt hai nguồn: runtime thật và chuỗi phiên bản cần phân tích

### 2.1. Đang chạy trên JVM phiên bản nào?

```java
Runtime.Version actual = Runtime.version();
int javaFeature = actual.feature();

System.out.println("Feature version: " + javaFeature);
```

Đây là đoạn trong một phương thức. `Runtime.version()` trả về thông tin phiên bản của **Java Runtime Environment đang thực thi mã**. Trên một máy chạy JDK 17, `feature()` thường là `17`; trên một máy chạy JDK 21, nó là `21`.

**Không hardcode output của `Runtime.version()` trong tài liệu kiểm thử đa môi trường.** Kết quả phụ thuộc runtime thực tế mà lệnh `java` đã chọn. Một ứng dụng biên dịch bằng JDK 24 với `--release 17` nhưng chạy trên JVM 21 sẽ nhận `feature() == 21`, không phải `17`.

### 2.2. Đang kiểm tra một chuỗi khai báo phiên bản?

```java
Runtime.Version declared =
        Runtime.Version.parse("17.0.10+7-LTS");

System.out.println(declared.feature()); // 17
System.out.println(declared.update());  // 10
```

Đây là một **object được parse từ chuỗi do ứng dụng cung cấp**, không phải bản mô tả JVM hiện đang chạy. `Runtime.Version.parse` không thay đổi runtime, không kiểm tra xem JDK đó có được cài trên máy hay không, và không tải bất cứ thư viện nào.

Đừng dùng `Runtime.version()` để xác nhận phiên bản một **JAR dependency**: nó chỉ mô tả JVM. Ngược lại, `parse("21")` không có nghĩa chương trình hiện chạy Java 21.

## 3. Hợp đồng phiên bản Java SE hiện đại

Theo tài liệu `Runtime.Version`, các thành phần số đầu tiên có dạng khái niệm:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

| Thành phần | Phương thức | Ý nghĩa theo mô hình hiện đại |
| --- | --- | --- |
| `FEATURE` | `feature()` | Bộ đếm bản phát hành tính năng, ví dụ `17`, `21` |
| `INTERIM` | `interim()` | Bộ đếm bản interim tương thích; thường là `0` trong mô hình phát hành hiện hành |
| `UPDATE` | `update()` | Bộ đếm đợt cập nhật tương thích, có thể chứa sửa lỗi/bảo mật |
| `PATCH` | `patch()` | Bộ đếm bản vá khẩn cấp khi cần |
| Thành phần số thứ 5 trở đi | `version()` | Có thể do nhà triển khai dùng cho thông tin patch riêng |

Ví dụ:

```java
Runtime.Version v = Runtime.Version.parse("17.0.10");

System.out.println(v.feature()); // 17
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 10
System.out.println(v.patch());   // 0
```

**Điểm đặc biệt:** các thành phần số ở cuối có giá trị `0` **không được ghi thừa** trong chuỗi phiên bản hợp lệ. Vì vậy:

- `17`: hợp lệ.
- `17.0.10`: hợp lệ; `interim() = 0`, `update() = 10`, `patch() = 0`.
- `17.0.10.1`: hợp lệ; `patch() = 1`.
- `17.0.0`: **không hợp lệ**, vì chứa số 0 thừa ở cuối.
- `17.0.010`: **không hợp lệ**, vì `010` có số 0 đứng đầu.

Khi accessor cho một thành phần bị thiếu, các hàm `interim()`, `update()` và `patch()` **trả `0`**; không cần tự kiểm tra độ dài danh sách và lấp các phần tử còn thiếu.

Đây là mô hình phát hành Java SE từ Java 10, **không phải quy tắc SemVer chung cho mọi phần mềm**. Không dùng nó để parse mọi chuỗi version của thư viện Maven hoặc ứng dụng khác.

## 4. Chuỗi phiên bản có thể có pre-release, build và thông tin tùy chọn

Một Java version string có thể bổ sung những đoạn sau:

```text
17.0.10+7-LTS
|  |  | |  |
|  |  | |  +-- optional build information: LTS
|  |  | +----- build number: 7
|  +--+------- các thành phần version number
+-------------- feature: 17

21-ea+5
|  |  |
|  |  +-- build: 5
|  +----- pre-release: ea
+-------- feature: 21
```

Javadoc nêu các họ cú pháp `$VNUM(-$PRE)?+$BUILD(-$OPT)?`, `$VNUM-$PRE(-$OPT)?` và `$VNUM(+- $OPT)` với dấu nối liền phù hợp (mẫu cuối thực tế viết `$VNUM+-$OPT`, không có khoảng trắng). Những thành phần bổ sung:

- **`pre()`:** `Optional<String>`, chứa nhãn tiền phát hành như `ea`; có thể vắng.
- **`build()`:** `Optional<Integer>`, chứa số build; có thể vắng.
- **`optional()`:** `Optional<String>`, chứa mô tả build bổ sung; có thể vắng.

Ví dụ:

```java
var v = Runtime.Version.parse("17.0.10+7-LTS");

System.out.println(v.version());               // [17, 0, 10]
System.out.println(v.pre().orElse("none"));    // none
System.out.println(v.build().orElse(-1));      // 7
System.out.println(v.optional().orElse("none")); // LTS
```

**Không tự diễn giải `LTS` trong `optional()` thành bằng chứng runtime đã được nhà cung cấp bảo trì, hỗ trợ hoặc vá mọi lỗ hổng.** Nó chỉ là thông tin nhận diện bổ sung của chuỗi. Chính sách hỗ trợ/bảo mật thực tế phải được xác minh với nhà cung cấp, kênh phân phối và lịch cập nhật.

Tương tự, build `7` không phải số `UPDATE` và không phải “bản vá bảo mật thứ bảy”. Cần dùng đúng accessor tương ứng.

## 5. Những phương thức cần dùng và kiểu dữ liệu trả về

| Phương thức hiện hành | Kiểu trả về | Dùng khi nào |
| --- | --- | --- |
| `Runtime.version()` | `Runtime.Version` | Lấy phiên bản JVM đang chạy |
| `Runtime.Version.parse(String)` | `Runtime.Version` | Đọc chuỗi Java SE version hợp lệ |
| `feature()` | `int` | Kiểm tra major feature release của Java |
| `interim()` | `int` | Đọc thành phần interim, không có thì 0 |
| `update()` | `int` | Đọc update counter, không có thì 0 |
| `patch()` | `int` | Đọc patch counter, không có thì 0 |
| `version()` | `List<Integer>` không sửa được | Đọc toàn bộ dãy thành phần số |
| `pre()` | `Optional<String>` | Xem nhãn pre-release, ví dụ `ea` |
| `build()` | `Optional<Integer>` | Xem build number |
| `optional()` | `Optional<String>` | Xem nhận diện build bổ sung |
| `compareTo(Version)` | `int` | So sánh theo đầy đủ quy tắc phiên bản |
| `compareToIgnoreOptional(Version)` | `int` | So sánh nhưng bỏ qua `optional()` |
| `equals(Object)` | `boolean` | So sánh cả những thành phần phân biệt hai version |
| `equalsIgnoreOptional(Object)` | `boolean` | So sánh bỏ qua thông tin optional |
| `toString()` | `String` | Lấy biểu diễn chuỗi phiên bản |

Ba phương thức cũ `major()`, `minor()`, `security()` đã được **deprecated từ Java 10**. Trong code mới, **không sử dụng** chúng làm chuẩn; nên dùng `feature()`, `interim()`, `update()`. Tên `security()` đặc biệt dễ gây nhầm vì thành phần thứ ba hiện nay là update counter, **không phải một mức bảo mật**.

## 6. `version()` là một danh sách số không sửa được

```java
Runtime.Version version =
        Runtime.Version.parse("17.0.10+7-LTS");

List<Integer> numbers = version.version();

System.out.println(numbers);      // [17, 0, 10]
System.out.println(numbers.size()); // 3
```

Đoạn này cần import `java.util.List`; `Runtime` nằm trong `java.lang`.

Các điểm cần chú ý:

1. `version()` chứa **các thành phần số thực sự hiện diện**; không tự thêm hai số `0` ở cuối chỉ vì mô hình khái niệm có bốn vị trí.
2. Danh sách trả về là **unmodifiable**; gọi `add` hoặc `set` không hợp lệ.
3. Danh sách có ít nhất phần tử `FEATURE`, nhưng **không hứa luôn có phần tử ở vị trí 2/3**.
4. Cần lấy feature/update/patch? Ưu tiên **accessor có tên**; tránh `version().get(2)` mà không biết dãy đủ dài.
5. Các thành phần số **không thể so sánh bằng string lexical**: cần so số theo từng phần hoặc dùng sẵn `compareTo`.

Ví dụ `Runtime.Version.parse("21").version()` là `[21]`. `update()` và `patch()` đều trả `0`, chứ không tự đọc từ vị trí không tồn tại.

## 7. Vì sao so sánh chuỗi theo từ điển sai?

So sánh String trong Java là so theo thứ tự ký tự, không phải số:

```java
String a = "17.0.9";
String b = "17.0.10";

System.out.println(b.compareTo(a) > 0); // false
```

Vì tại vị trí sau `"17.0."`, ký tự `'1'` của `"10"` đứng trước ký tự `'9'` của `"9"` trong thứ tự ký tự. Điều đó không phản ánh ý nghĩa update counter.

`Runtime.Version` thực hiện so sánh theo **thành phần số**, rồi đến pre-release, build number và optional information:

```java
var a = Runtime.Version.parse("17.0.9");
var b = Runtime.Version.parse("17.0.10");

System.out.println(b.compareTo(a) > 0); // true
```

**Quy tắc Java cần ghi nhớ:** nếu mục tiêu là biết bản Java nào lớn hơn theo thứ tự phiên bản Java SE, dùng `compareTo` thay vì `String.compareTo`, regex tách dấu chấm rồi tự viết comparator hoặc so từng ký tự.

Không so sánh kết quả `compareTo` với giá trị chính xác `1` hay `-1`: hợp đồng `Comparable` chỉ bảo đảm **âm, bằng 0, dương**, không buộc độ lớn tuyệt đối của kết quả là 1. Cách an toàn là `compareTo(...) < 0`, `== 0`, hoặc `> 0`.

## 8. Quy tắc so sánh của `Runtime.Version.compareTo`

Theo Javadoc, việc so sánh đi qua các thành phần theo thứ tự ưu tiên:

1. **Version number**: so các số theo từng vị trí; version có thành phần phụ lớn hơn thắng.
2. **Pre-release identifier**: khi version number bằng nhau, bản có pre-release **nhỏ hơn** bản không có pre-release.
3. **Build number**: sau khi các thành phần trước bằng nhau, bản **không có** build number nhỏ hơn bản có build; hai build number so sánh như số.
4. **Optional build information**: sau các thành phần còn lại, so theo thứ tự chữ; bản **có** optional information được coi lớn hơn bản không có.

Ví dụ:

```java
var ea = Runtime.Version.parse("21-ea+5");
var released = Runtime.Version.parse("21+5");

System.out.println(ea.compareTo(released) < 0); // true
```

Điều đó thể hiện bản pre-release thấp hơn bản không có pre-release, **không phải** lời hứa một build bất kỳ sẽ có các tính năng ổn định hoặc được phép dùng trong production.

Một vài so sánh theo quy tắc API:

```java
Runtime.Version.parse("17.0.10")
        .compareTo(Runtime.Version.parse("17.0.9")) > 0; // true

Runtime.Version.parse("17.0.10.1")
        .compareTo(Runtime.Version.parse("17.0.10")) > 0; // true

Runtime.Version.parse("17+7")
        .compareTo(Runtime.Version.parse("17")) > 0; // true
```

Đây là các biểu thức minh họa bên trong một phương thức. Chúng cho thấy **số trong version không giống ký tự trong string**; phần build cũng có vị trí trong ordering nếu dùng `compareTo`.

**Tuy nhiên, đối với chính sách “runtime có đủ feature Java 17 hay không”, không nhất thiết muốn so toàn bộ build/optional**. Khi chỉ yêu cầu API Java 17, thường nên kiểm tra `feature() >= 17`, không phải chọn một build string tùy ý rồi so đầy đủ.

## 9. `compareToIgnoreOptional` và `equalsIgnoreOptional`

Một số chuỗi phiên bản khác nhau ở phần optional build information:

```java
var lts = Runtime.Version.parse("17.0.10+7-LTS");
var vendor = Runtime.Version.parse("17.0.10+7-vendor");
```

Với chúng:

```java
System.out.println(lts.equals(vendor)); // false

System.out.println(
        lts.equalsIgnoreOptional(vendor)); // true

System.out.println(
        lts.compareToIgnoreOptional(vendor)); // 0
```

Đây không phải hai Java runtime đã được xác minh tương đương ở mọi thuộc tính; các lời gọi này **chỉ so sánh phiên bản theo tiêu chí được xác định bởi API**.

Nên chọn một cặp phương thức **nhất quán**:

- Nếu phần `optional()` quan trọng với bài toán, dùng `compareTo` và `equals`.
- Nếu chỉ muốn bỏ qua phần optional build identity, dùng `compareToIgnoreOptional` và `equalsIgnoreOptional`.
- **`compareToIgnoreOptional` vẫn xét version number, pre-release và build number**. Nó không có nghĩa “chỉ so sánh feature” hay “bỏ hết phần đằng sau số đầu tiên”.

**Lưu ý về Collection:** `equalsIgnoreOptional` **không thay thế** phương thức `Object.equals` của lớp. `HashSet` và `HashMap` mặc định vẫn dùng `equals/hashCode`, không tự gộp hai phiên bản chỉ vì `equalsIgnoreOptional` trả `true`. Nếu nghiệp vụ cần gom phiên bản theo một phần thông tin, thiết kế key chuẩn hóa riêng; đừng suy luận rằng HashMap sẽ sử dụng comparator hoặc equals-ignore-optional.

Tương tự, khi sắp xếp hoặc làm key trong `TreeSet` với một Comparator bỏ qua optional, có thể xảy ra việc hai phiên bản được coi là trùng theo comparator dù `equals` trả `false`. Chỉ dùng khi đó là một **chính sách được chấp nhận có chủ đích**.

## 10. Chính sách kiểm tra JVM tối thiểu: ưu tiên `Runtime.version().feature()`

Một API hoặc thư viện có thể yêu cầu Java 17 trở lên. Nếu yêu cầu thực sự là **feature level**, cách kiểm tra trực tiếp:

```java
static void requireJava17() {
    int feature = Runtime.version().feature();
    if (feature < 17) {
        throw new IllegalStateException(
                "Ứng dụng yêu cầu Java 17 trở lên");
    }
}
```

Đây là phương thức trong một lớp Java.

Ưu điểm:

- Không cần `System.getProperty("java.version")` rồi tự tách string.
- Không nhầm update/build với feature.
- Có ý nghĩa rõ ràng, dễ unit test khi trích chính sách thành hàm nhận `Runtime.Version`.
- Không phụ thuộc thứ tự ký tự của chuỗi version.

Một phiên bản linh hoạt để kiểm thử:

```java
static boolean supportsMinimumFeature(
        Runtime.Version running, int minimum) {
    Objects.requireNonNull(running, "running");
    return running.feature() >= minimum;
}
```

Cần import `java.util.Objects`; mã nằm trong một lớp.

**Giới hạn quan trọng:** số feature chỉ giúp trả lời runtime đã ở feature release nào. Nó **không** tự bảo đảm chương trình dùng đúng classfile target, có mọi module, dependency, native library, hay JVM flags cần thiết. Để bảo đảm tương thích chạy thật, còn phải cấu hình `javac --release`, kiểm tra dependencies và test trên JVM mục tiêu.

Nếu muốn kiểm tra **bản update tối thiểu của một dòng Java cụ thể**, hãy xác định một chính sách rõ về feature, update và patch; đừng so mỗi `update()` của Java 17 với Java 21 mà không nhìn feature.

## 11. Kiểm tra pre-release trước khi quyết định policy

Một chuỗi Java như `21-ea+5` có thông tin pre-release:

```java
Runtime.Version candidate =
        Runtime.Version.parse("21-ea+5");

boolean earlyAccess = candidate.pre().isPresent();
// true
```

Một ứng dụng có thể yêu cầu không chạy trên pre-release nếu sản phẩm chưa hỗ trợ, bằng cách kiểm tra `pre().isEmpty()`. Đó là **chính sách ứng dụng**, không phải quy định mọi chương trình Java phải cấm early-access.

Ví dụ minh họa:

```java
static boolean acceptableForProduction(
        Runtime.Version version, int minFeature) {
    return version.feature() >= minFeature
            && version.pre().isEmpty();
}
```

Lưu ý rằng điều kiện trên **không kiểm tra** bản JDK có thực sự được vá bảo mật, nhà cung cấp có hỗ trợ, module có đủ, hay license/distribution có phù hợp hay không. Nó chỉ kiểm tra **số feature tối thiểu và việc thiếu nhãn pre-release**. Không đặt tên hàm như `isSecure` khi nó không có đủ dữ liệu để kết luận.

Khi cần kiểm soát nhà cung cấp hay lịch bảo trì, dùng metadata triển khai/nhà phân phối và thông tin cập nhật đáng tin cậy bên ngoài `Runtime.Version`.

## 12. Đầu vào sai định dạng và chính sách xử lý lỗi

`Runtime.Version.parse` đòi hỏi **Java version string hợp lệ theo quy ước của API**. Nếu input không đúng, nó không cố đoán ý định như một bộ parser tự viết có thể làm.

Các trường hợp cần phân biệt:

| Input | Hành vi điển hình | Lý do |
| --- | --- | --- |
| `"17"` | Hợp lệ | Chỉ có feature |
| `"17.0.10"` | Hợp lệ | Có interim và update |
| `"17.0.10+7-LTS"` | Hợp lệ | Có build và optional info |
| `"21-ea+5"` | Hợp lệ | Có pre-release và build |
| `"17.0.0"` | `IllegalArgumentException` | Thành phần `0` thừa ở cuối |
| `"17.0.010"` | `IllegalArgumentException` | Số có leading zero |
| `"17-ea+"` | `IllegalArgumentException` | Có `+` nhưng thiếu build |
| `"1.8.0_202"` | `IllegalArgumentException` | Không thuộc cú pháp Java SE version string hiện hành |
| `null` | `NullPointerException` | Không có chuỗi để parse |
| Phần số vượt phạm vi `int` | Có thể `NumberFormatException` | Số không biểu diễn được bằng Integer |

`NumberFormatException` là lớp con của `IllegalArgumentException`; khi cần phân loại lỗi chi tiết, bắt cụ thể trước rồi mới bắt tổng quát. Khi chỉ muốn báo lỗi “invalid Java version string”, thường có thể bắt `IllegalArgumentException` cho các chuỗi không parse được, và xác thực null ở ranh giới.

Ví dụ một phương thức parse được kiểm soát:

```java
static Runtime.Version parseConfiguredJavaVersion(String raw) {
    Objects.requireNonNull(raw, "javaVersion");
    if (raw.isBlank()) {
        throw new IllegalArgumentException(
                "javaVersion must not be blank");
    }
    try {
        return Runtime.Version.parse(raw);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid Java version string", ex);
    }
}
```

Phương thức này cần `java.util.Objects`. Nó **không tự cắt khoảng trắng**, không tự sửa số version và không âm thầm bỏ phần suffix. Nếu nghiệp vụ cho phép trim whitespace, hãy thực hiện điều đó thành **một bước chuẩn hóa có chủ đích** và mô tả rõ hợp đồng; nếu dữ liệu là input cấu hình nghiêm ngặt, việc reject ngay có thể phù hợp hơn.

**Không nên “fallback” về phiên bản nhỏ như `8` hoặc `17` khi parse lỗi**, rồi tiếp tục cho chạy tính năng phụ thuộc runtime. Điều đó sẽ che thông tin sai và có thể làm hệ thống đi vào nhánh cấu hình không an toàn.

## 13. Đừng cố parse nguyên stdout của `java -version`

Lệnh console:

```bash
java --version
```

có thể in nhiều dòng, bao gồm version, loại VM, vendor, build string và các mô tả khác. **Cả khối stdout** không phải một `$VSTR` theo hợp đồng `Runtime.Version.parse`.

Ngay cả property `java.version` hoặc `java.runtime.version` cũng có thể có định dạng nhận diện bổ sung tùy nhà cung cấp và release. Khi code đang chạy trong JVM và chỉ cần biết **runtime hiện tại**, hãy lấy trực tiếp:

```java
Runtime.Version running = Runtime.version();
```

Nếu một **công cụ ngoài Java** phải đọc phiên bản JDK khác, hãy dùng nguồn dữ liệu có cấu trúc hoặc bước trích xuất theo hợp đồng của công cụ đó. Sau khi đã có một **Java version string hợp lệ**, mới gọi `Runtime.Version.parse`. Không xem `parse` là parser đa năng nhận mọi dòng log, Docker tag, banner hoặc tên gói cài đặt.

**Ví dụ phân biệt:**

```text
17.0.10+7-LTS            <-- Java version string có thể parse
openjdk 17.0.10 2024...  <-- dòng banner, không phải version string
jdk-17.0.10+7.zip        <-- tên file, không phải version string
```

Không cắt “ba chữ số đầu tiên” của banner rồi đoán phiên bản. Với mục đích xác nhận runtime trong chính chương trình, không cần parse banner ngay từ đầu.

## 14. Mô hình phiên bản Java không phải SemVer tổng quát

`Runtime.Version` được thiết kế cho **version string của implementation Java SE Platform**. Nó không phải thư viện so sánh tất cả version string trên Internet.

Ví dụ những kiểu dữ liệu khác có thể có hợp đồng riêng:

- Maven artifact version như `1.2.3-SNAPSHOT`.
- Semantic Versioning của sản phẩm thứ ba như `1.2.3-beta.1+build.45`.
- Docker image tag ghép vendor, OS, kiến trúc và build.
- Git tag/release string có tiền tố `v` hoặc nhãn tuỳ ý.
- Nhãn bảo mật được ghi trong CMDB hoặc metadata cập nhật của vendor.

Ngay cả khi một số chuỗi ở các hệ sinh thái đó **vô tình parse thành công**, thứ tự so sánh của chúng cũng không nhất thiết có cùng ý nghĩa với `Runtime.Version.compareTo`. Không dùng API chỉ vì “nó nhận được dấu chấm và dấu gạch”.

**Quy tắc:** dữ liệu đại diện **phiên bản Java SE** → `Runtime.Version`. Dữ liệu phiên bản của hệ thống khác → dùng parser/comparator theo **đúng đặc tả của hệ thống đó**.

## 15. Chương trình Java 17+ đầy đủ, không cần thư viện ngoài

Tạo tệp `RuntimeVersionContractDemo.java`:

```java
import java.util.Objects;

public class RuntimeVersionContractDemo {

    static void require(boolean ok, String msg) {
        if (!ok) {
            throw new AssertionError(msg);
        }
    }

    static void expectInvalid(String value) {
        try {
            Runtime.Version.parse(value);
            throw new AssertionError(
                    "Accepted invalid version: " + value);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid=" + value);
        }
    }

    public static void main(String[] args) {
        var parsed = Runtime.Version.parse("17.0.10+7-LTS");

        System.out.println("full=" + parsed);
        System.out.println("numbers=" + parsed.version());
        System.out.println("feature=" + parsed.feature());
        System.out.println("interim=" + parsed.interim());
        System.out.println("update=" + parsed.update());
        System.out.println("patch=" + parsed.patch());
        System.out.println("pre="
                + parsed.pre().orElse("none"));
        System.out.println("build="
                + parsed.build().orElse(-1));
        System.out.println("optional="
                + parsed.optional().orElse("none"));

        require(parsed.feature() == 17
                && parsed.interim() == 0
                && parsed.update() == 10
                && parsed.patch() == 0
                && parsed.build().orElseThrow() == 7,
                "wrong version fields");

        var ea = Runtime.Version.parse("21-ea+5");
        var ga = Runtime.Version.parse("21+5");
        System.out.println("prerelease="
                + ea.pre().orElse("none"));
        System.out.println("eaLessThanGa="
                + (ea.compareTo(ga) < 0));
        require(ea.compareTo(ga) < 0,
                "EA ordering is incorrect");

        var oldUpdate = Runtime.Version.parse("17.0.9");
        var newUpdate = Runtime.Version.parse("17.0.10");
        System.out.println("numericCompare="
                + (newUpdate.compareTo(oldUpdate) > 0));
        System.out.println("lexicalCompare="
                + ("17.0.10".compareTo("17.0.9") > 0));
        require(newUpdate.compareTo(oldUpdate) > 0,
                "numeric version comparison failed");

        var vendor = Runtime.Version.parse(
                "17.0.10+7-vendor");
        System.out.println("equal="
                + parsed.equals(vendor));
        System.out.println("equalIgnoreOptional="
                + parsed.equalsIgnoreOptional(vendor));
        System.out.println("compareIgnoreOptional="
                + parsed.compareToIgnoreOptional(vendor));

        require(!parsed.equals(vendor)
                && parsed.equalsIgnoreOptional(vendor)
                && parsed.compareToIgnoreOptional(vendor) == 0,
                "optional build comparison failed");

        expectInvalid("17.0.0");
        expectInvalid("17.0.010");
        expectInvalid("17-ea+");
        expectInvalid("1.8.0_202");

        System.out.println("runningFeaturePositive="
                + (Runtime.version().feature() > 0));
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac RuntimeVersionContractDemo.java
java RuntimeVersionContractDemo
```

Output được kiểm chứng trên JDK 24, nhưng **không phụ thuộc số feature cụ thể của máy chạy**:

```text
full=17.0.10+7-LTS
numbers=[17, 0, 10]
feature=17
interim=0
update=10
patch=0
pre=none
build=7
optional=LTS
prerelease=ea
eaLessThanGa=true
numericCompare=true
lexicalCompare=false
equal=false
equalIgnoreOptional=true
compareIgnoreOptional=0
invalid=17.0.0
invalid=17.0.010
invalid=17-ea+
invalid=1.8.0_202
runningFeaturePositive=true
tests=PASS
```

**Cách hiểu từng nhóm output:**

1. `full` và `numbers`: API tách chính xác phần số, pre-release, build và optional; danh sách số không có những số 0 cuối bị bỏ qua theo cú pháp.
2. `feature/interim/update/patch`: tên truy cập mang đúng ý nghĩa của các thành phần; patch bị thiếu trả `0`.
3. `pre=none`, `build=7`, `optional=LTS`: chỉ `build` và `optional` hiện diện trong ví dụ.
4. `prerelease=ea` và `eaLessThanGa=true`: so sánh hiểu thứ tự pre-release/GA.
5. `numericCompare=true` nhưng `lexicalCompare=false`: minh họa tại sao so String là sai.
6. `equal=false` và `equalIgnoreOptional=true`: hai version có optional info khác nhau, cần chọn chính sách so sánh nhất quán.
7. Các dòng `invalid=...` chỉ xuất hiện khi API **từ chối** đúng đầu vào sai, còn `AssertionError` nếu lại chấp nhận.
8. `runningFeaturePositive=true` chỉ kiểm tra rằng feature JVM hiện tại là một số hợp lệ; không hardcode `24`.
9. `tests=PASS` chỉ in nếu các assertion đã qua.

**Lưu ý về kiểm thử:** bản thân `Runtime.Version` có từ Java 9, nhưng cách truy cập `feature()`/`interim()`/`update()`/`patch()` được giới thiệu từ Java 10. Chương trình trên dùng Java 17+ để có môi trường học và các API hiện hành, không sử dụng những phương thức version đã deprecated.

## 16. Viết unit test cho logic phụ thuộc phiên bản

Nếu ứng dụng thật sự cần quyết định một tính năng dựa trên JVM hiện có, nên tách chính sách khỏi việc **đọc phiên bản JVM** để test bằng giá trị ổn định.

Ví dụ:

```java
import java.util.Objects;

static boolean canRunFeature(
        Runtime.Version current, int minimumFeature) {

    Objects.requireNonNull(current, "current");
    return current.feature() >= minimumFeature
            && current.pre().isEmpty();
}
```

Phương thức này là **mã minh họa bên trong một lớp**. Từ “canRunFeature” ở đây chỉ là chính sách kiểm tra **feature + không pre-release**, không bảo đảm dependencies đã được đóng gói hoặc mọi API đều có thể chạy.

Các trường hợp kiểm thử theo JUnit Jupiter:

```java
assertFalse(canRunFeature(
        Runtime.Version.parse("17-ea+5"), 17));

assertTrue(canRunFeature(
        Runtime.Version.parse("17.0.10+7"), 17));

assertFalse(canRunFeature(
        Runtime.Version.parse("16.0.2"), 17));

assertTrue(canRunFeature(
        Runtime.Version.parse("21.0.2"), 17));
```

Cần JUnit Jupiter và static imports `assertFalse`/`assertTrue`; đây chỉ là đoạn test, không phải chương trình độc lập. Những test này **không cần thay JVM hiện tại** hay sửa `System.setProperty("java.version",...)`; chúng dùng các `Runtime.Version` giả lập có chủ đích.

**Không dùng `Runtime.version()` trực tiếp trong mọi assertion** vì test có thể chạy trên JDK khác nhau trong CI. Ở điểm tích hợp cuối cùng, chỉ cần gọi `Runtime.version()` một lần ở nơi quyết định policy rồi truyền vào hàm xử lý.

Khi test thông tin optional:

```java
var a = Runtime.Version.parse("17.0.10+7-LTS");
var b = Runtime.Version.parse("17.0.10+7-vendor");

// assertFalse(a.equals(b));
// assertTrue(a.equalsIgnoreOptional(b));
// assertEquals(0, a.compareToIgnoreOptional(b));
```

Hãy đặt tên test theo **ý nghĩa chính sách**, không chỉ tên phương thức. Ví dụ `ignoresVendorSuffixWhenComparingBuildLevel` diễn đạt rõ hơn `testCompare`.

## 17. Kiểm thử và logging trong hệ thống thật

### 17.1. Logging runtime đúng mục đích

Khi chương trình khởi động, có thể log:

```java
Runtime.Version javaVersion = Runtime.version();

System.out.println(
        "javaFeature=" + javaVersion.feature());
System.out.println(
        "javaRuntimeVersion=" + javaVersion);
```

Giá trị `toString()` phụ thuộc JVM thật; output không cố định giữa môi trường. Dùng để chẩn đoán cấu hình deployment. Nếu cần thêm vendor, xem thuộc tính phù hợp như `java.vendor` nhưng **không suy rằng vendor là một thành phần của `feature()`**.

### 17.2. Kiểm tra patch/update theo chính sách

Nếu một yêu cầu cụ thể nói “chỉ cho phép Java 17 kể từ update 10”, có thể kiểm tra feature bằng 17 và update bằng 10:

```java
static boolean supportsJava17Update10OrNewer(
        Runtime.Version version) {

    if (version.feature() > 17) {
        return true;
    }
    return version.feature() == 17
            && version.update() >= 10
            && version.pre().isEmpty();
}
```

Đây **chỉ là một ví dụ điều kiện nghiệp vụ**; không có nghĩa mọi JDK 17.0.10 đều bảo đảm đã vá mọi CVE, hay Java 18 có cùng chính sách hỗ trợ của một dự án. Cần có **ma trận runtime được phép và kênh vá thật sự** từ nhà cung cấp.

Nếu chính sách so phiên bản đầy đủ bằng `compareTo`, hãy nhớ build/pre/optional có ảnh hưởng. Ví dụ `17.0.10` so với `17.0.10+7` không bằng nhau theo ordering, và chuỗi build có thể tạo khác biệt không được doanh nghiệp quan tâm. Trước khi chọn comparator, phải nói rõ **cần so feature, update, patch, build, hay vendor-specific metadata**.

### 17.3. Khác biệt compiler target và runtime thật

Một ứng dụng biên dịch bằng:

```bash
javac --release 17 App.java
```

có thể được chạy bằng JVM Java 17 hoặc mới hơn nếu toàn bộ ứng dụng/dependency thích hợp. `Runtime.version().feature()` phản ánh **JVM chạy**, không phản ánh tham số `--release` đã dùng để tạo classfile.

Để xem classfile major, dùng công cụ như `javap -verbose` trên artifact; **đừng dùng `Runtime.version()` thay phép kiểm tra classfile target**.

## 18. API có hợp đồng, nhưng không giải quyết mọi điều kiện tương thích

`Runtime.Version` làm rất tốt hai nhóm công việc:

1. **Truy xuất phiên bản Java runtime một cách có cấu trúc**.
2. **Parse và so sánh Java version strings hợp lệ**.

Nó không phải một bộ xác nhận mọi năng lực của JVM. Ví dụ:

- Một runtime có feature phù hợp nhưng dependency bên thứ ba được build cho feature mới hơn.
- Một module cần được đóng gói hoặc cấu hình thêm.
- Một tính năng cần flags, native libraries hoặc điều kiện hệ điều hành.
- Một bản phát hành pre-release có cách phân phối khác với bản ổn định.
- Một JDK có version lớn nhưng chưa có bản vá security dành cho nhánh phân phối cụ thể.
- Một classfile target không phù hợp với JVM thực tế.

Vì vậy nên:

- Dùng `Runtime.version()` để lấy thông tin **JVM** khi cần.
- Dùng `Runtime.Version.parse` cho **chuỗi phiên bản Java SE** đã được xác định nguồn và định dạng.
- Dùng `--release` trong build để kiểm soát language + JDK API + classfile.
- Test trên **JVM mục tiêu thật** cùng dependency/packaging thực tế.
- Dựa vào tài liệu nhà cung cấp cho thông tin support/security, không tự gắn nhãn an toàn từ `optional()`.

## 19. Value-based class: so sánh bằng giá trị, không khóa theo identity

Javadoc mô tả `Runtime.Version` là một **value-based class**. Điều này có nghĩa các instance đại diện cùng một giá trị nên được coi như thay thế nhau theo `equals`.

```java
var one = Runtime.Version.parse("17.0.10");
var two = Runtime.Version.parse("17.0.10");

System.out.println(one.equals(two)); // true
```

**Không dùng `one == two` để kiểm tra phiên bản**, vì identity của object không phải hợp đồng cần dựa vào.

Đặc biệt **không đồng bộ bằng `synchronized(versionObject)`**. Javadoc cảnh báo identity-sensitive operations trên value-based instance có thể cho hành vi khó đoán. Nếu cần khóa trong ứng dụng đa luồng, dùng đối tượng khóa độc lập hoặc cơ chế đồng bộ phù hợp, không dùng phiên bản như một monitor.

Vì `Runtime.Version` chỉ mang dữ liệu phiên bản, các đoạn code chọn nhánh theo version có thể dùng object bất biến và giá trị đọc được ở runtime, không cần tự tạo state mutable để “ghi nhớ” các thành phần đã tách bằng regex.

## 20. Những lỗi thường gặp và cách xử lý

| Cách hiểu/viết sai | Vấn đề | Cách nên dùng |
| --- | --- | --- |
| `System.getProperty("java.version").split("\\.")` rồi lấy thành phần đầu | Phụ thuộc format chuỗi, suffix build/pre-release có thể làm parse lỗi | `Runtime.version().feature()` |
| So `"17.0.10"` và `"17.0.9"` bằng `String.compareTo` | So ký tự, không phải số | `Runtime.Version.parse(...).compareTo(...)` |
| Tự tách `17.0.10+7-LTS` bằng dấu chấm rồi `Integer.parseInt` | Phần build và optional không được phân tích đúng | `feature()`/`update()`/`build()`/`optional()` |
| Gọi `version().get(2)` mà không kiểm tra độ dài | `"17"` chỉ có một thành phần số | `update()` trả 0 nếu không có |
| Nhầm `build()` với `update()` | Build number khác update counter | Dùng accessor đúng ngữ nghĩa |
| Dùng `major()` hoặc `security()` cho code mới | Deprecated từ Java 10, tên không phản ánh mô hình mới | Dùng `feature()`, `update()` |
| Chấp nhận `17.0.0` như chuỗi chuẩn | Version number không có trailing zero | Dùng `17` hoặc chuỗi hợp lệ |
| Cho rằng `Runtime.Version.parse` nhận mọi banner `java --version` | Banner có cả chữ và mô tả khác | Chỉ parse một Java version string hợp lệ |
| Tự parse phiên bản thư viện Maven/Gradle với `Runtime.Version` | Java SE version không phải SemVer chung | Dùng công cụ đặc thù hệ sinh thái đó |
| `equalsIgnoreOptional` được dùng như `equals` trong HashSet mặc định | HashSet dùng `equals/hashCode` | Thiết kế key/comparator phù hợp theo policy |
| `compareToIgnoreOptional` bị hiểu là “bỏ mọi suffix” | Chỉ bỏ **optional()**, vẫn tính pre/build | Ghi rõ phạm vi so sánh |
| Dựa vào `optional()=="LTS"` để kết luận đã vá mọi CVE | Optional chỉ là metadata nhận diện | Xem vendor/support/advisory thực tế |
| Coi `Runtime.version().feature()==17` là bảo chứng toàn bộ app chạy được | Không kiểm tra dependencies, runtime flags, modules, bytecode | Build `--release` + test JVM thực |
| Kiểm tra Java feature bằng so chữ `"9">"17"` | Lexical khác numeric | Dùng `feature()` |
| Dùng kết quả `compareTo` và yêu cầu đúng `1` | Comparator chỉ hứa âm/0/dương | Dùng `<0` / `==0` / `>0` |
| Đồng bộ trên object `Runtime.Version` | Value-based class không phù hợp làm monitor | Dùng khóa riêng |

## 21. Bài tập tự kiểm tra

### Bài 1: các accessor

```java
var version = Runtime.Version.parse("21.0.2+13");
```

**Hỏi:** giá trị `feature()`, `interim()`, `update()`, `patch()`, `build()`?

**Đáp án:** `21`, `0`, `2`, `0` và `Optional.of(13)`. Patch bị thiếu trả `0`; số `13` sau dấu `+` là **build**, không phải patch/update.

### Bài 2: “17.0.10” và “17.0.9”

```java
var a = Runtime.Version.parse("17.0.10");
var b = Runtime.Version.parse("17.0.9");
```

**Hỏi:** `a.compareTo(b) > 0` hay `< 0`?

**Đáp án:** `> 0` vì so theo các thành phần **số**, 10 lớn hơn 9. Không so chuỗi trực tiếp theo chữ cái.

### Bài 3: pre-release so với bản không pre-release

```java
var a = Runtime.Version.parse("21-ea+5");
var b = Runtime.Version.parse("21+5");
```

**Hỏi:** bên nào nhỏ hơn?

**Đáp án:** `a.compareTo(b) < 0` vì bản có pre-release được xếp trước bản không có pre-release khi version number tương đương.

### Bài 4: hai build identity khác nhau

```java
var a = Runtime.Version.parse("17.0.10+7-LTS");
var b = Runtime.Version.parse("17.0.10+7-vendor");
```

**Hỏi:** `a.equals(b)` và `a.equalsIgnoreOptional(b)`?

**Đáp án:** lần lượt `false` và `true`. `compareToIgnoreOptional` cũng trả `0`. Chỉ phần optional khác; điều đó không khẳng định hai bản build có cùng vendor, security updates hoặc packaging.

### Bài 5: parse input không đúng hợp đồng

```java
Runtime.Version.parse("17.0.0");
```

**Hỏi:** liệu API có sửa chuỗi thành `17` không?

**Đáp án:** Không. Theo hợp đồng version string, trailing zero elements là không hợp lệ; API ném `IllegalArgumentException`. Nếu ứng dụng muốn chuẩn hóa dữ liệu người dùng, cần bước chuẩn hóa do chính ứng dụng định nghĩa trước đó, không tự gán hành vi tự sửa cho `parse`.

### Bài 6: runtime và target

**Hỏi:** chương trình được biên dịch `javac --release 17`, chạy trên JDK 21. `Runtime.version().feature()` bằng bao nhiêu?

**Đáp án:** `21`, vì nó mô tả **runtime thực đang chạy**. `--release 17` là ràng buộc lúc build, không thay version của JVM khi thực thi.

### Bài 7: phiên bản một thư viện khác

**Hỏi:** chuỗi `1.2.3-beta.1+meta` của một thư viện tuân thủ SemVer có nên đưa thẳng vào `Runtime.Version.parse` để so sánh không?

**Đáp án:** Không. `Runtime.Version` dùng quy ước version của Java SE implementation; một hệ thống version khác cần parser và comparator theo đặc tả của hệ thống đó.

## 22. Checklist khi thay logic tách chuỗi version thủ công

1. **Phân loại nguồn:** đang kiểm tra runtime thật hay parse Java version string từ cấu hình?
2. **Runtime thật:** ưu tiên `Runtime.version()`; nếu chỉ cần version feature, dùng `feature()`.
3. **Chuỗi từ cấu hình:** kiểm tra null/blank và gọi `Runtime.Version.parse`; không đoán lại cú pháp.
4. **Bỏ sử dụng accessor deprecated:** chọn `feature()/interim()/update()/patch()`.
5. **Không tự parse số cuối chuỗi:** dùng `pre()/build()/optional()` theo đúng kiểu `Optional`.
6. **Chọn phép so sánh:** `compareTo` hay `compareToIgnoreOptional` tùy việc optional build information có quan trọng.
7. **So minimum feature:** thường dùng `feature() >= N`, không dùng lexical String.
8. **Có input sai:** xử lý `IllegalArgumentException` và null, không âm thầm fallback về version tùy ý.
9. **Có test version update 9 so với 10:** phải khẳng định ordering numeric đúng.
10. **Có test pre-release, build, optional info:** bảo đảm comparator tương thích chính sách.
11. **Không parse cả banner Java launcher:** chỉ parse một chuỗi đúng hợp đồng.
12. **Không dùng Runtime.Version cho các SemVer package khác** trừ khi đã chứng minh quy ước thực sự tương thích.
13. **Không xem metadata version là chứng chỉ an toàn:** xác nhận vendor, bản vá và support ở nguồn thích hợp.
14. **Khi ứng dụng phải chạy trên JVM cũ:** kiểm soát `--release`, dependency và test trên JVM đích.
15. **Dùng value equality, tránh identity/synchronization:** `Runtime.Version` là lớp value-based.

## Kết luận

**`Runtime.Version` thay thế nhu cầu tự cắt chuỗi phiên bản Java** bằng một hợp đồng có cấu trúc: `feature`, `interim`, `update`, `patch`, `pre`, `build`, `optional` và quy tắc so sánh version-aware. Với JVM đang chạy, `Runtime.version().feature()` là cách trực tiếp để lấy feature release; với chuỗi Java SE version hợp lệ, `Runtime.Version.parse` xử lý cú pháp và cung cấp các accessor đúng nghĩa.

Đừng dùng `String.compareTo` hoặc regex `split` tự chế để suy luận thứ tự update/build, đừng dùng các accessor đã deprecated, và đừng coi version string là bằng chứng tuyệt đối về khả năng tương thích/bảo mật. API từ Java 9/10 này **vẫn là lựa chọn hiện hành trong Java mới**, đúng với mục tiêu học Java 10 mà không phụ thuộc những kỹ thuật legacy.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): cú pháp version number/string, `parse`, `feature/interim/update/patch`, `pre/build/optional`, `compareTo` và `compareToIgnoreOptional`, deprecated methods, value-based contract.
- [Java SE 26 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#version()): lấy thông tin version của runtime đang thực thi.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): nền tảng của mô hình `FEATURE.INTERIM.UPDATE.PATCH` từ Java 10.
- [OpenJDK JEP 223 — New Version-String Scheme](https://openjdk.org/jeps/223): cấu trúc version string và pre-release/build metadata.
- [Java SE 26 — `Optional`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html): làm việc với `pre()`, `build()`, `optional()` một cách an toàn.
- [Java SE 26 — `Comparable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Comparable.html): quy tắc trả kết quả âm, bằng 0 và dương cho phép so sánh.
