# Entry snapshot và giới hạn thay đổi giá trị trong NavigableMap

## 1. Map.Entry không luôn là một cửa cập nhật map

Một `Map.Entry<K, V>` biểu diễn cặp khóa–giá trị. Khi nhận entry từ một map, rất dễ nghĩ rằng gọi `setValue` sẽ thay giá trị trong map. Điều đó **phụ thuộc nguồn gốc và hợp đồng của entry**, không chỉ phụ thuộc kiểu `Map.Entry`.

Với `NavigableMap`, các phương thức tìm ánh xạ trả ảnh chụp (snapshot) của một ánh xạ tại lúc gọi:

- `lowerEntry`, `floorEntry`, `ceilingEntry`, `higherEntry`.
- `firstEntry`, `lastEntry`.
- `pollFirstEntry`, `pollLastEntry`.

Các entry này không được dùng để sửa ánh xạ gốc bằng `setValue`. Trên `TreeMap`, lời gọi đó ném `UnsupportedOperationException`. Đây là hợp đồng API hiện hành, không phải một hạn chế của Java cũ. Xem [NavigableMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Cần tách ba câu hỏi:

1. Entry có còn liên kết với map không?
2. Có được thay tham chiếu value qua entry không?
3. Đối tượng mà value trỏ tới có tự thay đổi được không?

Ba câu trả lời này không nhất thiết giống nhau.

## 2. Snapshot của ánh xạ nghĩa là gì?

### 2.1. Chụp lại cặp tham chiếu tại một thời điểm

Giả sử map chứa:

```text
10 -> "alpha"
20 -> "beta"
```

Ta gọi `floorEntry(15)`, nhận entry `10=alpha`. Sau đó:

```java
// Đoạn minh họa, names là NavigableMap<Integer, String>.
names.put(10, "alpha-new");
```

Kết quả quan sát:

```text
Entry đã giữ:    10=alpha
Ánh xạ hiện tại: 10=alpha-new
```

Entry đã giữ không phải góc nhìn tự cập nhật theo `put`. Nó tiếp tục giữ khóa và tham chiếu value được chụp lúc nhận kết quả.

Với V là `String` bất biến, điều này rất dễ thấy. Nhưng từ “snapshot” không tự hàm ý đã sao chép sâu mọi đối tượng; phần đó sẽ được phân tích riêng.

### 2.2. Snapshot không giữ cho ánh xạ tồn tại

Nếu map xóa khóa 10, entry đã lấy vẫn có thể biểu diễn `10=alpha`. Nó là dữ liệu đã quan sát, không phải bằng chứng khóa 10 đang còn trong map.

Entry từ `pollFirstEntry` hoặc `pollLastEntry` còn minh họa rõ hơn: phương thức trả ánh xạ đã chọn **và xóa ánh xạ ấy khỏi map**. Entry còn tồn tại trong biến bên gọi, còn ánh xạ thì đã bị lấy khỏi cấu trúc.

Không thể gọi `setValue` trên entry của poll để “đưa nó trở lại”. Muốn thêm lại phải thực hiện thao tác map rõ ràng, và cần xem xét trạng thái map hiện tại cùng quy tắc nghiệp vụ.

### 2.3. Một ảnh chụp ánh xạ không phải ảnh chụp toàn bộ map

Lấy hai entry bằng hai lần gọi khác nhau không mặc nhiên tạo một bộ dữ liệu nhất quán của cùng một thời điểm nếu map có thể thay đổi giữa các lần gọi.

Snapshot cũng không đặt chỗ khóa, khóa value hoặc dành quyền cập nhật cho bên nhận. Nó chỉ mô tả kết quả của lần quan sát đó theo hợp đồng của cách cài đặt.

## 3. Vì sao có setValue nhưng vẫn không được gọi?

`setValue(V)` là thao tác **tùy chọn** của giao diện `Map.Entry`. Việc một phương thức xuất hiện trên kiểu không có nghĩa mọi đối tượng thuộc kiểu ấy đều hỗ trợ thay đổi.

```java
// Đoạn minh họa với entry từ floorEntry của TreeMap.
Map.Entry<Integer, String> saved = names.floorEntry(15);
if (saved != null) {
    saved.setValue("changed"); // UnsupportedOperationException.
}
```

Không nên bắt ngoại lệ này rồi coi đó là quy trình cập nhật bình thường. Hãy chọn API phù hợp ngay từ đầu.

Phân biệt những trường hợp thường gặp:

| Nguồn entry | Liên kết với map | Khả năng setValue |
| --- | --- | --- |
| Entry điều hướng của `TreeMap` | Ảnh chụp tách khỏi ánh xạ hiện tại | Không hỗ trợ |
| Entry từ iterator `TreeMap.entrySet()` trong khi đang lặp hợp lệ | Có liên kết trong phạm vi hợp đồng iterator | Hỗ trợ thay value trong map |
| `new AbstractMap.SimpleEntry<>(source)` | Đối tượng riêng, không liên kết map nguồn | Sửa được value của bản riêng |
| `new AbstractMap.SimpleImmutableEntry<>(source)` | Đối tượng riêng, không liên kết map nguồn | Không hỗ trợ |
| Entry từ một map/lớp bao khác | Phải xem hợp đồng cụ thể | Không suy đoán từ tên kiểu |

`Map.Entry` không có `setKey`. Thay khóa là một thao tác khác trên map, thường cần chọn cách xóa/thêm phù hợp và giữ đúng quy tắc thứ tự; không thực hiện bằng một setter của entry.

## 4. Cập nhật qua map: chọn đúng ý nghĩa

### 4.1. put: tạo hoặc thay ánh xạ tại khóa

Sau khi chọn được một entry:

```java
// Đoạn minh họa, chạy trong điều kiện truy cập names được kiểm soát.
Map.Entry<Integer, String> selected = names.floorEntry(15);
if (selected != null) {
    names.put(selected.getKey(), "replacement");
}
```

Thao tác sửa xảy ra trên map, không qua entry. Nếu khóa đã bị xóa trước lần put, put có thể tạo lại ánh xạ. Điều này có thể đúng hoặc sai tùy yêu cầu.

Nếu muốn “chỉ sửa khi khóa vẫn hiện diện”, `replace(key, newValue)` diễn đạt gần yêu cầu đó hơn put. Giá trị trả về của dạng replace này có thể null, nên cần xét chính sách value null nếu muốn diễn giải kết quả.

### 4.2. replace có expectedValue: không ghi đè khi giá trị đã khác

Nếu chỉ muốn thay khi ánh xạ hiện tại vẫn có giá trị bằng giá trị đã quan sát:

```java
// Đoạn minh họa trong ngữ cảnh một luồng hoặc có đồng bộ phù hợp.
Map.Entry<Integer, String> selected = names.floorEntry(15);
if (selected != null) {
    boolean changed = names.replace(
            selected.getKey(), selected.getValue(), "replacement");
    System.out.println(changed);
}
```

Dạng ba đối số trả boolean. Nó so giá trị theo quan hệ bằng phù hợp của `Map`, không yêu cầu hai tham chiếu phải là cùng một đối tượng.

Trong chương trình bên dưới, entry cũ lưu `alpha` nhưng ánh xạ đã thành `via-iterator`, nên thay có điều kiện với giá trị cũ trả false.

Giới hạn cần hiểu:

- Nó kiểm tra giá trị tại **khóa đã chọn**, không tự kiểm tra khóa ấy còn là kết quả đúng của `floorEntry(15)` hay không nếu có khóa mới được thêm.
- Một giá trị hiện tại bằng expectedValue không chứng minh chưa từng có thay đổi trung gian.
- Trên `TreeMap`, không mặc định lời gọi replace hoặc chuỗi chọn rồi replace an toàn trước nhiều luồng cùng sửa. Cần kiểm soát truy cập theo hợp đồng của cấu trúc cụ thể.

Snapshot giúp biết đã nhìn thấy gì; nó không phải số phiên bản hoặc cơ chế khóa lạc quan hoàn chỉnh.

### 4.3. Thay qua entrySet iterator trong phạm vi hợp lệ

Với `TreeMap`, có thể thay value trong lúc lặp qua entry set:

```java
// Đoạn minh họa.
for (Map.Entry<Integer, String> entry : names.entrySet()) {
    if (entry.getKey() == 10) {
        entry.setValue("via-iterator");
    }
}
```

Đây là entry có nguồn gốc khác với `floorEntry`. Thay value qua `setValue` được hỗ trợ bởi `TreeMap`; vòng lặp không tự thêm/xóa khóa.

Không giữ entry từ iterator rồi dựa vào việc nó còn liên kết sau khi đã kết thúc vòng lặp hoặc sau các thay đổi khác của map. Hợp đồng `Map.Entry` giới hạn tính liên kết trong quá trình lặp hợp lệ. Entry lấy qua stream, toArray hoặc sao chép thô tập entry cũng không được giả định luôn có cùng loại liên kết. Xem [Map.Entry API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.Entry.html).

Nếu cần chuyển dữ liệu cho một lớp khác hoặc giữ lại lâu, hãy tạo một cặp độc lập có hợp đồng rõ ràng.

## 5. Bản sao sửa được không có nghĩa sửa được map nguồn

Tạo bản riêng:

```java
// Đoạn minh họa.
Map.Entry<Integer, String> copy =
        new AbstractMap.SimpleEntry<>(saved);
copy.setValue("copy-only");
```

Sau đó:

```text
copy có value "copy-only".
saved không bị thay tham chiếu value.
map nguồn không bị thay ánh xạ.
```

`SimpleEntry` là một cặp riêng, có value sửa được và không liên kết với map nguồn. Constructor sao chép entry không biến nó thành một tay nắm map. Hợp đồng này được ghi trong [SimpleEntry API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).

Nếu nhu cầu là soạn dữ liệu trung gian rồi quyết định lưu, bản riêng có thể hữu ích. Bước lưu vào map vẫn phải là một thao tác rõ ràng, kiểm tra điều kiện cần thiết tại thời điểm lưu.

## 6. Snapshot nông và thay đổi bên trong value

### 6.1. Hai lớp tham chiếu

Với `NavigableMap<Integer, List<String>>`:

```text
map[1] ----+
          +--> ArrayList ["A"]
saved.V --+
```

Snapshot giữ cùng tham chiếu tới danh sách. Nếu gọi:

```java
// Đoạn minh họa với mutableValues có ánh xạ tại khóa 1.
mutableValues.get(1).add("B");
```

Cả map lẫn saved đều có thể quan sát `["A", "B"]`. Ta không gọi `saved.setValue`, nhưng đã sửa **đối tượng mà value trỏ tới**.

Nếu thay ánh xạ sang một danh sách mới:

```java
// Đoạn minh họa.
mutableValues.put(1, new ArrayList<>(List.of("X")));
```

Bây giờ:

```text
map[1] -----> ArrayList ["X"]

saved.V ----> ArrayList ["A", "B"]
```

Sửa nội dung một đối tượng và thay tham chiếu value trong map là hai việc khác nhau.

### 6.2. Tạo dữ liệu có mức cô lập phù hợp

Với danh sách chứa các `String` bất biến, có thể chụp cấu trúc danh sách:

```java
// Đoạn minh họa.
List<String> valueCopy = List.copyOf(savedListEntry.getValue());
Map.Entry<Integer, List<String>> copy =
        new AbstractMap.SimpleImmutableEntry<>(
                savedListEntry.getKey(), valueCopy);
```

Sau đó, thay đổi cấu trúc danh sách gốc không làm valueCopy đổi. Nhưng nếu phần tử trong danh sách là các đối tượng mutable, `List.copyOf` vẫn chỉ chép tham chiếu tới chúng. Nó không sao chép sâu cả đồ thị đối tượng.

`List.copyOf` còn không nhận nguồn null hoặc phần tử null. Cách chụp dữ liệu phải phù hợp với miền dữ liệu, không áp dụng máy móc.

Nếu khóa cũng mutable, snapshot có thể chia sẻ chính đối tượng khóa. Việc cố sửa đối tượng khóa qua `getKey()` không phải lối đi hợp lệ để đổi khóa trong map; nó còn có thể phá giả định thứ tự của cây. Dùng khóa bất biến.

### 6.3. Không sửa được cặp tham chiếu khác với bất biến sâu

`SimpleImmutableEntry` không hỗ trợ thay value bằng setValue và không liên kết với map, nhưng các đối tượng key/value bên trong vẫn có thể mutable. Tên lớp không phải lời hứa sao chép sâu hoặc đóng băng toàn bộ dữ liệu. Xem [SimpleImmutableEntry API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Muốn truyền một kết quả đáng tin cậy qua nhiều lớp, nên thiết kế kiểu giá trị rõ ràng và bất biến khi phù hợp, thay vì chỉ bọc một value mutable trong entry không sửa được.

## 7. Null và các factory tạo entry

Entry null và value null là hai tình huống khác nhau:

- `floorEntry` có thể trả null nếu không có khóa thỏa điều kiện.
- `TreeMap` có thể chứa một ánh xạ với value null và vẫn trả một entry khác null.

Phải kiểm tra entry trước khi gọi `getKey` hoặc `getValue`.

Khi tạo một cặp độc lập:

- `Map.entry(key, value)` không nhận key/value null.
- `Map.Entry.copyOf(entry)` tạo entry tách khỏi map và cũng không nhận thành phần null.
- `AbstractMap.SimpleImmutableEntry` có thể dùng để giữ một cặp có thành phần null theo chính sách dữ liệu thích hợp.

Không đổi sang factory khác chỉ vì tên ngắn hơn mà bỏ qua chính sách null. Các lựa chọn này đều vẫn không phải sao chép sâu đối tượng key/value.

## 8. Chương trình hoàn chỉnh

Lưu thành **EntrySnapshotDemo.java**. Chương trình chạy bằng Java 17 trở lên. Nó cố ý đối chiếu snapshot điều hướng, entry của iterator, bản sao riêng, thay có điều kiện, poll và value mutable.

```java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class EntrySnapshotDemo {
    public static void main(String[] args) {
        NavigableMap<Integer, String> names = new TreeMap<>();
        names.put(10, "alpha");
        names.put(20, "beta");

        Map.Entry<Integer, String> saved = names.floorEntry(15);
        System.out.println("Saved: " + saved);
        names.put(10, "alpha-new");
        System.out.println("Saved after put: " + saved);
        System.out.println("Current: " + names.get(10));
        try {
            saved.setValue("via-snapshot");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot setValue rejected");
        }

        for (Map.Entry<Integer, String> entry : names.entrySet()) {
            if (entry.getKey() == 10) entry.setValue("via-iterator");
        }
        System.out.println("After iterator setValue: " + names);

        Map.Entry<Integer, String> independent =
                new AbstractMap.SimpleEntry<>(saved);
        independent.setValue("copy-only");
        System.out.println("Mutable copy: " + independent);
        System.out.println("Map after copy change: " + names.get(10));

        boolean staleReplace =
                names.replace(saved.getKey(), saved.getValue(), "attempt");
        System.out.println("Replace with stale value: " + staleReplace);
        Map.Entry<Integer, String> current = names.floorEntry(15);
        boolean freshReplace =
                names.replace(current.getKey(), current.getValue(), "confirmed");
        System.out.println("Replace with current value: " + freshReplace);
        System.out.println("Map after replace: " + names);

        Map.Entry<Integer, String> removed = names.pollFirstEntry();
        System.out.println("Polled snapshot: " + removed);
        System.out.println("Key still exists: " +
                names.containsKey(removed.getKey()));

        NavigableMap<Integer, List<String>> mutableValues = new TreeMap<>();
        mutableValues.put(1, new ArrayList<>(List.of("A")));
        Map.Entry<Integer, List<String>> shallow =
                mutableValues.firstEntry();
        mutableValues.get(1).add("B");
        System.out.println("Shared value after add: " + shallow.getValue());
        mutableValues.put(1, new ArrayList<>(List.of("X")));
        System.out.println("Saved after replacing list: " + shallow.getValue());
        System.out.println("Current list: " + mutableValues.get(1));

        List<String> copiedValue = List.copyOf(shallow.getValue());
        Map.Entry<Integer, List<String>> isolated =
                new AbstractMap.SimpleImmutableEntry<>(
                        shallow.getKey(), copiedValue);
        shallow.getValue().add("C");
        System.out.println("Original shared list: " + shallow.getValue());
        System.out.println("Copied value: " + isolated.getValue());

        NavigableMap<Integer, String> nullable = new TreeMap<>();
        nullable.put(5, null);
        Map.Entry<Integer, String> withNull = nullable.firstEntry();
        Map.Entry<Integer, String> nullSafeCopy =
                new AbstractMap.SimpleImmutableEntry<>(withNull);
        System.out.println("Null value snapshot: " + nullSafeCopy);
        try {
            Map.entry(withNull.getKey(), withNull.getValue());
        } catch (NullPointerException ex) {
            System.out.println("Map.entry rejects null");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 EntrySnapshotDemo.java
java EntrySnapshotDemo
```

Kết quả chuẩn:

```text
Saved: 10=alpha
Saved after put: 10=alpha
Current: alpha-new
Snapshot setValue rejected
After iterator setValue: {10=via-iterator, 20=beta}
Mutable copy: 10=copy-only
Map after copy change: via-iterator
Replace with stale value: false
Replace with current value: true
Map after replace: {10=confirmed, 20=beta}
Polled snapshot: 10=confirmed
Key still exists: false
Shared value after add: [A, B]
Saved after replacing list: [A, B]
Current list: [X]
Original shared list: [A, B, C]
Copied value: [A, B]
Null value snapshot: 5=null
Map.entry rejects null
```

Dòng `Saved after put` chứng minh entry không tự cập nhật khi thay ánh xạ. Dòng `After iterator setValue` chứng minh nguồn gốc entry quyết định khả năng sửa. Hai dòng về danh sách chứng minh giới hạn của ảnh chụp nông.

## 9. Cách chọn khi thiết kế hàm trả kết quả

| Nhu cầu | Lựa chọn và giới hạn |
| --- | --- |
| Đọc một ánh xạ đã được chọn | Giữ entry điều hướng; hiểu nó có thể khác map hiện tại sau này |
| Sửa ánh xạ hiện tại tại khóa | Dùng map API, chọn put/replace theo yêu cầu |
| Sửa từng value khi đang duyệt TreeMap | Dùng entrySet iterator hợp lệ và setValue được hỗ trợ |
| Giữ một cặp trung gian có value sửa được | SimpleEntry, không liên kết map nguồn |
| Giữ cặp không thay được tham chiếu value | SimpleImmutableEntry hoặc factory phù hợp chính sách null |
| Chụp dữ liệu để dùng độc lập | Sao chép hoặc dùng kiểu bất biến cho cả nội dung cần cô lập |
| Cập nhật chỉ khi trạng thái đã quan sát vẫn hợp lệ | Kiểm tra điều kiện/version theo nghiệp vụ và cơ chế đồng bộ phù hợp |

Nếu một API chỉ muốn công bố “khóa được chọn và thông tin hiển thị”, có thể trả một record riêng thay vì để bên gọi đoán hợp đồng `Map.Entry`. Nhưng record chứa value mutable vẫn cần chính sách sao chép hoặc sở hữu; đổi lớp bao không tự giải quyết chia sẻ dữ liệu.

## 10. Lỗi thường gặp và bài tập

| Lỗi | Hậu quả |
| --- | --- |
| Thấy setValue trên interface nên gọi được trên mọi entry | UnsupportedOperationException |
| Coi snapshot là góc nhìn tự đổi theo put | Đọc dữ liệu đã cũ mà tưởng là hiện tại |
| Sửa bản SimpleEntry và chờ map đổi | Chỉ bản sao thay đổi |
| Coi setValue không được hỗ trợ là value bất biến | Vẫn có thể sửa đối tượng mutable bên trong |
| Sao chép danh sách nhưng không xét phần tử bên trong | Chưa cô lập các đối tượng mutable |
| Giữ entry iterator làm tay nắm cập nhật lâu dài | Vượt phạm vi hợp đồng liên kết |
| Cập nhật bằng put sau khi khóa bị xóa | Có thể tạo lại ánh xạ ngoài mong muốn |
| Dùng snapshot như bằng chứng không có thay đổi đồng thời | Không có version hoặc quyền sở hữu tự động |
| Thay factory tạo entry mà quên null | Lỗi dữ liệu hợp lệ ở miền có null |

Bài tập tự kiểm chứng:

1. Tạo map `{5=A, 10=B}`, lấy `floorEntry(7)` rồi thay ánh xạ tại khóa 5 thành C. Entry cũ phải vẫn biểu diễn A, còn lần truy vấn mới biểu diễn C.
2. Thử setValue trên entry điều hướng và trên entry nhận trong vòng lặp entrySet của TreeMap. Giải thích vì sao hai kết quả khác nhau dù cùng kiểu Map.Entry.
3. Tạo SimpleEntry từ entry cũ, thay value thành D. Chứng minh map không bị sửa.
4. Với value là ArrayList chứa `"A"`, thêm `"B"` qua tham chiếu lấy từ map rồi thay map sang danh sách `["X"]`. Dự đoán snapshot thấy gì sau từng bước.
5. Dùng replace ba đối số với giá trị đã cũ. Nó phải trả false khi ánh xạ hiện tại có giá trị khác, trong điều kiện truy cập một luồng của ví dụ.
6. Tạo một ánh xạ có value null và chụp bằng SimpleImmutableEntry. Thử Map.entry trên cùng cặp và giải thích chính sách null khác nhau.

Khi làm việc với entry, hãy xác định nguồn gốc của nó, mức liên kết với map và mức thay đổi của từng đối tượng được tham chiếu. Một snapshot của ánh xạ chỉ có ý nghĩa chính xác khi ba điều đó được hiểu rõ.
