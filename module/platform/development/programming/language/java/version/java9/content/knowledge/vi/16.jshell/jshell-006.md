# Sửa, loại bỏ và thực thi lại snippet trong JShell

JShell quản lý từng đơn vị mã Java đã nhập như một snippet có ID riêng. Trong lúc thử nghiệm, bạn có thể cần chỉnh sửa nội dung, loại bỏ một khai báo không còn dùng hoặc chạy lại một đoạn mã để kiểm tra kết quả. Ba nhóm lệnh chính cho những thao tác này là `/edit`, `/drop` và các lệnh thực thi lại như `/!`, `/-n`, `/<id>`.

Các thao tác dưới đây thuộc JShell hiện hành trong JDK. JShell được giới thiệu từ Java 9 và tiếp tục được hỗ trợ trong các JDK mới.

## 1. Vòng đời của một snippet

Mỗi snippet được JShell gán một ID duy nhất trong phiên. Snippet có thể là import, khai báo biến, phương thức, kiểu, câu lệnh hoặc biểu thức.

Một snippet có thể ở những trạng thái khác nhau:

- **Đang hoạt động (active):** nội dung được đánh giá thành công và hiện có hiệu lực trong phiên.
- **Bị thay thế (overwritten):** một khai báo mới thay thế khai báo cũ có cùng tên.
- **Đã loại bỏ (dropped):** người dùng chủ động làm snippet mất hiệu lực bằng `/drop`.
- **Lỗi (rejected):** JShell không thể đánh giá nội dung; snippet lỗi vẫn có thể được xem trong danh sách đầy đủ.
- **Snippet khởi tạo (startup):** nội dung JShell tự nạp khi khởi chạy, thường có ID bắt đầu bằng `s`.

Dùng `/list` để xem snippet đang hoạt động và `/list -all` để xem cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. ID là căn cứ để chọn đúng snippet khi chỉnh sửa, loại bỏ hoặc chạy lại.

## 2. Chỉnh sửa snippet bằng /edit

Lệnh `/edit` mở snippet trong trình soạn thảo bên ngoài để bạn sửa mã nguồn. Khi rời editor, JShell đọc nội dung đã chỉnh sửa và đánh giá lại các snippet liên quan.

### 2.1. Cách mở snippet

| Lệnh | Công dụng |
|---|---|
| `/edit` | Mở các snippet đang hoạt động do người dùng nhập hoặc nạp bằng `/open`. |
| `/edit <name>` | Mở snippet theo tên; ưu tiên phiên bản đang hoạt động nếu có nhiều phiên bản. |
| `/edit <id>` | Mở snippet theo ID. |
| `/edit 3-7` | Mở một khoảng ID. |
| `/edit -start` | Mở các snippet khởi tạo; thay đổi chỉ áp dụng trong phiên hiện tại, không sửa cấu hình khởi tạo. |
| `/edit -all` | Mở tất cả snippet, kể cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. |

Trước khi chọn ID, hãy dùng `/list` để xem nội dung và số ID. Khi có nhiều khai báo cùng tên, có thể dùng `/list -all` để nhận diện đúng phiên bản.

### 2.2. Ví dụ chỉnh sửa một biến

Bắt đầu phiên JShell và nhập:

```
jshell> int limit = 10
limit ==> 10

jshell> /list
   1 : int limit = 10;
```

Nhập `/edit 1`. Trong editor, đổi dòng `int limit = 10;` thành `int limit = 12;`, lưu file tạm và đóng editor.

Sau khi JShell nhận nội dung mới, kiểm tra:

```
jshell> /vars
  int limit = 12
```

Trong lần chỉnh sửa này, JShell tạo snippet mới cho nội dung đã sửa. Ví dụ kiểm tra trên JDK 24 cho thấy `/list -all` giữ cả snippet cũ và snippet mới; `/vars` hiển thị giá trị đang hoạt động là `12`. Vì vậy, sau khi chỉnh sửa hãy dùng `/list`, `/list -all` và `/vars` để xác nhận nội dung cũng như trạng thái hiện tại.

### 2.3. Cấu hình trình soạn thảo

Lệnh `/set editor` chọn chương trình mà JShell gọi khi chạy `/edit`.

| Cú pháp | Ý nghĩa |
|---|---|
| `/set editor` | Hiển thị cấu hình editor hiện tại. |
| `/set editor <command>` | Chọn chương trình và các đối số để mở file tạm. |
| `/set editor -retain <command>` | Chọn editor và giữ cấu hình cho các lần chạy JShell tiếp theo. |
| `/set editor -wait <command>` | Dùng chế độ chờ, hữu ích khi editor mở cửa sổ riêng rồi trả quyền điều khiển ngay. |
| `/set editor -default` | Chọn editor đơn giản tích hợp trong JShell. |
| `/set editor -delete` | Xóa lựa chọn editor hiện tại và quay về cơ chế dò mặc định. |

Khi chưa cấu hình editor, JShell kiểm tra lần lượt các biến môi trường `JSHELLEDITOR`, `VISUAL` và `EDITOR`. Nếu không tìm thấy chương trình phù hợp, công cụ dùng editor đơn giản tích hợp sẵn.

Ví dụ cấu hình trên Windows PowerShell:

```
/set editor notepad
```

Ví dụ cấu hình trên môi trường có nano:

```
/set editor nano
```

Tên chương trình phải có trên máy và có thể được khởi chạy từ môi trường của JShell. Nếu editor khởi chạy một cửa sổ riêng rồi thoát ngay, tùy chọn `-wait` cho phép JShell yêu cầu xác nhận khi kết thúc edit mode. Dùng `/help /set editor` để xem cú pháp chi tiết của JDK đang chạy.

## 3. Loại bỏ snippet bằng /drop

Lệnh `/drop` làm một snippet mất hiệu lực trong phiên hiện tại. Nó không xóa vật lý lịch sử nhập mã; snippet đã drop vẫn có thể được xem bằng `/list -all`.

Cú pháp:

```
/drop <name>
/drop <id>
/drop <id-range>
```

Ví dụ:

```
jshell> int price = 100
price ==> 100

jshell> /list
   1 : int price = 100;

/drop price

/vars
```

Sau khi drop, biến `price` không còn trong danh sách biến đang hoạt động và không thể được dùng trong snippet mới. Nếu cần kiểm tra lịch sử, dùng `/list -all`.

Có thể drop theo ID thay vì tên:

```
/drop 4
/drop 4-7
```

Một lệnh có thể nhận tên, ID hoặc khoảng ID. ID giúp chọn đúng snippet khi có nhiều khai báo cùng tên.

### 3.1. Drop một snippet ảnh hưởng thế nào đến trạng thái?

Drop một khai báo biến, phương thức hoặc kiểu làm thành phần đó mất hiệu lực cho những lần nhập sau. Các snippet khác đã được đánh giá có thể vẫn giữ kết quả riêng của chúng.

Ví dụ, một biểu thức đã tính ra scratch variable có thể vẫn giữ giá trị ngay cả khi biến nguồn được drop. Tương tự, việc drop một phương thức không tự xóa các giá trị mà những lần gọi phương thức trước đó đã trả về.

Sau khi drop, nên kiểm tra:

- `/vars` để xem biến còn hoạt động.
- `/methods` để xem phương thức còn hiệu lực.
- `/types` để xem kiểu còn được khai báo.
- `/list -all` để xem snippet đã drop và các snippet khác.

Nếu cần chạy lại một khai báo đã drop, hãy xem nội dung bằng `/list -all`, rồi dùng `/<id>` để đánh giá lại snippet đó nếu nó còn có thể được tham chiếu trong phiên.

## 4. Thực thi lại snippet

JShell hỗ trợ nhiều cách chạy lại mã đã nhập. Lệnh thực thi lại đánh giá snippet thêm một lần và tạo một snippet mới với ID mới.

| Cú pháp | Ý nghĩa |
|---|---|
| `/!` | Chạy lại snippet gần nhất trong lịch sử. |
| `/-<n>` | Chạy lại snippet thứ n tính ngược từ lịch sử, ví dụ `/-4`. |
| `/<id>` | Chạy lại snippet theo ID. |
| `/<id-range>` | Chạy lại một khoảng ID, ví dụ `/3-7`. |
| `/history` | Hiển thị lịch sử lệnh và snippet đã nhập. |
| `Ctrl+R` | Tìm ngược trong lịch sử theo chuỗi ký tự. |

Cần phân biệt `/-n` và `/<id>`:

- `/-n` chọn snippet theo vị trí tương đối trong lịch sử.
- `/<id>` chọn snippet theo ID được JShell gán cho snippet đó.

Ví dụ, nếu snippet có ID `3`, `/3` chạy lại chính snippet đó. Nếu muốn chạy lại snippet thứ tư tính từ cuối lịch sử, dùng `/-4`; con số này không nhất thiết là ID `4`.

### 4.1. Chạy lại snippet gần nhất bằng /!

Ví dụ:

```
jshell> 2 + 2
$1 ==> 4

jshell> /!
2 + 2
$2 ==> 4
```

Lệnh `/!` đánh giá lại biểu thức gần nhất. Kết quả mới được lưu trong scratch variable mới, ở ví dụ trên là `$2`. Kết quả cũ `$1` vẫn thuộc trạng thái phiên nếu snippet tạo ra nó còn hoạt động.

### 4.2. Chạy lại theo ID hoặc khoảng ID

Nếu biết ID từ `/list`, có thể chạy lại một hoặc nhiều snippet:

```
/3
/3-5
```

Các snippet được xử lý theo ID. Dùng `/list` trước khi chạy để kiểm tra mã nguồn, đặc biệt khi khoảng ID có thể chứa câu lệnh gây tác dụng phụ.

### 4.3. Chạy lại theo vị trí lịch sử

Cú pháp `/-n` dùng vị trí tương đối:

```
/-1
/-4
```

`/-1` chạy lại snippet gần nhất được ghi nhận trong lịch sử; `/-4` chạy lại snippet thứ tư tính ngược theo quy tắc lịch sử của JShell. Dùng `/history` hoặc `Ctrl+R` để tìm đúng đoạn mã trước khi chạy lại.

## 5. Ví dụ hoàn chỉnh: chạy lại và drop một phương thức

Ví dụ này có bộ đếm tăng mỗi lần gọi phương thức. Nó cho thấy `/!` và `/3` chạy lại cùng một snippet, tạo kết quả mới; sau đó `/drop 2` loại bỏ phương thức `next`.

**EditDropRerunDemo.jsh**

```
int counter = 0;
int next() { return ++counter; }
next()
/!
/3
/vars
/list
/drop 2
/methods
/vars
/list -all
/exit
```

Chạy bằng JDK:

```
jshell --feedback concise EditDropRerunDemo.jsh
```

Output quan sát được trên JDK 24:

```
next()
next()
  int counter = 3
  int $3 = 1
  int $4 = 2
  int $5 = 3

   1 : int counter = 0;
   2 : int next() { return ++counter; }
   3 : next()
   4 : next()
   5 : next()
  int counter = 3
  int $3 = 1
  int $4 = 2
  int $5 = 3

  s1 : import java.io.*;
  s2 : import java.math.*;
  s3 : import java.net.*;
  s4 : import java.nio.file.*;
  s5 : import java.util.*;
  s6 : import java.util.concurrent.*;
  s7 : import java.util.function.*;
  s8 : import java.util.prefs.*;
  s9 : import java.util.regex.*;
 s10 : import java.util.stream.*;
   1 : int counter = 0;
   2 : int next() { return ++counter; }
   3 : next()
   4 : next()
   5 : next()
```

Giải thích:

1. Snippet `1` khai báo `counter` với giá trị ban đầu `0`.
2. Snippet `2` khai báo phương thức `next()`. Mỗi lần gọi, phương thức tăng `counter` rồi trả về giá trị mới.
3. Snippet `3` gọi `next()`, tạo `$3 = 1`.
4. `/!` chạy lại snippet gần nhất, tạo snippet `4` và `$4 = 2`.
5. `/3` chạy lại snippet có ID `3`, tạo snippet `5` và `$5 = 3`.
6. `/vars` hiển thị `counter = 3` cùng ba scratch variable.
7. `/drop 2` làm phương thức `next()` mất hiệu lực. Vì vậy `/methods` không còn liệt kê phương thức đang hoạt động.
8. `/vars` vẫn hiển thị các giá trị đã được tạo. `/list -all` cho thấy toàn bộ snippet, gồm cả khai báo phương thức đã drop.

Ví dụ cho thấy chạy lại một snippet có thể thay đổi trạng thái chương trình. Mỗi lần gọi `next()` tăng bộ đếm, nên ba lần đánh giá tạo ba giá trị khác nhau.

## 6. Cách phối hợp /edit, /drop và chạy lại

Trong một phiên khám phá API, có thể dùng quy trình sau:

1. Chạy `/list` để xem ID và nội dung snippet.
2. Chạy `/vars`, `/methods` hoặc `/types` để xác định thành phần cần thay đổi.
3. Dùng `/edit <id>` hoặc `/edit <name>` để sửa nội dung trong editor.
4. Lưu và đóng editor; kiểm tra kết quả bằng `/list`, `/list -all` và lệnh quan sát phù hợp.
5. Dùng `/drop <id>` hoặc `/drop <name>` để làm snippet không còn hiệu lực khi không cần nữa.
6. Dùng `/!`, `/-n` hoặc `/<id>` để đánh giá lại snippet cần kiểm tra.
7. Dùng `/vars` và `/list` để xác nhận trạng thái sau thao tác.

Không cần drop mọi snippet cũ chỉ để sửa một dòng. `/edit` phù hợp khi muốn thay đổi mã nguồn; `/drop` phù hợp khi muốn loại bỏ một khai báo khỏi trạng thái hoạt động; lệnh rerun phù hợp khi muốn đánh giá lại mã hiện có.

## 7. Lỗi thường gặp và cách tránh

1. **Chọn nhầm snippet để sửa:** dùng `/list` hoặc `/list -all` để xác định ID và tên trước khi gọi `/edit`.
2. **Nghĩ `/drop` xóa lịch sử:** drop chỉ làm snippet mất hiệu lực; `/list -all` vẫn có thể hiển thị nó.
3. **Nhầm `/-n` với `/<id>`:** một lệnh dùng vị trí lịch sử, lệnh kia dùng ID snippet. Kiểm tra `/history` và `/list` trước khi chọn.
4. **Cho rằng rerun giữ nguyên ID:** mỗi lần đánh giá lại tạo snippet mới và nhận ID mới.
5. **Quên kiểm tra trạng thái sau khi edit:** dùng `/vars`, `/methods`, `/types` và `/list -all` để xác nhận phiên bản nào đang hoạt động.
6. **Drop nhầm khai báo đang được dùng:** sau khi drop, các snippet mới có thể không còn truy cập được tên biến, phương thức hoặc kiểu đó. Kiểm tra phần phụ thuộc trước khi loại bỏ.
7. **Chạy lại snippet có tác dụng phụ:** thao tác ghi file, cập nhật dữ liệu, gửi yêu cầu mạng hoặc tăng bộ đếm có thể lặp lại. Đọc nội dung trước khi dùng `/!`, `/-n` hoặc `/<id>`.
8. **Editor không mở hoặc thay đổi không được nhận:** kiểm tra `/set editor`, biến môi trường `JSHELLEDITOR`, `VISUAL`, `EDITOR` và lưu file trước khi đóng editor.

## 8. Ghi nhớ

- `/edit` mở snippet trong editor để sửa; có thể chọn theo tên, ID, khoảng ID hoặc phạm vi snippet.
- `/set editor` cấu hình editor bên ngoài hoặc editor tích hợp.
- `/drop` làm snippet mất hiệu lực; `/list -all` vẫn có thể hiển thị lịch sử của nó.
- `/!` chạy lại snippet gần nhất; `/-n` chọn theo vị trí lịch sử; `/<id>` chọn theo ID.
- Mỗi lần chạy lại tạo một snippet mới và có thể thay đổi trạng thái phiên hoặc tạo tác dụng phụ mới.
- Sau khi sửa, drop hoặc rerun, kiểm tra lại bằng `/list`, `/vars`, `/methods` và `/types` để biết trạng thái hiện tại.