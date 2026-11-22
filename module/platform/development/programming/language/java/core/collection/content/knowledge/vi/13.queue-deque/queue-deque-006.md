# ArrayDeque: mảng vòng, tăng dung lượng và thao tác hai đầu

## 1. Vì sao một Deque dựa trên mảng vẫn thao tác đầu dãy hiệu quả?

Nếu dùng một mảng tuyến tính ngây thơ để biểu diễn hàng đợi, việc lấy phần tử đầu có thể kéo theo dồn mọi phần tử còn lại sang trái. Làm như vậy nhiều lần khiến công việc tăng theo chiều dài dãy.

ArrayDeque tránh cách tổ chức ấy. Nó giữ dữ liệu trong một mảng có thể tăng sức chứa và quản lý hai vị trí đầu–cuối theo dạng vòng. Khi lấy đầu, chủ yếu là xóa tham chiếu ở một ô rồi chuyển vị trí đầu; không cần dồn cả dãy sau mỗi lần lấy.

Ba ý chính của cấu trúc là:

- **Mảng vòng:** thứ tự logic có thể đi qua cuối mảng rồi tiếp tục ở đầu mảng.
- **Hai đầu:** thêm, xem và gỡ ở first hoặc last bằng những thao tác vị trí phù hợp.
- **Tăng dung lượng:** khi mảng hiện có không đủ chỗ, tạo mảng lớn hơn và giữ đúng thứ tự các phần tử.

[Tài liệu ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) mô tả đây là triển khai Deque dựa trên mảng có thể tăng, không có giới hạn dung lượng cố định do người gọi đặt, cấm phần tử null và không tự an toàn khi nhiều luồng truy cập không có phối hợp.

Bài này phân biệt hai tầng:

1. **Hợp đồng sử dụng:** phần tử nào được thêm/lấy, thứ tự nào được quan sát, điều gì xảy ra khi rỗng.
2. **Mô hình triển khai:** mảng nền, vị trí hai đầu, quay vòng và cấp phát khi tăng dung lượng.

Các sơ đồ chỉ số là mô hình để hiểu cơ chế. Không dùng chúng để suy ra một chỉ số nội bộ cụ thể sau một lời gọi API trên mọi JDK.

## 2. Dãy logic khác với thứ tự ô vật lý

Giả sử Deque đang biểu đạt dãy:

```text
first -> A, B, C, D, E <- last
```

Không bắt buộc A phải ở ô 0 và E phải ở ô 4. Một cách bố trí trong mảng vòng 8 ô có thể là:

```text
chỉ số:   0   1   2   3   4   5   6   7
nội dung: C   D   E   .   .   .   A   B
                                  ^
                                 head

tail = 3, vị trí sẽ ghi khi thêm cuối
dấu . là ô trống trong mô hình
```

Đọc từ head theo chiều tiến của mảng:

```text
6 -> 7 -> 0 -> 1 -> 2
A    B    C    D    E
```

Thứ tự logic vẫn là A, B, C, D, E dù có hai đoạn nằm ở hai phía mảng.

Đây là ý nghĩa “vòng”: chỉ số được đưa về đầu khi đi qua ô cuối. Không có nghĩa các ô mảng ở bộ nhớ được nối vật lý thành một vòng.

### 2.1. head và tail có vai trò khác nhau

Trong mô hình phù hợp với triển khai OpenJDK 17:

- `head` là vị trí phần tử first khi dãy không rỗng.
- `tail` là vị trí sẽ dùng cho lần thêm last tiếp theo.
- Phần tử last hiện tại nằm ở vị trí lùi một bước từ tail.
- Khi trạng thái ổn định là rỗng, head bằng tail.

Đặc biệt, tail không phải luôn là chỉ số của phần tử cuối đang có. Nếu tail bằng 0, vị trí ngay trước nó theo vòng là ô cuối của mảng.

Không cần dùng reflection để lấy các trường ấy trong mã ứng dụng. API cung cấp `peekFirst`, `peekLast`, `getFirst`, `getLast` để đọc các đầu theo hợp đồng.

### 2.2. Phân biệt size và độ dài mảng nền

Gọi:

```text
n = số phần tử hiện có
L = số ô của mảng nền
```

n và L không phải một đại lượng. Mảng có thể còn chỗ dự phòng; một số thiết kế còn dành ô trống để phân biệt trạng thái.

ArrayDeque không có một phương thức public thông thường để hỏi chính xác độ dài mảng nội bộ. `size()` trả số phần tử, không trả số ô đang được cấp phát.

Constructor nhận một con số chuẩn bị sức chứa ban đầu, không hứa mảng vật lý có đúng từng ấy ô và không đặt giới hạn tối đa từng ấy phần tử.

## 3. Tăng hoặc giảm chỉ số theo vòng

Một cách minh họa việc tiến và lùi chỉ số là:

```java
// Các hàm minh họa đặt trong một lớp bao quanh.
// Điều kiện: length > 0 và 0 <= index < length.
static int nextIndex(int index, int length) {
    return index + 1 == length ? 0 : index + 1;
}

static int previousIndex(int index, int length) {
    return index == 0 ? length - 1 : index - 1;
}
```

Đây là mã mô hình, không phải mã nguồn được sao chép nguyên từ ArrayDeque. Nó biểu đạt rõ thao tác tại biên mảng:

```text
nextIndex(7, 8)     -> 0
previousIndex(0, 8) -> 7
```

Không được áp dụng tùy ý công thức mặt nạ bit như `(index + 1) & (length - 1)` nếu chưa có điều kiện length là lũy thừa của hai. Mô hình mảng vòng không tự yêu cầu độ dài mảng phải có dạng ấy.

Khi đọc các phiên bản JDK khác nhau, chi tiết chọn độ dài và công thức cập nhật chỉ số có thể khác. Hợp đồng ArrayDeque không hứa mọi phiên bản giữ cùng một độ dài mảng hay cùng một hệ số tăng.

### 3.1. Tính số phần tử trong mô hình có một khoảng trống

Với quy ước head là đầu có dữ liệu và tail là ô ghi tiếp, số phần tử ở trạng thái ổn định có thể được tính theo khoảng cách vòng:

```text
n = tail - head                  nếu tail >= head
n = tail - head + L              nếu tail < head
```

Trong hình ban đầu:

```text
head = 6, tail = 3, L = 8
n = 3 - 6 + 8 = 5
```

Công thức này đi cùng quy ước trạng thái của mô hình. Trong một cấu trúc vòng khác cho phép dùng kín mọi ô và giữ một biến đếm riêng, head bằng tail có thể cần được giải thích khác.

Không lấy một công thức của mảng vòng rồi gán cho mọi cách triển khai.

## 4. Bốn thao tác cốt lõi ở hai đầu

Bắt đầu lại từ bố trí minh họa:

```text
chỉ số:   0   1   2   3   4   5   6   7
nội dung: C   D   E   .   .   .   A   B
head = 6
tail = 3
logic = [A, B, C, D, E]
```

Giả sử các bước dưới đây chưa cần tăng mảng.

### 4.1. Thêm cuối

Để thêm F ở last:

1. Ghi F vào ô tail hiện tại, tức ô 3.
2. Đưa tail tiến một bước theo vòng.

```text
head = 6
tail = 4
logic = [A, B, C, D, E, F]
```

Không cần chuyển A, B, C, D, E sang vị trí mới.

### 4.2. Lấy đầu

Để lấy first:

1. Đọc A ở head.
2. Xóa tham chiếu trong ô ấy.
3. Đưa head tiến một bước theo vòng.

```text
trả về A
head = 7
tail = 4
logic = [B, C, D, E, F]
```

Việc “xóa” ở đây không bắt buộc hủy đối tượng A trong bộ nhớ. Nó bỏ tham chiếu từ ô của Deque; đối tượng còn có thể được giữ bởi tham chiếu khác.

### 4.3. Thêm đầu

Từ trạng thái vừa có, thêm X ở first:

1. Lùi head một bước theo vòng.
2. Ghi X vào head mới.

```text
head = 6
tail = 4
logic = [X, B, C, D, E, F]
```

Thứ tự B, C, D, E, F vẫn nguyên vẹn.

### 4.4. Lấy cuối

Để lấy last:

1. Lùi từ tail tới vị trí phần tử cuối.
2. Đọc F tại đó.
3. Xóa tham chiếu và cập nhật tail về vị trí vừa gỡ.

```text
trả về F
head = 6
tail = 3
logic = [X, B, C, D, E]
```

Bảng đối chiếu cả chuỗi:

| Bước | head | tail | Dãy logic sau bước |
|---|---:|---:|---|
| Ban đầu | 6 | 3 | A, B, C, D, E |
| Thêm last F | 6 | 4 | A, B, C, D, E, F |
| Lấy first | 7 | 4 | B, C, D, E, F |
| Thêm first X | 6 | 4 | X, B, C, D, E, F |
| Lấy last | 6 | 3 | X, B, C, D, E |

Số thao tác vị trí của mỗi bước là nhỏ và cố định khi không cần tăng mảng. Đó là lý do ArrayDeque xử lý hai đầu khác với một mảng tuyến tính luôn dồn nội dung về ô 0.

## 5. Trạng thái rỗng, ô trống và chính sách null

Trong [mã nguồn ArrayDeque của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayDeque.java), các ô không giữ phần tử được đặt null; ở trạng thái ổn định có ô trống tại tail. Khi thêm làm mảng tạm kín, cơ chế tăng mảng khôi phục khoảng trống cần thiết.

Các chi tiết đó giải thích mô hình đang dùng, không phải một API để ứng dụng điều khiển trực tiếp.

### 5.1. head bằng tail ở trạng thái rỗng

Sau khi lấy hết, head và tail gặp nhau. Chúng không bắt buộc phải ở ô 0 sau mọi chuỗi poll; vị trí cụ thể là chi tiết nội bộ.

Một thao tác clear có thể đặt lại vị trí theo lựa chọn triển khai. Người gọi chỉ nên dựa vào size bằng 0, isEmpty đúng và hành vi rỗng của các phương thức.

### 5.2. Null không phải phần tử hợp lệ

ArrayDeque cấm thêm null. Nhờ đó, null có thể được dùng rõ ràng như giá trị báo không có phần tử của poll và peek.

Cấm null cũng phù hợp với cách dùng null đánh dấu ô trống trong triển khai này. Tuy nhiên, không suy luận rằng mọi mảng vòng về mặt lý thuyết đều không thể hỗ trợ null: một thiết kế khác có thể dùng thông tin đếm hoặc đánh dấu khác.

Nếu dữ liệu nghiệp vụ có trường có thể thiếu, hãy biểu đạt trong một đối tượng không null, hoặc chọn chính sách đầu vào rõ. Không dùng một phần tử null như công việc đặc biệt trong ArrayDeque.

### 5.3. Rỗng: phương thức trả null và phương thức ném ngoại lệ

| Ý định | Trả null khi rỗng | Ném NoSuchElementException khi rỗng |
|---|---|---|
| Chỉ xem first | `peekFirst()` | `getFirst()` |
| Chỉ xem last | `peekLast()` | `getLast()` |
| Lấy và gỡ first | `pollFirst()` | `removeFirst()` |
| Lấy và gỡ last | `pollLast()` | `removeLast()` |

Thêm null vẫn ném NullPointerException kể cả gọi offer. “Trả một giá trị trạng thái” không có nghĩa mọi đầu vào không hợp lệ đều được chuyển thành false hoặc null.

## 6. Gắn API với hàng đợi và ngăn xếp

Từ bốn thao tác cơ chế, có thể xây hai chính sách quen thuộc:

```text
FIFO: thêm last, lấy first
LIFO: thêm first, lấy first
```

Các tên phương thức rút gọn của Deque dùng cùng quy ước:

| Tên quen dùng | Thao tác hai đầu tương ứng |
|---|---|
| `offer(e)` | `offerLast(e)` |
| `poll()` | `pollFirst()` |
| `peek()` | `peekFirst()` |
| `push(e)` | `addFirst(e)` |
| `pop()` | `removeFirst()` |

Với FIFO, một phần tử được thêm ở last chờ các phần tử phía first được lấy trước. Với LIFO, phần tử mới được thêm first đứng ngay trước phần tử cũ và được lấy trước.

Cũng có thể làm ngăn xếp ở đầu last nếu thêm và lấy đều ở last, nhưng các tên push/pop của API đặt đỉnh ở first. Hãy giữ một quy ước nhất quán.

Cơ chế vòng không tự quyết định FIFO hay LIFO. Nó tạo khả năng thao tác hiệu quả ở hai đầu; mã gọi chọn chính sách bằng cặp thao tác.

## 7. Chương trình 1: quan sát từng đầu thao tác

Lưu tệp `ArrayDequeEndsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeEndsDemo {
    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();
        values.addLast("B");
        values.addLast("C");
        values.addFirst("A");

        System.out.println("initial = " + values);
        System.out.println("peek first = " + values.peekFirst());
        System.out.println("peek last = " + values.peekLast());
        System.out.println("offer first X = " + values.offerFirst("X"));
        System.out.println("offer last D = " + values.offerLast("D"));
        System.out.println("after offers = " + values);
        System.out.println("poll first = " + values.pollFirst());
        System.out.println("poll last = " + values.pollLast());
        System.out.println("after polls = " + values);

        values.push("TOP");
        System.out.println("after push = " + values);
        System.out.println("pop = " + values.pop());
        System.out.println("remove first = " + values.removeFirst());
        System.out.println("remove last = " + values.removeLast());
        System.out.println("one member = " + values);
        System.out.println("get first = " + values.getFirst());
        System.out.println("get last = " + values.getLast());
        System.out.println("take final member = " + values.pollFirst());
        System.out.println("empty = " + values.isEmpty());
        System.out.println("empty poll = " + values.pollFirst());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeEndsDemo.java
java ArrayDequeEndsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
initial = [A, B, C]
peek first = A
peek last = C
offer first X = true
offer last D = true
after offers = [X, A, B, C, D]
poll first = X
poll last = D
after polls = [A, B, C]
after push = [TOP, A, B, C]
pop = TOP
remove first = A
remove last = C
one member = [B]
get first = B
get last = B
take final member = B
empty = true
empty poll = null
```

Các chương trình trong bài dùng ngôn ngữ và API có ở Java 17 trở lên, được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

Output thể hiện dãy logic từ first tới last, không phải một bản in mảng vật lý. Có thể đối chiếu:

- AddFirst đặt A trước B, C.
- OfferFirst và offerLast thêm ở hai phía khác nhau.
- PollFirst và pollLast gỡ đúng hai phần tử vừa thêm ở hai đầu.
- Push đặt TOP ở first; pop lấy chính TOP.
- Khi chỉ còn B, cả hai đầu đều đọc ra B.
- Sau khi lấy B, poll tiếp trả null.

Các lời gọi peek và get chỉ xem phần tử. Chúng không dịch head hoặc tail để gỡ dữ liệu.

Không thể từ dãy in ra suy ra head đang bằng bao nhiêu. Hợp đồng cần kiểm tra là thứ tự và kết quả, còn vị trí ô thật thuộc triển khai.

## 8. Khi mảng vòng không còn đủ chỗ thì điều gì xảy ra?

Quay vòng chỉ tái sử dụng các ô đã trống. Nếu số phần tử tiếp tục tăng và không còn chỗ theo quy ước lưu trữ, quay về ô 0 không tạo thêm sức chứa.

ArrayDeque tăng mảng để tiếp tục giữ các phần tử hiện có và phần tử mới. Ý tưởng chung:

```text
mảng hiện tại không đủ chỗ
    -> tính kích thước mới phù hợp
    -> cấp phát mảng lớn hơn
    -> chuyển các tham chiếu cần giữ
    -> điều chỉnh vị trí hai đầu
    -> tiếp tục biểu đạt cùng dãy logic
```

### 8.1. Phải bảo toàn thứ tự, kể cả khi dữ liệu đang quấn vòng

Giả sử nội dung cũ được chia thành hai đoạn vật lý:

```text
đoạn cuối mảng: A, B
đoạn đầu mảng:  C, D, E
thứ tự logic:  A, B, C, D, E
```

Sau tăng mảng, thứ tự logic vẫn phải là A, B, C, D, E. Sao chép các ô theo chỉ số vật lý một cách ngây thơ mà bỏ qua head có thể cho C, D, E, A, B và làm sai Deque.

Một cách vẽ để hình dung mảng mới là:

```text
[A, B, C, D, E, ., ., ., ...]
```

Đây là một cách bố trí minh họa hợp lệ, không phải lời hứa rằng ArrayDeque luôn dồn head về 0 sau tăng mảng. Triển khai có thể di chuyển các đoạn theo cách khác miễn bảo toàn thứ tự và các bất biến.

### 8.2. Tăng mảng chuyển tham chiếu, không sao chép sâu đối tượng

Mảng nền giữ các tham chiếu tới phần tử. Tăng mảng không mặc định clone từng đối tượng nghiệp vụ.

Nếu một đối tượng đang được giữ ở ngoài Deque, tăng sức chứa không tự tách nó thành một bản khác. Điều được tổ chức lại là các ô chứa tham chiếu.

Tương tự, một Deque<Integer> còn có các đối tượng số nguyên do cơ chế đóng hộp; không nên coi toàn bộ dữ liệu đối tượng nằm liên tiếp trong mảng chỉ vì các tham chiếu được lưu trong một mảng.

### 8.3. Không dựa vào một hệ số tăng cố định trong mã ứng dụng

Hợp đồng ArrayDeque không cho phép người gọi cấu hình hệ số tăng và không hứa một chuỗi dung lượng nội bộ cố định.

Mã nguồn OpenJDK 17 có cách tính tăng phụ thuộc kích thước hiện tại và lượng cần thêm. Không nên học thành quy tắc “mọi lần đều nhân đôi” hoặc “độ dài luôn là lũy thừa hai”.

Nếu cần phân tích cơ chế, hãy ghi rõ phiên bản triển khai đang đọc. Nếu viết ứng dụng, hãy dựa vào hợp đồng sức chứa tự tăng và chi phí thích hợp, không dựa vào thời điểm resize đoán từ một con số bên trong.

## 9. Vì sao thêm có chi phí O(1) khấu hao nhưng có lần O(n)?

Một lần thêm thông thường có thể chỉ cần ghi một ô và cập nhật một vị trí. Nhưng một lần thêm đúng lúc cần tăng mảng phải xử lý nhiều tham chiếu hiện có.

Nếu đang có n phần tử gần lấp đầy mảng, một lần tăng mảng có thể tốn O(n) thời gian. Vì vậy, không có bảo đảm mọi addFirst hoặc addLast riêng lẻ luôn có chi phí hằng số.

Khái niệm **khấu hao** nhìn tổng công việc trên một chuỗi thao tác, rồi phân bổ chi phí những lần tăng mảng cho các lần thêm đã được sức chứa mới phục vụ.

### 9.1. Ý tưởng tăng theo tỷ lệ

Trong một mô hình tăng theo hệ số g > 1, tổng lượng dữ liệu sao chép qua các lần tăng có dạng một cấp số nhân:

```text
C + gC + g²C + ... + gᵏC
```

Tổng ấy cùng bậc với số hạng lớn nhất. Nếu xây dãy bằng m lần thêm từ nhỏ đến lớn, tổng chi phí chuyển dữ liệu có cận O(m), bên cạnh m lần ghi phần tử.

Do đó, tổng có thể là O(m), dẫn đến O(1) khấu hao cho mỗi lần thêm. Các ngưỡng và làm tròn thực tế không yêu cầu đúng một công thức duy nhất để hiểu ý tưởng này.

Đây là phân tích chuỗi thao tác, không phải xác suất “phần lớn dữ liệu ngẫu nhiên sẽ nhanh”. Nó cũng không có nghĩa một yêu cầu cần độ trễ tối đa chặt đã được đáp ứng.

### 9.2. Đặt kỳ vọng hiệu năng đúng

| Thao tác | Cách hiểu với mô hình ArrayDeque này |
|---|---|
| Thêm first/last | O(1) khấu hao; một lần cần tăng mảng có thể O(n) |
| Lấy first/last | Cập nhật đầu và xóa tham chiếu, không dồn cả dãy |
| Xem first/last | Truy cập vị trí đầu tương ứng |
| size | Tính theo trạng thái chỉ số, không duyệt từng phần tử |
| contains theo giá trị | Có thể phải tìm qua n phần tử |
| remove theo giá trị hoặc occurrence | Có thể phải tìm và dịch một phần dữ liệu |
| Duyệt toàn bộ | O(n) về số phần tử cần đọc |

Bảng không biến mọi phương thức của giao diện Deque thành cùng một chi phí. `removeFirst()` và `remove(Object)` có tên gần nhau nhưng phục vụ hai việc khác nhau.

Độ phức tạp còn giả sử các thao tác trên phần tử như equals có chi phí thích hợp. Nếu phép equals rất tốn kém, tìm theo giá trị có thêm chi phí ấy.

### 9.3. Chuẩn bị sức chứa khi biết quy mô

Nếu dự kiến số phần tử lớn, constructor có sức chứa ban đầu phù hợp có thể giảm nhu cầu tăng mảng trong giai đoạn đầu:

```java
// Trích đoạn: chuẩn bị cho quy mô dự kiến, không đặt giới hạn cứng.
Deque<String> pending = new ArrayDeque<>(1_000);
```

Đổi lại, cấp phát dự phòng lớn có chi phí bộ nhớ. Không chọn một con số khổng lồ chỉ để tránh mọi resize mà chưa hiểu tải thực tế.

Nếu quy mô vượt dự kiến, ArrayDeque vẫn có thể tăng. Nó không tự từ chối phần tử thứ 1001 chỉ vì constructor nhận 1000.

## 10. Chương trình 2: lấy đầu, thêm cuối rồi tiếp tục dùng cả hai đầu

Lưu tệp `ArrayDequeMixedEndsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;

public class ArrayDequeMixedEndsDemo {
    public static void main(String[] args) {
        Deque<Integer> values = new ArrayDeque<>(8);
        for (int value = 0; value < 6; value++) {
            values.addLast(value);
        }
        System.out.println("initial = " + values);

        List<Integer> removedFront = new ArrayList<>();
        for (int count = 0; count < 4; count++) {
            removedFront.add(values.removeFirst());
        }
        System.out.println("removed front = " + removedFront);
        System.out.println("after front removals = " + values);

        for (int value = 6; value <= 12; value++) {
            values.addLast(value);
        }
        System.out.println("after tail additions = " + values);

        values.addFirst(3);
        values.addFirst(2);
        System.out.println("after front additions = " + values);
        System.out.println("remove last one = " + values.removeLast());
        System.out.println("remove last two = " + values.removeLast());
        System.out.println("forward = " + new ArrayList<>(values));

        List<Integer> reverse = new ArrayList<>();
        Iterator<Integer> iterator = values.descendingIterator();
        while (iterator.hasNext()) {
            reverse.add(iterator.next());
        }
        System.out.println("reverse = " + reverse);

        List<Integer> drained = new ArrayList<>();
        Integer next;
        while ((next = values.pollFirst()) != null) {
            drained.add(next);
        }
        System.out.println("drained = " + drained);
        System.out.println("empty after drain = " + values.isEmpty());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeMixedEndsDemo.java
java ArrayDequeMixedEndsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
initial = [0, 1, 2, 3, 4, 5]
removed front = [0, 1, 2, 3]
after front removals = [4, 5]
after tail additions = [4, 5, 6, 7, 8, 9, 10, 11, 12]
after front additions = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
remove last one = 12
remove last two = 11
forward = [2, 3, 4, 5, 6, 7, 8, 9, 10]
reverse = [10, 9, 8, 7, 6, 5, 4, 3, 2]
drained = [2, 3, 4, 5, 6, 7, 8, 9, 10]
empty after drain = true
```

Chương trình tạo một chuỗi thao tác hữu ích để kiểm tra tính liên tục của dãy:

1. Thêm một nhóm ở last.
2. Lấy bớt ở first.
3. Thêm tiếp nhiều giá trị ở last.
4. Thêm ở first.
5. Lấy ở last.
6. Duyệt hai chiều rồi lấy hết theo first.

Những chuỗi như vậy tạo điều kiện cho vị trí hai đầu tiến/lùi và cho việc tái sử dụng vùng trống trong một triển khai mảng vòng. Nhưng chương trình không đọc các chỉ số nội bộ, nên output không phải phép đo “resize xảy ra chính xác ở lần gọi nào”.

### 10.1. Thứ tự duyệt là thứ tự logic

`new ArrayList<>(values)` thu dãy từ first tới last, cho `[2, 3, ..., 10]`.

`descendingIterator()` đọc chiều ngược lại, cho `[10, 9, ..., 2]`. Nó không thay đổi nội dung Deque.

Dù dữ liệu đang nằm trong một đoạn hay quấn thành hai đoạn vật lý, iterator và toArray vẫn phải biểu đạt thứ tự logic phù hợp.

### 10.2. Lấy hết không cần tự biết head/tail

Vòng pollFirst đến khi null lấy ra cùng dãy `[2, 3, ..., 10]` rồi dừng.

Vì ArrayDeque cấm phần tử null, giá trị null ở đây báo hết dữ liệu. Mã gọi không cần biết phần tử tiếp theo nằm ở cuối mảng hay đã quay về ô 0.

Đó là giá trị của việc dùng collection chuẩn: cơ chế chỉ số được đóng gói, còn mã ứng dụng thao tác bằng thứ tự và ý nghĩa của các đầu.

### 10.3. Không kiểm tra bằng hình dạng mảng đoán trước

Một kiểm tra yêu cầu “sau chuỗi này head phải bằng 6” phụ thuộc vào một bố trí nội bộ không thuộc API. Cùng thứ tự đầu ra có thể được tạo bởi các phiên bản triển khai với dung lượng và chỉ số khác nhau.

Điều nên bảo vệ là không mất, không lặp ngoài ý muốn, đúng thứ tự và đúng giá trị trả về sau mỗi thao tác.

## 11. Chương trình 3: tăng qua nhiều mức mà vẫn giữ đủ dữ liệu

Lưu tệp `ArrayDequeGrowthDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeGrowthDemo {
    public static void main(String[] args) {
        Deque<Integer> values = new ArrayDeque<>(1);
        int count = 10_000;

        for (int value = 0; value < count; value++) {
            values.addLast(value);
        }

        System.out.println("size after additions = " + values.size());
        System.out.println("first = " + values.getFirst());
        System.out.println("last = " + values.getLast());

        int expected = 0;
        long checksum = 0L;
        Integer next;
        while ((next = values.pollFirst()) != null) {
            if (next != expected) {
                throw new AssertionError("Order differs at " + expected);
            }
            checksum += next;
            expected++;
        }
        if (expected != count) {
            throw new AssertionError("Element count differs");
        }

        System.out.println("verified elements = " + expected);
        System.out.println("checksum = " + checksum);
        System.out.println("empty after drain = " + values.isEmpty());

        values.addFirst(1);
        values.addFirst(2);
        values.addFirst(3);
        System.out.println("reuse at front = " + values);
        values.clear();
        System.out.println("size after clear = " + values.size());
        values.addLast(7);
        System.out.println("reuse after clear = " + values);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeGrowthDemo.java
java ArrayDequeGrowthDemo
```

Kết quả của lần chạy kiểm chứng:

```text
size after additions = 10000
first = 0
last = 9999
verified elements = 10000
checksum = 49995000
empty after drain = true
reuse at front = [3, 2, 1]
size after clear = 0
reuse after clear = [7]
```

Sức chứa ban đầu được yêu cầu nhỏ, nhưng chương trình thêm được 10.000 giá trị. Nó kiểm tra từng phần tử khi lấy ra, không chỉ nhìn size ở cuối.

### 11.1. Kiểm tra thứ tự và số lượng riêng

Trong vòng lấy:

- Mỗi phần tử phải bằng giá trị expected.
- Expected tăng sau mỗi lần lấy.
- Sau khi dừng, tổng số phần tử phải đúng count.

Nếu chỉ kiểm tra tổng checksum, một số lỗi thiếu/lặp hoặc tráo thứ tự có thể không bị phát hiện. Vì vậy, chương trình còn đối chiếu tuần tự từng giá trị.

Checksum `49.995.000` là tổng từ 0 tới 9999. Biến long giúp mẫu dễ mở rộng mà không dùng một biến tổng int quá nhỏ khi tăng quy mô.

### 11.2. Đây là kiểm tra tính đúng, không phải benchmark

Chương trình không đo thời gian và không đọc sức chứa bên trong. Nó xác nhận rằng qua việc tăng quy mô sử dụng, dãy được giữ đúng và có thể dùng lại sau khi đã lấy hết.

Không thể từ một lần chạy đúng suy ra giới hạn độ trễ của từng add, hệ số tăng cụ thể hoặc dung lượng tối đa khả dụng trên mọi máy.

### 11.3. Có thể dùng lại sau drain và clear

Sau khi lấy hết, chương trình thêm 1, 2, 3 ở first nên dãy là `[3, 2, 1]`. Clear làm size về 0; thêm 7 ở last sau đó vẫn hoạt động.

Trạng thái rỗng là một trạng thái sử dụng bình thường, không có nghĩa đối tượng ArrayDeque đã bị hủy.

## 12. Bộ nhớ sau khi lấy phần tử và sau clear

Mỗi lần gỡ đầu/cuối, triển khai bỏ tham chiếu ở ô đã gỡ. Điều đó tránh việc mảng nền tiếp tục giữ một đối tượng chỉ vì ô cũ chưa được xóa.

Nhưng có hai loại bộ nhớ cần phân biệt:

1. Đối tượng phần tử và các đối tượng mà nó tham chiếu.
2. Mảng nền chứa các ô tham chiếu của Deque.

Gỡ phần tử bỏ một tham chiếu từ Deque. Đối tượng có thể đủ điều kiện được thu gom nếu không còn tham chiếu giữ nó ở nơi khác. Không thể kết luận đối tượng được thu gom ngay lập tức.

### 12.1. Size giảm không có nghĩa mảng tự co ngay

Trong triển khai OpenJDK 17 đang xét, lấy phần tử không có cơ chế tự giảm mảng sau mỗi lần xóa; clear xóa các tham chiếu và đặt lại trạng thái, không tự cấp một mảng nhỏ hơn.

Vì vậy, một Deque từng đạt đỉnh rất lớn có thể còn giữ mảng dự phòng lớn khi số phần tử hiện tại đã ít.

Có thể biểu đạt chi phí lưu trữ theo độ dài mảng nền L, thay vì luôn gắn với n hiện tại. L có thể lớn hơn đáng kể n sau một giai đoạn tải cao.

### 12.2. Khi cần tách khỏi mảng nền cũ

Nếu yêu cầu giữ phần dữ liệu còn lại trong một container mới, có thể tạo:

```java
// Trích đoạn: tạo container riêng từ thứ tự hiện tại.
ArrayDeque<String> compactCopy = new ArrayDeque<>(remaining);
```

Constructor xây một Deque mới từ các phần tử của collection nguồn theo thứ tự iterator. Nó không phải lời gọi public để sửa trực tiếp capacity của đối tượng cũ.

Sau đó cần quản lý tham chiếu tới container cũ nếu mục tiêu là không giữ nó nữa. Khi các bên khác còn giữ đối tượng cũ, đổi một biến ở một nơi chưa làm nó biến mất.

Bản sao vẫn chia sẻ các đối tượng phần tử; đây không phải sao chép sâu dữ liệu nghiệp vụ.

### 12.3. Không coi tự tăng là bộ nhớ vô hạn

ArrayDeque không có giới hạn dung lượng cố định kiểu hàng đợi bounded do người gọi đặt, nhưng vẫn chịu giới hạn mảng và bộ nhớ của JVM.

Nếu luồng tạo công việc nhanh hơn luồng xử lý trong thời gian dài, tự tăng không thay thế kiểm soát tải hoặc chính sách giới hạn ở cấp ứng dụng.

Những yêu cầu chờ khi đầy, từ chối khi quá tải hoặc xử lý đa luồng cần cấu trúc và quy trình có hợp đồng phù hợp. Constructor có capacity ban đầu không tạo ra các khả năng ấy.

## 13. Những lỗi thường gặp khi suy luận từ mảng vòng

| Nhận định hoặc cách làm | Vấn đề | Cách hiểu đúng |
|---|---|---|
| Phần tử first luôn ở ô 0 | Bỏ qua head | First là vị trí logic hiện tại |
| tail luôn trỏ phần tử last | Sai quy ước vị trí ghi tiếp | Last nằm ở ô lùi một bước từ tail |
| head lớn hơn tail là trạng thái hỏng | Dữ liệu có thể quấn vòng | Đọc qua cuối mảng rồi tiếp tục ở đầu |
| Lấy đầu phải dồn mọi phần tử | Nhầm với mảng tuyến tính ngây thơ | Chuyển head và xóa ô đã lấy |
| Quay vòng nghĩa là ghi đè dữ liệu chưa lấy | Quên điều kiện hết chỗ | ArrayDeque tăng mảng khi cần |
| Mọi lần tăng đều nhân đôi | Không phải hợp đồng API | Cơ chế tăng là chi tiết triển khai |
| Độ dài mảng luôn là lũy thừa hai | Không được suy ra từ mô hình vòng | Dùng công thức chỉ số phù hợp với thiết kế |
| Khấu hao O(1) nghĩa mọi add O(1) | Bỏ qua lần resize | Một lần có thể O(n), tổng chuỗi mới có cận khấu hao |
| `new ArrayDeque<>(n)` giới hạn n phần tử | Nhầm capacity ban đầu với bound | Đây là chuẩn bị sức chứa |
| Clear luôn trả lại mảng lớn cho JVM | Không đúng với triển khai đang xét | Phân biệt xóa tham chiếu phần tử và thay mảng nền |
| Remove theo giá trị cũng rẻ như removeFirst | Cần tìm và điều chỉnh nội dung | Chọn đúng thao tác hai đầu |
| Dùng null để đánh dấu một phần tử đặc biệt | ArrayDeque không nhận null | Dùng kiểu hoặc giá trị hợp lệ rõ ràng |

Một lỗi ở cấp mã sử dụng là vừa duyệt bằng iterator vừa thay đổi cấu trúc qua phương thức khác. Iterator không phải ảnh chụp; sửa đổi có thể bị phát hiện và gây ConcurrentModificationException.

Nếu cần tiêu thụ từ một đầu, dùng vòng poll/remove phù hợp. Nếu chỉ cần đọc ổn định độc lập, cân nhắc bản sao. Không dùng fail-fast như một cơ chế phối hợp nhiều luồng.

ArrayDeque không tự an toàn cho truy cập đồng thời không có phối hợp. Tính đúng của công thức vòng và tính nhất quán giữa nhiều luồng là hai vấn đề khác nhau.

## 14. Chọn ArrayDeque và kiểm tra điều gì?

ArrayDeque thường phù hợp khi cần giữ một dãy không null, thêm/lấy chủ yếu ở hai đầu và không cần truy cập theo chỉ số qua API.

Trước khi chọn, hãy xác định:

- Chỉ dùng FIFO, chỉ dùng LIFO hay thật sự cần cả hai đầu?
- Rỗng là trạng thái bình thường hay lỗi giả định?
- Quy mô đang chờ có thể tăng đến đâu?
- Có cần giới hạn cứng, chờ hoặc phối hợp nhiều luồng không?
- Có thao tác tìm/xóa giữa dãy thường xuyên không?
- Có yêu cầu độ trễ tối đa mà phân tích khấu hao chưa đáp ứng không?

Không chọn bằng một khẳng định chung “mảng luôn nhanh hơn danh sách liên kết”. Cấu trúc, loại thao tác, bộ nhớ và môi trường đều ảnh hưởng đánh giá.

### 14.1. Những chuỗi kiểm tra hữu ích

Các trường hợp đáng kiểm tra trực tiếp qua API:

1. Rỗng, một phần tử, rồi rỗng lại.
2. Thêm/lấy ở first liên tiếp.
3. Thêm/lấy ở last liên tiếp.
4. Thêm last nhưng lấy first qua nhiều vòng.
5. Thêm xen kẽ cả hai đầu, sau đó gỡ cả hai đầu.
6. Bắt đầu nhỏ rồi thêm nhiều, kiểm tra đủ thứ tự và số lượng.
7. Lấy hết, clear rồi dùng lại.
8. Các lần xuất hiện có giá trị trùng nhau vẫn được giữ đúng số lượng.
9. Null bị từ chối ở ranh giới được thiết kế.
10. Duyệt xuôi và ngược cho thứ tự tương ứng.

Không cần biết chính xác lúc nào mảng tăng để kiểm tra hợp đồng của mã sử dụng. Nếu mục tiêu riêng là phân tích một phiên bản JDK, hãy dùng mã nguồn và công cụ đo phù hợp, đồng thời ghi rõ phiên bản.

### 14.2. Đừng dùng equals của Deque như equals của List

ArrayDeque không định nghĩa equals theo nội dung dãy giống List. Khi cần đối chiếu thứ tự, thu các giá trị lấy ra vào List hoặc so từng phần tử theo một quy trình rõ ràng như chương trình 3.

Dùng Set để kiểm tra đầu ra còn làm mất cả thứ tự lẫn số lần xuất hiện. Một kiểm tra như vậy có thể bỏ qua chính lỗi mà mảng vòng cần tránh.

## 15. Bài tập áp dụng

### Bài 1: đọc dãy đang quấn vòng

Mảng minh họa có `L = 8`, head = 6, tail = 3, các ô 6, 7, 0, 1, 2 lần lượt là A, B, C, D, E.

Dãy logic và size là gì?

**Gợi ý trả lời:** A, B, C, D, E; size bằng `3 - 6 + 8 = 5`.

### Bài 2: phần tử last ở đâu?

Trong cùng mô hình, tail bằng 0 và Deque không rỗng. Phần tử last có nằm ở ô 0 không?

**Gợi ý trả lời:** không theo quy ước đang dùng. Nó nằm ở ô lùi một bước theo vòng, tức ô 7 nếu L = 8.

### Bài 3: xóa đầu có phải sao chép không?

Nếu Deque có 1000 phần tử và gọi pollFirst không cần thay mảng, có phải chuyển 999 phần tử còn lại sang trái không?

**Gợi ý trả lời:** không. Cấu trúc có thể đọc và xóa ô head, rồi tiến head. Đó là lợi ích của cách quản lý vòng.

### Bài 4: thêm vào khi đã kín

Nếu head đã đi qua nhiều vị trí nhưng số phần tử vẫn lấp đầy vùng lưu theo quy ước, quay về đầu mảng có tạo thêm chỗ không?

**Gợi ý trả lời:** không. Chỉ các ô thực sự đã trống mới được tái sử dụng. ArrayDeque cần tăng mảng khi không còn đủ chỗ, không ghi đè phần tử chưa được lấy.

### Bài 5: đọc O(1) khấu hao

Một lần addLast mất nhiều thời gian hơn các lần trước vì cần tăng mảng. Điều đó có mâu thuẫn với O(1) khấu hao không?

**Gợi ý trả lời:** không. Khấu hao nói về tổng công việc của một chuỗi; một thao tác riêng vẫn có thể tốn O(n).

### Bài 6: constructor và giới hạn

Khởi tạo ArrayDeque với 16 có bảo đảm phần tử thứ 17 bị từ chối không?

**Gợi ý trả lời:** không. Con số là nhu cầu sức chứa ban đầu, không phải giới hạn cố định của collection.

### Bài 7: size nhỏ sau một đỉnh tải lớn

Deque từng có rất nhiều phần tử, sau đó chỉ còn một ít. Có thể suy ra mảng nền đã nhỏ tương ứng không?

**Gợi ý trả lời:** không với triển khai đang xét. Size phản ánh số phần tử hiện tại; mảng nền có thể còn giữ sức chứa từ trước.

### Bài 8: tăng mảng có clone đối tượng không?

Một đối tượng Customer được giữ cả trong Deque lẫn một biến ngoài. Sau tăng mảng, đó có tự thành hai Customer độc lập không?

**Gợi ý trả lời:** không. Tăng mảng tổ chức lại các tham chiếu, không mặc định sao chép sâu đối tượng.

### Bài 9: đầu ra không đủ để đọc chỉ số

Hai phiên bản JDK cùng in `[A, B, C]`. Có thể kết luận chúng có cùng head, tail và độ dài mảng không?

**Gợi ý trả lời:** không. Đó là cùng dãy logic; nhiều bố trí nội bộ có thể biểu đạt cùng kết quả.

Khi dùng ArrayDeque, hãy giữ rõ sự khác nhau giữa dãy logic, vị trí vòng và dung lượng đã cấp phát. Nhờ đó có thể khai thác thao tác hai đầu mà vẫn hiểu đúng lúc tăng mảng, chi phí khấu hao và vòng đời bộ nhớ.
