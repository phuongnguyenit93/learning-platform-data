# Chọn dữ liệu cốt lõi, dữ liệu suy ra và dữ liệu ghi nhớ tạm khi thiết kế `equals()` và `hashCode()`

## 1. Vì sao phải phân loại dữ liệu trước khi định nghĩa “bằng nhau”?

Hai đối tượng Java có thể lưu rất nhiều trường, nhưng **không phải mọi trường đều quyết định hai đối tượng có được coi là cùng một giá trị hoặc cùng một thực thể hay không**. Khi override `equals(Object)`, việc đầu tiên là trả lời câu hỏi nghiệp vụ:

> Trong ngữ cảnh này, thay đổi thông tin nào sẽ khiến hai đối tượng **không còn được coi là bằng nhau**?

Chỉ sau khi trả lời, ta mới chọn những trường cần so sánh. Không thể suy ra câu trả lời một cách máy móc từ số lượng trường, từ tên biến `id` hay từ việc trường được khai báo `final`.

Một mô hình thường có ba loại dữ liệu:

1. **Dữ liệu cốt lõi cho quan hệ bằng nhau** (*equality-defining state*): thông tin trực tiếp xác định tiêu chí equality đã chọn. Nếu thông tin này khác nhau, hai đối tượng có thể không còn bằng nhau.
2. **Dữ liệu suy ra** (*derived/computed data*): kết quả có thể tính lại từ dữ liệu khác, chẳng hạn tên hiển thị ghép từ họ và tên, nhãn ghép từ mã sản phẩm và mô tả, hoặc tổng tiền tính từ số lượng và đơn giá. Giá trị suy ra có thể có ý nghĩa với ứng dụng, nhưng thường **không cần so sánh lặp lại** nếu những đầu vào đầy đủ của nó đã được so sánh.
3. **Dữ liệu ghi nhớ tạm** (*cached/memoized data*): kết quả tính toán được lưu lại nhằm tránh làm việc lặp lại, như nhãn đã tạo, kết quả phân tích cú pháp, mã băm đã tính hoặc dữ liệu truy xuất đã tải. Cache phải phản ánh trạng thái gốc; bản thân việc cache đã có hay chưa thường **không làm đổi ý nghĩa equality**.

“Cốt lõi” ở đây có nghĩa là **cốt lõi đối với quan hệ bằng nhau đang thiết kế**, không có nghĩa mọi dữ liệu khác đều vô ích. Một trường có thể quan trọng để hiển thị, tính hóa đơn hoặc kiểm toán mà vẫn không được dùng trong `equals`.

## 2. Quyết định ngữ nghĩa: cùng thực thể hay cùng giá trị?

Không có một danh sách trường `equals` dùng chung cho mọi class. Hai lối thiết kế thường gặp là:

| Quan hệ bằng nhau | Câu hỏi | Trường thường xét | Ví dụ |
| --- | --- | --- | --- |
| **Entity identity** – cùng thực thể | Đây có phải cùng một thực thể trong miền nghiệp vụ không? | Định danh ổn định, duy nhất trong phạm vi phù hợp | Hai đối tượng `Customer` cùng `customerId` được xem là một khách hàng, dù tên hiển thị thay đổi. |
| **Value equality** – cùng giá trị | Hai đối tượng có biểu diễn cùng giá trị đã được định nghĩa không? | Các thành phần quyết định toàn bộ giá trị | Hai `Money` bằng nhau khi cùng số tiền và cùng đơn vị tiền tệ theo quy ước của miền nghiệp vụ. |

Ví dụ, hai bản ghi sản phẩm có cùng SKU nhưng mô tả khác nhau **có thể** được coi là cùng thực thể nếu SKU là định danh ổn định. Ngược lại, nếu lớp đang biểu diễn một *bản chụp mô tả sản phẩm* và yêu cầu tất cả thuộc tính cấu thành bản chụp giống nhau, việc bỏ qua mô tả sẽ không phù hợp.

Điều kiện quyết định là **ngữ nghĩa miền nghiệp vụ**, không phải “mọi class có ID thì chỉ so sánh ID”. Với thực thể chưa được gán ID (ví dụ entity do ORM tạo trước khi lưu), ID có thể còn `null` hoặc thay đổi theo vòng đời; dùng nó trong equality đòi hỏi chính sách rõ ràng để tránh hai thực thể mới bị coi bằng nhau chỉ vì đều có `null`.

### Bốn câu hỏi trước khi chọn trường

1. Người dùng hoặc API coi hai đối tượng là **cùng cái gì**: cùng người dùng, cùng số tiền, cùng bản ghi, hay cùng trạng thái hiện tại?
2. Có trường nào là **định danh ổn định** không? Định danh ấy có được bảo đảm duy nhất trong phạm vi đối tượng đang xét không?
3. Trường nào chỉ là **hàm của trường khác**, hoặc chỉ khác vì chưa tính/chưa lưu cache?
4. Trường nào **có thể thay đổi sau khi đối tượng được dùng làm khóa** trong `HashMap` hoặc phần tử trong `HashSet`?

Nếu chưa xác định được ngữ nghĩa, không nên viết `equals` bằng cách tự động so sánh mọi field được IDE liệt kê.

## 3. Bảng phân loại trường trong một mô hình cụ thể

Giả sử hệ thống có lớp `InventoryItem` và quy tắc nghiệp vụ là: **SKU chuẩn hóa xác định duy nhất một mặt hàng**. Những trường sau có vai trò khác nhau:

| Trường | Ví dụ | Vai trò | Có tham gia equality theo SKU? |
| --- | --- | --- | --- |
| `sku` | `"AB-12"` | Định danh cốt lõi đã chuẩn hóa | **Có** |
| `description` | `"Bút màu xanh"` | Thông tin mô tả có thể sửa | **Không**, theo quy tắc cùng SKU là cùng mặt hàng |
| `displayLabel` | `"AB-12 - Bút màu xanh"` | Dữ liệu suy ra từ SKU và mô tả | **Không** |
| `cachedLabel` | Chuỗi `displayLabel` đã tính trước | Cache của dữ liệu suy ra | **Không** |
| `lastViewedAt` | Thời điểm UI đọc thông tin | Metadata hoạt động hoặc quan sát | **Không** |

Bảng chỉ đúng **với hợp đồng SKU đã nêu**. Nếu một class `ItemSnapshot` lại định nghĩa “bằng nhau khi mọi thuộc tính của snapshot giống nhau”, thì `description` có thể là một thành phần cốt lõi và cần được xét. Điều quan trọng là mô hình hóa chính sách trước khi viết code.

Đặc biệt:

- Dữ liệu suy ra **không tự động là dữ liệu vô nghĩa**: một giá trị tổng hợp có thể là dạng chuẩn duy nhất lưu trong hệ thống, khi đó nó cũng có thể là dữ liệu cốt lõi.
- Dữ liệu lưu cache có thể chứa chính kết quả của một hàm thuộc equality, ví dụ mã băm đã tính. Tuy nhiên **trạng thái “cache còn trống hay đã có kết quả”** không tạo ra một sự khác biệt về giá trị.
- Từ khóa Java `transient` chỉ liên quan đến cơ chế Java serialization mặc định của trường; nó **không tự động loại trường khỏi `equals`**. Ngược lại, một trường không khai báo `transient` cũng chưa chắc phải tham gia equality.

## 4. Ví dụ Java 17: mô tả và cache thay đổi, identity không đổi

Ví dụ sau định nghĩa `InventoryItem` có SKU ổn định. Chuỗi nhãn được tính từ SKU và mô tả, sau đó cache lại. Khi mô tả cập nhật, cache được xóa để tính lại. Vì quan hệ bằng nhau của mô hình này chỉ xét SKU, `equals` và `hashCode` không phụ thuộc vào mô tả hoặc cache.

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class EqualityStateDemo {
    static final class InventoryItem {
        // Dữ liệu cốt lõi của equality: SKU chuẩn hóa, bất biến.
        private final String sku;

        // Dữ liệu mô tả: có ích nhưng không xác định identity theo SKU.
        private String description;

        // Dữ liệu ghi nhớ tạm: có thể bỏ đi và tính lại.
        private String cachedLabel;

        InventoryItem(String rawSku, String description) {
            String normalized = Objects.requireNonNull(rawSku, "sku")
                    .trim()
                    .toUpperCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }
            this.sku = normalized;
            this.description = Objects.requireNonNull(description, "description");
        }

        String displayLabel() {
            if (cachedLabel == null) {
                cachedLabel = sku + " - " + description;
            }
            return cachedLabel;
        }

        void updateDescription(String description) {
            this.description = Objects.requireNonNull(description, "description");
            cachedLabel = null; // Làm mới cache khi đầu vào thay đổi.
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof InventoryItem that)) {
                return false;
            }
            return sku.equals(that.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        InventoryItem first = new InventoryItem(" ab-12 ", "Tên cũ");
        InventoryItem second = new InventoryItem("AB-12", "Tên khác");

        Set<InventoryItem> items = new HashSet<>();
        items.add(first);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(items.contains(second));
        System.out.println(first.displayLabel());

        first.updateDescription("Tên mới");
        System.out.println(first.displayLabel());
        System.out.println(items.contains(first));
        System.out.println(items.contains(second));
    }
}
```

Lưu tệp `EqualityStateDemo.java` bằng UTF-8 rồi chạy:

```bash
javac -encoding UTF-8 EqualityStateDemo.java
java EqualityStateDemo
```

Kết quả:

```text
false
true
true
true
AB-12 - Tên cũ
AB-12 - Tên mới
true
true
```

**Giải thích:**

- `first == second` là `false` vì hai lần `new` tạo hai đối tượng khác nhau.
- `first.equals(second)` là `true` vì đầu vào `" ab-12 "` được chuẩn hóa thành `"AB-12"` và cùng SKU với đối tượng thứ hai.
- Hai đối tượng bằng nhau cho cùng `hashCode`, nên `HashSet` có thể tra cứu `second` sau khi thêm `first`.
- Lần gọi `displayLabel()` đầu tiên sinh và lưu `"AB-12 - Tên cũ"`. Sau `updateDescription`, giá trị cache cũ bị hủy, nhãn mới là `"AB-12 - Tên mới"`.
- Kết quả `contains` vẫn đúng vì **không có thay đổi nào ở SKU**, là trường duy nhất xác định equality và hash.

Đây là ví dụ chạy một luồng. Vì `description` và `cachedLabel` thay đổi mà không có đồng bộ hóa, **không được suy ra** rằng cách cache này an toàn nếu dùng chung đối tượng giữa nhiều luồng. Nếu cần truy cập đồng thời, phải thiết kế cơ chế đồng bộ/hiển thị bộ nhớ riêng; yêu cầu đó độc lập với việc chọn trường cho equality.

## 5. Dữ liệu suy ra: so sánh nguồn hay so sánh kết quả?

Giả sử một người dùng có `firstName` và `lastName`, còn `fullName` chỉ là chuỗi ghép từ hai trường. Nếu quan hệ bằng nhau là “cùng cặp tên theo cách lưu dữ liệu hiện tại”, thì so sánh `firstName` và `lastName` đã đủ. So sánh thêm `fullName` là dư thừa, và có thể tạo lỗi nếu một cache chưa được làm mới.

Tuy nhiên, **không phải mọi dữ liệu suy ra đều có thể thay thế cho nguồn**:

- Hai cặp `("An", "Binh")` và `("An Binh", "")` có thể tạo cùng chuỗi hiển thị sau một cách nối, nhưng không nhất thiết đại diện cùng giá trị cặp tên. Nếu equality dựa vào **cặp thành phần**, chỉ so sánh `fullName` là sai về ngữ nghĩa.
- Tổng tiền có thể tính từ đơn giá × số lượng nhưng cũng chịu quy tắc làm tròn, thuế, thời điểm áp dụng tỷ giá. Nếu các đầu vào hoặc chính sách tính toán khác nhau, cùng tổng đã làm tròn chưa chắc đồng nghĩa cùng đối tượng nghiệp vụ.
- Một dữ liệu suy ra phụ thuộc đồng hồ hiện tại, cấu hình hoặc dịch vụ ngoài có thể thay đổi **dù dữ liệu gốc của object không đổi**. Ví dụ, tuổi tính từ ngày sinh thay đổi theo thời gian; không nên dùng “tuổi hôm nay” làm thành phần hash của một khóa lâu dài.

Một quy tắc thực tế: **so sánh tập dữ liệu ổn định, đủ phân biệt theo ngữ nghĩa đã định nghĩa**. Nếu hai thành phần bằng nhau luôn cho cùng kết quả suy ra, không cần dùng thêm kết quả suy ra để chứng minh equality. Nếu kết quả suy ra chứa thông tin hoặc ràng buộc riêng, cần đưa thông tin ấy vào đặc tả của mô hình và cân nhắc trực tiếp.

## 6. Cache là cơ chế hiệu năng, không phải sự thật nghiệp vụ

Cache là bản sao hoặc kết quả trung gian; nó có thể xuất hiện sau lần đọc đầu tiên, bị xóa khi cập nhật, hoặc được dựng lại sau khi deserialization.

### Sai lầm: đưa trạng thái cache vào `equals`

Đoạn dưới đây chỉ minh họa **cách thiết kế sai** bên trong một class có `sku` và `cachedLabel`:

```java
// Sai nếu cachedLabel chỉ là kết quả ghi nhớ tạm.
@Override
public boolean equals(Object other) {
    return other instanceof InventoryItem that
            && Objects.equals(sku, that.sku)
            && Objects.equals(cachedLabel, that.cachedLabel);
}
```

Hai đối tượng cùng SKU có thể khác nhau chỉ vì một bên đã gọi `displayLabel()` còn bên kia chưa gọi. Khi ấy việc **đọc nhãn hiển thị** có thể làm thay đổi kết quả equality, dù không có thay đổi thực chất nào về định danh. Nếu `hashCode` cũng đưa cache vào, mã băm có thể đổi sau lần tính nhãn đầu tiên, khiến việc dùng đối tượng làm hash key trở nên không ổn định.

Để tránh lỗi này, chọn trường gốc cho `equals` và `hashCode`; nếu cần cache chính kết quả `hashCode`, chỉ làm điều đó khi toàn bộ dữ liệu mà hash phụ thuộc vào được bảo đảm không đổi, và xử lý cả vấn đề đồng thời khi có nhiều luồng.

### Khi nào cache có thể là một phần của equality?

Khi một trường tưởng như “cache” thực chất chứa trạng thái được **cam kết là một phần giá trị** và không thể suy ra từ trường còn lại, cần xem lại tên gọi và mô hình. Đó không còn thuần túy là cache theo nghĩa “bỏ đi rồi tính lại mà không mất thông tin”. Phân loại theo **vai trò và ngữ nghĩa**, không theo tên biến.

## 7. Hệ quả của trạng thái thay đổi với `HashSet` và `HashMap`

Hợp đồng của `Object` yêu cầu:

- `equals` phải phản xạ, đối xứng, bắc cầu, nhất quán khi thông tin dùng để so sánh không đổi, và trả `false` với `null`.
- Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải đúng.
- Không có yêu cầu hai đối tượng **khác nhau** phải có mã băm khác nhau; hash collision được phép.

Điều này làm nảy sinh vấn đề: nếu thay đổi một trường **tham gia equality** sau khi đối tượng đã nằm trong `HashSet` hoặc được dùng làm khóa `HashMap`, phép tra cứu có thể không còn tìm được phần tử theo cách mong đợi.

Ví dụ minh họa trường hợp nguy hiểm (đoạn code không phải chương trình độc lập):

```java
// Giả sử class MutableKey có equals/hashCode dựa trên code.
MutableKey key = new MutableKey("A");
Set<MutableKey> set = new HashSet<>();
set.add(key);
key.setCode("B"); // Đổi thông tin định vị theo hash của khóa đã lưu.
// set.contains(key) lúc này có thể không còn đúng kỳ vọng.
```

Không nên biến kết quả ví dụ thành khẳng định `contains` *luôn* trả `false`: hành vi quan sát được còn tùy mã băm trước/sau, bucket và triển khai. Vấn đề là **không còn cơ sở để dựa vào hoạt động tra cứu đúng như khi khóa không đổi**.

Đối với `InventoryItem` trong ví dụ chạy ở trên, thay đổi `description` không ảnh hưởng hợp đồng vì trường ấy không tham gia equality. Trái lại, nếu thay `sku` được, rủi ro sẽ xuất hiện. Vì vậy `sku` được khai báo `final` và chuẩn hóa ngay trong constructor.

**Bất biến theo nghĩa của equality không đòi hỏi mọi thuộc tính của object đều bất biến.** Chỉ cần dữ liệu quyết định equality và hash ổn định trong suốt vòng đời cần thiết; trong thực tế, immutable value objects thường đơn giản và an toàn hơn.

## 8. Chú ý với chuẩn hóa, cấu trúc lồng nhau và `record`

### 8.1. Chuẩn hóa đầu vào

Hai chuỗi `"ab-12"` và `"AB-12"` chỉ được coi là cùng SKU nếu quy tắc nghiệp vụ công nhận không phân biệt chữ hoa/thường. Ví dụ đã chọn `trim()` và `toUpperCase(Locale.ROOT)`; đây là **chính sách của mô hình**, không phải quy tắc Java áp cho mọi mã định danh.

Đừng tự động chuẩn hóa với mọi trường: username có thể phân biệt chữ hoa, mã sản phẩm có thể giữ dấu cách có nghĩa, còn các quy tắc Unicode hoặc ngôn ngữ tự nhiên có thể cần xử lý chuyên biệt. Nếu chuẩn hóa quyết định equality, hãy thực hiện ổn định tại ranh giới tạo đối tượng hoặc sử dụng cùng quy tắc nhất quán trong `equals` và `hashCode`.

### 8.2. Đối tượng lồng nhau và mảng

Nếu equality của một value object phụ thuộc vào một danh sách hay mảng, cần quyết định so sánh theo **nội dung**, thứ tự, hay identity của container. Với mảng Java, `Object.equals` kế thừa theo tham chiếu; có thể cần `Arrays.equals`, `Arrays.deepEquals` và hàm hash tương ứng. Nếu lưu một mảng mutable trong field `final`, từ khóa `final` chỉ ngăn gán lại tham chiếu; **phần tử mảng vẫn có thể bị sửa**. Cân nhắc defensive copy hoặc cấu trúc immutable nếu mảng tham gia equality.

Tương tự, nếu `equals` xét các trường bên trong một đối tượng con mutable, việc đối tượng cha có tất cả field `final` vẫn chưa chắc đảm bảo equality ổn định.

### 8.3. Java `record`

Một `record` Java 17 tự sinh `equals`, `hashCode` và `toString` dựa trên các record components. Điều đó thích hợp khi mọi component được chọn đều thuộc giá trị cần so sánh.

```java
record Money(long cents, String currency) {}
```

Đoạn này minh họa khai báo kiểu; có thể đặt ở mức top-level trong tệp Java phù hợp. Với chính sách “số xu và đơn vị tiền tệ cùng nhau xác định giá trị”, hai component đều có ý nghĩa với equality. Tránh thêm `cachedDisplayText` làm component chỉ để lưu cache: nó mặc nhiên sẽ tham gia các phương thức tự sinh, trừ khi định nghĩa lại hành vi theo thiết kế riêng. Việc dùng `record` cũng không tự động khiến các object mutable được truyền vào component trở nên bất biến sâu.

### 8.4. ORM và entity lifecycle

Ở các mô hình entity lưu cơ sở dữ liệu, ID phát sinh sau khi lưu, proxy, cùng entity ở các phiên làm việc khác nhau và trạng thái chuyển tiếp đều có thể ảnh hưởng cách chọn `equals`/`hashCode`. Không áp dụng máy móc ví dụ “dùng ID trong `equals`” cho entity chưa được gán ID hoặc ID có thể thay đổi. Cần xác định rõ thời điểm ID ổn định, ngữ nghĩa khi ID còn `null` và yêu cầu của framework đang dùng.

## 9. Quy trình thực hành để chọn đúng dữ liệu equality

Trước khi viết `equals` và `hashCode`, hãy làm rõ lần lượt:

1. **Phát biểu bằng một câu:** “Hai đối tượng kiểu X bằng nhau khi …”. Câu này phải dùng ngôn ngữ nghiệp vụ, không dựa vào tên trường cụ thể khi chưa cần.
2. **Lập danh sách trường:** đánh dấu trường nào trực tiếp quyết định equality, trường nào được suy ra, trường nào là cache hoặc metadata vận hành.
3. **Kiểm tra tính đủ và tính tối thiểu:** hai trạng thái khác nhau về dữ liệu cốt lõi có khi nào bị xem nhầm là bằng nhau? Có đang so sánh thêm kết quả có thể suy ra hoàn toàn từ trường đã xét không?
4. **Kiểm tra khả năng thay đổi:** dữ liệu tham gia equality có thể biến đổi không? Nếu có, class có được dùng làm key trong hash collection không?
5. **Đảm bảo `hashCode` tương thích:** mọi cặp bằng nhau phải có cùng mã băm; đồng thời chọn phân bố hash phù hợp để hạn chế va chạm không cần thiết.
6. **Đánh giá vùng biên:** `null`, đối tượng khác kiểu, kế thừa, proxy, mảng, giá trị Unicode/chuẩn hóa, trạng thái chưa có ID và concurrency nếu có.
7. **Thử các tình huống đọc và cache:** tạo hai đối tượng cùng core nhưng khác cache; gọi hàm tính dữ liệu suy ra, xóa/tái tạo cache và thay đổi dữ liệu không thuộc equality. Kết quả `equals`/`hashCode` phải giữ theo ngữ nghĩa đã công bố.

### Ma trận kiểm thử cho mô hình dùng SKU làm định danh

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai đối tượng có cùng SKU sau chuẩn hóa, mô tả khác | `equals == true`; hash bằng nhau |
| Hai đối tượng có SKU khác | `equals == false`; hash **có thể** bằng nhau do va chạm |
| Một bên chưa tạo cache nhãn, bên kia đã tạo | Equality không đổi |
| Cập nhật mô tả và làm mới cache | Equality/hash không đổi |
| So sánh với chính đối tượng | `true` |
| So sánh với `null` | `false` |
| So sánh với đối tượng kiểu khác | `false` |

Các kiểm thử phải khẳng định **hành vi contract**, không khẳng định hai hash của mọi SKU khác nhau hay cấu trúc bucket của `HashSet`.

## 10. Tình huống tự luyện

**Tình huống A:** Một `OrderLine` có `productId`, `quantity`, `unitPrice`, `totalPrice = quantity × unitPrice` và `cachedFormattedTotal`. Yêu cầu là so sánh **giá trị của dòng đơn hàng** theo sản phẩm, số lượng và đơn giá. Chọn dữ liệu equality thế nào?

**Gợi ý đáp án:** Xét `productId`, `quantity` và `unitPrice` theo biểu diễn/ngữ nghĩa giá trị đã xác định. `totalPrice` là dữ liệu suy ra từ hai số đã xét nên không cần lặp lại; `cachedFormattedTotal` chỉ là cache hiển thị, không tham gia. Nếu đơn giá hoặc số lượng có thể sửa, nên tránh dùng đối tượng mutable này trực tiếp làm hash key lâu dài hoặc thiết kế immutable snapshot.

**Tình huống B:** Một `Session` có `sessionId`, `lastAccessedAt` và `cachedPermissions`. Hệ thống quy định cùng `sessionId` là cùng phiên. Một lần truy cập cập nhật `lastAccessedAt` và nạp lại quyền. `equals` có nên thay đổi?

**Gợi ý đáp án:** Không, nếu `sessionId` thực sự là định danh bất biến trong phạm vi so sánh. Hai trường còn lại là metadata vận hành/cache theo mô hình này. Dĩ nhiên, việc có cùng session ID không tự xác nhận hai cache quyền đều còn hiệu lực; tính hợp lệ của phiên là một bài toán khác equality.

**Tình huống C:** Một `Point` lưu `x`, `y` và cache `distanceFromOrigin`. Hai điểm được xem bằng nhau khi tọa độ giống nhau. Có nên so sánh cache khoảng cách?

**Gợi ý đáp án:** Không. Hai điểm khác tọa độ có thể cùng khoảng cách đến gốc; còn cache có thể chưa tính. `x` và `y` mới là dữ liệu đủ để quyết định equality. Nếu tọa độ có thể sửa thì phải làm mới cache và cân nhắc rủi ro khi dùng `Point` làm khóa.

## 11. Ghi nhớ

- **Chọn ngữ nghĩa trước, chọn trường sau.** “Dữ liệu cốt lõi” là tập trường quyết định quan hệ bằng nhau, và phụ thuộc vào việc so sánh thực thể hay giá trị.
- **Dữ liệu suy ra** thường không cần so sánh nếu được xác định hoàn toàn từ tập dữ liệu cốt lõi đã xét; tránh dùng riêng biểu diễn bị mất thông tin để thay nguồn.
- **Cache** thường được bỏ qua trong equality vì trạng thái đã tính/chưa tính không thay đổi bản chất object. Cache phải có chính sách invalidation khi nguồn thay đổi.
- **`equals` và `hashCode` phải cùng tuân theo một quan hệ bằng nhau**: bằng nhau ⇒ cùng hash; chiều ngược lại không bắt buộc.
- **Ổn định khi dùng hash collection**: hạn chế sửa dữ liệu tham gia equality/hash sau khi chèn đối tượng vào `HashSet` hoặc làm khóa `HashMap`.
- **Không đánh đồng từ khóa `final`, `transient`, tên `id` hay `record` với quyết định equality**: phải hiểu ý nghĩa và vòng đời thực tế của dữ liệu.

Đối chiếu đặc tả chính thức: [`Object.equals` và `Object.hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [`Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).
