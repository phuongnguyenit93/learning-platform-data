# Chọn ma trận hệ điều hành và phiên bản theo nhu cầu hỗ trợ

Một dự án có thể chạy trên nhiều hệ điều hành, phiên bản runtime và kiến trúc phần cứng. Kiểm thử mọi tổ hợp trong mọi lần push thường làm pipeline chậm, tốn runner và tạo nhiều kết quả khó xử lý. Ngược lại, chỉ kiểm tra trên một máy Linux mới nhất có thể bỏ sót lỗi chỉ xuất hiện trên Windows, macOS, một bản phân phối Linux cũ hoặc một phiên bản runtime mà khách hàng vẫn đang sử dụng.

Cách chọn ma trận CI hợp lý bắt đầu từ chính sách hỗ trợ của sản phẩm. Nhóm cần biết đang cam kết hỗ trợ những hệ điều hành và phiên bản nào, tổ hợp nào có rủi ro cao, kiểm tra nào phải chạy trước khi merge và kiểm tra nào có thể chạy theo lịch hoặc trước release. Từ đó, matrix trở thành cách thực thi chính sách hỗ trợ và phân bổ chi phí kiểm thử, thay vì một tích Descartes lớn được tạo ra chỉ vì có thể.

Bài này trình bày cách xây dựng ma trận hệ điều hành và phiên bản có căn cứ, phân biệt môi trường runner với môi trường sản phẩm, giảm thời gian phản hồi mà vẫn bảo vệ các cam kết hỗ trợ, và duy trì matrix khi nền tảng CI hoặc vòng đời hệ điều hành thay đổi.

## 1. Ma trận CI biểu diễn điều gì?

Ma trận CI là tập hợp các cấu hình kiểm thử mà pipeline chạy cho cùng một revision. Mỗi cấu hình là một tổ hợp giá trị của các chiều như:

- Hệ điều hành hoặc image runner.
- Phiên bản runtime, ví dụ JDK, Node.js, Python hoặc .NET.
- Kiến trúc CPU, ví dụ x64 hoặc ARM64.
- Phiên bản compiler hoặc build tool.
- Phiên bản dependency hoặc database cần kiểm tra tương thích.
- Loại cấu hình build, ví dụ debug/release hoặc feature profile.

Ví dụ, một thư viện Java có thể cần kiểm tra trên Linux, Windows và macOS, đồng thời hỗ trợ JDK 17 và 21. Ma trận đơn giản có ba hệ điều hành nhân hai phiên bản JDK, tức sáu cấu hình.

| Hệ điều hành | JDK | Câu hỏi kiểm tra |
|---|---:|---|
| Linux | 17 | Phiên bản runtime tối thiểu có build và test được không? |
| Linux | 21 | Phiên bản runtime mới hơn có tương thích không? |
| Windows | 17 | File path, process và shell behavior có đúng không? |
| Windows | 21 | Tổ hợp Windows/runtime mới có lỗi riêng không? |
| macOS | 17 | Có lỗi phụ thuộc hệ thống hoặc toolchain không? |
| macOS | 21 | Phiên bản runtime mới có hoạt động trên macOS không? |

Một matrix có thể chạy nhiều job song song, nhưng số job tăng sẽ làm tăng thời gian chờ runner, mức sử dụng quota và số kết quả cần phân tích. Vì vậy, không nên chọn tổ hợp chỉ theo số lượng phiên bản có thể khai báo.

## 2. Bắt đầu từ chính sách hỗ trợ của sản phẩm

Nguồn sự thật đầu tiên là chính sách hỗ trợ, không phải danh sách runner có sẵn trên nền tảng CI.

Chính sách cần trả lời:

- Sản phẩm hỗ trợ hệ điều hành nào?
- Phiên bản tối thiểu và phiên bản mới nhất được hỗ trợ là gì?
- Có hỗ trợ nhiều bản phân phối Linux hay chỉ một họ phân phối?
- Có hỗ trợ cả x64 và ARM64 không?
- Runtime nào là mức tối thiểu, mức khuyến nghị và mức đang được thử nghiệm?
- Phiên bản nào chỉ được hỗ trợ trong một thời gian chuyển tiếp?
- Phiên bản nào đã hết hỗ trợ và không còn nằm trong cam kết?
- Có tổ hợp nào bị loại trừ vì dependency hoặc vendor không hỗ trợ?

Nên phân loại rõ:

| Trạng thái hỗ trợ | Ý nghĩa | Kỳ vọng kiểm thử |
|---|---|---|
| Supported | Có cam kết hỗ trợ chính thức | Phải có kiểm thử tự động phù hợp |
| Best effort | Có thể hoạt động nhưng không cam kết đầy đủ | Kiểm tra đại diện hoặc theo lịch |
| Preview/experimental | Đang đánh giá, có thể thay đổi | Pipeline riêng, không chặn mọi PR trừ khi cần |
| Deprecated | Đã thông báo ngừng hỗ trợ | Tiếp tục kiểm tra trong giai đoạn chuyển tiếp |
| Unsupported | Không còn cam kết | Không đưa vào release gate |

Nếu tài liệu sản phẩm tuyên bố hỗ trợ Windows và Linux nhưng pipeline chỉ kiểm tra Ubuntu, matrix đang không phản ánh cam kết. Ngược lại, nếu sản phẩm chỉ hỗ trợ Linux, chạy toàn bộ test trên macOS và Windows ở mọi PR có thể không tạo thêm giá trị.

Chính sách hỗ trợ nên có owner, ngày rà soát và tiêu chí loại bỏ phiên bản. Matrix CI cần được cập nhật khi chính sách thay đổi.

## 3. Phân biệt runner OS với target OS

Runner OS là hệ điều hành nơi job CI thực thi. Target OS là hệ điều hành hoặc môi trường mà sản phẩm được thiết kế để chạy. Hai khái niệm có thể giống nhau nhưng không bắt buộc.

Ví dụ:

- CI chạy trên Ubuntu để cross-compile binary Windows.
- Job chạy trên macOS để ký package cho Apple platform.
- Container build chạy trên Linux nhưng tạo image chạy trong một distro Linux khác.
- CI chạy trên Windows để build ứng dụng .NET dành cho Windows.
- Pipeline chạy trên runner ARM64 để kiểm tra binary ARM64.

Chạy build trên Ubuntu không chứng minh ứng dụng hoạt động trên Windows. Nếu cần xác minh hành vi Windows, test phải chạy trên runner Windows hoặc môi trường Windows tương đương được hỗ trợ.

Ngược lại, nếu chỉ kiểm tra logic Java thuần không phụ thuộc OS, một số test có thể chạy trên một runner đại diện; các kiểm tra file system, shell, process, path, line ending, native library và packaging mới cần trải rộng trên từng OS.

Hãy ghi rõ mục tiêu của từng job: kiểm tra khả năng build trên runner, kiểm tra runtime trên target hay kiểm tra package được tạo cho target cụ thể.

## 4. Chọn mức chi tiết của hệ điều hành

"Hỗ trợ Linux" có thể bao gồm nhiều môi trường khác nhau: Ubuntu, Debian, Fedora, RHEL-compatible, Alpine hoặc image tối giản. Chúng khác nhau về libc, package manager, đường dẫn thư viện, shell và phiên bản package.

Cần xác định mức cam kết:

- Hỗ trợ một distro và phiên bản cụ thể.
- Hỗ trợ một họ distro, ví dụ Debian-based.
- Hỗ trợ mọi distro đáp ứng yêu cầu runtime.
- Chỉ hỗ trợ container image do dự án phát hành.
- Hỗ trợ một danh sách target image do khách hàng lựa chọn.

Nếu sản phẩm chỉ chạy trong container image do nhóm cung cấp, matrix có thể tập trung vào image đó và các kiến trúc được công bố. Nếu phát hành package native cho nhiều distro, cần kiểm tra từng nền tảng ABI hoặc nhóm tương thích có rủi ro riêng.

Alpine dùng musl libc trong khi nhiều Linux distribution phổ biến dùng glibc. Một binary native được build trên Ubuntu có thể không chạy trên Alpine nếu không được build hoặc đóng gói phù hợp. Chỉ ghi "Linux" trong matrix sẽ che mất khác biệt quan trọng này.

## 5. Chọn phiên bản theo vòng đời và cam kết

Không nhất thiết kiểm tra mọi phiên bản đã từng tồn tại. Nên chọn dựa trên vòng đời hỗ trợ và khả năng tương thích.

Một chính sách thường gặp:

- **Minimum supported:** phiên bản cũ nhất mà sản phẩm còn cam kết.
- **Current stable/LTS:** phiên bản chính đang được khuyến nghị.
- **Latest supported:** phiên bản mới nhất nằm trong phạm vi hỗ trợ.
- **Next version:** phiên bản sắp phát hành để phát hiện sớm thay đổi.
- **Deprecated version:** chỉ kiểm tra trong thời gian chuyển tiếp nếu còn cần duy trì cam kết.

Ví dụ thư viện Java có thể hỗ trợ JDK 17 và 21. JDK 17 đại diện mức tối thiểu, JDK 21 đại diện phiên bản LTS mới hơn. Một feature release mới hơn, chẳng hạn JDK 26 trong giai đoạn đánh giá của dự án, có thể chạy ở job preview theo lịch thay vì điều kiện bắt buộc của mọi PR.

Không dùng từ "latest" mà không có định nghĩa. Latest có thể thay đổi theo thời gian và làm kết quả pipeline khó tái lập. Hãy dùng phiên bản cụ thể hoặc một kênh preview được quản lý rõ.

## 6. Chọn tổ hợp theo rủi ro thay vì nhân mọi chiều

Giả sử dự án có 3 hệ điều hành, 3 phiên bản JDK, 2 kiến trúc CPU và 2 database version. Full Cartesian matrix có \(3 \times 3 \times 2 \times 2 = 36\) job. Nếu mỗi job mất 8 phút và chạy song song tối đa 6 runner, thời gian và chi phí vẫn đáng kể; nếu quota runner thấp, queue có thể kéo dài.

Không phải mọi tổ hợp đều có ý nghĩa. Có thể database chỉ được kiểm thử trên Linux; macOS chỉ cần một JDK; ARM64 chỉ là target Linux; Windows chỉ hỗ trợ JDK 17 và 21. Khi đó, ma trận nên mô tả những tổ hợp hợp lệ thay vì tạo mọi kết hợp rồi để job thất bại vì cấu hình không được hỗ trợ.

Một cách chọn:

1. Liệt kê các tổ hợp sản phẩm thực sự hỗ trợ.
2. Xác định tổ hợp tối thiểu cần chặn merge.
3. Đánh dấu tổ hợp có lịch sử lỗi hoặc khác biệt nền tảng.
4. Chọn tổ hợp đại diện cho nightly.
5. Chọn tổ hợp đầy đủ cho release hoặc pre-release.
6. Loại bỏ tổ hợp không có giá trị kiểm thử và ghi rõ lý do.

Matrix tốt là matrix có lý do cho từng hàng, không phải matrix có số job lớn nhất.

## 7. Phân tầng kiểm thử: pull request, nightly và release

Một cách cân bằng phản hồi nhanh với độ bao phủ là dùng nhiều tầng matrix.

| Tầng | Mục tiêu | Matrix gợi ý | Khi chạy |
|---|---|---|---|
| Pull request | Phát hiện lỗi phổ biến nhanh | OS đại diện + runtime tối thiểu và hiện hành | Mỗi PR |
| Merge/main | Kiểm tra rộng hơn sau khi tích hợp | Các OS được hỗ trợ và phiên bản chính | Mỗi lần merge |
| Nightly | Bao phủ tổ hợp ít chạy, phiên bản preview và kiến trúc phụ | Matrix rộng hoặc pairwise | Theo lịch |
| Release candidate | Xác nhận toàn bộ cam kết phát hành | Full supported matrix | Trước release |
| Scheduled compatibility | Phát hiện thay đổi từ runner, dependency và upstream | Phiên bản kế tiếp hoặc image cập nhật | Theo lịch |

Không nên để mọi PR chờ 36 tổ hợp nếu chỉ một vài tổ hợp có giá trị phản hồi nhanh. Tuy nhiên, mọi tổ hợp được cam kết hỗ trợ vẫn cần có đường kiểm tra trước khi release.

Nếu một tổ hợp chỉ chạy nightly và liên tục thất bại, nhóm cần quyết định có sửa, giới hạn hỗ trợ hay thay đổi tầng kiểm tra. Không để job đỏ tồn tại lâu đến mức mọi người bỏ qua cảnh báo.

## 8. Chọn tổ hợp đại diện cho pull request

Ma trận PR cần nhỏ nhưng có khả năng bắt lỗi có xác suất cao.

Ví dụ:

- Linux + minimum JDK để phát hiện việc vô tình dùng API mới hơn mức tối thiểu.
- Linux + latest supported JDK để kiểm tra runtime hiện hành.
- Windows + JDK hiện hành để phát hiện lỗi path, process và shell.
- macOS + JDK hiện hành nếu macOS nằm trong cam kết hỗ trợ.
- Một kiến trúc phụ nếu dự án có binary native hoặc dependency khác biệt.

Có thể chọn 3–5 cấu hình thay vì toàn bộ 12 hoặc 24 tổ hợp. Số lượng thực tế phụ thuộc thời gian test, lịch sử lỗi và mức độ khác biệt giữa nền tảng.

PR matrix không nên chỉ gồm phiên bản mới nhất. Nếu sản phẩm còn hỗ trợ runtime cũ, lỗi do vô tình dùng API mới có thể chỉ xuất hiện ở minimum version. Kiểm tra minimum supported là một lớp bảo vệ quan trọng.

## 9. Khi nào cần full matrix?

Full matrix có giá trị khi xác nhận cam kết release, kiểm tra tương tác giữa các chiều hoặc điều tra lỗi chỉ xuất hiện trên một tổ hợp cụ thể.

Nên chạy full matrix:

- Trước khi phát hành phiên bản chính thức.
- Khi thay đổi build tool, compiler hoặc runtime.
- Khi thay đổi code liên quan đến OS-specific behavior.
- Khi cập nhật dependency có native library.
- Khi thay đổi packaging, installer hoặc signing.
- Khi thêm/bỏ OS hoặc phiên bản trong support policy.
- Khi một lỗi đã được báo cáo trên tổ hợp ít phổ biến.
- Theo lịch nếu sản phẩm cần theo dõi drift từ runner image hoặc upstream.

Full matrix không nhất thiết phải chạy lại toàn bộ integration test nặng ở mọi tổ hợp. Có thể tách compile/package/smoke và test sâu, miễn là release policy ghi rõ bằng chứng cần có cho từng target.

## 10. Dùng pairwise testing khi số chiều tăng

Khi matrix có nhiều chiều, pairwise testing có thể giảm số tổ hợp bằng cách bảo đảm mọi cặp giá trị giữa các chiều xuất hiện ít nhất một lần.

Ví dụ, thay vì chạy toàn bộ tổ hợp OS × JDK × database × architecture, nhóm chọn một tập nhỏ hơn để bao phủ các cặp có thể tương tác.

Pairwise hữu ích khi:

- Có nhiều chiều cấu hình.
- Phần lớn lỗi dự kiến đến từ tương tác giữa hai yếu tố.
- Chạy full matrix quá tốn thời gian.
- Có thể chạy full matrix ở một tầng khác như release hoặc nightly.

Pairwise không thay thế các tổ hợp bắt buộc. Nếu sản phẩm cam kết Windows + JDK 17 + x64, tổ hợp đó phải được kiểm tra trực tiếp dù thuật toán pairwise không chọn nó. Những tổ hợp có lịch sử lỗi hoặc có dependency native cũng nên được pin vào matrix.

Đối với lỗi tương tác ba hoặc nhiều chiều, pairwise có thể bỏ sót. Cần dùng risk-based selection hoặc t-wise testing cho khu vực có rủi ro cao.

## 11. Tách ma trận build, test và packaging

Không phải mọi bước đều cần chạy trên mọi tổ hợp.

Một pipeline có thể chia:

- **Build/compile matrix:** kiểm tra code biên dịch trên runtime và toolchain cần hỗ trợ.
- **Unit test matrix:** chạy logic độc lập trên các OS/runtime đại diện.
- **Integration matrix:** chạy trên những tổ hợp mà dependency hoặc behavior khác biệt.
- **Packaging matrix:** tạo package cho từng target OS/architecture.
- **Release verification:** kiểm tra package thực tế trên target tương ứng.

Ví dụ, Java bytecode có thể build một lần bằng JDK được quy định rồi chạy test trên nhiều OS và JRE. Nhưng nếu build script có native tool hoặc shell script theo OS, build cũng cần chạy trên các runner tương ứng.

Tách job giúp tránh build lại không cần thiết và làm rõ lỗi thuộc compile, test hay packaging. Tuy nhiên, nếu artifact được tạo trên Linux rồi đưa sang Windows, phải xác minh artifact đó thực sự portable và không phụ thuộc path hoặc file metadata của Linux.

## 12. Ví dụ GitHub Actions với matrix tường minh

Ví dụ dưới đây chọn các tổ hợp đại diện thay vì nhân mọi hệ điều hành với mọi JDK:

```yaml
name: Supported platform checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        include:
          - os: ubuntu-24.04
            java: '17'
            tier: pr
          - os: ubuntu-24.04
            java: '21'
            tier: pr
          - os: windows-2025
            java: '21'
            tier: pr
          - os: macos-15
            java: '21'
            tier: pr

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}

      - name: Run tests on Unix-like runner
        if: runner.os != 'Windows'
        run: ./gradlew test

      - name: Run tests on Windows
        if: runner.os == 'Windows'
        run: .\gradlew.bat test
```

Trong ví dụ, runs-on và java-version tham chiếu trực tiếp giá trị của từng hàng matrix. Cần pin action theo chính sách của tổ chức; ví dụ dùng tag phiên bản để dễ đọc, còn môi trường production có thể yêu cầu pin commit SHA.

Các điểm cần lưu ý:

- include khai báo đúng các tổ hợp được chọn.
- max-parallel giới hạn số job chạy đồng thời để kiểm soát quota.
- fail-fast: false giúp các tổ hợp khác tiếp tục chạy và cung cấp nhiều tín hiệu hơn khi một platform thất bại.
- runner.os được dùng để chọn lệnh phù hợp cho Windows và Unix-like.
- Phiên bản JDK được truyền theo từng hàng matrix.
- Test được thực hiện trên từng runner OS đã chọn.

Với repository có workflow cần phản hồi rất nhanh, có thể dùng matrix PR nhỏ hơn và workflow nightly riêng cho các tổ hợp còn lại.

## 13. Dùng exclude và include có chủ đích

Trong GitHub Actions, matrix có thể được tạo từ các danh sách và sau đó điều chỉnh bằng exclude/include.

Ví dụ:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04, windows-2025, macos-15]
    java: ['17', '21']
    exclude:
      - os: macos-15
        java: '17'
    include:
      - os: ubuntu-24.04
        java: '26'
        tier: preview
```

Exclude loại bỏ tổ hợp không hỗ trợ hoặc không có ý nghĩa. Include thêm một cấu hình riêng, ví dụ JDK preview chỉ chạy trên Linux.

Không dùng exclude để che lỗi test hoặc tránh một tổ hợp đang thất bại mà không có quyết định hỗ trợ. Mỗi exclusion nên có lý do, owner và ngày xem xét. Nếu một tổ hợp không hỗ trợ, chính sách sản phẩm và tài liệu cần phản ánh điều đó.

Khi matrix dùng include để thêm thuộc tính, cần hiểu cách nền tảng ghép giá trị vào các tổ hợp hiện có. Nếu muốn kiểm soát chính xác từng cấu hình, khai báo danh sách object trong include thường dễ đọc và ít gây nhầm hơn.

## 14. Chọn fail-fast phù hợp

fail-fast quyết định điều gì xảy ra khi một cấu hình trong matrix thất bại.

**Bật fail-fast** có thể dừng các job matrix còn lại khi có lỗi. Điều này tiết kiệm runner và hữu ích nếu mọi cấu hình đều thực hiện cùng một phép kiểm tra nhanh, một lỗi đã đủ chặn PR.

**Tắt fail-fast** cho phép các cấu hình còn lại tiếp tục, hữu ích khi cần biết lỗi có chỉ xuất hiện trên Windows, macOS hoặc một runtime cụ thể không.

Một chiến lược thường dùng:

| Tầng | fail-fast | Lý do |
|---|---|---|
| PR smoke matrix | Có thể bật | Phản hồi sớm và giảm chi phí |
| PR platform matrix nhỏ | Thường tắt nếu cần chẩn đoán | Thu thập kết quả từ các OS |
| Nightly full matrix | Tắt | Cần báo cáo đầy đủ tổ hợp |
| Release matrix | Tắt hoặc theo policy | Cần bằng chứng cho từng target |
| Exploratory preview | Tắt | Quan sát nhiều phiên bản mà không dừng sớm |

Không nhầm fail-fast của matrix với việc một test case dừng suite bên trong runner. Hai cơ chế có phạm vi khác nhau.

## 15. Kiểm soát số job và thời gian phản hồi

Thời gian pipeline không chỉ là thời gian chạy một job. Nó còn phụ thuộc queue, giới hạn runner, thời gian setup và thời gian tổng hợp kết quả.

Các cách giảm thời gian:

- Chạy song song các tổ hợp độc lập trong giới hạn quota.
- Dùng PR matrix nhỏ, nightly/release matrix rộng.
- Cache dependency theo OS, architecture và toolchain.
- Tránh cài đặt lại dependency ở mỗi step không cần thiết.
- Tách smoke test nhanh khỏi integration test nặng.
- Dùng runner phù hợp với workload và thời gian khởi động.
- Chạy các kiểm tra có giá trị cao sớm.
- Dừng sớm ở tầng PR khi có lỗi chắc chắn chặn merge, nếu không cần chẩn đoán toàn matrix.

Không tăng max-parallel vượt quá khả năng runner hoặc quota của tổ chức. Nếu job chỉ mất 5 phút nhưng phải chờ 20 phút trong queue, thêm job song song có thể làm mọi pipeline khác chậm hơn.

Theo dõi cả thời gian queue và thời gian thực thi. Hai chỉ số này cần cách xử lý khác nhau.

## 16. Cache phải tách theo môi trường tương thích

Cache dependency hoặc build output không nên được chia sẻ mù quáng giữa các OS, architecture hoặc phiên bản toolchain khác nhau.

Cache key nên phản ánh các yếu tố có thể làm nội dung cache không tương thích:

- Runner OS hoặc distro.
- Architecture.
- JDK/runtime version.
- Build tool version.
- Lockfile hoặc dependency manifest hash.
- Compiler flags và build profile nếu ảnh hưởng output.

Ví dụ một cache key logic:

```text
gradle-OS-ARCH-JDK-VERSION-LOCKHASH
```

Nếu dùng cache chung cho Windows và Linux, có thể gặp path, permission hoặc file format khác nhau. Với native compilation, architecture và ABI đặc biệt quan trọng.

Cache là tối ưu hiệu năng, không phải nguồn chuẩn của artifact. Khi cache bị xóa, build phải có thể tái tạo từ source và dependency đã khóa. Artifact phát hành cần được lưu trong repository riêng.

## 17. Runner image và tính tái lập

Runner label như ubuntu-24.04 hoặc windows-2025 thường biểu thị một image do nền tảng quản lý. Nội dung image có thể được cập nhật theo thời gian: compiler, SDK, system package hoặc tool được cài sẵn có thể thay đổi.

Điều này có thể làm cùng một commit cho kết quả khác nhau ở hai thời điểm.

Để kiểm soát:

- Dùng runner label cụ thể thay vì alias latest nếu nền tảng cung cấp.
- Pin version toolchain trong workflow.
- Ghi lại runner image/version nếu nền tảng cung cấp.
- Dùng container image theo digest cho job có thể chạy trong container.
- Cập nhật runner image có lịch và quan sát.
- Chạy scheduled compatibility test để phát hiện thay đổi upstream.
- Lưu metadata build để điều tra khác biệt.

Không phải mọi runner image đều có thể pin hoàn toàn. Với hosted runner, nhà cung cấp vẫn có thể cập nhật image theo chính sách. Hãy ghi nhận giới hạn này và dùng toolchain pinning để giảm biến động.

## 18. Kiểm tra khác biệt đặc thù từng hệ điều hành

Các lỗi chỉ xuất hiện trên một OS thường đến từ khác biệt môi trường hơn là logic nghiệp vụ.

| Khác biệt | Rủi ro | Kiểm tra nên có |
|---|---|---|
| File path separator | Dùng slash/backslash sai | Test path qua API chuẩn của ngôn ngữ |
| Case sensitivity | Tên file khác chữ hoa/thường | Test trên filesystem phân biệt hoa thường |
| Line endings | Script hoặc fixture bị CRLF/LF khác nhau | Kiểm tra checkout và script execution |
| File permission | Script không có execute bit | Test packaging và permission |
| Process/signal | Cách dừng process khác nhau | Test start/stop và cleanup |
| Shell | Bash, PowerShell, cmd có cú pháp khác | Chọn shell tường minh |
| Native library | ABI hoặc libc khác nhau | Test trên target image/architecture |
| Symlink | Quyền và hành vi khác nhau | Test install/unpack |
| Encoding/locale | Default locale khác nhau | Test Unicode và định dạng |
| Certificate store | Trust store khác nhau | Test TLS trên target OS |

Không nên dùng chuỗi path tự ghép nếu thư viện chuẩn có API xử lý path. Không nên giả định mọi runner đều có Bash hoặc cùng phiên bản shell. Workflow cần chỉ định shell phù hợp và kiểm tra tool prerequisite.

## 19. Linux matrix: distro, libc và container base image

Với sản phẩm chạy trên Linux, cần xác định liệu hỗ trợ dựa trên distro cụ thể hay ABI/runtime.

Các điểm cần kiểm tra:

- glibc hay musl.
- Phiên bản libc tối thiểu.
- OpenSSL và thư viện native.
- Package manager và tên package.
- User/group mặc định trong container.
- Certificate authority bundle.
- Shell và core utilities.
- CPU architecture.
- Kernel feature nếu ứng dụng phụ thuộc.

Nếu image production là Alpine, chạy test chỉ trên Ubuntu không đủ. Nếu ứng dụng chạy trong image distroless, cần test image thực tế hoặc một môi trường tương đương để xác minh startup, health và certificate.

Không nhất thiết đưa mọi distro vào mọi PR. Có thể chọn distro đại diện ở PR, image phát hành ở release và các distro bổ sung trong nightly. Nhưng mọi target image được công bố phải có một bước xác minh trực tiếp.

## 20. Windows và macOS cần kiểm tra riêng

Windows và macOS có những yêu cầu build/test khác Linux.

**Windows:**

- Đường dẫn có drive letter và giới hạn path.
- Quy tắc file locking và xóa file đang mở.
- PowerShell/cmd/Git Bash.
- File permission và executable behavior.
- Native DLL, signing và installer.
- Process termination và service management.
- Line endings và case-insensitive filesystem.

**macOS:**

- Phiên bản SDK và Xcode nếu build native.
- Kiến trúc Intel và Apple Silicon nếu còn hỗ trợ.
- Code signing, notarization và entitlement.
- Keychain/certificate handling.
- Filesystem và permission behavior.
- Khác biệt giữa runner image và target macOS version.

Nếu sản phẩm không phát hành cho một OS, không cần giả lập toàn bộ kiểm tra platform đó. Nếu có phát hành, cần test package thực tế trên target và xác minh bước signing/installer tương ứng.

## 21. Kiểm tra kiến trúc CPU khi có native dependency

Một matrix có thể cần thêm architecture dimension khi binary hoặc dependency có mã native.

Ví dụ:

- Linux x64 và ARM64.
- macOS Apple Silicon.
- Windows x64 hoặc ARM64.
- Container image đa kiến trúc.

Không phải mọi dependency Java đều thuần Java. JNI, compression library, database driver native hoặc công cụ build có thể phụ thuộc kiến trúc.

Cần phân biệt:

- Runner architecture: nơi job thực thi.
- Build target architecture: kiến trúc binary được tạo.
- Runtime architecture: kiến trúc nơi binary được chạy.

Cross-compilation có thể tạo binary cho target khác runner, nhưng không thay thế hoàn toàn test runtime trên target architecture. Nếu không có runner thật, có thể dùng emulator hoặc container phù hợp, nhưng cần ghi rõ giới hạn và vẫn kiểm tra release trên thiết bị/runner mục tiêu khi rủi ro cao.

## 22. Chọn phiên bản runtime và toolchain độc lập

Một lỗi thường gặp là dùng một chiều version chung cho tất cả công cụ. Runtime ứng dụng, compiler, build tool và test runtime có thể có vòng đời khác nhau.

Ví dụ Java:

- Compile toolchain có thể là JDK 21.
- Bytecode target có thể là Java 17.
- Unit test có thể chạy trên JDK 17 và 21.
- Gradle wrapper có version riêng.
- Plugin Gradle có giới hạn JDK riêng.

Nếu sản phẩm hỗ trợ Java 17, chỉ chạy build trên JDK 21 mà không đặt target release có thể vô tình tạo bytecode hoặc dùng API không có trên Java 17.

Cần xác định rõ:

| Thành phần | Câu hỏi |
|---|---|
| Compiler JDK | Dùng JDK nào để biên dịch? |
| Target bytecode/API | Sản phẩm cần tương thích mức Java nào? |
| Test runtime | Cần chạy trên những JDK nào? |
| Build tool | Gradle/Maven version nào được hỗ trợ? |
| Plugin | Plugin có tương thích với JDK/build tool không? |
| Runtime image | Production chạy trên JRE/JDK hoặc base image nào? |

Với ngôn ngữ khác, nguyên tắc tương tự áp dụng cho compiler, SDK, package manager, runtime và target framework.

## 23. Kiểm tra version mới trước khi thêm vào support matrix

Phiên bản mới của OS hoặc runtime có thể thay đổi API, compiler warning, TLS default, certificate store, package manager hoặc behavior hệ thống.

Không nên thêm version mới vào cam kết hỗ trợ chỉ vì runner đã xuất hiện. Trước tiên:

1. Tạo job preview hoặc scheduled compatibility.
2. Build và chạy unit test.
3. Chạy integration test có dependency quan trọng.
4. Kiểm tra packaging và installer.
5. Kiểm tra native library và security provider.
6. Chạy smoke test trên target.
7. Theo dõi lỗi và hiệu năng.
8. Quyết định trạng thái preview, supported hoặc unsupported.

Tương tự, khi version cũ sắp hết hỗ trợ, cần kiểm tra dependency và người dùng còn sử dụng nó. Thông báo deprecation trước khi loại bỏ khỏi matrix và sản phẩm.

## 24. Xử lý tổ hợp không hỗ trợ và lỗi hạ tầng

Một tổ hợp có thể không chạy vì cấu hình không được hỗ trợ, hoặc vì runner/infra tạm thời gặp sự cố. Hai trường hợp cần được phân biệt.

| Kết quả | Ví dụ | Hành động |
|---|---|---|
| Product incompatibility | Runtime mới không tương thích dependency | Sửa code hoặc cập nhật support policy |
| Unsupported combination | OS/version ngoài cam kết | Exclude có lý do, không tính là product failure |
| Runner outage | Hosted runner không cấp máy | Retry hoặc chờ hạ tầng |
| Download failure | SDK mirror hoặc package registry lỗi | Retry có giới hạn, kiểm tra nguồn |
| Test failure | Assertion thất bại trên một OS | Điều tra product/platform behavior |
| Flaky test | Lúc pass lúc fail trên cùng cấu hình | Ghi nhận, ổn định test, không che giấu lâu dài |

Không dùng continue-on-error cho cả một platform chỉ vì test đang đỏ. Nếu cần tạm thời cho phép pipeline tiếp tục, phải có owner, issue, thời hạn và báo cáo rõ trạng thái. Một tổ hợp được hỗ trợ mà luôn bị bỏ qua sẽ làm mất giá trị của matrix.

## 25. Cache, artifact và kết quả giữa các tổ hợp

Mỗi matrix job nên tạo output có định danh để tránh ghi đè artifact của job khác.

Tên artifact có thể chứa OS, runtime version, architecture, build profile và run ID hoặc commit SHA.

Ví dụ:

```text
test-report-linux-jdk17-x64
test-report-windows-jdk21-x64
test-report-macos-jdk21-arm64
```

Khi tổng hợp kết quả, pipeline nên biết job nào tạo report và tổ hợp nào tương ứng. Không dùng cùng một tên artifact cho tất cả job nếu nền tảng sẽ ghi đè hoặc trộn nội dung.

Với release artifact, chỉ publish đúng output được chọn theo release policy. Không publish nhầm binary thử nghiệm từ matrix preview. Metadata cần ghi toolchain và target tương ứng.

## 26. Lập kế hoạch cập nhật và loại bỏ matrix

OS và runtime có vòng đời. Runner label có thể bị deprecate, image có thể ngừng cung cấp, JDK hoặc SDK có thể hết hỗ trợ.

Nên duy trì một lịch rà soát:

- Kiểm tra lịch deprecation của runner.
- Theo dõi lifecycle của OS và runtime.
- Kiểm tra version build tool và plugin.
- Đánh giá người dùng còn trên phiên bản cũ.
- Cập nhật support policy và tài liệu sản phẩm.
- Thêm version mới vào preview trước khi promote.
- Bỏ version cũ sau giai đoạn thông báo.
- Xóa cache key, secret và runner config không còn dùng.

Mỗi thay đổi matrix nên có lý do và owner. Không để một phiên bản cũ tồn tại trong workflow nhiều năm chỉ vì không ai nhớ tại sao nó được thêm vào.

## 27. Đo hiệu quả của ma trận

Các chỉ số giúp đánh giá matrix có cân bằng tốt hay không:

- Thời gian queue và thời gian thực thi theo từng tổ hợp.
- Tỷ lệ lỗi theo OS/runtime/architecture.
- Số lỗi chỉ xuất hiện trên một nền tảng.
- Tỷ lệ flaky test.
- Tỷ lệ tổ hợp hỗ trợ được kiểm tra trong PR, nightly và release.
- Chi phí runner theo tầng pipeline.
- Thời gian từ khi upstream phát hành phiên bản mới tới khi dự án xác minh.
- Số tổ hợp bị bỏ qua và tuổi của exception.
- Tỷ lệ release có đầy đủ bằng chứng cho các target được hỗ trợ.

Nếu một tổ hợp luôn mất nhiều thời gian nhưng không phát hiện lỗi, hãy xem lại test scope hoặc cách chạy. Không tự động xóa tổ hợp có cam kết hỗ trợ; cần đánh giá lại rủi ro và chính sách sản phẩm trước.

## 28. Checklist thiết kế support matrix

- [ ] Có danh sách OS, distro, runtime và architecture được hỗ trợ.
- [ ] Mỗi version có trạng thái supported, preview, deprecated hoặc unsupported.
- [ ] Có minimum và latest supported version rõ ràng.
- [ ] Runner OS và target OS được phân biệt.
- [ ] Các tổ hợp không hỗ trợ được loại trừ có lý do.
- [ ] PR matrix có đủ OS/runtime đại diện và minimum version.
- [ ] Nightly hoặc release chạy các tổ hợp bổ sung cần thiết.
- [ ] Full matrix được dùng trước release khi chính sách yêu cầu.
- [ ] Pairwise không thay thế các tổ hợp bắt buộc.
- [ ] Platform-specific behavior được kiểm tra trên runner phù hợp.
- [ ] Native dependency được kiểm tra theo architecture và ABI.
- [ ] Compiler target, runtime và build tool version được xác định riêng.
- [ ] Cache key tách theo OS, architecture và toolchain.
- [ ] Artifact/report có tên gắn với từng matrix combination.
- [ ] fail-fast và max-parallel phù hợp với tầng pipeline.
- [ ] Runner image và toolchain được pin hoặc ghi nhận.
- [ ] Có lịch rà soát deprecation và cập nhật version.
- [ ] Ngoại lệ continue-on-error có owner và thời hạn.
- [ ] Release evidence chứng minh các target được hỗ trợ đã được kiểm tra.

## Kết luận

Ma trận hệ điều hành và phiên bản nên phản ánh chính sách hỗ trợ thực tế của sản phẩm. Bắt đầu từ target OS, runtime, architecture và phiên bản được cam kết; sau đó chọn tổ hợp bắt buộc cho pull request, mở rộng ở nightly và xác minh đầy đủ trước release. Runner OS chỉ là môi trường thực thi của job, không tự chứng minh sản phẩm chạy đúng trên target.

Khi phân biệt rõ build, test và packaging; dùng full matrix cho các cổng cần thiết, pairwise cho các tổ hợp có nhiều chiều và cache/artifact được phân vùng đúng, nhóm có thể rút ngắn phản hồi mà vẫn giữ được bằng chứng cho mọi nền tảng được hỗ trợ. Matrix cần được rà soát theo vòng đời OS/runtime và mỗi hàng cần có lý do, owner cùng mục tiêu kiểm thử rõ ràng.

