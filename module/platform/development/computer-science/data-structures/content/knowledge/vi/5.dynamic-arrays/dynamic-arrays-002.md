# Biểu diễn mảng động bằng bộ đệm, kích thước và dung lượng

Mảng động (*dynamic array*) là cấu trúc dữ liệu cho phép truy cập phần tử theo chỉ số như mảng thông thường, đồng thời có thể mở rộng khi số phần tử tăng. Đằng sau vẻ đơn giản của thao tác `add`, `get` hay `remove` là một mô hình lưu trữ gồm **bộ đệm (`buffer`)**, **kích thước (`size`)** và **dung lượng (`capacity`)**.

Bài học này tập trung vào cách ba thành phần đó phối hợp để biểu diễn một mảng động, duy trì trạng thái hợp lệ và thực hiện các thao tác. Hiểu mô hình này giúp tự cài đặt cấu trúc dữ liệu, giải thích chi phí thời gian/bộ nhớ và tránh lỗi truy cập vùng chưa chứa phần tử.

## 1. Ba thành phần của một mảng động

| Thành phần | Vai trò trong cài đặt | Ví dụ |
| --- | --- | --- |
| `buffer` | Vùng lưu trữ liên tiếp chứa các ô đã cấp phát, thường là một mảng nền có kích thước cố định | Một `int[]` gồm sáu ô |
| `size` | Số phần tử **đang tồn tại về mặt logic** và có thể truy cập bằng chỉ số | `3` |
| `capacity` | Số phần tử tối đa có thể đặt vào `buffer` hiện tại trước khi phải cấp phát vùng lớn hơn | `6` |

Ví dụ, một mảng động chứa ba giá trị `12`, `25`, `40`:

```text
          đối tượng DynamicArray
       ┌────────────────────────┐
       │ buffer ────────────────┼────┐
       │ size     = 3           │    │
       │ capacity = 6           │    │
       └────────────────────────┘    ▼
                            bộ đệm đã cấp phát
          chỉ số        0    1    2    3    4    5
                       ┌────┬────┬────┬────┬────┬────┐
          buffer       │ 12 │ 25 │ 40 │  ? │  ? │  ? │
                       └────┴────┴────┴────┴────┴────┘
                       └───── hợp lệ ──┘└─ dự trữ ───┘
```

Các vị trí `0`, `1`, `2` thuộc mảng động; các ô `3`, `4`, `5` đã được cấp phát nhưng **chưa là phần tử của mảng**. Dấu `?` không có nghĩa là ô chứa `null` hay `0`: với từng ngôn ngữ, vùng này có thể được khởi tạo bằng giá trị mặc định hoặc chứa dữ liệu cũ. Ranh giới hợp lệ được xác định bởi `size`, **không phải giá trị nằm trong ô**.

Ta có thể chia bộ đệm theo khoảng chỉ số nửa mở:

```text
[0, size)          : phần tử đang sử dụng
[size, capacity)   : các ô dành sẵn
```

Vì vậy `buffer[capacity - 1]` có thể là một vị trí tồn tại trong bộ đệm, nhưng `get(capacity - 1)` vẫn phải từ chối nếu chỉ số đó lớn hơn hoặc bằng `size`.

## 2. Các bất biến cần giữ đúng

**Bất biến (*invariant*)** là điều kiện phải đúng ở những thời điểm mà cấu trúc sẵn sàng cho thao tác tiếp theo:

1. `0 <= size <= capacity`.
2. `buffer` có ít nhất `capacity` ô; với ví dụ dùng mảng nền Java và lưu riêng ba trường, ta đặt `buffer.length == capacity`.
3. Mỗi vị trí từ `0` đến `size - 1` chứa một phần tử hợp lệ theo hợp đồng của cấu trúc.
4. Những vị trí từ `size` đến `capacity - 1` không được trả về như phần tử hiện có, dù có giá trị vật lý trong bộ đệm.

Khi `size = 0`, mảng rỗng. Nó có thể có `capacity = 0` và một bộ đệm rỗng, hoặc có `capacity > 0` vì đã dành sẵn chỗ. Khi `size = capacity`, bộ đệm hiện tại đầy; lần thêm tiếp theo phải mở rộng nếu cấu trúc cho phép.

Trong nhiều ngôn ngữ, `capacity` có thể **suy ra** từ độ dài của `buffer` thay vì lưu thành một trường độc lập. Chẳng hạn một cài đặt Java có thể chỉ lưu `int[] buffer` và `int size`, rồi định nghĩa `capacity()` trả về `buffer.length`. Nếu lưu cả ba trường để dễ học, mọi thao tác thay `buffer` phải đồng thời cập nhật `capacity` để giữ bất biến thứ hai.

## 3. Trạng thái thay đổi sau từng thao tác

Giả sử bắt đầu với `size = 0`, `capacity = 0` và sử dụng chính sách **tăng gấp đôi dung lượng khi đầy**, bắt đầu từ một ô. Đây là một chiến lược minh họa, không phải quy tắc bắt buộc của mọi thư viện.

| Thao tác | `buffer` trong phần đang dùng | `size` | `capacity` | Giải thích |
| --- | --- | ---: | ---: | --- |
| Khởi tạo | `[]` | 0 | 0 | Chưa lưu phần tử nào |
| `append(12)` | `[12]` | 1 | 1 | Cấp phát một ô rồi ghi phần tử |
| `append(25)` | `[12, 25]` | 2 | 2 | Cấp phát hai ô, chép `12` rồi thêm `25` |
| `append(40)` | `[12, 25, 40]` | 3 | 4 | Cấp phát bốn ô, chép hai phần tử rồi thêm `40` |
| `insert(1, 18)` | `[12, 18, 25, 40]` | 4 | 4 | Dời `25`, `40` sang phải và chèn `18` |
| `removeAt(2)` | `[12, 18, 40]` | 3 | 4 | Bỏ `25`, dồn `40` sang trái |
| `reserve(7)` | `[12, 18, 40]` | 3 | 8 | Mở rộng theo hệ số 2 để có ít nhất bảy ô |
| `clear()` | `[]` | 0 | 8 | Xóa logic các phần tử; giữ bộ đệm để dùng lại |

Điểm quan trọng là việc đổi `capacity` **không tự động đổi `size`**. `reserve(7)` yêu cầu đủ chỗ cho ít nhất bảy phần tử, nhưng tại bước đó mảng vẫn chỉ chứa ba phần tử. Sau `clear()`, các ô của bộ đệm vẫn tồn tại về mặt lưu trữ nhưng không có chỉ số phần tử nào hợp lệ.

### Khi thêm vào cuối

```text
append(value):
    bảo đảm buffer có ít nhất size + 1 ô
    buffer[size] = value
    size = size + 1
```

Nếu `size < capacity`, chỉ cần ghi vào ô kế tiếp. Nếu đầy, phải cấp phát bộ đệm lớn hơn, sao chép **`size` phần tử hợp lệ**, thay bộ đệm, cập nhật dung lượng, rồi mới ghi phần tử mới.

```text
Trước:  buffer = [12, 25]       size = 2, capacity = 2

        cấp phát vùng mới 4 ô
        sao chép hai phần tử: 12, 25
        ghi thêm 40 tại chỉ số 2

Sau:    buffer = [12, 25, 40, ?] size = 3, capacity = 4
```

Việc cấp phát lại có thể làm thay đổi địa chỉ bộ đệm. Bởi vậy, trong ngôn ngữ cho phép giữ con trỏ hoặc iterator trỏ trực tiếp vào vùng nhớ (ví dụ `std::vector` của C++), việc mở rộng có thể khiến các con trỏ/iterator cũ không còn hợp lệ.

### Khi chèn hoặc xóa ở giữa

Chèn tại chỉ số `i` cần chỗ cho phần tử mới, rồi dời các phần tử từ `i` đến `size - 1` **sang phải, theo thứ tự từ phải sang trái**, tránh ghi đè phần tử chưa di chuyển:

```text
Trước chèn 18 tại i = 1:  [12, 25, 40, ?]
Dời 40, rồi dời 25:      [12, 25, 25, 40]
Ghi 18 vào ô 1:          [12, 18, 25, 40]
size: 3 -> 4, capacity: 4
```

Khi xóa phần tử tại `i`, dời các phần tử sau `i` **sang trái**, giảm `size` đi một. Một ô cuối có thể vẫn chứa dữ liệu cũ; nếu `buffer` giữ tham chiếu đối tượng, nên xóa tham chiếu không còn dùng để hỗ trợ thu hồi bộ nhớ.

## 4. Một cài đặt Java minh họa cả ba thành phần

Ví dụ sau dùng `int[]` làm `buffer`, đồng thời lưu riêng `size` và `capacity` để nhìn rõ trạng thái. Phương thức `ensureCapacity` đảm bảo sức chứa tối thiểu trước khi thêm hoặc chèn; phần tử chỉ được truy cập nếu chỉ số nằm trong `[0, size)`.

```java
import java.util.Arrays;

public class DynamicArrayRepresentation {
    static final class IntDynamicArray {
        private int[] buffer = new int[0];
        private int size = 0;
        private int capacity = 0;

        int size() {
            return size;
        }

        int capacity() {
            return capacity;
        }

        int get(int index) {
            checkExistingIndex(index);
            return buffer[index];
        }

        void append(int value) {
            ensureRoomForOne();
            buffer[size] = value;
            size++;
        }

        void insert(int index, int value) {
            if (index < 0 || index > size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
            ensureRoomForOne();
            System.arraycopy(buffer, index, buffer, index + 1, size - index);
            buffer[index] = value;
            size++;
        }

        int removeAt(int index) {
            checkExistingIndex(index);
            int removed = buffer[index];
            System.arraycopy(buffer, index + 1, buffer, index, size - index - 1);
            size--;
            buffer[size] = 0; // Xóa giá trị cũ khỏi ô vừa bỏ sử dụng
            return removed;
        }

        void reserve(int minimumCapacity) {
            if (minimumCapacity < 0) {
                throw new IllegalArgumentException("capacity < 0");
            }
            ensureCapacity(minimumCapacity);
        }

        void clear() {
            size = 0; // Với int[] không có tham chiếu đối tượng cần giải phóng
        }

        private void checkExistingIndex(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
        }

        private void ensureRoomForOne() {
            if (size == Integer.MAX_VALUE) {
                throw new IllegalStateException("Không thể tăng size");
            }
            ensureCapacity(size + 1);
        }

        private void ensureCapacity(int minimumCapacity) {
            if (minimumCapacity <= capacity) {
                return;
            }
            int newCapacity = Math.max(1, capacity);
            while (newCapacity < minimumCapacity) {
                if (newCapacity > Integer.MAX_VALUE / 2) {
                    newCapacity = minimumCapacity; // Tránh tràn số khi nhân đôi
                    break;
                }
                newCapacity *= 2;
            }

            int[] newBuffer = new int[newCapacity];
            System.arraycopy(buffer, 0, newBuffer, 0, size);
            buffer = newBuffer;
            capacity = newBuffer.length;
        }

        @Override
        public String toString() {
            return Arrays.toString(Arrays.copyOf(buffer, size));
        }
    }

    public static void main(String[] args) {
        IntDynamicArray a = new IntDynamicArray();
        a.append(12);
        a.append(25);
        a.append(40);
        System.out.println(a + " | size=" + a.size() + ", capacity=" + a.capacity());
        // [12, 25, 40] | size=3, capacity=4

        a.insert(1, 18);
        a.removeAt(2);
        a.reserve(7);
        System.out.println(a + " | size=" + a.size() + ", capacity=" + a.capacity());
        // [12, 18, 40] | size=3, capacity=8

        a.clear();
        System.out.println(a + " | size=" + a.size() + ", capacity=" + a.capacity());
        // [] | size=0, capacity=8
    }
}
```

Trong ví dụ này, `newBuffer` chỉ thay thế `buffer` **sau khi đã sao chép** các phần tử đang sử dụng. Sau đó `capacity` được gán bằng độ dài vùng mới, giữ điều kiện `buffer.length == capacity`. Các thao tác với chỉ số chèn cho phép `index == size` (chèn cuối), trong khi `get` và `removeAt` yêu cầu `index < size`.

Đây là cài đặt dùng để học mô hình; một thư viện sản xuất còn cần xét giới hạn kích thước mảng của runtime, lỗi hết bộ nhớ, chính sách tăng trưởng, khả năng truy cập đồng thời và cách quản lý các kiểu phần tử khác nhau. Java có thể từ chối cấp phát mảng rất lớn ngay cả khi phép tính dung lượng không tràn số.

## 5. Tại sao bộ đệm thường lớn hơn số phần tử?

Nếu chỉ cấp phát đúng `size` ô sau **mỗi lần** thêm, một chuỗi `n` lần thêm cuối phải sao chép tổng cộng khoảng `0 + 1 + ... + (n - 1)` phần tử, tức **O(n²)**. Khi tăng dung lượng theo một hệ số lớn hơn 1 (ví dụ nhân đôi), các lần cấp phát thưa hơn:

```text
capacity: 0 -> 1 -> 2 -> 4 -> 8 -> 16 -> ...
           sao chép 0, 1, 2, 4, 8, ... phần tử khi đầy
```

Tổng số phần tử được sao chép khi thêm `n` phần tử là O(n); do đó **thêm cuối có thời gian O(1) khấu hao (*amortized*)**, dù một lần thêm cụ thể vẫn có thể mất O(n) vì phải mở rộng. Cấp phát dư làm tăng lượng bộ nhớ dự trữ để giảm số lần cấp phát và sao chép.

| Thao tác | Chi phí thời gian điển hình | Thay đổi trạng thái |
| --- | --- | --- |
| `get(i)` hợp lệ | O(1) | Không đổi |
| `append(value)` | O(1) khấu hao; có lần phải sao chép O(n) | `size += 1`; `capacity` tăng khi cần |
| `insert(i, value)` | O(n) vì có thể phải dời phần tử | `size += 1`; có thể tăng `capacity` |
| `removeAt(i)` | O(n) trong trường hợp phải dồn các phần tử | `size -= 1`; thường giữ `capacity` |
| `reserve(k)` | Không đổi nếu đã đủ chỗ; nếu cấp phát lại, phải tạo vùng mới và sao chép | `size` giữ nguyên; `capacity >= k` |
| `clear()` trong ví dụ `int[]` | O(1) vì chỉ đặt lại `size` | `size = 0`; `capacity` giữ nguyên |

Trong Java, việc tạo một mảng mới cũng khởi tạo các ô về giá trị mặc định, nên thời gian cấp phát còn phụ thuộc dung lượng vùng mới; bảng chỉ tóm tắt cách phân tích thông dụng theo số phần tử. Với mảng giữ **tham chiếu đối tượng**, thao tác xóa hoặc làm rỗng thường cần xóa các tham chiếu cũ, vì vậy `clear()` có thể mất O(n).

Về bộ nhớ, nếu mỗi ô có độ rộng `b` byte, vùng lưu trữ chứa khoảng `capacity × b` byte (chưa tính thông tin quản lý và dữ liệu của đối tượng được tham chiếu). Số ô chưa sử dụng bằng `capacity - size`. Chi phí bộ nhớ là **O(capacity)**, không chỉ O(size).

## 6. Những lựa chọn thiết kế cần hiểu rõ

**Lưu `capacity` hay suy ra từ `buffer`?** Nếu bộ đệm có thuộc tính độ dài như `int[]` trong Java, dùng `buffer.length` tránh trạng thái hai giá trị không khớp. Lưu riêng `capacity` vẫn hữu ích để biểu diễn tường minh và phù hợp với môi trường chỉ lưu con trỏ đến vùng nhớ mà không truy vấn được số ô đã cấp phát.

**Có thu nhỏ sau khi xóa không?** Cấu trúc có thể giữ bộ đệm để thêm lại nhanh; một số cài đặt cung cấp thao tác thu gọn riêng. Nếu cứ giảm dung lượng ngay khi `size` giảm một, chương trình dễ phải cấp phát lại liên tục khi thêm/xóa luân phiên. Quy tắc thu nhỏ cần cân nhắc tần suất thao tác và bộ nhớ.

**Ô chưa sử dụng có nhất thiết phải được xóa không?** Với `int[]`, một ô cũ có thể còn giá trị sau khi `size` giảm nhưng không còn là phần tử hợp lệ. Với `Object[]`, việc giữ tham chiếu ở các ô đã bỏ có thể ngăn đối tượng được thu hồi; vì thế thường phải gán `null` cho những ô đó. Đó là khác biệt về quản lý tài nguyên, không làm thay đổi định nghĩa `size`.

**Các thư viện có biểu diễn giống hệt nhau không?** Không. `std::vector` trong C++ có `size()` và `capacity()`; `ArrayList` trong Java có `size()` nhưng không cung cấp phương thức công khai đọc trực tiếp sức chứa nội bộ; `list` trong Python có `len()` cho số phần tử nhưng không có API chuẩn `capacity()`. Các thư viện có thể có hệ số tăng dung lượng khác nhau. Mô hình ba thành phần là một cách giải thích cơ bản, không phải cam kết về cách triển khai nội bộ của mọi thư viện.

## 7. Lỗi thường gặp và cách phát hiện

1. **Kiểm tra chỉ số theo `capacity`**: nếu `size = 3`, `capacity = 8`, chỉ số `7` vẫn không hợp lệ. Chỉ `0 <= i < size` mới được `get(i)`.
2. **Tăng `size` trước khi đảm bảo đủ chỗ**: khi đã đầy, việc ghi vào `buffer[size]` trước khi mở rộng dẫn tới vượt chỉ số. Phải kiểm tra sức chứa trước, rồi ghi và cập nhật `size`.
3. **Cấp phát vùng mới nhưng quên sao chép**: phần tử logic cũ sẽ biến mất; cần sao chép đúng đoạn `[0, size)`.
4. **Thay `buffer` mà không đồng bộ `capacity`**: sẽ vi phạm bất biến nếu dung lượng được lưu riêng. Nên cập nhật cùng một chỗ, hoặc suy `capacity` từ độ dài bộ đệm.
5. **Chèn sai hướng dịch chuyển**: dời từ trái sang phải có thể ghi đè phần tử chưa chuyển. Khi chèn, dời từ cuối về đầu; khi xóa, dồn từ đầu về cuối.
6. **Cho rằng `reserve(k)` tạo sẵn `k` phần tử**: nó chỉ đảm bảo sức chứa. `size` không đổi, nên không thể đọc ô dự trữ qua API truy cập phần tử.

## 8. Tự kiểm tra mô hình

**Câu 1.** Cho `buffer` có sáu ô: `[4, 7, 9, ?, ?, ?]`, `size = 3`, `capacity = 6`. Lời gọi `get(4)` có hợp lệ không? Vì sao?

**Đáp án:** Không. Chỉ số `4` nằm trong vùng bộ đệm nhưng ngoài đoạn phần tử logic `[0, 3)`.

**Câu 2.** Trong cài đặt bắt đầu với `capacity = 0` và luôn nhân đôi khi cần, thêm lần lượt năm phần tử. Hãy xác định `size`, `capacity` cuối cùng và số lần phải cấp phát.

**Đáp án:** `size = 5`, `capacity = 8`; các lần cấp phát dung lượng `1`, `2`, `4`, `8` (bốn lần nếu tính cả lần đầu).

**Câu 3.** Một thao tác `reserve(20)` làm bộ đệm mới có 32 ô và chép bảy phần tử cũ. Trước và sau thao tác, `size` bằng bao nhiêu?

**Đáp án:** Đều bằng `7`. `reserve` làm thay đổi sức chứa, không thay đổi số phần tử đang dùng.

**Câu 4.** Một mảng động lưu tham chiếu đối tượng xóa phần tử cuối bằng `size--`, nhưng không xóa ô `buffer[size]`. Truy cập qua `get()` có còn trả về phần tử đó không, và có vấn đề nào khác?

**Đáp án:** `get()` đúng quy tắc sẽ từ chối vì chỉ số không còn nhỏ hơn `size`. Tuy nhiên, tham chiếu còn sót trong bộ đệm có thể giữ đối tượng trong bộ nhớ; cài đặt nên gán `null` cho ô vừa ngừng sử dụng.

Khi thiết kế mảng động, hãy luôn xác định rõ **vùng lưu trữ nằm ở `buffer`, phần tử hợp lệ được đếm bằng `size`, và khả năng chứa tối đa của vùng hiện tại được thể hiện bằng `capacity`**. Mọi thao tác đúng đều phải duy trì mối quan hệ giữa ba thành phần này.
