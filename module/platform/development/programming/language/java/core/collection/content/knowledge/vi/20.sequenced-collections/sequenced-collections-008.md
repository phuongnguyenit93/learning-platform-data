# putFirst, putLast và các sequenced view của Map

## 1. Một map có thứ tự cần cả tra cứu lẫn định vị

Giả sử ứng dụng giữ các công việc theo mã. Mỗi mã có một trạng thái hoặc số liệu đi kèm, và giao diện hiển thị chúng theo thứ tự xử lý. Khi ghim một công việc lên đầu, ta muốn thay đổi vị trí **cả ánh xạ khóa–giá trị**, không tách riêng một danh sách khóa rồi cố giữ nó khớp với map.

Từ Java 21, `SequencedMap<K,V>` diễn đạt map có thứ tự gặp ánh xạ xác định. `putFirst(k, v)` và `putLast(k, v)` cho phép thêm/cập nhật ánh xạ đồng thời chỉ định đầu hoặc cuối khi cách triển khai hỗ trợ. Ba view có trình tự cho phép nhìn cùng dữ liệu dưới dạng khóa, giá trị hoặc entry.

Đơn vị có thứ tự của map là **ánh xạ**. Nó khác collection thông thường, nơi đơn vị là một phần tử. `SequencedMap` kế thừa `Map`, không kế thừa `SequencedCollection`. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

Bài này dùng `LinkedHashMap` làm nguồn sửa được để kiểm chứng định vị và view. Ta cũng sẽ xem nguồn sắp xếp, lớp bọc chỉ đọc, giá trị `null` và map theo thứ tự truy cập. Ví dụ chính yêu cầu **Java 21 trở lên**; các API từ Java 21 này không thuộc mục tiêu thư viện chuẩn Java 17.

## 2. putFirst và putLast làm hai việc cùng lúc

Hai chữ ký trọng tâm là:

~~~java
V putFirst(K key, V value);
V putLast(K key, V value);
~~~

Đây là hình dạng chữ ký để đọc hợp đồng, không phải một lớp Java chạy độc lập.

Nếu thao tác hoàn tất bình thường:

- ánh xạ cho khóa `key` có giá trị `value`;
- nó đứng đầu với `putFirst` hoặc đứng cuối với `putLast`;
- giá trị trả về là **giá trị trước đó gắn với khóa**, hoặc `null` nếu trước đó chưa có ánh xạ.

Đó là thao tác tùy chọn. Không suy rằng mọi đối tượng khai báo `SequencedMap` đều hỗ trợ định vị.

### 2.1. Khóa chưa có: thêm một ánh xạ ở biên

Với một `LinkedHashMap` sửa được:

~~~text
ban đầu                        {A=10, B=20, C=30}

putFirst(Z, 0)
giá trị trả về                 null
sau                            {Z=0, A=10, B=20, C=30}

putLast(D, 40)
giá trị trả về                 null
sau                            {Z=0, A=10, B=20, C=30, D=40}
~~~

Kích thước tăng khi thêm khóa chưa có. Giá trị không cần khác các giá trị đã tồn tại; map chỉ yêu cầu tính duy nhất theo khóa của nó.

### 2.2. Khóa đã có: cập nhật giá trị và chuyển vị trí

Bắt đầu lại từ `{A=10, B=20, C=30}`:

~~~text
putFirst(B, 200)                trả 20
map sau                        {B=200, A=10, C=30}

putLast(A, 100)                 trả 10
map sau                        {B=200, C=30, A=100}
~~~

Số ánh xạ vẫn là 3. Không có hai khóa `B` hay hai khóa `A` vì thay đổi vị trí. Các ánh xạ khác giữ quan hệ tương đối khi một ánh xạ được chuyển trong cách dùng này.

Đừng coi `putFirst` là “chỉ ghim lên đầu”. Nó còn thay giá trị theo đối số bạn truyền vào. Nếu vô tình truyền một giá trị cũ đã đọc từ trước, bạn có thể ghi đè trạng thái mới hơn của công việc.

### 2.3. Đã ở biên vẫn có thể được cập nhật giá trị

Nếu map đang là `{B=200, A=10}`, gọi `putFirst("B", 201)` giữ `B` ở đầu nhưng đổi giá trị thành `201`, trả `200`.

Vì vậy, kiểm tra thứ tự không đổi chưa đủ kết luận thao tác không làm gì. Tách rõ ba quan sát: có thêm khóa không, giá trị có đổi không, trình tự có đổi không.

### 2.4. put thông thường khác gì?

Ở `LinkedHashMap` mặc định theo thứ tự chèn, `put` với khóa đang có cập nhật giá trị nhưng giữ vị trí. `putFirst`/`putLast` biểu đạt ý định định vị tường minh. Lớp còn có chế độ access-order với quy tắc khác, được xem riêng ở cuối bài. [Java 21: LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

| Ý định trên map liên kết theo thứ tự chèn | Phương thức |
| --- | --- |
| Thêm nếu thiếu; nếu đã có thì cập nhật và giữ vị trí | `put(k, v)` |
| Thêm hoặc cập nhật, đặt ánh xạ ở đầu | `putFirst(k, v)` |
| Thêm hoặc cập nhật, đặt ánh xạ ở cuối | `putLast(k, v)` |

Không dùng `remove(k)` rồi `put(k, v)` như một thay thế vô điều kiện. Chuỗi đó tạo khoảng giữa hai lệnh khi ánh xạ không tồn tại và không diễn đạt rõ cùng một ý định. Nó cũng không trở thành giao dịch khi có nhiều luồng.

## 3. Giá trị trả về null không chứng minh khóa trước đó vắng mặt

`LinkedHashMap` cho phép giá trị `null` và một khóa `null`. `HashMap`, lớp nền của nó, cũng có chính sách cho phép các giá trị này. Không được suy chính sách ấy cho mọi `SequencedMap`. [Java 21: HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

Ví dụ:

~~~java
map.putLast("pending", null);
Integer previous = map.putFirst("pending", 7);
~~~

Đoạn minh họa Java 21 giả sử `map` là `LinkedHashMap<String,Integer>`. `previous` bằng `null` dù khóa `pending` đã có.

Muốn phân biệt “khóa chưa có” với “khóa đã ánh xạ đến `null`”, có thể kiểm tra `containsKey` trước trong ngữ cảnh bạn giữ quyền truy cập nhất quán. Nhưng `containsKey` rồi `putFirst` là hai lời gọi; nó không cung cấp một giao dịch nguyên tử cho nhiều luồng.

Cũng cần phân biệt:

- `putFirst` trả `null` là nói về **giá trị trước đó**;
- `firstEntry()` trả `null` là nói map **rỗng**;
- một entry tồn tại nhưng `getValue() == null` vẫn là một ánh xạ.

Các cách dùng `null` này xuất hiện ở các tầng khác nhau. Đừng dùng một điều kiện duy nhất để thay cho cả ba ý nghĩa.

## 4. Ba view có trình tự của cùng một map

Giả sử map hiện là:

~~~text
map:        {A=10, B=20, C=20}
khóa:       [A, B, C]
giá trị:    [10, 20, 20]
entry:      [A=10, B=20, C=20]
~~~

Ba phương thức và kiểu trả về:

| Phương thức | Kiểu trả về | Đơn vị phần tử |
| --- | --- | --- |
| `sequencedKeySet()` | `SequencedSet<K>` | Khóa |
| `sequencedValues()` | `SequencedCollection<V>` | Giá trị |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K,V>>` | Cặp khóa–giá trị |

Khóa không trùng; entry của mỗi ánh xạ cũng có tính duy nhất. Giá trị có thể lặp, nên view giá trị là `SequencedCollection` chứ không phải `SequencedSet`.

`SequencedSet` kết hợp hợp đồng set với trình tự; phép bằng của set vẫn dựa trên thành viên, không tự xét vị trí. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

### 4.1. Không phải ba bản sao

Trên `LinkedHashMap`, các view được liên kết với dữ liệu nguồn. Khi map thay đổi, các lần truy vấn view nhìn theo trạng thái mới; khi một thao tác xóa qua view được hỗ trợ, ánh xạ tương ứng trong map cũng bị xóa.

Có thể tạo view một lần:

~~~java
java.util.SequencedSet<String> keys = map.sequencedKeySet();
java.util.SequencedCollection<Integer> values = map.sequencedValues();
java.util.SequencedSet<java.util.Map.Entry<String, Integer>> entries =
        map.sequencedEntrySet();
~~~

Đoạn này giả sử `map` là `SequencedMap<String,Integer>`. Sau `map.putFirst("Z", 0)` trên nguồn phù hợp, không cần gọi lại ba phương thức để có các đối tượng view mới chỉ nhằm nhìn ánh xạ đó.

Nhưng **view đang sống không có nghĩa iterator cũ luôn còn hợp lệ**. Nếu tạo iterator rồi thay trình tự hoặc số ánh xạ, phải tuân quy tắc duyệt của nguồn; không dùng việc view nhìn thấy cập nhật làm lý do tiếp tục iterator cũ tùy ý.

### 4.2. Các view cũ vẫn theo trình tự của map

`keySet()`, `values()` và `entrySet()` trên một `SequencedMap` vẫn phản ánh thứ tự gặp ánh xạ. Khác biệt quan trọng là kiểu trả về cũ không cung cấp trực tiếp bộ API có trình tự.

Vì thế, đây là thay đổi về **khả năng biểu đạt và thao tác qua kiểu**, không phải tuyên bố rằng view cũ của map liên kết trước đó duyệt ngẫu nhiên.

Ví dụ, khi cần khóa cuối, `sequencedKeySet().getLast()` thể hiện ý định trực tiếp hơn việc nhận `Set<K>` rồi tự đi đến cuối.

## 5. Đọc và xóa qua view có tác dụng gì?

### 5.1. Xóa khóa qua view là xóa ánh xạ

Nếu nguồn đang `{A=10, B=20, C=30}`:

~~~text
keys.removeFirst()             trả A
map sau                        {B=20, C=30}
~~~

Nó không chỉ xóa một nhãn trong một danh sách hiển thị. Giá trị `10` cùng ánh xạ của khóa `A` không còn trong map.

Khi cần chỉ ẩn một khóa trên giao diện mà vẫn giữ dữ liệu nguồn, hãy tạo một trình tự hiển thị riêng hoặc kết quả lọc phù hợp. Đừng dùng thao tác xóa của view như thao tác “bỏ khỏi màn hình” nếu nguồn vẫn cần giữ ánh xạ.

### 5.2. Xóa giá trị qua view cũng xóa cả ánh xạ

`values.removeLast()` lấy giá trị của ánh xạ cuối và xóa ánh xạ ấy khỏi map. Với `{A=10, B=20, C=30}`, nó trả `30` và xóa khóa `C`.

Nếu giá trị bị trùng, một lệnh xóa theo giá trị không thể được hiểu là chỉ định rõ khóa. Trong chương trình, view của `LinkedHashMap` có `[5, 20, 20]`; `remove(20)` xóa một ánh xạ phù hợp, không xóa mọi ánh xạ mang `20`. Ví dụ kiểm chứng cách triển khai này chọn lần khớp đầu theo chiều duyệt hiện tại. Nếu nghiệp vụ cần xóa một khóa cụ thể, hãy gọi theo khóa; đừng dựa vào một giá trị trùng để đoán khóa.

Hợp đồng `Collection.remove(Object)` là xóa một phần tử phù hợp nếu có, không phải thao tác xóa tất cả lần xuất hiện. [Java 21: Collection.remove](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

### 5.3. Xóa entry trả cả khóa lẫn giá trị

`entries.removeFirst()` trên view có quyền xóa cho bạn entry của ánh xạ đầu bị lấy bỏ. Đây có thể là lựa chọn rõ hơn xóa một giá trị khi bạn cần biết mã nào đã bị loại.

Tuy vậy, không tự suy rằng mọi entry nhận theo cách này đều là một đối tượng sửa được kết nối vĩnh viễn với map. Vòng đời và quyền `setValue` của entry là câu hỏi riêng, được giải thích ở phần tiếp theo.

### 5.4. Trạng thái rỗng khác API entry biên của map

`SequencedCollection.getFirst()` và `getLast()` báo `NoSuchElementException` khi collection rỗng. Các phương thức lấy bỏ có thêm điều kiện nguồn hỗ trợ xóa. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

Do đó, với map rỗng:

~~~text
map.firstEntry()                    null
map.sequencedKeySet().getFirst()    NoSuchElementException
~~~

Hai lệnh không có cùng quy ước thiếu dữ liệu dù cùng liên quan biên đầu. Hãy chọn theo kiểu kết quả và chính sách lỗi mà hàm của bạn cần.

## 6. Vì sao view không phải lối tắt để thêm hoặc chuyển ánh xạ?

Trên các view của `LinkedHashMap`:

- `keys.addFirst(k)` và `keys.addLast(k)` không được hỗ trợ;
- `values.addFirst(v)` và `values.addLast(v)` không được hỗ trợ;
- `entries.addFirst(entry)` và `entries.addLast(entry)` cũng không được hỗ trợ.

Điều này vẫn áp dụng khi khóa đã có. Không dùng view khóa như một `LinkedHashSet` độc lập rồi mong nó chuyển vị trí ánh xạ.

Khóa đơn lẻ không mang giá trị cần thiết để tạo ánh xạ. Giá trị đơn lẻ không chỉ định khóa. Ngay cả entry có đủ hai phần cũng không làm view trở thành API chèn/định vị tùy ý của map. Nguồn sở hữu quyền thêm hoặc đặt vị trí qua `putFirst`, `putLast` khi chúng được hỗ trợ.

Mã nguồn OpenJDK 21 của `LinkedHashMap` thể hiện trực tiếp các thao tác thêm tại hai đầu của view bị từ chối, trong khi các thao tác xóa biên đi vào việc xóa ánh xạ nguồn. Đây là bằng chứng cho cách triển khai được dùng trong ví dụ. [OpenJDK 21: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java).

Kết quả cần nhớ là **quyền thao tác không suy ra chỉ từ tên kiểu trả về**. `SequencedSet` và `SequencedCollection` có các thao tác tùy chọn; nguồn view quyết định phần nào được hỗ trợ.

## 7. Entry có thể là ảnh chụp hoặc phần tử đang kết nối với map

Một lỗi phổ biến là thấy kiểu `Map.Entry<K,V>` rồi cho rằng gọi `setValue` lúc nào cũng sửa được map.

Cần phân biệt ba cách nhận entry:

| Cách lấy | Điều có thể dựa vào |
| --- | --- |
| `map.firstEntry()`, `lastEntry()`, `pollFirstEntry()`, `pollLastEntry()` | Entry là ảnh chụp ánh xạ tại lúc gọi; không hỗ trợ sửa nguồn bằng `setValue` |
| Entry lấy trong lúc duyệt entry view | Kết nối với nguồn được bảo đảm trong thời gian duyệt; `setValue` có thể sửa giá trị nếu nguồn hỗ trợ |
| `map.sequencedEntrySet().getFirst()` | Giao diện `SequencedMap` không quy định chung việc entry ấy có kết nối/sửa được hay không |

### 7.1. firstEntry không phải tay nắm để sửa ánh xạ

Ví dụ nguồn là `{E=5, D=20}`:

~~~java
java.util.Map.Entry<String, Integer> before = map.firstEntry();
map.putFirst("E", 50);
~~~

Entry `before` vẫn mô tả `E=5`; ánh xạ hiện tại trong map là `E=50`. Gọi `before.setValue(999)` không phải cách cập nhật map và bị từ chối ở entry ảnh chụp này.

Ảnh chụp entry là sao chép cặp tham chiếu khóa/giá trị, không phải tự sao chép sâu mọi trạng thái bên trong đối tượng. Ví dụ dùng chuỗi và số nguyên bất biến để kết quả rõ ràng.

### 7.2. Cập nhật qua entry trong lúc duyệt

Với nguồn hỗ trợ, có thể dùng:

~~~java
for (java.util.Map.Entry<String, Integer> entry
        : map.sequencedEntrySet()) {
    if (entry.getKey().equals("D")) {
        entry.setValue(21);
    }
}
~~~

Đây là đoạn minh họa dành cho `LinkedHashMap` sửa được trong ví dụ một luồng. Nó cập nhật **giá trị** qua entry của lần duyệt, không tự gọi `putFirst` làm đổi trình tự trong vòng lặp ấy.

Hợp đồng `Map.Entry` ràng buộc kết nối với map vào cách lấy entry và thời gian duyệt. Không giữ một entry iterator lâu dài rồi sửa map qua đường khác và coi entry ấy còn là tay nắm hợp lệ. Nếu cần entry độc lập, phải sao chép theo chính sách thích hợp; `Map.Entry.copyOf` không nhận khóa hoặc giá trị `null`. [Java 21: Map.Entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html).

### 7.3. Không tự khái quát từ một lần thử getFirst().setValue()

Một cách triển khai có thể trả entry kết nối khi bạn gọi `sequencedEntrySet().getFirst()`; cách khác có thể trả ảnh chụp hoặc từ chối sửa. Muốn viết mã chỉ dựa trên giao diện chung, không được biến quan sát của một lớp thành bảo đảm cho mọi map.

Nếu ý định là cập nhật một khóa, API map trực tiếp thường rõ hơn. Nếu ý định là duyệt và cập nhật giá trị của từng entry trên nguồn cho phép, dùng hợp đồng của phép duyệt. Chọn đường thao tác dựa trên ý định thay vì thử phương thức nào tình cờ chạy.

## 8. reversed đảo chiều của map và mọi view liên quan

Với nguồn:

~~~text
map gốc:       {A=1, B=2, C=3}
map ngược:     {C=3, B=2, A=1}
khóa ngược:    [C, B, A]
giá trị ngược: [3, 2, 1]
~~~

`map.reversed()` là view theo chiều ngược. Các view khóa, giá trị, entry của map ngược cũng đi theo chiều ấy.

Trên `LinkedHashMap` có quyền định vị:

- `map.reversed().putFirst(k, v)` đặt ánh xạ ở đầu chiều ngược, tương ứng cuối nguồn;
- `map.reversed().putLast(k, v)` đặt ở cuối chiều ngược, tương ứng đầu nguồn.

Ví dụ:

~~~text
nguồn trước                       {A=1, B=2, C=3}
ngược.putFirst(B, 20)
nguồn sau                         {A=1, C=3, B=20}
view ngược sau                    {B=20, C=3, A=1}
~~~

Giá trị cũ trả về vẫn thuộc khóa được cập nhật; đảo chiều không đổi khóa mà lời gọi nhắm đến.

Với `LinkedHashMap`, thay đổi qua map ngược và các view của nó truyền về nguồn, thay đổi nguồn cũng nhìn thấy qua view. Giao diện chung để một số đặc điểm nhìn thấy thay đổi cho cách triển khai, nên hãy phân biệt hợp đồng lớp cụ thể với phần chung của mọi `SequencedMap`.

Nếu chỉ cần xuất báo cáo theo chiều ngược, hãy duyệt view ngược. Không cần chuyển từng ánh xạ trong nguồn để đảo toàn bộ dữ liệu rồi lại đảo trở lại.

## 9. Không phải mọi map có thứ tự đều hỗ trợ putFirst/putLast

### 9.1. SortedMap và TreeMap

`SortedMap` định vị ánh xạ theo phép so sánh khóa. Vì vậy, `putFirst` và `putLast` từ chối định vị tường minh bằng `UnsupportedOperationException`. Điều này vẫn đúng nếu khóa tình cờ đã ở đúng biên. [Java 21: SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html#putFirst(K,V)).

`TreeMap` dùng thứ tự tự nhiên hoặc `Comparator` của khóa, không phải thứ tự giá trị và cũng không tự chuyển sang thứ tự chèn khi được tham chiếu qua `SequencedMap`. [Java 21: TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Muốn thêm/cập nhật trong map sắp xếp, dùng `put` và để nguồn xác định vị trí. Nếu sản phẩm cần ghim tùy ý một mục, phải xem lại mô hình thứ tự; không bắt lỗi rồi giả vờ vị trí đã được cập nhật.

### 9.2. Map không sửa được và các view của nó

`Collections.unmodifiableSequencedMap(source)` trả một view chỉ đọc có cùng khả năng biểu đạt trình tự. Nó chặn sửa qua map và qua các collection view của map ấy. [Java 21: Collections.unmodifiableSequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableSequencedMap(java.util.SequencedMap)).

Việc chặn sửa qua view không làm nguồn trở thành một ảnh chụp bất biến. Nếu nơi khác gọi `source.putLast`, view chỉ đọc có thể nhìn thấy trình tự mới của nguồn theo hợp đồng lớp bọc.

Để giữ dữ liệu riêng về cấu trúc, có thể tạo `new LinkedHashMap<>(source)` trước rồi bọc bản sao. Cách này giữ trình tự duyệt được sao chép vào map liên kết; nó không phải sao chép sâu các đối tượng khóa/giá trị.

Đừng thay bằng `Map.copyOf` chỉ vì tên có chữ “copy” rồi mặc định còn có hợp đồng `SequencedMap` hoặc thứ tự hiển thị theo ý muốn. Chọn công cụ theo cả quyền sửa và yêu cầu thứ tự.

## 10. Chương trình đầy đủ

Lưu mã dưới vào **`SequencedMapViewsDemo.java`**. Các view được lấy trước nhiều lần cập nhật để chứng minh chúng không phải bản sao. Chương trình dùng nguồn một luồng; không giữ iterator qua các thao tác định vị.

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedMap;
import java.util.SequencedSet;
import java.util.TreeMap;

public class SequencedMapViewsDemo {
    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NoSuchElementException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 10);
        map.put("B", 20);
        map.put("C", 20);
        SequencedSet<String> keys = map.sequencedKeySet();
        SequencedCollection<Integer> values = map.sequencedValues();
        SequencedSet<Map.Entry<String, Integer>> entries = map.sequencedEntrySet();

        Integer previous = map.putFirst("B", 200);
        System.out.println("putFirst existing: previous=" + previous + ", map=" + map);
        previous = map.putLast("A", 100);
        System.out.println("putLast existing: previous=" + previous + ", map=" + map);
        previous = map.putFirst("Z", 0);
        System.out.println("putFirst new: previous=" + previous + ", map=" + map);
        System.out.println("live keys: " + keys);
        System.out.println("live values: " + values);
        System.out.println("live entries: " + entries);

        System.out.println("key view removeFirst: " + keys.removeFirst());
        System.out.println("after key removal: " + map);
        System.out.println("value view removeLast: " + values.removeLast());
        System.out.println("after value removal: " + map);
        System.out.println("entry view removeFirst: " + entries.removeFirst());
        System.out.println("after entry removal: " + map);

        map.putLast("D", 20);
        map.putFirst("E", 5);
        System.out.println("duplicate values: " + values);
        boolean removed = values.remove(Integer.valueOf(20));
        System.out.println("remove one matching value: " + removed + ", map=" + map);
        System.out.println("same key view now: " + keys);

        Map.Entry<String, Integer> snapshot = map.firstEntry();
        map.putFirst("E", 50);
        System.out.println("snapshot and current: " + snapshot + " / " + map.firstEntry());
        System.out.println("snapshot setValue: " + failure(() -> snapshot.setValue(999)));
        for (Map.Entry<String, Integer> entry : entries) {
            if (entry.getKey().equals("D")) {
                entry.setValue(21);
            }
        }
        System.out.println("iterator entry update: " + map);

        SequencedMap<String, Integer> backwards = map.reversed();
        previous = backwards.putFirst("E", 500);
        System.out.println("reverse putFirst: previous=" + previous + ", base=" + map);
        System.out.println("reverse map: " + backwards);
        backwards.putLast("X", 9);
        System.out.println("reverse putLast new, base: " + map);
        System.out.println("reverse keys: " + backwards.sequencedKeySet());

        System.out.println("key addFirst: " + failure(() -> keys.addFirst("D")));
        System.out.println("value addLast: " + failure(() -> values.addLast(30)));
        System.out.println("entry addFirst: "
                + failure(() -> entries.addFirst(Map.entry("Y", 1))));

        SequencedMap<String, Integer> empty = new LinkedHashMap<>();
        System.out.println("empty map firstEntry: " + empty.firstEntry());
        System.out.println("empty key view getFirst: "
                + failure(() -> empty.sequencedKeySet().getFirst()));

        SequencedMap<String, Integer> nullable = new LinkedHashMap<>();
        nullable.putLast("nullValue", null);
        boolean existed = nullable.containsKey("nullValue");
        previous = nullable.putFirst("nullValue", 7);
        System.out.println("previous null: existed=" + existed + ", previous=" + previous);
        nullable.putLast(null, 9);
        System.out.println("null key: " + nullable);

        SequencedMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(2, "two");
        sorted.put(1, "one");
        System.out.println("sorted putFirst existing: "
                + failure(() -> sorted.putFirst(1, "ONE")));
        System.out.println("sorted remains: " + sorted);

        SequencedMap<String, Integer> readOnly =
                Collections.unmodifiableSequencedMap(map);
        LinkedHashMap<String, Integer> saved = new LinkedHashMap<>(map);
        System.out.println("read-only putFirst: "
                + failure(() -> readOnly.putFirst("D", 2)));
        System.out.println("read-only view removeFirst: "
                + failure(() -> readOnly.sequencedValues().removeFirst()));
        map.putLast("F", 6);
        System.out.println("read-only sees source keys: " + readOnly.sequencedKeySet());
        System.out.println("saved copy keys: " + saved.sequencedKeySet());
        System.out.println("map equals reverse: " + map.equals(map.reversed()));

        LinkedHashMap<String, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);
        access.put("A", 1);
        access.put("B", 2);
        access.put("C", 3);
        access.get("A");
        System.out.println("access after get A: " + access.sequencedKeySet());
        access.putFirst("C", 30);
        System.out.println("access explicit first C: " + access.sequencedKeySet());
        System.out.println("access firstEntry: " + access.firstEntry());
        System.out.println("access after firstEntry: " + access.sequencedKeySet());
        access.get("C");
        System.out.println("access after get C: " + access.sequencedKeySet());
    }
}
~~~

Biên dịch bằng JDK 21 trở lên và chạy trên Java 21 trở lên:

~~~shell
javac --release 21 -encoding UTF-8 SequencedMapViewsDemo.java
java SequencedMapViewsDemo
~~~

Không cần `--enable-preview`. Ví dụ đã được biên dịch với mức release 21 và chạy thành công bằng OpenJDK 24.0.2.

Stdout chính xác:

~~~text
putFirst existing: previous=20, map={B=200, A=10, C=20}
putLast existing: previous=10, map={B=200, C=20, A=100}
putFirst new: previous=null, map={Z=0, B=200, C=20, A=100}
live keys: [Z, B, C, A]
live values: [0, 200, 20, 100]
live entries: [Z=0, B=200, C=20, A=100]
key view removeFirst: Z
after key removal: {B=200, C=20, A=100}
value view removeLast: 100
after value removal: {B=200, C=20}
entry view removeFirst: B=200
after entry removal: {C=20}
duplicate values: [5, 20, 20]
remove one matching value: true, map={E=5, D=20}
same key view now: [E, D]
snapshot and current: E=5 / E=50
snapshot setValue: UnsupportedOperationException
iterator entry update: {E=50, D=21}
reverse putFirst: previous=50, base={D=21, E=500}
reverse map: {E=500, D=21}
reverse putLast new, base: {X=9, D=21, E=500}
reverse keys: [E, D, X]
key addFirst: UnsupportedOperationException
value addLast: UnsupportedOperationException
entry addFirst: UnsupportedOperationException
empty map firstEntry: null
empty key view getFirst: NoSuchElementException
previous null: existed=true, previous=null
null key: {nullValue=7, null=9}
sorted putFirst existing: UnsupportedOperationException
sorted remains: {1=one, 2=two}
read-only putFirst: UnsupportedOperationException
read-only view removeFirst: UnsupportedOperationException
read-only sees source keys: [X, D, E, F]
saved copy keys: [X, D, E]
map equals reverse: true
access after get A: [B, C, A]
access explicit first C: [C, B, A]
access firstEntry: C=30
access after firstEntry: [C, B, A]
access after get C: [B, A, C]
~~~

### 10.1. Cập nhật và định vị

Ba dòng đầu phân biệt hai khóa đã có với một khóa mới. Giá trị trước đó của `B` và `A` được trả về; `Z` được thêm mới với kết quả `null`.

Ba view đã tạo trước đó đều phản ánh map sau cập nhật. Chúng đọc cùng trình tự ánh xạ, nhưng chiếu ra loại phần tử khác nhau.

### 10.2. Xóa qua view và giá trị lặp

Xóa khóa đầu lấy `Z` khỏi map; xóa giá trị cuối lấy ánh xạ của `A`; xóa entry đầu tiếp tục lấy ánh xạ của `B`. Các thay đổi không bị giới hạn trong “bản danh sách” của từng view.

Sau khi thêm `E` và `D`, giá trị `20` lặp hai lần. Lần `remove(20)` trên view giá trị của nguồn này chỉ xóa một ánh xạ khớp; dòng map sau đó cho biết khóa `C` đã mất, `D` vẫn còn.

### 10.3. Entry ảnh chụp và entry iterator

`snapshot` giữ `E=5` sau khi map đã cập nhật `E=50` và từ chối `setValue`. Vòng lặp entry sau đó thay `D` thành `21` trực tiếp qua entry được lấy trong lúc duyệt trên nguồn hỗ trợ.

Không lấy kết quả của hai cách này để suy rằng mọi `Map.Entry` đều có cùng quyền sửa.

### 10.4. Chiều ngược, nguồn bị hạn chế và bản sao

`backwards.putFirst("E", 500)` đẩy `E` về cuối nguồn. `backwards.putLast("X", 9)` đưa khóa mới về đầu nguồn.

Các thao tác thêm vào view bị từ chối. Map sắp xếp cũng từ chối định vị. Lớp bọc chỉ đọc chặn cả `putFirst` và xóa qua view giá trị; nhưng nhìn thấy khóa `F` được thêm qua nguồn. Bản `saved` giữ cấu trúc trước lần thêm ấy.

## 11. Cẩn thận với access-order của LinkedHashMap

`LinkedHashMap` mặc định theo thứ tự chèn. Constructor có đối số cuối `true` tạo chế độ thứ tự truy cập (access-order): các thao tác truy cập được lớp quy định có thể đưa ánh xạ về cuối nguồn.

Ví dụ ở cuối chương trình:

~~~text
ban đầu sau các lệnh put          [A, B, C]
get(A)                           [B, C, A]
putFirst(C, 30)                  [C, B, A]
firstEntry()                     vẫn [C, B, A]
get(C)                           [B, A, C]
~~~

`putFirst` là định vị tường minh, không được hiểu như một lần truy cập thông thường tự đẩy mục về cuối. Nhưng một lệnh `get` tiếp theo vẫn có thể đổi vị trí theo chính sách access-order.

Vì vậy, quy trình “đưa C lên đầu, rồi đọc lại giá trị bằng get(C) để in” có thể vừa kiểm tra vừa làm C rời đầu. Khi chỉ cần hiển thị các ánh xạ của nguồn access-order, hãy cân nhắc duyệt entry thay vì duyệt khóa rồi gọi `get` cho từng khóa.

Đây cũng là lý do không định nghĩa đầu/cuối đơn giản bằng thời điểm chèn cho mọi `LinkedHashMap`. Phải biết chế độ tạo map và những sự kiện làm đổi trình tự.

## 12. Chọn cách áp dụng và kiểm thử

### 12.1. Cần cả khóa và giá trị: ưu tiên duyệt entry

Một báo cáo cần cặp khóa–giá trị nên đọc trực tiếp entry:

~~~java
for (var entry : report.reversed().sequencedEntrySet()) {
    System.out.println(entry.getKey() + " = " + entry.getValue());
}
~~~

Đây là đoạn minh họa Java 21, giả sử `report` là nguồn phù hợp và không bị thay đổi đồng thời trong thời gian duyệt. Nó thể hiện rõ chiều xuất báo cáo và không cần một lần tra cứu phụ cho mỗi khóa.

### 12.2. Chỉ chuyển vị trí mà giữ giá trị cần một hợp đồng riêng

`putFirst` bắt buộc bạn truyền giá trị. Nếu muốn “chỉ chuyển khóa đang có và giữ nguyên giá trị hiện tại”, hãy thiết kế helper với chính sách rõ về khóa thiếu, giá trị `null` và thay đổi đồng thời.

Với nguồn access-order, `get` tự nó còn có thể đổi trình tự trước thao tác định vị. Với nguồn nhiều luồng, một lần đọc rồi ghi giá trị cũ có thể ghi đè cập nhật khác. Không quảng bá helper đọc–ghi đơn giản như một thao tác chuyển vị trí nguyên tử.

### 12.3. Kiểm thử cả nội dung lẫn trình tự

`Map.equals` xét cùng các ánh xạ, không xét thứ tự duyệt. Một map và map ngược của nó có thể bằng nhau. [Java 21: Map.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

Vì vậy, kiểm thử định vị nên có ít nhất hai quan sát độc lập:

- ánh xạ cho từng khóa đúng giá trị;
- danh sách khóa hoặc entry theo chiều cần dùng đúng trình tự.

Đừng dùng việc map `equals` với kết quả mong đợi làm bằng chứng duy nhất rằng `putFirst` đã đặt đúng vị trí. Cũng không dùng `size` để phát hiện mọi thay đổi: cập nhật và chuyển khóa đã có thường giữ nguyên số ánh xạ.

### 12.4. Đồng thời, iterator và hiệu năng

Map liên kết không tự đồng bộ. Cập nhật giá trị, định vị và xóa qua view phải tuân chính sách truy cập của nguồn. Tránh giữ iterator rồi gọi thao tác có thể đổi trình tự qua đường khác.

Nếu cần một thao tác nhiều bước như kiểm tra quyền ghim, đọc giá trị, chuyển vị trí và ghi lịch sử thành một đơn vị nhất quán, phải có cơ chế bao trùm cả chuỗi. Fail-fast chỉ giúp phát hiện một số lỗi; nó không thay thế khóa hay giao dịch.

Hiệu năng đến từ cách triển khai băm/liên kết hoặc cây, không đến từ tên `SequencedMap`. Dùng giao diện chung giúp biểu đạt hợp đồng; nó không hứa mọi thao tác trên mọi nguồn có cùng độ phức tạp.

## 13. Các lỗi dễ gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `putFirst` chỉ đổi thứ tự | Vô tình ghi đè giá trị | Nhận diện cả cập nhật lẫn định vị |
| Thấy giá trị cũ `null` và kết luận khóa mới | Sai khi khóa đã có giá trị `null` | Phân biệt hiện diện theo hợp đồng nguồn |
| Xóa trên view để chỉ ẩn dòng | Ánh xạ nguồn bị xóa | Tạo dữ liệu hiển thị riêng nếu cần |
| Thêm hoặc chuyển khóa qua view | `UnsupportedOperationException` | Dùng API map hỗ trợ thao tác ấy |
| Coi mọi entry sửa được | Gặp lỗi hoặc phụ thuộc triển khai | Phân biệt ảnh chụp, iterator và cách lấy khác |
| Coi view ngược là bản sao | Sửa làm đổi nguồn ở đầu đối diện | Chọn view hay bản sao theo quyền sở hữu |
| Dùng `TreeMap.putFirst` khi khóa đúng là nhỏ nhất | Vẫn bị từ chối | Dùng `put` theo quy tắc so sánh |
| Duyệt khóa rồi `get` trên access-order | Thứ tự có thể đổi trong lúc duyệt | Duyệt entry hoặc thiết kế ảnh chụp phù hợp |
| Chỉ dùng `Map.equals` để kiểm thử ghim | Bỏ sót lỗi thứ tự | So sánh trình tự riêng |
| Coi lớp bọc chỉ đọc là ảnh chụp cố định | Không dự đoán được thay đổi qua nguồn | Xác định vòng đời và cách sao chép |

## 14. Thực hành có đáp án

### Bài 1 — Cập nhật hai biên

Một `LinkedHashMap` theo thứ tự chèn có `{A=1, B=2, C=3}`. Gọi `putFirst("B", 20)` rồi `putLast("A", 10)`. Hai giá trị trả về và map cuối là gì?

**Đáp án:** trả `2` rồi `1`. Map cuối `{B=20, C=3, A=10}`, kích thước vẫn 3. Mỗi lời gọi cập nhật giá trị đồng thời đặt vị trí của ánh xạ.

### Bài 2 — null trước đó

Map có khóa `K` ánh xạ đến `null`. `putLast("K", 9)` trả `null`. Có thể kết luận đây là lần thêm khóa mới không?

**Đáp án:** không. Kết quả là giá trị cũ, có thể là `null` của một ánh xạ đã tồn tại. Nếu cần phân biệt, kiểm tra hiện diện theo một quy trình truy cập nhất quán; không coi `containsKey` rồi cập nhật là một giao dịch tự động trong nhiều luồng.

### Bài 3 — Xóa giá trị cuối

Map là `{P=5, Q=5, R=8}`. `sequencedValues().removeLast()` trên view sửa được trả gì và tác động nguồn ra sao?

**Đáp án:** trả `8` và xóa cả ánh xạ của `R`, nguồn còn `{P=5, Q=5}`. Nó không chỉ sửa một collection giá trị tách rời map. Nếu cần biết cả khóa bị lấy bỏ, xem API entry biên phù hợp.

### Bài 4 — View khóa có đủ quyền không?

Một biến `SequencedSet<String> keys = map.sequencedKeySet()` của `LinkedHashMap`. Vì sao `keys.addFirst("Q")` không phải cách ghim khóa đang có lên đầu?

**Đáp án:** view không hỗ trợ thao tác thêm/định vị này, kể cả với khóa đã có. Phải thao tác trên map qua API có hợp đồng thích hợp và quản lý giá trị đi kèm. Kiểu `SequencedSet` không đồng nghĩa mọi thao tác sửa tùy chọn đều được hỗ trợ.

### Bài 5 — Hai cách lấy entry

`before = map.firstEntry()` khi đầu là `A=1`. Sau đó map đổi `A` thành `10`. Có nên gọi `before.setValue(100)` để sửa tiếp map không?

**Đáp án:** không. Entry đó là ảnh chụp không cho cập nhật nguồn bằng `setValue`. Nó vẫn mô tả giá trị tại lúc lấy. Nếu muốn cập nhật ánh xạ, dùng API map phù hợp; nếu dùng entry trong lúc duyệt, phải tuân quyền và vòng đời của entry iterator trên nguồn hỗ trợ.

### Bài 6 — Định vị qua chiều ngược

Nguồn `{A=1, B=2, C=3}`. Gọi `map.reversed().putLast("B", 200)` trên map liên kết sửa được. Nguồn và view ngược sau là gì?

**Đáp án:** cuối chiều ngược là đầu nguồn, nên nguồn trở thành `{B=200, A=1, C=3}`; view ngược là `{C=3, A=1, B=200}`. Giá trị cũ trả về là `2`.

### Bài 7 — Map theo truy cập

Một map access-order có khóa theo trình tự `[A, B, C]`. Gọi `putFirst("B", 20)` rồi `get("B")`. Có thể hứa `B` vẫn ở đầu sau đoạn này không?

**Đáp án:** không. Lệnh định vị cho `[B, A, C]`, nhưng `get` tiếp theo tạo truy cập làm `B` về cuối nguồn, thành `[A, C, B]`. Khi kiểm tra hoặc xuất dữ liệu, phải biết các lệnh đọc nào cũng tác động thứ tự.

### Bài 8 — Chỉ đọc, sao chép và kiểm thử thứ tự

API trả `Collections.unmodifiableSequencedMap(source)`. Sau đó nguồn thêm một khóa ở đầu. Kết quả trả về có chắc giữ nguyên không, và kiểm thử `equals` có đủ kiểm tra thứ tự không?

**Đáp án:** lớp bọc là view, không tự tạo ảnh chụp độc lập. Muốn giữ cấu trúc tại một thời điểm, tạo bản sao giữ chính sách thứ tự rồi bọc nếu phù hợp; vẫn phải xác định mức sao chép sâu khi khóa/giá trị có thể sửa. `Map.equals` không xét thứ tự, nên cần kiểm tra trình tự khóa/entry riêng.

Khi tự mở rộng chương trình, hãy thử một khóa mới, một khóa đã ở đúng biên, hai ánh xạ có cùng giá trị và một nguồn rỗng. Với mỗi lời gọi, ghi ba điều: giá trị trả về, nội dung ánh xạ và trình tự duyệt. Cách kiểm chứng này giúp phân biệt rõ định vị, cập nhật và tác dụng của view.
