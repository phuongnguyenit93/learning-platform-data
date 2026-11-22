# Lỗi khi chỉ ghi đè `equals()` hoặc thiết kế `hashCode()` không tương thích

## 1. Vì sao hai phương thức này phải đi cùng nhau?

Trong Java, `equals(Object)` mô tả **quan hệ bằng nhau về mặt logic** giữa hai đối tượng; `hashCode()` cung cấp số nguyên dùng để hỗ trợ tìm kiếm trong các cấu trúc dữ liệu băm như `HashMap` và `HashSet`. Cả hai đều bắt nguồn từ `java.lang.Object`, nhưng chúng đảm nhiệm hai việc khác nhau:

- `equals` quyết định hai khóa có được xem là cùng một khóa hay không.
- `hashCode` giúp cấu trúc băm chọn vùng tra cứu phù hợp trước khi so sánh các khóa. Với hai giá trị hash khác nhau, cấu trúc băm thông thường không thể coi các khóa đó là cùng khóa trong cùng lần tìm kiếm.

**Quy tắc bắt buộc:** Nếu `a.equals(b)` là `true` thì **`a.hashCode() == b.hashCode()` phải là `true`**. Đây là quan hệ một chiều:

```text
a.equals(b) == true  ==>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  =/=>  a.equals(b) == true
```

Nghĩa là các đối tượng không bằng nhau **được phép** trùng mã băm (*hash collision*). Hai đối tượng có hash giống nhau không đủ để kết luận chúng bằng nhau; sau bước xác định hash, cấu trúc dữ liệu còn phải so sánh bằng `equals`.

Ngoài quy tắc trên, trong một lần chạy chương trình, khi không thay đổi thông tin dùng trong `equals`, các lần gọi `hashCode` trên cùng đối tượng phải cho cùng kết quả. Kết quả hash **không bắt buộc giống giữa các lần chạy JVM khác nhau**. Hợp đồng `equals` cũng đòi hỏi phản xạ, đối xứng, bắc cầu, nhất quán và `x.equals(null) == false` khi `x` khác `null`.

Một số hệ quả quan trọng:

1. **Ghi đè `equals` theo giá trị nhưng giữ nguyên `Object.hashCode` là sai hợp đồng** trong các trường hợp hai đối tượng riêng biệt được coi là bằng nhau. `Object.hashCode` không được thiết kế để bám theo trường dùng trong `equals`.
2. **Đã ghi đè cả hai nhưng để `hashCode` phụ thuộc trường bị `equals` bỏ qua** cũng sai: hai đối tượng bằng nhau có thể có hash khác nhau.
3. **Chỉ ghi đè `hashCode` và giữ nguyên `Object.equals`** chưa chắc vi phạm hợp đồng: `Object.equals` vẫn so cùng tham chiếu. Tuy nhiên nó **không tạo ra bình đẳng theo giá trị**, dù các đối tượng có hash bằng nhau.

## 2. Cấu trúc băm thực sự sử dụng hai phương thức như thế nào?

Hãy tưởng tượng một `HashMap<Key, Value>` có hai khóa biểu diễn cùng mã đơn hàng. Khi `map.put(k1, value)`, `HashMap` tính hash của `k1` để xác định vị trí lưu. Khi `map.get(k2)`, nó tính hash của `k2` để tìm vùng tương ứng, rồi dùng `equals` để phân biệt các khóa ứng viên có hash tương thích.

Trong các bản triển khai `HashMap` tiêu chuẩn của JDK, hash đầu vào được trộn bit để xác định bucket; khi tìm khóa, cấu trúc kiểm tra cả hash đã tính và tính bằng nhau của khóa. Bảng dưới là **mô hình giải thích hành vi**, không phải lời hứa rằng mọi chi tiết bên trong `HashMap` sẽ mãi cố định qua mọi bản JDK.

| Tình huống | `equals` | `hashCode` | Hành vi mong đợi của cấu trúc băm |
| --- | --- | --- | --- |
| Cùng giá trị logic, triển khai đúng | `true` | Bằng nhau | `get` bằng khóa tương đương tìm được bản ghi; `Set` loại trùng |
| Khác giá trị, hash trùng nhau | `false` | Bằng nhau | Vẫn lưu/nhận diện thành hai khóa khác nhau; phải xử lý collision |
| Cùng giá trị logic, hash khác nhau | `true` | Khác nhau | **Vi phạm hợp đồng**; `get` có thể bỏ lỡ khóa và `Set` có thể chứa hai phần tử bằng nhau |
| Cùng một đối tượng, không đổi trạng thái liên quan | `true` | Ổn định | Truy xuất bằng chính khóa đã lưu phải hoạt động bình thường |

Phát biểu chính xác là **có thể** xảy ra lỗi tra cứu khi hợp đồng bị phá vỡ; số bucket, cơ chế trộn hash, thứ tự chèn và va chạm có thể ảnh hưởng biểu hiện cụ thể. Để thấy lỗi một cách xác định, ví dụ runnable bên dưới cố tình gán các giá trị hash khác nhau rõ rệt cho hai đối tượng mà `equals` coi là bằng nhau.

## 3. Lỗi 1: chỉ ghi đè `equals()`, bỏ quên `hashCode()`

Giả sử khóa `EqualsOnly` chứa một `code`. Chúng ta muốn hai đối tượng cùng `code` là bằng nhau, nên viết:

```java
static final class EqualsOnly {
    private final String code;

    EqualsOnly(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        return other instanceof EqualsOnly key
                && code.equals(key.code);
    }

    // LỖI: thiếu override hashCode().
}
```

Đây là **đoạn lớp lồng minh họa**; chương trình độc lập đầy đủ nằm ở mục 5. Hai đối tượng `new EqualsOnly("A")` được `equals` đánh giá bằng nhau dù là hai đối tượng khác nhau. Tuy nhiên `hashCode` kế thừa từ `Object` không có nghĩa vụ tạo cùng hash cho hai đối tượng ấy.

Hệ quả là quy tắc “bằng nhau thì cùng hash” **không được bảo đảm**. Trong thực tế, `HashSet.contains(new EqualsOnly("A"))` hoặc `HashMap.get(new EqualsOnly("A"))` có thể trả kết quả không mong đợi khi đối tượng được thêm bằng một instance khác có cùng `code`.

**Không nên tạo một bài kiểm thử giả định rằng hai lần `new EqualsOnly("A")` chắc chắn có hash khác nhau.** Hợp đồng `Object.hashCode` không bảo đảm mọi đối tượng khác tham chiếu luôn có hash khác nhau; va chạm vẫn có thể xảy ra. Sự thiếu bảo đảm chính là lỗi thiết kế, dù một lần chạy tình cờ tìm được phần tử.

Cách sửa là ghi đè cả `hashCode` theo **cùng bộ thuộc tính định nghĩa bình đẳng**, ví dụ:

```java
@Override
public int hashCode() {
    return code.hashCode();
}
```

Với nhiều trường, có thể dùng `Objects.hash(field1, field2)` hoặc công thức kết hợp hash phù hợp. Nếu dùng `Arrays.equals`, `Arrays.deepEquals` hay `Objects.deepEquals` cho dữ liệu mảng/lồng nhau, cách tính hash phải tương ứng (`Arrays.hashCode` hoặc `Arrays.deepHashCode` khi thích hợp). Không nhất thiết mọi trường của đối tượng đều tham gia hash; những trường khiến hai đối tượng có thể *bằng nhau* phải được tính sao cho hai đối tượng bằng nhau luôn có cùng kết quả.

## 4. Lỗi 2: có `hashCode()` nhưng thiết kế không tương thích `equals()`

Một lỗi khó nhận ra hơn: cả hai phương thức có tồn tại nhưng chúng căn cứ vào **hai tập thuộc tính không tương thích**.

Ví dụ, đối tượng có `code` và `hash`. `equals` chỉ dùng `code`, trong khi `hashCode` trả trực tiếp trường `hash`:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    return other instanceof IncompatibleHash key
            && code.equals(key.code);
}

@Override
public int hashCode() {
    return hash; // LỖI: khác nhau dù equals có thể true.
}
```

Đây là **hai phương thức trong lớp `IncompatibleHash`** ở ví dụ chạy đầy đủ bên dưới. Khi tạo `new IncompatibleHash("A", 1)` và `new IncompatibleHash("A", 2)`, hai đối tượng bằng nhau theo `code` nhưng hash lần lượt là 1 và 2. Vi phạm xảy ra **ngay tại cặp đối tượng**, trước cả khi sử dụng collection.

Đây là lỗi về **tương thích hợp đồng**, không phải lỗi cú pháp Java. Trình biên dịch không thể chứng minh tất cả phép so sánh giá trị động của ứng dụng.

Một biến thể khác: `equals` bỏ qua `lastUpdated`, nhưng `hashCode` lại dùng `lastUpdated`. Hai bản ghi cùng danh tính logic khác thời gian cập nhật có thể bị hash vào hai vị trí khác nhau. Ngược lại, nếu `equals` dùng cả `code` và `region`, còn `hashCode` chỉ dùng `code`, quy tắc bắt buộc vẫn có thể đúng: hai đối tượng bằng nhau chắc chắn cùng `code` nên cùng hash, dù tạo nhiều collision hơn. **Hash không buộc phải dùng đúng toàn bộ trường trong `equals`**, nhưng phải tuyệt đối tương thích.

## 5. Chương trình Java 17+ chạy được: sai và đúng cạnh nhau

Lưu mã dưới đây vào tệp **`HashContractDemo.java`**. Có ba kiểu khóa:

- `EqualsOnly`: cố tình ghi đè `equals` nhưng không ghi đè `hashCode`.
- `IncompatibleHash`: cố tình ghi đè cả hai nhưng trả hash không phụ thuộc tiêu chí `equals`.
- `GoodKey`: ghi đè đúng cả hai theo `code`, lưu dữ liệu bất biến.

```java
import java.util.*;

public class HashContractDemo {
    static final class EqualsOnly {
        private final String code;

        EqualsOnly(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof EqualsOnly key
                    && code.equals(key.code);
        }
        // Cố ý kế thừa Object.hashCode(): sai với value equality.
    }

    static final class IncompatibleHash {
        private final String code;
        private final int hash;

        IncompatibleHash(String code, int hash) {
            this.code = Objects.requireNonNull(code);
            this.hash = hash;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof IncompatibleHash key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return hash; // Cố ý không nhất quán với equals.
        }
    }

    static final class GoodKey {
        private final String code;

        GoodKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof GoodKey key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        EqualsOnly e1 = new EqualsOnly("A");
        EqualsOnly e2 = new EqualsOnly("A");
        System.out.println("equals-only logically equal: " + e1.equals(e2));

        IncompatibleHash b1 = new IncompatibleHash("A", 1);
        IncompatibleHash b2 = new IncompatibleHash("A", 2);
        Map<IncompatibleHash, String> brokenMap = new HashMap<>();
        brokenMap.put(b1, "stored");

        Set<IncompatibleHash> brokenSet = new HashSet<>();
        brokenSet.add(b1);
        brokenSet.add(b2);

        System.out.println("bad pair equals: " + b1.equals(b2));
        System.out.println("bad pair hashes: "
                + b1.hashCode() + " / " + b2.hashCode());
        System.out.println("broken map get original: " + brokenMap.get(b1));
        System.out.println("broken map get equal key: " + brokenMap.get(b2));
        System.out.println("broken set size: " + brokenSet.size());

        GoodKey g1 = new GoodKey("A");
        GoodKey g2 = new GoodKey("A");
        Map<GoodKey, String> goodMap = new HashMap<>();
        goodMap.put(g1, "stored");

        Set<GoodKey> goodSet = new HashSet<>();
        goodSet.add(g1);
        goodSet.add(g2);

        System.out.println("good pair equals: " + g1.equals(g2));
        System.out.println("good pair hashes equal: "
                + (g1.hashCode() == g2.hashCode()));
        System.out.println("good map get equal key: " + goodMap.get(g2));
        System.out.println("good set size: " + goodSet.size());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac HashContractDemo.java
java HashContractDemo
```

Kết quả của chương trình:

```text
equals-only logically equal: true
bad pair equals: true
bad pair hashes: 1 / 2
broken map get original: stored
broken map get equal key: null
broken set size: 2
good pair equals: true
good pair hashes equal: true
good map get equal key: stored
good set size: 1
```

**Phân tích dòng theo dòng:**

1. `e1.equals(e2)` là `true`, vì cả hai mã cùng là `"A"`. Không in ra hash của `EqualsOnly` vì kết quả kế thừa từ `Object` không có giá trị cụ thể được bảo đảm trên mọi JVM/lần chạy.
2. `b1.equals(b2)` là `true`, nhưng `b1.hashCode() == 1` và `b2.hashCode() == 2`. Đây là vi phạm xác định được mà không cần suy đoán về identity hash.
3. `brokenMap.get(b1)` là `stored` vì tra đúng đối tượng và hash 1 đã dùng để lưu.
4. `brokenMap.get(b2)` là `null`: với cặp hash 1 và 2 ở ví dụ này, `HashMap` không tìm thấy vùng chứa khóa đã lưu. Kết quả `null` ở đây nghĩa là **không tìm được bản ghi**, không phải có một mapping với giá trị `null` (ví dụ không lưu giá trị `null`).
5. `brokenSet.size()` là 2: `HashSet` lưu hai đối tượng mà `equals` lại coi là bằng nhau. Đây là một hậu quả cụ thể của vi phạm hợp đồng.
6. `g1` và `g2` có cùng `code` nên `equals` cho `true` và `hashCode` cho cùng kết quả; tra bằng khóa tương đương thành công và `HashSet` chỉ giữ một giá trị logic.

Chú ý: Trong mã ví dụ, `Map` và `Set` là các **interface**; các thể hiện thực tế là `HashMap` và `HashSet`. Không nên áp dụng kết luận về cơ chế bucket cho các cấu trúc không dựa trên hash, ví dụ `TreeMap` và `TreeSet` có thể sử dụng `Comparator`/`compareTo` để định danh khóa thay vì `equals/hashCode`.

## 6. Lỗi 3: thay đổi thuộc tính của khóa sau khi thêm vào collection

Ngay cả khi hai phương thức nhất quán ở thời điểm tạo đối tượng, **thay đổi trường tham gia `equals`/`hashCode` sau khi lưu khóa** có thể làm hỏng kết quả tra cứu.

Giả sử `MutableKey` có trường `code` được dùng trong cả `equals` và `hashCode`. Ta thêm đối tượng có `code = "A"` vào `HashSet`, rồi đổi `code = "B"`. Đối tượng vẫn đang nằm ở vị trí được xác định từ hash của `"A"` khi chèn, trong khi lần gọi `contains` tiếp theo tính hash theo `"B"`. Vì vậy có thể không tìm lại được khóa, kể cả khi giữ chính cùng tham chiếu.

Đây không phải lỗi “chỉ ghi đè `equals`” nhưng là một **lỗi bảo toàn tính ổn định của hash khi khóa còn nằm trong cấu trúc băm**. `HashMap` không tự dời một entry sang bucket mới chỉ vì trường của khóa bị sửa.

Giải pháp thực tế:

- Ưu tiên lớp khóa **bất biến** với các trường xác định equality được khai báo `final` và bản thân dữ liệu thành phần không thay đổi ngầm.
- Nếu cần đổi danh tính logic của khóa, xóa entry bằng trạng thái cũ trước, tạo khóa mới và chèn lại.
- Không dùng trường có thể đổi theo thời gian (`updatedAt`, trạng thái phiên, thông tin hiển thị) trong equality/hash của khóa trừ khi có thiết kế cập nhật collection đặc biệt rõ ràng.

Đặt `final` ở **tham chiếu tới một mảng hoặc đối tượng mutable** không tự làm nội dung bên trong bất biến. Ví dụ, khóa giữ `final List<String> values` vẫn có thể gặp lỗi nếu các phần tử trong list bị thay đổi và list là thành phần được đưa vào hash.

## 7. Cách thiết kế đúng khi có nhiều trường, null, mảng và kế thừa

### 7.1. Cùng danh tính logic

Trước tiên cần trả lời: hai đối tượng thuộc cùng kiểu nên bằng nhau theo tiêu chí gì? Với khóa người dùng (`tenantId`, `userId`), nếu **cả hai** trường định nghĩa danh tính, chúng phải được so sánh nhất quán trong `equals` và tham gia một cách tương thích vào `hashCode`:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof UserKey key)) return false;
    return Objects.equals(tenantId, key.tenantId)
            && Objects.equals(userId, key.userId);
}

@Override
public int hashCode() {
    return Objects.hash(tenantId, userId);
}
```

Đây là **đoạn phương thức minh họa** cho lớp `UserKey` đã có hai trường `tenantId` và `userId`; không phải tệp độc lập. `Objects.equals` xử lý `null` ở các **trường** một cách an toàn. Nếu chính đối tượng bên phải là `null`, điều kiện `instanceof` trả `false`.

Không bắt buộc dùng `Objects.hash`: với một trường `String` không null, `code.hashCode()` là hoàn toàn hợp lệ, như `GoodKey` đã minh họa. Nếu lựa chọn dùng ít trường để tính hash thì phải biết cái giá collision cao hơn, nhưng không được làm hash phụ thuộc trường nằm ngoài tiêu chí bình đẳng theo cách gây khác hash ở hai đối tượng bằng nhau.

### 7.2. Mảng cần so sánh theo nội dung

`Objects.equals(arrayA, arrayB)` và `arrayA.equals(arrayB)` trên các mảng Java thông thường so theo **tham chiếu**, không so phần tử. Với mảng một chiều, dùng `Arrays.equals` kết hợp `Arrays.hashCode`. Với mảng lồng nhau cần so sâu, cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode` theo đúng cấu trúc. Phải quyết định rõ nội dung mảng có thể thay đổi hay không khi dùng làm khóa băm.

### 7.3. Kế thừa có thể gây lỗi khác

Nếu lớp cha coi một số đối tượng lớp con bằng nhau, nhưng lớp con bổ sung trường tham gia equality và từ chối lớp cha, vi phạm **đối xứng** có thể xảy ra trước cả khi xét hash. Nếu một lớp con dùng `super.equals` và mở rộng thêm tiêu chí, cần kiểm tra đầy đủ phản xạ/đối xứng/bắc cầu và `hashCode` xuyên mọi kiểu có khả năng so sánh.

Không thể sửa lỗi kế thừa chỉ bằng cách đổi công thức hash. Với kiểu giá trị, `final class`, `record` và composition thường dễ duy trì hơn khi không cần quan hệ bằng nhau xuyên kiểu.

### 7.4. Giá trị bất biến và `record`

Từ Java 16, `record` cung cấp `equals` và `hashCode` tự sinh theo các thành phần. Trong Java 17, khai báo:

```java
record OrderKey(String tenantId, String orderId) {}
```

là một cách ngắn gọn để có bình đẳng theo thành phần, khi kiểu dữ liệu phù hợp với mô hình khóa giá trị. **Lưu ý**: đối tượng thành phần mutable vẫn có thể thay đổi trạng thái bên trong; với trường kiểu mảng, cách so sánh mặc định của `record` không biến mảng thành bình đẳng sâu theo nội dung.

## 8. Kiểm thử hợp đồng, không chỉ kiểm thử kết quả hash

Khi tự viết `equals` và `hashCode` cho một loại khóa, nên kiểm tra:

| Kiểm thử | Điều kiện cần xác nhận |
| --- | --- |
| Phản xạ | `a.equals(a)` là `true` |
| Đối xứng | `a.equals(b) == b.equals(a)` |
| Bắc cầu | Nếu `a.equals(b)` và `b.equals(c)`, thì `a.equals(c)` |
| Null | `a.equals(null)` là `false` |
| Hash đi cùng equality | Nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()` |
| Collision | Có thể có `hash(a) == hash(b)` trong khi `!a.equals(b)`, nhưng collection vẫn phân biệt đúng |
| `HashMap`/`HashSet` | `get`/`contains` thành công với khóa tương đương; `Set` không giữ trùng giá trị logic |
| Tính ổn định | Nếu thông tin tham gia equality không thay đổi, hash của cùng đối tượng phải ổn định |

Có thể thêm một assertion ngắn trong bộ kiểm thử:

```java
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("equals/hashCode contract violated");
}
```

Đây là **đoạn kiểm tra giả định đã có biến `a`, `b`**, không phải chương trình độc lập. Kiểm thử nên tạo nhiều cặp khác nhau (cùng giá trị, khác giá trị, khác kiểu, trường tùy chọn null, trường mutable nếu có), và kiểm thử riêng cả `HashMap`/`HashSet` trong tình huống ứng dụng thực tế.

Đừng kiểm thử bằng giả thiết `!a.equals(b)` thì hash phải khác. Giả thiết đó **sai**: collision là hợp lệ. Cũng đừng khẳng định các giá trị hash cụ thể của `Object.hashCode` sẽ cố định giữa máy hoặc các phiên chạy.

## 9. Bảng tổng hợp nguyên nhân và hướng khắc phục

| Lỗi thực tế | Dấu hiệu | Hướng sửa |
| --- | --- | --- |
| Ghi đè `equals` mà quên `hashCode` | Hai đối tượng bằng nhau theo giá trị nhưng kết quả tra cứu bằng instance tương đương không ổn định | Ghi đè `hashCode` theo dữ liệu equality |
| `equals` và `hashCode` dùng hai tập trường không tương thích | `equals` là `true`, nhưng hash khác nhau | Xác định một định nghĩa danh tính logic nhất quán |
| `equals` sai tính đối xứng/bắc cầu trong kế thừa | Có cặp/chuỗi đối tượng cho kết quả trái chiều | Thiết kế lại quan hệ bằng nhau giữa các lớp |
| Trường khóa bị sửa sau khi insert | `contains` hoặc `get` không tìm thấy khóa | Dùng khóa bất biến hoặc xóa rồi thêm khóa mới |
| Hash luôn trả hằng số | Vẫn có thể đúng hợp đồng nhưng rất nhiều collision và giảm hiệu năng | Phối hợp các thuộc tính equality thành phân bố hash hợp lý |
| Chỉ ghi đè `hashCode` để mong bằng nhau theo giá trị | Hai instance có hash bằng nhau nhưng `equals` vẫn `false` | Phải ghi đè `equals` nếu muốn value equality |
| Kiểm tra equality bằng `==` khi cần so giá trị | Hai instance cùng dữ liệu vẫn không bằng nhau | Dùng `equals` đã thiết kế đúng; không nhầm identity với equality |
| Mảng dùng sai cặp phương thức | Hash/so sánh theo tham chiếu trong khi nghiệp vụ cần so nội dung | Dùng cặp `Arrays.equals/hashCode` hoặc `deepEquals/deepHashCode` thích hợp |

**Câu hỏi tự kiểm tra:** Hai đối tượng `CustomerKey("C01", "west")` và `CustomerKey("C01", "east")` được `equals` coi là bằng nhau vì chỉ so mã khách hàng. Nếu `hashCode` lại băm cả mã khách hàng và vùng, đó có phải một triển khai đúng? **Không**, vì hai đối tượng bằng nhau có thể nhận hai hash khác nhau. Hoặc sửa `equals` để vùng cũng là thành phần danh tính, hoặc bỏ vùng khỏi công thức hash, tùy yêu cầu nghiệp vụ.

Nguyên tắc thiết kế bền vững là **xác định rõ giá trị nào làm nên danh tính**, triển khai `equals` và `hashCode` tương thích với quan hệ ấy, ưu tiên khóa bất biến và kiểm tra trên các collection băm thật sự. `hashCode` giúp tìm nhanh; `equals` mới xác định bằng nhau. Chúng phải hợp tác đúng hợp đồng.