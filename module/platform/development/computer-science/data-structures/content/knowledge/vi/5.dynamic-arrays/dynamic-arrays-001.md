# Phân biệt số phần tử đang dùng với dung lượng đã cấp phát

Mảng động (*dynamic array*) là một cấu trúc dữ liệu lưu các phần tử liên tiếp và cho phép bổ sung phần tử khi cần. Khác với mảng có kích thước cố định, mảng động có thể thay vùng lưu trữ bằng một vùng lớn hơn. Để hiểu đúng cách nó hoạt động và chi phí thời gian, bộ nhớ, cần phân biệt hai đại lượng: **số phần tử đang dùng** (*size*) và **dung lượng đã cấp phát** (*capacity*).

Đây cũng là nền tảng để hiểu vì sao mảng động truy cập theo chỉ số nhanh, vì sao thêm ở cuối thường nhanh nhưng đôi khi tốn công sao chép, và khi nào nên dành sẵn bộ nhớ. Những phân biệt này giúp chọn cấu trúc dữ liệu phù hợp trong bài toán thực tế.

## 1. `size` và `capacity` nói về hai điều khác nhau

| Đại lượng | Ý nghĩa | Cho biết điều gì? |
| --- | --- | --- |
| `size` | Số phần tử **hợp lệ về mặt logic** mà mảng động đang chứa | Có thể truy cập các chỉ số từ `0` đến `size - 1` |
| `capacity` | Số vị trí mà vùng lưu trữ hiện tại **có thể chứa** trước khi phải cấp phát lớn hơn | Hiện còn bao nhiêu chỗ trống để thêm phần tử mà chưa cần mở rộng |
| `capacity - size` | Số vị trí còn dự trữ | Có thể thêm tối đa bao nhiêu phần tử mà không cần cấp phát lại, nếu không có thao tác khác |

Ví dụ, một mảng động lưu ba điểm số `8, 6, 9` trên vùng nhớ có năm ô:

```text
Chỉ số ô lưu trữ:     0    1    2    3    4
                     +----+----+----+----+----+
Vùng đã cấp phát:    |  8 |  6 |  9 |  ? |  ? |
                     +----+----+----+----+----+
                       ^^^^^^^^^^^^  ^^^^^^^^
                       đang sử dụng  còn dự trữ

size = 3            capacity = 5           còn trống = 2
Chỉ số hợp lệ: 0, 1, 2
```

Dấu `?` biểu thị **ô chưa thuộc phần tử logic**, không khẳng định bên trong ô chứa một giá trị đặc biệt. Trong một mảng số nguyên, những ô này có thể mang giá trị `0`; trong một vùng nhớ tái sử dụng, chúng có thể còn dữ liệu cũ. **Không được dựa vào giá trị trong ô để suy ra ô đã được sử dụng hay chưa.** Một phần tử hợp lệ hoàn toàn có thể bằng `0` hoặc `null` (nếu cấu trúc cho phép).

Bất biến quan trọng của mảng động là:

\[
0 \leq \text{size} \leq \text{capacity}
\]

- `size = 0`: mảng động rỗng về mặt logic; nó **vẫn có thể** đang giữ một vùng nhớ có `capacity > 0`.
- `size < capacity`: vẫn còn ô dự trữ.
- `size = capacity`: vùng lưu trữ hiện tại đầy; có thể tiếp tục thêm nếu cấu trúc cấp phát vùng lớn hơn.
- `size > capacity`: trạng thái sai, vì số phần tử hợp lệ không thể vượt quá số ô đang có.

`size` và `capacity` đều được đo bằng **số ô/phần tử**, không phải trực tiếp bằng byte. Lượng bộ nhớ thực tế còn phụ thuộc kích thước mỗi ô, cách biểu diễn đối tượng và phần chi phí quản lý của thư viện/ngôn ngữ.

## 2. Vì sao cần cấp phát dư?

Giả sử mỗi lần thêm một phần tử đều tạo một vùng lưu trữ đúng bằng số phần tử mới, rồi sao chép toàn bộ dữ liệu cũ. Khi thêm lần lượt `n` phần tử, số phần tử cần sao chép có thể lên đến `0 + 1 + 2 + ... + (n - 1)`, tức **O(n²)**. Thao tác thêm cuối sẽ quá đắt nếu lặp nhiều lần.

Thay vào đó, mảng động thường cấp phát **dư chỗ** và chỉ mở rộng khi `size = capacity`. Một chiến lược minh họa phổ biến là tăng gấp đôi dung lượng khi đầy (hệ số tăng thực tế do từng thư viện quyết định):

```text
Nếu size < capacity:
    lưu phần tử mới tại vị trí size
    tăng size lên 1

Nếu size = capacity:
    chọn dung lượng mới lớn hơn (ví dụ max(1, 2 * capacity))
    cấp phát vùng mới
    sao chép size phần tử hợp lệ sang vùng mới
    thay vùng lưu trữ cũ bằng vùng mới
    lưu phần tử mới tại vị trí size
    tăng size lên 1
```

Theo dõi ví dụ bắt đầu với `size = 0`, `capacity = 2`:

| Thao tác | `size` sau thao tác | `capacity` sau thao tác | Điều gì xảy ra? |
| --- | ---: | ---: | --- |
| Khởi tạo | 0 | 2 | Cấp phát sẵn hai ô |
| Thêm `A` | 1 | 2 | Ghi vào ô `0` |
| Thêm `B` | 2 | 2 | Ghi vào ô `1`, hiện đã đầy |
| Thêm `C` | 3 | 4 | Cấp phát bốn ô, sao chép `A`, `B`, rồi ghi `C` |
| Thêm `D` | 4 | 4 | Ghi vào ô `3`, hiện đã đầy |
| Thêm `E` | 5 | 8 | Cấp phát tám ô, sao chép bốn phần tử cũ, rồi ghi `E` |

Có hai điểm cần nhớ: **thêm một phần tử chỉ làm `size` tăng một**, còn `capacity` có thể giữ nguyên hoặc tăng nhiều ô cùng lúc; và **việc mở rộng vùng nhớ không tạo thêm phần tử logic**. Ví dụ sau khi thêm `C`, `size = 3` chứ không phải `4`, dù đã có bốn ô lưu trữ.

### Chi phí thời gian khi thêm cuối

Nếu còn ô trống, thêm cuối chỉ cần một phép gán và cập nhật bộ đếm: **O(1)**. Nếu phải mở rộng, thao tác đó cần sao chép khoảng `size` phần tử: **O(n)** cho riêng lần thêm ấy.

Với chiến lược tăng theo hệ số cố định lớn hơn 1 (chẳng hạn nhân đôi), các lần sao chép thưa dần: sao chép 1, 2, 4, 8, ... phần tử. Tổng số phần tử được sao chép trong `n` lần thêm vẫn là **O(n)**, nên thời gian **trung bình khấu hao (*amortized*)** cho mỗi lần thêm cuối là **O(1)**. Đây không phải lời hứa rằng *mọi lần* thêm đều O(1).

## 3. Các thao tác thay đổi `size` hoặc `capacity` như thế nào?

| Thao tác | Ảnh hưởng lên `size` | Ảnh hưởng lên `capacity` | Chi phí điển hình với mảng liên tiếp |
| --- | --- | --- | --- |
| Đọc hoặc sửa phần tử tại chỉ số hợp lệ | Không đổi | Không đổi | O(1) |
| Thêm ở cuối | Tăng 1 | Giữ nguyên hoặc tăng khi đầy | O(1) khấu hao, O(n) khi mở rộng |
| Xóa ở cuối | Giảm 1 | Thường giữ nguyên | O(1) |
| Chèn vào giữa | Tăng 1 | Có thể tăng khi đầy | O(n) do dời phần tử |
| Xóa ở giữa | Giảm 1 | Thường giữ nguyên | O(n) do dồn phần tử |
| Xóa toàn bộ phần tử (*clear*) | Về 0 | Thường giữ nguyên | Tùy cách quản lý vùng nhớ và tham chiếu |
| Dành sẵn chỗ cho ít nhất `k` phần tử (*reserve/ensure capacity*) | **Không đổi** | Có thể tăng | O(n) nếu phải cấp phát và sao chép |
| Thu gọn bộ nhớ (*trim/shrink*) | Không đổi | Có thể giảm, nhưng không dưới `size` | Thường O(n) nếu phải sao chép |

Các chi phí trên giả định việc truy cập, sao chép một ô có chi phí hằng số; một phần tử lớn hoặc một đối tượng có thao tác sao chép phức tạp có thể thay đổi chi phí thực tế. Các thư viện cũng không bắt buộc thu hẹp `capacity` ngay khi xóa.

### `reserve` khác `resize`

Điểm dễ nhầm là **dành sẵn chỗ không đồng nghĩa thêm phần tử**:

```text
Ban đầu:        [10, 20, ?, ?, ?]      size = 2, capacity = 5
reserve(8):     [10, 20, ?, ?, ?, ?, ?, ?]
                                         size = 2, capacity >= 8

resize(4):      [10, 20, x, x, ?, ?, ?, ?]
                                         size = 4, capacity >= 8
```

Ở đây `x` tượng trưng cho giá trị được tạo theo quy tắc khởi tạo của cấu trúc. `reserve(8)` chỉ đảm bảo đủ chỗ cho ít nhất tám phần tử; còn thao tác `resize(4)` (ở thư viện có cung cấp) thay đổi **số phần tử logic** thành bốn. `reserve(8)` không làm cho việc đọc ô số 7 trở nên hợp lệ khi `size` vẫn bằng 2.

## 4. Tự cài đặt mảng động số nguyên để nhìn rõ hai bộ đếm

Ví dụ Java dưới đây chủ động dùng một mảng cố định `int[]` làm vùng lưu trữ bên trong và dùng biến `size` để đánh dấu phần đã sử dụng. Đây là bản cài đặt học tập tối giản; `capacity` chính là `storage.length`.

```java
import java.util.Arrays;

public class DynamicArrayDemo {
    static class DynamicIntArray {
        private int[] storage = new int[2]; // Ban đầu có 2 ô
        private int size = 0;                // Chưa có phần tử logic nào

        int size() {
            return size;
        }

        int capacity() {
            return storage.length;
        }

        void add(int value) {
            if (size == storage.length) {
                int next = storage.length == 0 ? 1 : storage.length * 2;
                storage = Arrays.copyOf(storage, next);
            }
            storage[size] = value;
            size++;
        }

        int get(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
            return storage[index];
        }

        int removeLast() {
            if (size == 0) {
                throw new IllegalStateException("Mảng đang rỗng");
            }
            size--;
            return storage[size];
        }

        void reserve(int minimumCapacity) {
            if (minimumCapacity > storage.length) {
                storage = Arrays.copyOf(storage, minimumCapacity);
            }
        }

        void clear() {
            size = 0;
        }
    }

    public static void main(String[] args) {
        DynamicIntArray a = new DynamicIntArray();
        a.add(8);
        a.add(6);
        a.add(9); // Trước lần thêm này đã đầy: capacity 2 -> 4
        System.out.println(a.get(2));               // 9
        System.out.println(a.size() + "/" + a.capacity()); // 3/4

        a.removeLast();
        System.out.println(a.size() + "/" + a.capacity()); // 2/4

        a.reserve(10);
        System.out.println(a.size() + "/" + a.capacity()); // 2/10

        a.clear();
        System.out.println(a.size() + "/" + a.capacity()); // 0/10
    }
}
```

Đọc `get(2)` chỉ hợp lệ khi `size >= 3`; dù có `capacity = 10`, chỉ số `2` vẫn **không hợp lệ** sau khi `removeLast()` đưa `size` về 2. Mảng `int[]` có thể chứa giá trị mặc định `0` trong các ô dự trữ, nhưng những ô đó không phải phần tử đã thêm.

Trong ví dụ, `clear()` chỉ thay `size` vì dữ liệu là số nguyên nguyên thủy. Với mảng chứa **tham chiếu đối tượng**, khi xóa hoặc làm rỗng, cài đặt thường cần gán `null` cho các ô không còn dùng để tránh giữ đối tượng trong bộ nhớ không cần thiết; việc đó có thể khiến `clear()` mất O(n). Ngoài ra, cài đặt thực tế cần xử lý giới hạn dung lượng tối đa, tràn số khi nhân đôi và các điều kiện lỗi khác.

## 5. Bộ nhớ được dùng ra sao?

Nếu phần lưu trữ gồm `capacity` ô và mỗi ô chiếm xấp xỉ `b` byte, riêng vùng ô đã cấp phát có dung lượng khoảng:

\[
\text{bộ nhớ vùng ô} \approx \text{capacity} \times b
\]

Trong khi đó, số ô chứa phần tử logic chỉ bằng `size`. Ví dụ nếu `size = 10`, `capacity = 16`, mỗi ô là một vị trí 8 byte, vùng ô chiếm khoảng 128 byte; 80 byte tương ứng với 10 vị trí đang dùng và 48 byte tương ứng với 6 vị trí dự trữ. Con số này **chưa tính** phần đầu đối tượng, bộ đếm, căn chỉnh bộ nhớ hoặc dữ liệu của đối tượng được tham chiếu đến.

Có thể dùng tỉ lệ `size / capacity` (khi `capacity > 0`) để hình dung mức sử dụng **các ô đã cấp phát**. Tỉ lệ thấp nghĩa là đang giữ nhiều chỗ dự trữ; điều đó đôi khi hợp lý nếu dự kiến tiếp tục thêm nhiều phần tử. Khi `capacity = 0`, tỉ lệ này không xác định.

Việc giữ dung lượng lớn sau khi xóa là một đánh đổi: tiết kiệm thời gian cấp phát nếu mảng sắp tăng trở lại, nhưng tiếp tục chiếm bộ nhớ. Các chiến lược tự thu nhỏ cần cẩn thận: nếu vừa thêm vừa xóa quanh một ngưỡng, thu nhỏ và mở rộng liên tiếp có thể gây sao chép nhiều lần. Vì vậy các thư viện thường không tự giảm `capacity` theo từng lần xóa.

## 6. Liên hệ với thư viện thực tế

- **Java `ArrayList`**: `size()` cho số phần tử đang có; lớp có dung lượng bên trong nhưng API thông thường không đưa ra `capacity()` để đọc trực tiếp. `ensureCapacity(k)` có thể dự trữ thêm chỗ mà không làm tăng `size()`.
- **C++ `std::vector`**: cung cấp cả `size()` lẫn `capacity()`. `reserve(k)` yêu cầu sức chứa ít nhất `k`, không tạo phần tử mới; `resize(k)` thay đổi số phần tử. Khi cấp phát lại, con trỏ, tham chiếu và iterator trỏ vào vùng lưu trữ cũ có thể bị mất hiệu lực.
- **Python `list`**: `len(a)` cho số phần tử logic; ngôn ngữ không cung cấp API chuẩn `capacity()` cho người dùng. Không nên dùng `len(a)` để suy ra số ô đã cấp phát bên trong.

Nguyên tắc quan trọng khi chuyển ngôn ngữ: **đừng nhầm API trả số phần tử logic với kích thước bộ nhớ dự trữ**. Chiến lược tăng dung lượng là chi tiết cài đặt của thư viện, không phải lúc nào cũng nhân đôi chính xác.

## 7. Những lỗi thường gặp

1. **Kiểm tra chỉ số bằng `capacity` thay vì `size`.** Điều kiện đúng để truy cập là `0 <= index < size`. Truy cập ô chưa sử dụng có thể đọc dữ liệu cũ hoặc sai hợp đồng của cấu trúc.
2. **Cho rằng cấp phát thêm chỗ đồng nghĩa tạo thêm phần tử.** Sau `reserve(100)`, `size` có thể vẫn bằng 0.
3. **Cho rằng xóa phần tử sẽ giải phóng vùng lưu trữ ngay.** Nhiều mảng động giữ nguyên `capacity` để tái sử dụng; giải phóng vùng dự trữ là quyết định riêng.
4. **Dùng giá trị `0`/`null` làm dấu hiệu ô trống mà không có quy ước rõ ràng.** Giá trị đó có thể là dữ liệu hợp lệ.
5. **Nghĩ rằng thêm cuối luôn mất O(1) trong trường hợp xấu nhất.** Lần thêm gây cấp phát lại vẫn có thể mất O(n).

## 8. Tự kiểm tra

**Tình huống 1.** Một mảng động có `size = 4`, `capacity = 8`. Có bao nhiêu chỉ số hợp lệ? Có thể thêm mấy phần tử ở cuối trước khi *bắt buộc* mở rộng, nếu không có thao tác khác?

**Đáp án:** Có bốn chỉ số hợp lệ: `0, 1, 2, 3`. Có thể thêm bốn phần tử nữa trước khi phải mở rộng ở lần thêm tiếp theo.

**Tình huống 2.** Một mảng động vừa xóa ba phần tử, từ `size = 7` còn `size = 4`, còn `capacity = 12`. Cấu trúc có sai không?

**Đáp án:** Không. Điều kiện `0 <= 4 <= 12` vẫn đúng. Việc xóa không bắt buộc giảm dung lượng đã cấp phát.

**Tình huống 3.** Sau khi gọi thao tác dành sẵn chỗ cho 50 phần tử, một mảng đang rỗng có được đọc phần tử tại chỉ số `0` không?

**Đáp án:** Không. Dành sẵn chỗ chỉ ảnh hưởng `capacity`; mảng vẫn có `size = 0` và chưa có chỉ số hợp lệ nào.

**Tình huống 4.** Tại sao có lần `append` mất O(n), nhưng `append` vẫn được gọi là O(1) khấu hao?

**Đáp án:** Vì chỉ một số ít lần thêm phải cấp phát và sao chép; với chiến lược tăng dung lượng theo hệ số, tổng chi phí của nhiều lần thêm là O(n), tương ứng O(1) khấu hao cho mỗi lần.

Khi đọc hoặc tự cài đặt bất kỳ mảng động nào, hãy luôn kiểm tra **`size` xác định phần dữ liệu có thể sử dụng**, còn **`capacity` xác định phần bộ nhớ đã chuẩn bị để phục vụ tăng trưởng**. Hai giá trị cùng tồn tại vì mảng động cần cân bằng giữa tốc độ thao tác và mức sử dụng bộ nhớ.
