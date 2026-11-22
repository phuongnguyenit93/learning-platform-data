# Cấu hình cone mode và sparse index

Trong một repository lớn, lập trình viên thường chỉ làm việc với một phần mã nguồn, chẳng hạn một dịch vụ backend, một ứng dụng frontend hoặc một nhóm tài liệu. Checkout toàn bộ cây tệp có thể tốn thời gian, dung lượng đĩa và làm IDE phải lập chỉ mục những thư mục không liên quan.

Git sparse-checkout cho phép giới hạn những đường dẫn được hiện diện trong working tree. Trong đó, **cone mode** định nghĩa cách chọn thư mục theo cấu trúc cây; **sparse index** tối ưu cách Git biểu diễn các phần nằm ngoài vùng được checkout trong index. Hai tính năng thường được dùng cùng nhau nhưng giải quyết hai vấn đề khác nhau.

Bài học này hướng dẫn cách bật cone mode, chọn và thay đổi vùng làm việc, bật sparse index, kiểm tra trạng thái và xử lý các giới hạn khi dùng repository lớn hoặc làm việc trên nhiều môi trường.

## 1. Sparse-checkout giải quyết vấn đề gì?

Một clone Git thông thường tạo working tree chứa phần lớn hoặc toàn bộ các tệp được theo dõi trong commit hiện tại. Với monorepo có hàng trăm nghìn tệp, bạn có thể chỉ cần một vài thư mục để phát triển một dịch vụ.

Sparse-checkout cho phép Git chỉ materialize (đưa ra working tree) những đường dẫn nằm trong tập lựa chọn. Những tệp tracked ngoài vùng đó vẫn thuộc lịch sử và cây commit, nhưng thường không xuất hiện trong working tree.

Ví dụ repository:

~~~text
platform/
├── apps/
│   ├── web/
│   └── mobile/
├── services/
│   ├── billing/
│   ├── identity/
│   └── notification/
├── libraries/
├── docs/
├── scripts/
└── README.md
~~~

Nếu bạn chỉ làm việc với dịch vụ billing và tài liệu, có thể chọn:

- `services/billing/`
- `docs/`

Git giữ các tệp cần thiết theo quy tắc sparse-checkout, giảm số lượng tệp xuất hiện trong working tree.

Sparse-checkout chủ yếu kiểm soát working tree và index. Nó không tự động có nghĩa repository đã tải ít lịch sử hoặc ít object hơn. Một clone thông thường vẫn có thể tải phần lớn object của repository dù chỉ hiển thị một phần tệp.

## 2. Cone mode là gì?

### 2.1. Chọn thư mục theo cấu trúc cây

Cone mode là chế độ sparse-checkout được khuyến nghị cho phần lớn workflow. Thay vì cho phép các mẫu glob tùy ý, cone mode chọn các thư mục và áp dụng quy tắc nhất quán dựa trên cấu trúc thư mục.

Bật sparse-checkout ở cone mode:

~~~bash
git sparse-checkout init --cone
~~~

Chọn các thư mục cần làm việc:

~~~bash
git sparse-checkout set services/billing docs
~~~

Các đường dẫn truyền cho `set` là thư mục tương đối từ gốc repository. `set` thay thế tập thư mục đã chọn hiện tại bằng danh sách mới.

### 2.2. Cone mode bao gồm những gì?

Cone mode giữ:

- Các tệp ở gốc repository.
- Các tệp nằm trực tiếp trong những thư mục cha dẫn đến thư mục được chọn.
- Toàn bộ nội dung bên trong các thư mục được chọn, kể cả các thư mục con.

Với lệnh:

~~~bash
git sparse-checkout set services/billing docs
~~~

Working tree có thể chứa:

~~~text
platform/
├── README.md
├── .gitignore
├── services/
│   ├── README.md
│   └── billing/
│       ├── pom.xml
│       └── src/
│           └── ...
└── docs/
    ├── architecture.md
    └── ...
~~~

Các tệp ngay trong `services/` được giữ để có thể đi tới thư mục con `services/billing/`; những thư mục ngang hàng như `services/identity/` không được mở rộng toàn bộ. Thư mục `docs/` được chọn nên nội dung bên trong nó được checkout đệ quy.

Quy tắc này giúp Git tạo tập đường dẫn hiệu quả mà vẫn giữ cấu trúc cha cần thiết.

### 2.3. Cone mode chọn thư mục, không chọn file tùy ý

Cone mode phù hợp khi đơn vị làm việc là thư mục. Ví dụ:

~~~bash
git sparse-checkout set apps/web services/identity
~~~

Nếu bạn muốn chọn một tệp cụ thể nằm sâu trong thư mục hoặc dùng mẫu phức tạp như `src/**/test-*.java`, cone mode không phải cách biểu đạt phù hợp. Khi đó có thể dùng non-cone mode với các pattern tương tự gitignore, nhưng quy tắc khó hiểu hơn và có thể tốn chi phí xử lý hơn trên repository lớn.

Với đa số monorepo, nên tổ chức cấu trúc thư mục sao cho nhóm có thể chọn theo thư mục và dùng cone mode.

## 3. Thiết lập và quản lý vùng sparse-checkout

### 3.1. Khởi tạo cone mode

Từ bất kỳ thư mục con nào bên trong repository, xác nhận repository hiện tại:

~~~bash
git rev-parse --show-toplevel
git status --short --branch
~~~

Sau đó bật cone mode:

~~~bash
git sparse-checkout init --cone
~~~

Lệnh khởi tạo sparse-checkout và cấu hình cone mode. Hãy đọc trạng thái trước khi chạy nếu working tree đang có thay đổi chưa commit.

### 3.2. Chọn vùng làm việc bằng set

Ví dụ chỉ làm việc với frontend và thư mục tài liệu:

~~~bash
git sparse-checkout set apps/web docs
~~~

Lệnh `set` thay thế tập thư mục được chọn. Nếu trước đó bạn chọn `services/billing`, sau lệnh này thư mục đó có thể bị loại khỏi working tree vì không còn thuộc vùng sparse.

Xem danh sách hiện tại:

~~~bash
git sparse-checkout list
~~~

Lệnh này hiển thị các thư mục được chọn trong cone mode.

### 3.3. Thêm thư mục bằng add

Nếu muốn mở rộng vùng làm việc mà vẫn giữ các thư mục hiện có, dùng:

~~~bash
git sparse-checkout add services/identity
~~~

Sau lệnh, vùng được chọn gồm các thư mục cũ và `services/identity`.

Kiểm tra:

~~~bash
git sparse-checkout list
git status --short
~~~

Phân biệt:

- `set`: thay thế tập lựa chọn hiện tại.
- `add`: bổ sung thư mục vào tập lựa chọn.

Đây là khác biệt quan trọng để tránh vô tình loại khỏi working tree một thư mục bạn vẫn cần.

### 3.4. Xem và kiểm tra cấu hình

Có thể kiểm tra các cấu hình liên quan:

~~~bash
git config --show-origin --get core.sparseCheckout
git config --show-origin --get core.sparseCheckoutCone
git config --show-origin --get index.sparse
~~~

Ý nghĩa:

| Cấu hình | Vai trò |
| --- | --- |
| `core.sparseCheckout` | Cho biết sparse-checkout có được bật hay không |
| `core.sparseCheckoutCone` | Cho biết đang dùng cone mode |
| `index.sparse` | Cho biết Git có dùng sparse index hay không |

Không phải mọi khóa đều được ghi tường minh trong cùng file cấu hình; nếu lệnh không in kết quả, có thể khóa chưa được đặt ở các cấp cấu hình được truy vấn.

Có thể xem danh sách đường dẫn được theo dõi:

~~~bash
git ls-files
~~~

Danh sách này có thể lớn tùy cách Git biểu diễn index và tùy chọn hiển thị. Phần tiếp theo trình bày cách kiểm tra sparse index.

## 4. Sparse index là gì?

### 4.1. Index thông thường và chi phí trên monorepo

Index (staging area) lưu thông tin về nội dung được chuẩn bị cho commit. Trong một repository lớn, index thông thường có thể chứa một entry cho từng tệp tracked, kể cả nhiều tệp nằm ngoài vùng sparse-checkout.

Khi số lượng tệp rất lớn, việc đọc và cập nhật index có thể tốn thời gian và bộ nhớ dù working tree chỉ hiển thị một phần repository.

Sparse index tối ưu phần này bằng cách cho phép index biểu diễn một cây thư mục nằm ngoài vùng sparse bằng một **sparse-directory entry**, thay vì mở rộng thành entry riêng cho từng tệp bên trong.

Nhờ vậy, index có thể nhỏ hơn đáng kể trong monorepo có nhiều thư mục không được checkout.

### 4.2. Sparse index không phải là cone mode

Hai khái niệm có vai trò khác nhau:

| Thành phần | Quyết định điều gì? | Lợi ích |
| --- | --- | --- |
| Cone mode | Những thư mục và tệp nào hiện diện trong working tree | Quy tắc chọn đường dẫn đơn giản, hiệu quả |
| Sparse index | Git biểu diễn phần ngoài vùng sparse trong index ra sao | Giảm kích thước index và chi phí xử lý |

Có thể bật cone mode mà không bật sparse index. Sparse index cần cone mode; nó không phải chế độ chọn đường dẫn độc lập.

Một workflow phổ biến là bắt đầu với cone mode, xác nhận vùng làm việc đúng, sau đó bật sparse index nếu repository đủ lớn và công cụ trong nhóm tương thích.

### 4.3. Bật sparse index

Có thể khởi tạo cả hai cùng lúc:

~~~bash
git sparse-checkout init --cone --sparse-index
~~~

Nếu sparse-checkout đã được bật ở cone mode, có thể áp dụng lại cấu hình với sparse index:

~~~bash
git sparse-checkout reapply --sparse-index
~~~

Sau đó kiểm tra cấu hình:

~~~bash
git config --get core.sparseCheckoutCone
git config --get index.sparse
~~~

Sparse index được giới thiệu trong Git 2.32. Đây là tính năng có phạm vi hỗ trợ phụ thuộc phiên bản Git và các lệnh được sử dụng. Với môi trường cũ hơn hoặc công cụ chưa tương thích, hãy dùng cone mode với index thông thường.

### 4.4. Kiểm tra sparse-directory entry

Có thể xem index ở dạng sparse:

~~~bash
git ls-files --sparse
~~~

Khi sparse index được sử dụng, Git có thể hiển thị một số thư mục ngoài vùng checkout như entry thư mục thay vì liệt kê mọi tệp con. Kết quả cụ thể phụ thuộc cấu trúc repository và tập thư mục đã chọn.

Để xem đầy đủ entry và mode:

~~~bash
git ls-files --stage --sparse
~~~

Sparse-directory entry thường có mode dạng `040000`, đại diện cho một cây thư mục. Đừng nhầm entry này với một tệp thư mục thông thường do người dùng tạo; nó là cách index nén biểu diễn một phần cây repository.

Không nên chỉnh sửa index trực tiếp để tạo hoặc xóa các entry này. Hãy dùng các lệnh sparse-checkout để Git quản lý nhất quán.

## 5. Dùng cone mode và sparse index trong một workflow

Giả sử nhóm phát triển monorepo có các thư mục:

~~~text
repo/
├── apps/
│   ├── web/
│   └── mobile/
├── services/
│   ├── billing/
│   ├── identity/
│   └── notification/
├── shared/
├── docs/
└── tools/
~~~

Bạn phụ trách dịch vụ billing và cần dùng thư viện chung cùng tài liệu.

### Bước 1 — Kiểm tra phiên bản và repository

~~~bash
git --version
git rev-parse --show-toplevel
git status --short --branch
~~~

Sparse-checkout có từ Git 2.25. Sparse index cần Git 2.32 trở lên. Nếu lệnh không hỗ trợ, kiểm tra trợ giúp của chính phiên bản đang chạy:

~~~bash
git sparse-checkout -h
git sparse-checkout init -h
~~~

### Bước 2 — Bật cone mode và chọn thư mục

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/billing shared docs
~~~

Working tree sẽ có các tệp gốc, tệp trực tiếp trong các thư mục cha cần thiết và toàn bộ nội dung của các thư mục được chọn.

### Bước 3 — Kiểm tra vùng được chọn

~~~bash
git sparse-checkout list
git status --short
git ls-files
~~~

Mở một vài đường dẫn cần thiết và xác nhận IDE, build script hoặc công cụ dự án có thể truy cập đúng tệp.

### Bước 4 — Bật sparse index nếu phù hợp

~~~bash
git sparse-checkout reapply --sparse-index
git config --get index.sparse
git ls-files --sparse
~~~

Nếu công cụ hoặc lệnh trong môi trường gặp vấn đề với sparse index, có thể chuyển về index đầy đủ nhưng vẫn giữ cone mode:

~~~bash
git sparse-checkout reapply --no-sparse-index
~~~

Việc này không tắt sparse-checkout; nó chỉ thay đổi cách index được biểu diễn.

### Bước 5 — Mở rộng vùng làm việc khi cần

Nếu phải sửa thêm dịch vụ identity:

~~~bash
git sparse-checkout add services/identity
git sparse-checkout list
~~~

Nếu muốn chuyển sang làm frontend và tài liệu thay cho billing:

~~~bash
git sparse-checkout set apps/web docs
~~~

Lệnh `set` thay thế danh sách trước đó. Hãy xác nhận lại vùng làm việc sau mỗi lần thay đổi.

## 6. Thay đổi branch và đồng bộ remote trong sparse checkout

Sparse-checkout không tạo một loại branch riêng. Bạn vẫn dùng các lệnh Git bình thường để chuyển nhánh, fetch, pull, merge, rebase và commit.

Tuy nhiên, nhánh mới có thể có cấu trúc tệp khác với nhánh hiện tại. Git áp dụng các quy tắc sparse-checkout để quyết định tệp nào được materialize. Sau khi thao tác branch hoặc tích hợp, nếu working tree không còn khớp vùng lựa chọn, có thể áp dụng lại:

~~~bash
git sparse-checkout reapply
~~~

Ví dụ:

~~~bash
git fetch origin
git switch feature/billing-v2
git sparse-checkout reapply
git status --short --branch
~~~

Nếu có conflict, giải quyết các tệp cần thiết theo quy trình merge/rebase thông thường. Không xóa thủ công những tệp bị ẩn khỏi sparse view để “làm sạch” conflict; hãy xem `git status` và danh sách unmerged trước.

Các thao tác merge, rebase hoặc công cụ bên ngoài có thể materialize tạm thời một số tệp ngoài vùng sparse. `reapply` giúp Git đưa working tree trở lại tập lựa chọn đã cấu hình sau khi thao tác hoàn tất.

### 6.1. Commit chỉ chứa thay đổi được stage

Sparse-checkout không thay đổi quy tắc commit. Commit vẫn lấy nội dung từ index:

~~~bash
git status
git diff
git diff --cached
git commit -m "Update billing validation"
~~~

Trước commit, kiểm tra index để chắc chắn chỉ có thay đổi dự định. Những tệp ngoài vùng sparse thường không xuất hiện trong working tree, nhưng vẫn thuộc cây commit hiện tại.

Không dùng `git add -A` trên phạm vi quá rộng một cách máy móc nếu chưa kiểm tra tác động. Hãy stage theo đường dẫn hoặc thư mục liên quan và xem `git diff --cached`.

## 7. Sparse-checkout khác partial clone như thế nào?

Hai tính năng thường được kết hợp nhưng không giống nhau.

- **Sparse-checkout:** giới hạn tệp được materialize trong working tree.
- **Partial clone:** giới hạn một số object được tải từ remote, thường bằng object filter.

Một sparse checkout trên clone thông thường vẫn có thể tải toàn bộ hoặc phần lớn blob dù chỉ hiện một phần tệp. Nếu mục tiêu là giảm cả số tệp trong working tree lẫn lượng dữ liệu tải ban đầu, có thể kết hợp partial clone:

~~~bash
git clone --filter=blob:none --sparse <repository-url>
cd <repository-folder>
git sparse-checkout set services/billing shared docs
~~~

Với `--filter=blob:none`, blob được tải khi cần thiết theo cơ chế partial clone. Khi checkout hoặc mở tệp cần blob chưa có local, Git có thể lấy object từ remote nếu promisor remote và kết nối hoạt động.

Partial clone có yêu cầu máy chủ hỗ trợ filter và có thể cần mạng khi truy cập nội dung chưa được tải. Sparse-checkout vẫn là cơ chế quyết định đường dẫn nào xuất hiện trong working tree.

Không nên coi `--sparse` của clone là đồng nghĩa với partial clone. Nó khởi tạo sparse-checkout ban đầu; filter mới quyết định việc trì hoãn tải một số object.

## 8. Giới hạn và lưu ý khi dùng sparse index

### 8.1. Không phải mọi công cụ đều hiểu sparse index

Một số công cụ bên ngoài, IDE, script hoặc phiên bản Git cũ có thể giả định index luôn chứa một entry cho mỗi tệp. Sparse index dùng sparse-directory entry nên các công cụ đó có thể đọc sai hoặc không hỗ trợ.

Các lệnh Git hiện đại thường có thể mở rộng sparse index khi cần để tương thích, nhưng việc mở rộng có thể làm mất lợi ích hiệu năng trong lần chạy đó. Nếu gặp lỗi, kiểm tra phiên bản Git và công cụ đang sử dụng trước khi kết luận repository bị hỏng.

Có thể tạm tắt sparse index:

~~~bash
git sparse-checkout reapply --no-sparse-index
~~~

Cone mode và sparse working tree vẫn được giữ.

### 8.2. Không thao tác trực tiếp với file ngoài vùng sparse

Một đường dẫn không xuất hiện trong working tree không có nghĩa nó bị xóa khỏi repository. Nó vẫn tồn tại trong commit và được quản lý bởi Git.

Không nên tự tạo lại các tệp ngoài vùng sparse bằng cách sao chép từ nơi khác, vì có thể tạo trạng thái khó hiểu giữa index và working tree. Nếu cần một thư mục mới, hãy thêm nó vào tập lựa chọn:

~~~bash
git sparse-checkout add path/to/directory
~~~

Sau khi làm việc, có thể bỏ thư mục khỏi vùng lựa chọn bằng cách dùng `set` với danh sách mới chỉ chứa những thư mục cần giữ.

### 8.3. Tệp untracked và ignored

Sparse-checkout chủ yếu quản lý các đường dẫn tracked. Tệp chưa được theo dõi hoặc bị ignore có quy tắc riêng và có thể vẫn còn trên đĩa dù thư mục tracked tương ứng không còn nằm trong tập sparse.

Trước khi thay đổi vùng lựa chọn hoặc disable, kiểm tra:

~~~bash
git status --short
git status --ignored --short
~~~

Đừng nhầm một tệp untracked hoặc ignored với nội dung được sparse-checkout quản lý.

### 8.4. Disable sparse-checkout

Khi cần quay lại working tree đầy đủ:

~~~bash
git sparse-checkout disable
~~~

Lệnh này tắt sparse-checkout và khôi phục các đường dẫn tracked vào working tree. Với partial clone, Git có thể cần tải thêm object từ remote để materialize đầy đủ nội dung.

Sau đó kiểm tra:

~~~bash
git sparse-checkout list
git status --short --branch
~~~

Nếu sparse-checkout đã bị tắt, lệnh list có thể báo rằng chế độ sparse không hoạt động hoặc không còn cấu hình tương ứng. Hãy kiểm tra working tree và trạng thái repository.

## 9. Xử lý lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `git sparse-checkout` không tồn tại | Git quá cũ hoặc executable khác đang được gọi | Kiểm tra `git --version` và đường dẫn executable; sparse-checkout cần Git 2.25 trở lên |
| `--sparse-index` không được hỗ trợ | Git cũ hoặc lệnh không có tùy chọn đó | Kiểm tra trợ giúp; dùng cone mode với index thông thường |
| Một thư mục biến mất sau `set` | `set` thay thế tập lựa chọn cũ | Dùng `add` để bổ sung hoặc đưa thư mục vào danh sách set mới |
| Working tree có tệp ngoài vùng sparse sau merge | Thao tác có thể materialize tạm thời tệp | Kiểm tra trạng thái và chạy `git sparse-checkout reapply` |
| IDE hoặc script báo lỗi khi sparse index bật | Công cụ chưa hỗ trợ sparse-directory entry | Cập nhật công cụ hoặc dùng `reapply --no-sparse-index` |
| Không mở được nội dung tệp trong partial clone | Blob chưa được tải và remote không truy cập được | Kiểm tra mạng, promisor remote và quyền truy cập |
| `disable` mất nhiều thời gian | Repository có nhiều tệp hoặc cần tải object còn thiếu | Chờ quá trình hoàn tất và kiểm tra kết nối remote nếu dùng partial clone |

Khi có lỗi, kiểm tra theo thứ tự:

~~~bash
git --version
git status --short --branch
git sparse-checkout list
git config --show-origin --get core.sparseCheckout
git config --show-origin --get core.sparseCheckoutCone
git config --show-origin --get index.sparse
~~~

Các lệnh này giúp xác định phiên bản, vùng sparse và cách index đang được cấu hình.

## 10. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Khởi tạo cone mode | `git sparse-checkout init --cone` |
| Khởi tạo cone mode và sparse index | `git sparse-checkout init --cone --sparse-index` |
| Chọn hoặc thay thế thư mục | `git sparse-checkout set services/billing docs` |
| Bổ sung thư mục | `git sparse-checkout add services/identity` |
| Xem thư mục được chọn | `git sparse-checkout list` |
| Áp dụng lại quy tắc sparse | `git sparse-checkout reapply` |
| Bật sparse index khi đã có cone mode | `git sparse-checkout reapply --sparse-index` |
| Tắt sparse index nhưng giữ cone mode | `git sparse-checkout reapply --no-sparse-index` |
| Xem index dạng sparse | `git ls-files --sparse` |
| Xem cấu hình sparse checkout | `git config --get core.sparseCheckout` |
| Xem cấu hình cone mode | `git config --get core.sparseCheckoutCone` |
| Xem cấu hình sparse index | `git config --get index.sparse` |
| Tắt sparse-checkout | `git sparse-checkout disable` |

## 11. Tổng kết

Cone mode và sparse index bổ sung cho nhau trong việc làm việc với repository lớn. Cone mode chọn thư mục theo cấu trúc cây và giúp tập đường dẫn dễ hiểu, dễ duy trì. Sparse index giảm số entry cần lưu trong index bằng cách biểu diễn các thư mục ngoài vùng checkout dưới dạng sparse-directory entry.

Bắt đầu bằng cone mode, chọn đúng thư mục bằng `set`, mở rộng bằng `add` và xác nhận bằng `list`. Chỉ bật sparse index khi phiên bản Git và công cụ trong nhóm hỗ trợ. Sau khi chuyển nhánh hoặc tích hợp thay đổi, dùng `reapply` nếu working tree cần được đưa về vùng lựa chọn. Khi cần làm việc với toàn bộ repository, dùng `disable`.

Cuối cùng, hãy nhớ sparse-checkout chỉ quyết định phần working tree được materialize; nó không tự thay thế partial clone hay xóa lịch sử. Phân biệt đúng hai tính năng giúp bạn chọn cấu hình phù hợp với quy mô repository, giảm chi phí làm việc và tránh nhầm lẫn khi đồng bộ hoặc commit.

