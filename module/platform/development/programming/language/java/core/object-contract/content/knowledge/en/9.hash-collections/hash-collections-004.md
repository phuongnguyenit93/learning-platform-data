# Dùng đối tượng mới nhưng bằng nhau để tìm khóa trong HashMap

## 1. Một khóa mới có thể tìm được mapping đã lưu

Khi lưu dữ liệu trong `HashMap<K, V>`, không nhất thiết phải giữ lại chính instance khóa đã truyền vào `put()`. Ta có thể tạo một đối tượng mới có cùng **giá trị khóa theo nghiệp vụ** để gọi `get()` hoặc `containsKey()`.

Ví dụ: tài khoản được định danh bằng cặp `(tenantId, userId)`. Một bản đồ lưu tên người dùng theo khóa `AccountKey("team-a", "u-42")`. Sau đó, một yêu cầu khác tạo **instance mới** với cùng hai trường và lấy lại giá trị cũ. Điều này hoạt động nếu `AccountKey` xác định chính xác hai instance thế nào được coi là bằng nhau, đồng thời cung cấp `hashCode()` nhất quán với `equals()`.

Phân biệt ngay từ đầu:

- `first == second` kiểm tra hai biến có trỏ tới **cùng một instance** hay không. Hai lần gọi `new` riêng biệt thông thường cho kết quả `false`.
- `first.equals(second)` kiểm tra bình đẳng logic do kiểu đối tượng định nghĩa. Hai instance khác nhau có thể trả về `true`.
- `first.hashCode() == second.hashCode()` là điều **bắt buộc** nếu `first.equals(second)` đúng, nhưng bản thân hash bằng nhau không chứng minh hai đối tượng bằng nhau.

`Object.equals()` mặc định so đồng nhất tham chiếu. Vì vậy, tự tạo một lớp khóa rồi chỉ giữ các trường giống nhau **chưa đủ** để tìm lại bằng instance mới. `String` và các kiểu giá trị khác đã định nghĩa hợp đồng phù hợp; một lớp khóa tự viết phải chủ động thiết kế.

## 2. Cách HashMap dùng hash và equality

Có thể hình dung thao tác thêm và lấy phần tử qua luồng khái niệm sau:

```text
put(keyA, value)
    │
    ├─ tính keyA.hashCode()
    ├─ xác định bucket phù hợp
    ├─ so với các khóa ứng viên bằng equals() khi cần
    └─ thêm mapping hoặc cập nhật mapping tương đương

get(keyB)    // keyB là một object mới
    │
    ├─ tính keyB.hashCode()
    ├─ tìm vùng lưu tương ứng
    ├─ kiểm tra khóa tương đương bằng equals()
    └─ trả giá trị hoặc null nếu không có mapping
```

Với Java `HashMap`, một khóa đang tra cứu có thể tìm thấy mapping lưu bằng khóa khác nếu chúng tương đương theo `equals()` và có giá trị hash tương thích. Chi tiết nội bộ như trộn bit của hash, chọn bucket, cấu trúc danh sách/cây và resize phụ thuộc triển khai JDK; không nên xây logic ứng dụng dựa vào chỉ số bucket hay thứ tự duyệt `HashMap`.

**Hai quy tắc phải đi cùng nhau:**

1. **Bằng nhau kéo theo cùng hash.** Nếu `a.equals(b)` trả về `true`, `a.hashCode()` và `b.hashCode()` phải giống nhau. Nếu vi phạm, `HashMap` có thể tìm sai vùng và bỏ lỡ khóa.
2. **Cùng hash chưa chắc bằng nhau.** Hash collision xảy ra hợp lệ: các đối tượng không bằng nhau có thể trùng hash. `HashMap` cần dùng kiểm tra equality để phân biệt chúng.

Khi gọi `put()` bằng một khóa mới **tương đương** với khóa đã có, bản đồ cập nhật giá trị hiện hữu thay vì tăng số lượng entry. Không cần hai tham chiếu bằng `==`.

## 3. Thiết kế khóa: chọn đúng các trường equality

Không có quy tắc “so mọi trường” áp dụng cho mọi class. Với khóa tài khoản ở nhiều tenant, mã `userId` có thể lặp giữa các tenant, nên `(tenantId, userId)` tạo thành khóa kết hợp. Bỏ `tenantId` sẽ làm hai tài khoản thuộc hai tenant khác nhau bị coi là một. Ngược lại, nếu thêm `displayName` vào equality, việc đổi tên có thể khiến cùng tài khoản trở thành một khóa khác.

Một tập trường khóa tốt nên có:

- **Ý nghĩa nghiệp vụ rõ ràng:** hai đối tượng có cùng những trường đó thực sự đại diện cùng khóa.
- **Phạm vi duy nhất đúng:** nếu ID chỉ duy nhất trong tenant, phải xét tenant; nếu ID đã duy nhất toàn hệ thống, có thể không cần thêm namespace.
- **Độ ổn định:** những dữ liệu tham gia `equals()/hashCode()` không nên thay đổi khi object còn là key của `HashMap`.
- **So sánh nhất quán:** kiểu thành phần có chính sách equality phù hợp; ví dụ `String.equals()` phân biệt chữ hoa thường và `BigDecimal.equals()` xét scale.

Hợp đồng `equals()` gồm: phản xạ (`x.equals(x)`), đối xứng (`x.equals(y)` tương đương `y.equals(x)`), bắc cầu, nhất quán khi dữ liệu liên quan không đổi, và `x.equals(null) == false`. Hai khóa được coi là bằng nhau phải có cùng `hashCode()`. Đừng dùng timestamp thay đổi liên tục, giá trị ngẫu nhiên hoặc địa chỉ tham chiếu trong hash nếu equality dựa trên các trường giá trị.

## 4. Chương trình Java 17+ hoàn chỉnh

Đặt mã sau trong tệp `HashMapEqualKeysDemo.java`. Ta tự viết `equals()` và `hashCode()` để nhìn rõ giao ước:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashMapEqualKeysDemo {

    static final class AccountKey {
        private final String tenantId;
        private final String userId;

        AccountKey(String tenantId, String userId) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.userId = Objects.requireNonNull(userId);
            if (tenantId.isBlank() || userId.isBlank()) {
                throw new IllegalArgumentException("IDs must not be blank");
            }
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof AccountKey that)) return false;
            return tenantId.equals(that.tenantId)
                    && userId.equals(that.userId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    public static void main(String[] args) {
        Map<AccountKey, String> accounts = new HashMap<>();

        AccountKey inserted = new AccountKey("team-a", "u-42");
        accounts.put(inserted, "Trang hồ sơ");

        AccountKey lookup = new AccountKey("team-a", "u-42");
        AccountKey otherTenant = new AccountKey("team-b", "u-42");

        System.out.println(inserted == lookup);
        System.out.println(inserted.equals(lookup));
        System.out.println(inserted.hashCode() == lookup.hashCode());
        System.out.println(accounts.containsKey(lookup));
        System.out.println(accounts.get(lookup));
        System.out.println(accounts.containsKey(otherTenant));
        System.out.println(accounts.get(otherTenant));

        accounts.put(lookup, "Đã cập nhật");
        System.out.println(accounts.size());
        System.out.println(accounts.get(inserted));

        AccountKey nullValueKey = new AccountKey("team-b", "u-01");
        accounts.put(nullValueKey, null);
        System.out.println(accounts.containsKey(
                new AccountKey("team-b", "u-01")));
        System.out.println(accounts.get(nullValueKey));
        System.out.println(accounts.getOrDefault(
                new AccountKey("team-c", "u-99"), "Không có"));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac HashMapEqualKeysDemo.java
java HashMapEqualKeysDemo
```

Đầu ra:

```text
false
true
true
true
Trang hồ sơ
false
null
1
Đã cập nhật
true
null
Không có
```

Từng nhóm kết quả mang ý nghĩa:

1. `inserted == lookup` là `false` vì hai lần khởi tạo tạo hai instance. Nhưng `inserted.equals(lookup)` là `true` vì hai trường khóa giống nhau; hash của chúng cũng bằng nhau.
2. `accounts.containsKey(lookup)` là `true` và `accounts.get(lookup)` trả về `Trang hồ sơ`, mặc dù chính instance `lookup` chưa từng được truyền vào `put()`.
3. `otherTenant` mang cùng `userId` nhưng tenant khác nên không phải khóa tương đương. `containsKey()` cho `false`; `get()` cho `null`.
4. `accounts.put(lookup, "Đã cập nhật")` cập nhật mapping cũ. Vì hai khóa bằng nhau, `size()` vẫn là `1` và `get(inserted)` trả về `Đã cập nhật`.
5. Một mapping thực sự có thể lưu giá trị `null`. `containsKey(new AccountKey("team-b", "u-01"))` cho `true`, còn `get(nullValueKey)` trả về `null`. Điều này không đồng nghĩa khóa vắng mặt.
6. `getOrDefault()` với khóa `("team-c", "u-99")` chưa lưu trả về `Không có`. Nếu mapping có tồn tại và lưu `null`, `getOrDefault()` trả về `null`, không dùng default.

Trong thiết kế này, `AccountKey` là `final`, hai trường khóa là `private final String`, constructor từ chối `null` hoặc chuỗi trắng, và `String` bất biến. Vì vậy sau khi tạo khóa, không có cách hợp lệ để đổi giá trị hai thành phần equality; dùng làm key của `HashMap` ổn định.

## 5. Điểm khác biệt giữa get, containsKey và getOrDefault

| Lệnh | Ý nghĩa |
| --- | --- |
| `map.get(key)` | Lấy giá trị của khóa tương đương, hoặc `null` nếu không có mapping; cũng `null` nếu giá trị lưu là `null`. |
| `map.containsKey(key)` | Xác nhận có mapping ứng với khóa tương đương, kể cả khi giá trị map đang lưu là `null`. |
| `map.getOrDefault(key, fallback)` | Trả fallback nếu **không có mapping**. Mapping tới `null` vẫn trả `null`. |
| `map.put(key, value)` | Thêm mapping mới hoặc thay thế giá trị của mapping có khóa tương đương; trả giá trị cũ hoặc `null`. |
| `map.remove(key)` | Xóa mapping được nhận diện qua khóa tương đương; giá trị trả về có thể là `null`. |

`HashMap` hỗ trợ một khóa `null` và các giá trị `null`. Trong trường hợp cần phân biệt mapping có tồn tại hay không, không được chỉ dựa vào `get(key) != null`. Ngữ nghĩa này khác `ConcurrentHashMap`, vốn không cho khóa hoặc giá trị `null`.

Ngoài `HashMap`, các triển khai `Map` có thể chọn tiêu chí tương đương khóa khác: `IdentityHashMap` cố ý so theo đồng nhất tham chiếu, `TreeMap` dựa vào thứ tự so sánh của `Comparable`/`Comparator`. Vì vậy kỹ thuật “tạo khóa mới nhưng bằng nhau” trong bài này gắn với **HashMap và hợp đồng equals/hashCode**, không tự động khái quát cho mọi map.

## 6. Sai lầm: chỉ ghi đè một trong hai phương thức

### Chỉ ghi đè equals()

Nếu hai object có cùng `tenantId` và `userId` nhưng `hashCode()` vẫn là cách tính mặc định theo identity, chúng có thể có hash khác nhau. Tra cứu bằng object mới không đáng tin cậy vì hash có thể dẫn đến vùng khác. Ví dụ sai về mặt hợp đồng:

```java
// Chỉ là ví dụ phương thức bên trong một class có hai trường:
@Override
public boolean equals(Object other) {
    return other instanceof AccountKey that
            && tenantId.equals(that.tenantId)
            && userId.equals(that.userId);
}
// Quên ghi đè hashCode(): SAI, vì hai instance equals có thể khác hash.
```

Chú thích trên giả định lớp đang dùng `Object.hashCode()`. Nếu `AccountKey` đã có cách tính hash tương thích thì phương thức equals không tạo vấn đề này; lỗi nằm ở việc thiếu hợp đồng đồng bộ.

### Chỉ ghi đè hashCode()

Nếu `hashCode()` trả giá trị giống nhau cho mọi instance nhưng `equals()` vẫn là `Object.equals()` mặc định, hai object khác nhau vẫn không được coi là một khóa. Hash chỉ khoanh vùng ứng viên, còn `equals()` quyết định chúng có tương đương hay không.

### Hash collision không phải lỗi equality

Không được dùng `a.hashCode() == b.hashCode()` để khẳng định `a.equals(b)`. Một hash 32-bit không thể phân biệt mọi đối tượng có thể tạo; collision là điều bình thường. Dù hai khóa có cùng hash, `HashMap` vẫn có thể lưu cả hai nếu chúng không bằng nhau. Cũng không nên cố tạo hash “duy nhất tuyệt đối” vì hợp đồng Java không hứa điều đó.

## 7. Sai lầm: thay đổi trạng thái quyết định khóa sau khi put

Đây là một bẫy thực tế. Giả sử `MutableKey.id` tham gia tính cả `equals()` lẫn `hashCode()`:

```java
// Minh họa logic sai, không phải chương trình chạy độc lập.
MutableKey key = new MutableKey("U-100");
map.put(key, "An");

key.setId("U-200"); // Đổi giá trị đang tham gia hash/equality.
System.out.println(map.get(key)); // Có thể null dù map vẫn chứa entry.
```

Entry được bố trí theo hash tại thời điểm `put()`. Nếu trường khóa thay đổi, `get(key)` tính hash mới và có thể tìm nhầm vùng. Ngay cả khi truyền lại **chính instance** đã lưu, tra cứu vẫn có thể thất bại. `HashMap` không tự di chuyển entry khi các trường của object thay đổi.

Giải pháp:

- Ưu tiên key bất biến hoặc snapshot khóa được đóng băng tại thời điểm tạo.
- Nếu cần đổi danh tính khóa, xóa mapping cũ trước khi thay và thêm mapping dưới khóa mới, hoặc tạo key mới thay vì mutate key cũ.
- Với field tham chiếu, `final` chỉ ngăn gán lại biến; `final List<String>` hoặc `final StringBuilder` vẫn có thể chứa nội dung mutable ảnh hưởng equality/hash.
- Nếu ID database chỉ được cấp sau khi persist, đừng vô tình dùng object với ID thay đổi làm key. Thiết kế chính sách equality cho toàn bộ vòng đời entity trước khi lưu nó trong collection băm.

Các trường bổ trợ như `displayName`, `lastLogin` có thể mutable nếu hoàn toàn không được dùng trong `equals()/hashCode()`. Điều phải ổn định là **phần tạo nên khóa**, không bắt buộc mọi trạng thái của entity.

## 8. Viết key gọn hơn bằng record (Java 17)

Nếu khóa có đúng hai thành phần giá trị, `record` hỗ trợ tự sinh `equals()` và `hashCode()`:

```java
record AccountKey(String tenantId, String userId) {
    AccountKey {
        java.util.Objects.requireNonNull(tenantId);
        java.util.Objects.requireNonNull(userId);
        if (tenantId.isBlank() || userId.isBlank()) {
            throw new IllegalArgumentException("IDs must not be blank");
        }
    }
}
```

*Đây là cách khai báo thay thế, không ghép thêm vào chương trình ở mục 4 vì sẽ trùng tên `AccountKey`.* Java tạo equality dựa trên **tất cả** record component. Do đó hai `new AccountKey("team-a", "u-42")` riêng biệt có equality/hash tương thích để dùng với `HashMap`.

Record **không tự sao chép sâu** các component là array, list hay đối tượng mutable. Đặc biệt, record chứa array sử dụng semantics equality mặc định của array cho component đó; nếu muốn so nội dung mảng và hash theo nội dung, phải thiết kế riêng. Record có component mang trạng thái không nên ảnh hưởng identity sẽ đưa component ấy vào equality mặc định, nên chọn component phù hợp với domain.

## 9. Dữ liệu thành phần và chuẩn hóa khóa

Một số tình huống khiến hai đối tượng nhìn “giống nhau” với người dùng nhưng `equals()` lại khác nhau:

| Thành phần | Cần xác định chính sách |
| --- | --- |
| `String` | `"U-42"` và `"u-42"` là hai chuỗi khác theo `equals()`; chỉ chuẩn hóa hoa/thường nếu domain cho phép. |
| `BigDecimal` | `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` vì khác scale, dù `compareTo() == 0`. Nếu cần cùng giá trị số, chuẩn hóa nhất quán trước khi tạo khóa. |
| Array | Equality mặc định trên tham chiếu không so từng phần tử. Nếu lấy nội dung làm khóa, cần `Arrays.equals()/hashCode()` hoặc `deepEquals()/deepHashCode()` tương thích với loại dữ liệu. |
| `List` | `List.equals()` xét các phần tử **theo thứ tự**; phải kiểm soát khả năng mutate trong thời gian khóa nằm trong map. |
| `Set` | `Set.equals()` xét tập phần tử, không dựa vào thứ tự; phần tử thay đổi equality/hash cũng có thể gây hỏng logic. |

Chính sách chuẩn hóa dữ liệu (ví dụ mã có cần loại khoảng trắng đầu/cuối không) phải được quyết định **trước** khi thiết lập khóa và áp dụng đồng bộ cho `equals()` lẫn `hashCode()`. Không nên âm thầm `toLowerCase()` mọi mã, tên người dùng hoặc email khi chưa biết domain có phân biệt chữ hoa thường hay không.

`toString()` không phải cách chuẩn để tạo khóa. Hai chuỗi hiển thị giống nhau không đảm bảo hai object bằng nhau và `toString()` có thể thay đổi chỉ để phục vụ debug.

## 10. Bảng kiểm và tự kiểm tra

Trước khi dùng lớp tùy biến làm khóa `HashMap`, có thể kiểm tra:

| Tình huống thử | Kết quả cần có |
| --- | --- |
| Tạo hai object độc lập có cùng giá trị khóa | `a != b` theo tham chiếu; `a.equals(b)` là `true` và hash bằng nhau. |
| `put(a, v)` rồi `get(b)` | Nhận đúng `v` và `containsKey(b)` là `true`. |
| `put(b, newValue)` khi `a.equals(b)` | Chỉ cập nhật mapping, `size()` không tăng. |
| Khóa khác tenant dù trùng userId | Không lấy nhầm dữ liệu giữa các tenant. |
| Hai khóa khác nhau cùng hash | Vẫn được phân biệt qua `equals()`. |
| Thay trường không thuộc equality | Việc tra cứu không thay đổi. |
| Thay trường thuộc equality khi key đang trong map | Đó là thiết kế nguy hiểm, cần tránh. |
| Có mapping lưu giá trị `null` | `containsKey()` phân biệt được với trường hợp không có mapping. |

**Câu 1:** Vì sao `new String("java")` có thể tìm mapping lưu bởi một instance `String` khác có nội dung `"java"`?  
**Đáp án:** Vì `String.equals()` so nội dung và `String.hashCode()` nhất quán với equality.

**Câu 2:** Hai object cùng `hashCode()` có chắc trả cùng giá trị khi `map.get()` không?  
**Đáp án:** Không; hai khóa có thể collision mà `equals()` vẫn `false`.

**Câu 3:** Khi `put()` một instance khóa mới bằng khóa đã tồn tại, số entry tăng không?  
**Đáp án:** Không; giá trị gắn với khóa tương đương được thay thế.

**Câu 4:** `map.get(key) == null` có chắc không có mapping không?  
**Đáp án:** Không với `HashMap`: mapping có thể tồn tại và chứa giá trị `null`. Dùng `containsKey()`.

**Câu 5:** Vì sao không nên sửa `id` của object đang nằm trong `HashMap` nếu `id` tham gia equality/hash?  
**Đáp án:** Vì hash dùng khi tra cứu có thể khác hash lúc lưu, làm map không tìm được entry đang tồn tại.

**Câu 6:** Thay `tenantId` có làm cùng `userId` trở thành cùng khóa không?  
**Đáp án:** Không trong mô hình của bài; tenant là một phần của khóa để ngăn tra cứu nhầm giữa các không gian định danh.

Kết luận dùng được ngay: **Một instance khóa mới có thể tìm lại mapping trong `HashMap` nếu nó `equals()` với khóa đã lưu, có `hashCode()` tương thích, và dữ liệu tạo nên khóa được giữ ổn định trong quá trình sử dụng.**