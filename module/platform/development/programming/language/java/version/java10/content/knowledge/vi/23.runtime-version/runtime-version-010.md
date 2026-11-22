# Kiểm thử phiên bản chính thức, tiền phát hành và bản cập nhật bằng `Runtime.Version` (Java 10+)

## 1. Vấn đề cần giải quyết

Một ứng dụng Java có thể cần kiểm tra phiên bản runtime khi khởi động, khi chạy bộ kiểm thử tương thích, hoặc khi đánh giá một bản JDK trước khi đưa vào hệ thống. Các chuỗi dễ gặp:

```text
27-ea+5
27+1
27.0.1+9
25.0.5+8-LTS
```

Chúng **không mang cùng ý nghĩa**:

- `27-ea+5` có **dấu hiệu tiền phát hành** (*pre-release identifier*) `ea`, thường viết tắt của *early access*.
- `27+1` thuộc feature version 27, không chứa dấu hiệu tiền phát hành, có build number 1.
- `27.0.1+9` là **bản cập nhật** trong dòng feature 27, với update number 1, build number 9.
- `25.0.5+8-LTS` là chuỗi có feature 25, update 5, build 8 và phần **optional build information** `LTS`.

Nếu dùng so sánh chuỗi thô, code có thể nhầm `"27-10"` với `"27-2"`, nhầm `ea` với GA hoặc nhầm metadata `LTS` với quyết định hỗ trợ của nhà cung cấp. Vì vậy cần một API parse/so sánh có hợp đồng rõ ràng.

Java cung cấp `java.lang.Runtime.Version`. Class này có từ **Java 9**; **Java 10**, thông qua **JEP 322 — Time-Based Release Versioning**, làm rõ ý nghĩa các thành phần `FEATURE.INTERIM.UPDATE.PATCH` và bổ sung các accessor mang tên tương ứng.

**Trọng tâm bài học:** viết các phép thử đúng cho **phiên bản chính thức (không có pre-release marker)**, **tiền phát hành**, **update**, **build**, **optional metadata**, cùng các chuỗi hợp lệ và sai cú pháp. Tất cả những API được dùng ở đây vẫn tồn tại trong Java hiện hành.

### Kết quả mong đợi

Sau bài, bạn có thể:

1. Parse version string bằng `Runtime.Version.parse` và đọc các trường có ý nghĩa.
2. Biết khi nào `pre().isPresent()` thể hiện một dấu hiệu tiền phát hành.
3. Viết assertion về thứ tự `EA < phiên bản không có PRE` và `update > bản feature cùng dòng chưa update`.
4. So sánh đúng `compareTo` với `compareToIgnoreOptional`, không làm mất khác biệt của build number.
5. Kiểm thử các chuỗi invalid, các ranh giới cú pháp và giá trị số.
6. Không nhầm phép so phiên bản với chính sách LTS, SLA, bảo mật, giấy phép hoặc việc API có tương thích hay không.

## 2. Phân tích cấu trúc version string hiện hành

Theo Javadoc hiện hành của `Runtime.Version` và JEP 322, version number `$VNUM` là dãy số phân tách bằng dấu chấm. Bốn thành phần chính có ý nghĩa:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

| Thành phần | Nghĩa | Ví dụ trong `27.0.1+9` |
| --- | --- | --- |
| `FEATURE` | Bộ đếm feature release; tăng theo mỗi lần phát hành dòng tính năng | `27` |
| `INTERIM` | Bộ đếm interim release nếu có | `0` |
| `UPDATE` | Bộ đếm bản cập nhật tương thích, sửa lỗi/bảo mật/hồi quy | `1` |
| `PATCH` | Bộ đếm bản vá khẩn cấp nếu có | `0` (không xuất hiện) |

**Các thành phần bằng 0 ở cuối được lược bỏ** trong representation chuẩn. Ví dụ:

```text
27            -> feature 27, các thành phần còn lại = 0
27.0.1        -> feature 27, interim 0, update 1
27.0.1.2      -> feature 27, interim 0, update 1, patch 2
```

Không được mặc định các chuỗi `27.0` hoặc `27.0.0` là cách viết thay thế hợp lệ của `27`: version number **không được kết thúc bằng phần tử 0**. `Runtime.Version.parse("27.0")` ném `IllegalArgumentException`.

Nếu component thiếu, accessor `interim()`, `update()`, `patch()` trả `0`. Không cần truy cập thủ công phần tử của `version()` để tự đoán chỉ số.

### 2.1. Phần hậu tố: `PRE`, `BUILD` và `OPT`

Một phiên bản có thể chứa các nhóm thông tin bổ sung:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
```

Ý nghĩa:

- `$PRE`: pre-release identifier, ví dụ `ea` hoặc `internal`; truy cập bằng `pre()`.
- `$BUILD`: build number có dạng số nguyên không âm, truy cập bằng `build()`.
- `$OPT`: thông tin build tùy chọn, ví dụ `LTS`, truy cập bằng `optional()`.

Ví dụ:

| Chuỗi | `feature()` | `update()` | `pre()` | `build()` | `optional()` |
| --- | ---: | ---: | --- | ---: | --- |
| `27-ea+5` | 27 | 0 | `ea` | 5 | rỗng |
| `27+1` | 27 | 0 | rỗng | 1 | rỗng |
| `27.0.1+9` | 27 | 1 | rỗng | 9 | rỗng |
| `25.0.5+8-LTS` | 25 | 5 | rỗng | 8 | `LTS` |
| `27` | 27 | 0 | rỗng | rỗng | rỗng |

Hai cách viết sau **không cùng nghĩa**:

```text
27-ea     : có PRE là ea
27+-ea    : không có PRE, có OPT là ea
```

**Không xác định pre-release bằng việc kiểm tra cả chuỗi có chứa chữ `ea`.** Hãy dùng `pre()` vì chuỗi metadata tùy chọn cũng có thể chứa các ký tự trùng tên.

### 2.2. `version()` là dãy số, không phải mọi metadata

```java
Runtime.Version v = Runtime.Version.parse("27.0.1+9");
System.out.println(v.version()); // [27, 0, 1]
```

`version()` trả về danh sách **không sửa được** các phần tử số phiên bản. Nó **không bao gồm** build, pre-release hay optional metadata. Không sửa danh sách này và không suy đoán rằng số phần tử luôn là 4.

### 2.3. Vì sao không dùng tên accessor cũ?

Các method tên cũ `major()`, `minor()`, `security()` đã được **deprecated từ Java 10** do scheme hiện hành có nghĩa khác. Với code mới, chọn `feature()`, `interim()`, `update()`, `patch()`, đều là API còn được hỗ trợ hiện nay.

Điều này liên quan trực tiếp tới Special Note: **không giới thiệu các accessor deprecated như lựa chọn khuyến nghị cho project mới**.

## 3. Định nghĩa bài kiểm thử trước khi viết code

Trước khi sử dụng `compareTo`, hãy xác định bạn muốn thử **chính sách nào**:

| Tình huống | Assertion phù hợp | Điều KHÔNG được suy ra |
| --- | --- | --- |
| Parse phiên bản tiền phát hành | `pre().orElse("").equals("ea")` | Bản build có/không có hỗ trợ thương mại |
| Parse version không có PRE | `pre().isEmpty()` | File thực sự đã được công bố GA bởi một vendor |
| So sánh EA và bản không PRE có cùng `VNUM` | `ea.compareTo(noPre) < 0` | Mọi tag chứa `ea` đều là pre-release |
| Kiểm tra update | `v.update() == 1` | Bản đó chắc chắn đã vá toàn bộ CVE |
| So cùng dòng: update 1 và feature chưa update | `updated.compareTo(base) > 0` | Các distribution khác nhau hỗ trợ dài/ngắn ra sao |
| So build `+2` và `+1` | `b2.compareTo(b1) > 0` | Build number lớn hơn luôn bảo mật hơn |
| Bỏ qua metadata `OPT` | `compareToIgnoreOptional` và `equalsIgnoreOptional` | Bỏ luôn build number hoặc PRE |
| Parse đầu vào không hợp lệ | Bắt đúng `IllegalArgumentException` | Mọi byte/chuỗi tự do đều hợp lệ nếu có chữ số |

**Quan trọng:** từ “GA” (*general availability*) là thông tin về trạng thái phát hành thực tế. Một chuỗi parse được mà **không có PRE** là **điều kiện kiểm tra về biểu diễn**, không tự xác thực rằng binary ấy đã qua quy trình GA của nhà cung cấp. Nếu cần xác minh release thật, đối chiếu artifact, checksum/signature, release notes và nguồn phát hành chính thức.

## 4. Kiểm thử phiên bản chính thức và tiền phát hành

### 4.1. Dấu `ea` là pre-release marker

```java
var ea = Runtime.Version.parse("27-ea+5");

System.out.println(ea.pre().orElse("none")); // ea
System.out.println(ea.build().orElse(-1));   // 5
```

Các accessors trả kiểu `Optional` vì một version string **có thể không chứa** dữ liệu tương ứng. Khi không có PRE, `pre()` là `Optional.empty()`, không phải chuỗi literal `"GA"`.

### 4.2. Phiên bản không có PRE

```java
var release = Runtime.Version.parse("27+1");

System.out.println(release.pre().isEmpty()); // true
```

Trong nội dung bài, `release` là **chuỗi mô phỏng bản chính thức không có PRE**, không phải xác nhận rằng build `27+1` là bản phát hành cụ thể của một vendor.

### 4.3. Pre-release đứng trước bản không PRE cùng version number

```java
var ea = Runtime.Version.parse("27-ea+5");
var released = Runtime.Version.parse("27+1");

System.out.println(ea.compareTo(released) < 0); // true
```

Theo `Runtime.Version.compareTo`: **nếu các phần số phiên bản bằng nhau**, phiên bản **có PRE** luôn nhỏ hơn phiên bản **không có PRE**. Vì vậy một EA build có `+5` vẫn đứng trước bản không PRE có `+1`; đừng so build number trước pre-release.

**Thứ tự ưu tiên:** so phần số phiên bản → so PRE → so BUILD → so OPT.

### 4.4. PRE số và PRE chữ có quy tắc so khác nhau

```java
var numeric2 = Runtime.Version.parse("27-2");
var numeric10 = Runtime.Version.parse("27-10");
var text = Runtime.Version.parse("27-ea");

System.out.println(numeric2.compareTo(numeric10) < 0); // true
System.out.println(numeric2.compareTo(text) < 0);      // true
```

- Nếu **cả hai PRE đều chỉ chứa chữ số**, chúng được so **theo giá trị số**, nên 2 nhỏ hơn 10.
- PRE **chỉ số** nhỏ hơn PRE **không chỉ số**.
- Với PRE không phải dạng toàn số, dùng so sánh theo quy tắc **lexicographic** của API.

Không sắp thứ tự các pre-release strings bằng `String.compareTo` và hy vọng ra cùng kết quả cho mọi tình huống.

### 4.5. Một số hiểu nhầm về `ea`

`Runtime.Version.parse("27-ea+5")` không chạy hay tải EA binary. Nó chỉ parse một chuỗi. Tương tự, `Runtime.Version.parse("27")` không chứng minh trong năm 2026 đã có hay chưa có artifact `27` ở một kho tải xuống.

Với runtime thực đang chạy, dùng `Runtime.version()` để lấy version đã được nhúng vào bản build. Thông tin phân phối/tiền phát hành nên được kiểm tra thêm bằng `java --version`, metadata của vendor và release notes.

## 5. Kiểm thử bản cập nhật và emergency patch

### 5.1. Update number không phải build number

```java
var updated = Runtime.Version.parse("27.0.1+9");

System.out.println(updated.feature()); // 27
System.out.println(updated.interim()); // 0
System.out.println(updated.update());  // 1
System.out.println(updated.patch());   // 0
System.out.println(updated.build().orElse(-1)); // 9
```

`update=1` và `build=9` là **hai thành phần khác nhau**. Bản `+9` chưa chắc có update number 9; nó có thể là build thứ 9 của một release với update number 1.

### 5.2. Update có ưu tiên trước build

```java
var base = Runtime.Version.parse("27+99");
var update1 = Runtime.Version.parse("27.0.1+1");

System.out.println(update1.compareTo(base) > 0); // true
```

Phần số version được so trước. Vì vậy `27.0.1` lớn hơn `27`, dù build number của `27+99` cao hơn. Không so các chuỗi version bằng cách lấy số `BUILD` lớn nhất.

### 5.3. Patch number là một thành phần có nghĩa

```java
var update = Runtime.Version.parse("27.0.1+9");
var patched = Runtime.Version.parse("27.0.1.1+1");

System.out.println(patched.patch());             // 1
System.out.println(patched.compareTo(update) > 0); // true
```

`PATCH` dành cho emergency patch release theo mô hình Java 10+. Nó đứng sau `UPDATE` trong thứ tự các phần số phiên bản; **không đồng nghĩa mọi bản vá bảo mật đều bắt buộc tăng `PATCH`**. Các bản cập nhật bình thường có thể sửa lỗi bảo mật trong thành phần `UPDATE`.

### 5.4. Không dùng so phiên bản thay cho kiểm toán bản vá

`Runtime.Version.compareTo` chỉ so **các chuỗi version theo quy tắc Java**. Nó không biết:

- CVE nào đã được một vendor backport;
- dòng LTS nào còn được cung cấp quarterly updates;
- binary của vendor A và vendor B có cùng lịch bản vá hay không;
- policy, SLA, support entitlement, license;
- image đang chạy có dùng đúng bản update đã được phê duyệt hay không.

Muốn đánh giá security posture, phải kết hợp thông tin version/build với **advisory và release notes chính thức của chính nhà cung cấp**.

## 6. So sánh build number: một chi tiết dễ bỏ qua

Khi số phiên bản và PRE giống nhau, `compareTo` xem xét build:

```java
var noBuild = Runtime.Version.parse("27");
var build1 = Runtime.Version.parse("27+1");
var build2 = Runtime.Version.parse("27+2");

System.out.println(noBuild.compareTo(build1) < 0); // true
System.out.println(build2.compareTo(build1) > 0);  // true
```

Theo Java API:

1. Phiên bản **không có build number** được xem là nhỏ hơn phiên bản **có build number** khi các thành phần trước bằng nhau.
2. Nếu cả hai có build number, so theo **giá trị số**.
3. `+0` là build number **hợp cú pháp**; đừng đánh đồng “có build 0” với “không có build”.
4. Build number **không phải** ngày phát hành, số update hay cam kết hỗ trợ.

Điều này có nghĩa một kiểm tra `compareTo(...) > 0` có thể đúng **chỉ do build khác nhau**, chứ không phải do một feature hay update mới. Khi viết version gates, cần quyết định rõ có tính build number hay không.

## 7. Optional build information: vì sao có hai phép so sánh?

Giả sử có hai version strings:

```text
25.0.5+8-LTS
25.0.5+8-CUSTOM
```

Hai chuỗi này giống hoàn toàn về `FEATURE.INTERIM.UPDATE.PATCH` và `BUILD`; **chỉ khác `OPT`**.

### 7.1. So đầy đủ: `compareTo` và `equals`

```java
var lts = Runtime.Version.parse("25.0.5+8-LTS");
var custom = Runtime.Version.parse("25.0.5+8-CUSTOM");

System.out.println(lts.equals(custom)); // false
System.out.println(lts.compareTo(custom) == 0); // false
```

Hợp đồng `compareTo` tính cả optional build information; nếu phần trước bằng nhau, `OPT` được so lexicographic. Từ ví dụ không nên suy ra bản build nào “tốt” hơn chỉ vì chữ `LTS` và `CUSTOM` có thứ tự chữ cái khác nhau.

### 7.2. Bỏ qua chỉ `OPT`: `compareToIgnoreOptional` và `equalsIgnoreOptional`

```java
System.out.println(lts.equalsIgnoreOptional(custom));         // true
System.out.println(lts.compareToIgnoreOptional(custom) == 0); // true
```

Điều quan trọng là **chỉ `OPT` bị bỏ qua**. Các thành phần version number, PRE và BUILD **vẫn được xét**. Không mô tả `compareToIgnoreOptional` thành “chỉ so major version”.

Nếu yêu cầu là hai runtime có **cùng chính xác feature/update/build nhưng vendor-specific optional label khác nhau**, phương thức này có thể hữu ích.

### 7.3. Vì sao phải dùng cặp nhất quán?

Javadoc khuyến nghị ghép:

- `compareTo` với `equals`;
- `compareToIgnoreOptional` với `equalsIgnoreOptional`.

Nếu bạn tạo một `TreeSet<Runtime.Version>` với comparator bỏ qua optional, hai phiên bản khác `OPT` có thể được xem là **cùng key** về thứ tự so sánh. Trong khi đó, `HashSet` và `HashMap` dựa vào `equals`/`hashCode` đầy đủ, không tự áp dụng `equalsIgnoreOptional`.

Đừng dùng một phép `equalsIgnoreOptional` tự phát rồi mặc định các collection bình thường cũng xem hai object giống nhau. Khi cần một khóa nghiệp vụ chỉ gồm feature/update/build, hãy định nghĩa **kiểu khóa riêng** với equality/hash phù hợp.

## 8. `LTS` trong version string: metadata chứ không phải API hỗ trợ

`LTS` có thể xuất hiện trong phần `OPT`:

```java
var version = Runtime.Version.parse("25.0.5+8-LTS");

System.out.println(version.optional().orElse("none")); // LTS
```

Nhưng **không có API `Runtime.Version.isSupportedByVendor()`** hay một kết quả tự động cho biết thời hạn bảo trì. `LTS` trong version string là thông tin implementor có thể gắn vào bản build, không phải chứng chỉ hỗ trợ trả phí.

Để xác định một dòng Java có phù hợp cho deployment:

- xác nhận **distribution/vendor** (Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, v.v.);
- kiểm tra dòng LTS/non-LTS và **lịch EOL của đúng nhà cung cấp**;
- kiểm tra **update/build thực tế** đã chứa bản vá nào;
- kiểm tra **OS/architecture**, license và support entitlement;
- đối chiếu policy tại thời điểm triển khai.

Một feature version mới nhất không nhất thiết là dòng có **horizon hỗ trợ dài nhất**. Thông tin này nằm ngoài hợp đồng của `Runtime.Version`.

## 9. Kiểm thử parse đầu vào sai cú pháp

`Runtime.Version.parse(String)` có hợp đồng lỗi rõ ràng:

- `IllegalArgumentException`: chuỗi không thể hiểu thành version string hợp lệ.
- `NullPointerException`: đối số là `null`.
- `NumberFormatException`: phần số version/build không biểu diễn được bằng `Integer`.

`NumberFormatException` là lớp con của `IllegalArgumentException`, nhưng khi phân loại lỗi input theo nguyên nhân, nên cân nhắc ba tình huống này.

### 9.1. Các trường hợp invalid cơ bản

| Input | Nguyên nhân |
| --- | --- |
| `27.0` | Version number kết thúc bằng phần tử 0 |
| `027` | Có số 0 đứng đầu phần tử số version |
| `27..1` | Có component trống giữa hai dấu chấm |
| `27-ea+` | Có dấu `+` mà không có build number hợp lệ |
| `27-ea+abc` | Build number không phải số |
| `-ea` | Thiếu phần version number |
| chuỗi rỗng | Không có feature number |
| `null` | Không phải String object; ném `NullPointerException` |

**Không gộp tất cả thành một kiểu lỗi duy nhất nếu hợp đồng ứng dụng cần phân biệt null input và malformed input.**

### 9.2. Viết hàm kiểm thử mong đợi bị từ chối

```java
private static void rejected(String value) {
    try {
        Runtime.Version.parse(value);
        throw new AssertionError("Expected invalid: " + value);
    } catch (IllegalArgumentException expected) {
        System.out.println("REJECT " + value);
    }
}
```

Phương thức này **cố ý chỉ nhận các input kỳ vọng ném `IllegalArgumentException`**. Do `AssertionError` **không phải** `IllegalArgumentException`, nếu parser chấp nhận chuỗi invalid, test sẽ thất bại đúng cách thay vì nuốt mất lỗi assertion.

Với `null` nên dùng một bài test riêng:

```java
try {
    Runtime.Version.parse(null);
    throw new AssertionError("Expected NullPointerException");
} catch (NullPointerException expected) {
    System.out.println("nullRejected=true");
}
```

Đây là đoạn trong phương thức; chương trình ở phần 11 tập trung các trường hợp invalid string ngắn và dùng đúng bốn input đã xác minh.

### 9.3. Kiểm tra overflow riêng

Nếu một phần tử số quá lớn so với `Integer.MAX_VALUE`, parser có thể ném `NumberFormatException` theo hợp đồng. Khi xây endpoint nhận version string từ bên ngoài, đừng giả định chuỗi chỉ gồm chữ số là an toàn; cần giới hạn độ dài và xử lý lỗi parse phù hợp.

**Không dùng `Runtime.Version.parse` để parse semantic versioning tùy ý của thư viện khác.** Cú pháp của `Runtime.Version` là Java platform version-string scheme, không phải bộ parse SemVer tổng quát cho `1.2.3-beta.4+metadata` của một gói bất kỳ.

## 10. Xây dựng bộ kiểm thử có ý nghĩa

Một test tốt cần kiểm tra cả **nguyên nhân** và **kết quả**, không chỉ in version string.

### 10.1. Kiểm thử có giá trị ổn định

Hãy dùng các chuỗi phiên bản **cố định do test tạo ra**:

```java
Runtime.Version.parse("27-ea+5");
Runtime.Version.parse("27+1");
Runtime.Version.parse("27.0.1+9");
```

Vì dữ liệu do test kiểm soát, các assertion từ `Runtime.Version` ổn định trên JDK tuân theo cùng API. Không phụ thuộc version thực của máy CI hay vendor.

### 10.2. Kiểm thử runtime thực tế nhưng tránh expected value cố định

```java
Runtime.Version running = Runtime.version();
System.out.println(running.feature() >= 17);
```

Trong một bộ test chạy trên **JDK 17+**, dòng trên in `true`, nhưng nó **không cố định feature number là 17** vì CI có thể chạy JDK 21, 25 hoặc 27.

Nếu test có yêu cầu cụ thể, ví dụ “chỉ chạy với Java 21+”, dùng `feature() >= 21` kết hợp công cụ build cấu hình runtime thích hợp. Không suy rằng `feature() >= 21` đủ xác nhận mọi API/feature đang bật, đặc biệt với preview/incubator modules.

### 10.3. Kiểm thử version gate mà không nuốt lỗi

Một helper làm fail-fast:

```java
static void requireFeatureAtLeast(int minimumFeature) {
    var runtime = Runtime.version();
    if (runtime.feature() < minimumFeature) {
        throw new IllegalStateException(
                "Requires Java " + minimumFeature
                + "+, running " + runtime);
    }
}
```

Đây là method minh họa, không phải toàn bộ chương trình. Nó chỉ kiểm tra **feature counter**; nếu hệ thống đòi một **update release** đã vá lỗi, cần thêm yêu cầu version và vendor-specific advisory, không nên chỉ dùng helper này.

### 10.4. Hạn chế so trực tiếp chuỗi

**Sai:**

```java
boolean newer = "27.0.1".compareTo("27") > 0;
```

Có những cặp chuỗi đơn giản cho kết quả vô tình đúng, nhưng không thể dựa vào thứ tự từ điển khi có version components số. Ví dụ string `"27-10"` và `"27-2"` có thứ tự lexicographic khác thứ tự **numeric PRE** theo `Runtime.Version`.

**Đúng:**

```java
boolean newer = Runtime.Version.parse("27.0.1")
        .compareTo(Runtime.Version.parse("27")) > 0;
```

Phép so này tuân theo hợp đồng Java thay vì logic chuỗi tự chế.

## 11. Chương trình Java 17+ độc lập: test GA, EA, update, build, optional và parse lỗi

Lưu toàn bộ mã trong file **`RuntimeVersion293.java`**:

```java
import java.util.List;

public class RuntimeVersion293 {
    private static void ok(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println("PASS " + name);
    }

    private static void rejected(String value) {
        try {
            Runtime.Version.parse(value);
            throw new AssertionError("Expected invalid: " + value);
        } catch (IllegalArgumentException expected) {
            System.out.println("REJECT " + value);
        }
    }

    public static void main(String[] args) {
        var ea = Runtime.Version.parse("27-ea+5");
        var ga = Runtime.Version.parse("27+1");
        var update = Runtime.Version.parse("27.0.1+9");
        var lts = Runtime.Version.parse("25.0.5+8-LTS");
        var sameBase = Runtime.Version.parse("25.0.5+8-CUSTOM");

        ok("eaMarker", ea.pre().orElse("").equals("ea"));
        ok("gaHasNoPre", ga.pre().isEmpty());
        ok("eaBeforeGa", ea.compareTo(ga) < 0);
        ok("updateAfterGa", update.compareTo(ga) > 0);
        ok("updateNumbers", update.feature() == 27 && update.interim() == 0
                && update.update() == 1 && update.patch() == 0);
        ok("buildPresent", update.build().orElse(-1) == 9);
        ok("versionList", update.version().equals(List.of(27, 0, 1)));
        ok("missingBuildLess", Runtime.Version.parse("27").compareTo(ga) < 0);
        ok("numericPre", Runtime.Version.parse("27-2").compareTo(Runtime.Version.parse("27-10")) < 0);
        ok("numericVsTextPre", Runtime.Version.parse("27-2").compareTo(Runtime.Version.parse("27-ea")) < 0);
        ok("buildOrder", Runtime.Version.parse("27+2").compareTo(Runtime.Version.parse("27+1")) > 0);
        ok("strictDifferentOptional", !lts.equals(sameBase));
        ok("strictComparisonOptional", lts.compareTo(sameBase) != 0);
        ok("ignoreOptionalEqual", lts.equalsIgnoreOptional(sameBase));
        ok("ignoreOptionalComparison", lts.compareToIgnoreOptional(sameBase) == 0);
        ok("ltsIsMetadata", lts.optional().orElse("").equals("LTS"));
        ok("eaBuild", ea.build().orElse(-1) == 5);
        ok("runtimeAtLeast17", Runtime.version().feature() >= 17);
        rejected("27.0");
        rejected("027");
        rejected("27..1");
        rejected("27-ea+");
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac --release 17 -encoding UTF-8 RuntimeVersion293.java
java RuntimeVersion293
```

**Stdout chính xác:**

```text
PASS eaMarker
PASS gaHasNoPre
PASS eaBeforeGa
PASS updateAfterGa
PASS updateNumbers
PASS buildPresent
PASS versionList
PASS missingBuildLess
PASS numericPre
PASS numericVsTextPre
PASS buildOrder
PASS strictDifferentOptional
PASS strictComparisonOptional
PASS ignoreOptionalEqual
PASS ignoreOptionalComparison
PASS ltsIsMetadata
PASS eaBuild
PASS runtimeAtLeast17
REJECT 27.0
REJECT 027
REJECT 27..1
REJECT 27-ea+
```

### Diễn giải bộ kiểm thử

- **`eaMarker` / `gaHasNoPre`:** kiểm tra sự có mặt của `PRE` bằng accessor, không tìm chuỗi thủ công.
- **`eaBeforeGa`:** dù EA có build `5` và chuỗi không PRE có build `1`, pre-release vẫn đứng trước.
- **`updateAfterGa` / `updateNumbers`:** update counter là một phần của version number, đứng trước build trong thứ tự so sánh.
- **`buildPresent` / `buildOrder` / `missingBuildLess`:** xác minh giá trị BUILD và hai quy tắc có/không có build.
- **`versionList`:** danh sách số phiên bản có ba phần `[27, 0, 1]`, không có `+9`.
- **`numericPre` / `numericVsTextPre`:** hai quy tắc của PRE dạng số.
- **`strictDifferentOptional` / `strictComparisonOptional`:** so đầy đủ có xét `LTS`/`CUSTOM`.
- **`ignoreOptionalEqual` / `ignoreOptionalComparison`:** hai version chỉ khác `OPT` có thể xem bằng nhau khi bỏ qua optional metadata.
- **`ltsIsMetadata`:** xác nhận `LTS` được lưu ở `optional()`, không phải một boolean SLA.
- **`eaBuild`:** pre-release vẫn có thể có build number.
- **`runtimeAtLeast17`:** kiểm tra environment thuộc JDK 17+, không hard-code số runtime cụ thể.
- **`REJECT ...`:** bốn chuỗi invalid thực sự bị từ chối; helper chỉ in `REJECT` sau khi bắt đúng ngoại lệ.

Chương trình dùng **API ổn định**, biên dịch với `javac --release 17` và không dùng preview. Những version strings `27-ea+5`, `27+1`, `27.0.1+9` chỉ là **test fixtures hợp cú pháp**, không xác nhận trạng thái phát hành thật của vendor.

## 12. Khi cần test trong JUnit hoặc CI

Với project có thư viện test như JUnit Jupiter, tư duy nên chuyển từ `System.out.println` sang các assertion tường minh:

```java
// Đoạn minh họa JUnit 5/Jupiter, KHÔNG phải file độc lập.
// Các imports @Test/assertTrue/assertThrows do dự án test cung cấp.

@Test
void prereleaseComesBeforeNoPrerelease() {
    var early = Runtime.Version.parse("27-ea+5");
    var noPre = Runtime.Version.parse("27+1");
    assertTrue(early.compareTo(noPre) < 0);
}

@Test
void malformedVersionIsRejected() {
    assertThrows(IllegalArgumentException.class,
            () -> Runtime.Version.parse("27.0"));
}
```

**Chú ý:** `@Test` và `assertThrows` không nằm trong Java SE; cần dependency JUnit và imports phù hợp. Đoạn minh họa ở phần này không phải chương trình runnable độc lập. Ví dụ Java SE thuần ở phần 11 không cần thư viện ngoài.

Các kiểm tra trong CI nên thuộc những nhóm khác nhau:

1. **Version parsing tests:** test parser và các fixture cố định, không phụ thuộc máy.
2. **Runtime feature checks:** xác nhận môi trường chạy/biên dịch có feature level phù hợp.
3. **Binary/security checks:** kiểm tra artifact thật, vendor build, checksum/advisory, không thay bằng `Runtime.Version.compareTo`.
4. **Compatibility tests:** chạy ứng dụng trên các JDK/distributions mục tiêu, kể cả thư viện, native code và modules liên quan.

### 12.1. Thử với bản tiền phát hành có chủ đích

Nếu pipeline thật sự thử trên EA build, hãy phân biệt:

- **Test parser:** parse một chuỗi `27-ea+5` ở bất kỳ runtime JDK17+; không cần cài EA JDK.
- **Test chương trình trên EA JDK:** khởi chạy bằng **binary EA thật** và kiểm tra `Runtime.version().pre()`, feature, build cũng như danh tính artifact.
- **Test behavior:** kiểm thử API/bytecode/runtime behavior thực sự trên build đó.

Bài test parser thành công không chứng minh chương trình của bạn đã được chạy trên EA build. **Đó là hai mục tiêu kiểm thử riêng biệt.**

### 12.2. Test khi nâng version

Khi nâng runtime từ một update sang update mới:

- xác minh số `FEATURE`/`UPDATE`/`BUILD` của bản thực;
- kiểm tra release notes và security advisories từ distribution đang dùng;
- chạy bộ test regression trên runtime mới;
- phân loại vấn đề API, thư viện, thay đổi cấu hình, locale data, TLS, GC hoặc module system;
- rollback có kiểm soát nếu cần, nhưng không giữ vô thời hạn một binary cũ thiếu security updates.

Không dùng quy tắc “`Runtime.Version.compareTo(old) > 0` thì mọi thứ đều an toàn” như một thay thế quy trình nghiệm thu.

## 13. Những ranh giới về so sánh và value-based class

### 13.1. `Runtime.Version` là value-based

Javadoc hiện hành mô tả `Runtime.Version` là **value-based class**. Lập trình viên nên coi các instance có giá trị bằng nhau là có thể thay thế lẫn nhau, không phụ thuộc reference identity.

**Không dùng:**

```java
var a = Runtime.Version.parse("27+1");
var b = Runtime.Version.parse("27+1");

// Không dùng a == b để kiểm tra phiên bản bằng nhau.
// Không dùng System.identityHashCode(a) làm version identifier.
// Không dùng synchronized (a) làm chiến lược đồng bộ hóa.
```

**Dùng:**

```java
System.out.println(a.equals(b)); // true
```

Nếu cần khóa đồng bộ, hãy dùng một object lock chuyên dụng thuộc quyền sở hữu của ứng dụng, không dùng đối tượng value-based.

### 13.2. `compareTo` dùng cho thứ tự phiên bản, không phải thước đo thời gian phát hành tuyệt đối

Hai build khác nhau có thể được dựng trong những môi trường khác nhau. Việc `compareTo` trả số dương chỉ mô tả **thứ tự theo scheme**, không xác nhận ngày phát hành hay bản vá nào được một vendor triển khai.

Nếu cần timeline thực, truy xuất metadata/release notes của artifact. Nếu cần ràng buộc business như `"đã duyệt tới update 25.0.5"`, phải gắn định danh vendor và chính sách cập nhật cụ thể.

### 13.3. `equalsIgnoreOptional` không đồng nghĩa một key hash

`equalsIgnoreOptional` bỏ qua `OPT`, nhưng `equals`/`hashCode` chuẩn của object vẫn là toàn bộ version string. Không dùng `equalsIgnoreOptional` làm logic duy nhất để lưu trữ khóa trong `HashMap` hoặc `HashSet` nếu kỳ vọng chúng nhập các phiên bản chỉ khác `OPT` thành một.

Khi cần khóa có equivalence khác, thiết kế một value object riêng (ví dụ các trường feature, interim, update, patch, pre, build) và triển khai equality/hash đồng nhất với yêu cầu.

## 14. Lỗi phổ biến

**Lỗi 1 — So trực tiếp chuỗi version bằng `String.compareTo`.**  
Với PRE dạng số, thứ tự từ điển và thứ tự số có thể khác nhau. `Runtime.Version.compareTo` có hợp đồng riêng.

**Lỗi 2 — Coi `27.0` là dạng đầy đủ của `27`.**  
Không đúng cú pháp Java version number hiện hành: không kết thúc bằng số 0.

**Lỗi 3 — Tìm chuỗi `"ea"` ở bất cứ đâu để xác định pre-release.**  
Một metadata `OPT` có thể chứa `ea`. Dùng `pre()`.

**Lỗi 4 — Coi `+9` là update 9.**  
`+9` là build number; update là phần thứ ba của version number.

**Lỗi 5 — So BUILD trước PRE hoặc UPDATE.**  
Sai với `Runtime.Version.compareTo`. So version-number, PRE, BUILD, rồi OPT.

**Lỗi 6 — Cho rằng `compareToIgnoreOptional` bỏ luôn BUILD.**  
Nó chỉ bỏ `OPT`. BUILD vẫn thuộc thứ tự được so.

**Lỗi 7 — Dùng `LTS` metadata như chứng chỉ hỗ trợ.**  
Nhãn build không tự xác định SLA, license, thời gian EOL hoặc bản vá bảo mật hiện tại.

**Lỗi 8 — Coi version string không có PRE là bằng chứng GA của vendor.**  
Parser chỉ biết cú pháp. Cần kiểm tra artifact/release notes chính thức.

**Lỗi 9 — Đoán kiểu exception của mọi input lỗi giống nhau.**  
Chuỗi malformed thường ném `IllegalArgumentException`; input `null` ném `NullPointerException`; số overflow có `NumberFormatException`.

**Lỗi 10 — Dùng `Runtime.Version` cho SemVer bất kỳ.**  
Cú pháp của Java runtime version không trùng mọi biến thể version của npm, Maven hoặc các thư viện khác.

**Lỗi 11 — Dựa vào `==` hoặc khóa đồng bộ `synchronized(version)`.**  
`Runtime.Version` là value-based; dùng equality theo giá trị và khóa đồng bộ riêng.

**Lỗi 12 — Test parser rồi tuyên bố đã test runtime mới.**  
`parse("27-ea+5")` không khởi chạy JDK 27 EA. Muốn test runtime mới phải thực sự chạy trên binary ấy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Runtime.Version.parse("27-ea+5").pre()` có giá trị gì?  
**Đáp án:** `Optional` chứa `"ea"`. `build()` chứa `5`.

**Câu 2.** `Runtime.Version.parse("27+1").pre().isEmpty()` có ý nghĩa gì?  
**Đáp án:** Chuỗi không có pre-release marker; chưa phải bằng chứng vendor đã phát hành artifact GA tương ứng.

**Câu 3.** Vì sao `27-ea+5` nhỏ hơn `27+1` theo `compareTo`?  
**Đáp án:** Cùng version number `27`, nhưng pre-release đứng trước phiên bản không có PRE; BUILD chỉ được so sau đó.

**Câu 4.** So `27.0.1+1` với `27+99` thì bản nào lớn hơn?  
**Đáp án:** `27.0.1+1` lớn hơn do update number 1, dù build của bản cơ sở là 99.

**Câu 5.** `27-2` và `27-10`, bên nào nhỏ hơn?  
**Đáp án:** `27-2` nhỏ hơn vì hai PRE đều là số và so numeric, không phải lexicographic.

**Câu 6.** Hai chuỗi `25.0.5+8-LTS` và `25.0.5+8-CUSTOM` có bằng nhau không?  
**Đáp án:** `equals` là `false` vì `OPT` khác. `equalsIgnoreOptional` là `true` vì phần còn lại giống nhau.

**Câu 7.** `Runtime.Version.parse("27.0")` sẽ làm gì?  
**Đáp án:** Ném `IllegalArgumentException` vì version number kết thúc bằng phần tử 0.

**Câu 8.** `Runtime.Version.parse(null)` có trả `Optional.empty()` không?  
**Đáp án:** Không. `parse` trả `Runtime.Version` hoặc ném ngoại lệ; `null` ném `NullPointerException`.

**Câu 9.** `compareToIgnoreOptional` có bỏ qua `+BUILD` không?  
**Đáp án:** Không. Nó chỉ bỏ phần metadata `OPT`.

**Câu 10.** Nếu `Runtime.version().feature() == 27`, có được kết luận runtime đó là LTS không?  
**Đáp án:** Không. Feature number không biểu diễn vòng đời hỗ trợ của vendor. Cần xem release channel và support policy của binary đang dùng.

## 16. Ghi nhớ

1. `Runtime.Version` là API parse và so sánh version strings của **Java platform**, đã có từ Java 9 và được cập nhật về tên accessor trong **Java 10/JEP 322**.
2. Dùng `feature()`, `interim()`, `update()`, `patch()`, `pre()`, `build()`, `optional()`; không dùng các accessor deprecated `major/minor/security` cho code mới.
3. Phân biệt **pre-release marker** với **metadata `OPT`**. `27-ea` và `27+-ea` có ý nghĩa khác nhau.
4. `compareTo` so lần lượt **số phiên bản → PRE → BUILD → OPT**. Cùng version number, bản có PRE nhỏ hơn bản không PRE.
5. Bản **update** khác **build** và **patch**. `27.0.1+9` có update 1 và build 9.
6. `compareToIgnoreOptional`/`equalsIgnoreOptional` **chỉ bỏ qua `OPT`**, phải dùng đúng cặp để giữ ngữ nghĩa nhất quán.
7. Kiểm thử malformed string bằng `IllegalArgumentException`, null input bằng `NullPointerException`, số vượt phạm vi `Integer` bằng `NumberFormatException` theo hợp đồng.
8. Kiểm thử parser trên fixture **không đồng nghĩa** đã kiểm thử binary JDK thực. Kiểm thử runtime và chính sách bảo trì/vendor là các bài toán khác.
9. `Runtime.Version` là **value-based class**: không dựa vào identity, không dùng làm lock.
10. Các kiến thức này vẫn áp dụng trên JDK hiện hành; code mẫu Java 17+ minh họa đúng cơ chế Java 10+, không đòi hỏi preview.

## Tài liệu tham khảo chính thức còn áp dụng

- OpenJDK JEP 322 — **Time-Based Release Versioning**, delivered in JDK 10: https://openjdk.org/jeps/322
- Java SE 26 API — **`Runtime.Version`**, cú pháp version, `pre/build/optional`, `compareTo`, `compareToIgnoreOptional`, `equalsIgnoreOptional`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html
- Java SE 27 API — **`Runtime.Version`** (kiểm tra các hợp đồng vẫn được hỗ trợ): https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.Version.html
- Java SE 26 API — **`Runtime.version()`**, runtime hiện tại: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html
- Oracle Java SE 26 Installation Guide — **Version-String Format**: https://docs.oracle.com/en/java/javase/26/install/version-string-format.html
- Oracle Java SE Support Roadmap — phân biệt feature release, LTS và lifecycle theo vendor: https://www.oracle.com/java/technologies/java-se-support-roadmap.html
