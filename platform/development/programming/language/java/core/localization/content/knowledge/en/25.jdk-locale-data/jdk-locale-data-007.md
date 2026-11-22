# jdk.localedata và tập dữ liệu trong runtime tùy chỉnh

## 1. Vấn đề: cùng chương trình nhưng định dạng locale khác nhau giữa các runtime

Một chương trình Java có thể chạy đúng trên máy phát triển dùng JDK đầy đủ, nhưng sau khi đóng gói thành runtime nhỏ bằng `jlink`, cách in ngày tháng, số, tiền tệ hoặc tên bản địa hóa có thể thay đổi. Thay vì `28 tháng 10, 2026`, hệ thống có thể dùng một kiểu fallback; thay vì tên tháng bằng tiếng Pháp, bạn có thể thấy dữ liệu từ locale cha hoặc locale gốc.

Đó không nhất thiết là lỗi trong `DateTimeFormatter`, `NumberFormat` hay `Locale`. Nguyên nhân có thể là **runtime image không chứa dữ liệu locale mà formatter cần**.

Java 9+ tách nhiều dữ liệu bản địa hóa ra một module tên **`jdk.localedata`**. Khi dùng `jlink` để tạo **custom runtime image**, bạn quyết định đưa module đó vào hay loại bỏ; tùy chọn `--include-locales` cho phép chọn một tập locale nhỏ hơn trong module.

Bài học giải thích:

1. `java.base`, `jdk.localedata` và dữ liệu locale được phân chia ra sao.
2. Vì sao `Locale` hợp lệ **không chứng minh** bản dịch/định dạng cho nó có sẵn.
3. Cách tạo runtime tùy chỉnh với `jlink --add-modules` và `--include-locales`.
4. Cách kiểm tra `DateTimeFormatter`, `NumberFormat`, `DateFormat`, tên tiền tệ và danh sách locale có sẵn.
5. Cách đối chiếu hành vi giữa JDK đầy đủ và runtime tối giản, phát hiện fallback, viết test và tránh giả định sai khi triển khai.

Phạm vi bài nằm trong **Dữ liệu locale JDK**. Đây là câu chuyện về **tài nguyên dữ liệu được đóng gói trong runtime**, không phải hướng dẫn tải bản dịch từ Internet hay chỉ định một `Locale` trong mã nguồn.

## 2. Locale không phải là một gói dữ liệu bản dịch

`java.util.Locale` chủ yếu là một **đối tượng định danh ngôn ngữ/vùng/script/extension**, chẳng hạn:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

Lệnh này tạo ra một đối tượng mô tả locale tiếng Việt (vùng Việt Nam). Nó **không** tự tải về tên tháng, dấu số, tên tiền tệ hoặc các mẫu ngày tháng.

Khi bạn gọi:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
~~~

API định dạng sẽ tra cứu **nguồn dữ liệu locale/provider có sẵn trong runtime** để chọn pattern và các từ ngữ tương ứng. Nếu dữ liệu đúng locale không có, việc fallback có thể khiến kết quả khác mong đợi.

Phân biệt ba câu hỏi:

| Câu hỏi | Điều đang được xác minh |
| --- | --- |
| `Locale.forLanguageTag("vi-VN")` có tạo object không? | Locale identifier có thể được biểu diễn trong Java |
| Runtime có module `jdk.localedata` không? | Image có chứa module dữ liệu locale mở rộng không |
| Dịch vụ định dạng cho `vi-VN` có dữ liệu thực sự không? | Provider được chọn có hỗ trợ đúng dữ liệu cho dịch vụ/ngữ cảnh đó không |

Ba câu hỏi **không tương đương**. Một `Locale` được khởi tạo thành công không chứng minh rằng `DateTimeFormatter` sẽ in tên tháng tiếng Việt hoặc `Currency.getDisplayName(locale)` sẽ có tên dịch mà bạn kỳ vọng.

## 3. `java.base` và `jdk.localedata` đóng vai trò gì?

### 3.1. `java.base`: module nền tảng

Mọi Java runtime image luôn cần `java.base`, vì đây là module bắt buộc của nền tảng Java. Module này bao gồm các API như:

- `java.util.Locale`;
- `java.text.NumberFormat`, `DateFormat`;
- `java.time.format.DateTimeFormatter`;
- `java.util.Currency`.

Các API trên tồn tại **không có nghĩa runtime đã đi kèm mọi dữ liệu bản địa hóa**.

Trong các bản Oracle/OpenJDK được tài liệu hóa, `java.base` mang dữ liệu locale cơ bản, bao gồm **US English và các locale cha như `ROOT`**. Dữ liệu cho nhiều locale khác nằm ở `jdk.localedata`.

### 3.2. `jdk.localedata`: dữ liệu locale bổ sung

`jdk.localedata` là một **JDK-specific module** chứa dữ liệu bản địa hóa mở rộng cho các dịch vụ locale-sensitive, ví dụ lựa chọn biểu diễn ngày, số, đơn vị tiền tệ hoặc tên hiển thị theo ngôn ngữ.

Module này không phải một lớp mà bạn phải import khi viết `DateTimeFormatter`. Phần lớn chương trình vẫn dùng các API trong `java.base`; chính **module graph và nguồn dữ liệu runtime** quyết định dữ liệu mở rộng có sẵn không.

Ví dụ những tính năng có thể chịu ảnh hưởng khi dữ liệu locale tương ứng bị lược bỏ:

- Tên tháng, tên thứ, mẫu ngày/giờ qua `DateTimeFormatter` hoặc `DateFormat`.
- Dấu thập phân, dấu phân nhóm, biểu diễn phần trăm qua `NumberFormat`.
- Tên hiển thị của locale, quốc gia và tiền tệ qua các API tương ứng.
- Một số quy tắc định dạng/so sánh được cấp bởi các locale service providers của runtime.

**Không suy diễn quá mức:** việc bỏ `jdk.localedata` không có nghĩa mọi chức năng Unicode, UTF-8, `Locale`, `java.time` hay mọi múi giờ đều biến mất. Phạm vi của nó là **dữ liệu locale mở rộng**; các thành phần khác của `java.base` vẫn tồn tại.

### 3.3. Dữ liệu locale và tài nguyên riêng của ứng dụng

`ResourceBundle` hoặc file `messages_vi.properties` do **ứng dụng tự cung cấp** không tự nằm trong `jdk.localedata`. Chúng phải được đóng gói/đọc theo cách của ứng dụng và module tương ứng.

Ngược lại, có đủ bản dịch UI trong `ResourceBundle` của bạn **không bảo đảm** `NumberFormat` hoặc `DateTimeFormatter` có đúng dữ liệu CLDR của locale đó trong runtime.

Hai luồng tài nguyên cần được kiểm thử riêng: **dữ liệu bản địa hóa ứng dụng** và **dữ liệu locale JDK**.

## 4. JDK đầy đủ khác runtime được tạo bằng jlink

Khi cài một **JDK đầy đủ**, bộ công cụ thường bao gồm module `jdk.localedata` và dữ liệu locale mở rộng. Vì vậy thử nghiệm với `vi-VN`, `fr-FR`, `ja-JP` trên máy phát triển có thể thành công.

Với `jlink`, nhà phát triển tạo một **custom runtime image** bằng cách ghép tập module cần thiết. Một image tối giản có thể chỉ có `java.base`; khi ấy nhiều dữ liệu locale mở rộng sẽ vắng mặt.

Hãy hình dung:

~~~text
JDK đầy đủ
  java.base          -> APIs + locale data cơ bản
  jdk.localedata     -> dữ liệu locale mở rộng
  nhiều module khác  -> các API/công cụ/dịch vụ khác

Custom image nhỏ
  java.base          -> APIs vẫn có
  (không có jdk.localedata)
  => nhiều locale không có dữ liệu định dạng đầy đủ
~~~

Một image khác có thể chứa:

~~~text
Custom image hỗ trợ chọn lọc
  java.base
  jdk.localedata (đã lọc theo --include-locales)
  các module app yêu cầu
  => có dữ liệu cho nhóm locale được chọn
~~~

`jlink` **không thay đổi semantics của `Locale.forLanguageTag`**; nó thay đổi **nội dung module và tài nguyên đi kèm runtime**, từ đó ảnh hưởng các dịch vụ cần dữ liệu locale.

Không coi “chương trình chạy không ném lỗi” là bằng chứng locale data đầy đủ. Fallback nhiều khi **không gây exception** mà chỉ tạo chuỗi ngày/giờ hoặc số khác với trải nghiệm người dùng dự kiến.

## 5. Công cụ kiểm tra tại máy phát triển

Trước khi tạo image, xác minh JDK nguồn đang được dùng:

~~~bash
java -version
jlink --version
java --list-modules
~~~

Lệnh `java --list-modules` liệt kê các module có trong runtime. Bạn có thể tìm `jdk.localedata` trong danh sách này.

Trên Windows PowerShell, có thể lọc:

~~~powershell
java --list-modules | Select-String 'jdk.localedata'
~~~

Trên shell Linux/macOS, ví dụ:

~~~bash
java --list-modules | grep 'jdk.localedata'
~~~

**Lưu ý:** các lệnh trên chỉ cho biết **module có tồn tại trong runtime image**, không khẳng định mọi locale đã được đưa vào. Một image có `jdk.localedata` nhưng được lọc bằng `--include-locales` vẫn có thể thiếu các locale bạn cần.

Nếu ứng dụng hoặc công cụ triển khai dùng `JAVA_HOME`, phải bảo đảm `java` và `jlink` được gọi từ **đúng JDK phiên bản/kiến trúc mục tiêu**. Khi kiểm tra runtime image đã phát hành, hãy chạy **binary `java` của image đó**, không vô tình chạy lệnh từ JDK hệ thống.

## 6. Tạo image chỉ với module tối thiểu

Ví dụ dòng lệnh dành cho `jlink` của JDK phù hợp:

~~~bash
jlink --add-modules java.base --output image-base
~~~

Đây là **ví dụ tạo custom runtime image tối giản để so sánh**. Nó tạo thư mục `image-base` chứa runtime có `java.base`; không phải bản build tự động đủ mọi module cho một ứng dụng bất kỳ.

Sau khi tạo, kiểm tra image bằng chính Java launcher bên trong nó.

Linux/macOS:

~~~bash
./image-base/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\image-base\bin\java.exe --list-modules
~~~

Danh sách sẽ có `java.base` và không có `jdk.localedata` trong image chỉ gồm `java.base`.

Điều đó **không đồng nghĩa mọi locale khác US sẽ throw exception**. Dịch vụ có thể fallback hoặc cung cấp hành vi dựa trên dữ liệu cơ bản. Vì vậy không dùng một exception làm điều kiện duy nhất để phát hiện thiếu dữ liệu locale.

`jlink` cũng yêu cầu các module ứng dụng thực sự sử dụng. Nếu ứng dụng cần `java.logging`, `java.sql`, `java.xml` hoặc module khác, phải tính các phụ thuộc đó khi build. Không sao chép nguyên lệnh `java.base` vào production nếu nó không phù hợp module graph của ứng dụng.

## 7. Bổ sung jdk.localedata vào image

Để mang theo module dữ liệu locale mở rộng:

~~~bash
jlink --add-modules java.base,jdk.localedata --output image-full-locale
~~~

Đối với nhiều JDK, nếu không dùng tùy chọn `--include-locales` để lọc, module được đóng gói với tập dữ liệu locale đi kèm JDK đang dùng. Image sẽ lớn hơn bản chỉ có `java.base`, nhưng có điều kiện để cung cấp nhiều dịch vụ bản địa hóa hơn.

Kiểm tra:

~~~bash
./image-full-locale/bin/java --list-modules
~~~

Trên Windows, thay đường dẫn launcher bằng `.\image-full-locale\bin\java.exe`.

Kết quả danh sách phải chứa `jdk.localedata`. Tuy nhiên, **module hiện diện chưa phải bằng chứng các dịch vụ định dạng bạn dùng đang chọn đúng provider hoặc có đúng mọi bản dịch**. Hãy chạy thêm một chương trình kiểm tra ngày/số/tiền tệ theo từng locale quan trọng.

Đừng chỉ xem `jlink` có exit code 0: một image hợp lệ về module vẫn có thể thiếu **yêu cầu locale thực tế** của sản phẩm.

## 8. `--include-locales`: lọc dữ liệu theo danh sách ngôn ngữ/vùng

Plug-in `include-locales` của `jlink` cho phép giới hạn dữ liệu locale đóng gói:

~~~bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales=vi-VN,fr-FR,ja-JP \
      --output image-selected-locales
~~~

Đây là ví dụ cú pháp cho shell có hỗ trợ dấu `\\` tiếp dòng. Trên Windows PowerShell, sử dụng **một dòng** để tránh khác biệt ký tự tiếp dòng:

~~~powershell
jlink --add-modules java.base,jdk.localedata --include-locales=vi-VN,fr-FR,ja-JP --output image-selected-locales
~~~

**Hai điểm quan trọng của `include-locales`:**

1. Khi dùng `--include-locales`, **phải thêm module `jdk.localedata`** trong tập module đưa vào image. Plug-in không có ý nghĩa như một yêu cầu “tự tải ngôn ngữ về”.
2. Danh sách `vi-VN,fr-FR,ja-JP` là **language tags** theo BCP 47. Plug-in có quy tắc matching locale; có thể dùng các mẫu ngôn ngữ/vùng như `en,ja,*-IN` trong ví dụ tài liệu Oracle. Không tự coi `vi` và `vi-VN` luôn giống nhau cho mọi bộ dữ liệu và dịch vụ; kiểm tra tập locale thực tế sau khi build.

`--include-locales` **không được hiểu là bộ lọc toàn bộ String/ResourceBundle của ứng dụng**. Nó lọc phần dữ liệu locale tương ứng trong module `jdk.localedata` của image. Nó cũng không chuyển đổi các tệp dữ liệu người dùng sang tiếng Việt/Pháp/Nhật.

Một cách chọn locale chỉ phù hợp nếu bạn biết danh sách locale mà **sản phẩm phải hỗ trợ**; cần cân bằng kích thước image với chất lượng bản địa hóa.

## 9. Ví dụ Java 17+: dò module, locale và kết quả định dạng

Việc có/không có module mới chỉ là tín hiệu đầu tiên. Bạn cần **kiểm tra kết quả chạy thực tế** bằng các API của sản phẩm.

Tạo file `LocaleDataProbe.java`:

~~~java
import java.lang.module.ModuleFinder;
import java.text.DateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Arrays;
import java.util.Locale;

public class LocaleDataProbe {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale fr = Locale.FRANCE;
        LocalDate day = LocalDate.of(2026, 10, 28);

        boolean hasModule = ModuleFinder.ofSystem()
                .find("jdk.localedata").isPresent();

        System.out.println("module present: " + hasModule);
        System.out.println("date vi available: "
                + Arrays.asList(DateFormat.getAvailableLocales())
                        .contains(vi));
        System.out.println("date fr available: "
                + Arrays.asList(DateFormat.getAvailableLocales())
                        .contains(fr));

        DateTimeFormatter longDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

        System.out.println("vi: "
                + longDate.withLocale(vi).format(day));
        System.out.println("fr: "
                + longDate.withLocale(fr).format(day));
        System.out.println("us: "
                + longDate.withLocale(Locale.US).format(day));
    }
}
~~~

Biên dịch bằng JDK 17+:

~~~bash
javac -encoding UTF-8 LocaleDataProbe.java
~~~

Chạy trên JDK đầy đủ:

~~~bash
java LocaleDataProbe
~~~

Ví dụ stdout đã kiểm tra trên OpenJDK 24 có dữ liệu locale mở rộng:

~~~text
module present: true
date vi available: true
date fr available: true
vi: 28 tháng 10, 2026
fr: 28 octobre 2026
us: October 28, 2026
~~~

Khi chạy trên một runtime image bị lọc hoặc không có `jdk.localedata`, **kết quả có thể khác**; nhất là không được sao chép nguyên stdout của full JDK thành kỳ vọng cố định cho image thu gọn.

Phân tích các tín hiệu:

- `ModuleFinder.ofSystem().find("jdk.localedata")` kiểm tra module **có trong hệ thống module hiện tại**. Nó không chứng minh module đã được resolve trong boot layer, cũng không đếm các locale được giữ sau lọc.
- `DateFormat.getAvailableLocales()` liệt kê các locale được dịch vụ `DateFormat` công bố có sẵn; nó **không** bảo đảm các dịch vụ `java.time`, tiền tệ và số đều có cùng mức dữ liệu hoặc từng chuỗi hiển thị khớp kỳ vọng.
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(...)` kiểm tra **hành vi định dạng thật** cho ngày và locale đã chọn.
- Chuỗi ngày tháng có thể thay đổi theo JDK/CLDR provider; kiểm tra semantic và môi trường mục tiêu, không mặc định dữ liệu dịch thuật bất biến mãi mãi.

Một module có sẵn có thể không nằm trong **module graph được resolve** của ứng dụng; cần xem thêm cấu hình launcher/đồ thị module nếu có tình huống provider không được sử dụng. Trong thực tế, thử nghiệm output là bước không thể thiếu.

## 10. Chạy cùng class trên nhiều runtime để so sánh

Sau khi biên dịch `LocaleDataProbe.java` thành `LocaleDataProbe.class` trong thư mục làm việc, chạy **cùng class** bằng các launcher khác nhau:

Linux/macOS:

~~~bash
java -cp . LocaleDataProbe
./image-base/bin/java -cp . LocaleDataProbe
./image-full-locale/bin/java -cp . LocaleDataProbe
./image-selected-locales/bin/java -cp . LocaleDataProbe
~~~

Windows PowerShell:

~~~powershell
java -cp . LocaleDataProbe
.\image-base\bin\java.exe -cp . LocaleDataProbe
.\image-full-locale\bin\java.exe -cp . LocaleDataProbe
.\image-selected-locales\bin\java.exe -cp . LocaleDataProbe
~~~

**Đảm bảo phiên bản JDK dùng biên dịch tương thích với Java launcher trong image.** Nếu class được biên dịch cho Java 24 nhưng image chỉ chạy Java 17, chương trình có thể ném `UnsupportedClassVersionError`; đó không phải lỗi locale.

Khi so sánh, giữ cố định:

1. Bytecode chương trình, dữ liệu ngày/giờ và số đầu vào.
2. `Locale` được truyền tường minh.
3. Phiên bản JDK/CLDR nếu có thể.
4. Provider selection, module graph, môi trường chạy và biến cấu hình liên quan.

Sau đó thay đổi **duy nhất runtime image** để thấy ảnh hưởng của gói locale data. Nếu vừa thay version JDK vừa thay `java.locale.providers`, rất khó quy kết nguyên nhân từ một khác biệt trong output.

## 11. Tại sao fallback không luôn gây lỗi?

Một dịch vụ định dạng có thể dự phòng từ locale cụ thể sang locale cha, từ nguồn dữ liệu hiện có khác, hoặc dữ liệu gốc theo cơ chế của API/provider. Nếu người dùng yêu cầu `vi-VN` mà image thiếu dữ liệu phù hợp, bạn có thể gặp:

- Tên tháng/thứ không ở ngôn ngữ mong đợi.
- Mẫu ngày tháng thay đổi thứ tự hoặc dấu câu.
- Cách nhóm số, dấu thập phân hoặc ký hiệu tiền tệ khác.
- Tên hiển thị quốc gia/tiền tệ trở về mã hay tên trong locale khác.
- Một dịch vụ có output có vẻ bình thường, trong khi dịch vụ khác thiếu bản địa hóa.

**Không tuyên bố chắc chắn một chuỗi fallback duy nhất** cho mọi phiên bản JDK hoặc provider. Output cụ thể phải được xác minh trên image thực tế.

Việc `Locale.forLanguageTag("vi-VN")` thành công, hoặc ngày ISO `2026-10-28` vẫn format được, không chứng minh tên tháng tiếng Việt có mặt. Một formatter toàn chữ số có thể che giấu việc thiếu dữ liệu locale. Cần test những phần **thực sự phải bản địa hóa**, chẳng hạn `MMMM` hoặc `FormatStyle.LONG`.

## 12. Kiểm thử NumberFormat và Currency trên image

Ngày tháng không phải đối tượng duy nhất của locale data. Một ứng dụng tài chính nên kiểm tra cả định dạng số và cách trình bày tiền tệ.

Tạo `LocaleNumberProbe.java`:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class LocaleNumberProbe {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale fr = Locale.FRANCE;
        Currency usd = Currency.getInstance("USD");

        NumberFormat viNumber = NumberFormat.getNumberInstance(vi);
        NumberFormat frNumber = NumberFormat.getNumberInstance(fr);

        System.out.println("vi number: "
                + viNumber.format(1234.5));
        System.out.println("fr number: "
                + frNumber.format(1234.5));
        System.out.println("USD name vi: "
                + usd.getDisplayName(vi));
        System.out.println("USD name fr: "
                + usd.getDisplayName(fr));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocaleNumberProbe.java
java LocaleNumberProbe
~~~

**Không ấn định một stdout cố định cho ví dụ này**: định dạng số, khoảng trắng có thể là NBSP/narrow NBSP, tên hiển thị tiền tệ và provider có thể khác theo JDK/CLDR. Mục tiêu là chạy **cùng class ở hai image** và so sánh hành vi.

Đừng so sánh bằng cách nhìn mắt thường khi có dấu cách Unicode đặc biệt. Nếu một test thất bại dù đầu ra trông gần giống nhau, hãy in các code point (ví dụ dùng `String.codePoints()`) để xác định có `U+00A0` hay `U+202F`.

**Phân biệt currency metadata và tên được dịch:** việc `Currency.getInstance("USD")` tồn tại không chứng minh tên tiếng Việt hoặc ký hiệu mong đợi có trong runtime. Nếu một API dùng metadata đơn vị còn API khác dùng dữ liệu hiển thị theo locale, sự hiện diện module/locale vẫn phải được kiểm tra theo đúng dịch vụ.

## 13. Locale provider và `java.locale.providers`

Java có kiến trúc **Locale Service Provider**. Dữ liệu locale có thể được cấp bởi những provider khác nhau tùy phiên bản, runtime và cấu hình. Hệ sinh thái JDK hiện đại dùng dữ liệu **CLDR** rộng rãi để bản địa hóa.

System property `java.locale.providers` cho phép cấu hình thứ tự/loại provider được ưu tiên trong những phiên bản hỗ trợ. Ví dụ chạy probe bằng CLDR:

~~~bash
java -Djava.locale.providers=CLDR -cp . LocaleDataProbe
~~~

Khi so sánh, hãy giữ cùng cấu hình provider trên cả JDK đầy đủ và image được tạo bằng `jlink`.

**Các bẫy thường gặp:**

- Đổi property provider **không tự thêm** dữ liệu locale đã bị loại khỏi image.
- Những provider legacy hoặc tên cấu hình hợp lệ có thể khác giữa các đời JDK; không áp một danh sách provider của JDK cũ lên mọi runtime mới.
- Việc có thêm provider không chứng minh mọi dịch vụ/locale được hỗ trợ bởi cùng provider.
- Tùy chỉnh property lúc quá muộn trong quá trình chạy có thể không làm các dịch vụ đã khởi tạo tự động chuyển nguồn; nên cấu hình từ lúc JVM start nếu cần.

Khi chẩn đoán, ghi lại Java version, module list, provider property và đầu ra định dạng thực tế trước khi kết luận.

## 14. Tùy chỉnh runtime đúng nghĩa: image và ứng dụng

Một custom runtime image **khác** với file ứng dụng `.jar` hoặc module của bạn. `jlink` tạo thư mục runtime gồm Java launcher, module system image và các tài nguyên liên quan. Bạn còn phải phân phối ứng dụng (hoặc tích hợp bằng công cụ đóng gói khác) tùy cách build.

Các trường hợp phổ biến:

- **Ứng dụng modular** có `module-info.java`: image cần module ứng dụng và các phụ thuộc.
- **Ứng dụng chạy trên classpath**: có thể tạo image chứa các JDK modules cần thiết rồi chạy classpath với Java launcher của image.
- **Ứng dụng desktop**: có thể dùng `jpackage` dựa trên custom runtime và bộ đóng gói cho nền tảng.
- **Ứng dụng container/server**: image chạy trong container phải chứa đúng tập JDK modules, bao gồm `jdk.localedata` nếu cần dữ liệu locale ngoài base.

Không lấy ví dụ `jlink --add-modules java.base,jdk.localedata` làm công thức cho mọi ứng dụng thực tế. Nó chỉ minh họa sự hiện diện dữ liệu locale; phần module ứng dụng, service binding và các dependency cần được xác định riêng.

Một lỗi thường gặp là JDK trong CI có đủ `jdk.localedata`, nhưng runtime image trong Docker hoặc bản desktop release lại thiếu. Vì vậy các test bản địa hóa cần chạy trên **artifact cuối cùng**, không chỉ trên máy build.

## 15. Kích thước image và chiến lược chọn locale

Đóng gói toàn bộ `jdk.localedata` thường làm image lớn hơn bản tối giản. Lọc locale bằng `--include-locales` có thể giảm dữ liệu đi kèm, nhưng quá chặt sẽ gây fallback khi ứng dụng thực sự phục vụ ngôn ngữ khác.

Cách chọn:

1. Liệt kê locale sản phẩm **cam kết hỗ trợ**, gồm language tag đầy đủ và vùng/script khi cần.
2. Xác định API sử dụng: ngày/giờ, số/tiền tệ, tên quốc gia, collator và tài nguyên riêng.
3. Xem nhu cầu các **parent locales**, vùng và extension tương ứng; dựa vào tài liệu matching của `jlink` rồi kiểm tra thực tế.
4. Thêm `jdk.localedata` và dùng `--include-locales` phù hợp.
5. Chạy probe trên image mới và kiểm tra dịch vụ theo từng locale.
6. Đo kích thước image, khởi động và chất lượng bản địa hóa; tối ưu sau khi bảo đảm tính đúng.
7. Nếu sản phẩm bổ sung locale, cập nhật cấu hình `jlink` và regression tests cùng lúc.

**Không giả định** chỉ việc đặt ngôn ngữ của UI thành `vi` thì mọi nhu cầu định dạng `vi-VN`, locale extension hoặc các vùng khác đều được bao phủ. Đồng thời, không cần đóng gói tất cả locale nếu sản phẩm thật sự chỉ sử dụng một tập nhỏ và đã kiểm thử.

## 16. Một chiến lược QA cho CI/CD

Có thể xây bài kiểm tra tự động gồm các bước:

### 16.1. Kiểm tra module

Chạy launcher của image:

~~~bash
./image-selected-locales/bin/java --list-modules
~~~

Xác nhận `jdk.localedata` xuất hiện khi image được yêu cầu hỗ trợ dữ liệu locale mở rộng.

### 16.2. Kiểm tra phạm vi locale

Dùng `DateFormat.getAvailableLocales()` hoặc API `getAvailableLocales()` tương ứng của dịch vụ. Xác nhận danh sách chứa các locale bắt buộc và ghi nhận những locale không có.

### 16.3. Kiểm tra output thật

Format một ngày cố định `2026-10-28`, một số `1234.5` và một tiền tệ cụ thể bằng locale yêu cầu. Với locale tiếng Việt, kiểm tra tên tháng thực sự là tên tiếng Việt khi theo chính sách sản phẩm; với locale Pháp, kiểm tra tên tháng tiếng Pháp.

**Không chỉ kiểm tra length hoặc “không ném exception”**. Dịch vụ có fallback vẫn có thể chạy thành công với ngôn ngữ không mong đợi.

### 16.4. Kiểm thử chính image phát hành

Trong CI/CD, chạy kiểm thử **sau khi tạo image** và trước publish. Nếu có nhiều image (Linux, Windows, macOS hoặc các kiến trúc), kiểm tra từng artifact phù hợp; `jlink` thường tạo runtime gắn với nền tảng của JDK nguồn.

### 16.5. Lưu bằng chứng build

Ghi thông tin JDK version, danh sách module, tập language tags được chọn, phiên bản công cụ build và kết quả probe. Khi nâng JDK, dữ liệu CLDR có thể thay đổi mà source code không đổi; so sánh các thay đổi đó có chủ đích.

## 17. Những ngộ nhận cần tránh

| Ngộ nhận | Thực tế | Hướng xử lý |
| --- | --- | --- |
| `Locale.forLanguageTag` thành công là đủ dữ liệu | Nó chỉ tạo locale identifier | Kiểm thử provider/output |
| `java.base` chứa mọi bản dịch | Chỉ có dữ liệu locale cơ bản trong nhiều JDK | Thêm `jdk.localedata` khi cần |
| Có `jdk.localedata` là có mọi locale | Có thể đã bị lọc bằng `--include-locales` | Kiểm tra tập locale thực tế |
| Không có module là tất cả API locale thất bại | Các API vẫn có thể fallback | Quan sát định dạng thật |
| `--include-locales` tự tải/generate dữ liệu | Nó chọn dữ liệu đã có trong JDK | Build bằng JDK nguồn phù hợp |
| `--include-locales` hoạt động mà không add `jdk.localedata` | Plug-in yêu cầu module | Add module và kiểm tra output |
| Dữ liệu `ResourceBundle` của app nằm trong `jdk.localedata` | Đây là tài nguyên ứng dụng riêng | Đóng gói và test riêng |
| `getAvailableLocales` đảm bảo mọi dịch vụ có đủ tài nguyên | Mỗi dịch vụ/provider có đặc điểm riêng | Test API sử dụng |
| Locale thiếu luôn ném exception | Fallback thường không báo lỗi | Kiểm tra tên tháng/dấu số |
| Date/number ISO còn chạy là locale đầy đủ | Output chỉ toàn chữ số có thể che thiếu dữ liệu | Kiểm thử tên tháng/tiền tệ |
| Property provider khôi phục dữ liệu đã bị cắt | Property chỉ điều chỉnh lựa chọn provider | Bổ sung dữ liệu vào image |
| Test thành công trên full JDK là đủ | Image release có module/data khác | Chạy test trên artifact cuối |
| Nâng JDK không ảnh hưởng output localized | CLDR/data cập nhật theo phiên bản | Pin/test runtime khi cần |
| Locale là timezone | Locale và `ZoneId` độc lập | Cấu hình đúng ngữ cảnh |

## 18. Checklist thực hành

1. **Nguồn JDK:** xác minh `java -version` và `jlink --version` thuộc bản JDK dự kiến.
2. **Module:** chạy `java --list-modules` của custom image; kiểm tra `jdk.localedata`.
3. **Jlink config:** nếu dùng `--include-locales`, có `jdk.localedata` trong `--add-modules`.
4. **Ngôn ngữ:** liệt kê `vi-VN`, `fr-FR`, `ja-JP` hoặc các BCP 47 tags bắt buộc.
5. **Provider:** ghi nhận `java.locale.providers` và tránh dùng cấu hình provider không có trên JDK đích.
6. **Ngày:** test tên tháng/thứ và localized style chứ không chỉ ISO numeric format.
7. **Số:** test dấu thập phân, phân nhóm, phần trăm và số âm.
8. **Tiền tệ:** test ký hiệu/tên hiển thị theo locale và precision phù hợp.
9. **Locale listing:** dùng đúng `getAvailableLocales` theo dịch vụ cần kiểm tra.
10. **Fallback:** nếu thiếu locale, xác nhận hành vi mong muốn hoặc chặn release.
11. **ResourceBundle:** xác nhận các bundle do ứng dụng cung cấp có trong artifact.
12. **Phần mềm đóng gói:** kiểm tra runtime được launcher thật sự sử dụng.
13. **Chạy thử:** dùng cùng class probe trên full JDK và image nhỏ.
14. **Tính ổn định:** dữ liệu thử cố định, không dùng ngày/giờ hiện tại.
15. **CLDR:** khi nâng JDK, xác định khác biệt format là cập nhật dữ liệu hay lỗi thiếu module.
16. **Release:** tự động kiểm thử artifact được phát hành, không chỉ source hoặc CI host.

### Bài tập

- Tạo image chỉ có `java.base` rồi chạy `LocaleDataProbe`. So sánh danh sách module và định dạng `vi-VN` với full JDK.
- Tạo image `java.base,jdk.localedata` không dùng `--include-locales`. So sánh với image có chọn `vi-VN,fr-FR`.
- Dùng `--include-locales=vi-VN` để tạo image chuyên cho Việt Nam, sau đó thử `Locale.FRANCE` và giải thích fallback.
- Với `NumberFormat.getNumberInstance(Locale.FRANCE)`, in code points của formatted string để tìm dấu phân nhóm không phải ASCII.
- Thiết kế kiểm thử `Currency.getDisplayName(Locale.forLanguageTag("vi-VN"))` trên image và so sánh với full JDK.
- Thêm các locale `en-US`, `ja-JP`, `vi-VN` vào danh sách test, chỉ định đâu là cam kết sản phẩm và đâu là fallback chấp nhận được.
- Viết pipeline build thất bại nếu image release không có module hoặc không đạt kiểm thử định dạng cho các locale bắt buộc.

## 19. Kết luận

`java.base` cung cấp API và dữ liệu locale cơ bản; **`jdk.localedata` cung cấp dữ liệu locale mở rộng** trong các bản JDK được tài liệu hóa. Khi tạo custom runtime image bằng `jlink`, phải đưa `jdk.localedata` vào nếu cần bản địa hóa ngoài tập cơ bản, và có thể chọn lọc dữ liệu qua **`--include-locales`** để giảm kích thước.

**Một `Locale` tồn tại không bảo đảm dữ liệu format tồn tại.** Vì vậy, đừng chỉ kiểm tra code chạy mà phải xác minh chính launcher của image, module list, tập locale khả dụng và kết quả định dạng ngày/số/tiền tệ thực tế. Đồng thời tách tài nguyên bản dịch ứng dụng khỏi dữ liệu JDK và giữ môi trường/phiên bản CLDR nhất quán khi test.

Lựa chọn đúng không phải “đóng gói tất cả locale” bằng mọi giá, mà là **đóng gói đủ những locale sản phẩm cam kết hỗ trợ và kiểm thử trực tiếp trên runtime image phát hành**.

## Tài liệu tham khảo chính thức

- [Oracle JDK 17 — Supported Locales, Locales and Modules](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html)
- [Oracle Java 21 — jlink command và plug-in include-locales](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Oracle Java 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html)
- [Oracle Java 21 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [OpenJDK — jlink: The Java Linker (JEP 282)](https://openjdk.org/jeps/282)
