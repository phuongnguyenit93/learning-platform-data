# keySet, values, entrySet và các thao tác ghi xuyên về Map

## 1. View là một cách truy cập dữ liệu đang có

Một map lưu vai trò theo tên người dùng:

~~~text
ada -> READER
lin -> EDITOR
sam -> READER
~~~

Một chức năng chỉ cần tên; một chức năng thống kê vai trò; một chức năng khác cần cả tên và vai trò. Java cung cấp ba góc nhìn (view) của cùng map:

~~~java
Set<K> keySet();
Collection<V> values();
Set<Map.Entry<K, V>> entrySet();
~~~

Đây là hình dạng chữ ký API để đọc hợp đồng, không phải chương trình Java độc lập.

**View không mặc nhiên là bản sao.** Với một map sửa được như `LinkedHashMap`, các đối tượng view gắn với map nguồn: sửa nguồn được phản ánh qua view; các thao tác ghi được hỗ trợ trên view truyền về nguồn. Vì vậy, trả `keySet` cho một hàm khác có thể trao cả quyền xóa ánh xạ, chứ không chỉ đưa ra danh sách tên.

`Map` quy định ba collection view này; thứ tự duyệt phụ thuộc loại map. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

Bài này giải thích những đường ghi xuyên, các thao tác bị từ chối, cách duyệt và sửa đúng hợp đồng, cùng khác biệt giữa view, lớp bọc chỉ đọc và bản sao. Chương trình đầy đủ dùng API tương thích **Java 17 trở lên**.

## 2. Ba loại view khác nhau ở đơn vị phần tử

Với nguồn:

~~~text
map                 {ada=READER, lin=EDITOR, sam=READER}

keySet              [ada, lin, sam]
values              [READER, EDITOR, READER]
entrySet            [ada=READER, lin=EDITOR, sam=READER]
~~~

Dấu ngoặc vuông ở đây biểu diễn trình tự in của ví dụ dùng map liên kết, không có nghĩa cả ba đối tượng đều là `List`.

| View | Kiểu trả về | Phần tử biểu diễn | Có thể trùng theo ý nghĩa thông thường? |
| --- | --- | --- | --- |
| `keySet()` | `Set<K>` | Khóa | Không |
| `values()` | `Collection<V>` | Giá trị của từng ánh xạ | Có |
| `entrySet()` | `Set<Map.Entry<K,V>>` | Cặp khóa–giá trị | Mỗi ánh xạ là một entry |

### 2.1. Vì sao values không phải Set?

Hai khóa `ada` và `sam` cùng có giá trị `READER`. Map vẫn có ba ánh xạ, nên view giá trị cũng có ba phần tử: hai lần xuất hiện của `READER` và một `EDITOR`.

Nếu dùng set giá trị để biểu diễn view ấy, bạn sẽ mất thông tin số lần xuất hiện theo ánh xạ. Khi muốn thống kê số người của mỗi vai trò, không được tự loại trùng trước khi đếm.

### 2.2. Entry xét cả khóa lẫn giá trị

Một `Map.Entry` mô tả một cặp. Entry `ada=READER` khác entry `ada=EDITOR` vì giá trị khác. Điều này quan trọng với `entrySet.contains` hoặc `entrySet.remove`: dùng entry đối chiếu không chỉ là đưa một khóa vào một hình thức viết dài hơn.

Phép bằng của entry chuẩn xét cả khóa và giá trị; vai trò kết nối của một entry với map còn phụ thuộc cách bạn lấy nó. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### 2.3. Không phải mọi view có cùng hợp đồng equals

`keySet` và `entrySet` là set, nên có hợp đồng so sánh theo thành viên của set. `values` chỉ được khai báo là `Collection`, không phải danh sách có vị trí hay set loại trùng.

Đừng dùng `map.values().equals(expectedList)` như một cách tổng quát để kiểm chứng nội dung hoặc thứ tự giá trị. Nếu cần kiểm tra trình tự, hãy tạo một danh sách theo lần duyệt phù hợp. Nếu không quan tâm thứ tự nhưng quan tâm số lần lặp, cần so sánh tần suất, không chuyển thẳng sang set.

`Collection` không tự đặt cùng hợp đồng `equals` như `List` hoặc `Set`. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 3. Liên kết hai chiều giữa nguồn và view

Có thể giữ view rồi sửa map:

~~~java
Map<String, String> users = new LinkedHashMap<>();
users.put("ada", "READER");
Set<String> names = users.keySet();

users.put("lin", "EDITOR");
System.out.println(names);
~~~

Đây là đoạn minh họa đặt trong một phương thức có import tương ứng. Kết quả đọc qua `names` là `[ada, lin]`. Không cần gọi lại `keySet` để view “tải dữ liệu mới”.

Ngược lại:

~~~java
names.remove("ada");
~~~

Nếu nguồn hỗ trợ xóa, ánh xạ của `ada` biến mất khỏi `users`. Nó không chỉ mất khỏi một collection tên riêng.

Mô hình cần nhớ:

~~~text
                 cùng map nguồn
                      |
        +-------------+-------------+
        |             |             |
      keySet        values       entrySet
        |             |             |
      xóa khóa     xóa giá trị    xóa cặp phù hợp
        +-------------+-------------+
                      |
                 xóa ánh xạ nguồn
~~~

“Ghi xuyên” là việc thao tác qua view làm thay đổi dữ liệu nguồn. Nó không phải ghi ra tệp, cơ sở dữ liệu hay mạng; bài này chỉ nói về các đối tượng Java trong bộ nhớ.

### 3.1. Live view khác iterator đang hoạt động

View có thể tiếp tục phản ánh nguồn qua những lần truy vấn mới. Iterator là một quá trình duyệt cụ thể, có quy tắc riêng khi nguồn bị sửa.

Bạn không thể tạo iterator, thêm một khóa bằng `map.put`, rồi viện lý do “đây là live view” để tiếp tục duyệt tùy ý. Phải tuân hợp đồng iterator và chính sách đồng thời của map.

### 3.2. Việc đọc view không tạo ảnh chụp nguyên tử

Nếu một luồng khác thay map giữa lúc bạn xem kích thước, in khóa rồi in giá trị, ba quan sát có thể không thuộc cùng một trạng thái. Đặc tính liên kết không đồng nghĩa có khóa ngầm cho toàn bộ chuỗi thao tác.

Chương trình trong bài chạy một luồng để làm rõ hành vi. Khi dùng thực tế, quyền sở hữu và chính sách đồng bộ phải được thiết kế ở nơi quản lý nguồn.

## 4. Những thao tác xóa ghi xuyên về map

### 4.1. keySet.remove(k): chỉ cần khớp khóa

Với `{ada=READER, lin=EDITOR, sam=READER}`:

~~~text
keySet.remove("lin")       true
map sau                   {ada=READER, sam=READER}
~~~

Giá trị của `lin` không cần được truyền vào. Trên view sửa được, giá trị trả về `true` nghĩa có phần tử khóa bị xóa, nên ánh xạ ấy cũng bị xóa.

Điểm này hữu ích khi giá trị có thể là `null`. `map.remove(k)` trả giá trị cũ và có thể trả `null` cho cả ánh xạ vắng mặt lẫn ánh xạ từng mang `null`. `keySet.remove(k)` trả cờ về việc xóa khóa, giúp phân biệt trong cách dùng phù hợp.

Cả hai vẫn là thao tác tùy chọn và phải tuân chính sách kiểu/`null` của nguồn.

### 4.2. values.remove(v): xóa một lần xuất hiện

Nếu có hai người mang vai trò `READER`, `values().remove("READER")` xóa **một ánh xạ** có giá trị phù hợp, không xóa hết hai người.

Trên `LinkedHashMap` của chương trình, việc duyệt có thứ tự chèn nên ví dụ cho kết quả cụ thể. Trong mã nhận `Map` bất kỳ, không dùng thao tác này như cách chỉ định danh tính một người. Nếu mục tiêu là xóa `sam`, hãy xóa theo khóa `sam`.

`Collection.remove` xóa một lần xuất hiện phù hợp nếu có; `removeAll` có ý nghĩa khác. [Java 17: Collection.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

Đừng giả định xóa qua view giá trị chỉ bỏ một giá trị nhưng giữ khóa “không có giá trị”. Một ánh xạ map luôn liên quan đến khóa và giá trị; xóa phần tử view này loại cả ánh xạ tương ứng.

### 4.3. entrySet.remove(entry): phải khớp cặp

Với nguồn chứa `maya=REVIEWER`:

~~~java
entries.remove(Map.entry("maya", "WRONG"));     // false
entries.remove(Map.entry("maya", "REVIEWER"));  // true
~~~

Đây là đoạn minh họa với các khóa/giá trị không `null` và entry view sửa được. Lần thứ nhất giữ nguyên nguồn vì cặp không khớp. Lần thứ hai xóa ánh xạ hiện có.

Nếu muốn xóa khi khóa đang mang đúng một giá trị, `map.remove(key, expectedValue)` cũng diễn đạt ý định rõ. Đừng suy một chuỗi `contains` rồi `remove` qua view là một thao tác nguyên tử trong môi trường đồng thời.

### 4.4. clear: xóa toàn bộ ánh xạ

Với các view có quyền xóa:

~~~java
map.keySet().clear();
map.values().clear();
map.entrySet().clear();
~~~

Mỗi dòng riêng lẻ đều là một đường xóa toàn bộ map. Nếu chạy dòng đầu trước, hai dòng sau chỉ còn gặp nguồn đã rỗng; chúng không nhắm ba bản dữ liệu riêng.

Đây là một lý do quan trọng để không trả view nguồn cho bên gọi khi bạn chỉ muốn cung cấp dữ liệu đọc. Một collection trả về có thể chứa quyền tác động rộng hơn vẻ ngoài của tên phương thức.

### 4.5. removeAll, retainAll và removeIf

Các phép lọc trên view có thể rất thuận tiện:

| Ý định | Cách dùng trên nguồn có quyền xóa |
| --- | --- |
| Xóa các khóa thuộc một danh sách cấm | `map.keySet().removeAll(blockedKeys)` |
| Chỉ giữ các khóa được phép | `map.keySet().retainAll(allowedKeys)` |
| Xóa mọi ánh xạ có giá trị trong nhóm | `map.values().removeAll(rejectedValues)` |
| Xóa theo điều kiện cả khóa và giá trị | `map.entrySet().removeIf(predicate)` |

`retainAll` có nghĩa xóa phần tử không được giữ; nó không chỉ “đánh dấu các phần tử được chọn”. Nếu tập cho phép rỗng, thao tác giữ lại theo tập rỗng có thể làm map rỗng.

`removeIf` xóa các phần tử thỏa điều kiện; cách mặc định dựa trên iterator và thao tác xóa của iterator. Nếu điều kiện ném ngoại lệ sau một số lần xóa, không tự coi các lần xóa trước đã được rollback.

Điều kiện nên tập trung vào quyết định, không đồng thời sửa cấu trúc map qua một đường khác. Ví dụ `entry -> entry.getValue().equals("REVIEWER")` phù hợp khi miền dữ liệu cấm `null`; nếu cho phép `null`, cần so sánh an toàn theo chính sách ấy.

## 5. Vì sao thêm vào view thường bị từ chối?

`keySet` và `values` không đủ thông tin để tạo một ánh xạ mới theo ý nghĩa của map:

- thêm một khóa không nói giá trị phải là gì;
- thêm một giá trị không nói khóa nào sở hữu nó.

Ngay cả `entrySet` có cặp đủ thông tin, hợp đồng view cũng không cung cấp `add` hay `addAll` như một đường thay thế `Map.put`. Các view chuẩn này không hỗ trợ các thao tác thêm ấy.

Với nguồn sửa được trong ví dụ:

~~~java
map.keySet().add("new-user");
map.values().add("READER");
map.entrySet().add(Map.entry("new-user", "READER"));
~~~

Mỗi lệnh được kiểm tra riêng và gây `UnsupportedOperationException`. Muốn thêm hoặc cập nhật ánh xạ, dùng API map phù hợp.

Không nên gọi thử một thao tác không được hỗ trợ với dữ liệu trùng hoặc rỗng rồi kết luận “có thể dùng trong trường hợp này”. Các thao tác tùy chọn có thể bị từ chối ngay cả khi bạn cho rằng chúng không tạo thay đổi.

Cũng không có `set(index, value)` trên `values` vì kiểu trả về là `Collection`, không phải danh sách. Muốn thay giá trị cho một khóa, dùng API map hoặc entry iterator có quyền cập nhật.

## 6. entry.setValue: đường cập nhật giá trị trực tiếp

Khi duyệt `entrySet` của một `LinkedHashMap` sửa được, entry được iterator trả về có thể dùng để cập nhật giá trị của ánh xạ:

~~~java
for (Map.Entry<String, String> entry : users.entrySet()) {
    if (entry.getValue().equals("EDITOR")) {
        entry.setValue("REVIEWER");
    }
}
~~~

Đoạn minh họa này thay `EDITOR` thành `REVIEWER` mà giữ khóa và số ánh xạ. Nó không “đổi biến entry cục bộ”; lời gọi ghi vào giá trị của ánh xạ nguồn nếu được hỗ trợ.

### 6.1. Thay biến value cục bộ khác thay giá trị trong map

Đoạn sau không thay ánh xạ:

~~~java
for (String role : users.values()) {
    role = "REVIEWER";
}
~~~

Nó chỉ gán biến vòng lặp đến chuỗi khác. Biến `role` không phải một ô tham chiếu có thể dùng để thay giá trị đang được map lưu.

Ngược lại, nếu giá trị là một đối tượng có thể sửa như `List`, gọi một phương thức sửa trên chính đối tượng đó có thể làm trạng thái thấy qua map thay đổi. Đó là thay trạng thái phần tử, khác với việc thay ánh xạ đến một đối tượng mới.

### 6.2. setValue là tùy chọn và có vòng đời

Không phải mọi `Map.Entry` đều cho `setValue`. Entry từ `Map.entry` là entry độc lập không sửa được; entry lấy qua một map/view chỉ đọc cũng không phải đường mở quyền cập nhật.

Với entry iterator, kết nối với nguồn gắn với quá trình duyệt. Không giữ entry ấy như một tay nắm lâu dài rồi xóa/thay cấu trúc nguồn qua đường khác và tiếp tục dựa vào nó. Nếu cần lưu một cặp ở thời điểm hiện tại, hãy tạo một entry độc lập phù hợp.

Không sửa khóa của entry qua API này; chỉ có `setValue`. Danh tính khóa và các quy tắc bằng/băm của nó vẫn thuộc hợp đồng map.

### 6.3. Giá trị có thể bị hạn chế

Một map có thể cấm giá trị `null` hoặc có ràng buộc khác. Entry cập nhật không tự bỏ qua ràng buộc của nguồn. Đừng dùng `setValue(null)` như cách xóa ánh xạ: nếu được phép, nó gán giá trị `null` nhưng khóa vẫn tồn tại.

Muốn loại ánh xạ đang duyệt, hãy dùng thao tác xóa đúng hợp đồng.

## 7. Duyệt và xóa: dùng iterator của chính lần duyệt

Cách làm rõ ràng là:

~~~java
var it = users.entrySet().iterator();
while (it.hasNext()) {
    var entry = it.next();
    if (shouldDelete(entry)) {
        it.remove();
    }
}
~~~

Đây là đoạn minh họa cần một phương thức quyết định `shouldDelete` do ứng dụng cung cấp; chưa phải chương trình độc lập.

`Iterator.remove` xóa phần tử vừa được `next` trả về; với entry view, đó là ánh xạ tương ứng. Nó chỉ được gọi đúng trạng thái và tối đa một lần cho mỗi lần `next` theo hợp đồng iterator. [Java 17: Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

Không viết vòng `for-each` trên `keySet` rồi gọi `map.remove(key)` bên trong đối với các map thông thường và mong quá trình duyệt luôn hợp lệ. Điều kiện xóa có thể đúng, nhưng đường sửa nằm ngoài iterator đang duyệt.

### 7.1. Fail-fast không phải cơ chế đồng bộ

`HashMap` không bảo đảm thứ tự duyệt và không tự đồng bộ; iterator fail-fast dùng để phát hiện một số sửa cấu trúc ngoài quy trình cho phép, không phải bảo đảm mọi tranh chấp đều bị phát hiện. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Không thấy `ConcurrentModificationException` không chứng minh mã sửa map trong vòng lặp là đúng. Cũng đừng dùng một kiểm thử “phải ném ngoại lệ ở đúng dòng này” làm định nghĩa nghiệp vụ cho thao tác sai hợp đồng.

### 7.2. LinkedHashMap được dùng để kiểm chứng stdout có trình tự

Ví dụ đầy đủ chọn `LinkedHashMap` mặc định theo thứ tự chèn để các dòng in có thể dự đoán. Điều đó không áp đặt thứ tự ấy lên mọi `Map`.

Nếu dùng `LinkedHashMap` access-order, một số lời gọi `get` có thể thay trình tự. Vì vậy, khi đã cần cả khóa lẫn giá trị, duyệt entry thường rõ hơn duyệt khóa rồi tra `get` lặp lại. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

### 7.3. Map đồng thời có chính sách khác, nhưng không tự tạo giao dịch

Một nguồn như `ConcurrentHashMap` có iterator nhất quán yếu và các thao tác đồng thời được mô tả riêng. Nó cấm khóa và giá trị `null`; các quan sát trong khi nguồn đổi không nên bị hiểu là một ảnh chụp nguyên tử của toàn bộ map. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Khi chuyển thuật toán sang map đồng thời, phải đọc hợp đồng của nguồn, phép cập nhật và view đang dùng. Không giữ nguyên mọi giả định fail-fast của `HashMap`, cũng không suy rằng cả một phép lọc nhiều mục luôn là một giao dịch.

## 8. null và phép đối chiếu entry

Với một map cho phép `null`, một khóa có thể tồn tại dù giá trị là `null`:

~~~java
Map<String, String> state = new LinkedHashMap<>();
state.put("pending", null);
boolean removed = state.keySet().remove("pending");
~~~

`removed` là `true` vì khóa đã có và bị xóa. Trường hợp này không cần suy từ giá trị cũ `null`.

Muốn tạo entry đối chiếu có giá trị `null`, không dùng `Map.entry("pending", null)` vì factory đó từ chối `null`. Có thể dùng:

~~~java
Map.Entry<String, String> expected =
        new AbstractMap.SimpleImmutableEntry<>("pending", null);
boolean removed = state.entrySet().remove(expected);
~~~

Đây là đoạn minh họa với nguồn đã có ánh xạ phù hợp. `SimpleImmutableEntry` tạo một cặp độc lập và không cho thay giá trị qua `setValue`. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Các phép kiểm tra/xóa trên nguồn cấm `null` có thể có hành vi theo hợp đồng riêng. Không khái quát một lần thử `HashMap` sang mọi map.

## 9. View, bản sao collection và bản sao entry là ba mức khác nhau

### 9.1. Sao chép khóa hoặc giá trị

Nếu muốn một danh sách tên độc lập về cấu trúc:

~~~java
List<String> savedNames = new ArrayList<>(users.keySet());
~~~

Thêm/xóa khóa trong `users` sau đó không tự thêm/xóa trong `savedNames`. Danh sách mới nhận phần tử theo lần duyệt nguồn khi sao chép. `ArrayList` tạo một cấu trúc danh sách riêng và cho phép thao tác danh sách theo hợp đồng lớp. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Tương tự, `new ArrayList<>(users.values())` lưu các tham chiếu giá trị tại lúc sao chép. Nếu giá trị là đối tượng có thể sửa, bản sao collection không tự sao chép sâu chúng.

### 9.2. Chỉ sao chép collection entry chưa đủ chứng minh cặp đã độc lập

Đoạn này tạo một list mới:

~~~java
List<Map.Entry<String, String>> saved =
        new ArrayList<>(users.entrySet());
~~~

Nhưng các phần tử được đưa vào vẫn là các đối tượng entry do nguồn cung cấp. Không dựa vào list mới để suy rằng mọi entry đã bị tách khỏi nguồn hoặc tiếp tục có quyền cập nhật hợp lệ ngoài lần duyệt.

Muốn giữ các cặp độc lập, hãy sao chép từng entry ngay trong lần duyệt:

~~~java
List<Map.Entry<String, String>> saved = new ArrayList<>();
for (Map.Entry<String, String> entry : users.entrySet()) {
    saved.add(new AbstractMap.SimpleImmutableEntry<>(entry));
}
~~~

Các entry mới không còn là đối tượng entry của view nguồn. Đây vẫn là sao chép nông các tham chiếu khóa/giá trị.

Java 17 cũng có `Map.Entry.copyOf` để tạo entry độc lập, nhưng nó không nhận khóa hoặc giá trị `null`. Chọn công cụ theo miền dữ liệu, không chỉ theo độ ngắn của câu lệnh.

### 9.3. Sao chép map

`new LinkedHashMap<>(users)` tạo một map mới có các ánh xạ được sao chép, giữ thứ tự duyệt đầu vào trong cách dựng này. Sau đó thay giá trị của khóa trong map gốc không tự thay ánh xạ của bản sao.

Nhưng nếu cả hai map cùng giữ một `List` làm giá trị, sửa `List` ấy có thể nhìn thấy qua cả hai. Bản sao cấu trúc map và bản sao sâu dữ liệu là hai mức bảo đảm khác nhau.

Một bản sao được tạo trong khi nhiều luồng đang sửa nguồn cũng không tự được nâng thành ảnh chụp nghiệp vụ nguyên tử. Cần điều kiện truy cập phù hợp trong suốt việc sao chép.

## 10. Bọc chỉ đọc cần bảo vệ đúng tầng

### 10.1. Collections.unmodifiableMap bảo vệ các đường sửa qua map và view

`Collections.unmodifiableMap(source)` trả view chặn sửa ánh xạ qua map và qua các collection view mà nó trả về. Các lần đọc vẫn nhìn nguồn phía dưới, nên nguồn có thể thay đổi qua một tham chiếu khác. [Java 17: Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

Điều này hữu ích khi muốn giữ nguồn đang sống nhưng không trao quyền thêm/xóa/thay giá trị ánh xạ cho bên gọi.

Nó không làm các đối tượng giá trị trở thành bất biến sâu. Nếu nguồn giữ một `ArrayList`, bên gọi có thể nhận tham chiếu danh sách qua `get` và sửa chính danh sách đó, trừ khi mô hình dữ liệu cũng bảo vệ tầng phần tử.

### 10.2. Chỉ bọc entrySet bằng unmodifiableSet có thể để lọt setValue

Xét ý định “trả một set entry không cho bên gọi sửa map”:

~~~java
Set<Map.Entry<String, Integer>> result =
        Collections.unmodifiableSet(scores.entrySet());
~~~

Lớp bọc chặn thêm/xóa phần tử set và xóa qua iterator của nó. Nhưng nó không tự thay mỗi entry bằng một entry chỉ đọc. Khi các entry từ nguồn còn cho cập nhật trong lúc duyệt, `entry.setValue` có thể vẫn ghi xuyên.

Chương trình đầy đủ chứng minh điều này trên một `LinkedHashMap`: vòng lặp qua set bọc đổi điểm `math` từ `80` thành `90`. Bọc `scores` bằng `unmodifiableMap` rồi lấy `entrySet` mới chặn đường cập nhật entry ấy.

Bài học về thiết kế API là kiểm tra **quyền trên đối tượng phần tử**, không chỉ quyền của collection bên ngoài. Tương tự, một `List` không sửa được vẫn có thể chứa phần tử sửa được.

### 10.3. Khi nào chọn bản sao không sửa được?

Nếu bên gọi cần trạng thái tại một thời điểm, có thể sao chép cấu trúc phù hợp rồi bọc bản sao. Nếu cần bất biến sâu, phải sao chép hoặc dùng kiểu bất biến cho các khóa/giá trị liên quan.

`Map.copyOf` tạo map không sửa được và không phản ánh các lần thay đổi ánh xạ tiếp theo của nguồn, nhưng cấm khóa/giá trị `null` và không bảo đảm cùng thứ tự duyệt mong muốn. Không dùng nó như một phép sao chép mọi khía cạnh vô điều kiện.

Lựa chọn cần dựa trên bốn yêu cầu riêng: nguồn có tiếp tục sống không, có được sửa cấu trúc không, phần tử có thể sửa không, và thứ tự có quan trọng không.

## 11. Chương trình đầy đủ

Lưu toàn bộ mã dưới vào **`MapWriteThroughDemo.java`**. Chương trình chạy một luồng, dùng `LinkedHashMap` để stdout có thứ tự xác định và không dùng API chỉ có sau Java 17.

Các chuỗi vai trò là dữ liệu minh họa cho hành vi collection; ví dụ không triển khai một hệ thống phân quyền.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MapWriteThroughDemo {
    static String unsupported(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        Map<String, String> users = new LinkedHashMap<>();
        users.put("ada", "READER");
        users.put("lin", "EDITOR");
        users.put("sam", "READER");
        Set<String> keys = users.keySet();
        Collection<String> roles = users.values();
        Set<Map.Entry<String, String>> entries = users.entrySet();

        users.put("maya", "REVIEWER");
        users.put("lin", "ADMIN");
        System.out.println("live keys: " + keys);
        System.out.println("live values: " + roles);
        System.out.println("live entries: " + entries);

        boolean changed = roles.remove("READER");
        System.out.println("remove one value: " + changed + ", map=" + users);
        changed = keys.remove("lin");
        System.out.println("remove key: " + changed + ", map=" + users);
        changed = entries.remove(Map.entry("maya", "WRONG"));
        System.out.println("remove wrong pair: " + changed + ", map=" + users);
        changed = entries.remove(Map.entry("maya", "REVIEWER"));
        System.out.println("remove matching pair: " + changed + ", map=" + users);

        users.put("nora", "READER");
        users.put("oli", "EDITOR");
        users.put("pia", "READER");
        changed = roles.removeAll(Set.of("READER"));
        System.out.println("remove all reader values: " + changed + ", map=" + users);
        users.put("uma", "VIEWER");
        users.put("vic", "ADMIN");
        users.put("wen", "EDITOR");
        keys.retainAll(Set.of("oli", "uma", "vic"));
        System.out.println("retain allowed keys: " + users);

        Iterator<Map.Entry<String, String>> it = entries.iterator();
        while (it.hasNext()) {
            Map.Entry<String, String> entry = it.next();
            if (entry.getValue().equals("VIEWER")) {
                it.remove();
            } else if (entry.getValue().equals("EDITOR")) {
                entry.setValue("REVIEWER");
            }
        }
        System.out.println("iterator remove and setValue: " + users);
        entries.removeIf(entry -> entry.getValue().equals("REVIEWER"));
        System.out.println("entry predicate removal: " + users);

        List<String> savedKeys = new ArrayList<>(keys);
        List<String> savedValues = new ArrayList<>(roles);
        List<Map.Entry<String, String>> savedEntries = new ArrayList<>();
        for (Map.Entry<String, String> entry : entries) {
            savedEntries.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }
        Map<String, String> savedMap = new LinkedHashMap<>(users);
        users.put("vic", "OWNER");
        users.put("zoe", "EDITOR");
        System.out.println("live map after changes: " + users);
        System.out.println("saved keys: " + savedKeys);
        System.out.println("saved values: " + savedValues);
        System.out.println("saved entries: " + savedEntries);
        System.out.println("saved map: " + savedMap);

        roles.clear();
        System.out.println("clear values, map: " + users);
        System.out.println("other views after clear: keys=" + keys + ", entries=" + entries);
        System.out.println("key add: " + unsupported(() -> keys.add("new-user")));
        System.out.println("value add: " + unsupported(() -> roles.add("READER")));
        System.out.println("entry add: "
                + unsupported(() -> entries.add(Map.entry("new-user", "READER"))));

        Map<String, String> nullable = new LinkedHashMap<>();
        nullable.put("pending", null);
        System.out.println("null mapping key remove: "
                + nullable.keySet().remove("pending") + ", empty=" + nullable.isEmpty());
        nullable.put("pending", null);
        Map.Entry<String, String> nullPair =
                new AbstractMap.SimpleImmutableEntry<>("pending", null);
        System.out.println("null pair remove: " + nullable.entrySet().remove(nullPair));

        users.put("r1", "VIEWER");
        Map<String, String> readOnly = Collections.unmodifiableMap(users);
        System.out.println("read-only key remove: "
                + unsupported(() -> readOnly.keySet().remove("r1")));
        System.out.println("read-only entry setValue: " + unsupported(() -> {
            for (Map.Entry<String, String> entry : readOnly.entrySet()) {
                entry.setValue("OTHER");
            }
        }));
        users.put("r2", "EDITOR");
        System.out.println("read-only view sees source: " + readOnly);

        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("math", 80);
        Set<Map.Entry<String, Integer>> setOnly =
                Collections.unmodifiableSet(scores.entrySet());
        for (Map.Entry<String, Integer> entry : setOnly) {
            entry.setValue(90);
        }
        System.out.println("set wrapper entry still writes: " + scores);
        Map<String, Integer> protectedMap = Collections.unmodifiableMap(scores);
        System.out.println("map wrapper blocks entry write: " + unsupported(() -> {
            for (Map.Entry<String, Integer> entry : protectedMap.entrySet()) {
                entry.setValue(99);
            }
        }));

        Map<String, List<String>> groups = new LinkedHashMap<>();
        groups.put("team", new ArrayList<>(List.of("a")));
        Map<String, List<String>> groupCopy = new LinkedHashMap<>(groups);
        Map<String, List<String>> groupView = Collections.unmodifiableMap(groups);
        groupView.get("team").add("b");
        System.out.println("nested value changes source: " + groups);
        System.out.println("shallow copy shares value: "
                + (groups.get("team") == groupCopy.get("team")));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 MapWriteThroughDemo.java
java MapWriteThroughDemo
~~~

Có thể dùng JDK 17 trở lên để biên dịch mức release 17 và runtime Java 17 trở lên để chạy. Ví dụ đã được biên dịch ở mức release 17 và chạy thành công bằng OpenJDK 24.0.2.

Stdout chính xác:

~~~text
live keys: [ada, lin, sam, maya]
live values: [READER, ADMIN, READER, REVIEWER]
live entries: [ada=READER, lin=ADMIN, sam=READER, maya=REVIEWER]
remove one value: true, map={lin=ADMIN, sam=READER, maya=REVIEWER}
remove key: true, map={sam=READER, maya=REVIEWER}
remove wrong pair: false, map={sam=READER, maya=REVIEWER}
remove matching pair: true, map={sam=READER}
remove all reader values: true, map={oli=EDITOR}
retain allowed keys: {oli=EDITOR, uma=VIEWER, vic=ADMIN}
iterator remove and setValue: {oli=REVIEWER, vic=ADMIN}
entry predicate removal: {vic=ADMIN}
live map after changes: {vic=OWNER, zoe=EDITOR}
saved keys: [vic]
saved values: [ADMIN]
saved entries: [vic=ADMIN]
saved map: {vic=ADMIN}
clear values, map: {}
other views after clear: keys=[], entries=[]
key add: UnsupportedOperationException
value add: UnsupportedOperationException
entry add: UnsupportedOperationException
null mapping key remove: true, empty=true
null pair remove: true
read-only key remove: UnsupportedOperationException
read-only entry setValue: UnsupportedOperationException
read-only view sees source: {r1=VIEWER, r2=EDITOR}
set wrapper entry still writes: {math=90}
map wrapper blocks entry write: UnsupportedOperationException
nested value changes source: {team=[a, b]}
shallow copy shares value: true
~~~

### 11.1. Các view được lấy trước khi nguồn đổi

Ba view được tạo khi nguồn mới có ba người. Sau khi thêm `maya` và đổi giá trị của `lin`, lần in view đã thấy trạng thái mới. Đây là bằng chứng view không phải bản sao tạo ở thời điểm lấy.

### 11.2. Các phép xóa có đối tượng nhắm đến khác nhau

Xóa một giá trị `READER` chỉ loại một ánh xạ. Xóa khóa `lin` không cần truyền vai trò. Xóa entry `maya=WRONG` không khớp nên giữ nguồn, còn cặp đúng xóa được.

`removeAll` trên view giá trị loại hết các ánh xạ mang vai trò bị chọn; `retainAll` trên view khóa loại các khóa ngoài nhóm cho phép.

### 11.3. Iterator phối hợp xóa và cập nhật

Trong vòng lặp iterator, `uma` bị xóa qua `it.remove`. `oli` được đổi giá trị qua entry hiện tại. Vòng lặp không thêm/xóa qua `users.put` hay `users.remove` ở bên ngoài iterator.

Sau đó, `entrySet.removeIf` loại các entry thỏa điều kiện. Mỗi giai đoạn kết thúc việc duyệt trước khi bước kế tiếp làm thay đổi cấu trúc.

### 11.4. Các bản sao và lớp bọc

Bốn bản lưu giữ dữ liệu lúc nguồn chỉ còn `vic=ADMIN`. Thay `vic` và thêm `zoe` trên nguồn không tự đổi cấu trúc hay entry độc lập đã lưu.

`roles.clear` làm nguồn rỗng và hai view còn lại cũng rỗng. Các lệnh thêm vào view bị từ chối.

Cuối chương trình, hai ví dụ lớp bọc chứng minh giới hạn ở từng tầng: bọc set không tự bọc entry, còn bọc map không tự làm một `List` giá trị trở thành bất biến.

## 12. Thiết kế hàm trả dữ liệu từ map

Trước khi trả một view, hãy xác định bên nhận được phép làm gì:

| Nhu cầu của bên nhận | Lựa chọn có thể phù hợp | Điều cần nêu rõ |
| --- | --- | --- |
| Theo dõi nguồn và được phép xóa ánh xạ theo khóa | `keySet` trực tiếp | Đây là quyền sửa nguồn |
| Chỉ đọc nguồn đang sống | Map/view được bọc chỉ đọc đúng tầng | Nguồn vẫn có thể đổi qua đường khác |
| Giữ danh sách tên tại một thời điểm | Bản sao khóa vào collection phù hợp | Không tự là ảnh chụp nguyên tử nếu nguồn đổi đồng thời |
| Giữ các cặp độc lập về cấu trúc | Sao chép từng entry hoặc sao chép map | Vẫn phải xác định mức sao chép sâu |
| Lọc dữ liệu hiển thị mà không xóa nguồn | Tạo kết quả lọc riêng | Không dùng remove trên live view |
| Cập nhật giá trị trong lúc duyệt nguồn hỗ trợ | Entry iterator và `setValue` | Tôn trọng vòng đời, kiểu và quyền sửa |

Một hàm có tên `getUserNames` nhưng trả thẳng `users.keySet()` có thể hợp lý nếu hợp đồng chủ động trao quyền ấy. Nếu mục tiêu là một ranh giới chỉ đọc, tên hàm không tự bảo vệ dữ liệu.

Cũng đừng bắt mọi `UnsupportedOperationException` rồi bỏ qua để làm một hàm “chạy với mọi map”. Khi chức năng cần xóa/cập nhật, nguồn không hỗ trợ là một khác biệt về hợp đồng cần được xử lý hoặc báo rõ.

## 13. Lỗi thường gặp

| Hiểu nhầm | Vấn đề | Cách sửa theo ý định |
| --- | --- | --- |
| `keySet` là bản sao danh sách khóa | Xóa qua nó có thể xóa nguồn | Chọn view hoặc bản sao có chủ đích |
| `values.remove` chỉ bỏ một giá trị hiển thị | Ánh xạ tương ứng bị xóa | Dùng kết quả hiển thị riêng |
| `values` là set | Bỏ mất số lần xuất hiện của giá trị | Giữ ngữ nghĩa collection có thể lặp |
| `entrySet.remove` chỉ cần khóa khớp | Cặp sai giá trị không bị xóa | Xóa theo khóa hoặc đối chiếu đủ cặp |
| Thêm qua view để cập nhật map | Thao tác không được hỗ trợ | Dùng API map |
| Gán lại biến value trong for-each | Không thay ánh xạ | Dùng `put`, `replace` hoặc entry có quyền sửa |
| Xóa nguồn trực tiếp trong for-each | Phá quy tắc duyệt thông thường | Dùng iterator.remove hoặc removeIf phù hợp |
| Bọc entrySet bằng unmodifiableSet là đủ | Entry có thể còn cho setValue | Bọc đúng map hoặc sao chép entry đúng mục đích |
| Sao chép list entry là sao chép sâu | Entry/phần tử có thể còn gắn nguồn hoặc chia sẻ tham chiếu | Tách từng mức sao chép |
| Không thấy ngoại lệ nên coi là an toàn luồng | Không có bảo đảm như vậy | Thiết kế truy cập theo nguồn và đơn vị nghiệp vụ |

## 14. Thực hành có đáp án

### Bài 1 — View hay bản sao?

Tạo `Set<String> names = map.keySet()` rồi thêm một khóa qua `map.put`. `names` có nhìn thấy khóa mới không? Nếu xóa khóa qua `names` thì nguồn ra sao?

**Đáp án:** view gắn với nguồn nhìn thấy cập nhật qua các lần truy vấn. Với nguồn/view hỗ trợ xóa, xóa qua `names` xóa ánh xạ tương ứng trong map. Iterator đã tạo trước thay đổi vẫn phải tuân hợp đồng duyệt riêng.

### Bài 2 — Giá trị trùng

Nguồn có `{A=OPEN, B=OPEN, C=DONE}`. So sánh ý định của `values().remove("OPEN")` và `values().removeAll(Set.of("OPEN"))`.

**Đáp án:** phép đầu xóa một ánh xạ có giá trị phù hợp; không dùng nó để chỉ định chắc chắn khóa `A` trên mọi map. Phép sau loại các ánh xạ có giá trị thuộc nhóm, nên cả hai giá trị `OPEN` không còn sau khi hoàn tất thành công trên nguồn hỗ trợ. Muốn xóa đúng một khóa, dùng khóa ấy.

### Bài 3 — Đối chiếu đủ entry

Nguồn có `{item=7}`. `entrySet().remove(Map.entry("item", 8))` trả gì và có làm map rỗng không?

**Đáp án:** trên nguồn sửa được thông thường, trả `false` vì giá trị không khớp, nguồn vẫn `{item=7}`. Xóa theo entry đối chiếu cả khóa lẫn giá trị; xóa theo khóa là ý định khác.

### Bài 4 — Gán biến trong vòng lặp

Vì sao `for (String v : map.values()) { v = "NEW"; }` không thay mọi giá trị trong map? Một hướng cập nhật đúng là gì?

**Đáp án:** `v` là biến cục bộ nhận tham chiếu; gán lại nó không sửa ánh xạ. Có thể dùng entry iterator và `setValue` trên nguồn hỗ trợ, hoặc API cập nhật map phù hợp như `replaceAll` với hợp đồng quyền sửa rõ ràng. Không đồng thời sửa cấu trúc ngoài quy tắc duyệt.

### Bài 5 — Lớp bọc thiếu một tầng

API trả `Collections.unmodifiableSet(map.entrySet())` của một map sửa được và tuyên bố bên gọi không thể cập nhật giá trị. Tuyên bố đó có đủ cơ sở không?

**Đáp án:** không. Lớp bọc set chặn thay thành viên set nhưng không tự chặn phương thức sửa của từng entry. Nếu entry nguồn hỗ trợ `setValue` trong lúc duyệt, bên gọi vẫn có thể ghi xuyên. Dùng lớp bọc map phù hợp rồi lấy view của nó, hoặc trả các entry độc lập không sửa được theo mục tiêu dữ liệu.

### Bài 6 — Bản sao entry

Một hàm cần lưu các cặp hiện tại để dùng sau khi map tiếp tục đổi. Chỉ `new ArrayList<>(map.entrySet())` đã chứng minh các entry độc lập chưa?

**Đáp án:** chưa. Collection mới vẫn nhận các đối tượng entry từ nguồn; không dùng vòng đời entry iterator như một bảo đảm cho dữ liệu giữ lâu. Sao chép từng entry ngay trong lúc duyệt, chẳng hạn `new SimpleImmutableEntry<>(entry)`. Đây vẫn là sao chép nông khóa/giá trị; nếu muốn dùng `Map.Entry.copyOf` phải xử lý điều kiện không `null`.

### Bài 7 — null và cờ xóa

Map cho phép `null` và có `pending=null`. `keySet().remove("pending")` trả gì? Vì sao nó khác việc suy từ `map.remove("pending")` trả `null`?

**Đáp án:** xóa khóa qua view trả `true` khi khóa tồn tại và bị xóa. Giá trị cũ do `map.remove` trả có thể là `null` ở cả tình huống vắng ánh xạ và tình huống từng có giá trị `null`. Chọn kiểu kết quả đúng điều bạn cần biết và tuân chính sách nguồn.

### Bài 8 — Không sửa map nhưng sửa giá trị

Một map chỉ đọc chứa giá trị là `ArrayList`. Gọi `readOnly.get("team").add("new")` có thể làm dữ liệu thấy qua nguồn đổi không?

**Đáp án:** có nếu bạn nhận chính danh sách sửa được mà nguồn đang giữ. Chặn thêm/xóa/thay ánh xạ không tự làm đối tượng giá trị bất biến sâu. Cần quyết định sao chép hoặc bọc dữ liệu ở tầng phần tử, đồng thời cân nhắc vòng đời và việc chia sẻ tham chiếu.

Khi tự mở rộng ví dụ, hãy thử mỗi thao tác trên nguồn sửa được, lớp bọc chỉ đọc và một bản sao độc lập. Sau mỗi lần, kiểm tra cả map lẫn các view đã lấy trước đó. Phân biệt được nơi dữ liệu thực sự thay đổi là điều kiện để dùng collection view mà không làm mất ranh giới sở hữu.
