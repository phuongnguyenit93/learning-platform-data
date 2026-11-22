# Quy định tường minh cách xử lý `null`, chuẩn hóa và dữ liệu suy ra trong hợp đồng đối tượng Java

## 1. Vì sao đây là một phần của hợp đồng đối tượng?

Hợp đồng đối tượng (*object contract*) xác định trạng thái hợp lệ, ý nghĩa của các thuộc tính và hành vi có thể dự đoán của đối tượng: cách khởi tạo, đọc dữ liệu, so sánh bằng nhau (`equals()`), lấy mã băm (`hashCode()`), biểu diễn (`toString()`), cũng như những gì được phép thay đổi sau khi tạo. Nếu không nói rõ ba quy tắc **xử lý `null`**, **chuẩn hóa đầu vào** và **quản lý dữ liệu suy ra**, cùng một thông tin nghiệp vụ có thể sinh ra nhiều trạng thái mâu thuẫn.

Ví dụ, mã hàng `" ab-17 "` và `"AB-17"` có nên là cùng mã? Ghi chú `null` có khác chuỗi trống `""` không? Tổng tiền có nên được lưu như một trường độc lập bên cạnh đơn giá và số lượng? Không có câu trả lời đúng cho mọi hệ thống; điều quan trọng là **chốt một chính sách cho từng thuộc tính, thực thi tại ranh giới tạo đối tượng và duy trì nhất quán trong toàn bộ vòng đời đối tượng**.

Đối với *value object*, chính sách ấy quyết định cả `equals()` và `hashCode()`. Đối với *entity*, phải xác định thêm danh tính nghiệp vụ nào được dùng để so sánh; không nên mặc nhiên đưa mọi trường vào phép so sánh.

## 2. Ba quyết định cần ghi vào hợp đồng

| Nhóm | Câu hỏi phải trả lời | Ví dụ về quyết định minh bạch |
| --- | --- | --- |
| `null` | Trường bắt buộc hay tùy chọn? `null` có ý nghĩa độc lập với rỗng/không tồn tại không? | `sku` và `unitPrice` không nhận `null`; `note == null` được hiểu là ghi chú rỗng. |
| Chuẩn hóa | Giá trị được chuẩn hóa ở đâu, theo thuật toán nào, có mất thông tin không? | Xóa khoảng trắng bao ngoài SKU, kiểm tra ký tự ASCII, chuyển chữ thường sang hoa bằng `Locale.ROOT`; không tự sửa mã sai. |
| Dữ liệu suy ra | Trường nào là nguồn chân lý, trường nào tính từ nguồn, có được sửa độc lập không? | `total = unitPrice × quantity` được tính khi gọi phương thức; không nhận giá trị `total` từ caller. |

### 2.1. `null`: từ chối, chuẩn hóa hay giữ nguyên?

Các lựa chọn đều hợp lệ **nếu phù hợp ngữ nghĩa miền dữ liệu**:

1. **Bắt buộc có giá trị:** dùng `Objects.requireNonNull(value, "field")`, sau đó kiểm tra điều kiện miền (không rỗng, không âm, đúng định dạng). `requireNonNull` phát sinh `NullPointerException` với tên trường được cung cấp khi đối số là `null`. Nếu API quy định mọi dữ liệu đầu vào sai đều phải thành `IllegalArgumentException`, hãy chuyển đổi ngoại lệ một cách tường minh và nhất quán.
2. **Tùy chọn nhưng vắng mặt và rỗng có cùng nghĩa:** quy về một biểu diễn chuẩn, ví dụ `note = note == null ? "" : note.strip()`. Khi đó caller quan sát `note()` luôn trả về chuỗi, không có `null`.
3. **Tùy chọn và vắng mặt khác chuỗi rỗng:** giữ `null` hoặc mô hình trạng thái vắng mặt riêng; giải thích rõ `null`, `""`, `"   "` khác nhau ra sao. `Objects.equals(a, b)` giúp so sánh giá trị nullable mà không gây NPE.
4. **Tùy chọn trong API trả về:** cân nhắc `Optional<T>` làm kiểu trả về khi làm rõ ý nghĩa vắng mặt; không tự động thay mọi trường nullable bằng `Optional` vì việc đó làm phức tạp mô hình dữ liệu, ánh xạ ORM và tuần tự hóa.

Không dùng `"N/A"`, `0`, `false` hay thời điểm giả làm giá trị mặc định nếu các giá trị ấy có thể là dữ liệu nghiệp vụ thật. Không tự đồng nhất `null`, chuỗi trống và chuỗi toàn khoảng trắng trừ khi hợp đồng nêu rõ chúng là tương đương.

### 2.2. Chuẩn hóa: xác định biểu diễn chuẩn (*canonical form*)

Một hàm chuẩn hóa tốt cần **xác định được**, **ổn định**, **lặp lại không đổi** (`normalize(normalize(x)) == normalize(x)` đối với đầu vào hợp lệ), và phù hợp với khái niệm bằng nhau của miền nghiệp vụ. Các bước có thể bao gồm `strip()`, chuyển kiểu chữ, chuẩn hóa Unicode, quy đổi đơn vị, làm rõ múi giờ hoặc chuẩn hóa dạng thập phân. Nhưng mỗi bước đều có thể đổi nghĩa dữ liệu.

- **Mã định danh có quy tắc ASCII:** có thể cắt khoảng trắng hai đầu, chỉ cho phép `[A-Za-z0-9_-]`, sau đó chuyển thành chữ hoa với `Locale.ROOT`. Chỉ nên làm vậy nếu mã **không phân biệt hoa/thường theo đặc tả**. Kiểm tra ký tự trước khi biến đổi giúp ngăn việc vô tình hợp thức hóa ký tự ngoài tập được phép.
- **Tên người và nội dung hiển thị:** không tự động xóa mọi khoảng trắng bên trong, bỏ dấu hoặc chuyển sang chữ thường chỉ để so sánh. Những phép đổi ấy có thể làm mất thông tin.
- **Unicode:** nếu miền dữ liệu coi ký tự có dấu ở dạng dựng sẵn và dạng tổ hợp là cùng một ký tự, cân nhắc `Normalizer.normalize(text, Normalizer.Form.NFC)`. NFC không tự giải quyết tất cả quy tắc so sánh theo ngôn ngữ, chữ hoa/thường hay các vấn đề đồng dạng Unicode.
- **Số thập phân:** `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là `false` do khác `scale`, dù `compareTo(...) == 0`. Với value object sử dụng `BigDecimal`, cần quyết định có chuẩn hóa `scale`, dùng quy tắc so sánh riêng hay giữ nguyên chính xác biểu diễn ban đầu.
- **Ngày giờ và đơn vị:** làm rõ dùng `Instant` hay giờ địa phương, UTC hay vùng giờ miền nghiệp vụ, mét hay centimet. Chỉ chuẩn hóa nếu có đủ thông tin để không đánh mất nghĩa.

**Không nên coi chuẩn hóa là “sửa dữ liệu bằng mọi giá”.** Với mã hàng không hợp lệ, từ chối thường tốt hơn cắt bỏ ký tự lạ khiến hai mã khác nhau bất ngờ nhập làm một. Nếu phép chuẩn hóa làm hai đầu vào khác nhau trở thành một giá trị, đó là một quyết định nghiệp vụ cần tài liệu và kiểm thử.

### 2.3. Dữ liệu suy ra: một nguồn chân lý

Giả sử `total = unitPrice.multiply(quantity)`. Nếu đối tượng đồng thời giữ `quantity`, `unitPrice` **và** `total` có thể gán tùy ý, hợp đồng phải giải thích sẽ làm gì khi ba giá trị không khớp. Cách an toàn với phép tính rẻ là **chỉ lưu hai đầu vào và tính `total()` theo nhu cầu**. Khi đó không tồn tại trạng thái `total` bị cũ.

Nếu tính toán đắt và cần cache, hãy ghi rõ: cache có ảnh hưởng đến `equals()`/`hashCode()` không (thường là **không**), khi nào cache mất hiệu lực, xử lý luồng đồng thời ra sao, và cache có được tái dựng sau deserialization không. Với đối tượng bất biến, lazy cache có thể dùng trong các trường hợp cụ thể nhưng phải xem xét thread safety và chi phí; không tự tạo cache khi phép tính đơn giản.

## 3. Ví dụ đầy đủ: `OrderLine` bất biến trên Java 17+

Chính sách minh họa:

- `sku`: bắt buộc, chỉ nhận chữ cái ASCII, số, `_`, `-`; bỏ khoảng trắng hai đầu; chữ hoa/thường tương đương.
- `note`: tùy chọn; `null`, chuỗi trống và chuỗi chỉ chứa khoảng trắng được xem là cùng một ghi chú rỗng; giữ nguyên phân biệt hoa/thường của nội dung còn lại.
- `quantity`: số nguyên dương; không có giá trị mặc định ngầm.
- `unitPrice`: không `null`, không âm; tối đa hai chữ số thập phân. Chuẩn hóa về `scale = 2` và **từ chối** nếu cần làm tròn.
- `total`: bằng `unitPrice × quantity`, luôn tính từ trạng thái hiện tại; không nằm trong thành phần lưu trữ.

`record` tự sinh `equals()`, `hashCode()` và `toString()` từ các thành phần của record. Constructor dạng *compact* bên dưới chuyển mọi đầu vào hợp lệ sang biểu diễn chuẩn **trước khi Java tự gán các tham số vào trường cuối cùng**. Vì thế so sánh giá trị hoạt động nhất quán trên các trường được chuẩn hóa.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class ObjectContractDemo {
    record OrderLine(String sku, String note, int quantity, BigDecimal unitPrice) {
        public OrderLine {
            sku = normalizeSku(sku);
            note = note == null ? "" : note.strip();

            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");
            try {
                unitPrice = unitPrice.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                        "unitPrice must have at most two decimal places", ex);
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("unitPrice must not be negative");
            }
        }

        private static String normalizeSku(String input) {
            String value = Objects.requireNonNull(input, "sku").strip();
            if (!value.matches("[A-Za-z0-9][A-Za-z0-9_-]*")) {
                throw new IllegalArgumentException("invalid sku");
            }
            return value.toUpperCase(Locale.ROOT);
        }

        public BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        OrderLine first = new OrderLine(
                " ab-17 ", null, 2, new BigDecimal("10.0"));
        OrderLine second = new OrderLine(
                "AB-17", "   ", 2, new BigDecimal("10.00"));
        OrderLine withNote = new OrderLine(
                "AB-17", "gift", 2, new BigDecimal("10.00"));

        System.out.println("same value: " + first.equals(second));
        System.out.println("same reference: " + (first == second));
        System.out.println("same hash: " + (first.hashCode() == second.hashCode()));
        System.out.println("sku: " + first.sku());
        System.out.println("note: [" + first.note() + "]");
        System.out.println("price: " + first.unitPrice().toPlainString());
        System.out.println("total: " + first.total().toPlainString());
        System.out.println("different note: " + first.equals(withNote));

        Set<OrderLine> lines = new HashSet<>();
        lines.add(first);
        lines.add(second);
        System.out.println("set size: " + lines.size());

        try {
            new OrderLine("  ", null, 1, BigDecimal.ONE);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank sku rejected");
        }
        try {
            new OrderLine("AB-17", "", 1, new BigDecimal("1.234"));
        } catch (IllegalArgumentException ex) {
            System.out.println("too precise price rejected");
        }
    }
}
```

Đặt tên tệp là `ObjectContractDemo.java`. Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 ObjectContractDemo.java
java ObjectContractDemo
```

Kết quả xác định (không phụ thuộc vào số identity hash code ngẫu nhiên của JVM):

```text
same value: true
same reference: false
same hash: true
sku: AB-17
note: []
price: 10.00
total: 20.00
different note: false
set size: 1
blank sku rejected
too precise price rejected
```

**Đọc kết quả:** `first` và `second` là hai instance khác nhau (`== false`) nhưng sau chuẩn hóa chúng có bốn thành phần tương ứng bằng nhau, vì vậy `equals()` trả về `true`, hash bằng nhau và `HashSet` chỉ lưu một phần tử. `note` là một thành phần của **value equality**, nên bản ghi có ghi chú `gift` khác về giá trị; `total()` được tính từ hai thành phần gốc và có `scale = 2`. Nếu nghiệp vụ muốn bỏ qua `note` trong phép so sánh, cần thiết kế hợp đồng `equals()`/`hashCode()` khác một cách nhất quán; không thể vừa dùng equality mặc định của record vừa mong nó bỏ qua một thành phần.

Ví dụ đặt quy tắc **từ chối** nhiều hơn là tự sửa: `sku` sai định dạng, số lượng không dương, giá âm, hoặc giá buộc phải làm tròn đều thất bại lúc khởi tạo. Điều này giúp đối tượng đã tạo luôn tuân thủ bất biến (*invariant*).

## 4. `equals()`, `hashCode()` và dữ liệu chuẩn hóa liên hệ thế nào?

Đối với value object, hãy lựa chọn **các thành phần tham gia equality** theo ý nghĩa thực của giá trị. Nếu `equals()` dựa trên biểu diễn chuẩn của trường, `hashCode()` phải dùng cùng các thành phần với cùng quy tắc. Cụ thể:

- **Phản xạ:** `x.equals(x)` phải `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` phải trả kết quả giống nhau.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
- **Nhất quán:** nếu trạng thái liên quan đến equality không đổi, kết quả phải ổn định.
- **Đối với `null`:** `x.equals(null)` phải `false`.
- **Hợp đồng hash:** nếu `x.equals(y)` thì `x.hashCode() == y.hashCode()`; chiều ngược lại **không** được bảo đảm do collision.

`record` phát sinh các phương thức này từ những thành phần lưu trữ. Trong ví dụ, chuẩn hóa giá về cùng `scale` đặc biệt hữu ích vì `BigDecimal.equals()` phân biệt `10.0` và `10.00`; `record` sẽ kế thừa chính cách so sánh đó cho trường `unitPrice`. Khi thiết kế một class thường và tự override `equals()`/`hashCode()`, áp dụng cùng chính sách cho cả hai, và không đưa giá trị suy ra có thể thay đổi vào hash nếu giá trị ấy không thuộc identity/equality.

**Phân biệt entity và value object:** Nếu hai entity có cùng `sku` nhưng khác các trường nghiệp vụ vẫn được xem là cùng thực thể, cần một khóa định danh ổn định cùng chính sách equality riêng. Record minh họa ở trên là **value object**: mọi thành phần (`sku`, `note`, `quantity`, `unitPrice`) đều có ý nghĩa trong phép so sánh.

## 5. Ổn định dữ liệu và nguy cơ khi để trạng thái thay đổi

Với một đối tượng đã được thêm vào `HashSet` hoặc dùng làm khóa `HashMap`, thay đổi trường dùng trong `equals()`/`hashCode()` có thể khiến tra cứu thất bại hoặc hành vi tập hợp trở nên khó dự đoán. Vì vậy, value object dùng làm khóa nên bất biến; thay đổi dữ liệu nên tạo instance mới. `record` ở ví dụ có thành phần `String`, `int`, `BigDecimal` bất biến và không trả tham chiếu tới cấu trúc có thể sửa đổi.

Với class có `List`, `Date`, mảng hoặc đối tượng mutable, chỉ khai báo `final` trên tham chiếu **chưa đủ** tạo bất biến sâu; cần sao chép phòng thủ và quyết định cách expose giá trị. Tránh trả trực tiếp mảng nội bộ hoặc giữ tham chiếu đến collection bên ngoài có thể bị sửa sau khi khởi tạo.

### 5.1. Phân biệt dữ liệu nguồn và dữ liệu cache

```java
// Minh họa đoạn trích: KHÔNG phải chương trình độc lập.
// Không nên giữ total độc lập nếu quantity/unitPrice còn đổi tự do:
BigDecimal total = unitPrice.multiply(BigDecimal.valueOf(quantity));
// Khi quantity thay đổi, total cũ sẽ sai nếu không được cập nhật.
```

Trong tình huống cần đối tượng mutable, mọi thao tác ghi phải giữ các invariant, cập nhật hoặc vô hiệu hóa cache phụ thuộc, đồng thời bảo vệ truy cập đồng thời nếu được chia sẻ giữa các thread. Cách đơn giản hơn thường là bất biến hóa trạng thái và tính lại trường suy ra trong phương thức truy cập.

### 5.2. `toString()`, log và tuần tự hóa

`toString()` là một phần giao diện quan sát được: cần quy định cách biểu diễn `null`, giá trị chuẩn hóa và trường suy ra, cũng như những gì **không** được in vì nhạy cảm (mật khẩu, token, dữ liệu cá nhân). `record.toString()` mặc định hiển thị thành phần của record, nên không dùng mặc định vô điều kiện với dữ liệu nhạy cảm. Nếu JSON hoặc cơ sở dữ liệu lưu giá trị trước chuẩn hóa, đường nạp lại phải duy trì invariant hoặc báo dữ liệu không hợp lệ; không nên để constructor, mapper, factory và deserializer áp các quy tắc khác nhau.

## 6. Những chính sách phải kiểm thử

| Tình huống đầu vào | Kỳ vọng trong ví dụ | Lý do |
| --- | --- | --- |
| `sku = null` | Từ chối bằng `NullPointerException` | Trường bắt buộc, kiểm tra bằng `requireNonNull`. |
| `sku = "  "` | Từ chối bằng `IllegalArgumentException` | Sau `strip()` không còn mã hợp lệ. |
| `sku = " ab-17 "` và `"AB-17"` | Cùng giá trị chuẩn `AB-17` | Mã không phân biệt hoa/thường theo chính sách đã công bố. |
| `sku` có dấu hoặc ký tự lạ | Từ chối | Bộ ký tự được giới hạn rõ ràng. |
| `note = null`, `""`, `"  "` | Cùng giá trị chuẩn `""` | Chính sách gộp vắng mặt và rỗng. |
| `note = "Gift"` và `"gift"` | Khác nhau | Ghi chú chỉ được `strip()`, không đổi kiểu chữ. |
| `quantity = 0` hoặc số âm | Từ chối | Điều kiện `quantity > 0`. |
| `unitPrice = null` hoặc âm | Từ chối | Trường bắt buộc, giá không âm. |
| `unitPrice = 10.0` và `10.00` | Cùng biểu diễn `10.00` | Chuẩn hóa `BigDecimal` về `scale = 2`. |
| `unitPrice = 1.234` | Từ chối; không làm tròn âm thầm | `RoundingMode.UNNECESSARY` buộc chính xác tuyệt đối. |
| Hai bản ghi chuẩn hóa bằng nhau | `equals()` và hash bằng nhau | Hợp đồng value object. |
| Cùng giá trị nguồn, tính `total()` nhiều lần | Cùng kết quả | Trường suy ra không có cache sai lệch. |

Điều kiện về `null`, `equals()`/`hashCode()`, trường hợp biên sau chuẩn hóa, vòng đời object và dữ liệu nạp lại nên được kiểm tra cả với đơn vị kiểm thử tự động. Nếu quy tắc chuẩn hóa đổi trong phiên bản mới, xem xét tác động tới khóa map, dữ liệu database, tìm kiếm, API client, và các bản ghi đã tồn tại: thay đổi chính sách bình đẳng có thể tạo hoặc giải quyết collision nghiệp vụ.

## 7. Các lỗi thiết kế thường gặp

1. **Bỏ `null` qua nhiều lớp mà không định nghĩa nghĩa:** null gây NPE ở nơi xa nguồn gốc. Hãy xác thực tại ranh giới tạo đối tượng và công khai chính sách.
2. **Chuẩn hóa chỉ ở một đường tạo:** factory chuẩn hóa nhưng ORM/JSON mapper nạp trường nguyên gốc. Kết quả là cùng đối tượng nghiệp vụ có hai biểu diễn, khiến equality và tra cứu không nhất quán.
3. **Ép chuỗi rỗng thành `null` hoặc ngược lại tùy tiện:** làm mất khác biệt nghiệp vụ giữa “chưa nhập” và “cố ý để trống”.
4. **Dùng locale mặc định cho khóa kỹ thuật:** kiểu chữ có thể biến đổi theo máy/chính sách vùng. Với mã ASCII không phân biệt hoa/thường, dùng `Locale.ROOT` và quy định tập ký tự.
5. **Dùng `BigDecimal.compareTo()` ở một nơi, `equals()` ở nơi khác nhưng không nêu quy tắc scale:** đối tượng có thể “bằng nhau” trong tính toán nhưng khác trong `HashSet`.
6. **Lưu và cho sửa riêng giá trị suy ra:** dễ tạo trạng thái mâu thuẫn khi dữ liệu nguồn đổi.
7. **Đưa cache, timestamp quan sát hoặc trường có thể thay đổi vào `hashCode()`:** làm hỏng tính ổn định của key trong collection băm.
8. **Dùng record như entity mà không xem equality mặc định:** record so sánh theo toàn bộ thành phần, không tự suy luận định danh nghiệp vụ.

## 8. Checklist chốt hợp đồng

- Với **mỗi trường**, mô tả bắt buộc/tùy chọn, ý nghĩa `null`/rỗng, giá trị hợp lệ và loại ngoại lệ khi vi phạm.
- Mô tả cụ thể **thuật toán chuẩn hóa**, thứ tự thực hiện, trường hợp bị từ chối và dữ liệu có thể bị gộp.
- Xác định **nguồn chân lý**; phân biệt trạng thái lưu trữ, giá trị suy ra và cache.
- Chốt **equality/identity/hash**, tránh phụ thuộc trường mutable; kiểm tra tương thích với collection và serialization.
- Đảm bảo mọi đường tạo/nạp đối tượng dùng cùng chính sách, đồng thời kiểm thử các trường hợp biên và phiên bản dữ liệu cũ.

**Nguyên tắc cốt lõi:** Một đối tượng hợp lệ phải có cách biểu diễn được định nghĩa rõ; cùng đầu vào theo ngữ nghĩa phải dẫn đến cùng trạng thái chuẩn, dữ liệu suy ra phải khớp với nguồn, và toàn bộ hành vi `equals()`/`hashCode()` phải phản ánh chính sách đó.

## Tài liệu tham khảo

- [Java SE 17 — `Object.equals()` và `Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Java SE 17 — `Objects.requireNonNull()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)
- [Java SE 17 — `BigDecimal` và `RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — `String.strip()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip())
- [Java Language Specification 17 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10)
