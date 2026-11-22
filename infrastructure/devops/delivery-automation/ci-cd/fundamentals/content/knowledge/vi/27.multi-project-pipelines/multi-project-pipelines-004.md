# Phối hợp artifact và hợp đồng giữa nhiều kho mã

Trong một hệ thống gồm nhiều dịch vụ hoặc thư viện, một thay đổi ở kho mã này có thể ảnh hưởng đến cách kho mã khác build, kiểm thử hoặc triển khai. Dịch vụ A có thể phát hành một thư viện mà dịch vụ B sử dụng; một producer có thể thay đổi schema sự kiện mà nhiều consumer đang đọc; hoặc frontend và backend có thể được phát triển trong hai repository riêng nhưng phải tương thích khi phát hành.

Nếu mỗi repository chỉ kiểm tra mã nguồn của chính nó, pipeline có thể xanh trong từng kho nhưng toàn hệ thống vẫn không hoạt động. Nguyên nhân thường nằm ở artifact không đúng phiên bản, hợp đồng giao tiếp bị phá vỡ, thứ tự phát hành không phù hợp hoặc pipeline downstream kiểm thử nhầm một bản build mới nhất chưa được xác minh.

Với CI/CD nhiều dự án, cần phối hợp hai thứ có quan hệ chặt chẽ: **artifact được tạo ra và hợp đồng mà artifact phải tuân thủ**. Artifact cần có định danh bất biến để kho khác có thể tải đúng nội dung. Hợp đồng cần được phiên bản hóa, kiểm tra tương thích và gắn với phiên bản artifact tương ứng. Nhờ vậy, các repository có thể phát triển độc lập mà vẫn tạo thành một luồng phát hành có thể truy vết.

## 1. Vai trò của producer, consumer, artifact và contract

Trong một luồng nhiều repository, một dự án có thể là producer ở một quan hệ và là consumer ở quan hệ khác.

- **Producer** là repository tạo ra một thành phần được dự án khác sử dụng, chẳng hạn package, container image, API, schema sự kiện hoặc bộ cấu hình.
- **Consumer** là repository sử dụng thành phần đó, gọi API hoặc đọc dữ liệu theo hợp đồng do producer cung cấp.
- **Artifact** là đầu ra đã được build và đóng gói, ví dụ thư viện JAR, container image, file frontend, package hoặc bundle triển khai.
- **Contract** là thỏa thuận có thể kiểm tra về giao tiếp hoặc cách sử dụng artifact, ví dụ API schema, event schema, public interface, định dạng cấu hình, quy tắc xác thực hoặc semantics của một thao tác.
- **Release metadata** là thông tin nhận diện nguồn tạo artifact và quá trình xác minh, chẳng hạn commit, pipeline run, digest, phiên bản contract và kết quả kiểm thử.

Một ví dụ đơn giản:

    repository payments-api
        -> build image payments-api
        -> publish artifact và OpenAPI contract
        -> repository checkout-service tải contract
        -> kiểm tra client và contract test
        -> xác minh phiên bản tích hợp

Artifact và contract có thể được phát hành cùng nhau hoặc dưới dạng hai gói liên kết. Điều quan trọng là consumer biết chính xác contract nào mô tả artifact nào. Nếu chỉ tải một file schema có tên chung như latest, consumer không thể chứng minh mình đang kiểm thử đúng giao diện của phiên bản sắp triển khai.

## 2. Xác định ranh giới và quan hệ phụ thuộc giữa repository

Trước khi thiết kế pipeline, hãy lập bản đồ quan hệ giữa các dự án. Một dependency có thể là quan hệ build-time, test-time hoặc runtime:

| Quan hệ | Ví dụ | Điều pipeline cần bảo đảm |
| --- | --- | --- |
| Build-time | Ứng dụng phụ thuộc vào thư viện dùng chung | Lấy đúng package version và checksum |
| Contract-time | Consumer tạo client từ OpenAPI hoặc Protobuf | Kiểm tra schema và quy tắc tương thích |
| Test-time | Dịch vụ cần một service khác để chạy integration test | Dùng phiên bản môi trường kiểm thử đã xác định |
| Runtime | Frontend gọi backend hoặc service A gọi service B | Các phiên bản có thể giao tiếp trong giai đoạn triển khai |
| Release-time | Một nhóm dịch vụ phải được phát hành theo cùng một đợt | Điều phối thứ tự, điều kiện và trạng thái phát hành |

Không phải mọi quan hệ đều cần pipeline kích hoạt trực tiếp. Một thư viện có thể chỉ cần phát hành package mới; các consumer sau đó cập nhật dependency theo lịch hoặc theo pull request. Một API thay đổi contract quan trọng có thể cần kích hoạt kiểm tra ở tất cả consumer đang được hỗ trợ. Hãy xác định quan hệ nào cần phản hồi tự động và quan hệ nào chỉ cần ghi nhận phiên bản.

Nên biểu diễn dependency thành đồ thị có hướng. Nếu A tạo artifact cho B và B tạo artifact cho C, thứ tự xác minh là A, sau đó B, rồi C. Chu trình phụ thuộc như A chờ B phát hành trong khi B lại chờ A có thể làm pipeline deadlock hoặc buộc nhóm phát hành nhiều dự án cùng lúc. Khi phát hiện chu trình, hãy xem lại ranh giới module, tách contract độc lập hoặc xác định một điểm tích hợp có phiên bản rõ ràng.

## 3. Phát hành artifact bất biến

Consumer cần tải đúng artifact mà producer đã kiểm thử. Vì vậy, artifact được dùng giữa các repository phải có định danh ổn định và nội dung không bị thay đổi sau khi publish.

Một quy trình đáng tin cậy thường có các bước:

1. Checkout đúng commit của producer.
2. Build artifact một lần bằng toolchain và dependency đã khóa phiên bản.
3. Chạy kiểm tra cần thiết trên artifact đó.
4. Tính checksum hoặc digest và lưu metadata của lần build.
5. Publish artifact vào registry hoặc kho lưu trữ có kiểm soát.
6. Cấp cho consumer phiên bản và digest để tải chính xác.
7. Promote cùng artifact đã xác minh qua các môi trường.

Ví dụ, một image có tag `payments-api:2.4.1` vẫn có thể bị ghi đè nếu registry cho phép tái sử dụng tag. Khi đó, consumer dùng tag này ở hai thời điểm khác nhau có thể nhận hai nội dung khác nhau. Digest như `sha256:...` xác định nội dung image cụ thể và phù hợp hơn để khóa một lần tích hợp hoặc triển khai.

Tag phiên bản dễ đọc và hữu ích cho con người, nhưng digest là bằng chứng định danh nội dung. Nên lưu cả hai: phiên bản phục vụ quản lý release, digest phục vụ xác minh chính xác artifact.

    producer commit 7fa31c2
        -> build image
        -> image tag 2.4.1
        -> digest sha256:abc...
        -> publish
        -> consumer pin digest sha256:abc...

Không dùng nhãn thay đổi liên tục như latest, stable hoặc tên nhánh làm định danh duy nhất cho artifact trong một release đã được phê duyệt. Có thể dùng nhãn đó để khám phá phiên bản mới, nhưng sau khi chọn phiên bản cần ghi lại version và digest cụ thể.

## 4. Phiên bản hóa hợp đồng

Hợp đồng phải có phiên bản và phải được liên kết với producer cùng artifact tương ứng. Tùy loại giao tiếp, contract có thể là:

- OpenAPI hoặc AsyncAPI cho HTTP API và giao tiếp bất đồng bộ.
- Protobuf, Avro hoặc JSON Schema cho payload và event.
- Public API hoặc metadata của package cho thư viện dùng chung.
- Schema database và quy tắc migration cho dữ liệu được nhiều dịch vụ truy cập.
- Cấu trúc file, biến cấu hình, exit code hoặc giao thức dòng lệnh cho công cụ nội bộ.

Không phải mọi thay đổi contract đều cần tăng major version. Hãy đánh giá ảnh hưởng với consumer hiện hữu:

| Thay đổi | Khả năng tương thích thường gặp | Việc cần xác minh |
| --- | --- | --- |
| Thêm trường tùy chọn có default an toàn | Thường tương thích ngược nếu consumer bỏ qua trường lạ | Consumer cũ có chấp nhận payload mới không |
| Thêm giá trị enum | Có thể phá vỡ consumer dùng enum đóng | Consumer có xử lý giá trị chưa biết không |
| Xóa hoặc đổi tên trường | Thường phá vỡ consumer cũ | Đã có giai đoạn chuyển đổi và đo mức sử dụng chưa |
| Đổi kiểu dữ liệu hoặc semantics | Có thể phá vỡ cả compile-time lẫn runtime | Contract test và kiểm thử dữ liệu thực tế |
| Thêm endpoint hoặc operation mới | Thường tương thích nếu không làm thay đổi hành vi cũ | Quyền truy cập, xác thực và semantics mới |
| Siết validation hoặc thay đổi mặc định | Có thể phá vỡ consumer dù schema bề ngoài không đổi | Test với các request và dữ liệu đang được hỗ trợ |

Semantic Versioning có thể hữu ích với package hoặc contract có quy tắc tương thích rõ: patch cho sửa lỗi tương thích, minor cho mở rộng tương thích, major cho thay đổi phá vỡ. Tuy nhiên, không nên chỉ dựa vào con số phiên bản. Một thay đổi nhỏ về cú pháp vẫn có thể phá vỡ consumer nếu semantics thay đổi; ngược lại, một major version không nhất thiết buộc tất cả consumer chuyển đổi cùng ngày nếu hệ thống hỗ trợ nhiều phiên bản song song.

Với API hoặc event, cần xem cả tương thích phía đọc và phía ghi. Một consumer mới có thể đọc payload cũ nhưng producer cũ chưa chắc xử lý payload mới. Với hệ thống event, schema registry thường hỗ trợ chính sách backward, forward hoặc full compatibility; nhóm phải chọn chính sách phù hợp với thứ tự triển khai và thời gian lưu giữ message.

## 5. Kiểm thử contract giữa producer và consumer

Unit test của producer có thể chứng minh logic nội bộ đúng, nhưng không chứng minh consumer sử dụng API đúng cách. Integration test của consumer cũng có thể xanh nếu nó dùng mock không phản ánh giao diện thật. Contract test giúp kiểm tra ranh giới giữa hai dự án.

Có hai hướng kiểm tra thường dùng:

- **Provider verification:** producer xác minh rằng phiên bản API hoặc schema thực tế đáp ứng các contract đã công bố và các consumer được hỗ trợ.
- **Consumer-driven contract test:** consumer mô tả những tương tác mà nó cần; producer chạy xác minh để bảo đảm không phá vỡ các nhu cầu đó.

Một luồng cơ bản:

1. Consumer tạo hoặc cập nhật contract test từ các request, response và hành vi mà nó sử dụng.
2. Contract được publish thành artifact có phiên bản, gắn với commit của consumer.
3. Producer tải các contract còn hiệu lực của consumer được hỗ trợ.
4. Producer chạy verification trên bản build ứng viên.
5. Kết quả verification được lưu cùng phiên bản producer và contract.
6. Consumer chỉ nâng dependency hoặc triển khai khi contract và các kiểm tra liên quan đạt.

Contract test không thay thế mọi integration test. Nó tập trung vào thỏa thuận giao tiếp và thường chạy nhanh hơn việc dựng toàn bộ hệ thống. Integration hoặc end-to-end test vẫn cần thiết để xác minh authentication, network, database, cấu hình môi trường và hành vi xuyên nhiều thành phần.

Để tránh kiểm thử một tập consumer lỗi thời, cần có chính sách vòng đời contract: ai sở hữu contract, consumer nào đang hoạt động, khi nào contract hết hạn và điều kiện nào cho phép ngừng hỗ trợ. Không xóa contract chỉ vì một repository không có build gần đây; có thể đó là consumer được triển khai theo lịch hoặc ở môi trường riêng.

## 6. Thiết kế luồng pipeline producer và consumer

Một mẫu phổ biến là producer build và publish artifact trước, sau đó kích hoạt pipeline của consumer bằng thông tin phiên bản bất biến.

Ví dụ payload kích hoạt downstream có thể mang các trường sau:

    event_type: artifact_published
    producer: payments-api
    producer_commit: 7fa31c2
    artifact:
      name: payments-api
      version: 2.4.1
      digest: sha256:abc...
    contract:
      name: payments-openapi
      version: 2.4.1
      digest: sha256:def...
    producer_pipeline_run: ci-1842

Consumer dùng event này để tải đúng artifact và contract, chạy kiểm tra tương thích, build ứng dụng với dependency đã pin và lưu kết quả. Event không nên chỉ truyền tên nhánh hoặc từ khóa latest vì downstream có thể chạy muộn và nhận một phiên bản khác với phiên bản đã kích hoạt nó.

Sơ đồ luồng tổng quát:

    Producer repository
        | checkout commit
        v
    Build + unit test + provider contract verification
        |
        v
    Publish immutable artifact + contract + metadata
        |
        v
    Emit artifact_published event
        |
        +--------------------+
        |                    |
        v                    v
    Consumer A CI         Consumer B CI
        |                    |
        v                    v
    Pin digest + test     Pin digest + test
        |                    |
        +---------+----------+
                  |
                  v
          Integration status
                  |
                  v
          Release decision

Nếu một producer có nhiều consumer, có thể fan-out sự kiện để mỗi consumer kiểm tra độc lập. Khi release cần tất cả consumer quan trọng đạt, một bước fan-in tổng hợp trạng thái. Nếu một consumer không thuộc phạm vi phát hành hiện tại, chính sách có thể đánh dấu nó là không bắt buộc, nhưng quyết định này cần có lý do và được lưu trong release metadata.

## 7. Chọn mô hình điều phối phù hợp

Có hai mô hình chính, có thể kết hợp trong cùng hệ thống.

### Điều phối tập trung

Một pipeline điều phối biết dependency graph và gọi các pipeline hoặc job theo thứ tự. Mô hình này phù hợp khi một release cần phối hợp nhiều repository, có điều kiện phê duyệt chung hoặc phải bảo đảm một tập dịch vụ được xác minh cùng nhau.

Ưu điểm là nhìn thấy toàn bộ luồng và có một nơi tổng hợp kết quả. Nhược điểm là orchestrator có thể trở thành điểm tập trung quyền hạn, nút thắt hoặc nơi chứa nhiều logic đặc thù. Hãy giữ cấu hình dependency rõ ràng, chia pipeline thành bước có thể tái sử dụng và tránh để orchestrator phải chứa toàn bộ cách build của từng repository.

### Điều phối theo sự kiện

Producer publish artifact hoặc contract rồi phát sự kiện. Consumer đăng ký nhận sự kiện và tự quyết định kiểm tra nào cần chạy. Mô hình này phù hợp khi repository phát hành độc lập và có nhiều consumer không cần chờ nhau.

Ưu điểm là giảm phụ thuộc trực tiếp giữa các pipeline và dễ mở rộng fan-out. Nhược điểm là trạng thái phát hành phân tán, sự kiện có thể đến trễ hoặc lặp, và khó biết khi nào toàn bộ consumer quan trọng đã xác minh xong.

Với mô hình sự kiện, consumer cần xử lý event theo cách idempotent: cùng một event được gửi lại không được tạo ra các lần phát hành hoặc cập nhật trạng thái trùng lặp. Dùng event ID hoặc khóa từ producer, artifact digest và consumer version để nhận diện một lần tích hợp.

### Kết hợp hai mô hình

Một hệ thống thường dùng event để thông báo artifact mới, rồi dùng orchestrator hoặc status aggregator để theo dõi các consumer bắt buộc. Cách kết hợp này giữ quyền tự chủ của repository nhưng vẫn cung cấp một quyết định release tổng thể khi cần.

Không nên để pipeline A chờ B, B chờ C và C lại chờ A. Hãy xác định rõ đâu là bước publish, đâu là bước verify và đâu là cổng release. Mỗi lần kích hoạt phải mang phiên bản cụ thể để có thể hoàn thành độc lập và truy vết.

## 8. Quản lý dependency graph và thứ tự phát hành

Thứ tự build và thứ tự triển khai không phải lúc nào cũng giống nhau. Build có thể thực hiện song song nếu chỉ cần contract đã phát hành. Triển khai có thể cần theo thứ tự nếu một consumer yêu cầu endpoint hoặc schema mới đã tồn tại.

Ví dụ, khi backend thêm một trường response tùy chọn, có thể triển khai backend trước rồi cập nhật frontend sau. Khi backend xóa trường cũ, cần triển khai frontend ngừng sử dụng trường đó trước, xác minh telemetry không còn request cũ rồi mới xóa trường ở backend. Đây là một chuyển đổi nhiều bước, không phải một lần đổi phiên bản đồng thời.

Với database được nhiều service dùng chung, nên áp dụng chiến lược expand-and-contract:

1. Expand: thêm cột hoặc cấu trúc mới theo cách vẫn tương thích với phiên bản ứng dụng cũ.
2. Deploy: phát hành ứng dụng có thể đọc/ghi theo cấu trúc mới trong giai đoạn chuyển tiếp.
3. Migrate: chuyển đổi dữ liệu và xác minh kết quả.
4. Contract: sau khi mọi consumer đã chuyển đổi và không còn truy cập cấu trúc cũ, mới loại bỏ phần cũ.

Dependency graph cần ghi nhận cả ràng buộc phiên bản và thứ tự rollout. Chỉ dùng thứ tự topological của build graph là chưa đủ nếu runtime có yêu cầu tương thích theo giai đoạn.

## 9. Gắn artifact, contract và bằng chứng vào release manifest

Một release manifest tập hợp các thành phần của một lần tích hợp. Nó cho biết hệ thống được tạo từ commit nào, dùng artifact nào, contract nào và kết quả xác minh ra sao.

Ví dụ minh họa:

    release_id: platform-2026.11.18-rc2
    components:
      - repository: payments-api
        commit: 7fa31c2
        artifact: registry.example/payments-api@sha256:abc...
        version: 2.4.1
        contract: payments-openapi@2.4.1
        provider_verification: passed
      - repository: checkout-service
        commit: 18bd902
        artifact: registry.example/checkout-service@sha256:789...
        version: 5.8.0
        consumer_verification: passed
    integration:
      contract_suite: passed
      smoke_test: pending

Manifest cần được tạo từ dữ liệu pipeline thực tế và lưu cùng hồ sơ phát hành. Không điền bằng tay những giá trị không được kiểm chứng. Khi smoke test hoặc phê duyệt hoàn tất, có thể ghi thêm kết quả tương ứng theo cơ chế quản lý release của hệ thống.

Manifest giúp trả lời các câu hỏi:

- Phiên bản nào của mỗi service đang nằm trong release?
- Artifact có đúng digest đã được build và kiểm tra không?
- Contract nào được dùng để xác minh tương thích?
- Consumer nào đã xác minh thành công và consumer nào còn pending hoặc failed?
- Commit và pipeline run nào tạo ra bằng chứng đó?
- Nếu cần rollback, tập artifact trước đó là gì?

Với hệ thống có yêu cầu truy vết cao, có thể bổ sung SBOM, build provenance, chữ ký artifact, kết quả quét lỗ hổng và danh tính workflow đã publish. Những bằng chứng này cần được gắn với digest để không bị tách khỏi nội dung thực tế.

## 10. Bảo vệ quyền truy cập giữa các repository

Pipeline nhiều repository thường phải đọc package, phát hành artifact, tải contract hoặc kích hoạt workflow ở dự án khác. Đây là ranh giới bảo mật cần được thiết kế rõ.

- Cấp quyền tối thiểu cho từng workflow: consumer chỉ cần quyền đọc artifact thì không nên có quyền ghi hoặc xóa package.
- Dùng token ngắn hạn hoặc danh tính workload/OIDC nếu nền tảng hỗ trợ, thay vì lưu một token cá nhân có quyền rộng trong nhiều repository.
- Tách quyền publish của producer khỏi quyền triển khai vào môi trường production.
- Không truyền secret qua event payload, log, artifact công khai hoặc tham số dòng lệnh có thể bị ghi lại.
- Xác minh nguồn gốc artifact và chữ ký trước khi consumer sử dụng trong release nhạy cảm.
- Không để pipeline chạy từ pull request không tin cậy có quyền truy cập secret hoặc credential phát hành.
- Ghi lại repository, workflow identity, artifact digest và thời điểm thực hiện các thao tác publish/consume.

Khi một repository kích hoạt workflow ở repository khác, cần xác thực cả danh tính người gọi và nội dung sự kiện. Không coi tên repository hoặc tên branch trong payload là bằng chứng đáng tin cậy nếu payload có thể bị giả mạo.

## 11. Xử lý thất bại, chạy lại và hủy một lần tích hợp

Trong pipeline phân tán, một consumer có thể thất bại sau khi producer đã publish artifact. Điều này không nhất thiết có nghĩa artifact producer không hợp lệ. Cần phân biệt:

- Producer build hoặc provider verification thất bại: artifact chưa đủ điều kiện phát hành.
- Consumer contract verification thất bại: có khả năng thay đổi phá vỡ hợp đồng hoặc consumer đang dùng contract cũ.
- Consumer build thất bại do lỗi nội bộ: cần xác định lỗi có liên quan dependency mới hay không.
- Hạ tầng downstream không sẵn sàng: có thể chạy lại bước kiểm tra theo chính sách retry có giới hạn.
- Release aggregator chưa nhận đủ kết quả: trạng thái phải là pending hoặc incomplete, không tự suy ra thành công.

Mỗi lần tích hợp cần có correlation ID hoặc release ID ổn định để nối log từ producer tới consumer. Khi retry event, giữ cùng ID của thao tác logic và bảo đảm consumer không tạo release trùng. Nếu một consumer thất bại, hãy giữ lại artifact và metadata để điều tra; không xóa hoặc ghi đè artifact đã publish.

Nếu release bị hủy, ghi lại trạng thái canceled cùng lý do và các thành phần đã triển khai. Việc hủy một pipeline điều phối không tự động đảo ngược những deployment đã hoàn thành. Các hành động rollback phải là bước riêng, có trạng thái và xác minh.

## 12. Rollback khi nhiều dự án đã được triển khai

Rollback trong hệ thống nhiều repository phức tạp hơn rollback một ứng dụng đơn lẻ vì các phiên bản có thể đã thay đổi quan hệ tương thích.

Một release manifest tốt giúp chọn đúng bộ artifact trước đó. Tuy nhiên, trước khi rollback cần xác minh:

1. Phiên bản cũ của từng service còn khả năng giao tiếp với các service hiện tại không?
2. Database schema hoặc event đã được migrate theo cách có thể quay lui không?
3. Artifact cũ còn tồn tại, digest còn xác minh được và cấu hình runtime còn phù hợp không?
4. Việc rollback một service có làm consumer khác mất contract hoặc endpoint đang sử dụng không?
5. Có cần roll forward bằng bản sửa lỗi thay vì quay lui toàn bộ release không?

Nếu thay đổi database là destructive hoặc event mới đã được phát ra, rollback binary đơn thuần có thể không an toàn. Có thể cần một phiên bản tương thích chuyển tiếp, migration bù hoặc roll forward. Chính sách rollback phải dựa trên trạng thái dữ liệu và quan hệ tương thích, không chỉ dựa vào tag phiên bản trước.

Sau khi rollback hoặc roll forward, chạy lại contract test và smoke test trên tập service liên quan. Ghi nhận release ID, digest thực tế đang chạy và kết quả xác minh để lịch sử phát hành phản ánh đúng trạng thái hệ thống.

## 13. Những lỗi phối hợp thường gặp

| Cách làm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Consumer tải artifact bằng tag latest | Có thể nhận nội dung khác với bản đã kiểm thử | Pin version và digest trong manifest |
| Chỉ kiểm thử trong từng repository | Không phát hiện contract bị phá vỡ giữa producer và consumer | Thêm provider verification và contract test liên repository |
| Chia sẻ schema bằng cách copy thủ công | Các bản schema dần lệch nhau | Publish contract có phiên bản và checksum |
| Kích hoạt downstream chỉ bằng tên branch | Pipeline chạy muộn có thể lấy commit khác | Truyền commit, artifact digest và contract version cụ thể |
| Mỗi consumer tự đoán phiên bản producer | Khó tái hiện và khó xác định release đang dùng gì | Dùng dependency pin hoặc release manifest |
| Trigger lẫn nhau không có đồ thị phụ thuộc | Tạo vòng lặp hoặc pipeline chạy vô hạn | Thiết kế DAG, event ID và quy tắc chống lặp |
| Cho mọi workflow dùng token quyền rộng | Tăng phạm vi ảnh hưởng khi credential bị lộ | Dùng quyền tối thiểu và credential ngắn hạn |
| Coi một consumer chưa phản hồi là thành công | Release có thể thiếu bằng chứng tương thích | Giữ trạng thái pending/incomplete cho tới khi đủ điều kiện |
| Rollback từng service mà không kiểm tra contract | Các service còn lại có thể không tương thích | Kiểm tra ma trận phiên bản và trạng thái dữ liệu trước rollback |

## 14. Ví dụ: phát hành thư viện dùng chung và hai consumer

Giả sử repository `pricing-core` phát hành thư viện Java được dùng bởi `checkout-service` và `invoice-service`. Producer tạo package `pricing-core:3.2.0` cùng metadata và contract mô tả public API. Hai consumer có dependency được pin theo phiên bản.

Khi producer thay đổi:

1. Pipeline producer build package từ commit cụ thể, chạy unit test và kiểm tra public API.
2. Pipeline publish package bất biến cùng checksum và metadata nguồn.
3. Sự kiện phát hành mang version, checksum, commit và pipeline run được gửi tới hai consumer.
4. Mỗi consumer tạo một nhánh hoặc pull request cập nhật dependency, sau đó chạy compile, unit test và contract/integration test liên quan.
5. Trạng thái của hai consumer được tổng hợp. Nếu checkout-service đạt nhưng invoice-service thất bại, release tổng thể chỉ được phép tiếp tục nếu chính sách xác định invoice-service không thuộc phạm vi hoặc có phương án tương thích đã được phê duyệt.
6. Khi các điều kiện phát hành đạt, release manifest ghi lại package digest và phiên bản của cả ba repository.

Nếu producer phát hiện lỗi sau publish, nhóm có thể phát hành patch version mới và gửi sự kiện mới. Không ghi đè package 3.2.0 vì consumer đã có thể tải và kiểm thử đúng checksum cũ. Lịch sử cần giữ cả hai artifact để có thể tái hiện các lần tích hợp trước.

## 15. Checklist thiết kế pipeline nhiều repository

Trước khi đưa luồng phối hợp vào sử dụng, hãy xác nhận:

- [ ] Đã xác định producer, consumer và loại dependency giữa từng repository.
- [ ] Dependency graph không có chu trình chưa được xử lý và có thứ tự build/verify/release rõ ràng.
- [ ] Artifact được build một lần, publish bất biến và có version cùng digest.
- [ ] Contract được phiên bản hóa, lưu cùng metadata và liên kết với artifact tương ứng.
- [ ] Có provider verification và contract test cho các consumer cần hỗ trợ.
- [ ] Downstream trigger mang commit, artifact digest, contract version và pipeline run cụ thể.
- [ ] Event có ID ổn định và consumer xử lý lặp an toàn.
- [ ] Release aggregator phân biệt rõ passed, failed, pending, canceled và skipped.
- [ ] Release manifest ghi lại phiên bản, digest, contract và bằng chứng xác minh của từng thành phần.
- [ ] Quyền truy cập liên repository tuân theo nguyên tắc tối thiểu; secret không bị truyền qua event hoặc log.
- [ ] Thứ tự triển khai và chiến lược chuyển đổi dữ liệu giữ tương thích trong giai đoạn chuyển tiếp.
- [ ] Rollback được đánh giá theo ma trận tương thích, trạng thái dữ liệu và artifact còn khả dụng.
- [ ] Có correlation ID để truy vết từ commit producer tới consumer, release và môi trường triển khai.

Phối hợp nhiều repository hiệu quả khi mỗi dự án có thể build và phát hành độc lập, nhưng mọi lần tích hợp đều dùng artifact bất biến, contract có phiên bản và bằng chứng kiểm tra rõ ràng. Pipeline khi đó có thể phản hồi nhanh trước thay đổi, phát hiện sớm sự không tương thích và đưa ra quyết định phát hành dựa trên đúng bộ thành phần đã được xác minh.
