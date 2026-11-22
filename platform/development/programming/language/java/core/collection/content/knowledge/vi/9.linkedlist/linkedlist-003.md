# LinkedList: chi phí tìm nút theo chỉ số

`LinkedList` triển khai giao diện `List`, nên có `get(i)`, `set(i, value)`, `add(i, value)` và `remove(i)`. Nhưng việc có cùng tên phương thức với `ArrayList` không có nghĩa là có cùng cách tìm vị trí.

Một mảng có thể truy cập vị trí i trực tiếp. Một danh sách liên kết phải tìm nút chứa vị trí đó bằng cách đi qua các liên kết. Java `LinkedList` có liên kết hai chiều và giữ tham chiếu đến cả đầu lẫn cuối, nên có thể bắt đầu từ phía gần hơn. Cách này giảm số bước đi, nhưng không làm truy cập giữa danh sách thành O(1).

Điểm cần nắm là: **tìm đến nút** và **thực hiện công việc tại nút đã tìm được** là hai phần chi phí khác nhau. Nhầm lẫn hai phần này dễ dẫn tới vòng lặp O(n²) hoặc kết luận sai rằng chèn/xóa theo chỉ số luôn có chi phí hằng số.

## 1. Mô hình: chỉ số là vị trí logic, không phải địa chỉ nút

Một danh sách liên kết hai chiều có thể được hình dung như sau:

~~~text
first                                             last
  |                                                 |
  v                                                 v
 [A] <-> [B] <-> [C] <-> [D] <-> [E] <-> [F] <-> [G]
  0       1       2       3       4       5       6
             chi so logic trong danh sach
~~~

Mỗi nút giữ phần tử và liên kết tới nút trước, nút sau. Các số 0, 1, 2… trong sơ đồ là vị trí mà ta dùng để giải thích thứ tự. Không có một mảng công khai ánh xạ mỗi số đó tới sẵn một nút.

Biết `i = 4` nghĩa là biết mình muốn phần tử thứ năm. Điều đó chưa cung cấp trực tiếp tham chiếu tới nút E.

Theo [tài liệu LinkedList Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), các thao tác truy cập theo chỉ số đi từ đầu hoặc cuối, tùy phía nào gần vị trí cần hơn. Đây là đặc tính quan trọng khi chọn cách duyệt và đánh giá chi phí.

### 1.1. Có liên kết prev giúp gì?

Nếu chỉ có liên kết tiến và chỉ giữ đầu danh sách, tìm chỉ số i cần đi i bước từ đầu. Với liên kết hai chiều và có cả `last`, tìm gần cuối có thể đi ngược ít bước hơn nhiều.

Ví dụ, một danh sách có 10.000 phần tử:

- Tìm chỉ số 2 có thể đi từ đầu qua hai liên kết.
- Tìm chỉ số 9.997 có thể đi từ cuối qua hai liên kết.
- Tìm chỉ số 5.000 vẫn cần đi qua khoảng một nửa danh sách.

Vì vậy, không phải mọi `get(i)` đều phải đi từ đầu. Cũng không phải có hai chiều thì mọi `get(i)` chỉ cần vài bước.

### 1.2. Phần tử khác nút chứa phần tử

`get(i)` trả về phần tử kiểu E, không trả về một đối tượng nút công khai để ứng dụng tự nối hoặc tháo.

Ngay cả khi đang giữ tham chiếu tới một phần tử, ta chưa chắc có tham chiếu tới nút chứa nó. Danh sách còn có thể chứa cùng một tham chiếu phần tử ở nhiều vị trí.

Do đó, câu “đã có đối tượng cần xóa nên xóa O(1)” không tự áp dụng cho `linkedList.remove(object)`. Phương thức đó còn phải tìm vị trí xuất hiện phù hợp theo giá trị.

## 2. Đếm số bước tìm nút cho một chỉ số hợp lệ

Gọi:

- n là số phần tử hiện có.
- i là chỉ số cần truy cập.
- `0 <= i < n`.

Khoảng cách từ đầu là i. Khoảng cách từ cuối, ở chỉ số n−1, là n−1−i.

Số bước đi qua liên kết khi chọn phía gần hơn:

~~~text
h(n, i) = min(i, n - 1 - i)
~~~

Đây là số lần chuyển từ một nút sang nút lân cận, không phải toàn bộ số lệnh mà JVM chạy. Ngay cả h = 0, vẫn phải kiểm tra chỉ số, lấy tham chiếu đầu/cuối và đọc phần tử.

Vì vậy, mô hình công việc của tìm nút và truy cập phần tử là:

~~~text
Theta(1 + min(i, n - 1 - i))
~~~

Thêm 1 giúp biểu diễn đúng phần việc hằng số ở hai đầu.

### 2.1. Ví dụ n = 8

| i | Đi từ đầu | Đi từ cuối | Phía gần hơn | Số bước h(n,i) |
|---:|---:|---:|---|---:|
| 0 | 0 | 7 | Đầu | 0 |
| 1 | 1 | 6 | Đầu | 1 |
| 2 | 2 | 5 | Đầu | 2 |
| 3 | 3 | 4 | Đầu | 3 |
| 4 | 4 | 3 | Cuối | 3 |
| 5 | 5 | 2 | Cuối | 2 |
| 6 | 6 | 1 | Cuối | 1 |
| 7 | 7 | 0 | Cuối | 0 |

Tìm chỉ số 4 đi từ nút ở chỉ số 7, qua 6, 5 rồi đến 4. Ta đi ba liên kết, không cần đi từ đầu qua bốn liên kết.

### 2.2. Cách chọn nhánh cụ thể trong OpenJDK 17

Ở [mã nguồn LinkedList của OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedList.java), hàm tìm nút nội bộ so sánh chỉ số với một nửa kích thước. Nửa đầu đi từ `first` qua `next`; phần còn lại đi từ `last` qua `prev`.

Nếu n lẻ, nút chính giữa cách hai đầu bằng nhau; cách chọn nhánh trong bản này đi từ cuối khi rơi đúng mốc giữa. Chọn đầu hay cuối trong trường hợp hòa không đổi số bước và không đổi bậc chi phí.

Chương trình trong bài mô phỏng quy tắc đếm này. Nó không gọi một API xem nút riêng và không đo trực tiếp trường nội bộ của JVM.

### 2.3. Vì sao lấy đầu và cuối vẫn O(1)?

Với i = 0:

~~~text
min(0, n - 1) = 0
~~~

Với i = n−1:

~~~text
min(n - 1, 0) = 0
~~~

Do đã giữ tham chiếu đầu và cuối, không cần lần theo danh sách để tìm hai vị trí này. Các thao tác thể hiện rõ mục đích như `getFirst()`, `getLast()`, `addFirst()`, `addLast()`, `removeFirst()`, `removeLast()` sử dụng trực tiếp các đầu mút trong triển khai đang xét.

O(1) mô tả số lượng công việc quản lý cấu trúc, không phải bảo đảm mọi lời gọi có cùng độ trễ tuyệt đối. Cấp nút mới, hoạt động bộ nhớ và môi trường chạy vẫn có thể ảnh hưởng thời gian thực.

### 2.4. Vì sao giữa vẫn O(n)?

Nếu i ở gần n/2, cả hai khoảng cách đều tỷ lệ với n. Đi n/2 bước thay vì n bước có lợi về số bước, nhưng:

~~~text
Theta(n/2) = Theta(n)
~~~

Giảm hệ số không đổi không thay đổi bậc tăng. Với yêu cầu truy cập một vị trí bất kỳ, trường hợp xấu nhất của tìm nút theo chỉ số vẫn tuyến tính.

Cách phát biểu đầy đủ là: **phụ thuộc vị trí, nhanh ở hai đầu, tuyến tính ở vùng giữa trong trường hợp xấu nhất**. Chỉ nói “LinkedList.get là O(n)” có thể dùng làm giới hạn xấu nhất, nhưng bỏ qua thông tin hữu ích về các vị trí gần đầu/cuối.

## 3. Những phương thức nào phải trả phần chi phí tìm nút?

### 3.1. get(i): tìm rồi đọc phần tử

`get(i)` kiểm tra chỉ số, tìm nút, rồi đọc phần tử trong nút. Đọc phần tử sau khi đã có nút là hằng số; phần đi qua liên kết tạo chi phí theo vị trí.

Hai lời gọi liên tiếp `get(i)` và `get(i+1)` không tự chia sẻ một con trỏ đang ở i. Trong triển khai OpenJDK được nêu, mỗi lời gọi `get` thực hiện việc tìm nút lại từ đầu hoặc cuối.

Đây là khác biệt quan trọng giữa truy cập lặp bằng chỉ số và duyệt bằng iterator.

### 3.2. set(i, value): tìm rồi thay tham chiếu phần tử

`set` không chèn nút và không thay đổi số phần tử. Tuy nhiên, nó vẫn phải tìm nút tại i trước khi thay giá trị.

Do đó, không thể suy từ “chỉ thay một tham chiếu” ra kết luận toàn bộ `set(i, value)` luôn O(1). Nếu chỉ số nằm giữa, bước tìm vẫn tuyến tính.

Nếu một thuật toán vừa `get(i)` rồi `set(i, newValue)` cho mọi i, nó có thể lặp phần đi tìm hai lần tại mỗi vị trí. Dùng `ListIterator` để đọc và thay tại vị trí đang duyệt tránh việc tìm lại theo chỉ số.

### 3.3. remove(i): tìm rồi tháo liên kết

Sau khi đã có nút, bỏ nó khỏi chuỗi liên kết cần cập nhật một số lượng tham chiếu cố định và các thông tin đầu/cuối khi cần. Không phải dồn mọi phần tử sau nó như trong mảng.

Nhưng `remove(i)` bắt đầu bằng một chỉ số, nên vẫn phải tìm nút. Chi phí toàn thao tác là:

~~~text
tim nut tai i + thao lien ket tai nut do
~~~

Với nút giữa, phần đầu tuyến tính, phần sau hằng số; tổng vẫn tuyến tính.

Không có một bước đi qua toàn bộ các nút phía sau chỉ để giảm “số chỉ mục” lưu trên chúng. Chỉ số là vị trí logic được suy ra từ thứ tự, không phải trường bắt buộc phải cập nhật trên từng nút.

### 3.4. add(i, value): chú ý vị trí chèn ở cuối

Miền hợp lệ của chèn rộng hơn miền đọc:

~~~text
get/set/remove:  0 <= i < n
add:             0 <= i <= n
~~~

Trong triển khai đang xét:

- Nếu i = n, có thể nối vào cuối trực tiếp.
- Nếu i < n, cần tìm nút hiện đang ở i rồi nối nút mới trước nó.
- Nối nút mới sau khi biết vị trí là phần việc hằng số, ngoài việc cấp phát.

Danh sách rỗng chỉ có vị trí chèn 0, nhưng không có vị trí đọc/xóa nào.

Không áp dụng công thức `min(i, n−1−i)` trực tiếp cho i = n: đó là công thức tìm một phần tử đã có, còn i = n là một khoảng chèn sau phần tử cuối.

### 3.5. Bảng tách hai giai đoạn

| Thao tác trên LinkedList | Cần tìm theo chỉ số? | Phần việc sau khi đã có nút/vị trí |
|---|---|---|
| `get(i)` | Có | Đọc phần tử |
| `set(i, x)` | Có | Thay phần tử |
| `remove(i)` | Có | Tháo nút và cập nhật liên kết |
| `add(i, x)`, i < n | Có | Nối nút mới trước nút tìm được |
| `add(n, x)` | Không cần duyệt tìm nút giữa | Nối cuối |
| `getFirst()`, `getLast()` | Không | Đọc trực tiếp đầu/cuối |
| `ListIterator.next()` đã định vị | Không tìm lại bằng chỉ số | Đi tới nút kế tiếp và trả phần tử |

Bảng mô tả việc quản lý cấu trúc dưới điều kiện sử dụng hợp lệ. Nó không tính công việc do ứng dụng làm với phần tử và không là cam kết độ trễ theo thời gian thực.

## 4. Bẫy lớn: vòng for theo chỉ số có thể thành O(n²)

Xét một đoạn thân phương thức minh họa:

~~~java
long sum = 0;
for (int index = 0; index < values.size(); index++) {
    sum += values.get(index);
}
~~~

Nếu `values` là `LinkedList`, mỗi lần `get(index)` tìm từ một đầu. Vòng lặp không giữ vị trí của lần trước.

### 4.1. Với n = 8, cộng số bước của từng get

Dãy số bước tìm là:

~~~text
index:       0  1  2  3  4  5  6  7
so buoc:     0  1  2  3  3  2  1  0

tong = 12 buoc lan theo lien ket
~~~

Ngoài 12 bước này còn có 8 lượt xử lý phần tử và phần việc hằng số mỗi vòng. Không nên nhầm số bước tìm với tổng số lệnh máy.

### 4.2. Chứng minh tổng theo n

Nếu n = 2m là số chẵn, dãy khoảng cách là:

~~~text
0, 1, ..., m-1, m-1, ..., 1, 0
~~~

Tổng:

~~~text
2 * (0 + 1 + ... + m-1) = m(m-1)
~~~

Nếu n = 2m+1 là số lẻ, dãy là:

~~~text
0, 1, ..., m-1, m, m-1, ..., 1, 0
~~~

Tổng:

~~~text
2 * (0 + 1 + ... + m-1) + m = m^2
~~~

Cả hai đều là Θ(n²). Việc luôn chọn đầu gần hơn làm tổng nhỏ hơn so với luôn đi từ đầu, nhưng vẫn không biến nó thành tuyến tính.

Với n = 1.000, tổng số bước tìm theo mô hình là 249.500. Duyệt một lượt không cần khởi động lại việc tìm 1.000 lần.

### 4.3. Lưu size ra biến không giải quyết phần chi phí chính

Trong OpenJDK `LinkedList`, kích thước được lưu sẵn. `size()` không cần đếm lại các nút mỗi lần.

Đổi điều kiện thành `index < cachedSize` có thể thay cách viết nhưng không loại bỏ việc `get(index)` tìm nút lại. Nếu vấn đề là bậc hai do truy cập theo chỉ số, phải đổi cách duyệt hoặc cách lưu dữ liệu.

Tương tự, duyệt chỉ số từ n−1 về 0 chỉ đảo thứ tự các khoảng cách. Tổng số bước tìm vẫn là tổng cũ nếu đọc mọi chỉ số một lần theo cách đó.

### 4.4. Truy cập lặp ở cùng vị trí giữa cũng phải xét lại

Nếu gọi `get(n/2)` q lần độc lập trên một danh sách không đổi, mỗi lần vẫn phải đi tới nút giữa. Tổng phần tìm có thể là Θ(qn).

Nếu thực sự chỉ cần sử dụng lại cùng một phần tử và danh sách không đổi theo cách ảnh hưởng yêu cầu, có thể lấy phần tử một lần rồi dùng biến đang giữ nó. Nếu cần duyệt các phần tử lân cận, dùng một iterator đã định vị.

Không tự giả định thư viện sẽ nhớ nút được truy cập gần nhất giữa các lời gọi `get`.

## 5. Iterator giữ vị trí: trả chi phí tìm một lần rồi tiến từng bước

### 5.1. Duyệt tuần tự bằng for-each

Đoạn minh họa:

~~~java
long sum = 0;
for (int value : values) {
    sum += value;
}
~~~

Với `LinkedList`, bộ lặp đi qua chuỗi nút đang có. Mỗi lần tiến dùng liên kết tiếp theo, không đổi một số nguyên thành vị trí bằng cách tìm lại từ đầu/cuối.

Một lượt duyệt n phần tử có chi phí O(n), cộng công việc xử lý từng phần tử. Mã ngắn hơn không phải nguyên nhân làm nhanh hơn; nguyên nhân là bảo toàn trạng thái vị trí giữa các bước.

Ví dụ dùng `int` giả định phần tử không phải `null`, vì đọc vào biến nguyên thủy cần mở hộp. Nếu danh sách cho phép `null`, cách xử lý phải phù hợp với dữ liệu.

### 5.2. listIterator(i) không miễn phí ở giữa

`ListIterator` có con trỏ nằm giữa các phần tử. Với `listIterator(i)`, lần `next()` đầu tiên sẽ trả phần tử tại i nếu còn phần tử.

Để đặt con trỏ vào giữa một `LinkedList`, triển khai cần tìm nút tương ứng. Vì vậy:

~~~text
tao iterator tai vi tri i:
    tra chi phi dinh vi ban dau

sau do next/previous:
    di theo lien ket, moi buoc O(1)
~~~

Nếu đi qua k phần tử sau khi định vị tại i < n, mô hình chi phí là:

~~~text
O(1 + min(i, n - 1 - i) + k)
~~~

Thay vì gọi `get(i)`, `get(i+1)`… rồi trả phần tìm lại cho từng vị trí, ta định vị một lần.

### 5.3. Vị trí size là con trỏ hợp lệ ở cuối

`listIterator(n)` hợp lệ: con trỏ nằm sau phần tử cuối, `hasNext()` là false; nếu danh sách không rỗng, `previous()` có thể trả phần tử cuối.

Ở OpenJDK đang xét, việc tạo iterator tại cuối không phải đi qua n nút. Nó dùng trạng thái cuối trực tiếp.

Ngược lại, `get(n)` không hợp lệ, vì không có phần tử ở vị trí n. Phải phân biệt **chỉ số phần tử** với **vị trí con trỏ/khoảng chèn**.

### 5.4. Giữ một iterator cho nhiều chỉnh sửa cục bộ

Khi `ListIterator` của `LinkedList` đã tới vị trí, `set`, `add` và `remove` hợp lệ có thể làm việc bằng các tham chiếu nút mà nó đang giữ. Không cần tìm lại nút bằng chỉ số cho từng thao tác.

Ví dụ: định vị trước phần tử 3, đọc nó, thay giá trị, chèn một phần tử kế bên, đọc phần tử tiếp theo rồi xóa phần tử vừa đọc. Chi phí định vị được trả ở đầu; phần cập nhật cục bộ sau đó dùng số lượng thao tác liên kết cố định.

Nhưng các phương thức có quy tắc trạng thái:

- `set` và `remove` cần có phần tử vừa được trả bởi `next` hoặc `previous`.
- Sau `add`, trạng thái “phần tử vừa trả” để dùng cho `set/remove` bị đặt lại.
- Không gọi `remove` hai lần cho cùng một lần đọc.
- Không sửa cấu trúc qua đường khác rồi tiếp tục dùng iterator như thể vị trí vẫn hợp lệ.

Chương trình bên dưới gọi `next` sau `add` trước khi `remove`, nên xóa đúng phần tử vừa đọc. Việc có chi phí tốt không cho phép bỏ qua hợp đồng thao tác.

### 5.5. Tạo một iterator mới trong mỗi vòng vẫn có thể chậm

Nếu mỗi vòng đều gọi `listIterator(i)` rồi chỉ `next()` một lần, ta vẫn lặp việc định vị. Cú pháp có chữ “iterator” chưa bảo đảm đã dùng thuật toán tuyến tính.

Lợi ích xuất hiện khi giữ và tiến chính iterator đó qua các vị trí cần duyệt. Hãy đếm số lần định vị, không chỉ đếm số lần gọi `next`.

## 6. Chương trình hoàn chỉnh: truy cập theo chỉ số và duyệt tuần tự

Chương trình tạo một `LinkedList` thật, đọc các vị trí và đối chiếu kết quả duyệt. Các cột `modeledHops` và `initialHops` được **tính theo công thức**, không phải số đọc từ bên trong JVM.

Mục tiêu là làm rõ cơ chế và kiểm tra phép tính; không dùng ví dụ này để kết luận một tỷ lệ tốc độ theo nano giây.

### 6.1. Mã nguồn

Lưu thành `LinkedListIndexCostDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class LinkedListIndexCostDemo {
    // So buoc di qua lien ket theo mo hinh, khong do noi bo JVM.
    static int modeledHops(int size, int index) {
        Objects.checkIndex(index, size);
        return Math.min(index, size - 1 - index);
    }

    static long allIndexHops(int size) {
        if (size < 0) {
            throw new IllegalArgumentException("negative size");
        }
        long half = size / 2L;
        return size % 2 == 0 ? half * (half - 1) : half * half;
    }

    public static void main(String[] args) {
        LinkedList<Integer> values = new LinkedList<>();
        for (int value = 0; value < 8; value++) {
            values.addLast(value);
        }
        System.out.println("values: " + values);
        System.out.println("index, direction, modeledHops, value");
        for (int index = 0; index < values.size(); index++) {
            String direction = index < values.size() / 2 ? "HEAD" : "TAIL";
            System.out.printf("%d, %s, %d, %d%n", index, direction,
                    modeledHops(values.size(), index), values.get(index));
        }

        long indexedSum = 0;
        long indexedHops = 0;
        for (int index = 0; index < values.size(); index++) {
            indexedSum += values.get(index);
            indexedHops += modeledHops(values.size(), index);
        }
        long sequentialSum = 0;
        int visits = 0;
        for (int value : values) {
            sequentialSum += value;
            visits++;
        }
        System.out.printf("get loop: sum=%d, modeledHops=%d%n",
                indexedSum, indexedHops);
        System.out.printf("for-each: sum=%d, visits=%d%n", sequentialSum, visits);
        System.out.println("same sums: " + (indexedSum == sequentialSum));

        for (int size : new int[] {8, 9, 10, 100, 1000}) {
            System.out.printf("formula only: n=%d, allIndexHops=%d%n",
                    size, allIndexHops(size));
        }

        int start = 3;
        int width = 3;
        ListIterator<Integer> range = values.listIterator(start);
        long rangeSum = 0;
        for (int count = 0; count < width; count++) {
            rangeSum += range.next();
        }
        System.out.printf("range [3,6): initialHops=%d, nextCalls=%d, sum=%d%n",
                modeledHops(values.size(), start), width, rangeSum);

        ListIterator<Integer> editor = values.listIterator(3);
        int first = editor.next();
        editor.set(30);
        editor.add(31);
        int second = editor.next();
        editor.remove();
        System.out.printf("editor read=%d then %d, values=%s%n",
                first, second, values);

        ListIterator<Integer> reverse = values.listIterator(values.size());
        System.out.println("iterator at size, previous: " + reverse.previous());
        try {
            values.get(values.size());
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(size): IndexOutOfBoundsException");
        }

        List<Integer> linkedAsList = values;
        List<Integer> arrayAsList = new ArrayList<>(values);
        System.out.println("LinkedList RandomAccess: "
                + (linkedAsList instanceof RandomAccess));
        System.out.println("ArrayList RandomAccess: "
                + (arrayAsList instanceof RandomAccess));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 LinkedListIndexCostDemo.java
java LinkedListIndexCostDemo
~~~

### 6.2. Kết quả stdout

~~~text
values: [0, 1, 2, 3, 4, 5, 6, 7]
index, direction, modeledHops, value
0, HEAD, 0, 0
1, HEAD, 1, 1
2, HEAD, 2, 2
3, HEAD, 3, 3
4, TAIL, 3, 4
5, TAIL, 2, 5
6, TAIL, 1, 6
7, TAIL, 0, 7
get loop: sum=28, modeledHops=12
for-each: sum=28, visits=8
same sums: true
formula only: n=8, allIndexHops=12
formula only: n=9, allIndexHops=16
formula only: n=10, allIndexHops=20
formula only: n=100, allIndexHops=2450
formula only: n=1000, allIndexHops=249500
range [3,6): initialHops=3, nextCalls=3, sum=12
editor read=3 then 4, values=[0, 1, 2, 30, 31, 5, 6, 7]
iterator at size, previous: 7
get(size): IndexOutOfBoundsException
LinkedList RandomAccess: false
ArrayList RandomAccess: true
~~~

### 6.3. Giải thích kết quả

Tám dòng chỉ số cho thấy phía tìm và khoảng cách theo mô hình. Hai đầu đều có số bước 0; vùng giữa cần 3 bước với n = 8.

Hai cách tính tổng cùng cho 28. Điều đó kiểm tra rằng thay cách duyệt không làm thay kết quả trong dữ liệu thử. Khác biệt về thuật toán nằm ở việc vòng `get` tìm lại vị trí, còn `for-each` tiến liên tục.

Các dòng `formula only` chỉ tính tổng bằng công thức; không tạo các danh sách rồi đo hàng nghìn lời gọi. `long` được dùng cho tích và tổng để tránh tràn `int` khi n tăng.

Với đoạn `[3,6)`, iterator được đặt tại 3 bằng một lần định vị theo mô hình, sau đó gọi `next` ba lần để nhận 3, 4, 5 và tính tổng 12. `initialHops` và `nextCalls` đo hai loại công việc khác nhau, không phải hai cột thời gian để cộng thành nano giây.

Phần `editor`:

1. Đọc 3 và thay nó bằng 30.
2. Chèn 31 ở vị trí con trỏ, trước 4.
3. Đọc 4 rồi xóa nó qua chính iterator.
4. Nhận `[0, 1, 2, 30, 31, 5, 6, 7]`.

Đây là ví dụ cập nhật cục bộ sau khi đã định vị. Nó không nói `values.add(3, ...)` tự nhiên miễn bước tìm.

`listIterator(size)` đi lùi được tới 7, còn `get(size)` ném `IndexOutOfBoundsException`. Chương trình tự in tên loại ngoại lệ nên không phụ thuộc câu thông báo riêng của từng bản JDK.

Hai dòng `RandomAccess` minh họa rằng cùng giữ qua biến kiểu `List` nhưng đối tượng thật vẫn có đặc tính truy cập khác nhau.

## 7. List và RandomAccess: cùng giao diện không có nghĩa cùng chi phí

### 7.1. Kiểu biến không thay cấu trúc bên dưới

Đoạn minh họa:

~~~java
List<String> values = new LinkedList<>();
~~~

Lệnh `values.get(i)` vẫn chạy theo triển khai của `LinkedList`. Khai báo qua giao diện giúp giảm phụ thuộc về kiểu, nhưng không biến danh sách liên kết thành mảng.

Nếu viết một phương thức nhận `List<T>`, hãy tránh mặc định rằng mọi `get(i)` đều O(1). Một vòng `for-each` thường diễn đạt tốt hơn khi mục đích chỉ là xem từng phần tử một lần.

Hợp đồng `List` cho phép truy cập bằng chỉ số, không bảo đảm mọi lớp triển khai có cùng chi phí cho cách truy cập đó. Xem [List Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### 7.2. RandomAccess là dấu hiệu để thuật toán lựa chọn cách đi

`RandomAccess` là một giao diện đánh dấu cho các `List` hỗ trợ truy cập ngẫu nhiên hiệu quả. `ArrayList` triển khai dấu hiệu này; `LinkedList` không triển khai nó.

Tài liệu [RandomAccess Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) giải thích vai trò của dấu hiệu này để thuật toán tổng quát tránh lựa chọn cách truy cập bất lợi cho các danh sách khác nhau.

Nó không tự tối ưu một vòng lặp mà ứng dụng đã viết. Nếu mã vẫn gọi `get(i)` cho từng i trên một `LinkedList`, không có cơ chế tự động đổi vòng đó thành iterator chỉ vì một giao diện đánh dấu tồn tại trong thư viện.

Khi không cần một chiến lược chuyên biệt, duyệt qua iterator là cách đơn giản để không phụ thuộc vào khả năng truy cập ngẫu nhiên. Khi thật sự cần chọn hai chiến lược, việc kiểm tra dấu hiệu cần đi cùng phân tích thuật toán và yêu cầu cụ thể.

### 7.3. Sao chép sang ArrayList cho nhiều lượt truy cập chỉ số

Nếu đã có một `LinkedList` ổn định nhưng giai đoạn sau cần rất nhiều truy cập chỉ số rời rạc, có thể cân nhắc:

~~~java
List<String> indexed = new ArrayList<>(linkedSource);
~~~

Việc chuyển một lần cần đọc nguồn và tạo cấu trúc chứa các tham chiếu, có chi phí tuyến tính và cần thêm bộ nhớ. Sau đó, truy cập `get` theo chỉ số của `ArrayList` có chi phí hằng số, theo [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Nếu chỉ đọc một phần tử hoặc chỉ duyệt một lần, tạo bản sao có thể không cần thiết. Nếu nguồn tiếp tục thay đổi, bản sao không tự phản ánh cấu trúc mới; phải chọn thời điểm và quyền sở hữu rõ ràng.

Constructor sao chép danh sách không tự sao chép sâu đối tượng phần tử. Hai cấu trúc có thể vẫn cùng giữ tham chiếu tới một đối tượng có thể thay đổi.

## 8. Đừng nhầm tìm theo chỉ số với tìm theo giá trị

### 8.1. indexOf không biết trước vị trí đích

`get(i)` biết i rồi tìm nút ở đó. `indexOf(value)` cần tìm xem phần tử phù hợp đầu tiên nằm ở đâu.

Trong triển khai đang xét, `indexOf` đi tuần tự từ đầu, kiểm tra phần tử ở mỗi nút. Nó không thử `get(0)`, `get(1)`, `get(2)` theo một vòng lặp gây tìm lại cho từng vị trí.

Vì vậy, việc tìm theo giá trị có trường hợp xấu nhất O(n) lần xem phần tử, cộng chi phí so sánh. Không được nhìn cách mô tả hợp đồng bằng `get(i)` rồi suy ra mã triển khai chắc chắn dùng vòng `get` bậc hai.

### 8.2. indexOf rồi get có thể đi lại một đoạn

Nếu chỉ cần đối tượng phù hợp với một điều kiện, việc tìm chỉ số trước rồi `get` lại có thể khiến chương trình đi qua một phần danh sách lần nữa.

Một lượt duyệt trả trực tiếp phần tử tìm thấy có thể đủ. Nếu cần sửa/xóa phần tử đang tìm, một iterator có quy tắc sử dụng phù hợp có thể giữ được vị trí.

Không phải mọi lần đi lại đều là lỗi đáng tối ưu; đây là cách nhận diện phần công việc để đánh giá khi dữ liệu lớn hoặc thao tác lặp nhiều lần.

### 8.3. remove(Object) không phải remove(int)

Với danh sách số nguyên, `remove(2)` chọn overload xóa tại chỉ số 2; `remove(Integer.valueOf(2))` tìm và xóa một phần tử bằng giá trị 2.

Xóa theo giá trị không có được nút trực tiếp chỉ vì đối tượng được truyền vào. Chi phí tìm vẫn cần xét, rồi mới đến bước tháo liên kết.

## 9. Những giới hạn của mô hình chi phí

### 9.1. Số bước liên kết không phải thời gian thực

Một bước từ nút hiện tại sang nút tiếp theo cần đọc tham chiếu. Độ trễ thực có thể phụ thuộc cách các nút nằm trong bộ nhớ, bộ nhớ đệm, JVM và tải hệ thống.

Số bước giúp giải thích bậc tăng và lượng công việc lặp. Nó không cho phép khẳng định “mỗi bước mất đúng X nano giây” hay “danh sách này luôn chậm hơn cấu trúc kia đúng Y lần”.

Nếu cần quyết định hiệu năng ở một ứng dụng thực, phải đo kiểu truy cập cụ thể, kích thước dữ liệu và môi trường mục tiêu.

### 9.2. Phần việc của người dùng được cộng riêng

Duyệt bằng iterator là O(n) về cấu trúc. Nếu mỗi phần tử gây truy vấn mạng, tìm kiếm trên một tập khác hoặc phép tính O(n), tổng ứng dụng có thể lớn hơn O(n).

Tương tự, truy cập đầu danh sách là O(1) không làm biểu thức `getFirst().expensiveOperation()` thành O(1) xét toàn bộ công việc.

### 9.3. Công thức giả định trạng thái hợp lệ, ổn định trong lúc phân tích

n và i được hiểu tại thời điểm thao tác. Nếu thêm/xóa, kích thước và chỉ số phần tử phía sau có thể đổi; cần cập nhật lại cách tính.

Nếu i không hợp lệ, phương thức kiểm tra chỉ số rồi ném ngoại lệ, không áp dụng công thức tìm nút như thể có một nút ở ngoài danh sách.

`LinkedList` không tự an toàn khi nhiều luồng cùng thay đổi cấu trúc. Fail-fast của iterator không phải cơ chế đồng bộ và không bảo đảm phát hiện mọi truy cập sai. Ví dụ trong bài chỉ dùng một luồng.

### 9.4. Giữ một iterator là giữ một trạng thái sử dụng

Một iterator hữu ích vì giữ vị trí, nhưng vị trí đó đi kèm trạng thái và sự hợp lệ đối với cấu trúc danh sách. Không xem iterator như một mã định danh bền vững để cất giữ rồi sửa danh sách qua nhiều đường độc lập.

Nếu bài toán cần tham chiếu ổn định tới các đối tượng nghiệp vụ, hãy thiết kế định danh của phần tử. Đừng đồng nhất nó với chỉ số hoặc một iterator cũ.

## 10. Các lỗi suy luận thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| LinkedList có get nên truy cập chỉ số giống mảng | Cần tìm nút bằng liên kết |
| Mọi get đều đi từ đầu | Có thể đi từ đầu hoặc cuối gần hơn |
| Có hai chiều nên tìm giữa O(1) | Giữa vẫn cách mỗi đầu một số bước tỷ lệ với n |
| Đi n/2 thay vì n thì không còn tuyến tính | Hệ số 1/2 không đổi bậc Θ(n) |
| get(0) cũng phải duyệt n nút | Có tham chiếu đầu, không cần đi qua liên kết |
| set chỉ thay giá trị nên toàn thao tác luôn O(1) | Phải tính bước tìm nút theo chỉ số |
| Xóa nút O(1) nên remove(i) luôn O(1) | remove(i) còn phải định vị |
| Biết đối tượng phần tử nghĩa là đã có nút của nó | Phần tử và nút chứa phần tử là hai đối tượng khác nhau |
| Vòng get theo chỉ số chỉ đi qua danh sách một lần | Mỗi get có thể khởi động việc tìm lại |
| Duyệt chỉ số giảm dần tránh bậc hai | Nó chỉ đảo thứ tự các khoảng cách |
| Dùng listIterator(i) luôn tạo trong O(1) | Tạo ở giữa còn phải tìm vị trí |
| Tạo iterator mới mỗi vòng vẫn là một lượt duyệt | Chi phí định vị có thể bị lặp lại |
| Khai báo List làm chi phí giống nhau | Đối tượng triển khai quyết định cơ chế |
| Không có RandomAccess nghĩa là không dùng được get | get vẫn có, nhưng thuật toán cần xét chi phí |
| Tìm theo giá trị chắc chắn gọi get(i) nhiều lần | Thư viện có thể duyệt trực tiếp qua liên kết |

## 11. Bài tập tự kiểm tra

### Bài 1: khoảng cách từ hai đầu

Danh sách có n = 12. Tìm i = 2 và i = 9 cần bao nhiêu bước theo mô hình?

**Giải thích:** i = 2 có khoảng cách 2 từ đầu, 9 từ cuối, chọn 2. i = 9 có khoảng cách 9 từ đầu, 2 từ cuối, cũng chọn 2. Hai vị trí đối xứng có cùng khoảng cách nhỏ nhất.

### Bài 2: nút giữa của số phần tử lẻ

n = 9, tìm i = 4. Có bao nhiêu bước? Việc chọn đầu hay cuối có làm đổi kết quả bậc lớn không?

**Giải thích:** Cả hai khoảng cách đều bằng 4. Bản OpenJDK được nêu chọn nhánh từ cuối ở điểm hòa này, nhưng số bước và bậc chi phí không đổi.

### Bài 3: vòng đọc mọi chỉ số

Với n = 10, tổng số bước tìm của `get(0)` đến `get(9)` là bao nhiêu?

**Giải thích:** n = 2m với m = 5, tổng là m(m−1) = 20. Ngoài 20 bước đi còn có phần việc hằng số cho 10 lần truy cập. Khi n tăng, tổng có bậc hai.

### Bài 4: đọc một khoảng liên tiếp

Cần đọc 100 phần tử liên tiếp bắt đầu ở giữa một danh sách liên kết lớn. Nên tạo iterator một lần hay gọi get theo từng chỉ số?

**Giải thích:** Một iterator được định vị một lần rồi tiến qua 100 phần tử tránh tìm lại nút từ đầu/cuối cho từng chỉ số. Phải tính chi phí định vị ban đầu và đảm bảo khoảng đọc hợp lệ.

### Bài 5: sửa tại vị trí đã tới

Một `ListIterator` đã vừa trả về một phần tử. Vì sao `iterator.set(x)` có thể có chi phí cấu trúc hằng số, còn `list.set(i, x)` ở giữa có thể tuyến tính?

**Giải thích:** Iterator giữ nút vừa trả; lời gọi theo chỉ số phải tìm lại nút. Cả hai cùng thay phần tử nhưng nhận thông tin vị trí khác nhau.

### Bài 6: vị trí n

Danh sách có 5 phần tử. `get(5)`, `add(5, x)`, `listIterator(5)` có cùng tính hợp lệ không?

**Giải thích:** Không. `get(5)` không có phần tử để đọc. Hai thao tác còn lại cho phép vị trí sau phần tử cuối: chèn cuối hoặc đặt con trỏ ở cuối.

Khi phân tích một thao tác trên `LinkedList`, hãy hỏi: **vị trí đã được giữ dưới dạng con trỏ hợp lệ, hay chỉ mới có một số chỉ mục?** Câu trả lời quyết định có phải trả thêm phần tìm nút, và giúp chọn giữa truy cập theo chỉ số, giữ iterator hoặc chuyển sang cách lưu trữ phù hợp hơn.
