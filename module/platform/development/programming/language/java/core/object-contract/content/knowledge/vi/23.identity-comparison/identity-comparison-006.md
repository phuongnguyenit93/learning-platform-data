# IdentityHashMap: Vì sao cố ý khác hợp đồng Map thông thường ở quan hệ so sánh

Trong Java, `IdentityHashMap<K, V>` triển khai giao diện `Map<K, V>` nhưng **cố ý sử dụng danh tính đối tượng (reference identity, toán tử `==`)** để phân biệt các khóa và so sánh các giá trị, thay cho quan hệ bằng nhau về mặt logic (`equals()`). Đây là ngoại lệ được mô tả công khai trong API, phù hợp với một số bài toán đặc biệt; không phải lỗi của `IdentityHashMap`.

Ý chính cần ghi nhớ: **hai đối tượng có `equals() == true` vẫn có thể là hai khóa khác nhau trong `IdentityHashMap`**. Khi đem map này so sánh với một map thông thường như `HashMap`, thậm chí `Map.equals()` có thể không còn đối xứng.

## 1. Phân biệt bằng nhau về giá trị và bằng nhau về danh tính

Giả sử:

```java
String a = new String("java");
String b = new String("java");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
```

- `a.equals(b)` trả về `true` vì hai chuỗi mang cùng nội dung.
- `a == b` trả về `false` vì `new` tạo ra hai đối tượng riêng biệt.
- Việc `equals()` trả về `true` không có nghĩa là hai biến trỏ tới cùng đối tượng. Cùng tham chiếu thì `==` luôn là `true`, bất kể lớp ghi đè `equals()` ra sao.

Với khóa trong `HashMap`, Java dùng `hashCode()` và `equals()` để tìm khóa tương đương logic. `IdentityHashMap` dùng `==` kết hợp mã băm danh tính (`System.identityHashCode()`). Mã băm danh tính chỉ là công cụ tra cứu: **hai đối tượng khác nhau vẫn có thể trùng identity hash code**, và map phải phân biệt chúng bằng `==`. Mã băm này không phải địa chỉ bộ nhớ hoặc ID duy nhất tuyệt đối.

| Tình huống | `HashMap` thông thường | `IdentityHashMap` |
| --- | --- | --- |
| Hai khóa cùng một tham chiếu | Cùng một khóa | Cùng một khóa |
| Hai khóa khác tham chiếu nhưng `equals()` là `true` | Cùng khóa nếu tuân thủ hợp đồng `hashCode/equals` | Hai khóa riêng |
| `get(key)` / `containsKey(key)` | Dựa trên tương đương logic của key | Dựa trên đúng tham chiếu đã lưu |
| `containsValue(value)` | So sánh theo `equals()` | So sánh bằng `==` |
| Hai entry có key/value bằng nhau về nội dung nhưng khác tham chiếu | Có thể là cùng mapping | Không cùng mapping theo danh tính |

**Lưu ý:** `IdentityHashMap` không băm theo value; việc kiểm tra danh tính value thể hiện ở `containsValue()` và quan hệ so sánh các entry/map. `get()` vẫn chọn mapping dựa trên **danh tính key**.

## 2. “Vi phạm hợp đồng Map” chính xác là gì?

Hợp đồng `Map` thông thường mô tả tính tương đương của khóa dựa trên `equals()` và quan hệ bằng nhau giữa hai map dựa trên các mapping tương đương. `IdentityHashMap` triển khai thao tác `Map` nhưng chủ ý thay tiêu chí tương đương khóa/giá trị bằng **cùng tham chiếu đối tượng**.

Các hệ quả quan trọng:

1. **Tính duy nhất của khóa thay đổi.** `put(k1, v1)` rồi `put(k2, v2)` không thay mapping cũ chỉ vì `k1.equals(k2)` là `true`; hai key phải là chính cùng đối tượng.
2. **`IdentityHashMap.equals(other)` xét các mapping theo danh tính.** Đặc tả diễn đạt bằng `this.entrySet().equals(other.entrySet())`, trong đó các entry của `IdentityHashMap` sử dụng quan hệ tham chiếu.
3. **So sánh với map thông thường có thể bất đối xứng:** tồn tại trường hợp `normalMap.equals(identityMap) == true` nhưng `identityMap.equals(normalMap) == false`. Javadoc còn cảnh báo tính bắc cầu (`transitivity`) của `Object.equals` có thể bị vi phạm khi trộn các kiểu map.
4. **`hashCode()` của map dựa trên entry với ngữ nghĩa identity.** Quy tắc “bằng nhau thì hash code bằng nhau” được đảm bảo khi so sánh giữa các `IdentityHashMap`; khi so sánh chéo với map thường, không thể mặc định quy tắc đó còn đúng.

Điểm mấu chốt: **giữa các instance `IdentityHashMap`, hợp đồng `equals/hashCode` vẫn được bảo đảm**; rủi ro xuất hiện khi code áp dụng giả định của `HashMap`/`Map` thông thường hoặc so sánh chéo các kiểu map.

## 3. Ví dụ Java 17+: Chứng minh khác biệt và tính bất đối xứng

Lưu thành `IdentityMapContractDemo.java`:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityMapContractDemo {
    public static void main(String[] args) {
        String k1 = new String("code");
        String k2 = new String("code");
        String v1 = new String("same");
        String v2 = new String("same");

        Map<String, String> normal = new HashMap<>();
        Map<String, String> byIdentity = new IdentityHashMap<>();

        normal.put(k1, v1);
        normal.put(k2, v2);
        byIdentity.put(k1, v1);
        byIdentity.put(k2, v2);

        System.out.println("k1.equals(k2) = " + k1.equals(k2));
        System.out.println("k1 == k2 = " + (k1 == k2));
        System.out.println("HashMap.size = " + normal.size());
        System.out.println("IdentityHashMap.size = " + byIdentity.size());
        System.out.println("IdentityHashMap.containsKey(new key) = "
                + byIdentity.containsKey(new String("code")));
        System.out.println("IdentityHashMap.containsValue(new value) = "
                + byIdentity.containsValue(new String("same")));
        System.out.println("IdentityHashMap.containsValue(v1) = "
                + byIdentity.containsValue(v1));

        // Cùng object khóa, hai object giá trị khác nhau nhưng equals() == true.
        Object sharedKey = new Object();
        Map<Object, String> regularOne = new HashMap<>();
        Map<Object, String> identityOne = new IdentityHashMap<>();
        regularOne.put(sharedKey, new String("same"));
        identityOne.put(sharedKey, new String("same"));

        System.out.println("HashMap.equals(IdentityHashMap) = "
                + regularOne.equals(identityOne));
        System.out.println("IdentityHashMap.equals(HashMap) = "
                + identityOne.equals(regularOne));
    }
}
```

Biên dịch và chạy:

```bash
javac IdentityMapContractDemo.java
java IdentityMapContractDemo
```

Kết quả chuẩn:

```text
k1.equals(k2) = true
k1 == k2 = false
HashMap.size = 1
IdentityHashMap.size = 2
IdentityHashMap.containsKey(new key) = false
IdentityHashMap.containsValue(new value) = false
IdentityHashMap.containsValue(v1) = true
HashMap.equals(IdentityHashMap) = true
IdentityHashMap.equals(HashMap) = false
```

Giải thích:

- Hai chuỗi khóa cùng nội dung nhưng khác đối tượng. `HashMap` giữ một mapping vì khóa thứ hai tương đương khóa đầu; `IdentityHashMap` giữ cả hai vì `k1 != k2`.
- Tạo chuỗi mới `new String("code")` để tra cứu không tìm thấy key của `IdentityHashMap` dù nội dung bằng nhau. Tương tự, `containsValue(new String("same"))` là `false`; dùng đúng object `v1` thì là `true`.
- Ở phần cuối, hai map chứa **chính cùng object `sharedKey`**, nhưng value là hai `String` khác tham chiếu, cùng nội dung. `HashMap.equals` chấp nhận value tương đương theo `equals()` nên trả `true`. `IdentityHashMap.equals` đòi đúng value reference nên trả `false`. Đây là phản ví dụ cụ thể cho tính đối xứng, **không phải** hiện tượng ngẫu nhiên do thứ tự duyệt hay va chạm hash.

**Không dùng `System.identityHashCode(...)` để dự đoán output:** con số hash có thể khác giữa các lần chạy, không biểu thị thứ tự map và không chứng minh hai tham chiếu là cùng object.

## 4. Ảnh hưởng đến API, collection views và chuyển đổi map

### Các thao tác tra cứu

- `put(k, v)` thay thế value chỉ khi đã tồn tại mapping với **chính object `k`**; object khóa mới có cùng nội dung được thêm thành mapping mới.
- `get(k)`, `containsKey(k)`, `remove(k)` tra cứu bằng identity của key. `get(k) == null` có thể nghĩa là không có key **hoặc** key đang ánh xạ tới `null`; dùng `containsKey(k)` để phân biệt.
- `containsValue(v)` dùng identity của value, không dùng `v.equals(...)`.
- `IdentityHashMap` cho phép một key `null` và các value `null`.

### `keySet()`, `entrySet()`, `values()`

- `keySet()` là một **set dựa trên danh tính**: hai key khác object nhưng `equals() == true` vẫn cùng xuất hiện. Không nên mặc định rằng view này so sánh với mọi `HashSet` theo quy ước `Set.equals` thông thường.
- `entrySet()` thể hiện mapping theo identity của **cả key lẫn value**. Đây là nền tảng của `IdentityHashMap.equals/hashCode`.
- `values()` là collection view, được liên kết với map gốc, không phải bản sao. Việc kiểm tra value hiện diện tuân theo identity semantics.
- `IdentityHashMap` không bảo đảm thứ tự duyệt; không viết test phụ thuộc thứ tự `keySet()`/`entrySet()`/`values()`.

### Chuyển qua `HashMap` có thể làm mất mapping

Nếu `identityMap` chứa hai khóa `k1` và `k2` khác object nhưng `k1.equals(k2) == true`:

```java
Map<String, String> copied = new HashMap<>(identityMap);
```

`copied` có thể gộp hai mapping thành một; value còn lại phụ thuộc thứ tự duyệt nguồn nên không được dựa vào nó. Ngược lại, tạo `IdentityHashMap` từ `HashMap` không thể khôi phục các khóa khác object đã bị gộp. Hai lớp cùng triển khai `Map<K,V>` nhưng việc đổi implementation có thể thay **ý nghĩa dữ liệu**.

### Bẫy khi dùng `Map.equals/hashCode` để tích hợp

Một API nhận `Map` bất kỳ thường giả định `equals` đối xứng, bắc cầu và tương thích `hashCode`. Với `IdentityHashMap`, các giả định ấy có thể thất bại khi trộn với map thường. Cần xem xét code so sánh map, dùng map làm key trong map khác, kiểm tra `assertEquals(expectedHashMap, actualIdentityMap)`, hoặc chuyển đổi dữ liệu qua API không nêu rõ tiêu chí equality. **Thứ tự hai đối số so sánh có thể làm thay kết quả.**

## 5. Khi nào nên dùng IdentityHashMap?

Chỉ dùng khi bài toán cần định danh **đúng từng instance**, kể cả các instance tình cờ mang dữ liệu giống nhau:

- **Sao chép/chuyển đổi đồ thị object có chia sẻ hoặc chu trình:** ánh xạ mỗi *node object gốc* sang đúng *node object mới*. Nếu hai node khác nhau nhưng `equals()` giống nhau, nhập chúng làm một sẽ phá cấu trúc đồ thị.
- **Theo dõi object đã thăm trong quá trình duyệt đồ thị:** các node đại diện hai thực thể riêng phải được xử lý riêng, dù cùng thuộc tính.
- **Ánh xạ object gốc sang proxy hoặc metadata chẩn đoán:** giữ một proxy riêng cho từng object cụ thể trong runtime.

Khi chỉ cần tập các đối tượng đã thăm, dùng `Collections.newSetFromMap(new IdentityHashMap<>())` với map ban đầu trống. Bài **Dùng danh tính khi duyệt và theo dõi đồ thị đối tượng** có ví dụ DFS và phân biệt việc gặp lại node với chu kỳ.

## 6. Những nhầm lẫn## 6. Những nhầm lẫn và giới hạn cần tránh

1. **Không nghĩ `IdentityHashMap` là `HashMap` nhanh hơn.** Hai cấu trúc có ngữ nghĩa khác nhau. Chi tiết bảng băm và tối ưu không phải lý do thay thế nếu nghiệp vụ dùng `equals()`.
2. **Không dùng cho khóa nghiệp vụ “bằng giá trị”.** Email, mã sản phẩm, ID hay chuỗi được tạo lại qua request có thể thành nhiều entry khó tra cứu dù cùng nội dung.
3. **Không hiểu `==` là `equals()`.** Với object, `==` so tham chiếu; ghi đè `equals/hashCode` không thay đổi điều này.
4. **Không dùng identity hash code làm ID toàn cục.** `System.identityHashCode(x)` có thể trùng giữa các object khác nhau và không phải định danh bền vững qua tiến trình.
5. **Không giả định thứ tự, thread safety hoặc tự giải phóng key.** `IdentityHashMap` không bảo đảm thứ tự, không đồng bộ hóa mặc định và giữ tham chiếu mạnh tới key/value. Khi nhiều luồng có sửa cấu trúc phải đồng bộ phù hợp; nếu cần weak keys, chọn cấu trúc theo yêu cầu đó.
6. **Không trông chờ iterator fail-fast làm cơ chế đồng bộ.** `ConcurrentModificationException` chỉ được phát hiện ở mức cố gắng tốt nhất, không thay cho synchronization.
7. **Không so sánh bằng `Map.equals` khi hai bên dùng tiêu chí khác nhau.** Xác định rõ cần cùng instance hay cùng dữ liệu; nếu chuyển sang cấu trúc dùng equality theo giá trị, phải đánh giá trước rủi ro gộp key.

## 7. Checklist thực hành

Trước khi chọn `IdentityHashMap`, hãy trả lời:

- Hai key khác tham chiếu nhưng `equals() == true` có **bắt buộc** phải được giữ riêng không?
- Việc so sánh value (`containsValue`, `entrySet`, `Map.equals`) có thật sự cần `==` thay cho `equals()` không?
- Code gọi có dựa vào hợp đồng `Map.equals/hashCode` khi so sánh với `HashMap`/`TreeMap` không?
- Có bước copy map, serialize, cache hoặc expose `Map` ra API khác làm mất ý nghĩa identity không?
- Test bao gồm cả **cùng tham chiếu**, **khác tham chiếu nhưng bằng giá trị**, **`null`**, và **so sánh chéo loại map** chưa?

Nếu tiêu chí là bằng nhau về logic, `HashMap` thường phù hợp. Nếu tiêu chí là **object nào trong bộ nhớ**, `IdentityHashMap` đáp ứng mục đích đó; hãy bảo vệ ranh giới ngữ nghĩa khi kết hợp với collection khác.

## Tài liệu tham khảo

- [Java SE 17 API — IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): mô tả identity semantics, ngoại lệ với hợp đồng `Map`, `equals/hashCode`, collection views và ứng dụng trên đồ thị object.
- [Java SE 17 API — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng tổng quát về key, value, `equals` và `hashCode`.
- [Java SE 17 API — System.identityHashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): mã băm theo danh tính, độc lập với override `hashCode()`.