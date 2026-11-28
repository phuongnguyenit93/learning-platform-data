# Quyền sở hữu, vòng đời và giải phóng tài nguyên

Một danh sách liên kết có thể trả kết quả đúng khi thêm, tìm và xóa phần tử, nhưng vẫn là hiện thực **không đúng** nếu sau khi xóa nút, chương trình tiếp tục dùng con trỏ tới nút ấy; hoặc nếu xóa toàn bộ danh sách mà quên giải phóng một số nút. Ngược lại, khi hai cấu trúc cố ý chia sẻ một cây con, việc một bên giải phóng cây con đó ngay khi không cần nữa có thể làm bên kia mất dữ liệu.

Vì vậy, ngoài **giá trị** và **liên kết**, mỗi cấu trúc dữ liệu cần xác định rõ: **ai sở hữu tài nguyên**, **đối tượng tồn tại đến khi nào**, **ai chỉ đang mượn quyền truy cập**, và **thao tác nào kết thúc vòng đời của đối tượng**.

Bài này thuộc chương **Bộ nhớ và biểu diễn** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Kiến thức về vòng đời và quyền sở hữu giúp xây dựng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị có bất biến đúng, đồng thời đánh giá chi phí thời gian và bộ nhớ khi chọn cách biểu diễn.

## 1. Bốn khái niệm phải tách bạch

### 1.1. Đối tượng và tài nguyên

**Đối tượng** là một thực thể có trạng thái, kiểu dữ liệu và vòng đời theo quy tắc của ngôn ngữ. **Tài nguyên** là thứ chương trình phải quản lý để sử dụng đúng, ví dụ vùng bộ nhớ cấp phát, file đang mở, socket, mutex, kết nối hoặc handle hệ điều hành.

Vùng nhớ cấp phát động là một loại tài nguyên; nhưng không phải mọi tài nguyên đều là vùng nhớ và không phải mọi đối tượng đều cần gọi `free`. Chẳng hạn, biến cục bộ C thông thường sẽ hết vòng đời khi thoát phạm vi thích hợp, còn đối tượng cấp bằng `malloc` phải được quản lý theo hợp đồng của bộ cấp phát.

### 1.2. Quyền sở hữu (ownership)

**Chủ sở hữu** là thành phần chịu trách nhiệm quản lý và cuối cùng **thu hồi hoặc chuyển giao** tài nguyên. Đây là **hợp đồng thiết kế** chứ không nhất thiết là một trường chứa trong đối tượng.

Các kiểu quan hệ phổ biến:

| Quan hệ | Ai chịu trách nhiệm về vòng đời? | Ví dụ |
| --- | --- | --- |
| **Sở hữu duy nhất** | Một chủ sở hữu được xác định rõ | Container sở hữu các nút danh sách; `std::unique_ptr` |
| **Sở hữu chia sẻ** | Nhiều chủ sở hữu phối hợp giữ tài nguyên sống | `std::shared_ptr` trong C++ |
| **Mượn/không sở hữu** | Bên cho mượn bảo đảm đối tượng còn hợp lệ khi dùng | Tham số `const Node *` của hàm chỉ đọc |
| **Quyền sở hữu theo vùng** | Một arena/pool quản lý vòng đời của nhiều phần tử | Nhiều nút được cấp từ cùng arena |
| **Được runtime quản lý** | Runtime/GC quyết định thời điểm thu hồi bộ nhớ không còn truy cập được | Đối tượng Java, Python |

Một **con trỏ thô** trong C/C++ tự nó không cho biết là sở hữu hay mượn. Phải đọc hợp đồng API để hiểu. Không nên lấy việc “có địa chỉ của nút” làm bằng chứng rằng mình được quyền giải phóng nút.

### 1.3. Vòng đời (lifetime)

Vòng đời của đối tượng là khoảng thời gian đối tượng tồn tại hợp lệ theo ngôn ngữ. Khi đối tượng hết vòng đời, những đường truy cập tới vùng cũ có thể trở nên không hợp lệ, dù biến con trỏ vẫn đang chứa một giá trị địa chỉ.

```text
Thời gian ─────────────────────────────────────────────────────>

      tạo đối tượng              sử dụng              hủy/giải phóng
            |                       |                         |
            v                       v                         v
         [ bắt đầu vòng đời ──────────────────────── kết thúc ]
                                hợp lệ                        X

Con trỏ tới vùng cũ có thể còn tồn tại sau dấu X,
nhưng không được tiếp tục truy cập đối tượng đã kết thúc vòng đời.
```

**Thời gian sống của biến con trỏ** và **vòng đời đối tượng đích** là hai điều riêng. Một biến con trỏ có thể còn tồn tại lâu hơn đối tượng mà nó từng trỏ tới.

### 1.4. Giải phóng (release) và kết thúc vòng đời

Tùy ngôn ngữ, kết thúc vòng đời có thể:

- Được thực hiện tự động khi rời phạm vi hoặc hủy đối tượng sở hữu.
- Được thực hiện tường minh bằng API như `free`, `close`, `release`.
- Được runtime/GC quyết định khi không còn tham chiếu giữ đối tượng sống theo cơ chế của runtime.
- Được thực hiện theo nhóm khi hủy arena/pool.

**Không đồng nhất** `free` với “hủy tất cả tài nguyên”: giải phóng vùng bộ nhớ chứa một `struct` không tự động đóng file/socket mà các trường của nó đang giữ, trừ khi mã quản lý chủ động đóng chúng. Ngược lại, trong một số runtime, bộ gom rác quản lý **bộ nhớ**, nhưng vẫn phải đóng tài nguyên ngoại vi đúng cách.

## 2. Mô hình thời gian sống ở C: tự động, tĩnh và cấp phát động

### 2.1. Vùng lưu trữ tự động

```c
#include <stdio.h>

void print_number(void) {
    int number = 42;
    printf("%d\n", number);
} /* Vòng đời number kết thúc khi rời phạm vi phù hợp. */
```

Đối tượng cục bộ `number` có *automatic storage duration*. Trong nhiều môi trường, nó nằm trong vùng stack frame, nhưng tiêu chuẩn C quy định **thời hạn lưu trữ**, không yêu cầu nó luôn nằm tại một vị trí “stack” vật lý cụ thể.

Không được trả về con trỏ tới một biến tự động cục bộ để truy cập sau khi hàm kết thúc:

```c
/* SAI: kết quả không được dùng để truy cập một int còn sống. */
int *invalid_result(void) {
    int temporary = 7;
    return &temporary;
}
```

Đối tượng `temporary` đã hết vòng đời khi hàm trả về. Con trỏ trả về không kéo dài vòng đời của đối tượng đó.

### 2.2. Vùng lưu trữ tĩnh

```c
#include <stdio.h>

int next_id(void) {
    static int counter = 0;
    return ++counter;
}

int main(void) {
    printf("%d %d\n", next_id(), next_id()); /* Các lần gọi dùng chung counter. */
    return 0;
}
```

Biến `counter` có *static storage duration* và duy trì trạng thái giữa các lần gọi. Nó không đòi hỏi `malloc/free` và thường tồn tại trong toàn bộ thời gian chạy chương trình theo quy tắc C. Nhưng nếu nhiều luồng cùng sửa biến như thế, phải xét vấn đề đồng bộ và data race.

### 2.3. Vùng nhớ cấp phát động

```c
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int *p = malloc(sizeof *p);
    if (p == NULL) {
        return EXIT_FAILURE; /* Cấp phát thất bại. */
    }

    *p = 42;
    printf("%d\n", *p);

    free(p);
    p = NULL;               /* Chỉ làm sạch biến p này. */
    return EXIT_SUCCESS;
}
```

Trong C, `malloc` cấp một vùng có dung lượng được yêu cầu và căn chỉnh phù hợp theo hợp đồng của nó; `free` giải phóng vùng đã cấp theo quy tắc. `malloc` không tự đặt giá trị của một `int` mới thành 0; ta đã khởi tạo bằng lệnh `*p = 42` trước khi đọc.

**Các điều kiện an toàn trọng yếu:**

1. Kiểm tra kết quả `malloc` trước khi giải tham chiếu.
2. Không đọc dữ liệu chưa khởi tạo hoặc truy cập ngoài kích thước được cấp.
3. Chỉ gọi `free` với đối số hợp lệ theo hợp đồng cấp phát (hoặc `NULL`).
4. Không dùng vùng đã được giải phóng và không giải phóng cùng vùng hai lần nếu chưa có cấp phát mới tương ứng.
5. Không gọi `free` cho biến tự động, biến tĩnh hoặc địa chỉ tùy ý.

`free(NULL)` hợp lệ và không làm gì. Nhưng việc đặt **một biến** thành `NULL` sau `free` không sửa các **bí danh con trỏ khác** cùng mang địa chỉ cũ.

### 2.4. Phân biệt nơi lưu con trỏ với nơi lưu đối tượng

```text
Hàm đang chạy:
    Node *head ----------+
    (biến con trỏ)       |
                        v
                  [ Node A ] ---> [ Node B ] ---> NULL
                  malloc          malloc

head tự nó có thời hạn lưu trữ riêng.
Node A và Node B có vòng đời do việc cấp phát/giải phóng chi phối.
```

Nếu `head` là biến cục bộ rồi hàm trả về mà không truyền lại con trỏ, các nút động không tự được giải phóng vì biến `head` biến mất. Khi không còn đường truy cập để `free` những nút ấy, chương trình có thể bị **rò rỉ bộ nhớ (memory leak)**.

## 3. Hợp đồng API: trả con trỏ không đủ nói ai sở hữu

Một hàm trả về `Node *` có thể mang ít nhất hai ý nghĩa hoàn toàn khác nhau:

```c
Node *create_node(int value);         /* Có thể trả quyền sở hữu nút mới. */
Node *find_node(Node *head, int key);  /* Thường chỉ cho mượn nút đã có. */
```

Không thể xác định chính xác trách nhiệm giải phóng chỉ từ kiểu trả về. Một API rõ ràng phải mô tả:

- Hàm có **tạo** đối tượng mới không?
- Nếu có, ai là **chủ sở hữu** khi hàm thành công?
- Nếu trả về con trỏ mượn, con trỏ hợp lệ đến khi nào và thao tác nào làm nó mất hiệu lực?
- Nếu xảy ra lỗi, đầu vào còn thuộc bên gọi không, và có phần tài nguyên nào được tạo mà phải dọn?
- Có cho phép người gọi sửa dữ liệu hoặc liên kết của nút được trả về không?

Ví dụ hợp đồng:

```text
create_node(value):
    Thành công: trả nút mới, caller sở hữu và phải giải phóng hoặc chuyển giao.
    Thất bại: trả NULL, không chuyển bất kỳ quyền sở hữu nào.

list_push_owned(list, node):
    Thành công: list nhận quyền sở hữu node.
    Thất bại: caller vẫn sở hữu node.
    Không gọi free(node) sau khi chuyển giao thành công.

list_find(list, key):
    Trả con trỏ mượn; list vẫn sở hữu nút.
    Không được free trực tiếp nút trả về.
    Con trỏ có thể mất hiệu lực nếu list xóa nút hoặc bị hủy.
```

Cần tách **trả quyền truy cập** khỏi **trả quyền sở hữu**. Đó là nguyên tắc có ích cho toàn bộ chương trình, ngay cả khi ngôn ngữ không có cơ chế kiểm tra quyền sở hữu tĩnh.

## 4. Ví dụ C hoàn chỉnh: danh sách liên kết đơn có một chủ sở hữu

Ta thiết kế một container `List` sở hữu toàn bộ các nút của nó. Cấu trúc có `head` và `size`; mỗi nút có `value` và `next`. Các thao tác chuẩn:

- `list_push_front`: cấp phát nút mới, thêm vào đầu.
- `list_pop_front`: tách đầu, đọc giá trị nếu cần, giải phóng nút cũ.
- `list_clear`: giải phóng từng nút một.
- `list_size`: trả số phần tử theo metadata.

### 4.1. Bất biến của container

Với mọi trạng thái hợp lệ:

1. `head == NULL` **khi và chỉ khi** `size == 0`.
2. Theo các liên kết `next` từ `head` có đúng `size` nút, không tạo chu trình, kết thúc tại `NULL`.
3. Mỗi nút thuộc danh sách do **duy nhất List này sở hữu**; không có container khác được tự do `free` các nút ấy.
4. Giá trị `size` phản ánh số nút hiện còn sống và có thể đi tới từ `head`.

Bất biến không chỉ phục vụ việc tìm kiếm. Chúng quyết định `list_clear` có đi qua **đúng các nút cần giải phóng** hay không.

### 4.2. Mã C có thể biên dịch độc lập

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
    Node *head;
    size_t size;
} List;

void list_init(List *list) {
    if (list == NULL) return;
    list->head = NULL;
    list->size = 0;
}

/* Thành công: danh sách nhận quyền sở hữu của nút mới. */
bool list_push_front(List *list, int value) {
    if (list == NULL || list->size == (size_t)-1) {
        return false;
    }

    Node *node = malloc(sizeof *node);
    if (node == NULL) {
        return false; /* Danh sách giữ nguyên khi không cấp phát được. */
    }

    node->value = value;
    node->next = list->head;

    list->head = node;
    ++list->size;
    return true;
}

/* Lấy/xóa nút đầu. out có thể NULL nếu không cần nhận giá trị. */
bool list_pop_front(List *list, int *out) {
    if (list == NULL || list->head == NULL) {
        return false;
    }

    Node *removed = list->head;
    if (out != NULL) {
        *out = removed->value;
    }

    list->head = removed->next; /* Cập nhật liên kết trước khi free. */
    --list->size;
    free(removed);
    return true;
}

/* Giải phóng tất cả các nút còn thuộc list. */
void list_clear(List *list) {
    if (list == NULL) return;

    Node *current = list->head;
    while (current != NULL) {
        Node *next = current->next; /* Lưu địa chỉ tiếp theo khi còn hợp lệ. */
        free(current);             /* Sau lệnh này không đọc *current nữa. */
        current = next;
    }

    list->head = NULL;
    list->size = 0;
}

size_t list_size(const List *list) {
    return (list != NULL) ? list->size : 0;
}

int main(void) {
    List list;
    list_init(&list);

    if (!list_push_front(&list, 20) ||
        !list_push_front(&list, 10)) {
        list_clear(&list);  /* Dọn cả trạng thái được tạo một phần. */
        return EXIT_FAILURE;
    }

    printf("size before = %zu\n", list_size(&list));

    int popped = 0;
    if (list_pop_front(&list, &popped)) {
        printf("popped = %d\n", popped); /* 10 */
    }

    list_clear(&list);
    printf("size after = %zu\n", list_size(&list)); /* 0 */
    return EXIT_SUCCESS;
}
```

Các điểm quan trọng:

- `list_push_front` gọi `malloc` trước khi thay đổi container; nếu cấp phát thất bại, danh sách **không đổi**.
- Sau khi nối nút mới vào `head`, quyền sở hữu nút thuộc `List`. Người gọi không nhận con trỏ để tự `free`.
- `list_pop_front` phải cập nhật `head` **trước** khi `free(removed)`. Không đọc `removed->next` sau khi giải phóng.
- `list_clear` đọc `current->next` vào `next` khi nút vẫn còn sống; sau đó mới `free(current)`.
- Gọi `list_clear` thêm lần nữa trên container đã được xóa sạch là hợp lệ theo hiện thực này: `head == NULL` nên không có nút nào để giải phóng.

**Giới hạn hợp đồng:** mã này giả sử mọi nút thuộc danh sách được cấp phát hợp lệ và độc quyền sở hữu, không có chu trình, không có thao tác thay đổi từ luồng khác khi đang xử lý. Việc sao chép trực tiếp cả `List` bằng phép gán struct sẽ sao chép **con trỏ head**, không deep copy các nút; hai bản sao khi đó có thể cùng nghĩ mình là chủ sở hữu. Không được dùng kiểu dữ liệu này bằng phép gán như một container có ngữ nghĩa giá trị độc lập.

### 4.3. Chi phí các thao tác

| Thao tác | Thời gian | Bộ nhớ phát sinh |
| --- | --- | --- |
| `list_init` | O(1) | O(1) |
| `list_push_front` | O(1) theo mô hình cấp phát thông thường | O(1) cho một nút |
| `list_pop_front` | O(1) | Không cấp thêm nút; giải phóng một nút |
| `list_clear` với `n` nút | O(n) | O(1) bộ nhớ phụ trợ |
| Truy cập nút thứ `i` từ đầu | O(i), xấu nhất O(n) | O(1) khi duyệt lặp |

Thời gian thực của `malloc/free` phụ thuộc bộ cấp phát và hệ thống; bảng ghi độ phức tạp thao tác liên kết trong mô hình thông dụng, không bảo đảm mọi lời gọi cấp phát đều có giới hạn thời gian cố định trên mọi allocator.

## 5. Những lỗi vòng đời và sở hữu thường gặp

### 5.1. Use-after-free: sử dụng sau khi giải phóng

```c
#include <stdlib.h>

int main(void) {
    int *p = malloc(sizeof *p);
    if (p == NULL) return EXIT_FAILURE;

    *p = 5;
    free(p);

    /* printf("%d\n", *p); SAI: đối tượng không còn hợp lệ. */
    return EXIT_SUCCESS;
}
```

Một con trỏ còn giữ địa chỉ cũ không kéo dài vòng đời đối tượng. Trên môi trường thực, chương trình sai có thể vẫn “in ra đúng” trong vài lần chạy, nhưng đó không làm thao tác trở thành hợp lệ.

### 5.2. Double free: giải phóng cùng vùng hai lần

```c
/* SAI:
int *p = malloc(sizeof *p);
int *q = p;
free(p);
free(q);
*/
```

`q` và `p` là hai biến, nhưng ban đầu chỉ có **một** vùng được cấp phát. Giải phóng hai lần cùng vùng vi phạm hợp đồng bộ cấp phát.

### 5.3. Memory leak: làm mất đường truy cập tới vùng còn sống

```c
/* SAI nếu chưa có nơi khác giữ và quản lý vùng cũ:
int *p = malloc(sizeof *p);
p = malloc(sizeof *p);  // Địa chỉ lần cấp đầu có thể bị thất lạc.
*/
```

Chương trình không còn cách giải phóng vùng đầu nếu đã mất mọi con trỏ tới nó. Cũng có thể rò rỉ tài nguyên khi quên dọn một nhánh xử lý lỗi hoặc giải phóng container mà bỏ sót các đối tượng bên trong nó.

### 5.4. Giải phóng địa chỉ không được cấp phát động

```c
/* SAI:
int local = 42;
free(&local);
*/
```

`local` có thời hạn lưu trữ tự động, không phải khối do `malloc` cấp. Không dùng `free` cho biến cục bộ, biến tĩnh, địa chỉ nội bộ không phải điểm bắt đầu khối cấp phát hoặc địa chỉ tùy ý.

### 5.5. Quên giải phóng dữ liệu lồng nhau

Giả sử một nút có trường `char *name` và mỗi `name` do container cấp phát riêng. Nếu chỉ `free(node)` mà quên `free(node->name)`, vùng chứa tên có thể bị rò rỉ. Ngược lại, nếu `name` là con trỏ **mượn**, việc `free(node->name)` có thể sai.

Đối với đối tượng chứa nhiều lớp tài nguyên, cần **hàm hủy/cleanup** hiểu rõ từng trường nào được sở hữu và thứ tự giải phóng hợp lệ.

### 5.6. Nhầm lẫn giữa “đóng tài nguyên” và “hủy đối tượng quản lý”

Một đối tượng quản lý file hoặc socket có thể tồn tại sau khi `close` được gọi, nhưng không còn tài nguyên mở. Trong chiều ngược lại, xóa tham chiếu tới một đối tượng trong ngôn ngữ có GC **không** bảo đảm file/socket được đóng ngay. Phải hiểu hợp đồng của tài nguyên và API đóng riêng.

## 6. Đường lỗi và quy tắc dọn dẹp một lần

Phần khó của quản lý vòng đời không chỉ là **đường thành công**, mà còn là khi thao tác bị dừng giữa chừng.

Giả sử một hàm phải cấp phát vùng A rồi vùng B. Nếu tạo B thất bại, A phải được thu hồi theo hợp đồng. C có thể dùng một nhãn cleanup duy nhất:

```c
#include <stdio.h>
#include <stdlib.h>

int process_buffers(size_t n) {
    int result = 0;
    unsigned char *a = NULL;
    unsigned char *b = NULL;

    a = malloc(n);
    if (a == NULL) {
        result = -1;
        goto cleanup;
    }

    b = malloc(n);
    if (b == NULL) {
        result = -1;
        goto cleanup;
    }

    /* Ở đây mới là nơi dùng a, b sau khi đã khởi tạo phù hợp.
       Không đọc các byte chưa khởi tạo do malloc trả về. */
    result = 0;

cleanup:
    free(b);
    free(a);
    return result;
}

int main(void) {
    int status = process_buffers(100);
    printf("status = %d\n", status);
    return (status == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
```

Vì `free(NULL)` hợp lệ, phần cleanup có thể gọi `free` cho cả A/B kể cả khi một trong hai chưa được cấp thành công. Điều này giúp hạn chế các nhánh lỗi quên giải phóng.

**Nguyên tắc:** sau khi tài nguyên có chủ sở hữu xác định, mọi lối ra khỏi phạm vi quản lý đều phải đi qua đường **giải phóng hoặc chuyển giao quyền sở hữu** phù hợp. Không tự `free` đối tượng đã bàn giao thành công cho container khác.

### 6.1. Tính nguyên tử ở mức giao diện khi thao tác thất bại

Một thao tác thêm phần tử vào danh sách cần quy định **nếu cấp phát thất bại, danh sách có thay đổi hay không**. Mẫu `list_push_front` ở trên đảm bảo:

- Thất bại: trả `false`, danh sách giữ nguyên.
- Thành công: thêm đúng một nút, tăng `size` đúng một đơn vị.
- Không có “nút lửng” bị thất lạc hoặc chiếm chỗ mà không thể dọn.

Với thao tác phức tạp hơn như chèn vào bảng băm phải rehash hay tạo một nhánh cây nhiều nút, có thể chuẩn bị vùng mới trước, kiểm tra mọi cấp phát, rồi **commit** thay đổi sau khi đủ điều kiện. Nếu không thể đảm bảo hoàn toàn “không thay đổi khi thất bại”, API cần mô tả rõ trạng thái hợp lệ còn lại và cách phục hồi.

## 7. Sao chép, di chuyển và chia sẻ quyết định ai được giải phóng

### 7.1. Sao chép một con trỏ không tạo chủ sở hữu thứ hai an toàn

```c
typedef struct Buffer {
    int *data;
    size_t size;
} Buffer;

/* Giả sử a.data do a sở hữu:
   Buffer b = a;  // Shallow copy của con trỏ.
   Nếu a và b đều gọi free(data) sẽ double free.
*/
```

Phép gán struct C sao chép các trường theo ngữ nghĩa kiểu; trường con trỏ vẫn chỉ tới cùng vùng. Nếu muốn **hai Buffer độc lập**, phải cấp phát bộ đệm mới, sao chép dữ liệu và quy định rõ hai bản sao có trách nhiệm giải phóng riêng.

### 7.2. Chuyển quyền sở hữu (ownership transfer)

Chuyển quyền sở hữu nghĩa là người nhận trở thành chủ sở hữu theo hợp đồng; bên giao **không còn quyền giải phóng** tài nguyên như chủ sở hữu. Trong C, điều này thường được biểu diễn qua hợp đồng hàm, không có kiểm tra tĩnh tự động:

```text
Trước chuyển giao:
  caller --(owns)--> Node X

Sau push_owned thành công:
  list   --(owns)--> Node X
  caller --(không còn sở hữu)--> Node X

Nếu push_owned thất bại:
  caller tiếp tục sở hữu Node X và phải xử lý tiếp.
```

Phần quan trọng nhất không phải “địa chỉ Node X đã đổi” (nó có thể giữ nguyên), mà là **trách nhiệm giải phóng đã đổi**. Một hệ thống quản lý ownership tốt còn làm rõ những tham chiếu mượn nào vẫn hợp lệ sau chuyển giao.

### 7.3. Clone và chia sẻ: hai chiến lược khác nhau

| Chiến lược | Kết quả | Chi phí chính |
| --- | --- | --- |
| Clone toàn bộ `n` nút | Một bộ nút mới độc lập | O(n) thời gian và O(n) vùng nút mới, nếu mỗi payload sao chép O(1) |
| Chia sẻ cùng `head` | Cùng một chuỗi nút | O(1) để tạo liên kết nhưng phải quản lý vòng đời và quyền ghi |
| Sao chép nông container | Container mới, nút/đối tượng đích có thể vẫn dùng chung | Chi phí tạo container nhưng **không** tạo ownership độc lập |
| Chuyển giao ownership | Tài nguyên có chủ mới, thường không nhân bản vùng dữ liệu | Có thể O(1) cho handle; bên giao mất quyền sở hữu |
| Persistent structure chia sẻ nhánh bất biến | Phiên bản mới giữ các nhánh không đổi | Chỉ cấp nút mới cho phần thay đổi, tùy cấu trúc |

Với bảng băm, cây hay đồ thị, clone sâu còn phải xác định liệu phần tử/đỉnh mang con trỏ đến tài nguyên khác có được nhân bản không. Một clone đồ thị có chu trình thường cần bảng ánh xạ nút nguồn → nút đích để không nhân đôi nút logic hay duyệt vô hạn.


## 8. C++: RAII và tài nguyên gắn với vòng đời đối tượng

**RAII (Resource Acquisition Is Initialization)** là cách gắn trách nhiệm quản lý tài nguyên với vòng đời đối tượng C++. Khi đối tượng quản lý bị hủy, destructor của nó thực hiện cleanup phù hợp. Nhờ đó, đường thành công và đường thoát do lỗi/ngoại lệ đều được dọn theo quy tắc của đối tượng còn sống.

Ví dụ, `std::vector<int>` quản lý vùng lưu trữ phần tử, còn `std::unique_ptr<T>` quản lý quyền sở hữu duy nhất đối với một đối tượng động. Thường không cần tự viết cặp `new/delete` trong logic ứng dụng.

### 8.1. Ví dụ `std::unique_ptr` và chuyển quyền sở hữu

```cpp
#include <iostream>
#include <memory>
#include <utility>
#include <vector>

struct Node {
    int value;
};

int main() {
    auto node = std::make_unique<Node>(Node{42});

    // Một unique_ptr không thể sao chép để tạo hai chủ sở hữu.
    // auto another = node;    // Không biên dịch.

    std::unique_ptr<Node> owner = std::move(node);
    // Sau move này, node rỗng theo ngữ nghĩa của unique_ptr.

    if (owner) {
        std::cout << owner->value << "\n"; // 42
    }

    std::vector<int> values{10, 20, 30};
    values.push_back(40); // vector quản lý vùng phần tử của mình.

    // Rời scope: vector và owner tự thực hiện cleanup thích hợp.
}
```

`std::move` tự nó không nhất thiết di chuyển byte hay cấp phát; nó cho phép chọn **ngữ nghĩa move** của kiểu đích. Với `unique_ptr`, phép chuyển làm nguồn không còn sở hữu đối tượng và đích nhận quyền sở hữu. Đối tượng động vẫn có cùng vòng đời, không phải được sao chép sâu.

**Quy tắc thực hành – Rule of Zero:** ưu tiên dùng những trường thành viên biết tự quản lý tài nguyên (như `vector`, `unique_ptr`), để cấu trúc bao ngoài không phải tự viết destructor/copy/move. Nếu bắt buộc tự quản lý con trỏ sở hữu thô, phải cân nhắc đầy đủ copy constructor, copy assignment, move, destructor và cách xử lý ngoại lệ; điều đó dễ sai hơn.

### 8.2. Tham chiếu và iterator mượn không kéo dài vòng đời

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{10, 20};
    int &first = values[0];

    first = 99;  // Sửa giá trị trực tiếp trong vector.

    // Nếu push_back/reserve làm vector cấp phát lại,
    // tham chiếu first có thể bị vô hiệu hóa.
    values.reserve(1000);

    // Không đọc/ghi first sau khi vùng lưu trữ đã bị dời.
    std::cout << values[0] << "\n";
}
```

Tham chiếu `first` được mượn từ một phần tử. Khi `vector` thay đổi kích thước/capacity theo cách làm mất hiệu lực tham chiếu, tham chiếu ấy không tự trỏ sang vùng mới. Không nhầm **vòng đời của vector** với **tính ổn định của địa chỉ từng phần tử**.

Với `std::list<T>`, chèn nút thường không làm mất hiệu lực iterator tới các nút còn sống, nhưng **xóa nút** làm iterator/tham chiếu tới chính nút đó mất hiệu lực. Chọn cấu trúc dữ liệu nên xét cả quy tắc invalidation bên cạnh Big-O.

### 8.3. Không có chủ sở hữu vẫn có thể có nhiều đường tham chiếu

Một `const T&` hoặc `const T*` có thể là đường đọc dữ liệu không sở hữu. Từ khóa `const` chỉ hạn chế cách sửa **thông qua đường đó**, chứ không tự đảm bảo không có alias khác có quyền ghi:

```cpp
int value = 7;
const int &reader = value;
int &writer = value;

writer = 9;
// reader giờ quan sát giá trị 9, nếu đọc trong cùng luồng hợp lệ.
```

Vì vậy “tham chiếu chỉ đọc” không phải là một snapshot. Nếu yêu cầu bản chụp ổn định, phải thiết kế dữ liệu bất biến, copy thích hợp hoặc đồng bộ với mọi tác nhân ghi.

## 9. Sở hữu chia sẻ, đếm tham chiếu và chu trình

Một số cấu trúc có **tài nguyên được nhiều đối tượng cùng sở hữu**. Trong C++, `std::shared_ptr<T>` giữ thông tin về số chủ sở hữu chia sẻ; tài nguyên được quản lý theo cơ chế của nó khi không còn chủ sở hữu mạnh thích hợp.

```cpp
#include <iostream>
#include <memory>

struct Item {
    int value;
};

int main() {
    auto a = std::make_shared<Item>(Item{5});
    std::shared_ptr<Item> b = a; // Hai chủ sở hữu chia sẻ.

    b->value = 12;
    std::cout << a->value << "\n"; // 12

    b.reset(); // a vẫn sở hữu, Item còn sống.
    a.reset(); // Chủ sở hữu mạnh cuối cùng đã rời bỏ Item.
}
```

**Sở hữu chia sẻ không đồng nghĩa dữ liệu bất biến.** Khi nhiều đường tới cùng đối tượng mutable, thay đổi có thể nhìn thấy từ các đường khác. `shared_ptr` quản lý vòng đời theo cơ chế của nó, nhưng **không tự đồng bộ việc sửa các trường** của đối tượng đích giữa nhiều luồng.

### 9.1. Chu trình sở hữu mạnh có thể giữ lại đối tượng

Nếu A sở hữu B và B lại sở hữu A qua hai `shared_ptr`, số chủ sở hữu mạnh có thể không giảm về 0 khi các biến bên ngoài được hủy.

```text
root --> A --shared_ptr--> B
          ^               |
          |               |
          +---shared_ptr--+

Bỏ root: A và B vẫn giữ nhau qua liên kết sở hữu mạnh.
```

Một giải pháp thường gặp là một chiều liên kết dùng `std::weak_ptr`, tức **không tăng số chủ sở hữu mạnh**:

```cpp
#include <memory>

struct Child;

struct Parent {
    std::shared_ptr<Child> child;
};

struct Child {
    std::weak_ptr<Parent> parent; // Liên kết ngược không sở hữu.
};

int main() {
    auto parent = std::make_shared<Parent>();
    auto child = std::make_shared<Child>();

    parent->child = child;
    child->parent = parent;

    // Khi cần truy cập parent từ child:
    if (auto alive = child->parent.lock()) {
        // alive giữ Parent còn sống trong phạm vi này.
    }
}
```

Đây là **lựa chọn thiết kế quyền sở hữu**, không phải quy tắc mọi liên kết ngược đều buộc phải yếu. Trong cây, liên kết cha thường là tham chiếu mượn nếu cha sở hữu con; trong một đồ thị có nhiều kết nối, có thể cần một kho lưu trữ tập trung sở hữu các đỉnh và tất cả cạnh chỉ tham chiếu không sở hữu.

### 9.2. Đếm tham chiếu và GC không cùng một cơ chế

Đếm tham chiếu đơn thuần có thể không tự thu hồi các **chu trình sở hữu mạnh**. Một bộ gom rác dựa trên reachability từ các gốc có thể xử lý những chu trình không còn tới được, tùy runtime. Không nên quy mọi hệ thống “tự dọn rác” thành một thuật toán duy nhất.

Chọn cơ chế quản lý còn phải xét chi phí cập nhật bộ đếm, bộ nhớ metadata, thời điểm destructor chạy, pause của GC, và mức độ cần dự đoán thời điểm tài nguyên được thu hồi.

## 10. Java và Python: GC quản lý bộ nhớ, không thay quy tắc tài nguyên

### 10.1. Vòng đời tham chiếu trong Java

Trong Java, nhiều biến tham chiếu có thể chỉ cùng một đối tượng. Bộ gom rác quản lý vùng nhớ của các đối tượng không còn tới được theo cơ chế runtime, nhưng thời điểm thu hồi **không phải một lời hứa đóng file hay socket ngay lập tức**.

Đối với tài nguyên có API đóng, dùng **try-with-resources**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class Example {
    public static void main(String[] args) {
        try (BufferedReader reader =
                 Files.newBufferedReader(Path.of("input.txt"))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        } catch (IOException error) {
            System.err.println(error.getMessage());
        }
    }
}
```

Đây là ví dụ về **đọc một file có sẵn**; tên `input.txt` cần tồn tại nếu muốn chạy thành công. Khi ra khỏi khối `try`, Java gọi `close` cho `BufferedReader` theo hợp đồng `AutoCloseable`, kể cả khi có ngoại lệ. Bộ nhớ của đối tượng `reader` vẫn do GC quản lý theo cơ chế của runtime.

### 10.2. Python: context manager và vòng đời file

```python
# Giả sử input.txt tồn tại và đọc được.
with open("input.txt", "r", encoding="utf-8") as stream:
    text = stream.read()
    print(text)

# Sau khi rời khối with, stream đã được đóng theo hợp đồng.
```

Khối `with` gọi các phương thức context manager để bảo đảm cleanup, kể cả khi có ngoại lệ. Với danh sách Python, không cần gọi `free` cho từng phần tử theo cách C; nhưng file, socket, transaction hay khóa vẫn có hợp đồng kết thúc riêng.

### 10.3. Rò rỉ logic vẫn xảy ra khi có GC

Bộ gom rác chỉ có thể thu hồi đối tượng khi các điều kiện thu hồi của runtime được thỏa mãn. Nếu ứng dụng giữ một tham chiếu trong cache hoặc cấu trúc toàn cục mà không bao giờ xóa, đối tượng vẫn còn **tới được** dù nghiệp vụ không cần nữa.

```python
cache = []

def keep_object(item):
    cache.append(item)  # cache giữ một đường tham chiếu mạnh.

# Khi cache cứ tăng mà không xóa phần tử,
# bộ nhớ của các đối tượng còn được giữ có thể tăng theo.
```

Đây là rò rỉ theo nghĩa **giữ đối tượng ngoài nhu cầu nghiệp vụ**, không nhất thiết là mất khả năng giải phóng vùng nhớ như trường hợp quên `free` trong C. Chính sách eviction, giới hạn dung lượng và việc xóa tham chiếu không còn cần thiết vẫn rất quan trọng.

## 11. Quyền sở hữu theo từng cấu trúc dữ liệu

Không có một mô hình ownership phù hợp mọi cấu trúc. Hãy xuất phát từ **bất biến và thao tác chính**.

### 11.1. Mảng và mảng động

Một mảng tự động C có vòng đời gắn với phạm vi; mảng động C dùng `malloc` có một vùng cần được giải phóng theo hợp đồng. Container kiểu `std::vector<T>` trong C++ tự quản lý vùng lưu trữ phần tử.

- Khi mảng động **tăng dung lượng**, dữ liệu có thể được chuyển sang vùng mới và những con trỏ/view vào phần tử cũ có thể mất hiệu lực.
- Một **mảng con trỏ** chỉ sở hữu vùng ô con trỏ nếu đó là hợp đồng của container. Nó **không tự động sở hữu các đối tượng** mà các ô trỏ tới.
- Sao chép một mảng giá trị tạo vùng riêng; sao chép một mảng con trỏ có thể chỉ nhân bản các liên kết, không nhân bản đối tượng đích.

Ví dụ, một danh sách các `Task *` có thể là **danh sách mượn task** do một kho trung tâm quản lý, hoặc **danh sách sở hữu task**; cả hai đều có thể được hiện thực bằng cùng kiểu con trỏ, nên API phải nói rõ.

### 11.2. Danh sách liên kết, stack và queue

Với danh sách liên kết cấp phát nút động, việc hủy container thường cần duyệt từng nút và giải phóng **đúng một lần**. Stack dùng danh sách liên kết có thể dùng `push/pop` ở đầu; queue có thể giữ `head/tail` để enqueue/dequeue O(1) về số bước liên kết.

Nhưng mỗi phép xóa phải cập nhật metadata trước khi hủy nút:

```text
Queue trước xóa:
head ---> [10] ---> [20] ---> NULL
                              ^ tail

Sau dequeue [10]:
head ------------> [20] ---> NULL
                    ^ tail

Nếu xóa phần tử cuối:
head = NULL, tail = NULL, size = 0
```

Nếu `tail` vẫn trỏ tới nút đã giải phóng khi queue rỗng, lần thêm tiếp theo có thể ghi qua con trỏ treo. **Bất biến của queue:** khi rỗng, `head` và `tail` cùng null; khi không rỗng, `tail->next` là null và `tail` còn sống.

Với mảng vòng, việc dequeue thường chỉ thay chỉ số, không giải phóng một nút riêng. Nếu phần tử mang tài nguyên, còn phải quy định thao tác xóa phần tử có hủy tài nguyên ấy hay chỉ trả quyền sở hữu cho người gọi.

### 11.3. Bảng băm: bucket, key và value có thể có chủ khác nhau

Một bảng băm có thể sở hữu **vùng bucket** và các **nút/mục** của nó, nhưng chỉ **mượn** con trỏ tới key/value do đối tượng khác quản lý. Cũng có thể bảng băm sở hữu cả key/value, tùy kiểu và API.

Ví dụ các trường hợp thiết kế:

| Bảng băm lưu | Trách nhiệm có thể có |
| --- | --- |
| `char *key` là bản sao động riêng, `Value *value` mượn | Xóa mục phải giải phóng bản sao key và nút, không tự hủy value |
| `char *key` và `Value *value` đều thuộc bảng | Xóa mục phải giải phóng key/value theo hợp đồng, rồi nút |
| Khóa/giá trị nằm trực tiếp trong một đối tượng C++ `unordered_map` | Container quản lý vòng đời các phần tử theo ngữ nghĩa kiểu |
| Bảng trỏ đến các đối tượng do GC quản lý | Xóa mục bỏ tham chiếu, runtime quyết định thu hồi khi thích hợp |

Một phép xóa bucket không đảm bảo đã xử lý mọi tài nguyên **được quản lý bởi từng mục**. Đồng thời, khi key mutable làm thay đổi hash/equality lúc đang nằm trong bảng, bất biến tra cứu có thể bị phá vỡ: quyền sửa key cũng là một phần của hợp đồng container.

### 11.4. Binary heap: các ô chứa giá trị hay con trỏ?

Binary heap thường lưu trong mảng; không phải cấp phát từng nút để giữ quan hệ cha–con. Nếu phần tử là giá trị đơn giản, xóa một phần tử thường chỉ có nghĩa thay đổi dãy phần tử logic và sắp xếp lại bằng sift.

Nếu heap chứa **con trỏ tới đối tượng nghiệp vụ**, phải xác định: heap sở hữu đối tượng, hay chỉ xếp hàng ưu tiên cho các đối tượng do bên khác sở hữu? Nếu có nhiều hệ thống tham chiếu đến cùng đối tượng, việc xóa một ô heap không có nghĩa đối tượng có thể được giải phóng ngay.

### 11.5. Cây: ai sở hữu nút con?

Một cách tổ chức phổ biến là **nút cha sở hữu các nút con**, hoặc toàn bộ cây sở hữu tập nút. Khi hủy cây, có thể duyệt hậu tự để hủy các cây con trước nút cha.

Hàm minh họa cho cây nhị phân **không có chu trình và không chia sẻ nút**:

```c
#include <stdlib.h>

typedef struct TreeNode {
    int value;
    struct TreeNode *left;
    struct TreeNode *right;
} TreeNode;

void free_tree(TreeNode *root) {
    if (root == NULL) return;

    free_tree(root->left);
    free_tree(root->right);
    free(root);
}
```

Với `n` nút, hàm giải phóng O(n) nút và dùng bộ nhớ stack đệ quy O(h), với `h` là chiều cao cây. Cây mất cân bằng nghiêm trọng có thể có `h = O(n)`, làm sâu stack; khi cần phải xem xét cách duyệt lặp phù hợp.

**Không dùng hàm này cho đồ thị có chu trình hoặc cấu trúc chia sẻ cùng nút con:** có thể giải phóng lặp hoặc duyệt vô hạn. Khi một cây con được hai phiên bản dùng chung, phải có cơ chế sở hữu chia sẻ hoặc không sửa đổi thích hợp trước khi quyết định khi nào được hủy nút.

### 11.6. Đồ thị: một nút có nhiều cạnh đến, không được giải phóng theo từng cạnh

Trong đồ thị, một đỉnh có thể có nhiều cạnh đi vào, cạnh ngược hoặc chu trình. Vì vậy **“mỗi cạnh trỏ tới đỉnh thì cạnh có quyền xóa đỉnh”** là sai.

Một mô hình dễ quản lý là:

- Một **kho đỉnh (vertex store)** hoặc **đối tượng đồ thị** sở hữu toàn bộ các đối tượng đỉnh.
- Các cạnh chỉ giữ **ID/chỉ số/tham chiếu không sở hữu** tới đỉnh đích.
- Khi xóa đỉnh, thuật toán trước hết bảo đảm các cạnh/metadata liên quan được cập nhật theo bất biến đồ thị, sau đó mới thu hồi đỉnh.
- Khi hủy đồ thị, giải phóng **mỗi đỉnh đúng một lần**, không đi gọi `free` mỗi khi gặp lại đỉnh theo một cạnh.

```text
Graph store --owns--> Vertex A
            --owns--> Vertex B
            --owns--> Vertex C

A --edge--> C
B --edge--> C
C --edge--> A

Các cạnh là liên kết logic, không phải ba quyền sở hữu độc lập.
```

Nếu đồ thị dùng mảng chỉ số, phải xử lý chỉ số đã bị xóa hoặc tái sử dụng. Một kỹ thuật là dùng **generation counter** cùng chỉ số để phân biệt handle cũ với đối tượng mới chiếm cùng ô, nhưng chi phí và thiết kế cụ thể phụ thuộc hệ thống.

## 12. Cấp phát theo pool/arena: vòng đời theo nhóm

Cấp phát từng nút có thể tốn chi phí allocator và tạo nhiều khối rời rạc. Một **object pool** giữ các ô nút để cấp phát/tái sử dụng; một **arena** có thể cấp nhiều đối tượng từ một vùng lớn và thu hồi theo nhóm.

```text
Arena:
  +------------------------------------------------------+
  | Node A | Node B | Node C | Node D | vùng chưa dùng... |
  +------------------------------------------------------+
          \________________________________/
           Những đối tượng có vòng đời gắn với arena
```

Lợi ích có thể gồm:

- Giảm số lần gọi hệ thống cấp phát tổng quát.
- Dễ thu hồi cả một nhóm đối tượng cùng vòng đời.
- Có thể tăng tính cục bộ dữ liệu khi nhiều nút nằm gần nhau.

Nhưng không phải arena luôn tiết kiệm hơn: vùng dự phòng có thể bị giữ lâu, hoặc một đối tượng cần sống lâu hơn cả nhóm. **Giải phóng arena có thể làm mọi con trỏ mượn tới các nút bên trong mất hiệu lực cùng lúc.** Không được giữ con trỏ tới nút arena để dùng sau khi arena đã bị thu hồi.

Với C++, arena chỉ hoàn trả bộ nhớ thô không nhất thiết tự gọi destructor cho từng đối tượng có tài nguyên. Phải tuân theo hợp đồng allocator/arena cụ thể để đảm bảo các destructor cần thiết vẫn được thực hiện.

### 12.1. Tái sử dụng địa chỉ và “ABA”

Giả sử một nút A tại địa chỉ `0x1000` bị giải phóng, rồi pool cấp lại chính địa chỉ `0x1000` cho một nút B khác. Một handle cũ vẫn chứa `0x1000` có thể trông giống handle tới B nếu chỉ so sánh địa chỉ.

```text
Lúc t1: handle H -> [A tại slot 7]
Lúc t2: A bị xóa, slot 7 trống
Lúc t3: slot 7 được tái sử dụng cho B
Lúc t4: H vẫn ghi slot 7, nhưng nay slot này chứa B
```

Đó là nguyên nhân của một lớp lỗi **stale handle**; trong cấu trúc lock-free, một dạng thay đổi rồi trở lại giá trị con trỏ cũ còn liên quan đến vấn đề **ABA**. Handle gồm **chỉ số + phiên bản (generation)** hoặc cơ chế quản lý epoch/quyền sở hữu có thể giảm nguy cơ nhận nhầm đối tượng, tùy thiết kế. Không tự suy ra “địa chỉ vẫn giống” nghĩa là **đối tượng vẫn là đối tượng cũ**.

## 13. Nhiều luồng: thu hồi bộ nhớ an toàn khó hơn khóa một con trỏ

Nếu một luồng đang duyệt danh sách và luồng khác xóa nút hiện tại rồi `free`, luồng thứ nhất có thể truy cập vùng đã được thu hồi. Chỉ có con trỏ đến nút **không bảo đảm nút còn sống**.

Cần phân biệt:

- **Mutual exclusion / đồng bộ:** bảo vệ các thao tác đọc/ghi cấu trúc và bất biến của container.
- **Memory reclamation:** xác định **khi nào** không còn luồng nào có thể dùng một nút để thu hồi nó an toàn.
- **Ownership:** xác định **ai** có quyền quyết định nút cần được hủy hoặc chuyển quyền sở hữu.

Đối với mã thông thường, sử dụng mutex phù hợp để bảo vệ cả thao tác truy cập lẫn thao tác hủy nút có thể đơn giản hơn việc viết thuật toán lock-free. Với cấu trúc lock-free chuyên dụng, các kỹ thuật như **hazard pointers**, **epoch-based reclamation** hoặc **reference counting** có thể hỗ trợ thu hồi an toàn, nhưng mỗi kỹ thuật cần hợp đồng và chứng minh tính đúng đắn riêng.

**Lưu ý:** `std::shared_ptr` quản lý số chủ sở hữu theo cách thread-safe phù hợp với các thao tác trên các bản sao `shared_ptr`, nhưng không biến mọi trường của đối tượng đích thành atomic. Dùng chung một container có thể sửa giữa nhiều luồng vẫn cần đồng bộ theo quy tắc của container và ngôn ngữ.

## 14. Bảng quyết định: thời gian, bộ nhớ và vòng đời

| Lựa chọn thiết kế | Lợi ích | Chi phí/rủi ro | Khi nên cân nhắc |
| --- | --- | --- | --- |
| Cấp từng nút bằng `malloc/free` | Từng nút có vòng đời linh hoạt | Phí cấp phát, phân mảnh, trách nhiệm cleanup | Nút thêm/xóa riêng lẻ, yêu cầu ổn định địa chỉ |
| Lưu phần tử trực tiếp trong mảng | Bộ nhớ tập trung, ít metadata theo nút | Mở rộng có thể dời dữ liệu, invalidation | Quét nhiều, truy cập theo chỉ số |
| Pool/arena | Giảm chi phí cấp phát nhỏ, thu hồi theo nhóm | Quản lý vùng rỗng, stale handle, lifetime theo nhóm | Nhiều nút có vòng đời gần nhau |
| Sở hữu duy nhất | Quy tắc hủy rõ ràng, dễ kiểm soát | Phải chuyển quyền hoặc clone khi cần chia sẻ sở hữu | Cấu trúc có ranh giới quản lý rõ |
| Sở hữu chia sẻ | Nhiều chủ giữ đối tượng sống | Overhead metadata, chu trình, khó đoán thời điểm hủy | Cần tài nguyên sống qua nhiều thành phần |
| Mượn/view | Tránh copy, ít chi phí tạo | Dễ có dangling khi nguồn bị hủy hoặc dời | Truy cập ngắn hạn trong phạm vi được đảm bảo |
| Sao chép sâu | Dữ liệu độc lập theo ranh giới clone | O(n) hoặc hơn về thời gian/bộ nhớ | Các bên cần sửa độc lập hoặc snapshot thực |
| Dữ liệu bất biến và structural sharing | Nhiều phiên bản dùng chung nhánh | Cần thiết kế bất biến và thu hồi nút chia sẻ | History/undo, truy vấn đọc nhiều |
| GC của runtime | Giảm quản lý giải phóng bộ nhớ thủ công | Giữ đối tượng do còn tham chiếu, pause/overhead | Java/Python và runtime có GC |

Độ phức tạp của một thao tác **không bao gồm tự động chi phí dọn dẹp mà ứng dụng trì hoãn**. Ví dụ: thêm một phần tử vào đầu danh sách O(1), nhưng hủy danh sách `n` nút cần O(n). Nếu phân tích toàn vòng đời từ tạo đến hủy, cần tính cả chi phí dọn dẹp và bộ nhớ còn giữ giữa các giai đoạn.

## 15. Quy trình kiểm tra một API quản lý tài nguyên

Khi thiết kế hoặc đánh giá một cấu trúc dữ liệu, trả lời lần lượt:

1. **Tạo:** đối tượng/nút/tài nguyên được tạo ở đâu và bằng cơ chế nào?
2. **Sở hữu:** thành phần nào chịu trách nhiệm giải phóng? Ai chỉ là borrower?
3. **Chuyển giao:** khi chèn một nút vào container, ownership có chuyển không? Nếu thất bại thì ai vẫn sở hữu?
4. **Bất biến:** `head`, `tail`, `size`, liên kết cha–con, bucket hoặc ánh xạ ID có luôn nhất quán không?
5. **Vòng đời:** khi nào đối tượng hết hiệu lực? Con trỏ, iterator, view hoặc handle nào bị vô hiệu hóa?
6. **Đường lỗi:** nếu cấp phát thứ hai/thứ ba thất bại, các phần đã tạo trước được dọn như thế nào?
7. **Dọn dẹp:** đối tượng con hoặc tài nguyên lồng nhau có cần destructor/`close`/`free` riêng không?
8. **Chia sẻ:** nhiều đường tham chiếu có thể tới cùng nút không? Có chu trình sở hữu hay rủi ro double free không?
9. **Đồng thời:** có luồng nào có thể giữ tham chiếu trong lúc nơi khác định thu hồi nút không?
10. **Chi phí:** thao tác định vị, cấp phát, chuyển quyền, dọn dẹp và phân mảnh ảnh hưởng tới thời gian/bộ nhớ thế nào?

Có thể viết hợp đồng ngắn trong phần tài liệu API, ví dụ:

```text
list_find:
- Returns borrowed Node*; List retains ownership.
- Pointer remains valid only while this node exists and is not erased.
- Caller must not free the node or change its next link.
- O(n) search time, O(1) auxiliary space.

list_clear:
- Releases all nodes currently owned by List.
- Resets head=NULL and size=0.
- Invalidates all borrowed Node* that targeted released nodes.
- O(n) time, O(1) auxiliary space for this iterative implementation.
```

Bảng hợp đồng cụ thể giúp người dùng thư viện phân biệt **khả năng truy cập** với **quyền giải phóng**, đồng thời giảm nguy cơ hiểu sai Big-O.

## 16. Bài tập thực hành có lời giải

### Bài 1. Biến cục bộ và con trỏ trả về

```c
int *create_bad(void) {
    int value = 7;
    return &value;
}
```

**Câu hỏi:** Vì sao `*create_bad()` không an toàn?

**Lời giải:** `value` là biến tự động đã hết vòng đời khi hàm trả về; con trỏ không còn trỏ tới một `int` còn sống. Nên trả giá trị `int` hoặc tạo đối tượng có vòng đời phù hợp, kèm hợp đồng ownership rõ ràng.

### Bài 2. Hai con trỏ và một lần cấp phát

```c
int *p = malloc(sizeof *p);
int *q = p;
```

Giả sử `malloc` thành công. Có thể gọi `free(p); free(q);` không?

**Lời giải:** **Không.** Hai biến con trỏ có cùng địa chỉ một vùng cấp phát. Sau `free(p)`, vùng đã được giải phóng; `free(q)` là giải phóng hai lần. Chỉ một chủ sở hữu phải giải phóng vùng đúng một lần.

### Bài 3. Cách xóa đầu danh sách

Có `Node *head` trỏ tới nút đầu trong danh sách hợp lệ. Đoạn nào đúng?

```c
/* Phương án A: sai. */
free(head);
head = head->next;

/* Phương án B: đúng khi head != NULL và sở hữu nút đầu. */
Node *removed = head;
head = head->next;
free(removed);
```

**Lời giải:** Phương án B đọc `head->next` khi nút còn sống, cập nhật con trỏ đầu rồi mới giải phóng. Phương án A đọc `head->next` **sau khi đã free**, gây use-after-free. Nếu container còn `size` và `tail`, cũng phải cập nhật các metadata liên quan cho đúng.

### Bài 4. Bỏ quên một nút giữa đường

Danh sách `A -> B -> C -> NULL`. Nếu viết `A->next = C` rồi không còn con trỏ nào khác tới B, điều gì xảy ra?

**Lời giải:** Nút B không còn nằm trên đường đi từ đầu danh sách. Nếu B do `malloc` cấp và vẫn còn sống nhưng mất toàn bộ đường tới, vùng B bị **rò rỉ**; đồng thời `size` có thể sai. Phải tách và giải phóng B theo đúng ownership, cập nhật metadata và đảm bảo không có bên khác còn dùng B.

### Bài 5. List sở hữu nút, hàm tìm trả con trỏ mượn

`list_find` trả `Node *found`. Người gọi được phép `free(found)` để “tiết kiệm bộ nhớ” không?

**Lời giải:** **Không**, nếu `List` vẫn sở hữu nút. Làm vậy khiến liên kết của list trỏ vào vùng đã giải phóng và gây double free khi list dọn sau đó. Cần dùng API xóa nút của list để duy trì bất biến và ownership.

### Bài 6. Đếm tham chiếu và chu trình

Hai đối tượng A và B có các `shared_ptr` mạnh trỏ vòng tới nhau, không còn chủ sở hữu nào từ bên ngoài. Chúng có chắc được hủy ngay không?

**Lời giải:** **Không.** Hai liên kết mạnh có thể giữ số chủ sở hữu của nhau khác 0. Nên thiết kế liên kết không sở hữu phù hợp, ví dụ `weak_ptr` cho chiều ngược, hoặc chuyển sang một kho chủ sở hữu tập trung.

### Bài 7. GC có tự đóng file đúng lúc không?

Một chương trình Java chỉ bỏ biến tham chiếu tới `BufferedReader` mà không đóng. Có đảm bảo file được đóng ngay không?

**Lời giải:** **Không.** Không được dựa vào thời điểm GC để thực hiện cleanup tài nguyên ngoài bộ nhớ. Dùng `try-with-resources` hoặc cơ chế đóng có kiểm soát khác theo API.

### Bài 8. Hủy cây có dùng chung nút

Hai nhánh cây cùng trỏ tới một nút con `S`, nhưng hàm `free_tree` đệ quy giải phóng mọi `left`/`right` rồi `free(root)`. Có an toàn không?

**Lời giải:** **Không** với cấu trúc có nút dùng chung. Hàm có thể gặp lại vùng S đã được giải phóng và gây double free/use-after-free. Phải định nghĩa ownership của S (chỉ một chủ sở hữu, sở hữu chia sẻ, hoặc kho chủ sở hữu tập trung) và dùng thuật toán dọn tương ứng.

### Bài 9. Thu hồi arena

Một arena chứa 100.000 nút; một đối tượng ngoài arena giữ con trỏ tới nút thứ 50. Sau khi hủy arena, có được dùng con trỏ ấy không?

**Lời giải:** **Không.** Vòng đời các đối tượng trong arena đã kết thúc theo hợp đồng thu hồi. Mọi con trỏ mượn vào vùng ấy phải được xem là không còn hợp lệ.

### Bài 10. Chi phí dọn danh sách

Một danh sách liên kết đơn có `n` nút cấp phát riêng. `push_front` tốn O(1) theo thao tác liên kết; nếu dùng vòng lặp giải phóng lần lượt toàn bộ `n` nút, `clear` tốn bao nhiêu?

**Lời giải:** **O(n)** thời gian vì mỗi nút cần được thăm và giải phóng một lần; vòng lặp giữ một số con trỏ cố định nên **O(1)** bộ nhớ phụ. Phí thực tế của allocator có thể thay đổi theo môi trường.

### Bài 11. Mảng động và con trỏ mượn

Một hàm giữ `int *p = vector.data()` rồi vector tăng capacity và có cấp phát lại. `p` còn trỏ tới mảng phần tử hiện tại không?

**Lời giải:** **Không.** Khi vùng lưu trữ bị dời, các con trỏ/iterator/tham chiếu vào vùng cũ bị vô hiệu hóa theo quy tắc của vector. Phải lấy lại con trỏ từ container nếu còn cần.

### Bài 12. Chọn cách sở hữu cho đồ thị

Một đồ thị có chu trình `A -> B -> C -> A`. Có nên để mỗi cạnh tự `free` đỉnh đích khi bị xóa không?

**Lời giải:** **Không.** Mỗi đỉnh có thể có nhiều cạnh đến, chu trình và nhiều đường truy cập. Nên có chủ sở hữu của tập đỉnh (ví dụ đối tượng Graph hoặc vertex store) và coi cạnh là liên kết mượn/ID; khi xóa đỉnh, cập nhật các cạnh liên quan rồi thu hồi đúng một lần theo hợp đồng.

## 17. Tổng kết

- **Ownership** trả lời “ai có trách nhiệm giải phóng”, **lifetime** trả lời “đối tượng hợp lệ đến khi nào”, còn **borrowing/aliasing** mô tả những đường truy cập không nhất thiết sở hữu.
- **Tài nguyên không chỉ là bộ nhớ**: file, socket, lock và các handle khác có hợp đồng đóng riêng. GC thu hồi bộ nhớ không thay thế việc đóng tài nguyên ngoại vi có kiểm soát.
- **Cấu trúc dữ liệu cần bất biến vòng đời** bên cạnh bất biến liên kết: mỗi nút phải được giải phóng đúng một lần theo hợp đồng, không còn borrower nào dùng vùng đã thu hồi và mọi metadata phải khớp với các nút còn sống.
- **C++ RAII**, **C cleanup có kỷ luật**, **Java try-with-resources**, **Python with**, pool/arena và sở hữu chia sẻ đều là công cụ giải quyết bài toán tùy môi trường, không phải lựa chọn đúng tuyệt đối.
- Khi so sánh mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, hãy xét cả **chi phí tạo – sử dụng – mở rộng – sao chép – xóa – giải phóng**, tính hợp lệ của view/con trỏ, quyền sở hữu và nhu cầu đồng thời. Một thuật toán nhanh nhưng giữ tài nguyên sai vòng đời vẫn là một hiện thực không đúng.
