# `Runtime.version()` và phiên bản JVM đang chạy

*Chủ đề cha: `Runtime.Version` — Java 10. Bài học giải thích cách lấy, phân tích và sử dụng phiên bản của môi trường Java đang thực thi chính chương trình, phân biệt phiên bản Java runtime với phiên bản triển khai JVM và phiên bản JDK dùng để biên dịch. Ưu tiên các API vẫn áp dụng trong Java hiện đại; ví dụ hoàn chỉnh có thể biên dịch và chạy trên JDK 17 trở lên.*

## 1. Trả lời ngắn gọn: `Runtime.version()` là gì?

Lời gọi:

```java
Runtime.Version version = Runtime.version();
```

trả về một đối tượng kiểu **`java.lang.Runtime.Version`** mô tả **phiên bản Java Runtime Environment của tiến trình Java đang chạy**. Lớp `Runtime.Version` nằm trong `java.lang.Runtime`, nên có thể truy cập trực tiếp không cần `import`.

Nếu bạn chỉ cần biết **nhánh phiên bản Java** đang chạy để thực hiện một kiểm tra phù hợp, hãy dùng:

```java
int feature = Runtime.version().feature();
```

Ví dụ, khi tiến trình đang chạy trên JDK 17, `feature()` trả 17; khi chạy trên JDK 21, nó trả 21. Đây là những **ví dụ**, không phải giả định rằng chương trình của bạn đang chạy trên một phiên bản cố định. Mỗi lần triển khai hoặc mỗi máy có thể có runtime khác nhau.

**Phân biệt quan trọng:** Javadoc định nghĩa `Runtime.version()` là phiên bản **Java Runtime Environment**. Nó là câu trả lời thực dụng cho “Java nào đang chạy chương trình này?”, nhưng không phải tên chính xác của **triển khai JVM** hay toàn bộ chi tiết build JVM. Nếu muốn metadata về chính VM, hãy đọc thêm các system properties như `java.vm.name`, `java.vm.vendor` và `java.vm.version`.

`Runtime.version()` là **phương thức static**; không phải gọi trên một đối tượng `Runtime` do bạn tạo. `Runtime.getRuntime()` là API khác, dùng để lấy đối tượng môi trường thực thi phục vụ nhiều tác vụ tài nguyên/process. Bạn có thể dùng cú pháp `Runtime.version()` trực tiếp.

## 2. Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Hiểu `Runtime.version()` đọc phiên bản của **tiến trình Java hiện tại**, không phải mọi Java đã cài trên máy.
2. Phân biệt `Runtime.Version` với chuỗi `System.getProperty("java.version")` và `System.getProperty("java.vm.version")`.
3. Dùng các accessor hiện đại `feature()`, `interim()`, `update()`, `patch()`.
4. Hiểu sơ đồ số phiên bản Java 10+ theo JEP 322 và vì sao các phần cuối bằng 0 thường bị lược bỏ.
5. Đọc `pre()`, `build()`, `optional()` và `version()` đúng kiểu `Optional` và `List<Integer>`.
6. Phân tích chuỗi phiên bản hợp lệ bằng `Runtime.Version.parse(...)` và nhận biết chuỗi sai cú pháp.
7. So sánh số phiên bản bằng `compareTo` thay vì so sánh chuỗi theo thứ tự chữ cái.
8. Phân biệt pre-release, build number, optional build information và các phép so sánh bỏ qua optional information.
9. Xây dựng kiểm tra yêu cầu phiên bản tối thiểu nhưng không nhầm nó với khả năng tự động sử dụng API mà mã nguồn chưa biên dịch được.
10. Kiểm thử chương trình theo phiên bản thực tế, tránh expected output cố định vào một bản JDK của máy tác giả.

## 3. Bối cảnh Java 9 và Java 10

Một sự thật lịch sử cần nói **chính xác**:

- **`Runtime.version()` và `Runtime.Version` xuất hiện từ Java 9.**
- **Java 10** áp dụng cách đánh số thời gian theo **JEP 322 — Time-Based Release Versioning**, với các thành phần `FEATURE.INTERIM.UPDATE.PATCH`.
- Các accessor `feature()`, `interim()`, `update()`, `patch()` được bổ sung từ **Java 10**, và **đây là nhóm nên dùng** trong chương trình Java hiện đại.
- Những accessor cũ `major()`, `minor()`, `security()` đã **deprecated từ Java 10** vì tên không còn phản ánh ý nghĩa của sơ đồ mới. Không lấy chúng làm cách giảng dạy hoặc cách viết code mới.

Cần phân biệt “phương thức có từ lúc nào” với “cách đánh số phiên bản được cải tiến lúc nào”. Một bài học thuộc module Java 10 về `Runtime.Version` không có nghĩa phải tuyên bố toàn bộ API lần đầu xuất hiện trong Java 10.

### 3.1. Vì sao sơ đồ mới quan trọng?

Các giá trị `feature`, `interim`, `update` và `patch` mô tả **vai trò của một lần phát hành** chứ không đơn giản là “major/minor/security” như cách gọi lịch sử.

Ví dụ minh họa:

```text
17          -> feature 17, interim 0, update 0, patch 0
17.0.10     -> feature 17, interim 0, update 10, patch 0
17.0.10+7   -> như trên, kèm build number 7
21-ea+12    -> feature 21, pre-release "ea", build 12
```

Những chuỗi này **chỉ là phiên bản mẫu** để học; không ngụ ý máy đang chạy bản 17 hoặc 21.

## 4. Các thành phần phiên bản số

Định dạng khái quát từ Java 10:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

Bốn thành phần đầu có ý nghĩa:

| Thành phần | Accessor | Ý nghĩa |
| --- | --- | --- |
| `FEATURE` | `feature()` | Bộ đếm các bản feature release |
| `INTERIM` | `interim()` | Bộ đếm bản interim có thay đổi tương thích |
| `UPDATE` | `update()` | Bộ đếm các bản update sửa lỗi, bảo mật, regression |
| `PATCH` | `patch()` | Bộ đếm bản vá khẩn cấp |

Cả bốn accessor trả **`int`**. Nếu một thành phần không xuất hiện trong chuỗi phiên bản, accessor tương ứng trả **0** (ngoại trừ `feature` luôn hiện diện).

### 4.1. Không phải mọi thành phần bằng 0 đều xuất hiện trong chuỗi

Một version number hợp lệ **không có phần tử cuối bằng 0**. Vì vậy:

- `17` là hợp lệ, và có `interim() == 0`, `update() == 0`, `patch() == 0`.
- `17.0.10` là hợp lệ: số 0 ở giữa là cần thiết để xác định `update=10`.
- `17.0` hoặc `17.0.0` không phải cách viết hợp lệ của version number theo quy tắc `Runtime.Version.parse` vì các phần tử cuối đều bằng 0.
- `17.0.10.0` cũng có phần tử cuối bằng 0 và không phải version number hợp lệ.
- `17.0.10+7` là hợp lệ và chứa build number 7.

Đừng cắt chuỗi bằng `split("\\.")` rồi giả định luôn có bốn phần. Một phiên bản có thể chỉ có một thành phần số; một phiên bản khác lại có thêm `-ea` hoặc `+7`. Dùng accessor đã được định nghĩa để đọc thành phần cần thiết.

### 4.2. Version number không chỉ được phép có bốn số

Theo Javadoc, version number có thể có **nhiều hơn bốn thành phần**; từ phần tử thứ năm, cách sử dụng tùy nhà triển khai. Vì vậy không nên áp một regex chỉ nhận bốn phần rồi gọi mọi phiên bản khác là sai, khi `Runtime.Version` có thể biểu diễn một dãy số dài hơn.

`version()` trả `List<Integer>` của các phần tử số xuất hiện; nó không chèn số 0 bị lược bỏ vào cuối chỉ để danh sách có bốn phần.

## 5. Chương trình 1: hỏi phiên bản Java đang chạy mà không đóng đinh số hiệu

Tạo file **`RunningRuntimeDemo.java`**:

```java
public class RunningRuntimeDemo {
    public static void main(String[] args) {
        Runtime.Version running = Runtime.version();

        System.out.println("type="
                + running.getClass().getSimpleName());
        System.out.println("featureAtLeast17="
                + (running.feature() >= 17));
        System.out.println("componentsNonnegative="
                + (running.interim() >= 0
                && running.update() >= 0
                && running.patch() >= 0));
        System.out.println("featureIsFirstElement="
                + (running.version().get(0) == running.feature()));
        System.out.println("runtimeSpecMatchesFeature="
                + Integer.toString(running.feature()).equals(
                        System.getProperty("java.specification.version")));
        System.out.println("vmVersionPresent="
                + (System.getProperty("java.vm.version") != null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RunningRuntimeDemo.java
java RunningRuntimeDemo
```

Stdout trên Java SE 17+ được cấu hình thông thường, với các standard system properties nguyên trạng:

```text
type=Version
featureAtLeast17=true
componentsNonnegative=true
featureIsFirstElement=true
runtimeSpecMatchesFeature=true
vmVersionPresent=true
```

Giải thích:

1. `Runtime.version()` trả một `Runtime.Version`; tên lớp lồng là `Version`.
2. Vì ví dụ yêu cầu chạy Java 17+, `featureAtLeast17` là `true` bất kể runtime là 17, 21 hay một bản mới hơn.
3. Các thành phần phiên bản không âm; `feature()` là phần tử đầu tiên trong danh sách `version()`.
4. `java.specification.version` theo chuẩn Java hiện đại là **feature element** của phiên bản runtime, được biểu diễn bằng String.
5. `java.vm.version` là một system property tiêu chuẩn chứa phiên bản implementation của VM; ví dụ chỉ kiểm tra sự hiện diện, không đoán tên vendor và số build.

**Không cố định output thành `feature=17`** khi bài được biên dịch với `--release 17`. Tùy JDK dùng để chạy, `Runtime.version().feature()` có thể là số lớn hơn.

### 5.1. Nếu muốn in phiên bản thật trên máy

```java
var running = Runtime.version();

System.out.println("runtime=" + running);
System.out.println("feature=" + running.feature());
System.out.println("interim=" + running.interim());
System.out.println("update=" + running.update());
System.out.println("patch=" + running.patch());
System.out.println("pre=" + running.pre().orElse("none"));
System.out.println("build=" + running.build().map(Object::toString)
        .orElse("none"));
```

Đây là đoạn minh họa trong `main` hoặc method. **Không có stdout cố định đúng cho mọi máy**: một runtime có thể ở feature 17, runtime khác ở feature 21, bản early access có `pre()`, bản build khác có số build riêng. Đây mới là mục tiêu của `Runtime.version()`: **hỏi môi trường thật**, không trả chuỗi ví dụ.

## 6. `Runtime.Version` có các method gì?

| API | Kiểu trả về | Cách dùng |
| --- | --- | --- |
| `Runtime.version()` | `Runtime.Version` | Lấy phiên bản Java runtime của tiến trình hiện tại |
| `feature()` | `int` | Feature release, ví dụ 17 |
| `interim()` | `int` | Interim release hoặc 0 |
| `update()` | `int` | Update release hoặc 0 |
| `patch()` | `int` | Patch release hoặc 0 |
| `version()` | `List<Integer>` | Dãy thành phần số phiên bản |
| `pre()` | `Optional<String>` | Pre-release identifier, nếu có |
| `build()` | `Optional<Integer>` | Build number, nếu có |
| `optional()` | `Optional<String>` | Thông tin build bổ sung, nếu có |
| `toString()` | `String` | Chuỗi phiên bản dạng tiêu chuẩn |
| `Runtime.Version.parse(String)` | `Runtime.Version` | Parse chuỗi phiên bản hợp lệ |
| `compareTo(Version)` | `int` | So sánh theo quy tắc phiên bản, gồm optional info |
| `compareToIgnoreOptional(Version)` | `int` | So sánh không xét optional build information |
| `equals(Object)` | `boolean` | Bằng nhau theo version string |
| `equalsIgnoreOptional(Object)` | `boolean` | Bằng nhau khi bỏ qua optional build information |

**`major()`, `minor()` và `security()` vẫn có thể xuất hiện khi đọc code cũ, nhưng đã deprecated từ Java 10.** Khi viết ví dụ mới, nên dùng `feature()`, `interim()` và `update()`. Không nên gọi `security()` rồi diễn giải số đó là “mức độ bảo mật” của runtime: trong sơ đồ mới, thành phần thứ ba là bộ đếm bản update.

### 6.1. `version()` không phải chuỗi và không luôn dài bốn phần

```java
var v = Runtime.Version.parse("17.0.10+7");
System.out.println(v.version()); // [17, 0, 10]
```

Danh sách gồm ba số xuất hiện trong `VNUM`, không có số 0 `patch` ở cuối. `version()` trả danh sách **không cho phép sửa**; đừng cố `add` phần tử để “cập nhật” phiên bản. Muốn phân tích một phiên bản khác, tạo đối tượng mới bằng `parse`.

### 6.2. `pre()`, `build()` và `optional()` đều có thể vắng mặt

`Runtime.Version` không giả định mọi runtime đã có pre-release identifier, build number hoặc vendor optional text.

```java
var stable = Runtime.Version.parse("17.0.10+7");

System.out.println(stable.pre().orElse("none"));       // none
System.out.println(stable.build().orElse(-1));         // 7
System.out.println(stable.optional().orElse("none"));  // none
```

Tránh gọi `.get()` không kiểm tra trên `Optional` vì có thể ném `NoSuchElementException`. Với dữ liệu tùy chọn, dùng `orElse(...)` hoặc `ifPresent(...)` để hiển thị thông tin có điều kiện.

## 7. Phần số, pre-release, build và optional text

Một version string có thể mang thông tin ngoài phần số, theo dạng khái quát:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+- $OPT)?
```

Đây chỉ là sơ đồ để đọc các phần; khoảng trắng trong dòng cuối để dễ nhìn, **không** phải cú pháp literal hợp lệ. Ví dụ literal đúng là `17+-vendor` nếu muốn có optional build information mà không có build number.

| Đầu mục | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `VNUM` | `17.0.10` | Dãy các số phiên bản |
| `PRE` | `ea` | Nhận diện pre-release như early access |
| `BUILD` | `7` | Số build trong nhánh phát hành |
| `OPT` | `vendor.1` | Thông tin nhận diện build bổ sung |

Một số chuỗi hợp lệ để hiểu:

```text
17.0.10
17.0.10+7
21-ea
21-ea+12
17.0.10+7-vendor.1
17+-vendor.1
```

Đừng nhầm `optional()` là thông tin bắt buộc hoặc là “update number”. `optional` là text bổ sung theo sơ đồ version string; `update()` là phần số thứ ba của `VNUM`.

## 8. Chương trình 2: parse một phiên bản mẫu và đọc đúng thành phần

Tạo file **`ParsedVersionDemo.java`**:

```java
public class ParsedVersionDemo {
    public static void main(String[] args) {
        var version = Runtime.Version.parse("17.0.10+7");

        System.out.println("feature=" + version.feature());
        System.out.println("interim=" + version.interim());
        System.out.println("update=" + version.update());
        System.out.println("patch=" + version.patch());
        System.out.println("list=" + version.version());
        System.out.println("build=" + version.build().orElse(-1));
        System.out.println("pre=" + version.pre().orElse("none"));
        System.out.println("optional="
                + version.optional().orElse("none"));
        System.out.println("string=" + version);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ParsedVersionDemo.java
java ParsedVersionDemo
```

Stdout **cố định** vì ví dụ parse chuỗi literal, không đọc runtime thật:

```text
feature=17
interim=0
update=10
patch=0
list=[17, 0, 10]
build=7
pre=none
optional=none
string=17.0.10+7
```

Tại sao có thể viết stdout cố định ở đây nhưng không nên làm vậy ở demo `Runtime.version()`?

- `Runtime.Version.parse("17.0.10+7")` phân tích **đúng chuỗi được viết trong source**, nên giá trị của các thành phần có thể xác định trước.
- `Runtime.version()` hỏi runtime của máy chạy chương trình nên phụ thuộc môi trường.
- Cả hai trả cùng **kiểu** `Runtime.Version`, nhưng **nguồn dữ liệu** khác nhau.

**`parse` không đổi phiên bản JVM đang chạy.** Gọi `Runtime.Version.parse("99")` chỉ tạo một đối tượng mô tả version string “99”; không cài Java 99, không nâng phiên bản process và không làm API mới xuất hiện.

## 9. So sánh version bằng `compareTo`, không so sánh lexicographic

Một bẫy phổ biến là:

```java
String a = "17.0.9";
String b = "17.0.10";

// a.compareTo(b) so sánh ký tự, không phải version number.
```

So sánh String theo thứ tự chữ cái **không** cho ra thứ tự số phiên bản đúng trong mọi trường hợp: ở phần update, `"10"` và `"9"` có độ dài/chữ số khác nhau. Đừng dùng `String.compareTo` để xác định bản cập nhật mới hơn.

Đúng:

```java
var a = Runtime.Version.parse("17.0.9");
var b = Runtime.Version.parse("17.0.10");

boolean bIsNewer = b.compareTo(a) > 0;
```

`compareTo` so sánh các phần số theo giá trị số, sau đó xét pre-release, build và optional build information theo quy tắc Javadoc.

### 9.1. Pre-release đi trước bản chính thức

Một bản có `-ea` (early access) được xem là **thấp hơn** cùng version number không có pre-release identifier.

```java
var early = Runtime.Version.parse("21-ea+12");
var release = Runtime.Version.parse("21+12");

System.out.println(early.compareTo(release) < 0); // true
```

Cần dùng quy tắc version, không tự xóa `-ea` hoặc chỉ so `feature()` nếu yêu cầu thật sự là “bản ổn định”.

### 9.2. Build number cũng là thành phần được so sánh

Theo `Runtime.Version.compareTo`, một bản **không có build number** được coi là nhỏ hơn bản cùng các thành phần khác **có build number**; nếu cả hai có build number thì so số build. Phần `optional` có quy tắc so sánh riêng.

Nhưng **thứ tự phiên bản theo cú pháp không chứng minh một build của vendor nào đã chứa một bản vá bảo mật cụ thể**. Khi kiểm tra một CVE hoặc hỗ trợ vận hành, cần đối chiếu advisory, vendor và danh sách patch của chính bản phân phối.

## 10. `compareToIgnoreOptional` là một lựa chọn có chủ đích

Hai chuỗi:

```text
17.0.10+7-A
17.0.10+7-B
```

có cùng version number `17.0.10`, cùng build `7`, nhưng khác optional build information `A` và `B`.

Theo `Runtime.Version`:

- `equals(...)` xét cả thông tin optional nên hai Version **khác nhau**.
- `equalsIgnoreOptional(...)` bỏ qua trường `OPT`, nên hai Version **được xem bằng nhau**.
- `compareToIgnoreOptional(...)` cũng bỏ qua `OPT`, cho kết quả **0**.
- `compareTo(...)` có thể phân biệt hai optional text theo thứ tự.

### 10.1. Chương trình 3: so sánh số, early access và build

Tạo **`CompareVersionDemo.java`**:

```java
public class CompareVersionDemo {
    public static void main(String[] args) {
        var oldVersion = Runtime.Version.parse("17.0.9+9");
        var newVersion = Runtime.Version.parse("17.0.10+7");

        var early = Runtime.Version.parse("21-ea+12");
        var stable = Runtime.Version.parse("21+12");

        var buildA = Runtime.Version.parse("17.0.10+7-A");
        var buildB = Runtime.Version.parse("17.0.10+7-B");

        System.out.println("numeric="
                + (newVersion.compareTo(oldVersion) > 0));
        System.out.println("eaBeforeStable="
                + (early.compareTo(stable) < 0));
        System.out.println("equalsOptional="
                + buildA.equals(buildB));
        System.out.println("equalsIgnoreOptional="
                + buildA.equalsIgnoreOptional(buildB));
        System.out.println("compareIgnoreOptional="
                + buildA.compareToIgnoreOptional(buildB));
        System.out.println("compareOptional="
                + (buildA.compareTo(buildB) < 0));
    }
}
```

Chạy:

```bash
javac --release 17 CompareVersionDemo.java
java CompareVersionDemo
```

Stdout:

```text
numeric=true
eaBeforeStable=true
equalsOptional=false
equalsIgnoreOptional=true
compareIgnoreOptional=0
compareOptional=true
```

**Phân biệt:** `equalsIgnoreOptional` và `compareToIgnoreOptional` **chỉ bỏ qua trường optional build information**, không phải mọi thông tin ngoài `feature`. `build()` vẫn là thành phần có nghĩa; `pre()` vẫn có nghĩa. Nếu muốn chỉ hỏi “cùng feature release không?”, so trực tiếp `feature()`, không đổi ý nghĩa của các phương thức ignore-optional.

Khi dùng sorted collections như `TreeSet` hoặc `TreeMap`, hãy nhớ comparator quyết định thế nào là “cùng khóa” trong tập/map đó. Nếu chọn `compareToIgnoreOptional`, hai version chỉ khác `OPT` có thể bị coi là tương đương trong tập sắp xếp; chọn comparator theo nhu cầu thật. Không dùng `equalsIgnoreOptional` cùng `HashSet` thông thường rồi mong nó tự thay đổi hành vi `equals/hashCode`.

## 11. Chuỗi phiên bản sai định dạng và ngoại lệ từ `parse`

`Runtime.Version.parse(String)` không phải parser chung cho **mọi cách ghi phiên bản Java từ lịch sử hoặc mọi text in ra bởi vendor**. Nó nhận một **version string theo grammar `Runtime.Version`**.

Ví dụ:

| Chuỗi | Có parse hợp lệ? | Vì sao |
| --- | --- | --- |
| `17` | Có | Một feature element |
| `17.0.10+7` | Có | Dãy số và build hợp lệ |
| `21-ea+12` | Có | Pre-release và build hợp lệ |
| `17.0` | Không | Kết thúc bằng phần tử số 0 |
| `17.0.01` | Không | Phần tử `01` có số 0 đứng đầu |
| `1.8.0_362` | Không | Không thuộc grammar version string Java 10+ |
| `"Java version 17"` | Không | Có chữ và khoảng trắng không đúng dạng |
| `null` | Không | `parse(null)` ném `NullPointerException` |

Ngoài `IllegalArgumentException` cho chuỗi không thể hiểu, Javadoc còn tài liệu hóa `NumberFormatException` khi phần tử số hoặc số build vượt khả năng biểu diễn của `Integer`. Đây là một nhánh lỗi riêng cần biết khi xử lý input bên ngoài.

**Đừng** cố thay hết lỗi parse bằng cách cắt String thủ công rồi dùng `Integer.parseInt` cho mỗi thành phần: bạn sẽ phải tự tái hiện quy tắc pre-release, build và optional text.

### 11.1. Chương trình 4: bắt các định dạng không hợp lệ

Tạo file **`InvalidVersionDemo.java`**:

```java
import java.util.List;

public class InvalidVersionDemo {
    public static void main(String[] args) {
        for (var value : List.of(
                "17.0", "17.0.01", "1.8.0_362")) {
            try {
                Runtime.Version.parse(value);
                System.out.println("accepted=" + value);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected=" + value);
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 InvalidVersionDemo.java
java InvalidVersionDemo
```

Stdout:

```text
rejected=17.0
rejected=17.0.01
rejected=1.8.0_362
```

`NumberFormatException` là subclass của `IllegalArgumentException` nên cũng nằm trong nhánh catch này nếu gặp số vượt giới hạn. Ví dụ chỉ sử dụng đầu vào cố định để minh họa grammar; với input từ người dùng, nên có thông báo lỗi rõ và giới hạn kích thước đầu vào để tránh xử lý dữ liệu vô hạn.

## 12. `Runtime.version()` khác `System.getProperty("java.version")` như thế nào?

Hai cách phổ biến:

```java
Runtime.Version running = Runtime.version();

String property = System.getProperty("java.version");
```

| Tiêu chí | `Runtime.version()` | `System.getProperty("java.version")` |
| --- | --- | --- |
| Kiểu trả | `Runtime.Version` | `String` (hoặc `null` nếu property bị xóa/không còn) |
| Mục đích | Thông tin version có cấu trúc | Thuộc tính mô tả phiên bản Java runtime |
| Đọc `feature` | `running.feature()` | Cần parse chuỗi hợp lệ hoặc đọc specification property |
| So sánh bản cập nhật | `compareTo(...)` | Không nên so String trực tiếp |
| Nguồn giá trị | API runtime đang chạy | Bảng system properties có thể bị code thay đổi |
| Chi tiết VM implementation | Không phải API riêng về VM vendor | Xem thêm `java.vm.version`, `java.vm.name`, `java.vm.vendor` |

`System.getProperty(...)` hữu ích để log hoặc tương tác cấu hình, nhưng với kiểm tra version nên ưu tiên object có cấu trúc. Một ứng dụng có thể thay đổi system properties bằng `System.setProperty`; **đổi `java.version` sau khi khởi động không nâng cấp JVM**, không nạp runtime mới và không làm `Runtime.version()` trở thành phiên bản giả mà chương trình vừa ghi vào property.

### 12.1. Đọc tên, phiên bản và vendor của JVM

Các property tiêu chuẩn:

| Property | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản Java Runtime Environment |
| `java.specification.version` | Phiên bản specification, tương ứng feature element của runtime |
| `java.vm.version` | Phiên bản **implementation** của Java Virtual Machine |
| `java.vm.specification.version` | Phiên bản JVM specification; feature element của runtime |
| `java.vm.name` | Tên triển khai Java Virtual Machine |
| `java.vm.vendor` | Nhà cung cấp triển khai JVM |
| `java.vendor` | Nhà cung cấp runtime |
| `java.home` | Thư mục cài đặt Java runtime dùng trong tiến trình |

Ví dụ chương trình **`JvmPropertiesDemo.java`**:

```java
public class JvmPropertiesDemo {
    public static void main(String[] args) {
        System.out.println("runtime=" + Runtime.version());
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.vendor="
                + System.getProperty("java.vm.vendor"));
        System.out.println("java.home="
                + System.getProperty("java.home"));
    }
}
```

Chạy:

```bash
javac --release 17 JvmPropertiesDemo.java
java JvmPropertiesDemo
```

**Không có stdout chung chính xác cho mọi hệ thống.** Những dòng này phụ thuộc JDK/JRE đang chạy, nhà cung cấp, build và vị trí cài đặt. Bài giảng không in một mẫu “Java 17” rồi gọi đó là output bắt buộc.

**Cách diễn đạt chính xác:** `Runtime.version()` trả phiên bản **Java runtime** đang thực thi, thường dùng để xác định feature/update mà JVM của tiến trình đang phục vụ; `java.vm.version` là **chuỗi version riêng của implementation VM**. Chúng có thể có hình thức khác nhau, và không nên bắt buộc hai chuỗi bằng nhau.

## 13. Runtime đang chạy khác JDK đã dùng để biên dịch

Tình huống thực tế:

1. Trên máy phát triển, bạn dùng JDK 21 để gọi `javac --release 17`.
2. Bản `.class` được tạo theo mức tương thích Java 17.
3. Ở máy khác, cùng artifact chạy bằng Java 17, 21 hoặc runtime Java mới hơn khi tương thích.
4. `Runtime.version().feature()` phản ánh **runtime của process đó**, không phải JDK biên dịch và không phải con số `--release 17`.

**Một lệnh `javac --release 17` không khóa `Runtime.version().feature()` thành 17.** Nó là option biên dịch quyết định API và bytecode target Java 17 cho các mã nguồn được biên dịch, không ép máy chạy dùng JDK 17.

Ngược lại, nếu một class đã được biên dịch nhắm tới Java 21 nhưng được nạp bởi JVM chỉ hỗ trợ Java 17, có thể xảy ra `UnsupportedClassVersionError` ngay khi nạp, trước khi một đoạn code `if (Runtime.version().feature() >= 21)` trong class đó có cơ hội chạy.

### 13.1. Java dùng ở terminal có thể khác Java chạy dịch vụ

```bash
java -version
javac -version
```

Đây là lệnh chẩn đoán môi trường. Chúng có thể gọi executable được tìm thấy qua `PATH` của terminal hiện tại, trong khi service Java đã được khởi chạy từ một đường dẫn JDK khác, container image khác hoặc runtime khác.

Muốn biết Java **đang chạy ngay bên trong ứng dụng**, log `Runtime.version()` và khi cần `java.home`/`java.vm.*` ngay từ tiến trình đó. Đừng suy ra runtime service chỉ từ kết quả `java -version` trong một terminal độc lập.

### 13.2. Một host có nhiều tiến trình Java

`Runtime.version()` không tìm “Java mới nhất đã cài trên máy”. Nó không quét registry, `JAVA_HOME`, SDK manager hay nhiều thư mục cài Java. Mỗi process Java đã chạy có runtime gắn với nó; hai service trên cùng máy hoàn toàn có thể báo `Runtime.Version` khác nhau.

Để quan sát một process khác, cần công cụ giám sát/chẩn đoán hoặc telemetry của chính process đó; `Runtime.version()` trong ứng dụng A không phải API truy vấn mọi JVM khác đang chạy.

## 14. Kiểm tra phiên bản tối thiểu an toàn

Một số chức năng ứng dụng có thể yêu cầu feature release tối thiểu.

Ví dụ code chạy trên Java 17+:

```java
static void requireJava17OrLater() {
    int feature = Runtime.version().feature();
    if (feature < 17) {
        throw new IllegalStateException(
                "Requires Java 17+, running " + feature);
    }
}
```

Đoạn này là method minh họa cần đặt trong class. Nó chỉ kiểm tra điều kiện; không thể biến một JVM Java 11 thành Java 17 hoặc làm nó hiểu bytecode của Java 17.

Nếu mục tiêu là **tính năng API**, hãy kiểm tra version theo bản Java đã giới thiệu API và bảo đảm code biên dịch/chạy theo thiết kế của bạn. Trong ứng dụng mới vốn chỉ hỗ trợ Java 17+, kiểm tra lặp lại “>=17” ở mọi điểm có thể không cần thiết; cấu hình build/deploy mới là nguồn kiểm soát chính.

### 14.1. Kiểm tra update cụ thể

```java
Runtime.Version minimum =
        Runtime.Version.parse("17.0.10");

boolean meetsMinimum =
        Runtime.version().compareTo(minimum) >= 0;
```

Đây là cách so sánh *toàn bộ version* theo grammar `Runtime.Version`, không phải so chuỗi. Tuy nhiên, một yêu cầu thực tế như “đã vá CVE X” không chỉ là phép so sánh `17.0.10`; các bản phân phối vendor có thể backport fix, cách gắn patch khác nhau hoặc có build riêng. Khi quyết định về bảo mật, phải tham khảo vendor advisory và chính sách bản vá, không chỉ so phiên bản chung của Java.

Nếu chỉ muốn kiểm tra feature tối thiểu, `feature()` là đơn giản và ít bị chi tiết build ảnh hưởng hơn. Nếu muốn phân biệt prerelease, `compareTo` theo quy tắc version sẽ có ý nghĩa khác một phép chỉ so `feature()`.

### 14.2. Khả năng hỗ trợ tính năng không chỉ là con số feature

`Runtime.version().feature() >= 17` không chứng minh mọi class/module đều có sẵn, mọi preview feature đã bật, mọi native library đều tương thích hay mọi permission được cấp. Ví dụ:

- Một runtime image `jlink` có thể không chứa module bạn muốn dùng.
- Preview features có thể cần cờ bật và điều kiện biên dịch/chạy phù hợp.
- API của thư viện bên thứ ba phụ thuộc version thư viện, không tự đến từ Java feature.
- Một chức năng VM có thể phụ thuộc cấu hình cờ, kiến trúc CPU, provider hoặc môi trường.

**Version gate là một điều kiện cần có thể hữu ích, không phải phép kiểm tra mọi capability.** Với một khả năng cụ thể, kiểm tra module/API/config tương ứng và thử thao tác được hỗ trợ khi thích hợp.

### 14.3. Không dùng version gate để bao quanh code không biên dịch được

Ví dụ ý tưởng sau **không hoạt động** nếu bạn biên dịch với một `--release` không có API bạn tham chiếu:

```java
// Giả sử SomeFutureApi chỉ có ở phiên bản Java lớn hơn
if (Runtime.version().feature() >= 99) {
    SomeFutureApi.doSomething();
}
```

Đây là **mã giả để minh họa lỗi tư duy**, không phải Java SE class có thật. Compiler vẫn phải phân giải `SomeFutureApi` tại thời điểm biên dịch. Một điều kiện `if` không giấu được symbol chưa tồn tại hoặc bytecode không tương thích.

Nếu thực sự cần artifact chạy trên nhiều feature releases, hãy chọn chiến lược hỗ trợ tương thích rõ ràng: API phổ biến ở target thấp, adapter được tải có điều kiện, reflection khi hợp lý và có kiểm soát, hoặc multi-release JAR theo hợp đồng — không đơn thuần nhét API mới vào nhánh `if`.

## 15. Lỗi và ngoại lệ liên quan

| Tình huống | Điều cần biết |
| --- | --- |
| `Runtime.version()` | Trả đối tượng `Runtime.Version` của runtime hiện tại |
| `Runtime.Version.parse("17.0.10+7")` | Trả đối tượng phiên bản mẫu hợp lệ |
| `Runtime.Version.parse("17.0")` | `IllegalArgumentException` do version string không hợp lệ |
| `Runtime.Version.parse(null)` | `NullPointerException` |
| `parse` có phần số quá lớn | `NumberFormatException` theo hợp đồng |
| `v.pre().get()` khi không có pre-release | `NoSuchElementException` từ `Optional.get` |
| `v.version().add(999)` | `UnsupportedOperationException` vì danh sách không cho sửa |
| `v.compareTo(null)` | `NullPointerException` |
| `Runtime.version().feature()` | Trả feature của runtime, không phải bản compiler |
| `System.getProperty("java.vm.version")` | Trả metadata JVM dạng String, không phải `Runtime.Version` tự động |

### 15.1. `Runtime.Version` là value-based class

Javadoc mô tả `Runtime.Version` là một **value-based class**. Nên quan tâm đến **giá trị**, không lấy identity của đối tượng làm hợp đồng.

```java
var a = Runtime.Version.parse("17.0.10+7");
var b = Runtime.Version.parse("17.0.10+7");

System.out.println(a.equals(b)); // true
```

Không dùng `a == b` để kết luận phiên bản giống nhau; không dùng các đối tượng value-based làm monitor cho `synchronized`. Khi cần so sánh, dùng `equals` hoặc các comparator đã được API quy định.

### 15.2. Đừng thay system properties tiêu chuẩn để “giả lập” nâng cấp

```java
System.setProperty("java.version", "99");
```

Lời gọi này **không** thay runtime process. Nó chỉ làm thay đổi giá trị trong bảng property theo điều kiện môi trường. Java docs cảnh báo sửa standard system properties sau khởi động có thể cho kết quả không dự đoán được ở các API phụ thuộc những giá trị đó. Với test cần mô phỏng version, hãy tách logic so version thành hàm nhận đối tượng `Runtime.Version` đã được `parse`, thay vì sửa `java.version`.

## 16. Tách việc đọc runtime và kiểm thử chính sách

Một cấu trúc dễ test:

```java
// Đoạn minh họa trong một class:
static boolean supportsFeature(
        Runtime.Version actual, int minimumFeature) {
    return actual.feature() >= minimumFeature;
}
```

Ở production:

```java
boolean ok = supportsFeature(Runtime.version(), 17);
```

Trong test:

```java
boolean testOld = supportsFeature(
        Runtime.Version.parse("11.0.20"), 17); // false

boolean testNew = supportsFeature(
        Runtime.Version.parse("21.0.2"), 17);  // true
```

Đoạn code minh họa trong method. Cách này giúp test logic trên **version mẫu** mà không cần chạy lại trên một JVM cũ hoặc can thiệp property global. Nhưng để kiểm chứng **tương thích runtime thực tế**, vẫn nên chạy integration/build test trên các JDK đã công bố hỗ trợ.

Một lỗi thường gặp là dùng `Runtime.version()` trực tiếp ở mọi nơi, khiến bạn khó test các nhánh feature thấp hơn runtime máy phát triển. Tách phần phụ thuộc môi trường thành một điểm hoặc truyền `Runtime.Version` vào helper sẽ làm code dễ kiểm chứng.

## 17. Đọc phiên bản bằng dòng lệnh hay programmatic API?

| Mục tiêu | Công cụ/API | Giới hạn |
| --- | --- | --- |
| Hỏi runtime **ngay trong process** | `Runtime.version()` | Không nói gì về các process Java khác |
| Đọc tên/phiên bản VM cụ thể | `java.vm.name`, `java.vm.version` | Chuỗi phụ thuộc vendor/build |
| Xem JDK command được terminal dùng | `java -version` | Có thể khác runtime của service |
| Xem compiler trong terminal | `javac -version` | Không phải bằng chứng runtime của service |
| Biên dịch cho Java feature khác | `javac --release N` | Không ép JVM chạy thành phiên bản N |
| Phân tích version string đã có | `Runtime.Version.parse` | Chỉ parse grammar được API hỗ trợ |
| So sánh bản phát hành | `Runtime.Version.compareTo` | Không thay vendor compatibility policy |
| Nhận feature number | `Runtime.version().feature()` | Không tự xác nhận module/preview/library availability |

### 17.1. Logging chẩn đoán lúc khởi động

Ứng dụng có thể log một lần ở điểm startup:

```java
System.out.println("Java runtime: " + Runtime.version());
System.out.println("JVM: " + System.getProperty("java.vm.name"));
System.out.println("JVM version: "
        + System.getProperty("java.vm.version"));
```

Với production, dùng logger thay `System.out` theo tiêu chuẩn dự án. Thông tin vendor/build có thể hữu ích khi debug khác biệt môi trường. Tuy nhiên, log không nên kèm thêm toàn bộ environment variables, `java.class.path` hoặc đường dẫn chứa dữ liệu nhạy cảm nếu không cần.

## 18. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`Runtime.version()` ra phiên bản JDK đã dùng để compile.” | Không: trả phiên bản Java runtime **đang chạy** |
| “Chạy `javac --release 17` thì `Runtime.version().feature()` luôn là 17.” | Không: có thể chạy bytecode tương thích Java 17 trên runtime mới hơn |
| “`Runtime.version()` được tạo lần đầu ở Java 10.” | Sai: có từ Java 9; accessor/scheme hiện đại liên quan Java 10 |
| “`Runtime.version()` chỉ trả String.” | Sai: trả `Runtime.Version` |
| “`Runtime.Version.parse("21")` đổi JVM đang chạy thành Java 21.” | Sai: chỉ tạo một đối tượng phiên bản |
| “`major()/minor()/security()` là cách mới nên dùng.” | Sai: deprecated từ Java 10; dùng `feature()/interim()/update()` |
| “`17.0.10` có `interim==10`.” | Sai: `interim=0`, `update=10` |
| “`17` bắt buộc phải viết `17.0.0.0`.” | Sai: không cho phần tử cuối bằng 0 trong version number |
| “`version()` luôn có bốn phần tử.” | Sai: nó chỉ gồm các thành phần xuất hiện |
| “`pre()`/`build()` luôn present.” | Sai: là `Optional` |
| “Bản `21-ea` tương đương bản `21` chính thức.” | Không: pre-release so thấp hơn bản không có pre-release |
| “`String.compareTo` đủ để so bản 17.0.9 và 17.0.10.” | Không: hãy parse và compare theo số |
| “`compareToIgnoreOptional` bỏ qua cả build number.” | Không: chỉ bỏ qua optional build information |
| “`equalsIgnoreOptional` làm `HashSet` tự bỏ qua optional.” | Không: equals/hashCode mặc định của collection không được thay |
| “`java.version` và `java.vm.version` bắt buộc giống hệt.” | Không: hai system property có ý nghĩa khác nhau |
| “Có thể set `java.version=99` để ứng dụng chạy Java 99.” | Không: không nâng runtime |
| “`java -version` trong terminal mô tả mọi service Java trên host.” | Không: service có thể dùng JDK khác |
| “`feature>=N` bảo đảm mọi API, module, preview feature có sẵn.” | Không: cần kiểm tra target, module, cấu hình và triển khai |
| “Một phiên bản cao hơn chắc chắn đã vá mọi CVE.” | Không: cần thông tin advisory/vendor và patch thực tế |
| “Số build là update number.” | Không: `build()` và `update()` khác nhau |
| “`Runtime.Version` có thể sửa tại chỗ bằng danh sách `version()`.” | Không: danh sách không cho sửa |
| “Mọi version text của JDK 8 có thể đưa thẳng vào `parse`.” | Không: grammar mới không nhận mọi định dạng lịch sử |

## 19. Bài tập thực hành và lời giải

### Bài 1 — Runtime thật

```java
var version = Runtime.version();
var n = version.feature();
```

`n` đại diện cho gì?

**Đáp án:** feature release của **Java runtime đang chạy process này**. Không phải JDK biên dịch hay số Java cố định được hardcode.

### Bài 2 — Chuỗi mẫu

```java
var v = Runtime.Version.parse("17.0.10+7");
```

`v.feature()`, `v.interim()`, `v.update()`, `v.patch()`, `v.build()` là gì?

**Đáp án:** lần lượt `17`, `0`, `10`, `0`; `v.build()` là `Optional<Integer>` có giá trị 7. `v.version()` trả `[17, 0, 10]`.

### Bài 3 — Số 0 bị lược bỏ

`Runtime.Version.parse("17.0")` hợp lệ không?

**Đáp án:** không, vì thành phần cuối của version number là 0. Dùng `"17"` để biểu diễn feature 17 và các thành phần còn lại bằng 0.

### Bài 4 — Chuỗi và đối tượng

```java
var raw = System.getProperty("java.version");
var typed = Runtime.version();
```

Điểm khác nhau?

**Đáp án:** `raw` là `String` lấy từ system properties; `typed` là `Runtime.Version` có accessor và comparator. Không so chuỗi phiên bản lexicographic để quyết định thứ tự phát hành.

### Bài 5 — So sánh update

Giữa `17.0.9` và `17.0.10`, bản nào mới hơn?

**Đáp án:**

```java
var older = Runtime.Version.parse("17.0.9");
var newer = Runtime.Version.parse("17.0.10");

boolean newerIsGreater = newer.compareTo(older) > 0; // true
```

`Runtime.Version` so theo số, không theo chuỗi ký tự.

### Bài 6 — Early access

Bản `21-ea+12` so với `21+12` thế nào?

**Đáp án:** `Runtime.Version.parse("21-ea+12").compareTo(Runtime.Version.parse("21+12")) < 0` là `true`. Pre-release nhỏ hơn bản không có pre-release cùng phần số.

### Bài 7 — Bỏ optional build information

`17.0.10+7-A` và `17.0.10+7-B` có bằng nhau không?

**Đáp án:** `equals` trả false, `equalsIgnoreOptional` trả true, `compareToIgnoreOptional` trả 0. Build number `7` vẫn được xét; chỉ optional suffix khác được bỏ qua.

### Bài 8 — Version tối thiểu

Bạn muốn yêu cầu Java 17+ khi ứng dụng khởi động. Biểu thức phù hợp?

**Đáp án:** `Runtime.version().feature() >= 17`. Nó kiểm tra phiên bản runtime hiện tại; vẫn phải biên dịch với target phù hợp và có cấu hình triển khai đúng.

### Bài 9 — Kiểm tra VM vendor

`Runtime.version()` có cho biết chính xác tên JVM và vendor không?

**Đáp án:** không phải mục đích chính của API. Đọc `System.getProperty("java.vm.name")`, `java.vm.vendor`, `java.vm.version` để có metadata triển khai JVM; kết quả phụ thuộc vendor.

### Bài 10 — Bản build bảo mật

Bạn muốn xác nhận bản runtime đã vá một CVE quan trọng. Chỉ cần `feature() >= 17`?

**Đáp án:** không. Feature không nói bản update/build đã có bản vá cụ thể. Cần advisory của nhà phân phối, update/build tương ứng và kiểm tra cấu hình/vận hành.

### Bài 11 — Test chạy nhiều Java

Một artifact biên dịch `--release 17` được chạy trên Java 21. `Runtime.version().feature()` trả bao nhiêu?

**Đáp án:** trả `21` trên runtime Java 21 đó, không trả `17` chỉ vì target biên dịch. Nếu có sự cố khi tải class, kiểm tra class file version và compatibility trước.

### Bài 12 — Sửa system property

`System.setProperty("java.version","99")` có làm `Runtime.version().feature()` thành 99 không?

**Đáp án:** không. Thao tác trên chỉ thay một standard system property (và cũng không được khuyến khích để mô phỏng runtime). `Runtime.version()` mô tả runtime thực tế; muốn test logic phiên bản, truyền một `Runtime.Version.parse("99")` vào hàm test độc lập.

### Bài 13 — Optional build

`Runtime.Version.parse("17").build().get()` có an toàn?

**Đáp án:** không. `"17"` không có build number; `build()` là Optional rỗng, `get()` ném `NoSuchElementException`. Dùng `orElse(...)` hoặc `ifPresent(...)`.

### Bài 14 — Phân tích version lịch sử

Vì sao `Runtime.Version.parse("1.8.0_362")` không phải cách kiểm tra Java 8 tốt?

**Đáp án:** đây là chuỗi kiểu cũ, không hợp grammar `Runtime.Version` của Java 9+ / Java 10+; để tương thích Java 8 thật, phải có chiến lược build/runtime riêng, và bản Java 8 không có `Runtime.version()`.

## 20. Checklist trước khi dùng trong dự án

1. **Muốn biết Java của process hiện tại hay JDK cài trên máy?** `Runtime.version()` chỉ trả runtime process hiện tại.
2. **Muốn số feature hay toàn version?** Dùng `feature()` cho nhánh Java, `compareTo` nếu cần các phần khác.
3. **Đã phân biệt phiên bản Java runtime và phiên bản JVM implementation chưa?** Dùng `java.vm.*` khi cần VM cụ thể.
4. **Có hiểu `Runtime.version()` static không?** Không tạo `new Runtime()`.
5. **Có dùng accessor hiện đại không?** Ưu tiên `feature`, `interim`, `update`, `patch`; tránh deprecated `major`, `minor`, `security`.
6. **Có hardcode output của runtime vào test không?** Hãy kiểm tra invariant hoặc parse phiên bản mẫu.
7. **Có nhầm `--release` với Java dùng để chạy không?** Chúng là hai tầng riêng.
8. **Có so sánh bằng String.compareTo không?** Dùng `Runtime.Version.compareTo`.
9. **Có cần phân biệt prerelease không?** `pre()` và comparator quan trọng.
10. **Có cần build number không?** `build()` có thể rỗng.
11. **Có cần optional build metadata không?** `optional()` riêng với `update()`.
12. **Có dùng đúng cặp phương thức so sánh/bằng nhau không?** `compareToIgnoreOptional` đi với `equalsIgnoreOptional`.
13. **Có giả định `version()` luôn bốn thành phần không?** Không; dùng accessor cho số vắng mặt.
14. **Đã xử lý chuỗi parse không hợp lệ chưa?** `IllegalArgumentException`, `NullPointerException` và số vượt giới hạn.
15. **Có dùng parse để biến môi trường thành runtime mới không?** Parse chỉ tạo object.
16. **Version gate có được hỗ trợ bởi build target thực tế không?** Nhánh `if` không làm class phiên bản cao hơn biên dịch được.
17. **Có runtime image thiếu module/preview config không?** Version number không đủ đảm bảo capability.
18. **Có yêu cầu an toàn/vá lỗi bảo mật?** Tham khảo vendor advisory, không chỉ số feature.
19. **Có nhiều Java installations hoặc containers?** Thu thập thông tin trực tiếp từ mỗi process.
20. **Có log metadata phù hợp không?** `Runtime.version()`, `java.vm.name`, `java.vm.version` hữu ích; tránh log quá mức dữ liệu nhạy cảm.
21. **Có dùng lớp value-based làm khóa đồng bộ không?** Không; so sánh theo giá trị, không theo identity.
22. **Có viết test giả lập phiên bản bằng thay global system properties không?** Ưu tiên inject một `Runtime.Version` mẫu.

## 21. Tổng kết

**`Runtime.version()` trả một `Runtime.Version` phản ánh phiên bản Java runtime đang chạy chính tiến trình của bạn.** Khi cần xác định nhánh Java, dùng `feature()`; khi cần đọc bản update hoặc patch, dùng `interim()`, `update()` và `patch()`. Đây là API hiện đại của sơ đồ Java 10+; đừng dùng `major()/minor()/security()` đã deprecated.

`Runtime.Version.parse` cho phép tạo và kiểm tra phiên bản từ một chuỗi hợp lệ; `compareTo` biết so thành phần số, pre-release, build và optional text. `Runtime.version()` khác parse ở chỗ nó **hỏi runtime thật**, không phải đọc một ví dụ. Để biết **triển khai JVM** cụ thể, dùng thêm `java.vm.version`, `java.vm.name` và `java.vm.vendor`.

**Không coi phiên bản JVM đang chạy là phiên bản compiler hay bất kỳ JDK nào có trên máy.** Hãy kiểm tra version tại đúng process, test runtime thực tế, hiểu giới hạn của version gates và giữ các chính sách tương thích/bảo mật riêng.

### Tài liệu API chính thức

- [Runtime.version() — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
- [Runtime.Version — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html)
- [System properties — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322)
- [Oracle Java SE 17 — Version String Format](https://docs.oracle.com/en/java/javase/17/install/version-string-format.html)
- [Oracle Java SE 17 — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)