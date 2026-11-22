# Đọc phiên bản feature, interim, update và patch của JDK

Khi nâng cấp một ứng dụng Java, chỉ nói rằng máy chủ đang chạy “Java 21” thường chưa đủ. Hai môi trường cùng dùng JDK 21 có thể khác nhau ở bản cập nhật bảo mật, bản sửa lỗi, nhà cung cấp và số build. Những khác biệt đó có thể ảnh hưởng đến việc tái hiện lỗi, kiểm tra lỗ hổng, chuẩn hóa môi trường CI/CD và quyết định thời điểm nâng cấp.

Từ JDK 10, cách đánh số phiên bản của JDK sử dụng bốn thành phần số theo quy ước của JEP 322:

```text
FEATURE.INTERIM.UPDATE.PATCH
```

Mỗi thành phần mô tả một loại mốc phát hành khác nhau. Đọc đúng các thành phần này giúp phân biệt một feature release, một update release và một patch release; đồng thời tránh nhầm số build hoặc nhãn LTS với số phiên bản chính.

## 1. Vì sao cần đọc đủ phiên bản JDK?

Giả sử hai máy đều hiển thị JDK 21. Một máy chạy `21.0.1`, máy còn lại chạy `21.0.2`. Cả hai thuộc cùng feature release 21, nhưng máy thứ hai đã nhận một đợt update mới hơn. Nếu một lỗi đã được sửa trong update đó, kết quả chạy chương trình có thể khác nhau.

Khi điều tra sự cố hoặc chuẩn bị migration, cần biết ít nhất:

- Feature release mà ứng dụng đang chạy, ví dụ 17, 21 hoặc 25.
- Interim, update và patch component nếu có.
- Số build của bản JDK cụ thể.
- Nhà cung cấp và bản phân phối JDK.
- Phiên bản runtime thực tế của tiến trình, không chỉ phiên bản được cài đặt trên máy.

Thông tin phiên bản đầy đủ giúp nhóm phát triển xác định môi trường có cùng mức cập nhật hay không, đối chiếu với thông báo bảo mật và tái tạo lỗi trên đúng bản runtime.

## 2. Quy ước phiên bản JDK từ JDK 10

JEP 322 chuẩn hóa chuỗi phiên bản thành các thành phần sau:

| Thành phần | Ý nghĩa | Cách thay đổi |
|---|---|---|
| `FEATURE` | Số feature release của JDK. Đây là số thường được nhắc đến khi nói JDK 17, JDK 21 hoặc JDK 25. | Tăng khi phát hành một feature release mới. |
| `INTERIM` | Số interim release thuộc cùng feature release. | Tăng khi có một interim release theo quy ước phát hành. Với các feature release thông thường hiện nay, thành phần này thường là `0`. |
| `UPDATE` | Số update release thuộc feature/interim tương ứng. | Tăng khi phát hành một bản update, thường chứa sửa lỗi và cập nhật bảo mật. |
| `PATCH` | Số patch release được phát hành để xử lý một vấn đề cần bản sửa riêng. | Tăng khi có patch release; thường là `0` trong các bản phát hành thông thường. |

Một chuỗi phiên bản đầy đủ có dạng:

```text
21.0.2.1
│  │ │ └── PATCH
│  │ └──── UPDATE
│  └────── INTERIM
└───────── FEATURE
```

Trong ví dụ này, `21` là feature release, `0` là interim, `2` là update và `1` là patch. Nhiều chuỗi phiên bản thực tế không hiển thị các thành phần bằng `0` ở cuối. Vì vậy, `21`, `21.0`, `21.0.2` và `21.0.2.0` có thể biểu diễn cùng các giá trị thành phần theo quy tắc chuẩn hóa của phiên bản.

Điểm quan trọng là bốn thành phần không có cùng ý nghĩa. Ví dụ `21.0.2` có nghĩa feature 21, interim 0, update 2, patch 0. Số `2` ở cuối chuỗi được hiển thị không phải patch component; nó là update component vì thành phần patch đứng sau nó và đang bằng 0 nên được lược bỏ.

## 3. Feature release

`FEATURE` nhận diện thế hệ feature chính của JDK. Ví dụ:

- `17` là feature release 17.
- `21` là feature release 21.
- `25` là feature release 25.

Kể từ khi mô hình phát hành sáu tháng được áp dụng, feature release mới thường xuất hiện vào khoảng tháng 3 và tháng 9. Một feature release có thể bổ sung ngôn ngữ Java, API, công cụ, khả năng của JVM, thay đổi mặc định hoặc loại bỏ những thành phần đã bị deprecated theo lộ trình.

Do đó, nâng từ JDK 17 lên JDK 21 là nâng qua các feature release. Việc này có phạm vi ảnh hưởng lớn hơn so với nâng từ `21.0.1` lên `21.0.2`. Nhóm phát triển cần đọc release notes, kiểm tra các JEP liên quan, chạy bộ kiểm thử và xác minh thư viện phụ thuộc trước khi đưa feature release mới vào production.

### Feature release và LTS

LTS là viết tắt của *Long-Term Support*. Đây là nhãn chính sách hỗ trợ của nhà cung cấp hoặc bản phân phối JDK. LTS không phải một thành phần trong bốn số `FEATURE.INTERIM.UPDATE.PATCH`.

Ví dụ, khi nói “JDK 21 LTS”, số `21` vẫn là feature component. Nhãn LTS cho biết bản phát hành thuộc nhóm được hỗ trợ dài hạn theo chính sách của nhà cung cấp. Thời gian hỗ trợ, điều kiện nhận bản vá và lịch kết thúc hỗ trợ có thể khác nhau giữa các nhà cung cấp; không nên suy ra thời hạn hỗ trợ chỉ từ chuỗi số phiên bản.

Một feature release không tự động là LTS. Khi lập kế hoạch migration, hãy kiểm tra chính sách hỗ trợ của đúng nhà cung cấp JDK mà hệ thống sử dụng.

## 4. Interim release

`INTERIM` biểu thị số thứ tự của interim release bên trong một feature release. Thành phần này được dành cho những mốc phát hành trung gian theo quy ước phiên bản của JDK. Với các feature release thông thường mà đội ngũ Java thường cài đặt, giá trị interim hiện thường là `0`.

Ví dụ minh họa cách đọc một chuỗi có interim khác `0`:

```text
23.1.0
│  │ └── UPDATE = 0
│  └──── INTERIM = 1
└─────── FEATURE = 23
```

Đây là ví dụ minh họa vị trí thành phần, không khẳng định một bản JDK cụ thể có số phiên bản đó. Khi gặp một chuỗi thực tế có interim khác `0`, cần đối chiếu tài liệu phát hành của nhà cung cấp để biết phạm vi và nội dung của interim release đó.

Không nên hiểu `INTERIM = 0` là JDK chưa có bản cập nhật. Update release được biểu diễn bằng thành phần `UPDATE`. Chẳng hạn, `21.0.2` có interim bằng `0` nhưng update bằng `2`, nghĩa là đã có hai mốc update được tính trong chuỗi phiên bản của feature release đó.

## 5. Update release

`UPDATE` biểu thị số update release. Các update release thường được phát hành theo chu kỳ ba tháng và tập trung vào sửa lỗi, cập nhật bảo mật, cải thiện độ ổn định và các điều chỉnh cần thiết. Chúng không phải feature release mới.

Ví dụ:

| Chuỗi phiên bản | Feature | Interim | Update | Patch |
|---|---:|---:|---:|---:|
| `17.0.8` | 17 | 0 | 8 | 0 |
| `17.0.9` | 17 | 0 | 9 | 0 |
| `21.0.1` | 21 | 0 | 1 | 0 |
| `21.0.2` | 21 | 0 | 2 | 0 |

Khi chuyển từ `21.0.1` sang `21.0.2`, feature release vẫn là 21. Ứng dụng không chuyển sang một thế hệ feature mới, nhưng runtime đã nhận một update mới. Update có thể chứa bản sửa cho lỗi JVM, thư viện chuẩn hoặc vấn đề bảo mật. Vì thế, cùng feature release không có nghĩa hai máy có hành vi hoàn toàn giống nhau.

Đối với môi trường production, nên có quy trình tiếp nhận update định kỳ: theo dõi thông báo của nhà cung cấp, đánh giá nội dung bản cập nhật, chạy regression test và triển khai theo từng môi trường. Không nên trì hoãn vô thời hạn các bản cập nhật bảo mật chỉ vì ứng dụng vẫn chạy được trên bản cũ.

## 6. Patch release

`PATCH` là thành phần thứ tư. Nó biểu thị patch release được phát hành để xử lý một vấn đề cần bản sửa riêng, thường là vấn đề nghiêm trọng cần giải quyết ngoài nhịp update thông thường.

Ví dụ minh họa:

```text
21.0.2.1
│  │ │ └── PATCH = 1
│  │ └──── UPDATE = 2
│  └────── INTERIM = 0
└───────── FEATURE = 21
```

Trong ví dụ này, feature vẫn là 21 và update vẫn là 2; patch component đã tăng lên 1. Khi so sánh với `21.0.2`, ta biết đây là một patch release dựa trên mốc update `21.0.2`.

Patch component thường bằng `0` và có thể bị lược bỏ trong chuỗi phiên bản. Không phải mọi bản phân phối đều phát hành patch release theo cùng một cách hoặc dùng nhãn hiển thị giống nhau. Hãy đọc thông báo của nhà cung cấp thay vì suy luận rằng mọi bản sửa khẩn cấp đều nhất thiết xuất hiện dưới dạng số thứ tư.

## 7. Đọc các phần bổ sung trong version string

Chuỗi phiên bản JDK có thể chứa thêm thông tin ngoài bốn thành phần số. Những phần này giúp nhận diện bản thử nghiệm, build hoặc thông tin bổ sung của bản phân phối.

### 7.1. Build number sau dấu `+`

Ví dụ:

```text
21.0.2+13
```

Ở đây:

- `21.0.2` là phần version number.
- `+13` là số build.

Build number cho biết bản build cụ thể của bản phát hành. Nó không phải `PATCH`, cũng không phải `UPDATE`. Vì vậy, `21.0.2+13` có patch component bằng `0`, không phải patch 13.

Khi cần tái tạo môi trường, nên ghi lại cả build number. Hai bản build từ các nhà cung cấp khác nhau có thể có cách đóng gói, bản vá bổ sung hoặc thông tin build khác nhau dù cùng feature, interim và update component.

### 7.2. Nhãn pre-release

Một bản JDK chưa phát hành chính thức có thể có nhãn thử nghiệm như `ea` (early access). Ví dụ minh họa:

```text
25-ea+12
```

`25` là feature component, `ea` là nhãn pre-release và `12` là build number. Bản early access phục vụ thử nghiệm, đánh giá khả năng tương thích và phản hồi trước khi phát hành chính thức. Không nên mặc định dùng bản EA cho production.

### 7.3. Thông tin bổ sung sau dấu `-`

Một số bản phân phối có thể thêm thông tin sau phần build, chẳng hạn thông tin nhận diện bản build hoặc nhà cung cấp. Cách hiển thị cụ thể tùy bản phân phối. Những chuỗi như vậy không làm thay đổi ý nghĩa của bốn thành phần số.

Tương tự, nhãn LTS thường được hiển thị như thông tin hỗ trợ hoặc metadata của bản phân phối. Không đọc nó như một chữ số thứ năm của JDK version.

## 8. Ví dụ phân tích phiên bản hoàn chỉnh

Xét chuỗi:

```text
21.0.2+13
```

Ta phân tích được:

| Phần | Giá trị | Diễn giải |
|---|---:|---|
| Feature | 21 | Thuộc feature release JDK 21. |
| Interim | 0 | Không có interim component khác 0. |
| Update | 2 | Thuộc update thứ 2 trong chuỗi phát hành này. |
| Patch | 0 | Không có patch component khác 0. |
| Build | 13 | Bản build số 13. |

Một chuỗi khác:

```text
17.0.10.1+1
```

được đọc là feature 17, interim 0, update 10, patch 1, build 1. Số `10` là update component; số `1` đứng sau nó là patch component; số `1` sau dấu `+` là build number. Ba số này có ba ý nghĩa khác nhau.

Khi đọc một chuỗi phiên bản, hãy tách phần số trước, sau đó mới đọc pre-release, build và metadata. Đừng đếm các nhóm số một cách máy móc mà bỏ qua vị trí của dấu chấm và dấu cộng.

## 9. Đọc phiên bản JDK bằng lệnh dòng lệnh

### 9.1. Kiểm tra runtime

Chạy:

```bash
java -version
```

Lệnh này hiển thị phiên bản của lệnh `java` đang được shell tìm thấy. Một kết quả minh họa có thể như sau:

```text
openjdk version "21.0.2" 2024-01-16
OpenJDK Runtime Environment (build 21.0.2+13)
OpenJDK 64-Bit Server VM (build 21.0.2+13, mixed mode)
```

Trong ví dụ, version number là `21.0.2`, build number là `13`. Runtime thuộc feature 21, interim 0, update 2 và patch 0.

### 9.2. Kiểm tra compiler

Chạy:

```bash
javac -version
```

Lệnh này cho biết phiên bản compiler `javac` mà shell đang gọi. Không nên mặc định compiler và runtime luôn đến từ cùng một thư mục cài đặt. Trên máy có nhiều JDK, `java` và `javac` có thể được phân giải từ các đường dẫn khác nhau nếu `PATH` hoặc `JAVA_HOME` được cấu hình không nhất quán.

### 9.3. Xem thuộc tính runtime

Có thể xem thêm thông tin môi trường bằng:

```bash
java -XshowSettings:properties -version
```

Một số thuộc tính hữu ích gồm:

| Thuộc tính | Thông tin |
|---|---|
| `java.version` | Chuỗi phiên bản Java được runtime công bố. |
| `java.runtime.version` | Chuỗi phiên bản runtime chi tiết hơn, có thể gồm build metadata. |
| `java.vendor` | Nhà cung cấp runtime. |
| `java.home` | Thư mục cài đặt runtime đang chạy. |
| `os.arch` | Kiến trúc hệ điều hành mà JVM nhận diện. |

Các thuộc tính có thể khác nhau giữa nhà cung cấp và phiên bản. Khi điều tra production, hãy lưu lại output thực tế thay vì chỉ ghi “Java 21”.

### 9.4. Kiểm tra đường dẫn trên Windows

Trong PowerShell, có thể kiểm tra lệnh đang được phân giải:

```powershell
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
$env:JAVA_HOME
```

Trên Linux hoặc macOS, có thể dùng:

```bash
which java
which javac
echo "$JAVA_HOME"
```

Những lệnh này giúp xác định shell đang sử dụng JDK nào. Trong Maven, Gradle hoặc IDE, toolchain hay cấu hình dự án có thể chọn một JDK khác với JDK mặc định của terminal. Khi build không giống CI, cần kiểm tra JDK mà chính tiến trình build đang sử dụng.

## 10. Đọc các thành phần phiên bản bằng Java API

Từ Java 9, có thể lấy đối tượng phiên bản của runtime hiện tại bằng `Runtime.version()`. Các phương thức `feature()`, `interim()`, `update()` và `patch()` phản ánh bốn thành phần theo quy ước JEP 322 và có trong API từ Java 10.

```java
public class JdkVersionInfo {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        System.out.println("Version: " + version);
        System.out.println("Feature: " + version.feature());
        System.out.println("Interim: " + version.interim());
        System.out.println("Update: " + version.update());
        System.out.println("Patch: " + version.patch());

        System.out.println("Pre-release: "
                + version.pre().orElse("none"));
        System.out.println("Build: "
                + version.build().map(String::valueOf).orElse("none"));
        System.out.println("Optional: "
                + version.optional().orElse("none"));
    }
}
```

Ví dụ, nếu chương trình chạy trên runtime `21.0.2+13`, các thành phần số được in ra tương ứng là feature `21`, interim `0`, update `2`, patch `0`. `build()` cung cấp số build nếu chuỗi phiên bản có thông tin đó. Các phương thức `pre()` và `optional()` trả về `Optional`, vì một bản phát hành chính thức có thể không có nhãn pre-release hoặc thông tin bổ sung.

Nếu cần phân tích một chuỗi phiên bản do cấu hình cung cấp, có thể dùng `Runtime.Version.parse`:

```java
public class ParseJdkVersion {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.Version.parse("21.0.2+13");

        System.out.println("Feature = " + version.feature());
        System.out.println("Interim = " + version.interim());
        System.out.println("Update = " + version.update());
        System.out.println("Patch = " + version.patch());
        System.out.println("Build = "
                + version.build().map(String::valueOf).orElse("unknown"));
    }
}
```

`Runtime.Version.parse` kiểm tra cú pháp version string và tạo đối tượng phiên bản. Nếu chuỗi không hợp lệ, phương thức sẽ ném `IllegalArgumentException`. Khi nhận version string từ file cấu hình hoặc hệ thống bên ngoài, nên xử lý lỗi phân tích thay vì giả định đầu vào luôn đúng.

Không nên tự tách chuỗi bằng `split("\\.")` rồi coi các vị trí là đủ. Cách đó dễ bỏ sót build number, nhãn pre-release, metadata hoặc những thành phần bị lược bỏ. API `Runtime.Version` hiểu cấu trúc phiên bản và cung cấp các thành phần bằng kiểu dữ liệu phù hợp.

## 11. So sánh hai phiên bản

So sánh version string bằng thứ tự từ điển có thể cho kết quả sai. Ví dụ, chuỗi `21.0.10` có thể bị so sánh nhỏ hơn `21.0.9` nếu so sánh từng ký tự, vì ký tự `1` ở vị trí thứ hai của `10` đứng trước `9`.

Hãy phân tích thành `Runtime.Version` rồi dùng `compareTo`:

```java
public class CompareJdkVersions {
    public static void main(String[] args) {
        Runtime.Version installed = Runtime.Version.parse("21.0.10+7");
        Runtime.Version minimum = Runtime.Version.parse("21.0.9+5");

        if (installed.compareTo(minimum) >= 0) {
            System.out.println("Runtime meets the minimum version");
        } else {
            System.out.println("Runtime is older than the minimum version");
        }
    }
}
```

`compareTo` so sánh theo cấu trúc phiên bản thay vì thứ tự ký tự. Với ứng dụng kiểm tra phiên bản tối thiểu, cần xác định rõ chính sách so sánh: chỉ cần cùng feature release hay phải đạt một update/patch cụ thể. Nếu chính sách còn phụ thuộc nhà cung cấp hoặc build, cần kiểm tra các thông tin đó riêng vì bốn thành phần số không nhận diện đầy đủ toàn bộ bản phân phối.

## 12. Phân biệt scheme JDK với Semantic Versioning

Thư viện Java và nhiều phần mềm khác thường dùng Semantic Versioning (SemVer) theo dạng `MAJOR.MINOR.PATCH`. JDK từ Java 10 dùng `FEATURE.INTERIM.UPDATE.PATCH`. Hai quy ước có số lượng thành phần nhìn gần giống nhau nhưng ý nghĩa khác nhau.

| Chuỗi | Cách hiểu |
|---|---|
| JDK `21.0.2` | Feature 21, interim 0, update 2, patch 0. |
| Thư viện `2.1.0` theo SemVer | Major 2, minor 1, patch 0 theo hợp đồng SemVer của thư viện. |

Không nên áp dụng máy móc quy tắc SemVer cho JDK. Trong SemVer, thành phần thứ hai thường là minor và thành phần thứ ba là patch. Trong JDK version string, thành phần thứ hai là interim và thành phần thứ ba là update.

Điều này cũng có nghĩa rằng `21.0.2` không phải “JDK major 21, minor 0, patch 2” theo cách gọi SemVer. Đó là JDK feature 21, interim 0, update 2.

## 13. Phiên bản JDK trước JDK 10

Các phiên bản Java cũ dùng quy ước khác, vì vậy không thể áp dụng cách tách bốn thành phần của JEP 322 cho mọi chuỗi lịch sử.

### Java 8 và các bản trước đó

Java 8 thường hiển thị dạng:

```text
1.8.0_402
```

Trong chuỗi này, `1.8` nhận diện Java 8 theo quy ước cũ; phần `_402` là số update được hiển thị theo định dạng lịch sử. Không được đọc `1.8.0_402` như `FEATURE.INTERIM.UPDATE.PATCH`.

### Java 9

JDK 9 chuyển sang scheme phiên bản mới theo JEP 223, với chuỗi ví dụ như `9.0.4`. Từ JDK 10, JEP 322 tiếp tục điều chỉnh scheme và định nghĩa rõ các thành phần feature, interim, update và patch.

Khi viết script quản lý nhiều thế hệ JDK, cần xác định scheme dựa trên phiên bản hoặc dùng thư viện/parser hiểu các dạng lịch sử. Một script chỉ tách dấu chấm có thể xử lý sai Java 8, Java 9 hoặc các chuỗi có build metadata.

## 14. Liên hệ với migration và tương thích ứng dụng

Đọc phiên bản JDK là bước đầu của migration. Con số phiên bản không tự chứng minh ứng dụng tương thích với JDK mới. Cần phân biệt một số lớp thông tin:

| Thông tin | Trả lời câu hỏi nào? | Cách kiểm tra |
|---|---|---|
| Feature release | Ứng dụng đang chạy trên thế hệ JDK nào? | `java -version`, `Runtime.version().feature()` |
| Update/patch | Runtime đã nhận mức cập nhật nào trong feature release đó? | Version string, `update()` và `patch()` |
| Build/vendor | Bản runtime cụ thể do ai cung cấp và được build ra sao? | Output `java -version`, thuộc tính hệ thống, metadata bản phân phối |
| Compile target | Mã nguồn được biên dịch để chạy trên Java release nào? | Cấu hình compiler và tùy chọn `--release` |
| Runtime thực tế | Tiến trình ứng dụng đang dùng JVM nào? | Log khi khởi động, `Runtime.version()`, cấu hình service/container |

Ví dụ, một dự án có thể được biên dịch bằng JDK 21 nhưng tạo bytecode tương thích với Java 17 thông qua `javac --release 17`. Điều đó không có nghĩa ứng dụng đang chạy trên JDK 17. Compile target và runtime version là hai thông tin riêng.

Khi nâng cấp feature release:

1. Xác định JDK nguồn và JDK đích, bao gồm vendor, build và update level.
2. Đọc release notes và các thay đổi có thể ảnh hưởng đến API, JVM, GC, module, TLS, charset hoặc công cụ.
3. Kiểm tra thư viện, plugin build, agent và framework có hỗ trợ feature release đích không.
4. Biên dịch với cấu hình mục tiêu đã chọn và chạy test trên runtime đích.
5. Triển khai thử ở môi trường staging, theo dõi log, metric, hiệu năng và lỗi tương thích.

Khi nâng update hoặc patch trong cùng feature release, vẫn cần kiểm thử hồi quy. Update có thể sửa lỗi hoặc thay đổi hành vi ở những tình huống trước đây vốn phụ thuộc vào lỗi cũ. Patch release cũng cần được đánh giá theo nội dung bản sửa và thông báo của nhà cung cấp.

## 15. Ghi nhận phiên bản trong log và hồ sơ triển khai

Để có thể tái tạo môi trường, ứng dụng hoặc pipeline triển khai nên ghi lại phiên bản runtime lúc khởi động. Ví dụ:

```java
public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static void logVersion() {
        Runtime.Version version = Runtime.version();

        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.runtime.version="
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
        System.out.println("jdk.feature=" + version.feature());
        System.out.println("jdk.interim=" + version.interim());
        System.out.println("jdk.update=" + version.update());
        System.out.println("jdk.patch=" + version.patch());
    }
}
```

Trong hệ thống thực tế, nên dùng logger của ứng dụng thay vì `System.out.println`. Thông tin này hữu ích khi so sánh hai pod, hai máy chủ hoặc hai lần triển khai. Không cần ghi lặp lại ở mọi request; ghi một lần lúc khởi động thường đủ để xác định runtime của tiến trình.

Một hồ sơ triển khai có thể lưu các trường:

- JDK distribution và vendor.
- Feature, interim, update, patch.
- Build number và kiến trúc.
- Giá trị `JAVA_HOME` hoặc đường dẫn runtime của tiến trình.
- Compile target và phiên bản toolchain dùng khi build.
- Ngày cập nhật và mã image/container nếu ứng dụng chạy trong container.

Khi so sánh môi trường, hãy kiểm tra cả runtime thực tế bên trong container. JDK trên máy host có thể khác JDK được đóng gói trong image.

## 16. Những nhầm lẫn thường gặp

**Coi số cuối cùng nhìn thấy là patch.** Trong `21.0.2`, số `2` là update; patch component bằng `0` và bị lược bỏ.

**Coi số sau dấu `+` là patch.** Trong `21.0.2+13`, `13` là build number.

**Coi LTS là thành phần phiên bản.** LTS là nhãn/chính sách hỗ trợ, không thuộc bốn thành phần số.

**Cho rằng cùng feature release nghĩa là cùng runtime.** `21.0.1` và `21.0.2` cùng feature 21 nhưng khác update.

**Dùng quy tắc SemVer để đọc JDK.** JDK dùng feature/interim/update/patch, không phải major/minor/patch theo SemVer.

**Chỉ kiểm tra `java -version` trên terminal.** IDE, Maven, Gradle, service manager và container có thể dùng JDK khác. Hãy kiểm tra runtime thực tế của tiến trình cần điều tra.

**Cho rằng update release là feature release mới.** Update thường tập trung vào sửa lỗi và bảo mật; feature component vẫn giữ nguyên.

**Áp dụng scheme JDK 10+ cho Java 8.** Java 8 dùng định dạng lịch sử như `1.8.0_402`; cần parser hoặc quy tắc riêng cho chuỗi cũ.

## 17. Checklist khi đọc và ghi nhận phiên bản JDK

- [ ] Đã lấy version string từ đúng runtime đang chạy ứng dụng.
- [ ] Đã xác định feature component.
- [ ] Đã đọc interim, update và patch đúng vị trí.
- [ ] Đã phân biệt build number sau dấu `+` với patch component.
- [ ] Đã nhận diện pre-release hoặc metadata nếu có.
- [ ] Đã ghi nhận vendor, distribution và build khi cần tái tạo môi trường.
- [ ] Đã kiểm tra compiler/toolchain riêng với runtime.
- [ ] Đã phân biệt compile target với phiên bản JVM thực tế.
- [ ] Đã xác định scheme lịch sử nếu phải xử lý JDK 8 hoặc phiên bản cũ hơn.
- [ ] Đã đối chiếu release notes và chính sách hỗ trợ trước khi nâng cấp.

## Kết luận

JDK từ phiên bản 10 sử dụng quy ước `FEATURE.INTERIM.UPDATE.PATCH`. Feature nhận diện thế hệ JDK; interim biểu thị mốc phát hành trung gian; update biểu thị bản cập nhật định kỳ; patch biểu thị bản sửa riêng. Build number, nhãn pre-release, metadata và LTS cung cấp thêm thông tin nhưng không thay thế các thành phần số này. Khi migration, hãy đọc version string từ đúng runtime, ghi nhận vendor/build, phân biệt compile target với runtime và kiểm thử theo phạm vi thay đổi của từng loại release.
