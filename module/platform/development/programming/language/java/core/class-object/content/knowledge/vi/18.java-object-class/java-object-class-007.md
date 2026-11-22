# Hệ quả của thay đổi trường dùng trong `equals()` và `hashCode()`

## 1. Bài toán: object vẫn ở trong tập hợp nhưng có thể không tìm lại được

Trong Java, `HashMap` và `HashSet` sử dụng **hash code và phép so sánh bằng nhau** để tổ chức, tìm kiếm và phát hiện khóa/phần tử trùng nhau. Nếu một field ảnh hưởng đến `equals(Object)` hoặc `hashCode()` bị thay đổi **trong khi object đang là key trong `HashMap` hoặc phần tử trong `HashSet`**, cấu trúc đã lưu object dựa trên trạng thái cũ sẽ **không tự di chuyển hay đánh chỉ mục lại** chỉ vì một setter chạy.

Hậu quả có thể là:

- `contains` hoặc `get` không tìm được một object dù iterator vẫn duyệt thấy nó.
- `remove` theo key hiện tại không thành công.
- Hai object khác nhau vốn không equal lúc insert trở thành equal sau mutation nhưng vẫn nằm trong cùng một Set.
- Một Map có thể chứa các entries mà keys hiện tại mang cùng logical identity.
- Cache miss, thao tác tạo trùng, dữ liệu index không nhất quán và kiểm thử khó tái hiện.

**Đây là lỗi do thay đổi các thông tin quyết định equality/hash trong suốt thời gian lưu key, không phải lỗi Java syntax.**

Ví dụ class dễ gặp:

~~~java
class MutableKey {
    private String code;

    MutableKey(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    void rename(String next) {
        code = java.util.Objects.requireNonNull(next);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

Đây là **class minh họa**, chưa có `main`. Khi `code = "A"`, hash là hash của A; đổi sang B thì hash đổi. Nếu key đã được thêm vào hash collection lúc A, collection không được gọi để cập nhật entry khi object tự đổi field.

> **Nguyên tắc:** thông tin ảnh hưởng `equals/hashCode` của một key phải ổn định trong suốt thời gian key đang được lưu trong hash-based collection, hoặc phải được thay bằng một protocol gỡ bỏ, cập nhật và thêm lại có kiểm soát.

Bài Knowledge README Java 17+ này giải thích hợp đồng `Object.equals/hashCode`, cơ chế hash lookup, triệu chứng và những giới hạn được bảo đảm, mutable fields và aliases, records, entity identity, HashMap/HashSet/TreeSet, cách thiết kế immutable keys, cập nhật an toàn, concurrency và các bài kiểm tra. Có bốn chương trình Java độc lập kèm lệnh chạy và kết quả đầu ra.

## 2. Xác định chính xác điều kiện gây *key instability*

Trước khi xem HashMap lỗi thế nào, chỉ cần giữ hai quy tắc: `equals` là phép bằng nhau theo contract của class (mặc định Object identity); và **nếu hai keys equal thì hash codes của chúng phải bằng nhau**. Hợp đồng `equals` vẫn có tính phản xạ/đối xứng/bắc cầu/nhất quán khi equality-related state không thay đổi; collision giữa unequal keys vẫn hợp lệ.

**Rủi ro cần điều tra của bài này là trục thời gian**, không phải việc một implementation luôn sai:

~~~text
T0: key.code = "A"  → hash/equality theo trạng thái A
T1: map.put(key, value)  → entry được đặt khi key còn ở trạng thái A
T2: key.rename("B")  → cùng object, nhưng field so sánh/hash đã đổi
T3: map.get(key)  → lookup dùng trạng thái B; entry không được tự di chuyển
~~~

Ngay cả nếu implementation `equals` và `hashCode` **vẫn phù hợp với nhau tại T3**, việc đổi thông tin equality-relevant trong thời gian làm key đã khiến ứng dụng mất guarantee membership/lookup theo điều kiện của collections. **Không khẳng định mọi JDK luôn trả cùng kết quả**; hash collision và cấu trúc hiện tại có thể tình cờ làm lookup thành công.

Các mục sau giải thích cơ chế, trình bày một chương trình HashSet có expected stdout chỉ dựa vào facts xác định, rồi đưa ra giải pháp **immutable key**, **stable identity**, hoặc **remove–modify–reinsert** có kiểm soát.

## 3. HashMap sử dụng key như thế nào?

Về mặt khái niệm:

**Lúc ghi `put(key, value)`:**

1. Map lấy `hashCode` từ key để xác định đường lưu trữ thích hợp.
2. Nó dùng phép so sánh keys theo contract để phát hiện key tương đương.
3. Nó lưu entry liên quan đến key và value.

**Lúc đọc `get(lookupKey)`:**

1. Map tính hash của lookupKey ở **thời điểm đọc**.
2. Tìm candidates phù hợp cấu trúc lưu trữ.
3. Kiểm tra logical equality để chọn entry.

~~~text
Thời điểm put:
  key.code = "A"
  key.hashCode() = hash("A")
  entry được tổ chức theo trạng thái key lúc đó

Sau lệnh key.rename("B"):
  key.code = "B"
  key.hashCode() = hash("B")
  entry không tự được di chuyển chỉ vì lệnh rename

Thời điểm get:
  lookup dựa vào hash("B")
  trạng thái đã không còn khớp với cấu trúc được lập theo "A"
~~~

**HashMap không deep-copy key**, không đăng ký listener tự động theo dõi các setters trên key và không thể tự biết bao giờ code của bạn đổi một field.

### 3.1. Hành vi sau mutation không có một kết quả cố định được chuẩn hóa

Điều khoản của Java Collections nêu rõ **hành vi không được quy định đầy đủ** nếu giá trị của một object bị thay đổi theo cách ảnh hưởng tới equality khi nó đang nằm trong Set/được dùng làm key của Map.

Vì vậy, đừng khẳng định mọi JVM/implementation luôn trả `false` cho `contains` sau mutation. Những triệu chứng phụ thuộc hash, collision, capacity, implementation và hoàn cảnh. **Một test hôm nay vẫn trả true không có nghĩa thiết kế mutable key được bảo đảm đúng**.

Chúng ta có thể phát biểu chắc chắn hơn:

- Java object đã thay field.
- Key hash/equality hiện tại có thể khác thời điểm insert.
- Collection không tự reindex một key chỉ vì đổi field.
- Ứng dụng không còn được dựa vào lookup/membership behavior như khi key ổn định.

### 3.2. Iterator và lookup là hai con đường khác nhau

Một iterator có thể duyệt entry đã được lưu trong Set, trong khi `contains` lại thực hiện lookup theo hash/equality hiện tại. Do đó thấy object trong vòng `for` **không chứng minh** `set.contains(object)` sẽ thành công sau một mutation không hợp lệ.

Tương tự, `map.size() > 0` chỉ báo có entries về mặt cấu trúc, không chứng minh key hiện tại được tra cứu đúng.

## 4. Ví dụ chạy được 1 — hash đổi, object vẫn còn trong Set

Tạo tệp **`MutableKeyObservationDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MutableKeyObservationDemo {
    static final class MutableKey {
        private String code;

        MutableKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void rename(String next) {
            code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }

        @Override
        public String toString() {
            return "Key(" + code + ")";
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Set<MutableKey> keys = new HashSet<>();
        int before = key.hashCode();

        keys.add(key);
        System.out.println("Original hash = " + before);
        System.out.println("Original size = " + keys.size());

        key.rename("B");
        int after = key.hashCode();

        System.out.println("New hash = " + after);
        System.out.println("Hash changed = " + (before != after));
        System.out.println("Stored object = " + keys.iterator().next());
        System.out.println("Same reference = "
                + (keys.iterator().next() == key));
        System.out.println("Size after rename = " + keys.size());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 MutableKeyObservationDemo.java
java MutableKeyObservationDemo
~~~

**Stdout chính xác:**

~~~text
Original hash = 65
Original size = 1
New hash = 66
Hash changed = true
Stored object = Key(B)
Same reference = true
Size after rename = 1
~~~

**Giải thích:**

- Hash của `"A"` là 65 và `"B"` là 66 theo công thức `String.hashCode`.
- Collection giữ reference tới **chính object key**; iterator nhận ra object đã có code mới.
- Rename không phải `remove` hay `add` nên Set size không tự đổi.
- Hash của object đã đổi từ 65 sang 66 trong lúc phần tử vẫn lưu.
- Chương trình cố ý **không in `contains(key)` với expected boolean cố định**, vì sau mutation ảnh hưởng equality/hash, collection API không bảo đảm một kết quả cụ thể.

Bạn có thể thử `keys.contains(key)` và `keys.remove(key)` tại dòng cuối. Trên implementations phổ biến, cả hai có thể không tìm được key dù iterator còn thấy nó. Xem đó là **triệu chứng**, không phải quy định mọi implementation phải xuất kết quả giống nhau.

## 5. Các hậu quả trong thực tế

### 5.1. Tra cứu thất bại

`HashMap.get`, `containsKey` hoặc `HashSet.contains` có thể không tìm được object. Code xử lý kết quả như “không tồn tại”, tạo lại dữ liệu hoặc bỏ sót nghiệp vụ.

### 5.2. Gỡ bỏ thất bại

`map.remove(key)` hay `set.remove(key)` có thể tìm theo trạng thái hash mới, trong khi entry được tổ chức theo trạng thái cũ. Thử xóa sau mutation có thể thất bại. **Muốn đổi key theo protocol thì thường phải gỡ trước khi sửa.**

### 5.3. Trùng logical key

Hai keys lúc insert không bằng nhau có thể trở thành equal sau khi một key đổi. Set/Map không được tự thông báo để quét toàn bộ entries và hợp nhất các keys đã thành equal.

~~~text
Lúc ghi:
  A.code = "A"
  B.code = "B"
  A.equals(B) = false

Sau khi đổi A:
  A.code = "B"
  B.code = "B"
  A.equals(B) = true
  Collection có thể vẫn chứa cả hai stored references
~~~

Điều này có thể xảy ra kể cả khi hashCode bị collision hoặc mọi key trả cùng hash cố định: **thay đổi quan hệ equality đã là rủi ro độc lập**.

### 5.4. Cache miss và stale indexes

Nếu cache dùng entity mutable làm key, rename/email/status change có thể gây lookup miss. Sau đó code tạo entry mới, kéo theo duplicate cached values hoặc logic không nhất quán.

Cũng cần phân biệt **stale secondary index**: nếu Map dùng **String email immutable** làm key nhưng `User.email` thay đổi mà application quên cập nhật index, đó vẫn là bug dù String key không mutate. Cần xóa mapping email cũ và thêm email mới theo business transaction.

### 5.5. Không dùng `hashCode` như unique identifier

Dù một key không đổi, `hashCode` vẫn không bảo đảm unique. Không dùng nó làm database primary key, authorization token hoặc dữ liệu bảo mật. Mutability và uniqueness là hai vấn đề khác nhau.

## 6. Vì sao sửa `hashCode()` trả một hằng không giải quyết triệt để?

Có người đề xuất:

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

Một constant hash không tự vi phạm nguyên tắc “equal objects có equal hash”, nhưng:

- Các entries có thể va chạm nhiều, làm giảm performance.
- `equals` vẫn thay đổi khi field mutable đổi.
- Collection không tự quét và gộp những keys mới trở thành equal.
- Vẫn không có contract đảm bảo semantics đúng khi key bị mutate ảnh hưởng equality.

**Không dùng constant hash như thuốc chữa chung cho mutable key.** Nếu object có stable identity, hãy thiết kế equality/hash theo identity ấy. Nếu không có, hãy dùng immutable value key hoặc quản lý thay đổi key tường minh.

### 6.1. Cache hash vào field có an toàn hơn không?

Một class có thể lưu cachedHash được tính lúc construction. Nhưng nếu `equals` sau đó dựa trên mutable fields, cached hash có thể không phù hợp equality mới. Nếu x và y trở thành equal nhưng cached hashes khác nhau, vi phạm equal-hash contract.

Chỉ cache hash khi bạn có **cơ sở chắc chắn dữ liệu quyết định equality không đổi** (immutable value object, hoặc một contract tương đương). Không cache để che giấu việc mutable fields bị sử dụng sai.

## 7. HashMap key và Map value có vai trò khác nhau

~~~java
Map<CustomerId, Customer> customers = new HashMap<>();
~~~

Nếu `CustomerId` immutable và `Customer` có `displayName`/`status` mutable, thay Customer name **không ảnh hưởng việc tra Map theo CustomerId**.

Ngược lại:

~~~java
Map<Customer, String> auditByCustomer = new HashMap<>();
~~~

nếu `Customer.equals/hashCode` dựa trên mutable displayName hoặc status, dùng Customer object trực tiếp làm key dễ gặp rủi ro.

Điểm phân biệt: **Map chọn entry dựa trên key**, không dựa vào việc Java value object thay field. Tuy nhiên, mutable values có những vấn đề riêng về concurrency/aliasing/domain invariants.

## 8. Chiến lược 1 — immutable key + mutable domain object

Một giải pháp dễ hiểu là **tách stable identity khỏi state có thể đổi**. Dùng Java 17 record có immutable components để biểu diễn key:

~~~java
record CustomerId(long number, String tenant) {
    CustomerId {
        if (number <= 0) {
            throw new IllegalArgumentException("ID không dương");
        }
        java.util.Objects.requireNonNull(tenant);
    }
}
~~~

Nếu tenant có thể đổi thì cần chọn một kiểu key khác. Một key an toàn phải **thật sự ổn định theo domain**, không chỉ có modifier final.

### 8.1. Ví dụ chạy được 2 — thay displayName không ảnh hưởng lookup

Tệp **`ImmutableMapKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ImmutableMapKeyDemo {
    record CustomerId(long value, String tenant) {
        CustomerId {
            if (value <= 0) {
                throw new IllegalArgumentException("ID không dương");
            }
            Objects.requireNonNull(tenant, "tenant");
            if (tenant.isBlank()) {
                throw new IllegalArgumentException("Tenant rỗng");
            }
        }
    }

    static final class Customer {
        private final CustomerId id;
        private String displayName;

        Customer(CustomerId id, String name) {
            this.id = Objects.requireNonNull(id);
            displayName = Objects.requireNonNull(name);
        }

        CustomerId id() {
            return id;
        }

        void rename(String next) {
            if (next == null || next.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            displayName = next;
        }

        String displayName() {
            return displayName;
        }
    }

    public static void main(String[] args) {
        CustomerId id = new CustomerId(7, "shop");
        Customer customer = new Customer(id, "Lan");

        Map<CustomerId, Customer> customers = new HashMap<>();
        customers.put(customer.id(), customer);

        System.out.println("Before = "
                + customers.get(new CustomerId(7, "shop"))
                        .displayName());

        customer.rename("Linh");

        System.out.println("After = "
                + customers.get(new CustomerId(7, "shop"))
                        .displayName());
        System.out.println("Key equal = "
                + id.equals(new CustomerId(7, "shop")));
        System.out.println("Key hash equal = "
                + (id.hashCode()
                        == new CustomerId(7, "shop").hashCode()));
        System.out.println("Map size = " + customers.size());
        System.out.println("Stable id = " + customer.id());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableMapKeyDemo.java
java ImmutableMapKeyDemo
~~~

**Stdout chính xác:**

~~~text
Before = Lan
After = Linh
Key equal = true
Key hash equal = true
Map size = 1
Stable id = CustomerId[value=7, tenant=shop]
~~~

- `CustomerId` là immutable record trong ví dụ vì components là primitive long và immutable String.
- Customer giữ final id nhưng có quyền thay displayName.
- Map tra cứu theo ID, vì vậy rename không làm key hash/equality đổi.
- Hai instance CustomerId khác nhau vẫn equal theo records components, được dùng để lookup cùng entry.
- Map size vẫn 1 và record toString có dạng được in như trên trong Java 17.

**Điều kiện:** `tenant` và `value` phải là identity ổn định của customer trong hệ thống thật. Nếu business thay tenant, cần định nghĩa chuyển key chính thức.

## 9. Chiến lược 2 — equals/hash chỉ dựa vào stable field

Một class có mutable fields vẫn có thể là hash key nếu những thông tin **tham gia equality/hash** không đổi trong giai đoạn lưu.

~~~java
final class User {
    private final long id;
    private String nickname;

    User(long id, String nickname) {
        this.id = id;
        this.nickname = nickname;
    }

    void rename(String next) {
        nickname = next;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof User user && id == user.id;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(id);
    }
}
~~~

Đây là class minh họa; code production còn phải validate id/name và xem ID namespace/uniqueness.

`nickname` được phép đổi; vì `equals/hashCode` chỉ phụ thuộc final `id`, việc đổi nickname **không làm cơ chế hash key thay đổi theo dạng lỗi đang học**.

### 9.1. Khi không override equals/hash cũng có thể đúng

Nếu nghiệp vụ thật sự muốn **reference identity**, inherited `Object.equals/hashCode` có thể phù hợp: thay business state không biến object thành một reference khác.

Đừng override equality theo mọi field chỉ vì IDE gợi ý hoặc vì nghĩ class OOP nào cũng phải override. Hãy trả lời: **hai objects khác reference khi nào thực sự được coi là một logical entity/value?**

### 9.2. Cạm bẫy generated ID của ORM

Một entity có database ID được cấp **sau** khi persist. Nếu equals/hashCode dựa trên ID mà entity đã được đưa vào hash collection **trước khi ID xuất hiện**, chuyển ID từ null sang một số có thể làm identity/hash đổi khi đang lưu.

Với JPA/ORM còn có proxy subclass, transient/persisted lifecycle, multi-tenant identity. **Không có một công thức copy-paste đúng cho mọi ORM.** Cần theo framework contract và domain identity. Cách đơn giản là không dùng entity có identity chưa ổn định làm hash key; dùng immutable application-assigned key nếu phù hợp.

## 10. Chiến lược 3 — gỡ trước, thay đổi, thêm lại

Nếu business bắt buộc thay mutable key object, một protocol có điều kiện là:

~~~text
remove(key) khi equality/hash còn ở state cũ
        ↓
kiểm tra việc remove thành công
        ↓
mutate state của key
        ↓
add/put(key) theo state mới
~~~

Phải **remove trước khi mutate**; remove sau khi code đã đổi có thể không tìm đúng stored entry.

### 10.1. Ví dụ chạy được 3 — remove/mutate/reinsert

Tệp **`RemoveMutateReinsertDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RemoveMutateReinsertDemo {
    static final class Key {
        private String code;

        Key(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void change(String next) {
            code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        Set<Key> set = new HashSet<>();
        Key one = new Key("A");

        set.add(one);
        boolean removed = set.remove(one); // Khi key còn ở A
        one.change("B");
        boolean added = set.add(one);

        System.out.println("Set removed = " + removed);
        System.out.println("Set readded = " + added);
        System.out.println("Set contains B = "
                + set.contains(new Key("B")));
        System.out.println("Set contains A = "
                + set.contains(new Key("A")));
        System.out.println("Set size = " + set.size());

        Map<Key, String> map = new HashMap<>();
        Key key = new Key("old");
        map.put(key, "payload");

        String payload = map.remove(key);
        key.change("new");
        map.put(key, payload);

        System.out.println("Map new = "
                + map.get(new Key("new")));
        System.out.println("Map old = "
                + map.containsKey(new Key("old")));
        System.out.println("Map size = " + map.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RemoveMutateReinsertDemo.java
java RemoveMutateReinsertDemo
~~~

**Stdout chính xác:**

~~~text
Set removed = true
Set readded = true
Set contains B = true
Set contains A = false
Set size = 1
Map new = payload
Map old = false
Map size = 1
~~~

### 10.2. Những giới hạn của protocol này

Đây là ví dụ **tuần tự, mỗi key được quản lý bởi một collection**. Production code cần thêm:

- Không object khác đổi key qua alias trong lúc operation.
- Remove thành công mới tiến hành thay.
- Kiểm tra **new key conflict** và quyết định reject/merge.
- Rollback nếu mutation hoặc insert thất bại.
- Cập nhật **mọi collection/index** đang giữ key, không chỉ một Set.
- Nếu có concurrent readers/writers, khóa/transaction phải bao phủ **toàn bộ sequence**.
- Không suy đoán hash-based collection iteration order được giữ nguyên sau remove/reinsert.

Nếu có thể, dùng **immutable key mới** thay vì mutate key cũ thường dễ audit/test hơn.

## 11. Immutable replacement thay cho sửa object key

Một operation thay identity có thể được mô tả là:

~~~java
record Key(String code) {
    Key {
        java.util.Objects.requireNonNull(code);
    }
}
~~~

Trong method sử dụng Map:

~~~java
Map<Key, String> values = new HashMap<>();
Key oldKey = new Key("A");
Key newKey = new Key("B");

values.put(oldKey, "payload");
String payload = values.remove(oldKey);
values.put(newKey, payload);
~~~

Đây là **fragment**, cần imports và method scope thích hợp. Không object key nào bị mutate. Operation thể hiện rõ việc chuyển mapping.

**Chú ý:** remove+put vẫn là **hai operations**. Với nhiều threads hoặc data được persisted, cần atomicity/transaction protocol nếu yêu cầu không có khoảng trống hoặc trạng thái trung gian. `ConcurrentHashMap` không tự làm mọi chuỗi lệnh nhiều bước trở thành atomic.

## 12. `final` field và records không đồng nghĩa deep immutability

Một hash key có:

~~~java
private final List<String> tags;
~~~

chỉ giữ **tham chiếu tới List** cố định, không cấm `tags.add(...)` khi underlying List mutable. Nếu equals/hashCode của key dựa trên List content, mutable tags gây cùng loại lỗi.

### 12.1. Alias của đầu vào

~~~java
List<String> source = new ArrayList<>(List.of("A"));
Key key = new Key(source);
source.add("B");
~~~

Nếu Key constructor chỉ viết `this.tags = source`, caller vẫn giữ alias tới List và có thể đổi nội dung sau khi key được thêm vào Map/Set.

### 12.2. Getter làm lộ mutable state

Nếu getter trả lại chính internal mutable List, caller có thể sửa ngay cả khi field private/final:

~~~java
List<String> tags() {
    return tags; // Nguy hiểm nếu tags mutable
}
~~~

Defensive copying phải xem **cả chiều nhận vào lẫn chiều trả ra**.

### 12.3. `List.copyOf` và shallow copying

`List.copyOf(source)` tạo unmodifiable List phù hợp, tránh mutation cấu trúc từ alias của source. Nhưng nó **không deep-copy mutable elements**. Với String immutable, hữu ích; với List chứa MutableItem, phần tử vẫn có thể bị sửa từ alias khác.

`Collections.unmodifiableList(source)` thường tạo **view** không cho sửa qua view, nhưng phản ánh mutation diễn ra trên source. View và snapshot **không tương đương**.

## 13. Ví dụ chạy được 4 — record có mutable component vẫn đổi hash

Tệp **`MutableRecordComponentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableRecordComponentDemo {
    record UnsafeKey(List<String> tags) {
    }

    record SafeKey(List<String> tags) {
        SafeKey {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        UnsafeKey unsafe = new UnsafeKey(source);
        SafeKey safe = new SafeKey(source);

        int beforeUnsafe = unsafe.hashCode();
        int beforeSafe = safe.hashCode();

        source.add("B");

        System.out.println("Unsafe = " + unsafe.tags());
        System.out.println("Safe = " + safe.tags());
        System.out.println("Unsafe shares source = "
                + (unsafe.tags() == source));
        System.out.println("Unsafe hash changed = "
                + (beforeUnsafe != unsafe.hashCode()));
        System.out.println("Safe hash unchanged = "
                + (beforeSafe == safe.hashCode()));
        System.out.println("Safe equal = "
                + safe.equals(new SafeKey(List.of("A"))));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MutableRecordComponentDemo.java
java MutableRecordComponentDemo
~~~

**Stdout chính xác:**

~~~text
Unsafe = [A, B]
Safe = [A]
Unsafe shares source = true
Unsafe hash changed = true
Safe hash unchanged = true
Safe equal = true
~~~

### 13.1. Phân tích

Record component fields được Java sinh là private final. Nhưng `UnsafeKey.tags` trỏ đến mutable List của caller. Generated record `hashCode` sử dụng component List, trong khi `List.hashCode` phản ánh nội dung. Sau `source.add("B")`, hash của UnsafeKey đổi.

`SafeKey` dùng compact constructor để copy List trước khi gán component field. Vì các phần tử là **String immutable**, snapshot là ổn định đối với tình huống này. Nếu tags chứa mutable objects, vẫn cần deep copy hoặc immutable element model.

**Điểm cần nhớ:** “record là final” và “record components final” không có nghĩa tất cả nested state bất biến.

## 14. Vì sao equality đổi dù hash không đổi vẫn là vấn đề?

Giả sử Set lưu hai objects A và B khi chúng không equal. Sau đó mutation khiến A.equals(B) true mà hashCode của chúng **tình cờ không đổi** do collision.

Collection không được thông báo để quét lại và loại logical duplicates. Vì vậy không nên thu hẹp quy tắc thành **“chỉ cần hashCode không đổi”**. Quy tắc đúng là: **thông tin ảnh hưởng đến logical equality/hash phải ổn định khi đang stored**.

Một implement `hashCode() { return 1; }` không ngăn vấn đề này. Dù equal-hash relation vẫn được thỏa, quan hệ **ai bằng ai** đã biến đổi so với thời điểm insert.

### 14.1. Vì sao Set.size không tự cập nhật?

`size` phản ánh số entries được quản lý theo các collection operations. Thay field của một object ngoài API collection không làm nó tự kiểm tra lại toàn bộ tập keys, kể cả khi có những pairs đã thành equal.

## 15. Mutable graph: một key trỏ tới object khác cũng có rủi ro

Không cần key tự có public setter. Nếu `hashCode` dựa trên nested object với state biến đổi, kết quả vẫn có thể thay:

~~~java
final class Group {
    private final List<Member> members;

    @Override
    public int hashCode() {
        return members.hashCode();
    }
}
~~~

Đây là fragment có type `Member` và List tương ứng; nếu Member thay field tham gia Member.hashCode, List.hashCode có thể thay theo. Tương tự với:

- Array có elements mutable.
- List/Map chứa mutable objects.
- Mutable Date.
- Record có mutable component.
- Nested value object chỉ **shallow immutable**.
- State lấy từ collaborators mà equality/hash gọi vào.

Cần kiểm tra **toàn bộ đường phụ thuộc của equality/hash**, không chỉ modifier `final` ở lớp ngoài.

### 15.1. Không nên gọi external mutable provider từ hashCode

Một hashCode dựa trên `configuration.currentRegion()` hoặc `clock.instant()` có thể đổi theo thời gian ngay cả khi fields trong key không được gán lại. Đây là thiết kế rất khó bảo vệ khi object làm key.

Equality/hash nên dựa trên **state mang nghĩa identity/value tại object đó**, không một nguồn thời gian/cấu hình mutable bên ngoài được gọi mỗi lần.

## 16. Nếu cùng object đang nằm trong nhiều collections

Giả sử một mutable `UserKey` đang được dùng trong:

- `HashSet<UserKey> activeUsers`.
- `HashMap<UserKey, Session> sessions`.
- `HashMap<UserKey, Roles> roleCache`.

Việc `activeUsers.remove(key)` trước rename **không đủ** nếu hai maps vẫn giữ cùng key object. Chúng cũng phải được cập nhật theo protocol, hoặc tốt hơn là tất cả cùng dùng **immutable UserId**.

Bài học về **ownership**: ai có quyền gọi setter ảnh hưởng key semantics, ai quản lý indexes, ai đảm bảo operation cập nhật toàn bộ hệ thống? Nếu nhiều callers có references tự do, rất khó bảo đảm.

### 16.1. Secondary index khác mutable-key bug

Một map có key String immutable `email` cũng cần cập nhật khi domain object đổi email. Đây là bug **stale index** chứ không phải String key tự mutate:

~~~text
emailIndex["old@domain"] = user
user.email = "new@domain"
emailIndex vẫn chưa được cập nhật
~~~

Cả hai bài toán đều đòi lifecycle protocol, nhưng một bên là **key object nội tại đổi hash**, bên kia là **mapping bị thiếu thao tác cập nhật**. Đừng dùng lời giải của trường hợp này để giải thích sai trường hợp kia.

## 17. `TreeSet` và `TreeMap`: cùng rủi ro nhưng không dựa trên hash

`TreeSet`/`TreeMap` dùng `Comparable` hoặc `Comparator` để tổ chức và tra cứu theo **ordering**, không phải hệ thống buckets của HashMap.

Nếu một Person đang lưu trong TreeSet sắp theo `age` rồi age thay đổi, ordering được dùng lúc insert có thể không còn đúng; lookup/range operations có thể sai. Vì vậy, **field tham gia compareTo/comparator cũng cần ổn định trong suốt thời gian làm key/member**.

Không suy ra TreeSet an toàn chỉ vì không dựa trên Object.hashCode.

Một Comparator không consistent với equals cũng có thể khiến cách TreeSet xác định “trùng” khác cách `equals` xác định logical equality; cần hiểu contract của SortedSet/Map.

## 18. Concurrency không tự cứu key bị mutable

Khi nhiều threads vừa mutate key vừa lookup, có thể có hai vấn đề độc lập:

1. **Data races/visibility** vì field mutable không có synchronization.
2. **Hash collection invariant bị phá** vì equality/hash của stored key thay đổi ngoài API collection.

Khai báo:

~~~java
private volatile String code;
~~~

có thể hỗ trợ visibility đối với field code, nhưng **không thông báo HashMap reindex**.

Dùng `ConcurrentHashMap` cũng không làm key tự theo dõi field changes. Nó bảo đảm các operation concurrent được mô tả bởi API, không làm mutable-key mutation trở nên an toàn.

### 18.1. Remove–mutate–reinsert có thể cần transaction

Nếu business thực sự cho phép đổi identity, cần lock/transaction bao phủ toàn bộ sequence và bảo đảm mọi readers/writers tuân thủ cùng protocol. Khi operations tách nhau, một reader có thể quan sát entry tạm thời vắng mặt.

Immutable key replacement thường giảm đáng kể trạng thái đồng bộ cần phải giải quyết.

## 19. Generated ID, ORM và proxies

Những lưu ý khi dùng JPA/ORM hoặc các framework làm việc với entities:

- ID được sinh sau persist có thể đổi từ null sang non-null.
- Entity mới và entity đã lưu có thể cần equality semantics khác.
- Proxy subclasses khiến `getClass()` và `instanceof` trong equals cần suy nghĩ cẩn thận.
- Không nên chọn mọi mutable entity field vào generated equals/hashCode.
- HashMap/HashSet có thể tồn tại lâu hơn một persistence transaction.

Không có một công thức equals/hashCode đúng cho mọi version/framework/domain. Hãy xem contract framework cụ thể và mô hình identity của hệ thống. Nếu có thể, dùng **stable immutable key** tách khỏi entity mutable.

### 19.1. Tránh lạm dụng công cụ sinh mã

IDE hoặc Lombok có thể sinh equals/hashCode từ các fields được chọn. Nếu chọn `status`, `updatedAt`, `displayName` hoặc List mutable chỉ vì có trong class, bạn có thể vô tình đổi logical equality khi state cập nhật.

**Generated code không tự biết business identity.** Review những fields tham gia và viết tests cho lifecycle thực tế.

## 20. Debugging thực tế

Nếu `map.get(key) == null` nhưng map còn entries, hãy kiểm tra:

1. Key dùng lúc put và lúc get có cùng semantic identity không?
2. Class có override `equals/hashCode` đúng signature `equals(Object)` không?
3. Những fields nào tham gia hai methods?
4. Có setter, ORM hydration, JSON mapper, external alias hoặc listener thay fields đó không?
5. Có nested List/Map/array/object con mutable không?
6. Hash trước put và sau thay đổi có khác không?
7. Iterator còn duyệt thấy key đang nói đến không?
8. Có nhiều maps/indexes giữ cùng key không?
9. Có concurrent mutation và data race không?
10. Có đang dựa trên collision/implementation-specific behavior không?
11. Có dùng key với unstable ID lifecycle không?
12. Có thể sửa bằng immutable ID/value key không?

**Không** sửa internal buckets của HashMap bằng reflection hoặc giả định gọi resize/rehash ở thời điểm bất kỳ sẽ khôi phục đúng toàn bộ business semantics. Đó là chi tiết implementation, không phải API contract.

### 20.1. Khi dữ liệu đã hỏng semantics

Một hướng phục hồi có kiểm soát:

- Ngừng/đồng bộ các cập nhật liên quan.
- Lấy data từ nguồn đủ tin cậy, có thể qua iteration hoặc persistence.
- Xác định equality/identity hiện tại và giải quyết logical duplicates theo domain policy.
- Xây lại index/collection với immutable keys.
- Công bố trạng thái mới bằng synchronization/transaction an toàn.
- Kiểm tra lookup, duplicates, size, recovery/rollback.

`new HashSet<>(oldSet)` có thể loại một số entries nay equal nhau; không nên làm điều đó mà không có policy để chọn bản ghi được giữ.

## 21. Kiểm thử cần gì ngoài một lần gọi `contains`?

| Phép kiểm thử | Điều cần xác nhận |
| --- | --- |
| Reflexivity/symmetry/transitivity | `equals` tuân đúng contract |
| Equal-hash rule | Equal instances có hash bằng nhau |
| Null handling | `equals(null)` false, không ném exception tùy tiện |
| Hash key stability | Equality-relevant state không thay trong suốt vòng đời làm key |
| Mutable non-key fields | Thay field không tham gia equality không làm lookup hỏng |
| HashMap lookup | Equal immutable key mới truy cập được value |
| HashSet membership | Equal immutable instance được nhận diện phù hợp |
| Aliasing | Input/getter không cho sửa nested equality components |
| Generated ID lifecycle | Không thay identity/hash của stored key ngoài ý muốn |
| Safe replacement | Xóa key cũ/thêm key mới đầy đủ các indexes |
| Concurrent access | Atomicity/visibility và ownership rõ |
| Comparator ordering | TreeSet/TreeMap có stable comparator keys |

Một test `contains(mutatedKey)` tình cờ true trên JVM hiện tại **không chứng minh ổn định**. Kiểm tra design rule và lifecycle thay vì chỉ quan sát một tình huống may mắn.

### 21.1. Đừng quên `@Override`

Nếu viết `boolean equals(MyType other)`, đó là **overload**, không thay thế `Object.equals(Object)`. Khi collections gọi qua Object-based contracts, kết quả khác dự kiến.

Dùng:

~~~java
@Override
public boolean equals(Object other) {
    // ...
}
~~~

và hashCode tương ứng. Java compiler sẽ phát hiện signature không thực sự override nếu annotation đặt sai.

## 22. Những lỗi thường gặp

1. Dùng email/username mutable làm hash identity rồi đổi chúng.
2. Sinh equals/hashCode theo tất cả fields, gồm status và updatedAt.
3. Override equals nhưng quên hashCode.
4. Dùng hash code khác fields với logical equality dẫn đến vi phạm equal-hash rule.
5. Chọn constant hash để che vấn đề equality mutation.
6. Cache hash cũ trong khi equals tiếp tục thay đổi.
7. Nghĩ `final List` làm các phần tử không thể sửa.
8. Nghĩ record tự deep-immutable.
9. Nghĩ `Collections.unmodifiableList(source)` luôn ngăn source đổi.
10. Thử remove **sau** khi key đã mutate.
11. Remove key từ một Set nhưng bỏ quên các Maps/indexes khác.
12. Thấy iterator có object rồi kết luận `contains` phải true.
13. Coi `size()` là số lượng logical equivalence classes hiện tại sau mutation.
14. Khẳng định mọi JVM đều trả một giá trị contains cố định sau khi phá contract.
15. Coi `ConcurrentHashMap` tự động theo dõi key setter.
16. Dùng volatile để chữa lỗi stale hash bucket.
17. Dùng mutable comparator field trong TreeSet.
18. Dùng generated ORM ID chưa ổn định trong hash collection.
19. Dùng `==` cho String content nếu cần value equality.
20. Dùng hashCode như ID không va chạm hoặc token bảo mật.
21. Dùng setter public cho field tham gia equality nhưng không có owner quản lý.
22. Dùng mutable object graph trong record/hash key mà không defensive copy.
23. Rebuild Set sau sự cố mà không giải quyết duplicate identity.
24. Sửa collection internals bằng reflection thay vì giải quyết domain protocol.

## 23. Bài tập tự kiểm tra có đáp án

**Câu 1.** Đổi một field tham gia `equals/hashCode` khi object đang trong HashSet có thể dẫn đến điều gì?

**Đáp án:** Lookup/remove/membership không còn được bảo đảm; object có thể vẫn được iterator duyệt nhưng `contains` không tìm được. Set không tự reindex theo field.

**Câu 2.** Hash của key đổi có bắt buộc `set.contains(key)` luôn false không?

**Đáp án:** Không. Hành vi không được quy định đầy đủ trong tình huống mutation làm ảnh hưởng equality; kết quả có thể tùy điều kiện/implementation.

**Câu 3.** Nếu hai objects equal, hash codes phải thế nào?

**Đáp án:** Phải bằng nhau. Ngược lại, cùng hash chưa đủ kết luận equal.

**Câu 4.** Nếu field đổi nhưng không tham gia equality/hash, có cùng lỗi không?

**Đáp án:** Không do cơ chế này, nếu toàn bộ state ảnh hưởng equality/hash vẫn ổn định và các hợp đồng khác đúng.

**Câu 5.** `final List<String> tags` có tự tạo immutable list không?

**Đáp án:** Không. Final chặn reassign field, không chặn thay nội dung List.

**Câu 6.** `record R(List<String> items)` có thể đổi hashCode không?

**Đáp án:** Có khi component List mutable được sửa và record hash dùng List component ấy.

**Câu 7.** `List.copyOf` có deep-copy các mutable elements không?

**Đáp án:** Không. Nó bảo vệ cấu trúc List nhưng không tự deep-copy từng mutable object con.

**Câu 8.** Tại sao dùng immutable CustomerId làm HashMap key tốt hơn dùng Customer với mutable displayName?

**Đáp án:** DisplayName thay đổi không làm stable ID equality/hash đổi, nên lookup theo ID vẫn có nghĩa nhất quán.

**Câu 9.** Có thể làm hashCode luôn là 1 để chữa mutation không?

**Đáp án:** Không nên: giảm hiệu năng vì collisions và không ổn định quan hệ equality giữa stored keys.

**Câu 10.** Nếu buộc mutate key, thứ tự thao tác thường nên là gì?

**Đáp án:** Remove theo state cũ → mutate → reinsert theo state mới, cùng việc quản lý tất cả owners/indexes và concurrency.

**Câu 11.** Nếu key cùng xuất hiện trong ba maps, remove khỏi một Map có đủ không?

**Đáp án:** Không. Các maps còn lại vẫn giữ key reference có thể mutate; cần cập nhật tất cả hoặc dùng immutable identifier.

**Câu 12.** Còn rủi ro nào nếu key hash không đổi nhưng equals đổi?

**Đáp án:** Logical duplicates và trạng thái membership của Set/Map có thể không còn phản ánh equality hiện tại; Set không tự quét/gộp.

**Câu 13.** TreeSet có an toàn trước thay đổi field dùng trong Comparator không?

**Đáp án:** Không. Nó dựa trên ordering được dùng khi insert; đổi comparison-relevant state cũng có thể phá lookup/order.

**Câu 14.** `volatile String code` có khiến HashMap tự cập nhật entry khi code đổi không?

**Đáp án:** Không. Volatile về memory visibility/order, không phải rehashing.

**Câu 15.** `ConcurrentHashMap` có biến mutable keys thành an toàn không?

**Đáp án:** Không. Nó hỗ trợ concurrent map operations, không tự theo dõi internal mutable key state.

**Câu 16.** Vì sao database-generated ID có thể tạo mutable hash key?

**Đáp án:** ID chuyển trạng thái chưa có → được cấp, khiến equals/hash có thể đổi nếu dựa trên ID, nhất là khi object đã nằm trong Set/Map.

**Câu 17.** HashMap.get trả null có luôn nghĩa key không tồn tại không?

**Đáp án:** Không: HashMap cho phép null values. Với map hợp lệ, có thể dùng containsKey phân biệt; với key đã mutate thì lookup contract cũng không đáng tin.

**Câu 18.** Có nên dùng một field status mutable cho logical identity của entity không?

**Đáp án:** Thường không nếu status được phép đổi mà entity vẫn là cùng entity. Chọn ổn định ID/domain contract.

**Câu 19.** Sửa một immutable email String key bằng setter có được không?

**Đáp án:** String không có setter đổi nội dung. Nhưng khi User.email đổi, secondary index Map<String,User> vẫn cần xóa key cũ và thêm key mới; đây là stale index, không phải mutable String key.

**Câu 20.** Tại sao không thể tin rằng map sẽ tự reindex khi key setter chạy?

**Đáp án:** Map giữ reference và thực hiện operations theo API, không quan sát/đăng ký từng mutation của tùy ý object key.

**Câu 21.** Khi rebuild collection đã có duplicates theo equality hiện tại, điều gì quan trọng?

**Đáp án:** Có policy chọn/gộp bản ghi, transaction/synchronization và kiểm tra lại indexes. Tạo Set mới có thể loại dữ liệu không mong muốn nếu không xem xét.

**Câu 22.** Nếu object không override equals/hashCode, thay displayName có đổi reference identity không?

**Đáp án:** Không. Inherited Object.equals là identity-based; mutation của business field không biến object thành reference khác.

**Câu 23.** `hashCode()` có phải unique ID giữa các objects không?

**Đáp án:** Không. Collisions hợp lệ và không có bảo đảm ổn định xuyên runs.

**Câu 24.** IDE tự tạo equals/hashCode từ mọi fields có an toàn không?

**Đáp án:** Chỉ khi field selection đúng logical equality contract và lifecycle. Các mutable fields thường cần xem lại.

**Câu 25.** Khi nào có thể dùng một mutable object làm Map key?

**Đáp án:** Khi thông tin quyết định equals/hashCode **thật sự ổn định trong suốt thời gian lưu** và ownership/API bảo đảm điều đó; tốt hơn nếu dùng immutable key.

## 24. Checklist áp dụng vào code Java thật

1. Đã xác định rõ **business identity** hoặc value equality chưa?
2. `equals` đúng signature `equals(Object)`, có `@Override` chưa?
3. `hashCode` tương thích với tất cả tình huống equals true chưa?
4. Những fields tham gia equality/hash có thay đổi theo lifecycle không?
5. Có generated ID chưa được cấp khi object đưa vào Set/Map không?
6. Nested objects/Lists/Maps/arrays có mutable không?
7. Input constructor đã defensive-copy phần cần giữ ổn định chưa?
8. Getter có làm lộ equality-relevant mutable representation không?
9. Có immutable record/value key phù hợp hơn không?
10. Có thể tách stable ID khỏi displayName/status/updatedAt không?
11. Nếu không thể tránh đổi key, có thể remove theo state cũ trước chưa?
12. Đã kiểm tra conflict với existing new key chưa?
13. Có rollback khi reinsert hoặc mutation fail không?
14. Các indexes/collections khác có giữ cùng key reference không?
15. Concurrent readers/writers có tuân thủ chung transaction/lock không?
16. Có đang lạm dụng `volatile`/`ConcurrentHashMap` để thay cho update protocol không?
17. Có comparator fields mutable trong TreeSet/TreeMap không?
18. Tests đã kiểm tra equal-hash rule và key stability chưa?
19. Có hiểu rằng một kết quả `contains` sau invalid mutation không phải contract không?
20. Có sử dụng hashCode làm ID bảo mật hoặc database key không? Nếu có, phải thiết kế lại.

## Kết luận

**`equals()` quyết định khi nào hai objects được coi là bằng nhau; `hashCode()` cung cấp hash tương ứng với logical equality.** Khi một object được lưu làm key/member của `HashMap` hoặc `HashSet`, collection cần những thông tin ấy **ổn định** để tra cứu, xóa và phát hiện trùng. Nếu bạn đổi field liên quan mà không thông qua API cập nhật collection, object có thể vẫn còn trong cấu trúc nhưng lookup trở nên không đáng tin. Hai methods vẫn có thể tự nhất quán với nhau **ở từng thời điểm**, song key đã bị thay trong khoảng thời gian lưu.

Cách thiết kế bền vững là **ưu tiên immutable keys**, dùng record/value type với components bất biến thật sự, tách stable identity khỏi business state mutable, và bảo vệ nested data bằng defensive copying phù hợp. Khi bắt buộc đổi key, hãy **gỡ theo state cũ → thay đổi → thêm lại**, đồng thời bảo vệ tất cả collections, indexes, error handling và concurrency.

Nguyên tắc này không có nghĩa cấm tất cả mutable fields: **chỉ cần đừng thay đổi những thông tin xác định equality/hash trong khi object đang làm key**. Nắm vững ranh giới đó sẽ tránh được một nhóm lỗi Java collections khó thấy nhưng có hậu quả lớn trong phần mềm thực tế.
