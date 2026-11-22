# Phân biệt submodule, subtree và thư mục mã nguồn thông thường

Khi một dự án cần dùng mã nguồn được phát triển ở repository khác, bạn có thể tích hợp mã đó theo nhiều cách. Git submodule giữ repository phụ độc lập và để repository cha ghi nhận một commit cụ thể. Git subtree đưa nội dung repository phụ vào một thư mục trong repository cha và có thể đồng bộ thay đổi với upstream. Một thư mục mã nguồn thông thường chỉ là các file được quản lý trực tiếp bởi repository hiện tại.

Ba lựa chọn có thể tạo ra cấu trúc thư mục nhìn khá giống nhau, nhưng khác nhau về cách lưu lịch sử, clone dự án, cập nhật phiên bản và cộng tác. Chọn đúng mô hình giúp nhóm biết ai quản lý mã nguồn, cách nhận cập nhật và điều gì sẽ xảy ra khi một thành viên clone dự án mới.

## 1. Ba mô hình nhìn từ repository

Giả sử ứng dụng `storefront` cần dùng thư viện `payment-core`.

### Submodule: repository riêng, superproject ghim một commit

```text
storefront/                  # superproject
|-- src/
|-- .gitmodules
|-- .git/
`-- libs/payment-core/       # working tree của repository con
```

Thư mục `libs/payment-core` là một repository Git riêng. Superproject lưu gitlink mode `160000` trỏ đến commit SHA của submodule. File `.gitmodules` công bố path và URL để clone khác biết cách lấy repository con. Lịch sử, branch và remote của thư viện được quản lý trong repository submodule.

### Subtree: nội dung repository phụ nằm trong lịch sử repository cha

```text
storefront/                  # một repository Git
|-- src/
|-- vendor/payment-core/     # các file được lưu trong repository cha
`-- .git/
```

Với cách tích hợp subtree, các file của `payment-core` nằm trực tiếp trong tree của `storefront` dưới prefix `vendor/payment-core`. Có thể dùng công cụ `git subtree` để nhập lịch sử và đồng bộ với repository nguồn. Clone superproject sẽ lấy luôn nội dung thư mục này; không cần khởi tạo một repository con riêng.

### Thư mục thông thường: mã nguồn thuộc hẳn repository hiện tại

```text
storefront/
|-- src/
|-- libs/payment-utils/      # file thông thường của storefront
`-- .git/
```

Các file trong `libs/payment-utils` được stage và commit như mọi file khác của `storefront`. Không có gitlink, không có repository con và cũng không có cơ chế upstream tự động. Nếu mã ban đầu được sao chép từ dự án khác, nhóm tự quản lý việc lấy các bản cập nhật tiếp theo.

## 2. So sánh cách Git lưu dữ liệu

| Tiêu chí | Submodule | Subtree | Thư mục thông thường |
|---|---|---|---|
| Nội dung trong repository cha | Gitlink trỏ đến commit con | File và tree của mã phụ | File và tree thông thường |
| Repository độc lập | Có | Repository nguồn có thể vẫn tồn tại riêng, nhưng bản tích hợp nằm trong repository cha | Không |
| Lịch sử mã phụ | Nằm trong repository submodule | Có thể nhập lịch sử upstream hoặc dùng bản squash | Lịch sử được tạo và quản lý trong repository cha |
| Cách ghim phiên bản | Commit SHA của submodule | Commit/tree trong lịch sử superproject | Commit của superproject |
| Clone dự án | Cần khởi tạo/fetch submodule | Clone superproject lấy luôn nội dung subtree | Clone superproject lấy luôn file |
| Đồng bộ upstream | Fetch và checkout commit submodule | Dùng `git subtree pull`/`push` hoặc quy trình tương ứng | Tự lấy và tích hợp mã nguồn |
| Cấu hình riêng | `.gitmodules` và cấu hình local | Thường không cần `.gitmodules`; công cụ subtree dùng prefix và remote/ref | Không cần cấu hình tích hợp |
| Phù hợp | Thành phần có vòng đời và quyền quản lý riêng | Muốn vendoring nhưng vẫn trao đổi thay đổi với upstream | Mã thuộc cùng dự án, cùng quy trình review và phát hành |

Điểm khác biệt quan trọng nhất: submodule để repository cha tham chiếu đến một repository khác; subtree nhập nội dung mã phụ vào lịch sử repository cha; thư mục thông thường chỉ là cấu trúc file nội bộ, không có quan hệ đồng bộ upstream được Git quản lý.

## 3. Khi nào nên chọn submodule?

Submodule phù hợp khi thành phần phụ có vòng đời độc lập với dự án chính:

- Một thư viện được nhiều repository sử dụng và có nhóm duy trì riêng.
- Dự án cần ghim chính xác một commit của thư viện mà không sao chép toàn bộ lịch sử vào repository cha.
- Nhóm muốn phát hành, review, cấp quyền và quản lý issue của thư viện tại repository riêng.
- Nhiều ứng dụng dùng các phiên bản khác nhau của cùng một thành phần.

Ví dụ thêm submodule:

```bash
git submodule add https://git.example.com/platform/payment-core.git libs/payment-core
git status
git diff --cached
git commit -m "Add payment-core submodule"
```

Git tạo hoặc cập nhật `.gitmodules` và thêm gitlink vào index. Sau khi commit, superproject ghi nhận commit SHA mà submodule đang checkout.

Clone dự án và khởi tạo submodule:

```bash
git clone --recurse-submodules https://git.example.com/platform/storefront.git
```

Nếu đã clone trước đó:

```bash
git submodule update --init --recursive
```

Để cập nhật submodule theo commit được superproject ghim, chạy:

```bash
git submodule update --init --recursive
```

Lệnh này checkout commit đã ghi trong gitlink, thường ở detached `HEAD`. Khi muốn cập nhật lên commit mới, làm việc trong repository con, push commit đó lên remote submodule, rồi stage gitlink và commit superproject. Nhóm cần bảo đảm commit con có thể truy cập được trước khi chia sẻ gitlink mới.

Nhược điểm cần tính đến là quy trình clone và CI phải xử lý submodule, người dùng cần quyền truy cập cả repository cha lẫn repository con, và một gitlink trỏ đến commit chưa được push có thể khiến clone khác không lấy được phiên bản yêu cầu.

## 4. Khi nào nên chọn subtree?

Subtree phù hợp khi bạn muốn mã phụ xuất hiện trực tiếp trong repository chính để việc clone, build và phát triển diễn ra trong một working tree, nhưng vẫn muốn giữ khả năng đồng bộ với repository nguồn.

Các tình huống thường gặp:

- Vendoring một thư viện hoặc công cụ vào repository ứng dụng.
- Môi trường CI cần lấy đủ mã nguồn chỉ bằng một lần clone superproject.
- Thành viên không muốn chạy thêm bước init/update submodule.
- Nhóm muốn nhận bản cập nhật upstream theo đợt và review chúng như thay đổi của repository chính.
- Có thể cần gửi một số sửa đổi ngược lại repository nguồn.

`git subtree` là script hỗ trợ thao tác subtree, thường được phân phối cùng bộ mã nguồn Git trong thư mục `contrib` nhưng không phải bản dựng Git nào cũng cài sẵn lệnh này. Hãy kiểm tra `git subtree -h`; nếu máy không có lệnh, cần cài script theo hướng dẫn của môi trường trước khi dùng.

### Thêm subtree lần đầu

Ví dụ nhập nhánh `main` từ repository `payment-core` vào thư mục `vendor/payment-core`:

```bash
git subtree add --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main --squash
```

- `--prefix=vendor/payment-core`: thư mục trong superproject sẽ chứa mã phụ.
- URL: repository nguồn của subtree.
- `main`: nhánh nguồn được nhập.
- `--squash`: gộp lịch sử nhập thành một commit tổng hợp thay vì đưa toàn bộ chuỗi commit upstream vào lịch sử superproject.

Nếu không dùng `--squash`, `git subtree add` có thể nhập lịch sử commit của repository nguồn và tạo merge commit để kết nối hai lịch sử. Chọn cách squash hay giữ lịch sử đầy đủ theo yêu cầu truy vết và chính sách repository.

### Cập nhật subtree từ upstream

Khi repository nguồn có thay đổi mới:

```bash
git subtree pull --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main --squash
```

Lệnh fetch và tích hợp thay đổi từ nhánh nguồn vào thư mục prefix. Nếu có xung đột, xử lý như conflict trong superproject, kiểm tra nội dung trong `vendor/payment-core`, sau đó hoàn tất merge theo thông báo của Git.

### Gửi thay đổi từ subtree về upstream

Nếu nhóm sửa thư viện trong `vendor/payment-core` và muốn gửi thay đổi ngược về repository nguồn:

```bash
git subtree push --prefix=vendor/payment-core https://git.example.com/platform/payment-core.git main
```

`git subtree push` tạo lịch sử được tách từ prefix và đẩy lên nhánh nguồn theo cách công cụ subtree hỗ trợ. Tài khoản cần có quyền push vào repository nguồn. Nếu dự án chỉ muốn vendoring một chiều, nhóm có thể chỉ dùng `add` và `pull` mà không cần `push`.

Với subtree, nội dung thư viện đã nằm trong commit của superproject. Do đó, khi clone ứng dụng, các file đó sẵn có ngay mà không cần fetch repository phụ riêng. Đổi lại, lịch sử superproject có thể dài hơn nếu nhập toàn bộ lịch sử upstream; lựa chọn `--squash` làm lịch sử gọn hơn nhưng giảm mức độ chi tiết của lịch sử commit upstream trong repository cha.

## 5. Khi nào chỉ cần thư mục mã nguồn thông thường?

Không phải mọi thư mục con đều cần submodule hoặc subtree. Nếu mã nguồn thuộc cùng sản phẩm, cùng nhóm sở hữu và cùng chu kỳ phát hành, hãy quản lý nó như một phần bình thường của repository.

Ví dụ:

```bash
mkdir -p libs/payment-utils
# Thêm các file nguồn vào libs/payment-utils
git add libs/payment-utils
git diff --cached
git commit -m "Add payment utility module"
```

Các file được commit trực tiếp cùng ứng dụng. Branch, tag, review, quyền truy cập và release đều theo repository cha. Cách này đơn giản cho developer và CI; không cần thêm remote hoặc công cụ đồng bộ thành phần.

Nếu thư mục chứa mã được sao chép từ upstream, Git không biết nguồn gốc hoặc cách cập nhật của nó. Khi cần nhận bản mới, nhóm phải chủ động tải, so sánh, cherry-pick, copy hoặc áp dụng patch theo quy trình đã chọn. Nếu việc đồng bộ trở nên thường xuyên hoặc thành phần có chủ sở hữu riêng, hãy đánh giá lại subtree hoặc submodule.

## 6. So sánh quy trình clone và CI

Quy trình clone là khác biệt dễ nhận thấy nhất với người mới tham gia dự án.

| Công việc | Submodule | Subtree | Thư mục thông thường |
|---|---|---|---|
| Clone superproject | Có thể cần `--recurse-submodules` | Clone bình thường | Clone bình thường |
| Cập nhật nội dung phụ | `git submodule update` hoặc workflow theo branch | `git subtree pull` | Cập nhật thủ công |
| Quyền truy cập | Cần quyền với repository con | Chỉ cần quyền đọc superproject để lấy nội dung đã nhập | Chỉ cần quyền đọc superproject |
| Build trong CI | Phải khởi tạo submodule trước khi build | Nội dung có sẵn sau clone | Nội dung có sẵn sau clone |
| Khóa phiên bản | Gitlink ghi commit SHA | Commit superproject ghi nội dung subtree | Commit superproject ghi nội dung thư mục |

Ví dụ bước chuẩn bị CI khi dùng submodule:

```bash
git submodule update --init --recursive
```

Nếu pipeline clone mới, có thể cấu hình clone với `--recurse-submodules`. Khi dùng subtree hoặc thư mục thông thường, không cần bước riêng này vì các file đã nằm trong tree của superproject.

Đừng chỉ so sánh thời gian clone. Hãy tính cả dung lượng lịch sử, số repository cần xác thực, cách cache dependency, khả năng truy cập mạng và mức độ tin cậy của nguồn mã phụ.

## 7. Lịch sử và cách review thay đổi

### Với submodule

Superproject thường hiển thị thay đổi submodule như thay đổi gitlink:

```bash
git diff --submodule
git ls-tree HEAD libs/payment-core
```

Reviewer cần biết commit SHA cũ và mới, đồng thời có thể mở repository con để đọc chi tiết commit. Diff của superproject không tự hiển thị toàn bộ thay đổi từng file bên trong submodule.

### Với subtree

Các file trong prefix là nội dung trực tiếp của superproject. Có thể review bằng diff thông thường:

```bash
git diff -- vendor/payment-core
git log --oneline -- vendor/payment-core
```

Nếu nhập lịch sử đầy đủ, lịch sử upstream có thể được nhìn thấy trong đồ thị commit. Nếu dùng `--squash`, mỗi lần đồng bộ tạo commit tổng hợp đại diện cho trạng thái được nhập; chi tiết commit upstream vẫn có ở repository nguồn.

### Với thư mục thông thường

Review như mọi thay đổi trong repository:

```bash
git diff -- libs/payment-utils
git log --oneline -- libs/payment-utils
```

Git không có thông tin để phân biệt thay đổi nào đến từ upstream nếu nhóm không ghi lại bằng thông điệp commit, metadata hoặc quy trình riêng.

## 8. Quyền sở hữu, phiên bản và bảo trì

Hãy chọn mô hình dựa trên ranh giới sở hữu:

- Nếu thư viện có nhóm duy trì, release và quyền truy cập riêng, submodule giúp giữ ranh giới repository rõ ràng.
- Nếu ứng dụng muốn mang mã phụ theo cùng repository nhưng vẫn nhận bản cập nhật upstream định kỳ, subtree có thể phù hợp.
- Nếu mã chỉ là một phần của ứng dụng và không cần đồng bộ từ repository khác, thư mục thông thường đơn giản nhất.

Submodule ghim commit cụ thể nên giúp tái lập phiên bản phụ, nhưng nhóm vẫn cần bảo đảm commit đó còn được phục vụ bởi remote. Subtree cũng lưu trạng thái nội dung trong commit cha nên checkout lại superproject sẽ lấy đúng phiên bản đã tích hợp. Thư mục thông thường cũng được ghim trong commit cha, nhưng không có quan hệ upstream được Git quản lý.

Với cả ba cách, hãy kiểm tra license, nguồn gốc, quy trình cập nhật bảo mật và người chịu trách nhiệm nâng phiên bản. Việc đưa mã vào subtree hoặc thư mục thường không làm thay đổi nghĩa vụ license của mã nguồn đó.

## 9. Bảng chọn nhanh

| Câu hỏi | Chọn thường phù hợp |
|---|---|
| Thành phần có repository, release và nhóm quản lý riêng? | Submodule |
| Muốn clone một lần có đủ mã phụ và vẫn đồng bộ upstream? | Subtree |
| Mã phụ chỉ là một phần của cùng sản phẩm, không cần upstream độc lập? | Thư mục thông thường |
| Cần nhiều dự án dùng cùng một commit thư viện, nhưng mỗi dự án tự chọn phiên bản? | Submodule |
| Muốn review cập nhật thư viện bằng diff file trong pull request của ứng dụng? | Subtree hoặc thư mục thông thường |
| Không muốn thêm bước khởi tạo repository con trong CI? | Subtree hoặc thư mục thông thường |

Không có lựa chọn nào tốt nhất trong mọi dự án. Hãy ưu tiên mô hình phản ánh đúng cách nhóm sở hữu và phát hành thành phần đó, rồi chuẩn hóa quy trình clone, cập nhật và review tương ứng.

## 10. Bài tập thực hành

Trong môi trường thử nghiệm, chuẩn bị một repository ứng dụng `storefront` và một repository thư viện `payment-core` có ít nhất hai commit.

1. Thêm `payment-core` làm submodule, commit superproject và kiểm tra gitlink bằng `git ls-tree HEAD`.
2. Clone superproject vào thư mục mới mà không dùng `--recurse-submodules`, quan sát trạng thái rồi chạy `git submodule update --init`.
3. Tạo một repository thử nghiệm khác, nhập `payment-core` bằng `git subtree add --prefix=vendor/payment-core ... --squash`.
4. Tạo commit mới trong `payment-core`, rồi cập nhật subtree bằng `git subtree pull`.
5. So sánh `git diff --submodule` với `git diff -- vendor/payment-core` để nhận biết cách review của hai mô hình.
6. Tạo một thư mục mã nguồn thông thường trong `storefront`, stage và commit nó; xác định vì sao Git không biết thư mục này có upstream riêng.
7. Viết một quyết định ngắn cho dự án giả định: mô hình nào phù hợp nếu thư viện có nhóm phát hành riêng, và mô hình nào phù hợp nếu thư viện chỉ được vendoring vào ứng dụng.

Bạn hoàn thành bài tập khi giải thích được superproject lưu gì trong từng mô hình, cách clone lấy mã phụ và cách cập nhật phiên bản từ repository nguồn.
