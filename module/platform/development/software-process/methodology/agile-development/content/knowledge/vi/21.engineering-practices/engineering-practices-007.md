# Tích hợp liên tục cùng nhánh mã tồn tại ngắn

## 1. Vì sao Agile cần tích hợp mã thường xuyên?

Trong phát triển phần mềm, nhiều người có thể cùng làm việc trên một hệ thống: một người sửa giao diện, người khác thay API, người khác nữa đổi dữ liệu hoặc thêm kiểm thử. Nếu từng người làm việc trên nhánh riêng trong nhiều tuần rồi mới ghép lại, sản phẩm có thể gặp **xung đột mã, sai hợp đồng giao tiếp, lỗi dữ liệu, thay đổi không tương thích và kiểm thử tích hợp thất bại** ngay khi thời gian bàn giao đã gần hết.

Một nhóm có thể báo đã hoàn tất hầu hết các tác vụ nhưng vẫn chưa có phần mềm **tích hợp và sử dụng được**. Tình trạng ấy trái với mục tiêu nhận phản hồi sớm, giao sản phẩm tăng dần và thích ứng liên tục trong Agile.

**Continuous Integration (CI — tích hợp liên tục)** là thực hành mà những người phát triển **thường xuyên tích hợp thay đổi vào một nhánh mã chung**, và mỗi lần tích hợp được kiểm tra bằng hệ thống build cùng các phép kiểm thử tự động thích hợp. Kết hợp CI với **nhánh mã tồn tại ngắn (short-lived branches)** giúp giảm lượng thay đổi chưa được kiểm chứng cùng nhau, nhờ đó giảm rủi ro khi ghép các phần của sản phẩm.

Ví dụ, một nhóm xây nền tảng học trực tuyến có Sprint Goal là **học viên tự đăng ký được khóa học miễn phí còn chỗ và nhận xác nhận đúng**. Backend đổi cấu trúc kết quả API, frontend đổi thông báo, còn người kiểm thử bổ sung kịch bản hai học viên tranh chỗ cuối. Nếu nhóm tích hợp các thay đổi nhỏ thường xuyên, những hiểu lầm về API và dữ liệu dễ được phát hiện ngay, thay vì chỉ lộ ra trong ngày demo.

Trong module **AGILE_DEVELOPMENT**, CI là một thực hành kỹ thuật hỗ trợ giá trị Agile: **phần mềm hoạt động được**, phản hồi sớm, hợp tác giữa các chuyên môn và cải tiến liên tục. Nó bổ trợ Scrum, Kanban và các thực hành **Extreme Programming (XP)**, nhưng không thay thế Product Goal, ưu tiên backlog hay việc hiểu đúng nhu cầu người dùng.

> **Nguyên tắc:** Chưa tích hợp và chưa kiểm chứng được với phiên bản chung thì một phần mã dù “xong trên máy cá nhân” vẫn chưa chứng minh sản phẩm có khả năng hoạt động đúng cùng các thay đổi khác.

## 2. Làm rõ CI, mainline, nhánh ngắn và phát hành

### 2.1. CI là thói quen của nhóm, không chỉ là một máy chạy test

Một hệ thống có thể có Jenkins, GitHub Actions, GitLab CI hoặc công cụ pipeline tương tự mà vẫn **chưa thực hành CI tốt** nếu các thành viên giữ nhánh riêng hàng tuần và chỉ merge cuối tháng.

CI gồm cả hai khía cạnh:

1. **Tích hợp thường xuyên:** thay đổi được đưa vào một dòng phát triển chung (mainline/trunk) với nhịp đủ ngắn.
2. **Kiểm chứng tự động và phản hồi nhanh:** build, test và các phép kiểm tra phù hợp được chạy để nhóm sớm biết thay đổi có làm hỏng phần mềm chung không.

Một pipeline xanh nhưng chỉ chạy trên nhánh riêng biệt **không chứng minh hai nhánh đã hoạt động đúng khi kết hợp**. Tương tự, merge thường xuyên nhưng không kiểm thử có thể tạo một mainline liên tục bị lỗi.

### 2.2. Phân biệt các thuật ngữ

| Khái niệm | Ý nghĩa | Điều không nên nhầm |
| --- | --- | --- |
| **Mainline / trunk** | Dòng phát triển chính được nhóm chia sẻ, thường là nhánh **main**. | Không mặc định là phiên bản production đang chạy. |
| **Integration** | Đưa thay đổi vào dòng chung và kiểm tra tính tương thích. | Không đồng nghĩa đã phát hành cho khách hàng. |
| **Short-lived branch** | Nhánh thực hiện một thay đổi nhỏ, tồn tại ngắn trước khi tích hợp hoặc hủy. | Không có một mốc số ngày bắt buộc áp dụng mọi đội. |
| **Trunk-based development (TBD)** | Cách làm nhấn mạnh tích hợp thường xuyên vào trunk, dùng commit trực tiếp có kiểm soát hoặc nhánh rất ngắn. | Không bắt buộc bỏ code review hoặc mọi thành viên đều commit trực tiếp lên main. |
| **CI pipeline** | Chuỗi kiểm tra tự động khi có thay đổi, chẳng hạn build, unit test, integration test. | Không tự bảo đảm mọi kịch bản nghiệp vụ hoặc an toàn đã đúng. |
| **Continuous Delivery** | Duy trì phần mềm ở trạng thái có thể phát hành theo quy trình đã định, thường có bước quyết định phát hành. | Không bắt buộc tự động đưa mọi thay đổi ra production. |
| **Continuous Deployment** | Tự động triển khai những thay đổi đã qua kiểm soát tới production theo chính sách. | Không phù hợp mặc định cho mọi hệ thống có ràng buộc vận hành. |
| **Release** | Đưa một phiên bản/khả năng tới đối tượng sử dụng đã định. | Có thể diễn ra tách biệt thời điểm merge và deploy. |

### 2.3. Một chuỗi phản hồi lý tưởng

~~~mermaid
flowchart LR
    A["Chọn lát cắt nhỏ"] --> B["Sửa mã và test cục bộ"]
    B --> C["Đẩy nhánh ngắn / tạo PR"]
    C --> D["CI: build và kiểm thử"]
    D --> E{"Đạt điều kiện tích hợp?"}
    E -- "Chưa" --> F["Sửa, chạy lại kiểm tra"]
    F --> C
    E -- "Có" --> G["Tích hợp vào mainline"]
    G --> H["Kiểm tra mainline / bản tích hợp"]
    H --> I["Sẵn sàng bàn giao theo chính sách"]
    I --> J["Phản hồi người dùng và cải tiến"]
~~~

Sơ đồ mô tả **một cách vận hành phổ biến**, không bắt buộc mọi nhóm dùng Pull Request hoặc cùng các cổng kiểm tra. Nhóm có thể chạy kiểm tra khác nhau tùy rủi ro, nhưng phải có **cơ chế để phát hiện và khắc phục khi tích hợp phá hỏng phiên bản chung**.

## 3. Vì sao nhánh sống lâu làm tăng rủi ro?

### 3.1. Nhánh sống lâu làm tăng khoảng cách giữa hai phiên bản

Giả sử hai nhóm cùng bắt đầu từ phiên bản V1:

- Nhóm A đổi cách lưu đăng ký để hỗ trợ hủy khóa học.
- Nhóm B đổi API lấy số chỗ để hiển thị trạng thái nhanh hơn.
- Trong ba tuần, cả hai giữ nhánh riêng và chỉ kiểm thử trên mã riêng.

Khi ghép lại, nhóm có thể gặp:

1. **Textual conflicts:** các thay đổi cùng sửa một đoạn mã.
2. **Semantic conflicts:** Git merge không báo xung đột nhưng logic kết hợp sai.
3. **Contract conflicts:** API hoặc dữ liệu đổi theo các giả định không còn đúng.
4. **Migration conflicts:** cả hai nhánh dùng phiên bản schema khác nhau.
5. **Test/infrastructure drift:** pipeline, thư viện và cấu hình giữa các nhánh khác nhau.
6. **Phản hồi đến muộn:** chi phí sửa tăng vì người làm đã chuyển ngữ cảnh hoặc quyết định phụ thuộc đã lan rộng.

**Không phải mọi xung đột đều là xung đột do Git nhận biết.** Hai nhánh có thể merge sạch nhưng khi chạy thật lại tạo đăng ký trùng hoặc trả mã lỗi không khớp.

### 3.2. So sánh nhánh ngắn và nhánh dài

| Khía cạnh | Nhánh ngắn, tích hợp thường xuyên | Nhánh dài, tích hợp muộn |
| --- | --- | --- |
| **Quy mô một lần merge** | Thường nhỏ hơn, dễ review và thử nghiệm. | Dễ tích lũy nhiều thay đổi khó phân biệt. |
| **Độ trễ nhận phản hồi chung** | Phát hiện xung đột và lỗi tích hợp sớm. | Có thể chỉ phát hiện khi tính năng gần xong. |
| **Kiến thức bối cảnh** | Thay đổi còn mới, người làm dễ giải thích. | Người làm đã quên chi tiết hoặc đổi ưu tiên. |
| **Khả năng hoàn tác** | Thường dễ khoanh vùng hơn nếu thay đổi nhỏ. | Khó tách một lỗi khỏi nhiều thay đổi gộp. |
| **Phụ thuộc giữa người/nhóm** | Có cơ hội điều chỉnh hợp đồng sớm. | Quyết định sai có thể lan sang nhiều nhánh. |
| **Rủi ro** | Không biến mất; vẫn cần test và review. | Rủi ro tích hợp và chi phí làm lại thường tăng theo độ lệch. |

Nhánh ngắn **không tự bảo đảm chất lượng**. Nếu nhóm liên tục đưa thay đổi chưa được kiểm tra vào mainline, kết quả có thể tệ hơn. Lợi ích đến từ **tần suất tích hợp cộng với kiểm tra, giới hạn thay đổi và phản ứng nhanh khi lỗi**.

### 3.3. Ngắn là bao lâu?

Trong nhiều cách thực hành trunk-based, nhánh feature được giữ **rất ngắn**, thường mục tiêu là tích hợp trong ngày hoặc sau một vài ngày thay vì nhiều tuần. Đây là **mục tiêu cải tiến thực hành**, không phải ngưỡng chính thức của Scrum hoặc một định luật rằng nhánh sang ngày thứ ba đã sai.

Độ dài hợp lý phụ thuộc công việc, năng lực kiểm thử, chính sách review và rủi ro. Điều nên theo dõi là:

- Nhánh có liên tục lệch xa mainline không?
- Một PR có quá lớn để reviewer hiểu không?
- Test tích hợp có phát hiện sai khác nhanh không?
- Công việc có thể tách thành phần nhỏ, vẫn an toàn để merge không?
- Có nguyên nhân hệ thống nào khiến nhánh chờ review lâu?

**Branch age** là tín hiệu để hỏi về luồng công việc, không phải lý do phạt người giữ nhánh lâu mà không xem blocker.

## 4. Trunk-based development và hai cách làm thông dụng

### 4.1. Tích hợp trực tiếp với bảo vệ phù hợp

Ở một số nhóm nhỏ, thành viên có thể tích hợp những thay đổi rất nhỏ trực tiếp vào mainline nếu:

- Có bộ kiểm tra cục bộ và tự động phù hợp.
- Nhóm có chính sách review/ghép cặp đáp ứng rủi ro.
- Mainline được giám sát liên tục.
- Có khả năng nhanh chóng sửa hoặc hoàn tác khi sai.

Cách này giảm thời gian tồn tại nhánh, nhưng **không đồng nghĩa ai cũng nên có quyền push tự do lên nhánh được bảo vệ**. Nhiều tổ chức cần pull request, reviewer và branch protection theo chính sách.

### 4.2. Nhánh feature rất ngắn với pull request nhỏ

Một lựa chọn phổ biến:

1. Tạo nhánh từ mainline mới nhất.
2. Thực hiện **một thay đổi hẹp**, kèm kiểm thử cần thiết.
3. Đẩy lên và mở Pull Request sớm để nhận phản hồi.
4. Chạy CI, sửa lỗi và review theo quy tắc nhóm.
5. Cập nhật với mainline hoặc dùng merge queue nếu cần.
6. Merge khi điều kiện đã đạt; đóng/xóa nhánh đã tích hợp.

**Ví dụ luồng Git minh họa** (giả sử repo có nhánh **main**, quyền Git và chính sách review đã được thiết lập):

~~~bash
# Đồng bộ với mainline
git fetch origin
git switch main
git pull --ff-only origin main

# Một lát cắt thay đổi nhỏ
git switch -c feat/enrollment-status

# ... sửa mã và thêm/chỉnh kiểm thử ...
git status
git add .
git commit -m "Show confirmed enrollment status"
git push -u origin feat/enrollment-status

# Mở PR bằng giao diện hoặc CLI của nền tảng.
# Chỉ merge sau khi đạt kiểm tra và review bắt buộc.
~~~

**Lưu ý:** các lệnh chỉ minh họa cách làm, không phải lệnh đã chạy trong repo của người học. Cần kiểm tra thay đổi trước khi dùng **git add .** để tránh đưa nhầm file chứa bí mật, dữ liệu cá nhân, tệp sinh ra hoặc cấu hình không thuộc PR. Có thể dùng **git add <đường-dẫn>** cho các file cụ thể.

Trong môi trường doanh nghiệp, quy tắc branch protection có thể yêu cầu nhiều kiểm tra hơn. Không nên dùng **force push lên mainline**, vô hiệu hóa hook bảo mật hoặc bỏ review chỉ để nhánh được tính là ngắn.

### 4.3. Khi có nhiều PR liên tục, mainline vẫn phải được kiểm tra

Một PR xanh khi chạy với phiên bản mainline tại thời điểm T có thể gặp lỗi khi một PR khác được merge trước nó. Nhóm có thể:

- Yêu cầu cập nhật nhánh với mainline trước merge.
- Chạy kiểm thử trên kết quả tích hợp dự kiến.
- Sử dụng **merge queue** để kiểm tra tổ hợp PR theo thứ tự.
- Chạy lại các phép kiểm tra quan trọng trên mainline sau merge.

Không nên kết luận “PR xanh” đồng nghĩa “mainline luôn xanh”. **Điểm kiểm tra của bản tích hợp chung** vẫn cần được công bố và quan sát.

### 4.4. Có nhất thiết phải dùng trunk-based cho mọi dự án?

Không có chiến lược nhánh duy nhất phù hợp mọi bối cảnh. Những sản phẩm phải duy trì **nhiều phiên bản phát hành song song**, sửa lỗi cho bản cũ hoặc tuân thủ quy định đặc thù có thể cần release/maintenance branches.

Ngay cả khi dùng release branch, nhóm vẫn có thể:

- Tích hợp phát triển chính thường xuyên trên trunk.
- Giữ các bản vá nhỏ, truy vết được.
- Dùng test tự động và kiểm chứng hồi quy giữa các phiên bản.
- Hạn chế việc phát triển một tính năng lớn chỉ tồn tại trên nhánh riêng trong thời gian dài.

**Nhánh phát hành được duy trì theo chính sách** không phải lúc nào cũng là phản mẫu của nhánh feature sống lâu. Cần phân biệt mục đích và cơ chế đồng bộ.

## 5. Chia thay đổi nhỏ để có thể merge thường xuyên

### 5.1. Một tính năng lớn không nhất thiết là một PR lớn

Ví dụ backlog có khả năng **học viên hủy đăng ký khóa học**. Nếu làm toàn bộ UI, API, dữ liệu, email, quyền và hoàn tiền trong một nhánh kéo dài vài tuần, rủi ro tích hợp rất lớn.

Nhóm có thể chia thay đổi kỹ thuật thành:

1. Bổ sung hợp đồng API hoặc cấu trúc dữ liệu tương thích với phiên bản hiện tại.
2. Thêm logic xử lý và kiểm thử phía server dưới một cơ chế chưa bật cho người dùng.
3. Thêm giao diện và điều kiện quyền trong những phần thay đổi nhỏ.
4. Kiểm thử luồng tích hợp đầu cuối.
5. Kích hoạt cho nhóm thử nghiệm khi đủ điều kiện bàn giao.

Những bước kỹ thuật nhỏ **có thể được merge trước khi tính năng hoàn chỉnh được phát hành**, miễn chúng an toàn và không phá hành vi sản phẩm hiện tại.

### 5.2. Phân biệt kích thước PR và kích thước lát cắt giá trị

| Cấp độ | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Commit** | Thay đổi hẹp nào có thể hiểu và kiểm tra? | Thêm kiểm thử cho trạng thái đăng ký. |
| **Pull Request** | Một nhóm thay đổi nào có thể review/tích hợp độc lập? | Trả trạng thái đăng ký trong API theo cách tương thích. |
| **Product Backlog Item / user story** | Hành vi người dùng nào cần được đáp ứng? | Học viên biết mình đã đăng ký thành công hay chưa. |
| **Increment** | Phần sản phẩm nào đã tích hợp, có thể sử dụng và đạt DoD? | Học viên xem trạng thái thật trên giao diện trong phạm vi đã định. |
| **Release** | Khi nào khả năng được mở cho người dùng mục tiêu? | Bật luồng trạng thái cho nhóm học viên thử nghiệm. |

**Một PBI không bắt buộc tương đương một PR.** Nhiều PR nhỏ có thể tạo một Increment có ích. Nhưng không nên gọi từng PR đang ẩn, chưa tạo hành vi dùng được là một Increment hoàn tất nếu Definition of Done yêu cầu khả năng sử dụng thực tế.

### 5.3. Chia theo thay đổi có thể kiểm chứng

Một thay đổi phù hợp để merge sớm thường có:

- Mục đích hẹp, bối cảnh được mô tả rõ.
- Hành vi cũ được giữ nguyên hoặc thay đổi được quản lý có chủ đích.
- Kiểm thử tương ứng với rủi ro của thay đổi.
- Không cần đồng thời merge nhiều nhánh khác mới build được.
- Tác động tới API/schema được công bố và tương thích khi cần.
- Một phương án sửa hoặc hoàn tác nếu phát hiện vấn đề.

Nếu mỗi PR luôn cần một PR khác được merge cùng lúc để sản phẩm không lỗi, đó có thể là dấu hiệu cần **chia khác, dùng branch by abstraction hoặc thay đổi hợp đồng theo nhiều bước tương thích**.

## 6. Một CI pipeline đáng tin cậy gồm những gì?

### 6.1. Mục tiêu là phản hồi đúng và kịp thời

Pipeline phải đủ nhanh để người phát triển còn nhớ thay đổi của mình và đủ đáng tin để khi báo lỗi, nhóm thực sự hành động. Một pipeline chậm hàng giờ, thỉnh thoảng xanh/đỏ ngẫu nhiên hoặc bỏ qua các test quan trọng sẽ làm các nhánh tồn tại lâu hơn.

Một số lớp kiểm tra:

| Lớp | Mục tiêu | Thời điểm thường phù hợp |
| --- | --- | --- |
| **Cấu trúc và vệ sinh mã** | Kiểm tra format, lint, tệp cấu hình, lỗi biên dịch. | Rất sớm trên PR hoặc trước push. |
| **Unit tests** | Bảo vệ các quy tắc nhỏ và thuật toán có phản hồi nhanh. | Mỗi lần thay đổi liên quan. |
| **Integration / contract tests** | Kiểm tra API, dữ liệu, thành phần phối hợp đúng. | PR và/hoặc mainline theo rủi ro và thời gian chạy. |
| **Security / dependency checks** | Phát hiện vấn đề ở thành phần/phụ thuộc và chính sách. | Theo chính sách, cả khi thay đổi và theo nhịp định kỳ. |
| **End-to-end tests cốt lõi** | Kiểm tra hành trình người dùng quan trọng. | Trên bản tích hợp, trước mốc bàn giao cần kiểm chứng. |
| **Hiệu năng, khả năng phục hồi, kiểm tra chuyên biệt** | Kiểm tra rủi ro không chức năng đặc biệt. | Tại mốc phù hợp; không mặc định chạy đầy đủ mọi commit. |

Mục tiêu không phải đưa mọi bài kiểm thử nặng nhất vào bước đầu rồi để người làm chờ. Có thể **phân tầng kiểm tra**: một nhóm rất nhanh để feedback sớm; các kiểm tra sâu hơn chạy song song hoặc ở mốc tích hợp/phát hành. Nhưng test bắt buộc trước một quyết định cụ thể **không được bỏ qua chỉ vì chạy lâu**.

### 6.2. Pipeline cơ bản trên PR và mainline

~~~mermaid
flowchart TD
    A["Thay đổi được push"] --> B["Đọc cấu hình, kiểm tra mã"]
    B --> C["Build + unit tests"]
    C --> D["Integration / contract tests cần thiết"]
    D --> E{"Đạt kiểm tra bắt buộc?"}
    E -- "Không" --> F["PR không được merge / cần sửa"]
    E -- "Có" --> G["Review và kiểm tra quyền"]
    G --> H["Merge vào mainline"]
    H --> I["Kiểm tra phiên bản tích hợp chung"]
    I --> J{"Mainline ổn định?"}
    J -- "Không" --> K["Ưu tiên khôi phục mainline"]
    J -- "Có" --> L["Có thể tiếp tục tích hợp/bàn giao"]
~~~

Tùy công cụ, các bước có thể chạy song song hoặc theo thứ tự khác; quy định review/approval có thể độc lập pipeline. Điều quan trọng là **ai có thể merge, kiểm tra nào bắt buộc và hành động khi check thất bại đều rõ**.

### 6.3. Ví dụ cấu hình GitHub Actions cho dự án Java dùng Gradle

Đoạn sau **chỉ để minh họa cấu trúc kiểm tra CI**. Nó giả định dự án có Gradle Wrapper, dùng Java 21 và quy ước các phép kiểm tra đang nằm trong tác vụ **check**. Cần điều chỉnh cho thực tế trước khi dùng:

~~~yaml
name: ci

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - uses: gradle/actions/setup-gradle@v4
      - name: Compile and run configured checks
        run: ./gradlew --no-daemon check
~~~

**Giải thích:**

- **pull_request** kiểm tra thay đổi trước merge, **push vào main** kiểm tra trạng thái thực tế của mainline.
- **permissions: contents: read** thể hiện nguyên tắc cấp quyền tối thiểu cho job chỉ cần đọc mã.
- **gradlew check** phải được cấu hình để thực thi đúng tập kiểm tra dự án; không mặc nhiên bao gồm toàn bộ test tích hợp, bảo mật hoặc end-to-end.
- Các phiên bản action, JDK, nền tảng runner và cơ chế pin action cần được quản lý theo chính sách tổ chức. Trong hệ thống yêu cầu bảo đảm chuỗi cung ứng, có thể cần **ghim action bằng commit SHA đầy đủ**, rà soát nguồn và cập nhật có kiểm soát.
- Không đưa secrets vào log, không cấp đặc quyền production cho PR tùy ý và không chạy mã không tin cậy với thông tin xác thực nhạy cảm.

CI pipeline trên repo Java thực có thể dùng Maven, Gradle, GitLab CI, Jenkins hoặc giải pháp khác. Không cần đổi công cụ chỉ vì ví dụ dùng GitHub Actions.

### 6.4. Phản hồi nhanh không chỉ đến từ cache

Một số cách tăng tốc có thể thử:

- Chạy unit tests và kiểm tra tĩnh sớm.
- Chia test theo loại và cân bằng khả năng chạy song song.
- Cache phụ thuộc **an toàn**, không cache kết quả khiến bỏ lỡ thay đổi quan trọng.
- Dùng môi trường kiểm thử tái hiện được.
- Giảm test trùng lặp nhưng giữ những rủi ro cốt lõi.
- Quan sát thời gian chờ runner, thời gian setup, thời gian test để xử lý đúng điểm nghẽn.

**Nhanh nhưng không đáng tin** không phải mục tiêu. Nếu cache tạo kết quả sai hoặc test phụ thuộc thứ tự chạy, pipeline xanh có thể không còn ý nghĩa.

## 7. Kiểm thử tự động giúp CI phát hiện lỗi gì?

### 7.1. Ba mức kiểm thử thường bổ sung nhau

| Mức | Ví dụ với đăng ký khóa học | Điều thường chưa chứng minh |
| --- | --- | --- |
| **Unit test** | Một hàm từ chối đăng ký khi sức chứa không hợp lệ. | Không chứng minh hai request đồng thời không vượt sức chứa trên DB thật. |
| **Integration / contract test** | API lưu dữ liệu chính xác, kết quả tương thích với frontend; thử tranh chỗ cuối. | Chưa chắc người học hiểu giao diện trong trình duyệt thật. |
| **End-to-end test** | Học viên đăng nhập, chọn khóa, đăng ký và thấy xác nhận. | Không tự bao phủ mọi rủi ro, tải đồng thời hoặc lỗi bảo mật. |

Tư duy **test pyramid** có thể giúp chọn nhiều bài kiểm tra nhanh ở tầng thấp và số lượng hợp lý các kiểm tra xuyên hệ thống. Nhưng không dùng kim tự tháp thành công thức số lượng cứng cho mọi dự án.

### 7.2. Một kịch bản chấp nhận cho việc tích hợp thật

Ví dụ Gherkin:

~~~gherkin
Feature: Đăng ký khóa học miễn phí

  Scenario: Học viên đăng ký khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa X
    And khóa X còn ít nhất một chỗ
    When A gửi yêu cầu đăng ký khóa X
    Then chỉ một đăng ký hiệu lực được lưu cho A
    And A thấy thông báo xác nhận thành công

  Scenario: Gửi lặp không tạo đăng ký trùng
    Given A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại cùng yêu cầu đăng ký khóa X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhận trạng thái đăng ký hiện tại

  Scenario: Hai học viên chọn chỗ cuối
    Given khóa X chỉ còn một chỗ
    When hai học viên đủ điều kiện đồng thời xác nhận đăng ký
    Then tối đa một đăng ký mới được xác nhận
    And tổng đăng ký hiệu lực không vượt sức chứa
~~~

Các ví dụ mô tả hành vi, **không tự thành kiểm thử tự động** nếu chưa có mã test, môi trường, dữ liệu và điều kiện tái hiện phù hợp. Ngay cả khi pipeline xanh, nhóm vẫn phải xem liệu các trường hợp rủi ro thực tế đã có trong bộ kiểm tra hay chưa.

### 7.3. Test thất bại ngẫu nhiên không được bỏ qua

**Flaky test** là test có thể cho kết quả khác nhau dù phần mềm và đầu vào về bản chất không thay đổi. Nguyên nhân thường gặp gồm:

- Dữ liệu test dùng chung bị thay đổi bởi các job khác.
- Phụ thuộc thời gian, thứ tự chạy, múi giờ hoặc môi trường.
- Chờ bất đồng bộ bằng **sleep** cố định, không có đồng bộ đúng.
- Tài nguyên hoặc môi trường mạng không ổn định.
- Test cạnh tranh chỉ đôi khi kích hoạt được trạng thái lỗi.

Nếu test thất bại thường xuyên, nhóm dễ hình thành thói quen bấm **rerun cho xanh** mà không điều tra, làm mất độ tin cậy của CI.

Một chính sách hợp lý:

1. Ghi nhận tỷ lệ và điều kiện thất bại có thể tái hiện.
2. Phân loại lỗi sản phẩm, lỗi test hoặc lỗi môi trường dựa trên bằng chứng.
3. Sửa nguyên nhân, bổ sung quan sát và dữ liệu test độc lập.
4. Chỉ tạm cách ly test trong trường hợp có quyết định minh bạch, đánh giá rủi ro và kế hoạch khôi phục; **không bỏ kiểm chứng bắt buộc đối với chức năng hoặc điều kiện an toàn**.

### 7.4. Test chạy trên PR và test sau merge đều quan trọng

Một kiểm tra chạy trên nhánh riêng có thể không phát hiện tác động khi kết hợp các PR. Vì vậy, những hệ thống có nhiều người merge đồng thời nên xem xét kiểm tra trên **merge result** hoặc dùng merge queue và kiểm tra tiếp trên mainline.

Nếu test quan trọng chạy theo lịch ban đêm thay vì mỗi PR, nhóm cần biết **thời điểm nào kết quả mới có** và **có được coi bản tích hợp là sẵn sàng bàn giao trước kết quả ấy không**. Điều này là quyết định về rủi ro và Definition of Done, không chỉ tối ưu pipeline.

## 8. Feature flags: tích hợp sớm mà chưa mở tính năng

### 8.1. Tại sao cần tách merge khỏi release?

Đôi khi một tính năng cần nhiều thay đổi nhỏ, nhưng nhóm không muốn để code nằm trên nhánh riêng trong thời gian dài. **Feature flag (feature toggle)** cho phép đưa mã vào mainline dưới điều kiện bật/tắt, sau đó chỉ mở hành vi mới khi đủ điều kiện.

Ví dụ, luồng **hủy đăng ký** đang được phát triển:

- API mới được thêm theo cách tương thích nhưng chưa cho người dùng thông thường gọi.
- Giao diện hủy đăng ký được ẩn khi flag tắt.
- Kiểm thử kiểm tra đường cũ và đường mới trong phạm vi cần thiết.
- Sau khi toàn bộ luồng đạt chuẩn, nhóm bật thử cho một nhóm học viên hợp lệ.

**Feature flag là công cụ quản lý tiếp xúc với tính năng**, không phải bằng chứng rằng tính năng đã hoàn tất.

### 8.2. Pseudocode minh họa

~~~java
// Minh họa, không phải triển khai production hoàn chỉnh.
public EnrollmentResult cancelEnrollment(
        User user, Enrollment enrollment) {
    if (!featureFlags.enabledFor("cancel-enrollment", user)) {
        return EnrollmentResult.unavailable();
    }

    // Vẫn phải xác thực, kiểm tra quyền và quy tắc nghiệp vụ
    // trong đường thực thi phía server.
    authorization.requireCanCancel(user, enrollment);
    enrollmentPolicy.requireCancellationAllowed(enrollment);
    return enrollmentService.cancelSafely(enrollment);
}
~~~

**Lưu ý bảo mật:** một flag tắt trên giao diện **không phải ranh giới phân quyền**. Người dùng vẫn có thể gọi API trực tiếp; hệ thống phải thực thi xác thực, phân quyền và quy tắc nghiệp vụ ở nơi thích hợp, kể cả khi bật/tắt tính năng.

### 8.3. Các loại flag và rủi ro vòng đời

| Loại cờ | Mục đích ví dụ | Cần chú ý |
| --- | --- | --- |
| **Release flag** | Ẩn khả năng chưa mở rộng. | Nên loại bỏ sau khi quyết định hoàn tất rollout. |
| **Experiment flag** | Thử biến thể giao diện với nhóm người dùng. | Cần thiết kế đo lường và quyền riêng tư đúng. |
| **Operational flag** | Tắt một đường xử lý khi có sự cố. | Phải kiểm chứng đường tắt, trạng thái dữ liệu và quyền vận hành. |
| **Permission/entitlement rule** | Xác định người dùng nào được phép dùng khả năng. | Đây là quy tắc quyền riêng, không nên dựa vào cờ frontend thông thường. |

Flags tồn tại mãi gây **nợ kỹ thuật**: nhiều nhánh điều kiện, tổ hợp hành vi khó test, khó biết đường nào còn được dùng. Nhóm cần có người sở hữu, lý do, ngày xem lại, kế hoạch dọn cờ và kiểm thử các trạng thái có rủi ro.

### 8.4. Có thể merge code chưa hoàn thiện mà vẫn giữ mainline khỏe?

Có thể merge phần triển khai chưa **được mở sử dụng** nếu:

- Đường hành vi hiện tại không bị phá.
- Mã vẫn build và chạy các kiểm tra bắt buộc.
- Tính năng mới được cô lập an toàn.
- Những thay đổi schema/hợp đồng tương thích với phiên bản đang vận hành.
- Có kế hoạch hoàn thiện, kiểm thử và dọn cờ rõ.

Nhưng **không được gọi tính năng chưa hoàn tất ấy là Increment Done** nếu các yêu cầu sử dụng và DoD của nó chưa đạt. Điều được merge chỉ là một bước tích hợp kỹ thuật an toàn.

## 9. Branch by abstraction: thay đổi lớn mà vẫn tích hợp nhỏ

### 9.1. Vấn đề khi thay một thành phần cốt lõi

Giả sử nhóm cần thay thư viện tính học phí hoặc chuyển cách lưu đăng ký. Nếu thay toàn bộ trong một nhánh nhiều tuần, việc tích hợp sẽ khó. **Branch by abstraction** tạo một lớp giao tiếp ổn định để **cả triển khai cũ và mới** có thể tồn tại tạm thời trong mainline.

Luồng thường gồm:

1. Xác định hợp đồng cần giữ ổn định.
2. Đưa vào một abstraction/interface phù hợp, dùng triển khai cũ phía sau.
3. Xây triển khai mới theo từng phần nhỏ, có test tương đương.
4. Chuyển từng nhóm sử dụng theo điều kiện kiểm chứng và kế hoạch rollback.
5. Gỡ triển khai cũ và abstraction chuyển tiếp khi không còn cần.

~~~mermaid
flowchart TD
    A["Caller: Enrollment Service"] --> B["Giao diện lưu đăng ký ổn định"]
    B --> C["Triển khai cũ"]
    B --> D["Triển khai mới"]
    E["Chính sách lựa chọn có kiểm soát"] --> B
    C --> F["Test hợp đồng và dữ liệu"]
    D --> F
    F --> G["Di chuyển dần, theo dõi rồi dọn mã cũ"]
~~~

Phương pháp này có chi phí: abstraction thêm độ phức tạp và cần kiểm chứng tính tương đương. **Không nên thêm abstraction cho mọi thay đổi nhỏ**. Dùng khi chi phí giữ một nhánh lớn hoặc thay đổi đột ngột cao hơn chi phí chuyển tiếp.

### 9.2. Tránh hai nguồn sự thật

Khi triển khai cũ và mới cùng tồn tại, cần quyết định:

- Nguồn dữ liệu nào là **source of truth**?
- Nếu đọc từ hai hệ thống, sai lệch được phát hiện thế nào?
- Nếu có dual write, xử lý lỗi một bên thành công, một bên thất bại ra sao?
- Chuyển đổi có thể hoàn tác không; dữ liệu đã chuyển có tương thích ngược không?
- Khi nào có đủ bằng chứng để loại bỏ đường cũ?

Không nên xem “đã có flag” là đủ để an toàn. Dữ liệu và tác động ngoài hệ thống có thể **không thể rollback chỉ bằng đổi cờ**.

## 10. CI với thay đổi cơ sở dữ liệu và hợp đồng API

### 10.1. Tại sao schema gây khó khi merge thường xuyên?

Nếu một PR đổi mã sang cột dữ liệu mới và ngay lập tức xóa cột cũ, phiên bản đang chạy hoặc một dịch vụ phụ thuộc có thể bị lỗi. CI và nhánh ngắn khuyến khích thay đổi từng phần, nhưng với hệ thống phân tán cần có **chiến lược tương thích chuyển tiếp**.

Một cách tiếp cận thường dùng là **expand–migrate–contract**:

1. **Expand:** thêm cấu trúc/hợp đồng mới theo cách không phá phiên bản cũ.
2. **Migrate:** cập nhật mã đọc/ghi hoặc chuyển dữ liệu với kiểm tra nhất quán.
3. **Contract:** sau khi mọi thành phần phụ thuộc đã chuyển và có bằng chứng, mới loại bỏ cấu trúc cũ.

### 10.2. Ví dụ thay một cột trạng thái

Giả sử bảng đăng ký đang có cột **status_text** và nhóm muốn dùng cấu trúc trạng thái mới **status_code**. Một thay đổi theo nhiều bước:

~~~sql
-- Minh họa bước mở rộng cho một hệ quản trị dữ liệu phù hợp.
-- Cú pháp và chiến lược migration phải được kiểm tra với DB thật.
ALTER TABLE enrollment
ADD COLUMN status_code VARCHAR(32);
~~~

Các bước tiếp theo có thể là:

- Bảo đảm ứng dụng cũ vẫn chạy khi có cột mới.
- Cập nhật mã theo cách đọc được trạng thái hợp lệ trong thời gian chuyển tiếp.
- Chuyển dữ liệu cũ theo lô hoặc cơ chế phù hợp, có khả năng kiểm tra/khôi phục.
- Tạo kiểm tra tương thích giữa các phiên bản đang tồn tại.
- Theo dõi dữ liệu thiếu hoặc không nhất quán.
- Chỉ ngừng dùng rồi xóa **status_text** khi đã có bằng chứng không còn thành phần cần nó.

Đây không phải một kế hoạch migration hoàn chỉnh. Tùy hệ quản trị dữ liệu, việc thêm/chuyển cột có thể ảnh hưởng locking, hiệu năng, chỉ mục, rollback và nghĩa vụ vận hành. Với dữ liệu thật, cần kiểm thử theo rủi ro và phê duyệt đúng thẩm quyền.

### 10.3. Thay đổi API theo hướng tương thích

Thay vì bất ngờ đổi:

~~~json
{"success": true}
~~~

thành:

~~~json
{"state": "CONFIRMED", "enrollmentId": "E123"}
~~~

và xóa trường cũ ngay, nhóm có thể cân nhắc giữ hành vi/hợp đồng cũ tạm thời hoặc sử dụng versioning, **theo những gì client hiện tại thực sự hỗ trợ**. Không nên giả định mọi client đều bỏ qua trường mới hoặc đều xử lý được enum mới.

**Contract tests** giữa dịch vụ và client giúp phát hiện xung đột sớm. Khi có nhiều nhóm cùng dùng API, thông báo thay đổi, lộ trình deprecation và kiểm thử tương thích là phần quan trọng của việc giữ nhánh ngắn mà không phá hệ thống.

## 11. Tình huống xuyên suốt: CI cho chức năng đăng ký khóa học

### 11.1. Bối cảnh và mục tiêu

Một Scrum Team phát triển nền tảng học trực tuyến. **Sprint Goal** minh họa:

> Học viên thử nghiệm có thể tự đăng ký một khóa học miễn phí còn chỗ và nhận xác nhận chính xác, không tạo đăng ký trùng.

Product Backlog có các hạng mục:

- Học viên xem khóa còn chỗ.
- Học viên gửi đăng ký và thấy trạng thái thành công/thất bại.
- Hệ thống xử lý đăng ký lặp và tranh chấp chỗ cuối.
- Nhân viên hỗ trợ tra cứu được kết quả phù hợp quyền.

Nhóm gồm frontend, backend, người kiểm thử và người hỗ trợ tích hợp. Nếu mỗi chuyên môn giữ một nhánh riêng trong cả Sprint, những thay đổi lớn sẽ khó ghép vào cuối. Nhóm quyết định **giữ nhánh ngắn và tích hợp theo các bước nhỏ có test**.

### 11.2. Lập chuỗi PR nhỏ

| PR minh họa | Nội dung hẹp | Cách giữ an toàn khi merge |
| --- | --- | --- |
| **PR-01** | Thêm kiểu dữ liệu trạng thái đăng ký và test chuyển đổi tương thích. | Không phá API hiện hành; kiểm tra unit/contract. |
| **PR-02** | API trả trạng thái đăng ký cho chính học viên đã đăng nhập. | Kiểm tra quyền, response contract và dữ liệu. |
| **PR-03** | Xử lý tạo đăng ký với ràng buộc không trùng. | Test tích hợp, trạng thái lỗi và hành vi retry. |
| **PR-04** | Kiểm soát đồng thời để không vượt sức chứa. | Test cạnh tranh trên DB phù hợp, xác minh rollback. |
| **PR-05** | Giao diện gọi API và hiển thị xác nhận. | Test component/end-to-end theo rủi ro; giữ đường cũ hoạt động khi chưa mở. |
| **PR-06** | Bật luồng cho nhóm dùng thử sau khi đạt điều kiện. | Kiểm tra bản tích hợp, quyền, quan sát và chính sách phát hành. |

Thứ tự trên chỉ là một cách chia để minh họa. Trong thực tế, nhóm có thể chọn một **lát cắt dọc nhỏ hơn** với frontend–API–DB ngay từ đầu, sau đó tăng độ bao phủ. Nếu PR-03 chưa an toàn khi thiếu PR-04, nhóm phải **đổi cách chia hoặc cô lập hành vi** trước khi merge, không dựa vào bảng kế hoạch để giả vờ những PR độc lập.

### 11.3. Vai trò của kiểm thử ở mỗi bước

| Tình huống | Kiểm tra sớm | Kiểm tra trên bản tích hợp |
| --- | --- | --- |
| Trạng thái đăng ký | Unit/contract tests. | API trả trạng thái đúng với client hiện hành. |
| Đăng ký lặp | Kiểm tra quy tắc idempotency ở module. | Gửi request lặp đến API dùng DB thật phù hợp. |
| Tranh chỗ cuối | Kiểm tra điều kiện giao dịch. | Hai request đồng thời, xác nhận không vượt sức chứa. |
| Phân quyền | Unit/policy tests. | Gọi API với học viên khác quyền và xác minh từ chối. |
| Giao diện xác nhận | Component tests. | Hành trình học viên trên bản tích hợp. |

Không có một loại test duy nhất bao phủ hết. Đặc biệt, kiểm thử **hai request đồng thời** cần môi trường và cách phối hợp thực thi có khả năng tái hiện rủi ro; một unit test happy path không đủ chứng minh dữ liệu nhất quán.

### 11.4. Một sự cố CI trong Sprint

Giả sử PR-04 merge vào mainline sau khi PR checks đạt, nhưng một thay đổi khác vừa merge khiến integration test trên mainline thất bại. Nhóm nên:

1. **Công khai mainline đang đỏ** và xác định phép kiểm tra nào thất bại.
2. Ưu tiên người có bối cảnh và khả năng phối hợp điều tra; tránh mở thêm nhiều PR phụ thuộc mainline lỗi.
3. Tái hiện lỗi ở phiên bản tích hợp, phân biệt lỗi sản phẩm, dữ liệu test và hạ tầng.
4. **Sửa nhanh hoặc revert thay đổi gây lỗi** bằng quy trình an toàn được phép, không xóa lịch sử tùy tiện.
5. Chạy lại kiểm tra bắt buộc, xác nhận mainline ổn định.
6. Bổ sung test hoặc cơ chế merge để giảm tái diễn.

Nếu lỗi là **đăng ký vượt sức chứa**, việc bỏ test để pipeline xanh là sai. Nếu lỗi do môi trường kiểm thử không ổn định, cần sửa điều kiện chạy và có chính sách minh bạch về trạng thái kiểm chứng.

### 11.5. Kết thúc Sprint và Definition of Done

Trong Scrum, **Definition of Done (DoD)** mô tả trạng thái chất lượng của Increment. Developers chịu trách nhiệm tuân thủ DoD khi tạo phần sản phẩm tăng trưởng.

CI có thể cung cấp nhiều bằng chứng quan trọng, nhưng cần phân biệt:

- **PR merged:** thay đổi đã vào dòng chung.
- **CI xanh:** những phép kiểm tra được cấu hình đã đạt trên phiên bản đã kiểm tra.
- **PBI Done / Increment đáp ứng DoD:** các yêu cầu chất lượng và hành vi cần thiết đã được xác minh.
- **Release:** phần mềm được đưa đến đối tượng sử dụng theo chính sách.
- **Outcome:** học viên thực sự tự đăng ký được, ít cần hỗ trợ hơn.

Nếu luồng đăng ký còn thất bại ở kiểm thử cạnh tranh, **không được gọi khả năng đăng ký là Increment Done** dù PR đã merge và một số job xanh. CI là phương tiện giúp đạt DoD, không phải phép thay thế tất cả tiêu chuẩn nghiệp vụ, an toàn và vận hành.

## 12. Khi mainline bị lỗi: ưu tiên khôi phục luồng

### 12.1. “Keep the build green” là thỏa thuận hành động

Một mainline thường xuyên đỏ khiến thành viên không phân biệt lỗi do thay đổi của mình hay lỗi có sẵn. Điều đó tạo nhiều nhánh sửa chữa, test lại và thời gian chờ.

Nhóm nên có **working agreement**:

- Nếu check bắt buộc trên mainline thất bại, thông báo rõ và xử lý theo mức nghiêm trọng.
- Người có bối cảnh thay đổi và người hỗ trợ tập trung khôi phục nhanh.
- Có quyền và cách thức **revert** hoặc sửa phù hợp, tuân thủ chính sách.
- Không gắn nhãn thành công khi phép kiểm tra bắt buộc chưa đạt.
- Khi khôi phục, xem nguyên nhân và cải tiến pipeline, test hoặc cơ chế merge.

Không nhất thiết mọi sự cố nhỏ phải dừng toàn tổ chức. Mức phản ứng phụ thuộc **phạm vi ảnh hưởng, tính bắt buộc của test và mức rủi ro**.

### 12.2. Các trường hợp cần phân biệt

| Sự cố | Cách xử lý phù hợp |
| --- | --- |
| **Build không biên dịch** | Ưu tiên sửa hoặc revert thay đổi gây lỗi; không coi mainline sẵn sàng tích hợp tiếp. |
| **Unit test bắt buộc thất bại** | Tái hiện và xử lý; nếu lỗi test, sửa test đúng nguyên nhân. |
| **Integration test báo dữ liệu sai** | Giữ nguyên kiểm soát chất lượng; điều tra nghiệp vụ và dữ liệu. |
| **Runner/công cụ CI ngừng hoạt động** | Minh bạch mất khả năng kiểm chứng, phối hợp vận hành và tuân thủ chính sách merge khẩn cấp nếu có. |
| **Flaky test đã được xác minh** | Điều tra tính không xác định, có phương án tạm được chấp thuận và không bỏ qua an toàn cốt lõi. |
| **Lỗ hổng hoặc bí mật bị lộ** | Kích hoạt quy trình ứng cứu bảo mật; thu hồi bí mật, hạn chế tác động và bảo toàn bằng chứng khi cần. |

**Lưu ý:** một kết quả CI không thể xác minh vì hạ tầng bị lỗi **khác** với kết quả CI đã chạy và đạt. Không được báo xanh bằng cách diễn giải “không thấy lỗi” khi không có kiểm tra.

### 12.3. Revert không phải lúc nào cũng hoàn tác được dữ liệu

Mã có thể revert tương đối dễ nếu thay đổi hẹp. Nhưng tác động **schema, dữ liệu đã ghi, message đã gửi, thanh toán hoặc trạng thái bên ngoài** có thể không thể phục hồi chỉ bằng revert commit.

Với thay đổi có hậu quả cao, thiết kế phát hành và CI phải tính cả:

- Tương thích phiên bản cũ/mới.
- Migration và rollback dữ liệu.
- Idempotency của tác vụ lặp.
- Cơ chế tạm dừng hoặc giảm phạm vi ảnh hưởng.
- Giám sát và xác nhận phục hồi.

Một nhánh ngắn là điều kiện tốt để giảm rủi ro, nhưng **không thay thế chiến lược khôi phục**.

## 13. Review nhỏ, cộng tác nhanh và quyền quyết định

### 13.1. PR nhỏ giúp review có chất lượng hơn

Một PR chứa hàng nghìn dòng thay đổi không liên quan sẽ khó kiểm tra hơn một PR hẹp có mô tả mục đích rõ và test đi kèm. Nhánh ngắn khuyến khích:

- Chọn một trách nhiệm thay đổi chính.
- Tách refactor không thay đổi hành vi khỏi thay đổi hành vi nếu có thể.
- Đưa ví dụ tái hiện lỗi hoặc tiêu chí chấp nhận.
- Nêu tác động API/schema và cách tương thích.
- Liên kết kết quả test và bối cảnh rủi ro.
- Chỉ dùng **draft PR** sớm khi cần phối hợp nhưng chưa đủ điều kiện merge.

Tuy nhiên, **PR nhỏ không đồng nghĩa phải chia thay đổi đến mức mất khả năng hiểu ngữ cảnh**. Nhóm cần cân bằng độ nhỏ với tính độc lập kiểm chứng được.

### 13.2. Review là cơ hội chia sẻ kiến thức

Người review nên hỏi:

- Thay đổi này phục vụ hành vi hoặc rủi ro nào?
- Có phá hợp đồng hay dữ liệu cũ không?
- Những trường hợp biên nào đáng thử?
- Test có đáng tin cậy và đúng mức không?
- Phần nào cần theo dõi khi triển khai?

Tránh biến review thành cổng duyệt tùy tiện không có tiêu chí. Người review phải có thời gian, bối cảnh và quyền phù hợp; nhánh chờ nhiều ngày vì một người duy nhất được phép duyệt là dấu hiệu cần xem lại **chính sách review**, không chỉ yêu cầu người viết mã “nhanh hơn”.

### 13.3. Pair programming và kiểm thử sớm

Các thực hành XP như **pair programming, TDD, refactoring và collective code ownership** giúp thay đổi nhỏ có chất lượng. Đặc biệt:

- Pairing giảm thời gian chờ phản hồi ở phần khó.
- TDD có thể làm rõ hành vi trước khi code, nếu phù hợp ngữ cảnh.
- Refactoring có test bảo vệ giúp duy trì khả năng chia PR nhỏ.
- Chia sẻ hiểu biết giảm phụ thuộc vào một chuyên gia duy nhất.

Scrum không bắt buộc dùng những kỹ thuật này, nhưng Developers vẫn chịu trách nhiệm tạo Increment đáp ứng DoD.

## 14. CI liên hệ với Scrum, Kanban và XP như thế nào?

| Góc nhìn | Vai trò của CI và nhánh ngắn |
| --- | --- |
| **Scrum** | Giúp Developers có cơ hội tạo một hoặc nhiều Increment trong Sprint; phát hiện lỗi tích hợp trước Sprint Review, bảo vệ Sprint Goal và DoD. |
| **Kanban** | Giảm thời gian chờ ở bước integration/review, hạn chế WIP nhánh chưa merge và cải thiện cycle time. |
| **XP** | CI là thực hành kỹ thuật quan trọng cùng TDD, refactoring, pairing và các thay đổi nhỏ. |
| **Lean** | Giảm hàng đợi mã chưa tích hợp, làm lại, chuyển giao và thời gian phản hồi dài. |
| **Crystal** | Cung cấp môi trường kỹ thuật giúp nhóm giao thường xuyên; mức kiểm soát có thể tăng theo quy mô và hậu quả lỗi. |

### 14.1. Scrum Team có thể tích hợp nhiều lần trong một Sprint

Sprint không phải một “nhánh Git kéo dài hai tuần”. Trong Scrum, một Sprint có thể có nhiều Increment và các Increment có thể được phát hành trước Sprint Review. Developers cần có khả năng tích hợp và kiểm tra thường xuyên **ngay trong Sprint**, không chờ ngày cuối mới merge.

Một Sprint Goal vẫn có thể được đạt bằng nhiều PR nhỏ. **Số lượng PR merged không phải thước đo Sprint Goal**, vì mục tiêu nói về giá trị và khả năng sản phẩm, không chỉ trạng thái Git.

### 14.2. Kanban làm rõ điểm nghẽn tích hợp

Một workflow tham khảo:

~~~mermaid
flowchart LR
    A["Ready"] --> B["Developing"]
    B --> C["Review / CI"]
    C --> D["Integrated"]
    D --> E["Verify / Release theo chính sách"]
    E --> F["Done"]
    C -. "Fix / rework" .-> B
    D -. "Mainline đỏ" .-> C
~~~

Nhóm cần định nghĩa **Started/Finished** và điều kiện chuyển trạng thái, tránh dùng **Integrated** và **Done** như từ đồng nghĩa nếu còn yêu cầu kiểm tra hoặc release chưa đạt. Những hạng mục bị chặn ở review/CI vẫn là **WIP** nếu đã Started nhưng chưa tới Finished.

### 14.3. Phản hồi sớm vẫn phải có phản hồi người dùng

CI chỉ cho biết những kiểm tra **được viết và được chạy** có đạt hay không. Một luồng đăng ký có thể xanh toàn bộ test nhưng người học vẫn không hiểu thông báo “đã ghi danh”.

Vì vậy, sau khi tích hợp và đạt tiêu chuẩn bàn giao, nhóm cần thu phản hồi **từ người dùng hoặc bên liên quan phù hợp** để xem kết quả có tạo giá trị không. CI giảm độ trễ kỹ thuật, không thay thế kiểm chứng nhu cầu sản phẩm.

## 15. Đo hiệu quả của CI và nhánh ngắn

### 15.1. Những số đo có ích

| Số đo | Định nghĩa tham khảo | Câu hỏi |
| --- | --- | --- |
| **Branch age / branch lifetime** | Thời gian từ khi tạo hoặc bắt đầu làm trên nhánh tới merge/đóng theo quy ước. | Nhánh có bị giữ quá lâu do kích thước hay chờ review? |
| **PR size** | Phạm vi thay đổi, chẳng hạn số file/độ lớn diff trong bối cảnh. | PR có đủ hẹp để review và kiểm chứng không? |
| **PR review waiting time** | Thời gian từ khi sẵn sàng review tới phản hồi/merge theo quy ước. | Có điểm nghẽn ở bước review? |
| **CI feedback time** | Thời gian từ push/PR event đến kết quả kiểm tra cần thiết. | Phản hồi có đủ sớm để hỗ trợ thay đổi nhỏ? |
| **Mainline health** | Tình trạng và thời lượng check bắt buộc trên mainline thất bại. | Dòng chung có đáng tin để tích hợp tiếp? |
| **Change failure / lỗi sau tích hợp** | Số/tỷ lệ thay đổi gây vấn đề theo định nghĩa đã thống nhất. | Có đang tăng tốc bằng cách giảm chất lượng không? |
| **Work item age / cycle time** | Thời gian item chưa xong hoặc hoàn tất trong workflow. | Có chờ review/CI/verify nhiều không? |
| **Deployment lead time** | Thời gian từ mốc thay đổi đã chọn đến lúc triển khai theo quy ước. | Tốc độ đưa thay đổi ra môi trường đích ra sao? |
| **Deployment frequency** | Nhịp triển khai của phần mềm theo môi trường/phạm vi xác định. | Khả năng đưa phần mềm ra dùng có được cải thiện không? |
| **Outcome người dùng** | Học viên tự đăng ký thành công, số sự cố hoặc cần hỗ trợ. | Khả năng kỹ thuật có tạo giá trị thực không? |

Không nên dùng **số lần commit, PR hoặc dòng mã** để xếp hạng cá nhân. Một người sửa lỗi dữ liệu phức tạp có thể có ít commit hơn người sửa văn bản nhưng tạo giá trị bảo vệ lớn hơn.

### 15.2. Ví dụ đọc tuổi nhánh

Giả sử tám nhánh feature gần đây có tuổi khi merge (ngày lịch):

~~~text
0,5 ; 1 ; 1 ; 1,5 ; 2 ; 2 ; 3 ; 7
~~~

**Trung vị** là trung bình của hai giá trị giữa:

\[
\frac{1,5 + 2}{2}=1,75\ \text{ngày}.
\]

Một nhánh sống **7 ngày** nổi bật hơn phần lớn nhánh còn lại; nên xem vì sao: PR quá lớn, phụ thuộc bên ngoài, người review vắng, pipeline chậm hoặc một thử nghiệm cần thêm thời gian? **Không tự kết luận người tạo nhánh làm việc kém**.

Nếu nhóm muốn dự báo, cần xem **phân bố theo loại việc**, dữ liệu đủ nhiều và cách tính mốc nhất quán. Trung vị tốt không loại bỏ rủi ro một số nhánh cực lớn.

### 15.3. Đọc kết quả cân bằng

Giả sử một nhóm giảm thời gian review trung vị từ 2 ngày xuống 0,5 ngày nhưng số lỗi sau triển khai tăng. Đây **chưa phải cải tiến thành công toàn diện**. Có thể review đang bị làm qua loa, bộ test chưa bao phủ rủi ro hoặc loại việc đã đổi.

Ngược lại, số lần CI báo đỏ tăng có thể xuất phát từ **bổ sung kiểm thử phát hiện lỗi trước khi ra production**, không nhất thiết hệ thống kém đi. Cần xem thời điểm phát hiện, mức độ nghiêm trọng, thời gian khôi phục và lỗi thực tế.

**Thước đo phục vụ cải tiến luồng và chất lượng**, không phải mục tiêu để tối ưu bề mặt báo cáo.

## 16. Những phản mẫu phổ biến

| Phản mẫu | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Có pipeline nhưng merge cuối Sprint** | Phát hiện lỗi tích hợp muộn, khó tạo Increment. | Chia PR nhỏ và tích hợp thường xuyên. |
| **PR hàng nghìn dòng không liên quan** | Review khó và chậm, khó tìm nguồn lỗi. | Tách thay đổi theo mục đích và rủi ro kiểm chứng. |
| **Giữ nhánh riêng nhiều tuần để “an toàn”** | Lệch mainline và phải ghép thay đổi lớn. | Dùng flag/abstraction, thay đổi tương thích khi phù hợp. |
| **Chạy test trên nhánh nhưng không kiểm tra mainline** | Hai PR cùng xanh có thể phá nhau sau merge. | Kiểm tra bản tích hợp, merge queue hoặc mainline CI. |
| **Bấm rerun flaky test tới khi xanh** | Mất độ tin cậy của CI, che lỗi thật. | Điều tra và khắc phục flakiness có trách nhiệm. |
| **Tắt test quan trọng để kịp merge** | Chất lượng giảm, rủi ro lan tới người dùng. | Bảo vệ tiêu chuẩn bắt buộc, cập nhật dự báo nếu cần. |
| **CI xanh được gọi là feature Done** | Chưa có bằng chứng toàn bộ hành vi/DoD. | Phân biệt PR, integration, Increment, release và outcome. |
| **Dùng feature flag thay quyền truy cập** | Người dùng có thể gọi API bị ẩn trực tiếp. | Kiểm tra authn/authz phía server; flag chỉ quản lý rollout. |
| **Không dọn flag cũ** | Nhiều đường điều kiện, khó test và bảo trì. | Có owner, ngày xem lại và kế hoạch gỡ cờ. |
| **Thay schema phá tương thích ngay** | Bản cũ, dịch vụ phụ thuộc hoặc rollout bị lỗi. | Expand–migrate–contract và contract tests. |
| **PR xanh nhưng bị chờ duyệt nhiều ngày** | Tuổi nhánh và thay đổi lệch main tăng. | Cải thiện chính sách review, người dự phòng và flow. |
| **Mainline đỏ nhưng mọi người vẫn kéo việc mới** | Nhiều thay đổi khó xác minh, nợ lỗi tăng. | Ưu tiên khôi phục dòng chung theo chính sách. |
| **Đếm commit/PR làm thước đo cá nhân** | Chia việc giả tạo, dễ bỏ chất lượng. | Đo flow, độ tin cậy, giá trị và kết quả dùng được. |
| **Tích hợp thường xuyên nhưng không nhận feedback người dùng** | Có thể hoàn thiện nhanh thứ không cần thiết. | Bàn giao lát cắt có giá trị và kiểm chứng giả thuyết. |
| **Tuyên bố rollback chỉ cần revert Git** | Không xử lý dữ liệu và tác động bên ngoài. | Thiết kế chiến lược khôi phục cho schema và side effects. |

## 17. Lộ trình áp dụng cho nhóm mới bắt đầu CI

### Bước 1 — Đo hiện trạng

Thống nhất số ngày nhánh tồn tại, thời gian chờ review, thời gian pipeline, tình trạng mainline và số lần lỗi tích hợp. Ghi rõ mốc đo để so sánh sau này. Không cần tạo dashboard lớn ngay; dữ liệu đủ tin cậy quan trọng hơn số biểu đồ.

### Bước 2 — Xác định mainline và nguyên tắc bảo vệ

Nhóm biết dòng chung là gì, ai có quyền merge, check nào bắt buộc, cách sửa hoặc revert khi lỗi. Với hệ thống có dữ liệu nhạy cảm, giữ nguyên các quyền và kiểm soát tổ chức.

### Bước 3 — Bảo đảm pipeline cơ bản đáng tin

Trước tiên xây build lặp lại được và bộ unit/integration tests thiết yếu. Chú ý flakiness và cách tạo dữ liệu test. Một pipeline hoàn hảo trong tương lai không bù được mainline hiện tại không thể build.

### Bước 4 — Chọn một lát cắt backlog nhỏ

Lấy một hạng mục có giá trị đủ hẹp. Thống nhất acceptance criteria, những rủi ro cần test và phương án chia thành nhiều thay đổi an toàn để merge.

### Bước 5 — Thử nhánh ngắn và review sớm

Giữ PR nhỏ, mở review sớm, sử dụng pairing khi có thay đổi liên thành phần, tích hợp ngay khi đạt điều kiện. Với tính năng cần thời gian dài hơn, cân nhắc flag, abstraction hoặc migration tương thích thay vì cất toàn bộ mã trong nhánh tuần lễ.

### Bước 6 — Kiểm tra mainline sau tích hợp

Quan sát check trên mainline, xử lý lỗi nhanh, xác nhận hoạt động với sản phẩm chung. Duy trì bằng chứng test và những điều chưa kiểm chứng.

### Bước 7 — Bàn giao Increment và thu phản hồi

Tập hợp những thay đổi nhỏ thành khả năng sản phẩm đáp ứng DoD, bàn giao theo chính sách. Nhận phản hồi từ người dùng/PO để điều chỉnh backlog.

### Bước 8 — Cải tiến nhịp và chất lượng

Sau một vài vòng, xem tuổi nhánh, chờ review, độ tin cậy pipeline, lỗi sau phát hành và cycle time. Chọn một điểm nghẽn rõ để cải thiện, thử nhỏ, đo rồi giữ hoặc điều chỉnh.

## 18. Bài tập thực hành

### Bài tập 1 — Nhận diện tích hợp liên tục hay chỉ tự động hóa test

Ba nhóm có cách làm:

1. Nhóm A chạy unit tests mỗi commit trên từng nhánh, nhưng chỉ merge cuối tháng.
2. Nhóm B thường merge thay đổi nhỏ trong ngày, có build và test tự động cho bản tích hợp.
3. Nhóm C merge mỗi ngày nhưng không chạy kiểm tra nào, mainline thường xuyên không biên dịch.

**Câu hỏi:** nhóm nào đang gần thực hành CI hiệu quả hơn? Hai nhóm còn lại thiếu điều gì?

**Gợi ý:** **B** thể hiện rõ cả tích hợp thường xuyên và kiểm chứng tự động. A có tự động hóa test nhưng phản hồi tích hợp muộn; C có nhịp merge nhưng thiếu bảo vệ chất lượng của mainline.

### Bài tập 2 — Chia một nhánh lớn thành các thay đổi an toàn

Một nhánh triển khai “Học viên tự hủy đăng ký” đang tồn tại 12 ngày và chứa:

- Thêm trường dữ liệu mới.
- Đổi API đăng ký.
- Thêm nút hủy trên web.
- Tích hợp gửi email xác nhận.
- Thay cơ chế cập nhật sức chứa.

Hãy đề xuất cách tách thành **ít nhất bốn PR** có thể tích hợp theo thứ tự hợp lý. Với mỗi PR, nêu điều kiện để không phá phiên bản hiện hành. Khi nào cần feature flag hoặc branch by abstraction?

**Gợi ý:** mở rộng schema tương thích, đưa hợp đồng API an toàn, triển khai xử lý hủy có test dưới flag, thêm UI, kiểm chứng luồng tích hợp rồi bật. Không merge một PR làm hệ thống không build hoặc phá quyền chỉ vì các PR khác “sẽ đến sau”.

### Bài tập 3 — Một PR xanh nhưng mainline đỏ

Hai PR chạy test trên cùng mainline cũ. PR A đổi API thành công, PR B đổi frontend để dùng kết quả cũ. Cả hai đều xanh khi chạy độc lập. Sau khi lần lượt merge, phiên bản chung có lỗi.

**Câu hỏi:**

1. Vì sao Git có thể merge không xung đột nhưng sản phẩm vẫn sai?
2. Những kiểm tra nào nên chạy ở mốc merge/mainline?
3. Merge queue giúp giảm rủi ro nào?
4. Nhóm xử lý mainline đỏ ra sao để không tích lũy thêm lỗi?

**Gợi ý:** đây là **semantic/contract conflict**. Cần test hợp đồng và integration trên kết quả tích hợp dự kiến; merge queue kiểm tra tổ hợp PR theo thứ tự; ưu tiên khôi phục mainline và bổ sung kiểm tra ngăn tái diễn.

### Bài tập 4 — CI xanh có đồng nghĩa Done?

Một chức năng đăng ký đã merge vào main. Pipeline xanh với 90 unit tests, nhưng:

- Không có test hai học viên tranh chỗ cuối.
- Chưa kiểm tra quyền xem đăng ký của người khác.
- Giao diện đang hiển thị dữ liệu mô phỏng.
- DoD yêu cầu luồng đầu cuối trên bản tích hợp.

**Câu hỏi:** có thể gọi Increment đăng ký là Done không? Nêu các bằng chứng còn thiếu.

**Gợi ý:** không. Cần kiểm chứng đồng thời, phân quyền và tích hợp giao diện–API–dữ liệu thật theo DoD. Số lượng unit tests không thay thế kiểm chứng các rủi ro còn thiếu.

### Bài tập 5 — Feature flag và quyền truy cập

Nhóm ẩn nút “Hủy đăng ký” nếu flag tắt, nhưng backend vẫn cho mọi người gọi endpoint hủy đăng ký của người khác.

**Yêu cầu:** xác định hai lỗi tư duy và đề xuất thiết kế an toàn hơn.

**Gợi ý:** flag frontend không bảo vệ API; backend thiếu phân quyền. Cần kiểm tra authn/authz phía server, ràng buộc nghiệp vụ và trạng thái flag theo thiết kế phù hợp; test cả trường hợp trái quyền, không chỉ kiểm tra nút có bị ẩn.

### Bài tập 6 — Thiết kế pipeline theo rủi ro

Một đội Java có các phép kiểm tra:

| Kiểm tra | Thời gian minh họa | Đặc điểm |
| --- | ---: | --- |
| Compile + unit tests | 2 phút | Hầu hết thay đổi liên quan. |
| Contract tests | 4 phút | Bắt lỗi API tương thích. |
| Test đăng ký đồng thời trên DB tích hợp | 6 phút | Quan trọng với luồng đăng ký. |
| End-to-end toàn hệ thống | 25 phút | Rộng, một số kịch bản có thể trùng. |
| Security scan sâu | 18 phút | Quan trọng theo chính sách thay đổi/triển khai. |

**Câu hỏi:** làm sao tạo feedback sớm mà vẫn bảo vệ rủi ro quan trọng? Điều kiện nào có thể chạy song song, điều kiện nào bắt buộc trước merge hoặc release?

**Gợi ý:** chạy compile/unit sớm, contract test và test dữ liệu quan trọng song song nếu môi trường cho phép; phân tầng E2E và scan theo chính sách; bắt buộc các kiểm chứng cần thiết trước quyết định liên quan. Không đưa toàn bộ test chậm sang “sau release” nếu DoD/rủi ro yêu cầu kiểm chứng sớm.

### Bài tập 7 — Đo nhánh dài mà không đổ lỗi

Nhánh gần đây có tuổi (ngày) như phần 15: **0,5; 1; 1; 1,5; 2; 2; 3; 7**.

**Yêu cầu:**

1. Tính trung vị tuổi nhánh.
2. Nêu ít nhất ba giả thuyết vì sao một nhánh kéo dài 7 ngày.
3. Đề xuất một cải tiến nhỏ có cách đo rõ.
4. Nêu một rủi ro nếu ép mọi nhánh phải merge trước hai ngày.

**Gợi ý:** trung vị **1,75 ngày**. Nhánh dài có thể do review chậm, phụ thuộc schema/API, PR lớn hoặc CI flakiness. Có thể thử review dự phòng hay chia PR nhỏ, quan sát thời gian chờ và lỗi. Ép merge theo ngày có thể khiến thành viên bỏ test, phá tính ổn định mainline.

### Bài tập 8 — Khi nào revert không đủ?

Một phiên bản mới ghi dữ liệu theo cấu trúc mới và đã gửi email xác nhận cho học viên. Sau khi phát hành, nhóm phát hiện lỗi và muốn revert commit.

Hãy liệt kê:

- Những tác động bên ngoài mà revert mã không thu hồi được.
- Bằng chứng cần thu trước khi khôi phục.
- Cơ chế tương thích hoặc bù trừ có thể cần.
- Cách thay đổi quy trình CI/release để giảm nguy cơ tương tự.

**Gợi ý:** dữ liệu đã ghi, email đã gửi, side effects và client đang dùng API mới có thể tồn tại sau revert. Cần chiến lược schema, rollback/correction và communication theo thẩm quyền, kiểm thử migration cùng quan sát sau phát hành.

## 19. Checklist áp dụng CI và nhánh mã ngắn

### Quy ước nhánh và cộng tác

- [ ] Nhóm biết **mainline/trunk** nào là nguồn tích hợp chung.
- [ ] Các nhánh feature được giữ hẹp, ưu tiên tích hợp thường xuyên.
- [ ] Có chính sách merge, review, quyền truy cập và branch protection rõ.
- [ ] PR đủ nhỏ để hiểu và kiểm tra; không tách nhỏ tới mức mất khả năng hoạt động.
- [ ] Những thay đổi lớn được chia bằng cách an toàn: flag, abstraction hoặc tương thích hợp đồng khi phù hợp.
- [ ] Có cách kiểm tra thay đổi trong bối cảnh mainline mới nhất hoặc phiên bản tích hợp dự kiến.
- [ ] Không giữ nhánh dài vì điểm nghẽn review/CI mà không tìm cách cải thiện.

### Pipeline và chất lượng

- [ ] Build tự động lặp lại được trên môi trường phù hợp.
- [ ] Các kiểm tra nhanh tạo phản hồi sớm, các kiểm tra sâu được đặt đúng mốc rủi ro.
- [ ] Test quan trọng có dữ liệu độc lập và ít phụ thuộc ngẫu nhiên.
- [ ] Có kiểm tra trên mainline sau merge, không chỉ trên PR riêng.
- [ ] Test thất bại không bị bỏ qua bằng cách rerun hoặc vô hiệu hóa tùy tiện.
- [ ] Secrets, quyền pipeline và phụ thuộc bên ngoài được quản lý an toàn.
- [ ] Người liên quan biết ai xử lý mainline đỏ, khi nào nên sửa hoặc revert.
- [ ] CI xanh không được đánh tráo với Increment đã đáp ứng toàn bộ DoD.

### Bàn giao và cải tiến

- [ ] Hành vi API, dữ liệu và giao diện tương thích qua các bước triển khai.
- [ ] Có kế hoạch xử lý schema migration, rollback và side effects khi cần.
- [ ] Feature flags có owner, tiêu chí bật và kế hoạch dọn cờ.
- [ ] Bản tích hợp được kiểm chứng trước khi tuyên bố khả năng dùng được.
- [ ] Nhóm nhận được phản hồi người dùng sau những Increment có giá trị.
- [ ] Theo dõi tuổi nhánh, chờ review, thời gian CI, sức khỏe mainline và lỗi sau phát hành.
- [ ] Số đo được dùng để cải tiến hệ thống thay vì xếp hạng cá nhân.
- [ ] Khi tăng tần suất tích hợp, chất lượng và an toàn vẫn được giữ hoặc cải thiện.

Checklist này là công cụ trao đổi, không thay thế **Definition of Done** của Scrum Team, quy tắc chất lượng của tổ chức hoặc những nghĩa vụ an toàn/chuyên ngành. Nhóm có thể bắt đầu bằng vài điểm nghẽn quan trọng nhất rồi cải tiến liên tục.

## 20. Ghi nhớ

**Continuous Integration** là thực hành **đưa thay đổi nhỏ vào dòng mã chung thường xuyên và tự động kiểm chứng bản tích hợp**. **Nhánh mã tồn tại ngắn** giảm khoảng cách giữa các phiên bản đang phát triển, giúp xung đột, lỗi hợp đồng và sai lệch dữ liệu được phát hiện sớm hơn.

Một pipeline xanh **không tự chứng minh** chức năng đã đáp ứng mọi hành vi, an toàn hoặc giá trị người dùng. Nhóm cần phân biệt **commit, PR, merge, Increment, release và outcome**; đồng thời giữ những tiêu chuẩn hoàn tất và kiểm soát bắt buộc.

Các kỹ thuật **feature flags, branch by abstraction, expand–migrate–contract, contract testing, review nhỏ và merge queue** hỗ trợ tích hợp sớm khi sản phẩm có nhiều phụ thuộc. Nhưng mọi kỹ thuật đều cần ranh giới, kiểm thử và kế hoạch làm sạch hoặc khôi phục thích hợp.

CI kết hợp tốt với Scrum, Kanban, XP và tư duy Lean vì cùng giảm **thời gian phản hồi và công việc dở dang**. Mục tiêu không phải tạo thật nhiều commit hay PR, mà là **giữ sản phẩm chung đáng tin cậy để nhóm có thể giao phần tăng trưởng nhỏ, học nhanh và thay đổi an toàn**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Continuous Integration (CI)** | Tích hợp thay đổi thường xuyên vào dòng phát triển chung, được kiểm chứng tự động. |
| **Mainline / trunk** | Nhánh/dòng phát triển chính được nhóm chia sẻ. |
| **Short-lived branch** | Nhánh phát triển tồn tại ngắn để đưa một thay đổi hẹp vào dòng chung. |
| **Trunk-based development** | Cách phát triển thường xuyên tích hợp vào trunk, dùng commit có kiểm soát hoặc nhánh rất ngắn. |
| **Feature branch** | Nhánh tạm phục vụ một thay đổi hoặc khả năng sản phẩm. |
| **Pull Request (PR)** | Đề nghị xem xét và tích hợp thay đổi theo workflow của hệ thống quản lý mã. |
| **Build pipeline** | Chuỗi công việc tự động tạo/kiểm tra bản phần mềm. |
| **Unit test** | Kiểm thử một đơn vị logic nhỏ trong phạm vi tương đối cô lập. |
| **Integration test** | Kiểm thử sự phối hợp giữa các thành phần hoặc dịch vụ. |
| **Contract test** | Kiểm tra hợp đồng giao tiếp giữa producer và consumer của API/dịch vụ. |
| **Flaky test** | Kiểm thử cho kết quả không ổn định trong điều kiện về bản chất tương đương. |
| **Merge queue** | Cơ chế xếp và kiểm tra thay đổi trên phiên bản tích hợp dự kiến trước khi merge. |
| **Feature flag** | Cơ chế bật/tắt hoặc giới hạn khả năng theo chính sách rollout/experiment. |
| **Branch by abstraction** | Dùng lớp trừu tượng chuyển tiếp để thay đổi triển khai qua các bước tích hợp nhỏ. |
| **Expand–migrate–contract** | Cách thay đổi schema/hợp đồng qua các bước tương thích rồi loại bỏ cấu trúc cũ. |
| **Idempotency** | Tính chất giúp việc lặp một yêu cầu không tạo thêm tác động không mong muốn. |
| **Definition of Done (DoD)** | Cam kết về trạng thái chất lượng của Increment trong Scrum. |
| **Continuous Delivery** | Duy trì phần mềm sẵn sàng phát hành theo quy trình đã quy định. |
| **Continuous Deployment** | Tự động đưa thay đổi đã qua kiểm tra tới production theo chính sách. |
| **Branch age** | Thời gian nhánh tồn tại hoặc đang mở theo mốc đo được công bố. |
| **Cycle time** | Thời gian từ Started tới Finished của item theo workflow. |
| **Work in Progress (WIP)** | Những hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Increment** | Phần sản phẩm tăng thêm đã tích hợp, có thể sử dụng và đáp ứng chuẩn hoàn tất. |
