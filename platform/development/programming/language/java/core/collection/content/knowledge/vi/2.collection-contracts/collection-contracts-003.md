# add, remove, clear và quy tắc thao tác tùy chọn

## 1. Hiểu “có phương thức” và “hỗ trợ thao tác”

Một collection là đối tượng quản lý một nhóm phần tử. Khi làm việc với nó, ta thường muốn thêm phần tử, xóa một phần tử hoặc làm rỗng toàn bộ nhóm.

Ba phương thức chung của `Collection<E>` là:

```java
boolean add(E element);
boolean remove(Object element);
void clear();
```

Đây là các chữ ký API để đọc hợp đồng, không phải chương trình chạy độc lập.

Điểm quan trọng là: **một phương thức tồn tại trên giao diện không có nghĩa mọi đối tượng cài đặt giao diện đều hỗ trợ thay đổi tương ứng**.

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Collection<String> editable = new ArrayList<>();
Collection<String> readOnly = List.of("A", "B");

editable.add("C"); // Thêm được.
// readOnly.add("C"); // Biên dịch được, nhưng khi chạy ném UnsupportedOperationException.
```

Hai biến có cùng kiểu khai báo `Collection<String>`. Khác biệt nằm ở đối tượng: đối tượng thứ nhất cho phép thêm; đối tượng thứ hai không cho sửa.

“Thao tác tùy chọn” (optional operation) là thuật ngữ trong hợp đồng Collections Framework. Nó cho phép một lớp cài đặt không hỗ trợ một thao tác thay đổi và báo bằng `UnsupportedOperationException`. Nó không có nghĩa là phương thức được phép biến mất, hoặc người dùng có thể bỏ qua kết quả tùy ý.

Bài này tập trung vào hợp đồng thêm/xóa, các biến thể dễ nhầm và cách sử dụng an toàn trên Java 17. Cần biết biến tham chiếu, generics cơ bản, `List` và `Set`.

Tham khảo nền tảng: [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 2. Mục đích và kết quả của ba thao tác

| Phương thức | Ý định | Kết quả khi hoàn tất bình thường |
| --- | --- | --- |
| `add(e)` | Đưa `e` vào collection theo hợp đồng của nó | `true` nếu collection thay đổi; `false` trong trường hợp phần tử trùng bị từ chối bởi cấu trúc không giữ trùng |
| `remove(o)` | Xóa một lần xuất hiện phù hợp với `o` | `true` nếu xóa được; `false` nếu không có phần tử phù hợp |
| `clear()` | Xóa toàn bộ phần tử | Không trả giá trị; collection rỗng sau khi thao tác thành công |

“Hoàn tất bình thường” nghĩa là lời gọi không ném ngoại lệ. Không suy ra kết quả từ bảng nếu thao tác bị từ chối hoặc đầu vào không hợp lệ.

Đối với một đối tượng mà chương trình được phép thay đổi, giá trị trả về giúp diễn đạt điều đã xảy ra. Ví dụ, thêm vào tập đã có phần tử không làm thay đổi tập; đây không phải lỗi cần ném ngoại lệ.

Bài hướng dẫn [The Collection Interface](https://docs.oracle.com/javase/tutorial/collections/interfaces/collection.html) giải thích cùng ý tưởng: phương thức chung cần dùng được cho nhiều dạng collection, dù cách giữ phần tử khác nhau.

## 3. add(E): thêm phần tử theo hợp đồng của cấu trúc

### 3.1. Danh sách thường giữ cả phần tử trùng

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> names = new ArrayList<>();

boolean first = names.add("An");
boolean second = names.add("An");

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(names);  // [An, An]
```

Mỗi lần `add` thêm một phần tử cuối danh sách. Hai lần thêm cùng chuỗi vẫn tạo hai vị trí, nên cả hai lần đều làm thay đổi danh sách.

Ở đây `true` không có nghĩa “trước đó chưa chứa giá trị này”. Nó có nghĩa collection đã thay đổi do lời gọi.

Hợp đồng thêm cuối của `List.add(E)` được mô tả trong [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#add(E)).

### 3.2. Tập không tạo thêm bản trùng

```java
// Đặt trong một phương thức; cần import java.util.*.
Set<String> codes = new LinkedHashSet<>();

boolean first = codes.add("A");
boolean second = codes.add("A");

System.out.println(first);  // true
System.out.println(second); // false
System.out.println(codes);  // [A]
```

Lần thứ hai không đổi tập. `false` là kết quả hợp lệ, không phải dấu hiệu lỗi hệ thống.

Có thể dùng trực tiếp kết quả khi nghiệp vụ cần biết phần tử vừa được thêm:

```java
// Đặt trong một phương thức; cần import java.util.*.
Set<String> registered = new LinkedHashSet<>();
if (registered.add("ID-01")) {
    System.out.println("New registration");
}
```

Ví dụ một luồng này tránh phải viết riêng `contains` rồi `add`. Tuy nhiên, nó không tự làm `LinkedHashSet` an toàn nhiều luồng.

Với đối tượng do ứng dụng định nghĩa, quy tắc bằng nhau phải đúng. Các tập dựa trên bảng băm còn dựa vào hợp đồng `equals/hashCode`. Tập dựa trên phép so sánh có thêm yêu cầu nhất quán giữa phép so sánh và `equals`. Đây là điều cần xét khi “trùng” khác với việc hai tham chiếu có cùng địa chỉ. [Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 3.3. add không dùng false để biểu diễn mọi lý do thất bại

Không được hiểu `false` là “bất cứ trường hợp nào thêm không được”. Một collection từ chối thêm vì lý do khác phần tử đã có phải báo lỗi phù hợp theo hợp đồng.

Ví dụ:

- Đối tượng không hỗ trợ thêm: `UnsupportedOperationException`.
- Đối tượng không nhận `null`: có thể ném `NullPointerException` khi thêm `null`.
- Có giới hạn kiểu hoặc giá trị: có thể ném `ClassCastException` hoặc `IllegalArgumentException`.
- Không thể thêm lúc này do giới hạn dung lượng: có thể ném `IllegalStateException`.

Với hàng đợi có giới hạn dung lượng, `Queue.offer` thường là API diễn đạt việc không còn chỗ bằng giá trị trả về; `Queue.add` dùng ngoại lệ cho tình huống này. Đừng chuyển cách hiểu của `offer` sang `add`. [Queue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

### 3.4. List.add(index, element) là một phương thức khác

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> values = new ArrayList<>(List.of("A", "C"));
values.add(1, "B");
System.out.println(values); // [A, B, C]
```

`List.add(int, E)` trả `void`, không trả `boolean`. Nó chèn ở vị trí được chỉ định, không thay thế phần tử tại đó. Chỉ số hợp lệ cho chèn là từ `0` đến `size()`, bao gồm `size()` để chèn cuối.

Để thay phần tử mà không thay kích thước danh sách, thao tác là `set(index, element)`. Khả năng hỗ trợ `set` không suy ra khả năng hỗ trợ `add`.

## 4. remove(Object): xóa theo giá trị, một lần xuất hiện

### 4.1. Kết quả true/false và phần tử trùng

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> values =
        new ArrayList<>(List.of("a", "b", "a"));

boolean removed = values.remove("a");
boolean missing = values.remove("missing");

System.out.println(removed); // true
System.out.println(missing); // false
System.out.println(values);  // [b, a]
```

`remove("a")` chỉ xóa **một** lần xuất hiện. Với `List`, đó là lần đầu tiên theo thứ tự danh sách. Nó không xóa tất cả các phần tử bằng `"a"`.

Không tìm thấy phần tử hợp lệ để xóa là trường hợp bình thường đối với một collection hỗ trợ thao tác này. Không cần bắt ngoại lệ chỉ để xử lý “không có phần tử”.

Nếu nghiệp vụ muốn xóa tất cả lần xuất hiện hoặc lọc theo điều kiện, hãy chọn thao tác phù hợp như `removeAll` hoặc `removeIf`, đồng thời kiểm tra hợp đồng sửa đổi của đối tượng. Không gọi `remove` một lần rồi giả định không còn giá trị đó.

### 4.2. Đối số là Object vì đây là thao tác tìm/xóa

Chữ ký là `remove(Object)`, không phải `remove(E)`. Ví dụ sau có thể biên dịch:

```java
// Đặt trong một phương thức; cần import java.util.*.
Collection<String> words = new ArrayList<>(List.of("one"));
System.out.println(words.remove(123)); // false với ArrayList trong ví dụ này.
```

Điều đó không cho phép đưa số nguyên vào `Collection<String>`. Thêm và tìm/xóa có chữ ký khác nhau.

Cũng không nên suy rộng rằng mọi collection đều trả `false` cho một đối số không phù hợp. Một số cấu trúc có thể ném ngoại lệ theo hợp đồng khi đối số sai kiểu hoặc là `null` không được chấp nhận. Hãy xem tài liệu của lớp và thao tác cụ thể.

Đối với dữ liệu có `null`, cần phân biệt:

- Xóa phần tử `null` trong cấu trúc cho phép giữ `null`.
- Gọi `remove(null)` trên cấu trúc cấm `null`.
- Gọi `remove` trên collection vốn không cho sửa.

Đây là các trục hợp đồng khác nhau, không phải cùng một loại lỗi.

## 5. remove(int) và remove(Object) trong List<Integer>

Đây là một trong những lỗi khó nhận ra vì mã vẫn biên dịch.

```java
// Đặt trong một phương thức; cần import java.util.*.
List<Integer> numbers =
        new ArrayList<>(List.of(10, 20, 30));

Integer removedAtIndex = numbers.remove(1);
System.out.println(removedAtIndex); // 20
System.out.println(numbers);       // [10, 30]

boolean removedValue = numbers.remove(Integer.valueOf(10));
System.out.println(removedValue);  // true
System.out.println(numbers);       // [30]
```

Có hai overload:

| Lời gọi | Phương thức được chọn | Ý nghĩa | Kiểu trả về |
| --- | --- | --- | --- |
| `numbers.remove(1)` khi `numbers` là `List<Integer>` | `remove(int index)` | Xóa ở chỉ số `1` | `Integer` |
| `numbers.remove(Integer.valueOf(10))` | `remove(Object value)` | Xóa giá trị bằng `10` | `boolean` |

Chỉ số của `remove(int)` phải nằm từ `0` đến `size() - 1`. Chỉ số ngoài phạm vi có thể gây `IndexOutOfBoundsException`; nó không trả `false` để nói “không có chỉ số này”.

Kiểu khai báo cũng ảnh hưởng tập phương thức có thể chọn:

```java
// Đặt trong một phương thức; cần import java.util.*.
Collection<Integer> values =
        new ArrayList<>(List.of(1, 2, 3));

boolean changed = values.remove(1);
System.out.println(changed); // true
System.out.println(values);  // [2, 3]
```

`Collection` không có `remove(int index)`. Số `1` được boxing thành `Integer` để truyền cho `remove(Object)`. Đối tượng thực tế vẫn là `ArrayList`; nó không làm trình biên dịch tự thêm overload của `List` vào biến khai báo bằng `Collection`.

Một tên `remove` khác nữa là `Queue.remove()` không có đối số: lấy và xóa đầu hàng đợi, có thể ném `NoSuchElementException` khi rỗng. Đó không phải `Collection.remove(Object)`.

Các thao tác theo vị trí của danh sách được giới thiệu trong [The List Interface](https://docs.oracle.com/javase/tutorial/collections/interfaces/list.html).

## 6. clear(): làm rỗng đối tượng đang có

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> tasks =
        new ArrayList<>(List.of("code", "test"));
tasks.clear();

System.out.println(tasks.isEmpty()); // true
System.out.println(tasks.size());    // 0
```

`clear` trả `void`. Vì vậy, `boolean changed = tasks.clear();` không biên dịch.

### 6.1. clear khác với gán biến sang một collection mới

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> original = new ArrayList<>(List.of("A"));
List<String> alias = original;

original.clear();
System.out.println(alias); // []
```

Hai biến tham chiếu cùng đối tượng. `clear` sửa đối tượng đó nên thay đổi được quan sát qua `alias`.

Ngược lại:

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> original = new ArrayList<>(List.of("A"));
List<String> alias = original;

original = new ArrayList<>();
System.out.println(original); // []
System.out.println(alias);    // [A]
```

Phép gán chỉ chuyển biến `original` sang đối tượng mới. Nó không làm rỗng đối tượng cũ.

### 6.2. clear không xóa sâu hoặc xóa an toàn dữ liệu nhạy cảm

Collection bỏ các phần tử khỏi cấu trúc quản lý của nó. Điều này không đồng nghĩa với:

- Gọi phương thức hủy trên từng phần tử.
- Đóng tài nguyên như tệp hoặc kết nối mà phần tử đang giữ.
- Xóa trạng thái của phần tử đang được nơi khác tham chiếu.
- Bảo đảm dữ liệu bị ghi đè khỏi RAM.
- Bảo đảm bộ nhớ được trả lại ngay cho hệ điều hành.
- Bảo đảm dung lượng lưu trữ nội bộ giảm theo một chính sách chung.

Với tài nguyên cần đóng, phải quản lý vòng đời tài nguyên riêng. Với dữ liệu nhạy cảm, không dùng `clear` như bằng chứng đã xóa an toàn.

## 7. Bốn nhóm đối tượng và mức hỗ trợ khác nhau

### 7.1. Collection sửa được

Một `ArrayList` thông thường hỗ trợ thêm, xóa, thay phần tử và làm rỗng. Điều đó không có nghĩa mọi thao tác đều miễn lỗi: chỉ số vẫn phải đúng, đầu vào vẫn phải đáp ứng các điều kiện cần thiết. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 7.2. Danh sách cố định kích thước

```java
// Đặt trong một phương thức; cần import java.util.*.
String[] array = {"red", "blue"};
List<String> fixed = Arrays.asList(array);

fixed.set(0, "green");
System.out.println(Arrays.toString(array)); // [green, blue]
// fixed.add("yellow"); // UnsupportedOperationException.
// fixed.remove("blue"); // UnsupportedOperationException.
// fixed.clear(); // UnsupportedOperationException với dữ liệu không rỗng này.
```

`Arrays.asList` trả danh sách được chống lưng bởi mảng. Nó cho thay phần tử hiện có nhưng không hỗ trợ thay đổi kích thước.

“Cố định kích thước” không đồng nghĩa “không thể thay đổi nội dung”. Sửa phần tử qua danh sách được phản ánh vào mảng và ngược lại. [Arrays.asList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

### 7.3. Đối tượng không cho sửa

`List.of(...)` tạo danh sách không cho sửa và không nhận `null`. Các thao tác thay đổi như thêm, xóa, thay thế hoặc làm rỗng bị từ chối theo hợp đồng factory.

```java
// Đặt trong một phương thức; cần import java.util.List.
List<String> values = List.of("x", "y");
// values.add("z");    // UnsupportedOperationException.
// values.remove("x"); // UnsupportedOperationException.
// values.clear();     // UnsupportedOperationException.
```

Không cho sửa collection không tự làm từng phần tử bất biến. Nếu phần tử là đối tượng có trạng thái thay đổi, code còn giữ tham chiếu đến phần tử vẫn có thể sửa trạng thái ấy.

### 7.4. View không cho sửa

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);

backing.clear();
System.out.println(view); // []
```

`view.clear()` bị từ chối. Nhưng `backing.clear()` vẫn thay đổi dữ liệu mà view đang quan sát. Không được gọi view này là một bản sao độc lập.

Ngược lại, `List.copyOf(backing)` tạo kết quả không phản ánh thay đổi cấu trúc sau đó của collection nguồn; nó vẫn là bản sao nông về các tham chiếu phần tử và không hứa tạo một đối tượng mới trong mọi trường hợp.

Quy tắc view và thao tác được ủy quyền được mô tả tại [Collections.unmodifiableCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableCollection(java.util.Collection)) và các wrapper cùng họ.

## 8. Quy tắc thao tác tùy chọn

### 8.1. Hỗ trợ được xác định theo thao tác, không phải một cờ chung

Một đối tượng có thể cho `set` nhưng không cho `add`. Một view có thể cho `remove` và `clear` để thay đổi cấu trúc nguồn, nhưng không cho `add` vì thiếu thông tin cần thiết để thêm.

Vì vậy, đừng suy luận:

- “Đã `set` được thì chắc `add` được.”
- “`remove` thất bại nên mọi thao tác đều không được hỗ trợ.”
- “Đối tượng là `List` nên chắc chắn xóa được.”
- “Kích thước hiện tại bằng 0 thì gọi `clear` ở đâu cũng được.”

Khi viết lớp collection tùy chỉnh, các lớp khung như [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) và [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) cung cấp cách cài đặt mặc định. Muốn hỗ trợ thay đổi, người cài đặt phải thực hiện các điểm mở rộng tương ứng; chỉ kế thừa lớp khung không bảo đảm mọi thao tác sửa đều hoạt động.

### 8.2. Thao tác không làm thay đổi vẫn có thể bị từ chối

Hợp đồng tổng quát cho phép một thao tác không được hỗ trợ ném `UnsupportedOperationException` ngay cả khi lời gọi cụ thể có vẻ không gây thay đổi. Một số lớp cài đặt có thể kết thúc bình thường nếu không có gì để làm; các factory/wrapper cụ thể có thể đưa ra bảo đảm mạnh hơn.

Ví dụ cần xem hợp đồng cụ thể:

- `clear()` trên collection vốn đã rỗng.
- `remove(x)` khi không có `x`.
- `addAll` với nguồn rỗng.

Không lấy một lần `clear` thành công trên collection rỗng để kết luận nó hỗ trợ xóa phần tử khi có dữ liệu. Không dùng “thử thao tác vô hại” làm cơ chế nhận biết collection sửa được.

### 8.3. Không có phép kiểm tra kiểu chung cho mọi collection sửa được

`instanceof List` hoặc `instanceof Collection` chỉ kiểm tra quan hệ kiểu. Nó không trả lời thao tác `add` có được hỗ trợ không.

Kiểm tra `instanceof ArrayList` cũng không phải thiết kế tổng quát cho API chấp nhận nhiều loại dữ liệu. Thay vào đó:

1. Nêu rõ tiền điều kiện nếu phương thức sửa đối số.
2. Chỉ truyền đối tượng đáp ứng tiền điều kiện đó.
3. Hoặc tạo collection riêng khi phương thức không nên sửa nguồn.

Nếu cần một API chỉ đọc rõ ràng hơn, lựa chọn tham số và thiết kế quyền sở hữu phải thể hiện điều đó; giao diện `Collection` tự nó vẫn chứa các phương thức thay đổi.

## 9. Phân loại lỗi đúng để xử lý đúng

| Hiện tượng | Ý nghĩa cần xét | Không nên kết luận |
| --- | --- | --- |
| `add` vào `Set` trả `false` khi trùng | Không có thay đổi vì phần tử đã tồn tại | Hệ thống bị lỗi |
| `remove(Object)` trả `false` | Không xóa phần tử nào trong lời gọi hợp lệ | Collection chắc chắn không sửa được |
| `UnsupportedOperationException` | Thao tác bị từ chối bởi hợp đồng đối tượng | Đầu vào luôn sai |
| `IndexOutOfBoundsException` từ thao tác theo vị trí | Chỉ số không hợp lệ | Nên thử lại với cùng chỉ số |
| `NullPointerException` | Có thể do collection hoặc đầu vào `null`, tùy điểm gọi | Mọi collection đều cấm `null` |
| `ClassCastException` hoặc `IllegalArgumentException` | Kiểu hoặc giá trị không đáp ứng ràng buộc | Mọi collection có cùng ràng buộc |
| `IllegalStateException` khi thêm vào hàng đợi hạn chế | Không thể thêm trong trạng thái hiện tại | `add` phải trả `false` |

Trình tự các ngoại lệ khi một yêu cầu vi phạm nhiều điều kiện cùng lúc không phải bảo đảm chung. Không viết nghiệp vụ phụ thuộc vào việc “phải kiểm tra chỉ số trước, rồi mới kiểm tra tính sửa được” nếu tài liệu không quy định.

Cũng không bắt `RuntimeException` rồi bỏ qua toàn bộ. Làm như vậy có thể che lỗi hợp đồng, lỗi dữ liệu và lỗi lập trình.

## 10. Sửa trong lúc duyệt và ranh giới nguyên tử

Thêm/xóa cấu trúc trong vòng `for-each` bằng cách gọi trực tiếp collection có thể làm iterator mất hiệu lực. Với nhiều cài đặt như `ArrayList`, ta có thể gặp `ConcurrentModificationException`, nhưng không được dựa vào việc ngoại lệ này luôn xảy ra để bảo đảm tính đúng.

Nếu cần xóa phần tử hiện tại và iterator hỗ trợ, dùng `Iterator.remove` sau `next`:

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> values =
        new ArrayList<>(List.of("keep", "drop", "keep"));

Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    if (iterator.next().equals("drop")) {
        iterator.remove();
    }
}
System.out.println(values); // [keep, keep]
```

`Iterator.remove` cũng là thao tác tùy chọn. Nó chỉ được gọi một lần sau mỗi lần `next`; không phải mọi iterator đều hỗ trợ nó. [Iterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

Đối với một chuỗi gồm nhiều thao tác:

```java
// Ý tưởng minh họa; không có bảo đảm giao dịch chung.
target.clear();
target.add("replacement");
```

Không có hợp đồng chung rằng hai lời gọi là một giao dịch. Nếu lời gọi sau thất bại, đừng giả định phần tử đã xóa sẽ tự khôi phục.

Khi nhiều luồng cùng truy cập, việc một thao tác sửa được hỗ trợ cũng không có nghĩa đối tượng an toàn đồng thời. Cần thiết kế đồng bộ hoặc chọn cấu trúc concurrent phù hợp, không chỉ đổi kiểu khai báo.

## 11. Thiết kế phương thức khi cần thay đổi dữ liệu

### 11.1. Sửa trực tiếp: ghi rõ tác động và tiền điều kiện

```java
// Đoạn khai báo phương thức; cần import java.util.Collection.
// Sửa collection của người gọi; yêu cầu collection hỗ trợ clear.
static void reset(Collection<?> target) {
    target.clear();
}
```

Tên `reset` chưa đủ truyền đạt mọi tác động. Tài liệu cần nói:

- Phương thức sửa đối số, không trả bản sao.
- View hoặc tham chiếu khác có thể quan sát thay đổi.
- Collection phải hỗ trợ `clear`.
- Không được truyền `null` nếu phương thức không có xử lý riêng.

Không cần gọi `isEmpty` trước chỉ để né một ngoại lệ. Cách đó có thể làm API khi thì “thành công” khi thì thất bại theo dữ liệu đầu vào, trong khi yêu cầu sửa được vẫn chưa rõ.

### 11.2. Giữ nguồn: tạo bản sao sửa được

```java
// Đặt trong một phương thức; cần import java.util.*.
List<String> source = List.of("A", "B");
List<String> result = new ArrayList<>(source);

result.remove("A");
result.add("C");

System.out.println(source); // [A, B]
System.out.println(result); // [B, C]
```

Đây là lựa chọn tốt khi đầu vào chỉ cung cấp dữ liệu, không phải vật chứa mà phương thức có quyền sửa.

Tạo `ArrayList` cũng là một quyết định về hợp đồng: nó giữ thứ tự duyệt nguồn và cho phép phần tử trùng. Không dùng bản sao này nếu bài toán đòi giữ nguyên hành vi `Set` hoặc một cấu trúc có thứ tự theo comparator. Hãy chọn kiểu bản sao đúng yêu cầu.

### 11.3. Không dùng bắt ngoại lệ làm chiến lược sửa rồi sao chép mù

Tránh quy trình “thử một chuỗi thay đổi, nếu có `UnsupportedOperationException` thì sao chép và chạy lại” mà không biết trạng thái đã thay đổi đến đâu. Một bước trước có thể đã thành công.

Việc chọn sửa tại chỗ hay tạo kết quả mới nên là quyết định của hợp đồng phương thức. Bắt `UnsupportedOperationException` có thể phù hợp tại ranh giới hiển thị lỗi hoặc trong chương trình học để quan sát hành vi; nó không thay thế thiết kế quyền sở hữu.

## 12. Chương trình hoàn chỉnh

Lưu thành `OptionalOperationsDemo.java`. Chương trình minh họa các collection cụ thể nên kết quả có thể đối chiếu chính xác.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class OptionalOperationsDemo {
    private static void showUnsupported(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": completed");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> list = new ArrayList<>();
        System.out.println("List add A: " + list.add("A"));
        System.out.println("List add A again: " + list.add("A"));
        list.add("B");
        System.out.println("List: " + list);

        Set<String> set = new LinkedHashSet<>();
        System.out.println("Set add A: " + set.add("A"));
        System.out.println("Set add A again: " + set.add("A"));
        System.out.println("Set: " + set);

        Collection<String> values =
                new ArrayList<>(List.of("a", "b", "a"));
        System.out.println("Remove a: " + values.remove("a"));
        System.out.println("After remove: " + values);
        System.out.println("Remove missing: " + values.remove("missing"));
        values.clear();
        System.out.println("After clear: " + values);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        System.out.println("remove(1): " + numbers.remove(1));
        System.out.println("Numbers: " + numbers);
        System.out.println("remove(Integer 10): "
                + numbers.remove(Integer.valueOf(10)));
        System.out.println("Numbers: " + numbers);

        Collection<Integer> numberCollection =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("Collection remove(1): "
                + numberCollection.remove(1));
        System.out.println("Collection numbers: " + numberCollection);

        String[] array = {"red", "blue"};
        List<String> fixed = Arrays.asList(array);
        System.out.println("Fixed set old: " + fixed.set(0, "green"));
        System.out.println("Array: " + Arrays.toString(array));
        showUnsupported("Fixed add", () -> fixed.add("yellow"));
        showUnsupported("Fixed remove", () -> fixed.remove("blue"));
        showUnsupported("Fixed clear", fixed::clear);

        List<String> readOnly = List.of("x", "y");
        showUnsupported("Read-only add", () -> readOnly.add("z"));
        showUnsupported("Read-only remove", () -> readOnly.remove("x"));
        showUnsupported("Read-only clear", readOnly::clear);

        List<String> backing = new ArrayList<>(List.of("secret"));
        List<String> view = Collections.unmodifiableList(backing);
        List<String> copy = List.copyOf(backing);
        backing.clear();
        System.out.println("View after backing clear: " + view);
        System.out.println("Copy after backing clear: " + copy);

        List<String> editable = new ArrayList<>(readOnly);
        editable.add("z");
        editable.remove("x");
        System.out.println("Editable copy: " + editable);
        System.out.println("Original read-only: " + readOnly);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OptionalOperationsDemo.java
java OptionalOperationsDemo
```

Cần JDK có `javac`. Mã đã được biên dịch bằng `--release 17` và chạy trên một JDK mới hơn; không sử dụng API chỉ có sau Java 17.

Stdout:

```text
List add A: true
List add A again: true
List: [A, A, B]
Set add A: true
Set add A again: false
Set: [A]
Remove a: true
After remove: [b, a]
Remove missing: false
After clear: []
remove(1): 20
Numbers: [10, 30]
remove(Integer 10): true
Numbers: [30]
Collection remove(1): true
Collection numbers: [2, 3]
Fixed set old: red
Array: [green, blue]
Fixed add: UnsupportedOperationException
Fixed remove: UnsupportedOperationException
Fixed clear: UnsupportedOperationException
Read-only add: UnsupportedOperationException
Read-only remove: UnsupportedOperationException
Read-only clear: UnsupportedOperationException
View after backing clear: []
Copy after backing clear: [secret]
Editable copy: [y, z]
Original read-only: [x, y]
```

### Đọc kết quả theo từng cơ chế

- Hai lần thêm `A` vào `ArrayList` đều thay đổi dữ liệu, còn lần hai trong `LinkedHashSet` trả `false`.
- Collection chứa `a, b, a` chỉ mất lần `a` đầu tiên. Xóa `missing` trả `false`.
- `clear` làm collection rỗng; không có giá trị trả về để in.
- `List<Integer>.remove(1)` xóa phần tử chỉ số `1` và trả `20`.
- `remove(Integer.valueOf(10))` xóa theo giá trị và trả `true`.
- Qua biến `Collection<Integer>`, `remove(1)` là xóa giá trị `1`.
- `Arrays.asList` cho `set`, thay đổi mảng nguồn, nhưng từ chối các thao tác thay kích thước được thực hiện.
- `List.of` từ chối các thao tác thay đổi trong ví dụ.
- View không cho sửa vẫn thấy nguồn bị `clear`. Bản `List.copyOf` không phản ánh thay đổi cấu trúc ấy.
- Bản sao `ArrayList` được sửa độc lập về cấu trúc với danh sách nguồn không cho sửa.

Hàm `showUnsupported` chỉ phục vụ minh họa: nó in ngoại lệ dự kiến thay vì làm chương trình dừng. Nó không bắt mọi loại ngoại lệ và không đưa ra chính sách xử lý lỗi sản xuất.

## 13. Các lỗi cần nhận ra khi đọc mã

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `add` trả `true` nghĩa là giá trị chưa tồn tại | Diễn giải sai đối với `List` | Đọc kết quả theo “collection có thay đổi không” |
| Cho rằng `remove` xóa hết phần tử trùng | Dữ liệu trùng còn lại | Chọn thao tác xóa toàn bộ hoặc điều kiện phù hợp |
| Dùng `remove(1)` để xóa số `1` trong `List<Integer>` | Xóa nhầm phần tử ở chỉ số `1` | Truyền `Integer.valueOf(1)` khi muốn xóa giá trị |
| Coi `clear` trả `boolean` | Không biên dịch | Gọi `clear` như một thao tác `void` |
| Coi `Arrays.asList` là `ArrayList` sửa kích thước | Gặp `UnsupportedOperationException` | Tạo `new ArrayList<>(...)` nếu cần thay kích thước |
| Coi view không cho sửa là bản sao | Thấy dữ liệu nguồn thay đổi ngoài dự kiến | Chọn copy hoặc view có chủ đích |
| Thử `clear` trên collection rỗng để nhận biết tính sửa được | Kết luận không có bảo đảm | Dựa vào hợp đồng cụ thể |
| Bắt mọi ngoại lệ rồi tiếp tục | Che dữ liệu sai hoặc thao tác chưa hoàn tất | Phân loại lỗi và giữ trạng thái rõ ràng |
| Sửa collection trực tiếp trong `for-each` | Iterator có thể mất hiệu lực | Dùng cơ chế xóa được hỗ trợ khi duyệt |
| Dùng `clear` như xóa an toàn bí mật | Giả định bảo mật không đúng | Quản lý dữ liệu nhạy cảm bằng cơ chế riêng |

## 14. Tự kiểm tra và thực hành

### Câu hỏi

1. Vì sao hai lời gọi `add("A")` vào `List` có thể đều trả `true`?
2. `Set.add` trả `false` khi trùng có phải lỗi không?
3. `remove(Object)` xóa bao nhiêu lần xuất hiện?
4. `List<Integer>.remove(1)` khác `Collection<Integer>.remove(1)` thế nào?
5. Vì sao `Arrays.asList` cho `set` nhưng không cho thêm phần tử?
6. Gọi `clear` thành công trên dữ liệu rỗng có chứng minh đối tượng xóa được khi có dữ liệu không?
7. Tại sao biến `Collection` vẫn có thể trỏ tới một đối tượng không cho sửa?
8. View không cho sửa có tiếp tục quan sát thay đổi từ collection nguồn không?
9. `clear` có đóng tài nguyên hoặc xóa an toàn dữ liệu khỏi bộ nhớ không?
10. Một phương thức sửa collection nhận vào cần công bố điều gì?

### Bài tập

- Chạy chương trình đầy đủ và giải thích mỗi dòng `true/false` bằng trạng thái trước–sau.
- Thêm một lần `remove("A")` vào danh sách chứa `A, A, B`; kiểm chứng vẫn còn một `A`.
- Đổi ví dụ số nguyên để xóa **giá trị** `1` trong danh sách `10, 20, 1`, không xóa theo chỉ số.
- Tạo danh sách mới bằng `new ArrayList<>(Arrays.asList(...))` và kiểm chứng thêm/xóa được mà không đổi kích thước mảng gốc.
- Viết một phương thức tạo bản sao, xóa phần tử không mong muốn rồi trả kết quả; kiểm tra nguồn không bị sửa.
- Đối chiếu hợp đồng của ba nguồn `new ArrayList<>()`, `Arrays.asList(...)` và `List.of(...)`, không dùng kết quả một thao tác rỗng làm phép thử tính sửa được.

### Gợi ý đối chiếu

1. Mỗi lần thêm tạo một vị trí mới nên danh sách thay đổi.
2. Không; tập đã chứa phần tử và không tạo bản trùng.
3. Một lần; `List` xóa lần phù hợp đầu tiên.
4. Với `List` chọn overload theo chỉ số; với `Collection` chỉ có overload theo đối tượng.
5. Nó là view của mảng có độ dài cố định; thay nội dung phần tử không đổi độ dài.
6. Không; quy tắc thao tác không gây thay đổi không cung cấp bảo đảm đó.
7. Kiểu khai báo cho biết API, còn hợp đồng đối tượng xác định mức hỗ trợ.
8. Có, nếu đó là view sống của nguồn như wrapper được minh họa.
9. Không; đó là các trách nhiệm riêng.
10. Tác động lên đối số, thao tác phải được hỗ trợ, giới hạn đầu vào, quan hệ với view/tham chiếu khác và hành vi lỗi cần biết.
