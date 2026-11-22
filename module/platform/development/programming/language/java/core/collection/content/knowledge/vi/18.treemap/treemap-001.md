# TreeMap, SortedMap, NavigableMap và thứ tự khóa

Một map thông thường trả lời câu hỏi “khóa này ánh xạ tới giá trị nào?”. Nhiều bài toán còn cần biết khóa đầu tiên, khóa gần một mốc nhất hoặc tất cả khóa trong một khoảng. Ví dụ, bảng cấu hình có hiệu lực từ các mốc thời gian cần tìm bản cấu hình mới nhất không muộn hơn thời điểm đang xét.

`TreeMap` giải quyết nhóm bài toán này bằng cách giữ các khóa theo một quy tắc so sánh. `SortedMap` và `NavigableMap` là hai giao diện mô tả những khả năng liên quan đến thứ tự; chúng không phải hai chế độ khác nhau mà phải bật trên TreeMap.

Bài này dùng Java 17. Mục tiêu là hiểu quan hệ giữa ba tên gọi, đọc đúng ý nghĩa của thứ tự khóa, chọn truy vấn lân cận và khoảng khóa, đồng thời phân biệt góc nhìn dùng chung dữ liệu với bản sao độc lập.

## 1. Từ Map đến NavigableMap

Quan hệ giao diện trong Java 17 có thể đọc theo chuỗi:

~~~text
Map<K, V>
    ↑
SortedMap<K, V>
    ↑
NavigableMap<K, V>
    ↑ được triển khai bởi
TreeMap<K, V>
~~~

Mũi tên biểu diễn việc kiểu bên dưới có các khả năng của kiểu bên trên. `TreeMap` là một lớp cụ thể, còn ba tên đầu là giao diện.

| Kiểu | Điều nó bổ sung hoặc biểu diễn |
|---|---|
| Map | Các ánh xạ khóa–giá trị |
| SortedMap | Thứ tự toàn phần trên khóa, khóa đầu/cuối và các khoảng |
| NavigableMap | Tìm khóa lân cận, điều khiển biên khoảng, chiều đảo và lấy/xóa hai đầu |
| TreeMap | Một cách triển khai NavigableMap dựa trên cây đỏ–đen |

`TreeMap` có bảo đảm chi phí `O(log n)` cho `containsKey`, `get`, `put` và `remove`. Bài này không đi vào thuật toán cân bằng cây; điều cần nối với API là dữ liệu đã có quan hệ thứ tự để phục vụ các truy vấn theo mốc và theo khoảng. [Java 17: TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 1.1. SortedMap chưa phải NavigableMap về mặt kiểu biến

Một đối tượng TreeMap có thể được tham chiếu qua nhiều kiểu:

~~~java
TreeMap<Integer, String> tree = new TreeMap<>();
Map<Integer, String> general = tree;
SortedMap<Integer, String> sorted = tree;
NavigableMap<Integer, String> navigable = tree;
~~~

Đây là các khai báo minh họa, chưa phải chương trình độc lập.

Bốn biến cùng trỏ đến một đối tượng. Duyệt qua `general.entrySet()` vẫn theo thứ tự do TreeMap giữ. Đổi kiểu tham chiếu không biến đối tượng thành HashMap và không xóa thứ tự của nó.

Nhưng các phương thức gọi được ở lúc biên dịch phụ thuộc kiểu khai báo:

- `general` có các phương thức của Map.
- `sorted` có thêm `firstKey`, `lastKey` và các khoảng của SortedMap.
- `navigable` có thêm `floorEntry`, `ceilingKey`, `descendingMap` và các phương thức điều hướng khác.

Nếu một hàm cần khả năng điều hướng, nên biểu diễn yêu cầu bằng tham số `NavigableMap` phù hợp. Không nên nhận Map rồi ép kiểu mù với giả định mọi nơi đều truyền TreeMap.

### 1.2. Vì sao cần hơn một giao diện?

Một hàm chỉ đếm số ánh xạ không cần yêu cầu lớp cây cụ thể. Một hàm cần khóa lân cận lại cần hợp đồng mạnh hơn Map. Các giao diện giúp nói rõ điều hàm cần từ dữ liệu.

Ví dụ, chức năng tìm phiên bản cấu hình tại một thời điểm có thể cần `floorEntry`. Khai báo nhận NavigableMap làm khả năng đó hiện rõ trong chữ ký, thay vì giấu một giả định TreeMap trong phần thân.

## 2. TreeMap sắp xếp khóa theo quy tắc nào?

### 2.1. Thứ tự tự nhiên

Nếu không truyền comparator, TreeMap dùng thứ tự tự nhiên (`natural ordering`) của khóa qua `Comparable.compareTo`. Các khóa phải so sánh được với nhau.

Với `Integer`, thứ tự thông thường là thứ tự số. Chèn `40, 10, 30, 20` vẫn cho thứ tự duyệt `10, 20, 30, 40`.

Với `String`, quy tắc do `String.compareTo` định nghĩa. Không nên mặc nhiên coi đó là quy tắc sắp tên tiếng Việt theo nhu cầu ngôn ngữ của ứng dụng. Quy tắc so sánh phải được chọn theo dữ liệu và nghiệp vụ. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)

### 2.2. Comparator riêng

Có thể đưa một đối tượng so sánh khi tạo map:

~~~java
NavigableMap<Integer, String> decreasing =
        new TreeMap<>(Comparator.reverseOrder());
~~~

Khi ấy thứ tự của map là thứ tự đảo. “Khóa nhỏ nhất”, “trước” và “sau” trong các phương thức điều hướng đều phải hiểu theo comparator này, không tự động theo cách đọc số tăng dần.

`comparator()` trả về comparator đang dùng, hoặc null nếu dùng thứ tự tự nhiên. Kết quả null ở đây không có nghĩa map không có thứ tự.

`Comparator` phải tạo quan hệ so sánh nhất quán, chẳng hạn tính bắc cầu. Khi so số nguyên, không nên viết `a - b` để lấy dấu vì tràn số có thể làm sai quan hệ. Dùng `Integer.compare(a, b)` hoặc các hàm tạo comparator thích hợp. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 2.3. Sắp xếp theo khóa, không theo giá trị

Giả sử map có các cặp:

~~~text
40 -> forty
10 -> ten
30 -> thirty
20 -> twenty
~~~

Duyệt entrySet theo khóa tăng dần cho `10=ten, 20=twenty, 30=thirty, 40=forty`. Duyệt values cho `ten, twenty, thirty, forty` vì các giá trị đi theo ánh xạ của khóa tương ứng. Điều đó không nói các chuỗi giá trị đã được sắp chữ cái.

Thứ tự cũng không phải thứ tự chèn. Nếu cần lần đầu xuất hiện, đó là yêu cầu khác. TreeMap giữ quy tắc so sánh, không lưu lịch sử chèn để dùng làm thứ tự duyệt.

`SortedMap` xác định thứ tự khóa được phản ánh khi duyệt các góc nhìn `keySet`, `entrySet` và `values`. [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html)

## 3. So sánh bằng 0 ảnh hưởng cả định danh khóa

Comparator không chỉ trang trí cách in dữ liệu. TreeMap dùng phép so sánh để xác định các khóa trong cấu trúc của nó.

### 3.1. Hai chuỗi khác nhau có thể chiếm một vị trí

Với comparator không phân biệt hoa thường, `"java"` và `"JAVA"` được so sánh bằng 0. Thêm lần lượt hai khóa ấy có thể tạo một ánh xạ với giá trị sau thay giá trị trước, thay vì hai ánh xạ.

Trong chương trình phía dưới:

~~~java
TreeMap<String, Integer> folded =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
folded.put("java", 1);
folded.put("JAVA", 2);
~~~

Kết quả có một ánh xạ và tra cứu `"JaVa"` nhận 2. Ví dụ chỉ khẳng định số ánh xạ và giá trị tra được; không dựa vào việc đại diện khóa nào được giữ để giải thích định danh nghiệp vụ.

Điều này thường bị hiểu nhầm thành “mất dữ liệu do cây”. Thực ra, quy tắc so sánh đã nói hai khóa thuộc cùng vị trí so sánh.

### 3.2. Nhất quán với equals

Để tuân thủ hợp đồng Map dựa trên equals, thứ tự của sorted map cần nhất quán với equals: so sánh bằng 0 tương ứng với bằng nhau theo equals.

Comparator không phân biệt hoa thường với String không có tính nhất quán đó, vì `"java".equals("JAVA")` là false. Ví dụ cố ý bộc lộ sự khác biệt, không phải khuyến nghị dùng comparator ấy cho mọi danh mục định danh. [Java 17: quan hệ giữa so sánh và equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

Nếu nghiệp vụ thực sự không phân biệt hoa thường, có thể thiết kế biểu diễn khóa được chuẩn hóa phù hợp. Nếu cần giữ hai bản ghi có cùng điểm hoặc cùng tên hiển thị, phải có tiêu chí phân biệt thêm thay vì vô tình gộp chúng.

Ví dụ minh họa một phần với khóa bản ghi:

~~~java
record RankKey(int score, long id) {}

Comparator<RankKey> byScoreThenId =
        Comparator.comparingInt(RankKey::score)
                  .thenComparingLong(RankKey::id);

NavigableMap<RankKey, String> ranking =
        new TreeMap<>(byScoreThenId);
~~~

Hai khóa khác id nhưng cùng score vẫn so sánh khác 0 nhờ tiêu chí phụ. Với bản ghi này, equals cũng xét hai thành phần đó.

### 3.3. Giữ ổn định các thành phần được so sánh

Nếu khóa đang nằm trong cây mà trường dùng để so sánh bị thay đổi, quan hệ thứ tự của đối tượng đó với các khóa khác có thể không còn phù hợp vị trí đã được tổ chức. Đừng giả định map sẽ tự phát hiện và đặt lại khóa.

Khóa bất biến giúp việc tổ chức dữ liệu rõ ràng hơn. Khi cần thay thông tin ảnh hưởng thứ tự, hãy thiết kế thao tác loại khóa cũ và thêm khóa mới theo trạng thái được kiểm soát, thay vì sửa trực tiếp đối tượng đang đóng vai trò khóa.

## 4. SortedMap: hai đầu và ba loại khoảng

### 4.1. Khóa đầu và cuối

`firstKey()` trả về khóa đầu theo thứ tự map, `lastKey()` trả về khóa cuối. Với map tự nhiên có `10, 20, 30, 40`, kết quả là 10 và 40.

Trên map giảm dần của cùng các số, đầu là 40 và cuối là 10. “Đầu” là đầu thứ tự của map, không nhất thiết là số nhỏ nhất theo cách đọc số tăng dần.

Nếu map trống, hai phương thức này ném `NoSuchElementException`. Khi muốn kết quả có thể vắng mà không dùng ngoại lệ, NavigableMap có các phương thức trả entry ở hai đầu.

### 4.2. Khoảng mặc định của SortedMap

Theo thứ tự hiện có, các phương thức là:

| Phương thức | Điều kiện khóa k |
|---|---|
| subMap(a, b) | a ≤ k < b |
| headMap(b) | k < b |
| tailMap(a) | k ≥ a |

Dấu ≤ và < trong bảng là quan hệ theo comparator hoặc thứ tự tự nhiên đang dùng.

Với khóa `10, 20, 30, 40` theo thứ tự số tăng:

~~~text
subMap(20, 40) -> 20, 30
headMap(30)    -> 10, 20
tailMap(30)    -> 30, 40
~~~

Khoảng subMap mặc định bao gồm đầu dưới và loại đầu trên. Cách viết này thường được gọi là khoảng nửa mở `[a, b)`.

Biên không bắt buộc là khóa đang tồn tại. Với cùng dữ liệu, `subMap(15, 35)` chọn 20 và 30. Biên dùng để so sánh phạm vi, không phải lời yêu cầu phải tìm thấy hai ánh xạ biên.

### 4.3. Chọn khoảng theo nghiệp vụ

Khoảng nửa mở giúp ghép các vùng liền nhau mà không lặp biên: `[a, b)` rồi `[b, c)`. Ví dụ, báo cáo một ngày có thể dùng thời điểm bắt đầu ngày hiện tại và đầu ngày tiếp theo thay cho việc tự tính “thời điểm cuối ngày” với một độ chính xác giả định.

Đây là lý do thiết kế phạm vi trước khi gọi hàm. Khi nghiệp vụ yêu cầu bao gồm cả hai mốc, cần dạng có tham số boolean của NavigableMap, không được tự bỏ sót đầu trên vì nhớ nhầm mặc định.

## 5. NavigableMap: tìm khóa lân cận

### 5.1. Bốn quan hệ cần phân biệt

Với mốc x và thứ tự map:

| Nhóm | Khóa được chọn |
|---|---|
| lowerKey(x), lowerEntry(x) | Khóa lớn nhất nhưng nhỏ hơn x |
| floorKey(x), floorEntry(x) | Khóa lớn nhất nhưng không lớn hơn x |
| ceilingKey(x), ceilingEntry(x) | Khóa nhỏ nhất nhưng không nhỏ hơn x |
| higherKey(x), higherEntry(x) | Khóa nhỏ nhất nhưng lớn hơn x |

Có thể nhớ bằng việc tách hai câu hỏi: tìm phía trước hay phía sau, và có chấp nhận bằng đúng mốc hay không.

Với khóa `10, 20, 30, 40` theo thứ tự số:

| Mốc | lower | floor | ceiling | higher |
|---|---:|---:|---:|---:|
| 20 | 10 | 20 | 20 | 30 |
| 25 | 20 | 20 | 30 | 30 |
| 5 | Không có | Không có | 10 | 10 |
| 45 | 40 | 40 | Không có | Không có |

Các phương thức trả null khi không có kết quả phù hợp. Bản `Key` trả khóa; bản `Entry` trả cả khóa và giá trị. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

### 5.2. Ví dụ cấu hình có hiệu lực từ một mốc

Giả sử khóa là thời điểm bắt đầu hiệu lực:

~~~text
10 -> cấu hình A
20 -> cấu hình B
30 -> cấu hình C
~~~

Muốn biết cấu hình tại thời điểm 25, dùng floorEntry(25), nhận ánh xạ ở 20. Dùng lowerEntry(25) cũng cho 20 trong ví dụ này, nhưng tại đúng thời điểm 20, lowerEntry sẽ trả bản ở 10, khác yêu cầu.

Đó là lý do phải kiểm thử cả trường hợp bằng biên, không chỉ chọn một mốc nằm giữa hai khóa. Khi dữ liệu có thể vắng ở đầu trục thời gian, cũng cần định nghĩa trường hợp floorEntry trả null: không có cấu hình hợp lệ hay phải dùng cấu hình mặc định?

### 5.3. Lân cận theo thứ tự không phải gần nhất theo khoảng cách

Lower, floor, ceiling và higher nói về quan hệ thứ tự. Chúng không tự trả “giá trị có khoảng cách số học nhỏ nhất”.

Ví dụ, với các khóa 10 và 100, tìm khóa gần số 90 nhất cần cân nhắc khoảng cách sau khi lấy ứng viên thích hợp. Chọn floorKey(90) một mình chỉ cho khóa phía dưới là 10, không phải lời giải “gần nhất” theo khoảng cách.

Với thời điểm, địa chỉ hoặc phiên bản, quan hệ nghiệp vụ có thể không phải khoảng cách số. Hãy gọi đúng tên điều ứng dụng cần.

### 5.4. Khi giá trị hoặc khóa có thể null

Một entry kết quả khác null có thể chứa giá trị null. Vì vậy, đừng kiểm tra `entry.getValue() == null` để kết luận không tìm thấy.

Nếu comparator cho phép khóa null, phương thức trả khóa có thể gặp sự nhập nhằng giữa “khóa kết quả là null” và “không có kết quả”. Dạng trả entry giúp phân biệt qua chính đối tượng entry.

Phải xét quy tắc null của cách triển khai; không suy từ một giao diện sang việc mọi map đều cho phép null.

## 6. Hai đầu: xem và lấy ra là hai thao tác khác nhau

NavigableMap có các phương thức:

| Phương thức | Tác động |
|---|---|
| firstEntry() | Xem ánh xạ đầu, không xóa |
| lastEntry() | Xem ánh xạ cuối, không xóa |
| pollFirstEntry() | Lấy và xóa ánh xạ đầu |
| pollLastEntry() | Lấy và xóa ánh xạ cuối |

Map trống cho kết quả null ở các phương thức trên. Tên `poll` là lời nhắc rằng thao tác làm thay đổi map khi có kết quả.

Ví dụ, dùng pollFirstEntry để “xem khóa nhỏ nhất” trong phần ghi log sẽ vô tình lấy nó khỏi dữ liệu. Nếu chỉ muốn quan sát, chọn firstEntry hoặc firstKey theo cách xử lý map trống mong muốn.

### 6.1. Entry từ truy vấn điều hướng của TreeMap

Các entry do những phương thức điều hướng của TreeMap như firstEntry, floorEntry hoặc pollFirstEntry trả về là ảnh chụp ánh xạ tại thời điểm tạo. Chúng không hỗ trợ setValue để ghi ngược lại map. Muốn sửa ánh xạ đang tồn tại, thực hiện thao tác map thích hợp.

Không mở rộng câu này thành “mọi Map.Entry trong Java đều bất biến”. Entry lấy khi duyệt entrySet có hợp đồng riêng; một cặp trả về từ truy vấn điều hướng và một entry của góc nhìn duyệt không nên bị coi là cùng một loại quan hệ với map.

Ảnh chụp cặp cũng không có nghĩa sao chép sâu đối tượng giá trị. Ví dụ dùng String để việc so sánh giá trị cũ và mới rõ ràng.

## 7. Biên bao gồm và loại trừ trong NavigableMap

Các dạng bổ sung cho phép chọn từng biên:

~~~java
NavigableMap<Integer, String> middle =
        map.subMap(20, true, 40, false);

NavigableMap<Integer, String> upTo30 =
        map.headMap(30, true);

NavigableMap<Integer, String> after30 =
        map.tailMap(30, false);
~~~

Đây là đoạn minh họa với biến map đã có, không phải chương trình độc lập.

Các kết quả trên dữ liệu 10, 20, 30, 40:

~~~text
subMap(20, true, 40, false) -> 20, 30
headMap(30, true)          -> 10, 20, 30
tailMap(30, false)         -> 40
~~~

`true` nghĩa là bao gồm biên đó nếu có khóa so sánh bằng biên; `false` nghĩa là loại trừ.

Nếu hai biên bằng nhau, các cờ vẫn quan trọng. Khoảng bao gồm cả hai đầu có thể chứa khóa bằng mốc nếu khóa đó tồn tại; khoảng loại ít nhất một đầu không chứa khóa ấy. Trường hợp mặc định `subMap(a, a)` là khoảng rỗng.

Nếu biên bắt đầu đứng sau biên kết thúc theo thứ tự của map, yêu cầu khoảng không hợp lệ. Đừng hiểu “bắt đầu nhỏ hơn kết thúc” luôn là phép so số tăng dần; phần thứ tự đảo sẽ minh họa điều này.

## 8. Các khoảng là góc nhìn dùng chung dữ liệu

### 8.1. Không tự tạo bản sao

`subMap`, `headMap` và `tailMap` trên TreeMap trả góc nhìn (`view`) vào dữ liệu. Thay đổi hợp lệ qua view được phản ánh vào map gốc; thay đổi map gốc trong phạm vi cũng được nhìn thấy qua view.

Ví dụ:

~~~text
map gốc: 10, 20, 30, 40
view [20,40): 20, 30

thêm 35 qua view:
map gốc: 10, 20, 30, 35, 40
view:    20, 30, 35

xóa 20 qua view:
map gốc: 10, 30, 35, 40
view:    30, 35
~~~

Có thể đọc view như “cửa sổ giới hạn khóa” vào cùng dữ liệu, không phải bảng dữ liệu mới đã được tách.

### 8.2. Ghi ngoài phạm vi bị từ chối

Với view `[20,40)`, put khóa 40 hoặc 45 qua view ném `IllegalArgumentException`. Ngay cả khi 40 đã tồn tại trong map gốc, nó vẫn ngoài phạm vi view vì đầu trên bị loại.

Giới hạn view không cấm map gốc có các khóa ngoài khoảng; nó giới hạn những khóa view đại diện và có thể chèn qua view. Một phép get khóa ngoài phạm vi không tự biến thành phép ghi và không nên được diễn giải như yêu cầu mở rộng view.

Các view lồng nhau tiếp tục bị ràng buộc bởi phạm vi đang có. Không dùng một view để tự mở rộng ra ngoài cửa sổ của view cha. [Java 17: hợp đồng các vùng khóa của TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 8.3. Clear view khác clear toàn bộ map

`view.clear()` loại các ánh xạ nằm trong vùng của view khỏi dữ liệu gốc. Nó không chỉ làm rỗng một bản hiển thị riêng, và cũng không nhất thiết xóa những khóa ngoài phạm vi.

Điều này có ích cho việc xóa một khoảng, nhưng cần xem đó là thao tác sửa dữ liệu gốc. Đặt tên biến phản ánh phạm vi giúp giảm nhầm lẫn, chẳng hạn `expiredByTime` thay vì một tên chung chung như `temp`.

### 8.4. Khi cần bản độc lập

Có thể tạo TreeMap mới từ SortedMap hoặc NavigableMap đang có:

~~~java
NavigableMap<Integer, String> window =
        source.subMap(20, true, 40, false);

TreeMap<Integer, String> copy = new TreeMap<>(window);
~~~

Bản copy có cấu trúc độc lập; sửa view về sau không tự thêm hoặc xóa ánh xạ trong copy. Các tham chiếu khóa và giá trị vẫn được dùng lại, nên không tự có sao chép sâu.

Nếu nguồn đang bị sửa cạnh tranh, bước sao chép vẫn cần chính sách đồng thời phù hợp. Tạo đối tượng mới không tự hợp thức hóa việc đọc nguồn trong trạng thái không được bảo vệ.

## 9. Thứ tự đảo thay đổi cả nghĩa của điều hướng

### 9.1. DescendingMap là view

`descendingMap()` trả góc nhìn với thứ tự đảo so với map hiện tại. Nó dùng cùng dữ liệu, nên xóa một khóa qua map đảo cũng xóa ánh xạ trong map gốc.

Với gốc có thứ tự 10, 20, 30, 40, map đảo duyệt 40, 30, 20, 10.

Các phương thức vẫn làm việc theo thứ tự của chính view:

~~~text
trên thứ tự tăng:
lowerKey(20)  -> 10
higherKey(20) -> 30

trên thứ tự đảo:
lowerKey(20)  -> 30
higherKey(20) -> 10
~~~

Khóa 30 đứng trước 20 trong thứ tự đảo, còn 10 đứng sau. Đây không phải lỗi của lower hoặc higher; quan hệ đang dùng đã đổi.

### 9.2. Biên khoảng cũng theo thứ tự đảo

Trên view đảo, `subMap(40, true, 20, false)` chọn 40 và 30. Cặp biên trông “từ số lớn xuống số nhỏ” nhưng đúng chiều của comparator.

Ngược lại, lấy thói quen truyền 20 rồi 40 từ map tăng áp vào view đảo có thể tạo khoảng không hợp lệ. Hãy đọc dãy thứ tự thực tế trước khi diễn giải fromKey và toKey.

`descendingKeySet` và `navigableKeySet` cung cấp góc nhìn khóa tương ứng. Chúng không phải nơi có thể tự thêm một khóa mới mà không có giá trị map; việc loại khóa được hỗ trợ sẽ tác động đến ánh xạ gốc theo hợp đồng góc nhìn.

## 10. Chọn constructor cũng là chọn thứ tự

Hai constructor sao chép có điểm khác biệt đáng học:

| Đối số được chọn theo kiểu ở lúc biên dịch | TreeMap mới dùng |
|---|---|
| Map | Thứ tự tự nhiên của khóa |
| SortedMap | Thứ tự của SortedMap nguồn |

Ví dụ, một TreeMap nguồn đang giảm dần. Nếu truyền nguồn qua biến kiểu SortedMap, constructor giữ quy tắc giảm dần. Nếu truyền qua biến kiểu Map, constructor nhận Map dùng thứ tự tự nhiên.

Không có việc “runtime luôn nhìn ra đối tượng nguồn là TreeMap rồi chọn lại dạng nạp chồng (overload)”. Việc chọn dạng nạp chồng dựa vào kiểu biểu thức ở lúc biên dịch.

Khi muốn kiểm soát rõ ràng hơn, có thể tạo map với comparator mong muốn rồi putAll các ánh xạ. Thứ tự sẽ do comparator của đích quyết định; putAll không tự thay nó bằng comparator nguồn.

Chi tiết này giải thích vì sao hai bản sao cùng ánh xạ có thể duyệt khác thứ tự. Nó cũng nhắc rằng kiểu giao diện không chỉ ảnh hưởng danh sách phương thức gọi được mà còn có thể ảnh hưởng việc chọn constructor. [Java 17: các constructor của TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 11. Null, kiểu khóa và những giới hạn cần biết

TreeMap dùng thứ tự tự nhiên không chấp nhận khóa null. Comparator riêng có thể cho phép null nếu chính comparator định nghĩa cách so sánh nó, chẳng hạn `Comparator.nullsFirst(...)`.

Chương trình dùng comparator cho phép null và in thứ tự `[null, A, B]`. Điều đó không có nghĩa mọi TreeMap đều chấp nhận null.

Giá trị null là câu hỏi khác với khóa null. Một ánh xạ có giá trị null vẫn có thể tồn tại; cần dùng containsKey hoặc entry phù hợp khi phải phân biệt với vắng ánh xạ.

Các khóa phải so sánh được với nhau bằng quy tắc của map. Generic giúp kiểm tra kiểu ở lúc biên dịch nhưng không tự bảo đảm mọi quy tắc so sánh đều đúng. Không dùng raw type để trộn tùy ý những loại khóa không thể so sánh.

TreeMap cũng không tự đồng bộ hóa. Iterator có cơ chế phát hiện sửa đổi theo nỗ lực tốt nhất; cơ chế đó không thay thế chính sách truy cập đồng thời. Nội dung về thứ tự ở đây giả sử các thao tác được tổ chức trong trạng thái hợp lệ của map.

## 12. Chương trình Java đầy đủ

Lưu mã sau vào `SortedNavigationDemo.java`. Mỗi nhóm tình huống dùng dữ liệu phù hợp để tránh một phép poll hoặc xóa ở phần trước làm sai cách hiểu phần sau.

Chương trình kiểm chứng thứ tự khóa, khác biệt giữa lower và floor, view so với copy, entry điều hướng, thứ tự đảo, comparator so sánh bằng 0 và hai overload constructor.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NoSuchElementException;
import java.util.SortedMap;
import java.util.TreeMap;

public class SortedNavigationDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(40, "forty");
        map.put(10, "ten");
        map.put(30, "thirty");
        map.put(20, "twenty");
        return map;
    }

    private static <K, V> List<K> keys(Map<K, V> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> tree = sample();
        Map<Integer, String> asMap = tree;
        SortedMap<Integer, String> sorted = tree;
        NavigableMap<Integer, String> navigable = tree;

        require(keys(asMap).equals(List.of(10, 20, 30, 40)));
        System.out.println("order/keys=" + keys(asMap));
        System.out.println("order/values=" + new ArrayList<>(tree.values()));
        System.out.println("sorted/first=" + sorted.firstKey()
                + ", last=" + sorted.lastKey());
        System.out.println("sorted/[20,40)=" + sorted.subMap(20, 40));
        System.out.println("near/25: lower=" + navigable.lowerKey(25)
                + ", floor=" + navigable.floorKey(25)
                + ", ceiling=" + navigable.ceilingKey(25)
                + ", higher=" + navigable.higherKey(25));
        System.out.println("near/20: lower=" + navigable.lowerKey(20)
                + ", floor=" + navigable.floorKey(20)
                + ", ceiling=" + navigable.ceilingKey(20)
                + ", higher=" + navigable.higherKey(20));

        NavigableMap<Integer, String> range =
                tree.subMap(20, true, 40, false);
        TreeMap<Integer, String> independent = new TreeMap<>(range);
        range.put(35, "thirty-five");
        range.remove(20);
        require(keys(tree).equals(List.of(10, 30, 35, 40)));
        require(keys(independent).equals(List.of(20, 30)));
        boolean outsideRejected = false;
        try {
            range.put(40, "not-allowed");
        } catch (IllegalArgumentException exception) {
            outsideRejected = true;
        }
        require(outsideRejected);
        System.out.println("view/range=" + range);
        System.out.println("view/parent=" + tree);
        System.out.println("view/copy=" + independent);
        System.out.println("view/outsideRejected=" + outsideRejected);

        TreeMap<Integer, String> snapshotMap = sample();
        Map.Entry<Integer, String> first = snapshotMap.firstEntry();
        snapshotMap.put(10, "TEN");
        require(first.getValue().equals("ten"));
        boolean snapshotImmutable = false;
        try {
            first.setValue("changed");
        } catch (UnsupportedOperationException exception) {
            snapshotImmutable = true;
        }
        require(snapshotImmutable);
        System.out.println("entry/snapshot=" + first
                + ", current=" + snapshotMap.get(10)
                + ", setValueRejected=" + snapshotImmutable);

        TreeMap<Integer, String> drained = sample();
        Map.Entry<Integer, String> smallest = drained.pollFirstEntry();
        Map.Entry<Integer, String> largest = drained.pollLastEntry();
        require(keys(drained).equals(List.of(20, 30)));
        System.out.println("poll/first=" + smallest + ", last=" + largest);
        System.out.println("poll/remaining=" + drained);

        TreeMap<Integer, String> empty = new TreeMap<>();
        boolean firstKeyThrows = false;
        try {
            empty.firstKey();
        } catch (NoSuchElementException exception) {
            firstKeyThrows = true;
        }
        require(firstKeyThrows && empty.firstEntry() == null);
        System.out.println("empty/firstEntry=" + empty.firstEntry()
                + ", firstKeyThrows=" + firstKeyThrows);

        TreeMap<Integer, String> ascending = sample();
        NavigableMap<Integer, String> descending = ascending.descendingMap();
        require(keys(descending).equals(List.of(40, 30, 20, 10)));
        System.out.println("descending/keys=" + keys(descending));
        System.out.println("descending/at20: lower=" + descending.lowerKey(20)
                + ", higher=" + descending.higherKey(20));
        System.out.println("descending/[40,20)="
                + descending.subMap(40, true, 20, false));
        descending.remove(20);
        require(!ascending.containsKey(20));
        System.out.println("descending/parentAfterRemove=" + keys(ascending));

        TreeMap<String, Integer> folded =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        folded.put("java", 1);
        folded.put("JAVA", 2);
        require(folded.size() == 1 && folded.get("JaVa") == 2);
        System.out.println("compareZero/size=" + folded.size()
                + ", value=" + folded.get("JaVa"));

        TreeMap<Integer, String> reverseSource =
                new TreeMap<>(Comparator.reverseOrder());
        reverseSource.putAll(sample());
        SortedMap<Integer, String> sortedSource = reverseSource;
        Map<Integer, String> mapSource = reverseSource;
        TreeMap<Integer, String> copySorted = new TreeMap<>(sortedSource);
        TreeMap<Integer, String> copyMap = new TreeMap<>(mapSource);
        require(keys(copySorted).equals(List.of(40, 30, 20, 10)));
        require(keys(copyMap).equals(List.of(10, 20, 30, 40)));
        System.out.println("constructor/SortedMap=" + keys(copySorted));
        System.out.println("constructor/Map=" + keys(copyMap));

        NavigableMap<String, Integer> nullable =
                new TreeMap<>(Comparator.nullsFirst(
                        Comparator.<String>naturalOrder()));
        nullable.put("B", 2);
        nullable.put(null, 0);
        nullable.put("A", 1);
        require(keys(nullable).toString().equals("[null, A, B]"));
        System.out.println("nullKeys/order=" + keys(nullable));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 SortedNavigationDemo.java
java SortedNavigationDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
order/keys=[10, 20, 30, 40]
order/values=[ten, twenty, thirty, forty]
sorted/first=10, last=40
sorted/[20,40)={20=twenty, 30=thirty}
near/25: lower=20, floor=20, ceiling=30, higher=30
near/20: lower=10, floor=20, ceiling=20, higher=30
view/range={30=thirty, 35=thirty-five}
view/parent={10=ten, 30=thirty, 35=thirty-five, 40=forty}
view/copy={20=twenty, 30=thirty}
view/outsideRejected=true
entry/snapshot=10=ten, current=TEN, setValueRejected=true
poll/first=10=ten, last=40=forty
poll/remaining={20=twenty, 30=thirty}
empty/firstEntry=null, firstKeyThrows=true
descending/keys=[40, 30, 20, 10]
descending/at20: lower=30, higher=10
descending/[40,20)={40=forty, 30=thirty}
descending/parentAfterRemove=[10, 30, 40]
compareZero/size=1, value=2
constructor/SortedMap=[40, 30, 20, 10]
constructor/Map=[10, 20, 30, 40]
nullKeys/order=[null, A, B]
~~~

Mã đã được biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; không khẳng định JVM thực thi là đúng bản JDK 17.

### 12.1. Các dòng order và sorted

Dữ liệu được chèn theo 40, 10, 30, 20 nhưng khóa được in theo 10, 20, 30, 40. Các giá trị đi theo các ánh xạ ấy, không theo một phép sắp giá trị riêng.

Ba biến giao diện cùng tham chiếu tree. Kết quả cho thấy việc nhìn đối tượng qua Map không làm mất thứ tự duyệt của TreeMap, còn kiểu SortedMap cho phép gọi firstKey và subMap.

### 12.2. Hai mốc near được chọn có chủ đích

Mốc 25 nằm giữa hai khóa nên lower và floor cùng cho 20, ceiling và higher cùng cho 30. Nếu chỉ thử mốc này, dễ tưởng các cặp phương thức là đồng nghĩa.

Mốc 20 đúng bằng khóa có sẵn làm khác biệt lộ rõ: lower là 10, floor là 20, ceiling là 20 và higher là 30. Một bài kiểm tra biên phải có trường hợp bằng đúng mốc.

### 12.3. View thay đổi, copy giữ dữ liệu đã sao chép

Copy được tạo trước khi view thêm 35 và xóa 20. Vì vậy copy vẫn chứa 20 và 30, trong khi map gốc phản ánh hai thao tác của view.

Lần put khóa 40 bị từ chối vì 40 là đầu trên bị loại. Việc khóa đó tồn tại trong map gốc không cho view quyền sửa nó.

### 12.4. Entry chụp cặp và poll xóa dữ liệu

FirstEntry giữ cặp 10=ten sau khi map đã được cập nhật thành 10=TEN. Lần setValue trên entry đó bị từ chối. Ví dụ dùng String để tránh nhập nhằng với việc sửa bên trong một đối tượng giá trị có thể thay đổi.

PollFirstEntry và pollLastEntry trả 10=ten và 40=forty, đồng thời map còn 20 và 30. Trên map trống, firstEntry trả null, trong khi firstKey ném NoSuchElementException.

### 12.5. Đảo thứ tự và chọn overload

Map đảo duyệt 40, 30, 20, 10; lower và higher ở mốc 20 được hiểu theo chiều này. Xóa 20 qua view đảo làm map gốc không còn 20.

Hai dòng constructor dùng cùng dữ liệu nguồn giảm dần nhưng khác kiểu biểu thức đối số. Một bản giữ giảm dần; bản qua Map dùng thứ tự tự nhiên. Đây là kết quả lựa chọn overload, không phải dữ liệu bị xáo ngẫu nhiên.

## 13. Lỗi thường gặp và cách nhận diện

| Nhận định dễ sai | Cách kiểm tra đúng |
|---|---|
| TreeMap sắp xếp theo giá trị | Xác định comparator áp lên khóa nào |
| TreeMap giữ thứ tự chèn | Thử chèn ngược thứ tự rồi đọc keySet |
| comparator() bằng null nghĩa là không sắp | Null biểu diễn thứ tự tự nhiên |
| lower và floor giống nhau | Thử mốc bằng đúng một khóa |
| ceiling là phần tử gần nhất theo khoảng cách | Nó là ứng viên phía không nhỏ hơn theo thứ tự |
| subMap mặc định bao gồm cả hai biên | Dạng hai đối số là đầu dưới gồm, đầu trên loại |
| subMap là bản sao để sửa thử | Nó là view; sửa hợp lệ đi vào map gốc |
| Có thể put khóa ngoài vùng vì gốc có khóa đó | Phạm vi view vẫn giới hạn quyền chèn qua view |
| descending chỉ đổi cách in | Nó đảo cả quan hệ điều hướng và biên khoảng |
| firstEntry và pollFirstEntry đều chỉ đọc | Poll loại ánh xạ khỏi map |
| Mọi entry đều setValue được | Entry từ truy vấn điều hướng có hợp đồng riêng |
| compare bằng 0 chỉ ảnh hưởng hiển thị | Nó ảnh hưởng việc TreeMap coi các khóa cùng vị trí |
| Bản copy luôn giữ comparator nguồn | Phải xét constructor được chọn theo kiểu đối số |

## 14. Thực hành và lời giải

### Bài 1. Phân biệt kiểu giao diện và đối tượng

Biến Map tham chiếu một TreeMap có khóa 30, 10, 20. Duyệt keySet có còn theo thứ tự không? Vì sao không gọi trực tiếp floorKey qua biến Map?

**Lời giải:** Đối tượng vẫn là TreeMap nên giữ thứ tự 10, 20, 30 theo quy tắc đang dùng. Map không khai báo floorKey nên kiểu biến không cho phép gọi phương thức ấy. Nếu hàm cần điều hướng, hãy biểu diễn yêu cầu bằng NavigableMap phù hợp.

### Bài 2. Kiểm thử đúng biên

Với khóa 10, 20, 30, hãy tính lowerKey(20), floorKey(20), ceilingKey(20), higherKey(20). Tại sao chỉ thử mốc 25 chưa đủ?

**Lời giải:** Kết quả là 10, 20, 20, 30. Mốc 25 cho lower bằng floor và ceiling bằng higher, nên không bộc lộ sự khác biệt về việc chấp nhận bằng mốc.

### Bài 3. Chọn cấu hình có hiệu lực

Các mốc bắt đầu là 100, 200, 300. Tại thời điểm 200 cần cấu hình ở mốc nào và dùng phương thức nào? Nếu truy vấn 50 thì sao?

**Lời giải:** Dùng floorEntry(200), nhận ánh xạ ở 200. LowerEntry(200) trả mốc 100 nên sai yêu cầu. Tại 50 không có mốc không muộn hơn, kết quả là null; ứng dụng phải định nghĩa chính sách không có cấu hình hoặc dùng mặc định.

### Bài 4. Khoảng và dữ liệu gốc

Map có 10, 20, 30, 40. Tạo subMap(20, 40), rồi gọi clear trên view. Những khóa nào còn trong gốc? Put(40, value) qua view có được không?

**Lời giải:** View đại diện 20 và 30; clear loại hai ánh xạ đó khỏi gốc, còn 10 và 40. Khóa 40 ngoài view do đầu trên bị loại, nên put qua view bị từ chối bằng IllegalArgumentException.

### Bài 5. Thứ tự đảo

Map gốc tăng dần có 10, 20, 30, 40. Trên descendingMap, lowerKey(20) và higherKey(20) là gì? SubMap(40, true, 20, false) chứa gì?

**Lời giải:** Lower là 30 và higher là 10 theo thứ tự đảo. Khoảng bắt đầu ở 40 bao gồm, kết thúc ở 20 loại, nên chứa 40 và 30.

### Bài 6. Comparator vô tình gộp khóa

Khóa là cặp score và id, nhưng comparator chỉ xét score. Hai bản ghi cùng score khác id có chắc được giữ thành hai ánh xạ không? Sửa như thế nào nếu cần giữ cả hai?

**Lời giải:** Không. Comparator cho kết quả 0 khi score bằng nhau nên TreeMap coi chúng cùng vị trí khóa. Có thể thêm id làm tiêu chí phụ, đồng thời thiết kế quan hệ equals tương thích và giữ khóa ổn định.

### Bài 7. Xem và lấy ra

Tác vụ ghi log cần in ánh xạ đầu mà không sửa map, map có thể trống. Chọn firstEntry hay pollFirstEntry? Có thể setValue trên kết quả điều hướng để cập nhật gốc không?

**Lời giải:** Chọn firstEntry và xử lý null nếu trống. PollFirstEntry sẽ loại ánh xạ nếu có. Entry từ truy vấn điều hướng TreeMap không hỗ trợ setValue ghi ngược; muốn sửa phải dùng thao tác map phù hợp.

### Bài 8. Sao chép và comparator

Nguồn là TreeMap giảm dần. Một biến SortedMap và một biến Map cùng trỏ nguồn. Hai lần new TreeMap với hai biến ấy có luôn cùng thứ tự không?

**Lời giải:** Không. Constructor nhận SortedMap giữ thứ tự nguồn; constructor nhận Map dùng thứ tự tự nhiên. Overload được chọn theo kiểu biểu thức ở lúc biên dịch. Muốn rõ ý định có thể tạo đích với comparator cụ thể rồi sao chép ánh xạ.

## 15. Cách đọc một truy vấn trước khi chạy

Trước khi viết floor, subMap hoặc descendingMap, hãy trả lời bốn câu: thứ tự nào đang dùng, có nhận bằng mốc hay không, kết quả là view hay cặp/bản sao, và thao tác có sửa dữ liệu không.

Khi bốn câu này rõ ràng, chuỗi Map → SortedMap → NavigableMap trở thành các mức khả năng dễ dùng: ánh xạ, thứ tự, rồi điều hướng theo thứ tự. TreeMap cung cấp một cách triển khai để nối các khả năng ấy với bài toán thực tế.
