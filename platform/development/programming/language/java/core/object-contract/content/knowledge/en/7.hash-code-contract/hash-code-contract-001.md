# `hashCode()` trả về `int` để hỗ trợ cấu trúc dữ liệu băm

## 1. `hashCode()` là gì và vì sao kiểu trả về là `int`?

Trong Java, mọi lớp kế thừa phương thức `public int hashCode()` từ `java.lang.Object` (có thể ghi đè). Phương thức trả về một **giá trị băm 32-bit có dấu** để các cấu trúc dữ liệu dựa trên bảng băm, như `HashMap` và `HashSet`, tổ chức và tra cứu phần tử hiệu quả.

- **Kiểu `int` là một phần của chữ ký phương thức theo Java**, không phải lựa chọn tuỳ ý ở lớp con. Miền giá trị là từ `-2_147_483_648` đến `2_147_483_647` (tổng cộng `2^32` mẫu bit). Số âm, số 0 và số dương đều là kết quả hợp lệ.
- **Hash code không phải ID duy nhất.** Không gian 32-bit hữu hạn, nên những đối tượng khác nhau hoàn toàn có thể cùng hash code (collision, hay đụng độ băm).
- **Hash code không phải chỉ số ngăn (bucket) trực tiếp.** Cấu trúc băm còn phải chuyển đổi giá trị băm sang vị trí trong vùng lưu trữ hiện tại. Thuật toán chuyển đổi và số bucket phụ thuộc cách triển khai; chúng có thể thay đổi khi cấu trúc mở rộng.
- **Hash code cũng không phải địa chỉ bộ nhớ được bảo đảm.** `Object.hashCode()` mặc định gắn với sự bằng nhau theo danh tính đối tượng, nhưng Java không cam kết nó là địa chỉ, duy nhất hay giữ nguyên giữa những lần chạy JVM.

Trả về một `int` tạo ra giao diện chung để các thư viện Java có thể băm mọi đối tượng. Giá trị này giúp *thu hẹp phạm vi ứng viên cần kiểm tra*; việc xác định hai khoá có thực sự bằng nhau vẫn dựa trên `equals()`.

## 2. `HashMap` và `HashSet` sử dụng giá trị băm như thế nào?

Khi thêm và tìm một khoá khác `null` trong `HashMap`, có thể hiểu ở mức khái niệm như sau:

1. Gọi `hashCode()` của khoá để lấy số nguyên băm; triển khai có thể trộn thêm các bit.
2. Chuyển giá trị băm thành vị trí bucket trong bảng đang dùng.
3. Tìm trong bucket các mục ứng viên. Khi gặp hash tương ứng, so sánh tính bằng nhau của khoá, thường qua `equals()`; nếu nhiều khoá rơi vào cùng bucket, cấu trúc phải phân biệt chúng.
4. Nếu tìm thấy khoá tương đương theo `equals()`, `put` cập nhật giá trị; nếu chưa có, thêm mục mới. Khi `get`, chỉ trả về giá trị ứng với khoá phù hợp.

`HashSet` có ý tưởng tương tự để quyết định phần tử đã có trong tập hợp hay chưa; triển khai chuẩn dựa trên một `HashMap` nội bộ. Đặc biệt, **trùng hash code không đồng nghĩa trùng phần tử**. Hai khoá khác nhau có cùng hash vẫn được lưu riêng nếu `equals()` trả `false`.

Chi tiết bucket, cơ chế xử lý va chạm và chính sách mở rộng là vấn đề triển khai; không nên dựa vào công thức bucket cụ thể, thứ tự duyệt hay vị trí cố định của phần tử trong chương trình.

Với hàm băm phân phối hợp lý và mức tải thích hợp, thao tác thông thường của bảng băm có chi phí trung bình gần `O(1)`. Nếu quá nhiều khoá va chạm hoặc phân phối kém, chi phí xử lý trong bucket tăng; `hashCode()` không bảo đảm mỗi thao tác luôn `O(1)`.

## 3. Hợp đồng bắt buộc giữa `equals()` và `hashCode()`

Theo hợp đồng của `Object`:

- Trong một lần thực thi ứng dụng Java, khi dữ liệu dùng để xác định `equals()` của một đối tượng không thay đổi, các lần gọi `hashCode()` trên đối tượng đó phải trả về cùng kết quả.
- **Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`** (giả sử `a`, `b` khác `null`).
- Nếu `a.equals(b)` là `false`, **không có yêu cầu** hai hash code phải khác nhau. Va chạm hợp lệ.
- Hai lần chạy độc lập của cùng chương trình không nhất thiết tạo cùng hash code cho mọi đối tượng.

Vì vậy, **lớp ghi đè `equals()` cần ghi đè `hashCode()` nhất quán**. Nếu hai khoá được xem là bằng nhau nhưng cho hash khác nhau, `HashMap.get()` hoặc `HashSet.contains()` có thể không tìm thấy phần tử đã lưu.

Chiều ngược lại không đúng:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  =/=>  a.equals(b) == true
```

## 4. Chương trình Java 17+ chứng minh va chạm băm

Lưu chương trình hoàn chỉnh dưới tên `HashCodeDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashCodeDemo {
    static final class Key {
        private final String value;

        Key(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Key other)) return false;
            return value.equals(other.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }

    public static void main(String[] args) {
        Key first = new Key("FB");
        Key second = new Key("Ea");

        Map<Key, String> map = new HashMap<>();
        map.put(first, "first");
        map.put(second, "second");

        System.out.println("hash(FB): " + first.hashCode());
        System.out.println("hash(Ea): " + second.hashCode());
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("map.size(): " + map.size());
        System.out.println("lookup new FB: " + map.get(new Key("FB")));
        System.out.println("lookup new Ea: " + map.get(new Key("Ea")));
    }
}
```

Biên dịch và chạy:

```bash
javac HashCodeDemo.java
java HashCodeDemo
```

Kết quả chính xác:

```text
hash(FB): 2236
hash(Ea): 2236
first.equals(second): false
map.size(): 2
lookup new FB: first
lookup new Ea: second
```

Giải thích:

- Trong Java, `String.hashCode()` tính theo công thức tích luỹ `31 * h + ký_tự`. `"FB"` và `"Ea"` đều cho `2236`: `70 * 31 + 66 = 2236`, `69 * 31 + 97 = 2236`.
- Hai `Key` dùng `value.hashCode()` nên cũng cho cùng hash code. Tuy nhiên `value.equals(...)` trả `false` vì `"FB"` khác `"Ea"`.
- `HashMap` giữ **hai** khoá riêng. Một khoá `new Key("FB")` mới có cùng ý nghĩa với `first` theo `equals()` và có cùng hash code, nên tìm lại được giá trị `"first"`.
- Không có gì trong ví dụ yêu cầu biết bucket nội bộ của `HashMap`; kết quả chỉ chứng minh hash code dùng để tìm ứng viên còn `equals()` quyết định tính bằng nhau.

## 5. Thiết kế `hashCode()` cho lớp tự định nghĩa

Để giữ đúng hợp đồng, chọn các trường dữ liệu tham gia `equals()` làm cơ sở tính băm. Ví dụ dưới đây là một đoạn lớp minh hoạ độc lập về mặt cú pháp lớp (không có `main`):

```java
import java.util.Objects;

final class ProductKey {
    private final String sku;
    private final int version;

    ProductKey(String sku, int version) {
        this.sku = Objects.requireNonNull(sku);
        this.version = version;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ProductKey other)) return false;
        return version == other.version && sku.equals(other.sku);
    }

    @Override
    public int hashCode() {
        int result = sku.hashCode();
        return 31 * result + Integer.hashCode(version);
    }
}
```

Trong ví dụ, `equals()` xét `sku` và `version`; `hashCode()` cũng xét cả hai. Phép nhân/cộng `int` có thể tràn số theo quy tắc số nguyên Java, điều đó **được phép** đối với hash code. Đây là công thức kết hợp thông dụng, không phải công thức duy nhất.

Các công cụ hỗ trợ:

- `Objects.hash(sku, version)` giúp kết hợp nhiều trường; có tạo mảng varargs và thao tác đóng hộp trong một số trường hợp, vì vậy cân nhắc khi ở đường xử lý hiệu năng cao.
- `Objects.hashCode(reference)` trả về `0` nếu đối số là `null`, còn khác `null` thì gọi `reference.hashCode()`.
- Nếu trường là mảng và muốn so sánh theo **nội dung mảng**, dùng cặp `Arrays.equals(...)` / `Arrays.hashCode(...)` (hoặc biến thể sâu phù hợp với mảng lồng nhau); bản thân mảng không tự so sánh nội dung bằng `Object.equals()`.
- Java `record` tự sinh `equals()` và `hashCode()` phù hợp dựa trên các thành phần record. Có thể ưu tiên record cho đối tượng giá trị khi đáp ứng yêu cầu thiết kế.

## 6. Các lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả hoặc cách hiểu đúng |
| --- | --- |
| Chỉ ghi đè `equals()`, bỏ `hashCode()` | Hai đối tượng bằng nhau có thể có hash khác nhau; tra cứu trong cấu trúc băm sai |
| Nghĩ hash trùng nghĩa là đối tượng bằng nhau | Hash trùng là va chạm bình thường; vẫn cần `equals()` để phân biệt |
| Dùng số băm làm ID toàn cục hoặc khoá cơ sở dữ liệu duy nhất | `int` hữu hạn, va chạm được phép, không bảo đảm ổn định qua nhiều lần chạy |
| Luôn trả về cùng một số (chẳng hạn `1`) | Không nhất thiết vi phạm hợp đồng nhưng làm phân phối rất kém và giảm hiệu suất |
| Thay đổi trường tham gia `equals()` / `hashCode()` sau khi đưa khoá vào `HashMap` | Khoá có thể được tìm ở bucket khác với lúc lưu, khiến `get`/`containsKey` thất bại |
| Cho rằng hash code luôn không âm | Hash code `int` có dấu; thư viện băm phải xử lý cả giá trị âm |
| Giả định thứ tự duyệt `HashMap` do hash quyết định ổn định | `HashMap` không cam kết thứ tự duyệt, kể cả sau khi thêm/xoá hoặc resize |

**Khuyến nghị:** Dùng khoá bất biến (các trường tham gia so sánh là `final` và các giá trị thành phần không bị thay đổi). Kiểm thử hai chiều: các đối tượng bằng nhau phải có cùng hash; các đối tượng khác nhau vẫn được cấu trúc băm quản lý đúng ngay cả khi vô tình trùng hash.

## 7. Tự kiểm tra kiến thức

1. Hai đối tượng khác nhau cùng trả về hash `42`. `HashSet` có bắt buộc chỉ giữ một đối tượng? **Không**; nó phải xét `equals()` để xác định phần tử bằng nhau.
2. Hai đối tượng được `equals()` xem là bằng nhau nhưng có hash khác nhau. Có hợp lệ? **Không**; đó là vi phạm hợp đồng và có thể làm hỏng logic tra cứu.
3. Có thể nhận hash âm từ một đối tượng hợp lệ? **Có**; `hashCode()` trả về kiểu `int` có dấu.
4. Có thể suy ra bucket từ chính `hashCode()` để lưu ngoài `HashMap`? **Không nên**; bucket phụ thuộc dung lượng và cách triển khai, không phải phần của hợp đồng `Object.hashCode()`.

**Ghi nhớ:** `hashCode()` trả `int` để hỗ trợ ánh xạ nhanh từ khoá tới nhóm ứng viên; `equals()` xác định khoá có thực sự bằng nhau. **Bằng nhau ⇒ cùng hash; cùng hash ⇏ bằng nhau.**