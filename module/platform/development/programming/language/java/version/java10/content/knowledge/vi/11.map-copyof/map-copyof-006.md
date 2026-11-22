# Rủi ro khi khóa thay đổi trạng thái dùng trong `equals()` và `hashCode()` — `Map.copyOf` (Java 10+)

## 1. Mục tiêu và vấn đề cốt lõi

`Map.copyOf(Map<? extends K, ? extends V>)` xuất hiện từ **Java 10** và vẫn được sử dụng trong Java hiện đại để tạo một **map unmodifiable** từ một map đầu vào. Với map kết quả, không thể dùng `put`, `remove`, `clear`, `replace` hay `compute` để chỉnh sửa các ánh xạ khóa–giá trị.

Tuy nhiên, **unmodifiable map không đồng nghĩa mọi đối tượng khóa và giá trị bên trong đều bất biến**. `Map.copyOf` không tự clone sâu (deep copy) từng khóa/giá trị. Nếu một **key (khóa)** là đối tượng mutable và các thuộc tính mutable đó tham gia `equals()` hoặc `hashCode()`, thay đổi chúng **sau khi đưa key vào map** có thể làm hành vi tra cứu trở nên không nhất quán.

Đây là rủi ro rất dễ bỏ qua:

```java
var mutableKey = new MutableKey("DRAFT");
var source = new java.util.HashMap<MutableKey, String>();
source.put(mutableKey, "item-1");

var snapshot = java.util.Map.copyOf(source);

// Ở nơi khác, code vẫn giữ tham chiếu mutableKey:
mutableKey.code = "DONE";
```

Hai dòng dùng `MutableKey` chỉ là minh họa; class đầy đủ nằm ở mục 10. Việc gán `mutableKey.code = "DONE"` **không gọi mutator trên map**, nên ràng buộc unmodifiable của `Map.copyOf` không ngăn được thao tác ấy. Nhưng nếu `equals()/hashCode()` của `MutableKey` dựa vào `code`, danh tính logic của key đã thay đổi trong khi key vẫn nằm trong map.

Bài học tập trung vào:

1. Hợp đồng `equals()`/`hashCode()` của key và vì sao trạng thái dùng trong hai phương thức cần ổn định.
2. Điều gì được `Map.copyOf` “đóng băng”, điều gì **không** được đóng băng.
3. Triệu chứng `get`/`containsKey` sai kỳ vọng, các key có thể trở nên tương đương, và `Map.equals()/hashCode()` thay đổi.
4. Cách thiết kế key bất biến, copy dữ liệu thành key bất biến **trước khi** gọi `Map.copyOf`.
5. Những bẫy với `record` chứa collection mutable, map có giá trị mutable, view và snapshot.

## 2. `Map.copyOf` thật sự bảo đảm điều gì?

```java
import java.util.HashMap;
import java.util.Map;

var source = new HashMap<String, Integer>();
source.put("A", 10);

var readOnly = Map.copyOf(source);
source.put("B", 20);

System.out.println(readOnly.size()); // 1
System.out.println(readOnly.get("A")); // 10
// readOnly.put("C", 30); // UnsupportedOperationException
```

Đây là đoạn minh họa các câu lệnh trong phương thức, không phải file Java độc lập.

Hợp đồng quan trọng:

- Kết quả là **unmodifiable**: các thao tác thêm, xóa và cập nhật ánh xạ qua map trả về đều không được hỗ trợ, kể cả khi đang giữ tham chiếu kiểu `Map<K,V>`.
- Việc thay đổi **cấu trúc map nguồn** sau khi tạo bản copy không được phản ánh vào snapshot được tạo từ nguồn mutable hợp lệ.
- `Map.copyOf` không chấp nhận key hoặc value `null`; nguồn `null` cũng không hợp lệ.
- Không có bảo đảm iteration order cố định cho kết quả; không dùng thứ tự duyệt để chứng minh điều gì về khóa.
- Nếu nguồn đã là map unmodifiable thích hợp, JDK có thể tái sử dụng instance; không dựa vào `source == copy` hoặc tên lớp implementation.
- **Các object làm key và value vẫn là các object được tham chiếu**, không bị biến thành immutable chỉ vì map không cho `put`.

Vì vậy, `Map.copyOf` bảo vệ **tập ánh xạ ở mức cấu trúc**, nhưng không tạo một “đóng băng sâu” cho toàn bộ đồ thị đối tượng.

## 3. Hợp đồng `equals()`/`hashCode()` của key

Với hai key `a` và `b`, quy tắc nền tảng của Java:

1. `equals()` phải tuân theo tính phản xạ, đối xứng, bắc cầu và tính nhất quán trong khi các thông tin dùng để so sánh chưa đổi.
2. Nếu `a.equals(b) == true` thì bắt buộc `a.hashCode() == b.hashCode()`.
3. Hai key có cùng `hashCode()` **không nhất thiết** phải `equals()`; va chạm hash là hợp lệ.
4. Nếu trạng thái được dùng trong `equals()` thay đổi, kết quả so sánh có thể đổi. Nếu trạng thái dùng trong `hashCode()` thay đổi, mã hash có thể đổi. Bản thân Java không cấm một object mutable có logic như vậy, nhưng **dùng nó làm khóa khi trạng thái còn biến đổi là không an toàn**.
5. Hợp đồng `Map` cảnh báo rằng **hành vi của map là không được quy định** khi một key bị thay đổi theo cách ảnh hưởng đến so sánh `equals()` trong khi key vẫn đang nằm trong map.

Ví dụ class key không an toàn:

```java
import java.util.Objects;

final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey
                && code.equals(((MutableKey) other).code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
```

Đây là một class hoàn chỉnh có thể đặt trong một file Java cùng ngữ cảnh thích hợp; nó **cố tình** dùng field mutable trong cả `equals()` và `hashCode()` nhằm minh họa rủi ro.

Nếu tạo `new MutableKey("DRAFT")` rồi đổi `code` thành `"DONE"`, nó sẽ **không còn bằng** một key mới có code `"DRAFT"`, mà sẽ bằng một key mới có code `"DONE"`. Mã hash cũng thay đổi tương ứng. Điều này đặc biệt nguy hiểm khi object nằm trong map dựa trên khóa băm.

## 4. Vì sao key đổi `hashCode()` có thể làm tra cứu sai?

Các cấu trúc hash-based thường dùng `hashCode()` và `equals()` để xác định vị trí hoặc so khớp khóa. Với `HashMap`, mã hash của key được sử dụng để xác định nơi lưu entry khi chèn. Nếu key sau đó đổi các trường ảnh hưởng đến hash, những lần `get`/`containsKey` tiếp theo có thể tìm theo một mã hash **khác mã hash khi lưu**.

Với `Map.copyOf`, Javadoc cũng nói rõ: nếu các key/value chứa bên trong mutable và bị thay đổi, map có thể **hành xử không nhất quán** hoặc nội dung có vẻ thay đổi.

```java
var key = new MutableKey("DRAFT");
var source = new java.util.HashMap<MutableKey, String>();
source.put(key, "task");
source.put(new MutableKey("OTHER"), "other");

var snapshot = java.util.Map.copyOf(source);
System.out.println(snapshot.get(new MutableKey("DRAFT"))); // task

key.code = "DONE"; // Thay trạng thái tham gia equals() và hashCode().

// KHÔNG dựa vào kết quả của các phép tra cứu sau:
// snapshot.get(new MutableKey("DRAFT"))
// snapshot.get(new MutableKey("DONE"))
// snapshot.containsKey(new MutableKey("DONE"))
```

**Điểm cần cực kỳ chính xác:** Không tuyên bố `Map.copyOf` **luôn** trả `null` khi tìm bằng key cũ hoặc key mới sau mutation. Kết quả khi vi phạm điều kiện ổn định của key **không có hợp đồng ổn định**; có thể khác theo implementation, số entry và bản JDK. Kiến thức cần ghi nhớ không phải “câu `get` cụ thể nào trả null” mà là **không được thay đổi trạng thái ảnh hưởng đến `equals()` trong khi object đang là key**.

Ngoài mất khả năng tra cứu, có thể gặp:

- `containsKey` trả kết quả không khớp với trực giác khi duyệt `keySet()`.
- Hai key trước đó khác nhau có thể trở nên `equals() == true` sau thay đổi, làm logic “khóa là duy nhất” trở nên khó hiểu.
- Kết quả `Map.equals(otherMap)` hoặc `Map.hashCode()` có thể thay đổi do trạng thái key/value thay đổi, mặc dù không ai gọi `put` hay `remove` lên snapshot.
- Một map bị dùng làm key của map khác, hoặc trong cache/hệ thống so sánh, có thể gây vấn đề dây chuyền nếu mã hash của nó bị thay đổi.

Không sử dụng các triệu chứng không xác định này làm “tính năng” để cập nhật key; chúng là lỗi thiết kế.

## 5. Phân biệt sửa biến tham chiếu với sửa trạng thái của key

```java
var key = new MutableKey("A");
var map = java.util.Map.copyOf(
        java.util.Map.of(key, "value"));

key = new MutableKey("B"); // Chỉ gán biến local tới object KHÁC.
```

Với đoạn trên, việc **gán lại biến `key`** không làm đổi trạng thái của object `MutableKey("A")` đã được map giữ. Nếu không còn tham chiếu mutable nào khác tới object đó và không có mutation, riêng việc gán biến không gây rủi ro về hash.

Ngược lại:

```java
var key = new MutableKey("A");
var map = java.util.Map.copyOf(
        java.util.Map.of(key, "value"));

key.code = "B"; // Sửa TRỰC TIẾP object đang được map tham chiếu.
```

Đây mới là vấn đề. Dù biến `key` là `final`, trường `code` vẫn có thể đổi:

```java
final var key = new MutableKey("A");
// key = new MutableKey("B"); // Lỗi: biến final không được gán lại.
key.code = "B";              // Vẫn có thể sửa field của object mutable.
```

**`final` trên biến không tạo deep immutability cho object.** Tương tự, `Map.copyOf` không tự gắn `final` vào những field của key.

## 6. Tại sao ngay cả map chỉ đọc cũng có thể bị ảnh hưởng?

Có ba tầng khác nhau:

| Tầng | `Map.copyOf` có bảo vệ không? | Điều cần nhớ |
| --- | --- | --- |
| Thêm/xóa/cập nhật cặp key–value qua API map | Có, mutator ném `UnsupportedOperationException` | `put`, `remove`, `replace` không dùng được |
| Cấu trúc map nguồn mutable bị sửa sau khi copy | Có, bản copy không theo thay đổi cấu trúc của nguồn | Đây là snapshot, không phải live view |
| Trạng thái nội bộ của key/value mutable được tham chiếu | **Không** | Có thể ảnh hưởng lookup, `equals`, `hashCode`, dữ liệu nhìn thấy |

Một đối tượng `MutableKey` được sử dụng đồng thời trong map nguồn và map kết quả vẫn chỉ là **một object được nhiều nơi tham chiếu**. Sửa nó qua bất kỳ tham chiếu nào đều có thể ảnh hưởng đến cả hai map, tùy cách các map dùng equals/hash.

Cũng vì vậy, copy map một lần nữa **không phải một deep-copy fix**:

```java
var snapshot1 = java.util.Map.copyOf(source);
var snapshot2 = java.util.Map.copyOf(snapshot1);
```

Nếu bên trong chứa cùng một key mutable, việc tạo `snapshot2` không bảo đảm key trở thành immutable; implementation còn có thể trả lại cùng instance map khi map đầu vào đã là unmodifiable phù hợp.

## 7. Thiết kế key an toàn: biến trạng thái xác định danh tính thành bất biến

### 7.1. Dùng key có dữ liệu bất biến

Nếu một key chỉ cần mã định danh, dùng `String` hoặc một kiểu có các thành phần immutable:

```java
var source = new java.util.HashMap<String, String>();
source.put("ORDER-001", "pending");

var snapshot = java.util.Map.copyOf(source);
System.out.println(snapshot.get("ORDER-001")); // pending
```

`String` immutable, nên không thể đổi nội dung đã dùng cho `equals()/hashCode()` sau khi key được chèn.

Trong Java 17+, `record` là cách gọn để định nghĩa key mang dữ liệu không thay đổi:

```java
record OrderId(String value) {
    OrderId {
        java.util.Objects.requireNonNull(value);
    }
}

var source = new java.util.HashMap<OrderId, String>();
source.put(new OrderId("ORDER-001"), "pending");
var snapshot = java.util.Map.copyOf(source);

System.out.println(snapshot.get(new OrderId("ORDER-001"))); // pending
```

`record` tự cung cấp `equals()/hashCode()` theo thành phần, và thành phần `String` không đổi. **`record` là tính năng chuẩn từ Java 16**, không thuộc cú pháp nguyên bản Java 10; dùng Java 17+ cho ví dụ này.

Nếu dự án cố định Java 10, có thể dùng một `final class` với `private final String id` và các phương thức `equals()/hashCode()` dựa trên field bất biến. Tính an toàn đến từ thiết kế key, **không** phụ thuộc có dùng `record` hay không.

### 7.2. Không dùng đối tượng domain mutable làm key chỉ vì tiện

Ví dụ một đối tượng `Order` có thể thay đổi trạng thái từ `DRAFT` sang `DONE`. Nếu `equals()/hashCode()` được tính từ `status`, đưa toàn bộ `Order` làm key là rủi ro. Nên tách danh tính ổn định, ví dụ `OrderId`:

```java
Map<OrderId, OrderSummary> snapshots = /* tập dữ liệu tạo trước */;
```

Dòng này minh họa chữ ký dữ liệu; `OrderId` và `OrderSummary` là các kiểu nghiệp vụ giả định, không phải class trong Java SE hay đoạn code độc lập. Ý tưởng là key chỉ chứa các trường thể hiện **danh tính ổn định**, còn các trạng thái thường thay đổi thuộc về value.

Một cách khác, nếu đối tượng mutable có `equals()/hashCode()` chỉ dựa vào **ID bất biến**, thay đổi trường không liên quan sẽ không làm thay đổi danh tính key. Tuy nhiên, khi thiết kế API dài hạn, key value object bất biến thường dễ kiểm tra và bảo trì hơn.

### 7.3. Defensive copy **key** trước khi `Map.copyOf`

Không đủ nếu chỉ viết `Map.copyOf(source)` rồi kỳ vọng key được sao chép sâu. Nếu nguồn có key mutable nhưng muốn snapshot an toàn, **tạo key mới loại immutable** trước:

```java
record StableId(String code) { }

var stableWorking = new java.util.HashMap<StableId, String>();

for (var entry : source.entrySet()) {
    var stableKey = new StableId(entry.getKey().code);

    if (stableWorking.putIfAbsent(stableKey, entry.getValue()) != null) {
        throw new IllegalArgumentException("Duplicate logical key");
    }
}

var safeSnapshot = java.util.Map.copyOf(stableWorking);
```

Đoạn này cần đặt cùng ngữ cảnh có `source` là map chứa `MutableKey` của ví dụ trước và không có giá trị `null`. Nó dùng Java 17+ vì `record`. Cần bảo đảm không có tiến trình khác sửa khóa hoặc nguồn trong lúc chuyển đổi; việc đọc key để tạo snapshot nên được thực hiện trong phạm vi đồng bộ/ownership phù hợp.

Nếu nhiều key mutable có cùng mã sau khi chuyển sang `StableId`, đoạn trên cố ý phát hiện xung đột danh tính. Không âm thầm ghi đè một value lên value khác nếu nghiệp vụ yêu cầu khóa duy nhất.

## 8. Cẩn thận: `record` không tự bảo đảm deep immutability

Một `record` có thành phần là collection mutable vẫn có thể gặp **chính rủi ro như khóa mutable**, vì `equals()/hashCode()` sinh ra từ các thành phần:

```java
record GroupKey(java.util.List<String> tags) { }

var tags = new java.util.ArrayList<>(
        java.util.List.of("team-A"));

var key = new GroupKey(tags);
int beforeHash = key.hashCode();

tags.add("team-B"); // Sửa nội dung List đang nằm bên trong record.
System.out.println(beforeHash != key.hashCode()); // true với dữ liệu này
```

Cấu trúc record là final ở cấp tham chiếu tới list nhưng **nội dung list vẫn mutable**. Nếu `GroupKey` đang nằm trong map, thay đổi list có thể làm `equals()/hashCode()` của key thay đổi.

Một thiết kế tốt hơn:

```java
record GroupKey(java.util.List<String> tags) {
    GroupKey {
        tags = java.util.List.copyOf(tags);
    }
}
```

Ở đây compact constructor sao chép list đầu vào thành một list unmodifiable. Nếu **các phần tử** của list cũng là immutable (ví dụ `String`), `GroupKey` có danh tính ổn định hơn. Nếu list chứa object phần tử mutable dùng trong `equals()/hashCode()`, vẫn phải phòng vệ **ở cấp phần tử**, vì `List.copyOf` chỉ shallow copy.

Điều này nhắc lại nguyên tắc: **tính bất biến phải được bảo đảm cho toàn bộ trạng thái tham gia xác định key**, không chỉ tại lớp vỏ.

## 9. Giá trị mutable cũng là rủi ro khác cần biết

`Map.copyOf` không deep copy **value**.

```java
final class MutableValue {
    String status;

    MutableValue(String status) {
        this.status = status;
    }
}

var value = new MutableValue("pending");
var snapshot = java.util.Map.copyOf(
        java.util.Map.of("ORDER-001", value));

value.status = "done";
System.out.println(snapshot.get("ORDER-001").status); // done
```

Đây là class cùng đoạn code minh họa phải bố trí trong ngữ cảnh Java hợp lệ. Nó chứng minh **trạng thái object value vẫn có thể thay đổi**, dù không có `snapshot.put(...)`.

Nếu value có `equals()/hashCode()` dựa vào trạng thái mutable, `Map.equals()/hashCode()` cũng có thể thay đổi theo giá trị đó. Nhưng với lỗi “không tìm thấy key”, cần kiểm tra **key** trước tiên.

Giải pháp tùy nghiệp vụ:

- Dùng value immutable khi cần snapshot ổn định từ đầu đến cuối.
- Tạo defensive copy cho value nếu caller phải được cách ly khỏi object nguồn.
- Nếu cố ý truyền object mutable, tài liệu hóa rõ giới hạn của “unmodifiable map”: chỉ cấu trúc ánh xạ được bảo vệ, không phải toàn bộ trạng thái phần tử.

## 10. Ví dụ Java 17+ hoàn chỉnh: key mutable, key ổn định, shallow value và record

Tạo tệp **`MapCopyOfMutableKeyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class MapCopyOfMutableKeyDemo {
    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    record StableKey(String code) {
        StableKey {
            Objects.requireNonNull(code);
        }
    }

    record ShallowKey(List<String> tags) { }

    static final class MutableValue {
        String status;

        MutableValue(String status) {
            this.status = status;
        }
    }

    public static void main(String[] args) {
        var mutableKey = new MutableKey("DRAFT");
        var source = new HashMap<MutableKey, String>();
        source.put(mutableKey, "item-1");
        source.put(new MutableKey("OTHER"), "item-2");

        var snapshot = Map.copyOf(source);
        System.out.println("snapshot size=" + snapshot.size());
        System.out.println("before equals=" + mutableKey.equals(new MutableKey("DRAFT")));
        System.out.println("before lookup=" + snapshot.get(new MutableKey("DRAFT")));

        int originalHash = mutableKey.hashCode();
        mutableKey.code = "DONE";
        System.out.println("hash changed=" + (originalHash != mutableKey.hashCode()));
        System.out.println("old identity equals=" + mutableKey.equals(new MutableKey("DRAFT")));
        System.out.println("new identity equals=" + mutableKey.equals(new MutableKey("DONE")));
        System.out.println("same object stored=" + snapshot.keySet().stream().anyMatch(k -> k == mutableKey));

        try {
            snapshot.put(new MutableKey("NEW"), "item-3");
        } catch (UnsupportedOperationException ex) {
            System.out.println("put blocked=UnsupportedOperationException");
        }

        var sourceWithStableKeys = new HashMap<StableKey, String>();
        sourceWithStableKeys.put(new StableKey("DRAFT"), "item-1");
        var stableSnapshot = Map.copyOf(sourceWithStableKeys);
        sourceWithStableKeys.put(new StableKey("NEW"), "item-2");
        System.out.println("stable lookup=" + stableSnapshot.get(new StableKey("DRAFT")));
        System.out.println("stable size=" + stableSnapshot.size());

        var mutableValue = new MutableValue("pending");
        var valuesSnapshot = Map.copyOf(Map.of(new StableKey("ORDER"), mutableValue));
        mutableValue.status = "done";
        System.out.println("value status=" + valuesSnapshot.get(new StableKey("ORDER")).status);

        var mutableList = new ArrayList<>(List.of("a"));
        var shallowRecord = new ShallowKey(mutableList);
        int beforeRecordHash = shallowRecord.hashCode();
        mutableList.add("b");
        System.out.println("record hash changed=" + (beforeRecordHash != shallowRecord.hashCode()));

        try {
            Map.copyOf(Map.of("x", "ok", "y", "good"));
            System.out.println("null-free copy=ok");
        } catch (RuntimeException ex) {
            System.out.println("unexpected error");
        }
    }
}
```

Biên dịch theo mức ngôn ngữ Java 17 (vì có `record` và pattern matching cho `instanceof`):

```bash
javac --release 17 MapCopyOfMutableKeyDemo.java
java MapCopyOfMutableKeyDemo
```

Kết quả stdout **đã kiểm chứng**:

```text
snapshot size=2
before equals=true
before lookup=item-1
hash changed=true
old identity equals=false
new identity equals=true
same object stored=true
put blocked=UnsupportedOperationException
stable lookup=item-1
stable size=1
value status=done
record hash changed=true
null-free copy=ok
```

Giải thích từng nhóm:

1. `snapshot size=2` và `before lookup=item-1` cho thấy việc tạo snapshot với key ở trạng thái đầu tiên hoạt động như mong đợi.
2. Sau khi `mutableKey.code = "DONE"`, cả `equals()` và `hashCode()` của key đã thay đổi. `snapshot` vẫn giữ **cùng object** key này: `same object stored=true`. **Chương trình cố tình không khẳng định đầu ra của `get` sau mutation**, vì trạng thái key đã vi phạm điều kiện ổn định của khóa và hành vi tra cứu không được bảo đảm.
3. `snapshot.put(...)` bị chặn bằng `UnsupportedOperationException`, nhưng điều đó không ngăn việc sửa `mutableKey.code` từ ngoài map.
4. `StableKey` dùng `record` với thành phần `String` immutable; việc thay đổi `sourceWithStableKeys` sau khi copy không làm thay đổi snapshot cấu trúc. Một key mới có cùng mã tra cứu được value cũ.
5. `MutableValue` thay đổi trạng thái từ `pending` sang `done` và điều đó vẫn nhìn thấy qua snapshot.
6. `ShallowKey` là record chứa một `ArrayList` mutable; sửa list làm mã hash của record thay đổi.
7. Dòng cuối chỉ xác nhận một map không chứa `null` được copy thành công.

Ví dụ không cần thư viện ngoài Java SE. Hành vi unmodifiable của `Map.copyOf` có từ Java 10; các cú pháp bổ sung trong chương trình dùng Java 17 vẫn còn hợp lệ trên JDK hiện đại.

## 11. `Map.copyOf` và `Collections.unmodifiableMap`: cùng chỉ đọc, khác nguồn

So sánh:

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 1);

var snapshot = java.util.Map.copyOf(source);
var view = java.util.Collections.unmodifiableMap(source);

source.put("B", 2);

System.out.println(snapshot.size()); // 1
System.out.println(view.size());     // 2
```

- `snapshot` là kết quả unmodifiable **tách khỏi thay đổi cấu trúc của source**.
- `view` là wrapper unmodifiable **phản ánh các thay đổi được thực hiện qua tham chiếu nguồn**.
- **Cả hai đều không deep-copy key hoặc value**, và cả hai đều không cho mutator qua biến kết quả.
- Nếu key bản thân mutable, vấn đề key đổi trạng thái ảnh hưởng `equals()/hashCode()` vẫn cần được giải quyết độc lập. Chuyển từ `Map.copyOf` sang `Collections.unmodifiableMap` **không phải giải pháp**.

`Map.of(...)` cũng tạo unmodifiable map nhưng không bảo vệ trạng thái mutable của key/value bên trong.

## 12. Những tình huống và sai lầm thường gặp

### 12.1. Đặt toàn bộ entity mutable làm key

Một `Customer` hoặc `Order` có các field trạng thái thay đổi. Nếu `equals()/hashCode()` dựa vào trạng thái ấy, không nên dùng nguyên object làm key trong cache hoặc map snapshot. Hãy dùng ID immutable hoặc value object riêng.

### 12.2. Cho rằng `Map.copyOf` copy cả các object key

Sai. Nó tạo một map không cho chỉnh sửa cấu trúc, **không** có nghĩa tự deep-clone key/value. Sửa key qua tham chiếu gốc vẫn làm trạng thái của object key thay đổi.

### 12.3. Nghĩ `final` hoặc `record` luôn đủ

`final var key` chỉ cấm gán lại biến. `record` với field tham chiếu mutable không tự sao chép sâu. Cần bất biến ở những trường dùng xác định danh tính.

### 12.4. Sửa key trước rồi “cứ get lại bằng key mới”

Không an toàn. Khi một key đã đổi thông tin tham gia `equals()/hashCode()` trong lúc nằm trong map, **không có hợp đồng bảo đảm** `get(newKey)` hay `remove(newKey)` sẽ sửa được vấn đề. Đừng dùng các phép tra cứu sau mutation làm chiến lược di chuyển key.

Cách đúng là **không sửa key khi còn nằm trong map**. Nếu danh tính phải đổi, hãy thiết kế thao tác ở lớp quản lý dữ liệu: tạo **một key immutable mới** rồi tạo một map phiên bản mới hoặc sửa map mutable trong phạm vi kiểm soát, với thao tác loại bỏ key cũ **trước khi** thay đổi trạng thái cần thiết; sau đó xuất bản `Map.copyOf` mới.

### 12.5. Làm key từ danh sách và tưởng có `record` là bất biến

Nếu list mutable tham gia so sánh hoặc mã hash của record, caller sửa list sẽ gây thay đổi key. Sao chép vào `List.copyOf` ngay trong constructor của key và chỉ chứa phần tử immutable là một hướng tốt.

### 12.6. Muốn map snapshot giữ cả trạng thái value ổn định nhưng chỉ gọi `copyOf`

Không đủ. Nếu cần snapshot dữ liệu ở mọi cấp, phải defensive-copy cả value và các object con thích hợp; key ổn định chỉ giải quyết phần tra cứu.

### 12.7. Dùng map đã hỏng để làm nguồn tái tạo mà không kiểm tra

Nếu key đã bị sửa khi đang nằm trong `HashMap`, bản thân cấu trúc source có thể đã không nhất quán. Đừng giả định chỉ cần `Map.copyOf(source)` là tự sửa mọi lỗi. Tốt hơn là tái tạo từ nguồn dữ liệu có danh tính rõ ràng và kiểm tra xung đột key.

### 12.8. Dựa vào thứ tự duyệt hoặc implementation class

`Map.copyOf` không có hợp đồng thứ tự iteration cố định. Các ví dụ có nhiều key dùng `size()`, `get()` hoặc kiểm tra theo thuộc tính thay vì in toàn bộ map và giả định thứ tự luôn như nhau.

## 13. Checklist thiết kế và code review

Trước khi dùng `Map.copyOf` để xuất bản bản đồ dữ liệu chỉ đọc, hãy trả lời:

- [ ] **Key dùng gì để `equals()/hashCode()`?** Các trường đó có thể đổi trong suốt thời gian key tồn tại trong map không?
- [ ] **Có tham chiếu bên ngoài tới key mutable không?** `Map.copyOf` không tước quyền sửa object key ở nơi khác.
- [ ] **Key có thực sự immutable không?** Kiểm tra cả collection/array/object lồng trong `record` hoặc final class.
- [ ] **Giá trị (value) có mutable không?** Nếu cần snapshot ổn định hoàn toàn, đã xử lý defensive copy phần value chưa?
- [ ] **Có khả năng trùng danh tính logic khi chuyển từ entity sang key ID không?** Cần policy phát hiện/merge rõ ràng thay vì ghi đè âm thầm.
- [ ] **Có null key/value không?** `Map.copyOf` không cho phép `null`.
- [ ] **Cấu trúc nguồn có đang bị sửa đồng thời không?** Cần đồng bộ hóa/ownership phù hợp khi xây dựng snapshot.
- [ ] **Đã test theo vòng đời key chưa?** Tạo map → thao tác bên ngoài → tra cứu bằng một key tương đương; tốt nhất bảo đảm key không thể thay đổi, không cố chấp nhận hành vi không xác định.
- [ ] **Không phụ thuộc iteration order hoặc implementation của immutable map?** Chỉ dựa vào hợp đồng Map.
- [ ] **Map có thật sự cần unmodifiable API không?** Nếu cần thay đổi ánh xạ, hãy dùng map mutable để xây dựng dữ liệu, rồi gọi `Map.copyOf` tại thời điểm xuất bản.

Quy tắc thực dụng: **ổn định danh tính trước, chốt bản snapshot sau**.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `Map.copyOf(map)` có làm object key đang giữ ở biến ngoài trở nên bất biến không?

**Đáp án:** Không. Nó không deep-copy hay đóng băng key. Nếu caller còn tham chiếu đến key mutable, caller có thể sửa object ấy.

**Câu 2.** Một key có `equals()/hashCode()` dựa vào field `status`. Nếu sửa `status` sau khi key đã nằm trong map, có thể bảo đảm `get` bằng key mới sẽ hoạt động không?

**Đáp án:** Không. Hợp đồng `Map` không quy định hành vi của map khi key thay đổi theo cách ảnh hưởng đến `equals()` trong khi đang là khóa. Kết quả lookup sau đó không được dựa vào.

**Câu 3.** Nếu `key` là `final`, `key.code = "NEW"` có bị Java tự cấm không?

**Đáp án:** Không nếu `code` là field mutable và quyền truy cập cho phép. `final` trên biến chỉ cấm gán lại tham chiếu `key`.

**Câu 4.** Dùng `record Key(List<String> parts)` có đảm bảo key bất biến không?

**Đáp án:** Không. Bên ngoài vẫn có thể sửa list gốc, làm nội dung và mã hash của record đổi. Có thể dùng compact constructor `parts = List.copyOf(parts);` và bảo đảm phần tử cũng immutable.

**Câu 5.** `Map.copyOf` có bảo đảm không thấy các lần `source.put(...)` tiếp theo trên một source `HashMap` mutable hợp lệ không?

**Đáp án:** Có, nó tạo snapshot cấu trúc unmodifiable. Nhưng nếu object key/value được chia sẻ và mutable, trạng thái bên trong vẫn có thể thay đổi.

**Câu 6.** Vì sao `Map.copyOf(source)` không thể tự “sửa” một `HashMap` đã chứa key bị sửa gây hỏng logic hash?

**Đáp án:** `copyOf` không có trách nhiệm khôi phục danh tính logic, không deep-clone key và không xác minh lại toàn bộ nguồn nghiệp vụ. Tạo dữ liệu an toàn từ key immutable, kiểm tra xung đột trước khi xuất bản.

**Câu 7.** Khi cần cập nhật ID của một entity trong map unmodifiable, nên làm gì?

**Đáp án:** Không mutate object key hiện có. Tạo key ID immutable mới, xây dựng một map mutable/phiên bản mới với ánh xạ đúng rồi xuất bản một `Map.copyOf` mới.

**Câu 8.** Nếu value mutable thay đổi sau `Map.copyOf`, có thể đọc thấy trạng thái mới qua snapshot không?

**Đáp án:** Có thể; bản copy giữ tham chiếu value. Đây là lý do snapshot cấu trúc không tương đương deep immutable snapshot.

## 15. Tài liệu tham khảo chính thức còn hiệu lực

- [Java SE — `Map.copyOf` và Unmodifiable Maps](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): hợp đồng copy và hạn chế mutator.
- [Java SE — `Map`, lưu ý về mutable keys](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): cảnh báo hành vi không xác định nếu key đổi theo cách ảnh hưởng `equals()`, và các đặc tính của unmodifiable maps.
- [Java SE — `HashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html): các thao tác hash-based của map.
- [Java SE — `Object.equals` và `Object.hashCode`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html): hợp đồng về so sánh và mã hash.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): snapshot khác view, và ảnh hưởng của phần tử mutable trong collection unmodifiable.
- [OpenJDK — JEP 395: Records](https://openjdk.org/jeps/395): cú pháp record được chuẩn hóa từ Java 16; record không tự deep-copy thành phần mutable.
