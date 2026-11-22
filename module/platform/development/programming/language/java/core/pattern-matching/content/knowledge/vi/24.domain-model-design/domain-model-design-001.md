# Chọn interface hay sealed interface

## 1. Câu hỏi thiết kế: miền kiểu mở hay đóng?

Khi mô hình hóa một domain trong Java, cả `interface` thông thường và `sealed interface` đều có thể diễn tả **một hợp đồng chung cho nhiều kiểu đối tượng**. Khác biệt cốt lõi nằm ở quyền mở rộng hệ phân cấp:

- **`interface` thông thường (open interface):** các lớp hoặc interface khác có thể triển khai/mở rộng hợp đồng theo các quy tắc truy cập và module thông thường. Người viết interface không liệt kê trước toàn bộ implementation.
- **`sealed interface` (closed hoặc controlled hierarchy):** người viết hợp đồng chỉ định **những subtype trực tiếp được phép**. Một subtype được phép có thể đóng hẳn nhánh đó, tiếp tục giới hạn nhánh đó, hoặc cố ý mở nhánh đó.

Ví dụ trong hệ thống thanh toán:

- **Kết quả thanh toán** của lõi hệ thống chỉ gồm ba trạng thái `Approved`, `Declined`, `Pending`. Nếu đây là tập biến thể do domain sở hữu và cần xử lý đầy đủ, `sealed interface` là ứng viên tốt.
- **Nhà cung cấp thanh toán** có thể đến từ tích hợp nội bộ, đối tác hoặc plugin chưa tồn tại lúc viết code. Nếu muốn bên ngoài có thể thêm implementation, `interface` thông thường có thể phù hợp hơn.

Không có nguyên tắc “`sealed` luôn tốt hơn” hay “cứ dùng pattern matching là phải `sealed`”. Hãy chọn dựa trên **khả năng mở rộng thực tế của domain**, trách nhiệm sở hữu các subtype và cách ứng dụng tiêu thụ những subtype đó.

## 2. Interface thông thường: mở cho implementation mới

Một hợp đồng mở:

```java
interface PaymentProvider {
    String name();
}

record DomesticProvider(String name) implements PaymentProvider {}
record PartnerProvider(String name) implements PaymentProvider {}
```

Một module/tầng tích hợp khác có thể thêm implementation mới, miễn đáp ứng các yêu cầu Java về truy cập, module và các phương thức giao diện:

```java
final class PluginProvider implements PaymentProvider {
    @Override
    public String name() {
        return "Plugin-X";
    }
}
```

Các đoạn mã này là ví dụ khai báo có thể ghép trong cùng chương trình. Khi hợp đồng mở, code xử lý cần chấp nhận thực tế rằng **có thể xuất hiện implementation chưa được liệt kê**.

Ví dụ với pattern matching for `switch` của Java 21:

```java
static String providerLabel(PaymentProvider provider) {
    return switch (provider) {
        case DomesticProvider p -> "Nội địa: " + p.name();
        case PartnerProvider p -> "Đối tác: " + p.name();
        case null -> "Chưa có nhà cung cấp";
        default -> "Khác: " + provider.name();
    };
}
```

Vì `PaymentProvider` là interface mở, chỉ xử lý `DomesticProvider` và `PartnerProvider` **không chứng minh rằng mọi subtype trong tương lai đã được xử lý**. Nhánh `default` ở đây quy định hành vi dự phòng cho các implementation khác. Một lựa chọn khác là dùng `case PaymentProvider p` sau các nhánh cụ thể để tạo nhánh bao quát không-null.

**Khi ưu tiên interface mở:**

- Tính năng là một **extension point**, SPI (Service Provider Interface) hoặc plugin API.
- Dự kiến có nhiều implementation do đội khác hoặc bên thứ ba tạo.
- Danh sách implementation thay đổi thường xuyên, không do một module duy nhất kiểm soát.
- API chủ yếu gọi hành vi chung như `provider.authorize(...)` hoặc `provider.name()`, không cần phân biệt mọi subtype.
- Các phép thử hoặc mô phỏng cần thêm implementation độc lập với các subtype có sẵn.

Đổi lại, compiler không thể dùng **danh sách implementation mở** để chứng minh rằng một `switch` liệt kê vài subtype cụ thể đã bao phủ toàn bộ domain.

## 3. Sealed interface: kiểm soát các subtype trực tiếp

Mô hình kết quả thanh toán:

```java
sealed interface PaymentOutcome permits Approved, Declined, Pending {}

record Approved(long transactionId) implements PaymentOutcome {}
record Declined(int reasonCode) implements PaymentOutcome {}
record Pending(int secondsToRetry) implements PaymentOutcome {}
```

Ở đây, `PaymentOutcome` là kiểu gốc. Ba record là **các implementation trực tiếp được cho phép** và record mặc nhiên là `final`, nên không thể bị kế thừa tiếp.

Nếu một lớp khác viết:

```java
// KHÔNG BIÊN DỊCH: Unknown không nằm trong danh sách permits.
// record Unknown(int code) implements PaymentOutcome {}
```

compiler sẽ từ chối việc triển khai trực tiếp `PaymentOutcome`, vì kiểu đó không thuộc tập được `permits`. Đây là **ràng buộc của hệ kiểu ngay tại biên dịch**, không phải chỉ là quy ước tài liệu.

Trong một **named module**, các subtype trực tiếp được phép phải thuộc cùng module với sealed type. Nếu dùng **unnamed module**, các subtype trực tiếp được phép phải cùng package. Các ví dụ trong bài đặt các kiểu vào cùng một lớp nguồn, nên không vướng quy tắc tổ chức package/module này.

Từ `sealed interface` không có nghĩa **mọi nhánh con vĩnh viễn không thể mở rộng**. Mỗi subtype trực tiếp được phép phải thể hiện cách tiếp tục hệ phân cấp:

- Một **class** có thể là `final` để đóng nhánh, `sealed` để tiếp tục liệt kê subtype, hoặc `non-sealed` để mở lại nhánh. Một `record` đã mặc nhiên là `final`.
- Một **interface** con có thể là `sealed` để tiếp tục giới hạn hoặc `non-sealed` để cho phép implementation mới.
- Không được áp dụng `non-sealed` bừa bãi lên một interface không có supertype `sealed` tương ứng; `non-sealed` là lựa chọn mở lại một nhánh đang bị kiểm soát.

`permits` liệt kê **subtype trực tiếp**, không phải mọi descendant ở bất kỳ tầng sâu nào. Nếu các subtype trực tiếp nằm trong cùng compilation unit, compiler có thể suy ra danh sách trong một số trường hợp; ghi rõ `permits` vẫn thường giúp người đọc thấy biên giới của domain.

## 4. Giá trị lớn: switch exhaustiveness và pattern matching

Đối với kiểu gốc `PaymentOutcome` ở trên, `switch expression` có thể xử lý tất cả các biến thể được phép:

```java
static String outcomeLabel(PaymentOutcome outcome) {
    return switch (outcome) {
        case Approved(long id) -> "Thành công #" + id;
        case Declined(int code) -> "Từ chối mã " + code;
        case Pending(int seconds) -> "Chờ " + seconds + " giây";
        case null -> "Chưa có kết quả";
    };
}
```

Đây là ví dụ **Java 21** có thể đặt cùng các khai báo record ở phần trước. Các `case` dùng **record patterns**: vừa kiểm tra subtype, vừa phân rã component thành biến có kiểu rõ ràng.

Vì `PaymentOutcome` chỉ cho phép trực tiếp `Approved`, `Declined`, `Pending` và cả ba là record `final`, compiler có đủ thông tin để xác định các dạng **không-null** đều có nhánh. `case null` xử lý riêng selector bằng `null`. Không cần viết một `default` chỉ để “cho đủ nhánh”.

Lợi ích thiết kế:

1. **Tập biến thể được diễn đạt trong type system**, không chỉ trong tài liệu.
2. **Compiler kiểm tra tính bao phủ (exhaustiveness)** của `switch expression`.
3. Khi domain được mở rộng bằng một subtype mới, nhiều `switch` đang dựa vào tính đầy đủ có thể cần cập nhật; đó là tín hiệu hữu ích để xem lại quy tắc nghiệp vụ.
4. Record patterns có thể trích xuất dữ liệu ngay tại `case`, tránh nhiều lần cast và accessor.

Một điểm tinh tế: `sealed` giúp compiler hiểu **các subtype được phép**, nhưng không có nghĩa compiler hiểu tất cả các ràng buộc **giá trị**. Nếu viết:

```java
case Pending(int seconds) when seconds > 0 -> "Đang chờ";
```

thì nhánh này chỉ xử lý các `Pending` thỏa `seconds > 0`. Vẫn phải có nhánh cho `Pending` có `seconds <= 0` (hoặc nhánh tương đương), nếu không tập trường hợp có thể chưa được bao phủ. Vì vậy, không dùng guard `when` như một cách thay thế cho kiểm tra tính đầy đủ.

Tương tự, một `sealed interface` không tự cấm `null`, số âm hoặc dữ liệu không hợp lệ trong component. Nếu domain yêu cầu `secondsToRetry >= 0`, hãy thêm kiểm tra constructor hoặc tại ranh giới dữ liệu. **Sealed kiểm soát hình dạng của hierarchy, không tự đảm bảo mọi invariant của đối tượng.**

## 5. Sealed không nhất thiết đóng mọi nhánh: dùng non-sealed có chủ đích

Một hệ thống có thể muốn giữ loại event lõi hữu hạn, nhưng mở riêng nhóm event đến từ đối tác:

```java
sealed interface PaymentEvent permits CoreEvent, PartnerEvent {}

record CoreEvent(int code) implements PaymentEvent {}

non-sealed interface PartnerEvent extends PaymentEvent {
    String code();
}

record WebhookEvent(String code) implements PartnerEvent {}
```

`CoreEvent` là record `final`; không thể thêm subtype của `CoreEvent`. `PartnerEvent` là **nhánh được cho phép trực tiếp** và có `non-sealed`, nên những kiểu khác được phép triển khai `PartnerEvent` theo quy tắc Java thông thường.

Khi xử lý `PaymentEvent`:

```java
static String eventLabel(PaymentEvent event) {
    return switch (event) {
        case CoreEvent(int code) -> "Core: " + code;
        case PartnerEvent partner -> "Partner: " + partner.code();
        case null -> "Không có event";
    };
}
```

Compiler vẫn có thể kiểm tra tính đầy đủ, bởi nhánh `case PartnerEvent partner` bao quát **mọi implementation thuộc nhánh mở đó**. Nếu chỉ viết `case WebhookEvent webhook` thì không đủ để đại diện cho toàn bộ các implementation tương lai của `PartnerEvent`.

Mô hình này hữu ích khi domain có ranh giới rõ: **các nhóm lớn được kiểm soát**, nhưng một số nhóm cho phép mở rộng. Tuy nhiên, đừng làm hierarchy phức tạp chỉ để sử dụng đủ cả ba từ khóa `sealed`, `non-sealed`, `final`; chỉ dùng khi thực sự có yêu cầu mở/đóng khác nhau ở từng nhánh.

## 6. Ví dụ Java 21 chạy hoàn chỉnh

Tạo tệp **`ChooseInterfaceOrSealedDemo.java`**:

```java
public class ChooseInterfaceOrSealedDemo {
    // Hệ kết quả đóng: chỉ ba subtype trực tiếp.
    sealed interface PaymentOutcome permits Approved, Declined, Pending {}

    record Approved(long transactionId) implements PaymentOutcome {}
    record Declined(int reasonCode) implements PaymentOutcome {}
    record Pending(int secondsToRetry) implements PaymentOutcome {}

    // Điểm mở rộng: bên ngoài có thể có provider mới.
    interface PaymentProvider {
        String name();
    }

    record DomesticProvider(String name) implements PaymentProvider {}
    record PartnerProvider(String name) implements PaymentProvider {}

    // Hệ phân cấp lai: sealed gốc, non-sealed ở một nhánh.
    sealed interface PaymentEvent permits CoreEvent, PartnerEvent {}
    record CoreEvent(int code) implements PaymentEvent {}

    non-sealed interface PartnerEvent extends PaymentEvent {
        String code();
    }

    record WebhookEvent(String code) implements PartnerEvent {}

    static String outcomeLabel(PaymentOutcome outcome) {
        return switch (outcome) {
            case Approved(long id) -> "Thành công #" + id;
            case Declined(int code) -> "Từ chối mã " + code;
            case Pending(int seconds) -> "Chờ " + seconds + " giây";
            case null -> "Chưa có kết quả";
        };
    }

    static String providerLabel(PaymentProvider provider) {
        return switch (provider) {
            case DomesticProvider p -> "Nội địa: " + p.name();
            case PartnerProvider p -> "Đối tác: " + p.name();
            case null -> "Chưa có nhà cung cấp";
            default -> "Khác: " + provider.name();
        };
    }

    static String eventLabel(PaymentEvent event) {
        return switch (event) {
            case CoreEvent(int code) -> "Core: " + code;
            case PartnerEvent partner -> "Partner: " + partner.code();
            case null -> "Không có event";
        };
    }

    public static void main(String[] args) {
        System.out.println(outcomeLabel(new Approved(1024L)));
        System.out.println(outcomeLabel(new Declined(403)));
        System.out.println(outcomeLabel(new Pending(15)));
        System.out.println(outcomeLabel(null));

        System.out.println(
                providerLabel(new DomesticProvider("Nội bộ")));
        System.out.println(
                providerLabel(new PartnerProvider("Đối tác A")));

        PaymentProvider plugin = new PaymentProvider() {
            @Override
            public String name() {
                return "Plugin-X";
            }
        };
        System.out.println(providerLabel(plugin));
        System.out.println(providerLabel(null));

        System.out.println(eventLabel(new CoreEvent(7)));
        System.out.println(eventLabel(new WebhookEvent("W-1")));
        System.out.println(eventLabel(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac ChooseInterfaceOrSealedDemo.java
java ChooseInterfaceOrSealedDemo
```

Kết quả chuẩn:

```text
Thành công #1024
Từ chối mã 403
Chờ 15 giây
Chưa có kết quả
Nội địa: Nội bộ
Đối tác: Đối tác A
Khác: Plugin-X
Chưa có nhà cung cấp
Core: 7
Partner: W-1
Không có event
```

Giải thích:

- Bốn dòng đầu đến từ **closed hierarchy** `PaymentOutcome`. Ba record được `permits` xác định đầy đủ, nên `switch expression` không cần `default`; trường hợp `null` có nhánh riêng.
- Hai dòng tiếp theo nhận dạng các implementation đã biết của `PaymentProvider`.
- `plugin` là implementation **vô danh** của interface mở; nó không thuộc hai record `DomesticProvider` hoặc `PartnerProvider`. Do đó, `default` trả về `Khác: Plugin-X`. Cách thêm implementation này không thể dùng để triển khai trực tiếp `PaymentOutcome` nếu kiểu mới không được liệt kê trong `permits`.
- `providerLabel(null)` chọn `case null`, không chọn `default`.
- Ba dòng cuối dùng hệ phân cấp **lai** `PaymentEvent`. `CoreEvent` được phân rã bằng record pattern; `WebhookEvent` là một implementation của nhánh `PartnerEvent` mở rộng và được xử lý bởi type pattern `PartnerEvent partner`.

Trong chương trình này, các record được khai báo lồng trong lớp chính; Java cho phép tổ chức như vậy. Khi tách ra nhiều tệp và module thật, phải áp dụng quy tắc package, module và visibility của `sealed`.

## 7. Cân nhắc quan trọng trước khi chọn

### 7.1. Mức độ ổn định của domain

Nếu tập biến thể **thực sự hữu hạn và thuộc quyền quản lý của module lõi**, sealed mô tả được invariant của kiến trúc: chỉ các subtype được phép mới tham gia mô hình. Ví dụ điển hình là các biến thể của một *result*, *AST node*, *command nội bộ* hoặc một trạng thái có tập lựa chọn rõ ràng.

Nếu domain cần **khả năng đăng ký loại mới** mà thư viện lõi không thể dự đoán, interface thường phù hợp. Ví dụ như plugin, driver, provider hoặc adapter tích hợp.

Không nên chọn sealed chỉ vì **hiện tại mới có hai implementation**. “Mới có hai” khác với “theo hợp đồng sẽ chỉ có hai hoặc tập được kiểm soát”.

### 7.2. Ai sở hữu subtype?

Với `sealed`, nhà phát triển kiểu gốc kiểm soát tập subtype trực tiếp. Điều này phù hợp với domain nội bộ do một module chịu trách nhiệm.

Với interface mở, các module/nhóm khác có thể thêm implementation. Nếu thư viện công bố interface để khách hàng mở rộng, chuyển từ interface mở sang sealed về sau có thể **làm hỏng mã nguồn của implementation hiện hữu** vì chúng không còn được phép triển khai trực tiếp.

### 7.3. Tác động khi thêm loại mới

| Tình huống | Interface thông thường | Sealed interface |
| --- | --- | --- |
| Thêm implementation mới | Có thể triển khai nếu đáp ứng visibility và hợp đồng. | Không thể trực tiếp nếu không được phép; thường cần sửa `permits` và quy tắc tổ chức module. |
| `switch` liệt kê vài subtype | Cần nhánh bao quát hoặc `default` nếu compiler chưa thấy đầy đủ. | Có thể được kiểm tra tính đầy đủ dựa trên permitted subtypes. |
| Thêm subtype vào domain | Code xử lý không được compiler bắt buộc cập nhật từng nơi nếu đã có fallback. | `switch` được biên dịch lại có thể bị báo thiếu nhánh khi tập subtype thay đổi. |
| Tích hợp plugin chưa biết trước | Linh hoạt hơn. | Cần một nhánh `non-sealed` được thiết kế trước hoặc cách mở rộng khác. |
| Ranh giới domain | Dựa nhiều vào quy ước và API. | Được thể hiện trực tiếp trong quy tắc kế thừa/triển khai của Java. |

Thêm một subtype được phép là thay đổi mô hình domain có ảnh hưởng tới code xử lý và khả năng tương thích. Khi triển khai các module đã biên dịch riêng, không nên giả định nâng cấp hierarchy mà không đồng bộ code phụ thuộc sẽ luôn an toàn; compile-time exhaustiveness là lợi thế khi biên dịch lại và kiểm tra lại toàn bộ nơi tiêu thụ.

### 7.4. Polymorphism hành vi hay phân loại dữ liệu?

Nếu các subtype chủ yếu thực hiện **hành vi chung** qua phương thức interface, ví dụ `provider.authorize(request)`, thì code có thể không cần `switch` phân biệt kiểu. Dùng interface mở là hợp lý nếu hợp đồng được thiết kế làm extension point.

Nếu nhiều phần của ứng dụng cần **phân loại cấu trúc dữ liệu** để xử lý theo từng biến thể, sealed + record + pattern matching giúp compiler biết các loại hợp lệ và kiểm tra đủ nhánh. Nhưng nếu sự phân loại đó bị lặp lại ở quá nhiều nơi, vẫn nên cân nhắc đưa hành vi vào phương thức của domain thay vì biến mọi thao tác thành một `switch` lớn.

## 8. Những hiểu nhầm thường gặp

1. **“Sealed nghĩa là mọi lớp con đều final.”** Sai. Sealed kiểm soát subtype **trực tiếp**. Một subtype được phép có thể là `sealed` hoặc `non-sealed` để tiếp tục hoặc mở lại hệ phân cấp; record thì mặc nhiên final.
2. **“Record bắt buộc đi cùng sealed.”** Sai. Record có thể triển khai interface thông thường, sealed interface hoặc một interface con hợp lệ. Record và sealed giải quyết hai nhu cầu khác nhau: biểu diễn dữ liệu và giới hạn hierarchy.
3. **“Dùng sealed sẽ loại bỏ mọi default ở mọi switch.”** Không hẳn. Còn tùy selector, pattern, các `when`, kiểu nhánh `non-sealed` và quy tắc exhaustiveness. Compiler kiểm tra các trường hợp được biểu diễn trong mã, không phải các điều kiện nghiệp vụ tùy ý.
4. **“Sealed tự kiểm tra giá trị bên trong record.”** Sai. `record Pending(int secondsToRetry)` vẫn cho phép số âm nếu không có validation. Sealed chỉ giới hạn **loại subtype**, không đảm bảo dữ liệu hợp lệ.
5. **“Interface mở không dùng được pattern matching.”** Sai. Type pattern và record pattern vẫn hoạt động; điểm khác là compiler không thể suy ra tất cả implementation tương lai chỉ từ một interface mở.
6. **“`default` luôn xử lý cả null.”** Không nên dựa vào điều đó. Với pattern matching for `switch`, `null` có quy tắc riêng; ví dụ trong bài dùng `case null` khi selector có thể null.
7. **“Có thể thêm implementation trực tiếp ở bất kỳ module nào khi interface sealed có permits.”** Không đúng. Permitted subtype trực tiếp bị ràng buộc bởi cùng named module, hoặc cùng package nếu ở unnamed module.
8. **“Sealed giúp code luôn tương thích khi thêm trạng thái mới.”** Không đúng. Việc thêm biến thể có thể buộc cập nhật `switch`, test, serialization, API và module phụ thuộc. Đó là tác động kiến trúc cần quản lý, không phải lỗi của sealed.

## 9. Checklist chọn thiết kế

Trước khi chọn, hãy trả lời:

1. Tập biến thể là **định nghĩa domain hữu hạn** hay chỉ là những implementation hiện có?
2. Ai được quyền thêm implementation: module lõi, các module nội bộ khác, hay cả bên thứ ba?
3. Nếu xuất hiện subtype mới, hệ thống nên **buộc cập nhật xử lý** hay nên chạy theo hợp đồng chung?
4. Có cần compiler bảo đảm `switch expression` không bỏ sót loại đã được phép không?
5. Có yêu cầu tích hợp plugin hay versioning độc lập giữa các module không?
6. Có thực sự cần **nhánh mở có kiểm soát** để cân bằng giữa closed domain và extension point không?
7. Invariant dữ liệu nào cần được kiểm tra ở constructor/API thay vì dựa vào sealed?

**Quy tắc quyết định thực tế:**

- Chọn **`sealed interface`** khi tập subtype thuộc quyền kiểm soát rõ ràng, có ý nghĩa domain và cần tính đầy đủ khi phân loại.
- Chọn **`interface` thông thường** khi muốn công bố hợp đồng để những implementation chưa biết trước có thể tham gia.
- Chọn **`sealed` kết hợp một nhánh `non-sealed`** khi chỉ một phần của hierarchy được phép mở rộng, và nhánh ấy có hợp đồng đủ rõ để xử lý tổng quát.

## 10. Phiên bản Java và tự kiểm tra

- **Sealed classes/interfaces** và **records** là tính năng chính thức từ **Java 17** (records đã chính thức từ Java 16). Các mô hình kiểu trong bài có thể được sử dụng với JDK 17.
- **Pattern matching for `switch` và record patterns** chính thức từ **Java 21**. Chương trình chạy hoàn chỉnh ở trên cần JDK 21 và không cần `--enable-preview`.
- Nếu dự án chỉ có Java 17, có thể dùng `sealed interface` nhưng xử lý phân loại bằng `instanceof`/type patterns hoặc các phương thức polymorphic thay cho record patterns trong `switch` Java 21.

**Tình huống 1:** Ứng dụng bán hàng có ba trạng thái duy nhất theo hợp đồng lõi: `Created`, `Paid`, `Cancelled`. Mỗi khi thêm trạng thái, code định tuyến phải được kiểm tra lại. **Gợi ý:** `sealed interface` với các record `final` đại diện trạng thái.

**Tình huống 2:** Thư viện cho phép khách hàng viết thêm exporter mới mà không phải sửa thư viện. **Gợi ý:** `interface Exporter` mở, có phương thức chung như `export(data)`, và tránh `switch` cố liệt kê tất cả exporter.

**Tình huống 3:** Event nội bộ chỉ có hai nhóm: `SystemEvent` và `PluginEvent`; nhà phát triển chỉ muốn cho phép plugin mở rộng nhóm thứ hai. **Gợi ý:** sealed gốc với một nhánh `non-sealed PluginEvent` được cho phép; các `switch` trên kiểu gốc xử lý toàn bộ nhóm plugin bằng `case PluginEvent e`.

**Ghi nhớ:** Khác biệt chính giữa `interface` và `sealed interface` là **ai có thể mở rộng hierarchy và compiler biết được tập subtype đến đâu**. Thiết kế tốt phải khớp với ranh giới domain, nhu cầu plugin và vòng đời thay đổi API; `sealed` cùng pattern matching tạo sức mạnh kiểm tra đầy đủ, nhưng chỉ đáng dùng khi mô hình thực sự cần một tập biến thể được kiểm soát.
