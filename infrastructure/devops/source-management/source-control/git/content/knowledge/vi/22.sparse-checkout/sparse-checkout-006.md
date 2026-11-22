# Sparse checkout giới hạn đường dẫn trong thư mục làm việc

Một repository lớn có thể chứa nhiều ứng dụng, thư viện, tài liệu và công cụ build trong cùng một lịch sử Git. Nếu bạn chỉ làm việc với một vài thư mục, checkout toàn bộ repository có thể khiến thư mục làm việc nặng và khó quan sát. **Sparse checkout** cho phép Git chỉ đưa những đường dẫn được chọn vào working tree, trong khi vẫn làm việc trên cùng repository và lịch sử commit.

Ví dụ, repository có các thư mục `services/`, `libraries/`, `docs/` và `tools/`, nhưng bạn chỉ phát triển `services/payment/`. Sparse checkout có thể giới hạn working tree vào thư mục cần thiết và một số tệp ở cấp cha mà Git cần giữ theo quy tắc sparse checkout.

## 1. Sparse checkout giải quyết vấn đề gì?

Trong repository thông thường, khi checkout một commit, Git tạo working tree từ các tệp được theo dõi trong commit đó. Với monorepo hoặc repository có nhiều thành phần, số lượng tệp có thể rất lớn dù một thành viên chỉ làm việc trên một phần nhỏ.

Sparse checkout giúp:

- Giảm số lượng tệp được đưa ra working tree.
- Làm IDE, trình tìm kiếm và công cụ build tập trung vào phần dự án đang làm.
- Giảm dung lượng working tree và thời gian thao tác với filesystem.
- Cho phép một thành viên chọn thư mục khác nhau theo nhiệm vụ mà không cần tạo repository độc lập cho từng phần.

Sparse checkout điều khiển **những đường dẫn được checkout trong working tree**. Nó không tạo repository mới, không xóa lịch sử commit và không thay đổi nội dung các commit trên branch.

## 2. Sparse checkout hoạt động như thế nào?

Git lưu trạng thái đường dẫn trong index. Khi bật sparse checkout, Git dùng các mẫu (*patterns*) để xác định tệp nào nên xuất hiện trong working tree. Các tệp ngoài phạm vi được chọn thường được đánh dấu bằng bit `skip-worktree` trong index, giúp Git biết rằng chúng được cố ý để ngoài working tree theo cấu hình sparse.

Có thể hình dung repository như sau:

```text
company-platform/
├── services/
│   ├── payment/
│   ├── identity/
│   └── notification/
├── libraries/
│   ├── common/
│   └── security/
├── docs/
└── tools/
```

Nếu chỉ chọn `services/payment/`, working tree sẽ tập trung vào phần đó cùng các tệp ở gốc và thư mục cha cần thiết theo quy tắc cone mode. Những thư mục không được chọn như `services/identity/`, `libraries/` hay `tools/` sẽ không được checkout đầy đủ.

Sparse checkout không phải cơ chế phân quyền. Người dùng vẫn làm việc trong cùng repository; việc giới hạn working tree không ngăn họ truy cập commit hoặc object đã có trong repository bằng các lệnh Git phù hợp.

## 3. Cone mode và non-cone mode

Git hỗ trợ hai cách diễn tả phạm vi sparse checkout.

### Cone mode

Cone mode chọn phạm vi theo thư mục. Đây là cách nên ưu tiên trong phần lớn dự án vì mẫu dễ hiểu, dễ quản lý và Git có thể xử lý hiệu quả hơn trên repository lớn.

Ví dụ:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/payment docs
```

Với hai thư mục trên, cone mode giữ:

- Các tệp ở thư mục gốc repository.
- Các tệp trực tiếp trong những thư mục cha trên đường dẫn đến thư mục được chọn, ví dụ các tệp nằm ngay trong `services/`.
- Toàn bộ nội dung nằm bên trong `services/payment/` và `docs/`, kể cả các thư mục con.

Cone mode không có nghĩa chỉ xuất hiện đúng hai thư mục được nêu. Các tệp ở gốc và tệp trực tiếp trong thư mục cha là một phần của quy tắc cone để hỗ trợ cấu trúc dự án.

### Non-cone mode

Non-cone mode dùng pattern linh hoạt hơn, có thể mô tả phạm vi tệp theo cú pháp gần với `.gitignore`, chẳng hạn chọn hoặc loại trừ theo tên hay vị trí. Cách này hữu ích khi cần chọn một nhóm tệp không thể diễn tả gọn bằng thư mục, nhưng pattern phức tạp hơn và có thể kém hiệu quả trên repository lớn.

Với repository mới hoặc nhu cầu thông thường, nên dùng cone mode. Chỉ dùng non-cone khi thực sự cần biểu đạt phạm vi theo pattern và đã kiểm tra kỹ kết quả.

## 4. Bật sparse checkout cho repository hiện có

Mở terminal tại repository cần cấu hình. Trước khi bật, kiểm tra trạng thái làm việc:

```bash
git status --short --branch
```

Nếu có thay đổi chưa commit, hãy commit hoặc lưu chúng theo quy trình của nhóm trước khi thay đổi phạm vi checkout. Việc thu hẹp working tree có thể làm thay đổi sự hiện diện của các tệp trong thư mục; không nên bắt đầu khi chưa biết rõ trạng thái hiện tại.

Bật sparse checkout ở cone mode:

```bash
git sparse-checkout init --cone
```

Lệnh khởi tạo cấu hình sparse checkout và áp dụng chế độ cone. Khi chưa chỉ định danh sách thư mục, phạm vi ban đầu có thể chỉ bao gồm các tệp ở gốc repository.

Sau đó chọn những thư mục cần làm việc:

```bash
git sparse-checkout set services/payment
```

Git cập nhật danh sách sparse patterns và điều chỉnh working tree theo lựa chọn mới. Nếu cần nhiều thư mục, truyền tất cả trong cùng lệnh:

```bash
git sparse-checkout set services/payment libraries/common docs
```

Lệnh `set` thay thế danh sách thư mục/pattern đang được cấu hình bằng danh sách mới. Vì vậy, nếu muốn giữ các thư mục đã chọn trước đó, hãy liệt kê lại chúng cùng thư mục mới trong lệnh `set`.

## 5. Tạo clone chỉ checkout một phần ngay từ đầu

Nếu chưa có repository local, có thể clone ở chế độ sparse:

```bash
git clone --sparse https://example.com/company/platform.git
```

`--sparse` tạo clone với sparse checkout được bật và working tree ban đầu chỉ đưa các tệp ở cấp gốc ra. Sau đó, đi vào thư mục vừa clone và chọn phạm vi:

```bash
cd platform
git sparse-checkout set services/payment docs
```

Lệnh clone trên vẫn tạo một repository Git bình thường với remote được cấu hình. Sparse checkout giới hạn những gì được checkout ra working tree; nó không mặc nhiên có nghĩa Git chỉ tải object của những thư mục đã chọn.

Nếu muốn giảm cả lượng dữ liệu object tải về, có thể kết hợp partial clone khi máy chủ hỗ trợ:

```bash
git clone --filter=blob:none --sparse https://example.com/company/platform.git
```

`--filter=blob:none` yêu cầu server không gửi các blob ban đầu; Git có thể tải blob cần thiết sau khi chúng được truy cập. Đây là cơ chế khác với sparse checkout và phụ thuộc hỗ trợ của remote server.

## 6. Xem và cập nhật danh sách đường dẫn được chọn

### Xem danh sách sparse patterns

```bash
git sparse-checkout list
```

Trong cone mode, kết quả thường liệt kê các thư mục đã chọn, ví dụ:

```text
docs
services/payment
```

Danh sách này phản ánh phạm vi sparse checkout được cấu hình, không nhất thiết liệt kê mọi thư mục con thực tế xuất hiện trong working tree.

### Thay thế danh sách bằng set

Giả sử ban đầu đã chọn:

```bash
git sparse-checkout set services/payment docs
```

Sau đó bạn chuyển sang nhiệm vụ ở `services/identity/` và vẫn muốn giữ tài liệu:

```bash
git sparse-checkout set services/identity docs
```

Sau lệnh này, `services/payment` không còn nằm trong danh sách được chọn, trừ khi nó được bao phủ bởi một pattern khác.

### Thêm thư mục bằng add

Nếu chỉ muốn bổ sung phạm vi mà vẫn giữ các lựa chọn hiện tại, dùng:

```bash
git sparse-checkout add libraries/security
```

`add` thêm thư mục/pattern vào cấu hình đang có. Đây là lựa chọn thuận tiện khi mở rộng working tree từng bước.

### Kiểm tra lại sau thay đổi

```bash
git sparse-checkout list
git status --short --branch
```

Nên kiểm tra cả danh sách sparse lẫn trạng thái repository sau mỗi lần thay đổi phạm vi để chắc chắn bạn đang làm việc trên đúng phần dự án.

## 7. Cập nhật phạm vi sau khi chuyển branch hoặc pull

Sparse checkout tiếp tục được áp dụng khi bạn chuyển branch hoặc cập nhật lịch sử. Tuy nhiên, branch mới có thể chứa các thư mục hoặc tệp khác với branch trước. Git sẽ áp dụng sparse patterns hiện tại vào nội dung của commit mới.

Ví dụ:

```bash
git switch feature/payment-v2
git pull --ff-only
```

Sau khi chuyển branch hoặc pull, kiểm tra:

```bash
git status
git sparse-checkout list
```

Nếu cần mở rộng phạm vi để sửa một thư mục mới có trong branch đó:

```bash
git sparse-checkout add services/payment-migration
```

Nếu thay đổi branch tạo ra tình huống working tree chưa khớp với sparse patterns, có thể áp dụng lại cấu hình:

```bash
git sparse-checkout reapply
```

`reapply` yêu cầu Git áp dụng lại sparse checkout patterns lên working tree và index. Trước khi dùng, hãy kiểm tra `git status` và bảo toàn thay đổi local; không dùng lệnh này như một cách xóa tùy tiện các tệp đang sửa.

## 8. Khôi phục đầy đủ working tree bằng disable

Khi không còn cần sparse checkout và muốn đưa toàn bộ nội dung được theo dõi trong commit hiện tại trở lại working tree, chạy:

```bash
git sparse-checkout disable
```

Lệnh này tắt sparse checkout và mở rộng working tree về trạng thái checkout đầy đủ. Sau đó kiểm tra:

```bash
git sparse-checkout list
git status --short --branch
```

Khi sparse checkout bị tắt, `git sparse-checkout list` có thể báo cấu hình không còn hoạt động hoặc không có danh sách patterns hiện hành, tùy phiên bản Git. Điều quan trọng là các tệp tracked của commit hiện tại đã được đưa trở lại working tree.

Nếu repository dùng partial clone và một số blob chưa được tải, thao tác mở rộng có thể khiến Git cần truy cập remote để lấy object còn thiếu. Hãy bảo đảm có kết nối và quyền truy cập phù hợp.

## 9. Non-cone mode và pattern theo tệp

Khi cần chọn tệp theo pattern thay vì theo thư mục, có thể khởi tạo non-cone mode:

```bash
git sparse-checkout init --no-cone
```

Sau đó cấu hình các pattern. Ví dụ dưới đây minh họa ý tưởng giữ nội dung gốc và một nhóm đường dẫn cụ thể theo cú pháp pattern:

```bash
git sparse-checkout set --no-cone '/*' '!/*/' '/services/payment/' '/docs/'
```

Non-cone mode dùng quy tắc pattern có tính biểu đạt cao, nhưng các pattern có thể khó đọc và dễ tạo phạm vi ngoài ý muốn. Đặc biệt, pattern bắt đầu bằng `!` có thể loại trừ đường dẫn đã được pattern khác chọn; thứ tự và cách Git khớp pattern cần được kiểm tra trên repository thực tế.

Sau khi cấu hình, kiểm tra danh sách:

```bash
git sparse-checkout list
```

Nếu mục tiêu chỉ là làm việc theo thư mục, cone mode đơn giản và dễ duy trì hơn. Tránh chuyển qua lại giữa cone và non-cone chỉ để thử một pattern mà chưa lưu lại danh sách và hiểu tác động lên working tree.

## 10. Sparse checkout và partial clone khác nhau thế nào?

Hai tính năng này thường được dùng cùng nhau nhưng giải quyết hai vấn đề khác nhau:

| Tính năng | Kiểm soát điều gì? | Tác động chính |
|---|---|---|
| Sparse checkout | Những đường dẫn được checkout trong working tree | Giảm số tệp xuất hiện trong thư mục làm việc |
| Partial clone | Những object Git được tải từ remote | Có thể giảm dữ liệu tải ban đầu, ví dụ trì hoãn blob bằng `--filter=blob:none` |

Chỉ dùng sparse checkout không đảm bảo giảm tương ứng dung lượng object database hoặc lượng lịch sử đã tải. Ngược lại, partial clone không tự giới hạn thư mục xuất hiện trong working tree nếu không kết hợp sparse checkout.

Với repository rất lớn, có thể kết hợp:

```bash
git clone --filter=blob:none --sparse https://example.com/company/platform.git
cd platform
git sparse-checkout set services/payment
```

Hãy kiểm tra khả năng hỗ trợ filter của Git server và chính sách truy cập của tổ chức trước khi chọn cách clone này.

## 11. Giới hạn và lưu ý khi sử dụng

- **Không phải cơ chế bảo mật:** sparse checkout không ngăn người dùng truy cập lịch sử hoặc object đã tải trong repository.
- **Không tự bỏ qua mọi tệp untracked:** sparse patterns chủ yếu kiểm soát đường dẫn tracked được checkout; tệp untracked và ignored cần được quản lý riêng.
- **Cần chú ý thay đổi chưa commit:** trước khi thu hẹp hoặc mở rộng phạm vi, hãy kiểm tra và bảo toàn các thay đổi local.
- **Một số công cụ giả định repository đầy đủ:** IDE, script hoặc build tool có thể cần các thư mục nằm ngoài sparse set. Hãy mở rộng phạm vi nếu công việc cần chúng.
- **Cone mode chọn theo thư mục:** nó cũng giữ tệp ở gốc và tệp trực tiếp trong thư mục cha trên đường dẫn được chọn.
- **Non-cone mode phức tạp hơn:** pattern linh hoạt nhưng khó bảo trì và có thể làm thao tác kém hiệu quả hơn.
- **Partial clone cần remote:** nếu blob chưa được tải, Git có thể cần mạng để lấy chúng khi nội dung được yêu cầu.

Nếu một lệnh Git hoặc công cụ build báo thiếu tệp, trước tiên kiểm tra sparse patterns bằng `git sparse-checkout list`. Đừng kết luận tệp đã bị xóa khỏi repository; có thể nó chỉ nằm ngoài phạm vi checkout hiện tại.

## 12. Quy trình làm việc mẫu trong monorepo

Giả sử bạn cần phát triển dịch vụ thanh toán trong repository có nhiều ứng dụng và thư viện.

```bash
# 1. Clone repository ở chế độ sparse.
git clone --sparse https://example.com/company/platform.git
cd platform

# 2. Chọn thư mục phục vụ công việc.
git sparse-checkout set services/payment libraries/common docs

# 3. Kiểm tra phạm vi đã chọn.
git sparse-checkout list
git status --short --branch

# 4. Tạo branch cho thay đổi.
git switch -c feature/payment-retry

# 5. Sau khi làm việc, kiểm tra diff và commit như bình thường.
git status
git diff
git add services/payment
git commit -m "feat: add payment retry handling"

# 6. Nếu cần thêm thư mục test dùng chung.
git sparse-checkout add tools/test-fixtures

# 7. Khi cần làm việc với toàn repository.
git sparse-checkout disable
```

Các lệnh branch, diff, add và commit vẫn hoạt động theo mô hình Git quen thuộc. Điểm khác biệt là working tree chỉ hiển thị phạm vi được sparse checkout chọn.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Sparse checkout tạo repository nhỏ độc lập | Nó giữ nguyên repository và lịch sử, chỉ giới hạn đường dẫn được checkout trong working tree |
| Thư mục không xuất hiện nghĩa là đã bị xóa khỏi Git | Đường dẫn có thể chỉ đang nằm ngoài sparse patterns |
| `git sparse-checkout set` thêm vào danh sách cũ | `set` thay thế danh sách; dùng `add` để bổ sung |
| Cone mode chỉ giữ đúng thư mục đã chọn | Cone mode còn giữ tệp ở gốc và tệp trực tiếp trong thư mục cha cần thiết |
| Sparse checkout tự giảm toàn bộ dữ liệu tải về | Nó kiểm soát working tree; partial clone mới kiểm soát việc tải object |
| Sparse checkout là cách giới hạn quyền truy cập | Đây không phải cơ chế bảo mật hoặc phân quyền |
| `git sparse-checkout disable` xóa repository | Lệnh tắt chế độ sparse và khôi phục working tree đầy đủ cho commit hiện tại |

## 14. Ghi nhớ

Sparse checkout phù hợp khi repository có nhiều thư mục nhưng công việc chỉ cần một phần. Trong phần lớn trường hợp, hãy dùng cone mode:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/payment docs
git sparse-checkout list
```

Dùng `add` để mở rộng phạm vi, `reapply` để áp dụng lại patterns và `disable` để khôi phục working tree đầy đủ. Trước khi thay đổi phạm vi, kiểm tra `git status` và bảo toàn công việc local. Nếu cần giảm cả lượng object tải về, xem xét kết hợp partial clone như `--filter=blob:none`.

Hãy nhớ sparse checkout chỉ giới hạn những gì được checkout ra working tree. Repository, lịch sử và quyền truy cập Git vẫn tuân theo cấu hình repository cùng quyền remote hiện có.
