# Tên tệp Unicode, ký tự không hợp lệ và đường dẫn dài

Một repository Git có thể được phát triển trên Windows, macOS và Linux. Mỗi hệ điều hành cùng hệ thống tệp có cách xử lý tên tệp, chữ hoa chữ thường, Unicode và độ dài đường dẫn khác nhau. Vì vậy, một tên tệp hợp lệ trên máy Linux có thể không checkout được trên Windows; hai tên khác nhau trong Git cũng có thể bị xem là cùng một tệp trên ổ đĩa không phân biệt hoa thường.

Git lưu tên đường dẫn trong lịch sử repository, nhưng khả năng tạo, đọc và checkout tệp còn phụ thuộc hệ điều hành cùng hệ thống tệp. Để cộng tác ổn định, nhóm cần hiểu các khác biệt này, kiểm tra tên tệp trước khi commit và thống nhất một quy ước tên có tính di động.

## 1. Git lưu tên đường dẫn như thế nào?

Trong repository, tên tệp và thư mục là một phần của tree object và index. Git lưu đường dẫn dưới dạng chuỗi byte; dấu `/` được dùng để phân tách các thành phần đường dẫn và byte NUL không thể xuất hiện trong tên. Git không tự áp đặt một quy tắc chuẩn hóa Unicode chung cho mọi hệ điều hành.

Khi làm việc trên thực tế, Git phải chuyển đổi và trao đổi những đường dẫn đó với API của hệ điều hành. Hệ thống tệp có thể giới hạn ký tự, cách so sánh tên, dạng Unicode hoặc độ dài đường dẫn. Vì thế, một repository có thể chứa commit với tên tệp mà một máy khác không thể checkout hoặc thao tác bình thường.

Một số khác biệt thường gặp:

| Môi trường | Đặc điểm thường gặp | Rủi ro khi cộng tác |
|---|---|---|
| Linux với ext4 | Thường phân biệt hoa thường; cho phép nhiều ký tự trong tên, ngoại trừ các giới hạn cơ bản của hệ thống tệp | Có thể tạo tên không hợp lệ trên Windows hoặc tên chỉ khác chữ hoa/thường |
| Windows với NTFS | Thường không phân biệt hoa thường; có các ký tự và tên thiết bị bị dành riêng | Hai đường dẫn khác nhau trong Git có thể va chạm; một số tên không thể tạo |
| macOS với APFS | Thường cài đặt theo chế độ không phân biệt hoa thường, dù có thể dùng volume phân biệt hoa thường; có các vấn đề tương thích về biểu diễn Unicode | Tên khác biệt về hoa thường hoặc cách mã hóa Unicode có thể gây nhầm lẫn |

Đây là các mặc định phổ biến, không phải quy tắc tuyệt đối cho mọi máy. Hệ thống tệp, tùy chọn định dạng volume và cấu hình Git có thể làm hành vi khác đi.

## 2. Tên tệp Unicode và chuẩn hóa ký tự

Unicode cho phép một ký tự hiển thị được biểu diễn theo nhiều chuỗi mã tương đương. Ví dụ, ký tự `é` có thể được biểu diễn bằng:

- Một code point dựng sẵn: `U+00E9` (LATIN SMALL LETTER E WITH ACUTE).
- Hai code point: `U+0065` (LATIN SMALL LETTER E) theo sau bởi `U+0301` (COMBINING ACUTE ACCENT).

Hai chuỗi có thể hiển thị giống nhau nhưng byte UTF-8 khác nhau. Dạng chuẩn hóa NFC thường dùng ký tự dựng sẵn khi có thể; NFD biểu diễn bằng ký tự cơ sở kết hợp dấu. Git không tự coi mọi chuỗi Unicode tương đương về mặt hiển thị là cùng một tên đường dẫn trong object database.

Điều này có thể dẫn đến tình huống:

- Một máy tạo tệp bằng dạng NFC, máy khác tạo tên bằng dạng NFD.
- Terminal hiển thị hai tên giống nhau, nhưng Git xem chúng là hai chuỗi byte khác nhau.
- Hệ thống tệp hoặc API của một nền tảng chuẩn hóa tên khi ghi/đọc, gây va chạm hoặc khiến trạng thái Git khó hiểu.

### core.precomposeUnicode trên macOS

Git for macOS có cấu hình `core.precomposeUnicode` để xử lý tên Unicode ở dạng decomposition do hệ thống tệp macOS cung cấp. Khi bật, Git chuyển tên về dạng precomposed khi làm việc với repository để giảm khác biệt giữa biểu diễn trên filesystem và tên được lưu trong Git.

Kiểm tra giá trị đang dùng:

```bash
git config --show-origin --get core.precomposeUnicode
```

Nếu không có output, cấu hình có thể đang dùng mặc định của bản Git hiện tại. Trên macOS, tùy chọn này thường được bật để hỗ trợ tên Unicode. Chỉ thay đổi cấu hình khi bạn hiểu tác động đến repository và môi trường cộng tác; không nên tắt nó như một cách thử ngẫu nhiên khi thấy tên tệp hiển thị lạ.

### Quy ước Unicode cho nhóm

Để giảm rủi ro, nhóm nên thống nhất:

- Dùng UTF-8 cho tên tệp và nội dung văn bản.
- Dùng một dạng chuẩn hóa Unicode nhất quán, thường chọn NFC cho tên mới.
- Tránh tạo hai tên chỉ khác cách biểu diễn Unicode nhưng trông giống nhau.
- Tránh các ký tự dễ gây nhầm lẫn thị giác giữa các bảng chữ cái khác nhau khi tên tệp có ý nghĩa vận hành quan trọng.
- Khi rename hàng loạt tên Unicode, kiểm tra diff và trạng thái trên ít nhất một môi trường khác hệ điều hành.

## 3. Phân biệt chữ hoa và chữ thường

Git phân biệt tên đường dẫn theo dữ liệu được lưu trong repository. Tuy nhiên, nhiều volume Windows và macOS mặc định không phân biệt hoa thường. Ví dụ, Git có thể lưu hai đường dẫn:

```text
src/Config.java
src/config.java
```

Trên hệ thống tệp phân biệt hoa thường, đây là hai tệp khác nhau. Trên volume không phân biệt hoa thường, hai tên có thể xung đột vì hệ thống tệp xem chúng là cùng một đường dẫn.

Rủi ro thường gặp khác là đổi tên chỉ khác chữ hoa/thường, ví dụ `readme.md` thành `README.md`. Máy Linux có thể ghi nhận ngay, nhưng trên máy Windows hoặc macOS không phân biệt hoa thường, thao tác đổi tên có thể không được nhận diện như mong đợi.

### Kiểm tra cấu hình core.ignoreCase

Git có cấu hình `core.ignoreCase` để thích nghi với filesystem không phân biệt hoa thường. Khi clone hoặc khởi tạo repository, Git có thể tự đặt giá trị phù hợp với môi trường. Kiểm tra cấu hình:

```bash
git config --show-origin --get core.ignoreCase
```

Không nên tùy tiện đặt `core.ignoreCase=false` trên volume không phân biệt hoa thường để ép Git xử lý tên như Linux. Git có thể hiển thị trạng thái khó hiểu hoặc không thể tạo đồng thời những tên mà filesystem coi là trùng nhau. Cấu hình này giúp Git thích nghi với filesystem; nó không biến filesystem thành case-sensitive.

### Đổi tên chỉ khác hoa thường

Nếu cần đổi `readme.md` thành `README.md` trên máy không phân biệt hoa thường, có thể dùng tên trung gian:

```bash
git mv readme.md readme-temp.md
git mv readme-temp.md README.md
git status --short
```

Sau đó kiểm tra diff và commit việc đổi tên. Bước trung gian giúp filesystem nhận ra đây là hai thao tác rename riêng biệt. Nếu tên nguồn không đúng như ví dụ, hãy thay bằng đường dẫn thực tế của repository.

## 4. Ký tự và tên dành riêng trên Windows

Windows có các giới hạn tên tệp phổ biến mà Linux cho phép. Trong tên một thành phần đường dẫn trên Windows, tránh các ký tự:

```text
< > : " / \ | ? *
```

Ngoài ra, Windows không cho phép các ký tự điều khiển từ U+0000 đến U+001F trong tên thông thường. Dấu `/` và `\` được dùng làm dấu phân tách đường dẫn; dấu `:` có ý nghĩa đặc biệt trong cú pháp ổ đĩa và alternate data stream.

Windows cũng có các tên thiết bị dành riêng, kể cả khi thêm phần mở rộng. Những tên thường gặp gồm:

```text
CON   PRN   AUX   NUL
COM1  COM2  ... COM9
LPT1  LPT2  ... LPT9
```

Ví dụ `NUL.txt`, `CON.log` hoặc `COM1.data` vẫn có thể bị xem là tên thiết bị dành riêng. Một số biến thể dùng ký tự số mũ Unicode cũng được Windows xử lý như tên thiết bị; vì vậy, quy tắc di động nên tránh toàn bộ họ tên này thay vì chỉ kiểm tra một vài chuỗi thông thường.

Tên thành phần đường dẫn trên Windows cũng không nên kết thúc bằng dấu chấm hoặc dấu cách. Ví dụ `report.` và `report ` có thể bị chuẩn hóa hoặc không truy cập được như mong đợi.

### Ví dụ tên có nguy cơ

| Tên | Vấn đề trên Windows | Gợi ý thay thế |
|---|---|---|
| `report:final.txt` | Có dấu `:` | `report-final.txt` |
| `image?.png` | Có dấu `?` | `image-1.png` |
| `data*.csv` | Có dấu `*` | `data-all.csv` |
| `CON` hoặc `CON.txt` | Tên thiết bị dành riêng | `console-output.txt` |
| `notes.` | Kết thúc bằng dấu chấm | `notes` hoặc `notes-final` |
| `draft ` | Kết thúc bằng dấu cách | `draft` |

Nếu một commit được tạo trên Linux chứa tên không hợp lệ với Windows, người dùng Windows có thể gặp lỗi khi checkout, switch branch hoặc reset về commit đó. Trong trường hợp này, cần sửa tên ở môi trường có thể truy cập tệp, commit việc rename và chia sẻ thay đổi để các nền tảng khác sử dụng tên tương thích.

## 5. Đường dẫn dài và giới hạn MAX_PATH

Độ dài đường dẫn không chỉ phụ thuộc tên tệp cuối cùng mà còn gồm toàn bộ thư mục cha. Ví dụ, một tên tệp ngắn nằm sâu trong nhiều cấp thư mục vẫn có thể tạo ra đường dẫn rất dài:

```text
C:\Users\developer\Documents\workspace\company\platform\services\identity\src\main\java\com\example\security\authentication\AuthenticationConfiguration.java
```

Trên Windows, giới hạn truyền thống `MAX_PATH` thường được nhắc đến là 260 ký tự cho đường dẫn kiểu Win32 thông thường. Các phiên bản Windows hiện đại có hỗ trợ đường dẫn dài hơn nếu chính sách hệ thống và ứng dụng cùng đáp ứng điều kiện cần thiết. Vì vậy, bật hỗ trợ long paths trong Windows không tự động bảo đảm mọi chương trình đều xử lý được đường dẫn dài.

Git for Windows có cấu hình riêng để dùng API phù hợp khi thao tác với đường dẫn dài:

```bash
git config --show-origin --get core.longpaths
```

Nếu nhóm dùng Git for Windows và gặp lỗi như `Filename too long`, có thể bật trong repository hiện tại:

```bash
git config core.longpaths true
```

Thiết lập này ghi cấu hình local cho repository. Nó giúp Git for Windows xử lý đường dẫn dài trong những thao tác được hỗ trợ, nhưng không thay đổi giới hạn của editor, IDE, compiler, công cụ build, shell hoặc ứng dụng khác. Windows cũng có thể cần bật chính sách hỗ trợ long paths và ứng dụng phải hỗ trợ cơ chế đó.

### Các cách giảm độ dài đường dẫn

- Clone repository vào thư mục ngắn hơn, ví dụ `C:\src\project` thay vì thư mục lồng nhiều cấp.
- Rút gọn tên thư mục không cần thiết hoặc giảm số cấp lồng nhau.
- Tránh lặp lại tên module dài ở nhiều cấp thư mục nếu cấu trúc có thể được đơn giản hóa.
- Bật `core.longpaths` trong Git for Windows khi cần và kiểm tra các công cụ tiếp theo trong pipeline.
- Kiểm tra checkout trên Windows thực tế, vì thành công trên Linux không chứng minh mọi đường dẫn sẽ hoạt động trên Windows.

Không nên dựa hoàn toàn vào cấu hình long paths để thiết kế cấu trúc repository. Đường dẫn ngắn và dễ đọc giúp cả IDE, công cụ build và CI hoạt động ổn định hơn.

## 6. Kiểm tra tên đường dẫn trong repository

Một số lệnh Git giúp xem tên tệp mà repository đang quản lý:

```bash
# Liệt kê các đường dẫn tracked trong index.
git ls-files

# Xem đường dẫn cùng trạng thái ngắn.
git status --short

# Liệt kê đường dẫn trong một commit cụ thể.
git ls-tree -r --name-only HEAD
```

Mặc định, Git có thể quote các ký tự đặc biệt hoặc ký tự non-ASCII trong output để tránh làm terminal hiểu sai. Nếu muốn hiển thị ký tự Unicode trực tiếp để kiểm tra bằng mắt:

```bash
git -c core.quotepath=false ls-files
```

Nếu muốn xem dạng escape để phân biệt byte hoặc ký tự đặc biệt, dùng mặc định `core.quotepath=true`:

```bash
git -c core.quotepath=true ls-files
```

Output có escape không đồng nghĩa tên tệp bị hỏng; đó có thể chỉ là cách Git biểu diễn an toàn trong terminal. Với script xử lý tên tệp, ưu tiên dạng NUL-delimited:

```bash
git ls-files -z
```

Không nên parse output `git ls-files` bằng cách tách theo dấu cách hoặc dòng nếu tên tệp có thể chứa ký tự đặc biệt. Dùng `-z` và xử lý delimiter NUL để giữ nguyên tên.

## 7. Chuẩn hóa tên tệp để tương thích đa nền tảng

Một quy ước đơn giản giúp giảm phần lớn vấn đề là:

1. Dùng chữ thường ASCII cho tên thư mục và tên tệp kỹ thuật khi không cần Unicode.
2. Dùng dấu gạch ngang `-` hoặc gạch dưới `_` thay cho dấu cách và ký tự phân cách đặc biệt.
3. Tránh tên thiết bị Windows, dấu chấm hoặc dấu cách ở cuối tên.
4. Tránh hai đường dẫn chỉ khác chữ hoa/thường.
5. Với tên Unicode, thống nhất UTF-8 và chuẩn hóa NFC.
6. Giữ cấu trúc thư mục nông và tên thành phần ngắn, dễ đọc.
7. Kiểm tra các thay đổi rename trên Windows, macOS và Linux trước khi phát hành.

Ví dụ chuyển một số tên không nhất quán sang tên dễ di động:

| Tên ban đầu | Tên đề xuất |
|---|---|
| `User Profile/` | `user-profile/` |
| `API Response.JSON` | `api-response.json` |
| `cấu hình local/` | `local-config/` nếu không cần giữ tên tiếng Việt |
| `release:2026.txt` | `release-2026.txt` |
| `Image.PNG` và `image.png` | Chọn một tên duy nhất, ví dụ `image.png` |

Không phải mọi tên có dấu hoặc Unicode đều không hợp lệ. Tên tiếng Việt có thể dùng bình thường nếu các môi trường xử lý Unicode thống nhất. Điều quan trọng là tránh các dạng biểu diễn tương đương nhưng khác byte, tránh tên không được nền tảng hỗ trợ và kiểm tra khả năng checkout trên các hệ điều hành nhóm đang dùng.

## 8. Phát hiện và sửa tên gây xung đột

Nếu nghi ngờ repository có hai tên chỉ khác chữ hoa/thường hoặc khác dạng Unicode, hãy liệt kê đường dẫn và so sánh chúng. Có thể xem các tên được Git lưu bằng:

```bash
git -c core.quotepath=true ls-files
```

Nếu filesystem hiện tại không thể biểu diễn cả hai đường dẫn, việc kiểm tra có thể cần thực hiện trên volume phân biệt hoa thường hoặc một môi trường Linux. Sau khi xác định tên chuẩn cần giữ, rename về một tên duy nhất và commit thay đổi.

Ví dụ đổi tên tệp bằng Git:

```bash
git mv -- "src/OldName.java" "src/new-name.java"
git status --short
git diff --cached --summary
```

Với rename chỉ khác hoa thường trên filesystem không phân biệt hoa thường, dùng tên trung gian như đã trình bày:

```bash
git mv -- "src/Config.java" "src/config-temp.java"
git mv -- "src/config-temp.java" "src/config.java"
```

Nếu tệp trong commit có tên không hợp lệ trên Windows và Windows không thể checkout commit đó, hãy nhờ thành viên dùng Linux hoặc filesystem hỗ trợ tên này thực hiện rename rồi push commit sửa. Tránh thao tác trực tiếp trong `.git` để đổi tên object hoặc index bằng tay.

## 9. Kiểm tra trong quy trình CI và review

Với dự án có nhiều hệ điều hành, nên đưa kiểm tra tính di động của tên tệp vào quy trình review hoặc CI. Một chính sách có thể kiểm tra:

- Không có hai đường dẫn trùng nhau khi chuyển về chữ thường theo quy tắc so sánh của nhóm.
- Không có ký tự bị cấm trên Windows hoặc tên thiết bị dành riêng.
- Không có thành phần đường dẫn kết thúc bằng dấu chấm hay dấu cách.
- Tên Unicode tuân theo chuẩn hóa đã thống nhất.
- Đường dẫn không vượt quá giới hạn nội bộ mà công cụ build và IDE hỗ trợ.

CI nên chạy checkout và build trên Windows, macOS và Linux nếu đó là các nền tảng được hỗ trợ. Việc chỉ chạy unit test trên một hệ điều hành có thể bỏ sót lỗi tên tệp xảy ra ngay từ bước checkout.

Nếu nhóm có quy tắc chặt, có thể viết script kiểm tra danh sách từ `git ls-files -z` để xử lý chính xác mọi tên đường dẫn. Script cần xử lý dữ liệu NUL-delimited, so sánh case-insensitive theo quy tắc đã chọn và kiểm tra các ký tự/tên dành riêng của Windows. Không nên dùng một phép đổi chữ thường đơn giản làm phép so sánh Unicode duy nhất nếu dự án hỗ trợ nhiều ngôn ngữ; hãy xác định rõ chính sách normalization và case folding.

## 10. Quy trình xử lý lỗi tên tệp trên một nền tảng

Giả sử một thành viên Windows không thể checkout branch vừa được push từ Linux và nhận lỗi liên quan đến tên tệp hoặc đường dẫn dài. Có thể điều tra theo trình tự:

1. Ghi lại chính xác thông báo lỗi và tên đường dẫn Git đang xử lý.
2. Xem trạng thái hiện tại bằng `git status` và không xóa thư mục làm việc đang có dữ liệu.
3. Kiểm tra danh sách tên tracked bằng `git -c core.quotepath=true ls-files` hoặc `git ls-tree -r --name-only <commit>`.
4. Kiểm tra tên có chứa ký tự cấm, tên thiết bị, dấu chấm/dấu cách cuối, va chạm hoa thường hoặc Unicode normalization không.
5. Nếu lỗi là đường dẫn quá dài, thử clone vào thư mục ngắn hơn và kiểm tra `core.longpaths` cùng chính sách Windows.
6. Nếu tên không hợp lệ trên Windows, thực hiện rename ở môi trường có thể truy cập tệp và commit thay đổi.
7. Checkout lại commit đã sửa trên Windows và chạy các bước build/test liên quan.

Các lệnh chẩn đoán đường dẫn dài trên Git for Windows:

```bash
git config --show-origin --get core.longpaths
git config --show-origin --get core.ignoreCase
```

Các lệnh trên chỉ đọc cấu hình. Chỉ bật `core.longpaths` khi cần hỗ trợ đường dẫn dài trên Git for Windows; không đổi `core.ignoreCase` để cố vượt qua giới hạn của filesystem.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Tên tệp hợp lệ trên Linux sẽ hợp lệ ở mọi nơi | Windows có ký tự và tên thiết bị dành riêng; filesystem cũng khác nhau về case sensitivity |
| Hai tên Unicode nhìn giống nhau luôn là cùng một tên | Chuỗi Unicode có thể có dạng mã hóa/chuẩn hóa khác nhau và byte khác nhau |
| Git tự chuẩn hóa mọi tên Unicode | Git lưu đường dẫn trong object/index và không áp đặt một chuẩn hóa Unicode chung cho mọi nền tảng |
| `core.ignoreCase=false` làm Windows phân biệt hoa thường | Cấu hình không thay đổi khả năng so sánh tên của filesystem |
| Bật `core.longpaths` giải quyết mọi lỗi đường dẫn dài | Nó hỗ trợ Git for Windows; editor, IDE, build tool và ứng dụng khác vẫn có giới hạn riêng |
| Git quote ký tự Unicode nghĩa là tên bị hỏng | Quote có thể chỉ là cách biểu diễn output an toàn của Git |
| Rename chỉ khác hoa thường luôn hoạt động giống nhau | Trên filesystem không phân biệt hoa thường, nên dùng tên trung gian và kiểm tra trạng thái |

## 12. Ghi nhớ

Tên đường dẫn trong Git được lưu trong repository, nhưng thao tác với tệp phụ thuộc filesystem và hệ điều hành. Khi xây dựng repository đa nền tảng, hãy chú ý ba nhóm rủi ro chính: Unicode và chuẩn hóa ký tự, khác biệt hoa thường cùng ký tự/tên dành riêng của Windows, và độ dài toàn bộ đường dẫn.

Dùng `git ls-files` hoặc `git ls-tree` để kiểm tra tên đã được lưu; `core.precomposeUnicode` hỗ trợ một số khác biệt Unicode trên macOS; `core.ignoreCase` giúp Git thích nghi với filesystem không phân biệt hoa thường; `core.longpaths` hỗ trợ Git for Windows xử lý đường dẫn dài. Những cấu hình này không thay thế một quy ước tên tệp có tính di động.

Hãy ưu tiên tên rõ ràng, ngắn, nhất quán và có thể checkout trên mọi nền tảng mà nhóm hỗ trợ. Khi gặp lỗi, xác định đúng loại vấn đề trước khi thay đổi cấu hình hoặc rename, rồi xác minh bằng checkout và build trên môi trường bị ảnh hưởng.
