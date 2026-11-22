# Kiểm thử khóa biên, khoảng rỗng và thứ tự đảo

## 1. Kiểm thử điều gì thay vì chỉ in map?

Với `NavigableMap`, dữ liệu nằm giữa hai khóa thường cho kết quả dễ đoán. Các lỗi phổ biến lại xuất hiện ở nơi điều kiện thay đổi:

- Mốc truy vấn bằng một khóa đã có.
- Mốc nằm trước khóa nhỏ nhất hoặc sau khóa lớn nhất.
- Hai biên khoảng bằng nhau.
- Khoảng hợp lệ nhưng không chứa dữ liệu.
- Map sử dụng thứ tự đảo chiều.

Nếu chỉ in kết quả rồi nhìn bằng mắt, một thay đổi sai có thể bị bỏ qua. Một kiểm thử cần có **đầu vào cụ thể, kết quả mong đợi và điều kiện thất bại rõ ràng**.

Bài này dùng `TreeMap<Integer,String>` để giữ mô hình nhỏ và kiểm soát được. Mục tiêu là kiểm tra hợp đồng quan sát được của `NavigableMap`, không kiểm tra hình dạng cây bên trong JDK. API và cú pháp đều còn áp dụng trong Java hiện đại; chương trình độc lập dùng Java 17 trở lên.

## 2. Bộ dữ liệu nhỏ phải chứa các điểm phân biệt

Dùng map tăng dần:

```text
10 -> A
20 -> B
30 -> C
```

Các mốc truy vấn có chủ đích:

| Mốc | Vai trò |
| --- | --- |
| 5 | Trước mọi khóa |
| 10 | Đúng khóa đầu |
| 20 | Đúng khóa giữa |
| 25 | Không tồn tại, nằm giữa 20 và 30 |
| 30 | Đúng khóa cuối |
| 35 | Sau mọi khóa |

Ví dụ tại mốc 20:

```text
lowerEntry(20)   -> 10=A
floorEntry(20)   -> 20=B
ceilingEntry(20) -> 20=B
higherEntry(20)  -> 30=C
```

Tại mốc 25, `lower` và `floor` cùng chọn 20; `ceiling` và `higher` cùng chọn 30. Vì vậy chỉ thử 25 sẽ không phát hiện lỗi vô tình thay `floor` bằng `lower`.

Bốn phương thức trả null khi không có khóa phù hợp; điều kiện có/không chấp nhận bằng mốc khác nhau theo tên phương thức. Xem [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Khi yêu cầu cần cả khóa và giá trị, đừng chỉ kiểm tra khóa. Kiểm tra thêm giá trị đã gắn với khóa được chọn để phát hiện lỗi ghép kết quả.

## 3. Tách bốn ý nghĩa của “rỗng”

### Map gốc không có ánh xạ nào

Các truy vấn lân cận không tìm được Entry, bất kể mốc hợp lệ được chọn là gì.

### Khoảng hợp lệ nhưng không có khóa bên trong

Ví dụ `[11,19]` không chứa khóa nào của dữ liệu mẫu. Nó là một khoảng hợp lệ, không phải lỗi.

### Hai biên bằng nhau nhưng bị loại ở một phía

Khoảng `[20,20]` chứa khóa 20 nếu có; các khoảng `[20,20)`, `(20,20]` và `(20,20)` rỗng. Cần kiểm tra các tổ hợp để phát hiện nhầm cờ bao gồm biên.

### Hai biên sai thứ tự

Trên map tăng dần, từ 30 đến 10 không phải một khoảng rỗng hợp lệ. Yêu cầu bị từ chối bằng `IllegalArgumentException`.

Những trường hợp này không được gộp thành một nhánh “không có dữ liệu”. Hợp đồng khoảng của [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html) phân biệt khoảng hợp lệ, biên sai thứ tự và thao tác thêm khóa ngoài phạm vi view.

## 4. Đảo thứ tự phải kiểm tra cả hướng điều hướng

Map giảm dần của dữ liệu mẫu có thứ tự khóa `[30,20,10]`. Không chỉ vòng lặp duyệt đổi hướng; quan hệ điều hướng cũng đổi theo.

| Truy vấn trên map giảm dần | Kết quả khóa |
| --- | --- |
| lowerKey(20) | 30 |
| floorKey(20) | 20 |
| ceilingKey(20) | 20 |
| higherKey(20) | 10 |

Với một map và `descendingMap()` của chính nó, có thể kiểm tra các quan hệ đối xứng trên cùng mốc k:

```text
descending.lowerEntry(k)   = ascending.higherEntry(k)
descending.floorEntry(k)   = ascending.ceilingEntry(k)
descending.ceilingEntry(k) = ascending.floorEntry(k)
descending.higherEntry(k)  = ascending.lowerEntry(k)
```

Cả trường hợp kết quả null cũng phải tuân theo quan hệ này. Chọn nhiều mốc, gồm biên và mốc không tồn tại, giúp tránh một cặp dữ liệu ngẫu nhiên che lỗi.

Đồng thời phải đảo đúng thứ tự biên khoảng. Trên map giảm dần, khoảng từ 30 đến 10 là hợp lệ; từ 10 đến 30 không còn đúng thứ tự.

## 5. Chương trình kiểm thử độc lập

Chương trình tự ném `AssertionError` khi kết quả không đúng, nên không cần tùy chọn `-ea`. Nó không dùng từ khóa Java `assert`, và không cần JUnit để chạy.

Lưu tệp `NavigableMapBoundaryTest.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.Objects;
import java.util.TreeMap;

public class NavigableMapBoundaryTest {
    static NavigableMap<Integer, String> sample() {
        NavigableMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        return map;
    }

    static void equal(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    static List<Integer> keys(NavigableMap<Integer, String> map) {
        return new ArrayList<>(map.navigableKeySet());
    }

    static void expectIllegalArgument(Runnable action, String label) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError(label + ": expected IllegalArgumentException");
    }

    static void testNavigation() {
        NavigableMap<Integer, String> map = sample();
        equal(10, map.lowerKey(20), "lower at existing key");
        equal(20, map.floorKey(20), "floor at existing key");
        equal(20, map.ceilingKey(20), "ceiling at existing key");
        equal(30, map.higherKey(20), "higher at existing key");

        equal(20, map.lowerKey(25), "lower in gap");
        equal(20, map.floorKey(25), "floor in gap");
        equal(30, map.ceilingKey(25), "ceiling in gap");
        equal(30, map.higherKey(25), "higher in gap");

        equal(null, map.lowerEntry(10), "lower before first");
        equal(10, map.floorKey(10), "floor includes first");
        equal(30, map.ceilingKey(30), "ceiling includes last");
        equal(null, map.higherEntry(30), "higher after last");
        equal(null, map.floorEntry(5), "floor below all");
        equal(null, map.ceilingEntry(35), "ceiling above all");

        Map.Entry<Integer, String> found = map.floorEntry(25);
        equal(Map.entry(20, "B"), found, "entry key and value");
        equal(3, map.size(), "lookups do not remove");

        NavigableMap<Integer, String> empty = new TreeMap<>();
        equal(null, empty.lowerEntry(20), "empty lower");
        equal(null, empty.floorEntry(20), "empty floor");
        equal(null, empty.ceilingEntry(20), "empty ceiling");
        equal(null, empty.higherEntry(20), "empty higher");

        map.put(20, null);
        Map.Entry<Integer, String> nullValue = map.floorEntry(20);
        equal(true, nullValue != null, "null value is an existing entry");
        equal(null, nullValue.getValue(), "existing entry has null value");
    }

    static void testRanges() {
        NavigableMap<Integer, String> map = sample();

        equal(List.of(10, 20, 30),
                keys(map.subMap(10, true, 30, true)), "closed");
        equal(List.of(10, 20),
                keys(map.subMap(10, true, 30, false)), "left closed");
        equal(List.of(20, 30),
                keys(map.subMap(10, false, 30, true)), "right closed");
        equal(List.of(20),
                keys(map.subMap(10, false, 30, false)), "open");

        equal(List.of(10), keys(map.headMap(20, false)), "head excludes");
        equal(List.of(10, 20), keys(map.headMap(20, true)), "head includes");
        equal(List.of(30), keys(map.tailMap(20, false)), "tail excludes");
        equal(List.of(20, 30), keys(map.tailMap(20, true)), "tail includes");

        equal(List.of(20),
                keys(map.subMap(20, true, 20, true)), "equal closed");
        equal(List.of(),
                keys(map.subMap(20, true, 20, false)), "equal right open");
        equal(List.of(),
                keys(map.subMap(20, false, 20, true)), "equal left open");
        equal(List.of(),
                keys(map.subMap(20, false, 20, false)), "equal both open");

        NavigableMap<Integer, String> gap =
                map.subMap(11, true, 19, true);
        equal(true, gap.isEmpty(), "valid empty range");
        gap.put(15, "X");
        equal("X", map.get(15), "empty view accepts in-range key");

        expectIllegalArgument(
                () -> map.subMap(30, true, 10, true), "reversed bounds");

        NavigableMap<Integer, String> restricted =
                map.subMap(10, true, 30, false);
        expectIllegalArgument(
                () -> restricted.put(30, "NEW"), "excluded endpoint");
        equal("C", map.get(30), "failed endpoint write preserves value");
    }

    static void testReverse() {
        NavigableMap<Integer, String> ascending = sample();
        NavigableMap<Integer, String> descending = ascending.descendingMap();

        equal(List.of(30, 20, 10), keys(descending), "descending keys");
        equal(30, descending.lowerKey(20), "descending lower");
        equal(10, descending.higherKey(20), "descending higher");

        for (int query : new int[] {5, 10, 20, 25, 30, 35}) {
            equal(ascending.higherEntry(query),
                    descending.lowerEntry(query), "reverse lower " + query);
            equal(ascending.ceilingEntry(query),
                    descending.floorEntry(query), "reverse floor " + query);
            equal(ascending.floorEntry(query),
                    descending.ceilingEntry(query), "reverse ceiling " + query);
            equal(ascending.lowerEntry(query),
                    descending.higherEntry(query), "reverse higher " + query);
        }

        equal(List.of(30, 20),
                keys(descending.subMap(30, true, 10, false)),
                "descending range");
        expectIllegalArgument(
                () -> descending.subMap(10, true, 30, false),
                "wrong descending bounds");
        equal(ascending, descending.descendingMap(), "reverse twice");
    }

    public static void main(String[] args) {
        testNavigation();
        System.out.println("navigation=PASS");
        testRanges();
        System.out.println("ranges=PASS");
        testReverse();
        System.out.println("reverse=PASS");
        System.out.println("ALL PASS");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 NavigableMapBoundaryTest.java
java NavigableMapBoundaryTest
```

Stdout khi tất cả kiểm tra đúng:

```text
navigation=PASS
ranges=PASS
reverse=PASS
ALL PASS
```

Nếu một kiểm tra thất bại, chương trình ném `AssertionError` với nhãn, giá trị mong đợi và giá trị thực tế. Nó không in các dòng PASS của những nhóm chưa hoàn thành.

## 6. Vì sao bộ kiểm thử được tổ chức như vậy?

### So sánh kết quả có xử lý null

Hàm `equal` dùng `Objects.equals`, cho phép kiểm tra cả kết quả null mà không gọi phương thức trên null. Xem [Objects.equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

Đặc biệt, `equal(Map.entry(20,"B"), found,...)` kiểm tra cả khóa và giá trị. `Map.entry` không được dùng để tạo cặp có null trong ví dụ; trường hợp giá trị null được kiểm tra riêng sau đó.

### Ngoại lệ phải đúng loại

`expectIllegalArgument` chỉ coi `IllegalArgumentException` là kết quả mong đợi. Nếu hành động không ném lỗi, chính hàm kiểm thử thất bại. Nếu có một loại lỗi khác, lỗi đó không bị nuốt.

Điều này tránh kiểu kiểm thử bắt mọi `Exception` rồi kết luận thành công, dù chương trình thất bại vì nguyên nhân khác hoàn toàn.

### Không dùng equals của map để kiểm tra thứ tự duyệt

Hai map có cùng ánh xạ có thể bằng nhau theo `Map.equals` dù thứ tự duyệt khác nhau. Vì vậy chương trình chuyển các khóa thành `List` để kiểm tra chính xác `[30,20,10]`.

Kiểm tra `reverse twice` ở cuối chỉ xác nhận cùng ánh xạ; kiểm tra danh sách khóa phía trước mới xác nhận hướng duyệt.

### Mỗi nhóm có dữ liệu riêng

`sample()` tạo map mới cho từng nhóm. Thử giá trị null ở nhóm điều hướng không làm bẩn dữ liệu của nhóm khoảng. Việc thêm 15 để chứng minh view rỗng vẫn dùng được cũng không ảnh hưởng nhóm đảo chiều.

### Kết quả mong đợi không gọi lại chính thao tác đang thử

Kiểm tra `floorKey(20)` dùng mong đợi cụ thể 20, không gọi thêm một lần `floorKey(20)` để tính “đáp án”. Các quan hệ đối xứng của map đảo chỉ là kiểm tra bổ sung; những kết quả cụ thể như `descending.lowerKey(20)=30` vẫn giúp định nghĩa rõ hướng cần có.

## 7. Các tình huống nên bổ sung theo ứng dụng

Bộ ví dụ bao phủ những biên chính của khóa số nguyên, nhưng dữ liệu nghiệp vụ có thể cần thêm:

- Khóa nhỏ nhất/lớn nhất thực tế của kiểu được dùng, nhất là khi mã ứng dụng tự cộng/trừ để tạo biên.
- Khóa ghép có cùng tiêu chí chính nhưng khác tiêu chí phụ.
- Comparator riêng với các khóa được coi là tương đương.
- View con tại biên mà cha đã loại, để kiểm tra không mở rộng phạm vi.
- Xóa một khoảng qua view và xác nhận chỉ các ánh xạ phù hợp bị xóa ở gốc.
- Đổi giá trị trong map sau khi lấy Entry để kiểm tra hành vi ảnh chụp theo hợp đồng.
- Map chỉ có một ánh xạ và map có nhiều khoảng trống giữa khóa.

Không tạo khóa “ngay trước/ngay sau” bằng phép cộng hoặc trừ tùy tiện khi kiểu khóa không có quy tắc kế tiếp rõ ràng. Hãy chọn dữ liệu mẫu phù hợp với thứ tự được định nghĩa.

Nếu ứng dụng dùng cấu trúc đồng thời, cần kiểm thử riêng các yêu cầu đồng thời. Một chương trình một luồng báo ALL PASS không chứng minh các chuỗi thao tác giữa nhiều luồng đã an toàn.

## 8. Thử làm kiểm thử thất bại để xác nhận nó có ý nghĩa

Có thể thực hành trên bản mã riêng:

1. Trong kiểm tra điều hướng đầu tiên, thay `floorKey(20)` bằng `lowerKey(20)`. Kiểm tra phải báo mong đợi 20 nhưng thực tế 10.
2. Đổi cờ biên trên của khoảng `[10,30)` thành true nhưng giữ đáp án `[10,20]`. Kiểm tra phải thất bại vì có thêm 30.
3. Đổi `descending.lowerKey(20)` thành `descending.higherKey(20)` nhưng giữ đáp án 30. Kiểm tra phải nhận ra kết quả 10 là sai.
4. Xóa lời gọi trong lambda của một kiểm tra ngoại lệ để hành động không làm gì. Hàm kiểm tra ngoại lệ phải thất bại.

Các thử nghiệm này giúp xác nhận bộ kiểm thử có thể bắt đúng kiểu lỗi đang quan tâm. Khôi phục mã đúng sau từng lần để lỗi trước không che lỗi sau.

Mục tiêu là xác nhận điều kiện bằng tại biên, phân biệt rỗng với sai phạm vi, và đọc mọi quan hệ theo đúng thứ tự của map. Số lượng kiểm tra chỉ có ý nghĩa khi từng trường hợp bảo vệ một khác biệt cụ thể.
