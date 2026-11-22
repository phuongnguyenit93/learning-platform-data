# firstEntry, lastEntry và các thao tác poll trong NavigableMap

## 1. Xem một đầu hay lấy nó ra khỏi map?

Giả sử một `NavigableMap<Integer, String>` giữ các công việc theo khóa ưu tiên:

```text
10 -> urgent
20 -> index
30 -> archive
```

Trong ví dụ, khóa số nhỏ hơn nghĩa là ưu tiên cao hơn. Ta có hai nhu cầu khác nhau:

- **Xem** công việc ưu tiên cao nhất nhưng vẫn giữ trong map.
- **Lấy và xóa** công việc ấy để xử lý.

`firstEntry()` và `lastEntry()` phục vụ việc xem hai đầu. `pollFirstEntry()` và `pollLastEntry()` lấy ánh xạ ở một đầu rồi xóa nó.

| Phương thức | Ánh xạ được chọn | Có xóa khỏi map? | Khi map rỗng |
| --- | --- | --- | --- |
| `firstEntry()` | Ánh xạ đầu theo thứ tự khóa | Không | `null` |
| `lastEntry()` | Ánh xạ cuối theo thứ tự khóa | Không | `null` |
| `pollFirstEntry()` | Ánh xạ đầu theo thứ tự khóa | Có | `null` |
| `pollLastEntry()` | Ánh xạ cuối theo thứ tự khóa | Có | `null` |

Cả bốn trả `Map.Entry<K, V>`, chứa cả khóa và giá trị. Đây là hợp đồng hiện hành của [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Các ví dụ dưới đây chạy bằng Java 17 trở lên và dùng `TreeMap` làm cách cài đặt cụ thể.

## 2. “Đầu” và “cuối” do thứ tự khóa quyết định

### 2.1. Không phải thứ tự thêm vào

Với `TreeMap` theo khóa số tăng dần, thêm lần lượt 30, 10, 20 vẫn tạo thứ tự `[10, 20, 30]`.

```text
firstEntry() -> 10=urgent
lastEntry()  -> 30=archive
```

`firstEntry` không có nghĩa “ánh xạ được thêm sớm nhất”. `lastEntry` không có nghĩa “ánh xạ vừa được cập nhật”. Giá trị `urgent`, `index`, `archive` cũng không tham gia xác định hai đầu.

Nếu V chứa độ ưu tiên nhưng K chỉ là mã công việc không liên quan, `firstEntry()` sẽ chọn theo mã. Muốn dùng các thao tác đầu/cuối để xử lý theo ưu tiên, khóa phải thể hiện đúng quy tắc ưu tiên mong muốn.

### 2.2. Comparator có thể đảo hai đầu

Một map dùng `Comparator.reverseOrder()` có thứ tự khóa số giảm dần. Khi ấy ánh xạ đầu có khóa số lớn nhất, còn ánh xạ cuối có khóa số nhỏ nhất.

Quy tắc tổng quát: đầu là vị trí nhỏ nhất **theo comparator của map**, không nhất thiết theo giá trị số tự nhiên.

Không sửa các trường tham gia so sánh của một khóa đang nằm trong `TreeMap`. Cây không tự dời khóa sau khi đối tượng bị đổi, nên cả việc tìm kiếm lẫn chọn hai đầu có thể mất ý nghĩa đúng đắn. Ưu tiên khóa bất biến.

## 3. Xem ánh xạ: dữ liệu còn trong map

### 3.1. firstEntry và lastEntry không làm giảm kích thước

Gọi nhiều lần trên map không thay đổi sẽ tiếp tục nhận ánh xạ cùng đầu:

```text
Map ban đầu: {10=urgent, 20=index, 30=archive}

firstEntry() -> 10=urgent
firstEntry() -> 10=urgent

Map vẫn có 3 ánh xạ.
```

Điều này phù hợp cho hiển thị công việc tiếp theo, kiểm tra một điều kiện trước khi quyết định hoặc đọc phạm vi khóa hiện tại.

Nhưng nếu viết vòng lặp gọi `firstEntry()` mà không xóa hoặc thay đổi dữ liệu, vòng lặp có thể xử lý mãi cùng ánh xạ. Hàm không lưu vị trí duyệt và không tự chuyển sang phần tử tiếp theo.

### 3.2. Khác với firstKey và lastKey khi rỗng

`firstKey()` và `lastKey()` chỉ trả khóa, nhưng trên map rỗng chúng ném `NoSuchElementException`.

`firstEntry()` và `lastEntry()` trả null trên map rỗng. Vì vậy, khi cần cả dữ liệu và muốn xử lý trạng thái rỗng bằng nhánh điều kiện, dạng Entry thường diễn đạt thuận tiện hơn.

Không viết:

```java
// Đoạn minh họa lỗi nếu jobs có thể rỗng.
String value = jobs.firstEntry().getValue();
```

Hãy giữ kết quả và kiểm tra:

```java
// Đoạn minh họa, jobs có kiểu NavigableMap<Integer, String>.
Map.Entry<Integer, String> next = jobs.firstEntry();
if (next == null) {
    System.out.println("Khong con cong viec");
} else {
    System.out.println(next.getKey() + ": " + next.getValue());
}
```

### 3.3. Null entry khác value null

`TreeMap` cho phép giá trị V là null. Khi đó:

- `entry == null`: không có ánh xạ ở đầu vì map đang rỗng.
- `entry != null` nhưng `entry.getValue() == null`: có ánh xạ, chỉ là giá trị của nó đang null.

Không dùng `getValue() != null` làm điều kiện duy nhất để nhận biết còn ánh xạ. Khóa null là một chính sách riêng của thứ tự khóa; bài này không dùng khóa null, và `TreeMap` theo thứ tự tự nhiên không chấp nhận chúng.

## 4. Poll: trả kết quả và loại ánh xạ

### 4.1. Chuyển trạng thái của map

Với map ban đầu:

```text
{10=urgent, 20=index, 30=archive}
```

Gọi:

```text
pollFirstEntry() -> 10=urgent
Map sau đó       -> {20=index, 30=archive}

pollLastEntry()  -> 30=archive
Map sau đó       -> {20=index}
```

Mỗi lần poll có kết quả khác null xóa đúng một ánh xạ ở đầu tương ứng. Nếu chỉ có một ánh xạ, first và last cùng trỏ vào ánh xạ ấy; poll ở bất cứ đầu nào cũng làm map rỗng.

Kết quả trả về vẫn giữ khóa và giá trị của ánh xạ vừa lấy, dù ánh xạ đó không còn nằm trong map.

### 4.2. Poll không chờ dữ liệu

Map rỗng thì poll trả null; nó không đợi một producer thêm công việc. Đây không phải thao tác lấy có chờ của một hàng đợi chặn.

Trên map hoặc góc nhìn không cho sửa, thao tác xóa có thể không được hỗ trợ và ném `UnsupportedOperationException`. Cần biết khả năng sửa của đối tượng cụ thể, không chỉ nhìn kiểu giao diện `NavigableMap`.

### 4.3. Xử lý cho đến khi rỗng

Trong một luồng sở hữu map, có thể lấy lần lượt đầu nhỏ nhất:

```java
// Đoạn minh họa, jobs có kiểu NavigableMap<Integer, String>.
Map.Entry<Integer, String> job;
while ((job = jobs.pollFirstEntry()) != null) {
    System.out.println(job.getKey() + ": " + job.getValue());
}
```

Bất biến của vòng lặp: mỗi lần thân vòng lặp chạy, một ánh xạ đã được lấy ra khỏi map; với dữ liệu hữu hạn không được thêm mới, số ánh xạ giảm dần tới 0.

Cách này **tiêu thụ dữ liệu**. Nếu chỉ muốn in báo cáo hoặc duyệt mà không xóa, dùng vòng lặp trên `entrySet()`.

Không cần thêm một lần `isEmpty()` trước mỗi poll chỉ để biết có kết quả hay không. Việc kiểm tra kết quả trả về phản ánh trực tiếp lần lấy đã thực hiện. Tuy nhiên, điều đó không biến `TreeMap` thành cấu trúc an toàn khi nhiều luồng cùng sửa.

### 4.4. Xóa trước xử lý có hệ quả nghiệp vụ

Trong vòng lặp trên, job đã bị xóa **trước khi** bước xử lý bên trong hoàn tất. Nếu bước xử lý ném lỗi, công việc không tự quay lại map.

Do đó, ví dụ phù hợp để hiểu chuyển trạng thái trong bộ nhớ; nó không tự cung cấp cơ chế hàng đợi bền vững, xác nhận hoàn thành hoặc thử lại. Nếu yêu cầu không được mất công việc khi xử lý thất bại, cần thiết kế trạng thái đang xử lý, chiến lược phục hồi hoặc một cơ chế lưu trữ/hàng đợi thích hợp.

Tương tự, poll trả được một job không có nghĩa một tác động bên ngoài như ghi tệp hoặc gọi dịch vụ sẽ tự thành công đúng một lần.

## 5. Entry trả về là ảnh chụp, không phải tay nắm cập nhật

### 5.1. Thay ánh xạ không làm entry cũ đổi theo

Giả sử:

```text
saved = firstEntry() -> 10=urgent
put(10, "urgent-updated")
```

Entry đã giữ vẫn biểu diễn `10=urgent`, còn một lần `firstEntry()` mới trả `10=urgent-updated`.

Các entry trả về từ các phương thức đang học đại diện cho ánh xạ ở thời điểm gọi. Trên `TreeMap`, chúng không hỗ trợ `setValue`. Muốn thay giá trị hiện tại, thực hiện thao tác trên map phù hợp như `put`, thay vì gọi `setValue` trên entry cũ. Đặc điểm này được nêu trong [TreeMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Entry lấy qua một API khác không nhất thiết có cùng hợp đồng; không tổng quát rằng mọi `Map.Entry` trong Java đều không sửa được.

### 5.2. Ảnh chụp nông không đóng băng đối tượng value

Nếu V là `String`, nó bất biến nên ví dụ entry cũ dễ hiểu. Nếu V là `StringBuilder`:

```text
Map giữ: 1 -> một StringBuilder có nội dung "a"
saved = firstEntry()
Sửa chính StringBuilder đó bằng append("b")
saved.getValue() quan sát được "ab"
```

Entry không cho thay tham chiếu value bằng `setValue`, nhưng tham chiếu nó đang giữ vẫn có thể trỏ tới một đối tượng mutable.

Phân biệt:

- `map.put(key, newValue)`: thay tham chiếu trong ánh xạ hiện tại.
- Sửa chính đối tượng V đang được chia sẻ: các tham chiếu cùng trỏ tới nó đều có thể quan sát thay đổi.

Muốn một bản chụp dữ liệu bất biến, phải thiết kế V bất biến hoặc sao chép dữ liệu đủ sâu theo nhu cầu.

## 6. Tác động khi dùng góc nhìn đảo hoặc có giới hạn

### 6.1. descendingMap đảo đầu và cuối

Map gốc:

```text
{1=one, 2=two, 3=three}
```

Góc nhìn `descendingMap()` có thứ tự:

```text
{3=three, 2=two, 1=one}
```

Vì vậy:

| Thao tác trên góc nhìn đảo | Kết quả | Ảnh hưởng tập gốc |
| --- | --- | --- |
| `firstEntry()` | `3=three` | Không sửa |
| `lastEntry()` | `1=one` | Không sửa |
| `pollFirstEntry()` | Lấy `3=three` | Xóa khóa lớn nhất của map gốc |
| `pollLastEntry()` | Lấy `1=one` | Xóa khóa nhỏ nhất của map gốc |

Góc nhìn đảo liên kết với cùng dữ liệu. Nó không phải một map sao chép riêng để có thể thoải mái tiêu thụ mà giữ nguyên map gốc.

### 6.2. subMap chỉ xét và xóa trong phạm vi nhìn thấy

Với map `{1=one, 2=two, 3=three, 4=four}`, tạo:

```java
// Đoạn minh họa.
NavigableMap<Integer, String> window =
        ranged.subMap(2, true, 4, false);
```

Window chứa `{2=two, 3=three}`. Đầu là 2, cuối là 3. `window.pollLastEntry()` lấy và xóa khóa 3 khỏi map gốc; các khóa 1 và 4 không bị lấy vì nằm ngoài cửa sổ.

Một góc nhìn có thể rỗng trong khi map gốc không rỗng. Khi ấy `firstEntry`, `lastEntry` và các poll trên góc nhìn trả null. Null phải được hiểu theo **phạm vi đang thao tác**, không nhất thiết theo toàn bộ map gốc.

## 7. Chương trình hoàn chỉnh

Lưu thành **NavigableMapEnds.java**. Chương trình minh họa riêng việc xem, lấy/xóa, trạng thái rỗng, góc nhìn đảo, cửa sổ và ảnh chụp nông của value.

```java
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NavigableMapEnds {
    public static void main(String[] args) {
        NavigableMap<Integer, String> jobs = new TreeMap<>();
        jobs.put(30, "archive");
        jobs.put(10, "urgent");
        jobs.put(20, "index");
        Map.Entry<Integer, String> saved = jobs.firstEntry();
        System.out.println("First: " + saved);
        System.out.println("Last: " + jobs.lastEntry());
        System.out.println("Size after peek: " + jobs.size());

        jobs.put(10, "urgent-updated");
        System.out.println("Saved entry: " + saved);
        System.out.println("Current first: " + jobs.firstEntry());
        try {
            saved.setValue("changed");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Saved entry is not a write handle");
        }

        System.out.println("Poll first: " + jobs.pollFirstEntry());
        System.out.println("After poll first: " + jobs);
        System.out.println("Poll last: " + jobs.pollLastEntry());
        System.out.println("After poll last: " + jobs);

        Map.Entry<Integer, String> job;
        while ((job = jobs.pollFirstEntry()) != null) {
            System.out.println("Process: " + job);
        }
        System.out.println("Empty firstEntry: " + jobs.firstEntry());
        System.out.println("Empty lastEntry: " + jobs.lastEntry());
        System.out.println("Empty pollFirstEntry: " + jobs.pollFirstEntry());
        System.out.println("Empty pollLastEntry: " + jobs.pollLastEntry());
        try {
            jobs.firstKey();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("Empty firstKey throws");
        }

        NavigableMap<Integer, String> base = new TreeMap<>();
        base.put(1, "one");
        base.put(2, "two");
        base.put(3, "three");
        NavigableMap<Integer, String> reverse = base.descendingMap();
        System.out.println("Reverse first/last: " +
                reverse.firstEntry() + "/" + reverse.lastEntry());
        System.out.println("Reverse poll first: " + reverse.pollFirstEntry());
        System.out.println("Reverse poll last: " + reverse.pollLastEntry());
        System.out.println("Base after reverse polls: " + base);

        NavigableMap<Integer, String> ranged = new TreeMap<>();
        ranged.put(1, "one");
        ranged.put(2, "two");
        ranged.put(3, "three");
        ranged.put(4, "four");
        NavigableMap<Integer, String> window =
                ranged.subMap(2, true, 4, false);
        System.out.println("Window first/last: " +
                window.firstEntry() + "/" + window.lastEntry());
        System.out.println("Window poll last: " + window.pollLastEntry());
        System.out.println("Base after window poll: " + ranged);

        NavigableMap<Integer, StringBuilder> mutableValues = new TreeMap<>();
        mutableValues.put(1, new StringBuilder("a"));
        Map.Entry<Integer, StringBuilder> shallow =
                mutableValues.firstEntry();
        mutableValues.get(1).append("b");
        System.out.println("Shallow snapshot value: " + shallow.getValue());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 NavigableMapEnds.java
java NavigableMapEnds
```

Kết quả chuẩn:

```text
First: 10=urgent
Last: 30=archive
Size after peek: 3
Saved entry: 10=urgent
Current first: 10=urgent-updated
Saved entry is not a write handle
Poll first: 10=urgent-updated
After poll first: {20=index, 30=archive}
Poll last: 30=archive
After poll last: {20=index}
Process: 20=index
Empty firstEntry: null
Empty lastEntry: null
Empty pollFirstEntry: null
Empty pollLastEntry: null
Empty firstKey throws
Reverse first/last: 3=three/1=one
Reverse poll first: 3=three
Reverse poll last: 1=one
Base after reverse polls: {2=two}
Window first/last: 2=two/3=three
Window poll last: 3=three
Base after window poll: {1=one, 2=two, 4=four}
Shallow snapshot value: ab
```

Các dòng sau poll cho thấy dữ liệu thực sự bị loại. Dòng `Size after peek` chứng minh xem hai đầu không tiêu thụ dữ liệu. Dòng cuối chứng minh “entry không hỗ trợ setValue” không đồng nghĩa “mọi đối tượng được tham chiếu đều bất biến”.

## 8. Khi nào cách tổ chức này hữu ích?

### 8.1. Công việc theo khóa ưu tiên hoặc thời hạn

Nếu khóa là mức ưu tiên duy nhất hoặc thời điểm thực hiện duy nhất, đầu map có thể biểu diễn công việc cần xem trước. Nhưng một map chỉ có một giá trị cho mỗi khóa tương đương theo comparator.

Hai job cùng mức ưu tiên không tự trở thành hai ánh xạ. `put` lần thứ hai có thể thay giá trị của lần thứ nhất. Nếu cần giữ tất cả, phải có mô hình phù hợp, chẳng hạn khóa ghép gồm ưu tiên và mã phân biệt, hoặc mỗi mức ưu tiên ánh xạ tới một nhóm công việc.

Nếu cần thứ tự FIFO giữa các job cùng mức ưu tiên, khóa hoặc cấu trúc bên trong nhóm phải thể hiện quy tắc ấy. `TreeMap` không tự giữ thứ tự đến giữa các value bị ghi lên cùng khóa.

### 8.2. Loại dữ liệu quá cũ

Nếu khóa là thời gian tăng dần, `firstEntry()` giúp xem mốc cũ nhất. Chỉ khi mốc đó vượt điều kiện hết hạn mới quyết định poll nó. Bài toán này cần phân biệt “xem để kiểm tra” và “xóa”.

Trong môi trường một luồng sở hữu dữ liệu, có thể phối hợp hai bước theo quy tắc ứng dụng. Với nhiều luồng sửa dữ liệu, ánh xạ đầu có thể đổi giữa lúc xem và lúc poll; không mặc định hai bước chọn cùng một công việc.

### 8.3. Giới hạn dung lượng theo thứ tự

Một bộ lưu nhỏ có thể thêm dữ liệu rồi loại đầu nhỏ nhất hoặc lớn nhất khi vượt dung lượng. Tuy nhiên, đó là chính sách loại theo **khóa**, không phải tự động là LRU hoặc loại theo thời gian dùng gần nhất. Muốn LRU, dữ liệu phải có mô hình theo dõi lần truy cập phù hợp.

## 9. Chi phí và phối hợp thao tác

Với `TreeMap` dựa trên cây cân bằng, tìm các đầu và xóa một đầu có chi phí O(log n) trong trường hợp xấu nhất. Lặp poll cho đến khi xóa n ánh xạ có chi phí O(n log n). Nếu mục tiêu chỉ đọc hết theo thứ tự, duyệt iterator trên cây có thời gian O(n) và không xóa dữ liệu.

`NavigableMap` là giao diện, không áp đặt một cấu trúc bên trong hay cùng mức hiệu năng cho mọi cách cài đặt. Chi phí comparator cũng có thể ảnh hưởng thời gian thực tế.

`TreeMap` không tự đồng bộ truy cập nhiều luồng. Một lời gọi có tên “lấy và xóa” không biến mọi cách cài đặt `NavigableMap` thành một hàng đợi đồng thời an toàn. Nếu có nhiều bên truy cập, cần chọn cấu trúc và hợp đồng đồng thời phù hợp, hoặc bảo vệ toàn bộ chuỗi thao tác cần nhất quán.

Không dùng `ConcurrentModificationException` như cơ chế phối hợp. Fail-fast của iterator phục vụ phát hiện lỗi theo nỗ lực tốt nhất, không chứng minh rằng một lần poll hoặc một chuỗi xử lý là an toàn.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Hậu quả hoặc cách sửa |
| --- | --- |
| Gọi `pollFirstEntry` chỉ để xem | Vô tình mất ánh xạ; dùng `firstEntry` |
| Gọi `firstEntry` liên tục để tiêu thụ | Lặp lại mãi một ánh xạ |
| Đọc `getValue` trước khi kiểm tra null | Lỗi khi map hoặc góc nhìn rỗng |
| Coi value null là map rỗng | Kiểm tra chính entry |
| Nghĩ đầu là phần tử thêm sớm nhất | Đọc thứ tự comparator của khóa |
| Coi entry là tay nắm cập nhật | Cập nhật qua map theo hợp đồng |
| Coi ảnh chụp entry là sao chép sâu | Đối tượng V mutable vẫn có thể được chia sẻ |
| Poll trên góc nhìn và nghĩ map gốc giữ nguyên | Các góc nhìn liên kết cùng dữ liệu |
| Dùng mức ưu tiên làm khóa duy nhất cho nhiều job | Một lần put có thể thay job trước |
| Cho rằng poll xong là xử lý đã thành công | Phân biệt lấy khỏi bộ nhớ và hoàn tất nghiệp vụ |

Bài tập tự kiểm chứng:

1. Tạo map `{2=A, 5=B}`. Gọi first/last nhiều lần và kiểm tra kích thước vẫn là 2. Sau một `pollFirstEntry`, chỉ còn khóa 5.
2. Với map một ánh xạ, gọi `pollLastEntry`, rồi gọi cả bốn phương thức. Sau lần poll đầu, mọi kết quả Entry phải là null.
3. Tạo góc nhìn đảo của map `{1=A, 2=B, 3=C}`, poll đầu góc nhìn. Khóa bị xóa khỏi map gốc phải là 3.
4. Tạo cửa sổ nhận đoạn `[2, 4)` trên map có các khóa 1, 2, 3, 4. Poll cửa sổ đến rỗng; map gốc phải còn 1 và 4.
5. Lưu entry đầu, thay value tại khóa đó bằng `put`, rồi so entry cũ với entry mới. Thử riêng V là một đối tượng mutable và giải thích khác biệt.
6. Thử thêm hai job cùng khóa ưu tiên. Xác minh dữ liệu bị thay, rồi đề xuất khóa ghép hoặc cách nhóm dữ liệu để giữ đủ job.

Trước khi gọi các phương thức ở hai đầu, hãy chốt thứ tự khóa, phạm vi góc nhìn và việc chỉ xem hay thực sự tiêu thụ dữ liệu. Đó là ba quyết định làm rõ ý nghĩa của `firstEntry`, `lastEntry` và các thao tác poll.
