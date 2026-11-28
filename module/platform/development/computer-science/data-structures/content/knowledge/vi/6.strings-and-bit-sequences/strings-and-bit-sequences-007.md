# Kết thúc bằng ký hiệu canh gác so với lưu độ dài tường minh

Một vùng nhớ chứa các byte `41 00 42` (hệ 16). Nếu đọc theo quy ước chuỗi C kết thúc ở byte NUL (`00`), nội dung được hiểu là `"A"`. Nhưng nếu đọc theo cặp **địa chỉ và độ dài 3 byte**, nội dung là ba byte `'A'`, `0` và `'B'`. Cùng một vùng dữ liệu, hai quy ước biểu diễn tạo ra hai kết quả khác nhau.

Trong chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài này giúp hiểu sự khác biệt giữa biểu diễn dãy bằng **ký hiệu canh gác/kết thúc (sentinel-terminated)** và bằng **độ dài tường minh (explicit length)**. Trọng tâm là bất biến dữ liệu, thao tác truy cập và nối, độ phức tạp thời gian/bộ nhớ, xử lý byte NUL, ranh giới Unicode và lựa chọn cấu trúc phù hợp với bài toán.

## 1. Hai cách mô tả điểm kết thúc một dãy

Một dãy có thứ tự cần biết đâu là phần tử đầu và đâu là điểm kết thúc. Hai thiết kế phổ biến là:

**Cách A — Ký hiệu canh gác:** Chọn một giá trị đặc biệt `T` làm dấu kết thúc. Khi duyệt từ đầu, thuật toán dừng tại lần xuất hiện đầu tiên của `T`. Giá trị này thường **không** được dùng như phần tử dữ liệu bình thường nếu không có cơ chế thoát (escape) hoặc mã hóa bổ sung.

**Cách B — Độ dài tường minh:** Lưu số phần tử hợp lệ `n` bên cạnh vùng dữ liệu. Khi duyệt, đọc đúng `n` phần tử; nội dung có thể chứa bất kỳ giá trị nào của miền dữ liệu nếu biểu diễn cho phép.

Ví dụ với một chuỗi gồm `A`, `B`, `C`:

```text
Sentinel-terminated (NUL):
index:     0    1    2    3    4
buffer:   [A]  [B]  [C] [\0]  [?]
             phần dữ liệu  kết thúc

Explicit length:
length = 3
index:     0    1    2    3    4
buffer:   [A]  [B]  [C]  [?]  [?]
          └── 3 phần tử ──┘
```

Ký hiệu `?` chỉ vùng chưa thuộc nội dung logic; nó không phải ký tự đặc biệt cần tồn tại trong bộ nhớ.

Hai thiết kế có thể **kết hợp**: lưu cả `length` lẫn byte `\0` để vừa truy vấn độ dài nhanh, vừa tương thích với API C. Điều cần tránh là sử dụng các quy ước không nhất quán trên cùng một dữ liệu.

## 2. Bất biến của biểu diễn dùng sentinel

Cho mảng `a` có sức chứa `C` phần tử và dấu kết thúc `T`. Một dãy logic dài `n` đáp ứng:

\[
0 \le n < C,\qquad a[n] = T,\qquad
a[i] \ne T\ \text{với mọi}\ 0 \le i < n.
\]

Điểm quan trọng là điều kiện **`n < C`**: bộ đệm phải đủ chứa `n` phần tử nội dung **và thêm một phần tử kết thúc**.

Nếu `T = 0` trong mảng byte, ta được quy ước chuỗi C kết thúc bằng NUL. Ví dụ:

```c
char text[6] = "hello";
/*
  text[0..4] = 'h', 'e', 'l', 'l', 'o'
  text[5]    = '\0'
*/
```

Chuỗi này có:

- **Độ dài logic:** 5 ký tự byte trước NUL.
- **Sức chứa mảng:** 6 byte.
- **Dấu kết thúc:** 1 byte NUL ở vị trí chỉ số 5.

Mảng `char text[5] = {'h', 'e', 'l', 'l', 'o'};` chứa đủ năm byte dữ liệu nhưng **không có NUL kết thúc**. Không được truyền mảng đó vào `strlen` hoặc hàm yêu cầu C string nếu chưa bảo đảm tồn tại NUL trong vùng có thể đọc.

### Chuỗi rỗng

Chuỗi sentinel rỗng vẫn cần một vị trí chứa dấu kết thúc:

```text
buffer: [\0] [?] [?]
length logic = 0
```

Trong khi đó, dãy có độ dài tường minh có thể mô tả dữ liệu rỗng chỉ bằng `length = 0`, miễn mọi API tuân thủ hợp đồng về con trỏ/vùng dữ liệu khi độ dài bằng 0.

### Một sentinel không thể tùy ý xuất hiện trong payload

Nếu `T` xuất hiện trong dữ liệu, thuật toán dừng quá sớm. Chẳng hạn:

```text
buffer: ['A'] [0x00] ['B'] [0x00]
                  ^
                dừng ở đây
```

Theo hợp đồng chuỗi C, dữ liệu logic kết thúc ngay trước byte NUL đầu tiên. Phần `'B'` phía sau không thuộc cùng C string. Nếu cần biểu diễn cả `A`, NUL và `B` như nội dung, ta phải chọn một quy ước khác hoặc cơ chế mã hóa/thoát ký hiệu.

## 3. Bất biến của biểu diễn lưu độ dài

Với bộ đệm `a` có `capacity = C` và số phần tử nội dung `length = n`, bất biến cơ bản là:

\[
0 \le n \le C.
\]

Phần tử hợp lệ nằm trong khoảng nửa mở `[0, n)`. Các vị trí `[n, C)` không thuộc nội dung, bất kể hiện đang chứa giá trị gì.

```text
length = 3, capacity = 6
buffer: [A] [0] [B] [ ] [ ] [ ]
        └─ dữ liệu ─┘
```

Ở đây byte `0` giữa `A` và `B` là **dữ liệu hợp lệ** vì điểm kết thúc được xác định bằng `length = 3`. Nếu API yêu cầu byte hoặc ký tự tùy ý, biểu diễn này thuận tiện hơn dùng ký hiệu canh gác dành riêng.

Trong hệ thống thực tế có ít nhất hai biến thể:

**Pointer + length:** Một descriptor hoặc view chứa tham chiếu tới dữ liệu và số phần tử. Các byte dữ liệu có thể nằm ở vùng sở hữu bên ngoài. Ví dụ biểu diễn ý tưởng là `(data, length)`.

**Length prefix:** Số phần tử được ghi **ngay trước payload** trong định dạng lưu trữ hoặc giao thức. Ví dụ một gói nhỏ giả định trường chiều dài một byte:

```text
03 | 41 00 42
│    └─── 3 byte payload ───┘
└── length = 3
```

Ví dụ trên chỉ dùng một byte độ dài vì `3` vừa trong phạm vi; giao thức thật phải công bố kích thước trường, thứ tự byte (endianness) nếu có nhiều byte, giá trị tối đa và quy định xử lý thông điệp không hoàn chỉnh.

**Không nên nhầm `length` với `capacity`.** Một builder có thể lưu cả hai: `length` cho nội dung hiện hữu và `capacity` cho sức chứa cấp phát. Nếu muốn tiếp xúc với API C, builder còn có thể duy trì byte `\0` ở vị trí `buffer[length]`, khi đó phải bảo đảm `capacity \ge length + 1`.

## 4. So sánh độ phức tạp thao tác

Xét dãy dài `n` đơn vị được lưu liên tiếp và hợp lệ. Với dạng sentinel, giả sử thuật toán chỉ nhận con trỏ tới phần tử đầu, không có metadata độ dài đã lưu riêng. Với dạng explicit length, `n` đã có sẵn trong descriptor.

| Thao tác | Sentinel không lưu độ dài | Lưu độ dài tường minh |
|---|---|---|
| Xác định số phần tử `n` | Quét tới `T`: `O(n)` | Đọc metadata: `O(1)` |
| Kiểm tra rỗng | So sánh phần tử đầu với `T`: `O(1)` | Kiểm tra `length == 0`: `O(1)` |
| Duyệt toàn dãy | `O(n)` | `O(n)` |
| Đọc phần tử tại offset **đã biết và hợp lệ** | `O(1)` ở mảng liên tiếp | `O(1)` ở mảng liên tiếp |
| Kiểm tra chỉ số `i` có nằm trong dãy không | Có thể phải quét tới `i` hoặc sentinel, tối đa `O(n)` | So sánh `i < length`: `O(1)` |
| Tìm phần tử đầu tiên có giá trị xác định | `O(n)` trong trường hợp xấu | `O(n)` trong trường hợp xấu |
| Nối khi **không biết vị trí cuối** | Tìm sentinel `O(n)`, rồi ghi đoạn mới | Có thể đến vị trí `length` ngay `O(1)` |
| Kiểm tra ranh giới khi nhận payload nhị phân | Phải tìm hoặc xử lý dấu kết thúc | Cần kiểm tra `length` trong vùng nhận |
| Bộ nhớ metadata cơ bản | Một ký hiệu kết thúc `T` ở cuối | Một trường độ dài có kích thước số nguyên |

Bảng nói về **chi phí tra cứu thông tin biên**. Thời gian sao chép, kiểm tra dung lượng hay cấp phát trong phép nối cần cộng riêng. Chẳng hạn, nếu dãy được lưu trong mảng động tăng theo hệ số, thêm `m` đơn vị cuối có thể tốn `O(m)` khấu hao **khi đã biết vị trí cuối**; nhưng việc gọi `strlen` để tìm cuối trước mỗi lần thêm lại có thể khiến tổng chi phí tăng nhiều.

Nếu hệ thống sentinel có **bộ đếm chiều dài được cache** hoặc con trỏ trỏ sẵn đến cuối, phép nối có thể nhanh tương tự biểu diễn explicit length. Vì vậy đặc tính quyết định độ phức tạp là **thông tin nào có sẵn** chứ không phải chỉ có hay không có byte `\0`.

### Một phép quét tuyến tính vẫn có thể rất nhanh

Hàm `strlen` trên C string hợp lệ có độ phức tạp `O(n)`, nhưng thư viện hệ thống có thể dùng các tối ưu đọc nhiều byte mỗi bước để giảm hằng số thời gian. Tối ưu triển khai **không thay đổi bậc độ phức tạp**: với đầu vào dài gấp nhiều lần, số byte cần kiểm tra vẫn tăng theo độ dài trong trường hợp tổng quát.

## 5. Ví dụ C: `strlen`, `sizeof` và byte NUL giữa dữ liệu

Đoạn mã sau là một chương trình C hoàn chỉnh:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    char text[] = {'A', '\0', 'B', '\0'};

    printf("strlen = %zu\n", strlen(text));  // 1
    printf("sizeof = %zu\n", sizeof text);   // 4

    // In ra cả byte dữ liệu sau NUL bằng độ dài tường minh.
    const size_t payload_length = 3;
    for (size_t i = 0; i < payload_length; ++i) {
        printf("%02X ", (unsigned int)(unsigned char) text[i]);
    }
    putchar('\n'); // 41 00 42

    return 0;
}
```

Có ba phép đếm khác nhau:

- `strlen(text)` trả số **byte trước NUL đầu tiên**: 1.
- `sizeof text` trả kích thước **toàn mảng** tính bằng byte: 4. Điều này đúng vì `text` là mảng tại chính phạm vi đó; khi truyền tới hàm nhận `char *`, `sizeof` trên con trỏ không còn là kích thước dữ liệu.
- `payload_length` được người viết chọn là 3 để biểu diễn toàn bộ dữ liệu `A 00 B`, không tính dấu NUL cuối trong ví dụ.

`strlen` **không** đếm Unicode code point, grapheme cluster hoặc số phần tử của một buffer nhị phân tùy ý. Với UTF-8, nếu dữ liệu chứa byte NUL biểu diễn `U+0000`, `strlen` cũng dừng tại đó.

### Không truyền vùng không có NUL vào `strlen`

`strlen(p)` yêu cầu `p` trỏ tới một chuỗi byte được kết thúc bằng NUL hợp lệ. Nếu không có NUL trước khi vùng nhớ hợp lệ kết thúc, hàm có thể tiếp tục đọc vượt giới hạn; trong C, đó là **hành vi không xác định**.

Ví dụ mảng sau **không phải C string hợp lệ**:

```c
char bytes[3] = {'A', 'B', 'C'};

// SAI nếu gọi strlen(bytes): không có '\0' trong mảng.
// Nhưng có thể xử lý bằng chiều dài rõ ràng là sizeof bytes.
```

Ngay cả khi một lần chạy tình cờ tìm thấy byte NUL ngoài mảng và cho ra con số “có vẻ đúng”, chương trình vẫn sai về mặt an toàn bộ nhớ.

## 6. Quét có giới hạn an toàn hơn khi nhận vùng byte ngoài

Khi đã biết sức chứa vùng dữ liệu nhưng không chắc có sentinel, có thể dùng **tìm kiếm có giới hạn** thay vì quét vô hạn.

Ví dụ `memchr` trong C tìm byte NUL tối đa `capacity` byte:

```c
#include <stddef.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    const unsigned char data[] = {'A', 'B', 'C'};
    const size_t capacity = sizeof data;

    const unsigned char *end =
        memchr(data, '\0', capacity);

    if (end == NULL) {
        puts("Khong co NUL trong vung duoc cap");
    } else {
        size_t length = (size_t)(end - data);
        printf("length = %zu\n", length);
    }

    return 0;
}
```

Ở đây không có NUL nên chương trình phát hiện được việc vùng dữ liệu **không đáp ứng quy ước kết thúc**. `memchr` hoạt động trên dữ liệu dạng byte có giới hạn, không yêu cầu NUL phải tồn tại.

Thư viện một số hệ thống có `strnlen` để giới hạn số byte quét, nhưng tính sẵn có phụ thuộc tiêu chuẩn/thư viện. `memchr` là cách minh họa dựa trên API chuẩn C khi đã có con trỏ và giới hạn dung lượng hợp lệ.

**Phải biết giới hạn vùng có thể đọc.** Dùng một con số giới hạn tùy ý lớn hơn vùng thực sự được cấp phát cũng có thể dẫn tới đọc ngoài biên. Cần kiểm tra tính hợp lệ của `data` và `capacity` theo hợp đồng nơi cấp dữ liệu.

## 7. Chi phí nối nhiều lần: sentinel và bộ đệm tăng trưởng

Xét việc thêm `k` đoạn có tổng độ dài `N`. Với dạng sentinel, một cách cài đặt kém hiệu quả là mỗi lần tìm lại byte NUL cuối cùng rồi mới nối đoạn tiếp theo.

```text
append 1: tìm điểm cuối của kết quả hiện có
append 2: quét lại từ đầu tới NUL
append 3: lại quét toàn bộ tiền tố
...
```

Nếu mỗi đoạn thêm có độ dài cố định, tổng số byte được quét tìm NUL có thể là:

\[
0 + m + 2m + \cdots + (k-1)m
= \frac{mk(k-1)}{2} = \Theta(mk^2).
\]

Với `m = Θ(1)` và `N = mk`, đó là `Θ(N²)` **chỉ riêng công tìm điểm cuối**. Nếu còn cần cấp phát/copy vùng nhớ, tổng chi phí có thể cao hơn về hằng số.

Cách cải thiện là **lưu vị trí cuối hoặc lưu độ dài**:

```text
buffer, length, capacity
    |
append(chunk of m units):
    ensure_capacity(length + m + 1)  // +1 nếu cần sentinel
    copy chunk vào buffer[length: length+m]
    length += m
    buffer[length] = '\0'
```

Việc duy trì `buffer[length] = '\0'` sau mỗi thao tác bảo đảm dữ liệu vẫn dùng được với các API C (miễn nội dung không chứa NUL ở giữa). Lưu `length` giúp không phải gọi `strlen` để tìm vị trí cuối.

Nếu `capacity` được mở rộng theo hệ số khi cần, thêm từng byte có chi phí **`O(1)` khấu hao** cho phần ghi và sao chép do cấp phát; thêm đoạn `m` đơn vị có chi phí khấu hao `O(m)`. Mỗi lần tăng dung lượng riêng lẻ vẫn có thể phải sao chép `O(n)` byte hiện hữu.

### Một thiết kế có cả độ dài và sentinel

```text
capacity = 8 (đơn vị byte)
length   = 4
buffer: [t][e][s][t][\0][?][?][?]
        └─ 4 byte ─┘ │
                     sentinel
```

Bất biến kết hợp:

\[
0 \le \text{length} < \text{capacity},\qquad
buffer[\text{length}] = 0.
\]

Thiết kế này hỗ trợ `O(1)` khi lấy độ dài đã lưu, đồng thời bảo đảm có NUL ở cuối. Tuy nhiên, nếu vùng dữ liệu chứa **NUL nằm giữa**, các hàm C string vẫn chỉ thấy phần trước NUL đầu tiên: lưu độ dài riêng không làm thay đổi hợp đồng của `strlen` hay `printf("%s", ...)`.

## 8. Unicode và đơn vị mã hóa của sentinel

Quy ước sentinel phải được xác định theo **đơn vị mã hóa**, không phải theo khái niệm “ký tự người dùng nhìn thấy”.

- Trong **UTF-8**, `U+0000` mã hóa bằng **một byte `00`**. Byte NUL có thể xuất hiện như dữ liệu Unicode hợp lệ nhưng C string sẽ coi đó là kết thúc.
- Trong **UTF-16**, giá trị code unit bằng 0 có thể dùng như marker kết thúc nếu API quy ước như vậy. Nó gồm **16 bit**, không thể dò đúng bằng cách tìm bất kỳ byte `00` đơn lẻ nào.
- Trong **UTF-32**, code unit 0 gồm **32 bit** và cũng khác byte NUL.
- Với các API sử dụng **độ dài tường minh**, dữ liệu Unicode có thể chứa `U+0000` như một code point bình thường nếu hợp đồng cho phép.

Ví dụ UTF-8:

```text
Văn bản logic:    A   U+0000   B
UTF-8 bytes:     41    00     42
code point count: 3
byte length:      3
C strlen:         1
```

Trên văn bản tiếng Việt hoặc emoji, `strlen` đếm byte **trước NUL**, không đếm ký tự:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    // Ghi trực tiếp byte để ví dụ không phụ thuộc mã hóa source file.
    const char text[] = {(char)0xC3, (char)0xA9, '\0'}; // UTF-8 của "é"
    printf("%zu\n", strlen(text));  // 2 byte
    return 0;
}
```

`"é"` thường là **một Unicode code point** và một grapheme cluster, nhưng gồm hai byte UTF-8. Tách biệt ba số đếm này là yêu cầu bắt buộc khi thiết kế cấu trúc lưu chuỗi quốc tế.

**Cẩn thận với số byte zero trong UTF-16/UTF-32.** Chẳng hạn nhiều code unit UTF-16 chứa một byte `00` mà bản thân code unit không phải `U+0000`. Quét từng byte và dừng ở `00` sẽ sai; phải dùng đúng đơn vị mã và byte order mà biểu diễn quy định.

## 9. Giao thức truyền dữ liệu: sentinel, delimiter và length prefix

Để nhận nhiều bản tin qua một dòng byte liên tục, chương trình cần biết bản tin hiện tại kết thúc ở đâu. Những cách phổ biến gồm:

### 9.1. Ký hiệu/delimiter kết thúc

Ví dụ thông điệp kết thúc bằng xuống dòng:

```text
HELLO\nWORLD\n
```

Ưu điểm: dễ đọc và triển khai với văn bản đơn giản; có thể đọc từng byte cho tới dấu kết thúc.

Giới hạn: nếu payload được phép chứa dấu xuống dòng, cần **escape**, quoting hoặc một cơ chế framing khác. Cùng nguyên lý đó, chuỗi C dựa vào NUL như byte kết thúc dành riêng.

### 9.2. Length prefix

Ví dụ với trường độ dài 1 byte (chỉ cho payload không vượt 255 byte):

```text
03 41 00 42 02 FF 01
│  └───3────┘ │  └─2─┘
│              └ length=2
└ length=3
```

Bộ đọc lấy `length` trước rồi lấy đúng số byte payload. Dữ liệu có thể chứa bất kỳ byte nào, kể cả `00` hoặc byte giống delimiter.

Trong giao thức thật, cần quy định: độ rộng trường length, endianness, có tính header trong length hay không, maximum size, xử lý đầu vào chưa đủ, giới hạn bộ nhớ và lỗi tràn số nguyên.

### 9.3. Không được tin giá trị độ dài từ đầu vào

Một length prefix tự nó **không bảo đảm an toàn**. Nếu bản tin báo độ dài rất lớn hoặc lớn hơn số byte còn lại, đọc theo độ dài mà không kiểm tra vẫn có thể truy cập ngoài vùng nhận hoặc cấp phát bộ nhớ quá mức.

Giả mã an toàn khi parse:

```text
parse_frame(bytes, cursor, limit):
    require cursor < limit
    length = read_length_prefix_bounded(bytes, cursor, limit)
    cursor = cursor_after_header

    require length <= configured_max_payload
    require length <= limit - cursor    // tránh cộng tràn số
    payload = bytes[cursor : cursor + length]
    return payload
```

Đây là giả mã, không phải một định dạng giao thức hoàn chỉnh. Điều kiện `length <= limit - cursor` yêu cầu `cursor <= limit` trước đó; sử dụng phép trừ trong phạm vi đã kiểm tra giúp tránh trường hợp cộng `cursor + length` bị tràn.

### 9.4. Dấu kết thúc không thay cho ranh giới bản tin ở mọi môi trường

Với TCP, dữ liệu là **dòng byte**, không có bảo đảm một lời gọi `recv` tương ứng một thông điệp ứng dụng. Bộ đọc phải duy trì trạng thái qua nhiều lần nhận: quét tới delimiter hợp lệ hoặc đọc đủ payload theo length prefix. Trong các giao thức văn bản/nhị phân khác, các quy tắc framing cụ thể có thể khác nhau.

## 10. Ví dụ thực tế: C++ giữ NUL trong chuỗi có độ dài

`std::string` trong C++ cho phép lưu giá trị NUL ở giữa nội dung vì nó quản lý độ dài tường minh:

```cpp
#include <cstring>
#include <iostream>
#include <string>

int main() {
    std::string value("A\0B", 3);  // độ dài chỉ rõ: 3 byte

    std::cout << value.size() << '\n';        // 3
    std::cout << std::strlen(value.c_str()) << '\n'; // 1

    // Truy cập các byte theo size() sẽ thấy cả byte NUL giữa.
    for (unsigned char byte : value) {
        std::cout << static_cast<unsigned>(byte) << ' ';
    }
    std::cout << '\n'; // 65 0 66
}
```

`value.c_str()` có dấu kết thúc NUL để tương tác với API C. Nhưng `std::strlen(value.c_str())` chỉ tìm NUL **đầu tiên**, nên không thể đại diện cho toàn bộ nội dung `std::string` có NUL nội bộ.

Bài học về API: khi chuyển từ `(pointer, length)` sang giao diện chỉ nhận `const char *` theo quy ước C string, ta có thể **mất thông tin** về phần nội dung sau NUL đầu tiên. Nếu cần bảo toàn toàn bộ byte, phải truyền thêm `size()` tới API nhận độ dài.

### Python: byte sequence lưu NUL như dữ liệu

```python
data = b"A\x00B"

print(len(data))          # 3 byte
print(data[0])            # 65
print(data[1])            # 0
print(data[2])            # 66
print(data.find(b"\x00")) # 1, nhưng không phải điểm kết thúc của bytes

# Truyền qua API có hợp đồng C string có thể gặp kết quả khác
# nếu API đó tự tìm byte NUL đầu tiên.
```

Trong Python, `bytes` có độ dài được lưu trong kiểu đối tượng. NUL là một byte bình thường; chỉ khi **cố tình dùng quy ước sentinel** mới coi nó như dấu kết thúc.

## 11. Các lỗi lập trình dễ gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng `strlen` trên một mảng không có NUL | Có thể đọc vượt bộ nhớ hợp lệ | Giữ độ dài riêng hoặc tìm sentinel trong giới hạn vùng thật sự |
| Dùng `sizeof(pointer)` làm độ dài payload | Kích thước con trỏ khác kích thước dữ liệu mà nó trỏ tới | Truyền `length` hoặc metadata cùng con trỏ |
| Dành đúng `n` byte để chứa C string dài `n` | Thiếu 1 byte cho `\0` | Cấp phát ít nhất `n + 1` byte, kiểm tra tràn |
| Dùng `strncpy` và mặc định kết quả luôn có NUL | Có trường hợp `strncpy` không ghi terminator | Sử dụng API có hợp đồng rõ ràng và kiểm tra hậu điều kiện |
| Gọi `strlen` trước mỗi lần append | Quét lại các tiền tố, có thể gây chi phí `Θ(N²)` | Cache `length`, dùng builder hoặc pointer tới cuối |
| Dùng C string cho payload nhị phân có NUL | Bị cắt tại NUL đầu tiên | Dùng pointer + length hoặc length-prefix framing |
| Tin tuyệt đối độ dài nhận từ mạng | Có thể tràn số, đọc quá vùng hoặc cấp phát quá lớn | Giới hạn kích thước, kiểm tra số byte còn lại, chống tràn |
| Nhầm byte count với số ký tự Unicode | UTF-8 dùng số byte thay đổi cho mỗi code point | Đặt tên rõ đơn vị và dùng bộ đếm Unicode phù hợp |
| Quét byte `00` để tìm cuối chuỗi UTF-16 | Byte zero có thể chỉ là một phần của code unit khác 0 | Quét theo đúng code unit và endianness |
| Coi `capacity` là `length` | Đọc vùng dự phòng chưa thuộc dữ liệu logic | Duy trì bất biến `0 ≤ length ≤ capacity` |

### Một điểm riêng về kiểm tra độ dài và an toàn

Dữ liệu đến từ người dùng, mạng hoặc file có thể **không tuân thủ** những bất biến mà thuật toán nội bộ giả định. Trước khi chuyển vùng byte ngoài thành C string, cần xác định terminator nằm trong phạm vi cho phép. Trước khi chấp nhận explicit length, cần xác định độ dài không vượt buffer và các giới hạn tài nguyên. Hai cách đều cần xác thực biên; khác nhau ở cách phát hiện và biểu diễn điểm cuối.

## 12. Chọn cách biểu diễn theo bài toán

| Bài toán | Cách biểu diễn đáng cân nhắc | Lý do |
|---|---|---|
| Gọi API C truyền thống mong đợi `const char *` | NUL-terminated, có vùng NUL hợp lệ | Đúng hợp đồng hàm C |
| Xử lý byte nhị phân chứa mọi giá trị `00`–`FF` | Pointer + length | Không cần dành riêng một byte kết thúc |
| Đọc payload có kích thước truyền trước | Length prefix | Có thể đọc chính xác số byte ngay cả khi payload chứa sentinel |
| Parser văn bản dòng đơn giản, ký tự xuống dòng không được phép xuất hiện thô trong bản ghi | Delimiter/ký hiệu kết thúc | Dễ tìm và xử lý dòng |
| Xây chuỗi tăng dần nhiều lần | Builder lưu `length`, `capacity`, tùy cần thêm NUL | Tránh quét lại điểm cuối, tăng dung lượng khấu hao |
| Chuỗi Unicode dùng trong giao diện | Explicit length + xử lý mã hóa/grapheme | Phân biệt số byte, code point và ký tự hiển thị |
| Cấu trúc vừa cần `size()` nhanh vừa cần API C | Lưu metadata độ dài và NUL cuối | Kết hợp ưu điểm, phải duy trì hai bất biến |
| Lưu các bản ghi có giá trị delimiter tự nhiên trong payload | Length prefix hoặc escape rõ ràng | Tránh nhầm dữ liệu với dấu phân cách |

Không có một chiến lược luôn tốt nhất. Một sentinel có thể giúp tiết kiệm trường metadata trong biểu diễn đơn giản và thuận tiện cho nhiều API sẵn có. Độ dài tường minh giúp truy vấn nhanh và giữ dữ liệu tùy ý, nhưng phải quản lý và kiểm tra metadata. Nhiều hệ thống kết hợp chúng hoặc sử dụng framing riêng để đáp ứng các ràng buộc thực tế.

## 13. Bài tập tự kiểm tra

**Câu 1.** Cho mảng byte `{'X', 'Y', '\0', 'Z'}`. `strlen` (nếu dùng như C string hợp lệ) trả về bao nhiêu? Nếu mô tả bằng `length = 4` thì độ dài là bao nhiêu?

**Đáp án:** `strlen` trả 2 vì gặp NUL ở chỉ số 2; biểu diễn explicit length có độ dài 4 và chứa cả NUL cùng `'Z'` như dữ liệu.

**Câu 2.** Muốn lưu một C string dài 100 byte nội dung trong mảng chỉ chứa duy nhất chuỗi đó, phải dành ít nhất bao nhiêu byte?

**Đáp án:** Ít nhất **101 byte**, gồm 100 byte nội dung và một byte NUL kết thúc.

**Câu 3.** Tại sao biết con trỏ đầu chuỗi NUL-terminated nhưng không lưu `length` thì truy vấn độ dài thường là `O(n)`?

**Đáp án:** Phải duyệt từ phần tử đầu tới lần gặp sentinel đầu tiên; không có metadata để suy ngay vị trí cuối.

**Câu 4.** Một bộ đệm động đã lưu `length` và duy trì NUL ở cuối có cần gọi `strlen` trước mỗi lần thêm không?

**Đáp án:** Không. Có thể ghi trực tiếp tại `buffer[length]` sau khi kiểm tra/mở rộng `capacity`, cập nhật `length` rồi đặt NUL mới ở `buffer[length]`. Nhờ vậy tránh quét lại tiền tố.

**Câu 5.** Một gói có length prefix bằng 500 byte nhưng buffer nhận chỉ còn 100 byte. Có được đọc 500 byte không?

**Đáp án:** Không. Phải phát hiện gói chưa đủ hoặc sai định dạng; chỉ đọc khi có đủ dữ liệu và giá trị length không vượt giới hạn tài nguyên.

**Câu 6.** Vì sao `strlen` trên UTF-8 `"é"` trả số 2 dù người dùng thấy một chữ?

**Đáp án:** `é` mã hóa thành hai byte UTF-8 (`C3 A9`), còn `strlen` đếm byte trước NUL. Nó không phân tích code point hoặc grapheme cluster.

**Câu 7.** Một giao thức cần chứa dữ liệu tùy ý, kể cả byte `00`. Chọn một trong hai hướng: NUL-terminated không escape hay length-prefixed? Giải thích.

**Đáp án:** Chọn **length-prefixed** nếu chỉ xét hai lựa chọn đó, vì byte `00` được phép tồn tại trong payload mà không bị hiểu nhầm là kết thúc. Dùng delimiter cũng có thể được nếu giao thức định nghĩa cơ chế escape hợp lệ.

## Ghi nhớ

- **Sentinel-terminated** xác định điểm cuối bằng giá trị đặc biệt, thường cần **một ô kết thúc** và không thể chứa marker như dữ liệu thô nếu thiếu escape.
- **Explicit length** lưu số phần tử hợp lệ; truy vấn độ dài thường `O(1)` và có thể giữ byte NUL như một phần của dữ liệu.
- `strlen` quét tới byte NUL đầu tiên, tốn `O(n)` theo độ dài và yêu cầu vùng có terminator hợp lệ; thiếu NUL có thể gây đọc ngoài biên.
- Một builder có thể lưu **`length`, `capacity` và cả NUL ở cuối**, nhờ đó append nhanh mà vẫn tương thích API C; phải cập nhật các bất biến sau mỗi thao tác.
- Với giao thức hoặc bộ đệm từ nguồn ngoài, cần kiểm tra **kích thước thật, độ dài, giới hạn tài nguyên và ranh giới mã hóa**. Dùng đúng đơn vị byte/code unit/code point khi xử lý Unicode.
- Chọn cách biểu diễn dựa trên **miền giá trị dữ liệu**, **chi phí quét**, **API cần tương tác** và **yêu cầu an toàn bộ nhớ**.
