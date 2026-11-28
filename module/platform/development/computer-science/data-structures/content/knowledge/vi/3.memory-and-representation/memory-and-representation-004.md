# Tính cục bộ dữ liệu và ảnh hưởng của bộ nhớ đệm

Hai thuật toán cùng duyệt `n` phần tử, đều có độ phức tạp thời gian **O(n)**, nhưng có thể chênh lệch đáng kể về thời gian chạy. Một lý do quan trọng là **CPU cần lấy dữ liệu từ bộ nhớ**: nếu các phần tử cần xử lý nằm gần nhau hoặc được sử dụng lại trước khi rời cache, CPU thường ít phải chờ dữ liệu hơn.

Trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**, thuộc chương **Bộ nhớ và biểu diễn**, bài này giúp lý giải hiệu năng của mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Mục tiêu là kết hợp **bất biến, thao tác, độ phức tạp thời gian, chi phí bộ nhớ và hành vi cache** để chọn cấu trúc phù hợp với từng bài toán.

Học xong bài này, người học có thể phân biệt cục bộ không gian và thời gian, giải thích cache line/cache miss/working set, nhận biết các mẫu truy cập kém hiệu quả và thử những cách cải thiện như thay thứ tự duyệt, bố trí dữ liệu theo trường và chia khối xử lý.

## 1. Bộ nhớ đệm là gì và tại sao cần đến nó?

CPU thực hiện phép toán rất nhanh, nhưng việc lấy dữ liệu từ RAM thường tốn nhiều thời gian hơn so với lấy từ một bộ nhớ nhỏ đặt gần lõi xử lý. Vì vậy nhiều máy tính dùng hệ phân cấp bộ nhớ:

```text
        Gần lõi CPU, thường nhanh, dung lượng nhỏ
                      +----------+
                      | Thanh ghi|
                      +----------+
                           |
                         +----+
                         | L1 |
                         +----+
                           |
                         +----+
                         | L2 |
                         +----+
                           |
                         +----+
                         | L3 |   (có thể chia sẻ giữa các lõi)
                         +----+
                           |
                         +-----+
                         | RAM |
                         +-----+
       Xa lõi hơn, thường chậm, dung lượng lớn hơn
```

Đây là một **mô hình điển hình**, không phải cấu hình cố định của mọi CPU: số cấp, dung lượng, độ trễ, khả năng chia sẻ và quan hệ giữa các cache phụ thuộc phần cứng. Bộ nhớ đĩa không phải một cấp cache CPU theo nghĩa sơ đồ trên.

Khi truy cập dữ liệu đã có sẵn trong cấp cache cần xét, CPU nhận được **cache hit**. Khi không tìm thấy, xảy ra **cache miss**, dữ liệu có thể được lấy từ cache cấp khác hoặc bộ nhớ chính. Một cache miss không đồng nghĩa lúc nào cũng phải đọc tới RAM.

### 1.1. Cache line: nhiều byte đi cùng một lần

**Cache line** là đơn vị khối dữ liệu mà nhiều cache CPU quản lý. **64 byte** là kích thước cache line thường gặp nhưng không phải một bảo đảm cho mọi kiến trúc.

Giả sử `sizeof(int) = 4` byte, cache line dài 64 byte và mảng `int` bắt đầu đúng ranh giới line. Khi đó một cache line có thể chứa 16 phần tử liên tiếp:

```text
Một cache line 64 byte
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
| a0 | a1 | a2 | a3 | a4 | a5 | a6 | a7 | a8 | a9 |a10 |a11 |a12 |a13 |a14 |a15 |
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
       Mỗi phần tử int chiếm 4 byte trong giả định.
```

Khi đọc `a[0]`, hệ thống có thể nạp cả line chứa `a[0]` đến `a[15]`. Những lần đọc `a[1]`, `a[2]`, ... có cơ hội sử dụng cùng line đã nạp. Nếu địa chỉ đầu của mảng **lệch ranh giới cache line**, 16 phần tử liên tiếp có thể trải trên hai line; điều đó cho thấy việc tính số line phải xét căn chỉnh.

Một line đã nạp **không được bảo đảm ở lại cache mãi**: cache có dung lượng hữu hạn, cơ chế thay thế, tranh chấp với dữ liệu khác và tương tác giữa các lõi.

### 1.2. Phân biệt cache line, trang bộ nhớ và TLB

Một **trang bộ nhớ (memory page)** là đơn vị thường dùng trong cơ chế bộ nhớ ảo. **TLB** là bộ nhớ đệm thông tin dịch địa chỉ ảo sang địa chỉ vật lý. Chúng khác với cache line dữ liệu.

| Khái niệm | Tác dụng chính | Vấn đề liên quan |
| --- | --- | --- |
| Cache line | Đưa và lưu khối dữ liệu gần CPU | Cache miss, chờ dữ liệu |
| Trang bộ nhớ | Tổ chức, ánh xạ không gian địa chỉ ảo | Page fault khi cần hệ điều hành xử lý |
| TLB | Tăng tốc dịch địa chỉ ảo | TLB miss, thêm công việc dịch địa chỉ |

**TLB miss không đồng nghĩa với page fault**, và page fault cũng không giống một cache miss dữ liệu thông thường. Khi các nút của cấu trúc dữ liệu phân tán trên nhiều trang, chúng có thể gây áp lực lên cả cache và TLB.

## 2. Hai dạng tính cục bộ dữ liệu

### 2.1. Cục bộ không gian (spatial locality)

Chương trình có **cục bộ không gian** khi sau khi truy cập một địa chỉ, nó có xu hướng truy cập các địa chỉ **gần đó**.

Ví dụ: duyệt một mảng `int` liên tiếp.

```c
#include <stddef.h>

long long sum_array(const int *a, size_t n) {
    long long sum = 0;
    for (size_t i = 0; i < n; ++i) {
        sum += a[i];
    }
    return sum;
}
```

Nếu `a` trỏ tới một mảng có ít nhất `n` phần tử hợp lệ, các lần đọc `a[i]` và `a[i+1]` thường nằm gần nhau. Khi một line được nạp, nhiều phần tử kế tiếp có thể dùng lại line đó. CPU còn có thể **đọc trước (hardware prefetch)** các line sắp được dùng khi phát hiện mẫu truy cập tuần tự.

Ví dụ khác gồm duyệt một chuỗi byte, quét mảng đỉnh kề của đồ thị, hoặc duyệt một đoạn dữ liệu kiểu cấu trúc SoA được mô tả ở phần sau.

### 2.2. Cục bộ thời gian (temporal locality)

Chương trình có **cục bộ thời gian** khi một địa chỉ vừa được dùng có khả năng được dùng lại **sớm**.

```c
int counter = 0;
for (int i = 0; i < 1000; ++i) {
    ++counter;
}
```

Ở mức ý tưởng, nếu `counter` được đọc/ghi từ bộ nhớ mỗi vòng thì chương trình dùng lại cùng vị trí. Nhưng ở mức mã máy, trình biên dịch có thể giữ nó trong **thanh ghi** hoặc tính luôn kết quả; không được dùng ví dụ này để khẳng định có đúng 1.000 lượt truy cập cache.

Trong cấu trúc dữ liệu, cục bộ thời gian thường xuất hiện khi nhiều thao tác cùng dùng phần tử đầu stack, các nút gần gốc của cây tìm kiếm, một số khóa được tra nhiều lần trong bảng băm, hoặc một mảng nhỏ được xử lý qua nhiều lượt.

| Mẫu truy cập | Cục bộ không gian | Cục bộ thời gian |
| --- | --- | --- |
| Quét một mảng lớn duy nhất một lượt | Thường tốt | Có thể thấp |
| Liên tục dùng lại một vài giá trị | Không nhất thiết nổi bật | Thường tốt |
| Lặp xử lý mảng nhỏ theo thứ tự | Thường tốt | Thường tốt |
| Theo con trỏ tới các nút rời rạc chỉ một lượt | Có thể kém | Có thể thấp |

**Cục bộ là đặc điểm của mẫu truy cập**, không chỉ là một thuộc tính cố định của kiểu dữ liệu.

## 3. Working set và các loại cache miss

**Working set** là tập vùng dữ liệu thực sự được chương trình truy cập trong một khoảng hoạt động có ý nghĩa. Khi working set phù hợp với khả năng lưu giữ của cache, cơ hội tái sử dụng line thường tốt hơn.

Ví dụ giả định: một thuật toán thường xuyên xử lý bảng 16 KiB và một thuật toán khác truy cập ngẫu nhiên mảng 2 GiB. Với các điều kiện khác tương tự, dữ liệu của thuật toán đầu có khả năng được cache giữ lại tốt hơn. Nhưng **nhỏ hơn dung lượng cache không có nghĩa chắc chắn 100% hit**, vì còn ánh xạ địa chỉ vào các set, tính liên kết (*associativity*), cơ chế thay thế và dữ liệu cạnh tranh.

Ba loại cache miss thường được sử dụng trong mô hình giải thích:

| Loại miss | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Compulsory / cold | Line chưa có khi cần dùng lần đầu | Lượt quét đầu của mảng mới |
| Capacity | Không đủ dung lượng giữ working set hiệu quả | Nhiều tập dữ liệu lớn thay nhau được sử dụng |
| Conflict | Nhiều địa chỉ cạnh tranh các vị trí/set của cache | Mẫu địa chỉ ánh xạ bất lợi trong cache có số way hữu hạn |

Trên CPU hiện đại, prefetch, nhiều cấp cache và hoạt động nhiều lõi khiến việc gán chính xác một miss vào một nhóm không phải lúc nào cũng đơn giản.

## 4. Mảng và danh sách liên kết: cùng O(n), khác cách lấy dữ liệu

Mảng liên tiếp cho phép tính địa chỉ phần tử trực tiếp từ chỉ số:

`address(a[i]) = base + i × sizeof(T)`.

Với danh sách liên kết, phải đọc trường `next` của nút hiện tại để biết địa chỉ nút tiếp theo.

```text
Mảng (địa chỉ tăng đều):
[10][20][30][40][50][60] ...

Danh sách liên kết (địa chỉ nút có thể không tăng theo thứ tự):
head -> Node(10) -> Node(20) -> Node(30) -> Node(40) -> NULL
        0x9000      0x1300      0x7000      0x3100
        (địa chỉ chỉ để minh họa)
```

Một lượt quét `n` phần tử của cả hai cách biểu diễn đều là **O(n)** trong mô hình bước xử lý. Tuy nhiên, mảng thường có cục bộ không gian tốt và dễ đọc trước; danh sách liên kết có thể phải chờ lấy địa chỉ `next` từng bước, đồng thời mỗi nút còn mang con trỏ, padding và có thể phí cấp phát.

```c
#include <stddef.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

long long sum_array(const int *a, size_t n) {
    long long sum = 0;
    for (size_t i = 0; i < n; ++i) {
        sum += a[i];
    }
    return sum;
}

long long sum_list(const Node *head) {
    long long sum = 0;
    for (const Node *p = head; p != NULL; p = p->next) {
        sum += p->value;
    }
    return sum;
}
```

Hai hàm đều có thời gian **O(n)** (với `n` là số phần tử) và bộ nhớ phụ **O(1)**, nhưng không được suy ra thời gian thực tế bằng nhau. Các nút cấp phát từ pool gần nhau có thể cải thiện tính cục bộ; danh sách cũng có thể phù hợp hơn khi thường xuyên **chèn/xóa nút đã biết vị trí**, vì nối liên kết chỉ cần O(1) thao tác sau khi đã có nút liên quan. Nếu phải tìm vị trí, chi phí tìm có thể O(n).

### 4.1. Bài toán tính số cache line

Giả sử `int` 4 byte, cache line 64 byte, mảng 2.048 `int` bắt đầu đúng ranh giới line:

```text
Dung lượng mảng: 2.048 × 4 = 8.192 byte
Số line chứa mảng: 8.192 / 64 = 128 line
```

Nếu chỉ đọc `a[0]`, `a[16]`, `a[32]`, ... trong một lượt quét lạnh, mỗi lần truy cập lấy 4 byte từ một line 64 byte mới. Tỷ lệ byte **được sử dụng ngay** trên mỗi line là `4/64 = 6,25%`. Đó **không phải tỷ lệ cache hit**. Nếu phần mềm sau đó quay lại dùng các phần tử khác trong cùng line khi line vẫn còn ở cache, hiệu quả sử dụng line sẽ khác.

## 5. Stride: khoảng cách giữa các địa chỉ được đọc

**Stride** là bước nhảy giữa các địa chỉ truy cập kế tiếp, thường tính theo số phần tử hoặc số byte.

```c
#include <stddef.h>

long long sum_all(const int *a, size_t n) {
    long long total = 0;
    for (size_t i = 0; i < n; ++i)
        total += a[i];       /* Stride 1 int */
    return total;
}

long long sum_every_16th(const int *a, size_t n) {
    long long total = 0;
    for (size_t i = 0; i < n; i += 16)
        total += a[i];       /* Stride 16 int */
    return total;
}
```

Khi `sizeof(int)=4`, hai mẫu có bước địa chỉ tương ứng 4 byte và 64 byte. Stride lớn có thể khiến mỗi line được đọc chỉ đóng góp một phần nhỏ dữ liệu hữu ích. Mẫu truy cập ngẫu nhiên trên working set lớn còn khó đọc trước hơn. Nhưng một số CPU vẫn có thể prefetch mẫu stride có quy luật.

Lưu ý hàm thứ hai thực hiện **ít phép cộng hơn**, nên không được so sánh thời gian tổng giữa hai hàm rồi kết luận stride 16 nhanh/chậm hơn trên mỗi phần tử. Để đánh giá đúng, phải thiết kế benchmark giữ công việc tương đương và kiểm soát tối ưu trình biên dịch.

## 6. Ma trận C: duyệt hàng và duyệt cột

Mảng hai chiều C `int matrix[ROWS][COLS]` được lưu theo **row-major order**: các phần tử cùng hàng nằm liền nhau trước hàng tiếp theo.

```text
matrix[3][4]:
Hàng 0: a00 a01 a02 a03
Hàng 1: a10 a11 a12 a13
Hàng 2: a20 a21 a22 a23

Trong bộ nhớ:
a00 a01 a02 a03 | a10 a11 a12 a13 | a20 a21 a22 a23
```

Hai vòng lặp sau tính cùng tổng nhưng có thứ tự truy cập khác nhau:

```c
#include <stdio.h>

enum { ROWS = 1024, COLS = 1024 };
static int matrix[ROWS][COLS];

int main(void) {
    for (int r = 0; r < ROWS; ++r)
        for (int c = 0; c < COLS; ++c)
            matrix[r][c] = (r + c) % 101;

    long long row_sum = 0;
    for (int r = 0; r < ROWS; ++r)
        for (int c = 0; c < COLS; ++c)
            row_sum += matrix[r][c]; /* Liên tiếp */

    long long column_sum = 0;
    for (int c = 0; c < COLS; ++c)
        for (int r = 0; r < ROWS; ++r)
            column_sum += matrix[r][c]; /* Nhảy giữa hàng */

    printf("row=%lld, column=%lld\n", row_sum, column_sum);
    return 0;
}
```

Nếu `int` là 4 byte, khoảng cách giữa `matrix[r][c]` và `matrix[r+1][c]` là `1024 × 4 = 4096` byte. Vòng duyệt theo cột có thể chạm nhiều line khác nhau trước khi quay lại sử dụng những phần tử kế bên, còn duyệt theo hàng có cục bộ không gian thuận lợi hơn.

Đây là **ví dụ về mẫu truy cập**, không phải benchmark có kết luận tốc độ cố định. Trình biên dịch có thể biến đổi vòng lặp; cache lớn, prefetch và phần cứng khác nhau cũng ảnh hưởng kết quả.

Mảng C `int a[R][C]` khác với `int **a`: con trỏ tới con trỏ **không bảo đảm** các hàng lưu liền nhau. Trong Java, `int[][]` là mảng các tham chiếu tới mảng con. Với thư viện ma trận, layout còn có thể là column-major hay mảng nhìn qua stride. **Trước khi đổi thứ tự duyệt, luôn xác định layout vật lý thật của dữ liệu.**

## 7. Bố trí dữ liệu: AoS và SoA

Ngoài thứ tự duyệt, **cách nhóm các trường của phần tử** cũng quyết định tỷ lệ dữ liệu hữu ích được đưa vào cache. Giả sử chương trình mô phỏng nhiều hạt với vị trí và vận tốc:

```c
typedef struct Particle {
    float x, y, vx, vy;
} Particle;

/* AoS: mỗi phần tử có tất cả trường của một hạt. */
Particle particles[1000];

/* SoA: mỗi trường của toàn bộ hạt nằm trong một mảng riêng. */
float x[1000], y[1000], vx[1000], vy[1000];
```

**AoS (Array of Structures):**

```text
| x0 y0 vx0 vy0 | x1 y1 vx1 vy1 | x2 y2 vx2 vy2 | ...
```

**SoA (Structure of Arrays):**

```text
x : | x0 | x1 | x2 | ...
y : | y0 | y1 | y2 | ...
vx: |vx0 |vx1 |vx2 | ...
vy: |vy0 |vy1 |vy2 | ...
```

Nếu phép thống kê **chỉ đọc tất cả giá trị `x`**, SoA có thể tận dụng cache line tốt hơn: các giá trị cần dùng nằm liên tiếp, không phải tải thêm trường `y`, `vx`, `vy` của mỗi đối tượng. Layout này cũng có thể thuận lợi cho các phép toán vector. Ngược lại, nếu thao tác cần **đọc và ghi toàn bộ trường của một hạt**, AoS có thể thuận tiện hơn.

| Nhu cầu | Bố trí đáng cân nhắc | Đánh đổi |
| --- | --- | --- |
| Duyệt chỉ một thuộc tính của rất nhiều đối tượng | SoA | Dữ liệu cùng trường liên tiếp; quản lý nhiều mảng |
| Thao tác từng đối tượng đầy đủ | AoS | Các trường cùng đối tượng nằm gần nhau |
| Tính toán vector trên một trường | SoA | Có thể vector hóa thuận lợi; phụ thuộc compiler và phần cứng |
| Chèn/xóa nguyên đối tượng giữa dãy | Tùy workload | AoS dịch struct; SoA cần dịch đồng bộ nhiều mảng |

**Bất biến quan trọng của SoA:** cùng chỉ số `i` trong mọi mảng phải đại diện cho **cùng một hạt**. Nếu xóa, đổi thứ tự hoặc chuyển một phần tử, phải cập nhật các mảng tương ứng cùng cách. Dùng SoA sai bất biến có thể gây lỗi kết quả dù tối ưu cache tốt.

AoS và SoA không tự quyết định độ phức tạp của thuật toán; chúng chủ yếu tác động tới **vị trí dữ liệu, số line phải đọc và thuận lợi cho mã máy**.

## 8. Tái sử dụng cache bằng chia khối (blocking/tiling)

Một thuật toán có thể thường xuyên cần lại các phần tử vừa truy cập. Nếu working set của một giai đoạn quá lớn, những phần tử ấy có thể bị thay thế khỏi cache trước khi tái sử dụng. **Blocking** (hay **tiling**) chia việc tính thành các khối nhỏ hơn để tăng cục bộ thời gian và không gian trong từng khối.

Ví dụ nhân hai ma trận `N × N`: phiên bản trực tiếp với thứ tự `i, j, k` thường duyệt phần tử `B[k][j]` theo cột khi `k` biến đổi nhanh, tạo stride lớn trên ma trận row-major:

```c
/* Minh họa: A, B, C là ma trận N x N hợp lệ đã khởi tạo. */
for (int i = 0; i < N; ++i)
    for (int j = 0; j < N; ++j)
        for (int k = 0; k < N; ++k)
            C[i][j] += A[i][k] * B[k][j];
```

Đây là một cách chia khối đơn giản. Các kích thước cố ý chia hết để tập trung vào mẫu truy cập:

```c
#include <stdio.h>

enum { N = 64, BLOCK = 16 };
static float A[N][N], B[N][N], C[N][N];

int main(void) {
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            A[i][j] = (float)((i + j) % 7);
            B[i][j] = (i == j) ? 1.0f : 0.0f;
        }
    }

    for (int ii = 0; ii < N; ii += BLOCK) {
        for (int kk = 0; kk < N; kk += BLOCK) {
            for (int jj = 0; jj < N; jj += BLOCK) {
                for (int i = ii; i < ii + BLOCK; ++i) {
                    for (int k = kk; k < kk + BLOCK; ++k) {
                        float aik = A[i][k];
                        for (int j = jj; j < jj + BLOCK; ++j) {
                            C[i][j] += aik * B[k][j];
                        }
                    }
                }
            }
        }
    }

    printf("C[3][5] = %.0f\n", C[3][5]);
    return 0;
}
```

**Cách hoạt động:** khi `j` chạy trong một khối, các lần đọc `B[k][j]` và cập nhật `C[i][j]` tiến qua đoạn liên tiếp. Một `A[i][k]` được lấy ra dùng cho nhiều `j`; một đoạn `B`/`C` có cơ hội được dùng lại trước khi chuyển sang khối khác.

Cả hai cách nhân ma trận vẫn thực hiện **O(N³)** phép nhân/cộng về bậc tăng trưởng. Chia khối tác động chủ yếu đến **mẫu truy cập và số lần nạp dữ liệu**, không làm biến đổi bài toán nhân ma trận thành O(N²).

Chọn `BLOCK` không có công thức cố định: khối quá nhỏ tăng chi phí điều khiển, khối quá lớn có thể vượt dung lượng cache. Với `N` không chia hết cho `BLOCK`, phải chặn các cận bằng `min(N, start + BLOCK)`; ví dụ này chọn `N=64`, `BLOCK=16` nên không có phần khối dư. Thư viện số học chuyên dụng có thể dùng nhiều kỹ thuật phức tạp hơn, gồm vectorization, chia nhiều tầng và đa luồng.

## 9. Ảnh hưởng đối với từng họ cấu trúc dữ liệu

### 9.1. Mảng, mảng động và mảng con trỏ

Mảng chứa giá trị trực tiếp trong vùng liên tiếp, phù hợp cho duyệt tuần tự và đọc phần tử theo chỉ số O(1). Mảng động có thể có `capacity` lớn hơn `size`: vùng dự phòng tiêu tốn bộ nhớ để giảm tần suất cấp phát lại. Việc tăng dung lượng có thể phải sao chép các phần tử, nhưng thêm cuối với chính sách tăng theo cấp số nhân thường có **O(1) amortized**.

Với **mảng chứa con trỏ/tham chiếu**, các ô con trỏ nằm liên tiếp nhưng đối tượng được trỏ tới có thể nằm xa nhau. Phải phân biệt chi phí đọc các **con trỏ** và chi phí dereference để đọc **đối tượng đích**.

### 9.2. Danh sách liên kết

Danh sách đơn/đôi liên kết các nút bằng `next` và có thể `prev`. Việc chèn/xóa một nút khi đã có thông tin liên kết phù hợp có thể tốn O(1), nhưng xác định vị trí bằng cách duyệt từ đầu thường tốn O(n). Các nút có thể cấp phát rời rạc, tạo áp lực cache và TLB khi duyệt; danh sách đôi còn có thể có overhead bộ nhớ lớn hơn.

Một **object pool/arena** có thể đặt nhiều nút trong các khối gần nhau để cải thiện locality và giảm chi phí cấp phát. Tuy vậy, điều đó không bảo đảm tất cả nút xuất hiện đúng thứ tự vật lý của danh sách, và không loại bỏ chi phí con trỏ.

### 9.3. Stack và queue

**Stack** dùng mảng động thường hưởng lợi từ việc thao tác liên tục gần cuối mảng; phiên bản danh sách liên kết có thêm con trỏ và cấp phát nút, nhưng vẫn có thể phù hợp với các ràng buộc cụ thể.

**Queue** có thể dùng **mảng vòng (circular buffer)**: dùng chỉ số `head`/`tail` luân chuyển trong vùng liên tiếp. Thêm cuối và lấy đầu tốn O(1) khi còn dung lượng; khi mở rộng mảng động cần phân tích thêm chi phí amortized. Ngược lại, xóa đầu mảng động theo kiểu phải dịch tất cả phần tử thường O(n) mỗi lần, không phù hợp với queue lớn có nhiều lần lấy đầu.

### 9.4. Binary heap, cây liên kết và B-tree

**Binary heap** thường dùng mảng: ở chỉ số `i` (bắt đầu từ 0), con trái `2i+1`, con phải `2i+2`, cha của `i>0` là `(i-1)/2`. Dữ liệu tập trung trong vùng liên tiếp và không phải trả hai con trỏ cho mỗi nút. Tuy nhiên, các thao tác sift vẫn đi qua nhiều vị trí trong mảng, nên không phải thao tác nào cũng quét tuần tự.

**Cây nút liên kết** chứa con trỏ `left`, `right` và có thể metadata cân bằng. Truy vấn theo một đường gốc–lá đi qua `h` mức thường có O(h) bước; hiệu năng thực tế còn phụ thuộc việc các nút có ở cache hay không. Nút gần gốc có thể có cục bộ thời gian khi nhiều truy vấn đều đi qua đó.

**B-tree/B+ tree** lưu nhiều khóa và liên kết con trong mỗi nút lớn, có thể giảm số mức phải truy cập và tăng lượng dữ liệu hữu ích mỗi lần đọc một nút. Tùy mục tiêu (RAM, SSD, hệ thống tập tin), kích thước nút thường được thiết kế theo đơn vị truyền và cách phân trang thích hợp.

### 9.5. Bảng băm: số bước không bằng số cache miss

**Open addressing** thường lưu mục trong một mảng ô và xử lý va chạm bằng chuỗi probe. Một số cách probe có tính liên tiếp tốt; hiệu năng phụ thuộc hệ số tải, clustering, kích thước mục và cách đánh dấu ô đã xóa.

**Separate chaining** dùng mảng bucket trỏ tới các chuỗi nút hoặc container khác. Cách này linh hoạt ở một số workload nhưng có thể phát sinh nhiều dereference và cấp phát theo nút. Không phải mọi bảng băm kiểu open addressing đều nhanh hơn mọi bảng băm dùng chaining.

Tra cứu trung bình có thể O(1) trong giả định hash và hệ số tải phù hợp, nhưng **O(1) không bảo đảm một cache hit**. Bảng lớn, nhiều probe và key/value có kích thước lớn đều ảnh hưởng thời gian.

### 9.6. Đồ thị: danh sách kề và CSR

Đồ thị thường được biểu diễn bằng danh sách các đỉnh kề. Nếu mỗi cạnh được lưu qua một nút liên kết riêng, traversal có thể phải theo nhiều con trỏ. Một lựa chọn cho đồ thị thưa ít thay đổi là **CSR (Compressed Sparse Row)**, dùng các mảng liên tiếp:

```text
Ba đỉnh A, B, C với:
A -> B, C
B -> C
C -> (không có cạnh)

offsets = [0, 2, 3, 3]
edges   = [B, C, C]

Hàng xóm của đỉnh i ở edges[offsets[i] ... offsets[i+1]-1]
A: edges[0..1] = [B, C]
B: edges[2..2] = [C]
C: đoạn rỗng
```

CSR có tính cục bộ tốt khi duyệt các hàng xóm của một đỉnh, nhưng thêm/xóa cạnh tùy ý có thể cần di chuyển dữ liệu hoặc xây lại cấu trúc. BFS/DFS có độ phức tạp O(V+E) trên cách biểu diễn danh sách kề thích hợp, song trạng thái `visited` và mẫu truy cập thực tế có thể làm thời gian chạy khác nhau dù cùng Big-O.

## 10. Big-O và mô hình chi phí trao đổi bộ nhớ

**Big-O** mô tả sự tăng trưởng số bước theo kích thước đầu vào. Nó thường bỏ qua chi tiết cache line, cache hit/miss, vectorization, cấp phát và chi phí dịch địa chỉ.

Một mô hình bổ sung là **I/O model**: dữ liệu chuyển theo block chứa `B` phần tử. Trong điều kiện phù hợp, quét `n` phần tử liên tiếp cần khoảng **O(n/B + 1)** lần chuyển block; nếu mỗi nút liên kết nằm ở một block khác nhau, lần theo `n` nút có thể cần đến **O(n)** lần chuyển block. Đây là cách lý giải sự khác nhau về **lượng dữ liệu phải nạp**, không phải công thức chính xác cho số cache miss trên mọi CPU.

| Vấn đề cần đánh giá | Công cụ tư duy |
| --- | --- |
| Đọc `a[i]` theo chỉ số? | O(1) bước |
| Tìm nút thứ `i` bằng `next`? | O(i), tối đa O(n) bước |
| Một lượt quét tận dụng cache line bao nhiêu? | Xem layout, stride, kích thước phần tử, căn chỉnh |
| Tập dữ liệu lặp lại có nằm trong cache không? | Ước lượng working set, đo cache hit/miss |
| Chương trình thật nhanh hơn bao nhiêu? | Benchmark trong môi trường mục tiêu |

Tối ưu locality thường giảm hệ số thực tế **trong cùng một bậc Big-O**. Khi so sánh hai thuật toán khác bậc, phải xét cả `n` và hằng số: O(n log n) không tự động thắng O(n²) ở mọi kích thước nhỏ, còn O(n²) không trở thành O(n log n) chỉ vì được tối ưu cache.

## 11. False sharing khi nhiều luồng cùng chạy

**False sharing** là tình huống hai luồng cập nhật **hai biến khác nhau**, nhưng các biến nằm trên cùng một cache line. Giao thức **cache coherence** có thể phải chuyển quyền ghi hoặc vô hiệu hóa line giữa các lõi, gây lưu lượng bổ sung.

```text
Một cache line:
+----------------------+----------------------+------+
| counter_for_thread_1 | counter_for_thread_2 | ...  |
+----------------------+----------------------+------+
          ^                       ^
        Luồng 1                 Luồng 2
```

False sharing **khác data race**. Nếu mỗi luồng chỉ truy cập biến riêng và mọi thao tác đều hợp lệ theo quy tắc đồng thời của ngôn ngữ, vẫn có thể không có data race nhưng hiệu năng thấp vì cache coherence.

Có thể giảm false sharing bằng cách căn chỉnh/tách các biến bị ghi thường xuyên sang những line khác nhau hoặc tích lũy cục bộ rồi gộp. Nhưng thêm padding làm tăng bộ nhớ; khi cục bộ không gian của các dữ liệu khác quan trọng, giải pháp có thể bất lợi. Cần đo trước khi thay đổi.

## 12. Cách đo hiệu quả cache thực tế

Để tránh tối ưu theo trực giác sai, nên thực hiện thí nghiệm có kiểm soát:

1. **Chọn phép đo cụ thể:** quét mảng so với danh sách, duyệt hàng so với cột, hoặc AoS so với SoA trong một thao tác.
2. **Giữ nguyên kết quả logic và lượng công việc:** cùng dữ liệu, cùng phép tính; không so sánh hai hàm thực hiện số phép toán khác biệt rồi gán chênh lệch cho cache.
3. **Thử nhiều kích thước working set:** nhỏ, gần các mức cache, và lớn hơn cache.
4. **Biên dịch công bằng:** cùng mức tối ưu; kiểm tra biến đổi vòng lặp/vector hóa khi cần.
5. **Không cho trình biên dịch xóa phép tính:** sử dụng kết quả thật sự, kiểm tra tính đúng đắn và đảm bảo benchmark đo công việc cần khảo sát.
6. **Lặp nhiều lượt:** phân biệt lượt đầu (cold) và lượt sau (warm); xem độ phân tán, tránh suy luận từ một lần chạy.
7. **Đọc công cụ đo nếu có:** profiler hoặc hardware performance counters có thể cung cấp cycles, instructions và cache-miss counters, nhưng cần hiểu ý nghĩa, mức cache và giới hạn của từng counter.

**Ít cache miss không phải luôn đồng nghĩa chạy nhanh hơn:** phiên bản mới có thể thực hiện nhiều phép toán, nhánh hoặc cấp phát bổ sung. Thước đo cuối cùng là tổng thời gian và tài nguyên cho workload cần xử lý.

## 13. Quyết định cấu trúc dựa trên locality

| Nhu cầu chính | Lựa chọn nên cân nhắc | Vì sao |
| --- | --- | --- |
| Quét rất nhiều phần tử liên tiếp | Mảng, mảng động | Cục bộ không gian, ít metadata theo phần tử |
| Duyệt một trường của nhiều đối tượng | SoA | Dữ liệu cần dùng nằm dày đặc trong cache line |
| Thêm/xóa nút thường xuyên khi đã biết nút liên quan | Danh sách đôi | Sửa liên kết O(1); chấp nhận chi phí con trỏ |
| Stack/queue với nhiều thao tác | Mảng động, mảng vòng | Ít cấp phát nút, dữ liệu tập trung |
| Hàng đợi ưu tiên | Binary heap dùng mảng | Không cần con trỏ cha/con cho mỗi nút |
| Tra cứu theo khóa | Bảng băm với layout phù hợp | Đo hệ số tải, số probe và cache miss |
| Duyệt đồ thị thưa ít cập nhật | CSR hoặc danh sách kề dạng mảng | Các cạnh lân cận nằm liên tiếp |
| Cây có nhiều thay đổi hình dạng | Nút liên kết hoặc cấu trúc theo khối | Cân bằng tính linh hoạt với chi phí cache |

Không có cấu trúc tối ưu tuyệt đối: cách lưu liên tiếp có thể phải dịch dữ liệu khi chèn/xóa, còn nút liên kết có chi phí metadata và truy cập gián tiếp. Chọn theo **tần suất thao tác, đặc tính cập nhật, bộ nhớ cho phép và benchmark**.

## 14. Bài tập tự kiểm tra có lời giải

### Câu 1. Một cache line chứa bao nhiêu số nguyên?

Giả sử một cache line dài 64 byte, `sizeof(int) = 4` và mảng bắt đầu đúng ranh giới line. Một line có thể chứa bao nhiêu phần tử `int`?

**Đáp án:** `64 / 4 = 16` phần tử. Mảng 1.024 số nguyên chiếm 4.096 byte, tương ứng 64 line nếu căn chỉnh đúng. Nếu địa chỉ đầu lệch ranh giới line, mảng có thể trải qua **thêm một line**.

### Câu 2. Vì sao hai vòng lặp O(n) có thời gian khác nhau?

Một hàm cộng `n` phần tử mảng; hàm kia cộng `n` giá trị từ các nút danh sách liên kết cấp phát rải rác.

**Đáp án:** Mảng tận dụng địa chỉ liên tiếp, cache line và thường dễ prefetch; danh sách cần theo `next` và có thể chạm nhiều line/trang khác nhau. Cả hai cùng O(n) nhưng chi phí chờ dữ liệu có thể khác đáng kể.

### Câu 3. Stride trong ma trận

Với `int a[512][512]` trong C và `int` 4 byte, khoảng cách địa chỉ từ `a[r][c]` đến `a[r+1][c]` là bao nhiêu?

**Đáp án:** `512 × 4 = 2.048` byte. Nếu vòng trong tăng `r`, chương trình liên tục nhảy giữa hàng. Tăng `c` ở vòng trong thường thuận lợi hơn trên row-major.

### Câu 4. Chọn AoS hay SoA?

Ứng dụng lưu một triệu hạt `{x, y, vx, vy}` và chỉ cần tính trung bình `x`. Bố trí nào nên thử?

**Đáp án:** SoA là ứng viên hợp lý vì các giá trị `x` có thể nằm liền nhau, tăng mật độ dữ liệu hữu ích trong line. Phải giữ bất biến rằng `x[i]`, `y[i]`, `vx[i]`, `vy[i]` cùng mô tả hạt `i`.

### Câu 5. Dữ liệu nhỏ hơn cache có bảo đảm mọi truy cập hit?

Một mảng nhỏ hơn dung lượng L1 có chắc tất cả lần đọc sau lượt đầu là L1 hit không?

**Đáp án:** **Không.** Line có thể bị thay thế do ánh xạ set, dữ liệu cạnh tranh, hoạt động nhiều lõi hoặc hành vi cache khác. Kích thước working set chỉ giúp dự đoán xu hướng.

### Câu 6. False sharing có phải data race?

Hai luồng thay đổi hai bộ đếm riêng biệt, hai bộ đếm nằm trên cùng cache line.

**Đáp án:** **Không nhất thiết là data race.** Chương trình có thể không có truy cập xung đột lên cùng biến, nhưng vẫn chịu lưu lượng nhất quán cache khi hai luồng ghi các phần khác nhau của line. Có thể đo và thử tách line hoặc tích lũy cục bộ.

### Câu 7. Vì sao heap thường dùng mảng?

Một binary heap cài bằng mảng có lợi gì so với việc cấp phát một đối tượng cho mỗi nút cây?

**Đáp án:** Quan hệ cha/con có thể tính bằng chỉ số; không cần lưu `left`/`right` ở từng nút, giảm metadata và tập trung dữ liệu trong một vùng. Các thao tác sift vẫn O(log n) theo chiều cao, và không phải mọi bước truy cập đều tuần tự.

## 15. Ghi nhớ

- **Spatial locality**: dùng các địa chỉ gần nhau. **Temporal locality**: sớm dùng lại cùng dữ liệu. Cả hai có thể giúp tận dụng cache.
- **Cache line** là đơn vị khối dữ liệu; mức độ sử dụng hiệu quả phụ thuộc kích thước phần tử, căn chỉnh, layout và stride.
- **Big-O không phản ánh hết chi phí bộ nhớ:** quét mảng và theo danh sách liên kết cùng O(n), nhưng số lần nạp dữ liệu, cache miss và metadata có thể khác nhau.
- **Layout và thứ tự duyệt là quyết định thiết kế:** row-major, AoS/SoA, tiling, mảng vòng, heap chỉ số và CSR phù hợp với những workload khác nhau.
- **Tối ưu dựa trên kết quả đo:** xác định thao tác chủ đạo, giữ bất biến và tính đúng đắn, thử nhiều quy mô rồi so sánh thời gian cùng các chỉ số bộ nhớ trên môi trường mục tiêu.
