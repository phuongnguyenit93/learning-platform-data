# Danh sách nội tại (intrusive list) và quyền sở hữu nút

## 1. Khi đối tượng tự mang các liên kết của danh sách

Trong một danh sách liên kết thông thường, ta thường hình dung một **nút** chứa dữ liệu cùng con trỏ đến nút tiếp theo:

```text
head
  |
  v
[data | next] --> [data | next] --> [data | null]
```

Tuy nhiên, nếu chương trình đã có các đối tượng `Task` (công việc), `Connection` (kết nối) hoặc `Process` (tiến trình), việc cấp phát thêm một nút bao riêng cho mỗi đối tượng không phải lúc nào cũng cần thiết.

**Danh sách nội tại** (*intrusive linked list*) đặt trường liên kết — thường gọi là **hook** — **ngay bên trong đối tượng**. Danh sách kết nối các hook ấy thay vì cấp phát nút bọc dữ liệu độc lập.

Ví dụ với hệ thống điều phối tác vụ:

```text
Các đối tượng Task do hệ thống quản lý:

Task 101                              Task 102
┌─────────────────────────┐            ┌─────────────────────────┐
│ id = 101                │            │ id = 102                │
│ priority = 2            │            │ priority = 1            │
│ ready_hook: prev / next │ <--------> │ ready_hook: prev / next │
└─────────────────────────┘            └─────────────────────────┘

Danh sách "ready" chỉ cần một đầu danh sách;
không bắt buộc tạo thêm một node bọc Task 101, Task 102.
```

Điều quan trọng nhất: **một đối tượng thuộc danh sách không tự động có nghĩa danh sách sở hữu đối tượng đó**. Nối hook, tháo hook và cấp phát/giải phóng đối tượng là những trách nhiệm cần được thiết kế rõ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt danh sách **nội tại** (*intrusive*) với danh sách **không nội tại** (*non-intrusive*).
- Hiểu vị trí của hook, nút canh gác (*sentinel*) và các bất biến liên kết.
- Giải thích sự khác nhau giữa **membership** (thuộc danh sách) và **ownership** (sở hữu vòng đời/bộ nhớ).
- Cài thao tác nối, tháo, duyệt danh sách liên kết đôi vòng và phục hồi đối tượng từ hook.
- Xác định điều kiện để thao tác `O(1)` thực sự đúng.
- Phòng tránh con trỏ treo, giải phóng sớm, thêm một hook hai lần, sao chép hoặc di chuyển đối tượng khi đang liên kết.
- Chọn danh sách nội tại khi đánh đổi giữa hiệu năng, chi phí bộ nhớ và tính dễ bảo trì phù hợp với ứng dụng.

Đây là nội dung thuộc chương **Danh sách liên kết** của học phần **Cấu trúc dữ liệu**. Cùng với mảng, stack, queue, bảng băm, cây, heap và đồ thị, chúng ta sử dụng bất biến, phép thao tác và độ phức tạp thời gian/bộ nhớ để chọn cấu trúc dữ liệu thích hợp.

## 2. Danh sách không nội tại và nội tại khác nhau thế nào?

### 2.1. Non-intrusive list: nút bọc đối tượng

Một cách cài đặt danh sách liên kết đôi không nội tại có thể là:

```c
typedef struct Task {
    int id;
    int priority;
} Task;

typedef struct Node {
    struct Node *prev;
    struct Node *next;
    Task *value;
} Node;
```

Ở đây, `Node` chứa con trỏ `value` tới `Task`. Có thể hình dung:

```text
Danh sách:
  [prev | value* | next] <--> [prev | value* | next]
           |                          |
           v                          v
        Task 101                   Task 102
```

Nút danh sách và đối tượng `Task` là **hai thực thể khác nhau**. Chương trình có thể cấp phát nút lúc chèn, giải phóng nút khi xóa, trong khi `Task` tồn tại lâu hơn. Tuy nhiên, đây chỉ là **một** cách cài đặt: các container như `std::list<Task>` trong C++ có thể lưu trực tiếp giá trị `Task` trong nút do container sở hữu, chứ không nhất thiết có con trỏ `Task*` rời.

### 2.2. Intrusive list: liên kết là thành viên của đối tượng

```c
typedef struct Link {
    struct Link *prev;
    struct Link *next;
} Link;

typedef struct Task {
    int id;
    int priority;
    Link ready_hook;
} Task;
```

Danh sách nối `Task.ready_hook`:

```text
Đầu danh sách
     |
     v
 [Task 101: ready_hook] <--> [Task 102: ready_hook]

Không cần một Node độc lập lưu Task* cho từng phần tử.
```

Vì hook là một phần của đối tượng `Task`, từ con trỏ đến hook có thể xác định đối tượng chứa nó bằng cơ chế phù hợp với kiểu dữ liệu và cách bố trí bộ nhớ.

| Tiêu chí | Danh sách không nội tại | Danh sách nội tại |
|---|---|---|
| Vị trí con trỏ liên kết | Trong nút bao riêng hoặc nút do container quản lý | Nằm bên trong chính đối tượng được liên kết |
| Chi phí cấp phát nút khi chèn | Có thể cần cấp phát nút mới | Thường không cần cấp phát **nút danh sách riêng** |
| Quan hệ với dữ liệu | Nút có thể chứa giá trị hoặc con trỏ dữ liệu | Đối tượng phải cung cấp hook đúng kiểu |
| Quyền sở hữu | Do API quyết định; container thường quản lý nút của nó | Danh sách intrusive điển hình **không sở hữu đối tượng** |
| Xóa khỏi danh sách | Thường hủy nút bao; xử lý payload tùy chính sách | Chủ yếu cập nhật các liên kết trong đối tượng |
| Một đối tượng tham gia nhiều danh sách | Có thể có nhiều nút bao tham chiếu tới cùng đối tượng | Cần nhiều hook độc lập, hoặc cơ chế khác |
| Tính đóng gói | Đối tượng không nhất thiết biết về danh sách | Kiểu đối tượng phải mang thông tin liên kết |
| Độ phức tạp duy trì vòng đời | Thường do container hỗ trợ nhiều hơn | Người dùng phải xác định rõ owner và lúc unlink |

Không phải mọi danh sách nội tại đều dùng liên kết đôi: nó có thể có một hook `next` cho danh sách liên kết đơn. Bài này tập trung vào **danh sách liên kết đôi vòng có sentinel**, một thiết kế thường dùng trong hệ thống cấp thấp.

## 3. Hai khái niệm độc lập: membership và ownership

**Membership** trả lời: “Đối tượng đang nằm trong danh sách nào?”. **Ownership** trả lời: “Thành phần nào chịu trách nhiệm giữ đối tượng tồn tại và giải phóng tài nguyên của nó?”.

Giả sử một hệ thống có:

- `TaskRegistry`: tạo, lưu và giải phóng các đối tượng `Task`.
- `ReadyQueue`: liên kết những tác vụ đang chờ chạy.
- `TimeoutQueue`: liên kết các tác vụ đang chờ đến hạn.

```text
                  SỞ HỮU VÒNG ĐỜI
                     TaskRegistry
                    /     |      \
                   v      v       v
                Task A  Task B  Task C
                   |       |       |
               ready_hook  |   timeout_hook
                   |       |       |
                   v       v       v
             ReadyQueue  ...   TimeoutQueue
                  CHỈ QUẢN LÝ THÀNH VIÊN
```

Trong thiết kế này, `ReadyQueue` không được tự ý `free(Task A)` chỉ vì vừa tháo `Task A` khỏi hàng đợi. Ngược lại, `TaskRegistry` không được hủy `Task A` khi hook của nó còn liên kết trong một danh sách đang được sử dụng.

Một hợp đồng vòng đời an toàn có thể phát biểu:

1. **Owner** cấp phát và kiểm soát thời hạn sống của đối tượng.
2. Mỗi danh sách quản lý quan hệ **thuộc danh sách**, thông qua một hook cụ thể.
3. Trước khi hủy đối tượng, phải tháo **mọi hook đang liên kết**, hoặc sử dụng cơ chế tự tháo có bảo đảm tương đương.
4. Một danh sách không được duyệt tới một hook của đối tượng đã bị hủy.
5. Nếu có nhiều thành phần cùng cần giữ đối tượng tồn tại, phải áp dụng cơ chế sở hữu chung hoặc một hợp đồng vòng đời khác rõ ràng.

**Intrusive không có nghĩa “luôn không sở hữu” về mọi thiết kế có thể có.** Một container hoặc hệ thống có thể bổ sung chính sách hủy đối tượng. Tuy nhiên, **các thao tác nối/tháo hook thông thường không tự tạo quyền sở hữu bộ nhớ**, nên không được suy ra việc tự động giải phóng từ tên cấu trúc.

### Một phép xóa cần được hiểu chính xác

Khi gọi `unlink(task.ready_hook)`:

- Đối tượng không còn là thành viên của danh sách đó.
- Các đối tượng đứng trước/sau được nối lại.
- Vùng nhớ của `task` vẫn tồn tại nếu owner chưa hủy nó.
- Những hook khác của `task` (nếu có) không nhất thiết bị thay đổi.

Khi gọi `destroy(task)` hoặc `free(task)`, điều kiện an toàn lại khác: **không còn danh sách hay người dùng nào được phép truy cập đến vùng nhớ đó**.

## 4. Bất biến của danh sách liên kết đôi vòng có sentinel

Nhiều triển khai intrusive list dùng một **nút canh gác** (*sentinel/head*) có cùng kiểu `Link` như hook. Sentinel là đầu danh sách, nhưng **không phải đối tượng dữ liệu**.

### Danh sách rỗng

```text
             +-----------+
             |           |
             v           |
          [ HEAD ] -------+
          HEAD.next = &HEAD
          HEAD.prev = &HEAD
```

Với danh sách rỗng, hai con trỏ của sentinel đều trỏ về chính nó. Không cần `NULL` ở đầu/cuối danh sách.

### Danh sách có ba phần tử

```text
   HEAD <--> A.hook <--> B.hook <--> C.hook
     ^                                  |
     +----------------------------------+
```

Nếu `x` là bất kỳ nút liên kết hợp lệ nào, kể cả sentinel:

\[
x.next.prev=x,\qquad x.prev.next=x.
\]

Các bất biến cần giữ:

1. Sentinel luôn tồn tại và thuộc đúng danh sách trong suốt thời gian danh sách hoạt động.
2. Với danh sách rỗng: `head.next == head` và `head.prev == head`.
3. Với danh sách không rỗng: `head.next` là hook đầu; `head.prev` là hook cuối.
4. Mỗi hook đang liên kết có `next` và `prev` hợp lệ, hai hướng nhất quán.
5. Một hook không được **đồng thời** thuộc hai danh sách hoặc xuất hiện hai lần trong cùng danh sách.
6. Mọi đối tượng chứa hook đang liên kết phải còn sống và có địa chỉ bộ nhớ ổn định.

### Trạng thái “đã tháo” cũng cần một quy ước

Ta sẽ sử dụng **quy ước cục bộ**: một hook chưa thuộc danh sách có `prev = NULL` và `next = NULL`. Đây không phải quy ước phổ quát — một số thư viện dùng con trỏ tự trỏ, giá trị đánh dấu khác hoặc chế độ quản lý link chuyên dụng.

```text
Hook độc lập:      prev = NULL, next = NULL
Hook đã nối:       prev != NULL, next != NULL
Sentinel rỗng:     prev = &head, next = &head
```

Trong ví dụ bên dưới, sentinel **không bao giờ được đưa qua hàm tháo một hook dữ liệu**. Nếu hủy sentinel như một phần tử thông thường, toàn bộ danh sách có thể bị hỏng.

## 5. Nối và tháo hook: thứ tự cập nhật con trỏ

### 5.1. Chèn hook trước một vị trí đã biết

Giả sử có hai liên kết kề nhau `before <-> pos` và muốn chèn `node` vào giữa:

```text
Trước:
    before <-------------> pos

Sau:
    before <---> node <---> pos
```

Các thao tác cập nhật trong danh sách liên kết đôi:

```text
node.prev   = pos.prev
node.next   = pos
pos.prev.next = node
pos.prev    = node
```

Các phép gán là hữu hạn, không phụ thuộc số nút đang có; chèn vào vị trí **đã biết** vì vậy là **O(1)**, nếu hợp đồng về trạng thái hook được đáp ứng.

Để thêm cuối danh sách vòng, chèn hook **ngay trước sentinel**.

### 5.2. Tháo một hook đã biết

Giả sử `node` có nút trước là `before` và nút sau là `after`:

```text
Trước:
    before <---> node <---> after

Sau:
    before <-------------> after
    node.prev = node.next = NULL  (quy ước cục bộ)
```

Phép tháo chỉ cần:

```text
node.prev.next = node.next
node.next.prev = node.prev
node.prev = NULL
node.next = NULL
```

Khi đã có con trỏ tới đúng hook, đây cũng là **O(1)**. Lưu ý: **tháo hook không phải giải phóng đối tượng**.

### 5.3. Điều kiện để được gọi O(1)

Phát biểu “chèn/xóa danh sách liên kết O(1)” chỉ đúng nếu **đã có con trỏ đến nút hoặc vị trí liên kết cần sửa**. Nếu phải tìm một nút theo khóa trong danh sách chưa có chỉ mục, bước tìm thường mất **O(n)**. Nếu cần xác định nút thứ `i` bằng cách đi qua liên kết từ đầu, thời gian cũng có thể là **O(n)**.

Nếu danh sách đồng thời phải duy trì tổng số nút `size`, việc cộng/trừ bộ đếm là `O(1)`. Nhưng nếu không lưu bộ đếm, muốn tính số phần tử thường phải đi qua mọi hook: **O(n)**.

## 6. Cài đặt đầy đủ bằng C: sentinel, hook nhúng và duyệt

Ví dụ dưới đây dùng C, danh sách liên kết đôi vòng và các đối tượng `Task` được tạo trên stack. Đối tượng chỉ chứa hook; danh sách **không cấp phát, không sở hữu, không `free` Task**. Code minh họa một cách triển khai thông dụng, không phải API tiêu chuẩn của mọi thư viện intrusive list.

```c
#include <assert.h>
#include <stddef.h>  /* offsetof */
#include <stdio.h>

typedef struct Link {
    struct Link *prev;
    struct Link *next;
} Link;

typedef struct Task {
    int id;
    int priority;
    Link ready_hook;       /* Nút liên kết nhúng trong Task */
} Task;

/* Khởi tạo sentinel của danh sách rỗng. */
static void list_init(Link *head) {
    head->prev = head;
    head->next = head;
}

/* Quy ước: hook đã tháo có hai con trỏ NULL. */
static void hook_init(Link *hook) {
    hook->prev = NULL;
    hook->next = NULL;
}

static int hook_is_detached(const Link *hook) {
    return hook->prev == NULL && hook->next == NULL;
}

static int list_empty(const Link *head) {
    return head->next == head;
}

/* Chèn hook chưa thuộc danh sách trước pos đã liên kết.
   pos có thể là sentinel; hook KHÔNG được là sentinel. */
static void list_insert_before(Link *pos, Link *hook) {
    assert(hook_is_detached(hook));
    assert(pos->prev != NULL && pos->next != NULL);

    Link *before = pos->prev;
    hook->prev = before;
    hook->next = pos;
    before->next = hook;
    pos->prev = hook;
}

/* Thêm cuối: ngay trước sentinel. */
static void list_push_back(Link *head, Link *hook) {
    list_insert_before(head, hook);
}

/* Tháo hook dữ liệu đang liên kết, KHÔNG tháo sentinel.
   Không giải phóng đối tượng chứa hook. */
static void list_remove(Link *hook) {
    assert(hook->prev != NULL && hook->next != NULL);

    Link *before = hook->prev;
    Link *after  = hook->next;
    before->next = after;
    after->prev  = before;

    hook_init(hook);
}

/* Chỉ dùng khi link trỏ đúng thành viên ready_hook
   của một đối tượng Task còn sống. */
static Task *task_from_ready_link(Link *link) {
    return (Task *)((char *)link - offsetof(Task, ready_hook));
}

static void print_ready(const Link *head) {
    for (const Link *it = head->next; it != head; it = it->next) {
        const Task *task = (const Task *)(
            (const char *)it - offsetof(Task, ready_hook)
        );
        printf("%d ", task->id);
    }
    putchar('\n');
}

int main(void) {
    Link ready;
    list_init(&ready);
    assert(list_empty(&ready));

    Task a = {.id = 101, .priority = 2};
    Task b = {.id = 102, .priority = 1};
    Task c = {.id = 103, .priority = 3};

    hook_init(&a.ready_hook);
    hook_init(&b.ready_hook);
    hook_init(&c.ready_hook);

    list_push_back(&ready, &a.ready_hook);
    list_push_back(&ready, &b.ready_hook);
    list_push_back(&ready, &c.ready_hook);
    print_ready(&ready);  /* 101 102 103 */

    /* Từ hook lấy được con trỏ về Task chứa nó. */
    Task *first = task_from_ready_link(ready.next);
    assert(first == &a);

    list_remove(&b.ready_hook);
    print_ready(&ready);  /* 101 103 */
    assert(hook_is_detached(&b.ready_hook));

    /* Tháo mọi hook trước khi các Task trên stack hết sống. */
    list_remove(&a.ready_hook);
    list_remove(&c.ready_hook);
    assert(list_empty(&ready));
    return 0;
}
```

### Đọc mã theo các bất biến

- `list_init` tạo danh sách rỗng với hai liên kết tự trỏ của sentinel.
- `hook_init` đánh dấu một hook chưa thuộc danh sách bằng `NULL` ở cả hai chiều.
- `list_push_back` chèn hook dữ liệu trước sentinel nên duy trì thứ tự `101, 102, 103`.
- `list_remove` nối hai láng giềng, rồi đưa hook về trạng thái tách rời.
- `task_from_ready_link` nhận hook `ready_hook`, xác định đối tượng `Task` chứa trường đó.
- Trước khi thoát hàm, các hook còn liên kết được tháo; biến trên stack không còn bị danh sách tham chiếu khi chúng hết thời hạn sống.

Các lệnh `assert` giúp phát hiện vi phạm tiền điều kiện khi chạy bản debug. **Không được xem chúng là cơ chế bảo vệ đầy đủ trong bản phát hành**, vì `assert` có thể bị vô hiệu hóa khi định nghĩa `NDEBUG`. Mã sản xuất phải có cách quản lý trạng thái, tiền điều kiện và vòng đời phù hợp với thiết kế tổng thể.

### Phục hồi đối tượng qua offsetof

Với một `struct` phù hợp trong C, `offsetof(Task, ready_hook)` cho biết số byte từ đầu `Task` đến trường hook. Công thức thông dụng:

\[
\operatorname{addr}(Task)
=\operatorname{addr}(Task.ready\_hook)
-offsetof(Task,ready\_hook).
\]

Trong các hệ thống C cấp thấp, ý tưởng này thường xuất hiện qua macro `container_of`. Nhưng phép chuyển chỉ hợp lệ theo **hợp đồng bố trí và kiểu dữ liệu**: con trỏ phải thực sự trỏ tới **trường đúng của một đối tượng còn sống**, không phải tới sentinel hoặc một `Link` không thuộc `Task`. Trộn `ready_hook` với một hook khác, hoặc đoán sai kiểu chứa, có thể gây truy cập sai bộ nhớ.

Trong C++, nếu tự dùng `offsetof`, cần lưu ý các hạn chế về kiểu đối tượng và bố trí (đặc biệt với kiểu không có *standard-layout*). Thư viện intrusive chuyên dụng thường cung cấp cơ chế khôi phục giá trị và hợp đồng kiểu để tránh tự viết phép trừ byte tùy tiện.

## 7. Duyệt và xóa nút trong cùng một vòng lặp

Một lỗi phổ biến là tháo hook **rồi mới đọc `hook->next`** để đi tới nút kế tiếp:

```c
/* SAI với quy ước list_remove đặt next thành NULL. */
for (Link *it = ready.next; it != &ready; it = it->next) {
    if (should_remove(task_from_ready_link(it))) {
        list_remove(it);
    }
}
```

Sau `list_remove(it)`, `it->next` đã thành `NULL`; vòng lặp có thể truy cập con trỏ không hợp lệ. Nếu đối tượng bị hủy ngay sau khi tháo, `it` còn có thể trở thành con trỏ treo.

**Cách đúng:** lưu nút kế tiếp **trước khi tháo nút hiện tại**.

```c
for (Link *it = ready.next; it != &ready; ) {
    Link *next = it->next;
    Task *task = task_from_ready_link(it);
    if (should_remove(task)) {
        list_remove(it);
        /* Chỉ owner mới được quyết định hủy task nếu cần. */
    }
    it = next;
}
```

Ví dụ là đoạn mã minh họa cần định nghĩa `ready` và `should_remove` trong chương trình bao quanh. Thao tác lưu `next` là an toàn **khi không có tác nhân khác đồng thời xóa hoặc hủy nút kế tiếp**. Nếu danh sách được sửa từ nhiều luồng, phải có khóa hoặc giao thức đồng bộ riêng.

Khi cần giải phóng động đối tượng hiện tại, trình tự nên là:

1. Lưu liên kết hoặc con trỏ tiếp theo hợp lệ.
2. Tháo hook của đối tượng khỏi danh sách hiện tại.
3. Bảo đảm các hook, chỉ mục và người dùng khác không còn tham chiếu đến đối tượng theo cách không an toàn.
4. Chỉ **owner** hoặc thành phần được ủy quyền mới hủy đối tượng.
5. Tiếp tục từ liên kết kế tiếp đã lưu, miễn là liên kết ấy vẫn còn sống.

Không nên thêm một dòng `free(task)` vào ví dụ trên nếu `task` vốn được cấp phát trên stack, còn được dùng ở nơi khác, hoặc có hook chưa được tháo khỏi các danh sách khác.

## 8. Một đối tượng có thể thuộc nhiều danh sách không?

**Có, nếu mỗi quan hệ thành viên có một hook riêng biệt.** Ví dụ một tác vụ vừa nằm trong danh sách tác vụ đang sẵn sàng, vừa nằm trong danh sách theo dõi thời hạn:

```c
typedef struct Task {
    int id;
    Link ready_hook;
    Link timeout_hook;
} Task;
```

```text
ReadyQueue:    A.ready_hook <--> B.ready_hook
TimeoutQueue:  A.timeout_hook <--> C.timeout_hook

Đối tượng A giống nhau, nhưng hai liên kết là hai trường khác nhau.
```

Đối tượng `A` vẫn chỉ là **một đối tượng**. Nó có thể mang **hai quan hệ thành viên độc lập**, mỗi quan hệ có liên kết riêng.

Tuy nhiên:

- `A.ready_hook` không thể xuất hiện đồng thời trong hai danh sách intrusive độc lập theo hợp đồng này.
- `A.ready_hook` cũng không thể được chèn **hai lần** vào cùng một danh sách.
- Phải tháo **cả** `A.ready_hook` và `A.timeout_hook` (nếu đang liên kết) trước khi hủy `A`.
- Hàm khôi phục `Task` từ hook phải trừ **đúng offset của trường đang dùng**:

```c
Task *from_ready(Link *link) {
    return (Task *)((char *)link - offsetof(Task, ready_hook));
}

Task *from_timeout(Link *link) {
    return (Task *)((char *)link - offsetof(Task, timeout_hook));
}
```

Hai hàm này là mã minh họa phụ thuộc vào định nghĩa `Task` và `Link` phù hợp; việc dùng sai hàm cho loại hook khác là một lỗi nghiêm trọng.

### Vì sao không chèn cùng một hook hai lần?

Giả sử `A.ready_hook` đã nối trong `ReadyQueue`. Các trường `prev` và `next` đang trỏ đến láng giềng trong danh sách đó. Nếu dùng chính hai trường này để nối `A.ready_hook` sang `TimeoutQueue` **mà không tháo trước**, ta sẽ ghi đè thông tin cần để duy trì `ReadyQueue`, dẫn đến đứt hoặc hỏng liên kết.

Một hook là một **vị trí liên kết cụ thể**, không phải một tham chiếu có thể nhân bản tùy ý.

## 9. Vòng đời và tính ổn định địa chỉ: rủi ro lớn nhất

Danh sách nội tại giữ những con trỏ **trỏ vào bên trong đối tượng**. Vì vậy, đối tượng phải còn sống và vị trí bộ nhớ của hook phải ổn định khi đang liên kết.

### 9.1. Giải phóng đối tượng khi hook còn liên kết

```text
HEAD <--> A.hook <--> B.hook <--> HEAD
                         |
                       free(B)   (SAI nếu chưa unlink)

HEAD vẫn giữ con trỏ tới vùng nhớ đã giải phóng.
```

Sau khi owner hủy `B`, danh sách vẫn có thể giữ con trỏ tới `B.hook`. Lần duyệt tiếp theo có nguy cơ **use-after-free** — dùng vùng nhớ sau khi đã giải phóng. Không thể sửa bằng cách “chỉ bỏ qua B”, vì để bỏ qua B có thể đã phải đọc liên kết trong B.

**Nguyên tắc:** phải bảo đảm hook đã được tháo (hoặc tự tháo an toàn theo cơ chế thư viện) trước khi đối tượng bị hủy.

### 9.2. Sao chép hoặc di chuyển đối tượng đang liên kết

Giả sử ta thực hiện sao chép byte một `Task` đã liên kết:

```text
Trước:  HEAD <--> A.hook <--> B.hook <--> HEAD

Copy B sang C bằng memcpy:
        C.hook.prev, C.hook.next giữ con trỏ của B
        nhưng láng giềng vẫn trỏ tới B.hook, không phải C.hook.
```

Đối tượng `C` có các liên kết **giống giá trị con trỏ** của `B`, nhưng không được nối đúng vào danh sách. Nếu tháo `C.hook` như thể nó đang được liên kết, có thể ghi hỏng danh sách đang chứa `B`.

Tương tự, di chuyển vùng nhớ chứa đối tượng đang liên kết — ví dụ mảng động cấp phát lại, `realloc`, `std::vector` tăng sức chứa hoặc một phép move không xử lý hook — có thể khiến các con trỏ trong danh sách trỏ tới **địa chỉ cũ**. Thời hạn sống và **địa chỉ ổn định** là hai yêu cầu liên quan nhưng không giống nhau.

Do đó:

- Không sao chép nguyên trạng một hook đang liên kết và xem bản sao như nút hợp lệ.
- Không tự ý di chuyển một đối tượng đang chứa hook liên kết.
- Khi muốn chuyển đối tượng sang nơi lưu khác, phải thiết kế quá trình unlink/relink an toàn và cập nhật các tham chiếu liên quan.
- Với kiểu C++ có hook intrusive, thường cần điều khiển rõ sao chép/move hoặc sử dụng chính sách của thư viện thích hợp.

### 9.3. Nút trên stack và owner sống ngắn hơn danh sách

Một tác vụ khai báo trong một hàm cục bộ có thể nằm trên stack:

```c
/* Minh họa lỗi vòng đời: KHÔNG sử dụng như mã đúng. */
void bad_add(Link *head) {
    Task local = {.id = 42};
    hook_init(&local.ready_hook);
    list_push_back(head, &local.ready_hook);
} /* local hết thời hạn sống; danh sách vẫn giữ con trỏ treo. */
```

Ngược lại, dùng biến stack **không tự động sai** nếu tất cả hook được tháo trước khi biến ra khỏi phạm vi, như `main` của ví dụ đầy đủ. Điều quyết định là **thời hạn sống của đối tượng có bao phủ thời gian nó thuộc mọi danh sách hay không**.

## 10. Tháo nút, chuyển danh sách và các thao tác thường gặp

Danh sách nội tại có ưu thế khi chương trình đã giữ con trỏ tới đối tượng và thường xuyên đổi trạng thái thành viên:

```text
ReadyQueue:
    A <--> B <--> C

Thao tác "chuyển B sang WaitingQueue":

ReadyQueue:       A <--> C
WaitingQueue:     ... <--> B
```

Nếu biết `B.ready_hook`, các thao tác tháo rồi chèn có số phép cập nhật con trỏ cố định, mỗi thao tác **O(1)**. Nhưng cần phân biệt:

- **Chuyển sang danh sách khác bằng cùng hook:** tháo hook khỏi danh sách cũ trước khi thêm vào danh sách mới, duy trì quy tắc một hook thuộc tối đa một danh sách.
- **Đồng thời thuộc hai danh sách:** cần hai hook khác nhau, chẳng hạn `ready_hook` và `waiting_hook`; không dùng chung một hook.
- **Chuyển một đoạn nút liên tiếp:** với danh sách đôi và đã biết hai biên đoạn cùng vị trí đích, có thể nối lại bằng một số phép cập nhật con trỏ cố định. Tuy nhiên, nếu phải tìm biên đoạn, đếm số nút di chuyển hoặc bảo trì bộ đếm kích thước, còn có chi phí bổ sung.

### Bảng độ phức tạp

Giả sử có `n` đối tượng đang thuộc một danh sách liên kết đôi; bỏ qua chi phí cấp phát và hủy đối tượng vì owner quản lý việc đó riêng.

| Thao tác | Chi phí thời gian | Điều kiện |
|---|---|---|
| Kiểm tra rỗng | `O(1)` | Sentinel đã khởi tạo |
| Lấy hook đầu hoặc cuối | `O(1)` | Sentinel có con trỏ `next` và `prev` |
| Chèn đầu/cuối | `O(1)` | Có hook chưa liên kết, sentinel hợp lệ |
| Chèn trước/sau hook đã biết | `O(1)` | Đã có con trỏ đến vị trí |
| Tháo hook đã biết | `O(1)` | Hook thật sự đang liên kết, không phải sentinel |
| Di chuyển một hook giữa hai danh sách | `O(1)` | Đã biết hook và vị trí đích |
| Tìm đối tượng theo khóa | `O(n)` xấu nhất | Không có bảng băm hoặc chỉ mục phụ |
| Lấy phần tử thứ `i` | `O(n)` xấu nhất | Phải duyệt liên kết, không có truy cập ngẫu nhiên |
| Duyệt hết các nút | `O(n)` | Mỗi nút thăm một lần |
| Tính số nút không có biến `size` | `O(n)` | Phải đếm khi duyệt |

Mỗi hook của danh sách liên kết đôi chứa thường là **hai con trỏ**. Với `n` đối tượng, tổng phần liên kết chiếm `O(n)` ô con trỏ, **nằm nhúng trong đối tượng**; thêm sentinel dùng `O(1)`. Không có cấp phát nút bao riêng cho từng phần tử, nhưng không có nghĩa mọi chi phí bộ nhớ biến mất.

## 11. Hiệu năng và bộ nhớ: khi nào intrusive list có lợi?

### Lợi ích tiềm năng

**Ít cấp phát riêng.** Nếu các đối tượng đã tồn tại, thao tác thêm vào danh sách thường chỉ nối hook. Điều này có thể tránh cấp phát một nút bao và giảm tải cho bộ cấp phát bộ nhớ.

**Ít mức gián tiếp hơn ở một số triển khai.** Duyệt từ hook có thể khôi phục trực tiếp đối tượng chứa nó, thay vì đi qua một nút bao có `value*`. Hiệu quả cụ thể còn phụ thuộc bố trí đối tượng.

**Phù hợp danh sách sự kiện và trạng thái.** Một đối tượng có thể tự mang hook sẵn sàng, hook timeout, hook quản lý phân loại; hệ thống không cần tạo nút bao cho mọi lần nó tham gia quan hệ.

**Thao tác di chuyển giữa danh sách nhanh.** Khi đã biết hook, tháo và nối lại chỉ đổi một số con trỏ.

### Chi phí và giới hạn

**Đối tượng luôn mang thêm trường liên kết.** Ngay cả khi chưa bao giờ nằm trong danh sách, mỗi đối tượng có thể vẫn chiếm chỗ cho hook (kể cả padding do căn chỉnh).

**Địa chỉ ổn định trở thành ràng buộc mạnh.** Nhiều cách lưu trữ di chuyển đối tượng, như mảng động tăng dung lượng, không tự phù hợp với hook intrusive đang liên kết.

**Dễ phụ thuộc vòng đời.** Container thường không tự hủy đối tượng; người dùng phải thiết kế owner, thứ tự tháo liên kết và xử lý lỗi.

**Không hỗ trợ truy cập theo chỉ số nhanh.** Giống danh sách liên kết thông thường, muốn tới nút thứ `i` phải lần theo liên kết `O(n)` trong trường hợp xấu nhất, khác với mảng `O(1)`.

**Tính cục bộ bộ nhớ chưa chắc tốt.** Các đối tượng có thể nằm phân tán trong heap, khiến duyệt con trỏ gặp nhiều lần cache miss. Việc tránh cấp phát nút bao không tự biến danh sách liên kết thành vùng dữ liệu liên tiếp như mảng.

### So sánh với mảng và container khác

| Yêu cầu ứng dụng | Lựa chọn thường nên cân nhắc | Lý do |
|---|---|---|
| Đọc phần tử thứ `i` thường xuyên | Mảng / mảng động | Truy cập trực tiếp `O(1)` |
| Duyệt theo thứ tự, cần cache locality | Mảng hoặc bố trí dữ liệu liên tiếp | Các phần tử thường nằm gần nhau |
| Liên tục tháo/chèn đối tượng đã có con trỏ | Danh sách nội tại | Cập nhật liên kết `O(1)`, không cần node bao riêng |
| Cần container sở hữu vòng đời các giá trị | Container có chính sách ownership rõ | Giảm trách nhiệm quản lý tài nguyên thủ công |
| Hàng đợi FIFO với thêm cuối/lấy đầu | Deque hoặc bộ đệm vòng; intrusive list nếu có đối tượng ổn định | Tùy cách tạo đối tượng và yêu cầu cấp phát |
| Tìm theo khóa rất nhiều | Bảng băm hoặc cây tìm kiếm | Không phải duyệt toàn danh sách `O(n)` |
| Luôn lấy đối tượng ưu tiên cao nhất | Heap hoặc hàng đợi ưu tiên | Duy trì thứ tự ưu tiên hiệu quả hơn |

Lựa chọn phụ thuộc loại thao tác, tần suất, quyền sở hữu và đặc tính bộ nhớ; không chỉ phụ thuộc Big-O của riêng phép chèn/xóa.

## 12. Chọn một chính sách sở hữu rõ ràng

Không có một quy tắc cấp phát duy nhất cho mọi intrusive list, nhưng có thể thiết kế hợp đồng cụ thể theo các mẫu sau.

### Mẫu A: một owner, nhiều danh sách chỉ tham chiếu

```text
Registry sở hữu Task
  |
  +--> ready list   (hook ready)
  +--> timeout list (hook timeout)
  +--> log/index khác
```

- Registry hoặc một đối tượng owner giữ tác vụ tồn tại.
- Các danh sách chỉ biểu diễn trạng thái hoặc thứ tự.
- Trước khi registry hủy tác vụ, hệ thống tháo tất cả hook và cập nhật chỉ mục liên quan.
- Có thể dùng `id` ổn định cho tham chiếu nghiệp vụ thay vì giữ con trỏ trực tiếp ở nhiều nơi.

### Mẫu B: cấp phát từ pool/arena

Nhiều đối tượng được cấp phát trong một vùng quản lý chung. Các hook liên kết chúng vào những hàng đợi công việc.

- Thường giúp giảm chi phí cấp phát từng đối tượng.
- Phải đảm bảo **không tái sử dụng ô trong pool** khi vẫn còn hook của đối tượng cũ hoặc có người dùng giữ con trỏ cũ.
- Khi tái sử dụng, phải khởi tạo lại trạng thái đối tượng và hook theo quy ước của danh sách.

### Mẫu C: container có chính sách tự tháo / tự hủy rõ ràng

Một số thư viện C++ chuyên biệt cho intrusive container hỗ trợ các **chế độ quản lý hook** hoặc chính sách hủy khác nhau (ví dụ tự tháo liên kết trong điều kiện thích hợp). Không nên mặc định mọi hook đều tự tháo khi đối tượng bị hủy: phải đọc hợp đồng của chính thư viện và kiểm tra giới hạn của từng chế độ.

Khái niệm **RAII** có thể giúp gắn việc tháo liên kết với vòng đời của một đối tượng quản lý tài nguyên. Tuy nhiên, cơ chế tự động vẫn phải bảo đảm thứ tự hủy an toàn, không truy cập sentinel đã chết và không để các quan hệ khác còn giữ con trỏ treo.

### Một quy trình hủy tác vụ an toàn

```text
Yêu cầu hủy Task T
      |
      v
Ngăn các thao tác mới sử dụng T
      |
      v
Tháo T khỏi mọi intrusive list đang tham gia
      |
      v
Xóa/cập nhật các chỉ mục và tham chiếu liên quan
      |
      v
Đợi các truy cập đang hoạt động hoàn tất nếu có đồng thời
      |
      v
Owner hủy Task T và giải phóng tài nguyên
```

Đây là **quy trình ý niệm**. Cơ chế kỹ thuật để “ngăn thao tác mới” hoặc “đợi truy cập hoàn tất” phụ thuộc môi trường, chẳng hạn dùng khóa, đếm tham chiếu hoặc một cơ chế thu hồi bộ nhớ an toàn cho đồng thời.

## 13. Đồng thời: các phép gán O(1) không tự trở thành thread-safe

Chèn hoặc xóa một hook phải sửa **nhiều con trỏ**. Trên một luồng, ta có thể sắp thứ tự các phép gán để bảo toàn bất biến sau thao tác. Nhưng khi hai luồng sửa cùng danh sách mà không đồng bộ:

```text
Luồng A: chèn X trước sentinel
Luồng B: xóa Y khỏi danh sách

Cả hai có thể đọc/ghi cùng next/prev.
Nếu xen kẽ không kiểm soát, danh sách có thể đứt liên kết.
```

Các nguy cơ gồm:

- **Race condition** làm thay đổi liên kết dựa trên trạng thái đã lỗi thời.
- **Use-after-free** khi một luồng duyệt còn luồng khác đã hủy đối tượng.
- **ABA/reuse** khi một địa chỉ được giải phóng, cấp phát lại cho đối tượng khác và người duyệt nhầm đó là nút cũ.
- **Deadlock** nếu có nhiều danh sách và dùng nhiều khóa theo thứ tự không nhất quán.

Các phép gán con trỏ riêng lẻ không làm **toàn bộ thao tác liên kết** trở thành nguyên tử. Một intrusive list thông thường cần đồng bộ bên ngoài khi được dùng chung giữa nhiều luồng. Cấu trúc lock-free, nếu có, cần thuật toán và cơ chế thu hồi bộ nhớ chuyên dụng; không thể đạt an toàn chỉ bằng cách bỏ khóa khỏi đoạn mã danh sách liên kết đôi vừa trình bày.

Để giải thích Big-O trong các phần trước, ta giả định thao tác được thực hiện **không có sửa đổi đồng thời gây xung đột** và các con trỏ đang dùng vẫn hợp lệ.

## 14. Những lỗi đặc trưng và cách phòng tránh

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| `free(task)` khi một hook của task còn liên kết | Danh sách giữ con trỏ treo; use-after-free | Tháo mọi hook trước khi owner hủy |
| Chèn một hook hai lần | Ghi đè `prev/next`, hỏng liên kết | Kiểm tra trạng thái hook chưa liên kết |
| Dùng cùng hook cho hai danh sách đồng thời | Hai danh sách tranh cùng hai con trỏ | Mỗi membership có hook riêng |
| Xóa sentinel như nút dữ liệu | Hỏng đầu danh sách | Sentinel không đi qua API xóa hook dữ liệu |
| Duyệt rồi xóa, sau đó đọc `it->next` | `it` có thể bị reset hoặc đã hủy | Lưu con trỏ kế tiếp trước khi xóa |
| Sao chép cấu trúc chứa hook đã nối bằng `memcpy` | Bản sao có liên kết giả, láng giềng không trỏ về nó | Cấm/kiểm soát sao chép hook đang nối |
| `realloc` hoặc di chuyển đối tượng đang được liên kết | Láng giềng vẫn giữ địa chỉ cũ | Duy trì địa chỉ ổn định hoặc unlink/relink đúng |
| Dùng sai trường trong `offsetof` | Truy ra địa chỉ đối tượng sai | Dùng đúng kiểu và đúng hook |
| Gọi `container_of` trên sentinel | Sentinel không nằm trong một Task | Kiểm tra `it != head` khi duyệt |
| Mặc định container tự giải phóng đối tượng | Rò rỉ hoặc hủy sai trách nhiệm | Xác định owner và chính sách hủy |
| Mặc định mọi hook chưa nối đều có `next==NULL` | API khác có thể dùng quy ước riêng | Theo hợp đồng của thư viện |
| Dựa vào `assert` để kiểm tra dữ liệu không tin cậy | Bản phát hành có thể bỏ kiểm tra | Thực thi kiểm tra tiền điều kiện phù hợp |
| Sửa danh sách đồng thời không khóa | Race, mất liên kết, truy cập vùng đã hủy | Đồng bộ và quản lý vòng đời an toàn |
| Cho rằng truy cập nút thứ `i` là `O(1)` | Bỏ qua chi phí duyệt con trỏ | Phân biệt thao tác với hook đã biết và tìm vị trí |

Khi debug, có thể kiểm tra các bất biến tại từng nút:

```text
head.next.prev == &head
head.prev.next == &head
node.next.prev == &node
node.prev.next == &node
```

Các điều kiện trên là ví dụ cho **nút đang liên kết hợp lệ**. Với hook đã tháo theo quy ước của bài, hai con trỏ là `NULL` nên không được giải tham chiếu chúng.

## 15. Bài tập tự kiểm tra

**Bài 1.** Giải thích điểm khác biệt giữa `struct Node { Task *value; Node *next; }` và `struct Task { Link hook; ... }`. Cách nào cần nút bao riêng?

**Bài 2.** Một `Task` có `ready_hook` đang liên kết trong `ReadyQueue`. Gọi `list_remove(&task.ready_hook)` có tự động hủy `Task` không? Sau thao tác, quyền sở hữu của `Task` thuộc về ai?

**Bài 3.** Với danh sách đôi vòng rỗng dùng sentinel `head`, `head.next` và `head.prev` phải trỏ tới đâu? Vì sao cách này thuận tiện cho thao tác thêm cuối?

**Bài 4.** Danh sách có ba hook `A <-> B <-> C`. Sau khi tháo `B`, các liên kết giữa `A` và `C` phải có giá trị nào? Có cần duyệt từ đầu danh sách nếu đã biết `B` không?

**Bài 5.** Khi một hook thuộc danh sách, tại sao lệnh `list_push_back(&another_head, &same_hook)` mà không tháo trước có thể làm hỏng cả hai danh sách?

**Bài 6.** Một đối tượng `Task` cần đồng thời thuộc danh sách `ReadyQueue` và `TimeoutQueue`. Hãy đề xuất khai báo `struct Task` tối thiểu cho hai membership, và nêu số hook cần tháo trước khi hủy nếu cả hai đang liên kết.

**Bài 7.** Tại sao không được `memcpy` một `Task` đang liên kết rồi coi bản sao là một nút hợp lệ trong danh sách cũ? Phần nào của quan hệ liên kết không được sao chép đúng?

**Bài 8.** Một đối tượng được cấp phát trong mảng động có thể bị di chuyển khi mảng mở rộng. Rủi ro gì xảy ra nếu hook của nó đang nối vào intrusive list?

**Bài 9.** Trong mã C:

```c
for (Link *it = head.next; it != &head; it = it->next) {
    if (match(it)) list_remove(it);
}
```

Điều gì sai với cách cập nhật `it`? Hãy viết hướng sửa mà không cần thực thi.

**Bài 10.** Một danh sách intrusive có `n` nút và đã có con trỏ trực tiếp tới `node`. Chi phí tháo `node` là bao nhiêu? Nếu chỉ biết `id` của đối tượng và phải tìm trong danh sách từ đầu thì tổng chi phí là bao nhiêu trong trường hợp xấu nhất?

**Bài 11.** Mỗi đối tượng có hai hook `ready_hook` và `timeout_hook`. Nếu đang duyệt danh sách timeout, nên dùng offset của trường nào để phục hồi `Task` từ con trỏ `Link*`? Vì sao?

**Bài 12.** Vì sao việc giữ địa chỉ ổn định và tháo hook trước khi hủy vẫn chưa đủ để bảo đảm an toàn khi nhiều luồng truy cập đồng thời? Cần thêm nhóm cơ chế gì?

### Đáp án và giải thích

1. `Node` riêng bọc con trỏ tới `Task` là non-intrusive; `Task` tự chứa `Link hook` là intrusive. Phương án đầu cần nút bao riêng nếu dùng đúng cách khai báo ấy.
2. Không. `list_remove` chỉ sửa quan hệ thành viên và làm hook tách khỏi danh sách. Owner của `Task` vẫn chịu trách nhiệm giữ/hủy đối tượng.
3. Cả hai trỏ tới chính `&head`. Khi thêm cuối, chèn hook mới ngay trước sentinel, không cần nhánh xử lý riêng cho đầu hoặc cuối rỗng.
4. `A.next = &C` và `C.prev = &A`; hook `B` trở về trạng thái đã tháo. Khi biết `B` và có liên kết đôi, thao tác `O(1)`.
5. Hook chỉ chứa một cặp `prev/next`; nối vào danh sách thứ hai sẽ ghi đè con trỏ của danh sách thứ nhất, làm mất bất biến hai chiều.
6. Khai báo có hai trường `Link ready_hook; Link timeout_hook;`. Nếu cả hai đang liên kết, phải tháo cả hai trước khi hủy `Task`.
7. Bản sao có giá trị con trỏ `prev/next` cũ, nhưng các nút láng giềng vẫn trỏ về hook của đối tượng gốc, không trỏ về hook bản sao. Không có liên kết hai chiều nhất quán cho bản sao.
8. Danh sách và các nút láng giềng có thể vẫn trỏ tới địa chỉ hook cũ; truy cập sau khi vùng nhớ cũ hết hợp lệ gây lỗi con trỏ treo.
9. `list_remove(it)` có thể đặt `it->next=NULL`, nên biểu thức bước lặp `it=it->next` không còn hợp lệ. Lưu `next=it->next` trước khi tháo, rồi dùng `it=next`.
10. Có con trỏ `node`: tháo `O(1)`. Chỉ biết `id` và không có chỉ mục: tìm có thể `O(n)`, rồi tháo `O(1)`, tổng `O(n)`.
11. Dùng `offsetof(Task, timeout_hook)`, vì con trỏ đang trỏ tới trường `timeout_hook`. Dùng offset của `ready_hook` sẽ trừ sai số byte và phục hồi địa chỉ đối tượng không đúng.
12. Đồng thời có thể làm các lần ghi con trỏ xen kẽ và một luồng hủy nút khi luồng khác đang đọc. Cần đồng bộ truy cập (khóa hoặc thuật toán concurrent đúng đắn) cùng cơ chế quản lý/thu hồi bộ nhớ an toàn.

## 16. Ghi nhớ

**Danh sách nội tại (intrusive list)** đưa các liên kết vào **chính đối tượng** thay vì tạo một nút bao độc lập cho mỗi phần tử. Cách này có thể giảm cấp phát nút riêng và hỗ trợ chèn/tháo hook đã biết trong **O(1)**, nhưng không cho truy cập ngẫu nhiên theo chỉ số: tìm vị trí hoặc giá trị vẫn thường **O(n)**. Điểm quan trọng nhất là **membership khác ownership**: tháo hook không đồng nghĩa hủy đối tượng, còn hủy một đối tượng khi hook đang liên kết có thể để lại con trỏ treo. Một hook chỉ nên tham gia **tối đa một danh sách tại một thời điểm**; muốn tham gia nhiều danh sách đồng thời phải có các hook độc lập. Đối tượng chứa hook phải còn sống, có địa chỉ ổn định và được tháo khỏi mọi quan hệ liên kết trước khi hủy. Lựa chọn intrusive list chỉ hợp lý khi hiểu rõ những bất biến, chính sách vòng đời và chi phí bộ nhớ, đồng thời có cơ chế đồng bộ phù hợp nếu danh sách được dùng giữa nhiều luồng.
