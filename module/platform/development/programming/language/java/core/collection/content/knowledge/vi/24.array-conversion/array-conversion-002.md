# Những thay đổi được phép qua set và những thao tác bị từ chối

## 1. Điểm xuất phát: cùng dùng List nhưng quyền thay đổi khác nhau

Trong bài này, đối tượng cần xét là danh sách tạo từ `Arrays.asList` trong nhóm kiến thức **mảng và chuyển đổi**. Một mảng đã có số vị trí cố định. Đưa nó qua `Arrays.asList` giúp dùng giao diện `List` để đọc, tìm kiếm hoặc thay nội dung các vị trí ấy; việc chuyển đổi này không tự tạo ra khả năng thêm và xóa vị trí.

Hãy hình dung một phiếu đăng ký có đúng ba ô tên. Ta có thể sửa tên ở ô thứ hai, đổi chỗ hai tên hoặc viết hoa cả ba tên. Các thao tác ấy vẫn dùng ba ô cũ. Muốn ghi thêm một người thứ tư hoặc bỏ hẳn một ô, ta cần một cấu trúc có quyền thay đổi số ô.

Tài liệu `Arrays.asList` xác định danh sách có kích thước cố định, dùng chung mảng nền; cập nhật qua một phía được nhìn thấy ở phía kia. Các phép làm thay đổi kích thước không được hỗ trợ. [Java SE 17 — Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Ba câu hỏi phải tách riêng khi đọc một đoạn mã:

1. Có thay được phần tử tại một chỉ số đã tồn tại hay không?
2. Có thay được số phần tử của danh sách hay không?
3. Thao tác có tác động đến một mảng hoặc đối tượng khác đang được dùng chung hay không?

Với `Arrays.asList(array)`, câu trả lời thông thường là: thay vị trí được, đổi kích thước không được, và thay vị trí sẽ tác động tới mảng nền. Việc gọi được một phương thức qua biến kiểu `List` chỉ chứng minh rằng chữ ký phương thức tồn tại; chưa chứng minh rằng đối tượng thực tế hỗ trợ thao tác đó.

Sau bài này, người học cần dự đoán được một lệnh `set` thay đổi gì, giải thích được vì sao `sort` có thể chạy còn `add` bị từ chối, nhận ra lỗi do chỉ số hoặc kiểu mảng, và chọn đúng cách sao chép khi cần một danh sách có thể thêm/xóa.

## 2. set là thay một vị trí đã có

Xét đoạn minh họa bên trong một phương thức; cần nhập `java.util.Arrays` và `java.util.List`:

~~~java
String[] names = {"Lan", "Mai", "An"};
List<String> view = Arrays.asList(names);

String old = view.set(1, "Vy");
~~~

Sau lệnh cuối:

| Thành phần | Giá trị |
| --- | --- |
| `old` | `"Mai"` |
| `view` | `[Lan, Vy, An]` |
| `names[1]` | `"Vy"` |
| `view.size()` | `3` |
| `names.length` | `3` |

Chỉ số bắt đầu từ `0` nên `1` là vị trí thứ hai. `set` trả về phần tử trước đó tại vị trí ấy; nó không trả về danh sách và cũng không trả về giá trị boolean báo thành công. Hợp đồng của `List.set` mô tả thao tác thay thế và điều kiện `0 <= index < size()`. [Java SE 17 — List.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#set(int,E)).

Điểm quan trọng là **vị trí đã tồn tại trước khi gọi**. Với danh sách ba phần tử, các chỉ số hợp lệ cho `set` là `0`, `1` và `2`. `set(3, value)` không phải cách nối phần tử thứ tư. Chỉ số `3` nằm ngoài vùng có thể thay thế, dù chính số `3` bằng kích thước hiện tại.

`add(index, value)` là yêu cầu khác. Nó chèn thêm một vị trí và đẩy các phần tử phía sau; `size` tăng lên. Vì vậy, `add(1, "Vy")` không thể dùng thay cho `set(1, "Vy")` trên danh sách cố định. Hai câu lệnh có thể giống nhau ở dữ liệu truyền vào nhưng mang ý nghĩa cấu trúc khác nhau.

Cũng không có vùng “chưa dùng” trong danh sách sau:

~~~java
String[] slots = new String[3];
List<String> fixed = Arrays.asList(slots);
~~~

`fixed.size()` đã bằng `3` ngay từ đầu. Ba vị trí đều chứa `null`. Muốn điền vị trí đầu tiên, dùng `fixed.set(0, "Lan")`. Gọi `fixed.add("Lan")` vẫn là yêu cầu tạo vị trí thứ tư và bị từ chối. Giá trị `null` ở một vị trí không có nghĩa rằng vị trí ấy chưa được tính vào kích thước.

Đây cũng là lý do không nên nhầm **kích thước hiện tại** với **dung lượng dự trữ** của `ArrayList`. `new ArrayList<String>(3)` tạo danh sách có kích thước `0`; số `3` chỉ là dung lượng ban đầu. Trong khi đó, `Arrays.asList(new String[3])` đã có ba phần tử. Nếu một thuật toán sẽ gọi `set(0, ...)`, hai cấu trúc này có điều kiện ban đầu khác nhau.

## 3. Phạm vi tác động của set lên mảng nguồn

`Arrays.asList(array)` dùng chung các vị trí của mảng nguồn. Tiếp tục ví dụ `names` và `view` ở trên:

~~~java
names[0] = "Ha";
view.set(2, null);
~~~

Cả mảng lẫn danh sách lúc này đọc được `[Ha, Vy, null]`. Một hàm nhận `List` có thể vô tình sửa mảng của bên gọi thông qua `set`; ngược lại, bên giữ mảng có thể làm dữ liệu mà hàm đang đọc thay đổi. Vì thế, hãy công bố rõ khi hàm sửa đầu vào.

Gán lại biến `names` sang mảng khác không di chuyển view sang mảng mới: view tiếp tục tham chiếu mảng cũ. Quan hệ tham chiếu hai chiều và cách tách bản sao được giải thích đầy đủ trong bài về `Arrays.asList` đứng trước; tại đây, điều cần giữ là **`set` sửa vị trí hiện hữu, kể cả khi không trực tiếp truy cập mảng**.

## 4. Những phép thay đổi được phép khi số vị trí giữ nguyên

`set` là trường hợp trực tiếp nhất. Một số thuật toán thay nhiều vị trí nhưng vẫn giữ kích thước cũng có thể áp dụng lên danh sách của `Arrays.asList`.

| Thao tác | Loại thay đổi | Điều cần nhớ |
| --- | --- | --- |
| `view.set(i, x)` | Thay một vị trí | Chỉ số phải tồn tại, giá trị phải phù hợp kiểu mảng |
| `ListIterator.set(x)` | Thay phần tử vừa được duyệt | Phải thỏa trạng thái của bộ duyệt |
| `view.replaceAll(op)` | Tính lại từng phần tử | Hàm biến đổi có thể ném lỗi |
| `view.sort(comparator)` | Đổi thứ tự phần tử | Các phần tử phải so sánh được theo quy tắc đã chọn |
| `Collections.reverse(view)` | Đảo thứ tự | Mảng nền cũng bị thay thứ tự |
| `Collections.swap(view, i, j)` | Đổi hai vị trí | Hai chỉ số phải hợp lệ |
| `Collections.fill(view, x)` | Ghi cùng giá trị vào các vị trí | Không tạo thêm phần tử |
| `Collections.copy(view, source)` | Ghi đè một đoạn đầu | Đích phải có đủ kích thước trước khi chép |

Các thuật toán thao tác danh sách trong `Collections` công bố yêu cầu riêng đối với khả năng thay thế phần tử. Không thể suy ra rằng mọi đối tượng mang kiểu `List` đều dùng được với chúng. [Java SE 17 — Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

Ví dụ minh họa dưới đây cần các import `Arrays`, `Collections`, `List` và `Locale` trong `java.util`:

~~~java
String[] words = {"c", "a", "b"};
List<String> view = Arrays.asList(words);

view.sort(null);
Collections.reverse(view);
view.replaceAll(s -> s.toUpperCase(Locale.ROOT));
Collections.copy(view, List.of("X", "Y"));
~~~

Diễn biến của mảng nền:

~~~text
ban đầu      [c, a, b]
sort         [a, b, c]
reverse      [c, b, a]
replaceAll   [C, B, A]
copy         [X, Y, A]
~~~

`sort(null)` dùng thứ tự tự nhiên của chuỗi. `reverse` đảo các giá trị trong chính các vị trí hiện tại. `replaceAll` viết hoa từng chuỗi bằng `Locale.ROOT` để tránh phụ thuộc thiết lập ngôn ngữ mặc định. `copy` cuối cùng ghi đè hai phần tử đầu, giữ nguyên phần tử thứ ba.

Không thao tác nào trong chuỗi này tạo ra vị trí mới. Tuy nhiên, cả bốn đều là thay đổi dữ liệu. Khi muốn bảo toàn mảng ban đầu để hiển thị hoặc tính toán tiếp, việc “chỉ sắp xếp lại” vẫn có thể làm hỏng giả định của bên gọi.

`Collections.copy` cũng không phải lệnh tự tăng kích thước đích. Nếu đích chỉ có một phần tử mà nguồn có hai phần tử, việc chép không có đủ vị trí để ghi. Một danh sách được tạo với dung lượng dự trữ lớn nhưng `size() == 0` vẫn không đáp ứng yêu cầu này.

`sort` có thể thất bại vì dữ liệu hoặc bộ so sánh, ngay cả khi danh sách cho phép thay vị trí. Chẳng hạn, thứ tự tự nhiên của `String` không xử lý `null` như một chuỗi thông thường; nếu có `null` và thật sự cần sắp xếp, hãy chọn quy tắc rõ ràng, ví dụ bộ so sánh có xử lý `null`. Khả năng sửa danh sách và khả năng so sánh dữ liệu là hai điều kiện khác nhau.

## 5. Những thao tác làm đổi kích thước bị từ chối

Với danh sách cố định không rỗng, yêu cầu thực sự thêm hoặc xóa phần tử sẽ dẫn tới `UnsupportedOperationException`. Lỗi này biểu thị rằng đối tượng không hỗ trợ thao tác được yêu cầu.

| Lệnh điển hình | Vì sao không thực hiện được |
| --- | --- |
| `view.add(x)` | Cần thêm một vị trí ở cuối |
| `view.add(i, x)` | Cần chèn một vị trí |
| `view.addAll(nonEmptySource)` | Cần thêm các vị trí cho nguồn không rỗng |
| `view.remove(i)` với chỉ số hợp lệ | Cần bỏ một vị trí |
| `view.remove(existingValue)` | Cần bỏ vị trí chứa giá trị tìm thấy |
| `view.clear()` khi đang có phần tử | Cần xóa các vị trí hiện có |
| `view.removeIf(predicate)` khi có phần tử cần xóa | Cần xóa vị trí thỏa điều kiện |
| `view.removeAll(values)` khi có phần tử bị loại | Cần giảm số vị trí |
| `view.retainAll(values)` khi có phần tử bị loại | Cần giảm số vị trí |
| `iterator.remove()` sau khi đã duyệt một phần tử | Cần xóa phần tử vừa duyệt |
| `listIterator.add(x)` | Cần chèn một vị trí qua bộ duyệt |

Các ví dụ trong bảng giả định tham số thông thường hợp lệ và thao tác có tác dụng thêm/xóa thật sự. Đừng dùng bảng để đoán thứ tự kiểm tra lỗi khi vừa sai chỉ số, vừa không hỗ trợ thao tác.

Một lỗi thường gặp là dùng `remove` để bỏ các ô `null`:

~~~java
List<String> fixed = Arrays.asList("A", null, "B");
fixed.removeIf(value -> value == null);
~~~

Đây là đoạn minh họa gây lỗi, không phải cách lọc hợp lệ trên danh sách này. `null` là một phần tử đang chiếm vị trí; bỏ nó sẽ làm danh sách từ ba phần tử thành hai. Nếu mục tiêu là giữ ba ô nhưng đánh dấu ô thứ hai là trống, `set(1, null)` diễn tả điều đó. Nếu mục tiêu là tạo danh sách chỉ còn hai phần tử, hãy lọc sang một cấu trúc khác có thể thay kích thước.

Tương tự, thay phần tử thành chuỗi rỗng `""` không xóa vị trí. `set(i, "")` và `remove(i)` có kết quả khác nhau về cả kích thước lẫn ý nghĩa dữ liệu. Chọn một giá trị đánh dấu chỉ phù hợp khi mô hình nghiệp vụ đã định nghĩa giá trị ấy.

Cần đặc biệt chú ý danh sách số nguyên:

~~~java
List<Integer> values = Arrays.asList(10, 20, 30);
values.remove(1);
~~~

Tham số `1` có kiểu `int` nên chọn phép xóa theo chỉ số, tức yêu cầu bỏ phần tử `20`. Dùng `values.remove(Integer.valueOf(20))` chọn phép xóa theo giá trị. Trên danh sách cố định này, cả hai đều không thể hoàn tất khi có phần tử phải xóa. Ép kiểu đúng giúp chọn đúng ý nghĩa của `remove`; nó không bổ sung quyền xóa cho đối tượng.

## 6. Vì sao một lệnh remove hoặc addAll đôi khi không ném lỗi?

Không được dùng một lần gọi không làm thay đổi dữ liệu để kết luận danh sách hỗ trợ thêm/xóa.

Các tình huống điển hình là `remove("không có")`, `addAll` với nguồn rỗng, `removeIf` khi mọi lần kiểm tra đều trả về `false`, hoặc `clear` trên danh sách đang rỗng. Một cách cài đặt có thể kết thúc mà không cần thực hiện bước sửa cấu trúc.

Hợp đồng `Collection` cho phép thao tác tùy chọn không được hỗ trợ vẫn trả về bình thường nếu lời gọi không có tác dụng; nó cũng cho phép ném `UnsupportedOperationException` trong tình huống ấy. Vì thế, không nên viết mã phụ thuộc vào việc “thêm không phần tử chắc chắn không lỗi”. [Java SE 17 — Collection, optional operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

Ví dụ lập luận:

~~~text
remove("Z") trên [A, B]
    không tìm thấy Z
    có thể kết thúc mà chưa yêu cầu xóa vị trí

remove("A") trên [A, B]
    tìm thấy A
    muốn hoàn tất phải bỏ một vị trí
    danh sách cố định không hỗ trợ bước đó
~~~

Sự khác nhau nằm ở đường thực thi và điều kiện dữ liệu, không phải ở việc danh sách bỗng đổi loại sau lần gọi đầu tiên.

Một hàm lọc như sau sẽ có lỗi phụ thuộc đầu vào:

~~~java
// Đoạn minh họa bên trong phương thức, items được truyền từ bên ngoài.
items.removeIf(item -> item == null);
~~~

Nếu `items` là danh sách cố định và hôm nay không có `null`, hàm có thể chưa bộc lộ lỗi. Ngày mai dữ liệu có một `null`, cùng câu lệnh mới chạm tới bước xóa không được hỗ trợ. Kiểm thử chỉ với dữ liệu không cần xóa dễ bỏ sót lỗi thiết kế.

`Collection.removeIf` còn quy định rằng cách cài đặt mặc định duyệt rồi dùng `Iterator.remove` cho phần tử thỏa điều kiện. Thông tin này giải thích vì sao việc gọi điều kiện lọc và việc thực hiện xóa là hai giai đoạn khác nhau; không nên để điều kiện lọc thực hiện tác dụng phụ rồi dựa vào ngoại lệ để “hủy” chúng.

Giải pháp bền vững là biết trước yêu cầu của thuật toán và quyền thay đổi của đầu vào. Đừng thử một thao tác không có tác dụng để thăm dò khả năng, và đừng bắt mọi `UnsupportedOperationException` rồi bỏ qua như thể yêu cầu đã thành công.

## 7. Thay qua ListIterator và qua subList

### 7.1. ListIterator.set không thêm phần tử

`Iterator` thông thường không có phương thức `set`. `ListIterator` có thể thay phần tử vừa được trả về bởi `next` hoặc `previous` nếu danh sách hỗ trợ thay thế. Nó không tự coi vị trí con trỏ là một phần tử đang được chọn.

Đoạn minh họa:

~~~java
List<String> fixed = Arrays.asList("A", "B");
ListIterator<String> editing = fixed.listIterator();

editing.next();
editing.set("X");
~~~

Kết quả là `[X, B]`. `next` đã trả về `A`, nên `set` thay đúng vị trí của `A`. Nếu gọi `set` ngay sau khi tạo bộ duyệt mà chưa gọi `next` hoặc `previous`, điều kiện trạng thái chưa thỏa. Hợp đồng `ListIterator.set` quy định các trạng thái hợp lệ và `IllegalStateException`. [Java SE 17 — ListIterator.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#set(E)).

Hai điều kiện phải đồng thời đúng:

- Bộ duyệt đang có một phần tử vừa được trả về để thay.
- Danh sách phía sau cho phép thay thế phần tử ấy.

Trên `Arrays.asList`, đáp ứng điều kiện trạng thái cho phép `set` hoạt động. Cũng với bộ duyệt đó, `add` cần thêm vị trí nên bị từ chối. `remove` cần bớt vị trí nên cũng không trở thành hợp lệ chỉ vì đã gọi `next`.

Đừng sửa vòng lặp xóa bằng cách chuyển từ `list.remove` sang `iterator.remove` rồi cho rằng đã xử lý xong. Bộ duyệt có thể giải quyết một số yêu cầu về cách duyệt và sửa, nhưng không tự thay đổi hợp đồng thêm/xóa của cấu trúc nền.

### 7.2. subList tiếp tục dùng chung dữ liệu

Với mảng bốn phần tử:

~~~java
String[] days = {"Mon", "Tue", "Wed", "Thu"};
List<String> week = Arrays.asList(days);
List<String> middle = week.subList(1, 3);
middle.set(0, "TUE");
~~~

`middle` chứa các vị trí tương ứng với chỉ số `1` và `2` của `week`. Chỉ số `0` trong danh sách con được ánh xạ về chỉ số `1` trong danh sách gốc. Sau lệnh `set`, mảng thành `[Mon, TUE, Wed, Thu]`.

`subList` là một khung nhìn dùng chung danh sách nền, không phải danh sách độc lập được sao chép ra. Hợp đồng của nó mô tả việc phản ánh thay đổi không cấu trúc giữa hai phía và các thao tác tùy chọn được kế thừa từ danh sách nền. [Java SE 17 — List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

Vì nền là danh sách cố định, `middle.clear()` khi có phần tử vẫn không xóa được. Việc chỉ lấy ra một đoạn không biến đoạn đó thành nơi được phép co giãn. Muốn có một danh sách con độc lập và thêm/xóa được, có thể tạo `new ArrayList<>(week.subList(1, 3))`.

## 8. set được hỗ trợ nhưng vẫn có thể thất bại

`UnsupportedOperationException` chỉ là một nhóm lỗi. Không nên gộp mọi ngoại lệ từ `set` vào kết luận “danh sách không sửa được”.

### 8.1. Sai chỉ số

Với ba phần tử, `set(-1, x)` và `set(3, x)` đều nằm ngoài vùng hợp lệ. Hãy bắt hoặc kiểm tra theo `IndexOutOfBoundsException` khi thực sự cần xử lý lỗi chỉ số; một cách cài đặt có thể dùng lớp con như `ArrayIndexOutOfBoundsException`.

Không nên dùng ngoại lệ để điều khiển vòng lặp thông thường. Điều kiện `i < list.size()` diễn tả ranh giới rõ hơn. Nếu dữ liệu cần nối ở vị trí `size()`, hãy chọn cấu trúc hỗ trợ `add` thay vì cố sửa chỉ số cho `set`.

### 8.2. Kiểu của mảng lúc chạy hẹp hơn kiểu được nhìn thấy qua biến

Đoạn sau biên dịch được:

~~~java
Number[] narrow = new Integer[] {1, 2};
List<Number> numbers = Arrays.asList(narrow);
numbers.set(0, 1.5);
~~~

`1.5` được đóng gói thành `Double`, là một `Number`. Tuy nhiên, đối tượng mảng thật sự là `Integer[]`. Việc lưu một `Double` vào nó vi phạm kiểu thành phần của mảng và ném `ArrayStoreException`.

Đây là hệ quả của kiểm tra lưu phần tử vào mảng lúc chạy. Kiểu tham chiếu rộng hơn không thay đổi kiểu thật của đối tượng mảng. [Java Language Specification 17 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

So sánh hai cách chuẩn bị dữ liệu:

~~~java
// Mảng thật sự là Number[]: có thể chứa Integer hoặc Double.
Number[] broad = new Number[] {1, 2};
List<Number> broadView = Arrays.asList(broad);
broadView.set(0, 1.5);

// Bản sao có cấu trúc riêng: không ghi vào Integer[] ban đầu.
Number[] narrow = new Integer[] {1, 2};
List<Number> detached = new ArrayList<>(Arrays.asList(narrow));
detached.set(0, 1.5);
~~~

Đây là đoạn minh họa, cần các import `Arrays`, `ArrayList` và `List`. Cách thứ nhất chọn đúng loại mảng từ đầu; cách thứ hai chấm dứt việc ghi thay vị trí vào mảng hẹp ban đầu. Chọn theo yêu cầu chia sẻ dữ liệu, không chỉ để làm ngoại lệ biến mất.

### 8.3. null không phải là phép xóa

Mảng tham chiếu `String[]` có thể giữ `null`; thay một vị trí thành `null` trên khung nhìn của nó vẫn giữ nguyên số vị trí. Tuy nhiên, các lệnh sau đó phải xử lý được `null`. Ví dụ `value.toUpperCase(...)` không thể gọi trên một tham chiếu `null`.

Phân biệt giá trị `null` nằm trong mảng với việc bản thân tham chiếu mảng truyền vào `Arrays.asList` là `null`. Trường hợp thứ hai không cung cấp một mảng nền hợp lệ và gây `NullPointerException` khi tạo danh sách. Không nên kiểm tra khả năng chấp nhận phần tử `null` bằng cách truyền một tham chiếu mảng `null`.

## 9. Thay nhiều vị trí không có nghĩa là giao dịch nguyên khối

Một thao tác hợp lệ về kích thước vẫn có thể đang thực hiện dở thì thất bại. `replaceAll` không nên được hiểu là “hoặc thay tất cả, hoặc tự động trả mọi thứ về ban đầu”.

Xét đoạn minh họa:

~~~java
Integer[] amounts = {1, 2, 3};
List<Integer> view = Arrays.asList(amounts);

view.replaceAll(n -> {
    if (n == 2) {
        throw new IllegalStateException("stop at 2");
    }
    return n * 10;
});
~~~

Trong cách cài đặt được chương trình minh chứng bên dưới kiểm tra, phần tử `1` đã đổi thành `10` trước khi hàm gặp `2` và ném lỗi. Mảng lúc ấy là `[10, 2, 3]`. Bắt được ngoại lệ không khôi phục lại giá trị `1`.

Mã nguồn OpenJDK 17 của lớp danh sách nội bộ trong `Arrays` cho thấy việc ghi kết quả `replaceAll` lần lượt vào mảng. Đây là căn cứ cho cách giải thích trạng thái bị thay một phần, không phải lời hứa về tính nguyên tử của mọi cách cài đặt `List`. [OpenJDK 17 — Arrays.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Arrays.java).

Nếu yêu cầu nghiệp vụ là không đụng vào dữ liệu gốc cho đến khi toàn bộ phép tính thành công, có thể tính trên một bản sao trước. Đoạn minh họa cần các import thông thường:

~~~java
List<Integer> working = new ArrayList<>(view);
working.replaceAll(n -> transform(n));
~~~

`transform` ở đây là hàm do ứng dụng định nghĩa, nên đoạn này không phải chương trình độc lập. Trong giai đoạn tính, thay các vị trí của `working` không thay vị trí của `view`. Sau khi kiểm tra thành công, ứng dụng mới quyết định công bố kết quả nào.

Nếu sau đó chép từng vị trí từ `working` về mảng dùng chung, bản thân giai đoạn chép không tự trở thành một giao dịch nguyên khối cho nhiều luồng. Ngoài ra, sao chép tham chiếu sang danh sách mới không ngăn một hàm biến đổi sửa trực tiếp trạng thái của các đối tượng phần tử được dùng chung. Yêu cầu nhất quán cao hơn cần được thiết kế riêng, thay vì suy ra từ tên `replaceAll` hoặc từ việc kích thước không đổi.

## 10. Chọn cấu trúc theo quyền thay đổi cần có

Ba lựa chọn rất dễ bị dùng lẫn:

| Cách tạo | Có thay vị trí bằng set? | Có thêm/xóa? | Quan hệ với mảng nguồn |
| --- | --- | --- | --- |
| `Arrays.asList(array)` | Có, theo chỉ số và kiểu hợp lệ | Không đổi kích thước | Dùng chung các vị trí |
| `new ArrayList<>(Arrays.asList(array))` | Có | Có | Có cấu trúc riêng, ban đầu chép các tham chiếu phần tử |
| `Collections.unmodifiableList(Arrays.asList(array))` | Không qua khung nhìn chỉ đọc | Không qua khung nhìn chỉ đọc | Vẫn nhìn thấy mảng nguồn thay đổi |
| `List.copyOf(Arrays.asList(array))` | Không | Không | Không phản ánh việc thay vị trí ở mảng nguồn; không chấp nhận phần tử null |

Đối với `ArrayList` thông thường, việc có cấu trúc riêng cho phép thêm/xóa và thay vị trí; hàm tạo từ `Collection` là lựa chọn rõ ràng khi cần danh sách làm việc. [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Đối với `Collections.unmodifiableList`, giới hạn nằm trên đường truy cập qua khung nhìn. Nếu mảng nền còn được bên khác nắm giữ, nó vẫn có thể thay đổi. Không nên coi lớp bọc này là một bản chụp độc lập. [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

`List.of` và `List.copyOf` tạo danh sách không cho phép thay phần tử và không chấp nhận `null`. Đây là hợp đồng khác với danh sách cố định của `Arrays.asList`. [Java SE 17 — Unmodifiable Lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable).

Một bản sao cấu trúc cũng chưa phải bản sao sâu. Xét:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> view = Arrays.asList(item);
List<StringBuilder> copy = new ArrayList<>(view);

copy.get(0).append("!");
~~~

Hai danh sách có các vị trí riêng, nhưng cả hai vị trí số `0` vẫn tham chiếu cùng một `StringBuilder`. Đọc `view.get(0)` sẽ thấy `seed!`. Ngược lại, `copy.set(0, new StringBuilder("other"))` chỉ thay vị trí bên `copy`.

Khi cần chấm dứt mọi ảnh hưởng từ thay đổi đối tượng phần tử, phải quyết định cách sao chép từng đối tượng hoặc dùng kiểu phần tử bất biến phù hợp. Không có một phép chuyển từ mảng sang danh sách chung nào tự hiểu quy tắc sao chép sâu của mọi kiểu nghiệp vụ.

### Mảng lấy từ toArray là một trường hợp khác

`Arrays.asList(array)` dùng mảng được đưa vào làm nền; điều đó không có nghĩa mọi phép đổi qua lại giữa mảng và danh sách đều dùng chung chính các vị trí ấy.

Với `String[] snapshot = view.toArray(String[]::new)`, mảng kết quả mới có các vị trí riêng. Thay `snapshot[0]` không ghi vào `view`. Tuy nhiên, nếu phần tử là đối tượng có trạng thái sửa được, các tham chiếu bên trong vẫn có thể cùng trỏ tới một đối tượng.

Hợp đồng `Collection.toArray` là căn cứ để chọn phép chuyển đổi phù hợp với mảng kết quả và kiểu thành phần cần dùng. [Java SE 17 — Collection.toArray](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

## 11. set với một List chứa mảng nguyên thủy

```java
int[] raw = {1, 2};
List<int[]> groups = Arrays.asList(raw);
groups.set(0, new int[] {8, 9});
```

Đây là đoạn minh họa trong phương thức có import `Arrays` và `List`. `groups` chỉ có **một phần tử kiểu `int[]`**, nên `set(0, ...)` thay tham chiếu mảng tại vị trí đó, không sửa hay gán lại biến `raw`. Kích thước `groups` vẫn là `1`. Cách chuyển từng `int` thành `Integer`, kể cả nguồn rỗng và null, được triển khai riêng ở bài kế tiếp.

## 12. Chương trình minh chứng đầy đủ

Lưu toàn bộ mã sau thành **ArrayListChangesDemo.java**. Chương trình dùng API tương thích Java 17 và không cần thư viện bên ngoài. Tên lớp ở đây là tên ví dụ; danh sách cố định từ `Arrays.asList` không phải đối tượng `java.util.ArrayList` có thể co giãn.

Hàm `rejects` kiểm tra ngoại lệ nhận được có thuộc kiểu kỳ vọng hay không. Nó in tên **kiểu kỳ vọng**, nên dòng `IndexOutOfBoundsException` vẫn đúng khi ngoại lệ cụ thể là một lớp con. Nếu thao tác không thất bại hoặc thất bại bằng loại ngoại lệ khác, chương trình dừng bằng lỗi thay vì âm thầm coi đó là kết quả hợp lệ.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class ArrayListChangesDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + expected.getSimpleName());
        }
    }

    public static void main(String[] args) {
        String[] names = {"Lan", "Mai", "An"};
        List<String> view = Arrays.asList(names);
        System.out.println("old=" + view.set(1, "Vy"));
        names[0] = "Ha";
        System.out.println("shared=" + view + " / " + Arrays.toString(names));
        System.out.println("size=" + view.size());
        view.set(2, null);
        System.out.println("null=" + Arrays.toString(names));

        String[] words = {"c", "a", "b"};
        List<String> changes = Arrays.asList(words);
        changes.sort(null);
        System.out.println("sort=" + Arrays.toString(words));
        Collections.reverse(changes);
        System.out.println("reverse=" + Arrays.toString(words));
        changes.replaceAll(s -> s.toUpperCase(Locale.ROOT));
        System.out.println("replaceAll=" + Arrays.toString(words));
        Collections.copy(changes, List.of("X", "Y"));
        System.out.println("copy=" + Arrays.toString(words));

        List<String> blocked = Arrays.asList("A", "B");
        rejects("add", UnsupportedOperationException.class, () -> blocked.add("C"));
        rejects("remove-index", UnsupportedOperationException.class, () -> blocked.remove(0));
        rejects("remove-value", UnsupportedOperationException.class, () -> blocked.remove("A"));
        rejects("clear", UnsupportedOperationException.class, blocked::clear);
        rejects("removeIf", UnsupportedOperationException.class,
                () -> blocked.removeIf(s -> s.equals("A")));
        Iterator<String> iterator = blocked.iterator();
        iterator.next();
        rejects("iterator-remove", UnsupportedOperationException.class, iterator::remove);
        System.out.println("after-rejection=" + blocked);

        ListIterator<String> editing = blocked.listIterator();
        editing.next();
        editing.set("X");
        System.out.println("iterator-set=" + blocked);
        rejects("iterator-add", UnsupportedOperationException.class, () -> editing.add("Y"));

        String[] days = {"Mon", "Tue", "Wed", "Thu"};
        List<String> week = Arrays.asList(days);
        List<String> middle = week.subList(1, 3);
        middle.set(0, "TUE");
        System.out.println("subList=" + Arrays.toString(days));
        rejects("subList-clear", UnsupportedOperationException.class, middle::clear);

        rejects("set-at-size", IndexOutOfBoundsException.class,
                () -> view.set(view.size(), "Out"));
        Number[] narrow = new Integer[] {1, 2};
        List<Number> numbers = Arrays.asList(narrow);
        rejects("runtime-array-type", ArrayStoreException.class, () -> numbers.set(0, 1.5));
        System.out.println("narrow=" + Arrays.toString(narrow));

        Integer[] amounts = {1, 2, 3};
        List<Integer> amountView = Arrays.asList(amounts);
        rejects("operator-failure", IllegalStateException.class,
                () -> amountView.replaceAll(n -> {
                    if (n == 2) {
                        throw new IllegalStateException("stop at 2");
                    }
                    return n * 10;
                }));
        System.out.println("partial=" + Arrays.toString(amounts));

        String[] source = {"A", "B"};
        List<String> fixed = Arrays.asList(source);
        List<String> editable = new ArrayList<>(fixed);
        editable.set(0, "C");
        editable.add("D");
        System.out.println("editable=" + editable + " / source=" + Arrays.toString(source));
        String[] snapshot = fixed.toArray(String[]::new);
        snapshot[0] = "Z";
        System.out.println("snapshot=" + Arrays.toString(snapshot) + " / fixed=" + fixed);
        List<String> readOnly = Collections.unmodifiableList(fixed);
        rejects("readOnly-set", UnsupportedOperationException.class, () -> readOnly.set(0, "X"));
        source[0] = "Q";
        System.out.println("readOnly-shared=" + readOnly);
        rejects("List.of-set", UnsupportedOperationException.class,
                () -> List.of("A", "B").set(0, "X"));

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> itemView = Arrays.asList(item);
        List<StringBuilder> itemCopy = new ArrayList<>(itemView);
        itemCopy.get(0).append("!");
        System.out.println("shared-object=" + itemView.get(0));

        int[] raw = {1, 2};
        List<int[]> groups = Arrays.asList(raw);
        groups.get(0)[0] = 7;
        System.out.println("primitive-size=" + groups.size() + " / raw=" + Arrays.toString(raw));
        groups.set(0, new int[] {8, 9});
        System.out.println("primitive-set=" + Arrays.toString(groups.get(0))
                + " / raw=" + Arrays.toString(raw));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListChangesDemo.java
java ArrayListChangesDemo
~~~

Stdout chính xác:

~~~text
old=Mai
shared=[Ha, Vy, An] / [Ha, Vy, An]
size=3
null=[Ha, Vy, null]
sort=[a, b, c]
reverse=[c, b, a]
replaceAll=[C, B, A]
copy=[X, Y, A]
add -> UnsupportedOperationException
remove-index -> UnsupportedOperationException
remove-value -> UnsupportedOperationException
clear -> UnsupportedOperationException
removeIf -> UnsupportedOperationException
iterator-remove -> UnsupportedOperationException
after-rejection=[A, B]
iterator-set=[X, B]
iterator-add -> UnsupportedOperationException
subList=[Mon, TUE, Wed, Thu]
subList-clear -> UnsupportedOperationException
set-at-size -> IndexOutOfBoundsException
runtime-array-type -> ArrayStoreException
narrow=[1, 2]
operator-failure -> IllegalStateException
partial=[10, 2, 3]
editable=[C, B, D] / source=[A, B]
snapshot=[Z, B] / fixed=[A, B]
readOnly-set -> UnsupportedOperationException
readOnly-shared=[Q, B]
List.of-set -> UnsupportedOperationException
shared-object=seed!
primitive-size=1 / raw=[7, 2]
primitive-set=[8, 9] / raw=[7, 2]
~~~

Mã đã được biên dịch với `--release 17` và chạy kiểm tra trên JDK 24.0.2. Cờ biên dịch kiểm tra mức ngôn ngữ/API Java 17; nó không có nghĩa chương trình đã được chạy trên JVM 17. Dòng `partial` là quan sát từ cách cài đặt đã chạy, không phải cam kết một thuật toán phải để lại đúng trạng thái ấy trên mọi loại `List`.

Đọc kết quả theo từng nhóm:

- `old`, `shared`, `size` và `null` thể hiện thay vị trí, giá trị trả về và việc chia sẻ mảng.
- `sort`, `reverse`, `replaceAll` và `copy` cho thấy thay nhiều vị trí vẫn không cần đổi kích thước.
- Các dòng `UnsupportedOperationException` chứng minh các yêu cầu thêm/xóa được thử với dữ liệu thật sự cần thay đổi cấu trúc.
- `iterator-set` và `subList` cho thấy đường truy cập khác vẫn có thể sửa các vị trí của cùng dữ liệu nền.
- `set-at-size` và `runtime-array-type` tách lỗi chỉ số khỏi lỗi kiểu thành phần mảng.
- `partial` chỉ ra giới hạn khi phép biến đổi thất bại giữa chừng.
- `editable`, `snapshot` và `readOnly-shared` phân biệt bản sao cấu trúc, mảng kết quả riêng và khung nhìn chỉ đọc còn dùng chung dữ liệu.
- `shared-object` và hai dòng `primitive` giúp nhận ra tầng đối tượng phần tử đang bị thay.

Chương trình chạy tuần tự. Các kết quả trên không chứng minh tính an toàn khi nhiều luồng cùng truy cập và sửa dữ liệu.

## 13. Áp dụng trong thiết kế hàm

Giả sử một hàm có nhiệm vụ chuẩn hóa từng tên nhưng phải giữ nguyên số cột của bản ghi. Nhận một danh sách cố định và dùng `set` hoặc `replaceAll` có thể phù hợp, nếu hợp đồng của hàm công bố rõ rằng nó sửa đầu vào và cho phép các giá trị hợp lệ.

Nếu hàm phải bỏ tên rỗng, gộp các phần tử trùng hoặc thêm nhãn tổng kết, yêu cầu số phần tử đã thay đổi. Một bản sao `ArrayList` trước khi xử lý sẽ làm quyền sửa cấu trúc trở nên rõ ràng hơn:

~~~java
// Đoạn minh họa bên trong phương thức.
// incoming là List<String> do bên gọi cung cấp.
List<String> result = new ArrayList<>(incoming);
result.removeIf(name -> name == null || name.isBlank());
result.add("TOTAL");
~~~

Đoạn này không sửa các vị trí của `incoming`. Nó tạo kết quả riêng cho thuật toán cần lọc và nối thêm. Quyết định xem nhãn `TOTAL` có thuộc cùng mô hình dữ liệu hay không là việc của thiết kế ứng dụng; ví dụ chỉ minh họa sự khác biệt về quyền thay đổi.

Khi viết một hàm tổng quát nhận `List<T>`, hãy xác định một trong các hợp đồng:

| Mục đích của hàm | Cách công bố/phân chia trách nhiệm |
| --- | --- |
| Chỉ đọc | Không gọi thao tác sửa và không giả định đầu vào bất biến |
| Sửa giá trị tại chỗ | Nêu rõ yêu cầu đầu vào hỗ trợ thay thế và việc dữ liệu dùng chung có thể bị đổi |
| Thêm/xóa tại chỗ | Nêu rõ yêu cầu đầu vào hỗ trợ thay đổi kích thước |
| Trả kết quả mới | Tạo cấu trúc kết quả phù hợp; nói rõ mức sao chép phần tử |

Không cần ép kiểu sang `ArrayList` để thử lấy quyền sửa. Một cách cài đặt khác cũng có thể hỗ trợ những thao tác cần thiết. Ngược lại, đối tượng do `Arrays.asList` trả về không phải `java.util.ArrayList` thông thường; ép kiểu như vậy không chuyển đổi cấu trúc và có thể gây `ClassCastException`.

Cũng không nên dựa vào tên lớp nội bộ được in ra lúc gỡ lỗi. Các tên như lớp lồng bên trong `Arrays` là chi tiết cài đặt. Quyền thao tác cần được xác định từ cách tạo danh sách và hợp đồng API mà mã đang dùng.

## 14. Thực hành có đáp án

### Bài 1 — Điền các ô đã có

Một hàm nhận `Arrays.asList(new String[2])` và cần ghi `"A"`, `"B"` vào hai ô. Nên dùng `add` hay `set`? Kích thước cuối cùng là bao nhiêu?

**Đáp án:** Dùng `set(0, "A")` rồi `set(1, "B")`. Danh sách vốn đã có hai vị trí chứa `null`, nên kích thước giữ nguyên bằng `2`. `add` yêu cầu tạo thêm vị trí và không đáp ứng hợp đồng của danh sách này.

### Bài 2 — Sắp xếp có sửa mảng không?

Có `String[] data = {"b", "a"}` và `List<String> view = Arrays.asList(data)`. Sau `view.sort(null)`, `data[0]` là gì? Nếu mảng gốc cần giữ nguyên, cần thay đổi cách chuẩn bị dữ liệu như thế nào?

**Đáp án:** `data[0]` là `"a"`. Để không thay thứ tự các vị trí của mảng nguồn, sắp xếp trên một cấu trúc riêng, chẳng hạn `new ArrayList<>(view)`. Việc đổi thuật toán từ `sort` sang `Collections.sort` không tự giải quyết vấn đề dùng chung dữ liệu.

### Bài 3 — Không có lỗi có chứng minh xóa được không?

Một lần gọi `fixed.remove("Z")` trả về `false` với dữ liệu `[A, B]`. Có thể suy ra `fixed.remove("A")` cũng dùng được không?

**Đáp án:** Không. Lần đầu không có phần tử cần xóa nên có thể chưa thực hiện bước sửa cấu trúc. Trên danh sách cố định, lần thứ hai cần bỏ một vị trí và bị từ chối. Hợp đồng thao tác tùy chọn cũng không bảo đảm mọi danh sách đều trả `false` cho lần gọi không có tác dụng ấy.

### Bài 4 — Sửa lỗi set ở cuối

Với `List<String> fixed = Arrays.asList("A", "B")`, `fixed.set(fixed.size(), "C")` gây lỗi. Đổi chỉ số thành `fixed.size() - 1` có phải cách thêm `"C"` không?

**Đáp án:** Không. Chỉ số mới làm lệnh trở thành thay `"B"` bằng `"C"`, kết quả có hai phần tử. Nếu cần giữ cả `A`, `B` và thêm `C`, tạo danh sách hỗ trợ tăng kích thước rồi dùng `add`.

### Bài 5 — Vì sao đúng kiểu Number vẫn lỗi?

`Number[] data = new Integer[] {4, 5}` được bọc thành `List<Number>`. Tại sao `set(0, 2.5)` không hợp lệ lúc chạy?

**Đáp án:** `Double` phù hợp với `Number` nhưng không thể lưu vào đối tượng mảng thật sự có kiểu `Integer[]`. Lỗi là `ArrayStoreException`. Tạo mảng thật sự kiểu `Number[]` hoặc một bản sao danh sách có cấu trúc riêng tùy nhu cầu; không giải thích lỗi này thành việc mọi `set` đều bị cấm.

### Bài 6 — Bản sao đã tách mọi thay đổi chưa?

`copy = new ArrayList<>(Arrays.asList(builder))` với một `StringBuilder`. Sau `copy.get(0).append("!")`, đối tượng `builder` bên ngoài có thay đổi không? Nếu dùng `copy.set(0, new StringBuilder("X"))` thì sao?

**Đáp án:** Lệnh `append` sửa chính đối tượng đang được dùng chung, nên `builder` thay đổi. Lệnh `set` thay vị trí trong `copy` bằng một tham chiếu khác, không gán lại biến `builder` hoặc vị trí của danh sách nguồn. Cần phân biệt sửa đối tượng phần tử và thay tham chiếu nằm ở một vị trí.

### Bài 7 — Khung nhìn chỉ đọc có phải ảnh chụp không?

Tạo `readOnly = Collections.unmodifiableList(Arrays.asList(array))`, rồi bên giữ mảng gán `array[0] = "Q"`. `readOnly.get(0)` có thấy `"Q"` không? `readOnly.set(0, "X")` có hợp lệ không?

**Đáp án:** Có nhìn thấy `"Q"` vì vẫn dùng chung dữ liệu nền. Nhưng thay qua `readOnly.set` bị từ chối. Nếu cần ảnh chụp các vị trí không phản ánh thay đổi nguồn, hãy chọn cách sao chép; nếu còn yêu cầu không cho sửa kết quả, áp dụng thêm hợp đồng chỉ đọc phù hợp.

### Bài 8 — Kiểu phần tử quyết định ý nghĩa của set

Với `int[] raw = {1, 2}` và `List<int[]> groups = Arrays.asList(raw)`, `groups.size()` bằng bao nhiêu? Sau `groups.set(0, new int[] {3, 4})`, biến `raw` có trỏ sang mảng mới không?

**Đáp án:** Kích thước là `1` vì phần tử duy nhất là tham chiếu tới một `int[]`. `set` thay tham chiếu đó trong danh sách; biến `raw` không bị gán lại. Để có danh sách các số nguyên riêng lẻ, phải chuyển từng số sang phần tử `Integer` theo một cách tạo danh sách thích hợp.

## 15. Các điểm cần giữ đúng khi dùng Arrays.asList

Trước một thao tác sửa, hãy xác định phần tử nào đang được nhắm tới, vị trí ấy đã tồn tại chưa, kiểu mảng thật sự có chứa được giá trị mới không, và thuật toán có cần tăng/giảm số vị trí không. Sau đó xét những nơi cùng dùng mảng hoặc đối tượng phần tử.

Mô hình cốt lõi của bài là: **`set` thay nội dung một vị trí hiện có; thêm/xóa thay số vị trí; `Arrays.asList` chỉ cung cấp nhóm quyền thứ nhất trên mảng nền.** Từ mô hình đó có thể giải thích các ví dụ sắp xếp, bộ duyệt, danh sách con, lỗi kiểu và cách tạo bản sao mà không phải học thuộc từng ngoại lệ rời rạc.
