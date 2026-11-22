# Checklist trước khi công bố một lớp có hợp đồng giá trị trong Java

## Mục tiêu: điều gì phải chắc chắn trước khi phát hành?

**Hợp đồng giá trị** (*value contract*) nói rõ khi nào hai instance biểu diễn **cùng một giá trị**, đầu vào nào hợp lệ, trạng thái có thể thay đổi ra sao và những hành vi nào caller được quyền dựa vào. Trước khi công bố một lớp kiểu giá trị cho module khác, thư viện hoặc API công khai, hãy trả lời những câu hỏi dưới đây bằng **quyết định cụ thể và phép kiểm chứng**. Đừng chỉ kiểm tra rằng lớp đã override `equals()` và `hashCode()`.

Ví dụ điển hình là `Money`, `Point`, `EmailAddress`, `DateRange` hoặc một mã định danh nghiệp vụ. Hai instance của value object có thể là hai đối tượng khác nhau trong bộ nhớ (`a != b` theo `==`) nhưng vẫn `a.equals(b) == true`. Điều này khác với *entity*, nơi tính đồng nhất có thể phụ thuộc vào một ID riêng và vòng đời tồn tại lâu dài.

**Câu hỏi mở đầu phải chốt:** Lớp này thực sự đại diện cho *một giá trị* hay *một thực thể có danh tính riêng*? Nếu không thể nói rõ quy tắc hai instance được coi là cùng giá trị, chưa nên công bố hợp đồng equality.

## 1. Danh sách câu hỏi theo giai đoạn

### A. Xác định ý nghĩa và phạm vi của giá trị

- [ ] **Đối tượng đại diện cho khái niệm nào?** Viết được một câu rõ ràng, ví dụ: “Một số tiền không âm với mã tiền tệ, có độ chính xác hai chữ số thập phân”.
- [ ] **Những thuộc tính nào tạo nên giá trị?** Liệt kê trường quyết định equality; trường nào chỉ là dữ liệu hiển thị, mô tả, cache, metadata hoặc dữ liệu suy ra?
- [ ] **Hai instance có cùng dữ liệu nhưng được tạo tại hai thời điểm khác nhau có bằng nhau không?** Nếu có, `==` không phải tiêu chí; hãy xác định value equality.
- [ ] **Có trường nào mang danh tính ổn định của entity không?** Nếu có, xem lại việc coi lớp là value object; đừng vô tình gộp hai entity khác nhau vì chúng tình cờ có cùng thuộc tính.
- [ ] **Các giới hạn miền dữ liệu đã được mô tả chưa?** Chẳng hạn đơn giá âm có hợp lệ, khoảng ngày đảo ngược có hợp lệ, mã tiền tệ cho phép tập ký tự nào?
- [ ] **Có những biểu diễn đầu vào khác nhau nhưng tương đương không?** Ví dụ mã `" usd "` và `"USD"`, hay `BigDecimal("10.0")` và `BigDecimal("10.00")`.
- [ ] **Lớp cần triển khai `Comparable` không?** Nếu có, có ý nghĩa thứ tự tổng quát không, và `compareTo(x) == 0` có nhất quán với `equals(x)` không?

**Quyết định cần lưu:** bảng liệt kê mọi thành phần, quy tắc hợp lệ, cách chuẩn hóa và việc có tham gia `equals()`/`hashCode()` hay không. Một quy tắc chưa thống nhất phải được giải quyết trước khi thiết kế API công khai.

### B. Chính sách `null` và bất biến (*invariant*)

- [ ] **Trường nào cấm `null`?** Trường bắt buộc cần được kiểm tra ngay tại constructor/factory, ví dụ `Objects.requireNonNull(name, "name")`.
- [ ] **Trường tùy chọn phân biệt `null`, chuỗi rỗng và giá trị vắng mặt không?** Chỉ gộp các trạng thái này khi nghiệp vụ thật sự cho phép.
- [ ] **Có điều kiện hợp lệ kết hợp giữa nhiều trường không?** Ví dụ `start <= end`, hoặc hai tọa độ phải sử dụng cùng hệ quy chiếu.
- [ ] **Khi đầu vào không hợp lệ, phương thức làm gì?** Công bố loại ngoại lệ, thông điệp hỗ trợ chẩn đoán và liệu có tự chuẩn hóa hay từ chối.
- [ ] **Mọi đường tạo đối tượng đều kiểm tra invariant chưa?** Xem constructor, static factory, builder, parser, JSON mapper, ORM, deserialization và các phương thức tạo bản sao.
- [ ] **Getter có thể trả `null` bất ngờ không?** Phần tài liệu và type contract cần khớp với hành vi thực tế.

Không dùng các sentinel như `0`, `"N/A"`, ngày giả hoặc chuỗi trống để biểu diễn thiếu dữ liệu nếu chúng có thể là giá trị hợp lệ. Quy tắc `null` phải nhất quán giữa đầu vào, trạng thái lưu trữ, equality, `toString()` và API trả về.

### C. Chuẩn hóa và biểu diễn chuẩn

- [ ] **Đã xác định phép chuẩn hóa cụ thể, thứ tự áp dụng và locale chưa?** Ví dụ trim đầu/cuối, chuẩn hóa Unicode, đổi chữ hoa/thường theo `Locale.ROOT`, quy đổi đơn vị.
- [ ] **Chuẩn hóa có làm mất thông tin không?** Chuyển hoa/thường, bỏ dấu hoặc nén khoảng trắng có thể gây trùng tên/ID vốn khác nghĩa; chỉ làm khi đặc tả cho phép.
- [ ] **Phép chuẩn hóa có ổn định và idempotent không?** Một giá trị hợp lệ sau chuẩn hóa lần hai phải giữ nguyên.
- [ ] **Có kiểm tra ký tự hợp lệ trước/sau chuẩn hóa không?** Tránh “sửa” mã sai định dạng thành mã khác một cách âm thầm.
- [ ] **Các giá trị số cần chính xác đến đâu?** Không dùng `double` cho tiền theo mặc định; với `BigDecimal`, đã quyết định rõ `scale`, làm tròn và quan hệ giữa `equals()` với `compareTo()` chưa?
- [ ] **Thời điểm hoặc đơn vị đo có cách biểu diễn thống nhất không?** Nêu rõ vùng giờ/UTC, đơn vị gốc, độ chính xác và giới hạn chuyển đổi.

**Lưu ý về `BigDecimal`:** `new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0`, nhưng `equals()` là `false` vì `scale` khác. Nếu trường tham gia equality của record hoặc class, hãy chuẩn hóa thang đo hoặc thiết kế một phép so sánh và hash tương thích có chủ ý. Không được chỉ sửa `equals()` mà bỏ qua `hashCode()`.

### D. `equals()`, `hashCode()` và thứ tự so sánh

- [ ] **`equals()` có phản xạ không?** Với mọi giá trị hợp lệ `x`, `x.equals(x)` là `true`.
- [ ] **Có đối xứng không?** `x.equals(y)` và `y.equals(x)` phải giống nhau, kể cả khi tham gia phân lớp hoặc proxy.
- [ ] **Có bắc cầu không?** Nếu `x.equals(y)` và `y.equals(z)`, phải có `x.equals(z)`.
- [ ] **Có nhất quán khi trạng thái liên quan không đổi không?** Kết quả không được phụ thuộc cache không ổn định, thời gian hiện tại hoặc trạng thái ngoài bất ngờ.
- [ ] **`x.equals(null)` luôn `false` không?**
- [ ] **Hai instance bằng nhau có hash bằng nhau không?** `x.equals(y) => x.hashCode() == y.hashCode()`; chiều ngược lại không được bảo đảm vì có collision.
- [ ] **Tất cả và chỉ những trường được chọn cho equality đã được dùng nhất quán chưa?** Tránh trường cache, timestamp ghi log, trạng thái mutable hoặc trường suy ra không thuộc ngữ nghĩa giá trị.
- [ ] **Có subclass nào phá tính đối xứng/bắc cầu không?** Nếu không thiết kế đầy đủ equality cho hệ phân cấp, cân nhắc `final` hoặc `record` (record mặc định là `final`).
- [ ] **Nếu triển khai `Comparable`, comparator hoặc dùng `TreeSet`/`TreeMap`, quan hệ thứ tự có được mô tả không?** `compareTo() == 0` có thể khác `equals()` nhưng sẽ khiến collection sắp xếp vận hành khác collection dùng hash; phải biết trước tác động.

Với `record`, các phương thức `equals()` và `hashCode()` được tạo từ **toàn bộ thành phần**. Hãy cân nhắc thành phần trước khi công bố record: thêm một thành phần thường ảnh hưởng constructor, pattern matching, biểu diễn chuỗi và định nghĩa value equality. Nếu giá trị phải bỏ qua một số metadata, có thể cần thiết kế class hoặc override rõ ràng thay cho equality mặc định.

### E. Bất biến, sao chép phòng thủ và dữ liệu suy ra

- [ ] **Đối tượng có thực sự bất biến sau khi tạo không?** `final` trên field tham chiếu không làm `List`, mảng, `Date` hoặc các object con trở thành bất biến.
- [ ] **Constructor có sao chép dữ liệu mutable do caller truyền vào không?** Dùng bản sao phòng thủ, chẳng hạn `List.copyOf(...)` khi phù hợp (lưu ý `List.copyOf` không chấp nhận phần tử `null` và chỉ sao chép cấu trúc, không sao chép sâu phần tử).
- [ ] **Accessor có lộ tham chiếu mutable nội bộ không?** Trả bản sao hoặc view bất biến phù hợp; giữ chính sách nhất quán.
- [ ] **Giá trị suy ra có nguồn chân lý rõ ràng không?** Ví dụ `total = unitPrice * quantity`; tránh lưu và cho sửa độc lập cả nguồn lẫn kết quả.
- [ ] **Nếu có cache, cache được vô hiệu hóa khi nào và có tham gia equality/hash không?** Giá trị cache thường phải bị loại khỏi equality; nếu lazy cache dùng ở nhiều thread, phải có chính sách đồng thời.
- [ ] **Có thể dùng object an toàn làm khóa `HashMap` hoặc phần tử `HashSet` không?** Các thành phần tham gia hash nên bất biến suốt thời gian đối tượng ở trong collection.

**Kiểm tra aliasing:** tạo value object từ collection/mảng, sửa dữ liệu gốc sau khi xây dựng, rồi kiểm tra `equals()`, `hashCode()` và getter của value object không đổi. Lặp lại phép kiểm sau khi lấy tham chiếu từ getter và thử sửa nó.

### F. API công khai, lỗi và khả năng tương thích

- [ ] **Tên kiểu, constructor, factory và phương thức đã thể hiện đúng bất biến chưa?** Chẳng hạn `Money.of(...)`, `plus(...)`, `amount()`; tránh getter hoặc setter làm caller tưởng có thể sửa trường bất biến.
- [ ] **Tính công khai của constructor và helper có chủ ý không?** Cân nhắc validation không thể bị vượt qua qua constructor phụ hay builder.
- [ ] **`toString()` có phù hợp để log không?** Record có `toString()` mặc định in toàn bộ component, có thể vô tình tiết lộ thông tin nhạy cảm.
- [ ] **Có cần biểu diễn JSON, database, text hoặc binary ổn định không?** Chuẩn hóa, schema, tên trường, định dạng số và khả năng nạp lại cần tương thích với hợp đồng.
- [ ] **Các ngoại lệ khi parse, normalize và thao tác số có được công bố không?** Caller phải biết khi nào cần xử lý lỗi.
- [ ] **Nếu công bố thành API thư viện, chính sách phiên bản đã được xác định chưa?** Đổi quy tắc `equals()`, chuẩn hóa, `hashCode()` hoặc constructor có thể gây khác biệt hành vi dù chữ ký Java không đổi.
- [ ] **Tài liệu có ví dụ phân biệt hai instance khác nhau nhưng bằng giá trị không?** Nhắc caller không dùng `==` để so sánh hai value object độc lập.

Không dựa vào `System.identityHashCode()` để xác định value equality, cũng không dùng `toString()` hoặc giá trị `hashCode()` làm ID duy nhất. `hashCode()` phục vụ tổ chức bucket của collection băm và cho phép collision; giá trị băm có thể thay đổi theo implementation/phiên bản và không phải định danh bền vững.

## 2. Ví dụ kiểm tra trước khi công bố: value object `Money`

Chính sách dưới đây được chọn **cho ví dụ**, không áp đặt cho mọi hệ thống tài chính:

1. Tiền gồm mã đơn vị và số tiền không âm. Đây là **value object**, không phải tài khoản hay giao dịch có ID.
2. Mã đơn vị nhận đúng ba chữ cái **ASCII**, không phân biệt kiểu chữ, cắt khoảng trắng hai đầu; chỉ các ký tự ASCII hợp lệ được nhận. Ví dụ dùng quy tắc cú pháp ba ký tự, chưa xác thực mã ấy có trong danh sách ISO 4217 hay không.
3. `amount` bắt buộc, không âm, có tối đa hai chữ số sau dấu thập phân; chuẩn hóa về `scale = 2` **mà không làm tròn âm thầm**.
4. `record` lưu chỉ hai thành phần chuẩn hóa; `equals()` và `hashCode()` mặc định cùng xét cả hai. Không có setter, cache hay trường suy ra.
5. `plus()` yêu cầu cùng mã đơn vị, trả về một value object mới; không tự quy đổi tỷ giá.

Đặt chương trình Java 17+ vào tệp `ValueContractReview.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class ValueContractReview {
    public record Money(String currency, BigDecimal amount) {
        public Money {
            currency = Objects.requireNonNull(currency, "currency").strip();
            if (!currency.matches("[A-Za-z]{3}")) {
                throw new IllegalArgumentException("currency must be three ASCII letters");
            }
            currency = currency.toUpperCase(Locale.ROOT);

            amount = Objects.requireNonNull(amount, "amount");
            try {
                amount = amount.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException("amount requires rounding", ex);
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must be nonnegative");
            }
        }

        public Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("different currencies");
            }
            return new Money(currency, amount.add(other.amount));
        }
    }

    public static void main(String[] args) {
        Money first = new Money(" usd ", new BigDecimal("10.0"));
        Money second = new Money("USD", new BigDecimal("10.00"));
        Money euro = new Money("EUR", new BigDecimal("10.00"));

        System.out.println("same reference: " + (first == second));
        System.out.println("same value: " + first.equals(second));
        System.out.println("same hash: " + (first.hashCode() == second.hashCode()));
        System.out.println("different currency: " + first.equals(euro));
        System.out.println("canonical code: " + first.currency());
        System.out.println("canonical amount: " + first.amount().toPlainString());
        System.out.println("sum: "
                + first.plus(new Money("usd", new BigDecimal("2.50")))
                       .amount().toPlainString());

        Set<Money> values = new HashSet<>();
        values.add(first);
        values.add(second);
        System.out.println("set size: " + values.size());

        try {
            new Money("usd", new BigDecimal("1.234"));
        } catch (IllegalArgumentException ex) {
            System.out.println("fractional precision rejected");
        }
        try {
            first.plus(euro);
        } catch (IllegalArgumentException ex) {
            System.out.println("cross-currency addition rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ValueContractReview.java
java ValueContractReview
```

Đầu ra xác định:

```text
same reference: false
same value: true
same hash: true
different currency: false
canonical code: USD
canonical amount: 10.00
sum: 12.50
set size: 1
fractional precision rejected
cross-currency addition rejected
```

**Phân tích:** `first` và `second` được tạo bằng `new` hai lần nên khác tham chiếu, nhưng các thành phần record sau chuẩn hóa bằng nhau. `HashSet` giữ một phần tử vì `equals()` và `hashCode()` nhất quán. `amount` là `BigDecimal` bất biến, giúp record ở ví dụ không lộ trạng thái mutable. Mọi thao tác tạo `Money` đi qua constructor có invariant; phép cộng trả về instance mới. Dữ liệu `"1.234"` bị từ chối vì không thể đặt `scale = 2` mà không làm tròn.

**Giới hạn có chủ ý:** Ví dụ chưa kiểm tra mã tiền tệ là mã ISO thật, không quy đổi tỷ giá, không định nghĩa chia hoặc nhân với số thực, và dùng đúng hai chữ số thập phân cho mọi mã. Hệ thống thực phải điều chỉnh các quy tắc đó theo loại tiền tệ và bài toán. Ví dụ cũng không dùng `Money` làm entity hoặc thay thế thiết kế nghiệp vụ giao dịch.

## 3. Ma trận kiểm thử tối thiểu để duyệt hợp đồng

Chuyển các câu hỏi thành kiểm thử độc lập trên các giá trị hợp lệ và không hợp lệ. Bảng dưới đây nêu kết quả mong đợi; không kiểm tra bằng cách so sánh chuỗi `toString()` trừ khi đó chính là hợp đồng đầu ra.

| Nhóm kiểm tra | Dữ liệu/phép thử | Kết quả cần xác nhận |
| --- | --- | --- |
| Phản xạ | `x.equals(x)` | `true`. |
| Đối xứng | `x.equals(y)` và `y.equals(x)` | Cùng kết quả. |
| Bắc cầu | `x ==value y`, `y ==value z` | `x.equals(z) == true`. |
| `null` trong `equals()` | `x.equals(null)` | `false`. |
| Khác kiểu | `x.equals("other")` | `false`, không ném ngoại lệ. |
| Tương đương qua chuẩn hóa | `" usd ", 10.0` và `"USD", 10.00` | `equals == true`, hash bằng nhau. |
| Cùng hash chưa chắc cùng giá trị | Hai object bất kỳ bị collision | `equals()` vẫn quyết định theo giá trị; không coi hash là ID. |
| Khác thành phần equality | `USD 10.00` và `EUR 10.00` | `equals == false`. |
| Collection băm | Thêm hai giá trị tương đương vào `HashSet` | Kích thước 1. |
| `null` bắt buộc | `currency = null`, `amount = null` | Lỗi sớm và nhất quán (`NullPointerException` trong ví dụ). |
| Mã sai | Mã rỗng, `"US1"`, ký tự ngoài ASCII | `IllegalArgumentException`. |
| Số không hợp lệ | `amount < 0` hoặc cần làm tròn | `IllegalArgumentException`. |
| Tính idempotent | Tạo lại từ `x.currency()` và `x.amount()` | Giá trị chuẩn không đổi. |
| Bất biến | Đọc field và thực hiện `plus()` | `x` không đổi; kết quả là instance mới. |
| Sai ngữ nghĩa phép toán | Cộng hai mã đơn vị khác nhau | Bị từ chối, không cộng số học thuần túy. |
| Chuyển đổi/tuần tự hóa | Serialize rồi deserialize (nếu hỗ trợ) | Invariant và equality còn đúng; mã hóa có phiên bản rõ ràng. |

Với lớp có chứa tham chiếu mutable, bổ sung kiểm thử **sao chép phòng thủ** trước và sau khi khởi tạo. Với lớp tự viết `equals()`/`hashCode()`, kiểm thử tình huống subclass và proxy nếu thiết kế cho phép kế thừa. Với `Comparable`, bổ sung tính phản đối xứng dấu, bắc cầu của thứ tự và tính nhất quán với `equals()` theo hợp đồng đã chọn.

## 4. Các câu hỏi bắt buộc trong code review

Trước khi merge hoặc phát hành API, reviewer nên yêu cầu tác giả chỉ ra ngay trong mã hoặc tài liệu:

1. **“Khi nào hai instance bằng nhau?”** Cho ba ví dụ: bằng nhau sau chuẩn hóa, khác nhau do một trường giá trị, và khác nhau về tham chiếu nhưng bằng nhau về giá trị.
2. **“Mọi đường tạo có duy trì invariant không?”** Chỉ vào constructor/factory và kiểm thử đầu vào biên; xem parser, builder, deserializer.
3. **“Có trạng thái nào có thể làm hash thay đổi khi object đang là key không?”** Nếu có, yêu cầu bất biến hoặc xem lại thiết kế equality.
4. **“Những gì được giữ nguyên và những gì bị chuẩn hóa?”** Kiểm tra khả năng mất thông tin, Unicode, locale, `BigDecimal.scale`, vùng giờ, `null`/rỗng.
5. **“Có vô tình đưa metadata hoặc cache vào equality không?”** Nếu là record, kiểm tra kỹ mọi component.
6. **“Khi giá trị không hợp lệ, API báo gì?”** Ngoại lệ phải rõ và caller có thể dự đoán.
7. **“Có getter nào lộ cấu trúc mutable không?”** Thử sửa collection/mảng ban đầu và đối tượng trả về.
8. **“Thay đổi sau phát hành ảnh hưởng những consumer nào?”** Bao gồm `HashSet`/`HashMap`, cache key, database unique key, JSON schema và phương thức so sánh.

### Ví dụ nhận diện vấn đề trước–sau

**Thiết kế có vấn đề (mã minh họa, không phải chương trình độc lập):**

```java
// amount và currency là trường có thể thay đổi và đã tham gia equals/hashCode.
// Nếu instance đang nằm trong HashSet, setter có thể làm việc tra cứu thất bại.
money.setCurrency("EUR");

// Nếu đồng thời lưu total như một trường cho phép sửa riêng,
// total có thể không còn khớp amount * quantity.
```

**Thiết kế chặt chẽ hơn:** factory/constructor validate mọi dữ liệu đầu vào, chuẩn hóa một lần, lưu trạng thái bất biến và trả instance mới khi thay đổi giá trị. Các giá trị suy ra được tính từ thành phần gốc hoặc cache được quản lý rõ ràng. Lời hứa của API phải khớp với những invariant mã thực sự duy trì.

## 5. Điều kiện chấp nhận phát hành

Đánh dấu **sẵn sàng công bố** khi đồng thời đáp ứng bốn nhóm kết quả sau:

- **Có bản hợp đồng đọc được:** mô tả loại giá trị, trường tham gia equality, quy tắc `null`, chuẩn hóa, độ chính xác, ngoại lệ, bất biến và hành vi liên quan.
- **Có implementation tương ứng:** mọi đường tạo giữ invariant; `equals()`/`hashCode()` đúng hợp đồng; nội bộ không lộ mutable state; các phép toán trả giá trị hợp lệ.
- **Có bằng chứng kiểm chứng:** kiểm thử các quy luật equality/hash, biên dữ liệu, đường tạo/nạp, collection, quan hệ thứ tự nếu có và tính bất biến.
- **Có đánh giá tương thích:** kiểm tra tác động tới API công khai, consumer, serialization, database/caching và quy tắc versioning khi thay đổi.

Nếu bất kỳ câu hỏi cốt lõi nào còn chưa trả lời (đặc biệt là **giá trị nào được xem bằng nhau, đầu vào nào hợp lệ và trạng thái nào có thể đổi**), hãy coi đó là vấn đề thiết kế cần giải quyết trước phát hành, thay vì chữa bằng một `hashCode()` ngẫu nhiên hoặc một lớp kiểm tra ở phía caller.

## 6. Mẫu ghi hợp đồng ngắn kèm lớp

```text
Type: Money (value object, immutable)
Components: currency (ASCII 3 letters, uppercase), amount (>= 0, scale 2)
Null policy: both required; null rejected
Canonicalization: strip currency, validate ASCII, uppercase Locale.ROOT;
                  amount.setScale(2, UNNECESSARY)
Equality/hash: both canonical components, record defaults
Ordering: no Comparable; different currencies have no implicit order
Derived values: none stored; plus() returns new Money
Failure policy: invalid state or mixed currencies -> exception
Compatibility: changes in equality, scale or normalization need review
```

**Ghi nhớ:** Hợp đồng giá trị đáng tin là tập hợp nhất quán giữa **ngữ nghĩa nghiệp vụ, biểu diễn chuẩn, invariant, equality/hash, bất biến, API và kiểm thử**. Checklist chỉ hoàn thành khi mọi câu trả lời đã được chuyển thành hành vi có thể quan sát và kiểm chứng trong mã.

## Tài liệu tham khảo

- [Java SE 17 — `Object.equals()` / `hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Java SE 17 — `Record` và đặc tả record](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10)
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — `Set`, `HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
