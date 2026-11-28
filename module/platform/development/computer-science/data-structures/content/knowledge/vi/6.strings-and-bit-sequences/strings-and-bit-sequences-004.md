# Chuỗi khả biến, bất biến và bộ đệm xây dựng chuỗi

Một chương trình cần tạo thông báo từ hàng nghìn dòng dữ liệu. Nếu mỗi lần thêm một dòng đều ghép vào chuỗi cũ, chương trình có thể liên tục sao chép phần văn bản đã tạo. Nếu dùng bộ đệm xây dựng chuỗi, chương trình có thể ghi thêm dữ liệu vào vùng nhớ dự phòng và chỉ tạo chuỗi kết quả sau khi hoàn tất. Hai cách có thể cho **cùng một nội dung** nhưng khác đáng kể về chi phí thời gian, bộ nhớ và cách chia sẻ dữ liệu.

Trong chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, chủ đề này giúp người học hiểu **bất biến (immutable)**, **khả biến (mutable)**, **bộ đệm xây dựng chuỗi (string builder)** và đánh đổi giữa chi phí sao chép với khả năng sửa tại chỗ. Kiến thức liên hệ trực tiếp đến mảng động, quản lý dung lượng, bất biến biểu diễn, phân tích độ phức tạp thời gian/bộ nhớ và chọn cấu trúc dữ liệu phù hợp với thao tác thực tế.

## 1. Ba khái niệm cơ bản

### Chuỗi bất biến (immutable string)

**Chuỗi bất biến** là giá trị mà nội dung không thể bị thay đổi thông qua các thao tác thông thường sau khi tạo. Muốn có nội dung khác, chương trình phải thu được **một giá trị chuỗi mới**, dù biến có thể tiếp tục giữ tên cũ.

Ví dụ Python:

```python
first = "data"
alias = first

first = first + " structures"

print(first)  # data structures
print(alias)  # data
```

Dòng `first = first + " structures"` **gán lại biến `first`** với kết quả nối. Giá trị ban đầu `"data"` vẫn nguyên vẹn nên `alias` không thay đổi. Trong Python, cách viết `first[0] = "D"` không hợp lệ vì `str` bất biến.

Bất biến giúp suy luận đơn giản: nếu hai nơi cùng giữ tham chiếu đến một đối tượng chuỗi bất biến, một nơi không thể bí mật thay đổi nội dung mà nơi kia đang đọc. Chuỗi bất biến cũng phù hợp với các khóa được so sánh theo giá trị vì nội dung và giá trị băm của khóa không bị đổi bởi thao tác sửa chuỗi.

**Cần phân biệt:** bất biến của đối tượng chuỗi không đồng nghĩa biến không thể gán lại. Trong ví dụ trên, `first` là tên biến có thể nhận giá trị khác; chính nội dung của giá trị chuỗi là bất biến.

### Chuỗi khả biến (mutable string)

**Chuỗi khả biến** cho phép thay đổi nội dung của cùng một đối tượng: sửa phần tử, thêm đoạn, xóa đoạn hoặc thay thế đoạn, tùy các phép toán API hỗ trợ.

Ví dụ Python với `bytearray` (đây là bộ đệm **byte khả biến**, chưa phải abstraction đầy đủ cho ký tự Unicode):

```python
buffer = bytearray(b"data")
alias = buffer

buffer[0] = ord("D")
buffer.extend(b" structures")

print(buffer.decode("ascii"))  # Data structures
print(alias.decode("ascii"))   # Data structures
print(buffer is alias)         # True
```

Vì `buffer` và `alias` trỏ đến cùng đối tượng khả biến, sửa qua một tên có thể nhìn thấy qua tên còn lại. Đó là **aliasing**: nhiều tham chiếu cùng sở hữu hoặc quan sát một trạng thái khả biến.

Khả biến thường tiết kiệm việc cấp phát khi sửa nhiều lần, nhưng API phải quy định rõ ai được sửa, ai đang giữ tham chiếu, và điều gì xảy ra nếu vùng nhớ được cấp phát lại.

### Bộ đệm xây dựng chuỗi (string builder)

**String builder** là đối tượng được thiết kế để **tích lũy văn bản qua nhiều thao tác**, đặc biệt là thêm ở cuối, rồi chuyển thành kết quả chuỗi.

```text
Bắt đầu:   builder = ""
append A:  [A][ ][ ][ ][ ][ ][ ][ ]
append B:  [A][B][ ][ ][ ][ ][ ][ ]
append CD: [A][B][C][D][ ][ ][ ][ ]
           └─ length 4 ─┘└ capacity còn dư ┘

Kết thúc: build() → "ABCD"
```

Nhiều builder hoạt động tương tự **mảng động**: lưu một vùng nhớ có sức chứa lớn hơn dữ liệu đang dùng, mở rộng khi cần và tránh việc tạo chuỗi mới sau từng lần nối. Builder **không bắt buộc** luôn dùng một mảng liên tiếp; có thư viện tích lũy danh sách mảnh rồi ghép một lần. Điều quan trọng là hợp đồng và chi phí của các phép `append`, `insert`, `clear` và `build`.

## 2. Biểu diễn trong bộ nhớ và các bất biến cần duy trì

Với builder hoặc chuỗi khả biến lưu liên tiếp, có thể mô hình hóa trạng thái như sau:

```text
buffer:   [A][B][C][D][?][?][?][?]
          |<-- length = 4 -->|
          |<------- capacity = 8 ------->|
```

- `length` là số **đơn vị lưu trữ đang thuộc nội dung logic**.
- `capacity` là số đơn vị **có thể chứa** mà chưa cần mở rộng bộ nhớ.
- `buffer[0:length]` là dữ liệu thực tế; phần từ `length` đến `capacity - 1` là vùng dự phòng, không được tự động coi là nội dung.
- Bất biến cơ bản: `0 ≤ length ≤ capacity`.

Nếu builder lưu **UTF-8**, `length` có thể đếm **byte**; nếu lưu **UTF-16**, nó có thể đếm **code unit 16 bit**. Số này có thể khác số Unicode code point và số grapheme cluster (ký tự hiển thị). Ví dụ `"🙂"` chiếm 4 byte UTF-8, 2 code unit UTF-16, 1 code point và thường là 1 grapheme cluster.

Khi thiết kế thao tác sửa, cần duy trì thêm bất biến về dữ liệu:

1. **Ranh giới hợp lệ:** nếu nội dung được cam kết là chuỗi UTF-8 hợp lệ, không được cắt tại một byte tiếp diễn rồi trả về chuỗi hỏng.
2. **Đơn vị chỉ số nhất quán:** chỉ số byte, code unit, code point và grapheme phải được phân biệt.
3. **Độ dài thực tế được cập nhật:** sau thêm, xóa, thay thế phải phản ánh đúng số phần tử logic.
4. **Vòng đời tham chiếu:** nếu bộ đệm thay địa chỉ khi mở rộng, view/con trỏ đến vùng nhớ cũ có thể không còn hợp lệ; quy tắc phụ thuộc ngôn ngữ và API.
5. **Ảnh chụp bất biến:** nếu `build()` trả về một chuỗi bất biến, sửa builder về sau **không được làm thay đổi** nội dung chuỗi đã trả về.

Không phải builder nào cũng cho phép sửa một code unit tùy ý. Một số builder chỉ hỗ trợ thêm văn bản hợp lệ, nhờ đó dễ duy trì tính hợp lệ của mã hóa hơn một bộ đệm byte cho phép ghi ở mọi offset.

## 3. Phép nối lặp lại có thể tốn bao nhiêu?

Giả sử có `k` đoạn văn bản, mỗi đoạn dài `m` đơn vị lưu trữ. Tổng chiều dài kết quả là `N = k × m`.

Nếu mỗi phép nối của chuỗi bất biến phải **cấp phát và sao chép toàn bộ tiền tố đã có**, các bước sẽ xử lý:

```text
Sau đoạn 1:  m   đơn vị
Sau đoạn 2:  2m  đơn vị
Sau đoạn 3:  3m  đơn vị
...
Sau đoạn k:  km  đơn vị
```

Tổng số đơn vị được viết vào các kết quả trung gian là:

```text
m + 2m + 3m + ... + km
= m × k(k + 1) / 2
= Θ(m × k²)
= Θ(N × k)
```

Với các đoạn có độ dài cố định `m = Θ(1)`, thì `k = Θ(N)` và tổng công việc là **`Θ(N²)`**. Đây là mô hình chi phí khi mỗi lần nối thực sự sao chép tiền tố; một số runtime có tối ưu chuyên biệt hoặc biểu diễn nội bộ khác, nên không thể mặc định mọi cú pháp `+=` trong mọi ngôn ngữ luôn có cùng chi phí này.

Ngược lại, nếu tích lũy các đoạn trong một builder hiệu quả rồi hoàn thiện một lần, tổng chi phí ghi dữ liệu thường gần **`O(N)`** với chi phí khấu hao thích hợp, cộng công quản lý `k` đoạn.

### Ví dụ với Python

```python
parts = ["cấu", " ", "trúc", " ", "dữ", " ", "liệu"]

# Kết quả đúng, nhưng việc cộng dồn từng phần có thể gây sao chép tiền tố.
text = ""
for part in parts:
    text += part

# Thường phù hợp khi đã có sẵn danh sách các phần và cần một chuỗi.
result = "".join(parts)

assert text == result
print(result)  # cấu trúc dữ liệu
```

`str.join` biết toàn bộ các phần tử đầu vào và tạo ra kết quả bằng cách ghép chúng; với danh sách chuỗi, thời gian thường tuyến tính theo số phần và tổng độ dài đầu ra. Nếu đoạn được sinh dần, có thể giữ danh sách rồi `join` một lần:

```python
def build_report(rows):
    parts = ["DANH SÁCH\n"]
    for index, name in enumerate(rows, start=1):
        parts.append(f"{index}. {name}\n")
    return "".join(parts)

print(build_report(["Mảng", "Stack", "Queue"]))
```

Danh sách `parts` cũng chiếm bộ nhớ cho tham chiếu đến các mảnh và các chuỗi con; khi `join`, bộ nhớ cho kết quả mới còn tồn tại song song với các mảnh ít nhất trong giai đoạn ghép. Vì vậy tiết kiệm **sao chép lặp lại** không đồng nghĩa mọi thời điểm đều dùng ít bộ nhớ nhất.

## 4. Builder tăng dung lượng như mảng động

Một cách triển khai phổ biến cho `append` có `length` hiện tại và `capacity`. Khi có thêm `m` đơn vị:

1. Tính dung lượng cần có `required = length + m`.
2. Nếu `required ≤ capacity`, ghi thêm vào vùng dự phòng.
3. Nếu không đủ, cấp phát vùng mới có dung lượng lớn hơn, chép phần dữ liệu cũ sang rồi ghi dữ liệu mới.
4. Cập nhật `length = required` sau khi dữ liệu được ghi hợp lệ.

Giả mã ở mức đơn vị lưu trữ:

```text
append(data, m):
    required = length + m
    if required > capacity:
        newCapacity = max(required, max(1, capacity * 2))
        newBuffer = allocate(newCapacity)
        copy(newBuffer, 0, buffer, 0, length)
        buffer = newBuffer
        capacity = newCapacity

    copy(buffer, length, data, 0, m)
    length = required
```

Mã giả thiết `required`, phép nhân dung lượng và cấp phát đều được kiểm tra chống tràn và lỗi bộ nhớ trong triển khai thật. Nếu `data` cùng chia sẻ bộ nhớ với `buffer`, cần xử lý an toàn tình huống chồng lấn hoặc cấp phát lại làm mất địa chỉ nguồn; không thể áp dụng nguyên xi giả mã cho mọi ngôn ngữ.

### Chi phí khấu hao khi tăng theo hệ số

Giả sử builder bắt đầu với sức chứa 1, và mỗi lần đầy thì **gấp đôi capacity**:

```text
capacity: 1 → 2 → 4 → 8 → 16 → 32 → ...
```

Lần mở rộng có thể phải sao chép toàn bộ dữ liệu hiện có, nên **một lần append** có thể tốn `O(n)` khi `n` là độ dài trước khi mở rộng.

Tuy nhiên, sau `N` lần thêm **mỗi lần một đơn vị**, tổng số phần tử cũ được sao chép ở các lần mở rộng nhỏ hơn:

```text
1 + 2 + 4 + 8 + ... < 2N
```

Cộng với `N` đơn vị được ghi mới, tổng công việc là `O(N)`. Như vậy:

- **Append một đơn vị:** `O(1)` **khấu hao**, `O(n)` trong lần phải mở rộng.
- **Append đoạn `m` đơn vị:** `O(m)` **khấu hao** theo lượng dữ liệu được bổ sung, có thể cộng chi phí sao chép tại một lần mở rộng.
- **Bộ nhớ:** có thể dự phòng đáng kể so với `length`; khi vừa tăng gấp đôi, `capacity` gần gấp đôi độ dài.

Đây là nguyên tắc tương tự **dynamic array**. Nếu mỗi lần thiếu chỗ chỉ tăng `capacity` thêm 1 đơn vị, việc append `N` đơn vị có thể dẫn đến `Θ(N²)` công sao chép. Quy tắc tăng dung lượng ảnh hưởng trực tiếp đến độ phức tạp.

### Chủ động dành dung lượng (reserve)

Nếu đã biết độ dài gần đúng của kết quả, có thể đặt trước `capacity` để giảm cấp phát lại. `reserve` thay đổi **sức chứa**, không thay đổi `length` hay nội dung logic. Không được ghi vào phần capacity dự phòng như thể đã là phần tử hợp lệ, trừ khi API cho phép theo đúng hợp đồng.

Ví dụ Java:

```java
StringBuilder builder = new StringBuilder(64);

builder.append("Mảng");
builder.append(", ");
builder.append("Stack");
builder.append(", ");
builder.append("Queue");

String result = builder.toString();
System.out.println(result);  // Mảng, Stack, Queue
```

Ở đây số 64 là **dung lượng ban đầu theo đơn vị mà `StringBuilder` công bố**, không phải 64 byte UTF-8 hay 64 grapheme. Java `StringBuilder` làm việc với API chuỗi dựa trên UTF-16 code unit; cách lưu bên trong có thể thay đổi giữa phiên bản JVM.

## 5. Chi phí của các thao tác và lựa chọn cấu trúc

Trong bảng, gọi `n` là số đơn vị hiện có, `m` là độ dài đoạn thêm và `N` là tổng độ dài đầu ra. Chi phí giả định kiểu chuỗi bất biến nối bằng cách tạo/copy kết quả, builder có vùng nhớ liên tiếp tăng theo hệ số.

| Thao tác | Chuỗi bất biến lưu liên tiếp | Builder trên bộ đệm động |
|---|---|---|
| Đọc độ dài đã lưu | `O(1)` | `O(1)` |
| Đọc code unit tại chỉ số hợp lệ | `O(1)` | `O(1)` |
| Thêm `m` đơn vị vào cuối | Thường `O(n + m)` do tạo kết quả mới | `O(m)` khấu hao; có lần `O(n + m)` khi tăng dung lượng |
| Thêm một đơn vị vào cuối nhiều lần | Có thể `O(N²)` nếu luôn chép tiền tố | `O(N)` tổng khi tăng dung lượng theo hệ số |
| Chèn `m` đơn vị vào đầu/giữa | `O(n + m)` tạo mới | `O(n + m)` do phải dịch chuyển phần đuôi trong trường hợp xấu |
| Xóa đoạn giữa | Thường `O(n)` để tạo mới | Thường `O(n)` để dời phần còn lại |
| Hoàn tất nội dung dạng chuỗi bất biến | Sẵn có một giá trị bất biến | Phụ thuộc `build()/toString()`: có thể tạo bản sao `O(n)` |
| Duyệt toàn bộ nội dung | `O(n)` | `O(n)` |
| Bộ nhớ dự phòng | Thường ít nếu lưu vừa đủ; tùy runtime | Thường có `capacity - length` đơn vị chưa sử dụng |

Bảng không mô tả **truy cập theo code point hoặc grapheme** của UTF-8/UTF-16. Đọc code unit ở chỉ số biết trước có thể `O(1)`, nhưng xác định code point thứ `i` trong mã hóa độ rộng thay đổi có thể cần quét hoặc một chỉ mục phụ.

**Builder không làm thao tác chèn giữa trở thành `O(1)`.** Nếu thường xuyên sửa giữa tài liệu rất lớn, có thể cân nhắc gap buffer, rope hoặc piece table. Nếu chủ yếu thêm nội dung ở cuối, builder hoặc mảng động thường là lựa chọn trực tiếp và dễ kiểm soát hơn.

## 6. Ví dụ đối chiếu theo ngôn ngữ

### Python: `str` bất biến, danh sách phần tử và `io.StringIO`

Python `str` là kiểu chuỗi bất biến. Khi nội dung đến từ nhiều phần, các lựa chọn phổ biến là `list` + `join` hoặc `io.StringIO`.

```python
from io import StringIO

def render_lines(lines):
    out = StringIO()
    out.write("KẾT QUẢ\n")
    for line in lines:
        out.write("- ")
        out.write(line)
        out.write("\n")
    return out.getvalue()

print(render_lines(["Array", "Stack", "Queue"]))
```

`StringIO` cung cấp bộ đệm ghi văn bản; `getvalue()` trả về giá trị `str`. Chi tiết cấp phát và sao chép trong lúc hoàn tất là quyết định triển khai. Với dữ liệu **nhị phân**, dùng `bytearray` hoặc `io.BytesIO` thay vì giải thích mọi byte là ký tự.

### Java: `String`, `StringBuilder` và `StringBuffer`

- `String` là chuỗi bất biến; các phép tạo kết quả khác không sửa nội dung chuỗi cũ.
- `StringBuilder` dành cho thao tác xây dựng/đổi nội dung văn bản trong cùng luồng hoặc khi đã tự tổ chức đồng bộ thích hợp.
- `StringBuffer` có các phương thức đồng bộ, hữu ích trong một số tình huống chia sẻ, nhưng **không thay thế** việc thiết kế đồng bộ cho chuỗi nhiều thao tác cần tính nguyên tử.

```java
String original = "Array";
String alias = original;

original = original.concat(" List");
System.out.println(alias);      // Array

StringBuilder builder = new StringBuilder();
builder.append("Array");
builder.append(' ');
builder.append("List");

String snapshot = builder.toString();
builder.append(" + Stack");

System.out.println(snapshot);   // Array List
System.out.println(builder);    // Array List + Stack
```

Điểm đáng chú ý: `snapshot` là `String` bất biến, nội dung phải tiếp tục ổn định dù `builder` được dùng thêm. Không nên tự giả định việc tạo snapshot luôn không sao chép hoặc luôn sao chép; hãy xem tài liệu và kết quả đo nếu chi phí hoàn tất là nút thắt cổ chai.

### JavaScript: chuỗi bất biến và `join`

JavaScript `String` bất biến; không thể thay một đơn vị bên trong đối tượng chuỗi bằng cách gán `s[i] = ...` rồi mong nội dung đổi. Với các mảnh sẵn có hoặc được sinh dần, có thể tập hợp trong mảng:

```javascript
const parts = [];

for (let i = 1; i <= 3; i++) {
  parts.push("Dòng " + i + "\n");
}

const result = parts.join("");
console.log(result);
// Dòng 1
// Dòng 2
// Dòng 3
```

Engine JavaScript có thể tối ưu phép nối chuỗi bằng các biểu diễn nội bộ đặc biệt. Vì thế cần đánh giá trên dữ liệu thực tế thay vì khẳng định mọi lần `+=` đều tạo bản sao toàn bộ ngay lập tức. Cấu trúc ghép một lần từ mảng giúp **diễn đạt rõ mục tiêu tích lũy**, đồng thời phải tính bộ nhớ giữ các mảnh.

### C++: `std::string` là vùng chuỗi có thể sửa

Trong C++, `std::string` hỗ trợ các phép `append`, `push_back`, `insert`, `erase` và `reserve`. Ví dụ:

```cpp
#include <iostream>
#include <string>

int main() {
    std::string text;
    text.reserve(64);

    text += "Array";
    text.push_back(' ');
    text += "Stack";

    std::cout << text << '\n'; // Array Stack
}
```

`std::string` quản lý một dãy `char`; với nội dung UTF-8, `size()` trả số **byte/code unit char** mà đối tượng đang giữ, không mặc nhiên là số Unicode code point hay grapheme. Một số thao tác làm thay đổi dung lượng có thể khiến con trỏ, iterator hoặc tham chiếu tới phần tử không còn hợp lệ theo quy tắc của API; tránh giữ địa chỉ cũ khi builder còn mở rộng.

## 7. Chia sẻ dữ liệu: bất biến, aliasing và bản sao

### Bất biến giúp chia sẻ dễ dự đoán

Khi đối tượng chuỗi không thể đổi nội dung, hai thành phần có thể chia sẻ cùng giá trị mà không sợ một thành phần thay đổi nó. Điều này hữu ích cho:

- Dùng chuỗi làm **khóa bảng băm**: giá trị dùng cho `hash` và so sánh không bị sửa giữa chừng.
- **Truyền dữ liệu qua nhiều hàm**: hàm nhận chuỗi không cần lo hàm khác sửa trực tiếp phần đã nhận.
- **Lưu phiên bản cũ**: một giá trị đã lưu tiếp tục biểu diễn cùng văn bản.

Tuy nhiên, một **đối tượng bao ngoài** có thể khả biến dù các chuỗi bên trong bất biến. Ví dụ, danh sách Python chứa `str` vẫn có thể bị thêm/xóa hoặc thay thế phần tử.

### Khả biến đòi hỏi quy tắc sở hữu

Nếu một builder được nhiều nơi cùng dùng, cần trả lời rõ:

- Ai được thêm/xóa/sửa?
- Có được giữ một `view` vào vùng nhớ bên trong không?
- Khi `build()` xong, ai sở hữu vùng nhớ của kết quả?
- Có cho phép sửa tiếp builder mà kết quả cũ vẫn không thay đổi không?
- Có truy cập đồng thời từ nhiều luồng không?

Một cách API dễ sử dụng là coi builder như **đối tượng sở hữu nội dung đang soạn**, còn `build()` trả về bản kết quả bất biến độc lập về mặt quan sát. Về triển khai, có thể dùng **copy-on-write**, chuyển giao quyền sở hữu hoặc sao chép; mỗi lựa chọn có chi phí và bất biến riêng. Không được dùng chung vùng nhớ có thể sửa theo cách làm thay đổi kết quả bất biến đã xuất ra.

### Lưu ý khi xử lý khóa và dữ liệu nhạy cảm

Dùng nội dung khả biến làm khóa cho một bảng băm dựa trên hash của nội dung có thể phá vỡ khả năng tìm lại khóa nếu sửa nội dung sau khi chèn. Nên dùng giá trị khóa bất biến hoặc bảo đảm tuyệt đối không sửa trạng thái tham gia hash/equality.

Với dữ liệu nhạy cảm cần chủ động xóa bộ nhớ, chuỗi bất biến có thể làm xuất hiện các bản sao không kiểm soát được. Một số ứng dụng chuyên biệt chọn bộ đệm khả biến có chính sách quản lý bộ nhớ chặt hơn, nhưng thao tác xóa dữ liệu vẫn phụ thuộc runtime, bản sao và khả năng tối ưu của hệ thống; không được coi việc gán lại biến là xóa hết dấu vết.

## 8. Builder phải bảo vệ ranh giới Unicode

Một builder lưu byte UTF-8 có thể thực hiện append nhanh, nhưng nếu cho phép ghi vào byte bất kỳ thì thao tác sửa có thể tạo văn bản không hợp lệ.

```python
raw = bytearray("é".encode("utf-8"))  # C3 A9
raw[0] = ord("e")                     # 65 A9: không còn UTF-8 hợp lệ

try:
    print(raw.decode("utf-8"))
except UnicodeDecodeError:
    print("Dãy byte đã bị sửa hỏng ranh giới UTF-8")
```

Trong builder dựa trên UTF-16, sửa/xóa một code unit có thể để lại một surrogate không ghép cặp. Ngay cả khi kết quả vẫn là văn bản Unicode hợp lệ, xóa đúng một **code point** có thể bỏ lại dấu kết hợp và khiến hiển thị khác kỳ vọng.

Vì vậy, trước khi công bố API sửa chuỗi, hãy xác định đơn vị hợp lệ của vị trí và đoạn:

| Mục đích | Đơn vị thường phù hợp |
|---|---|
| Gửi/nhận dữ liệu theo giao thức byte | Byte, với kiểm tra ranh giới giải mã khi xử lý văn bản |
| Thao tác trực tiếp trên bộ đệm UTF-16 | Code unit theo hợp đồng API |
| Chuyển đổi và xử lý giá trị Unicode | Code point |
| Di chuyển con trỏ, xóa một “ký tự” người dùng nhìn thấy | Grapheme cluster theo quy tắc Unicode |

Không nên coi `StringBuilder` hay một mảng byte khả biến là cơ chế tự động xử lý đúng mọi quy tắc grapheme. Nếu giao diện cần xóa/chèn theo cụm ký tự, phải có lớp phân đoạn hoặc chỉ mục tương ứng.

## 9. Khi nào dùng chuỗi bất biến, khi nào dùng builder?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Giá trị cấu hình, mã định danh, khóa từ điển | Chuỗi bất biến | Giá trị ổn định, dễ chia sẻ và so sánh |
| Nối hai đoạn nhỏ một lần | Phép nối chuỗi thông thường | Đơn giản, chi phí thường không đáng kể |
| Xây báo cáo từ nhiều dòng, ghi log định dạng, tạo truy vấn/văn bản | Builder hoặc danh sách mảnh + ghép một lần | Tránh sao chép tiền tố lặp lại |
| Biết trước dung lượng đầu ra gần đúng | Builder có `reserve` / dung lượng ban đầu thích hợp | Giảm lần cấp phát lại |
| Thường xuyên chèn/xóa ở đầu hoặc giữa tài liệu lớn | Cân nhắc gap buffer, rope hoặc piece table | Builder mảng liên tiếp vẫn phải dời dữ liệu |
| Cần lưu phiên bản cũ để tra cứu hoặc truyền giữa thành phần | Giá trị bất biến/snapshot | Tránh thay đổi dữ liệu đã công bố |
| Xử lý dữ liệu byte nhị phân | Bộ đệm byte khả biến nếu cần sửa | Rõ ràng về đơn vị, không tự giải mã Unicode |

Quyết định không chỉ dựa vào dung lượng tối đa. Một chuỗi rất lớn nhưng chủ yếu được **đọc và chia sẻ** có thể phù hợp với dạng bất biến. Một chuỗi vừa phải nhưng được **ghép từ nhiều phần** có thể hưởng lợi từ builder. Tần suất thao tác, đơn vị chỉ số, vòng đời dữ liệu và chi phí bộ nhớ đều quan trọng.

## 10. Bài tập tư duy và tự kiểm tra

**Câu 1.** Trong Python, vì sao sau đoạn mã dưới đây `b` không trở thành `"xy"`?

```python
a = "x"
b = a
a += "y"
print(b)
```

**Đáp án:** `str` là bất biến; `a += "y"` gán `a` tới kết quả ghép mới về mặt ngữ nghĩa, không sửa đối tượng `"x"` mà `b` đang tham chiếu.

**Câu 2.** Một builder tăng `capacity` gấp đôi khi đầy. Sau khi thêm lần lượt `N` phần tử đơn vị, chi phí một lần `append` và chi phí toàn bộ chuỗi thao tác là bao nhiêu?

**Đáp án:** Một lần append có thể `O(n)` khi phải sao chép để cấp phát lại; chi phí **khấu hao** mỗi lần là `O(1)`, tổng `O(N)` cho `N` lần thêm đơn vị, nếu cơ chế tăng dung lượng theo hệ số và các giả định chi phí thông thường được đáp ứng.

**Câu 3.** Nếu biết `capacity = 128` và `length = 30`, có thể đọc 128 phần tử như nội dung chuỗi không?

**Đáp án:** Không. Chỉ `30` phần tử trong vùng `[0, 30)` thuộc nội dung logic; `98` phần tử còn lại là vùng dự phòng, không thể coi là ký tự hợp lệ.

**Câu 4.** Builder đã tạo `snapshot = builder.toString()`. Sau đó thêm văn bản vào builder, `snapshot` có được thay đổi theo không?

**Đáp án:** Không. `snapshot` là giá trị chuỗi bất biến và phải giữ nguyên nội dung đã trả về. Việc thư viện tạo bản sao hay dùng chiến lược chia sẻ bộ nhớ là chi tiết triển khai miễn vẫn bảo đảm hợp đồng đó.

**Câu 5.** Tại sao builder không nhất thiết là lựa chọn tốt nhất cho trình soạn thảo liên tục sửa tại nhiều vị trí trong tài liệu lớn?

**Đáp án:** Builder dùng vùng nhớ liên tiếp thường phải dịch chuyển nhiều phần tử khi chèn/xóa giữa, mất `O(n)` trong trường hợp xấu. Gap buffer, rope hoặc piece table có thể phù hợp hơn với mẫu chỉnh sửa này.

**Câu 6.** Dùng `bytearray` để xóa một byte bất kỳ trong chuỗi UTF-8 có an toàn về mặt văn bản không?

**Đáp án:** Không. Có thể xóa một phần byte của code point, khiến UTF-8 không hợp lệ. Nếu thao tác theo ký tự người dùng nhìn thấy, phải bảo vệ cả ranh giới grapheme, không chỉ code point.

## Ghi nhớ

- **Bất biến** nghĩa là nội dung giá trị không sửa được; **gán lại biến** không phải sửa giá trị. **Khả biến** cho phép sửa cùng đối tượng, nhưng phải quản lý aliasing, vòng đời và truy cập đồng thời.
- **String builder** phù hợp với việc tích lũy nhiều đoạn, đặc biệt là append ở cuối. Cách tăng dung lượng theo hệ số giúp đạt **`O(1)` khấu hao** cho mỗi đơn vị thêm và `O(N)` cho `N` lần thêm đơn vị.
- Luôn phân biệt **`length`** với **`capacity`**, và xác định `length` đang đo byte, code unit, code point hay grapheme.
- Builder liên tiếp vẫn có thể tốn **`O(n)`** khi chèn/xóa giữa và khi cần cấp phát lại; `build()/toString()` cũng có thể cần tạo bản sao.
- Chọn cấu trúc theo **thao tác chủ đạo**, **tính ổn định của dữ liệu**, **chi phí bộ nhớ** và **bất biến Unicode** mà hệ thống cần bảo đảm.
