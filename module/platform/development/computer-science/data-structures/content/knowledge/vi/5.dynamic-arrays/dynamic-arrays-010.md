# Mất hiệu lực của con trỏ, tham chiếu hoặc bộ duyệt sau cấp phát lại

Mảng động (*dynamic array*) cho phép lưu phần tử liên tiếp, truy cập theo chỉ số nhanh và tăng số phần tử khi cần. Nhưng khi bộ đệm đầy, cấu trúc có thể phải **cấp phát vùng lưu trữ mới và chuyển các phần tử cũ**. Những giá trị dùng để chỉ trực tiếp tới phần tử trong vùng nhớ cũ, như **con trỏ** (*pointer*), **tham chiếu** (*reference*) hoặc **bộ duyệt** (*iterator*), có thể trở nên **mất hiệu lực** (*invalidated*).

Đây là một vấn đề quan trọng khi lập trình với mảng động, đặc biệt là `std::vector` trong C++. Dữ liệu có thể vẫn được giữ nguyên về giá trị và thứ tự, nhưng một con trỏ từng hợp lệ không nhất thiết còn trỏ tới phần tử đó. Sử dụng lại nó có thể gây **hành vi không xác định** (*undefined behavior*).

Bài học giải thích nguyên nhân, chỉ rõ các quy tắc mất hiệu lực của `std::vector` khi thêm, chèn, xóa, đặt trước dung lượng hoặc thu gọn, rồi giới thiệu cách thiết kế mã an toàn và phân biệt với cách quản lý tham chiếu trong Java, Python.

## 1. Vì sao thay bộ đệm có thể làm mất hiệu lực vị trí cũ?

Một mảng động thường được biểu diễn bằng:

| Thành phần | Ý nghĩa |
| --- | --- |
| `buffer` | Vùng chứa các ô lưu trữ liên tiếp |
| `size` | Số phần tử logic đang có |
| `capacity` | Số ô của bộ đệm đang được cấp phát |

Bất biến là `0 <= size <= capacity`. Khi `size < capacity`, thêm cuối có thể ghi vào ô trống ngay sau phần tử cuối. Khi `size == capacity`, mảng động cần tăng sức chứa để thêm tiếp.

Xét mảng chứa `[10, 20, 30]` với `size = capacity = 3`. Giả sử một biến `p` đang trỏ vào ô chứa `20`:

```text
Trước khi thêm 40:

buffer cũ (vùng A):     +------+------+------+
                       |  10  |  20  |  30  |
                       +------+------+------+
                                 ^
                                 p
size = 3, capacity = 3

Sau khi cấp phát vùng B lớn hơn và sao chép:

buffer mới (vùng B):    +------+------+------+------+------+------+
                       |  10  |  20  |  30  |  40  |  ?   |  ?   |
                       +------+------+------+------+------+------+

buffer cũ (vùng A):    không còn là nơi lưu các phần tử hợp lệ
                       p vẫn mang địa chỉ cũ và đã mất hiệu lực

size = 4, capacity = 6
```

Giá trị `20` vẫn tồn tại ở **chỉ số logic 1** của mảng mới, nhưng địa chỉ vùng nhớ chứa nó đã thay đổi. Không thể dựa vào con trỏ, tham chiếu hoặc iterator đã lấy từ bộ đệm cũ để tiếp tục đọc phần tử.

**Mất hiệu lực không đồng nghĩa phần tử bị xóa khỏi danh sách.** Nó có nghĩa là *cách truy cập cũ* không còn được phép sử dụng. Đọc hoặc ghi qua một con trỏ/tham chiếu/iterator đã mất hiệu lực trong C++ là lỗi nghiêm trọng ngay cả khi chương trình tình cờ chạy đúng trong một lần thử.

### Ba khái niệm cần phân biệt

| Khái niệm | Ví dụ C++ | Ý nghĩa |
| --- | --- | --- |
| Chỉ số (*index*) | `std::size_t i = 1;` | Vị trí logic đếm từ đầu mảng; không lưu địa chỉ vật lý |
| Con trỏ/tham chiếu (*pointer/reference*) | `int* p = &v[1];` hoặc `int& r = v[1];` | Gắn với phần tử đang tồn tại tại một vị trí lưu trữ |
| Bộ duyệt (*iterator*) | `auto it = v.begin() + 1;` | Đối tượng hỗ trợ duyệt/truy cập phần tử theo giao diện của container |

Sau **cấp phát lại mà không chèn/xóa phần tử cũ**, các giá trị thường vẫn giữ nguyên thứ tự chỉ số `0, 1, 2, ...`. Nhưng một con trỏ hoặc iterator đang gắn với **vùng lưu trữ cũ** không tự được chuyển sang vùng mới.

## 2. Ví dụ C++: con trỏ cũ trở thành không hợp lệ

Ví dụ dưới đây **không cố truy cập con trỏ sau khi nó mất hiệu lực**. Thay vào đó, chương trình lấy lại con trỏ mới từ vector sau khi gọi `reserve`.

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{10, 20, 30};

    std::size_t index = 1;
    int* oldPointer = &values[index];
    std::cout << "Truoc: " << *oldPointer << "\n"; // 20

    // Yeu cau capacity lon hon capacity hien tai:
    // neu thanh cong, reserve bat buoc cap phat lai.
    std::size_t requestedCapacity = values.capacity() + 1;
    values.reserve(requestedCapacity);

    // oldPointer da mat hieu luc; TUYET DOI khong giai tham chieu.
    // std::cout << *oldPointer;  // SAI: undefined behavior

    int* newPointer = &values[index]; // Lay lai tu buffer moi
    std::cout << "Sau: " << *newPointer << "\n";  // 20
    std::cout << "Size: " << values.size() << "\n"; // 3
}
```

Lời gọi `reserve` trong ví dụ yêu cầu sức chứa lớn hơn `capacity()` hiện tại, nên nếu thành công sẽ làm `std::vector` cấp phát lại. `size()` vẫn bằng 3 vì `reserve` chỉ đặt trước chỗ chứa; việc tạo vùng mới không tự thêm phần tử logic.

Ví dụ dùng `values.capacity() + 1` với một vector nhỏ để thể hiện điều kiện cần cấp phát; mã sản xuất phải xét trường hợp vượt `max_size()` hoặc tràn số khi tính dung lượng mong muốn. Một lần cấp phát thất bại có thể ném ngoại lệ.

## 3. Những thao tác nào làm mất hiệu lực trong `std::vector`?

Không phải mọi thao tác thay đổi mảng đều gây cấp phát lại, và **không phải chỉ khi cấp phát lại mới có iterator mất hiệu lực**. Quy tắc phụ thuộc vào thao tác, việc bộ đệm có đổi chỗ hay không, và vị trí phần tử được chèn/xóa.

| Thao tác trên `std::vector` | Khi nào cấp phát lại? | Con trỏ/tham chiếu/iterator nào mất hiệu lực? |
| --- | --- | --- |
| `reserve(k)` | Khi `k > capacity()` và lời gọi thành công | Nếu cấp phát lại: **tất cả**, kể cả iterator `end()`; nếu không: không cái nào |
| `push_back(x)` / `emplace_back(...)` | Khi không còn sức chứa | Nếu cấp phát lại: **tất cả**; nếu không: iterator `end()` cũ mất hiệu lực, các iterator/tham chiếu trỏ đến phần tử cũ vẫn hợp lệ |
| `insert(pos, x)` / `emplace(pos, ...)` | Có thể xảy ra khi cần thêm chỗ | Nếu cấp phát lại: **tất cả**; nếu không: các iterator/tham chiếu **tại hoặc sau vị trí chèn**, gồm `end()` cũ, mất hiệu lực |
| `erase(pos)` / `erase(first, last)` | Bản thân thao tác xóa không làm `capacity()` giảm | Các iterator/tham chiếu **tại hoặc sau vị trí bị xóa**, gồm `end()` cũ, mất hiệu lực |
| `pop_back()` | Không tự làm giảm `capacity()` | Tham chiếu/iterator đến phần tử bị xóa và iterator `end()` cũ mất hiệu lực |
| `resize(k)` với `k` lớn hơn `size()` | Có thể khi vượt sức chứa | Nếu cấp phát lại: **tất cả**; nếu không: iterator `end()` cũ mất hiệu lực |
| `resize(k)` với `k` nhỏ hơn `size()` | Không cấp phát lại để giảm số phần tử | Tham chiếu/iterator tới phần tử bị loại và `end()` cũ mất hiệu lực |
| `clear()` | Không thay đổi `capacity()` | Mọi iterator/tham chiếu đến phần tử đã bị xóa và `end()` cũ mất hiệu lực |
| `shrink_to_fit()` | Là yêu cầu thu gọn không bắt buộc | Nếu thực sự cấp phát lại: **tất cả**; nếu không: không mất hiệu lực do lời gọi đó |

Các quy tắc trên áp dụng cho `std::vector` thông thường. Một số kiểu đặc biệt như `std::vector<bool>` có cách biểu diễn phần tử khác và không nên dùng để suy ra con trỏ `bool*` như một vector thông thường.

### Trường hợp quan trọng: thêm cuối khi vẫn còn chỗ

Giả sử đã gọi `reserve(8)` trước, sau đó vector chỉ có ba phần tử:

```cpp
std::vector<int> v{10, 20, 30};
v.reserve(8);           // Co the cap phat lai o DAY

int& first = v[0];      // Lay tham chieu SAU reserve
auto it = v.begin() + 1;
auto oldEnd = v.end();

v.push_back(40);        // size 3 -> 4, capacity >= 8: khong realloc

// first va it van tham chieu den cac phan tu cu hop le.
// oldEnd da mat hieu luc; khong su dung no nua.
int a = first;          // 10
int b = *it;            // 20
```

Ngay cả khi bộ đệm không đổi chỗ, iterator `end()` biểu diễn vị trí **ngay sau phần tử cuối**. Khi thêm một phần tử, vị trí kết thúc của dãy thay đổi; vì vậy **`end()` cũ mất hiệu lực**. Đây là lỗi phổ biến khi lưu `auto finish = v.end()` rồi tiếp tục thay đổi kích thước vector trong vòng lặp.

### Trường hợp chèn giữa dù không cấp phát lại

Nếu vector đang có `[A, B, C, D]` và đủ sức chứa, chèn `X` vào chỉ số 1 sẽ dịch `B, C, D` sang phải:

```text
Trước chèn: [A][B][C][D][ ][ ]
             0  1  2  3

Sau chèn:  [A][X][B][C][D][ ]
             0  1  2  3  4
```

Tham chiếu/iterator tới `A` (trước điểm chèn) vẫn có thể hợp lệ khi không cấp phát lại. Những tham chiếu/iterator từng trỏ tới `B, C, D` ở hoặc sau điểm chèn **đều mất hiệu lực theo hợp đồng `std::vector`**, mặc dù các ô lưu trữ vẫn nằm trong cùng bộ đệm. Không được dùng lại các iterator đó rồi cho rằng chúng “tự chuyển sang chỉ số mới”.

Tương tự, khi xóa ở giữa, các phần tử phía sau bị dồn về trái; iterator ở điểm xóa và phía sau không còn hợp lệ. Những quy tắc này thuộc **hiệu lực của đối tượng truy cập**, không thể suy ra chỉ từ việc `capacity()` có thay đổi hay không.

## 4. Dùng chỉ số để xác định lại phần tử sau cấp phát

Nếu thao tác chỉ là mở rộng ở cuối và **giữ nguyên thứ tự các phần tử cũ**, chỉ số là cách đơn giản để tìm lại phần tử.

```cpp
#include <cstddef>
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{10, 20, 30};
    std::size_t selectedIndex = 1;

    // Khong giu iterator/con tro qua thao tac co the realloc.
    values.push_back(40);
    values.push_back(50);
    values.push_back(60);

    if (selectedIndex < values.size()) {
        std::cout << values[selectedIndex] << "\n"; // 20
    }
}
```

Chỉ số `1` vẫn chỉ đến giá trị `20` trong ví dụ vì các thao tác chỉ **thêm cuối**. Không có thao tác nào chèn hoặc xóa trước phần tử đã chọn.

**Giới hạn của cách dùng chỉ số:** sau khi chèn hoặc xóa ở trước một phần tử, chỉ số của phần tử đó có thể thay đổi. Ví dụ:

```text
Trước:            [10, 20, 30]        20 ở chỉ số 1
insert(0, 5):     [ 5, 10, 20, 30]    20 ở chỉ số 2
erase(0):         [10, 20, 30]        20 trở lại chỉ số 1
```

Vì vậy, **chỉ số tránh phụ thuộc địa chỉ vật lý**, nhưng **không phải định danh vĩnh viễn của phần tử**. Nếu ứng dụng cần theo dõi một đối tượng qua cả các thao tác chèn/xóa, nên dùng một mã định danh ổn định, bảng ánh xạ `id -> vị trí` được cập nhật khi dữ liệu thay đổi, hoặc cấu trúc dữ liệu có đặc tính ổn định tham chiếu phù hợp.

## 5. Lấy lại iterator và dùng iterator do thao tác trả về

C++ cung cấp các thao tác trả về iterator mới để chương trình tiếp tục duyệt an toàn sau khi thay đổi vector:

- `insert(pos, value)` trả về iterator hợp lệ trỏ tới phần tử được chèn.
- `erase(pos)` trả về iterator hợp lệ trỏ tới phần tử đứng sau phần tử bị xóa, hoặc `end()` nếu không còn phần tử nào sau đó.

Ví dụ:

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> v{10, 20, 30};

    auto it = v.begin() + 1;  // Tro vao 20
    it = v.insert(it, 15);    // Lay lai iterator cho phan tu 15
    std::cout << *it << "\n"; // 15

    it = v.erase(it);         // Lay iterator moi, tro vao 20
    if (it != v.end()) {
        std::cout << *it << "\n"; // 20
    }
}
```

Không dùng lại iterator cũ **sau** lời gọi chèn/xóa; việc gán `it = v.insert(...)` hoặc `it = v.erase(...)` sử dụng ngay giá trị trả về hợp lệ để tiếp tục.

Khi duyệt và đồng thời xóa phần tử thỏa điều kiện, có thể cập nhật iterator như sau:

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4, 5, 6};

    for (auto it = v.begin(); it != v.end(); ) {
        if (*it % 2 == 0) {
            it = v.erase(it);  // Khong ++it them trong nhanh nay
        } else {
            ++it;
        }
    }

    for (int x : v) {
        std::cout << x << ' ';
    }
    // 1 3 5
}
```

Ở nhánh xóa, `erase` đã trả về vị trí cần xét tiếp. Nếu vừa nhận iterator trả về vừa tăng thêm một lần, chương trình có thể bỏ qua phần tử kế tiếp. Ngược lại, nếu dùng iterator đã bị xóa để tăng hoặc so sánh, chương trình có thể rơi vào hành vi không xác định.

## 6. Dành sẵn dung lượng để giảm việc cấp phát lại

Khi biết sẽ thêm `m` phần tử vào một vector đang có `s` phần tử, có thể gọi `reserve(s + m)` **một lần trước chuỗi thêm** để giảm khả năng cấp phát lại trong chuỗi đó:

```cpp
#include <vector>

void appendBatch(std::vector<int>& values,
                 const std::vector<int>& incoming) {
    // Minh hoa khi tong khong vuot gioi han kich thuoc.
    values.reserve(values.size() + incoming.size());

    for (int x : incoming) {
        values.push_back(x);
    }
}
```

Nếu `reserve` thành công và lượng thêm không vượt chỗ đã đặt, các lần `push_back` tiếp theo không cần cấp phát lại. Tuy nhiên:

1. **Chính lời gọi `reserve` có thể làm mất hiệu lực tất cả con trỏ, tham chiếu và iterator hiện có.** Vì vậy phải lấy chúng lại sau `reserve`.
2. **`push_back` vẫn làm iterator `end()` cũ mất hiệu lực**, ngay cả khi không cấp phát lại.
3. **`reserve` không ngăn mất hiệu lực do chèn/xóa giữa mảng**; các thao tác đó vẫn dịch chuyển phần tử.
4. `reserve` có thể phải cấp phát và sao chép O(`s`) phần tử cũ. Nó giúp giảm số lần cấp phát trong tương lai nhưng không phải thao tác miễn phí.

Không nên gọi `reserve(size() + 1)` trước **mọi lần** thêm. Cách này có thể ép vector tăng dung lượng từng ô và phá chính sách tăng trưởng hiệu quả của thư viện, gây tổng công sao chép lớn.

Ngoài ra, việc tính `values.size() + incoming.size()` phải được kiểm tra để tránh tràn số và vượt `values.max_size()` trong mã sản xuất.

### Khi thật sự cần địa chỉ của đối tượng ổn định

Một lựa chọn là lưu **con trỏ sở hữu đến các đối tượng được cấp phát riêng**, ví dụ `std::vector<std::unique_ptr<T>>`. Khi bộ đệm vector chứa `unique_ptr` được chuyển sang nơi khác, bản thân các `unique_ptr` có thể được di chuyển, nhưng những đối tượng `T` được chúng sở hữu vẫn nằm ở vùng cấp phát riêng.

```cpp
#include <memory>
#include <vector>

struct Item {
    int value;
};

int main() {
    std::vector<std::unique_ptr<Item>> items;
    items.push_back(std::make_unique<Item>(Item{42}));

    Item* selected = items[0].get();
    items.reserve(100); // Co the realloc vector unique_ptr

    // Doi tuong Item van o cho cu, mien la chua bi huy/thay the.
    selected->value = 99;
}
```

Điều này **không** làm iterator hay tham chiếu đến **các phần tử `unique_ptr` trong vector** trở nên ổn định; chúng vẫn chịu quy tắc mất hiệu lực của `std::vector`. Cũng không bảo đảm `selected` tiếp tục hợp lệ nếu `Item` đã bị hủy, phần tử sở hữu bị xóa hoặc thay thế. Lựa chọn lưu đối tượng riêng có chi phí cấp phát và truy cập gián tiếp, nên chỉ dùng khi nhu cầu ổn định địa chỉ thực sự đáng giá.

## 7. Phân biệt với Java và Python

Khái niệm “mất hiệu lực của con trỏ” ở C++ **không chuyển nguyên xi** sang các ngôn ngữ có mô hình bộ nhớ khác.

### Java: tham chiếu đối tượng và `ArrayList.Iterator`

Java `ArrayList` cũng có bộ đệm bên trong và có thể cấp phát lại khi tăng số phần tử. Tuy nhiên, biến Java tham chiếu tới **đối tượng**, không phải một con trỏ mà người dùng lấy trực tiếp tới ô trong bộ đệm nội bộ của `ArrayList`.

```java
import java.util.ArrayList;
import java.util.Iterator;

public class JavaArrayListReferences {
    static final class Person {
        String name;
        Person(String name) { this.name = name; }
    }

    public static void main(String[] args) {
        ArrayList<Person> people = new ArrayList<>();
        Person selected = new Person("An");
        people.add(selected);

        people.ensureCapacity(100); // Co the thay mang nen noi bo
        people.add(new Person("Binh"));
        System.out.println(selected.name); // An: doi tuong van ton tai

        Iterator<Person> it = people.iterator();
        people.add(new Person("Chi")); // Sua doi cau truc sau khi tao iterator
        // it.next() co the nem ConcurrentModificationException.
        // Khong su dung iterator cu de tiep tuc duyet.
    }
}
```

Việc `ArrayList` thay mảng tham chiếu bên trong **không tự di chuyển hoặc hủy các đối tượng `Person`**. Biến `selected` vẫn tham chiếu tới đối tượng đó. Ngược lại, `Iterator` của `ArrayList` là iterator **fail-fast**: khi phát hiện sửa đổi cấu trúc không thông qua iterator theo cách được cho phép, nó thường ném `ConcurrentModificationException`. Cơ chế fail-fast là **nỗ lực phát hiện lỗi** (*best effort*), không phải bảo đảm đồng bộ hay công cụ điều khiển truy cập đồng thời.

Nếu muốn xóa phần tử trong lúc duyệt `ArrayList` bằng iterator, có thể dùng `Iterator.remove()` theo hợp đồng API, hoặc dùng `removeIf(...)` trong trường hợp phù hợp, thay vì sửa `ArrayList` tùy ý trong vòng lặp đang dùng iterator.

### Python: danh sách, đối tượng và thay đổi khi duyệt

Python `list` cũng thường lưu các tham chiếu tới đối tượng trong một vùng có thể mở rộng. Khi list cấp phát lại bộ đệm nội bộ, một biến Python giữ đối tượng đã lấy từ danh sách **không trở thành con trỏ treo như con trỏ `T*` tới ô của `std::vector<T>`**.

Tuy nhiên, thay đổi danh sách **trong khi đang duyệt** có thể khiến phần tử bị bỏ qua, xuất hiện thêm trong lượt duyệt hoặc thay đổi ý nghĩa chỉ số, tùy kiểu thao tác. Cách an toàn khi cần biến đổi danh sách là tạo một danh sách kết quả:

```python
values = [1, 2, 3, 4, 5, 6]
values = [x for x in values if x % 2 != 0]
print(values)  # [1, 3, 5]
```

Với trường hợp phải sửa đối tượng đang được tham chiếu, cần phân biệt **biến trỏ tới đối tượng** với **vị trí phần tử trong danh sách**. Đối tượng có thể vẫn sống dù bị loại khỏi danh sách, nhưng một chỉ số đã lưu không mặc nhiên tiếp tục chỉ đến cùng đối tượng sau các thao tác chèn/xóa.

| Nội dung | C++ `std::vector<T>` | Java `ArrayList<T>` | Python `list` |
| --- | --- | --- | --- |
| Có thể thay bộ đệm khi thêm | Có | Có | Có, phụ thuộc cài đặt |
| Có thể trực tiếp giữ con trỏ/tham chiếu đến phần tử trong bộ đệm | Có với vector thông thường | Không qua API `ArrayList` công khai | Không qua API `list` thông thường |
| Thay bộ đệm làm mất hiệu lực con trỏ đến ô lưu trữ | Có | Không áp dụng theo cách dùng tham chiếu Java | Không áp dụng theo cách dùng biến Python |
| Sửa đổi trong khi dùng iterator | Tuân theo quy tắc invalidation; dùng sai có thể là UB | Iterator fail-fast thường phát hiện sửa đổi cấu trúc | Có thể làm thay đổi kết quả duyệt, không có quy tắc fail-fast giống `ArrayList` |

## 8. Mất hiệu lực ảnh hưởng gì đến tính đúng đắn và hiệu năng?

Về độ phức tạp, việc thêm cuối mảng động theo chính sách tăng dung lượng hình học có chi phí **O(1) khấu hao**, nhưng một lần mở rộng có thể sao chép O(n) phần tử. **Phân tích thời gian không nói rằng các địa chỉ cũ vẫn hợp lệ.**

Tương tự, việc đặt trước đủ sức chứa có thể giảm lần cấp phát lại, nhưng không giải quyết mọi kiểu mất hiệu lực khi chèn/xóa. Khi lựa chọn cấu trúc dữ liệu, cần xem xét đồng thời:

| Nhu cầu | Tác động đến lựa chọn |
| --- | --- |
| Truy cập nhanh theo chỉ số, thêm chủ yếu ở cuối | Mảng động thường thích hợp |
| Có thể lấy lại vị trí sau khi mở rộng | Dùng chỉ số và lấy lại con trỏ/iterator khi cần |
| Cần giữ iterator qua chèn/xóa nhiều lần | Phải kiểm tra quy tắc của container; có thể cần cấu trúc khác |
| Cần địa chỉ đối tượng ổn định | Cân nhắc cấp phát đối tượng riêng hoặc container có bảo đảm ổn định phù hợp |
| Cần độ trễ ổn định cho từng lần thêm | Phải xét chi phí O(n) tại đợt cấp phát lại, không chỉ O(1) khấu hao |

Ví dụ, `std::list` có thể giữ ổn định iterator/tham chiếu tới các phần tử **không bị xóa** qua nhiều thao tác chèn/xóa, nhưng đánh đổi bằng việc không có truy cập theo chỉ số O(1) và cần bộ nhớ cho liên kết giữa các nút. Không có cấu trúc nào tốt nhất cho mọi loại thao tác.

## 9. Những lỗi dễ gặp

1. **Tiếp tục giải tham chiếu con trỏ cũ sau `push_back` khi vector đã đầy.** Lần thêm có thể cấp phát lại toàn bộ bộ đệm, làm con trỏ cũ mất hiệu lực.
2. **Tin rằng không cấp phát lại thì mọi iterator đều hợp lệ.** `end()` cũ mất hiệu lực sau `push_back`; iterator tại hoặc sau vị trí chèn/xóa cũng có thể mất hiệu lực dù `capacity` không đổi.
3. **Lưu `v.end()` rồi thêm phần tử trong vòng lặp.** Vị trí kết thúc thay đổi; phải tính lại `end()` đúng lúc theo quy tắc container.
4. **Cho rằng giá trị địa chỉ tình cờ trông giống nhau nghĩa là iterator hợp lệ.** Việc sử dụng đối tượng truy cập đã bị invalidation không trở thành hợp lệ chỉ vì thử nghiệm không lỗi.
5. **Lấy `&v[0]` khi vector rỗng.** `v[0]` không hợp lệ nếu `size() == 0`; phải kiểm tra kích thước trước khi lấy địa chỉ phần tử.
6. **Giữ một chỉ số qua các thao tác chèn/xóa rồi giả định nó vẫn đại diện cho cùng phần tử.** Chỉ số có thể thay đổi ý nghĩa khi các phần tử phía trước bị dịch chuyển.
7. **Dùng iterator đã bị `erase` làm mất hiệu lực để tăng hoặc so sánh.** Với `std::vector`, hãy tiếp tục từ iterator do `erase` trả về.
8. **Coi biến Java/Python trỏ tới đối tượng là con trỏ vào ô bộ đệm như C++.** Mô hình quản lý đối tượng khác nhau; phải áp dụng quy tắc của ngôn ngữ và API cụ thể.
9. **Cho rằng `reserve` chỉ cải thiện tốc độ và không ảnh hưởng quyền truy cập đang giữ.** Nếu `reserve` cấp phát lại, toàn bộ iterator, con trỏ và tham chiếu vào phần tử vector cũ đều mất hiệu lực.

## 10. Tự kiểm tra

**Câu 1.** Vector C++ có `size() = capacity() = 4`. Lấy `int* p = &v[1]` rồi `push_back(50)` thành công. Có được dùng `*p` để đọc phần tử thứ hai không?

**Đáp án:** Không. Vector đã đầy trước khi thêm, nên `push_back` cần cấp phát lại và `p` mất hiệu lực. Hãy dùng `v[1]` hoặc lấy con trỏ mới sau thao tác.

**Câu 2.** Vector đã `reserve(20)` thành công, hiện có năm phần tử. Nếu `push_back` thêm phần tử thứ sáu, con trỏ đến phần tử đầu có còn hợp lệ không? `end()` cũ thì sao?

**Đáp án:** Vì đủ sức chứa và `push_back` không cấp phát lại, con trỏ tới phần tử đầu vẫn hợp lệ. Nhưng iterator `end()` cũ mất hiệu lực.

**Câu 3.** Một vector có dư chỗ và iterator `it` trỏ đến phần tử ở chỉ số 3. Chèn phần tử tại chỉ số 1 mà không cấp phát lại. Có được dùng `it` để truy cập phần tử cũ không?

**Đáp án:** Không. `it` nằm sau vị trí chèn nên mất hiệu lực. Phải lấy lại iterator hoặc tìm lại phần tử theo chỉ số/định danh đã cập nhật.

**Câu 4.** Sau khi `std::vector::reserve(k)` với `k <= capacity()`, các iterator tới phần tử hiện có có bị mất hiệu lực vì lời gọi `reserve` đó không?

**Đáp án:** Không. `reserve` không cấp phát lại trong trường hợp này và không làm mất hiệu lực iterator do chính lời gọi đó.

**Câu 5.** Trong vòng lặp C++, sau khi xóa một phần tử bằng `v.erase(it)`, nên cập nhật `it` thế nào?

**Đáp án:** Gán `it = v.erase(it)` để lấy iterator hợp lệ trỏ tới phần tử tiếp theo hoặc `v.end()`. Không tiếp tục dùng iterator cũ đã bị xóa.

**Câu 6.** Sau khi mở rộng vector chỉ bằng `push_back`, vì sao chỉ số `1` vẫn có thể tìm lại phần tử cũ, trong khi con trỏ tới `v[1]` có thể mất hiệu lực?

**Đáp án:** `push_back` giữ nguyên thứ tự và chỉ số logic của các phần tử cũ, nhưng cấp phát lại có thể chuyển chúng sang địa chỉ bộ nhớ khác. Chỉ số không gắn với vùng nhớ cũ.

**Câu 7.** Tại sao lưu `std::unique_ptr<Item>` trong vector đôi khi giúp giữ địa chỉ `Item` ổn định qua việc mở rộng bộ đệm?

**Đáp án:** Vector chứa các `unique_ptr`, còn đối tượng `Item` được cấp phát ở vùng nhớ riêng. Di chuyển `unique_ptr` khi vector cấp phát lại không di chuyển đối tượng nó sở hữu. Tuy nhiên, nếu đối tượng bị hủy hoặc quyền sở hữu thay đổi khiến nó bị hủy, con trỏ tới `Item` vẫn mất hiệu lực.

**Câu 8.** Với Java `ArrayList<Person>`, một biến `Person p` lấy từ danh sách có tự trở thành tham chiếu treo khi `ArrayList` tăng dung lượng nội bộ không?

**Đáp án:** Không. `p` tham chiếu tới đối tượng `Person`, còn `ArrayList` giữ các tham chiếu trong mảng nội bộ. Nhưng iterator của `ArrayList` có quy tắc riêng khi cấu trúc bị sửa đổi.

**Câu 9.** Nếu cần giữ một phần tử được chọn qua các lần chèn/xóa ở đầu vector, chỉ lưu chỉ số có đủ không?

**Đáp án:** Không. Chèn/xóa phía trước làm thay đổi chỉ số của phần tử đó. Cần cập nhật chỉ số theo thao tác hoặc dùng định danh ổn định để tìm lại phần tử.

**Điểm ghi nhớ:** Sau khi mảng động cấp phát lại, **dữ liệu logic có thể còn nguyên nhưng con trỏ, tham chiếu và iterator gắn với bộ đệm cũ không còn hợp lệ**. Với `std::vector`, cả thao tác chèn/xóa không cấp phát lại cũng có các quy tắc invalidation theo vị trí. Muốn an toàn, hãy lấy lại iterator sau thay đổi, dùng các iterator do API trả về, hoặc lưu chỉ số/định danh kèm theo việc cập nhật khi cấu trúc thay đổi.
