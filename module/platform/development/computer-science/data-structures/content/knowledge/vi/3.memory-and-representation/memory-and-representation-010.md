# Giá trị rỗng, nút canh gác và quy ước biểu diễn rỗng

Một danh sách liên kết không có phần tử sẽ lưu gì ở `head`? Một queue có `head == tail` là đang rỗng hay đã đầy? Khi xóa khóa trong bảng băm dùng open addressing, có thể đánh dấu ô ấy thành “chưa từng dùng” không? Trong cây đỏ–đen, một lá vắng mặt được biểu diễn bằng `NULL` hay bằng nút `NIL` đặc biệt?

Các câu hỏi trên đều liên quan tới **quy ước biểu diễn trạng thái rỗng**. Một lựa chọn tưởng nhỏ như `NULL`, chỉ số `-1`, `size == 0` hay **nút canh gác (sentinel/dummy node)** có thể quyết định bất biến của cấu trúc, cách cài đặt thao tác biên, độ an toàn bộ nhớ và lượng metadata cần lưu.

Bài thuộc chương **Bộ nhớ và biểu diễn** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là xây dựng tư duy chính xác khi hiện thực **mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị**: xác định trạng thái hợp lệ, chọn biểu diễn rỗng rõ ràng, phân tích chi phí thời gian và bộ nhớ, rồi kiểm thử các tình huống biên trước khi quyết định cách biểu diễn thích hợp.

Sau khi học, bạn có thể:

- Phân biệt **không có phần tử**, **phần tử có giá trị rỗng**, **ô chưa từng sử dụng**, **ô đã xóa** và **nút kỹ thuật không mang dữ liệu**.
- Định nghĩa một **bất biến** để nhận biết trạng thái rỗng; chứng minh thao tác thêm, lấy ra, tìm kiếm và xóa giữ bất biến đó.
- Cài đặt danh sách đơn với **dummy head** và danh sách đôi với **sentinel vòng** an toàn về liên kết và giải phóng.
- Giải thích cách nhận biết rỗng/đầy ở mảng vòng, tombstone của bảng băm và `NIL` sentinel trong cây.
- Phân tích đánh đổi giữa nhánh điều kiện, metadata và bộ nhớ, tránh dùng giá trị dữ liệu hợp lệ làm “tín hiệu không tồn tại”.

## 1. “Rỗng” không chỉ có một nghĩa

Trong cấu trúc dữ liệu, cần phân biệt ít nhất năm tình huống.

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Container rỗng** | Cấu trúc chứa **0 phần tử logic** | Danh sách chưa thêm nút, stack chưa push |
| **Phần tử có giá trị rỗng** | Vẫn có một phần tử, nhưng payload được phép là `None`/`null` | `[None]` có độ dài 1 trong Python |
| **Ô chưa dùng** | Vị trí lưu trữ chưa chứa mục nào từ lúc khởi tạo | Slot `EMPTY` của bảng băm mở |
| **Ô đã xóa** | Từng có mục, đã bỏ mục, cần giữ dấu vết cho thuật toán | Tombstone `DELETED` của bảng băm |
| **Nút kỹ thuật/canh gác** | Đối tượng dùng để làm mốc liên kết, **không được tính là dữ liệu** | Nút `head` giả trong danh sách đơn |

Nếu nhầm các trạng thái, thuật toán có thể dừng tìm kiếm quá sớm, truy cập dữ liệu không tồn tại, làm sai `size` hoặc giải phóng nhầm nút canh gác.

### 1.1. Ví dụ đơn giản: `[]` và `[None]`

```python
empty = []
one_null_value = [None]

print(len(empty))          # 0
print(len(one_null_value)) # 1

print(empty == one_null_value)  # False
```

`None` ở đây là **giá trị của một phần tử hợp lệ**, không tự đánh dấu danh sách rỗng. Việc `list.pop()` trên danh sách rỗng gây `IndexError` là cách API biểu diễn **thất bại vì không có phần tử** khác với trường hợp phần tử thực sự là `None`.

### 1.2. Rỗng, không tìm thấy và kết thúc chuỗi khác nhau

Trong C, con trỏ `NULL` thường được dùng để chỉ **không có đối tượng đích** cho một liên kết. Với danh sách đơn kết thúc tại `NULL`:

```text
Danh sách rỗng:    head --> NULL
Danh sách 1 nút:   head --> [10 | next=NULL]
Danh sách 3 nút:   head --> [10] --> [20] --> [30] --> NULL
```

Trường `next == NULL` của nút cuối biểu diễn **không có nút kế tiếp**; nó không biến nút cuối thành nút “rỗng”. Tương tự, `root == NULL` có thể biểu diễn cây rỗng; nhưng một nút có một nhánh con `NULL` vẫn có thể là nút thật trong cây không rỗng.

**Nguyên tắc:** trạng thái rỗng thuộc về **container hoặc một liên kết**, còn giá trị payload thuộc về **phần tử**. Chỉ gộp hai tầng ý nghĩa khi API có hợp đồng chặt chẽ và không làm mất khả năng biểu diễn dữ liệu hợp lệ.

## 2. Bất biến biểu diễn rỗng

**Bất biến (invariant)** là điều kiện phải đúng trước và sau mỗi thao tác công khai trên cấu trúc. Định nghĩa rỗng cần viết thành một mệnh đề có thể kiểm tra.

Ví dụ phổ biến:

| Cấu trúc | Một quy ước rỗng | Bất biến đi kèm |
| --- | --- | --- |
| Mảng động | `size == 0` | `0 <= size <= capacity`; không phần tử logic nào ở vùng `[0, size)` khi size 0 |
| Danh sách đơn không sentinel | `head == NULL` | `size == 0` khi và chỉ khi `head == NULL` |
| Danh sách đơn có dummy head | `dummy.next == NULL` | Dummy **luôn tồn tại**, không tính vào `size` |
| Danh sách đôi sentinel vòng | `sentinel.next == &sentinel` | `sentinel.prev == &sentinel` khi rỗng |
| Stack lưu bằng mảng | `size == 0` hoặc `top == -1` | Chỉ số đỉnh phải tương thích với số phần tử |
| Queue vòng với `count` | `count == 0` | `0 <= count <= capacity` |
| Binary heap mảng | `size == 0` | `0 <= size <= capacity`; chỉ vùng `[0,size)` là heap logic |
| Cây con trỏ thông thường | `root == NULL` | Con trỏ rỗng là vắng nút |
| Cây có `NIL` sentinel | `root == NIL` | `NIL` không được tính là khóa/nút logic |
| Bảng băm open addressing | `size == 0` | Các ô có trạng thái `EMPTY/OCCUPIED/DELETED` riêng |

Quy ước có thể khác nhau giữa thư viện. Điều quan trọng là **đừng trộn nửa cách này với nửa cách kia**: ví dụ kiểm tra `head == NULL` trong một danh sách luôn có dummy head sẽ không bao giờ báo rỗng.

### 2.1. Chu trình giữ bất biến qua thao tác

Với bất kỳ thao tác nào, kiểm tra ba giai đoạn:

1. **Trước thao tác:** container đang ở trạng thái hợp lệ; rỗng và không rỗng đều phải được hỗ trợ.
2. **Trong thao tác:** nếu có cấp phát hoặc sửa liên kết, xác định trạng thái tạm; không để API công bố nửa chừng một cấu trúc sai.
3. **Sau thao tác:** mọi bất biến được khôi phục; `size`, `head/tail`, liên kết ngược và quyền sở hữu phản ánh chính xác các phần tử còn sống.

Đặc biệt, các chuyển trạng thái **0 → 1**, **1 → 0** và **n → 0** thường là nơi nhiều lỗi xuất hiện.

## 3. Giá trị dấu hiệu (sentinel value) và bài toán đụng độ dữ liệu

Một cách biểu diễn “không có phần tử” là trả về giá trị đặc biệt như `-1`, `0` hoặc `NULL`. Cách này đơn giản nhưng **chỉ đúng khi giá trị ấy không thể là dữ liệu hợp lệ**, hoặc hợp đồng API có quy tắc phân biệt rõ ràng.

### 3.1. Lỗi khi dùng `-1` làm dấu hiệu stack rỗng

Giả sử stack chứa số nguyên có thể âm:

```c
/* Ví dụ API mơ hồ: */
int pop_or_minus_one(void);

/* Kết quả -1 không phân biệt:
   - Stack rỗng, hoặc
   - Stack có phần tử thật bằng -1. */
```

Nếu `-1` là giá trị hợp lệ, không thể diễn giải kết quả duy nhất bằng cách kiểm tra `result == -1`.

### 3.2. API tốt hơn: tách trạng thái khỏi payload

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

typedef struct Stack {
    int items[4];
    size_t size;
} Stack;

bool stack_push(Stack *s, int value) {
    if (s == NULL || s->size == 4) return false;
    s->items[s->size++] = value;
    return true;
}

/* false: không có phần tử để lấy; true: *out nhận giá trị hợp lệ. */
bool stack_pop(Stack *s, int *out) {
    if (s == NULL || s->size == 0) return false;
    --s->size;
    if (out != NULL) {
        *out = s->items[s->size];
    }
    return true;
}

int main(void) {
    Stack s = {{0}, 0};
    int value;

    stack_push(&s, -1);
    if (stack_pop(&s, &value)) {
        printf("Gia tri: %d\n", value); /* -1, hoàn toàn hợp lệ. */
    }
    if (!stack_pop(&s, &value)) {
        puts("Stack rong");
    }
    return 0;
}
```

Ở đây `bool` báo **có lấy được phần tử hay không**, còn `*out` giữ **giá trị phần tử**, kể cả `-1` hay `0`. Hàm không cần cấp phát động; thêm và lấy đỉnh O(1) khi có dung lượng/không rỗng.

Trong C++ có thể dùng `std::optional<T>` để biểu diễn có/không có kết quả, trong Rust dùng `Option<T>`, trong Python có thể ném ngoại lệ hoặc trả một object dấu hiệu không trùng dữ liệu. Lựa chọn phụ thuộc kiểu dữ liệu và quy ước thư viện.

### 3.3. `None` có thể là dữ liệu hợp lệ: dùng sentinel object riêng

```python
MISSING = object()

config = {"timeout": None, "retries": 0}

timeout = config.get("timeout", MISSING)
hostname = config.get("hostname", MISSING)

print(timeout is MISSING)   # False: khóa tồn tại, giá trị là None
print(hostname is MISSING)  # True: không có khóa hostname
```

Một object sentinel độc nhất trong Python có lợi khi `None` là giá trị có ý nghĩa. Nên so sánh bằng `is` để kiểm tra **danh tính sentinel**, không dùng `==` vì loại đối tượng tùy biến có thể định nghĩa phép bằng nhau đặc biệt.

**Đừng nhầm sentinel object với sentinel node:** sentinel object có thể chỉ là giá trị đánh dấu `MISSING` trong API, còn sentinel node là **một nút liên kết thực** được đặt vào cấu trúc để làm mốc thao tác.

## 4. Nút canh gác (sentinel/dummy node) là gì?

**Nút canh gác** là nút tồn tại nhằm đơn giản hóa thao tác ở ranh giới cấu trúc, thường **không chứa dữ liệu logic** và **không được đếm** vào số phần tử.

Danh sách đơn **không có** dummy head:

```text
Rỗng:     head -> NULL
Có nút:   head -> [10] -> [20] -> NULL
```

Danh sách đơn **có** dummy head:

```text
Rỗng:     head -> [DUMMY | next=NULL]
Có nút:   head -> [DUMMY] -> [10] -> [20] -> NULL

DUMMY không phải phần tử 0 của dãy; chỉ là mốc liên kết.
```

Lợi ích chính: thao tác tại đầu danh sách có thể dùng cùng quy tắc sửa liên kết như thao tác sau một nút bình thường. Thay vì hai nhánh “xóa đầu” và “xóa sau nút trước”, ta luôn có một **nút đứng trước** phần tử đầu tiên.

### 4.1. Dummy head và dummy tail khác nhau

- **Dummy head:** nút giả đứng **trước** phần tử đầu; hữu ích khi chèn/xóa ở đầu hoặc khi cần con trỏ nút trước.
- **Dummy tail:** nút giả đứng **sau** phần tử cuối; có thể giúp đơn giản hóa thao tác ở cuối với quy tắc liên kết thích hợp.
- **Sentinel vòng:** một nút duy nhất đóng cả vai trò mốc đầu và mốc cuối trong danh sách đôi vòng.

Các từ “dummy” và “sentinel” đôi khi được dùng thay nhau, nhưng không thể suy ra chỉ từ tên rằng nút đó ở đầu, cuối hay đóng thành vòng. Hãy xem **bất biến liên kết** của hiện thực cụ thể.

### 4.2. Sentinel có nằm trong vùng heap không?

Không bắt buộc. Sentinel có thể là trường nhúng trong đối tượng container, nút cấp phát riêng trên heap, hay một đối tượng dùng chung theo chính sách cụ thể. Dù ở đâu, phải **quản lý vòng đời đúng**:

- Sentinel nhúng trực tiếp trong container **không được gọi `free` riêng**.
- Sentinel được cấp phát động phải được thu hồi theo hợp đồng của container.
- Sentinel dùng chung giữa nhiều cây không được giải phóng theo từng nhánh.
- Nếu sentinel chứa self-pointer, **sao chép cấu trúc container bằng copy byte** có thể khiến liên kết chỉ về sentinel của bản gốc, không phải bản mới.

## 5. Ví dụ C hoàn chỉnh: danh sách đơn với dummy head nhúng

Thiết kế dùng `List` sở hữu các nút dữ liệu; `dummy` luôn tồn tại bên trong `List` và không được tính vào `size`. Chỉ các nút dữ liệu mới do `malloc` tạo ra.

Bất biến:

1. `list.dummy.next == NULL` khi và chỉ khi `list.size == 0`.
2. Từ `dummy.next` đi qua `next` có đúng `size` nút dữ liệu, không chu trình và kết thúc ở `NULL`.
3. `dummy.value` không có ý nghĩa nghiệp vụ, **không được xuất ra như phần tử**.
4. Mỗi nút dữ liệu thuộc quyền sở hữu duy nhất của danh sách và được giải phóng đúng một lần.
5. Không sao chép `List` bằng phép gán struct như hai container sở hữu độc lập: trường `next` sẽ bị sao chép nông.

### 5.1. Mã minh họa có thể biên dịch độc lập

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

typedef struct List {
    Node dummy;             /* Nút canh gác nhúng, không malloc. */
    size_t size;
} List;

void list_init(List *list) {
    if (list == NULL) return;
    list->dummy.value = 0; /* Không được tính là dữ liệu. */
    list->dummy.next = NULL;
    list->size = 0;
}

bool list_push_front(List *list, int value) {
    if (list == NULL || list->size == (size_t)-1) return false;

    Node *node = malloc(sizeof *node);
    if (node == NULL) return false;

    node->value = value;
    node->next = list->dummy.next;

    list->dummy.next = node;
    ++list->size;
    return true;
}

/* Xóa nút có giá trị value xuất hiện đầu tiên. */
bool list_erase_first(List *list, int value) {
    if (list == NULL) return false;

    Node *prev = &list->dummy;
    while (prev->next != NULL) {
        Node *current = prev->next;

        if (current->value == value) {
            prev->next = current->next;
            --list->size;
            free(current);           /* Dummy không bao giờ bị free. */
            return true;
        }
        prev = current;
    }
    return false;
}

bool list_pop_front(List *list, int *out) {
    if (list == NULL || list->dummy.next == NULL) return false;

    Node *first = list->dummy.next;
    if (out != NULL) *out = first->value;

    list->dummy.next = first->next;
    --list->size;
    free(first);
    return true;
}

void list_clear(List *list) {
    if (list == NULL) return;

    Node *p = list->dummy.next;
    while (p != NULL) {
        Node *next = p->next;  /* Đọc trước khi free(p). */
        free(p);
        p = next;
    }
    list->dummy.next = NULL;
    list->size = 0;
}

void list_print(const List *list) {
    if (list == NULL) return;
    const Node *p = list->dummy.next;
    while (p != NULL) {
        printf("%d ", p->value);
        p = p->next;
    }
    puts("");
}

int main(void) {
    List list;
    list_init(&list);

    printf("Empty? %d\n", list.dummy.next == NULL); /* 1 */
    list_print(&list);                              /* Dòng trống */

    if (!list_push_front(&list, 20) ||
        !list_push_front(&list, 10)) {
        list_clear(&list); /* Dọn cả trạng thái tạo được một phần. */
        return EXIT_FAILURE;
    }

    list_print(&list);              /* 10 20 */
    list_erase_first(&list, 10);    /* Xóa đầu như một trường hợp chung. */
    list_print(&list);              /* 20 */

    int popped = 0;
    if (list_pop_front(&list, &popped)) {
        printf("Popped = %d\n", popped); /* 20 */
    }

    printf("Empty? %d; size=%zu\n",
           list.dummy.next == NULL, list.size);      /* 1; size=0 */

    list_clear(&list);
    return EXIT_SUCCESS;
}
```

**Tại sao dummy head hữu ích?** Khi xóa, `prev` bắt đầu từ `&list->dummy`. Nếu phần tử cần xóa nằm ở đầu, `prev->next` chính là `dummy.next`; nếu nằm ở giữa, `prev->next` là liên kết của nút trước. Không cần nhánh riêng xử lý `head`.

### 5.2. Chi phí và các trường hợp biên

| Thao tác | Trạng thái cần hỗ trợ | Thời gian |
| --- | --- | --- |
| `list_init` | Container chưa khởi tạo | O(1) |
| `list_push_front` | Rỗng hoặc không rỗng | O(1) bước liên kết, cộng chi phí cấp phát |
| `list_pop_front` | Rỗng → trả `false`; có 1 hoặc nhiều nút → xóa đầu | O(1) |
| `list_erase_first` | Không thấy, xóa đầu, xóa giữa, xóa cuối | O(n) xấu nhất vì cần tìm |
| `list_clear` | Rỗng, 1 nút, nhiều nút | O(n) với `n` nút dữ liệu |

Dummy head chiếm **O(1) dung lượng bổ sung cho mỗi container**, không thêm một nút cho mỗi phần tử. Nó giảm một số nhánh đặc biệt, **không thay đổi** độ phức tạp của tìm kiếm từ O(n) thành O(1). Để xử lý an toàn, vẫn phải kiểm tra điều kiện rỗng trước khi dereference nút dữ liệu.

## 6. Danh sách đôi vòng dùng một sentinel cho cả hai đầu

Trong danh sách đôi thông thường không có sentinel, trạng thái rỗng thường là:

```text
head == NULL
tail == NULL
size == 0
```

Với **danh sách đôi vòng có sentinel S**:

```text
Rỗng:
       +---- next ----+
       |              |
       v              |
      [S]-------------+
       ^              |
       +---- prev ----+
S.next == &S, S.prev == &S

Có 3 phần tử:
S <--> [A] <--> [B] <--> [C] <--> S

S.next = A, S.prev = C
A.prev = S, C.next = S
```

Bất biến quan trọng:

1. Sentinel `S` **luôn tồn tại** và `S.next`, `S.prev` luôn hợp lệ trong trạng thái container đã được khởi tạo.
2. Rỗng khi `S.next == &S` **và** `S.prev == &S`.
3. Với mọi nút trong vòng, `node.next.prev == node` và `node.prev.next == node`.
4. Có đúng `size` nút dữ liệu; `S` không được tính vào `size`.
5. Duyệt phần tử phải **dừng khi quay lại `&S`**, không đợi `NULL`.

### 6.1. Mã C minh họa danh sách đôi vòng với sentinel nhúng

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct DNode {
    int value;
    struct DNode *prev, *next;
} DNode;

typedef struct DList {
    DNode sentinel;       /* Mốc đầu/cuối nhúng trực tiếp. */
    size_t size;
} DList;

void dlist_init(DList *list) {
    if (list == NULL) return;
    DNode *s = &list->sentinel;
    s->prev = s;
    s->next = s;
    s->value = 0;        /* Không mang dữ liệu logic. */
    list->size = 0;
}

bool dlist_push_back(DList *list, int value) {
    if (list == NULL || list->size == (size_t)-1) return false;
    DNode *node = malloc(sizeof *node);
    if (node == NULL) return false;

    DNode *s = &list->sentinel;
    DNode *tail = s->prev;

    node->value = value;
    node->prev = tail;
    node->next = s;

    tail->next = node;   /* Rỗng: tail chính là sentinel. */
    s->prev = node;
    ++list->size;
    return true;
}

bool dlist_pop_front(DList *list, int *out) {
    if (list == NULL) return false;
    DNode *s = &list->sentinel;
    if (s->next == s) return false; /* Không xóa sentinel. */

    DNode *first = s->next;
    if (out != NULL) *out = first->value;

    /* Gỡ first bằng quy tắc liên kết đôi chung. */
    first->prev->next = first->next;
    first->next->prev = first->prev;
    --list->size;
    free(first);
    return true;
}

void dlist_clear(DList *list) {
    if (list == NULL) return;
    DNode *s = &list->sentinel;

    while (s->next != s) {
        dlist_pop_front(list, NULL);
    }
}

void dlist_print(const DList *list) {
    if (list == NULL) return;
    const DNode *s = &list->sentinel;

    for (const DNode *p = s->next; p != s; p = p->next) {
        printf("%d ", p->value);
    }
    puts("");
}

int main(void) {
    DList list;
    dlist_init(&list);

    dlist_print(&list);  /* Dòng trống */
    if (!dlist_push_back(&list, 10) ||
        !dlist_push_back(&list, 20)) {
        dlist_clear(&list);
        return EXIT_FAILURE;
    }

    dlist_print(&list);  /* 10 20 */
    dlist_pop_front(&list, NULL);
    dlist_pop_front(&list, NULL);
    dlist_pop_front(&list, NULL);  /* false: danh sách rỗng. */
    dlist_print(&list);  /* Dòng trống */

    dlist_clear(&list);
    return EXIT_SUCCESS;
}
```

Khi xóa nút duy nhất, cả `first->prev` và `first->next` đều là sentinel; hai phép cập nhật sẽ đặt lại `S.next == S` và `S.prev == S` đúng bất biến rỗng, **không cần nhánh riêng cho phần tử cuối**.

**Giới hạn cực kỳ quan trọng:** `DList.sentinel` chứa các con trỏ trỏ tới **chính địa chỉ của nó**. Không được sao chép `DList` bằng phép gán struct hoặc di chuyển byte tùy tiện rồi dùng tiếp; các con trỏ có thể vẫn chỉ về sentinel của đối tượng gốc. Nếu cần chuyển vị trí container, phải xây dựng cơ chế di chuyển/tái liên kết phù hợp với thiết kế. Những nút dữ liệu mới cấp phát vẫn do `DList` sở hữu; hàm `dlist_clear` không được gọi `free` lên sentinel nhúng.

## 7. Nút canh gác giảm nhánh nhưng không miễn kiểm tra biên

Kỹ thuật sentinel thường làm mã **đồng nhất** hơn, nhưng không tự biến mọi truy cập thành hợp lệ.

- Với danh sách đơn dummy head, `dummy.next == NULL` vẫn có nghĩa **không có phần tử**, phải kiểm tra trước khi đọc `dummy.next->value`.
- Với danh sách đôi sentinel vòng, `sentinel.next` luôn trỏ tới một `DNode` hợp lệ sau khởi tạo, nhưng khi rỗng nó **trỏ tới sentinel**, và đọc `sentinel.value` như payload là lỗi **ngữ nghĩa**.
- Với vòng lặp duyệt danh sách đôi, điều kiện dừng là `node == &sentinel`, không phải `node == NULL`.
- Nếu xóa bằng con trỏ tới nút dữ liệu, cần bảo đảm nút thuộc **đúng container**, chưa bị xóa, và không phải sentinel.
- Với nút sentinel cấp phát động, khi hủy cấu trúc cần xử lý vòng đời của sentinel và các nút dữ liệu **không bị giải phóng trùng**.

**Sentinel loại bỏ một số trường hợp biên ở tầng liên kết, không loại bỏ các tiền điều kiện của API.** Giá trị payload rỗng, container rỗng, nút kỹ thuật và liên kết không tồn tại vẫn cần định nghĩa rõ.

## 8. Stack và heap: rỗng thường là metadata, không phải nút giả

### 8.1. Stack mảng dùng `size`

Với stack có mảng `data[capacity]` và `size`:

```text
Rỗng:
size = 0

Push(7), push(9):
data = [7][9][...]
size = 2
top logical index = size - 1 = 1

Pop 9, pop 7:
size = 0
Các byte cũ có thể vẫn còn trong data,
nhưng không còn là phần tử logic của stack.
```

Không cần xóa sạch byte của ô vừa pop nếu kiểu dữ liệu và chính sách sở hữu cho phép; chỉ cần duy trì `size` và quy tắc vòng đời phần tử. Với container quản lý đối tượng có destructor, thao tác pop phải thực hiện các bước hủy phù hợp theo ngữ nghĩa kiểu.

Một cách khác dùng biến `top = -1` khi rỗng; `top` phải có **kiểu số nguyên có dấu** phù hợp. Nếu viết `size_t top = -1`, giá trị sẽ chuyển thành một số unsigned rất lớn, nên cần xem xét kỹ điều kiện so sánh/truy cập.

### 8.2. Binary heap lưu bằng mảng

Heap nhị phân thường chứa đúng `size` phần tử logic trong vùng `[0,size)`. Khi `size == 0`, không có gốc; không được đọc `data[0]` như phần tử thật.

```text
Heap không rỗng: size = 3
index:            0    1    2
data:            [2]  [5]  [9]
root = data[0]

Heap rỗng: size = 0
data có thể còn dung lượng capacity > 0
nhưng data[0] không phải phần tử logic.
```

`insert` vào heap rỗng đặt phần tử mới ở chỉ số 0; `extract_min` phải kiểm tra rỗng trước khi đọc gốc. Cây heap lưu bằng mảng không cần tạo sentinel `NIL` cho các con thiếu: con trái/phải tồn tại hay không được quyết định bằng phép kiểm tra chỉ số `2*i+1 < size` và `2*i+2 < size` (với xử lý tính toán tránh tràn số khi `i` cực lớn).

Với heap chứa **con trỏ hoặc handle** tới các đối tượng nghiệp vụ, `NULL` có thể biểu diễn “không có đối tượng” chỉ khi hợp đồng cấm phần tử null; nếu null là phần tử hợp lệ, phải lưu trạng thái riêng.

## 9. Queue mảng vòng: `head == tail` có thể là rỗng lẫn đầy

Trong **circular buffer**, các chỉ số được cập nhật modulo `capacity`. Nếu chỉ giữ `head` và `tail`, thường xuất hiện một sự mơ hồ:

```text
capacity = 4
head = 0, tail = 0

Có thể là:
- Queue rỗng: chưa có phần tử cần đọc.
- Queue đầy: đã thêm 4 phần tử, tail quay lại vị trí 0.

Chỉ hai chỉ số head/tail không luôn đủ để phân biệt.
```

Ba chính sách phổ biến:

| Chính sách | Điều kiện rỗng | Điều kiện đầy | Đánh đổi |
| --- | --- | --- | --- |
| Lưu thêm `count` | `count == 0` | `count == capacity` | Thêm một trường metadata |
| Chừa một slot | `head == tail` | `(tail+1)%capacity == head` | Chỉ dùng tối đa `capacity-1` slot |
| Lưu thêm `full` hoặc trạng thái tương đương | `head == tail && !full` | `head == tail && full` | Phải cập nhật đúng flag theo mỗi thao tác |

Trong ví dụ dưới, dùng `count` và `capacity` cố định, nên có thể sử dụng **toàn bộ các ô**.

### 9.1. Cài đặt C queue vòng với count và payload bằng 0 hợp lệ

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

enum { QUEUE_CAPACITY = 4 };

typedef struct Queue {
    int data[QUEUE_CAPACITY];
    size_t head;
    size_t tail;
    size_t count;
} Queue;

void queue_init(Queue *q) {
    q->head = 0;
    q->tail = 0;
    q->count = 0;
}

bool queue_push(Queue *q, int value) {
    if (q == NULL || q->count == QUEUE_CAPACITY) return false;
    q->data[q->tail] = value;
    q->tail = (q->tail + 1) % QUEUE_CAPACITY;
    ++q->count;
    return true;
}

bool queue_pop(Queue *q, int *out) {
    if (q == NULL || q->count == 0) return false;
    if (out != NULL) *out = q->data[q->head];
    q->head = (q->head + 1) % QUEUE_CAPACITY;
    --q->count;
    return true;
}

int main(void) {
    Queue q;
    queue_init(&q);

    queue_push(&q, 0);   /* 0 là dữ liệu hợp lệ. */
    queue_push(&q, 10);
    queue_push(&q, 20);
    queue_push(&q, 30);

    printf("head=%zu tail=%zu count=%zu\n",
           q.head, q.tail, q.count);  /* 0, 0, 4: đầy, không rỗng */

    if (!queue_push(&q, 40)) {
        puts("Queue day");
    }

    int value = -1;
    while (queue_pop(&q, &value)) {
        printf("%d ", value); /* 0 10 20 30 */
    }
    puts("");

    printf("head=%zu tail=%zu count=%zu\n",
           q.head, q.tail, q.count);  /* 0, 0, 0: rỗng */
    return 0;
}
```

Bất biến:

- `0 <= count <= QUEUE_CAPACITY`.
- `head` là vị trí phần tử đầu khi `count > 0`.
- `tail` là vị trí sẽ ghi phần tử kế tiếp khi chưa đầy.
- `(head + count) % QUEUE_CAPACITY == tail`, khi chỉ số trong phạm vi.
- `count == 0` nghĩa là rỗng, kể cả nếu ô dữ liệu còn chứa byte cũ.
- `count == QUEUE_CAPACITY` nghĩa là đầy, kể cả nếu `head == tail`.

`queue_push` và `queue_pop` có thời gian O(1) với capacity cố định. Trong queue đa luồng, việc đọc/ghi đồng thời `head`, `tail`, `count` cần thiết kế đồng bộ thích hợp; một quy ước rỗng đúng về logic **không tự làm thao tác thread-safe**.


## 10. Bảng băm open addressing: rỗng và đã xóa không thể gộp làm một

Trong bảng băm dùng **open addressing**, các khóa được lưu trong mảng slot. Khi đụng độ, thuật toán đi qua một **chuỗi vị trí dò (probe sequence)** cho đến khi tìm thấy khóa hoặc gặp điều kiện kết luận khóa không tồn tại.

Một slot thường cần ít nhất ba trạng thái:

- `EMPTY`: ô **chưa từng có** mục được chèn vào từ lần khởi tạo/rehash thích hợp; có thể dùng làm mốc dừng tìm trong chuỗi dò.
- `OCCUPIED`: ô đang chứa một khóa và giá trị hợp lệ.
- `DELETED`: ô **đã từng chứa** mục nhưng mục đã bị xóa; thao tác tìm kiếm không được xem nó tương đương với `EMPTY`.

### 10.1. Vì sao cần tombstone?

Giả sử bảng kích thước 7, hàm băm `h(k) = k % 7`, xử lý va chạm bằng **linear probing**:

```text
h(12) = 5, h(19) = 5

Sau insert(12), insert(19):
index:   0       1       2       3       4       5           6
       [EMPTY] [EMPTY] [EMPTY] [EMPTY] [EMPTY] [12]        [19]
                                              probe 12 -> 19

Delete(12) nhưng đặt slot 5 = EMPTY (SAI):
index:   0       1       2       3       4       5           6
       [EMPTY] [EMPTY] [EMPTY] [EMPTY] [EMPTY] [EMPTY]     [19]

Search(19): bắt đầu từ 5, gặp EMPTY và dừng -> báo sai "không có 19".
```

Cách đúng khi chỉ đánh dấu xóa, chưa tái tổ chức chuỗi probe:

```text
index 5 = DELETED, index 6 = OCCUPIED(19)

Search(19):
  index 5: DELETED -> tiếp tục dò
  index 6: OCCUPIED(19) -> tìm thấy
```

Với **linear probing** còn có kỹ thuật xóa bằng dịch các mục thích hợp về vị trí trước (*backward-shift deletion*) nếu duy trì đúng bất biến; khi dùng thuật toán đó, không nhất thiết để tombstone vĩnh viễn. Nhưng **chỉ đổi thành `EMPTY` mà không sửa chuỗi probe** là không đúng.

### 10.2. Mã tìm khóa bằng trạng thái slot

```c
#include <stdbool.h>
#include <stddef.h>

enum { TABLE_CAPACITY = 7 };

typedef enum SlotState {
    SLOT_EMPTY,
    SLOT_OCCUPIED,
    SLOT_DELETED
} SlotState;

typedef struct Slot {
    int key;
    int value;
    SlotState state;
} Slot;

/* capacity 7, linear probing, chỉ minh họa lookup. */
bool table_find(const Slot slots[TABLE_CAPACITY],
                int key, int *out) {
    /* Phép đổi sang unsigned xử lý cả key âm theo quy tắc
       phép băm minh họa, nhưng không ảnh hưởng tính đúng của probe. */
    size_t start = (size_t)(unsigned int)key % TABLE_CAPACITY;

    for (size_t step = 0; step < TABLE_CAPACITY; ++step) {
        size_t i = (start + step) % TABLE_CAPACITY;

        if (slots[i].state == SLOT_EMPTY) {
            return false; /* Không có khóa theo chuỗi dò này. */
        }
        if (slots[i].state == SLOT_DELETED) {
            continue;     /* Không dừng. */
        }
        if (slots[i].key == key) {
            if (out != NULL) *out = slots[i].value;
            return true;
        }
    }
    return false;         /* Đã kiểm tra tối đa capacity slot. */
}
```

Hàm trên giả sử mọi phép chèn đều dùng **cùng hàm băm và quy tắc linear probing**, mọi slot đã được khởi tạo trạng thái, không có xóa làm phá chuỗi dò, và không có thay đổi đồng thời khi tìm. Đây là code tìm kiếm độc lập, không phải một hiện thực bảng băm đầy đủ. Để triển khai chèn/xóa, cần thiết kế thêm quy tắc **tái sử dụng tombstone**, xử lý bảng đầy, số mục thực, số tombstone, tăng dung lượng và rehash.

**Chú ý:** Khi tái sử dụng tombstone để chèn, phải dò đủ theo hợp đồng tránh tạo hai bản ghi cho cùng một khóa nếu khóa ấy đã tồn tại **sau tombstone** trong chuỗi dò. Không thể luôn chèn ngay vào ô `DELETED` đầu tiên mà chưa kiểm tra khóa trùng ở phần sau.

### 10.3. Quy ước khóa rỗng có thể làm mất miền dữ liệu

Một số bảng cố định dùng giá trị `key == 0` làm tín hiệu “ô trống”. Cách này chỉ đúng nếu **0 bị loại khỏi miền khóa hợp lệ**. Nếu khóa 0 cần được lưu, phải:

- Chọn metadata trạng thái riêng như `state` hoặc bitmap.
- Dùng một quy ước khác có chứng minh không va chạm dữ liệu.
- Hoặc có cơ chế ngoại lệ riêng xử lý khóa đặc biệt, đồng thời điều chỉnh mọi phép chèn/tìm/xóa.

Đánh đổi thường là **thêm một lượng metadata** để giữ đủ miền dữ liệu. Không được mặc định số 0, chuỗi rỗng `""` hoặc con trỏ `NULL` luôn là khóa không hợp lệ trong mọi bài toán.

### 10.4. Chi phí tombstone

Tombstone giữ đúng chuỗi dò nhưng khi tích lũy nhiều ô `DELETED`, một phép tìm kiếm có thể phải kiểm tra nhiều slot hơn. Rehash định kỳ hoặc thuật toán xóa/tái tổ chức thích hợp giúp kiểm soát hiệu năng.

| Thao tác | Tác động |
| --- | --- |
| Tìm gặp `EMPTY` | Có thể dừng theo hợp đồng probe |
| Tìm gặp `DELETED` | Phải tiếp tục |
| Tìm gặp `OCCUPIED` trùng khóa | Trả giá trị tìm được |
| Xóa mục | Đặt tombstone hoặc tái tổ chức chuỗi đúng |
| Rehash | Tạo bảng mới theo các mục đang sống, thường loại tombstone |

Với giả định hàm băm tốt và hệ số tải phù hợp, tìm/chèn/xóa có **thời gian trung bình kỳ vọng O(1)**; xấu nhất có thể O(n) theo số slot phải dò. Tỉ lệ slot tombstone và chiến lược rehash ảnh hưởng chi phí thực tế.

## 11. Cây nhị phân: `NULL` leaf và nút `NIL` canh gác

Trong cây nhị phân liên kết thông thường, một nút có thể có `left == NULL` hoặc `right == NULL` để biểu diễn **không có nhánh con**. Cây rỗng có thể dùng `root == NULL`.

```text
root -> [10]
       /   \
     [5]   NULL
    /   \
  NULL  NULL

Không có nhánh không có nghĩa nút cha rỗng.
```

Một số cấu trúc như **cây đỏ–đen (red–black tree)** có thể dùng **nút `NIL` canh gác** thay cho nhiều con trỏ lá `NULL`.

### 11.1. Một nút `NIL` dùng chung

```text
                  root
                   |
                  [10, B]
                 /       \
            [5, R]       NIL
             /   \
           NIL   NIL

NIL không mang khóa logic; thường được xem là đen.
Các nhánh vắng mặt trỏ đến NIL dùng chung.
```

Quy ước thường dùng của một hiện thực cây đỏ–đen có sentinel:

- `tree.root == tree.nil` nghĩa là cây rỗng.
- Các liên kết con vắng mặt được biểu diễn bằng `tree.nil` thay vì `NULL`.
- `tree.nil` được coi là nút lá **đen** trong phân tích bất biến màu.
- `tree.nil` không được tính vào `size` và không được xuất như khóa trong duyệt inorder.
- Việc giải phóng cây **không free `nil` mỗi khi gặp một nhánh**; nếu `nil` do cây sở hữu, giải phóng nó đúng một lần theo vòng đời cây.

**Điểm cần thận trọng:** cách xử lý `nil.parent` tùy thuật toán/hiện thực. Một số thuật toán xóa cây đỏ–đen gán tạm parent cho sentinel để dễ sửa cân bằng; vì vậy không được tự giả định mọi trường của `NIL` luôn bất biến sau khởi tạo. Nếu nhiều cây dùng chung một sentinel, càng phải quản lý trạng thái và đồng bộ cẩn thận.

### 11.2. Hàm duyệt có `NIL` phải dừng đúng chỗ

Ví dụ mã giả:

```text
INORDER(node, NIL):
    if node == NIL:
        return

    INORDER(node.left, NIL)
    visit(node.key)
    INORDER(node.right, NIL)
```

Nếu duyệt với điều kiện `node != NULL` trong một cây mà nhánh rỗng trỏ tới `NIL` khác `NULL`, thuật toán có thể đi vào chính nút canh gác, làm sai dữ liệu hoặc lặp vô hạn tùy liên kết. Phải dùng **đúng quy ước của cây cụ thể**.

### 11.3. Sentinel không thay thế các bất biến của cây

Cây đỏ–đen ngoài `NIL` còn phải giữ quy tắc màu, black-height và quan hệ BST. Việc thống nhất biểu diễn lá có thể đơn giản hóa thao tác quay/chèn/xóa, nhưng **không tự bảo đảm cây cân bằng**.

Tương tự với B-tree/B+ tree, “nút lá” là nút dữ liệu thật dù không có con; không nên gọi nó là một nút “rỗng” theo nghĩa nó không chứa khóa, trừ khi định dạng cấu trúc quy định như vậy. Nút có 0 khóa có thể hợp lệ ở một số vị trí/trạng thái tạm, nhưng phải xét các quy tắc bậc, số khóa tối thiểu và gốc riêng.

## 12. Đồ thị: đỉnh không có hàng xóm, ID không tồn tại và sentinel

Trong đồ thị, “rỗng” xuất hiện ở nhiều cấp:

- **Đồ thị rỗng:** không có đỉnh nào (`V = 0`) và do đó không có cạnh.
- **Tập cạnh rỗng:** có thể có nhiều đỉnh nhưng `E = 0`.
- **Danh sách kề rỗng của một đỉnh:** đỉnh tồn tại nhưng không có hàng xóm theo loại cạnh đang xét.
- **Không có kết quả tìm kiếm:** không có đỉnh mang ID/khóa đang hỏi.
- **Đỉnh canh gác hoặc ID sentinel:** giá trị kỹ thuật, không phải đỉnh nghiệp vụ, chỉ dùng nếu API định nghĩa rõ.

### 12.1. CSR biểu diễn hàng xóm rỗng không cần nút giả

Với đồ thị thưa dùng **Compressed Sparse Row (CSR)**, danh sách hàng xóm của đỉnh `v` nằm trong đoạn:

```text
edges[offsets[v] ... offsets[v+1]-1]

Đỉnh 0 -> 1, 2
Đỉnh 1 -> (không có hàng xóm)
Đỉnh 2 -> 0

offsets = [0, 2, 2, 3]
edges   = [1, 2, 0]

Đỉnh 0: edges[0..1] = [1, 2]
Đỉnh 1: edges[2..1] = []    (đoạn rỗng vì offsets[1] == offsets[2])
Đỉnh 2: edges[2..2] = [0]
```

Bất biến CSR với `V` đỉnh và `E` cạnh trong mảng:

- `offsets` có `V+1` phần tử.
- `offsets[0] == 0`, `offsets[V] == E`.
- `offsets[v] <= offsets[v+1]` cho mọi `v` hợp lệ.
- Đỉnh `v` không có hàng xóm khi `offsets[v] == offsets[v+1]`.
- Các ID đỉnh trong `edges` phải hợp lệ theo hợp đồng, hoặc có quy ước đặc biệt riêng được xử lý rõ.

Không cần chèn một **giá trị đỉnh 0** để biểu diễn danh sách kề rỗng: ID 0 thường là đỉnh thật. Nếu thư viện dùng `-1` để biểu diễn “không tìm thấy” thì phải đảm bảo các ID hợp lệ không bao gồm `-1`, chẳng hạn đánh số từ 0 đến `V-1` và dùng kiểu số có dấu cho kết quả.

### 12.2. BFS/DFS với hàng xóm rỗng

Một đỉnh không có hàng xóm vẫn phải được coi là **đỉnh thật đã thăm**. Khi BFS lấy đỉnh đó ra từ queue, thuật toán chỉ không thêm hàng xóm mới. Nếu queue rỗng, BFS kết thúc lượt duyệt thành phần liên thông đang xử lý; điều này không có nghĩa toàn đồ thị đã được thăm nếu đồ thị không liên thông.

Nếu dùng adjacency list gồm nhiều danh sách liên kết có dummy head, mỗi danh sách kề rỗng vẫn có thể chứa một dummy node **không mang ID đỉnh**. Thuật toán BFS/DFS phải bỏ qua dummy và chỉ duyệt các cạnh thật.

### 12.3. Ma trận kề và ý nghĩa của 0

Trong **đồ thị có trọng số**, giá trị `0` có thể có hai cách diễn giải khác nhau:

- Nếu quy ước **không có cạnh** là `0`, ta không phân biệt được cạnh trọng số 0 với vắng cạnh nếu cả hai được phép.
- Nếu cạnh trọng số 0 là dữ liệu hợp lệ, cần dùng **bitmap có cạnh**, giá trị `None`/`optional`, hoặc một sentinel không nằm trong miền trọng số (cùng các xử lý tương ứng).

Một giá trị lớn như `INF` thường được dùng trong thuật toán đường đi ngắn để biểu diễn “chưa có đường đi hữu hạn được biết đến”, nhưng không nên sử dụng nó như vô hạn thực trong phép cộng nếu có nguy cơ **tràn số** hoặc bị nhầm với trọng số hợp lệ.

## 13. Sentinel trong thuật toán: lợi ích và rủi ro khác với sentinel node

Ngoài cấu trúc dữ liệu, **sentinel** còn chỉ một **giá trị canh gác tạm thời** được đặt để kết thúc vòng lặp mà không phải kiểm tra điều kiện biên ở mỗi bước.

Ví dụ, tìm tuần tự thông thường:

```text
i = 0
while i < n and a[i] != target:
    i += 1
if i == n: không thấy
else:      thấy tại i
```

Nếu **được phép sửa mảng và có sẵn một slot canh gác hợp lệ tại chỉ số n**, có thể đặt `a[n] = target`. Khi đó vòng lặp biết chắc sẽ dừng tại hoặc trước `n`:

```text
Yêu cầu: a có n phần tử dữ liệu, cộng thêm ô a[n] ghi được.
a[n] = target             # Sentinel tạm thời

i = 0
while a[i] != target:
    i += 1

if i == n:
    không thấy trong n phần tử thật
else:
    thấy ở i
```

Điều kiện an toàn cực kỳ quan trọng:

1. Có **slot phụ hợp lệ**, không ghi vượt mảng.
2. Được phép ghi slot đó, và không có bên khác đồng thời dựa vào giá trị của nó.
3. Nếu dữ liệu ở slot canh gác phải được giữ, cần lưu/khôi phục theo hợp đồng.
4. Mốc `i == n` **không phải phần tử dữ liệu**, dù ô canh gác chứa đúng `target`.
5. Nếu mảng chỉ có đúng `n` phần tử, tuyệt đối **không** dùng kỹ thuật này bằng cách ghi `a[n]` ngoài biên.

Về Big-O, cả tìm tuần tự thường lẫn tìm có sentinel đều là **O(n)** trong trường hợp xấu nhất. Sentinel có thể giảm một phép kiểm tra điều kiện trong vòng lặp ở một số môi trường, nhưng còn chi phí ghi/khôi phục sentinel, ảnh hưởng cache và quy tắc an toàn. **Không được tuyên bố luôn nhanh hơn** nếu chưa đo trên mã máy, compiler và workload cụ thể.

**Phân biệt:** sentinel ở ví dụ này là **một phần tử tạm thời** phục vụ vòng lặp, không nhất thiết là nút liên kết tồn tại suốt vòng đời của container.

## 14. Bảng so sánh các lựa chọn biểu diễn rỗng

| Chiến lược | Nơi dùng điển hình | Chi phí bộ nhớ | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- | --- | --- |
| Con trỏ `NULL` | Head danh sách đơn, cây con vắng | O(1) trên mỗi trường con trỏ | Đơn giản, rõ không có nút | Cần nhánh xử lý đầu/cuối và tránh dereference null |
| `size == 0` | Mảng động, heap, stack | Một trường `size` mỗi container | Không hy sinh giá trị dữ liệu | Phải đồng bộ `size` với thao tác |
| Chỉ số `-1` | `top` của stack chỉ số có dấu | Một trường số nguyên | Biểu diễn trực tiếp trước phần tử đầu | Dễ sai nếu trộn với unsigned/giá trị hợp lệ |
| Dummy head nhúng | Danh sách đơn | Một nút giả O(1) mỗi list | Đồng nhất cách xóa/chèn đầu | Tốn metadata, không được tính/giải phóng như dữ liệu |
| Sentinel vòng | Danh sách đôi | Một nút giả O(1) mỗi list | Ít nhánh riêng đầu/cuối | Duyệt phải dừng tại sentinel; self-pointer không thể copy byte tùy tiện |
| Cờ trạng thái slot | Bảng băm open addressing | Metadata theo mỗi slot | Phân biệt EMPTY/OCCUPIED/DELETED | Tombstone có thể kéo dài probe, cần rehash |
| `NIL` sentinel | Một số cây cân bằng | Có thể một nút cho toàn cây | Đơn giản hóa thao tác trên lá rỗng | Phải xử lý màu, parent, vòng đời NIL đúng |
| `count` trong queue vòng | Circular buffer | Một số nguyên thêm | Dùng được toàn bộ capacity; phân biệt đầy/rỗng | Thêm metadata cần cập nhật mỗi push/pop |
| Object dấu hiệu riêng | API tra cứu `None` có thể là dữ liệu | Một object/giá trị phân biệt | Không đụng payload hợp lệ | Cần kiểm tra danh tính hoặc quy tắc bằng nhau đúng |
| Optional/Result/ngoại lệ | Pop, tìm kiếm, parsing | Phụ thuộc API và runtime | Tách trạng thái khỏi dữ liệu rõ ràng | Cú pháp/chi phí khác nhau, cần hợp đồng thống nhất |

Không có một lựa chọn tối ưu cho mọi cấu trúc. Ví dụ, dummy head giảm trường hợp đặc biệt trong mã liên kết nhưng thêm một nút metadata; mảng động chỉ cần `size` là đủ vì vị trí phần tử đã được xác định theo chỉ số. Mục tiêu là **tính đúng đắn của biểu diễn trước**, sau đó mới đo hiệu năng.

## 15. Kiểm thử trạng thái rỗng và các chuyển trạng thái

Một bộ kiểm thử cấu trúc dữ liệu nên bao gồm ít nhất:

1. **Ngay sau khởi tạo:** `is_empty` phải đúng, `size == 0` và các trường liên kết tuân thủ quy ước.
2. **Thêm phần tử đầu tiên:** trạng thái **0 → 1** đúng; phần tử được đọc và loại đúng.
3. **Xóa phần tử cuối cùng:** trạng thái **1 → 0** đúng; head/tail/sentinel liên kết nhất quán.
4. **Thực hiện thao tác trên container rỗng:** pop/dequeue/erase/search trả kết quả thất bại hoặc báo ngoại lệ theo hợp đồng, **không dereference nút giả/null**.
5. **Phần tử mang giá trị giống sentinel phổ biến:** `0`, `-1`, `None` hoặc chuỗi rỗng, nếu những giá trị ấy hợp lệ theo kiểu.
6. **Lặp thêm/xóa nhiều lượt:** mọi bất biến và metadata vẫn khớp, không leak/double free.
7. **Xóa giữa và cuối danh sách có sentinel:** không làm sentinel bị bỏ hoặc tự nối sai.
8. **Bảng băm va chạm rồi xóa:** khóa nằm **sau tombstone** vẫn tìm được; khóa trùng không bị chèn hai lần.
9. **Queue vòng đầy rồi rỗng:** nếu `head == tail` ở cả hai trạng thái, `count/flag` phân biệt đúng.
10. **Cây rỗng và chỉ một nút:** `NIL`/`NULL` được dùng nhất quán; không xuất sentinel như dữ liệu.
11. **Đồ thị có đỉnh cô lập và không có đỉnh:** không tạo ra đỉnh giả trong kết quả duyệt.
12. **Đường lỗi cấp phát:** không để lại container ở trạng thái “nửa có, nửa không”, và không giải phóng sentinel nhúng.

### 15.1. Kiểm thử bất biến sau mỗi thao tác

Với danh sách đôi sentinel vòng, trong mã kiểm thử (không nhất thiết chạy trên đường nóng sản phẩm), có thể kiểm tra:

```text
S = &list.sentinel

if list.size == 0:
    assert S.next == S
    assert S.prev == S

count = 0
p = S.next
while p != S:
    assert p.next.prev == p
    assert p.prev.next == p
    count += 1
    assert count <= list.size  # Gợi ý phát hiện chu trình sai dạng.

assert count == list.size
```

Với danh sách đơn dummy head, có thể đếm các nút từ `dummy.next` tới `NULL` rồi so với `size`. Với heap kiểm tra `size <= capacity` và bất biến cha/con; với CSR kiểm tra `offsets` không giảm. Những phép kiểm tra O(n) hoặc O(V+E) thích hợp trong kiểm thử, nhưng **không nhất thiết chạy mỗi thao tác** trên môi trường sản phẩm nếu làm tăng chi phí đáng kể.

### 15.2. Property-based và mô hình tham chiếu

Một cách kiểm thử mạnh là chạy chuỗi thao tác ngẫu nhiên có kiểm soát (push/pop/insert/erase/search), đồng thời so sánh kết quả của cấu trúc tự cài với một mô hình đơn giản đã tin cậy như list Python hoặc vector theo quy tắc nghiệp vụ.

Sau **mỗi thao tác**, kiểm tra:

- Kích thước logic.
- Thứ tự phần tử.
- Trạng thái rỗng/đầy.
- Kết quả thao tác thất bại ở biên.
- Các bất biến liên kết và vòng đời.

Điều này đặc biệt hữu ích với trường hợp ít khi được nghĩ đến bằng tay, ví dụ xóa–thêm–xóa liên tục khi danh sách chỉ còn một phần tử hoặc các tombstone liên tiếp trên bảng băm.

## 16. Bài tập có lời giải

### Bài 1. Phân biệt rỗng và giá trị rỗng

```python
a = []
b = [None]
print(bool(a), bool(b), len(a), len(b))
```

**Lời giải:** Kết quả là `False True 0 1`. `a` không có phần tử; `b` chứa một phần tử có giá trị `None`. Dùng `None` làm tín hiệu container rỗng sẽ mơ hồ nếu `None` được phép làm payload.

### Bài 2. Dummy head có được tính vào `size`?

Danh sách đơn có dummy head và hai nút dữ liệu `10 -> 20`. Container nên có `size` bao nhiêu?

**Lời giải:** `size == 2`, vì dummy không phải phần tử logic. Chuỗi liên kết vật lý có ba nút, nhưng số phần tử dữ liệu chỉ là hai.

### Bài 3. Xóa đầu với dummy head

Danh sách `DUMMY -> 4 -> 7 -> NULL`. Muốn xóa nút chứa 4, phải cập nhật trường nào?

**Lời giải:** Đặt `dummy.next` trỏ đến nút 7, giảm `size` rồi giải phóng nút 4 theo quyền sở hữu. Không xóa dummy; thao tác này giống hệt cách sửa `prev.next` ở các vị trí khác, với `prev` chính là dummy.

### Bài 4. Danh sách đôi vòng rỗng

Một `DList` mới đã gọi `dlist_init`. `sentinel.next` và `sentinel.prev` có giá trị gì?

**Lời giải:** Cả hai trỏ tới chính `&sentinel`. Nếu duyệt bằng điều kiện `p != NULL`, vòng lặp không có điều kiện dừng đúng. Phải dừng khi `p == &sentinel`.

### Bài 5. Xóa nút duy nhất trong danh sách đôi vòng

Với `S <-> A <-> S`, thao tác pop nút A phải để lại bất biến gì?

**Lời giải:** Sau khi nối lại hai láng giềng của A và giải phóng A: `S.next == S`, `S.prev == S`, `size == 0`. Không để `S.prev` trỏ tới A đã hủy.

### Bài 6. Queue vòng và `head == tail`

Queue cố định capacity 4 lưu `count`. Ở trạng thái `head == tail == 0`, có thể kết luận queue rỗng không?

**Lời giải:** Không. Nếu `count == 0` thì rỗng; nếu `count == 4` thì đầy. Với count, `head==tail` ở cả hai trạng thái này.

### Bài 7. Dùng `-1` cho stack

Stack cho phép chứa mọi `int`, kể cả `-1`. Tại sao hàm `int pop()` trả `-1` khi rỗng là API thiếu rõ ràng?

**Lời giải:** Không thể phân biệt thất bại với giá trị dữ liệu `-1` thật. Trả cặp kết quả trạng thái + payload, optional/result hoặc báo lỗi theo hợp đồng.

### Bài 8. Tombstone trên bảng băm

Bảng 7 slot dùng linear probing. Khóa 12 và 19 cùng có hash 5; 12 nằm ô 5, 19 ở ô 6. Sau khi xóa 12, vì sao không nên đổi ô 5 ngay thành `EMPTY`?

**Lời giải:** Tra cứu 19 bắt đầu ở ô 5 sẽ thấy `EMPTY` và có thể dừng, báo không thấy dù 19 còn ở ô 6. Dùng `DELETED` để tiếp tục dò hoặc tái tổ chức chuỗi bằng thuật toán xóa đúng.

### Bài 9. Tái sử dụng tombstone

Sau khi xóa một mục, ô đầu trong chuỗi dò là `DELETED`. Có được chèn ngay khóa mới vào ô đó mà không kiểm tra các ô sau không?

**Lời giải:** Không phải luôn được. Khóa mới có thể đã tồn tại ở một ô phía sau. Quy trình chèn phải bảo đảm phát hiện khóa trùng theo hợp đồng trước khi chọn vị trí chèn, chẳng hạn ghi nhớ tombstone đầu rồi tiếp tục dò đến khi có điều kiện kết luận không tồn tại.

### Bài 10. Cây đỏ–đen dùng `NIL`

Trong cây có `root == NIL`, một hàm duyệt có nên dùng điều kiện dừng `if (node == NULL) return` không?

**Lời giải:** Không, nếu `NIL` không phải `NULL`. Hàm phải dừng tại `node == NIL`; nếu không, nó có thể xem sentinel là nút dữ liệu và đọc các liên kết của sentinel sai.

### Bài 11. Đỉnh cô lập trong đồ thị CSR

`offsets = [0, 2, 2, 3]`. Đỉnh chỉ số 1 có bao nhiêu hàng xóm?

**Lời giải:** `offsets[2] - offsets[1] = 2 - 2 = 0`. Đỉnh 1 vẫn tồn tại; nó chỉ có tập hàng xóm rỗng.

### Bài 12. Ma trận kề với cạnh trọng số 0

Một đồ thị cho phép cạnh có trọng số 0. Có thể dùng số 0 trong ma trận kề để biểu diễn “không có cạnh” mà không thêm metadata không?

**Lời giải:** Không, nếu muốn phân biệt cạnh trọng số 0 hợp lệ với không có cạnh. Dùng một cấu trúc trạng thái riêng, optional, bitmap cạnh tồn tại hoặc sentinel nằm ngoài miền trọng số theo hợp đồng rõ ràng.

### Bài 13. Sentinel search ngoài biên

Mảng có đúng `n` phần tử hợp lệ ở các chỉ số `0..n-1`, không có slot phụ. Có thể gán `a[n] = target` để làm sentinel không?

**Lời giải:** Không. `a[n]` nằm ngoài mảng, ghi vào đó là truy cập ngoài biên. Muốn dùng kỹ thuật này phải cấp vùng có ít nhất `n+1` ô và tuân thủ điều kiện được ghi slot phụ.

### Bài 14. Chi phí nút sentinel

Có `m` danh sách đôi vòng, mỗi danh sách lưu `n_i` nút dữ liệu và một sentinel nhúng. Số nút vật lý là bao nhiêu? Bao nhiêu nút mang dữ liệu?

**Lời giải:** Tổng nút vật lý là `(n_1 + ... + n_m) + m`; tổng nút dữ liệu là `n_1 + ... + n_m`. Sentinel làm tăng O(m) nút metadata cho `m` container, nhưng không thay đổi O(n_i) của phép duyệt dữ liệu trong một danh sách.

## 17. Ghi nhớ để vận dụng

- **Container rỗng khác phần tử mang giá trị rỗng.** `size == 0` là trạng thái cấu trúc; `None`, `NULL`, `0` hay `-1` có thể là dữ liệu hợp lệ tùy miền giá trị.
- **Nút canh gác là kỹ thuật biểu diễn, không phải dữ liệu nghiệp vụ.** Dummy head và sentinel vòng giúp đồng nhất thao tác biên, nhưng cần đúng điều kiện dừng, quyền sở hữu và bất biến liên kết.
- **Quy ước rỗng phải nhất quán trên mọi thao tác.** Danh sách đơn `head == NULL`, danh sách có dummy `dummy.next == NULL`, danh sách vòng `S.next == S`, queue vòng `count == 0` và cây có NIL `root == NIL` là các quy tắc khác nhau.
- **Một số trạng thái không thể gộp:** bảng băm open addressing cần phân biệt `EMPTY` với `DELETED` để bảo toàn chuỗi dò; đồ thị trọng số 0 cần phân biệt cạnh có trọng số 0 với vắng cạnh.
- **Không tối ưu trước tính đúng đắn.** Sentinel có thể giảm một số nhánh điều kiện nhưng tăng metadata, không làm biến mất thao tác kiểm tra rỗng cần thiết, và không đổi Big-O của việc duyệt n phần tử.
- **Kiểm thử tập trung vào biên:** rỗng, một phần tử, thêm/xóa đầu/cuối, chuyển 0 ↔ 1, queue đầy/rỗng, tombstone, cây NIL và đỉnh cô lập. Phân tích **bất biến, thời gian, bộ nhớ, vòng đời** để chọn cách biểu diễn phù hợp từng bài toán.
