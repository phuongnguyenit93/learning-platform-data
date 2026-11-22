# Kiến thức nền và trình tự học các nhóm collection

Học Java Collections Framework dễ bị biến thành việc ghi nhớ tên lớp: `ArrayList`, `HashSet`, `HashMap`, rồi chọn một lớp theo thói quen. Cách học đó có thể giúp viết được vài câu lệnh nhưng chưa giúp trả lời câu hỏi quan trọng: **dữ liệu này cần được tổ chức theo quy tắc nào, và lựa chọn đó có đúng khi yêu cầu thay đổi không?**

Bài này xây dựng nền tảng và trình tự học cho các nhóm collection trong Java Core. Mục tiêu là biết mình cần học gì trước, vì sao nên học theo thứ tự đó, khi nào có thể chuyển sang nhóm tiếp theo và cách nối các nhóm thành một lời giải hoàn chỉnh.

Các ví dụ dùng API có trong Java 17. Chương trình đầy đủ ở phần minh họa có thể biên dịch bằng JDK 17 trở lên. Những đoạn ngắn còn lại chỉ minh họa một ý; chúng không phải các chương trình độc lập.

## 1. Bắt đầu từ bài toán, không bắt đầu từ tên lớp

Giả sử một chương trình nhận các lượt đăng ký có mã:

```text
S2, S1, S2
```

Cùng một dữ liệu đầu vào có thể sinh ra nhiều yêu cầu:

| Yêu cầu | Ý nghĩa cần giữ | Nhóm nên tìm hiểu |
| --- | --- | --- |
| Giữ đầy đủ từng lượt đăng ký theo vị trí | Có thứ tự, cho phép lặp | `List` |
| Lấy các mã đã xuất hiện | Không lặp | `Set` |
| Đếm số lần đăng ký theo mã | Một khóa gắn với một giá trị đếm | `Map` |
| Xử lý lần lượt theo thứ tự chờ | Chính sách lấy phần tử ở đầu | `Queue` hoặc `Deque` dùng như hàng đợi |
| Xử lý công việc ưu tiên trước | Chính sách chọn phần tử theo độ ưu tiên | `PriorityQueue` |
| Lấy mã theo thứ tự tăng dần hoặc tìm mã gần nhất | Có quan hệ sắp xếp và điều hướng | `SortedSet`, `NavigableSet`, `SortedMap`, `NavigableMap` |

Không có một collection nào tự diễn đạt tốt mọi yêu cầu trên. Đổi từ `List` sang `Set` có thể làm mất thông tin về các lượt lặp; đổi sang một lớp không bảo đảm thứ tự có thể làm mất thứ tự cần cho nghiệp vụ.

Trước khi viết `new`, hãy trả lời:

1. Đơn vị được lưu là một phần tử hay một cặp khóa–giá trị?
2. Phần tử lặp có mang ý nghĩa không?
3. Cần vị trí, thứ tự thêm, thứ tự sắp xếp hay thứ tự ưu tiên?
4. Thao tác thường xuyên là tra cứu, thêm cuối, lấy đầu hay tìm theo khoảng?
5. Ai được sửa dữ liệu? Có nhiều luồng cùng truy cập không?

Năm câu hỏi này là sợi dây nối toàn bộ lộ trình.

## 2. Kiến thức nền cần chuẩn bị

Không cần thành thạo toàn bộ Java trước khi dùng `ArrayList`. Tuy nhiên, một số kiến thức phải được học trước khi giải thích sâu cơ chế của từng nhóm.

### 2.1. Biến, vòng lặp, phương thức và mảng

Cần biết khai báo biến, truyền tham số, nhận giá trị trả về, dùng `if`, `for`, `while` và đọc một phương thức đơn giản.

Mảng là điểm so sánh tốt:

- Mảng có độ dài cố định sau khi tạo.
- Mảng có chỉ số bắt đầu từ 0.
- Mảng lưu được kiểu nguyên thủy hoặc kiểu tham chiếu.
- Khi muốn thêm nhiều phần tử hơn sức chứa, phải tự tạo mảng khác và chuyển dữ liệu nếu làm thủ công.

Collection giải quyết nhiều nhu cầu tổ chức dữ liệu mà người học không nên phải tự xây lại mỗi lần. Tuy vậy, collection không phải chỉ là “mảng có thể tăng kích thước”: tập hợp không lặp, bảng ánh xạ và hàng đợi có những quy tắc riêng.

**Dấu hiệu đã đủ nền:** tự viết được vòng lặp tính tổng một mảng và giải thích vì sao truy cập chỉ số bằng độ dài mảng là sai.

### 2.2. Đối tượng, tham chiếu và sự thay đổi

Với collection chứa đối tượng, cần hiểu rằng collection thông thường giữ các tham chiếu đến đối tượng. Thêm một đối tượng vào danh sách không tự tạo bản sao sâu của đối tượng đó.

Hai biến có thể cùng trỏ đến một danh sách; hai danh sách khác nhau có thể cùng trỏ đến những phần tử giống nhau về danh tính đối tượng.

Đoạn minh họa:

```java
List<StringBuilder> first = new ArrayList<>();
first.add(new StringBuilder("A"));

List<StringBuilder> second = new ArrayList<>(first);
second.get(0).append("B");
```

Sau các câu lệnh này:

- `first` và `second` là hai đối tượng danh sách khác nhau.
- Phần tử ở vị trí 0 của chúng trỏ đến cùng một `StringBuilder`.
- Nội dung đối tượng đó là `"AB"`.

Đây là lý do cần phân biệt **sao chép cấu trúc chứa tham chiếu** với **sao chép toàn bộ các đối tượng bên trong**. Kiến thức này sẽ được dùng khi học constructor sao chép, view, defensive copy và collection không cho sửa.

### 2.3. Interface, lớp triển khai và đa hình

Người học cần đọc được khai báo:

```java
List<String> names = new ArrayList<>();
```

Trong đó:

- `List<String>` diễn đạt hợp đồng mà đoạn mã cần.
- `ArrayList<>` là lớp triển khai được chọn để đáp ứng hợp đồng đó.
- Biến `names` chỉ cho gọi trực tiếp các phương thức mà kiểu khai báo cung cấp.

Lập trình theo interface giúp giảm phụ thuộc vào một lớp cụ thể. Tuy nhiên, thay lớp triển khai vẫn cần kiểm tra thứ tự, hiệu năng, quy tắc `null`, khả năng sửa và yêu cầu đồng bộ. Cùng triển khai một interface không có nghĩa là mọi đặc điểm đều giống nhau.

**Dấu hiệu đã đủ nền:** giải thích được vì sao không thể viết `new List<String>()`, và vì sao một biến kiểu `Collection<String>` không cung cấp thao tác truy cập chỉ số của `List`.

### 2.4. Generics và kiểu phần tử

Cần hiểu `List<String>`, `Set<Integer>`, `Map<String, Integer>` và tác dụng kiểm tra kiểu khi biên dịch.

Những điều cần biết sớm:

- Tham số kiểu của generics là kiểu tham chiếu: dùng `Integer`, không dùng `int` trong `List<...>`.
- Boxing và unboxing có thể xuất hiện khi đưa số nguyên vào hoặc lấy ra khỏi collection.
- Unboxing một giá trị `null` có thể gây `NullPointerException`.
- Raw type như `List` làm suy yếu kiểm tra kiểu và nên tránh trong mã mới.
- `List<Integer>` không phải là kiểu con của `List<Number>`.

Không cần bắt đầu bằng toàn bộ lý thuyết wildcard. Trình tự phù hợp là dùng collection có kiểu cụ thể trước; sau đó học `?`, `? extends T`, `? super T` khi thiết kế phương thức nhận hoặc chuyển dữ liệu giữa các collection.

**Dấu hiệu đã đủ nền:** đọc được một phương thức nhận `List<String>` mà không phải ép kiểu từng phần tử về `String`.

### 2.5. Ngoại lệ và hợp đồng phương thức

Không phải lỗi nào khi dùng collection cũng là lỗi của cấu trúc dữ liệu. Cần biết đọc tên ngoại lệ cùng điều kiện gây lỗi:

| Ngoại lệ hoặc kết quả | Câu hỏi nên kiểm tra |
| --- | --- |
| `IndexOutOfBoundsException` | Chỉ số có nằm trong phạm vi hợp lệ không? |
| `UnsupportedOperationException` | Collection này có hỗ trợ thao tác sửa đang gọi không? |
| `NullPointerException` | Đã truyền `null` vào nơi không cho phép hoặc unbox `null` chưa? |
| `ClassCastException` | Có raw type, ép kiểu sai hoặc phần tử không thể so sánh không? |
| `ConcurrentModificationException` | Có sửa cấu trúc ngoài cách iterator cho phép khi đang duyệt không? |
| `false`, `null` hoặc giá trị cũ | Phương thức này dùng giá trị trả về để báo điều gì? |

Từ “concurrent” trong tên ngoại lệ không chứng minh chương trình đang chạy nhiều luồng. Một luồng cũng có thể gây sửa đổi không hợp lệ trong lúc duyệt. Không dùng ngoại lệ này như cơ chế bảo đảm an toàn giữa các luồng.

### 2.6. Bình đẳng, băm và so sánh

Ba khái niệm phải được tách biệt:

- `==` trên tham chiếu kiểm tra có cùng đối tượng hay không.
- `equals` diễn đạt bình đẳng theo giá trị mà lớp quy định.
- `Comparator` hoặc `Comparable` diễn đạt thứ tự so sánh.

Trước `HashSet` và `HashMap`, phải học hợp đồng `equals`–`hashCode`: hai đối tượng bằng nhau theo `equals` phải có cùng mã băm; cùng mã băm không bắt buộc là bằng nhau.

Trước `TreeSet`, `TreeMap` và `PriorityQueue`, phải học so sánh tự nhiên hoặc `Comparator`. Kết quả so sánh âm, bằng 0, dương diễn đạt quan hệ thứ tự; không nên viết bộ so sánh số bằng cách trừ nếu phép trừ có thể tràn.

Đặc biệt, `TreeSet` xem hai phần tử là cùng vị trí trong tập khi phép so sánh trả về 0. `TreeMap` cũng dùng phép so sánh để nhận diện khóa tương đương trong cây. Nếu chỉ so sánh sinh viên theo tên, hai sinh viên khác mã nhưng cùng tên có thể bị coi là trùng trong một `TreeSet`. Bộ so sánh nên nhất quán với `equals` để tập hợp hoặc bảng ánh xạ tuân thủ đúng hợp đồng tổng quát.

### 2.7. Độ phức tạp và cấu trúc dữ liệu cơ bản

Chỉ cần bắt đầu với:

- `O(1)`: số bước không tăng theo số phần tử ở mức mô hình phân tích.
- `O(log n)`: số bước tăng chậm theo kích thước.
- `O(n)`: có thể phải xem qua số phần tử tỷ lệ với kích thước.
- `O(n log n)`: thường gặp ở các thuật toán sắp xếp dựa trên so sánh.

Sau đó mới tìm hiểu mảng động, danh sách liên kết, bảng băm, cây cân bằng và heap.

Độ phức tạp không phải thời gian đo bằng mili giây. Cần phân biệt trường hợp trung bình, trường hợp xấu nhất và chi phí khấu hao; dữ liệu nhỏ, cấp phát bộ nhớ và cách truy cập cũng ảnh hưởng kết quả thực tế.

## 3. Bản đồ các nhóm trước khi đi sâu

Trong Java 17, có thể dùng sơ đồ rút gọn sau. Sơ đồ chỉ thể hiện các interface chính phục vụ lộ trình này, không phải toàn bộ cây kiểu của JDK.

```text
Iterable<E>
└── Collection<E>
    ├── List<E>
    ├── Set<E>
    │   └── SortedSet<E>
    │       └── NavigableSet<E>
    └── Queue<E>
        └── Deque<E>

Map<K, V>
└── SortedMap<K, V>
    └── NavigableMap<K, V>
```

`Map` thuộc Java Collections Framework nhưng không kế thừa `Collection`. Nó tổ chức các cặp khóa–giá trị; `keySet()`, `values()` và `entrySet()` cung cấp các góc nhìn dạng collection. Vì vậy, không được suy ra rằng phương thức nhận `Collection<E>` sẽ nhận trực tiếp một `Map<K, V>`. Xem [tổng quan Collections Framework của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html).

Ba tên dễ nhầm:

| Tên | Vai trò |
| --- | --- |
| “collection” trong lời giải thích | Tên gọi chung cho cấu trúc chứa nhiều phần tử |
| `Collection<E>` | Interface nền của `List`, `Set`, `Queue` và các nhánh liên quan |
| `Collections` | Lớp chứa các phương thức tiện ích tĩnh như sắp xếp, đảo thứ tự hoặc tạo wrapper |

Không học `Collections` bằng cách tưởng đó là phiên bản số nhiều của interface `Collection`.

## 4. Trình tự học đề xuất

Đây là thứ tự phục vụ người mới: từ thao tác dễ quan sát đến các hợp đồng dễ sai. `Queue` và `Deque` cơ bản có thể học ngay sau `List`; phần hàng đợi ưu tiên nên học sau kiến thức so sánh. Không có yêu cầu mọi người phải học đúng một thứ tự cứng.

### Chặng 1: Collection và cách duyệt

Học các thao tác chung như `size`, `isEmpty`, `add`, `contains`, `remove`, `clear` và vòng lặp `for-each`.

Mục tiêu chưa phải là phân tích cơ chế bên trong. Mục tiêu là hiểu “chứa phần tử”, đọc giá trị trả về và biết thao tác nào làm thay đổi dữ liệu.

Tiếp theo học `Iterable`, `Iterator`, `hasNext()`, `next()` và thao tác xóa qua iterator khi được hỗ trợ. `for-each` thuận tiện cho đọc tuần tự; không phải lời cho phép gọi trực tiếp mọi phương thức sửa collection trong thân vòng lặp.

Bài tập đạt chặng: nhận một danh sách số, đếm các số dương bằng vòng lặp; sau đó loại số âm bằng cách phù hợp như `removeIf` trên danh sách cho phép sửa.

**Có thể chuyển chặng khi:** giải thích được vì sao kết quả `add` hoặc `remove` phải được đọc theo hợp đồng cụ thể, và vì sao biến chứa collection không tự cho biết nó hỗ trợ mọi thao tác sửa.

### Chặng 2: List, bắt đầu với ArrayList

`List` phù hợp khi vị trí và các phần tử lặp có ý nghĩa. Học:

1. Thêm cuối, chèn tại chỉ số, đọc bằng `get`, thay bằng `set`.
2. Xóa theo chỉ số khác với xóa theo giá trị.
3. Duyệt theo thứ tự và tìm kiếm.
4. Quan hệ giữa kích thước logic với sức chứa của mảng bên trong `ArrayList`.
5. Chi phí dịch phần tử khi chèn hoặc xóa ở giữa.

Bắt đầu với `ArrayList` vì dễ nối với kiến thức mảng. Sau đó so sánh `LinkedList` để thấy cùng là `List` nhưng cơ chế truy cập khác nhau.

Không kết luận “thêm xóa nhiều thì dùng `LinkedList`” nếu chưa hỏi vị trí cần sửa đã được xác định như thế nào. `LinkedList.get(i)` cần đi qua các nút; nếu mỗi vòng lại gọi `get(i)`, một lần duyệt có thể bị biến thành chi phí bậc hai.

Bài tập đạt chặng: quản lý các lượt đăng ký và giữ cả những lượt có cùng mã. Quy định rõ đổi một vị trí khác với xóa mọi lượt của một mã.

**Có thể chuyển chặng khi:** chọn được cách duyệt phù hợp, giải thích được chi phí chèn giữa `ArrayList`, và không nhầm thứ tự danh sách với thứ tự đã sắp xếp. Hợp đồng nền ở [List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### Chặng 3: Set và ý nghĩa “không trùng”

Học `Set` sau khi đã có khái niệm `equals` và `hashCode`.

So sánh:

- `HashSet`: kiểm tra tồn tại và loại trùng, không bảo đảm thứ tự duyệt.
- `LinkedHashSet`: loại trùng và giữ thứ tự thêm trong cách dùng thông thường.
- `TreeSet`: quản lý phần tử theo thứ tự so sánh; để dành các truy vấn điều hướng cho chặng sau.

Câu hỏi quan trọng là **thế nào là hai phần tử trùng nhau trong mô hình của bài toán?** Với `String`, đáp án tương đối trực quan. Với một lớp `Student`, phải xác định bình đẳng theo mã sinh viên hay theo cả mã và tên.

Bài tập đạt chặng: từ các lượt đăng ký, lấy mã duy nhất; lần lượt yêu cầu không quan tâm thứ tự, giữ thứ tự xuất hiện và tăng dần. Chỉ ra thay đổi lớp triển khai nào đáp ứng từng yêu cầu.

**Có thể chuyển chặng khi:** giải thích được vì sao một tập hợp vẫn có thể chứa hai đối tượng khác tham chiếu nhưng chỉ giữ một phần tử theo bình đẳng giá trị; đồng thời hiểu thứ tự của tập không được suy ra từ vài lần in thử. Xem [hợp đồng Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### Chặng 4: Map và tổ chức dữ liệu theo khóa

Học `Map` sau `Set` giúp tái sử dụng kiến thức bình đẳng và băm cho khóa.

Nắm các thao tác `put`, `get`, `containsKey`, `remove`, `getOrDefault` và duyệt `entrySet`. Khi đã hiểu phiên bản vòng lặp, mới thêm `merge`, `computeIfAbsent` hoặc các thao tác nhận hàm.

Những quy tắc cần quan sát:

- Khóa không lặp theo quy tắc của map.
- Giá trị có thể lặp.
- `put` một khóa đã có thường thay giá trị gắn với khóa đó.
- Một khóa có thể gắn với một collection, ví dụ `Map<String, List<String>>`, nếu bài toán cần nhiều giá trị.
- `get(key) == null` chưa luôn đủ để kết luận khóa không tồn tại trong map cho phép giá trị `null`.

So sánh `HashMap`, `LinkedHashMap` và `TreeMap` theo yêu cầu tra cứu, thứ tự và chi phí.

Bài tập đạt chặng: đếm số lượt đăng ký theo mã. Sau đó đổi sang gom danh sách lượt theo mã; giải thích vì sao hai bài toán cần kiểu giá trị khác nhau.

**Có thể chuyển chặng khi:** phân biệt được “khóa chưa có” với “giá trị cũ bị thay”, và dùng được `entrySet` để xử lý từng cặp. Xem [hợp đồng Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Chặng 5: Queue và Deque theo chính sách xử lý

Ở các chặng trước, câu hỏi chính là “lưu thế nào?”. Với hàng đợi, cần hỏi thêm “lấy phần tử nào tiếp theo?”.

Học `Deque` với `ArrayDeque` để thấy:

- Thêm cuối, lấy đầu tạo cách dùng FIFO.
- Thêm và lấy cùng một đầu tạo cách dùng LIFO.
- `Deque` cung cấp thao tác ở cả hai đầu.
- Các cặp phương thức có thể khác cách báo thất bại: ném ngoại lệ hoặc trả giá trị đặc biệt.

Ví dụ, khi hàng đợi rỗng, `remove()` ném ngoại lệ còn `poll()` trả `null`. Không nên đưa `null` vào hàng đợi vì sẽ gây mơ hồ với kết quả rỗng; `ArrayDeque` không cho phần tử `null`.

Sau đó học `PriorityQueue`. Đây không phải hàng đợi FIFO. Với thứ tự tự nhiên của số nguyên, phần tử nhỏ nhất được lấy trước. Một bộ so sánh khác có thể định nghĩa độ ưu tiên khác. Duyệt trực tiếp `PriorityQueue` không bảo đảm thứ tự toàn bộ các phần tử; muốn quan sát thứ tự xử lý phải lấy dần từ đầu.

Bài tập đạt chặng: mô phỏng hàng chờ và một danh sách công việc có ưu tiên. Chứng minh thứ tự thêm với thứ tự xử lý có thể khác nhau.

**Có thể chuyển chặng khi:** phân biệt được FIFO, LIFO và ưu tiên; biết chọn phương thức báo rỗng phù hợp. Xem [Queue của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

### Chặng 6: Các nhóm có sắp xếp và điều hướng

Quay lại `TreeSet` và `TreeMap` sau khi đã học kỹ `Comparable` và `Comparator`.

Phân biệt:

- `SortedSet` và `SortedMap`: duy trì thứ tự cùng các thao tác theo miền giá trị.
- `NavigableSet` và `NavigableMap`: thêm các truy vấn như phần tử hoặc khóa nhỏ hơn, nhỏ hơn hoặc bằng, lớn hơn hoặc bằng, lớn hơn.

Không cần học thuộc ngay mọi tên phương thức. Trước hết nối yêu cầu với ý nghĩa của `lower`, `floor`, `ceiling`, `higher`.

Bài tập đạt chặng: từ tập điểm `{50, 70, 90}`, phân biệt điểm gần nhất không vượt quá 80 với điểm nhỏ nhất từ 80 trở lên. Kết quả lần lượt là 70 và 90.

**Có thể chuyển chặng khi:** diễn đạt được điều kiện biên và hiểu comparator ảnh hưởng cả thứ tự lẫn nhận diện phần tử hoặc khóa trong cấu trúc cây.

### Chặng 7: Khả năng sửa, view và sao chép

Đây là phần cần học trước khi thiết kế API trả collection ra ngoài một lớp.

Phân biệt:

| Cách tạo hoặc lấy danh sách | Ý nghĩa cần nhớ |
| --- | --- |
| `new ArrayList<>(source)` | Tạo danh sách mới có thể sửa; không sao chép sâu phần tử |
| `List.of(...)` | Danh sách không cho sửa và không nhận phần tử `null` |
| `List.copyOf(source)` | Lấy danh sách không cho sửa với các phần tử của nguồn tại thời điểm gọi; không sao chép sâu phần tử |
| `Arrays.asList(array)` | Danh sách kích thước cố định gắn với mảng; có thể thay phần tử bằng `set`, không thêm hoặc xóa phần tử |
| `Collections.unmodifiableList(source)` | Góc nhìn không cho sửa qua wrapper; thay đổi ở nguồn vẫn có thể được nhìn thấy |
| `list.subList(from, to)` | Góc nhìn một phần của danh sách, cần tôn trọng hợp đồng với danh sách nền |

Không cho sửa qua một tham chiếu không đồng nghĩa toàn bộ dữ liệu là bất biến sâu. Nếu phần tử là đối tượng có thể thay đổi, nội dung của chính phần tử vẫn có thể thay đổi. Với `List.copyOf`, không nên dựa vào việc luôn tạo ra một đối tượng mới; điều cần dựa vào là hợp đồng của kết quả.

Bài tập đạt chặng: cung cấp danh sách từ một lớp quản lý dữ liệu; chọn giữa cho sửa trực tiếp, trả view chỉ đọc và trả bản chụp cấu trúc. Giải thích ảnh hưởng khi nguồn hoặc phần tử thay đổi.

### Chặng 8: Thuật toán tiện ích và xử lý bằng Stream

Học sắp xếp, đảo thứ tự, tìm kiếm và sao chép sau khi hiểu collection nguồn có thể sửa hay không.

Một số điều kiện phải kiểm tra:

- Sắp xếp cần cách so sánh đúng.
- Tìm kiếm nhị phân cần dữ liệu được sắp theo đúng thứ tự tương ứng.
- Sắp xếp tại chỗ khác với tạo danh sách kết quả mới.
- Loại trùng vẫn phụ thuộc ý nghĩa bình đẳng.
- Kết quả chuyển đổi có thể có hợp đồng sửa khác với nguồn.

Sau vòng lặp, học lambda, method reference và Stream để viết lọc, ánh xạ, gom nhóm, đếm. Cần phân biệt collection lưu dữ liệu với stream biểu diễn một luồng xử lý; stream không phải collection thứ hai và không dùng lại sau khi đã thực hiện thao tác kết thúc.

Không dùng Stream để che việc chưa hiểu kiểu dữ liệu, thứ tự hoặc quy tắc trùng. Trước hết viết được lời giải bằng vòng lặp, sau đó so sánh độ rõ ràng của hai cách.

### Chặng 9: Collection dùng chung giữa nhiều luồng

Chỉ học phần này sau kiến thức cơ bản về luồng, đồng bộ, hiển thị bộ nhớ và thao tác nguyên tử.

Các nhánh cần khảo sát gồm wrapper đồng bộ, `ConcurrentHashMap`, `BlockingQueue`, `CopyOnWriteArrayList` và các collection đồng thời chuyên dụng.

Cần phân biệt:

- Một phương thức an toàn giữa các luồng.
- Một chuỗi thao tác nghiệp vụ nguyên tử.
- Cách duyệt mà cấu trúc cụ thể cho phép.
- Khả năng nhìn thấy thay đổi từ luồng khác.

Chẳng hạn, “nếu chưa có thì thêm” bằng hai lời gọi riêng không tự trở thành một thao tác nguyên tử chỉ vì map có hỗ trợ truy cập đồng thời. Phải chọn thao tác hoặc cơ chế đồng bộ phù hợp.

`parallelStream()` cũng không biến mọi thao tác sửa collection trong lambda thành an toàn.

**Dấu hiệu đã đạt:** giải thích được vì sao đổi lớp collection không đủ để sửa mọi lỗi đồng thời. Cơ chế đồng bộ phải được đọc theo tài liệu của từng lớp; interface `Collection` không đưa ra một bảo đảm đồng bộ chung cho mọi lớp triển khai. Xem [Collection: hợp đồng đồng bộ, view và khả năng sửa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 5. Hiệu năng cần học sau ngữ nghĩa

Khi đã biết kiểu dữ liệu phù hợp, mới so sánh chi phí của những lựa chọn đáp ứng cùng yêu cầu.

| Cấu trúc và thao tác | Mô hình chi phí thường dùng | Điều phải giữ trong đầu |
| --- | --- | --- |
| `ArrayList.get(i)` | `O(1)` | Chỉ số hợp lệ |
| Thêm cuối `ArrayList` | `O(1)` khấu hao | Một lần tăng sức chứa có thể phải sao chép nhiều phần tử |
| Chèn hoặc xóa giữa `ArrayList` | `O(n)` | Có dịch các phần tử phía sau |
| `LinkedList.get(i)` | `O(n)` | Phải tìm nút theo vị trí |
| Thêm hoặc xóa qua vị trí iterator phù hợp ở danh sách liên kết | Thao tác nối hoặc bỏ nút là `O(1)` | Việc đi đến vị trí trước đó vẫn có chi phí |
| Tra cứu cơ bản bằng bảng băm | Kỳ vọng gần `O(1)` với điều kiện băm phù hợp | Không phải bảo đảm vô điều kiện cho mọi đầu vào |
| Tra cứu trong cây cân bằng | `O(log n)` | Chi phí so sánh cũng cần tính đến |
| Thêm hoặc lấy phần tử đầu `PriorityQueue` | Thường học theo `O(log n)` | Không áp dụng cùng kết luận cho tìm phần tử bất kỳ |

Bảng này giúp xây dựng trực giác, không thay thế tài liệu của từng phương thức. Chỉ đo hiệu năng sau khi bảo đảm hai lời giải có cùng kết quả, cùng hợp đồng và khối lượng công việc đại diện.

Ví dụ, dùng `HashSet` nhanh hơn một vòng tìm trên danh sách không có giá trị nếu bài toán cần giữ các phần tử lặp mà tập hợp đã loại bỏ.

## 6. Chương trình tổng hợp: một đầu vào, nhiều cách tổ chức

Chương trình sau nối các chặng cơ bản. Không có xử lý đa luồng hoặc phụ thuộc bên ngoài.

Lưu nguyên nội dung vào tệp `CollectionLearningPathDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionLearningPathDemo {
    public static void main(String[] args) {
        List<String> registrations =
                new ArrayList<>(List.of("S2", "S1", "S2"));

        Set<String> uniqueCodes = new LinkedHashSet<>(registrations);

        Map<String, Integer> counts = new TreeMap<>();
        for (String code : registrations) {
            counts.put(code, counts.getOrDefault(code, 0) + 1);
        }

        Set<String> sortedCodes = new TreeSet<>(uniqueCodes);

        Deque<String> waiting = new ArrayDeque<>(uniqueCodes);
        List<String> processed = new ArrayList<>();
        while (!waiting.isEmpty()) {
            processed.add(waiting.removeFirst());
        }

        PriorityQueue<Integer> priorities =
                new PriorityQueue<>(List.of(30, 10, 20));
        List<Integer> priorityOrder = new ArrayList<>();
        while (!priorities.isEmpty()) {
            priorityOrder.add(priorities.remove());
        }

        List<String> snapshot = List.copyOf(registrations);
        registrations.add("S3");

        System.out.println("Unique codes: " + uniqueCodes);
        System.out.println("Counts by code: " + counts);
        System.out.println("Sorted codes: " + sortedCodes);
        System.out.println("FIFO order: " + processed);
        System.out.println("Priority order: " + priorityOrder);
        System.out.println("Source size: " + registrations.size());
        System.out.println("Snapshot size: " + snapshot.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CollectionLearningPathDemo.java
java CollectionLearningPathDemo
```

Kết quả chuẩn:

```text
Unique codes: [S2, S1]
Counts by code: {S1=1, S2=2}
Sorted codes: [S1, S2]
FIFO order: [S2, S1]
Priority order: [10, 20, 30]
Source size: 4
Snapshot size: 3
```

Giải thích theo yêu cầu thay vì theo từng câu lệnh:

1. `registrations` ban đầu giữ ba lượt, trong đó `"S2"` xuất hiện hai lần. `List` bảo toàn thông tin này.
2. `uniqueCodes` chỉ giữ hai mã và giữ thứ tự xuất hiện đầu tiên nhờ `LinkedHashSet`.
3. `counts` dùng mã làm khóa, số lần làm giá trị. `TreeMap` giúp thứ tự in khóa ổn định theo thứ tự tự nhiên của chuỗi.
4. `sortedCodes` biểu diễn một tập có sắp xếp, nên `"S1"` đứng trước `"S2"`.
5. `waiting` được thêm theo thứ tự của `uniqueCodes`, rồi lấy đầu bằng `removeFirst()`; đây là cách dùng FIFO.
6. `priorities` nhận 30, 10, 20 nhưng lấy ra 10, 20, 30. Chương trình lấy từng phần tử bằng `remove()`, không dựa vào thứ tự iterator của heap.
7. `snapshot` lấy từ ba lượt ban đầu. Thêm `"S3"` vào danh sách nguồn khiến kích thước nguồn thành 4, còn kích thước danh sách chụp vẫn là 3.

Chương trình dùng `String` và `Integer` để tránh phải định nghĩa bình đẳng cùng khả năng so sánh của lớp nghiệp vụ ngay trong ví dụ nhập môn. Khi chuyển sang đối tượng tự định nghĩa, phải quay lại kiến thức `equals`, `hashCode` và `Comparator`.

## 7. Những lỗi học và dùng collection thường gặp

### 7.1. Nhầm thứ tự thêm với thứ tự sắp xếp

`List` có thứ tự vị trí nhưng không tự sắp xếp giá trị. `LinkedHashSet` giữ thứ tự thêm nhưng không phải thứ tự tăng dần. `HashSet` không bảo đảm thứ tự dù một lần in trông có vẻ được sắp.

Hãy ghi rõ loại thứ tự mà bài toán cần trước khi chọn lớp.

### 7.2. Dùng Set rồi phát hiện đã mất dữ liệu lặp

Nếu một sinh viên có thể đăng ký nhiều lần và mỗi lượt là một sự kiện cần thống kê, chuyển ngay tất cả sang `Set` làm mất thông tin.

Có thể giữ `List` làm dữ liệu nguồn và tạo thêm `Set` cho nhu cầu riêng. Chọn collection cho một góc nhìn không nhất thiết thay thế nguồn dữ liệu gốc.

### 7.3. Nhầm hai phương thức remove của List<Integer>

Đoạn minh họa:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
numbers.remove(1);
numbers.remove(Integer.valueOf(30));
```

Lời gọi đầu dùng đối số `int`, nên xóa phần tử ở chỉ số 1, tức 20. Lời gọi sau dùng `Integer`, nên xóa theo giá trị 30. Danh sách cuối còn `[10]`.

Đây là kiến thức overload và boxing được áp dụng vào collection, không phải một quy tắc ngẫu nhiên của danh sách.

### 7.4. Thay khóa sau khi đã đưa vào HashMap

Nếu một trường được dùng trong `equals` hoặc `hashCode` bị đổi sau khi đối tượng đã làm khóa, cấu trúc băm không tự bố trí lại khóa theo giá trị mới. Việc tra cứu có thể không còn hoạt động như người viết mong đợi.

Nên thiết kế khóa có giá trị ổn định. Vấn đề tương tự xuất hiện khi sửa trạng thái dùng để so sánh của phần tử đang ở trong một tập hoặc map có sắp xếp.

### 7.5. Coi view là bản sao

Lấy `map.keySet()` hoặc `list.subList(...)` không mặc nhiên tạo bản sao độc lập. Xóa qua một view được phép sửa có thể tác động đến cấu trúc nền.

Trước mỗi API trả collection, hỏi: **đây là đối tượng mới độc lập, view sống theo nguồn hay wrapper hạn chế thao tác?**

### 7.6. Coi unmodifiable là bất biến sâu

`List.of` không cho thêm, xóa hoặc thay phần tử trong danh sách. Nó không khóa các đối tượng có thể thay đổi mà danh sách đang tham chiếu.

Nếu cần một kết quả không thay đổi về mặt nghiệp vụ, phải xét cả loại phần tử, quyền sở hữu dữ liệu và khả năng người khác đang giữ tham chiếu tới phần tử.

### 7.7. Học Stream quá sớm

Một chuỗi `filter`–`map`–`collect` có thể ngắn hơn vòng lặp, nhưng không giải thích thay cho người viết về trùng lặp, thứ tự, bình đẳng hay khả năng sửa.

Thứ tự nên là hiểu dữ liệu và hợp đồng, làm đúng bằng các thao tác cơ bản, rồi mới chọn cách diễn đạt bằng Stream.

### 7.8. Chọn cấu trúc theo một mẹo hiệu năng

“Map luôn nhanh”, “LinkedList luôn tốt cho thêm xóa”, hoặc “collection đồng thời giải quyết mọi lỗi luồng” đều thiếu điều kiện.

Hãy nêu thao tác, dữ liệu, bảo đảm cần có và chi phí liên quan. Khi chưa chứng minh được lựa chọn, quay lại hợp đồng và bài toán thay vì thay lớp ngẫu nhiên.

## 8. Bài tập theo trình tự và tiêu chí hoàn thành

| Bài tập | Kiến thức chính | Bằng chứng đã hiểu |
| --- | --- | --- |
| Giữ danh sách lượt đăng ký và sửa một lượt theo vị trí | `List` | Không vô tình xóa mọi lượt cùng mã |
| Lấy mã duy nhất theo ba yêu cầu thứ tự | `Set` | Phân biệt không bảo đảm thứ tự, thứ tự thêm và thứ tự so sánh |
| Đếm lượt theo mã và gom lượt theo mã | `Map` | Chọn đúng kiểu giá trị số đếm hoặc danh sách |
| Mô phỏng hàng chờ, hoàn tác và ưu tiên công việc | `Deque`, `PriorityQueue` | Giải thích rõ FIFO, LIFO và ưu tiên |
| Tìm mốc gần nhất không vượt giá trị cho trước | `NavigableSet` hoặc `NavigableMap` | Xử lý đúng bằng, nhỏ hơn và lớn hơn |
| Trả dữ liệu từ một lớp quản lý ra bên ngoài | View, copy, unmodifiable | Biết thao tác nào của bên gọi có thể ảnh hưởng nguồn |
| Viết lại phép thống kê bằng Stream | Lambda, Stream, collector | Kết quả và quy tắc dữ liệu giữ nguyên |
| Nhiều tác vụ cùng cập nhật bộ đếm | Đồng thời | Chọn được thao tác nguyên tử và giải thích cách duyệt |

Với mỗi bài, nên tự kiểm tra ít nhất các đầu vào: rỗng, một phần tử, có phần tử lặp, không tìm thấy dữ liệu và có nhiều phần tử bằng nhau theo tiêu chí nghiệp vụ.

Chỉ kiểm tra `null` khi bài toán hoặc API cho phép nó. Không mặc nhiên đưa `null` vào mọi cấu trúc rồi mong một hành vi chung.

## 9. Câu hỏi tự đánh giá

1. Vì sao `Map` thuộc framework nhưng không thể truyền trực tiếp vào tham số `Collection`?
2. Một `List` có thứ tự có đồng nghĩa các giá trị được sắp tăng dần không?
3. Yêu cầu nào khiến `LinkedHashSet` phù hợp hơn `HashSet`?
4. Hai đối tượng khác tham chiếu có thể bị `HashSet` coi là trùng không? Điều kiện nào quyết định?
5. Vì sao bộ so sánh chỉ theo tên có thể làm mất một sinh viên trong `TreeSet`?
6. Khi nào một lần `put` vào map thay dữ liệu thay vì thêm một khóa mới?
7. Vì sao không thể dùng thứ tự in trực tiếp của `PriorityQueue` để chứng minh thứ tự ưu tiên?
8. `List.copyOf` và `Collections.unmodifiableList` khác nhau thế nào khi danh sách nguồn được sửa?
9. Sao chép `ArrayList` chứa đối tượng có tạo bản sao của từng đối tượng không?
10. Vì sao sửa collection trong lúc duyệt có thể lỗi dù chỉ có một luồng?
11. Vì sao phải hiểu chi phí tìm vị trí trước khi nói thêm hoặc xóa ở danh sách liên kết là nhanh?
12. Một lớp collection an toàn giữa các luồng có bảo đảm nguyên tử cho mọi chuỗi thao tác nghiệp vụ không?

Người học đã sẵn sàng đi sâu từng nhóm khi có thể trả lời bằng quy tắc, ví dụ hoặc một chương trình nhỏ; chỉ nhớ tên phương thức chưa đủ.

## 10. Cách dùng tài liệu để tiếp tục học

Mỗi khi gặp một lớp mới, đọc theo thứ tự:

1. Hợp đồng interface: cấu trúc biểu diễn điều gì?
2. Bảo đảm riêng của lớp: thứ tự, `null`, khả năng sửa, đồng bộ.
3. Hợp đồng phương thức: đầu vào, giá trị trả về, ngoại lệ.
4. Chi phí và điều kiện sử dụng.
5. Ví dụ nhỏ để kiểm chứng điều vừa đọc.

Các trang nên dùng cùng bài học:

- [Collections Framework Overview — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html): bản đồ interface, lớp triển khai và thuật toán.
- [Collection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): nền chung, thao tác tùy chọn, view và khả năng sửa.
- [List — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng của từng kiểu tổ chức dữ liệu.
- [Queue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html): chính sách phần tử đầu và các cặp phương thức báo thất bại.

Với JDK khác, mở tài liệu đúng phiên bản đang dùng. Sơ đồ của một phiên bản không nên được coi là danh sách bất biến của mọi interface hoặc API trong các phiên bản sau.

Lộ trình đạt mục tiêu khi người học có thể đi từ yêu cầu nghiệp vụ đến hợp đồng dữ liệu, chọn cấu trúc phù hợp, viết ví dụ kiểm chứng và giải thích được giới hạn của lựa chọn đó.
