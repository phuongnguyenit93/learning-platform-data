# Đặt behavior ở domain type hay switch?

**Bối cảnh:** Thiết kế domain model trong Java, đặc biệt khi dữ liệu được biểu diễn bằng `sealed interface` và các `record`, còn phía sử dụng có thể dùng pattern matching cho `switch` (Java 21).

## 1. Câu hỏi thiết kế

Giả sử một ứng dụng có nhiều kiểu chính sách giảm giá: giảm theo phần trăm hoặc giảm theo số tiền cố định. Ta cần hai việc:
- **Tính số tiền giảm và số tiền phải trả** theo quy tắc nghiệp vụ.
- **Tạo nhãn hiển thị** cho báo cáo, ví dụ `"Percent 10%"` hay `"Fixed 175c"`.

Có hai hướng tổ chức behavior:
1. **Behavior nằm trong domain type:** Mỗi subtype có phương thức riêng thực hiện cùng một contract. Bên gọi dùng **đa hình** (*polymorphism*): `policy.discountCents(subtotal)`.
2. **Behavior nằm ngoài domain type:** Một hàm ở bên tiêu thụ dùng **pattern switch** để tách subtype rồi thực hiện công việc tương ứng: `switch (policy) { case Percent(...); case Fixed(...); }`.

Cả hai đều là Java hợp lệ. Quyết định tốt phụ thuộc **ai sở hữu quy tắc**, **hướng phụ thuộc giữa module**, và hệ thống hay thay đổi theo trục **loại dữ liệu** hay **thao tác**. Không nên kết luận `switch` luôn là code smell, cũng không nên đưa mọi phương thức vào entity chỉ để tránh `switch`.

**Mục tiêu bài học:** Sau khi học, bạn sẽ phân biệt domain behavior với hành vi của consumer, hiểu ưu/nhược điểm của đa hình và pattern switch, chọn vị trí behavior trong một domain model có nhiều subtype, xử lý đúng `sealed`, `record`, null và exhaustive switch, đồng thời nhận diện các anti-pattern khi refactor.

**Phiên bản:** Ví dụ sử dụng **Java 21**. Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) đều là tính năng chính thức từ Java 21, không cần `--enable-preview`.

## 2. Phân biệt domain behavior và hành vi của consumer

**Domain behavior** diễn đạt quy tắc cốt lõi của một khái niệm nghiệp vụ: ví dụ một chính sách tính mức giảm, đơn hàng kiểm tra điều kiện hủy, hoặc số dư kiểm tra điều kiện rút tiền. Nó thường liên quan trực tiếp đến **domain invariant**: điều kiện phải luôn đúng để mô hình không ở trạng thái bất hợp lệ.

Ví dụ invariant của chính sách giảm giá trong bài:
- Tỷ lệ giảm từ **0 đến 100** phần trăm.
- Số tiền giảm cố định **không âm**.
- Tổng tiền đầu vào trong bài **không âm**.
- Mức giảm áp dụng **không vượt subtotal** và số tiền còn trả không âm.

Các rule này cần đúng dù giao dịch được tạo từ web, mobile hay API khác. Nếu mỗi controller hoặc giao diện đều tự tính lại, nguy cơ lệch logic rất cao.

**Consumer behavior** phục vụ một mục đích sử dụng của dữ liệu domain, không nhất thiết là trách nhiệm của domain object. Ví dụ:
- Hiển thị nhãn hoặc bản dịch trên UI.
- Mapping sang DTO/JSON cho đối tác.
- Tạo hàng trong báo cáo kế toán.
- Chọn template email, tạo thông tin audit.
- Chuyển dữ liệu sang một định dạng hoặc giao thức hạ tầng.

Những hoạt động này **đọc dữ liệu domain**, nhưng không vì thế mà `DiscountPolicy` phải biết HTML, i18n, REST, database hay hệ thống gửi email.

### Một phép thử nhanh

Hỏi: **“Nếu thay giao diện, database hoặc API bên ngoài, quy tắc này vẫn bắt buộc đúng chứ?”**

- Nếu **có**, behavior có xu hướng thuộc domain type hoặc domain service.
- Nếu **không**, nó có thể thuộc application service, mapper, presentation hoặc adapter.
- Nếu rule nghiệp vụ cần phối hợp nhiều entity mà không có một owner tự nhiên, **domain service** có thể phù hợp hơn việc ép một entity gánh tất cả.

Phân loại này là gợi ý thiết kế, không phải quy tắc cứng.

## 3. Mô hình DiscountPolicy

Một sealed hierarchy đơn giản:

```text
DiscountPolicy (sealed interface)
├── Percent(rate)        — record
└── Fixed(amountCents)  — record
```

`DiscountPolicy` mô tả contract tính giảm giá; `Percent` và `Fixed` là hai biến thể dữ liệu cùng behavior nhưng công thức khác nhau.

### Đặt công thức nghiệp vụ vào subtype

```java
// Minh họa cấu trúc domain; chương trình chạy đầy đủ ở phần 5.
sealed interface DiscountPolicy permits Percent, Fixed {
    int discountCents(int subtotalCents);

    default int payableCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return subtotalCents - discountCents(subtotalCents);
    }
}
```

Cả hai subtype phải thực hiện `discountCents`:

```java
record Percent(int rate) implements DiscountPolicy {
    Percent {
        if (rate < 0 || rate > 100) {
            throw new IllegalArgumentException("rate must be 0..100");
        }
    }

    @Override
    public int discountCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return (int) (((long) subtotalCents * rate) / 100);
    }
}

record Fixed(int amountCents) implements DiscountPolicy {
    Fixed {
        if (amountCents < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }

    @Override
    public int discountCents(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return Math.min(subtotalCents, amountCents);
    }
}
```

**Điểm thiết kế quan trọng:**

- **Đa hình:** `policy.discountCents(subtotal)` gọi implementation thích hợp dựa trên subtype runtime. Caller không cần `instanceof` hoặc cast.
- **Validation ngay khi tạo:** Compact constructor của mỗi record từ chối policy không hợp lệ, tránh lặp validation ở các consumer. Với record này, component là primitive nên không có vấn đề reference null.
- **Mức giảm không vượt subtotal:** Chính sách cố định dùng `Math.min`; tỷ lệ nằm trong 0..100 nên số giảm không vượt subtotal.
- **Phép tính tránh overflow trung gian:** Ép `subtotalCents` sang `long` trước khi nhân với phần trăm. Với `subtotalCents` không âm trong miền `int` và rate 0..100, kết quả sau chia 100 nằm trong `int`.
- **Làm tròn:** Phép chia nguyên với số không âm lấy phần nguyên của số cent; đây là *chính sách làm tròn minh họa*, không mặc nhiên phù hợp mọi loại tiền tệ.
- **Tên method theo ngôn ngữ domain:** `discountCents` và `payableCents` mô tả một khả năng nghiệp vụ, không gắn với UI hoặc adapter cụ thể.

Mã dùng `int` đơn vị cent cho dễ học. Hệ thống tiền tệ thật cần thống nhất tiền tệ, độ chính xác, chính sách làm tròn và có thể dùng value object hoặc `BigDecimal`.

**Lưu ý về record:** `record` thích hợp cho các value types bất biến ở mức field như cấu hình chính sách. Không nên mặc định chuyển mọi entity có identity, vòng đời và trạng thái thay đổi thành record.

## 4. Behavior hiển thị ở bên ngoài: pattern switch

Một hệ thống báo cáo muốn diễn đạt mỗi policy bằng nhãn. Nhãn có thể là hành vi của **presentation/adapter**, không phải quy tắc giảm giá. Với Java 21, ta có thể viết:

```java
// Đoạn minh họa trong một lớp sử dụng DiscountPolicy:
static String viewLabel(DiscountPolicy policy) {
    return switch (policy) {
        case Percent(int rate) -> "Percent " + rate + "%";
        case Fixed(int amountCents) -> "Fixed " + amountCents + "c";
        case null -> "No policy";
    };
}
```

Đây là **external operation** dùng **record patterns**. `case Percent(int rate)` phân loại object `Percent` và ràng buộc component `rate` trong một bước; không cần cast. Tương tự với `Fixed`.

`DiscountPolicy` là `sealed`, chỉ có hai record subtype `Percent` và `Fixed`; cả hai là kiểu final. Vì vậy `switch expression` đã xử lý đầy đủ mọi giá trị khác null của hierarchy. `case null` xử lý riêng selector null, không cần `default` trong ví dụ này.

**Vì sao không thêm `viewLabel()` vào domain type?** Nhãn `Percent 10%` có thể chỉ phục vụ một loại báo cáo. Sau này UI cần bản dịch tiếng Việt, báo cáo tài chính cần mã `PCT`, còn API đối tác cần DTO. Nếu tất cả biến thể phải có `renderHtml`, `toPartnerJson`, `accountingLabel`, domain API sẽ bị kéo theo các thay đổi bên ngoài. Consumer-specific pattern switch giúp mỗi adapter sở hữu cách biểu diễn riêng.

**Không đánh đồng quyền đọc dữ liệu với sở hữu quy tắc:** External `switch` đọc `rate` hoặc `amountCents` để tạo nhãn, nhưng không nên tự viết lại công thức tính giảm giá ở mọi adapter.

## 5. Chương trình hoàn chỉnh Java 21: kết hợp hai cách

Tạo file **`DomainBehaviorPlacementDemo.java`**:

```java
public class DomainBehaviorPlacementDemo {
    sealed interface DiscountPolicy permits Percent, Fixed {
        int discountCents(int subtotalCents);

        default int payableCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return subtotalCents - discountCents(subtotalCents);
        }
    }

    record Percent(int rate) implements DiscountPolicy {
        Percent {
            if (rate < 0 || rate > 100) {
                throw new IllegalArgumentException("rate must be 0..100");
            }
        }

        @Override
        public int discountCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return (int) (((long) subtotalCents * rate) / 100);
        }
    }

    record Fixed(int amountCents) implements DiscountPolicy {
        Fixed {
            if (amountCents < 0) {
                throw new IllegalArgumentException("negative amount");
            }
        }

        @Override
        public int discountCents(int subtotalCents) {
            if (subtotalCents < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            return Math.min(subtotalCents, amountCents);
        }
    }

    static String viewLabel(DiscountPolicy policy) {
        return switch (policy) {
            case Percent(int rate) -> "Percent " + rate + "%";
            case Fixed(int amountCents) -> "Fixed " + amountCents + "c";
            case null -> "No policy";
        };
    }

    static void report(DiscountPolicy policy, int subtotalCents) {
        System.out.println(
            viewLabel(policy)
                + ": discount=" + policy.discountCents(subtotalCents)
                + ", payable=" + policy.payableCents(subtotalCents));
    }

    public static void main(String[] args) {
        int subtotal = 1000;
        report(new Percent(10), subtotal);
        report(new Fixed(175), subtotal);
        report(new Fixed(1200), subtotal);
        System.out.println(viewLabel(null));

        try {
            new Percent(101);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid rate");
        }

        try {
            new Fixed(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected negative amount");
        }
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 DomainBehaviorPlacementDemo.java
java DomainBehaviorPlacementDemo
```

Kết quả stdout:

```text
Percent 10%: discount=100, payable=900
Fixed 175c: discount=175, payable=825
Fixed 1200c: discount=1000, payable=0
No policy
Rejected invalid rate
Rejected negative amount
```

### Phân tích kết quả

| Đầu vào | Quy tắc ở domain | Kết quả |
| --- | --- | --- |
| Subtotal 1000 cent, `Percent(10)` | 10% của 1000 = 100 | Còn trả 900 |
| Subtotal 1000 cent, `Fixed(175)` | Giảm 175 cent | Còn trả 825 |
| Subtotal 1000 cent, `Fixed(1200)` | Giảm tối đa bằng subtotal | Còn trả 0 |
| `viewLabel(null)` | Quy tắc hiển thị cho phép thiếu policy | `No policy` |
| `Percent(101)` | Constructor từ chối rate lớn hơn 100 | `Rejected invalid rate` |
| `Fixed(-1)` | Constructor từ chối số tiền âm | `Rejected negative amount` |

**Quan sát quan trọng:**
1. `report` gọi `policy.discountCents` và `policy.payableCents`, không cần biết đó là `Percent` hay `Fixed`.
2. `viewLabel` dùng `switch` vì logic của nó là **cách trình bày** hai biến thể, không phải công thức tiền.
3. Cả constructor và các hàm tính đều thực thi điều kiện hợp lệ, tránh việc một lớp ngoài có thể dùng một policy với tham số sai mà không kiểm tra.
4. `viewLabel(null)` được hỗ trợ, nhưng `report(null, ...)` không được phép theo contract đang dùng: gọi method trên null sẽ gây `NullPointerException`. Biên nhận dữ liệu nên có chính sách null rõ ràng, chẳng hạn kiểm tra `Objects.requireNonNull(policy)`.

Để trình bày trong một file chạy độc lập, `viewLabel` được đặt cạnh model. Khi tổ chức project thật, có thể chuyển nó sang package báo cáo/adapter; domain core không cần phụ thuộc vào cách định dạng nhãn.

## 6. Có thể đặt toàn bộ công thức trong switch không?

Về mặt Java, có thể viết một hàm ngoài domain type để tính tiền bằng pattern `switch`:

```java
// ĐOẠN MINH HỌA alternative design: không thêm vào chương trình phần 5
// khi đã có discountCents, để tránh duy trì trùng hai công thức.
static int discountViaSwitch(
        DiscountPolicy policy, int subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("negative subtotal");
    }

    return switch (policy) {
        case Percent(int rate) ->
            (int) (((long) subtotalCents * rate) / 100);
        case Fixed(int amountCents) ->
            Math.min(subtotalCents, amountCents);
        case null ->
            throw new IllegalArgumentException("Missing policy");
    };
}
```

Đoạn này là một **lựa chọn thiết kế khác**, không phải một phần cần chạy trong ví dụ hoàn chỉnh. Nó hợp lệ về cú pháp trong phạm vi có các kiểu đã định nghĩa.

**Vấn đề không nằm ở từ khóa `switch`.** Vấn đề xảy ra nếu nhiều module tự tính lại cùng business rule:

```text
API controller  -> switch policy -> tự tính giảm giá
Batch processor -> switch policy -> tự tính giảm giá
Checkout UI     -> switch policy -> tự tính giảm giá
```

Nếu đổi cách làm tròn hoặc cách chặn mức giảm mà không sửa đồng bộ cả ba, kết quả có thể sai khác. Khi phép tính thuộc domain do ta kiểm soát, tập trung nó vào `DiscountPolicy`/subtype hoặc một domain service là giải pháp có tính nhất quán tốt hơn.

**Tình huống external switch vẫn hợp lý:** dữ liệu là DTO từ một SDK bên ngoài mà không thể sửa, operation chỉ dùng trong một consumer, hoặc nghiệp vụ phối hợp nhiều đối tượng không có một owner tự nhiên. Khi ấy đặt thuật toán tại một domain service riêng vẫn có thể giữ đúng ranh giới nghiệp vụ mà không phải chèn method vào các DTO.

## 7. Bảng so sánh domain method và external pattern switch

| Tiêu chí | Domain type + đa hình | External pattern switch |
| --- | --- | --- |
| Ví dụ | `policy.discountCents(subtotal)` | `case Percent(int rate) -> ...` |
| Vị trí behavior | Gắn với contract của type/subtype | Ở consumer/service/adapter |
| Thích hợp | Rule nghiệp vụ, invariant, hành vi chung bền vững | Mapping, hiển thị, phân loại, operation của consumer |
| Phụ thuộc của caller | Chủ yếu vào interface/contract | Biết các subtype cụ thể |
| Thêm subtype | Subtype mới phải triển khai abstract method | Các switch exhaustive có thể phải thêm case |
| Thêm operation | Thêm method vào API có thể kéo theo thay đổi subtype | Thêm một hàm/switch riêng mà không sửa subtype |
| Compiler hỗ trợ | Báo thiếu method implementation | Báo thiếu coverage trên hierarchy phù hợp |
| Rủi ro | Domain phình to vì UI/transport concern | Rule domain bị rải trong nhiều consumer |
| Null | Caller cần object để gọi method | Có thể xử lý bằng `case null` theo nhu cầu |
| Kiểm thử | Unit test từng policy và contract | Test từng mapping, fallback và biến thể |

Những điểm này **không tuyệt đối**: Java interface có `default method` giúp chia sẻ hành vi; switch không buộc phải dùng mọi nơi; một domain service ngoài entity vẫn có thể là nơi đặt business behavior đúng. Mục tiêu là giảm coupling và tránh nhân bản rule.

## 8. Hai trục thay đổi: nhiều subtype hay nhiều operation?

Đây là một cách nhìn của **expression problem**: một thiết kế dễ thêm **biến thể dữ liệu** có thể không thuận tiện bằng khi thêm **thao tác mới**, và ngược lại.

### 8.1. Thường thêm loại policy mới, contract ít đổi

Ví dụ bổ sung `Tiered`, `Loyalty` hay `CampaignBased` nhưng mọi policy vẫn cần trả lời `discountCents(subtotal)`.

Đa hình có lợi: code checkout chỉ gọi cùng API, không phải thêm chuỗi `if (policy instanceof ...)` mỗi khi có subtype. Subtype mới chịu trách nhiệm triển khai công thức.

**Lưu ý:** Nếu hierarchy là `sealed`, ta vẫn phải cập nhật `permits` và các external exhaustive switches (ví dụ nhãn báo cáo). Đa hình không bảo đảm “thêm kiểu mà không sửa bất cứ nơi nào”; nó giúp **ổn định bên gọi của core behavior**.

Nếu cần hỗ trợ plugin của đối tác mở rộng subtype tùy ý, một interface có khả năng mở rộng hoặc Strategy pattern có thể phù hợp hơn sealed hierarchy. Khi tập subtype mở, external `switch` không thể dựa vào một danh sách kiểu lá đóng kín để bảo đảm exhaustive.

### 8.2. Subtype ổn định nhưng nhiều thao tác mới

Giả sử `Percent` và `Fixed` là hai kiểu cố định, còn các consumer liên tục yêu cầu:
- Nhãn cho web.
- Bản dịch trên mobile.
- Mapping sang DTO kế toán.
- Định dạng log hỗ trợ vận hành.
- Mã phân loại trong báo cáo.

Đặt tất cả `toMobileLabel`, `toAccountingJson`, `toAuditRow` lên `DiscountPolicy` có thể làm interface bị phình. Mỗi consumer có thể tạo một **external operation** trên sealed hierarchy, dùng pattern `switch` và được compiler nhắc nếu xuất hiện subtype mới.

**Giới hạn:** Nhiều operation trình bày khác nhau là hợp lý; nhiều implementation của **cùng phép tính nghiệp vụ** thì không nên.

### 8.3. Cả kiểu và thao tác đều biến động

Trong hệ thống lớn, có thể kết hợp:
- Core interface giữ những behavior lâu bền nhất.
- Các subtype chứa rule cục bộ và kiểm tra invariant.
- Domain services tập trung rule liên quan nhiều khái niệm.
- Presentation/integration adapters dùng pattern switch khi cần đọc cụ thể từng subtype.
- Unit và integration tests kiểm tra các contract giữa module.

Đừng chọn một phong cách tuyệt đối. Hãy quan sát **khi thay đổi một yêu cầu, bao nhiêu file và bao nhiêu lớp phải sửa**, và nơi nào dễ có bug nhất.

## 9. Domain service là lựa chọn thứ ba

Câu hỏi “domain type hay switch?” không nhất thiết chỉ có hai đáp án.

Một business rule có thể liên quan đến **nhiều entity**: hạn mức tài khoản, quyền lợi khách hàng, lịch sử đơn hàng, ngày áp dụng khuyến mại. Không phải lúc nào cũng tự nhiên đặt toàn bộ rule lên `Order` hoặc `DiscountPolicy`.

Khi không có một owner đối tượng rõ ràng, **domain service** có thể chứa thuật toán nghiệp vụ (thuần hoặc phụ thuộc vào các abstraction thích hợp), còn **application service** điều phối transaction, đọc repository và gọi adapter.

Ví dụ luồng xử lý:

```text
API/Controller
    -> Application service
        -> Repository: lấy Order, Customer, DiscountPolicy
        -> Domain service: kiểm tra quy tắc phối hợp
        -> DiscountPolicy.discountCents(): rule của từng policy
        -> Repository: lưu kết quả
    -> Presentation mapper: switch policy để tạo DTO
```

Nguyên tắc là **hướng phụ thuộc**: domain nên không cần biết giao thức HTTP, thư viện persistence, định dạng HTML hoặc nhà cung cấp email để thực thi rule nghiệp vụ. Switch trong domain service không tự sai; nhưng một switch trong controller tự quyết định mọi bất biến của domain thường là tín hiệu thiết kế cần xem lại.

## 10. Khi nào nên dùng switch trong domain?

Một external pattern switch cũng có thể hợp lý **ngay trong domain** khi:

1. Thao tác là một phép **chuyển đổi/phân loại một lần** trên tập biến thể đóng kín, không cần trở thành contract cho mọi subtype.
2. Các type dữ liệu là DTO/value objects từ thư viện khác mà domain không sở hữu, không thể thêm method vào từng lớp.
3. Một thuật toán liên quan đồng thời đến nhiều biến thể, không có một object tự nhiên sở hữu toàn bộ behavior.
4. Domain có một tập dữ liệu đóng kín, trong khi **operation** được bổ sung thường xuyên hơn kiểu dữ liệu.
5. Cần kiểm soát exhaustiveness bằng compiler thay vì cast/`if` thủ công.

Ví dụ một hoạt động kiểm toán độc lập có thể tạo mã phân loại như sau:

```java
// Đoạn minh họa của một lớp dùng DiscountPolicy:
static String auditCategory(DiscountPolicy policy) {
    return switch (policy) {
        case Percent(var rate) -> "RATE_BASED";
        case Fixed(var amountCents) -> "AMOUNT_BASED";
        case null -> "NONE";
    };
}
```

Nếu mã `RATE_BASED` chỉ phục vụ hệ thống audit, không cần ép mỗi policy có một method `auditCategory()`. Nếu nó trở thành phân loại pháp lý cốt lõi mà mọi hệ thống phải thống nhất, cân nhắc nâng nó thành khái niệm domain hoặc một domain service dùng chung.

## 11. Những anti-pattern khi đặt behavior

### 11.1. Anemic domain model: toàn bộ rule nằm ngoài

Một tín hiệu đáng chú ý là entity/value object chỉ chứa getter, còn mọi controller và batch job đều viết:

```java
// Mã minh họa một cấu trúc dễ bị lặp:
if (policy instanceof Percent p) {
    // Tính giảm theo phần trăm ở consumer A
} else if (policy instanceof Fixed f) {
    // Tính giảm cố định ở consumer A
}
// Consumer B/C lại copy thuật toán tương tự.
```

Nếu logic này thật sự là **cùng một core business rule**, việc nhân bản dễ làm kết quả checkout, batch và API lệch nhau. Hãy tìm contract domain như `discountCents` và chuyển rule về đúng owner.

**Không nhầm:** Một domain model chủ yếu mang immutable data **không tự là anemic** nếu nó được thiết kế có chủ ý và nghiệp vụ nằm trong domain services có trách nhiệm rõ ràng. Vấn đề nằm ở sự phân tán và thiếu quyền sở hữu rule, không chỉ ở số lượng method trên record.

### 11.2. Fat domain model: nhồi mọi chi tiết ngoài domain

Một cực đoan khác là entity có `sendEmail()`, `renderHtml()`, `toPartnerJson()` và `saveToDatabase()`. Những method đó có thể kéo domain vào phụ thuộc hạ tầng, làm khó kiểm thử, khó đổi UI/SDK.

Thay vào đó, giữ domain API tập trung vào nghĩa nghiệp vụ. Đặt mapping, giao thức I/O và việc định dạng ở các adapter; dùng pattern switch khi thật sự cần phân biệt subtype.

### 11.3. Switch khổng lồ và fallback che lỗi

Nếu một `switch` có nhiều case dài hàng trăm dòng, chứa truy cập database, logging, retry và quy tắc nghiệp vụ, nên tách các phương thức xử lý rồi chỉ giữ switch để điều phối. Trên sealed hierarchy, tránh thêm `default` vô điều kiện khi yêu cầu quan trọng là **phát hiện subtype chưa được hỗ trợ** sau khi thêm kiểu mới.

### 11.4. Lạm dụng pattern vì cú pháp ngắn

`case Percent(int rate)` có thể đọc component đẹp hơn, nhưng **pattern matching không tự thay behavior**. Một method call domain vẫn rõ ràng và phù hợp hơn khi bên gọi chỉ cần kết quả `discountCents`. Không suy diễn switch sẽ nhanh hơn dynamic dispatch; muốn đánh giá hiệu năng phải đo trên use case thực tế.

## 12. Sealed, null, record và giới hạn cần nhớ

**Sealed không phải bất biến sâu.** `sealed` kiểm soát subtype; `record` tạo các field final, nhưng nếu record chứa reference tới object mutable thì object được tham chiếu vẫn có thể thay đổi. Trong ví dụ `Percent` và `Fixed` chỉ có `int` nên tránh được vấn đề này.

**Exhaustiveness của switch.** Với `DiscountPolicy` sealed và `Percent`/`Fixed` final, Java 21 có thể xác nhận `switch expression` có case cho mọi subtype. Nếu thêm một subtype mới mà chưa thêm case, lần biên dịch tiếp theo có thể báo switch không exhaustive. Trong hệ thống dùng non-sealed hoặc interface mở, việc liệt kê vài subtype không bảo đảm đã bao phủ hết.

**Selector null và method call null khác nhau.** `case null` của `viewLabel` nhận null có chủ ý. `policy.discountCents` cần một object; gọi trên null sẽ thất bại. Domain API cần nêu rõ có chấp nhận input null hay không.

**Record deconstruction chỉ áp dụng cho record.** Đối với class thường, có thể dùng type pattern như `case SomeClass x` rồi gọi phương thức của class đó, không tự tạo ra `SomeClass(...)` nếu nó không phải record.

**Domain logic và format.** Chương trình minh họa trả tiền theo `cent` bằng `int`. Dự án thật nên có kiểu tiền tệ và các quy tắc chính xác về rounding, scale, currency; đừng đặt chúng trong formatter chỉ vì formatter có switch.

## 13. Kiểm thử và quy trình quyết định

### Test domain behavior

Nên kiểm thử:
- `Percent(0)`, `Percent(100)`, subtotal bằng 0 và subtotal lớn.
- `Fixed` nhỏ hơn, bằng hoặc lớn hơn subtotal.
- `Percent(-1)`, `Percent(101)`, `Fixed(-1)` phải bị từ chối.
- Subtotal âm phải bị từ chối; tổng tiền phải trả không âm.
- Làm tròn theo đơn vị tiền phù hợp đặc tả.

### Test external operation

Nên kiểm thử:
- Nhãn đúng cho `Percent` và `Fixed`.
- `null` có hành vi theo contract.
- Khi thêm subtype mới, build/test yêu cầu cập nhật mapping tương ứng.
- Formatter không tự thay đổi business calculation.

### Checklist review trước khi chọn nơi đặt behavior

1. Rule này có phải **invariant hoặc core domain contract** không? Nếu có, ưu tiên domain type/domain service.
2. Nó có thuộc **format, UI, API đối tác hoặc infrastructure** không? Nếu có, cân nhắc adapter/consumer.
3. Bên gọi có cần biết subtype để sử dụng rule không? Nếu không, đa hình giúp giữ caller đơn giản.
4. Hierarchy có **sealed/đóng kín** và do team sở hữu không? Nếu có, pattern switch giúp operation bên ngoài exhaustive.
5. Hệ thống hay **thêm variants** hay **thêm operations**? Chọn cấu trúc giúp giảm nơi phải sửa theo trục thường đổi hơn.
6. Có **nhiều consumer tự lặp cùng công thức** không? Nếu có, nên tập trung rule domain.
7. Rule liên quan nhiều entity, không có một owner? Hãy xét **domain service**.
8. Đặt method lên type có kéo domain phụ thuộc HTTP, DB, email, i18n không? Nếu có, xem lại ranh giới.
9. Pattern switch có che subtype mới bằng default không? Nếu yêu cầu coverage tường minh, hãy giữ compile-time checking.
10. Đã có unit/integration tests để kiểm tra hành vi và hệ quả thay đổi chưa?

## 14. Bài tập thực hành

**Bài tập 1 — Thêm một variant:** Bổ sung `record Bonus(int points) implements DiscountPolicy` và cập nhật `permits` của `DiscountPolicy`. Quy định `Bonus` giảm theo điểm, tối đa bằng subtotal, và `points` phải không âm. Hãy giải thích vì sao `report` vẫn gọi đúng `discountCents` mà không cần xử lý subtype bằng cast, nhưng `viewLabel` phải có case `Bonus` mới để tiếp tục exhaustive.

**Bài tập 2 — Thêm một operation:** Tạo hàm `accountingCode(DiscountPolicy policy)` ở lớp tích hợp, trả `PCT`, `FIX` hoặc `NONE`. Dùng `switch` và giải thích vì sao không cần đưa mã kế toán vào từng record nếu đó là quy ước riêng của đối tác.

**Bài tập 3 — Phân tích dependency:** Một nhóm đề xuất thêm `sendDiscountEmail()` vào `Percent` và `Fixed`. Hãy liệt kê những dependency có thể xuất hiện: email gateway, template, localization, retry. Đề xuất một application service dùng domain data và một adapter email, có thể chọn template bằng pattern switch bên ngoài domain.

**Bài tập 4 — Domain service:** Một chương trình ưu đãi cần xét `DiscountPolicy`, lịch sử đơn hàng và hạng khách hàng. Hãy phân biệt domain service tính quyền lợi với application service lấy dữ liệu từ repository, mở transaction và gọi domain service. Nêu lý do không nên ép toàn bộ use case thành method của `Percent` hoặc `Fixed`.

## 15. Kết luận

**Đặt behavior ở domain type** khi nó là khả năng cốt lõi của đối tượng, bảo vệ invariant hoặc tạo contract chung lâu dài giữa nhiều subtype. **Đặt behavior ở consumer bằng pattern `switch`** khi operation chủ yếu là biểu diễn, mapping hoặc phân loại dữ liệu cho một nhu cầu bên ngoài trên tập kiểu đã biết. **Dùng domain service** khi nghiệp vụ phối hợp nhiều khái niệm và không thuộc tự nhiên một type.

Không chọn theo cú pháp ngắn nhất. Hãy chọn theo **ownership của business rule, hướng dependency, trục thay đổi và khả năng kiểm thử**. Java 21 hỗ trợ cả đa hình truyền thống và pattern matching an toàn; kết hợp đúng chỗ thường tốt hơn áp dụng cực đoan một phía.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
