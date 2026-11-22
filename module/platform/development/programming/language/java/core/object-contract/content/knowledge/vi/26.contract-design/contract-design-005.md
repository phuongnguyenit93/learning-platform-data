# Tài liệu hóa trường tham gia so sánh và những ngoại lệ có chủ ý

Khi định nghĩa `equals(Object)` và `hashCode()` cho một lớp Java, quyết định quan trọng nhất là: **những thuộc tính nào khiến hai đối tượng được xem là cùng một giá trị theo ngữ nghĩa của miền nghiệp vụ?** Quyết định này cần được viết rõ thành hợp đồng; chỉ nhìn vào các dòng `Objects.equals(...)` thường không đủ để người dùng lớp hiểu vì sao một trường được đưa vào hay loại ra.

Trong chủ đề này, “ngoại lệ có chủ ý” nghĩa là **trường được cố ý loại khỏi phép so sánh**, hoặc một lựa chọn khác với trực giác thông thường đã được cân nhắc và ghi rõ. Đây không phải cơ chế ném ngoại lệ (`Exception`) của Java.

## 1. Xuất phát từ định nghĩa bình đẳng của miền nghiệp vụ

Trước khi liệt kê trường, hãy trả lời hai câu hỏi:

1. **Hai đối tượng khác nhau có được xem là cùng một thực thể/giá trị không?** Ví dụ: hai bản sao của sản phẩm có cùng mã trong cùng cửa hàng có thể đại diện cho cùng một mặt hàng, dù tên hiển thị và số lượng tồn kho khác nhau.
2. **Thay đổi nào làm thay đổi sự đồng nhất ấy?** Nếu thay mã sản phẩm hoặc cửa hàng sở hữu thì không còn cùng mặt hàng; nếu chỉ sửa tên hiển thị thì vẫn là mặt hàng đó.

Có hai cách nhìn thường gặp:

- **Value equality (bình đẳng theo giá trị):** so sánh tổ hợp các thành phần có ý nghĩa, như mã tiền tệ và số tiền của một giá trị tiền tệ. Mọi thành phần góp phần định nghĩa giá trị đều cần được xem xét.
- **Business identity (định danh nghiệp vụ):** so sánh một khóa nghiệp vụ ổn định, ví dụ `(tenantId, sku)`. Những thuộc tính có thể cập nhật sau đó không nhất thiết thuộc khóa đồng nhất.

Không có quy tắc “mọi trường đều vào `equals`” hay “chỉ dùng `id`” áp dụng đúng cho mọi lớp. Tên trường, annotations, thứ tự khai báo và việc một trường có phải khóa database hay không **không tự quyết định** ngữ nghĩa bình đẳng của miền.

## 2. Ghi rõ trường nào tham gia và trường nào bị loại

Giả sử một lớp `Product` mô tả mặt hàng của nhiều cửa hàng, mỗi cửa hàng có thể dùng cùng chuỗi SKU. Ta chọn **khóa đồng nhất là cặp `(tenantId, sku)`**.

| Trường | Tham gia `equals/hashCode`? | Lý do và quy tắc |
| --- | --- | --- |
| `tenantId` | **Có** | Phân biệt hai cửa hàng sử dụng cùng mã SKU; bất biến sau khi tạo. |
| `sku` | **Có** | Là mã duy nhất trong phạm vi `tenantId`; bất biến sau khi tạo. |
| `displayName` | **Không, có chủ ý** | Tên hiển thị có thể thay đổi, dịch hoặc sửa lỗi chính tả mà không làm mặt hàng thành một đối tượng nghiệp vụ khác. |
| `stock` | **Không, có chủ ý** | Tồn kho biến động theo giao dịch; thay đổi tồn kho không đổi khóa đồng nhất. |

Bên cạnh bảng này, tài liệu hợp đồng cần nêu rõ những giả định có thể gây hiểu lầm:

- `tenantId` và `sku` không được `null`; khóa được so sánh **phân biệt chữ hoa/chữ thường**. `"SKU-7"` khác `"sku-7"` vì ví dụ không tự chuẩn hóa.
- Cặp khóa phải duy nhất trong miền nghiệp vụ đang xét; việc hai đối tượng cùng khóa có các trạng thái khác nhau là **được chấp nhận trong mô hình này**.
- Không thay đổi khóa sau khi đưa đối tượng vào `HashMap` hoặc `HashSet`. Trong ví dụ, hai thành phần khóa là `final`.
- `displayName` và `stock` bị loại **khỏi cả `equals` lẫn `hashCode`**. Một bên có trường này còn bên kia không có sẽ phá vỡ yêu cầu: bằng nhau thì phải có cùng hash code.

## 3. Javadoc ngay cạnh hiện thực và ví dụ chạy được

Mô tả của lớp cần đặt gần mã để người bảo trì thấy hợp đồng khi sửa `equals` hoặc `hashCode`. Chương trình Java 17+ sau minh họa một cách viết hoàn chỉnh.

Lưu thành **`EqualityContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class EqualityContractDemo {
    public static void main(String[] args) {
        Product first = new Product("shop-a", "SKU-7", "Bàn phím", 3);
        Product sameKey = new Product("shop-a", "SKU-7", "Keyboard", 0);
        Product otherShop = new Product("shop-b", "SKU-7", "Bàn phím", 3);

        System.out.println("same key: " + first.equals(sameKey));
        System.out.println("same hash: " + (first.hashCode() == sameKey.hashCode()));
        System.out.println("different shop: " + first.equals(otherShop));

        Map<Product, String> approved = new HashMap<>();
        approved.put(first, "đã duyệt");
        System.out.println("lookup same key: " + approved.get(sameKey));

        first.rename("Tên mới");
        first.setStock(0);
        System.out.println("lookup after updates: " + approved.get(first));
    }

    /**
     * Mặt hàng được đồng nhất theo (tenantId, sku).
     *
     * <p>Trường tham gia: tenantId và sku; cả hai không null,
     * bất biến và so sánh phân biệt hoa/thường.
     *
     * <p>Loại trừ có chủ ý: displayName và stock, vì thay đổi
     * trình bày/tồn kho không thay đổi danh tính mặt hàng.
     * hashCode dùng đúng hai trường tham gia equals.
     *
     * <p>Lớp final: lớp con không được mở rộng quy tắc đồng nhất.
     */
    static final class Product {
        private final String tenantId;
        private final String sku;
        private String displayName;
        private int stock;

        Product(String tenantId, String sku, String displayName, int stock) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.sku = Objects.requireNonNull(sku);
            this.displayName = Objects.requireNonNull(displayName);
            this.stock = stock;
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        void setStock(int quantity) {
            stock = quantity;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Product other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, sku);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac EqualityContractDemo.java
java EqualityContractDemo
```

Kết quả:

```text
same key: true
same hash: true
different shop: false
lookup same key: đã duyệt
lookup after updates: đã duyệt
```

**Giải thích:** `first` và `sameKey` có cùng hai trường khóa, dù `displayName` và `stock` khác nhau, nên `equals` trả về `true` và `hashCode` bằng nhau. `otherShop` khác `tenantId` nên không bằng `first`. `HashMap` tìm được giá trị qua khóa tương đương, và việc sửa các trường đã loại trừ không làm thay đổi hash code của `first`.

Dòng `same hash: true` minh họa hướng bắt buộc của hợp đồng: **`a.equals(b) == true` thì `a.hashCode() == b.hashCode()`**. Chiều ngược lại **không bắt buộc**: hai đối tượng không bằng nhau vẫn có thể trùng hash do va chạm.

Ví dụ cố ý dùng `final class` để tránh việc lớp con thêm trường vào `equals` rồi làm mất tính đối xứng với lớp cha. Nếu thiết kế cho phép kế thừa, cần quy định và kiểm chứng chính sách so sánh giữa các kiểu một cách riêng biệt.

## 4. Những quyết định loại trừ phải có lý do kiểm chứng được

Không nên viết `// ignore stock` mà không giải thích hậu quả. Một tài liệu tốt gồm **quyết định → lý do miền nghiệp vụ → tình huống kiểm chứng → hệ quả**.

### Loại trường thay đổi thường xuyên

Ví dụ `stock` thay đổi mỗi phút nhưng mặt hàng vẫn giữ `(tenantId, sku)`. Đưa `stock` vào `hashCode` có thể làm khóa bị “mất dấu” sau khi đối tượng được đưa vào `HashMap` hoặc `HashSet`. Ghi rõ: “Tồn kho là trạng thái tức thời; cố ý không tham gia định danh và có thể sửa sau khi đối tượng làm khóa của collection.”

Tuy nhiên, nếu lớp thực chất là **bản ghi snapshot tồn kho**, số lượng có thể là một phần giá trị. Khi đó phải thay đổi định nghĩa và tài liệu thay vì máy móc sao chép quy tắc của `Product`.

### Loại trường kỹ thuật, dẫn xuất hoặc liên kết

Một số lớp có timestamp cập nhật, nhãn đã tính toán, cache, hoặc liên kết ngược tới đối tượng khác. Nếu các trường này không tạo nên giá trị/định danh, có thể loại trừ, nhưng tài liệu phải nêu **vì sao khác nhau vẫn được coi là bằng nhau**.

Ví dụ: `lastViewedAt` là dấu mốc giao diện, không làm thay đổi định danh mặt hàng. Ngược lại, `currency` thường không thể bị loại khi so sánh giá trị tiền tệ, vì `100 USD` và `100 VND` không phải cùng một giá trị.

### Khóa được cấp sau khi tạo đối tượng

Một khóa database tự sinh ban đầu có thể là `null` rồi được gán khi lưu. Nếu chọn khóa này để định danh, cần làm rõ đối tượng chưa lưu được so sánh ra sao, thời điểm nào giá trị hash thay đổi và việc lưu trữ trong hash collection có an toàn không. **Không được tự tiện kết luận hai đối tượng có `id == null` là bằng nhau.** Các quy tắc cho entity của ORM còn phụ thuộc vòng đời và proxy; thiết kế/ghi chú riêng trước khi triển khai.

### Chuẩn hóa giá trị khi so sánh

Nếu nghiệp vụ coi `"SKU-7"` và `"sku-7"` là cùng mã, hãy định nghĩa rõ **thời điểm chuẩn hóa** (ví dụ ngay trong constructor bằng `toUpperCase(Locale.ROOT)`), quy tắc khoảng trắng, locale và giá trị `null`. `equals` và `hashCode` phải dùng cùng giá trị đã chuẩn hóa. Không chỉ áp dụng `equalsIgnoreCase` cho `equals` rồi tiếp tục hash chuỗi gốc theo kiểu phân biệt chữ hoa/chữ thường.

## 5. Hợp đồng Java phải được giữ nguyên

Tài liệu trường tham gia so sánh cần kiểm tra các tính chất sau của `equals`:

- **Phản xạ:** với đối tượng không `null`, `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho kết quả như nhau.
- **Bắc cầu:** nếu `x` bằng `y` và `y` bằng `z`, thì `x` bằng `z`.
- **Nhất quán:** khi các thông tin dùng để so sánh không đổi, các lần gọi cho kết quả giống nhau.
- **So với `null`:** `x.equals(null)` là `false`.

Với `hashCode`: hai đối tượng bằng nhau phải trả về cùng một giá trị hash; các lần gọi trên cùng đối tượng phải ổn định khi dữ liệu tham gia `equals` không đổi. Phép hash **không cần duy nhất** giữa các đối tượng khác nhau.

Việc tự ý thêm hoặc bỏ một trường trong `equals` có thể thay đổi hành vi của `Set.contains`, `Map.get`, bộ nhớ đệm, gom nhóm/deduplicate và kết quả test. Thay đổi này cần được xem là **thay đổi hợp đồng có tác động tới mã sử dụng**, không đơn thuần là tối ưu nội bộ.

## 6. Mẫu ghi quyết định và checklist review

Có thể dùng cấu trúc ngắn sau trong Javadoc hoặc tài liệu thiết kế để các quyết định được giữ nhất quán:

```text
Định nghĩa bình đẳng:
  Hai Product bằng nhau khi cùng tenantId và cùng sku.

Trường tham gia:
  tenantId, sku — không null, bất biến, phân biệt hoa/thường.

Loại trừ có chủ ý:
  displayName — thay đổi trình bày không đổi định danh.
  stock       — cập nhật tồn kho không đổi định danh.

Giới hạn:
  Áp dụng cho Product final; không ngụ ý rằng hai snapshot có cùng nội dung.

Hệ quả:
  Thay displayName/stock không ảnh hưởng equals/hashCode.
  Đổi tenantId/sku cần một đối tượng khóa nghiệp vụ khác.

Trường hợp cần kiểm tra:
  Cùng khóa/khác trạng thái; khác tenant/cùng SKU;
  so với null; ba đối tượng có cùng khóa; tra cứu HashMap.
```

Khi review một hiện thực, hãy xác nhận các điểm sau:

1. **Có định nghĩa bình đẳng bằng ngôn ngữ miền nghiệp vụ**, thay vì chỉ mô tả “so sánh hai trường”.
2. **Từng trường quan trọng được phân loại**, đặc biệt những trường tưởng như phải so sánh nhưng bị loại có chủ ý.
3. **`equals` và `hashCode` dùng cùng tổ hợp trường**, tuân thủ phản xạ, đối xứng, bắc cầu và tính nhất quán.
4. **Tính bất biến của khóa được bảo đảm hoặc giới hạn được nêu rõ**, đặc biệt nếu đối tượng dùng làm khóa của hash collection.
5. **Chính sách `null`, chuẩn hóa, phân biệt hoa/thường và kế thừa được công bố** nếu chúng ảnh hưởng kết quả.
6. **Có ví dụ hoặc kiểm tra cho lựa chọn loại trừ**, như cùng định danh nhưng khác tồn kho vẫn bằng nhau; không chỉ test hai đối tượng có mọi trường giống hệt nhau.
7. **Nếu dùng `record`**, nhớ rằng `equals/hashCode` do record sinh mặc định xét tất cả record components; nếu muốn ngoại lệ, phải cân nhắc mô hình record hoặc chủ động định nghĩa lại và tài liệu hóa sự thay đổi.

**Ghi nhớ:** tên các trường có mặt trong `equals`/`hashCode` mới cho thấy *cách mã chạy*; tài liệu về trường được chọn, trường bị loại có chủ ý và các ràng buộc bất biến mới giải thích *vì sao đó là hợp đồng đúng*.
