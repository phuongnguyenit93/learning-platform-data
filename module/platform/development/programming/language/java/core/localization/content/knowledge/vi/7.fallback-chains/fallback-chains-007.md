# Định nghĩa chính sách dự phòng không phụ thuộc môi trường

Trong Java Core, ứng dụng quốc tế hóa thường có nhiều bộ thông điệp theo ngôn ngữ, chẳng hạn **messages_vi.properties**, **messages_fr.properties** và **messages.properties**. Khi người dùng yêu cầu một locale không có bản dịch, hoặc một khóa thiếu trong bản dịch, chương trình phải quyết định nội dung dự phòng. Nếu không định nghĩa chính sách rõ ràng, kết quả có thể bị ảnh hưởng bởi **Locale mặc định của JVM**: cùng một request có thể nhận thông điệp khác nhau trên máy phát triển, CI và máy chủ.

Bài học này giải thích cách **định nghĩa một chuỗi dự phòng (fallback chain) ổn định, có thể dự đoán và kiểm thử**, độc lập với mặc định của môi trường chạy. Trọng tâm là chọn locale, tìm resource bundle, xử lý thông điệp thiếu khóa và kiểm tra tính nhất quán của kết quả bằng các API Java 17+.

## 1. “Không phụ thuộc môi trường” nghĩa là gì?

Một chính sách dự phòng xác định phải trả cùng kết quả khi có cùng:

1. **Đầu vào người dùng**: locale yêu cầu hoặc preference đã lưu.
2. **Cấu hình ứng dụng**: danh sách locale được hỗ trợ, locale mặc định, chiến lược lựa chọn bản dịch.
3. **Tập resource đã triển khai**: các file bundle và khóa bên trong.
4. **Quy tắc xử lý**: thứ tự ứng viên, hành vi thiếu bundle hoặc thiếu khóa.

Nó **không** được âm thầm phụ thuộc vào ngôn ngữ của tài khoản hệ điều hành, locale của runner CI, hoặc việc một thư viện khác thay đổi **Locale.setDefault(...)** trong cùng JVM.

Ví dụ một hệ thống hỗ trợ **vi-VN** và **fr-FR**, mặc định ứng dụng **vi-VN**:

| Đầu vào | Kết quả chọn locale theo chính sách mẫu |
| --- | --- |
| User yêu cầu **fr-FR** | **fr-FR** |
| User yêu cầu **vi-VN** | **vi-VN** |
| User yêu cầu **es-ES** (không hỗ trợ) | **vi-VN** |
| Không có lựa chọn nào | **vi-VN** |
| JVM trên server đặt **en-US** | Không thay đổi các kết quả trên |
| JVM trong CI đặt **de-DE** | Không thay đổi các kết quả trên |

Cần phân biệt **kết quả chọn locale** và **nội dung của từng thông điệp**. Chọn **fr-FR** không đảm bảo tất cả khóa trong bundle tiếng Pháp đã được dịch. Vì thế chính sách dự phòng thực tế có **hai tầng**, cần xác định riêng.

## 2. Hai tầng dự phòng thường bị nhầm lẫn

### Tầng A – chọn locale hiệu lực của ứng dụng

Đây là câu trả lời cho câu hỏi: **“Với request này, ứng dụng cam kết sử dụng locale nào?”**

Một chính sách mẫu:

~~~text
Locale người dùng chọn trực tiếp
   ↓ nếu thiếu, sai hoặc không hỗ trợ
Locale đã lưu của tài khoản
   ↓ nếu thiếu, sai hoặc không hỗ trợ
Locale được thương lượng từ client
   ↓ nếu không có lựa chọn phù hợp
Locale mặc định riêng của ứng dụng (vi-VN)
~~~

Đây là **quyết định của sản phẩm**, không phải quy tắc tự có của **java.util.Locale**. Có ứng dụng chọn cách báo lỗi ngay khi user gửi locale không được hỗ trợ; có ứng dụng bỏ qua và tiếp tục xuống nguồn kế tiếp. Điều quan trọng là quy tắc phải được ghi thành hợp đồng và kiểm thử.

### Tầng B – tìm bản dịch cho một khóa

Sau khi đã chọn **fr-FR**, ứng dụng vẫn phải tìm khóa **checkout.submit** trong resource bundles. Chuỗi ví dụ:

~~~text
messages_fr_FR.properties
   ↓ nếu thiếu bộ hoặc thiếu khóa
messages_fr.properties
   ↓ nếu không có giá trị phù hợp
messages.properties (resource gốc)
   ↓ nếu khóa vẫn không tồn tại
Báo lỗi thiếu key theo chính sách
~~~

Đây là cách suy nghĩ về **candidate chain và parent lookup** của ResourceBundle, với giả định tệp gốc tồn tại và chính sách chọn các candidate tương ứng. **messages.properties** là tài nguyên gốc có nội dung được tác giả chủ động biên soạn; nó **không mặc nhiên trùng** với ngôn ngữ của application default.

Nếu **application default = vi-VN** nhưng **messages.properties** chứa tiếng Anh, yêu cầu **fr-FR** có thể tìm được locale tiếng Pháp cho một số khóa, rồi fallback sang tiếng Anh cho khóa khác. Đó là lựa chọn phải được quản trị, không phải bằng chứng đã chọn nhầm locale.

**Quy tắc then chốt:** đừng diễn đạt mơ hồ “thiếu thì dùng mặc định” mà không nêu rõ **mặc định của tầng A** hay **resource gốc của tầng B**.

## 3. Vì sao ResourceBundle mặc định có thể phụ thuộc JVM?

Java cung cấp nhiều overload của **ResourceBundle.getBundle**:

~~~java
ResourceBundle.getBundle("messages");
ResourceBundle.getBundle("messages", requestedLocale);
~~~

Đây là hai lời gọi minh họa, cần import **java.util.ResourceBundle**, biến **requestedLocale**, và tệp bundle trên classpath.

- **getBundle(baseName)** chọn locale mặc định của JVM làm locale yêu cầu ban đầu.
- **getBundle(baseName, locale)** lấy locale yêu cầu tường minh, nhưng với cơ chế **ResourceBundle.Control mặc định** vẫn có thể thực hiện một lượt fallback về **Locale.getDefault()** khi không tìm thấy bundle phù hợp và chính sách mặc định cho phép.

Ví dụ chỉ có **messages_en.properties** và **messages_de.properties**, không có bundle gốc. Khi yêu cầu **fr-FR**, một máy có default **en-US** có thể lấy bundle tiếng Anh, còn máy default **de-DE** có thể lấy tiếng Đức. Vì ứng dụng không quy định chính sách, môi trường đã vô tình quyết định ngôn ngữ phản hồi.

Mặc dù hai máy nhận cùng tham số **Locale.FRANCE**, kết quả vẫn có thể khác. Việc truyền locale vào **getBundle** là điều cần thiết nhưng **chưa đủ** nếu muốn kiểm soát chặt fallback khi thiếu resource.

**Cách tránh:** ứng dụng phải chủ động quyết định supported locales và fallback của request; đồng thời kiểm soát fallback khi tra ResourceBundle bằng một cơ chế rõ ràng.

## 4. Khai báo hợp đồng dự phòng trước khi viết code

Một chính sách có thể viết thành tài liệu như sau:

| Quy tắc | Chính sách ví dụ |
| --- | --- |
| Locale hỗ trợ | Chỉ **vi-VN**, **fr-FR** |
| Application default | **vi-VN** |
| Locale yêu cầu hợp lệ nhưng chưa hỗ trợ | Thử nguồn preference kế tiếp; nếu không có, dùng **vi-VN** |
| Locale sai cú pháp | Không chấp nhận làm locale hiệu lực; tùy ngữ cảnh báo lỗi hoặc fallback có kiểm soát |
| Cách so khớp | Exact match với danh sách hỗ trợ; không đoán vùng hoặc chữ viết |
| Resource bundle | File **messages** trên classpath, UTF-8 |
| Fallback theo JVM default | **Không cho phép** |
| Bundle mức vùng không có | Thử bundle mức ngôn ngữ, rồi bundle gốc theo candidate chain |
| Khóa thiếu trong bản dịch | Thử parent của bundle theo chính sách |
| Khóa thiếu trong toàn bộ chain | **MissingResourceException** hoặc lỗi ứng dụng có kiểm soát |
| Resource gốc | Nội dung chuẩn xác định trong **messages.properties** |
| Mọi môi trường | Cùng cấu hình, cùng resource và quy tắc; không đọc default JVM khi quyết định locale |

Dữ liệu hỗ trợ cần phản ánh những ngôn ngữ **thực sự có tài nguyên và được kiểm duyệt**. API **Locale.forLanguageTag("es-ES")** tạo được locale tiếng Tây Ban Nha, nhưng bản thân nó không tạo ra bản dịch tiếng Tây Ban Nha.

Nếu ứng dụng có nhiều tenant, danh sách locale hỗ trợ và app default có thể là cấu hình theo tenant. Dù vậy, **cấu hình của tenant hiện hành phải được xác định bởi dữ liệu nghiệp vụ**, không được lấy từ locale máy chủ. Nếu một tenant không hỗ trợ locale mặc định đã khai báo, ứng dụng cần phát hiện lỗi cấu hình khi khởi tạo hoặc nhận yêu cầu.

## 5. ResourceBundle.Control: loại bỏ fallback sang JVM default

Trong ứng dụng Java chạy trên classpath truyền thống, **ResourceBundle.Control** có hàm tạo một control không dùng default locale của JVM để fallback:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "messages", selectedLocale, control);
~~~

Đoạn minh họa cần import **java.util.ResourceBundle**, một biến **selectedLocale** đã được giải quyết, và resource **messages**. Với control này, **getFallbackLocale(...)** trả **null**: sau khi kiểm tra chuỗi candidate theo locale yêu cầu, quá trình tra cứu không chuyển sang locale mặc định JVM như vòng fallback bổ sung.

**Điều không thay đổi**: control vẫn cho phép chuỗi candidate vùng/ngôn ngữ và resource gốc theo mặc định; các khóa có thể được tìm trong parent bundle. Vì vậy **getNoFallbackControl(...)** không có nghĩa là “không fallback gì cả”.

Hai lựa chọn phổ biến:

- **FORMAT_PROPERTIES:** yêu cầu dùng bundle ở dạng **.properties**.
- **FORMAT_DEFAULT:** cho phép cả class-based bundle và .properties theo cơ chế mặc định.

Nếu muốn chỉ sử dụng định dạng properties, **FORMAT_PROPERTIES** giúp hợp đồng rõ ràng hơn. Nên giữ resource trên classpath có cấu trúc được kiểm thử, hoặc có cách đóng gói tương đương.

**Giới hạn API:** Với **named modules** (JPMS), các overload **ResourceBundle.getBundle** sử dụng **Control** có thể không được hỗ trợ theo cách classpath truyền thống và ném **UnsupportedOperationException**. Khi dùng named modules, chọn cơ chế bundle/provider tương ứng và kiểm thử thực tế; đừng sao chép giải pháp Control mà không xét packaging. Bài thực hành dưới đây dùng **classpath/unnamed module**, nơi overload này phù hợp.

## 6. Ví dụ hoàn chỉnh: cùng kết quả dù JVM default khác nhau

Ví dụ Java 17+ này có **một bộ resource gốc**, **hai bản dịch** và **một resolver**. Chương trình chủ động thay đổi default JVM trong **một tiến trình console cô lập** để chứng minh kết quả tra bundle vẫn xác định. Không dùng lối thay đổi default đó trong server đa người dùng.

### 6.1. Cấu trúc file

Đặt bốn file trong cùng một thư mục:

~~~text
LocaleFallbackDemo.java
messages.properties
messages_vi.properties
messages_fr.properties
~~~

**File messages.properties** – resource gốc, cố ý dùng tiếng Anh để minh họa fallback khóa:

~~~properties
greeting=Hello, {0}!
status=Status: ready.
~~~

**File messages_vi.properties**:

~~~properties
greeting=Xin chào, {0}!
status=Trạng thái: sẵn sàng.
~~~

**File messages_fr.properties** – cố ý thiếu khóa **status**:

~~~properties
greeting=Bonjour, {0}!
~~~

Từ Java 9, **PropertyResourceBundle** được đọc từ byte stream bằng UTF-8 theo mặc định, có cơ chế tương thích ISO-8859-1 với dữ liệu không hợp lệ. Với Java 17+, hãy lưu ba tệp properties ở **UTF-8**. Điều này khác API **Properties.load(InputStream)** có quy tắc ISO-8859-1; đừng áp dụng một quy tắc charset của API này cho API khác.

### 6.2. Mã Java độc lập

**File LocaleFallbackDemo.java**:

~~~java
import java.text.MessageFormat;
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleFallbackDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");
    private static final Locale FR =
            Locale.forLanguageTag("fr-FR");

    private static final List<Locale> SUPPORTED =
            List.of(VI, FR);

    private static final Locale APP_DEFAULT = VI;

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    public static void main(String[] args) {
        Locale oldGlobal = Locale.getDefault();
        Locale oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            for (Locale runtime : List.of(
                    Locale.US, Locale.GERMANY)) {
                // Chỉ làm điều này trong console demo độc lập.
                Locale.setDefault(runtime);

                printCase("fr-FR");
                printCase("es-ES");
            }
        } finally {
            Locale.setDefault(oldGlobal);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
        }
    }

    // Chọn locale hiệu lực theo cấu hình ứng dụng,
    // không dùng Locale.getDefault().
    private static Locale resolve(String requestedTag) {
        if (requestedTag == null || requestedTag.isBlank()) {
            return APP_DEFAULT;
        }

        final Locale requested;
        try {
            requested = new Locale.Builder()
                    .setLanguageTag(requestedTag.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            return APP_DEFAULT;
        }

        for (Locale supported : SUPPORTED) {
            if (supported.equals(requested)) {
                return supported;
            }
        }
        return APP_DEFAULT;
    }

    private static void printCase(String requestedTag) {
        Locale selected = resolve(requestedTag);
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", selected, CONTROL);

        MessageFormat formatter = new MessageFormat(
                bundle.getString("greeting"), selected);
        String greeting =
                formatter.format(new Object[] {"Mai"});

        String status = bundle.getString("status");

        System.out.println(
                "runtime=" + Locale.getDefault().toLanguageTag()
                + " | requested=" + requestedTag
                + " | selected=" + selected.toLanguageTag()
                + " | " + greeting
                + " | " + status);
    }
}
~~~

**Chạy chương trình:**

~~~bash
javac -encoding UTF-8 LocaleFallbackDemo.java
java -cp . LocaleFallbackDemo
~~~

**Stdout đúng theo các file đã cung cấp:**

~~~text
runtime=en-US | requested=fr-FR | selected=fr-FR | Bonjour, Mai! | Status: ready.
runtime=en-US | requested=es-ES | selected=vi-VN | Xin chào, Mai! | Trạng thái: sẵn sàng.
runtime=de-DE | requested=fr-FR | selected=fr-FR | Bonjour, Mai! | Status: ready.
runtime=de-DE | requested=es-ES | selected=vi-VN | Xin chào, Mai! | Trạng thái: sẵn sàng.
~~~

**Giải thích chi tiết:**

1. **fr-FR** thuộc danh sách hỗ trợ, nên resolver trả **fr-FR**. **messages_fr.properties** có khóa **greeting** nhưng thiếu **status**. ResourceBundle tìm **status** trong resource cha **messages.properties**, do đó nhận **Status: ready.**
2. **es-ES** không thuộc danh sách hỗ trợ nên resolver trả **vi-VN** theo **APP_DEFAULT**, sau đó ResourceBundle tìm **messages_vi.properties** và nhận hai câu tiếng Việt.
3. Việc đổi JVM default giữa **en-US** và **de-DE** chỉ thay giá trị in ở trường **runtime**. Cùng một requested tag vẫn giải quyết thành cùng locale và nội dung.
4. **MessageFormat** cũng nhận **selected** tường minh. Nếu pattern có tham số ngày/số, điều này giúp tránh thêm một đường phụ thuộc vào default locale.
5. **finally** khôi phục các default có sẵn trong phạm vi chương trình demo. Điều đó không làm **Locale.setDefault** an toàn cho request đồng thời; đây chỉ là phép thử có kiểm soát.

Kết quả có tiếng Anh **Status: ready.** khi chọn tiếng Pháp là **fallback cố ý của resource gốc**, không phải fallback ngẫu nhiên sang JVM default. Nếu sản phẩm cấm giao diện pha nhiều ngôn ngữ, cần chính sách khác ở tầng key hoặc kiểm tra đầy đủ bản dịch.

## 7. Không được nhầm “không fallback theo JVM” với “có bản dịch đầy đủ”

**ResourceBundle.getBundle("messages", fr, CONTROL)** trả một bundle theo candidate chain. Khi đọc **getString("status")**, hệ thống còn tìm khóa trong parent chain. Có ba tình huống:

| Tình huống | Hành vi cần xác định |
| --- | --- |
| Bundle được yêu cầu có khóa | Trả văn bản ở bundle đó |
| Bundle đó thiếu khóa, parent có | Có thể lấy khóa từ parent theo chuỗi bundle |
| Toàn bộ chain thiếu khóa | **MissingResourceException** khi gọi **getString** |
| Không có bundle phù hợp hoặc resource gốc | **MissingResourceException** khi không tìm được bundle nào |
| Locale yêu cầu không hỗ trợ nhưng có root | Nếu không kiểm tra supported trước, **getBundle** vẫn có thể trả root mà không phản ánh sự hỗ trợ thật |

Do đó một ứng dụng có chính sách “chỉ hiện bản dịch tiếng Pháp nếu đầy đủ, ngược lại hiện toàn bộ màn hình tiếng Việt” **không thể đạt được chỉ bằng** **getNoFallbackControl**. Đó là một yêu cầu bổ sung ở tầng nghiệp vụ: kiểm tra độ đầy đủ của bộ dịch, hoặc chọn toàn bộ ngôn ngữ dự phòng trước khi render.

Một hệ thống có thể chọn một trong những hợp đồng sau:

- **Fallback theo từng khóa:** cho phép mỗi khóa thiếu lấy nội dung của resource cha. Dễ triển khai, nhưng có thể xuất hiện nhiều ngôn ngữ trên cùng màn hình.
- **Bản dịch bắt buộc hoàn chỉnh:** quy trình build kiểm tra mọi khóa; không publish bộ dịch thiếu khóa quan trọng. Khi load bundle, thiếu khóa là lỗi cần xử lý.
- **Fallback theo màn hình/bộ nội dung:** nếu bundle không đạt độ đầy đủ cần thiết, chọn locale dự phòng cho toàn bộ màn hình hoặc nhóm thông điệp. Cần bộ kiểm tra hoàn chỉnh và thiết kế riêng; lookup mặc định của ResourceBundle không tự thực hiện giao dịch “all or nothing”.

Cần xác định hợp đồng nào phù hợp sản phẩm, viết nó thành kiểm thử và thông báo cho nhóm biên dịch. **Không để ResourceBundle mặc định tình cờ quyết định quy tắc trải nghiệm người dùng.**

## 8. Chọn chuỗi ứng viên locale một cách rõ ràng

### 8.1. Ngôn ngữ, vùng và chữ viết

Các locale sau thể hiện mức độ cụ thể khác nhau:

~~~text
fr-FR
fr
(root)
~~~

Một ứng dụng có thể có tệp **messages_fr_FR.properties**, **messages_fr.properties** và **messages.properties**. ResourceBundle tạo chuỗi ứng viên theo quy tắc của Control, thường ưu tiên biến thể/vùng cụ thể trước rồi mới đến ngôn ngữ và root.

Tuy nhiên, không nên giả định **mọi locale với cùng ngôn ngữ đều tương đương**. Với một số ngôn ngữ, script là yếu tố quan trọng, ví dụ **zh-Hans** và **zh-Hant**. Chính sách tự ánh xạ **zh-Hant-TW** về **zh-Hans-CN** chỉ vì cùng mã ngôn ngữ có thể dẫn đến trải nghiệm sai.

Nếu danh sách ứng dụng hỗ trợ cả **en-US** và **en-GB**, yêu cầu chỉ có **en** có thể nhập nhằng; cần một preferred variant được cấu hình hoặc yêu cầu người dùng chọn vùng. Đừng vô tình chọn phần tử đầu tiên từ tập hợp không có thứ tự ổn định.

### 8.2. Không giao việc chọn locale cho ResourceBundle

**ResourceBundle** là API tra tài nguyên, không phải chính sách sản phẩm. Nếu người dùng gửi locale **es-ES** nhưng sản phẩm chỉ hỗ trợ **vi-VN** và **fr-FR**, nên xác định trước **selected = vi-VN** theo hợp đồng rồi mới tìm bundle. Không nên gọi **getBundle("messages", Locale.forLanguageTag("es-ES"))** và coi kết quả bất kỳ nó trả là chứng cứ hệ thống hỗ trợ tiếng Tây Ban Nha.

Để parse một tag user cung cấp, **new Locale.Builder().setLanguageTag(...)** có thể phát hiện lỗi cú pháp qua **IllformedLocaleException**. Ngay cả tag hợp lệ, vẫn phải đối chiếu whitelist; tạo được Locale không đồng nghĩa có resource.

### 8.3. Tránh vòng fallback khó kiểm soát

Đối với yêu cầu phức tạp, hãy phác thảo thứ tự đầy đủ bằng ví dụ cụ thể:

~~~text
Người dùng yêu cầu fr-CA
    ↓ ứng dụng chỉ hỗ trợ fr-FR, vi-VN
Ứng dụng có cho phép khớp cùng ngôn ngữ?
    ├─ Không  → selected = vi-VN
    └─ Có     → selected = fr-FR (nếu ánh xạ được cấu hình)
                  ↓
ResourceBundle chọn messages_fr.properties
                  ↓
Khóa thiếu lấy từ messages.properties (nếu chính sách cho phép)
                  ↓
Không bao giờ tự chuyển qua locale của JVM
~~~

Không để logic locale của request và logic fallback resource thực thi trùng lặp theo cách khó giải thích. Cũng không nhầm thứ tự resource candidates của Java với danh sách locale UI mà ứng dụng tuyên bố hỗ trợ.

## 9. Mặc định của ứng dụng phải ổn định và hợp lệ

Một cấu hình hợp đồng có thể mô tả bằng YAML:

~~~yaml
localization:
  supported-locales:
    - vi-VN
    - fr-FR
  default-locale: vi-VN
  unsupported-request: use-app-default
  bundle-base-name: messages
  jvm-default-fallback: false
  missing-key: use-parent-bundle
~~~

Đây là **cấu hình minh họa**, không phải thuộc tính Java Core tự đọc. Ứng dụng phải tự nạp, xác minh và hiện thực các trường.

Tại khởi động, nên kiểm tra:

1. **default-locale** thuộc supported locales.
2. Mỗi language tag hợp lệ; không có hai cấu hình trùng nhau sau khi chuẩn hóa.
3. Các bundle tồn tại trên classpath đúng tên/gói theo chính sách.
4. Resource gốc tồn tại nếu chính sách phụ thuộc vào root.
5. Những khóa bắt buộc của ngôn ngữ mặc định có mặt, không bị trùng hoặc bỏ sót.
6. Chiến lược key fallback không làm mất những thông điệp quan trọng như lỗi bảo mật, xác nhận giao dịch hoặc yêu cầu pháp lý.

Một lỗi cấu hình được phát hiện khi deploy dễ xử lý hơn lỗi **MissingResourceException** chỉ xuất hiện khi người dùng mở trang hiếm dùng trong production.

## 10. Hạn chế phụ thuộc vào default còn lại

Kiểm soát ResourceBundle chưa đủ nếu các API khác tiếp tục lấy locale mặc định:

~~~java
NumberFormat number = NumberFormat.getNumberInstance();
String report = String.format("%.2f", 1234.5);
~~~

Đây là các đoạn minh họa cần import **java.text.NumberFormat**. Hai lời gọi không có locale nên có thể sử dụng default **FORMAT**. Để ứng dụng nhất quán:

~~~java
NumberFormat number =
        NumberFormat.getNumberInstance(selectedLocale);

String report = String.format(
        selectedLocale, "%.2f", 1234.5);
~~~

Lúc này **selectedLocale** phải được lấy từ resolver đã áp dụng chính sách. Với báo cáo máy đọc có hợp đồng kỹ thuật, có thể cần định dạng số cố định như **Locale.ROOT** hoặc một chuẩn độc lập ngôn ngữ; còn dữ liệu hiển thị cho người dùng nên dùng locale của chính họ.

Đối với ngày giờ, **DateTimeFormatter.withLocale(selectedLocale)** xác định ngôn ngữ/quy ước, nhưng **múi giờ** phải được chọn riêng bằng **ZoneId**. Không suy múi giờ từ ngôn ngữ. Với chữ hoa/thường của mã kỹ thuật, **String.toLowerCase(Locale.ROOT)** có thể thích hợp để tránh quy tắc case mapping theo ngôn ngữ hệ thống.

**Locale.setDefault(...)** thay đổi trạng thái dùng chung của JVM, không phải trạng thái của mỗi request. Trong server nhiều request, dùng nó để “chuyển ngôn ngữ cho người dùng này” có thể làm request khác định dạng sai hoặc tra bundle sai. Luôn truyền locale đã giải quyết vào các API ở nơi tiêu thụ.

## 11. Kiểm thử tính độc lập môi trường

### 11.1. Kiểm thử một resolver thuần

Giải quyết locale nên là một hàm dễ kiểm thử: cùng input và cùng cấu hình → cùng **selectedLocale**. Ví dụ những ca tối thiểu khi supported là **vi-VN**, **fr-FR**, default là **vi-VN**:

| Request | Selected | Ghi chú |
| --- | --- | --- |
| vi-VN | vi-VN | Được hỗ trợ trực tiếp |
| fr-FR | fr-FR | Được hỗ trợ trực tiếp |
| es-ES | vi-VN | Không hỗ trợ, dùng app default |
| null | vi-VN | Không có yêu cầu |
| chuỗi sai cú pháp | vi-VN hoặc lỗi input | Theo hợp đồng đã công bố |
| fr-CA | vi-VN | Theo chính sách exact matching trong ví dụ |
| fr | vi-VN | Không tự ghép về fr-FR trong chính sách exact |

Với cùng tập test, thay đổi **Locale.getDefault()** giữa **en-US**, **de-DE** và **tr-TR** không được thay selected. Đây là kiểm thử một **đặc tính của resolver**, không phải kiểm thử danh sách tiếng mà Java hỗ trợ.

### 11.2. Kiểm thử resource chain

Cần kiểm tra riêng:

- Bundle yêu cầu có mặt và khóa có mặt.
- Bundle mức vùng thiếu nhưng mức ngôn ngữ có.
- Bundle mức ngôn ngữ thiếu nhưng root có.
- Bundle cụ thể có mặt nhưng thiếu khóa, parent có khóa.
- Không có khóa trong bất kỳ parent nào: nhận **MissingResourceException** đúng chỗ hoặc lỗi ứng dụng đã định nghĩa.
- Một locale không có bundle, JVM default có bundle khác: **không** được đi sang bundle JVM nếu chính sách cấm.
- Mã nguồn chạy trên classpath/unnamed module hay named module có dùng đúng API provider/control được hỗ trợ không.

Không gắn kiểm thử phải “luôn trả tiếng Việt” vào mọi trường hợp khi resource root chứa ngôn ngữ khác, vì đó là hai hợp đồng độc lập. Nếu chính sách yêu cầu mọi khóa trong ngôn ngữ được chọn phải hoàn chỉnh, kiểm tra độ đầy đủ và không chỉ dựa vào parent fallback.

### 11.3. Không làm nhiễu bài kiểm thử song song

Một test có thể giả lập mặc định khác nhau bằng **Locale.setDefault** rồi khôi phục trong **finally**, nhưng default là trạng thái toàn JVM. Nếu test chạy song song, test A và B có thể can thiệp nhau, khiến phép thử thất bại ngẫu nhiên. Cách vững chắc là **chạy mỗi kịch bản trong JVM/process riêng**; hoặc giới hạn nhóm test được chạy tuần tự trong tiến trình cô lập.

Với chương trình đã biên dịch, có thể dùng các thuộc tính JVM khi khởi chạy chương trình chẩn đoán:

~~~bash
java -Duser.language=en -Duser.country=US LocaleFallbackDemo
java -Duser.language=de -Duser.country=DE LocaleFallbackDemo
~~~

Hai câu lệnh tạo hai tiến trình có mặc định khởi tạo theo các thuộc tính khác nhau. Demo **LocaleFallbackDemo** còn tự đặt hai default để in minh họa; trong kiểm thử production thực tế, nên dùng bộ kiểm thử/entry point không tự thay đổi default để phân biệt đúng ảnh hưởng của cấu hình khởi động.

### 11.4. Đối chiếu môi trường triển khai

Có hai tầng ổn định:

- **Không phụ thuộc default locale:** dùng locale và fallback cấu hình tường minh, không để JVM default tham gia quyết định.
- **Kết quả hiển thị có thể tái lập từng byte:** còn cần kiểm soát **phiên bản JDK, bộ dữ liệu CLDR, gói resource, timezone data** và các formatter liên quan.

Ngay cả khi hai máy đều dùng **vi-VN**, dữ liệu locale trong các bản JDK khác nhau vẫn có thể đổi ký hiệu, cách viết ngày hoặc dấu cách. Chính sách fallback xác định giải quyết **đường chọn bundle**, không khóa mọi dữ liệu localization của toàn runtime.

## 12. Phát hiện và xử lý lỗi thiếu bản dịch

**ResourceBundle.getString(key)** có thể ném **MissingResourceException** khi không tìm thấy khóa. Việc xử lý lỗi cũng phải có chính sách:

- Với **thông điệp bắt buộc** (thanh toán, cảnh báo an toàn, xác nhận pháp lý), nên kiểm tra khóa tồn tại và được phê duyệt từ build/deploy.
- Với **nội dung ít quan trọng** có thể cho phép fallback sang root; cần giám sát khóa thiếu để sớm bổ sung bản dịch.
- Nếu chọn hiển thị **[missing:key]** làm dấu hiệu trong môi trường dev, phải quyết định điều gì xảy ra trong production: placeholder có thể không phù hợp cho người dùng cuối.
- Không gửi toàn bộ stack trace hoặc đường dẫn resource lên giao diện để giải thích lỗi thiếu dịch; ghi nhận ở logs theo mức phù hợp.
- Cân nhắc cảnh báo khi bundle của selected locale không có và phải dùng root hoàn toàn, vì đó có thể là dấu hiệu hỏng gói triển khai.

Một kiểm thử tự động có thể kiểm tra **tập key** trong bản dịch và bộ gốc, cho phép một danh sách khóa được phép fallback có lý do. Điều này giúp chính sách trở thành một ràng buộc kiểm thử được, thay vì quy ước miệng.

Đối với file **.properties**, khóa trùng nhau trong cùng file không được phát hiện tự động như một lỗi biên dịch Java; quy trình kiểm tra tài nguyên nên phát hiện và cảnh báo bản dịch chồng lấp khi cần.

## 13. Những lỗi thiết kế thường gặp

### Lỗi 1 – Dùng overload mặc định của ResourceBundle

~~~java
ResourceBundle bundle = ResourceBundle.getBundle("messages");
~~~

Cùng một code nhưng JVM default khác nhau sẽ chọn bundle khác nhau. Khắc phục bằng **resolver ứng dụng**, truyền locale tường minh và kiểm soát fallback khi thiếu bundle.

### Lỗi 2 – Tưởng getBundle(baseName, locale) đã hết phụ thuộc môi trường

Truyền locale chỉ xác định đầu vào ban đầu; default **ResourceBundle.Control** vẫn có thể xét fallback về mặc định JVM trong một số trường hợp thiếu bundle. Khắc phục bằng **getNoFallbackControl** hoặc cơ chế resolver/provider đã được kiểm chứng đối với cách đóng gói đang dùng.

### Lỗi 3 – Không phân biệt khóa thiếu và locale không được hỗ trợ

Một locale có thể được ứng dụng hỗ trợ nhưng thiếu một vài khóa; một locale khác có thể hoàn toàn nằm ngoài phạm vi hỗ trợ. Hai lỗi này có nguyên nhân và phương án xử lý khác nhau. Không thể giải quyết cả hai chỉ bằng cách “đợi ResourceBundle tự fallback”.

### Lỗi 4 – Đặt default locale từ hệ điều hành

Nếu application default được gán ngầm từ **Locale.getDefault()**, CI và máy chủ có thể chọn bản dịch khác nhau. Khắc phục bằng cấu hình **application default** rõ ràng, validate thuộc supported list và dùng xuyên suốt.

### Lỗi 5 – Phụ thuộc thứ tự ngẫu nhiên của cấu trúc dữ liệu

Khi có nhiều locale cùng ngôn ngữ, một bộ chọn dùng “phần tử đầu tiên” của một **Set** không có quy tắc thứ tự có thể quyết định khác giữa những lần chạy. Nếu có fallback **fr-CA → fr-FR** hoặc **en → en-US**, đó phải là ánh xạ được công bố và kiểm thử, không phải quyết định ngẫu nhiên.

### Lỗi 6 – Cho phép fallback vô hạn hoặc im lặng

Các tầng như request locale → tenant locale → app default → bundle root → JVM default → placeholder có thể khiến lỗi bị che khuất. Hãy quyết định **điểm kết thúc**: một bundle rõ ràng, một giá trị mặc định đã chọn, hoặc một lỗi thiếu resource có thể giám sát.

### Lỗi 7 – Không kiểm tra resource trong CI

Mã chạy tốt khi bản dịch đủ, nhưng khi thêm locale mới thiếu key bắt buộc thì production mới phát sinh lỗi. Nên kiểm tra tập khóa theo phiên bản mã nguồn; có thể dùng bộ dịch gốc làm danh sách khóa chuẩn.

## 14. Danh sách kiểm tra khi thiết kế một chính sách dự phòng

Trước khi công bố một hệ thống bản địa hóa, hãy xác minh:

1. **Supported locales** được khai báo và tài nguyên tương ứng được kiểm tra.
2. **Application default** là một locale hợp lệ, được hỗ trợ, không phụ thuộc môi trường.
3. **Thứ tự ưu tiên** giữa lựa chọn người dùng, tài khoản, client và cấu hình tổ chức rõ ràng.
4. **Quy tắc mapping** giữa language/region/script được nêu rõ; không tự ghép bừa.
5. **Bundle base name**, kiểu resource và classpath/module packaging được xác nhận.
6. **Fallback theo JVM default** được chủ động cho phép hoặc bị vô hiệu hóa theo hợp đồng.
7. **Fallback theo key/parent** được định nghĩa, bao gồm ngôn ngữ của resource gốc.
8. **Lỗi khi thiếu khóa/bundle** có xử lý phù hợp và khả năng giám sát.
9. **Formatter khác** cũng nhận locale tường minh; không chỉ tập trung vào ResourceBundle.
10. **Test** bao phủ ít nhất hai JVM defaults, nhiều locale yêu cầu, khóa thiếu, bundle thiếu và cả trường hợp thiếu toàn bộ.
11. **CI** kiểm tra tài nguyên và phiên bản JDK/CLDR khi cần kết quả trình bày ổn định.
12. **Không đổi default JVM theo request**, tránh nhiễu giữa người dùng hoặc test chạy song song.

## 15. Kết luận

**Chuỗi dự phòng không phụ thuộc môi trường cần được định nghĩa ở cả tầng chọn locale và tầng tra cứu bản dịch.** Ứng dụng nên quyết định supported locales, application default, thứ tự ưu tiên, cách xử lý locale không hỗ trợ và hành vi khi thiếu key/bundle. Đối với classpath ResourceBundle, **ResourceBundle.Control.getNoFallbackControl(...)** giúp loại bỏ bước fallback sang locale mặc định JVM mà vẫn giữ candidate/parent chain có chủ đích.

Một resolver rõ ràng kết hợp với resource gốc được kiểm duyệt và kiểm thử hai môi trường default khác nhau giúp cùng một request nhận cùng lựa chọn bản dịch. Đó là nền tảng để bản địa hóa Java vận hành dự đoán được trên máy phát triển, CI và production.
