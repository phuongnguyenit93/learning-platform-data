# Các phương thức tối thiểu và hợp đồng thao tác tùy chọn

## Hiểu đúng chữ “tối thiểu” khi tự cài đặt collection

Khi tự cài đặt một collection, câu hỏi đầu tiên thường là: “Phải viết bao nhiêu phương thức?”. Câu trả lời phụ thuộc lớp nền và khả năng muốn cung cấp. Một danh sách chỉ đọc có điểm khởi đầu khác một danh sách thay đổi được kích thước; một map có các đường cập nhật qua view mà một collection thông thường không có.

Java Collections Framework cung cấp các lớp cài đặt khung, còn gọi là `skeletal implementation`: `AbstractCollection`, `AbstractList`, `AbstractSequentialList`, `AbstractSet`, `AbstractQueue` và `AbstractMap`. Ta viết một nhóm phương thức nền tảng, còn lớp khung xây dựng nhiều phương thức khác trên nhóm đó.

Mối quan hệ cần hiểu là:

~~~text
Hợp đồng của interface
    -> Lớp khung chọn một cách cài đặt chung
        -> Phương thức nền tảng của lớp con
            -> Hành vi của các phương thức kế thừa
~~~

Ví dụ, một `AbstractList` có thể tạo iterator từ `get(int)` và `size()`. Nếu lớp con cài `remove(int)`, thao tác xóa qua iterator kế thừa có thêm một đường thực hiện. Nếu `remove(int)` không được hỗ trợ, iterator vẫn duyệt được nhưng không vì thế mà xóa được.

Có hai mức tối thiểu khác nhau:

- **Đủ để trở thành lớp cụ thể:** các phương thức `abstract` cần có phần cài đặt, để trình biên dịch chấp nhận.
- **Đủ để thực hiện đúng lời hứa:** mọi phương thức đọc, ghi, iterator và view phải tuân thủ hợp đồng đã công bố, kể cả các phương thức kế thừa.

Mức thứ hai mới quyết định lớp có dùng đúng như một `List`, `Set`, `Queue` hay `Map` hay không. Biên dịch thành công không chứng minh không có phần tử trùng trong set, không làm map view trở thành bản sao hợp lệ, và không tự tạo đồng bộ cho nhiều luồng.

Bài dùng API Java 17 làm mốc. Khi nâng phiên bản Java, cần xem lại các phương thức interface mới và các phần cài đặt mặc định mới có ảnh hưởng đến lớp của mình hay không.

## Thao tác tùy chọn vẫn có hợp đồng

Một phương thức được ghi `optional operation` không có nghĩa người cài đặt được bỏ phương thức khỏi đối tượng hoặc tùy ý trả kết quả. Nó có nghĩa một triển khai có quyền không hỗ trợ khả năng đó; khi lời gọi yêu cầu khả năng không được hỗ trợ, ngoại lệ phù hợp là `UnsupportedOperationException`.

Ví dụ, một danh sách có kích thước cố định có thể hỗ trợ `set` nhưng không hỗ trợ `add` hoặc `remove`. Nó vẫn là một `List`. Một danh sách chỉ đọc có thể không hỗ trợ cả ba. Các lựa chọn này là một phần của hợp đồng của từng triển khai, không suy ra chỉ từ kiểu `List<E>`.

Cần phân biệt:

| Kết quả hoặc ngoại lệ | Ý nghĩa điển hình |
| --- | --- |
| `UnsupportedOperationException` | Triển khai không hỗ trợ thao tác được yêu cầu |
| `false` từ `Set.add` | Phần tử đã có nên set không đổi |
| `false` từ `Queue.offer` | Lần thêm không thực hiện được ngay, chẳng hạn queue đã đầy |
| `IndexOutOfBoundsException` | Chỉ số không thuộc miền hợp lệ |
| `IllegalStateException` từ iterator hỗ trợ xóa | Lời gọi xóa không hợp lệ với trạng thái duyệt hiện tại |
| `NoSuchElementException` từ `Iterator.next` | Đã hết phần tử |
| `NullPointerException` | Đối số hoặc phần tử `null` không hợp lệ với hợp đồng đang áp dụng |

Một `add` không được hỗ trợ không nên giả vờ trả `false` cho mọi phần tử. Một `set` không được hỗ trợ không nên im lặng bỏ qua rồi trả `null`. Những kết quả đó làm bên gọi hiểu sai rằng thao tác đã được xử lý theo hợp đồng.

Quy tắc thao tác tùy chọn và các hạn chế phần tử được nêu trong [Collection của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). Tên phương thức giống nhau không bảo đảm mọi triển khai có cùng khả năng ghi.

### Không làm thay đổi dữ liệu có thể không ném ngoại lệ

Đây là điểm dễ làm một bài kiểm tra khả năng bị sai:

~~~java
collection.addAll(List.of());
~~~

Collection không hỗ trợ thêm có thể ném `UnsupportedOperationException`, nhưng với hợp đồng tổng quát, một lời gọi không có tác động cũng có thể kết thúc bình thường. Tương tự, xóa phần tử không tồn tại có thể trả `false`, dù xóa phần tử đang có sẽ ném ngoại lệ.

Vì thế:

- `addAll` với tập rỗng thành công không chứng minh `add` được hỗ trợ.
- `remove` trả `false` cho giá trị không có không chứng minh xóa giá trị đang có sẽ thành công.
- `removeIf` với điều kiện luôn `false` không chứng minh iterator hỗ trợ xóa.
- Một lần gọi `putAll` với map rỗng không chứng minh map có thể thêm ánh xạ mới.

Đừng dùng các lời gọi không làm gì để dò khả năng, rồi dựa vào kết quả đó quyết định có thể ghi dữ liệu thật. Collections Framework không có một phương thức chung như `supportsAdd()`. Bên sử dụng cần biết hợp đồng của đối tượng được nhận hoặc thiết kế đầu vào với khả năng rõ ràng.

Một triển khai có thể đưa ra bảo đảm mạnh hơn. Chẳng hạn, các list tạo bằng `List.of` công bố rằng các phương thức thay đổi đều ném `UnsupportedOperationException`. Không lấy bảo đảm riêng ấy áp ngược cho mọi lớp con tối thiểu của `AbstractList`. Xem phần danh sách không sửa được trong [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## Chọn lớp khung và nhóm phương thức gốc

Bảng dưới đây là điểm khởi đầu, không thay cho việc đọc hợp đồng của mọi thao tác lớp muốn hỗ trợ.

| Lớp khung | Các phương thức nền tảng cần cung cấp | Để mở thêm khả năng ghi |
| --- | --- | --- |
| `AbstractCollection<E>` | `iterator()` và `size()` | Cài `add(E)` để thêm; iterator hỗ trợ `remove()` để nhiều thao tác xóa kế thừa dùng được |
| `AbstractSet<E>` | `iterator()` và `size()`, đồng thời bảo đảm không trùng theo hợp đồng set | Cài thêm/xóa mà vẫn giữ tính duy nhất |
| `AbstractList<E>` | `get(int)` và `size()` cho danh sách chỉ đọc | `set(int,E)` để thay phần tử; `add(int,E)` và `remove(int)` để đổi kích thước |
| `AbstractSequentialList<E>` | `listIterator(int)` và `size()` | Iterator hai chiều hỗ trợ `set`; thêm `add/remove` nếu đổi kích thước |
| `AbstractQueue<E>` | `offer(E)`, `peek()`, `poll()`, `iterator()` và `size()` | Quyết định riêng khả năng xóa qua iterator, xóa theo giá trị và các thao tác hàng loạt |
| `AbstractMap<K,V>` | `entrySet()` cho map chỉ đọc | `put(K,V)` để ghi; iterator của `entrySet` hỗ trợ xóa để các đường xóa kế thừa dùng được; `Entry.setValue` nếu hỗ trợ cập nhật qua entry |

Nếu cài trực tiếp một interface, phải cung cấp mọi phương thức trừ những phần đã được thừa kế hợp lệ, chẳng hạn các phương thức `default`. Lớp khung giảm số phương thức phải viết bằng cách chọn sẵn thuật toán chung.

Nhưng việc viết ít cũng tạo sự phụ thuộc: một sai sót trong `iterator` hoặc `get` có thể làm sai đồng thời `contains`, `toArray`, `equals`, `toString` và nhiều thao tác khác.

## AbstractCollection: đọc dựa trên iterator, xóa thường cũng dựa trên iterator

Với `AbstractCollection`, `size()` cho số lượng còn `iterator()` cho cách đi qua dữ liệu. Lớp khung có thể dùng iterator để tìm một giá trị, tạo mảng hoặc xây chuỗi hiển thị.

Đối với collection chỉ đọc, iterator vẫn phải:

- Trả `hasNext()` nhất quán với việc còn phần tử.
- Trả đúng phần tử tiếp theo từ `next()`.
- Ném `NoSuchElementException` khi `next()` được gọi sau phần tử cuối.
- Tuân thủ thứ tự nếu collection công bố thứ tự.
- Không để lộ một đường xóa ngoài ý muốn.

`Iterator.remove` có phần cài đặt mặc định ném `UnsupportedOperationException`. Vì vậy, một iterator chỉ viết `hasNext` và `next` có thể duyệt nhưng không hỗ trợ xóa. Xem [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Điểm cuối quan trọng với việc đóng gói. Nếu `iterator()` trả trực tiếp iterator của một `ArrayList` nội bộ, bên gọi có thể xóa qua iterator dù `add` của collection đã bị chặn. Muốn không cho sửa qua collection, phải kiểm tra cả đường iterator.

### Chuỗi gọi của thao tác xóa

Hình dung đường thực hiện thường gặp của phần cài đặt khung:

~~~text
remove(value)
    -> tìm value bằng iterator
    -> iterator.remove() nếu tìm thấy

clear()
    -> duyệt bằng iterator
    -> iterator.remove() cho từng phần tử

removeIf(predicate) mặc định
    -> duyệt bằng iterator
    -> iterator.remove() cho các phần tử được chọn
~~~

Nếu iterator không hỗ trợ xóa, `remove(value)` có thể chỉ thất bại lúc tìm thấy giá trị. Nếu không tìm thấy, nó trả `false` mà chưa cần gọi `remove` trên iterator.

Đây là lý do phải kiểm tra cả đầu vào có tác động lẫn không có tác động. Một lớp chỉ được thử với collection rỗng có thể trông như hỗ trợ nhiều thao tác, nhưng thất bại khi dữ liệu thật xuất hiện.

Đối với collection sửa được đầy đủ theo mô hình này, cài thêm `add(E)` và hỗ trợ `Iterator.remove` là nhóm mở rộng quan trọng. Có thể ghi đè các phương thức khác khi có thuật toán hiệu quả hơn, nhưng phải giữ cùng kết quả, ngoại lệ và tác động đã cam kết. Xem [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html).

## AbstractList: đọc, thay thế và đổi kích thước là ba khả năng khác nhau

`AbstractList` xây dựng các thao tác theo vị trí. Đối với dữ liệu hỗ trợ truy cập chỉ số hiệu quả, `get(int)` và `size()` tạo được một danh sách đọc được, có iterator và nhiều thuật toán sẵn.

Có ba mức hữu ích:

| Loại danh sách | `get/size` | `set` | `add/remove` |
| --- | --- | --- | --- |
| Chỉ đọc | Có | Không | Không |
| Kích thước cố định, thay phần tử được | Có | Có | Không |
| Thay đổi kích thước được | Có | Có nếu công bố hỗ trợ thay thế | Có theo khả năng công bố |

Khả năng thêm/xóa và khả năng thay thế không phải một cờ duy nhất “mutable”. Khi thiết kế một lớp chuyên biệt, hãy mô tả từng nhóm thao tác chính.

### Vì sao ghi đè add(E) chưa đủ?

`AbstractList.add(E)` kế thừa gọi `add(size(), e)`. Nếu muốn tích hợp với phần cài đặt khung, điểm mở đúng thường là `add(int,E)`.

Nếu chỉ viết `add(E)` mà để `add(int,E)` không được hỗ trợ, các đường thêm theo chỉ số hoặc `ListIterator.add` có thể vẫn ném `UnsupportedOperationException`. Khi ấy lớp chỉ hỗ trợ một tập thao tác hẹp hơn; không được mô tả rằng “thêm phần tử ở mọi vị trí”.

Tương tự, `remove(int)` và `remove(Object)` là hai overload khác nhau. Đối với `List<Integer>`:

~~~java
numbers.remove(1);                 // Xóa tại chỉ số 1.
numbers.remove(Integer.valueOf(1)); // Xóa giá trị 1 đầu tiên nếu có.
~~~

Đây là minh họa chọn overload, không phải một chương trình độc lập. Khi cài đặt và kiểm thử, phải phân biệt đúng loại đối số để không thử nhầm khả năng.

### Iterator kế thừa mở rộng từ phương thức của list

Với phần cài đặt của `AbstractList`, có thể hình dung:

~~~text
Iterator.next()          -> get(index)
Iterator.remove()        -> remove(index)

ListIterator.set(value)  -> set(index, value)
ListIterator.add(value)  -> add(index, value)
~~~

Điều đó không bỏ qua quy tắc trạng thái của iterator. Chẳng hạn, iterator hỗ trợ xóa vẫn không cho xóa trước khi `next` trả phần tử, và không cho xóa hai lần sau cùng một `next`.

`ListIterator` có con trỏ nằm giữa các phần tử. `set/remove` tác động đến phần tử được `next` hoặc `previous` trả gần nhất, không phải tùy ý phần tử tại một chỉ số con trỏ đang hiển thị. Sau các thao tác làm mất điều kiện ấy, phải duyệt lại theo hợp đồng trước khi gọi tiếp. Xem [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### set còn ảnh hưởng replaceAll và sort

Danh sách kích thước cố định có thể sắp xếp và thay toàn bộ giá trị mà không thêm hoặc xóa phần tử. Các phần cài đặt mặc định liên quan của `List` dùng khả năng thay thế qua list iterator.

Vì vậy, không hỗ trợ đổi kích thước không đồng nghĩa không thể `sort`. Ngược lại, hỗ trợ `add/remove` nhưng không hỗ trợ `set` cũng không tự làm mọi thuật toán thay thế hoạt động.

Trong ví dụ phía dưới, `FixedList` chỉ bổ sung `set` vào `get/size`. Nó sắp xếp, chuyển chữ thường và thay qua `ListIterator.set` thành công; `add` và `remove(int)` vẫn không được hỗ trợ.

### modCount khi dùng iterator và subList kế thừa

`AbstractList` cung cấp `modCount` cho việc phát hiện thay đổi cấu trúc trong iterator/list iterator kế thừa. Với lớp muốn dùng cơ chế ấy, các phương thức thay đổi cấu trúc phải cập nhật `modCount` đúng. Một lần thêm hoặc xóa đơn lẻ không tăng quá một lần.

Trong ví dụ, thêm/xóa thành công tăng `modCount`; `set` chỉ thay phần tử nên không tăng cho mô hình danh sách này. Nếu lời gọi thất bại trước khi thay đổi dữ liệu, không tăng như thể đã thay đổi.

Không chỉ dựa vào việc kho chứa nội bộ là `ArrayList`. Iterator do `AbstractList` ngoài tạo theo dõi trạng thái lớp ngoài; một bộ đếm riêng trong `ArrayList` bên trong không tự thay thế bộ đếm đó.

Việc dùng `modCount` cho phát hiện thay đổi là lựa chọn của lớp con theo tài liệu [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html). Nó không là khóa, không làm lớp an toàn cho nhiều luồng và không phải cách xác minh chương trình đồng thời đúng.

`subList` là view, không phải bản sao tách rời. Nếu cho phép sửa qua view, thay đổi phải đi vào list gốc theo hợp đồng. Khi sửa cấu trúc list gốc qua đường khác trong lúc đang dùng view, không được tiếp tục giả định view còn hợp lệ.

## AbstractSequentialList: đảo chiều phụ thuộc

Nếu kho dữ liệu đi theo nút liên kết, việc liên tục gọi `get(0)`, `get(1)`, `get(2)` có thể phải đi lại từ đầu và trở nên đắt.

`AbstractSequentialList` đi theo hướng ngược với `AbstractList`: cung cấp `listIterator(int)` rồi xây các thao tác theo vị trí trên iterator đó. Nhóm nền tảng là `listIterator(int)` và `size()`. Xem [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html).

Nếu tự viết một `ListIterator` chỉ đọc, vẫn phải có phần thân cho mọi phương thức trừu tượng trong `ListIterator`:

- Duyệt tới/lùi: `hasNext`, `next`, `hasPrevious`, `previous`.
- Chỉ số con trỏ: `nextIndex`, `previousIndex`.
- Các thao tác tùy chọn `add`, `set`, `remove`: nếu không hỗ trợ thì cài để ném `UnsupportedOperationException`.

Điểm cần lưu ý là `ListIterator` khai báo lại các thao tác này; không nên nhìn phần mặc định của `Iterator.remove` rồi nghĩ mọi lớp cài trực tiếp `ListIterator` có thể bỏ hết chúng.

Muốn hỗ trợ thay phần tử, iterator cần `set` đúng. Muốn đổi kích thước, iterator cần `add/remove` đúng, gồm cả việc chỉnh con trỏ và trạng thái phần tử vừa trả. Khi đó nhiều thao tác theo chỉ số kế thừa mới có nền tảng thích hợp để hoạt động.

Lựa chọn lớp khung không chỉ để ít mã: nó còn chọn đường đi của thuật toán. `RandomAccess` là dấu hiệu cho thuật toán bên ngoài về kiểu truy cập, không tự làm `get` nhanh lên và không nên gắn vào một danh sách liên kết chỉ để có vẻ đầy đủ.

## AbstractSet: lớp khung không tự loại phần tử trùng

`AbstractSet` dùng nhóm phương thức nền tảng tương tự `AbstractCollection`, đồng thời cung cấp ngữ nghĩa `equals/hashCode` của set. Nhưng nó không biến bất kỳ kho lưu trữ nào thành set đúng.

Nếu lớp con giữ `[A, A]` trong một list nội bộ rồi trả iterator của list đó và `size = 2`, việc chỉ đổi tên lớp thành `CustomSet` không sửa được vi phạm. Mọi điểm nhập dữ liệu, gồm hàm tạo và `add`, phải duy trì tính duy nhất.

Đoạn minh họa dưới đây là một hướng ủy quyền cho phần thêm, nếu kho nội bộ vốn đã có ngữ nghĩa set:

~~~java
@Override
public boolean add(E value) {
    return backingSet.add(value);
}
~~~

Nếu kho nội bộ là list, phải tự kiểm tra và giữ bất biến phù hợp; không có bảo đảm loại trùng nào xuất hiện chỉ nhờ `extends AbstractSet`.

Cần giữ đúng tính bằng nhau giữa các set khác triển khai: thứ tự duyệt khác nhau không làm hai set có cùng phần tử trở thành khác nhau. `hashCode` cũng phải theo hợp đồng set. Ngược lại, list so sánh theo thứ tự. Một collection dạng “túi” cho phép trùng không nên tự nhận ngữ nghĩa list hoặc set chỉ vì muốn tái dùng `equals`. Xem [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

Một số thao tác như `removeAll` có thể chọn đường thực hiện khác dựa trên kích thước hai phía. Vì vậy, không kiểm thử đúng một kích thước rồi suy ra các khả năng xóa đã nhất quán. Đối chiếu hợp đồng công bố với cả phương thức xóa trực tiếp và xóa qua iterator.

## AbstractQueue: một nhóm phương thức khác với Collection thông thường

`AbstractQueue` yêu cầu nền tảng `offer`, `poll`, `peek`, `iterator` và `size`. Nó phù hợp với queue không chấp nhận phần tử `null`.

Lý do `null` quan trọng: `poll/peek` dùng `null` làm kết quả báo rỗng. Nếu cho phép chèn `null` như phần tử thật, các phần cài đặt kế thừa không còn phân biệt được phần tử thật và tín hiệu rỗng.

Các phương thức kế thừa tạo hai cách báo kết quả:

| Phương thức nền | Phương thức xây trên nó | Khác biệt khi không có kết quả |
| --- | --- | --- |
| `offer(e)` | `add(e)` | `offer` trả `false` vì đầy; `add` ném `IllegalStateException` |
| `poll()` | `remove()` | `poll` trả `null` khi rỗng; `remove` ném `NoSuchElementException` |
| `peek()` | `element()` | `peek` trả `null` khi rỗng; `element` ném `NoSuchElementException` |

Đây là hợp đồng của [AbstractQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html). Một queue đã đầy vẫn có hỗ trợ thêm khi có chỗ trở lại; không dùng `UnsupportedOperationException` để diễn đạt trạng thái đầy tạm thời.

### remove() khác remove(Object)

`remove()` của queue lấy phần tử đầu. `remove(Object)` tìm và xóa một giá trị cụ thể.

Một queue có thể hỗ trợ lấy đầu bằng `poll` nhưng không cho iterator xóa phần tử bất kỳ. Với phần cài đặt khung, `remove()` vẫn hoạt động qua `poll`; `remove(existingValue)` có thể ném `UnsupportedOperationException` do cần `Iterator.remove`.

Khả năng `clear` cũng phụ thuộc lớp khung. `AbstractCollection.clear` dựa trên xóa qua iterator, còn `AbstractQueue.clear` gọi `poll` lặp đến khi rỗng. Do đó trong ví dụ, queue không hỗ trợ iterator xóa nhưng `clear` vẫn chạy được.

Đây là một lý do thực tế để đọc phần “Implementation Requirements” của đúng lớp được kế thừa, thay vì áp một mô hình gọi chung cho mọi collection.

## AbstractMap: entrySet là nền tảng và cũng là đường ghi

`Map` không phải kiểu con của `Collection`. Với `AbstractMap`, điểm nền tảng là `entrySet()`: một set view biểu diễn các ánh xạ.

Từ đó, lớp khung có thể suy ra `size`, tìm khóa, đọc giá trị, so sánh map và tạo các view khóa hoặc giá trị. Một map chỉ cần `entrySet` để bắt đầu đọc được, nhưng chất lượng của view này quyết định phần lớn hành vi còn lại.

Đối với map sửa được theo cách cài đặt khung, `put` là điểm mở thêm/cập nhật và iterator của `entrySet` cần hỗ trợ xóa nếu muốn các đường xóa kế thừa hoạt động. Xem [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

### Không trả snapshot nếu hợp đồng đòi view sống

Giả sử map còn có thể được cập nhật. Nếu `entrySet()` luôn tạo một bản sao rời rạc, một view đã lấy trước đó sẽ không phản ánh thay đổi map theo hợp đồng.

Hơn nữa, `entrySet().iterator().remove()` nếu được hỗ trợ phải xóa ánh xạ trong map gốc, không chỉ xóa một phần tử trong bản sao tạm. View `keySet` và `values` cũng có ý nghĩa liên kết với map.

Trong ví dụ, map sao chép nguồn một lần trong hàm tạo và giữ bản sao đó không sửa được. `entrySet` trả view của chính dữ liệu map đang sở hữu; đó không phải việc tạo snapshot mới ở mỗi lần gọi.

### Chặn put chưa đủ để làm map chỉ đọc

Một map có nhiều đường có thể thay đổi:

~~~text
put / putAll / remove / clear
keySet().remove(...)
values().remove(...)
entrySet().iterator().remove()
entrySet().iterator().next().setValue(...)
replaceAll(...) và các phương thức cập nhật mặc định khác
~~~

Nếu chỉ để `put` ném `UnsupportedOperationException` nhưng trả các entry ghi được, `Entry.setValue` có thể vẫn đổi giá trị.

Đặc biệt, `Collections.unmodifiableSet(backingMap.entrySet())` chỉ chặn thao tác thay đổi cấu trúc set qua wrapper đó; nó không tự bọc từng đối tượng `Map.Entry` để chặn `setValue`. Để dùng một map không sửa được, trả `entrySet` từ một `Collections.unmodifiableMap` đúng cách là một hướng rõ ràng hơn.

Nếu tự cài entry, phải xác định nó gắn với map hay độc lập. Một `SimpleEntry` có thể đổi giá trị của chính nó, nhưng một entry rời rạc không tự viết ngược vào kho map. Không trả một entry “trông có vẻ ghi được” mà `setValue` chỉ đổi bản sao khi hợp đồng view yêu cầu cập nhật ánh xạ gốc. Xem [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### put hỗ trợ không đồng nghĩa replaceAll mặc định hỗ trợ

Phần cài đặt mặc định của `Map.replaceAll` đi qua entry và gọi `Entry.setValue`. Do đó một map có `put` nhưng entry không hỗ trợ `setValue` có thể không dùng được `replaceAll` mặc định.

Muốn công bố hỗ trợ, phải cung cấp đường cài đặt đúng hoặc ghi đè phương thức phù hợp. Không suy ra từ việc một thao tác cập nhật đơn lẻ hoạt động rằng mọi phương thức mặc định đều hoạt động.

Ngược lại, `putAll` trong `AbstractMap` sử dụng `put` cho từng ánh xạ. Vì nguồn rỗng không có lượt `put` nào, map ví dụ nhận `putAll(Map.of())` bình thường dù `put` bị chặn. Quy tắc này phù hợp với trường hợp không có tác động được [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) cho phép.

## Chương trình đầy đủ kiểm chứng các khả năng

Lưu mã sau vào `MinimalCollectionsDemo.java`. Các lớp nhỏ dùng cấu trúc có sẵn làm kho để tập trung vào đường gọi của lớp khung, không nhằm thay thế các collection chuẩn.

Chương trình có sáu lớp minh họa:

- `ReadOnlyBag`: chỉ `iterator/size`, giữ cả phần tử trùng.
- `ReadOnlyList`: chỉ `get/size`, sao chép nguồn.
- `FixedList`: thêm `set`, giữ nguyên kích thước.
- `EditableList`: thêm `add(int,E)/remove(int)` và cập nhật `modCount`.
- `LimitedQueue`: năm phương thức nền của queue, cố ý không hỗ trợ iterator xóa.
- `ReadOnlyMap`: chỉ `entrySet` dựa trên bản sao map không sửa được.

`outcome` chỉ dùng để ghi tên ngoại lệ cho thí nghiệm. Trong mã ứng dụng, không nên biến mọi lỗi `RuntimeException` thành một chuỗi rồi tiếp tục như thể thao tác đã thành công.

~~~java
import java.util.AbstractCollection;
import java.util.AbstractList;
import java.util.AbstractMap;
import java.util.AbstractQueue;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.Objects;
import java.util.RandomAccess;
import java.util.Set;

public class MinimalCollectionsDemo {
    static final class ReadOnlyBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        ReadOnlyBag(Collection<? extends E> source) {
            data = List.copyOf(source);
        }

        @Override public int size() { return data.size(); }

        @Override public Iterator<E> iterator() {
            Iterator<E> delegate = data.iterator();
            return new Iterator<>() {
                @Override public boolean hasNext() { return delegate.hasNext(); }
                @Override public E next() { return delegate.next(); }
            };
        }
    }

    static final class ReadOnlyList<E> extends AbstractList<E>
            implements RandomAccess {
        private final List<E> data;

        ReadOnlyList(Collection<? extends E> source) {
            data = List.copyOf(source);
        }

        @Override public E get(int index) { return data.get(index); }
        @Override public int size() { return data.size(); }
    }

    static class FixedList<E> extends AbstractList<E> implements RandomAccess {
        protected final ArrayList<E> data;

        FixedList(Collection<? extends E> source) {
            data = new ArrayList<>(source);
        }

        @Override public E get(int index) { return data.get(index); }
        @Override public int size() { return data.size(); }
        @Override public E set(int index, E value) {
            return data.set(index, value);
        }
    }

    static final class EditableList<E> extends FixedList<E> {
        EditableList(Collection<? extends E> source) {
            super(source);
        }

        @Override public void add(int index, E value) {
            data.add(index, value);
            modCount++;
        }

        @Override public E remove(int index) {
            E previous = data.remove(index);
            modCount++;
            return previous;
        }
    }

    static final class LimitedQueue<E> extends AbstractQueue<E> {
        private final int capacity;
        private final ArrayDeque<E> data = new ArrayDeque<>();

        LimitedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        @Override public int size() { return data.size(); }
        @Override public E peek() { return data.peekFirst(); }
        @Override public E poll() { return data.pollFirst(); }

        @Override public boolean offer(E value) {
            Objects.requireNonNull(value);
            if (data.size() == capacity) {
                return false;
            }
            data.addLast(value);
            return true;
        }

        // Head removal is supported; iterator removal is not supported.
        @Override public Iterator<E> iterator() {
            Iterator<E> delegate = data.iterator();
            return new Iterator<>() {
                @Override public boolean hasNext() { return delegate.hasNext(); }
                @Override public E next() { return delegate.next(); }
            };
        }
    }

    static final class ReadOnlyMap<K, V> extends AbstractMap<K, V> {
        private final Map<K, V> data;

        ReadOnlyMap(Map<? extends K, ? extends V> source) {
            data = Collections.unmodifiableMap(new LinkedHashMap<>(source));
        }

        @Override public Set<Entry<K, V>> entrySet() {
            return data.entrySet();
        }
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        ReadOnlyBag<String> bag = new ReadOnlyBag<>(List.of("A", "B", "A"));
        System.out.println("bag = " + bag);
        System.out.println("bag-contains-A = " + bag.contains("A"));
        System.out.println("bag-add = " + outcome(() -> bag.add("C")));
        System.out.println("bag-remove-missing = " + bag.remove("Z"));
        System.out.println("bag-remove-existing = " + outcome(() -> bag.remove("A")));
        System.out.println("bag-addAll-empty = " + bag.addAll(List.of()));
        System.out.println("bag-removeIf-no-match = " + bag.removeIf(s -> s.equals("Z")));
        System.out.println("bag-removeIf-match = "
                + outcome(() -> bag.removeIf(s -> s.equals("A"))));

        ArrayList<String> source = new ArrayList<>(List.of("one", "two"));
        ReadOnlyList<String> readOnly = new ReadOnlyList<>(source);
        source.set(0, "changed");
        System.out.println("read-only-snapshot = " + readOnly);
        System.out.println("list-equals = " + readOnly.equals(List.of("one", "two")));
        System.out.println("list-hash-equals = "
                + (readOnly.hashCode() == List.of("one", "two").hashCode()));
        System.out.println("read-only-set = " + outcome(() -> readOnly.set(0, "X")));

        FixedList<String> fixed = new FixedList<>(List.of("B", "A"));
        System.out.println("fixed-set-old = " + fixed.set(0, "C"));
        fixed.sort(null);
        fixed.replaceAll(String::toLowerCase);
        System.out.println("fixed-after-sort-replace = " + fixed);
        ListIterator<String> fixedIt = fixed.listIterator();
        fixedIt.next();
        fixedIt.set("first");
        System.out.println("fixed-after-iterator-set = " + fixed);
        System.out.println("fixed-add = " + outcome(() -> fixed.add("D")));
        System.out.println("fixed-remove-index = " + outcome(() -> fixed.remove(0)));

        EditableList<String> editable = new EditableList<>(List.of("A", "B", "C"));
        editable.add("D");
        ListIterator<String> it = editable.listIterator();
        System.out.println("editable-remove-before-next = " + outcome(it::remove));
        it.next();
        it.remove();
        it.add("X");
        System.out.println("editable-after-iterator = " + editable);
        List<String> view = editable.subList(1, 3);
        view.clear();
        System.out.println("editable-after-sublist-clear = " + editable);
        Iterator<String> oldIterator = editable.iterator();
        editable.add("E");
        System.out.println("editable-old-iterator = " + outcome(oldIterator::next));

        LimitedQueue<String> queue = new LimitedQueue<>(2);
        System.out.println("queue-first-offer = " + queue.offer("A"));
        System.out.println("queue-add = " + queue.add("B"));
        System.out.println("queue-full-offer = " + queue.offer("C"));
        System.out.println("queue-full-add = " + outcome(() -> queue.add("C")));
        System.out.println("queue-remove-existing = "
                + outcome(() -> queue.remove("B")));
        System.out.println("queue-remove-head = " + queue.remove());
        queue.clear();
        System.out.println("queue-after-clear = " + queue);
        System.out.println("queue-empty-poll = " + queue.poll());
        System.out.println("queue-empty-remove = " + outcome(queue::remove));
        System.out.println("queue-null-offer = " + outcome(() -> queue.offer(null)));

        LinkedHashMap<String, Integer> input = new LinkedHashMap<>();
        input.put("A", 1);
        input.put("B", 2);
        ReadOnlyMap<String, Integer> map = new ReadOnlyMap<>(input);
        input.put("A", 99);
        System.out.println("map-snapshot = " + map);
        System.out.println("map-get = " + map.get("A"));
        System.out.println("map-put = " + outcome(() -> map.put("C", 3)));
        System.out.println("map-remove-missing = " + map.remove("Z"));
        System.out.println("map-remove-existing = " + outcome(() -> map.remove("A")));
        System.out.println("map-putAll-empty = " + outcome(() -> map.putAll(Map.of())));
        Map.Entry<String, Integer> entry = map.entrySet().iterator().next();
        System.out.println("map-entry-setValue = " + outcome(() -> entry.setValue(8)));
        System.out.println("map-keySet-remove = " + outcome(() -> map.keySet().remove("A")));
        System.out.println("map-replaceAll = "
                + outcome(() -> map.replaceAll((key, value) -> value + 1)));
        System.out.println("map-after-attempts = " + map);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 MinimalCollectionsDemo.java
java MinimalCollectionsDemo
~~~

Mã đã được biên dịch với `--release 17` và chạy bằng OpenJDK Zulu 24.0.2. Stdout chính xác của lần chạy:

~~~text
bag = [A, B, A]
bag-contains-A = true
bag-add = UnsupportedOperationException
bag-remove-missing = false
bag-remove-existing = UnsupportedOperationException
bag-addAll-empty = false
bag-removeIf-no-match = false
bag-removeIf-match = UnsupportedOperationException
read-only-snapshot = [one, two]
list-equals = true
list-hash-equals = true
read-only-set = UnsupportedOperationException
fixed-set-old = B
fixed-after-sort-replace = [a, c]
fixed-after-iterator-set = [first, c]
fixed-add = UnsupportedOperationException
fixed-remove-index = UnsupportedOperationException
editable-remove-before-next = IllegalStateException
editable-after-iterator = [X, B, C, D]
editable-after-sublist-clear = [X, D]
editable-old-iterator = ConcurrentModificationException
queue-first-offer = true
queue-add = true
queue-full-offer = false
queue-full-add = IllegalStateException
queue-remove-existing = UnsupportedOperationException
queue-remove-head = A
queue-after-clear = []
queue-empty-poll = null
queue-empty-remove = NoSuchElementException
queue-null-offer = NullPointerException
map-snapshot = {A=1, B=2}
map-get = 1
map-put = UnsupportedOperationException
map-remove-missing = null
map-remove-existing = UnsupportedOperationException
map-putAll-empty = OK
map-entry-setValue = UnsupportedOperationException
map-keySet-remove = UnsupportedOperationException
map-replaceAll = UnsupportedOperationException
map-after-attempts = {A=1, B=2}
~~~

## Giải thích kết quả và giới hạn của ví dụ

### Bag chỉ đọc vẫn có lời gọi xóa trả về bình thường

`bag-remove-missing = false` và `bag-addAll-empty = false` là các lời gọi không thay đổi dữ liệu. Chúng không cần gọi đường ghi bị chặn.

`bag-remove-existing` và `bag-removeIf-match` lại cần iterator xóa và nhận `UnsupportedOperationException`. Cùng một đối tượng, sự khác nhau nằm ở đường thực hiện thực tế của lời gọi, không phải khả năng tự nhiên thay đổi giữa các dòng.

`ReadOnlyBag` sao chép dữ liệu bằng `List.copyOf`, nên hàm tạo không nhận phần tử `null`. Đây là lựa chọn của lớp ví dụ; không phải mọi lớp con `AbstractCollection` đều buộc cấm `null`.

Nó không ghi đè `equals/hashCode` thành ngữ nghĩa list chỉ vì dữ liệu bên trong được lưu bằng list. Cấu trúc lưu trữ là chi tiết cài đặt; kiểu trừu tượng được công bố mới quyết định ngữ nghĩa bằng nhau cần có.

### ReadOnlyList tách dữ liệu nguồn và có ngữ nghĩa list

Sau khi thay phần tử trong `source`, `readOnly` vẫn hiển thị `[one, two]`. Hàm tạo đã lấy bản sao danh sách phần tử tại thời điểm tạo; đối tượng không là view của `source`.

`list-equals = true` và `list-hash-equals = true` cho thấy `AbstractList` cung cấp ngữ nghĩa so sánh theo phần tử và thứ tự, tương thích với một list chuẩn có cùng dữ liệu. Không cần tự viết lại thuật toán ấy khi nó đã phù hợp hợp đồng.

Đây vẫn là sao chép nông. Nếu phần tử là đối tượng mutable, bản sao chứa cùng tham chiếu tới đối tượng đó. Ví dụ dùng `String` để sự thay đổi nội dung phần tử không làm nhiễu bài học về khả năng sửa collection.

### FixedList chỉ cần set để mở một nhóm thao tác khác

`fixed-set-old = B` nhắc lại rằng `set` phải trả phần tử cũ, không phải phần tử mới hay một giá trị báo thành công tùy ý.

Sau `sort` rồi `replaceAll`, list là `[a, c]`; sau `ListIterator.set`, nó là `[first, c]`. Số phần tử vẫn là hai.

`fixed-add` và `fixed-remove-index` ném `UnsupportedOperationException`. Đó là khác biệt giữa thay thế và thay đổi kích thước. Một API nhận `List` và chỉ cần hoán vị/thay thế có yêu cầu khả năng khác API cần thêm dòng mới.

### EditableList kế thừa cả đường sửa qua iterator và subList

Từ `[A, B, C]`, lệnh `add("D")` kế thừa đi vào `add(int,E)` của lớp con. Sau đó iterator lấy `A`, xóa `A` rồi chèn `X` tại con trỏ, tạo `[X, B, C, D]`.

Lời gọi `remove` trước `next` nhận `IllegalStateException`: khả năng xóa có được hỗ trợ, nhưng lời gọi diễn ra sai trạng thái. Không đánh đồng ngoại lệ này với `UnsupportedOperationException`.

`subList(1,3)` chọn `[B,C]`. Gọi `clear` trên view làm list gốc còn `[X,D]`. Đây là bằng chứng đường ghi qua view hoạt động trên dữ liệu gốc.

Cuối cùng, chương trình tạo iterator rồi thêm `E` trực tiếp qua list. Lần `next` trên iterator cũ ném `ConcurrentModificationException` trong phép thử đơn luồng này. Nó cho thấy `modCount` đã được nối vào cơ chế kế thừa; không chứng minh cơ chế đó cung cấp đồng bộ cho cập nhật từ nhiều luồng.

`data` trong `FixedList` là `protected` để lớp minh họa `EditableList` dùng chung kho. Khi phát triển một thư viện có nhiều lớp con không kiểm soát được, phải thiết kế quyền truy cập cẩn thận để lớp con không sửa kho mà bỏ qua bất biến hoặc bộ đếm.

### LimitedQueue hỗ trợ lấy đầu nhưng không hỗ trợ xóa tùy ý

Queue dung lượng hai nhận `A` và `B`. Khi đầy, `offer("C")` trả `false` còn `add("C")` ném `IllegalStateException`. Đây là một cặp hợp đồng được `AbstractQueue` xây từ `offer`.

`queue.remove("B")` tìm đúng phần tử nhưng iterator không có `remove`, nên ném `UnsupportedOperationException`. `queue.remove()` lại lấy `A` thành công qua `poll`.

`queue.clear()` lấy bỏ phần tử còn lại bằng `poll` nên hoạt động được. Sau đó `poll` trả `null`, còn `remove()` ném `NoSuchElementException`. Thêm `null` bị `Objects.requireNonNull` chặn trước khi lưu dữ liệu.

Lớp ví dụ không cung cấp chờ, khóa hay bảo đảm dùng đồng thời. Một queue giới hạn dung lượng chưa tự trở thành `BlockingQueue` hoặc một cấu trúc an toàn cho nhiều luồng.

### ReadOnlyMap chặn cả đường entry và view

Map giữ bản sao `{A=1, B=2}` dù map đầu vào đã đổi `A` thành `99`. Chặn sửa được thực hiện trên bản sao riêng, tránh việc thành phần giữ map nguồn có thể sửa trực tiếp kho của đối tượng ví dụ.

`get`, `size` và hiển thị được suy ra từ `entrySet`. Nhưng `AbstractMap.get` theo cách kế thừa có thể phải duyệt entry; việc kho bên trong là `LinkedHashMap` không tự làm đường `get` lớp ngoài thành truy cập băm. Nếu hiệu năng đọc quan trọng, có thể ghi đè `get/containsKey/size` để ủy quyền phù hợp sau khi giữ đúng hợp đồng.

`map-remove-missing = null` là một thao tác không có tác động. `map-remove-existing`, `map-keySet-remove` và `map-entry-setValue` đều bị chặn. `map-replaceAll` cũng bị chặn tại đường cập nhật entry. Map cuối vẫn là `{A=1, B=2}`.

Bản sao map cũng là sao chép nông. Với khóa mutable, sửa những trường ảnh hưởng `equals/hashCode` sau khi đưa vào map có thể làm hỏng giả định tra cứu. Không dùng nhãn “chỉ đọc” để suy ra mọi đối tượng được chứa đều bất biến.

## Tối thiểu về số phương thức không có nghĩa tối thiểu về chất lượng

### Chỉ số và số lượng phải đúng

Với list, miền hợp lệ của `get/set/remove(int)` là từ `0` đến nhỏ hơn `size()`. `add(int,E)` cho phép thêm tại `size()`, tức ngay sau phần tử cuối.

Nếu tự viết kho dữ liệu, phải kiểm tra đúng hai loại biên. Đừng dùng chung một điều kiện `index < size` rồi vô tình không cho thêm vào list rỗng hoặc không cho nối cuối.

`size` phải nhất quán với số phần tử iterator có thể duyệt trong điều kiện sử dụng được hỗ trợ. Nếu kho có thể quá lớn để biểu diễn bằng `int`, phải theo quy tắc `Collection.size`; không tự để tràn thành số âm. Với lớp nhỏ trong ví dụ, cấu trúc chuẩn nội bộ xử lý phần này.

`next` khi hết phải ném `NoSuchElementException`, không trả `null` làm tín hiệu kết thúc: collection có thể chứa `null` hợp lệ theo chính sách riêng. `hasNext` không được tự tiêu thụ một phần tử rồi bỏ mất nó.

### Chính sách phần tử phải có tên rõ ràng

Khi cài lớp chuyên biệt, hãy mô tả các điều kiện như:

- Cho phép `null` hay không.
- Có chấp nhận trùng hay phải giữ duy nhất.
- Thứ tự có được bảo đảm hay không.
- Đối tượng được sao chép hay giữ view tới nguồn.
- Có giới hạn số lượng, miền giá trị hoặc loại dữ liệu hay không.
- Có hỗ trợ truy cập từ nhiều luồng hay cần đồng bộ bên ngoài.

Không phải mọi lỗi dữ liệu đều là thao tác không hỗ trợ. Nếu lớp có hỗ trợ thêm nhưng phần tử không hợp lệ, hãy ném loại ngoại lệ đúng với điều kiện đã công bố. Với phép truy vấn một giá trị không hợp lệ, hợp đồng một số interface cho phép trả kết quả không tìm thấy hoặc ném ngoại lệ tùy triển khai; không tự hứa tất cả collection có cùng chính sách.

Constructor nhận `Collection` hoặc `Map` là khuyến nghị cho các triển khai dùng chung, không phải một phương thức interface mà trình biên dịch bắt mọi lớp phải có. Một cấu trúc chuyên biệt có thể cần tham số dung lượng hoặc nguồn dữ liệu riêng; API phải giải thích được cách tạo một đối tượng hợp lệ.

### Các phương thức mặc định cũng phải được đưa vào danh sách khả năng

Không chỉ kiểm tra những phương thức mình viết bằng tay. Với một list, còn có `removeIf`, `replaceAll`, `sort`, iterator, list iterator và sublist. Với map, còn có `putIfAbsent`, `replace`, `compute`, `merge`, `replaceAll` và các view.

Ví dụ, phương thức mặc định có thể chỉ cần ghi trong một nhánh. Một `computeIfAbsent` có thể trả giá trị đã có mà chưa cần gọi `put`; điều đó không chứng minh map hỗ trợ ghi cho khóa vắng.

Nếu lớp hứa “mọi thao tác ghi đều thất bại ngay”, chỉ giữ phần cài đặt tối thiểu có thể không đủ để tạo đúng bảo đảm mạnh đó. Cần xem và có thể ghi đè mọi đường liên quan, gồm cả đường không có tác động và view. Nếu chỉ hứa không thể thay dữ liệu qua API, vẫn phải chắc không có đường ghi bị bỏ sót.

### Không có bảo đảm hoàn tác tự động cho thao tác hàng loạt

Một `addAll` kế thừa có thể thêm lần lượt. Nếu thêm vài phần tử rồi gặp dữ liệu không hợp lệ hoặc giới hạn dung lượng, phương thức có thể ném ngoại lệ sau khi đã thêm một phần.

Tương tự, một `removeIf` có thể đã xóa vài phần tử trước khi điều kiện ném lỗi; một phép cập nhật hàng loạt có thể đã thay một số giá trị. Không được công bố tính “tất cả hoặc không gì” chỉ vì phương thức có một tên duy nhất.

Nếu một lớp cần bảo đảm mạnh hơn, phải thiết kế cơ chế phù hợp: kiểm tra trước với điều kiện đúng, tạo trạng thái mới rồi công bố, hoặc dùng giao thức cập nhật khác. Việc kiểm tra trước cũng cần xem xét trạng thái có thể thay đổi giữa lúc kiểm tra và lúc ghi nếu có nhiều luồng.

## Một cách kiểm tra có hệ thống trước khi công bố lớp

Bắt đầu từ lời hứa công khai, rồi đi qua từng đường thực hiện.

| Nhóm kiểm tra | Ví dụ đầu vào có giá trị |
| --- | --- |
| Đọc | Rỗng, một phần tử, nhiều phần tử, có trùng nếu cho phép |
| Chỉ số | `-1`, `0`, chỉ số cuối, `size()`, vượt `size()` |
| Thêm | Thêm mới, thêm trùng, thêm tại đầu/cuối, khi đầy |
| Thay thế | Giá trị cũ trả về, cùng giá trị, giá trị không hợp lệ |
| Xóa | Có giá trị, không có giá trị, xóa đầu, xóa qua iterator |
| Trạng thái iterator | Trước `next`, sau một `next`, xóa hai lần, hết dữ liệu |
| Hàng loạt | Nguồn rỗng, không khớp, có khớp, dữ liệu lỗi giữa chừng |
| View | Sửa qua `subList/keySet/values/entrySet` có đi đúng vào gốc? |
| Bằng nhau | So với một triển khai chuẩn cùng kiểu trừu tượng |
| Đóng gói | Nguồn ban đầu, iterator hay entry có sửa ngoài ý muốn được không? |

Không cần viết lại một bộ kiểm thử cho toàn bộ JDK để thử một lớp nhỏ, nhưng các đường kế thừa gắn trực tiếp với khả năng đã hứa phải có bằng chứng. Một bài thử “tạo đối tượng rồi in ra” chỉ kiểm tra được rất ít phần của hợp đồng.

Đối với hiệu năng, trước hết đếm đường gọi. Nếu `iterator.next` gọi `get(i)` mà `get(i)` tốn thời gian theo `i`, duyệt toàn bộ có thể tốn bậc hai. Nếu `AbstractMap.get` duyệt `entrySet`, nhiều lần tra cứu có thể đắt dù kho vật lý có bảng băm. Sau khi đúng hợp đồng mới tối ưu các điểm đã đo hoặc có phân tích rõ.

## Bài tập tự kiểm tra

### 1. Chỉ cài size có tạo được AbstractCollection cụ thể không?

Một lớp con chỉ cài `size()` và muốn dựa vào lớp khung cho mọi thứ khác.

**Đáp án:** Chưa đủ. Cần cung cấp `iterator()`. Iterator phải duyệt đúng dữ liệu; một iterator luôn rỗng trong khi `size` khác không cũng không phải cài đặt đúng.

### 2. AbstractSet có tự bỏ phần tử trùng trong constructor không?

Một lớp set tự giữ `new ArrayList<>(source)` rồi trả iterator của list. `source` chứa hai phần tử bằng nhau.

**Đáp án:** Không. Lớp con phải duy trì bất biến không trùng ngay từ hàm tạo và các đường cập nhật. `AbstractSet` không tự lọc kho dữ liệu cho lớp con.

### 3. Vì sao addAll rỗng thành công mà add thật lại thất bại?

Một collection chỉ đọc kế thừa `addAll` từ lớp khung.

**Đáp án:** Với nguồn rỗng không có lượt `add` nào được gọi. Hợp đồng tổng quát cho phép lời gọi không có tác động kết thúc bình thường. Không dùng trường hợp này để dò khả năng thêm.

### 4. List chỉ hỗ trợ set có sort được không?

Một lớp có `get/size/set` đúng nhưng không cho thêm và xóa.

**Đáp án:** Có thể dùng phần sắp xếp mặc định phù hợp vì số lượng không thay đổi và việc ghi lại qua list iterator dùng khả năng `set`. Cần kiểm tra đúng hợp đồng của triển khai; không suy ra từ việc `add` bị chặn rằng mọi thao tác thay đổi đều bị chặn.

### 5. Tại sao queue xóa đầu được nhưng xóa giá trị không được?

Lớp con `AbstractQueue` có `poll` hoạt động, còn iterator chỉ hỗ trợ đọc.

**Đáp án:** `remove()` dựa trên `poll`. `remove(Object)` kế thừa tìm bằng iterator rồi cần `iterator.remove` khi gặp giá trị. Hai overload đi qua hai nhóm phương thức nền khác nhau.

### 6. Map chặn put nhưng entry vẫn ghi được có phải chỉ đọc không?

`entrySet().iterator().next().setValue(v)` sửa được dữ liệu map.

**Đáp án:** Không. Map có một đường cập nhật qua entry. Phải chặn hoặc thiết kế đúng cả entry, iterator và các view; chỉ chặn `put` không đủ.

### 7. Tăng modCount trong set có luôn là việc đúng không?

Lớp list dùng `set` thay một phần tử mà không đổi cấu trúc, nhưng mọi `set` đều tăng `modCount`.

**Đáp án:** Không nên tăng theo thói quen. Với mô hình này, thay phần tử không là thay đổi cấu trúc. Bộ đếm phải theo loại thay đổi mà cơ chế iterator đã công bố cần theo dõi; cập nhật sai có thể làm iterator báo lỗi không phù hợp. Không dùng bộ đếm để thay thế đồng bộ.

### 8. put hỗ trợ nhưng replaceAll thất bại ở setValue có mâu thuẫn không?

Map tự cài `put`, trả entry không hỗ trợ `setValue` và giữ `replaceAll` mặc định.

**Đáp án:** `replaceAll` mặc định đi qua entry, nên có thể không được hỗ trợ trong thiết kế đó. Nếu lớp muốn công bố hỗ trợ `replaceAll`, cần cung cấp một cách cài đặt đúng; kiểm thử `put` thành công không kiểm tra được đường cập nhật này.
