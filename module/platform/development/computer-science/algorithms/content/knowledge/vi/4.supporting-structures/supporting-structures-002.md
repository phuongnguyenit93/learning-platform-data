# Mảng, danh sách và đánh đổi khi truy cập, thêm, xóa

Mảng và danh sách là những cấu trúc hỗ trợ thường xuyên xuất hiện trong thuật toán: lưu tập dữ liệu có thứ tự, quản lý trạng thái, duyệt phần tử và thực hiện thao tác cập nhật. Tuy cùng cho phép chứa một dãy phần tử, **mảng có kích thước cố định, mảng động và danh sách liên kết** sử dụng các cách lưu trữ khác nhau, dẫn đến chi phí truy cập, thêm và xóa khác nhau.

**Mục tiêu học tập:** phân biệt các cấu trúc theo cách lưu trữ và hợp đồng thao tác; tính được số phần tử phải dịch chuyển khi chèn/xóa; hiểu chi phí khấu hao của mảng động; tránh nhầm thao tác trên `LinkedList` là O(1) khi trước đó phải tìm vị trí; chọn cấu trúc phù hợp với tần suất thao tác, bộ nhớ và đặc tính dữ liệu trong Java 17+.

## 1. Mảng và danh sách: phân biệt ý nghĩa trừu tượng với cách triển khai

**Danh sách (list)** là một tập hợp có thứ tự, có thể có các phần tử trùng nhau. Danh sách thường hỗ trợ các thao tác đọc phần tử ở vị trí `i`, thay đổi phần tử, thêm và xóa. Danh sách là **giao diện trừu tượng**; cách cài đặt quyết định chi phí thực tế của từng thao tác.

**Mảng (array)** cung cấp các vị trí liên tiếp theo chỉ số từ `0` tới `length - 1`. Mảng Java có độ dài cố định sau khi được tạo. Ví dụ `new int[4]` tạo bốn vị trí kiểu `int`, ban đầu đều bằng 0. Thay đổi giá trị của phần tử được, nhưng không thể thay đổi `length` của chính đối tượng mảng đó.

Một thuật toán cũng có thể sử dụng mảng như **bộ đệm có sức chứa**: mảng vật lý có `capacity` vị trí, còn `size` là số phần tử hiện đang hợp lệ, thỏa `0 ≤ size ≤ capacity`. Khi thêm vượt sức chứa, phải cấp phát mảng mới và sao chép; thao tác đó không làm độ dài của mảng cũ tăng lên.

Có ba cách triển khai phổ biến:

- **Mảng cố định (`int[]`, `String[]`):** số ô vật lý không đổi; truy cập theo chỉ số trực tiếp. Chèn hoặc xóa mà phải giữ thứ tự đòi hỏi dịch chuyển phần tử và cập nhật `size` nếu dùng bộ đệm.
- **Mảng động (`ArrayList<E>`):** duy trì một vùng lưu kiểu mảng chứa các tham chiếu, tự quản lý dung lượng và số phần tử. Truy cập theo chỉ số nhanh; thêm cuối thường rẻ; chèn/xóa ở giữa hoặc đầu phải dịch chuyển.
- **Danh sách liên kết đôi (`LinkedList<E>`):** mỗi phần tử nằm trong một nút có liên kết tới nút trước/sau. Thêm/xóa ở hai đầu nhanh; truy cập vị trí bất kỳ phải đi qua các nút.

Trong Java, `List<E>` chỉ là **giao diện**. Khi nhìn thấy `List<Integer> data`, chưa thể kết luận `data.get(i)` là O(1): còn phải biết đối tượng thực tế là `ArrayList`, `LinkedList` hay một triển khai khác.

## 2. Bảng so sánh chi phí

Gọi `n` là số phần tử hiện tại. Bảng dùng mô hình RAM thông thường, phép so sánh và sao chép một phần tử được xem O(1). Các chi phí chèn/xóa đều giả sử phải **giữ nguyên thứ tự tương đối** của các phần tử còn lại, trừ khi ghi chú khác.

| Thao tác | Mảng cố định hoặc bộ đệm mảng | `ArrayList<E>` | `LinkedList<E>` |
|---|---|---|---|
| Đọc hoặc ghi ở chỉ số hợp lệ `i` | O(1) | O(1) cho `get/set` | O(n) trong trường hợp xấu cho `get/set(index)` |
| Duyệt toàn bộ `n` phần tử | Θ(n) | Θ(n) | Θ(n) |
| Thêm vào cuối | O(1) nếu còn chỗ; O(n) nếu phải tạo mảng lớn hơn | O(1) **khấu hao**; một lần mở rộng có thể O(n) | O(1) với `addLast` |
| Thêm vào đầu | O(n) do dịch chuyển | O(n) do dịch chuyển | O(1) với `addFirst` |
| Chèn tại vị trí `i` bất kỳ | O(n) trong trường hợp xấu | O(n) trong trường hợp xấu | O(n) để tìm vị trí; liên kết nút sau khi đã tìm được là O(1) |
| Xóa phần tử cuối | O(1) nếu quản lý `size` logic | O(1) với `remove(size-1)` | O(1) với `removeLast` |
| Xóa phần tử đầu | O(n) khi giữ thứ tự | O(n) | O(1) với `removeFirst` |
| Xóa tại chỉ số `i` bất kỳ | O(n) trong trường hợp xấu | O(n) trong trường hợp xấu | O(n) để tìm nút; gỡ liên kết nút đã có là O(1) |
| Tìm giá trị trong dãy chưa sắp xếp | O(n) | O(n) với `contains/indexOf` | O(n) |
| Bộ nhớ lưu `n` phần tử | O(n) | O(n), có thể dư sức chứa | O(n), thêm các nút và liên kết |

**Các điểm cần đọc đúng trong bảng:**

1. O(n) trong trường hợp xấu không có nghĩa thao tác nào cũng mất đúng `n` bước. Ví dụ xóa cuối `ArrayList` là O(1), nhưng xóa đầu phải dịch chuyển gần `n` phần tử.
2. `LinkedList` chèn giữa bằng một **iterator đang ở đúng vị trí** có thể thay đổi liên kết O(1), nhưng nếu chỉ biết chỉ số hay giá trị thì quá trình tìm nút thường đã tốn O(n).
3. “O(1) khấu hao” không có nghĩa **mọi lần** thêm cuối vào `ArrayList` đều O(1); khi cần tăng dung lượng, có lần phải sao chép cả mảng.
4. Hai triển khai đều chiếm O(n) bộ nhớ nhưng hệ số có thể khác lớn. `LinkedList` thường dùng nhiều bộ nhớ/đối tượng hơn, còn `ArrayList` có thể dành các ô chứa tham chiếu chưa sử dụng.

## 3. Mảng: truy cập nhanh, chèn/xóa giữ thứ tự phải dịch chuyển

Cho dãy logic có `n` phần tử ở chỉ số `0..n-1`. Chèn `x` vào vị trí `i` với `0 ≤ i ≤ n` và vẫn giữ thứ tự các phần tử cũ nghĩa là mọi phần tử từ `i` trở đi phải dời sang phải một ô:

`a[n] = a[n-1], a[n-1] = a[n-2], ..., a[i+1] = a[i]`.

Nếu bộ đệm còn chỗ, cần đúng **`n-i` phép dời phần tử**. Chèn đầu `i=0` cần dời `n` phần tử; chèn cuối `i=n` không cần dời phần tử nào. Nếu không còn chỗ, còn phải cấp phát và sao chép dữ liệu sang mảng mới.

Xóa phần tử tại `i`, với `0 ≤ i < n` và giữ thứ tự, cần dời các phần tử sau vị trí đó sang trái. Số phần tử phải dời là **`n-i-1`**; xóa cuối bằng 0 lần dời, xóa đầu bằng `n-1` lần dời.

Ví dụ:

~~~text
Ban đầu:      [10, 20, 30, 40]     n = 4
Chèn 15 tại i=1:
Dời sang phải [20, 30, 40]         3 phần tử
Kết quả:      [10, 15, 20, 30, 40] n = 5

Xóa tại i=2 (giá trị 20):
Dời sang trái [30, 40]             2 phần tử
Kết quả:      [10, 15, 30, 40]     n = 4
~~~

Java có `System.arraycopy(src, srcPos, dest, destPos, length)` để sao chép các đoạn mảng. Hàm xử lý chính xác các vùng nguồn và đích **chồng lấn**. Nếu độ dài cần sao chép là `k` thì việc xử lý dữ liệu vẫn là O(k), dù mã chỉ có một lời gọi hàm. Lỗi thường gặp là cho rằng một dòng gọi `arraycopy` tương đương O(1).

### Nếu không cần giữ thứ tự: xóa bằng hoán đổi với phần tử cuối

Giả sử ta lưu một tập hợp mà thứ tự **không có ý nghĩa**; đã biết chỉ số `i` và dữ liệu nằm trong bộ đệm có `size > 0`. Có thể làm:

~~~java
values[i] = values[size - 1];
size--;
~~~

Đây là mã minh họa, chưa phải một chương trình Java đầy đủ; `values` là mảng, `size` là số phần tử logic. Thao tác xóa theo chỉ số đã biết mất O(1), **nhưng thứ tự bị thay đổi**. Ví dụ xóa phần tử `20` ở `[10,20,30,40]` tạo dãy `[10,40,30]`. Nếu phải **tìm** phần tử theo giá trị trước khi xóa, việc tìm vẫn có thể O(n).

Không áp dụng kỹ thuật này khi thuật toán cần duy trì thứ tự xuất hiện, dữ liệu đã được sắp xếp, chỉ số của phần tử có ý nghĩa hoặc các cấu trúc khác còn tham chiếu tới vị trí cũ.

## 4. `ArrayList`: mảng động và phân tích khấu hao

`ArrayList<E>` chứa một dãy có thứ tự với các vị trí `0..size()-1` và tự quản lý bộ nhớ lưu trữ. Lưu ý **`size` khác `capacity`**:

- `size` là số phần tử người dùng thấy.
- `capacity` là số vị trí có thể chứa trước khi cần tăng dung lượng, được quản lý nội bộ; không nên dựa vào hệ số tăng dung lượng cụ thể của một phiên bản JDK.
- Khi `size < capacity`, thêm cuối chỉ cần ghi giá trị vào vị trí trống và tăng `size`, thường O(1).
- Khi hết dung lượng, phải tạo vùng lưu mới lớn hơn và sao chép các tham chiếu đang có, nên **lần thêm đó** mất O(n).

Tại sao vẫn gọi `add(E)` là **O(1) khấu hao**? Với chiến lược tăng sức chứa theo một hệ số lớn hơn 1 (mô hình mảng động hình học), số phần tử đã sao chép qua nhiều lần nới dung lượng tạo thành một cấp số nhân. Sau `m` lượt thêm cuối từ danh sách rỗng, tổng lượt sao chép là O(m); cộng với `m` lần ghi phần tử mới, tổng thời gian là O(m). Vì vậy trung bình theo **chuỗi thao tác** là O(1) cho mỗi lần thêm. Đây là phân tích khấu hao, **không phải khẳng định mỗi lần đều có giới hạn hằng số**.

Trong Java, `ArrayList` được tài liệu hóa là có thêm cuối với chi phí hằng số khấu hao; chính sách tăng dung lượng cụ thể là chi tiết triển khai, không nên viết thuật toán phụ thuộc vào tỷ lệ tăng chính xác đó.

### Chèn/xóa ở vị trí xác định

Với `ArrayList<Integer> list` có `n` phần tử:

- `list.get(i)` và `list.set(i, x)`: O(1) nếu `i` hợp lệ.
- `list.add(x)`: O(1) khấu hao.
- `list.add(i, x)`: phải dời `n-i` tham chiếu trong danh sách, nên O(n) ở trường hợp xấu.
- `list.remove(i)`: phải dời `n-i-1` tham chiếu, nên O(n) ở trường hợp xấu; riêng xóa cuối O(1).
- `list.remove(Integer.valueOf(x))`: tìm lần xuất hiện đầu tiên có thể O(n), sau đó còn dịch chuyển phần tử; tổng O(n).

**Cảnh báo về overload:** Với `ArrayList<Integer>`, `remove(1)` chọn phiên bản nhận `int index` để xóa **vị trí 1**, còn `remove(Integer.valueOf(1))` chọn phiên bản nhận đối tượng để xóa **giá trị 1**. Nhầm hai lời gọi này làm chương trình chạy sai dù cú pháp hợp lệ.

### Chi phí bộ nhớ và kiểu phần tử

`ArrayList<Integer>` lưu các **tham chiếu tới đối tượng `Integer`**, không phải dãy `int` primitive thuần như `int[]`. Đối với dữ liệu số lớn, boxing, đối tượng và tham chiếu có thể làm tăng lượng bộ nhớ, cấp phát và áp lực GC. Độ phức tạp của cả hai vẫn O(n), nhưng thực tế lưu hàng triệu số có thể khác biệt đáng kể.

Nếu dự đoán được số phần tử, có thể dùng `new ArrayList<>(expectedSize)` hoặc `ensureCapacity(expectedSize)` để giảm số lần phải nới vùng lưu khi thêm. Điều này **không** thay đổi chi phí O(n) của chèn/xóa đầu hoặc giữa.

## 5. `LinkedList`: liên kết nhanh khi đã biết nút, truy cập theo chỉ số chậm

`LinkedList<E>` trong Java là **danh sách liên kết đôi**. Về mặt mô hình, mỗi nút lưu giá trị cùng liên kết tới nút trước/sau; danh sách lưu tham chiếu đầu/cuối. Vì thế:

- `addFirst(x)`, `addLast(x)`, `removeFirst()` và `removeLast()` thay đổi một số hữu hạn liên kết: O(1) (với các điều kiện hợp lệ).
- `get(i)` cần duyệt các nút để đến chỉ số `i`: O(n) trong trường hợp xấu. Triển khai có thể đi từ đầu hoặc cuối tùy vị trí; điều này cải thiện số bước cho một số chỉ số nhưng không biến truy cập bất kỳ thành O(1).
- `add(i,x)`, `remove(i)` thường phải **tìm vị trí** trước, tổng O(n) trong trường hợp xấu.
- Khi đã có `ListIterator<E>` ở một vị trí, `add`/`remove` thông qua iterator có thể gắn/gỡ nút với chi phí O(1) cho bước thay đổi liên kết; việc đưa iterator đến vị trí đó có thể vẫn cần O(n).

Ví dụ cần xóa các phần tử thỏa một điều kiện khi **đang duyệt toàn bộ danh sách**. Việc duyệt bằng iterator qua `n` nút và gọi `iterator.remove()` trên các nút gặp được có tổng thời gian O(n) nếu việc kiểm tra mỗi phần tử O(1). Ngược lại, lặp `i` từ 0 đến `n-1` rồi gọi `linkedList.get(i)` mỗi lượt có thể tốn O(n²), vì nhiều lần phải đi lại dọc danh sách.

### Vì sao `LinkedList` không phải lúc nào cũng nhanh hơn?

Một nút liên kết cần thêm tham chiếu và thường là một đối tượng riêng; nhiều nút nằm ở các vị trí bộ nhớ khác nhau. Duyệt `LinkedList` có thể gặp chi phí truy cập bộ nhớ, đối tượng và GC cao hơn so với duyệt phần tử trong mảng động. Mảng và `ArrayList` có tính cục bộ dữ liệu tốt hơn trong nhiều tình huống, dù cùng có chi phí duyệt Θ(n) theo mô hình RAM.

Nếu cần **chèn/xóa thường xuyên ở hai đầu**, `LinkedList` là một lựa chọn. Nhưng khi bài toán chỉ cần **ngăn xếp hoặc hàng đợi**, `ArrayDeque<E>` thường là lựa chọn Java đáng cân nhắc hơn nhờ cấu trúc bộ đệm vòng, tránh tạo một nút liên kết riêng cho mỗi phần tử. `ArrayDeque` hỗ trợ thêm/xóa ở hai đầu với O(1) khấu hao, nhưng **không hỗ trợ `get(i)` theo chỉ số** như `List`.

## 6. Tổng chi phí của một chuỗi thao tác quan trọng hơn từng thao tác lẻ

Một bài toán thuật toán thường yêu cầu **hàng nghìn hoặc hàng triệu thao tác**, nên cần tính tổng chi phí trên cả chuỗi.

### Ví dụ A: xóa lần lượt `n` phần tử đầu

Nếu dùng `ArrayList` và thực hiện `remove(0)` cho đến khi rỗng, các lần xóa sẽ lần lượt dời khoảng:

`(n-1) + (n-2) + ... + 1 + 0 = n(n-1)/2`

tham chiếu. Tổng thời gian là **Θ(n²)** dù bản thân mỗi câu lệnh có vẻ ngắn. Với `LinkedList.removeFirst()` hoặc `ArrayDeque.removeFirst()`, từng lượt có chi phí O(1) (khấu hao với `ArrayDeque`), nên toàn chuỗi thường O(n).

### Ví dụ B: đọc `n` phần tử nhiều lần theo chỉ số

Nếu lặp `for (int i = 0; i < n; i++)` và dùng `arrayList.get(i)`, tổng thời gian Θ(n). Với `linkedList.get(i)`, tổng chi phí có thể Θ(n²) vì mỗi lượt có thể duyệt nhiều nút. Nếu đã cần `LinkedList` vì lý do khác, hãy duyệt bằng `for (E x : linkedList)` hoặc iterator để xử lý tuần tự trong Θ(n).

### Ví dụ C: tìm và xóa một giá trị bất kỳ

Dù một nút `LinkedList` có thể được gỡ nhanh, nếu chỉ biết giá trị `x` thì phải **tìm** nút chứa `x` trước. `LinkedList.remove(Object)` vẫn có thể O(n); `ArrayList.remove(Object)` cũng O(n). Lựa chọn cấu trúc cho nhiệm vụ **tìm theo khóa** cần xét thêm cơ chế đánh chỉ mục (chẳng hạn `HashMap` khi phù hợp) cùng chi phí duy trì nó sau các lần thêm/xóa.

### Ví dụ D: dữ liệu luôn được sắp xếp

Mảng hoặc `ArrayList` đã sắp xếp có thể tìm vị trí bằng tìm kiếm nhị phân O(log n), nhưng chèn vào đúng vị trí có thể vẫn phải dời O(n) phần tử. `LinkedList` không có truy cập ngẫu nhiên O(1), nên không được mặc nhiên áp dụng tìm kiếm nhị phân theo chỉ số rồi kết luận O(log n).

**Bài học:** khi có một chuỗi thao tác, hãy lập bảng tần suất: bao nhiêu lần truy cập theo chỉ số, bao nhiêu lần duyệt, bao nhiêu lần thêm cuối/đầu, bao nhiêu lần chèn/xóa giữa và bao nhiêu lần tìm theo giá trị. Chọn cấu trúc để giảm **tổng chi phí**, không dựa vào một thao tác nổi bật.

## 7. Ví dụ Java 17+ hoàn chỉnh và kết quả chính xác

Chương trình dưới đây minh họa cùng một kiểu thao tác cập nhật có thứ tự trên bộ đệm mảng và `ArrayList`, thay đổi liên kết qua `LinkedList` và sử dụng `ArrayDeque` làm hàng đợi. Mã dùng các API có sẵn trong Java 17.

Lưu thành tệp `ListTradeoffsDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class ListTradeoffsDemo {
    private static String activeValues(int[] data, int size) {
        return Arrays.toString(Arrays.copyOf(data, size));
    }

    public static void main(String[] args) {
        // Mảng có 6 ô vật lý, ban đầu 3 ô logic có giá trị.
        int[] buffer = new int[6];
        buffer[0] = 10;
        buffer[1] = 20;
        buffer[2] = 30;
        int size = 3;

        // Chèn 15 ở vị trí 1: dời hai phần tử sang phải.
        int insertAt = 1;
        System.arraycopy(buffer, insertAt,
                buffer, insertAt + 1, size - insertAt);
        buffer[insertAt] = 15;
        size++;
        System.out.println("Array insert: " + activeValues(buffer, size));

        // Xóa vị trí 2 (giá trị 20): dời một phần tử sang trái.
        int deleteAt = 2;
        System.arraycopy(buffer, deleteAt + 1,
                buffer, deleteAt, size - deleteAt - 1);
        size--;
        buffer[size] = 0; // Xóa giá trị cũ ở ô không còn thuộc dãy logic.
        System.out.println("Array delete: " + activeValues(buffer, size));

        ArrayList<Integer> dynamic = new ArrayList<>(List.of(10, 20, 30));
        dynamic.add(1, 15);
        dynamic.remove(2); // Xóa theo chỉ số, không phải theo giá trị.
        System.out.println(
                "ArrayList: " + dynamic + ", get(1)=" + dynamic.get(1));

        LinkedList<Integer> linked = new LinkedList<>(List.of(10, 20, 30));
        linked.addFirst(5);
        linked.addLast(40);

        // Tìm bằng iterator và xóa đúng nút vừa duyệt tới.
        ListIterator<Integer> cursor = linked.listIterator();
        while (cursor.hasNext()) {
            if (cursor.next() == 20) {
                cursor.remove();
                break;
            }
        }
        System.out.println("LinkedList: " + linked);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        queue.addLast(10);
        queue.addLast(20);
        System.out.println(
                "Queue pop: " + queue.removeFirst()
                        + ", next=" + queue.peekFirst());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ListTradeoffsDemo.java
java ListTradeoffsDemo
~~~

Kết quả chuẩn:

~~~text
Array insert: [10, 15, 20, 30]
Array delete: [10, 15, 30]
ArrayList: [10, 15, 30], get(1)=15
LinkedList: [5, 10, 30, 40]
Queue pop: 10, next=20
~~~

**Giải thích và chi phí:**

- Bộ đệm `int[6]` có sức chứa 6 nhưng chỉ có 3 phần tử logic ban đầu. Chèn tại `i=1` phải dời hai giá trị `20` và `30`; xóa tại `i=2` sau đó chỉ dời `30`. Việc dùng `Arrays.copyOf` trong hàm in để tạo mảng tạm là O(size), **không thuộc riêng chi phí chèn/xóa** đang minh họa.
- `dynamic.add(1,15)` chèn vào giữa và `dynamic.remove(2)` xóa phần tử ở vị trí 2. `dynamic.get(1)` truy cập theo chỉ số O(1).
- `linked.addFirst(5)` và `linked.addLast(40)` đều O(1). Vòng `while` của iterator tìm tới giá trị `20`; **bước tìm** cần duyệt các phần tử, còn `cursor.remove()` khi đã đứng ở nút cần xóa là O(1).
- `queue.addLast` và `queue.removeFirst` mô phỏng hàng đợi FIFO. Cả `LinkedList` và `ArrayDeque` đều có thể dùng cho thao tác hai đầu, nhưng `ArrayDeque` là lựa chọn mặc định thực dụng khi không cần đặc tính riêng của `LinkedList`.

Thời gian in ra màn hình và việc dựng chuỗi biểu diễn danh sách phụ thuộc số phần tử cần in. Khi đánh giá thuật toán cho dữ liệu rất lớn, hãy tách phần **xử lý dữ liệu** ra khỏi việc in toàn bộ kết quả.

## 8. Lựa chọn cấu trúc theo mẫu thao tác

| Nhu cầu chính | Cấu trúc thường hợp lý | Vì sao |
|---|---|---|
| Kích thước cố định, nhiều phép toán số học theo chỉ số | `int[]`, `long[]` hoặc mảng primitive tương ứng | Truy cập O(1), ít overhead đối tượng so với collection có boxing |
| Kích thước thay đổi, đọc theo chỉ số và thêm cuối thường xuyên | `ArrayList<E>` | `get` O(1), thêm cuối O(1) khấu hao, duyệt thuận tiện |
| Cần một danh sách có thứ tự, thường xuyên thêm/xóa ở hai đầu | `ArrayDeque<E>` nếu không cần API `List`; `LinkedList<E>` khi cần chức năng danh sách liên kết | Hai đầu nhanh, tránh dời toàn bộ phần tử |
| Đang duyệt và cần xóa các phần tử thỏa điều kiện | `Iterator.remove()` đúng hợp đồng hoặc `removeIf` | Tránh sửa cấu trúc trực tiếp trong vòng `for-each` |
| Có một vị trí liên kết được giữ qua iterator, thường xuyên chèn/xóa lân cận | `LinkedList<E>` có thể có lợi | Chỉnh liên kết nhanh **sau khi đã có vị trí** |
| Truy cập ngẫu nhiên rất nhiều lần | Mảng hoặc `ArrayList` | Tránh phải duyệt tới vị trí như `LinkedList` |
| Chèn/xóa giữa thường xuyên nhưng đồng thời phải tìm vị trí theo chỉ số | Không mặc định chọn `LinkedList` | Chi phí tìm vị trí O(n) thường xóa lợi thế cập nhật liên kết |
| Hàng đợi cho BFS, ngăn xếp cho DFS dạng lặp | `ArrayDeque<E>` | `addLast/removeFirst` hoặc `addLast/removeLast` phù hợp |
| Luôn cần giữ dữ liệu có thứ tự sắp xếp sau nhiều lần cập nhật | Cân nhắc cấu trúc cây, heap hay chỉ mục phù hợp với thao tác | Dãy đã sắp xếp tìm nhanh nhưng chèn/xóa vẫn có thể O(n) |

**Ví dụ thuật toán BFS:** hàng đợi thực hiện thêm cuối và lấy đầu rất thường xuyên. Nếu dùng `ArrayList.remove(0)` để lấy đầu, số lần dời phần tử có thể tích lũy thành Θ(n²). Dùng `ArrayDeque` với `addLast`/`removeFirst` giữ tổng chi phí thao tác hàng đợi O(n) khấu hao cho O(n) lượt thêm/xóa, bỏ qua chi phí riêng của việc thăm láng giềng trong đồ thị.

## 9. Phân biệt hành vi của các API Java trông giống danh sách

**`List.of(...)`** tạo danh sách **không cho phép cập nhật**; gọi `add`, `remove` hoặc `set` sẽ ném `UnsupportedOperationException`. Không dùng nó khi bài toán yêu cầu thêm/xóa phần tử; có thể chuyển thành `new ArrayList<>(List.of(...))` hoặc `new LinkedList<>(List.of(...))`.

**`Arrays.asList(...)`** trả về một danh sách có kích thước cố định, thường được **backed bởi mảng ban đầu**: `set` có thể thay đổi giá trị phần tử tương ứng, nhưng `add`/`remove` làm thay đổi kích thước nên không được hỗ trợ. Cẩn thận với `Arrays.asList(intArray)`: nếu `intArray` là `int[]`, kết quả là một danh sách **chứa đúng một phần tử kiểu `int[]`**, không phải `List<Integer>` các số của mảng.

**`subList(from,to)`** là một **view** trên phần của danh sách cha, theo hợp đồng của `List`; thao tác hợp lệ trên view có thể ảnh hưởng danh sách gốc. Thay đổi cấu trúc danh sách cha ngoài view khi view còn được dùng có thể dẫn đến hành vi không được đặc tả cho view. Nếu muốn có danh sách độc lập, có thể dùng `new ArrayList<>(list.subList(from,to))`, chấp nhận chi phí sao chép theo kích thước đoạn.

**Sửa danh sách khi duyệt:** không gọi `list.remove(...)` trực tiếp trong vòng `for-each` rồi mặc nhiên mong vòng lặp tiếp tục đúng. Với các danh sách fail-fast phổ biến, sửa cấu trúc ngoài iterator có thể gây `ConcurrentModificationException`; đây là cơ chế phát hiện lỗi theo nỗ lực tốt nhất, không phải công cụ đảm bảo đồng bộ luồng. Dùng `Iterator.remove()`, `removeIf` hoặc thiết kế vòng lặp chỉ số phù hợp với việc dịch chuyển phần tử.

**Giới hạn chỉ số và rỗng:** chỉ số đọc/xóa hợp lệ là `0 ≤ i < size`, còn vị trí chèn bằng `add(i,x)` hợp lệ là `0 ≤ i ≤ size`. `LinkedList.removeFirst()` và `ArrayDeque.removeFirst()` ném `NoSuchElementException` nếu rỗng; các phương thức `pollFirst()` trả `null` khi rỗng theo hợp đồng deque, nhưng `ArrayDeque` không cho phép chứa phần tử `null`. Chọn API phù hợp với cách báo trường hợp không có phần tử.

## 10. Đánh đổi về bộ nhớ, độ cục bộ dữ liệu và hệ số thực tế

Ký hiệu O(n) chỉ nói tốc độ tăng, chưa cho biết **lượng byte**, số đối tượng hay khả năng dùng cache:

- Mảng `int[n]` chứa khoảng `4n` byte dữ liệu số nguyên, ngoài header và căn chỉnh phụ thuộc JVM. Mảng `long[n]` chứa khoảng `8n` byte phần tử. Mảng `String[]` chứa các **tham chiếu**; bản thân nội dung chuỗi nằm trong các đối tượng khác.
- `ArrayList<Integer>` chứa mảng tham chiếu `Integer`, không phải `int[]`. Nhiều giá trị có thể cần đối tượng `Integer` và bộ nhớ liên quan; `ArrayList` còn có thể dự trữ dung lượng lớn hơn `size`.
- `LinkedList<Integer>` thường cần một nút riêng với liên kết trước, sau và giá trị tham chiếu cho mỗi phần tử. Duyệt nhiều nút có thể kém hiệu quả cache và tạo áp lực GC dù về lý thuyết vẫn là Θ(n).
- Chèn/xóa giữa mảng phải sao chép nhiều phần tử, nhưng quá trình sao chép bộ nhớ liên tiếp có thể được tối ưu tốt. Vì thế không nên suy ra `LinkedList` chắc chắn nhanh hơn `ArrayList` chỉ từ một bảng Big-O.
- `ArrayDeque` dùng bộ đệm vòng và có thể mở rộng. Nó tránh phải dời toàn bộ phần tử khi lấy đầu, thường tiết kiệm overhead liên kết nút, nhưng không đáp ứng các thao tác truy cập theo chỉ số của `List`.

Nếu bài toán có `n` rất lớn hoặc giới hạn bộ nhớ chặt, cần ước tính cả mảng backing, đối tượng phần tử, nút liên kết, GC, dữ liệu tạm và ngăn xếp gọi hàm. Khi lựa chọn cuối cùng phụ thuộc hiệu năng thực tế, hãy kiểm thử trên dữ liệu gần giới hạn trong môi trường chạy đại diện. Không coi số đo một lần trên JVM là bằng chứng đủ về bản chất thuật toán.

## 11. Lỗi thường gặp, kiểm thử biên và cách tự rà soát

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Nhầm `size` logic với `array.length` | Duyệt cả ô chưa dùng hoặc ghi vượt sức chứa | Duy trì bất biến `0 ≤ size ≤ capacity` và dùng đúng `size` |
| Chèn bằng cách dời từ trái sang phải | Ghi đè phần tử nguồn trước khi sao chép | Khi tự viết vòng lặp chèn, dời **từ phải sang trái** hoặc dùng `System.arraycopy` |
| Xóa giữ thứ tự nhưng quên dời phần tử | Dữ liệu bị lệch hoặc xuất hiện bản sao không mong muốn | Dời `n-i-1` phần tử sang trái rồi giảm `size` |
| Gọi `remove(1)` nhằm xóa giá trị 1 trong `List<Integer>` | Xóa phần tử tại chỉ số 1 | Dùng `remove(Integer.valueOf(1))` nếu cần xóa theo giá trị |
| Cho rằng `LinkedList.add(i,x)` luôn O(1) | Bỏ qua chi phí tìm nút ở chỉ số `i` | Tách việc **tìm vị trí** và **sửa liên kết** |
| Dùng `LinkedList.get(i)` trong vòng lặp chỉ số | Nhiều lần duyệt lại nút, có thể O(n²) | Dùng iterator/for-each để duyệt tuần tự |
| Dùng `ArrayList.remove(0)` như hàng đợi | Có thể dời tổng Θ(n²) phần tử | Dùng `ArrayDeque` hoặc cấu trúc hàng đợi phù hợp |
| Chọn `List.of`/`Arrays.asList` rồi gọi thêm/xóa | `UnsupportedOperationException` | Hiểu rõ mutable/fixed-size/unmodifiable trước khi chọn |
| Chọn cấu trúc theo Big-O duy nhất | Tốn RAM, cấp phát, GC hoặc cache miss không dự đoán | Xét cả mẫu thao tác, kiểu phần tử và hạn mức |

**Các trường hợp biên nên tự kiểm thử:**

1. Mảng/danh sách rỗng (`size=0`): thêm vị trí 0 được với danh sách có khả năng thay đổi; đọc/xóa ở 0 không hợp lệ.
2. Danh sách một phần tử: xóa đầu và xóa cuối đều dẫn đến rỗng; tránh truy cập phần tử sau khi đã xóa.
3. Thêm ở `i=0` và `i=n`; xóa ở `i=0` và `i=n-1`; xác minh đúng số phần tử bị dời.
4. Chèn khi mảng vừa đủ sức chứa: phải tăng dung lượng hoặc báo đầy theo hợp đồng; không được ghi ngoài `length`.
5. Xóa các giá trị trùng nhau: xóa theo giá trị thường xóa một lần xuất hiện; xóa theo chỉ số chỉ xóa vị trí được chỉ định.
6. Duyệt và xóa nhiều phần tử liền nhau: tránh bỏ sót phần tử do các chỉ số đã dời.
7. Bài có nhiều thao tác: kiểm thử tổng chi phí gần giới hạn, chẳng hạn nhiều lần thêm/xóa đầu, xen kẽ truy cập và cập nhật.

**Checklist khi chọn cấu trúc:** Dữ liệu có cần giữ thứ tự không? Số phần tử có biết trước không? Truy cập theo chỉ số hay duyệt tuần tự là chính? Thêm/xóa xảy ra ở đầu, cuối hay giữa? “Biết vị trí” là có sẵn chỉ số, iterator hay chỉ biết giá trị? Có cần giữ nhiều phần tử kiểu primitive và hạn chế bộ nhớ không? Chi phí của **cả chuỗi thao tác** có chịu được biên `n` tối đa không?

Một cấu trúc được xem là phù hợp khi nó bảo đảm đúng yêu cầu về thứ tự và truy cập, đồng thời giảm chi phí **các thao tác thực sự xuất hiện trong thuật toán**.