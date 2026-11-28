# Chuỗi con được sao chép hay chia sẻ vùng lưu trữ

Một hệ thống đọc tệp nhật ký 100 MB để lấy mã yêu cầu dài 20 byte. Sau khi tệp đã được phân tích, hệ thống chỉ cần giữ mã yêu cầu đó. Có hai cách hiện thực thao tác lấy chuỗi con: **sao chép 20 byte sang vùng lưu trữ riêng** hoặc **giữ một lát cắt (view) trỏ vào 20 byte nằm trong dữ liệu gốc**. Lựa chọn thứ hai có vẻ nhanh hơn vì tránh sao chép, nhưng trong một số mô hình quản lý bộ nhớ nó có thể khiến toàn bộ 100 MB chưa được giải phóng.

Bài học thuộc chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Ta sẽ dùng mô hình dữ liệu, bất biến và phân tích độ phức tạp để hiểu khi nào chuỗi con thực sự có bản sao, khi nào chia sẻ bộ nhớ, và ảnh hưởng của mỗi lựa chọn đối với thời gian, bộ nhớ, tính đúng đắn và vòng đời dữ liệu. Đây là một ví dụ điển hình của việc chọn cấu trúc dữ liệu dựa vào kiểu thao tác, tương tự cách cân nhắc giữa mảng, danh sách liên kết, bảng băm, cây, heap hay đồ thị.

## 1. Chuỗi con là một khái niệm logic; cách lưu trữ là quyết định triển khai

Với chuỗi \(S\) có độ dài \(n\), một **chuỗi con liên tiếp** (substring) được xác định bằng khoảng nửa mở \([i,j)\):

\[
S[i:j] = (S_i,S_{i+1},\ldots,S_{j-1}),\qquad 0\le i\le j\le n.
\]

Chuỗi con có độ dài \(k=j-i\). Ví dụ, với `S = "abcdef"`, `S[2:5]` có nội dung `"cde"`.

**Nội dung logic** của `"cde"` không thay đổi dù cách hiện thực là:

- **Copy:** cấp phát vùng mới chứa `"cde"`.
- **View/slice:** lưu tham chiếu tới vùng `"abcdef"`, offset 2 và độ dài 3.
- **Cấu trúc phân mảnh:** lưu các mảnh hoặc nút cây mô tả đoạn con, nếu chuỗi nguồn dùng rope/piece table.

Vì vậy, các tên `substring`, `slice`, `substr` hoặc cú pháp `s[i:j]` **không đủ** để kết luận dữ liệu có được sao chép hay không. Cần đọc hợp đồng của kiểu dữ liệu và API cụ thể.

Trong bài này, trừ khi có chú thích khác, \(n\) và \(k\) tính theo **đơn vị lưu trữ của biểu diễn** (ví dụ byte hoặc UTF-16 code unit). Số ký tự hiển thị không nhất thiết bằng số đơn vị này.

## 2. Hai cách biểu diễn: copy và view

### 2.1. Sao chép sang vùng độc lập

```text
Nguồn:
  index:    0   1   2   3   4   5
  source:  [a] [b] [c] [d] [e] [f]
                    └───────┘
                    lấy [2:5)

Kết quả copy:
  copy:    [c] [d] [e]
             vùng nhớ mới
```

Mỗi phần tử nội dung của đoạn con được sao chép từ nguồn vào vùng mới. Nếu chuỗi con dài \(k\) đơn vị, tạo bản sao thường tốn **\(O(k)\) thời gian** và **\(O(k)\) bộ nhớ dữ liệu bổ sung**.

Hệ quả quan trọng: bản sao có thể tồn tại độc lập với vùng lưu trữ nguồn. Sau khi hoàn tất sao chép, có thể giải phóng nguồn nếu không còn ai cần nó. Nếu nguồn khả biến bị chỉnh sửa, nội dung bản sao đã tạo không đổi.

### 2.2. View tham chiếu vùng nguồn

```text
Nguồn:
  owner:   [a] [b] [c] [d] [e] [f]
                     ▲
                     |
View:
  buffer = owner
  offset = 2
  length = 3

Đọc view[0] → owner[2] → "c"
Đọc view[2] → owner[4] → "e"
```

Một view điển hình được biểu diễn bằng bộ metadata có kích thước cố định:

```text
Slice {
    reference_to_backing_storage
    offset
    length
}
```

Việc tạo view từ một mảng liên tiếp, khi các chỉ số đã biết và hợp lệ, thường tốn **\(O(1)\) thời gian** và **\(O(1)\) bộ nhớ metadata**; không cần sao chép \(k\) phần tử. Tuy nhiên, `O(1)` là chi phí **tạo đối tượng lát cắt**, không nói toàn bộ bộ nhớ mà hệ thống phải giữ sống.

Ví dụ view chỉ rộng 3 byte nhưng vẫn giữ nguồn 6 byte. Trong tình huống lớn hơn, view chỉ 20 byte có thể giữ một nguồn 100 MB còn sống, tùy cơ chế sở hữu.

### 2.3. View của view

Nếu `v1` là view của nguồn với `offset = 10`, `length = 30` và tiếp tục lấy `v2 = v1[5:9]`, có thể biểu diễn trực tiếp:

```text
v2.owner  = v1.owner
v2.offset = v1.offset + 5   # 15
v2.length = 9 - 5          # 4
```

Khi metadata và chỉ số hợp lệ, tạo view lồng nhau có thể vẫn là \(O(1)\). Bất biến bắt buộc là:

\[
0\le \text{offset},\quad 0\le\text{length},\quad
\text{offset}+\text{length}\le\text{backingLength}.
\]

Trong triển khai thực tế, cần kiểm tra giới hạn trước khi cộng chỉ số để tránh tràn số nguyên; nếu view chỉ có quyền truy cập một phần nguồn, thao tác con còn phải nằm trong **phạm vi view cha**.

## 3. Độ phức tạp: không sao chép không có nghĩa mọi thao tác đều miễn phí

Giả sử nguồn là một dãy \(n\) đơn vị nằm liên tiếp trong bộ nhớ, lấy đoạn độ dài \(k\), và đã biết chỉ số đầu/cuối theo đúng đơn vị của dãy.

| Thao tác | Chuỗi con copy | Chuỗi con view |
|---|---|---|
| Tạo đoạn con | \(O(k)\) do sao chép | Thường \(O(1)\) tạo metadata |
| Bộ nhớ dữ liệu mới | \(O(k)\) | Không sao chép dữ liệu; metadata \(O(1)\) |
| Đọc phần tử lưu trữ thứ \(i\) | \(O(1)\) nếu mảng liên tiếp | \(O(1)\) qua `offset + i` |
| Duyệt đủ \(k\) phần tử | \(O(k)\) | \(O(k)\) |
| So sánh nội dung với chuỗi khác | Thường \(O(k)\) trong trường hợp xấu | Thường \(O(k)\) trong trường hợp xấu |
| Tính hash từ nội dung chưa có cache | \(O(k)\) | \(O(k)\) |
| Giải phóng nguồn khi chỉ cần đoạn con | Có thể giải phóng nguồn | Tùy cơ chế sở hữu/lifetime; view có thể giữ nguồn sống |
| Đổi nguồn khả biến | Bản sao đã tạo không đổi | View có thể thấy nội dung thay đổi hoặc mất hiệu lực |
| Tạo chuỗi độc lập từ kết quả | Đã độc lập | Cần sao chép \(O(k)\), trừ cơ chế chuyển quyền sở hữu phù hợp |

Bảng mô tả **mảng lưu trữ liên tiếp**. Với rope hoặc cấu trúc chuỗi phân mảnh, việc tìm vị trí, ghép mảnh hoặc duyệt nút có chi phí khác, phụ thuộc số nút, cân bằng cây và cơ chế metadata.

Một thao tác thường bị đánh giá nhầm là **lấy ký tự Unicode thứ \(i\)**. Byte thứ \(i\) trong mảng UTF-8 có thể đọc \(O(1)\), nhưng xác định *code point* thứ \(i\) từ byte chưa có chỉ mục có thể cần giải mã tuần tự. Copy/view không tự giải quyết việc đổi giữa chỉ số byte, code point và grapheme cluster.

## 4. Ba mô hình sở hữu bộ nhớ cần phân biệt

Dùng từ “view” vẫn chưa đủ để nói chính xác về **vòng đời dữ liệu**. Ít nhất cần phân biệt ba cơ chế.

### 4.1. View có tham chiếu sở hữu tới nguồn

Một view có thể lưu tham chiếu mạnh (strong reference) hoặc quyền sở hữu chia sẻ tới đối tượng chứa dữ liệu. Khi view còn sống, vùng nguồn không được giải phóng.

```text
owner:  [vùng dữ liệu lớn 100 MB]
  ▲
  │ tham chiếu mạnh
view:  [offset=..., length=20]
```

Ưu điểm: nguồn không bị thu hồi trong lúc view cần đọc, giảm lỗi sử dụng vùng nhớ đã giải phóng.

Đổi lại, **memory retention** xuất hiện: view nhỏ có thể giữ nguồn lớn hơn nhiều lần dung lượng cần thiết. Bộ gom rác hoặc reference counting không thể thu hồi vùng nguồn nếu vẫn có tham chiếu mạnh thông qua view.

Ví dụ điển hình là một lát cắt giữ tham chiếu đến một mảng hoặc bộ đệm gốc. Khi lưu một số lượng nhỏ token trích từ tài liệu rất lớn, tổng dung lượng lưu trữ hiệu dụng có thể lớn hơn tổng độ dài token.

### 4.2. View mượn vùng nhớ, không sở hữu

Một số kiểu view chỉ giữ địa chỉ và độ dài; chúng **không** kéo dài vòng đời vùng dữ liệu gốc. Ví dụ `std::string_view` trong C++ là một view không sở hữu.

Ưu điểm: chi phí metadata nhỏ và không bắt buộc cơ chế quản lý tham chiếu tới chủ sở hữu.

Rủi ro: nếu vùng nguồn bị giải phóng hoặc tái cấp phát khiến địa chỉ cũ không còn hợp lệ, view có thể trở thành **dangling view**. Đọc qua view đó là lỗi nghiêm trọng; với C++ có thể dẫn tới hành vi không xác định.

### 4.3. Bản sao sở hữu độc lập

Copy tạo vùng dữ liệu mới có thể quản lý độc lập. Nó tốn chi phí tạo \(O(k)\), nhưng dễ lưu giữ lâu dài và tránh phụ thuộc vào vòng đời của đối tượng nguồn.

“Bản sao độc lập” được hiểu ở mức **ngữ nghĩa sở hữu và khả năng quan sát nội dung**, chứ không nhất thiết mọi runtime đều bắt buộc dùng một cấp phát riêng: thư viện có thể dùng tối ưu nội bộ miễn vẫn bảo đảm hợp đồng kết quả.

### Ví dụ 100 MB và 20 byte

Nếu hệ thống trích một mã 20 byte từ nguồn 100 MB và giữ mã trong nhiều giờ:

- **Copy:** giữ khoảng 20 byte nội dung cùng metadata, sau đó nguồn 100 MB có thể được giải phóng khi không còn tham chiếu khác.
- **View sở hữu nguồn:** metadata của view nhỏ nhưng có thể giữ cả nguồn 100 MB tồn tại.
- **View không sở hữu:** có thể rất nhẹ, nhưng phải giữ nguồn còn sống bằng một cơ chế bên ngoài trong suốt thời gian sử dụng view.

Lúc tạo ra, view thường nhanh hơn copy; xét **toàn bộ vòng đời**, copy đôi khi tiết kiệm bộ nhớ đáng kể hơn.

## 5. Ví dụ Python: `bytes` được cắt và `memoryview` chia sẻ bộ đệm

Python cung cấp hai cơ chế khác nhau trên dữ liệu dạng byte:

- Lát cắt `bytes` tạo **giá trị bytes bất biến** với ngữ nghĩa độc lập; trong trường hợp tổng quát thường sao chép nội dung, dù các trường hợp đặc biệt như cắt toàn bộ có thể được tối ưu.
- `memoryview` cung cấp **view của đối tượng hỗ trợ buffer protocol**, cho phép thao tác trên dữ liệu mà không sao chép.

Ví dụ với nguồn khả biến:

```python
source = bytearray(b"abcdef")

copied = bytes(source[2:5])        # b"cde": giá trị độc lập
shared = memoryview(source)[2:5]  # view trỏ vào byte của source

print(copied)          # b'cde'
print(bytes(shared))   # b'cde'

source[2] = ord("X")

print(copied)          # b'cde': bản sao không đổi
print(bytes(shared))   # b'Xde': view thấy byte đã đổi

shared.release()       # giải phóng quyền truy cập của view khi xong
```

**Nhận xét:** view của `bytearray` cho phép nhìn thấy thay đổi ở các byte còn thuộc bộ đệm. Khi đang có một `memoryview` xuất dữ liệu, các thao tác làm thay đổi **kích thước** bộ đệm nguồn có thể bị từ chối (ví dụ `BufferError`), vì hệ thống phải giữ các địa chỉ bộ nhớ hợp lệ. Đó là một bất biến thực tế liên quan đến cơ chế chia sẻ vùng lưu trữ.

Với chuỗi Unicode kiểu `str`, `s[i:j]` trả về một `str` bất biến về mặt ngữ nghĩa. Không nên suy đoán nó nhất thiết dùng chung vùng nhớ hay cấp phát mới chỉ từ ký hiệu `[:]`; hiệu năng và bố trí bộ nhớ phụ thuộc triển khai. Nếu cần view theo byte, phải xác định rõ bước mã hóa và vòng đời bộ đệm.

### Cẩn thận khi cắt UTF-8 theo byte

```python
raw = "Aé🙂".encode("utf-8")
print(raw)               # b'A\xc3\xa9\xf0\x9f\x99\x82'
print(raw[1:3].decode("utf-8"))  # é: lấy đủ 2 byte UTF-8

try:
    raw[1:2].decode("utf-8")     # chỉ lấy byte C3, thiếu byte A9
except UnicodeDecodeError:
    print("Lát cắt không nằm trên ranh giới code point")
```

Copy hay view đều không tự bảo đảm **ranh giới UTF-8 hợp lệ**. Một lát cắt theo byte có thể là dãy byte hoàn toàn hợp lệ để xử lý nhị phân nhưng **không phải** một chuỗi UTF-8 hoàn chỉnh.

## 6. Ví dụ C++: `std::string::substr` và `std::string_view::substr`

Trong C++, hai API gần giống nhau mang hợp đồng sở hữu rất khác:

```cpp
#include <iostream>
#include <string>
#include <string_view>

int main() {
    std::string source = "abcdef";

    std::string copied = source.substr(2, 3);        // "cde"
    std::string_view whole(source);
    std::string_view shared = whole.substr(2, 3);    // view vào source

    source[2] = 'X';

    std::cout << copied << '\n'; // cde
    std::cout << shared << '\n'; // Xde
}
```

`std::string::substr` trả về một giá trị `std::string` độc lập, còn `std::string_view::substr` trả về một **view không sở hữu** trên vùng dữ liệu đã tham chiếu. View được tạo trong ví dụ hợp lệ vì `source` vẫn sống và thao tác chỉ thay một phần tử bên trong, không tái cấp phát bộ nhớ.

**Rủi ro cần tránh:**

```cpp
#include <string>
#include <string_view>

std::string_view unsafe_view() {
    std::string local = "hello";
    return std::string_view(local); // SAI: local bị hủy khi hàm trả về
}
```

Giá trị trả về chỉ còn địa chỉ tới vùng nhớ không còn hợp lệ. Không đọc từ view này. Nếu hàm cần trả về văn bản có vòng đời độc lập, hãy trả về `std::string` hoặc thiết kế rõ cơ chế chủ sở hữu sống lâu hơn view.

Đồng thời, `std::string` có thể cấp phát lại khi `append`/`reserve` làm tăng dung lượng; các view và con trỏ đang trỏ vào dữ liệu cũ cần được coi là có nguy cơ mất hiệu lực theo quy tắc của API.

## 7. Ví dụ Rust: `&str` mượn dữ liệu, `String` sở hữu

Rust biểu diễn một chuỗi Unicode hợp lệ bằng `String` sở hữu và kiểu lát cắt `&str`. Một lát cắt `&str` mượn dữ liệu nguồn; bộ kiểm tra borrow và lifetime ngăn nhiều trường hợp sử dụng sau khi nguồn bị hủy.

```rust
fn main() {
    let source = String::from("Aé🙂");

    // Chỉ số lát cắt &str là offset byte UTF-8.
    let view: &str = source.get(1..3).unwrap(); // "é"
    let copied: String = view.to_owned();       // tạo chuỗi sở hữu

    assert_eq!(view, "é");
    assert_eq!(copied, "é");

    // 1..2 cắt giữa hai byte mã hóa của "é".
    assert!(source.get(1..2).is_none());
}
```

Điểm quan trọng:

- `source.len()` trả số **byte UTF-8**, không phải số code point hay grapheme.
- `get(1..3)` trả `Option<&str>`: `None` nếu chỉ số vượt giới hạn hoặc không nằm trên ranh giới UTF-8 hợp lệ.
- `view.to_owned()` tạo `String` sở hữu nội dung, phù hợp để giữ sau khi không còn muốn phụ thuộc nguồn.
- Borrow checker giúp bảo vệ vòng đời tham chiếu trong Rust an toàn; vì thế nhiều sửa đổi nguồn bị cấm khi còn một borrow được sử dụng.

Rust không tự động coi một `&str` là “một grapheme cluster”; phân đoạn theo grapheme cần cơ chế/thư viện tương ứng.

## 8. Ví dụ JavaScript: `subarray` chia sẻ còn `slice` sao chép trên typed array

Trong JavaScript, hành vi chia sẻ của **typed array** được quy định rõ:

```javascript
const source = new Uint8Array([65, 66, 67, 68]); // A B C D

const view = source.subarray(1, 3);
const copy = source.slice(1, 3);

source[1] = 90; // đổi B thành Z

console.log([...view]); // [90, 67]  : view thấy nội dung mới
console.log([...copy]); // [66, 67]  : bản sao giữ nội dung cũ
```

`subarray` là view chia sẻ vùng `ArrayBuffer` bên dưới; `slice` của `Uint8Array` tạo typed array mới có phần tử sao chép. Các chỉ số trong ví dụ đều theo **phần tử byte**, không phải ký tự Unicode.

Với `String.prototype.substring` hoặc `String.prototype.slice`, ngữ nghĩa kết quả là một chuỗi giá trị bất biến, nhưng **mức độ chia sẻ vùng lưu trữ bên trong là chi tiết của JavaScript engine**, không phải hợp đồng để ứng dụng dựa vào. Vì vậy không thể khẳng định “JavaScript substring luôn copy” hay “luôn zero-copy” cho mọi phiên bản engine.

Tương tự, Java `String.substring` trả một `String` bất biến; cách cấp phát/bố trí nội bộ có thể thay đổi giữa các triển khai và phiên bản. Muốn đánh giá memory retention của một runtime cụ thể cần đọc tài liệu kỹ thuật tương ứng hoặc đo trên runtime đó.

## 9. Tác động của tính khả biến, aliasing và đồng thời

### 9.1. Hai view cùng nhìn một vùng nguồn

Giả sử `v1` và `v2` đều chỉ đến các vùng chồng lấn của một `bytearray` khả biến:

```text
Nguồn:  [a][b][c][d][e][f]
v1:       [b][c][d]
v2:          [c][d][e]
                    ^
                  chồng lấn
```

Thay byte `c` qua `v1` cũng có thể làm thay đổi nội dung đọc qua `v2`. Đây là **aliasing**, không phải lỗi của view: đó là hệ quả được mong đợi khi hai tham chiếu cùng quan sát trạng thái khả biến.

Tuy nhiên, nếu API trả về chuỗi con mà người gọi kỳ vọng là **snapshot độc lập**, chia sẻ nguồn khả biến mà không có hợp đồng rõ ràng sẽ làm vi phạm kỳ vọng. Cần chọn copy, chỉ cho phép nguồn bất biến, hoặc dùng **copy-on-write** để bảo đảm nội dung đã công bố không thay đổi.

### 9.2. Copy-on-write là một lựa chọn thứ ba về triển khai

Trong cơ chế **copy-on-write (COW)**, nhiều giá trị ban đầu có thể cùng chia sẻ vùng lưu trữ. Khi có yêu cầu sửa mà vùng đó đang được chia sẻ, hệ thống tạo bản sao trước khi sửa.

```text
Ban đầu:
  A ─┐
     ├──> ["abc"]    (chia sẻ)
  B ─┘

B được sửa:
  A ────> ["abc"]
  B ────> ["aXc"]    (tạo bản sao khi cần)
```

COW có thể tiết kiệm sao chép nếu chủ yếu đọc; nhưng nó làm chi phí một lần ghi khó dự đoán hơn, đòi hỏi quản lý sở hữu/đếm tham chiếu và xử lý đồng thời đúng cách. Nó không mặc nhiên là chiến lược của mọi `String` hoặc `substring`.

### 9.3. Chia sẻ nguồn khi có nhiều luồng đọc/ghi

Khi nguồn bất biến, nhiều view chỉ đọc thường dễ chia sẻ an toàn về mặt nội dung. Khi nguồn khả biến, hệ thống phải quy định đồng bộ và nhất quán dữ liệu. Một phép sửa đồng thời với đọc có thể tạo lỗi dữ liệu hoặc data race, tùy ngôn ngữ.

Đặc biệt không nên dùng **view tới vùng khả biến** làm khóa bảng băm khi hash và equality tính theo nội dung: sau khi sửa nguồn, khóa có thể không tìm lại được đúng cách. Chọn bản sao bất biến hoặc bảo đảm nội dung tham gia hash không thay đổi trong suốt thời gian khóa tồn tại.

## 10. Bộ nhớ giữ lại: nhìn vào bộ nhớ sống, không chỉ số byte được cấp phát mới

Giả sử dữ liệu đầu vào là một vùng \(R\) byte, ứng dụng trích \(q\) đoạn con, mỗi đoạn dài \(k\) byte. Ta xét hai phương án:

**Phương án copy:** chi phí tạo dữ liệu độc lập khoảng \(O(qk)\) bộ nhớ; mỗi chuỗi con có metadata riêng. Nếu không còn ai tham chiếu vùng gốc, nó có thể được giải phóng. Các công thức giả định sao chép đầy đủ và chưa tính overhead đối tượng/allocator.

**Phương án view sở hữu tham chiếu:** metadata mới khoảng \(O(q)\), nhưng vùng nguồn \(R\) byte có thể phải được giữ sống. Nếu các view đều trỏ vào **cùng** nguồn, vùng nguồn chỉ cần một bản, song toàn bộ vùng đó vẫn có thể tồn tại cho tới khi view cuối cùng được giải phóng.

Một ví dụ:

| Dữ liệu | Copy | View sở hữu nguồn |
|---|---:|---:|
| Nguồn ban đầu | 100 MB | 100 MB |
| Một token 20 byte | Cần ~20 byte dữ liệu mới | Không cần copy nội dung |
| Sau khi xử lý xong nguồn | Có thể giải phóng 100 MB | Có thể vẫn giữ 100 MB |
| Chi phí đọc lại token | Đọc 20 byte của bản sao | Đọc 20 byte tại offset nguồn |

Nếu giữ **1.000 token dài 20 byte** từ cùng một nguồn 100 MB, tổng dữ liệu token được sao chép chỉ khoảng 20 KB. Dùng view vẫn có thể giữ 100 MB nguồn, dù từng view rất nhỏ. Ngược lại, khi các view chỉ được dùng tạm trong lúc nguồn **đằng nào cũng phải sống**, chúng tránh được nhiều lần sao chép và thường hiệu quả.

### Vì sao không thể quyết định chỉ dựa trên \(O(1)\) và \(O(k)\)?

Độ phức tạp cục bộ của `substring` đo công tại thời điểm tạo đoạn. Quyết định thiết kế còn phụ thuộc **thời gian sống** của kết quả và dữ liệu nguồn:

\[
\text{Chi phí thực tế}
=
\text{chi phí tạo}
+\text{chi phí sử dụng}
+\text{chi phí duy trì bộ nhớ sống}.
\]

Biểu thức là khung suy luận, không phải công thức có cùng đơn vị đo: thời gian CPU, số byte bộ nhớ và thời gian lưu giữ cần được đánh giá theo những thước đo riêng khi tối ưu hệ thống.

## 11. Unicode: cắt đúng ranh giới quan trọng hơn copy hay view

Một chuỗi văn bản có ít nhất các mức độ dài cần phân biệt: **byte**, **code unit**, **Unicode code point** và **grapheme cluster**. View theo byte không tự động hiểu ranh giới ký tự.

Ví dụ `Aé🙂` trong UTF-8 gồm các byte:

```text
byte offset:  0    1    2    3    4    5    6
byte (hex):  41   C3   A9   F0   9F   99   82
kí hiệu:     A    └─é─┘   └────🙂──────┘
```

Một lát cắt `[1:3)` tạo đủ byte cho `é`. Nhưng `[1:2)` lấy riêng byte `C3`, không phải chuỗi UTF-8 hợp lệ để giải mã độc lập.

**Ngay cả khi cắt theo ranh giới code point, chưa chắc cắt đúng ký tự hiển thị.** Chẳng hạn `"e\u0301"` gồm code point `e` và dấu sắc kết hợp, thường là **một grapheme cluster**. Cắt giữa hai code point không làm hỏng UTF-8, nhưng tách dấu khỏi chữ.

Khi thiết kế API:

1. **Xác định kiểu dữ liệu:** đoạn nhị phân hay văn bản Unicode?
2. **Xác định đơn vị chỉ số:** byte, UTF-16 code unit, code point hay grapheme?
3. **Kiểm tra ranh giới:** với UTF-8/UTF-16 hợp lệ, không tách giữa code point; với thao tác giao diện, cân nhắc ranh giới grapheme.
4. **Xác định quyền sở hữu:** copy, view sở hữu nguồn hay view mượn?
5. **Xác định vòng đời:** kết quả sống bao lâu so với dữ liệu gốc?

Nếu mã hóa có độ rộng thay đổi, việc **tìm offset byte của code point thứ \(i\)** có thể tốn \(O(i)\) khi chưa có bảng chỉ mục. Không nên gán toàn bộ thao tác lấy chuỗi con là \(O(1)\) chỉ vì tạo view từ hai offset đã biết là \(O(1)\); chi phí tìm offset cũng là phần của yêu cầu người dùng.

## 12. Tình huống thiết kế: phân tích log và giữ token lâu dài

Một dịch vụ đọc lần lượt các bản ghi log lớn. Mỗi bản ghi có các trường phân tách bằng dấu cách hoặc dấu phẩy. Sau khi đọc, dịch vụ gửi nội dung từng trường vào bộ xử lý và giữ lại một số mã định danh để tra cứu.

Có thể phân tách xử lý thành hai giai đoạn.

**Giai đoạn phân tích tạm thời:** Dữ liệu nguồn vẫn còn cần dùng để quét các trường khác. Các view theo offset thường phù hợp để tránh cấp phát cho mọi token. Cần bảo đảm mọi view hợp lệ trong lúc xử lý và parser tôn trọng encoding.

**Giai đoạn lưu giữ dài hạn:** Một số mã định danh phải sống sau khi nguồn được loại bỏ. Nếu mỗi mã rất nhỏ so với bản ghi hoặc vùng đọc, **sao chép riêng những mã cần giữ** giúp giải phóng vùng lớn. Có thể dùng chuỗi bất biến làm khóa hoặc snapshot cho bảng băm.

Thiết kế minh họa:

```text
[buffer đọc log lớn]
        |
        v
[parser tạo view (offset, length)]
        |
        +--> phân tích tạm thời: đọc view, không copy
        |
        +--> cần giữ mã lâu: copy mã -> kho dữ liệu bền vững
        |
        v
[hoàn tất bản ghi -> có thể giải phóng buffer nguồn]
```

Nếu các token được giữ lại luôn chiếm gần như toàn bộ dữ liệu nguồn, sao chép tất cả sẽ làm tăng tổng công việc mà lợi ích giải phóng nguồn ít rõ hơn. Khi ấy lưu một vùng bất biến dùng chung, hoặc lưu chỉ mục vào một cấu trúc đã được quản lý vòng đời, có thể phù hợp hơn.

## 13. Checklist để quyết định copy hay share

| Câu hỏi | Nếu câu trả lời là… | Gợi ý |
|---|---|---|
| Đoạn con có tồn tại lâu hơn nguồn không? | Có | Copy hoặc chuyển rõ quyền sở hữu |
| Nguồn là vùng rất lớn, đoạn con rất nhỏ? | Có | Cân nhắc copy để tránh giữ vùng nguồn quá lâu |
| Nguồn chắc chắn còn sống suốt lúc dùng đoạn? | Có | View giúp tránh cấp phát và sao chép |
| Nguồn có thể bị sửa hoặc cấp phát lại? | Có | Copy hoặc quản lý chặt hiệu lực view |
| Đoạn con dùng làm khóa băm/snapshot? | Có | Ưu tiên giá trị bất biến với nội dung ổn định |
| Cần xử lý hàng triệu token ngắn trong một lượt quét? | Có | View thường giảm lượng cấp phát trung gian |
| Đoạn con từ rope/piece table? | Có | Xem chi phí tách nút/mảnh và giữ cây nguồn |
| API chỉ mô tả nội dung `substring`, không nêu storage? | Có | Không dựa vào giả định copy/share của implementation |

Tối ưu tốt nhất có thể là **dùng view trong quá trình xử lý ngắn, copy tại ranh giới sở hữu**. Một quyết định ở điểm chuyển vòng đời thường dễ lý giải và dễ kiểm thử hơn việc cố chọn một cơ chế cho mọi chuỗi con.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một view có `offset` và `length`, tạo trong \(O(1)\). Tại sao nó vẫn có thể làm chương trình sử dụng thêm hàng chục MB bộ nhớ sống?

**Đáp án:** View sở hữu tham chiếu có thể giữ cả vùng nguồn lớn chưa được giải phóng, mặc dù bản thân metadata của view chỉ chiếm bộ nhớ hằng số.

**Câu 2.** Trong C++, tại sao không được trả về `std::string_view` của một `std::string` cục bộ sẽ bị hủy khi hàm kết thúc?

**Đáp án:** View không sở hữu vùng nhớ. Khi biến cục bộ bị hủy, view có thể trỏ vào bộ nhớ không còn hợp lệ; đọc từ đó dẫn đến hành vi không xác định.

**Câu 3.** Hai byte slice cùng trỏ vào vùng khả biến và có đoạn chồng lấn. Điều gì có thể xảy ra sau khi sửa một byte trong đoạn chồng lấn?

**Đáp án:** Cả hai view có thể quan sát nội dung mới, vì chúng cùng tham chiếu tới một vùng lưu trữ. Bản copy độc lập không thay đổi theo sửa đổi đó.

**Câu 4.** Với một vùng log 100 MB và 1.000 token dài 20 byte cần giữ lâu dài, vì sao copy token có thể tiết kiệm RAM hơn view?

**Đáp án:** Dữ liệu các token copy khoảng 20 KB, còn view sở hữu nguồn có thể giữ cả 100 MB. Chênh lệch phải cộng thêm overhead đối tượng và cấu trúc lưu token, nhưng bậc kích thước vẫn rất khác nhau.

**Câu 5.** Nếu đã có đúng hai byte offset hợp lệ, tạo view của một buffer UTF-8 liên tiếp thường tốn bao nhiêu thời gian? Nếu đầu vào chỉ cho “grapheme thứ 100” thì sao?

**Đáp án:** Tạo view từ hai offset đã biết thường \(O(1)\). Tìm offset của grapheme thứ 100 có thể yêu cầu phân đoạn văn bản từ một ranh giới đã biết hoặc tra chỉ mục bổ trợ; chi phí này phải được tính riêng.

**Câu 6.** Tại sao `Uint8Array.subarray` và `Uint8Array.slice` trong JavaScript có hành vi quan sát thay đổi khác nhau?

**Đáp án:** `subarray` tạo view chia sẻ vùng `ArrayBuffer`, còn `slice` tạo typed array mới với dữ liệu sao chép. Sửa nguồn làm view thấy dữ liệu mới, còn bản sao giữ giá trị cũ.

## Ghi nhớ

- **Substring là nội dung logic của một đoạn liên tiếp**. Nó có thể được hiện thực bằng **copy**, **view chia sẻ vùng lưu trữ** hoặc cấu trúc phân mảnh.
- **Copy:** thường \(O(k)\) thời gian và \(O(k)\) bộ nhớ dữ liệu mới; phù hợp khi cần kết quả độc lập, nguồn khả biến hoặc đoạn con sống lâu hơn nguồn.
- **View:** thường \(O(1)\) để tạo metadata khi offset đã biết; có thể nhanh và ít cấp phát, nhưng phải tính **vòng đời nguồn**, **memory retention**, aliasing và khả năng mất hiệu lực.
- Phân biệt view **giữ tham chiếu sở hữu** với view **không sở hữu**; một loại có thể giữ vùng nguồn lớn sống quá lâu, loại kia có thể tạo dangling reference nếu nguồn chết trước.
- Copy hoặc view đều phải tôn trọng **đơn vị chỉ số và ranh giới Unicode**. Đọc byte, code unit, code point và grapheme là các thao tác khác nhau.
- Chọn giải pháp theo **tỷ lệ kích thước đoạn/nguồn**, **tần suất truy cập**, **khả năng sửa nguồn**, **vòng đời dữ liệu** và **chi phí thời gian/bộ nhớ** của ứng dụng.
