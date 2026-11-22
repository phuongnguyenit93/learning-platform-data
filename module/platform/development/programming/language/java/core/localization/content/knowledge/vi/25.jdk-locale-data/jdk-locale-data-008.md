# jlink --include-locales và cách kiểm tra dữ liệu locale còn lại trong runtime Java

## 1. Bài toán: runtime nhỏ nhưng không được mất bản địa hóa

Khi đóng gói ứng dụng Java thành một **custom runtime image** bằng `jlink`, nhóm phát triển thường muốn giảm kích thước phân phối: chỉ giữ những module Java thực sự cần thiết. Nếu ứng dụng đa ngôn ngữ, việc cắt module hoặc dữ liệu locale có thể khiến giao diện vẫn chạy, nhưng ngày, số, tiền tệ hoặc tên tháng **không còn định dạng đúng ngôn ngữ**.

Ví dụ ứng dụng cần tiếng Việt, Nhật, Pháp và Anh. Trên JDK phát triển đầy đủ, những locale này có thể được hỗ trợ. Nhưng runtime image chỉ có `java.base` có ít dữ liệu locale hơn. Nếu không chú ý, định dạng số `1234.5` cho `vi-VN` có thể cho dấu nhóm/dấu thập phân kiểu tiếng Anh thay vì quy ước tiếng Việt, **mà chương trình không ném ngoại lệ**.

Java cung cấp plugin:

```text
jlink --include-locales=<langtag>[,<langtag>]*
```

Tùy chọn này giúp **chọn tập dữ liệu locale đóng gói từ module `jdk.localedata`** khi tạo runtime image. Nó không phải câu lệnh cài bộ gõ, không chỉnh ngôn ngữ hệ điều hành, không tự đổi `Locale.getDefault()`, và không tự thêm mọi module mà ứng dụng sử dụng.

Mục tiêu của bài:

1. Hiểu `jlink`, `java.base` và `jdk.localedata` trong mô hình dữ liệu locale.
2. Dùng đúng `--add-modules` cùng `--include-locales`.
3. Hiểu cách chỉ định BCP 47 language tags/ranges và cơ chế lọc.
4. Viết chương trình Java 17+ kiểm tra **những locale thực sự còn được công bố** trong image.
5. Kiểm tra kết quả format của API cụ thể, nhận biết fallback im lặng.
6. Thiết kế bước QA và đóng gói để tránh việc bản địa hóa chỉ đúng trên máy phát triển.

## 2. Module nào chứa dữ liệu locale?

Trong JDK hiện đại có nhiều lớp dữ liệu và API liên quan:

| Thành phần | Vai trò |
|---|---|
| `java.base` | API cốt lõi: `Locale`, `NumberFormat`, `DateFormat`, `DateTimeFormatter`, `ResourceBundle`... và một phần dữ liệu locale cơ sở |
| `jdk.localedata` | Module chứa dữ liệu bản địa hóa bổ sung, thường dùng bởi locale provider CLDR |
| `java.desktop` | Các API desktop như AWT/Swing; chỉ cần khi ứng dụng thực sự sử dụng |
| Module ứng dụng và thư viện | Code cùng resource bundles do dự án và dependencies cung cấp |
| `jlink` | Công cụ liên kết các module thành runtime image có phạm vi nhỏ hơn JDK đầy đủ |

**Điểm quan trọng:** `java.base` không phải “không có locale nào”. Một runtime image chỉ gồm `java.base` vẫn có thể định dạng một số locale cơ sở, đặc biệt các lựa chọn tiếng Anh/root. Tuy nhiên, không nên suy ra nó giữ toàn bộ dữ liệu của JDK đầy đủ.

`jdk.localedata` không phải implementation của `NumberFormat` để bạn import như một package. Nó là **module dữ liệu** mà các locale-sensitive API có thể sử dụng. Khi runtime không có module này hoặc các resource của locale đã bị lọc, cùng một lời gọi API có thể trả về kết quả theo dữ liệu fallback.

### Dữ liệu CLDR và locale provider

Java có cơ chế **locale service providers**. Các JDK hiện đại thường sử dụng dữ liệu **CLDR** (Unicode Common Locale Data Repository) cho nhiều dịch vụ. Hành vi cuối cùng phụ thuộc phiên bản JDK, danh sách provider và tập dữ liệu đã đóng gói.

Có thể đặt property khi kiểm thử:

```bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

Nó giúp thử với provider CLDR một cách rõ ràng, nhưng **không tạo ra dữ liệu locale mới**. Nếu image đã bị cắt bỏ dữ liệu của `de-DE`, đặt provider thành CLDR không làm locale đó tự xuất hiện.

Khi sản phẩm có provider do ứng dụng cung cấp qua SPI hoặc cơ chế khác, kết quả cũng có thể bị ảnh hưởng. Các bài kiểm tra phải phản ánh provider/configuration dùng trong production, không chỉ trạng thái của máy phát triển.

## 3. jlink làm gì và --include-locales lọc ở đâu?

`jlink` đọc các module Java đã biên dịch cùng phần phụ thuộc để tạo một runtime image. Ví dụ image chỉ cần Java nền tảng và dữ liệu locale:

```bash
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --output runtime-l10n
```

Đây là ví dụ cho shell hỗ trợ dấu `\` nối dòng, như Bash. Trên Windows PowerShell, dùng ví dụ một dòng để tránh khác biệt cú pháp.

Một dòng tương đương:

```powershell
jlink --add-modules java.base,jdk.localedata --include-locales=en,ja,vi,fr --output runtime-l10n
```

Ý nghĩa:

- `--add-modules java.base,jdk.localedata`: đưa hai module vào graph của image. `java.base` là module nền tảng; `jdk.localedata` được thêm một cách **tường minh**.
- `--include-locales=en,ja,vi,fr`: yêu cầu plugin chỉ giữ các resource locale khớp các language ranges đã chọn trong `jdk.localedata`.
- `--output runtime-l10n`: nơi ghi image. Thư mục output cần chưa tồn tại hoặc đáp ứng điều kiện của jlink; không ghi đè lên một image đang được ứng dụng khác sử dụng.

**Không thể chỉ thêm `--include-locales` rồi bỏ `jdk.localedata`.** Khi thử bằng JDK cung cấp cho bài học, lệnh:

```bash
jlink --add-modules java.base --include-locales=ja --output runtime-wrong
```

báo:

```text
Error: jdk.localedata module was not specified with --add-modules option
```

Đây là lỗi cấu hình ở **thời điểm tạo image**, không phải lỗi parse ngày hoặc format số trong ứng dụng.

Trong production, `--add-modules` không nhất thiết chỉ có hai module như ví dụ. Nếu ứng dụng cần `java.logging`, `java.sql`, `java.net.http`, `java.desktop`, module của ứng dụng hoặc các dependency khác, phải bảo đảm chúng cũng được đưa vào runtime image theo module graph. `--include-locales` **không thay thế phân tích dependencies**.

## 4. Chuẩn BCP 47 và phạm vi matching

Cú pháp plugin được liệt kê bởi `jlink --list-plugins`:

```text
--include-locales <langtag>[,<langtag>]*
BCP 47 language tags separated by a comma,
allowing locale matching defined in RFC 4647.
e.g.: en,ja,*-IN
```

Các phần tử được ngăn bằng dấu phẩy. Ví dụ:

| Biểu thức | Ý tưởng lựa chọn |
|---|---|
| `en` | Dữ liệu khớp phạm vi ngôn ngữ Anh |
| `vi` | Dữ liệu khớp phạm vi tiếng Việt |
| `ja` | Dữ liệu khớp phạm vi tiếng Nhật |
| `fr` | Dữ liệu khớp phạm vi tiếng Pháp |
| `en,ja,vi,fr` | Kết hợp bốn phạm vi |
| `vi-VN` | Nhắm rõ biến thể tiếng Việt tại Việt Nam |
| `*-IN` | Ví dụ range có wildcard nhắm các locale phù hợp vùng IN theo quy tắc matching được hỗ trợ |

BCP 47 **language tags** dùng dấu gạch nối, chẳng hạn `vi-VN` hoặc `en-US`; không nhầm với các dạng dùng gạch dưới khi gọi constructor cũ của `Locale`.

**Không nên coi `en,ja,vi,fr` là “đúng bốn đối tượng Locale”**. Các language ranges có thể khớp nhiều biến thể vùng, và jlink có thể giữ thêm dữ liệu hỗ trợ cần thiết. Số locale xuất hiện sau khi link phụ thuộc JDK/provider và dữ liệu thực tế.

Tương tự, không suy ra pattern `*-IN` sẽ tự thêm tất cả thư viện ngôn ngữ thế giới; nó chỉ chọn những dữ liệu có sẵn và khớp với quy tắc plugin.

### Kiểm tra plugin có mặt trong JDK

Trước khi tạo image:

```bash
jlink --version
jlink --list-plugins
```

Quan sát mục `--include-locales`. Nếu công cụ không có plugin này, xem lại phiên bản/JDK distribution đang dùng thay vì thử truyền một option mà runtime không nhận ra.

Một pattern không khớp bất kỳ locale nào có thể khiến jlink báo lỗi. Với JDK đã kiểm tra, lệnh sau:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=zz-ZZ --output runtime-none
```

trả:

```text
Error: No matching locales found for "zz-ZZ". Check the specified pattern.
```

Không lấy `zz-ZZ` làm một locale giả định tồn tại; đây chỉ là ca kiểm thử **language range không khớp**.

## 5. Điều kiện môi trường khi tạo runtime image

Bạn cần một **JDK có công cụ `jlink` và các JMOD tương ứng**, không chỉ một JRE/runtime image tối giản. Với lệnh thông thường, jlink có thể sử dụng thư mục `jmods` của JDK khi không chỉ định `--module-path`, nhưng nên kiểm soát JDK build khi đóng gói.

Kiểm tra:

```bash
java -version
javac -version
jlink --version
java --list-modules
```

Trong danh sách của JDK tạo image, cần có `jdk.localedata`. Trên JDK phù hợp, có thể xem module:

```bash
java --describe-module jdk.localedata
```

Nếu muốn chỉ định module path tường minh, ví dụ trên Bash:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --output runtime-l10n
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,jdk.localedata --include-locales=en,ja,vi,fr --output runtime-l10n
```

Lưu ý thực tế:

- `JAVA_HOME` phải trỏ tới **JDK** có các file JMOD phù hợp.
- Không trộn module path của JDK phiên bản khác với `jlink` đang chạy.
- Khi tạo image chứa ứng dụng, cần thêm **module path của ứng dụng** và các root modules tương ứng.
- Image tạo ra có thể phụ thuộc nền tảng/kiến trúc và không tự là gói phân phối tương thích với mọi hệ điều hành.
- Sau khi link, image thường có `bin/java` (hoặc `bin\java.exe` trên Windows), nhưng **không nên giả định nó có `javac` hay `jlink`**. Hãy biên dịch chương trình bằng JDK đầy đủ trước khi chạy probe trong image.

Đừng sửa `JAVA_HOME` hoặc `PATH` toàn cục chỉ để kiểm tra một image; có thể gọi trực tiếp đường dẫn tới executable bên trong image.

## 6. Chương trình Java 17+ kiểm tra locale còn lại

Một cách QA cơ bản là kiểm tra **hai tầng**:

1. Module `jdk.localedata` có tồn tại trong image không?
2. Dịch vụ cần dùng (`NumberFormat` trong ví dụ) **còn công bố locale cụ thể không?**

`Locale.forLanguageTag("vi-VN")` chỉ **tạo đối tượng mô tả locale**; nó không chứng minh runtime có dữ liệu tiếng Việt.

Tạo file `LocaleDataProbe.java`:

```java
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class LocaleDataProbe {
    public static void main(String[] args) {
        List<Locale> available =
                Arrays.asList(NumberFormat.getAvailableLocales());

        boolean hasModule = ModuleLayer.boot()
                .findModule("jdk.localedata")
                .isPresent();

        System.out.println("jdk.localedata=" + hasModule);

        for (String tag : new String[] {
                "en-US", "ja-JP", "vi-VN",
                "fr-FR", "de-DE", "ar-EG"
        }) {
            Locale locale = Locale.forLanguageTag(tag);
            System.out.println(
                    tag + "=" + available.contains(locale));
        }

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        String shown = NumberFormat.getNumberInstance(vietnamese)
                .format(1234.5);

        System.out.println("vi-number=" + shown);
    }
}
```

Biên dịch bằng JDK đầy đủ:

```bash
javac LocaleDataProbe.java
```

Chạy bằng image đã tạo. Linux/macOS:

```bash
./runtime-l10n/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

Windows PowerShell:

```powershell
.\runtime-l10n\bin\java.exe "-Djava.locale.providers=CLDR" -cp . LocaleDataProbe
```

Một output đã được kiểm chứng với JDK dùng để thử nghiệm và image tạo bằng `--include-locales=en,ja,vi,fr`:

```text
jdk.localedata=true
en-US=true
ja-JP=true
vi-VN=true
fr-FR=true
de-DE=false
ar-EG=false
vi-number=1.234,5
```

Đọc output:

- `jdk.localedata=true` cho biết module có mặt, **không chứng minh mọi locale vẫn còn dữ liệu**.
- Bốn locale của yêu cầu được `NumberFormat` công bố.
- `de-DE` và `ar-EG` không có trong danh sách `NumberFormat.getAvailableLocales()` của image thử nghiệm.
- `vi-number=1.234,5` cho thấy trong runtime thử nghiệm, `vi-VN` vẫn sử dụng quy tắc dấu số mong đợi với provider CLDR.

**Các giá trị này là kết quả của một JDK/image cụ thể, không phải invariant của mọi Java 17+ release.** Dữ liệu CLDR và danh sách locale có thể thay đổi giữa các bản JDK. Unit test/CI nên kiểm tra **locale cần có và hành vi định dạng**, không dùng một tổng số locale cố định làm tiêu chí duy nhất.

## 7. Đối chiếu full JDK, image chỉ java.base và image được lọc

Một kiểm thử thực hành hữu ích là chạy **chính cùng một probe** trên ba runtime:

1. **JDK đầy đủ**: thường có dữ liệu locale phong phú.
2. **Image tối thiểu chỉ `java.base`**: có dữ liệu locale cơ sở.
3. **Image có `jdk.localedata` nhưng `--include-locales` chỉ giữ các language ranges cần thiết**.

Ví dụ tạo image tối thiểu:

```bash
jlink --add-modules java.base --output runtime-base
```

Sau đó chạy:

```bash
./runtime-base/bin/java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
```

Với JDK thử nghiệm, image `java.base` chỉ công bố **5** locale qua `NumberFormat.getAvailableLocales()`, trong khi image lọc `en,ja,vi,fr` công bố **166** và JDK đầy đủ công bố **1146**. **Không hardcode ba số này:** chúng chỉ minh họa tác động rõ ràng của module/filter trên một JDK cụ thể.

Một điều đáng chú ý là `java.base` vẫn có thể trả về chuỗi số khi được yêu cầu một locale không nằm trong danh sách. Ví dụ yêu cầu `vi-VN` trên image tối thiểu có thể dẫn tới định dạng kiểu `1,234.5` thay vì `1.234,5`. Đây là **fallback**, không phải bằng chứng hệ thống vẫn giữ dữ liệu tiếng Việt.

Quy trình kiểm thử không nên dựa vào điều kiện “`format(...)` không ném exception” vì việc fallback có thể xảy ra âm thầm.

## 8. Vì sao runtime còn module nhưng mất dữ liệu một số locale?

`java --list-modules` chỉ chứng minh module có mặt trong image, **không liệt kê chi tiết từng dữ liệu locale đã giữ lại**.

Nếu:

```bash
./runtime-l10n/bin/java --list-modules
```

có kết quả chứa:

```text
java.base@...
jdk.localedata@...
```

thì module data vẫn được link. Nhưng lệnh tạo image với `--include-locales` có thể đã loại bớt resource bundles trong `jdk.localedata`.

Do đó, không thể kết luận:

```text
jdk.localedata có mặt => mọi locale JDK đầy đủ đều có mặt
```

Điều đúng là cần **kiểm tra dịch vụ và locale cụ thể** trong chính image đích.

Nếu bạn chỉ kiểm tra `ModuleLayer.boot().findModule("jdk.localedata").isPresent()`, việc ghi nhãn runtime “hỗ trợ tiếng Pháp” vẫn có thể sai khi lệnh jlink ban đầu không chọn dữ liệu French.

## 9. Kiểm tra Locale.getAvailableLocales và các dịch vụ cụ thể

Java có nhiều API công bố danh sách locale:

```java
Locale.getAvailableLocales();
NumberFormat.getAvailableLocales();
DateFormat.getAvailableLocales();
Collator.getAvailableLocales();
```

Các lời gọi này là **mảnh mã trong phương thức**, cần import tương ứng.

Khuyến nghị chọn API dựa trên chức năng sản phẩm:

| Chức năng | Cần kiểm tra |
|---|---|
| Format số, phần trăm, tiền tệ | `NumberFormat.getAvailableLocales()` và kết quả format |
| Format ngày/giờ kiểu `java.text` | `DateFormat.getAvailableLocales()` và kết quả date/time |
| Sắp xếp văn bản theo ngôn ngữ | `Collator.getAvailableLocales()` và các cặp so sánh thực |
| Chọn locale tổng quát | `Locale.getAvailableLocales()` như tín hiệu ban đầu |
| Tên tháng, tên thứ, định dạng `java.time` | Test `DateTimeFormatter` với locale/kiểu format cần sử dụng |
| Ngôn ngữ của UI do ứng dụng tự cung cấp | Kiểm tra `ResourceBundle` của ứng dụng riêng, không chỉ `jdk.localedata` |

**Không coi một danh sách locale là chứng minh tất cả các dịch vụ đều hỗ trợ đúng chiều sâu.** Một locale có thể khả dụng trong một API, nhưng kết quả tùy thuộc service provider và dữ liệu cụ thể.

`Locale.getAvailableLocales()` là chỉ báo tổng quát; khi ứng dụng có chức năng number/date/collation, cần test trực tiếp từng dịch vụ. Trường hợp app chỉ dùng `DateTimeFormatter`, không nên dùng kiểm tra `NumberFormat` làm tiêu chí duy nhất cho date-time.

## 10. Test hành vi định dạng, không chỉ danh sách hỗ trợ

Danh sách supported locales rất hữu ích để phát hiện locale bị lọc, nhưng QA cuối cùng phải hỏi **sản phẩm hiển thị nội dung thật có đúng không?**

Ví dụ:

- **Tiếng Việt:** `1234.5` theo cấu hình của ứng dụng, dấu nhóm/dấu thập phân và cách biểu diễn ngày.
- **Tiếng Pháp:** số dùng quy ước group/decimal và ký hiệu/khoảng trắng tương ứng trong JDK/provider.
- **Tiếng Nhật:** cách hiển thị tháng, tên thời đại Nhật nếu ứng dụng sử dụng Japanese calendar, tiền tệ yen và patterns liên quan.
- **Tiếng Arabic:** chữ số, ký hiệu phân nhóm, dấu thập phân, hướng chữ và tương tác font/rendering nếu là ứng dụng desktop.

**Không khóa cứng mọi kết quả locale vào văn bản của một phiên bản CLDR duy nhất**. Thay đổi dữ liệu vùng/ngôn ngữ có thể đúng theo chuẩn cập nhật. Test nên có cả tiêu chí mềm (locale phải có) và bộ case quan trọng đã được đánh giá theo JDK build production.

Một chiến lược tốt là test với:

```text
Locale cần có?
   |
   +-- Không -> FAIL BUILD
   |
   +-- Có -> format dữ liệu thực
                   |
                   +-- Không đúng yêu cầu nghiệp vụ -> FAIL QA
                   |
                   +-- Đúng -> kiểm tra UI/font nếu liên quan
```

Nếu thiếu dữ liệu ngày của locale, app có thể rơi về định dạng khác mà không báo lỗi; đây là lý do QA về định dạng phải chạy **bằng chính executable trong image**, không chỉ bằng JDK dùng biên dịch.

## 11. Phân biệt dữ liệu JDK và resource bundles của ứng dụng

`--include-locales` là plugin chọn locale của **`jdk.localedata`**. Nó không phải lệnh lọc tất cả file dịch trong project hoặc chỉnh dữ liệu của hệ thống quản lý bản dịch.

Ví dụ ứng dụng có:

```text
messages.properties
messages_vi.properties
messages_fr.properties
```

Các file này là **resource bundles của ứng dụng**. Chúng được đưa vào output/runtime theo cách đóng gói module/JAR/resource của app. Một image có `vi-VN` trong `jdk.localedata` **không bảo đảm** `messages_vi.properties` đã được đóng vào application artifact.

Ngược lại, dù ứng dụng có `messages_vi.properties`, vẫn có thể thiếu dữ liệu locale JDK dùng cho `DateFormat`, `NumberFormat` hoặc `Collator` trong runtime image.

Cần kiểm tra hai tuyến độc lập:

1. **Dữ liệu locale JDK:** module + include-locales + API formatting/collation.
2. **Bản dịch ứng dụng:** các file/resource bundles và fallback của `ResourceBundle.getBundle(...)`.

Chú ý `ResourceBundle` có cơ chế tìm kiếm/fallback riêng, nên một bundle được trả về cũng **không nhất thiết là bundle đúng locale yêu cầu**. Khi kiểm tra bản dịch, kiểm tra locale thực tế của bundle cùng key quan trọng để phát hiện fallback sai.

## 12. Không nên suy luận từ Locale.forLanguageTag()

Câu lệnh:

```java
Locale locale = Locale.forLanguageTag("de-DE");
```

không chứng minh dữ liệu German có mặt trong image. `Locale` phần lớn là **mô tả ngôn ngữ/vùng và các extension**, không tự tải resource bundles locale từ mạng.

Do đó những kiểm tra sau chưa đủ:

```java
System.out.println(locale.toLanguageTag()); // de-DE
System.out.println(locale.getLanguage());    // de
```

Chúng chứng minh object chứa mã locale, chứ không chứng minh thuật toán format số có dữ liệu `de-DE`.

Cũng không thể dựa vào việc `NumberFormat.getInstance(locale)` trả về non-null: API có thể fallback sang locale khác. Tốt hơn là kiểm tra `NumberFormat.getAvailableLocales()` **và** định dạng các giá trị có khả năng phơi bày khác biệt giữa những locale.

Ví dụ `1234.5` là số thử thuận tiện vì biểu diễn US (`1,234.5`) và vi-VN (`1.234,5`) khác dấu. Nhưng một giá trị nguyên nhỏ như `12` có thể cho cùng kết quả ở nhiều locale, khiến test quá yếu và bỏ sót dữ liệu bị cắt.

## 13. Tùy chọn include-locales không đặt default Locale

Sau khi chạy:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales=ja,vi --output runtime
```

bạn **không được kết luận**:

```text
Locale.getDefault() == vi-VN
```

Tùy chọn chỉ chọn dữ liệu được đóng gói, **không chỉ định ngôn ngữ mặc định của JVM**. Default locale có thể đến từ hệ điều hành, môi trường hoặc cấu hình runtime khác.

Một lời gọi không nêu locale:

```java
NumberFormat.getNumberInstance();
```

sử dụng default locale, có thể không phải một locale nằm trong mong muốn của sản phẩm. Nếu runtime không có dữ liệu tương ứng, hành vi fallback có thể làm đầu ra không như dự kiến.

Thay vì để mặc định thay đổi theo server, định dạng có chủ đích:

```java
Locale userLocale = Locale.forLanguageTag("vi-VN");
NumberFormat formatter =
        NumberFormat.getNumberInstance(userLocale);
```

Trong ứng dụng nhiều người dùng, locale cần đến từ lựa chọn người dùng/yêu cầu hoặc hợp đồng dữ liệu, không phải được thay đổi toàn cục bằng `Locale.setDefault(...)` cho mỗi request.

Nếu muốn kiểm tra default locale thật khi chạy image:

```java
System.out.println(Locale.getDefault().toLanguageTag());
```

Và kiểm tra riêng locale đang được truyền cho từng API formatting.

## 14. Lưu ý các extensions và biến thể locale

BCP 47 có thể có language, script, region, variant và Unicode locale extensions. Ví dụ:

```text
en-US
zh-Hant-TW
th-TH
ar-EG-u-nu-latn
```

Các extension có thể điều khiển hành vi mong muốn của dịch vụ, chẳng hạn hệ chữ số (*numbering system*) trong một số API/provider.

Tuy nhiên, **không được xem `--include-locales` là cơ chế tự động đảm bảo mọi numbering system/Calendar và extension được hỗ trợ**. Dữ liệu locale, biến thể ngôn ngữ và khả năng API nhận extension có thể khác nhau theo JDK. Cần kiểm thử **đúng locale tag mà ứng dụng sử dụng**, kể cả extension khi nó có ý nghĩa.

Ví dụ nếu giao thức sản phẩm cho phép `th-TH-u-nu-thai` hoặc `ar-EG-u-nu-latn`, đừng chỉ thử `th` hay `ar` rồi kết luận mọi cách hiển thị số sẽ đúng.

Ngược lại, nếu app không dùng biến thể vùng/extension nào, đừng đưa vào danh sách ngẫu nhiên: hãy chọn tập locale từ **yêu cầu sản phẩm thực tế**.

## 15. Tích hợp jlink vào quy trình build

Một quy trình phát hành đáng tin cậy:

1. **Xác định tập locale cần hỗ trợ:** từ product requirements, không chọn tùy tiện chỉ vì image sẽ nhỏ.
2. **Phân tích modules ứng dụng:** các root modules và dependencies của ứng dụng. Có thể dùng `jdeps` để hỗ trợ phân tích nếu phù hợp.
3. **Đưa `jdk.localedata` vào graph:** thêm nó vào `--add-modules` khi dùng `--include-locales`.
4. **Chạy `jlink` bằng JDK build đã pin:** tạo image ở thư mục mới.
5. **Chạy probe bằng `runtime/bin/java`:** kiểm tra module, API available locales và locale thiết yếu.
6. **Chạy integration tests:** format số, ngày, tiền, text collation và resource bundles trên image.
7. **Kiểm thử nền tảng đích:** nhất là desktop hoặc các tính năng cần font, timezone và môi trường hệ điều hành.
8. **Đóng gói image cùng ứng dụng:** bảo đảm classpath/module path và launcher thực tế dùng đúng image vừa kiểm thử.
9. **Gắn metadata:** lưu JDK vendor/version, lệnh jlink, phạm vi locale, hash artifact và kết quả QA.
10. **Kiểm tra lại khi nâng JDK:** dữ liệu CLDR, provider và output locale có thể thay đổi.

Ví dụ đặt lệnh trong CI (Bash):

```bash
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,ja,vi,fr \
  --no-header-files \
  --no-man-pages \
  --output runtime-l10n

javac LocaleDataProbe.java
./runtime-l10n/bin/java -Djava.locale.providers=CLDR \
  -cp . LocaleDataProbe
```

`--no-header-files` và `--no-man-pages` là những tùy chọn giảm bớt nội dung image, **không quyết định danh sách locale**. Nếu build production có module khác, phải bổ sung chúng vào câu lệnh thực tế.

Nếu chạy trên Windows, dùng `runtime-l10n\bin\java.exe`. Đảm bảo đường dẫn có khoảng trắng được quote phù hợp, đặc biệt với `--module-path` và `--output`.

## 16. Dùng jlink và jdeps đúng vai trò

`jdeps` giúp tìm các module mà Java application phụ thuộc về mặt class/module references; nó không thể tự suy ra **toàn bộ tập locale mà người dùng sẽ yêu cầu tại runtime**.

Ví dụ một ứng dụng có thể gọi:

```java
NumberFormat.getNumberInstance(userLocale);
```

Ở thời điểm build, giá trị `userLocale` chưa được biết nếu đến từ request. Dù `jdeps` phát hiện nhu cầu `java.base`, nó không biết sản phẩm cần `vi-VN`, `fr-FR` hay `ar-EG`.

Do đó, cần hai loại quyết định:

- **Dependencies kỹ thuật:** module nào để code chạy?
- **Địa bàn/ngôn ngữ hỗ trợ:** locale data nào để chức năng chạy **đúng ngữ nghĩa**?

`--include-locales` giải quyết lựa chọn thứ hai cho dữ liệu từ `jdk.localedata`, không thay thế loại thứ nhất. Không dùng một lần `jdeps` rồi coi bài toán bản địa hóa đã hoàn thành.

## 17. Cách giảm size nhưng vẫn kiểm soát chất lượng

Không có một danh sách ngôn ngữ “tốt nhất” cho mọi sản phẩm. Một ứng dụng chỉ dùng US English có thể không cần toàn bộ dữ liệu locale. Một ứng dụng có người dùng ở Việt Nam, Nhật Bản, Pháp và nhiều quốc gia khác lại phải giữ dữ liệu tương ứng.

Những đánh đổi:

| Quyết định | Lợi ích | Rủi ro |
|---|---|---|
| Chỉ `java.base` | Image nhỏ | Thiếu locale data của nhiều ngôn ngữ |
| Thêm toàn bộ `jdk.localedata` | Dữ liệu locale rộng hơn | Image lớn hơn |
| Thêm `jdk.localedata` + `--include-locales` | Cân bằng size và phạm vi locale | Dễ bỏ sót locale/extension nếu requirements không rõ |
| Chỉ test `Locale.forLanguageTag` | Test nhanh | Không chứng minh dữ liệu thực |
| Test output dưới image | Phát hiện fallback và lỗi thực tế | Phải duy trì test cases theo JDK/version |

Không nên chỉ tối ưu kích thước file ZIP hay số MB mà bỏ qua chức năng locale. Một runtime image “nhỏ nhất” nhưng xuất hóa đơn sai dấu thập phân có thể gây hậu quả nghiệp vụ lớn hơn nhiều so với phần dung lượng tiết kiệm.

## 18. Troubleshooting: lỗi điển hình

### Lỗi A — Thiếu jdk.localedata trong --add-modules

Triệu chứng ở bước jlink:

```text
Error: jdk.localedata module was not specified with --add-modules option
```

Khắc phục: thêm `jdk.localedata` vào danh sách root modules. Sau đó kiểm tra lại image thay vì chỉ thấy lệnh link thành công và kết thúc.

### Lỗi B — Include range không khớp dữ liệu JDK

Triệu chứng:

```text
Error: No matching locales found for "zz-ZZ". Check the specified pattern.
```

Khắc phục: xem lại language tag/range, chính tả và JDK/provider. Không tự coi locale do người dùng gõ vào là có sẵn.

### Lỗi C — Module có mặt nhưng định dạng không đúng locale

Triệu chứng: `java --list-modules` có `jdk.localedata`, nhưng `NumberFormat` cho một locale bắt buộc lại hiển thị kiểu English fallback.

Kiểm tra: `--include-locales` ban đầu, danh sách từ `NumberFormat.getAvailableLocales()`, property locale providers và output format thực tế. Thêm range bị thiếu rồi **build image mới**, không sửa resource trực tiếp trong image đã phát hành nếu không có quy trình được hỗ trợ.

### Lỗi D — Chạy probe bằng full JDK, không phải image

Triệu chứng: local test thành công nhưng production không đúng locale.

Nguyên nhân phổ biến: test gọi `java` theo `PATH` của JDK đầy đủ, thay vì `runtime-l10n/bin/java`. Trong CI, gọi **đường dẫn tuyệt đối/tường minh** đến image để tránh sự nhầm lẫn.

### Lỗi E — Có dữ liệu locale nhưng thiếu bản dịch UI

`NumberFormat` đúng `vi-VN` nhưng resource bundle `messages_vi.properties` không tồn tại trong ứng dụng. Đây là vấn đề đóng gói tài nguyên của app, không phải `--include-locales`. Kiểm tra đường dẫn resources/JAR/module, `ResourceBundle` fallback và bộ bản dịch.

### Lỗi F — Default locale khác mong muốn

Ứng dụng gọi `NumberFormat.getInstance()` không truyền locale; trên server default là `en-US` nên vẫn dùng English. Khắc phục: truyền `Locale` tường minh từ ngữ cảnh nghiệp vụ, không chỉ thêm `vi` vào image.

### Lỗi G — Khác output sau khi nâng cấp JDK

Bản JDK mới cập nhật dữ liệu locale/CLDR. Kết quả có thể khác dấu nhóm, tên vùng hoặc các chi tiết định dạng khác dù cùng option. Khắc phục: pin JDK build cho release, chạy regression tests, cập nhật expected output sau khi đánh giá thay đổi chuẩn.

## 19. Checklist QA cho image phát hành

| Kiểm tra | Điều kiện đạt |
|---|---|
| `jlink --list-plugins` | Có `--include-locales` trong JDK build |
| JDK modules | `jdk.localedata` có thể được liên kết |
| Lệnh link | Có `--add-modules ... ,jdk.localedata` và range cần thiết |
| Module trong image | `bin/java --list-modules` thấy `jdk.localedata` |
| Locale API | Các locale bắt buộc xuất hiện trong API liên quan |
| Number format | Grouping/decimal/precision đúng ca nghiệp vụ |
| Date/time | Ngày và tên tháng đúng locale; timezone được kiểm tra riêng |
| Currency | Ký hiệu, số chữ số và chính sách rounding đúng yêu cầu |
| Collation | Thứ tự các chuỗi test quan trọng đúng với quy tắc locale |
| Application bundles | Các bản dịch UI có trong app artifact |
| Image executable | Test chạy bằng `bin/java` của image, không nhầm full JDK |
| Locale extensions | Các BCP 47 tags thực tế được hỗ trợ và test |
| Build reproducibility | Pin JDK/provider, ghi lại jlink options và kết quả test |
| Fallback | Locale bị loại khỏi image được phát hiện, không chấp nhận im lặng |

Hãy giữ **danh sách locale tối thiểu bắt buộc** như một phần cấu hình release. Nếu người dùng có thể thay ngôn ngữ trong UI mà một lựa chọn không được đóng gói, ứng dụng nên chặn/hạn chế lựa chọn đó hoặc thông báo chính xác thay vì tự chuyển về format khác không được phê duyệt.

## 20. Các lỗi thường gặp khi học và triển khai

1. **Chỉ viết `--include-locales=vi` mà quên `jdk.localedata`.** Plugin cần module dữ liệu trong `--add-modules`.
2. **Tưởng `--include-locales` đặt ngôn ngữ JVM mặc định.** Nó chỉ lọc dữ liệu được giữ lại.
3. **Tưởng `Locale.forLanguageTag("vi-VN")` chứng minh có Vietnamese locale data.** Nó chỉ tạo đối tượng mô tả.
4. **Tưởng `NumberFormat.getInstance(locale)` không ném lỗi nghĩa là dữ liệu locale đầy đủ.** Provider có thể fallback.
5. **Chỉ kiểm tra `java --list-modules`.** Có `jdk.localedata` không chứng minh một locale cụ thể còn nằm trong image.
6. **Chạy test trên `java` theo PATH.** Có thể vô tình dùng JDK đầy đủ, không phải linked image.
7. **Hardcode tổng số locale cần bằng một số cố định.** Tập locale thay đổi theo JDK/provider.
8. **Nhầm data của JDK với `messages_*.properties` của app.** Hai nguồn tài nguyên độc lập.
9. **Dùng langtag sai cú pháp hoặc không kiểm tra wildcard.** BCP 47 language ranges phải được jlink chấp nhận và match dữ liệu có thật.
10. **Dựa vào `jdeps` để quyết định ngôn ngữ cần đóng gói.** Dependency analysis không biết nhu cầu locale runtime.
11. **Loại hết dữ liệu locale vì muốn image nhỏ.** Ứng dụng có thể vẫn chạy nhưng hiển thị sai.
12. **Không kiểm tra date, currency, Collator.** Một probe số duy nhất không chứng minh toàn bộ trải nghiệm localization.
13. **Không kiểm thử provider thực tế trên production.** Cùng module, khác provider/configuration có thể cho kết quả khác.
14. **Không xét BCP 47 extension.** Numbering system/calendar trong locale có extension có thể cần test riêng.
15. **Tự tin rằng runtime image dùng được trên mọi OS.** Image build có tính phụ thuộc nền tảng.
16. **Nâng JDK rồi tái dùng kỳ vọng CLDR cũ mà không kiểm tra.** Dữ liệu locale có thể cập nhật.
17. **Xem việc link thành công như QA hoàn thành.** Runtime cần được chạy và so output thực tế.
18. **Bỏ qua fallback của ResourceBundle.** Có thể hiển thị văn bản sai ngôn ngữ dù JDK date/number locale vẫn đủ.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao muốn dùng `jlink --include-locales` phải thêm `jdk.localedata` vào `--add-modules`?  
**Đáp án:** Plugin lọc dữ liệu locale của module `jdk.localedata`; thiếu module này là cấu hình link không hợp lệ trong JDK đã kiểm tra.

**Câu 2.** `--include-locales=en,ja,vi,fr` có nghĩa image chỉ công bố chính xác bốn `Locale` không?  
**Đáp án:** Không. Đây là language ranges; có thể khớp nhiều biến thể vùng và giữ một số locale cơ sở. Số lượng phụ thuộc JDK.

**Câu 3.** Image có `jdk.localedata` thì tất cả locale của JDK phát triển đều còn không?  
**Đáp án:** Không. `--include-locales` có thể đã lọc resource theo yêu cầu; phải kiểm tra các locale cụ thể.

**Câu 4.** Có thể dựa vào `Locale.forLanguageTag("vi-VN")` để kết luận dữ liệu tiếng Việt sẵn có không?  
**Đáp án:** Không. Phải kiểm tra API/service và đầu ra format thực tế trong runtime image.

**Câu 5.** Vì sao image thiếu `de-DE` vẫn có thể format số cho `de-DE` mà không báo lỗi?  
**Đáp án:** Locale provider có thể sử dụng quy tắc fallback. Không ném lỗi không đồng nghĩa locale được hỗ trợ đúng.

**Câu 6.** Tại sao phải gọi `./runtime-l10n/bin/java` thay vì chỉ `java` trong test?  
**Đáp án:** Để bảo đảm chạy bằng image vừa tạo; `java` theo PATH có thể là JDK đầy đủ.

**Câu 7.** Nếu `messages_vi.properties` bị bỏ khỏi application JAR, `--include-locales=vi` có tự tạo file đó không?  
**Đáp án:** Không. Đây là tài nguyên của ứng dụng, không thuộc `jdk.localedata`.

**Câu 8.** Muốn kiểm chứng cả date, currency và collation thì chỉ dùng `NumberFormat.getAvailableLocales()` có đủ không?  
**Đáp án:** Không. Cần test các API và giá trị đại diện cho từng dịch vụ.

**Câu 9.** Một bộ locale test chạy đúng trên JDK 17 nhưng sai sau khi nâng JDK mới hơn thì nên xem gì?  
**Đáp án:** JDK vendor/version, CLDR/provider version, jlink flags, module graph, language ranges và đầu ra ứng dụng thực tế.

**Câu 10.** Khi nào nên giữ thêm locale thay vì cố thu nhỏ image?  
**Đáp án:** Khi sản phẩm yêu cầu hỗ trợ những ngôn ngữ/vùng đó. Tính đúng của bản địa hóa phải là điều kiện chất lượng, không phải tùy chọn.

## 22. Tổng kết

`jlink --include-locales` là công cụ quan trọng để cân bằng **dung lượng runtime** và **phạm vi bản địa hóa** khi dùng modular Java. Nhưng để đúng:

- Thêm `jdk.localedata` vào `--add-modules` cùng các module thực tế mà ứng dụng cần.
- Chọn language ranges BCP 47 theo các locale sản phẩm hỗ trợ.
- Kiểm tra **trong image đích**: module presence, `getAvailableLocales()` của các dịch vụ liên quan và output số/ngày/tiền thực tế.
- Nhận diện **fallback im lặng**: formatter chạy không có nghĩa đang dùng dữ liệu đúng locale.
- Kiểm tra riêng resource bundles của ứng dụng, default locale, timezone, provider và việc nâng cấp JDK.

Nguyên tắc phát hành đáng nhớ: **“Build image nhỏ hơn, nhưng chứng minh tính đúng của locale bằng chính runtime đã link.”**

**Tài liệu tham khảo chính thức:** [Java SE 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html) · [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — DateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html) · [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252).
