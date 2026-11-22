# Phân tích, so sánh phiên bản bằng API thay vì cắt chuỗi tùy ý trong Java

## 1. Vì sao cần API phiên bản?

Nhiều ứng dụng phải quyết định **JDK đang chạy đã đạt một mốc phiên bản hay chưa**, ví dụ yêu cầu Java 17 trở lên, chỉ hỗ trợ một dòng JDK được kiểm thử, hay cần hiển thị thông tin phiên bản trong báo cáo chẩn đoán. Vấn đề phát sinh khi mã coi phiên bản là chuỗi thông thường:

```java
String a = "17.0.10";
String b = "17.0.8";
System.out.println(a.compareTo(b) > 0); // false: sai về thứ tự phiên bản
```

So sánh từ điển đặt ký tự `'1'` ở thành phần `10` trước `'8'` của thành phần `8`. Thực tế, bản update `17.0.10` **mới hơn** `17.0.8`. Mã kiểu `split("\\.")` rồi lấy phần tử cố định cũng có thể bỏ sót tiền tố phát hành thử (`-ea`), số build (`+7`), thông tin tùy chọn (`-LTS`), hoặc không xử lý đúng các phiên bản có số thành phần khác nhau.

Từ **Java 9**, JDK cung cấp **`java.lang.Runtime.Version`**, một kiểu dữ liệu chuẩn để:

- **Phân tích** chuỗi theo định dạng phiên bản của **Java Runtime/JDK** bằng `Runtime.Version.parse(String)`.
- **Đọc** các thành phần có ý nghĩa bằng các accessor, thay vì giải nghĩa vị trí ký tự tùy ý.
- **So sánh** theo quy tắc phiên bản bằng `compareTo(...)` hoặc `compareToIgnoreOptional(...)`.
- **Lấy phiên bản JVM đang chạy** bằng `Runtime.version()`, không phải đọc `java.version` rồi tự parse.

**Phạm vi quan trọng:** `Runtime.Version` được thiết kế cho **chuỗi phiên bản của Java runtime**, không phải một bộ phân tích đa năng cho mọi định dạng phiên bản ứng dụng, Maven, Docker, Git tag hay Semantic Versioning 2.0. Chỉ dùng nó cho những chuỗi tuân thủ ngữ pháp JDK.

### Ba câu hỏi khác nhau

| Câu hỏi | API / chính sách phù hợp | Ví dụ |
| --- | --- | --- |
| JVM hiện tại thuộc Java feature release nào? | `Runtime.version().feature()` | `17`, `21`, `25` |
| Một chuỗi JDK hợp lệ thuộc phiên bản nào, có mới hơn mốc khác không? | `Runtime.Version.parse(...)` rồi `compareTo(...)` | `17.0.10` mới hơn `17.0.8` |
| Một thư viện/app dùng version riêng có mới hơn không? | Parser và quy tắc **đúng với định dạng của thư viện/app đó** | Maven/SemVer, không mặc nhiên dùng `Runtime.Version` |

## 2. Java 9 mở đầu API; JDK hiện hành dùng thuật ngữ feature/interim/update/patch

API `Runtime.Version` được giới thiệu ở **Java 9** cùng sơ đồ phiên bản của **JEP 223**. Khi Java chuyển sang lịch phát hành theo thời gian, **JEP 322** (Java 10) điều chỉnh ý nghĩa các trường. Các JDK đang được duy trì sử dụng dạng thành phần:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

Những phần có giá trị `0` ở cuối thường được **lược bỏ**; ví dụ `21` thay vì `21.0.0. Có thể tồn tại phần bổ sung của nhà triển khai, cùng hậu tố pre-release, build và thông tin tùy chọn.

| Thành phần | API hiện hành | Ý nghĩa chính |
| --- | --- | --- |
| Feature | `feature()` | Bộ đếm phát hành tính năng, ví dụ `17`, `21` |
| Interim | `interim()` | Bộ đếm phát hành trung gian không thay đổi API chuẩn theo chính sách phiên bản |
| Update | `update()` | Bộ đếm bản cập nhật tương thích, thường bao gồm sửa lỗi và bảo mật |
| Patch | `patch()` | Bộ đếm phát hành sửa lỗi khẩn cấp |
| Danh sách số | `version()` | `List<Integer>` chứa các thành phần số thực sự có trong chuỗi |
| Tiền phát hành | `pre()` | `Optional<String>`, ví dụ `ea` |
| Build | `build()` | `Optional<Integer>`, ví dụ `7` |
| Thông tin tùy chọn | `optional()` | `Optional<String>`, ví dụ `LTS` |

**Khác biệt theo thời điểm:** các accessor `feature()`, `interim()`, `update()` và `patch()` mang tên hiện hành có từ Java 10. Một số tên cũ như `major()`, `minor()`, `security()` vẫn có thể thấy trên API nhưng **đã bị đánh dấu deprecated từ Java 10** vì nghĩa tên không còn mô tả đúng lịch phát hành mới. Với code Java 17+ mới, dùng các accessor hiện hành. Không sao chép đoạn dùng `feature()` để biên dịch với **JDK 9 nguyên bản** mà không đánh giá lại mức API của phiên bản đó.

Ví dụ:

```java
Runtime.Version version = Runtime.Version.parse("17.0.8+7-LTS");

System.out.println(version.feature());          // 17
System.out.println(version.interim());          // 0
System.out.println(version.update());           // 8
System.out.println(version.patch());            // 0
System.out.println(version.version());          // [17, 0, 8]
System.out.println(version.build().orElse(-1)); // 7
System.out.println(version.optional().orElse("không có")); // LTS
```

Đây là **đoạn mã** đặt trong phương thức Java, không phải chương trình độc lập. Kết quả `patch() == 0` khi phần patch không xuất hiện là hành vi API chuẩn; nó không có nghĩa chuỗi gốc phải chứa bốn số.

## 3. Cấu trúc chuỗi phiên bản của JDK

Chuỗi phiên bản theo JEP 322 có phần số chính, rồi có thể thêm định danh tiền phát hành, số build và thông tin bổ sung. Các ví dụ tiêu biểu:

| Chuỗi | Ý nghĩa |
| --- | --- |
| `17` | Feature release 17, không khai báo update/build |
| `17.0.8` | Feature 17, interim 0, update 8 |
| `17.0.8+7` | Cùng dòng phiên bản với số build 7 |
| `17.0.8+7-LTS` | Số build 7 và thông tin tùy chọn `LTS` |
| `21-ea` | Phiên bản 21 tiền phát hành (early access), chưa phải bản phát hành cuối cùng |
| `21-ea+18` | Tiền phát hành 21 cùng số build 18 |
| `21+35` | Feature 21 cùng số build 35 |

Sơ đồ đơn giản:

```text
17.0.8+7-LTS
│  │ │ │ └──── optional build information
│  │ │ └────── build = 7
│  │ └──────── update = 8
│  └────────── interim = 0
└───────────── feature = 17
```

Khi parse một chuỗi, **đừng gán nghĩa dựa trên số lượng dấu chấm**. Ví dụ `17` có đúng một thành phần số, nhưng `interim()`, `update()`, `patch()` vẫn trả `0`. `version()` giữ danh sách các thành phần số có thực trong chuỗi; nó có thể có nhiều thành phần hơn bốn khi có quy ước của nhà triển khai.

Một số chuỗi hay gặp **không đúng ngữ pháp JDK hiện hành**:

- `1.8.0_381` — dạng Java 8 cũ có ký tự gạch dưới.
- `v21.0.2` — có tiền tố `v` tự thêm.
- `17.0.0` — kết thúc bằng các thành phần zero dư, trái quy tắc chuẩn của `$VNUM`.
- `21.0.1-alpha.1` — cách đặt prerelease thường thấy ở SemVer nhưng không theo cú pháp `$PRE` của JDK.

`Runtime.Version.parse(...)` báo **`IllegalArgumentException`** khi chuỗi không hợp lệ; không tự sửa chuỗi bằng cách cắt bớt tiền tố/hậu tố trước khi hiểu rõ nguồn. Nếu cần xử lý phiên bản Java 8 hoặc chuỗi version của hệ sinh thái khác, dùng đúng parser cho định dạng đó và một chính sách chuyển đổi được thiết kế rõ ràng.

### Tên chuẩn và metadata không tạo ra bảo đảm tương thích

Hai JDK có cùng `feature() == 21` vẫn có thể khác build, bản update, nhà cung cấp, quyền sử dụng hay đặc tính triển khai. Trường `optional()` có thể chứa ký hiệu do nhà triển khai lựa chọn: **không** xem `LTS` trong chuỗi là bằng chứng duy nhất cho điều kiện hỗ trợ thương mại, chính sách vá lỗi hay trạng thái an ninh của bản JDK.

## 4. Phân tích và lấy phiên bản đúng API

### 4.1. Phân tích một phiên bản đã biết là phiên bản JDK

```java
Runtime.Version target = Runtime.Version.parse("21.0.2+13");

int feature = target.feature();               // 21
int update = target.update();                 // 2
boolean hasBuild = target.build().isPresent();// true
```

Dùng `parse` cho dữ liệu từ cấu hình, manifest hay metadata mà hợp đồng **định nghĩa đây là Java runtime version**. Với dữ liệu bên ngoài, xử lý lỗi, giới hạn độ dài và báo rõ chuỗi sai thay vì để một lỗi parser trở thành lỗi không giải thích được.

### 4.2. Lấy phiên bản JVM đang thực thi

```java
Runtime.Version current = Runtime.version();

System.out.println("Feature = " + current.feature());
System.out.println("Pre-release = " + current.pre().orElse("không"));
System.out.println("Full JDK version = " + current);
```

Đoạn này có kết quả **phụ thuộc bản JDK đang chạy**; không viết stdout cố định như thể mọi máy đều là Java 21. Đây là lựa chọn trực tiếp và rõ ràng hơn `System.getProperty("java.version").split("\\.")`.

Một số môi trường chạy bằng bản JDK khác với bản dùng để compile. `Runtime.version()` chỉ cho biết **runtime hiện tại**; nó không cho biết `javac --release` đã chọn mức bytecode nào, không bảo đảm một module/provider tùy chọn có mặt, và không thay được phép thử thật với API cần sử dụng.

### 4.3. Làm việc với Optional

`pre()`, `build()`, `optional()` đều trả về `Optional`:

```java
Runtime.Version v = Runtime.Version.parse("21-ea");
System.out.println(v.pre().orElse("bản phát hành cuối"));
System.out.println(v.build().orElse(-1));
```

Kết quả:

```text
ea
-1
```

`Optional.empty()` là trạng thái hợp lệ: nếu không có `+BUILD`, không gọi `build().get()` mà chưa kiểm tra. Lưu ý **`pre()` khác `optional()`**: `21-ea` có pre-release `ea`, còn `21+35-LTS` có optional information `LTS` mà không có pre-release.

## 5. Quy tắc so sánh của Runtime.Version

### 5.1. So sánh phần số theo từng thành phần, không theo từ điển

`Runtime.Version` implements `Comparable<Runtime.Version>`. Với `a.compareTo(b)`:

- Kết quả **âm**: `a` đứng trước `b`.
- Kết quả **0**: hai đối tượng có thứ tự tương đương theo quy tắc đang áp dụng.
- Kết quả **dương**: `a` đứng sau `b`.

**Không kiểm tra giá trị chính xác như `compareTo(...) == 1`**, vì hợp đồng `Comparable` chỉ bảo đảm dấu của kết quả. Dùng `> 0`, `< 0`, hoặc `== 0`.

Ví dụ:

```java
Runtime.Version older = Runtime.Version.parse("17.0.8");
Runtime.Version newer = Runtime.Version.parse("17.0.10");
boolean newerRelease = newer.compareTo(older) > 0; // true
```

Số `10` lớn hơn số `8` ở thành phần update, bất kể thứ tự chữ cái của các chuỗi gốc. Khi so sánh dãy số khác độ dài, các thành phần bổ sung cũng được xét theo quy tắc JDK.

### 5.2. Pre-release được xếp trước bản phát hành không có pre-release

```java
Runtime.Version early = Runtime.Version.parse("21-ea");
Runtime.Version generalAvailability = Runtime.Version.parse("21");
boolean earlyIsBeforeFinal = early.compareTo(generalAvailability) < 0;
// true
```

`21-ea` không thể coi là tương đương `21` chỉ vì `feature()` giống nhau. Nếu dịch vụ chỉ hỗ trợ bản phát hành cuối cùng, cần kiểm tra cả `pre().isEmpty()`; chỉ kiểm tra `feature() >= 21` sẽ vô tình chấp nhận `21-ea`.

Trong phần pre-release, các định danh toàn chữ số được so sánh số học; chữ và số có quy tắc ưu tiên theo đặc tả JDK. **Không tự viết comparator bằng cách so ký tự `-`, `.` hoặc chuẩn hóa thành một số `major*100+minor`.**

### 5.3. Số build và optional information cũng có thể ảnh hưởng so sánh

Sau phần số và pre-release, `compareTo` xét **số build**, rồi xét **optional build information**. Ví dụ:

```java
Runtime.Version withoutBuild = Runtime.Version.parse("21");
Runtime.Version withBuild = Runtime.Version.parse("21+1");
System.out.println(withBuild.compareTo(withoutBuild) > 0); // true
```

Phiên bản có build number được xếp sau phiên bản cùng phần số không có build number, theo hợp đồng của JDK. Điều này **khác** một số cách hiểu về SemVer 2.0, trong đó build metadata không ảnh hưởng thứ tự ưu tiên phiên bản.

Có hai cặp phương thức chính:

| Thứ tự và phép bằng | Tính đến số build? | Tính đến optional information? |
| --- | --- | --- |
| `compareTo(...)`, `equals(...)` | Có | Có |
| `compareToIgnoreOptional(...)`, `equalsIgnoreOptional(...)` | Có | **Không** |

Ví dụ:

```java
Runtime.Version a = Runtime.Version.parse("21.0.1+12-LTS");
Runtime.Version b = Runtime.Version.parse("21.0.1+12-vendor");

System.out.println(a.equals(b));                     // false
System.out.println(a.equalsIgnoreOptional(b));       // true
System.out.println(a.compareToIgnoreOptional(b) == 0);// true
```

Cặp `IgnoreOptional` **chỉ bỏ phần thông tin tùy chọn**, **không bỏ số build**. Nếu bạn muốn so **feature/update mà bỏ qua toàn bộ build**, cần định nghĩa policy rõ dựa trên các thành phần số, hoặc chuẩn hóa dữ liệu theo yêu cầu. Đừng gán nhầm `compareToIgnoreOptional` là “bỏ mọi metadata”.

**Giữ cặp phép toán nhất quán:** `compareTo()` đi cùng `equals()`, `compareToIgnoreOptional()` đi cùng `equalsIgnoreOptional()`. Nếu dùng `TreeSet` với comparator bỏ optional, nhưng dùng `HashSet` với `equals/hashCode` mặc định, hai tập có thể có hành vi “trùng” khác nhau; phải chọn một quy tắc nhận diện phiên bản thống nhất theo nghiệp vụ.

### 5.4. Cách so sánh nào dành cho yêu cầu nào?

| Bài toán | Cách tiếp cận |
| --- | --- |
| JDK có mới hơn mốc phiên bản chính thức không? | `actual.compareTo(required) >= 0`, nếu ngữ nghĩa build/pre phù hợp |
| JDK có đúng dòng Java 17/21 không? | `actual.feature() == 17` hoặc `== 21` |
| Chỉ yêu cầu feature Java 17 trở lên | `Runtime.version().feature() >= 17` |
| Cùng số bản phát hành và build, bỏ hậu tố nhà cung cấp | `equalsIgnoreOptional` / `compareToIgnoreOptional` |
| Chỉ chấp nhận bản GA, không chấp nhận early access | Kiểm tra thêm `actual.pre().isEmpty()` |
| Kiểm tra một cập nhật bảo mật có được backport hay không | Dùng **policy/advisory của nhà cung cấp**, không dựa vào so version chung |
| So sánh artifact Maven/SemVer, dependency ranges, app version | Dùng parser/comparator của **hệ phiên bản tương ứng** |

## 6. Chương trình hoàn chỉnh Java 17+: parse, đọc thuộc tính, so sánh

Tạo file **`JavaVersionApiDemo.java`** với nội dung sau. Các chuỗi phiên bản được cố định để stdout có thể kiểm chứng độc lập với bản JDK người học đang chạy:

```java
public final class JavaVersionApiDemo {
    public static void main(String[] args) {
        Runtime.Version older =
            Runtime.Version.parse("17.0.8+7");
        Runtime.Version newer =
            Runtime.Version.parse("17.0.10+7");

        // Đọc các trường theo đúng API và ý nghĩa JDK 10+.
        System.out.println("Feature: " + newer.feature());
        System.out.println("Interim: " + newer.interim());
        System.out.println("Update: " + newer.update());
        System.out.println("Patch: " + newer.patch());
        System.out.println("Build: " + newer.build().orElse(-1));
        System.out.println("Number parts: " + newer.version());

        // So chuỗi trực tiếp cho kết quả sai ở update 10 và 8.
        boolean wrongTextOrder =
            "17.0.10".compareTo("17.0.8") > 0;
        boolean correctVersionOrder =
            newer.compareTo(older) > 0;
        System.out.println("Text order newer: " + wrongTextOrder);
        System.out.println("API order newer: " + correctVersionOrder);

        Runtime.Version early = Runtime.Version.parse("21-ea");
        Runtime.Version finalRelease = Runtime.Version.parse("21");
        System.out.println("EA before GA: "
            + (early.compareTo(finalRelease) < 0));

        Runtime.Version build = Runtime.Version.parse("21+1");
        System.out.println("Build affects order: "
            + (build.compareTo(finalRelease) > 0));

        Runtime.Version vendorA =
            Runtime.Version.parse("21.0.1+12-LTS");
        Runtime.Version vendorB =
            Runtime.Version.parse("21.0.1+12-vendor");

        System.out.println("Exact equals: "
            + vendorA.equals(vendorB));
        System.out.println("Ignore optional equals: "
            + vendorA.equalsIgnoreOptional(vendorB));
        System.out.println("Ignore optional compare: "
            + (vendorA.compareToIgnoreOptional(vendorB) == 0));
        System.out.println("Optional metadata: "
            + vendorA.optional().orElse("none"));

        // Định dạng Java 8 cũ không tuân theo JDK version scheme này.
        try {
            Runtime.Version.parse("1.8.0_381");
            System.out.println("Old format rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Old format rejected: true");
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 JavaVersionApiDemo.java
java JavaVersionApiDemo
```

**Stdout chính xác** (không phụ thuộc `Runtime.version()` trên máy):

```text
Feature: 17
Interim: 0
Update: 10
Patch: 0
Build: 7
Number parts: [17, 0, 10]
Text order newer: false
API order newer: true
EA before GA: true
Build affects order: true
Exact equals: false
Ignore optional equals: true
Ignore optional compare: true
Optional metadata: LTS
Old format rejected: true
```

Các hành vi cốt lõi đã được kiểm tra trên JDK hiện hành: `Runtime.Version.parse("17.0.10+7")` tạo feature `17` và update `10`; `compareTo(...)` không mắc lỗi so từ điển; hậu tố `-ea` đứng trước bản phát hành không có pre-release; `equalsIgnoreOptional` so các chuỗi cùng số build nhưng khác optional như kỳ vọng.

### Vì sao ví dụ không viết “đọc java.version rồi split”?

Vì `Runtime.version()` đã có kiểu dữ liệu chuẩn và `Runtime.Version.parse` đã cung cấp đúng ngữ pháp. Hơn nữa, code dùng chuỗi cố định để biểu diễn **quy tắc so sánh**; nếu dùng `Runtime.version()` trong dòng kiểm chứng kết quả, người học chạy JDK 17, 21 hoặc 25 sẽ có stdout khác nhau và không thể so sánh chính xác với mẫu.

Đối với dữ liệu thực, hãy đưa phiên bản cần kiểm tra vào một hàm nhận `Runtime.Version` và trả về quyết định, thay vì trộn logic parse/chính sách/hiển thị trong nhiều chỗ.

## 7. Kiểm tra phiên bản JVM khi khởi động ứng dụng

### 7.1. Chỉ yêu cầu một feature release tối thiểu

Ví dụ thư viện cần Java **17 trở lên**:

```java
// Đoạn mã đặt trong main() hoặc phần kiểm tra cấu hình.
Runtime.Version running = Runtime.version();

if (running.feature() < 17) {
    throw new IllegalStateException(
        "Cần Java 17+, hiện tại: " + running
    );
}
```

Trên JDK đã biên dịch được đoạn mã đó, điều kiện này có ý nghĩa rõ ràng. Tuy nhiên, nếu ứng dụng **được biên dịch cho Java 17** mà chạy bằng JVM Java 11, JVM thường từ chối class file trước khi `main()` chạy (`UnsupportedClassVersionError`). Vì vậy **mã kiểm tra trong main không thay thế** việc đặt `--release` phù hợp, metadata launcher hoặc chính sách triển khai.

### 7.2. Yêu cầu một mốc update cụ thể

Nếu chính sách của tổ chức yêu cầu tối thiểu chuỗi `17.0.8`:

```java
Runtime.Version current = Runtime.version();
Runtime.Version minimum = Runtime.Version.parse("17.0.8");

if (current.compareTo(minimum) < 0) {
    throw new IllegalStateException(
        "JDK quá cũ: " + current + ", yêu cầu: " + minimum
    );
}
```

Đoạn này chỉ là **so sánh theo trật tự phiên bản JDK**. Không khẳng định rằng một JDK vendor A có `17.0.8` luôn tương đương vendor B về bản vá bảo mật hoặc hỗ trợ thương mại. Để áp chính sách chống CVE, cần thêm vendor, build, advisories và lịch phát hành/bản vá thực tế, vì nhà cung cấp có thể **backport** bản sửa bảo mật.

Nếu policy chỉ quan tâm **phiên bản cập nhật** và cố ý bỏ số build/hậu tố optional, cần thể hiện quy tắc đó tường minh (ví dụ kiểm tra `feature()`, `interim()`, `update()`, `patch()`) thay vì âm thầm dùng `compareToIgnoreOptional()` với giả định nó bỏ cả build number.

### 7.3. Chặn pre-release khi bắt buộc bản phát hành ổn định

```java
Runtime.Version running = Runtime.version();
boolean stableEnough = running.feature() >= 21
    && running.pre().isEmpty();

if (!stableEnough) {
    throw new IllegalStateException(
        "Cần JDK 21+ bản phát hành ổn định: " + running
    );
}
```

Đây là **policy ví dụ**, không phải quy định chung rằng mọi dịch vụ phải yêu cầu Java 21. Chỉ so `feature() >= 21` sẽ chấp nhận `21-ea`, trong khi nhu cầu “GA only” yêu cầu kiểm tra `pre()`. Tùy chính sách, có thể chấp nhận hoặc không chấp nhận pre-release của các feature release cao hơn.

### 7.4. Nên tách việc kiểm tra khỏi chức năng nghiệp vụ

Một cách thiết kế có thể kiểm thử:

```java
// Đoạn hàm minh họa, không phải chương trình độc lập.
static boolean hasRequiredJdk(Runtime.Version current,
                              Runtime.Version minimum,
                              boolean allowPrerelease) {
    return current.compareTo(minimum) >= 0
        && (allowPrerelease || current.pre().isEmpty());
}
```

Phần gọi hàm quyết định thông báo lỗi, log, điều hướng và mức chấp nhận. Phần kiểm tra chỉ biết kiểu `Runtime.Version`, nên có thể test với các version giả định mà không cần chạy nhiều bản JVM.

## 8. Phân biệt phiên bản của JVM, module và phần mềm bên ngoài

### 8.1. Runtime.Version dành cho JDK runtime version

`Runtime.version()` cho phiên bản JVM; `Runtime.Version.parse(String)` cho chuỗi theo **sơ đồ phiên bản JDK**. Đây là đối tượng của bài học.

Khi bạn nhận được dữ liệu như:

```text
my-library-1.2.3-SNAPSHOT.jar
v2.1.0
1.0.0-alpha.1+sha.123
2026.11-build-abc
```

không được mặc định `Runtime.Version.parse` sẽ chấp nhận hay so sánh **theo đúng quy tắc nghiệp vụ**. Một số chuỗi tình cờ parse được nhưng có thể có thứ tự khác cách Maven hoặc SemVer định nghĩa. Dấu mốc `+BUILD` trong JDK chẳng hạn có tác động tới `compareTo`, trong khi **SemVer 2.0 build metadata không làm thay đổi precedence**.

### 8.2. Phiên bản module cũng có API riêng

Hệ module Java (JPMS) có `java.lang.module.ModuleDescriptor.Version`, một kiểu phiên bản khác được thiết kế cho **module descriptors**. Nó có `parse(...)` và `compareTo(...)` với ngữ nghĩa riêng. **Không chuyển đổi tùy ý** giữa `ModuleDescriptor.Version` và `Runtime.Version`, dù cả hai đều là kiểu phiên bản và đều có `parse`.

Nếu một ứng dụng thực sự phải so các phiên bản trong metadata module, hãy dùng API của module và đọc hợp đồng thứ tự tương ứng. Nếu phải chọn dependency version theo Maven, dùng cơ chế resolution/version comparison của Maven/Gradle hoặc một thư viện đúng chuẩn. Một parser đúng **lĩnh vực** quan trọng hơn việc dùng một API JDK chỉ vì nó có tên `Version`.

### 8.3. Version, vendor, tính năng và bản vá là các trục độc lập

Một hệ thống có thể chạy Java 21 mà vẫn thiếu module tùy chọn, provider mã hóa, native library hoặc tính năng preview cần thiết. Ngược lại, một bản JDK có số update nhỏ hơn có thể đã được nhà cung cấp backport một bản sửa. Vì vậy:

- Dùng `Runtime.Version` để trả lời **số phiên bản**.
- Dùng kiểm tra class/module/feature/capability để xác nhận tính năng thực sự **khả dụng**.
- Dùng tài liệu vendor/advisory và bằng chứng triển khai cho **tính an toàn, trạng thái hỗ trợ và bản vá**.

Đừng dùng mỗi chuỗi version để suy luận về tất cả ba khía cạnh.

## 9. Lỗi thường gặp khi xử lý phiên bản

| Lỗi | Vì sao sai? | Cách làm phù hợp |
| --- | --- | --- |
| `"17.0.10".compareTo("17.0.8")` | So chữ trước khi so số | Parse thành `Runtime.Version` rồi so |
| `java.version.split("\\.")` và ép phần tử cố định | Chuỗi có thể có `-ea`, `+build`, optional info hoặc ít thành phần | `Runtime.version()`, `parse`, accessor hiện hành |
| Cắt phần trước dấu `+` rồi so | Loại bỏ số build dù chính sách so sánh có thể cần | Quyết định có xét build bằng API/policy rõ ràng |
| Coi `compareToIgnoreOptional` là bỏ cả build | Chỉ bỏ `$OPT`, vẫn xét `$BUILD` | Dùng đúng ý nghĩa method |
| `compareTo(...) == 1` để kiểm tra mới hơn | `Comparable` chỉ bảo đảm dấu | `compareTo(...) > 0` |
| Dùng `==` để so hai `Runtime.Version` | So danh tính tham chiếu thay vì giá trị | `equals(...)` hoặc `compareTo(...) == 0` |
| Gọi `build().get()` không kiểm tra | Không phải phiên bản nào cũng có số build | `orElse(...)` hoặc `isPresent()` |
| Lấy `feature()` rồi cho phép `21-ea` như bản GA | Bỏ qua trạng thái pre-release | Xem `pre()` và chính sách release |
| Dùng các tên `major()/minor()/security()` cho code mới | Deprecated, tên không còn phù hợp JEP 322 | `feature()/interim()/update()/patch()` |
| Gửi `1.8.0_381` vào `Runtime.Version.parse` | Chuỗi Java 8 legacy không theo schema mới | Dùng parser thích hợp cho định dạng cũ |
| Dùng Runtime.Version để so Git tags/Maven versions | Ngữ pháp và thứ tự có thể khác | Dùng comparator của hệ version tương ứng |
| Coi bản JDK có feature cao hơn là bảo đảm hết mọi CVE | Vendor patch và backport khác nhau | Kiểm chứng advisory, build, vendor và deployment |
| Dùng version check để thay `javac --release` | Runtime check không kiểm soát bytecode/target API | Cấu hình build target đúng và test với JVM đích |

### Lỗi parser phải được xử lý ở ranh giới dữ liệu

```java
// Hàm minh họa: chỉ dùng cho chuỗi được tuyên bố là JDK version.
static Runtime.Version parseRequiredJdkVersion(String text) {
    if (text == null || text.length() > 128) {
        throw new IllegalArgumentException("Chuỗi version không hợp lệ");
    }
    try {
        return Runtime.Version.parse(text);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
            "Sai định dạng Java runtime version: " + text, ex
        );
    }
}
```

Giới hạn `128` là **policy minh họa của ứng dụng**, không phải giới hạn tiêu chuẩn của `Runtime.Version.parse`. Không dùng `trim()` hoặc tự xóa hậu tố như một cách “sửa” dữ liệu đầu vào thiếu hợp đồng; nếu nguồn cho phép khoảng trắng bao quanh, định nghĩa bước chuẩn hóa được chấp thuận rõ ràng và test các trường hợp biên.

## 10. Bộ kiểm thử đề xuất

Một tính năng chọn runtime JDK hoặc kiểm tra mốc phát hành nên bao phủ:

1. **Số thành phần:** `17`, `17.0.8`, `17.0.8.1`, phiên bản có thêm phần số từ nhà triển khai.
2. **Thứ tự số học:** `17.0.10 > 17.0.8` dù so chuỗi ngược lại; `21 > 17.0.99`.
3. **Tiền phát hành:** `21-ea < 21`; quy tắc ổn định không chấp nhận `pre()` khi yêu cầu GA.
4. **Build và thông tin tùy chọn:** `21+1 > 21` theo `compareTo`; `equalsIgnoreOptional` đúng với hai hậu tố optional khác nhau nếu phần còn lại trùng.
5. **Optional trống:** `pre()/build()/optional()` đều có thể vắng mặt, không gây `NoSuchElementException`.
6. **Chuỗi không hợp lệ:** Java 8 cũ, chuỗi có tiền tố `v`, dấu phân cách sai, các thành phần zero dư, `null`.
7. **Phân biệt miền dữ liệu:** không parse một Git tag hay phiên bản Maven bất kỳ như JDK version.
8. **Đối chiếu runtime triển khai:** máy chạy thực tế, custom runtime image và vendor/build thực tế, không suy luận từ JDK của IDE.
9. **Cặp so sánh và bằng:** comparator bỏ optional phải kết hợp với logic nhận diện đúng; tránh khác biệt bất ngờ khi lưu vào map/set.
10. **Quy tắc bảo mật:** khi áp mốc cập nhật cần dữ liệu phát hành/advisory thật, bao gồm trường hợp backport từ vendor.

Trong unit test, tạo các đối tượng bằng `Runtime.Version.parse` với chuỗi cố định. Không kiểm thử thứ tự số học bằng cách phụ thuộc `Runtime.version()`, bởi kết quả đó sẽ thay đổi khi CI nâng JDK.

## 11. Áp dụng lâu dài và tài liệu tham khảo

**Cách làm phù hợp với API hiện hành:** khi so phiên bản runtime, dùng `Runtime.version()` hoặc `Runtime.Version.parse(...)` để có đối tượng chuẩn; dùng `feature()` và các accessor rõ nghĩa cho điều kiện chính sách; dùng `compareTo` hoặc `compareToIgnoreOptional` đúng quy tắc; xử lý lỗi parser và phân biệt early access/build. Đó là cách bền vững trước những chuỗi phiên bản có nhiều thành phần.

Đối với code chạy trên Java 17+ mới, **không dùng các accessor deprecated** chỉ để giữ cách gọi cũ từ Java 9. Khi cần hỗ trợ JVM 9 thực sự, đánh giá riêng tập API có mặt ở Java 9 và biên dịch/kiểm thử với đúng target; việc giới thiệu từ Java 9 không có nghĩa mọi tên accessor hiện tại đều có từ Java 9.

Tài liệu chính thức:

- [Java SE 25 — Runtime.Version API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): `parse`, `feature`, `compareTo`, `compareToIgnoreOptional`, `equalsIgnoreOptional`, ngữ pháp và ví dụ.
- [Java SE 25 — Runtime API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html): `Runtime.version()` và thông tin runtime.
- [OpenJDK JEP 223 — New Version-String Scheme](https://openjdk.org/jeps/223): nguồn gốc của cơ chế Java 9.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): điều chỉnh sơ đồ tên trường từ Java 10 cho các JDK sau đó.
- [Java SE 25 — ModuleDescriptor.Version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleDescriptor.Version.html): kiểu dữ liệu phiên bản cho Java modules, có ngữ nghĩa riêng.
- [Oracle Migration Guide — New Version-String Scheme](https://docs.oracle.com/en/java/javase/25/migrate/migrating-from-jdk-8-later-jdk-releases.html): hướng dẫn chuyển từ quy ước cũ sang sơ đồ hiện hành.

Bài học áp dụng cho **sơ đồ phiên bản JDK còn hiệu lực** và các API được JDK hiện đại duy trì; không khuyến khích tự cắt chuỗi, phụ thuộc vào tên accessor legacy, hay so sánh sai định dạng bằng một comparator chung.