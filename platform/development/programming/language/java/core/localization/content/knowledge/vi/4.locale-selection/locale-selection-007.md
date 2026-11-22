# Xử lý không có locale khớp bằng chính sách tường minh trong Java

Một hệ thống có thể nhận yêu cầu hiển thị bằng `ja-JP`, `fr-CA` hoặc `vi-VN`, trong khi thực tế chỉ có bản dịch và cấu hình định dạng cho `vi-VN`, `en-US`, `fr-FR`. Sau khi thương lượng ngôn ngữ, câu hỏi quan trọng là: **nếu không tìm được locale phù hợp, ứng dụng phải làm gì?**

Không nên để kết quả tùy thuộc ngẫu nhiên vào locale mặc định của JVM, thứ tự dữ liệu, hoặc hành vi fallback ẩn của một thư viện. Cần định nghĩa **chính sách không khớp (no-match policy)**, áp dụng nhất quán và kiểm thử được.

Bài học nằm trong chủ đề **Chọn locale** và tập trung vào xử lý tình huống không có kết quả khớp. Phần chọn thứ tự ưu tiên ngôn ngữ chỉ được nhắc đủ để hiểu điểm phát sinh no-match.

## 1. “Không có locale khớp” nghĩa là gì?

Một quy trình lựa chọn locale có ba đầu vào cơ bản:

1. **Yêu cầu của người dùng hoặc client:** locale được chọn trong hồ sơ, tham số API, hoặc danh sách sở thích `Accept-Language`.
2. **Danh sách locale được ứng dụng thực sự hỗ trợ:** chẳng hạn `[vi-VN, en-US, fr-FR]`.
3. **Thuật toán lựa chọn:** có thể là đối chiếu chính xác, `Locale.lookup`, một bộ luật fallback tùy chỉnh, hoặc bộ thương lượng của framework.

**Không khớp** nghĩa là thuật toán đã áp dụng lên dữ liệu hợp lệ và **không tìm thấy ứng viên nào đạt tiêu chí**. Đây khác với việc yêu cầu không được gửi, cú pháp đầu vào sai, hoặc kho tài nguyên dịch thuật bị thiếu.

| Tình huống | Ví dụ | Cách hiểu | Phản ứng cần quy định |
| --- | --- | --- | --- |
| Không cung cấp sở thích | Không có `Accept-Language`, chưa chọn ngôn ngữ | Thiếu input, không phải match thất bại | Dùng mặc định hoặc yêu cầu chọn |
| Không có ứng viên hỗ trợ | Chỉ hỗ trợ `vi-VN`, `en-US`; client yêu cầu `ja-JP` | Không khớp | Fallback, yêu cầu chọn lại hoặc từ chối |
| Cú pháp input không hợp lệ | Header `en_US` trong bộ phân tích language ranges | Input lỗi | Trả lỗi rõ ràng hoặc áp chính sách dữ liệu hỏng riêng |
| Có match nhưng thiếu bản dịch | Đã chọn `fr-FR` nhưng thiếu một message key | Lỗi tài nguyên, không phải lỗi match | Fallback tài nguyên/khắc phục bản dịch theo quy định |
| Cấu hình ứng dụng hỏng | Default `en-US` không nằm trong danh sách hỗ trợ | Lỗi vận hành | Báo lỗi cấu hình, không âm thầm tiếp tục |
| Thẻ có syntax hợp lệ nhưng locale chưa hỗ trợ | `de-DE` được parser nhận, ứng dụng không có bản dịch | Hợp lệ về cú pháp, chưa được hỗ trợ | Áp dụng no-match policy |

Sự phân biệt này quan trọng khi theo dõi lỗi, trả trạng thái HTTP và giải thích cho người dùng vì sao giao diện xuất hiện bằng ngôn ngữ khác.

## 2. Bắt đầu bằng danh sách locale được hỗ trợ rõ ràng

Ví dụ một ứng dụng chỉ có ba ngôn ngữ/vùng:

~~~java
import java.util.List;
import java.util.Locale;

List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("fr-FR")
);
Locale applicationDefault = Locale.forLanguageTag("en-US");
~~~

Đây là **đoạn mã minh họa**, đặt trong một phương thức của lớp đã import các kiểu. Danh sách trên là **cam kết hỗ trợ của ứng dụng**, không phải danh sách tất cả `Locale` mà JDK có thể phân tích.

`Locale.getAvailableLocales()` cung cấp các locale mà runtime và các locale service provider nhận biết; điều đó **không đồng nghĩa** ứng dụng đã có đầy đủ màn hình, message bundles, nội dung hoặc chính sách nghiệp vụ cho tất cả locale ấy.

Cần xác định ba bất biến:

- Danh sách `supported` không rỗng và có thứ tự/quy tắc lựa chọn được kiểm soát.
- Default phải là locale đã được hỗ trợ, trừ khi thiết kế đặc biệt có lý do rõ ràng.
- Các locale công bố là “được hỗ trợ” phải thực sự có đủ tài nguyên thiết yếu hoặc một chính sách fallback tài nguyên minh bạch.

Có thể dùng cấu hình để thay danh sách và default theo sản phẩm/tenant, nhưng nên kiểm tra hợp lệ khi khởi động thay vì đợi đến request đầu tiên gặp lỗi.

## 3. Nhận diện no-match từ các API Java

### Locale.lookup() có thể trả null

Java cung cấp `Locale.LanguageRange.parse()` để phân tích các dải ngôn ngữ có trọng số như `Accept-Language`, và `Locale.lookup()` để tìm kết quả theo cơ chế lookup của RFC 4647.

~~~java
List<Locale.LanguageRange> preferences =
        Locale.LanguageRange.parse("ja-JP,ko-KR;q=0.8");
Locale matched = Locale.lookup(preferences, supported);

if (matched == null) {
    // Chưa có locale nào khớp: chuyển tới chính sách no-match.
}
~~~

Đây là đoạn minh họa trong phạm vi đã khai báo `supported` và import `java.util.List`, `java.util.Locale`. **`null` là kết quả bình thường khi không tìm được match**, không nên dereference ngay bằng `matched.toLanguageTag()`.

Một tình huống dễ hiểu sai: `Locale.lookup(Locale.LanguageRange.parse("fr-CA"), supported)` có thể trả `null` dù danh sách có `fr-FR`. Thuật toán lookup không tự quyết định rằng “mọi biến thể vùng có cùng ngôn ngữ là tương đương”. Nếu sản phẩm muốn từ `fr-CA` chuyển sang `fr-FR`, phải có **quy tắc fallback cấp ngôn ngữ** được phê duyệt, hoặc thiết kế danh sách/thuật toán matching phù hợp. Không tự ý thay `CA` bằng `FR` rồi xem đó là kết quả khớp chính xác.

Ngoài ra, giá trị chỉ chứa wildcard `*` có thể không đưa ra lựa chọn cụ thể từ `Locale.lookup`; trong Java, wildcard không được xử lý như một lệnh bắt buộc chọn locale đầu tiên. Khi yêu cầu là “chấp nhận bất kỳ”, hệ thống vẫn cần một lựa chọn mặc định hoặc quy tắc ưu tiên cụ thể.

### Locale.filter() khác Locale.lookup()

`Locale.filter()` trả một **danh sách** các locale phù hợp theo cơ chế filtering; nó không có cùng hợp đồng với `lookup()`. Với filter, trường hợp không có kết quả thường cho danh sách rỗng. Cách xử lý tương ứng:

~~~java
List<Locale> matches = Locale.filter(preferences, supported);
if (matches.isEmpty()) {
    // Áp dụng no-match policy.
}
~~~

Không thay `lookup` bằng `filter` một cách máy móc: cơ chế đối chiếu, độ rộng của kết quả và hành vi language ranges khác nhau. Trước tiên xác định sản phẩm cần **một locale duy nhất** hay **tập những locale chấp nhận được**.

### Lỗi cú pháp không phải no-match

`Locale.LanguageRange.parse(...)` có thể ném `IllegalArgumentException` nếu giá trị không phải danh sách language ranges hợp lệ. Tránh bắt mọi exception rồi lặng lẽ coi tất cả là không khớp. Ví dụ cấu hình sai `"en_US"` cần được báo đúng lỗi nhập liệu hoặc xử lý theo chính sách dữ liệu hỏng đã tài liệu hóa.

Đối với một **thẻ ngôn ngữ đơn lẻ** trong cấu hình, `Locale.forLanguageTag()` là parser khoan dung; nếu cần kiểm tra nghiêm ngặt có thể dùng `new Locale.Builder().setLanguageTag(tag).build()`. Với header chứa nhiều thẻ và trọng số, dùng parser `Locale.LanguageRange`, không truyền toàn bộ header vào `Locale.forLanguageTag()`.

## 4. Những chính sách xử lý no-match có thể chọn

Không có một lựa chọn đúng tuyệt đối cho mọi sản phẩm. Chính sách phải xuất phát từ mức độ bắt buộc về ngôn ngữ và tính chất nội dung.

| Chính sách | Hành vi khi không khớp | Phù hợp khi | Điều cần làm rõ |
| --- | --- | --- | --- |
| **Dùng default đã công bố** | Chọn `en-US` hoặc locale sản phẩm đã cấu hình | Website, trang tài liệu nhiều ngôn ngữ, UI phổ thông | Giao diện có thể khác mong muốn; thông báo lựa chọn khi cần |
| **Từ chối / yêu cầu lựa chọn lại** | Trả lỗi cụ thể hoặc hiển thị hộp chọn ngôn ngữ | API yêu cầu locale nghiêm ngặt, tài liệu pháp lý, nội dung buộc đúng ngôn ngữ | Mã lỗi, thông điệp, danh sách hỗ trợ và cách chọn lại |
| **Thử fallback có kiểm soát** | Ví dụ `fr-CA` → `fr-FR` nếu bản dịch cho phép | Nội dung chỉ yêu cầu gần đúng theo ngôn ngữ | Quy tắc theo từng ngôn ngữ, vùng, loại nội dung |
| **Dùng locale trung lập** | Dùng nội dung độc lập ngôn ngữ hoặc mã kỹ thuật | Dữ liệu máy không có bản dịch | Không được biến thành giao diện “vô ngôn ngữ” khó hiểu |

Lưu ý: `Locale.ROOT` biểu diễn locale gốc/trung lập trong Java, nhưng không tự tạo ra bản dịch dự phòng phù hợp với con người. Khi phải trả thông điệp thân thiện, thường cần một **ngôn ngữ mặc định thực tế**.

### Thứ tự ưu tiên phải được viết thành hợp đồng

Một hợp đồng có thể là:

1. Nếu người dùng đã chọn trực tiếp một locale **được hỗ trợ**, giữ lựa chọn đó.
2. Nếu không có lựa chọn trực tiếp, thương lượng `Accept-Language` với danh sách hỗ trợ.
3. Nếu không khớp, áp dụng chính sách của tính năng: dùng default, từ chối hoặc fallback có kiểm soát.
4. Ghi nhận locale cuối cùng và lý do lựa chọn để phục vụ chẩn đoán.

Đây là **ví dụ về chính sách**, không phải một thứ tự bắt buộc của Java. Với sản phẩm ưu tiên header hơn hồ sơ, thứ tự có thể khác; cần thống nhất giữa UI, API, tài liệu và kiểm thử.

Nếu một yêu cầu **chọn locale trực tiếp** đã được người dùng gửi rõ ràng nhưng không hỗ trợ, không nhất thiết nên lặng lẽ chuyển sang ngôn ngữ trong header. Sản phẩm phải định nghĩa liệu lựa chọn trực tiếp có quyền ưu tiên tuyệt đối, có được fallback hay phải trả lỗi.

## 5. Thiết kế kết quả chọn locale có lý do rõ ràng

Để tránh nhầm một match thực sự với một fallback, ngoài `Locale` cuối cùng, nên ghi nhận nguồn quyết định:

- `MATCHED`: tìm được locale theo tiêu chí đã cấu hình.
- `MISSING_FALLBACK`: client không cung cấp sở thích, đã dùng default.
- `UNMATCHED_FALLBACK`: có sở thích hợp lệ nhưng không khớp, đã dùng default.

Khi hệ thống từ chối, phải cung cấp một lỗi có ý nghĩa thay vì tiếp tục trả `null`. Mô hình nguồn quyết định giúp đo số lượt fallback, nhận diện lỗ hổng hỗ trợ ngôn ngữ và kiểm tra UI có hiển thị đúng thông điệp hay không.

Không log nguyên mọi header hoặc thông tin người dùng mà không có mục đích. Có thể ghi các mã đã chuẩn hóa hoặc đếm theo loại kết quả, theo chính sách bảo vệ dữ liệu của sản phẩm.

## 6. Ví dụ Java 17+ hoàn chỉnh: USE_DEFAULT hoặc REJECT

Chương trình dưới đây minh họa hai chính sách **được chọn tường minh**. Danh sách locale và default được đặt cố định để kết quả dễ kiểm chứng. Dữ liệu lỗi cú pháp được tách khỏi trường hợp không có match.

Tạo tệp **`LocaleNoMatchDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class LocaleNoMatchDemo {
    enum Policy {
        USE_DEFAULT,
        REJECT
    }

    enum Decision {
        MATCHED,
        MISSING_FALLBACK,
        UNMATCHED_FALLBACK
    }

    record Resolution(Locale locale, Decision decision) {}

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("fr-FR")
    );
    private static final Locale DEFAULT = Locale.forLanguageTag("en-US");

    private static Resolution noMatch(Policy policy, Decision reason) {
        if (policy == Policy.REJECT) {
            throw new IllegalArgumentException(
                    reason == Decision.MISSING_FALLBACK
                            ? "Missing locale preference"
                            : "No supported locale matches");
        }
        return new Resolution(DEFAULT, reason);
    }

    static Resolution resolve(String acceptLanguage, Policy policy) {
        Objects.requireNonNull(policy, "policy");

        if (!SUPPORTED.contains(DEFAULT)) {
            throw new IllegalStateException(
                    "Default locale is not supported");
        }
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return noMatch(policy, Decision.MISSING_FALLBACK);
        }

        List<Locale.LanguageRange> requested;
        try {
            requested = Locale.LanguageRange.parse(acceptLanguage);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Malformed language preference", ex);
        }

        Locale matched = Locale.lookup(requested, SUPPORTED);
        return matched != null
                ? new Resolution(matched, Decision.MATCHED)
                : noMatch(policy, Decision.UNMATCHED_FALLBACK);
    }

    private static void show(String label, Resolution resolution) {
        System.out.println(label + ": "
                + resolution.locale().toLanguageTag()
                + " (" + resolution.decision() + ")");
    }

    public static void main(String[] args) {
        show("Supported",
                resolve("vi-VN,fr-FR;q=0.8", Policy.USE_DEFAULT));

        show("Unsupported",
                resolve("ja-JP", Policy.USE_DEFAULT));

        show("Missing",
                resolve(null, Policy.USE_DEFAULT));

        show("Region differs",
                resolve("fr-CA", Policy.USE_DEFAULT));

        try {
            resolve("ja-JP", Policy.REJECT);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        try {
            resolve("en_US", Policy.USE_DEFAULT);
        } catch (IllegalArgumentException ex) {
            System.out.println("Malformed: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch bằng Java 17 hoặc cao hơn:

~~~bash
javac -encoding UTF-8 LocaleNoMatchDemo.java
java LocaleNoMatchDemo
~~~

Kết quả chuẩn của chương trình (đã đối chiếu hành vi API bằng Java):

~~~text
Supported: vi-VN (MATCHED)
Unsupported: en-US (UNMATCHED_FALLBACK)
Missing: en-US (MISSING_FALLBACK)
Region differs: en-US (UNMATCHED_FALLBACK)
Rejected: No supported locale matches
Malformed: Malformed language preference
~~~

### Giải thích từng nhánh

- **Supported:** `vi-VN` khớp danh sách hỗ trợ và được ưu tiên hơn `fr-FR` có trọng số `q=0.8`. Quyết định `MATCHED`.
- **Unsupported:** `ja-JP` hợp lệ nhưng không có trong tập hỗ trợ; với `USE_DEFAULT`, ứng dụng chọn `en-US`.
- **Missing:** không có input; chính sách mặc định cũng chọn `en-US`, nhưng lý do là `MISSING_FALLBACK`, khác trường hợp có yêu cầu không được đáp ứng.
- **Region differs:** `fr-CA` không mặc nhiên tương đương ứng viên `fr-FR` theo `Locale.lookup`; fallback chọn `en-US`. Nếu muốn chọn `fr-FR`, cần thêm quy tắc có chủ đích.
- **Rejected:** chính sách `REJECT` báo lỗi rõ ràng khi input hợp lệ nhưng không match; caller có thể chuyển thành HTTP response hoặc yêu cầu người dùng chọn lại.
- **Malformed:** `en_US` sai cú pháp language range; parser báo lỗi và chương trình không âm thầm coi đó là request không khớp.

Mẫu này sử dụng một `record Resolution` (hỗ trợ chính thức từ Java 16) để giữ locale cùng lý do lựa chọn. `Objects.requireNonNull` chặn một chính sách `null`; kiểm tra `SUPPORTED.contains(DEFAULT)` là bước bảo vệ cấu hình. Trong hệ thống sản xuất, nên kiểm tra bất biến này một lần khi khởi động, cấu hình lỗi HTTP tại lớp API và giới hạn độ dài header đầu vào.

**Phạm vi của ví dụ:** `resolve` nhận riêng nội dung header hoặc danh sách language ranges, chưa triển khai lựa chọn locale lưu trong hồ sơ người dùng. Nó cố ý từ chối đầu vào sai cú pháp cho cả hai chính sách. Nếu sản phẩm muốn coi header lỗi là “không gửi header”, cần viết rõ một chính sách khác và kiểm thử hành vi ấy.

## 7. Nếu muốn fallback theo ngôn ngữ, hãy quy định rõ

Nhiều sản phẩm muốn hiển thị giao diện Pháp dù người dùng yêu cầu `fr-CA` mà ứng dụng mới có `fr-FR`. Đây có thể là lựa chọn hợp lý, nhưng không thể mặc định áp dụng cho mọi ngôn ngữ hoặc mọi dữ liệu.

Ví dụ một **quy tắc nghiệp vụ bổ sung** (không có trong chương trình chạy ở mục 6):

~~~text
request: fr-CA
exact lookup: no match
authorized fallback map: fr-CA -> fr-FR
final locale: fr-FR
reason: LANGUAGE_POLICY_FALLBACK
~~~

Khi bổ sung quy tắc, cần làm rõ:

- Danh sách ánh xạ nào được phép, có thể áp dụng cho từng ngôn ngữ/vùng riêng.
- Có được dùng cùng từ ngữ nhưng khác chính tả, đơn vị đo, tiền tệ, pháp luật hoặc tập quán hay không.
- Có cần thông báo người dùng về sự thay đổi không.
- Nếu ánh xạ đích cũng không được hỗ trợ thì chuyển sang default hay từ chối.
- Thứ tự ưu tiên giữa exact match, language fallback, tenant default và global default.

Ví dụ `pt-PT` và `pt-BR` cùng tiếng Bồ Đào Nha nhưng khác biến thể; văn bản pháp lý, tiền tệ hoặc nội dung y tế có thể không được thay thế tùy tiện. Tương tự, `zh-Hans` và `zh-Hant` khác hệ chữ. **Fallback phải được cho phép theo nội dung và ngữ cảnh**, không chỉ dựa vào mã ngôn ngữ giống nhau.

Không dùng `Locale.getLanguage()` để chọn bừa phần tử đầu tiên trong `supported` mà không kiểm soát thứ tự, vì khi danh sách thay đổi, kết quả có thể đổi âm thầm.

## 8. Kết quả locale và ResourceBundle là hai lớp khác nhau

Chọn được locale không có nghĩa tất cả thông điệp bản dịch đã tồn tại. Ví dụ ứng dụng chọn `fr-FR`, nhưng resource bundle cho một số màn hình chỉ có tiếng Anh.

`ResourceBundle.getBundle(...)` có cơ chế tìm tài nguyên và fallback riêng (bao gồm khả năng sử dụng locale mặc định JVM trong một số đường đi). Nếu chỉ dùng `Locale.lookup` mà không kiểm soát bước nạp tài nguyên, UI có thể không tuân thủ hoàn toàn chính sách đã công bố.

Nên phân biệt rõ:

1. **Locale resolution:** ứng dụng chọn một locale từ tập hỗ trợ theo sở thích người dùng.
2. **Resource resolution:** ứng dụng tìm các thông điệp thực có cho locale đã chọn.
3. **Missing-key policy:** khi thiếu một khóa, ứng dụng fallback theo thứ tự cho phép, log lỗi dữ liệu hoặc dừng render nếu nội dung bắt buộc đầy đủ.

Nếu cần tránh fallback theo locale mặc định của JVM khi dùng `ResourceBundle` trong mô hình classpath phù hợp, nghiên cứu `ResourceBundle.Control.getNoFallbackControl(...)` cùng cách sắp xếp bundle gốc. Cơ chế của `ResourceBundle.Control` có giới hạn theo cách bundle được nạp và module Java; không áp dụng máy móc cho mọi môi trường. Quan trọng là phải kiểm thử **văn bản cuối cùng** chứ không chỉ kiểm tra `locale.toLanguageTag()`.

Cần thống nhất locale của thông điệp, định dạng số/ngày, và ngữ cảnh nghiệp vụ. Nếu mặc định `en-US`, UI không nên hiển thị nhãn tiếng Anh nhưng số/ngày tùy tiện theo `Locale.getDefault()` của server khi sản phẩm yêu cầu cùng một ngữ cảnh.

## 9. Hành vi ở tầng API và giao diện

### Trang web và nội dung phổ thông

Thông thường có thể dùng default công khai khi client không gửi ngôn ngữ hoặc không có ngôn ngữ tương ứng. Nếu giao diện đã đăng nhập và có lựa chọn ngôn ngữ cá nhân, cần quyết định lựa chọn đó được ưu tiên trước header hay không. Khi fallback, có thể hiển thị language switcher để người dùng chủ động đổi sang một ngôn ngữ được hỗ trợ.

Nếu nội dung trả về thay đổi theo `Accept-Language`, caching cần được thiết kế phù hợp; với HTTP, header `Vary: Accept-Language` có thể cần thiết cho các phản hồi được cache và thương lượng theo header. Cũng cần xem các yếu tố như cookie/hồ sơ người dùng để tránh gửi nhầm bản dịch của người khác.

### API có yêu cầu locale nghiêm ngặt

Một endpoint tạo tài liệu theo ngôn ngữ pháp lý đã chọn có thể không được phép âm thầm dùng default. Khi không hỗ trợ, trả lỗi được định nghĩa trong hợp đồng API, ví dụ yêu cầu client chọn lại locale. Nếu lỗi là tham số không hợp lệ, có thể dùng `400 Bad Request`; nếu liên quan đến khả năng cung cấp representation theo thương lượng nội dung, `406 Not Acceptable` có thể phù hợp tùy hợp đồng. Không chọn mã trạng thái chỉ dựa vào việc `Locale.lookup()` trả `null`: HTTP `Accept-Language` là một sở thích của client, và không phải mọi tình huống không khớp đều phải trả 406.

Response lỗi hữu ích nên cho biết locale đã yêu cầu (ở dạng được phép hiển thị), nguyên nhân và danh sách mã được hỗ trợ. Không trả exception stack trace cho người dùng cuối.

### Nội dung nhạy cảm hoặc có ràng buộc pháp lý

Khi cần đúng ngôn ngữ/phiên bản vùng để tránh hiểu nhầm nội dung, chính sách `REJECT` hoặc yêu cầu xác nhận chuyển ngôn ngữ thường dễ kiểm soát hơn fallback ngầm. Quyết định phải theo nghiệp vụ và được kiểm thử, không phải mặc định chung cho mọi sản phẩm.

## 10. Thiết kế kiểm thử bảng quyết định

Hãy kiểm tra cả **locale được trả** và **lý do**. Với danh sách hỗ trợ `vi-VN`, `en-US`, `fr-FR`, default `en-US` và chính sách ví dụ ở mục 6:

| Đầu vào | Chính sách | Kỳ vọng |
| --- | --- | --- |
| `vi-VN` | USE_DEFAULT | `vi-VN / MATCHED` |
| `fr-FR,vi-VN;q=0.7` | USE_DEFAULT | `fr-FR / MATCHED` |
| `ja-JP` | USE_DEFAULT | `en-US / UNMATCHED_FALLBACK` |
| `ja-JP` | REJECT | Lỗi `No supported locale matches` |
| `fr-CA` | USE_DEFAULT | `en-US / UNMATCHED_FALLBACK` với thuật toán hiện tại |
| `null` hoặc `""` | USE_DEFAULT | `en-US / MISSING_FALLBACK` |
| `null` hoặc `""` | REJECT | Lỗi `Missing locale preference` |
| `en_US` | USE_DEFAULT | Lỗi `Malformed language preference` |
| Default không thuộc danh sách hỗ trợ | Bất kỳ | Lỗi cấu hình trước khi thương lượng |

Những kịch bản khác cần đưa vào kiểm thử khi áp dụng thực tế: ngôn ngữ mới được thêm vào hoặc bị gỡ; wildcard `*`; yêu cầu có trọng số `q`, kể cả loại trừ `q=0`; thẻ chỉ có ngôn ngữ; ngôn ngữ có script; tên vùng khác nhau; header dài/bất thường; locale trong hồ sơ người dùng đã hết hỗ trợ; và cache trả đúng biến thể ngôn ngữ.

Với `q=0` (client đánh dấu một language range là không chấp nhận), cần kiểm thử hành vi của cơ chế thương lượng cụ thể và đảm bảo chính sách fallback cuối cùng không đi ngược các ràng buộc bắt buộc của ứng dụng. Nếu default không được người dùng chấp nhận nhưng API lại bắt buộc đúng ngôn ngữ, phải xem xét chọn `REJECT` thay vì mặc định một cách im lặng.

Đặt test chạy trong JVM có locale mặc định khác (ví dụ máy chủ cấu hình tiếng Anh và CI cấu hình tiếng Việt) để chứng minh rằng quyết định không phụ thuộc ngầm vào `Locale.getDefault()`.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `Locale.lookup(...).toLanguageTag()` ngay | `NullPointerException` khi không khớp | Xử lý `null` bằng chính sách rõ ràng |
| Dùng `Locale.getDefault()` vô điều kiện | Hành vi thay đổi theo server/container | Cấu hình default của sản phẩm |
| Nhận mọi locale mà parser hiểu | UI được chọn nhưng thiếu bản dịch | Duy trì danh sách hỗ trợ thực tế |
| Xem header sai cú pháp như không khớp | Che lỗi client, khó quan sát | Phân loại invalid/missing/unmatched |
| Tự ánh xạ mọi locale cùng language | Sai vùng, hệ chữ hoặc ngữ cảnh | Bảng fallback được phê duyệt |
| Chỉ kiểm tra locale match mà bỏ qua bundle | Kết quả UI lẫn ngôn ngữ | Kiểm thử resource resolution |
| Trả `406` cho mọi header không khớp | Khó sử dụng với client chỉ nêu sở thích | Tùy hợp đồng, cho phép default khi phù hợp |
| Dùng thứ tự ngẫu nhiên của tập locale | Kết quả không ổn định | Danh sách/quy tắc ưu tiên xác định |
| Không ghi nguồn quyết định | Không biết có bao nhiêu lần fallback | Lưu loại quyết định có kiểm soát |
| Thay đổi `Locale.setDefault` mỗi request | Trạng thái toàn cục gây ảnh hưởng lẫn nhau | Truyền locale riêng theo request |

## 12. Tự kiểm tra và thực hành

**Câu 1.** Ứng dụng chỉ hỗ trợ `vi-VN` và `en-US`. Client yêu cầu `ja-JP`, nhưng sản phẩm là website giới thiệu có default `vi-VN`. Có nên ném exception ngay?

**Gợi ý:** Nếu hợp đồng là ưu tiên sở thích nhưng cho phép default, trả `vi-VN` cùng lý do `UNMATCHED_FALLBACK`. Exception chỉ hợp lý khi chính sách bắt buộc phải match hoặc lý do nghiệp vụ khác yêu cầu từ chối.

**Câu 2.** Tại sao `fr-CA` không tự động được thay bằng `fr-FR` trong mọi hệ thống?

**Đáp án:** Hai locale cùng ngôn ngữ nhưng khác vùng. Thuật toán `lookup` không bảo đảm một phép thay vùng tùy ý; lựa chọn tương đương về nội dung là quyết định nghiệp vụ cần định nghĩa riêng.

**Câu 3.** Trường hợp `Locale.lookup()` trả `null` và `Locale.LanguageRange.parse()` ném `IllegalArgumentException` có nên chung một mã lỗi không?

**Đáp án:** Không nên đánh đồng. Trường hợp đầu là không có match từ input đã phân tích; trường hợp thứ hai là input sai cú pháp. Có thể cùng kết thúc bằng fallback nếu được thiết kế rõ, nhưng cần phân loại để xử lý và chẩn đoán.

**Bài tập.** Sửa `LocaleNoMatchDemo` để thêm một cấu hình `TENANT_DEFAULT`, rồi viết test khẳng định default của tenant phải thuộc danh sách locale tenant hỗ trợ. Tạo thêm một nhánh `LANGUAGE_POLICY_FALLBACK` chỉ cho phép ánh xạ `fr-CA → fr-FR`, bảo đảm các locale còn lại giữ nguyên chính sách đã có. Viết test cho cả trước/sau thay đổi.

**Ghi nhớ:** No-match là một **kết quả hợp lệ của quá trình lựa chọn**, không phải lời mời dùng ngẫu nhiên cấu hình của máy chủ. Hãy định nghĩa danh sách hỗ trợ, default, luật fallback hoặc từ chối, lý do của quyết định và các trường hợp kiểm thử trước khi triển khai.
