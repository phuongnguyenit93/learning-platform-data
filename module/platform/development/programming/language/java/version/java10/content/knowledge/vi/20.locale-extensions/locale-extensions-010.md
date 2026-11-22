# Kết hợp nhiều phần mở rộng trong cùng một `Locale` (Java 10+)

## 1. Tổng quan và mục tiêu

`java.util.Locale` không chỉ xác định ngôn ngữ (`language`) và vùng (`region`). Theo chuẩn thẻ ngôn ngữ **IETF BCP 47**, một Locale còn có thể mang **extensions** — các phần mở rộng mô tả lựa chọn đặc thù về lịch, chữ số, tiền tệ, quy tắc tuần, vùng ưu tiên và múi giờ.

Ví dụ, ứng dụng muốn giữ ngôn ngữ tiếng Anh và vùng cơ sở Hoa Kỳ, nhưng yêu cầu:
- Hệ lịch Gregorian;
- Hệ chữ số Latin;
- Tiền tệ Euro;
- Ngày bắt đầu tuần là thứ Hai;
- Quy tắc vùng ưu tiên từ Vương quốc Anh;
- Múi giờ tương ứng New York.

Những lựa chọn này có thể được ghi **đồng thời trong cùng một Locale**, chẳng hạn:

~~~text
en-US-u-ca-gregory-cu-eur-fw-mon-nu-latn-rg-gbzzzz-tz-usnyc
~~~

Đây là **một thẻ BCP 47**, không phải sáu Locale riêng. Sau khi học, bạn có thể:
1. Hiểu vì sao một **Unicode locale extension `u`** chứa được nhiều cặp **key–type**.
2. Phân biệt nhiều keyword trong `u` với nhiều extension singleton như `u` và `x`.
3. Dùng `Locale.Builder`, `Locale.forLanguageTag`, `toLanguageTag` để tạo, đọc và cập nhật đúng.
4. Không làm mất các keyword cũ khi thêm một lựa chọn mới.
5. Hiểu giới hạn: **Locale lưu tùy chọn không đồng nghĩa mọi API định dạng đều hỗ trợ tùy chọn đó**.
6. Viết và kiểm thử mã Java 17+ biên dịch, chạy độc lập.

### Mốc phiên bản cần phân biệt

**Java 10** có cải tiến **JEP 314 — Additional Unicode Language-Tag Extensions**: mở rộng việc hỗ trợ trong các lớp JDK có liên quan đối với `cu` (currency), `fw` (first day of week), `rg` (region override) và `tz` (time zone). Trước đó, các lựa chọn như `ca` (calendar) và `nu` (numbering) đã được hỗ trợ.

Bản thân `Locale.Builder`, thẻ BCP 47, `Locale.forLanguageTag` và cơ chế các extension **không phải API lần đầu được thêm vào Java 10**; chúng đã có từ Java 7. Các ví dụ và quy tắc trong bài vẫn áp dụng trong Java hiện đại. Chương trình đầy đủ sử dụng **JDK 17+** và không cần tính năng preview.

## 2. Cấu trúc BCP 47 và hai cấp độ mở rộng

Một thẻ ngôn ngữ có thể gồm:

~~~text
language[-Script][-REGION][-variants...][-extensions...]
~~~

Ví dụ:

~~~text
en-US-u-ca-gregory-nu-latn
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `en` | Language: tiếng Anh |
| `US` | Region: Hoa Kỳ |
| `u` | Singleton biểu thị **Unicode locale extension** |
| `ca-gregory` | Unicode keyword: calendar kiểu Gregorian |
| `nu-latn` | Unicode keyword: numbering system Latin |

**Điểm quan trọng:** `ca` và `nu` là **hai keyword trong cùng một extension `u`**. Không cố tạo hai extension `u` bằng cách viết một thẻ như `en-US-u-ca-gregory-u-nu-latn`. Việc lặp singleton như vậy không phải cách hợp lệ để kết hợp keyword.

Ngoài Unicode extension `u`, thẻ có thể có **extension singleton khác**. Ví dụ:

~~~text
en-US-u-ca-gregory-nu-latn-x-training
~~~

- `u` chứa hai keyword `ca`, `nu`.
- `x` là singleton **private use**, có giá trị `training`.
- Phần `x-training` độc lập về mặt cấu trúc với các Unicode keyword.
- Private use chỉ có nghĩa theo quy ước giữa các bên. Java **không tự thay đổi lịch, tiền tệ hoặc múi giờ** chỉ vì có `x-training`.
- Thẻ BCP 47 thường biểu diễn private use `x` ở phần cuối.

Do đó, khi nói “kết hợp nhiều phần mở rộng”, cần phân biệt:
- **Kết hợp nhiều key/type trong một `u`**, ví dụ `ca`, `nu`, `cu`, `fw`, `rg`, `tz`.
- **Kết hợp nhiều singleton extension trong một Locale**, ví dụ có cả `u` và `x`.

Một Locale có thể mang cả hai cấp độ mà không cần nối chuỗi thủ công.

## 3. Các Unicode locale keyword thường gặp

| Key | Ví dụ type | Mục đích | Bối cảnh |
| --- | --- | --- | --- |
| `ca` | `gregory`, `japanese` | Hệ lịch | Được hỗ trợ trước Java 10 trong API liên quan |
| `nu` | `latn`, `thai`, `arab` | Hệ chữ số | Được hỗ trợ trước Java 10 |
| `cu` | `eur`, `usd`, `jpy` | Tiền tệ ưu tiên | JEP 314 / Java 10 |
| `fw` | `mon`, `sun` | Ngày đầu tuần | JEP 314 / Java 10 |
| `rg` | `gbzzzz`, `uszzzz` | Ghi đè vùng áp dụng dữ liệu địa phương | JEP 314 / Java 10 |
| `tz` | `usnyc` | Mã Unicode của múi giờ | JEP 314 / Java 10 |

Các ví dụ là **type có ý nghĩa phổ biến**, không phải danh sách đầy đủ những giá trị đã đăng ký.

**Cần tránh hiểu sai ngữ nghĩa:**
- `cu-eur` có thể hướng API hỗ trợ đến tiền tệ EUR, nhưng **không đổi tỷ giá** giữa USD và EUR.
- `fw-mon` chọn thứ Hai làm đầu tuần với API lịch/tuần hỗ trợ, chứ không làm mọi ngày tháng tự thay đổi.
- `rg-gbzzzz` là gợi ý vùng cho dữ liệu locale; nó **không tự sửa trường `getCountry()`** của Locale cơ sở.
- `tz-usnyc` là mã Unicode time zone; nó **không phải** tên vùng `America/New_York` và không làm `ZoneId.systemDefault()` của JVM đổi theo.
- `nu-latn` yêu cầu hệ số Latin, nhưng không có cam kết rằng mọi formatter hoặc provider đều hiểu mọi type.

**Tính hiện hành:** những keyword bổ sung ở Java 10 tiếp tục được các JDK hiện đại hỗ trợ tại các điểm API phù hợp. Khi chuyển giữa runtime khác nhau, phải kiểm tra lớp tiêu thụ Locale và dữ liệu locale có sẵn thay vì giả định tất cả tương đương.

## 4. Tạo một Locale chứa nhiều keyword bằng `Locale.Builder`

`Locale.Builder` cung cấp phương thức **`setUnicodeLocaleKeyword(String key, String type)`**. Gọi nhiều lần với **key khác nhau** sẽ đưa các key/type vào cùng Unicode locale extension.

~~~java
import java.util.Locale;

Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("nu", "latn")
        .setUnicodeLocaleKeyword("ca", "gregory")
        .setUnicodeLocaleKeyword("cu", "eur")
        .setUnicodeLocaleKeyword("fw", "mon")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .setUnicodeLocaleKeyword("tz", "usnyc")
        .build();
~~~

Đây là **mã minh họa đặt trong phương thức**, không phải tệp Java độc lập. Mục 8 chứa chương trình hoàn chỉnh.

Các nguyên tắc:
1. `setLanguage("en")`, `setRegion("US")` đặt các trường cơ sở.
2. `setUnicodeLocaleKeyword` với các key **khác nhau** giữ các key đã thêm.
3. Gọi lại **cùng một key** sẽ **thay type** của key ấy.
4. `build()` tạo đối tượng `Locale` có thể được chia sẻ như một giá trị, không bị thay đổi từ các thao tác trên builder về sau.
5. Khi gọi `toLanguageTag()`, các Unicode keywords được chuẩn hóa, không phụ thuộc thứ tự gọi setter.

Ví dụ:

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag("en-US")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setUnicodeLocaleKeyword("ca", "gregory")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(locale.toLanguageTag());
// en-US-u-ca-gregory-nu-latn
~~~

Vì `nu` được gán lần hai, type cuối cùng là `latn`; `ca-gregory` vẫn còn.

### Thứ tự hiển thị sau chuẩn hóa

Hai đoạn dưới tạo Locale tương đương:

~~~java
Locale a = new Locale.Builder()
        .setLanguageTag("en-US")
        .setUnicodeLocaleKeyword("nu", "latn")
        .setUnicodeLocaleKeyword("ca", "gregory")
        .build();

Locale b = new Locale.Builder()
        .setLanguageTag("en-US")
        .setUnicodeLocaleKeyword("ca", "gregory")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(a.equals(b)); // true
System.out.println(a.toLanguageTag());
// en-US-u-ca-gregory-nu-latn
~~~

Thứ tự `ca` rồi `nu` là kết quả chuẩn hóa key, không do setter nào được gọi trước.

## 5. Đọc lại các phần mở rộng

Một Locale vừa biểu diễn cấu hình, vừa cho phép truy vấn chi tiết:

~~~java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-gregory-cu-eur-fw-mon-nu-latn");

System.out.println(locale.getLanguage());              // en
System.out.println(locale.getCountry());               // US
System.out.println(locale.getUnicodeLocaleType("ca")); // gregory
System.out.println(locale.getUnicodeLocaleType("cu")); // eur
System.out.println(locale.getUnicodeLocaleType("fw")); // mon
System.out.println(locale.getUnicodeLocaleType("nu")); // latn
System.out.println(locale.getUnicodeLocaleType("tz")); // null
~~~

**Ý nghĩa của các getter:**
- `getLanguage()`, `getCountry()` truy vấn trường cơ sở.
- `getUnicodeLocaleType(key)` trả **type của Unicode keyword**.
- Nếu keyword không có mặt, `getUnicodeLocaleType(key)` trả **`null`**.
- `getUnicodeLocaleKeys()` trả tập **các key Unicode** đang có.
- `getExtension(Locale.UNICODE_LOCALE_EXTENSION)` trả **toàn bộ giá trị extension `u`**, không bao gồm tiền tố `u-`.
- `getExtensionKeys()` trả tập các **singleton extension key** như `u`, `x`; không phải các Unicode key `ca` hoặc `nu`.
- `getUnicodeLocaleAttributes()` trả các Unicode attributes nếu có, khác với key/type.

Ví dụ:

~~~java
System.out.println(locale.getExtension(
        Locale.UNICODE_LOCALE_EXTENSION));
// ca-gregory-cu-eur-fw-mon-nu-latn

System.out.println(
        new java.util.TreeSet<>(locale.getUnicodeLocaleKeys()));
// [ca, cu, fw, nu]
~~~

Dùng `TreeSet` để in ổn định theo thứ tự chữ cái. **Không dựa vào thứ tự duyệt `Set` do `getUnicodeLocaleKeys()` trả về**.

### Đọc thẻ ngôn ngữ hoàn chỉnh

~~~java
String languageTag = locale.toLanguageTag();
System.out.println(languageTag);
// en-US-u-ca-gregory-cu-eur-fw-mon-nu-latn
~~~

Khi trao đổi cấu hình theo BCP 47, `toLanguageTag()` thường có ý nghĩa hơn `toString()`: dạng `Locale.toString()` có quy ước riêng của Java và không nên coi là định dạng BCP 47 chuẩn để trao đổi giữa hệ thống.

## 6. Kết hợp Unicode extension với private-use extension

Dùng `setExtension(char key, String value)` để đặt một singleton extension:

~~~java
Locale combined = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("cu", "eur")
        .setUnicodeLocaleKeyword("fw", "mon")
        .setExtension(Locale.PRIVATE_USE_EXTENSION, "training")
        .build();

System.out.println(combined.toLanguageTag());
// en-US-u-cu-eur-fw-mon-x-training

System.out.println(combined.getExtension(
        Locale.UNICODE_LOCALE_EXTENSION));
// cu-eur-fw-mon

System.out.println(combined.getExtension(
        Locale.PRIVATE_USE_EXTENSION));
// training
~~~

Ở đây `u` và `x` tồn tại đồng thời. `Locale.PRIVATE_USE_EXTENSION` là hằng singleton `'x'`; `Locale.UNICODE_LOCALE_EXTENSION` là `'u'`.

Về mặt thiết kế:
- `u` dành cho các Unicode locale keyword/attribute theo chuẩn.
- `x` dành cho private-use subtags mà các bên tự thống nhất.
- Đừng đưa thông tin bảo mật hay dữ liệu người dùng nhạy cảm vào `x` rồi coi thẻ Locale là một container bí mật.
- Việc `x-training` tồn tại **không tự làm thay đổi** `Currency`, `Calendar`, `NumberFormat`.

## 7. Cảnh báo quan trọng: các setter có phạm vi khác nhau

Đây là nơi nhiều chương trình vô tình **làm mất các keyword vừa cấu hình**.

### `setUnicodeLocaleKeyword`: thêm, cập nhật hoặc xóa một key

~~~java
Locale updated = new Locale.Builder()
        .setLocale(original)
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
~~~

`setLocale(original)` nạp cấu hình Locale hiện có; setter tiếp theo chỉ cập nhật một Unicode key `nu`. Các keyword khác được giữ lại. Nếu type là `null`, key tương ứng sẽ **bị xóa**.

### `setExtension('u',...)`: thay toàn bộ nội dung extension `u`

~~~java
Locale replaced = new Locale.Builder()
        .setLocale(original)
        .setExtension(Locale.UNICODE_LOCALE_EXTENSION, "nu-thai")
        .build();
~~~

Lệnh này **thay mọi Unicode locale keyword/attribute hiện có** bằng nội dung của `nu-thai`. Nếu trước đó có `ca-gregory`, `cu-eur`, `fw-mon`, chúng sẽ **bị xóa khỏi `u`**. Các singleton extension khác như `x` không tự bị xóa chỉ vì `u` được thay.

### `setLanguageTag` và `setLocale`: đặt lại Builder

~~~java
Locale.Builder builder = new Locale.Builder()
        .setUnicodeLocaleKeyword("nu", "thai");

builder.setLanguageTag("en-US");
// Keyword nu=thai đặt trước đã bị mất.
~~~

`setLanguageTag(tag)` **đặt lại builder theo toàn bộ tag đã cung cấp**, không chỉ thêm language và region. `setLocale(locale)` cũng đặt lại builder theo Locale được truyền. Khi muốn cập nhật, hãy nạp base trước, rồi mới chỉnh các key.

### `clearExtensions` khác `clear`

| Phương thức | Hiệu ứng |
| --- | --- |
| `setUnicodeLocaleKeyword("cu","eur")` | Đặt type của `cu`, giữ key khác |
| `setUnicodeLocaleKeyword("cu",null)` | Xóa riêng `cu` |
| `setExtension('u',"nu-thai")` | Thay toàn bộ Unicode extension |
| `setExtension('x',"training")` | Đặt private-use extension |
| `setExtension('x',null)` | Xóa riêng extension `x` |
| `clearExtensions()` | Xóa tất cả extension, **giữ language/script/region/variant** |
| `clear()` | Đặt toàn bộ builder về trạng thái rỗng |
| `setLocale(base)` | Đặt lại builder theo mọi thành phần của base |
| `setLanguageTag(tag)` | Đặt lại builder theo toàn bộ tag |

**Quy tắc thực hành:** để thay **một** Unicode locale keyword, ưu tiên `setUnicodeLocaleKeyword`. Chỉ dùng `setExtension('u',...)` khi thật sự muốn cấu hình lại **toàn bộ** extension ấy.

## 8. Chương trình Java 17+ độc lập, đã kiểm chứng đầu ra

Tạo file **CombinedLocaleExtensionsDemo.java**:

~~~java
import java.util.Currency;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.TreeSet;
import java.time.temporal.WeekFields;

public class CombinedLocaleExtensionsDemo {
    public static void main(String[] args) {
        Locale combined = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("nu", "latn")
                .setUnicodeLocaleKeyword("ca", "gregory")
                .setUnicodeLocaleKeyword("cu", "eur")
                .setUnicodeLocaleKeyword("fw", "mon")
                .setUnicodeLocaleKeyword("rg", "gbzzzz")
                .setUnicodeLocaleKeyword("tz", "usnyc")
                .setExtension(Locale.PRIVATE_USE_EXTENSION, "training")
                .build();

        System.out.println("tag = " + combined.toLanguageTag());
        System.out.println("language = " + combined.getLanguage());
        System.out.println("region = " + combined.getCountry());
        System.out.println("u = " + combined.getExtension(
                Locale.UNICODE_LOCALE_EXTENSION));
        System.out.println("x = " + combined.getExtension(
                Locale.PRIVATE_USE_EXTENSION));
        System.out.println("keys = "
                + new TreeSet<>(combined.getUnicodeLocaleKeys()));
        System.out.println("ca = " + combined.getUnicodeLocaleType("ca"));
        System.out.println("nu = " + combined.getUnicodeLocaleType("nu"));
        System.out.println("cu = " + combined.getUnicodeLocaleType("cu"));
        System.out.println("fw = " + combined.getUnicodeLocaleType("fw"));
        System.out.println("rg = " + combined.getUnicodeLocaleType("rg"));
        System.out.println("tz = " + combined.getUnicodeLocaleType("tz"));

        System.out.println("currency = "
                + Currency.getInstance(combined).getCurrencyCode());
        System.out.println("first day = "
                + WeekFields.of(combined).getFirstDayOfWeek());

        Locale roundTrip =
                Locale.forLanguageTag(combined.toLanguageTag());
        System.out.println("round-trip equals = "
                + combined.equals(roundTrip));

        Locale changed = new Locale.Builder()
                .setLocale(combined)
                .setUnicodeLocaleKeyword("nu", "arab")
                .build();
        System.out.println("original nu = "
                + combined.getUnicodeLocaleType("nu"));
        System.out.println("changed nu = "
                + changed.getUnicodeLocaleType("nu"));
        System.out.println("changed cu = "
                + changed.getUnicodeLocaleType("cu"));

        Locale replaced = new Locale.Builder()
                .setLocale(combined)
                .setExtension(Locale.UNICODE_LOCALE_EXTENSION, "nu-thai")
                .build();
        System.out.println("replaced keys = "
                + new TreeSet<>(replaced.getUnicodeLocaleKeys()));
        System.out.println("replaced x = "
                + replaced.getExtension(Locale.PRIVATE_USE_EXTENSION));

        Locale removed = new Locale.Builder()
                .setLocale(combined)
                .setUnicodeLocaleKeyword("fw", null)
                .build();
        System.out.println("removed fw = "
                + removed.getUnicodeLocaleType("fw"));

        Locale plain = new Locale.Builder()
                .setLocale(combined)
                .clearExtensions()
                .build();
        System.out.println("plain tag = " + plain.toLanguageTag());
        System.out.println("plain extensions empty = "
                + plain.getExtensionKeys().isEmpty());

        try {
            new Locale.Builder()
                    .setUnicodeLocaleKeyword("abc", "latn");
        } catch (IllformedLocaleException ex) {
            System.out.println("invalid unicode key = rejected");
        }
    }
}
~~~

Dùng JDK 17+ và lệnh:

~~~bash
javac --release 17 CombinedLocaleExtensionsDemo.java
java CombinedLocaleExtensionsDemo
~~~

**Đầu ra đã kiểm chứng bằng Java và `--release 17`:**

~~~text
tag = en-US-u-ca-gregory-cu-eur-fw-mon-nu-latn-rg-gbzzzz-tz-usnyc-x-training
language = en
region = US
u = ca-gregory-cu-eur-fw-mon-nu-latn-rg-gbzzzz-tz-usnyc
x = training
keys = [ca, cu, fw, nu, rg, tz]
ca = gregory
nu = latn
cu = eur
fw = mon
rg = gbzzzz
tz = usnyc
currency = EUR
first day = MONDAY
round-trip equals = true
original nu = latn
changed nu = arab
changed cu = eur
replaced keys = [nu]
replaced x = training
removed fw = null
plain tag = en-US
plain extensions empty = true
invalid unicode key = rejected
~~~

### Cách đọc những kết quả đáng chú ý

- **`tag`:** dù setter gọi `nu` trước `ca`, kết quả `toLanguageTag` sắp key theo quy tắc chuẩn hóa, và `x-training` nằm sau `u`.
- **`u` và `x`:** `getExtension` trả phần giá trị extension, **không** kèm singleton `u-` hoặc `x-`.
- **`keys`:** chương trình đưa tập key vào `TreeSet` để in theo thứ tự rõ ràng.
- **`region`:** vẫn là `US`, dù có `rg-gbzzzz`. Region override không thay trường cơ sở.
- **`currency`:** `Currency.getInstance` áp dụng lựa chọn `cu-eur` và trả mã `EUR`.
- **`first day`:** `WeekFields.of` áp dụng `fw-mon`, trả `MONDAY`.
- **`round-trip equals`:** thẻ BCP 47 có thể được parse lại thành đối tượng Locale tương đương.
- **`changed`:** thay `nu` từ `latn` sang `arab` giữ lại `cu-eur` và không sửa Locale gốc.
- **`replaced`:** thay toàn bộ extension `u` bằng `nu-thai` làm `ca`, `cu`, `fw`, `rg`, `tz` biến mất khỏi `u`, nhưng `x-training` được giữ.
- **`removed`:** xóa riêng key `fw` làm `getUnicodeLocaleType("fw")` trả `null`.
- **`plain`:** `clearExtensions()` chỉ loại bỏ phần mở rộng; `en-US` vẫn giữ.
- **Key sai:** `abc` dài ba ký tự, trong khi Unicode locale key phải có hai ký tự; builder từ chối bằng `IllformedLocaleException`.

Ví dụ in **mã tiền tệ** và **ngày đầu tuần**, không in các chuỗi định dạng đầy đủ phụ thuộc dữ liệu locale hoặc cấu hình máy.

## 9. Một Locale nhiều keyword không bắt mọi dịch vụ hỗ trợ mọi keyword

`Locale` chứa cấu hình; **API tiêu thụ Locale** mới quyết định lựa chọn nào được áp dụng.

| API | Các keyword có thể liên quan | Giới hạn |
| --- | --- | --- |
| `Currency.getInstance(locale)` | `cu`, dữ liệu vùng | Chọn tiền tệ, **không thực hiện chuyển đổi tỷ giá** |
| `NumberFormat` | `nu`, locale data | Kiểu chữ số được hỗ trợ tùy provider và service |
| `Calendar.getInstance(locale)` | `ca`, `fw`, `rg`, `tz` theo overload | Không sửa múi giờ mặc định của JVM |
| `WeekFields.of(locale)` | `fw`, `rg`, dữ liệu vùng | Có quy tắc ưu tiên riêng cho tuần |
| `DateTimeFormatter` được localize | Dữ liệu lịch/số/thời gian theo API | Không phải mọi type đều được áp dụng tự động |
| `Locale.toLanguageTag()` | Mọi phần được biểu diễn hợp lệ | Không chứng minh một formatter đã hỗ trợ tất cả |
| `Locale.getUnicodeLocaleType(key)` | Giá trị đã lưu cho key | Không chứng minh type có được service công nhận |

**Ví dụ xung đột `fw` và `rg`:** `rg` có thể yêu cầu quy tắc tuần theo vùng override. Nếu đồng thời có `fw-mon`, `fw` có thể ưu tiên hơn ngày đầu tuần suy ra ngầm từ `rg`, theo hợp đồng `Calendar`.

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag("en-US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .setUnicodeLocaleKeyword("fw", "mon")
        .build();
~~~

Đoạn code đặt hai lựa chọn **đồng thời và rõ ràng**. Nó không làm `getCountry()` thành `GB`.

**Về `tz`:** BCP 47 `tz-usnyc` là lựa chọn múi giờ cho dịch vụ có hỗ trợ. Nếu phép tính nghiệp vụ phải dùng đúng vùng thời gian, vẫn nên chỉ định rõ `ZoneId`, ví dụ `ZoneId.of("America/New_York")`, trong API thời gian thay vì dựa vào tác động ngầm của Locale.

**Về `co` và các keyword khác:** Java có thể giữ một type đúng cú pháp mà một `Collator` hoặc provider cụ thể không hỗ trợ. Không mặc định mọi `co` đều được Java 10 hay JDK 17 áp dụng; hãy kiểm tra danh sách hỗ trợ cho runtime đang triển khai.

## 10. Cú pháp hợp lệ không đồng nghĩa tính năng có sẵn

`Locale.Builder` kiểm tra **cú pháp** thẻ ngôn ngữ:
- Language hợp lệ về hình dạng (ví dụ `en`, `vi`, `ja`).
- Region dạng mã phù hợp (ví dụ `US`, `VN`).
- Unicode locale key gồm **hai ký tự chữ/số**.
- Type được tổ hợp từ các subtag theo quy tắc của Unicode locale extension.
- Extension singleton và các subtag phải đúng định dạng.
- Sai hình dạng ném `IllformedLocaleException`.

Nhưng builder **không kiểm chứng toàn bộ giá trị đã đăng ký** và **không kiểm thử formatter**:
- Type có tồn tại trong registry phù hợp không?
- Runtime/provider có dữ liệu locale tương ứng không?
- API cần dùng có thực sự tôn trọng keyword đó không?
- Khi không hỗ trợ, cơ chế fallback cụ thể là gì?

Do đó, `build()` thành công **không bảo đảm** formatter hiển thị đúng mong muốn. Với chức năng hiển thị mang tính bắt buộc, hãy kiểm thử bằng đúng API và dữ liệu runtime mục tiêu.

### Parse nghiêm ngặt và parse dung sai

`Locale.forLanguageTag(tag)` có thể bỏ những phần sai cú pháp theo đặc tả parse của nó. Nếu cần phát hiện rõ input BCP 47 sai hình dạng, dùng:

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag(userTag)
        .build();
~~~

Đây là snippet cần khai báo `String userTag`, và ứng dụng cần bắt hoặc để lan truyền `IllformedLocaleException` theo hợp đồng.

`setLanguageTag` cũng **đặt lại toàn bộ builder**, nên thực hiện trước các setter tùy chỉnh tiếp theo nếu muốn giữ chúng.

### Attributes khác keywords

Unicode extension `u` có thể chứa **attributes** không đi với key/type:

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag("en-US")
        .addUnicodeLocaleAttribute("foobar")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(locale.toLanguageTag());
// en-US-u-foobar-nu-latn
~~~

`foobar` chỉ là **attribute minh họa đúng cú pháp**, không khẳng định JDK có behavior đặc biệt cho nó. `getUnicodeLocaleAttributes()` xem attribute, `getUnicodeLocaleKeys()` xem keyword key. Các attribute xuất hiện trước key/type trong phần Unicode extension đã chuẩn hóa.

## 11. Thiết kế một hệ thống dùng nhiều lựa chọn Locale

Một ứng dụng quốc tế hóa có thể lưu thẻ:

~~~text
vi-VN-u-cu-eur-fw-mon-nu-latn
~~~

Nó biểu diễn lựa chọn tiếng Việt, vùng Việt Nam, đồng tiền Euro để định dạng, đầu tuần thứ Hai và chữ số Latin. Có thể xây với:

~~~java
Locale preferences = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .setUnicodeLocaleKeyword("cu", "eur")
        .setUnicodeLocaleKeyword("fw", "mon")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
~~~

Để xử lý vững:
1. **Lưu và trao đổi `toLanguageTag()`**, không nối các đoạn tag tùy tiện.
2. **Tạo Locale mới** khi cần cập nhật, dùng `new Locale.Builder().setLocale(old)...build()`.
3. **Xác định chính sách khi nhiều nguồn cấu hình cùng key**: một giá trị ưu tiên, hay reject xung đột.
4. **Kiểm tra hỗ trợ trong formatter cụ thể**, không suy luận từ việc Locale lưu key.
5. **Không gộp lựa chọn tiền tệ với quy tắc chuyển đổi tỷ giá**: mã tiền tệ không tự sửa số tiền.
6. **Không dùng Locale làm dữ liệu vị trí thực tế hoặc thông tin cá nhân**: đây là lựa chọn ngôn ngữ/định dạng, không phải bằng chứng địa chỉ.
7. **Tránh lạm dụng private-use `x`** để chứa trạng thái nghiệp vụ phức tạp.
8. **Kiểm thử trên JDK/provider thực tế** nếu giao diện phụ thuộc định dạng locale cụ thể; bản dữ liệu CLDR hoặc runtime image có thể khác nhau.

Nếu cần đảm bảo các lựa chọn nghiệp vụ độc lập với formatter, mô hình Java 17+ có thể tách rõ:

~~~java
record DisplayConfig(
        Locale locale,
        Currency currency,
        java.time.ZoneId zone) {}
~~~

Đây là định nghĩa kiểu minh họa: currency và zone được lưu thành lựa chọn **rõ ràng** khi nghiệp vụ cần, thay vì chỉ trông chờ formatter suy ra từ Locale.

## 12. Các lỗi thường gặp

**Lỗi 1 — “Mỗi Unicode keyword phải có một `u` riêng.”**  
Không. Chỉ **một Unicode extension `u`** chứa nhiều cặp key/type, như `u-ca-gregory-nu-latn-cu-eur`. Dùng builder để tránh lặp singleton sai.

**Lỗi 2 — “Gọi `setUnicodeLocaleKeyword` lần thứ hai sẽ xóa lần đầu.”**  
Không khi key khác nhau. Chỉ khi gọi cùng key thì type mới thay type cũ.

**Lỗi 3 — “`setExtension('u',...)` thêm tiếp các key đang có.”**  
Sai. Nó **thay toàn bộ extension `u`**, có thể làm mất các key/attribute trước.

**Lỗi 4 — “`setLanguageTag` chỉ đặt language mà không thay tùy chọn khác.”**  
Sai. Nó đặt lại builder theo **toàn bộ language tag được truyền**. Hãy nạp base trước rồi mới sửa từng keyword.

**Lỗi 5 — “`rg` tự thay giá trị `getCountry()`.”**  
Không. `rg` mô tả vùng override cho service hỗ trợ; trường region cơ sở vẫn giữ nguyên.

**Lỗi 6 — “`tz-usnyc` thay múi giờ của cả JVM.”**  
Không. Locale không tự đổi `ZoneId.systemDefault()`; API thời gian cần vùng rõ ràng khi nghiệp vụ yêu cầu.

**Lỗi 7 — “`cu-eur` đổi USD thành EUR.”**  
Không. Nó chỉ chọn currency type; tỷ giá và chuyển đổi đơn vị là bài toán riêng.

**Lỗi 8 — “Builder đúng cú pháp thì mọi type đều được mọi service hỗ trợ.”**  
Không. Cần kiểm tra runtime, provider và class tiêu thụ.

**Lỗi 9 — “`x-training` là Unicode locale keyword.”**  
Không. `x` là private-use extension, độc lập với `u`.

**Lỗi 10 — “Thứ tự gọi setter phải giống thứ tự language tag in ra.”**  
Không. `toLanguageTag()` chuẩn hóa thứ tự của keyword.

**Lỗi 11 — “Có thể nối hai language tags bằng toán tử `+`.”**  
Không. BCP 47 có cấu trúc singleton, language, region, key/type; cần chính sách hợp nhất và builder.

**Lỗi 12 — “Toàn bộ Locale.Builder mới được thêm ở Java 10.”**  
Không. Builder/BCP 47 có từ Java 7. Java 10 nổi bật với hỗ trợ bổ sung `cu`, `fw`, `rg`, `tz`.

**Lỗi 13 — “`getUnicodeLocaleKeys()` luôn có thứ tự in giống `toLanguageTag()`.”**  
Không nên phụ thuộc thứ tự duyệt của `Set`. Dùng `TreeSet` nếu cần hiển thị xác định.

**Lỗi 14 — “`clearExtensions()` xóa luôn ngôn ngữ và quốc gia.”**  
Sai. Nó chỉ xóa extensions; `clear()` mới reset tất cả trường builder.

## 13. Tự kiểm tra kiến thức

**1. Thẻ `en-US-u-ca-gregory-nu-latn` có bao nhiêu extension `u` và bao nhiêu keyword?**  
Một `u` với hai keyword `ca`, `nu`.

**2. Thêm `cu-eur` mà không mất `nu-latn` bằng cách nào?**  
Dùng `new Locale.Builder().setLocale(base).setUnicodeLocaleKeyword("cu","eur").build()`.

**3. Vì sao `setExtension('u',"nu-thai")` có thể làm mất `ca` và `cu`?**  
Nó thay **toàn bộ Unicode extension `u`**, không chỉ thêm một key.

**4. `u` và `x` có thể cùng xuất hiện trong một language tag không?**  
Có. `u` chứa Unicode keywords, `x` chứa private-use subtags.

**5. `rg-gbzzzz` có tự làm `locale.getCountry()` trả `GB` không?**  
Không. `getCountry()` phản ánh region cơ sở; `rg` là override cho dịch vụ có hỗ trợ.

**6. `fw-mon` có bắt mọi API lịch, tuần hoặc ngày giờ chọn thứ Hai không?**  
Không. Tác dụng tùy service. `WeekFields.of(locale)` là ví dụ API hỗ trợ thích hợp.

**7. `tz-usnyc` có đổi `ZoneId.systemDefault()` không?**  
Không. Locale không tự thay đổi múi giờ toàn cục của JVM.

**8. `Locale.Builder` có xác thực một type đúng cú pháp đã được CLDR/provider hỗ trợ không?**  
Không. Builder kiểm tra cú pháp, không đảm bảo mọi thư viện biết ý nghĩa type.

**9. Xóa riêng keyword `fw` mà giữ `cu` và `nu` thế nào?**  
Dùng `setUnicodeLocaleKeyword("fw", null)` trên builder nạp từ Locale gốc.

**10. `clearExtensions()` khác `clear()` thế nào?**  
Cái đầu xóa extension, giữ language/region/script/variant; cái sau đặt lại toàn bộ builder.

**11. Vì sao `Locale.toLanguageTag()` không nhất thiết giữ thứ tự setter?**  
Vì Java chuẩn hóa cách xuất thẻ theo các quy tắc BCP 47.

**12. Java 10 đã tăng hỗ trợ dịch vụ cho những keyword nào?**  
`cu`, `fw`, `rg`, `tz` qua JEP 314.

## 14. Ghi nhớ cuối bài

- Có thể lưu **nhiều Unicode keywords trong một extension `u`**, đồng thời kết hợp với các extension singleton khác như `x`.
- **Java 10/JEP 314** tăng hỗ trợ `cu`, `fw`, `rg`, `tz` trong JDK; API BCP 47 và `Locale.Builder` có từ trước.
- **`setUnicodeLocaleKeyword`** phù hợp để thêm, cập nhật, xóa **một** key mà giữ các key khác.
- **`setExtension('u',...)` thay toàn bộ Unicode extension**; `setLanguageTag` đặt lại builder; `clearExtensions` xóa mọi extension mà giữ trường cơ sở.
- Dùng `getUnicodeLocaleType`, `getUnicodeLocaleKeys`, `getExtension` và `toLanguageTag` để đọc, kiểm tra, truyền cấu hình.
- **Locale lưu cấu hình, formatter áp dụng có điều kiện**. Đúng cú pháp không phải bằng chứng rằng mọi service hỗ trợ các keyword.
- Khi có xung đột giữa các cấu hình, dùng builder và chính sách ưu tiên rõ ràng; không nối tag bằng chuỗi.

**Tài liệu tham khảo hiện còn áp dụng:**
- [Oracle Java SE 17 — Internationalization Enhancements, JEP 314](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html).
- [Oracle Java SE 17 — `Locale`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).
- [Oracle Java SE 17 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html).
- [Oracle Java SE 17 — `Calendar` và các tùy chọn tuần](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Calendar.html).
- [Oracle Java SE 17 — `WeekFields.of(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html).
- [Oracle JDK 17 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html).
