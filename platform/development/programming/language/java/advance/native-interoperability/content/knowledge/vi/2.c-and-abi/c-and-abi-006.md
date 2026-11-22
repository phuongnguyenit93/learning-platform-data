# Con trỏ, con trỏ kép, mảng liên tục và con trỏ hàm trong C/ABI

## 1. Mục tiêu và lý do cần học trong Java Native Interoperability

Khi Java gọi thư viện native qua JNI hoặc Foreign Function & Memory API (FFM), chữ ký C không chỉ mô tả “kiểu dữ liệu”. Nó còn quy định **địa chỉ nào được truyền**, vùng nhớ đó chứa gì, cách đọc theo kích thước/căn chỉnh của ABI, bên nào sở hữu bộ nhớ và native code có thể gọi ngược một hàm hay không. Những khác biệt giữa `T *`, `T **`, `T [N]`, `T (*)[N]` và con trỏ hàm là nguồn gốc của nhiều lỗi biên dịch, crash và hỏng bộ nhớ.

Sau bài này, bạn cần:
- Đọc đúng khai báo con trỏ và phân biệt **giá trị con trỏ (địa chỉ)** với **đối tượng mà nó trỏ đến**.
- Giải thích được con trỏ kép, trường hợp tham số output và cách phân biệt với mảng hai chiều.
- Xác định vùng nhớ liên tục, bước nhảy con trỏ, độ dài mảng và kiểu của từng phép lấy địa chỉ.
- Đọc/khai báo và truyền con trỏ hàm; hiểu callback đi qua ranh giới ABI.
- Thiết kế hợp đồng Java–C đủ thông tin về **kiểu, kích thước, độ dài, ownership, lifetime, alignment và calling convention**.

Phạm vi chính là C và ABI. Các ví dụ C dùng C11; phần Java chỉ ra cách biểu diễn tương ứng khi tích hợp native.

## 2. Mô hình nền tảng: đối tượng, địa chỉ, con trỏ và phép giải tham chiếu

Xét:

~~~c
int value = 42;
int *p = &value;
~~~

- `value` là một đối tượng kiểu `int`; `&value` là địa chỉ của nó, kiểu `int *`.
- `p` là **một biến riêng**, có kiểu `int *`, đang chứa giá trị địa chỉ của `value`.
- `*p` truy cập đối tượng `int` ở địa chỉ mà `p` đang biểu diễn. `*p = 7;` làm thay đổi `value` thành `7`.
- `&p` là địa chỉ của **biến con trỏ** `p`; nó có kiểu `int **`, hoàn toàn khác `p`.

Mô hình khái niệm (địa chỉ chỉ để minh họa, không phải giá trị được bảo đảm):

~~~text
value (int)            p (int *)
địa chỉ 0x1000         địa chỉ 0x2000
giá trị 42     <------- nội dung 0x1000

*p  -> đọc/ghi value
&p  -> 0x2000 (địa chỉ nơi lưu chính p)
~~~

Cú pháp thường dùng:

| Biểu thức | Kiểu (trong ví dụ) | Ý nghĩa |
|---|---|---|
| `value` | `int` | Giá trị của đối tượng |
| `&value` | `int *` | Địa chỉ của đối tượng |
| `p` | `int *` | Giá trị địa chỉ đã lưu trong con trỏ |
| `*p` | `int` (lvalue) | Đối tượng được trỏ đến |
| `&p` | `int **` | Địa chỉ của biến con trỏ |
| `**pp`, với `int **pp = &p` | `int` (lvalue) | Đối tượng cuối cùng sau hai lần giải tham chiếu |

Có thể đặt `p = NULL;` để biểu diễn “không trỏ đến đối tượng/hàm hợp lệ”. **Không được giải tham chiếu** `NULL`. Con trỏ chưa khởi tạo chứa giá trị không xác định; không được đọc hay dùng nó như một địa chỉ hợp lệ. Con trỏ trỏ đến biến cục bộ sau khi biến hết lifetime, hoặc đến vùng nhớ sau `free`, trở thành con trỏ treo (dangling pointer).

### `const` áp dụng ở đâu?

~~~c
const int *read_only_value = &value;  // Không thể sửa *read_only_value qua biến này.
int *const fixed_pointer = &value;    // Không thể gán fixed_pointer sang địa chỉ khác.
const int *const fixed_read_only = &value; // Cả hai hạn chế.
~~~

`const int *` và `int const *` tương đương nhau. `const` đối với dữ liệu không đồng nghĩa với “bộ nhớ luôn bất biến trong toàn chương trình”; nó hạn chế các phép sửa thông qua lối truy cập mang kiểu const. Chuyển `int **` thành `const int **` không được C cho phép một cách ngầm định, vì sẽ phá vỡ tính an toàn của `const`.

## 3. Con trỏ và phép toán địa chỉ trên mảng

~~~c
int numbers[] = {10, 20, 30, 40};
int *p = numbers;       // Trong biểu thức này, numbers chuyển thành &numbers[0].
int second = *(p + 1);  // 20
int third = p[2];       // 30, tương đương *(p + 2).
~~~

Nếu `p` có kiểu `T *`, `p + i` di chuyển theo **i phần tử kiểu `T`**, không phải i byte. Trên nền tảng mà `sizeof(int) == 4`, `p + 1` thường cách `p` 4 byte. Phép toán được định nghĩa khi cả hai con trỏ thuộc cùng một đối tượng mảng (hoặc vị trí **ngay sau phần tử cuối** theo quy tắc C); có thể tạo con trỏ one-past, nhưng **không được giải tham chiếu** nó. Đi quá phạm vi đó là hành vi không xác định (undefined behavior).

Một mảng C có các phần tử đặt liên tiếp trong bộ nhớ; **con trỏ không tự lưu độ dài**. Đối với mảng thực sự trong cùng scope:

~~~c
int a[] = {4, 5, 6};
size_t count = sizeof a / sizeof a[0]; // 3
~~~

Sau khi truyền `a` vào hàm có tham số `int *p`, `sizeof p` chỉ cho biết **kích thước của con trỏ**, không tính số phần tử. API native thường cần truyền riêng `(pointer, length)`.

Các ngoại lệ quan trọng của chuyển mảng thành con trỏ (array-to-pointer conversion) gồm `sizeof a` và `&a`. Với `int a[3]`:
- Trong hầu hết biểu thức, `a` chuyển thành `int *` trỏ đến `a[0]`.
- `&a` có kiểu `int (*)[3]`: con trỏ tới **toàn bộ mảng ba int**.
- `sizeof a` cho kích thước cả ba phần tử; `sizeof &a` cho kích thước một con trỏ.
- Mảng không thể được gán nguyên khối bằng phép `=` như một biến con trỏ.

## 4. Con trỏ kép (`T **`): một địa chỉ trỏ đến chỗ lưu địa chỉ

`int **pp` có nghĩa `pp` trỏ đến một đối tượng kiểu `int *`. Vì vậy:

~~~c
int x = 10;
int y = 20;
int *p = &x;
int **pp = &p;

**pp = 11;  // Sửa x, vì *pp là p và **pp là *p.
*pp = &y;   // Sửa chính p để nó trỏ sang y.
**pp = 21;  // Sửa y.
~~~

Khác biệt quyết định: khi hàm nhận `int *p` theo giá trị, việc gán `p = ...` trong hàm chỉ thay đổi **bản sao con trỏ**. Nếu muốn hàm đổi con trỏ của caller, truyền địa chỉ của biến con trỏ qua `int **`.

Một ví dụ C11 **chạy độc lập**, đồng thời minh họa mảng một chiều và con trỏ tới hàng của mảng hai chiều:

~~~c
// File: PointerBasics.c
#include <stdio.h>

static void reseat(int **slot, int *new_target) {
    if (slot != NULL) {
        *slot = new_target;
    }
}

int main(void) {
    int a = 10;
    int b = 20;
    int *p = &a;
    int **pp = &p;

    **pp = 11;
    reseat(pp, &b);
    *p = 21;

    int values[] = {3, 5, 7, 9};
    int matrix[2][3] = {{1, 2, 3}, {4, 5, 6}};
    int (*row)[3] = matrix;

    printf("a=%d, b=%d\n", a, b);
    printf("values[2]=%d, *(values+2)=%d\n",
           values[2], *(values + 2));
    printf("row[1][2]=%d\n", row[1][2]);
    return 0;
}
~~~

Biên dịch và chạy (GCC/Clang, C11):

~~~sh
cc -std=c11 -Wall -Wextra -pedantic PointerBasics.c -o pointer-basics
./pointer-basics
~~~

Kết quả chính xác:

~~~text
a=11, b=21
values[2]=7, *(values+2)=7
row[1][2]=6
~~~

### `T **out` trong native API

Một mẫu chữ ký thường gặp:

~~~c
// Chỉ là giao diện minh họa, chưa phải chương trình triển khai hoàn chỉnh.
int create_buffer(size_t count, unsigned char **out_data);
void release_buffer(unsigned char *data);
~~~

`out_data` trỏ đến **ô chứa con trỏ** mà caller cấp. Hàm C có thể cấp phát buffer rồi đặt địa chỉ mới vào `*out_data`; bên gọi phải truyền `&buffer` nếu `buffer` là biến `unsigned char *`. Tài liệu API phải nêu rõ: quy ước trả lỗi, `*out_data` khi thất bại, có chấp nhận `NULL` không, kích thước thực cấp, ai gọi `release_buffer`, và có được giữ địa chỉ qua lời gọi kế tiếp không. Java FFM biểu diễn “ô chứa một địa chỉ” bằng vùng native có layout địa chỉ; JNI thường phải cung cấp hàm native bao bọc thay vì xem Java array như `T **`.

**Không nhầm `T **` với “con trỏ tới hai chiều”.** Đây là hai cấu trúc bộ nhớ khác nhau.

## 5. Ba kiểu trông giống nhau nhưng có layout khác hẳn

Với `int m[2][3] = {{1,2,3}, {4,5,6}};`, C lưu sáu `int` liên tục theo **row-major**:

~~~text
m[0][0] m[0][1] m[0][2] | m[1][0] m[1][1] m[1][2]
    1       2       3    |     4       5       6
[      hàng int[3]     ] [      hàng int[3]     ]
~~~

Khi dùng tên `m` ở hầu hết biểu thức, kiểu sau chuyển đổi là `int (*)[3]` (địa chỉ của hàng đầu tiên), **không phải `int **`. Vì vậy `int (*row)[3] = m;` là đúng, `int **wrong = m;` là không tương thích kiểu và không được ép kiểu để “chữa”.

So sánh:

| Khai báo | Đọc từ trong ra ngoài | Cách tổ chức |
|---|---|---|
| `int *p` | `p` là con trỏ tới `int` | Một địa chỉ trỏ đến `int` |
| `int **pp` | `pp` trỏ đến một `int *` | Địa chỉ trỏ đến ô lưu địa chỉ |
| `int a[3]` | `a` là mảng 3 `int` | Ba số nguyên liên tiếp |
| `int *a[3]` | `a` là mảng 3 con trỏ `int *` | Ba ô địa chỉ liên tiếp; dữ liệu đích có thể nằm rải rác |
| `int (*p)[3]` | `p` trỏ đến một mảng 3 `int` | Một địa chỉ; tăng `p` một bước là tăng một hàng 3 `int` |
| `int (*f)(int, int)` | `f` trỏ đến hàm nhận 2 `int`, trả `int` | Địa chỉ hàm, không phải vùng dữ liệu `int` |

Ví dụ với **mảng các con trỏ**:

~~~c
int x = 1, y = 2, z = 3;
int *slots[3] = {&x, &y, &z};
int **first_slot = slots; // slots chuyển thành con trỏ đến slots[0].
~~~

Ở đây `slots` thật sự có các phần tử kiểu `int *`, nên chuyển thành `int **` là phù hợp. Nhưng không thể suy ra ba đối tượng `x`, `y`, `z` nằm liên tiếp.

Một `int matrix[2][3]` không thể được diễn giải qua `int **` vì máy sẽ đọc **giá trị số nguyên trong hàng** như thể đó là **địa chỉ của hàng**, gây lỗi hoặc hành vi không xác định. Nếu cần bảng hàng động `int **rows`, thường phải cấp phát bảng con trỏ và từng vùng hàng (hoặc cấp một buffer liên tục rồi gán từng `rows[i]`), và phải thiết kế giải phóng phù hợp.

### Chỉ số hàng/cột và cách làm phẳng dữ liệu

Truy cập mảng hai chiều `matrix[i][j]` tương đương `*(*(matrix + i) + j)` khi chỉ số hợp lệ. Đối với dữ liệu 2D động mà ABI yêu cầu **một buffer phẳng**, có thể dùng:

~~~c
// flat trỏ đến ít nhất rows * cols phần tử int được cấp phát hợp lệ.
int element = flat[i * cols + j]; // 0 <= i < rows, 0 <= j < cols
~~~

Phải kiểm tra phép nhân `rows * cols` không tràn `size_t` trước khi cấp phát/truy cập. Dù bộ nhớ của `int matrix[R][C]` là liên tiếp, không nên dựa vào việc lấy `&matrix[0][0]` rồi tăng một `int *` vượt **ranh giới subarray đầu tiên** để duyệt toàn ma trận: các quy tắc phép toán con trỏ C áp dụng theo đối tượng mảng mà con trỏ đang trỏ tới. Dùng `matrix[i][j]` / `int (*)[C]`, hoặc cấp phát buffer phẳng 1D thật sự khi API nhận `int *`.

## 6. Con trỏ hàm: gọi mã thông qua địa chỉ hàm

Khác với `int *` trỏ đến dữ liệu, `int (*operation)(int, int)` trỏ tới hàm có kiểu tương ứng. Dấu ngoặc quanh `*operation` là bắt buộc để khai báo **con trỏ hàm**:

~~~c
int add(int a, int b) {
    return a + b;
}

typedef int (*binary_operation)(int, int);

binary_operation operation = add;
int result = operation(2, 3); // 5, tương đương (*operation)(2, 3).
~~~

Đây là mã minh họa khai báo; ví dụ `qsort` bên dưới là chương trình C11 hoàn chỉnh.

Con trỏ hàm cần khớp **kiểu trả về, danh sách tham số và calling convention**. Không được gọi hàm qua con trỏ có kiểu hàm không tương thích chỉ vì các địa chỉ có vẻ giống nhau. Cũng không có đảm bảo ISO C tổng quát rằng `void *` có thể chứa mọi con trỏ hàm: `void *` là con trỏ đối tượng; quy tắc chuyển đổi con trỏ hàm tùy nền tảng, loader và ABI. Một số API hệ điều hành quy định cầu nối riêng cho tra cứu biểu tượng động; phải theo đúng hợp đồng đó.

### Callback chuẩn thư viện với `qsort`

`qsort` nhận một con trỏ hàm so sánh hai phần tử. Phần tử được truyền dưới dạng `const void *`, nên comparator phải đọc theo đúng kiểu phần tử thật:

~~~c
// File: FunctionPointerSort.c
#include <stdio.h>
#include <stdlib.h>

static int compare_ints(const void *left, const void *right) {
    int a = *(const int *)left;
    int b = *(const int *)right;
    return (a > b) - (a < b);
}

int main(void) {
    int values[] = {9, -2, 7, 0, 7};
    size_t count = sizeof values / sizeof values[0];

    qsort(values, count, sizeof values[0], compare_ints);
    for (size_t i = 0; i < count; ++i) {
        if (i != 0) {
            putchar(' ');
        }
        printf("%d", values[i]);
    }
    putchar('\n');
    return 0;
}
~~~

~~~sh
cc -std=c11 -Wall -Wextra -pedantic FunctionPointerSort.c -o pointer-sort
./pointer-sort
~~~

Stdout:

~~~text
-2 0 7 7 9
~~~

Không dùng `return a - b;` làm comparator tổng quát vì có thể tràn `int`. Hàm so sánh phải trả giá trị âm/0/dương theo quan hệ thứ tự và xử lý phần tử trùng nhau nhất quán. Khi native API lưu callback để gọi **sau khi lời gọi đăng ký kết thúc**, lifetime của callback và user context cũng phải kéo dài đến lúc hủy đăng ký.

### API callback thường thấy

~~~c
// Giao diện ví dụ, không phải mã triển khai hoàn chỉnh:
typedef void (*on_item_fn)(int item, void *user_context);
void native_visit(const int *items, size_t count,
                  on_item_fn callback, void *user_context);
~~~

`callback` là địa chỉ một hàm phù hợp ABI; `user_context` là con trỏ dữ liệu truyền lại cho callback, không phải con trỏ hàm. Trên Java FFM, một **upcall stub** có thể tạo địa chỉ callable từ Java method handle; trên JNI, cần cầu nối C/JNI thích hợp. Phải xử lý hủy đăng ký, thread gọi lại, ngoại lệ Java, tái nhập (reentrancy) và lifetime của stub/context. Không chuyển bừa exception Java qua frame C như một C exception.

## 7. ABI quyết định cách các kiểu và lời gọi thực sự đi qua ranh giới

ABI (Application Binary Interface) quy định không chỉ tên kiểu C, mà cả cách tham số/giá trị trả về được đưa vào thanh ghi hoặc stack, độ lớn và alignment, layout cấu trúc, calling convention, quy tắc biểu tượng và một số yếu tố nền tảng. Hai đoạn mã có vẻ hợp lệ ở cấp source vẫn có thể không tương thích ở cấp nhị phân.

| Kiểu C / khái niệm | Điều cần kiểm tra trước khi map sang Java |
|---|---|
| `int`, `short`, `long` | Kích thước/độ có dấu theo target ABI; Java `int` cố định 32 bit, Java `long` cố định 64 bit |
| `size_t`, `ptrdiff_t` | Loại số nguyên native phụ thuộc nền tảng; không giả định tự động là C `long` hay Java `long` |
| `T *`, `void *` | Kiểu địa chỉ native; cần length/layout/lifetime để đọc vùng được trỏ tới |
| `T **` | Một địa chỉ trỏ tới ô con trỏ; cần đọc/ghi thêm một tầng địa chỉ |
| `T [N]`, `T (*)[N]` | Shape, stride và bố cục; mảng C liên tục, tham số mảng thường chuyển thành con trỏ |
| `T *[N]` | N ô con trỏ liên tiếp, khác buffer chứa N giá trị `T` |
| Con trỏ hàm | Signature + calling convention + lifetime của mã/stub |
| `struct` | Offset trường, padding, alignment, nested layout; không được đoán bằng cách cộng kích thước trường |

Ví dụ phổ biến: trên LP64 (nhiều Unix 64 bit), C `long` thường 8 byte; trên LLP64 (Windows 64 bit), C `long` thường **4 byte** dù con trỏ 8 byte. Do đó việc “máy 64 bit nên mọi `long` và pointer đều 8 byte” là sai. `sizeof` cho độ lớn theo đơn vị byte C, `_Alignof` (C11) cho alignment của kiểu. `intptr_t`/`uintptr_t` trong `<stdint.h>` là các kiểu số nguyên **tùy chọn nếu nền tảng hỗ trợ**, dùng khi cần chuyển đổi con trỏ đối tượng qua số nguyên theo quy tắc được hỗ trợ; không phải giấy phép tạo địa chỉ tùy ý hoặc chuyển con trỏ hàm sang số.

Khi cần bind một thư viện C, phải xác nhận **header và binary được build cho cùng kiến trúc/ABI**, quy ước đóng gói (packing), version, kích thước `size_t`/`long`, endianness khi diễn giải dữ liệu nhị phân và các quy định về lỗi. Đặc biệt, không dùng `int **` để thay `int (*)[N]` chỉ vì cả hai có thể có kích thước một địa chỉ.

## 8. Java liên hệ thế nào: JNI, FFM, pointer slot và callback

### Java không có `T *` như C

Một tham chiếu đối tượng Java không phải địa chỉ C ổn định được phép tự do cộng/trừ; GC có thể di chuyển đối tượng và JVM quản lý lifetime. `int[]` trên Java cũng không tự động tương thích với tham số native `int *` theo quy tắc ABI. JNI có API chuyên dụng để truy cập/copy/pin mảng primitive, đi kèm nghĩa vụ release và giới hạn của API đang dùng; đừng giữ con trỏ tới vùng tạm đó sau khi lifetime kết thúc.

JNI và FFM giải quyết bài toán khác nhau:
- **JNI** dùng hàm cầu nối native với các kiểu `jint`, `jlong`, `jobject`, `jintArray`…; lớp JNI xử lý chuyển đổi mảng/đối tượng và quản lý tương tác với JVM.
- **FFM (ổn định từ JDK 22, JEP 454)** mô hình hóa vùng nhớ bằng `MemorySegment`, lifetime bằng `Arena`, kiểu/layout bằng `MemoryLayout`/`ValueLayout`, gọi native bằng `Linker` + `FunctionDescriptor` và callback bằng upcall stub. JDK 21 có FFM ở trạng thái preview với chi tiết API/tùy chọn chạy khác; ví dụ dưới đây nhắm **JDK 22+**, không mặc định biên dịch nguyên dạng trên JDK 21.

Bảng chuyển đổi về **ý nghĩa**, không phải phép cast tự động:

| C | Mô hình FFM (JDK 22+) | Điểm kiểm tra |
|---|---|---|
| `const int *data, size_t length` | Segment địa chỉ buffer + chiều dài + layout số nguyên C tương thích | Byte size, bounds, alignment, owner |
| `int **out` | Segment cấp chỗ lưu `ValueLayout.ADDRESS` để C ghi một pointer | Pointer cấp hai; cần giải nghĩa địa chỉ nhận về và hàm free |
| `int (*)[3]` | Segment với layout hàng gồm 3 phần tử, hoặc sequence/offset tương đương | Stride hàng và kích thước phần tử |
| `void (*cb)(int, void *)` | Upcall stub từ method handle phù hợp descriptor | Lifetime, calling thread, context, unregister |
| `int (*fn)(int)` | Downcall handle cho địa chỉ hàm với đúng function descriptor | Signature, ABI, native-access requirement |

Một segment chỉ là vùng có **địa chỉ, byteSize và phạm vi truy cập**. Không đủ thông tin để suy ra “bao nhiêu phần tử” từ địa chỉ C. Nếu đọc một địa chỉ với `ValueLayout.ADDRESS` **không khai báo target layout**, segment đại diện địa chỉ đó mặc định có `byteSize() == 0`. Không được giải tham chiếu nó như buffer hữu hạn khi chưa có bounds và lifetime đáng tin cậy; các thao tác FFM thay đổi bounds/mô tả vùng gốc có thể là restricted và tiềm ẩn hỏng bộ nhớ nếu khai báo sai.

### Ví dụ Java FFM: buffer liên tục và ô chứa con trỏ

Chương trình sau dùng **JDK 22+**, không cần thư viện C ngoài. Nó minh họa hai vùng native: một buffer ba `int` và một pointer slot kiểu `ADDRESS`. Nó **không** tự giải tham chiếu raw pointer trả về:

~~~java
// File: PointerSlotDemo.java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerSlotDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            long intBytes = ValueLayout.JAVA_INT.byteSize();
            MemorySegment values = arena.allocate(
                    3L * intBytes, ValueLayout.JAVA_INT.byteAlignment());

            values.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            values.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            values.setAtIndex(ValueLayout.JAVA_INT, 2, 30);

            MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
            pointerSlot.set(ValueLayout.ADDRESS, 0, values);

            MemorySegment rawAddress = pointerSlot.get(ValueLayout.ADDRESS, 0);
            System.out.println("values[1] = "
                    + values.getAtIndex(ValueLayout.JAVA_INT, 1));
            System.out.println("address view bytes = " + rawAddress.byteSize());
        }
    }
}
~~~

~~~sh
javac PointerSlotDemo.java
java PointerSlotDemo
~~~

Stdout theo hợp đồng JDK 22:

~~~text
values[1] = 20
address view bytes = 0
~~~

`values` được cấp phát trong arena nên có giới hạn ba phần tử và bị vô hiệu hóa sau khi arena đóng. `pointerSlot` chứa **giá trị địa chỉ** tới buffer đó, tương đương ý tưởng một biến `int *` mà C có thể dùng thông qua `int **`. `rawAddress` mặc định chỉ là một address view zero-sized; khi nó được đọc ra, phạm vi truy cập của view đó **không tự kế thừa** lifetime/bounds của buffer gốc. Không dùng rawAddress sau khi buffer bị giải phóng. Ví dụ đang dùng `JAVA_INT` cho các giá trị Java 32 bit; khi bind C thật, chỉ dùng layout đó nếu đã xác minh C `int` của target ABI tương ứng.

## 9. Thiết kế một hợp đồng C–Java đúng khi nhận pointer

Giả sử một thư viện đưa ra giao diện:

~~~c
// Header minh họa cho phân tích hợp đồng, không có implementation:
typedef int (*transform_fn)(int value, void *user_context);

int transform_buffer(const int *input, size_t count,
                     int **output, transform_fn fn,
                     void *user_context);
void transform_free(int *output);
~~~

Hãy tách từng đối tượng:
1. `input`: địa chỉ đầu của **count phần tử int**; Java phải bảo đảm vùng đọc tồn tại và đủ kích thước trong lúc gọi, và C không sửa vì tham số mang `const`.
2. `count`: một `size_t` theo ABI; kiểm tra overflow của `count * sizeof(int)`, không đồng nhất tự động với Java `int`.
3. `output`: một **pointer slot** (`int **`); C ghi con trỏ kết quả vào `*output`. Java không được truyền trực tiếp địa chỉ của buffer kết quả như thể đó là con trỏ kép.
4. `fn`: con trỏ hàm callback khớp signature native; nếu C giữ lại thì upcall stub cần sống qua mọi lần gọi.
5. `user_context`: dữ liệu context/handle của caller được truyền nguyên nghĩa; phải nêu rõ C có dereference hay chỉ chuyển tiếp; không giả định đó là Java object reference.
6. `transform_free`: hàm giải phóng kết quả theo đúng allocator của thư viện; không tự dùng `free` từ một runtime/CRT khác nếu hợp đồng đòi hàm release riêng.

Vì giao diện minh họa không cho biết trường hợp lỗi, độ dài `output`, callback chạy đồng bộ hay bất đồng bộ và quyền sở hữu của `user_context`, **chưa thể viết một binding an toàn hoàn chỉnh** chỉ từ chữ ký. Phải đọc hợp đồng thư viện hoặc bổ sung API trả chiều dài và chính sách lifetime.

Một đặc tả tối thiểu cho mỗi tham số native nên trả lời: kiểu và layout nào; có cho `NULL` không; đọc/ghi bao nhiêu byte; alignment nào; ai cấp phát/giải phóng; dùng trong bao lâu; có giữ callback/địa chỉ lại không; có được gọi từ thread khác không; ý nghĩa của lỗi và cách khôi phục. Đối với `struct`, xác minh offset/padding thay vì dựa vào phỏng đoán.

## 10. Lỗi phổ biến và cách phát hiện

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `int **p = matrix;` với `int matrix[R][C]` | Hiểu số nguyên thành địa chỉ, UB | Dùng `int (*p)[C] = matrix;` hoặc buffer phẳng đúng contract |
| Truyền `int *p` khi hàm đòi `int **out` | Hàm ghi địa chỉ vào dữ liệu đích thay vì pointer slot | Tạo biến `int *p` rồi truyền `&p`; trong FFM cấp pointer slot |
| Dùng `sizeof(pointer)` để tính số phần tử | Sai độ dài, đọc/ghi quá biên | Truyền `length` riêng và kiểm tra phép nhân kích thước |
| Trả về địa chỉ của biến local đã hết lifetime | Dangling pointer / use-after-scope | Caller cung cấp buffer, hoặc cấp phát với ownership rõ |
| Dùng con trỏ sau `free`/đóng Arena | Use-after-free, crash hoặc hỏng dữ liệu | Ràng buộc lifetime và không giữ địa chỉ quá hạn |
| Ép con trỏ tùy tiện để “khớp” `T **` / `T (*)[N]` | Sai layout và dereference UB | Sửa signature/layout thật |
| Gọi callback bằng descriptor/calling convention sai | Sai tham số, return và có thể crash | Match chính xác prototype + ABI |
| C giữ callback Java sau khi Arena đóng | Gọi vào stub không còn sống | Giữ arena/stub sống đến khi native unregister xong |
| Giả định C `long` luôn 64 bit | Đọc sai byte/đẩy sai đối số | Kiểm tra LP64/LLP64 và canonical layout |
| Cast địa chỉ số nguyên không kiểm chứng thành pointer | Vi phạm alignment/lifetime/provenance | Chỉ dùng địa chỉ hợp lệ từ native allocator/API |
| Dùng một loại `free` cho mọi vùng native | Sai allocator/heap boundary | Gọi hàm release chính thức của nhà cung cấp |

Khi debug, ưu tiên kiểm tra **prototype C thực tế, target ABI, số byte, địa chỉ, quyền sở hữu và thời điểm callback**; một segmentation fault phát sinh sau đó thường chỉ là triệu chứng. Trên C có thể bổ sung cảnh báo compiler và AddressSanitizer/UndefinedBehaviorSanitizer khi toolchain hỗ trợ, nhưng sanitizer không thay thế hợp đồng native đúng.

## 11. Tự kiểm tra

**Câu 1.** Với `int v[4]`, `int *a = v;` và `int (*b)[4] = &v;`, `a + 1` và `b + 1` khác nhau thế nào?

**Đáp án:** `a + 1` tăng một `int` trong mảng; `b + 1` tăng một **mảng bốn int**, tức đến vị trí ngay sau đối tượng `v` nếu phép tính hợp lệ. Không giải tham chiếu con trỏ one-past.

**Câu 2.** Vì sao không thể truyền `int m[2][3]` cho tham số `int **rows`?

**Đáp án:** `m` chuyển thành `int (*)[3]`, con trỏ đến hàng liên tục. `rows` lại đòi một vùng chứa những ô `int *`. Mã native sẽ đọc bytes của `int` như địa chỉ khi giải tham chiếu tầng thứ nhất.

**Câu 3.** Khi native hàm C có tham số `int **result` và caller cần nhận một `int *` mới, caller truyền gì?

**Đáp án:** Truyền **địa chỉ của biến con trỏ** (`&ptr` trong C), hoặc cấp pointer slot có layout ADDRESS trong FFM và để C ghi địa chỉ mới vào đó. Phải xác nhận cách lấy length và giải phóng buffer.

**Câu 4.** Khi nào callback Java qua FFM không thể đóng arena ngay sau lúc đăng ký?

**Đáp án:** Khi native giữ con trỏ hàm để gọi lại bất đồng bộ hoặc sau khi lời gọi đăng ký đã return; stub và context phải sống tới khi native xác nhận đã hủy/không còn callback đang chạy.

## 12. Tóm lược theo một chuỗi suy luận

Đọc một chữ ký C, trước hết xác định **đó là đối tượng, ô con trỏ, mảng, hay hàm**. Tiếp đó xác định số lượng phần tử/stride, cách đánh địa chỉ hợp lệ, target ABI, rồi mới chọn biểu diễn bên Java. `T *` là địa chỉ tới dữ liệu `T`; `T **` là địa chỉ tới **một con trỏ**; `T (*)[N]` di chuyển theo từng hàng `N` phần tử; `T *[N]` là mảng của `N` con trỏ; `R (*)(Args...)` là con trỏ tới hàm đúng chữ ký. Cả những kiểu mang cùng kích thước địa chỉ vẫn có **ngữ nghĩa giải tham chiếu và layout khác nhau**.

**Tham khảo để đối chiếu API Java:** JEP 454 (https://openjdk.org/jeps/454); [Java SE 22 `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html); [`AddressLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html); [`MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html). Với mã C, đối chiếu prototype thực tế và quy tắc của chuẩn C/ABI target thay vì suy diễn từ độ lớn con trỏ.