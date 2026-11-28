# Bộ duyệt và điều kiện làm mất hiệu lực khi cấu trúc thay đổi

Một vòng lặp bắt đầu duyệt danh sách, lấy được phần tử đầu tiên, rồi xóa chính phần tử ấy. Bộ duyệt đang giữ còn hợp lệ không? Trong một mảng động, nếu `push_back` làm cấp phát lại vùng chứa, con trỏ đang trỏ tới phần tử thứ ba có tiếp tục dùng được không? Với bảng băm, tại sao `rehash` có thể làm bộ duyệt cũ vô hiệu dù khóa–giá trị vẫn tồn tại?

Đây là câu hỏi về **bộ duyệt (iterator/cursor)** và **điều kiện làm mất hiệu lực (invalidation)**. Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, thuộc chương **Bộ nhớ và biểu diễn**, hiểu bộ duyệt giúp cài đặt và sử dụng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị mà vẫn giữ **bất biến, an toàn vòng đời, độ phức tạp thời gian và bộ nhớ**.

Bài học tập trung vào ba nguyên tắc:

1. Bộ duyệt là **một cách ghi nhớ vị trí hoặc trạng thái duyệt**, không phải lời bảo đảm phần tử sẽ tồn tại mãi.
2. **Mỗi kiểu cấu trúc và mỗi thao tác** có hợp đồng khác nhau về bộ duyệt, con trỏ và tham chiếu nào còn hợp lệ.
3. Khi có thay đổi cấu trúc, chương trình phải **lấy lại vị trí hợp lệ, sử dụng API xóa phù hợp, hoặc thiết kế chính sách duyệt rõ ràng**, thay vì dùng lại bộ duyệt cũ theo trực giác.

## 1. Bộ duyệt là gì và chứa thông tin nào?

**Bộ duyệt** là đối tượng hoặc trạng thái cho phép lần lượt truy cập các phần tử của cấu trúc mà không cần biết toàn bộ cách lưu trữ bên trong.

Một giao diện trừu tượng thường có các ý niệm:

- `begin`: vị trí phần tử đầu tiên nếu có.
- `end`: vị trí **sau phần tử cuối**, hoặc ký hiệu kết thúc; không phải phần tử dữ liệu.
- `dereference`: lấy phần tử tại vị trí hợp lệ đang trỏ tới dữ liệu.
- `advance/next`: chuyển tới vị trí tiếp theo.
- `equals`: kiểm tra hai vị trí có tương đương theo hợp đồng của iterator hay không.

Trong C++, `std::vector<int>::iterator`, `std::list<int>::iterator`, `std::map<...>::iterator` đều cho phép duyệt, nhưng cấu trúc lưu vị trí và quy tắc mất hiệu lực rất khác nhau.

### 1.1. Ba cách lưu vị trí thông dụng

```text
(a) Mảng liên tiếp, iterator có thể hành xử như con trỏ/vị trí:
    data: [10][20][30][40]
                ^
             vị trí 1

(b) Danh sách liên kết, iterator có thể mang con trỏ nút:
    head ---> [10] ---> [20] ---> [30] ---> NULL
                         ^
                      nút hiện tại

(c) Bảng băm, iterator có thể mang trạng thái dò bucket/nút:
    buckets:  0       1       2       3
             ---    [K,V]    ---    [K,V]
                       ^
                 vị trí duyệt
```

Đây chỉ là **mô hình khái niệm**. Tiêu chuẩn thư viện thường quy định hành vi của iterator, không bắt buộc một biểu diễn vật lý cụ thể. Iterator có thể là con trỏ, chỉ số, đối tượng chứa nhiều trường hoặc một bộ duyệt sinh giá trị theo nhu cầu.

### 1.2. Vị trí hợp lệ khác với vị trí được phép đọc

Một iterator bằng `end()` có thể là một **vị trí kết thúc hợp lệ để so sánh**, nhưng **không được giải tham chiếu** như phần tử.

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{10, 20, 30};

    for (auto it = values.begin(); it != values.end(); ++it) {
        std::cout << *it << " ";
    }
    // Không đọc *values.end(): end không trỏ tới phần tử dữ liệu.
}
```

Với container rỗng, `begin() == end()` và vòng lặp không chạy. Trạng thái “không có phần tử” nên được biểu diễn bằng hợp đồng `end`/`has_next` hoặc kết quả tùy chọn, không phải bằng cách đọc giá trị từ một vùng giả định.

### 1.3. Vị trí duyệt, tham chiếu phần tử và quyền sở hữu

Ba đối tượng cần phân biệt:

| Khái niệm | Nó đại diện cho điều gì? | Rủi ro sau thay đổi |
| --- | --- | --- |
| **Iterator/cursor** | Vị trí hoặc trạng thái đang duyệt | Có thể không xác định được vị trí tiếp theo, hoặc bị invalidation |
| **Reference/pointer đến phần tử** | Đường truy cập tới đối tượng phần tử | Có thể bị treo khi vùng lưu trữ dời hoặc đối tượng bị xóa |
| **Handle/ID logic** | Định danh được API quản lý | Có thể còn hợp lệ, bị thay ID hoặc bị tái sử dụng tùy hợp đồng |
| **Owner/container** | Thành phần quản lý phần tử và tài nguyên | Có trách nhiệm duy trì bất biến, vòng đời và API thao tác |

Một iterator **không nhất thiết sở hữu** phần tử; giữ iterator không kéo dài vòng đời của phần tử theo một quy tắc chung. Một ID logic có thể được tra cứu lại sau thay đổi, nhưng phải kiểm tra xem nó có còn định danh cùng đối tượng không.

## 2. “Mất hiệu lực” có thể diễn ra theo nhiều cách

**Iterator invalidation** xảy ra khi một thao tác làm cho iterator trước đó không còn được sử dụng theo hợp đồng như trước.

Có những nguyên nhân khác nhau:

1. **Đối tượng bị xóa:** nút hoặc phần tử đích kết thúc vòng đời.
2. **Vùng chứa bị dời:** mảng động cấp phát vùng mới; địa chỉ cũ không còn là đường truy cập hợp lệ.
3. **Phần tử bị dịch vị trí:** chèn/xóa trong mảng làm các phần tử phía sau đổi vị trí logic; iterator ở vùng bị ảnh hưởng mất hiệu lực theo container.
4. **Tái tổ chức bảng:** `rehash` thay cách duyệt bucket; iterator cũ mất hiệu lực dù các phần tử vẫn còn sống.
5. **Metadata duyệt trở nên cũ:** phiên bản cấu trúc, số phần tử, liên kết hoặc ngăn xếp duyệt không còn tương ứng trạng thái hiện tại.
6. **Container bị hủy hoặc chuyển quyền:** iterator mượn dữ liệu từ container có thể hết hợp lệ khi chủ sở hữu hủy hoặc chuyển vùng theo quy tắc của kiểu.

### 2.1. Vẫn nhìn thấy địa chỉ không có nghĩa còn hợp lệ

```text
Tại t1:
vector buffer A: [10][20][30]
                    ^
                  ptr

Tại t2: vector tăng capacity và cấp phát lại:
buffer A: đã bị thu hồi
buffer B: [10][20][30][...][...]
            ^
          vùng mới

ptr cũ không tự trỏ sang buffer B.
```

Giá trị con trỏ cũ có thể trông quen thuộc trong debugger, nhưng sau khi vùng lưu trữ bị vô hiệu hóa, không được giải tham chiếu nó. Tương tự, một con trỏ nút trong danh sách có thể trở thành con trỏ treo sau `erase`.

### 2.2. Thay đổi nội dung chưa chắc là thay đổi cấu trúc

Sửa **giá trị phần tử đang tồn tại** không nhất thiết làm iterator mất hiệu lực. Ví dụ, với `std::vector<int>`, phép gán `values[1] = 42` không tự cấp phát lại, không thay kích thước và không làm iterator hợp lệ đang trỏ đến phần tử biến mất.

Nhưng nếu đang duyệt một **cây tìm kiếm** mà bên ngoài đổi trực tiếp **khóa dùng để sắp thứ tự**, cấu trúc có thể mất bất biến BST dù địa chỉ nút không đổi. Với bảng băm, sửa khóa ảnh hưởng hash/equality có thể phá phép tra cứu mà không nhất thiết tạo ra lỗi bộ nhớ.

Vì vậy **iterator còn hợp lệ về bộ nhớ** và **thuật toán vẫn đúng về ngữ nghĩa** là hai điều kiện khác nhau.

### 2.3. Vô hiệu hóa không phải lúc nào là “lỗi ngay tại dòng sửa”

Ví dụ `erase` trên vector là thao tác hợp lệ. Lỗi xảy ra nếu **sau đó** mã sử dụng một iterator/tham chiếu bị vô hiệu hóa, hoặc dùng vị trí logic cũ như thể chưa có phần tử nào dịch chuyển.

Lập luận đúng gồm hai bước:

- Thao tác thay đổi cấu trúc nào vừa xảy ra?
- Hợp đồng cụ thể của nó nói **đường truy cập nào không còn hợp lệ**?

## 3. Mảng động và `std::vector`: tăng capacity là điểm quan trọng

Mảng động thường lưu phần tử liên tiếp trong một vùng bộ nhớ. Khi có đủ `capacity`, thêm phần tử cuối có thể không cần dời vùng. Khi không đủ, container cấp vùng lớn hơn, chuyển/copy phần tử rồi thu hồi vùng cũ.

```text
Trước:
size = 3, capacity = 3
     +----+----+----+
     | 10 | 20 | 30 |
     +----+----+----+
            ^
          saved_it

Sau push_back(40) cần tăng capacity:
     +----+----+----+----+----+----+
     | 10 | 20 | 30 | 40 |    |    |
     +----+----+----+----+----+----+
     vùng mới: saved_it không hợp lệ
```

Trong C++, `std::vector` có các quy tắc invalidation được xác định cụ thể.

### 3.1. Bảng quy tắc quan trọng của `std::vector<T>`

| Thao tác | Điều kiện | Iterator/tham chiếu mất hiệu lực |
| --- | --- | --- |
| `push_back` / `emplace_back` | Có cấp phát lại | **Tất cả** iterator, con trỏ, tham chiếu tới phần tử, kể cả `end` cũ |
| `push_back` / `emplace_back` | Không cấp phát lại | Iterator/tham chiếu tới phần tử cũ vẫn hợp lệ; **`end` cũ** bị vô hiệu |
| `insert` / `emplace` | Có cấp phát lại | **Tất cả** |
| `insert` / `emplace` | Không cấp phát lại | Iterator/tham chiếu **tại và sau** vị trí chèn, kể cả `end` cũ |
| `erase` | Xóa phần tử hoặc đoạn | Iterator/tham chiếu **tại và sau** vị trí xóa, kể cả `end` cũ |
| `reserve(n)` | `n > capacity()` nên cấp phát lại | **Tất cả** |
| `reserve(n)` | `n <= capacity()` | Không bị vô hiệu chỉ do `reserve` |
| `clear()` | Xóa tất cả phần tử | Iterator/tham chiếu tới phần tử đã bị xóa; `end` cũ cũng không được giữ dùng như trước |
| `operator[]` để gán giá trị | Vị trí hợp lệ, không có thay đổi cấu trúc khác | Không tự gây invalidation |

Bảng nói về **quy tắc của `std::vector`**, không áp dụng nguyên xi cho `std::deque`, `std::list` hay một vector tùy biến. Với kiểu phần tử có tham chiếu nội bộ, bản thân thao tác move/copy còn có các yêu cầu về vòng đời và bất biến riêng.

### 3.2. Ví dụ sai: giữ con trỏ rồi làm vector tăng dung lượng

```cpp
#include <vector>

int main() {
    std::vector<int> values{10, 20};
    values.shrink_to_fit(); // Không bảo đảm kết quả capacity cụ thể.

    int *first = values.data();

    values.reserve(values.capacity() + 10); // Buộc cần tăng capacity.

    // std::cout << *first;  // SAI: first đã bị vô hiệu.
    // Lấy lại đường truy cập nếu vẫn cần:
    int current_first = values[0];
    (void)current_first;
}
```

Chú ý `shrink_to_fit` chỉ là yêu cầu không bắt buộc; tính an toàn của ví dụ không dựa vào việc nó có thu nhỏ thành công hay không. Lệnh `reserve(values.capacity() + 10)` yêu cầu dung lượng lớn hơn trước, nên khi thành công sẽ làm cấp phát lại vùng phần tử. Không dùng `first` sau đó.

### 3.3. Ví dụ đúng: xóa có điều kiện bằng iterator do `erase` trả về

Sai lầm thường gặp là:

```cpp
/* SAI: sau erase, it cũ không còn được dùng để ++.
for (auto it = values.begin(); it != values.end(); ++it) {
    if (*it % 2 == 0) {
        values.erase(it);
    }
}
*/
```

Với vector, `erase` trả về iterator tới phần tử **đứng ngay sau phần bị xóa trong trạng thái mới**, hoặc `end()` nếu không còn phần tử nào. Dùng iterator trả về và chỉ tăng ở nhánh không xóa:

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{1, 2, 3, 4, 5, 6};

    for (auto it = values.begin(); it != values.end();) {
        if (*it % 2 == 0) {
            it = values.erase(it); // Nhận iterator hợp lệ của trạng thái mới.
        } else {
            ++it;
        }
    }

    for (int value : values) {
        std::cout << value << " "; // 1 3 5
    }
}
```

Không tăng thêm `it` sau nhánh xóa; nếu làm vậy, có thể bỏ qua phần tử ngay sau vị trí vừa xóa.

**Chi phí:** xóa một phần tử giữa vector thường cần dịch các phần tử còn lại, O(n) xấu nhất. Vòng lặp xóa lần lượt nhiều phần tử bằng `erase` có thể đạt **O(n²)** tổng thời gian vì dịch lặp nhiều lần.

Nếu chỉ cần giữ các phần tử thỏa điều kiện và không phụ thuộc địa chỉ phần tử, có thể dùng thuật toán lọc tập trung. Với C++20:

```cpp
#include <algorithm>
#include <vector>

int main() {
    std::vector<int> values{1, 2, 3, 4, 5, 6};

    std::erase_if(values, [](int x) {
        return x % 2 == 0;
    });

    // values == {1, 3, 5}; duyệt/lọc thường tuyến tính về số phần tử.
}
```

`std::erase_if` thao tác trực tiếp trên container và vẫn có các quy tắc invalidation liên quan đến phần tử bị xóa/di chuyển. **Không giữ iterator cũ rồi giả định nó hợp lệ chỉ vì đã thay bằng thuật toán O(n).**

### 3.4. Chỉ số không đồng nghĩa định danh bền vững

Thay con trỏ bằng **chỉ số** giúp tránh một số lỗi do dời vùng: sau khi vector cấp phát lại, `values[2]` vẫn truy cập vị trí thứ ba **nếu vị trí ấy còn tồn tại**. Tuy nhiên, chèn trước phần tử làm chỉ số logic của phần tử đó tăng; xóa trước phần tử làm chỉ số giảm.

```text
Ban đầu:  [A][B][C]       lưu index = 1 để chỉ B
Chèn X:   [X][A][B][C]    index = 1 giờ là A

Địa chỉ và chỉ số là hai kiểu handle khác nhau;
cả hai đều cần hợp đồng về thao tác làm thay đổi cấu trúc.
```

Nếu ứng dụng cần định danh không đổi theo chèn/xóa, cân nhắc **ID riêng hoặc handle có phiên bản** thay vì lưu chỉ số từ một danh sách có thể sắp xếp lại.

## 4. Danh sách liên kết: nút còn sống thường ổn định địa chỉ

Khác với vector, mỗi nút danh sách liên kết thường nằm ở vùng riêng. Chèn nút mới không yêu cầu dời mọi nút đã có. Vì thế với `std::list` trong C++:

- Chèn phần tử không làm mất hiệu lực iterator và tham chiếu tới phần tử đang tồn tại.
- Xóa phần tử chỉ làm mất hiệu lực iterator và tham chiếu tới **những phần tử bị xóa**.
- Iterator tới các phần tử **khác** vẫn hợp lệ; nhưng cần nhớ nội dung/quan hệ hàng xóm có thể thay đổi.

### 4.1. Ví dụ C++: chèn nút mới không làm mất iterator nút cũ

```cpp
#include <iostream>
#include <iterator>
#include <list>

int main() {
    std::list<int> values{10, 20, 30};
    auto it20 = std::next(values.begin()); // Phần tử 20.

    values.push_front(5); // Chèn nút mới, it20 vẫn hợp lệ.
    std::cout << *it20 << "\n"; // 20

    values.erase(it20);   // Xóa chính nút 20.
    // Không được giải tham chiếu hay ++it20 sau khi xóa.
}
```

`std::forward_list` là danh sách liên kết đơn của C++ với API `before_begin` và `erase_after`; nó trả iterator phù hợp sau xóa. Hợp đồng chính xác vẫn phải xem theo container thay vì dùng phương pháp xóa vector một cách máy móc.

### 4.2. Ví dụ C: xóa nút khi đang duyệt mà không dùng sau `free`

Trong C không có iterator chuẩn cho danh sách do ta tự thiết kế. Con trỏ nút hiện tại đóng vai trò cursor. Với danh sách đơn, dùng **con trỏ tới ô liên kết** để xóa mọi nút có giá trị âm mà không phải đọc nút sau khi giải phóng.

```c
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

typedef struct List {
    Node *head;
    size_t size;
} List;

void list_clear(List *list) {
    if (list == NULL) return;

    Node *cur = list->head;
    while (cur != NULL) {
        Node *next = cur->next; // Lưu khi cur còn sống.
        free(cur);
        cur = next;
    }

    list->head = NULL;
    list->size = 0;
}

/* Xóa mọi nút có value < 0; không có chu trình, list sở hữu các nút. */
void erase_negative(List *list) {
    if (list == NULL) return;

    Node **link = &list->head;

    while (*link != NULL) {
        Node *cur = *link;         // Nút còn sống.

        if (cur->value < 0) {
            *link = cur->next;     // Nối lại trước khi giải phóng.
            --list->size;
            free(cur);
            // Không đọc cur nữa. link vẫn trỏ tới ô hợp lệ.
        } else {
            link = &cur->next;     // Giữ nút, chuyển sang ô next của nó.
        }
    }
}

int main(void) {
    /* List sở hữu các nút cấp phát động; mảng data chỉ chứa giá trị. */
    int data[] = {1, -2, -3, 4};
    List list = {NULL, 0};
    Node **tail_link = &list.head;

    for (size_t i = 0; i < 4; ++i) {
        Node *node = malloc(sizeof *node);
        if (node == NULL) {
            list_clear(&list);
            return EXIT_FAILURE;
        }
        node->value = data[i];
        node->next = NULL;

        *tail_link = node;
        tail_link = &node->next;
        ++list.size;
    }

    erase_negative(&list);

    for (Node *p = list.head; p != NULL; p = p->next) {
        printf("%d ", p->value);  // 1 4
    }
    puts("");

    list_clear(&list);
    return EXIT_SUCCESS;
}
```

Trong ví dụ, các nút thuộc `List` đều được cấp phát bằng `malloc`; mảng `data` chỉ cung cấp giá trị `int` và có thời hạn lưu trữ tự động. Hàm `list_clear` giải phóng các nút do danh sách sở hữu, không giải phóng mảng `data`.

**Bất biến của vòng lặp `erase_negative`:**

1. `link` trỏ tới một ô con trỏ còn hợp lệ, là `list.head` hoặc `next` của **một nút đang sống** được giữ lại.
2. `*link` là nút tiếp theo chưa xử lý hoặc `NULL`.
3. Sau khi xóa nút âm, `*link` đã được cập nhật sang nút kế tiếp trước khi `free(cur)`.
4. Không truy cập lại `cur` sau khi giải phóng, không đi qua một `next` thuộc nút đã chết.

Với `n` nút, vòng lặp thăm mỗi nút một lần: **O(n)** thời gian và **O(1)** bộ nhớ phụ trợ (ngoài vùng chứa nút). Hàm không tự an toàn nếu một luồng khác đồng thời sửa/xóa nút.

### 4.3. Đường duyệt ổn định không có nghĩa container cho phép xóa tùy ý

Một con trỏ tới nút có thể ổn định khi thêm nút mới, nhưng nếu API giữ `tail`, `size`, liên kết `prev` hoặc ánh xạ từ ID sang nút, phép xóa phải **cập nhật toàn bộ bất biến**. Với một danh sách đôi, xóa nút thường cần nối đúng hai láng giềng; với danh sách đơn, cần biết nút trước hoặc ô con trỏ dẫn tới nút.

Nếu danh sách chia sẻ nút giữa nhiều container, giải phóng một nút có thể làm **mọi** đường mượn từ các container còn lại thành dangling. Bất biến quyền sở hữu phải được xác định trước.

## 5. Cây tìm kiếm và bảng băm: cùng thao tác chèn, quy tắc duyệt khác nhau

### 5.1. `std::map` và `std::set`: node-based ordered containers

Các container có thứ tự `std::map` và `std::set` quản lý phần tử theo cấu trúc nút phù hợp với hợp đồng thứ tự. Đối với hai container này:

- `insert` và `emplace` **không làm mất hiệu lực** iterator/tham chiếu tới các phần tử hiện có.
- `erase` làm mất hiệu lực iterator/tham chiếu tới phần tử **bị xóa**, không phải toàn bộ những phần tử khác.
- `clear` xóa mọi phần tử, nên mọi iterator tới phần tử cũ không còn hợp lệ.
- Việc duyệt theo khóa là một tính chất của container; không tự sửa khóa đang nằm trong `std::map`/`std::set` qua iterator.

```cpp
#include <iostream>
#include <map>

int main() {
    std::map<int, int> scores{{10, 100}, {30, 300}};
    auto it = scores.find(30);

    scores.emplace(20, 200); // Iterator it tới 30 vẫn hợp lệ.
    std::cout << it->second << "\n"; // 300

    scores.erase(10);        // Không xóa phần tử 30.
    std::cout << it->first << "\n";  // 30

    scores.erase(it);        // Iterator it giờ bị invalidation.
    // Không dùng lại it sau erase.
}
```

Ngay cả khi một hiện thực cây cân bằng phải **quay cây (rotation)** khi chèn/xóa, iterator tới những nút không bị xóa vẫn hợp lệ theo hợp đồng của `std::map`. Không được tự suy luận rằng “cây thay đổi hình dạng ⇒ mọi con trỏ nút đều mất hiệu lực”.

Tuy vậy, đối với **bộ duyệt cây do chính ta cài** bằng một ngăn xếp các tổ tiên hoặc bộ chỉ số con, việc quay/chuyển liên kết trong khi duyệt có thể khiến **trạng thái duyệt logic** trở nên cũ. Cần có hợp đồng riêng, không mặc định bộ duyệt tùy biến có bảo đảm như `std::map`.

### 5.2. `std::unordered_map` và `std::unordered_set`: rehash đổi đường duyệt

Trong bảng băm kiểu `std::unordered_map`:

- `insert`/`emplace` có thể kích hoạt **rehash** để tăng bucket.
- Nếu **không rehash**, insert thường không làm mất hiệu lực iterator tới mục cũ theo hợp đồng.
- Nếu **rehash**, **mọi iterator** hiện có bị vô hiệu hóa; thứ tự duyệt bucket có thể thay đổi.
- **Con trỏ và tham chiếu tới các phần tử còn sống** không bị vô hiệu hóa chỉ vì rehash; chúng chỉ mất hiệu lực khi phần tử tương ứng bị xóa theo hợp đồng.
- `erase` làm mất hiệu lực iterator/tham chiếu tới phần tử đã xóa.

Sự khác nhau giữa **iterator** và **reference** đặc biệt quan trọng tại đây.

```cpp
#include <iostream>
#include <unordered_map>

int main() {
    std::unordered_map<int, int> lookup{{1, 10}, {2, 20}};

    auto saved_it = lookup.find(1);
    int& saved_value = saved_it->second;

    lookup.rehash(lookup.bucket_count() * 2 + 1);
    // saved_it KHÔNG được dùng sau rehash.
    // Tham chiếu saved_value tới phần tử 1 vẫn hợp lệ,
    // vì phần tử đó chưa bị xóa.

    std::cout << saved_value << "\n";       // 10
    std::cout << lookup.find(1)->second;    // 10

    lookup.erase(1);
    // Từ đây saved_value đã trở thành tham chiếu không hợp lệ.
}
```

**Phân tích:** `rehash` có thể xây lại phân bố bucket mà không hủy chính các đối tượng phần tử. Tham chiếu tới phần tử còn sống có thể giữ được, trong khi iterator cần thông tin thứ tự/đường duyệt cũ phải bị bỏ.

Bởi vậy, không được gom mọi hiện tượng thành một quy tắc “thay cấu trúc là mọi đường truy cập đều chết”. Cần hỏi **đối tượng đích còn sống không, vị trí duyệt có đổi không, và hợp đồng API cho phép gì**.

### 5.3. Điều kiện làm mất hiệu lực có thể được quyết định bởi load factor

Trong bảng băm, việc chèn có thể vẫn giữ bucket hiện tại hoặc kích hoạt rehash tùy số phần tử, số bucket, load factor tối đa và cài đặt. Vì vậy một đoạn mã chạy an toàn ở tập dữ liệu nhỏ chưa chứng minh iterator sẽ hợp lệ khi bảng lớn lên.

Nếu đang duyệt mà cần chèn mục mới vào `unordered_map` và tiếp tục dùng iterator cũ, cần:

- Bảo đảm theo hợp đồng rằng không có rehash; hoặc
- Tách thao tác chèn và thao tác duyệt; hoặc
- Lưu khóa/ID để tra cứu lại sau khi chèn; hoặc
- Dùng container/chiến lược khác có bảo đảm ổn định iterator theo workload.

Dù dự phòng bucket với `reserve` có thể giảm số lần rehash, bản thân `reserve` cũng có thể làm các iterator hiện tại mất hiệu lực nếu thực hiện rehash.


## 6. `std::deque`, chuỗi ký tự và các container adapter

Đừng suy từ tên “sequence container” rằng mọi container có cùng quy tắc invalidation.

### 6.1. `std::deque` khác vector ở hai đầu

`std::deque` thường được tổ chức bằng các khối lưu trữ và metadata liên kết khối; chuẩn không buộc một biểu diễn vật lý duy nhất. Nó hỗ trợ truy cập chỉ số O(1) và thêm/xóa ở **hai đầu** có hiệu quả, nhưng không có bảo đảm iterator giống `std::list`.

Các quy tắc cần nhớ khi sử dụng `std::deque` trong C++:

- Chèn ở **đầu hoặc cuối** làm **các iterator hiện tại mất hiệu lực**; tham chiếu tới các phần tử đang tồn tại vẫn hợp lệ theo hợp đồng của thao tác này.
- Chèn vào **giữa** có thể làm mất hiệu lực cả iterator **và tham chiếu** tới các phần tử.
- Xóa ở **đầu hoặc cuối** có quy tắc invalidation nhẹ hơn với các phần tử không bị xóa, nhưng `end()` cũ có những ngoại lệ tùy thao tác; **không giữ end iterator cũ theo trực giác**.
- Xóa ở **giữa** làm các iterator/tham chiếu tới phần tử bị ảnh hưởng mất hiệu lực theo quy tắc của container.

Vì vậy, dù `deque.push_back` thường không phải dời mọi phần tử như vector, điều đó **không đồng nghĩa iterator cũ an toàn**. Một tham chiếu tới phần tử có thể còn hợp lệ trong khi **iterator** đã mất hiệu lực; đây là khác biệt cần học từ hợp đồng chứ không đoán từ cách bố trí bộ nhớ.

### 6.2. `std::string` và `std::string_view`

`std::string` quản lý vùng ký tự có thể thay đổi. Những thao tác chèn/nối làm thay dung lượng có thể khiến con trỏ/iterator vào chuỗi mất hiệu lực; tối ưu *small-string optimization* có thể làm dữ liệu thay đổi chỗ theo cách không hiển nhiên.

`std::string_view` chỉ nhìn vào vùng ký tự: nó không tự kéo dài vòng đời của `std::string` nguồn. Nếu nguồn bị hủy hoặc thay đổi khiến vùng ký tự bị vô hiệu, view cũng không còn được dùng.

```cpp
#include <string>
#include <string_view>

int main() {
    std::string text = "data";
    std::string_view view(text);

    text += std::string(1000, 'x'); // Có thể dời vùng ký tự.
    // Không mặc định view vẫn còn hợp lệ sau khi text dời vùng.
    (void)view;
}
```

Ngay cả khi con trỏ vật lý vẫn hợp lệ trong một thao tác cụ thể, thay đổi nội dung mà view đang quan sát có thể ảnh hưởng tính đúng đắn của thuật toán; cần xác định yêu cầu **snapshot** hay **live view**.

### 6.3. Stack, queue, priority queue có thể không lộ iterator

Các container adapter C++ như `std::stack`, `std::queue` và `std::priority_queue` chủ yếu cung cấp `push`, `pop`, `top`/`front`/`back`, `empty` và `size`, chứ không cung cấp giao diện duyệt iterator công khai theo cách `std::vector` hoặc `std::list` làm.

Điều đó không loại trừ rủi ro về **tham chiếu tới phần tử**:

- Lưu tham chiếu từ `top()` hoặc `front()` rồi `pop()` có thể làm tham chiếu tới phần tử vừa xóa mất hiệu lực.
- Nếu adapter dùng một container nền có quy tắc reallocation, các thao tác thêm có thể ảnh hưởng tới tham chiếu vào phần tử nền.
- Với `priority_queue`, thao tác push/pop có thể đổi vị trí và thứ tự phần tử để duy trì heap; không được coi một “vị trí trước đây là phần tử X” như ID bền vững.

Khi cần duyệt toàn bộ queue/heap, hãy cân nhắc **tách bài toán đọc** khỏi **API thao tác chuẩn của adapter**, chẳng hạn tạo bản sao nếu phù hợp hoặc chọn container khác có API duyệt đã được định nghĩa.

## 7. Duyệt trong Python: iterator không nhất thiết là snapshot

Trong Python, vòng `for` lấy một iterator từ đối tượng. Việc **sửa container trong lúc duyệt** phụ thuộc loại container và thao tác.

### 7.1. List: thay đổi kích thước có thể làm bỏ sót phần tử

```python
items = [1, 2, 3, 4, 5]

for item in items:
    items.remove(item)

print(items)  # [2, 4]
```

Vòng lặp không xóa hết phần tử như nhiều người mong đợi. Khi xóa phần tử đầu, những phần tử sau dịch trái; iterator list tiếp tục tiến theo vị trí và bỏ qua một số phần tử vừa dịch lên.

**Không dựa vào việc list không ném ngoại lệ** để kết luận thao tác là đúng. Có trường hợp duyệt vẫn chạy và cho kết quả sai âm thầm.

Cách giải quyết 1 — tạo danh sách kết quả:

```python
items = [1, 2, 3, 4, 5]
items = [x for x in items if x % 2 == 0]
print(items)  # [2, 4]
```

Đây là **gán lại tên `items`** sang một list mới. Nếu có tên khác đang trỏ đến list cũ, nó vẫn trỏ đến list cũ.

Cách giải quyết 2 — sửa nội dung list gốc bằng slice assignment khi cần giữ danh tính container:

```python
items = [1, 2, 3, 4, 5]
alias = items

items[:] = [x for x in items if x % 2 == 0]

print(items)          # [2, 4]
print(alias)          # [2, 4]
print(alias is items) # True
```

Bộ duyệt đang hoạt động đồng thời trên list gốc vẫn không nên bị dùng xuyên qua thao tác thay đổi kích thước này. Slice assignment chỉ giúp **giữ danh tính container cho những alias khác**, không biến cập nhật cấu trúc thành một phép an toàn cho mọi iterator đang chạy.

### 7.2. Snapshot nông để duyệt, thay đổi container thật

Nếu cần duyệt tập phần tử ban đầu trong khi cập nhật container, có thể tạo một snapshot nông:

```python
items = [1, 2, 3, 4, 5, 6]

for value in items[:]:
    if value % 2 == 0:
        items.remove(value)

print(items)  # [1, 3, 5]
```

`items[:]` tạo một list ngoài khác, nên việc `remove` trên `items` không đổi **độ dài của list snapshot** đang được duyệt. Nhưng:

- Phần tử là object mutable có thể vẫn được chia sẻ giữa hai list.
- `remove(value)` tìm phần tử bằng phép so sánh, có thể xóa lần xuất hiện đầu và tốn O(n).
- Với nhiều giá trị trùng nhau hoặc cần xóa theo danh tính/chỉ số, nên chọn thuật toán phù hợp thay vì dùng mẫu này vô điều kiện.

Vì vậy, nếu mục tiêu chỉ là lọc theo điều kiện, list comprehension thường đơn giản và có độ phức tạp tốt hơn việc lặp nhiều `remove`.

### 7.3. Dictionary và set: sửa kích thước trong khi duyệt

Trong các hiện thực Python thông dụng, thay đổi **kích thước** dict/set trong lúc đang duyệt có thể làm phát sinh `RuntimeError`. Không dùng việc bắt ngoại lệ này làm giao thức duyệt–cập nhật có chủ đích.

```python
counts = {"A": 1, "B": 0, "C": 3}

# An toàn: duyệt snapshot các khóa, xóa trong dict gốc.
for key in list(counts):
    if counts[key] == 0:
        del counts[key]

print(counts)  # {'A': 1, 'C': 3}
```

Đổi **giá trị** của một khóa đang tồn tại mà không thay tập khóa có thể có quy tắc khác với thêm/xóa khóa. Nhưng nếu thuật toán cần một “ảnh chụp” thống nhất của toàn bộ cặp khóa–giá trị, việc chỉ copy danh sách khóa chưa đủ; phải quyết định cần snapshot nông của mục hay snapshot sâu của dữ liệu.

### 7.4. Generator: dữ liệu nguồn có thể thay đổi giữa các lần `next`

Generator và bộ duyệt lazy có thể giữ trạng thái rồi tạm dừng giữa các lần tạo phần tử. Nếu nguồn bị thay đổi trong thời gian tạm dừng, kết quả có thể phụ thuộc trạng thái mới theo ngữ nghĩa generator.

```python
values = [10, 20, 30]
generator = (x * 2 for x in values)

print(next(generator))  # 20
values.append(40)

# Không coi generator là snapshot của [10, 20, 30].
print(list(generator))  # Các giá trị còn lại theo nguồn đang được duyệt.
```

Trong ví dụ này, iterator của list có thể nhìn thấy mục thêm cuối; nhưng **không nên tổng quát hóa** hành vi sang mọi iterable, query, cursor database hay cấu trúc concurrent. Nếu cần một tập dữ liệu không đổi, tạo snapshot trước hoặc chọn cơ chế phiên bản hóa.

## 8. Java: fail-fast là tín hiệu lỗi, không phải cơ chế đồng bộ

Với `ArrayList`, iterator thường ghi nhận **phiên bản thay đổi cấu trúc**. Khi chương trình thêm/xóa phần tử trực tiếp qua list trong khi iterator đang duyệt, một lần gọi iterator tiếp theo có thể ném `ConcurrentModificationException`.

### 8.1. Ví dụ dễ lỗi

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

class BadIteration {
    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(Arrays.asList(1, 2, 3, 4));

        // Không làm như thế này khi đang duyệt values:
        /*
        for (Integer value : values) {
            if (value % 2 == 0) {
                values.remove(value);
            }
        }
        */
    }
}
```

For-each trong ví dụ đi qua iterator của list. Xóa trực tiếp qua list có thể làm iterator phát hiện cấu trúc đã đổi. **Không nên trông chờ ngoại lệ luôn luôn được ném**: cơ chế fail-fast được tài liệu Java mô tả là kiểm tra **best-effort**, không phải bảo đảm an toàn đồng bộ hay chứng minh mọi trường hợp đều bị phát hiện.

### 8.2. Cách đúng: xóa qua chính iterator

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

class RemoveDuringIteration {
    public static void main(String[] args) {
        List<Integer> values =
                new ArrayList<>(Arrays.asList(1, 2, 3, 4, 5, 6));

        Iterator<Integer> it = values.iterator();

        while (it.hasNext()) {
            int value = it.next();
            if (value % 2 == 0) {
                it.remove(); // Xóa phần tử vừa trả về qua iterator.
            }
        }

        System.out.println(values); // [1, 3, 5]
    }
}
```

`Iterator.remove()` hoạt động theo **hợp đồng của iterator hỗ trợ thao tác này**; không phải mọi iterator đều cho phép xóa. Trong Java, thông thường phải gọi `next()` trước và không gọi `remove()` hai lần cho cùng một lần `next()` nếu chưa bước tiếp, nếu không có thể gặp `IllegalStateException`. Với iterator của cấu trúc không hỗ trợ xóa, có thể gặp `UnsupportedOperationException`.

Một lựa chọn khác khi chỉ lọc bằng điều kiện là API `removeIf` của collection thích hợp, với hợp đồng và chi phí của kiểu cụ thể.

### 8.3. Fail-fast, weakly consistent và snapshot iterator

Các thư viện Java có nhiều mô hình iterator, ví dụ:

| Mô hình | Ý nghĩa khái quát | Điều cần hiểu |
| --- | --- | --- |
| **Fail-fast** | Phát hiện một số thay đổi cấu trúc không được thực hiện qua iterator | Phát hiện best-effort; không thay thế đồng bộ |
| **Weakly consistent** | Có thể tiếp tục duyệt trong khi cấu trúc thay đổi theo hợp đồng concurrent collection | Có thể thấy một phần thay đổi; không nhất thiết là snapshot tại một thời điểm |
| **Snapshot iterator** | Duyệt trên tập phần tử được chụp trước | Chi phí tạo/lưu snapshot; nội dung object bên trong có thể vẫn mutable |

Ví dụ `ConcurrentHashMap` có kiểu duyệt phù hợp cho truy cập đồng thời với ngữ nghĩa *weakly consistent* theo hợp đồng của nó; `CopyOnWriteArrayList` tạo snapshot iterator và đánh đổi chi phí copy khi cập nhật. Không áp đặt quy tắc của `ArrayList` lên mọi collection Java.

## 9. Rust: cơ chế mượn hạn chế nhiều lỗi từ trước khi chạy

Rust có hệ thống ownership và borrowing giúp phát hiện nhiều trường hợp giữ tham chiếu tới `Vec` trong khi muốn thay đổi cấu trúc của chính `Vec`.

```rust
fn main() {
    let mut values = vec![1, 2, 3, 4];

    for item in &values {
        println!("{item}");

        // values.push(*item);
        // Không biên dịch: cố mượn mutable khi lượt duyệt
        // vẫn giữ mượn immutable của values.
    }

    values.retain(|x| x % 2 != 0);
    assert_eq!(values, vec![1, 3]);
}
```

`retain` là API thực hiện lọc phù hợp trên vector, không cần người dùng giữ một tham chiếu phần tử rồi làm vector dời vùng trong lúc vòng `for` còn mượn nó.

Hệ thống kiểu Rust hạn chế nhiều lỗi dangling trong mã an toàn, nhưng **không tự bảo đảm mọi thuật toán logic đều đúng**: ví dụ, một chỉ số được lưu từ trước vẫn có thể trỏ đến **phần tử khác** sau khi chèn/xóa; mã phải kiểm tra giới hạn và ý nghĩa định danh. Các API có interior mutability, concurrent structures và mã `unsafe` còn có những quy tắc riêng cần tuân thủ.

## 10. Duyệt cây và đồ thị khi dữ liệu thay đổi

### 10.1. Duyệt cây tìm kiếm: iterator phụ thuộc thuật toán hiện thực

Với cây nhị phân, duyệt inorder có thể giữ một **stack các nút tổ tiên**:

```text
         8
        / \
       3   12
      / \
     1   6

Stack đang duyệt có thể chứa: [8, 3, 1]
Phần tử hiện tại: 1
```

Nếu thuật toán khác xóa nút `3` hoặc quay lại liên kết của cây ngay lúc stack đang giữ đường cũ, nhiều con trỏ trong stack có thể treo hoặc thứ tự duyệt không còn tương ứng với cấu trúc mới.

Một thư viện `std::map` có bảo đảm iterator theo quy tắc riêng; **bộ duyệt cây thủ công** có thể không đạt bảo đảm tương tự nếu không chủ động thiết kế. Có ít nhất ba chính sách:

1. **Không cho sửa cấu trúc trong lúc duyệt**, bằng hợp đồng API.
2. **Iterator theo định danh nút ổn định**, và hiện thực xử lý thay đổi liên kết một cách nhất quán.
3. **Snapshot phiên bản cây** (hoặc persistent tree dùng structural sharing) để duyệt một phiên bản bất biến.

Chi phí khác nhau: sao chép toàn cây có thể O(n), path copying trong cây cân bằng có thể thêm O(log n) nút cho một thay đổi theo thiết kế, còn khóa toàn bộ thời gian duyệt có thể làm giảm khả năng cập nhật đồng thời.

### 10.2. BFS/DFS: cấu trúc đang duyệt là hai thứ khác nhau

Trong BFS, **queue duyệt** và **đồ thị nguồn** là hai cấu trúc có liên quan nhưng khác nhau. BFS điển hình giữ một queue các ID đỉnh đã phát hiện; khi đồ thị thay đổi, cần hỏi:

- Có cho phép chèn/xóa đỉnh trong khi BFS đang chạy không?
- Một ID đã nằm trong queue có thể bị xóa trước khi được xử lý không?
- Một adjacency vector có thể cấp phát lại khi có cạnh mới, khiến iterator vào danh sách hàng xóm cũ mất hiệu lực không?
- Một cạnh mới xuất hiện sau khi BFS đã xử lý đỉnh nguồn có cần được duyệt không?
- Nếu nhiều đường dẫn đến cùng đỉnh, tập `visited` có dùng ID ổn định hay con trỏ nút có thể bị hủy?

```text
Đồ thị tại t1:
A ----> B ----> C

BFS đang duyệt A; queue = [B]

Tại t2:
Xóa đỉnh B khỏi đồ thị.

Tại t3:
BFS lấy ID B ra từ queue.

Nếu API không định nghĩa cách xử lý ID B đã bị xóa,
BFS có thể truy cập nhầm dữ liệu hoặc cho kết quả không nhất quán.
```

### 10.3. Snapshot adjacency để có ngữ nghĩa rõ ràng

Một ví dụ Python đọc snapshot **các đỉnh và danh sách kề** trước khi bắt đầu BFS:

```python
from collections import deque

def bfs_snapshot(graph, start):
    """
    graph: dict[vertex, list[vertex]]
    Đỉnh trong khóa được xem là tập đỉnh hợp lệ.
    Không dùng các list/khóa đang bị sửa đồng thời trong lúc tạo snapshot.
    """
    adjacency = {v: tuple(neighbors)
                 for v, neighbors in graph.items()}

    if start not in adjacency:
        return []

    seen = {start}
    queue = deque([start])
    order = []

    while queue:
        vertex = queue.popleft()
        order.append(vertex)

        for neighbor in adjacency[vertex]:
            if neighbor not in adjacency:
                continue  # Chính sách ví dụ: bỏ cạnh tới đỉnh không tồn tại.
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)

    return order


graph = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": [],
    "D": [],
}

print(bfs_snapshot(graph, "A"))  # ['A', 'B', 'C', 'D']
```

Hàm tạo bản sao **cấu trúc ngoài** (dict và tuple kề) rồi BFS trên dữ liệu ấy. Nếu ID đỉnh là giá trị bất biến như chuỗi, snapshot đủ ổn định cho ví dụ. Nếu các ID là đối tượng mutable với hash/equality thay đổi, hoặc graph đang bị sửa bởi luồng khác **ngay trong lúc snapshot được tạo**, còn cần cơ chế đồng bộ hoặc thiết kế bất biến dữ liệu để lấy được một ảnh chụp nhất quán.

**Độ phức tạp:** với `V` đỉnh và `E` cạnh trong biểu diễn adjacency list, tạo snapshot và BFS thường O(V+E) thời gian, O(V+E) dung lượng snapshot, thêm O(V) cho queue/seen trong kịch bản đơn giản. Đổi lại, những thay đổi trên graph gốc **sau khi snapshot hoàn thành** không làm iterator đang duyệt snapshot mất hiệu lực.

### 10.4. Graph CSR và iterator theo đoạn mảng

Với CSR, danh sách hàng xóm của đỉnh `v` là đoạn `edges[offsets[v] ... offsets[v+1])`. Nếu mảng `edges` được xây lại hoặc một thao tác làm thay đổi `offsets`, iterator/con trỏ vào đoạn cũ có thể mất hiệu lực hoặc vẫn còn địa chỉ nhưng mô tả một tập cạnh không còn đúng.

Vì CSR thường phù hợp cho **đồ thị tương đối tĩnh**, một chiến lược hợp lý là xây CSR một lần, giữ bất biến khi chạy các thuật toán duyệt, và nếu cần cập nhật thì xây một phiên bản mới rồi chuyển giao có kiểm soát. Với đồ thị cập nhật liên tục, adjacency lists hoặc cấu trúc động khác có thể dễ duy trì hơn.

**Điểm cốt lõi:** độ phức tạp BFS O(V+E) được chứng minh cho một đồ thị **có ngữ nghĩa cố định trong lượt duyệt**. Nếu cạnh/đỉnh thay đổi trong lúc thuật toán chạy, trước hết phải định nghĩa kết quả mong muốn rồi mới phân tích độ phức tạp và tính đúng đắn.


## 11. Thiết kế iterator tự cài: đếm phiên bản để phát hiện thay đổi

Khi tự cài cấu trúc dữ liệu, có thể thiết kế **fail-fast iterator** theo cách bảo thủ: mọi thao tác thay đổi cấu trúc sẽ tăng bộ đếm phiên bản của container; iterator giữ phiên bản lúc tạo và từ chối duyệt nếu phiên bản hiện tại khác.

### 11.1. Bất biến của iterator theo phiên bản

Giả sử mảng động hoặc buffer có:

- `size`: số phần tử logic.
- `version`: phiên bản thay đổi cấu trúc.
- Iterator có `index`, `expected_version` và tham chiếu mượn tới container.

Hợp đồng:

1. Khi tạo iterator: `expected_version = container.version`.
2. Mỗi lần `next`: kiểm tra container còn sống, rồi kiểm tra phiên bản.
3. Nếu hai phiên bản khác nhau: trả **STALE**, không truy cập phần tử bằng chỉ số cũ.
4. Nếu phiên bản khớp và `index == size`: trả **END**.
5. Nếu còn dữ liệu: trả phần tử tại `index` rồi tăng `index`.
6. Mọi `push/erase/clear/reorder` làm thay đổi cấu trúc phải tăng phiên bản theo chính sách đã chọn.

Trạng thái kết quả **STALE** khác **END**: một bên nghĩa là “cấu trúc đã thay đổi và iterator không còn được dùng”, bên kia nghĩa là “đã duyệt hết theo cấu trúc hợp lệ”.

### 11.2. Mã C minh họa đầy đủ

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

enum { CAPACITY = 8 };

typedef struct Buffer {
    int values[CAPACITY];
    size_t size;
    unsigned long version;
} Buffer;

typedef struct Cursor {
    const Buffer *owner;       /* Mượn, không sở hữu. */
    size_t index;
    unsigned long expected_version;
} Cursor;

typedef enum CursorResult {
    CURSOR_ITEM,
    CURSOR_END,
    CURSOR_STALE
} CursorResult;

void buffer_init(Buffer *buffer) {
    if (buffer == NULL) return;
    buffer->size = 0;
    buffer->version = 0;
}

bool buffer_push(Buffer *buffer, int value) {
    if (buffer == NULL || buffer->size >= CAPACITY) return false;

    buffer->values[buffer->size] = value;
    ++buffer->size;
    ++buffer->version;         /* Cấu trúc đã đổi, dù không realloc. */
    return true;
}

Cursor cursor_begin(const Buffer *buffer) {
    Cursor c = {buffer, 0, buffer != NULL ? buffer->version : 0};
    return c;
}

CursorResult cursor_next(Cursor *cursor, int *out) {
    if (cursor == NULL || cursor->owner == NULL) {
        return CURSOR_STALE;
    }

    const Buffer *buffer = cursor->owner;

    if (cursor->expected_version != buffer->version) {
        return CURSOR_STALE; /* Không dùng index cũ. */
    }

    if (cursor->index >= buffer->size) {
        return CURSOR_END;
    }

    if (out != NULL) {
        *out = buffer->values[cursor->index];
    }
    ++cursor->index;
    return CURSOR_ITEM;
}

int main(void) {
    Buffer buffer;
    buffer_init(&buffer);
    buffer_push(&buffer, 10);
    buffer_push(&buffer, 20);

    Cursor cursor = cursor_begin(&buffer);
    int value = 0;

    if (cursor_next(&cursor, &value) == CURSOR_ITEM) {
        printf("%d\n", value); /* 10 */
    }

    buffer_push(&buffer, 30);  /* Iterator cũ bị đánh dấu stale. */

    if (cursor_next(&cursor, &value) == CURSOR_STALE) {
        puts("Iterator khong con hop le");
    }

    cursor = cursor_begin(&buffer); /* Tạo iterator mới. */
    while (cursor_next(&cursor, &value) == CURSOR_ITEM) {
        printf("%d ", value); /* 10 20 30 */
    }
    puts("");
    return 0;
}
```

**Ưu điểm:** thay đổi cấu trúc được phát hiện theo chính sách, không cần cố “đoán” chỉ số cũ còn mang ý nghĩa nào.

**Giới hạn quan trọng:**

- Con trỏ `owner` vẫn là **borrowed pointer**. Nếu container đã hết vòng đời, chỉ riêng việc đọc `buffer->version` cũng có thể là truy cập sai. Bộ đếm phiên bản **không thay thế quản lý vòng đời**.
- Khi `version` quay vòng sau đủ nhiều thay đổi, giá trị cũ có thể trùng lại; hệ thống cần chính sách giới hạn/phiên bản đủ lớn nếu muốn độ tin cậy lâu dài.
- Đây là hiện thực **không thread-safe**. Cả việc đọc `version` lẫn dữ liệu phải được đồng bộ khi có luồng khác ghi; dùng biến không atomic như trong ví dụ mà truy cập đồng thời không khóa có thể gây data race.
- Việc làm stale **mọi** iterator trên bất kỳ `push` nào là **chính sách bảo thủ**. Nó dễ triển khai hơn nhưng kém linh hoạt so với các container bảo đảm iterator ổn định khi chèn.

Với `n` phần tử không có thay đổi, duyệt toàn bộ vẫn O(n), mỗi bước kiểm tra O(1), bộ nhớ riêng mỗi cursor O(1). Thêm trường phiên bản vào container tốn O(1) metadata, không làm dữ liệu tự trở thành bất biến.

### 11.3. Phương án khác: snapshot iterator và iterator sống

| Kiểu iterator | Quan sát dữ liệu nào? | Khi nguồn thay đổi | Chi phí chính |
| --- | --- | --- | --- |
| **Fail-fast** | Trạng thái đang sống, kiểm tra phiên bản | Báo lỗi hoặc dừng nếu phiên bản đổi | Kiểm tra O(1) mỗi bước; cần duy trì version |
| **Live iterator có hợp đồng cập nhật** | Cấu trúc hiện hành | Có thể thấy thay đổi theo quy tắc riêng | Khó xác định ngữ nghĩa khi chèn/xóa |
| **Snapshot iterator** | Bản chụp lúc bắt đầu | Nguồn đổi không đổi thứ tự/danh sách snapshot | Sao chép O(n) nếu snapshot toàn phần |
| **Persistent-version iterator** | Phiên bản bất biến đã lưu | Phiên bản mới tạo không sửa phiên bản cũ | Chi phí phiên bản hóa/structural sharing |
| **Handle-based cursor** | Định danh được kho đối tượng quản lý | Có thể tra lại hoặc phát hiện đã xóa | Metadata tra cứu, generation, policy |

Không tồn tại một API duy nhất tối ưu cho mọi bài toán. Lựa chọn phụ thuộc số lần duyệt, tần suất sửa, kích thước dữ liệu và mức nhất quán mà ứng dụng cần.

## 12. Truy cập đồng thời: iterator hợp lệ còn phụ thuộc đồng bộ

Trong một luồng, ta có thể suy luận theo thứ tự: lấy iterator, cập nhật container, xem quy tắc invalidation rồi sử dụng hoặc bỏ iterator.

Với nhiều luồng, còn có một lớp câu hỏi khác: **có tồn tại data race hay không, và trạng thái nào được quan sát theo mô hình bộ nhớ?**

### 12.1. Không khóa: đừng mặc định iterator đọc được dữ liệu đang sửa

Ví dụ, một luồng `push_back` vào `std::vector` trong lúc luồng khác đang duyệt vector mà không có đồng bộ. Ngay cả khi `capacity` tình cờ còn đủ, việc đọc/ghi `size` và các phần tử có thể vi phạm yêu cầu đồng bộ của chương trình C++.

Một cơ chế fail-fast kiểm tra `version` không tự làm cho mã an toàn đa luồng: luồng ghi có thể sửa dữ liệu **sau khi** iterator kiểm tra phiên bản nhưng **trước khi** iterator đọc phần tử.

### 12.2. Ba chiến lược phổ biến

**(a) Khóa bảo vệ toàn bộ lần duyệt và thao tác sửa**

```text
Thread đọc:
  lock
  duyệt container
  unlock

Thread ghi:
  lock
  chèn/xóa
  unlock
```

Cách này giúp duy trì bất biến nếu tất cả bên tham gia tôn trọng cùng cơ chế khóa. Đổi lại, một lần duyệt O(n) có thể giữ khóa lâu, khiến các thao tác cập nhật phải chờ.

**(b) Tạo snapshot nhất quán dưới khóa, rồi duyệt ngoài khóa**

```text
lock
snapshot = copy(container)
unlock

duyệt(snapshot)
```

Nguồn có thể tiếp tục cập nhật sau khi snapshot hoàn tất. Giá phải trả thường là O(n) thời gian/bộ nhớ cho bản sao toàn phần; snapshot nông còn có thể **chia sẻ các phần tử mutable**, nên phải xác định mức độc lập mong muốn.

**(c) Container concurrent có hợp đồng duyệt riêng**

Một số cấu trúc hỗ trợ *weakly consistent iterator*, versioned snapshot, read-copy-update hoặc thu hồi bộ nhớ an toàn chuyên biệt. Không suy ra các bảo đảm ấy chỉ từ tên “thread-safe”; phải đọc API: có thể thấy phần tử mới không, có thể thấy phần tử đã xóa không, thứ tự có cố định không và khi nào bộ nhớ được thu hồi.

### 12.3. Iterator, đối tượng và thu hồi bộ nhớ là ba rủi ro

Với danh sách lock-free, một thread đọc địa chỉ nút A; thread khác xóa A rồi giải phóng ngay. Việc một phép đọc con trỏ đã hoàn tất không bảo đảm A còn sống khi thread thứ nhất giải tham chiếu. Các kỹ thuật như **hazard pointers**, **epoch-based reclamation**, quản lý ownership theo tham chiếu hoặc khóa phù hợp giải quyết vấn đề **khi nào được phép thu hồi**, không chỉ thứ tự các phép cập nhật liên kết.

Đây là bài toán khác với quy tắc invalidation đơn luồng của `std::list`. Không có container node-based nào tự an toàn khi nhiều luồng xóa và truy cập cùng nút mà không có hợp đồng đồng bộ.

## 13. So sánh nhanh các cấu trúc và tình huống invalidation

Bảng dưới tóm tắt các trường hợp điển hình; **quy tắc thư viện được nêu áp dụng cho các container C++ đã ghi tên**, không phải mọi hiện thực dữ liệu.

| Cấu trúc/cách lưu | Chèn/thêm | Xóa | Điểm cần nhớ khi duyệt |
| --- | --- | --- | --- |
| Mảng cố định C / `std::array` | Không thay kích thước mảng | Không tự xóa vị trí vật lý | Bộ duyệt chỉ còn hợp lệ khi mảng còn sống; cập nhật giá trị không tự dời vùng |
| `std::vector` | Có reallocation: mọi iterator/ref mất hiệu lực; không reallocation: iterator/ref ở hoặc sau chỗ chèn có thể mất | `erase` làm mất iterator/ref tại và sau chỗ xóa | Dùng iterator do `erase` trả về |
| `std::deque` | Thêm đầu/cuối làm iterator mất hiệu lực; tham chiếu phần tử cũ có thể vẫn sống | Phụ thuộc xóa đầu/cuối/giữa | Đừng suy từ ổn định reference sang ổn định iterator |
| `std::list` | Iterator/ref phần tử cũ vẫn hợp lệ | Chỉ phần tử bị xóa mất hiệu lực | Giữ con trỏ tới nút còn sống, nhưng cập nhật đúng `size/next/prev` |
| `std::map` / `std::set` | Không làm mất iterator/ref cũ khi insert | Chỉ phần tử bị xóa mất hiệu lực | Thứ tự theo khóa; không sửa khóa phá bất biến |
| `std::unordered_map` | Rehash làm mọi iterator mất hiệu lực | Iterator/ref tới phần tử bị xóa mất hiệu lực | Tham chiếu tới phần tử còn sống giữ được qua rehash |
| Stack/queue dạng adapter | Phụ thuộc container nền | Pop xóa phần tử đích | API thường không cấp iterator; không giữ reference tới phần tử bị pop |
| Binary heap mảng | Có thể đổi capacity, phần tử sift/hoán đổi vị trí | Xóa đỉnh rồi sift, thay thứ tự | Chỉ số/iterator vào ô không phải ID phần tử |
| Cây tùy biến | Phụ thuộc chiến lược nút và iterator | Con trỏ nút bị xóa treo | Rotation có thể làm cursor stack tổ tiên cũ không còn đúng |
| Đồ thị adjacency list/CSR | Có thể dời vùng kề hoặc cập nhật liên kết | Có thể làm ID/handle cũ hết hiệu lực | Cần định nghĩa snapshot hoặc live traversal |

**Chú thích về vector:** `push_back` không cấp phát lại giữ iterator/tham chiếu tới **phần tử cũ**, nhưng `end()` cũ vẫn mất hiệu lực. `insert` không cấp phát lại làm mất iterator/tham chiếu **từ vị trí chèn trở đi**. Bảng rút gọn không thay thế quy tắc chi tiết ở Mục 3.

**Chú thích về deque:** trường hợp xóa ở giữa có thể làm mất hiệu lực **toàn bộ** iterator/tham chiếu theo hợp đồng; những trường hợp xóa biên có quy tắc nhẹ hơn nhưng `end` cần xem riêng.

## 14. Phân tích chi phí: độ ổn định bộ duyệt không miễn phí

Một cấu trúc có iterator ổn định khi chèn thường đánh đổi ở những mặt khác, ví dụ cấp phát theo nút, bộ nhớ metadata hoặc tính cục bộ dữ liệu.

| Nhiệm vụ | Phương án | Độ phức tạp điển hình | Điều kiện/đánh đổi |
| --- | --- | --- | --- |
| Duyệt `n` phần tử | Vector/list/array | O(n) | Chi phí cache khác nhau |
| Xóa một phần tử vector đã có iterator | `erase` | O(n) xấu nhất | Có thể dịch phần tử và invalidate vị trí sau |
| Xóa một nút list đã có iterator | `list.erase` | O(1) | Chỉ khi iterator hợp lệ; tìm nút trước đó có thể O(n) |
| Xóa nhiều phần tử vector bằng nhiều lần `erase` | Lặp và xóa từng mục | Có thể O(n²) | Dịch đuôi lặp lại |
| Lọc vector một lần | `std::erase_if`/remove–erase | Thường O(n) | Vẫn thay trạng thái container và invalidation |
| Chụp snapshot toàn bộ mảng/list | Sao chép `n` phần tử | O(n) thời gian, O(n) vùng mới | Snapshot nông có thể chia sẻ object con |
| Tra lại phần tử bằng khóa hash | `unordered_map.find` | Trung bình kỳ vọng O(1); xấu nhất O(n) | Khóa phải ổn định; rehash có chi phí |
| Tái băm bảng `n` mục | `rehash` | Thường tuyến tính theo số mục/bucket trong mô hình phổ biến | Làm iterator cũ mất hiệu lực |
| Duyệt cây theo stack tổ tiên | Inorder DFS | O(n) tổng, O(h) stack | Vòng đời nút và cập nhật cây phải được kiểm soát |
| BFS/DFS đồ thị | Duyệt snapshot cố định | O(V+E) | Snapshot có thể cần O(V+E) dung lượng thêm |
| Kiểm tra `version` mỗi `next` | Fail-fast cursor | O(1) mỗi bước | Không đảm bảo thread-safety/vòng đời |

**Cần tính toàn bộ chuỗi thao tác.** Một API xóa nút O(1) không có nghĩa “tìm khóa rồi xóa” là O(1) nếu phải duyệt O(n) để tìm. Tương tự, dùng `std::list` để giữ iterator ổn định có thể làm tăng chi phí cấp phát, phân mảnh và cache miss so với vector trong workload quét lớn.

Một thiết kế thực tế có thể chọn:

- Vector + **ID riêng** nếu duyệt tuần tự là thao tác chính và sắp xếp lại vị trí thường xuyên.
- Danh sách liên kết hoặc node-based container khi cần chèn/xóa tại vị trí đã biết và giữ iterator tới các nút khác.
- Bảng băm + **tra lại theo khóa** khi không cần duy trì một iterator xuyên qua `rehash`.
- Persistent structure hoặc snapshot khi cần duyệt phiên bản không đổi trong lúc nơi khác cập nhật.

## 15. Quy trình rà soát và kiểm thử hợp đồng bộ duyệt

Trước khi viết mã giữ iterator qua một thao tác sửa cấu trúc, trả lời:

1. **Iterator thuộc về container nào?** Không so sánh tùy tiện iterator của hai container khác nhau khi API không cho phép.
2. **Đối tượng được duyệt còn sống không?** Có bị xóa, container hủy hoặc chuyển ownership không?
3. **Thao tác sắp xảy ra là gì?** Gán giá trị, chèn/xóa, tăng capacity, rehash, quay cây, đổi metadata?
4. **Hợp đồng chỉ vô hiệu iterator hay cả reference/pointer?** Đặc biệt với `deque` và `unordered_map`.
5. **Vị trí nào bị ảnh hưởng?** Tại chỗ sửa, phía sau, mọi iterator, hay chỉ phần tử bị xóa?
6. **Có API trả iterator hợp lệ tiếp theo không?** Ví dụ `vector.erase` hoặc `list.erase`.
7. **Nếu đang duyệt lazy, nguồn có phải snapshot không?** Thứ tự và tập phần tử có được cố định trước không?
8. **Có dữ liệu dùng chung/đa luồng không?** Ai bảo vệ quyền đọc và ai được quyền thu hồi?
9. **Chi phí thay thế là gì?** Lưu ID/tra lại, snapshot, khóa, sao chép, hoặc đổi container?
10. **Những trường hợp biên nào phải kiểm thử?** Rỗng, phần tử cuối, chèn ở đầu/cuối, reallocation, xóa liên tiếp, thay đổi ở giữa lượt duyệt.

### 15.1. Bộ kiểm thử gợi ý

Đối với container tự cài, tối thiểu thử:

- Tạo iterator khi container rỗng: `begin == end` hoặc `next` trả END.
- Thêm phần tử đầu tiên sau khi tạo iterator rỗng: iterator cũ xử lý theo chính sách (stale, snapshot hoặc live) đã định.
- Xóa **chính phần tử iterator đang trỏ đến**; không cho dùng con trỏ nút sau hủy.
- Xóa một phần tử **trước** vị trí hiện tại trong vector; xác minh không nhầm chỉ số cũ.
- Chèn/xóa cuối rồi kiểm tra `end`, đặc biệt với vector/deque.
- Ép vector tăng capacity/rehash bảng băm trong test có kiểm soát để xác minh invalidation.
- Duyệt list với nhiều nút âm liên tiếp; bảo đảm vòng xóa không bỏ qua nút hoặc truy cập sau `free`.
- Xóa phần tử cuối và tiếp tục vòng bằng iterator trả về, không tăng thêm iterator `end`.
- Với cây, quay cây hoặc xóa nút trong một bản kiểm thử chỉ khi bộ duyệt có hợp đồng cho phép, đối chiếu thứ tự duyệt.
- Với đồ thị, xóa một đỉnh đã được enqueue; kiểm thử chính sách snapshot hoặc xử lý ID đã bị xóa.
- Với concurrent container, kiểm thử đúng cơ chế đồng bộ/reclamation, không lấy “chạy không crash” làm bằng chứng đủ.

### 15.2. Đừng kiểm thử invalidation bằng cách cố ý dereference iterator cũ

Trong C/C++, việc giải tham chiếu một iterator/con trỏ đã bị vô hiệu có thể dẫn tới **undefined behavior**. Nếu muốn kiểm tra lỗi bằng sanitizer trong môi trường thử nghiệm, phải hiểu đó là cách công cụ phát hiện *một số* dạng sai chứ không phải phép thử an toàn trong logic sản phẩm.

Đối với **ngữ nghĩa** của container, nên viết kiểm thử dựa trên các tiền điều kiện và hậu điều kiện hợp lệ: phần tử nào còn tồn tại, thứ tự nào đúng, iterator trả về từ `erase` có dẫn đến phần tử kế tiếp thích hợp không, và các bất biến metadata có khớp không.

## 16. Bài tập có lời giải

### Bài 1. `end` cũ sau `push_back`

```cpp
std::vector<int> v{1, 2};
v.reserve(10);
auto end_before = v.end();
v.push_back(3);
```

**Câu hỏi:** Vì còn capacity, `end_before` có thể được dùng như `v.end()` mới không?

**Lời giải:** **Không.** Dù không cấp phát lại nên iterator tới phần tử cũ vẫn hợp lệ, `end()` cũ bị vô hiệu sau `push_back`. Lấy `v.end()` mới trước khi so sánh tiếp.

### Bài 2. Con trỏ vector sau `reserve`

```cpp
std::vector<int> v{10, 20};
auto p = &v[0];
v.reserve(v.capacity() + 1);
```

**Lời giải:** Khi `reserve` thành công và yêu cầu capacity lớn hơn capacity hiện tại, vùng phần tử được cấp phát lại; `p` cũ không được giải tham chiếu. Lấy lại địa chỉ qua `&v[0]` nếu phần tử vẫn tồn tại và đang cần.

### Bài 3. Xóa phần tử chẵn trong vector

```cpp
for (auto it = v.begin(); it != v.end(); ++it) {
    if (*it % 2 == 0) {
        v.erase(it);
    }
}
```

**Lời giải:** Mã sai vì iterator `it` bị vô hiệu sau `erase` nhưng vòng vẫn tăng `++it`. Viết:

```cpp
for (auto it = v.begin(); it != v.end();) {
    if (*it % 2 == 0) it = v.erase(it);
    else ++it;
}
```

### Bài 4. Xóa hai phần tử liên tiếp

Vector `[1, 2, 4, 5]` cần xóa tất cả số chẵn. Vì sao sau khi xóa 2 không được tăng iterator thêm một lần?

**Lời giải:** `erase` trả iterator tới phần tử kế tiếp trong trạng thái mới, tức vị trí đang mang số 4. Nếu tăng nữa, ta nhảy qua 4 và bỏ sót. Chỉ tăng trong nhánh **không xóa**.

### Bài 5. `std::list` chèn ở đầu

Iterator `it` trỏ tới nút chứa 20 trong list `[10,20,30]`. Thực hiện `push_front(5)`. `it` còn hợp lệ không?

**Lời giải:** **Có**, theo hợp đồng của `std::list`: chèn không làm mất hiệu lực iterator/tham chiếu tới các nút đã tồn tại. Nhưng nếu `erase(it)`, chính `it` sẽ bị vô hiệu.

### Bài 6. `std::deque` thêm ở cuối

Iterator `it` và tham chiếu `ref` cùng chỉ một phần tử đang sống trong deque. Sau `push_back`, hai đường truy cập có nhất thiết cùng trạng thái hợp lệ không?

**Lời giải:** **Không.** Chèn ở đầu/cuối deque làm iterator cũ mất hiệu lực, nhưng tham chiếu tới các phần tử cũ vẫn hợp lệ theo hợp đồng cho trường hợp chèn biên. Không suy rằng iterator còn hợp lệ chỉ vì địa chỉ phần tử chưa đổi.

### Bài 7. `std::map` chèn khóa mới

Một iterator tới khóa 30 của `std::map` đang được giữ. Chèn khóa 20 làm cây cân bằng phải quay. Iterator tới 30 còn hợp lệ không?

**Lời giải:** **Có**, vì `std::map::insert` không làm mất hiệu lực iterator/reference hiện có. Đây là bảo đảm của **API container**, không phải suy luận áp dụng cho bộ duyệt cây tự viết.

### Bài 8. `std::unordered_map` rehash

Một iterator và một `int&` cùng truy cập giá trị của khóa 1 trong `std::unordered_map<int,int>`. `rehash` diễn ra, khóa 1 không bị xóa. Đường nào còn hợp lệ?

**Lời giải:** Iterator cũ **bị vô hiệu hóa**; tham chiếu tới giá trị phần tử vẫn hợp lệ sau rehash nếu phần tử không bị xóa. Nếu sau đó xóa khóa 1, tham chiếu cũng không còn hợp lệ.

### Bài 9. Python list tự xóa khi duyệt

```python
a = [1, 2, 3, 4, 5]
for x in a:
    a.remove(x)
print(a)
```

**Lời giải:** Kết quả là `[2, 4]`: phần tử dịch trái sau xóa khiến iterator theo vị trí bỏ qua một số phần tử. Nếu muốn xóa hết, gọi `a.clear()`; nếu muốn lọc, dùng comprehension hoặc API phù hợp.

### Bài 10. Python dict xóa khóa

```python
d = {"A": 1, "B": 0, "C": 2}
for key in list(d):
    if d[key] == 0:
        del d[key]
```

**Lời giải:** Kết quả là `{"A": 1, "C": 2}`. `list(d)` tạo snapshot các khóa để không sửa kích thước chính dict đang được lặp. Vẫn phải tránh thay dict từ nơi khác không đồng bộ nếu yêu cầu snapshot nhất quán.

### Bài 11. Java `Iterator.remove`

Vì sao `iterator.remove()` phù hợp hơn `list.remove(value)` khi đang duyệt một `ArrayList` bằng chính iterator đó?

**Lời giải:** `Iterator.remove` là thao tác hợp đồng để xóa phần tử vừa được `next` trả về và cập nhật trạng thái iterator tương ứng. Xóa trực tiếp qua list trong vòng dùng iterator có thể bị phát hiện như sửa đổi cấu trúc ngoài iterator. Cần tuân thủ tiền điều kiện của `remove` và nhớ fail-fast chỉ best-effort.

### Bài 12. Rust và `Vec`

Trong Rust an toàn, tại sao mã sửa `Vec` bằng `push` ngay trong `for x in &vec` thường không được biên dịch?

**Lời giải:** Vòng lặp đang mượn `vec` theo cách đọc; `push` cần quyền mượn mutable và có thể dời vùng phần tử, làm các tham chiếu đang dùng mất hiệu lực. Dùng một API như `retain` để lọc, hoặc tạo danh sách thay đổi rồi áp dụng sau lượt duyệt.

### Bài 13. Graph BFS đang chạy thì xóa đỉnh

BFS đã enqueue ID của đỉnh B. Trước khi dequeue, đồ thị bị xóa B. Vì sao thuật toán có thể sai?

**Lời giải:** ID nằm trong queue không tự bảo đảm đỉnh B vẫn tồn tại và có thể đọc adjacency. Phải xác định chính sách đồ thị bất biến trong lượt duyệt, snapshot, hoặc kiểm tra lại ID kèm cơ chế quản lý generation/đồng bộ phù hợp.

### Bài 14. Snapshot có luôn sao chép sâu payload?

Đồ thị dùng dict chứa các danh sách láng giềng, mỗi đỉnh có một đối tượng metadata mutable. Nếu chỉ copy dict và các danh sách kề, metadata của đỉnh có trở thành bản sao độc lập không?

**Lời giải:** **Không nhất thiết.** Snapshot nông của container có thể vẫn giữ cùng tham chiếu tới các đối tượng metadata. Nếu yêu cầu snapshot bất biến sâu, cần cơ chế sao chép hoặc phiên bản hóa phù hợp với kiểu payload.

### Bài 15. Cursor có bộ đếm phiên bản

Cursor lưu `expected_version = 9`, container sau một lần `push` có `version = 10`. `cursor_next` nên trả “hết dữ liệu” hay “mất hiệu lực”?

**Lời giải:** Trả **STALE/INVALID** theo hợp đồng fail-fast, không đánh đồng với END. Khi phát hiện khác phiên bản, không tiếp tục đọc phần tử theo vị trí cũ; tạo cursor mới hoặc xử lý trạng thái thay đổi.

### Bài 16. So sánh độ phức tạp

Với vector có `n` phần tử, xóa `k` phần tử bằng `erase` lặp từng phần tử có thể tốn bao nhiêu trong trường hợp xấu nhất? Có cách lọc tốt hơn không?

**Lời giải:** Có thể lên tới O(nk), đặc biệt khi mỗi lần xóa phải dịch nhiều phần tử; nếu `k = Θ(n)` thì thành O(n²). Một lần lọc tập trung như `std::erase_if` hoặc thuật toán remove–erase thường O(n) theo số phần tử được xét/di chuyển trong mô hình thao tác phần tử chi phí cố định.

## 17. Tổng kết và nguyên tắc thiết kế

- **Bộ duyệt là trạng thái truy cập, không phải quyền sở hữu.** Một iterator có thể mất hiệu lực dù biến vẫn tồn tại và dù địa chỉ cũ còn nhìn thấy trong debugger.
- **Hợp đồng invalidation phụ thuộc cả container và thao tác.** `vector` có thể dời vùng; `list` ổn định nút chưa bị xóa; `unordered_map` có thể vô hiệu iterator do rehash trong khi reference tới phần tử sống vẫn hợp lệ.
- **Không suy từ tính hợp lệ bộ nhớ sang tính đúng đắn logic.** Chèn/xóa có thể đổi thứ tự, chỉ số, khóa hoặc đường duyệt ngay cả khi node address vẫn ổn định.
- **Dùng đúng API khi vừa duyệt vừa sửa.** Với C++ vector, dùng iterator do `erase` trả về; với Java, dùng `Iterator.remove` khi hỗ trợ; với Python, ưu tiên lọc hoặc snapshot các phần tử cần duyệt.
- **Nếu cần bảo đảm phiên bản dữ liệu**, cân nhắc snapshot, persistent structure hoặc cơ chế phiên bản/ID. Bộ đếm phiên bản chỉ phát hiện thay đổi theo chính sách, **không tự giải quyết vòng đời hoặc data race**.
- **Phân tích cả chi phí và bất biến:** xóa nút đã định vị có thể O(1) trên list nhưng tìm nút vẫn O(n); lọc nhiều phần tử vector bằng từng lần xóa có thể O(n²); snapshot có thể cần O(n) hoặc O(V+E) bộ nhớ.
- **Kiểm thử các tình huống biên và thao tác gây dời vùng:** rỗng, xóa cuối, xóa liên tiếp, reallocation, rehash, rotation, đổi adjacency và đồng bộ nhiều luồng. Mỗi API cần mô tả rõ **iterator nào còn được sử dụng, lúc nào phải lấy lại và khi nào tuyệt đối không được truy cập**.
