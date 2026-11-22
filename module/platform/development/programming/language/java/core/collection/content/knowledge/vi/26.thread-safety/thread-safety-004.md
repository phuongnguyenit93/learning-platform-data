# Khóa đúng đối tượng khi duyệt các wrapper đồng bộ

## 1. Một wrapper đồng bộ không giữ khóa thay cho cả vòng lặp

Các phương thức như `Collections.synchronizedList`, `synchronizedSet` và `synchronizedMap` tạo lớp bọc có cơ chế đồng bộ cho các thao tác được hỗ trợ. Nhưng một lượt duyệt qua Iterator, Spliterator hoặc Stream gồm nhiều bước và có thể kéo dài hơn một lời gọi phương thức.

Vì vậy, câu hỏi cần trả lời là:

> Toàn bộ lượt duyệt phải giữ monitor của đối tượng nào để phối hợp với những nơi đang sửa dữ liệu?

Đáp án không luôn là “đối tượng đang được for-each duyệt”. Khi duyệt `map.keySet()`, phải khóa Map bọc. Khi duyệt một vùng con như `headSet` hoặc `subMap` từ wrapper gốc, vẫn phải dùng khóa gốc được hợp đồng chỉ định.

Tài liệu các wrapper đồng bộ yêu cầu khóa thủ công đúng đối tượng khi duyệt và truy cập dữ liệu nền qua lớp bọc. [Java SE 17 — Collections synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedCollection(java.util.Collection)).

Mô hình của bài:

~~~text
nhiều đường nhìn dữ liệu
        |
        v
một nguồn nền và một giao thức khóa chung
        |
        v
giữ đúng khóa trong toàn bộ thời gian duyệt
~~~

Bài sẽ đi từ List/Set đơn giản tới Map và các vùng con, rồi chỉ ra các trường hợp khóa nhầm: khóa Iterator, khóa khung nhìn, khóa dữ liệu nền, tạo hai wrapper độc lập hoặc khóa một lớp bọc chỉ đọc bên ngoài.

## 2. Monitor thuộc về đối tượng, không thuộc về tên biến hay equals

`synchronized (object)` lấy monitor gắn với chính đối tượng mà biểu thức đó tham chiếu. Hai đối tượng khác nhau có monitor khác nhau, dù:

- Chúng có cùng lớp triển khai.
- Chúng biểu diễn nội dung bằng nhau theo equals.
- Chúng dùng chung một collection nền.
- Một đối tượng là khung nhìn được tạo từ đối tượng kia.

Java cho phép cùng một luồng lấy lại monitor nó đang giữ; đây là khả năng tái nhập. Điều này giúp mã giữ khóa wrapper gọi những phương thức wrapper dùng cùng monitor mà không tự chặn chính nó. [Java Language Specification 17 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1).

Nhưng khóa một đối tượng con không có nghĩa tự động khóa đối tượng cha:

~~~text
synchronized(view)
    chỉ giữ monitor của view

synchronized(root)
    chỉ giữ monitor của root
~~~

Một phương thức của `view` có thể chủ động dùng khóa gốc bên trong cách cài đặt. Điều đó không làm monitor của chính `view` trở thành cùng monitor với gốc, và không khiến một khối synchronized(view) giữ khóa gốc xuyên suốt vòng duyệt.

Đây là khác biệt giữa **đối tượng được gọi phương thức** và **đối tượng làm khóa cho giao thức truy cập**.

## 3. Bảng chọn khóa cho những trường hợp thường gặp

Giả định các wrapper gốc được tạo bằng các factory công khai tương ứng của `Collections`:

| Đang duyệt | Đối tượng cần khóa để phối hợp với wrapper |
| --- | --- |
| Một synchronizedCollection gốc | Collection bọc được factory trả về |
| Một synchronizedList hoặc synchronizedSet gốc | List/Set bọc gốc |
| subList lấy từ synchronizedList | List bọc gốc chia sẻ khóa, không chỉ subList |
| keySet, values, entrySet của synchronizedMap | Map bọc gốc |
| subSet, headSet, tailSet của synchronizedSortedSet | SortedSet bọc gốc |
| Vùng con hoặc khung nhìn của synchronizedSortedMap | SortedMap bọc gốc |
| Khung nhìn điều hướng của wrapper navigable tương ứng | Wrapper gốc theo hợp đồng của nó |

“Gốc” ở đây là đối tượng sở hữu giao thức khóa cho nhóm khung nhìn đang dùng, không phải lúc nào cũng là collection thô được đưa vào factory.

Ví dụ:

~~~java
List<String> list = Collections.synchronizedList(new ArrayList<>());
~~~

Khóa công khai cần dùng cho lượt duyệt là `list`. Không cần và không nên tìm một ArrayList bên trong để khóa thay.

Nếu API chỉ đưa cho ta một khung nhìn mà không cung cấp thông tin về giao thức khóa, không thể tự suy ra khóa gốc bằng cách nhìn kiểu giao diện `Collection`. Thiết kế API cần giữ quyền duyệt ở nơi biết gốc, hoặc công bố snapshot hay một thao tác quản lý việc duyệt.

## 4. List và Set: tạo bộ duyệt và dùng nó trong cùng vùng khóa

Ví dụ với List:

~~~java
List<String> list = Collections.synchronizedList(
        new ArrayList<>(List.of("A", "B", "C")));

synchronized (list) {
    Iterator<String> iterator = list.iterator();
    while (iterator.hasNext()) {
        consume(iterator.next());
    }
}
~~~

Đây là đoạn minh họa bên trong một phương thức, với `consume` do ứng dụng định nghĩa. Phần chương trình đầy đủ phía sau không phụ thuộc hàm còn thiếu và có lệnh chạy cụ thể.

Hai điểm đều quan trọng:

1. Tạo Iterator bên trong vùng khóa.
2. Giữ khóa cho tới khi hoàn tất việc dùng Iterator.

Tài liệu synchronizedList chỉ rõ yêu cầu này cho Iterator, Spliterator và Stream. [Java SE 17 — Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

### 4.1. Chỉ khóa lúc tạo Iterator là chưa đủ

Mẫu sau sai giao thức:

~~~java
Iterator<String> iterator;
synchronized (list) {
    iterator = list.iterator();
}

// Sai nếu nguồn có thể bị các bên khác sửa trong lúc duyệt.
while (iterator.hasNext()) {
    consume(iterator.next());
}
~~~

Ra khỏi khối, các luồng khác có thể lấy cùng khóa để sửa nguồn. Iterator không tự giữ monitor của List trong suốt thời gian tồn tại của nó.

### 4.2. Khóa từng bước riêng không giữ được một lượt duyệt nhất quán

Nếu mỗi lần hasNext/next được đặt trong một khối khóa tách rời, vẫn có khoảng trống cho nguồn đổi giữa các bước hoặc giữa các phần tử. Với Iterator thường của collection nền, điều đó không đáp ứng mẫu bảo vệ toàn bộ lượt duyệt mà wrapper yêu cầu.

Hãy xác định ranh giới công việc: nếu nhiệm vụ cần một lượt nhìn ổn định, khóa cả lượt hoặc tạo một snapshot phù hợp.

### 4.3. foreach vẫn là duyệt

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

Cú pháp gọn hơn không thay đổi đối tượng khóa. Nếu `for` dùng một khung nhìn con, phải xem khóa của khung nhìn ấy thay vì máy móc khóa chính biến đang đứng sau dấu hai chấm.

Set bọc đồng bộ gốc được xử lý tương tự, chỉ khác hợp đồng phần tử và thứ tự của Set nền. Khóa đúng không làm HashSet có thứ tự hoặc tự sắp xếp dữ liệu.

## 5. Map: khóa Map bọc, không khóa keySet, values hoặc entrySet

Xét:

~~~java
Map<String, Integer> map =
        Collections.synchronizedMap(new LinkedHashMap<>());

Set<String> keys = map.keySet();
~~~

Khung nhìn `keys` không phải một bản sao độc lập. Nó dùng chung Map nền. Khi duyệt, khóa đúng là `map`:

~~~java
synchronized (map) {
    for (String key : keys) {
        consume(key);
    }
}
~~~

Không thay thành `synchronized (keys)` rồi cho rằng các lời gọi `map.put` từ luồng khác sẽ bị chặn bởi khóa đó. Chúng sử dụng giao thức khóa của Map, không phải monitor riêng của đối tượng keySet.

Tài liệu synchronizedMap yêu cầu khóa trên Map trả về khi duyệt mọi khung nhìn collection của nó, gồm keySet, values và entrySet. [Java SE 17 — Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

### 5.1. Có thể lấy khung nhìn trước, nhưng bộ duyệt phải được dùng dưới khóa đúng

Lấy `map.keySet()` trước khối khóa như ví dụ là cách sử dụng được tài liệu minh họa. Khi bắt đầu Iterator hoặc lượt Stream trên khung nhìn, dùng vùng khóa bảo vệ trọn quá trình tương ứng.

Không đưa một Iterator đang sống ra khỏi khối rồi trả cho bên gọi sử dụng như thể nó đã được “khóa sẵn”.

### 5.2. Entry là phần tử có hợp đồng riêng

Khi duyệt entrySet dưới khóa, có thể đọc khóa và giá trị để tạo dữ liệu đầu ra. Nếu muốn giữ các cặp để xử lý lâu hơn sau khi nhả khóa, nên tạo các entry hoặc đối tượng dữ liệu độc lập trong lúc đang duyệt.

Chỉ chép `new ArrayList<>(map.entrySet())` không tự nhân bản từng entry thành cặp độc lập. Khóa bảo vệ lượt chép không thay đổi hợp đồng thời gian sống và quan hệ của các entry lấy từ khung nhìn.

Chương trình minh chứng tạo chuỗi biểu diễn khóa–giá trị bên trong vùng khóa rồi mới in các chuỗi ấy bên ngoài. Nó không giữ các entry sống từ nguồn để tiếp tục dùng sau khi nguồn có thể đổi.

### 5.3. Khóa khung nhìn có thể tạo ấn tượng sai

Một phương thức đơn lẻ của keySet có thể vẫn đồng bộ đúng bên trong vì khung nhìn chia sẻ khóa gốc với Map. Điều đó không hợp thức hóa việc giữ `synchronized(keys)` quanh Iterator.

Trong OpenJDK 17, các khung nhìn keySet, values và entrySet của wrapper được tạo với cùng mutex của wrapper Map. Đây là cơ chế giải thích vì sao các phương thức dùng chung giao thức, trong khi monitor của chính đối tượng khung nhìn vẫn là một đối tượng khác. [OpenJDK 17 — Collections.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Collections.java).

## 6. Các vùng con tiếp tục dùng khóa gốc

### 6.1. subList của synchronizedList

~~~java
List<String> list = Collections.synchronizedList(
        new ArrayList<>(List.of("A", "B", "C")));
List<String> tail = list.subList(1, 3);

synchronized (list) {
    for (String value : tail) {
        consume(value);
    }
}
~~~

`tail` là một đối tượng khung nhìn khác, nhưng các thao tác của wrapper con chia sẻ khóa với List gốc. Do đó, giữ monitor của `tail` không thay thế giữ monitor của `list` cho lượt duyệt.

Mã nguồn OpenJDK cho thấy subList của synchronizedList truyền tiếp mutex hiện có cho wrapper con; nó không tạo một giao thức độc lập mới cho cùng vùng dữ liệu.

Ngoài vấn đề khóa, subList còn có hợp đồng về thay đổi cấu trúc của List nền. Nếu cấu trúc cha bị đổi bên ngoài khung nhìn theo cách làm subList không còn hợp lệ, chỉ lấy đúng khóa sau đó không làm khung nhìn tự hợp lệ trở lại. Khóa giải quyết truy cập chen ngang, không thay thế quy tắc hợp lệ của cấu trúc.

### 6.2. subSet, headSet và tailSet

Với SortedSet:

~~~java
SortedSet<Integer> sorted = Collections.synchronizedSortedSet(
        new TreeSet<>(List.of(1, 2, 3, 4)));
SortedSet<Integer> head = sorted.headSet(4);

synchronized (sorted) {
    for (Integer value : head) {
        consume(value);
    }
}
~~~

`headSet(4)` ở đây lấy những phần tử nhỏ hơn `4`. Đối tượng khóa là `sorted`, không phải `head`. Tài liệu SortedSet bọc đồng bộ nêu rõ phải khóa tập gốc cả khi duyệt các vùng con. [Java SE 17 — Collections.synchronizedSortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedSortedSet(java.util.SortedSet)).

Với NavigableSet, những khung nhìn điều hướng và vùng có tham số bao gồm/không bao gồm cũng phải tuân thủ khóa gốc theo hợp đồng wrapper tương ứng. Đừng suy ra rằng thêm tham số ranh giới tạo một khóa mới độc lập.

### 6.3. subMap, headMap, tailMap và các khung nhìn tiếp theo

Với SortedMap:

~~~java
SortedMap<String, Integer> root =
        Collections.synchronizedSortedMap(new TreeMap<>());
SortedMap<String, Integer> range = root.subMap("A", "C");

synchronized (root) {
    for (String key : range.keySet()) {
        consume(key);
    }
}
~~~

Cần khóa `root`, không khóa `range` và cũng không khóa `range.keySet()`.

Khung nhìn có thể đi qua nhiều tầng nhưng giao thức không được suy ra chỉ từ tầng ngoài cùng. Tài liệu synchronizedSortedMap và synchronizedNavigableMap chỉ định Map gốc cho việc duyệt các khung nhìn vùng con ấy. [Java SE 17 — Collections.synchronizedSortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedSortedMap(java.util.SortedMap)).

Một cách nhớ chính xác là theo dõi **ai sở hữu khóa chung** ngay từ lúc tạo wrapper, rồi giữ thông tin ấy cùng với những khung nhìn được tạo ra.

## 7. Spliterator và Stream phải sống trong phạm vi bảo vệ phù hợp

### 7.1. Spliterator không giữ khóa của wrapper suốt đời

~~~java
synchronized (list) {
    Spliterator<String> source = list.spliterator();
    source.forEachRemaining(value -> consume(value));
}
~~~

Đây là một lượt duyệt tuần tự dưới khóa List. Không lấy Spliterator ra ngoài khối rồi cho rằng lớp bọc đã biến nó thành một ảnh chụp hoặc bộ duyệt tự khóa toàn bộ.

Sau `trySplit`, các phần chia vẫn đọc nguồn nền. Phân chia không tự tạo nhiều snapshot độc lập với những lần ghi vào nguồn.

### 7.2. Stream lười nên phải chú ý nơi terminal chạy

Mẫu sai về phạm vi:

~~~java
Stream<String> plan;
synchronized (list) {
    plan = list.stream().filter(value -> !value.isBlank());
}

// Lượt duyệt thực sự nằm ngoài khóa.
List<String> result = plan.toList();
~~~

Tạo pipeline trong vùng khóa không có nghĩa việc đọc phần tử đã hoàn tất. Với nguồn có thể được các bên khác sửa, cần bảo vệ cả thời gian thực hiện terminal theo hợp đồng.

Mẫu tuần tự phù hợp:

~~~java
List<String> result;
synchronized (list) {
    result = list.stream()
            .filter(value -> !value.isBlank())
            .toList();
}
~~~

Đoạn này giả định phần tử khác null và kết quả theo hợp đồng của toList phù hợp nhu cầu.

### 7.3. Không dùng khóa ngoài như lời giải tự động cho parallelStream

Một pipeline song song có thể đưa hành động sang các luồng khác. Nếu luồng gọi giữ khóa gốc và đợi các tác vụ hoàn thành, còn tác vụ lại cố lấy chính khóa đó, chương trình có thể không tiến triển.

Ngay cả khi callback không lấy khóa, vẫn cần hiểu chính sách nguồn, phạm vi bảo vệ và chi phí giữ khóa. Khi muốn xử lý song song hoặc làm việc lâu, cách dễ kiểm soát hơn thường là tạo snapshot hợp lệ dưới khóa rồi xử lý snapshot sau khi nhả.

Đây không phải kết luận mọi parallelStream đều bị cấm. Nó là yêu cầu thiết kế quyền sở hữu và thời gian giữ khóa thay vì bọc synchronized rồi bỏ qua hành vi của các tác vụ.

## 8. Những đối tượng khóa thường bị chọn nhầm

### 8.1. Khóa collection nền thay cho wrapper

~~~java
List<String> backing = new ArrayList<>();
List<String> safe = Collections.synchronizedList(backing);
~~~

Các phương thức của wrapper dùng giao thức của `safe`. Chỉ giữ `synchronized(backing)` không buộc một luồng gọi `safe.add` phải chờ khóa ấy.

Cách tránh lỗi là tạo wrapper và giữ nó như điểm truy cập duy nhất. Đừng để nhiều nơi còn sửa trực tiếp backing bên ngoài giao thức. Nếu một thiết kế riêng dùng khóa khác, mọi nơi phải được thiết kế đồng nhất; không trộn nó vô tình với mutex của wrapper chuẩn.

### 8.2. Khóa Iterator

Iterator là một đối tượng duyệt, không phải đối tượng khóa mà các phương thức của wrapper đang dùng. `synchronized(iterator)` không làm những người gọi `list.add` phối hợp với vòng lặp ấy.

Tương tự, khóa Stream hoặc Spliterator chỉ khóa đối tượng đó; nó không tự khóa nguồn.

### 8.3. Hai wrapper riêng trên cùng backing

~~~java
List<String> first = Collections.synchronizedList(backing);
List<String> second = Collections.synchronizedList(backing);
~~~

Hai lời gọi factory độc lập không tự nhận ra cùng backing rồi thống nhất một monitor. Một bên khóa `first` không ngăn bên khác đi qua `second` theo monitor khác.

Nếu hai bên cùng sửa backing theo hai giao thức độc lập, việc cả hai đều có tên “synchronizedList” không cứu được thiết kế.

Trong chương trình, ca này chỉ thử khả năng lấy hai monitor khác nhau; không thực hiện các lượt ghi xung đột lên backing. Nó phục vụ minh chứng danh tính khóa, không phải mẫu dùng hai wrapper để bảo vệ cùng nguồn.

### 8.4. Khóa lớp bọc chỉ đọc bên ngoài

~~~java
List<String> readOnly = Collections.unmodifiableList(safe);
~~~

`readOnly` cấm sửa qua giao diện đó, nhưng monitor của `readOnly` không tự là monitor của `safe`. Giữ synchronized(readOnly) không làm những nơi đang dùng safe tuân theo khóa ấy.

Nếu API chỉ cung cấp readOnly cho người gọi, nên cân nhắc cung cấp snapshot hoặc phương thức đọc được quản lý từ bên sở hữu. Không yêu cầu người gọi đoán xem bên trong có bao nhiêu lớp bọc và khóa nào mới đúng.

## 9. Một API đọc nên giữ quyền khóa ở nơi biết nguồn

Nếu một hàm chỉ nhận `Collection<T> view` rồi viết `synchronized(view)`, nó chưa có đủ căn cứ để bảo đảm đúng cho mọi khung nhìn đồng bộ có thể được truyền vào.

Hai hướng thiết kế rõ hơn:

| Hướng | Trách nhiệm |
| --- | --- |
| Bên sở hữu dữ liệu thực hiện lượt đọc | Nó biết wrapper gốc và giữ khóa đúng |
| Bên sở hữu trả snapshot độc lập | Nó tạo snapshot trong giao thức hợp lệ rồi để bên gọi đọc ngoài khóa |

Có thể truyền thêm một đối tượng khóa đã được thỏa thuận trong một API nội bộ, nhưng điều đó phải là hợp đồng rõ ràng. Truyền một Object bất kỳ không tự tạo quan hệ với các phương thức đang sửa nguồn.

Cũng tránh trả một Iterator sống từ trong một phương thức synchronized:

~~~java
// Minh họa thiết kế không giữ khóa cho thời gian bên gọi sử dụng Iterator.
Iterator<String> iteratorForCaller() {
    synchronized (list) {
        return list.iterator();
    }
}
~~~

Monitor đã nhả khi phương thức trả về. Nếu cần cung cấp dữ liệu để bên gọi duyệt độc lập, trả một bản sao phù hợp thường dễ biểu đạt đúng hơn.

Mục tiêu không phải che giấu khóa đến mức người dùng không biết dữ liệu có nhất quán hay không. Mục tiêu là đặt việc thực hiện giao thức ở nơi có đủ thông tin và giữ phạm vi trách nhiệm rõ ràng.

## 10. Tạo snapshot dưới khóa rồi làm việc ngoài khóa

Với danh sách tên khác null:

~~~java
List<String> snapshot;
synchronized (list) {
    snapshot = List.copyOf(list);
}

process(snapshot);
~~~

`process` là hàm do ứng dụng cung cấp; đoạn này minh họa cách tách thời gian giữ khóa khỏi xử lý có thể lâu. Snapshot không phản ánh việc thêm/xóa vị trí sau đó ở List nguồn.

Nếu nguồn có null hợp lệ, chọn một phép sao chép chấp nhận null và quyền sửa kết quả phù hợp thay vì mặc định dùng List.copyOf. Bản sao cấu trúc cũng không tự nhân bản những đối tượng phần tử sửa được.

Với Map, nếu cần snapshot cặp để dùng sau, tạo các cặp độc lập ngay trong vùng khóa. Nếu dùng SimpleImmutableEntry, tham chiếu khóa/giá trị được giữ trong cặp mới; trạng thái bên trong đối tượng khóa/giá trị vẫn cần chính sách riêng.

Một snapshot chỉ có ý nghĩa khi quá trình tạo nó đã đọc nguồn hợp lệ. Tạo bản sao ngoài khóa từ một wrapper đang có các bên sửa không giải quyết được yêu cầu duyệt ổn định chỉ bằng tên “copy”.

Bên đọc còn cần biết dữ liệu snapshot có thể cũ. Nếu nghiệp vụ phải kiểm tra điều kiện rồi cập nhật dựa trên trạng thái hiện tại, không được thay phần giao dịch ấy bằng snapshot mà bỏ bước xác nhận/cập nhật nguyên tử cần có.

## 11. Khóa đúng chưa thay thế hợp đồng Iterator và chính sách callback

Giữ khóa ngăn các bên tuân thủ cùng khóa chen vào, nhưng chính luồng đang duyệt vẫn có thể làm một thao tác không hợp lệ.

Ví dụ, gọi add trực tiếp lên nguồn trong khi Iterator đang chạy có thể phá hợp đồng của Iterator, dù cùng luồng đang giữ khóa và có thể tái nhập monitor. Tái nhập không biến một sửa đổi cấu trúc tùy ý thành thao tác Iterator hợp lệ.

Nếu cần xóa trong một lượt duyệt được hỗ trợ, dùng đúng thao tác Iterator hoặc một phương thức sửa phù hợp với cấu trúc và yêu cầu. Đừng dùng một lần không gặp ConcurrentModificationException để coi mọi thay đổi đều được chấp nhận.

Callback trong vùng khóa cũng cần được kiểm soát. Một callback làm I/O chậm, giữ một khóa khác hoặc chờ công việc đang cần khóa gốc có thể làm tăng thời gian chặn hoặc tạo deadlock.

Nếu cần nhiều khóa cho nhiều nguồn, có một thứ tự lấy khóa nhất quán trong thiết kế. Không khóa List trước Map ở nơi này rồi khóa Map trước List ở nơi khác mà không xem khả năng chờ vòng.

Đối với `list.forEach(action)` trực tiếp, cách cài đặt wrapper có thể đồng bộ toàn phương thức; đó không phải cùng lời gọi với `list.iterator().forEachRemaining(action)`. Không lấy việc một phương thức tiện ích có khóa nội bộ để suy ra mọi bộ duyệt được lấy ra đều giữ khóa suốt thời gian dùng.

## 12. Kiểm tra monitor bằng Thread.holdsLock

`Thread.holdsLock(object)` cho biết **luồng hiện tại** có giữ monitor của đối tượng đó hay không. Nó không lấy khóa, không chờ khóa và không kiểm tra xem một luồng khác có giữ khóa hay không. [Java SE 17 — Thread.holdsLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)).

Trong ví dụ:

~~~java
synchronized (list) {
    System.out.println(Thread.holdsLock(list)); // true
    System.out.println(Thread.holdsLock(tail)); // false nếu tail là đối tượng khác
}
~~~

Hai kết quả không mâu thuẫn với việc các phương thức tail dùng chung mutex gốc. Lần gọi holdsLock(tail) chỉ hỏi monitor của chính tail.

Phương thức này hữu ích để kiểm tra tiền điều kiện của helper nội bộ hoặc để học danh tính khóa. Nó không tự chứng minh toàn bộ hệ thống an toàn; vẫn phải kiểm tra mọi nơi sửa dữ liệu và thời gian sống của bộ duyệt.

Chương trình còn dùng một luồng thăm dò và latch: trong khi luồng gọi đang giữ monitor của khung nhìn, luồng thăm dò thử lấy monitor gốc. Nếu lấy được và báo qua latch trước khi luồng gọi nhả khung nhìn, điều đó chứng minh hai monitor không loại trừ nhau.

Latch chỉ phối hợp phép thử; nó không tham gia một thuật toán duyệt nguồn sai. [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

## 13. Chương trình minh chứng đầy đủ

Lưu mã sau thành **WrapperTraversalLockDemo.java**. Chương trình dùng API tương thích Java 17, không cần thư viện ngoài.

Các lượt duyệt thực sự đều giữ đúng khóa gốc. Phép thử khóa sai chỉ thăm dò monitor và không duyệt/ghi dữ liệu xung đột qua một khung nhìn không được bảo vệ. Không có yêu cầu tái lập một lỗi ngẫu nhiên từ data race.

Sau khi thêm D vào List gốc, chương trình không tiếp tục dùng subList cũ. Các entry từ Map được chuyển thành chuỗi ngay trong khóa, nên dữ liệu được in sau đó không giữ entry sống của khung nhìn.

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

public class WrapperTraversalLockDemo {
    private static boolean rootLockAvailableWhileViewHeld(Object root, Object view)
            throws InterruptedException {
        CountDownLatch enteredRoot = new CountDownLatch(1);
        Thread probe = new Thread(() -> {
            synchronized (root) {
                enteredRoot.countDown();
            }
        });
        boolean entered;
        synchronized (view) {
            probe.start();
            entered = enteredRoot.await(5, TimeUnit.SECONDS);
        }
        probe.join(5000);
        if (probe.isAlive()) {
            probe.interrupt();
            throw new AssertionError("Probe did not finish");
        }
        return entered;
    }

    public static void main(String[] args) throws Exception {
        List<String> list = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B", "C")));
        List<String> visited = new ArrayList<>();
        synchronized (list) {
            Iterator<String> iterator = list.iterator();
            while (iterator.hasNext()) {
                visited.add(iterator.next());
            }
            System.out.println("list-root-held=" + Thread.holdsLock(list));
        }
        System.out.println("list-values=" + visited);

        List<String> tail = list.subList(1, 3);
        List<String> tailValues = new ArrayList<>();
        synchronized (list) {
            for (String value : tail) {
                tailValues.add(value);
            }
            System.out.println("sublist-root-held=" + Thread.holdsLock(list));
            System.out.println("sublist-view-held=" + Thread.holdsLock(tail));
        }
        System.out.println("sublist-values=" + tailValues);
        synchronized (tail) {
            System.out.println("view-only-root-held=" + Thread.holdsLock(list));
        }
        System.out.println("root-available-under-sublist-lock="
                + rootLockAvailableWhileViewHeld(list, tail));

        String joined;
        synchronized (list) {
            joined = list.stream().collect(Collectors.joining("|"));
        }
        System.out.println("stream-under-root=" + joined);

        Map<String, Integer> map = Collections.synchronizedMap(new LinkedHashMap<>());
        map.put("B", 2);
        map.put("A", 1);
        Set<String> keys = map.keySet();
        Collection<Integer> values = map.values();
        Set<Map.Entry<String, Integer>> entries = map.entrySet();
        List<String> keyValues = new ArrayList<>();
        List<Integer> mappedValues = new ArrayList<>();
        List<String> entryValues = new ArrayList<>();
        synchronized (map) {
            for (String key : keys) {
                keyValues.add(key);
            }
            for (Integer value : values) {
                mappedValues.add(value);
            }
            for (Map.Entry<String, Integer> entry : entries) {
                entryValues.add(entry.getKey() + "=" + entry.getValue());
            }
            System.out.println("map-root-held=" + Thread.holdsLock(map));
            System.out.println("map-key-view-held=" + Thread.holdsLock(keys));
        }
        System.out.println("map-keys=" + keyValues);
        System.out.println("map-values=" + mappedValues);
        System.out.println("map-entries=" + entryValues);
        System.out.println("map-root-available-under-key-lock="
                + rootLockAvailableWhileViewHeld(map, keys));

        SortedSet<Integer> sorted = Collections.synchronizedSortedSet(
                new TreeSet<>(List.of(1, 2, 3, 4)));
        SortedSet<Integer> head = sorted.headSet(4);
        List<Integer> headValues = new ArrayList<>();
        synchronized (sorted) {
            for (Integer value : head) {
                headValues.add(value);
            }
            System.out.println("set-root-held=" + Thread.holdsLock(sorted));
            System.out.println("set-range-held=" + Thread.holdsLock(head));
        }
        System.out.println("set-range-values=" + headValues);

        SortedMap<String, Integer> sortedMap =
                Collections.synchronizedSortedMap(new TreeMap<>());
        sortedMap.put("A", 1);
        sortedMap.put("B", 2);
        sortedMap.put("C", 3);
        SortedMap<String, Integer> range = sortedMap.subMap("A", "C");
        List<String> rangeKeys = new ArrayList<>();
        synchronized (sortedMap) {
            for (String key : range.keySet()) {
                rangeKeys.add(key);
            }
            System.out.println("sorted-map-root-held=" + Thread.holdsLock(sortedMap));
            System.out.println("sorted-map-range-held=" + Thread.holdsLock(range));
        }
        System.out.println("sorted-map-range-keys=" + rangeKeys);

        List<String> snapshot;
        synchronized (list) {
            snapshot = List.copyOf(list);
        }
        list.add("D");
        System.out.println("snapshot=" + snapshot);
        System.out.println("current-list=" + list);

        List<String> sharedBacking = new ArrayList<>(List.of("X"));
        List<String> firstWrapper = Collections.synchronizedList(sharedBacking);
        List<String> secondWrapper = Collections.synchronizedList(sharedBacking);
        System.out.println("independent-wrapper-locks="
                + rootLockAvailableWhileViewHeld(firstWrapper, secondWrapper));

        List<String> readOnly = Collections.unmodifiableList(list);
        System.out.println("outer-read-only-lock-is-different="
                + rootLockAvailableWhileViewHeld(list, readOnly));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 WrapperTraversalLockDemo.java
java WrapperTraversalLockDemo
~~~

Stdout chính xác:

~~~text
list-root-held=true
list-values=[A, B, C]
sublist-root-held=true
sublist-view-held=false
sublist-values=[B, C]
view-only-root-held=false
root-available-under-sublist-lock=true
stream-under-root=A|B|C
map-root-held=true
map-key-view-held=false
map-keys=[B, A]
map-values=[2, 1]
map-entries=[B=2, A=1]
map-root-available-under-key-lock=true
set-root-held=true
set-range-held=false
set-range-values=[1, 2, 3]
sorted-map-root-held=true
sorted-map-range-held=false
sorted-map-range-keys=[A, B]
snapshot=[A, B, C]
current-list=[A, B, C, D]
independent-wrapper-locks=true
outer-read-only-lock-is-different=true
~~~

Mã đã biên dịch bằng `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch xác minh mức ngôn ngữ/API Java 17; JVM chạy được nêu rõ, không phải một lần chạy bằng JVM 17.

Cách đọc kết quả:

- `list-root-held` xác nhận vùng duyệt List giữ monitor gốc.
- `sublist-root-held` và `sublist-view-held` phân biệt gốc với đối tượng subList.
- `view-only-root-held` cho thấy chỉ khóa subList không làm luồng hiện tại giữ khóa gốc.
- Các dòng `root-available` cho thấy một luồng khác có thể lấy gốc khi ta chỉ giữ monitor của khung nhìn.
- Các dữ liệu `map-keys`, `map-values`, `map-entries` được thu trong một vùng khóa Map.
- Các vùng SortedSet và SortedMap được duyệt dưới khóa wrapper gốc, không dưới monitor riêng của vùng.
- `snapshot` không đổi sau khi nguồn thêm D.
- Hai dòng cuối kiểm tra monitor khác nhau của hai wrapper độc lập và một lớp bọc chỉ đọc bên ngoài.

Thứ tự in do luồng main thực hiện. Luồng thăm dò chỉ báo qua latch rồi kết thúc; chương trình không dùng sleep để đoán lịch chạy.

## 14. Thực hành có đáp án

### Bài 1 — List gốc và Iterator

Một helper khóa synchronizedList, tạo Iterator rồi nhả khóa và trả Iterator ra ngoài. Bên gọi có được coi Iterator ấy đã được bảo vệ cho cả lượt duyệt không?

**Đáp án:** Không. Monitor đã được nhả khi helper trả về. Cần giữ đúng khóa suốt thời gian sử dụng bộ duyệt hoặc trả một snapshot để bên gọi duyệt độc lập.

### Bài 2 — Khóa keySet

Map được tạo bằng synchronizedMap. Vì sao synchronized(map.keySet()) không thay thế synchronized(map) cho một vòng lặp trên khóa?

**Đáp án:** Các thao tác của wrapper phối hợp qua mutex gốc của Map. Monitor của đối tượng keySet là đối tượng khác. Khóa keySet không làm những bên gọi map.put phải đợi cùng monitor đó.

### Bài 3 — subList có tên synchronized trong cách cài đặt

subList của synchronizedList vẫn là một wrapper đồng bộ. Vì sao khóa chính subList quanh Iterator chưa đúng?

**Đáp án:** Wrapper con chia sẻ mutex của gốc cho các phương thức, không dùng monitor riêng của nó làm khóa độc lập cho cả lượt duyệt. Phải theo dõi và giữ wrapper gốc sở hữu giao thức khóa chung.

### Bài 4 — Vùng con của SortedMap

Có root là synchronizedSortedMap, range là root.subMap(...) và keys là range.keySet(). Khi duyệt keys, khóa đối tượng nào?

**Đáp án:** Khóa root. Không chọn range hoặc keys chỉ vì chúng gần vòng lặp hơn. Các tầng khung nhìn tiếp tục dùng giao thức gốc theo hợp đồng wrapper.

### Bài 5 — Tạo Stream trong khóa

Pipeline được tạo dưới synchronized(list) nhưng toList chạy sau khi ra ngoài khối. Phần tử có được bảo vệ cho lượt duyệt không?

**Đáp án:** Không chỉ nhờ đoạn tạo pipeline. Stream lười nên terminal là nơi lượt đọc thực sự diễn ra. Giữ khóa phù hợp trong thời gian terminal tuần tự hoặc tạo snapshot hợp lệ rồi xử lý ngoài khóa.

### Bài 6 — Hai wrapper cùng nền

Hai module tự gọi synchronizedList trên cùng một ArrayList rồi mỗi nơi khóa wrapper của mình. Có đủ phối hợp không?

**Đáp án:** Không. Hai wrapper độc lập có monitor độc lập. Cần một điểm truy cập và giao thức khóa chung; không tạo nhiều lớp bọc riêng rồi giả định chúng tự thống nhất khóa.

### Bài 7 — holdsLock có lấy khóa không?

`Thread.holdsLock(root)` trả false. Có nghĩa root đang do một luồng khác giữ không? Lời gọi có bảo vệ mã tiếp theo không?

**Đáp án:** Không cho biết điều đó. Nó chỉ báo luồng hiện tại không giữ monitor root và không thực hiện lấy khóa. Muốn dùng giao thức phải lấy khóa bằng cơ chế phù hợp; holdsLock chỉ là phép quan sát hoặc kiểm tra tiền điều kiện.

### Bài 8 — Giữ khóa nhưng callback tự thêm phần tử

Một vòng Iterator đã giữ đúng khóa wrapper. Callback gọi add trực tiếp lên nguồn trong cùng luồng. Vì sao vẫn có thể không hợp lệ?

**Đáp án:** Khóa ngăn các bên khác chen vào nhưng không thay hợp đồng Iterator. Sửa cấu trúc trực tiếp trong lượt duyệt có thể làm Iterator mất hiệu lực. Tái nhập monitor không làm một thao tác sửa tùy ý trở thành thao tác duyệt hợp lệ.

## 15. Quy tắc làm việc với wrapper đồng bộ

Giữ lại thông tin về đối tượng gốc ngay từ lúc tạo wrapper, để mọi khung nhìn và thao tác đọc–ghi phối hợp theo cùng giao thức. Khi duyệt, khóa đúng gốc trước khi tạo bộ duyệt và giữ nó cho đến khi hoàn tất phạm vi cần bảo vệ.

Nếu không muốn giữ khóa qua xử lý lâu, tạo dữ liệu độc lập trong vùng bảo vệ rồi làm việc ngoài khóa. Đừng để Iterator, Spliterator, Stream chưa được thực hiện hoặc entry sống làm rò rỉ một lượt duyệt ra khỏi phạm vi mà nó cần được bảo vệ.

Quy tắc cốt lõi là: **khóa đối tượng sở hữu giao thức đồng bộ, không chọn khóa theo tên biến hoặc theo khung nhìn đang được duyệt.** Với List/Set gốc đó là wrapper gốc; với các khung nhìn Map và vùng con dùng chung mutex, vẫn theo khóa gốc được hợp đồng chỉ định.
