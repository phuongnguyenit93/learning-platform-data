# Viết guarded case bằng when trong Java 21 — bài thực hành tổng hợp

## 1. Mục tiêu bài thực hành

Khi sử dụng **pattern matching for switch**, một nhánh `case` có thể khớp đúng kiểu hoặc cấu trúc dữ liệu nhưng vẫn cần thỏa thêm một điều kiện nghiệp vụ. Java 21 cung cấp cú pháp **guarded pattern label** với từ khóa `when` để diễn đạt trực tiếp ý tưởng đó:

```java
case SomeType value when condition -> result;
```

Bài **Viết guarded case bằng when** thuộc nhóm **Thực hành tổng hợp**. Bạn sẽ viết một bộ phân loại yêu cầu giao nhận, gồm ba subtype của một `sealed interface`: giao nội địa, giao quốc tế và tự nhận hàng. Mỗi subtype có các nhánh được bảo vệ bởi guard, sau đó là nhánh fallback theo chính subtype. Bài cũng rèn kỹ năng xử lý `null` ở root, `null` trong record lồng nhau, kiểm tra chuỗi và giá trị biên; cuối cùng có chương trình Java 21 tự chạy để kiểm thử tất cả.

Sau bài này, bạn có thể:

- Viết đúng cú pháp `case Pattern when booleanExpression -> result` trong `switch`.
- Phân biệt **pattern match** (đúng loại/cấu trúc) và **guard true** (đúng điều kiện bổ sung).
- Dùng record pattern để lấy component và gọi hàm validation từ guard.
- Đặt nhánh đặc biệt **trước** nhánh cùng kiểu tổng quát để tránh bị che hoặc sai thứ tự ưu tiên.
- Xử lý `null` đúng cách; tránh `NullPointerException` ở guard.
- Viết `switch expression` exhaustive trên sealed hierarchy **không thêm `default` chỉ để che nhánh thiếu**.
- Tự thiết kế test đúng/sai/biên cho từng subtype, đọc compiler errors và kiểm chứng kết quả bằng `javac --release 21`.

**Yêu cầu:** JDK 21 trở lên để biên dịch và chạy mã ví dụ. **Record patterns** và **pattern matching for switch** là tính năng chính thức trong Java 21 (JEP 440 và JEP 441), không cần `--enable-preview`. Type pattern trong `instanceof` đã chính thức từ Java 16 (JEP 394).

## 2. Đề bài: phân tuyến yêu cầu giao nhận

Xây dựng hàm:

```java
static String route(ShippingRequest request)
```

Hàm nhận một yêu cầu giao nhận và trả **một chuỗi nhãn** theo quy tắc nghiệp vụ giả định trong bài. Tập kiểu được đóng bằng `sealed interface`:

```java
sealed interface ShippingRequest permits Domestic, International, Pickup {}

record Address(String city, String country) {}

record Domestic(String id, Address address, int weightKg)
        implements ShippingRequest {}

record International(String id, String country, boolean customsReady)
        implements ShippingRequest {}

record Pickup(String id, boolean paid)
        implements ShippingRequest {}
```

Đây là **các khai báo minh họa**; chương trình hoàn chỉnh ở mục 6 khai báo tất cả bên trong một lớp Java.

### Hợp đồng phân loại

| Subtype | Điều kiện | Kết quả |
|---|---|---|
| Root null | `request == null` | `INVALID:NULL` |
| Domestic | ID và city có text, country chính xác `VN`, cân nặng dương và không quá 5 kg, city bằng `HCM` không phân biệt hoa/thường | `DOMESTIC_EXPRESS:<id>` |
| Domestic | ID và city có text, country chính xác `VN`, cân nặng dương; không thỏa điều kiện express | `DOMESTIC_STANDARD:<id>` |
| Domestic | Thiếu địa chỉ, field không hợp lệ, country khác VN hoặc cân nặng không dương | `INVALID:DOMESTIC` |
| International | ID/country có text và `customsReady == true` | `INTERNATIONAL_READY:<id>` |
| International | ID/country có text nhưng `customsReady == false` | `INTERNATIONAL_PENDING:<id>` |
| International | ID/country null, rỗng hoặc chỉ khoảng trắng | `INVALID:INTERNATIONAL` |
| Pickup | ID có text và `paid == true` | `PICKUP_READY:<id>` |
| Pickup | ID có text và `paid == false` | `PICKUP_PENDING:<id>` |
| Pickup | ID null, rỗng hoặc chỉ khoảng trắng | `INVALID:PICKUP` |

Đây là **quy tắc demo**, không phải hệ thống logistics tiêu chuẩn. Ví dụ mã quốc gia được kiểm tra theo chuỗi, cân nặng dùng `int` để làm rõ điều kiện biên và kết quả là string phục vụ kiểm thử. Dự án production có thể yêu cầu mã vùng chuẩn, đơn vị đo, idempotency, tracking và service riêng.

Mục tiêu luyện `when` là xây **một chuỗi case có ưu tiên**: nếu điều kiện đặc biệt đúng thì chọn nhánh hẹp; nếu không, xét nhánh phù hợp tiếp theo; cuối cùng có fallback cho subtype.

## 3. Hiểu đúng cú pháp guarded case

Một nhãn `case` có guard trong Java 21:

```java
case Domestic(var id, var address, var weightKg)
        when weightKg > 0 -> "POSITIVE_WEIGHT";
```

**Đoạn này chỉ là nhãn case minh họa**, không phải chương trình độc lập. Ý nghĩa:

1. Selector của `switch` là một đối tượng `Domestic` khác null.
2. Record pattern phân rã các component và bind `id`, `address`, `weightKg`.
3. Chỉ **sau khi pattern khớp**, biểu thức boolean `weightKg > 0` mới được đánh giá.
4. Nếu guard đúng, thực hiện vế phải của `->`.
5. Nếu guard sai, `switch` tiếp tục xét các nhãn case tiếp theo.

Khi pattern không khớp, guard không được đánh giá. Vì vậy khi debug cần hỏi **“Không đúng subtype/cấu trúc hay đúng subtype nhưng guard false?”** — hai trường hợp khác nhau.

### Tại sao dùng when thay vì một if bên trong case?

Với nhiều trường hợp cùng subtype, guarded case giúp diễn đạt rõ các **nhánh quyết định**, ví dụ:

```java
return switch (request) {
    case Pickup(var id, var paid)
            when hasText(id) && paid -> "PICKUP_READY:" + id;
    case Pickup(var id, var paid)
            when hasText(id) -> "PICKUP_PENDING:" + id;
    case Pickup ignored -> "INVALID:PICKUP";

    // Những subtype khác và case null phải được xử lý
    // để switch expression đầy đủ.
};
```

**Đây là một switch minh họa chưa exhaustive** vì còn Domestic và International. Chương trình đầy đủ ở mục 6 có tất cả các nhánh.

Cách đọc như một bảng quyết định:

- Nhánh 1: Pickup có ID hợp lệ, đã thanh toán.
- Nhánh 2: Pickup có ID hợp lệ, chưa được chọn bởi nhánh 1.
- Nhánh 3: mọi Pickup còn lại có input không hợp lệ.

Không có nghĩa mọi `if` nên đổi sang `when`. Nếu chỉ có một kiểm tra đơn lẻ và phần xử lý dài, một `if` với type pattern đơn giản có thể dễ hiểu hơn. Dùng `when` khi nó giúp **so sánh các khả năng cùng một kiểu ngay cạnh nhau**.

## 4. Thực hành theo bước: viết từ case không guard đến case có guard

### Bước 1 — Bắt đầu với subtype và fallback

Viết nhánh đơn giản:

```java
case Pickup pickup -> "PICKUP:" + pickup.id();
```

Nó khớp mọi `Pickup` khác null, không phân biệt đã thanh toán hay chưa; thậm chí `pickup.id() == null` vẫn có thể xuất hiện. Nhánh này hữu ích để kiểm tra **dispatch theo subtype**, nhưng chưa đáp ứng đề bài.

### Bước 2 — Thêm điều kiện boolean với when

Rút ra field bằng record pattern và thêm guard:

```java
case Pickup(var id, var paid)
        when hasText(id) && paid -> "PICKUP_READY:" + id;
```

Đoạn này khớp `Pickup` với ID có text và `paid=true`. Hàm `hasText` sẽ bảo vệ giá trị null.

### Bước 3 — Thêm nhánh cho giá trị hợp lệ còn lại

```java
case Pickup(var id, var paid)
        when hasText(id) -> "PICKUP_PENDING:" + id;
```

Với `paid=false`, nhánh 1 có guard false, nhánh 2 có guard true, nên trả PENDING. Với `paid=true`, nhánh 1 đã được chọn nên không xét nhánh 2.

**Thứ tự chính là logic nghiệp vụ.** Nếu để nhánh “hasText” lên trước nhánh “hasText && paid”, một Pickup đã thanh toán sẽ bị trả PENDING. Compiler không nhất thiết nhận ra mọi quan hệ logic giữa các guard biểu thức, nên phải có test chứng minh.

### Bước 4 — Thêm fallback cùng subtype

```java
case Pickup ignored -> "INVALID:PICKUP";
```

Nhánh này khớp bất kỳ Pickup khác null nào **không được các guard phía trên chọn**. Dùng `ignored` nếu không cần truy cập các component. Đặt sau các nhánh guarded. Nếu đặt ngay từ đầu, nhánh hẹp phía sau sẽ bị bao phủ và có thể bị compiler báo `dominated case label`.

Bộ ba `Pickup` ở trên là mẫu luyện tập: **guard hẹp → guard rộng hơn → fallback cùng subtype**.

### Bước 5 — Áp dụng với record pattern lồng nhau

Đối với Domestic, cần địa chỉ:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id)
             && hasText(city)
             && "VN".equals(country)
             && weightKg > 0
             && weightKg <= 5
             && city.equalsIgnoreCase("HCM")
        -> "DOMESTIC_EXPRESS:" + id;
```

Đây là điểm cần phân biệt **mức record**:

- `Domestic` phải khác null để pattern ở root khớp.
- `Address(...)` là **nested record pattern**; nếu `address == null`, toàn pattern sâu **không khớp**, guard không chạy.
- Nếu `address` khác null nhưng `city == null`, `var city` vẫn có thể **bind null** vì đây là component trực tiếp. Guard `hasText(city)` trả false; nhánh không được chọn.
- `"VN".equals(country)` **null-safe** với country null.
- `city.equalsIgnoreCase("HCM")` chỉ được gọi sau khi `hasText(city)` true, nên không dereference null.

Bước tiếp theo là case STANDARD, bớt điều kiện express:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id)
             && hasText(city)
             && "VN".equals(country)
             && weightKg > 0
        -> "DOMESTIC_STANDARD:" + id;

case Domestic ignored -> "INVALID:DOMESTIC";
```

Đây là cấu trúc **ưu tiên express, sau đó standard, cuối cùng invalid**. Nó không có nghĩa STANDARD “bắt mọi request sai express”: STANDARD **vẫn phải hợp lệ** theo ID/city/country/weight. Các yêu cầu thiếu dữ liệu không được chuyển thành STANDARD.

### Bước 6 — Áp dụng cho International

Với `International(id,country,customsReady)`:

```java
case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country) && customsReady
        -> "INTERNATIONAL_READY:" + id;

case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country)
        -> "INTERNATIONAL_PENDING:" + id;

case International ignored -> "INVALID:INTERNATIONAL";
```

Suy luận: nhánh READY ưu tiên hơn PENDING. Cả hai đều yêu cầu ID/country có text. Vì vậy một International thiếu country dù `customsReady=true` vẫn INVALID.

### Bước 7 — Xử lý null và exhaustiveness

Bổ sung `case null -> "INVALID:NULL"`. Với tập `sealed ShippingRequest` gồm ba subtype, mỗi subtype có một **fallback không guard** nên mọi giá trị khác null thuộc các subtype hiện hữu đều được xử lý.

**Không cần `default`** chỉ để làm compiler hài lòng. Khi thêm một permitted subtype mới và biên dịch lại, việc thiếu case tương ứng phải được xem xét — compiler có thể báo `switch expression does not cover all possible input values`. Nếu thêm `default` vô cớ, nhu cầu xử lý subtype mới có thể bị che khuất.

## 5. Chuẩn bị bộ dữ liệu kiểm thử

Trước khi xem lời giải đầy đủ, hãy lập bảng input/expected. Trọng tâm là **mỗi guarded case phải có cả một đầu vào chọn được nhánh lẫn một đầu vào làm guard false**.

| Test | Request | Kỳ vọng |
|---|---|---|
| Root null | `null` | INVALID:NULL |
| Domestic Express | Domestic("D1", Address("HCM","VN"), 1) | DOMESTIC_EXPRESS:D1 |
| Express tại biên | Domestic("D2", Address("HCM","VN"), 5) | DOMESTIC_EXPRESS:D2 |
| Nặng hơn biên | Domestic("D3", Address("HCM","VN"), 6) | DOMESTIC_STANDARD:D3 |
| Thành phố khác | Domestic("D4", Address("HN","VN"), 2) | DOMESTIC_STANDARD:D4 |
| Thành phố chữ thường | Domestic("D5", Address("hcm","VN"), 2) | DOMESTIC_EXPRESS:D5 |
| Thành phố trắng | Domestic("D6", Address("  ","VN"), 2) | INVALID:DOMESTIC |
| Thành phố null | Domestic("D7", Address(null,"VN"), 2) | INVALID:DOMESTIC |
| Địa chỉ null | Domestic("D8", null, 2) | INVALID:DOMESTIC |
| ID null | Domestic(null, Address("HCM","VN"), 2) | INVALID:DOMESTIC |
| Country sai | Domestic("D9", Address("HCM","TH"), 2) | INVALID:DOMESTIC |
| Cân nặng 0/âm | Domestic hợp lệ khác, weight = 0 hoặc -1 | INVALID:DOMESTIC |
| International ready | International("I1","JP",true) | INTERNATIONAL_READY:I1 |
| International pending | International("I2","JP",false) | INTERNATIONAL_PENDING:I2 |
| International country trắng/null | International có country thiếu | INVALID:INTERNATIONAL |
| Pickup paid | Pickup("P1",true) | PICKUP_READY:P1 |
| Pickup unpaid | Pickup("P2",false) | PICKUP_PENDING:P2 |
| Pickup ID null/trắng | Pickup với ID thiếu | INVALID:PICKUP |

Bảng trên chọn các lớp tương đương quan trọng, còn chương trình đầy đủ triển khai **24 ca độc lập** bằng expected strings tường minh. Kết quả trả về được kiểm tra bằng assertion; không chỉ in log cho có.

## 6. Lời giải đầy đủ: chương trình Java 21 tự chạy

Lưu vào tệp **`GuardedWhenPracticeDemo.java`** (tên file phải trùng tên public class). Không cần thư viện ngoài JDK.

```java
import java.util.Objects;

public class GuardedWhenPracticeDemo {
    sealed interface ShippingRequest permits Domestic, International, Pickup {}

    record Address(String city, String country) {}

    record Domestic(String id, Address address, int weightKg)
            implements ShippingRequest {}

    record International(String id, String country, boolean customsReady)
            implements ShippingRequest {}

    record Pickup(String id, boolean paid)
            implements ShippingRequest {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String route(ShippingRequest request) {
        return switch (request) {
            case null -> "INVALID:NULL";

            case Domestic(var id, Address(var city, var country), var weightKg)
                    when hasText(id)
                         && hasText(city)
                         && "VN".equals(country)
                         && weightKg > 0
                         && weightKg <= 5
                         && city.equalsIgnoreCase("HCM")
                    -> "DOMESTIC_EXPRESS:" + id;

            case Domestic(var id, Address(var city, var country), var weightKg)
                    when hasText(id)
                         && hasText(city)
                         && "VN".equals(country)
                         && weightKg > 0
                    -> "DOMESTIC_STANDARD:" + id;

            case Domestic ignored -> "INVALID:DOMESTIC";

            case International(var id, var country, var customsReady)
                    when hasText(id) && hasText(country) && customsReady
                    -> "INTERNATIONAL_READY:" + id;

            case International(var id, var country, var customsReady)
                    when hasText(id) && hasText(country)
                    -> "INTERNATIONAL_PENDING:" + id;

            case International ignored -> "INVALID:INTERNATIONAL";

            case Pickup(var id, var paid)
                    when hasText(id) && paid
                    -> "PICKUP_READY:" + id;

            case Pickup(var id, var paid)
                    when hasText(id)
                    -> "PICKUP_PENDING:" + id;

            case Pickup ignored -> "INVALID:PICKUP";
        };
    }

    static void test(String label, ShippingRequest input, String expected) {
        String actual = route(input);
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("root null", null, "INVALID:NULL");

        test("domestic express", new Domestic("D1",
                new Address("HCM", "VN"), 1), "DOMESTIC_EXPRESS:D1");
        test("domestic express limit", new Domestic("D2",
                new Address("HCM", "VN"), 5), "DOMESTIC_EXPRESS:D2");
        test("domestic standard heavy", new Domestic("D3",
                new Address("HCM", "VN"), 6), "DOMESTIC_STANDARD:D3");
        test("domestic standard city", new Domestic("D4",
                new Address("HN", "VN"), 2), "DOMESTIC_STANDARD:D4");
        test("domestic lowercase city", new Domestic("D5",
                new Address("hcm", "VN"), 2), "DOMESTIC_EXPRESS:D5");

        test("domestic blank city", new Domestic("D6",
                new Address("  ", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic null city", new Domestic("D7",
                new Address(null, "VN"), 2), "INVALID:DOMESTIC");
        test("domestic null address", new Domestic("D8",
                null, 2), "INVALID:DOMESTIC");
        test("domestic null id", new Domestic(null,
                new Address("HCM", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic blank id", new Domestic(" ",
                new Address("HCM", "VN"), 2), "INVALID:DOMESTIC");
        test("domestic other country", new Domestic("D9",
                new Address("HCM", "TH"), 2), "INVALID:DOMESTIC");
        test("domestic null country", new Domestic("D10",
                new Address("HCM", null), 2), "INVALID:DOMESTIC");
        test("domestic zero weight", new Domestic("D11",
                new Address("HCM", "VN"), 0), "INVALID:DOMESTIC");
        test("domestic negative weight", new Domestic("D12",
                new Address("HCM", "VN"), -1), "INVALID:DOMESTIC");

        test("international ready", new International("I1",
                "JP", true), "INTERNATIONAL_READY:I1");
        test("international pending", new International("I2",
                "JP", false), "INTERNATIONAL_PENDING:I2");
        test("international blank country", new International("I3",
                " ", true), "INVALID:INTERNATIONAL");
        test("international null country", new International("I4",
                null, true), "INVALID:INTERNATIONAL");
        test("international null id", new International(null,
                "JP", true), "INVALID:INTERNATIONAL");

        test("pickup paid", new Pickup("P1", true), "PICKUP_READY:P1");
        test("pickup pending", new Pickup("P2", false), "PICKUP_PENDING:P2");
        test("pickup null id", new Pickup(null, true), "INVALID:PICKUP");
        test("pickup blank id", new Pickup(" ", true), "INVALID:PICKUP");
    }
}
```

### 6.1. Lệnh biên dịch và chạy

Trên JDK 21+:

```bash
javac --release 21 GuardedWhenPracticeDemo.java
java GuardedWhenPracticeDemo
```

**Stdout thực tế đã kiểm chứng:**

```text
root null => INVALID:NULL
domestic express => DOMESTIC_EXPRESS:D1
domestic express limit => DOMESTIC_EXPRESS:D2
domestic standard heavy => DOMESTIC_STANDARD:D3
domestic standard city => DOMESTIC_STANDARD:D4
domestic lowercase city => DOMESTIC_EXPRESS:D5
domestic blank city => INVALID:DOMESTIC
domestic null city => INVALID:DOMESTIC
domestic null address => INVALID:DOMESTIC
domestic null id => INVALID:DOMESTIC
domestic blank id => INVALID:DOMESTIC
domestic other country => INVALID:DOMESTIC
domestic null country => INVALID:DOMESTIC
domestic zero weight => INVALID:DOMESTIC
domestic negative weight => INVALID:DOMESTIC
international ready => INTERNATIONAL_READY:I1
international pending => INTERNATIONAL_PENDING:I2
international blank country => INVALID:INTERNATIONAL
international null country => INVALID:INTERNATIONAL
international null id => INVALID:INTERNATIONAL
pickup paid => PICKUP_READY:P1
pickup pending => PICKUP_PENDING:P2
pickup null id => INVALID:PICKUP
pickup blank id => INVALID:PICKUP
```

Có **24 phép gọi `test(...)`**, từng phép có expected string riêng. Nếu một kết quả khác hợp đồng, chương trình ném `AssertionError` và không tiếp tục in bình thường. Ví dụ đã được biên dịch trực tiếp với `javac --release 21` và chạy thành công trên tất cả 24 ca.

**Điều được xác nhận:** cú pháp guarded case, thứ tự chọn nhánh, logic guard, xử lý `null` ở dữ liệu thử và expected outputs. **Điều chưa thể suy ra:** mọi đơn hàng thực tế đều được phân loại chính xác, tính hợp lệ của chuẩn địa chỉ, hay hệ thống giao hàng production có đầy đủ validation. Đó là các quy tắc và phép kiểm thử bổ sung tùy domain.

## 7. Phân tích kết quả: điều kiện nào khiến một case được chọn?

### 7.1. Domestic: express, standard và invalid

Trong nhánh express, điều kiện:

```java
hasText(id)
    && hasText(city)
    && "VN".equals(country)
    && weightKg > 0
    && weightKg <= 5
    && city.equalsIgnoreCase("HCM")
```

là một biểu thức boolean có **short-circuit**. Chẳng hạn khi `id == null`, `hasText(id)` false; các điều kiện phía sau không cần được tính. Khi `city == null`, `hasText(city)` false và `equalsIgnoreCase` không được gọi, nên an toàn.

- **Domestic("D1",Address("HCM","VN"),1)**: đúng kiểu, địa chỉ tồn tại, tất cả điều kiện express true → EXPRESS.
- **Domestic("D2",Address("HCM","VN"),5)**: đúng tại mốc 5 kg, vì điều kiện là `weightKg <= 5` → EXPRESS.
- **Domestic("D3",Address("HCM","VN"),6)**: express false vì quá 5 kg; standard true vì vẫn dương và các điều kiện còn lại hợp lệ → STANDARD.
- **Domestic("D4",Address("HN","VN"),2)**: express false vì city không phải HCM; standard true → STANDARD.
- **Domestic("D5",Address("hcm","VN"),2)**: `equalsIgnoreCase` trả true → EXPRESS.
- **Domestic("D8",null,2)**: nested `Address(...)` không khớp null, nên cả hai nhánh Domestic có guard không được xét; `case Domestic ignored` trả INVALID.
- **Domestic có city null hoặc blank**: Address tồn tại, `var city` bind null/blank, nhưng guard `hasText(city)` false → INVALID.
- **Domestic có country không phải VN hoặc weight <= 0**: đúng subtype, nhưng không đủ điều kiện giao nội địa theo hợp đồng demo → INVALID.

**Quan trọng:** `DOMESTIC_STANDARD` ở đây không phải default cho mọi Domestic thất bại express. Nó chỉ nhận Domestic còn **hợp lệ** về ID, city, country và cân nặng. Đây là cách viết guard giúp phân biệt “không đủ điều kiện express” với “dữ liệu không hợp lệ”.

### 7.2. International: readiness không thay thế validation

Hai guard của International:

```java
case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country) && customsReady
        -> "INTERNATIONAL_READY:" + id;

case International(var id, var country, var customsReady)
        when hasText(id) && hasText(country)
        -> "INTERNATIONAL_PENDING:" + id;
```

- `customsReady=true` nhưng country null/blank → cả hai guard false → INVALID.
- `customsReady=false` và dữ liệu hợp lệ → guard READY false; guard PENDING true.
- `customsReady=true` và dữ liệu hợp lệ → READY.

Đừng viết nhánh READY chỉ có `when customsReady` và bỏ validation: nó sẽ gắn nhãn READY cho dữ liệu thiếu ID/country. Nếu policy yêu cầu country thuộc một danh sách đã hỗ trợ, phải bổ sung validator đúng nghiệp vụ, không tự suy ra `hasText(country)` là đủ.

### 7.3. Pickup: phân biệt điều kiện con và fallback

`Pickup("P1",true)` và `Pickup("P2",false)` đều là Pickup hợp lệ, nhưng nhận nhãn khác nhau nhờ guard. `Pickup(null,true)` vẫn có subtype Pickup; pattern `Pickup(var id,var paid)` khớp record, nhưng `hasText(id)` false nên fallback INVALID.

Khi sửa code, test riêng **paid=true**, **paid=false**, **ID null** và **ID blank**. Nếu chỉ test paid=true, bạn sẽ không phát hiện trường hợp PENDING và fallback hoạt động sai.

## 8. Ba lỗi compile time điển hình khi tự viết when

Phần này có **các file cố ý sai** để xem thông báo compiler. Không trộn các file này vào chương trình chính vì chúng được thiết kế để **không biên dịch**.

### 8.1. Guarded case chưa đủ làm switch exhaustive

Tạo **`MissingFallback.java`**:

```java
class MissingFallback {
    sealed interface Job permits Build, Deploy {}
    record Build(int units) implements Job {}
    record Deploy() implements Job {}
    static String route(Job job) {
        return switch (job) {
            case Build(var units) when units > 0 -> "BUILD";
            case Deploy deploy -> "DEPLOY";
        };
    }
}
```

Chạy:

```bash
javac --release 21 MissingFallback.java
```

**Kết quả đã kiểm chứng:** `javac` từ chối vì `Build(units <= 0)` không được các case bao phủ; một nhánh guarded **không tự bảo đảm mọi giá trị của Build đều làm guard true**.

**Cách sửa hợp lý:** thêm fallback theo subtype:

```java
case Build(var units) when units > 0 -> "BUILD";
case Build ignored -> "INVALID_BUILD";
case Deploy deploy -> "DEPLOY";
```

Đây là **các nhãn case để thay trong hàm**, không phải tệp Java riêng.

### 8.2. Đặt case tổng quát trước case hẹp

Tạo **`DominatedGuard.java`**:

```java
class DominatedGuard {
    sealed interface Job permits Build {}
    record Build(int units) implements Job {}
    static String route(Job job) {
        return switch (job) {
            case Build build -> "ANY_BUILD";
            case Build(var units) when units > 0 -> "POSITIVE_BUILD";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 DominatedGuard.java
```

**Kết quả đã kiểm chứng:** compiler từ chối nhánh sau do *dominated case label*. Vì `case Build build` đã khớp mọi Build không null, nhánh `Build(...) when ...` phía sau không còn cơ hội chạy. Sửa bằng cách chuyển nhánh có guard lên trước và đặt nhánh tổng quát phía sau.

### 8.3. Dùng when sau instanceof

Tạo **`InvalidWhenInstanceof.java`**:

```java
class InvalidWhenInstanceof {
    static boolean test(Object value) {
        return value instanceof String text when !text.isBlank();
    }
}
```

Biên dịch:

```bash
javac --release 21 InvalidWhenInstanceof.java
```

**Kết quả đã kiểm chứng:** lỗi cú pháp. Trong Java 21, `when` được sử dụng cho **guarded pattern `case` trong switch**, không phải viết nối sau toán tử `instanceof`.

Với `instanceof`, dùng `&&`:

```java
static boolean isValidText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Phương thức sau là ví dụ hợp lệ có thể đặt trong class Java. Pattern variable `text` có scope ở vế phải của `&&` khi pattern bên trái khớp.

## 9. Cách viết when dễ đọc: từ biểu thức dài tới predicate có tên

Nếu một guard chứa quá nhiều quy tắc, nó trở thành đoạn code khó xem hơn một phương thức có tên rõ nghĩa. Đặt trường hợp validation:

```java
static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

vào helper là có ích vì:

- Tên hàm truyền tải ý định: giá trị có text không trắng.
- Điều kiện null an toàn được dùng thống nhất.
- Có thể viết test riêng cho null/empty/blank/normal text.
- Guard giữ focus vào quyết định phân tuyến chứ không lặp các chi tiết `value != null` ở mọi case.

Tương tự, nếu chính sách domestic tăng thêm nhiều điều kiện vùng, cân nặng tối đa, loại hàng, ngày giao, có thể định nghĩa một domain predicate:

```java
static boolean expressEligible(
        String id, String city, String country, int weightKg) {
    return hasText(id)
            && hasText(city)
            && "VN".equals(country)
            && weightKg > 0
            && weightKg <= 5
            && city.equalsIgnoreCase("HCM");
}
```

Sau đó:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when expressEligible(id, city, country, weightKg)
        -> "DOMESTIC_EXPRESS:" + id;
```

Hai đoạn này là **mảnh code minh họa**, không nằm trong class ở mục 6. Predicate `expressEligible` tái hiện đúng điều kiện express của chương trình đã chạy; nếu bạn dùng nó, vẫn phải bảo đảm nhánh STANDARD và INVALID tồn tại. Tách helper chỉ nên thực hiện khi nó **giảm độ phức tạp nhận thức**, không phải để giấu logic sai.

**Một lưu ý hiệu năng và side effect:** guard được đánh giá khi pattern khớp và có thể không được đánh giá nếu case trước đã được chọn. Tránh đưa thao tác mạng, ghi dữ liệu, cộng metric, chỉnh state vào guard, vì kết quả phụ thuộc thứ tự case và các điều kiện boolean. Khi xử lý side effect, nên chọn case trước rồi thực hiện hành động rõ ràng trong body hoặc service phù hợp.

## 10. Thứ tự guard và điều kiện biên

### 10.1. Trường hợp nhiều guard cùng đúng

Một request Express D1 thỏa cả điều kiện EXPRESS và STANDARD. Nó được phân loại EXPRESS vì **nhánh EXPRESS đứng trước**. Khi đọc một pattern switch, hãy xem toàn bộ thứ tự case, không chỉ guard cụ thể.

Hai guard có thể liên quan logic nhưng compiler **không chứng minh đầy đủ mọi quan hệ đại số/nghiệp vụ giữa các boolean expressions**. Do đó một switch sai thứ tự có thể vẫn compile và trả nhãn không mong muốn. Tests với dữ liệu thỏa nhiều guard là bắt buộc.

### 10.2. Ranh giới điều kiện

Trong bài, trọng lượng `5` được tính Express, `6` là Standard, `0` và `-1` invalid. Nếu ai đổi `weightKg <= 5` thành `weightKg < 5`, test `domestic express limit` sẽ thất bại.

Khi thiết kế test guard, cần ít nhất ba điểm cho mọi ngưỡng quan trọng: **dưới**, **bằng**, **trên**. Với boolean `paid` hoặc `customsReady`, thử cả true/false; với giá trị nullable, thử cả null.

### 10.3. So sánh chuỗi và locale

- `"VN".equals(country)` phân biệt chữ hoa/thường, không bị NPE nếu country null.
- `city.equalsIgnoreCase("HCM")` bỏ qua khác biệt chữ hoa/thường nhưng **không tự trim**. `" HCM "` không khớp HCM theo guard này.
- `String.isBlank()` nhận biết chuỗi rỗng hoặc toàn ký tự khoảng trắng theo định nghĩa của Java, nhưng **không tự loại whitespace trước các phép so sánh khác**.
- Không tự thay điều kiện bằng `toLowerCase()` mà không có chính sách locale/normalization; điều đó có thể đổi hành vi với một số dữ liệu Unicode.

### 10.4. Khi fallback trông như đang “nuốt lỗi”

Một default rộng như:

```java
default -> "INVALID";
```

trong sealed command/request hierarchy làm mất thông tin subtype nào thất bại. Ở bài này, fallback có tên riêng cho Domestic, International, Pickup. Điều đó giúp test và người đọc phân biệt **guard nào không được chọn** với **một subtype hoàn toàn mới chưa được xử lý**.

Nhưng fallback riêng cũng chỉ nói rằng request không đủ hợp đồng; nó không tự biết lý do chi tiết. Nếu cần hiển thị lỗi chính xác như country missing, weight invalid hoặc id missing, hãy dùng model kết quả giàu ngữ nghĩa hơn (ví dụ `ValidationError`) thay vì nhồi logic phụ trong guarded case.

## 11. Kiểm thử khi refactor from if/else sang when

Một bài tập thực tế là chuyển code có `if` thành guarded switch mà **không đổi hành vi**. Ví dụ nhánh Pickup truyền thống:

```java
static String routePickup(Pickup pickup) {
    if (!hasText(pickup.id())) return "INVALID:PICKUP";
    return pickup.paid()
            ? "PICKUP_READY:" + pickup.id()
            : "PICKUP_PENDING:" + pickup.id();
}
```

Đây là phương thức minh họa dành cho input Pickup **khác null**. Trong chương trình tổng hợp, `switch` đã có chính sách xử lý root null riêng.

Sau khi đổi sang guarded cases, test phải chứng minh:

- ID null: không NPE và INVALID.
- ID blank: INVALID.
- ID có text, `paid=true`: READY.
- ID có text, `paid=false`: PENDING.

Cách đánh giá tốt nhất không chỉ là so output của hai phiên bản; hai phiên bản có thể cùng sai. Hãy xác định expected từ hợp đồng độc lập, như phương thức `test(...)` của mục 6.

Trong codebase production, nếu case xử lý database hoặc gọi external service, phải kiểm thử **side effects** theo subtype và trạng thái, vì thay đổi lựa chọn nhánh có thể gây tác động ngoài chuỗi kết quả. Ví dụ bài này chỉ phân loại thành chuỗi nên không phát sinh side effect.

### Gợi ý chuyển bộ dữ liệu sang JUnit 5

Nếu đã cài JUnit Jupiter 5 trong dự án, có thể tách các lượt test thành các phương thức riêng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GuardedWhenPracticeTests {
    @Test
    void expressWeightAtBoundaryIsAccepted() {
        var input = new GuardedWhenPracticeDemo.Domestic(
                "D2", new GuardedWhenPracticeDemo.Address("HCM", "VN"), 5);
        assertEquals("DOMESTIC_EXPRESS:D2",
                GuardedWhenPracticeDemo.route(input));
    }

    @Test
    void missingNestedAddressUsesDomesticFallback() {
        var input = new GuardedWhenPracticeDemo.Domestic("D8", null, 2);
        assertEquals("INVALID:DOMESTIC",
                GuardedWhenPracticeDemo.route(input));
    }

    @Test
    void unpaidPickupIsPending() {
        var input = new GuardedWhenPracticeDemo.Pickup("P2", false);
        assertEquals("PICKUP_PENDING:P2",
                GuardedWhenPracticeDemo.route(input));
    }
}
```

**Đây là snippet JUnit minh họa**, cần dependency JUnit 5, cùng package với class chính và test runner phù hợp; **không** phải mã đã biên dịch bằng javac không có classpath JUnit. Chương trình chính mới là ví dụ độc lập đã được chạy và đối chiếu.

## 12. Các lỗi hay gặp khi viết guarded case

| Sai sót | Hệ quả | Cách tránh |
|---|---|---|
| Dùng `when` sau `instanceof` | Lỗi cú pháp | Với `instanceof` dùng `&&`, với switch dùng `case ... when ...` |
| Đặt nhánh tổng quát cùng subtype trước guard | Nhánh guard bị dominated hoặc logic bỏ qua | Sắp guard hẹp trước, fallback sau |
| Chỉ có guarded case mà không có nhánh còn lại | Switch expression có thể không exhaustive | Thêm fallback cùng subtype theo hợp đồng |
| Dùng `default` như một cách tắt lỗi exhaustive | Subtype mới có thể bị che | Với sealed hierarchy, liệt kê các subtype |
| Guard gọi method trên component null | Ném NPE | Đặt `hasText`/null guard trước |
| Cho rằng nested Address null vẫn match `Address(...)` | Dự đoán sai nhánh | Nhớ nested record pattern không match null |
| Cho rằng `var city` luôn non-null | Bỏ qua leaf null | Test `Address(null, ...)` |
| Đảo guard EXPRESS và STANDARD | Express bị phân loại thành Standard | Test input thỏa cả hai |
| Không test giá trị biên cân nặng | Lỗi `<`/`<=` không bị phát hiện | Test 4, 5, 6 kg và 0 |
| Dùng `||` thay `&&` trong validation | Có thể chấp nhận input thiếu field | Viết test từng field null/blank |
| Đưa side effect vào guard | Phụ thuộc thứ tự đánh giá, khó debug | Tách phân loại và xử lý |
| Viết guard quá dài, trùng lặp | Khó sửa và bảo trì | Tách predicate có tên khi cần |

### Phân biệt compile-time và runtime

- **Lỗi compile-time:** cú pháp `when` sai, pattern không applicable, scope của biến pattern sai, `case` bị dominated, switch expression không exhaustive.
- **Runtime no-match:** đúng cú pháp nhưng selector khác subtype, nested record null hoặc guard false.
- **Runtime exception:** ví dụ gọi phương thức trên field null khi guard chưa bảo vệ; không đồng nghĩa no-match.
- **Kết quả nghiệp vụ sai:** có case hợp lệ và guard true nhưng thứ tự nhánh hoặc quy tắc chọn nhãn sai.

Khi debug, nên đi theo thứ tự: **compiler → selector type/null → record structure → guard → case order → output**. Không sửa thông báo runtime bằng cách thêm default khi thực ra sai thứ tự case.

## 13. Bài tập thực hành thêm và hướng dẫn kiểm tra

### Bài A — Thêm giới hạn Express theo cân nặng

Thay ngưỡng Express từ 5 kg thành 3 kg, giữ các điều kiện khác.

**Kỳ vọng thay đổi:** `Domestic("D2", Address("HCM","VN"),5)` chuyển từ `DOMESTIC_EXPRESS:D2` sang `DOMESTIC_STANDARD:D2`. Giá trị 3 vẫn Express. Hãy sửa guard và expected tests cho phù hợp, thay vì sửa code rồi bỏ test cũ.

### Bài B — Thêm thành phố ưu tiên

Muốn Express cho city HCM **hoặc** DN, hãy thay điều kiện cuối thành:

```java
(city.equalsIgnoreCase("HCM") || city.equalsIgnoreCase("DN"))
```

**Cần giữ `hasText(city)` trước**, và đặt ngoặc cho nhóm `||` để các điều kiện chung về ID, country, weight vẫn áp dụng cho **cả hai** thành phố. Nếu viết `commonConditions && isHcm || isDn`, DN có thể được chấp nhận dù sai country/weight vì độ ưu tiên toán tử.

**Test gợi ý:** DN/1kg/VN → Express; DN/0kg/VN → Invalid; DN/1kg/TH → Invalid; DN/6kg/VN → Standard.

### Bài C — Chấp nhận country code không phân biệt hoa/thường

Thay `"VN".equals(country)` bằng một predicate có chính sách rõ:

```java
static boolean vietnamCountry(String country) {
    return country != null && country.equalsIgnoreCase("VN");
}
```

Khi dùng predicate này trong guard, test `country="vn"` sẽ thay đổi kết quả so với phiên bản gốc. **Đây là thay đổi yêu cầu nghiệp vụ**, không đơn thuần là format. Hãy cập nhật expected theo quyết định đã được duyệt.

### Bài D — Tạo subtype mới

Bổ sung `record Locker(String id, boolean codeSent) implements ShippingRequest {}` và cập nhật `permits`. Trước khi thêm case, chạy `javac --release 21`: compiler cần handler exhaustive cho subtype mới. Sau đó viết:

```java
case Locker(var id, var codeSent)
        when hasText(id) && codeSent -> "LOCKER_READY:" + id;
case Locker(var id, var codeSent)
        when hasText(id) -> "LOCKER_PENDING:" + id;
case Locker ignored -> "INVALID:LOCKER";
```

**Đây là gợi ý mở rộng**, cần đưa vào switch và khai báo đầy đủ, không phải đoạn đã được biên dịch trong chương trình ban đầu. Test ít nhất ba trường hợp: codeSent true/false và ID blank/null.

### Bài E — Chẩn đoán guard sai

Một người viết:

```java
case Domestic(var id, Address(var city, var country), var weightKg)
        when hasText(id) && hasText(city)
             && "VN".equals(country)
             && weightKg >= 0
        -> "DOMESTIC_STANDARD:" + id;
```

Tại sao `weightKg == 0` có thể bị chấp nhận?

**Đáp án:** vì thay `weightKg > 0` bằng `weightKg >= 0`. Guard nhìn vẫn hợp lệ, compiler không bắt lỗi; test `domestic zero weight` sẽ phát hiện.

### Bài F — Chuyển một if có side effect

Nếu code cũ cập nhật trạng thái sau khi kiểm tra `if (paid)`, có nên đưa chính thao tác cập nhật vào `when`?

**Đáp án:** Không nên. Guard nên diễn đạt **điều kiện**; side effect đặt ở phần thân case hoặc service. Khi đổi thứ tự nhánh hay guard false, side effect trong guard có thể thực thi khác dự kiến.

## 14. Checklist trước khi hoàn tất một guarded switch

1. **Cú pháp:** Guard nằm đúng sau case pattern bằng `when`, trước dấu `->`?
2. **Kiểu:** Selector và pattern compatible với nhau ở compile time?
3. **Record:** Component pattern đúng số lượng/thứ tự/type của record?
4. **Scope:** Biến pattern chỉ dùng ở guard và phần thân nhánh nơi nó đã được bind?
5. **Null:** Root null có chính sách rõ? Nested record null và leaf null đã được test?
6. **Guard:** Điều kiện có null-safe, dùng đúng `&&`/`||`, ngoặc và thứ tự short-circuit?
7. **Thứ tự:** Nhánh ưu tiên và cụ thể trước, fallback tổng quát sau?
8. **Exhaustiveness:** Mọi subtype của sealed type có đường đi, không thêm default thừa?
9. **Boundary:** Đã test tại điểm ngưỡng và ngay hai phía?
10. **Nhãn:** Expected output có được xác định từ hợp đồng độc lập?
11. **Tính dễ đọc:** Guard có biểu đạt chính sách, hoặc cần tách helper với tên rõ?
12. **Side effects:** Guard có giữ thuần tính và không thực hiện thao tác ngoài ý muốn?
13. **Build:** `javac --release 21` chạy thành công với tệp/class đúng tên?
14. **Regression:** Từng guarded case có ít nhất một test chọn được và một test guard false?

## 15. Tự kiểm tra kiến thức

**1. `when` được đánh giá trước hay sau record pattern?**

Sau. Nếu pattern không khớp, guard không được đánh giá.

**2. `Domestic("D8",null,2)` có đi qua guard dùng `Address(...)` không?**

Không. Nested record pattern không khớp khi Address null; fallback Domestic xử lý.

**3. `Domestic("D7",Address(null,"VN"),2)` có cùng nguyên nhân với địa chỉ null không?**

Không. Address tồn tại và `var city` bind null; guard `hasText(city)` false.

**4. Vì sao cần nhánh `case Domestic ignored` dù đã có hai guarded cases Domestic?**

Vì cả hai guard có thể false. Fallback bao phủ Domestic không hợp lệ và giúp switch exhaustive.

**5. `Domestic("D2",Address("HCM","VN"),5)` đi vào nhánh nào?**

DOMESTIC_EXPRESS do dấu `<= 5`. Giá trị đúng bằng ngưỡng được chấp nhận.

**6. Có thể viết `input instanceof String s when !s.isBlank()` không?**

Không. Trong `instanceof` dùng `&&`; `when` thuộc guarded case của switch.

**7. Nếu đặt case Domestic tổng quát trước các guarded cases, điều gì xảy ra?**

Nhánh tổng quát bao phủ Domestic trước, khiến các case hẹp sau bị dominated; compiler có thể từ chối.

**8. Vì sao không thêm default khi sealed hierarchy đã có đủ fallback mỗi subtype?**

Vì default có thể che thiếu xử lý khi bổ sung một subtype mới, làm mất lợi ích exhaustive check.

**9. Có thể viết guard với `||` không?**

Có. Guard là một boolean expression; phải dùng ngoặc và lưu ý short-circuit/độ ưu tiên để không vô tình bỏ qua điều kiện chung.

**10. Vì sao một guarded switch biên dịch được vẫn cần unit test?**

Compiler kiểm tra cú pháp/kiểu/scope/exhaustiveness, không chứng minh ngưỡng cân nặng, thành phố ưu tiên hoặc điều kiện validation là đúng yêu cầu.

## Kết luận

Viết guarded case bằng `when` hiệu quả nhất khi bạn xây quyết định thành **từng tầng rõ nghĩa**: pattern nhận subtype và dữ liệu, guard kiểm tra điều kiện, nhánh có ưu tiên được đặt trước, rồi fallback cùng subtype xử lý phần còn lại. Với Java 21, record patterns và sealed switch giúp giảm cast, kiểm tra đầy đủ kiểu và thể hiện rule gần dữ liệu.

Trong bài thực hành này, ba subtype Domestic/International/Pickup minh họa đủ các tình huống: guard true/false, record lồng nhau, null root và null component, điều kiện biên, short-circuit, dominance và exhaustiveness. Hãy xem **test expected độc lập** là phần bắt buộc của bài giải, chứ không chỉ là bước phụ sau khi code compile.

## Tài liệu tham khảo chính thức

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [Java Language Specification SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
