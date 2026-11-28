# Đặt trước dung lượng khi biết quy mô dữ liệu

Khi dùng **mảng động** (*dynamic array*) để xây dựng danh sách phần tử, ta thường thêm dữ liệu lần lượt bằng `append`, `add` hoặc `push_back`. Nếu bộ đệm hiện tại đã đầy, mảng động phải cấp phát bộ đệm lớn hơn và chuyển các phần tử cũ sang vùng mới. Cơ chế mở rộng theo hệ số giúp thao tác thêm cuối có chi phí **O(1) khấu hao**, nhưng các lần cấp phát và sao chép vẫn tiêu tốn thời gian.

Trong nhiều bài toán, ta **biết trước số phần tử dự kiến**: số bản ghi trong một lô dữ liệu, số đỉnh cần lưu, số mẫu đã được khai báo trong đầu tệp hay số kết quả đã tính được ở bước trước. Khi đó, có thể **đặt trước dung lượng** (*reserve capacity*, *preallocate*) để giảm hoặc tránh cấp phát lại trong quá trình thêm. Bài học này chỉ ra khi nào nên làm, cách giữ đúng sự khác nhau giữa `size` và `capacity`, chi phí thực tế và những đánh đổi về bộ nhớ.

## 1. Đặt trước dung lượng là gì?

Giả sử một mảng động có ba thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `buffer` | Vùng lưu trữ liên tiếp của các ô đã cấp phát |
| `size` | Số phần tử hợp lệ đã được thêm |
| `capacity` | Số ô mà bộ đệm hiện tại có thể chứa mà chưa cần cấp phát lại |

Bất biến quan trọng là:

\[
0\le\text{size}\le\text{capacity}.
\]

Ví dụ ban đầu:

```text
Mảng động chứa 3 phần tử:

chỉ số:       0     1     2     3
            +-----+-----+-----+-----+
buffer:     |  A  |  B  |  C  |  ?  |
            +-----+-----+-----+-----+

size = 3, capacity = 4
```

Nếu biết sẽ có **ít nhất 10 phần tử tổng cộng** và gọi `reserve(10)` (trong một API hỗ trợ thao tác này), bộ đệm có thể được thay bằng vùng đủ chứa ít nhất mười ô:

```text
Sau reserve(10):

chỉ số:       0     1     2     3     4          9
            +-----+-----+-----+-----+--- ... ---+
buffer:     |  A  |  B  |  C  |  ?  |    ?      |
            +-----+-----+-----+-----+--- ... ---+
            <--- 3 phần tử ---><-- 7 ô dự trữ -->

size = 3, capacity >= 10
```

**Điểm cốt lõi:** `reserve(10)` chỉ bảo đảm đủ **chỗ chứa** cho tối thiểu mười phần tử; nó **không biến `size` thành 10**. Các ô dự trữ chưa phải phần tử logic và không được đọc qua giao diện `get(i)` khi `i >= size`.

Trong nhiều thư viện, yêu cầu dành trước dung lượng nhỏ hơn hoặc bằng `capacity` hiện tại sẽ không thay đổi bộ đệm. `reserve(10)` cũng không có nghĩa sẽ thu nhỏ một bộ đệm đang chứa 16 ô xuống 10 ô.

## 2. Vì sao biết trước quy mô có thể giúp giảm sao chép?

Giả sử cần đọc lần lượt **10 số nguyên** vào một mảng động rỗng. Không đặt trước dung lượng, một cài đặt minh họa với chính sách **nhân đôi khi đầy** sẽ trải qua các mức `capacity`:

```text
Ban đầu:                      capacity = 0
Thêm phần tử thứ 1:   0 -> 1   sao chép 0 phần tử cũ
Thêm phần tử thứ 2:   1 -> 2   sao chép 1 phần tử cũ
Thêm phần tử thứ 3:   2 -> 4   sao chép 2 phần tử cũ
Thêm phần tử thứ 5:   4 -> 8   sao chép 4 phần tử cũ
Thêm phần tử thứ 9:   8 -> 16  sao chép 8 phần tử cũ
```

Tổng cộng có **5 lần cấp phát**, **15 phần tử cũ được sao chép** và **10 lần ghi phần tử mới**. Sau khi thêm đủ 10 số, mảng còn sáu ô dự trữ.

Nếu đặt trước `capacity >= 10` ngay từ đầu:

```text
Khởi tạo và reserve(10):
  cấp phát bộ đệm đủ 10 ô, sao chép 0 phần tử cũ

append lần 1 ... lần 10:
  luôn có ô trống; chỉ ghi phần tử rồi tăng size

Kết quả:
  size = 10, capacity >= 10
  không cần cấp phát lại trong 10 lần append
```

Theo mô hình cài đặt đặt dung lượng đúng bằng giá trị yêu cầu, hai trường hợp khác nhau như sau:

| Chỉ số so sánh | Không đặt trước, nhân đôi khi đầy | `reserve(10)` ngay từ đầu |
| --- | ---: | ---: |
| Số lần tạo bộ đệm mới | 5 | 1 |
| Số phần tử cũ phải sao chép | 15 | 0 |
| Số phần tử mới được ghi | 10 | 10 |
| `size` cuối | 10 | 10 |
| `capacity` cuối | 16 | 10 |
| Số ô dư cuối | 6 | 0 |

Các con số là kết quả của **chính sách tăng trưởng cụ thể trong ví dụ**, không phải số lần cấp phát bắt buộc của tất cả thư viện. Một số thư viện có dung lượng khởi tạo mặc định hoặc quy tắc mở rộng khác.

Lợi ích chính là giảm chi phí không cần thiết khi đã biết trước nhu cầu. **Không thể bỏ qua việc ghi 10 phần tử mới**; đặt trước chỉ tránh những lần *chuyển phần tử đã có* giữa các bộ đệm trong giai đoạn thêm.

## 3. `reserve` khác `resize` và khác khởi tạo phần tử

Đây là chỗ dễ nhầm nhất khi dùng API mảng động.

| Thao tác | Ý nghĩa | Có làm tăng `size` không? |
| --- | --- | --- |
| `reserve(k)` hoặc `ensureCapacity(k)` | Yêu cầu dung lượng đủ chứa ít nhất `k` phần tử | **Không** |
| `append(value)` / `push_back(value)` | Thêm một phần tử logic vào cuối | **Có, tăng một** |
| `resize(k)` trong thư viện có hỗ trợ | Thay số phần tử logic thành `k`; có thể tạo hoặc hủy phần tử | **Có thể tăng hoặc giảm** |
| Khởi tạo danh sách gồm `k` phần tử | Tạo ngay `k` phần tử logic | **Có, thường bằng `k`** |

Ví dụ với `std::vector<int>` trong C++:

```cpp
#include <vector>
#include <iostream>

int main() {
    std::vector<int> values;  // size = 0

    values.reserve(10);
    std::cout << values.size() << " "
              << (values.capacity() >= 10) << "\n";
    // 0 1 : có đủ chỗ, nhưng chưa có phần tử nào

    values.push_back(42);
    std::cout << values.size() << "\n"; // 1

    values.resize(4); // có 4 phần tử; 3 số int mới mang giá trị 0
    std::cout << values.size() << "\n"; // 4
}
```

Sau `reserve(10)`, truy cập `values[5]` **không hợp lệ** khi `size()` vẫn là 0. Cần thêm phần tử bằng `push_back` hoặc thay đổi số phần tử bằng `resize` trước khi truy cập các chỉ số mới.

**Đặc biệt với Python:** `list` không có API chuẩn cho phép đọc hoặc đặt `capacity` trực tiếp. Viết `a = [None] * 10` tạo **mười phần tử logic** (giá trị `None`), không phải tương đương với `reserve(10)`. Nếu biết chính xác số phần tử và muốn điền theo chỉ số, có thể dùng cách khởi tạo mười chỗ rồi gán từng ô; nhưng điều đó là **một mô hình thao tác khác với `append` vào danh sách rỗng**.

## 4. Chọn đúng số lượng ô cần đặt trước

Ký hiệu:

- `s`: số phần tử đã có;
- `m`: số phần tử mới dự kiến thêm;
- `N = s + m`: tổng số phần tử dự kiến sau khi thêm.

Để tránh mở rộng trong `m` lần thêm tiếp theo, cần bảo đảm:

\[
\text{capacity}\ge N = s+m.
\]

Ví dụ, mảng đã có `s = 6` phần tử, và sắp thêm `m = 40` phần tử mới. Khi đó:

```text
size = 6
incoming = 40
minimum required capacity = 6 + 40 = 46

reserve(46)     # yêu cầu chỗ cho TỔNG 46 phần tử
append(...) x40

Kết quả: size = 46, không cần mở rộng giữa 40 lần append,
         giả sử reserve thành công và không có thay đổi khác.
```

**Đừng nhầm `reserve(40)` với “dành thêm 40 ô”.** Trong các API `reserve(k)` thông dụng, `k` là **tổng dung lượng tối thiểu**, không phải số ô cộng thêm. Nếu `capacity` chỉ được đảm bảo 40 trong khi tổng nhu cầu là 46, mảng vẫn có thể phải mở rộng trước khi hoàn tất lô dữ liệu.

### Khi mới biết giá trị ước lượng

Không phải lúc nào ta cũng biết chính xác `N`. Chẳng hạn máy chủ báo dự kiến 50.000 bản ghi, nhưng một số bản ghi có thể bị loại bỏ hoặc được bổ sung ở bước xử lý.

| Kết quả thực tế | Nếu đã đặt trước 50.000 ô | Hệ quả |
| --- | --- | --- |
| Nhận 50.000 phần tử | Vừa đủ | Không cần mở rộng trong quá trình thêm |
| Chỉ nhận 30.000 phần tử | Còn 20.000 ô dư | Có thể sử dụng bộ nhớ nhiều hơn nhu cầu |
| Nhận 70.000 phần tử | Vượt dung lượng dự trữ | Mảng động vẫn mở rộng theo chính sách bình thường |

Đặt trước là một **gợi ý tối ưu hiệu năng dựa trên nhu cầu dự đoán**, không phải giới hạn số phần tử mảng có thể chứa. Nếu số phần tử tăng vượt `capacity` đã đặt trước, cấu trúc vẫn cần cơ chế mở rộng đúng đắn.

## 5. Mã Java: đếm số lần cấp phát khi có và không có `reserve`

Ví dụ sau tự cài đặt mảng động số nguyên để quan sát rõ hành vi. `IntDynamicArray` giữ `size` và một mảng `buffer`; `capacity` được suy từ `buffer.length`. Thao tác `reserve(k)` chỉ tạo vùng lớn hơn nếu cần, sao chép **`size` phần tử hợp lệ**, rồi giữ nguyên `size`.

```java
import java.util.Arrays;

public class ReserveCapacityDemo {
    static final class IntDynamicArray {
        private int[] buffer = new int[0];
        private int size = 0;
        private int allocations = 0;
        private long copiedElements = 0;

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        void reserve(int minimumCapacity) {
            if (minimumCapacity < 0) {
                throw new IllegalArgumentException("capacity < 0");
            }
            if (minimumCapacity <= buffer.length) {
                return;
            }

            // Chi sao chep cac phan tu dang su dung.
            int[] next = new int[minimumCapacity];
            System.arraycopy(buffer, 0, next, 0, size);
            copiedElements += size;
            buffer = next;
            allocations++;
        }

        void append(int value) {
            if (size == buffer.length) {
                // Tang gap doi khi day, bat dau tu 1 o.
                int old = buffer.length;
                if (old > Integer.MAX_VALUE / 2) {
                    throw new IllegalStateException("capacity too large");
                }
                int next = old == 0 ? 1 : old * 2;
                reserve(next);
            }

            buffer[size] = value;
            size++;
        }

        String stats() {
            return "size=" + size
                + ", capacity=" + capacity()
                + ", allocations=" + allocations
                + ", copied=" + copiedElements;
        }

        int[] snapshot() {
            return Arrays.copyOf(buffer, size);
        }
    }

    public static void main(String[] args) {
        final int total = 10;
        IntDynamicArray regular = new IntDynamicArray();
        IntDynamicArray reserved = new IntDynamicArray();

        reserved.reserve(total); // size van bang 0

        for (int i = 1; i <= total; i++) {
            regular.append(i);
            reserved.append(i);
        }

        System.out.println("Normal:  " + regular.stats());
        System.out.println("Reserve: " + reserved.stats());
        System.out.println(Arrays.toString(reserved.snapshot()));
    }
}
```

Kết quả dự kiến:

```text
Normal:  size=10, capacity=16, allocations=5, copied=15
Reserve: size=10, capacity=10, allocations=1, copied=0
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

**Đọc kết quả:** Hai mảng đều chứa đúng mười phần tử và có cùng thứ tự. Mảng được đặt trước dung lượng chỉ cấp phát một lần ở giai đoạn đầu, khi `size = 0` nên không cần sao chép phần tử cũ nào. Mảng còn lại phải cấp phát ở các dung lượng `1, 2, 4, 8, 16`, tổng cộng sao chép `1 + 2 + 4 + 8 = 15` phần tử cũ.

Đoạn mã chỉ phục vụ học tập. Trong Java, `new int[k]` phải khởi tạo các ô về `0`; việc cấp phát một mảng rất lớn vẫn có chi phí thời gian và bộ nhớ đáng kể. Hơn nữa, giới hạn kích thước mảng trên máy ảo có thể thấp hơn `Integer.MAX_VALUE`, và yêu cầu cấp phát có thể thất bại do không đủ bộ nhớ.

### Nếu `reserve` được gọi sau khi đã có dữ liệu?

Giả sử `size = capacity = 4` với các phần tử `[3, 6, 9, 12]`, sau đó gọi `reserve(10)`:

```text
Trước:  [3][6][9][12]                        size=4, capacity=4
Sau:    [3][6][9][12][ ][ ][ ][ ][ ][ ]      size=4, capacity=10

Sao chép: 4 phần tử cũ trong lần reserve
Tiếp tục thêm: có thể thêm 6 phần tử mà không cần mở rộng.
```

Đặt trước muộn vẫn có thể hữu ích nếu sắp thêm một lô lớn, nhưng bản thân lần `reserve` có thể gây **cấp phát và sao chép O(size)** ngay tại thời điểm gọi. Với ngôn ngữ cho phép giữ tham chiếu, con trỏ hoặc iterator đến bộ đệm, cấp phát lại còn có thể làm chúng không hợp lệ.

## 6. Sử dụng API thư viện đúng cách

### C++: `std::vector::reserve`

```cpp
#include <vector>
#include <cstddef>

void loadValues(const std::vector<int>& incoming) {
    std::vector<int> values;
    values.reserve(incoming.size()); // chi dat truoc dung luong

    for (int x : incoming) {
        values.push_back(x);
    }
    // values.size() == incoming.size()
}
```

Trong C++, `reserve(k)` bảo đảm `capacity() >= k` khi thành công; nó **không thay đổi `size()`**. Nếu `k <= capacity()`, thao tác không yêu cầu tăng dung lượng. Nếu `k > capacity()`, `std::vector` cấp phát lại và có thể làm mất hiệu lực các con trỏ, tham chiếu và iterator trỏ vào phần tử cũ. Với các kiểu đối tượng phức tạp, việc chuyển sang bộ đệm mới có thể phải di chuyển hoặc sao chép các đối tượng theo quy tắc của kiểu.

Nếu vector đã có dữ liệu và cần thêm một lô, giá trị cần đặt trước là **`values.size() + incoming.size()`**, sau khi kiểm tra tổng không vượt `max_size()` và không làm tràn kiểu số lượng phần tử. Không nên gọi `reserve(size() + 1)` trước **mỗi lần** `push_back`: cách làm này có thể phá lợi ích tăng dung lượng theo cấp số nhân của vector, khiến việc cấp phát lại diễn ra gần như sau từng phần tử.

### Java: `ArrayList` và `ensureCapacity`

```java
import java.util.ArrayList;

public class BatchUsers {
    public static void main(String[] args) {
        int expected = 50_000;

        ArrayList<Integer> values = new ArrayList<>(expected);
        // values.size() == 0; khong co 50_000 phan tu logic

        for (int i = 0; i < expected; i++) {
            values.add(i);
        }

        System.out.println(values.size()); // 50000
    }
}
```

Có thể dùng hàm tạo `new ArrayList<>(expected)` khi đã biết tổng quy mô trước khi tạo danh sách, hoặc `list.ensureCapacity(requiredTotal)` trên danh sách đã tồn tại. Cả hai đều chuẩn bị **dung lượng**, không làm `size()` tăng lên con số đó.

`ArrayList` không cung cấp API công khai chuẩn để đọc trực tiếp dung lượng của bộ đệm nội bộ, nên không nên suy đoán `capacity` bằng `size()` hay mặc định một hệ số tăng cố định cho mọi phiên bản.

### Python: không có `list.reserve` chuẩn

Python `list` không có phương thức `reserve` chuẩn. Với bài toán biết chính xác số phần tử và cần điền theo vị trí, một lựa chọn là:

```python
n = 5
items = [None] * n  # len(items) == 5: da co 5 phan tu logic

for i in range(n):
    items[i] = i * 10

print(items)  # [0, 10, 20, 30, 40]
```

Đây là **khởi tạo danh sách có sẵn `n` phần tử** rồi thay giá trị theo chỉ số, **khác với `reserve(n)`** của C++: phần tử `None` đã tồn tại ngay sau dòng khởi tạo. Nếu chưa biết kích thước chính xác, việc tiếp tục dùng `append` thông thường thường đơn giản và phù hợp hơn.

## 7. Đặt trước giúp giảm hằng số chi phí, không đổi bản chất của mọi thao tác

Với chiến lược tăng dung lượng theo một hệ số cố định lớn hơn 1, `n` lần thêm cuối vốn đã có **tổng thời gian O(n)**, tương ứng **O(1) khấu hao** mỗi lần. Đặt trước dung lượng đủ lớn **không đổi bậc tăng trưởng này**: ta vẫn phải ghi `n` phần tử mới.

Lợi ích nằm ở việc giảm số lần cấp phát và công sao chép phần tử cũ, có thể giúp thời gian chạy thực tế ổn định hơn trong giai đoạn thêm:

| Hoạt động | Không đặt trước, tăng theo hệ số | Đặt trước đủ chỗ từ đầu |
| --- | --- | --- |
| Ghi `n` phần tử mới | Θ(n) | Θ(n) |
| Tổng sao chép phần tử cũ do mở rộng | O(n) | 0 trong chuỗi thêm |
| Số lần mở rộng | O(log n) với chính sách hình học | 0 trong chuỗi thêm |
| Chi phí cấp phát ban đầu | Thường nhỏ | Có thể cấp phát một vùng lớn ngay |
| Tổng độ phức tạp cho `n` lần thêm | Θ(n) theo mô hình thao tác ô | Θ(n) theo mô hình thao tác ô |

Trong Java, cấp phát một bộ đệm có `n` ô có thể mất Θ(n) thời gian khởi tạo bộ nhớ. Với các ngôn ngữ và kiểu dữ liệu khác, chi phí cấp phát hoặc tạo phần tử có thể khác. Vì vậy, **không nên hiểu rằng `reserve(n)` là thao tác O(1) trong mọi môi trường**. Khi mảng đã có `s` phần tử, `reserve` còn có thể phải sao chép O(s) phần tử cũ.

Đặt trước cũng **không làm chèn/xóa giữa mảng thành O(1)**. Chèn giữa vẫn có thể phải dịch `size - i` phần tử sang phải, xóa giữa phải dồn các phần tử phía sau về trái để giữ thứ tự. `reserve` chỉ giúp tránh phần **cấp phát lại do thiếu sức chứa**.

## 8. Đánh đổi về bộ nhớ và khi nào nên dùng

Nếu đặt trước quá nhiều, chương trình giữ bộ đệm lớn nhưng sử dụng rất ít:

```text
reserve(100_000)
append 20_000 phần tử

size     = 20_000
capacity >= 100_000
ô dự trữ >= 80_000, nếu capacity đúng bằng 100_000
```

Khi `capacity = 100_000`, tỉ lệ ô dự trữ trong ví dụ là `80_000 / 100_000 = 80%`. Bộ nhớ của riêng vùng ô xấp xỉ `capacity × bytesPerSlot`, chưa bao gồm thông tin quản lý và dữ liệu của những đối tượng được tham chiếu. Nếu mỗi ô chiếm khoảng tám byte, phần 80.000 ô dự trữ tương ứng khoảng 640.000 byte.

Ngoài bộ nhớ ổn định, khi `reserve` buộc cấp phát lại một mảng đã có dữ liệu, bộ đệm cũ và bộ đệm mới có thể cùng tồn tại trong lúc sao chép. Đây là **bộ nhớ đỉnh tạm thời** cần cân nhắc trong hệ thống giới hạn RAM.

Một số gợi ý thực hành:

| Hoàn cảnh | Cách lựa chọn |
| --- | --- |
| Biết chính xác số phần tử sẽ thêm | Đặt trước tổng dung lượng cần thiết để giảm cấp phát lại |
| Đã có `s` phần tử và biết sẽ thêm `m` | Đặt trước ít nhất `s + m`, kiểm tra tràn số và giới hạn |
| Chỉ có dự báo tương đối đáng tin | Đặt trước mức ước tính phù hợp với giới hạn bộ nhớ; vẫn xử lý trường hợp dữ liệu vượt dự báo |
| Dữ liệu nhỏ hoặc kích thước rất khó đoán | Để mảng động tăng tự nhiên có thể đơn giản và tiết kiệm hơn |
| Dữ liệu tăng rồi giảm mạnh, cần trả lại RAM | Cân nhắc thao tác thu gọn riêng khi phù hợp với API và mô hình sử dụng |
| Giao dịch cần tránh đợt sao chép lớn tại thời điểm nhạy cảm | Có thể chuẩn bị trước dung lượng ở giai đoạn ít tải, nếu biết nhu cầu |

Ví dụ, một quy trình nhập 100.000 bản ghi từ tệp có thông tin số dòng có thể đặt trước dung lượng theo số dòng. Nếu dữ liệu thực tế sau lọc chỉ còn 40.000 phần tử, phần bộ nhớ dư là chi phí phải cân nhắc. Ngược lại, nếu đã biết chắc chỉ nhập 100.000 bản ghi rồi mới xử lý, đặt trước thường là một lựa chọn hợp lý.

## 9. Những lỗi thường gặp

1. **Nhầm `reserve(k)` với `resize(k)`.** Dành chỗ không tự sinh phần tử. Chỉ số hợp lệ vẫn phải nhỏ hơn `size`.
2. **Dùng số phần tử sắp thêm làm tổng dung lượng.** Nếu đang có `s` phần tử và thêm `m`, nhu cầu tối thiểu là `s + m`, không phải chỉ `m`.
3. **Gọi `reserve(size + 1)` trước mọi lần thêm.** Có thể biến một cơ chế tăng trưởng hiệu quả thành cấp phát lại liên tục, làm mất lợi ích khấu hao của cấu trúc.
4. **Cho rằng `reserve` miễn phí.** Nếu phải cấp phát lại, nó có thể tốn thời gian khởi tạo vùng mới và sao chép phần tử cũ; trong lúc đó còn cần bộ nhớ bổ sung.
5. **Đặt trước quá lớn không có giới hạn.** Dữ liệu thực tế có thể ít hơn nhiều, gây giữ quá nhiều bộ nhớ dự trữ hoặc khiến cấp phát thất bại.
6. **Không xử lý trường hợp dự báo thấp hơn thực tế.** `reserve` chỉ bảo đảm một dung lượng tối thiểu. Nếu số phần tử vượt mức đó, cấu trúc vẫn phải mở rộng chính xác.
7. **Giữ con trỏ, iterator hoặc tham chiếu cũ qua đợt cấp phát lại.** Ví dụ, `std::vector::reserve` có thể làm các đối tượng trỏ vào bộ đệm cũ mất hiệu lực khi cấp phát lại.
8. **Hiểu `[None] * n` của Python là đặt trước dung lượng nhưng không có phần tử.** Cách này đã tạo `n` phần tử logic mang giá trị `None`.

## 10. Tự kiểm tra

**Câu 1.** Mảng có `size = 6`, `capacity = 8`. Sắp thêm 20 phần tử vào cuối. Nên yêu cầu `reserve` dung lượng tối thiểu bằng bao nhiêu để không phải mở rộng trong chuỗi thêm đó?

**Đáp án:** `6 + 20 = 26`. Sau khi `reserve(26)` thành công, `size` vẫn bằng 6; sau 20 lần thêm, `size = 26`.

**Câu 2.** Một vector có `size = 0`. Sau `reserve(100)`, có thể đọc phần tử ở chỉ số `0` chưa? Vì sao?

**Đáp án:** Chưa. Dung lượng ít nhất 100 chỉ thể hiện chỗ dự trữ; số phần tử logic vẫn bằng 0. Phải thêm hoặc tạo phần tử trước khi đọc theo chỉ số.

**Câu 3.** Với mảng động ban đầu rỗng, nhân đôi dung lượng theo `1, 2, 4, 8, 16, ...`, thêm 10 phần tử mà không đặt trước sẽ sao chép bao nhiêu phần tử cũ?

**Đáp án:** `0 + 1 + 2 + 4 + 8 = 15` phần tử cũ. Nếu đặt trước đủ 10 ô ngay từ đầu, số phần tử cũ phải sao chép **trong 10 lần thêm** là 0.

**Câu 4.** Nếu một mảng đã có bốn phần tử và bốn ô lưu trữ, gọi `reserve(20)` có thể gây sao chép hay không?

**Đáp án:** Có. Cấu trúc có thể cần cấp phát bộ đệm mới đủ ít nhất 20 ô và sao chép bốn phần tử cũ. Sau đó `size` vẫn bằng 4.

**Câu 5.** Một chương trình đặt trước 200.000 ô nhưng chỉ dùng 50.000 phần tử. Nếu `capacity` thực tế đúng bằng 200.000 thì bao nhiêu ô chưa dùng, chiếm tỷ lệ bao nhiêu?

**Đáp án:** Có 150.000 ô dự trữ, tương đương `150.000 / 200.000 = 75%` số ô cấp phát.

**Câu 6.** Vì sao đặt trước `n` ô từ đầu không làm tổng chi phí thêm `n` phần tử giảm thành O(1)?

**Đáp án:** Chương trình vẫn phải ghi `n` phần tử mới, ít nhất Θ(n) công theo mô hình một lần ghi mỗi phần tử. Đặt trước chủ yếu giúp tránh các lần cấp phát và sao chép dữ liệu cũ.

**Câu 7.** Trong C++, việc gọi `reserve` với dung lượng lớn hơn hiện tại có thể ảnh hưởng thế nào đến iterator và tham chiếu?

**Đáp án:** Nếu lời gọi khiến `std::vector` cấp phát lại, các iterator, con trỏ và tham chiếu vào các phần tử cũ đều bị mất hiệu lực. Cần lấy lại chúng từ vector sau khi cấp phát lại.

**Câu 8.** Nếu dự kiến sẽ có 10.000 phần tử nhưng thực tế có 12.000, việc đặt trước 10.000 có khiến mảng động không thể nhận thêm 2.000 phần tử còn lại không?

**Đáp án:** Không, miễn là mảng động vẫn có cơ chế mở rộng, còn bộ nhớ và chưa chạm giới hạn dung lượng. Nó có thể cấp phát lại khi vượt 10.000 phần tử. `reserve` không phải giới hạn kích thước tối đa.

**Điểm ghi nhớ:** Khi biết trước tổng số phần tử, đặt trước **dung lượng đủ chứa toàn bộ dữ liệu** giúp giảm cấp phát lại và sao chép phần tử cũ trong quá trình thêm. `reserve` chỉ đổi khả năng chứa của bộ đệm; **`size` chỉ tăng khi phần tử mới thực sự được thêm**. Lợi ích hiệu năng cần được cân nhắc cùng chi phí cấp phát ban đầu, bộ nhớ dư và mức tin cậy của ước lượng quy mô.
