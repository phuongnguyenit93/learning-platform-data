# Fallback theo nhu cầu ứng dụng: chọn ngôn ngữ và locale đúng trong Java

Khi một ứng dụng hỗ trợ nhiều ngôn ngữ nhưng chưa có bản dịch cho mọi vùng, việc “fallback về một ngôn ngữ khác” là một **quyết định sản phẩm** chứ không đơn thuần là gọi một phương thức Java. Người dùng yêu cầu `fr-CA` (tiếng Pháp ở Canada), sản phẩm có `fr` nhưng không có `fr-CA`: có thể dùng `fr`. Người dùng yêu cầu `de-DE` (tiếng Đức ở Đức) nhưng sản phẩm chỉ có tiếng Anh và tiếng Việt: có thể chọn tiếng Anh **nếu đó là ngôn ngữ mặc định do ứng dụng quy định**. Một màn hình hợp đồng pháp lý lại có thể yêu cầu bản dịch đúng khu vực, không được tự động sử dụng bản gần nhất.

Java cung cấp hai nhóm công cụ đang được sử dụng trong Java hiện đại:

- **`Locale`**, `Locale.LanguageRange`, `Locale.lookup` và `Locale.filter`: biểu diễn thẻ ngôn ngữ (BCP 47) và chọn một locale từ danh sách mà **ứng dụng thật sự hỗ trợ**. Các API matching theo RFC 4647 đã có trong Java 8.
- **`ResourceBundle`** và `ResourceBundle.Control`: tìm resource theo biến thể locale, kế thừa bundle của ngôn ngữ gần hơn và bundle gốc để đọc các khóa dịch. Có thể cấu hình cách tìm và fallback trên classpath/unnamed module.

**Bốn kiểu fallback cần tách riêng:**

1. **Chọn locale cho request**: khi người dùng muốn `fr-CA` nhưng ứng dụng chỉ hỗ trợ `fr`, `en` và `vi`, chọn locale nào?
2. **Tìm resource bundle**: với locale đã chọn, nếu không có tệp `Messages_fr_CA` thì thử `Messages_fr` rồi `Messages` hay tìm locale mặc định JVM?
3. **Tìm khóa bản dịch**: trong `Messages_fr` thiếu `checkout.button` thì lấy từ parent `Messages`, hiển thị nhãn thay thế hay báo lỗi?
4. **Định dạng dữ liệu và chính sách miền**: văn bản tiếng Anh không đồng nghĩa số tiền phải dùng ký hiệu USD, thời gian phải ở múi giờ London, hoặc một hợp đồng pháp lý được phép dùng tiếng Anh.

Bài thuộc mục **Ngôn ngữ và locale**, chủ đề **Fallback theo nhu cầu ứng dụng**. Tất cả kiến thức và Java API trình bày **vẫn áp dụng hiện nay**; ví dụ chính sử dụng API Java 8, chạy trên JDK 17+ và đã được kiểm tra bằng bản biên dịch tương thích Java 8.

## 1. Locale không phải chỉ là mã quốc gia

`java.util.Locale` mô tả tập các thuộc tính có thể gồm:

- **Language**: `vi`, `en`, `fr`, `zh`.
- **Script**: `Latn` (Latin), `Hans` (Hán giản thể), `Hant` (Hán phồn thể).
- **Region**: `VN`, `US`, `GB`, `CA`, `TW`.
- **Variant**: biến thể theo nhu cầu ngôn ngữ.
- **Extensions**: ví dụ Unicode locale extensions dùng cho lựa chọn lịch, hệ số, đối chiếu chuỗi, định dạng.

Ví dụ:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale canadianFrench = Locale.forLanguageTag("fr-CA");
Locale traditionalChinese = Locale.forLanguageTag("zh-Hant-TW");

System.out.println(vietnamese.getLanguage()); // vi
System.out.println(canadianFrench.getCountry()); // CA
System.out.println(traditionalChinese.getScript()); // Hant
~~~

Đây là **đoạn minh họa**; import `java.util.Locale`. Thẻ BCP 47 dùng dấu gạch ngang `-`. `Locale.toLanguageTag()` hữu ích để tạo biểu diễn chuẩn hóa cho HTTP hoặc cấu hình.

### 1.1. Không ghép nhầm ngôn ngữ và quốc gia

- `en-US` và `en-GB`: cùng ngôn ngữ, cách viết/thuật ngữ, ngày giờ, đơn vị đo có thể khác.
- `fr-CA` và `fr-FR`: cùng họ ngôn ngữ nhưng từ vựng, quy chuẩn pháp lý và nội dung tiếp thị có thể khác.
- `zh-Hans` và `zh-Hant`: khác **script**, không nên gộp tùy tiện chỉ vì đều có `zh`.
- `pt-BR` và `pt-PT`: nội dung tại hai vùng có thể cần biên tập riêng.
- `sr-Latn` và `sr-Cyrl`: script rất quan trọng khi chọn tài nguyên hiển thị.

**Không có một quy tắc fallback toàn cầu luôn đúng** cho mọi ngôn ngữ. Một sản phẩm có thể hợp lý khi `fr-CA → fr` nhưng không thể mặc nhiên dùng `zh-Hans` làm bản dịch cho người yêu cầu `zh-Hant`, nhất là trong nội dung quan trọng.

### 1.2. Locale.ROOT không có nghĩa “tiếng Anh”

`Locale.ROOT` có các thuộc tính language/region trống. Trong `ResourceBundle`, nó thường đại diện **bundle gốc** như `Messages.properties` hoặc class `Messages`. Văn bản bên trong bundle gốc có thể được tác giả ứng dụng viết bằng tiếng Anh, tiếng Việt hoặc một ngôn ngữ trung tính.

Do đó:

~~~java
Locale.ROOT.equals(Locale.ENGLISH); // false
~~~

Không sử dụng `Locale.ROOT` như một tên khác của `Locale.ENGLISH`. **Chính nội dung của base bundle** quyết định bản dịch cuối cùng, chứ không phải tên `ROOT`.

## 2. Xác định fallback policy trước khi gọi API

Một ứng dụng nhiều tenant có thể chọn các cấp ưu tiên:

~~~text
Ưu tiên cao -> thấp
1. Locale do người dùng đã lưu trong tài khoản (nếu còn được hỗ trợ)
2. Locale được user chủ động chọn trong request hoặc giao diện
3. Accept-Language của trình duyệt, với các mức ưu tiên q
4. Locale mặc định của tenant hoặc sản phẩm
5. Một hành vi cuối cùng được quy định rõ: ROOT / thông báo lỗi / từ chối
~~~

**Đây là ví dụ thứ tự chính sách**, không phải điều Java tự áp dụng. Một API có tham số `lang` rõ ràng có thể ưu tiên request override hơn cài đặt tài khoản; email notification có thể ưu tiên ngôn ngữ người nhận; trang công khai có thể ưu tiên `Accept-Language`. Cần thống nhất quy tắc theo sản phẩm.

Nên công bố rõ:

- Danh sách locale mà ứng dụng **có tài nguyên đã kiểm thử**.
- Locale mặc định của ứng dụng hoặc từng tenant.
- Có cho phép fallback trong **cùng ngôn ngữ** nhưng khác vùng/script không?
- Khi chưa có **khóa dịch**, dùng base bundle, thông báo rõ, hay coi là lỗi build?
- Nội dung pháp lý, bảo mật, thanh toán hoặc y tế có được fallback không?
- Locale dùng để **định dạng** có được tách khỏi locale dùng để **dịch UI** không?

### 2.1. Quy tắc “đã hỗ trợ” quan trọng hơn “JDK biết locale”

`Locale.getAvailableLocales()` mô tả khả năng của các locale-sensitive providers trong runtime, **không phải danh sách bản dịch sản phẩm**. JDK có thể biết `de-DE` để định dạng ngày, nhưng ứng dụng không hề có `Messages_de.properties`.

**Sai lầm:** lấy `Locale.getAvailableLocales()` làm mọi ngôn ngữ sản phẩm hỗ trợ.

**Đúng hơn:** duy trì một `Set<Locale>` hoặc danh sách BCP 47 **do đội sản phẩm/l10n quản lý**, được xác minh trong CI cùng resource bundles, rồi chỉ negotiation với tập đó.

## 3. Chọn locale từ Accept-Language bằng RFC 4647

HTTP `Accept-Language` có thể biểu diễn một danh sách ưu tiên:

~~~http
Accept-Language: fr-CA, en-US;q=0.8, vi;q=0.5
~~~

`q` là trọng số sở thích ngôn ngữ, thông thường từ 0 đến 1. Java 8 có:

~~~java
List<Locale.LanguageRange> preferences =
    Locale.LanguageRange.parse("fr-CA, en-US;q=0.8, vi;q=0.5");

List<Locale> supported = Arrays.asList(
    Locale.ENGLISH,
    Locale.UK,
    Locale.FRENCH,
    Locale.forLanguageTag("vi"));

Locale result = Locale.lookup(preferences, supported);
~~~

Đây là **đoạn minh họa** với imports `Locale`, `List`, `Arrays`. `Locale.lookup` chọn một kết quả phù hợp theo cơ chế *lookup* của RFC 4647. Trong danh sách hỗ trợ ở trên, ưu tiên `fr-CA` có thể được rút về `fr`; `result.toLanguageTag()` là `fr`.

### 3.1. Lookup và filtering là hai việc khác nhau

| API | Dùng để làm gì? | Trả về |
| --- | --- | --- |
| `Locale.LanguageRange.parse` | Đọc danh sách ưu tiên có thể có q | `List<LanguageRange>` |
| `Locale.lookup` | Chọn **một locale phù hợp nhất** từ tập hỗ trợ theo RFC 4647 | `Locale` hoặc `null` |
| `Locale.lookupTag` | Chọn một language tag String từ tập tags | `String` hoặc `null` |
| `Locale.filter` | Lấy **các locale phù hợp** từ danh sách hỗ trợ | `List<Locale>` |
| `Locale.filterTags` | Lấy những language tag phù hợp | `List<String>` |
| `Locale.forLanguageTag` | Parse một BCP 47 language tag thành đối tượng | `Locale` |

**`lookup` không tự chọn tiếng Anh của ứng dụng khi không có match.** Nó trả `null`, lúc đó **ứng dụng** phải quyết định fallback mặc định:

~~~java
Locale selected = Locale.lookup(preferences, supported);

if (selected == null) {
    selected = Locale.ENGLISH; // Quy tắc ứng dụng.
}
~~~

Nếu một request có `Accept-Language: de-DE` nhưng bạn chỉ hỗ trợ `en` và `vi`, Java không có lý do để tự biết tiếng Anh là mong muốn của sản phẩm. Đó là cấu hình của bạn, không phải tiêu chuẩn HTTP.

### 3.2. Request header là dữ liệu không tin cậy

Header có thể vắng mặt, quá dài, sai cú pháp hoặc chứa các thẻ ngôn ngữ không được sản phẩm hỗ trợ. Trong server thực:

1. Giới hạn độ dài/giới hạn số phần tử header theo cấu hình dịch vụ.
2. Parse bên trong `try/catch IllegalArgumentException`.
3. Không dùng giá trị header trực tiếp làm đường dẫn tệp, tên class hoặc đường truy cập resource tùy ý.
4. Chỉ chọn locale nằm trong danh sách hỗ trợ.
5. Khi không có match hoặc input không hợp lệ, áp dụng **fallback ứng dụng đã định nghĩa**.
6. Nếu API yêu cầu bảo toàn q=0, wildcard, chính sách “không chấp nhận bản dịch” hoặc thông tin pháp lý, kiểm thử kỹ theo HTTP semantics và quy tắc của chính ứng dụng.

Không nên coi `Locale.forLanguageTag(headerRaw)` là một parser thay thế cho **cả danh sách `Accept-Language`**, vì nó chỉ nhận một language tag, không tự diễn giải q-weighted ranges như `LanguageRange.parse`.

### 3.3. Kiểm thử thứ tự lựa chọn

Giả sử ứng dụng hỗ trợ:

~~~text
en
en-GB
fr
vi
~~~

| Input preference | Locale được ứng dụng chọn | Lý do |
| --- | --- | --- |
| `fr-CA, en-US;q=0.8` | `fr` | Cùng ngôn ngữ là match được phép theo lookup |
| `en-AU` | `en` | Rút dần subtags theo RFC lookup |
| `en-GB` | `en-GB` | Có chính xác locale được hỗ trợ |
| `de-DE` | `en` | Không match; **policy mặc định** tiếng Anh |
| Không có header | `en` | **Policy mặc định** |
| Chuỗi sai cú pháp | `en` | Parse lỗi và được app fallback |

**Đây là output theo policy/danh sách của ví dụ**, không có nghĩa mọi ứng dụng nên fallback sang tiếng Anh. Một sản phẩm cho người Việt có thể chọn `vi`; sản phẩm Canada có thể ưu tiên `fr-CA` hoặc `en-CA`; sản phẩm pháp lý có thể từ chối thay vì fallback.

## 4. ResourceBundle giải quyết tầng tìm kiếm tài nguyên

Một cách tổ chức truyền thống, vẫn dùng được:

~~~text
src/main/resources/i18n/
  Messages.properties
  Messages_en.properties
  Messages_en_GB.properties
  Messages_fr.properties
  Messages_vi.properties
~~~

Khi load trên classpath:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
    "i18n.Messages",
    Locale.forLanguageTag("fr-CA"));

String title = bundle.getString("screen.title");
~~~

Đây là **mã minh họa**, đường dẫn và tên property key cần tồn tại trong dự án. Nếu có `Messages_fr.properties` nhưng không có `Messages_fr_CA.properties`, ResourceBundle có thể chọn bundle tiếng Pháp. Với một khóa không có trong bundle tiếng Pháp, nó tìm trên **parent chain**, có thể đến `Messages.properties`.

### 4.1. Quy tắc candidate locales

Với locale đơn giản, thứ tự thường là:

~~~text
fr-CA:
  Messages_fr_CA
  Messages_fr
  Messages                 (ROOT/base)

en-GB:
  Messages_en_GB
  Messages_en
  Messages                 (ROOT/base)
~~~

Với script/variant, danh sách có nhiều cấp hơn. Ví dụ về ý tưởng:

~~~text
zh-Hant-TW:
  Messages_zh_Hant_TW
  Messages_zh_Hant
  Messages_zh_TW
  Messages_zh
  Messages
~~~

**Đây là thứ tự khái quát theo họ cấu trúc Java**, không thay cho Javadoc `ResourceBundle.Control.getCandidateLocales`: một số language tags/locale đặc biệt có danh sách bổ sung hoặc thứ tự khác. Quy tắc không có nghĩa Java “dịch” từ giản thể sang phồn thể; nó chỉ tìm **resource bundles mà ứng dụng đóng gói**.

### 4.2. getBundle và getString có thể fallback ở hai thời điểm khác nhau

Hai câu hỏi:

1. `ResourceBundle.getBundle(...)` chọn **đối tượng bundle đại diện** với locale nào?
2. `bundle.getString(key)` tìm khóa **ở bundle đó hay một parent**?

Ví dụ:

~~~text
Messages.properties:
  title=Hello (root)
  status=Status (root)

Messages_fr.properties:
  title=Bonjour
  (không có status)

Yêu cầu: fr-CA
Bundle được chọn: fr
getString("title")  -> Bonjour
getString("status") -> Status (root)
~~~

**`bundle.getLocale()` trả locale của bundle được chọn**, không nói một khóa cụ thể được lấy từ bundle cấp nào. Trong ví dụ `getLocale() == fr` dù `status` thực sự rơi về bundle gốc.

### 4.3. MissingResourceException

Có hai tình huống phổ biến:

- **Không tìm được bundle nào**, kể cả ROOT/base theo quy tắc tìm kiếm: `ResourceBundle.getBundle` có thể ném `MissingResourceException`.
- **Không tìm thấy key trong bundle và parent chain**: `bundle.getString(key)` có thể ném `MissingResourceException`.

~~~java
try {
    String label = bundle.getString("checkout.pay");
} catch (MissingResourceException ex) {
    // Chọn chính sách: telemetry, lỗi kiểm thử, bản thay thế,
    // hoặc trả thông báo thân thiện. Không âm thầm giấu lỗi.
}
~~~

Đây là snippet minh họa. Không nên trả nguyên `null` và tạo `NullPointerException` muộn hơn; cần một policy được ghi nhận.

### 4.4. containsKey cũng tính các parent

`ResourceBundle.containsKey(key)` xem xét bundle **và parent chain**, không chỉ file locale cụ thể. Vì vậy:

~~~java
boolean exists = bundle.containsKey("status");
~~~

có thể là true dù `Messages_fr` không hề tự dịch `status`, vì `Messages.properties` có khóa đó.

**Hệ quả cho QA bản dịch:** nếu muốn đo tỷ lệ dịch hoàn chỉnh của `fr`, **không** đếm đơn giản `containsKey` trên bundle đã fallback. Cần so các tài nguyên **riêng từng locale** ở build/tooling layer, không chỉ gọi public inherited lookup.

## 5. Fallback ngầm sang locale mặc định JVM: bẫy khó thấy

Một câu lệnh có vẻ xác định:

~~~java
ResourceBundle bundle =
    ResourceBundle.getBundle("i18n.Messages", requested);
~~~

Theo chiến lược mặc định, sau khi thử candidates của `requested`, ResourceBundle có thể thử **locale mặc định của JVM** trước khi cuối cùng dùng ROOT/base. Do đó chương trình dùng cùng code và cùng file resources vẫn có thể trả ngôn ngữ khác nhau nếu cấu hình locale JVM khác nhau.

Ví dụ:

~~~text
requested  = de-DE
JVM locale = fr
Có: Messages_fr và Messages

Kết quả getBundle mặc định:
  Có thể chọn Messages_fr
  dù ứng dụng mong fallback sang English ROOT.
~~~

Đây là **hành vi tìm bundle của Java**, không nhất thiết là chính sách sản phẩm mong muốn. Trên máy developer mặc định `en-US`, lỗi có thể khó thấy; khi deploy container/server có locale `fr-FR`, giao diện tự đổi sang tiếng Pháp.

### 5.1. Tránh coi Locale.getDefault() là user locale

`Locale.getDefault()` là trạng thái **toàn JVM**. Một server xử lý đồng thời người dùng tiếng Việt, tiếng Pháp và tiếng Anh không nên sửa `Locale.setDefault(...)` cho từng HTTP request. Làm vậy các request có thể ảnh hưởng lẫn nhau và tác động đến nhiều API định dạng.

Thay vì:

~~~java
// PHẢN VÍ DỤ trên server đa người dùng:
Locale.setDefault(userLocale);
String label = ResourceBundle.getBundle("i18n.Messages")
                             .getString("title");
~~~

hãy chuyển `Locale selected` **rõ ràng** qua call chain, template engine, service hoặc request context và dùng các formatter/bundles nhận locale tường minh.

### 5.2. Control không fallback sang JVM default

Trong ứng dụng chạy **classpath/unnamed module**, có thể dùng:

~~~java
ResourceBundle.Control noJvmFallback =
    ResourceBundle.Control.getNoFallbackControl(
        ResourceBundle.Control.FORMAT_DEFAULT);

ResourceBundle bundle = ResourceBundle.getBundle(
    "i18n.Messages",
    chosenLocale,
    MyApp.class.getClassLoader(),
    noJvmFallback);
~~~

Đây là mã minh họa; `MyApp` đại diện class ứng dụng. `FORMAT_DEFAULT` cho phép load class-based bundle rồi property bundle. `getNoFallbackControl` chỉ bỏ bước **fallback sang default locale của JVM**; nó **không bỏ fallback trong cùng language** (`fr-CA → fr`) và **không tự xóa base bundle ROOT**.

**Giới hạn quan trọng của Java hiện đại:** `ResourceBundle.Control` không được hỗ trợ cho `getBundle` với `Control` khi code gọi **từ named module (JPMS)**; Javadoc nêu sẽ ném `UnsupportedOperationException`. Với ứng dụng modular, cần thiết kế resource bundles theo cơ chế module/provider phù hợp (chẳng hạn `ResourceBundleProvider`), hoặc negotiation tới locale được hỗ trợ và bảo đảm đóng gói resources/không dựa vào fallback ngầm. Không copy nguyên overload Control từ ví dụ classpath sang module-info.java rồi tin nó chạy.

### 5.3. Không dùng Control để che thiếu bản dịch

Nếu ứng dụng hỗ trợ `fr` nhưng thiếu vài key, việc tắt JVM-default fallback **chỉ thay đổi cơ chế tìm bundle**, không tự giải quyết thiếu key. Cần có base bundle đầy đủ hoặc key-level policy. Đối với thông báo pháp lý quan trọng, có thể cần **fail closed**/không hiển thị nội dung sai ngôn ngữ thay vì lấy English key một cách âm thầm.

## 6. Ba chính sách fallback có thể cùng tồn tại

| Loại nội dung | Chính sách thường cân nhắc | Lý do |
| --- | --- | --- |
| Nút, nhãn UI phổ thông | Region → language → ROOT/default | Người dùng vẫn thao tác được khi thiếu vài bản dịch |
| Thông báo giao dịch/email | Preference của người nhận → ngôn ngữ được kiểm chứng → app default | Giữ thông điệp có thể đọc, log được locale thực tế |
| Nội dung pháp lý/đồng ý | Locale/region có bản đã phê duyệt, nếu không có báo không khả dụng | Tránh hiển thị bản không đủ hiệu lực pháp lý |
| Văn bản hỗ trợ khách hàng | Locale hỗ trợ gần nhất, ghi nhãn ngôn ngữ đang hiển thị | Giảm hiểu nhầm |
| Cấu hình kỹ thuật, log, error code | Mã lỗi ổn định + bản hiển thị tùy locale | Log/máy không phụ thuộc một thông điệp dịch |
| Tên sản phẩm, mã quốc gia, tiền tệ | Theo dữ liệu miền; không dịch tùy ý | Đây không phải translation key bình thường |
| Thông báo an toàn/bảo mật | Bản dịch đã QA, và hành vi rõ nếu thiếu | Không đưa thông điệp gây hiểu nhầm |

Ví dụ một ứng dụng thương mại điện tử: nhãn `Buy now` có thể fallback từ `en-GB` sang `en`. Nhưng văn bản “Điều khoản hoàn tiền” theo quốc gia phải dựa trên **bản được legal phê duyệt**, không chỉ locale gần nhất. “Fallback theo nhu cầu ứng dụng” nghĩa là policy theo **tác vụ** chứ không chọn một đường fallback mù cho toàn hệ thống.

## 7. Chương trình Java hoàn chỉnh: negotiation và ResourceBundle có fallback rõ ràng

Chương trình **`LocaleFallbackDemo.java`** bên dưới tự chứa resource bundles dạng class `ListResourceBundle`, không yêu cầu tạo thêm tệp `.properties`. Nó sử dụng:

1. Một tập locale được ứng dụng hỗ trợ: `en`, `en-GB`, `fr`, `vi`.
2. `Locale.LanguageRange.parse` + `Locale.lookup` để chọn theo yêu cầu.
3. Ứng dụng mặc định `en` nếu không match hoặc header sai.
4. `ResourceBundle.Control.getNoFallbackControl(FORMAT_CLASS)` để dùng language/parent/ROOT **mà không vô tình theo default JVM**, trên classpath.
5. Các bundle lồng nhau `Messages`, `Messages_en`, `Messages_en_GB`, `Messages_fr`, `Messages_vi`.
6. `MessageFormat` truyền **locale được chọn** để định dạng tham số thông điệp.
7. Kiểm tra một key có trong parent ROOT nhưng thiếu ở `fr`.
8. Mô phỏng JVM default `fr` trong phạm vi `try/finally` rồi so sánh fallback ngầm và fallback kiểm soát.

**Chương trình đã được biên dịch bằng `javac --release 8` và chạy thử trên OpenJDK 24.** Mặc dù demo tạm thay JVM default để biểu diễn bẫy fallback, đây **không** phải cách vận hành một server đa người dùng; `finally` khôi phục default ngay sau bài thử.

~~~java
import java.text.MessageFormat;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public final class LocaleFallbackDemo {
    private static final String BASE = "LocaleFallbackDemo$Messages";
    private static final Locale DEFAULT = Locale.ENGLISH;
    private static final List<Locale> SUPPORTED =
            Collections.unmodifiableList(Arrays.asList(
                Locale.ENGLISH,
                Locale.UK,
                Locale.FRENCH,
                Locale.forLanguageTag("vi")));
    private static final ResourceBundle.Control NO_JVM_FALLBACK =
            ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_CLASS);

    public static Locale negotiate(String header) {
        if (header == null || header.trim().isEmpty() ||
                header.length() > 256) {
            return DEFAULT;
        }
        try {
            Locale matched = Locale.lookup(
                Locale.LanguageRange.parse(header), SUPPORTED);
            return matched == null ? DEFAULT : matched;
        } catch (IllegalArgumentException ex) {
            return DEFAULT;
        }
    }

    private static ResourceBundle bundle(Locale locale) {
        return ResourceBundle.getBundle(
            BASE, locale,
            LocaleFallbackDemo.class.getClassLoader(),
            NO_JVM_FALLBACK);
    }

    public static class Messages extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"title", "Hello (root)"},
                {"status", "Status (root)"},
                {"greeting", "Hello, {0}!"}
            };
        }
    }

    public static class Messages_en extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"title", "Hello"},
                {"greeting", "Hello, {0}!"}
            };
        }
    }

    public static class Messages_en_GB extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"title", "Hello, UK"}
            };
        }
    }

    public static class Messages_fr extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"title", "Bonjour"},
                {"greeting", "Bonjour, {0}!"}
            };
        }
    }

    public static class Messages_vi extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"title", "Xin chào"},
                {"greeting", "Xin chào, {0}!"}
            };
        }
    }

    public static void main(String[] args) {
        Locale selected = negotiate("fr-CA, en-US;q=0.8");
        ResourceBundle french = bundle(selected);
        System.out.println("selected=" + selected.toLanguageTag());
        System.out.println("bundleLocale=" +
                french.getLocale().toLanguageTag());
        System.out.println("title=" + french.getString("title"));
        System.out.println("status=" + french.getString("status"));
        System.out.println("greeting=" +
                new MessageFormat(
                    french.getString("greeting"), selected)
                    .format(new Object[] {"Lan"}));
        System.out.println("enAU=" +
                negotiate("en-AU").toLanguageTag());
        System.out.println("noMatch=" +
                negotiate("de-DE").toLanguageTag());
        System.out.println("enGBTitle=" +
                bundle(Locale.UK).getString("title"));
        System.out.println("viVNTitle=" +
                bundle(Locale.forLanguageTag("vi-VN"))
                    .getString("title"));
        boolean missing = false;
        try {
            french.getString("unknown-key");
        } catch (MissingResourceException ex) {
            missing = true;
        }
        System.out.println("missingKey=" + missing);
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.FRENCH);
            ResourceBundle implicit = ResourceBundle.getBundle(
                BASE, Locale.GERMANY,
                LocaleFallbackDemo.class.getClassLoader());
            ResourceBundle explicit = bundle(Locale.GERMANY);
            System.out.println("implicitJvmFallback=" +
                    implicit.getLocale().toLanguageTag());
            System.out.println("noJvmFallbackUsesRoot=" +
                    explicit.getLocale().equals(Locale.ROOT));
        } finally {
            Locale.setDefault(original);
        }
    }
}
~~~

### 7.1. Biên dịch và chạy

Lưu file Java **UTF-8** (tên file khớp public class):

~~~bash
javac -encoding UTF-8 LocaleFallbackDemo.java
java LocaleFallbackDemo
~~~

Với JDK hỗ trợ option biên dịch đích Java 8, có thể kiểm tra thêm bằng `javac --release 8 -encoding UTF-8 LocaleFallbackDemo.java`; cảnh báo về độ tuổi phiên bản `--release 8` nếu có **không** phủ nhận API tương thích Java 8.

### 7.2. Đầu ra đã kiểm tra

~~~text
selected=fr
bundleLocale=fr
title=Bonjour
status=Status (root)
greeting=Bonjour, Lan!
enAU=en
noMatch=en
enGBTitle=Hello, UK
viVNTitle=Xin chào
missingKey=true
implicitJvmFallback=fr
noJvmFallbackUsesRoot=true
~~~

### 7.3. Giải thích kết quả

- `selected=fr`: ứng dụng hỗ trợ tiếng Pháp chung, không có `fr-CA`; `Locale.lookup` đưa người dùng vào locale `fr`.
- `bundleLocale=fr`: `ResourceBundle` chọn class `Messages_fr`; không phải `Locale.CANADA_FRENCH`.
- `title=Bonjour`: key được dịch trong `Messages_fr`.
- `status=Status (root)`: key **không có ở `Messages_fr`**, nên parent `Messages` được dùng. `getLocale()==fr` không phản ánh xuất xứ từng key.
- `greeting=Bonjour, Lan!`: chuỗi mẫu ở `fr` và `MessageFormat` dùng locale đã chọn.
- `enAU=en`: theo lookup, sở thích `en-AU` được rút về locale `en` đã hỗ trợ.
- `noMatch=en`: `de-DE` không có trong tập hỗ trợ, **ứng dụng** tự chọn DEFAULT en.
- `enGBTitle=Hello, UK`: locale có biến thể vùng được dùng khi tài nguyên đó tồn tại.
- `viVNTitle=Xin chào`: locale `vi-VN` có thể dùng bundle `vi`; không cần giả lập một tệp `vi_VN` khi chưa có khác biệt thực.
- `missingKey=true`: không có `unknown-key` ở fr hoặc ROOT, `getString` ném `MissingResourceException`.
- `implicitJvmFallback=fr`: requested `de-DE` nhưng JVM default vừa được đặt `fr`; tìm kiếm mặc định chọn French trước ROOT.
- `noJvmFallbackUsesRoot=true`: Control không fallback sang JVM default, nên requested `de-DE` không có bundle vùng/ngôn ngữ và cuối cùng nhận ROOT. Trong mã này ứng dụng **chỉ gọi trực tiếp một locale không được hỗ trợ để làm rõ hành vi**; request thông thường nên được negotiation thành `en` trước.

**Không phụ thuộc thread race, thời gian, thứ tự duyệt collection hay cấu hình hệ điều hành** để xác định output: chương trình tự cấu hình locale cho phần thí nghiệm và khôi phục trong finally.

### 7.4. Vì sao demo dùng class-based bundle?

Bundle nội bộ dạng `ListResourceBundle` cho phép chạy **một file Java độc lập**, kiểm tra trực tiếp tính đúng đắn mà không cần tạo và đóng gói thêm nhiều tệp resources. Trong ứng dụng thật, đội dịch thuật thường dùng các `.properties` hoặc hệ thống quản trị bản dịch. Hai cách đều phù hợp nếu đóng gói và hỗ trợ runtime đúng; **đừng nhầm lựa chọn dạng file với lựa chọn fallback policy**.

## 8. Dùng .properties trong dự án thật

Cấu trúc ví dụ trong Maven/Gradle:

~~~text
src/main/resources/i18n/
  Messages.properties
  Messages_en.properties
  Messages_fr.properties
  Messages_vi.properties
~~~

**`Messages.properties`** (base bundle):

~~~properties
title=Hello
status=Status
greeting=Hello, {0}!
~~~

**`Messages_fr.properties`**:

~~~properties
title=Bonjour
greeting=Bonjour, {0}!
~~~

**`Messages_vi.properties`**:

~~~properties
title=Xin chào
greeting=Xin chào, {0}!
~~~

Với `ResourceBundle.getBundle("i18n.Messages", Locale.forLanguageTag("fr-CA"))`, nếu không có `Messages_fr_CA` nhưng có `Messages_fr`, key `title` được đọc bằng tiếng Pháp; key `status` từ `Messages.properties`.

### 8.1. Lưu ý encoding theo phiên bản Java

**Không dùng mẹo lỗi thời “mọi ResourceBundle .properties luôn phải viết ISO-8859-1”.** Java đã thay đổi:

- Với **Java 8 trở về trước**, `PropertyResourceBundle` load từ stream theo quy tắc **ISO-8859-1**; ký tự ngoài tập này thường được viết bằng escape `\uXXXX` hoặc qua quy trình conversion phù hợp.
- Từ **Java 9**, cách tải property resource bundles từ `InputStream` mặc định ưu tiên **UTF-8**; khi chuỗi byte không hợp lệ theo UTF-8, runtime có cơ chế thử lại ISO-8859-1 theo đặc tả. Có thể điều chỉnh bằng system property `java.util.PropertyResourceBundle.encoding` nếu cần tương thích dữ liệu cũ.
- Với dự án **JDK 17+/21+/26**, sử dụng tệp dịch UTF-8 với build pipeline được kiểm thử là lựa chọn tự nhiên.
- Với dự án bắt buộc **chạy trên Java 8**, phải xử lý encoding Java 8 đúng (ví dụ Unicode escapes, class-based bundle, hoặc giải pháp loader UTF-8 có kiểm soát). **Không** lấy ví dụ .properties UTF-8 không dấu escape rồi tuyên bố nó chạy đúng tiếng Việt mặc định trên JDK 8.

**Chương trình hoàn chỉnh của bài không gặp khác biệt đó**, vì nó dùng `ListResourceBundle` với nguồn Java Unicode được biên dịch `-encoding UTF-8`, không dùng parser `.properties`.

### 8.2. Khi nào dùng class-based bundle?

Class-based bundles có thể chứa giá trị kiểu object bên cạnh string, phù hợp cấu hình/tài nguyên phức tạp trong một số tình huống. Nhưng bản dịch thường thuận lợi hơn khi lưu ở nguồn dữ liệu mà biên dịch viên bản địa hóa có thể chỉnh sửa độc lập. Đừng tự chọn class-based chỉ để tránh kiểm tra encoding/packaging của dự án.

### 8.3. Named modules (JPMS)

Từ Java 9, named modules có quy tắc đóng gói/encapsulation. `ResourceBundle.Control` không hoạt động như overload Control trên named modules; `ResourceBundleProvider` là cơ chế phù hợp để cung cấp tài nguyên từ module hoặc dùng resource loading được phép theo module graph.

**Bài mẫu chạy trên classpath/unnamed module.** Khi chuyển sang `module-info.java`, phải xác minh API overload, visibility, provider và truy cập resources; không sao chép nguyên `Control` sang mà không thay đổi kiến trúc.

## 9. Fallback của thông điệp có tham số

Bản dịch hiển thị không chỉ là một chuỗi; nó có thể chứa **số, ngày, tên riêng hoặc biến thể số nhiều**.

~~~properties
welcome=Hello, {0}!
items=You have {0,number,integer} items.
~~~

Khi format, cần truyền **locale đúng**:

~~~java
String pattern = bundle.getString("items");

MessageFormat fmt = new MessageFormat(pattern, selectedLocale);
String result = fmt.format(new Object[] {5});
~~~

Đây là đoạn minh họa với `bundle` và `selectedLocale` đã có. `MessageFormat` dùng locale để chọn các quy tắc định dạng số/ngày được hỗ trợ, thay vì vô tình dùng `Locale.getDefault()` của JVM.

### 9.1. Tránh truyền trực tiếp giá trị đã format thành pattern

~~~java
// PHẢN VÍ DỤ: input không tin cậy bị coi là format pattern.
MessageFormat fmt = new MessageFormat(userInput, selectedLocale);
~~~

Đây là rủi ro về logic/cú pháp và nội dung không tin cậy. Pattern nên đến từ **bộ resource đã kiểm soát**, còn input người dùng được đưa qua tham số. Khi render HTML, vẫn phải áp dụng **escaping theo ngữ cảnh**, vì `MessageFormat` không phải HTML sanitizer.

### 9.2. Plural/gender và ngữ cảnh không luôn giải quyết bằng một key

Mỗi ngôn ngữ có quy tắc số nhiều và ngữ pháp khác nhau. Đừng dịch cứng:

~~~text
"You have " + count + " items"
~~~

rồi chỉ thay hai từ tiếng Anh. `MessageFormat` tiêu chuẩn có `ChoiceFormat` và các định dạng cơ bản, nhưng không có nghĩa nó thay thế mọi quy tắc plurals/gender/context của CLDR trong một sản phẩm đa ngôn ngữ phức tạp. Với yêu cầu localization phong phú, cân nhắc framework/i18n engine hiện hành, như ICU4J hoặc hệ message catalog phù hợp, và **test từng locale**.

### 9.3. Fallback cần giữ cùng hợp đồng tham số

Nếu `Messages_fr` thiếu key và dùng pattern từ ROOT, caller vẫn phải truyền đúng số lượng/kiểu tham số. Một bản dịch có `{0}`/`{1}` bị nhầm vị trí có thể tạo thông điệp sai mà không bị phát hiện ngay.

Trong CI, nên kiểm tra:
- Mọi key bắt buộc tồn tại trong nguồn chuẩn.
- Placeholder IDs và loại tham số tương thích giữa các locale.
- Cú pháp `MessageFormat` hợp lệ.
- Không mất dữ liệu hoặc nhập nhằng khi định dạng số/đơn vị.
- Kiểm thử các trường hợp 0, 1, nhiều, số âm và tên dài.

## 10. Locale của UI khác locale định dạng dữ liệu

Một người dùng có thể muốn **giao diện bằng tiếng Anh**, **giá hiển thị bằng VND**, **định dạng số theo Việt Nam** và **múi giờ Asia/Ho_Chi_Minh**. Đây là các lựa chọn liên quan nhưng **không đồng nhất**.

### 10.1. Định dạng số và tiền

~~~java
Locale uiLocale = Locale.ENGLISH;
Locale numberLocale = Locale.forLanguageTag("vi-VN");

NumberFormat number = NumberFormat.getNumberInstance(numberLocale);
NumberFormat price = NumberFormat.getCurrencyInstance(numberLocale);

price.setCurrency(Currency.getInstance("VND"));
~~~

Đây là **mã minh họa**, cần imports `NumberFormat`, `Currency` và `Locale`. `uiLocale` dùng chọn bundle; `numberLocale` dùng định dạng. Đừng đoán currency của một đơn hàng chỉ bằng locale; currency phải lấy từ **dữ liệu giá giao dịch**. Nếu một user ở Canada mua bằng USD, `Locale.CANADA` không tự biến giá tiền giao dịch thành CAD.

**Không hardcode chuỗi output NumberFormat cho mọi JDK:** ký hiệu, khoảng trắng, group separator và CLDR locale data có thể khác theo runtime/provider. Kiểm thử ngữ nghĩa (giá trị, currency, quy tắc có chủ đích), chỉ snapshot chính xác nếu kiểm soát environment.

### 10.2. Định dạng ngày giờ

~~~java
Locale displayLocale = Locale.forLanguageTag("fr-CA");

DateTimeFormatter formatter =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                     .withLocale(displayLocale);

String dateText = formatter.format(LocalDate.of(2026, 11, 6));
~~~

Đây là **đoạn minh họa**, cần imports `java.time.LocalDate`, `DateTimeFormatter` và `FormatStyle`. Định dạng tùy locale; không dùng ngôn ngữ của UI để đoán một `Instant` có múi giờ gì. Nếu hiển thị giờ từ `Instant`, cần một `ZoneId` theo người dùng/ứng dụng:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime local = instant.atZone(zone);
~~~

`instant` là giá trị có trước. **Ngôn ngữ (`Locale`), time zone (`ZoneId`) và currency (`Currency`) là ba khía cạnh độc lập**. Nếu business chọn fallback ngôn ngữ từ `fr-CA` sang `fr`, không tự thay múi giờ/tiền tệ của user.

### 10.3. Collation và tìm kiếm không chỉ phụ thuộc translation

`Collator` có thể cung cấp locale-sensitive string comparison/sorting, nhưng chuẩn hóa tìm kiếm, chữ có dấu, text indexing và full-text search trên database thường có quy tắc riêng. Đừng bỏ qua các khác biệt như case folding hoặc diacritics chỉ vì giao diện đã chọn bundle fallback.

## 11. Fallback khi chưa có bản dịch khóa quan trọng

Không phải mọi khóa thiếu nên xử lý giống nhau:

| Key type | Ví dụ | Cách xử lý đáng cân nhắc |
| --- | --- | --- |
| Nhãn phụ | Tooltip hiếm dùng | Có thể fallback ROOT và ghi metric |
| Nút chính | `checkout.confirm` | Fallback đã QA, không dùng nhãn gây hiểu nhầm |
| Lỗi xác thực | `auth.invalidCredentials` | Không tiết lộ dữ liệu nhạy cảm; kiểm tra văn bản ngôn ngữ |
| Nội dung pháp lý | `terms.regionPolicy` | Có thể bắt buộc đúng region/version; không fallback bừa |
| Email OTP | `mail.otp` | Nội dung an toàn, placeholder và hướng dẫn đúng |
| Mô tả hóa đơn | `billing.taxExplanation` | Cần quy tắc thị trường/thuế, không chỉ cùng language |
| Mã lỗi máy | `error.code` | Giữ error code ổn định, chỉ dịch phần hiển thị |

### 11.1. Chiến lược fail open và fail closed

- **Fail open về bản dịch:** vẫn cho hiển thị một text trong ngôn ngữ mặc định để user có thể tiếp tục, kèm logging/metric về fallback.
- **Fail closed:** không hiển thị hoặc không cho thực hiện nghiệp vụ nếu chưa có bản được phê duyệt, nhất là những thao tác pháp lý, đồng ý hoặc an toàn.
- **Fallback từng phần:** chỉ một vài key được fallback tự động, còn key bắt buộc phải hoàn chỉnh.

Chọn chiến lược theo **rủi ro nghiệp vụ**. Một ứng dụng ngân hàng đa quốc gia không nên tự chọn bản điều khoản luật quốc gia khác chỉ vì language tag có phần ngôn ngữ giống nhau.

### 11.2. Đừng gửi tên khóa nội bộ cho người dùng cuối nếu không có chủ ý

Khi thiếu bản dịch:

~~~text
error.payment.limitExceeded
~~~

là một identifier thuận tiện cho developer, nhưng không nhất thiết là thông báo hợp lệ cho user. Nếu dùng key như fallback cuối ở môi trường development, phải có cơ chế phân biệt dev/prod và alert/telemetry. Production có thể chọn message an toàn, trang lỗi phù hợp hoặc trả trạng thái chưa hỗ trợ theo policy.

### 11.3. Không che lỗi thiếu bản dịch đến khi release

ResourceBundle parent chain làm ứng dụng vẫn hiển thị được, nhưng một số khóa có thể rơi về ROOT mà nhóm dịch thuật không biết. Tại build/test nên so sánh **raw keys của từng file** với catalog chuẩn, theo dõi:
- Tỷ lệ key hoàn chỉnh cho từng locale.
- Key bị thiếu hoặc thừa.
- Placeholder/ICU pattern mismatch.
- Giá trị bỏ trống, lỗi escaping, encoding.
- Locale có thay đổi chính sách và cần phê duyệt lại.
- Nội dung có giá trị pháp lý bắt buộc bản theo region.

**`containsKey` trên bundle đã có parent không phải phép kiểm tra độ phủ raw key**; nhắc lại vì đây là bug QA phổ biến.

## 12. ResourceBundle cache và reload

`ResourceBundle.getBundle` có cơ chế **cache**. Tải lại cùng base name/locale có thể trả lại resource đã cache; điều này giúp giảm I/O và parsing, nhưng cần thiết kế khi dịch vụ thay đổi bản dịch trong lúc chạy.

### 12.1. Deploy tệp resource mới không chắc live reload

Nếu process đang chạy và lớp/bundle đã cache, việc thay một `.properties` bên dưới chưa đủ để mọi request nhìn thấy nội dung mới tức thì. Có `ResourceBundle.clearCache()` và overload theo class loader; `Control` có cơ chế TTL/`needsReload` trong phạm vi được hỗ trợ. Nhưng **xóa cache toàn ứng dụng trên mỗi request** có thể gây overhead và race không cần thiết.

Trong dịch vụ hiện đại, thường có một trong hai chiến lược:
1. Đóng gói translations cùng bản release, deploy/restart theo quy trình.
2. Dùng message catalog/config service có cache TTL/versioning và invalidation được thiết kế riêng.

### 12.2. Thread safety và biến locale

`ResourceBundle` được thiết kế để được dùng bởi nhiều thread trong các tình huống thông thường, nhưng **không dùng chung một biến `currentLocale` mutable** trên singleton service cho mọi người dùng. Mỗi request nên mang locale được chọn như dữ liệu đầu vào bất biến và cache bundle theo locale nếu phù hợp.

`MessageFormat` là lớp mutable và **không mặc định an toàn khi nhiều thread cùng format chung một instance**. Nếu chia sẻ pattern, tạo `MessageFormat` theo request hoặc đồng bộ/sử dụng cơ chế khác; đừng nhầm an toàn của ResourceBundle với an toàn của mọi formatter liên quan.

### 12.3. Locale được chọn phải dễ quan sát

Hệ thống nên có trace/log hợp lý:

~~~text
requested=fr-CA
selected=fr
bundle=fr
fallbackKey=status (ROOT)
policyVersion=ui-locales-v3
~~~

Đây là **định dạng log minh họa**. Không log Accept-Language, user ID hoặc dữ liệu nhạy cảm vô hạn; ghi metadata cần thiết theo chính sách. Chỉ số fallback theo locale/key giúp nhóm bản địa hóa phát hiện thay đổi hành vi sau release.

**Với named modules**, cơ chế cache/provider và mức độ khả dụng của Control cần được thiết kế dựa trên module API, không lấy toàn bộ mã classpath rồi dùng nguyên xi.

## 13. HTTP caching và SEO khi chọn theo ngôn ngữ

Nếu server trả HTML theo `Accept-Language`, một reverse proxy/CDN có thể cache response đầu tiên rồi trả nhầm ngôn ngữ cho người dùng sau nếu cache key không phân biệt ngôn ngữ.

**Các hướng thiết kế:**

- Với trang chọn locale dựa trên request header, cân nhắc `Vary: Accept-Language` theo HTTP caching policy. Nhưng nhiều tổ hợp header có thể làm cache phân mảnh.
- Với ứng dụng có URL rõ locale như `/vi/...`, `/en/...`, cấu hình cache theo route dễ dự đoán hơn.
- Gắn `Content-Language` phù hợp khi response có ngôn ngữ chính xác định.
- Với trang công khai nhiều ngôn ngữ, dùng canonical/hreflang và route policy phù hợp, không chỉ thay text trên trang nhưng giữ một URL/cache duy nhất.
- Nếu ngôn ngữ được lưu trong account/cookie, cache cần xét **dữ liệu user-specific** và không để lộ response cá nhân.

**Không để locale fallback là nguyên nhân cross-user data leakage.** Dù ngôn ngữ là dữ liệu hiển thị, nếu caching nhầm cả thông tin cá nhân của user trước, hậu quả vượt xa vấn đề dịch thuật.

## 14. Một số lựa chọn về script và locale theo ứng dụng

### 14.1. Chinese: zh-Hans và zh-Hant

Đối với hai script chính, ứng dụng có thể duy trì bundle `zh_Hans` và `zh_Hant` riêng. Một người chọn `zh-Hant-HK` có thể fallback đến `zh-Hant`; nhưng fallback sang `zh-Hans` không nhất thiết phù hợp. Nếu không có bản thích hợp, dùng ngôn ngữ mặc định hoặc hỏi người dùng theo policy thay vì đưa ra nội dung đọc khó.

### 14.2. Portuguese: pt-BR và pt-PT

Một ứng dụng e-commerce có thể có `pt-BR` trước, rồi bổ sung `pt-PT`. Không tự mặc định mọi thông báo thuế, thanh toán hoặc chính sách trả hàng có thể dùng bản của quốc gia kia. Có thể fallback UI labels nhưng tách legal copy.

### 14.3. Một locale chung có thể đủ cho một số màn hình

Nếu tiếng Việt của sản phẩm chưa có biến thể `vi-VN` và `vi`, một bundle `Messages_vi` có thể phục vụ request `vi-VN`. Không nhất thiết tạo tệp cho mọi tổ hợp language-region nếu nội dung thực sự giống nhau.

### 14.4. Giữ đúng chiều chữ và accessibility

Một locale dùng hệ chữ phải-sang-trái như `ar`/`he` có thể cần layout direction, bidi isolation, fonts, keyboard accessibility và định dạng phù hợp. Dùng bản fallback tiếng Anh không tự sửa layout RTL hoặc cách hiển thị tên/ngày/đơn vị. Localization cần test **toàn bộ trải nghiệm**, không chỉ nội dung string.

## 15. Các lỗi thường gặp trong thiết kế fallback

### Lỗi 1 — Lấy Locale.getDefault() làm locale người dùng

Server có nhiều user trong cùng JVM. Default locale thuộc process, không phải từng user. Chọn locale rõ trên request/session và truyền xuống service.

### Lỗi 2 — Dùng Locale.setDefault cho từng request

Đây là trạng thái global; request có thể ảnh hưởng lẫn nhau. Chỉ dùng tạm trong test một process đã kiểm soát (và khôi phục finally), không làm policy trong ứng dụng đa luồng.

### Lỗi 3 — Cho rằng ResourceBundle luôn về ROOT trước JVM default

Chiến lược mặc định có thể thử **default locale JVM** trước khi trả base bundle khi không có match ở requested locale. Nếu muốn policy khác, negotiate rõ và dùng Control trong phạm vi hợp lệ hoặc provider khác.

### Lỗi 4 — Hiểu getNoFallbackControl là “không fallback”

Nó chỉ chặn fallback **sang default JVM**; vẫn có candidate locales và ROOT. Nếu muốn reject mọi fallback vùng/key, cần policy riêng và validation/tài nguyên phù hợp.

### Lỗi 5 — Sử dụng Control trong named module

Trong Java 9+, ResourceBundle.Control overload bị hạn chế ở named modules và có thể ném UnsupportedOperationException. Hãy dùng cơ chế provider/module được hỗ trợ thay vì copy code classpath.

### Lỗi 6 — Dùng containsKey để kết luận file bản dịch đã hoàn chỉnh

`containsKey` bao gồm parent chain. Nó không cho biết key được dịch trong locale hiện hành; so raw resources ở build step.

### Lỗi 7 — Dùng getLocale để kết luận mọi key đều từ cùng một ngôn ngữ

`getLocale()` cho biết **bundle được chọn**, không cho biết resource cha nào cung cấp mỗi khóa. Một trang có thể trộn `fr` và ROOT.

### Lỗi 8 — Chọn locale từ getAvailableLocales thay vì bản dịch ứng dụng

JDK biết nhiều locale để định dạng không đồng nghĩa sản phẩm có message bundle. Dùng danh sách được sản phẩm hỗ trợ.

### Lỗi 9 — Đoán fallback giữa scripts/regions mà không hỏi product

`zh-Hans` và `zh-Hant` khác script; một số nội dung `fr-CA` và `fr-FR` khác pháp lý. Chính sách cần dựa vào nhu cầu sử dụng.

### Lỗi 10 — Coi Locale.ROOT là tên khác của en

ROOT là locale rỗng; ngôn ngữ thực của base bundle do nội dung ứng dụng quyết định. Nếu dùng English root, ghi rõ đó là policy.

### Lỗi 11 — Quên set locale cho MessageFormat

`MessageFormat.format(pattern,args)` tiện dùng nhưng có thể dựa vào locale mặc định trong quá trình format. Trên server, tạo `new MessageFormat(pattern, selectedLocale)` để nhất quán với user.

### Lỗi 12 — Dùng một MessageFormat mutable instance chung nhiều thread

`MessageFormat` không mặc định thread-safe. Tạo instance theo request hoặc quản lý concurrency đúng.

### Lỗi 13 — Dùng default locale chọn cả currency và timezone

Ngôn ngữ UI không cho biết currency giao dịch hoặc ZoneId user. Tách display locale, money currency, calendar/timezone theo miền.

### Lỗi 14 — Bỏ qua thay đổi CLDR/JDK locale data

Các kiểu dấu câu, format số/ngày có thể thay đổi khi nâng JDK/CLDR. Test theo semantics hoặc kiểm soát môi trường khi snapshot text chính xác thực sự quan trọng.

### Lỗi 15 — Lưu .properties tiếng Việt UTF-8 rồi chạy Java 8 mặc định

Java 8 đọc property resource bundle theo ISO-8859-1, khác Java 9+ mặc định UTF-8. Dùng escapes/loader phù hợp khi phải hỗ trợ Java 8; trên JDK hiện đại xác nhận tệp UTF-8 đúng.

### Lỗi 16 — Bắt MissingResourceException rồi luôn trả chính tên key

Người dùng có thể thấy một mã kỹ thuật khó hiểu. Với production, có fallback message/telemetry rõ và kiểm thử không thiếu key bắt buộc.

### Lỗi 17 — Không validate placeholder khi fallback

Bản dịch có thể thiếu `{0}` hoặc đảo tham số sai ngữ nghĩa. QA MessageFormat/ICU pattern theo từng locale.

### Lỗi 18 — Cache response không phân biệt ngôn ngữ

Khi dùng `Accept-Language`/cookie nhưng CDN cache chung, user có thể thấy sai ngôn ngữ hoặc dữ liệu người khác. Thiết kế Vary/cache keys và privacy hợp lý.

### Lỗi 19 — Cho rằng truyền Locale.forLanguageTag là validate ngôn ngữ được hỗ trợ

Một Locale object không chứng minh app có resource. Phải so với allowlist và áp dụng policy.

### Lỗi 20 — Mặc định missing legal translation có thể fallback giống nút UI

Nội dung pháp lý và xác nhận có thể cần bản dịch đúng vùng/đã phê duyệt; không tự lấy văn bản nước khác chỉ vì cùng ngôn ngữ.

### Lỗi 21 — Không giới hạn header Accept-Language

Request có thể quá dài hoặc sai cú pháp; cần giới hạn resource và exception policy thay vì parse tùy ý. Không ghép header trực tiếp thành resource class/path.

### Lỗi 22 — Dùng ngôn ngữ của bản dịch làm tín hiệu quyền truy cập

Locale là preference hiển thị; không phải role, tenant authorization, data residency hoặc giấy phép pháp lý. Những điều kiện ấy cần dữ liệu chính sách độc lập.

## 16. Thiết kế unit test cho fallback policy

| Trường hợp | Input/fixture | Điều phải được bảo đảm |
| --- | --- | --- |
| Đúng một locale hỗ trợ | `en-GB` | Chọn `en-GB` và bundle vùng nếu có |
| Vùng chưa có bundle | `fr-CA`, có `fr` | Chọn `fr` theo policy, không vô tình chọn một ngôn ngữ khác |
| Locale không hỗ trợ | `de-DE`, app default `en` | Chọn `en` theo policy |
| Không có header | null/blank | Chọn default ứng dụng |
| Header sai | `fr;q=oops` | Không crash; fallback app |
| q-weighted preferences | `fr-CA, en-US;q=0.8` | Tôn trọng chính sách ưu tiên |
| Key thiếu ở child | `status` thiếu trong `fr` nhưng có ROOT | Trả giá trị ROOT, ghi nhận fallback nếu cần |
| Key không có mọi bundle | `unknown-key` | Xử lý `MissingResourceException` theo policy |
| JVM default khác | JVM `fr`, requested `de-DE` | Không làm ứng dụng tự sai policy |
| Script khác | `zh-Hant` và `zh-Hans` | Không hoán đổi thiếu kiểm chứng |
| Tiền tệ/múi giờ | UI `en`, VND, `Asia/Ho_Chi_Minh` | Không suy currency/zone từ UI |
| Missing legal text | key thuộc loại bắt buộc | Fail closed/đánh dấu không khả dụng theo policy |
| Named module | module-info và ResourceBundle provider | Không dùng Control overload bị cấm |
| UTF-8 source trên JDK8 | .properties có dấu tiếng Việt | Biên dịch/tải đúng encoding |
| Hot reload translations | nhiều request + cache | Có chiến lược phiên bản/invalidations rõ |
| HTTP cache | request khác Accept-Language | Không trả nhầm bản dịch/dữ liệu user |

### 16.1. Test không nên dùng trạng thái máy làm expected

Một bài test chỉ chạy trên laptop có JVM default English có thể pass tình cờ vì fallback ngầm trùng policy. Để test nghiêm túc, hãy chạy thêm ít nhất một trường hợp default JVM khác, nhưng **không thay đổi Locale.setDefault giữa các test chạy song song** mà không cô lập tiến trình.

Có thể truyền locale tường minh hoặc chạy từng test JVM riêng với cấu hình locale kiểm soát. Demo đã thực hiện thay đổi trong `try/finally` trên một process riêng để bảo đảm stdout ổn định.

### 16.2. Test cả ngôn ngữ được chọn và nội dung thực tế

`assert selectedLocale == Locale.FRENCH` chưa chứng minh `bundle.getString("key")` thật sự tiếng Pháp; key có thể nằm ở ROOT. Test hai tầng:
1. Negotiation chọn locale đúng.
2. Catalog có đúng key/bản dịch và fallback hợp lệ theo product spec.

Khi chất lượng bản dịch quan trọng, cần test bản dịch từ chính resource file/source of truth, không chỉ dùng API `containsKey` đã kế thừa.

## 17. Checklist triển khai production

- [ ] Danh sách locale sản phẩm hỗ trợ được quản lý và kiểm thử độc lập với JDK available locales?
- [ ] Có định nghĩa rõ ưu tiên locale của account, request override, browser, tenant và app default?
- [ ] Có parse `Accept-Language` với weights, giới hạn độ dài và xử lý lỗi?
- [ ] Có dùng `Locale.lookup/filter` đúng mục tiêu và xử lý kết quả `null`?
- [ ] Có phân biệt locale đã **được app chọn** với locale bundle **thực tế load**?
- [ ] Có hiểu thứ tự region → language/script → ROOT và những trường hợp đặc biệt?
- [ ] Có ngăn việc fallback ngầm sang default JVM khi policy yêu cầu deterministic?
- [ ] Nếu dùng `ResourceBundle.Control`, ứng dụng có chạy trên unnamed module/classpath phù hợp?
- [ ] Nếu dùng named modules, đã kiểm tra `ResourceBundleProvider` và cách đóng gói/encapsulation?
- [ ] `getLocale` và `containsKey` có bị dùng sai để kết luận nguồn của từng key?
- [ ] Base bundle/ROOT có đủ các khóa bắt buộc, và language bundles có QA độ phủ?
- [ ] Có chính sách rõ cho missing keys: fallback, telemetry, không khả dụng hay fail closed?
- [ ] Nội dung pháp lý, bảo mật, thanh toán có fallback riêng theo vùng/phiên bản?
- [ ] Các placeholders MessageFormat/ICU có tương thích giữa các locale?
- [ ] Có truyền locale rõ cho `MessageFormat` và không share mutable formatter không an toàn?
- [ ] Có tách UI locale với NumberFormat, Currency, ZoneId và dữ liệu miền?
- [ ] Các resources `.properties` có encoding hợp với JDK thực tế (Java 8 vs JDK9+)?
- [ ] Nếu có hot reload, đã xác định cache TTL/invalidation thay vì tin tệp mới tự được load?
- [ ] Có telemetry phân biệt requested, negotiated, bundle và key-level fallback?
- [ ] Có test locale có script khác, RTL, text dài, định dạng số/ngày và font?
- [ ] HTTP response theo ngôn ngữ có cache key/`Vary`/`Content-Language` phù hợp?
- [ ] Có tránh dùng locale/header như tín hiệu authorization hoặc data-residency?
- [ ] Có integration test khi nâng JDK/CLDR và khi cập nhật bản dịch?

**Kết luận:** Fallback không phải một cờ bật/tắt chung. Ứng dụng cần **chọn locale theo một chính sách rõ** (và danh sách supported), rồi dùng `ResourceBundle` để tìm tài nguyên theo mức độ cụ thể của language/script/region và parent chain, **kiểm soát fallback sang JVM default** khi nó trái với nhu cầu. Khóa dịch thiếu, nội dung pháp lý, việc định dạng số/ngày, currency/timezone và HTTP caching cần chính sách riêng. `Locale.lookup`, `Locale.LanguageRange` và `ResourceBundle` tiếp tục là các API Java hiện hành; điều quyết định chất lượng là quy tắc ứng dụng, chất lượng bản dịch và kiểm thử đúng các cấp fallback.

## Tài liệu chính thức và chuẩn

- [Oracle Java SE 26 — Locale: BCP 47, RFC 4647 lookup/filter, language tags](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html)
- [Oracle Java SE 26 — Locale.LanguageRange: parse weighted language preferences](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Oracle Java SE 26 — ResourceBundle: candidate locales, parent chain, default fallback, cache, getLocale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle Java SE 26 — ResourceBundle.Control: getNoFallbackControl và giới hạn trong named modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [Oracle Java SE 26 — ListResourceBundle: bundle classes cho ví dụ độc lập](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ListResourceBundle.html)
- [Oracle Java SE 26 — MessageFormat và quy tắc định dạng tham số](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle Java SE 26 — PropertyResourceBundle: Unicode/UTF-8 và encoding](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Oracle — Internationalization Enhancements in JDK 9: property bundles mặc định UTF-8](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-9.htm)
- [Oracle Java SE 26 — ResourceBundleProvider cho named modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647)
- [MDN — Accept-Language header, q weights và HTTP content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept-Language)
