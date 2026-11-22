# Danh sách ứng viên theo language, script, region và variant

## 1. Bài toán: một bản dịch có nhiều mức độ cụ thể

Một ứng dụng Java thường có nhiều tập tài nguyên, ví dụ:

```text
Messages.properties
Messages_en.properties
Messages_en_US.properties
Messages_en_Latn.properties
Messages_en_Latn_US.properties
Messages_en_Latn_US_POSIX.properties
```

Nếu người dùng yêu cầu locale `en-Latn-US-POSIX` nhưng ứng dụng chưa có bundle đúng tuyệt đối, Java phải xác định **những bundle nào có thể thay thế và thứ tự thử chúng**. Đó là mục đích của **danh sách ứng viên (candidate locales)** trong cơ chế `java.util.ResourceBundle`.

Mục tiêu bài học:

- Hiểu vai trò và thứ tự của **language, script, region/country và variant** khi tìm `ResourceBundle`.
- Tự xem danh sách được sinh bởi `ResourceBundle.Control.getCandidateLocales(...)` và chuyển từng ứng viên thành tên bundle.
- Nhận ra hai nhánh quan trọng khi có script: ưu tiên nhánh **có script**, sau đó thử nhánh **không có script**.
- Phân biệt **candidate list**, **bundle thực sự tồn tại**, **parent-chain fallback của từng key** và **fallback sang JVM default locale**.
- Biết các ngoại lệ của Java như suy ra script cho tiếng Trung, biến thể nhiều phần, các mã tiếng Na Uy và việc bỏ qua Unicode extensions khi dựng candidate list.

Đây là kiến thức trong nhóm **Chuỗi dự phòng (fallback chain)**, tập trung vào quá trình tra cứu resource bundle. Các ứng viên không có nghĩa là tất cả những locale trong danh sách đều đã được cài đặt hoặc có bản dịch.

## 2. Thành phần của `Locale` liên quan tới candidate list

Xét một thẻ BCP 47 thông dụng:

```text
en-Latn-US-POSIX
│  │    │  │
│  │    │  └── variant
│  │    └───── region / country
│  └────────── script
└───────────── language
```

| Thành phần | API trong `Locale` | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Language (L) | `getLanguage()` | `en`, `vi`, `sr` | Ngôn ngữ |
| Script (S) | `getScript()` | `Latn`, `Cyrl`, `Hant` | Hệ chữ viết |
| Region / country (C) | `getCountry()` | `US`, `VN`, `TW` | Vùng lãnh thổ |
| Variant (V) | `getVariant()` | `POSIX`, `rozaj_biske` | Biến thể cụ thể |
| Extension | `getExtension(...)` hoặc Unicode extension API | `u-nu-thai` | Thông tin mở rộng; không tham gia danh sách ứng viên mặc định |

Thứ tự các thành phần trong tag BCP 47 không đồng nghĩa với việc chỉ xóa lần lượt từng subtag để có fallback. Java có quy tắc riêng: **nếu có script, sau khi thử nhánh có script sẽ thử lại nhánh chỉ gồm language + country + variant (không có script)**.

Các tên file `.properties` truyền thống dùng dấu gạch dưới (`_`), trong khi BCP 47 tag sử dụng dấu gạch nối (`-`). Chẳng hạn thẻ `sr-Latn-RS` tương ứng một ứng viên có tên file `Messages_sr_Latn_RS.properties`. Đừng truyền tên file đã gắn hậu tố `.properties` vào `Locale.forLanguageTag`.

## 3. Quy tắc thông thường khi không có script

Với locale có đầy đủ language, country, variant nhưng **script rỗng**, danh sách ứng viên mặc định có thứ tự:

```text
[L, C, V]  ->  [L, C]  ->  [L]  ->  ROOT
```

Ví dụ `en-US-POSIX`:

```text
en-US-POSIX  -> Messages_en_US_POSIX.properties
en-US        -> Messages_en_US.properties
en           -> Messages_en.properties
ROOT         -> Messages.properties
```

Nếu yêu cầu chỉ có `en-US` thì bỏ những ứng viên có variant; nếu chỉ có `en` thì chỉ còn `en` và `ROOT`. **Những ứng viên mà thành phần cuối rỗng sẽ bị bỏ qua**; Java không cần tạo một tên bundle như `Messages_en_.properties`.

`Locale.ROOT` là đối tượng locale có language/script/country/variant rỗng. Trong cơ chế bundle, nó đại diện cho **bundle gốc không có hậu tố locale** như `Messages.properties`. `Locale.ROOT.toString()` trả về chuỗi rỗng, nên khi debug cần tự đặt nhãn `ROOT` để tránh hiểu nhầm là một phần tử bị mất.

Nếu không có variant và region, hãy hình dung việc ưu tiên đi từ cụ thể tới tổng quát, nhưng **đừng suy diễn rằng `en-US` tự rơi về `en-GB`**: `en-GB` là một nhánh vùng khác, không nằm trên đường ứng viên mặc định của `en-US`.

## 4. Quy tắc khi có script: hai nhánh rõ ràng

Với locale gồm language (L), script (S), country (C), variant (V), danh sách mặc định là:

```text
[L, S, C, V]
      ↓
[L, S, C]
      ↓
[L, S]
      ↓
[L, C, V]    ← thử lại khi bỏ script, giữ region và variant
      ↓
[L, C]
      ↓
[L]
      ↓
ROOT
```

Ví dụ `en-Latn-US-POSIX`, lấy base name là `Messages`:

| Thứ tự | Candidate locale | Tên file bundle tương ứng |
| --- | --- | --- |
| 1 | `en-Latn-US-POSIX` | `Messages_en_Latn_US_POSIX.properties` |
| 2 | `en-Latn-US` | `Messages_en_Latn_US.properties` |
| 3 | `en-Latn` | `Messages_en_Latn.properties` |
| 4 | `en-US-POSIX` | `Messages_en_US_POSIX.properties` |
| 5 | `en-US` | `Messages_en_US.properties` |
| 6 | `en` | `Messages_en.properties` |
| 7 | `ROOT` | `Messages.properties` |

Lưu ý vị trí thứ tư: Java không bỏ thẳng từ `en-Latn` tới `en`. Nó **khôi phục region/variant trên nhánh không có script**. Vì vậy, có thể dùng bundle chung cho Mỹ như `Messages_en_US.properties` nếu thiếu tài nguyên chuyên biệt chữ Latin.

Với `sr-Latn-RS`, danh sách là:

```text
sr-Latn-RS
sr-Latn
sr-RS
sr
ROOT
```

Nhánh `sr-RS` có thể hữu ích khi ứng dụng có tài nguyên tiếng Serbia cho vùng Serbia nhưng chưa tách chữ Latin và Cyrillic. **Đây là cách Java tra cứu ứng viên**, không có nghĩa nội dung Cyrillic và Latin luôn thay thế an toàn cho nhau; ứng dụng cần quyết định bộ tài nguyên nào thực sự nên có.

## 5. Variant nhiều phần: bỏ dần từ phải sang trái

`Locale.getVariant()` có thể chứa nhiều phần ngăn bởi dấu `_`. Ví dụ đọc BCP 47 `sl-rozaj-biske` tạo language `sl` và variant có hai phần `rozaj`, `biske`. Khi sinh candidate list, Java thử **biến thể đầy đủ**, sau đó **biến thể rút gọn**, rồi mới bỏ hoàn toàn variant:

```text
sl-rozaj-biske  -> Messages_sl__rozaj_biske.properties
sl-rozaj        -> Messages_sl__rozaj.properties
sl              -> Messages_sl.properties
ROOT            -> Messages.properties
```

Tại sao tên file có **hai dấu gạch dưới** giữa `sl` và `rozaj`? Vì vị trí region trong quy ước `toBundleName` đang rỗng, nhưng variant vẫn có mặt. Việc `Locale.forLanguageTag("sl-rozaj-biske").toLanguageTag()` dùng dấu `-` **không làm thay đổi** quy ước đặt tên bundle Java bằng `_`.

Với nhiều thành phần cùng lúc, giả sử variant gồm `V1_V2`, script và region cũng có:

```text
L_S_C_V1_V2
L_S_C_V1
L_S_C
L_S
L_C_V1_V2
L_C_V1
L_C
L
ROOT
```

Hai nhánh đều ưu tiên phiên bản variant đầy đủ rồi rút gọn. **Không phải mọi chuỗi variant đều là BCP 47 hợp lệ:** các `Locale` được tạo từ constructor cũ có thể chứa variant theo quy tắc legacy. Khi tạo dữ liệu mới, ưu tiên `Locale.Builder` hoặc `Locale.forLanguageTag` với tag hợp lệ.

## 6. Java 17+: in chính xác candidate và tên bundle

Đoạn sau chạy độc lập trên classpath bằng JDK 17+. Nó sử dụng `ResourceBundle.Control` với danh sách định dạng mặc định để **quan sát thuật toán**, không cần có file `Messages.properties` thật.

Tạo file `CandidateLocalesDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class CandidateLocalesDemo {
    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getControl(
                    ResourceBundle.Control.FORMAT_DEFAULT);

    private static void show(String tag) {
        Locale requested = Locale.forLanguageTag(tag);
        List<Locale> candidates =
                CONTROL.getCandidateLocales("Messages", requested);

        System.out.println(tag + ":");
        for (Locale candidate : candidates) {
            String display = candidate.equals(Locale.ROOT)
                    ? "ROOT"
                    : candidate.toLanguageTag();
            String bundleName =
                    CONTROL.toBundleName("Messages", candidate);
            System.out.println("  " + display
                    + " -> " + bundleName + ".properties");
        }
    }

    public static void main(String[] args) {
        show("en-Latn-US-POSIX");
        show("zh-TW");
        show("sl-rozaj-biske");
    }
}
```

Biên dịch và chạy:

```bash
javac CandidateLocalesDemo.java
java CandidateLocalesDemo
```

Kết quả trên JDK tiêu chuẩn:

```text
en-Latn-US-POSIX:
  en-Latn-US-POSIX -> Messages_en_Latn_US_POSIX.properties
  en-Latn-US -> Messages_en_Latn_US.properties
  en-Latn -> Messages_en_Latn.properties
  en-US-POSIX -> Messages_en_US_POSIX.properties
  en-US -> Messages_en_US.properties
  en -> Messages_en.properties
  ROOT -> Messages.properties
zh-TW:
  zh-Hant-TW -> Messages_zh_Hant_TW.properties
  zh-Hant -> Messages_zh_Hant.properties
  zh-TW -> Messages_zh_TW.properties
  zh -> Messages_zh.properties
  ROOT -> Messages.properties
sl-rozaj-biske:
  sl-rozaj-biske -> Messages_sl__rozaj_biske.properties
  sl-rozaj -> Messages_sl__rozaj.properties
  sl -> Messages_sl.properties
  ROOT -> Messages.properties
```

`getCandidateLocales` trả các đối tượng `Locale`, không phải tên file. `toBundleName` biến mỗi candidate thành tên bundle dạng gạch dưới; trong ví dụ thêm `.properties` để minh họa một định dạng file khả dĩ. `FORMAT_DEFAULT` còn cho phép `java.class`; một tên candidate có thể được ứng với class bundle hoặc properties bundle, và thứ tự tìm định dạng cũng ảnh hưởng bundle thực sự được tải.

Đây là API hỗ trợ quan sát thuật toán rõ ràng trong ứng dụng **classpath/unnamed module**. Trong ứng dụng Java đóng gói thành **named module**, một số overload `ResourceBundle.getBundle` với `Control` không được hỗ trợ như cơ chế classpath; hãy tuân theo quy tắc module/service provider dành cho resource bundle. Ví dụ trên chỉ gọi `Control.getCandidateLocales` để minh họa thứ tự, không cần tự viết loader.

## 7. Ngoại lệ quan trọng: script có thể được suy ra cho tiếng Trung

Với language `zh` và **script rỗng**, `ResourceBundle.Control` mặc định có quy tắc đặc biệt:

- Region `CN` hoặc `SG`: bổ sung script `Hans` (giản thể).
- Region `TW`, `HK` hoặc `MO`: bổ sung script `Hant` (phồn thể).
- Region khác hoặc không có region: không tự bổ sung script theo quy tắc này.

Vì vậy, `Locale.forLanguageTag("zh-TW")`, dù `getScript()` của locale đầu vào rỗng, sinh candidate list:

```text
zh-Hant-TW
zh-Hant
zh-TW
zh
ROOT
```

Tương tự, `zh-CN` có thể sinh:

```text
zh-Hans-CN
zh-Hans
zh-CN
zh
ROOT
```

Đây là **đặc lệ của thuật toán chọn bundle**. Nó không có nghĩa chính đối tượng `Locale.forLanguageTag("zh-TW")` đã được sửa để chứa `Hant`, cũng không cho phép suy script cho mọi ngôn ngữ bằng mã quốc gia. Khi dự đoán chuỗi fallback thực tế, hãy ưu tiên kết quả của `getCandidateLocales` thay vì suy luận tự động từ nhãn BCP 47.

## 8. Các trường hợp đặc biệt khác: Norwegian và extensions

### 8.1. Các mã `nn`, `nb` và `no`

Java có logic tương thích lịch sử cho các dạng tiếng Na Uy. Với `nn-NO` (Nynorsk), candidate list mặc định bao gồm cả một số tên `no` cũ:

```text
Messages_nn_NO
Messages_nn
Messages_no_NO_NY
Messages_no_NO
Messages_no
Messages
```

Với `nb-NO` (Bokmål), mã `nb` và đồng nghĩa lịch sử `no` được xen kẽ:

```text
Messages_nb_NO
Messages_no_NO
Messages_nb
Messages_no
Messages
```

Danh sách này nhằm tương thích tên tài nguyên đã có và không được suy rộng thành quy tắc mọi language code đều có synonym. Trong hệ thống mới, đặt tên tài nguyên nhất quán và kiểm tra đúng JDK được triển khai.

### 8.2. Unicode extensions không làm tăng số mức bundle mặc định

Ví dụ:

```text
en-US-u-nu-thai
```

Có Unicode extension yêu cầu chữ số Thái (`nu=thai`), nhưng danh sách ứng viên của `ResourceBundle.Control` mặc định vẫn là:

```text
en-US
en
ROOT
```

Nó không sinh `Messages_en_US_u_nu_thai.properties`. Extension có thể quan trọng với bộ định dạng số/lịch, nhưng **không được sử dụng trong quy tắc sinh tên ResourceBundle mặc định**. Nếu bộ tài nguyên cần phân biệt nội dung theo extension, ứng dụng phải thiết kế key/lookup riêng hoặc một cơ chế tùy biến phù hợp.

## 9. Candidate list khác với kết quả tìm bundle thực tế

Ba khái niệm liên quan nhưng khác nhau:

1. **Candidate locale:** một locale Java *có thể* thử. `getCandidateLocales` chỉ lập danh sách dựa trên quy tắc; không đọc file để kiểm tra bundle có tồn tại hay không.
2. **Resource bundle được chọn:** bundle thực sự được tìm thấy theo thứ tự tìm kiếm và định dạng hỗ trợ. Nếu ứng viên đầu không có file/class, Java tiếp tục với ứng viên kế tiếp.
3. **Parent chain / key fallback:** sau khi chọn bundle, `ResourceBundle.getString(key)` có thể lấy giá trị từ bundle cha nếu bundle con không khai báo key tương ứng. Điều này khác với việc tự đổi locale theo từng key.

Giả sử chỉ có:

```text
Messages.properties             -> hello=Default
Messages_en.properties          -> hello=Hello; help=Help
Messages_en_Latn_US.properties  -> hello=Howdy
```

Với yêu cầu `en-Latn-US-POSIX`, `Messages_en_Latn_US` là candidate đầu tiên tồn tại (do bundle `POSIX` chưa có), nên:

- `hello` lấy ở `Messages_en_Latn_US`: `Howdy`.
- `help` không có ở bundle cụ thể nhưng có trong parent `Messages_en`: `Help`.
- Một key chỉ có ở `Messages.properties` có thể được lấy từ root parent, nếu chuỗi cha phù hợp.

Các tên và giá trị trên là **tình huống minh họa**, không phải file đã tồn tại trong project. Khi đánh giá runtime, cần chú ý classpath/module, `Control`, cache và việc resource bundle có tự thiết lập parent hay không.

### Nếu ngay cả locale cụ thể cũng không có bundle thì sao?

Theo `ResourceBundle.Control` mặc định, `getFallbackLocale(baseName, requestedLocale)` thường trả **JVM default locale** nếu nó khác requested locale, hoặc `null` nếu bằng nhau. Trong tìm kiếm bình thường, nếu chỉ tìm được root bundle, root có thể được **giữ lại tạm thời** để thử fallback theo default locale trước khi quyết định dùng root. Do đó:

- `getCandidateLocales("Messages", requested)` **không bao gồm** dãy ứng viên của JVM default locale.
- `getBundle(...)` có thể thử thêm một **vòng candidate list mới** từ default locale nếu không tìm được bundle bản địa hóa thích hợp cho requested locale.
- Nếu có một bundle không phải root phù hợp với requested locale, nó được chọn, và tra cứu key thiếu đi theo parent chain thay vì tự chuyển sang một ngôn ngữ mặc định khác cho mỗi key.

Ví dụ application yêu cầu `fr-CA`, nhưng không có `Messages_fr_CA` hay `Messages_fr`; Java có thể thử chuỗi default như `en-US → en → ROOT` trước khi trả root (nếu có) hoặc ném `MissingResourceException` (nếu không tìm được bundle nào). Không thể suy ra kết quả cuối chỉ từ candidate list; phải biết bundle nào hiện diện, môi trường default, loader và chính sách fallback.

**Đừng gọi `Locale.setDefault(...)` trên mỗi request để ép fallback:** default là trạng thái dùng chung trong JVM, thay nó giữa các request có thể gây xung đột. Nếu server cần fallback cố định, ứng dụng nên chọn rõ locale/chuỗi ưu tiên và truyền explicit vào hàm tra cứu hoặc triển khai chính sách resource lookup có kiểm soát.

## 10. Cách dự đoán tên file và kiểm tra lỗi

Để phân tích một lỗi "đã có file nhưng Java không dùng":

1. **Xác nhận base name**: `Messages`, `com.example.i18n.Messages`... Base name xác định đường dẫn package tương ứng, không phải đường dẫn chứa `.properties` tự do.
2. **Xác nhận requested locale**: in `toLanguageTag()` và các getter `getLanguage()`, `getScript()`, `getCountry()`, `getVariant()`.
3. **In candidate list** bằng `ResourceBundle.Control.getCandidateLocales` trong trường hợp dùng quy tắc classpath mặc định.
4. **In tên bundle tương ứng** qua `Control.toBundleName`. Đừng tự đoán script/variant hay bỏ dấu `_` kép trong tên file.
5. **Xác nhận file/class thật sự hiện diện** đúng package và classpath/module path; phân biệt chữ hoa/thường trên hệ thống file.
6. **Xác nhận default locale và chính sách fallback**, nhất là khi chỉ có root hoặc bundle của một ngôn ngữ khác.
7. **Xác nhận key và parent chain**. Không tìm thấy bundle và không tìm thấy key là hai lỗi khác nhau.
8. **Lưu ý cache** của `ResourceBundle` khi vừa cập nhật tài nguyên: kết quả có thể phụ thuộc loader/cache; khi cần reload hãy dùng API cache phù hợp trong môi trường phát triển.

Ví dụ lỗi đặt tên phổ biến:

| Tên viết | Vấn đề |
| --- | --- |
| `Messages_zh_TW_Hant.properties` | Đặt sai thứ tự script/region so với `toBundleName`; Java có thể tìm `Messages_zh_Hant_TW.properties` |
| `Messages_en-US.properties` | Dùng dấu `-` của tag thay vì dấu `_` trong tên bundle |
| `Messages_sl_rozaj_biske.properties` | Thiếu vị trí region rỗng khi variant có mặt; theo mặc định cần `Messages_sl__rozaj_biske.properties` |
| `Messages_en_US_u_nu_thai.properties` | Mong Unicode extension trở thành một mức candidate mặc định |
| Chỉ tạo `Messages_en_GB` rồi yêu cầu `en-US` | `en-GB` không tự là candidate của `en-US` |

## 11. Tự kiểm tra

1. Với locale `en-US`, các ứng viên theo thứ tự là gì? **`en-US → en → ROOT`**.
2. Với `sr-Latn-RS`, vì sao `sr-RS` xuất hiện sau `sr-Latn`? **Java thử nhánh có script trước, rồi nhánh không có script và phục hồi region/variant**.
3. Với `sl-rozaj-biske`, tại sao tên file bundle chứa `sl__rozaj`? **Region rỗng, variant vẫn có; quy ước tên bundle giữ vị trí này bằng dấu `_` thứ hai**.
4. Vì sao `zh-TW` sinh candidate `zh-Hant-TW` dù tag ban đầu không có `Hant`? **Quy tắc bổ sung script đặc biệt cho tiếng Trung theo region**.
5. Có thể coi `getCandidateLocales` là bằng chứng tất cả file tương ứng đều tồn tại không? **Không**; nó chỉ sinh tên ứng viên.
6. Nếu bundle `Messages_en` có `help` còn `Messages_en_Latn_US` không có key đó, cách tìm là gì? **Tra qua parent chain, có thể lấy `help` từ `Messages_en`**.
7. `en-US-u-nu-thai` có candidate bundle dành riêng `nu-thai` không? **Không theo `Control` mặc định**.
8. Khi thiếu mọi bundle dành cho requested locale, vòng thử JVM default locale có nằm sẵn trong danh sách `getCandidateLocales(requested)` không? **Không**; đó là bước fallback bổ sung của quá trình `getBundle`.

## Tài liệu tham khảo

- [Java SE 21 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.Control.html): `getCandidateLocales`, `toBundleName`, `getFallbackLocale` và các ngoại lệ cho tiếng Trung/Na Uy.
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): chiến lược tìm bundle, parent chain, cache và fallback.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): các thành phần language/script/country/variant và `toLanguageTag`.
