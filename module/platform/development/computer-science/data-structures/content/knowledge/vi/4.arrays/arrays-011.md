# Tách mảng cấu trúc thành các mảng trường và đánh đổi bố trí dữ liệu

## 1. Cùng một dữ liệu, hai cách sắp xếp trong bộ nhớ

Một ứng dụng mô phỏng chuyển động có nhiều đối tượng. Với mỗi đối tượng, ta lưu mã định danh `id`, tọa độ `x`, `y` và vận tốc `vx`, `vy`:

| Đối tượng | `id` | `x` | `y` | `vx` | `vy` |
|---|---:|---:|---:|---:|---:|
| 0 | 101 | 1.0 | 3.0 | 0.5 | 0.0 |
| 1 | 102 | 2.0 | 4.0 | 1.0 | -0.5 |
| 2 | 103 | 5.0 | 2.0 | -0.5 | 0.5 |

Về mặt logic, ta có ba **bản ghi** (*records*) cùng năm trường. Nhưng khi đưa vào bộ nhớ, có ít nhất hai phương án chính:

- **AoS — Array of Structures (mảng các cấu trúc):** mỗi phần tử mảng là một bản ghi chứa đủ các trường.
- **SoA — Structure of Arrays (cấu trúc các mảng):** mỗi trường được tách thành một mảng riêng; những giá trị tại **cùng chỉ số** tạo thành một bản ghi logic.

Hai cách biểu diễn chứa cùng thông tin, nhưng đặt những byte hay được truy cập **gần nhau** theo hai cách khác nhau. Vì thế, chúng có thể khác nhau đáng kể khi xử lý nhiều phần tử, dù các phép tính toán học và độ phức tạp Big-O của thuật toán không thay đổi.

Sau bài học, bạn có thể:

1. Vẽ và giải thích bố trí AoS, SoA theo bản ghi và theo trường.
2. Tính vị trí phần tử/trường, phân biệt bước truy cập `stride` và khoảng đệm `padding`.
3. Dự đoán cách truy cập bộ nhớ khi quét một trường hoặc xử lý toàn bộ bản ghi.
4. Chuyển đổi giữa hai biểu diễn mà không làm lẫn dữ liệu của các bản ghi.
5. Giữ bất biến đồng bộ chỉ số khi thêm, xóa, sắp xếp và cập nhật dữ liệu.
6. Đánh giá tính cục bộ cache, khả năng vector hóa SIMD, chi phí bộ nhớ và chi phí bảo trì cấu trúc.

Đây là một chủ đề của chương **Mảng** trong học phần **Cấu trúc dữ liệu**. Tư duy chọn bố trí dữ liệu dựa trên kiểu truy cập sẽ còn hữu ích khi thiết kế danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nơi các bất biến cùng độ phức tạp thời gian, bộ nhớ quyết định lựa chọn phù hợp.

## 2. AoS: gom các trường của một bản ghi lại với nhau

Với AoS, các bản ghi được đặt thành phần tử liên tiếp của một mảng. Một bản ghi chứa những trường mô tả cùng một đối tượng:

```text
AoS — mỗi ô lớn là một bản ghi:

         bản ghi 0                      bản ghi 1                    bản ghi 2
┌──────────────────────────┬──────────────────────────┬──────────────────────────┐
│ id  x  y  vx  vy         │ id  x  y  vx  vy         │ id  x  y  vx  vy         │
│101 1.0 3.0 .5  .0        │102 2.0 4.0 1.0 -.5       │103 5.0 2.0 -.5 .5        │
└──────────────────────────┴──────────────────────────┴──────────────────────────┘

Ví dụ truy cập: particles[1].x = 2.0
```

Nếu cần **đọc và thao tác đủ các trường của một đối tượng**, AoS là biểu diễn trực quan: lấy phần tử thứ `i` rồi truy cập các trường của nó.

Trong C, có thể dùng mảng các `struct`:

```c
struct Particle {
    unsigned int id;
    float x, y;
    float vx, vy;
};

struct Particle particles[3] = {
    {101u, 1.0f, 3.0f,  0.5f,  0.0f},
    {102u, 2.0f, 4.0f,  1.0f, -0.5f},
    {103u, 5.0f, 2.0f, -0.5f,  0.5f}
};

float x_of_second = particles[1].x;  /* 2.0f */
```

**Bất biến AoS:** mỗi phần tử mảng là một bản ghi hoàn chỉnh; các trường của đối tượng thứ `i` nằm bên trong `particles[i]`. Di chuyển cả phần tử `particles[i]` thường di chuyển dữ liệu của tất cả các trường đi cùng nhau.

Một điểm cần phân biệt: đối với mảng `struct` thực sự trong C, các bản ghi nằm liên tiếp trong vùng mảng, nhưng **bên trong struct có thể có byte đệm** do yêu cầu căn chỉnh. Không được tự tính `sizeof(struct Particle)` bằng tổng `sizeof` các trường mà không xem quy tắc của trình biên dịch.

## 3. SoA: gom các giá trị của cùng một trường lại với nhau

Với SoA, mỗi trường có một dãy riêng:

```text
SoA — mỗi hàng là một mảng trường:

id:  [101 | 102 | 103]
x:   [1.0 | 2.0 | 5.0]
y:   [3.0 | 4.0 | 2.0]
vx:  [0.5 | 1.0 |-0.5]
vy:  [0.0 |-0.5 | 0.5]
       ↑     ↑     ↑
       0     1     2   chỉ số bản ghi logic

Ví dụ truy cập: x[1] = 2.0
```

Trong C, có thể biểu diễn bằng những mảng riêng:

```c
unsigned int ids[3] = {101u, 102u, 103u};
float xs[3]  = {1.0f, 2.0f, 5.0f};
float ys[3]  = {3.0f, 4.0f, 2.0f};
float vxs[3] = {0.5f, 1.0f, -0.5f};
float vys[3] = {0.0f, -0.5f, 0.5f};

/* Bản ghi logic thứ hai có id=102, x=2.0, y=4.0, vx=1.0, vy=-0.5. */
float x_of_second = xs[1];
```

**Bất biến SoA quan trọng nhất:** mọi mảng trường có cùng **độ dài logic `n`**, và tất cả phần tử ở chỉ số `i` cùng thuộc về **một bản ghi**:

\[
\forall i\in[0,n):\quad
\operatorname{record}(i)
=(id[i],\,x[i],\,y[i],\,vx[i],\,vy[i]).
\]

Nếu vô tình xóa phần tử `x[1]` mà không xóa đúng vị trí đó trong các mảng còn lại, `x[1]` sẽ thuộc đối tượng cũ thứ ba trong khi `id[1]` vẫn thuộc đối tượng thứ hai. Cấu trúc có thể không phát sinh lỗi chỉ số, nhưng dữ liệu đã **sai quan hệ**.

SoA không bắt buộc phải là năm khối nằm kế tiếp nhau. Mỗi mảng trường thường liên tiếp *bên trong chính nó*, còn các mảng có thể nằm ở những vùng nhớ hoàn toàn khác nhau.

## 4. Cách tính địa chỉ và stride trong hai biểu diễn

Giả sử mỗi bản ghi AoS có kích thước thực tế `S = sizeof(struct Particle)` byte; trường `x` nằm cách đầu bản ghi `o_x = offsetof(struct Particle, x)` byte. Nếu `base` là địa chỉ bắt đầu mảng:

\[
\boxed{addr_{AoS}(x_i)=base+iS+o_x}
\]

Trong AoS, khoảng cách địa chỉ giữa `x_i` và `x_{i+1}` là **`S` byte**, vì hai giá trị `x` thuộc hai bản ghi liên tiếp.

Đối với SoA có mảng `xs` liên tiếp, mỗi phần tử chiếm `s_x=sizeof(float)` byte, địa chỉ trường `x` ở bản ghi thứ `i`:

\[
\boxed{addr_{SoA}(x_i)=base_x+i\,s_x}
\]

Khoảng cách giữa hai giá trị `x` liên tiếp trong SoA chỉ là **`s_x` byte**.

Ví dụ giả định một nền tảng có `sizeof(struct Particle)=20` byte, `offsetof(struct Particle,x)=4` byte và `sizeof(float)=4` byte:

```text
               x[0]        x[1]        x[2]
AoS offset:        4           24           44      (stride 20 byte)
SoA offset:        0            4            8      (stride  4 byte)
```

Các số `20`, `4` trong ví dụ là **giả định minh họa**, không phải quy định bắt buộc cho mọi máy. Kiểu dữ liệu, căn chỉnh, thứ tự trường và ABI có thể làm `S` hoặc `o_x` thay đổi.

Có thể quan sát các đại lượng này bằng C:

```c
#include <stddef.h>
#include <stdio.h>

struct Particle {
    unsigned int id;
    float x, y;
    float vx, vy;
};

int main(void) {
    printf("sizeof(Particle) = %zu byte\n", sizeof(struct Particle));
    printf("offsetof(x) = %zu byte\n", offsetof(struct Particle, x));
    printf("sizeof(float) = %zu byte\n", sizeof(float));
    return 0;
}
```

**Phân biệt tính địa chỉ và truy cập hợp lệ:** các công thức chỉ dùng cho `0 <= i < n` và vùng lưu thật sự tồn tại. Một chỉ số vượt giới hạn vẫn có thể cho ra một con số địa chỉ nhưng không vì thế mà trở thành truy cập an toàn.

## 5. Quét một trường: vì sao SoA thường có lợi?

Giả sử cần tính tổng tọa độ `x` của `n` đối tượng, hoàn toàn không cần `id`, `y`, `vx` hay `vy`.

Với AoS:

```c
double total_x = 0.0;
for (size_t i = 0; i < n; ++i) {
    total_x += particles[i].x;
}
```

Với SoA:

```c
double total_x = 0.0;
for (size_t i = 0; i < n; ++i) {
    total_x += xs[i];
}
```

Cả hai có **`O(n)` thời gian** vì đều phải đọc `n` giá trị `x`. Nhưng thứ tự các byte được truy cập khác nhau:

- Ở **AoS**, hai lần đọc trường `x` cách nhau `S` byte. Khi CPU nạp một dòng cache chứa `x`, nó có thể đồng thời nạp cả các trường khác trong bản ghi mà thuật toán không sử dụng.
- Ở **SoA**, các giá trị `x` nằm cạnh nhau. Một dòng cache có thể chứa nhiều giá trị `x` hữu ích, thuận lợi cho duyệt tuần tự và đọc trước (*prefetch*).

Ví dụ với giả định mỗi bản ghi AoS rộng `32` byte, trường `x` rộng `8` byte, và thuật toán chỉ đọc `x` của một triệu bản ghi: vùng bản ghi AoS trải dài khoảng **32 MB**, trong khi mảng `x` SoA chỉ chiếm khoảng **8 MB** dữ liệu trường `x`. Con số đó **không** có nghĩa CPU nhất thiết chuyển đúng 32 MB và 8 MB qua mọi mức cache; lượng truyền thực tế phụ thuộc dòng cache, bộ nhớ đệm, cấu trúc vòng lặp và phần cứng. Nó chỉ minh họa lượng dữ liệu **có khả năng phải đi qua** khi quét một trường ở hai bố trí.

Với dữ liệu đủ lớn so với cache, quét một hoặc một vài trường thường là kiểu công việc có thể hưởng lợi từ SoA.

## 6. Đọc toàn bộ một bản ghi: khi AoS có thể thuận lợi

Không phải lúc nào SoA cũng tốt hơn. Xét thao tác “lấy tất cả thuộc tính của đối tượng có chỉ số `i` để gửi đi”:

```text
AoS:
   particles[i] → id, x, y, vx, vy cùng nằm trong một bản ghi.

SoA:
   ids[i], xs[i], ys[i], vxs[i], vys[i]
   → đọc từ năm mảng trường, có thể là năm vùng nhớ khác nhau.
```

Ở AoS, các trường của cùng bản ghi thường nằm gần nhau, nên một lần nạp cache có khả năng phục vụ nhiều trường cần đọc. Với SoA, khi chỉ đọc ngẫu nhiên **một vài** bản ghi và cần **đủ trường**, có thể phải đụng tới nhiều vùng nhớ và nhiều dòng cache khác nhau.

AoS cũng thuận tiện khi:

- API yêu cầu nhận/trả một bản ghi hoàn chỉnh.
- Mã nghiệp vụ thường xuyên thao tác trên một đối tượng tại một thời điểm.
- Số bản ghi nhỏ, dữ liệu vừa trong cache, hoặc chi phí chuyển đổi lớn hơn lợi ích.
- Cần sao chép hoặc lưu trữ một bản ghi như một đơn vị, với điều kiện hợp đồng biểu diễn phù hợp.

Ngược lại, khi xử lý *mọi giá trị của một trường* hoặc chạy nhiều phép tính hàng loạt trên từng trường, SoA có thể đem lại tính cục bộ tốt hơn.

**Kết luận thực hành:** khả năng tối ưu hóa phụ thuộc **cách chương trình truy cập dữ liệu**, không phải tên AoS hay SoA.

## 7. SoA và vector hóa SIMD

**SIMD** (*Single Instruction, Multiple Data*) là cách xử lý nhiều phần tử bằng một lệnh thích hợp. Chẳng hạn, cần cập nhật tọa độ theo vận tốc:

\[
x_i \leftarrow x_i+vx_i\,\Delta t,\qquad
y_i \leftarrow y_i+vy_i\,\Delta t.
\]

Với SoA, các mảng `xs`, `ys`, `vxs`, `vys` chứa các giá trị cùng loại liền nhau. Các phép tính trên `xs[i]` và `vxs[i]` có thể phù hợp với truy cập theo vector:

```c
void advance_soa(float *xs, float *ys,
                 const float *vxs, const float *vys,
                 size_t n, float dt) {
    for (size_t i = 0; i < n; ++i) {
        xs[i] += vxs[i] * dt;
        ys[i] += vys[i] * dt;
    }
}
```

Trong AoS, những giá trị `x_i` hoặc `vx_i` của các bản ghi kế tiếp cách nhau cả một `struct`; truy cập có **stride lớn hơn** kích thước của từng trường. Điều đó có thể làm việc vector hóa khó hơn hoặc kém hiệu quả hơn.

Tuy nhiên, **không phải cứ chuyển sang SoA là trình biên dịch tự tạo SIMD và chương trình chắc chắn nhanh hơn**. Khả năng vector hóa còn phụ thuộc:

- Trình biên dịch, cờ tối ưu hóa và kiến trúc CPU.
- Kiểu dữ liệu, alignment, số lượng phần tử và chiều dài vòng lặp.
- Phụ thuộc dữ liệu giữa các vòng lặp và khả năng hai con trỏ trỏ vào vùng nhớ chồng lấp (*aliasing*).
- Phép toán có phép gọi hàm khó tối ưu hoặc thay đổi kết quả do thứ tự làm tròn số thực.
- Cache, băng thông bộ nhớ và phần việc khác của chương trình.

Nếu cần đánh giá hiệu năng, hãy đo **cùng một công việc thực tế trên dữ liệu đại diện**, với cấu hình biên dịch phù hợp, thay vì chỉ nhìn sơ đồ bố trí.

## 8. Mô phỏng chuyển đổi AoS → SoA bằng Python

Python phù hợp để minh họa **quan hệ logic** giữa hai biểu diễn, nhưng cần nhớ: một `list` các `dict` **không phải** mảng `struct` liên tiếp như C; và một `dict` chứa nhiều `list` Python cũng không bảo đảm toàn bộ số thực nằm trong các bộ đệm số liền nhau. Ví dụ này dạy cách biến đổi dữ liệu và giữ đồng bộ chỉ số, không được dùng để kết luận trực tiếp về hiệu năng bộ nhớ của AoS/SoA cấp thấp.

### Dữ liệu theo bản ghi (AoS về mặt logic)

```python
records = [
    {"id": 101, "x": 1.0, "y": 3.0, "vx": 0.5, "vy": 0.0},
    {"id": 102, "x": 2.0, "y": 4.0, "vx": 1.0, "vy": -0.5},
    {"id": 103, "x": 5.0, "y": 2.0, "vx": -0.5, "vy": 0.5},
]

print(records[1]["x"])  # 2.0
```

### Chuyển thành các mảng trường (SoA về mặt logic)

```python
def to_soa(records: list[dict]) -> dict[str, list]:
    fields = ("id", "x", "y", "vx", "vy")
    return {
        field: [record[field] for record in records]
        for field in fields
    }


columns = to_soa(records)
print(columns)
# {'id': [101, 102, 103], 'x': [1.0, 2.0, 5.0],
#  'y': [3.0, 4.0, 2.0], 'vx': [0.5, 1.0, -0.5],
#  'vy': [0.0, -0.5, 0.5]}

print(columns["x"][1])  # 2.0
```

### Chuyển ngược SoA → AoS

```python
FIELDS = ("id", "x", "y", "vx", "vy")


def validate_soa(columns: dict[str, list]) -> int:
    if any(field not in columns for field in FIELDS):
        raise ValueError("Thiếu mảng trường")

    n = len(columns["id"])
    if any(len(columns[field]) != n for field in FIELDS):
        raise ValueError("Độ dài các mảng trường không bằng nhau")
    return n


def to_aos(columns: dict[str, list]) -> list[dict]:
    n = validate_soa(columns)
    return [
        {field: columns[field][i] for field in FIELDS}
        for i in range(n)
    ]


restored = to_aos(columns)
print(restored == records)  # True
```

Chuyển đổi một lần có `n` bản ghi, `f` trường, giả định việc đọc/sao chép một giá trị hoặc tham chiếu có chi phí `O(1)`, cần **`O(nf)` thời gian** và **`O(nf)` vị trí lưu** cho kết quả mới. Khi `f` cố định, thường viết gọn là **`O(n)`**. Bản sao logic này có thể chỉ sao chép **tham chiếu** đối với những trường chứa đối tượng có thể thay đổi; muốn độc lập sâu cần chiến lược sao chép thích hợp.

## 9. Bất biến đồng bộ chỉ số và thao tác cập nhật

SoA thường khó bảo trì hơn AoS khi thêm, xóa hoặc sắp xếp bản ghi, vì **một thao tác logic phải tác động nhất quán lên mọi mảng trường**.

### 9.1. Thêm bản ghi vào cuối

```python
def append_record(columns: dict[str, list], record: dict) -> None:
    # Ví dụ giả định columns hợp lệ và đủ trường từ trước.
    validate_soa(columns)
    if any(field not in record for field in FIELDS):
        raise ValueError("Bản ghi thiếu trường")
    for field in FIELDS:
        columns[field].append(record[field])


append_record(columns, {"id": 104, "x": 4.0, "y": 1.0,
                        "vx": 0.0, "vy": 1.0})
print(validate_soa(columns))  # 4
```

Mỗi mảng trường động thực hiện thêm cuối, thường `O(1)` **khấu hao** trên mỗi mảng. Với `f` trường cố định, thêm một bản ghi thường `O(1)` khấu hao về thời gian; nếu `f` là biến số, chi phí là `O(f)` khấu hao. Một lần thêm có thể gây cấp phát lại ở một hoặc nhiều mảng và tốn `O(n)` trong trường hợp xấu nhất.

Mã trên chỉ minh họa thứ tự thao tác. Trong hệ thống cần tính đúng đắn cao, nếu thêm vào giữa chừng phát sinh lỗi (ví dụ thiếu bộ nhớ), phải có cơ chế **rollback**, thay đổi nguyên tử hoặc xây bản mới trước khi công bố; không được để một số cột có độ dài `n+1` còn các cột khác có `n`.

### 9.2. Xóa bản ghi nhưng giữ thứ tự

Giả sử muốn xóa bản ghi thứ `i`, vẫn giữ nguyên thứ tự những bản ghi còn lại. Phải xóa **chỉ số `i` trong tất cả các mảng trường**:

```python
def delete_record_stable(columns: dict[str, list], index: int) -> None:
    n = validate_soa(columns)
    if not 0 <= index < n:
        raise IndexError("Chỉ số bản ghi không hợp lệ")
    for field in FIELDS:
        columns[field].pop(index)


delete_record_stable(columns, 1)  # Xóa bản ghi id=102
print(columns["id"])             # [101, 103, 104]
print(columns["x"])              # [1.0, 5.0, 4.0]
```

Nếu mỗi mảng trường liên tiếp, xóa tại `i` cần dịch các phần tử phía sau trong từng mảng. Tổng số ô phải dịch là `f(n-i-1)` khi `f` cột có cùng độ dài `n` và giữ thứ tự, nên chi phí là **`O(f(n-i))`**, thường viết **`O(n)`** khi `f` cố định. AoS cũng phải dịch `n-i-1` **bản ghi**, mỗi bản ghi rộng hơn; Big-O không phân biệt được lượng byte cụ thể.

### 9.3. Xóa không giữ thứ tự bằng phần tử cuối

Nếu thứ tự các bản ghi **không quan trọng**, có thể thay toàn bộ bản ghi `i` bằng bản ghi ở cuối rồi giảm độ dài. Với SoA, phải thực hiện phép thay cho **mọi cột**:

```python
def delete_record_unordered(columns: dict[str, list], index: int) -> None:
    n = validate_soa(columns)
    if not 0 <= index < n:
        raise IndexError("Chỉ số bản ghi không hợp lệ")

    for field in FIELDS:
        values = columns[field]
        values[index] = values[-1]
        values.pop()


delete_record_unordered(columns, 0)
print(columns["id"])  # [104, 103], thứ tự có thể thay đổi
```

Với `f` trường và chỉ số `i` đã biết, cách này dùng **`O(f)` thời gian** và **`O(1)` bộ nhớ phụ** trong trường hợp thao tác lấy/xóa cuối có chi phí hằng số thông thường; với `f` cố định, tương đương `O(1)`. Tuy nhiên, người dùng giữ **chỉ số cũ** để xác định đối tượng có thể bị nhầm: bản ghi ở cuối đã được chuyển đến vị trí `i`. Hệ thống cần duy trì ánh xạ `id → index` nếu tra bản ghi theo mã định danh, hoặc cập nhật các tham chiếu tới vị trí đã thay đổi.

### 9.4. Sắp xếp phải dùng cùng một hoán vị cho mọi trường

Giả sử muốn sắp bản ghi theo `x`, ta không thể chỉ gọi `columns["x"].sort()` vì làm vậy tách `x` khỏi `id`, `y`, `vx`, `vy` của bản ghi ban đầu.

Đúng hơn, hãy tính **một hoán vị chỉ số** rồi áp dụng hoán vị ấy lên tất cả các cột:

```python
def sort_soa_by_x(columns: dict[str, list]) -> dict[str, list]:
    n = validate_soa(columns)
    order = sorted(range(n), key=lambda i: columns["x"][i])
    return {
        field: [columns[field][i] for i in order]
        for field in FIELDS
    }


sorted_columns = sort_soa_by_x(columns)
print(sorted_columns["x"])   # [4.0, 5.0]
print(sorted_columns["id"])  # [104, 103]
```

Tạo hoán vị sắp xếp so sánh cần **`O(n\log n)` thời gian** trong trường hợp phổ biến, rồi xây lại `f` cột cần **`O(nf)` thời gian và bộ nhớ**; với `f` cố định, tổng thời gian **`O(n\log n)`**. Bù lại, mọi giá trị tại chỉ số `i` vẫn thuộc cùng một bản ghi sau khi sắp.

## 10. Dung lượng bộ nhớ: SoA không phải lúc nào cũng nhỏ hơn

Đánh giá bộ nhớ cần phân biệt:

1. **Dữ liệu hữu ích**: số byte thật sự dùng để lưu các trường.
2. **Padding và alignment**: khoảng đệm có thể nằm trong từng bản ghi AoS.
3. **Metadata**: độ dài, sức chứa, con trỏ và thông tin quản lý nhiều mảng SoA.
4. **Dung lượng dự phòng**: mảng động có thể cấp phát nhiều ô hơn độ dài hiện tại.
5. **Bản sao hoặc chỉ mục phụ**: nếu chương trình giữ đồng thời AoS và SoA, dữ liệu có thể bị nhân đôi.

Ví dụ giả định một bản ghi có ba trường:

```c
struct Example {
    char active;
    double score;
    int id;
};
```

Tổng kích thước các trường là `sizeof(char)+sizeof(double)+sizeof(int)`, nhưng `sizeof(struct Example)` có thể lớn hơn do byte đệm. Nếu có `n` bản ghi:

\[
\operatorname{bytes}_{AoS}=n\times sizeof(struct\ Example).
\]

Trong SoA lưu ba mảng kiểu tương ứng, số byte chứa **các phần tử** xấp xỉ:

\[
\operatorname{bytes}_{SoA,data}
=n\big(sizeof(char)+sizeof(double)+sizeof(int)\big).
\]

Tuy nhiên, SoA còn cần metadata cho từng mảng, vùng dự phòng và có thể có chi phí căn chỉnh của từng vùng cấp phát. Vì vậy không thể khẳng định tổng dung lượng SoA **luôn nhỏ hơn** AoS.

**Kích thước thực tế phụ thuộc nền tảng và cách cài đặt.** Chỉ dùng các con số cụ thể sau khi đo `sizeof`, `offsetof` và chính sách cấp phát của cấu trúc đang dùng. Đối với Python `list` hay `dict`, chi phí đối tượng và tham chiếu còn làm phép so sánh theo `sizeof(struct)` không thể áp dụng trực tiếp.

## 11. AoS, SoA và AoSoA: không chỉ có hai cực

Một phương án trung gian là **AoSoA — Array of Structures of Arrays** (*mảng các khối, mỗi khối chứa những mảng trường*). Thay vì đặt đủ `n` giá trị `x` trong một vùng, ta chia dữ liệu thành các **khối nhỏ** cỡ `B`:

```text
AoS:
    [id x y vx vy] [id x y vx vy] [id x y vx vy] ...

SoA:
    id: [id0 id1 id2 ...]
    x:  [x0  x1  x2  ...]
    y:  [y0  y1  y2  ...]

AoSoA (minh họa B=4):
    Khối 0: id[0..3] | x[0..3] | y[0..3] | vx[0..3] | vy[0..3]
    Khối 1: id[4..7] | x[4..7] | y[4..7] | vx[4..7] | vy[4..7]
    ...
```

AoSoA cố gắng dung hòa:

- Trong mỗi khối, các phần tử cùng trường liền nhau, thuận lợi cho vector hóa trên nhóm `B` phần tử.
- Các trường của **một nhóm bản ghi** vẫn ở gần nhau tương đối, có thể thuận lợi khi thuật toán dùng nhiều trường trong từng khối.
- Có thể điều chỉnh kích thước khối theo nhu cầu cache, SIMD và thuật toán.

Đổi lại, mã ánh xạ chỉ số phức tạp hơn. Với `B` phần tử mỗi khối, chỉ số toàn cục `i` được đổi thành:

\[
\operatorname{block}(i)=\lfloor i/B\rfloor,\qquad
\operatorname{local}(i)=i\bmod B.
\]

Truy cập `x_i` cần chọn đúng khối rồi đúng cột `x` và vị trí cục bộ. Khối cuối có thể chưa đầy, nên phải theo dõi số phần tử thực tế hoặc xử lý phần đuôi. AoSoA có lợi trong một số hệ thống số học, đồ họa, mô phỏng và xử lý dữ liệu theo lô, nhưng không mặc định phù hợp với mọi ứng dụng.

Một thiết kế thực tế khác là **lai ghép**: đặt các trường thường xuyên dùng cùng nhau trong một nhóm AoS nhỏ, còn các trường ít dùng hoặc có kích thước lớn đặt ở vùng riêng. Mục đích vẫn là tối ưu **kiểu truy cập nổi trội**.

## 12. Bảng so sánh theo các thao tác thực tế

Giả định `n` bản ghi, `f` trường có kích thước cố định, mảng đủ điều kiện truy cập trực tiếp theo chỉ số. Các độ phức tạp dưới đây tính theo mô hình RAM; hiệu năng cache có thể khác.

| Thao tác / đặc điểm | AoS | SoA |
|---|---|---|
| Đọc một trường của bản ghi `i` đã biết | `O(1)` | `O(1)` |
| Đọc đủ trường của bản ghi `i` | `O(f)` nếu tính từng trường; `O(1)` khi `f` cố định | `O(f)`; phải đọc từ nhiều mảng |
| Quét một trường qua `n` bản ghi | `O(n)`, thường có stride bằng kích thước bản ghi | `O(n)`, thường liên tiếp theo trường |
| Xử lý nhiều trường của cùng bản ghi | Có thể có tính cục bộ tốt | Có thể phải truy cập nhiều vùng |
| Vector hóa vòng lặp chỉ dùng vài trường | Có thể khó hơn do stride lớn | Thường thuận lợi hơn do các trường liên tiếp |
| Thêm bản ghi cuối | `O(1)` khấu hao trên mảng động | `O(f)` khấu hao, `O(1)` nếu `f` cố định |
| Xóa ở giữa, giữ thứ tự | `O(n)` xấu nhất, dịch bản ghi | `O(fn)` xấu nhất, dịch từng mảng trường |
| Xóa bằng đổi chỗ với phần tử cuối | `O(1)` khi đã biết chỉ số và không giữ thứ tự | `O(f)`, phải đổi ở mọi trường |
| Sắp xếp theo một trường | Sắp cùng toàn bộ bản ghi | Phải áp dụng cùng hoán vị cho tất cả trường |
| Bộ nhớ | Có thể có padding trong `struct` | Có metadata/cấp phát riêng cho từng mảng |
| Tính độc lập của một bản ghi | Thường dễ đóng gói và chuyển giao | Phải ghép lại từ các mảng trường |

Khi so sánh `O(n)` và `O(fn)`, nhớ rằng nếu số trường `f` là một hằng số nhỏ, cả hai đều là **`O(n)`**. Điểm khác biệt quan trọng thường là **số byte di chuyển**, **lượng dữ liệu phải tải vào cache** và **độ phức tạp duy trì quan hệ giữa các trường**.

## 13. Ví dụ lựa chọn theo yêu cầu ứng dụng

### 13.1. Hệ thống phát hiện bất thường trên một triệu bản ghi

Giả sử mỗi bản ghi có khoảng hai mươi thuộc tính, nhưng vòng kiểm tra bất thường chỉ cần `temperature` và `pressure`. Bố trí SoA đặt hai mảng `temperature` và `pressure` liên tiếp có thể giúp giảm việc nạp các trường không liên quan, phù hợp với xử lý theo lô và có thể dễ vector hóa hơn.

Nếu ứng dụng vẫn cần thường xuyên **truy xuất đầy đủ một bản ghi theo mã định danh**, có thể bổ sung một bảng băm `id → index` và dùng các mảng trường cùng chỉ số để dựng bản ghi. Chỉ mục ấy tốn bộ nhớ và phải được cập nhật nếu bản ghi đổi vị trí.

### 13.2. Dịch vụ nhận một yêu cầu và xử lý một hồ sơ

Nếu đa số truy vấn là “lấy hồ sơ thứ `i`, kiểm tra đủ các trường rồi cập nhật vài thuộc tính”, AoS có thể thuận tiện hơn vì các trường của cùng hồ sơ ở gần nhau về mặt biểu diễn và giao diện mã nguồn.

### 13.3. Xử lý ảnh, mô phỏng và hệ thống thực thể

Dữ liệu điểm ảnh có thể được tổ chức dạng **xen kẽ kênh** (*interleaved*, gần với AoS: `RGBRGB...`) hoặc dạng **tách kênh** (*planar*, gần với SoA: `RRR... GGG... BBB...`). Nếu thuật toán thường xử lý một kênh, planar có thể thuận lợi; nếu xử lý đủ các kênh mỗi điểm ảnh, interleaved có thể hợp lý hơn.

Tương tự, các hệ thống **ECS (Entity Component System)** thường tổ chức thành phần theo những tập cấu phần được xử lý cùng nhau, nhằm tránh phải quét qua dữ liệu không dùng tới. Tuy nhiên, cách bố trí thực tế của một ECS có thể là SoA, AoSoA hoặc dạng khối lai, tùy thiết kế.

### 13.4. Chọn theo kết quả đo

Một quy trình quyết định hợp lý:

1. Liệt kê các truy vấn và vòng lặp chạy nhiều nhất: đọc **theo bản ghi** hay **theo trường**?
2. Xác định số lượng `n`, số trường `f`, kích thước từng trường và nhu cầu thêm/xóa/sắp xếp.
3. Ước lượng số byte hữu ích trên mỗi bước, khả năng dùng cache và yêu cầu vector hóa.
4. Chọn bố trí đơn giản nhất vẫn đáp ứng tốt các thao tác quan trọng.
5. Đo hiệu năng, mức dùng bộ nhớ và chi phí cập nhật trên dữ liệu đại diện trước khi tối ưu thêm.

Đừng chuyển đổi bố trí chỉ để giảm một hằng số trên lý thuyết nếu phần việc thực tế bị chi phối bởi I/O, khóa đồng bộ, tra cứu mạng hoặc những thao tác khác.

## 14. Những sai lầm thường gặp

| Nhầm lẫn | Vì sao nguy hiểm? | Cách nghĩ đúng |
|---|---|---|
| “SoA chắc chắn nhanh hơn AoS” | Phụ thuộc số trường sử dụng, kích thước dữ liệu và mô hình truy cập | Đánh giá workload và đo hiệu năng |
| “AoS quét một trường là `O(n²)`” | Stride lớn không thay đổi số bản ghi phải duyệt | Vẫn `O(n)`, khác hệ số và đặc tính cache |
| “Cứ tách trường là đã giảm bộ nhớ” | Có metadata, padding riêng, capacity và chi phí duy trì | Tính toàn bộ chi phí lưu trữ |
| “Chỉ cần `x.sort()` để sắp các bản ghi SoA” | Các trường không còn thuộc cùng bản ghi | Áp dụng một hoán vị chung cho tất cả cột |
| “Có thể xóa `ids[i]` mà không đụng các mảng khác” | Độ dài lệch, sai quan hệ ở các chỉ số | Xóa đúng bản ghi logic trong mọi cột |
| “Thêm tất cả cột lần lượt là thao tác nguyên tử” | Một lỗi ở giữa có thể để lại trạng thái không đồng bộ | Có rollback/transaction hoặc xây trạng thái mới |
| “Một bản ghi C có kích thước bằng tổng `sizeof` trường” | Struct có thể có padding | Dùng `sizeof(struct)` và `offsetof` |
| “SoA bắt buộc nằm trong một khối chung” | Mỗi cột có thể được cấp phát riêng | Phân biệt tính liên tiếp **trong cột** và giữa các cột |
| “Python `list[dict]` là mảng `struct` vật lý” | `dict` là đối tượng riêng, nhiều tham chiếu | Chỉ coi đây là mô hình logic |
| “Đổi thứ tự phần tử không ảnh hưởng chỉ số lưu ở nơi khác” | Các chỉ số dùng làm định danh tạm thời sẽ thay đổi ý nghĩa | Giữ `id` và duy trì ánh xạ `id → index` |
| “SoA tự bảo đảm SIMD” | Trình biên dịch và phụ thuộc dữ liệu còn quyết định | Kiểm tra tối ưu hóa và đo đạc |
| “AoSoA không có chi phí gì ngoài SoA” | Có ánh xạ block/local và xử lý khối cuối | Chọn kích thước khối có cơ sở |

## 15. Bài tập tự kiểm tra

Cho ba bản ghi:

```text
P0: id=1, x=2, y=5
P1: id=2, x=4, y=7
P2: id=3, x=6, y=9
```

**Bài 1.** Hãy viết dữ liệu dưới dạng AoS (mảng ba bản ghi) và SoA (ba mảng `id`, `x`, `y`). Phần tử ở chỉ số `1` trong ba mảng SoA phải tương ứng với bản ghi nào?

**Bài 2.** Giả sử `sizeof(struct Record)=24` byte và `offsetof(struct Record,x)=8` byte. Mảng AoS bắt đầu ở địa chỉ `1000`. Trường `x` của bản ghi `i=2` có địa chỉ nào? Nếu mảng SoA chứa `x` có `base_x=3000`, mỗi giá trị rộng `8` byte, địa chỉ `x[2]` là bao nhiêu?

**Bài 3.** Một thuật toán chỉ cần tính trung bình `x` trên một triệu bản ghi, mỗi bản ghi AoS rộng `32` byte, mỗi `x` rộng `8` byte. Vì sao SoA có thể thuận lợi hơn dù cả hai đều `O(n)`?

**Bài 4.** Trong SoA, `ids=[1,2,3]`, `xs=[2,4,6]`, `ys=[5,7,9]`. Nếu chỉ xóa `xs[1]`, bất biến nào bị phá vỡ và thông tin nào có thể bị hiểu nhầm?

**Bài 5.** Muốn xóa bản ghi `id=2` nhưng giữ thứ tự, cần thao tác trên những mảng nào? Kết quả ba mảng là gì?

**Bài 6.** Nếu muốn sắp theo `x` giảm dần và giữ đúng `id`, `y`, thứ tự `id` mới phải là gì? Có được chỉ sắp `xs` không?

**Bài 7.** Một hệ thống truy vấn ngẫu nhiên từng bản ghi và thường cần đủ mười trường. AoS hay SoA nên được xem xét trước? Nêu ít nhất một điều kiện có thể khiến kết luận thay đổi.

**Bài 8.** Với AoSoA có kích thước khối `B=4`, bản ghi toàn cục `i=10` thuộc khối nào (từ `0`) và vị trí cục bộ nào?

**Bài 9.** Một SoA có `n` bản ghi, `f` trường, mỗi mảng trường là mảng động. Tính số ô phải dịch nếu xóa bản ghi ở vị trí `i` và giữ thứ tự. Nếu `f` được xem là hằng số, độ phức tạp trường hợp xấu nhất là gì?

**Bài 10.** Vì sao một `list` gồm các `dict` trong Python không phải bằng chứng rằng AoS vật lý có dữ liệu trường nằm liên tiếp trong bộ nhớ? Nếu muốn kiểm tra tác động cache/SIMD, nên đo bằng loại dữ liệu nào?

### Đáp án gợi ý

1. AoS: `[(1,2,5),(2,4,7),(3,6,9)]`. SoA: `id=[1,2,3]`, `x=[2,4,6]`, `y=[5,7,9]`. Chỉ số `1` thuộc bản ghi `id=2` với `x=4`, `y=7`.
2. AoS: `1000+2×24+8=1056`. SoA: `3000+2×8=3016`.
3. `x` ở SoA nằm liên tiếp, thuận lợi khi nạp cache và vector hóa. AoS có thể phải đọc qua nhiều byte của các trường không dùng; Big-O của hai vòng quét vẫn là `O(n)`.
4. Các mảng không còn cùng độ dài và `xs[i]` không còn khớp `ids[i]`, `ys[i]`. Chẳng hạn `xs[1]` sau xóa là giá trị `6` thuộc `id=3`, nhưng `ids[1]` vẫn là `2`.
5. Xóa chỉ số `1` trong **cả ba** mảng: `ids=[1,3]`, `xs=[2,6]`, `ys=[5,9]`.
6. Khi sắp `x` giảm, thứ tự bản ghi là `id=[3,2,1]` và `y=[9,7,5]`. Không được chỉ sắp `xs`.
7. AoS thường là điểm xuất phát vì các trường cùng bản ghi nằm gần nhau. Tuy nhiên, nếu mười trường rất lớn, chỉ đôi ba trường thực sự được dùng, hoặc thao tác xử lý lô/SIMD chiếm phần lớn thời gian, SoA hay bố trí lai có thể hợp lý hơn.
8. `block=10//4=2`, `local=10%4=2`.
9. Mỗi cột dịch `n-i-1` ô, nên tổng `f(n-i-1)`. Với `f` cố định, trường hợp xấu nhất là `O(n)`.
10. `list` và `dict` là các đối tượng được quản lý qua tham chiếu, không phải một `struct` C nằm nối tiếp. Nên đo bằng bộ đệm số có kiểu phần tử rõ ràng như mảng `struct`/mảng trường trong C/C++, hoặc mảng số chuyên dụng có bố trí xác định.

## 16. Ghi nhớ

**AoS (Array of Structures)** đặt **các trường của từng bản ghi gần nhau**, thuận tiện khi chương trình thường xử lý đầy đủ một đối tượng. **SoA (Structure of Arrays)** đặt **các giá trị của từng trường gần nhau**, thuận lợi khi duyệt hoặc tính toán hàng loạt trên một vài trường, thường giúp tăng tính cục bộ và mở cơ hội vector hóa. Cả hai vẫn có truy cập theo chỉ số `O(1)`; quét toàn bộ `n` bản ghi vẫn là `O(n)` khi số trường cố định. SoA đòi hỏi bất biến quan trọng: **các mảng trường cùng độ dài và những giá trị ở cùng chỉ số luôn thuộc cùng bản ghi**. Khi thêm, xóa hoặc sắp xếp, phải duy trì bất biến ấy trên mọi cột. Không có cách bố trí nào luôn tối ưu: hãy chọn theo dạng truy cập chủ đạo, số byte hữu ích, chi phí cập nhật, khả năng mở rộng và kết quả đo trên ứng dụng thực tế.
