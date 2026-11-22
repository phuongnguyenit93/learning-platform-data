# Tránh chạy trùng cùng một kiểm tra do nhiều sự kiện

Một commit được đẩy lên repository có thể đồng thời tạo ra nhiều sự kiện: push lên nhánh, cập nhật pull request, thay đổi trạng thái review hoặc đưa thay đổi vào merge queue. Nếu nhiều sự kiện cùng kích hoạt một pipeline giống nhau, hệ thống có thể build và chạy test lặp lại, tiêu tốn runner, làm hàng đợi dài hơn và tạo nhiều kết quả kiểm tra khó theo dõi.

Mục tiêu của việc kiểm soát trigger là bảo đảm mỗi thay đổi được kiểm tra trong đúng ngữ cảnh cần thiết, với số lần chạy hợp lý và kết quả có thể truy vết. Không phải cứ hai lần chạy cùng một commit là thừa: kiểm tra trên nhánh nguồn, kiểm tra trên trạng thái merge dự kiến và kiểm tra trong merge queue có thể xác minh những điều kiện khác nhau. Vì vậy, trước khi loại bỏ một lần chạy, cần xác định hai lần chạy có thực sự kiểm tra cùng một nội dung và cùng một điều kiện hay không.

## 1. Phân biệt sự kiện, lần chạy và kết quả kiểm tra

Các khái niệm sau thường bị gọi chung là trigger hoặc pipeline, nhưng chúng nằm ở những lớp khác nhau:

- **Sự kiện (event):** một điều xảy ra trong hệ thống, chẳng hạn push commit, mở pull request, cập nhật pull request, tạo tag hoặc yêu cầu triển khai.
- **Lần giao sự kiện (delivery):** một lần nền tảng gửi thông tin về sự kiện đến workflow hoặc webhook receiver. Một số nền tảng có thể gửi lại delivery khi gặp lỗi tạm thời.
- **Lần chạy workflow (workflow run):** một phiên thực thi được tạo ra để xử lý sự kiện.
- **Job hoặc stage:** đơn vị công việc bên trong workflow, ví dụ build, unit test, scan hoặc deploy.
- **Kết quả kiểm tra (check result):** trạng thái được báo về một commit, pull request hoặc đối tượng cần xác minh.

Một sự kiện có thể tạo nhiều workflow run; một workflow run có thể chứa nhiều job; một job có thể tạo nhiều check. Ngược lại, nhiều sự kiện khác nhau có thể dẫn đến cùng một loại kiểm tra. Muốn tránh chạy trùng, phải xác định lớp nào đang bị lặp.

Ví dụ, một commit trên nhánh tính năng được push khi pull request đã mở. Nền tảng có thể phát ra cả sự kiện push và pull_request synchronize. Nếu cả hai trigger đều khởi chạy workflow kiểm tra giống nhau, cùng một thay đổi có thể được build và test hai lần. Tuy nhiên, nếu một lần chạy kiểm tra commit của nhánh và lần còn lại kiểm tra merge result với nhánh đích mới nhất, chúng có mục đích khác nhau và không nên gộp chỉ dựa trên việc cùng xuất phát từ một commit.

## 2. Vì sao nhiều sự kiện có thể kích hoạt cùng một kiểm tra?

### Push và pull request cùng mô tả một thay đổi

Khi lập trình viên push commit lên nhánh đã có pull request, hệ thống thường phát ra sự kiện push và sự kiện cập nhật pull request. Nếu workflow lắng nghe cả hai loại sự kiện mà không có quy tắc phân chia, cùng một bộ test có thể chạy hai lần.

### Một pull request có nhiều hành động

Pull request có thể phát ra sự kiện khi được mở, đồng bộ commit mới, mở lại, chuyển sang trạng thái sẵn sàng review, chỉnh sửa tiêu đề hoặc thay đổi nhãn. Không phải hành động nào cũng cần chạy lại toàn bộ bộ kiểm tra.

Ví dụ, thêm nhãn để phân công reviewer thường không làm thay đổi mã nguồn. Ngược lại, hành động synchronize cho biết nhánh nguồn có commit mới và thường cần chạy lại các kiểm tra liên quan đến mã.

### Nhiều workflow cùng lắng nghe một sự kiện

Một repository có thể có workflow CI tổng quát, workflow kiểm tra tài liệu, workflow bảo mật và workflow build image. Đây có thể là phân chia hợp lý nếu mỗi workflow đảm nhận phạm vi khác nhau. Nhưng nếu nhiều workflow đều chạy cùng bộ unit test hoặc build cùng artifact mà không có lý do, tài nguyên sẽ bị sử dụng lặp lại.

### Trigger thủ công và trigger tự động chồng lấn

Người dùng có thể yêu cầu chạy lại workflow thủ công ngay sau khi một push đã kích hoạt pipeline. Nếu không kiểm tra trạng thái hiện tại và lý do chạy lại, hai phiên có thể cùng làm một công việc. Chạy lại có thể cần thiết khi runner hoặc dịch vụ phụ thuộc gặp sự cố; nhưng không nên dùng rerun như cách thay thế cho việc xác định nguyên nhân.

### Retry và giao sự kiện lặp

Webhook hoặc hệ thống tích hợp có thể gửi lại cùng một thông báo nếu không nhận được phản hồi đúng hạn. Receiver xử lý webhook cần nhận diện một delivery đã xử lý để tránh tạo thêm hành động. Retry của một job cũng có thể lặp lại thao tác đã thực hiện một phần.

### Nhiều nguồn kích hoạt cùng một quy trình phát hành

Một tag có thể tạo sự kiện push tag và sự kiện release. Nếu cả hai đều chạy quy trình đóng gói và phát hành giống nhau, hệ thống có thể tạo artifact hoặc phát hành lặp. Cần chọn một sự kiện làm nguồn điều phối chính hoặc thiết kế bước phát hành có tính idempotent.

## 3. Xác định khi nào hai lần chạy thực sự bị trùng

Không nên chỉ so sánh tên branch hoặc commit SHA. Hai lần chạy chỉ có thể xem là trùng khi chúng cùng mục tiêu kiểm tra, cùng nội dung đầu vào và cùng ngữ cảnh cần xác minh.

Trước khi gộp hoặc loại bỏ trigger, hãy trả lời:

1. Hai lần chạy có kiểm tra cùng commit hoặc cùng trạng thái mã nguồn không?
2. Cả hai có dùng cùng nhánh đích, cấu hình, biến môi trường và dependency không?
3. Kết quả có được báo về cùng một đối tượng và cùng một check context không?
4. Một lần chạy có xác minh trạng thái merge dự kiến, merge queue hoặc môi trường khác không?
5. Một lần chạy có phải là retry sau thất bại, còn lần kia là lần chạy mới do commit khác không?

Một khóa nhận diện (deduplication key) hữu ích có thể kết hợp các trường:

- Repository hoặc project.
- Tên workflow và loại kiểm tra.
- Pull request number hoặc ref cần kiểm tra.
- Commit SHA đầu vào.
- Nhánh đích hoặc loại merge context.
- Cấu hình kiểm tra quan trọng, nếu cấu hình làm thay đổi kết quả.

Ví dụ, khóa cho unit test của pull request có thể được hiểu là repository + workflow + pull request + head SHA + loại kiểm tra. Kiểm tra merge queue phải có định danh merge group hoặc merge result riêng. Nếu bỏ nhánh đích hoặc merge context, hai lần chạy có thể bị coi là giống nhau dù đang xác minh hai tổ hợp mã khác nhau.

### Head SHA và merge SHA không phải lúc nào cũng giống nhau

Trong một số nền tảng, pull request được kiểm tra bằng một commit merge tạm thời giữa nhánh nguồn và nhánh đích. Head SHA đại diện cho commit cuối của nhánh nguồn; merge SHA đại diện cho trạng thái hợp nhất dự kiến. Khi nhánh đích thay đổi, merge SHA có thể thay đổi dù head SHA của pull request không đổi.

Nếu mục tiêu là kiểm tra mã nguồn của nhánh, head SHA có thể là định danh phù hợp. Nếu mục tiêu là bảo đảm thay đổi có thể hợp nhất với nhánh đích hiện tại, cần xác minh merge result hoặc merge group. Không nên dùng một khóa duy nhất cho cả hai mục tiêu.

## 4. Thiết kế ma trận sự kiện trước khi cấu hình

Một ma trận sự kiện giúp xác định nguồn kích hoạt có thẩm quyền cho từng loại kiểm tra:

| Sự kiện | Khi nào nên chạy | Kiểm tra thường phù hợp |
|---|---|---|
| Pull request opened | Khi tạo yêu cầu tích hợp | CI nhanh, lint, build và test cần thiết |
| Pull request synchronize | Khi nhánh nguồn có commit mới | Chạy lại các kiểm tra phụ thuộc mã nguồn |
| Pull request reopened | Khi mở lại một PR đã đóng | Kiểm tra lại nếu trạng thái mã hoặc chính sách đã thay đổi |
| Pull request labeled/unlabeled | Khi thay đổi nhãn | Chỉ chạy công việc thực sự phụ thuộc nhãn |
| Push lên nhánh chính | Khi thay đổi đã được tích hợp | CI của nhánh chính, tạo artifact hoặc kiểm tra sau merge |
| Push lên nhánh tính năng | Khi nhóm muốn xác minh nhánh độc lập | Chạy khi không có PR hoặc khi kiểm tra đó có mục tiêu riêng |
| Merge queue / merge group | Khi nền tảng chuẩn bị tích hợp thay đổi | Xác minh tổ hợp mã sẽ được merge |
| Tag hoặc release | Khi tạo phiên bản | Đóng gói, ký, phát hành và xác minh artifact |
| Schedule | Theo lịch định kỳ | Kiểm tra toàn diện, cập nhật dependency hoặc kiểm tra bảo trì |
| Manual dispatch | Khi có người yêu cầu có chủ đích | Chạy lại hoặc tác vụ vận hành với đầu vào rõ ràng |

Ma trận này không phải cấu hình mặc định cho mọi repository. Hãy điều chỉnh theo chiến lược nhánh, loại kiểm thử và nền tảng CI. Điểm quan trọng là mỗi loại kiểm tra có nguồn kích hoạt rõ, thay vì để mọi workflow lắng nghe mọi sự kiện.

### Một cách phân chia thường dùng

Với nhóm sử dụng pull request, có thể chọn:

- Pull request là nguồn kích hoạt CI cho các nhánh tính năng.
- Push lên nhánh chính là nguồn kích hoạt CI sau merge.
- Merge queue là nguồn kích hoạt kiểm tra tổ hợp trước khi merge khi repository sử dụng tính năng này.
- Tag hoặc release là nguồn kích hoạt đóng gói và phát hành.
- Schedule dành cho các kiểm tra định kỳ không cần chạy theo từng commit.

Khi đã chọn quy tắc, hãy kiểm tra các luồng ngoại lệ: pull request từ fork, nhánh release, hotfix, merge queue và workflow được gọi từ workflow khác.

## 5. Lọc sự kiện ở cấp workflow

Lọc ở cấp workflow giúp hệ thống không tạo workflow run khi sự kiện không thuộc phạm vi. Nên giới hạn loại sự kiện, hành động, nhánh và đường dẫn ngay tại cấu hình trigger nếu nền tảng hỗ trợ.

Ví dụ GitHub Actions: chạy CI cho pull request hướng vào main, push trực tiếp lên main và merge queue:

~~~yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  merge_group:
    types:
      - checks_requested

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run validation
        run: ./gradlew check
~~~

Trong ví dụ này, push lên nhánh tính năng không khởi chạy workflow này. Pull request đảm nhiệm kiểm tra thay đổi trước khi merge; push lên main đảm nhiệm kiểm tra trạng thái sau merge; merge_group đảm nhiệm xác minh trạng thái dự kiến trong merge queue. Nhờ đó, cùng một commit trên nhánh tính năng không tự động tạo thêm một workflow push trùng với workflow pull request.

Nếu repository cần CI độc lập cho nhánh chưa mở pull request, có thể thêm trigger push cho các nhánh đó, nhưng phải xác định cách tránh chạy lặp khi nhánh đã có pull request. Có thể tách workflow hoặc dùng điều kiện rõ ràng theo sự kiện và trạng thái PR.

### Lọc hành động của pull request

Nếu chỉ một số hành động làm thay đổi nội dung cần kiểm tra, hãy giới hạn danh sách action:

~~~yaml
on:
  pull_request:
    branches:
      - main
    types:
      - opened
      - synchronize
      - reopened
      - ready_for_review
~~~

Các hành động như thay đổi nhãn hoặc tiêu đề có thể được xử lý bằng workflow riêng nếu có nhu cầu. Không nên thêm mọi action vào danh sách chỉ vì muốn nhận đầy đủ sự kiện.

### Lọc theo đường dẫn

Nếu workflow chỉ kiểm tra tài liệu, có thể dùng path filter để chạy khi tài liệu thay đổi. Nếu workflow build backend, có thể giới hạn vào thư mục mã nguồn và các file cấu hình liên quan. Tuy nhiên, phải tính đến dependency: thay đổi build script, lockfile, thư viện dùng chung hoặc workflow YAML có thể ảnh hưởng đến nhiều thành phần dù không nằm trong thư mục mã nguồn chính.

Một path filter quá hẹp có thể bỏ qua thay đổi ảnh hưởng gián tiếp. Hãy lập danh sách đường dẫn phụ thuộc và có cách chạy kiểm tra toàn diện khi thay đổi cấu hình nền tảng.

Trên GitHub Actions, workflow bị bỏ qua bởi bộ lọc branch hoặc path có thể để lại required check ở trạng thái pending và chặn merge. Khi check là bắt buộc, cân nhắc để workflow luôn được tạo rồi dùng điều kiện ở cấp job, hoặc thiết kế một check tổng hợp luôn báo trạng thái rõ ràng. Cần kiểm tra hành vi cụ thể của nền tảng trước khi đưa filter vào branch protection.

## 6. Dùng điều kiện ở cấp job để tránh công việc thừa

Không phải lúc nào cũng cần bỏ toàn bộ workflow. Một workflow có thể nhận nhiều sự kiện nhưng chỉ chạy những job cần thiết theo loại event hoặc phạm vi thay đổi.

Ví dụ GitHub Actions: một job chỉ chạy khi workflow được kích hoạt bởi pull request:

~~~yaml
jobs:
  pr-tests:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew test

  main-validation:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew check
~~~

Điều kiện cấp job hữu ích khi nhiều loại event cùng vào một workflow nhưng cần các bước khác nhau. Hãy bảo đảm mọi nhánh điều kiện đều có kết quả check dễ hiểu, đặc biệt khi một check là điều kiện bắt buộc để merge.

### Không nhầm điều kiện với bảo mật

Một điều kiện chỉ quyết định job có chạy hay không; nó không tự làm cho dữ liệu hoặc mã nguồn của pull request trở nên đáng tin cậy. Với pull request từ fork, cần xem xét quyền token, secret và quyền ghi. Tránh chạy mã không đáng tin cậy trong ngữ cảnh có quyền cao. Đặc biệt, workflow dùng sự kiện có quyền truy cập repository đích không nên checkout rồi thực thi tùy tiện mã do người gửi pull request kiểm soát.

## 7. Dùng concurrency để thay thế các lần chạy đã lỗi thời

Khi một pull request nhận commit mới liên tiếp, các lần chạy cũ có thể vẫn đang thực hiện. Kết quả của commit cũ thường không còn giúp quyết định có merge commit mới hay không. Cơ chế concurrency có thể giới hạn số lần chạy đồng thời trong cùng một nhóm và hủy phiên cũ khi có phiên mới hơn.

Ví dụ GitHub Actions:

~~~yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
~~~

Nhóm concurrency được tạo theo workflow và pull request number; với sự kiện không có pull request thì dùng ref. Khi một lần chạy mới trong cùng nhóm bắt đầu, phiên đang chạy có thể bị hủy. Điều này phù hợp với kiểm tra có thể chạy lại từ đầu trên commit mới nhất.

Không nên bật hủy tự động cho mọi workflow. Một công việc phát hành, triển khai hoặc migration có thể đã tạo tác động bên ngoài; hủy giữa chừng có thể để lại trạng thái không hoàn chỉnh. Với các công việc như vậy, cần thiết kế bước an toàn khi dừng, cơ chế khóa và khả năng tiếp tục hoặc phục hồi.

### Concurrency không phải là deduplication tuyệt đối

Concurrency giới hạn hoặc thay thế các lần chạy trong cùng nhóm. Nó không chứng minh hai event giống nhau, không đảm bảo một thao tác chỉ được thực hiện đúng một lần và không thay thế idempotency. Một workflow có thể hoàn tất trước khi lần chạy mới đến; một lần chạy khác nhóm có thể chạy song song; hoặc hệ thống có thể gửi lại một sự kiện sau khi job đã thực hiện tác động.

Hãy dùng concurrency cho mục tiêu quản lý tài nguyên và loại bỏ kết quả đã lỗi thời. Dùng event filter và khóa nhận diện cho mục tiêu tránh tạo công việc không cần thiết. Dùng idempotency cho mục tiêu bảo vệ thao tác có tác động bên ngoài.

## 8. Bảo vệ thao tác bằng idempotency

Một thao tác **idempotent** có thể được thực hiện nhiều lần với cùng đầu vào mà trạng thái cuối cùng không bị nhân đôi hoặc sai lệch. Điều này đặc biệt quan trọng với deploy, tạo release, upload artifact, gửi thông báo hoặc cập nhật hệ thống bên ngoài.

Ví dụ, trước khi tạo release cho tag v2.4.0, hệ thống kiểm tra release có cùng tag và cùng artifact digest đã tồn tại hay chưa. Nếu đã có, workflow xác minh và trả về kết quả hiện tại thay vì tạo release thứ hai.

Một khóa idempotency có thể được tạo từ:

- Repository hoặc project.
- Môi trường đích.
- Phiên bản hoặc tag.
- Artifact digest.
- Loại hành động, chẳng hạn deploy hoặc publish.

Hệ thống nhận yêu cầu nên lưu khóa và kết quả xử lý trong một nơi có tính nhất quán. Nếu hai request cùng khóa đến đồng thời, chỉ một request được phép thực hiện tác động; request còn lại nhận kết quả đã có hoặc trạng thái đang xử lý. Nếu chỉ kiểm tra trước rồi mới ghi mà không có ràng buộc duy nhất, hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

Với API bên ngoài, ưu tiên truyền idempotency key nếu API hỗ trợ. Nếu không hỗ trợ, cần có cơ chế đối soát trạng thái sau timeout vì client có thể không biết request trước đã thành công hay chưa.

## 9. Xử lý webhook giao lặp và retry

Nếu tự xây dựng webhook receiver để kích hoạt pipeline, nên xử lý delivery theo quy trình:

1. Xác thực chữ ký và nguồn gửi trước khi tin cậy payload.
2. Đọc delivery ID hoặc event ID do nguồn gửi cung cấp.
3. Ghi nhận ID trong kho lưu trữ có ràng buộc duy nhất.
4. Nếu ID đã được xử lý, trả phản hồi thành công phù hợp mà không tạo hành động mới.
5. Nếu là sự kiện mới, ghi nhận trạng thái tiếp nhận và đưa công việc vào hàng đợi.
6. Worker xử lý công việc theo khóa idempotency; cập nhật trạng thái thành công hoặc thất bại.
7. Cho phép retry có giới hạn đối với lỗi tạm thời và giữ dấu vết để đối soát.

Không nên giữ kết nối webhook mở trong lúc chạy build hoặc deploy kéo dài. Receiver nên xác nhận tiếp nhận nhanh sau khi đã lưu bền vững, rồi xử lý bất đồng bộ.

Delivery ID nhận diện một lần giao thông báo; nó không nhất thiết nhận diện một thay đổi mã nguồn. Hai event khác nhau có thể cùng mô tả một commit. Vì vậy, hệ thống có thể cần cả event ID để chống xử lý lại delivery và khóa nghiệp vụ để hợp nhất các yêu cầu cùng mục tiêu.

## 10. Các nền tảng CI có cơ chế khác nhau

Nguyên tắc chung là chọn nguồn sự kiện, giới hạn hành động và bảo vệ thao tác lặp. Cú pháp và ý nghĩa của từng cơ chế tùy nền tảng.

### GitHub Actions

- Dùng phần on để chọn event, branch, path và action.
- Dùng điều kiện if ở job hoặc step để giới hạn công việc theo event payload.
- Dùng concurrency để giới hạn các lần chạy cùng nhóm và có thể hủy lần chạy lỗi thời.
- Khi sử dụng merge queue, cấu hình sự kiện merge_group và bảo đảm check bắt buộc được báo trên merge group.

### GitLab CI

Có thể dùng workflow rules để chọn nguồn pipeline và ngăn tạo pipeline không thuộc luồng mong muốn. Ví dụ dưới đây ưu tiên pipeline merge request và pipeline push lên nhánh mặc định:

~~~yaml
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
    - when: never
~~~

Quy tắc này là ví dụ tối giản. Repository có thể cần thêm lịch, tag, trigger hoặc pipeline con. Cần kiểm tra các loại pipeline được tạo khi vừa có push vừa có merge request để tránh bỏ sót kiểm tra cần thiết.

GitLab resource_group có thể tuần tự hóa job dùng chung tài nguyên, chẳng hạn triển khai cùng một môi trường. Nó giải quyết tranh chấp đồng thời; bản thân nó không chứng minh hai pipeline là trùng và không tự loại bỏ một pipeline đã tạo.

### Jenkins và các hệ thống khác

Với Jenkins hoặc hệ thống CI tự quản, cần xem xét webhook trigger, polling SCM, multibranch indexing, build cause và cơ chế khóa tài nguyên. Nếu webhook và polling cùng phát hiện một commit, có thể xuất hiện hai build. Nên chọn một cơ chế phát hiện chính hoặc dùng logic nhận diện build theo repository, ref và revision.

Tên tùy chọn có thể khác nhau giữa các phiên bản và plugin. Hãy kiểm tra hành vi thực tế của plugin trigger, đặc biệt khi có retry, multibranch pipeline và build được gọi từ upstream job.

## 11. Quan sát và chẩn đoán lần chạy trùng

Để biết chính sách trigger có hiệu quả, mỗi workflow run nên ghi lại tối thiểu:

- Event name và action.
- Repository, branch/ref và pull request number nếu có.
- Head SHA, merge SHA hoặc merge group ID theo ngữ cảnh.
- Workflow name, job name và run ID.
- Delivery ID nếu nguồn sự kiện cung cấp.
- Lý do job được chạy hoặc bị bỏ qua.
- Khóa concurrency hoặc idempotency liên quan.
- Kết quả, thời điểm bắt đầu và kết thúc.

Một dashboard có thể theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Workflow runs trên mỗi commit hoặc PR | Phát hiện cùng thay đổi bị kích hoạt quá nhiều lần |
| Số job lặp theo loại kiểm tra | Xác định build/test nào bị chạy lặp |
| Tỷ lệ run bị hủy do concurrency | Cho biết có nhiều phiên lỗi thời được tạo |
| Thời gian chờ runner và phút runner tiêu thụ | Đánh giá chi phí của trigger dư thừa |
| Tỷ lệ delivery bị nhận lại | Phát hiện vấn đề webhook hoặc receiver |
| Số lần publish/deploy lặp | Xác định rủi ro tác động bên ngoài |
| Tỷ lệ check bắt buộc bị pending | Phát hiện filter làm mất kết quả cần thiết |

Khi thấy hai run gần nhau, so sánh event, SHA, PR number, merge context, workflow và job. Không kết luận trùng chỉ dựa vào thời điểm bắt đầu hoặc tên branch.

## 12. Kiểm thử chính sách trigger trước khi áp dụng

Thay đổi trigger có thể vô tình làm mất một lần kiểm tra bắt buộc hoặc bỏ qua nhánh phát hành. Trước khi áp dụng rộng, hãy lập bảng tình huống và xác minh kết quả mong đợi:

| Tình huống | Kết quả mong đợi |
|---|---|
| Push commit lên nhánh tính năng chưa có PR | Chạy CI nhánh nếu nhóm yêu cầu kiểm tra độc lập |
| Push commit lên nhánh đã có PR | Chạy đúng bộ kiểm tra PR; không tạo thêm bộ kiểm tra push trùng mục tiêu |
| Mở PR mới | Tạo các check bắt buộc cho PR |
| Push commit mới lên PR | Kiểm tra lại SHA mới và làm mất hiệu lực kết quả cũ khi phù hợp |
| Đổi nhãn hoặc tiêu đề PR | Không chạy lại test mã nguồn nếu không có phụ thuộc |
| Đóng rồi mở lại PR | Áp dụng chính sách kiểm tra lại theo trạng thái và thay đổi kể từ lần chạy trước |
| Merge vào nhánh chính | Chạy CI sau merge và các bước tạo artifact cần thiết |
| Merge queue tạo merge group | Báo đầy đủ các check được yêu cầu trên merge group |
| Tạo tag hoặc release | Chỉ tạo một lần phát hành cho cùng phiên bản và artifact |
| Webhook được gửi lại | Không tạo thêm hành động cho cùng delivery |
| Người dùng rerun thủ công | Chạy lại có chủ đích và lưu nguyên nhân |

Ngoài bảng tình huống, kiểm tra log của một số lần chạy thực tế và xác nhận branch protection hoặc quy tắc merge vẫn nhận được check cần thiết. Khi thay đổi cấu hình trên repository quan trọng, triển khai trước trên một repository thử nghiệm hoặc một workflow ít rủi ro.

## 13. Các lỗi thiết kế thường gặp

### Dùng concurrency như cơ chế chống trùng duy nhất

Concurrency có thể hủy hoặc xếp hàng lần chạy, nhưng không bảo đảm tác động bên ngoài chỉ xảy ra một lần. Hãy bổ sung idempotency cho thao tác publish, deploy và webhook.

### Chỉ dùng commit SHA làm khóa

Cùng head SHA có thể được kiểm tra trên các nhánh đích hoặc merge context khác nhau. Khóa cần phản ánh đúng mục tiêu kiểm tra.

### Bỏ qua merge queue

Nếu nhánh chính yêu cầu check từ merge queue mà workflow chỉ lắng nghe pull_request và push, merge group có thể không nhận được check cần thiết. Thêm và xác minh trigger riêng cho luồng merge queue.

### Lọc path quá hẹp

Thay đổi build script, lockfile hoặc cấu hình chung có thể ảnh hưởng nhiều thành phần. Path filter cần tính đến phụ thuộc gián tiếp và có cách chạy kiểm tra rộng khi cần.

### Hủy mọi workflow khi có phiên bản mới

Một lần chạy CI có thể an toàn để hủy; một lần triển khai hoặc migration có thể không an toàn. Chỉ bật cancel-in-progress cho công việc có thể dừng và chạy lại an toàn.

### Không ghi lại lý do bỏ qua job

Một job không chạy có thể là do điều kiện hợp lệ, cấu hình sai hoặc thiếu dữ liệu. Ghi rõ điều kiện và event giúp phân biệt hành vi dự kiến với lỗi cấu hình.

### Cho rằng retry luôn an toàn

Retry có thể lặp lại thao tác đã thành công nhưng client chưa nhận được phản hồi. Trước khi retry, kiểm tra trạng thái hoặc dùng idempotency key để tránh tạo bản phát hành, deploy hay thông báo trùng.

## 14. Quy tắc thực hành

- Xác định mục tiêu kiểm tra và ngữ cảnh đầu vào trước khi quyết định hai trigger có trùng nhau.
- Chọn nguồn sự kiện có thẩm quyền cho từng loại kiểm tra: pull request, push nhánh chính, merge queue, tag/release hoặc lịch.
- Lọc event, action, branch và path ở cấp workflow khi phù hợp; dùng điều kiện cấp job cho các khác biệt bên trong workflow.
- Dùng concurrency để hạn chế phiên chạy lỗi thời, nhưng chỉ hủy công việc có thể dừng an toàn.
- Dùng khóa idempotency và kiểm tra trạng thái trước khi thực hiện tác động bên ngoài.
- Với webhook receiver, xác thực nguồn, lưu delivery ID và xử lý bất đồng bộ có khả năng retry.
- Giữ đầy đủ check bắt buộc cho pull request và merge queue; xác minh branch protection sau khi đổi trigger.
- Theo dõi run theo commit, PR, event và loại kiểm tra để tìm phần lặp thực sự.

Tránh chạy trùng không chỉ giúp tiết kiệm phút runner. Chính sách trigger rõ ràng còn làm cho kết quả CI dễ hiểu, check bắt buộc đáng tin cậy và thao tác phát hành an toàn khi có retry hoặc nhiều sự kiện cùng đến. Khi một thay đổi cần được xác minh ở nhiều ngữ cảnh, hãy giữ các lần chạy có mục đích riêng; khi chúng chỉ lặp lại cùng một kiểm tra trên cùng đầu vào, hãy hợp nhất nguồn kích hoạt hoặc dùng cơ chế kiểm soát phù hợp.
