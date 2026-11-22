# Rủi ro sửa trường tham gia equals hoặc hashCode sau khi thêm

Một khóa có thể vẫn nằm trong `HashMap` nhưng `get` bằng chính tham chiếu đó lại không tìm thấy. Một `HashSet` có thể giữ hai đối tượng vốn khác nhau lúc thêm, rồi sau một lần sửa trường, hai đối tượng ấy trở nên bằng nhau mà `size()` vẫn là `2`. Cả hai hiện tượng đều có thể bắt nguồn từ việc thay đổi dữ liệu dùng để xác định khóa hoặc phần tử sau khi đưa vào tập hợp.

Trong chủ đề **Java core - collection**, nhóm **Bằng nhau và băm**, bài này giải thích vì sao việc thay đổi ấy nguy hiểm và cách thiết kế để tránh nó. Mục tiêu không phải học thuộc một kết quả lỗi cụ thể của `HashMap`. Mục tiêu là giữ cho ý nghĩa của khóa ổn định trong suốt thời gian nó được dùng làm khóa.

## 1. Mô hình cần nắm trước: đối tượng thay đổi, tập hợp không tự cập nhật chỉ mục

Hãy hình dung một danh mục được lập theo mã hồ sơ. Khi đưa hồ sơ mã `A` vào danh mục, hệ thống chọn vị trí tìm kiếm dựa trên mã `A`. Nếu sau đó một người cầm trực tiếp hồ sơ và sửa mã trên hồ sơ thành `B`, việc sửa giấy không đồng nghĩa với việc hệ thống đã thực hiện thao tác chuyển danh mục từ `A` sang `B`.

Tương tự, `HashMap` tổ chức các mục dựa trên thông tin từ khóa lúc thêm. Việc gọi một phương thức như `key.setId(2)` chỉ sửa đối tượng khóa. Nó không phải lời gọi đổi khóa của `Map` và không thông báo cho bảng băm rằng phải lập lại cấu trúc tìm kiếm.

Có ba khái niệm cần tách rõ:

| Khái niệm | Câu hỏi mà nó trả lời |
|---|---|
| Đồng nhất tham chiếu, `a == b` | Hai biến có cùng trỏ đến một đối tượng không? |
| Bằng nhau về giá trị, `a.equals(b)` | Hai đối tượng có đại diện cho cùng một khóa hoặc giá trị theo mô hình đã chọn không? |
| Mã băm, `a.hashCode()` | Thông tin số nào được dùng để hỗ trợ tổ chức và thu hẹp tìm kiếm? |

Một tham chiếu không thay đổi không kéo theo trạng thái của đối tượng không thay đổi. Và trạng thái thay đổi có thể làm kết quả `equals` hoặc `hashCode` thay đổi.

**Nguyên tắc thực hành:** trong thời gian một đối tượng đang làm khóa của `HashMap` hoặc phần tử của `HashSet`, hãy giữ ổn định những dữ liệu quyết định quan hệ bằng nhau và mã băm của nó.

Tài liệu `Map` và `Set` đều cảnh báo về trường hợp thay đổi đối tượng trong khi nó đang được lưu, nếu thay đổi đó ảnh hưởng đến việc so sánh bằng nhau. Khi vi phạm điều kiện ấy, hành vi của tập hợp không được đặc tả bảo đảm. Vì vậy, các biểu hiện lỗi ở bài này là để thấy cơ chế và tránh thiết kế sai; chúng không phải kết quả mà mọi triển khai phải tạo ra. [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 2. Vì sao đây là vấn đề về thời gian, không chỉ là viết đúng hai phương thức

Một lớp thường được kiểm tra bằng các quy tắc:

- `equals` phải phản xạ, đối xứng, bắc cầu và nhất quán khi dữ liệu tham gia so sánh không đổi.
- Hai đối tượng bằng nhau phải có cùng mã băm.
- Hai đối tượng khác nhau vẫn có thể có cùng mã băm.
- Các lần gọi `hashCode` phải nhất quán khi dữ liệu dùng trong `equals` không bị thay đổi.

Quy tắc cuối có điều kiện: dữ liệu liên quan không bị thay đổi. Nó không nói rằng mã băm của mọi đối tượng bắt buộc bất biến từ lúc sinh ra đến lúc bị thu gom. [Object.equals và Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

Ví dụ, một lớp dùng `id` cho cả `equals` và `hashCode` có thể có:

- Tại thời điểm thứ nhất: `id = 1`; quan hệ bằng nhau và mã băm đều dựa trên `1`.
- Tại thời điểm thứ hai: `id = 2`; cả hai đều chuyển sang dựa trên `2`.

Hai phương thức có thể vẫn phù hợp với nhau tại từng thời điểm. Tuy nhiên, nếu giữa hai thời điểm ấy đối tượng đang là khóa trong bảng băm, việc sử dụng khóa vẫn có vấn đề. Cấu trúc lưu trữ đã được xây dựng theo trạng thái trước đó.

Cần phân biệt hai loại lỗi:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Sai hợp đồng giữa `equals` và `hashCode` | Hai đối tượng bằng nhau nhưng trả mã băm khác nhau ngay tại cùng một trạng thái | Sửa thiết kế và cài đặt hai phương thức |
| Sửa dữ liệu xác định khóa khi khóa đang được lưu | Ban đầu `id = 1`, thêm vào map, rồi sửa `id = 2` | Giữ khóa ổn định hoặc thực hiện quy trình đổi khóa có kiểm soát |

Sửa đúng hai phương thức không tự giải quyết được loại lỗi thứ hai. Để dùng an toàn trong bảng băm, cần thêm một quyết định thiết kế về **vòng đời của khóa**.

## 3. Cơ chế: thông tin khi thêm khác thông tin khi tìm

Giả sử một khóa có `hashCode()` trả về trực tiếp `id`. Một mô hình đơn giản của thao tác thêm là:

1. Lấy mã băm từ khóa hiện tại.
2. Dùng mã băm để xác định khu vực tìm kiếm.
3. Kiểm tra các khóa ứng viên để xem đã có khóa bằng nhau hay chưa.
4. Lưu một mục mới nếu chưa có.

Khi tra cứu, map bắt đầu từ mã băm của đối tượng được dùng để tìm ở thời điểm tra cứu. Nó không bắt buộc đi qua mọi phần tử rồi so sánh tham chiếu với đối tượng cần tìm.

Trong cài đặt OpenJDK 17 của `HashMap`, nút lưu trữ giữ mã băm đã được tính lúc tạo nút. Đường tìm kiếm xét mã băm trước khi kiểm tra tham chiếu hoặc `equals` ở nút ứng viên. Do đó, thay đổi mã băm của đối tượng không tự cập nhật mã băm đã lưu trong nút. Đây là một giải thích về cài đặt cụ thể, không phải định nghĩa áp dụng cho mọi loại `Map`. [Mã nguồn HashMap của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java)

Ví dụ theo dòng thời gian:

| Thời điểm | Trạng thái khóa | Thao tác | Điều cần hiểu |
|---|---|---|---|
| T0 | `id = 1` | `map.put(key, "payload")` | Map tổ chức mục theo thông tin ban đầu |
| T1 | `id = 2` | `key.setId(2)` | Chỉ đối tượng thay đổi; không có thao tác đổi khóa trên map |
| T2 | `id = 2` | `map.get(key)` | Đường tìm kiếm sử dụng thông tin hiện tại của khóa |
| T3 | `id = 2` | Duyệt `entrySet` hoặc `keySet` | Có thể vẫn thấy mục và tham chiếu đã bị sửa |

**Không tìm thấy khi tra cứu không có nghĩa là mục đã bị xóa.** Mục có thể vẫn chiếm chỗ, vẫn được đếm trong `size` và vẫn xuất hiện khi duyệt.

Cũng không nên suy ra rằng giữ nguyên số thứ tự ngăn là đủ an toàn. Một bảng băm có thể kiểm tra cả mã băm đã lưu, không chỉ ngăn được chọn. Tương tự, đừng dùng việc thêm đủ phần tử để bảng mở rộng làm cơ chế sửa lỗi: đó không phải một thao tác đổi khóa được API cam kết.

## 4. Ba kiểu thay đổi cần nhận diện

### 4.1. Mã băm thay đổi

Một trường được dùng để tính `hashCode` bị sửa sau khi thêm:

```java
// Minh họa thao tác nguy hiểm; lớp MutableKey có trong chương trình đầy đủ.
MutableKey key = new MutableKey(1);
map.put(key, "payload");
key.setId(2);
```

Các triệu chứng có thể gồm:

- `containsKey(key)` trả `false` dù duyệt map vẫn thấy khóa.
- `get(key)` trả `null` dù giá trị đã lưu khác `null`.
- `remove(key)` không loại bỏ được mục mà người viết chương trình mong muốn.
- Một lần `put` tiếp theo không tạo ra trạng thái mà người viết nghĩ là “cập nhật mục cũ”.

Không nên viết logic nghiệp vụ dựa trên việc một triệu chứng nào đó chắc chắn xảy ra. Sau khi làm thay đổi khóa theo cách không được hỗ trợ, API không bảo đảm một cách khôi phục tự động.

Riêng `get` trả `null` còn có nghĩa khác trong `HashMap`: có thể không có ánh xạ, hoặc có ánh xạ với giá trị `null`. Khi chẩn đoán trên một map hợp lệ cho phép `null`, cần xét cả `containsKey`. Trong ví dụ chạy ở dưới, giá trị ban đầu là chuỗi `"payload"` để loại bỏ sự nhập nhằng này. [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

### 4.2. Quan hệ bằng nhau thay đổi, dù mã băm không đổi

Giả sử mọi đối tượng của lớp đều trả mã băm `7`. Điều này có thể làm hiệu năng kém, nhưng bản thân việc nhiều đối tượng có cùng mã băm không vi phạm quy tắc “bằng nhau thì cùng mã băm”.

Ta có hai đối tượng:

- `left.code = "A"`.
- `right.code = "B"`.

Ban đầu chúng khác nhau nên được thêm thành hai phần tử của set. Nếu sau đó sửa `right.code` thành `"A"` thì hai đối tượng đang được lưu trở nên bằng nhau.

Mã băm vẫn là `7`, nhưng quan hệ bằng nhau đã thay đổi. Set không tự chạy lại thao tác thêm cho toàn bộ phần tử để loại bỏ một phần tử trùng theo nghĩa mới.

Điểm cần nhớ: **giữ mã băm không đổi chưa đủ; ý nghĩa bằng nhau cũng phải ổn định.**

Tình huống tương tự với map còn khó xử lý hơn vì hai khóa nay bằng nhau có thể gắn với hai giá trị khác nhau. Nếu dựng lại map, phải quyết định giá trị nào được giữ hoặc có cần báo xung đột. Không được coi đó chỉ là việc “băm lại cho đúng”.

### 4.3. Trường không tham gia nhận diện khóa thay đổi

Không phải mọi thay đổi của đối tượng đều phá hỏng cách dùng trong map.

Ví dụ:

- `id` là định danh ổn định.
- `displayName` là tên hiển thị có thể đổi.
- `equals` và `hashCode` chỉ dựa trên `id`.

Đổi `displayName` không làm thay đổi dữ liệu dùng cho bằng nhau hoặc băm. Về khía cạnh tra cứu khóa, thay đổi đó có thể an toàn.

Tuy vậy, phải kiểm tra ý nghĩa nghiệp vụ. Nếu `id` thực sự chỉ duy nhất trong từng `tenant` thì khóa chỉ có `id` có thể đã thiếu dữ liệu ngay từ đầu. Quyết định “không đưa trường này vào `equals`” phải xuất phát từ định nghĩa đúng về danh tính, không phải để né một lỗi đang gặp.

## 5. Chương trình chạy hoàn chỉnh với Java 17 trở lên

Chương trình sau đặt các tình huống cạnh nhau:

1. Sửa trường làm thay đổi mã băm của khóa.
2. Sửa quan hệ bằng nhau của phần tử set dù mã băm không đổi.
3. Đổi một trường không tham gia định danh.
4. Thấy rủi ro của một `record` chứa danh sách còn sửa được.
5. Dùng bản sao bảo vệ cho danh sách và dùng khóa bất biến để đổi khóa.

Lưu toàn bộ vào `MutableCollectionKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class MutableCollectionKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    static final class SameHashKey {
        private String code;

        SameHashKey(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        void setCode(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof SameHashKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class StableId {
        private final int id;
        private String displayName;

        StableId(int id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        String displayName() {
            return displayName;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof StableId other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    record UnsafeTagsKey(String tenant, List<String> tags) {}

    record SafeTagsKey(String tenant, List<String> tags) {
        SafeTagsKey {
            tenant = Objects.requireNonNull(tenant, "tenant");
            tags = List.copyOf(tags);
        }
    }

    record UserKey(String tenant, int id) {
        UserKey {
            Objects.requireNonNull(tenant, "tenant");
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> map = new HashMap<>();
        map.put(key, "payload");
        System.out.println("Before change: "
                + map.get(new MutableKey(1)));

        key.setId(2);
        System.out.println("Same object still stored: "
                + (map.keySet().iterator().next() == key));
        System.out.println("Map size after change: " + map.size());
        System.out.println("Lookup same changed object: " + map.get(key));
        System.out.println("Lookup old logical key: "
                + map.get(new MutableKey(1)));
        System.out.println("Lookup new logical key: "
                + map.get(new MutableKey(2)));

        SameHashKey left = new SameHashKey("A");
        SameHashKey right = new SameHashKey("B");
        Set<SameHashKey> set = new HashSet<>();
        set.add(left);
        set.add(right);
        right.setCode("A");
        System.out.println("Elements now equal: " + left.equals(right));
        System.out.println("Set size after equality change: " + set.size());
        System.out.println("Distinct references still stored: "
                + (set.stream().filter(value -> value == left).count() == 1
                && set.stream().filter(value -> value == right).count() == 1));

        StableId stable = new StableId(7, "Old name");
        Map<StableId, String> stableMap = new HashMap<>();
        stableMap.put(stable, "account");
        stable.setDisplayName("New name");
        System.out.println("Changed non-key field: " + stable.displayName());
        System.out.println("Stable identity lookup: "
                + stableMap.get(new StableId(7, "Another name")));

        List<String> mutableTags = new ArrayList<>(List.of("reader"));
        UnsafeTagsKey unsafe = new UnsafeTagsKey("t", mutableTags);
        UnsafeTagsKey oldSnapshot =
                new UnsafeTagsKey("t", List.of("reader"));
        mutableTags.add("writer");
        System.out.println("Unsafe record changed equality: "
                + !unsafe.equals(oldSnapshot));

        List<String> input = new ArrayList<>(List.of("reader"));
        SafeTagsKey safe = new SafeTagsKey("t", input);
        int oldHash = safe.hashCode();
        input.add("writer");
        System.out.println("Safe record tags: " + safe.tags());
        System.out.println("Safe record hash stable: "
                + (oldHash == safe.hashCode()));
        Map<SafeTagsKey, String> safeMap = new HashMap<>();
        safeMap.put(safe, "allowed");
        System.out.println("Safe record lookup: "
                + safeMap.get(new SafeTagsKey("t", List.of("reader"))));

        UserKey oldKey = new UserKey("t", 1);
        UserKey newKey = new UserKey("t", 2);
        Map<UserKey, String> accounts = new HashMap<>();
        accounts.put(oldKey, "value");
        if (!accounts.containsKey(oldKey)
                || accounts.containsKey(newKey)) {
            throw new IllegalStateException("cannot change key");
        }
        String value = accounts.remove(oldKey);
        accounts.put(newKey, value);
        System.out.println("Rekey old present: "
                + accounts.containsKey(oldKey));
        System.out.println("Rekey new value: " + accounts.get(newKey));
        System.out.println("Rekey size: " + accounts.size());
    }
}

```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked MutableCollectionKeyDemo.java
java MutableCollectionKeyDemo
```

Mã chỉ sử dụng tính năng và API có từ Java 17 trở xuống. Lệnh trên đã được kiểm tra bằng `javac` và Java 24.0.2 với `--release 17` khi biên dịch; không cần thư viện ngoài.

Kết quả quan sát được trên lần chạy đã kiểm tra:

```text
Before change: payload
Same object still stored: true
Map size after change: 1
Lookup same changed object: null
Lookup old logical key: null
Lookup new logical key: null
Elements now equal: true
Set size after equality change: 2
Distinct references still stored: true
Changed non-key field: New name
Stable identity lookup: account
Unsafe record changed equality: true
Safe record tags: [reader]
Safe record hash stable: true
Safe record lookup: allowed
Rekey old present: false
Rekey new value: value
Rekey size: 1
```

**Giới hạn của kết quả:** các dòng thuộc hai tình huống cố ý sửa khóa/phần tử đang được lưu mô tả hành vi quan sát được của `HashMap` và `HashSet` trong lần chạy này. Hành vi sau sự thay đổi ấy không phải bảo đảm có tính di động của hợp đồng `Map` hoặc `Set`. Các phần dùng khóa ổn định ở cuối mới là mẫu thiết kế nên áp dụng.

### 5.1. Đọc nhóm kết quả về MutableKey

`Before change: payload` chứng minh khóa tra cứu độc lập có `id = 1` tìm được giá trị trước khi có thay đổi.

Sau `key.setId(2)`:

- `Same object still stored: true` được kiểm tra bằng `==` khi duyệt `keySet`: tham chiếu ban đầu vẫn nằm trong map.
- `Map size after change: 1` cho thấy việc sửa trường không phải thao tác xóa mục.
- Tra cứu bằng chính đối tượng đã đổi, một khóa mới có `id = 1` hoặc một khóa mới có `id = 2` đều cho `null` trong lần chạy này.

Khóa `id = 1` mới không còn bằng đối tượng đang lưu vì đối tượng đang lưu đã có `id = 2`. Khóa `id = 2` mới lại bắt đầu tìm theo thông tin băm mới, trong khi mục đã được tổ chức theo thông tin cũ. “Dùng lại chính đối tượng đó” không giúp bỏ qua toàn bộ quá trình chọn ứng viên.

### 5.2. Đọc nhóm kết quả về SameHashKey

Hai phần tử được thêm khi `code` khác nhau. Sau khi đổi `right` thành `"A"`:

- `Elements now equal: true` xác nhận quan hệ bằng nhau mới.
- `Set size after equality change: 2` cho thấy tập hợp không tự loại bỏ một mục.
- `Distinct references still stored: true` chứng minh cả hai tham chiếu ban đầu vẫn được duyệt ra.

Phép đếm bằng `==` ở đây chỉ dùng để quan sát hai đối tượng vật lý. Nó không thay thế định nghĩa bằng nhau của set.

### 5.3. Đọc nhóm kết quả về StableId

Khóa `StableId` dùng `id` cho cả `equals` và `hashCode`; `displayName` không tham gia. Vì `id` không đổi, một đối tượng khác cùng `id = 7` vẫn tìm được `"account"` sau khi đổi tên hiển thị.

Đây là ví dụ về một đối tượng có dữ liệu thay đổi được nhưng có phần nhận diện khóa ổn định. Trong một thiết kế lớn hơn, tách khóa thành một kiểu riêng vẫn thường dễ kiểm tra và giải thích hơn.

### 5.4. Đọc nhóm kết quả về record và danh sách

`UnsafeTagsKey` giữ trực tiếp tham chiếu danh sách được đưa vào. Sau `mutableTags.add("writer")`, thành phần `tags` trong record cũng quan sát thấy danh sách mới, nên record không còn bằng bản chụp chỉ có `"reader"`.

`SafeTagsKey` tạo `List.copyOf(tags)` trong hàm tạo. Với các phần tử là `String` trong ví dụ, việc sửa danh sách đầu vào không thay đổi danh sách được giữ trong khóa. Khóa vẫn tìm được giá trị qua một khóa độc lập có cùng dữ liệu.

### 5.5. Đọc nhóm kết quả về đổi khóa

`UserKey` là khóa mới độc lập cho định danh cũ và định danh mới. Chương trình kiểm tra khóa cũ tồn tại, khóa mới chưa có, rồi lấy giá trị khỏi khóa cũ và thêm dưới khóa mới.

Sau đó:

- Khóa cũ không còn tồn tại.
- Khóa mới dẫn đến cùng giá trị.
- Kích thước vẫn là `1`.

Đoạn này chạy trong một luồng, với các khóa bất biến, không có tác nhân khác sửa map và không mô phỏng lỗi giữa hai thao tác. Nó không phải một phép đổi khóa nguyên tử dành cho mọi môi trường.

## 6. final và record chưa có nghĩa là bất biến sâu

### 6.1. final khóa tham chiếu, không khóa toàn bộ đồ thị đối tượng

Xét khai báo:

```java
final List<String> tags = new ArrayList<>();
tags.add("reader");
```

`final` cấm gán `tags` sang một tham chiếu khác sau khi đã được khởi tạo. Nó không cấm gọi `add` trên đối tượng đang được tham chiếu.

Nếu một khóa tính `equals` hoặc `hashCode` từ nội dung danh sách đó, việc sửa danh sách qua bất kỳ tham chiếu nào cũng có thể làm thay đổi dữ liệu nhận diện khóa. Không nhất thiết phải có phương thức `setTags` ngay trên lớp khóa mới có rủi ro.

Các đường thay đổi gián tiếp thường gặp gồm:

- Người gọi giữ danh sách đầu vào và tiếp tục sửa sau khi tạo khóa.
- Một phương thức truy cập trả trực tiếp danh sách bên trong.
- Danh sách không cho thêm/xóa phần tử nhưng phần tử bên trong vẫn có thể bị sửa.
- Một đối tượng lồng bên trong thay đổi kết quả `equals` hoặc `hashCode`.

Cần kiểm tra cả dữ liệu đi vào lẫn dữ liệu đi ra, và cả các đối tượng lồng mà phép so sánh phụ thuộc vào.

### 6.2. record tự sinh phương thức theo thành phần, không tự sao chép sâu

Một record có các trường thành phần là `private final` và sinh các phương thức truy cập, `equals`, `hashCode`, `toString` theo mô hình record. Tuy nhiên, nếu thành phần tham chiếu một danh sách sửa được, chính danh sách đó vẫn có thể đổi. Record không tự biến danh sách đầu vào thành bản sao bất biến. [Records trong Java 17](https://docs.oracle.com/en/java/javase/17/language/records.html)

Vì vậy:

```java
record UserKey(String tenant, int id) {}
```

là một lựa chọn khóa ổn định đơn giản: `String` bất biến, `int` là giá trị nguyên thủy, và hai thành phần không bị gán lại sau khi tạo.

Ngược lại:

```java
record TagsKey(List<String> tags) {}
```

cần chính sách sở hữu danh sách rõ ràng. Kiểu `record` một mình không đưa ra chính sách ấy.

Mẫu `List.copyOf` trong chương trình đầy đủ có ba điểm cần hiểu:

1. Danh sách kết quả không cho sửa cấu trúc qua API danh sách.
2. Việc thêm/xóa vào danh sách đầu vào sau khi sao chép không phản ánh vào danh sách kết quả.
3. Nó không sao chép sâu từng phần tử.

`List.copyOf` không chấp nhận nguồn `null` hoặc phần tử `null`. Với `List<String>`, các phần tử chuỗi bất biến nên rủi ro sửa trạng thái của phần tử không xuất hiện. Nếu thành phần là `List<MutableTag>`, vẫn phải xử lý tính ổn định của từng `MutableTag`. [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

Ngoài ra, nếu danh sách là một phần của danh tính thì thứ tự phần tử có ý nghĩa theo `List.equals`. Hai danh sách `["reader", "writer"]` và `["writer", "reader"]` không tự trở thành cùng một khóa. Nếu nghiệp vụ muốn bỏ qua thứ tự hoặc chuẩn hóa chữ hoa/chữ thường, phải định nghĩa và chuẩn hóa ngay khi tạo khóa, trước khi đưa vào map.

## 7. Lựa chọn thiết kế: định danh ổn định, dữ liệu thay đổi ở phía giá trị

Thiết kế dễ duy trì thường là:

```text
Khóa bất biến: tenant + userId
                ↓
Giá trị thay đổi: tên hiển thị, trạng thái tài khoản, quyền hiện tại...
```

Ví dụ khai báo loại khóa:

```java
record AccountKey(String tenant, long userId) {}
```

Nếu `tenant` và `userId` xác định danh tính của tài khoản và không đổi trong thời gian lưu, khóa này dễ dùng hơn một đối tượng `Account` lớn chứa nhiều trường có thể sửa.

Bảng quyết định:

| Nhu cầu | Lựa chọn nên cân nhắc | Điều cần kiểm tra |
|---|---|---|
| Nhận diện bằng một mã ổn định | Dùng mã bất biến làm khóa | Mã có duy nhất đúng trong phạm vi cần dùng không? |
| Nhận diện bằng nhiều trường | Tạo lớp/record khóa riêng | Mọi thành phần có ổn định và được chuẩn hóa nhất quán không? |
| Chỉ cập nhật tên, trạng thái, dữ liệu hiển thị | Sửa hoặc thay giá trị của map | Dữ liệu này có thực sự không tham gia khóa không? |
| Danh tính nghiệp vụ thực sự đổi | Thực hiện quy trình đổi khóa | Có xung đột với khóa mới, lỗi giữa chừng hoặc truy cập đồng thời không? |
| Dùng khóa có tập hợp lồng nhau | Sao chép bảo vệ và giữ thành phần ổn định | Bản sao có đủ sâu theo định nghĩa bằng nhau không? |

Đừng loại một trường khỏi `equals` chỉ vì trường đó hay đổi, nếu bỏ nó làm hai thực thể khác nhau trở thành cùng một khóa. Trước hết phải trả lời: “Hai đối tượng nào được phép đại diện cho cùng một mục trong map?” Sau đó mới quyết định cấu trúc khóa.

Một đối tượng giá trị của map có thể thay đổi mà không ảnh hưởng đến chỉ mục khóa của chính map ấy. Ví dụ, sửa `Account.displayName` khi map được đánh khóa bởi `AccountKey` không phải là sửa khóa. Tuy nhiên, nếu lại dùng toàn bộ map hoặc một đối tượng chứa map làm khóa ở một nơi khác, phải xét lại chuỗi phụ thuộc của `equals` và `hashCode` ở nơi đó.

## 8. Nếu buộc phải đổi dữ liệu nhận diện

### 8.1. Cách ưu tiên: thay bằng khóa mới bất biến

Với một map do một luồng sở hữu, cách làm có thể là:

1. Xác định khóa cũ và khóa mới dưới dạng các giá trị ổn định.
2. Kiểm tra khóa cũ có tồn tại.
3. Kiểm tra chính sách khi khóa mới đã có: từ chối, hợp nhất hay thay thế.
4. Lấy giá trị và bỏ ánh xạ theo khóa cũ.
5. Tạo ánh xạ theo khóa mới.
6. Kiểm tra kết quả phù hợp với chính sách đã chọn.

Chương trình chạy ở trên chọn chính sách từ chối nếu khóa mới đã tồn tại. Đây là một chính sách cụ thể; không phải mọi ứng dụng đều phải dùng cùng chính sách.

Nếu map cho phép giá trị `null`, chỉ kiểm tra kết quả `remove` có `null` hay không là chưa đủ để phân biệt “khóa không có” với “khóa có và giá trị là `null`”. Đó là lý do ví dụ kiểm tra `containsKey(oldKey)` trước.

Chuỗi kiểm tra rồi xóa rồi thêm có thể bị chen ngang khi có nhiều luồng hoặc có tác nhân khác sửa map. Nó cũng có thể cần phục hồi nếu hệ thống có thao tác bổ sung có thể thất bại giữa chừng. Cách đồng bộ hóa, giao dịch hoặc điều phối phải bao phủ toàn bộ yêu cầu đổi khóa, không chỉ một lệnh riêng lẻ.

### 8.2. Nếu vẫn dùng đối tượng khóa thay đổi được

Trong phạm vi thật sự kiểm soát được, thứ tự phải là:

```text
Khóa còn ở trạng thái cũ và map còn hợp lệ
    → loại khóa khỏi tất cả cấu trúc đang lập chỉ mục theo nó
    → thay đổi dữ liệu nhận diện
    → thêm lại theo dữ liệu mới và xử lý xung đột
```

Điểm quyết định là **loại ra trước khi sửa**, khi thao tác tìm bằng trạng thái cũ vẫn còn hợp lệ. Sửa trước rồi mới gọi `remove(key)` có thể đã quá muộn.

Đồng thời phải biết đối tượng đang được dùng ở những đâu. Một khóa có thể xuất hiện trong nhiều map hoặc đồng thời là phần tử của set. Chỉ bỏ nó khỏi một map không làm cho việc sửa trở nên an toàn đối với các cấu trúc còn lại.

Cách này đòi hỏi quyền sở hữu và điều phối chặt chẽ. Nếu không chứng minh được các điều kiện ấy, tạo khóa bất biến riêng là lựa chọn ít rủi ro hơn.

### 8.3. Nếu đối tượng đã bị sửa khi đang nằm trong bảng băm

Đừng tiếp tục gọi thử nhiều lần `put`, `remove` hoặc tăng kích thước map với hy vọng nó tự lành.

Một hướng phục hồi có kiểm soát là:

1. Dừng các thay đổi và truy cập cạnh tranh vào cấu trúc bị ảnh hưởng.
2. Quan sát các mục hiện có để giữ lại khóa, giá trị và bằng chứng xung đột cần thiết.
3. Chuyển dữ liệu sang các khóa mới ổn định.
4. Phát hiện các khóa nay bằng nhau và áp dụng chính sách xung đột rõ ràng.
5. Chỉ thay thế cấu trúc cũ khi kết quả mới đã được kiểm tra.

Đây là hướng xử lý dữ liệu trong một quy trình phục hồi, không phải cam kết rằng mọi thao tác trên map đã bị dùng sai đều có hành vi được đặc tả. Nếu hậu quả liên quan dữ liệu quan trọng, cần có nguồn dữ liệu chuẩn hoặc bản chụp tin cậy để đối chiếu.

Không sao chép mù quáng sang map mới rồi cho rằng đã bảo toàn mọi giá trị: các khóa nay bằng nhau có thể khiến một giá trị ghi đè giá trị khác. Việc tái lập chỉ mục phải đi cùng quyết định nghiệp vụ về xung đột.

## 9. Những thay đổi có vẻ là giải pháp nhưng không giải quyết nguyên nhân

### 9.1. Dùng lại cùng tham chiếu

`get(key)` không phải lời yêu cầu quét mọi phần tử để tìm đúng địa chỉ đối tượng. Một cấu trúc dựa trên băm có thể cần đến đúng ứng viên trước khi kiểm tra tham chiếu. Vì vậy, “tôi vẫn giữ biến `key` ban đầu” không chứng minh khóa vẫn tìm được.

### 9.2. Chuyển sang ConcurrentHashMap

`ConcurrentHashMap` cung cấp các đặc tính cho truy cập đồng thời. Nó không biến dữ liệu trong khóa thành bất biến và không tự theo dõi mọi lần sửa trường của khóa. [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Các thao tác như `compute` hoặc `putIfAbsent` cũng không tự biến “bỏ khóa cũ rồi thêm khóa mới” thành một phép đổi tên nguyên tử trên hai khóa. Cần thiết kế riêng nếu yêu cầu nghiệp vụ cần tính nguyên tử của cả chuỗi.

### 9.3. Bọc map bằng unmodifiableMap hoặc gọi Map.copyOf

Một map không cho sửa qua API của nó vẫn có thể giữ tham chiếu tới các khóa hoặc giá trị có trạng thái thay đổi được. Chặn `put` và `remove` không chặn một tham chiếu bên ngoài gọi `key.setId(...)`.

`Collections.unmodifiableMap` tạo một cách nhìn không cho sửa map qua cách nhìn đó; nó không đóng băng các đối tượng khóa. Với `Map.copyOf` cũng không nên suy ra rằng các đối tượng khóa đã được sao chép sâu. [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)), [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))

### 9.4. Đổi hashCode thành một hằng số

Nếu quan hệ `equals` thay đổi thì mã băm hằng số không bảo vệ được tính duy nhất của phần tử. Ví dụ `SameHashKey` đã minh họa trực tiếp điều này. Mã băm hằng số còn làm giảm khả năng phân tán, nên không phải cách sửa thiết kế khóa.

### 9.5. Chuyển sang TreeMap hoặc TreeSet

Cấu trúc có thứ tự dựa vào quy tắc so sánh để định vị phần tử. Nếu sửa trường mà `Comparator` hoặc `compareTo` dùng trong lúc phần tử đang được lưu, quan hệ thứ tự có thể thay đổi mà cây không tự tổ chức lại. Chuyển cấu trúc dữ liệu chỉ có ích khi tiêu chí nhận diện và cách thay đổi phù hợp với cấu trúc mới. [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 9.6. Dùng IdentityHashMap để bỏ qua equals và hashCode

`IdentityHashMap` nhận diện khóa bằng đồng nhất tham chiếu. Đây là một mô hình khóa khác, thích hợp cho một số bài toán theo dõi từng đối tượng vật lý. Hai đối tượng khác nhau có cùng mã nghiệp vụ không tự trở thành cùng khóa. Vì vậy, nó chỉ phù hợp khi chính bài toán yêu cầu ngữ nghĩa đó. [IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 9.7. Chờ ConcurrentModificationException

Việc sửa trường của một đối tượng không phải thao tác thêm hoặc xóa mục qua API của collection. Không có bảo đảm rằng một lần sửa như thế sẽ gây `ConcurrentModificationException`.

Cơ chế phát hiện sửa cấu trúc trong lúc duyệt không phải bộ kiểm tra tính đúng đắn của danh tính khóa. Chương trình không ném ngoại lệ vẫn có thể đang giữ một cấu trúc mà tra cứu không còn đáng tin.

## 10. Cách kiểm tra một loại khóa trước khi đưa vào sử dụng

### 10.1. Kiểm tra định nghĩa danh tính

Viết một câu rõ ràng, chẳng hạn:

> Trong map này, hai khóa bằng nhau khi cùng tenant và cùng mã tài khoản.

Sau đó đối chiếu:

- `equals` có dùng đúng hai thành phần ấy không?
- `hashCode` có dựa trên các thành phần phù hợp không?
- Các thành phần có đổi trong thời gian lưu không?
- Có cần chuẩn hóa dữ liệu đầu vào không?
- Có trường nào bị bỏ sót làm hai danh tính khác nhau nhập làm một không?

Một phương thức sinh tự động từ IDE có thể nhất quán về cú pháp nhưng vẫn chọn sai định nghĩa nghiệp vụ.

### 10.2. Kiểm tra đường thay đổi gián tiếp

Tìm các phương thức đặt giá trị, phương thức truy cập và các tham chiếu dùng chung. Với khóa chứa dữ liệu lồng nhau, kiểm tra cả đối tượng bên trong.

Các câu hỏi thực tế:

- Sau khi tạo khóa, sửa danh sách đầu vào có làm khóa đổi không?
- Lấy danh sách từ khóa rồi sửa có làm khóa đổi không?
- Phần tử của danh sách có thể thay đổi dữ liệu dùng cho bằng nhau không?
- Trường `final` có đang giữ một đối tượng thay đổi được không?
- Có lớp con ghi đè phương thức liên quan làm thay đổi cách nhận diện không?

### 10.3. Kiểm tra hành vi đúng, không cố định một biểu hiện lỗi không được bảo đảm

Các kiểm tra nên bảo vệ cam kết thiết kế:

| Cam kết | Cách kiểm tra có ý nghĩa |
|---|---|
| Khóa độc lập cùng danh tính tra cứu được | Tạo hai khóa riêng cùng dữ liệu; dùng khóa thứ hai tìm giá trị đã thêm bằng khóa thứ nhất |
| Trường ngoài danh tính được phép đổi | Đổi tên hiển thị; xác nhận khóa độc lập cùng định danh vẫn tra cứu đúng |
| Dữ liệu đầu vào đã được sao chép bảo vệ | Sửa danh sách đầu vào; xác nhận dữ liệu, bằng nhau và mã băm của khóa không đổi |
| Không làm lộ cấu trúc sửa được của khóa | Kiểm tra chính sách truy cập dữ liệu trả ra phù hợp với thiết kế bất biến |
| Đổi khóa tuân theo chính sách | Kiểm tra khóa mới trống, khóa mới đã tồn tại, khóa cũ vắng mặt và giá trị `null` nếu được hỗ trợ |
| Xung đột không làm mất dữ liệu âm thầm | Tạo tình huống nhiều dữ liệu dẫn về cùng khóa mới và xác nhận chính sách xử lý |

Không nên coi một kiểm tra bắt buộc `map.get(mutatedKey) == null` là hợp đồng mà chương trình phải giữ trên mọi JVM. Đó là kiểm tra một biểu hiện của việc dùng sai điều kiện lưu trữ. Kiểm tra hữu ích hơn là bảo đảm không có dữ liệu nhận diện bị sửa khi khóa đang được lưu.

## 11. Bài tập thực hành

### Bài 1: sửa tên tài khoản

Một map dùng `record AccountKey(String tenant, long id)` làm khóa và đối tượng `Account` làm giá trị. Đổi `Account.displayName` có phải đổi khóa không?

**Đáp án:** không, nếu `Account` chỉ là giá trị và tên hiển thị không làm thay đổi các thành phần của `AccountKey`. Vẫn cần xử lý đồng thời và các ràng buộc riêng của giá trị nếu có, nhưng đó là vấn đề khác với tính ổn định của khóa.

### Bài 2: record chứa danh sách

Một khóa là `record GroupKey(List<String> members)`. Người gọi tạo khóa bằng một `ArrayList` rồi tiếp tục thêm thành viên vào danh sách đó. Có thể kết luận an toàn vì record không có phương thức đặt giá trị không?

**Đáp án:** không. Record giữ tham chiếu tới danh sách. Nội dung danh sách ảnh hưởng đến bằng nhau và băm của thành phần ấy. Cần xác định lại danh tính nhóm và chính sách sao chép bảo vệ; nếu thành viên thay đổi thường xuyên thì dùng mã nhóm ổn định làm khóa thường phù hợp hơn.

### Bài 3: hashCode luôn bằng 7

Một set có hai phần tử với mã băm bằng `7`. Chúng khác nhau khi thêm, rồi một phần tử bị sửa để bằng phần tử kia. Mã băm không đổi có đủ bảo đảm set vẫn đúng không?

**Đáp án:** không. Quan hệ bằng nhau đã đổi trong thời gian lưu. Mã băm chỉ là một phần của điều kiện cần giữ ổn định.

### Bài 4: thứ tự sửa và xóa

Lập trình viên làm `key.setId(newId)` rồi `map.remove(key)` trước khi thêm lại. Vì sao thứ tự này nguy hiểm?

**Đáp án:** thao tác xóa đã bắt đầu từ trạng thái mới, trong khi mục được tổ chức theo trạng thái cũ. Nếu dùng khóa thay đổi được trong phạm vi kiểm soát, phải loại nó ra khi nó vẫn có trạng thái cũ. Cách dễ duy trì hơn là dùng hai khóa bất biến khác nhau và một quy trình đổi ánh xạ rõ ràng.

### Bài 5: hai người dùng đồng thời đổi khóa

Một `ConcurrentHashMap` có thao tác kiểm tra khóa mới vắng mặt, xóa khóa cũ, rồi thêm khóa mới. Có tự động bảo đảm không luồng nào chen vào giữa không?

**Đáp án:** không. Việc mỗi thao tác được hỗ trợ an toàn khi truy cập đồng thời không làm toàn bộ chuỗi trên hai khóa trở thành một giao dịch. Phải xác định điều kiện đồng bộ hóa hoặc giao dịch ở cấp yêu cầu đổi khóa.

## 12. Những điểm cần ghi nhớ

- Giữ ổn định cả quan hệ bằng nhau lẫn mã băm trong thời gian khóa hoặc phần tử đang được lưu trong bảng băm.
- Một lớp có thể viết `equals` và `hashCode` phù hợp tại từng thời điểm nhưng vẫn bị dùng sai nếu dữ liệu nhận diện đổi giữa thời gian lưu.
- Cùng tham chiếu, mã băm hằng số, `final`, `record` hoặc map không cho sửa đều không tự giải quyết mọi đường thay đổi của dữ liệu nhận diện.
- Ưu tiên khóa nhỏ, bất biến, mô tả đúng danh tính; đặt thông tin thường xuyên thay đổi ở giá trị.
- Khi danh tính thực sự cần đổi, xử lý bằng một quy trình đổi khóa có chính sách xung đột và điều kiện đồng thời rõ ràng.
- Dùng các kết quả lỗi để hiểu rủi ro; dùng các bất biến thiết kế để kiểm tra mã đúng.

## Tài liệu đối chiếu

- [Object — hợp đồng equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
- [Map — điều kiện sử dụng khóa và các thao tác ánh xạ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Set — điều kiện sử dụng phần tử và tính duy nhất](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).
- [HashMap — hành vi API và đặc điểm cài đặt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).
- [Records trong Java 17](https://docs.oracle.com/en/java/javase/17/language/records.html).
- [List.copyOf — bản sao không cho sửa và giới hạn sao chép](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Mã nguồn HashMap của OpenJDK 17 — tham khảo cơ chế cụ thể](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java).
