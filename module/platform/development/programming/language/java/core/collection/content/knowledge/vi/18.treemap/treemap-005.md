# lowerEntry, floorEntry, ceilingEntry và higherEntry

## 1. Tìm một ánh xạ lân cận thay vì chỉ tìm đúng khóa

Giả sử chương trình giữ các phiên bản cấu hình theo mốc bắt đầu hiệu lực. Khi hỏi tại mốc 25, map có thể chỉ chứa các mốc 10, 20 và 30.

Get(25) chỉ trả lời liệu có đúng khóa 25 hay không. Nó không trả lời phiên bản gần nhất đã bắt đầu trước hoặc tại 25.

TreeMap thực hiện NavigableMap, cung cấp bốn phép tìm entry lân cận theo thứ tự khóa:

- LowerEntry: phía trước, không lấy khóa bằng mốc hỏi.
- FloorEntry: phía trước, có thể lấy khóa bằng mốc hỏi.
- CeilingEntry: phía sau, có thể lấy khóa bằng mốc hỏi.
- HigherEntry: phía sau, không lấy khóa bằng mốc hỏi.

“Phía trước/phía sau” ở đây phải hiểu theo **thứ tự của map**. Với thứ tự số tự nhiên, chúng tương ứng phía nhỏ hơn/lớn hơn. Khi đảo Comparator, không được tiếp tục áp trực giác số tăng như cũ.

Bài này giải thích dấu biên, trường hợp không có kết quả, ý nghĩa Map.Entry trả về và cách chọn phương thức theo yêu cầu thực tế.

## 2. Bảng định nghĩa cần nắm chắc

Gọi q là khóa truy vấn, k là khóa của một ánh xạ đang có.

| Phương thức | Điều kiện của khóa kết quả | Chọn khóa nào trong các ứng viên? |
| --- | --- | --- |
| lowerEntry(q) | k < q | Khóa lớn nhất thỏa điều kiện |
| floorEntry(q) | k ≤ q | Khóa lớn nhất thỏa điều kiện |
| ceilingEntry(q) | k ≥ q | Khóa nhỏ nhất thỏa điều kiện |
| higherEntry(q) | k > q | Khóa nhỏ nhất thỏa điều kiện |

Tất cả quan hệ trong bảng dùng thứ tự của map, qua compareTo hoặc Comparator.

Nếu không có ứng viên, kết quả là null. Nếu có, kết quả là Map.Entry<K,V>, chứa cả khóa và giá trị của ánh xạ được chọn.

Đối chiếu định nghĩa công khai ở [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html).

### 2.1. Hai cặp khác nhau ở dấu bằng

Lower và floor cùng tìm về phía nhỏ hơn theo thứ tự, nhưng floor cho phép bằng q.

Ceiling và higher cùng tìm về phía lớn hơn theo thứ tự, nhưng ceiling cho phép bằng q.

Khi q không tồn tại trong map, lower và floor thường cho cùng ứng viên; ceiling và higher cũng vậy. Khi q có một vị trí khóa tương đương theo Comparator, dấu bằng tạo khác biệt rõ.

### 2.2. “Lớn nhất” hoặc “nhỏ nhất” giúp chọn sát biên

Không phải chỉ lấy một khóa bất kỳ nhỏ hơn q. Lower/floor lấy khóa sát q nhất từ phía được phép.

Tương tự, ceiling/higher không lấy một khóa lớn hơn tùy ý; chúng chọn ứng viên đầu tiên phù hợp theo chiều thứ tự.

Đó là lý do các phép này hữu ích cho mốc hiệu lực, vị trí tiếp theo hoặc ranh giới của một khoảng.

### 2.3. Khóa truy vấn không cần tồn tại

Q là mốc dùng để so sánh. Nó không cần được put vào map trước.

Không thêm q tạm vào map rồi xóa chỉ để tìm lân cận. Những API này đã được thiết kế để định vị theo một khóa truy vấn độc lập.

## 3. Đọc bốn phép bằng một bộ dữ liệu nhỏ

Map theo thứ tự số tự nhiên có:

```text
10=ten       20=twenty       30=thirty
   ────────────────┬────────────────
              các khóa đã có
```

Bảng dưới chỉ ghi **khóa** của entry kết quả; dấu “không có” nghĩa cả entry là null:

| q | lowerEntry | floorEntry | ceilingEntry | higherEntry |
| --- | --- | --- | --- | --- |
| 5 | Không có | Không có | 10 | 10 |
| 10 | Không có | 10 | 10 | 20 |
| 15 | 10 | 10 | 20 | 20 |
| 20 | 10 | 20 | 20 | 30 |
| 25 | 20 | 20 | 30 | 30 |
| 30 | 20 | 30 | 30 | Không có |
| 35 | 30 | 30 | Không có | Không có |

### 3.1. Truy vấn bằng một khóa đang có

Với q = 20:

- Lower bỏ qua 20 vì yêu cầu nhỏ hơn nghiêm ngặt, nên chọn 10.
- Floor chấp nhận 20, nên chọn 20.
- Ceiling cũng chấp nhận 20, nên chọn 20.
- Higher bỏ qua 20, nên chọn 30.

Floor và ceiling có thể trả cùng một ánh xạ. Không có yêu cầu hai kết quả này phải khác nhau.

### 3.2. Truy vấn nằm giữa hai khóa

Với q = 25, không có khóa bằng 25:

- Lower và floor đều chọn 20.
- Ceiling và higher đều chọn 30.

Đây là trường hợp nhiều người học thấy các cặp “giống nhau”, rồi bỏ qua dấu bằng. Phải kiểm tra thêm trường hợp q đúng bằng khóa để hiểu đầy đủ.

### 3.3. Truy vấn vượt biên và map rỗng

Q nhỏ hơn mọi khóa thì không có ứng viên cho lower/floor. Q lớn hơn mọi khóa thì không có ứng viên cho ceiling/higher.

Map rỗng không có ứng viên cho cả bốn phép, với khóa truy vấn hợp lệ theo hợp đồng.

Không tự thay kết quả thiếu bằng khóa nhỏ nhất/lớn nhất ở phía ngược lại. Nếu ứng dụng cần một quy tắc dự phòng như vậy, phải định nghĩa rõ ngoài phép truy vấn.

## 4. Ví dụ Java 17: bảy vị trí truy vấn và toàn bộ kết quả

Lưu thành **NeighborEntriesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NeighborEntriesDemo {
    static String format(Map.Entry<Integer, String> entry) {
        return entry == null ? "none" : entry.getKey() + "=" + entry.getValue();
    }

    static void show(NavigableMap<Integer, String> map, int query) {
        System.out.println(query + " | " + format(map.lowerEntry(query))
                + " | " + format(map.floorEntry(query))
                + " | " + format(map.ceilingEntry(query))
                + " | " + format(map.higherEntry(query)));
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> map = new TreeMap<>();
        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");

        System.out.println("q | lower | floor | ceiling | higher");
        for (int query : new int[] {5, 10, 15, 20, 25, 30, 35}) {
            show(map, query);
        }
        System.out.println("keys after queries: " + new ArrayList<>(map.keySet()));
        System.out.println("size after queries: " + map.size());

        NavigableMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty floor: " + format(empty.floorEntry(20)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NeighborEntriesDemo.java
java NeighborEntriesDemo
```

Stdout:

```text
q | lower | floor | ceiling | higher
5 | none | none | 10=ten | 10=ten
10 | none | 10=ten | 10=ten | 20=twenty
15 | 10=ten | 10=ten | 20=twenty | 20=twenty
20 | 10=ten | 20=twenty | 20=twenty | 30=thirty
25 | 20=twenty | 20=twenty | 30=thirty | 30=thirty
30 | 20=twenty | 30=thirty | 30=thirty | none
35 | 30=thirty | 30=thirty | none | none
keys after queries: [10, 20, 30]
size after queries: 3
empty floor: none
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ --release chọn mức ngôn ngữ/API và bytecode đích; JVM chạy chương trình vẫn là bản 24.0.2.

### 4.1. Thứ tự thêm không quyết định kết quả lân cận

Map được thêm theo 30,10,20 nhưng có thứ tự khóa 10,20,30. Các phép điều hướng dựa vào thứ tự ấy.

Không chọn “entry vừa được put gần đây nhất” hoặc “entry nằm gần dòng thêm q nhất trong mã nguồn”.

### 4.2. Tìm không làm mất entry

Sau các truy vấn, map vẫn có ba khóa 10,20,30 và size bằng 3.

Bốn phép này định vị ánh xạ, không lấy ra rồi xóa. Không nhầm chúng với các phép poll có tác dụng loại phần tử.

### 4.3. Chỉ xử lý entry sau khi kiểm tra tồn tại

Hàm format kiểm tra entry == null trước khi gọi getKey/getValue.

Đó là hai tầng riêng: **có ánh xạ kết quả hay không**, rồi **khóa/giá trị của ánh xạ ấy là gì**.

Không gọi map.floorEntry(q).getValue() nếu chưa có cơ sở rằng một ứng viên chắc chắn tồn tại.

## 5. Entry trả về chứa gì và có thể sửa được không?

### 5.1. Entry có giá trị null vẫn là một kết quả

TreeMap cho phép giá trị null. Nếu một khóa phù hợp đang gắn với null, floorEntry hoặc phương thức khác vẫn có thể trả một entry khác null.

Ví dụ, map chứa 20=null. FloorEntry(20) có kết quả với key 20 và value null.

Không kiểm tra chỉ getValue() == null để kết luận không tìm thấy khóa. Kết luận “không có ứng viên” dựa vào việc **entry trả về là null**.

### 5.2. Các entry điều hướng của TreeMap là bản chụp ánh xạ

Với bốn phương thức đang xét của TreeMap, entry trả về ghi nhận cặp khóa–giá trị tại thời điểm được tạo và không hỗ trợ setValue.

Đổi giá trị trong map bằng put sau đó không tự cập nhật trường giá trị đã được ghi vào bản chụp entry trước đó.

Trong nguồn [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java), các phép này đi qua exportEntry để tạo một SimpleImmutableEntry từ kết quả tìm.

Không suy tính chất này thành một quy tắc chung cho mọi Map.Entry lấy từ mọi nguồn. Entry có thể xuất hiện từ iterator, view hoặc một lớp triển khai khác với hợp đồng khác. Cần biết API đã tạo ra nó.

### 5.3. Sửa map qua API của map

Nếu muốn thay ánh xạ được chọn, trước hết lấy entry, kiểm tra tồn tại rồi dùng khóa của nó cho thao tác cập nhật phù hợp trên map.

Ví dụ minh họa trong ngữ cảnh có map và q:

```java
Map.Entry<Integer, String> selected = map.floorEntry(q);
if (selected != null) {
    map.put(selected.getKey(), "updated");
}
```

Đây là đoạn trong một chương trình đã có biến và import thích hợp, không phải một tệp chạy độc lập.

Tìm và cập nhật là hai bước. Khi map được dùng chung giữa các luồng, một chuỗi như vậy cần cơ chế phối hợp theo yêu cầu ứng dụng; bản chụp entry không tự biến hai bước thành một giao dịch.

### 5.4. Bản chụp không phải bản sao sâu

Nếu value là một đối tượng có thể sửa, bản chụp entry và map vẫn có thể cùng tham chiếu đối tượng đó.

Không thay được value bằng setValue không có nghĩa những trường bên trong đối tượng value đã trở thành bất biến.

Các ví dụ dùng String để tập trung vào ý nghĩa ánh xạ và tránh lẫn thêm tác động sửa đối tượng dùng chung.

## 6. Thứ tự Comparator quyết định mọi dấu quan hệ

### 6.1. Thứ tự số tự nhiên

Với khóa 10,20,30 theo natural order, lowerEntry(25) chọn 20 và higherEntry(25) chọn 30.

Ở cấu hình này, “nhỏ hơn” trùng với số học quen thuộc.

### 6.2. Thứ tự đảo chiều

Nếu map có thứ tự 30,20,10, thì 30 đứng trước 25 theo thứ tự đảo, còn 20 đứng sau 25.

Với cùng dữ liệu và q = 25:

| Phép | Theo thứ tự tự nhiên | Theo thứ tự đảo |
| --- | --- | --- |
| lowerEntry | 20 | 30 |
| floorEntry | 20 | 30 |
| ceilingEntry | 30 | 20 |
| higherEntry | 30 | 20 |

Các định nghĩa không đổi. Điều đổi là quan hệ so sánh mà các định nghĩa dùng.

Đừng cố nhớ “lower luôn là số bé hơn” rồi áp cho một Comparator bất kỳ.

### 6.3. DescendingMap đảo nghĩa điều hướng

DescendingMap là view đảo thứ tự của map gốc. Những quan hệ điều hướng được hiểu theo thứ tự của view ấy.

Về quan hệ khóa:

- Lower của view đảo tương ứng higher của map gốc.
- Floor của view đảo tương ứng ceiling của map gốc.
- Ceiling của view đảo tương ứng floor của map gốc.
- Higher của view đảo tương ứng lower của map gốc.

View vẫn gắn với cùng dữ liệu nền. Việc nhìn qua view không tự tạo một bản sao riêng của toàn map.

### 6.4. “Bằng” là bằng theo thứ tự

Floor/ceiling xét khả năng so sánh bằng 0 theo thứ tự map, không đòi q và khóa lưu trong cây phải là cùng một đối tượng theo ==.

Comparator cần có quan hệ thứ tự đúng và nên nhất quán với equals để TreeMap tuân đầy đủ hợp đồng Map. Không thay Comparator hoặc sửa thuộc tính dùng để sắp xếp khóa khi chúng đang được dùng như thể cây sẽ tự tổ chức lại.

## 7. Ví dụ Java 17: null, bản chụp và view đảo chiều

Lưu thành **NeighborEntrySemantics.java**:

```java
import java.util.ArrayList;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NeighborEntrySemantics {
    static String format(Map.Entry<Integer, String> entry) {
        return entry == null ? "none" : entry.getKey() + "=" + entry.getValue();
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> map = new TreeMap<>();
        map.put(10, "ten");
        map.put(20, null);
        map.put(30, "thirty");

        Map.Entry<Integer, String> saved = map.floorEntry(20);
        System.out.println("entry exists: " + (saved != null));
        System.out.println("snapshot before put: " + format(saved));
        map.put(20, "updated");
        System.out.println("current value: " + map.get(20));
        System.out.println("snapshot after put: " + format(saved));
        try {
            saved.setValue("changed through entry");
        } catch (UnsupportedOperationException expected) {
            System.out.println("setValue: UnsupportedOperationException");
        }

        NavigableMap<Integer, String> descending = map.descendingMap();
        System.out.println("descending keys: " + new ArrayList<>(descending.keySet()));
        System.out.println("descending lower 25: " + format(descending.lowerEntry(25)));
        System.out.println("descending floor 25: " + format(descending.floorEntry(25)));
        System.out.println("descending ceiling 25: " + format(descending.ceilingEntry(25)));
        System.out.println("descending higher 25: " + format(descending.higherEntry(25)));
        System.out.println("original keys: " + new ArrayList<>(map.keySet()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NeighborEntrySemantics.java
java NeighborEntrySemantics
```

Stdout trên môi trường đã nêu:

```text
entry exists: true
snapshot before put: 20=null
current value: updated
snapshot after put: 20=null
setValue: UnsupportedOperationException
descending keys: [30, 20, 10]
descending lower 25: 30=thirty
descending floor 25: 30=thirty
descending ceiling 25: 20=updated
descending higher 25: 20=updated
original keys: [10, 20, 30]
```

### 7.1. Có entry dù value bằng null

Saved khác null vì khóa 20 là ứng viên hợp lệ cho floorEntry(20). Value của nó là null, nhưng không phải “không có kết quả”.

Sau put(20, "updated"), get trên map cho giá trị mới. Saved vẫn ghi 20=null vì đó là bản chụp cặp ánh xạ đã nhận.

### 7.2. SetValue bị từ chối theo hợp đồng entry này

Thử saved.setValue gây UnsupportedOperationException. Ví dụ bắt ngoại lệ để minh họa khả năng của đối tượng trả về.

Trong cách dùng thông thường, cập nhật qua map như phần trước thay vì dùng ngoại lệ làm đường xử lý chính.

### 7.3. Dữ liệu gốc và chiều nhìn khác nhau

View descending duyệt 30,20,10. Tại q=25, lower/floor của view chọn 30 và ceiling/higher chọn 20.

Map gốc vẫn có dãy khóa 10,20,30. Không có thao tác sắp xếp lại map gốc theo lịch sử thêm; chỉ có một góc nhìn thứ tự khác trên cùng dữ liệu.

## 8. Chọn phương thức từ yêu cầu nghiệp vụ

Hãy viết rõ điều kiện trước khi nhớ tên API.

| Điều kiện cần tìm, theo thứ tự map | Phương thức phù hợp |
| --- | --- |
| Mốc cuối cùng trước q, không lấy q | lowerEntry(q) |
| Mốc cuối cùng không vượt q | floorEntry(q) |
| Mốc đầu tiên không nhỏ hơn q | ceilingEntry(q) |
| Mốc đầu tiên sau q, không lấy q | higherEntry(q) |

### 8.1. Cấu hình bắt đầu có hiệu lực từ một mốc

Giả sử các phiên bản bắt đầu ở 10,20,30. Mỗi phiên bản được coi là có hiệu lực từ mốc bắt đầu cho tới trước phiên bản kế tiếp.

Tại 25, phiên bản có mốc bắt đầu lớn nhất không vượt 25 là 20: dùng floorEntry.

Tại đúng 20, phiên bản 20 phải được chọn. Dùng lowerEntry sẽ lùi về 10 và tạo lỗi ngay tại thời điểm chuyển phiên bản.

Nếu truy vấn trước mốc 10, floorEntry không có kết quả. Ứng dụng cần quyết định đó là thiếu cấu hình, dùng cấu hình mặc định hay một tình huống khác; API không tự đoán chính sách ấy.

### 8.2. Tìm công việc ở mốc hiện tại hoặc sau đó

Nếu một công việc có thể bắt đầu ngay tại q, dùng ceilingEntry(q).

Nếu quy tắc yêu cầu mốc phải sau q nghiêm ngặt, dùng higherEntry(q).

Hai yêu cầu khác nhau chỉ ở dấu bằng, nhưng có thể tạo khác biệt về việc một mục được xử lý ngay hay bị bỏ qua.

### 8.3. Tìm phiên bản ngay trước hoặc ngay sau một khóa

Khi q đang có trong map và cần hàng xóm khác nó, lower/higher là hai phép phù hợp.

Nếu dùng floor/ceiling, kết quả có thể là chính entry q, không phải một hàng xóm khác.

Không sửa q thành q - 1 hoặc q + 1 để giả lập dấu nghiêm ngặt. Cách đó phụ thuộc kiểu dữ liệu, có thể tràn số, và không áp dụng chung cho mọi Comparator hoặc kiểu khóa.

## 9. “Gần nhất theo phía” khác “gần nhất theo khoảng cách”

Bốn phép điều hướng chọn theo quan hệ thứ tự và hướng biên. Chúng không tự tính khoảng cách số học.

Với các khóa 10 và 20:

- Tại q = 12, floor chọn 10, ceiling chọn 20; 10 gần hơn về khoảng cách số.
- Tại q = 18, floor vẫn chọn 10, ceiling vẫn chọn 20; lần này 20 gần hơn.

Muốn chọn khóa gần nhất theo khoảng cách tuyệt đối trên số tự nhiên, có thể lấy hai ứng viên floor và ceiling rồi so khoảng cách, xử lý trường hợp chỉ có một bên và định nghĩa cách phá hòa.

Một Comparator tổng quát chỉ cho thứ tự; nó không tự cung cấp một hàm khoảng cách có ý nghĩa nghiệp vụ.

Nếu tính chênh lệch giữa các khóa int ở biên lớn, phải tính trong kiểu đủ rộng trước phép trừ. Đừng để một phép abs trên hiệu int đã tràn quyết định sai ứng viên.

Các quy tắc khoảng cách này là bước chọn bổ sung của ứng dụng, không phải ý nghĩa ẩn của floorEntry hoặc ceilingEntry.

## 10. Entry, Key, get và poll phục vụ các nhu cầu khác nhau

### 10.1. Chỉ cần khóa thì dùng phương thức Key tương ứng

LowerKey, floorKey, ceilingKey và higherKey áp cùng quan hệ nhưng chỉ trả khóa.

Nếu cần cả khóa lẫn giá trị, dùng phương thức Entry để có trực tiếp cặp ánh xạ phù hợp, thay vì tìm khóa rồi get lại một lần.

Trong một chương trình có sửa đổi đồng thời, hai lời gọi riêng không tự là một ảnh chụp thống nhất. TreeMap cũng không tự an toàn đa luồng.

### 10.2. Get chỉ tìm khóa tương đương, không tìm lân cận

Get(q) không tự chọn floor khi không có q.

Ví dụ map có 10,20,30, get(25) không có ánh xạ tương đương. FloorEntry(25) có thể trả 20=twenty.

Không trộn chính sách “lấy đúng khóa” và “lấy mốc áp dụng gần nhất” bằng việc xử lý null tùy tiện.

### 10.3. Điều hướng không xóa, poll có thể xóa

Bốn phép đang xét chỉ định vị và trả kết quả. Chúng không làm size giảm.

PollFirstEntry/pollLastEntry lấy và xóa entry biên. Đó là API khác với một ý nghĩa thay đổi dữ liệu rõ ràng.

Muốn xóa một lân cận vừa tìm, cần một thao tác xóa riêng và xem tính nguyên tử nếu trạng thái được dùng chung; không gọi lowerEntry rồi mặc định mục đã rời map.

## 11. Null của khóa và tính hợp lệ của truy vấn

### 11.1. Khóa truy vấn phải so sánh được

Với natural order, không dùng null như một mốc hợp lệ. Với Comparator riêng, khả năng nhận null phụ thuộc Comparator và hợp đồng của map.

Các API điều hướng có thể ném ngoại lệ khi khóa không thể so sánh phù hợp. Dùng kiểu generic và quy tắc khóa rõ ràng giúp tránh các lời gọi không có ý nghĩa.

Map rỗng chỉ có nghĩa không có ứng viên; không nên coi trạng thái rỗng là lý do bỏ qua mọi ràng buộc hợp lệ của kiểu khóa/truy vấn.

### 11.2. Một khóa null hợp lệ khác với không có entry

Nếu chủ động dùng Comparator.nullsFirst để cho phép khóa null, một entry kết quả có thể có getKey() bằng null.

Ví dụ map theo nullsFirst có null="null-key" và 10="ten". LowerEntry(10) có thể là entry của khóa null. Entry ấy vẫn khác null.

Trong trường hợp này lowerKey(10) trả null không đủ để phân biệt khóa null hợp lệ với không có ứng viên. Dùng kết quả Entry khi cần phân biệt hai trường hợp.

Đây là lý do phải tách rõ ba khái niệm:

- Không có entry kết quả.
- Có entry với khóa null, nếu được phép.
- Có entry với giá trị null.

Nếu ứng dụng không cần khóa null, có thể chọn chính sách không cho phép để mô hình đơn giản hơn. Không dùng null như một “khóa nhỏ vô hạn” mà chưa có Comparator hỗ trợ.

## 12. Cơ chế tìm trên cây và chi phí sử dụng

TreeMap dựa trên cây tìm kiếm cân bằng. Một phép tìm lân cận không cần quét lần lượt mọi entry.

Hình dung floorEntry(q):

1. Nếu khóa hiện tại lớn hơn q, ứng viên cần tìm phải nằm phía nhỏ hơn.
2. Nếu khóa hiện tại không vượt q, nó là một ứng viên; phần có thể tốt hơn nằm phía lớn hơn nhưng vẫn không vượt q.
3. Nếu gặp bằng q thì đã có ứng viên tốt nhất cho dấu ≤.
4. Khi không thể đi tiếp, trả ứng viên phù hợp hoặc không có kết quả.

Lower giống hướng tìm về phía nhỏ hơn nhưng không chấp nhận bằng q. Ceiling/higher có mô hình đối xứng về phía lớn hơn.

Nguồn OpenJDK có thể thực hiện việc tìm ứng viên qua các đường con và cha cụ thể. Phần giải thích trên là cách lập luận về điều kiện kết quả, không phải yêu cầu mã nguồn phải giữ đúng một biến ứng viên theo một mẫu duy nhất.

### 12.1. Một truy vấn có chi phí theo chiều cao

Với TreeMap và mô hình so sánh khóa có chi phí hằng số, các đường điều hướng này có chi phí O(log n) theo cây cân bằng được phân tích.

Nếu so sánh khóa đắt, phần chi phí ấy cũng phải được tính. Không xem tên phương thức ngắn là một bảo đảm thời gian hằng số.

### 12.2. Dùng để định vị, không thay iterator cho mọi lượt quét

Một chuỗi gọi higherEntry lặp lại có thể hữu ích khi chương trình cần từng truy vấn lân cận độc lập.

Nhưng nếu mục tiêu là duyệt liên tiếp k entry, mỗi lời gọi tìm mới có thể cộng thêm O(log n), tạo tổng O(k log n). Một iterator hoặc view khoảng có đường đi liên tiếp phù hợp hơn cho lượt quét.

Đặc biệt, lấy floorEntry hoặc ceilingEntry với chính khóa kết quả làm mốc tiếp theo mà không thay đổi gì có thể trả lại cùng entry mãi. Khi cần một khóa khác tiếp theo, điều kiện nghiêm ngặt của higher/lower mới phản ánh việc tiến bước.

Việc chọn iterator hay truy vấn lân cận còn phụ thuộc mục tiêu và hợp đồng sửa đổi dữ liệu, không chỉ tránh vòng lặp không tiến triển.

## 13. Cách tự kiểm tra đủ các biên

Một bộ dữ liệu ba khóa cách nhau đủ rộng giúp kiểm tra các nhóm sau:

| Nhóm truy vấn | Điều cần xác nhận |
| --- | --- |
| Nhỏ hơn mọi khóa | Lower/floor thiếu, ceiling/higher chọn khóa đầu theo thứ tự |
| Bằng khóa đầu | Dấu nghiêm ngặt và dấu bao gồm khác nhau |
| Nằm giữa hai khóa | Cặp lower/floor và cặp ceiling/higher có thể cùng kết quả |
| Bằng một khóa giữa | Floor/ceiling có thể trả chính khóa ấy |
| Bằng khóa cuối | Một phía nghiêm ngặt có thể không còn kết quả |
| Lớn hơn mọi khóa | Lower/floor chọn khóa cuối, ceiling/higher thiếu |
| Map rỗng | Không có entry cho truy vấn hợp lệ |
| Map một khóa | Kiểm tra rõ dấu bằng ở cả hai phía |

Thử thêm Comparator đảo chiều để chắc rằng bài kiểm tra dùng quan hệ của map, không chỉ một điều kiện số học cố định.

Với Entry, kiểm tra cả sự tồn tại, khóa và giá trị. Một kết quả có đúng khóa nhưng đọc sai ý nghĩa null vẫn là lỗi ở mã gọi.

Để kiểm tra tính không thay đổi dữ liệu, có thể giữ các ánh xạ dự kiến và xác nhận size/khóa/giá trị sau loạt truy vấn.

Với bản chụp entry, kiểm tra thay map bằng put không làm cặp đã nhận tự đổi và không dùng setValue làm cách cập nhật cho entry điều hướng của TreeMap.

## 14. Lỗi phổ biến và cách sửa

| Hiểu nhầm | Cách sửa |
| --- | --- |
| Lower và floor giống nhau vì một lần thử đều trả 20 | Thử thêm q đúng bằng một khóa |
| Ceiling luôn là phần tử sau q | Ceiling cho phép bằng q; higher mới bỏ dấu bằng |
| Query phải được thêm trước vào map | Dùng trực tiếp khóa truy vấn để định vị |
| Không có kết quả thì API tự lấy phía đối diện | Xử lý null theo chính sách rõ ràng |
| Entry có value null nghĩa không tìm thấy | Kiểm tra entry == null trước, tách giá trị của ánh xạ |
| Gọi setValue trên entry điều hướng sẽ sửa map | Các entry này của TreeMap không hỗ trợ setValue; dùng API map |
| Lower luôn là số nhỏ hơn | Đọc theo Comparator, kể cả view đảo |
| Floor/ceiling tự chọn khoảng cách nhỏ nhất | Chúng chọn theo phía; khoảng cách là bước riêng |
| Có kết quả lân cận nghĩa entry đã bị xóa | Bốn phương thức chỉ tìm, không poll |
| Lấy Key rồi get luôn giống một ảnh chụp Entry | Hai lời gọi có thể tách biệt về trạng thái |
| Q - 1 thay được lower cho mọi loại khóa | Không phụ thuộc số học; dùng dấu quan hệ đúng |
| Lặp ceiling với khóa vừa tìm sẽ luôn tiến | Nó có thể trả lại cùng khóa; chọn higher hoặc iterator khi phù hợp |

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1: Dấu bằng

Map tự nhiên có 4,8,12. Với q=8, khóa của bốn kết quả lower, floor, ceiling, higher là gì?

**Lời giải:** 4,8,8,12.

### Bài 2: Nằm giữa hai khóa

Cũng map ấy, q=10. Bốn khóa kết quả là gì?

**Lời giải:** 8,8,12,12. Không có khóa bằng 10 nên dấu bằng không tạo khác biệt trong từng cặp.

### Bài 3: Ngoài biên

Với q=2, có lowerEntry hoặc floorEntry không? Ceiling/higher chọn gì?

**Lời giải:** lower/floor không có; ceiling/higher chọn khóa 4.

### Bài 4: Chọn cấu hình có hiệu lực

Phiên bản bắt đầu từ các mốc 100,200,300. Tại đúng 200, nếu phiên bản mới có hiệu lực ngay từ mốc ấy, dùng lower hay floor?

**Lời giải:** floorEntry(200), để chọn phiên bản bắt đầu ở 200. Lower sẽ lùi về 100.

### Bài 5: Có null trong giá trị

Map có 8=null. FloorEntry(8) trả entry khác null với value null. Có được xử lý như không có ứng viên không?

**Lời giải:** không. Ánh xạ khóa 8 đang tồn tại; chỉ giá trị của nó là null.

### Bài 6: Thứ tự đảo

Map có các số 4,8,12 nhưng Comparator đảo chiều. LowerEntry(10) chọn số nào?

**Lời giải:** 12, vì 12 nằm trước 10 theo thứ tự đảo. Không áp điều kiện “số nhỏ hơn 10” vào quan hệ của map đảo.

### Bài 7: Gần nhất về khoảng cách

Map có 10 và 20, q=18. Floor trả 10 và ceiling trả 20. Phương thức nào tự quyết định 20 là gần nhất theo khoảng cách tuyệt đối?

**Lời giải:** không phương thức nào trong bốn phép tự làm bước chọn đó. Ứng dụng so hai khoảng cách và xử lý biên/phá hòa nếu cần.

### Bài 8: Bản chụp entry

Saved = floorEntry(8) ghi 8="old". Sau put(8, "new"), saved có bắt buộc tự đổi thành "new" không?

**Lời giải:** không. Entry điều hướng của TreeMap là bản chụp ánh xạ, không phải một handle cập nhật sống cho map.

### Bài 9: Tiến tới khóa tiếp theo

Tìm được khóa 8 và muốn một khóa lớn hơn khác 8. CeilingEntry(8) có bảo đảm tiến tới khóa khác không?

**Lời giải:** không. Nó có thể trả lại 8; higherEntry(8) mới yêu cầu lớn hơn nghiêm ngặt theo thứ tự map.

## 16. Tài liệu đối chiếu

- [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): bốn quan hệ lân cận, phương thức Key và ý nghĩa view đảo.
- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): hợp đồng cụ thể của lớp, quy tắc khóa và entry trả về.
- [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): các đường tìm ứng viên và exportEntry.
- [Map.Entry Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html): cặp khóa–giá trị và khả năng tùy chọn của thao tác setValue.

Chọn đúng một trong bốn phép bắt đầu từ điều kiện cần tìm: phía nào, có lấy trường hợp bằng hay không, và theo thứ tự nào. Sau đó xử lý sự tồn tại của entry riêng với nội dung khóa–giá trị mà entry mang theo.
