# HashMap và HashSet phối hợp `hashCode()` với `equals()` như thế nào?

## 1. Bài toán cần giải quyết

`HashMap<K, V>` lưu cặp **khóa → giá trị** để tra cứu, thêm hoặc xóa theo khóa. `HashSet<E>` lưu những **phần tử không trùng nhau**. Muốn thực hiện các thao tác này hiệu quả, hai cấu trúc cần trả lời:

1. Nên tìm khóa hoặc phần tử ở **nhóm ứng viên** nào?
2. Trong nhóm đó, đối tượng đang tìm có **bằng** một đối tượng đã lưu không?

Với các đối tượng Java thông thường, hai phương thức hợp tác để trả lời:

- **`hashCode()`** trả về một số nguyên `int` đại diện cho giá trị băm. Nó giúp cấu trúc băm định vị nhóm ứng viên có thể chứa khóa hoặc phần tử.
- **`equals(Object)`** quyết định hai đối tượng có được xem là **bằng nhau về mặt logic** hay không.

`hashCode()` là bước hỗ trợ chọn nơi tìm; `equals()` mới xác nhận sự bằng nhau. **Trùng mã băm chưa đủ để coi hai đối tượng bằng nhau.**

Ví dụ: hai mã sản phẩm khác nhau có thể tình cờ cho cùng một hash. `HashMap` vẫn phải phân biệt chúng thành hai khóa; `HashSet` vẫn phải chứa được cả hai phần tử nếu `equals()` trả `false`.

## 2. Hợp đồng bắt buộc giữa equals và hashCode

Hợp đồng trong `java.lang.Object` quy định:

> Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`.

Chiều ngược lại **không bắt buộc**. Hai đối tượng có cùng mã băm có thể hoàn toàn khác nhau; đó là **hash collision** (va chạm băm).

| Quan hệ giữa `a`, `b` | Hợp lệ không? | Ý nghĩa |
| --- | --- | --- |
| `a.equals(b)` là `true`, mã băm bằng nhau | Có, bắt buộc | Hai đối tượng được coi là cùng một khóa/phần tử logic |
| `a.equals(b)` là `false`, mã băm khác nhau | Có | Có thể thuộc các nhóm băm khác nhau |
| `a.equals(b)` là `false`, mã băm bằng nhau | Có | Va chạm; phải dùng `equals` để phân biệt |
| `a.equals(b)` là `true`, mã băm khác nhau | **Không** | Vi phạm hợp đồng, gây lỗi với cấu trúc băm |

Ngoài tương thích với `hashCode`, `equals(Object)` còn phải bảo đảm tính **phản xạ, đối xứng, bắc cầu, nhất quán** và `x.equals(null)` là `false` đối với `x` khác `null`. `hashCode()` phải trả cùng kết quả qua các lần gọi trong một lần chạy khi những thông tin dùng bởi `equals` không thay đổi. Nó không cần giữ nguyên qua các lần chạy chương trình khác nhau.

Do đó, quy tắc thực hành là: **khi ghi đè `equals(Object)` để xác định bình đẳng theo giá trị, hãy ghi đè `hashCode()` theo chính các thành phần tạo nên bình đẳng ấy.**

## 3. HashMap xử lý put/get bằng hai phương thức ra sao?

Giả sử cần thực hiện `map.put(key, value)` hoặc `map.get(key)`.

### Bước 1 — Lấy mã băm và xác định vị trí ứng viên

`HashMap` sử dụng `hashCode()` của khóa để tính vị trí hoặc nhóm ứng viên trong bảng băm. Bảng có thể thay đổi kích thước; JDK cũng có thể thực hiện các bước trộn bit của hash. Vì vậy **không nên suy luận vị trí lưu chỉ từ số `hashCode()` hiển thị**.

### Bước 2 — So khóa trong nhóm ứng viên

Nếu đã có khóa khác có hash phù hợp, `HashMap` phải kiểm tra **cùng tham chiếu hoặc bằng nhau theo `equals(Object)`** để biết chúng có biểu thị cùng khóa logic hay không.

- Nếu khóa mới **bằng** khóa đã lưu: `put` thay giá trị gắn với khóa hiện có và trả về giá trị cũ (nếu có).
- Nếu khóa mới **không bằng** khóa đã lưu: `put` có thể lưu thêm một mục, kể cả hai khóa có cùng mã băm.
- Khi `get` được gọi, cấu trúc đi vào các ứng viên có hash phù hợp rồi dùng phép kiểm tra equality để chọn đúng mục; nếu không thấy thì trả `null`.

Lưu ý `get` trả `null` cũng có thể vì khóa **có tồn tại nhưng được ánh xạ tới giá trị `null`**. Sử dụng `containsKey(key)` khi cần phân biệt hai trường hợp.

### Bước 3 — Xử lý va chạm hoặc thay đổi kích thước

Một nhóm có thể chứa nhiều khóa khác nhau cùng hash. Triển khai `HashMap` trong OpenJDK có các cơ chế xử lý va chạm (và có thể chuyển nhóm đủ lớn sang cấu trúc dạng cây), nhưng đó là **chi tiết triển khai**, không phải hợp đồng mà mã ứng dụng được phép dựa vào.

Sơ đồ khái quát:

```text
put / get
   |
   v
key.hashCode()
   |
   v
Xác định nhóm ứng viên trong bảng băm
   |
   v
So hash, rồi kiểm tra cùng tham chiếu / equals(Object)
   |
   +-- bằng khóa đã lưu ------> cùng khóa logic
   |                            put: thay giá trị; get: trả giá trị
   |
   +-- chưa có khóa bằng -----> put: thêm mục; get: không tìm thấy
```

Không phải mỗi phép gọi đều nhất thiết trực tiếp gọi `equals`: trường hợp cùng tham chiếu có thể được xử lý nhanh. Nhưng quyết định về **bình đẳng giữa các đối tượng khác tham chiếu** phải nhất quán với hợp đồng `equals(Object)`.

## 4. HashSet dựa vào cùng logic như thế nào?

Về hành vi công khai, `HashSet` trả lời câu hỏi **“tập hợp đã chứa phần tử bằng phần tử này chưa?”**:

- `set.add(x)` trả `true` nếu tập hợp thay đổi do thêm `x`.
- Nếu đã có phần tử `y` mà `x.equals(y)` theo hợp đồng là `true`, `add(x)` trả `false`; không tạo thêm phần tử logic.
- `contains(x)` và `remove(x)` cũng cần định vị bằng mã băm rồi phân biệt bằng equality.

Trong triển khai Java tiêu chuẩn, `HashSet` dùng một `HashMap` bên trong: phần tử set đóng vai trò **khóa** của map, còn giá trị kèm theo chỉ là chi tiết nội bộ. Vì vậy các quy tắc `hashCode`/`equals` áp dụng tương tự cho cả hai.

| Thao tác | `HashMap` | `HashSet` |
| --- | --- | --- |
| Thêm phần tử logic mới | `put(k, v)` thêm khóa | `add(e)` thêm phần tử, trả `true` |
| Thêm đối tượng khác nhưng bằng khóa/phần tử cũ | `put` cập nhật giá trị ở khóa tương ứng | `add` không thêm mục logic mới, trả `false` |
| Hai đối tượng khác nhau nhưng cùng `hashCode()` | Có thể tồn tại như hai khóa nếu không `equals` | Có thể cùng tồn tại nếu không `equals` |
| Tra cứu | `get`, `containsKey` | `contains` |

Cả `HashMap` và `HashSet` đều cho phép `null`: `HashMap` có tối đa một khóa `null`; `HashSet` có tối đa một phần tử `null`. `HashMap`/`HashSet` thường không bảo đảm thứ tự duyệt, nên thứ tự đầu ra khi lặp không được dùng làm bằng chứng về vị trí băm.

## 5. Ví dụ Java 17+: đúng hợp đồng và có va chạm hash

Tạo tệp `HashContractDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {
    static final class ProductKey {
        private final String sku;

        ProductKey(String sku) {
            this.sku = Objects.requireNonNull(sku);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ProductKey other)) {
                return false;
            }
            return sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    static final class CollisionKey {
        private final String code;

        CollisionKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof CollisionKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 7; // Cố ý tạo collision để minh họa.
        }
    }

    public static void main(String[] args) {
        ProductKey first = new ProductKey("P-10");
        ProductKey same = new ProductKey("P-10");
        ProductKey other = new ProductKey("P-20");

        Map<ProductKey, String> prices = new HashMap<>();
        prices.put(first, "100");
        System.out.println(prices.put(same, "120"));
        prices.put(other, "250");
        System.out.println(prices.size());
        System.out.println(prices.get(new ProductKey("P-10")));

        Set<ProductKey> products = new HashSet<>();
        System.out.println(products.add(first));
        System.out.println(products.add(same));
        System.out.println(products.add(other));
        System.out.println(products.size());

        Set<CollisionKey> collisions = new HashSet<>();
        System.out.println(collisions.add(new CollisionKey("A")));
        System.out.println(collisions.add(new CollisionKey("B")));
        System.out.println(collisions.add(new CollisionKey("A")));
        System.out.println(collisions.size());
    }
}
```

Biên dịch và chạy:

```bash
javac HashContractDemo.java
java HashContractDemo
```

Kết quả chính xác:

```text
100
2
120
true
false
true
2
true
true
false
2
```

Giải thích:

1. `first` và `same` là **hai instance khác nhau** nhưng `equals` là `true` vì cùng `sku`; hash cũng bằng nhau. `put(same, "120")` cập nhật mục cũ và trả `"100"`. Vì thế map chỉ có hai khóa logic (`P-10` và `P-20`).
2. Một `new ProductKey("P-10")` vẫn tìm được giá trị `"120"`: việc tra cứu dựa vào **giá trị khóa**, không phụ thuộc có dùng chính instance ban đầu hay không.
3. Trong `HashSet<ProductKey>`, lần thêm `first` trả `true`; thêm `same` trả `false` vì đã có phần tử bằng nó; thêm `other` trả `true`.
4. `CollisionKey.hashCode()` luôn trả `7`, nên `A` và `B` cùng mã băm nhưng khác nhau theo `equals`. `HashSet` vẫn lưu cả hai. Thêm thêm một `A` thì được coi là trùng và trả `false`.

Việc cố ý dùng hash cố định **đúng về tính tương thích với equality** (hai đối tượng bằng nhau vẫn cùng hash), nhưng cho phân bố rất xấu khi dữ liệu lớn. Đây là cách minh họa va chạm, không phải chiến lược băm được khuyến nghị.

## 6. Lỗi nguy hiểm: equals đúng nhưng hashCode không tương ứng

Ví dụ dưới đây có ý định coi hai khóa bằng nhau khi `code` giống nhau, nhưng tính hash theo `bucketId` — một thành phần **không tham gia equality**. Đây là lỗi logic.

Tạo tệp `BrokenHashDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class BrokenHashDemo {
    static final class BrokenKey {
        private final String code;
        private final int bucketId;

        BrokenKey(String code, int bucketId) {
            this.code = code;
            this.bucketId = bucketId;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof BrokenKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return bucketId; // Sai: hai khóa bằng nhau có thể khác hash.
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey("A", 1);
        BrokenKey b = new BrokenKey("A", 2);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<BrokenKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        System.out.println(set.size());
    }
}
```

Chạy với JDK 17:

```bash
javac BrokenHashDemo.java
java BrokenHashDemo
```

Kết quả trên triển khai `HashSet`/ `HashMap` của JDK 17:

```text
true
false
2
```

Theo `equals`, `a` và `b` là một giá trị logic; nhưng chúng có hash khác nhau, được tìm trong các nhóm khác nhau, nên tập hợp có thể giữ **hai phần tử vốn được xem là bằng nhau**. Kết quả không còn phù hợp kỳ vọng nghiệp vụ vì chính lớp khóa vi phạm hợp đồng. Không được dựa vào bất kỳ hành vi cụ thể nào của collection khi đối tượng vi phạm hợp đồng này.

Sửa bằng cách tính `hashCode()` theo cùng trường được `equals` sử dụng, chẳng hạn `return code.hashCode();` (và bảo đảm `code` khác `null` hoặc dùng quy tắc null nhất quán). Ngược lại, nếu `bucketId` thực sự tham gia định nghĩa hai khóa bằng nhau, phải đưa nó vào cả `equals` và `hashCode`.

**Một lỗi tương tự:** chỉ khai báo `equals(MyType)` là **overload**, không ghi đè `Object.equals(Object)`. HashMap và HashSet dựa vào `equals(Object)`, vì vậy hãy khai báo đúng chữ ký `public boolean equals(Object obj)` với `@Override`.

## 7. Lỗi khác: thay đổi khóa sau khi chèn vào HashMap

Giả sử một khóa có trường `id` có thể thay đổi và cả `equals`/`hashCode` đều dựa vào `id`. Ta thêm khóa với `id=10`; sau đó đổi nó thành `id=20`.

Dù `hashCode()` tính đúng theo giá trị `id` **ở mỗi thời điểm**, khóa có thể đã nằm ở nhóm băm được chọn theo `id=10`. Khi tìm với hash theo `id=20`, map có thể tra sang nhóm khác và không tìm được mục cũ, kể cả khi vẫn giữ tham chiếu tới object khóa.

**Cách an toàn:** thiết kế các trường dùng trong `equals`/`hashCode` của khóa là bất biến (`final` và trạng thái được tham chiếu cũng ổn định). Nếu buộc phải đổi giá trị khóa, hãy xóa mục khỏi map/set **trước khi thay đổi**, cập nhật đối tượng, rồi thêm lại — hoặc tạo một khóa bất biến mới. Nếu lỡ thay đổi trước, thao tác `remove` bằng chính khóa đã đổi có thể không tìm thấy mục cũ.

`String`, `Integer` hoặc record chứa các thành phần bất biến là những lựa chọn phù hợp khi ngữ nghĩa khóa tương ứng. Record tự sinh `equals(Object)`/`hashCode()` theo các thành phần của nó, nhưng record **không tự làm cho các đối tượng mutable được chứa bên trong trở nên bất biến**.

## 8. Hiệu năng và các giới hạn cần hiểu đúng

- Trung bình, khi băm phân bố tốt và không có vấn đề đặc biệt, các thao tác phổ biến của `HashMap`/`HashSet` có thể thực hiện với chi phí kỳ vọng gần **O(1)**. Đây không phải bảo đảm mọi thao tác đều mất thời gian cố định.
- Mã băm phân bố kém tạo nhiều va chạm, khiến số khóa ứng viên phải kiểm tra tăng. Hai đối tượng khác nhau có cùng `hashCode` **không phải lỗi correctness**, nhưng quá nhiều collision ảnh hưởng hiệu năng.
- `hashCode()` không cần duy nhất, không nhất thiết là địa chỉ bộ nhớ và không phải mã định danh ổn định qua những lần khởi động JVM khác nhau.
- `HashMap`/`HashSet` không duy trì thứ tự chèn như một cam kết công khai. Nếu cần thứ tự chèn, cân nhắc `LinkedHashMap`/`LinkedHashSet`; nếu cần thứ tự sắp xếp, xem `TreeMap`/`TreeSet` và quy tắc so sánh của chúng.
- `HashMap`/`HashSet` không tự an toàn cho việc thay đổi đồng thời từ nhiều luồng nếu không có cơ chế đồng bộ phù hợp; điều này độc lập với chất lượng `equals/hashCode`.

Cần phân biệt **hợp đồng API** (hai đối tượng bằng nhau phải cùng hash, tập hợp không có phần tử trùng logic) với **chi tiết cấu trúc bảng băm** (dung lượng bucket, cách trộn bit, ngưỡng mở rộng, cây hóa). Mã ứng dụng nên dựa vào hợp đồng, không dựa vào chi tiết triển khai.

## 9. Checklist thiết kế khóa và kiểm thử

1. **Xác định định nghĩa bằng nhau** theo nghiệp vụ: khóa sản phẩm theo `sku`, tài khoản theo mã ổn định, hay đối tượng theo nhiều thuộc tính?
2. **Ghi đè đúng cả hai phương thức:** `equals(Object)` và `hashCode()`; nên dùng `@Override` để trình biên dịch phát hiện sai chữ ký.
3. **Dùng cùng tập trường** trong hai quy tắc. Nếu hai đối tượng bằng nhau thì chắc chắn tạo cùng mã băm; chấp nhận mã băm trùng với đối tượng khác.
4. **Giữ trạng thái khóa ổn định** khi đối tượng đang nằm trong map hoặc set; chú ý cả object lồng nhau có thể thay đổi.
5. **Kiểm thử ba loại cặp:** cùng một object, hai object khác nhau nhưng bằng nhau, và hai object khác nhau cố tình có cùng hash nhưng không bằng nhau.
6. **Kiểm thử qua collection:** `map.put(k1,v1)` rồi `map.put(k2,v2)` với `k1.equals(k2)` phải cập nhật cùng khóa; `set.add(k2)` sau `set.add(k1)` phải trả `false`.
7. **Đảm bảo equality đối xứng và bắc cầu**, đặc biệt nếu khóa có quan hệ kế thừa. Một lớp con dùng thêm trường để so sánh có thể làm hỏng hợp đồng với lớp cha.
8. **Không nhầm null với thiếu khóa:** khi cần phân biệt giá trị `null`, dùng `containsKey` thay vì chỉ dựa vào `get`.

**Tự kiểm tra:**

- Hai khóa có cùng hash nhưng `equals` là `false`: `HashMap` có thể giữ cả hai không? **Có.**
- Hai khóa `equals` là `true` nhưng khác hash: lớp khóa hợp lệ không? **Không.**
- Thêm một khóa bằng khóa cũ vào `HashMap`: số khóa logic tăng không? **Không; `put` cập nhật giá trị của khóa tương ứng.**
- Vì sao `HashSet.add(x)` biết cần trả `false` với phần tử trùng? **Vì nó dùng cùng cơ chế nhận diện khóa qua mã băm và equality.**

**Ghi nhớ:** `hashCode()` giúp tìm **nơi có thể chứa đối tượng**; `equals(Object)` quyết định **đó có phải đối tượng bằng nhau về giá trị hay không**. HashMap và HashSet chỉ vận hành đúng theo kỳ vọng khi hai phương thức cùng tuân thủ một hợp đồng equality nhất quán.