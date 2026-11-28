# Giá trị, địa chỉ, con trỏ, tham chiếu và tính gián tiếp

Một cấu trúc dữ liệu không chỉ lưu **giá trị** mà còn phải xác định cách chương trình **tìm được** giá trị đó. Mảng thường dựa vào vị trí có thể tính từ chỉ số; danh sách liên kết, cây và nhiều biểu diễn đồ thị lại dựa vào các liên kết đến vùng lưu trữ khác. Để hiểu đúng các cấu trúc này, cần phân biệt rõ **giá trị**, **địa chỉ**, **con trỏ**, **tham chiếu** và thao tác **truy cập gián tiếp** (indirection).

Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES** về cấu trúc dữ liệu, các khái niệm này giúp phân tích bất biến và thao tác trên mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời lý giải độ phức tạp về thời gian, bộ nhớ khi lựa chọn cách biểu diễn.

## 1. Giá trị và địa chỉ: hai câu hỏi khác nhau

**Giá trị (value)** là dữ liệu một biểu thức/đối tượng biểu diễn, chẳng hạn số nguyên `42`, ký tự `'A'` hoặc một đối tượng chứa nhiều trường. **Địa chỉ (address)** định vị nơi một đối tượng được lưu trong không gian địa chỉ của chương trình. Hai biến chứa cùng giá trị có thể nằm ở hai vị trí khác nhau.

Xét chương trình C:

```c
#include <stdio.h>

int main(void) {
    int a = 42;
    int b = 42;

    printf("a = %d, b = %d\n", a, b);
    printf("&a = %p, &b = %p\n", (void *)&a, (void *)&b);
    return 0;
}
```

- `a` và `b` cùng có **giá trị** `42`.
- `&a` và `&b` là **địa chỉ** của hai biến khác nhau; chúng có vùng lưu trữ riêng trong ví dụ.
- `%p` dùng để hiển thị địa chỉ qua đối số kiểu `void *`. Địa chỉ thực tế phụ thuộc lần chạy, hệ điều hành và trình biên dịch; không nên giả định các địa chỉ cố định.

Sơ đồ minh họa (giả sử `int` chiếm bốn byte):

```text
Không gian địa chỉ (giả định)
0x1000  +----------+
        | a = 42   |   <-- địa chỉ &a = 0x1000
        +----------+
 ...
0x2000  +----------+
        | b = 42   |   <-- địa chỉ &b = 0x2000
        +----------+

Giá trị giống nhau; danh tính và vị trí lưu trữ khác nhau.
```

Địa chỉ ở C là địa chỉ trong **không gian địa chỉ của tiến trình**, thường được hệ điều hành/bộ xử lý ánh xạ tới bộ nhớ vật lý. Không nên đồng nhất một giá trị địa chỉ in ra với địa chỉ vật lý của RAM. Nhiều ngôn ngữ cấp cao còn chủ động che giấu địa chỉ cụ thể.

### 1.1. Giá trị bằng nhau chưa chắc là cùng đối tượng

Có hai câu hỏi phải tách bạch:

1. **Bằng nhau về nội dung?** Hai giá trị có cùng thông tin hay không.
2. **Cùng một đối tượng?** Hai biến/tham chiếu có dẫn tới cùng một nơi lưu đối tượng hay không.

Ví dụ Python:

```python
left = [10, 20]
right = [10, 20]
alias = left

print(left == right)  # True: nội dung bằng nhau
print(left is right)  # False: hai list khác nhau
print(left is alias)  # True: alias trỏ tới cùng list

alias.append(30)
print(left)           # [10, 20, 30]
print(right)          # [10, 20]
```

`==` trong Python là phép kiểm tra bằng nhau theo ngữ nghĩa của kiểu dữ liệu; `is` kiểm tra danh tính đối tượng. Không nên dùng `is` thay `==` để so sánh nội dung.

## 2. Con trỏ: một giá trị dùng để chỉ tới đối tượng khác

Trong C, **con trỏ (pointer)** là giá trị của một kiểu con trỏ, có thể chỉ tới đối tượng/hàm thích hợp hoặc mang giá trị con trỏ null. Một **biến con trỏ** là biến lưu giá trị con trỏ. Với đối tượng `int x`:

```c
int x = 42;
int *p = &x;
```

- `x`: biến chứa số nguyên `42`.
- `&x`: biểu thức lấy địa chỉ của `x`.
- `p`: biến con trỏ kiểu `int *`, hiện lưu địa chỉ của `x`.
- `*p`: biểu thức **giải tham chiếu (dereference)**, truy cập đối tượng `int` mà `p` chỉ đến.

```text
             +-------------------+
p            |      &x           | ----+
             +-------------------+     |
                                       v
                                  +---------+
x                                 |   42    |
                                  +---------+
                                 Đối tượng int

p là một biến có vùng lưu trữ riêng; giá trị của p là địa chỉ của x.
```

Đọc biểu thức `*p` là “đối tượng được `p` trỏ tới”, **không phải** “địa chỉ của `p`”. Trong biểu thức `int *p`, dấu `*` là một phần cú pháp **khai báo kiểu**; còn `*p` khi dùng trong biểu thức là phép **giải tham chiếu**. Hai vai trò này dễ bị nhầm khi mới học C.

### 2.1. Đọc, ghi thông qua con trỏ

```c
#include <stdio.h>

int main(void) {
    int score = 70;
    int *p = &score;

    printf("score = %d, *p = %d\n", score, *p);
    *p = 95;
    printf("score = %d, *p = %d\n", score, *p);
    printf("address of score = %p\n", (void *)&score);
    printf("value stored in p = %p\n", (void *)p);
    printf("address of p = %p\n", (void *)&p);
    return 0;
}
```

Sau `*p = 95`, giá trị `score` cũng thành `95` vì đây là **cùng một đối tượng**, được truy cập qua hai cách. Địa chỉ `&p` lại là địa chỉ **của chính biến con trỏ**, khác khái niệm với địa chỉ mà `p` đang lưu.

Một cách phân biệt ngắn:

| Biểu thức | Ý nghĩa | Ví dụ về kiểu trong C |
| --- | --- | --- |
| `score` | Giá trị hiện có của biến `score` | `int` |
| `&score` | Địa chỉ biến `score` | `int *` |
| `p` | Giá trị con trỏ, đang chỉ đến `score` | `int *` |
| `*p` | Đối tượng được `p` trỏ tới (đọc hay ghi được khi hợp lệ) | lvalue kiểu `int` |
| `&p` | Địa chỉ của **biến con trỏ** `p` | `int **` |

### 2.2. Con trỏ có thể chuyển sang chỉ đối tượng khác

```c
int a = 10;
int b = 20;
int *p = &a;  /* *p = 10 */

p = &b;       /* Đổi nơi p trỏ tới, không thay đổi a */
*p = 99;      /* Bây giờ thay đổi b */
```

Sau đoạn này `a == 10` và `b == 99`. Gán `p = &b` là **đổi liên kết** của con trỏ; gán `*p = 99` là **đổi dữ liệu** tại nơi con trỏ chỉ tới. Sự khác biệt này xuất hiện liên tục khi viết thuật toán nối, tách nút trong danh sách liên kết và cây.

## 3. Tính gián tiếp: đi từ liên kết đến dữ liệu

**Truy cập trực tiếp** dùng ngay đối tượng/giá trị mà biểu thức xác định; **truy cập gián tiếp** thông qua một con trỏ hoặc tham chiếu để đến đối tượng đích.

```text
Trực tiếp:       score --------> [95]
Gián tiếp:       p ---> [&score] -------> [95]
                                             score
Hai đường truy cập đến cùng một giá trị đang lưu.
```

Một bước giải tham chiếu từ con trỏ hợp lệ như `*p` có chi phí thao tác hằng số theo số lượng phần tử, thường mô hình hóa **O(1)**. Nhưng **đi qua một chuỗi `n` con trỏ** như khi duyệt danh sách liên kết cần **O(n)** bước:

```text
head -> Node A -> Node B -> Node C -> NULL
          |         |         |
         10        20        30
```

Tại từng nút, chương trình cần đọc `next` rồi mới biết địa chỉ nút kế tiếp. Chuỗi phụ thuộc này còn có thể ảnh hưởng đến bộ nhớ đệm CPU, vì các nút không nhất thiết nằm liên tiếp. Ngược lại, mảng thường cho phép tính địa chỉ phần tử từ **địa chỉ đầu + chỉ số × kích thước phần tử**.

**Gián tiếp là cơ chế biểu diễn**, không đồng nghĩa với thuật toán chậm. Chỉ số lượng bước phải đi, tính cục bộ dữ liệu, và cách phần mềm quản lý bộ nhớ mới quyết định chi phí cụ thể.

## 4. Con trỏ null, con trỏ chưa khởi tạo và con trỏ hết hiệu lực

Ba tình huống sau rất khác nhau trong C:

| Trạng thái | Ý nghĩa | Có được giải tham chiếu? |
| --- | --- | --- |
| `int *p = NULL;` | Giá trị con trỏ null: cố ý không chỉ đến đối tượng hợp lệ | **Không** |
| `int *p;` (biến cục bộ không khởi tạo) | Giá trị không xác định/không được thiết lập | **Không**; không đọc giá trị để sử dụng |
| `p` còn giữ địa chỉ vùng đã `free` | Con trỏ treo (dangling): đối tượng đích hết vòng đời | **Không** |

Ví dụ kiểm tra trước khi dùng một con trỏ có thể là null:

```c
#include <stdio.h>

void print_if_present(const int *value) {
    if (value != NULL) {
        printf("%d\n", *value);
    }
}

int main(void) {
    int x = 5;
    print_if_present(&x);
    print_if_present(NULL);
    return 0;
}
```

Lưu ý: kiểm tra `p != NULL` **chỉ loại được trường hợp null**, không chứng minh `p` trỏ tới đối tượng còn sống hay kiểu được phép truy cập. C cần có kỷ luật về khởi tạo, vòng đời và quyền sở hữu bộ nhớ.

### 4.1. Vòng đời đối tượng và nguy cơ con trỏ treo

```c
#include <stdlib.h>

int main(void) {
    int *p = malloc(sizeof *p);
    if (p == NULL) return EXIT_FAILURE;

    *p = 42;
    free(p);
    p = NULL;  /* Tránh tiếp tục dùng chính biến p như con trỏ tới vùng cũ. */
    return EXIT_SUCCESS;
}
```

`malloc` xin một vùng nhớ đủ cho `int`; `free` kết thúc quyền sử dụng vùng được cấp phát. Nếu còn biến con trỏ khác mang địa chỉ đó, việc gán `p = NULL` **không** tự cập nhật các bản sao khác. Khi một đối tượng hết vòng đời, mọi liên kết trỏ tới nó đều phải được đánh giá lại.

Không được trả về địa chỉ biến tự động cục bộ để dùng sau khi hàm kết thúc:

```c
/* SAI: tuyệt đối không dùng kết quả trả về. */
int *invalid_address(void) {
    int local = 7;
    return &local;
}
```

Biến `local` hết vòng đời khi hàm trả về, nên địa chỉ của nó không còn chỉ đến một `int` còn sống. Trong triển khai an toàn, có thể trả về **giá trị** `int`, nhận con trỏ đầu ra do bên gọi cung cấp, hoặc cấp phát đối tượng với vòng đời phù hợp và quy định rõ ai có trách nhiệm giải phóng.

### 4.2. Bộ nhớ tự động và bộ nhớ cấp phát động

Ở C, biến cục bộ thông thường có **thời hạn lưu trữ tự động**; vùng do `malloc` tạo ra tồn tại cho đến khi `free` (hoặc khi tiến trình kết thúc). Thực tế, biến cục bộ thường được đặt trong stack frame và vùng cấp phát động thường thuộc heap, nhưng tiêu chuẩn C không bắt buộc mọi đối tượng cụ thể nằm ở cấu trúc bộ nhớ vật lý giống nhau trên mọi môi trường.

Quan trọng hơn địa điểm “stack/heap” là **vòng đời đối tượng** và **ai chịu trách nhiệm quản lý**. Cấu trúc dữ liệu dùng nút liên kết thường xin bộ nhớ động vì các nút cần tồn tại sau khi hàm tạo nút kết thúc.

## 5. Tham chiếu: liên hệ với cùng đối tượng ở ngôn ngữ khác

Từ **tham chiếu (reference)** thay đổi sắc thái theo ngôn ngữ:

- Trong **C++**, một tham chiếu như `int& ref = x;` là một tên khác (alias) cho đối tượng `x`. Tham chiếu đã được khởi tạo không thể chuyển sang ràng buộc một đối tượng khác bằng phép gán; `ref = y` gán **giá trị của `y` vào `x`**.
- Trong **Java**, biến kiểu tham chiếu như `Node next` mang tham chiếu đến đối tượng (hoặc `null`). Biến tham chiếu có thể được gán để tham chiếu đối tượng khác; cú pháp Java không cho phép lấy và tính toán địa chỉ như con trỏ C. Các kiểu nguyên thủy như `int` có ngữ nghĩa giá trị.
- Trong **Python**, tên biến được ràng buộc với đối tượng. Nhiều tên có thể cùng ràng buộc một đối tượng; gán lại một tên không tự thay đổi tên khác. Python không cung cấp phép giải tham chiếu con trỏ C ở mức thông thường.

Ví dụ C++ để phân biệt **con trỏ** và **tham chiếu C++**:

```cpp
#include <iostream>

int main() {
    int x = 10;
    int y = 20;

    int &ref = x;  // ref là alias của x
    int *ptr = &x; // ptr hiện chỉ đến x

    ref = y;       // x trở thành 20; ref vẫn là alias của x
    ptr = &y;      // ptr chuyển sang chỉ đến y
    *ptr = 30;     // y trở thành 30

    std::cout << x << " " << y << "\n"; // 20 30
}
```

Cả con trỏ và tham chiếu đều giúp truy cập một đối tượng “qua liên kết”, nhưng **cú pháp, khả năng ràng buộc lại, tính null và quy tắc vòng đời** khác nhau. Trong C++, tham chiếu vẫn có thể bị treo nếu đối tượng gốc hết vòng đời; việc tham chiếu thường không cần viết `*` không loại bỏ rủi ro đó.

### 5.1. Truyền tham số: đừng nhầm “truyền địa chỉ” với “truyền tham chiếu”

**C chỉ truyền tham số theo giá trị**. Khi truyền một con trỏ vào hàm, hàm nhận **bản sao của giá trị con trỏ**, nên có thể thay đổi đối tượng đích qua bản sao đó:

```c
#include <stdio.h>

void increment(int *p) {
    if (p != NULL) {
        ++*p;
    }
}

int main(void) {
    int count = 3;
    increment(&count);
    printf("%d\n", count); /* 4 */
    return 0;
}
```

Nếu trong hàm chỉ thực hiện `p = NULL;`, biến con trỏ ở phía người gọi **không đổi**: đây là phép gán vào bản sao `p` tại hàm.

**Java** cũng truyền tham số theo giá trị: đối với kiểu tham chiếu, hàm nhận bản sao tham chiếu. Hàm có thể sửa **trạng thái đối tượng** (nếu đối tượng cho phép), nhưng gán lại biến tham số không đổi biến tham chiếu của người gọi. **Python** thường được mô tả bằng ngữ nghĩa *call by sharing*: tên tham số cục bộ được ràng buộc tới cùng đối tượng; sửa nội dung đối tượng có thể nhìn thấy từ bên ngoài, gán lại tên thì không.

```python
def add_item(items):
    items.append("new")   # Sửa đối tượng list đang được chia sẻ.

def rebind(items):
    items = ["other"]     # Chỉ gán lại tên cục bộ.

values = ["first"]
add_item(values)
rebind(values)
print(values)             # ['first', 'new']
```

Đặc biệt khi xây dựng cây hoặc danh sách, cần biết thao tác đang **sửa đối tượng hiện có** hay đang **thay đổi liên kết/biến ở phía gọi**.

## 6. Nhiều tầng gián tiếp: con trỏ tới con trỏ

C cho phép một biến chứa địa chỉ của **biến con trỏ**. Ví dụ:

```c
int value = 7;
int *p = &value;
int **pp = &p;
```

```text
pp ------------> p ----------------> value
(int **)         (int *)             (int)
                 lưu &value          lưu 7

*pp  chính là p
**pp chính là value
```

- `pp` có kiểu `int **`: chỉ tới một đối tượng con trỏ kiểu `int *`.
- `*pp` có kiểu `int *`: chính là giá trị `p`.
- `**pp` có kiểu `int` khi đọc: truy cập đối tượng `value`.

Một ví dụ hữu dụng trong cấu trúc dữ liệu là **thay đổi nút đầu danh sách liên kết đơn** ở ngay trong hàm. Nếu chỉ truyền `Node *head`, hàm nhận bản sao `head`; gán lại bản sao đó không đổi `head` ở phía gọi. Truyền `Node **head` cho phép cập nhật con trỏ đầu thật sự.

### 6.1. Ví dụ: thêm nút vào đầu danh sách liên kết đơn

```c
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

/* Trả về 1 khi thành công, 0 khi không cấp phát được. */
int push_front(Node **head, int value) {
    if (head == NULL) return 0;

    Node *node = malloc(sizeof *node);
    if (node == NULL) return 0;

    node->value = value;
    node->next = *head;
    *head = node;
    return 1;
}

void clear_list(Node **head) {
    if (head == NULL) return;

    while (*head != NULL) {
        Node *removed = *head;
        *head = removed->next;
        free(removed);
    }
}

int main(void) {
    Node *head = NULL;

    if (!push_front(&head, 20) || !push_front(&head, 10)) {
        clear_list(&head);
        return EXIT_FAILURE;
    }

    for (const Node *cur = head; cur != NULL; cur = cur->next) {
        printf("%d ", cur->value);  /* In: 10 20 */
    }
    puts("");

    clear_list(&head);
    return EXIT_SUCCESS;
}
```

Diễn giải ba dòng cốt lõi trong `push_front`:

1. `node->next = *head;`: nút mới trỏ tới nút đầu cũ (có thể là `NULL`).
2. `*head = node;`: cập nhật **biến con trỏ đầu của người gọi** để nó trỏ tới nút mới.
3. Trả kết quả, trong khi cả nút mới và liên kết đầu đã được cập nhật đúng.

Khi danh sách rỗng, `*head == NULL`; thao tác vẫn đúng. Khi không cấp phát được, hàm không thay đổi danh sách. Tương tự, `clear_list` luôn chuyển `*head` đến nút tiếp theo **trước khi** giải phóng nút đang xóa, cuối cùng đưa `head` của người gọi về `NULL`.

**Bất biến biểu diễn:** từ `head`, đi theo `next` đến đúng các nút đang thuộc danh sách theo thứ tự và kết thúc ở `NULL`. Sửa sai một con trỏ có thể khiến nút bị mất khỏi danh sách, tạo vòng lặp hoặc làm chương trình truy cập vùng đã giải phóng.

**Một lựa chọn C khác:** hàm nhận `Node *head` và trả về giá trị `Node *` mới; phía gọi thực hiện `head = push_front(head, value)`. Cách này cũng hợp lệ nếu thiết kế rõ đường xử lý khi cấp phát thất bại.

## 7. Trường `next`, `prev`, `left`, `right`: liên kết là dữ liệu

Các cấu trúc dùng nút thường chứa trường liên kết. Với C, toán tử `->` kết hợp truy cập đối tượng qua con trỏ rồi lấy trường:

```c
node->next   /* Tương đương (*node).next nếu node hợp lệ. */
node->value  /* Tương đương (*node).value */
```

`node.next` dùng khi `node` là **đối tượng struct**, còn `node->next` dùng khi `node` là **con trỏ tới struct**.

### 7.1. Danh sách liên kết

```text
head --> [value=5 | next] --> [value=8 | next] --> NULL
```

Mỗi nút có `next` chỉ tới nút sau. Nếu đã có con trỏ đến nút đứng trước vị trí cần chèn, đổi một số liên kết là **O(1)**. Nếu phải tìm nút thứ `i` trước khi chèn, bước tìm có thể là **O(n)**.

Danh sách liên kết đôi thêm `prev`, hỗ trợ đi hai chiều và xóa nút khi có con trỏ tới chính nút đó trong **O(1)** nếu duy trì đúng `head`/`tail`; đổi lại mỗi nút tốn thêm một trường liên kết.

### 7.2. Cây nhị phân

```c
typedef struct TreeNode {
    int key;
    struct TreeNode *left;
    struct TreeNode *right;
} TreeNode;
```

```text
            [8]
           /   \
         [3]   [12]
          \
          [6]
```

Các trường `left`, `right` mô tả **quan hệ cha–con**, không yêu cầu nút con nằm gần nút cha trong bộ nhớ. Nếu cây là cây nhị phân tìm kiếm (BST), bất biến về thứ tự khóa cần được duy trì **ngoài** bất biến về liên kết; nếu là cây tổng quát thì không thể tự suy ra quy tắc BST chỉ từ con trỏ.

Một bước từ nút cha sang `left` hoặc `right` thường là **O(1)**; tìm kiếm qua `h` mức trên một cây tìm kiếm phù hợp có thể tốn **O(h)**. Khi cây suy biến thành một chuỗi dài `n` nút, `h` có thể bằng **O(n)**; nếu cân bằng thì chiều cao thường là **O(log n)**.

### 7.3. Đồ thị

Đồ thị có thể lưu theo **danh sách kề**: mỗi đỉnh lưu các đỉnh hàng xóm qua một danh sách/mảng chứa tham chiếu hoặc chỉ số đỉnh. Một cạnh logic `u -> v` có thể được biểu diễn bằng một liên kết hay một mã chỉ số, chứ không nhất thiết là một con trỏ máy C.

```text
A : B -> C
B : C
C : A
```

Nếu biểu diễn bằng các con trỏ tới nút/đỉnh, phải quản lý vòng đời và tránh liên kết treo khi xóa đỉnh. Nếu biểu diễn bằng chỉ số trong mảng, địa chỉ và chuyển dời bộ nhớ có quy tắc khác. **Tính gián tiếp** là ý tưởng chung; *con trỏ thô* chỉ là một trong nhiều cách hiện thực.

## 8. Bí quyết đọc sơ đồ địa chỉ, alias và liên kết

Xét trạng thái ban đầu:

```c
int a = 4, b = 9;
int *p = &a;
int *q = p;
```

```text
p ----+
      +----> a: 4
q ----+
            b: 9
```

Sau lần lượt các lệnh sau:

```c
*p = 6;
q = &b;
*q = 12;
```

Ta được:

```text
p --------> a: 6
q --------> b: 12
```

Vì `q = p` đã **sao chép giá trị địa chỉ** nên ban đầu `p` và `q` là hai biến con trỏ **đồng trỏ (aliasing)** tới `a`; thay `*p` được nhìn thấy khi đọc `*q`. Nhưng sau `q = &b`, chỉ **q đổi liên kết**, `p` vẫn trỏ đến `a`. Phân tích con trỏ tốt cần vẽ **từng đối tượng**, **mỗi biến con trỏ**, rồi cập nhật mũi tên theo thứ tự câu lệnh.

Một lỗi thường gặp là viết:

```c
Node *new_node = /* nút hợp lệ đã tạo */;
new_node->next = head;
head = new_node;
```

Đoạn trên **đúng nếu `head` là biến của cùng phạm vi muốn cập nhật**. Nhưng nếu `head` là **tham số kiểu `Node *` của hàm C**, việc gán đó chỉ thay tham số cục bộ, chưa cập nhật con trỏ của người gọi. Cần dùng `Node **`, trả về `Node *`, hoặc quản lý con trỏ đầu trong một đối tượng cấu trúc được truyền vào.

## 9. Cơ sở của việc an toàn bộ nhớ và quyền sở hữu

Với cấu trúc chứa liên kết, chương trình phải duy trì đồng thời:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **Tính hợp lệ (validity)** | Con trỏ/tham chiếu hiện có dẫn đến một đối tượng còn sống, đúng kiểu và được phép truy cập không? |
| **Vòng đời (lifetime)** | Đối tượng tồn tại từ lúc nào đến lúc nào? |
| **Quyền sở hữu (ownership)** | Ai chịu trách nhiệm hủy/giải phóng đối tượng? |
| **Đồng trỏ (aliasing)** | Có những đường truy cập nào cùng dẫn đến đối tượng này? |
| **Bất biến (invariant)** | Sau thao tác, các liên kết, đầu/cuối và số phần tử có còn nhất quán không? |

Trong C dùng `malloc`/`free`, các nút phải được giải phóng theo đúng quyền sở hữu; giải phóng một nút khi nút khác còn dùng địa chỉ của nó sẽ tạo nguy cơ truy cập sai. Trong **C++**, có thể dùng smart pointer như `std::unique_ptr`, `std::shared_ptr` hoặc tham chiếu không sở hữu khi phù hợp. Trong **Java/Python**, bộ gom rác thu hồi các đối tượng không còn truy cập được theo cơ chế của runtime, nhưng bản thân thuật toán vẫn phải quản lý liên kết đúng để không giữ đối tượng lâu ngoài ý muốn hoặc làm sai cấu trúc.

### 9.1. Các trường hợp cần tránh

- **Giải tham chiếu null:** `*NULL`, `node->next` khi `node == NULL`.
- **Đọc con trỏ chưa được thiết lập:** một biến `int *p;` cục bộ chưa gán không phải con trỏ hợp lệ mặc định.
- **Use-after-free:** tiếp tục truy cập nút sau khi đã `free`.
- **Double free:** giải phóng cùng vùng cấp phát nhiều lần khi chưa có cấp phát mới tương ứng.
- **Làm mất nút:** ghi đè `p->next` mà chưa lưu vị trí của chuỗi phía sau.
- **Tạo chu trình ngoài ý muốn:** một nút trỏ ngược vào nút trước trong danh sách vốn được giả định kết thúc tại `NULL`.
- **Nhầm quyền sở hữu:** hai nơi cùng nghĩ mình sở hữu một nút và cùng tìm cách hủy nó.
- **Nhầm so sánh con trỏ:** trong C, `p == q` so sánh giá trị con trỏ theo quy tắc ngôn ngữ, không so sánh nội dung `*p` và `*q`.

Dấu hiệu sai có thể là lỗi chương trình, vòng lặp vô tận, mất dữ liệu, rò rỉ bộ nhớ, hoặc hành vi không xác định. Với C/C++, bộ kiểm tra như AddressSanitizer có thể giúp phát hiện nhiều lỗi truy cập bộ nhớ khi kiểm thử, nhưng không thay thế việc kiểm tra bất biến và vòng đời.

## 10. Địa chỉ, phép toán con trỏ và giới hạn khi lập trình cấu trúc dữ liệu

Với một mảng C có các phần tử liên tiếp:

```c
int data[] = {11, 22, 33};
int *p = data;    /* Trỏ đến data[0]. */

int first  = *p;       /* 11 */
int second = *(p + 1); /* 22 */
int third  = p[2];     /* 33 */
```

`p + 1` đi thêm **một phần tử `int`**, không phải thêm một byte. Phép toán con trỏ chỉ được dùng trong phạm vi mảng tương ứng (kể cả vị trí một-phần-tử-sau-cuối để so sánh/điều khiển); **không được giải tham chiếu vị trí sau cuối**. Không có quyền dùng phép cộng tùy ý lên con trỏ để đoán vị trí của nút liên kết khác vì các nút không nhất thiết cùng mảng.

Mảng C trong nhiều biểu thức được chuyển thành con trỏ đến phần tử đầu, nhưng **mảng không phải là biến con trỏ**: `sizeof data` cho kích thước **toàn bộ mảng** trong phạm vi khai báo (khi `data` còn là mảng), trong khi `sizeof p` cho kích thước biến con trỏ. Đặc biệt, khi truyền mảng vào tham số hàm `int data[]`, tham số được điều chỉnh thành `int *data`; trong hàm, `sizeof data` không cho số byte của mảng gốc.

Các cấu trúc như **binary heap** thường dùng chỉ số để xác định con/cha trong mảng; liên kết ở đây là **quan hệ logic tính từ chỉ số**, không cần trường con trỏ ở mỗi phần tử. Chọn con trỏ hay chỉ số là một quyết định thiết kế biểu diễn.

## 11. Chi phí thời gian và bộ nhớ của tính gián tiếp

Khi đánh giá cấu trúc dữ liệu, cần xét cả chi phí của **đối tượng đích** và của **liên kết**:

| Biểu diễn | Chi phí truy cập điển hình | Chi phí bộ nhớ liên quan |
| --- | --- | --- |
| Một giá trị ở vị trí đã biết | O(1) | Dung lượng của giá trị và căn chỉnh |
| Một con trỏ hợp lệ tới đối tượng | O(1) cho một lần giải tham chiếu | Một giá trị con trỏ, căn chỉnh/padding khi đặt trong struct |
| Chuỗi `n` nút liên kết | O(n) để lần lượt đi qua `n` nút | Mỗi nút có dữ liệu, liên kết, có thể thêm chi phí cấp phát |
| Mảng `n` phần tử cùng kiểu | O(1) theo chỉ số; O(n) để duyệt toàn bộ | Vùng lưu trữ liên tiếp; mảng động có thể có capacity dự phòng |
| Cây liên kết có chiều cao `h` | O(h) để theo một đường từ gốc xuống lá | Con trỏ con tại mỗi nút, và overhead cấp phát/căn chỉnh |

Ở hệ 64 bit phổ biến, một giá trị con trỏ thường chiếm **8 byte**, nhưng đây không phải bảo đảm chung cho mọi kiến trúc hoặc kiểu con trỏ. Kích thước struct còn chịu ảnh hưởng của căn chỉnh, nên không nên tính kích thước nút chỉ bằng cách cộng kích thước các trường rồi mặc định không có padding.

**Big-O không đo trực tiếp độ trễ bộ nhớ.** Việc theo nhiều con trỏ rải rác có thể phát sinh cache miss; một mảng liên tiếp dù phải dịch phần tử lại có thể được CPU tối ưu rất tốt. Hiệu năng thật cần xem tần suất thao tác, kích thước dữ liệu, kiểu cấp phát, khả năng sử dụng cache và kết quả đo.

## 12. Chọn biểu diễn cho yêu cầu cụ thể

**Bài toán A – đọc phần tử thứ `i` nhiều lần:** mảng/mảng động thường hợp lý vì truy cập theo chỉ số trực tiếp. Không cần lặp lại qua hàng loạt `next` để đến phần tử thứ `i`.

**Bài toán B – di chuyển nút bất kỳ giữa các vị trí khi đã có tham chiếu tới nút:** danh sách liên kết đôi có thể thay đổi một số `next`/`prev` trong O(1), với điều kiện xử lý đúng các đầu mút và tính hợp lệ của tham chiếu. Nếu phải tìm vị trí trước, vẫn cần cộng chi phí tìm kiếm.

**Bài toán C – cache theo khóa:** bảng băm dùng ánh xạ từ khóa tới giá trị hoặc tham chiếu nút; kết hợp danh sách liên kết đôi có thể hỗ trợ chiến lược LRU. Bảng băm thường có truy cập trung bình O(1) dưới giả định phù hợp, còn đổi vị trí một nút đã biết trong danh sách đôi là O(1). Bước định vị và bước đổi liên kết phải được phân tích riêng.

**Bài toán D – hàng đợi:** queue có thể dùng mảng vòng với hai chỉ số hoặc nút liên kết với `head` và `tail`. Cả hai có thể cung cấp thêm/cuối và lấy/đầu hiệu quả, nhưng khác nhau về số lần cấp phát, tính liên tục bộ nhớ và cách tăng dung lượng.

**Bài toán E – đồ thị biến đổi nhiều:** dùng danh sách kề chứa chỉ số hoặc tham chiếu tùy cách quản lý đỉnh, vòng đời, yêu cầu xóa và khả năng thay đổi vị trí vùng lưu trữ. Không có nghĩa biểu diễn nào dùng con trỏ cũng tối ưu cho mọi đồ thị.

## 13. Bài tập tự kiểm tra có giải thích

### Câu 1. Dự đoán giá trị

```c
int x = 3;
int y = 8;
int *a = &x;
int *b = a;
*b = 5;
a = &y;
*a = 10;
```

**Đáp án:** `x == 5`, `y == 10`, `*a == 10`, `*b == 5`. Ban đầu `a` và `b` cùng trỏ `x`; việc đổi `a = &y` không làm `b` đổi theo.

### Câu 2. Nhận diện địa chỉ

Giả sử `int number = 7; int *p = &number;`. Ba biểu thức `number`, `p`, `&p` mang thông tin gì?

**Đáp án:** `number` cho giá trị `7`; `p` cho địa chỉ của `number`; `&p` cho địa chỉ **của biến con trỏ `p`**. Không được nhầm `p` với `&p`.

### Câu 3. Vì sao thay `head` trong hàm có thể không hiệu quả?

Một hàm C khai báo `void reset(Node *head) { head = NULL; }`. Gọi `reset(head);` có làm biến `head` của người gọi thành `NULL` không?

**Đáp án:** **Không.** Tham số là bản sao của giá trị con trỏ. Muốn thay con trỏ phía gọi, có thể dùng `void reset(Node **head) { if (head) *head = NULL; }` rồi gọi `reset(&head);`. Đây chỉ là minh họa thao tác gán; với danh sách đã có nút được cấp phát, chỉ xóa `head` mà không giải phóng đúng cách sẽ **làm mất đường truy cập và rò rỉ bộ nhớ**.

### Câu 4. Phân tích độ phức tạp

Có danh sách liên kết đơn với 100.000 nút, chỉ biết `head`. Muốn sửa giá trị ở nút thứ 80.000 thì việc `*p = value` sau khi đã tìm được `p` là O(1). Tổng công việc là bao nhiêu?

**Đáp án:** **O(n)** theo số nút vì phải duyệt tới vị trí cần cập nhật. Chi phí một bước giải tham chiếu không đại diện cho toàn bộ chi phí tìm đích.

### Câu 5. Bẫy vòng đời

```c
int *p = malloc(sizeof *p);
int *q = p;
free(p);
p = NULL;
```

Có thể dùng `*q` không?

**Đáp án:** **Không.** `q` vẫn là bản sao địa chỉ vùng đã được `free`, nên là con trỏ treo. Việc đặt `p = NULL` không làm `q` hợp lệ lại.

## 14. Những điểm cần ghi nhớ

- **Giá trị** nói về dữ liệu; **địa chỉ** nói về vị trí của đối tượng. Hai biến có cùng giá trị không có nghĩa là cùng đối tượng.
- **Con trỏ** mang thông tin liên kết tới đối tượng; **giải tham chiếu** dùng liên kết đó để truy cập dữ liệu. `p`, `*p` và `&p` là ba khái niệm khác nhau.
- **Tham chiếu** không có một cú pháp hay quy tắc thống nhất giữa C++, Java và Python; phải hiểu ngữ nghĩa của ngôn ngữ đang dùng.
- **Tính gián tiếp** là nền tảng của danh sách liên kết, cây và nhiều đồ thị. Một bước đi thường O(1), nhưng đi qua `n` nút sẽ là O(n).
- **Vòng đời, aliasing, quyền sở hữu và bất biến liên kết** quyết định tính đúng đắn. Khi chọn cấu trúc dữ liệu, hãy phân tích cả thao tác định vị phần tử lẫn thao tác thay đổi liên kết và chi phí bộ nhớ đi kèm.
