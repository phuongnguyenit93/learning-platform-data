# Căn chỉnh, phần đệm và chi phí thông tin phụ của nút

Hai cấu trúc dữ liệu cùng chứa một triệu số nguyên có thể tiêu thụ lượng bộ nhớ rất khác nhau. Một mảng lưu trực tiếp số nguyên chỉ cần vùng chứa giá trị và phần quản lý của mảng. Một danh sách liên kết thường cần thêm con trỏ cho **mỗi nút**, đồng thời mỗi nút có thể có những byte không chứa dữ liệu do yêu cầu **căn chỉnh** (alignment) và **phần đệm** (padding). Việc cấp phát từng nút còn tạo chi phí quản lý và phân mảnh bộ nhớ.

Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, chương **Bộ nhớ và biểu diễn** đặt nền tảng để so sánh mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị theo **bất biến, thao tác, thời gian và bộ nhớ**. Bài này giải thích cách tính và đo chi phí của *biểu diễn nút*, phân biệt dữ liệu thực với thông tin phụ, rồi sử dụng kết quả để đưa ra lựa chọn cấu trúc dữ liệu.

## 1. Căn chỉnh là gì?

Mỗi đối tượng trong bộ nhớ có một kích thước và thường có **yêu cầu căn chỉnh**: địa chỉ bắt đầu của đối tượng cần phù hợp với ranh giới mà kiểu dữ liệu yêu cầu. Chẳng hạn, trong một môi trường minh họa, một đối tượng yêu cầu căn chỉnh 8 byte có thể bắt đầu ở các địa chỉ `0x1000`, `0x1008`, `0x1010`, … nhưng không bắt đầu ở `0x1003`.

```text
Địa chỉ (minh họa):
0x1000 0x1001 0x1002 0x1003 0x1004 0x1005 0x1006 0x1007
  |      |      |      |      |      |      |      |
  +------------------------------------------------+
  |             Một vùng gồm 8 byte                |
  +------------------------------------------------+
0x1008: ranh giới căn chỉnh 8 byte kế tiếp
```

Đây là ví dụ về **một yêu cầu căn chỉnh 8 byte**, không phải khẳng định mọi kiểu hay mọi máy đều yêu cầu căn chỉnh như vậy. Căn chỉnh thực tế phụ thuộc kiến trúc, kiểu, ABI, trình biên dịch và đôi khi các chỉ thị căn chỉnh đặc biệt.

Với một độ căn chỉnh `A` thông dụng, có thể hình dung địa chỉ bắt đầu như một bội số của `A`. Ta thường gặp quy tắc: `char` có căn chỉnh 1, `int` thường là 4, con trỏ thường là 8 trên hệ 64-bit; **không được lấy các con số phổ biến này làm quy tắc cố định của C**.

### 1.1. Vì sao cần căn chỉnh?

- Một số CPU hoặc lệnh chỉ hỗ trợ truy cập đối tượng đúng căn chỉnh; đọc dữ liệu không đúng yêu cầu có thể gây lỗi.
- Nhiều kiến trúc vẫn đọc được dữ liệu lệch căn chỉnh nhưng có thể cần thêm công việc, tùy vị trí và loại lệnh.
- Trình biên dịch dựa vào hợp đồng căn chỉnh của kiểu để sinh mã tối ưu và thực hiện các giả định hợp lệ về truy cập bộ nhớ.

Việc dereference một con trỏ tới `T` ở địa chỉ không đáp ứng yêu cầu căn chỉnh của `T` có thể dẫn đến **hành vi không xác định** trong C/C++; không nên chỉ dựa vào việc “máy mình vẫn chạy được”.

### 1.2. Đo căn chỉnh và kích thước thay vì đoán

Trong C11 trở lên, dùng `_Alignof(T)` để hỏi yêu cầu căn chỉnh và `sizeof(T)` để hỏi kích thước kiểu. Ví dụ hoàn chỉnh:

```c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("char:  size=%zu, align=%zu\n",
           sizeof(char), (size_t)_Alignof(char));
    printf("int:   size=%zu, align=%zu\n",
           sizeof(int), (size_t)_Alignof(int));
    printf("void*: size=%zu, align=%zu\n",
           sizeof(void *), (size_t)_Alignof(void *));
    printf("double: size=%zu, align=%zu\n",
           sizeof(double), (size_t)_Alignof(double));
    return 0;
}
```

Biên dịch với chế độ **C11** trở lên. Trong C++11 trở lên, từ khóa tương ứng là `alignof(T)`; cú pháp nêu trên minh họa C11. Kết quả đo là thông tin về **môi trường đang chạy**, không phải chứng minh giá trị nào cũng đúng trên mọi nền tảng.

## 2. Phần đệm trong một `struct` xuất hiện từ đâu?

**Phần đệm (padding)** là những byte có thể được trình biên dịch chèn vào bố cục của một cấu trúc để các trường đáp ứng yêu cầu căn chỉnh và để mỗi phần tử của một mảng `struct` tiếp tục được căn chỉnh đúng. Hai loại quan trọng:

1. **Phần đệm giữa các trường (internal padding)**: khoảng trống trước một trường cần bắt đầu tại ranh giới phù hợp.
2. **Phần đệm ở cuối cấu trúc (tail padding)**: khoảng trống sau trường cuối để kích thước mỗi `struct` phù hợp khi xếp các phần tử liên tiếp trong mảng.

Xét kiểu nút thường gặp:

```c
typedef struct Node {
    int value;
    struct Node *next;
} Node;
```

Trên **một ABI 64-bit điển hình** có `sizeof(int) == 4`, `sizeof(void *) == 8`, yêu cầu căn chỉnh của con trỏ là 8 và của `int` là 4, bố cục thường có dạng:

```text
struct Node, giả định địa chỉ đầu 0x1000
+----------------+----------------+--------------------------------+
| 0..3           | 4..7           | 8..15                          |
| value: int     | padding 4 byte | next: con trỏ 8 byte          |
+----------------+----------------+--------------------------------+
offset 0          offset 4         offset 8

sizeof(Node) thường bằng 16 byte; phần dữ liệu trường chỉ là 4 + 8 = 12 byte.
```

Trình biên dịch có thể chọn bố cục khác trên nền tảng khác. Ví dụ này chỉ giúp hiểu cơ chế, không khẳng định kích thước `Node` luôn là 16.

### 2.1. Phần đệm cuối giúp mảng nút giữ đúng căn chỉnh

Giả sử một `struct` cần căn chỉnh 8 byte và trường cuối kết thúc ở offset 13. Nếu `sizeof(struct)` chỉ bằng 13, phần tử thứ hai của mảng bắt đầu ngay 13 byte sau phần tử đầu và có thể sai ranh giới căn chỉnh. Vì vậy trình biên dịch thường làm tròn kích thước cấu trúc lên đến một bội phù hợp, ví dụ từ 13 thành 16 byte.

```text
Nếu sizeof(T) = 16, alignof(T) = 8:

Địa chỉ 0x1000                    Địa chỉ 0x1010
+-------------------------------+-------------------------------+
| T[0]: dữ liệu + padding       | T[1]: dữ liệu + padding       |
+-------------------------------+-------------------------------+
      16 byte giữa hai phần tử; mỗi phần tử bắt đầu đúng ranh giới.
```

Kích thước kiểu `sizeof(T)` **đã bao gồm phần đệm nội bộ và phần đệm cuối**. Vì vậy phép nhân `n * sizeof(T)` là cách tính đúng dung lượng vùng mảng có `n` phần tử kiểu `T` trong C (khi không tràn số nguyên), chứ không chỉ nhân tổng kích thước từng trường.

### 2.2. Đo chính xác vị trí các trường bằng `offsetof`

Thư viện `<stddef.h>` cung cấp `offsetof(Type, member)` để lấy độ lệch tính bằng byte của trường trong kiểu cấu trúc hợp lệ.

```c
#include <stddef.h>
#include <stdio.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

int main(void) {
    printf("sizeof(Node): %zu\n", sizeof(Node));
    printf("_Alignof(Node): %zu\n", (size_t)_Alignof(Node));
    printf("offset value: %zu\n", offsetof(Node, value));
    printf("offset next:  %zu\n", offsetof(Node, next));

    printf("size of fields: %zu\n",
           sizeof(((Node *)0)->value) +
           sizeof(((Node *)0)->next));
    return 0;
}
```

Trong biểu thức `sizeof(((Node *)0)->value)`, toán hạng có kiểu không biến đổi độ dài và **không được đánh giá** bởi chương trình ở thời gian chạy, vì vậy đây không phải thao tác giải tham chiếu con trỏ null để đọc dữ liệu. Cách viết này chỉ nhằm lấy kích thước kiểu trường; có thể thay bằng `sizeof(int) + sizeof(Node *)` cho ví dụ cụ thể.

Khi biết độ lệch, ta có thể kiểm tra phần đệm:

```text
Khoảng trước next  = offsetof(Node, next) - sizeof(int)
Khoảng cuối        = sizeof(Node) - (offsetof(Node, next) + sizeof(Node *))
Tổng phần đệm      = sizeof(Node) - (sizeof(int) + sizeof(Node *))
```

Các công thức trên **dành riêng cho bố cục `Node` gồm hai trường theo thứ tự đã nêu**, không phải công thức dùng nguyên xi cho mọi `struct`.

## 3. Thứ tự khai báo trường có thể thay đổi kích thước nút

C không tự sắp xếp lại thứ tự các trường thông thường của một `struct`: bố cục phải tuân theo thứ tự khai báo (dù có thể chèn phần đệm). Hai kiểu chứa **cùng ba trường** có thể có kích thước khác nhau:

```c
typedef struct NodeA {
    char tag;
    void *next;
    int value;
} NodeA;

typedef struct NodeB {
    void *next;
    int value;
    char tag;
} NodeB;
```

Giả sử `char = 1` byte/căn chỉnh 1, `int = 4` byte/căn chỉnh 4, `void * = 8` byte/căn chỉnh 8:

```text
NodeA: sizeof thường là 24 byte
offset:  0      1..7        8..15         16..19       20..23
         +-----+-----------+-------------+------------+--------+
         | tag | padding 7 | next: ptr 8 | value: 4   | pad 4  |
         +-----+-----------+-------------+------------+--------+

NodeB: sizeof thường là 16 byte
offset:  0..7           8..11       12        13..15
         +--------------+-----------+---------+--------+
         | next: ptr 8  | value: 4  | tag: 1  | pad 3  |
         +--------------+-----------+---------+--------+
```

| Chỉ tiêu theo giả định trên | `NodeA` | `NodeB` |
| --- | ---: | ---: |
| Kích thước trường có ý nghĩa: `1 + 8 + 4` | 13 byte | 13 byte |
| Phần đệm (gồm nội bộ và cuối) | 11 byte | 3 byte |
| Tổng `sizeof` | **24 byte** | **16 byte** |
| Với 1.000.000 nút (chỉ tính `sizeof`) | 24 MB | 16 MB |

Ở đây MB là **megabyte thập phân** (`1 MB = 1.000.000 byte`). Chênh lệch 8 MB chỉ từ thứ tự trường, trước khi tính chi phí cấp phát từng nút.

**Quy tắc kinh nghiệm:** khi không có ràng buộc tương thích ABI hoặc định dạng nhị phân, thử nhóm các trường có yêu cầu căn chỉnh lớn lại với nhau để giảm khoảng trống. Đây là cách *thường giúp ích*, không bảo đảm luôn tối ưu trên mọi nền tảng; hãy đo `sizeof`, `_Alignof`, `offsetof` của môi trường đích.

Không thay đổi thứ tự trường tùy tiện nếu kiểu đã được dùng trong giao diện nhị phân (ABI), dữ liệu lưu trên đĩa, trao đổi với phần cứng hoặc thư viện phụ thuộc bố cục. Thay đổi bố cục có thể phá vỡ tính tương thích dù chương trình vẫn biên dịch.

## 4. Chi phí thông tin phụ (metadata) của nút

Một nút không chỉ có phần dữ liệu nghiệp vụ (payload). Nó có thể cần **thông tin phụ để cấu trúc vận hành**, chẳng hạn con trỏ, độ dài, trạng thái, màu của nút cây cân bằng, cờ đánh dấu hoặc thông tin về quyền sở hữu.

Ví dụ so sánh:

```c
/* Danh sách liên kết đơn: một liên kết ở mỗi nút. */
typedef struct SNode {
    int value;
    struct SNode *next;
} SNode;

/* Danh sách liên kết đôi: hai liên kết ở mỗi nút. */
typedef struct DNode {
    int value;
    struct DNode *prev;
    struct DNode *next;
} DNode;

/* Cây nhị phân có thông tin phụ về chiều cao. */
typedef struct TreeNode {
    int key;
    int height;
    struct TreeNode *left;
    struct TreeNode *right;
} TreeNode;
```

Trên ABI 64-bit minh họa ở trên:

| Kiểu | Phần dữ liệu chính | Thông tin phụ trong trường | `sizeof` thường gặp |
| --- | --- | --- | ---: |
| `SNode` | `value`: 4 byte | `next`: 8 byte | 16 byte |
| `DNode` | `value`: 4 byte | `prev` và `next`: 16 byte | 24 byte |
| `TreeNode` | `key`: 4 byte | `height`: 4 byte; `left`, `right`: 16 byte | 24 byte |

Một `DNode` với payload 4 byte có thể dùng 24 byte trong chính `struct`, tức **gấp sáu lần payload**. Không nên kết luận danh sách đôi luôn tốn hơn mọi lựa chọn khác: nó cho phép biết nút trước ngay tại nút đang xét, nhờ đó có thể xóa/chèn bằng số bước liên kết hằng số khi đã có vị trí thích hợp.

### 4.1. Metadata của toàn cấu trúc khác metadata của từng nút

Ngoài từng nút, container còn có thể giữ:

```c
typedef struct LinkedList {
    SNode *head;
    SNode *tail;
    size_t size;
} LinkedList;
```

Nếu `size_t` và con trỏ đều 8 byte, phần container trên thường chiếm 24 byte, **một lần cho toàn danh sách**. Trái lại, `SNode.next` chiếm dung lượng **cho mỗi nút**. Với `n` phần tử, mô hình dung lượng:

```text
Bộ nhớ lưu trữ của danh sách ≈ sizeof(LinkedList)
                          + n × sizeof(SNode)
                          + phí cấp phát và phân mảnh của n nút
```

Nếu `LinkedList` được cấp phát riêng, đối tượng container còn có thể chịu thêm chi phí allocator. Công thức cố ý tách metadata theo **mỗi cấu trúc** và **mỗi phần tử**; tránh cộng hai lần khi `sizeof(SNode)` đã chứa padding và con trỏ.

### 4.2. Nút canh gác và trường đánh dấu

Một số hiện thực dùng **nút canh gác (sentinel/dummy node)** để đơn giản hóa cập nhật đầu/cuối hoặc giữ riêng một con trỏ `tail`. Nút canh gác có thể tiêu tốn thêm một nút dù không chứa phần tử nghiệp vụ. Nếu có `n` phần tử và `s` nút canh gác thực sự được cấp phát, chi phí của các nút theo kiểu `Node` xấp xỉ `(n + s) * sizeof(Node)`, cộng phí cấp phát.

Các cấu trúc như cây đỏ–đen có thể cần **cờ màu**, cây AVL có thể cần chiều cao hoặc độ cân bằng, hash table có thể cần trạng thái ô trống/đã xóa, đồ thị có thể cần nhãn hoặc dữ liệu cạnh. Không phải metadata nào cũng là **một byte tăng thêm**: cờ 1 byte có thể nằm trong padding sẵn có, hoặc có thể khiến `sizeof` tăng nguyên một mức căn chỉnh.

Vì vậy khi muốn biết việc thêm một trường `bool` có làm nút lớn lên không, **hãy đo `sizeof` trước và sau**, đừng chỉ cộng số byte của trường.

## 5. Phí cấp phát: `sizeof(Node)` chưa phải toàn bộ dung lượng

`malloc(sizeof(Node))` yêu cầu một vùng cho ít nhất một nút, nhưng **kích thước vùng yêu cầu không phải lúc nào cũng là lượng RAM thực mà allocator tiêu thụ**. Bộ cấp phát có thể dùng:

- Metadata quản lý khối cấp phát và các ô đánh dấu trạng thái.
- Phân lớp kích thước, làm tròn yêu cầu (ví dụ từ một số byte lên mức lớn hơn).
- Khoảng trống do các khối đang sống xen kẽ các khối đã giải phóng (**phân mảnh ngoài**).
- Các vùng dữ liệu quản lý tập trung, cache của allocator hoặc trang bộ nhớ chưa trả về hệ điều hành.

Những khoản này phụ thuộc allocator, môi trường chạy và lịch sử cấp phát. Không có một con số cố định kiểu “`malloc` luôn cộng 8 byte cho mỗi nút”.

Ta có thể hình dung gần đúng:

\[
M_{\text{linked}} \approx M_{\text{container}} + n\,\operatorname{sizeof}(Node)
+ M_{\text{allocator}} + M_{\text{fragmentation}}.
\]

Công thức chỉ là **mô hình kế toán**, không có nghĩa các khoản có thể đo độc lập dễ dàng trong mọi allocator. Đặc biệt, một số metadata quản lý và nội bộ allocator đã có thể nằm trong phần dung lượng sử dụng thực tế mà công cụ đo cấp phát báo cáo; cần xác định cách công cụ tính để không cộng trùng.

### 5.1. Ví dụ với một triệu số nguyên

Giả định nền tảng có `sizeof(int) = 4`, `sizeof(SNode) = 16`, một triệu phần tử, chưa tính thông tin toàn container:

| Biểu diễn | Công thức | Dung lượng phần tử/nút |
| --- | --- | ---: |
| Mảng `int` đủ đúng một triệu ô | `1.000.000 × 4` | **4 MB** |
| Mảng động `int` có capacity 1,5 triệu | `1.500.000 × 4` | **6 MB** |
| Danh sách liên kết đơn `SNode` | `1.000.000 × 16` | **16 MB** |
| Danh sách liên kết đôi `DNode` | `1.000.000 × 24` | **24 MB** |

Các con số là **chi phí vùng phần tử/nút theo kiểu dữ liệu**, chưa gồm allocator, các cấu trúc quản lý, đối tượng bên ngoài và bản sao dữ liệu tạm thời. Đối với danh sách liên kết cấp phát từng nút, tổng thực tế **có thể cao hơn** đáng kể 16 MB hoặc 24 MB. Với mảng động, `capacity` lớn hơn `size` là lựa chọn cân đối: tốn thêm bộ nhớ dự phòng để giảm số lần di chuyển/cấp phát khi thêm phần tử.

Lưu ý với **mảng chứa con trỏ hoặc tham chiếu** (ví dụ mảng con trỏ tới đối tượng): vùng liên tiếp chứa các *liên kết*, còn vùng lưu các đối tượng đích phải được tính **riêng**. So sánh công bằng phải tính cùng một mức dữ liệu nghiệp vụ.

### 5.2. Metadata của runtime trong ngôn ngữ cấp cao

Trong Java, Python và các runtime tương tự, một “nút” cài đặt bằng **đối tượng** còn có thể mang header đối tượng, thông tin quản lý bộ nhớ, căn chỉnh, và tham chiếu tới các đối tượng chứa giá trị. Chẳng hạn, một đối tượng lưu số nguyên theo cách đóng hộp (boxing) không nhất thiết có kích thước bằng một `int` nguyên thủy trong mảng.

Do đó, công thức `sizeof(struct C)` không áp dụng trực tiếp để suy ra kích thước một đối tượng Python hay Java. Cần dùng công cụ đo phù hợp runtime, xem khả năng nén con trỏ, cấu hình VM và cách triển khai loại container. Không mặc định “Python list là mảng các đối tượng Python nằm liền nhau”: phần tử list thường là các tham chiếu trong vùng chứa liên tiếp, trong khi đối tượng được tham chiếu có thể nằm nơi khác.

## 6. Căn chỉnh, phân mảnh và hiệu năng truy cập

**Căn chỉnh** giúp mỗi đối tượng được truy cập hợp lệ và có thể hiệu quả hơn. **Padding** đổi thêm dung lượng lấy bố cục đáp ứng căn chỉnh. **Phân mảnh** phát sinh từ cách cấp phát và thu hồi vùng nhớ theo thời gian. Ba khái niệm liên quan nhưng không đồng nhất.

Giả sử CPU sử dụng cache line 64 byte (kích thước chỉ để minh họa). Nếu có một mảng `int` 4 byte nằm liên tiếp, một dòng cache có thể chứa dữ liệu của nhiều phần tử gần nhau. Với các nút 16 hoặc 24 byte cấp phát rời rạc, mỗi lần đọc `next` có thể buộc CPU theo một địa chỉ mới, đôi lúc phải tải thêm cache line hoặc trang bộ nhớ.

```text
Mảng giá trị liên tiếp: [4][4][4][4][4][4] ...   (dữ liệu sát nhau)
Danh sách nút:          [Node A] ----> [Node B] ----> [Node C]
                        vị trí 1      vị trí 2      vị trí 3
                        (các vị trí không bắt buộc liền kề)
```

Vì thế hai thuật toán duyệt đều **O(n)** vẫn có thể khác tốc độ lớn. Các nguyên nhân gồm:

- **Tính cục bộ không gian (spatial locality):** truy cập phần tử kế tiếp gần phần tử vừa đọc.
- **Đọc trước (prefetch):** CPU dễ dự đoán luồng truy cập tuần tự hơn một chuỗi con trỏ phụ thuộc dữ liệu.
- **Mật độ dữ liệu hữu ích:** nếu nút 24 byte chỉ chứa giá trị 4 byte, phần lớn dung lượng mang theo trong cache không phải payload cần xử lý.
- **Số trang nhớ được chạm đến:** các nút phân tán có thể tăng áp lực lên hệ thống quản lý ánh xạ địa chỉ (TLB).

Chèn vào giữa danh sách liên kết có thể chỉ cần **O(1) lần sửa liên kết** *khi đã có nút liên quan*, nhưng **tìm** nút để chèn có thể cần O(n). Mảng có thể phải dịch O(n) phần tử, song việc sao chép dữ liệu liên tiếp thường được tối ưu tốt. Không nên lựa chọn chỉ dựa vào một ô trong bảng Big-O.

## 7. Cách giảm chi phí thông tin phụ

Các kỹ thuật giảm dung lượng đều có **điều kiện áp dụng** và **đánh đổi**.

### 7.1. Sắp xếp lại các trường

Nhóm các trường có căn chỉnh lớn và đo lại `sizeof` thường giúp giảm phần đệm. Đây thường là bước đơn giản khi ta kiểm soát định nghĩa kiểu và không có ràng buộc ABI/serialization.

### 7.2. Dùng mảng hoặc nhóm nút trong một khối

**Object pool / arena allocator** cấp phát nhiều nút từ một hoặc vài khối lớn. Nó có thể giảm chi phí gọi allocator từng nút, giảm metadata trên mỗi lần cấp phát và cải thiện vị trí tương đối của các nút. Tuy vậy, nút vẫn cần `next`/`prev` nếu thuật toán dựa trên liên kết; pool không tự làm mất nhu cầu metadata.

Pool còn phải quản lý danh sách ô rảnh, vòng đời, cơ chế thu hồi và những khối còn được tham chiếu. Bộ nhớ dự phòng lớn có thể làm tăng dung lượng giữ lại nếu số nút sử dụng thấp.

### 7.3. Dùng chỉ số thay vì con trỏ

Khi tất cả nút được lưu trong mảng và số nút có giới hạn, có thể thay con trỏ `next` bằng **chỉ số**:

```c
#include <stdint.h>

typedef struct IndexedNode {
    int value;
    uint32_t next_index; /* Chỉ số nút kế tiếp, hoặc giá trị sentinel. */
} IndexedNode;
```

Giả sử `int` và `uint32_t` đều 4 byte, `IndexedNode` có thể chiếm 8 byte thay vì 16 byte ở `SNode` trên môi trường minh họa. Một quy ước như `UINT32_MAX` có thể biểu diễn “không có nút kế tiếp” nếu không dùng giá trị này làm chỉ số thật. Để dùng `uint32_t`, nền tảng phải cung cấp kiểu đó; giới hạn số phần tử và quy tắc quản lý chỉ số cần được thiết kế rõ.

Kỹ thuật chỉ số đặt ra trách nhiệm khác: xác định chỉ số hợp lệ, theo dõi ô trống khi xóa, xử lý cấp phát lại mảng, và tránh tái sử dụng chỉ số cũ trong khi nơi khác vẫn đang giữ nó. Nếu thay đổi thứ tự phần tử trong mảng, có thể phải cập nhật các chỉ số liên kết.

### 7.4. Lưu cấu trúc bằng vùng liên tiếp

Một **binary heap** thường đặt phần tử trong mảng và dùng công thức chỉ số cha/con thay cho hai trường con trỏ:

```text
Với chỉ số gốc 0:
con trái của i   = 2*i + 1
con phải của i   = 2*i + 2
cha của i > 0    = (i - 1) / 2  (chia nguyên)
```

Cần kiểm tra chỉ số nằm trong phạm vi mảng và tránh tràn số nguyên khi tính toán với chỉ số lớn. Cách biểu diễn mảng đặc biệt hiệu quả cho cây nhị phân *đầy theo thứ tự mức* của heap, vì không cần lưu các liên kết riêng.

Đối với **đồ thị**, danh sách kề lưu trong mảng các chỉ số (hoặc biểu diễn CSR: mảng độ lệch và mảng đỉnh kề) có thể tránh chi phí một đối tượng/nút cấp phát riêng cho mỗi cạnh. Cách lựa chọn phụ thuộc việc đồ thị có thay đổi thường xuyên hay không, yêu cầu truy xuất láng giềng và mức độ cần giữ định danh đỉnh ổn định.

### 7.5. Lưu thông tin trạng thái bằng bit nếu phù hợp

Một cờ chỉ có hai giá trị về mặt thông tin cần một bit, nhưng khai báo thêm trường `bool` không bảo đảm `sizeof(Node)` chỉ tăng 1 bit. Bit field hoặc bitmap ngoài có thể lưu nhiều cờ với mật độ cao hơn. Đổi lại phải cân nhắc tính di động của bố cục bit field, chi phí thao tác bit và tính an toàn khi nhiều luồng đồng thời cập nhật.

### 7.6. Nút “nội tại” (intrusive) và nút bọc (non-intrusive)

Một container **intrusive** đặt trường liên kết trực tiếp trong đối tượng nghiệp vụ. Container kiểu **non-intrusive** thường tạo một nút bọc giữ giá trị hoặc tham chiếu đến giá trị đó. Intrusive có thể tránh một lớp đối tượng và một lần cấp phát, nhưng buộc đối tượng tham gia theo hợp đồng vòng đời và liên kết của container; một đối tượng tham gia nhiều danh sách có thể cần nhiều bộ liên kết.

Tối ưu biểu diễn cần xét **toàn bộ vòng đời đối tượng**, không chỉ byte mà một nút trông như đang chiếm.

## 8. Có nên ép đóng gói `struct` để bỏ padding?

Một số trình biên dịch cung cấp `#pragma pack` hoặc thuộc tính `packed` để thay đổi bố cục và giảm khoảng đệm. Các cơ chế này **không phải một giao diện C/C++ di động dùng giống nhau trên mọi trình biên dịch**.

Giả sử muốn giảm `sizeof(Node)` từ 16 về gần 12 bằng cách bỏ 4 byte đệm giữa `int` và con trỏ. Khi đó trường con trỏ có thể ở địa chỉ **không đáp ứng căn chỉnh thông thường**; việc truy cập có thể chậm, gây lỗi trên kiến trúc yêu cầu căn chỉnh, hoặc cần mã xử lý đặc biệt do trình biên dịch sinh. Không được tự tạo một `Node *` tới vùng byte lệch căn chỉnh rồi giải tham chiếu như thể đó là đối tượng `Node` hợp lệ.

**Không nên mặc định `packed` là tối ưu.** Với cấu trúc dữ liệu thường xuyên xử lý trực tiếp trong RAM, bố cục tự nhiên thường đáng tin cậy và dễ tối ưu hơn. Nếu đọc/ghi định dạng byte cố định từ file hoặc giao thức mạng, nên mô tả rõ định dạng, kích thước và thứ tự byte (endianness), rồi dùng các thao tác chuyển đổi/`memcpy` phù hợp. Không được coi bố cục một `struct` trong bộ nhớ luôn là định dạng file hay định dạng truyền qua mạng.

## 9. Cách đánh giá bộ nhớ của một cấu trúc dữ liệu

Muốn ước lượng công bằng, hãy xác định rõ *đơn vị phải chứa* và *nơi lưu metadata*.

1. **Payload:** mỗi phần tử thực sự phải chứa dữ liệu gì, kích thước hoặc cách tham chiếu tới dữ liệu ấy?
2. **Metadata mỗi phần tử:** con trỏ `next`, `prev`, `left`, `right`, cờ, chiều cao, hash cache, chỉ số, độ dài…
3. **Padding mỗi phần tử:** lấy `sizeof(Node)` đã bao gồm các byte chèn; dùng `offsetof` để giải thích khi cần.
4. **Metadata toàn container:** `head`, `tail`, `size`, `capacity`, bảng bucket và các mảng phụ khác.
5. **Bộ cấp phát:** n lần cấp phát riêng, hay một mảng/một pool; overhead và phân mảnh của từng chiến lược.
6. **Dung lượng dự phòng:** ô chưa sử dụng trong mảng động, bucket chưa dùng trong bảng băm, nút tự do trong pool, ô dấu xóa…
7. **Thao tác chủ đạo:** duyệt, truy cập ngẫu nhiên, tìm kiếm, chèn/xóa, tính ổn định của địa chỉ và yêu cầu bộ nhớ tối đa.

Một số công thức gần đúng hữu dụng:

```text
Mảng giá trị kiểu T:
  Bộ nhớ phần tử = capacity × sizeof(T)

Danh sách cấp phát riêng:
  Bộ nhớ nút       = n × sizeof(Node)
  Tổng gần đúng    = Bộ nhớ nút + quản lý container + allocator + phân mảnh

Bảng băm móc xích:
  Tổng gần đúng    = vùng các bucket + n × sizeof(nút bảng băm)
                   + phí cấp phát và các thành phần liên quan
```

`capacity` là số ô **đã cấp chỗ**, `n` là số phần tử **đang dùng**. Đối với bảng băm, còn phải xét hệ số tải, số bucket và chính sách tái băm. Đối với chương trình có nhiều cấu trúc trỏ chung một đối tượng, hãy tính bộ nhớ đối tượng đó **một lần**, tránh cộng lặp qua các liên kết.

### 9.1. Thí nghiệm gợi ý với C

Đo trực tiếp `sizeof`, `_Alignof`, `offsetof` cho ba kiểu trên:

```c
#include <stddef.h>
#include <stdio.h>

typedef struct NodeA {
    char tag;
    void *next;
    int value;
} NodeA;

typedef struct NodeB {
    void *next;
    int value;
    char tag;
} NodeB;

typedef struct SingleNode {
    int value;
    struct SingleNode *next;
} SingleNode;

int main(void) {
    printf("NodeA: size=%zu, align=%zu, tag=%zu, next=%zu, value=%zu\n",
           sizeof(NodeA), (size_t)_Alignof(NodeA),
           offsetof(NodeA, tag), offsetof(NodeA, next),
           offsetof(NodeA, value));
    printf("NodeB: size=%zu, align=%zu, tag=%zu, next=%zu, value=%zu\n",
           sizeof(NodeB), (size_t)_Alignof(NodeB),
           offsetof(NodeB, tag), offsetof(NodeB, next),
           offsetof(NodeB, value));
    printf("SingleNode: size=%zu, align=%zu, value=%zu, next=%zu\n",
           sizeof(SingleNode), (size_t)_Alignof(SingleNode),
           offsetof(SingleNode, value), offsetof(SingleNode, next));
    return 0;
}
```

Hãy đối chiếu kết quả máy thật với sơ đồ trong bài. Nếu khác giả định minh họa, **kết quả thực tế theo ABI của môi trường đang biên dịch** mới là cơ sở để tính dung lượng trên môi trường đó. `sizeof` chỉ đo kích thước **đối tượng của kiểu**, không tự đo metadata bên trong allocator hay dung lượng thường trú (resident memory) của toàn tiến trình.

Để đánh giá ảnh hưởng tới thời gian, có thể thiết kế benchmark duyệt tuần tự mảng và danh sách liên kết có cùng dữ liệu, dùng nhiều kích thước `n`, lặp đủ lần, giảm tác động tối ưu loại bỏ tính toán, rồi so sánh. Không suy ra một kết luận về hiệu năng từ một lần chạy hay chỉ từ Big-O.

## 10. Các hiểu lầm phổ biến

**“`sizeof(struct)` bằng tổng `sizeof` các trường.”** Không nhất thiết. Trình biên dịch có thể thêm padding giữa các trường và ở cuối.

**“`sizeof(Node)` cho toàn bộ bộ nhớ thực cấp cho một nút.”** Nó cho kích thước đối tượng của kiểu; cấp phát động có thể có phí quản lý, làm tròn kích thước và phân mảnh.

**“Cứ thêm trường 1 byte là cấu trúc chỉ tăng 1 byte.”** Một trường mới có thể nằm vừa trong padding cũ, hoặc đẩy toàn cấu trúc sang một kích thước lớn hơn do căn chỉnh.

**“Con trỏ luôn là 8 byte.”** Đó là tình huống phổ biến trên nhiều hệ 64-bit, không phải bảo đảm chung của ngôn ngữ C/C++.

**“Nút liên kết O(1) khi chèn nên luôn rẻ hơn mảng.”** Nếu phải duyệt đến vị trí chèn trước, tổng thời gian có thể O(n), trong khi nút tốn thêm con trỏ và chi phí cấp phát.

**“Giảm padding bằng `packed` luôn làm chương trình nhanh hơn.”** Bố cục đóng gói có thể gây truy cập không đúng căn chỉnh hoặc tăng chi phí truy cập; còn phụ thuộc phần cứng và trình biên dịch.

**“Bộ gom rác xóa hết chi phí metadata.”** GC quản lý vòng đời đối tượng, không khiến header, tham chiếu, căn chỉnh hay chi phí truy cập gián tiếp biến mất.

## 11. Bài tập vận dụng có lời giải

### Bài 1. Tính padding từ bố cục giả định

Một kiểu có `char flag` ở offset 0, `int count` ở offset 4, `void *next` ở offset 8, tổng `sizeof = 16`; `char = 1`, `int = 4`, con trỏ = 8 byte. Bao nhiêu byte padding?

**Lời giải:** tổng kích thước trường là `1 + 4 + 8 = 13` byte. Padding là `16 - 13 = 3` byte, nằm giữa `flag` và `count`. Đây là kết quả dưới giả định đã cho.

### Bài 2. Vì sao một nút chỉ chứa `int` vẫn tốn 16 byte?

Giả sử `int` 4 byte và `next` 8 byte, căn chỉnh con trỏ là 8, `sizeof(SNode) = 16`.

**Lời giải:** 4 byte cho `value`, 8 byte cho `next`, 4 byte padding để `next` bắt đầu đúng ranh giới. Dữ liệu nghiệp vụ chiếm 4/16 = **25%** kích thước `struct`; chưa tính bộ cấp phát.

### Bài 3. Tính phần lớn bộ nhớ khi nhân rộng

Theo giả định `NodeA = 24` byte, `NodeB = 16` byte, có 250.000 nút. Sắp xếp lại trường tiết kiệm bao nhiêu byte trong vùng nút?

**Lời giải:** `250.000 × (24 - 16) = 2.000.000` byte, tức **2 MB thập phân**. Chênh lệch phí cấp phát nếu allocator thay đổi lớp kích thước có thể làm kết quả tổng thực tế khác.

### Bài 4. So sánh mảng động và danh sách liên kết

Một mảng `int` có `size = 800.000`, `capacity = 1.000.000`, `sizeof(int) = 4`. Một danh sách với cùng 800.000 giá trị có `sizeof(Node) = 16`. Chỉ tính vùng lưu phần tử/nút, mỗi cấu trúc chiếm bao nhiêu?

**Lời giải:** mảng là `1.000.000 × 4 = 4.000.000` byte, danh sách là `800.000 × 16 = 12.800.000` byte. Danh sách có chi phí bộ cấp phát và container riêng chưa tính; mảng có 200.000 ô dự phòng đã tính trong `capacity`.

### Bài 5. Chọn cấu trúc và giải thích trade-off

Cần một cấu trúc quản lý một triệu phần tử nhỏ, chủ yếu duyệt tuần tự, thỉnh thoảng thêm phần tử ở cuối. Có cần dùng danh sách liên kết vì “thêm cuối O(1)”?

**Lời giải:** **Không nhất thiết.** Mảng động thường phù hợp vì truy cập tuần tự có tính cục bộ dữ liệu tốt, ít metadata mỗi phần tử và thêm cuối **O(1) trung bình dồn tích** khi chính sách tăng dung lượng phù hợp. Nếu cần giữ địa chỉ từng nút ổn định khi thêm/xóa, hoặc thường xuyên nối/tách nút đã xác định, một cấu trúc liên kết có thể hợp lý. Phải xác định yêu cầu thao tác và đo trên dữ liệu thật.

## 12. Ghi nhớ để lựa chọn biểu diễn

- **Alignment** quy định yêu cầu bố trí địa chỉ hợp lệ cho kiểu; **padding** là phần trống có thể được chèn vào cấu trúc để đáp ứng căn chỉnh. `sizeof` đã bao gồm padding.
- **Thông tin phụ theo từng nút** như `next`, `prev`, cờ, chiều cao và metadata cấp phát có thể lớn hơn payload khi phần tử rất nhỏ.
- **Chi phí toàn container** như `head`, `tail`, `capacity` khác với chi phí nhân theo `n`; cần phân tách để dự toán đúng.
- **Đo thay vì đoán:** dùng `sizeof`, `_Alignof`, `offsetof` và công cụ đo bộ nhớ phù hợp. Phân biệt ví dụ giả định 64-bit với đặc tính bảo đảm bởi ngôn ngữ.
- **Chọn theo cả bộ nhớ và thao tác:** mảng, danh sách liên kết, heap, bảng băm và cây đánh đổi mật độ lưu trữ, thời gian định vị, khả năng chèn/xóa và ổn định địa chỉ. Một cách biểu diễn tối ưu là cách đáp ứng yêu cầu cụ thể với chi phí chấp nhận được.
