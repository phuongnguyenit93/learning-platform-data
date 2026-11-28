# So sánh mảng động với mảng cố định và danh sách liên kết

**Mảng cố định** (*fixed-size array*), **mảng động** (*dynamic array*) và **danh sách liên kết** (*linked list*) đều có thể dùng để lưu một dãy phần tử theo thứ tự. Tuy nhiên, chúng khác nhau về cách tổ chức bộ nhớ, khả năng thay đổi số phần tử, chi phí truy cập theo chỉ số và chi phí chèn/xóa. Chọn sai cấu trúc có thể khiến thao tác quan trọng nhất của chương trình trở nên chậm hoặc tiêu tốn bộ nhớ không cần thiết.

Ví dụ, một bảng dữ liệu có số cột không đổi, một danh sách kết quả được thêm dần và một hàng chờ cần thêm/xóa ở hai đầu có những kiểu thao tác khác nhau. Không thể chỉ nhìn vào tên “danh sách” hoặc “mảng” để chọn cấu trúc. Cần xem **công việc chủ yếu** là truy cập ngẫu nhiên, duyệt tuần tự, thêm cuối, chèn giữa, xóa đầu hay duy trì tham chiếu đến phần tử.

Trong bài này, ta so sánh ba cấu trúc trên cùng một mô hình và cùng các phép toán, đồng thời chỉ rõ những giả định ảnh hưởng đến ký hiệu độ phức tạp O(1), O(n) và O(1) khấu hao.

## 1. Ba cách biểu diễn một dãy phần tử

Giả sử dãy logic đang chứa `[10, 20, 30]`.

### Mảng cố định: vùng liên tiếp có độ dài không đổi

```text
int[] data = new int[5]

Chỉ số:     0     1     2     3     4
          +-----+-----+-----+-----+-----+
data:     | 10  | 20  | 30  |  0  |  0  |
          +-----+-----+-----+-----+-----+
          <----- 5 ô cố định ------------>
```

Mảng cố định có **độ dài vùng lưu trữ được quyết định khi tạo**. Trong Java, `int[]` có thuộc tính `length` và không thể thay độ dài của chính đối tượng mảng đó. Các giá trị ở từng ô có thể được thay đổi, nhưng muốn có một mảng dài hơn phải tạo **mảng khác**.

Nếu ứng dụng muốn dùng chỉ ba ô đầu làm phần tử logic và giữ hai ô dự trữ, nó phải **tự quản lý biến `size = 3`**. Đó là một cách sử dụng mảng cố định làm bộ đệm, không có nghĩa mảng nền tự biến thành mảng động.

### Mảng động: bộ đệm liên tiếp có thể được thay thế

```text
DynamicArray
    size = 3
    capacity = 5
    buffer ─────────────► [10][20][30][?][?]
                         < sử dụng ><dự trữ>
```

Mảng động có **kích thước logic (`size`)** khác với **dung lượng của bộ đệm (`capacity`)**. Khi còn chỗ, thêm phần tử mới chỉ cần ghi vào ô kế tiếp. Khi đầy, nó cấp phát một bộ đệm lớn hơn, chuyển dữ liệu cũ và thay bộ đệm.

Vì thế, mảng động có thể thay đổi số phần tử mà không yêu cầu người sử dụng tự tạo mảng mới ở mỗi lần thêm. Tuy nhiên, bộ đệm bên dưới **vẫn là một vùng cố định tại từng thời điểm** và việc mở rộng có thể phải sao chép nhiều phần tử.

### Danh sách liên kết: các nút nối bằng liên kết

```text
head
  |
  v
[10 | next] ──► [20 | next] ──► [30 | null]

Mỗi nút lưu dữ liệu và thông tin dẫn tới nút tiếp theo.
Các nút không cần nằm kề nhau trong bộ nhớ.
```

Trong **danh sách liên kết đơn** (*singly linked list*), mỗi nút lưu một liên kết đến nút kế tiếp. **Danh sách liên kết đôi** (*doubly linked list*) còn có liên kết về nút trước, hỗ trợ một số thao tác xóa/chèn thuận tiện hơn khi đã biết nút.

Danh sách liên kết thường không cần sao chép toàn bộ dãy chỉ để thêm một nút; nhưng để đến phần tử tại chỉ số `i`, nó thường phải **đi theo liên kết từ đầu hoặc cuối**, thay vì tính vị trí bộ nhớ trực tiếp.

## 2. Bảng tổng quan về cấu trúc lưu trữ

| Tiêu chí | Mảng cố định | Mảng động | Danh sách liên kết |
| --- | --- | --- | --- |
| Tổ chức dữ liệu | Các ô liên tiếp | Các ô liên tiếp trong bộ đệm hiện tại | Các nút nối bằng liên kết, không cần liên tiếp |
| Độ dài vùng lưu trữ | Không đổi sau khi tạo mảng | Có thể thay bằng vùng lớn hơn/nhỏ hơn | Tăng/giảm bằng cách tạo/hủy nút |
| Số phần tử logic | Thường bằng độ dài mảng; có thể quản lý riêng | `size` được quản lý riêng với `capacity` | Số nút đang thuộc danh sách |
| Dung lượng dự trữ | Phụ thuộc kích thước mảng đã cấp phát | Thường có ô dư để giảm số lần cấp phát lại | Thường không có vùng ô liên tiếp dự trữ |
| Truy cập trực tiếp theo chỉ số | Có | Có | Không |
| Chi phí quản lý cấu trúc | Thấp | Thêm metadata và có thể có vùng dư | Liên kết/nút và thường nhiều lần cấp phát |
| Ảnh hưởng của cấp phát lại | Muốn dài hơn phải tạo mảng khác | Có thể chuyển toàn bộ phần tử cũ | Thêm nút thường không cần chuyển các nút cũ |

**Đừng nhầm số phần tử với sức chứa.** Mảng động có bất biến `0 <= size <= capacity`; còn `int[]` của Java đơn giản có `length` cố định. Danh sách liên kết có số nút hiện có nhưng không phải một `capacity` của vùng lưu trữ liên tiếp như mảng động.

## 3. So sánh độ phức tạp của các thao tác

Giả sử `n` là số phần tử logic hiện có. Bảng dưới đây phân tích **dãy có thứ tự**; chèn/xóa phải giữ thứ tự tương đối của những phần tử còn lại.

| Thao tác | Mảng cố định | Mảng động | Danh sách liên kết |
| --- | --- | --- | --- |
| Đọc/ghi phần tử tại chỉ số `i` hợp lệ | O(1) | O(1) | O(n) để tìm nút |
| Duyệt toàn bộ `n` phần tử | O(n) | O(n) | O(n) |
| Thêm vào cuối | O(1) nếu tự quản lý `size` và còn ô trống; **không thể tăng độ dài mảng gốc** khi đầy | O(1) khấu hao với chính sách tăng dung lượng hình học; có lần O(n) | O(1) nếu giữ con trỏ `tail`; nếu không có thể cần O(n) để tới cuối |
| Chèn vào đầu và giữ thứ tự | O(n) nếu còn chỗ; nếu đầy phải tạo mảng mới | O(n) để dịch phần tử | O(1) khi có `head` |
| Chèn tại chỉ số `i` | O(n) để dịch hoặc tạo mảng thay thế | O(n) do dịch phần đuôi | O(n) để tìm vị trí, rồi O(1) để nối nút nếu có liên kết cần thiết |
| Xóa đầu và giữ thứ tự | O(n) nếu dồn trái | O(n) | O(1) khi có `head` |
| Xóa ở chỉ số `i` | O(n) để dồn phần tử phía sau | O(n) trong trường hợp xấu | O(n) để tìm nút; O(1) để tháo nút khi đã có vị trí và liên kết thích hợp |
| Xóa cuối | O(1) nếu quản lý `size` riêng và chỉ bỏ phần tử logic cuối | O(1) nếu không thu nhỏ; có thể O(1) khấu hao với quy tắc co phù hợp | O(1) với danh sách liên kết đôi có `tail`; với liên kết đơn thường O(n) để tìm nút trước cuối |

**Các điều kiện trong bảng rất quan trọng:**

1. Mảng cố định `int[]` **không có thao tác tăng `length`**. Các nhận xét về thêm/xóa trên mảng cố định giả định ứng dụng quản lý riêng số phần tử đang dùng trong một bộ đệm đã cấp phát. Nếu muốn vượt độ dài vật lý, phải tạo một mảng khác và chuyển dữ liệu.
2. O(1) **khấu hao** của thêm cuối mảng động dựa trên việc tăng `capacity` theo hệ số cố định lớn hơn 1 (ví dụ nhân đôi). Một lần riêng lẻ khi đầy vẫn có thể tốn O(n).
3. Thêm cuối danh sách liên kết O(1) giả định có `tail`; xóa cuối O(1) cần điều kiện mạnh hơn, chẳng hạn danh sách **liên kết đôi** có `tail`.
4. Chèn/xóa tại “vị trí đã biết” trong danh sách liên kết có thể O(1), nhưng **tìm** nút ở chỉ số `i` không tự nhiên là O(1). Với danh sách đơn, xóa nút thông thường còn cần nút đứng trước.
5. Nếu không cần giữ thứ tự, một mảng động có thể xóa bằng cách thay phần tử cần xóa bằng phần tử cuối rồi giảm `size`, đạt O(1). Đó là một **hợp đồng thao tác khác** với xóa bảo toàn thứ tự trong bảng.

## 4. Vì sao mảng truy cập chỉ số O(1) còn danh sách liên kết O(n)?

Với mảng có các ô kích thước cố định, vị trí của phần tử `i` có thể được tính từ địa chỉ đầu và độ rộng ô:

\[
\operatorname{address}(i)=\operatorname{base}+i\times\operatorname{slotSize}.
\]

Đó là cơ sở cho truy cập ngẫu nhiên (*random access*) O(1), sau khi kiểm tra chỉ số hợp lệ.

Ngược lại, với danh sách liên kết đơn:

```text
get(3):

head
  |
  v
[A] -> [B] -> [C] -> [D] -> [E] -> null
  0      1      2      3

Đi theo next ba lần mới đến nút chỉ số 3.
```

Để truy cập `get(i)`, danh sách thường phải đi qua O(i) liên kết nếu bắt đầu từ đầu. Danh sách liên kết đôi có thể chọn đi từ đầu hoặc cuối gần hơn, nhưng trong trường hợp xấu nhất việc tìm vị trí vẫn là O(n).

**Ví dụ:** nếu thuật toán liên tục đọc `a[0], a[1], ..., a[n - 1]` trên `std::vector` hoặc mảng động, mỗi truy cập theo chỉ số là O(1), tổng là O(n). Nhưng trên Java `LinkedList`, đoạn mã sau có thể tốn O(n²):

```java
for (int i = 0; i < linked.size(); i++) {
    consume(linked.get(i)); // Moi lan get(i) co the di qua nhieu nut.
}
```

Nếu cần duyệt một danh sách liên kết, dùng **iterator** hoặc vòng lặp `for-each` để đi qua các nút liên tiếp, tổng thời gian O(n):

```java
for (Integer value : linked) {
    consume(value);
}
```

Ở đây `consume` là thao tác xử lý một phần tử giả định có thời gian O(1); không phải phương thức có sẵn của `LinkedList`.

## 5. Chèn và xóa: dịch phần tử so với đổi liên kết

### Mảng động phải bảo toàn vùng dữ liệu liên tiếp

Giả sử dãy chứa `[A, B, C, D]` và muốn chèn `X` ở chỉ số 1:

```text
Trước: [A][B][C][D][ ]

Dịch phần đuôi từ phải sang trái:
       [A][B][C][D][D]
       [A][B][C][C][D]
       [A][B][B][C][D]

Ghi X: [A][X][B][C][D]
```

Ta phải dịch `D, C, B`, tức `n - i` phần tử khi chèn vào vị trí `i`. Nếu bộ đệm không còn chỗ, còn phải cấp phát lại và sao chép toàn bộ phần đang dùng trước khi chèn.

Xóa `B` khỏi `[A, B, C, D]` lại phải dồn `C, D` sang trái; số ô dịch là `n - i - 1`. Chỉ giảm `size` mà không dồn sẽ không bảo toàn một dãy liên tục đúng thứ tự.

### Danh sách liên kết đổi các liên kết của nút

Trong danh sách liên kết đơn, nếu đã có **nút đứng trước vị trí cần chèn**:

```text
Trước:
[A] ──► [B] ──► [C] ──► [D]

Chèn X sau A:
1. X.next = B
2. A.next = X

Sau:
[A] ──► [X] ──► [B] ──► [C] ──► [D]
```

Các nút `B, C, D` không cần bị di chuyển. Tương tự, nếu biết `A` và muốn bỏ nút `B` khỏi danh sách liên kết đơn:

```text
A.next = B.next

[A] ──► [C] ──► [D]
```

Thao tác đổi liên kết có thể O(1), **nhưng nếu chỉ biết “chèn tại chỉ số 10.000”**, chương trình thường phải tìm đến vị trí đó trước, mất O(n). Với liên kết đôi và đã có nút mục tiêu, chèn/xóa cục bộ có thể thay đổi một số lượng liên kết hằng số.

Vì vậy, lợi thế của danh sách liên kết thể hiện rõ nhất khi ứng dụng **đã giữ nút hoặc iterator thích hợp**, thường xuyên chèn/xóa gần nút đó và không cần truy cập theo chỉ số.

## 6. Bộ nhớ: các ô dư đối đầu với chi phí nút

Cả ba cấu trúc cần lưu dữ liệu, nhưng phần bộ nhớ **ngoài dữ liệu** khác nhau:

| Cấu trúc | Bộ nhớ chủ yếu | Phần dư/chi phí quản lý |
| --- | --- | --- |
| Mảng cố định | `N` ô được cấp phát từ đầu | Nếu chỉ dùng `n < N` ô thì `N - n` ô dự trữ; kích thước vật lý vẫn là `N` |
| Mảng động | `capacity` ô trong bộ đệm | `capacity - size` ô dư và metadata; có thể tạm giữ cả bộ đệm cũ lẫn mới lúc mở rộng |
| Danh sách liên kết | `n` nút | Mỗi nút có liên kết, thông tin quản lý và có thể chịu chi phí cấp phát/căn chỉnh riêng |

Với dữ liệu kiểu nguyên thủy và cách triển khai lưu trực tiếp, mảng thường có lợi về bộ nhớ vì không cần đối tượng nút cho mỗi phần tử. Một danh sách liên kết đôi thường cần ít nhất hai liên kết (`prev`, `next`) cho mỗi nút, ngoài dữ liệu và chi phí đối tượng/nút.

Không thể lấy một con số “byte mỗi phần tử” đúng cho mọi ngôn ngữ: nó phụ thuộc kiến trúc, trình biên dịch, runtime, kiểu dữ liệu, đối tượng bao bọc và bộ cấp phát.

**Lưu ý đặc biệt trong Java:** `int[]` lưu số nguyên nguyên thủy trực tiếp; `ArrayList<Integer>` và `LinkedList<Integer>` lưu các tham chiếu đến `Integer`, vì generic collection không lưu trực tiếp `int`. So sánh mức dùng RAM của ba ví dụ Java cần xét thêm chi phí đối tượng `Integer` hoặc hành vi cache/boxing, không chỉ riêng cấu trúc mảng hay nút.

### Tính cục bộ bộ nhớ và CPU cache

Mảng cố định và mảng động lưu các ô **liên tiếp**, thường giúp việc duyệt tuần tự tận dụng bộ nhớ đệm CPU (*cache locality*) và cơ chế nạp trước dữ liệu (*prefetch*). Danh sách liên kết có thể đặt các nút rải rác, nên quá trình đi theo liên kết có thể khiến CPU phải truy cập nhiều vùng nhớ.

Hai thuật toán đều có thể cùng O(n) nhưng thời gian thực tế chênh lệch đáng kể vì đặc điểm bộ nhớ. Ký hiệu Big-O mô tả tốc độ tăng theo đầu vào, **không phản ánh hết hằng số chi phí**, tác động cache hay chi phí cấp phát.

## 7. Tính ổn định của địa chỉ, tham chiếu và bộ duyệt

Một yếu tố dễ bị bỏ qua là điều gì xảy ra với **cách truy cập đã giữ trước đó** khi cấu trúc thay đổi.

- **Mảng cố định:** bản thân vùng lưu trữ không tự thay chỗ khi thêm/xóa logic trong vùng đã cấp phát. Tuy nhiên, nếu ứng dụng tạo mảng mới và thay biến giữ mảng cũ, tham chiếu đến **mảng cũ** vẫn là tham chiếu đến đối tượng mảng cũ, không tự trỏ tới mảng mới.
- **Mảng động:** cấp phát lại có thể thay bộ đệm. Với C++ `std::vector`, các con trỏ, tham chiếu và iterator trỏ vào phần tử trong vùng cũ sẽ mất hiệu lực khi cấp phát lại. Chèn/xóa cũng có quy tắc mất hiệu lực ngay cả khi không cấp phát lại.
- **Danh sách liên kết:** nhiều triển khai dựa trên nút có thể giữ ổn định vị trí của **các nút không bị xóa** khi chèn/xóa nút khác. Chẳng hạn, `std::list` trong C++ thường giữ iterator/tham chiếu đến phần tử không bị xóa qua các thao tác chèn/xóa; iterator trỏ tới chính phần tử bị xóa vẫn mất hiệu lực.

Với Java, các biến tham chiếu đến **đối tượng** trong `ArrayList` không phải con trỏ trực tiếp vào ô lưu trữ bên trong; việc thay mảng tham chiếu nội bộ không tự làm đối tượng bị di chuyển hay biến tham chiếu đến đối tượng mất hiệu lực. Tuy nhiên, iterator của `ArrayList` và `LinkedList` có quy tắc phát hiện sửa đổi cấu trúc riêng, không nên dùng để tiếp tục duyệt sau những thay đổi trái hợp đồng iterator.

Khi ứng dụng cần lưu “vị trí phần tử được chọn” lâu dài qua các lần thêm/xóa, hãy kiểm tra rõ **độ ổn định của chỉ số, iterator, con trỏ hoặc định danh** của cấu trúc đang dùng.

## 8. Ví dụ Java: nhìn thấy sự khác biệt qua cùng một tác vụ

Đoạn mã sau mô phỏng cùng ý tưởng: lưu các công việc `10, 20, 30`, thêm `40`, chèn `15` ở đầu đoạn giữa, rồi xóa phần tử tại vị trí 2.

Mảng cố định trong ví dụ có năm ô và **tự quản lý `size`**; mảng động dùng `ArrayList`; danh sách liên kết dùng `LinkedList`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;

public class SequenceStructureComparison {
    public static void main(String[] args) {
        // 1) Mang co dinh: tu quan ly so phan tu dang dung.
        int[] fixed = new int[5];
        int fixedSize = 0;
        fixed[fixedSize++] = 10;
        fixed[fixedSize++] = 20;
        fixed[fixedSize++] = 30;
        fixed[fixedSize++] = 40;

        // Chen 15 tai index 1; phai dich sang phai.
        int insertionIndex = 1;
        if (fixedSize >= fixed.length) {
            throw new IllegalStateException("Fixed array is full");
        }
        System.arraycopy(
            fixed, insertionIndex, fixed, insertionIndex + 1,
            fixedSize - insertionIndex
        );
        fixed[insertionIndex] = 15;
        fixedSize++;

        // Xoa tai index 2; don sang trai.
        int removalIndex = 2;
        System.arraycopy(
            fixed, removalIndex + 1, fixed, removalIndex,
            fixedSize - removalIndex - 1
        );
        fixedSize--;
        fixed[fixedSize] = 0; // Don o logic cu trong vi du int[].

        System.out.println(
            "Fixed: " + Arrays.toString(Arrays.copyOf(fixed, fixedSize))
        );

        // 2) Mang dong: API tu quan ly buffer/size/capacity.
        ArrayList<Integer> dynamic = new ArrayList<>();
        dynamic.add(10);
        dynamic.add(20);
        dynamic.add(30);
        dynamic.add(40);
        dynamic.add(1, 15);
        dynamic.remove(2); // remove(int index), xoa gia tri o chi so 2
        System.out.println("Dynamic: " + dynamic);

        // 3) Danh sach lien ket: API giong, bieu dien bang nut.
        LinkedList<Integer> linked = new LinkedList<>();
        linked.add(10);
        linked.add(20);
        linked.add(30);
        linked.add(40);
        linked.add(1, 15);   // Can tim den vi tri de chen.
        linked.remove(2);    // Can tim den vi tri de xoa.
        System.out.println("Linked: " + linked);
    }
}
```

Kết quả của cả ba cách:

```text
Fixed: [10, 15, 30, 40]
Dynamic: [10, 15, 30, 40]
Linked: [10, 15, 30, 40]
```

Đầu ra giống nhau **không có nghĩa chi phí giống nhau**:

- Với mảng cố định, lập trình viên tự kiểm tra dung lượng, dịch các phần tử, tăng/giảm `fixedSize` và quyết định cách xử lý khi đầy.
- Với `ArrayList`, các thao tác `add(index, value)` và `remove(index)` ẩn việc dịch chuyển bộ đệm bên trong.
- Với `LinkedList`, chèn/xóa theo **chỉ số** vẫn cần tìm vị trí. Nếu đã có `ListIterator` ở đúng vị trí, thao tác chèn/xóa cục bộ có thể không cần duyệt lại từ đầu.

Trong Java, `LinkedList` thực tế là danh sách liên kết đôi và có thể dùng như `Deque` với `addFirst`, `addLast`, `removeFirst`, `removeLast`. Các thao tác này có chi phí O(1) về mặt cấu trúc, với điều kiện không tính riêng chi phí cấp phát/GC bất thường.

## 9. Lựa chọn cấu trúc theo kiểu công việc

Thay vì hỏi “cấu trúc nào nhanh nhất?”, hãy liệt kê những thao tác thường xảy ra và xem chi phí của **toàn bộ quy trình**.

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Bảng dữ liệu có số ô đã biết và không cần thay độ dài | Mảng cố định | Kích thước rõ ràng, ít metadata, truy cập chỉ số O(1) |
| Lưu dữ liệu chưa biết trước số phần tử, chủ yếu thêm cuối rồi duyệt | Mảng động | Mở rộng linh hoạt, thêm cuối O(1) khấu hao, duyệt tuần tự có lợi về locality |
| Truy cập `get(i)` rất thường xuyên | Mảng cố định hoặc mảng động | Truy cập theo chỉ số O(1) |
| Thêm/xóa gần đầu liên tục | Danh sách liên kết hoặc deque | Tránh phải dịch nhiều phần tử của mảng; deque dựa trên mảng vòng cũng có thể phù hợp |
| Chèn/xóa tại nút đã được giữ trước đó | Danh sách liên kết | Đổi liên kết cục bộ có thể O(1) |
| Chèn/xóa tại chỉ số ngẫu nhiên nhưng phải tìm vị trí mỗi lần | Cần đo và xem kỹ workload | Danh sách liên kết phải tìm O(n); mảng động phải dịch O(n), locality có thể khiến mảng lợi thế |
| Bộ nhớ hạn chế, số phần tử đã biết và gần như không đổi | Mảng cố định hoặc mảng động được đặt trước đúng mức | Giảm chỗ dự trữ không cần thiết, tránh overhead nút |
| Cần giữ ổn định iterator đến các phần tử không bị xóa | Cân nhắc danh sách liên kết có hợp đồng ổn định phù hợp | Mảng động có thể làm iterator mất hiệu lực khi cấp phát lại |

### Trường hợp hàng chờ: đừng chỉ chọn giữa `ArrayList` và `LinkedList`

Nếu bài toán chỉ cần thêm cuối và lấy đầu theo FIFO, gọi `ArrayList.remove(0)` lặp lại có thể gây dịch chuyển O(n) mỗi lần. `LinkedList` có thể xử lý hai đầu O(1), nhưng **`ArrayDeque` của Java** là một lựa chọn đáng xét: nó sử dụng cấu trúc dựa trên mảng vòng để tránh dồn toàn bộ phần tử khi bỏ đầu.

Đây là ví dụ cho thấy lựa chọn cấu trúc phải gắn với **loại thao tác**: mảng vòng có thể khai thác ưu điểm lưu trữ theo khối và thao tác hai đầu hiệu quả; không phải mọi hàng chờ đều nên dùng danh sách liên kết.

### Trường hợp chỉ cần duyệt sau khi xây dựng

Nếu chương trình đọc `n` giá trị, sau đó thực hiện nhiều lần duyệt hoặc truy cập theo chỉ số nhưng hầu như không chèn/xóa giữa, mảng động thường thuận tiện. Khi biết gần đúng `n`, có thể đặt trước dung lượng (chẳng hạn `new ArrayList<>(n)`) để giảm cấp phát lại trong giai đoạn nạp.

Nếu số phần tử hoàn toàn cố định và yêu cầu trực tiếp thao tác với số nguyên nguyên thủy, `int[]` có thể giảm nhu cầu đối tượng bao bọc và metadata so với `ArrayList<Integer>`. Dù vậy, việc chọn API còn liên quan đến độ rõ ràng, tính an toàn và sự thuận tiện của mã.

## 10. Những nhận định sai thường gặp

1. **“Mảng cố định không thể thêm phần tử.”** Nếu đã cấp phát dư chỗ và tự quản lý `size`, có thể thêm vào các ô trống. Nhưng không thể làm **chính đối tượng mảng nền** tự dài ra khi hết chỗ.
2. **“Mảng động thêm phần tử nào cũng O(1).”** Thêm cuối O(1) **khấu hao** với quy tắc tăng trưởng thích hợp; một lần phải cấp phát lại có thể là O(n).
3. **“Danh sách liên kết luôn chèn/xóa O(1).”** Chỉ đúng khi đã có nút hoặc vị trí liên kết cần thiết. Nếu tìm vị trí bằng chỉ số, việc tìm có thể mất O(n).
4. **“Danh sách liên kết lưu ít bộ nhớ hơn vì không cần ô dư.”** Mỗi nút thường cần liên kết và chi phí cấp phát/đối tượng riêng; tổng overhead có thể cao hơn mảng động.
5. **“Cấu trúc nào có O(n) khi duyệt thì thực tế nhanh như nhau.”** Tính cục bộ bộ nhớ, cache, boxing và cấp phát nút có thể tạo khác biệt lớn về hằng số thời gian.
6. **“Nếu đã `reserve` đủ chỗ, chèn giữa mảng động sẽ O(1).”** Dành trước tránh cấp phát lại, nhưng không loại bỏ việc dịch `n - i` phần tử để giữ thứ tự.
7. **“Mảng động có `capacity = 100` thì có thể đọc chỉ số 99 dù `size = 10`.”** Không. Chỉ số phần tử logic hợp lệ phải nhỏ hơn `size`.
8. **“Danh sách liên kết đôi luôn xóa cuối O(1) mà không cần metadata.”** Cần giữ được nút cuối (`tail` hoặc cách truy cập tương đương). Với liên kết đơn, thường cần tìm nút trước cuối.
9. **“Iterator của mọi danh sách liên kết luôn hợp lệ.”** Nút bị xóa sẽ làm iterator/tham chiếu trỏ tới nút đó mất hiệu lực; các thư viện/ngôn ngữ có hợp đồng sửa đổi khi duyệt khác nhau.
10. **“Big-O đủ để quyết định hiệu năng.”** Độ phức tạp là nền tảng, nhưng cũng cần xét chi phí cấp phát, bộ nhớ, độ trễ trường hợp xấu và đặc điểm cache.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Cần lưu đúng 1.024 số nguyên và không bao giờ thay số phần tử. Nếu ưu tiên truy cập bằng chỉ số và tối giản cấu trúc, nên cân nhắc lựa chọn nào?

**Đáp án:** Mảng cố định tạo bằng `new int[1024]` trong Java, vì kích thước đã biết và truy cập theo chỉ số O(1). Nếu cần API phong phú hoặc thay số phần tử sau này, mảng động có thể thuận tiện hơn.

**Câu 2.** Một mảng động chứa 1.000 phần tử, `capacity = 2.048`. Muốn chèn một phần tử vào đầu và giữ thứ tự, có cần cấp phát lại không và phải dịch bao nhiêu phần tử?

**Đáp án:** Không cần cấp phát lại vì còn chỗ; vẫn phải dịch **1.000 phần tử** sang phải. Thời gian O(n).

**Câu 3.** Với danh sách liên kết đôi có con trỏ tới nút đứng trước vị trí cần chèn, chi phí nối một nút mới vào đó là bao nhiêu nếu không tính tìm nút và cấp phát?

**Đáp án:** O(1), vì chỉ cần cập nhật một số hữu hạn liên kết. Nếu chỉ có chỉ số `i`, việc đi tới vị trí đó thường O(n).

**Câu 4.** Vì sao `LinkedList.get(i)` trong Java thường chậm hơn `ArrayList.get(i)` khi `i` nằm xa hai đầu?

**Đáp án:** `ArrayList` truy cập ô theo chỉ số O(1), còn `LinkedList` phải đi qua các nút theo liên kết từ đầu hoặc cuối, mất O(n) trong trường hợp xấu.

**Câu 5.** Một danh sách liên kết đơn có `head` nhưng không có `tail`. Thêm vào cuối một danh sách `n` nút thường có độ phức tạp nào?

**Đáp án:** O(n), vì phải đi từ `head` tới nút cuối. Nếu giữ `tail` được cập nhật đúng, thêm cuối có thể O(1).

**Câu 6.** Nếu ứng dụng thường xuyên xóa phần tử đầu một danh sách dài nhưng vẫn muốn cấu trúc dựa trên mảng, có cấu trúc nào khác cần cân nhắc?

**Đáp án:** Mảng vòng (*circular buffer*) hoặc deque dựa trên mảng, ví dụ `ArrayDeque` của Java. Nó có thể thay đổi vị trí đầu/cuối logic mà không dồn toàn bộ phần tử sau mỗi lần bỏ đầu.

**Câu 7.** Một mảng cố định dài 100 ô nhưng mới dùng 30 ô, có thể nói nó “đã chứa 100 phần tử logic” không?

**Đáp án:** Nếu ứng dụng tự quản lý `size = 30`, thì chỉ có 30 phần tử logic, dù mảng vật lý có 100 ô. Nếu không có lớp quản lý `size`, bản thân `int[]` vẫn có `length = 100` và tất cả 100 ô vật lý đều có giá trị (đối với Java `int[]`, ô chưa ghi có giá trị mặc định bằng 0).

**Câu 8.** Cấu trúc nào thường tận dụng CPU cache tốt hơn khi duyệt tuần tự rất nhiều phần tử: mảng động hay danh sách liên kết?

**Đáp án:** Mảng động thường có lợi thế do các ô lưu trữ liên tiếp. Danh sách liên kết có thể cần đi theo các con trỏ tới nút nằm rải rác. Đây là đặc tính hiệu năng thực tế, không thay đổi việc cả hai đều có độ phức tạp duyệt O(n).

**Câu 9.** Một chương trình cần chèn/xóa tại **các nút đang được giữ sẵn** và muốn tham chiếu đến các nút khác không đổi khi thao tác. Nên cân nhắc cấu trúc nào?

**Đáp án:** Danh sách liên kết có hợp đồng ổn định nút/iterator phù hợp, ví dụ `std::list` trong C++. Cần tính thêm chi phí nút và việc không truy cập theo chỉ số O(1).

**Câu 10.** Với mảng động tăng dung lượng theo hệ số cố định lớn hơn 1, `n` lần thêm cuối từ rỗng có tổng thời gian nào, và vì sao không nên nói mỗi lần đều O(1) trường hợp xấu nhất?

**Đáp án:** Tổng thời gian O(n), nên O(1) khấu hao mỗi lần thêm. Tuy nhiên, khi bộ đệm đầy, một lần thêm có thể cấp phát lại và sao chép O(n) phần tử.

**Câu 11.** Nếu liên tục duyệt một `LinkedList` bằng `get(i)` từ `i = 0` đến `n - 1`, tổng thời gian có thể là bậc nào? Cần thay bằng gì?

**Đáp án:** Có thể O(n²) do mỗi lần `get(i)` phải tìm nút từ đầu/cuối. Dùng iterator hoặc `for-each` giúp duyệt liên tiếp tổng O(n).

**Điểm ghi nhớ:** **Mảng cố định** thích hợp khi độ dài vùng lưu trữ đã biết và ổn định. **Mảng động** giữ lợi thế truy cập chỉ số O(1) của mảng, đồng thời mở rộng linh hoạt và thêm cuối O(1) khấu hao, nhưng chèn/xóa giữa phải dời phần tử. **Danh sách liên kết** tránh phải dời các nút khi nối/tháo tại vị trí đã biết, nhưng truy cập theo chỉ số thường O(n) và chi phí bộ nhớ của nút cao hơn. Hãy chọn theo **chuỗi thao tác thực tế, ràng buộc bộ nhớ, độ trễ và yêu cầu ổn định tham chiếu**, không chỉ theo tên cấu trúc.
