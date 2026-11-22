# Phiên bản theo lịch phát hành của Java — mô hình time-based release (Java 10+)

## 1. Tại sao phải hiểu mô hình phiên bản?

Java không chỉ có “một bản mới mỗi khi tính năng lớn hoàn tất”. Từ giai đoạn Java 9–10, hệ sinh thái JDK chuyển sang **nhịp phát hành có lịch dự kiến** (*time-based release model*), trong đó bản **feature release** được lên lịch khoảng **sáu tháng một lần**, thường vào tháng 3 và tháng 9.

Đối với lập trình viên, DBA, DevOps và nhóm phụ trách sản phẩm, thay đổi này ảnh hưởng trực tiếp đến:

- **Khi nào** một bản JDK mới được phát hành chính thức (*General Availability — GA*).
- **Cách đọc số phiên bản**: ví dụ `10`, `10.0.2`, `25.0.1+8-LTS` và `27.0.1` mang các ý nghĩa khác nhau.
- **Phân biệt cập nhật tính năng và cập nhật bảo mật/sửa lỗi**.
- **Lựa chọn LTS và non-LTS** theo chính sách hỗ trợ của nhà cung cấp thay vì chỉ theo “số mới nhất”.
- **Đặt mục tiêu biên dịch và chạy** cho ứng dụng, container, pipeline CI/CD.
- **Xác minh Java thực tế** đang chạy trong production bằng `java --version`, `javac --version` và API `Runtime.version()`.
- **Theo dõi vòng đời hỗ trợ**, cập nhật bản vá và đánh giá mức tương thích khi nâng cấp.

Bài này thuộc chủ đề cha **Mô hình phiên bản**, gắn với **Java 10**: JEP 322 (*Time-Based Release Versioning*) được triển khai ở Java 10 và định nghĩa cấu trúc số phiên bản hiện đại. Các nguyên tắc mô hình, API và quy trình lựa chọn JDK nêu trong bài **vẫn được sử dụng trong Java hiện nay**, không khuyến nghị triển khai một bản JDK cũ đã hết hỗ trợ cộng đồng chỉ để làm theo bài học.

### Một câu ghi nhớ

**Feature release đến theo nhịp khoảng sáu tháng; update release vá lỗi trên một nhánh; LTS là chính sách hỗ trợ dài hạn của nhà cung cấp; version number cho biết nhánh và mức cập nhật, chứ không tự cam kết một thời gian hỗ trợ hoặc khả năng tương thích.**

## 2. Lịch phát hành feature: tháng 3 và tháng 9

Theo mô hình hiện hành, các **feature release** của JDK thường được công bố GA vào khoảng **giữa tháng 3 và giữa tháng 9**. Mỗi kỳ feature làm tăng bộ đếm **FEATURE** một đơn vị, bất kể release đó có bao nhiêu tính năng lớn.

Một số mốc lịch sử và hiện hành dùng để định vị chu kỳ:

| JDK feature release | Mốc GA | Ý nghĩa trong mô hình |
| --- | --- | --- |
| **Java 10** | 20/03/2018 | Feature release tháng 3; JEP 322 mô tả cấu trúc version theo lịch |
| **Java 11** | 25/09/2018 | Feature tiếp theo khoảng sáu tháng sau; bản LTS theo roadmap Oracle |
| **Java 17** | 14/09/2021 | Một mốc LTS khác theo lịch tháng 9 |
| **Java 21** | 19/09/2023 | Mốc LTS tháng 9 |
| **Java 25** | 16/09/2025 | Mốc LTS tháng 9; đến 07/11/2026 vẫn là bản LTS mới nhất theo Oracle |
| **Java 26** | 17/03/2026 | Feature release tháng 3, non-LTS |
| **Java 27** | 15/09/2026 | Feature release tháng 9, non-LTS; **bản feature GA mới nhất vào 07/11/2026** |
| **Java 28** | Dự kiến 03/2027 | Lịch tương lai, **chưa được phát hành** tính đến ngày nói trên |
| **Java 29** | Dự kiến 09/2027 | Oracle dự kiến một mốc LTS tiếp theo; kế hoạch có thể điều chỉnh |

Các ngày lịch sử và trạng thái 2026 được đối chiếu với [Oracle JDK 27 release announcement](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/), [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) và [JDK release timeline](https://ops.java/releases/). **Lịch dự kiến không phải bản phát hành đã có**; hãy kiểm tra trang release chính thức khi cập nhật bài hoặc lập kế hoạch triển khai trong tương lai.

### “Theo lịch” không có nghĩa “mọi feature đều hoàn tất đúng hạn”

Khi tới kỳ phát hành, một tính năng chưa đáp ứng tiêu chí chất lượng/cấu hình thích hợp có thể bị chuyển sang kỳ sau. Nhờ vậy kế hoạch phát hành **không phải chờ tất cả tính năng trong một nhóm lớn hoàn tất**.

Điểm quan trọng là **số FEATURE tăng theo release**, chứ không phải có số “major” mới chỉ khi một tính năng đặc biệt xuất hiện. Một feature release có thể đem tới thay đổi thư viện, runtime, hiệu năng, hành vi bảo mật, preview/incubator hoặc công cụ. Không thể suy ra “JDK 27 chắc chắn chứa tính năng X” chỉ từ con số 27; phải đọc release notes/JEP của bản đó.

### GA, EA và update là ba trạng thái khác nhau

- **EA (*Early Access*)**: bản dùng để thử và phản hồi trước GA; không coi là bản sản xuất ổn định nếu chưa có chính sách chấp nhận rõ.
- **GA (*General Availability*)**: bản phát hành chính thức của feature release.
- **Update**: phiên bản cập nhật cho một nhánh đã phát hành nhằm sửa lỗi/bảo mật và vấn đề phù hợp với chính sách nhánh.

Một build có `-ea` trong version string cần được phân biệt với bản GA; chỉ so sánh số FEATURE sẽ che giấu sự khác biệt này.

## 3. “Sáu tháng” không đồng nghĩa thời gian hỗ trợ chỉ sáu tháng cho mọi bản

Có **hai lịch độc lập**:

1. **Lịch ra feature release:** khoảng sáu tháng một lần, từ Java 10 đến nay.
2. **Lịch cung cấp bản cập nhật và hỗ trợ:** khác nhau theo nhánh LTS/non-LTS và theo nhà cung cấp/distribution, hợp đồng, chính sách cấp bản vá.

Một non-LTS thường bị feature kế tiếp thay thế trong dòng phát hành chính của Oracle sau khoảng sáu tháng; điều đó **không có nghĩa** một bản LTS cũng bị dừng vá ngay sau sáu tháng. Nhà cung cấp có thể tiếp tục duy trì các nhánh LTS nhiều năm.

Ví dụ Java 25 LTS vẫn được Oracle công bố với lịch hỗ trợ dài hạn dù Java 26 rồi Java 27 ra sau nó. Không đọc “FEATURE lớn nhất” là “bản nên dùng cho tất cả hệ thống production”.

**LTS (*Long-Term Support*) là một cam kết hỗ trợ/phân phối**, không phải một từ khóa Java hoặc một khả năng của JVM được đảm bảo bởi ngôn ngữ. Các nhà cung cấp JDK có thể có lịch và điều khoản khác nhau. Xem roadmap của **đúng vendor đang dùng**, không chỉ đọc blog giới thiệu Java chung.

## 4. JEP 322 và định dạng version number hiện đại

JEP 322 định nghĩa bốn thành phần đầu của số phiên bản:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

Đây là **mô hình thành phần**; không phải lúc nào cả bốn số đều xuất hiện. Một số phiên bản **không có số 0 ở cuối**: các thành phần bằng 0 ở phía cuối được lược bỏ. Nếu thành phần ở giữa bằng 0 nhưng thành phần sau khác 0, số 0 ở giữa vẫn phải được giữ.

| Thành phần | Vai trò theo JEP 322 | Ví dụ |
| --- | --- | --- |
| `FEATURE` | Bộ đếm feature release, tăng ở mỗi kỳ theo lịch | `25`, `26`, `27` |
| `INTERIM` | Dự phòng cho interim release với thay đổi tương thích theo mô hình; trên nhịp sáu tháng thông thường **là 0** | Số thứ hai của `27.0.1` là `0` |
| `UPDATE` | Bộ đếm update release: vá lỗi bảo mật, regression, lỗi sản phẩm | Số `1` của `27.0.1` |
| `PATCH` | Bộ đếm emergency patch khi cần sửa lỗi nghiêm trọng ngoài chu kỳ bình thường | Có thể xuất hiện thành phần thứ tư khác 0 |

Ví dụ:

```text
27        -> FEATURE=27, INTERIM=0, UPDATE=0, PATCH=0
27.0.1    -> FEATURE=27, INTERIM=0, UPDATE=1, PATCH=0
25.0.2    -> FEATURE=25, INTERIM=0, UPDATE=2, PATCH=0
```

Cảnh báo: **`27.0.1` không phải feature release 27.1**. Nó là bản update thứ nhất trên nhánh feature 27 theo sơ đồ. Tương tự, `25.0.2` không nhất thiết có API mới theo nghĩa feature release 26.

Đừng gắn các nhãn kiểu “major.minor.patch” của semantic versioning chung vào bốn thành phần của JDK rồi suy luận tính tương thích. Chính JEP 322 định nghĩa ý nghĩa các thành phần này.

## 5. Quy tắc bỏ số 0 cuối và các thành phần mở rộng

Các phiên bản dưới đây minh họa việc **bỏ zero cuối**:

```text
10         // không phải 10.0.0.0
10.0.1     // INTERIM=0 phải giữ để UPDATE=1 ở đúng vị trí
25.0.2     // PATCH=0 bị lược bỏ
```

Nếu có phiên bản vendor-specific, **thành phần thứ năm trở đi** được dành cho consumer hoặc implementor của mã JDK để đánh dấu các mức patch riêng.

Ví dụ một vendor có thể cung cấp version number có nhiều hơn bốn phần tử như:

```text
27.0.1.0.3
```

Theo cấu trúc JEP 322:

- `FEATURE=27`
- `INTERIM=0`
- `UPDATE=1`
- `PATCH=0`
- Thành phần thứ năm `3` là **thông tin bổ sung theo implementor**, không phải tự động là PATCH tiêu chuẩn thứ tư.

Không tự gán ý nghĩa phổ quát cho từng phần mở rộng của tất cả vendor. Khi cần xử lý, dùng `Runtime.Version` hoặc tài liệu chính thức của bản distribution đang chạy.

Một số release notes của Oracle có thể công bố version cụ thể với 5 thành phần; mã ứng dụng vẫn nên đọc bằng API thay vì tự cắt từng dấu chấm rồi giả định luôn có đúng bốn trường.

### So sánh version bằng số, không bằng chuỗi

So sánh trực tiếp:

```java
"10.0.9".compareTo("10.0.10")
```

có thể cho thứ tự **sai** vì so sánh theo ký tự: `"9"` và `"10"` không được hiểu là số nguyên theo cách mong muốn.

Dùng API:

```java
Runtime.Version v9 = Runtime.Version.parse("10.0.9");
Runtime.Version v10 = Runtime.Version.parse("10.0.10");

boolean newer = v9.compareTo(v10) < 0;
```

Điều này dùng quy tắc so sánh phiên bản của Java, không phải lexical ordering. Trong code production, nên xác định rõ bạn muốn so sánh **version number**, **pre-release**, **build** hay **vendor optional data**, vì full version string và chính sách chọn bản cập nhật có thể phức tạp hơn một phép so sánh duy nhất.

## 6. Update release và lịch vá lỗi

Sau một kỳ feature release, các bản **update** thường được phát hành theo lịch khoảng **ba tháng một lần**. Với mô hình sáu tháng, các đợt phát hành tính năng vào tháng 3 và 9, còn các đợt update bảo mật chính thường gắn với **tháng 1, 4, 7 và 10**.

Theo mô hình của JEP 322:

- Một tháng sau feature release, update đầu tiên thường xuất hiện: ví dụ Java 10 phát hành tháng 3/2018, rồi có `10.0.1` tháng 4/2018.
- Các update tiếp theo trên nhánh tương ứng tăng `UPDATE`, chẳng hạn `10.0.2`.
- Trong LTS, nhánh được duy trì có thể tiếp tục nhận nhiều bản cập nhật qua các năm theo chính sách của vendor.
- Một bản khẩn cấp (*out-of-band patch*) có thể xuất hiện ngoài lịch, khi cần xử lý sự cố đặc biệt.

Không nhầm các khái niệm:

| Loại release | Mục đích nổi bật | Thay đổi số |
| --- | --- | --- |
| **Feature** | Tích lũy thay đổi ngôn ngữ/API/runtime theo chu kỳ | Tăng `FEATURE` |
| **Update** | Vá bảo mật, regression và bug fixes | Tăng `UPDATE` theo nhánh |
| **Emergency patch** | Vá vấn đề khẩn cấp đặc biệt | Có thể tăng `PATCH` |
| **Vendor-specific patch** | Bản sửa riêng của implementor | Có thể thêm thành phần số phiên bản từ vị trí thứ năm |

**Số VERSION tăng không phải bảo đảm số lỗi được sửa hoặc mức độ an toàn của deployment.** Bạn vẫn cần đọc advisories và release notes của đúng vendor, đối chiếu CVE/configuration liên quan và kiểm tra ứng dụng.

### Không suy từ ngày phát hành ra version chính xác

Ngày ấn định trên lịch có thể được dời hoặc có bản update ngoài chu kỳ. Cũng có những bản sửa riêng mà các JDK distribution đặt tên khác nhau. Vì vậy, lịch giúp **lập kế hoạch**, nhưng khi triển khai phải xác thực **artifact/build cụ thể** mà registry hoặc vendor đã phát hành.

## 7. Version string: pre-release, build và thông tin tùy chọn

**Version number** chỉ là một phần của **version string** đầy đủ. Có những dạng được JEP 322 mô tả:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+- $OPT)?    // Chỉ là minh họa vị trí phần tùy chọn.
```

Để tránh nhầm với cú pháp regex, một số ví dụ *thực tế hợp lệ* minh họa:

```text
10
10.0.2
11-ea+13
25.0.1+8-LTS
27.0.1
```

Ý nghĩa:

- `11-ea+13`: feature 11, nhãn pre-release `ea`, build 13.
- `25.0.1+8-LTS`: feature 25, update 1, build 8 và trường optional ghi `LTS` (ví dụ một version string hợp lệ).
- `27.0.1`: chỉ có version number; không chứa build/optional information trong chuỗi được phân tích.
- Thông tin sau `+` thường liên quan build hoặc optional metadata, không được hiểu là một feature mới.
- Ký hiệu `-ea` (early access) không có nghĩa build đã GA.

**Độ dài chuỗi, build label và optional data phụ thuộc distribution.** JEP 322 cho phép một số thông tin tùy chọn trong version string; đừng tạo parser chỉ dựa vào dấu `-` và `+` rồi giả định mọi vendor in giống nhau.

### LTS không phải một số thứ năm

Một chuỗi có `-LTS` là một gợi ý mà implementor có thể đưa vào thông tin version. Việc lựa chọn bảo trì và quyền nhận bản vá còn phụ thuộc chính sách hỗ trợ của nhà cung cấp. Do đó, **không viết logic “chỉ khi java --version có chữ LTS thì bản này mới là LTS”**.

Phân loại LTS cho mục tiêu vận hành nên dựa vào roadmap công khai/hợp đồng với vendor đang dùng. Trong Java SE, không tồn tại một API chuẩn “isLongTermSupported()” xác nhận thời hạn bảo trì cho mọi JDK distribution.

## 8. Những mốc LTS nên biết ở thời điểm hiện tại

Tính đến **07/11/2026**, theo Oracle Java SE Support Roadmap:

- Java **8, 11, 17, 21, 25** thuộc các dòng được Oracle chỉ định LTS.
- Java **25 LTS** (09/2025) là dòng LTS gần nhất đã GA.
- Java **27** (15/09/2026) là feature release gần nhất đã GA, nhưng thuộc dòng **non-LTS**.
- Java **29** mới là mốc **LTS dự kiến** trong kế hoạch tháng 9/2027, chưa phải một bản GA có sẵn.

Đừng hiểu “Java 8 là LTS” nghĩa là mọi binary Java 8 còn an toàn hoặc được cung cấp bản vá miễn phí cho mọi mục đích ở mọi vendor. **LTS là loại chính sách hỗ trợ, không phải bảo đảm cho mọi build/giấy phép**.

Với một sản phẩm mới, đánh giá một nhánh LTS đang được vendor hỗ trợ thường hợp lý khi cần ít nâng cấp feature và có chiến lược update ổn định. Với ứng dụng mong muốn tận dụng tính năng mới, có thể chọn nhánh non-LTS nhưng phải chấp nhận lịch **nâng feature khoảng sáu tháng**.

Không khẳng định mọi LTS luôn có vòng đời cố định 5 hoặc 10 năm: số năm và loại hỗ trợ phụ thuộc vendor, phiên bản, giấy phép và từng mức hỗ trợ.

## 9. Phân biệt Java SE, JDK, runtime, distribution và LTS

Một câu báo “ứng dụng chạy Java 25” vẫn **chưa đủ thông tin vận hành**.

| Khái niệm | Nội dung | Ví dụ câu hỏi cần kiểm tra |
| --- | --- | --- |
| **Java SE specification** | Đặc tả nền tảng/ngôn ngữ/thư viện | App dùng API Java SE feature nào? |
| **JDK feature version** | Nhánh phát hành, ví dụ 25/27 | JDK đang sử dụng feature nào? |
| **JDK update/build** | Bản vá cụ thể trong nhánh | Đã nhận bản cập nhật bảo mật thích hợp chưa? |
| **Distribution/vendor** | Nhà cung cấp binary và chính sách hỗ trợ | Oracle, Temurin, Corretto hoặc nhà cung cấp khác? |
| **LTS/non-LTS** | Hỗ trợ dài hạn hay chu kỳ ngắn theo vendor | Hợp đồng/support roadmap áp dụng tới khi nào? |
| **Build toolchain** | JDK dùng để biên dịch/đóng gói | CI có khớp production không? |
| **Application runtime** | JVM thật sự chạy process | Image/container/service dùng java binary nào? |

**Tên feature release không chỉ ra build của JVM đang chạy**, và version string không tự nói mức hỗ trợ thương mại.

Một ứng dụng có thể biên dịch bằng JDK mới nhưng đặt target tương thích cũ; ngược lại, một service đang dùng JDK feature cũ có thể được vendor duy trì theo hợp đồng. Việc chọn runtime phải dựa vào ít nhất: compatibility, update/security, phụ thuộc, môi trường deployment và chính sách support.

Không đưa đánh giá bản LTS về “đúng/sai tuyệt đối” mà không xét mục tiêu release cadence của dự án.

## 10. Kiểm tra phiên bản thực tế trên máy và trong container

Trước khi nâng cấp hoặc debug hành vi khác nhau, cần **đo phiên bản thực tế** thay vì dựa vào tên folder hoặc dòng cấu hình tài liệu.

Các lệnh thông dụng:

```bash
java --version
javac --version
```

Ví dụ output có thể có phần tên vendor, version, ngày phát hành, build, thông tin runtime/VM. Nội dung chính xác phụ thuộc distribution nên **không cố lấy một stdout của một máy làm chuẩn cho mọi JDK**.

Phải kiểm tra **cả hai lệnh**: trong một số môi trường, `java` đang chạy từ runtime khác với `javac` trên `PATH`. Nếu dùng container, chạy lệnh **bên trong image/container thực tế**, không chỉ ở laptop.

Một số kiểm tra bổ sung cho từng môi trường:

```bash
java -XshowSettings:properties -version
```

Lệnh này giúp xem thông tin property, ví dụ vị trí `java.home`, version của runtime và cấu hình JVM. Đầu ra có thể dài và chứa đường dẫn máy, nên tránh đưa nguyên văn vào log công khai nếu không cần.

Với build tool, đối chiếu **Gradle/Maven toolchain**, compiler fork, runtime dùng để chạy unit test và runtime thật khi deploy. “JDK 25 trong IDE” không chứng minh pipeline hoặc production đều chạy JDK 25.

### Phiên bản của thư viện hoặc framework là chuyện khác

Đừng suy từ `java --version` ra phiên bản Spring Boot, JUnit, Maven hoặc plugin build. Cần kiểm tra cả artifact dependency và ma trận tương thích riêng. JDK feature number là **một trục** trong nhiều trục version của sản phẩm.

## 11. Dùng Runtime.version() và Runtime.Version từ Java 10+

Nếu cần tự kiểm tra runtime từ mã Java, dùng API có kiểu rõ ràng:

```java
Runtime.Version current = Runtime.version();

int feature = current.feature();
int interim = current.interim();
int update = current.update();
int patch = current.patch();
```

`Runtime.version()` cung cấp version của runtime đang chạy. API `Runtime.Version` có từ Java 9 và các accessor `feature()`, `interim()`, `update()`, `patch()` được đưa vào theo JEP 322 ở Java 10.

Đọc thêm:

- `current.pre()`: `Optional<String>` mô tả nhãn pre-release, nếu có.
- `current.build()`: `Optional<Integer>` mô tả build number, nếu có.
- `current.optional()`: thông tin optional phụ thuộc implementor, nếu có.
- `current.version()`: các thành phần số phiên bản.
- `Runtime.Version.parse(text)`: tạo đối tượng version từ một chuỗi hợp lệ.
- `compareTo(...)`: so sánh theo quy tắc version của Java, không phải string.

### Đừng kiểm tra version bằng cách so chuỗi tay

Sai:

```java
// Chỉ là so chuỗi, không phải so sánh version theo số:
boolean newer = "10.0.10".compareTo("10.0.9") > 0;
```

Đúng hơn:

```java
Runtime.Version a = Runtime.Version.parse("10.0.10");
Runtime.Version b = Runtime.Version.parse("10.0.9");

boolean newer = a.compareTo(b) > 0;
```

**Cũng đừng dùng một phép so sánh version để tuyên bố tính năng có sẵn mọi nơi**: preview/removed API, sự khác biệt platform, flags và distribution có thể ảnh hưởng. Khi thực thi tính năng cụ thể, kiểm tra feature flag/API availability theo hợp đồng mà tính năng đó yêu cầu.

## 12. Ví dụ Java 10 hoàn chỉnh: phân tích version string có cấu trúc

Tạo file **`ReleaseCalendarVersionDemo.java`**:

```java
import java.lang.Runtime;
import java.util.List;

public final class ReleaseCalendarVersionDemo {
    static void inspect(String input) {
        Runtime.Version v = Runtime.Version.parse(input);
        System.out.println(input
                + " -> feature=" + v.feature()
                + ", interim=" + v.interim()
                + ", update=" + v.update()
                + ", patch=" + v.patch()
                + ", pre=" + v.pre().orElse("none")
                + ", build=" + v.build().map(Object::toString).orElse("none")
                + ", optional=" + v.optional().orElse("none"));
    }

    public static void main(String[] args) {
        inspect("10");
        inspect("10.0.2");
        inspect("11-ea+13");
        inspect("25.0.1+8-LTS");
        inspect("27.0.1");

        Runtime.Version older = Runtime.Version.parse("25.0.1+8");
        Runtime.Version newer = Runtime.Version.parse("25.0.2+1");
        System.out.println("updateAscending=" + (older.compareTo(newer) < 0));

        Runtime.Version feature10 = Runtime.Version.parse("10");
        Runtime.Version feature11 = Runtime.Version.parse("11");
        System.out.println("featureAscending=" + (feature10.compareTo(feature11) < 0));

        Runtime.Version current = Runtime.version();
        System.out.println("runtimeFeaturePositive=" + (current.feature() >= 10));
        System.out.println("runtimeVersionFromAPI=" + current);
        System.out.println("javaSpecVersion="
                + System.getProperty("java.specification.version"));
    }
}
```

Biên dịch và chạy bằng JDK có hỗ trợ target Java 10:

```bash
javac --release 10 ReleaseCalendarVersionDemo.java
java ReleaseCalendarVersionDemo
```

**Những dòng đầu ra cố định được kiểm chứng bằng cách chạy chương trình:**

```text
10 -> feature=10, interim=0, update=0, patch=0, pre=none, build=none, optional=none
10.0.2 -> feature=10, interim=0, update=2, patch=0, pre=none, build=none, optional=none
11-ea+13 -> feature=11, interim=0, update=0, patch=0, pre=ea, build=13, optional=none
25.0.1+8-LTS -> feature=25, interim=0, update=1, patch=0, pre=none, build=8, optional=LTS
27.0.1 -> feature=27, interim=0, update=1, patch=0, pre=none, build=none, optional=none
updateAscending=true
featureAscending=true
```

**Phần phụ thuộc runtime**, tại môi trường thực nghiệm đã chạy (JDK 24.0.2):

```text
runtimeFeaturePositive=true
runtimeVersionFromAPI=24.0.2+12
javaSpecVersion=24
```

Cần hiểu chính xác:

1. Năm dòng `inspect` được **parse từ chuỗi thử nghiệm** và không phụ thuộc runtime thực tế đang là Java 24, 25 hay 27. Chúng **không có nghĩa** máy đã cài tất cả những phiên bản JDK đó.
2. `Runtime.Version.parse("11-ea+13")` phân tích một **chuỗi mô phỏng** early access, không chứng minh máy đang chạy bản preview.
3. `25.0.1+8-LTS` trong ví dụ chỉ cho thấy *optional metadata* có giá trị `LTS` trong chuỗi đã nhập, không chứng minh build này có support contract cụ thể.
4. `updateAscending=true` và `featureAscending=true` cho thấy `Runtime.Version.compareTo` hiểu thứ tự số phiên bản.
5. `runtimeVersionFromAPI` mới phản ánh **JVM thật đang chạy process**; nó sẽ khác nếu chạy cùng chương trình trong một container/JDK khác.
6. `javaSpecVersion` là property của runtime hiện tại, không phải danh sách JDK khả dụng.
7. Với JDK cũ hơn feature được yêu cầu bởi chương trình, việc gọi API không tồn tại sẽ không thành công. Ví dụ dùng các accessor từ Java 10 để phù hợp phiên bản module.

**Không dùng output runtimeFeaturePositive làm bài kiểm tra Java 10 độc lập:** dòng này chỉ là một boolean đơn giản cho môi trường thực nghiệm, không thể thay kiểm tra đầy đủ về API và policies.

Nếu sản phẩm muốn ghi nhận thông tin môi trường để hỗ trợ vận hành, log có thể chứa `Runtime.version()`, vendor metadata và build ID; không cần log dữ liệu cá nhân/secret để chẩn đoán version.

## 13. Một runtime cũ có thể chạy mã biên dịch bằng JDK mới không?

Có ba ý tưởng rất dễ nhầm:

1. **JDK dùng biên dịch**: bản cài tại môi trường build.
2. **Java language/API target**: mức ngôn ngữ và API mà ứng dụng được phép sử dụng.
3. **JVM thực tế**: runtime sẽ load và chạy class.

Ví dụ:

```bash
javac --release 10 ReleaseCalendarVersionDemo.java
```

`--release 10` (nếu JDK compiler đang dùng còn hỗ trợ target này) yêu cầu compiler giới hạn **cú pháp, class file version và public Java SE API** theo mức Java 10. Đây là lựa chọn an toàn hơn việc chỉ dùng `-source 10 -target 10` khi bạn muốn tránh vô tình tham chiếu API mới.

Nhưng `--release 10` **không làm runtime hiện tại biến thành JDK 10** và **không khẳng định mọi lỗi hành vi ở Java 10 đã được test**. Để chắc chắn ứng dụng chạy trên một JVM mục tiêu, phải chạy bộ test với runtime mục tiêu hoặc môi trường tương thích được quản lý.

Một JDK mới có thể **ngừng hỗ trợ một số target quá cũ** trong javac, tùy phiên bản compiler. Đừng hard-code rằng mọi JDK tương lai vĩnh viễn hỗ trợ `--release 10`; kiểm tra `javac --help` và chính sách build toolchain.

### Vì sao class-file version quan trọng?

Một class được compile ở mức target mới hơn có thể không load được trên JVM cũ, báo `UnsupportedClassVersionError`. Ngược lại, class-file target tương thích không đảm bảo ứng dụng sẽ chạy nếu thiếu một Java SE API được dùng động, một thư viện native hoặc một tính năng runtime.

Một pipeline có thể kiểm tra:

- Target `--release` đã được đặt rõ.
- Build agent đang dùng compiler dự kiến.
- Unit/integration tests chạy với JDK production mục tiêu.
- Container image pin JDK/patch version đúng.
- Nếu đa JDK, sử dụng test matrix cho các nhánh được hỗ trợ.

**Kết luận:** Calendar versioning giúp biết lịch nâng cấp, nhưng **không thay thế kiểm thử binary/API compatibility**.

## 14. Feature release không có nghĩa mọi JEP đã trở thành tính năng ổn định

Mỗi feature release có thể bao gồm:

- Tính năng đã được hoàn thiện/thành tiêu chuẩn;
- **Preview features**, phải bật bằng cờ thích hợp trong những phiên bản hỗ trợ;
- **Incubator modules/APIs**, có thể thay đổi khi phát triển;
- Thay đổi runtime, hiệu năng, bảo mật, API và các tính năng chuẩn bị loại bỏ trong tương lai.

Không lấy “một JEP đã xuất hiện ở release 27” làm bằng chứng tính năng đó đã ổn định, có thể bật mặc định hoặc sẽ giữ nguyên signature trên mọi release tiếp theo. Cần đọc **trạng thái của JEP trong chính release notes**.

Lịch phát hành sáu tháng giúp tính năng chưa sẵn sàng có thể chuyển sang kỳ sau. Preview/incubator là cơ chế để trải nghiệm và thu phản hồi, nhưng không nên đưa vào yêu cầu sản phẩm mà không xác định rõ vòng đời/mức tương thích và cờ build/run.

Trong tổ chức cần bảo đảm ổn định, việc dùng nhánh LTS vẫn không loại bỏ nhu cầu đọc deprecations, removals và các thay đổi hành vi trong từng lần nâng feature.

## 15. Chọn LTS hay non-LTS trong một dự án thực tế

Không có một câu trả lời cố định cho mọi hệ thống. Dùng các yếu tố sau để quyết định:

| Nhu cầu | Hướng lựa chọn | Điều phải kiểm tra |
| --- | --- | --- |
| Ứng dụng production cần hỗ trợ dài hạn, ít nâng feature | Cân nhắc một nhánh LTS đang được vendor duy trì | Roadmap, license, patch cadence, dependency compatibility |
| Nhóm muốn dùng tính năng mới sớm và có CI tốt | Có thể dùng non-LTS | Kế hoạch nâng sau khoảng sáu tháng, kiểm thử API |
| Dịch vụ với nhiều phụ thuộc/native libraries | Ưu tiên JDK được tất cả thành phần quan trọng hỗ trợ | SDK, agents, DB drivers, OS images, observability |
| Tổ chức nhiều JVM khác nhau | Thiết lập ma trận JDK được hỗ trợ | Cả version feature và update/build |
| Ứng dụng cần bản vá bảo mật nhất quán | Dùng distribution có chu kỳ cập nhật tin cậy | Lịch update/advisory, ngày đã triển khai bản vá |
| Hệ thống không thể nâng feature nhanh | Chọn một nhánh được hỗ trợ dài hạn | Không nhầm “không nâng feature” với “không cập nhật security” |

Một chính sách thực dụng:

1. Chọn một **JDK distribution/vendor** có mức hỗ trợ phù hợp.
2. Chọn **feature branch** dựa vào độ ổn định, LTS và tính năng cần.
3. Pin/ghi nhận **update và build** trong artifact/image hoặc cơ chế quản lý tương ứng.
4. Cập nhật security/fix theo chính sách, không chỉ đợi ngày nâng feature.
5. Tập thử upgrade trước GA trên EA build **nếu có nguồn lực và điều kiện an toàn**, nhưng không phát hành EA vào production nếu policy không cho phép.
6. Dùng CI matrix và kiểm thử hiệu năng, encoding, TLS, JVM flags, GC và dependency khi nâng feature.
7. Ghi thông tin release vào tài liệu vận hành và kiểm tra ngày hỗ trợ kết thúc từ nhà cung cấp.

### Java 10 có phải runtime phù hợp để khởi đầu một dự án mới không?

Java 10 cực kỳ quan trọng **về mặt kiến thức mô hình phiên bản**, nhưng nó là một **non-LTS feature release của năm 2018** và đã được các nhánh sau thay thế trong chu kỳ hỗ trợ chính. Bài Java 10 này dùng các khái niệm xuất hiện tại Java 10; **không khuyến nghị cài Java 10 làm runtime production mới** vào năm 2026.

Nếu dự án mới chọn Java 25 LTS hoặc một nhánh non-LTS hiện hành theo vendor, phần lớn API version model nêu ở đây vẫn dùng được.

## 16. Lỗi phổ biến về release cadence và version

**Lỗi 1 — “Mỗi số Java chỉ thay đổi khi có một tính năng đột phá.”** Sai. `FEATURE` tăng theo chu kỳ release, không theo số lượng tính năng lớn.

**Lỗi 2 — “Java 27 nghĩa là năm 2027.”** Sai. `27` là bộ đếm feature version; Java 27 GA năm **2026**.

**Lỗi 3 — “Java 27 mới nhất nghĩa là luôn nên dùng Java 27.”** Sai. Cần xem LTS, vendor support, security update, dependencies và quy định vận hành.

**Lỗi 4 — “Java 25 LTS ngừng cập nhật khi Java 26 ra.”** Sai theo lộ trình hỗ trợ được Oracle công bố; LTS tiếp tục có lịch cập nhật riêng theo chính sách vendor.

**Lỗi 5 — “`27.0.1` có tính năng Java 27.1.”** Sai. Số `1` nằm ở vị trí `UPDATE`, sau `INTERIM=0`.

**Lỗi 6 — “Version nào cũng có bốn số.”** Sai. Các số 0 cuối thường bị lược bỏ, có chuỗi chỉ gồm `FEATURE` và có thể có thêm thành phần implementor-specific.

**Lỗi 7 — “Số build sau + là số PATCH.”** Sai. `+8` là build component trong version string, không đồng nghĩa `PATCH=8`.

**Lỗi 8 — “Có chữ LTS trong output là hợp đồng bảo trì được bảo đảm, không có chữ LTS là không được hỗ trợ dài hạn.”** Không chính xác. LTS phụ thuộc chính sách vendor, không chỉ vào optional string.

**Lỗi 9 — “Java --version trên laptop cho biết production đang chạy gì.”** Sai. Phải kiểm tra runtime **trong service/container/host thực tế**.

**Lỗi 10 — “javac --release 10 có nghĩa chương trình đang chạy JDK 10.”** Sai. Nó là target biên dịch, không phải thay đổi JVM đang thực thi.

**Lỗi 11 — “Cứ nâng bản feature mà không cần thử ứng dụng.”** Sai. Có thể có thay đổi behavior, dependency/native agent, reflection, JVM flag hoặc API. Cần test.

**Lỗi 12 — “Update đều chính xác sau ba tháng, không cần đọc advisory.”** Sai. Có lịch phổ biến nhưng vẫn có patch khẩn cấp hoặc thay đổi kế hoạch; phải theo release notes.

**Lỗi 13 — “`Runtime.Version.parse` sẽ tự cho biết JDK hiện cài.”** Sai. Nó chỉ phân tích chuỗi truyền vào; `Runtime.version()` mới phản ánh runtime hiện tại.

**Lỗi 14 — “So version bằng `String.compareTo` là đủ.”** Sai. Lexical ordering không tương đương numeric/version ordering.

**Lỗi 15 — “Một bản preview trong feature release đã là API ổn định.”** Sai. Phải kiểm tra trạng thái và yêu cầu bật/tương thích theo JEP.

## 17. Checklist vận hành và code review

- [ ] Đã phân biệt **feature release** (nhịp sáu tháng) với **update/patch release**.
- [ ] Đã xác định version theo cấu trúc `FEATURE.INTERIM.UPDATE.PATCH`, không đọc như semantic versioning chung.
- [ ] Không suy `FEATURE` từ năm hoặc ngược lại.
- [ ] Có phân biệt EA/GA và thông tin build/optional.
- [ ] Nếu chọn LTS, đã đọc chính sách của **đúng JDK vendor/distribution**.
- [ ] Nếu chọn non-LTS, đã có kế hoạch nâng feature trong vòng đời ngắn hơn.
- [ ] Đã kiểm tra runtime trong production bằng `java --version` / `Runtime.version()`, không chỉ ở local.
- [ ] Đã kiểm tra compiler và target `javac --release` nếu cần giữ tương thích.
- [ ] Không so version bằng chuỗi trực tiếp; dùng `Runtime.Version` khi xử lý version JDK trong Java.
- [ ] Các JEP preview/incubator chỉ được dùng khi có policy hỗ trợ và test đầy đủ.
- [ ] Bản cập nhật bảo mật được theo dõi theo lịch vendor, không chỉ ngày GA của feature mới.
- [ ] CI/CD có test matrix phiên bản thực tế được hỗ trợ, kể cả distribution khác nhau nếu sản phẩm yêu cầu.
- [ ] Deployment pin/update được artifact có thể tái lập và biết rõ build identity.
- [ ] Khi nâng JDK, đã test thư viện, toolchain, TLS, encoding, GC và application startup.
- [ ] Tài liệu ghi thời điểm tham chiếu các thông tin “mới nhất/LTS”, tránh biến trạng thái năm 2026 thành khẳng định vĩnh viễn.

## 18. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Vì sao Java 10 và Java 11 chỉ cách nhau khoảng sáu tháng?

**Đáp án:** Mô hình time-based release lên lịch feature release khoảng sáu tháng một lần, thường tháng 3 và tháng 9. `FEATURE` tăng theo mỗi kỳ, không đợi một tập lớn tính năng hoàn tất.

**Câu 2.** Số `27.0.1` có nghĩa là “Java 27 feature 0, patch 1” không?

**Đáp án:** Không. Theo JEP 322: FEATURE=27, INTERIM=0, UPDATE=1, PATCH=0. Số 1 nằm ở vị trí update.

**Câu 3.** Vì sao `25.0.2` không phải viết `25.0.2.0`?

**Đáp án:** Những thành phần zero cuối được lược bỏ theo quy tắc version number. PATCH=0 mặc định.

**Câu 4.** `11-ea+13` cho biết gì?

**Đáp án:** Feature=11, pre-release=ea, build=13. Đây là một version string mẫu; nó không chứng minh máy đang chạy JDK 11.

**Câu 5.** Java 27 đã GA tháng 9/2026; Java 25 LTS có tự ngừng được vendor hỗ trợ không?

**Đáp án:** Không. Các nhánh LTS có vòng đời cập nhật/hỗ trợ riêng theo vendor. Lịch feature GA và lịch support là hai việc khác nhau.

**Câu 6.** Tại sao không chọn JDK production bằng cách lấy số FEATURE cao nhất?

**Đáp án:** Cần xét LTS, vendor support/licensing, security updates, dependency compatibility, vận hành và khả năng nâng feature. “Mới nhất” không thay mọi tiêu chí lựa chọn.

**Câu 7.** `Runtime.Version.parse("27.0.1")` có cho biết chương trình đang chạy Java 27 không?

**Đáp án:** Không. Phương thức chỉ phân tích chuỗi đã nhập. Dùng `Runtime.version()` hoặc `java --version` của JVM đang chạy để biết runtime thật.

**Câu 8.** Vì sao không so `"10.0.9"` với `"10.0.10"` bằng `String.compareTo`?

**Đáp án:** So chuỗi theo thứ tự ký tự không phải so các thành phần version theo số; dùng `Runtime.Version.parse(...).compareTo(...)`.

**Câu 9.** `+8` trong chuỗi `25.0.1+8-LTS` là PATCH=8 hay build=8?

**Đáp án:** Là **build=8**. PATCH vẫn 0 do không có thành phần PATCH khác 0 trong VNUM.

**Câu 10.** LTS là API trả boolean từ JVM à?

**Đáp án:** Không. Đó là chỉ định hỗ trợ của vendor/distribution; optional `-LTS` có thể xuất hiện trong version string nhưng không thay hợp đồng support.

**Câu 11.** `javac --release 10` bảo đảm code chạy đúng trên JVM feature 10 chưa?

**Đáp án:** Chưa. Nó giới hạn ngôn ngữ/API/class-file target khi compiler hỗ trợ; vẫn cần chạy test trên runtime mục tiêu và kiểm tra dependencies, config.

**Câu 12.** Lịch feature và lịch update thường khác nhau thế nào?

**Đáp án:** Feature khoảng sáu tháng một lần, còn các update/security patch thường theo quý và có thể có bản ngoài chu kỳ. Phải kiểm tra thông báo của vendor.

**Câu 13.** Tính đến ngày 07/11/2026, bản GA gần nhất và bản Oracle LTS mới nhất là gì?

**Đáp án:** JDK 27 GA ngày 15/09/2026 là feature release mới nhất; JDK 25 GA tháng 9/2025 là dòng LTS mới nhất theo roadmap Oracle ở thời điểm này.

**Câu 14.** Nếu một tính năng được đưa vào JDK feature release dưới dạng preview, có nên coi nó là API ổn định không?

**Đáp án:** Không. Phải kiểm tra trạng thái JEP, cờ bật và quy tắc tương thích trước khi đưa vào hợp đồng production.

## 19. Tài liệu chính thức và cách cập nhật kiến thức

1. [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình feature/interim/update/patch và version string.
2. [Oracle — Version-String Format](https://docs.oracle.com/en/java/javase/23/install/version-string-format.html): cách đọc version number trong mô hình sáu tháng; quy tắc lược bỏ zero cuối.
3. [Java SE — Runtime.Version](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.Version.html): `feature()`, `interim()`, `update()`, `patch()`, `pre()`, `build()` và `parse()`.
4. [Java SE — Runtime.version()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#version()): hỏi phiên bản runtime hiện tại.
5. [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): các nhánh LTS/non-LTS và thời hạn hỗ trợ (khác biệt theo vendor).
6. [Oracle — Java 27 GA announcement, 15/09/2026](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/): ví dụ bản feature đã GA gần nhất tại thời điểm biên soạn.
7. [OpenJDK — JDK Releases](https://jdk.java.net/): các build GA/early access và thông tin JDK từ OpenJDK.
8. [Oracle — Java Platform, Standard Edition Documentation](https://docs.oracle.com/en/java/javase/): tài liệu cho phiên bản nền tảng đang sử dụng và release notes.

**Lưu ý cập nhật:** Các mốc “mới nhất” trong bài được kiểm chứng **đến 07/11/2026**. Khi đọc hoặc tái sử dụng sau thời điểm đó, hãy kiểm tra lại **JDK GA, lịch support và policy của vendor**; mô hình JEP 322 và cách dùng API `Runtime.Version` là những kiến thức nền đang tiếp tục áp dụng.

**Kết luận:** Java 10 đánh dấu mô hình phiên bản theo lịch được làm rõ trong JEP 322: **feature tăng theo nhịp khoảng sáu tháng**, **update/patch** được quản lý riêng, còn **LTS** thuộc về chiến lược hỗ trợ của nhà cung cấp. Hiểu đúng `FEATURE.INTERIM.UPDATE.PATCH`, build metadata và runtime thực tế sẽ giúp chọn JDK, triển khai bản vá và xây dựng ma trận kiểm thử một cách có cơ sở — không dựa vào cảm giác “số càng lớn càng tốt”.
