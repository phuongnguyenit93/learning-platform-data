# Chèn, xóa tại vị trí bất kỳ và dịch chuyển vùng dữ liệu

Mảng động (*dynamic array*) cho phép truy cập phần tử theo chỉ số nhanh và có thể mở rộng bộ đệm khi thêm dữ liệu. Nhưng khi muốn **chèn một phần tử vào giữa** hoặc **xóa một phần tử ở vị trí bất kỳ**, cấu trúc phải giữ các phần tử còn lại **liên tiếp và đúng thứ tự**. Vì thế, những thao tác này thường kéo theo công việc **dịch chuyển một vùng dữ liệu**.

Ví dụ, danh sách các bước xử lý `[A, B, C, D]` cần chèn bước `X` sau `A`. Nếu chỉ ghi đè vị trí `1` bằng `X`, ta sẽ làm mất `B`. Muốn giữ đủ dữ liệu, phải đẩy `B, C, D` sang phải một vị trí trước khi ghi `X`. Ngược lại, khi xóa `B`, ta phải kéo `C, D` sang trái để không để lại khoảng trống trong đoạn đang sử dụng.

Bài này giải thích hướng dịch chuyển, các điều kiện chỉ số, cách giữ bất biến của mảng động và chi phí thời gian, bộ nhớ. Các nguyên tắc áp dụng cho việc tự cài đặt mảng động và giúp hiểu vì sao các thao tác chèn/xóa của `ArrayList`, `std::vector` hay `list` có thể chậm hơn thêm ở cuối.

## 1. Vì sao phải dịch chuyển phần tử?

Trong mô hình mảng động phổ biến:

| Thành phần | Vai trò |
| --- | --- |
| `buffer` | Mảng nền có các ô lưu trữ liên tiếp |
| `size` | Số phần tử logic đang dùng |
| `capacity` | Số ô trong bộ đệm hiện tại |

Luôn phải có:

\[
0 \le \text{size} \le \text{capacity}.
\]

Chỉ các vị trí từ `0` đến `size - 1` mới chứa phần tử hợp lệ về mặt logic. Đoạn `[size, capacity)` có thể chứa giá trị vật lý trong bộ đệm nhưng **chưa thuộc mảng động**.

Ví dụ ban đầu:

```text
Chỉ số:    0     1     2     3     4     5
          +-----+-----+-----+-----+-----+-----+
buffer:   |  A  |  B  |  C  |  D  |  ?  |  ?  |
          +-----+-----+-----+-----+-----+-----+
          <--- các phần tử đang dùng ---><--dư-->
size = 4, capacity = 6
```

Một mảng động giữ thứ tự cần duy trì hai tính chất sau mỗi thao tác:

1. Các phần tử logic nằm liền nhau trong `buffer[0..size-1]`, không có lỗ trống.
2. Thứ tự tương đối của các phần tử **không bị chèn/xóa** được giữ nguyên.

Để chèn hoặc xóa tại chỉ số `i`, phần tử trước `i` thường không cần di chuyển. Chính đoạn từ `i` đến cuối phần đang dùng mới quyết định chi phí của thao tác.

## 2. Chèn tại vị trí `i`: dịch sang phải từ cuối về đầu

Giả sử đang có `[A, B, C, D]` với `size = 4` và `capacity = 6`. Muốn chèn `X` vào chỉ số `1`, kết quả phải là `[A, X, B, C, D]`.

### Từng bước dịch chuyển

```text
Ban đầu:
  i:       0     1     2     3     4     5
         +-----+-----+-----+-----+-----+-----+
         |  A  |  B  |  C  |  D  |  ?  |  ?  |
         +-----+-----+-----+-----+-----+-----+

1) Dịch phần tử cuối D: buffer[4] = buffer[3]
         [ A ] [ B ] [ C ] [ D ] [ D ] [ ? ]

2) Dịch C: buffer[3] = buffer[2]
         [ A ] [ B ] [ C ] [ C ] [ D ] [ ? ]

3) Dịch B: buffer[2] = buffer[1]
         [ A ] [ B ] [ B ] [ C ] [ D ] [ ? ]

4) Ghi X vào chỉ số 1, rồi tăng size
         [ A ] [ X ] [ B ] [ C ] [ D ] [ ? ]
         size = 5, capacity = 6
```

**Hướng dịch chuyển là từ phải sang trái**: đọc phần tử ở cuối trước, ghi sang ô bên phải, rồi lùi dần. Nếu đi từ trái sang phải bằng phép gán đơn giản:

```text
Sai khi chèn:
buffer[2] = buffer[1]  # [A, B, B, D, ?, ?]
buffer[3] = buffer[2]  # [A, B, B, B, ?, ?] -> mất C
```

Ta đã ghi đè `C` trước khi sao chép nó. Đi từ cuối về đầu giúp luôn đọc được giá trị gốc chưa bị ghi đè.

### Điều kiện chỉ số và mã giả

Một thao tác `insert(i, value)` cho phép:

\[
0\le i\le \text{size}.
\]

Chỉ số `i = size` là **chèn cuối**; `i = 0` là **chèn đầu**. Không được dùng `capacity` làm cận kiểm tra chỉ số, vì ô đã cấp phát dư không đồng nghĩa phần tử logic được phép chèn vào bất kỳ chỗ nào.

```text
insert(i, value):
    if i < 0 or i > size:
        báo lỗi chỉ số

    if size == capacity:
        cấp phát bộ đệm lớn hơn và sao chép size phần tử cũ

    for j từ size xuống i + 1:
        buffer[j] = buffer[j - 1]

    buffer[i] = value
    size = size + 1
```

Vòng lặp chạy qua các vị trí `size, size-1, ..., i+1`, tương đương **`size - i` lần dịch chuyển**. Khi `i = size`, vòng lặp không chạy: chèn cuối không phải dời phần tử nào, nhưng có thể vẫn cần mở rộng nếu bộ đệm đã đầy.

### Điều gì xảy ra khi không còn chỗ?

Nếu trước thao tác `size == capacity`, không thể dịch phần tử cuối sang `buffer[size]` vì ô đó chưa tồn tại. Phải **cấp phát vùng lớn hơn trước**, ví dụ tăng dung lượng theo hệ số cố định lớn hơn 1:

```text
Ban đầu, size = capacity = 4:
[A][B][C][D]

Cấp phát bộ đệm 8 ô, sao chép:
[A][B][C][D][?][?][?][?]

Dịch D, C, B sang phải, ghi X tại i = 1:
[A][X][B][C][D][?][?][?]

size = 5, capacity = 8
```

Việc cấp phát lại cần sao chép **toàn bộ `size` phần tử cũ**, sau đó thao tác chèn vẫn có thể cần dời thêm `size - i` phần tử. Tổng chi phí trong trường hợp này có thể là O(n), với `n` là số phần tử trước khi chèn. Chỉ số logic và thứ tự phần tử cũ vẫn đúng; vùng nhớ vật lý có thể đã đổi.

## 3. Xóa tại vị trí `i`: dồn sang trái từ đầu về cuối

Giả sử đang có `[A, B, C, D, E]` với `size = 5`. Xóa phần tử ở chỉ số `1` (là `B`) phải cho kết quả `[A, C, D, E]`.

### Từng bước dịch chuyển

```text
Trước xóa:
  i:       0     1     2     3     4     5
         +-----+-----+-----+-----+-----+-----+
         |  A  |  B  |  C  |  D  |  E  |  ?  |
         +-----+-----+-----+-----+-----+-----+

1) Dịch C sang ô của B:
         [ A ] [ C ] [ C ] [ D ] [ E ] [ ? ]

2) Dịch D sang ô của C:
         [ A ] [ C ] [ D ] [ D ] [ E ] [ ? ]

3) Dịch E sang ô của D:
         [ A ] [ C ] [ D ] [ E ] [ E ] [ ? ]

4) Giảm size từ 5 xuống 4, bỏ sử dụng ô cuối:
         [ A ] [ C ] [ D ] [ E ] [ ? ] [ ? ]
         size = 4
```

**Hướng dịch chuyển khi xóa là từ trái sang phải**: bắt đầu từ vị trí cần xóa, đọc phần tử bên phải rồi ghi đè vào ô hiện tại. Vì ta đọc `buffer[j + 1]` trước khi vị trí này bị sửa, thao tác không làm mất dữ liệu cần dịch chuyển tiếp.

Với `removeAt(i)`, điều kiện chỉ số là:

\[
0 \le i < \text{size}.
\]

Không được xóa ở `i = size`, vì đó là ô **sau** phần tử cuối. Khi mảng rỗng (`size = 0`), không có chỉ số xóa hợp lệ.

```text
removeAt(i):
    if i < 0 or i >= size:
        báo lỗi chỉ số

    removed = buffer[i]
    for j từ i đến size - 2:
        buffer[j] = buffer[j + 1]

    size = size - 1
    xóa tham chiếu ở buffer[size] nếu cần
    trả về removed
```

Số lần dịch chuyển là **`size - i - 1`**. Xóa phần tử cuối (`i = size - 1`) không cần dịch chuyển; xóa đầu có thể phải dồn toàn bộ `size - 1` phần tử còn lại.

### Vì sao phải dọn ô cuối?

Sau khi dồn trái, ô vật lý ở chỉ số `size` mới có thể còn chứa bản sao của phần tử cuối cũ. Ranh giới logic đã được xác định bằng `size`, nên ô này không được trả về qua `get()`. Tuy nhiên:

- Nếu bộ đệm chứa các kiểu nguyên thủy như `int[]`, giá trị còn lại không làm cho ô trở thành phần tử hợp lệ.
- Nếu bộ đệm chứa **tham chiếu đối tượng**, tham chiếu cũ trong ô ngoài vùng logic có thể giữ đối tượng trong bộ nhớ lâu hơn cần thiết. Cài đặt thường gán `null` cho ô vừa bỏ sử dụng.

Xóa phần tử thường **không làm `capacity` giảm ngay**. Mảng động có thể tái sử dụng các ô đó khi thêm dữ liệu mới. Một số cài đặt hỗ trợ thu nhỏ bộ đệm riêng; nếu thực hiện, việc cấp phát/thu nhỏ sẽ phát sinh chi phí bổ sung.

## 4. Chèn và xóa có bảo toàn thứ tự không?

Với hai thuật toán ở trên, thứ tự tương đối của những phần tử còn lại được giữ nguyên. Chẳng hạn:

```text
Ban đầu:          [10, 20, 30, 40]
Chèn 25 vào i=2:  [10, 20, 25, 30, 40]
Xóa tại i=1:      [10, 25, 30, 40]
```

Các phần tử `10, 30, 40` giữ thứ tự tương đối trong cả hai bước. Đây là hành vi thông thường của chèn/xóa trong mảng động dùng làm **danh sách có thứ tự**.

Ta cũng có thể kiểm tra bất biến trực tiếp:

**Chèn `value` tại `i`:**

- Các phần tử trước `i` giữ nguyên: đoạn `[0, i)`.
- `buffer[i]` chứa `value`.
- Mỗi phần tử cũ ở chỉ số `j \ge i` chuyển sang `j + 1`.
- `size` tăng đúng một, và `size <= capacity` sau khi đảm bảo đủ chỗ.

**Xóa tại `i`:**

- Các phần tử trước `i` giữ nguyên.
- Mỗi phần tử cũ sau `i`, tại chỉ số `j > i`, chuyển sang `j - 1`.
- `size` giảm đúng một và các vị trí `[0, size)` vẫn liên tiếp.

Những bất biến này giúp tự kiểm tra lỗi khi viết vòng lặp dịch chuyển, nhất là trường hợp chèn ở đầu, chèn cuối, xóa đầu, xóa cuối và mảng chỉ có một phần tử.

## 5. Cài đặt minh họa bằng Java

Lớp `StringDynamicArray` sau dùng `String[]` làm bộ đệm, lưu riêng `size`, tự mở rộng theo hệ số hai khi đầy và chèn/xóa bằng vòng lặp để thể hiện rõ hướng dịch chuyển. Phương thức `add` chỉ gọi `insert(size, value)`.

```java
import java.util.Arrays;

public class DynamicArrayInsertRemove {
    static final class StringDynamicArray {
        private String[] buffer = new String[2];
        private int size = 0;

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        String get(int index) {
            checkExistingIndex(index);
            return buffer[index];
        }

        void add(String value) {
            insert(size, value);
        }

        void insert(int index, String value) {
            if (index < 0 || index > size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }

            ensureRoomForOne();

            // Dịch từ cuối về đầu để không ghi đè giá trị chưa sao chép.
            for (int j = size; j > index; j--) {
                buffer[j] = buffer[j - 1];
            }

            buffer[index] = value;
            size++;
        }

        String removeAt(int index) {
            checkExistingIndex(index);
            String removed = buffer[index];

            // Dồn từ đầu về cuối để xóa khoảng trống tại index.
            for (int j = index; j < size - 1; j++) {
                buffer[j] = buffer[j + 1];
            }

            size--;
            buffer[size] = null; // Bỏ tham chiếu nằm ngoài vùng logic.
            return removed;
        }

        private void checkExistingIndex(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
        }

        private void ensureRoomForOne() {
            if (size < buffer.length) {
                return;
            }
            if (buffer.length > Integer.MAX_VALUE / 2) {
                throw new IllegalStateException("capacity cannot be doubled");
            }
            int next = buffer.length == 0 ? 1 : buffer.length * 2;
            buffer = Arrays.copyOf(buffer, next);
        }

        @Override
        public String toString() {
            return Arrays.toString(Arrays.copyOf(buffer, size));
        }
    }

    public static void main(String[] args) {
        StringDynamicArray steps = new StringDynamicArray();
        steps.add("A");
        steps.add("B");
        steps.add("C");
        steps.add("D");
        // size=4, capacity=4

        steps.insert(1, "X");
        System.out.println(steps + " | size=" + steps.size()
                           + ", capacity=" + steps.capacity());
        // [A, X, B, C, D] | size=5, capacity=8

        String removed = steps.removeAt(2);
        System.out.println("removed=" + removed + ", steps=" + steps);
        // removed=B, steps=[A, X, C, D]

        steps.insert(steps.size(), "E"); // Chèn cuối: không phải dịch.
        steps.removeAt(0);              // Xóa đầu: phải dồn trái.
        System.out.println(steps + " | size=" + steps.size()
                           + ", capacity=" + steps.capacity());
        // [X, C, D, E] | size=4, capacity=8
    }
}
```

Điểm cần chú ý trong chương trình:

- Khi chèn `X` lúc có bốn phần tử trong bộ đệm bốn ô, phương thức `ensureRoomForOne()` mở rộng lên tám ô **trước khi** dịch chuyển.
- Chỉ số chèn có thể bằng `size`; chỉ số đọc/xóa phải nhỏ hơn `size`.
- `removeAt` vừa giữ lại giá trị bị xóa để trả về, vừa dồn các phần tử phía sau và đặt `null` ở ô cuối cũ để không giữ tham chiếu không cần thiết.
- Chèn/xóa làm đổi `size` nhưng không bắt buộc đổi `capacity`. Trong ví dụ, sau khi xóa vẫn có `capacity = 8`.

Cài đặt minh họa xử lý được cả khi giá trị phần tử là `null`: một ô chứa `null` vẫn có thể là phần tử hợp lệ nếu chỉ số nhỏ hơn `size`. Tình trạng được sử dụng của ô luôn được xác định bằng chỉ số và `size`.

### Dùng `System.arraycopy` để dịch vùng dữ liệu

Java còn cung cấp phương thức `System.arraycopy` có khả năng sao chép đúng khi vùng nguồn và vùng đích **chồng lấn** trong cùng một mảng:

```java
// Trong insert, sau khi chắc chắn còn ít nhất một ô trống:
System.arraycopy(buffer, index, buffer, index + 1, size - index);

// Trong removeAt, trước khi giảm size:
System.arraycopy(buffer, index + 1, buffer, index, size - index - 1);
```

Câu lệnh thứ nhất tương đương dời phần đuôi sang phải; câu lệnh thứ hai dồn phần đuôi sang trái. Số lượng phần tử cần sao chép bằng tham số cuối cùng. Trong ví dụ, vòng lặp tự viết giúp thấy hướng dịch chuyển; khi dùng `System.arraycopy`, runtime xử lý an toàn việc nguồn và đích chồng lên nhau.

## 6. Phân tích độ phức tạp theo vị trí

Gọi `n = size` trước thao tác, `i` là chỉ số cần chèn hoặc xóa:

| Thao tác | Số phần tử cần dời | Thời gian điển hình | Ghi chú |
| --- | ---: | --- | --- |
| Chèn đầu `insert(0, x)` | `n` | O(n) | Dời toàn bộ phần tử hiện có |
| Chèn giữa `insert(i, x)`, `0 < i < n` | `n - i` | O(n - i), cộng chi phí mở rộng nếu đầy | Càng gần cuối, dời càng ít |
| Chèn cuối `insert(n, x)` | 0 | O(1) khấu hao với chính sách mở rộng hình học | Có thể cấp phát và sao chép O(n) ở lần đầy |
| Xóa đầu `removeAt(0)` | `n - 1` | O(n) | Dồn các phần tử còn lại sang trái |
| Xóa giữa `removeAt(i)` | `n - i - 1` | O(n - i - 1) cộng O(1) thao tác nền | Không cần tạo bộ đệm mới nếu giữ dung lượng |
| Xóa cuối `removeAt(n - 1)` | 0 | O(1) | Giảm `size`, dọn ô cuối |
| Đọc `get(i)` | 0 | O(1) | Truy cập trực tiếp theo chỉ số |

Trong bảng, mọi phân tích chi phí dịch chuyển giả định phép gán/sao chép một ô có chi phí hằng số. Nếu kiểu phần tử có chi phí di chuyển phức tạp, hoặc cài đặt tự thu nhỏ bộ đệm khi xóa, chi phí thực tế có thể khác.

**Tình huống đầy bộ đệm khi chèn:** nếu `size = capacity = n`, mở rộng có thể sao chép `n` phần tử cũ **ngoài** phần dời `n - i`. Như vậy, ngay cả chèn ở cuối khi đầy vẫn có trường hợp tốn O(n) cho một lần. Chỉ với chiến lược tăng dung lượng thích hợp, **chuỗi thêm cuối** mới có O(1) khấu hao.

**Tình huống xóa:** nếu giữ nguyên dung lượng sau xóa, không cần cấp phát lại; chi phí chủ yếu nằm ở số phần tử phải dồn. Trường hợp xấu của xóa là O(n) ở gần đầu, ngay cả khi còn rất nhiều ô trống.

### Ví dụ đếm chính xác phần tử dịch chuyển

Mảng có `n = 1.000` phần tử, còn đủ sức chứa:

| Thao tác | Số phần tử phải dời |
| --- | ---: |
| Chèn tại `i = 0` | 1.000 |
| Chèn tại `i = 500` | 500 |
| Chèn tại `i = 999` | 1 |
| Chèn tại `i = 1.000` | 0 |
| Xóa tại `i = 0` | 999 |
| Xóa tại `i = 500` | 499 |
| Xóa tại `i = 999` | 0 |

Bảng cho thấy thao tác gần đầu mảng thường đắt hơn thao tác gần cuối mảng, vì cần bảo toàn trật tự của nhiều phần tử phía sau.

## 7. Có thể xóa O(1) nếu không cần giữ thứ tự?

Đôi khi ứng dụng chỉ quan tâm tập hợp các phần tử đang lưu, **không cần giữ thứ tự**. Khi đó có một thủ thuật thường dùng để xóa tại chỉ số `i`: thay `buffer[i]` bằng phần tử cuối rồi giảm `size`.

```text
Ban đầu:              [A, B, C, D]    size = 4
Xóa tại i=1 (B):
  chuyển D đến ô 1:   [A, D, C, D]
  giảm size và dọn:   [A, D, C, ?]     size = 3
```

Thủ thuật này có chi phí O(1) khi đọc/ghi một ô có chi phí hằng số, nhưng **thay đổi thứ tự phần tử**: từ `[A, B, C, D]` thành `[A, D, C]`. Nó **không tương đương** với `removeAt(1)` bảo toàn thứ tự, vốn phải trả về `[A, C, D]`.

Chỉ sử dụng cách đổi phần tử cuối khi hợp đồng dữ liệu cho phép đổi thứ tự. Ví dụ, nếu mảng biểu diễn danh sách bước thực hiện, thời gian sự kiện, bảng xếp hạng hoặc dữ liệu có vị trí mang ý nghĩa, việc đổi thứ tự có thể làm sai kết quả.

## 8. Khi nào nên cân nhắc cấu trúc dữ liệu khác?

Mảng động vẫn thường phù hợp khi cần truy cập ngẫu nhiên O(1), duyệt tuần tự nhanh và chủ yếu thêm/xóa ở cuối. Nếu ứng dụng liên tục chèn/xóa gần đầu của danh sách dài, chi phí dịch chuyển O(n) cho mỗi thao tác có thể đáng kể.

| Nhu cầu chính | Hướng cân nhắc |
| --- | --- |
| Truy cập chỉ số thường xuyên, ít chèn/xóa giữa | Mảng động phù hợp |
| Chủ yếu thêm cuối, đôi khi cần tăng sức chứa | Mảng động với chính sách tăng dung lượng thích hợp |
| Thêm/xóa ở hai đầu thường xuyên | Cấu trúc deque hoặc vòng đệm có thể phù hợp hơn |
| Chèn/xóa tại nút đã biết mà không cần truy cập chỉ số nhanh | Danh sách liên kết có thể tránh dịch chuyển vùng dữ liệu |
| Chèn/xóa giữa nhưng thứ tự không quan trọng | Cân nhắc xóa bằng cách đổi với phần tử cuối |

Danh sách liên kết có thể chèn/xóa bằng cách đổi liên kết O(1) **khi đã có vị trí nút và các thông tin liên kết cần thiết**, nhưng việc tìm nút theo chỉ số thường mất O(n), đồng thời tốn bộ nhớ con trỏ và có đặc điểm truy cập bộ nhớ khác. Vì vậy, chọn cấu trúc dữ liệu phải dựa trên **toàn bộ chuỗi thao tác cần thực hiện**, không chỉ một thao tác riêng lẻ.

## 9. Lỗi thường gặp

1. **Chèn bằng cách dịch từ trái sang phải.** Phép gán sẽ ghi đè dữ liệu chưa sao chép. Với vòng lặp thủ công, chèn phải dịch từ cuối về đầu.
2. **Xóa nhưng không dồn phần đuôi.** Nếu cần bảo toàn thứ tự, việc chỉ đặt ô bị xóa thành `null` sẽ để lại lỗ trống và làm sai đoạn phần tử logic.
3. **Kiểm tra chỉ số chèn giống chỉ số xóa.** Chèn cho phép `i == size`; xóa chỉ cho phép `i < size`.
4. **Sử dụng `capacity` để xét chỉ số hợp lệ.** Số ô đã cấp phát không phải số phần tử logic đang có.
5. **Dịch phần tử cuối sang vị trí ngoài bộ đệm khi đầy.** Phải đảm bảo đủ chỗ trước khi thực hiện vòng lặp chèn.
6. **Quên cập nhật `size` hoặc cập nhật hai lần.** Chèn thành công tăng đúng một; xóa thành công giảm đúng một.
7. **Để lại tham chiếu đối tượng ngoài đoạn đang dùng.** Với bộ đệm đối tượng, nên xóa tham chiếu ở ô cuối cũ sau khi dồn và giảm `size`.
8. **Cho rằng chèn/xóa giữa có O(1) khấu hao giống thêm cuối.** Số phần tử bị dời vẫn tỷ lệ với chiều dài đoạn phía sau vị trí thao tác, kể cả khi không cấp phát lại.

## 10. Tự kiểm tra

**Câu 1.** Một mảng động có `[3, 5, 7, 9]`, `size = 4`, `capacity = 6`. Chèn `6` tại chỉ số `2`: có bao nhiêu phần tử phải dời, theo hướng nào và kết quả ra sao?

**Đáp án:** Dời hai phần tử `9` rồi `7` sang phải (từ cuối về đầu), sau đó ghi `6` ở vị trí `2`. Kết quả `[3, 5, 6, 7, 9]`, `size = 5`, `capacity = 6`.

**Câu 2.** Với `[A, B, C, D, E]`, xóa chỉ số `1` cần dịch chuyển bao nhiêu phần tử? Hướng dịch chuyển là gì?

**Đáp án:** Dời ba phần tử `C, D, E` sang trái theo thứ tự từ trái sang phải. Kết quả `[A, C, D, E]`.

**Câu 3.** Mảng có `size = capacity = 8`, muốn chèn tại chỉ số `8`. Vòng lặp dời phần tử chạy mấy lần? Thao tác có thể vẫn tốn O(n) không?

**Đáp án:** Vòng lặp dời chạy **0 lần** vì đây là chèn cuối. Tuy nhiên, bộ đệm đã đầy nên có thể phải cấp phát lớn hơn và sao chép tám phần tử cũ, làm lần chèn này tốn O(n).

**Câu 4.** Mảng có `size = 5` và `capacity = 12`. Chỉ số `5` có hợp lệ với `insert`, `removeAt` và `get` không?

**Đáp án:** Hợp lệ với `insert(5, x)` vì đây là chèn cuối; không hợp lệ với `removeAt(5)` và `get(5)` vì phần tử cuối hiện có nằm ở chỉ số `4`.

**Câu 5.** Sau khi xóa phần tử cuối của một `Object[]`, vì sao thường gán `null` cho ô vừa bỏ sử dụng dù `size` đã giảm?

**Đáp án:** Vì tham chiếu còn lưu ở ô bên ngoài đoạn phần tử logic có thể tiếp tục giữ đối tượng trong bộ nhớ. Việc gán `null` giải phóng tham chiếu đó; bản thân ô vẫn tồn tại trong `capacity`.

**Câu 6.** Xóa `B` khỏi `[A, B, C, D]` bằng cách thay `B` bằng phần tử cuối cho kết quả gì, và khi nào nên dùng?

**Đáp án:** Kết quả là `[A, D, C]` nếu dùng phép thay với `D` rồi giảm `size`. Cách này O(1) khi không cần giữ thứ tự; nếu phải bảo toàn thứ tự thì cần dồn trái để có `[A, C, D]`.

**Câu 7.** Vì sao việc giữ `capacity` lớn không giúp chèn ở đầu mảng `n` phần tử trở thành O(1)?

**Đáp án:** Dung lượng dư chỉ giúp tránh **cấp phát lại**. Chèn đầu vẫn phải dịch chuyển cả `n` phần tử để giữ thứ tự, nên vẫn cần O(n) thời gian.

Khi thiết kế thao tác trên mảng động, cần kiểm tra đồng thời **vị trí hợp lệ, chiều dịch chuyển, số phần tử phải dời, dung lượng còn trống và tính bất biến**. Chèn vào giữa dịch phần đuôi sang phải **từ cuối về đầu**; xóa ở giữa dồn phần đuôi sang trái **từ đầu về cuối**. Chính công dịch chuyển này tạo ra chi phí O(n) trong trường hợp xấu nhất, dù việc truy cập phần tử theo chỉ số vẫn là O(1).
