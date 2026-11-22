# subMap, headMap, tailMap và cờ giới hạn

## 1. Chọn một khoảng khóa, giữ lại cả khóa và giá trị

Giả sử bản đồ dữ liệu có các ánh xạ:

```text
100 -> A
200 -> B
300 -> C
400 -> D
500 -> E
```

Ứng dụng cần làm việc với các bản ghi có khóa từ 200 đến 400. Yêu cầu ấy chưa rõ liệu khóa 200 và khóa 400 có được lấy hay không.

`NavigableMap<K,V>` cung cấp ba nhóm phương thức để diễn đạt khoảng theo khóa:

- `subMap`: giữa hai mốc.
- `headMap`: phần đầu đến một mốc.
- `tailMap`: phần đuôi từ một mốc.

Các cờ `boolean` cho biết có bao gồm khóa bằng mốc tương ứng hay không. Kết quả giữ nguyên các cặp khóa–giá trị thỏa điều kiện, chứ không chỉ lấy riêng khóa.

Mô hình cần hiểu là: **thứ tự khóa → điều kiện khoảng → cờ ở từng biên → một khung nhìn trên các ánh xạ phù hợp**. Bài dùng API còn áp dụng trong Java hiện đại; chương trình độc lập chạy với Java 17 trở lên.

## 2. Đọc đúng tham số và vai trò của cờ

Với khóa số nguyên có thứ tự tự nhiên tăng dần:

| Lời gọi | Điều kiện chọn khóa k |
| --- | --- |
| `subMap(from, fromInclusive, to, toInclusive)` | Nằm giữa from và to; mỗi cờ quyết định lấy/bỏ biên tương ứng |
| `headMap(to, true)` | k ≤ to |
| `headMap(to, false)` | k < to |
| `tailMap(from, true)` | k ≥ from |
| `tailMap(from, false)` | k > from |

Cờ `true` nhận khóa bằng biên; `false` loại khóa bằng biên. Các overload có cờ trả `NavigableMap<K,V>`. Xem [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Ví dụ minh họa trong phương thức, với `records` là map ở đầu bài:

```java
NavigableMap<Integer, String> middle =
        records.subMap(200, true, 400, false);
NavigableMap<Integer, String> earlier =
        records.headMap(300, true);
NavigableMap<Integer, String> later =
        records.tailMap(300, false);
```

Kết quả:

```text
middle  = {200=B, 300=C}
earlier = {100=A, 200=B, 300=C}
later   = {400=D, 500=E}
```

Giới hạn ở đây là **giới hạn khóa**, không phải giới hạn số lượng bản ghi, dung lượng lưu trữ hay điều kiện so sánh trên giá trị B/C/D.

## 3. Bốn khoảng của subMap

Với dữ liệu ban đầu:

| Lời gọi | Ký hiệu khoảng khóa | Kết quả |
| --- | --- | --- |
| `subMap(200, true, 400, true)` | [200, 400] | {200=B, 300=C, 400=D} |
| `subMap(200, true, 400, false)` | [200, 400) | {200=B, 300=C} |
| `subMap(200, false, 400, true)` | (200, 400] | {300=C, 400=D} |
| `subMap(200, false, 400, false)` | (200, 400) | {300=C} |

Dấu ngoặc vuông nhận đầu biên; dấu ngoặc tròn loại đầu biên. Trong lời gọi Java, mỗi cờ nằm ngay sau mốc mà nó điều khiển.

Một cách chống nhầm là viết bất đẳng thức trước:

```text
Muốn: 200 <= k < 400
Suy ra: from=200, fromInclusive=true
        to=400,   toInclusive=false
```

Nếu chia dữ liệu thành hai khoảng liên tiếp, dạng nửa mở giúp phân chia mốc chung rõ ràng. Chẳng hạn `[100,300)` và `[300,500)` chỉ đưa khóa 300 vào khoảng thứ hai.

Không cần tự tăng biên 400 thành 401 để nhận khóa 400. Cách đó gắn với một loại khóa cụ thể và có thể tràn miền giá trị; cờ bao gồm biên diễn đạt trực tiếp ý định.

## 4. Biên không cần tồn tại trong map

`subMap(210, true, 390, true)` trên dữ liệu ban đầu trả `{300=C}`. Không cần có ánh xạ cho 210 hoặc 390.

Một khoảng hợp lệ cũng có thể chưa chứa bản ghi nào. Ví dụ `subMap(210, true, 290, true)` ban đầu rỗng, nhưng sau khi gốc được thêm khóa 250, bản ghi đó sẽ xuất hiện trong khung nhìn.

Nếu hai biên đều bằng 300:

- `subMap(300, true, 300, true)` có thể chứa ánh xạ tại khóa 300, nếu khóa đó tồn tại.
- Nếu một trong hai đầu loại 300, kết quả rỗng.
- Cờ không tự tạo thêm ánh xạ; bao gồm biên chỉ có tác dụng với dữ liệu phù hợp đang tồn tại.

Một biên đi sau biên còn lại theo thứ tự của map làm yêu cầu khoảng không hợp lệ và gây `IllegalArgumentException`. Với map tăng dần, `subMap(400, true, 200, true)` là ví dụ sai thứ tự.

## 5. Quy ước của overload không có cờ

Các overload sau vẫn là API hiện hành với quy ước cố định:

| Lời gọi | Khoảng tương đương |
| --- | --- |
| `subMap(from, to)` | `subMap(from, true, to, false)` |
| `headMap(to)` | `headMap(to, false)` |
| `tailMap(from)` | `tailMap(from, true)` |

Các quy ước này thuộc hợp đồng [SortedMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/SortedMap.html).

Vì vậy, với dữ liệu ban đầu:

```text
subMap(200, 400) -> {200=B, 300=C}
headMap(300)    -> {100=A, 200=B}
tailMap(300)    -> {300=C, 400=D, 500=E}
```

Trên biến khai báo kiểu `NavigableMap<K,V>`, các overload không có cờ được khai báo trả `SortedMap<K,V>`. Nếu cần tiếp tục gọi phương thức điều hướng trên kết quả, ưu tiên overload có cờ thay vì ép kiểu:

```java
SortedMap<Integer, String> ordinary =
        records.subMap(200, 400);
NavigableMap<Integer, String> navigable =
        records.subMap(200, true, 400, false);
```

Đây là đoạn minh họa trong phương thức; cần import `SortedMap`, `NavigableMap` từ `java.util` và một biến `records` đã khởi tạo.

## 6. Kết quả là view có phạm vi, không phải bản sao

Với `TreeMap`, các kết quả lấy khoảng được hỗ trợ bởi map gốc: thay đổi phù hợp ở gốc hiện ra trong view; cập nhật/xóa qua view tác động đến gốc. `put` một khóa ngoài phạm vi view ném `IllegalArgumentException`. Xem [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Với view `[200,400)`:

- `put(250,"X")` hợp lệ và thêm ánh xạ vào gốc.
- `put(200,"B2")` hợp lệ, cập nhật giá trị của khóa đã có.
- `put(400,"Z")` không hợp lệ vì biên trên bị loại, dù khóa 400 đang tồn tại ở gốc.
- `remove(300)` xóa khóa 300 khỏi gốc.
- `clear()` xóa các ánh xạ đang thuộc view, không xóa toàn bộ map gốc.

Nếu cần map riêng để chỉnh sửa độc lập, tạo `new TreeMap<>(view)`. Khi nguồn được khai báo là `NavigableMap`, constructor nguồn đã sắp xếp giữ thứ tự của nguồn. Đây là sao chép cấu trúc ánh xạ, không phải sao chép sâu đối tượng khóa hoặc giá trị.

## 7. Chương trình Java đầy đủ

Lưu tệp `MapRangeDemo.java`:

```java
import java.util.Comparator;
import java.util.NavigableMap;
import java.util.SortedMap;
import java.util.TreeMap;

public class MapRangeDemo {
    public static void main(String[] args) {
        NavigableMap<Integer, String> records = new TreeMap<>();
        records.put(100, "A");
        records.put(200, "B");
        records.put(300, "C");
        records.put(400, "D");
        records.put(500, "E");

        NavigableMap<Integer, String> descending =
                new TreeMap<>(Comparator.reverseOrder());
        descending.putAll(records);

        System.out.println("closed="
                + records.subMap(200, true, 400, true));
        System.out.println("left.closed="
                + records.subMap(200, true, 400, false));
        System.out.println("right.closed="
                + records.subMap(200, false, 400, true));
        System.out.println("open="
                + records.subMap(200, false, 400, false));
        System.out.println("head.exclusive="
                + records.headMap(300, false));
        System.out.println("head.inclusive="
                + records.headMap(300, true));
        System.out.println("tail.exclusive="
                + records.tailMap(300, false));
        System.out.println("tail.inclusive="
                + records.tailMap(300, true));

        SortedMap<Integer, String> ordinary =
                records.subMap(200, 400);
        System.out.println("default.sub=" + ordinary);
        System.out.println("missing.bounds="
                + records.subMap(210, true, 390, true));
        System.out.println("equal.closed="
                + records.subMap(300, true, 300, true));
        System.out.println("equal.exclusive="
                + records.subMap(300, true, 300, false));

        NavigableMap<Integer, String> range =
                records.subMap(200, true, 400, false);
        range.put(250, "X");
        range.put(200, "B2");
        System.out.println("base.after.view.put=" + records);

        try {
            range.put(400, "Z");
        } catch (IllegalArgumentException ex) {
            System.out.println("excluded.put=IllegalArgumentException");
        }

        records.put(350, "Y");
        System.out.println("view.after.base.put=" + range);
        range.remove(300);
        System.out.println("base.after.view.remove=" + records);

        NavigableMap<Integer, String> copy = new TreeMap<>(range);
        range.clear();
        System.out.println("base.after.view.clear=" + records);
        System.out.println("copy.after.clear=" + copy);

        System.out.println("descending.range="
                + descending.subMap(400, true, 100, false));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 MapRangeDemo.java
java MapRangeDemo
```

Stdout:

```text
closed={200=B, 300=C, 400=D}
left.closed={200=B, 300=C}
right.closed={300=C, 400=D}
open={300=C}
head.exclusive={100=A, 200=B}
head.inclusive={100=A, 200=B, 300=C}
tail.exclusive={400=D, 500=E}
tail.inclusive={300=C, 400=D, 500=E}
default.sub={200=B, 300=C}
missing.bounds={300=C}
equal.closed={300=C}
equal.exclusive={}
base.after.view.put={100=A, 200=B2, 250=X, 300=C, 400=D, 500=E}
excluded.put=IllegalArgumentException
view.after.base.put={200=B2, 250=X, 300=C, 350=Y}
base.after.view.remove={100=A, 200=B2, 250=X, 350=Y, 400=D, 500=E}
base.after.view.clear={100=A, 400=D, 500=E}
copy.after.clear={200=B2, 250=X, 350=Y}
descending.range={400=D, 300=C, 200=B}
```

Cách đối chiếu:

1. Bốn dòng đầu chỉ thay cờ, vì thế khác nhau đúng ở hai khóa biên.
2. Cờ của `headMap` quyết định có khóa 300 ở phần đầu không; cờ của `tailMap` quyết định có khóa 300 ở phần đuôi không.
3. Hai khóa 210 và 390 không tồn tại nhưng vẫn tạo được khoảng hợp lệ.
4. Thêm/cập nhật qua `range` thay dữ liệu gốc; khóa 400 bị loại nên không nhận giá trị Z.
5. Bản sao được tạo trước khi xóa view vẫn giữ các ánh xạ riêng sau `clear`.
6. `descending` là map riêng đã được nạp dữ liệu ban đầu bằng `putAll`; nó không bị xóa theo `records`.

## 8. Giới hạn cũng phải đúng theo comparator

Các từ “đầu”, “đuôi”, “từ”, “đến” đều theo thứ tự khóa của map. Với comparator giảm dần, khóa 400 đứng trước 300, 200 và 100.

Vì vậy, `subMap(400, true, 100, false)` trên map giảm dần chọn 400, 300, 200. Nếu mang nguyên lời gọi `subMap(100, true, 400, false)` của map tăng dần sang đây, thứ tự biên không còn hợp lệ.

Comparator cung cấp quan hệ thứ tự chứ không thay đổi kiểu giá trị hay nghĩa của cờ: `true` vẫn nhận khóa bằng biên, `false` vẫn loại khóa bằng biên. Xem [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Đối với khóa tự định nghĩa, cần hiểu tiêu chí so sánh trước khi phát biểu khoảng. Chọn theo một trường trong giá trị V không phải việc mà các phương thức này tự thực hiện.

## 9. Khoảng lồng nhau và lỗi dễ gặp

### View con không được mở rộng ngoài view cha

Nếu `range` có phạm vi `[200,400)`, có thể yêu cầu một khoảng con như `[250,350]`. Nhưng không dùng nó để yêu cầu biên trên 450. Đây không phải phép “giao khoảng nếu được”; biên ngoài phạm vi cha gây `IllegalArgumentException`.

Cờ cũng quan trọng: cha loại 400 thì con không thể yêu cầu nhận 400. Nếu cần khoảng rộng hơn, bắt đầu từ map gốc phù hợp.

### Biên khác vị trí

`subMap(2, true, 5, false)` chọn khóa từ 2 đến trước 5, không chọn bản ghi thứ hai đến thứ tư. Nếu khóa là mã rời rạc, số bản ghi kết quả có thể không liên hệ với chênh lệch hai biên.

### Tạo view không làm dữ liệu bất biến

View liên kết với gốc, không tự tạo ảnh chụp và không tự đồng bộ giữa các luồng. Nếu cần một bản kết quả ổn định về cấu trúc trước các thay đổi tiếp theo, phải sao chép có chủ đích. Nếu đang duyệt, cũng không mặc định được tùy ý sửa cấu trúc qua một đường truy cập khác.

### Không coi cờ là thao tác tạo dữ liệu

`true` không chèn bản ghi ở đầu biên. `false` không xóa bản ghi đó khỏi gốc. Cờ chỉ quy định ánh xạ nào thuộc phạm vi view.

## 10. Tự thực hành

Với map tăng dần `{10=X, 20=Y, 30=Z, 40=W}`:

1. Lấy các khóa lớn hơn 10 và không vượt quá 30.
2. Lấy mọi khóa trước 30, không nhận 30.
3. Lấy mọi khóa từ 20 trở đi, có nhận 20.
4. Tạo view `[20,40)`; `put(40,"NEW")` qua view có hợp lệ không?
5. Nếu chỉ muốn sửa kết quả đã chọn mà không sửa gốc, cần bước nào?

Định hướng: (1) `subMap(10, false, 30, true)` → `{20=Y,30=Z}`; (2) `headMap(30, false)`; (3) `tailMap(20, true)`; (4) không, khóa 40 nằm ở biên bị loại; (5) tạo map riêng như `new TreeMap<>(view)` trước khi sửa.

Trước khi dùng một kết quả lấy khoảng, hãy kiểm tra thứ tự khóa, điều kiện bằng ở từng đầu và việc kết quả có được phép tác động tới map gốc hay không.
