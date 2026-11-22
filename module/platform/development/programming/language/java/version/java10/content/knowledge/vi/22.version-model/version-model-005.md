# Phân biệt số phiên bản Java với chính sách hỗ trợ của nhà cung cấp (Java 10+)

## 1. Mục tiêu và vấn đề thực tế

Khi kiểm tra một máy chủ, bạn thấy:

```text
openjdk version "25.0.5" ...
```

hoặc nhận được yêu cầu “dịch vụ phải dùng **Java LTS**”. Chỉ nhìn số `25` hoặc `25.0.5` **chưa đủ** để kết luận máy chủ có còn nhận bản vá bảo mật, có hợp đồng hỗ trợ, được phép sử dụng dưới giấy phép nào hoặc tương thích với hệ điều hành nào.

Từ Java 10, mô hình đánh số phiên bản được làm rõ theo **JEP 322 — Time-Based Release Versioning**. Mô hình này phục vụ nhận diện **mốc tính năng, bản cập nhật, bản vá và build**. Trong khi đó, lịch **LTS (Long-Term Support)**, lịch hết hạn hỗ trợ, kênh cung cấp cập nhật, SLA và điều khoản cấp phép là **chính sách của bên phát hành bản phân phối JDK**. Hai hệ thống thông tin này có liên quan nhưng **không thay thế nhau**.

Ví dụ cùng một feature version `25` nhưng các lựa chọn sau có thể khác về thời hạn hỗ trợ và cách nhận bản vá:

- Oracle JDK 25;
- Eclipse Temurin 25;
- Amazon Corretto 25;
- Azul Zulu 25;
- một bản OpenJDK do tổ chức tự build và bảo trì.

Các sản phẩm có thể cùng tuân theo Java SE 25 và dùng nền tảng OpenJDK, nhưng **không cùng hợp đồng hỗ trợ hoặc lịch phát hành bản vá**.

**Mục tiêu học tập:**

1. Đọc được chuỗi phiên bản Java 10+ theo `FEATURE.INTERIM.UPDATE.PATCH`, phân biệt `+BUILD`, `-ea` và nhãn `LTS`.
2. Hiểu chu kỳ release sáu tháng **không** đồng nghĩa mỗi release được hỗ trợ trong một thời hạn cố định ở mọi vendor.
3. Phân biệt Java SE specification, OpenJDK project, binary distribution, giấy phép và dịch vụ hỗ trợ.
4. Xác minh runtime thực tế bằng `java --version`, `Runtime.version()` và các system properties.
5. Lập quyết định triển khai dựa trên **bằng chứng hỗ trợ cập nhật của đúng nhà cung cấp**, không chỉ dựa vào một số phiên bản.
6. Tránh khuyến nghị dùng Java 10 đã cũ làm runtime production chỉ vì bài học thuộc module Java 10; chỉ dùng kiến thức **vẫn còn áp dụng đến hiện nay**.

Bài viết đối chiếu tài liệu nhà cung cấp ở thời điểm **tháng 11 năm 2026**. Những mốc hỗ trợ dưới đây là **snapshot theo chính sách được công bố**, có thể thay đổi; phải kiểm tra lại trang chính thức khi quyết định vận hành.

## 2. Ba tầng cần tách bạch

### Tầng A — Phiên bản nền tảng Java

Một **Java SE feature release** như Java 17, 21, 25 hay 27 xác định tập tính năng ngôn ngữ, Java SE API và hợp đồng tương thích được đặc tả ở release tương ứng.

Ví dụ:

- `Java SE 25` là tên phiên bản đặc tả/nền tảng.
- Một JDK 25 có thể biên dịch và chạy những tính năng ổn định của Java SE 25.
- Bản cập nhật `25.0.5` thuộc **dòng feature version 25**, có thể bao gồm các bản sửa và cập nhật bảo mật.

**Không được suy ra** rằng một bản JDK 25 bất kỳ đều đang ở mức cập nhật mới nhất hoặc mọi bản JDK 25 có cùng các bản vá vendor-specific. Số phiên bản giúp xác định dòng sản phẩm; cần biết cả **build cụ thể**.

### Tầng B — Nhà cung cấp bản phân phối và binary thực tế

**OpenJDK** là dự án triển khai mã nguồn mở của Java Platform. Nhiều tổ chức xây dựng và phát hành những **binary distributions** từ nguồn OpenJDK, chẳng hạn Oracle OpenJDK builds, Eclipse Temurin, Amazon Corretto và Azul Zulu.

Từng bản phân phối có thể khác về:

- lịch phát hành những bản build đã qua kiểm thử;
- các nền tảng OS/architecture được cung cấp;
- bản vá backport và quy trình xác minh;
- công cụ đóng gói, runtime image và các sửa đổi được nhà cung cấp công bố;
- kênh tải xuống, thông báo lỗ hổng và kênh hỗ trợ.

Không có quy tắc “tên bản phân phối chứa chữ OpenJDK thì mọi bên nhận cùng một bảo hành”. **Đúng binary và đúng nguồn phát hành** mới là đối tượng cần đánh giá.

### Tầng C — Chính sách hỗ trợ và điều kiện sử dụng

Một vendor có thể mô tả:

- **LTS:** dòng sản phẩm nhận bảo trì dài hơn các feature releases thông thường.
- **Feature release / short-term support:** dòng được thay thế nhanh khi feature release tiếp theo xuất hiện.
- **Production/Premier support:** thời kỳ nhận các bản sửa/bản vá và hỗ trợ theo điều khoản áp dụng.
- **Extended/Sustaining/maintenance phases:** tên gọi khác nhau theo vendor, **không nhất thiết** tiếp tục nhận mọi bản vá mới.
- **Community support:** báo lỗi qua cộng đồng và nhận các binary builds mới khi dự án duy trì, khác với hợp đồng hỗ trợ có SLA.
- **Commercial support:** quyền lợi hỗ trợ được quy định bằng sản phẩm, hợp đồng và điều khoản cụ thể.

**Một nhãn `LTS` không tự động cho bạn bản vá, SLA hoặc quyền sử dụng thương mại vô thời hạn.** Cần đọc đúng chính sách của binary distribution và entitlement mà tổ chức đang có.

## 3. Mô hình đánh số phiên bản từ Java 10 — JEP 322

Java 9 có JEP 223 về scheme mới, nhưng **JDK 10/JEP 322** tinh chỉnh cách gọi tên các thành phần để phù hợp mô hình release theo thời gian. Chữ ký tổng quát:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

Các thành phần `0` ở cuối có thể được lược bỏ trong chuỗi hiển thị.

| Thành phần | Ý nghĩa trong mô hình hiện hành | Ví dụ |
| --- | --- | --- |
| `FEATURE` | Dòng tính năng được tăng theo chu kỳ phát hành, khoảng sáu tháng | `25`, `26`, `27` |
| `INTERIM` | Dành cho những interim releases tương thích nếu có; trong mô hình sáu tháng hiện tại thường là `0` | `25.0...` |
| `UPDATE` | Bộ đếm bản cập nhật gồm sửa lỗi, hồi quy, bảo mật và các bản sửa phù hợp | `25.0.5` có update `5` |
| `PATCH` | Bộ đếm emergency patch release | `25.0.5.1` có patch `1` |

**Đừng đọc `25.0.5` theo lối “major 25, minor 0, security level 5”.** Từ Java 10, thành phần thứ ba có nghĩa là **update-release counter**, chứ không phải “mức độ an toàn” hoặc số lượng lỗ hổng được sửa.

### 3.1. Chuỗi phiên bản còn có pre-release và build

Chuỗi release đầy đủ có thể chứa:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+- $OPT)?   (viết cách chỉ để mô tả)
```

Trong cú pháp thực tế của `Runtime.Version`, không có dấu cách tùy ý. Các mẫu phổ biến dễ đọc hơn:

```text
10.0.2+13
25.0.5+8-LTS
27-ea+5
27.0.1+9
```

Ý nghĩa:

- `10.0.2+13`: feature `10`, interim `0`, update `2`, build `13`.
- `25.0.5+8-LTS`: feature `25`, update `5`, build `8`; `LTS` là **optional build information** trong chuỗi ví dụ.
- `27-ea+5`: bản **early access**, build `5`; `ea` là pre-release indicator.
- `27.0.1+9`: feature `27`, update `1`, build `9`.

Đây là **các ví dụ chuỗi hợp cú pháp để học cách đọc**, không phải bằng chứng rằng đúng build đó hiện được vendor nào phân phối hoặc hỗ trợ.

### 3.2. Mốc thời gian release và update

Dưới mô hình phát hành sáu tháng:

- Feature release được phát hành khoảng **tháng 3 và tháng 9**.
- Các đợt sửa lỗi/bảo mật thông thường của những dòng đang được duy trì đi theo lịch **hàng quý**, thường vào tháng **1, 4, 7, 10**.
- Bản vá khẩn cấp có thể xuất hiện ngoài nhịp thông thường, tùy vendor và mức độ sự cố.
- Không phải mọi dòng feature đều được tất cả vendor duy trì cùng thời gian.

Ví dụ tại **ngày 7/11/2026**, Java **27** đã được phát hành tháng 9/2026, còn Java **25** là dòng **LTS** đã phát hành tháng 9/2025. Java **29** đang được **lên kế hoạch** là LTS tiếp theo vào tháng 9/2027, **chưa phải release hiện có** ở mốc thời gian của bài.

Từ đó: “phiên bản mới nhất” và “dòng LTS phù hợp cho hệ thống cần vòng đời hỗ trợ dài” **có thể là hai số khác nhau**.

## 4. Làm sao đọc phiên bản bằng API Java?

Java có API `Runtime.Version` để parse và thao tác có kiểu thay vì tự cắt chuỗi.

```java
Runtime.Version release = Runtime.Version.parse("25.0.5+8-LTS");

System.out.println(release.feature());             // 25
System.out.println(release.interim());             // 0
System.out.println(release.update());              // 5
System.out.println(release.patch());               // 0
System.out.println(release.build().orElse(-1));     // 8
System.out.println(release.optional().orElse(""));  // LTS
```

Các dòng này đặt trong một phương thức Java 10+; ví dụ chạy đầy đủ ở phần 12.

`Runtime.Version` có các API quan trọng:

| API | Mục đích |
| --- | --- |
| `Runtime.version()` | Phiên bản của **runtime đang chạy** dưới dạng `Runtime.Version`; API có từ Java 9 |
| `Runtime.Version.parse(String)` | Parse một chuỗi phiên bản đúng scheme |
| `feature()`, `interim()`, `update()`, `patch()` | Đọc các thành phần số phiên bản với ý nghĩa từ Java 10 |
| `pre()` | `Optional<String>` chứa pre-release marker, ví dụ `ea` |
| `build()` | `Optional<Integer>` chứa build number |
| `optional()` | `Optional<String>` chứa thông tin build bổ sung, ví dụ chữ `LTS` trong ví dụ |
| `compareTo(...)` | So thứ tự các chuỗi phiên bản theo hợp đồng của API |

**Không dùng** các accessor legacy `major()`, `minor()`, `security()` để diễn giải scheme Java 10+: những tên này đã được đánh dấu deprecated vì nghĩa cũ có thể gây hiểu nhầm. Dùng `feature()`, `interim()`, `update()`, `patch()` là cách hiện hành.

### 4.1. `compareTo` chỉ so phiên bản, không so vòng đời

```java
var lts = Runtime.Version.parse("25.0.5+8-LTS");
var newest = Runtime.Version.parse("27.0.1+9");

System.out.println(newest.compareTo(lts) > 0); // true
```

`27` có feature number lớn hơn `25`; điều đó **không** chứng minh một binary Java 27 có lịch hỗ trợ dài hơn dòng Java 25 LTS.

`Runtime.Version.compareTo` không gọi website vendor, không biết hợp đồng mua hỗ trợ, không kiểm tra bản vá mới nhất và không có cơ chế đánh giá chính sách giấy phép.

### 4.2. Nhãn `-LTS` trong build không phải bằng chứng SLA

Một số build hiển thị `LTS` trong tên runtime; một số không. Với chuỗi ví dụ `25.0.5+8-LTS`, `optional()` trả về `"LTS"`, nhưng đó chỉ là **thông tin build**.

**Không viết kiểm tra:**

```java
// Không dùng làm tiêu chí duy nhất cho production support:
// boolean supported = Runtime.version().optional()
//        .orElse("").contains("LTS");
```

Tại sao sai? Có thể một dòng từng được coi là LTS nhưng đã qua thời hạn nhận bản vá của một vendor, hoặc đang ở chế độ không có SLA với khách hàng hiện tại. Ngược lại, một bản phân phối đang được hỗ trợ có thể không đặt chữ `LTS` ở vị trí bạn đang kiểm tra.

Không có một API chuẩn kiểu `Runtime.version().isSupportedByVendorUntil(date)` trong Java SE.

## 5. “LTS” là lựa chọn duy trì dòng code, không phải một mức tính năng

LTS (*Long-Term Support*) mô tả **lựa chọn đầu tư bảo trì** của nhà cung cấp. Nó **không** phải tính năng ngôn ngữ riêng và không tạo ra Java SE specification khác biệt.

Một JDK 25 LTS và một JDK 27 feature release có **hai mức tính năng ngôn ngữ/API** tương ứng với `25` và `27`; khác biệt hỗ trợ lại đến từ vendor và release channel.

| Điều bạn quan tâm | Số phiên bản có trả lời đủ không? | Cần xem thêm |
| --- | --- | --- |
| Có API/ngôn ngữ của Java 25 không? | Có cơ sở qua `FEATURE=25`, cần kiểm tra preview/điều kiện cụ thể | Java SE 25/JDK API, flags |
| Chạy class file được biên dịch với `--release 17`? | Có cơ sở về baseline, nhưng chưa đủ toàn hệ thống | Runtime mục tiêu, dependencies, native libraries, test |
| Có bản vá bảo mật quý tiếp theo? | Không | Vendor support matrix và update channel |
| Có hỗ trợ Linux ARM64 trong bản build cụ thể? | Không | Supported platform matrix |
| Có quyền sử dụng Oracle JDK trong môi trường thương mại? | Không | License của đúng release/build và quyền lợi hiện có |
| Có SLA hoặc hỗ trợ sự cố P1/P2? | Không | Hợp đồng support và gói dịch vụ |
| Có thể dùng đến năm 2032? | Không | Vendor roadmap, giai đoạn và ngày EOL |
| Có nhận thêm bản vá sau khi “Premier” kết thúc? | Không | Có Extended/Sustaining không; loại sửa nào đi kèm |

### 5.1. Nhiều định nghĩa “hỗ trợ”

Một chữ `supported` trên trang download có thể chỉ việc binary còn được phát hành. Nó **không mặc định** bao gồm:

- bản vá CVE ngoài lịch cố định;
- hợp đồng tư vấn sản xuất theo giờ trực;
- quyền mở ticket ưu tiên;
- backward compatibility cho mọi thư viện third-party;
- hỗ trợ nền tảng OS/CPU đã hết hạn;
- giấy phép cho mọi hình thức triển khai.

Đặc biệt, **Sustaining Support** của một vendor có thể vẫn tồn tại sau khi giai đoạn phát hành bản vá thông thường đã kết thúc. Đừng hiểu “Sustaining Support: Indefinite” là **bản vá bảo mật mới vô thời hạn**.

### 5.2. Community builds và commercial SLA là hai chuyện

Dự án **Eclipse Temurin** công bố hỗ trợ cộng đồng cho release binaries, có kênh nhận issue và phát hành bản build tiếp theo khi có sửa lỗi. Nhưng **Eclipse Foundation không trực tiếp bán gói commercial support/SLA**; tổ chức muốn gói dịch vụ có thể làm việc với những công ty cung cấp hỗ trợ trên Temurin.

Việc chọn Temurin có thể hoàn toàn phù hợp với triển khai production nếu đáp ứng tiêu chí của tổ chức. Điều cần tránh là suy diễn “Temurin miễn phí = không có cập nhật” hoặc “Temurin có community support = công ty đã có hợp đồng hỗ trợ 24/7”.

## 6. Đối chiếu các nhà cung cấp: cùng số feature, khác lịch hỗ trợ

Bảng dưới đây trích ý chính từ **roadmap chính thức được công bố tới tháng 11/2026**. Chỉ lấy các mốc minh họa cho việc phân biệt **version** và **vendor policy**; không dùng nó làm chứng chỉ hỗ trợ cho một binary cụ thể về sau.

| Dòng Java | Oracle Java SE (khách hàng có entitlement phù hợp) | Amazon Corretto | Azul Zulu/Azul Core |
| --- | --- | --- | --- |
| **25 (LTS)** | Premier Support tới **9/2030**, Extended Support tới **9/2033** | Corretto 25 LTS: công bố EOL **10/2032** | Azul Core 25: Production Support tới **9/2033**, có thêm giai đoạn Extended Support theo chính sách |
| **27 (feature/short-term)** | Non-LTS: Premier Support tới **3/2027**, không có Extended Support trong bảng | Corretto 27 feature release: hỗ trợ tới **4/2027** | Azul Core 27 STS: Production Support tới **3/2027** |

Nguồn đối chiếu: Oracle Java SE Support Roadmap (cập nhật 4/8/2026), AWS Corretto FAQ/thông báo GA 17/9/2026 và Azul Support Roadmap. **Các mốc là chính sách từng sản phẩm, không phải thuộc tính do `Runtime.Version` tính ra.**

Một ví dụ khác từ Eclipse Temurin:

- Temurin duy trì các dòng LTS theo roadmap cộng đồng, với mục tiêu **ít nhất bốn năm** cho dòng LTS theo chính sách được công bố.
- Temurin 25 LTS có kế hoạch tiếp tục cung cấp builds qua một giai đoạn dài, nhưng **support community không đồng nghĩa SLA thương mại**.
- Ngày lên lịch phát hành upstream **không nhất thiết là ngày Temurin build hoàn thành**, vì quá trình kiểm thử/phát hành của họ có độ trễ riêng.

### 6.1. Vì sao cùng Java 25 nhưng ngày EOL khác?

Bởi mỗi bên có quyết định riêng về:

- thời gian backport security patches;
- số phiên bản được duy trì song song;
- vòng đời hệ điều hành/CPU;
- mức phí và điều khoản hỗ trợ;
- khả năng cung cấp bản vá khẩn cấp;
- thời hạn hỗ trợ khách hàng đã ký hợp đồng.

Nhà cung cấp có thể cung cấp hỗ trợ lâu hơn cho một khách hàng hoặc sản phẩm cụ thể **theo hợp đồng**, dù lịch website công bố là mốc chung. Ngược lại, không được mặc định mọi người dùng tải binary trên mạng có quyền hưởng toàn bộ quyền lợi của sản phẩm support trả phí.

### 6.2. Java 10 là trường hợp lịch sử để phân biệt rõ

Java 10 GA **tháng 3/2018**, là một **feature release không-LTS**. Theo Oracle Java SE Support Roadmap, thời kỳ Premier Support cho Java 10 trong lịch non-LTS kết thúc **tháng 9/2018**, khi Java 11 xuất hiện.

Điều này **không** có nghĩa “chạy Java 10 ở năm 2026 sẽ ném exception” hay “mã Java 10 bị cấm học”. Code có thể còn chạy, nhưng một runtime Java 10 cũ **không phải lựa chọn mặc định được khuyến nghị cho hệ thống production hiện nay** nếu không có kế hoạch hỗ trợ/vá lỗi cụ thể từ nhà cung cấp.

Một vendor khác có thể đưa ra dịch vụ ngoại lệ cho dòng cũ; cần kiểm tra đúng hợp đồng. **Đừng suy rằng vì vẫn tải được một binary lịch sử nên nó còn nhận cập nhật bảo mật.**

## 7. Giấy phép sử dụng khác với quyền nhận hỗ trợ

Một điểm thường bị bỏ sót trong audit:

**License to use/download** và **maintenance/support entitlement** là hai câu hỏi riêng.

Ví dụ với Oracle JDK:

- Oracle công bố các bản Oracle JDK 21 và 25 dưới **No-Fee Terms and Conditions** ở những giai đoạn nhất định, nhưng lịch và phạm vi bản cập nhật về sau có thể thay đổi theo release.
- Theo Oracle Support Roadmap cập nhật 4/8/2026, những bản cập nhật Oracle JDK 21 **sau tháng 9/2026** được dự kiến cung cấp theo **Java SE OTN license** thay vì mặc định giữ điều kiện NFTC cũ.
- Oracle JDK 8/11/17 và Oracle OpenJDK builds còn có những điều kiện phân phối/licensing khác.

Không nên từ một câu “Java là mã nguồn mở” mà kết luận **mọi binary Oracle JDK và mọi bản update đều có cùng giấy phép**. Bản thân mã nguồn OpenJDK và binary của một nhà cung cấp là các đối tượng cần phân biệt.

Khi lựa chọn một bản Java, cần kiểm tra **giấy phép áp dụng cho chính artifact tải về và mục đích sử dụng**, **các bản update sau đó**, cùng quy trình nội bộ của tổ chức. Đây là lưu ý kỹ thuật/tuân thủ, **không thay thế tư vấn pháp lý**.

### 7.1. Thông tin cần lấy từ vendor

| Câu hỏi | Cần bằng chứng nào? |
| --- | --- |
| Có được dùng trong production không? | Giấy phép và phạm vi sử dụng của release/build |
| Có cập nhật miễn phí không? | Chính sách public binaries, licensing các updates |
| Có hỗ trợ paid không? | Contract, entitlement, SLA và danh mục supported platforms |
| Khi nào kết thúc hỗ trợ? | Lifecycle/roadmap theo dòng JDK và plan |
| Hết support nhưng còn được chạy? | Tách điều kiện giấy phép khỏi việc nhận bản vá/sự cố |

## 8. Kiểm tra đúng JDK đang chạy trên máy hoặc container

Một ứng dụng Java có thể được build bằng JDK khác với JDK đang chạy. IDE, CLI, CI runner và container image có thể trỏ tới những JDK riêng.

### 8.1. Các câu lệnh chẩn đoán

```bash
java --version
java -version
javac -version
java -XshowSettings:properties -version
```

Kết quả của `java --version`/`-version` thường cho biết feature version, build, runtime/VM và tên distribution. Không dùng một chuỗi stdout cố định cho mọi vendor; ví dụ bên cung cấp có thể ghi `OpenJDK`, `Corretto`, `Temurin`, `Zulu` hoặc tên build riêng.

Với POSIX shell:

```bash
command -v java
command -v javac
```

Trên Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
```

Các lệnh này giúp xác định **đường dẫn thực sự được shell tìm thấy**. Kiểm tra thêm `JAVA_HOME`, `PATH`, toolchains của Gradle/Maven và base image của container. Không dùng mỗi `JAVA_HOME` để đoán JDK khi `PATH` hoặc cấu hình IDE trỏ nơi khác.

### 8.2. Kiểm tra bên trong ứng dụng

```java
Runtime.Version running = Runtime.version();

String javaVersion = System.getProperty("java.version");
String runtimeVersion = System.getProperty("java.runtime.version");
String vendor = System.getProperty("java.vendor");
String vmVendor = System.getProperty("java.vm.vendor");
String javaHome = System.getProperty("java.home");
```

Các dòng trên là mã **đặt trong phương thức**; bản thân chúng không tạo output. Nên ghi những giá trị cần thiết vào diagnostics/health report nội bộ, không tự phát tán đường dẫn local hoặc thông tin hệ thống nhạy cảm ra API public.

**Đọc đúng ý nghĩa:**

- `Runtime.version()`: phiên bản runtime hiện tại dưới dạng đối tượng có kiểu.
- `java.version`/`java.runtime.version`: chuỗi phiên bản implementation/runtime.
- `java.vendor`/`java.vm.vendor`: metadata mà bản build công bố, **không phải một tra cứu trực tuyến bảo đảm hỗ trợ của vendor**.
- `java.home`: nơi runtime đang chạy, giúp điều tra nhiều JDK trên cùng máy.

Không suy ra "bản đang chạy đã được vá tới bản mới nhất" chỉ vì feature và vendor đều đúng. Cần so sánh **update/build cụ thể** với release notes của **đúng nhà cung cấp**.

### 8.3. Container image và base image cũng nằm trong phạm vi hỗ trợ

Nếu chương trình chạy bên trong container:

- `java --version` chạy **bên trong container** mới nói đúng Java của workload.
- Ghi nhận image tag **và digest**, OS packages và architecture.
- Xác minh nguồn image có tiếp tục được rebuild khi có security updates không.
- Kiểm tra chính sách EOL của cả runtime **và hệ điều hành trong image**.
- Nếu image có một runtime do `jlink` tạo ra, xác minh các module đã đóng gói; số phiên bản không tự nói đầy đủ module set.

Không đánh đồng việc kéo lại một image tag `25` với chắc chắn được build mới. Tag có thể mutable, có thể bị pin ở digest cũ hoặc bị mirror nội bộ giữ lại.

## 9. Cập nhật bảo mật: đúng feature chưa chắc đã an toàn

Một feature release LTS như `25` có thể có nhiều update releases `25.0.1`, `25.0.2`, `25.0.5`,... Chỉ biết “chúng tôi chạy Java 25” chưa cho biết đang ở patch level nào.

### 9.1. Chu kỳ CPU/PSU và bản vá ngoài chu kỳ

Nhiều nhà cung cấp phân phối quarterly updates theo lịch phù hợp với OpenJDK. Các khái niệm thường gặp:

- **CPU (Critical Patch Update)**: đợt cập nhật định kỳ tập trung những lỗi quan trọng, bao gồm security;
- **PSU (Patch Set Update)** trong một số hệ sinh thái: tập các bản sửa rộng hơn hoặc kênh cập nhật khác, tùy chính sách nhà cung cấp;
- **Out-of-cycle / emergency patch**: có thể phát hành khi cần xử lý một vấn đề khẩn cấp.

**Không dựa vào tên CPU/PSU mà suy ra số bản vá thực tế của mọi vendor.** Xem advisories, release notes và CVE/security matrix tương ứng.

### 9.2. “Có support” không tự áp bản vá

Ngay cả với một nhà cung cấp công bố LTS đến năm 2033, ứng dụng vẫn có thể ở bản `25.0.1` cũ trong nhiều quý nếu đội vận hành không nâng cấp.

Một hệ thống được bảo trì tốt cần **cả hai**:

1. Dòng Java/binary **vẫn có kênh bản vá đang hoạt động** theo vendor.
2. Quy trình **nhận, kiểm thử, phê duyệt và triển khai cập nhật** theo lịch/chỉ số rủi ro.

Không nên trì hoãn vá các lỗ hổng nghiêm trọng chỉ vì mốc EOL còn xa. Ngược lại, một JDK có update number lớn không chứng minh tất cả rủi ro đã được loại bỏ.

### 9.3. Support ở mức OS/architecture

Bảng support có thể hỗ trợ `Java 25` nói chung nhưng ngừng hỗ trợ một OS hoặc architecture cụ thể sớm hơn. Xem **support matrix cho đúng hệ điều hành, CPU, container base, FIPS/security requirement nếu có**, không chỉ xem bảng vòng đời feature release.

## 10. Khi chọn JDK cho dự án, đặt các câu hỏi theo đúng thứ tự

Một quy trình thực tiễn:

**Bước 1 — Xác định nhu cầu tính năng.** Ứng dụng cần API của Java 17, 21, 25 hay 27? Framework, thư viện và toolchain có yêu cầu version tối thiểu/tối đa không? Dùng preview feature có chấp nhận rủi ro không?

**Bước 2 — Xác định horizon vận hành.** Ứng dụng cần chạy ổn định 6 tháng, 2 năm hay 5 năm? Một feature release không-LTS có thể phù hợp cho thử nghiệm hoặc dự án có kế hoạch nâng version mỗi sáu tháng; không phù hợp nếu tổ chức không có khả năng đó.

**Bước 3 — Chọn distribution thực tế.** Oracle JDK, Temurin, Corretto, Zulu hay một distribution khác có nguồn build rõ ràng, cung cấp đúng OS/architecture và quy trình update đáp ứng tổ chức?

**Bước 4 — Xem roadmap của đúng nhà cung cấp.** Xác minh LTS/non-LTS, chính sách các bản update, EOL, vòng đời hỗ trợ theo plan. **Chụp lại mốc ngày xác minh** vì roadmap có thể thay đổi.

**Bước 5 — Xem license/entitlement.** Có quyền dùng binary và updates không? Có cần hợp đồng SLA? Người chịu trách nhiệm support là dự án cộng đồng, vendor, nhà cung cấp hệ điều hành hay nhà thầu?

**Bước 6 — Quy định patch management.** Ai kiểm tra security advisories? Bao lâu cập nhật bản vá? Cách kiểm thử regression và rollback ra sao? Có cả build/test/runtime environments trong scope không?

**Bước 7 — Kiểm thử trên môi trường production tương đương.** Kiểm tra API, GC/tuning, container image, JNI/native libraries, TLS/certificates, date/time and locale data nếu nghiệp vụ phụ thuộc, rồi ghi nhận binary dùng thực tế.

**Bước 8 — Theo dõi vòng đời.** Đặt mốc review trước khi EOL hoặc giai đoạn miễn phí hết hạn. Đừng đợi đến ngày ngừng phát hành cập nhật mới lập kế hoạch.

Với sản phẩm không bắt buộc sử dụng tính năng rất mới, một **JDK LTS hiện hành được một vendor đáng tin cậy tiếp tục vá** thường là lựa chọn dễ quản lý hơn; nếu cần feature release mới nhất, hãy **có kế hoạch cập nhật sáu tháng một lần** phù hợp lịch support của vendor.

## 11. `javac --release` và tương thích runtime không phải chính sách hỗ trợ

Java hỗ trợ biên dịch hướng tới một phiên bản nền tảng:

```bash
javac --release 17 Example.java
```

Tham số `--release 17` làm `javac` áp dụng source level, target bytecode và Java SE API surface tương ứng Java 17. Nhưng điều đó **không** có nghĩa:

- ứng dụng thực sự đang chạy trên JDK 17;
- JDK 17 mà ứng dụng sẽ deploy còn nhận update từ vendor;
- mọi dependency/native library/third-party SDK đều tương thích;
- bytecode đã được kiểm thử trên mọi distribution Java 17;
- code không thể có lỗi runtime do cấu hình security/TLS/time-zone khác.

Tương tự, việc `java --version` in `25.0.5` không chứng minh rằng source code đã được build bằng JDK 25. Cần kiểm tra **build toolchain và runtime độc lập**.

Dùng build pipeline explicit để kiểm soát toolchain, `--release` và dependency compatibility; dùng vendor roadmap và security pipeline để kiểm soát **vòng đời hỗ trợ**. Đây là **hai mặt bổ sung**, không thể thay thế nhau.

## 12. Chương trình Java 17+ độc lập: đọc version string đúng nghĩa

Ví dụ sau **không tự suy đoán support** từ chuỗi phiên bản. Nó chỉ minh họa những điều Java có thể xác nhận bằng API `Runtime.Version`.

Lưu mã vào **`VersionSupportDemo.java`**:

```java
public class VersionSupportDemo {
    public static void main(String[] args) {
        Runtime.Version old = Runtime.Version.parse("10.0.2+13");
        Runtime.Version lts = Runtime.Version.parse("25.0.5+8-LTS");
        Runtime.Version feature = Runtime.Version.parse("27.0.1+9");
        Runtime.Version early = Runtime.Version.parse("27-ea+5");

        System.out.println("oldFeature=" + old.feature());
        System.out.println("oldInterim=" + old.interim());
        System.out.println("oldUpdate=" + old.update());
        System.out.println("oldPatch=" + old.patch());
        System.out.println("oldBuild=" + old.build().orElse(-1));

        System.out.println("ltsFeature=" + lts.feature());
        System.out.println("ltsUpdate=" + lts.update());
        System.out.println("ltsLabel=" + lts.optional().orElse("none"));

        System.out.println("featureUpdate=" + feature.update());
        System.out.println("featureNewerThanLts=" +
                (feature.compareTo(lts) > 0));
        System.out.println("earlyPre=" + early.pre().orElse("none"));
        System.out.println("earlyBuild=" + early.build().orElse(-1));

        Runtime.Version current = Runtime.version();
        String javaVendor = System.getProperty("java.vendor");
        System.out.println("runtimeFeatureAtLeast17=" +
                (current.feature() >= 17));
        System.out.println("vendorPropertyPresent=" +
                (javaVendor != null && !javaVendor.isBlank()));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 VersionSupportDemo.java
java VersionSupportDemo
```

**Stdout của chương trình trên JDK 17+:**

```text
oldFeature=10
oldInterim=0
oldUpdate=2
oldPatch=0
oldBuild=13
ltsFeature=25
ltsUpdate=5
ltsLabel=LTS
featureUpdate=1
featureNewerThanLts=true
earlyPre=ea
earlyBuild=5
runtimeFeatureAtLeast17=true
vendorPropertyPresent=true
```

Các dòng từ `oldFeature` đến `earlyBuild` xuất phát từ **những version string ví dụ do chương trình tự parse**, không phụ thuộc bản Java đang chạy. `runtimeFeatureAtLeast17` và `vendorPropertyPresent` chỉ kiểm tra runtime thực tế thỏa điều kiện biên dịch/chạy trong thử nghiệm; hai dòng đó **không chứng minh dòng JDK này đang được hỗ trợ**.

### 12.1. Giải thích chi tiết

1. `oldFeature=10` và `oldUpdate=2`: chuỗi `10.0.2+13` thuộc feature 10, update thứ 2; `+13` là build number, không phải ngày kết thúc support.
2. `oldInterim=0`, `oldPatch=0`: khi thành phần vắng mặt hoặc bằng 0, accessor trả 0.
3. `ltsFeature=25` và `ltsUpdate=5`: thuộc feature 25, update 5.
4. `ltsLabel=LTS`: `optional()` đọc marker có trong **chuỗi minh họa**; không có API Java SE nào từ đó tra cứu lịch support.
5. `featureNewerThanLts=true`: Java 27 là version lớn hơn Java 25, không có nghĩa “được hỗ trợ lâu hơn”.
6. `earlyPre=ea`: `ea` là pre-release; đây không phải lựa chọn mặc định cho production vì chưa GA.
7. `vendorPropertyPresent=true` chỉ nói rằng runtime công bố metadata về vendor; muốn biết cụ thể vendor nào và policy nào, phải điều tra thêm từ binary và nguồn chính thức.

**Ví dụ này cố ý không in `java.vendor` hay `Runtime.version()` nguyên văn vào expected stdout**, vì giá trị đó phụ thuộc JDK đang sử dụng. Nếu cần báo cáo chẩn đoán một máy cụ thể, dùng các command ở phần 8 để thu thập riêng.

## 13. Tình huống đánh giá lựa chọn triển khai

### Tình huống A — Chọn giữa Java 27 feature release và Java 25 LTS

Giả sử ứng dụng cần vận hành ít nhất ba năm, không có yêu cầu tính năng chỉ có từ Java 27.

- **Java 27** cung cấp feature level mới hơn và phù hợp khi đội ngũ sẵn sàng theo nhịp release nhanh. Theo roadmap 2026, một số vendor hiện chỉ duy trì Java 27 đến đầu năm 2027.
- **Java 25 LTS** có thể thích hợp hơn cho lịch bảo trì nhiều năm nếu vendor được chọn công bố cập nhật và hỗ trợ theo thời hạn đáp ứng sản phẩm.

Lựa chọn không thể được quyết định chỉ bằng biểu thức `27 > 25`. Hãy đánh giá yêu cầu tính năng, vòng đời hỗ trợ của distribution, license, OS/architecture và chi phí nâng cấp.

### Tình huống B — Một báo cáo bảo mật ghi “Java 17 LTS”

Báo cáo đó **chưa đủ**. Cần bổ sung:

- `17.0.x+build` cụ thể;
- tên distribution/vendor chính xác;
- OS/CPU và image/package đang triển khai;
- release notes và CVE fixes hiện đã tích hợp;
- lịch EOL của **distribution đó**, không chỉ của Java 17 nói chung;
- gói hỗ trợ thực tế của doanh nghiệp (nếu có).

Một JDK 17 LTS nhưng đã lâu không cập nhật vẫn có thể thiếu bản vá đã được nhà cung cấp phát hành.

### Tình huống C — Tài liệu cũ yêu cầu Java 10

Đây là tình huống của nhiều dự án học tập Java 10. Thực hành kiến thức vẫn có giá trị, nhưng hệ thống production mới không nên **mặc định** khóa runtime ở Java 10 đã ngừng hỗ trợ chính thống từ lâu.

Nếu code bắt buộc tương thích Java 10, hãy lập kế hoạch migration tới một JDK còn được cập nhật, kiểm tra dependencies và test behavior. Có thể viết code học thuật theo cú pháp Java 10 trong một JDK mới hơn hoặc cấu hình `--release 10` nếu JDK/toolchain thực sự còn hỗ trợ target đó; **không suy rằng mọi `javac` mới đều hỗ trợ tất cả release cũ vô thời hạn**.

Mục tiêu là **giữ kiến thức còn áp dụng**, chứ không khuyến nghị duy trì một runtime không có kênh vá lỗi.

## 14. Checklist trước khi phê duyệt một Java runtime

Dùng checklist này cho hồ sơ thay đổi hoặc review deployment:

| Câu hỏi kiểm tra | Bằng chứng kỳ vọng |
| --- | --- |
| Runtime thật là gì? | `java --version` từ host/container đang chạy và thông tin build |
| Vendor/distribution nào? | Package name, source/repository hoặc image digest, metadata runtime |
| Feature/update/patch/build cụ thể? | `Runtime.version()`, `java.runtime.version`, release notes |
| Dòng LTS/non-LTS theo **vendor**? | Trang hỗ trợ và ngày kiểm tra chính sách |
| Khi nào hết bản vá/security support? | Lifecycle/EOL và những chú thích theo gói hỗ trợ |
| Có support SLA không? | Hợp đồng, kênh ticket và trách nhiệm xử lý sự cố |
| Giấy phép có phù hợp không? | License của đúng artifact và các bản cập nhật dự kiến |
| OS/architecture được hỗ trợ không? | Supported platforms matrix và tình trạng OS |
| Bản vá nào đã có/đã triển khai? | Advisory/CVE matrix và version hiện tại |
| Khi nào cần nâng cấp? | Mốc review trước EOL và quy trình patching |

**Hãy ghi ngày kiểm chứng policy.** Không biến một bảng static trong tài liệu nội bộ thành “nguồn sự thật” nếu nhà cung cấp đã cập nhật roadmap.

## 15. Lỗi thường gặp và ngộ nhận

**Ngộ nhận 1: “Java 27 mới hơn Java 25 nên được hỗ trợ lâu hơn.”**  
Sai. Số feature chỉ biểu thị dòng tính năng; bản Java 25 LTS có thể được vendor duy trì nhiều năm, trong khi dòng Java 27 không-LTS có lịch ngắn hơn.

**Ngộ nhận 2: “Mọi vendor đều phải hỗ trợ Java 25 đến một ngày giống nhau.”**  
Sai. Oracle, Amazon Corretto, Azul và Temurin có lifecycle và điều kiện khác nhau.

**Ngộ nhận 3: “Chuỗi có `-LTS` là chắc chắn có hỗ trợ trả phí.”**  
Sai. `LTS` có thể là optional build metadata; support cần contract và policy của đúng sản phẩm.

**Ngộ nhận 4: “Cứ nâng update number lớn nhất là đủ an toàn.”**  
Chưa đủ. Cần kiểm tra bản update thực sự của vendor, advisories, OS support và quy trình triển khai, không chỉ so số.

**Ngộ nhận 5: “Java SE 25, OpenJDK 25, Oracle JDK 25 và Corretto 25 đều là tên của một sản phẩm.”**  
Sai. Đó là các tầng specification, project/build và distribution khác nhau.

**Ngộ nhận 6: “Oracle có Sustaining Support vô thời hạn, vậy security updates vô thời hạn.”**  
Sai. Tên giai đoạn hỗ trợ không tự bảo đảm tiếp tục có bản vá mới. Phải đọc rõ quyền lợi của từng phase.

**Ngộ nhận 7: “Java miễn phí luôn đồng nghĩa có commercial SLA.”**  
Sai. License sử dụng, kênh phát hành bản update và SLA là các điều kiện riêng.

**Ngộ nhận 8: “`javac --release 17` bảo đảm production runtime là bản Java 17 mới nhất.”**  
Sai. `--release` là lựa chọn target compilation, không kiểm tra runtime binary hay lịch support.

**Ngộ nhận 9: “`java.vendor` trả tên vendor nên tự xác nhận hợp đồng hỗ trợ.”**  
Sai. System property chỉ là metadata của build; không tra cứu trạng thái entitlement.

**Ngộ nhận 10: “Nếu một bản JDK còn tải được thì vẫn được vá.”**  
Sai. Download availability và security maintenance là hai câu hỏi khác nhau.

**Ngộ nhận 11: “Java 10 còn học được tức là Java 10 còn là runtime tốt cho production mới.”**  
Sai. Khái niệm JEP 322 vẫn hữu ích, nhưng lịch hỗ trợ Oracle của Java 10 đã kết thúc nhiều năm trước.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Chuỗi `25.0.5+8-LTS` cho biết điều gì và không cho biết điều gì?  
**Đáp án:** Cho biết feature 25, interim 0, update 5, build 8 và optional metadata `LTS`. **Không** cho biết deadline EOL, hợp đồng hỗ trợ, điều kiện license hoặc mức vá của vendor so với bản mới nhất.

**Câu 2.** Java 27 có feature number cao hơn Java 25. Có phải mọi bản Java 27 đều phù hợp hơn cho dự án cần vận hành 5 năm?  
**Đáp án:** Không. Phải so nhu cầu API và lịch hỗ trợ theo distribution. Java 25 là dòng LTS có kế hoạch duy trì dài hạn từ nhiều vendor, còn Java 27 là dòng feature release không-LTS.

**Câu 3.** Vì sao `Runtime.Version.compareTo` không thể dùng làm phép so “hỗ trợ lâu hơn”?  
**Đáp án:** Nó chỉ so hai version strings theo scheme, không biết vendor lifecycle hoặc contract.

**Câu 4.** Một bản Oracle JDK và một bản Amazon Corretto cùng là Java 25 có buộc giống lịch EOL không?  
**Đáp án:** Không. Mỗi vendor công bố lộ trình support riêng.

**Câu 5.** `java -version` đã đủ để kết luận bản JDK là bản vá mới nhất chưa?  
**Đáp án:** Chưa. Cần đối chiếu version/build cụ thể với lịch phát hành security updates và advisories của đúng distribution.

**Câu 6.** Có thể dùng `Runtime.Version.optional().orElse("").contains("LTS")` để kiểm tra entitlement không?  
**Đáp án:** Không. Metadata `LTS` không thay cho xác minh support policy và quyền lợi hợp đồng.

**Câu 7.** Nếu `javac --release 17` thành công, có cần kiểm thử trên runtime triển khai thực tế không?  
**Đáp án:** Có. Còn dependencies, native libraries, security provider, container/OS configuration và bản vá thực tế.

**Câu 8.** “Eclipse Temurin có community support” có nghĩa tổ chức đã sở hữu SLA thương mại của Eclipse Foundation chưa?  
**Đáp án:** Không. Trang Adoptium nói Eclipse Foundation không trực tiếp cung cấp commercial support; SLA có thể đến từ các đơn vị thương mại khác.

**Câu 9.** Nếu một bảng Oracle viết “Sustaining Support: Indefinite”, điều gì cần kiểm tra thêm?  
**Đáp án:** Quyền lợi cụ thể của phase đó, đặc biệt là có còn bản vá security mới hay không.

**Câu 10.** Java 10 từ năm 2018 có thuộc LTS theo Oracle không?  
**Đáp án:** Không. Nó là feature release không-LTS; kiến thức về mô hình phiên bản còn giá trị nhưng deployment hiện đại cần runtime được bảo trì đúng chính sách.

## 17. Ghi nhớ

1. **Phiên bản Java trả lời “đây là dòng tính năng/update/build nào”; chính sách vendor trả lời “bản phân phối này được bảo trì, vá và hỗ trợ cho ai, đến khi nào”.**
2. **JEP 322 / Java 10** đưa mô hình `FEATURE.INTERIM.UPDATE.PATCH` vào release cadence sáu tháng; dùng `Runtime.Version` và API `feature/interim/update/patch` thay các tên accessor deprecated.
3. **LTS là cam kết vòng đời bảo trì của từng nhà cung cấp**, không phải kiểu dữ liệu Java, chứng chỉ SLA hay bảo đảm license mặc định.
4. Ở thời điểm **11/2026**, Java **27** là dòng feature mới và Java **25** là LTS hiện hành; ngày EOL của Oracle, Corretto, Azul, Temurin **không nhất thiết giống nhau**.
5. **Giấy phép, support, security patch level, OS/architecture và binary provenance** phải kiểm tra riêng. Có thể có dòng LTS nhưng máy chạy bản cập nhật cũ.
6. Dùng `java --version`, `Runtime.version()` và system properties để biết runtime đang chạy, nhưng phải **đối chiếu vendor roadmap/advisories** để xác nhận khả năng nhận cập nhật.
7. **Java 10 vẫn hữu ích để học** những khái niệm hiện hành; không nên coi một runtime cũ đã hết lịch hỗ trợ chính thống là lựa chọn production mặc định.
8. Khi phê duyệt Java runtime, lưu **version + build + vendor + OS/arch + nguồn binary + quyền sử dụng + ngày EOL + kế hoạch patch**, thay vì chỉ lưu một số `Java 25`.

## Tài liệu tham khảo chính thức và hiện hành

- **JEP 322 — Time-Based Release Versioning** (mô hình từ Java 10): https://openjdk.org/jeps/322
- **Oracle Java SE 27 Installation Guide — Version-String Format**: https://docs.oracle.com/en/java/javase/27/install/version-string-format.html
- **Java SE 27 API — `Runtime.Version`** (`feature`/`interim`/`update`/`patch`/`optional`): https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.Version.html
- **Oracle Java SE 27 Migration Guide — New Version-String Scheme**: https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html
- **Oracle Java SE Support Roadmap** (cập nhật ngày 4/8/2026, LTS/non-LTS và licensing): https://www.oracle.com/java/technologies/java-se-support-roadmap.html
- **Eclipse Adoptium — Temurin Support / Release Roadmap** (community support, lịch build và commercial-support distinction): https://adoptium.net/support/
- **Amazon Corretto — FAQs / support calendar**: https://aws.amazon.com/corretto/faqs/
- **AWS — Amazon Corretto 27 now generally available**, thông báo ngày 17/9/2026: https://aws.amazon.com/about-aws/whats-new/2026/09/amazon-corretto-27-generally-available/
- **Azul — Java Support Roadmap** (LTS/STS theo sản phẩm): https://www.azul.com/products/azul-support-roadmap/
- **Azul — Support Lifecycle**: https://docs.azul.com/core/support-lifecycle
- **Java SE Specifications** (phân biệt đặc tả từng feature): https://docs.oracle.com/javase/specs/
