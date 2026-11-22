# Ảnh hưởng của clean/smudge filter và `working-tree-encoding`

Git cần một dạng nội dung nhất quán để lưu trong repository, nhưng tệp trên máy lập trình viên đôi khi cần một dạng khác. Ví dụ, một công cụ chỉ đọc được tệp UTF-16LE, một dự án cần chuẩn hóa dữ liệu trước khi commit, hoặc Git LFS cần thay nội dung tệp lớn bằng một con trỏ nhỏ trong repository rồi tải nội dung thật khi checkout.

Git hỗ trợ các cơ chế chuyển đổi nội dung qua **clean filter**, **smudge filter** và thuộc tính **`working-tree-encoding`**. Chúng tác động tới luồng dữ liệu giữa working tree, index và object database. Nếu cấu hình đúng, repository lưu nội dung theo dạng chuẩn trong khi mỗi working tree vẫn có thể dùng định dạng phù hợp với công cụ tại máy đó. Nếu cấu hình sai hoặc thiếu filter trên một máy, dữ liệu có thể bị lưu sai dạng, diff xuất hiện liên tục hoặc nội dung bị biến đổi ngoài ý muốn.

Bài này giải thích luồng chuyển đổi, cách cấu hình và kiểm tra, tác động lên `git add`/checkout, cùng những giới hạn cần tính đến khi nhiều hệ điều hành và nhiều phiên bản Git cùng làm việc trên một repository.

## 1. Git chuyển đổi nội dung ở đâu?

Một tệp được Git quản lý có thể tồn tại ở ba nơi với vai trò khác nhau:

- **Working tree:** tệp mà lập trình viên và công cụ đang mở, chỉnh sửa.
- **Index (staging area):** nội dung chuẩn bị cho commit tiếp theo.
- **Object database:** blob và các đối tượng Git được commit lưu lại.

Khi thêm tệp, Git đọc nội dung từ working tree và chuyển nó sang dạng lưu trong repository trước khi cập nhật index. Khi checkout hoặc ghi tệp từ commit ra working tree, Git chuyển nội dung lưu trong repository thành dạng cần dùng ở máy hiện tại.

```mermaid
flowchart LR
    W[Working tree\nNội dung tại máy] -->|clean filter / encoding| I[Index]
    I -->|commit| B[Blob trong repository]
    B -->|smudge filter / encoding| W2[Working tree sau checkout]
```

Mô hình trên giản lược một số bước như chuẩn hóa line ending và xử lý thuộc tính khác, nhưng thể hiện hướng chuyển đổi quan trọng:

- **Clean:** working tree → dạng canonical trong index/repository.
- **Smudge:** dạng canonical trong repository → working tree.

Git không yêu cầu hai dạng byte phải giống nhau. Mục tiêu là nội dung sau chuyển đổi phải đúng với quy ước của dự án và có thể tái tạo ổn định.

## 2. Clean filter và smudge filter là gì?

Clean và smudge là hai chiều của một filter driver do dự án cấu hình. Một thuộc tính trong `.gitattributes` gắn driver với nhóm đường dẫn; cấu hình Git trên máy cung cấp chương trình thực hiện chuyển đổi.

Ví dụ trong `.gitattributes`:

```gitattributes
*.data filter=normalize-data
```

Tên `normalize-data` là tên filter driver. Nó chưa phải lệnh thực thi. Mỗi máy cần cấu hình driver tương ứng trong Git config.

### 2.1. Clean filter

Clean filter chạy khi Git đưa nội dung từ working tree vào index, thường qua `git add`. Nó biến đổi dữ liệu về dạng canonical mà repository sẽ lưu.

Ví dụ, dự án muốn loại bỏ dấu thời gian sinh tự động ở cuối một tệp dữ liệu trước khi commit. Clean filter có thể chuẩn hóa tệp để hai máy sinh dữ liệu tương đương không tạo ra khác biệt không cần thiết.

```text
Tệp trên máy
    |
    v
clean filter
    |
    v
Nội dung chuẩn được đưa vào index và commit
```

### 2.2. Smudge filter

Smudge filter chạy theo chiều ngược lại khi Git ghi nội dung từ repository ra working tree, chẳng hạn khi checkout branch, switch branch hoặc khôi phục tệp từ commit.

Ví dụ, repository lưu một tệp cấu hình mẫu không chứa giá trị riêng của máy. Smudge filter có thể tạo dạng working-tree phù hợp với môi trường local dựa trên quy ước đã cấu hình.

```text
Blob trong repository
    |
    v
smudge filter
    |
    v
Tệp được ghi ra working tree
```

Smudge filter không thay đổi blob đã commit. Nó biến đổi dữ liệu được ghi ra working tree.

### 2.3. Clean và smudge nên phối hợp ra sao?

Với một filter chuẩn hóa, kết quả clean nên ổn định và có tính xác định: cùng đầu vào hợp lệ phải tạo cùng nội dung canonical. Khi dữ liệu canonical được checkout rồi đưa lại qua clean, lý tưởng là nó vẫn tạo ra đúng nội dung canonical ban đầu.

Có thể biểu diễn yêu cầu mong muốn:

```text
clean(smudge(blob)) = blob
```

Đây là cách kiểm tra tính nhất quán hữu ích. Không phải filter nào cũng là phép nghịch đảo hoàn hảo ở mức byte, nhưng filter cần được thiết kế để vòng checkout → add không tạo ra thay đổi giả hoặc làm mất dữ liệu.

Nếu clean filter thay đổi nội dung mỗi lần chạy, ví dụ chèn timestamp hiện tại, `git status` hoặc lần `git add` tiếp theo có thể liên tục báo khác biệt. Nếu smudge tạo nội dung mà clean không thể chuẩn hóa về dạng ban đầu, Git có thể tạo diff không mong muốn.

## 3. Cấu hình filter driver

### 3.1. Khai báo driver trong `.gitattributes`

`.gitattributes` xác định đường dẫn nào dùng filter và tên driver:

```gitattributes
*.data filter=normalize-data
```

Thuộc tính `filter=normalize-data` áp dụng driver tên `normalize-data` cho các đường dẫn khớp `*.data` theo quy tắc pattern của attributes.

### 3.2. Cấu hình lệnh trên máy

Driver được định nghĩa trong Git config, ví dụ:

```ini
[filter "normalize-data"]
    clean = "python tools/normalize.py clean"
    smudge = "python tools/normalize.py smudge"
    required = true
```

Ví dụ này giả định dự án có chương trình `tools/normalize.py` nhận chế độ `clean` hoặc `smudge`. Đây là cấu hình minh họa; lệnh thực tế phải phù hợp với ngôn ngữ, đường dẫn và môi trường chạy trên từng máy.

Filter command nhận nội dung qua standard input và trả nội dung đã chuyển đổi qua standard output. Thông báo chẩn đoán nên ghi ra standard error, tránh in thông báo vào standard output vì dữ liệu đó có thể bị Git coi là nội dung tệp.

Các khóa có ý nghĩa:

- `clean`: lệnh chuyển nội dung working tree sang dạng canonical.
- `smudge`: lệnh chuyển nội dung canonical sang dạng working tree.
- `required = true`: yêu cầu filter phải hoạt động; nếu không có hoặc chạy lỗi, Git báo lỗi thay vì âm thầm bỏ qua filter.

Nếu `required` không bật, filter được xem là tùy chọn. Khi lệnh filter không có hoặc không chạy được, Git có thể bỏ qua chuyển đổi và dùng nội dung nguyên trạng. Điều này có thể làm các máy lưu nội dung khác nhau dù dùng chung `.gitattributes`.

### 3.3. `.gitattributes` không tự cài đặt chương trình filter

Repository có thể commit `.gitattributes` và script filter, nhưng lệnh thực thi của driver được cấu hình trong Git config trên từng máy. Việc clone repository không tự bảo đảm mọi máy đã có filter driver hoạt động.

Do đó, quy trình onboarding cần chỉ rõ:

- Cần cài công cụ hoặc runtime nào.
- Lệnh clean/smudge được cấu hình ra sao.
- Phiên bản filter nào tương thích với repository.
- Cách kiểm tra filter có sẵn và hoạt động đúng.
- Điều gì xảy ra nếu máy không có filter.

Không nên giả định `.gitattributes` sẽ tự chạy một script chỉ vì script đó nằm trong repository. Việc tách thuộc tính khỏi cấu hình lệnh giúp người dùng kiểm soát môi trường, đồng thời tránh để một tệp attributes tự ý thực thi lệnh tùy ý.

Có thể thiết lập cấu hình local bằng lệnh, nếu dự án đã cung cấp script đáng tin cậy:

```bash
git config filter.normalize-data.clean "python tools/normalize.py clean"
git config filter.normalize-data.smudge "python tools/normalize.py smudge"
git config filter.normalize-data.required true
```

Các lệnh trên ghi cấu hình vào `.git/config` của repository hiện tại. Trước khi cấu hình hoặc chạy filter từ một dự án không quen thuộc, hãy đọc và hiểu chương trình được gọi: filter chạy với quyền của người dùng và có thể đọc, ghi hoặc gửi dữ liệu tùy nội dung script.

### 3.4. Process filter

Ngoài cặp lệnh `clean` và `smudge`, Git hỗ trợ process filter thông qua cấu hình `filter.<driver>.process`. Process filter là một tiến trình tồn tại lâu hơn và trao đổi nhiều yêu cầu chuyển đổi theo giao thức của Git, giúp giảm chi phí khởi động chương trình khi xử lý nhiều tệp.

Một driver dùng process filter thường được chọn thay cho việc khởi chạy một tiến trình riêng cho từng lần clean hoặc smudge. Cách triển khai cần tuân thủ giao thức process filter của Git; không thể thay một lệnh clean đơn giản bằng process filter mà không triển khai giao thức đó.

## 4. Ví dụ thực tế: Git LFS

Git LFS là ví dụ quen thuộc về việc dùng clean/smudge filter. Thay vì lưu trực tiếp nội dung lớn trong Git object database thông thường, Git LFS lưu một tệp pointer nhỏ trong repository; nội dung lớn được lưu trong hệ thống lưu trữ LFS.

Một `.gitattributes` có thể chứa quy tắc tương tự:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

Khi thêm tệp `.psd`, clean filter của Git LFS thay nội dung trong repository bằng pointer. Khi checkout, smudge/process filter của Git LFS lấy nội dung thực và ghi ra working tree nếu dữ liệu có sẵn và người dùng có quyền truy cập.

Kết quả:

- Repository Git thông thường lưu pointer nhỏ.
- Working tree của người dùng có thể chứa tệp nhị phân đầy đủ.
- Các máy cần Git LFS và quyền truy cập kho LFS để lấy nội dung thực.

Nếu máy không cài Git LFS hoặc filter không được cấu hình đúng, người dùng có thể thấy pointer thay vì tệp nhị phân mong đợi, hoặc Git không thực hiện chuyển đổi như dự án yêu cầu. Vì vậy, cần cài đặt và kiểm tra Git LFS trên các máy tham gia.

## 5. `working-tree-encoding` là gì?

`working-tree-encoding` là thuộc tính Git dùng để khai báo encoding của tệp trong working tree. Git chuyển nội dung từ encoding đó sang UTF-8 khi đưa vào repository và chuyển từ UTF-8 về encoding được chỉ định khi ghi tệp ra working tree.

Ví dụ, một số công cụ trên Windows cần tệp PowerShell ở dạng UTF-16LE với CRLF. Ta có thể khai báo:

```gitattributes
*.ps1 text working-tree-encoding=UTF-16LE eol=crlf
```

Ý nghĩa:

- `*.ps1`: áp dụng cho các tệp có phần mở rộng `.ps1` khớp pattern.
- `text`: bật xử lý nội dung như văn bản và chuẩn hóa line ending theo quy tắc Git.
- `working-tree-encoding=UTF-16LE`: working tree dùng UTF-16LE; nội dung lưu trong repository được chuyển sang UTF-8.
- `eol=crlf`: khi checkout, working tree dùng CRLF cho tệp này.

Luồng dữ liệu khái quát:

```text
Working tree: UTF-16LE + CRLF
        |
        | git add: chuyển encoding, chuẩn hóa nội dung
        v
Repository: UTF-8 với line ending chuẩn hóa
        |
        | checkout: chuyển về encoding và EOL được khai báo
        v
Working tree: UTF-16LE + CRLF
```

Nhờ vậy, các máy có thể lưu cùng nội dung văn bản theo dạng chuẩn trong repository, dù công cụ tại máy yêu cầu encoding khác.

### 5.1. Vì sao Git lưu UTF-8 trong repository?

UTF-8 là dạng lưu trữ phù hợp cho việc chia sẻ nội dung văn bản giữa các hệ điều hành và công cụ phát triển hiện đại. Nếu mỗi máy commit cùng một văn bản dưới encoding khác nhau, repository có thể chứa các blob khác nhau dù nội dung người dùng nhìn thấy giống nhau.

`working-tree-encoding` giúp tách encoding phục vụ công cụ local khỏi encoding chuẩn của repository. Review, diff và xử lý nội dung trên repository vì vậy dễ nhất quán hơn.

### 5.2. Phân biệt với `text` và `eol`

Ba thuộc tính liên quan nhưng không giống nhau:

| Thuộc tính | Vai trò |
|---|---|
| `text` | Xác định tệp được xử lý như văn bản và chuẩn hóa line ending khi đưa vào repository. |
| `eol=lf` hoặc `eol=crlf` | Chỉ định kiểu line ending trong working tree khi checkout. |
| `working-tree-encoding=<encoding>` | Chỉ định encoding trong working tree và chuyển đổi với UTF-8 trong repository. |

Chỉ đổi line ending không giải quyết vấn đề encoding. Tương tự, chuyển encoding không nhất thiết xác định line ending mong muốn. Nếu một công cụ cần cả encoding và EOL cụ thể, cần khai báo và kiểm tra cả hai.

## 6. Những giới hạn và rủi ro của `working-tree-encoding`

### 6.1. Tất cả client cần hỗ trợ thuộc tính

Không phải mọi phiên bản Git hoặc mọi Git client đều hỗ trợ `working-tree-encoding`. Client cũ không hiểu thuộc tính này có thể xử lý nội dung như dữ liệu thông thường và lưu nguyên byte từ working tree. Khi đó, một máy có thể commit UTF-16LE trong khi máy khác kỳ vọng repository lưu UTF-8.

Trước khi áp dụng thuộc tính trong dự án:

- Xác định phiên bản Git tối thiểu được hỗ trợ.
- Kiểm tra Git GUI, IDE và công cụ tích hợp của nhóm có hỗ trợ thuộc tính này.
- Thử clone, checkout, sửa, add và commit trên các môi trường đại diện.
- Ghi rõ yêu cầu phiên bản trong tài liệu dự án.

### 6.2. Encoding phải chuyển đổi được và round-trip an toàn

Không phải mọi encoding đều có phép chuyển đổi hai chiều hoàn hảo. Một số encoding có thể không biểu diễn được mọi ký tự Unicode hoặc có nhiều dạng byte tương đương. Nếu chuyển đổi làm mất ký tự, nội dung sau checkout có thể khác nội dung ban đầu.

Hãy thử với các ký tự ngoài ASCII, dấu tiếng Việt, ký tự đặc biệt và các trường hợp BOM nếu công cụ sử dụng chúng. Không chỉ kiểm tra một tệp chứa chữ cái tiếng Anh đơn giản.

### 6.3. Không áp dụng tùy tiện cho tệp nhị phân

`working-tree-encoding` được thiết kế cho nội dung văn bản có encoding xác định. Không dùng nó cho ảnh, archive, executable hoặc tệp nhị phân tùy ý. Chuyển đổi encoding trên dữ liệu nhị phân có thể làm hỏng nội dung.

Với tệp nhị phân, thường cần dùng filter chuyên biệt hoặc lưu nguyên byte. Hãy khai báo `-text` nếu muốn tránh Git xử lý line ending như văn bản cho đường dẫn đó.

### 6.4. Chi phí và khả năng tương thích

Chuyển đổi encoding và chạy filter có thể tăng thời gian `git add`, checkout, switch hoặc thao tác ghi tệp. Filter ngoài còn phụ thuộc runtime, script, quyền truy cập và cấu hình trên từng máy.

Chỉ dùng cơ chế chuyển đổi khi có yêu cầu thực tế. Nếu toàn bộ công cụ đã hỗ trợ UTF-8, giữ UTF-8 trong cả working tree và repository thường đơn giản hơn.

## 7. Filter lỗi hoặc thiếu cấu hình gây ra điều gì?

Giả sử `.gitattributes` có:

```gitattributes
*.data filter=normalize-data
```

Nhưng máy của một thành viên chưa cấu hình `filter.normalize-data`. Nếu filter là tùy chọn, Git có thể bỏ qua filter và dùng nội dung nguyên trạng. Khi thành viên chạy `git add`, dữ liệu chưa được chuẩn hóa có thể được đưa vào index.

Nếu dự án yêu cầu filter bắt buộc, cấu hình:

```ini
[filter "normalize-data"]
    clean = "python tools/normalize.py clean"
    smudge = "python tools/normalize.py smudge"
    required = true
```

Khi filter không thể chạy, Git sẽ báo lỗi thay vì âm thầm tiếp tục mà không chuyển đổi. Đây thường là lựa chọn phù hợp khi nội dung canonical phụ thuộc vào filter.

### 7.1. Clean filter không ổn định

Nếu clean filter tạo kết quả khác nhau giữa các lần chạy, có thể gặp các hiện tượng:

- `git status` liên tục báo tệp modified dù người dùng không sửa nội dung có ý nghĩa.
- Mỗi lần `git add` tạo blob khác nhau.
- Máy này commit được nhưng máy khác checkout rồi commit lại tạo diff lớn.
- Nội dung bị mất hoặc biến đổi sau nhiều vòng clean/smudge.

Filter nên có kiểm thử với dữ liệu đại diện và kiểm tra vòng chuyển đổi. Tránh chèn timestamp, đường dẫn tuyệt đối, username hoặc dữ liệu riêng của máy vào dạng canonical nếu các giá trị đó không phải nội dung cần quản lý.

### 7.2. Smudge filter phụ thuộc mạng hoặc dịch vụ ngoài

Một số filter, như Git LFS, cần truy cập dịch vụ bên ngoài khi checkout. Nếu mạng gián đoạn, xác thực hết hạn hoặc đối tượng không có trên server, checkout có thể không lấy được nội dung thật.

Khi gặp lỗi, hãy giữ lại thông báo, kiểm tra cấu hình filter và khả năng truy cập dịch vụ. Không ghi đè pointer hoặc nội dung canonical bằng một tệp placeholder không rõ nguồn gốc.

## 8. Kiểm tra thuộc tính và cấu hình filter

### 8.1. Xem thuộc tính hiệu lực của một đường dẫn

```bash
git check-attr --all -- path/to/file.data
```

Hoặc chỉ xem các thuộc tính liên quan:

```bash
git check-attr filter text eol working-tree-encoding -- path/to/file.data
```

Lệnh này giúp biết đường dẫn thực sự nhận thuộc tính nào từ các file attributes và cấu hình liên quan.

### 8.2. Xem cấu hình filter trên máy

```bash
git config --show-origin --get-regexp '^filter\.'
```

Kết quả hiển thị các cấu hình filter cùng nguồn cấu hình, giúp phát hiện máy thiếu clean/smudge command hoặc đang dùng cấu hình từ file global ngoài dự kiến.

Không chia sẻ đầu ra cấu hình một cách máy móc nếu command có chứa token, mật khẩu hoặc thông tin nội bộ.

### 8.3. Xem nội dung canonical trong repository

Với một tệp đã commit:

```bash
git cat-file -p HEAD:path/to/file.ps1
```

Lệnh hiển thị nội dung blob được lưu trong commit, tức dạng canonical mà Git quản lý. Nếu tệp dùng `working-tree-encoding=UTF-16LE`, nội dung blob thường là UTF-8 đã chuyển đổi, không phải byte UTF-16LE của working tree.

Để xem khác biệt giữa working tree và index:

```bash
git diff -- path/to/file.ps1
git diff --cached -- path/to/file.ps1
```

Nếu filter hoạt động không ổn định, các lệnh này có thể giúp xác định thay đổi xuất hiện ở bước nào.

## 9. Thay đổi attributes trên repository đã có dữ liệu

Khi thêm `filter` hoặc `working-tree-encoding` vào `.gitattributes`, các blob đã commit không tự động được viết lại. Git chỉ áp dụng chuyển đổi khi xử lý nội dung qua các thao tác tương ứng.

Nếu muốn chuẩn hóa lại các tệp tracked theo thuộc tính mới, có thể dùng:

```bash
git add --renormalize .
```

Lệnh này áp dụng lại quy trình clean cho các tệp tracked trong phạm vi chỉ định và cập nhật index. Trước khi commit:

```bash
git status --short
git diff --cached --stat
git diff --cached
```

Hãy kiểm tra kỹ diff để chắc chắn thay đổi chỉ là chuyển đổi mong muốn. Nếu repository lớn hoặc thuộc tính chỉ áp dụng cho một nhóm tệp, có thể giới hạn đường dẫn thay vì chuẩn hóa toàn bộ.

Không chạy renormalize trên toàn repository khi filter chưa được cài đặt và kiểm tra đầy đủ trên mọi môi trường. Nếu filter thiếu, tùy cấu hình, Git có thể không chuyển đổi nội dung như mong đợi.

## 10. Quy trình đưa filter hoặc encoding vào dự án

Khi nhóm quyết định dùng clean/smudge filter hoặc `working-tree-encoding`, hãy triển khai có kiểm soát:

1. **Xác định yêu cầu:** tệp nào cần chuyển đổi, dạng canonical nào được lưu trong repository và dạng working tree mà công cụ cần.
2. **Chọn cơ chế:** dùng `working-tree-encoding` cho chuyển đổi encoding văn bản; dùng filter driver cho biến đổi nội dung tùy chỉnh; dùng Git LFS cho nội dung lớn phù hợp với LFS.
3. **Khai báo `.gitattributes`:** chỉ áp dụng thuộc tính cho pattern chính xác, tránh ảnh hưởng nhầm tệp nhị phân hoặc mã nguồn khác.
4. **Cài đặt cấu hình local:** bảo đảm từng máy có driver, script, runtime và quyền truy cập cần thiết.
5. **Thiết lập lỗi rõ ràng:** nếu nội dung phụ thuộc filter, cân nhắc `required = true` để tránh máy thiếu filter commit dữ liệu chưa chuẩn hóa.
6. **Thử vòng chuyển đổi:** checkout, sửa, add, commit, clone và checkout lại; so sánh nội dung và diff.
7. **Kiểm tra đa môi trường:** thử trên Windows, macOS, Linux, IDE và phiên bản Git tối thiểu mà nhóm hỗ trợ.
8. **Chuẩn hóa dữ liệu cũ:** nếu cần, dùng `git add --renormalize` trên phạm vi đã kiểm tra rồi review toàn bộ diff.
9. **Tài liệu hóa:** ghi rõ cách cài filter, cấu hình, cách kiểm tra và cách xử lý lỗi cho thành viên mới.

## 11. Bảng so sánh các cơ chế

| Cơ chế | Chuyển đổi gì? | Cấu hình ở đâu? | Trường hợp phù hợp |
|---|---|---|---|
| Clean filter | Working tree → nội dung canonical | `.gitattributes` chọn driver; Git config cung cấp lệnh | Chuẩn hóa hoặc biến đổi nội dung trước khi lưu |
| Smudge filter | Nội dung canonical → working tree | `.gitattributes` chọn driver; Git config cung cấp lệnh | Tạo dạng tệp cần dùng trên máy khi checkout |
| Process filter | Clean/smudge qua tiến trình lâu dài | `filter.<driver>.process` và `.gitattributes` | Filter xử lý nhiều tệp cần giảm chi phí khởi động |
| `working-tree-encoding` | Encoding working tree ↔ UTF-8 trong repository | `.gitattributes` | Công cụ yêu cầu encoding văn bản cụ thể |
| `text` / `eol` | Chuẩn hóa và chọn line ending | `.gitattributes` | Khác biệt LF/CRLF giữa hệ điều hành |

## 12. Ghi nhớ

- Clean chuyển nội dung từ working tree sang dạng canonical khi Git cập nhật index/repository.
- Smudge chuyển nội dung canonical sang dạng cần có trong working tree khi Git ghi tệp ra.
- `.gitattributes` chọn driver theo đường dẫn; Git config trên từng máy cung cấp lệnh filter.
- `required = true` khiến Git báo lỗi nếu filter bắt buộc không hoạt động, tránh âm thầm lưu nội dung chưa chuyển đổi.
- Clean filter cần ổn định; vòng `clean(smudge(blob))` nên trả lại nội dung canonical tương đương.
- `working-tree-encoding` chuyển encoding working tree sang UTF-8 trong repository và chuyển ngược khi checkout.
- Mọi client cần hỗ trợ thuộc tính encoding và cài filter tương ứng; nếu không, các máy có thể lưu nội dung khác dạng.
- `text`/`eol` xử lý line ending, còn `working-tree-encoding` xử lý encoding; hai vấn đề cần được kiểm tra riêng.
- `git check-attr`, `git config --show-origin`, `git cat-file` và `git diff` giúp chẩn đoán luồng chuyển đổi.
- Khi đổi thuộc tính cho tệp đã tracked, xem xét `git add --renormalize` và review kỹ diff trước commit.

Trước khi dùng filter trong dự án, hãy xác định rõ dạng dữ liệu được lưu trong repository và dạng cần xuất hiện ở working tree. Sau đó kiểm tra cả máy có filter lẫn máy không có filter, bởi một cấu hình chỉ chạy đúng trên máy của tác giả vẫn có thể làm hỏng tính nhất quán của repository khi được chia sẻ.
