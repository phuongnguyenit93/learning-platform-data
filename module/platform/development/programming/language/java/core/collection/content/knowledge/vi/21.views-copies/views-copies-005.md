# Sao chép bằng constructor, addAll và putAll

## 1. Trước khi sao chép, cần nói rõ thứ gì phải độc lập

Một hàm nhận danh sách công việc và muốn sắp xếp riêng để dựng báo cáo. Nếu nó chỉ gán `List<Task> report = source;` rồi sửa danh sách, cấu trúc nguồn cũng bị sửa vì hai biến cùng tham chiếu một đối tượng.

Tạo một collection mới giải quyết được việc chia sẻ **cấu trúc chứa**, nhưng không mặc nhiên giải quyết việc chia sẻ **các đối tượng phần tử**. Đây là hai mức độc lập cần phân biệt trước khi chọn cách sao chép.

Ba công cụ thường gặp là:

- constructor nhận nguồn, chẳng hạn `new ArrayList<>(source)` hoặc `new LinkedHashMap<>(source)`;
- `destination.addAll(source)` để thêm các phần tử vào collection đích đã có;
- `destination.putAll(sourceMap)` để đưa các ánh xạ vào map đích đã có.

Bài này giải thích ý nghĩa, kiểu trả về, dữ liệu trùng, khóa đụng nhau, thứ tự, comparator, khả năng sửa và các giới hạn về sao chép sâu/đồng thời. Mọi ví dụ đầy đủ bên dưới tương thích **Java 17 trở lên**.

## 2. Gán tham chiếu, sao chép cấu trúc và sao chép phần tử

### 2.1. Gán không tạo collection mới

~~~java
List<String> alias = source;
~~~

Đây là đoạn minh họa trong phương thức có các biến và import phù hợp. `alias == source` là `true`. Thêm/xóa qua một biến tác động cùng đối tượng mà biến kia đang nhìn.

Không có bước “đợi đến lúc sửa rồi Java tự sao chép”. Các collection Java thông thường không có hành vi tự tách cấu trúc theo kiểu đó.

### 2.2. Constructor tạo cấu trúc chứa mới

~~~java
List<String> copy = new ArrayList<>(source);
~~~

`copy` là một danh sách khác với `source`. Thêm hoặc xóa phần tử khỏi một danh sách không tự thêm hoặc xóa ở danh sách kia.

Constructor `ArrayList(Collection)` tạo danh sách chứa các phần tử nguồn theo thứ tự iterator của nguồn. Lớp đích là danh sách mảng động, cho phép các thao tác danh sách thông thường và `null`. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Tuy nhiên, nếu phần tử là đối tượng thì danh sách mới nhận các tham chiếu đến chúng. Đó là **sao chép nông (shallow copy)**.

### 2.3. Sao chép nông chia sẻ đối tượng phần tử

Mô hình:

~~~text
source ----> danh sách S ----+
                            +----> đối tượng công việc T
copy ------> danh sách C ----+

S và C khác nhau.
Tham chiếu phần tử trong S và C cùng trỏ đến T.
~~~

Nếu đổi trạng thái của `T`, cả hai danh sách đều có thể thấy trạng thái ấy vì cùng trỏ đến nó. Nếu thay một vị trí trong `C` bằng đối tượng khác, bạn thay cấu trúc tham chiếu của `C`; vị trí tương ứng trong `S` không tự bị thay.

Các ví dụ chỉ dùng `String` thường làm người học bỏ sót điều này vì chuỗi không cho sửa nội dung tại chỗ. Chương trình chính dùng một lớp `Note` có trường thay đổi được để kiểm chứng rõ.

### 2.4. Sao chép sâu là trách nhiệm của mô hình dữ liệu

Nếu cần phần tử độc lập, phải tạo phần tử mới theo quy tắc của ứng dụng. Với một đối tượng phẳng chỉ chứa một chuỗi bất biến, tạo `new Note(old.text)` có thể đủ.

Với đối tượng chứa danh sách con, tham chiếu dùng chung hoặc chu trình, cần xác định sao chép đến tầng nào và giữ quan hệ dùng chung ra sao. Constructor collection, `addAll` và `putAll` không tự duyệt toàn bộ đồ thị đối tượng để làm việc ấy.

Không dùng từ “bản sao độc lập” mà bỏ trống câu hỏi độc lập về cấu trúc hay cả trạng thái phần tử.

## 3. Sao chép bằng constructor: lớp đích quyết định hợp đồng

Ví dụ phổ biến:

~~~java
List<E> listCopy = new ArrayList<>(sourceCollection);
Set<E> setCopy = new LinkedHashSet<>(sourceCollection);
Map<K, V> mapCopy = new LinkedHashMap<>(sourceMap);
~~~

Đây là các mẫu với tham số kiểu `E`, `K`, `V` do ngữ cảnh khai báo. Constructor nhận collection hoặc map là quy ước phổ biến của các lớp tổng quát trong JDK; nó không phải một phương thức của chính giao diện `Collection` hay `Map`.

Cần đọc theo ý nghĩa: “tạo **loại đích này** từ dữ liệu nguồn”, không phải “nhân bản nguyên trạng mọi thuộc tính của nguồn”.

### 3.1. Đổi loại collection có thể đổi số phần tử và quy tắc thứ tự

Nguồn danh sách:

~~~text
[B, A, B, C]
~~~

Các lựa chọn đích có ý nghĩa khác nhau:

| Đích | Kết quả theo hợp đồng tương ứng |
| --- | --- |
| `new ArrayList<>(source)` | Giữ các lần xuất hiện và thứ tự duyệt: `[B, A, B, C]` |
| `new LinkedHashSet<>(source)` | Loại trùng theo set, giữ thứ tự chèn đầu tiên: `[B, A, C]` |
| `new TreeSet<>(source)` với chuỗi tự nhiên | Loại trùng và sắp xếp: `[A, B, C]` |

`LinkedHashSet` duy trì thứ tự chèn, và thêm lại phần tử đã có không đổi vị trí của nó. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

Số phần tử giảm khi đổi list thành set không nhất thiết là lỗi sao chép; có thể đó chính là mục tiêu loại trùng. Nhưng nếu dữ liệu lặp biểu thị nhiều lần đặt hàng, đổi thành set sẽ làm mất ý nghĩa. Chọn theo mô hình nghiệp vụ.

### 3.2. Constructor nhận capacity không nhận dữ liệu

Hai lệnh trông gần nhau nhưng khác việc:

~~~java
new ArrayList<String>(10);
new ArrayList<String>(existingItems);
~~~

Lệnh đầu tạo một danh sách rỗng với dung lượng ban đầu dự kiến. `size()` vẫn bằng 0. Nó không tạo mười phần tử `null` và cũng không tạo một bản sao nào.

Lệnh thứ hai nhận collection nguồn để tạo danh sách chứa dữ liệu. Đừng dùng constructor số nguyên rồi gọi `set(0, value)` khi chưa có phần tử ở vị trí 0.

### 3.3. Chính sách sửa của nguồn không tự đi theo bản sao

Một `List.of("A")` không cho thêm/xóa. Nhưng `new ArrayList<>(thatList)` tạo một danh sách mới có quyền sửa theo `ArrayList`.

Tương tự, nguồn map không sửa được có thể được đọc để dựng một `LinkedHashMap` sửa được. Việc này không mở quyền sửa nguồn; nó chỉ tạo một đối tượng mới mang hợp đồng khác.

Ngược lại, constructor collection không tự tạo một bản sao không sửa được. Nếu API cần đầu ra chỉ đọc, phải chọn factory hoặc lớp bọc phù hợp sau khi xác định yêu cầu về `null`, thứ tự và vòng đời.

## 4. addAll: thêm vào đích hiện có, không thay toàn bộ đích

Chữ ký tổng quát:

~~~java
boolean addAll(Collection<? extends E> source);
~~~

Nếu hoàn tất, phương thức đã áp dụng việc thêm các phần tử nguồn theo quy tắc của collection đích. Cờ trả về nói collection đích có thay đổi hay không.

**addAll không tự clear đích trước.** Ví dụ:

~~~text
đích trước              [start]
nguồn                   [B, A, B, C]
đích.addAll(nguồn)
đích sau                [start, B, A, B, C]
~~~

Phần `start` vẫn còn. Nếu mục tiêu là một cấu trúc mới chỉ chứa nguồn, constructor thường thể hiện ý định trực tiếp hơn việc vô tình thêm vào một đích còn dữ liệu cũ.

`Collection.addAll` là thao tác tùy chọn; nguồn không được bị sửa trong lúc thao tác đang diễn ra theo hợp đồng chung. Cờ trả về là `true` khi đích thay đổi. [Java 17: Collection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)).

### 4.1. Trên List: giữ các lần xuất hiện và chèn theo trình tự

Với danh sách thường hỗ trợ thêm, `addAll(source)` nối các phần tử vào cuối theo thứ tự iterator nguồn.

`List` còn có overload:

~~~java
boolean addAll(int index, Collection<? extends E> source);
~~~

Nó chèn nhóm vào vị trí `index`, dịch phần phía sau. Vị trí chèn có thể từ `0` đến `size()`, bao gồm `size()` là nối cuối.

Ví dụ đích `[start, B, A]`, chèn `[X, Y]` tại `1` cho `[start, X, Y, B, A]`. Bên trong nhóm, `X` vẫn trước `Y`. [Java 17: List.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#addAll(int,java.util.Collection)).

Nếu nguồn là một set không bảo đảm thứ tự, list đích chỉ giữ trình tự nguồn được quan sát trong lần sao chép; nó không tự khôi phục một thứ tự nghiệp vụ chưa được nguồn bảo đảm.

### 4.2. Trên Set: không tăng số thành viên với phần tử đã có

Với `LinkedHashSet` đang là `[B, A, C]`:

~~~text
addAll([B, A])          false, vẫn [B, A, C]
addAll([C, D])          true, thành [B, A, C, D]
~~~

Cờ `false` không nói “không đọc nguồn” hay “sao chép gặp lỗi”. Nó nói không có thay đổi thành viên theo thao tác được thực hiện. Các giá trị đã tồn tại không tạo bản trùng.

Tính duy nhất do hợp đồng set và cách triển khai quyết định. Nếu dùng phần tử tự định nghĩa trong set băm, cần `equals`/`hashCode` đúng; nếu dùng set sắp xếp, quy tắc so sánh cũng liên quan. `Set` không cho các phần tử trùng theo hợp đồng của nó. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.3. addAll không sao chép sâu và không chuyển quyền sở hữu

Nếu nguồn chứa đối tượng `Note`, `addAll` đưa các tham chiếu đến chúng vào đích. Xóa một phần tử khỏi nguồn sau khi hoàn tất không tự xóa nó khỏi đích, nhưng sửa chính đối tượng dùng chung có thể thấy qua cả hai.

Thao tác cũng không “lấy” phần tử ra khỏi nguồn. Một nguồn vẫn giữ dữ liệu nếu bạn không chủ động xóa bằng một hành động riêng.

### 4.4. Nguồn là view của đích: tránh chồng lấn không rõ hợp đồng

Hợp đồng chung nêu hành vi không xác định khi nguồn bị sửa trong lúc `addAll` đang chạy; trường hợp source chính là collection đích không rỗng nằm trong cảnh báo này.

Không dùng việc một phiên bản `ArrayList` có thể xử lý một trường hợp `list.addAll(list)` để viết helper tổng quát dựa vào nó. Đích cũng có thể chồng lấn nguồn qua một `subList` hoặc view khác.

Nếu thật sự muốn nhân đôi các phần tử hiện tại, tạo dữ liệu trung gian độc lập về cấu trúc rồi thêm:

~~~java
List<E> snapshot = new ArrayList<>(items);
items.addAll(snapshot);
~~~

Đây là mẫu bên trong ngữ cảnh có kiểu `E`, nguồn/đích hỗ trợ và không bị sửa đồng thời. Dữ liệu phần tử vẫn được chia sẻ theo sao chép nông.

## 5. putAll: hợp nhất ánh xạ theo khóa, không đồng bộ hai map

Chữ ký:

~~~java
void putAll(Map<? extends K, ? extends V> source);
~~~

`Map` không phải `Collection`, nên thao tác hàng loạt của nó làm việc với ánh xạ khóa–giá trị. Hiệu ứng được mô tả tương đương việc áp dụng `put(k, v)` cho từng ánh xạ nguồn. Nó không trả cờ `boolean` hoặc map kết quả. [Java 17: Map.putAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putAll(java.util.Map)).

### 5.1. Khóa trùng bị cập nhật; khóa đích không có trong nguồn vẫn giữ

Giả sử:

~~~text
đích                  {timeout=5, mode=SAFE, owner=team}
nguồn                 {mode=FAST, retries=3}
~~~

Sau `destination.putAll(source)`:

~~~text
{timeout=5, mode=FAST, owner=team, retries=3}
~~~

`mode` được thay vì khóa đã có; `retries` được thêm; `timeout` và `owner` vẫn còn vì `putAll` không xóa những khóa vắng ở nguồn.

Một mẫu kết hợp cấu hình rõ ý định là:

~~~java
Map<String, String> effective = new LinkedHashMap<>(defaults);
effective.putAll(overrides);
~~~

Đây là đoạn minh họa trong phương thức. `defaults` không bị thay cấu trúc; `effective` nhận mặc định rồi lớp ghi đè. Thứ tự áp dụng quan trọng: đảo hai bước có thể khiến mặc định đè ngược giá trị người dùng cung cấp.

### 5.2. putAll không phải cộng dồn theo nghĩa nghiệp vụ

Nếu hai map cùng có `"apples"` với số lượng `2` và `3`, `putAll` không tự tính tổng `5`. Nó áp dụng quy tắc `put` của đích, tức thay giá trị cho khóa phù hợp.

Nếu cần cộng, giữ giá trị cũ hay phát hiện xung đột rồi báo lỗi, phải chọn quy tắc kết hợp riêng, ví dụ một vòng lặp dùng `merge` với hàm phù hợp. Không gọi mọi kiểu hợp nhất là cùng một thao tác “copy”.

### 5.3. Giá trị null là dữ liệu khi đích cho phép

Đưa ánh xạ `owner=null` vào `LinkedHashMap` bằng `putAll` làm khóa `owner` tồn tại với giá trị `null`. Nó không tự xóa khóa đó.

Một số định dạng cấu hình bên ngoài có thể quy ước `null` nghĩa là xóa, nhưng quy ước ấy cần một bước xử lý của ứng dụng. Nó không phải hành vi tự có của `Map.putAll`.

### 5.4. Không tạo liên kết sống giữa hai map

Sau khi `target.putAll(source)` hoàn tất, thay ánh xạ của `source` không tự cập nhật `target`. Hai cấu trúc map độc lập nếu chúng vốn là hai đối tượng riêng không có quan hệ view.

Tuy vậy, khóa và giá trị là các tham chiếu được sao chép. Nếu giá trị là một danh sách, cả hai map có thể cùng trỏ tới danh sách ấy. Thay ánh xạ khác với sửa trạng thái đối tượng giá trị.

### 5.5. Thứ tự sau putAll do đích quyết định

Với `LinkedHashMap` theo thứ tự chèn, khóa đã có giữ vị trí khi `put` cập nhật giá trị; khóa mới được thêm theo thứ tự các ánh xạ nguồn được xử lý. Một map access-order có quy tắc truy cập khác.

Constructor `LinkedHashMap(Map)` tạo map theo thứ tự chèn của bản mới, không tự sao chép chế độ access-order hoặc toàn bộ chính sách của nguồn. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Với map sắp xếp, thứ tự do khóa và bộ so sánh quyết định, không phải trình tự chèn. Không đoán kết quả in của một map không bảo đảm thứ tự chỉ từ cách viết `putAll`.

## 6. Comparator và overload constructor: cùng đối tượng nguồn, khác lựa chọn

Một constructor sao chép không phải luôn chỉ có một dạng. Kiểu khai báo của biểu thức đối số tham gia chọn overload lúc biên dịch.

### 6.1. TreeSet(Collection) và TreeSet(SortedSet)

Giả sử nguồn là một set số nguyên theo thứ tự giảm:

~~~java
SortedSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
descending.addAll(List.of(3, 1, 2));

Collection<Integer> broad = descending;
TreeSet<Integer> a = new TreeSet<>(descending);
TreeSet<Integer> b = new TreeSet<>(broad);
~~~

Đây là đoạn minh họa với import tương ứng.

- `new TreeSet<>(descending)` chọn constructor nhận `SortedSet`, giữ quy tắc thứ tự của nguồn: `[3, 2, 1]`.
- `new TreeSet<>(broad)` chọn constructor nhận `Collection`, dùng thứ tự tự nhiên: `[1, 2, 3]`.

Hai biến nguồn cùng trỏ đến một đối tượng, nhưng overload được chọn khác vì kiểu tĩnh khác. Constructor nhận `Collection` không tự biến thành constructor nhận `SortedSet` chỉ vì đối tượng thực tế là set sắp xếp. [Java 17: TreeSet constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Nếu muốn xây một set mới theo một comparator cụ thể từ nguồn tổng quát, tạo đích với comparator ấy rồi `addAll`:

~~~java
TreeSet<Integer> copy = new TreeSet<>(Comparator.reverseOrder());
copy.addAll(broad);
~~~

Dùng một `TreeSet` rỗng mặc định rồi `addAll` không tự học comparator của nguồn.

### 6.2. TreeMap(Map) và TreeMap(SortedMap)

`TreeMap` có sự phân biệt tương tự:

- constructor nhận `SortedMap` giữ thứ tự so sánh của nguồn;
- constructor nhận `Map` dùng thứ tự tự nhiên của khóa.

Nếu khóa không có thứ tự tự nhiên phù hợp, việc mất comparator không chỉ đổi trình tự mà còn có thể khiến constructor thất bại. [Java 17: TreeMap constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

Chương trình chính dùng số nguyên để cả hai cách đều chạy được và sự khác biệt thể hiện rõ ở thứ tự khóa.

### 6.3. Sao chép còn có thể đổi quan hệ “trùng”

Nếu đích so sánh các phần tử theo quy tắc khác nguồn, số phần tử hoặc ánh xạ có thể thay đổi theo quan hệ tương đương của đích.

Không dùng comparator chỉ dựa trên độ dài tên rồi mặc định vẫn giữ được mọi tên khác nhau. Với set/cây, các giá trị được so sánh bằng `0` có thể bị xem là cùng một vị trí logic. Muốn giữ hợp đồng set/map thông thường, quan hệ so sánh cần nhất quán với phép bằng cần thiết của kiểu dữ liệu.

Đây là lựa chọn mô hình dữ liệu, không phải một lỗi mà constructor sao chép có trách nhiệm tự sửa.

## 7. Quy tắc kiểu, null và khả năng sửa vẫn áp dụng

### 7.1. Kiểu con của phần tử nguồn có thể đi vào kiểu cha ở đích

`Collection<? extends E>` cho phép nguồn có phần tử là kiểu con của `E`:

~~~java
List<Integer> source = List.of(1, 2);
List<Number> target = new ArrayList<>();
target.addAll(source);
target.add(3.5);
~~~

Đây là đoạn chạy trong phương thức. Nó không có nghĩa `List<Integer>` trở thành kiểu con của `List<Number>`. Ta đọc các `Integer` từ nguồn và đưa chúng vào một đích có thể chứa `Number`.

`putAll` cũng cho nguồn có khóa và giá trị phù hợp dưới dạng kiểu con qua các wildcard tương ứng. Không cần dùng raw type hay ép kiểu mất an toàn chỉ để chuyển dữ liệu hợp lệ.

### 7.2. Đích quyết định có nhận null hay không

Một nguồn hợp lệ có thể chứa phần tử `null`, nhưng đích không nhất thiết nhận. `new ArrayList<>(sourceWithNull)` có thể thành công, trong khi `new ArrayDeque<>(sourceWithNull)` ném `NullPointerException` vì `ArrayDeque` cấm phần tử `null`. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Với map, chính sách khóa/giá trị `null` cũng phụ thuộc loại đích. Việc “dữ liệu đã nằm trong một map hợp lệ” không chứng minh nó hợp lệ với mọi map khác.

Phân biệt nguồn chứa một phần tử `null` với chính tham chiếu nguồn bằng `null`. Constructor hoặc thao tác hàng loạt không tự hiểu nguồn `null` là nguồn rỗng.

### 7.3. addAll và putAll cần quyền sửa đích

Đích từ `List.of` hoặc `Map.of` không cho sửa. Việc thao tác có tên “copy” trong suy nghĩ của bạn không mở quyền thay đổi đối tượng ấy.

Các lớp bọc không sửa được cũng giữ giới hạn tương ứng. Một nguồn không sửa được vẫn có thể được đọc để dựng một đích sửa được, nhưng muốn cập nhật tại chỗ thì chính đích phải hỗ trợ thao tác.

Không dùng một lần gọi với nguồn rỗng để thăm dò quyền sửa, rồi suy mọi lần sau sẽ hợp lệ. Các API có thể từ chối thao tác tùy chọn ngay cả khi bạn cho rằng không có gì thay đổi.

## 8. Ngoại lệ và thay đổi đồng thời: không tự có “tất cả hoặc không gì”

### 8.1. Thao tác hàng loạt không phải giao dịch tổng quát

`addAll` và `putAll` có thể gặp lỗi kiểu, `null`, comparator hoặc giới hạn của đích. Hợp đồng chung không hứa rollback mọi thay đổi đã làm trước ngoại lệ cho mọi cách triển khai.

Nếu muốn một chức năng thay thế dữ liệu chỉ công bố trạng thái mới sau khi chuẩn bị hợp lệ, có thể dựng một ứng viên riêng, kiểm tra rồi mới chuyển tham chiếu ở tầng sở hữu phù hợp. Đừng `clear` nguồn hiện tại trước khi biết dữ liệu mới hợp lệ rồi coi ngoại lệ là không có hậu quả.

Việc tạo ứng viên không tự giải quyết đồng thời: thao tác công bố trạng thái, vòng đời các view cũ và quy tắc khóa vẫn phải được thiết kế.

### 8.2. clear rồi addAll không tương đương trong mọi quan hệ tham chiếu

Giả sử hai biến cùng trỏ một list. Nếu gọi `target.clear()` rồi `target.addAll(source)` và source thực ra chính là target hoặc view dựa trên nó, bạn có thể đã xóa dữ liệu cần đọc trước khi bắt đầu thêm.

Khi mục đích là thay nội dung, hãy xác định nguồn/đích có chung cấu trúc không. Nếu cần giữ nguồn trước, sao chép dữ liệu thích hợp trước khi xóa. Nhưng nếu phải giữ nguyên danh tính đối tượng đích vì nơi khác đang giữ tham chiếu, thay biến sang đối tượng mới cũng có ý nghĩa khác việc sửa tại chỗ.

### 8.3. Sao chép không tự tạo ảnh chụp nguyên tử

Nếu nguồn bị sửa trong lúc constructor hoặc thao tác hàng loạt đang đọc, phải tuân chính sách đồng thời của nguồn và công cụ dùng. Không xem việc kết quả là một đối tượng mới như bằng chứng mọi phần tử được lấy ở cùng một thời điểm.

Một `ConcurrentHashMap` hỗ trợ truy cập đồng thời, nhưng các quan sát tổng hợp và cập nhật nhiều ánh xạ không tự trở thành một giao dịch toàn map. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Nếu nghiệp vụ cần một ảnh chụp nhất quán của nhiều trường/ánh xạ, cần một cơ chế phù hợp bao trùm việc đọc, hoặc một mô hình dữ liệu bất biến/phiên bản hóa rõ ràng. Không dựa vào việc có hay không có ngoại lệ fail-fast để chứng minh tính nhất quán.

## 9. Chương trình đầy đủ

Lưu toàn bộ mã dưới vào **`BulkCopyDemo.java`**. Ví dụ dùng một luồng và các nguồn có thứ tự xác định để stdout có thể kiểm tra chính xác.

Lớp `Note` cố tình có một trường thay đổi được để thấy tham chiếu chia sẻ. Bản sao phần tử tường minh trong ví dụ chỉ cần sao chép một chuỗi bất biến; không coi cách đó là thuật toán sao chép sâu cho mọi đồ thị đối tượng.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class BulkCopyDemo {
    static final class Note {
        String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public String toString() {
            return text;
        }
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("B", "A", "B"));
        List<String> alias = source;
        List<String> copied = new ArrayList<>(source);
        System.out.println("alias same list: " + (alias == source));
        System.out.println("constructor same list: " + (copied == source));
        source.add("C");
        System.out.println("source after add: " + source);
        System.out.println("constructor list stays: " + copied);

        List<String> merged = new ArrayList<>(List.of("start"));
        boolean changed = merged.addAll(source);
        System.out.println("list addAll: " + changed + ", result=" + merged);
        merged.addAll(1, List.of("X", "Y"));
        System.out.println("indexed addAll: " + merged);
        System.out.println("empty addAll: " + merged.addAll(List.of()));
        ArrayList<String> reserved = new ArrayList<>(10);
        System.out.println("capacity constructor size: " + reserved.size());

        LinkedHashSet<String> unique = new LinkedHashSet<>(source);
        System.out.println("set constructor: " + unique);
        System.out.println("set addAll existing: " + unique.addAll(List.of("B", "A")));
        changed = unique.addAll(List.of("C", "D"));
        System.out.println("set addAll new: " + changed + ", result=" + unique);

        Note shared = new Note("draft");
        List<Note> notes = new ArrayList<>(List.of(shared));
        List<Note> constructorNotes = new ArrayList<>(notes);
        List<Note> bulkNotes = new ArrayList<>();
        bulkNotes.addAll(notes);
        shared.text = "reviewed";
        System.out.println("shared element in both copies: "
                + (notes.get(0) == constructorNotes.get(0)
                && notes.get(0) == bulkNotes.get(0)));
        System.out.println("after element edit: " + notes + " / "
                + constructorNotes + " / " + bulkNotes);
        notes.add(new Note("extra"));
        System.out.println("independent list sizes: "
                + notes.size() + " / " + constructorNotes.size());

        List<Note> independentNotes = new ArrayList<>();
        for (Note note : notes) {
            independentNotes.add(new Note(note.text));
        }
        notes.get(0).text = "final";
        System.out.println("shallow after second edit: " + constructorNotes);
        System.out.println("explicit element copies: " + independentNotes);

        Map<String, String> defaults = new LinkedHashMap<>();
        defaults.put("timeout", "5");
        defaults.put("mode", "SAFE");
        defaults.put("owner", "team");
        Map<String, String> overrides = new LinkedHashMap<>();
        overrides.put("mode", "FAST");
        overrides.put("retries", "3");
        Map<String, String> combined = new LinkedHashMap<>(defaults);
        combined.putAll(overrides);
        System.out.println("map constructor plus putAll: " + combined);
        System.out.println("defaults unchanged: " + defaults);
        overrides.put("mode", "LATER");
        System.out.println("combined mode stays: " + combined.get("mode"));

        Map<String, String> nullOverride = new LinkedHashMap<>();
        nullOverride.put("owner", null);
        combined.putAll(nullOverride);
        System.out.println("null is a value, not deletion: " + combined);

        Map<String, List<String>> groups = new LinkedHashMap<>();
        groups.put("alpha", new ArrayList<>(List.of("one")));
        Map<String, List<String>> groupCopy = new LinkedHashMap<>(groups);
        groupCopy.get("alpha").add("two");
        groupCopy.put("beta", new ArrayList<>(List.of("x")));
        System.out.println("map shared value: " + groups);
        System.out.println("map structures independent: "
                + groups.keySet() + " / " + groupCopy.keySet());

        SortedSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(3, 1, 2));
        Collection<Integer> broadCollection = descending;
        TreeSet<Integer> keepSetOrder = new TreeSet<>(descending);
        TreeSet<Integer> naturalSetOrder = new TreeSet<>(broadCollection);
        System.out.println("SortedSet constructor: " + keepSetOrder);
        System.out.println("Collection constructor: " + naturalSetOrder);

        SortedMap<Integer, String> descendingMap =
                new TreeMap<>(Comparator.reverseOrder());
        descendingMap.put(3, "c");
        descendingMap.put(1, "a");
        descendingMap.put(2, "b");
        Map<Integer, String> broadMap = descendingMap;
        TreeMap<Integer, String> keepMapOrder = new TreeMap<>(descendingMap);
        TreeMap<Integer, String> naturalMapOrder = new TreeMap<>(broadMap);
        System.out.println("SortedMap constructor keys: " + keepMapOrder.keySet());
        System.out.println("Map constructor keys: " + naturalMapOrder.keySet());

        List<String> nullable = Arrays.asList("ok", null);
        System.out.println("ArrayList accepts copied null: " + new ArrayList<>(nullable));
        System.out.println("ArrayDeque rejects copied null: "
                + failure(() -> new ArrayDeque<>(nullable)));

        List<String> readOnlyList = List.of("A");
        System.out.println("read-only list addAll: "
                + failure(() -> readOnlyList.addAll(List.of("B"))));
        List<String> writableList = new ArrayList<>(readOnlyList);
        writableList.add("B");
        System.out.println("new mutable list from read-only source: " + writableList);

        Map<String, Integer> readOnlyMap = Map.of("A", 1);
        System.out.println("read-only map putAll: "
                + failure(() -> readOnlyMap.putAll(Map.of("B", 2))));
        Map<String, Integer> writableMap = new LinkedHashMap<>(readOnlyMap);
        writableMap.put("B", 2);
        System.out.println("new mutable map from read-only source: " + writableMap);

        List<Number> numbers = new ArrayList<>();
        numbers.addAll(List.of(1, 2));
        numbers.add(3.5);
        System.out.println("subtype source: " + numbers);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 BulkCopyDemo.java
java BulkCopyDemo
~~~

Dùng JDK 17 trở lên để biên dịch ở mức release 17 và runtime Java 17 trở lên để chạy. Ví dụ đã được biên dịch với mức release 17 và chạy thành công trên OpenJDK 24.0.2.

Stdout chính xác:

~~~text
alias same list: true
constructor same list: false
source after add: [B, A, B, C]
constructor list stays: [B, A, B]
list addAll: true, result=[start, B, A, B, C]
indexed addAll: [start, X, Y, B, A, B, C]
empty addAll: false
capacity constructor size: 0
set constructor: [B, A, C]
set addAll existing: false
set addAll new: true, result=[B, A, C, D]
shared element in both copies: true
after element edit: [reviewed] / [reviewed] / [reviewed]
independent list sizes: 2 / 1
shallow after second edit: [final]
explicit element copies: [reviewed, extra]
map constructor plus putAll: {timeout=5, mode=FAST, owner=team, retries=3}
defaults unchanged: {timeout=5, mode=SAFE, owner=team}
combined mode stays: FAST
null is a value, not deletion: {timeout=5, mode=FAST, owner=null, retries=3}
map shared value: {alpha=[one, two]}
map structures independent: [alpha] / [alpha, beta]
SortedSet constructor: [3, 2, 1]
Collection constructor: [1, 2, 3]
SortedMap constructor keys: [3, 2, 1]
Map constructor keys: [1, 2, 3]
ArrayList accepts copied null: [ok, null]
ArrayDeque rejects copied null: NullPointerException
read-only list addAll: UnsupportedOperationException
new mutable list from read-only source: [A, B]
read-only map putAll: UnsupportedOperationException
new mutable map from read-only source: {A=1, B=2}
subtype source: [1, 2, 3.5]
~~~

### 9.1. Danh sách và tập hợp

Các dòng đầu phân biệt alias với cấu trúc mới. Thêm `C` vào nguồn không làm bản sao constructor tăng kích thước. `addAll` vào danh sách có `start` giữ phần tử cũ và nối nguồn; overload có chỉ số chèn cả nhóm vào vị trí mong muốn.

Set đích loại trùng. `addAll` chỉ gồm thành viên đã có trả `false`; thêm `D` mới trả `true`.

### 9.2. Đối tượng Note và giá trị map có thể sửa

Hai danh sách sao chép cùng nhận tham chiếu `Note` nên thấy lần sửa `reviewed` và `final`. Nhưng việc thêm một note mới vào nguồn không làm cấu trúc bản sao tự tăng.

Vòng tạo note mới tạo các đối tượng độc lập cho mô hình đơn giản này. Bản ấy giữ `reviewed` sau khi nguồn đổi thành `final`.

Map có giá trị danh sách cũng cho thấy cùng nguyên tắc: sửa danh sách `alpha` nhìn thấy qua nguồn, còn thêm khóa `beta` vào bản sao không tự thêm khóa đó vào nguồn.

### 9.3. putAll và cấu hình ghi đè

Map kết hợp nhận mặc định trước, rồi cập nhật `mode` và thêm `retries`. `owner` không biến mất vì vắng ở map ghi đè.

Thay `overrides` sau khi thao tác hoàn tất không cập nhật map kết hợp. Đưa `owner=null` vào map kết hợp vẫn giữ khóa, chỉ thay giá trị.

### 9.4. Comparator và các điều kiện đích

Hai cặp constructor cho kết quả giảm hoặc tăng chỉ vì overload khác, dù nguồn thực tế là cùng đối tượng sắp xếp giảm.

Các dòng cuối phân biệt chính sách `null` và quyền sửa của đích. Bản `ArrayList`/`LinkedHashMap` mới tạo từ nguồn không sửa được lại có quyền sửa theo lớp đích đã chọn.

## 10. Những công cụ trông giống nhưng có ý nghĩa khác

### 10.1. View không phải constructor sao chép

`subList`, `keySet` hoặc các lớp bọc view có thể gắn với nguồn. `new ArrayList<>(view)` tạo cấu trúc danh sách mới chứa dữ liệu đọc từ view, không biến bản sao thành một phần tiếp tục ghi xuyên tự động.

Riêng phần tử `Map.Entry` cần thận trọng: sao chép collection chứa các entry không tự chứng minh từng entry đã độc lập với nguồn. Khi cần giữ các cặp ổn định, hãy sao chép từng cặp hoặc dựng map mới theo mục đích. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### 10.2. Collections.copy không phải addAll

`Collections.copy(destination, source)` ghi đè các vị trí đã tồn tại của list đích; đích phải đủ **size**, không chỉ capacity. Nó không phải phép tạo collection mới hoặc nối phần tử. [Java 17: Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)).

Vì thế, `new ArrayList<>(10)` không đủ làm đích cho việc copy mười phần tử bằng công cụ này nếu list vẫn rỗng. Với yêu cầu tạo bản sao sửa được, constructor nhận collection thường là lựa chọn trực tiếp.

### 10.3. List.copyOf và Map.copyOf có mục tiêu khác

Các factory `copyOf` tạo kết quả không sửa được theo hợp đồng của chúng và có giới hạn như không nhận `null`. Chúng không phải một tên khác của constructor lớp đích sửa được.

Không suy bảo đảm thứ tự cho mọi factory map hoặc suy rằng “không sửa được” đồng nghĩa phần tử bất biến sâu. Hãy xác định mục tiêu trước: kết quả mới có cần sửa không, có cần giữ thứ tự/comparator không, có `null` không và có được chia sẻ phần tử không.

## 11. Chọn cách sao chép theo yêu cầu

| Yêu cầu | Cách thường phù hợp | Điều phải kiểm tra |
| --- | --- | --- |
| Tạo list sửa được từ dữ liệu nguồn | `new ArrayList<>(source)` | Thứ tự nguồn, phần tử chia sẻ |
| Nối dữ liệu vào list đang có | `target.addAll(source)` | Dữ liệu cũ vẫn giữ, quyền thêm |
| Chèn một nhóm tại vị trí | `target.addAll(index, source)` | Chỉ số, thứ tự nhóm, chi phí dịch |
| Loại trùng và giữ lần xuất hiện đầu theo nguồn | `new LinkedHashSet<>(source)` | Phép bằng/băm và ý nghĩa dữ liệu lặp |
| Tạo map cấu trúc riêng | `new LinkedHashMap<>(source)` | Thứ tự duyệt, giá trị/khóa chia sẻ |
| Áp lớp ghi đè lên map đang có | `target.putAll(overrides)` | Khóa trùng bị thay, khóa khác không bị xóa |
| Giữ comparator của nguồn sắp xếp | Constructor/đích được cấu hình đúng comparator | Overload do kiểu tĩnh chọn |
| Giữ trạng thái phần tử độc lập | Sao chép phần tử theo mô hình dữ liệu | Độ sâu, tham chiếu dùng chung, chu trình |
| Công bố một trạng thái thay thế sau khi chuẩn bị | Dựng ứng viên, kiểm tra, công bố theo chính sách sở hữu | Đồng thời, lỗi giữa chừng, view/alias cũ |

Hiệu năng cũng phụ thuộc loại đích. Tạo bản sao nông của n tham chiếu vẫn cần làm việc với dữ liệu nguồn; không phải miễn phí vì không sao chép sâu. Với list mảng, cấp phát trước hợp lý hoặc thêm cả nhóm có thể giảm một số chi phí tăng dung lượng/dịch chuyển, nhưng không nên hứa mọi constructor luôn nhanh hơn mọi dạng `addAll`. Đo trường hợp thực tế khi hiệu năng có ý nghĩa.

## 12. Lỗi thường gặp

1. **Gán biến rồi gọi là bản sao:** hai biến vẫn chung cấu trúc.
2. **Có collection mới nên phần tử cũng mới:** constructor và thao tác hàng loạt thông thường sao chép tham chiếu.
3. **addAll thay dữ liệu cũ:** nó thêm theo hợp đồng đích, không tự clear.
4. **putAll làm đích giống hệt nguồn:** các khóa chỉ có ở đích vẫn giữ.
5. **Khóa trùng được cộng hoặc gộp tự động:** `putAll` dùng ngữ nghĩa `put`, không tự định nghĩa phép cộng.
6. **Nguồn không sửa được nên bản sao cũng không sửa được:** lớp/factory đích mới quyết định hợp đồng đó.
7. **Capacity bằng size:** constructor số nguyên không tạo phần tử.
8. **Comparator luôn đi theo dữ liệu:** overload hoặc cấu hình đích quyết định.
9. **Null ở nguồn hợp lệ nên đích nào cũng nhận:** chính sách đích có thể khác.
10. **Bulk operation là giao dịch:** không tự có rollback hoặc ảnh chụp nguyên tử.
11. **Self-copy hay nguồn view chồng lấn luôn an toàn:** phải theo hợp đồng; tách dữ liệu khi cần.
12. **Bản sao giữ nguyên mọi chế độ lớp nguồn:** loại đích có thể đổi thứ tự, tính duy nhất, comparator và chính sách truy cập.

## 13. Thực hành có đáp án

### Bài 1 — Phân biệt alias và list mới

`a` là một `ArrayList` chứa `[A, B]`. Đặt `b = a` và `c = new ArrayList<>(a)`. Sau `b.add("C")`, ba danh sách ra sao?

**Đáp án:** `a` và `b` cùng là `[A, B, C]` vì chung đối tượng. `c` vẫn `[A, B]` về cấu trúc. Nếu phần tử là đối tượng có trạng thái thay đổi, bản `c` vẫn có thể chia sẻ những đối tượng ấy.

### Bài 2 — addAll có xóa phần trước không?

Đích là `[old]`, nguồn `[X, X]`. Sau `ArrayList.addAll(source)` và sau `LinkedHashSet.addAll(source)` trên hai đích riêng cùng ban đầu chứa `old`, khác nhau gì?

**Đáp án:** list thành `[old, X, X]`; set liên kết thành `[old, X]`. Cả hai giữ `old`. Phần tử lặp được xử lý theo hợp đồng loại đích, không theo một quy tắc sao chép chung bắt buộc giữ nguyên số lượng.

### Bài 3 — Khóa trùng và khóa chỉ có ở đích

Đích `{A=1, B=2}`, nguồn `{B=20, C=3}`. Sau `putAll` có mất `A` không? `B` bằng bao nhiêu?

**Đáp án:** `A` vẫn có giá trị `1`, `B` thành `20` và `C` được thêm với `3`. Đây là áp các ánh xạ nguồn, không phải thao tác đồng bộ để xóa mọi khóa ngoài nguồn. Thứ tự in tùy nguồn/đích cụ thể.

### Bài 4 — Sao chép một danh sách đối tượng

Tạo `copy = new ArrayList<>(notes)` rồi sửa `notes.get(0).text`. Tại sao `copy` thấy thay đổi dù `copy != notes`?

**Đáp án:** hai list khác cấu trúc nhưng cùng chứa tham chiếu đến đối tượng note. Cần tạo note mới nếu yêu cầu độc lập về trạng thái ấy. Độ sâu sao chép phải theo mô hình dữ liệu, không mặc định mọi trường con cũng độc lập.

### Bài 5 — Constructor của set sắp xếp

Một `SortedSet<Integer>` dùng comparator giảm được gán thêm vào biến `Collection<Integer> broad`. Vì sao `new TreeSet<>(sorted)` và `new TreeSet<>(broad)` có thể khác thứ tự?

**Đáp án:** kiểu tĩnh chọn overload. Dạng nhận `SortedSet` giữ thứ tự so sánh nguồn; dạng nhận `Collection` dùng thứ tự tự nhiên. Muốn comparator cụ thể từ nguồn tổng quát, tạo đích với comparator rồi thêm dữ liệu.

### Bài 6 — Capacity và dữ liệu

Một lập trình viên tạo `new ArrayList<String>(100)` rồi cho rằng list có 100 vị trí để gọi `set` hoặc `Collections.copy`. Sai ở đâu?

**Đáp án:** con số là dung lượng ban đầu, `size` vẫn 0. Phải có phần tử thực sự nếu thao tác yêu cầu vị trí đã tồn tại. Nếu cần bản sao dữ liệu nguồn, dùng constructor nhận collection hoặc `addAll` đúng mục đích.

### Bài 7 — Ghi đè bằng null

Map cho phép `null`, có `mode=SAFE`. Nguồn chứa `mode=null`. `putAll` có xóa khóa `mode` không?

**Đáp án:** không; ánh xạ tồn tại với giá trị `null`. Nếu nghiệp vụ quy định `null` là tín hiệu xóa, cần một thuật toán xử lý quy ước đó riêng. Không nhầm quy tắc dữ liệu bên ngoài với ngữ nghĩa chuẩn của map.

### Bài 8 — Thất bại và nguồn chồng lấn

Một hàm làm `target.clear(); target.addAll(source);` để thay dữ liệu. Cần kiểm tra những vấn đề nào trước khi coi đây là phép thay thế an toàn?

**Đáp án:** nguồn có cùng đối tượng hoặc là view dựa trên đích không; đích có hỗ trợ xóa/thêm không; dữ liệu có hợp kiểu, `null`, comparator hay giới hạn không; thao tác có thể thất bại giữa chừng không; có thay đổi đồng thời không; các alias/view khác cần nhìn cùng đối tượng hay một trạng thái mới. Không tự có rollback. Có thể cần dựng ứng viên trước và công bố theo chính sách sở hữu phù hợp.

Khi tự luyện, hãy viết ra bốn dòng cho mỗi phép sao chép: đối tượng chứa mới hay cũ, phần tử/khóa/giá trị có dùng chung tham chiếu không, quy tắc dữ liệu của đích là gì, và thao tác có thay đổi dữ liệu đã có ở đích ra sao. Bốn câu trả lời ấy xác định đúng ý nghĩa hơn việc chỉ nhìn tên có chữ “copy”.
