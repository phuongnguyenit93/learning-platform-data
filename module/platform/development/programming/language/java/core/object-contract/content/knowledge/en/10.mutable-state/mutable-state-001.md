# Ảnh hưởng của thay đổi trường tham gia `equals()` hoặc `hashCode()`

## 1. Vấn đề: một đối tượng vẫn là chính nó nhưng quan hệ bằng nhau có thể thay đổi

Một đối tượng Java có thể giữ nguyên **danh tính tham chiếu** trong khi các trường bên trong bị sửa. Nếu các trường đó tham gia vào `equals(Object)` hoặc `hashCode()`, việc sửa có thể thay đổi cách đối tượng được so sánh và cách một cấu trúc dữ liệu dựa trên hash tìm lại nó.

Ví dụ, một `Member` được định nghĩa bằng `email`:

```java
// Minh họa ý tưởng, không phải lớp hoàn chỉnh.
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof Member other)) return false;
    return email.equals(other.email);
}

@Override
public int hashCode() {
    return email.hashCode();
}
```

Khi `email` đổi từ `"a@example.com"` thành `"b@example.com"`, đối tượng trong bộ nhớ vẫn là đối tượng cũ: một biến alias vẫn có `alias == member` bằng `true`. Tuy nhiên, đối tượng này không còn bằng một `Member` khác mang email cũ, và mã băm được tính từ email cũng có thể thay đổi.

Đây không nhất thiết là lỗi của bản thân phương thức `equals`: việc một đối tượng mutable thay đổi quan hệ bằng nhau **sau khi dữ liệu liên quan bị sửa** không tự động vi phạm hợp đồng `Object.equals`. Rủi ro chính xuất hiện khi mã khác đang dựa vào quan hệ bằng nhau và mã băm **ổn định**, chẳng hạn `HashSet` hoặc một khóa đã đưa vào `HashMap`.

### Phân biệt ba thứ

| Thành phần | Khi trường thay đổi | Điều cần hiểu |
| --- | --- | --- |
| Danh tính đối tượng (`a == b`) | Không đổi chỉ vì gán trường mới. | Hai alias vẫn trỏ cùng instance. |
| Kết quả `a.equals(b)` | Có thể đổi nếu trường tham gia định nghĩa bằng nhau đổi. | Hai instance đang bằng nhau có thể trở thành khác nhau, hoặc ngược lại. |
| Giá trị `a.hashCode()` | Có thể đổi nếu dữ liệu dùng tính hash đổi. | Mã băm được tính lại không tự di chuyển entry đã nằm trong một bảng hash. |

Mục tiêu bài này là nhìn rõ **ảnh hưởng của thay đổi trạng thái lên cả hợp đồng so sánh và hành vi collection**, sau đó lựa chọn thiết kế an toàn.

## 2. Hợp đồng `equals` và `hashCode` nói gì về tính ổn định?

Hợp đồng của `equals(Object)` bao gồm phản xạ, đối xứng, bắc cầu, nhất quán và so với `null` phải trả `false`. Quy tắc **nhất quán** được hiểu với điều kiện: nếu không thay đổi thông tin dùng trong phép so sánh, việc gọi `equals` lặp lại phải tiếp tục cho cùng kết quả.

Tương tự, trong một lần chạy ứng dụng, nhiều lần gọi `hashCode` trên cùng đối tượng phải trả cùng giá trị khi **không có thông tin tham gia `equals` bị thay đổi**. Mã băm không bắt buộc cố định giữa những lần chạy chương trình khác nhau.

Quy tắc quan trọng nhất khi kết hợp cả hai:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

Chiều ngược lại không đúng: hai đối tượng khác nhau được phép trùng mã băm (*hash collision*).

Các trường hợp thay đổi đáng chú ý:

1. **Trường dùng ở cả `equals` và `hashCode` đổi:** quan hệ bằng nhau với những đối tượng khác và hash của đối tượng có thể cùng đổi. Nếu nó đang là khóa/element trong collection dựa trên hash, thao tác tra cứu có thể thất bại.
2. **Trường chỉ dùng trong `equals` đổi:** hash có thể giữ nguyên, nhưng những phần tử vốn khác nhau có thể trở thành bằng nhau. `HashSet` không tự loại phần tử trùng hay tái xác lập tính duy nhất sau khi dữ liệu trong phần tử thay đổi.
3. **Trường chỉ dùng trong `hashCode` đổi:** dù phép `equals` không đổi, mã băm vẫn đổi và có thể làm mất khả năng tra cứu. Nguy hiểm hơn, nếu hai đối tượng bằng nhau theo `equals` nhưng có giá trị khác ở trường chỉ dùng tính hash thì hợp đồng **đã sai ngay từ đầu**, không cần đợi thao tác sửa.
4. **Trường không dùng ở cả hai đổi:** về mặt thiết kế, nếu đúng là không ảnh hưởng gián tiếp tới phép so sánh và hash, `equals/hashCode` nên giữ nguyên. Đây thường là cách cho phép đổi trạng thái hiển thị mà khóa danh tính vẫn ổn định.

**Không suy luận rằng hễ đổi trường nào thì bắt buộc có một giá trị hash mới.** Hai trạng thái khác nhau có thể tình cờ cho cùng hash. Kết quả tra cứu trong bảng hash vì thế có thể trông như vẫn đúng ở một ví dụ nhỏ; điều đó không chứng minh việc sử dụng khóa mutable là an toàn.

## 3. Vì sao `HashMap` và `HashSet` đặc biệt nhạy cảm?

Khi đưa một khóa vào `HashMap`, cấu trúc này dùng hash **ở thời điểm chèn** để định vị entry trong cấu trúc lưu trữ nội bộ. Khi tra cứu, nó lại tính hash từ **khóa truy vấn tại thời điểm tìm** và so sánh các khóa ứng viên bằng quy tắc phù hợp.

Luồng tư duy rút gọn:

```text
Tại thời điểm put:
key.code = "A" -> hash("A") -> chọn vị trí lưu entry

Sau khi sửa key.code = "B":
map.get(key) hoặc map.get(new Key("B"))
    -> hash("B") -> tìm theo hash mới
    -> không bảo đảm đến được entry đã lưu theo hash("A")
```

Đây là mô hình giải thích, không phải cam kết về cấu trúc bucket cụ thể của mọi bản JDK. Quan trọng là **collection không nhận thông báo và không tự lập chỉ mục lại** khi bạn sửa một trường nằm trong đối tượng đã đưa vào collection.

Hệ quả thường gặp:

- `map.get(key)`, `map.containsKey(key)` hoặc `map.remove(key)` có thể thất bại ngay cả khi `key` chính là **tham chiếu cũ** từng dùng để `put`.
- `HashSet.contains(element)` hoặc `HashSet.remove(element)` có thể thất bại, dù duyệt `set` vẫn nhìn thấy phần tử đó.
- Nếu thêm đối tượng mới được xem là bằng phần tử đã bị sửa, một `HashSet` có thể tạm thời chứa nhiều phần tử hiện được `equals` xem là bằng nhau. Tập không chủ động rà soát lại mọi phần tử sau mỗi thao tác sửa.
- Kết quả có thể phụ thuộc giá trị hash, số lượng entry và lịch sử thay đổi nội bộ; vì vậy không thể dựa vào việc một thử nghiệm cụ thể vẫn `contains == true`.

**Đừng nhầm mutable *value* của `Map<K,V>` với mutable *key*.** Sửa đối tượng `V` được lưu dưới một khóa ổn định thông thường không ảnh hưởng cách `HashMap` tìm khóa. Nguy cơ đang xét là sửa dữ liệu dùng để xác định `equals/hashCode` của chính `K`.

## 4. Ví dụ Java 17: đổi hash làm khóa khó tìm, đổi `equals` tạo phần tử trùng logic

Tạo tệp độc lập `MutableEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MutableEqualityDemo {
    static final class CodeKey {
        private String code;

        CodeKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void changeCode(String next) {
            this.code = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof CodeKey other)) return false;
            return code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static final class StageKey {
        private String stage;

        StageKey(String stage) {
            this.stage = Objects.requireNonNull(stage);
        }

        void changeStage(String next) {
            this.stage = Objects.requireNonNull(next);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof StageKey other)) return false;
            return stage.equals(other.stage);
        }

        @Override
        public int hashCode() {
            return 1; // Cố ý giữ hash cố định để tách riêng tác động của equals.
        }
    }

    public static void main(String[] args) {
        CodeKey storedKey = new CodeKey("A");
        Map<CodeKey, String> map = new HashMap<>();
        map.put(storedKey, "payload");

        System.out.println("before A: " + map.get(new CodeKey("A")));
        storedKey.changeCode("B");
        System.out.println("same reference: " + (storedKey == storedKey));
        System.out.println("equal to new B: " + storedKey.equals(new CodeKey("B")));
        System.out.println("after B by same key: " + map.get(storedKey));
        System.out.println("after B by new key: " + map.get(new CodeKey("B")));
        System.out.println("map size: " + map.size());

        storedKey.changeCode("A");
        System.out.println("restored A: " + map.get(new CodeKey("A")));

        StageKey first = new StageKey("todo");
        StageKey second = new StageKey("done");
        Set<StageKey> set = new HashSet<>();
        set.add(first);
        set.add(second);
        System.out.println("set size before: " + set.size());

        second.changeStage("todo");
        System.out.println("same value now: " + first.equals(second));
        System.out.println("same hash now: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("set size after: " + set.size());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac MutableEqualityDemo.java
java MutableEqualityDemo
```

Kết quả khi chạy trên JDK 17 với `HashMap`/`HashSet` tiêu chuẩn:

```text
before A: payload
same reference: true
equal to new B: true
after B by same key: null
after B by new key: null
map size: 1
restored A: payload
set size before: 2
same value now: true
same hash now: true
set size after: 2
```

**Giải thích phần `CodeKey`:**

- Khi `put`, khóa có `code = "A"`. Với cặp giá trị này, `"A".hashCode()` là `65` còn `"B".hashCode()` là `66`. Sau khi sửa `code`, hash tính lại đổi sang `66`, trong khi entry được chèn theo hash cũ.
- `storedKey.equals(new CodeKey("B"))` đúng, bởi **giá trị mới** giống nhau. Nhưng `map.get(storedKey)` vẫn có thể trả `null`: `HashMap` không tự cập nhật vị trí của entry chỉ vì đối tượng khóa bị sửa.
- `map.size()` vẫn bằng `1`: entry không bị xóa. Việc khôi phục `code` thành `"A"` chỉ giúp ví dụ nhỏ này tìm lại được entry; **không nên coi đổi ngược trường là chiến lược sửa lỗi thực tế**.

**Giải thích phần `StageKey`:**

- `hashCode()` luôn trả `1`. Cách viết này hợp lệ về mặt quan hệ bắt buộc giữa `equals` và hash, nhưng phân bố hash rất kém, **chỉ dùng để minh họa**.
- Ban đầu `"todo"` khác `"done"`, nên hai phần tử đều được chèn vào `HashSet`.
- Sau khi đổi `second.stage` thành `"todo"`, `first.equals(second)` trở thành `true` mà kích thước tập vẫn là `2`. Việc hash không đổi **không** giải quyết nguy cơ thay đổi quan hệ bằng nhau.

Ví dụ này làm rõ hai lỗi thiết kế riêng biệt: **hash thay đổi làm tra cứu không đáng tin**, còn **quan hệ bằng nhau thay đổi có thể làm mất bất biến logic của tập**, ngay cả khi hash cố định.

## 5. Phân tích từng loại thay đổi một cách hệ thống

### 5.1. Thay đổi một trường tham gia cả `equals` lẫn `hashCode`

Giả sử `InvoiceKey.equals` và `InvoiceKey.hashCode` đều dùng `invoiceNumber`. Sau khi thêm đối tượng vào `HashMap`, sửa `invoiceNumber` có thể làm khóa không tìm được. Nếu một đối tượng khác trùng số hóa đơn mới được thêm, collection có thể chứa cấu trúc trái với kỳ vọng nghiệp vụ.

Cách tránh: dùng khóa số hóa đơn bất biến, hoặc tạo khóa mới và cập nhật mapping theo cách quản lý rõ ràng (xem phần 7).

### 5.2. Chỉ trường tham gia `equals` thay đổi

Ví dụ `equals` dựa trên `firstName` và `lastName`, nhưng `hashCode` luôn trả giá trị hằng. Hợp đồng `equals => cùng hash` được thỏa mãn, nhưng nếu một trường tên đổi, các đối tượng có thể chuyển từ bằng sang không bằng hoặc ngược lại. `HashSet` không tự duyệt để loại bản sao logic vừa xuất hiện.

Việc bỏ trường khỏi hash **không khiến trường đó có thể sửa tùy ý** khi instance đang nằm trong một tập phụ thuộc `equals`.

### 5.3. Chỉ trường tham gia `hashCode` thay đổi

Đây thường còn là lỗi thiết kế độc lập. Giả sử:

```java
// Minh họa logic sai, không phải chương trình chạy độc lập.
// equals chỉ so sánh id, nhưng hashCode lại lấy displayName.
return displayName.hashCode();
```

Hai đối tượng có cùng `id` có thể được `equals` coi là bằng nhau nhưng `displayName` khác nhau làm hai hash khác nhau: **vi phạm hợp đồng từ trước khi có mutation**.

Không phải mọi công thức hash đều cần nêu đúng các trường có tên giống ở `equals`, nhưng bắt buộc bảo đảm với mọi cặp bằng nhau thì kết quả hash giống nhau. Thực hành dễ duy trì nhất là lấy hash từ bộ trường ổn định xác định bình đẳng, hoặc một dạng biến đổi nhất quán của bộ trường đó.

### 5.4. Thay đổi một trường không tham gia `equals/hashCode`

Nếu `User` có `final long userId` là danh tính, còn `displayName` là thông tin hiển thị, có thể chủ động thiết kế `equals` và hash chỉ dựa vào `userId`. Khi tên đổi, quan hệ bằng nhau không đổi. Điều này an toàn **nếu** định nghĩa nghiệp vụ thực sự coi hai user có cùng `userId` là một thực thể và ID không bị tái sử dụng sai phạm vi.

Đây là khác biệt giữa **đối tượng có thể sửa trường hiển thị** và **khóa có thể sửa danh tính logic**.

## 6. Ví dụ an toàn: khóa bất biến, dữ liệu hiển thị có thể đổi

Tạo tệp `StableKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class StableKeyDemo {
    static final class User {
        private final long id;
        private String displayName;

        User(long id, String displayName) {
            this.id = id;
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof User other)) return false;
            return id == other.id;
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        User user = new User(17L, "An");
        Map<User, String> roles = new HashMap<>();
        roles.put(user, "reader");

        user.rename("Bình");

        System.out.println("hash stable: "
                + (user.hashCode() == new User(17L, "Khác").hashCode()));
        System.out.println("equals stable: "
                + user.equals(new User(17L, "Khác")));
        System.out.println("lookup: "
                + roles.get(new User(17L, "Khác")));
        System.out.println("map size: " + roles.size());
    }
}
```

```bash
javac StableKeyDemo.java
java StableKeyDemo
```

Stdout:

```text
hash stable: true
equals stable: true
lookup: reader
map size: 1
```

Đổi `displayName` không làm thay đổi giá trị `id` đã dùng trong cả `equals` và `hashCode`. Do đó tra cứu qua một instance `User` khác nhưng cùng ID vẫn hoạt động. Mẫu này chỉ đúng nếu **ID là khóa nghiệp vụ ổn định và duy nhất trong đúng miền dữ liệu**.

Nếu tính duy nhất là theo cặp `(tenantId, userId)`, thì cả hai giá trị đó phải bất biến và cùng tham gia quan hệ bằng nhau; dùng một `userId` đơn lẻ giữa hai tenant có thể gộp nhầm thực thể.

## 7. Làm thế nào để cập nhật dữ liệu khi khóa logic cần đổi?

Ưu tiên các cách xử lý sau, tùy mô hình:

**Cách A — thiết kế khóa bất biến ngay từ đầu.** Dùng kiểu `final` với trường `final`, `record` chứa các thành phần bất biến thực sự, hoặc lớp định danh như `UserId`, `OrderId`. Khi một giá trị của khóa thay đổi, tạo **đối tượng khóa mới**, không sửa khóa cũ đang được dùng trong collection.

```java
record AccountKey(String tenantId, long accountId) {}
```

Với hai component `String` và `long`, ví dụ này có ngữ nghĩa bất biến phù hợp. `record` mặc định cung cấp `equals/hashCode` dựa trên các component.

**Cách B — thay entry bằng thao tác rõ ràng khi cần đổi khóa.** Khi logic yêu cầu đổi khóa, hãy tháo mapping ở **khóa cũ còn nguyên giá trị**, rồi thêm dưới khóa mới:

```java
// Minh họa: map là Map<AccountKey, String> có sẵn;
// oldKey là AccountKey cũ chưa từng bị sửa;
// newKey là khóa mới, được tạo độc lập.
String value = map.remove(oldKey);
if (value != null) {
    map.put(newKey, value);
}
```

Đoạn này chỉ minh họa trình tự và giả sử `null` không phải giá trị hợp lệ của mapping. Nếu `null` được phép, `remove` trả `null` không phân biệt được entry không tồn tại với entry có giá trị `null`; cần thiết kế kiểm tra tồn tại riêng. Khi thay khóa, cũng phải xác định xử lý xung đột nếu `newKey` đã có entry. Trên dữ liệu đồng thời, việc thay cần thực hiện trong cơ chế đồng bộ hoặc giao dịch thích hợp.

**Cách C — tách khóa bất biến khỏi trạng thái thay đổi.** Ví dụ dùng `Map<Long, User>`, trong đó `long id` làm khóa, còn `User` là value có thể đổi tên, email, trạng thái. Những thay đổi trên `User` không ảnh hưởng cách tìm entry bằng `Long`. Nếu `User` được đưa đồng thời vào một `HashSet<User>` khác thì phải đánh giá riêng hợp đồng của set đó.

### Không “chữa” bằng các mẹo thiếu cơ sở

- Không đơn giản gọi lại `map.put(existingMutableKey, value)` sau khi sửa rồi tin rằng entry cũ đã biến mất. Tùy hash, thao tác này có thể làm thêm mapping khó quản lý.
- Không dựa vào `HashMap` tự rehash khi resize để tái định vị mọi khóa đã đổi; collection không có hợp đồng theo dõi mutation của khóa.
- Không chỉ cache hash để ép `hashCode` cố định nếu `equals` vẫn thay đổi theo trường khác; nguy cơ trùng logic trong tập vẫn tồn tại. Nếu cache không cập nhật nhất quán với giá trị bình đẳng, còn có thể vi phạm hợp đồng hash.
- Không sử dụng `System.identityHashCode` để thay thế tùy tiện: đó là hàm theo danh tính, không bảo đảm thỏa `equals` dựa trên giá trị.

## 8. Thay đổi gián tiếp qua đối tượng con, mảng và record

Một trường tham chiếu có thể được khai báo `final` nhưng **đối tượng được trỏ đến vẫn mutable**. Vì vậy, đánh giá tính ổn định phải nhìn vào **toàn bộ đồ thị dữ liệu mà `equals/hashCode` sử dụng**, không chỉ modifier của trường.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

// Minh họa: khai báo kiểu dùng Java 17+, không phải main chạy độc lập.
record GroupKey(List<String> tags) {}

List<String> names = new ArrayList<>(List.of("java"));
GroupKey key = new GroupKey(names);
int before = key.hashCode();
names.add("spring");
int after = key.hashCode();
```

`record` tự sinh `equals/hashCode` dựa trên component `tags`. `List.equals` và `List.hashCode` phụ thuộc nội dung danh sách. Dù tham chiếu `tags` trong record không thể gán lại, câu `names.add(...)` thay đổi nội dung danh sách mà record đang giữ; hash của `GroupKey` theo đó thay đổi trong ví dụ.

Nếu cần sao chép phòng vệ, compact constructor của record có thể dùng:

```java
record GroupKey(List<String> tags) {
    GroupKey {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` tạo/sử dụng danh sách không cho phép thao tác sửa qua API của nó và tách khỏi danh sách nguồn mutable thông thường. Tuy nhiên, nó là **sao chép nông**: nếu phần tử trong danh sách là đối tượng mutable và quy tắc `equals/hashCode` của phần tử phụ thuộc trạng thái, khóa vẫn có thể thay đổi nghĩa. Phải tiếp tục sao chép hoặc bất biến hóa các phần tử đó khi cần.

Tương tự, mảng là mutable. Nếu một lớp dùng `Arrays.equals(array1, array2)` và `Arrays.hashCode(array)` để biểu diễn giá trị của mảng, sửa phần tử mảng sẽ thay đổi so sánh/hash. Ngược lại, record có component là mảng dùng `equals/hashCode` mặc định của mảng theo tham chiếu, **không tự thực hiện so sánh sâu nội dung**; phải thiết kế tường minh nếu muốn bình đẳng theo phần tử.

## 9. Một số khác biệt về collection và concurrency

| Nơi sử dụng đối tượng | Tác động khi trường so sánh bị sửa |
| --- | --- |
| `HashMap<K,V>` với đối tượng làm **key** | Có nguy cơ không tìm được hoặc không gỡ được mapping do hash/equality thay đổi. |
| `HashSet<E>` | Có nguy cơ `contains/remove` thất bại hoặc chứa nhiều phần tử hiện bằng nhau. |
| `ArrayList<E>` | Không dùng hash để tìm phần tử; `contains`/ `indexOf` dùng so sánh theo thời điểm gọi. Kết quả có thể đổi sau mutation, nhưng không có bucket cũ cần truy cập. |
| `TreeMap`/`TreeSet` | Thứ tự và tính tương đương phụ thuộc `Comparator` hoặc `Comparable`. Sửa trường dùng bởi comparator trong lúc phần tử đang lưu cũng nguy hiểm, ngay cả khi `hashCode` không liên quan. |
| `IdentityHashMap` | Dùng danh tính tham chiếu (`==`) thay vì `equals` cho khóa; không phù hợp để thay `HashMap` một cách máy móc khi nghiệp vụ cần khóa giá trị. |

**Concurrency:** Nếu nhiều luồng cùng đọc và sửa những trường dùng bởi `equals/hashCode`, có thể phát sinh thêm data race hoặc quan sát trạng thái thiếu nhất quán, ngay cả trước khi xét đến collection. `HashMap`/`HashSet` thông thường không phải cấu trúc an toàn cho truy cập ghi đồng thời. Dùng đồng bộ, immutable snapshot hoặc cấu trúc đồng thời phù hợp **không làm cho việc sửa các trường hash/equality của khóa đang lưu trở thành hợp lệ**. Một `ConcurrentHashMap` cũng không chủ động cập nhật vị trí khóa khi chính đối tượng khóa bị sửa.

**Thay thế dữ liệu và nhất quán nghiệp vụ:** Nếu đối tượng được dùng làm khóa trong nhiều collection/caches, việc đổi trường định danh có thể làm các chỉ mục lệch nhau. Nên quản lý thay đổi danh tính ở tầng dữ liệu với khóa bất biến, tạo khóa mới, cập nhật các index/caches cần thiết, và có cơ chế giao dịch phù hợp khi thay đổi liên quan nhiều nơi.

## 10. Checklist thiết kế và kiểm thử

Trước khi dùng một kiểu đối tượng làm khóa trong `Map` hoặc phần tử của `Set` dựa trên hash, trả lời:

1. **Khóa bình đẳng là gì?** Chính xác những trường nào quyết định `equals`?
2. **Những trường đó có thể bị sửa không?** Kể cả sửa gián tiếp qua `List`, `Map`, mảng hoặc object con?
3. **Hash có dựa trên quy tắc bằng nhau không?** Với mọi cặp bằng nhau, mã băm có bằng nhau không?
4. **Đối tượng đã được đưa vào collection chưa?** Nếu rồi, có luồng xử lý nào thay đổi giá trị liên quan trước khi remove?
5. **Có thể dùng ID bất biến hoặc khóa tách riêng không?** Nếu display/status đổi, có cần đổi khóa logic thật không?
6. **Có kiểm thử trước và sau mutation không?** Thử cả tham chiếu cũ, một instance khác bằng theo giá trị, trường hợp trùng logic và thao tác thêm/xóa.
7. **Có phụ thuộc trạng thái ngoại vi không?** Một `equals` dựa trên đồng hồ, cơ sở dữ liệu, biến global hoặc cấu hình có thể làm kết quả thay đổi khi object không được sửa trực tiếp; cần tránh quy tắc như vậy cho khóa hash.
8. **Có rủi ro đồng thời không?** Cần bảo đảm dữ liệu tham gia `equals/hashCode` ổn định suốt thời gian nó được dùng trong index.

### Bài tập tự kiểm tra

- Một khóa có `equals` theo `id` nhưng `hashCode` theo `name`: nó sai thế nào ngay cả khi cả hai trường đều bất biến?
- Vì sao thay trường chỉ tham gia `equals` vẫn có thể gây sai kỳ vọng trong `HashSet` dù hash giữ nguyên?
- Vì sao `map.get(oldKey)` có thể trả `null` sau khi sửa một trường của **chính oldKey**?
- Việc thay tên hiển thị có an toàn nếu `equals/hashCode` chỉ dựa trên `final id` không? Cần giả định nghiệp vụ nào?
- Tại sao `final List<String>` chưa đủ để đảm bảo một khóa dựa trên nội dung danh sách là bất biến?
- Nếu một khóa buộc phải thay đổi, nên thao tác collection và dữ liệu theo thứ tự nào để tránh giữ entry lập chỉ mục theo giá trị cũ?

**Ghi nhớ:** Thay đổi trường tham gia `equals` có thể thay đổi **quan hệ bằng nhau**; thay đổi dữ liệu tham gia `hashCode` có thể thay đổi **cách tra cứu theo hash**. Các collection không tự cập nhật cấu trúc khi đối tượng bên trong bị sửa. Thiết kế đáng tin cậy nhất là **khóa logic bất biến**, hash nhất quán với `equals`, và tách những thuộc tính có thể đổi khỏi định danh dùng để tra cứu.