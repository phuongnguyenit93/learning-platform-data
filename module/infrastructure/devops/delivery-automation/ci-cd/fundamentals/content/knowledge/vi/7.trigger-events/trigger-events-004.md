# Phân biệt sự kiện từ nguồn tin cậy với đóng góp bên ngoài

Pipeline CI/CD thường được kích hoạt bởi nhiều loại sự kiện: push lên nhánh chính, pull request, tag phát hành, lịch chạy hoặc yêu cầu chạy thủ công. Các sự kiện này không có cùng mức độ tin cậy. Một push lên nhánh đã được bảo vệ sau khi review có thể được xử lý theo chính sách phát hành; một pull request từ fork có thể chứa mã, script và cấu hình do người ngoài kiểm soát.

Nếu pipeline đối xử với mọi sự kiện như nhau, một đóng góp chưa được kiểm tra có thể khiến job thực thi mã tùy ý trong runner, đọc dữ liệu nhạy cảm hoặc sử dụng token có quyền ghi vào repository và môi trường triển khai. Vì vậy, thiết kế trigger cần bắt đầu bằng việc xác định **ai có thể tạo sự kiện, dữ liệu nào trong sự kiện có thể bị kiểm soát và job được phép làm gì**.

## 1. Sự kiện kích hoạt và mức độ tin cậy

Sự kiện kích hoạt (trigger event) là tín hiệu khiến nền tảng CI/CD tạo một lần chạy pipeline. Sự kiện thường chứa thông tin như repository, nhánh hoặc tag, commit SHA, pull request, người khởi tạo và loại thao tác.

Một số trigger thường gặp:

| Trigger | Mục đích thường dùng | Điểm cần xem xét về độ tin cậy |
|---|---|---|
| Push | Kiểm tra thay đổi vừa được đẩy lên repository | Ai có quyền push vào ref đó? Nhánh có được bảo vệ không? |
| Pull request / Merge request | Kiểm tra đóng góp trước khi merge | Mã nguồn và workflow có thể do contributor kiểm soát |
| Tag hoặc release | Tạo artifact và phát hành phiên bản | Ai được tạo, sửa hoặc xóa tag? Tag có được bảo vệ không? |
| Schedule | Chạy kiểm tra định kỳ | Workflow và cấu hình được lấy từ ref nào? |
| Manual dispatch | Cho phép người vận hành chủ động chạy | Ai có quyền khởi chạy và truyền tham số nào? |
| Workflow completion | Kích hoạt luồng sau khi workflow khác hoàn tất | Workflow trước có đáng tin và artifact truyền sang đã được xác minh chưa? |
| External webhook | Nhận sự kiện từ dịch vụ khác | Chữ ký, danh tính nguồn gửi và chống phát lại được xác minh ra sao? |

Không thể kết luận một sự kiện an toàn chỉ từ tên trigger. Ví dụ, push là sự kiện nội bộ của repository nhưng có thể đến từ một nhánh thử nghiệm do contributor tạo. Ngược lại, một pull request từ bên ngoài có thể chứa thay đổi hợp lệ và hữu ích, nhưng mã trong đó vẫn phải được xem là chưa tin cậy cho đến khi qua kiểm tra và review.

Cần phân biệt ba khái niệm:

- **Nguồn sự kiện:** hệ thống hoặc người đã tạo tín hiệu kích hoạt.
- **Nguồn mã:** commit, nhánh, tag và các file mà job sẽ checkout hoặc thực thi.
- **Quyền của lần chạy:** token, secret, quyền ghi, quyền truy cập mạng và tài nguyên mà job nhận được.

Ba khái niệm này có liên quan nhưng không đồng nhất. Một workflow được kích hoạt bởi sự kiện hợp lệ vẫn có thể checkout mã không đáng tin. Một contributor có tài khoản trong tổ chức cũng không đồng nghĩa mọi thay đổi của họ đã được review. Mức độ tin cậy phải được xác định theo ref, trạng thái review, chính sách bảo vệ và hành động mà pipeline định thực hiện.

## 2. Xác định ranh giới tin cậy

Trong một repository, có thể chia nguồn đầu vào thành các nhóm để thiết kế chính sách. Đây là mô hình tham khảo; tổ chức cần điều chỉnh theo quyền thực tế và quy trình review.

| Nhóm nguồn | Ví dụ | Cách xử lý mặc định |
|---|---|---|
| Nhánh phát hành được bảo vệ | main, release branch có required review | Có thể chạy các job nội bộ theo quyền đã cấp |
| Tag phát hành được bảo vệ | v2.4.0 do quy trình phát hành tạo | Có thể chạy build/publish sau khi xác minh tag và quyền tạo |
| Nhánh contributor trong cùng repository | feature branch, branch của người mới | Xem mã là chưa được phê duyệt; không cấp secret production |
| Pull request từ fork | Repository fork gửi thay đổi về upstream | Xem mã, script và metadata là dữ liệu không tin cậy |
| Workflow hoặc template bên ngoài | Reusable workflow, action, template từ repository khác | Pin phiên bản và đánh giá quyền mà thành phần đó cần |
| Webhook bên ngoài | Registry, ticket system hoặc dịch vụ triển khai | Xác minh chữ ký, nguồn gửi, phạm vi và tính mới của sự kiện |

Ranh giới tin cậy không nhất thiết trùng với ranh giới tổ chức. Một nhánh do nhân viên tạo vẫn có thể chứa mã chưa review, dependency độc hại hoặc lệnh build được sửa để lấy dữ liệu. Ngược lại, đóng góp bên ngoài có thể trở thành mã tin cậy sau khi được kiểm tra, review và merge vào nhánh được bảo vệ. Chính sách nên dựa vào trạng thái và bằng chứng thay vì chỉ dựa vào danh tính hoặc tên nhánh.

Một nguyên tắc hữu ích là **độ tin cậy của lần chạy không được cao hơn độ tin cậy của đầu vào mà job thực thi**. Nếu job chạy script từ pull request chưa được review, job đó cần được giới hạn quyền tương ứng, dù workflow được lưu trong repository chính.

## 3. Pull request từ cùng repository và từ fork

Pull request là một cơ chế cộng tác, nhưng hai trường hợp phổ biến có khác biệt về quyền kiểm soát mã nguồn.

**Pull request từ nhánh cùng repository** thường có source branch trong cùng repository. Contributor có thể có quyền push vào nhánh đó, nhưng điều này không có nghĩa thay đổi đã được phê duyệt. Pipeline vẫn phải kiểm tra commit, không giả định mọi script hoặc workflow mới đều an toàn.

**Pull request từ fork** đến từ repository do một chủ sở hữu khác kiểm soát. Người gửi có thể sửa source code, build script, dependency manifest, test và thậm chí file workflow nằm trong pull request. Nếu pipeline thực thi các file này với token hoặc secret có quyền cao, mã độc có thể tận dụng quyền đó.

Ví dụ về rủi ro: một pull request thay đổi script test để đọc biến môi trường rồi gửi nội dung ra một máy chủ bên ngoài. Nếu job có credential registry hoặc cloud, việc chạy test có thể làm lộ credential. Việc pull request chỉ nhằm sửa một dòng tài liệu không loại bỏ rủi ro nếu pipeline vẫn thực thi toàn bộ script của thay đổi.

Vì vậy, với đóng góp bên ngoài:

- Chạy kiểm tra cần thiết trong runner cô lập.
- Cấp token ở quyền tối thiểu, thường chỉ đọc source.
- Không truyền secret phát hành, cloud credential hoặc signing key.
- Hạn chế quyền ghi artifact và quyền thay đổi repository.
- Kiểm soát quyền truy cập mạng nếu runner xử lý mã có nguy cơ cao.
- Lưu log và báo cáo để reviewer đánh giá trước khi merge.
- Chỉ chạy tác vụ có quyền cao sau khi thay đổi đã qua review và nằm trên ref được bảo vệ.

## 4. Phân biệt các trigger trong GitHub Actions

GitHub Actions minh họa rõ cách trigger ảnh hưởng đến ngữ cảnh chạy và quyền.

### 4.1. pull_request

Trigger pull_request thường phù hợp để kiểm tra đóng góp trước khi merge. Với pull request từ fork, GitHub áp dụng các giới hạn bảo mật cho token và secret theo cấu hình repository. Tuy nhiên, nhóm vẫn phải thiết kế workflow sao cho mã trong pull request không nhận quyền nhạy cảm.

Ví dụ workflow CI chỉ đọc mã nguồn và chạy Maven verify:

~~~yaml
name: Validate pull request

on:
  pull_request:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Check out pull request
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run tests
        run: ./mvnw --batch-mode verify
~~~

Ví dụ này không khai báo secret hoặc quyền ghi. Job thực thi mã build và test trong pull request, vì vậy runner vẫn cần được xem là môi trường chạy mã chưa tin cậy. Với dự án có rủi ro cao, có thể dùng runner dùng một lần, cô lập mạng và không tái sử dụng workspace giữa các lần chạy.

### 4.2. push

Trigger push có thể chạy trên nhiều nhánh. Nếu pipeline cần quyền phát hành, hãy giới hạn nhánh và kiểm tra ref rõ ràng. Không nên suy luận rằng mọi push đều đến từ nhánh chính hoặc người có quyền phát hành.

Ví dụ chỉ chạy job xác minh trên nhánh main:

~~~yaml
name: Validate main

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./mvnw --batch-mode verify
~~~

Đây chỉ là điều kiện chọn ref. Để main thực sự đáng tin, repository cần có branch protection, required checks và quy tắc review phù hợp. Nếu quyền push trực tiếp không được kiểm soát, giới hạn trigger theo tên main không đủ tạo ra ranh giới bảo mật.

### 4.3. pull_request_target

pull_request_target chạy workflow trong ngữ cảnh của repository đích và có thể nhận quyền cùng secret của repository đích theo cấu hình. Điều này hữu ích cho một số tác vụ quản lý pull request, nhưng đặc biệt nhạy cảm khi xử lý đóng góp từ fork.

Rủi ro xuất hiện khi workflow có quyền cao checkout hoặc thực thi mã từ pull request. Khi đó, mã do contributor kiểm soát có thể chạy trong ngữ cảnh đặc quyền. Đây là một dạng lỗi thường được gọi là **pwn request**.

Không nên dùng pull_request_target để chạy test, build, script hoặc package từ source branch chưa tin cậy. Nếu cần dùng trigger này cho tác vụ quản lý metadata, hãy:

- Chỉ xử lý metadata cần thiết từ sự kiện.
- Không checkout hoặc thực thi mã của pull request.
- Không đưa title, branch name hoặc nội dung do người dùng kiểm soát trực tiếp vào shell command.
- Kiểm tra và escape dữ liệu trước khi đưa vào API hoặc nội dung hiển thị.
- Cấp đúng permission cần thiết cho tác vụ, ví dụ chỉ quyền quản lý pull request nếu thật sự cần.
- Tách workflow kiểm tra mã nguồn (pull_request) khỏi workflow quản lý trạng thái có quyền cao.

### 4.4. workflow_run

workflow_run có thể kích hoạt workflow sau khi một workflow khác hoàn tất. Đây là cơ chế hữu ích để tách CI không đặc quyền khỏi tác vụ cần quyền cao, nhưng kết quả workflow trước không tự động trở thành dữ liệu tin cậy.

Workflow thứ hai phải xác minh:

- Workflow nguồn đúng tên hoặc định danh được cho phép.
- Repository và ref nguồn đúng phạm vi.
- Lần chạy nguồn liên quan đến commit hoặc pull request mong muốn.
- Artifact tải về có nguồn gốc, tên và nội dung phù hợp.
- Dữ liệu artifact không được thực thi như script nếu chưa được xác minh.
- Token và secret của workflow thứ hai chỉ được cấp khi các điều kiện đã đạt.

Không nên tải artifact do pull request chưa tin cậy tạo ra rồi chạy script trong artifact bằng quyền cao. Artifact cần được xem là dữ liệu đầu vào có thể bị thao túng.

## 5. Thiết kế hai luồng: kiểm tra đóng góp và phát hành tin cậy

Một kiến trúc thường dùng là tách luồng CI dành cho đóng góp thành luồng phát hành có quyền cao. Hai luồng có mục tiêu và quyền khác nhau.

**Luồng kiểm tra đóng góp** chạy trên pull request hoặc nhánh chưa được bảo vệ. Nó có thể checkout source, lint, test, static analysis và tạo báo cáo. Luồng này chỉ cần quyền đọc, không nhận secret phát hành và không deploy production.

**Luồng phát hành** chỉ chạy sau khi thay đổi được merge vào nhánh được bảo vệ hoặc khi một tag phát hành hợp lệ được tạo. Luồng này có thể build artifact chính thức, publish vào registry và triển khai theo các cổng phê duyệt. Trước khi cấp quyền, cần xác minh ref, commit và điều kiện phát hành.

~~~mermaid
flowchart TD
    A[Pull request hoặc fork] --> B[CI không đặc quyền]
    B --> C[Lint, test, scan]
    C --> D{Kiểm tra đạt?}
    D -- Không --> E[Trả báo cáo cho contributor]
    D -- Có --> F[Review và merge]
    F --> G[Nhánh được bảo vệ]
    G --> H[Release pipeline]
    H --> I[Build và xác minh artifact]
    I --> J[Approval / quality gate]
    J --> K[Deploy môi trường đích]
    K --> L[Post-deploy verification]
~~~

Việc tách luồng giúp giảm khả năng mã chưa review tiếp cận secret và quyền phát hành. Tuy nhiên, luồng phát hành vẫn cần xác minh artifact, provenance và quyền sử dụng. Không nên chỉ dựa vào việc workflow trước có trạng thái xanh.

## 6. Bảo vệ token, secret và runner theo mức độ tin cậy

Mỗi job nên được cấp quyền tối thiểu đủ để hoàn thành nhiệm vụ. Quyền của workflow hoặc token cần phù hợp với loại sự kiện và ref.

| Tác vụ | Quyền thường cần | Quyền cần tránh cấp mặc định |
|---|---|---|
| Lint và unit test pull request | Đọc source | Ghi repository, publish package, deploy |
| Tạo báo cáo kiểm tra | Đọc source, lưu artifact theo chính sách | Secret production, signing key |
| Ghi nhận kết quả hoặc comment | Quyền ghi đúng tài nguyên cần thiết | Toàn quyền repository |
| Publish artifact chính thức | Quyền ghi đúng registry | Quyền quản trị cloud không liên quan |
| Deploy staging | Credential giới hạn cho staging | Credential production |
| Deploy production | Quyền triển khai production có kiểm soát | Quyền rộng hơn phạm vi dịch vụ |

Một số quy tắc thực hành:

- Khai báo permission tường minh thay vì phụ thuộc vào quyền mặc định rộng.
- Đặt quyền ở cấp job nếu các job có nhu cầu khác nhau.
- Dùng credential ngắn hạn hoặc OIDC/workload identity khi nền tảng hỗ trợ.
- Chỉ cấp secret cho job thực sự cần, sau khi điều kiện tin cậy đã được xác minh.
- Không ghi token, secret hoặc nội dung nhạy cảm ra log.
- Không lưu credential trong cache hoặc artifact.
- Dùng runner dùng một lần hoặc workspace sạch cho mã chưa tin cậy.
- Không chạy job đặc quyền trên runner tự quản lý có thể truy cập mạng nội bộ nếu mã nguồn đầu vào chưa được tin cậy.

Runner tự quản lý cần được chú ý đặc biệt. Nếu job từ fork có thể chạy trên runner dùng chung với job phát hành, mã độc có thể tìm cách đọc file còn sót lại, tiến trình khác, credential máy hoặc thông tin mạng nội bộ. Cần tách runner theo nhóm tin cậy, dọn workspace và hạn chế quyền hệ điều hành.

## 7. Xác minh sự kiện từ hệ thống bên ngoài

Ngoài sự kiện Git, pipeline có thể nhận webhook từ registry, hệ thống quản lý công việc, nền tảng triển khai hoặc dịch vụ bảo mật. Không nên tin payload chỉ vì endpoint nhận được request.

Một webhook đáng tin cậy cần xác minh tối thiểu:

1. **Chữ ký:** kiểm tra chữ ký HMAC hoặc cơ chế xác thực mà nhà cung cấp hỗ trợ.
2. **Nguồn gửi:** xác minh endpoint, tài khoản hoặc định danh ứng dụng đã được cấu hình.
3. **Tính mới:** kiểm tra timestamp, nonce hoặc event ID để giảm nguy cơ replay.
4. **Phạm vi:** chỉ chấp nhận repository, project, event type và tài nguyên nằm trong allowlist.
5. **Tính nhất quán:** tra cứu trạng thái tài nguyên qua API đáng tin khi payload chưa đủ bằng chứng.
6. **Quyền thực hiện:** ánh xạ loại sự kiện sang một hành động có giới hạn, không cho payload tùy ý chọn lệnh shell.

Ví dụ, webhook báo một image đã được publish không đủ để deploy ngay. Pipeline nên xác minh registry, repository image, digest, nguồn build và chính sách scan trước khi promotion.

Nếu webhook không có chữ ký hoặc cơ chế xác minh phù hợp, hãy coi nó như tín hiệu yêu cầu kiểm tra thêm. Không cấp quyền triển khai chỉ dựa trên nội dung JSON do bên gửi cung cấp.

## 8. Các trường dữ liệu sự kiện cần kiểm tra

Một pipeline có thể dùng dữ liệu sự kiện để chọn nhánh xử lý, nhưng cần coi những trường do contributor kiểm soát là dữ liệu không tin cậy.

| Trường | Cách sử dụng an toàn |
|---|---|
| Repository / project | So sánh với repository hoặc project được cho phép |
| Event type | Chỉ chấp nhận loại sự kiện mà workflow dự kiến xử lý |
| Branch / ref | So khớp ref đầy đủ; không dùng chuỗi tùy ý làm lệnh |
| Commit SHA | Dùng làm định danh mã nguồn; xác minh commit thuộc repository và ref mong muốn |
| Actor | Dùng cho audit và policy; không coi tên actor là bằng chứng duy nhất về độ tin cậy |
| Pull request number | Xác minh thuộc đúng repository trước khi gọi API |
| Title, body, branch name | Xem là dữ liệu không tin cậy; tránh ghép trực tiếp vào shell hoặc truy vấn |
| Artifact identifier | Xác minh nguồn, digest và quyền truy cập trước khi tải hoặc thực thi |

Không ghép dữ liệu sự kiện vào câu lệnh shell bằng cách nội suy chuỗi. Nếu phải truyền dữ liệu vào script, dùng tham số riêng, thư viện xử lý dữ liệu và quy tắc escape phù hợp. Với tên nhánh hoặc tiêu đề pull request, tránh giả định chỉ có chữ, số và dấu gạch nối.

## 9. Điều kiện chuyển từ không tin cậy sang tin cậy

Một đóng góp không trở nên đáng tin chỉ vì pipeline của nó đã chạy thành công. Test pass là bằng chứng về những kiểm tra đã chạy, không phải chứng minh mã không độc hại hoặc không có lỗi.

Một quy trình promotion có thể yêu cầu:

- Pull request đã được review theo chính sách.
- Required checks hoàn tất trên đúng commit cần merge.
- Commit được đưa vào nhánh được bảo vệ.
- Dependency và artifact đã qua các kiểm tra bảo mật cần thiết.
- Artifact gắn với commit SHA và pipeline run ID cụ thể.
- Provenance hoặc bằng chứng build có thể kiểm tra nếu tổ chức yêu cầu.
- Người có thẩm quyền phê duyệt phát hành khi cần.
- Deployment dùng đúng digest đã được xác minh.

Sau khi merge, pipeline phát hành nên build hoặc lấy artifact theo quy trình chính thức. Không nên tái sử dụng artifact từ một lần chạy pull request có quyền thấp như thể đó là artifact phát hành đã được tin cậy, trừ khi có cơ chế xác minh provenance và chính sách promotion rõ ràng.

## 10. Những tình huống dễ tạo ra lỗ hổng

| Tình huống | Rủi ro | Biện pháp |
|---|---|---|
| Dùng pull_request_target để chạy script từ fork | Mã không tin cậy chạy với ngữ cảnh đặc quyền | Dùng pull_request cho test; giữ pull_request_target cho metadata-only |
| Cấp secret cho mọi job | Pull request có thể làm lộ credential | Tách job, giới hạn secret và quyền theo ref |
| Chỉ kiểm tra tên nhánh | Nhánh có thể do contributor kiểm soát hoặc ref có thể bị thay đổi | Xác minh ref, commit, branch protection và trạng thái review |
| Dùng runner tự quản lý chung | Mã độc có thể truy cập workspace hoặc mạng nội bộ | Tách runner theo trust level, dùng runner tạm thời |
| Tin artifact từ workflow khác | Artifact có thể chứa dữ liệu hoặc script bị thao túng | Xác minh run nguồn, digest và provenance |
| Nội suy title hoặc branch name vào shell | Có thể dẫn đến command injection | Truyền tham số an toàn và xử lý dữ liệu không tin cậy |
| Tin webhook không xác minh | Kẻ khác có thể giả mạo sự kiện | Xác minh chữ ký, timestamp và phạm vi |
| Dùng actor làm tiêu chí duy nhất | Tài khoản hợp lệ vẫn có thể gửi thay đổi chưa review | Dựa vào ref, approval, checks và policy |

## 11. Checklist thiết kế trigger an toàn

Trước khi bật một trigger hoặc thêm job xử lý sự kiện mới, hãy kiểm tra:

- [ ] Đã xác định ai có thể tạo sự kiện và ref nào có thể kích hoạt pipeline.
- [ ] Đã phân biệt nguồn sự kiện với nguồn mã mà job sẽ checkout.
- [ ] Mã từ pull request hoặc fork được xem là chưa tin cậy trước khi review.
- [ ] Job xử lý đóng góp chỉ có quyền tối thiểu cần thiết.
- [ ] Không cấp secret phát hành hoặc cloud credential cho job chạy mã chưa tin cậy.
- [ ] Đã đánh giá rủi ro của pull_request_target và workflow_run nếu sử dụng.
- [ ] Runner xử lý mã không tin cậy được cô lập và dọn sạch sau lần chạy.
- [ ] Dữ liệu event như title, body, branch và actor được xử lý như đầu vào không tin cậy.
- [ ] Webhook bên ngoài được xác minh chữ ký, nguồn gửi và tính mới.
- [ ] Artifact từ workflow khác được xác minh nguồn và digest trước khi sử dụng.
- [ ] Luồng phát hành chỉ nhận commit và artifact đã qua các điều kiện promotion.
- [ ] Log lưu đủ event type, repository, ref, commit SHA và pipeline run ID để điều tra.

Thiết kế trigger an toàn bắt đầu từ việc hiểu mỗi sự kiện đại diện cho điều gì và dữ liệu nào có thể bị người gửi kiểm soát. Khi tách kiểm tra đóng góp khỏi phát hành có quyền cao, giới hạn token và secret theo từng job, đồng thời xác minh ref và artifact trước khi promotion, pipeline có thể tiếp nhận đóng góp từ nhiều nguồn mà vẫn giữ được ranh giới bảo mật và khả năng truy vết.

