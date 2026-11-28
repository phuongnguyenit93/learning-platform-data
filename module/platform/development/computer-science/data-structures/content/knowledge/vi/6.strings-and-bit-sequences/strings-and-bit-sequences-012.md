# So sánh chuỗi, mảng ký tự, mảng byte và dãy bit theo nhu cầu

Một chương trình lưu tên người dùng, nhận gói tin, chỉnh sửa nội dung văn bản và đánh dấu các đỉnh đã thăm của đồ thị. Cả bốn loại dữ liệu đều có thể được đặt trong những vùng nhớ liên tiếp, nhưng **không nên dùng cùng một kiểu biểu diễn cho tất cả**:

- Tên người dùng là **văn bản** cần tôn trọng Unicode.
- Gói tin là **dãy byte** có thể chứa mọi giá trị từ `0x00` đến `0xFF`.
- Bộ soạn thảo có thể cần **vùng ký tự khả biến** hoặc cấu trúc văn bản chuyên dụng.
- Tập đỉnh đã thăm chỉ chứa các cờ **đúng/sai** và có thể đóng gói vào **dãy bit**.

Trong chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài học này tổng hợp cách chọn cấu trúc dữ liệu theo **ngữ nghĩa, bất biến, thao tác chủ đạo và chi phí thời gian/bộ nhớ**. Các nguyên tắc cũng áp dụng khi dùng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap hoặc đồ thị: mô hình đúng dữ liệu trước, rồi mới tối ưu biểu diễn.

## 1. Bắt đầu bằng câu hỏi: một phần tử logic là gì?

Bốn biểu diễn khác nhau chủ yếu ở **đơn vị dữ liệu mà chương trình muốn thao tác**.

| Biểu diễn | Một phần tử logic thường mang ý nghĩa | Ví dụ | Điều cần định nghĩa |
|---|---|---|---|
| **Chuỗi văn bản (string)** | Ký hiệu/ngữ nghĩa văn bản; cách lập chỉ số tùy ngôn ngữ | `"Xin chào 🙂"` | Unicode, phép nối, so sánh, bất biến/khả biến |
| **Mảng ký tự (character array)** | Phần tử kiểu ký tự của ngôn ngữ; có thể là byte hoặc code unit | `char buf[16]`, Java `char[]` | Kiểu phần tử, độ dài, terminator, quy tắc mã hóa |
| **Mảng byte (byte array)** | Giá trị nguyên từ 0 đến 255 | `[0x41, 0x00, 0xFF]` | Số byte, định dạng nhị phân, endian, quyền sở hữu |
| **Dãy bit (bit sequence/bitset)** | Một cờ 0 hoặc 1 | `[1,0,0,1,0]` | Đánh số bit, độ dài logic, padding, word size |

**Chú ý:** đây là những *mô hình dữ liệu*, không phải bốn tên kiểu chuẩn có ngữ nghĩa giống nhau trong mọi ngôn ngữ.

- `str` trong Python là chuỗi văn bản **bất biến**; `std::string` trong C++ là đối tượng chuỗi **có thể sửa** và lưu dãy `char`.
- `char` của C/C++ là **một đơn vị ký tự của ngôn ngữ có kích thước một byte C**, không đương nhiên bằng một Unicode code point. `char` của Java là **một UTF-16 code unit 16 bit**.
- `bytes` của Python bất biến, còn `bytearray` khả biến; cùng là dữ liệu byte nhưng khác hợp đồng sửa.
- `bool[]`, `vector<bool>`, `std::bitset`, `BitSet` và bitmask nguyên là các lựa chọn khác nhau về cách lưu nhiều giá trị đúng/sai.

Do đó, câu hỏi chính không phải “cái nào nhanh hơn?” mà là **“dữ liệu thực sự có ý nghĩa gì và API phải bảo đảm điều gì?”**

## 2. Ba tầng phải phân biệt: nội dung, mã hóa và lưu trữ

Đối với văn bản, một đối tượng chuỗi không nhất thiết lưu trực tiếp “ký tự nhìn thấy” như một phần tử bộ nhớ.

```text
Văn bản người dùng:       "Aé🙂"

Unicode code point:       U+0041, U+00E9, U+1F642
                                   |
                                   v
Mã hóa UTF-8:             41 | C3 A9 | F0 9F 99 82
Số byte UTF-8:            1  + 2     + 4 = 7

Mã hóa UTF-16:            0041 | 00E9 | D83D DE42
Số code unit UTF-16:        1  +  1   +   2 = 4
```

Với ví dụ này:

- **Độ dài byte UTF-8:** 7.
- **Số UTF-16 code unit:** 4.
- **Số Unicode code point:** 3.
- **Số grapheme cluster:** thường là 3 (mỗi biểu tượng hiển thị là một cụm).

Nhưng `"e\u0301"` (chữ `e` theo sau bởi dấu sắc kết hợp) gồm **2 code point** và thường là **1 grapheme cluster**. Không thể lấy số ký tự người dùng cảm nhận bằng cách đếm byte hoặc tùy tiện đếm code point.

### Vì sao vấn đề này ảnh hưởng tới cấu trúc dữ liệu?

Nếu ứng dụng cần giới hạn **1.000 byte gói tin**, phải đo **độ dài sau mã hóa**. Nếu giao diện cần xóa **một ký tự người dùng nhìn thấy**, phải thao tác theo ranh giới **grapheme cluster**. Nếu đang đọc hoặc sửa **một byte của file**, không được ngầm coi byte đó là một ký tự Unicode.

Một byte trong UTF-8 có thể chỉ là một phần của code point. Cắt tại một byte bất kỳ có thể tạo chuỗi UTF-8 không hợp lệ. Một phần tử Java `char` cũng có thể chỉ là một nửa surrogate pair.

**Quy tắc:** phân biệt rõ *chuỗi văn bản có ngữ nghĩa Unicode* với *dãy đơn vị mã hóa* và *dãy byte trên đường truyền*.

## 3. Chuỗi (string): ưu tiên biểu diễn văn bản có hợp đồng rõ ràng

Một **string** thường cung cấp các thao tác:

- Lấy độ dài theo đơn vị ngôn ngữ định nghĩa.
- So sánh, tìm kiếm chuỗi con, nối văn bản.
- Cắt chuỗi hoặc tạo view trên đoạn con.
- Mã hóa ra byte để truyền hoặc giải mã byte thành văn bản.

Tính **bất biến (immutable)** phụ thuộc ngôn ngữ và kiểu dữ liệu, không phải bản chất bắt buộc của mọi string.

### 3.1. Chuỗi bất biến

Với Python:

```python
a = "dữ liệu"
b = a
a = a + " lớn"

print(a)  # dữ liệu lớn
print(b)  # dữ liệu
```

`a` được gán tới kết quả mới; chuỗi `"dữ liệu"` mà `b` tham chiếu không bị sửa. Bất biến giúp:

- Chia sẻ giá trị an toàn về mặt **nội dung** giữa các thành phần.
- Dùng nội dung làm **khóa bảng băm** trong các kiểu cho phép hash theo giá trị.
- Lưu snapshot hoặc trả kết quả mà nơi khác không thể sửa trực tiếp.

Tuy nhiên, nếu ghép nhiều đoạn liên tục và mỗi phép nối phải sao chép toàn tiền tố thì tổng công việc có thể tăng mạnh. Nên dùng builder hoặc gom mảnh rồi ghép một lần cho các tác vụ tạo văn bản dài.

### 3.2. Chuỗi khả biến

Trong C++:

```cpp
#include <string>

int main() {
    std::string s = "data";
    s[0] = 'D';          // sửa một char
    s += " structures";  // nối thêm nội dung
}
```

`std::string` lưu một dãy `char` có thể thay đổi. Khi các byte chứa UTF-8, `s.size()` là số phần tử `char` của chuỗi (thường tương ứng số byte UTF-8), **không** phải số grapheme cluster. Sửa một byte bất kỳ có thể làm hỏng biểu diễn UTF-8.

### 3.3. Thao tác ghép liên tục

Giả sử kết quả gồm `k` đoạn, mỗi đoạn dài `m` đơn vị lưu trữ. Nếu mỗi lần nối chuỗi bất biến phải sao chép toàn bộ tiền tố, công việc ghi các kết quả trung gian là:

\[
m + 2m + \cdots + km
= \frac{m\,k(k+1)}{2}
= \Theta(mk^2).
\]

Khi `m` là hằng số và tổng chiều dài `N=mk`, đây là `Θ(N²)`. Một **string builder** hoặc việc thu gom mảnh rồi `join` có thể giảm tổng lượng sao chép về gần `O(N)`, tùy chiến lược cấp phát và runtime.

Không nên khẳng định phép `+=` trong mọi ngôn ngữ **luôn** có độ phức tạp bậc hai: một số runtime có tối ưu ghép chuỗi hoặc biểu diễn chia sẻ. Độ phức tạp vừa nêu áp dụng cho **mô hình nối tạo bản mới và sao chép toàn tiền tố**.

## 4. Mảng ký tự: hữu ích khi phải điều khiển vùng lưu trữ và tương tác API thấp

**Mảng ký tự** cho phép chọn kích thước vùng nhớ và sửa phần tử nếu kiểu mảng/đối tượng khả biến. Tuy nhiên, ý nghĩa “ký tự” thay đổi giữa các ngôn ngữ.

### 4.1. C: `char[]` là dãy các phần tử byte C

Ví dụ:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    char text[8] = "abc";  // a b c \0, phần còn lại được điền 0
    text[0] = 'A';

    printf("%s\n", text);            // Abc
    printf("%zu\n", strlen(text));   // 3
    printf("%zu\n", sizeof text);    // 8
    return 0;
}
```

Các số trong ví dụ thể hiện **ba khái niệm**:

- `strlen(text)` đếm số `char` trước byte NUL đầu tiên, trong C string hợp lệ.
- `sizeof text` là kích thước **mảng thật tại phạm vi này**, bằng 8 byte C.
- `8` là sức chứa vật lý; không đồng nghĩa độ dài văn bản 3.

Nếu truyền `text` cho hàm nhận `char *`, phép `sizeof` trên tham số con trỏ **không** cho biết kích thước mảng gốc. Cần truyền thêm độ dài hoặc dung lượng.

Không được gọi `strlen` trên mảng `char` không có NUL kết thúc nằm trong vùng hợp lệ: hàm có thể đọc vượt bộ nhớ, dẫn đến hành vi không xác định.

### 4.2. Java: `char[]` là dãy code unit UTF-16

```java
String text = "A🙂";
char[] units = text.toCharArray();

System.out.println(units.length);              // 3 code unit
System.out.println(text.codePointCount(0, text.length())); // 2 code point

units[0] = 'B';  // mảng char thay đổi được
System.out.println(text); // A🙂: String ban đầu bất biến
```

Vì emoji có thể cần **hai UTF-16 code unit**, không được tự đồng nhất `char` của Java với “một ký tự nhìn thấy”. Cắt hoặc sửa một phần của surrogate pair có thể tạo dãy code unit không hợp lệ như văn bản Unicode hoàn chỉnh.

### 4.3. Khi nào mảng ký tự phù hợp?

Mảng ký tự có thể hữu ích khi:

- Gọi API C yêu cầu một vùng `char *`/`const char *`.
- Dùng **bộ đệm kích thước cố định** do một giao thức hoặc thư viện quy định.
- Thao tác trên code unit theo một hợp đồng rõ ràng, ví dụ một buffer UTF-16.
- Cần sửa phần tử ở vị trí đã biết, kiểm soát dung lượng và tránh cấp phát liên tục.

Nhưng mảng ký tự thô thường **không tự biết độ dài logic**, không tự đảm bảo ranh giới Unicode, và có thể yêu cầu mã lập trình viên duy trì NUL/length/capacity chính xác.

Nếu cần sửa rất nhiều vị trí giữa một văn bản dài, một mảng liên tiếp cũng có thể phải dịch chuyển `O(n)` phần tử khi chèn hoặc xóa. Có thể cân nhắc **gap buffer, rope hoặc piece table** cho trình soạn thảo văn bản lớn.

## 5. Mảng byte: dữ liệu nhị phân trước, văn bản sau

Một **mảng byte** biểu diễn các giá trị từ 0 đến 255. Nó không tự quyết định nội dung là văn bản, ảnh, âm thanh, gói tin, số nguyên, hay cấu trúc tuần tự hóa.

Ví dụ:

```text
Byte:         41 00 FF 42
Theo nhị phân: 65, 0, 255, 66
```

Dãy này hoàn toàn hợp lệ để lưu dữ liệu nhị phân. Tuy nhiên, `0xFF` đứng độc lập **không phải byte hợp lệ của một chuỗi UTF-8 hoàn chỉnh** và `0x00` có thể bị hiểu sai là dấu kết thúc nếu chuyển sang API chuỗi C.

### 5.1. Python: `bytes` so với `bytearray`

```python
immutable = b"A\x00B"
mutable = bytearray(immutable)

print(len(immutable))   # 3
print(immutable[1])     # 0, vẫn là dữ liệu hợp lệ

mutable[0] = 0x5A
mutable.append(0xFF)

print(mutable.hex())    # 5a0042ff
print(immutable)        # b'A\x00B': không đổi
```

- `bytes` có **nội dung bất biến**.
- `bytearray` cho phép sửa byte, thêm hoặc xóa byte.
- `len` trả về số byte.
- Không phải mọi dãy byte đều giải mã được thành Unicode theo mã hóa đã chọn.

### 5.2. Cần bước chuyển đổi rõ ràng tại ranh giới văn bản

```python
text = "Tiếng Việt 🙂"
encoded = text.encode("utf-8")

print(type(text).__name__)    # str
print(type(encoded).__name__) # bytes
print(len(text))              # số code point trong Python
print(len(encoded))           # số byte UTF-8

restored = encoded.decode("utf-8")
assert restored == text
```

Chỉ khi biết **encoding** và dữ liệu hợp lệ mới có thể giải mã chắc chắn. Với dữ liệu đầu vào không đáng tin, phải quy định chính sách lỗi giải mã: từ chối dữ liệu sai, thay ký tự lỗi hoặc xử lý theo định dạng đã công bố; không được tự giả định byte luôn là UTF-8.

### 5.3. Mảng byte và cấu trúc số nguyên

Nếu dãy byte chứa số nguyên nhiều byte, cần quy định **endianness**:

```python
raw = bytes([0x01, 0x02])
print(int.from_bytes(raw, "big"))     # 258
print(int.from_bytes(raw, "little"))  # 513
```

Cùng hai byte có thể mang giá trị số khác nhau tùy thứ tự byte được quy định. Đây là vấn đề của **định dạng dữ liệu**, không phải vấn đề của chuỗi văn bản hay bitset.

### 5.4. Chia sẻ vùng nhớ và lifetime

Một mảng byte có thể được **sao chép** hoặc được quan sát qua **view**. Ví dụ `memoryview(bytearray_obj)` trong Python chia sẻ dữ liệu với bộ đệm gốc; sửa byte nguồn có thể nhìn thấy qua view. Trong khi đó, `bytes(source_slice)` cho kết quả bất biến độc lập về mặt nội dung.

View có thể giảm sao chép nhưng đòi hỏi quản lý vòng đời và khả năng thay đổi kích thước bộ đệm. Một view nhỏ cũng có thể giữ vùng nguồn lớn sống lâu hơn mong muốn, tùy cơ chế sở hữu.

## 6. Dãy bit: lưu trạng thái Boolean và phép toán tập hợp

**Dãy bit** dùng một bit cho mỗi giá trị logic. Nếu có `n` cờ độc lập, số byte dữ liệu tối thiểu khi đóng gói sát theo byte là:

\[
M_{\mathrm{bits}}=\left\lceil\frac{n}{8}\right\rceil.
\]

Nếu dùng mảng các từ 64 bit:

\[
M_{\mathrm{words}}=
8\left\lceil\frac{n}{64}\right\rceil
\quad\text{byte dữ liệu}.
\]

Ví dụ một triệu trạng thái:

- Một byte cho mỗi Boolean: **1.000.000 byte dữ liệu**.
- Bitset đóng gói: **125.000 byte dữ liệu**.
- Nếu các đối tượng Boolean có overhead riêng, như một số cấu trúc cấp cao, chênh lệch thực tế có thể còn lớn hơn.

Đây là so sánh phần **dữ liệu**, chưa tính metadata, căn chỉnh bộ nhớ và bộ cấp phát.

### 6.1. Truy cập bit bằng mask

Với từ rộng `w`, bit thứ `i` được lưu tại:

\[
j=\left\lfloor\frac{i}{w}\right\rfloor,
\qquad
r=i\bmod w.
\]

Mặt nạ cho bit cần truy cập là `1 << r`, tạo bằng **kiểu số nguyên không dấu đủ rộng** và chỉ với `0 ≤ r < w`.

| Thao tác | Phép toán trên từ chứa bit |
|---|---|
| Kiểm tra `test(i)` | `(word & mask) != 0` |
| Đặt `set(i)` | `word \|= mask` |
| Xóa `clear(i)` | `word &= ~mask` |
| Đảo `flip(i)` | `word ^= mask` |

Một thao tác trên bit đã cấp phát thường `O(1)` trong mô hình từ máy cố định. Bitset vẫn cần lưu `bitLength`; bit đệm trong từ cuối không được coi là các phần tử logic.

### 6.2. Phép toán trên cả tập trạng thái

Nếu A và B là hai bitset trên **cùng miền chỉ số**:

- **Hợp:** `A | B`.
- **Giao:** `A & B`.
- **Hiệu:** `A & ~B`.
- **Hiệu đối xứng:** `A ^ B`.
- **Đếm phần tử:** tổng `popcount` trên từng từ.

Với `q=ceil(n/w)` từ, các phép toán toàn tập thường mất **`O(q)`** thời gian. Chúng có thể xử lý nhiều cờ trong một phép toán từ máy thay vì lặp qua từng Boolean.

### 6.3. Tại sao không dùng dãy bit cho byte tùy ý?

Một byte chứa **8 bit có cấu trúc**, nhưng nếu bài toán cần đọc/ghi **nguyên byte** theo giao thức, thao tác trên byte array rõ ràng hơn. Bitset chỉ thích hợp khi phần tử logic là cờ hoặc tập bit, không tự cung cấp parser, codec hoặc quy tắc byte order cho file ảnh và gói tin.

Nếu miền ID rất lớn nhưng chỉ có vài bit bật, một bitset **dày đặc** vẫn cấp phát theo toàn miền. Khi ấy hash set, danh sách ID có thứ tự, sparse word bitmap hoặc bitmap nén có thể tiết kiệm bộ nhớ hơn.

## 7. Cùng một dữ liệu có thể nhìn ở nhiều tầng — nhưng không được nhầm tầng

Hãy xét byte `0x41`:

```text
Giá trị byte:       0x41 = 65
Biểu diễn nhị phân: 01000001

Nếu diễn giải ASCII/UTF-8:
  0x41 → "A"

Nếu diễn giải 8 cờ theo quy ước bit 0 là LSB:
  bit 0 = 1
  bit 6 = 1
  các bit còn lại = 0
```

Bộ nhớ vật lý có thể giống hệt, nhưng **ngữ nghĩa và bất biến khác nhau**.

Một byte array có thể chứa dữ liệu text đã mã hóa; sau khi `decode("utf-8")` ta được một đối tượng chuỗi văn bản. Cũng có thể xem byte array như các bit để tính CRC, nén dữ liệu hay xử lý quyền truy cập. Tuy nhiên, chuyển cách **diễn giải** không mặc nhiên làm dãy byte biến thành một cấu trúc có đầy đủ hợp đồng của string hoặc bitset.

### Phân biệt ba giới hạn thường gặp

1. **Giới hạn byte:** ví dụ bản tin mạng tối đa 4.096 byte sau mã hóa.
2. **Giới hạn code point hoặc code unit:** phụ thuộc API của ngôn ngữ và thuật toán Unicode.
3. **Giới hạn ký tự hiển thị:** cần phân đoạn grapheme.

Một giao diện chỉ cho phép “20 ký tự” cần xác định chính sách theo grapheme hoặc một định nghĩa rõ ràng khác. Không thể dùng `len(utf8_bytes)` rồi gọi đó là số ký tự hiển thị.

## 8. So sánh thời gian và bộ nhớ trong mô hình thông thường

Đặt:

- `n` là số đơn vị lưu trữ của một chuỗi hoặc mảng đã cấp phát.
- `m` là số đơn vị mới thêm hoặc sao chép.
- `b` là số bit logic của bitset.
- `w` là số bit mỗi từ máy, `q=ceil(b/w)`.
- Với string/char array, giả sử truy cập được tới vị trí **đơn vị lưu trữ đã biết**, không yêu cầu tự tìm ranh giới Unicode.

| Thao tác | Chuỗi văn bản | Mảng ký tự liên tiếp | Mảng byte liên tiếp | Bitset đóng gói |
|---|---|---|---|---|
| Đọc độ dài **đã lưu** | Thường `O(1)` | `O(1)` nếu có metadata; chuỗi C chỉ có NUL phải quét `O(n)` | Thường `O(1)` | `O(1)` khi lưu bitLength |
| Đọc đơn vị lưu trữ thứ `i` | Thường `O(1)` nếu API cung cấp indexing theo code unit/code point; chi tiết phụ thuộc biểu diễn | `O(1)` | `O(1)` | `O(1)` để đọc bit |
| Sửa một đơn vị | Chuỗi bất biến: tạo giá trị mới; chuỗi khả biến: tùy biểu diễn | `O(1)` nếu đã có vị trí hợp lệ | `O(1)` | `O(1)` |
| Duyệt toàn bộ nội dung | `O(n)` theo số đơn vị xử lý | `O(n)` | `O(n)` | `O(q)` từ, hoặc `O(b)` nếu xử lý từng bit |
| Nối/append `m` đơn vị | Phụ thuộc chuỗi bất biến, builder, tối ưu runtime | Trong buffer có chỗ: `O(m)`; mở rộng có thể `O(n+m)` | Tương tự mảng động | Mở rộng miền có thể cần cấp phát, khởi tạo thêm từ |
| Chèn giữa mảng liên tiếp | Thường tạo/copy hoặc dời đuôi `O(n+m)` | `O(n+m)` trong trường hợp xấu | `O(n+m)` trong trường hợp xấu | Dịch bit toàn dãy có thể `O(q)` hoặc nhiều hơn tùy thuật toán |
| So sánh nội dung bằng nhau | Có thể cần `O(n)` | `O(n)` | `O(n)` | `O(q)` theo từ |
| AND/OR hai tập trạng thái | Không phải phép văn bản thông thường | Không phải thao tác ký tự mặc định | Có thể làm theo byte nhưng cần quy ước bitset | `O(q)` theo từ |

**Các giới hạn của bảng:**

- Chi phí lấy **code point hoặc grapheme thứ `i`** trong UTF-8/UTF-16 có thể yêu cầu giải mã/quét nếu không có chỉ mục phụ, dù truy cập **byte/code unit** tại offset đã biết là `O(1)`.
- `StringBuilder` tăng dung lượng theo hệ số có thể cho `append` một đơn vị **`O(1)` khấu hao**, nhưng một lần cấp phát lại riêng lẻ vẫn có thể `O(n)`.
- Nếu string được biểu diễn bằng rope, chunk hay slice, chi phí truy cập/copy có thể khác mảng liên tiếp.
- `O(q)` của bitset không có nghĩa `O(1)` cho cả tập khi `b` tăng.

Bảng giúp **đặt câu hỏi đúng** trước khi xem tài liệu của thư viện và benchmark trên dữ liệu thật.

## 9. Chi phí không gian: tính cả metadata, encoding và phần dự phòng

Một lỗi thiết kế thường gặp là so sánh “một ký tự”, “một byte” và “một bit” như ba đơn vị tương đương. Chúng đo **những thứ khác nhau**.

Ví dụ:

- Chuỗi văn bản `"🙂"` có thể chiếm 4 byte UTF-8 hoặc 2 UTF-16 code unit, chưa tính overhead đối tượng.
- Mảng Java `char[100]` cần dữ liệu phần tử tương ứng 100 code unit 16 bit, chưa tính header/alignment.
- Mảng byte 100 phần tử cần 100 byte dữ liệu logic, dù đối tượng và allocator có overhead.
- Bitset chứa 100 Boolean cần ít nhất `ceil(100/8)=13` byte nếu đóng gói sát theo byte, hoặc 16 byte dữ liệu khi lưu bằng hai từ 64 bit.

### Ví dụ 1.000.000 cờ

| Cách lưu trạng thái | Dữ liệu lý tưởng |
|---|---:|
| Một byte mỗi cờ | 1.000.000 B |
| Mỗi cờ là một `char` UTF-16 16 bit | 2.000.000 B (nhưng sai ngữ nghĩa nếu chỉ cần Boolean) |
| Bitset byte-packed | 125.000 B |
| Bitset `uint64_t[]` | 125.000 B |

Với 1.000.000 cờ, bitset có lợi thế rõ ràng. Nhưng nếu chỉ có 100 cờ bật trong miền một tỷ ID, bitset dày đặc cần khoảng **125 MB** dữ liệu, còn một mảng 100 ID 64 bit có dữ liệu thô chỉ khoảng **800 byte**. Không thể kết luận bitset luôn tiết kiệm hơn mọi cấu trúc.

### Khi nào cần dành trước dung lượng?

Bộ đệm xây dựng chuỗi hoặc mảng động thường duy trì `length` và `capacity`:

\[
0\le \text{length}\le\text{capacity}.
\]

Nếu dùng sentinel NUL như chuỗi C, phải còn **ít nhất một ô cho dấu kết thúc**. Còn bitset dài `b` lưu trong `q` từ có thể có bit vật lý dự phòng từ `b` đến `q w-1`; đó là **padding**, không phải các Boolean hợp lệ.

Đừng truy cập vùng `capacity` dư như thể `length` đã tăng. Với dữ liệu văn bản, cũng đừng coi vùng chứa byte `0` bất kỳ là điểm kết thúc nếu API được thiết kế dựa trên độ dài tường minh.

## 10. Ví dụ Python tổng hợp: bốn bài toán, bốn cách biểu diễn

Mã dưới đây dùng những kiểu chuẩn để thể hiện ranh giới ngữ nghĩa:

```python
# 1. Văn bản Unicode: xử lý như text.
user_name = "Hòa 🙂"
print(len(user_name))  # số Unicode code point trong Python str

# 2. Tích lũy những đơn vị văn bản có thể chỉnh sửa.
# Python không có kiểu mutable Unicode char array nguyên thủy;
# list[str] chỉ là danh sách các chuỗi, phải áp quy tắc mỗi phần tử.
characters = ["H", "o", "à"]
characters[1] = "Ò"
edited = "".join(characters)
print(edited)  # HÒà

# 3. Payload nhị phân: byte 0 là dữ liệu hợp lệ.
packet = bytearray([0x41, 0x00, 0x42])
packet[0] = 0x5A
print(packet.hex())  # 5a0042

# 4. Tập cờ trên miền 16 vị trí: dùng một bitmask nguyên.
visited = 0
visited |= 1 << 2    # bật cờ 2
visited |= 1 << 10   # bật cờ 10
print(bool(visited & (1 << 10)))  # True
visited &= ~(1 << 2)  # tắt cờ 2
print(visited.bit_count())  # 1
```

**Lưu ý:** danh sách Python `["H", "o", "à"]` không phải `char[]` theo nghĩa C hay Java. Mỗi phần tử là một đối tượng `str`, có thể chứa nhiều code point. Muốn xử lý grapheme, phải phân đoạn Unicode đúng quy tắc và đặt bất biến “mỗi mục là một grapheme”, không chỉ “mỗi mục dài một code point”.

Tương tự, số nguyên Python có độ rộng tùy ý, nên nếu dùng một bitmask để giữ **hàng triệu cờ**, các phép toán `&`, `|`, `bit_count()` không có chi phí `O(1)` độc lập độ dài số nguyên.

## 11. Ví dụ C: char buffer, byte buffer và bitmask

C có kiểu `char` cho dãy ký tự byte, `unsigned char` cho byte và các kiểu số nguyên không dấu cho phép toán bit. Ví dụ hoàn chỉnh:

```c
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    // A. Chuỗi C: phải có NUL trong vùng hợp lệ.
    char label[8] = "data";
    label[0] = 'D';
    printf("%s: %zu\n", label, strlen(label)); // Data: 4

    // B. Dãy byte: NUL không làm mất byte phía sau.
    unsigned char packet[3] = {0x41u, 0x00u, 0x42u};
    for (size_t i = 0; i < sizeof packet; ++i) {
        printf("%02X ", (unsigned int)packet[i]);
    }
    putchar('\n'); // 41 00 42

    // C. Dãy 16 cờ: đóng vào uint16_t.
    uint16_t flags = 0;
    flags |= (uint16_t)(UINT16_C(1) << 2);
    flags |= (uint16_t)(UINT16_C(1) << 10);

    bool is_set = (flags & (UINT16_C(1) << 10)) != 0;
    printf("bit 10: %d\n", (int)is_set); // 1

    flags &= (uint16_t)~(UINT16_C(1) << 2);
    return 0;
}
```

Ví dụ cố định bit 2 và bit 10, đều nhỏ hơn độ rộng 16. Trong code tổng quát, phải **kiểm tra index trong miền và nhỏ hơn độ rộng kiểu trước khi dịch**; không được dịch trái 16 vị trí trên một từ chỉ rộng 16 bit.

Mặc dù `label` và `packet` đều là dãy byte vật lý, chúng có hợp đồng **khác nhau**:

- `label` được dùng như **C string**: `strlen` dừng ở NUL đầu.
- `packet` là **payload nhị phân**: tất cả ba byte đều hợp lệ và phải được xử lý theo độ dài `3`.
- `flags` là **tập cờ**: các bit mang ý nghĩa riêng và được sửa bằng mask.

Không nên dùng `strlen` để xác định độ dài `packet`; không nên tự hiểu một byte của `packet` là một ký tự hiển thị; không nên coi `flags` là văn bản.

## 12. Chọn theo nhu cầu thực tế

| Bài toán | Biểu diễn nên cân nhắc trước | Vì sao |
|---|---|---|
| Tên người dùng, câu thông báo, nội dung giao diện | **String Unicode** | Các thao tác có ngữ nghĩa văn bản |
| Tạo báo cáo bằng hàng nghìn đoạn nhỏ | **String builder** hoặc danh sách mảnh + `join` | Tránh sao chép tiền tố lặp lại |
| Giao tiếp API C yêu cầu buffer `char *` | **Mảng ký tự có length/capacity/NUL đúng hợp đồng** | Tương thích API thấp |
| Sửa code unit tại offset đã biết trong buffer | **Mảng ký tự khả biến** | Có thể sửa tại chỗ, nhưng phải bảo vệ encoding |
| Đọc file ảnh, gói tin nhị phân, dữ liệu nén | **Byte array/buffer** | Payload chứa byte tùy ý và độ dài tường minh |
| Nhận/gửi văn bản qua mạng | **String trong logic, byte buffer ở ranh giới I/O** | Encode/decode có kiểm soát |
| Lưu nhiều cờ bật/tắt trên miền ID dày đặc | **Bitset** | Khoảng một bit cho mỗi trạng thái |
| Giao/hợp các tập ID đánh số liên tục | **Bitset theo từ máy** | AND/OR/XOR xử lý nhiều cờ mỗi phép |
| Tập chỉ có ít ID trong miền rất lớn | **Hash set, mảng ID, bitmap nén** | Không cần cấp phát toàn miền |
| Trình soạn thảo lớn, chèn/xóa giữa liên tục | **Gap buffer, rope, piece table** | Tránh dời toàn bộ dãy liên tiếp |
| Xử lý văn bản theo “ký tự người dùng nhìn thấy” | **String + phân đoạn grapheme** | Byte/code point/code unit chưa đủ để điều khiển con trỏ |

Đây là các **điểm xuất phát**, không phải quy tắc tuyệt đối. Quyết định cuối còn phụ thuộc kích thước, độ phân bố dữ liệu, tần suất cập nhật, tính đồng thời, tiêu chuẩn encoding và chi phí thực tế của runtime.

## 13. Bất biến và lỗi dễ gặp theo từng kiểu

### 13.1. Chuỗi

**Bất biến cần bảo vệ:** chuỗi có nội dung Unicode hợp lệ theo hợp đồng API; các offset cắt/nối đúng đơn vị; giá trị đã công bố là bất biến nếu kiểu hứa bất biến.

**Lỗi hay gặp:** dùng số byte thay số ký tự hiển thị; cắt giữa code point UTF-8; cho rằng mỗi Java `char` bằng một code point; nối chuỗi bất biến trong vòng lặp lớn mà không cân nhắc chi phí.

### 13.2. Mảng ký tự

**Bất biến cần bảo vệ:** `0 ≤ length ≤ capacity`, hoặc `length < capacity` nếu cần phần tử kết thúc; buffer được cấp phát đủ và các phần tử đã khởi tạo trước khi đọc.

**Lỗi hay gặp:** thiếu NUL cho `strlen`; dùng `sizeof(pointer)` để suy độ dài mảng; sửa một byte/code unit làm hỏng UTF-8/UTF-16; giữ con trỏ cũ sau khi realloc.

### 13.3. Mảng byte

**Bất biến cần bảo vệ:** độ dài payload được biết và nằm trong vùng cấp phát; encoding/byte order/format được xác định trước khi giải mã.

**Lỗi hay gặp:** coi `0x00` là kết thúc dù dữ liệu nhị phân cho phép nó; giải mã UTF-8 từ dãy byte bất kỳ mà không xử lý lỗi; không kiểm tra chiều dài gói tin nhận từ mạng; chia sẻ view rồi giải phóng/đổi kích thước buffer nguồn trái hợp đồng.

### 13.4. Dãy bit

**Bất biến cần bảo vệ:** chỉ số nằm trong `[0, bitLength)`; mapping ID→bit thống nhất; padding bị loại khỏi các phép đếm và duyệt; các bitset dùng phép tập hợp cùng miền.

**Lỗi hay gặp:** nhầm LSB/MSB hoặc byte order; dịch trái quá độ rộng từ; `NOT` bật bit đệm; đếm `popcount` cả padding; coi sửa hai bit khác nhau cùng một từ là tự động an toàn đồng thời.

### Một lưu ý chung về dữ liệu không đáng tin

Dù dùng biểu diễn nào, **độ dài và chỉ số nhận từ bên ngoài** phải được kiểm tra trước khi cấp phát, cắt, giải mã hoặc đọc vùng nhớ. Đặc biệt, một trường `length` trong giao thức có thể là số lớn giả mạo; cần giới hạn kích thước và tránh tràn khi tính `offset + length`.

## 14. Tránh tối ưu sai tầng

Có một số tình huống dễ chọn nhầm kiểu vì một ưu điểm cục bộ.

### “Bitset ít bộ nhớ hơn, vậy hãy dùng nó để chứa chuỗi”

Chuỗi chứa Unicode code point và các quy tắc mã hóa; bitset chỉ biểu diễn một dãy 0/1. Mọi dữ liệu cuối cùng đều là bit ở tầng vật lý, nhưng muốn dùng bitset để lưu văn bản phải xây **cả lớp codec, ranh giới ký tự, tìm kiếm và cập nhật**. Nó không tiết kiệm thông tin chỉ bằng việc gọi dữ liệu là bitset.

### “Bytearray khả biến, vậy thay một byte là sửa được một ký tự”

Sai với UTF-8 độ rộng biến đổi. Ví dụ `"🙂".encode("utf-8")` cần bốn byte. Sửa một byte ngẫu nhiên có thể làm giá trị UTF-8 không hợp lệ hoặc thành ký tự khác ngoài ý muốn.

### “Mảng char truy cập nhanh, vậy xóa ký tự ở giữa là O(1)”

Trong buffer liên tiếp, xóa một phần tử và giữ phần còn lại liên tục thường phải dịch chuyển các phần tử phía sau, **`O(n)` trong trường hợp xấu**. Truy cập ngẫu nhiên `O(1)` không kéo theo chèn/xóa giữa `O(1)`.

### “Chuỗi có `len()` nhanh, vậy tìm grapheme thứ i cũng nhanh”

Độ dài đã lưu có thể `O(1)`, nhưng phân đoạn Unicode theo grapheme và xác định offset của grapheme thứ `i` có thể cần quét hoặc chỉ mục phụ. Cần phân tích **truy vấn thực sự**, không suy rộng từ một phương thức khác.

### “Có ít cờ đang bật, bitset luôn tiết kiệm bộ nhớ”

Bitset dày đặc dùng bộ nhớ theo toàn miền `n` chứ không theo số bit 1 `k`. Với `k≪n` và `n` cực lớn, sparse set hoặc bitmap nén có thể tốt hơn.

## 15. Kiến trúc kết hợp: dùng các cấu trúc ở đúng ranh giới

Trong một hệ thống thực tế, không nhất thiết chọn một cấu trúc duy nhất từ đầu đến cuối.

Ví dụ dịch vụ xử lý sự kiện:

```text
             [Gói tin mạng]
                   |
            Byte array/buffer
                   |
         giải mã và kiểm tra định dạng
                   |
          [Văn bản / bản ghi]
                   |
                String
                   |
           phân tích và ánh xạ ID
                   |
          +--------+---------+
          |                  |
    Hash map: ID → index   Bitset: trạng thái đã xử lý
          |                  |
          +--------+---------+
                   |
              tạo báo cáo
                   |
          String builder/join
                   |
             encode UTF-8
                   |
            Byte array → I/O
```

Trong thiết kế này:

- **Byte array** phù hợp ở ranh giới truyền thông vì mạng trao đổi byte.
- **String** phù hợp cho các trường văn bản đã giải mã và xác thực.
- **Hash map** ánh xạ ID ngoài sang chỉ số liên tục khi cần.
- **Bitset** lưu những trạng thái Boolean trên miền chỉ số.
- **Builder** ghép nhiều đoạn báo cáo trước khi mã hóa ngược về byte.

Độ phức tạp phải tính **cả chi phí chuyển đổi giữa các tầng**. Một lựa chọn bộ nhớ tốt cho bitset không tự động làm chi phí parse/encode biến mất, và việc mã hóa văn bản thành byte không tự động miễn phí.

## 16. Quy trình ra quyết định trước khi triển khai

Có thể lần lượt trả lời sáu câu hỏi:

1. **Miền giá trị:** dữ liệu là văn bản, code unit, byte tùy ý, hay Boolean?
2. **Đơn vị truy cập:** byte, code point, grapheme, ký tự theo API hay vị trí bit?
3. **Thao tác chủ đạo:** đọc, so sánh, nối, chèn/xóa giữa, giải mã, kiểm tra cờ hay giao/hợp tập?
4. **Vòng đời và khả biến:** cần snapshot bất biến, vùng nhớ có thể sửa, view, hay chia sẻ giữa nhiều luồng?
5. **Kích thước/phân bố:** tổng độ dài, dung lượng tối đa, mật độ bit 1, độ lớn ID lớn nhất?
6. **Ranh giới tương tác:** API C, JSON, UTF-8, file nhị phân, giao thức mạng hoặc bộ nhớ dùng chung?

Sau đó chọn một biểu diễn có **bất biến rõ ràng**, ước lượng thời gian/bộ nhớ theo thao tác và kiểm chứng bằng dữ liệu đo nếu hiệu năng quan trọng.

## 17. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một ứng dụng nhận `b"A\x00B"` qua mạng. Có thể dùng `strlen` trên vùng ba byte này để xác định độ dài bản tin không?

**Đáp án:** Không. `strlen` dừng ở NUL đầu tiên nên chỉ thấy 1 byte nếu vùng được kết thúc hợp lệ, còn payload có 3 byte. Cần dùng độ dài tường minh do giao thức xác định và bảo đảm vùng nhớ hợp lệ.

**Câu 2.** Vì sao `len("Aé🙂")` trong Python khác độ dài sau `encode("utf-8")`?

**Đáp án:** Python `str` đếm code point ở `len`, ở đây là 3. UTF-8 mã hóa tương ứng 1 + 2 + 4 = **7 byte**, nên `len("Aé🙂".encode("utf-8"))` bằng 7.

**Câu 3.** Một Java `char[]` có phải “mỗi phần tử là một Unicode code point” không?

**Đáp án:** Không. Mỗi `char` là một UTF-16 code unit. Một code point ngoài BMP thường cần cặp surrogate gồm hai `char`.

**Câu 4.** Có 1.000.000 cờ Boolean theo miền ID liên tục. Đóng gói theo byte cần bao nhiêu byte dữ liệu?

**Đáp án:** `ceil(1.000.000 / 8) = 125.000` byte, chưa tính metadata/allocator.

**Câu 5.** Hai bitset dài `n`, mỗi từ chứa 64 bit. Chi phí AND toàn tập là bao nhiêu phép toán từ?

**Đáp án:** `ceil(n/64)` phép AND trên từ; thời gian `O(ceil(n/64))` chưa tính cấp phát và ghi kết quả.

**Câu 6.** Một trình soạn thảo thường xuyên chèn/xóa giữa văn bản rất lớn. Vì sao mảng ký tự liên tiếp có thể kém phù hợp?

**Đáp án:** Chèn/xóa giữa thường phải dời phần đuôi, mất `O(n)` trong trường hợp xấu. Gap buffer, rope hoặc piece table có thể hỗ trợ mẫu thao tác này tốt hơn.

**Câu 7.** Một file lưu ảnh có byte `0xFF` ở đầu. Có nên cố giải mã cả file thành chuỗi UTF-8 để xử lý không?

**Đáp án:** Không, nếu file có định dạng nhị phân. Phải đọc nó như byte array/buffer, parse theo định dạng ảnh; việc giải mã UTF-8 chỉ phù hợp cho các trường dữ liệu được quy định là văn bản.

**Câu 8.** Một miền ID có một tỷ vị trí nhưng chỉ 100 vị trí được đánh dấu. Có nên mặc định dùng bitset dày đặc?

**Đáp án:** Không. Bitset dày đặc cần khoảng 125 MB dữ liệu; hash set, mảng ID hoặc bitmap nén có thể phù hợp hơn cho tập thưa.

**Câu 9.** Vì sao `std::string::size()` của C++ không nhất thiết là số ký tự hiển thị khi chứa UTF-8?

**Đáp án:** `size()` đếm phần tử `char`, thường là số byte dữ liệu UTF-8. Một grapheme có thể gồm nhiều byte và nhiều code point.

**Câu 10.** Một dịch vụ nhận byte UTF-8 qua mạng, xử lý tên người dùng rồi xuất báo cáo. Nên dùng cấu trúc nào ở mỗi giai đoạn?

**Đáp án:** Byte buffer để nhận dữ liệu; giải mã/kiểm tra UTF-8 thành string cho các trường văn bản; dùng builder hoặc `join` để tổng hợp báo cáo; mã hóa kết quả thành byte khi ghi ra mạng/tệp.

**Câu 11.** Nếu hai luồng sửa hai bit khác nhau nhưng cùng nằm trong một từ 64 bit, có thể dùng phép OR thông thường không đồng bộ mà luôn an toàn không?

**Đáp án:** Không. Hai thao tác đọc-sửa-ghi cùng từ có thể mất cập nhật; trong C/C++ còn có nguy cơ data race. Cần atomic hoặc cơ chế đồng bộ thích hợp.

## Ghi nhớ

- **String** ưu tiên ngữ nghĩa văn bản, **mảng ký tự** kiểm soát các phần tử kiểu ký tự/code unit của ngôn ngữ, **mảng byte** giữ dữ liệu nhị phân tùy ý, còn **bitset** đóng gói nhiều trạng thái Boolean.
- Đừng nhầm **byte, code unit, Unicode code point và grapheme cluster**. Chọn đúng đơn vị chỉ số và kiểm tra encoding khi chuyển đổi giữa văn bản với byte.
- **Bất biến và vòng đời** quan trọng không kém Big-O: chuỗi có thể bất biến hoặc khả biến; char buffer có thể cần NUL; byte buffer phải có length hợp lệ; bitset phải giữ miền và padding đúng.
- **Mảng liên tiếp** thường truy cập phần tử tại offset hợp lệ `O(1)` nhưng chèn/xóa giữa `O(n)`; **builder** giúp tích lũy nhiều đoạn; **bitset** xử lý tập cờ theo từ máy với thời gian `O(ceil(n/w))` cho phép hàng loạt.
- **Không có cấu trúc tốt nhất cho mọi mục đích.** Hãy chọn theo ngữ nghĩa, mật độ, thao tác, kích thước, khả năng sửa, mức độ chia sẻ và giao diện tương tác.
