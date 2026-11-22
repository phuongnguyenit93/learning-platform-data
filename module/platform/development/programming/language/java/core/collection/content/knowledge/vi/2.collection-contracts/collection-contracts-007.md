# Phân biệt thay đổi cấu trúc, thay giá trị và sửa đối tượng phần tử

Cùng được gọi là “sửa collection”, nhưng ba thao tác dưới đây tác động lên những lớp dữ liệu khác nhau:

```java
students.add(new Student("S3", "Chi"));
students.set(0, new Student("S4", "Dung"));
students.get(0).rename("Anh");
```

Một thao tác thêm phần tử vào danh sách; một thao tác thay phần tử ở vị trí có sẵn; thao tác còn lại sửa chính đối tượng đang được danh sách tham chiếu.

Phân biệt chúng giúp hiểu iterator, bản sao nông, view, collection không cho sửa và các lỗi với khóa có thể thay đổi. Nếu chỉ nhìn kết quả in ra hoặc chỉ nhìn `size()`, ta dễ bỏ qua điều thực sự đã thay đổi.

Bài dùng Java 17 và lấy `ArrayList` làm mô hình chính. Phần mở rộng sang `Map`, `Set` và các cấu trúc khác luôn cần đối chiếu hợp đồng cụ thể. Các đoạn Java ngắn là minh họa theo ngữ cảnh; chương trình đầy đủ cùng lệnh biên dịch và kết quả nằm ở phần thực nghiệm.

## 1. Vì sao cần ba khái niệm riêng?

Giả sử danh sách quản lý hai sinh viên. Các yêu cầu sau khác nhau:

| Yêu cầu | Điều thực sự cần làm |
| --- | --- |
| Tiếp nhận thêm sinh viên | Thêm một phần tử vào cấu trúc chứa |
| Thay sinh viên ở vị trí 0 bằng người khác | Đổi phần tử được gắn với một vị trí đang tồn tại |
| Sửa tên của sinh viên đang ở vị trí 0 | Đổi trạng thái của đối tượng đã được tham chiếu |
| Đổi thứ tự hiển thị | Sắp xếp lại quan hệ vị trí và phần tử |
| Đọc được danh sách nhưng không cho người ngoài sửa | Xác định lớp dữ liệu nào cần được bảo vệ |

Nếu người thiết kế nói “danh sách chỉ đọc”, cần hỏi thêm:

- Không được thêm hoặc xóa?
- Không được thay phần tử?
- Không được sửa thuộc tính của phần tử?
- Có được thấy thay đổi do bên khác thực hiện không?

Những câu hỏi này không thể được giải quyết bằng một nhãn “mutable” hoặc “immutable” thiếu ngữ cảnh.

## 2. Mô hình ba lớp: cấu trúc, tham chiếu và đối tượng

Với collection chứa đối tượng, hãy hình dung ba lớp:

```text
Biến students
    |
    v
Đối tượng danh sách
    vị trí 0 ----> đối tượng Student S1, tên "An"
    vị trí 1 ----> đối tượng Student S2, tên "Binh"
```

### 2.1. Lớp cấu trúc chứa

Danh sách quản lý các vị trí, kích thước và các tham chiếu phần tử. `ArrayList` còn có vùng lưu trữ mảng bên trong với sức chứa riêng.

Với map, cấu trúc quản lý các ánh xạ khóa–giá trị. Với tập hợp, nó quản lý các phần tử theo quy tắc bình đẳng, băm hoặc so sánh.

### 2.2. Lớp gắn phần tử với vị trí hoặc khóa

Một vị trí trong danh sách đang chứa tham chiếu đến đối tượng nào? Một khóa trong map đang gắn với giá trị nào?

Thay tham chiếu ở vị trí 0 có thể không đổi số phần tử, nhưng đối tượng được truy cập qua vị trí đó đã khác.

### 2.3. Lớp trạng thái của phần tử

Đối tượng `Student` có trường `name`. Gọi phương thức đổi tên tác động lên đối tượng này, không nhất thiết gọi bất kỳ phương thức sửa nào của danh sách.

Các lớp không tách rời hoàn toàn về ý nghĩa nghiệp vụ: đổi một trường có thể làm đổi kết quả `equals`, `hashCode`, thứ tự hoặc cách hiển thị. Tuy nhiên, đường tác động và cơ chế collection quan sát được vẫn khác nhau.

## 3. Thay đổi cấu trúc là gì?

### 3.1. Trường hợp điển hình: thêm và xóa phần tử

Với một `ArrayList` đang có hai phần tử:

```java
students.add(new Student("S3", "Chi"));
students.remove(0);
```

Lời gọi đầu thêm một vị trí phần tử; lời gọi sau loại một vị trí và làm các phần tử phía sau dịch chỉ số.

Đó là các thay đổi cấu trúc điển hình. Một iterator đã tạo trước đó có thể không còn duyệt đúng theo cấu trúc mà nó đang theo dõi.

Các thao tác như `addAll`, `removeAll`, `retainAll`, `removeIf` hoặc `clear` cũng có thể tác động lên cấu trúc nếu thực sự thêm hoặc xóa phần tử. Cần xét tác dụng cụ thể, không chỉ tên phương thức.

### 3.2. Không định nghĩa bằng “size có đổi không?”

`size()` giúp quan sát số phần tử logic, nhưng không phải định nghĩa tổng quát của thay đổi cấu trúc.

Ví dụ, chuỗi thao tác:

```java
students.add(new Student("S3", "Chi"));
students.remove(students.size() - 1);
```

đưa kích thước về như cũ. Điều đó không khôi phục hiệu lực của một iterator đã tồn tại trước hai lời gọi.

Với `ArrayList`, tài liệu còn nhắc đến việc thay đổi rõ ràng kích thước vùng mảng nền. Sức chứa và số phần tử là hai đại lượng khác nhau; không suy luận về hiệu lực iterator chỉ bằng so sánh `size()` trước và sau. Chi tiết được mô tả trong [ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 3.3. Khái niệm phụ thuộc cấu trúc và hợp đồng lớp

Với `HashMap`, thêm một ánh xạ mới hoặc xóa ánh xạ là thay đổi cấu trúc; chỉ thay giá trị của khóa đã có không được xem là thay đổi cấu trúc theo định nghĩa của lớp đó.

Một `LinkedHashMap` cấu hình theo thứ tự truy cập còn khác: thao tác truy cập có thể ảnh hưởng thứ tự duyệt và được xem là thay đổi cấu trúc. Vì vậy, không thể đưa ra quy tắc chung “gọi `get` luôn chỉ đọc, nên không bao giờ ảnh hưởng iterator”. Xem [LinkedHashMap: chế độ access-order và structural modification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Ở mức lớp nền, `AbstractList` cũng diễn đạt thay đổi có thể làm xáo trộn cách duyệt. Điều cần học là **đọc định nghĩa của kiểu đang dùng**, thay vì coi một định nghĩa của `ArrayList` là định nghĩa cho toàn bộ framework.

## 4. Thay giá trị: giữ vị trí nhưng đổi phần tử ở đó

### 4.1. List.set không có nghĩa sửa đối tượng cũ

Đoạn minh họa:

```java
Student previous = students.set(0, new Student("S9", "Lan"));
```

Sau lời gọi:

- Vị trí 0 vẫn tồn tại.
- Kích thước danh sách không tăng hoặc giảm.
- Vị trí 0 tham chiếu đến đối tượng mới.
- Giá trị trả về là phần tử trước đó ở vị trí này.
- Đối tượng cũ không tự bị sửa thành đối tượng mới.

Có thể hình dung:

```text
Trước:
    students[0] ----> Student S1, tên "An"

Sau set:
    students[0] ----> Student S9, tên "Lan"
    previous    ----> Student S1, tên "An"
```

Với `ArrayList`, thay giá trị phần tử bằng `set` không phải thay đổi cấu trúc. Đó là đặc điểm cụ thể cần phân biệt với việc thêm hoặc xóa.

### 4.2. Kết quả đọc đã thay đổi dù không phải thay đổi cấu trúc

Một lời gọi `students.get(0)` sau `set` trả đối tượng khác so với trước.

Do đó:

- “Không đổi cấu trúc” không có nghĩa dữ liệu quan sát được không đổi.
- “Không có lỗi iterator” không có nghĩa đang duyệt một bản chụp cố định.
- “Không đổi số lượng” không có nghĩa thay đổi đó không quan trọng về nghiệp vụ.

Một hệ thống chấm điểm có thể giữ nguyên số sinh viên nhưng thay nhầm người ở một vị trí. Số lượng đúng không chứng minh nội dung đúng.

### 4.3. Với String hoặc Integer

`String` và các lớp bao như `Integer` là các giá trị bất biến. Khi muốn đổi một chuỗi hoặc một số trong danh sách, thông thường ta gắn giá trị mới vào vị trí đó:

```java
List<Integer> scores = new ArrayList<>(List.of(7, 8));
scores.set(0, scores.get(0) + 1);
```

Danh sách trở thành `[8, 8]`. Biểu thức trên không sửa đối tượng `Integer` đang mang giá trị 7 thành 8; nó tính giá trị mới rồi thay phần tử ở vị trí 0.

Điều này khác với gọi setter trên một đối tượng có thể thay đổi.

### 4.4. Không phải collection nào cũng có thao tác set

`set(index, value)` thuộc `List`, không thuộc hợp đồng chung của mọi `Collection`. Tập hợp không có vị trí phần tử theo chỉ số như danh sách.

Với map, thao tác thay giá trị theo khóa mang ý nghĩa tương ứng về liên kết, nhưng phải dùng hợp đồng map. Không chuyển cách gọi phương thức của list sang set hoặc map theo tên một cách máy móc.

## 5. Sửa đối tượng phần tử: tham chiếu giữ nguyên, trạng thái đổi

Xét:

```java
Student student = students.get(0);
student.rename("Anh");
```

Danh sách vẫn giữ tham chiếu đến cùng đối tượng. Phương thức `rename` thay trường tên bên trong đối tượng đó.

Hình dung:

```text
Trước:
    students[0] ----> Student S1, tên "An"

Sau rename:
    students[0] ----> cùng Student S1, tên "Anh"
```

Danh sách không được yêu cầu tăng số phần tử hoặc thay tham chiếu ở vị trí 0. Nếu in danh sách, chuỗi hiển thị có thể đổi vì `toString()` của phần tử đọc trạng thái mới.

### 5.1. Collection không tự quan sát mọi setter

Một `ArrayList` thông thường không tự nhận thông báo rằng đối tượng bên trong vừa đổi tên. Không có quy tắc chung khiến mọi thay đổi trường tự cập nhật bộ đếm sửa cấu trúc của collection.

Điều đó giải thích vì sao một setter có thể làm nội dung kết quả đổi mà iterator vẫn tiếp tục.

### 5.2. Một phần tử có thể được chia sẻ ở nhiều nơi

Nếu hai danh sách cùng chứa tham chiếu đến một `Student`, đổi tên qua danh sách thứ nhất có thể được nhìn thấy qua danh sách thứ hai.

Cũng có thể cùng một đối tượng xuất hiện ở hai vị trí của một list. Sửa đối tượng đó qua vị trí thứ nhất khiến đọc vị trí thứ hai cũng thấy trạng thái mới, vì không có hai đối tượng độc lập để sửa.

### 5.3. Sửa đối tượng có thể rất quan trọng dù collection không đổi cấu trúc

Đổi trường `name` chỉ ảnh hưởng hiển thị nếu nó không tham gia các quy tắc khác. Nhưng nếu trường bị đổi được dùng trong bình đẳng, băm hoặc thứ tự, collection có thể không còn duy trì được các giả định ban đầu.

Phải phân biệt:

- Thao tác có được bộ đếm sửa cấu trúc phát hiện hay không.
- Trạng thái sau thao tác có còn phù hợp hợp đồng collection và nghiệp vụ hay không.

Hai câu hỏi này độc lập.

## 6. Gán lại biến cục bộ không thay phần tử trong danh sách

Đây là một nhầm lẫn thường gặp:

```java
Student local = students.get(0);
local = new Student("S9", "Local");
```

Lời gọi `get` ban đầu đưa một tham chiếu vào biến `local`. Phép gán tiếp theo đổi riêng biến `local`, không sửa vị trí 0 của danh sách.

So sánh ba cách:

| Câu lệnh | Thứ được thay đổi |
| --- | --- |
| `local = new Student(...)` | Tham chiếu trong biến cục bộ |
| `students.set(0, new Student(...))` | Phần tử gắn với vị trí 0 |
| `local.rename("Anh")` | Trạng thái đối tượng mà local đang trỏ tới |

Điều này cũng đúng với biến vòng lặp `for-each`:

```java
for (Student student : students) {
    student = new Student("S9", "Replacement");
}
```

Đoạn trên không thay mọi phần tử trong danh sách. Nó chỉ gán lại biến vòng lặp ở từng lượt.

Nếu muốn thay các phần tử, dùng thao tác phù hợp như `ListIterator.set`, truy cập theo chỉ số trên kiểu hỗ trợ phù hợp, hoặc tạo một danh sách kết quả mới. Không dùng gán lại biến vòng lặp thay cho thao tác sửa collection.

## 7. Bảng phân biệt trên ArrayList

Bảng dưới giả định thao tác được hỗ trợ và đối số hợp lệ. Cột cấu trúc lấy `ArrayList` làm phạm vi, không áp dụng vô điều kiện cho mọi lớp.

| Thao tác | Kích thước logic | Tham chiếu phần tử | Trạng thái đối tượng cũ | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `list.add(newValue)` | Tăng | Thêm phần tử | Không tự sửa | Thay đổi cấu trúc |
| `list.remove(i)` | Giảm | Bỏ phần tử ở vị trí | Không tự sửa hay hủy đối tượng | Thay đổi cấu trúc |
| `list.set(i, newValue)` | Giữ nguyên | Thay tại vị trí có sẵn | Không tự sửa | Thay phần tử, không phải thay đổi cấu trúc của ArrayList |
| `list.get(i).rename(...)` | Giữ nguyên | Giữ nguyên | Bị sửa bởi phương thức phần tử | Sửa trạng thái đối tượng |
| `local = newValue` | Giữ nguyên | Không sửa phần tử của list | Không tự sửa | Gán lại biến riêng |
| `list.get(i)` | Giữ nguyên | Giữ nguyên | Không tự sửa | Đọc phần tử trong cách dùng thông thường |

Bỏ tham chiếu khỏi list không có nghĩa đối tượng lập tức bị thu hồi bộ nhớ. Đối tượng có thể còn được biến khác hoặc collection khác tham chiếu; việc thu hồi bộ nhớ còn phụ thuộc khả năng tiếp cận của toàn bộ đồ thị đối tượng.

Thay vị trí bằng chính tham chiếu cũ cũng khác với thay bằng một đối tượng mới. Việc có lời gọi phương thức chưa đủ để kết luận nội dung nghiệp vụ đã khác.

## 8. Iterator liên quan thế nào đến ba loại thay đổi?

### 8.1. Vì sao thay đổi cấu trúc có thể làm iterator không còn hợp lệ?

Iterator đang giữ tiến trình duyệt: vị trí tiếp theo, phần tử vừa trả về và thông tin cần để phát hiện một số thay đổi không hợp lệ.

Một thao tác xóa bên ngoài iterator có thể làm các chỉ số dịch đi; thao tác thêm có thể làm tập phần tử mà iterator phải đi qua thay đổi. Cơ chế fail-fast của nhiều lớp dùng để phát hiện những tình huống như vậy.

`ConcurrentModificationException` có thể xảy ra ngay trong chương trình một luồng. Tên ngoại lệ không chứng minh có hai luồng.

### 8.2. set trên ArrayList không tạo bản chụp cho iterator

Với `ArrayList`, thay một vị trí bằng `set` không phải thay đổi cấu trúc. Iterator đọc phần tử sau đó có thể nhìn thấy phần tử mới ở vị trí tương ứng.

Nếu iterator đã trả đối tượng cũ trước khi `set`, biến bên ngoài đang giữ đối tượng cũ không tự chuyển sang trỏ đối tượng mới. Thời điểm đọc và việc chia sẻ tham chiếu vẫn quan trọng.

Không tổng quát hành vi này sang mọi loại iterator. Ví dụ, iterator dạng bản chụp của một lớp khác có hợp đồng riêng.

### 8.3. Sửa trường của phần tử không mặc nhiên bị fail-fast phát hiện

Setter của `Student` không phải lời gọi thêm hoặc xóa trên list. Iterator thường vẫn trả cùng đối tượng với trạng thái mới.

Điều đó không phải một bảo đảm rằng ứng dụng được phép sửa mọi trường trong mọi cấu trúc. Với tập băm, cây hoặc heap, những trường liên quan đến vị trí logic cần được xử lý rất thận trọng.

### 8.4. Thay đổi cấu trúc qua đúng iterator có thể được hỗ trợ

Nếu muốn xóa phần tử đang duyệt, có thể dùng:

```java
Iterator<Student> iterator = students.iterator();
while (iterator.hasNext()) {
    Student student = iterator.next();
    if (shouldRemove(student)) {
        iterator.remove();
    }
}
```

Đây là đoạn minh họa cần có điều kiện `shouldRemove` do ứng dụng định nghĩa. Nó không phải chương trình hoàn chỉnh.

Thao tác vẫn xóa phần tử và vẫn thay đổi cấu trúc. Điểm khác là thực hiện qua iterator đang quản lý tiến trình duyệt, theo hợp đồng cho phép.

`Iterator.remove` là thao tác tùy chọn. Cần có phần tử hợp lệ từ `next()` và tuân thủ giới hạn gọi; không phải iterator nào cũng hỗ trợ xóa.

Với `ListIterator`, `set` dùng để thay phần tử vừa duyệt, còn `add` chèn phần tử theo vị trí con trỏ. Các trạng thái hợp lệ và thao tác được hỗ trợ phải đọc ở [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html) và [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### 8.5. Fail-fast là công cụ phát hiện lỗi

Không suy luận:

```text
không có ConcurrentModificationException
    ⇒ không có thay đổi
    ⇒ dữ liệu an toàn
    ⇒ an toàn giữa nhiều luồng
```

Chuỗi suy luận này sai ở cả ba bước.

Việc phát hiện có tính cố gắng tốt nhất, không phải khóa bảo vệ dữ liệu. Mã đúng phải tổ chức thao tác hợp lệ ngay từ đầu; không chờ ngoại lệ để quyết định thuật toán có đúng hay không.

## 9. Cùng kích thước nhưng iterator vẫn có thể bị ảnh hưởng

Ngoài ví dụ thêm rồi xóa, còn có thao tác thay đổi thứ tự hoặc cơ chế duyệt mà không đổi số lượng.

### 9.1. Sắp xếp và thay thế hàng loạt

`sort` làm thay đổi quan hệ vị trí và phần tử. `replaceAll` có thể thay nhiều phần tử.

Không được lấy quy tắc riêng “`ArrayList.set` không phải structural modification” rồi suy ra mọi phương thức giữ nguyên kích thước sẽ không làm iterator cũ mất hiệu lực.

Trong triển khai OpenJDK 17, `ArrayList.sort` và `ArrayList.replaceAll` cập nhật bộ đếm sửa đổi phục vụ kiểm tra iterator. Đây là chi tiết triển khai cần được phân biệt với quy tắc của một lời gọi `set`; xem [mã nguồn ArrayList trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

Cách dùng rõ ràng là hoàn tất sắp xếp hoặc thay thế trước khi tạo iterator mới, thay vì tái sử dụng iterator đang có.

### 9.2. Map theo thứ tự truy cập

Một `LinkedHashMap` ở chế độ access-order có thể đổi thứ tự duyệt khi truy cập một ánh xạ. Số ánh xạ vẫn không đổi.

Bài học không phải “mọi `get` đều sửa cấu trúc”, mà là “tên phương thức và số phần tử chưa đủ để phân loại tác động nếu chưa biết cấu hình cùng lớp triển khai”.

### 9.3. modCount không phải số phiên bản nghiệp vụ

Ở một số lớp, bộ đếm như `modCount` hỗ trợ iterator. Nó không phải:

- Tổng số lần thay đổi dữ liệu nghiệp vụ.
- Mã giao dịch.
- Dấu vết mọi setter của phần tử.
- Cơ chế đồng bộ giữa luồng.
- API công khai để ứng dụng kiểm tra tính bất biến.

Đọc [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) giúp hiểu mục đích của bộ đếm, nhưng không nên thiết kế logic nghiệp vụ phụ thuộc vào trường bảo vệ của một lớp triển khai.

## 10. Khả năng sửa có nhiều tầng

### 10.1. final chỉ hạn chế gán lại biến

Đoạn minh họa:

```java
final List<String> names = new ArrayList<>();
names.add("An");
names.set(0, "Binh");
```

Hai lời gọi đều hợp lệ. `final` không làm đối tượng danh sách bất biến; nó ngăn gán lại chính biến `names` sang một list khác.

Tương tự, trường tham chiếu `final` trong một lớp không tự làm mọi đối tượng mà nó trỏ tới bất biến sâu.

### 10.2. Kích thước cố định không đồng nghĩa không cho sửa

Một list từ `Arrays.asList(array)` có kích thước cố định và gắn với mảng:

- Có thể thay phần tử bằng `set`.
- Không thể thêm hoặc xóa phần tử để đổi kích thước.
- Thay phần tử qua list hoặc mảng có thể được nhìn thấy qua phía còn lại.

Nó minh họa sự khác nhau giữa “không sửa kích thước” và “không được thay phần tử”.

### 10.3. List.of không cho sửa qua API danh sách

Một list tạo bằng `List.of(...)` không cho thêm, xóa hoặc thay phần tử bằng `set`.

Như vậy, `set` là thao tác không đổi cấu trúc đối với `ArrayList` nhưng vẫn có thể bị cấm trên một list khác. **Phân loại tác động và khả năng hỗ trợ thao tác là hai điều cần kiểm tra riêng.**

### 10.4. Unmodifiable không làm phần tử bất biến

Nếu một list không cho sửa chứa `Student` có setter:

```java
readOnlyStudents.get(0).rename("Anh");
```

lời gọi này có thể vẫn hợp lệ. Wrapper ngăn các phương thức sửa cấu trúc hoặc thay phần tử qua list, nhưng không biến đối tượng trả về từ `get` thành một kiểu chỉ đọc.

Nếu người gọi được phép lấy tham chiếu tới một đối tượng có thể sửa, họ có thể gọi phương thức của đối tượng đó theo quyền mà API cung cấp.

Tài liệu [Collection: unmodifiable collections và view](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) phân biệt rõ collection không cho sửa với dữ liệu bất biến.

## 11. View, bản sao nông và ảnh chụp dữ liệu

### 11.1. View không cho sửa vẫn có thể nhìn thấy nguồn đổi

`Collections.unmodifiableList(source)` tạo góc nhìn không cho sửa qua wrapper, không tách dữ liệu khỏi `source`.

Nếu bên giữ nguồn gọi `source.add(...)`, kích thước đọc qua view có thể tăng. Nếu nguồn thay phần tử hoặc sửa đối tượng phần tử, view cũng có thể phản ánh thay đổi tương ứng.

Đây không phải lỗi của wrapper; đó là hợp đồng của một view sống theo dữ liệu nền.

### 11.2. Bản sao nông tách danh sách, vẫn chia sẻ phần tử

Với:

```java
List<Student> copy = new ArrayList<>(source);
```

- `copy` là đối tượng danh sách khác.
- Thêm hoặc xóa ở `source` không tự thêm hoặc xóa ở `copy`.
- `source.set(i, another)` không thay tham chiếu đang nằm ở `copy.get(i)`.
- Sửa đối tượng mà hai phía cùng tham chiếu có thể được thấy qua cả hai danh sách.

Không mâu thuẫn: cấu trúc đã tách, đối tượng phần tử vẫn chung.

### 11.3. List.copyOf không phải bản sao sâu

`List.copyOf(source)` cung cấp list không cho sửa với các phần tử của nguồn tại thời điểm gọi. Thay đổi về thêm, xóa hoặc thay phần tử của nguồn sau đó không làm kết quả tự đổi theo như một view.

Tuy nhiên, các phần tử vẫn có thể là những đối tượng dùng chung. Setter trên một phần tử có thể làm dữ liệu quan sát qua cả hai phía thay đổi.

Không dựa vào giả định `copyOf` luôn cấp phát một list mới khác tham chiếu; điều cần dựa vào là hợp đồng kết quả, quy tắc `null` và giới hạn không sao chép sâu.

### 11.4. Khi cần tách cả trạng thái phần tử

Cần xác định bản chụp nghiệp vụ phải giữ những dữ liệu nào, rồi tạo các đối tượng giá trị hoặc bản sao phần tử phù hợp.

Nếu một sinh viên chứa danh sách địa chỉ, sao chép đối tượng sinh viên nhưng tiếp tục dùng chung danh sách địa chỉ vẫn chưa tách toàn bộ trạng thái.

Một `record` có các trường tham chiếu cũng không tự sao chép sâu hoặc làm bất biến những đối tượng được tham chiếu. Thiết kế phần tử bất biến phải xét cả dữ liệu bên trong.

## 12. View một phần và tác động trở lại nguồn

Với `subList`, ta đang nhìn một vùng của list nền.

- `subList.set(...)` có thể thay phần tử tương ứng trong list nền khi thao tác được hỗ trợ.
- Xóa qua sublist có thể làm list nền giảm kích thước.
- Sửa đối tượng phần tử có thể nhìn thấy từ cả hai phía.
- Nếu list nền bị sửa cấu trúc ngoài đường đi được hợp đồng cho phép của view, không được tiếp tục coi sublist là một vùng dữ liệu độc lập còn hợp lệ.

Đừng diễn giải việc chưa có ngoại lệ là view chắc chắn còn đúng. Hợp đồng `List.subList` phải được kiểm tra khi nguồn có thể thay đổi; xem [List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Tương tự, `keySet`, `values` và `entrySet` của map là các góc nhìn dữ liệu. Việc thay giá trị của một ánh xạ khác với xóa khóa; một view đọc giá trị có thể thấy dữ liệu khác dù tập khóa vẫn giữ nguyên.

## 13. Với Set, Map và cấu trúc có thứ tự

### 13.1. HashSet: sửa thuộc tính tham gia băm

Giả sử phần tử dùng trường `code` trong `equals` và `hashCode`. Nếu đổi `code` sau khi đã thêm vào `HashSet`, đối tượng vẫn ở vị trí nội bộ được xác định theo trạng thái trước đó; tập không tự nhận setter rồi bố trí lại.

Hậu quả có thể là tra cứu, xóa hoặc quy tắc không trùng không còn hoạt động như mong đợi. Hợp đồng `Set` không bảo đảm hành vi khi phần tử bị thay đổi theo cách ảnh hưởng bình đẳng trong lúc còn thuộc tập; xem [Set của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

Không coi một lần thử cho kết quả cụ thể là bảo đảm tổng quát cho những phần tử đã vi phạm điều kiện này.

Cách thiết kế tốt là dùng thông tin định danh ổn định trong bình đẳng. Khi thật sự cần đổi trường liên quan, cần loại phần tử trước khi đổi, rồi thêm lại theo trạng thái mới và xử lý khả năng trùng. Chỉ thêm lại sau khi đã đổi mà không loại trạng thái cũ có thể không sửa được vấn đề.

### 13.2. Map: thay value khác với sửa key

Với `HashMap`:

```java
map.put(existingKey, anotherValue);
```

thay giá trị của khóa đã có không giống việc thêm một ánh xạ với khóa mới. Tập khóa có thể giữ nguyên trong khi giá trị quan sát được đã đổi.

Nhưng nếu sửa trạng thái của chính đối tượng đang làm khóa, nhất là các trường tham gia `equals` hoặc `hashCode`, ta gặp rủi ro tương tự phần tử của `HashSet`.

Khóa nên có giá trị ổn định. Sửa giá trị nghiệp vụ thường nên diễn đạt bằng thay value hoặc thao tác trên đối tượng value theo quy tắc sở hữu rõ ràng. Xem [HashMap: structural modification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

### 13.3. TreeSet hoặc TreeMap: sửa trường dùng để so sánh

Cây được tổ chức theo quan hệ so sánh khi thêm phần tử hoặc khóa. Nếu đối tượng đổi trường dùng trong comparator, cây không tự sắp lại khi setter được gọi.

Đừng kết luận an toàn chỉ vì không có thay đổi số lượng hoặc không có lỗi iterator. Cần giữ tiêu chí so sánh ổn định trong thời gian đối tượng nằm ở cấu trúc.

Đây là ví dụ rõ về sự khác nhau giữa không thay đổi cấu trúc qua API và làm hỏng giả định mà cấu trúc đang dựa vào.

## 14. Chương trình Java hoàn chỉnh

Chương trình dưới đây đặt ba loại thay đổi cạnh nhau và quan sát hai kiểu chia sẻ: view dùng cùng dữ liệu nền, bản sao nông dùng khác list nhưng chung phần tử.

Lưu vào tệp `CollectionMutationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CollectionMutationDemo {
    static final class Student {
        private final String id;
        private String name;

        Student(String id, String name) {
            this.id = id;
            this.name = name;
        }

        void rename(String newName) {
            name = newName;
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    public static void main(String[] args) {
        List<Student> students = new ArrayList<>(List.of(
                new Student("S1", "An"),
                new Student("S2", "Binh")));

        List<Student> shallowCopy = new ArrayList<>(students);
        List<Student> readOnly = Collections.unmodifiableList(students);

        Iterator<Student> beforeSet = students.iterator();
        Student replaced = students.set(1, new Student("S3", "Chi"));

        System.out.println("size after set: " + students.size());
        System.out.println("replaced object: " + replaced);
        System.out.println("iterator after set: "
                + beforeSet.next() + ", " + beforeSet.next());

        students.get(0).rename("Anh");
        System.out.println("students after rename: " + students);
        System.out.println("shallow copy: " + shallowCopy);

        Student local = students.get(0);
        local = new Student("S9", "Local");
        System.out.println("local variable: " + local);
        System.out.println("list first element: " + students.get(0));

        readOnly.get(0).rename("Annie");
        System.out.println("rename through readOnly: " + students.get(0));

        try {
            readOnly.set(0, new Student("S8", "Blocked"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("readOnly set: blocked");
        }

        students.add(new Student("S4", "Dung"));
        System.out.println("source size after add: " + students.size());
        System.out.println("readOnly size after add: " + readOnly.size());
        System.out.println("shallow copy size: " + shallowCopy.size());

        List<String> codes = new ArrayList<>(List.of("A", "B"));
        Iterator<String> stale = codes.iterator();
        codes.add("C");
        try {
            stale.next();
        } catch (ConcurrentModificationException ex) {
            System.out.println("stale iterator: ConcurrentModificationException");
        }

        Iterator<String> remover = codes.iterator();
        while (remover.hasNext()) {
            if (remover.next().equals("B")) {
                remover.remove();
            }
        }
        System.out.println("after iterator remove: " + codes);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CollectionMutationDemo.java
java CollectionMutationDemo
```

Kết quả:

```text
size after set: 2
replaced object: S2:Binh
iterator after set: S1:An, S3:Chi
students after rename: [S1:Anh, S3:Chi]
shallow copy: [S1:Anh, S2:Binh]
local variable: S9:Local
list first element: S1:Anh
rename through readOnly: S1:Annie
readOnly set: blocked
source size after add: 3
readOnly size after add: 3
shallow copy size: 2
stale iterator: ConcurrentModificationException
after iterator remove: [A, C]
```

### 14.1. Theo dõi thay phần tử bằng set

`students.set(1, ...)` thay sinh viên ở vị trí 1 từ `S2` sang `S3`. Danh sách vẫn có hai phần tử.

Biến `replaced` vẫn giữ đối tượng `S2:Binh`. Trong ví dụ `ArrayList` này, iterator tạo trước `set` duyệt được phần tử mới ở vị trí chưa đi qua.

### 14.2. Theo dõi sửa trạng thái đối tượng

Đổi tên phần tử đầu thành `Anh` được nhìn thấy từ `students` và `shallowCopy`, vì hai list cùng giữ tham chiếu đến sinh viên `S1`.

Trong khi đó, phần tử thứ hai ở `shallowCopy` vẫn là `S2:Binh`. Lời gọi `set` trên nguồn đã thay tham chiếu tại một vị trí của nguồn, không thay tham chiếu của bản sao.

### 14.3. Theo dõi gán lại biến riêng

Gán `local` sang `S9:Local` không thay `students.get(0)`. Hai biểu thức không còn trỏ cùng đối tượng sau phép gán.

### 14.4. Theo dõi giới hạn của view không cho sửa

`readOnly.get(0).rename(...)` vẫn sửa sinh viên. Nhưng `readOnly.set(...)` bị wrapper chặn.

Khi thêm sinh viên qua `students`, kích thước `readOnly` tăng theo, còn kích thước `shallowCopy` vẫn là 2.

### 14.5. Theo dõi thay đổi cấu trúc và iterator

Phần `codes` cố ý tạo một iterator cũ, sau đó thêm phần tử bằng list rồi gọi `next()`. Với `ArrayList` trong thực nghiệm một luồng này, lời gọi phát hiện thay đổi và ném `ConcurrentModificationException`.

Ví dụ dùng ngoại lệ để quan sát cơ chế, không dùng nó như bảo đảm đồng bộ hoặc như cách điều khiển một thuật toán đúng.

Cuối chương trình tạo một iterator mới, xóa `B` qua chính iterator đó và thu được `[A, C]`. Thao tác xóa vẫn sửa cấu trúc, nhưng thực hiện đúng đường đi mà iterator hỗ trợ.

Lớp `Student` trong chương trình chỉ phục vụ thí nghiệm tham chiếu và trạng thái; nó không được đưa vào cấu trúc yêu cầu bình đẳng hoặc băm theo mã nghiệp vụ.

## 15. Từ phân biệt khái niệm đến thiết kế API

### 15.1. Quy định điều gì được phép đổi

Một API trả `List<Student>` cần nói rõ:

- Người nhận được thêm hoặc xóa không?
- Được thay phần tử không?
- Được gọi phương thức thay đổi trạng thái sinh viên không?
- Kết quả là view sống theo nguồn hay dữ liệu ở một thời điểm?
- Nguồn hoặc phần tử có được chia sẻ với tác vụ khác không?

Nếu cần một bản chụp không thể bị người nhận thay đổi, chỉ bọc list bằng `unmodifiableList` có thể chưa đủ. Cần thiết kế cả phần tử và quyền sở hữu dữ liệu.

### 15.2. Chọn kiểu dữ liệu theo ranh giới cập nhật

Có thể chọn:

- Đối tượng có thể sửa trong nội bộ nơi có kiểm soát sở hữu.
- Đối tượng giá trị bất biến làm khóa hoặc phần tử cần bình đẳng ổn định.
- Bản chụp dữ liệu dành cho bên đọc.
- Phương thức cập nhật rõ ràng thay vì để bên ngoài giữ tham chiếu và tự gọi setter.

Lựa chọn phụ thuộc nhu cầu, không có yêu cầu mọi đối tượng đều phải bất biến.

### 15.3. Không dùng non-structural như giấy phép truy cập đa luồng

Hai luồng cùng thay phần tử bằng `set` có thể không gặp ngoại lệ cấu trúc nhưng vẫn có tranh chấp hoặc vấn đề hiển thị bộ nhớ.

Hai luồng cùng sửa trường của một phần tử cũng không được bảo vệ chỉ vì collection bao ngoài hỗ trợ đồng thời. Tính an toàn của cấu trúc chứa và tính an toàn của các đối tượng được chứa là hai phạm vi riêng.

Cần cơ chế đồng bộ, sở hữu theo luồng, truyền dữ liệu hoặc bất biến phù hợp. Không suy luận về đa luồng từ một chương trình một luồng chạy thành công.

## 16. Cách phân tích một thay đổi trong mã thực tế

Khi thấy một dòng có vẻ “sửa collection”, lần lượt hỏi:

1. Dòng này gọi phương thức của collection, của phần tử hay chỉ gán biến?
2. Collection cụ thể và cấu hình của nó là gì?
3. Có thêm hoặc xóa phần tử, ánh xạ hay đổi cơ chế duyệt không?
4. Chỉ thay phần tử ở một vị trí hoặc giá trị của khóa đã có?
5. Hay chỉ sửa trạng thái bên trong đối tượng đang được tham chiếu?
6. Có ai khác giữ tham chiếu tới cùng collection hoặc phần tử không?
7. Có view, iterator hoặc bản sao nông đang tồn tại không?
8. Thuộc tính bị sửa có tham gia băm, bình đẳng hoặc thứ tự không?
9. Thao tác có được hỗ trợ trên collection hiện tại không?
10. Có yêu cầu an toàn giữa nhiều luồng hoặc tính nhất quán nghiệp vụ không?

Cách đọc này tránh gộp mọi thay đổi vào một loại rồi đoán hành vi từ `size()` hoặc một ngoại lệ.

## 17. Bài tập tự kiểm chứng

### Bài 1: Phân loại ba thao tác

Tạo lại danh sách có hai sinh viên trước mỗi trường hợp:

- Thêm sinh viên thứ ba.
- Thay sinh viên ở vị trí 1.
- Đổi tên sinh viên ở vị trí 1.

Với từng trường hợp, ghi:

- Số phần tử trước và sau.
- Tham chiếu tại vị trí 1 có giữ nguyên không?
- Đối tượng ban đầu có bị sửa không?
- Một biến đang giữ đối tượng ban đầu sẽ quan sát gì?

Đáp án định hướng: thêm làm cấu trúc tăng; `set` thay liên kết tại vị trí; setter đổi trạng thái cùng đối tượng.

### Bài 2: Hai list, một phần tử chung

Tạo một `Student`, thêm cùng đối tượng đó vào hai list. Đổi tên qua list thứ nhất rồi thay phần tử của list thứ nhất bằng sinh viên khác.

Phải quan sát được hai kết quả khác nhau:

1. Đổi tên đối tượng chung được thấy ở cả hai list.
2. Thay phần tử của list thứ nhất không thay phần tử đang nằm ở list thứ hai.

### Bài 3: Bản sao nông và view

Từ một list nguồn, tạo:

- `new ArrayList<>(source)`.
- `Collections.unmodifiableList(source)`.
- `List.copyOf(source)`.

Sau đó thực hiện riêng từng loại thay đổi trên nguồn: thêm phần tử, thay phần tử, sửa đối tượng phần tử. Ghi nhận bên nào thấy thay đổi và giải thích bằng đồ thị tham chiếu.

Lưu ý `List.copyOf` không chấp nhận phần tử `null`; dùng dữ liệu hợp lệ để thí nghiệm tập trung vào việc chia sẻ.

### Bài 4: Kích thước bằng nhau nhưng iterator cũ

Tạo iterator của `ArrayList`, thêm rồi xóa phần tử để kích thước cuối bằng kích thước ban đầu. Sau đó thử duyệt bằng iterator cũ.

Giải thích vì sao so sánh kích thước không chứng minh iterator còn hợp lệ. Mục tiêu là hiểu thao tác không đúng hợp đồng, không phải tìm cách làm ngoại lệ biến mất.

### Bài 5: Thiết kế phần tử làm khóa

Một lớp có `id`, `name`, `email`. Hãy chọn trường dùng để nhận diện khi đối tượng làm khóa và quy định trường nào được sửa.

Giải thích hậu quả nếu đổi trường tham gia `hashCode` khi khóa còn ở map. Thiết kế lại bằng định danh ổn định hoặc đối tượng khóa bất biến, thay vì dựa vào may mắn của một lần tra cứu.

## 18. Những kết luận cần tránh

- “Không đổi size thì không đổi cấu trúc.”
- “Không structural nên không đổi nội dung.”
- “Không có ConcurrentModificationException nên mã đúng.”
- “List không cho sửa thì phần tử cũng không cho sửa.”
- “Sao chép list là sao chép mọi đối tượng bên trong.”
- “Gán lại biến lấy từ get sẽ cập nhật vị trí trong list.”
- “Xóa phần tử khỏi list là hủy ngay đối tượng.”
- “Collection an toàn giữa các luồng thì phần tử bên trong cũng an toàn.”
- “Định nghĩa của ArrayList áp dụng giống nhau cho mọi collection.”

Năng lực cần đạt là mô tả được **cái gì đổi, ai giữ tham chiếu tới nó, hợp đồng nào điều chỉnh thay đổi và các bên đọc sẽ thấy gì**. Khi bốn câu hỏi này rõ ràng, các hành vi về iterator, view, sao chép và bất biến trở nên có thể giải thích và kiểm chứng.
