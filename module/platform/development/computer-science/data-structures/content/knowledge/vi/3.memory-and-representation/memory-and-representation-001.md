# Lưu trữ liên tiếp và lưu trữ bằng các nút liên kết

Khi thiết kế một cấu trúc dữ liệu, ta cần trả lời hai câu hỏi khác nhau: **các phần tử được sắp xếp theo thứ tự logic nào** và **chúng được đặt ở đâu trong bộ nhớ**. Hai cách tổ chức nền tảng là **lưu trữ liên tiếp** (contiguous storage) và **lưu trữ bằng các nút liên kết** (linked-node storage). Hiểu được hai cách biểu diễn này giúp giải thích vì sao mảng truy cập theo chỉ số nhanh, vì sao danh sách liên kết có thể chèn ở đầu trong thời gian hằng số, cũng như vì sao chi phí thực tế đôi khi khác với ký hiệu Big-O.

Trong phạm vi môn **Cấu trúc dữ liệu** (Computer Science Data Structures), kiến thức này là nền móng để lựa chọn cách hiện thực mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Bài học tập trung vào **bố trí bộ nhớ, bất biến cấu trúc, thao tác, thời gian và dung lượng bộ nhớ** của hai kiểu biểu diễn.

## 1. Phân biệt thứ tự logic và vị trí vật lý

Xét dãy logic `10, 20, 30, 40`. Người dùng nhìn thấy cùng một thứ tự, nhưng chương trình có thể lưu dãy đó theo hai cách:

**Lưu trữ liên tiếp:** các ô chứa phần tử nằm cạnh nhau trong cùng một vùng bộ nhớ.

```text
Chỉ số:          0          1          2          3
Địa chỉ:       1000       1004       1008       1012
             +----------+----------+----------+----------+
Giá trị:     |    10    |    20    |    30    |    40    |
             +----------+----------+----------+----------+
                Mỗi phần tử int giả sử chiếm 4 byte
```

**Lưu trữ bằng nút liên kết:** mỗi nút mang dữ liệu và một hoặc nhiều liên kết tới nút khác; các nút không cần nằm cạnh nhau.

```text
head
  |
  v
[10 | next] ---> [20 | next] ---> [30 | next] ---> [40 | NULL]
   0x9000          0x1200          0x7000          0x3100

(Địa chỉ chỉ để minh họa; mũi tên quyết định thứ tự logic.)
```

Điểm mấu chốt: **cùng một dãy logic không đồng nghĩa với cùng một cách biểu diễn trong bộ nhớ**. Đối với mảng liên tiếp, vị trí phần tử được suy ra từ địa chỉ đầu và chỉ số. Đối với danh sách liên kết, ta phải lần theo các liên kết để tìm phần tử tiếp theo.

## 2. Lưu trữ liên tiếp: mảng và mảng động

### 2.1. Địa chỉ và truy cập theo chỉ số

Với mảng có các phần tử cùng kiểu, kích thước mỗi phần tử là `s` byte, và địa chỉ phần tử đầu là `base`, ta có:

\[
\operatorname{address}(A[i]) = base + i \times s
\]

Ví dụ, nếu `base = 1000`, `s = 4` và `i = 3` thì phần tử `A[3]` bắt đầu tại địa chỉ `1012`. Máy tính chỉ cần tính độ lệch để truy cập phần tử, không cần đi qua `A[0]`, `A[1]` và `A[2]`. Bởi vậy, **truy cập bằng chỉ số hợp lệ là O(1)**.

Chương trình C dưới đây minh họa các phần tử của một mảng `int` nằm liên tiếp:

```c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    int a[] = {10, 20, 30, 40};

    for (size_t i = 0; i < sizeof a / sizeof a[0]; ++i) {
        printf("a[%zu] = %d, dia chi = %p\n",
               i, a[i], (void *)&a[i]);
    }

    printf("Khoang cach hai phan tu lien ke: %td byte\n",
           (char *)&a[1] - (char *)&a[0]);
    return 0;
}
```

Địa chỉ thực sẽ thay đổi theo mỗi chương trình/môi trường, nhưng khoảng cách giữa hai phần tử kế tiếp luôn bằng `sizeof(int)` trong cùng mảng đó. Trong ngôn ngữ và kiểu dữ liệu khác, cần phân biệt **mảng chứa trực tiếp giá trị** với **mảng chứa các tham chiếu**: chẳng hạn, `list` của Python và mảng đối tượng của Java lưu các tham chiếu trong vùng liên tiếp, còn các đối tượng được tham chiếu có thể nằm rải rác. Vì vậy không được suy rằng toàn bộ đối tượng trong mọi “mảng” đều liền kề.

### 2.2. Mảng cố định và mảng động

- **Mảng có kích thước cố định:** dành đủ chỗ cho số phần tử đã xác định, ví dụ `int a[4]` trong C. Một mảng cố định thông thường không tự mở rộng thêm ô.
- **Mảng động** (dynamic array, ví dụ `std::vector` trong C++, `ArrayList` trong Java hoặc `list` trong Python): quản lý một vùng lưu trữ liên tiếp có thể thay thế bằng vùng lớn hơn khi cần.

Mảng động thường theo dõi hai đại lượng:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `size` | Số phần tử hợp lệ đang được lưu |
| `capacity` | Số phần tử có thể chứa trong vùng đã cấp phát mà chưa cần tăng dung lượng |

**Bất biến quan trọng:** `0 <= size <= capacity`; chỉ các vị trí từ `0` đến `size - 1` là phần tử logic của dãy. Các ô dự phòng từ `size` đến `capacity - 1` chưa được xem là phần tử đang có.

Ví dụ `size = 4`, `capacity = 8`:

```text
          Các phần tử đang dùng               Vùng dự phòng
        +----+----+----+----+----+----+----+----+
        | 10 | 20 | 30 | 40 |    |    |    |    |
        +----+----+----+----+----+----+----+----+
          0    1    2    3    4    5    6    7
```

Khi `size == capacity` và cần thêm một phần tử, mảng động có thể cấp phát vùng lớn hơn, sao chép/di chuyển các phần tử, rồi giải phóng vùng cũ. Chính sách tăng dung lượng phụ thuộc hiện thực; thường chọn tăng theo một hệ số lớn hơn 1 để hạn chế số lần cấp phát lại. Không nên mặc định mọi thư viện đều **nhân đôi** dung lượng.

### 2.3. Chèn và xóa: tại sao cần dịch phần tử?

Giả sử mảng đang chứa `[10, 20, 30, 40]` và muốn chèn `25` vào vị trí chỉ số `2`. Các phần tử từ vị trí `2` trở đi phải dịch sang phải một ô:

```text
Trước: [10, 20, 30, 40, --]
        Dịch 30 và 40 sang phải một vị trí; ô chỉ số 2 trống.
Sau:   [10, 20, 25, 30, 40]
```

Trong một mảng đã đủ dung lượng, thao tác có thể viết như sau:

```c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    int values[8] = {10, 20, 30, 40};
    size_t size = 4;
    const size_t capacity = sizeof values / sizeof values[0];
    size_t pos = 2;

    if (pos <= size && size < capacity) {
        for (size_t i = size; i > pos; --i) {
            values[i] = values[i - 1];
        }
        values[pos] = 25;
        ++size;
    }

    for (size_t i = 0; i < size; ++i) {
        printf("%d ", values[i]);
    }
    return 0;
}
/* In ra: 10 20 25 30 40 */
```

Nếu chèn ở đầu, có thể phải dịch `n` phần tử: **O(n)**. Nếu chèn ở cuối khi còn chỗ, chỉ cần gán một ô: **O(1)**. Xóa ở giữa thường cần dịch các phần tử phía sau sang trái để bảo toàn dãy liên tiếp, nên trong trường hợp xấu là **O(n)**. Xóa cuối mảng động thường là **O(1)** (chưa xét công việc bổ sung do kiểu phần tử hoặc thư viện yêu cầu).

### 2.4. Vì sao thêm ở cuối mảng động là O(1) trung bình dồn tích?

Một lần thêm ở cuối có thể khiến mảng phải cấp phát và chuyển `n` phần tử: **O(n)** ở lần đó. Tuy nhiên, nếu dung lượng được tăng theo cấp số nhân, các lần mở rộng xảy ra thưa dần. Với chính sách minh họa nhân đôi, tổng số phần tử được sao chép qua các lần mở rộng cho tới khi có `n` phần tử bị chặn bởi tổng hình học:

\[
1 + 2 + 4 + \cdots < 2n = O(n).
\]

Do đó, tổng chi phí của `n` lần thêm ở cuối là `O(n)` và **chi phí trung bình dồn tích (amortized) cho mỗi lần thêm là O(1)**. Đây là bảo đảm về *một chuỗi thao tác*; không có nghĩa mọi lần thêm đều chỉ mất một lượng công việc hằng số.

### 2.5. Hiệu ứng bộ nhớ đệm

CPU thường chuyển dữ liệu giữa RAM và cache theo các khối (cache line). Khi duyệt mảng liên tiếp, tải một khối có thể mang theo nhiều phần tử kế tiếp; việc truy cập tuần tự thường tận dụng bộ nhớ đệm và khả năng đọc trước (prefetch). Điều này giải thích vì sao mảng có thể duyệt rất nhanh ngay cả khi bảng độ phức tạp cho cả mảng lẫn danh sách liên kết đều ghi `O(n)`.

Chi phí của mảng là cần một vùng liên tiếp đủ lớn, có thể lãng phí ô dự phòng, và việc cấp phát lại có thể làm **thay đổi địa chỉ** của các phần tử. Trong C/C++, con trỏ, tham chiếu hoặc iterator trỏ vào vùng cũ có thể mất hiệu lực sau khi vùng lưu trữ bị dời; quy tắc chính xác phụ thuộc vào container và thao tác.

## 3. Lưu trữ bằng các nút liên kết

### 3.1. Thành phần và bất biến của danh sách liên kết đơn

Danh sách liên kết đơn (singly linked list) thường có:

- `head`: tham chiếu/con trỏ đến nút đầu; `NULL`/`null` khi danh sách rỗng.
- Mỗi **nút**: một phần dữ liệu và trường `next` trỏ đến nút kế tiếp.
- Nút cuối: `next = NULL`/`null`.

Một bất biến cơ bản là: **bắt đầu từ `head`, lần theo `next` ta gặp đúng các nút thuộc danh sách theo thứ tự logic và cuối cùng tới `NULL`; không có vòng lặp ngoài ý muốn**. Một số hiện thực có thêm `tail` trỏ tới nút cuối và bộ đếm `size`.

```text
head
 |
 v
+----------+       +----------+       +----------+
| 10 |  o--------->| 20 |  o--------->| 30 |NULL |
+----------+       +----------+       +----------+
                                              ^
                                              |
                                             tail
```

Các nút thường được cấp phát riêng lẻ và **không có bảo đảm liền kề về địa chỉ**. Bộ cấp phát có thể tình cờ đặt hai nút cạnh nhau; đó không phải bất biến của danh sách liên kết. Thứ tự của danh sách được xác định bởi trường `next`, không phải bởi việc so sánh địa chỉ.

### 3.2. Quan sát một danh sách liên kết bằng C

```c
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

static Node *create_node(int value, Node *next) {
    Node *node = malloc(sizeof *node);
    if (node == NULL) return NULL;
    node->value = value;
    node->next = next;
    return node;
}

int main(void) {
    Node *head = NULL;

    /* Thêm 30, rồi 20, rồi 10 vào đầu: dãy cuối là 10 -> 20 -> 30. */
    for (int value = 30; value >= 10; value -= 10) {
        Node *node = create_node(value, head);
        if (node == NULL) {
            while (head != NULL) {
                Node *next = head->next;
                free(head);
                head = next;
            }
            return EXIT_FAILURE;
        }
        head = node;
    }

    for (Node *cur = head; cur != NULL; cur = cur->next) {
        printf("value = %d, node = %p, next = %p\n",
               cur->value, (void *)cur, (void *)cur->next);
    }

    while (head != NULL) {
        Node *next = head->next;
        free(head);
        head = next;
    }
    return EXIT_SUCCESS;
}
```

Ví dụ thể hiện ba điều: thêm vào đầu chỉ thay một vài con trỏ; để duyệt phải theo `next`; và trong C cần `free` từng nút đã cấp phát. Ở ngôn ngữ có bộ gom rác như Java, Python hoặc C#, đối tượng không còn được tham chiếu có thể được thu hồi tự động, nhưng **chi phí đối tượng và liên kết vẫn tồn tại**.

### 3.3. Chèn một nút: cập nhật liên kết

Muốn chèn `25` sau nút `20`, khi **đã có con trỏ `p` tới nút `20`**, ta làm:

```text
Trước:  10 ---> 20 ------------> 30

Sau:    10 ---> 20 ---> 25 ---> 30
```

```c
/* Giả sử p là nút hợp lệ thuộc danh sách, new_node đã cấp phát. */
new_node->next = p->next;
p->next = new_node;
```

Hai phép gán liên kết thực hiện trong **O(1)**, không cần dịch các phần tử khác. Thứ tự gán rất quan trọng: phải giữ được đường dẫn tới nút kế tiếp cũ trước khi thay `p->next`.

Tuy nhiên, nếu yêu cầu là “tìm nút có giá trị `20` rồi chèn sau nó”, trước hết phải **tìm** nút đó từ `head`. Tìm kiếm trong danh sách liên kết đơn không có chỉ mục bổ sung thường là **O(n)**; tổng thao tác khi đó vẫn là **O(n)**. Độ phức tạp O(1) của chèn chỉ đúng khi vị trí liên quan đã biết qua con trỏ hợp lệ.

Chèn ở đầu còn đơn giản hơn:

```c
new_node->next = head;
head = new_node;
```

Nếu duy trì `tail`, phải cập nhật thêm `tail = new_node` khi danh sách trước đó rỗng.

### 3.4. Xóa nút và quản lý con trỏ

Để xóa nút ngay sau `p` trong danh sách liên kết đơn, khi `p->next` tồn tại:

```c
Node *removed = p->next;
p->next = removed->next;
free(removed);  /* Chỉ dùng cho nút cấp phát bằng malloc, thuộc quyền sở hữu này. */
```

Việc đổi liên kết là **O(1)** nếu đã có `p`. Nếu muốn xóa nút đang được trỏ bởi `target` nhưng **không biết nút đứng trước**, danh sách liên kết đơn nhìn chung phải tìm nút trước đó từ `head` (`O(n)`), trừ một số kỹ thuật đặc biệt có điều kiện và không dùng được cho mọi nút. Xóa `head` là trường hợp riêng `O(1)`; nếu danh sách trở thành rỗng phải cập nhật `tail` nếu có.

Trong ngôn ngữ dùng con trỏ thủ công, cần tránh mất địa chỉ của nút cần giải phóng, truy cập nút đã `free`, giải phóng trùng lặp, hoặc để liên kết trỏ tới vùng nhớ hết hiệu lực. Trong ngôn ngữ có tham chiếu và gom rác, vẫn cần giữ các bất biến `head`/`tail`/`next` và loại bỏ những tham chiếu không còn cần thiết.

### 3.5. Danh sách liên kết đôi và danh sách vòng

**Danh sách liên kết đôi** (doubly linked list) bổ sung trường `prev` ở mỗi nút:

```text
NULL <- [10] <-> [20] <-> [30] -> NULL
        head                 tail
```

Nhờ liên kết hai chiều, nếu đã có con trỏ đến một nút hợp lệ, ta có thể xóa nút đó bằng cách nối `prev` với `next` và cập nhật `head`/`tail` trong **O(1)**. Đổi lại mỗi nút cần thêm một con trỏ, và khi chèn/xóa phải cập nhật nhiều liên kết hơn. Bất biến quan trọng là `x.next.prev == x` và `x.prev.next == x` tại các vị trí có hàng xóm, trừ những đầu mút.

**Danh sách liên kết vòng** (circular linked list) nối nút cuối về nút đầu, thích hợp cho một số bài toán luân phiên. Vì không còn điểm kết thúc `NULL` theo cách thông thường, thuật toán duyệt phải có điều kiện dừng rõ ràng để tránh lặp vô hạn. Danh sách vòng có thể là đơn hoặc đôi.

## 4. So sánh thao tác và độ phức tạp

Đặt `n` là số phần tử đang lưu. Bảng dưới so sánh **mảng động** với **danh sách liên kết đơn có `head` và `tail`**, giả sử các thao tác trên nút biết trước nhận con trỏ hợp lệ và không bao gồm thời gian tìm nút:

| Thao tác | Mảng động | Danh sách liên kết đơn |
| --- | --- | --- |
| Đọc/ghi phần tử tại chỉ số `i` hợp lệ | **O(1)** | **O(n)** để đi đến nút thứ `i` |
| Duyệt tuần tự toàn bộ `n` phần tử | O(n) | O(n) |
| Tìm một giá trị trong dãy chưa sắp xếp | O(n) | O(n) |
| Chèn ở đầu | O(n) do dịch phần tử | **O(1)** |
| Chèn ở giữa, đã biết vị trí cần chèn | O(n) do dịch phần tử | **O(1)** nếu đã có con trỏ tới nút liền trước |
| Thêm ở cuối | **O(1) amortized**; một lần tăng dung lượng có thể O(n) | **O(1)** nếu duy trì `tail` |
| Xóa ở đầu | O(n) do dịch phần tử | **O(1)** |
| Xóa ở giữa, đã biết nút đứng trước | O(n) do dịch phần tử | **O(1)** để nối lại liên kết |
| Xóa ở cuối | Thường **O(1)** | **O(n)** để tìm nút đứng trước `tail` |

Các điều kiện làm thay đổi kết quả:

1. **Không có `tail`**: thêm cuối danh sách liên kết đơn phải duyệt từ `head`, tốn O(n).
2. **Chỉ biết chỉ số, không có con trỏ nút**: phải đi tới vị trí trong danh sách liên kết, tốn O(n), ngay cả khi thao tác nối liên kết sau đó là O(1).
3. **Danh sách liên kết đôi có `tail`**: xóa cuối có thể O(1) vì `tail.prev` cho biết nút trước; đổi lại chi phí bộ nhớ và cập nhật liên kết lớn hơn.
4. **Mảng đã được sắp xếp**: có thể dùng tìm kiếm nhị phân trong O(log n) nhờ truy cập ngẫu nhiên O(1). Danh sách liên kết không có ưu thế truy cập ngẫu nhiên này nên tìm kiếm nhị phân kiểu mảng không đạt cùng hiệu quả chỉ bằng cách chọn nút giữa.
5. **Cấp phát**: một lần chèn nút có thể cần xin bộ nhớ từ allocator. Phân tích O(1) của cập nhật liên kết thường không tính riêng chi phí hệ thống cấp phát; trong thực tế cấp phát có độ trễ và có thể thất bại.

Ký hiệu Big-O mô tả sự tăng trưởng theo `n`, **không đo trực tiếp số mili giây**. Hai thao tác cùng O(n) có thể chênh lệch đáng kể vì cách truy cập cache, số lần cấp phát, độ lớn phần tử và chi phí xử lý mỗi nút.

## 5. Dung lượng bộ nhớ và tính cục bộ dữ liệu

### 5.1. Phần bộ nhớ nào tạo ra chi phí?

Với mảng lưu trực tiếp `n` giá trị kiểu `T` vào một vùng có `capacity = c`, phần lưu trữ phần tử cần xấp xỉ `c * sizeof(T)` byte, cộng metadata nhỏ của container (nếu có). Phần chênh lệch `c - n` là chỗ dự phòng chưa chứa phần tử logic.

Với danh sách liên kết đơn, mỗi nút thường cần **dữ liệu + ít nhất một con trỏ `next` + padding căn chỉnh**, có thể còn có metadata của allocator hoặc của đối tượng runtime. Cấp phát từng nút có thể gây phân mảnh bộ nhớ và tăng chi phí theo dõi.

Trên **một hệ 64-bit điển hình**, giả sử `int` có 4 byte và con trỏ có 8 byte:

```c
typedef struct Node {
    int value;       /* 4 byte trong giả định */
    struct Node *next; /* 8 byte trong giả định */
} Node;
```

Một nút dạng này **thường** có `sizeof(Node) == 16` do padding, trong khi một giá trị `int` trong mảng chỉ cần 4 byte. Với 1.000 số nguyên, phần tử mảng cố định chiếm khoảng 4.000 byte, còn 1.000 nút ví dụ này có thể chiếm ít nhất khoảng 16.000 byte, **chưa tính metadata cấp phát riêng cho từng nút**. Đây là ví dụ để hình dung chênh lệch, không phải con số bất biến: kích thước kiểu, căn chỉnh và allocator phụ thuộc nền tảng. Nên đo `sizeof` và dung lượng thực tế khi cần chính xác.

### 5.2. Tại sao bố trí vật lý quan trọng?

| Đặc điểm | Vùng liên tiếp | Nút liên kết |
| --- | --- | --- |
| Truy cập tuần tự | Thường thuận lợi cho cache/prefetch | Phải đọc liên kết và đến địa chỉ nút tiếp theo |
| Truy cập phần tử thứ `i` | Tính địa chỉ trực tiếp | Theo `next` qua nhiều nút |
| Tăng số phần tử | Có thể phải đổi vùng lưu trữ khi hết capacity | Có thể cấp phát thêm nút riêng lẻ |
| Bộ nhớ phụ | Có thể có ô dự phòng của mảng động | Con trỏ, padding và chi phí cấp phát cho mỗi nút |
| Sự ổn định địa chỉ | Cấp phát lại có thể dời phần tử | Nút riêng lẻ thường giữ địa chỉ trong vòng đời của nó, trừ khi bị xóa/di chuyển bởi cơ chế đặc thù |

Đừng nhầm **“liên kết giúp chèn O(1)”** với **“liên kết luôn nhanh hơn khi chèn”**. Nếu chương trình phải đi qua hàng nghìn nút mới tìm thấy vị trí, tổng thời gian thường bị chi phối bởi bước tìm kiếm. Ngược lại, mảng có thể dịch nhiều phần tử nhưng thao tác sao chép liên tiếp được tối ưu rất tốt.

## 6. Lựa chọn cấu trúc từ yêu cầu bài toán

Điểm xuất phát nên là **kiểu thao tác chủ đạo** và **thông tin có sẵn khi thao tác**.

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Đọc phần tử theo chỉ số nhiều lần, quét và tính toán trên dãy lớn | Mảng/mảng động | O(1) theo chỉ số, tính cục bộ dữ liệu tốt |
| Thêm dữ liệu liên tục vào cuối, sau đó duyệt hoặc tìm theo chỉ số | Mảng động | Thêm cuối O(1) amortized, truy cập ngẫu nhiên nhanh |
| Thường xuyên thêm/xóa đầu danh sách, chỉ cần thao tác tuần tự | Danh sách liên kết đơn; hoặc deque phù hợp | Chèn/xóa đầu O(1) khi quản lý `head` |
| Phải xóa nhanh một phần tử khi **đã giữ tham chiếu trực tiếp đến nút** | Danh sách liên kết đôi | Nối `prev`/`next` và cập nhật hai đầu trong O(1) |
| Hàng đợi FIFO thường xuyên thêm cuối và lấy đầu | Hàng đợi dùng mảng vòng hoặc danh sách có `head`/`tail` | Cả hai có thể đạt O(1) amortized hoặc O(1) cho thao tác chính |
| Cấu trúc cần truy cập cha/con qua chỉ số theo công thức, như binary heap | Mảng | Với heap nhị phân: con của `i` ở `2i+1`, `2i+2` (chỉ số từ 0) |
| Cây có hình dạng thay đổi, các nút nối cha/con linh hoạt | Nút liên kết | Liên kết mô tả trực tiếp quan hệ giữa các nút |

Một vài ứng dụng kết hợp nhiều cách biểu diễn. Ví dụ **LRU cache** thường kết hợp bảng băm để tìm phần tử theo khóa với danh sách liên kết đôi để chuyển hoặc bỏ phần tử khi đã có nút tương ứng. Nhờ bảng băm, bước định vị không cần duyệt tuyến tính danh sách; hiệu năng trung bình của thao tác phụ thuộc thêm vào giả định về bảng băm. **Stack** và **queue** cũng có thể xây từ mảng hay danh sách liên kết; tên cấu trúc dữ liệu trừu tượng không bắt buộc một cách tổ chức bộ nhớ duy nhất.

## 7. Những nhầm lẫn cần tránh

**“Mọi phần tử trong một mảng đều là các đối tượng nằm sát nhau.”** Không nhất thiết. Trong một mảng chứa tham chiếu, các *ô tham chiếu* nằm liên tiếp, còn đối tượng đích có thể phân tán. Phải xác định chính xác phần tử vật lý của vùng chứa là gì.

**“Danh sách liên kết chèn ở vị trí bất kỳ đều O(1).”** Chỉ đúng khi đã có nút phù hợp để sửa liên kết. Nếu cần tìm nút ở chỉ số `i`, bước tìm là O(n).

**“Mảng động thêm cuối luôn O(1).”** Có thể có một lần O(n) khi cấp phát lại; O(1) chỉ là độ phức tạp *amortized* trong điều kiện chính sách tăng dung lượng thích hợp.

**“Nút liên kết luôn nằm xa nhau.”** Không có bảo đảm chúng nằm xa hoặc gần. Điều được bảo đảm là thứ tự logic dựa trên liên kết, và các nút **không cần** nằm liên tiếp.

**“Hai cấu trúc cùng O(n) sẽ chạy nhanh tương đương.”** Big-O bỏ qua hệ số hằng, cache, allocator và kích thước dữ liệu. Hiệu năng nên được đo với tải sử dụng thực tế.

**“Thêm một con trỏ luôn là không đáng kể.”** Với hàng triệu nút nhỏ, `next`, `prev`, padding và metadata cấp phát có thể chiếm lượng bộ nhớ lớn hơn chính dữ liệu.

## 8. Tự kiểm tra bằng ba tình huống

1. Một ứng dụng đọc `scores[i]` hàng triệu lần với chỉ số `i` thay đổi ngẫu nhiên. **Cách biểu diễn nào thuận lợi?** Mảng liên tiếp, vì phần tử được xác định bằng công thức địa chỉ O(1); danh sách liên kết phải lần theo các nút.
2. Một danh sách liên kết đơn có 100.000 nút và chỉ có `head`. Cần “chèn sau nút mang giá trị 42”. **Tổng chi phí có phải O(1)?** Không; tìm nút giá trị 42 có thể O(n), rồi chèn mới O(1).
3. Một queue cần `enqueue` ở cuối và `dequeue` ở đầu. **Có cần dùng nút liên kết để đạt O(1)?** Không; mảng vòng (circular buffer) có thể đạt các thao tác này trong O(1) khi còn dung lượng, và mảng vòng động có thể đạt O(1) amortized cho việc mở rộng.

## 9. Ghi nhớ để vận dụng

- **Liên tiếp:** tính được địa chỉ theo chỉ số, hiệu quả cache tốt; việc chèn/xóa giữa dãy thường phải dịch phần tử; mảng động có thể phải cấp phát lại.
- **Liên kết:** mô tả thứ tự bằng con trỏ/tham chiếu, dễ nối và tách nút khi đã biết vị trí; việc tìm theo chỉ số thường phải duyệt và mỗi nút có chi phí bộ nhớ bổ sung.
- **Chọn theo thao tác thực tế:** số lần đọc ngẫu nhiên, vị trí chèn/xóa có sẵn hay phải tìm, khối lượng dữ liệu, yêu cầu bộ nhớ và hiệu năng đo được. Độ phức tạp Big-O và bố trí bộ nhớ phải được xem xét cùng nhau.
