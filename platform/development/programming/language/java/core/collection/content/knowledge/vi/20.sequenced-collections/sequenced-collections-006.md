# SequencedSet và việc chuyển vị trí phần tử đã có

## 1. Từ tập hợp không trùng đến tập hợp có vị trí trong trình tự

Giả sử màn hình đang hiển thị các bước được chọn theo thứ tự:

~~~text
edit -> review -> publish
~~~

Người dùng muốn ghim `review` lên đầu. Yêu cầu có hai phần cùng lúc:

- `review` vẫn chỉ xuất hiện một lần;
- vị trí của nó trong trình tự phải thay đổi.

Một danh sách có thể đổi vị trí nhưng không tự bảo đảm loại trùng. Một set thông thường thể hiện tính duy nhất nhưng không nhất thiết có hợp đồng về thứ tự. Từ Java 21, `SequencedSet<E>` kết hợp hai khía cạnh: **là set và có thứ tự gặp phần tử xác định**.

Giao diện này kế thừa cả `Set<E>` lẫn `SequencedCollection<E>`; `reversed()` của nó trả lại một `SequencedSet<E>`. Tuy nhiên, quyền sửa và định vị vẫn phụ thuộc cách triển khai. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

Trong bài này, `LinkedHashSet` là cách triển khai chính để học việc đưa phần tử đã có về đầu/cuối. Ta sẽ phân biệt rõ nó với `TreeSet`, set chỉ đọc và view khóa của map. Chương trình đầy đủ dùng **Java 21 trở lên** vì `SequencedSet` và các thao tác định vị được học thuộc API từ phiên bản này.

## 2. Ba câu hỏi phải tách riêng

Khi gọi một thao tác trên set có trình tự, hãy tách ba câu hỏi:

1. **Thành viên:** phần tử này có thuộc set không?
2. **Trình tự:** nó đang đứng ở đâu trong lần duyệt?
3. **Quyền thao tác:** nguồn có cho phép áp đặt vị trí hay không?

Ví dụ, với `LinkedHashSet` đang là `[edit, review, publish]`:

~~~text
thành viên:    edit, review, publish đều có mặt
trình tự:     edit trước review, review trước publish
ý định mới:   review đứng đầu
~~~

Sau khi đưa `review` lên đầu:

~~~text
trình tự:     review -> edit -> publish
thành viên:   vẫn cùng ba phần tử
kích thước:   vẫn là 3
~~~

**Kích thước không đổi không có nghĩa trạng thái không đổi.** Trình tự là dữ liệu có thể quan trọng với giao diện, báo cáo hoặc chính sách ưu tiên. Một kiểm thử chỉ kiểm tra số phần tử sẽ không bắt được lỗi “đã nhận yêu cầu ghim nhưng chưa chuyển vị trí”.

Ngược lại, việc một kiểu có thứ tự cũng không đủ chứng minh được quyền chuyển vị trí. Một tập hợp sắp xếp xác định vị trí bằng phép so sánh; nó không thể cho tùy ý ghim một phần tử bất kỳ lên đầu mà vẫn giữ cùng quy tắc đó.

## 3. LinkedHashSet: add khác addFirst và addLast thế nào?

`LinkedHashSet` duy trì thứ tự chèn thông thường. Gọi lại `add(e)` khi phần tử đã có không làm đổi thứ tự. Từ Java 21, `addFirst(e)` và `addLast(e)` cung cấp ý định định vị tường minh; nếu phần tử đã có, nó được chuyển về đầu hoặc cuối khi cần. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

### 3.1. add: bảo đảm có thành viên, giữ vị trí của phần tử đã có

Bắt đầu từ `[A, B, C]`:

~~~java
boolean changed = items.add("B");
~~~

Đây là đoạn minh họa bên trong phương thức, với `items` là một `LinkedHashSet<String>` sửa được.

Kết quả là `changed == false` và trình tự vẫn `[A, B, C]`. Hàm trả `false` vì không thêm một thành viên mới. Không có hành vi tự động “vừa dùng B nên B thành mới nhất”.

Nếu gọi `add("D")` với phần tử chưa có, tập hợp liên kết thông thường thêm nó vào cuối, trở thành `[A, B, C, D]` và trả `true`.

### 3.2. addFirst: thêm nếu thiếu, đưa lên đầu nếu đã có

Bắt đầu từ `[A, B, C]`:

~~~text
addFirst(B)          [B, A, C]       kích thước 3
~~~

`B` không bị nhân đôi. Các phần tử còn lại giữ quan hệ tương đối `A` trước `C`.

Nếu đối số là `D` chưa có:

~~~text
[A, B, C]
addFirst(D)
[D, A, B, C]                        kích thước 4
~~~

Do đó `addFirst` không phải lệnh “chỉ di chuyển nếu tồn tại”. Nó cũng là lệnh thêm một phần tử mới vào đầu khi phần tử ấy chưa thuộc set.

### 3.3. addLast: thêm nếu thiếu, đưa xuống cuối nếu đã có

Bắt đầu từ `[A, B, C]`:

~~~text
addLast(A)           [B, C, A]       kích thước 3
~~~

Nếu đối số chưa có, nó được thêm ở cuối. Nếu phần tử đã là cuối, kết quả trình tự không thay đổi. Lặp `addLast("A")` trên `[B, C, A]` vẫn có cùng ba phần tử theo cùng trình tự.

Đó là kết quả logic có thể dựa vào. Đừng suy thêm rằng mọi lần gọi ở đúng đầu/cuối đều có cùng chi tiết nội bộ, không ảnh hưởng bất kỳ iterator nào hay miễn phí hoàn toàn.

### 3.4. Bảng đối chiếu cho một LinkedHashSet sửa được

| Thao tác | Đối số chưa có | Đối số đã có | Giá trị trả về |
| --- | --- | --- | --- |
| `add(e)` | Thêm vào cuối | Giữ vị trí hiện tại | `boolean`, có thêm thành viên mới hay không |
| `addFirst(e)` | Thêm vào đầu | Chuyển về đầu nếu cần | `void` |
| `addLast(e)` | Thêm vào cuối | Chuyển về cuối nếu cần | `void` |

Không thể viết `boolean moved = items.addFirst(e);`: phương thức trả `void`.

Cũng đừng dùng thay đổi của `size` để kết luận có chuyển vị trí hay không. Một phần tử đang ở giữa có thể được chuyển lên đầu trong khi `size` giữ nguyên.

## 4. “Đã có” dựa vào tính bằng, không phải chỉ cùng tham chiếu

Với các chuỗi trong `LinkedHashSet`, hai đối tượng `String` khác tham chiếu nhưng có nội dung bằng nhau vẫn đại diện cho cùng thành viên.

Ví dụ:

~~~java
var items = new java.util.LinkedHashSet<String>(
        java.util.List.of("A", "B", "C"));
boolean added = items.add(new String("B"));
items.addFirst(new String("B"));
~~~

Đoạn minh họa Java 21 này không tạo thêm thành viên `B`. Lệnh `add` trả `false`; sau lệnh định vị, trình tự là `[B, A, C]`.

`LinkedHashSet` thuộc họ set dựa trên băm. Cần triển khai `equals` và `hashCode` nhất quán cho kiểu phần tử tự định nghĩa. Việc chỉ trùng mã băm không đủ làm hai phần tử trở thành bằng nhau; mã băm hỗ trợ tìm vùng ứng viên, còn phép bằng phân biệt các giá trị trong vùng đó. Các thao tác cơ bản của `HashSet` dựa trên cấu trúc băm và có đặc tính hiệu năng gắn với sự phân tán mã băm. [Java 21: HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

Đối với một đối tượng nghiệp vụ có nhiều trường, phải xác định “cùng phần tử” là gì. Nếu `equals` chỉ dựa trên mã định danh, một lời gọi định vị bằng đối tượng cùng mã không có nghĩa API đã cập nhật mọi trường mô tả của đối tượng đang lưu. **Chuyển vị trí và cập nhật dữ liệu phần tử là hai trách nhiệm khác nhau.** Không dùng thao tác định vị như một API thay thế dữ liệu mà chưa xác định hợp đồng cần thiết.

### 4.1. Không đổi khóa bằng trong khi phần tử đang thuộc set

Nếu thay một trường ảnh hưởng `equals` hoặc `hashCode` khi đối tượng đang nằm trong set băm, việc tra cứu và các lần định vị sau có thể không còn đáng tin theo hợp đồng mong đợi.

Tài liệu `Set` cảnh báo hành vi không được xác định khi giá trị đối tượng đổi theo cách ảnh hưởng so sánh bằng trong lúc nó vẫn là thành viên. [Java 21: Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

Một lựa chọn dễ kiểm soát là lưu mã định danh bất biến, như `String` hoặc một kiểu giá trị bất biến có phép bằng đúng. Đổi nhãn hiển thị hay trạng thái xử lý trong nguồn dữ liệu khác không nên vô tình làm thay đổi danh tính của phần tử trong set.

### 4.2. null cũng là một thành viên có thể chuyển vị trí trong LinkedHashSet

`LinkedHashSet` cho phép `null`. Nếu đang có `[left, right]`:

~~~text
addFirst(null)       [null, left, right]       kích thước 3
addLast(null)        [left, right, null]       kích thước 3
add(null)            giữ nguyên               trả false
~~~

Không có “null thứ hai” sau lần định vị. Nhưng đây là khả năng của nguồn cho phép `null`, không phải quyền được suy cho mọi `SequencedSet`.

Với mã công việc hoặc mã tài liệu, nghiệp vụ thường có thể cấm `null` để tránh khó hiểu khi hiển thị và xử lý. Nếu cấm, kiểm tra trước khi sửa dữ liệu. `Objects.requireNonNull` là một cách biểu đạt điều kiện đó; nó không thay thế việc thiết kế ý nghĩa miền dữ liệu. [Java 21: Objects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).

## 5. Thêm hoặc chuyển khác với chỉ chuyển phần tử đang tồn tại

Một nút “ghim lên đầu” trên bảng chỉ chứa các mục đã chọn có thể không được phép tự đưa mã lạ vào bảng. Trong trường hợp ấy, gọi thẳng `addFirst` là quá rộng.

Helper sau chỉ chuyển nếu đã có:

~~~java
static <E> boolean moveExistingFirst(
        java.util.SequencedSet<E> items, E value) {
    if (!items.contains(value)) {
        return false;
    }
    items.addFirst(value);
    return true;
}
~~~

Đây là đoạn phương thức Java 21, cần đặt trong lớp; chương trình đầy đủ bên dưới có cách dùng.

Hợp đồng của helper phải nói rõ:

- nguồn hỗ trợ định vị khi nhánh đó được thực hiện;
- không có thay đổi đồng thời trong suốt phép kiểm tra và thao tác tiếp theo;
- `true` nghĩa là phần tử đã có và lời gọi định vị hoàn tất; nó **không** hứa phần tử trước đó nằm ở vị trí khác;
- `false` nghĩa là không tìm thấy nên helper không thêm phần tử.

Nếu phần tử đã ở đầu, helper vẫn trả `true`. Muốn báo riêng “thứ tự có thay đổi không”, cần thiết kế kết quả khác và so sánh với đầu hiện tại bằng phép bằng phù hợp. Đừng đặt tên `wasInserted` hoặc `orderChanged` cho cờ chỉ thể hiện sự hiện diện.

Trong hệ thống nhiều luồng, một luồng khác có thể xóa phần tử sau `contains`, rồi `addFirst` thêm nó trở lại. Hai lời gọi này không tạo một giao dịch nguyên tử. Cần đồng bộ cả thao tác nếu quy tắc “chỉ chuyển phần tử đang có” phải được giữ trong mọi lịch xen kẽ.

### 5.1. Vì sao không dùng remove rồi add như một thay thế vô điều kiện?

Mã cũ có thể làm:

~~~java
items.remove(value);
items.add(value);
~~~

Với một tập hợp liên kết sửa được và điều kiện phù hợp, cách này có thể đưa phần tử xuống cuối. Nhưng ý định được chia thành hai thay đổi, có thời điểm phần tử không thuộc set; nếu dùng đối tượng khác có phép bằng tương đương, việc xóa rồi thêm còn có thể thay đối tượng đại diện được lưu.

Thêm nữa, một generic set không nhất thiết giữ thứ tự chèn và không nhất thiết hỗ trợ cả hai thao tác. Không biến chuỗi `remove + add` thành cách “chữa” việc `addLast` ném `UnsupportedOperationException` trên nguồn không cho định vị. Trước hết phải chọn đúng mô hình dữ liệu.

`addLast` thể hiện trực tiếp ý định thêm hoặc đưa xuống cuối trên `LinkedHashSet`. Nó vẫn không làm cả quy trình nghiệp vụ xung quanh trở thành nguyên tử hay an toàn luồng.

### 5.2. Không dùng contains để tự động ghi nhận lần truy cập

`contains(e)` là câu hỏi về thành viên. Trên `LinkedHashSet` thông thường, nó không tự đẩy `e` về đầu/cuối như chính sách “mới dùng gần đây”.

Nếu muốn theo dõi lần sử dụng, phải gọi thao tác định vị khi sự kiện nghiệp vụ thực sự xảy ra. Cũng phải thống nhất đầu nào biểu thị mới nhất; mỗi nơi tự chọn một chiều sẽ tạo kết quả trái ngược dù từng lệnh đều hợp lệ.

## 6. Góc nhìn reversed đảo ý nghĩa của đầu và cuối

`reversed()` trả một view có chiều gặp phần tử ngược. Với `LinkedHashSet`, thay đổi qua view được phép truyền về nguồn, và thay đổi nguồn cũng nhìn thấy qua view.

Ví dụ nguồn ban đầu:

~~~text
nguồn:         [A, B, C, D]
view ngược:    [D, C, B, A]
~~~

Gọi `view.addFirst("B")` nghĩa là đưa `B` về **đầu view**. Đầu view là cuối theo chiều nguồn:

~~~text
nguồn sau:     [A, C, D, B]
view sau:      [B, D, C, A]
~~~

Sau đó gọi `view.addLast("D")`, tức đưa `D` về cuối view, tương ứng đầu nguồn:

~~~text
nguồn sau:     [D, A, C, B]
view sau:      [B, C, A, D]
~~~

Trong mã nguồn OpenJDK 21, view ngược của `LinkedHashSet` thực hiện `addFirst` qua `addLast` của nguồn và ngược lại. Đây là cách triển khai cụ thể phù hợp với ý nghĩa đảo chiều của view. [OpenJDK 21: LinkedHashSet.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashSet.java).

Có hai điểm dễ nhầm:

1. Tạo view không sao chép toàn bộ thành viên sang một set độc lập.
2. “Đưa lên đầu” luôn phải gắn với **chiều đang dùng để nhìn dữ liệu**.

Nếu cần thứ tự gốc giữ nguyên, hãy tạo một bản sao phù hợp rồi định vị trên bản sao. Nếu giao diện chỉ cần hiển thị mới nhất trước trong khi nguồn lưu mới nhất cuối, có thể đọc view ngược mà không chuyển mọi phần tử trong nguồn.

Không suy rằng `add` thông thường luôn tương đương `addLast` của mọi view. Khi ý định là một đầu cụ thể, dùng `addFirst` hoặc `addLast` và đọc hợp đồng nguồn.

## 7. Đưa nhiều phần tử lên đầu: thứ tự vòng lặp rất quan trọng

Bắt đầu `[A, B, C, D]`. Người dùng chọn thứ tự ưu tiên `[B, D]` và muốn chúng xuất hiện đầu tiên theo đúng thứ tự đó.

Nếu duyệt thuận yêu cầu và gọi `addFirst`:

~~~text
ban đầu                    [A, B, C, D]
đưa B lên đầu              [B, A, C, D]
đưa D lên đầu              [D, B, A, C]
~~~

Thứ tự nhóm ưu tiên bị đảo. Lần gọi sau cùng chiếm đầu.

Muốn kết quả `[B, D, A, C]`, hãy xử lý yêu cầu theo chiều ngược:

~~~java
for (String id : requested.reversed()) {
    selected.addFirst(id);
}
~~~

Đoạn minh họa Java 21 giả sử `requested` là `List<String>` riêng, `selected` là `LinkedHashSet<String>` sửa được, và các mã yêu cầu không lặp. `List.reversed()` cung cấp chiều duyệt ngược của danh sách yêu cầu. [Java 21: List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()).

Sau hai thao tác, các thành viên không thuộc nhóm ưu tiên giữ quan hệ tương đối `A` trước `C`.

### 7.1. Xác định chính sách với yêu cầu lặp hoặc thiếu

Nếu yêu cầu là `[B, D, B]`, câu “giữ nguyên thứ tự yêu cầu” chưa đủ rõ: set không thể hiển thị hai lần `B`. Phải chọn giữ lần xuất hiện đầu, lần cuối hay từ chối dữ liệu lặp, rồi chuẩn hóa đầu vào trước khi định vị.

Nếu yêu cầu có một mã chưa thuộc nguồn, `addFirst` sẽ thêm mã đó. Muốn chỉ chuyển thành viên đã có, dùng chính sách kiểm tra tương ứng dưới quyền truy cập phù hợp.

Đừng để vòng lặp vô tình định nghĩa chính sách mà sản phẩm chưa quyết định. Hãy kiểm thử riêng trường hợp mã lặp, mã lạ và nhóm rỗng.

### 7.2. Không vừa duyệt cùng nguồn vừa tùy tiện chuyển liên kết

Một vòng `for (E e : selected)` dùng iterator của nguồn. Đổi vị trí một phần tử thật sự có thể làm iterator không còn hợp lệ dù số thành viên giữ nguyên.

Cách thông thường là tách quyết định khỏi cập nhật:

~~~java
java.util.List<String> toPin = new java.util.ArrayList<>();
for (String id : selected) {
    if (id.startsWith("urgent-")) {
        toPin.add(id);
    }
}
for (String id : toPin.reversed()) {
    selected.addFirst(id);
}
~~~

Đây là đoạn minh họa Java 21 bên trong phương thức, dành cho ngữ cảnh không có thay đổi đồng thời. Vòng đầu thu thập quyết định mà không sửa nguồn; vòng sau duyệt danh sách riêng.

Iterator nói chung không cho tùy ý sửa cấu trúc nguồn trong lúc duyệt, trừ cơ chế được nó hoặc cách triển khai quy định. `Iterator.remove` là quyền xóa phần tử vừa trả về, không phải API chuyển nó về đầu/cuối. [Java 21: Iterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Iterator.html#remove()).

## 8. Cơ chế bên dưới: tính duy nhất và trình tự là hai phần phối hợp

Có thể hình dung `LinkedHashSet` bằng hai góc nhìn:

~~~text
tìm thành viên:     băm của giá trị -> tìm phần tử phù hợp

duyệt trình tự:     đầu <-> A <-> B <-> C <-> cuối
~~~

Khi đưa `B` lên đầu, mô hình logic là tháo `B` khỏi vị trí giữa rồi nối nó trước `A`:

~~~text
trước:              A <-> B <-> C
sau:                B <-> A <-> C
~~~

Phần tìm thành viên giúp nhận ra `B` đã có; phần liên kết giúp duy trì chiều duyệt. Không cần tạo một thành viên `B` mới chỉ vì nó đổi vị trí.

Trong OpenJDK 21, set này dùng `LinkedHashMap` làm cấu trúc hỗ trợ. Mã nguồn `LinkedHashMap` có nhánh đưa nút hiện có về đầu hoặc cuối, cập nhật các liên kết và bộ đếm thay đổi khi thực sự chuyển nút. Đây là giải thích cơ chế của cách triển khai đó, không phải thuật toán bắt buộc cho mọi `SequencedSet`. [OpenJDK 21: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java).

### 8.1. Vì sao size không đủ bảo đảm iterator còn hợp lệ?

Iterator theo dõi quá trình duyệt trình tự. Một nút chuyển từ giữa lên đầu có thể làm đường duyệt thay đổi dù số nút không đổi. Vì vậy, “không thêm hay xóa thành viên” không phải lý do cho phép định vị tùy ý trong lúc đang dùng iterator cũ.

Cơ chế phát hiện thay đổi kiểu fail-fast là hỗ trợ tìm lỗi, không phải công cụ đồng bộ hay một giao thức nghiệp vụ. Không dựa vào việc có hoặc không thấy `ConcurrentModificationException` để quyết định chương trình đúng.

### 8.2. Hiệu năng không đến từ tên giao diện

Tìm bằng băm tốt và cập nhật một số liên kết có thể giúp thao tác định vị trên cách triển khai liên kết không phải chép lại toàn bộ trình tự. Nhưng chi phí còn phụ thuộc phép băm, phép bằng, va chạm và cách triển khai.

Một tham số `SequencedSet<E>` không hứa mọi thao tác có cùng thời gian hay cùng quyền sửa. Nếu hiệu năng và quyền định vị là điều kiện của một API, cần nêu yêu cầu cụ thể và đo với khối lượng công việc thực tế. Đừng chỉ đổi tên biến từ `Set` thành `SequencedSet` rồi tuyên bố hiệu năng đã cải thiện.

## 9. Các nguồn có SequencedSet nhưng không cho chuyển vị trí tùy ý

### 9.1. TreeSet và SortedSet giữ thứ tự do so sánh quyết định

Một `TreeSet` tự nhiên chứa `[A, B, C]` phải giữ quy tắc so sánh. `addFirst("B")` không được phép đưa `B` trước `A`. `SortedSet.addFirst` và `addLast` ném `UnsupportedOperationException` vì định vị tường minh xung đột với quy tắc thứ tự.

Ngay cả gọi `addFirst("A")` khi `A` đã ở đầu vẫn không phải cách sử dụng được hỗ trợ. Dùng `add` để thêm thành viên, còn vị trí do phép so sánh quyết định. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html#addFirst(E)).

Nếu yêu cầu là “ghim một mục bất kỳ lên đầu”, việc sắp xếp toàn bộ bằng một bộ so sánh cố định có thể không còn là mô hình phù hợp. Có thể cần một trình tự ưu tiên riêng hoặc một bộ so sánh phản ánh đúng chính sách; không bắt ngoại lệ rồi bỏ qua mà vẫn báo ghim thành công.

### 9.2. Lớp bọc không sửa được

`Collections.unmodifiableSequencedSet(source)` giữ khả năng đọc trình tự và hai chiều, nhưng từ chối sửa qua view. Một lời gọi định vị bị từ chối ngay cả khi đối số đã thuộc nguồn.

Lớp bọc này vẫn là view; nếu nguồn được sửa qua một đường khác, truy vấn view đọc theo nguồn. Nó không tạo ảnh chụp cố định. [Java 21: Collections.unmodifiableSequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableSequencedSet(java.util.SequencedSet)).

Muốn giữ một bản dữ liệu độc lập về cấu trúc ở thời điểm hiện tại, có thể tạo `new LinkedHashSet<>(source)` trước. Đó là sao chép nông: nếu phần tử có trạng thái thay đổi, các cấu trúc vẫn có thể chia sẻ tham chiếu đến chúng.

### 9.3. View khóa của map

`SequencedMap.sequencedKeySet()` trả `SequencedSet<K>`, nhưng không nên hiểu đây là một set độc lập có mọi quyền định vị.

Ví dụ view khóa của `LinkedHashMap` không hỗ trợ `addFirst` hay `addLast`. Nếu cần định vị ánh xạ trong map, hãy dùng API thích hợp của map và cung cấp giá trị đi kèm, thay vì xem view khóa như một lối tắt. [Java 21: LinkedHashMap, các view có trình tự](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html#sequencedKeySet()).

Điều này cho thấy chỉ nhìn kiểu `SequencedSet` là chưa đủ để hứa một helper ghim hoạt động trên mọi đầu vào. Quyền sửa là một phần hợp đồng mà nơi tạo và nơi nhận dữ liệu phải thống nhất.

## 10. Chuyển vị trí không thay hợp đồng equals và hashCode của set

Hai set có cùng thành viên vẫn có thể `equals` nhau dù trình tự duyệt khác nhau. Thêm giao diện có trình tự không biến phép bằng của set thành phép bằng theo vị trí.

Ví dụ:

~~~text
x:    [A, B, C]
y:    [C, A, B]

x.equals(y)                      true
cùng thứ tự duyệt?               false
~~~

Nếu kiểm thử tính năng ghim chỉ dùng `expectedSet.equals(actualSet)`, nó có thể qua dù tính năng không đổi thứ tự như yêu cầu. Cần so sánh một trình tự, chẳng hạn:

~~~java
java.util.List<String> actualOrder = new java.util.ArrayList<>(actual);
if (!actualOrder.equals(java.util.List.of("B", "A", "C"))) {
    throw new AssertionError("unexpected order: " + actualOrder);
}
~~~

Đây là đoạn kiểm chứng Java 21 bên trong phương thức, giả sử `actual` là nguồn không bị thay đổi đồng thời. Lựa chọn danh sách cho kết quả kiểm chứng là có chủ đích vì `List.equals` xét các vị trí.

Trong chương trình đầy đủ, source và view ngược có `equals == true`, đồng thời `hashCode` bằng nhau. Hai dòng ấy xác nhận hợp đồng set; chúng không phủ định việc góc nhìn ngược đọc theo thứ tự khác.

## 11. Chương trình đầy đủ: phần tử đã có, view, nhóm ưu tiên và lịch sử gần đây

Lưu toàn bộ mã sau vào **`SetRepositionDemo.java`**. Chương trình chạy một luồng, dùng các chuỗi bất biến và giữ quyền cập nhật dữ liệu trong các helper.

Helper `touchRecent` minh họa một chính sách ứng dụng: mới dùng nhất nằm cuối, mã không được `null`, chỉ giữ tối đa một số mã. Đây là thuật toán mẫu cho lịch sử mã, không phải một cache hoàn chỉnh hay cơ chế xử lý đồng thời.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.SequencedSet;
import java.util.TreeSet;

public class SetRepositionDemo {
    // Requires supported positioning and exclusive access for the whole method.
    // true means the element was present, not necessarily that its order changed.
    static <E> boolean moveExistingFirst(SequencedSet<E> items, E value) {
        if (!items.contains(value)) {
            return false;
        }
        items.addFirst(value);
        return true;
    }

    // Application policy: newest at the end, no null IDs, positive capacity.
    // Requires exclusive access for the entire update.
    static void touchRecent(LinkedHashSet<String> recent, String id, int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("limit must be positive");
        }
        Objects.requireNonNull(id, "id");
        recent.addLast(id);
        while (recent.size() > limit) {
            recent.removeFirst();
        }
    }

    static String unsupported(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        LinkedHashSet<String> steps =
                new LinkedHashSet<>(List.of("edit", "review", "publish"));
        System.out.println("initial: " + steps);
        boolean added = steps.add(new String("review"));
        System.out.println("ordinary add existing: " + added + ", order=" + steps);

        steps.addFirst("review");
        System.out.println("first existing: " + steps + ", size=" + steps.size());
        steps.addLast("edit");
        System.out.println("last existing: " + steps + ", size=" + steps.size());
        steps.addFirst("draft");
        System.out.println("first missing: " + steps + ", size=" + steps.size());
        steps.addLast("draft");
        System.out.println("last draft: " + steps + ", size=" + steps.size());
        steps.addLast("draft");
        System.out.println("last draft again: " + steps + ", size=" + steps.size());

        boolean foundMissing = moveExistingFirst(steps, "missing");
        System.out.println("move missing: " + foundMissing + ", order=" + steps);
        boolean foundPublish = moveExistingFirst(steps, "publish");
        System.out.println("move publish: " + foundPublish + ", order=" + steps);
        System.out.println("set equals reverse: " + steps.equals(steps.reversed()));
        System.out.println("hash equals reverse: "
                + (steps.hashCode() == steps.reversed().hashCode()));

        SequencedSet<String> readOnly =
                Collections.unmodifiableSequencedSet(steps);
        LinkedHashSet<String> saved = new LinkedHashSet<>(steps);
        System.out.println("read-only reposition: "
                + unsupported(() -> readOnly.addFirst("edit")));
        steps.addFirst("edit");
        System.out.println("read-only sees source: " + readOnly);
        System.out.println("saved copy stays: " + saved);

        LinkedHashSet<String> base =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        SequencedSet<String> reverse = base.reversed();
        reverse.addFirst("B");
        System.out.println("reverse first B, base: " + base);
        System.out.println("reverse first B, view: " + reverse);
        reverse.addLast("D");
        System.out.println("reverse last D, base: " + base);
        System.out.println("reverse last D, view: " + reverse);

        List<String> requested = List.of("B", "D");
        LinkedHashSet<String> forwardBatch =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        for (String id : requested) {
            forwardBatch.addFirst(id);
        }
        LinkedHashSet<String> preservedBatch =
                new LinkedHashSet<>(List.of("A", "B", "C", "D"));
        for (String id : requested.reversed()) {
            preservedBatch.addFirst(id);
        }
        System.out.println("batch forward input: " + forwardBatch);
        System.out.println("batch preserve input: " + preservedBatch);

        LinkedHashSet<String> nullable =
                new LinkedHashSet<>(List.of("left", "right"));
        nullable.addFirst(null);
        nullable.addLast(null);
        boolean duplicateNull = nullable.add(null);
        System.out.println("null moved: " + nullable + ", size=" + nullable.size()
                + ", ordinary add=" + duplicateNull);

        SequencedSet<String> sorted =
                new TreeSet<>(List.of("A", "B", "C"));
        System.out.println("sorted first existing A: "
                + unsupported(() -> sorted.addFirst("A")));
        System.out.println("sorted last existing C: "
                + unsupported(() -> sorted.addLast("C")));

        LinkedHashMap<String, Integer> counts = new LinkedHashMap<>();
        counts.put("A", 1);
        counts.put("B", 2);
        SequencedSet<String> keys = counts.sequencedKeySet();
        System.out.println("map key view reposition: "
                + unsupported(() -> keys.addFirst("B")));

        LinkedHashSet<String> recent =
                new LinkedHashSet<>(List.of("r1", "r2", "r3"));
        touchRecent(recent, "r1", 3);
        System.out.println("touch existing: " + recent);
        touchRecent(recent, "r4", 3);
        System.out.println("touch new and trim: " + recent);
        System.out.println("newest first display: " + recent.reversed());
    }
}
~~~

Dùng JDK 21 trở lên để biên dịch và Java 21 trở lên để chạy:

~~~shell
javac --release 21 -encoding UTF-8 SetRepositionDemo.java
java SetRepositionDemo
~~~

Không cần `--enable-preview`. Ví dụ đã được biên dịch với mức release 21 và chạy thành công trên OpenJDK 24.0.2. Các dòng stdout dùng chuỗi ASCII để kết quả không phụ thuộc khả năng hiển thị dấu trên terminal.

Stdout chính xác:

~~~text
initial: [edit, review, publish]
ordinary add existing: false, order=[edit, review, publish]
first existing: [review, edit, publish], size=3
last existing: [review, publish, edit], size=3
first missing: [draft, review, publish, edit], size=4
last draft: [review, publish, edit, draft], size=4
last draft again: [review, publish, edit, draft], size=4
move missing: false, order=[review, publish, edit, draft]
move publish: true, order=[publish, review, edit, draft]
set equals reverse: true
hash equals reverse: true
read-only reposition: UnsupportedOperationException
read-only sees source: [edit, publish, review, draft]
saved copy stays: [publish, review, edit, draft]
reverse first B, base: [A, C, D, B]
reverse first B, view: [B, D, C, A]
reverse last D, base: [D, A, C, B]
reverse last D, view: [B, C, A, D]
batch forward input: [D, B, A, C]
batch preserve input: [B, D, A, C]
null moved: [left, right, null], size=3, ordinary add=false
sorted first existing A: UnsupportedOperationException
sorted last existing C: UnsupportedOperationException
map key view reposition: UnsupportedOperationException
touch existing: [r2, r3, r1]
touch new and trim: [r3, r1, r4]
newest first display: [r4, r1, r3]
~~~

### 11.1. Các lệnh trên steps

`new String("review")` tạo một đối tượng chuỗi khác tham chiếu nhưng bằng nội dung. `add` không tạo thành viên thứ hai và không chuyển vị trí.

`addFirst("review")` đưa bước đã có lên đầu, `addLast("edit")` đưa bước đã có xuống cuối. Kích thước vẫn 3. Chỉ khi thêm `draft` chưa có thì kích thước tăng lên 4.

Gọi lại `addLast("draft")` giữ cùng trình tự. Helper chỉ chuyển mục đang có không tự thêm `missing`, còn `publish` được chuyển thành công.

### 11.2. View chỉ đọc và bản sao

View chỉ đọc từ chối lời gọi định vị, sau đó nhìn thấy thay đổi qua nguồn gốc. Bản `saved` giữ thứ tự đã chép trước thay đổi ấy.

Đây là hai lựa chọn khác nhau về vòng đời dữ liệu: chia sẻ góc nhìn nguồn hoặc giữ một cấu trúc riêng. Đừng gọi cả hai là “bản không đổi” nếu chưa xác định mức bảo đảm cần thiết.

### 11.3. Hai chiều và cập nhật theo nhóm

Bốn dòng về view ngược cho phép đối chiếu trực tiếp đầu view với cuối nguồn và ngược lại.

Hai dòng cập nhật nhóm dùng cùng dữ liệu ban đầu nhưng khác chiều duyệt yêu cầu. Đọc chúng cùng với bảng trung gian ở phần 7 để thấy vì sao gọi `addFirst` lặp lại làm đảo thứ tự xử lý.

### 11.4. Nguồn từ chối định vị và chính sách gần đây

`TreeSet` từ chối cả hai lời gọi với phần tử đã ở đúng biên. View khóa của map cũng từ chối định vị, dù nó có kiểu `SequencedSet`.

Trong lịch sử gần đây, dùng lại `r1` chuyển mã này xuống cuối mà không tăng số thành viên. Thêm `r4` tạo thành viên mới rồi loại đầu cũ `r2`, nên nguồn còn `[r3, r1, r4]`. View ngược hiển thị mới nhất trước.

`LinkedHashMap` có một chế độ access-order riêng cho các ánh xạ, nhưng ở đây set không tự theo dõi truy cập; chính helper nhận sự kiện sử dụng và chủ động định vị. Nếu cần lưu thêm dữ liệu theo mã và chính sách cache, phải thiết kế tiếp trên mô hình phù hợp, không coi ví dụ set này đã giải quyết toàn bộ yêu cầu.

## 12. Cách dùng an toàn trong ứng dụng

### 12.1. Đặt tên chính sách theo ý nghĩa

Hãy chọn và ghi rõ một trong các quy ước như “ưu tiên cao nhất ở đầu” hoặc “mới dùng nhất ở cuối”. Từ đó suy ra `addFirst` hay `addLast` ở mỗi sự kiện.

Nếu phải hỗ trợ cả thứ tự tùy chỉnh của người dùng và thời điểm truy cập gần đây, một trình tự duy nhất có thể không đủ diễn đạt hai quan hệ độc lập. Cần hai nguồn thứ tự hoặc dữ liệu bổ sung, thay vì để thao tác ghim vô tình phá lịch sử truy cập.

### 12.2. Kiểm tra hợp lệ trước khi đổi thứ tự

Giả sử yêu cầu chứa mã chưa tồn tại trong kho dữ liệu nghiệp vụ. Nếu một API chỉ được phép chuyển mục đã chọn, phải xác minh điều kiện đó trước khi gọi thao tác có khả năng thêm.

Với cập nhật nhiều mục, kiểm tra toàn bộ yêu cầu trước có thể tránh lỗi dữ liệu ở mục thứ ba sau khi hai mục đầu đã được chuyển. Tuy vậy, việc kiểm tra rồi sửa nhiều lệnh không tự có rollback; nếu cần “tất cả hoặc không gì”, phải thiết kế một lần cập nhật trạng thái mới, khóa hoặc giao dịch phù hợp ở tầng sở hữu.

### 12.3. Đồng bộ toàn bộ đơn vị nghiệp vụ khi chia sẻ

`LinkedHashSet` không tự đồng bộ. Một lần định vị, kiểm tra `contains` rồi định vị, hoặc định vị rồi giới hạn kích thước đều có thể là phần của một đơn vị nghiệp vụ lớn hơn.

Nếu dùng khóa ngoài, mọi nơi đọc/sửa có liên quan phải tuân cùng quy tắc, và khóa cần bao trùm toàn bộ chuỗi phải nhất quán. Bọc bằng một API trả `Set` cũng có thể làm chữ ký không còn cung cấp trực tiếp các phương thức `SequencedSet`; đừng ép kiểu tùy tiện để lấy lại khả năng không được lớp bọc cam kết.

Fail-fast không thay cho khóa, còn không thấy ngoại lệ không chứng minh không có tranh chấp dữ liệu. Những ví dụ trong bài giữ ngữ cảnh một luồng để kiểm chứng trình tự mà không lẫn lịch xen kẽ.

### 12.4. Lưu và truyền trình tự bằng định dạng thể hiện được nó

Nếu thứ tự ghim là dữ liệu nghiệp vụ, khi xuất hoặc lưu phải chọn biểu diễn có trình tự rõ ràng. So sánh chỉ thành viên trước/sau có thể bỏ sót thay đổi cần lưu.

Tương tự, không chuyển qua `HashSet` hay `Set.copyOf` rồi mặc định vẫn giữ được thứ tự hiển thị đã chọn. Một set bất biến thông thường không tự trở thành hợp đồng có trình tự. Nếu cần đầu ra chỉ đọc có trình tự, chọn lớp bọc `unmodifiableSequencedSet` trên một nguồn có vòng đời và quyền sở hữu phù hợp.

## 13. Những lỗi thường gặp

| Cách nghĩ hoặc cách viết | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Gọi `add(e)` để đánh dấu e mới dùng nhất | Phần tử đã có không tự di chuyển trong LinkedHashSet | Dùng thao tác định vị theo chính sách |
| Gọi `addFirst` với mã lạ trong chức năng “chỉ ghim mục đã chọn” | Có thể thêm một thành viên mới | Kiểm tra và xác định hợp đồng thêm/di chuyển |
| Gán kết quả `addFirst` vào `boolean` | Sai kiểu trả về `void` | Tạo kết quả nghiệp vụ riêng nếu cần |
| Dùng `size` để phát hiện mọi thay đổi | Không thấy việc đổi thứ tự | Kiểm chứng trình tự |
| Coi mọi SequencedSet đều chuyển vị trí được | SortedSet/view chỉ đọc có thể từ chối | Nêu rõ quyền định vị cần thiết |
| Bắt lỗi định vị rồi xóa/thêm đại | Có thể phá quy tắc hoặc đổi đối tượng lưu | Chọn đúng cấu trúc và ý định |
| Duyệt nguồn và chuyển phần tử ngay trong vòng lặp | Iterator có thể không còn hợp lệ | Thu thập trước, cập nhật sau |
| Duyệt nhóm thuận rồi addFirst và mong giữ thứ tự nhóm | Nhóm bị đảo | Chọn chiều duyệt phù hợp |
| Dùng set equals để kiểm tra thứ tự | Kiểm thử có thể qua dù thứ tự sai | So sánh trình tự bằng danh sách |
| Đổi trường dùng cho equals/hashCode khi phần tử đang trong set | Tra cứu/định vị không còn đúng giả định | Dùng danh tính bất biến hoặc quy trình cập nhật đúng |

## 14. Thực hành có đáp án

### Bài 1 — Cùng phần tử, khác thao tác

Nguồn `LinkedHashSet` là `[A, B, C]`. Lần lượt gọi `add("B")`, `addFirst("C")`, `addLast("A")`. Trình tự và kích thước cuối là gì?

**Đáp án:** `add("B")` trả `false`, nguồn vẫn `[A, B, C]`. Sau `addFirst("C")` là `[C, A, B]`. Sau `addLast("A")` là `[C, B, A]`. Kích thước vẫn 3 vì không thêm thành viên mới.

### Bài 2 — Chỉ chuyển nếu đã có

Nguồn `[A, B]`. Yêu cầu “đưa X lên đầu nếu X đang được chọn, nếu chưa có thì không làm gì”. Vì sao gọi thẳng `addFirst("X")` sai yêu cầu?

**Đáp án:** thao tác thêm hoặc định vị sẽ đưa `X` vào nguồn, thành `[X, A, B]`. Cần helper có chính sách chỉ chuyển khi đã có, với quyền định vị và truy cập nhất quán. Nếu có nhiều luồng, phép kiểm tra cùng thao tác định vị phải được xử lý trong một đơn vị đồng bộ phù hợp.

### Bài 3 — Hai đối tượng bằng nhau

Một set chuỗi có `"B"`. Bạn gọi `addFirst(new String("B"))`. Có hai thành viên `B` vì tham chiếu khác nhau không?

**Đáp án:** không. Tính duy nhất dựa trên phép bằng đúng của phần tử, không chỉ `==`. Chuỗi mới bằng nội dung với thành viên đang có. Tuy nhiên, không hiểu lời gọi định vị là một API cập nhật mọi thuộc tính của đối tượng nghiệp vụ bằng nhau theo mã.

### Bài 4 — Đầu của view ngược

Nguồn là `[A, B, C]`, view ngược là `[C, B, A]`. Gọi `view.addFirst("A")` rồi `view.addLast("B")` trên view của `LinkedHashSet` sửa được. Nguồn và view cuối thế nào?

**Đáp án:** lần đầu đưa `A` xuống cuối nguồn, nguồn `[B, C, A]`, view `[A, C, B]`. Lần sau đưa `B` lên đầu nguồn; `B` vốn đã ở đầu nên trình tự giữ nguyên. Kết quả cuối vẫn là nguồn `[B, C, A]` và view `[A, C, B]`.

### Bài 5 — Nhóm ưu tiên có thứ tự

Nguồn `[A, B, C, D, E]`. Muốn nhóm `[C, E]` đứng đầu theo đúng thứ tự ấy. Hãy mô tả trình tự gọi `addFirst`.

**Đáp án:** xử lý `E` trước, rồi `C`. Sau lần đầu: `[E, A, B, C, D]`; sau lần hai: `[C, E, A, B, D]`. Nếu xử lý `C` trước rồi `E`, nhóm đầu sẽ thành `[E, C]`. Giả định yêu cầu không lặp và mọi mã đã có; chính sách khác cần được xác định riêng.

### Bài 6 — Kiểm thử ghim bị bỏ sót

Một kiểm thử tạo hai set có cùng thành viên nhưng khác thứ tự rồi dùng `equals`. Nó qua. Có chứng minh tính năng ghim đúng không?

**Đáp án:** không. `Set.equals` không xét thứ tự gặp phần tử. Hãy thu thập trình tự thành danh sách và so với trình tự mong đợi; đồng thời kiểm tra số thành viên và thành viên đúng nếu đó là yêu cầu riêng. Không dùng `hashCode` của set làm dấu thay đổi thứ tự.

### Bài 7 — Đã ở đầu nhưng vẫn bị từ chối

`SequencedSet<String> x` thực tế là `TreeSet` chứa `[A, B, C]`. Vì sao `x.addFirst("A")` vẫn có thể ném `UnsupportedOperationException` dù `A` đang ở đầu?

**Đáp án:** quyền định vị tường minh không được hỗ trợ trên set sắp xếp; vị trí do phép so sánh quyết định. Trạng thái hiện tại không mở thêm quyền cho API ấy. Dùng `add` để thêm thành viên, hoặc đổi mô hình nếu cần ghim tùy ý; không bắt ngoại lệ rồi báo thành công.

### Bài 8 — Lịch sử gần đây có giới hạn

Giữ tối đa 3 mã, cũ nhất ở đầu và mới nhất ở cuối. Nguồn ban đầu `[p1, p2, p3]`. Dùng lại `p2` rồi dùng mã mới `p4`. Kết quả phải thế nào và cần kiểm tra gì ngoài số phần tử?

**Đáp án:** sau khi dùng lại `p2` là `[p1, p3, p2]`. Thêm `p4` rồi loại đầu cũ cho `[p3, p2, p4]`. Cần kiểm tra trình tự, tính duy nhất và đúng mã bị loại. Phải xác định chính sách `null`, dung lượng hợp lệ, cách xử lý lỗi và đồng bộ toàn bộ cập nhật nếu chia sẻ giữa các luồng.

Hãy tự thêm một bài kiểm chứng với phần tử đã ở đúng đầu/cuối, nhóm yêu cầu rỗng và một mã chưa có. Trước khi chạy, ghi rõ thao tác nào chỉ di chuyển và thao tác nào được phép thêm. Khi dự đoán được cả thành viên lẫn trình tự sau mỗi lệnh, bạn đã nắm đúng ý nghĩa của việc chuyển vị trí trong set có trình tự.
