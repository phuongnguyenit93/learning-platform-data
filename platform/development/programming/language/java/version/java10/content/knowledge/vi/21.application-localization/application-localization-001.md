# `Currency.getInstance(Locale)` và Unicode locale extension `cu` — chọn đơn vị tiền tệ trong Java 10+

## 1. Vấn đề: Locale của người dùng không phải lúc nào cũng là đơn vị tiền tệ của giao dịch

Trong ứng dụng quốc tế hóa, chúng ta thường cần hiển thị tiền bằng ngôn ngữ và cách trình bày quen thuộc của người dùng, nhưng **đơn vị tiền tệ thực tế có thể khác tiền tệ mặc định của quốc gia đó**.

Ví dụ:

- Người dùng đang sử dụng tiếng Anh ở Hoa Kỳ (`en-US`), nhưng hóa đơn được lập bằng **EUR**, không phải USD.
- Một giao diện tiếng Việt cho người dùng ở Việt Nam (`vi-VN`) có thể cần hiển thị giá bán bằng **USD**.
- Một ứng dụng đặt phòng có thể hiển thị số tiền bằng **JPY** mặc dù giao diện đang dùng tiếng Anh kiểu Mỹ.
- Vùng dùng để xác định tiền tệ có thể được chỉ định qua Unicode locale extension `rg`; người dùng vẫn có thể chọn một tiền tệ khác bằng `cu`.

Java có sẵn `java.util.Currency` để mô tả tiền tệ bằng mã **ISO 4217** như `USD`, `EUR`, `JPY`, `VND`. Khi gọi:

```java
Currency currency = Currency.getInstance(Locale.US);
System.out.println(currency.getCurrencyCode()); // USD
```

API lấy tiền tệ mặc định gắn với quốc gia được thể hiện bởi `Locale`.

Kể từ **Java 10**, cách xử lý `Currency.getInstance(Locale)` hỗ trợ thêm **Unicode locale extension `cu` (currency type)**, giúp đưa yêu cầu lựa chọn tiền tệ vào chính đối tượng `Locale`:

```java
Locale locale = Locale.forLanguageTag("en-US-u-cu-eur");
Currency currency = Currency.getInstance(locale);

System.out.println(currency.getCurrencyCode()); // EUR
System.out.println(locale.getCountry());         // US
```

**Điểm cốt lõi:** locale vẫn có ngôn ngữ `en` và vùng `US`, nhưng phần mở rộng `cu-eur` khiến `Currency.getInstance(locale)` chọn **EUR**. Không cần thay quốc gia của người dùng thành Pháp/Đức để chọn đồng euro.

> **Quan trọng:** `Currency` **không đổi tỷ giá** và không chuyển số tiền USD sang EUR. Nó chỉ mô tả/chọn đơn vị tiền tệ. Nếu giá trị gốc là `100 USD` thì chỉ đổi ký hiệu hiển thị thành `€` mà không tính tỷ giá là **sai nghiệp vụ**.

Bài học thuộc nhóm **Locale trong ứng dụng**, tập trung vào sự khác biệt giữa **Locale cơ sở**, **Unicode extension `cu`**, và **Currency.getInstance(Locale)`**; chỉ trình bày API còn hiệu lực trong Java hiện đại.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích vì sao `Currency.getInstance(Locale)` thường trả tiền tệ theo quốc gia, không chỉ theo ngôn ngữ.
2. Đọc và xây dựng language tag có `-u-cu-xxx`, ví dụ `en-US-u-cu-eur`.
3. Phân biệt `Locale`, `Currency`, mã ISO 4217, ký hiệu tiền tệ và giá trị tiền.
4. Dùng `Locale.forLanguageTag(...)` và `Locale.Builder.setUnicodeLocaleKeyword("cu", ...)`.
5. Kiểm tra `locale.getUnicodeLocaleType("cu")` và `locale.toLanguageTag()`.
6. Hiểu ưu tiên giữa `cu` (currency type) và `rg` (region override).
7. So sánh `Currency.getInstance(Locale)` với `Currency.getInstance(String)`.
8. Dùng `NumberFormat.getCurrencyInstance(Locale)` để định dạng số tiền và hiểu vai trò của `cu`.
9. Biết ý nghĩa `getCurrencyCode()`, `getSymbol(Locale)`, `getDefaultFractionDigits()`, `getNumericCodeAsString()`.
10. Xử lý `null`, locale không có quốc gia hợp lệ, mã tiền tệ không được hỗ trợ và lãnh thổ không có tiền tệ.
11. Không phụ thuộc vào ký hiệu hiển thị hoặc dữ liệu tiền tệ có thể thay đổi theo JDK/CLDR.
12. Thiết kế luồng dữ liệu tiền tệ có `BigDecimal` và **mã tiền tệ tường minh** thay vì suy đoán từ người dùng.

## 3. `Locale` gồm những thành phần nào?

`Locale` là đại diện cho những đặc điểm ngôn ngữ, vùng địa lý/chính trị/văn hóa và các tùy chọn bổ sung có thể ảnh hưởng tới những API locale-sensitive.

Một locale như:

```text
en-US
│  └─ Vùng: United States (US)
└──── Ngôn ngữ: English (en)
```

Có hai thông tin chính; chúng không phải mã tiền tệ. Trong Java:

```java
Locale us = Locale.forLanguageTag("en-US");

System.out.println(us.getLanguage()); // en
System.out.println(us.getCountry());  // US
```

Khi chưa có `cu` hoặc `rg`, `Currency.getInstance(Locale)` dựa chủ yếu vào **country/region** để tìm tiền tệ mặc định; **language** và **variant** không quyết định mã tiền tệ trong phương thức này.

```java
System.out.println(Currency.getInstance(
        Locale.forLanguageTag("en-US")).getCurrencyCode()); // USD

System.out.println(Currency.getInstance(
        Locale.forLanguageTag("fr-FR")).getCurrencyCode()); // EUR
```

Hai ngôn ngữ khác nhau chỉ là một phần của ví dụ; yếu tố làm thay đổi tiền tệ mặc định ở đây là **US so với FR**, không phải riêng `en` so với `fr`.

### Không suy ra tiền tệ từ ngôn ngữ

Ngôn ngữ tiếng Anh được dùng ở nhiều quốc gia có tiền tệ khác nhau. Do đó `Locale.forLanguageTag("en")` chỉ có ngôn ngữ, **không có country** và không đủ dữ liệu vùng thông thường để tìm tiền tệ mặc định.

**Không mặc định** `Currency.getInstance(Locale.ENGLISH)` sẽ trả USD. Với locale thiếu country và không có extension xác định tiền tệ phù hợp, `Currency.getInstance(Locale)` có thể ném `IllegalArgumentException` theo hợp đồng.

## 4. `Currency` đại diện cho điều gì?

`java.util.Currency` là một class `final` có các instance đại diện cho mã tiền tệ ISO 4217.

Một số thông tin cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `getCurrencyCode()` | Mã tiền tệ chữ cái ISO 4217, ví dụ `EUR` |
| `getNumericCode()` | Mã tiền tệ dạng số ISO 4217, kiểu `int` |
| `getNumericCodeAsString()` | Mã số ba chữ số dưới dạng `String`, giữ số 0 ở đầu |
| `getSymbol(Locale)` | Ký hiệu hiển thị trong locale được chọn; có thể khác tùy vùng/provider |
| `getDisplayName(Locale)` | Tên tiền tệ cho hiển thị ở locale được chọn |
| `getDefaultFractionDigits()` | Số chữ số thập phân mặc định theo dữ liệu tiền tệ, có thể là `-1` cho pseudo-currency |
| `Currency.getInstance(String)` | Chọn tiền tệ theo **mã ISO 4217 tường minh** |
| `Currency.getInstance(Locale)` | Chọn tiền tệ dựa trên locale/`cu`/`rg` |

Ví dụ:

```java
Currency usd = Currency.getInstance("USD");
Currency jpy = Currency.getInstance("JPY");

System.out.println(usd.getCurrencyCode());        // USD
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(jpy.getDefaultFractionDigits()); // 0
```

**Không nhầm `getDefaultFractionDigits` với một luật tài chính tuyệt đối.** Đó là thông tin mặc định về minor unit ISO 4217 do runtime cung cấp; nghiệp vụ thanh toán, giá niêm yết, hạn mức làm tròn, tiền mặt hay yêu cầu đối tác có thể quy định precision khác.

`Currency` không có giá trị số tiền, không lưu số dư và không thực hiện chuyển đổi tỷ giá. `Currency.getSymbol(Locale)` còn là thông tin **hiển thị**, không phải định danh duy nhất đáng tin của tiền tệ.

## 5. Cú pháp BCP 47 của phần mở rộng Unicode `cu`

`Locale` hỗ trợ ngôn ngữ gắn tag theo **BCP 47**. Phần mở rộng Unicode được bắt đầu bởi singleton `u`, sau đó là các cặp **key–type**. Với tiền tệ:

- Key: `cu` — *currency type*.
- Type: mã tiền tệ ISO 4217 thường viết chữ thường trong language tag, ví dụ `usd`, `eur`, `jpy`.
- Dạng đầy đủ: `<language>-<region>-u-cu-<currency>`.

Ví dụ:

```text
en-US-u-cu-eur
│  │  │ │  └── type = eur (tiền tệ euro)
│  │  │ └───── key = cu (currency)
│  │  └─────── Unicode extension singleton = u
│  └────────── country = US
└───────────── language = en
```

Trong Java:

```java
Locale locale = Locale.forLanguageTag("en-US-u-cu-eur");

System.out.println(locale.toLanguageTag());        // en-US-u-cu-eur
System.out.println(locale.getCountry());           // US
System.out.println(locale.getUnicodeLocaleType("cu")); // eur
System.out.println(Currency.getInstance(locale).getCurrencyCode()); // EUR
```

**Chú ý chữ hoa/thường:** language tag chuẩn hóa Unicode keyword sang chữ thường `eur`, nhưng mã ISO 4217 do `Currency.getCurrencyCode()` trả về là `EUR`. Đây là **hai cách biểu diễn cùng lựa chọn tiền tệ**, không phải hai tiền tệ khác nhau.

Phần mở rộng `cu` là một **ưu tiên trong Locale**, không phải cách chuyển đổi tỷ giá hay thay đổi ý nghĩa số tiền đang lưu.

### Vì sao tính năng gắn với Java 10?

`Currency` tồn tại từ Java cũ, nhưng **JEP 314 — Additional Unicode Language-Tag Extensions**, được triển khai trong **Java 10**, bổ sung khả năng các API Java liên quan **hiểu** thêm `cu`, `rg`, `fw` và `tz`. Đặc biệt `Currency.getInstance(Locale)` nhận biết `cu`/`rg` kể từ thời điểm này và tiếp tục hỗ trợ trong các bản Java hiện hành.

## 6. Tạo Locale có `cu` bằng `Locale.forLanguageTag`

Đây là cách ngắn và gần với dữ liệu BCP 47 thường thấy trong cấu hình:

```java
var eurosInUsEnglish = Locale.forLanguageTag("en-US-u-cu-eur");
var yenInUsEnglish   = Locale.forLanguageTag("en-US-u-cu-jpy");
var dollarsInVietnam = Locale.forLanguageTag("vi-VN-u-cu-usd");

System.out.println(
        Currency.getInstance(eurosInUsEnglish).getCurrencyCode()); // EUR
System.out.println(
        Currency.getInstance(yenInUsEnglish).getCurrencyCode());   // JPY
System.out.println(
        Currency.getInstance(dollarsInVietnam).getCurrencyCode()); // USD
```

Lưu ý:

- `en-US` **không** biến thành `de-DE` khi chọn EUR.
- `vi-VN` **không** biến thành `en-US` khi chọn USD.
- Ngôn ngữ và country vẫn có ích cho ngữ cảnh hiển thị, nhưng currency override là một lựa chọn **độc lập**.
- Nếu đầu vào language tag đến từ người dùng/đối tác, cần kiểm tra type `cu` có thực sự là mã tiền tệ được ứng dụng hỗ trợ; việc parse language tag không tự đảm bảo mã đó được nghiệp vụ chấp nhận.

### Không dùng `-x-...` để thay cho `-u-cu-...`

BCP 47 phân biệt extension chuẩn `u` với *private-use* `x`. Tag `en-US-x-cu-eur` không tương đương `en-US-u-cu-eur`; ứng dụng không nên mong `Currency.getInstance` hiểu tiền tệ từ một extension tùy ý `x`.

## 7. Tạo Locale với `Locale.Builder`

Khi bạn đang xây Locale từ nhiều trường riêng biệt, `Locale.Builder` giúp tránh nối chuỗi BCP 47 thủ công:

```java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("cu", "eur")
        .build();

System.out.println(locale.toLanguageTag()); // en-US-u-cu-eur
System.out.println(Currency.getInstance(locale).getCurrencyCode()); // EUR
```

`setUnicodeLocaleKeyword` có hai tham số:

- `"cu"` là **key Unicode**.
- `"eur"` là **type** được chọn.

Builder kiểm tra cú pháp key/type theo quy tắc Locale và có thể ném `IllformedLocaleException` khi thành phần không đúng dạng. **Cú pháp hợp lệ không đồng nghĩa mã tiền tệ được hỗ trợ**: một type ba chữ cái không có trong dữ liệu Currency vẫn có thể thỏa kiểm tra hình thức của Locale.Builder. Nếu nhận currency code do người dùng cung cấp, hãy xác thực riêng.

### Thay đổi hoặc xóa override trong Builder

```java
Locale withEuro = new Locale.Builder()
        .setLocale(Locale.US)
        .setUnicodeLocaleKeyword("cu", "eur")
        .build();

Locale withoutOverride = new Locale.Builder()
        .setLocale(withEuro)
        .setUnicodeLocaleKeyword("cu", null)
        .build();

System.out.println(Currency.getInstance(withEuro).getCurrencyCode()); // EUR
System.out.println(Currency.getInstance(withoutOverride).getCurrencyCode()); // USD
```

Theo `Locale.Builder`, type `null` **loại bỏ keyword** tương ứng. Đây là thiết kế tốt khi cần reset lựa chọn tiền tệ về mặc định của region mà không chỉnh sửa ngôn ngữ/vùng thủ công.

**Cần nhớ:** `Locale` sau khi `build` là một object locale độc lập; bạn không thay trực tiếp một thuộc tính trên Locale cũ. Muốn tạo Locale khác, dùng Builder hoặc language tag khác.

## 8. `Currency.getInstance(Locale)` chọn tiền tệ theo nguyên tắc nào?

Với Locale hợp lệ, cách tư duy đơn giản:

1. Nếu có **`cu` hợp lệ và được hỗ trợ**, tiền tệ nêu trong `cu` được ưu tiên.
2. Nếu không có lựa chọn `cu` phù hợp, **`rg`** có thể xác định một vùng được áp dụng để tìm tiền tệ thay cho country cơ sở.
3. Nếu không có override được áp dụng, dùng **quốc gia** cơ sở của Locale để lấy tiền tệ tương ứng.
4. Một vùng không có tiền tệ có thể cho kết quả **`null`**; country không hợp lệ có thể dẫn đến **`IllegalArgumentException`**.

Với dữ liệu tiền tệ mặc định của JDK hiện hành:

```java
Currency usd = Currency.getInstance(Locale.US);
Currency euro = Currency.getInstance(
        Locale.forLanguageTag("en-US-u-cu-eur"));

System.out.println(usd.getCurrencyCode());  // USD
System.out.println(euro.getCurrencyCode()); // EUR
```

Không có bước đổi `getCountry()` từ `US` sang một nước khu vực đồng euro: **`cu` được diễn giải khi API lựa chọn tiền tệ**.

### Trường hợp `cu` không phải mã được hỗ trợ

Không nên suy luận rằng một tag có `cu` bất kỳ luôn tạo ra Currency mới. `Currency` chỉ làm việc với mã được runtime hỗ trợ; Javadoc của `Currency.getInstance(String)` nêu rõ mã không được hỗ trợ sẽ gây `IllegalArgumentException`.

Đối với `getInstance(Locale)`, cách triển khai có thể không sử dụng override `cu` không hợp lệ và quay về logic region. **Không dùng fallback để âm thầm chấp nhận dữ liệu tiền tệ người dùng nhập sai**. Trong nghiệp vụ thanh toán, nên xác thực mã tường minh bằng `Currency.getInstance(String)` rồi lưu code đã kiểm.

### Kiểm tra country trước khi dựa vào fallback

Locale chỉ chứa ngôn ngữ như `en` không cung cấp country rõ ràng; đừng gọi `Currency.getInstance(Locale.forLanguageTag("en"))` rồi mặc định kết quả là USD. Nếu currency do đơn hàng quyết định, hãy lưu và sử dụng mã tiền tệ của **đơn hàng**, không suy đoán từ ngôn ngữ giao diện.

## 9. `rg`: region override và thứ tự ưu tiên so với `cu`

Một Unicode locale keyword khác là **`rg` — region override**. Nó chỉ ra vùng thay thế dùng cho các hành vi nhạy với region. Trong language tag, ví dụ:

```text
en-US-u-rg-gbzzzz
        └─ region override = GB
```

Ở đây `gbzzzz` là một dạng type `rg` chỉ **GB** (United Kingdom) theo cú pháp Unicode. `Locale.getCountry()` vẫn là `US`, nhưng API Currency có thể dùng vùng override để xác định GBP.

```java
Locale regionOverride =
        Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(regionOverride.getCountry()); // US
System.out.println(regionOverride.getUnicodeLocaleType("rg")); // gbzzzz
System.out.println(
        Currency.getInstance(regionOverride).getCurrencyCode()); // GBP
```

Nếu **cả `rg` và `cu`** cùng xuất hiện, Javadoc xác định rằng tiền tệ từ `cu` **ưu tiên hơn** tiền tệ được suy ra ngầm từ `rg`:

```java
Locale both = Locale.forLanguageTag(
        "en-US-u-cu-jpy-rg-gbzzzz");

System.out.println(both.getCountry()); // US
System.out.println(both.getUnicodeLocaleType("cu")); // jpy
System.out.println(both.getUnicodeLocaleType("rg")); // gbzzzz

System.out.println(
        Currency.getInstance(both).getCurrencyCode()); // JPY
```

Tại sao không phải GBP? Vì `cu-jpy` đã **chỉ định tiền tệ trực tiếp**, còn `rg-gbzzzz` chỉ cho phép suy ra tiền tệ từ vùng GB.

| Locale | Country cơ sở | `rg` | `cu` | Currency theo API |
| --- | --- | --- | --- | --- |
| `en-US` | US | Không | Không | USD |
| `en-US-u-cu-eur` | US | Không | EUR | EUR |
| `en-US-u-rg-gbzzzz` | US | GB | Không | GBP |
| `en-US-u-cu-jpy-rg-gbzzzz` | US | GB | JPY | JPY |
| `vi-VN-u-cu-usd` | VN | Không | USD | USD |

**Chú ý:** `rg` có thể tác động tới nhiều cách xử lý locale-sensitive khác ngoài Currency. Nó không biến bản thân `Locale.getCountry()` thành GB. Đừng đánh đồng country cơ sở với effective region do một API lựa chọn.

## 10. So sánh `Currency.getInstance(Locale)` với `Currency.getInstance(String)`

Hai overload trả cùng kiểu `Currency` nhưng trả lời những câu hỏi khác nhau:

```java
Currency inferred = Currency.getInstance(Locale.US);
Currency selected = Currency.getInstance("EUR");
```

- `getInstance(Locale.US)`: “Đơn vị tiền tệ mặc định cho vùng của locale này là gì?”
- `getInstance("EUR")`: “Hãy lấy đơn vị tiền tệ có **mã ISO 4217 EUR**.”

Nếu bạn đã có mã tiền tệ **trong dữ liệu đơn hàng**, overload nhận `String` thường là lựa chọn rõ nhất. Nếu bạn có một Locale với `cu` đã xác thực và muốn những dịch vụ locale-sensitive cùng hiểu preference ấy, overload nhận `Locale` phù hợp.

### Ví dụ trong ứng dụng bán hàng

Giả sử:

```text
UI locale      = en-US
Order currency = EUR
Order amount   = 125.50 (EUR)
```

Không được lấy `Currency.getInstance(Locale.US)` (USD) rồi gắn `USD` vào số tiền `125.50` của đơn hàng. Điều đó **đổi đơn vị nhưng không đổi giá trị**, thành dữ liệu sai.

Thay vào đó:

```java
Currency orderCurrency = Currency.getInstance("EUR");
BigDecimal amount = new BigDecimal("125.50");
```

Bạn có thể dùng `Locale.US` làm **locale hiển thị** trong formatter, còn `orderCurrency` vẫn là EUR. Hoặc tạo một Locale `en-US-u-cu-eur` khi muốn gắn tùy chọn currency vào locale.

### Identity và đối tượng Currency

Javadoc của `Currency` nói class bảo đảm không có nhiều hơn một instance cho cùng mã tiền tệ trong runtime. Vì vậy các lời gọi lấy EUR từ mã và từ locale đều biểu diễn cùng Currency:

```java
Currency a = Currency.getInstance("EUR");
Currency b = Currency.getInstance(
        Locale.forLanguageTag("en-US-u-cu-eur"));

System.out.println(a == b); // true
```

Dù vậy trong dữ liệu trao đổi qua API/database, **lưu mã ISO 4217** thay vì lưu cách biểu diễn identity của object trong JVM.

## 11. Cách dùng với `NumberFormat.getCurrencyInstance(Locale)`

`Currency.getInstance(Locale)` giúp **lựa chọn Currency**, còn `NumberFormat` là API để **định dạng số tiền** thành văn bản cho người dùng.

```java
Locale displayLocale = Locale.forLanguageTag("en-US-u-cu-eur");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(displayLocale);

Currency selectedCurrency =
        Currency.getInstance(displayLocale);

System.out.println(selectedCurrency.getCurrencyCode()); // EUR
System.out.println(formatter.getCurrency().getCurrencyCode()); // EUR
```

Trên các provider hỗ trợ Unicode currency extension `cu` (bao gồm các JDK Oracle hiện hành), `NumberFormat.getCurrencyInstance` có thể nhận biết lựa chọn tiền tệ từ Locale. Javadoc hiện hành của `NumberFormat` mô tả các Unicode extension gồm `nu`, `rg`, `cf`, `cu`. Chi tiết cách hiển thị ký hiệu/khoảng trắng còn phụ thuộc provider và dữ liệu locale.

**Không hardcode kỳ vọng toàn bộ chuỗi tiền tệ** như `"€1,234.50"` trên mọi JDK/locale/provider. Đúng currency code không đủ để xác định tuyệt đối vị trí ký hiệu, spacing, kiểu dấu âm, group separator hoặc số chữ số thập phân ở mọi môi trường.

### Muốn chỉ định Currency nhưng giữ Locale hiển thị cơ sở?

```java
Locale uiLocale = Locale.US;
Currency orderCurrency = Currency.getInstance("EUR");
BigDecimal amount = new BigDecimal("1234.50");

NumberFormat formatter =
        NumberFormat.getCurrencyInstance(uiLocale);
formatter.setCurrency(orderCurrency);

String rendered = formatter.format(amount);
```

Đoạn này tách rõ:

- **Ngôn ngữ/vùng trình bày:** `Locale.US`.
- **Đơn vị tiền tệ của dữ liệu:** `EUR`.
- **Giá trị số tiền:** `BigDecimal("1234.50")`.

Đây là cách tốt khi tiền tệ nằm trên record/order và locale đến từ preference của người dùng. Không nên phụ thuộc vào locale của người dùng để suy ra tiền tệ của giao dịch.

### Lưu ý cực kỳ quan trọng về số chữ số thập phân

`NumberFormat.setCurrency(Currency)` **không tự cập nhật** `minimumFractionDigits` và `maximumFractionDigits`. Nếu bạn đang đổi một formatter đã tạo cho USD sang JPY, đừng tưởng chỉ gọi `setCurrency(jpy)` chắc chắn khiến mọi thiết lập fraction digits đổi về 0.

Khi yêu cầu định dạng là chính xác theo chính sách, hãy cấu hình rõ:

```java
Currency jpy = Currency.getInstance("JPY");
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.US);

formatter.setCurrency(jpy);
formatter.setMinimumFractionDigits(0);
formatter.setMaximumFractionDigits(0);
```

Khi có chính sách tiền tệ thực tế, cần phân biệt default minor unit, quy tắc làm tròn và số chữ số hiển thị theo nghiệp vụ; không để formatter tự quyết định tất cả.

## 12. `getSymbol(Locale)` và `getDisplayName(Locale)` là để hiển thị, không phải định danh

Cùng một mã Currency có thể có nhiều cách hiển thị theo locale.

```java
Currency usd = Currency.getInstance("USD");

String symbolForUS = usd.getSymbol(Locale.US);
String symbolForFrance = usd.getSymbol(Locale.FRANCE);
String nameForUS = usd.getDisplayName(Locale.US);
```

Các đoạn trả về là **text để hiển thị**. Chúng có thể khác nhau theo vùng hoặc dữ liệu locale/provider. Nếu provider không xác định được symbol/name thích hợp, API có thể dùng mã ISO 4217 làm fallback.

**Không sử dụng ký hiệu như `$` làm khóa định danh tiền tệ**: một ký hiệu có thể được nhiều đơn vị tiền tệ sử dụng và có thể thay đổi khi hiển thị ở những locale khác nhau.

Quy tắc:

- **Tính toán/lưu trữ:** mã `USD`, `EUR`… và số tiền bằng `BigDecimal`.
- **Hiển thị:** `currency.getSymbol(userLocale)`, `getDisplayName(userLocale)` hoặc `NumberFormat.getCurrencyInstance(...)`.
- **Trao đổi máy–máy:** mã ISO 4217, không dùng ký hiệu tiền tệ hoặc tên đã dịch để tự đoán mã.

### `cu` không phải ký hiệu hiển thị

`u-cu-eur` chọn **đơn vị EUR**, không bắt buộc chuỗi hiển thị sẽ là `€` trong mọi trường hợp. Có locale/provider có thể chọn dạng `EUR`, một dạng ký hiệu dài hơn hoặc tên hiển thị khác. Đây là lý do code kiểm thử nên assert `getCurrencyCode()`, không assert literal symbol.

## 13. Mã số ISO, số thập phân mặc định và giới hạn của metadata

`Currency` còn cung cấp metadata:

```java
Currency eur = Currency.getInstance("EUR");
Currency usd = Currency.getInstance("USD");
Currency jpy = Currency.getInstance("JPY");

System.out.println(eur.getNumericCodeAsString()); // 978
System.out.println(usd.getNumericCodeAsString()); // 840
System.out.println(jpy.getDefaultFractionDigits()); // 0
```

`getNumericCodeAsString()` trả **ba chữ số** theo ISO 4217, kể cả khi có số 0 đứng đầu. Khác với `getNumericCode()` trả về `int`, API dạng String tránh mất padding khi lưu/hiển thị mã số.

`getDefaultFractionDigits()` trả số chữ số thập phân mặc định gắn với đơn vị, ví dụ USD/EUR thường có 2, JPY có 0. Với một số pseudo-currency, API có thể trả `-1`.

**Không sử dụng metadata này như một bảng tỷ giá**:

- `getCurrencyCode()` không cho biết giá trị của 1 EUR bằng bao nhiêu USD.
- `getNumericCode()` không phải mã quốc gia, tỷ giá hay số tài khoản.
- `getDefaultFractionDigits()` không quy định mức giá nhỏ nhất có thể giao dịch trong mọi hệ thống.
- `Currency.getInstance(Locale)` không có tham số ngày giao dịch để truy vấn tỷ giá lịch sử.

Dữ liệu tiền tệ và luật sử dụng tiền có thể thay đổi theo thời gian. Nếu một doanh nghiệp cần xử lý giao dịch lịch sử hoặc các currency không còn lưu hành, phải gắn thời điểm hiệu lực và chính sách nghiệp vụ phù hợp; không dựa vào currency mặc định **hiện tại** của quốc gia để đoán đơn vị giao dịch cũ.

## 14. Null, quốc gia không hợp lệ và lãnh thổ không có tiền tệ

### 14.1. `Locale` là `null`

```java
// Currency.getInstance((Locale) null); // NullPointerException
```

Nếu locale đến từ request, cấu hình hoặc UI, cần kiểm tra null trước khi dùng API. Đây là lỗi đầu vào, không phải biểu hiện “không có tiền tệ”.

### 14.2. Locale thiếu hoặc có country không được hỗ trợ

```java
Locale onlyLanguage = Locale.forLanguageTag("en");
// Currency.getInstance(onlyLanguage); // Có thể ném IllegalArgumentException
```

Javadoc nói `Currency.getInstance(Locale)` ném `IllegalArgumentException` nếu country của locale **không phải mã quốc gia ISO 3166 được hỗ trợ**. Với locale chỉ có language, không nên giả định API tự chọn quốc gia. Trường hợp một extension `cu` hợp lệ có thể cung cấp lựa chọn tiền tệ riêng; nhưng **không xây API nghiệp vụ dựa trên việc sửa thiếu country bằng một fallback không được khai báo rõ**.

### 14.3. Lãnh thổ không có tiền tệ

`Currency.getInstance(Locale)` có thể trả **`null`** cho một lãnh thổ không có đơn vị tiền tệ, ví dụ Antarctica (`AQ`). Cần phân biệt:

- **`null` trả về bình thường**: lãnh thổ không có tiền tệ theo dữ liệu runtime.
- **`IllegalArgumentException`**: country không được hỗ trợ/không hợp lệ theo API.
- **`NullPointerException`**: tham số Locale null.

Nếu code viết:

```java
Currency currency = Currency.getInstance(locale);
String code = currency.getCurrencyCode();
```

thì cần kiểm tra `currency != null` trước khi gọi `getCurrencyCode()` đối với input locale tùy ý.

### 14.4. Mã tiền tệ do người dùng cung cấp

`Currency.getInstance(String)` nhận mã ISO 4217 và ném `IllegalArgumentException` khi mã không được runtime hỗ trợ. Nên áp dụng:

1. Kiểm tra `null` và ký tự/độ dài input theo hợp đồng API.
2. Chuẩn hóa chữ hoa theo `Locale.ROOT` khi có lý do dùng mã nhập không đồng nhất.
3. Gọi `Currency.getInstance(code)` để kiểm tra mã có được runtime hỗ trợ.
4. Kiểm tra danh sách tiền tệ **được phép giao dịch** của chính ứng dụng, vì một mã được JDK biết đến không chắc được doanh nghiệp chấp nhận.
5. Dùng Currency đã xác thực để lưu/format; không tự tạo mã giả và mong Java cung cấp instance hợp lệ.

Tránh kết luận chỉ cần ba chữ cái viết hoa là đủ xác thực ISO 4217. `ABC` có đúng **hình thức**, nhưng chưa chắc là mã tiền tệ được hỗ trợ.

## 15. `cu` và `Locale` không thực hiện phép đổi tiền

Xét ví dụ:

```text
Đơn hàng:    100.00 USD
UI locale:   en-US
Người dùng muốn xem theo EUR
```

Sai về nghiệp vụ:

```java
BigDecimal amount = new BigDecimal("100.00"); // đang là USD
Currency displayed = Currency.getInstance(
        Locale.forLanguageTag("en-US-u-cu-eur"));
// Sai nếu chỉ hiển thị amount cùng EUR mà không đổi giá trị!
```

Vì `cu` thay Currency **được chọn**, không thay đổi `amount`.

Cách đúng về mô hình:

```java
record Money(BigDecimal amount, Currency currency) {
    Money {
        java.util.Objects.requireNonNull(amount);
        java.util.Objects.requireNonNull(currency);
    }
}

Money original = new Money(
        new BigDecimal("100.00"),
        Currency.getInstance("USD"));
```

Đây là đoạn minh họa dùng record (Java 16+) và import `BigDecimal`, `Currency`. Để tính ra EUR, ứng dụng cần một **tỷ giá** có nguồn, thời điểm, loại tỷ giá, phí và quy tắc làm tròn được xác định:

```java
// Minh họa công thức, không có tỷ giá thực:
// BigDecimal converted = original.amount()
//         .multiply(rateUsdToEur)
//         .setScale(2, RoundingMode.HALF_EVEN);
```

Không có tỷ giá đầu vào thì **không thể** biết `100 USD` tương đương bao nhiêu EUR. Java Currency không cung cấp dữ liệu tỷ giá, và `getInstance(Locale)` không phải dịch vụ ngoại hối.

### Quy tắc thiết kế tốt

Lưu **`amount` + `currencyCode`** như một cặp không thể tách rời. `Locale` là thuộc tính của **ngữ cảnh hiển thị**, không thay thế đơn vị của bản ghi giao dịch.

Trong đa tiền tệ, có thể có ba giá trị riêng:

- `userLocale`: ngôn ngữ/vùng trình bày.
- `sourceCurrency`: tiền tệ gốc của giao dịch.
- `displayCurrency`: tiền tệ muốn hiển thị, chỉ dùng sau khi quy trình đổi tiền thật sự được thực hiện nếu hai mã khác nhau.

## 16. Ví dụ Java 17+ độc lập, kiểm chứng chính xác `cu` và `rg`

Tạo tệp **`CurrencyLocaleCuDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyLocaleCuDemo {
    static String currencyCode(Locale locale) {
        Currency currency = Currency.getInstance(locale);
        return currency == null ? "<none>" : currency.getCurrencyCode();
    }

    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale euroOverride =
                Locale.forLanguageTag("en-US-u-cu-eur");
        Locale yenOverride =
                Locale.forLanguageTag("en-US-u-cu-jpy");
        Locale gbRegionOverride =
                Locale.forLanguageTag("en-US-u-rg-gbzzzz");
        Locale bothOverrides =
                Locale.forLanguageTag("en-US-u-cu-jpy-rg-gbzzzz");
        Locale vietnamUsd =
                Locale.forLanguageTag("vi-VN-u-cu-usd");

        System.out.println("baseUS=" + currencyCode(us));
        System.out.println("euroOverride="
                + currencyCode(euroOverride));
        System.out.println("yenOverride="
                + currencyCode(yenOverride));
        System.out.println("gbRegionOverride="
                + currencyCode(gbRegionOverride));
        System.out.println("bothOverrides="
                + currencyCode(bothOverrides));
        System.out.println("vietnamUsd="
                + currencyCode(vietnamUsd));

        System.out.println("countryUnchanged="
                + euroOverride.getCountry());
        System.out.println("languageUnchanged="
                + euroOverride.getLanguage());
        System.out.println("cuType="
                + euroOverride.getUnicodeLocaleType("cu"));
        System.out.println("tag="
                + euroOverride.toLanguageTag());
        System.out.println("rgType="
                + gbRegionOverride.getUnicodeLocaleType("rg"));

        Locale builderLocale = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("cu", "eur")
                .build();
        System.out.println("builderEqual="
                + builderLocale.equals(euroOverride));

        Locale cleared = new Locale.Builder()
                .setLocale(builderLocale)
                .setUnicodeLocaleKeyword("cu", null)
                .build();
        System.out.println("clearedCurrency="
                + currencyCode(cleared));

        Currency eurByCode = Currency.getInstance("EUR");
        Currency eurByLocale = Currency.getInstance(euroOverride);
        System.out.println("sameEuroInstance="
                + (eurByCode == eurByLocale));
        System.out.println("eurNumericCode="
                + eurByCode.getNumericCodeAsString());
        System.out.println("usdNumericCode="
                + Currency.getInstance("USD").getNumericCodeAsString());
        System.out.println("usdFractionDigits="
                + Currency.getInstance("USD").getDefaultFractionDigits());
        System.out.println("jpyFractionDigits="
                + Currency.getInstance("JPY").getDefaultFractionDigits());

        System.out.println("euroSymbolPresent="
                + !eurByCode.getSymbol(Locale.US).isBlank());
        System.out.println("euroNamePresent="
                + !eurByCode.getDisplayName(Locale.US).isBlank());

        NumberFormat formatFromCu =
                NumberFormat.getCurrencyInstance(euroOverride);
        System.out.println("formatFromCuCurrency="
                + formatFromCu.getCurrency().getCurrencyCode());

        NumberFormat explicit =
                NumberFormat.getCurrencyInstance(Locale.US);
        System.out.println("formatBefore="
                + explicit.getCurrency().getCurrencyCode());
        explicit.setCurrency(Currency.getInstance("JPY"));
        System.out.println("formatAfter="
                + explicit.getCurrency().getCurrencyCode());
        explicit.setMinimumFractionDigits(0);
        explicit.setMaximumFractionDigits(0);
        System.out.println("formatFractionDigits="
                + explicit.getMaximumFractionDigits());

        BigDecimal amount = new BigDecimal("1234.50");
        System.out.println("amountUnchanged="
                + amount.toPlainString());

        try {
            Currency.getInstance((Locale) null);
        } catch (NullPointerException expected) {
            System.out.println("nullLocaleRejected=true");
        }

        try {
            Currency.getInstance("ZZZ");
        } catch (IllegalArgumentException expected) {
            System.out.println("unknownCodeRejected=true");
        }

        try {
            Currency.getInstance(Locale.forLanguageTag("en"));
        } catch (IllegalArgumentException expected) {
            System.out.println("missingCountryRejected=true");
        }

        System.out.println("antarcticaNoCurrency="
                + (Currency.getInstance(
                        Locale.forLanguageTag("en-AQ")) == null));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 CurrencyLocaleCuDemo.java
java CurrencyLocaleCuDemo
```

**Stdout dự kiến chính xác:**

```text
baseUS=USD
euroOverride=EUR
yenOverride=JPY
gbRegionOverride=GBP
bothOverrides=JPY
vietnamUsd=USD
countryUnchanged=US
languageUnchanged=en
cuType=eur
tag=en-US-u-cu-eur
rgType=gbzzzz
builderEqual=true
clearedCurrency=USD
sameEuroInstance=true
eurNumericCode=978
usdNumericCode=840
usdFractionDigits=2
jpyFractionDigits=0
euroSymbolPresent=true
euroNamePresent=true
formatFromCuCurrency=EUR
formatBefore=USD
formatAfter=JPY
formatFractionDigits=0
amountUnchanged=1234.50
nullLocaleRejected=true
unknownCodeRejected=true
missingCountryRejected=true
antarcticaNoCurrency=true
```

### Giải thích các nhóm kết quả

1. **Mặc định theo vùng:** `Locale.US` trả USD.
2. **Có `cu`:** `en-US-u-cu-eur` trả EUR, `en-US-u-cu-jpy` trả JPY, `vi-VN-u-cu-usd` trả USD.
3. **Có `rg`:** override GB được dùng để suy ra GBP.
4. **Có cả hai:** `cu-jpy` ưu tiên hơn tiền tệ GBP suy ra từ `rg-gbzzzz`; kết quả là JPY.
5. **Country và language không bị biến đổi:** locale vẫn `US` và `en`; chỉ có keyword `cu` thêm lựa chọn tiền tệ.
6. **Builder tương đương language tag:** `equals` trả `true`; loại bỏ `cu` trả lại lựa chọn mặc định USD.
7. **Mã ISO:** EUR có mã numeric `978`, USD có `840`; fraction digits mặc định USD `2`, JPY `0`.
8. **Symbol và name:** chương trình **không assert chuỗi ký hiệu/tên literal**, chỉ kiểm tra text hiển thị có dữ liệu vì chúng có thể khác theo provider.
9. **Formatter:** `NumberFormat.getCurrencyInstance(euroOverride)` chọn EUR; cũng có thể tạo formatter theo `Locale.US` rồi `setCurrency` sang JPY.
10. **Không đổi giá trị tiền:** `amountUnchanged=1234.50` dù formatter có thể dùng JPY; việc chọn Currency không đổi tỷ giá.
11. **Lỗi đầu vào:** Locale null, mã tiền tệ không được hỗ trợ và locale chỉ có ngôn ngữ được phân biệt.
12. **Lãnh thổ không có tiền tệ:** `AQ` trả null theo dữ liệu của JDK.

Nếu chạy trên một JVM sử dụng **custom currency data** hoặc dữ liệu currency/locale provider bị thay đổi, một số kết quả phụ thuộc dữ liệu có thể khác. Trong chương trình trên, các mã phổ biến USD/EUR/JPY/GBP và ví dụ `AQ` tương ứng dữ liệu chuẩn hiện hành.

## 17. Các lỗi phổ biến

### Lỗi A: Dùng country của Locale để đoán tiền tệ của giao dịch

```java
Currency currency = Currency.getInstance(Locale.US); // USD
// Nhưng hóa đơn thực tế có thể mang đơn vị EUR!
```

**Sửa:** lưu đơn vị tiền tệ thật của đơn hàng, sử dụng `Currency.getInstance("EUR")` hoặc Locale có `cu-eur` được xác thực.

### Lỗi B: Nghĩ `cu` thay đổi `Locale.getCountry()`

```java
Locale l = Locale.forLanguageTag("en-US-u-cu-eur");
System.out.println(l.getCountry()); // US
```

**Sửa:** hiểu `cu` là keyword override được API nhận biết; language/country cơ sở vẫn giữ nguyên.

### Lỗi C: Dùng `en-US-u-rg-gbzzzz` rồi vẫn mặc định USD

Khi `rg` hợp lệ, `Currency.getInstance` có thể suy ra GBP từ region override; không chỉ nhìn `locale.getCountry()`.

**Sửa:** dùng `Currency.getInstance(locale)` để tính theo các extension và test đầy đủ cả `cu` lẫn `rg`.

### Lỗi D: Có cả `cu` và `rg` nhưng chọn currency theo `rg`

Javadoc quy định `cu` có ưu tiên cao hơn currency suy ra từ `rg`.

**Sửa:** xem `cu` là lựa chọn trực tiếp của tiền tệ; `rg` chỉ cung cấp vùng khi không có `cu` áp dụng.

### Lỗi E: Ghép `cu` vào private-use extension `x`

`en-US-x-cu-eur` không tương đương `en-US-u-cu-eur`.

**Sửa:** dùng chuẩn BCP 47 Unicode `u-cu-xxx` hoặc `Locale.Builder.setUnicodeLocaleKeyword`.

### Lỗi F: Cho rằng mã ba chữ cái bất kỳ đều hợp lệ

`abc` có thể đúng hình thức, nhưng không chắc là mã ISO 4217 được runtime hỗ trợ.

**Sửa:** xác thực mã tiền tệ bằng `Currency.getInstance(String)` và whitelist được phép giao dịch của ứng dụng.

### Lỗi G: Lấy symbol `$` hoặc `€` làm khóa dữ liệu

Ký hiệu có thể trùng giữa nhiều tiền tệ và khác theo locale.

**Sửa:** dùng `getCurrencyCode()` trong dữ liệu lưu trữ/trao đổi; chỉ dùng symbol/name để hiển thị.

### Lỗi H: Coi `Currency` là API tỷ giá

Chuyển `USD` sang `EUR` qua `cu` không làm `amount` thay đổi. Không được gắn nhãn EUR cho số USD nếu chưa chuyển giá trị bằng quy trình ngoại hối thực.

**Sửa:** tách `Money(amount,currency)` và bước conversion có tỷ giá, thời điểm, phí, làm tròn.

### Lỗi I: Chỉ gọi `NumberFormat.setCurrency(jpy)` rồi nghĩ fraction digits tự đổi về 0

`setCurrency` **không cập nhật tự động** minimum/maximum fraction digits.

**Sửa:** cấu hình số chữ số và quy tắc rounding tường minh theo nghiệp vụ.

### Lỗi J: Hardcode ký hiệu và spacing của `NumberFormat`

Output có thể phụ thuộc dữ liệu locale, provider, bản JDK, nhóm chữ số hoặc display context.

**Sửa:** test mã Currency, số tiền và các thuộc tính được cam kết; pin format literal chỉ khi môi trường/provider được quy định rõ.

### Lỗi K: Gọi `getCurrencyCode()` ngay sau `getInstance(locale)` không kiểm null

Một số lãnh thổ không có tiền tệ và `getInstance` trả null.

**Sửa:** xử lý `null` riêng nếu input locale không được kiểm soát.

### Lỗi L: Lấy tiền tệ mặc định hiện tại làm tiền tệ lịch sử

Đơn vị tiền tệ của quốc gia có thể thay đổi theo thời gian. `Currency.getInstance(Locale)` không phải dịch vụ truy vấn tiền tệ của giao dịch vào một ngày lịch sử bất kỳ.

**Sửa:** lưu currency code tại thời điểm phát sinh nghiệp vụ và áp dụng quy tắc lịch sử khi cần.

### Lỗi M: Chia sẻ formatter mutable giữa các request đa luồng

`NumberFormat`/`DecimalFormat` có trạng thái mutable và không thể được coi là an toàn cho truy cập đồng thời tùy ý.

**Sửa:** tạo formatter riêng mỗi tác vụ hoặc đồng bộ hóa nếu thật sự chia sẻ; đừng thay `Locale.setDefault` toàn cục cho một request riêng.

## 18. Checklist thiết kế quốc tế hóa tiền tệ

Trước khi thêm `Currency.getInstance(Locale)` hoặc `cu` vào ứng dụng:

1. **Nguồn sự thật về đơn vị tiền tệ là gì?** Đơn hàng, payment provider hay lựa chọn UI?
2. **Locale nào dùng cho hiển thị?** Ngôn ngữ/vùng giao diện có thể khác đơn vị giao dịch.
3. **Currency là yêu cầu tường minh hay mặc định theo vùng?** Nếu tường minh, dùng code/`cu`.
4. **Có xây Locale theo chuẩn BCP 47 không?** Kiểm cấu trúc `u-cu-xxx`.
5. **Dữ liệu từ người dùng có được validate không?** Kiểm Currency code và danh sách nghiệp vụ.
6. **Có cần `rg` region override không?** Đừng nhầm country cơ sở với effective region.
7. **Đã hiểu `cu` ưu tiên hơn `rg` chưa?**
8. **Có xử lý Locale không có country, null và lãnh thổ không có tiền tệ không?**
9. **Có lưu mã ISO 4217 thay vì symbol không?**
10. **Có giữ amount và Currency cùng một record/kiểu dữ liệu không?**
11. **Nếu đổi tiền, nguồn tỷ giá và thời điểm hiệu lực là gì?**
12. **Dữ liệu tiền tệ có thể thay đổi theo thời gian không?** Đừng suy ngược tiền tệ quá khứ từ defaults hiện tại.
13. **Có sử dụng BigDecimal cho precision cần thiết không?**
14. **Có xác định rounding/fraction digits theo nghiệp vụ không?** `setCurrency` không tự cập nhật fraction digits.
15. **Formatter có được tạo theo Locale hiển thị và Currency đúng không?**
16. **Có đang hardcode symbol hoặc currency display name?** Tránh phụ thuộc dữ liệu provider.
17. **Có test cả `cu`, `rg` và tổ hợp hai extension không?**
18. **Có đổi default Locale toàn cục giữa các request không?** Tránh trong server đa luồng.
19. **Có viết test không phụ thuộc thứ tự/dữ liệu tiền tệ không liên quan không?** Kiểm code, không kiểm list currency tùy môi trường.
20. **Có xác định phiên bản JDK và tập dữ liệu currency/CLDR được triển khai không?**

## 19. Bài tập và đáp án

**Câu 1.** `Currency.getInstance(Locale.US)` thông thường trả tiền tệ nào?

**Câu 2.** Với `Locale.forLanguageTag("en-US-u-cu-eur")`, `getCountry()` trả gì và `Currency.getInstance(...)` trả mã nào?

**Câu 3.** Trong language tag `en-US-u-cu-jpy`, `u`, `cu` và `jpy` có vai trò gì?

**Câu 4.** `Locale.Builder.setUnicodeLocaleKeyword("cu","eur")` tạo thông tin currency trong Locale bằng cách nào?

**Câu 5.** `Currency.getInstance(Locale.forLanguageTag("en-US-u-rg-gbzzzz"))` trả mã gì theo JDK hiện hành?

**Câu 6.** Nếu có cả `cu-jpy` và `rg-gbzzzz` thì Currency chọn JPY hay GBP?

**Câu 7.** `Currency.getInstance("EUR")` khác `Currency.getInstance(Locale.US)` về mục đích thế nào?

**Câu 8.** `getSymbol(Locale.US)` có thể thay thế `getCurrencyCode()` để lưu mã giao dịch không?

**Câu 9.** `Currency.getDefaultFractionDigits()` có trả tỷ giá hoặc luật tiền mặt của toàn bộ doanh nghiệp không?

**Câu 10.** `Currency.getInstance(locale)` có thể trả `null` khi nào?

**Câu 11.** Nếu locale chỉ chứa ngôn ngữ `en`, có thể mặc định rằng Currency là USD không?

**Câu 12.** `NumberFormat.setCurrency(Currency.getInstance("JPY"))` có tự cập nhật fraction digit min/max không?

**Câu 13.** Giao dịch có `100 USD`, UI muốn EUR; có thể chỉ dùng `u-cu-eur` và hiển thị `100 EUR` không?

**Câu 14.** Có nên dùng `Locale.setDefault(Locale.GERMANY)` để xử lý một request giữa nhiều request khác không?

**Câu 15.** `cu` được JDK nhận biết bởi `Currency.getInstance(Locale)` từ phiên bản Java nào?

**Câu 16.** Nếu nhận chuỗi `"ZZZ"` từ khách hàng, nên xác thực Currency thế nào?

**Câu 17.** Kết quả `Currency.getInstance(Locale)` có phải luôn phù hợp để suy ra currency lịch sử không?

**Đáp án:**

1. `USD`.
2. `getCountry()` vẫn là `US`; Currency được chọn là `EUR`.
3. `u` mở Unicode locale extension, `cu` là key currency type, `jpy` là mã tiền tệ được yêu cầu.
4. Builder gắn Unicode locale key/type; sau `build()`, `Currency.getInstance` có thể diễn giải `cu`.
5. `GBP` theo region override `GB`.
6. `JPY`, vì currency `cu` ưu tiên hơn tiền tệ suy ra từ `rg`.
7. Overload String chọn mã tiền tệ **tường minh**; overload Locale suy ra từ region hoặc extension.
8. Không. Symbol là dữ liệu hiển thị phụ thuộc locale, có thể mơ hồ; dùng ISO 4217 code.
9. Không. Nó chỉ là số chữ số thập phân mặc định của tiền tệ theo metadata.
10. Khi locale chỉ một lãnh thổ không có tiền tệ, như `AQ`.
11. Không. Ngôn ngữ không xác định một country hay đơn vị tiền tệ mặc định.
12. Không. Cần cấu hình fraction digits và quy tắc làm tròn khi nghiệp vụ yêu cầu.
13. Không. Phải chuyển giá trị theo tỷ giá thích hợp hoặc giữ nguyên USD.
14. Không nên; thay đổi default toàn cục có thể ảnh hưởng các request khác.
15. Khả năng hỗ trợ Unicode `cu` trong các API liên quan được bổ sung ở **Java 10** theo JEP 314.
16. Kiểm tra đúng dạng, chuẩn hóa khi thích hợp, gọi `Currency.getInstance(String)`, xử lý mã không được hỗ trợ và kiểm danh sách được phép.
17. Không. Currency data có thể đổi; phải giữ code tại thời điểm giao dịch và policy lịch sử.

## 20. Tổng kết và nguồn chính thức còn hiệu lực

- `Currency.getInstance(Locale)` chọn tiền tệ theo country/region của locale, có xét Unicode extension.
- **`u-cu-xxx`** là Unicode locale keyword `cu` (*currency type*), ví dụ `en-US-u-cu-eur`.
- `Locale.getCountry()` **không bị đổi** khi thêm `cu`; country của `en-US-u-cu-eur` vẫn là US.
- **`cu` ưu tiên hơn currency ngầm định từ `rg`** nếu cả hai extension cùng có hiệu lực.
- `Locale.forLanguageTag(...)` và `Locale.Builder.setUnicodeLocaleKeyword("cu", ...)` đều là cách tạo Locale phù hợp.
- Khi giao dịch đã có đơn vị tường minh, **ưu tiên lưu `Currency.getInstance(code)` và `BigDecimal amount`**, thay vì suy đoán tiền tệ từ locale giao diện.
- `Currency` cung cấp metadata (ISO code, symbol/name, fraction digits), **không cung cấp tỷ giá**.
- `NumberFormat.getCurrencyInstance(locale)` dùng để định dạng cho người dùng; `setCurrency` không tự đổi min/max fraction digits.
- Xử lý mã không hợp lệ, locale không đủ thông tin, lãnh thổ không có tiền tệ và sự biến động của dữ liệu currency theo thời gian.
- **JEP 314 được phát hành trong Java 10**; hỗ trợ `cu`/`rg` vẫn được sử dụng trong Java hiện đại.

Tài liệu chính thức:

1. [Java SE 26 — `java.util.Currency`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Currency.html): `getInstance(Locale)`, `cu`/`rg`, null, ISO 4217, symbol, fraction digits.
2. [Java SE 26 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): cấu trúc BCP 47 và Unicode locale extension `u`.
3. [Java SE 26 — `Locale.Builder.setUnicodeLocaleKeyword`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html#setUnicodeLocaleKeyword(java.lang.String,java.lang.String)): xây/chỉnh Unicode key/type.
4. [Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): định dạng currency, Unicode extensions, `setCurrency` và fraction digits.
5. [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): bổ sung hỗ trợ `cu`, `rg`, `fw` và `tz` ở Java 10.
6. [Oracle Java SE 10 — Internationalization Enhancements](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): ví dụ `en-US-u-cu-EUR` và `en-US-u-cu-JPY`.
