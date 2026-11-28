# Sao chép dữ liệu so với chia sẻ cùng vùng lưu trữ

Trong một ứng dụng, hai biến cùng biểu diễn danh sách các công việc. Nếu sửa một danh sách, danh sách còn lại có thay đổi không? Nếu xóa một nút, các cấu trúc đang trỏ đến nút đó có còn hợp lệ không? Nếu muốn một bản sao độc lập, chương trình phải sao chép những gì: mảng chứa phần tử, chính từng phần tử, hay toàn bộ đồ thị đối tượng liên kết bên trong?

Đây là những câu hỏi về **sao chép dữ liệu (copying)** và **chia sẻ cùng vùng lưu trữ (sharing/aliasing)**. Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, chương **Bộ nhớ và biểu diễn**, phân biệt hai cơ chế này là nền tảng để hiện thực mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời phân tích **bất biến, vòng đời, độ phức tạp thời gian và bộ nhớ** khi lựa chọn cấu trúc phù hợp.

Bài học tập trung vào bốn câu hỏi: dữ liệu nằm ở đâu, biến nào đang truy cập cùng dữ liệu, thao tác thay đổi ảnh hưởng tới ai, và phải trả chi phí gì để có bản sao độc lập.

## 1. Ba tình huống dễ bị nhầm

Giả sử một danh sách logic có các giá trị `[10, 20, 30]`. Ta có ba cách tạo thêm một đường truy cập tới dữ liệu:

- **Sao chép giá trị/phần tử**: tạo vùng lưu trữ mới chứa các giá trị tương ứng.
- **Chia sẻ cùng đối tượng**: có thêm tên biến, con trỏ hoặc tham chiếu dẫn tới **chính vùng lưu trữ đang tồn tại**.
- **Sao chép một lớp nhưng chia sẻ lớp bên trong (shallow copy)**: tạo một đối tượng chứa mới, song những tham chiếu con bên trong vẫn chỉ tới cùng đối tượng đích.

```text
A. Hai dãy giá trị độc lập:

  first  ---> [10][20][30]     (vùng số 1)
  second ---> [10][20][30]     (vùng số 2)

  Sửa second[0] không làm first[0] đổi.


B. Hai tên cùng trỏ một dãy:

  first  -----+
              +----> [10][20][30]  (chỉ một vùng)
  second -----+

  Sửa second[0] cũng làm first[0] đổi.


C. Hai container, nhưng phần tử là các tham chiếu dùng chung:

  first  ---> [ref A][ref B] ----+
               |       |        |
               v       v        |
              Obj A   Obj B     |
               ^       ^        |
               |       |        |
  second ---> [ref A][ref B] ---+
               (container riêng)

  Có thể thay ô tham chiếu trong second độc lập,
  nhưng sửa Obj A qua một đường có thể nhìn thấy qua đường kia.
```

Sơ đồ C nhằm minh họa **container chứa tham chiếu**, không phải cách lưu trực tiếp những số nguyên hay kiểu giá trị bất biến. Để dự đoán đúng tác động, phải phân biệt **sao chép container**, **sao chép các phần tử** và **sao chép toàn bộ đối tượng mà các phần tử tham chiếu tới**.

### 1.1. Giá trị bằng nhau và danh tính giống nhau

Hai đối tượng có **giá trị bằng nhau** chưa chắc là **cùng đối tượng**. Trong Python:

```python
a = [10, 20]
b = [10, 20]
c = a

print(a == b)  # True: nội dung bằng nhau
print(a is b)  # False: hai đối tượng list khác nhau
print(a is c)  # True: c và a là hai tên của cùng list

c.append(30)
print(a)       # [10, 20, 30]
print(b)       # [10, 20]
```

Toán tử `==` so sánh theo quy tắc bằng nhau của kiểu dữ liệu, còn `is` so sánh danh tính trong Python. Không dùng `is` thay `==` để so sánh nội dung.

**Bất biến cần nhớ:** nếu nhiều tên cùng trỏ tới một đối tượng có thể sửa đổi (*mutable*), thay đổi trạng thái của đối tượng qua một tên sẽ được quan sát qua những tên còn lại. Nhưng **gán lại một tên** chỉ đổi ràng buộc của tên đó.

## 2. Sao chép giá trị và gán lại tham chiếu

### 2.1. Các giá trị độc lập trong C

Với kiểu giá trị đơn giản như `int`, gán từ biến này sang biến khác tạo một giá trị trong biến đích:

```c
#include <stdio.h>

int main(void) {
    int x = 7;
    int y = x;       /* y nhận giá trị 7. */

    y = 99;

    printf("x=%d, y=%d\n", x, y);  /* x=7, y=99 */
    return 0;
}
```

Hai biến `x` và `y` có vùng lưu trữ riêng trong mô hình ngôn ngữ; thay `y` không làm `x` đổi. Trình biên dịch có thể tối ưu và giữ giá trị trong thanh ghi, nhưng **ngữ nghĩa quan sát được** của phép gán vẫn như vậy.

Khi gán một con trỏ C:

```c
int x = 7;
int *p = &x;
int *q = p;

*q = 99;           /* x thành 99; *p cũng đọc ra 99. */
q = NULL;          /* Chỉ đổi giá trị con trỏ q; p vẫn trỏ đến x. */
```

`q = p` là **sao chép giá trị con trỏ**: hai biến con trỏ riêng biệt có cùng địa chỉ đích. Không có thao tác sao chép đối tượng `x`. Gán `q = NULL` thay đổi **liên kết của q**, không làm biến `p` đổi và không giải phóng `x`.

| Lệnh | Thay đổi gì? | Điều không tự động xảy ra |
| --- | --- | --- |
| `y = x` với hai biến `int` | Giá trị trong `y` | Không gán vào `x` |
| `q = p` với hai biến `int *` | Giá trị địa chỉ lưu trong `q` | Không sao chép đối tượng `*p` |
| `*q = 99` khi `q` hợp lệ | Đối tượng được `q` chỉ đến | Không đổi giá trị con trỏ `q` |
| `q = NULL` | Liên kết của biến `q` | Không giải phóng đối tượng đích |

### 2.2. Tham số hàm trong C: con trỏ cũng được truyền theo giá trị

Trong C, **mọi tham số được truyền theo giá trị**, kể cả tham số có kiểu con trỏ:

```c
#include <stdio.h>

void set_value(int *p) {
    if (p != NULL) {
        *p = 42;    /* Sửa đối tượng đích. */
        p = NULL;   /* Chỉ đổi bản sao con trỏ tại hàm. */
    }
}

int main(void) {
    int number = 3;
    int *ptr = &number;

    set_value(ptr);

    printf("number=%d\n", number);      /* 42 */
    printf("ptr points to number: %d\n", ptr == &number); /* 1 */
    return 0;
}
```

Hàm sửa được đối tượng thông qua `*p`, nhưng gán lại `p` không làm `ptr` ở phía gọi đổi. Để thay con trỏ của người gọi, hàm có thể nhận `int **` hoặc trả về con trỏ mới để phía gọi gán lại.

Đây là khác biệt quan trọng khi một hàm thêm nút đầu tiên vào danh sách: thay đổi `head` ở phía gọi cần được thực hiện **có chủ đích**, chứ không chỉ gán cho một bản sao của `head` trong hàm.

## 3. Sao chép nông (shallow copy) và sao chép sâu (deep copy)

**Shallow copy** tạo một đối tượng/container bên ngoài mới và sao chép các trường của nó. Nếu trường là địa chỉ hoặc tham chiếu, **giá trị liên kết** được sao chép; các đối tượng được trỏ tới vẫn là đối tượng cũ.

**Deep copy** tạo thêm các bản sao thích hợp cho những đối tượng nằm bên trong để đạt mức **độc lập cần thiết**. Với một cấu trúc lồng nhau, điều đó thường đòi hỏi duyệt đồ thị đối tượng chứ không chỉ sao chép một khối byte.

### 3.1. Ví dụ Python: list lồng nhau

```python
import copy

original = [[1, 2], [3, 4]]
shallow = original.copy()
deep = copy.deepcopy(original)

print(shallow is original)       # False: list ngoài khác nhau
print(shallow[0] is original[0]) # True: list con dùng chung
print(deep[0] is original[0])    # False: list con được sao chép

shallow[0].append(99)

print(original)  # [[1, 2, 99], [3, 4]]
print(shallow)   # [[1, 2, 99], [3, 4]]
print(deep)      # [[1, 2], [3, 4]]

shallow[1] = ["new"]     # Thay riêng ô trong shallow
print(original[1])      # [3, 4]: không bị thay
```

Sơ đồ trạng thái sau phép sao chép, trước khi sửa:

```text
original --+--> [ ref ---> Inner A, ref ---> Inner B ]
           |
shallow ------> [ ref ---> Inner A, ref ---> Inner B ]

deep ---------> [ ref ---> Copy A,  ref ---> Copy B  ]
                               (các list con mới)
```

Trong Python, `list.copy()` và phép cắt toàn bộ `original[:]` tạo list mới theo nghĩa **sao chép nông**. Phần tử là những tham chiếu được sao chép. Nếu các phần tử là đối tượng bất biến như số nguyên hoặc chuỗi, việc cùng tham chiếu tới chúng thường không gây vấn đề thay đổi tại chỗ; nhưng vẫn phải hiểu cơ chế.

`copy.deepcopy` có thể sao chép đệ quy nhiều loại đối tượng có thể thay đổi và dùng cơ chế ghi nhớ đối tượng đã gặp để xử lý quan hệ chia sẻ, chu trình trong nhiều trường hợp. Tuy nhiên, **không phải mọi đối tượng đều có thể hoặc nên deep copy**: file đang mở, socket, khóa đồng bộ, tài nguyên bên ngoài hoặc loại đối tượng có phương thức tùy chỉnh có thể có ngữ nghĩa riêng.

### 3.2. Gán một cấu trúc C có trường con trỏ

Gán một `struct` C có nghĩa là sao chép **giá trị các thành phần của struct** theo ngữ nghĩa của C. Những trường con trỏ vẫn mang cùng địa chỉ:

```c
#include <stdio.h>

typedef struct Record {
    int id;
    int *score;
} Record;

int main(void) {
    int shared_score = 80;
    Record first = {1, &shared_score};
    Record second = first;   /* Sao chép struct, không sao chép *score. */

    second.id = 2;
    *second.score = 95;

    printf("first: id=%d score=%d\n", first.id, *first.score);
    printf("second: id=%d score=%d\n", second.id, *second.score);
    /* first.id = 1, second.id = 2; cả hai cùng thấy score = 95. */
    return 0;
}
```

Sau phép gán:

- `first.id` và `second.id` là hai trường giá trị độc lập.
- `first.score` và `second.score` là hai trường con trỏ chứa cùng địa chỉ.
- Sửa `*second.score` làm thay đổi đối tượng `shared_score` được cả hai cùng dùng.

Nếu thay trường `score` bằng **mảng cố định nằm trực tiếp trong struct**, gán struct có thể sao chép cả thành phần mảng theo ngữ nghĩa gán struct; điều đó khác với việc sao chép một trường kiểu con trỏ.

### 3.3. Bản sao nông có thể gây lỗi sở hữu bộ nhớ

Nếu một `struct` quản lý vùng `malloc` và cả hai bản sao đều tự gọi `free` cho trường con trỏ đã sao chép, chương trình có nguy cơ **double free**. Nếu một bản sao giải phóng vùng trước, bản sao còn lại giữ **con trỏ treo (dangling pointer)**.

```c
/* Phác họa lỗi: cả first và second có cùng địa chỉ trong data. */
typedef struct Buffer {
    int *data;
} Buffer;

/*
Buffer second = first;
free(first.data);
free(second.data);  // SAI: giải phóng cùng vùng hai lần.
*/
```

Phải quy định **ai sở hữu vùng nhớ** trước khi sao chép. Những hướng xử lý phổ biến: cấm/giới hạn sao chép container sở hữu, cấp phát bản sao độc lập, chuyển quyền sở hữu, hoặc dùng cơ chế chia sẻ có quản lý vòng đời rõ ràng.

## 4. Sao chép độc lập một mảng trong C

Mảng C là vùng các phần tử cùng kiểu nằm liên tiếp. Sao chép dữ liệu giữa hai mảng **không** có nghĩa gán tên mảng bằng toán tử `=`:

```c
/* Sai trong C:
int a[3] = {1, 2, 3};
int b[3];
b = a;
*/
```

Có thể dùng vòng lặp, hoặc `memcpy` khi thích hợp. Ví dụ dưới đây dùng **mảng số nguyên thuần túy**, hai vùng không chồng lấn:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    int source[] = {10, 20, 30, 40};
    int destination[4];

    memcpy(destination, source, sizeof source);

    destination[0] = 99;

    printf("source[0]=%d\n", source[0]);           /* 10 */
    printf("destination[0]=%d\n", destination[0]); /* 99 */
    return 0;
}
```

`memcpy(destination, source, sizeof source)` sao chép **byte** từ vùng nguồn sang vùng đích. Các điều kiện quan trọng:

1. Hai vùng phải hợp lệ cho số byte yêu cầu; đích phải đủ dung lượng.
2. Hai vùng **không được chồng lấn**; nếu chồng lấn, dùng `memmove`.
3. Sao chép byte từ cấu trúc có trường con trỏ vẫn chỉ sao chép **giá trị con trỏ**, không sao chép đối tượng đích.
4. Cần biết đúng số byte cần sao chép. Nếu `source` đã được truyền vào hàm dưới dạng con trỏ, `sizeof(source)` trong hàm không còn cho kích thước mảng ban đầu.

Với một mảng nguồn và đích khác nhau lưu `n` giá trị có kích thước cố định, chi phí sao chép các phần tử là **O(n)** thời gian, và phải có **O(n)** dung lượng để giữ bản sao. Hàm sao chép chỉ cần O(1) bộ nhớ *phụ trợ ngoài vùng đích* trong mô hình đơn giản.

Với kiểu C++ có quản lý tài nguyên hoặc đối tượng không được phép sao chép byte để nhân bản, không dùng `memcpy` để thay cho copy constructor/assignment. Hãy dùng ngữ nghĩa sao chép và các thuật toán/container phù hợp của C++.

### 4.1. Chồng lấn bộ nhớ: khi nào cần `memmove`?

Xét mảng đang có `[1, 2, 3, 4, 5]` và muốn dịch bốn phần tử đầu sang phải một vị trí. Vùng nguồn và đích **chồng lấn**:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    int a[] = {1, 2, 3, 4, 5};

    memmove(&a[1], &a[0], 4 * sizeof a[0]);

    for (int i = 0; i < 5; ++i) {
        printf("%d ", a[i]);
    }
    puts(""); /* 1 1 2 3 4 */
    return 0;
}
```

`memmove` có ngữ nghĩa xử lý đúng vùng chồng lấn (như thể các byte được lưu tạm trước khi chép). Nhưng gọi `memmove` **không tạo một mảng logic mới**; ví dụ chỉ dịch nội dung trong một mảng đang tồn tại. Cũng không nên dùng `memmove` như kỹ thuật tùy tiện để di chuyển đối tượng C++ có vòng đời/cấu trúc nội bộ phức tạp.

## 5. Ngữ nghĩa giá trị và tham chiếu theo ngôn ngữ

### 5.1. C++: bản sao container và alias được phân biệt rõ

`std::vector<int>` có **ngữ nghĩa giá trị** khi sao chép bằng copy constructor: hai vector sở hữu các vùng chứa phần tử riêng. Trong khi đó, một tham chiếu C++ được ràng buộc với cùng đối tượng:

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> original = {10, 20};
    std::vector<int> copied = original;  // Sao chép dữ liệu vector.
    std::vector<int>& alias = original;  // Tham chiếu đến chính original.

    copied[0] = 99;
    alias[1] = 77;

    std::cout << original[0] << " " << original[1] << "\n"; // 10 77
    std::cout << copied[0] << " " << copied[1] << "\n";     // 99 20
}
```

Chi phí sao chép vector `n` phần tử thường là **O(n)** về số phần tử được sao chép (và cần cấp phát vùng mới). Với `std::vector<T>`, mỗi phần tử được sao chép bằng cơ chế thích hợp của `T`; nếu `T` là con trỏ, **đối tượng mà con trỏ chỉ đến không tự được sao chép sâu**. Nếu phần tử có thao tác sao chép tốn kém, tổng thời gian còn phụ thuộc chi phí sao chép từng phần tử.

Trong C++, phép **move** của một container có thể chuyển quyền quản lý vùng lưu trữ hiệu quả hơn một bản sao, nhưng không tạo hai vùng độc lập có cùng dữ liệu. Khi chọn move phải hiểu trạng thái hợp lệ của đối tượng nguồn sau move và quy tắc của container/allocator.

### 5.2. Java: biến kiểu tham chiếu và bản sao danh sách

`ArrayList` chứa tham chiếu đến các đối tượng (nếu phần tử là đối tượng). `new ArrayList<>(old)` tạo **container mới** chứa các tham chiếu phần tử đã sao chép, thông thường là sao chép nông:

```java
import java.util.ArrayList;

class Example {
    public static void main(String[] args) {
        ArrayList<StringBuilder> original = new ArrayList<>();
        original.add(new StringBuilder("A"));

        ArrayList<StringBuilder> copied = new ArrayList<>(original);

        copied.get(0).append("B");
        System.out.println(original.get(0)); // AB: cùng StringBuilder

        copied.add(new StringBuilder("C"));
        System.out.println(original.size());  // 1: container độc lập
        System.out.println(copied.size());    // 2
    }
}
```

Java **truyền tham số theo giá trị**; khi tham số thuộc kiểu tham chiếu, giá trị được sao chép là tham chiếu tới đối tượng. Hàm có thể sửa đối tượng đích thông qua tham số nhưng gán lại biến tham số không đổi biến của người gọi.

### 5.3. Python: phép gán tên không nhân bản object

`b = a` trong Python thường làm `b` tham chiếu tới **cùng đối tượng** như `a`. `a.copy()` với list tạo danh sách mới nông; `copy.deepcopy(a)` cố gắng sao chép các phần tử bên trong theo ngữ nghĩa của thư viện và các kiểu đối tượng tham gia. Với chuỗi hoặc số nguyên bất biến, chia sẻ thường không tạo hiệu ứng sửa tại chỗ vì các đối tượng này không cho phép sửa trạng thái nội tại.

```python
first = [1, 2]
alias = first
independent = first.copy()

alias[0] = 50
print(first)        # [50, 2]
print(independent)  # [1, 2]

alias = ["other"]   # Chỉ gán lại tên alias.
print(first)        # [50, 2]
```

Một điểm cần phân biệt: **slice của list Python** thường là một list mới (sao chép nông); còn slice của một số cấu trúc mảng trong thư viện khác, chẳng hạn một số thao tác NumPy, có thể là **view dùng chung vùng lưu trữ**. Không thể suy ra sao chép hay chia sẻ chỉ bằng ký hiệu `[start:end]` nếu chưa biết ngôn ngữ và kiểu dữ liệu.

### 5.4. Tham chiếu và view không tự đồng nghĩa sở hữu

Trong nhiều API, một **view** là đối tượng “nhìn vào” vùng lưu trữ đã có: nó mang liên kết và thông tin như độ dài/bước truy cập (*stride*) nhưng không nhất thiết sở hữu dữ liệu. Ví dụ `std::span<T>` trong C++20 thường là view tới một đoạn phần tử liên tiếp.

View thường rẻ để tạo và truy cập, nhưng phải giữ **vùng lưu trữ gốc còn sống** trong thời gian dùng view. Nếu vùng gốc bị cấp phát lại, thu hồi hoặc thay đổi theo cách làm mất hiệu lực đường truy cập, view có thể không còn hợp lệ. Việc API trả về một view có ghi được hay không còn phụ thuộc kiểu view và quyền truy cập.

## 6. Độ phức tạp: sao chép và chia sẻ trả giá khác nhau

Đặt `n` là số phần tử của một cấu trúc, giả sử sao chép từng phần tử có chi phí O(1). So sánh điển hình:

| Thao tác | Thời gian | Bộ nhớ mới cần | Quan hệ sau thao tác |
| --- | --- | --- | --- |
| Sao chép giá trị vô hướng cố định | O(1) | O(1) | Hai biến chứa giá trị riêng |
| Sao chép một giá trị con trỏ/tham chiếu | O(1) | O(1) | Hai đường truy cập có thể cùng trỏ một đối tượng |
| Sao chép mảng trực tiếp `n` phần tử | O(n) | O(n) | Hai vùng phần tử độc lập |
| Sao chép nông container `n` tham chiếu | O(n) | O(n) cho các ô container | Container riêng, đối tượng đích có thể dùng chung |
| Sao chép sâu danh sách liên kết đơn `n` nút | O(n) nếu mỗi giá trị sao chép O(1) | O(n) nút mới | Các nút độc lập theo chính sách sao chép |
| Tạo một view tới đoạn liên tiếp | Thường O(1) | Thường O(1) metadata | View chia sẻ vùng chứa với nguồn |
| Sao chép sâu đồ thị `V` đỉnh, `E` cạnh | Thường O(V+E) khi có cấu trúc ánh xạ phù hợp | O(V+E) cho bản sao và metadata | Cần bảo toàn quan hệ chia sẻ và chu trình |

**Chú ý về O(1):** sao chép **một con trỏ** là O(1), nhưng chi phí sử dụng dữ liệu qua con trỏ có thể phải cộng thêm bước định vị. Ví dụ, nếu muốn sửa phần tử thứ `i` của danh sách liên kết, dù phép gán trường khi đã có nút là O(1), bước đi tới nút thứ `i` vẫn là O(i).

**Chú ý về O(n):** việc sao chép container nông có chi phí theo số ô phần tử, nhưng không bao gồm giá thành sao chép sâu các đối tượng được tham chiếu. Với một chuỗi ký tự dài, một đối tượng tùy biến, hay container lồng sâu, thời gian sao chép có thể lớn hơn giả định sao chép giá trị O(1).

## 7. Bất biến và tính nhất quán khi nhiều cấu trúc chia sẻ đối tượng

Chia sẻ bộ nhớ có thể tiết kiệm thời gian sao chép và dung lượng, nhưng làm xuất hiện **các phụ thuộc giữa những đường truy cập**.

Ví dụ danh sách liên kết có hai biến đầu trỏ tới cùng nút:

```text
list_A.head --+
              +--> [10 | next] --> [20 | next] --> NULL
list_B.head --+
```

Nếu một hàm thay `next` của nút `10` thông qua `list_A`, cấu trúc nhìn từ `list_B` cũng thay đổi. Nếu một container **giải phóng** nút trong khi container khác còn trỏ tới nó, có thể xuất hiện con trỏ treo. Nếu hai container đều nghĩ mình là chủ sở hữu duy nhất và cùng giải phóng các nút, có thể xảy ra giải phóng hai lần.

Đối với cấu trúc dùng chung nút, phải trả lời rõ:

1. **Ai sở hữu** mỗi nút và được phép giải phóng nó?
2. **Ai được sửa** trường liên kết hoặc dữ liệu của nút?
3. Mỗi container có giữ riêng `head`, `tail`, `size` không, và việc sửa nút dùng chung ảnh hưởng bất biến nào?
4. Có cho phép cấu trúc chia sẻ toàn bộ hoặc một phần đuôi của danh sách, cây con, hay đối tượng đích không?
5. Nếu nhiều luồng cùng truy cập, cơ chế đồng bộ hoặc bất biến dữ liệu có đủ đảm bảo tính đúng đắn không?

Một danh sách liên kết “thuộc quyền sở hữu độc lập” thường cần bất biến rằng tất cả nút có thể đi tới từ `head` thuộc container đó và được giải phóng đúng một lần. Một cấu trúc **chia sẻ cây con** có thể có chính sách sở hữu khác, nhưng các thao tác sửa phải được thiết kế phù hợp. Không thể chỉ sao chép con trỏ gốc rồi giả định đã tạo được hai cây độc lập.


## 8. Thực hành: sao chép sâu một danh sách liên kết đơn

Giả sử cấu trúc danh sách đơn chỉ chứa các số nguyên. Muốn có một danh sách độc lập, chương trình phải **tạo nút mới cho từng nút nguồn**, sao chép `value` và nối `next` sao cho thứ tự logic được giữ nguyên.

```text
Nguồn:
head_A --> [10 | next] --> [20 | next] --> [30 | NULL]

Bản sao sâu:
head_B --> [10 | next] --> [20 | next] --> [30 | NULL]

Mỗi nút ở A khác địa chỉ với nút tương ứng ở B.
Không có liên kết next nào từ bản sao trỏ về nút thuộc nguồn.
```

### 8.1. Mã C hoàn chỉnh, có xử lý cấp phát thất bại

```c
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

void free_list(Node *head) {
    while (head != NULL) {
        Node *next = head->next;
        free(head);
        head = next;
    }
}

/*
 * Tạo bản sao độc lập của một danh sách đơn kết thúc tại NULL.
 * Thành công: trả về head mới, hoặc NULL nếu danh sách nguồn rỗng.
 * Thất bại cấp phát: giải phóng phần bản sao đã tạo, trả về NULL.
 *
 * Ví dụ này giả sử giá trị là int và danh sách nguồn không có chu trình.
 */
Node *clone_list(const Node *source) {
    Node dummy = {0, NULL};
    Node *tail = &dummy;

    for (const Node *cur = source; cur != NULL; cur = cur->next) {
        Node *copy = malloc(sizeof *copy);

        if (copy == NULL) {
            free_list(dummy.next);
            return NULL;
        }

        copy->value = cur->value;
        copy->next = NULL;

        tail->next = copy;
        tail = copy;
    }

    return dummy.next;
}

int main(void) {
    Node third  = {30, NULL};
    Node second = {20, &third};
    Node first  = {10, &second};

    Node *cloned = clone_list(&first);

    /* Nguồn có phần tử nên NULL ở đây có nghĩa là cấp phát thất bại. */
    if (cloned == NULL) {
        return EXIT_FAILURE;
    }

    cloned->value = 99;

    printf("Nguon: %d %d %d\n",
           first.value, second.value, third.value);
    printf("Ban sao: %d %d %d\n",
           cloned->value, cloned->next->value,
           cloned->next->next->value);
    /* Nguon: 10 20 30
       Ban sao: 99 20 30 */

    free_list(cloned);
    /* Khong free cac nut first/second/third: chung la bien cuc bo. */
    return EXIT_SUCCESS;
}
```

Để mã dễ tập trung vào phép sao chép, ba nút nguồn trong `main` là các biến cục bộ; chỉ các nút **bản sao** do `malloc` cấp phát mới cần `free`. Gọi `free` cho `first`, `second` hoặc `third` sẽ là sai vì chúng không phải vùng cấp phát từ `malloc`.

Bất biến trong vòng lặp sao chép:

1. Đoạn từ `dummy.next` đến `tail` chứa những nút mới đã sao chép thành công, theo đúng thứ tự nguồn.
2. `tail->next == NULL`, nên danh sách mới luôn kết thúc hợp lệ.
3. Không nút mới nào trỏ vào danh sách nguồn.
4. Nếu `malloc` thất bại, có thể giải phóng toàn bộ phần đã tạo bằng cách đi từ `dummy.next`.

Với `n` nút, thuật toán có **O(n)** thời gian và cần **O(n)** dung lượng cho `n` nút mới, ngoài bộ nhớ phụ trợ O(1) cho các con trỏ điều khiển. Nó không dùng đệ quy nên không phát sinh stack tăng theo chiều dài danh sách.

**Giới hạn cần lưu ý:** thuật toán chỉ sao chép **sâu ở lớp nút** khi payload là `int`. Nếu `Node.value` là con trỏ tới đối tượng động, cần quyết định có tạo bản sao sâu cho đối tượng đích hay cố ý chia sẻ nó. Nếu danh sách nguồn có chu trình, vòng lặp này sẽ không kết thúc; muốn sao chép danh sách vòng hoặc đồ thị phải có logic nhận diện nút đã thăm.

### 8.2. Khi nào sao chép nút nhưng vẫn là shallow copy?

Xét một danh sách có nút như sau:

```c
typedef struct TextNode {
    char *text;              /* Trỏ tới vùng ký tự được quản lý riêng. */
    struct TextNode *next;
} TextNode;
```

Nếu clone chỉ dùng `copy->text = source->text`, thì **các nút mới độc lập**, nhưng trường `text` vẫn trỏ tới **cùng vùng ký tự**. Muốn bản sao độc lập toàn bộ, cần có chính sách cấp phát và sao chép chuỗi, xác định quyền sở hữu, xử lý lỗi cấp phát và giải phóng từng chuỗi theo đúng chính sách.

Vì vậy các từ *shallow* và *deep* luôn cần được hiểu **đối với ranh giới đối tượng nào**. Một container có thể deep copy nút nhưng shallow copy phần tử; hoặc copy phần tử nhưng vẫn chia sẻ các đối tượng mà phần tử chứa tham chiếu.

## 9. Sao chép cây và đồ thị: bảo toàn quan hệ chia sẻ

### 9.1. Cây độc lập và cây con dùng chung

Với **cây đúng nghĩa**, một nút (trừ gốc) thường có một cha theo cách tổ chức cây, và các nút con không bị chia sẻ qua nhiều nhánh trong cùng cây. Nếu mỗi nút chỉ chứa giá trị đơn giản, deep copy cây có thể tạo nút đích rồi đệ quy sao chép các cây con.

Ví dụ trừu tượng:

```text
source_root
    8
   / \
  3  12
     /
    10

clone_root
    8
   / \
  3  12
     /
    10

Hai cây có giá trị/hình dạng như nhau; toàn bộ nút khác địa chỉ.
```

Một hàm clone đệ quy đơn giản có thể mất **O(n)** thời gian và O(h) bộ nhớ ngăn xếp, với `h` là chiều cao cây. Với cây suy biến thành chuỗi rất dài, `h = O(n)`; khi đó cần cân nhắc khả năng tràn stack và có thể dùng cách duyệt lặp. Hàm cũng phải xử lý tình huống cấp phát thất bại bằng cách dọn đúng toàn bộ cây con đã tạo.

### 9.2. Đồ thị có chu trình hoặc nhiều cạnh cùng đến một nút

Giả sử hai cạnh cùng trỏ tới một nút `C`, và `C` có đường quay về nút đầu:

```text
      A ----> B
       \      |
        \     v
         +--> C ----> A
```

Nếu sao chép mỗi lần gặp liên kết bằng cách tạo ngay nút mới mà không ghi nhớ, ta có thể:

- **Nhân đôi sai** nút `C` dù trong nguồn chỉ có một nút được dùng chung.
- **Lặp vô hạn** khi gặp chu trình `C -> A -> ...`.
- Làm mất quan hệ định danh và thay đổi ý nghĩa thuật toán trên đồ thị.

Giải pháp phổ biến là dùng một **bảng ánh xạ từ định danh nút nguồn sang nút bản sao**:

```text
clone(node):
    if node == null:
        return null
    if node đã có trong map:
        return map[node]

    new_node = cấp phát bản sao rỗng của node
    map[node] = new_node  # Lưu trước khi xử lý các cạnh, để xử lý chu trình.

    for mỗi cạnh node -> neighbor:
        thêm cạnh new_node -> clone(neighbor)

    return new_node
```

Khi gặp lại một nút nguồn, thuật toán dùng lại **đúng nút bản sao đã tạo**, từ đó bảo toàn các quan hệ chia sẻ trong nội bộ bản sao và tránh lặp vô hạn do chu trình. Với bảng băm được thiết kế phù hợp và số trường/cạnh được xử lý tỉ lệ với số cạnh, độ phức tạp **trung bình mong đợi** là O(V+E) thời gian và O(V+E) không gian cho bản sao cùng metadata; độ sâu đệ quy có thể O(V) nếu cài đặt đệ quy. Nếu bảng ánh xạ dùng cấu trúc khác, phải phân tích lại chi phí tra cứu.

Trong chương trình thực, quy tắc sao chép còn cần xử lý nhãn, dữ liệu cạnh, quyền sở hữu tài nguyên, cơ chế hoàn tác khi cấp phát thất bại và liệu bản sao có giữ các nút bên ngoài đồ thị hay không.

## 10. Chia sẻ có kiểm soát: bất biến, phiên bản và copy-on-write

### 10.1. Chia sẻ dữ liệu bất biến (immutable data)

Nếu dữ liệu **không thể bị sửa sau khi công bố**, nhiều nơi có thể dùng chung mà không sợ một nơi thay đổi âm thầm làm nơi khác sai lệch.

Ví dụ: nhiều cấu trúc cùng tham chiếu tới một chuỗi ký tự bất biến hoặc một cây con bất biến. Thay vì sao chép cây con, chương trình có thể chia sẻ cùng nút/đường liên kết.

```text
Version 1 root ----> [Root A] ----> [Subtree S]
Version 2 root ----> [Root B] ----> [Subtree S]
                                    (dùng chung,
                                     không sửa tại chỗ)
```

Sự an toàn không đến chỉ từ việc có hai con trỏ mà từ **hợp đồng không sửa** và **vòng đời được quản lý**. Nếu một nơi lén sửa `Subtree S`, cả hai phiên bản có thể bị ảnh hưởng.

### 10.2. Copy-on-write (COW): chỉ sao chép khi cần sửa

**Copy-on-write** là chiến lược ban đầu cho phép nhiều người dùng cùng một vùng dữ liệu, nhưng khi cần ghi, bên ghi phải đảm bảo có bản sao riêng trước khi thay đổi.

```text
Ban đầu:
  snapshot A ------+
                   +------> [10][20][30]  (dùng chung)
  snapshot B ------+

A muốn sửa phần tử đầu:
  A ----> [99][20][30]  (bản sao mới)
  B ----> [10][20][30]  (bản gốc)
```

Với COW ở mức **toàn bộ mảng**, tạo snapshot có thể là O(1) chỉ để chia sẻ liên kết và tăng số tham chiếu, nhưng **lần ghi đầu** có thể phải sao chép O(n) phần tử và cấp phát O(n) bộ nhớ. Sau khi mỗi bên đã có mảng riêng, những lần ghi tiếp theo trong bản đó không cần sao chép toàn bộ vì lý do chia sẻ nữa, tùy hiện thực.

Không phải mọi thao tác tạo snapshot đều O(1): còn tùy cấu trúc và cách quản lý metadata. COW cũng phải tránh lộ ra con trỏ/view ghi được vào vùng đang chia sẻ mà bỏ qua bước “tách bản sao” trước khi sửa.

### 10.3. Structural sharing trong cấu trúc dữ liệu bền vững

Một **persistent data structure** giữ các phiên bản cũ có thể truy cập được sau thao tác tạo phiên bản mới. Để tránh sao chép toàn bộ, một số cấu trúc dùng **structural sharing**: các nhánh không đổi tiếp tục được dùng chung, chỉ cấp phát các nút nằm trên đường cập nhật.

Ví dụ với cây nhị phân tìm kiếm cân bằng và bất biến:

```text
Trước khi sửa khóa ở nhánh phải:
       R
      / \
     L   X
        / \
       Y   Z

Sau khi tạo phiên bản mới:
       R'
      /  \
     L    X'
         /  \
        Y    Z'

L và Y có thể là các cây con dùng chung bất biến.
R', X', Z' là các nút mới trên đường cập nhật (minh họa).
Cây gốc R vẫn tham chiếu X, Z như trước.
```

Trong một cây cân bằng với chiều cao O(log n), **path copying** trên một đường cập nhật có thể tạo O(log n) nút mới thay vì O(n), miễn là thuật toán giữ đúng các bất biến cân bằng và bất biến bất biến dữ liệu. Với cấu trúc không cân bằng, số nút phải sao chép theo đường đi có thể là O(n). Nếu giá trị của nút là một đối tượng có thể sửa được dùng chung, vẫn cần chính sách xử lý tương ứng.

**Đừng nhầm persistent data structure với lưu trữ trên ổ đĩa**: “persistent” trong ngữ cảnh này nói về khả năng giữ và truy cập các phiên bản cấu trúc cũ.

### 10.4. Vòng đời nút được chia sẻ

Một nút/cây con dùng chung chỉ được thu hồi khi **không còn phiên bản nào cần nó**, theo cơ chế quản lý vòng đời được lựa chọn. Có thể dùng bộ gom rác, đếm tham chiếu, kỹ thuật xác định người sở hữu hoặc cơ chế riêng phù hợp với ngôn ngữ.

Đếm tham chiếu không tự giải quyết mọi vấn đề: **chu trình sở hữu** có thể giữ đối tượng tồn tại lâu ngoài ý muốn, tùy hệ thống. Ví dụ trong C++, dùng `std::shared_ptr` cho cả hai hướng của một liên kết vòng có thể tạo chu trình mạnh; `std::weak_ptr` được dùng ở các liên kết không sở hữu khi phù hợp.

## 11. Quyền sở hữu, thời gian sống và an toàn khi chia sẻ

### 11.1. Ai có thể giải phóng vùng lưu trữ?

Ba mô hình thường gặp:

| Mô hình | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Sở hữu duy nhất** | `std::unique_ptr<T>` trong C++ | Một chủ sở hữu quản lý vòng đời; có thể chuyển quyền sở hữu |
| **Sở hữu chia sẻ** | `std::shared_ptr<T>` trong C++ | Các chủ sở hữu cùng giữ đối tượng sống; cần xét chu trình |
| **Tham chiếu mượn / view** | Con trỏ không sở hữu, `std::span<T>` | Không tự giải phóng; vùng gốc phải tồn tại suốt thời gian sử dụng |

Một con trỏ thô C không tự nói rõ nó có **sở hữu** vùng nhớ hay chỉ **mượn**. API cần quy ước rõ, hoặc dùng kiểu/mẫu thiết kế buộc người dùng tuân theo hợp đồng.

### 11.2. Khi vùng gốc bị dời, view và con trỏ có thể hỏng

Mảng động thường tăng dung lượng bằng cách cấp phát vùng lớn hơn rồi chuyển các phần tử. Khi đó, các con trỏ/view trỏ tới vùng cũ có thể mất hiệu lực theo quy tắc của container.

Ví dụ C++:

```cpp
#include <vector>

int main() {
    std::vector<int> values = {10, 20};
    const int *old_address = values.data();

    values.reserve(1000);

    /* Nếu reserve làm thay đổi capacity, có thể đã cấp phát lại.
       Không được sử dụng old_address sau khi bị vô hiệu hóa. */
    (void)old_address;
}
```

Trong ví dụ này `reserve(1000)` sẽ yêu cầu dung lượng tối thiểu 1000; với vector hai phần tử thông thường, thao tác phải tăng dung lượng và có thể làm mất hiệu lực mọi con trỏ/iterator tới phần tử trước đó. Ví dụ tránh giải tham chiếu `old_address` sau khi vùng lưu trữ có thể đã dời.

**Sao chép** thành container độc lập đôi khi giảm phụ thuộc vòng đời với nguồn. Ngược lại, một **view** tiết kiệm chi phí cấp phát nhưng cần đảm bảo vùng được nhìn vào còn sống và còn hợp lệ.

### 11.3. Nhiều luồng cùng sửa: chia sẻ không tự an toàn

Hai luồng **đọc cùng dữ liệu bất biến** thường đơn giản để phối hợp. Nếu một luồng ghi vào vùng đang được luồng khác đọc hoặc ghi, phải tuân thủ quy tắc đồng bộ bộ nhớ của ngôn ngữ.

Ví dụ: dùng `std::shared_ptr` giúp **quản lý số lượng chủ sở hữu** theo cơ chế của C++, nhưng **không tự làm cho các thao tác đồng thời ghi vào đối tượng đích an toàn**. Quyền sở hữu và đồng bộ trạng thái là hai trách nhiệm khác nhau.

Khi tạo nhiều snapshot dùng chung vùng có thể sửa, cần một trong các chiến lược thích hợp như khóa đồng bộ, dữ liệu bất biến, COW có đồng bộ, hoặc thiết kế truyền thông điệp để chỉ một nơi có quyền ghi.

### 11.4. Chia sẻ dữ liệu còn có chi phí gián tiếp

Một vùng chia sẻ có thể tiết kiệm bộ nhớ nhưng kéo theo:

- Quản lý số lượng tham chiếu hoặc đồng bộ quyền truy cập.
- Cache coherence khi các lõi cùng ghi vào các vùng dữ liệu liên quan.
- Khó xác định thời điểm được phép giải phóng hoặc sửa cấu trúc.
- Khó áp dụng cập nhật độc lập nếu nhiều container dùng chung nút.
- Nguy cơ giữ lại cây con/đối tượng lớn chỉ vì còn một tham chiếu nhỏ.

Vì vậy “chia sẻ O(1)” chỉ mô tả **chi phí tạo một liên kết** trong một tình huống; nó không thay thế phân tích toàn bộ vòng đời.

## 12. Chọn sao chép hay chia sẻ khi xây cấu trúc dữ liệu

| Tình huống | Phương án thường hợp lý | Lý do |
| --- | --- | --- |
| Hai tác vụ cần danh sách số nguyên độc lập, có thể sửa riêng | Sao chép mảng hoặc clone nút | Tránh thay đổi chéo, đơn giản hóa quyền sở hữu |
| Chỉ cần gửi dữ liệu lớn cho hàm đọc | Tham chiếu/view chỉ đọc | Tránh sao chép O(n), giảm cấp phát |
| Nhiều truy vấn đọc chung một bảng tra cứu bất biến | Chia sẻ dữ liệu bất biến | Tăng tái sử dụng và giảm dung lượng |
| Thực hiện rollback/undo của nhiều phiên bản cây | Persistent tree với structural sharing | Giữ bản cũ và tái sử dụng nhánh không đổi |
| Hai thread cần sửa bản dữ liệu riêng | Sao chép độc lập hoặc COW có thiết kế đồng bộ | Giảm phụ thuộc cập nhật và xung đột |
| Copy container chứa các con trỏ sở hữu | Định nghĩa rõ deep copy/ownership trước | Shallow copy có thể tạo double free hoặc dangling |
| Truyền dữ liệu giữa các thành phần bằng move | Chuyển quyền sở hữu khi thích hợp | Tránh nhân bản dữ liệu nếu nơi cũ không còn cần bản đó |
| Sao chép đồ thị có chu trình | Clone với map nút nguồn → nút đích | Bảo toàn định danh, ngăn nhân đôi và lặp vô hạn |

### 12.1. Tình huống định lượng: một triệu số nguyên

Giả sử `sizeof(int) = 4` byte, mảng có đúng `1.000.000` phần tử:

- Vùng phần tử nguồn cần khoảng **4.000.000 byte (4 MB thập phân)**.
- Tạo thêm bản sao mảng độc lập cần khoảng **4 MB** nữa cho phần tử, chưa tính container và allocator.
- Thêm một con trỏ hoặc view chia sẻ có chi phí metadata nhỏ, thường O(1), nhưng **không làm vùng dữ liệu trở nên độc lập**.
- Với COW toàn mảng, snapshot chia sẻ lúc đầu có thể rẻ, nhưng lần ghi đầu có thể đòi hỏi thêm **4 MB** và sao chép một triệu số.
- Nếu thay bằng một triệu nút liên kết, tổng bộ nhớ còn bao gồm **con trỏ, padding và phí cấp phát** trên mỗi nút; việc deep copy nhân đôi số nút, không chỉ nhân đôi payload.

Tốc độ thật còn phụ thuộc locality, kích thước phần tử, tốc độ cấp phát và workload. Không được kết luận một thao tác O(1) chắc chắn có tổng chi phí thấp hơn qua mọi vòng đời so với một lần copy O(n).

## 13. Các lỗi phổ biến và cách nhận diện

### “Gán con trỏ là đã sao chép đối tượng”

Sai. `int *q = p;` tạo con trỏ mới chứa cùng địa chỉ đích; không nhân bản `*p`. Khi hai con trỏ cùng chỉ tới đối tượng có thể sửa, thao tác qua một con trỏ có thể được thấy qua con trỏ kia.

### “Sao chép list là sao chép sâu mọi đối tượng”

Sai với `list.copy()` của Python, `new ArrayList<>(source)` của Java và nhiều API copy container khác: container mới có thể giữ **cùng tham chiếu phần tử**. Phải kiểm tra hợp đồng của kiểu cụ thể.

### “Deep copy luôn là lựa chọn an toàn và nhanh”

Deep copy có thể ngăn phụ thuộc sửa đổi, nhưng phải trả chi phí thời gian/bộ nhớ và có thể không phù hợp với đối tượng tài nguyên ngoài, đối tượng mang định danh duy nhất hoặc cấu trúc có quy tắc sở hữu đặc thù. Thuật toán clone đồ thị cần giữ đúng quan hệ định danh trong bản sao.

### “Hai bản sao nông có thể tự giải phóng cùng vùng nhớ”

Không. Nếu hai bản sao chứa cùng con trỏ sở hữu và đều giải phóng, sẽ có double free. Phải quy định chủ sở hữu, cơ chế chuyển quyền, chia sẻ có quản lý hoặc copy sâu thích hợp.

### “Con trỏ còn khác NULL thì chắc chắn hợp lệ”

Sai. Sau khi đối tượng đích đã hết vòng đời, con trỏ vẫn có thể mang địa chỉ cũ. So sánh với NULL không tự chứng minh đối tượng còn sống hoặc có thể truy cập hợp lệ.

### “Copy-on-write cho phép sửa snapshot dùng chung mà không sao chép”

Sai. COW phải **tách dữ liệu trước khi sửa** nếu còn bên khác cùng dùng bản cũ. Nếu không, biến đổi của một bên vẫn làm bên kia nhìn thấy thay đổi.

### “Chỉ cần clone từng cạnh của đồ thị là đủ”

Sai. Một đỉnh có thể có nhiều cạnh đi tới, chu trình có thể khiến thuật toán lặp mãi. Dùng ánh xạ từ đỉnh nguồn sang đỉnh sao chép để bảo toàn quan hệ chia sẻ và tránh tạo trùng.

## 14. Bài tập có lời giải

### Bài 1. Dự đoán hiệu ứng alias

```python
a = [1, 2]
b = a
c = a[:]

b.append(3)
c[0] = 99
print(a, b, c)
```

**Đáp án:** `a` và `b` cùng là `[1, 2, 3]`; `c` là `[99, 2]`. `b = a` chia sẻ đối tượng list; `a[:]` tạo list mới nông. Vì phần tử là số nguyên nên thay một ô trong `c` không thay `a`.

### Bài 2. Bản sao nông của dữ liệu lồng nhau

```python
outer = [[1], [2]]
copy_outer = outer.copy()
copy_outer[0].append(7)
copy_outer[1] = [9]
print(outer)
```

**Đáp án:** `[[1, 7], [2]]`. List con ở chỉ số 0 vẫn dùng chung; thay ô ở chỉ số 1 trong container `copy_outer` chỉ đổi tham chiếu của container đó.

### Bài 3. Sao chép con trỏ trong C

```c
int x = 10;
int *p = &x;
int *q = p;
*q = 50;
q = NULL;
```

**Đáp án:** `x == 50`, `*p == 50`, `q == NULL`. Gán `q = p` sao chép **địa chỉ**; `*q = 50` sửa đối tượng `x`; gán lại `q` không sửa `p`.

### Bài 4. Chi phí sao chép mảng

Có mảng `n` số nguyên kích thước cố định. Tạo một mảng mới và sao chép mọi phần tử có chi phí bao nhiêu? Nếu chỉ tạo biến con trỏ mới trỏ về mảng cũ thì sao?

**Đáp án:** Copy mảng là **O(n)** thời gian và **O(n)** dung lượng để lưu bản độc lập; sao chép một giá trị con trỏ là **O(1)** thời gian và O(1) metadata, nhưng hai biến có thể cùng truy cập một vùng.

### Bài 5. Sao chép nút trong danh sách liên kết

Cho danh sách `10 -> 20 -> 30`, có hai con trỏ `head1` và `head2 = head1`. Nếu sửa `head2->next->value` thành 99 thì `head1` có thấy 99 không? Cần làm gì để hai danh sách độc lập?

**Đáp án:** **Có.** Hai con trỏ đầu cùng trỏ tới các nút. Muốn độc lập, cấp phát một nút mới cho mỗi nút, sao chép giá trị và liên kết các nút mới theo đúng thứ tự; cần quy định rõ việc giải phóng cả hai danh sách.

### Bài 6. Deep copy đồ thị có chu trình

Đồ thị `A -> B -> C -> A`. Vì sao một hàm clone đệ quy chỉ tạo nút mới rồi gọi clone lên từng hàng xóm có thể không kết thúc?

**Đáp án:** Vì quay lại `A` và tiếp tục clone mà không nhận biết đã xử lý. Phải ghi vào map `A -> A'` **trước khi** đi tới hàng xóm, rồi sử dụng lại `A'` khi gặp `A` lần nữa.

### Bài 7. Sao chép và chia sẻ ở mảng COW

Hai snapshot dùng chung mảng một triệu phần tử. Snapshot A cần sửa một ô, trong khi B phải giữ nguyên dữ liệu. Điều gì cần xảy ra?

**Đáp án:** Trong mô hình COW toàn mảng, A cần có bản sao riêng **trước khi ghi**; lần ghi đầu có thể tốn O(n) thời gian và bộ nhớ mới, dù thao tác tạo snapshot trước đó chỉ cần O(1) metadata. Sau khi tách, sửa một ô trong bản A là O(1).

### Bài 8. Chọn cấu trúc cho phiên bản lịch sử

Một ứng dụng cần giữ 10.000 phiên bản của cây có kích thước lớn, mỗi phiên bản thường chỉ đổi một khóa. Có nhất thiết deep copy toàn cây mỗi lần?

**Đáp án:** Không. Có thể cân nhắc **persistent tree** dùng structural sharing: các cây con bất biến được dùng chung, chỉ sao chép các nút trên đường cập nhật. Với cây cân bằng, một cập nhật đơn thường cần O(log n) nút mới theo mô hình phù hợp, thay vì O(n). Cần giải quyết vòng đời và hạn chế sửa đổi nút dùng chung.

### Bài 9. Vòng đời của view

Một hàm trả về view tới mảng cục bộ được tạo trong hàm rồi mảng hết vòng đời. View có còn an toàn không?

**Đáp án:** **Không**, nếu view chỉ mượn vùng nhớ và vùng gốc đã hết vòng đời. View không tự kéo dài vòng đời của dữ liệu theo một hợp đồng chung; phải trả về một đối tượng sở hữu thích hợp hoặc duy trì vùng gốc đủ lâu.

## 15. Ghi nhớ để ứng dụng

- **Sao chép giá trị** tạo thông tin độc lập ở mức được sao chép; **sao chép con trỏ/tham chiếu** tạo thêm một đường truy cập tới cùng đối tượng.
- **Shallow copy** nhân bản lớp container nhưng vẫn có thể dùng chung đối tượng bên trong. **Deep copy** cần xác định độ sâu và ngữ nghĩa sao chép của từng loại đối tượng.
- **Chia sẻ** thường tiết kiệm cấp phát và thời gian copy, nhưng đặt ra yêu cầu quản lý vòng đời, bất biến, quyền sở hữu và đồng bộ khi có ghi.
- **Copy-on-write** và **structural sharing** cho phép tận dụng vùng dữ liệu dùng chung trong những tình huống thích hợp; lần ghi và vòng đời dữ liệu vẫn có chi phí.
- Khi chọn mảng, danh sách liên kết, cây, bảng băm hay đồ thị, hãy tách rõ **chi phí tạo bản sao**, **chi phí truy cập/cập nhật**, **bộ nhớ giữ lại**, **điều kiện dữ liệu độc lập** và **trách nhiệm giải phóng**. Cách phù hợp là cách đáp ứng thao tác và bất biến của bài toán với độ phức tạp chấp nhận được.
