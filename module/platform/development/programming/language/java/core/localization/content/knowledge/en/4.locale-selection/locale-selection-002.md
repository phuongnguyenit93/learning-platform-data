# Thứ tự ưu tiên giữa lựa chọn người dùng và cấu hình mặc định khi chọn Locale

Một ứng dụng Java có thể nhận nhiều tín hiệu về ngôn ngữ và vùng: người dùng vừa chọn tiếng Việt trên giao diện, tài khoản lưu tiếng Anh, trình duyệt gửi **Accept-Language: fr-FR**, cấu hình hệ thống đặt **vi-VN**, còn JVM đang có locale **en-US**. Nếu chương trình tùy tiện dùng tín hiệu nào gặp trước, cùng một người dùng có thể thấy các màn hình bằng những ngôn ngữ khác nhau.

Bài học này xây dựng **chính sách thứ tự ưu tiên rõ ràng** để chọn **java.util.Locale** cho ứng dụng Java Core, giải thích cách xử lý ngôn ngữ không được hỗ trợ, fallback, và cách kiểm thử lựa chọn. Đề tài tập trung vào **quyết định chọn locale**; tra cứu bản dịch, định dạng số và ngày giờ chỉ là những bước tiêu thụ locale đã được quyết định.

## 1. Điều kiện tiên quyết: phải biết ứng dụng hỗ trợ locale nào

**Locale** mô tả ngôn ngữ và có thể gồm vùng, chữ viết, biến thể và các phần mở rộng. Ví dụ:

| Language tag | Ý nghĩa thường gặp |
| --- | --- |
| **vi-VN** | Tiếng Việt tại Việt Nam |
| **en-US** | Tiếng Anh theo quy ước Hoa Kỳ |
| **en-GB** | Tiếng Anh theo quy ước Vương quốc Anh |
| **fr-FR** | Tiếng Pháp tại Pháp |
| **zh-Hant-TW** | Tiếng Trung chữ Phồn thể tại Đài Loan |

Java tạo locale từ language tag theo BCP 47:

~~~java
import java.util.Locale;

public class LocaleBasics {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        System.out.println(locale.getLanguage());
        System.out.println(locale.getCountry());
        System.out.println(locale.toLanguageTag());
    }
}
~~~

Lưu thành **LocaleBasics.java**, sau đó chạy:

~~~bash
javac -encoding UTF-8 LocaleBasics.java
java LocaleBasics
~~~

Kết quả:

~~~text
vi
VN
vi-VN
~~~

**Tạo được một đối tượng Locale không có nghĩa ứng dụng hỗ trợ locale đó.** Java có thể hiểu tag **ja-JP** trong khi sản phẩm không hề có bản dịch tiếng Nhật. Ứng dụng cần một danh sách xác định, ví dụ **vi-VN**, **en-US**, **fr-FR**, kèm bản dịch và cách định dạng tương ứng. Danh sách đó là chuẩn đối chiếu cho mọi nguồn yêu cầu ngôn ngữ.

Cần phân biệt các khái niệm:

- **Requested locale:** người dùng hoặc phía gọi mong muốn.
- **Supported locale:** một locale có trong phạm vi ứng dụng cam kết hỗ trợ.
- **Resolved locale:** locale cuối cùng được chọn sau quy tắc ưu tiên và fallback.
- **Application default:** locale dự phòng do ứng dụng cấu hình rõ ràng; nên là một supported locale.
- **JVM default:** giá trị của **Locale.getDefault()**, phụ thuộc môi trường/chính sách chạy JVM và có thể thay đổi trong tiến trình.

Không coi locale và múi giờ là một. **vi-VN** không tự xác định múi giờ; ngày giờ vẫn phải sử dụng thông tin **ZoneId** riêng. Tương tự, giao diện tiếng Anh không chứng minh rằng người dùng thanh toán bằng USD.

## 2. Thứ tự ưu tiên phải là chính sách của ứng dụng

Java Core không tự đưa ra một thứ tự phổ quát giữa lựa chọn của người dùng, tùy chọn đã lưu, ngôn ngữ trình duyệt và cấu hình sản phẩm. **Locale.getDefault()** cũng không biết một người dùng vừa đổi ngôn ngữ trên giao diện hay đã lưu cấu hình tài khoản. Lập trình viên phải định nghĩa và thực thi chính sách đó.

Một **chính sách mẫu** phù hợp với ứng dụng đa người dùng:

1. **Lựa chọn tường minh trong request/phiên hiện tại:** người dùng vừa chọn ngôn ngữ trên giao diện hoặc truyền một tham số hợp lệ mà hệ thống cho phép.
2. **Tùy chọn được lưu của người dùng:** ngôn ngữ đã lưu trong hồ sơ hoặc cài đặt tài khoản.
3. **Ngôn ngữ do client đề nghị:** ví dụ header **Accept-Language** từ trình duyệt, được thương lượng với danh sách supported locales.
4. **Locale mặc định riêng của tenant/tổ chức:** nếu hệ thống đa tenant thực sự có thiết lập này.
5. **Locale mặc định của ứng dụng:** một supported locale được khai báo trong cấu hình triển khai.
6. **JVM default:** chỉ dùng như nguồn dự phòng **nếu sản phẩm chủ động lựa chọn và kiểm tra**; nhiều hệ thống sản xuất cố định application default thay vì ngầm dùng môi trường JVM.

Thứ tự trên là **quyết định sản phẩm có thể thay đổi**, không phải một chuẩn bắt buộc của Java. Ví dụ: hệ thống kiosk có thể ưu tiên cấu hình thiết bị hơn hồ sơ người dùng; hệ thống đa tenant có thể áp đặt danh sách supported locales khác nhau theo tenant. Tuy nhiên, ngay cả khi chính sách khác, thứ tự phải được viết rõ, nhất quán và kiểm thử được.

Điểm quan trọng là phân biệt **lựa chọn hợp lệ** với **sự tồn tại của một chuỗi yêu cầu**. Nếu một request ghi **xx-YY** nhưng ứng dụng không hỗ trợ ngôn ngữ đó, không thể trả về chính xác locale yêu cầu như một lời cam kết rằng giao diện đã được dịch. Ứng dụng cần chọn chính sách: thử matching theo ngôn ngữ, xét nguồn ưu tiên kế tiếp, dùng default hoặc thông báo để người dùng chọn lại.

## 3. Mô hình quyết định: từng tầng và điều kiện fallback

Có thể hình dung luồng đơn giản:

~~~text
Bắt đầu
  |
  v
Có lựa chọn tường minh hợp lệ và được hỗ trợ?
  | Có --> Dùng locale tương ứng
  | Không
  v
Có tùy chọn tài khoản được hỗ trợ?
  | Có --> Dùng locale tương ứng
  | Không
  v
Accept-Language có ứng viên được hỗ trợ?
  | Có --> Dùng ứng viên theo thương lượng
  | Không
  v
Có mặc định tenant hợp lệ? (nếu áp dụng)
  | Có --> Dùng mặc định tenant
  | Không
  v
Dùng application default đã xác minh
~~~

Ở mỗi tầng, chương trình phải trả lời hai câu hỏi độc lập: **nguồn này có được phép chi phối quyết định không?** và **giá trị của nguồn có thể ánh xạ sang một supported locale không?** Chuỗi rỗng, tag sai cú pháp, tag không hỗ trợ và nguồn vắng mặt phải được xử lý có chủ đích.

Bảng ví dụ với supported locales **vi-VN**, **en-US**, **fr-FR** và application default **vi-VN**:

| Lựa chọn hiện tại | Đã lưu | Accept-Language | Kết quả | Lý do |
| --- | --- | --- | --- | --- |
| **fr-FR** | en-US | vi-VN | **fr-FR** | Lựa chọn tường minh có ưu tiên cao nhất |
| Không có | **en-US** | fr-FR | **en-US** | Ưu tiên cấu hình tài khoản |
| Không có | Không có | **fr-FR, en-US;q=0.8** | **fr-FR** | Thương lượng ngôn ngữ client |
| Không có | Không có | Không có | **vi-VN** | Dùng application default |
| **es-ES** | en-US | fr-FR | **en-US** | Theo chính sách mẫu: lựa chọn không hỗ trợ được bỏ qua và xét nguồn tiếp |

Hàng cuối thể hiện chính sách mẫu chứ không phải hành vi mặc nhiên của Java. Với thao tác đổi ngôn ngữ trực tiếp, có thể hợp lý hơn khi **hiển thị lỗi “ngôn ngữ chưa được hỗ trợ”** thay vì âm thầm dùng tùy chọn cũ; còn khi hiển thị trang, quy tắc fallback vẫn giúp trang có nội dung. Nên tách phản hồi cho thao tác cập nhật cài đặt khỏi thuật toán chọn locale lúc đọc.

## 4. Thứ tự ưu tiên trong phạm vi một người dùng

### 4.1. Lựa chọn tường minh trong phiên hiện tại

Đây thường là tín hiệu thể hiện rõ nhất ý định mới nhất. Ví dụ người dùng đang có hồ sơ **en-US**, nhưng nhấp chuyển giao diện sang **vi-VN**. Nếu request hiện tại mang lựa chọn **vi-VN**, màn hình tiếp theo nên dùng **vi-VN** theo chính sách mẫu, ngay cả khi hồ sơ chưa kịp được cập nhật.

Không nên truyền giá trị thô trực tiếp vào formatter mà chưa kiểm tra. Chỉ nhận các locale thuộc danh sách hỗ trợ, hoặc áp dụng quy tắc matching được mô tả cụ thể. Một tham số như **?lang=vi-VN** là dữ liệu do phía gọi cung cấp; nó không phải căn cứ để quyết định quyền truy cập hay phân quyền.

### 4.2. Tùy chọn đã lưu trong hồ sơ

Nếu request không nêu lựa chọn mới, ứng dụng lấy giá trị đã lưu của người dùng. Điều này giữ trải nghiệm nhất quán khi họ đăng nhập từ thiết bị khác. Khi người dùng lưu thay đổi ngôn ngữ, cần xác định thời điểm hồ sơ được cập nhật và cache/session nào phải vô hiệu hóa để tránh tình trạng giao diện vẫn dùng lựa chọn cũ.

Với người dùng chưa đăng nhập, có thể lưu lựa chọn ngôn ngữ trong cookie/session. Thứ tự giữa cookie và Accept-Language cũng phải được công bố trong chính sách. Đối với tài khoản đã đăng nhập, nếu cookie cũ khác hồ sơ, cần quyết định rõ tín hiệu nào thắng; không để thứ tự đọc dữ liệu ngẫu nhiên quyết định.

### 4.3. Khi không có quyết định từ người dùng

Trình duyệt thường gửi **Accept-Language**, ví dụ:

~~~http
Accept-Language: fr-CA, fr;q=0.9, en-US;q=0.7
~~~

Header này là **danh sách ưu tiên**, không phải một language tag duy nhất. **q** là trọng số chất lượng trong khoảng 0 đến 1; nếu không ghi q thì thông thường được hiểu bằng 1.0. **fr-CA** có thể không thuộc supported locales, nhưng **fr** có thể khớp với một locale tiếng Pháp mà ứng dụng cung cấp.

Không nên xử lý bằng cách lấy chuỗi trước dấu phẩy rồi gọi **Locale.forLanguageTag(...)**: cách làm đó bỏ qua ứng viên tiếp theo, trọng số q và các quy tắc thương lượng. Java Core có **Locale.LanguageRange.parse(...)**, **Locale.filter(...)** và **Locale.lookup(...)** cho những tình huống này.

Một số request không có Accept-Language, ví dụ job nền, API client hoặc request kiểm thử. Khi đó chương trình chuyển tiếp về cấu hình hệ thống thay vì suy đoán ngôn ngữ từ địa chỉ IP.

## 5. Matching: yêu cầu “en”, “en-GB” hay “fr-CA” nên được xử lý thế nào?

Chỉ cho phép so khớp chính xác có thể quá nghiêm: người dùng yêu cầu **en** trong khi ứng dụng hỗ trợ **en-US**. Nhưng cho phép khớp theo ngôn ngữ một cách tùy tiện cũng có thể gây lỗi: **zh-Hant** và **zh-Hans** dùng hệ chữ viết khác nhau; **pt-BR** và **pt-PT** có khác biệt từ vựng và quy ước hiển thị.

Có ba cách thường gặp:

| Cách matching | Đặc điểm | Khi thích hợp |
| --- | --- | --- |
| **Exact** | Chỉ chấp nhận locale đúng với một phần tử supported | Sản phẩm cần lựa chọn rất cụ thể |
| **Language fallback có kiểm soát** | Nếu không exact, dùng cùng ngôn ngữ khi không nhập nhằng và chữ viết tương thích | Sản phẩm có một bản dịch cho mỗi ngôn ngữ |
| **Negotiation theo language ranges** | Phân tích danh sách ưu tiên có q, chọn kết quả phù hợp từ supported locales | Xử lý Accept-Language và yêu cầu nhiều ứng viên |

Với **Locale.forLanguageTag(...)**, hãy nhớ API có thể trả một locale với phần đầu vào bị xử lý lenient nếu tag không đúng cú pháp. Khi cần phân biệt dữ liệu nhập sai, dùng **new Locale.Builder().setLanguageTag(tag)** và bắt **IllformedLocaleException**. Sau khi parse vẫn phải kiểm tra ngôn ngữ không rỗng, danh sách hỗ trợ và chính sách matching. Không tin rằng một tag đúng cú pháp thì bản dịch, tiền tệ, múi giờ hoặc các ký hiệu cần thiết đã tồn tại trong ứng dụng.

Nếu supported locales chứa cả **en-US** và **en-GB**, yêu cầu chỉ có **en** không đủ để chọn một trong hai theo quy tắc “chỉ duy nhất một locale cùng ngôn ngữ”. Khi đó có thể dùng preferred variant từ cấu hình sản phẩm, một thứ tự được công bố, hoặc yêu cầu người dùng chọn vùng. Không nên chọn ngẫu nhiên phần tử đầu tiên của một tập không có thứ tự ổn định.

## 6. Java 17+: ví dụ đầy đủ tự quyết định thứ tự ưu tiên

Ví dụ dưới đây là **chính sách cụ thể**, không giả định Java tự có chính sách này:

- Supported locales: **vi-VN**, **en-US**, **fr-FR**.
- Lựa chọn tường minh hợp lệ đứng trước giá trị đã lưu.
- Mỗi lựa chọn đơn lẻ ưu tiên exact match, sau đó thử khớp cùng ngôn ngữ nếu chỉ có **một** supported locale cùng ngôn ngữ và không xung đột chữ viết.
- Header Accept-Language được xử lý theo trọng số bằng API Java Core.
- Nếu mọi nguồn đều vắng mặt hoặc không phù hợp, dùng **vi-VN** cấu hình sẵn.
- Không đọc hoặc thay đổi **Locale.setDefault(...)** trong thuật toán này.

**File LocalePriorityDemo.java**

~~~java
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;

public class LocalePriorityDemo {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("fr-FR"));

    private static final Locale APP_DEFAULT =
            Locale.forLanguageTag("vi-VN");

    public static void main(String[] args) {
        show("1. Chọn trực tiếp",
                resolve("fr-FR", "en-US", "vi-VN"));
        show("2. Không hỗ trợ ở tầng đầu",
                resolve("es-ES", "en-US", "fr-FR"));
        show("3. Dùng header",
                resolve(null, null, "fr-CA, fr;q=0.9"));
        show("4. Trọng số header",
                resolve(null, null, "en-US;q=0.6, vi-VN;q=0.9"));
        show("5. Dùng mặc định",
                resolve(null, null, null));
        show("6. Khớp ngôn ngữ",
                resolve("en", null, null));
    }

    private static void show(String scenario, Locale locale) {
        System.out.println(scenario + ": " + locale.toLanguageTag());
    }

    // Thứ tự ưu tiên là chính sách của ứng dụng.
    static Locale resolve(
            String explicitChoice,
            String savedPreference,
            String acceptLanguageHeader) {

        Locale candidate = matchSingleTag(explicitChoice);
        if (candidate != null) {
            return candidate;
        }

        candidate = matchSingleTag(savedPreference);
        if (candidate != null) {
            return candidate;
        }

        candidate = matchHeader(acceptLanguageHeader);
        if (candidate != null) {
            return candidate;
        }

        return APP_DEFAULT;
    }

    private static Locale matchSingleTag(String rawTag) {
        if (rawTag == null || rawTag.isBlank()) {
            return null;
        }

        final Locale requested;
        try {
            requested = new Locale.Builder()
                    .setLanguageTag(rawTag.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            return null;
        }

        if (requested.getLanguage().isEmpty()) {
            return null;
        }

        // Exact match được ưu tiên.
        for (Locale supported : SUPPORTED) {
            if (supported.equals(requested)) {
                return supported;
            }
        }

        // Cho phép cùng ngôn ngữ/chữ viết nếu duy nhất một ứng viên.
        Locale unique = null;
        for (Locale supported : SUPPORTED) {
            if (!supported.getLanguage()
                    .equals(requested.getLanguage())) {
                continue;
            }

            if (!requested.getScript().isEmpty()
                    && !requested.getScript()
                            .equals(supported.getScript())) {
                continue;
            }

            if (unique != null) {
                // Không tự chọn giữa hai vùng có cùng ngôn ngữ.
                return null;
            }
            unique = supported;
        }
        return unique;
    }

    private static Locale matchHeader(String header) {
        if (header == null || header.isBlank()) {
            return null;
        }

        try {
            List<Locale.LanguageRange> preferences =
                    Locale.LanguageRange.parse(header);
            List<Locale> matches =
                    Locale.filter(preferences, SUPPORTED);
            return matches.isEmpty() ? null : matches.get(0);
        } catch (IllegalArgumentException ex) {
            // Header sai cấu trúc: thử nguồn ưu tiên thấp hơn.
            return null;
        }
    }
}
~~~

Lưu đúng tên **LocalePriorityDemo.java**. Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 LocalePriorityDemo.java
java LocalePriorityDemo
~~~

Stdout kỳ vọng:

~~~text
1. Chọn trực tiếp: fr-FR
2. Không hỗ trợ ở tầng đầu: en-US
3. Dùng header: fr-FR
4. Trọng số header: vi-VN
5. Dùng mặc định: vi-VN
6. Khớp ngôn ngữ: en-US
~~~

**Giải thích từng tình huống:**

1. **fr-FR** là yêu cầu trực tiếp thuộc danh sách hỗ trợ nên chiến thắng **en-US** đã lưu và **vi-VN** từ client.
2. **es-ES** không được ứng dụng hỗ trợ; theo chính sách ví dụ, nó được bỏ qua và **en-US** từ hồ sơ chiến thắng **fr-FR** ở header.
3. Không có lựa chọn trực tiếp/hồ sơ; header ưu tiên **fr-CA** rồi **fr**. Vì danh sách hỗ trợ có **fr-FR**, range **fr** khớp và kết quả là **fr-FR**.
4. **vi-VN** có trọng số 0.9, cao hơn **en-US** với 0.6 nên kết quả thương lượng là **vi-VN**.
5. Không có dữ liệu đầu vào hợp lệ thì trả **APP_DEFAULT**, không phụ thuộc ngôn ngữ máy chạy.
6. Yêu cầu **en** được ánh xạ sang **en-US** vì danh sách hiện tại chỉ có một locale tiếng Anh và không có xung đột chữ viết.

**Giới hạn có chủ đích của ví dụ:** không triển khai tenant default, lưu hồ sơ, cookie hay giao diện thông báo lỗi, vì đó là các tầng tích hợp ngoài chức năng chọn locale thuần Java. Khi có tenant default, chèn một bước kiểm tra sau việc thương lượng header và trước **APP_DEFAULT**. Nếu chính sách sản phẩm đòi exact matching, bỏ nhánh chọn duy nhất theo ngôn ngữ.

### 6.1. Vì sao dùng Locale.filter thay vì tự tách header?

**Locale.LanguageRange.parse(header)** đọc danh sách ngôn ngữ và các trọng số. **Locale.filter(preferences, SUPPORTED)** tìm các supported locales phù hợp với các language ranges. Cách này tránh lối viết sai:

~~~java
// Không nên dùng để xử lý toàn bộ Accept-Language:
Locale requested = Locale.forLanguageTag(
        "fr-CA, fr;q=0.9".split(",")[0]);
~~~

Đoạn trên chỉ lấy **fr-CA** và đánh mất ứng viên **fr**. **Locale.lookup(...)** là một API khác để tìm một kết quả phù hợp nhất theo quy tắc lookup; kết quả và chiến lược so khớp có thể khác filtering. Hãy chọn một cơ chế rõ ràng, kiểm thử các trường hợp region/script và thống nhất với chính sách sản phẩm.

Ví dụ sử dụng **Locale.filter** cho danh sách hỗ trợ có một locale mỗi ngôn ngữ. Với một sản phẩm có nhiều biến thể cùng ngôn ngữ hoặc chính sách fallback vùng phức tạp, phải thiết kế thêm cách phân giải trường hợp không khớp/nhập nhằng.

### 6.2. Đầu vào sai và ngoại lệ

**IllformedLocaleException** được bắt tại bước parse yêu cầu đơn lẻ; **IllegalArgumentException** được bắt khi parse header thương lượng. Đầu vào không hỗ trợ không làm chương trình lỗi: nó trả **null** từ hàm match để thử nguồn kế tiếp. Tuy vậy, ứng dụng thực tế nên phân biệt lý do **missing**, **malformed** và **unsupported** để thông báo phù hợp và theo dõi cấu hình, thay vì chỉ ghi “locale null”.

Nếu người dùng vừa yêu cầu chuyển sang một locale không hỗ trợ, service cập nhật sở thích nên phản hồi lỗi xác thực rõ ràng và không lưu lựa chọn sai. Trong đường đọc trang, một fallback có định nghĩa trước giúp tránh trả một giao diện trống.

## 7. Phân biệt application default và JVM default

### 7.1. Giá trị mặc định của JVM

Java cung cấp:

~~~java
Locale systemDefault = Locale.getDefault();
Locale formatDefault =
        Locale.getDefault(Locale.Category.FORMAT);
Locale displayDefault =
        Locale.getDefault(Locale.Category.DISPLAY);
~~~

Đây là đoạn minh họa cần import **java.util.Locale**. **getDefault()** trả locale mặc định chung; hai category phân biệt ngữ cảnh định dạng dữ liệu và hiển thị tên địa phương/ngôn ngữ. JVM default có thể bắt nguồn từ hệ điều hành hoặc cấu hình chạy JVM, ví dụ một số thuộc tính **user.language**, **user.country**. Các mặc định đó có thể khác nhau giữa máy phát triển, CI, container và máy chủ.

Ví dụ chương trình chỉ dùng **NumberFormat.getInstance()** hoặc **DateTimeFormatter** mà không có locale rõ ràng có thể tạo output khác nhau theo môi trường. Nếu nghiệp vụ cần tính xác định, hãy truyền resolved locale tường minh cho các API tiêu thụ ngôn ngữ/vùng.

### 7.2. Vì sao không dùng Locale.setDefault cho từng request?

**Locale.setDefault(locale)** thay đổi trạng thái dùng chung trong JVM. Nó không phải một biến theo thread hay một bộ nhớ riêng cho từng người dùng. Trong máy chủ có hai request chạy đồng thời:

~~~text
Request A (vi-VN): gọi Locale.setDefault(vi-VN)
Request B (en-US): gọi Locale.setDefault(en-US)
Request A: gọi NumberFormat.getInstance() không truyền locale
Kết quả A có thể theo en-US do B vừa thay đổi JVM default
~~~

Đây là mô tả race condition, không phải một lịch chạy cố định. Dù mỗi request cố khôi phục locale cũ sau khi xử lý, sự đan xen giữa các request vẫn có thể làm kết quả sai. Chính sách an toàn hơn là **resolve locale thành một giá trị** rồi truyền giá trị đó qua các hàm cần dùng.

~~~java
Locale selected = Locale.forLanguageTag("vi-VN");
NumberFormat formatter = NumberFormat.getNumberInstance(selected);
~~~

Đoạn trên cần import **java.util.Locale** và **java.text.NumberFormat**. **formatter** được cấu hình cho locale cụ thể, không phụ thuộc vào việc request khác đổi cài đặt. Bản thân **NumberFormat** có trạng thái mutable, nên không mặc định dùng chung cùng một instance giữa nhiều luồng.

### 7.3. Khi nào xem JVM default là một nguồn ưu tiên?

Với ứng dụng desktop phục vụ một người dùng, dựa vào locale hệ điều hành khi lần đầu khởi động có thể hợp lý. Nhưng ngay khi người dùng chọn ngôn ngữ khác, giá trị đã chọn cần được áp dụng đúng chính sách.

Với dịch vụ web, API và job định kỳ, application default thường nên là cấu hình rõ ràng. Nếu tổ chức có quy tắc **“app config → JVM default → fallback cố định”**, hãy lọc mọi candidate theo supported locales và luôn kết thúc bằng một locale hợp lệ; đừng tin rằng **Locale.getDefault()** luôn nằm trong danh sách bản dịch sản phẩm.

## 8. Các tầng mặc định khác: tenant, ứng dụng và môi trường

Trong sản phẩm đa tenant, một tenant có thể mặc định **fr-FR**, trong khi application default toàn hệ thống là **vi-VN**. Nếu người dùng không có lựa chọn riêng và header không tìm được locale hỗ trợ của tenant, quy tắc có thể rơi về mặc định tenant. Tuy nhiên, **supported locales** cũng có thể phụ thuộc tenant; khi đó phải đối chiếu mọi yêu cầu với danh sách đã được xác minh cho tenant hiện tại trước khi quyết định.

Một cách triển khai rõ ràng là cấu hình dạng khái niệm:

~~~yaml
localization:
  supported-locales:
    - vi-VN
    - en-US
    - fr-FR
  default-locale: vi-VN
~~~

Đây chỉ là **ví dụ định dạng cấu hình**, không phải tính năng tự nạp của Java Core. Mã khởi tạo cần đọc cấu hình bằng cơ chế ứng dụng đang dùng, kiểm tra language tags hợp lệ và xác minh default nằm trong supported list. Nếu điều kiện này sai, nên báo lỗi cấu hình khi khởi động thay vì để request bất kỳ chọn được locale không có resource.

Khi có nhiều tầng cấu hình, cũng cần phân biệt **cấu hình được nạp sau ghi đè cấu hình trước** với **locale ưu tiên khi xử lý request**. Hai cơ chế có thể liên quan nhưng không đồng nhất. Ví dụ application default được chọn từ biến môi trường lúc khởi động, sau đó tại request vẫn phải nhường cho lựa chọn trực tiếp của người dùng.

## 9. Sau khi resolve: dùng locale nhất quán với ResourceBundle và formatter

Thuật toán chọn locale chỉ đưa ra một đối tượng **Locale**. Các tầng sau phải cùng tiêu thụ giá trị này:

~~~java
Locale resolved = Locale.forLanguageTag("vi-VN");

ResourceBundle messages =
        ResourceBundle.getBundle("messages", resolved);
String greeting = messages.getString("greeting");

NumberFormat numbers =
        NumberFormat.getNumberInstance(resolved);

DateTimeFormatter dates =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(resolved);
~~~

Đoạn minh họa cần import **java.util.Locale**, **java.util.ResourceBundle**, **java.text.NumberFormat**, **java.time.format.DateTimeFormatter** và **java.time.format.FormatStyle**; cần có resource bundle **messages** trên classpath. Ví dụ chỉ cho thấy cách truyền cùng resolved locale, không phải chương trình độc lập.

### 9.1. Hai lớp fallback phải được tách bạch

**Lớp 1 – lựa chọn locale của ứng dụng:** thuật toán quyết định **fr-FR** hay **vi-VN** theo người dùng, header, danh sách hỗ trợ và default.

**Lớp 2 – tìm resource trong ResourceBundle:** sau khi nhận locale **fr-FR**, cơ chế tra cứu có thể thử bundle cụ thể, bundle ngôn ngữ, bundle gốc, và trong một số trường hợp còn dùng JVM default khi tìm bundle. Điều này có thể dẫn đến tình huống **resolvedLocale = fr-FR** nhưng một thông điệp lại xuất phát từ resource của locale khác do fallback mặc định của API.

Nếu ứng dụng cần chính sách fallback resource độc lập với JVM default, với resource bundles dạng classpath truyền thống có thể kiểm soát bằng **ResourceBundle.Control**:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages",
        resolved,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES));
~~~

Đoạn trên không độc lập, cần import **java.util.ResourceBundle**, biến **resolved** và resource trên classpath. **getNoFallbackControl** ngăn bước fallback theo locale mặc định của JVM; quy tắc tra cứu bundle của candidate và bundle gốc vẫn còn. **ResourceBundle.Control** có những hạn chế khi dùng named modules: không giả định overload nhận Control hoạt động như nhau trong mọi kiểu module; với named modules cần áp dụng cơ chế resource/provider được hỗ trợ và kiểm thử fallback thực tế.

**Nguyên tắc thực dụng:** resolved locale, bản dịch thực tế được chọn và nội dung hiển thị nên có quy ước nhất quán. Nếu app ưu tiên **vi-VN** nhưng thiếu một khóa tiếng Việt, cần có chính sách rõ về fallback sang ngôn ngữ gốc, cảnh báo thiếu khóa và QA bản dịch. Locale đúng không tự bảo đảm từng message key đã được dịch.

### 9.2. Locale không thay thế các lựa chọn nghiệp vụ khác

- **Múi giờ:** lấy từ người dùng, tổ chức hoặc quy tắc nghiệp vụ, ví dụ **ZoneId.of("Asia/Ho_Chi_Minh")**; không suy từ locale.
- **Tiền tệ:** mã tiền dùng trong giao dịch phải đến từ nghiệp vụ; không tự suy nó từ ngôn ngữ giao diện.
- **Định dạng dữ liệu cho API:** dùng format hợp đồng xác định như ISO cho dữ liệu trao đổi, còn locale chủ yếu phục vụ hiển thị/nhập từ con người.
- **Quyền truy cập:** locale/header/cookie không phải chứng cứ danh tính hay quyền của người dùng.

## 10. Lựa chọn người dùng, cache và tính nhất quán xuyên request

Trong dịch vụ web, locale đã resolve có thể đi cùng **request context**, session hoặc một đối tượng truyền qua các tầng xử lý. Không cần thay đổi biến global của JVM để truyền ngữ cảnh. Nếu dùng thread pool hoặc tác vụ bất đồng bộ, không giả định một biến **ThreadLocal** luôn tự chuyển sang thread xử lý tiếp theo; phải truyền hoặc thiết lập/dọn dẹp context rõ ràng theo kiến trúc.

Khi cache nội dung đã dịch, **locale thường phải là một phần của cache key**. Ví dụ:

~~~text
Sai:  cache["welcome"] = "Xin chào"
Đúng: cache[("welcome", "vi-VN")] = "Xin chào"
      cache[("welcome", "en-US")] = "Hello"
~~~

Nếu ứng dụng dùng locale theo tenant hoặc phiên bản bản dịch, các yếu tố đó cũng có thể cần nằm trong cache key. Nếu không, request tiếng Anh có thể nhận bản dịch tiếng Việt do cache key quá chung.

Một user đổi lựa chọn từ **en-US** sang **vi-VN** cần thấy hiệu lực ở phạm vi đã cam kết: ngay lập tức trên request hiện tại, từ request tiếp theo sau khi lưu, hay sau khi tải lại trang. Xác định rõ thời điểm cập nhật profile, session và cache; tránh để UI nói “đã đổi ngôn ngữ” nhưng các phần sau vẫn lấy locale cũ.

## 11. Kiểm thử thứ tự ưu tiên như một hợp đồng

Một resolver có giá trị khi hành vi được kiểm thử bằng bảng trường hợp. Không chỉ kiểm thử ngôn ngữ “happy path”. Với chính sách ở phần 6, các ca tối thiểu gồm:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Explicit, saved và header đều hợp lệ nhưng khác nhau | Explicit thắng |
| Explicit rỗng, saved và header khác nhau | Saved thắng |
| Explicit không hỗ trợ, saved hợp lệ | Saved được chọn theo chính sách mẫu |
| Hai tầng đầu vắng mặt, header có q | Dùng ứng viên có độ ưu tiên thương lượng phù hợp |
| Header sai cú pháp | Không làm hỏng request; chuyển sang default |
| Không có nguồn nào | Application default |
| Explicit chỉ có **en**, chỉ hỗ trợ **en-US** | Ánh xạ thành **en-US** nếu cho phép language fallback |
| Hỗ trợ **en-US** và **en-GB**, request chỉ có **en** | Không tự chọn vùng trong quy tắc unique-language |
| Tag cùng ngôn ngữ nhưng khác script | Không tự đồng nhất hai hệ chữ viết |
| JVM default đổi sang locale khác | Resolver vẫn cho cùng kết quả với cùng đầu vào và cấu hình |

Nên kiểm thử thêm các chuỗi chứa khoảng trắng, tag viết sai, danh sách hỗ trợ rỗng, cấu hình default không nằm trong supported list, cookie cũ, tài khoản chưa đăng nhập và đổi ngôn ngữ đồng thời trên nhiều thiết bị.

Khi cần kiểm thử xem hành vi có bất biến theo môi trường, hãy đặt một JVM default khác trong **một bài kiểm thử cô lập**, rồi xác minh resolver trả cùng giá trị cho các đầu vào giống nhau. Không thực hiện **Locale.setDefault** tùy tiện giữa những bài kiểm thử chạy song song vì sẽ gây nhiễu toàn tiến trình.

Phân biệt **kiểm thử resolver** với **kiểm thử đầu ra định dạng**: resolver có thể được kiểm thử bằng **toLanguageTag()** chính xác; dấu phân cách số/tên tháng có thể chịu ảnh hưởng dữ liệu locale/CLDR của JDK, nên muốn so khớp từng byte phải kiểm soát phiên bản runtime và dữ liệu.

## 12. Các lỗi phổ biến và cách khắc phục

### Lỗi 1: Luôn dùng Locale.getDefault()

Triệu chứng: trên laptop lập trình viên giao diện là tiếng Việt; trên máy chủ hoặc CI lại là tiếng Anh. Nguyên nhân: không có application default rõ ràng, hoặc formatter lấy locale môi trường. Khắc phục: cấu hình supported/default, giải quyết theo từng request và truyền resolved locale tường minh.

### Lỗi 2: Header ghi đè lựa chọn đã lưu

Triệu chứng: user đã đặt tiếng Pháp, nhưng khi mở từ trình duyệt có **Accept-Language: en-US** thì giao diện trở lại tiếng Anh. Nguyên nhân: middleware đọc header trước hồ sơ dù chính sách nói hồ sơ có ưu tiên cao hơn. Khắc phục: thống nhất đúng thứ tự xử lý trong một resolver tập trung.

### Lỗi 3: Dùng Locale.forLanguageTag mà không kiểm tra hỗ trợ

Triệu chứng: ứng dụng nhận tag **ko-KR**, nhưng chưa có bản dịch Hàn; màn hình xuất hiện hỗn hợp tiếng Anh/tiếng Việt. Nguyên nhân: nhầm cú pháp locale hợp lệ với khả năng hỗ trợ của sản phẩm. Khắc phục: xác minh danh sách supported và chính sách fallback; kiểm tra độ đầy đủ của resource bundle.

### Lỗi 4: Chỉ lấy giá trị đầu tiên của Accept-Language

Triệu chứng: client gửi **fr-CA, fr;q=0.9, en-US;q=0.7**, trong khi ứng dụng chỉ hỗ trợ **fr-FR** và **en-US**; thuật toán thủ công có thể bỏ lỡ **fr-FR**. Khắc phục: dùng API thương lượng **Locale.LanguageRange** và một quy tắc matching được kiểm thử.

### Lỗi 5: Đổi ngôn ngữ bằng Locale.setDefault

Triệu chứng: request người dùng này thay đổi cách hiển thị của người khác. Nguyên nhân: locale mặc định là trạng thái chung của JVM. Khắc phục: giữ locale tại request/user context, tạo formatter theo locale.

### Lỗi 6: Fallback không rõ ràng hoặc khác nhau giữa màn hình

Triệu chứng: trang sản phẩm fallback về **vi-VN**, trang thanh toán fallback về **en-US**; một số chuỗi còn rơi về resource của JVM default. Nguyên nhân: nhiều thành phần tự chọn locale và tra bundle riêng. Khắc phục: tập trung chính sách resolve, tài liệu hóa fallback cho resource và kiểm thử toàn bộ luồng hiển thị.

### Lỗi 7: Trộn ngôn ngữ, vùng, múi giờ và tiền tệ

Triệu chứng: người dùng đổi UI sang tiếng Anh khiến thời gian hiển thị thành giờ Hoa Kỳ hoặc hóa đơn chuyển ký hiệu tiền. Nguyên nhân: coi locale là toàn bộ cài đặt địa phương. Khắc phục: quản lý riêng locale giao diện, time zone, currency và quy tắc giao dịch.

## 13. Mẫu thiết kế dễ bảo trì

Trong ứng dụng có nhiều luồng sử dụng locale, một thành phần chịu trách nhiệm **resolve** nên nhận dữ liệu đã kiểm tra quyền truy cập và được truyền các nguồn ưu tiên như tham số. Ví dụ chữ ký thiết kế:

~~~java
Locale resolveLocale(
        String explicitChoice,
        String savedPreference,
        String acceptLanguageHeader,
        Locale tenantDefault,
        Locale applicationDefault);
~~~

Đây là chữ ký minh họa, không phải đoạn code độc lập. Có thể chuyển các tham số thành một kiểu dữ liệu **LocalePreferenceContext** rõ ràng nếu ứng dụng có nhiều nguồn. Phần kiểm tra hỗ trợ và thuật toán matching nên tập trung; những phần hiển thị khác chỉ tiêu thụ **resolvedLocale**.

Một contract tốt ghi rõ:

1. **Nguồn đầu vào:** request, cookie/session, hồ sơ người dùng, header, tenant và app config.
2. **Thứ tự ưu tiên:** áp dụng chính xác khi các nguồn mâu thuẫn.
3. **Supported locales:** nguồn cấu hình duy nhất hoặc chính sách phạm vi tenant.
4. **Matching:** exact, language fallback, script/region handling, Accept-Language q.
5. **Hành vi với giá trị không hợp lệ:** fallback hoặc lỗi phản hồi cho thao tác cập nhật.
6. **Kết quả:** một supported locale xác định, có thể ghi log lý do chọn.
7. **Tác động hệ thống:** truyền locale tường minh, cache đúng ngữ cảnh, không thay JVM default theo request.

Nếu cần hỗ trợ người dùng tự đổi ngôn ngữ trên UI, hành động thay đổi nên vừa **lưu preference** theo nguyện vọng của người dùng, vừa đảm bảo **request hiện tại** sử dụng lựa chọn vừa được xác nhận. Tránh có hai cơ chế cạnh tranh nhau khi trang tải lại.

## 14. Tổng kết

**Ưu tiên lựa chọn người dùng so với cấu hình mặc định là một chính sách ứng dụng, không phải thứ tự tự động do java.util.Locale quyết định.** Với hệ thống đa người dùng, thiết kế phổ biến là **lựa chọn trực tiếp → tùy chọn đã lưu → thương lượng từ client → mặc định tenant (nếu có) → mặc định ứng dụng**. Mọi ứng viên phải được đối chiếu với danh sách supported locales và quy tắc matching được công bố; JVM default chỉ được dùng nếu chính sách thực sự yêu cầu.

Hãy giữ một nơi duy nhất quyết định locale, truyền kết quả tường minh sang ResourceBundle và các formatter, tránh **Locale.setDefault** theo request, đồng thời kiểm thử những trường hợp mâu thuẫn và fallback. Nhờ vậy người dùng nhận đúng ngôn ngữ mình đã chọn, và ứng dụng hoạt động ổn định dù chạy trên máy khác, trình duyệt khác hoặc nhiều request đồng thời.
