# Tham chiếu treo, rò rỉ bộ nhớ và giữ tham chiếu không cần thiết

Một chương trình có thể xử lý đúng dữ liệu ở 100 lần chạy đầu nhưng gặp lỗi ở lần thứ 101: một con trỏ đang giữ địa chỉ của nút đã bị xóa. Một chương trình khác không bao giờ truy cập vùng nhớ đã giải phóng, nhưng bộ nhớ tiêu thụ vẫn tăng vì các nút cấp phát bị thất lạc. Một ứng dụng Java hoặc Python có bộ gom rác (GC) vẫn có thể tăng dần dung lượng sử dụng vì bộ nhớ đệm hoặc bộ lắng nghe sự kiện tiếp tục giữ tham chiếu tới dữ liệu không còn cần thiết.

Đây là ba nhóm vấn đề cần phân biệt:

1. **Tham chiếu/con trỏ treo (dangling reference/pointer):** đường truy cập không còn dẫn tới đối tượng có vòng đời hợp lệ.
2. **Rò rỉ bộ nhớ (memory leak):** tài nguyên bộ nhớ đã cấp vẫn bị chiếm giữ nhưng chương trình không thu hồi theo nhu cầu/hợp đồng.
3. **Giữ tham chiếu không cần thiết (unnecessary retention):** đối tượng vẫn *còn tới được* từ những gốc đang sống, nên chưa thể được thu hồi mặc dù nghiệp vụ đã hết cần.

Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, phần **Bộ nhớ và biểu diễn**, bài này liên hệ các lỗi trên với mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Mục tiêu không chỉ là tránh lỗi bộ nhớ mà còn giữ **bất biến liên kết và vòng đời**, dự toán **thời gian/bộ nhớ**, và lựa chọn mô hình sở hữu phù hợp.

## 1. Ba vấn đề: định nghĩa và sự khác nhau

### 1.1. Tham chiếu treo: còn đường truy cập, không còn đối tượng hợp lệ

Hãy hình dung một nút được cấp phát động:

```text
Thời điểm t1:
head ----> [ Node A | next ] ----> [ Node B | NULL ]
              ^
borrowed -----+

Thời điểm t2: Node A đã bị giải phóng, head trỏ sang B
head ----------------------------> [ Node B | NULL ]
borrowed ---> [ vùng A đã thu hồi ]  X không được dereference
```

Biến `borrowed` có thể vẫn chứa một địa chỉ; nhưng vùng A đã hết vòng đời và có thể được bộ cấp phát tái sử dụng. Đọc `borrowed->value` hoặc ghi `borrowed->next` sau khi A bị giải phóng là **use-after-free**. Không thể suy luận “giá trị con trỏ khác `NULL` thì hợp lệ”.

### 1.2. Rò rỉ bộ nhớ: còn khối cấp phát, mất trách nhiệm thu hồi

```text
Ban đầu:
root ---> [ Node A ] ---> [ Node B ] ---> NULL

Sai sót:
root -------------------> [ Node B ] ---> NULL
          [ Node A ]  (vẫn được cấp phát, không còn đường hợp lệ tới)

Node A không được giải phóng và có thể không còn cách truy cập để free.
```

Khi không còn con trỏ nào để giải phóng khối được cấp bằng `malloc`, đó là tình huống **rò rỉ do mất đường truy cập**. Trong thực tế, còn có rò rỉ do quên chạy hàm cleanup ở nhánh lỗi hoặc do hai thành phần không thống nhất ai có trách nhiệm giải phóng.

### 1.3. Giữ tham chiếu không cần thiết: đối tượng vẫn tới được

```text
Gốc đang sống (global cache)
            |
            v
      [ cache entry ] ------> [ Đối tượng báo cáo lớn ]
                                     |
                                     v
                              [ mảng dữ liệu lớn ]

Nghiệp vụ đã xong nhưng cache entry vẫn giữ đường tham chiếu mạnh.
Bộ gom rác vẫn xem báo cáo là đối tượng có thể tới được.
```

Đối tượng có thể hoàn toàn hợp lệ và chương trình không có lỗi truy cập bộ nhớ. Tuy vậy, nếu cache tiếp tục giữ những báo cáo không dùng tới, dung lượng giữ lại tăng theo thời gian: đây là **rò rỉ logic do giữ tham chiếu** (*logical leak/unnecessary retention*).

### 1.4. So sánh nhanh

| Đặc điểm | Tham chiếu treo | Rò rỉ do thất lạc cấp phát | Giữ tham chiếu không cần thiết |
| --- | --- | --- | --- |
| Đối tượng đích còn hợp lệ? | Không | Có thể vùng vẫn cấp nhưng không quản lý được | Có |
| Có thể truy cập an toàn qua đường đang xét? | Không | Thường đã mất đường truy cập | Thường có, nhưng không cần |
| Vấn đề chính | Sai an toàn/vòng đời | Tài nguyên không được thu hồi | Đối tượng sống quá lâu |
| Ví dụ C | `p` trỏ đến vùng đã `free` | Ghi đè con trỏ `malloc` duy nhất | Danh sách giữ các nút đã hết nghiệp vụ |
| Ví dụ Java/Python | Thường được runtime ngăn với đối tượng managed thông thường; vẫn có rủi ro qua native handle/view | Có thể rò rỉ tài nguyên ngoài bộ nhớ | Cache/listener/closure giữ đối tượng |
| Khắc phục chính | Không dùng sau khi hết vòng đời; kiểm soát invalidation | Xác định chủ sở hữu, giải phóng mọi đường thoát | Xóa các tham chiếu không còn cần, giới hạn cache, vòng đời scope |

**Không phải mọi trường hợp bộ nhớ dùng nhiều đều là leak.** Dữ liệu còn cần và được quản lý đúng có thể chiếm nhiều RAM hợp lệ; allocator hay GC cũng có thể giữ vùng dự trữ để tái sử dụng thay vì trả ngay cho hệ điều hành.

## 2. Vòng đời đối tượng và lúc con trỏ mất hiệu lực

Cần phân biệt **vòng đời biến con trỏ** với **vòng đời đối tượng mà nó chỉ đến**.

```text
Thời gian ─────────────────────────────────────────────────────>

Đối tượng O:  tạo ├──────────── còn sống ──────────────┤ hủy
Con trỏ p:        ├──────────────────────────────────────────┤
                                                          ^
              p còn tồn tại nhưng không được dùng để đọc O sau khi O hủy
```

Một con trỏ mượn chỉ hợp lệ **chừng nào đối tượng gốc vẫn còn sống và các thao tác trên container chưa vô hiệu hóa nó**. Điều này quan trọng ngay cả với ngôn ngữ có hệ thống quản lý bộ nhớ tự động: nếu view tới tài nguyên ngoài đã bị đóng hoặc buffer bị hủy, vẫn phải tuân thủ hợp đồng của view/tài nguyên.

### 2.1. Use-after-free trong C

```c
#include <stdlib.h>

int main(void) {
    int *p = malloc(sizeof *p);
    if (p == NULL) return EXIT_FAILURE;

    *p = 10;
    int *alias = p;  /* p và alias trỏ cùng đối tượng. */

    free(p);
    p = NULL;        /* Chỉ thay giá trị con trỏ p. */

    /* *alias = 20;  SAI: alias trỏ vùng đã free. */
    return EXIT_SUCCESS;
}
```

Trong ví dụ, đặt `p = NULL` là một cách tránh vô tình dùng lại **chính biến p**. Nó **không đặt `alias` thành NULL**, cũng không vô hiệu hóa mọi bản sao địa chỉ khác theo cách có thể kiểm tra chỉ với `if (ptr != NULL)`.

Sau `free`, không đọc hoặc ghi vùng cũ, không dùng giá trị con trỏ cũ như một “handle hợp lệ” và không gọi `free` lần thứ hai cho cùng khối. Địa chỉ cũ có thể được cấp lại cho đối tượng hoàn toàn khác.

### 2.2. Use-after-scope: trả địa chỉ biến cục bộ

```c
/* Ví dụ SAI, chỉ để nhận diện lỗi. */
int *bad_address(void) {
    int local = 42;
    return &local;
}

/* Không được dereference con trỏ trả về sau khi local hết vòng đời. */
```

Biến `local` có *automatic storage duration*; sau khi hàm trở về, đối tượng không còn vòng đời hợp lệ. Không nên coi việc vùng stack tình cờ giữ nguyên byte là bằng chứng tham chiếu an toàn.

Các hướng sửa thông dụng: trả **giá trị** `int`; để caller cấp chỗ rồi truyền địa chỉ vào hàm; hoặc cấp phát đối tượng động và trả về với **hợp đồng sở hữu rõ ràng**.

### 2.3. Con trỏ/iterator treo do container cấp phát lại

Không nhất thiết phải gọi `free` trực tiếp mới làm con trỏ cũ mất hiệu lực. Mảng động có thể chuyển vùng lưu trữ khi tăng dung lượng.

```cpp
#include <vector>

int main() {
    std::vector<int> values{10, 20};
    int *borrowed = values.data();

    values.reserve(1000);  // Có thể thay vùng lưu trữ.

    // Không được dereference borrowed nếu reserve đã làm nó mất hiệu lực.
    (void)borrowed;
}
```

Trong C++, khi `std::vector` cấp phát lại, các con trỏ, tham chiếu và iterator đang trỏ vào phần tử cũ bị vô hiệu hóa theo quy tắc của container. Một số thao tác có thể vô hiệu hóa **chỉ một phần** iterator dù không cấp phát lại; cần kiểm tra hợp đồng thao tác, không suy luận chung rằng “cứ dùng vector là con trỏ ổn định”.

Ngược lại, với danh sách liên kết ổn định địa chỉ nút, việc **xóa nút cụ thể** vẫn làm mọi con trỏ mượn tới nút ấy mất hiệu lực.

### 2.4. View và slice: “không sở hữu” có thể treo

Một `std::span<T>` trong C++20 là một view không sở hữu đoạn phần tử. Nếu container nguồn bị hủy hoặc vùng chứa bị dời, span cũ không tự kéo dài vòng đời dữ liệu. Một `std::string_view` tham chiếu tới vùng ký tự hết vòng đời cũng có nguy cơ treo.

```cpp
#include <string>
#include <string_view>

std::string_view bad_view() {
    std::string temporary = "hello";
    return std::string_view(temporary); // SAI: dữ liệu temporary sắp chết.
}

/* Không được đọc ký tự qua view trả về từ bad_view(). */
```

**Hợp đồng của view:** nơi tạo phải bảo đảm đối tượng gốc sống đủ lâu; nơi sử dụng không được giữ view vượt thời hạn ấy. Nếu cần dữ liệu tồn tại độc lập, sao chép nội dung sang đối tượng **sở hữu** như `std::string`.

## 3. Rò rỉ bộ nhớ thủ công trong C: những đường dẫn sai

### 3.1. Ghi đè con trỏ duy nhất trước khi `free`

```c
/* Mô tả lỗi, không nên chạy:
int *data = malloc(100 * sizeof *data);
data = malloc(200 * sizeof *data);
*/
```

Nếu khối đầu được cấp phát thành công và không có con trỏ nào khác quản lý nó, phép gán lại `data` làm mất địa chỉ của khối đầu; vùng này không thể được `free` theo cách thông thường nữa. Việc cấp phát sau có thành công hay không **không làm khối đầu tự được thu hồi**.

Khi muốn thay vùng, phải xây một quy trình có chủ sở hữu và xử lý lỗi: dùng con trỏ tạm để giữ kết quả, chuyển dữ liệu nếu cần, sau đó dọn vùng cũ theo hợp đồng.

### 3.2. Dùng `realloc` trực tiếp vào chính con trỏ

Một lỗi tương tự xuất hiện nếu ghi:

```c
/* Không an toàn khi realloc thất bại:
data = realloc(data, new_size);
*/
```

Nếu `realloc` trả `NULL` do thất bại với yêu cầu `new_size > 0`, **vùng cũ vẫn được giữ lại** theo hợp đồng C, nhưng phép gán đã làm mất con trỏ cũ.

Cách an toàn hơn:

```c
#include <stdlib.h>

int grow_int_buffer(int **data, size_t new_count) {
    if (data == NULL || *data == NULL) return 0;
    if (new_count == 0 ||
        new_count > ((size_t)-1) / sizeof **data) {
        return 0;  /* Tránh tràn khi nhân kích thước, chọn chính sách rõ. */
    }

    int *candidate = realloc(*data, new_count * sizeof **data);
    if (candidate == NULL) {
        return 0;  /* *data vẫn trỏ vùng cũ, caller còn sở hữu. */
    }

    *data = candidate; /* Chuyển sang vùng mới nếu realloc thành công. */
    return 1;
}
```

Hàm này có **hợp đồng cụ thể**: `*data` phải trỏ đến một khối cấp phát động có thể gọi `realloc`, không chấp nhận `new_count == 0`, và caller tiếp tục sở hữu khối trước/sau thao tác. Trường hợp `realloc` di chuyển khối thì các con trỏ mượn vào vùng cũ sẽ mất hiệu lực; ngay cả khi vùng không di chuyển, phải tuân thủ quy tắc hiệu lực của con trỏ và thao tác theo chuẩn áp dụng.

**Không xử lý `realloc(p, 0)` bằng trực giác** vì đặc điểm lịch sử/phiên bản chuẩn và hành vi thư viện có thể khác; ví dụ chọn từ chối kích thước 0 và yêu cầu caller gọi `free` khi muốn xóa vùng.

### 3.3. Nhánh lỗi và đường về sớm

```c
#include <stdlib.h>

int do_work(void) {
    char *first = malloc(100);
    if (first == NULL) return 0;

    char *second = malloc(200);
    if (second == NULL) {
        free(first);  /* Phải dọn first trước khi thoát. */
        return 0;
    }

    /* Công việc với first và second. */
    free(second);
    free(first);
    return 1;
}
```

Mỗi nhánh rời hàm cần giải phóng những tài nguyên **vẫn thuộc quyền sở hữu của hàm**. Với nhiều tài nguyên, nhãn `cleanup:` hoặc một đối tượng RAII trong C++ giúp tránh bỏ sót.

### 3.4. Chỉ `free` container, quên các phần tử được cấp riêng

```c
typedef struct Node {
    char *name;       /* Nếu từng name được cấp động và node sở hữu nó. */
    struct Node *next;
} Node;
```

Nếu dọn từng nút bằng `free(node)` nhưng bỏ qua `free(node->name)`, các chuỗi được cấp riêng sẽ bị rò rỉ nếu không còn nơi sở hữu khác. Trái lại, nếu `name` là con trỏ **mượn**, việc giải phóng nó có thể sai. Chính sách cleanup phải dựa trên **hợp đồng sở hữu từng trường**, không chỉ kiểu con trỏ.

### 3.5. Rò rỉ không phải luôn là mất mọi con trỏ

Một chương trình có thể cố ý giữ tất cả nút trong một danh sách toàn cục, dù nghiệp vụ không cần nữa. Vùng đó vẫn có đường truy cập và về kỹ thuật có thể giải phóng được, nhưng do không có chính sách xóa, dung lượng tăng vô hạn. Trường hợp này gần với **giữ tham chiếu không cần thiết**.

Trong môi trường C/C++, người ta còn phân biệt “khối không thể tới được” và “khối vẫn được giữ nhưng không cần” khi dùng công cụ dò rò rỉ. **Phân loại phụ thuộc cách công cụ xét các gốc tham chiếu và vòng đời dự kiến**, không phải mọi khối chưa `free` ở thời điểm đo đều là lỗi.

## 4. Xóa đúng một nút trong danh sách: liên kết trước, giải phóng sau

Ta xây dựng một danh sách liên kết đơn với **chủ sở hữu duy nhất**: `List` sở hữu mọi nút có thể tới từ `head`. Bất biến:

1. Các nút thuộc danh sách tạo thành chuỗi không có chu trình, kết thúc tại `NULL`.
2. `size` đúng bằng số nút còn sống có thể tới từ `head`.
3. Mọi nút do danh sách cấp phát được giải phóng đúng một lần khi xóa hoặc dọn danh sách.
4. Các con trỏ trả về từ thao tác tìm kiếm chỉ **mượn** nút; không được tự `free` và có thể mất hiệu lực khi nút bị xóa.

### 4.1. Ví dụ C đầy đủ, xử lý đường cấp phát thất bại

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

bool list_push_front(List *list, int value) {
    if (list == NULL || list->size == (size_t)-1) {
        return false;
    }

    Node *fresh = malloc(sizeof *fresh);
    if (fresh == NULL) return false;

    fresh->value = value;
    fresh->next = list->head;
    list->head = fresh;
    ++list->size;
    return true;
}

/* Trả về con trỏ MƯỢN, chỉ hợp lệ khi nút còn sống. */
const Node *list_find(const List *list, int value) {
    if (list == NULL) return NULL;
    for (const Node *p = list->head; p != NULL; p = p->next) {
        if (p->value == value) return p;
    }
    return NULL;
}

/* Xóa lần xuất hiện đầu tiên của value, nếu có. */
bool list_erase_first(List *list, int value) {
    if (list == NULL) return false;

    Node **link = &list->head;
    while (*link != NULL) {
        Node *current = *link;
        if (current->value == value) {
            *link = current->next;  /* Tách nút trước khi giải phóng. */
            --list->size;
            free(current);
            return true;
        }
        link = &current->next;
    }
    return false;
}

void list_clear(List *list) {
    if (list == NULL) return;

    Node *current = list->head;
    while (current != NULL) {
        Node *next = current->next; /* Đọc khi current còn sống. */
        free(current);
        current = next;            /* Không đọc lại current. */
    }
    list->head = NULL;
    list->size = 0;
}

int main(void) {
    List list;
    list_init(&list);

    if (!list_push_front(&list, 30) ||
        !list_push_front(&list, 20) ||
        !list_push_front(&list, 10)) {
        list_clear(&list);         /* Dọn phần đã cấp phát. */
        return EXIT_FAILURE;
    }

    const Node *borrowed = list_find(&list, 20);
    if (borrowed != NULL) {
        printf("Before erase: %d\n", borrowed->value);
    }

    if (list_erase_first(&list, 20)) {
        /* borrowed trỏ đến nút đã xóa: KHÔNG được dereference. */
        borrowed = NULL;
    }

    printf("Size after erase: %zu\n", list.size); /* 2 */
    list_clear(&list);
    return EXIT_SUCCESS;
}
```

Đặc điểm của cách dùng `Node **link`:

- `link` trỏ tới **ô con trỏ đang dẫn tới nút hiện tại**, có thể là `list->head` hoặc trường `next` của nút trước.
- Khi tìm thấy nút, `*link = current->next` cập nhật đúng ô liên kết mà không cần một nhánh riêng cho nút đầu.
- `free(current)` chỉ thực hiện **sau khi** đã nối lại chuỗi.
- `list_clear` lưu `next` trước khi thu hồi `current`, tránh lỗi đọc `current->next` sau `free`.

**Giới hạn:** danh sách này chỉ có nút chứa `int`, không chia sẻ nút với container khác và không có chu trình. Đây là hợp đồng sở hữu của ví dụ, không phải điều kiện đúng cho mọi danh sách liên kết.

### 4.2. Độ phức tạp và invalidation

| Thao tác | Thời gian theo mô hình thông dụng | Bộ nhớ phụ | Con trỏ mượn bị ảnh hưởng |
| --- | --- | --- | --- |
| `list_push_front` | O(1) bước liên kết và một cấp phát | O(1) nút mới | Con trỏ tới nút cũ vẫn hợp lệ trong ví dụ |
| `list_find` | O(n) xấu nhất | O(1) | Không tự xóa nút |
| `list_erase_first` | O(n) xấu nhất; sau khi tìm nút, việc nối lại O(1) | O(1) | Con trỏ tới nút bị xóa mất hiệu lực |
| `list_clear` | O(n) | O(1) | Tất cả con trỏ tới các nút đã xóa mất hiệu lực |

Chi phí thực tế của `malloc/free` phụ thuộc allocator. Bảng tính theo **số thao tác trên cấu trúc** trong mô hình chuẩn, không phải cam kết mọi lần cấp phát/giải phóng đều chạy trong cùng thời lượng.

### 4.3. Không sửa lỗi bằng “đặt NULL cho tất cả” theo suy đoán

Nếu chương trình có nhiều alias đến cùng nút, đặt **một** con trỏ thành `NULL` không sửa những alias còn lại. Thay vào đó, API nên quy định:

- Con trỏ mượn được giữ trong phạm vi thao tác nào.
- Thao tác xóa nào làm các lối mượn mất hiệu lực.
- Có cần ID ổn định, handle kèm generation hoặc kiểu sở hữu đặc biệt hay không.
- Liệu có được dùng lối mượn khi cấu trúc đang bị sửa từ nơi khác.

Trong nhiều thiết kế, giải pháp đơn giản nhất là **không lưu lâu con trỏ mượn tới nút có thể bị xóa**; hãy giữ định danh logic rồi tra cứu lại qua container khi cần.

## 5. Vùng đã giải phóng có thể được tái sử dụng: stale handle và ABA

Một vấn đề khó là **địa chỉ tái sử dụng**. Giả sử pool có các slot nút; một đối tượng A ở slot 7 bị xóa, sau đó B được đặt vào slot 7:

```text
t1: handle H = slot 7  ---> Node A (version 12)
t2: xóa A, slot 7 được đưa vào danh sách ô trống
t3: cấp phát B ở slot 7 ---> Node B (version 13)
t4: H vẫn bằng slot 7, nhưng A không còn tồn tại
```

Nếu chỉ so sánh **chỉ số slot**, handle cũ có thể trông hợp lệ đối với đối tượng B. Đối với bộ nhớ thuần C/C++, con trỏ cũ hết hiệu lực không nên được dereference; việc địa chỉ mới trùng địa chỉ cũ không cho phép “hồi sinh” con trỏ cũ một cách tùy tiện.

Một giải pháp thiết kế là **generational handle** gồm `(index, generation)`. Khi tái sử dụng slot, tăng generation; trước khi truy cập, kiểm tra generation của handle khớp với slot hiện tại.

```text
Handle cũ: (7, 12)   Slot 7 đang ở generation 13  -> không hợp lệ.
Handle mới: (7, 13)  Slot 7 đang ở generation 13  -> có thể truy cập.
```

Điều này cần bổ sung kiểm tra chỉ số, giới hạn số phiên bản và xử lý generation wrap-around nếu có. Trong cấu trúc lock-free, một dạng giá trị được thay từ A sang B rồi lại giống A còn liên quan tới **vấn đề ABA**; giải pháp đúng cần xem cả đồng bộ và quy trình thu hồi, không chỉ thêm một trường generation.

## 6. Rò rỉ logic: GC không thể tự đoán dữ liệu nào đã hết giá trị nghiệp vụ

Bộ gom rác thường xác định đối tượng nào **còn tới được** từ các gốc tham chiếu; GC không biết rằng một báo cáo đã hết hạn sử dụng hoặc một listener không còn cần thiết.

### 6.1. Gốc tham chiếu và đường giữ đối tượng

Một mô hình đơn giản về reachability:

```text
GC roots
   |
   +--> global_cache --> Map entry --> Report --> LargeBuffer
   |
   +--> active_window --> callback --> captured_model --> Data
   |
   +--> running_task --> local reference --> TemporaryGraph

Dù màn hình đã đóng hoặc request đã kết thúc,
nếu một đường tham chiếu mạnh vẫn giữ đối tượng, GC có thể giữ nó.
```

Không phải mọi runtime đều dùng đúng tập gốc hay thuật toán GC giống nhau, nhưng **đường truy cập từ gốc còn sống** là cách rất hữu ích để phân tích retention.

### 6.2. Python: cache không giới hạn

```python
history = []

def retain_report(report):
    history.append(report)

for i in range(1000):
    retain_report(bytearray(100_000))

print(len(history))  # 1000: các báo cáo vẫn được history giữ.
```

Đây là ví dụ có chủ ý tạo ra nhiều khối dữ liệu còn tới được từ biến `history`. Nếu ứng dụng chỉ cần giữ mười báo cáo gần nhất, danh sách không giới hạn là thiết kế sai về vòng đời nghiệp vụ.

Một lựa chọn giới hạn số phần tử:

```python
from collections import deque

recent_reports = deque(maxlen=10)

def retain_recent(report):
    recent_reports.append(report)  # Phần tử cũ nhất bị loại khi đầy.

for i in range(1000):
    retain_recent(bytearray(100_000))

print(len(recent_reports))  # 10
```

Khi phần tử cũ bị loại khỏi `deque`, nó **không tự bảo đảm được giải phóng ngay lập tức**: có thể còn tham chiếu nơi khác, hoặc runtime giữ các vùng bộ nhớ để tái sử dụng. Tuy vậy, việc giới hạn container giúp tránh **retention không giới hạn do chính container này**.

### 6.3. Java: bộ nhớ đệm dạng static

```java
import java.util.ArrayList;
import java.util.List;

class ReportCache {
    private static final List<byte[]> REPORTS = new ArrayList<>();

    static void keep(byte[] report) {
        REPORTS.add(report);
    }

    static void clear() {
        REPORTS.clear();  // Bỏ các tham chiếu mà list này đang giữ.
    }
}
```

Khi `REPORTS` tiếp tục tăng, những mảng byte vẫn tới được qua danh sách static nên chưa đủ điều kiện thu hồi theo kiểu “không còn tham chiếu”. Gọi `clear()` bỏ liên kết từ cache, nhưng **không tự hủy** đối tượng nếu nơi khác vẫn giữ tham chiếu, cũng không bảo đảm heap/physical RAM giảm ngay.

Với cache thực tế, nên xác định **dung lượng tối đa**, **thời hạn sống**, chính sách thay thế và tác động cạnh tranh bộ nhớ. Dùng `WeakReference` có thể có chỗ đứng trong một số thiết kế, nhưng **không thay thế** việc xây cache có hợp đồng rõ về tính sẵn có và hiệu năng.

### 6.4. Listener/callback giữ màn hình hoặc mô hình dữ liệu

```text
EventBus (sống suốt ứng dụng)
   |
   v
registered callback
   |
   v
captured view-model
   |
   v
big data + view state

Màn hình đóng nhưng callback chưa unsubscribe:
view-model vẫn có đường tham chiếu từ EventBus.
```

Cách xử lý là đăng ký và **hủy đăng ký** theo cùng vòng đời, hoặc dùng đối tượng quản lý subscription có phương thức `close/dispose`. Với callback bất đồng bộ, cần xét thêm việc callback **đang chạy** và đồng bộ việc kết thúc để không sử dụng đối tượng đã hủy.

### 6.5. Closure cũng có thể là gốc giữ dữ liệu

```python
def make_reader():
    big_data = bytearray(2_000_000)

    def read_first():
        return big_data[0]  # Closure giữ tham chiếu tới big_data.

    return read_first

reader = make_reader()
# big_data tiếp tục được giữ qua reader mặc dù make_reader đã kết thúc.
```

Nếu `reader` được lưu trong một registry lâu dài, vùng dữ liệu nằm trong closure có thể sống lâu hơn dự kiến. Khi không còn cần, bỏ những tham chiếu tới callback, hoặc thay thiết kế để chỉ capture dữ liệu cần thiết.

**Không phải việc closure giữ dữ liệu luôn là lỗi.** Nếu callback còn cần đọc mảng, đó là một phụ thuộc hợp lệ. Vấn đề là **vòng đời thực tế dài hơn vòng đời yêu cầu**.

## 7. Chu trình tham chiếu: khác nhau giữa đếm tham chiếu và GC dựa trên reachability

### 7.1. C++: `shared_ptr` trong chu trình sở hữu mạnh

```cpp
#include <memory>

struct Node {
    std::shared_ptr<Node> next;
};

int main() {
    auto a = std::make_shared<Node>();
    auto b = std::make_shared<Node>();

    a->next = b;
    b->next = a;

    // Khi a và b bên ngoài rời scope, hai nút vẫn sở hữu mạnh lẫn nhau.
}
```

Với `std::shared_ptr`, hai liên kết sở hữu mạnh làm số chủ sở hữu không về 0 dù các biến địa phương đã hết phạm vi, gây **giữ tài nguyên do chu trình**. Nếu đây là quan hệ hai chiều hoặc liên kết không sở hữu, có thể thiết kế một cạnh dùng `std::weak_ptr`:

```cpp
#include <memory>

struct Child;
struct Parent {
    std::shared_ptr<Child> child;
};
struct Child {
    std::weak_ptr<Parent> parent;
};

int main() {
    auto parent = std::make_shared<Parent>();
    auto child = std::make_shared<Child>();

    parent->child = child;
    child->parent = parent; // Liên kết không sở hữu, không tạo chu trình mạnh.
}
```

`weak_ptr` không giữ đối tượng đích sống bằng chủ sở hữu mạnh; khi cần sử dụng, phải thử `lock()` rồi kiểm tra kết quả. **Không thay thế mọi con trỏ bằng `shared_ptr`**: sở hữu chia sẻ có overhead và không phù hợp nếu chỉ một container cần sở hữu các nút.

### 7.2. GC theo khả năng tới được có thể thu hồi chu trình không còn gốc

Trong nhiều runtime có GC đánh dấu từ các gốc, một chu trình đối tượng **không còn tới được** có thể được thu hồi, dù mỗi đối tượng trong chu trình vẫn có tham chiếu tới đối tượng khác.

```text
Trước:
ROOT --> A --> B --> C --> A

Sau khi ROOT bỏ tham chiếu:
         A --> B --> C --> A
         (chu trình không còn đường từ gốc)
```

Chu trình tự nó không phải lý do giữ đối tượng mãi trong một collector dựa trên reachability. Tuy nhiên, nếu còn một registry/callback/cache từ gốc trỏ tới A, **toàn bộ chu trình vẫn tới được** và vẫn có thể bị giữ. Các runtime có cơ chế bổ sung (reference counting, cycle detection, finalization) và thời điểm thu hồi khác nhau, nên không suy ra quá cụ thể từ một sơ đồ chung.

### 7.3. Đừng nhầm memory leak với resource leak

Đối tượng file trong Java/Python có thể được GC thu hồi bộ nhớ khi không còn tham chiếu, nhưng **đóng descriptor/file handle phải theo hợp đồng tài nguyên**. Dựa vào GC để đóng tài nguyên bên ngoài thường không bảo đảm thời điểm đóng.

```python
# Tốt: đóng file có kiểm soát kể cả khi có ngoại lệ.
with open("example.txt", "r", encoding="utf-8") as stream:
    first_line = stream.readline()
```

Ví dụ giả sử file `example.txt` tồn tại và đọc được. Với Java, `try-with-resources` thực hiện vai trò tương ứng cho kiểu triển khai `AutoCloseable`.


## 8. Phân tích từng cấu trúc dữ liệu: nơi dễ xảy ra lỗi vòng đời

Cùng một khối bộ nhớ nhưng những **đường liên kết** và **quy tắc xóa** khác nhau có thể tạo rủi ro khác nhau. Trước khi gọi `free`, xóa một ô hoặc bỏ một tham chiếu, cần xét bất biến của chính cấu trúc.

### 8.1. Mảng động: giữ con trỏ tới phần tử quá lâu

Mảng liên tiếp có lợi cho cache và truy cập theo chỉ số O(1), nhưng thêm phần tử làm vượt `capacity` có thể yêu cầu cấp phát lại. Khi đó con trỏ vào phần tử cũ có thể mất hiệu lực.

```text
Trước khi tăng capacity:
ptr ----> [10][20][30]           capacity 3
          ^ vùng A

Sau khi tạo vùng B:
          [vùng A đã bị thu hồi]
          [10][20][30][...][...]  capacity 5, vùng B

ptr cũ không tự đổi thành địa chỉ vùng B.
```

Nếu cần giữ “định danh phần tử” qua nhiều lần mở rộng, có thể lưu **chỉ số** và truy cập lại qua container mỗi lần; nhưng chỉ số cũng có thể bị ảnh hưởng bởi thao tác chèn/xóa gây dịch vị trí. Nếu cần định danh bền hơn, cân nhắc handle kèm generation hoặc cấu trúc lưu trữ ổn định phù hợp với thao tác.

### 8.2. Danh sách liên kết: xóa một nút nhưng quên cập nhật đầu/cuối

Với danh sách đơn có `head`, `tail` và `size`:

- Khi xóa nút đầu, `head` phải dẫn tới nút mới.
- Khi xóa nút cuối, `tail` phải được cập nhật về nút trước hoặc `NULL` nếu danh sách rỗng.
- Nếu còn nút, `tail->next == NULL`.
- `size` phải bằng số nút còn sống và đi tới được từ `head`.

```text
Trước: head --> [A] --> [B] --> NULL
                            ^
                           tail

Xóa B đúng:
  head --> [A] --> NULL
           ^
          tail

Xóa B sai:
  head --> [A] --> NULL
  tail vẫn trỏ vùng B đã free  X
```

Nếu dùng `tail` cũ khi thêm cuối, chương trình có thể ghi qua con trỏ treo. Ngược lại, nếu tách B khỏi chuỗi nhưng quên `free(B)`, B có thể bị rò rỉ. Một thao tác xóa đúng phải **duy trì metadata**, **thu hồi đúng nút** và **công bố điều kiện invalidation**.

### 8.3. Stack và queue: pop không nhất thiết đồng nghĩa hủy payload

Với stack/queue chứa **giá trị số nguyên trực tiếp**, lấy một phần tử có thể chỉ giảm kích thước logic hoặc giải phóng một nút bọc.

Với stack/queue chứa **con trỏ tới đối tượng nghiệp vụ**, cần quy định: container sở hữu đối tượng hay chỉ mượn? Nếu `pop` chỉ lấy phần tử ra và trả con trỏ, đó có thể là **chuyển quyền sở hữu** hoặc **trả tham chiếu mượn** tùy API.

```text
enqueue_owned(Task*) thành công:
  Queue nhận ownership Task.

dequeue_owned() thành công:
  Caller nhận ownership Task.
  Queue không còn quyền free Task này.

clear():
  Chỉ free các Task hiện còn thuộc ownership của Queue.
```

Nếu `dequeue` giải phóng Task trước khi trả con trỏ cho người gọi, con trỏ trả về sẽ treo. Nếu queue bỏ liên kết của một nút bọc mà quên giải phóng nút, sẽ rò rỉ nút. Nếu cả queue và caller cùng free Task, sẽ double free.

### 8.4. Bảng băm: xóa bucket, tombstone và khóa/giá trị còn được giữ

Trong **separate chaining**, bảng băm có thể sở hữu mỗi nút trong chuỗi bucket. Khi xóa một key, phải cập nhật liên kết bucket và thu hồi nút đúng một lần. Nếu key/value bên trong được cấp động, phải xử lý đúng theo chính sách sở hữu của từng trường.

Trong **open addressing**, xóa phần tử có thể để lại **tombstone** để không làm hỏng chuỗi dò. Tombstone là metadata logic, không tự đồng nghĩa “đối tượng giá trị còn sống”; cần phân biệt ô trống, ô đã xóa và ô đang chứa phần tử.

Đối với cache là bảng băm, một bảng lớn có thể hoàn toàn đúng về hash lookup nhưng vẫn giữ nhiều mục đã hết hạn. Cần eviction theo dung lượng/thời gian hoặc một chính sách quản lý rõ ràng.

### 8.5. Cây: hàm free đệ quy chỉ an toàn khi cấu trúc thật là cây sở hữu riêng

Một cây nhị phân không có chia sẻ nút con hoặc chu trình có thể được dọn bằng duyệt hậu tự:

```c
#include <stdlib.h>

typedef struct TreeNode {
    int key;
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

Hàm này có thời gian O(n) với `n` nút, dùng stack đệ quy O(h) với `h` là chiều cao cây. Nó **không phù hợp với đồ thị hoặc cây con dùng chung**: một nút được đi tới nhiều lần có thể bị free lại, còn chu trình có thể gây đệ quy vô hạn. Với cây suy biến chiều cao O(n), còn có nguy cơ quá sâu ngăn xếp.

Với **persistent tree** có structural sharing, nút cũ có thể tiếp tục được phiên bản khác dùng. Không được hủy nút chỉ vì một phiên bản đã bỏ tham chiếu; cơ chế sở hữu phải hỗ trợ thu hồi khi **không còn phiên bản nào cần**.

### 8.6. Heap: xóa phần tử nhưng còn handle ngoài

Binary heap thường lưu phần tử trong mảng và dùng hoán đổi các ô để duy trì tính chất heap. Nếu bên ngoài giữ `pointer` tới một ô hoặc `index` của một phần tử, thao tác sift/hoán đổi có thể làm “vị trí logic của phần tử” thay đổi.

Nếu cần hỗ trợ cập nhật ưu tiên qua handle, có thể dùng ánh xạ `ID -> index`; phải cập nhật ánh xạ cùng mỗi lần hoán đổi. Khi phần tử bị xóa, ID/handle cũ phải bị vô hiệu hóa rõ ràng. Nếu heap chứa con trỏ tới đối tượng do nơi khác sở hữu, xóa một ô heap không đương nhiên được phép hủy đối tượng đích.

### 8.7. Đồ thị: nhiều cạnh cùng trỏ tới một đỉnh

```text
A --edge--> C <--edge-- B
^           |
|           v
+---------  D
```

Nhiều cạnh có thể dẫn tới cùng một đỉnh, và đồ thị có thể có chu trình. Nếu giải phóng đỉnh mỗi khi duyệt thấy một cạnh đi đến nó, chương trình có thể **double free** hoặc dùng lại vùng đã giải phóng.

Một thiết kế điển hình:

- **Graph/vertex store** sở hữu tập đỉnh và quản lý vòng đời của từng đỉnh.
- Các cạnh chứa ID, chỉ số hoặc tham chiếu mượn đến đỉnh; không tự cấp thêm quyền sở hữu mạnh nếu không có chủ đích.
- Xóa đỉnh cần cập nhật mọi cạnh/metadata liên quan theo bất biến.
- Dọn toàn đồ thị thu hồi **mỗi đỉnh đúng một lần**, không phụ thuộc có bao nhiêu đường đi tới đỉnh.

Với đồ thị cấp phát động có O(V) đối tượng đỉnh và O(E) đối tượng cạnh, tổng dung lượng và chi phí cleanup phụ thuộc biểu diễn, thường O(V+E) nếu mỗi đỉnh/cạnh được xét một lần. Nếu dùng CSR, dữ liệu cạnh/độ lệch là các mảng liên tiếp: thay vì free mỗi cạnh, thường cần giải phóng các vùng mảng do container sở hữu.

## 9. Phân biệt bộ nhớ đang sử dụng, bộ nhớ giữ lại và rò rỉ thực tế

Một đồ thị thể hiện **memory leak** cần xét theo **thời gian** và **vòng đời nghiệp vụ**, không chỉ một ảnh chụp lượng RAM cao.

### 9.1. Các chỉ số thường khác nhau

| Chỉ số | Phản ánh | Điều không thể kết luận chỉ từ nó |
| --- | --- | --- |
| Số đối tượng còn sống | Đối tượng runtime cho là còn sống | Không nói tất cả đối tượng còn cần nghiệp vụ |
| Heap đã cấp phát/đã commit | Vùng allocator/GC đang quản lý | Không đồng nghĩa dung lượng leak |
| Resident Set Size (RSS) | Các trang bộ nhớ tiến trình đang thường trú | Không trực tiếp đếm đối tượng sống hoặc leak |
| Tổng byte đã cấp phát trong cả vòng đời | Lượng cấp phát tích lũy | Có thể lớn dù hầu hết đã free |
| Dữ liệu trong cache | Bộ nhớ giữ để tái sử dụng | Có thể là thiết kế hợp lệ nếu cache có giới hạn |

Ví dụ allocator có thể giữ các khối đã `free` trong pool để tái sử dụng, nên RSS không giảm tức thì. GC cũng có thể giữ heap đã mở rộng cho các lần cấp phát tương lai. Vì vậy **RSS không giảm sau free không tự chứng minh leak**.

### 9.2. Kịch bản đo có kiểm soát

Để tìm nguyên nhân bộ nhớ tăng theo mỗi request:

1. Chạy cùng loại workload lặp nhiều lần, với dữ liệu đủ giống nhau.
2. Đo số đối tượng và lượng bộ nhớ *còn sống* sau giai đoạn làm việc, không chỉ tổng số byte đã cấp phát trong quá trình.
3. Nếu dùng GC, phân biệt bộ nhớ có thể thu hồi với bộ nhớ vẫn reachable. Không ép GC liên tục để “chữa” một cache không giới hạn.
4. Chụp snapshot hoặc ghi nhận heap theo nhiều mốc để tìm **kiểu đối tượng tăng liên tục**.
5. Truy từ đối tượng bị giữ về **gốc tham chiếu** (cache, static field, listener, task, closure).
6. Với C/C++, kiểm tra **đường cấp phát**, **đường giải phóng**, trường hợp lỗi và thời điểm con trỏ bị invalidation.
7. Sau khi sửa, chạy lại cùng workload và so sánh **dung lượng ổn định, độ đúng và thời gian chạy**.

Một đồ thị minh họa:

```text
Bộ nhớ
  ^
  |          / / / / /    tăng mãi sau mỗi vòng: cần điều tra
  |         /
  |    ____/________________ mức ổn định: có thể là cache/allocator hợp lệ
  | __/
  +----------------------------------------------------> Thời gian
      khởi động   warm-up      chạy lặp cùng workload
```

Đường cong thực tế có thể dao động và tăng theo bậc thang. Trọng tâm là **có giới hạn dài hạn tương xứng với workload không**, chứ không đòi mọi phép đo tức thời phải giảm sau cleanup.

## 10. Công cụ và kỹ thuật phát hiện lỗi

### 10.1. C/C++: AddressSanitizer và LeakSanitizer

Với compiler hỗ trợ sanitizers, có thể biên dịch **bản kiểm thử** C/C++ với AddressSanitizer (ASan) để giúp phát hiện một số lỗi truy cập bộ nhớ, gồm use-after-free, out-of-bounds và một số dạng use-after-scope (tùy compiler/cờ).

Ví dụ lệnh mang tính tham khảo khi dùng một compiler tương thích:

```bash
# Ví dụ: thay demo.c bằng tệp mã nguồn thực sự của bài thử.
cc -g -O1 -fsanitize=address -fno-omit-frame-pointer demo.c -o demo
./demo
```

LeakSanitizer (LSan) có thể báo những khối chưa thu hồi theo cơ chế của công cụ; khả năng tích hợp với ASan, mức độ hỗ trợ và tùy chọn bật kiểm tra leak phụ thuộc hệ điều hành, compiler và runtime.

**Không chạy ví dụ có lỗi bộ nhớ trong sản phẩm đang phục vụ người dùng chỉ để “xem nó có crash không”.** Dùng bản thử nghiệm/kiểm thử với đầu vào kiểm soát và công cụ phù hợp. Chạy không crash chưa chứng minh mã an toàn; sanitizer cũng không bắt được mọi tình huống.

### 10.2. Công cụ theo dõi cấp phát và heap

- **Valgrind Memcheck** trên các hệ được hỗ trợ có thể giúp nhận diện truy cập sai và những khối còn cấp phát khi kết thúc.
- **Profiler heap** của môi trường C/C++ có thể cho biết đường cấp phát tạo nhiều byte hoặc đối tượng sống.
- **Java heap dump/profiler** có thể hiển thị retained size và chuỗi tham chiếu từ GC roots đến các đối tượng bị giữ.
- **Python `tracemalloc`** theo dõi các cấp phát bộ nhớ do Python quản lý, có thể so sánh snapshot để thấy vị trí tạo cấp phát tăng. Nó không quan sát đầy đủ mọi cấp phát native nằm ngoài cơ chế mà nó theo dõi.

Ví dụ Python minh họa **phân tích snapshot**, không phải phép đo bộ nhớ hệ điều hành:

```python
import tracemalloc

tracemalloc.start()

before = tracemalloc.take_snapshot()

data = [bytearray(10_000) for _ in range(100)]
after = tracemalloc.take_snapshot()

for stat in after.compare_to(before, "lineno")[:5]:
    print(stat)

data.clear()
tracemalloc.stop()
```

Việc `data.clear()` bỏ các tham chiếu từ list không bảo đảm RSS giảm ngay hoặc rằng từng vùng byte đã được hệ điều hành thu hồi. Đây chỉ là cách bắt đầu tìm **nguồn cấp phát**.

### 10.3. Kiểm thử vòng đời thay vì chỉ kiểm thử kết quả tính

Đối với cấu trúc dữ liệu tự cài:

- Kiểm thử **danh sách rỗng**, một nút, nhiều nút, xóa đầu/giữa/cuối và gọi `clear` lặp.
- Kiểm thử **cấp phát thất bại** bằng allocator giả lập hoặc cơ chế injection để xem các nhánh cleanup.
- Kiểm thử **con trỏ mượn bị vô hiệu hóa** sau erase/reallocation theo đúng hợp đồng.
- Với đồ thị, kiểm thử **chu trình**, nhiều cạnh tới cùng đỉnh, xóa đỉnh có nhiều cạnh đến.
- Kiểm thử cache/listener có **giới hạn dung lượng và unsubscribe** khi kết thúc vòng đời.
- Với nhiều luồng, kiểm thử điều kiện tranh chấp, đồng bộ và quy trình thu hồi trong môi trường thích hợp.

**Đừng dereference con trỏ đã hết hiệu lực để kiểm tra “liệu có còn dùng được không”**: đó không phải phép kiểm thử tính an toàn hợp lệ.

## 11. Thiết kế tránh rò rỉ và dangling ngay từ đầu

### 11.1. Quy định chủ sở hữu rõ ràng

Với mỗi vùng cấp phát, cần trả lời:

- Ai tạo, ai chịu trách nhiệm hủy?
- Có được chuyển quyền sở hữu sau khi thêm vào container không?
- Nếu thao tác thất bại, ownership thuộc về ai?
- API nào trả **con trỏ mượn**, và điều kiện invalidation cụ thể là gì?
- Nếu container bị hủy, tài nguyên lồng nhau được giải phóng theo thứ tự nào?

Nếu dùng C thuần, có thể đặt quy ước nhất quán: `create_*` trả đối tượng mới do caller sở hữu, `*_destroy` giải phóng đối tượng sở hữu, `find_*` trả borrowed reference, còn `take_*` biểu diễn chuyển ownership nếu được API định nghĩa như vậy. **Tên chỉ là gợi ý**; hợp đồng phải nói rõ.

### 11.2. C++: ưu tiên RAII và ownership types

Trong C++, dùng `std::vector`, `std::string`, `std::unique_ptr` và những container/quản lý tài nguyên thích hợp thay vì rải các cặp `new/delete` trong nhiều nhánh logic.

```cpp
#include <memory>
#include <vector>

struct Node {
    int value;
};

int main() {
    std::vector<std::unique_ptr<Node>> owned;

    owned.push_back(std::make_unique<Node>(Node{10}));
    owned.push_back(std::make_unique<Node>(Node{20}));

    // Các Node được container sở hữu qua unique_ptr.
    // Khi vector bị hủy, các unique_ptr cũng được hủy và dọn Node.
}
```

Ví dụ này là **mảng các chủ sở hữu duy nhất**, không phải danh sách liên kết. Nó cho thấy quyền sở hữu có thể gắn với một container dù mỗi đối tượng đích được cấp riêng. Nếu một đối tượng được nhiều nơi **sở hữu**, dùng sở hữu chia sẻ khi thật sự cần, đồng thời kiểm tra chu trình.

### 11.3. Weak reference không tự giải quyết mọi retention

Một weak reference không giữ đối tượng sống như strong reference trong các cơ chế hỗ trợ tương ứng. Tuy nhiên:

- Không phải mọi đối tượng đều hỗ trợ weak reference.
- Đối tượng có thể biến mất trước khi bạn dùng, nên phải **kiểm tra và xử lý trường hợp không còn đối tượng**.
- Weak reference không thay thế việc unsubscribe/close khi tài nguyên ngoài hoặc vòng đời nghiệp vụ cần kết thúc chính xác.
- Một cache chỉ lưu weak refs có thể có hành vi bị thu hồi khó dự đoán, ảnh hưởng hiệu năng; nó không luôn phù hợp cho cache cần bảo đảm giữ dữ liệu trong một khoảng.

Với `std::weak_ptr` trong C++, phải `lock()` để thử tạo một `shared_ptr` sống hợp lệ trước khi truy cập. Với Python `weakref` hoặc Java `WeakReference`, cần tuân theo quy tắc và giới hạn của từng runtime.

### 11.4. Giới hạn dung lượng và thời hạn sống theo nhu cầu

Đối với cache, queue và registry, thường nên xác định:

- Số mục tối đa hoặc ngân sách byte.
- Chính sách thay thế (ví dụ LRU) và thời điểm item được bỏ.
- TTL hoặc điều kiện hết hiệu lực khi dữ liệu thay đổi.
- Ai xóa các subscription hoặc callback khi đối tượng bị đóng.
- Việc xóa mục khỏi container có đồng nghĩa giải phóng **đối tượng được tham chiếu** không.

Một cache có `max_entries = 1000` nhưng mỗi entry giữ dữ liệu hàng trăm MB vẫn có thể quá lớn. **Ngân sách byte và workload thực tế** có thể quan trọng hơn chỉ đếm số phần tử.

### 11.5. Khi nhiều luồng cùng truy cập nút có thể bị xóa

Trong cấu trúc đa luồng, mutex có thể bảo vệ cả vòng duyệt và thao tác xóa nếu phạm vi khóa được thiết kế phù hợp. Với thuật toán lock-free, việc một con trỏ đã được đọc không đảm bảo nút còn sống khi sử dụng; có thể cần **hazard pointers**, **epoch-based reclamation** hoặc cơ chế chuyên dụng.

Aliasing, đồng bộ và reclamation là **ba trách nhiệm liên quan nhưng khác nhau**: nhiều luồng nhìn cùng nút, đồng bộ sửa nút, và biết khi nào được thu hồi nút.

## 12. Chi phí thời gian và bộ nhớ của các chiến lược

| Chiến lược | Chi phí chính | Khi phù hợp | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| Giải phóng từng nút khi xóa | O(1) thao tác unlink khi đã có đủ liên kết; `free` phụ thuộc allocator | Danh sách có sở hữu riêng | Borrowed pointer tới nút bị xóa thành dangling |
| Hủy danh sách `n` nút | O(n) thời gian, O(1) bộ nhớ phụ với vòng lặp | Cleanup theo container | Phải duyệt đúng nút, tránh double free/cycle |
| Hủy cây có `n` nút, cao `h` | O(n) thời gian, O(h) stack với đệ quy | Cây sở hữu riêng, không chia sẻ nút | Stack quá sâu; sai nếu có chu trình/shared child |
| Hủy đồ thị bằng kho đỉnh/cạnh | Thường O(V+E) khi thăm/xóa mỗi đỉnh và cạnh một lần | Đồ thị có nhiều cạnh vào và chu trình | Cần quy định chủ sở hữu, đồng bộ liên kết |
| Giữ cache không giới hạn | Mỗi insert có thể rẻ, nhưng bộ nhớ có thể tăng không giới hạn | Thường không phù hợp lâu dài | Retention và áp lực GC |
| Cache giới hạn `k` mục | Dung lượng mục O(k) nếu kích thước từng mục bị chặn | Dữ liệu đọc lại thường xuyên | Eviction làm giảm hit; giá trị mỗi mục vẫn quan trọng |
| Sở hữu duy nhất / RAII | Metadata sở hữu thường đơn giản, cleanup theo scope | Ranh giới sở hữu rõ | Muốn chia sẻ ownership phải chuyển/clone hoặc đổi chiến lược |
| Sở hữu chia sẻ | Chi phí quản lý ownership và metadata | Đối tượng thực sự có nhiều chủ | Chu trình mạnh, retention, đồng bộ trạng thái |
| Handle có generation | Thêm metadata/kiểm tra mỗi truy cập | Pool hay kho đối tượng tái sử dụng slot | Phải xử lý version wrap, slot reuse |
| Snapshot/copy thay vì view | O(n) thời gian/bộ nhớ nếu copy `n` phần tử | Cần dữ liệu độc lập qua vòng đời nguồn | Tăng cấp phát và dung lượng |

Một thao tác có thời gian O(1) khi thêm vào queue không có nghĩa toàn vòng đời của queue O(1): sau `n` lần thêm, cleanup có thể tốn O(n); hoặc nếu queue không có chính sách tiêu thụ/xóa, bộ nhớ có thể tăng O(n).

## 13. Các ngộ nhận cần loại bỏ

**“Con trỏ khác `NULL` chắc chắn hợp lệ.”** Sai: đối tượng có thể đã hết vòng đời hoặc vùng đã được cấp lại cho mục đích khác.

**“Đặt con trỏ thành `NULL` sau `free` sửa mọi bí danh.”** Sai: chỉ biến được gán lại thành `NULL`, các bản sao con trỏ khác không tự thay đổi.

**“Không crash nghĩa là không có use-after-free.”** Sai: truy cập vùng đã giải phóng có thể tình cờ cho kết quả có vẻ đúng trước khi gây lỗi; hành vi không đáng tin.

**“Bộ nhớ RSS không giảm sau `free` là do leak.”** Không thể kết luận như vậy: allocator có thể giữ vùng đã giải phóng để tái sử dụng.

**“Có GC thì không bị memory leak.”** Sai: cache không giới hạn, listener và closure vẫn có thể giữ object có thể tới được sau khi nghiệp vụ kết thúc.

**“Chu trình đối tượng luôn không được GC thu hồi.”** Không đúng với mọi GC: một chu trình không còn reachable từ root có thể được collector hỗ trợ thu hồi; riêng chu trình sở hữu mạnh bằng reference counting đơn thuần có thể giữ các đối tượng sống.

**“Khi xóa mục khỏi container, đối tượng đích luôn bị hủy.”** Sai: còn tùy container sở hữu giá trị hay chỉ lưu tham chiếu, và có nơi khác đang sở hữu đối tượng hay không.

**“Có thể kiểm tra con trỏ cũ bằng cách thử dereference.”** Không. Hãy dựa vào hợp đồng vòng đời, handle hợp lệ, hoặc công cụ kiểm thử có giám sát thay vì chủ động gây truy cập sai.

## 14. Quy trình chẩn đoán một trường hợp cụ thể

Đối với bất kỳ nghi vấn dangling/leak/retention nào, trả lời theo thứ tự:

1. **Xác định đối tượng:** nút, mảng, bucket, tài nguyên ngoài hay payload được tham chiếu?
2. **Xác định cơ chế tạo/hủy:** `malloc/free`, RAII, GC, arena, pool hay close/dispose?
3. **Vẽ các đường truy cập và chủ sở hữu:** ai mượn, ai sở hữu, ai có quyền sửa hoặc thu hồi?
4. **Đánh dấu thời điểm thay đổi:** erase, realloc, xóa container, unregister listener, kết thúc task, thay snapshot.
5. **Kiểm tra vòng đời:** đường truy cập nào còn tồn tại sau khi đối tượng đích bị hủy?
6. **Kiểm tra reachability:** đối tượng đã hết nghiệp vụ có còn bị giữ qua cache, global, thread, callback hoặc closure?
7. **Kiểm tra bất biến:** danh sách `size/tail`, cây cha–con, các cạnh đồ thị, tombstone/bucket hash, ánh xạ handle–slot có nhất quán không?
8. **Tính chi phí:** cleanup bao nhiêu nút, cấu trúc giữ bao nhiêu mục, bộ nhớ có bị tăng mãi theo workload không?
9. **Dùng công cụ phù hợp để xác minh:** sanitizer/profiler, heap snapshot, logging ownership và kiểm thử nhánh lỗi.
10. **Sửa nguyên nhân ở hợp đồng và thiết kế**, không chỉ làm crash biến mất hoặc ép GC chạy nhiều hơn.

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1. Dangling sau `free`

```c
int *p = malloc(sizeof *p);
/* Giả sử malloc thành công. */
int *q = p;
*p = 5;
free(p);
p = NULL;
```

**Câu hỏi:** `q` còn hợp lệ để đọc `*q` không? `p = NULL` có giúp `q` tự thành null không?

**Lời giải:** Không. `q` là con trỏ treo sau khi vùng đích đã được giải phóng. `p = NULL` chỉ thay biến `p`; không sửa `q`. Không được dereference hoặc `free(q)` lần nữa cho vùng cũ.

### Bài 2. Mất con trỏ do `realloc`

Một hàm viết `p = realloc(p, new_size)` với `new_size > 0`. Nếu `realloc` thất bại, tại sao có thể rò rỉ?

**Lời giải:** Khi thất bại, `realloc` trả `NULL` nhưng vùng cũ vẫn được cấp; gán trực tiếp làm mất giá trị con trỏ cũ. Dùng `candidate = realloc(p, new_size)`, kiểm tra kết quả trước khi cập nhật `p`.

### Bài 3. Xóa đầu danh sách sai thứ tự

```c
/* Sai: giả sử head khác NULL. */
free(head);
head = head->next;
```

**Lời giải:** Biểu thức `head->next` truy cập nút đã free. Phải lưu `next` trước, rồi cập nhật `head` và `free` nút cũ. Nếu container có `size`/`tail`, phải cập nhật bất biến tương ứng.

### Bài 4. RSS cao sau `free`

Một chương trình C giải phóng toàn bộ vùng cấp nhưng RSS vẫn cao. Có thể kết luận leak không?

**Lời giải:** Không. Allocator có thể giữ các vùng đã free trong pool/page để dùng lại. Cần đo số khối còn cấp, kiểm tra leak report và theo dõi dung lượng dưới workload lặp thay vì chỉ một mốc RSS.

### Bài 5. Python giữ lịch sử báo cáo

```python
history = []
for i in range(1_000):
    history.append(bytearray(100_000))
```

**Lời giải:** `history` giữ 1.000 tham chiếu mạnh tới các `bytearray`, vì vậy các đối tượng còn reachable. Nếu chỉ cần mười báo cáo gần đây, dùng container giới hạn như `deque(maxlen=10)` hoặc chính sách eviction. Không cần suy ra `bytearray` đã bị rò rỉ theo nghĩa `malloc` của C.

### Bài 6. Listener giữ đối tượng đã đóng

Một registry tồn tại suốt ứng dụng vẫn giữ callback do màn hình đăng ký; callback capture một view-model có mảng dữ liệu lớn. Màn hình đóng nhưng heap vẫn giữ mảng. Cần tìm đường tham chiếu nào?

**Lời giải:** `registry -> callback -> captured view-model -> array`. Cần unsubscribe/dispose callback theo vòng đời màn hình hoặc đổi thiết kế sở hữu. Việc chỉ đặt một biến màn hình thành `null` không đủ nếu registry vẫn giữ đường tới callback.

### Bài 7. Chu trình `shared_ptr`

Hai node A và B giữ nhau bằng `shared_ptr`, bên ngoài không còn owner. Tại sao destructor có thể không chạy?

**Lời giải:** Hai liên kết mạnh giữ số chủ sở hữu khác 0. Nếu quan hệ không đòi hỏi ownership ở cả hai chiều, dùng `weak_ptr` cho chiều không sở hữu hoặc một container trung tâm sở hữu tất cả node và cạnh chỉ mượn.

### Bài 8. Hủy cây có cùng nút con

Hai nhánh của cây cùng trỏ tới nút C và một hàm hủy đệ quy gọi `free_tree(left)` rồi `free_tree(right)`. Có an toàn không?

**Lời giải:** Không với đồ thị dùng chung nút: nhánh đầu có thể hủy C, nhánh kia lại đi vào C đã hủy. Phải có chính sách chia sẻ hoặc kho sở hữu các nút, giải phóng mỗi nút đúng một lần.

### Bài 9. Stable pointer của linked list

Một iterator trỏ tới nút N trong danh sách liên kết. Nếu chỉ thêm nút mới ở nơi khác, iterator có thể vẫn hợp lệ. Nếu xóa chính N thì sao?

**Lời giải:** Iterator tới N mất hiệu lực khi N bị xóa; không được truy cập lại vùng N. Tính ổn định của nút khác khi chèn không bảo vệ một nút đã bị hủy.

### Bài 10. Cache tối đa 100 mục nhưng vẫn chiếm rất nhiều RAM

Một cache giữ tối đa 100 mục, nhưng mỗi mục có thể giữ mảng 1 GiB. Giới hạn số mục có đủ không?

**Lời giải:** Chưa đủ. Bộ nhớ có thể lên tới quy mô hàng trăm GiB cho payload nếu dữ liệu thực như vậy và môi trường cho phép. Cần ngân sách byte, giới hạn kích thước mục, eviction và kiểm tra các đối tượng con bị giữ gián tiếp.

### Bài 11. Generational handle

Handle cũ `(slot=7, generation=4)` còn được giữ; slot 7 đã bị giải phóng và tái sử dụng với generation 5. Có thể dùng handle cũ không?

**Lời giải:** Không; kiểm tra generation phát hiện handle cũ không khớp. Cần bảo đảm thiết kế xử lý tăng generation và trường hợp tràn/quay vòng theo quy tắc hệ thống.

### Bài 12. Chi phí dọn một đồ thị

Đồ thị lưu `V` đỉnh và `E` cạnh dưới một kho sở hữu trung tâm; mỗi đỉnh và cạnh được thu hồi đúng một lần. Độ phức tạp cleanup phù hợp là bao nhiêu?

**Lời giải:** Thường O(V+E) thời gian nếu thuật toán duyệt/giải phóng từng đỉnh và cạnh một lần. Không được giải phóng đỉnh theo mỗi cạnh đi đến vì có thể gặp lại một đỉnh, đặc biệt khi có nhiều cạnh vào hoặc chu trình.

## 16. Ghi nhớ

- **Tham chiếu treo**: đường truy cập còn nhưng đối tượng đã hết vòng đời. **Rò rỉ thủ công**: khối cấp phát không được thu hồi theo hợp đồng. **Giữ tham chiếu không cần thiết**: đối tượng vẫn reachable từ gốc sống dù đã hết nhu cầu nghiệp vụ.
- **Bảo vệ vòng đời bằng hợp đồng sở hữu và invalidation**: biết ai tạo, ai giải phóng, khi nào borrower phải ngừng sử dụng, và thao tác nào làm mất hiệu lực con trỏ/iterator.
- **Rò rỉ có thể xảy ra dù có GC**: cache, listener, static field, task hoặc closure giữ đối tượng lâu hơn dự kiến. Dùng eviction, unsubscribe và chính sách vòng đời rõ ràng.
- **Cấu trúc dữ liệu phải giữ cả bất biến liên kết lẫn bất biến bộ nhớ**: xóa nút danh sách đúng thứ tự, không duyệt/free lại nút chung trong cây/đồ thị, không sử dụng handle cũ sau khi slot được tái sử dụng.
- **Đo và kiểm chứng thay vì đoán**: dùng sanitizer, heap profiler, snapshot và workload lặp; tách số đối tượng sống, dung lượng cấp phát và RSS.
- **Chọn cấu trúc theo cả vòng đời**: thời gian thao tác, chi phí dọn, bộ nhớ giữ lại, độ ổn định của đường tham chiếu và nhu cầu chia sẻ quyết định lựa chọn tối ưu cho bài toán thực.
