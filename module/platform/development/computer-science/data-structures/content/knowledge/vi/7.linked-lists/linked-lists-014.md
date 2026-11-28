# So sánh chi phí cấp phát, bộ nhớ đệm và dịch chuyển dữ liệu với mảng

## 1. Vì sao `O(1)` chưa chắc nhanh hơn `O(n)` trong thực tế?

Giả sử một ứng dụng quản lý `100.000` mã công việc và cần thực hiện hai loại thao tác:

1. Thường xuyên duyệt hết mọi mã để thống kê.
2. Thỉnh thoảng chèn hoặc xóa một công việc ở giữa danh sách.

Khi học bảng độ phức tạp, ta thường thấy:

- **Mảng động** (*dynamic array*): đọc theo chỉ số `O(1)`, chèn/xóa giữa mảng có thể `O(n)` vì phải dịch dữ liệu.
- **Danh sách liên kết** (*linked list*): đã có con trỏ hoặc iterator tới đúng vị trí thì nối/tháo nút thường `O(1)`.

Dễ từ đó kết luận “nếu chèn/xóa nhiều thì danh sách liên kết luôn nhanh hơn”. Kết luận này **thiếu điều kiện**. Một thao tác nối nút có thể cần cấp phát bộ nhớ, trong khi CPU có thể dịch một khối mảng liên tiếp rất nhanh. Danh sách liên kết cũng có thể phải lần theo nhiều con trỏ để tìm vị trí, khiến lợi thế `O(1)` của phần nối nút không còn quyết định tổng thời gian.

Để chọn cấu trúc dữ liệu tốt, cần xét ít nhất **ba nhóm chi phí**:

- **Cấp phát và thu hồi bộ nhớ:** mảng thường cấp phát theo khối; danh sách liên kết thông thường có thể cấp phát cho từng nút.
- **Bộ nhớ đệm và kiểu truy cập:** mảng lưu các ô cạnh nhau; các nút liên kết có thể nằm rải rác, dẫn đến truy cập theo con trỏ khó dự đoán.
- **Dịch chuyển dữ liệu và sửa liên kết:** mảng thường phải dời các phần tử phía sau vị trí cập nhật; danh sách liên kết có thể chỉ đổi vài con trỏ khi vị trí đã biết.

Sau bài này, bạn sẽ biết cách phân tích cả Big-O lẫn chi phí hằng số, bộ nhớ phụ, tính cục bộ, con trỏ/iterator và kiểu truy vấn; biết khi nào dùng mảng, danh sách liên kết, hoặc một cách tổ chức trung gian.

Đây là phần của chương **Danh sách liên kết** thuộc học phần **Cấu trúc dữ liệu**. Những đánh đổi này cũng xuất hiện trong mảng, stack, queue, bảng băm, cây, heap và đồ thị: cấu trúc phù hợp phụ thuộc bất biến, thao tác và chi phí thời gian/bộ nhớ của toàn bộ bài toán.

## 2. So sánh hai cách biểu diễn trước khi nói về tốc độ

### 2.1. Mảng liên tiếp và mảng động

Với mảng lưu trực tiếp các giá trị có kích thước cố định:

```text
Mảng A:

Địa chỉ:    base    base+s   base+2s  base+3s  ...
             |         |        |        |
             v         v        v        v
            [10]      [20]     [30]     [40]   ...

Chỉ số:      0         1        2        3
```

Nếu mỗi ô rộng `s` byte, địa chỉ của ô `i` là:

\[
\operatorname{address}(A[i])=base+i\cdot s.
\]

Tính địa chỉ không cần đi qua các phần tử trước, nên **truy cập theo chỉ số** có chi phí `O(1)` trong mô hình RAM.

Một **mảng động** có hai đại lượng:

- `n`: số phần tử đang sử dụng (*size/length*).
- `c`: số ô đang được cấp phát (*capacity*), với `0\le n\le c`.

Khi thêm cuối và `n<c`, có thể ghi vào ô còn trống. Khi hết sức chứa, mảng động có thể cần cấp phát vùng lớn hơn và chuyển phần tử sang vùng mới.

### 2.2. Danh sách liên kết đơn và đôi

Danh sách liên kết lưu một chuỗi **nút**, mỗi nút có giá trị và ít nhất một liên kết:

```text
Danh sách liên kết đơn:

head --> [10 | next] --> [20 | next] --> [30 | next] --> NULL

Danh sách liên kết đôi:

NULL <-- [prev | 10 | next] <--> [prev | 20 | next] <--> [prev | 30 | next] --> NULL
```

Con trỏ `next` cho biết nút tiếp theo nằm ở đâu; không cần giả định rằng địa chỉ của hai nút kề nhau cũng kề nhau trong bộ nhớ.

Với một nút `Node` biết trước, ta có thể đọc giá trị hoặc chuyển sang nút kế tiếp bằng một lần theo liên kết. Nhưng nếu muốn tìm **phần tử thứ `i`** tính từ `head` trong danh sách liên kết đơn thông thường, phải đi qua `i` liên kết: thời gian `O(i+1)`, trường hợp xấu nhất `O(n)`.

**Chú ý về ngôn ngữ:** Python `list` thực chất là mảng động của **các tham chiếu**, không phải một danh sách liên kết. `std::vector<T>` của C++ là một container có vùng lưu phần tử liên tiếp; `std::list<T>` thường là danh sách liên kết đôi. Khi nói về chi phí cache, cần phân biệt mảng các **giá trị trực tiếp** với mảng các **con trỏ tới đối tượng ở nơi khác**.

## 3. Phân tích đúng phải nêu rõ mô hình chi phí

Các phát biểu Big-O thông dụng thường giả định:

1. Đọc/ghi một ô có kích thước cố định tốn `O(1)`.
2. So sánh một khóa có kích thước cố định tốn `O(1)`.
3. Biết trước con trỏ hoặc iterator tới nút nếu đang tính **riêng** chi phí nối/tháo nút.
4. Không có thao tác đồng thời gây thay đổi danh sách/mảng giữa lúc thuật toán đang chạy.
5. Chương trình có đủ bộ nhớ và các đối tượng/con trỏ hợp lệ.

Trong chương trình thực, thời gian một thao tác còn phụ thuộc:

\[
T\approx T_{\text{tìm vị trí}}
+T_{\text{cấp phát}}
+T_{\text{đọc/ghi bộ nhớ}}
+T_{\text{dịch/chỉnh liên kết}}
+T_{\text{thu hồi}}.
\]

Đây là cách **phân rã chi phí để suy luận**, không phải công thức đo chuẩn cho mọi CPU. Một số thành phần có thể chồng lấp do pipeline, tối ưu hóa hoặc cache; nhưng mô hình giúp tránh bỏ sót phần việc quan trọng.

Ví dụ: “chèn vào danh sách liên kết `O(1)`” chỉ nói rằng **số thao tác sửa liên kết là hằng số** khi đã biết vị trí và có nút để nối. Nó không tự nói rằng bước tìm vị trí, cấp phát nút, khởi tạo giá trị hay thu hồi bộ nhớ đều `O(1)` trong mọi trường hợp triển khai.

## 4. Cấp phát bộ nhớ: cấp theo khối so với theo nút

### 4.1. Mảng thường cấp phát một khối

Một mảng có `n` phần tử kích thước `s` byte có thể dùng một vùng liên tiếp cỡ `n\cdot s` byte (bỏ qua phần quản lý và căn chỉnh).

```text
Một lần cấp phát vùng chứa:

ALLOCATE [ ô 0 | ô 1 | ô 2 | ... | ô n-1 ]
                   |
            đọc/ghi theo chỉ số
```

Mảng động có thể cấp phát vùng rộng hơn số ô đang dùng, vì nó muốn dự phòng cho các lần thêm cuối:

\[
\text{dữ liệu phần tử đang dùng}\approx n s,\qquad
\text{sức chứa ô phần tử}\approx c s.
\]

Khoảng `(c-n)s` là **dung lượng dự phòng**, không phải dữ liệu logic. Đổi lại, nhiều lần thêm cuối có thể không cần gọi bộ cấp phát.

### 4.2. Danh sách liên kết thông thường có thể cấp phát mỗi nút

Một nút đơn thường chứa:

```c
struct SinglyNode {
    int value;
    struct SinglyNode *next;
};
```

Một nút đôi thường chứa:

```c
struct DoublyNode {
    struct DoublyNode *prev;
    struct DoublyNode *next;
    int value;
};
```

Nếu `n` nút được tạo độc lập bằng bộ cấp phát, chương trình có thể thực hiện đến `n` lần cấp phát cho `n` phần tử. Mỗi lần cấp phát có thể liên quan đến metadata, căn chỉnh, tìm khối rảnh, đồng bộ bộ cấp phát và nhiều hành vi khác tùy bộ nhớ đang được quản lý.

**Không có một chi phí cố định cho `malloc` hay `new` áp dụng cho mọi nền tảng.** Thời gian một lần cấp phát có thể rất nhanh nhờ cache nội bộ của allocator, hoặc đắt hơn khi xảy ra phân mảnh, tranh chấp hoặc phải xin thêm bộ nhớ từ hệ điều hành.

Danh sách liên kết cũng **không bắt buộc** phải cấp phát mỗi nút riêng lẻ: có thể dùng *memory pool*, *arena*, mảng các nút có chỉ số liên kết, hoặc **intrusive list** có hook nhúng sẵn trong đối tượng. Các cách này thay đổi chi phí cấp phát và tính cục bộ nhưng có thêm điều kiện quản lý vòng đời.

### 4.3. Vùng cấp phát và thời điểm giải phóng

| Tình huống | Mảng động | Danh sách liên kết cấp phát nút riêng |
|---|---|---|
| Khởi tạo `n` phần tử | Thường xây vùng chứa theo khối | Có thể tạo `n` nút |
| Thêm cuối khi còn dung lượng | Không cần cấp phát | Thường cần nút mới nếu chưa có sẵn |
| Thêm giữa khi đã có nút/nơi trống | Dịch các ô sau vị trí | Nối nút; cấp phát nút tùy thiết kế |
| Xóa một phần tử | Có thể dịch nhiều ô; thường không thu hồi riêng một ô từ allocator | Tháo nút và có thể thu hồi nút đó |
| Thu hồi toàn bộ container | Giải phóng vùng chứa; hủy các phần tử còn sống theo hợp đồng | Thường duyệt và hủy/thu hồi từng nút |

Trong C++ chuẩn, thời điểm gọi hàm hủy của phần tử và thời điểm trả bộ nhớ về allocator không nhất thiết giống nhau. Bảng mô tả xu hướng **quản lý vùng lưu**, không áp đặt một cách cài đặt cụ thể lên mọi thư viện.

## 5. Chi phí bộ nhớ: giá trị hữu ích, con trỏ và padding

Xét `n` phần tử có payload cố định rộng `s` byte; kích thước một con trỏ là `p` byte.

### Mảng chứa giá trị trực tiếp

Khi chỉ cần lưu `n` giá trị và không dự phòng:

\[
M_{\text{array,data}}\approx n s.
\]

Với mảng động có sức chứa `c\ge n`:

\[
M_{\text{dynamic,data}}\approx c s,
\]

cộng bộ nhớ cho metadata của container và allocator nếu có.

### Danh sách liên kết

Một nút đơn cần lưu payload và một con trỏ; nút đôi cần payload và hai con trỏ. Bỏ qua padding, ta ước lượng:

\[
M_{\text{singly,node}}\gtrsim n(s+p),\qquad
M_{\text{doubly,node}}\gtrsim n(s+2p).
\]

Dấu `\gtrsim` nhấn mạnh rằng kích thước nút **có thể lớn hơn** do căn chỉnh, metadata allocator và trường bổ sung. Danh sách có `head`, `tail` hoặc sentinel cũng cần một lượng bộ nhớ quản lý riêng.

Ví dụ giả định `int` rộng `4` byte, con trỏ rộng `8` byte:

| Cấu trúc / thành phần | Kích thước lý tưởng cho một phần tử | Ví dụ padding có thể ảnh hưởng? |
|---|---:|---|
| Mảng `int` trực tiếp | `4` byte | Ô `int` đã có kích thước cố định |
| Nút đơn `int + next` | Ít nhất `12` byte về tổng trường | Có, có thể cần `16` byte |
| Nút đôi `prev + next + int` | Ít nhất `20` byte về tổng trường | Có, có thể cần `24` byte |

Đây là ví dụ về **mô hình bộ nhớ**, không phải kết quả `sizeof` bảo đảm trên mọi máy. Với `100.000` giá trị, một mảng `int` cần khoảng `400.000` byte cho dữ liệu, còn `100.000` nút đôi `24` byte/nút đã tốn khoảng `2.400.000` byte **chưa kể** metadata của các lần cấp phát riêng.

Đánh đổi còn phụ thuộc loại payload. Nếu mỗi phần tử là một cấu trúc lớn `1 KiB`, vài con trỏ thêm trên mỗi nút chiếm tỷ lệ nhỏ hơn so với trường hợp payload chỉ `4` byte. Khi mảng chỉ lưu **con trỏ** tới đối tượng lớn, các ô con trỏ liên tiếp nhưng đối tượng được trỏ tới vẫn có thể rải rác như ở danh sách liên kết.

## 6. Cache locality: các byte gần nhau có quan trọng không?

CPU không nhất thiết đọc từ RAM một byte mỗi lần. Dữ liệu thường được chuyển giữa các tầng bộ nhớ dưới dạng **dòng cache** (*cache line*), có kích thước tùy hệ thống; `64` byte là một kích thước phổ biến để minh họa, **không phải bảo đảm cho mọi CPU**.

Giả sử một mảng chứa các số nguyên `4` byte, nằm trong một vùng liên tiếp. Một dòng cache `64` byte có thể chứa tối đa `16` phần tử liên tiếp nếu vị trí căn chỉnh phù hợp:

```text
Một dòng cache 64 byte (minh họa):

[ 0 ][ 1 ][ 2 ][ 3 ][ 4 ][ 5 ][ 6 ][ 7 ]
[ 8 ][ 9 ][10 ][11 ][12 ][13 ][14 ][15 ]

               16 giá trị × 4 byte
```

Khi duyệt từ trái sang phải, sau lần nạp chứa `A[i]`, nhiều lần đọc `A[i+1]`, `A[i+2]` ... có thể **trúng cache**. Bộ xử lý cũng thường có cơ chế *prefetch* để nhận biết truy cập tuần tự và chuẩn bị dữ liệu tiếp theo.

Danh sách liên kết không bảo đảm tính liên tiếp:

```text
Địa chỉ minh họa trong heap:

head ──> Node A tại 0x1000 ──> Node B tại 0x9000
                                    |
                                    v
                              Node C tại 0x3000
```

Các nút kế nhau về mặt **logic** nhưng có thể xa nhau về mặt **địa chỉ**. Mỗi lần đi từ `node` sang `node.next` có khả năng phải nạp vùng nhớ mới. Nếu các nút phân tán và dữ liệu không nằm sẵn trong cache, nhiều lần truy cập có độ trễ lớn hơn đọc một mảng liên tiếp.

### Ba dạng tính cục bộ

- **Tính cục bộ không gian** (*spatial locality*): vừa đọc một địa chỉ thì nhiều khả năng sẽ sớm đọc địa chỉ gần đó.
- **Tính cục bộ thời gian** (*temporal locality*): dữ liệu vừa dùng có khả năng được sử dụng lại sớm.
- **Tính cục bộ của luồng truy cập/prefetch:** mẫu địa chỉ tuần tự thường dễ được phần cứng dự đoán hơn chuỗi con trỏ phụ thuộc kết quả đọc trước.

Mảng có lợi thế tự nhiên về tính cục bộ không gian khi duyệt tuần tự. Danh sách liên kết **cũng có thể** có tính cục bộ tốt nếu nút được cấp phát gần nhau và duyệt theo thứ tự vùng nhớ; đó không phải điều kiện bắt buộc của cấu trúc. Ngược lại, truy cập ngẫu nhiên vào mảng rất lớn không bảo đảm luôn trúng cache.

## 7. Pointer chasing: vì sao lần theo liên kết có thể chậm?

Khi duyệt danh sách:

```c
for (Node *cur = head; cur != NULL; cur = cur->next) {
    consume(cur->value);
}
```

Địa chỉ của nút tiếp theo chỉ biết được **sau khi đọc `cur->next`**. Lần nạp sau phụ thuộc vào kết quả của lần nạp trước:

```text
load Node A → đọc next của A → biết địa chỉ B
load Node B → đọc next của B → biết địa chỉ C
load Node C → ...
```

Chuỗi phụ thuộc dữ liệu này được gọi là **pointer chasing**. CPU có thể khó chồng lấp nhiều lần nạp trước khi biết địa chỉ cần nạp. Vì vậy, ngay cả khi hai vòng lặp đều thực hiện `n` lần, thời gian thực tế có thể rất khác nhau.

Với mảng:

```c
for (size_t i = 0; i < n; ++i) {
    consume(data[i]);
}
```

Địa chỉ `data[i+1]` được tính từ `base`, `i` và kích thước phần tử; phần cứng có thể dễ nhận biết các địa chỉ liên tiếp. Trong các vòng lặp đơn giản, compiler cũng có thể vector hóa xử lý nhiều phần tử cùng lúc.

**Big-O của cả hai phép duyệt là `O(n)`**, nhưng mô hình chi phí của CPU không đồng nhất: số lần cache miss, khả năng nạp trước, phụ thuộc tải và băng thông bộ nhớ ảnh hưởng mạnh đến thời gian.

### Mảng con trỏ không tự biến thành mảng giá trị

Ví dụ C++:

```cpp
std::vector<Record*> ptrs;
```

Các ô `ptrs[i]` nằm liên tiếp, nên **duyệt các con trỏ** có tính cục bộ tốt. Nhưng các `Record` mà chúng trỏ tới có thể nằm rải rác; phép `ptrs[i]->field` vẫn cần thêm một lần truy cập bộ nhớ tới đối tượng. Do đó, khi so sánh cache, phải kiểm tra **payload được lưu trực tiếp hay thông qua con trỏ**.

## 8. Mảng dịch dữ liệu khi chèn hoặc xóa: đếm chính xác bao nhiêu ô

Cho mảng `A` có `n` phần tử; muốn giữ thứ tự của các phần tử cũ.

### Chèn trước vị trí i

Nếu `0\le i\le n` và vùng chứa đủ sức chứa, ta dịch các phần tử từ chỉ số `i` tới `n-1` sang phải một vị trí:

\[
\boxed{\operatorname{moves}_{insert}=n-i.}
\]

```text
Chèn 99 tại i = 1:

Trước: [10, 20, 30, 40, _ ]
       [10, 20, 30, 40, 40]   dời 40
       [10, 20, 30, 30, 40]   dời 30
       [10, 20, 20, 30, 40]   dời 20
Sau:   [10, 99, 20, 30, 40]

Số phần tử dịch = 4 - 1 = 3.
```

Phải thực hiện dịch **từ phải sang trái** để không ghi đè giá trị nguồn chưa được sao chép.

### Xóa tại vị trí i

Nếu `0\le i<n`, các phần tử đứng sau `i` dịch trái:

\[
\boxed{\operatorname{moves}_{delete}=n-i-1.}
\]

```text
Xóa vị trí i = 1:

Trước: [10, 20, 30, 40]
       [10, 30, 30, 40]  dời 30
       [10, 30, 40, 40]  dời 40
Sau:   [10, 30, 40]

Số phần tử dịch = 4 - 1 - 1 = 2.
```

Dịch trái cần thực hiện **từ trái sang phải**. Ô cuối sau xóa không còn thuộc độ dài logic; trong bộ đệm chứa tham chiếu, triển khai còn phải xử lý tham chiếu dư để không giữ đối tượng không cần thiết.

Nếu chèn hoặc xóa ở đầu mảng, số ô dịch tỷ lệ `n`, nên trường hợp xấu nhất là **`O(n)`**. Nếu thêm cuối khi đã có chỗ hoặc xóa cuối, không phải dịch các ô trước đó.

### “Dời `O(n)` ô” không đồng nghĩa “chậm trong mọi trường hợp”

Vùng liên tiếp có thể được sao chép bằng các lệnh tối ưu, vector hóa hoặc hàm chuyển bộ nhớ xử lý vùng chồng lấp như `memmove` đối với kiểu dữ liệu phù hợp. Dịch `n/2` phần tử nhỏ theo một khối tuyến tính đôi khi nhanh hơn đi tới `n/2` nút rải rác và cấp phát thêm nút.

Tuy nhiên, không được giả định mọi phép dịch mảng đều là `memmove` thuần byte. Với đối tượng C++ không *trivially movable*, việc dời phần tử có thể gọi phép di chuyển/gán, và các thao tác đó có chi phí, ngoại lệ hoặc tác dụng phụ riêng. Phân tích chi phí cần dựa trên kiểu `T` đang được lưu.

## 9. Danh sách liên kết cập nhật con trỏ, nhưng tìm vị trí có thể tốn O(n)

Một danh sách liên kết đơn chứa:

```text
head --> A --> B --> C --> D --> NULL
```

Nếu đã có **con trỏ tới B**, muốn chèn X ngay sau B:

```text
X.next = B.next
B.next = X

Kết quả:
head --> A --> B --> X --> C --> D --> NULL
```

Chỉ cần cập nhật hai liên kết, nên phần thao tác **nối nút** là `O(1)`.

Nếu muốn xóa `C` trong danh sách liên kết **đơn**, cần biết **nút đứng trước C** là B (hoặc có một cơ chế khác có hợp đồng tương ứng):

```text
B.next = C.next
```

Nút `C` sau khi tháo vẫn phải được hủy hoặc quản lý theo chính sách sở hữu. Với **danh sách liên kết đôi**, nếu biết `C` thì có thể truy cập cả `C.prev` và `C.next` để tháo nó trong `O(1)`; điều kiện là các con trỏ hợp lệ và không có tranh chấp đồng thời.

### Chèn/xóa theo chỉ số không giống chèn/xóa theo con trỏ đã biết

Muốn “xóa phần tử tại chỉ số `i`” trong danh sách liên kết đơn từ `head`:

1. Đi đến nút đứng trước vị trí `i`: tốn `O(i)`, trường hợp xấu nhất `O(n)`.
2. Đổi liên kết: `O(1)`.
3. Xử lý hủy/thu hồi nút: còn tùy chính sách bộ nhớ.

Do đó thao tác tổng thể thường **`O(n)` trong trường hợp xấu nhất**, không phải `O(1)`. Nếu chỉ biết giá trị cần xóa, tìm tuyến tính cũng có thể phải duyệt `n` nút.

Trong mảng, **tìm vị trí bằng chỉ số** là `O(1)`, nhưng **dịch phần đuôi** có thể là `O(n)`. Hai cấu trúc trả giá ở **hai phần khác nhau của thao tác**.

| Yêu cầu | Mảng động | Danh sách liên kết |
|---|---|---|
| Truy cập `i` đã biết | `O(1)` | `O(n)` xấu nhất |
| Chèn tại vị trí `i`, giữ thứ tự | `O(n)` xấu nhất do dịch | `O(n)` xấu nhất nếu phải tìm vị trí |
| Chèn sau nút đã có con trỏ/iterator | Mảng vẫn có thể dịch `O(n)` | Phần nối liên kết `O(1)` |
| Xóa nút đã có iterator | Mảng có thể dịch `O(n)` | Danh sách đôi tháo liên kết `O(1)` |
| Tìm giá trị trên dữ liệu chưa có chỉ mục | `O(n)` | `O(n)` |

Chi phí bộ cấp phát và hủy đối tượng chưa được gộp vào bảng; cần tính thêm khi đánh giá hệ thống thực tế.

## 10. Mảng động: vì sao thêm cuối là O(1) khấu hao?

Mảng động không mở rộng vùng lưu mỗi lần thêm phần tử. Một chính sách phổ biến là **tăng sức chứa theo tỷ lệ**; minh họa bằng tăng gấp đôi:

```text
capacity=2: [A, B]

Thêm C khi đầy:
    cấp phát capacity=4
    dời A, B
    ghi C
    [A, B, C, _]

Thêm D:
    ghi vào ô trống
    [A, B, C, D]

Thêm E khi đầy:
    cấp phát capacity=8
    dời A, B, C, D
    ghi E
```

Một lần mở rộng có thể mất `O(n)` vì phải chuyển `n` phần tử. Nhưng qua nhiều lần thêm cuối, tổng số phần tử được dời trong các lần mở rộng có thể bị chặn bởi một cấp số nhân:

\[
1+2+4+\cdots+2^k<2^{k+1}.
\]

Nếu sức chứa tăng theo một tỷ lệ lớn hơn `1` cố định, tổng công chuyển qua `n` lần thêm cuối là **`O(n)`** (với chi phí chuyển một phần tử `O(1)`). Vì vậy **mỗi lần thêm cuối có chi phí `O(1)` khấu hao** (*amortized*), dù **một lần riêng lẻ** vẫn có thể là `O(n)`.

Tăng sức chứa theo tỷ lệ sử dụng thêm bộ nhớ trống để giảm số lần cấp phát. Chính sách tăng, giảm và khả năng giữ nguyên địa chỉ khác nhau theo thư viện; không nên mặc định mọi mảng động đều gấp đôi chính xác.

### So sánh với danh sách liên kết khi thêm cuối

- Danh sách liên kết đôi có con trỏ `tail`: phần **nối nút** ở cuối là `O(1)`; nếu nút cần cấp phát, tính thêm chi phí cấp phát.
- Danh sách liên kết đơn **không có tail**: tìm cuối bằng cách duyệt có thể mất `O(n)`.
- Mảng động còn chỗ: thêm cuối không cần dời dữ liệu, `O(1)`.
- Mảng động hết chỗ: có thể dời toàn bộ vùng, `O(n)` ở lần đó, nhưng `O(1)` khấu hao qua chuỗi thao tác.

Vì thế, tiêu chí “cần thêm cuối nhiều” **không đủ** để ưu tiên danh sách liên kết so với mảng động.

## 11. Lượng dữ liệu di chuyển khác với số con trỏ phải cập nhật

Giả sử một thao tác chèn vào giữa mảng dài `n` cần dời `k=n-i` phần tử, mỗi phần tử rộng `s` byte. Lượng dữ liệu **được dời về mặt logic** là:

\[
\boxed{B_{\text{move}}=k\cdot s\text{ byte}.}
\]

Ví dụ `n=100.000`, `i=50.000`:

- Với phần tử số nguyên `8` byte, cần dời `50.000` ô, tương đương `400.000` byte dữ liệu phần tử.
- Với phần tử cấu trúc `256` byte lưu trực tiếp, cần dời `12.800.000` byte, tức khoảng `12,2` MiB.
- Với mảng con trỏ `8` byte tới các đối tượng lớn, việc dời `50.000` **con trỏ** cũng là khoảng `400.000` byte, không tự động sao chép toàn bộ đối tượng được trỏ tới.

Những con số này là **kích thước logic của các ô cần dịch**, không nhất thiết bằng lượng lưu thông thực tế qua RAM hay cache: thuật toán thường vừa đọc vừa ghi, có các hiệu ứng cache và tối ưu hóa phần cứng.

Danh sách liên kết đôi khi đã có con trỏ tới nút cần xóa chỉ cập nhật vài con trỏ, bất kể payload là `8` hay `256` byte. Nhưng việc tìm nút và tạo hoặc hủy nó vẫn có chi phí.

**Đối tượng lớn không tự động khiến linked list thắng.** Nếu payload là đối tượng lớn, có thể dùng mảng chứa **định danh hoặc con trỏ** tới các đối tượng có vị trí ổn định; lúc ấy phần dịch của mảng chỉ gồm những ô tham chiếu nhỏ. Đánh đổi là thêm mức gián tiếp khi truy cập dữ liệu thực.

## 12. Ổn định địa chỉ và iterator khi cấu trúc thay đổi

Ngoài thời gian chạy, ứng dụng còn quan tâm **một con trỏ hoặc iterator đã giữ có còn trỏ tới đúng phần tử sau khi cập nhật không**.

### Mảng động

Khi mảng động cần mở rộng và cấp phát lại:

```text
Trước:
    [A][B][C]   tại vùng nhớ 0x1000
       ^
       p trỏ tới B

Mở rộng:
    [A][B][C][D][... ]  tại vùng nhớ 0x8000

Vùng nhớ cũ không còn là nơi lưu các phần tử.
```

Trong C++, `std::vector` có thể làm **mất hiệu lực** con trỏ, tham chiếu và iterator vào phần tử khi cấp phát lại. Ngay cả khi không cấp phát lại, phép chèn/xóa ở giữa cũng có những quy tắc mất hiệu lực đối với các vị trí từ điểm thay đổi trở đi. Cần tra hợp đồng chính xác của API.

### Danh sách liên kết

Với danh sách liên kết có nút được cấp phát riêng, nối/tháo các nút khác thường **không di chuyển đối tượng nút còn sống**. Trong `std::list` C++, chèn một phần tử không làm mất hiệu lực iterator và tham chiếu tới các phần tử khác; xóa phần tử làm mất hiệu lực iterator và tham chiếu tới chính phần tử bị xóa.

Điều này có thể là lý do mạnh để chọn danh sách liên kết khi chương trình giữ iterator lâu dài. Nhưng nút bị xóa vẫn không thể được truy cập tiếp; và nếu vùng lưu dữ liệu thực của phần tử bị quản lý ở nơi khác, vấn đề vòng đời của dữ liệu đó vẫn tồn tại.

### Không nhầm với đối tượng Python

`list` Python lưu các **tham chiếu**. Khi danh sách tăng sức chứa hoặc dịch vị trí, các **ô tham chiếu** có thể thay đổi, nhưng đối tượng Python đang được tham chiếu không nhất thiết bị di chuyển chỉ vì thao tác `insert`. Do vậy, câu “vector di chuyển phần tử làm mất hiệu lực địa chỉ” ở C++ không được sao chép nguyên xi sang cơ chế quản lý đối tượng của Python.

## 13. Ví dụ C++: cùng yêu cầu chèn/xóa, khác điều kiện chi phí

Đoạn mã sau dùng `std::vector<int>` và `std::list<int>` với cùng dữ liệu ban đầu. Nó minh họa cách API mô tả vị trí chèn/xóa, **không phải benchmark**.

```cpp
#include <iostream>
#include <iterator>
#include <list>
#include <vector>

int main() {
    std::vector<int> numbers_vec{10, 20, 30, 40};
    std::list<int> numbers_list{10, 20, 30, 40};

    // Vector: truy cập vị trí bằng chỉ số O(1).
    // Chèn giữa có thể phải dịch các phần tử sau vị trí.
    numbers_vec.insert(numbers_vec.begin() + 2, 99);

    // List: phải đi từ begin() tới vị trí thứ 2 (O(n) tổng quát).
    auto position = std::next(numbers_list.begin(), 2);
    // Nhưng khi đã có iterator position, phần nối nút là O(1).
    auto inserted = numbers_list.insert(position, 99);

    // Xóa phần tử vừa chèn:
    // Vector lại có thể dịch dữ liệu.
    numbers_vec.erase(numbers_vec.begin() + 2);

    // List: đã có iterator inserted nên xóa đúng nút là O(1).
    numbers_list.erase(inserted);

    for (int x : numbers_vec) std::cout << x << " ";
    std::cout << "\n";
    for (int x : numbers_list) std::cout << x << " ";
    std::cout << "\n";
}
```

Kết quả hai dòng đều là `10 20 30 40`.

Điểm cần rút ra:

- `numbers_vec.begin()+2` lấy vị trí trong mảng theo số bước chỉ số với `O(1)`.
- `std::next(numbers_list.begin(),2)` đi qua hai bước liên kết trong ví dụ nhỏ; nói chung tìm iterator tại vị trí `i` từ đầu mất `O(i)`.
- `list.insert(position,99)` tạo một nút mới rồi nối vào vị trí đã biết. Theo hợp đồng độ phức tạp của container, chèn một phần tử tại iterator là `O(1)` về số bước container; **chi phí cấp phát thực tế vẫn là một yếu tố khi đo**.
- `list.erase(inserted)` tháo/hủy nút đã biết trong `O(1)` về độ phức tạp container.
- `vector.erase` phải dồn các phần tử phía sau vị trí xóa, nên có thể mất `O(n)`.

**Lưu ý về C++:** không sử dụng iterator `inserted` sau khi gọi `numbers_list.erase(inserted)`; phần tử mà nó trỏ tới đã bị xóa. Tương tự, không giữ và tiếp tục dùng iterator của `vector` vượt qua một thao tác chèn/xóa nếu hợp đồng API đã làm iterator ấy mất hiệu lực.

## 14. Các phương án trung gian giúp giảm nhược điểm

Thực tế không chỉ có hai lựa chọn “mảng liên tiếp” và “mỗi nút cấp phát riêng”. Một số thiết kế dung hòa ưu/nhược:

### 14.1. Mảng các con trỏ hoặc handle

```text
Mảng chỉ số/con trỏ:
    [*] [*] [*] [*]
     |   |   |   |
     v   v   v   v
     A   B   C   D    (đối tượng ở vùng khác)
```

Khi chèn/xóa ở giữa, mảng phải dịch **các con trỏ/handle**, không cần di chuyển toàn bộ đối tượng. Điều này có thể giúp giữ địa chỉ payload ổn định, nhưng phép đọc payload chịu thêm một lần gián tiếp và có thể không có locality tốt.

### 14.2. Intrusive list

Liên kết `prev/next` được nhúng vào **chính đối tượng** thay vì cấp phát một nút bao mới. Khi đối tượng đã tồn tại và đã biết hook, nối/tháo có thể chỉ sửa con trỏ. Đổi lại, đối tượng mang chi phí hook ngay cả khi chưa tham gia danh sách; người lập trình phải quản lý vòng đời và bảo đảm địa chỉ hook ổn định.

### 14.3. Memory pool hoặc arena cho các nút

Thay vì gọi allocator cho từng nút, ta cấp phát các khối lớn và phân phối nút từ pool. Lợi ích tiềm năng:

- Ít lần gọi allocator tổng quát hơn.
- Có thể đặt nhiều nút gần nhau, cải thiện locality.
- Tái sử dụng nút phù hợp với workload tạo/hủy liên tục.

Đổi lại, pool phải quản lý vùng trống, căn chỉnh, tái sử dụng và lúc giải phóng. Nếu thứ tự duyệt danh sách không tương ứng thứ tự vật lý trong pool, tính cục bộ vẫn có thể kém.

### 14.4. Unrolled linked list / block list

Mỗi nút của danh sách giữ **một khối nhiều phần tử** thay vì đúng một phần tử:

```text
HEAD --> [10,20,30,40] --> [50,60,70,80] --> ...
               block              block
```

Duyệt trong một khối có tính cục bộ cao hơn; số con trỏ phải lần theo khi duyệt nhiều phần tử giảm. Chèn/xóa trong khối có thể phải dịch một số phần tử, nhưng phạm vi dịch giới hạn theo kích thước khối; đôi khi cần tách hoặc gộp khối.

### 14.5. Deque hoặc bộ đệm vòng

Nếu bài toán chỉ cần **thêm cuối/lấy đầu** theo FIFO, một `deque` hoặc **bộ đệm vòng** có thể thực hiện hai thao tác đầu/cuối hiệu quả mà **không** cần dùng danh sách liên kết có nút riêng cho từng phần tử. Cấu trúc đó có bất biến và đặc điểm cấp phát riêng; chọn nó khi bài toán thực sự là hàng đợi.

## 15. Chọn cấu trúc theo workload: ba bài toán điển hình

### Tình huống A: nhật ký một triệu bản ghi, chủ yếu quét tuần tự

Yêu cầu: lưu các giá trị có kích thước nhỏ, thêm cuối và thường xuyên tính tổng hoặc lọc dữ liệu.

**Thường ưu tiên mảng động** hoặc bộ đệm liên tiếp. Lý do: thêm cuối `O(1)` khấu hao, quét tuần tự có locality tốt, ít metadata theo từng phần tử. Danh sách liên kết không mang lại lợi thế đáng kể nếu hiếm khi chèn/xóa giữa.

### Tình huống B: bộ điều phối có sẵn con trỏ tới tác vụ cần chuyển trạng thái

Yêu cầu: thường xuyên tháo một tác vụ đã biết khỏi danh sách `ready`, nối vào `waiting`; các tác vụ có thể tồn tại lâu, được quản lý bởi registry riêng.

**Có thể ưu tiên danh sách liên kết đôi hoặc intrusive list** nếu hợp đồng vòng đời và địa chỉ ổn định được kiểm soát tốt. Chuyển membership chỉ cần một số phép nối con trỏ; không phải dịch phần đuôi mảng.

Nhưng nếu phần lớn thao tác là “tìm tác vụ theo `id`”, nên có chỉ mục phụ như bảng băm. Khi ấy tìm bằng bảng băm có thể lấy con trỏ tới nút nhanh hơn, còn danh sách quản lý thứ tự/quan hệ trạng thái.

### Tình huống C: danh sách kết quả tìm kiếm có nhiều lần chèn theo vị trí

Yêu cầu: hiển thị danh sách theo thứ tự, thỉnh thoảng chèn vào một vị trí được xác định bằng chỉ số.

Mảng động có truy cập `A[i]` nhanh nhưng chèn ở giữa phải dịch. Danh sách liên kết có thể nối nhanh **nếu có iterator tới vị trí**, nhưng để đi tới vị trí `i` tính từ đầu thường tốn `O(n)`. Vì vậy chuyển sang linked list **không đảm bảo** làm toàn bộ thao tác nhanh hơn; chi phí cache và cấp phát có thể khiến mảng vẫn là lựa chọn tốt.

Trong trường hợp rất nhiều chỉnh sửa theo vị trí và cần định vị nhanh, có thể cân nhắc các cấu trúc theo khối, cây cân bằng hỗ trợ chỉ số hoặc cấu trúc chuyên dụng khác thay vì mặc định dùng một danh sách liên kết đơn giản.

## 16. Cách xây dựng benchmark công bằng

Một bài đo nhỏ dễ dẫn tới kết luận sai nếu vô tình đo các công việc khác nhau. Để so sánh mảng và danh sách liên kết, nên:

1. **Xác định workload:** `n` bao nhiêu, phần tử cỡ nào, tỷ lệ duyệt, đọc ngẫu nhiên, chèn/xóa, cấp phát và tìm theo khóa.
2. **Tách từng giai đoạn:** đo xây cấu trúc, tìm vị trí, chèn/xóa, duyệt, hủy; sau đó đo thời gian tổng thể của ứng dụng.
3. **Giữ cùng nội dung và cùng kết quả:** hai cấu trúc phải thực hiện cùng số thao tác và kiểm chứng kết quả bằng nhau.
4. **Nêu rõ có sẵn iterator/con trỏ chưa:** không so “vector chèn tại chỉ số” với “list chèn tại iterator đã chuẩn bị” mà bỏ qua chi phí tìm iterator nếu ứng dụng thực phải tìm.
5. **Kiểm soát cấp phát:** cân nhắc `vector.reserve`, allocator/pool cho list, và đo cả khi không có tối ưu cấp phát.
6. **Kiểm soát kiểu phần tử:** đo cả payload nhỏ và lớn, giá trị lưu trực tiếp và dữ liệu chứa con trỏ.
7. **Lặp lại phép đo:** dùng nhiều lần chạy, thống kê phân bố, kiểm soát kích thước dữ liệu so với cache và ảnh hưởng của trình biên dịch.
8. **Ngăn công việc bị tối ưu bỏ:** kiểm chứng/tiêu thụ kết quả hợp lệ; một benchmark bị compiler loại vòng lặp sẽ cho số liệu vô nghĩa.
9. **Theo dõi bộ nhớ:** ngoài thời gian, xem dung lượng heap, số lần cấp phát, cache miss và CPU counters khi có công cụ phù hợp.

Không nên báo một con số kiểu “linked list chậm hơn mảng đúng 5 lần” nếu không có phép đo trong môi trường cụ thể. Sự chênh lệch có thể thay đổi theo CPU, compiler, allocator, kiểu dữ liệu và cấu trúc truy cập.

**Đặc biệt:** nếu đo thêm một triệu phần tử, một vòng `vector.push_back` với `reserve` và một vòng `list.push_back` cấp phát từng nút đo **cả khác biệt cấp phát**. Đó có thể chính là điều ứng dụng quan tâm, nhưng cần ghi rõ. Nếu muốn cô lập chi phí nối liên kết, hãy chuẩn bị nút trước và đo riêng phần nối.

## 17. Bảng tổng kết nhiều chiều

Giả sử:

- Mảng là mảng động có truy cập trực tiếp theo chỉ số, phần tử kích thước cố định.
- Danh sách là linked list đơn/đôi có nút thông thường, chưa có chỉ mục phụ.
- Các thao tác trên nút đã biết không gồm chi phí tìm nút và cấp phát/thu hồi.

| Đặc điểm | Mảng động | Danh sách liên kết |
|---|---|---|
| Truy cập phần tử thứ `i` | `O(1)` | `O(n)` xấu nhất |
| Duyệt toàn bộ | `O(n)`, thường locality tốt | `O(n)`, có thể pointer chasing và cache miss |
| Thêm cuối | `O(1)` khấu hao | Nối `O(1)` nếu có tail; có thể cần cấp phát nút |
| Chèn giữa theo chỉ số | `O(n)` xấu nhất do dịch | `O(n)` xấu nhất nếu phải tìm nút |
| Chèn sau nút/iterator đã biết | Vẫn có thể dịch `O(n)` | Sửa liên kết `O(1)` |
| Xóa nút đã biết | Có thể dịch `O(n)` | Danh sách đôi `O(1)`; đơn cần biết predecessor |
| Xóa đầu | Dịch `O(n)` | `O(1)` khi có head |
| Xóa cuối | Thường `O(1)` | Đôi với tail `O(1)`; đơn không có predecessor có thể `O(n)` |
| Cấp phát | Thường theo khối; ít lần mở rộng | Có thể theo từng nút |
| Metadata/bộ nhớ phụ mỗi phần tử | Không bắt buộc có con trỏ trong mỗi ô | Có liên kết `next`, đôi còn `prev`, và padding |
| Địa chỉ phần tử khi cập nhật | Có thể đổi khi cấp phát lại/dịch | Nút còn tồn tại thường giữ địa chỉ ổn định |
| Khả năng vector hóa duyệt số | Thường thuận lợi hơn | Thường khó hơn do con trỏ phụ thuộc |
| Thu hồi sau xóa | Có thể giữ nguyên capacity | Có thể trả nút riêng về allocator |

Độ phức tạp trong bảng không thay thế phép đo trên workload thực tế. Ví dụ một thao tác `O(n)` chuyển một vùng nhớ nhỏ liên tiếp có thể rất nhanh; một chuỗi thao tác `O(1)` nhưng phải cấp phát và cache miss nhiều lần có thể đắt hơn.

## 18. Những hiểu nhầm và lỗi phân tích phổ biến

| Nhầm lẫn | Điều cần nhớ |
|---|---|
| “Linked list chèn/xóa luôn `O(1)`.” | Đúng cho phần nối/tháo khi đã có đúng nút/vị trí; tìm nút có thể `O(n)`. |
| “Mảng luôn chậm vì chèn giữa `O(n)`.” | Dịch các ô liên tiếp có thể rất nhanh; cần tính kích thước và tần suất thao tác. |
| “Danh sách liên kết không tốn chi phí cấp phát.” | Nút thường phải được cấp phát, trừ khi đã có node/pool hoặc hook nhúng. |
| “Mảng có `capacity=100` nên đọc `A[99]` được dù `size=10`.” | Vùng trống dự phòng chưa phải phần tử logic; còn quy tắc tạo đối tượng của ngôn ngữ. |
| “`O(1)` là thời gian giống nhau trên mọi phần cứng.” | Big-O bỏ qua chi phí cấp phát, cache miss, kiểu dữ liệu và hệ số. |
| “Linked list không có dịch dữ liệu nên luôn ít tốn bộ nhớ hơn.” | Mỗi nút có con trỏ, padding và có thể metadata allocator. |
| “Vector mở rộng sau mọi lần `push_back`.” | Mảng động dự phòng sức chứa; thêm cuối thường `O(1)` khấu hao. |
| “Các nút liên kết luôn nằm xa nhau.” | Có thể được cấp phát gần nhau; không có bảo đảm về bố trí. |
| “Đã có con trỏ tới nút C thì xóa nó trong singly list luôn `O(1)`.” | Thường cần con trỏ tới nút trước C; hoặc phải dùng kỹ thuật với tiền điều kiện đặc biệt. |
| “Chèn một nút không làm ảnh hưởng bất kỳ ai.” | Có thể ảnh hưởng iterator/vòng đời/truy cập đồng thời; phải kiểm tra hợp đồng của cấu trúc. |
| “Danh sách liên kết có địa chỉ nút ổn định nghĩa là có thể `free` nút tùy lúc.” | Sau khi hủy nút, mọi con trỏ/iterator tới nó trở nên không hợp lệ. |
| “Cùng `O(n)` nên duyệt mảng và list nhanh ngang nhau.” | Cache locality và pointer chasing tạo khác biệt thực tế lớn. |
| “Mảng con trỏ tới đối tượng có cùng locality như mảng giá trị trực tiếp.” | Các ô con trỏ gần nhau nhưng payload có thể phân tán. |
| “Chỉ đo thời gian nối nút là đủ chọn linked list.” | Phải đo cả tìm vị trí, cấp phát, duyệt, hủy và quản lý vòng đời. |

## 19. Bài tập tự kiểm tra

Cho `n` là số phần tử, `s` là kích thước một phần tử, và giả định thao tác trên ô hoặc con trỏ đơn lẻ tốn `O(1)`.

**Bài 1.** Mảng `A` có `n=8` phần tử. Chèn một phần tử vào trước chỉ số `i=3` và giữ thứ tự cần dịch bao nhiêu ô? Xóa tại chỉ số `i=3` cần dịch bao nhiêu ô?

**Bài 2.** Nếu `n=100.000`, chèn vào giữa một mảng các phần tử `16` byte thì lượng dữ liệu phần tử phải dời là bao nhiêu byte? Kết quả có phải luôn là lượng byte truyền qua RAM không?

**Bài 3.** Một danh sách liên kết đơn có `head` nhưng không có `tail`. Thêm phần tử cuối có bảo đảm `O(1)` không? Nếu muốn bảo đảm phần nối cuối `O(1)` thì cần bổ sung điều gì?

**Bài 4.** Có sẵn con trỏ trực tiếp tới một nút trong danh sách liên kết đôi. Vì sao tháo nút có thể là `O(1)`? Nếu chỉ có khóa `id` và chưa có chỉ mục, tổng chi phí có thể là bao nhiêu?

**Bài 5.** Giả sử `sizeof(int)=4` byte, `sizeof(pointer)=8` byte. Nêu kích thước tối thiểu theo tổng trường của một nút đơn chứa `int` và một con trỏ; một nút đôi chứa `int` và hai con trỏ. Vì sao kích thước thực tế của `struct` có thể lớn hơn?

**Bài 6.** Mảng động mở rộng sức chứa theo cấp số nhân. Vì sao một lần `append` có thể `O(n)` nhưng tổng `n` lần thêm cuối vẫn `O(n)`, tức `O(1)` khấu hao mỗi lần?

**Bài 7.** Một ứng dụng thường xuyên duyệt một triệu số nguyên liên tiếp để tính tổng và chỉ thỉnh thoảng xóa cuối. Hãy chọn cấu trúc thường hợp lý hơn và giải thích dựa trên cache, cấp phát và chi phí thao tác.

**Bài 8.** Một bộ điều phối đã có con trỏ tới đối tượng tác vụ cần chuyển từ danh sách `ready` sang `waiting`. Vì sao linked list hoặc intrusive list có thể phù hợp? Điều kiện vòng đời nào cần duy trì?

**Bài 9.** Nếu dùng `std::vector<T>` và giữ một iterator tới phần tử thứ ba, điều gì có thể xảy ra với iterator đó sau thao tác chèn làm mảng cấp phát lại? So sánh với iterator tới một nút không bị xóa trong `std::list<T>` khi chèn nút khác.

**Bài 10.** Tại sao mảng chứa con trỏ `T*` không nhất thiết có locality tốt như mảng chứa trực tiếp `T`? Điểm đánh đổi tích cực của mảng con trỏ là gì?

**Bài 11.** Một nhóm dùng benchmark để kết luận `list.insert` luôn thắng `vector.insert`, nhưng họ truyền sẵn iterator vào list trong khi vector phải tìm vị trí theo khóa. Phép so sánh có công bằng không? Cần điều chỉnh thiết kế đo như thế nào?

**Bài 12.** Hãy nêu một giải pháp dung hòa giữa mảng và danh sách liên kết nếu yêu cầu vừa cần duyệt gần liên tiếp, vừa phải chèn/xóa theo nhóm phần tử.

**Bài 13.** Với singly linked list, tại sao chỉ có con trỏ tới nút cần xóa chưa đủ để tháo nó theo cách thông thường trong `O(1)`? Vì sao “chép dữ liệu nút sau vào nút hiện tại rồi xóa nút sau” không giải quyết được mọi trường hợp?

**Bài 14.** Nếu các node được phân phối từ một pool liên tiếp, có chắc linked list sẽ có tốc độ duyệt gần như mảng không? Những yếu tố nào vẫn có thể cản trở?

### Đáp án và giải thích

1. Chèn: `8-3=5` ô. Xóa: `8-3-1=4` ô.
2. Khoảng `50.000×16=800.000` byte dữ liệu phần tử cần dời. Không, lưu lượng RAM thực tế còn phụ thuộc cách đọc/ghi, các tầng cache, cache line và tối ưu hóa.
3. Không; nếu không biết cuối thì phải duyệt `O(n)` nút. Có thể lưu `tail` (và cập nhật đúng khi danh sách rỗng, chèn, xóa) để phần nối cuối là `O(1)`.
4. Có sẵn `prev` và `next`, chỉ cần sửa một số liên kết cố định, `O(1)`. Nếu phải tìm `id` bằng duyệt tuyến tính thì tổng `O(n)` xấu nhất.
5. Nút đơn có tối thiểu `4+8=12` byte tổng trường; nút đôi `4+8+8=20` byte. Padding và căn chỉnh có thể làm `sizeof(struct)` lớn hơn, chưa kể metadata của allocator.
6. Những lần mở rộng dời khoảng `1+2+4+\cdots` phần tử; tổng bị chặn bởi một bội số của `n` khi sức chứa tăng theo tỷ lệ cố định, nên cộng cả các lần thêm cuối vẫn `O(n)`.
7. Thường chọn mảng động chứa giá trị trực tiếp: duyệt tuần tự có locality tốt, cấp phát theo khối, xóa cuối không cần dịch phần tử. Kết luận còn phụ thuộc tải thực tế và kiểu dữ liệu.
8. Khi biết hook/vị trí, tháo và nối chỉ sửa vài con trỏ, không dời phần đuôi như mảng. Đối tượng phải còn sống và có địa chỉ ổn định; intrusive list còn cần tháo các hook trước khi hủy.
9. `std::vector` có thể làm mất hiệu lực mọi iterator/con trỏ/tham chiếu tới vùng lưu cũ sau cấp phát lại. `std::list` thông thường giữ iterator tới các phần tử khác vẫn hợp lệ khi chèn nút mới; iterator của nút bị xóa thì không hợp lệ.
10. Các con trỏ nằm liên tiếp nhưng `T` được trỏ tới có thể rải rác, cần thêm truy cập gián tiếp. Lợi ích: khi thay đổi thứ tự mảng, chỉ dời các con trỏ nhỏ; địa chỉ các đối tượng `T` có thể được giữ ổn định.
11. Không công bằng nếu ứng dụng thực phải tìm vị trí cho cả hai. Cần đo cùng nghiệp vụ, tính cả bước tìm vị trí, phân biệt benchmark riêng phần nối với benchmark toàn bộ thao tác, và ghi rõ cách chuẩn bị iterator.
12. Có thể dùng **unrolled linked list/block list**: mỗi nút chứa một khối phần tử liên tiếp, giảm số lần lần theo con trỏ và vẫn cho phép nối/tách khối.
13. Singly list thường phải sửa `prev.next` để bỏ nút, nhưng không có con trỏ ngược. Kỹ thuật sao chép nút sau không dùng được cho nút cuối, có thể thay đổi định danh/logical value của nút hiện tại và không phù hợp khi đối tượng có quyền sở hữu hoặc con trỏ bên ngoài.
14. Không chắc. Thứ tự liên kết có thể khác thứ tự bố trí trong pool; vẫn có pointer chasing, phụ thuộc tải, phân nhánh, metadata của nút và cache miss. Cần đo trên workload thật.

## 20. Ghi nhớ

**Mảng động** trả giá cho **dịch các ô liên tiếp** khi chèn/xóa ở đầu hoặc giữa, nhưng hỗ trợ truy cập theo chỉ số `O(1)`, duyệt tuần tự có tính cục bộ tốt và thêm cuối thường `O(1)` khấu hao. **Danh sách liên kết** có thể **nối/tháo nút đã biết bằng `O(1)` phép cập nhật liên kết**, nhưng có thể phải trả chi phí cấp phát/thu hồi từng nút, thêm con trỏ và padding, cùng thời gian tìm vị trí `O(n)`. Duyệt danh sách còn có thể gặp pointer chasing và cache miss, dù độ phức tạp vẫn `O(n)` như duyệt mảng. Đánh giá đúng đòi hỏi phân biệt **chi phí tìm vị trí, cấp phát, dịch dữ liệu, truy cập cache và vòng đời con trỏ**. Không chọn cấu trúc chỉ từ một hàng trong bảng Big-O; hãy chọn theo thao tác nổi trội, kích thước phần tử, đặc tính bộ nhớ, yêu cầu giữ con trỏ/iterator và kết quả đo thực tế.
