# Bí danh tham chiếu và thay đổi có thể quan sát từ nhiều nơi

Giả sử màn hình danh sách công việc và bộ nhớ đệm của ứng dụng cùng tham chiếu đến một đối tượng `Task`. Khi màn hình đổi trạng thái `done` từ `false` thành `true`, bộ nhớ đệm có nhìn thấy thay đổi đó không? Nếu một hàm gán lại biến tham số để trỏ tới một công việc mới, biến ở phía gọi có đổi theo không? Khi hai danh sách liên kết dùng chung một nút, sửa `next` của nút ấy ảnh hưởng tới cấu trúc nào?

Những câu hỏi này xoay quanh **bí danh tham chiếu (reference aliasing)**: nhiều đường truy cập dẫn tới **cùng một đối tượng hoặc vùng lưu trữ**. Nếu đối tượng có thể thay đổi, một lần ghi qua đường này có thể được quan sát qua đường khác. Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, chương **Bộ nhớ và biểu diễn**, đây là nền tảng để giữ bất biến cho mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời đánh giá thời gian và bộ nhớ của thao tác.

Sau bài học, bạn có thể:

- Vẽ sơ đồ các tên biến, tham chiếu, con trỏ và đối tượng đích; phân biệt **cùng giá trị** với **cùng danh tính**.
- Dự đoán sự khác nhau giữa **thay đổi đối tượng (mutation)** và **gán lại một đường tham chiếu (rebinding)**.
- Nhận ra aliasing trực tiếp, gián tiếp qua trường/collection, qua tham số hàm và qua các cấu trúc dùng chung nút.
- Xác định bất biến bị tác động khi nhiều đường truy cập cùng quan sát một thay đổi.
- Biết khi nào nên chia sẻ, hạn chế sửa đổi, sao chép hay quy định quyền sở hữu để tránh lỗi.

## 1. Bí danh là gì?

Hai biểu thức hoặc đường truy cập tạo thành **bí danh** khi chúng có thể định vị cùng một đối tượng, cùng một vị trí lưu trữ hoặc một phần vùng lưu trữ giao nhau. Trong các ví dụ đơn giản, ta nói hai biến `a` và `b` là bí danh ở mức đối tượng nếu cùng dẫn tới một đối tượng có danh tính `O`.

```text
Tên a ----+
          +----> Đối tượng O: {score: 50}
Tên b ----+

a và b là hai đường truy cập cùng đến O.
```

Nếu `O.score` thay đổi thành `80`, đọc trường đó qua `a` hoặc `b` đều cho giá trị mới, miễn là cả hai tiếp tục tham chiếu tới `O` và thao tác truy cập tuân thủ quy tắc ngôn ngữ. Ta gọi đây là **hiệu ứng quan sát qua bí danh** (*aliasing effect*).

### 1.1. Cùng giá trị chưa chắc là cùng đối tượng

```python
left = [1, 2]
right = [1, 2]
alias = left

print(left == right)  # True: nội dung bằng nhau
print(left is right)  # False: hai list khác nhau
print(left is alias)  # True: cùng đối tượng
```

Trong Python, `==` so sánh bằng nhau theo kiểu dữ liệu, còn `is` kiểm tra danh tính. Nếu đổi `left[0]`, `alias[0]` đổi theo; `right[0]` không đổi. Với một số kiểu bất biến, việc hệ thống tái sử dụng đối tượng có thể làm so sánh danh tính tình cờ cho kết quả không như trực giác; **không dùng `is` thay `==` để so sánh nội dung**.

### 1.2. Bí danh theo toàn đối tượng hay theo một phần?

Xét hai mảng hoặc hai cấu trúc nhìn vào các vùng byte **có thể chồng lấn**:

```text
Buffer có 8 phần tử: [0][1][2][3][4][5][6][7]
View A nhìn vào:     [0][1][2][3][4]
View B nhìn vào:           [2][3][4][5][6]
                           ^^^^^^^^^
                           Phần giao nhau
```

Hai view không nhất thiết trỏ đến cùng **phần tử đầu**, nhưng cùng truy cập được các vị trí `2`, `3`, `4`. Một thay đổi ở phần giao nhau có thể được nhìn thấy qua cả hai view. Vì vậy aliasing còn gồm **chia sẻ một phần vùng dữ liệu**, không chỉ trường hợp hai biến có cùng giá trị địa chỉ.

Không phải mọi ngôn ngữ đều cho phép tạo view vào bộ nhớ theo cùng cách. Trong C++ có `std::span`; Python có `memoryview` cho các đối tượng hỗ trợ buffer protocol; một số thư viện mảng cung cấp slice view. Phải biết chính xác API trả về **view** hay **bản sao**.

## 2. Thay đổi trạng thái và gán lại tên là hai thao tác khác nhau

Trong ngôn ngữ có đối tượng thay đổi được (*mutable*), cần tách:

1. **Mutation**: sửa trạng thái của đối tượng đang có, qua một đường tham chiếu.
2. **Rebinding**: gán lại tên biến hoặc ô tham chiếu để dẫn tới một đối tượng khác.
3. **Thay đối tượng lồng trong container**: đổi một ô chứa tham chiếu; có thể không sửa đối tượng mà ô cũ trỏ tới.

### 2.1. Ví dụ Python có thể chạy ngay

```python
a = ["A", "B"]
b = a

b.append("C")
print(a)  # ['A', 'B', 'C'] -- mutation của cùng list
print(b)  # ['A', 'B', 'C']

b = ["X", "Y"]  # Gán lại tên b sang list khác
print(a)        # ['A', 'B', 'C']
print(b)        # ['X', 'Y']

a[0] = "Z"      # Sửa list ban đầu; b không còn trỏ đến nó
print(a)        # ['Z', 'B', 'C']
print(b)        # ['X', 'Y']
```

Đọc từng dòng theo sơ đồ:

```text
Bước 1: a ──┐
            ├──> List 1 ["A", "B"]
        b ──┘

Bước 2: b.append("C")
        a ──┐
            ├──> List 1 ["A", "B", "C"]
        b ──┘

Bước 3: b = ["X", "Y"]
        a ─────> List 1 ["A", "B", "C"]
        b ─────> List 2 ["X", "Y"]
```

Bài toán cần phân tích **biến đang trỏ đến đâu tại từng thời điểm**, không chỉ “hai biến trước đó từng cùng trỏ một đối tượng”.

### 2.2. Biến bất biến không có thao tác sửa tại chỗ như list

```python
x = 10
y = x
y += 1

print(x)  # 10
print(y)  # 11
```

`int` của Python là bất biến: `y += 1` làm tên `y` ràng buộc với kết quả khác, không sửa một số nguyên dùng chung theo kiểu `list.append`. Với chuỗi Python cũng vậy: `name += "!"` tạo/ràng buộc giá trị chuỗi kết quả theo ngữ nghĩa bất biến; các tên trỏ chuỗi cũ không quan sát việc chuỗi cũ bị sửa tại chỗ.

Lưu ý **bất biến ở một cấp** không đồng nghĩa bất biến sâu. Ví dụ một `tuple` không cho thay chính ô tham chiếu của nó, nhưng nếu ô chứa một `list`, list con vẫn có thể bị sửa:

```python
inner = [1, 2]
outer = (inner, "fixed")
alias = outer[0]

alias.append(3)
print(outer)  # ([1, 2, 3], 'fixed')
```

## 3. Alias trong C: sao chép giá trị con trỏ, cùng sửa đối tượng

Trong C, con trỏ là một **giá trị** có thể chỉ đến đối tượng thích hợp. Sao chép con trỏ tạo hai biến con trỏ riêng, nhưng chúng có thể cùng trỏ đến **một đối tượng đích**.

```c
#include <stdio.h>

int main(void) {
    int score = 50;

    int *p = &score;
    int *q = p;

    *p = 70;
    printf("score=%d, *q=%d\n", score, *q);  /* 70, 70 */

    *q = 80;
    printf("score=%d, *p=%d\n", score, *p);  /* 80, 80 */

    q = NULL;   /* Đổi bản sao con trỏ q. */
    printf("score=%d, *p=%d\n", score, *p);  /* 80, 80 */
    return 0;
}
```

Trong ví dụ:

- `p` và `q` ban đầu có cùng giá trị địa chỉ `&score`.
- `*p` và `*q` là những đường truy cập tới cùng đối tượng `score`.
- `q = NULL` chỉ đổi giá trị trong **biến con trỏ q**; không sửa `p` hay `score`.

| Biểu thức | Vai trò | Khi gán, điều gì thay đổi? |
| --- | --- | --- |
| `score = 5` | Ghi đối tượng `int` | Giá trị của `score` |
| `*p = 5` | Ghi thông qua con trỏ | Đối tượng mà `p` đang chỉ đến |
| `p = &other` | Gán lại con trỏ | Địa chỉ được lưu trong `p` |
| `q = p` | Sao chép giá trị con trỏ | Địa chỉ lưu trong `q` |
| `&p` | Địa chỉ của chính biến `p` | Biểu thức lấy địa chỉ, không ghi |

### 3.1. Alias không chứng minh con trỏ hợp lệ mãi mãi

Một con trỏ có thể trỏ đến vùng nhớ đã hết vòng đời. Với C, phải tránh đọc/ghi qua con trỏ treo dù địa chỉ cũ trông giống địa chỉ hợp lệ:

```c
#include <stdlib.h>

int main(void) {
    int *p = malloc(sizeof *p);
    if (p == NULL) return EXIT_FAILURE;

    *p = 10;
    int *q = p;   /* p và q trỏ đến cùng vùng động. */

    free(p);
    p = NULL;

    /* *q = 20;   SAI: q là con trỏ treo, đối tượng đã được free. */
    /* Không free(q): sẽ là giải phóng hai lần cùng vùng. */
    return EXIT_SUCCESS;
}
```

Đặt `p = NULL` không tự cập nhật `q`. Trong cấu trúc dữ liệu chứa nhiều con trỏ tới một nút, phải quản lý quyền sở hữu/vòng đời để không nơi nào truy cập nút đã giải phóng.

### 3.2. Alias qua tham số hàm

C truyền tham số **theo giá trị**. Nếu tham số có kiểu con trỏ, bản sao giá trị con trỏ có thể truy cập cùng đối tượng đích:

```c
#include <stdio.h>

void double_value(int *target) {
    if (target != NULL) {
        *target *= 2;
    }
}

void rebind_locally(int *target) {
    target = NULL;   /* Chỉ đổi bản sao tham số trong hàm. */
    (void)target;
}

int main(void) {
    int x = 7;
    int *p = &x;

    double_value(p);
    rebind_locally(p);

    printf("x=%d, *p=%d\n", x, *p);  /* x=14, *p=14 */
    return 0;
}
```

Nếu muốn hàm thay **chính biến con trỏ của người gọi**, có thể nhận `int **`, hoặc trả về con trỏ rồi để người gọi gán kết quả. Sửa dữ liệu qua `*target` và thay tên con trỏ `target` là hai ý đồ khác nhau.

## 4. Alias trong C++, Java và Python

Ngôn ngữ có cách biểu diễn và cú pháp khác nhau, nhưng câu hỏi luôn là: **hai đường truy cập có cùng đến một đối tượng thay đổi được không?**

### 4.1. C++: tham chiếu và con trỏ

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> numbers{10, 20};

    std::vector<int>& alias = numbers;  // Tham chiếu C++.
    std::vector<int> copied = numbers;  // Container độc lập.

    alias[0] = 99;

    std::cout << numbers[0] << "\n"; // 99
    std::cout << copied[0] << "\n";  // 10

    std::vector<int> other{7};
    alias = other;  // GÁN GIÁ TRỊ vào numbers, không rebind alias!
    std::cout << numbers[0] << "\n"; // 7
}
```

Khác với biến tham chiếu của một số ngôn ngữ, tham chiếu C++ sau khi được ràng buộc không thể “đổi sang ràng buộc” một đối tượng khác bằng phép gán. `alias = other` gọi phép gán trên **đối tượng numbers**; do đó `numbers` trở thành nội dung của `other`.

Con trỏ C++ thì có thể gán lại để trỏ đối tượng khác như con trỏ C. Cả tham chiếu và con trỏ đều có thể gặp vấn đề **vòng đời** nếu đối tượng đã bị hủy hoặc bị container chuyển vùng lưu trữ.

### 4.2. Java: nhiều biến cùng tham chiếu đến một object

```java
class Task {
    String title;
    boolean done;

    Task(String title) {
        this.title = title;
        this.done = false;
    }
}

class Example {
    public static void main(String[] args) {
        Task screen = new Task("Review");
        Task cache = screen;

        cache.done = true;
        System.out.println(screen.done);  // true

        cache = new Task("Other");
        System.out.println(screen.title); // Review
        System.out.println(cache.title);  // Other
    }
}
```

`screen` và `cache` ban đầu mang tham chiếu tới cùng một đối tượng `Task`. Ghi `cache.done` làm đối tượng thay đổi, nên `screen.done` thấy giá trị mới. Nhưng `cache = new Task(...)` chỉ gán lại biến `cache`. Java truyền đối số cho hàm theo giá trị; đối số kiểu tham chiếu là **bản sao của tham chiếu**.

### 4.3. Python: nhiều tên, một đối tượng

```python
task = {"title": "Review", "done": False}
screen = task
cache = task

cache["done"] = True
print(screen["done"])  # True
print(task["done"])    # True

cache = {"title": "Other", "done": False}
print(screen["title"]) # Review
print(cache["title"])  # Other
```

Cả hai thao tác `cache["done"] = True` và `cache = {...}` có dấu `=`, nhưng chúng có ý nghĩa khác nhau: trường hợp đầu **gán vào một ô của đối tượng dict**, trường hợp sau **gán lại tên cache**.

Một cách tự hỏi hiệu quả: bên trái phép gán là **tên**, **ô của collection**, hay **trường của đối tượng**? Sau đó xem đối tượng chứa ô/trường đó có đang dùng chung hay không.

## 5. Aliasing gián tiếp: collection riêng, phần tử chung

Hai container độc lập vẫn có thể chứa cùng tham chiếu phần tử. Vì vậy cần phân tích **từng cấp** trong cấu trúc lồng nhau.

```python
user = {"name": "An", "points": 10}

active_users = [user]
archive = [user]  # Container khác nhưng phần tử dùng chung.

archive[0]["points"] = 50
print(active_users[0]["points"])  # 50

archive.append({"name": "Binh", "points": 8})
print(len(active_users))  # 1
print(len(archive))       # 2
```

Sơ đồ:

```text
active_users -> [ ref ] ----+
                            +---> user {name:"An", points:50}
archive      -> [ ref ] ----+
```

Thêm phần tử vào `archive` sửa **container archive**, nên độ dài `active_users` không đổi. Nhưng sửa `archive[0]["points"]` đi qua phần tử chung `user`, nên hai container đều quan sát cùng điểm mới.

Điều tương tự có thể xảy ra trong Java khi hai `ArrayList<Task>` cùng chứa một `Task`, trong C/C++ khi hai mảng con trỏ cùng trỏ tới một `struct`, hay khi hai nhánh đồ thị cùng dẫn tới một đỉnh.

### 5.1. Alias qua nhiều lớp

```python
child = {"value": 1}
left = {"inner": child}
right = {"inner": child}
root = [left, right]

root[0]["inner"]["value"] = 42
print(root[1]["inner"]["value"])  # 42
```

Ở đây `left` và `right` khác đối tượng, nhưng các đường `left["inner"]` và `right["inner"]` cùng đi tới `child`. Muốn phát hiện alias, cần xem **toàn bộ đường tham chiếu**, không dừng ở so sánh danh tính của hai container ngoài.

## 6. Phân tích alias bằng đồ thị đối tượng

Có thể mô hình hóa bộ nhớ ở mức đối tượng thành một **đồ thị có hướng**:

- **Nút:** đối tượng hoặc vùng lưu trữ.
- **Cạnh:** con trỏ, tham chiếu hay trường chứa liên kết.
- **Gốc:** các biến, trường trong container hoặc cấu trúc dữ liệu mà chương trình đang giữ.

Hai đường đi từ các gốc khác nhau hội tụ vào cùng một nút nghĩa là các gốc có thể truy cập cùng đối tượng. Nếu có một đường ghi được tới đối tượng ấy, thay đổi có thể quan sát qua đường khác.

```text
Root A ---> Node 1 ---> Node 3 ---> Node 5
                         ^            |
                         |            v
Root B ---> Node 2 ------+           NULL

Node 3 có hai đường đi tới: A và B.
```

Ví dụ về “cùng địa chỉ” chỉ là một trường hợp dễ nhận thấy. Một chương trình thực có thể có nhiều lớp con trỏ, nhiều container và liên kết ngược, khiến alias không hiển nhiên ngay từ tên biến.

### 6.1. Tập các đối tượng có thể đi tới (reachability)

Gọi `Reach(root)` là tập đối tượng có thể tới được từ `root` bằng các liên kết cho phép. Nếu:

```text
Reach(A) = {Node 1, Node 3, Node 5}
Reach(B) = {Node 2, Node 3, Node 5}
```

thì `Reach(A) ∩ Reach(B) = {Node 3, Node 5}`: hai cấu trúc dùng chung một phần đồ thị đối tượng. Điều này chưa tự chứng minh lỗi. Nó chỉ cho thấy **việc sửa hoặc giải phóng nút chung phải tuân theo hợp đồng của cả hai cấu trúc**.

Ví dụ trong danh sách liên kết đơn bất biến, chia sẻ đuôi có thể tiết kiệm bộ nhớ. Nhưng với hai danh sách thường xuyên sửa trường `next`, một lần đổi liên kết trong phần dùng chung làm thay đổi đường đi của cả hai danh sách.

### 6.2. Chia sẻ giá trị và chia sẻ liên kết là hai mức ảnh hưởng

Với nút `Node {value, next}`:

- Sửa `node.value` có thể làm hai cấu trúc nhìn thấy **giá trị** mới.
- Sửa `node.next` có thể làm hai cấu trúc nhìn thấy **tập nút và thứ tự duyệt** khác.
- Giải phóng `node` có thể làm mọi đường trỏ tới nó trở nên không hợp lệ.
- Gán lại `headA` chỉ thay đường đi từ **gốc A**; nếu không sửa nút dùng chung, gốc B vẫn như cũ.

Do đó, khi sửa một cấu trúc dữ liệu, cần liệt kê những **bất biến phụ thuộc vào trạng thái đang ghi**, chứ không chỉ xem kết quả của một biến đầu vào.

## 7. Danh sách liên kết có chung đuôi: ví dụ C cụ thể

Giả sử hai danh sách có chung hai nút đuôi:

```text
A: [1] --+
         |
         +--> [3] --> [5] --> NULL
         |
B: [2] --+
```

Hai danh sách có hai nút đầu riêng, nhưng dùng chung các nút `3` và `5`. Chương trình C sau dùng **các biến nút cục bộ** để minh họa alias mà không cần quản lý `malloc/free`:

```c
#include <stdio.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

static void print_list(const Node *head) {
    for (const Node *p = head; p != NULL; p = p->next) {
        printf("%d ", p->value);
    }
    puts("");
}

int main(void) {
    Node tail = {5, NULL};
    Node shared = {3, &tail};

    Node first_a = {1, &shared};
    Node first_b = {2, &shared};

    Node *head_a = &first_a;
    Node *head_b = &first_b;

    print_list(head_a);  /* 1 3 5 */
    print_list(head_b);  /* 2 3 5 */

    shared.value = 30;  /* Cùng một nút được hai danh sách truy cập. */
    print_list(head_a);  /* 1 30 5 */
    print_list(head_b);  /* 2 30 5 */

    first_b.next = &tail; /* Chỉ thay liên kết thuộc prefix của B. */
    print_list(head_a);  /* 1 30 5 */
    print_list(head_b);  /* 2 5 */

    return 0;
}
```

Giải thích:

1. Ban đầu cả `first_a.next` và `first_b.next` đều trỏ tới `shared`.
2. Ghi `shared.value = 30` đổi giá trị của **một nút dùng chung**; cả hai danh sách đều thấy `30`.
3. Ghi `first_b.next = &tail` thay trường của **nút đầu B**, vốn không được A dùng chung; đường đi từ A giữ nguyên.
4. Nếu thay `shared.next` khi B còn nối qua `shared`, đường đi của **cả A và B** sẽ thay đổi.

### 7.1. Những bất biến dễ hỏng

Giả sử mỗi danh sách còn lưu `size` và `tail` riêng. Một phép thay `shared.next` hoặc xóa nút dùng chung có thể khiến cả hai bản ghi metadata đó **không khớp** với danh sách thực tế. Ví dụ, nếu chỉ cập nhật `listA.size` sau khi cắt đuôi trong vùng chung, `listB.size` có thể sai. Với cấu trúc yêu cầu sở hữu riêng, việc chia sẻ nút ngay từ đầu đã vi phạm giả định của API.

Đừng tự `free` nút `shared` hoặc `tail` trong ví dụ trên: chúng là biến cục bộ, không phải vùng cấp phát bằng `malloc`. Với nút cấp phát động, chính sách giải phóng phải làm rõ liệu một hay nhiều danh sách có quyền sở hữu. Hai danh sách cùng “sở hữu duy nhất” một nút là hợp đồng mâu thuẫn.

### 7.2. Aliasing và độ phức tạp

Việc tạo thêm một con trỏ tới nút đã biết thường O(1) và dùng O(1) bộ nhớ cho liên kết. Việc **phát hiện mọi nút dùng chung** giữa hai danh sách có thể cần duyệt các nút hoặc dùng cấu trúc bổ trợ; không thể coi thao tác đó tự động O(1).

Nếu hai danh sách không có chu trình và lưu `tail`, có thể kiểm tra liệu chúng **có giao nhau về nút** bằng cách so sánh con trỏ nút cuối: nếu giao nhau, chúng sẽ có cùng nút cuối. Nhưng việc suy ra hai đuôi chia sẻ theo cách này chỉ đúng với **danh sách liên kết đơn kết thúc tại NULL, không có chu trình, và các liên kết phù hợp**. Trường hợp đồ thị hoặc danh sách vòng cần cách phân tích khác.


## 8. Alias trên mảng, slice và vùng lưu trữ chồng lấn

Khi một API trả về một “đoạn dữ liệu”, cần xem nó tạo **bản sao riêng** hay một **view trỏ vào vùng gốc**. Hai đối tượng view có thể khác danh tính nhưng vẫn truy cập chung một số byte.

### 8.1. Python: list slice tạo bản sao nông

```python
data = [10, 20, 30, 40]
part = data[1:3]

part[0] = 99

print(data)  # [10, 20, 30, 40]
print(part)  # [99, 30]
```

Với `list` chuẩn của Python, slice thông thường tạo một **list mới** gồm các tham chiếu phần tử tương ứng; vì vậy thay **ô tham chiếu trong `part`** không thay ô của `data`.

Nhưng nếu các phần tử là đối tượng mutable, những đối tượng đó vẫn có thể được dùng chung:

```python
data = [{"count": 1}, {"count": 2}]
part = data[:]

part[0]["count"] = 7

print(data[0]["count"])  # 7: dict bên trong dùng chung
print(part is data)       # False: hai list ngoài khác nhau
```

### 8.2. Python: memoryview dùng chung byte của bytearray

```python
data = bytearray(b"abcd")
view = memoryview(data)[1:3]

view[0] = ord("X")  # Ghi vào byte có chỉ số 1 của data.

print(data)         # bytearray(b'aXcd')
print(bytes(view))  # b'Xc'

view.release()      # Không dùng view sau khi release.
```

Ở đây `view` là một đường truy cập gián tiếp vào **bộ đệm của `data`**, không phải một bản sao byte độc lập. Một số thao tác làm thay đổi kích thước `bytearray` có thể bị chặn khi còn `memoryview` đang xuất, vì việc dời vùng dữ liệu có thể khiến view không an toàn. Phải tuân thủ hợp đồng của buffer/view.

### 8.3. C: hai con trỏ đến vùng chồng lấn

```c
#include <stdio.h>

int main(void) {
    int values[] = {10, 20, 30, 40};

    int *first = &values[0];
    int *middle = &values[2];

    first[2] = 99;          /* Chính là values[2]. */
    printf("%d\n", *middle); /* 99 */

    middle[1] = 88;         /* Chính là values[3]. */
    printf("%d\n", values[3]); /* 88 */
    return 0;
}
```

Hai con trỏ `first` và `middle` có **giá trị địa chỉ khác nhau**, nhưng đường `first[2]` và `*middle` cùng chỉ tới `values[2]`. Đây là aliasing ở **mức ô phần tử**.

Nếu cần dịch các byte giữa những vùng chồng lấn, phải hiểu quy tắc sao chép: `memcpy` không hỗ trợ vùng nguồn và đích chồng lấn, trong khi `memmove` có ngữ nghĩa xử lý chồng lấn phù hợp. Tuy nhiên, việc chọn `memmove` **không giải quyết tự động** các vấn đề vòng đời đối tượng hay bất biến container.

### 8.4. C++: view có thể mất hiệu lực khi nguồn chuyển vùng

```cpp
#include <span>
#include <vector>

int main() {
    std::vector<int> values{10, 20, 30};
    std::span<int> view(values);

    view[1] = 99;  // values[1] cũng trở thành 99.

    // Không dùng view sau khi vector có thể cấp phát lại.
    values.reserve(1000);
}
```

`std::span<int>` (C++20) không sở hữu các phần tử; nó nhìn vào vùng lưu trữ của vector. Nếu `reserve` làm vector cấp phát lại, các con trỏ/view trỏ tới vùng cũ bị vô hiệu hóa. Để chương trình an toàn, phải xem **hiệu lực của view theo vòng đời và thao tác của container gốc**, không chỉ xét cùng đối tượng vào lúc tạo.

## 9. Alias ảnh hưởng đến bất biến của các cấu trúc dữ liệu

Alias không phải lỗi tự thân. Nó có thể là cơ chế cốt lõi để mô hình hóa **quan hệ giữa các nút**. Lỗi xuất hiện khi các thành phần cùng sửa một đối tượng nhưng không biết hoặc không duy trì các bất biến liên quan.

### 9.1. Stack và queue: cùng payload, hay cùng nút?

Một stack và một queue có thể cùng lưu **tham chiếu tới đối tượng công việc**. Khi công việc đổi trạng thái qua stack, nơi đọc từ queue thấy trạng thái mới. Đó có thể là thiết kế mong muốn.

Nhưng nếu stack và queue **dùng chung chính nút liên kết** và mỗi cấu trúc đều sửa trường `next` để duy trì thứ tự riêng, hai cấu trúc dễ phá hỏng liên kết của nhau. Một đối tượng nghiệp vụ dùng chung có thể an toàn hơn nếu **mỗi container sở hữu nút/ô liên kết riêng**:

```text
Stack node ----> Task O <---- Queue node
  (next S)                 (next Q)

Hai nút container riêng;
Task O là payload dùng chung có chính sách sửa rõ ràng.
```

Tách **liên kết của container** khỏi **đối tượng nghiệp vụ** giúp tránh việc hai cấu trúc cập nhật cùng trường `next` theo hai thứ tự độc lập.

### 9.2. Bảng băm: khóa mutable có thể làm sai kết quả tra cứu

Bảng băm sử dụng hàm băm và quy tắc bằng nhau để định vị khóa. Nếu **khóa mutable thay đổi phần dữ liệu quyết định hash/equality sau khi đưa vào bảng**, bảng có thể không còn tìm được mục bằng khóa theo cách dự kiến.

Trong Java, một khóa tùy biến có `hashCode()` phụ thuộc trường `id` phải tránh thay `id` khi khóa đang ở trong `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

class Key {
    int id;

    Key(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof Key)) return false;
        return id == ((Key) other).id;
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }
}

class Example {
    public static void main(String[] args) {
        Key key = new Key(1);
        Map<Key, String> lookup = new HashMap<>();

        lookup.put(key, "value");

        key.id = 2; // SAI về thiết kế khóa: hash/equality đã đổi.

        // Các lần tra cứu có thể không tìm được mục theo cách dự kiến.
        System.out.println(lookup.get(key));
    }
}
```

Ví dụ không khẳng định kết quả in ra luôn là `null` trên mọi dung lượng và trạng thái bảng, vì còn phụ thuộc cách phân bucket và va chạm. Vấn đề là **vi phạm hợp đồng rằng các thuộc tính dùng để băm và so sánh khóa phải ổn định khi khóa nằm trong bảng**.

Cách sửa điển hình là dùng khóa bất biến, hoặc xóa mục dưới khóa cũ **trước khi** đổi thuộc tính ảnh hưởng hash, rồi chèn lại theo khóa mới (với hợp đồng và kiểm soát quyền sở hữu rõ ràng). Nếu đối tượng chỉ là **giá trị (value)** của bảng và khóa ổn định, việc thay đổi trạng thái giá trị là vấn đề riêng về aliasing, không nhất thiết làm sai vị trí bucket.

### 9.3. Cây tìm kiếm: sửa khóa trực tiếp có thể phá thứ tự

Cây nhị phân tìm kiếm (BST) có bất biến thường dùng:

- Mọi khóa trong cây con trái **nhỏ hơn** khóa của nút (với quy tắc không trùng đã chọn).
- Mọi khóa trong cây con phải **lớn hơn** khóa của nút.
- Mỗi cây con cũng phải thỏa bất biến tương ứng.

Nếu một bên giữ tham chiếu trực tiếp tới nút có khóa `10` và sửa nó thành `100`, cây có thể không còn thỏa quan hệ thứ tự với tổ tiên và con cháu. Khi đó phép tìm kiếm dựa vào so sánh có thể bỏ qua vị trí nút thật sự.

```text
BST ban đầu:         Sau khi sửa key 10 -> 100 tại chỗ:

       20                        20
      /  \                      /  \
    10    30                  100   30
      \                         \
      15                         15

Khóa 100 nằm bên trái 20: bất biến BST bị phá vỡ.
```

Một API cây tìm kiếm an toàn thường **không cho sửa khóa tùy ý qua một tham chiếu ngoài**. Thay khóa cần thao tác xóa/chèn phù hợp, hoặc thực hiện một thuật toán cập nhật duy trì bất biến. Nếu cây có thêm trường `parent`, thay `left`/`right` còn phải cập nhật liên kết ngược tương ứng.

### 9.4. Heap: thay khóa ưu tiên phải sắp xếp lại

Binary heap đặt phần tử trong mảng theo bất biến heap (với min-heap: khóa cha không lớn hơn khóa con). Nếu một đối tượng được nhiều nơi tham chiếu và một bên thay **mức ưu tiên** của nó, heap có thể không còn thỏa thứ tự.

```text
Min-heap hợp lệ theo khóa:
        1
       / \
      3   5

Sửa trực tiếp khóa 1 -> 9:
        9
       / \
      3   5

Không còn bất biến min-heap tại gốc.
```

Giải pháp là dùng API `decrease_key`/`increase_key` hoặc thao tác cập nhật tương đương rồi sift lên/xuống, thường O(log n) trong heap nhị phân. Nếu heap giữ ánh xạ từ đối tượng sang chỉ số, mọi phép hoán đổi khi sift phải cập nhật **cả mảng heap lẫn ánh xạ chỉ số**. Điều này là một ví dụ điển hình của alias/metadata phải nhất quán giữa nhiều cấu trúc.

### 9.5. Đồ thị: một đỉnh có nhiều đường đi tới

Trong đồ thị, nhiều cạnh cùng trỏ đến một đỉnh là trạng thái bình thường:

```text
A ---+
     +----> C ----> D
B ---+
```

Nếu hai đường đi `A -> C` và `B -> C` cùng dẫn đến một **đối tượng đỉnh C**, việc sửa nhãn/trạng thái `visited` của C có thể được quan sát qua cả hai đường. Đây là điều cần thiết trong một số thuật toán như BFS/DFS, nơi mỗi đỉnh phải được đánh dấu **một lần** dù có nhiều đường đi tới.

Tuy vậy, nếu gộp nhầm hai **đối tượng đỉnh khác nhau nhưng cùng nhãn**, thuật toán có thể xử lý sai. Với đồ thị, phải định nghĩa rõ **định danh đỉnh**: dựa vào ID, tham chiếu đối tượng hay khóa bất biến. Trong một đồ thị có chu trình, cần tập `visited` phù hợp để việc duyệt không lặp vô hạn; không thể suy ra một đồ thị là cây chỉ vì có thể bắt đầu duyệt từ một nút.

### 9.6. Persistent structure: chia sẻ phải đi kèm bất biến bất biến

Một số cấu trúc dữ liệu **bền vững theo phiên bản (persistent)** dùng chung những cây con không thay đổi giữa các phiên bản. Đây là **structural sharing**, thường được thiết kế theo nguyên tắc không sửa các nút đã công bố.

```text
Version 1 ---> Root A ---> Subtree S
Version 2 ---> Root B ---> Subtree S
                             (bất biến, dùng chung)
```

Khi cần đổi dữ liệu thuộc `Subtree S` cho phiên bản 2, có thể tạo nút mới trên đường cập nhật thay vì sửa `S` tại chỗ. Trong cây cân bằng cao O(log n), cập nhật theo **path copying** thường sao chép O(log n) nút, với điều kiện kiểu dữ liệu và thuật toán thực hiện đúng cơ chế này.

Nếu một bên vẫn giữ **tham chiếu ghi trực tiếp tới S** và sửa S, cả hai phiên bản có thể quan sát thay đổi, làm mất tính đúng đắn của snapshot. Alias chỉ an toàn khi gắn với hợp đồng về mutability và vòng đời.

## 10. Mutation khi đang duyệt: alias có thể làm hành vi khó dự đoán

Khi một vòng lặp duyệt cấu trúc trong khi một đường tham chiếu khác sửa chính cấu trúc ấy, có thể xảy ra:

- Bỏ qua hoặc xử lý lặp một số phần tử.
- Sử dụng iterator/con trỏ đã bị vô hiệu hóa.
- Lặp vô hạn nếu liên kết tạo chu trình ngoài ý muốn.
- Nhận kết quả không nhất quán do kích thước và liên kết thay đổi giữa các bước.

### 10.1. Python: đừng sửa chiều dài list khi đang duyệt theo list đó

```python
items = [1, 2, 3, 4]

for item in items[:]:  # Duyệt bản sao list ngoài.
    if item % 2 == 0:
        items.remove(item)

print(items)  # [1, 3]
```

Ở đây `items[:]` tạo bản sao nông để **ổn định dãy các ô đang được duyệt**. `items.remove` thay đổi list gốc. Vì phần tử là số nguyên bất biến, bài toán rõ ràng. Nhưng khi phần tử là những đối tượng mutable, bản sao nông vẫn tham chiếu tới **cùng các đối tượng con**.

Cũng có thể viết `items = [x for x in items if x % 2 != 0]` để tạo list mới. Khi đó biến `items` được **gán lại**; những alias cũ tới list ban đầu vẫn giữ đối tượng cũ và không tự chuyển sang list mới.

### 10.2. C++: iterator và con trỏ có thể mất hiệu lực

```cpp
#include <vector>

int main() {
    std::vector<int> values{10, 20};
    int *p = values.data();

    values.reserve(1000);  // Có thể làm vector cấp phát lại.

    // Không dereference p sau khi p đã mất hiệu lực.
    (void)p;
}
```

Những con trỏ, tham chiếu và iterator vào phần tử của vector có thể bị vô hiệu hóa khi vector di chuyển vùng lưu trữ. Các quy tắc chính xác phụ thuộc thao tác, vị trí và có cấp phát lại hay không. Vì vậy **lưu một con trỏ từ trước** không bảo đảm nó vẫn có thể truy cập dữ liệu sau khi container thay đổi.

Trong danh sách liên kết, việc chèn nút thường không dời các nút cũ, nhưng **xóa một nút** vẫn làm những con trỏ/iterator tới nút bị xóa mất hiệu lực. Sự ổn định địa chỉ của nút còn sống không giải quyết được vấn đề vòng đời của nút đã bị hủy.

## 11. Giảm tác dụng phụ do aliasing bằng thiết kế API

Không cần loại bỏ mọi alias. Mục tiêu là làm rõ nơi nào được phép **đọc, ghi, thay liên kết và hủy đối tượng**.

### 11.1. Chia sẻ dữ liệu bất biến

Nếu hai nơi chỉ cần đọc và dữ liệu không thay đổi sau khi công bố, có thể chia sẻ vùng lưu trữ để tiết kiệm sao chép. Ví dụ: nhiều truy vấn tra cứu cùng một bảng cấu hình bất biến, hoặc nhiều phiên bản cây chia sẻ các nhánh đã cố định.

**Bất biến sâu** phải được xác định đúng: một container bên ngoài bất biến mà chứa phần tử mutable dùng chung chưa chắc đem lại dữ liệu ổn định toàn bộ.

### 11.2. Sao chép phòng vệ và làm rõ ranh giới sao chép

Khi một hàm cần trả dữ liệu để phía gọi có thể sửa **độc lập**, nó có thể trả bản sao:

```python
def snapshot_scores(scores):
    return list(scores)

original = [10, 20, 30]
snapshot = snapshot_scores(original)

snapshot[0] = 99

print(original)  # [10, 20, 30]
print(snapshot)  # [99, 20, 30]
```

Đây là **bản sao nông**, phù hợp với các phần tử số nguyên bất biến trong ví dụ. Nếu phần tử là đối tượng có thể thay đổi, cần quyết định có sao chép sâu hay không. Tạo bản sao của danh sách `n` phần tử thông thường tốn O(n) thời gian và O(n) dung lượng cho vùng phần tử mới; cách này đánh đổi bộ nhớ lấy sự độc lập.

### 11.3. Chỉ đọc qua một đường không làm toàn bộ đối tượng bất biến

Trong C/C++, tham chiếu/con trỏ chỉ đọc hạn chế thao tác **qua chính đường truy cập đó**:

```cpp
int number = 10;
const int& readonly = number;
int& writable = number;

writable = 99;
// readonly là tham chiếu const, nhưng đọc readonly giờ được 99.
```

`const` không tự ngăn những alias có quyền ghi khác thay đổi đối tượng gốc (trừ các trường hợp đối tượng thực sự là `const` và quy tắc ngôn ngữ tương ứng). Tương tự, trong Java `final Task task` không cho **gán lại biến `task`**, nhưng không làm trường `task.done` tự trở thành bất biến.

Do đó, một API chỉ cung cấp lối đọc qua một đường tham chiếu chưa phải là cam kết snapshot dữ liệu vĩnh viễn.

### 11.4. Quyền sở hữu rõ ràng

Một hợp đồng đơn giản cho container tự sở hữu các nút liên kết:

- Container có quyền cấp phát và xóa các nút của mình.
- Các lối mượn nút chỉ dùng trong khoảng thời gian hợp lệ.
- Những API có thể xóa/di chuyển nút phải mô tả hiệu lực của con trỏ/iterator sau thao tác.
- Nếu cho phép nhiều container chia sẻ nút, phải bổ sung hợp đồng sở hữu và đồng bộ metadata của các container liên quan.

Trong C++ có thể dùng `std::unique_ptr` cho sở hữu duy nhất, `std::shared_ptr` khi thật sự cần sở hữu chia sẻ và `std::weak_ptr` cho liên kết không sở hữu nếu phù hợp. Các lựa chọn này không tự giải quyết bất biến nghiệp vụ hoặc mọi vấn đề đồng thời.

### 11.5. Copy-on-write khi cần snapshot và đôi lúc ghi

**Copy-on-write (COW)** cho nhiều nơi đọc vùng dữ liệu chung, nhưng khi một bên cần ghi, nó phải đảm bảo có vùng riêng trước khi sửa:

```text
Ban đầu:
A ----+
      +--> [10][20][30]
B ----+

A ghi 99 ở vị trí 0:
A --------> [99][20][30]
B --------> [10][20][30]
```

Trong một hiện thực COW **toàn mảng**, tạo snapshot bằng cách chia sẻ có thể O(1), còn lần ghi đầu có thể cần sao chép O(n) phần tử; các lần ghi sau tùy trạng thái chia sẻ. COW cần bảo vệ tất cả đường ghi vào vùng gốc, kể cả view và con trỏ được trao cho bên ngoài; nếu không, một alias có thể ghi trực tiếp và phá vỡ ý nghĩa snapshot.

## 12. Aliasing và nhiều luồng: khả năng quan sát cần đồng bộ

Trong một luồng thực thi tuần tự, sau khi gán vào một đối tượng còn sống, đọc lại qua alias hợp lệ thường quan sát trạng thái mới theo thứ tự thực thi của ngôn ngữ. Nhưng khi có **nhiều luồng** truy cập dữ liệu có thể sửa, cần xem thêm mô hình bộ nhớ và đồng bộ.

Nếu hai luồng truy cập cùng một đối tượng, ít nhất một bên ghi và không có đồng bộ hợp lệ, chương trình C/C++ có thể gặp **data race**, dẫn đến hành vi không xác định. Java cũng cần quan hệ *happens-before* hoặc cơ chế phù hợp để bảo đảm khả năng quan sát/đúng đắn giữa các luồng. Không thể lấy giả định “hai biến cùng trỏ một object” làm cam kết rằng luồng kia sẽ lập tức và an toàn thấy thay đổi.

Ví dụ C++ với đối tượng đếm được truy cập qua nhiều tham chiếu: nên dùng đồng bộ phù hợp như `std::atomic<int>` cho một biến đếm đơn giản hoặc mutex khi nhiều trường liên quan phải thay đổi nhất quán. Python cũng cần cơ chế đồng bộ phù hợp cho trạng thái chia sẻ trong chương trình đa luồng và không được suy ra an toàn toàn diện chỉ từ chi tiết triển khai một interpreter.

**Aliasing và đồng bộ là hai khía cạnh khác nhau**: aliasing xác định **đối tượng nào có thể bị ảnh hưởng**, còn đồng bộ xác định **khi nào và bằng cách nào các thao tác đồng thời được quan sát hợp lệ**.

## 13. Chi phí thời gian và bộ nhớ khi có aliasing

Đặt `n` là số phần tử và giả sử một giá trị phần tử có kích thước cố định:

| Tác vụ | Chi phí điển hình | Lưu ý |
| --- | --- | --- |
| Tạo thêm một biến tham chiếu/con trỏ tới đối tượng đã biết | O(1) thời gian, O(1) metadata | Đối tượng đích vẫn dùng chung |
| Sửa trường của đối tượng đã định vị | O(1) với trường đơn giản | Mọi alias có quyền đọc có thể thấy thay đổi |
| Tìm nút theo giá trị trong danh sách liên kết đơn | O(n) | Phải tính bước tìm trước khi sửa nút |
| Sao chép mảng `n` phần tử thành vùng độc lập | O(n) thời gian và O(n) vùng mới | Độc lập ở mức phần tử đã sao chép |
| Phát hiện nút dùng chung trong đồ thị | Phụ thuộc cách duyệt/đánh dấu; thường cần theo quy mô V, E | Phải phân biệt cùng ID với cùng đối tượng |
| Path copying trên cây cân bằng bất biến | Thường O(log n) nút mới trên một đường cập nhật | Cần đúng bất biến cân bằng và chính sách chia sẻ |
| COW toàn mảng, lần ghi cần tách bản | Có thể O(n) thời gian và vùng mới | Tạo alias/snapshot ban đầu có thể O(1) |
| Thêm đồng bộ khi nhiều luồng cùng sửa | Phụ thuộc contention và thiết kế | Không thể suy ra từ số alias đơn thuần |

**O(1) là bậc chi phí thao tác, không phải bảo đảm nhanh tuyệt đối.** Một phép ghi trường qua con trỏ có thể phải chờ cache line, gây cache coherence hoặc kéo theo cập nhật metadata ở cấu trúc khác. Ngược lại, sao chép một dãy liên tiếp O(n) có thể được thực hiện rất hiệu quả ở mức bộ nhớ. Quyết định thiết kế cần xét cả workload, quyền sở hữu và bất biến.

## 14. Phương pháp dự đoán tác động của một mutation

Khi được hỏi “dòng lệnh này thay đổi những gì?”, hãy đi theo quy trình:

1. **Liệt kê các đối tượng và đường tham chiếu.** Vẽ hộp cho đối tượng, mũi tên cho tên biến, ô container hoặc trường liên kết.
2. **Định vị đúng đối tượng được ghi.** `x = new_value` thường đổi ràng buộc của tên; `x.field = value` ghi trường của đối tượng `x` trỏ tới; `*p = value` ghi đối tượng do `p` chỉ đến.
3. **Đánh dấu tất cả đường có thể tới vùng được ghi.** Kể cả đường lồng nhau, view vùng chồng lấn, các gốc cây/đồ thị dùng chung nút.
4. **Xác định bất biến phụ thuộc vùng đó.** Ví dụ `size`/`tail` danh sách, thứ tự BST/heap, hash/equality của khóa, tập đỉnh đã thăm hoặc hiệu lực iterator.
5. **Kiểm tra vòng đời và quyền sửa.** Con trỏ còn hợp lệ? Nút còn sống? API có cho phép ghi? Có phiên bản bất biến cần giữ lại?
6. **Nếu nhiều luồng**, xác định đồng bộ hợp lệ trước khi suy luận về thời điểm quan sát.
7. **Cộng chi phí định vị và duy trì bất biến** vào chi phí phép ghi. Ghi một trường O(1) không có nghĩa thao tác nghiệp vụ tổng thể O(1).

### 14.1. Ví dụ phân tích nhanh

```python
item = {"score": 1}
a = [item]
b = [item]

b[0]["score"] = 7
b[0] = {"score": 9}
```

- Sau dòng ghi đầu: đối tượng `item` có `score = 7`; `a[0]["score"]` và `b[0]["score"]` cùng trả `7`.
- Sau dòng thứ hai: ô `b[0]` trỏ sang một dict mới; `a[0]` vẫn trỏ `item` với `score = 7`.
- Kết quả: `a[0]["score"] == 7`, `b[0]["score"] == 9`. Hai container vốn riêng, chỉ phần tử ban đầu mới dùng chung.

## 15. Bài tập có lời giải

### Bài 1. Biến danh sách là bí danh hay bản sao?

```python
a = [1, 2]
b = a
c = a.copy()
b.append(3)
c[0] = 9
print(a, b, c)
```

**Đáp án:** `a` và `b` cùng là `[1, 2, 3]`; `c` là `[9, 2]`. `b` là alias tới list `a`, còn `c` là container nông mới; với số nguyên bất biến, thay ô của `c` không tác động đến `a`.

### Bài 2. Một container ngoài mới có đảm bảo độc lập sâu?

```python
a = [[1], [2]]
b = a[:]
b[0].append(9)
b[1] = [7]
print(a)
```

**Đáp án:** `[[1, 9], [2]]`. List con đầu vẫn được chia sẻ; việc thay ô `b[1]` chỉ đổi container `b`.

### Bài 3. Đọc giá trị qua hai con trỏ C

```c
int number = 4;
int *p = &number;
int *q = p;
*q = 12;
q = NULL;
```

**Đáp án:** `number == 12` và `*p == 12`; `q == NULL`. Dòng cuối chỉ thay bản sao giá trị con trỏ `q`, không sửa `p` hay đối tượng `number`.

### Bài 4. Alias trong danh sách liên kết

Danh sách A: `1 -> 3 -> 5` và B: `2 -> 3 -> 5` cùng dùng chung **chính các nút** `3` và `5`. Nếu sửa `node3.next = NULL`, A và B trở thành gì?

**Đáp án:** A trở thành `1 -> 3`, B trở thành `2 -> 3`. Trường `next` của một nút dùng chung quyết định đường đi từ cả hai gốc. Nếu A/B có metadata `size` hoặc `tail`, các giá trị đó cần được kiểm tra/cập nhật theo hợp đồng; chỉ sửa metadata của A có thể làm B sai.

### Bài 5. Thay con trỏ đầu khác với thay nút

Cùng hai danh sách trên, nếu chỉ thực hiện `headB = headB->next` (giả sử các con trỏ hợp lệ), đường từ A có đổi không?

**Đáp án:** **Không.** Phép gán đổi riêng giá trị biến `headB`, không sửa bất kỳ trường `next` nào của các nút. B lúc này bắt đầu ở nút `3`, còn A vẫn bắt đầu ở `1`.

### Bài 6. Sửa khóa hash

Một đối tượng làm khóa bảng băm có `hashCode` phụ thuộc trường `id`. Sau khi chèn, bên khác giữ tham chiếu tới đối tượng và sửa `id`. Điều gì có thể xảy ra?

**Đáp án:** Mục đang được đặt theo hash/equality cũ nhưng tra cứu có thể tính hash/equality mới, gây kết quả không mong muốn. Dùng khóa bất biến hoặc cập nhật bằng cách xóa/chèn lại có kiểm soát. Không phải mọi lần sửa dữ liệu của **giá trị** trong bảng băm đều gây lỗi này; vấn đề là sửa thuộc tính quyết định **khóa**.

### Bài 7. BST bị phá bất biến

BST có gốc `20`, con trái `10` và con phải `30`. Một alias sửa khóa nút trái từ `10` thành `40`. Tìm `40` bằng quy tắc BST có đảm bảo thấy nút đó không?

**Đáp án:** **Không.** Khi so với `20`, thuật toán có thể đi sang phải, trong khi nút `40` thực tế nằm bên trái. Thay khóa phải qua thao tác duy trì thứ tự cây.

### Bài 8. View và vùng gốc

Một view chỉ mượn vùng dữ liệu của mảng động. Mảng được cấp phát lại, view vẫn giữ đường tới vùng cũ. Có thể tiếp tục dùng view không?

**Đáp án:** Thông thường **không** nếu thao tác cấp phát lại làm view/con trỏ tới vùng cũ mất hiệu lực. Phải tạo lại view tới vùng mới hoặc dùng cách quản lý ổn định địa chỉ phù hợp.

### Bài 9. Hai luồng sửa cùng đối tượng

Hai luồng cùng giữ tham chiếu tới một biến `counter` và cùng tăng nó. Việc chúng trỏ đúng cùng một đối tượng có đảm bảo kết quả cuối cùng chính xác không?

**Đáp án:** **Không.** Phải áp dụng đồng bộ/atomic phù hợp với ngôn ngữ và thao tác. Alias chỉ xác định đối tượng dùng chung; nó không tự tạo ra tính nguyên tử hoặc quan hệ happens-before.

### Bài 10. Tính chi phí tổng thể

Trong danh sách liên kết đơn `n` nút, một hàm tìm nút chứa khóa `k` rồi đổi `value` thành `v`. Bước gán trường O(1). Độ phức tạp xấu nhất của toàn hàm là bao nhiêu?

**Đáp án:** **O(n)** vì phải duyệt để tìm nút; việc ghi trường chỉ là phần cuối O(1). Nếu đã có con trỏ hợp lệ tới nút, thao tác ghi một trường đơn giản là O(1), nhưng phải đảm bảo bất biến của cấu trúc không yêu cầu thêm bước sửa chữa.

## 16. Ghi nhớ để sử dụng

- **Bí danh tham chiếu** là nhiều đường truy cập có thể cùng đến một đối tượng/vùng lưu trữ. Cùng giá trị **không đồng nghĩa** cùng danh tính; hai view khác địa chỉ đầu vẫn có thể chồng lấn ở một phần dữ liệu.
- **Mutation** sửa trạng thái đối tượng nên có thể quan sát qua mọi alias hợp lệ; **rebinding** chỉ đổi một tên hoặc ô tham chiếu cụ thể.
- Trong cấu trúc dữ liệu, alias có thể làm thay đổi không chỉ **giá trị**, mà cả **liên kết, thứ tự, kích thước logic, khóa tra cứu và hiệu lực con trỏ/iterator**. Bất biến của tất cả đường sử dụng chung phải được duy trì.
- Chia sẻ dữ liệu tiết kiệm sao chép, nhưng đòi hỏi thiết kế quyền sở hữu, vòng đời và quyền ghi. Dữ liệu bất biến, bản sao phòng vệ, COW hoặc API thao tác có kiểm soát là những lựa chọn tùy tình huống.
- Hãy phân tích **đường truy cập, phép ghi và tác động đến các cấu trúc phụ thuộc**, sau đó mới cộng chi phí thời gian/bộ nhớ. Khi có nhiều luồng, cần bổ sung quy tắc đồng bộ của ngôn ngữ trước khi suy ra khả năng quan sát.
