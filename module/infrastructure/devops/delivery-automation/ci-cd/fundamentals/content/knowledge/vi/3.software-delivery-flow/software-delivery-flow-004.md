# Nhận diện điểm bàn giao và thao tác thủ công dễ sai

Một quy trình CI/CD có thể tự động hóa nhiều lệnh nhưng vẫn dễ phát hành sai nếu thông tin bị mất hoặc bị thay đổi khi chuyển từ người này, hệ thống này hay giai đoạn này sang bên tiếp theo. Ví dụ, nhóm build đúng commit nhưng người vận hành chọn nhầm image khi triển khai; người duyệt xem báo cáo của một phiên bản nhưng pipeline lại phát hành phiên bản khác; hoặc nhóm trực nhận được thông báo triển khai thành công nhưng không biết cần kiểm tra dashboard và rollback theo cách nào.

Những ranh giới chuyển giao như vậy được gọi là **điểm bàn giao**. Đây là nơi trách nhiệm, quyền quyết định hoặc dữ liệu đi từ một bên sang bên khác. Nhận diện đúng điểm bàn giao giúp nhóm biết thông tin nào phải được chuyển tiếp, ai xác nhận đã nhận đủ và điều kiện nào cho phép công việc tiếp tục. Mục tiêu là giảm lỗi do chọn nhầm, sao chép sai, bỏ sót bước hoặc thao tác trong trạng thái không còn mới.

## 1. Điểm bàn giao là gì?

Một điểm bàn giao xuất hiện khi một công việc hoặc kết quả rời khỏi phạm vi kiểm soát của bên tạo ra và được bên khác tiếp nhận. Bên nhận có thể là:

- Một hệ thống khác, chẳng hạn CI chuyển artifact cho registry.
- Một giai đoạn khác trong pipeline, chẳng hạn build chuyển kết quả cho bước kiểm thử.
- Một người hoặc nhóm khác, chẳng hạn nhóm phát triển chuyển yêu cầu phát hành cho người duyệt.
- Một môi trường khác, chẳng hạn staging chuyển cùng một artifact sang production.
- Nhóm vận hành tiếp nhận dịch vụ sau khi triển khai.

Điểm bàn giao không chỉ là thời điểm gửi một file hoặc nhấn nút. Nó còn bao gồm việc chuyển ngữ cảnh: phiên bản nào đang được xử lý, kết quả nào đã được xác minh, rủi ro nào còn tồn tại, quyền nào được sử dụng và ai chịu trách nhiệm cho bước tiếp theo.

Một lần bàn giao đáng tin cậy cần trả lời được các câu hỏi:

1. **Ai gửi và ai nhận?** Phải xác định được chủ thể chịu trách nhiệm ở hai phía.
2. **Bàn giao việc gì?** Nêu rõ artifact, yêu cầu, cấu hình, thay đổi hoặc quyết định được chuyển.
3. **Định danh nào được dùng?** Ví dụ commit SHA, pipeline run ID, artifact digest, deployment revision hoặc mã yêu cầu thay đổi.
4. **Bằng chứng nào đi kèm?** Báo cáo test, kết quả quét bảo mật, log, phê duyệt hoặc kết quả xác minh.
5. **Bên nhận xác nhận ra sao?** Có thể kiểm tra dữ liệu, chấp nhận, từ chối hoặc yêu cầu bổ sung.
6. **Nếu có lỗi thì xử lý thế nào?** Xác định nơi dừng, cách thử lại, người cần thông báo và cách khôi phục.

Nếu một trong các câu trả lời này chỉ tồn tại trong trí nhớ hoặc một tin nhắn rời rạc, điểm bàn giao đó phụ thuộc quá nhiều vào con người.

## 2. Hợp đồng bàn giao

Có thể mô tả mỗi điểm bàn giao bằng một hợp đồng ngắn. Hợp đồng này làm rõ trách nhiệm và dữ liệu mà bên nhận được phép tin cậy.

| Thành phần | Nội dung cần xác định | Ví dụ |
|---|---|---|
| Bên gửi | Hệ thống hoặc vai trò tạo kết quả | Job build trong pipeline |
| Bên nhận | Hệ thống hoặc vai trò tiếp nhận | Artifact registry |
| Sự kiện bàn giao | Điều gì kích hoạt việc chuyển tiếp | Build hoàn tất và gate đạt |
| Định danh | Khóa duy nhất để nhận biết đúng đối tượng | Commit SHA và image digest |
| Payload | Dữ liệu hoặc sản phẩm được chuyển | Image, metadata, báo cáo |
| Điều kiện chấp nhận | Bên nhận kiểm tra điều gì | Digest khớp, chữ ký hợp lệ |
| Xác nhận | Cách ghi nhận đã nhận thành công | Registry trả về digest đã lưu |
| Xử lý lỗi | Cách từ chối, thử lại hoặc chuyển cấp | Dừng promotion, giữ log |

Ví dụ dưới đây chỉ là mô hình khái niệm để thể hiện hợp đồng, không phải cú pháp bắt buộc của một nền tảng CI/CD:

```yaml
handoff:
  name: build-to-registry
  sender: build-job
  receiver: container-registry
  trigger: build-and-scan-passed
  identity:
    commit: "COMMIT_SHA"
    artifact_digest: "IMAGE_DIGEST"
  evidence:
    - build_metadata
    - vulnerability_scan_report
  acceptance:
    - artifact_upload_succeeded
    - stored_digest_matches
  on_reject: stop_release
```

Hợp đồng nên được thực thi bằng kiểm tra tự động ở nơi có thể. Chẳng hạn, registry có thể xác nhận digest sau khi upload; bước deploy có thể từ chối nếu manifest không có digest; cổng production có thể yêu cầu phê duyệt gắn với đúng digest. Với quyết định cần con người, hệ thống vẫn phải ghi nhận danh tính, thời điểm, đối tượng được duyệt và bằng chứng đã xem.

## 3. Các điểm bàn giao thường gặp trong luồng CI/CD

### 3.1. Từ Git sang pipeline

Điểm bàn giao bắt đầu khi sự kiện Git kích hoạt một lần chạy CI/CD. Thông tin chuyển tiếp gồm repository, loại sự kiện, nhánh hoặc tag, commit SHA, pull request và danh tính tác nhân.

Các lỗi dễ gặp:

- Chạy pipeline trên nhánh mặc định trong khi yêu cầu phát hành nhắm đến nhánh release.
- Dùng tên nhánh làm định danh và vô tình lấy commit mới hơn so với commit đã được kiểm tra.
- Nhập tay commit SHA hoặc tag bị thiếu ký tự.
- Chạy lại một pipeline cũ mà không kiểm tra source đã thay đổi hay chưa.
- Cho mã từ pull request không tin cậy truy cập secret hoặc quyền publish.

**Cách kiểm soát:** pipeline phải ghi lại commit SHA ngay khi nhận sự kiện và truyền định danh này xuyên suốt các stage. Khi người dùng chọn chạy thủ công, giao diện nên hiển thị repository, ref, commit và môi trường mục tiêu để họ xác nhận. Quyền của job chạy trên mã chưa tin cậy cần bị giới hạn; không cấp secret production hoặc quyền ghi registry phát hành chỉ vì pipeline được kích hoạt.

### 3.2. Giữa các stage trong pipeline

Một stage thường tạo ra dữ liệu để stage tiếp theo sử dụng. Đây là điểm bàn giao giữa các job hoặc runner, ngay cả khi tất cả đều thuộc cùng một file pipeline.

Các lỗi dễ gặp:

- Job sau giả định file do job trước tạo vẫn tồn tại trên runner khác.
- Truyền dữ liệu qua biến môi trường không được khai báo hoặc bị ghi đè.
- Chỉ kiểm tra exit code mà bỏ qua báo cáo test hoặc metadata cần thiết.
- Dùng file trong workspace còn sót lại từ lần chạy trước.
- Stage sau tự lấy source mới nhất thay vì dùng snapshot đã được kiểm tra.

**Cách kiểm soát:** khai báo output và dependency tường minh; lưu artifact trung gian theo mã lần chạy; xác minh file tồn tại, định dạng và nguồn gốc trước khi sử dụng. Mỗi job cần nhận đúng input đã được khai báo. Không dựa vào trạng thái ngẫu nhiên của workspace hoặc cache. Nếu một stage không tạo được output bắt buộc, pipeline phải dừng tại điểm đó và chỉ rõ output nào thiếu.

### 3.3. Từ build sang artifact registry

Sau build, sản phẩm cần được đóng gói và chuyển vào nơi lưu trữ có thể truy cập cho các môi trường tiếp theo. Artifact có thể là binary, package, container image hoặc bundle triển khai.

Các lỗi dễ gặp:

- Copy thủ công tên image hoặc version tag giữa các công cụ.
- Gắn lại tag cho một image khác mà không cập nhật báo cáo.
- Đẩy artifact vào nhầm repository hoặc project.
- Chỉ lưu tag dễ đọc như `latest`, không lưu digest.
- Đánh dấu build thành công dù upload chưa hoàn tất hoặc artifact không tải lại được.

**Cách kiểm soát:** để pipeline publish artifact bằng danh tính máy có quyền tối thiểu; lấy digest từ kết quả registry; tải lại hoặc kiểm tra artifact theo digest; lưu metadata build, commit SHA và báo cáo scan cùng định danh artifact. Tag như `2.4.0` giúp con người tra cứu, còn digest xác định nội dung chính xác. Không dùng việc nhìn tên tag để thay cho xác minh nội dung.

### 3.4. Từ artifact sang môi trường triển khai

Đây là điểm bàn giao có rủi ro cao vì một lựa chọn sai có thể ảnh hưởng trực tiếp đến người dùng. Bên nhận gồm nền tảng triển khai, cluster, namespace, tài khoản cloud hoặc máy chủ đích.

Các lỗi dễ gặp:

- Chọn nhầm production thay vì staging, hoặc ngược lại.
- Chọn sai cluster, namespace, region hoặc tài khoản cloud.
- Dán nhầm image tag từ ticket hoặc chat.
- Triển khai artifact chưa qua staging.
- Dùng cấu hình của môi trường khác hoặc secret sai phạm vi.
- Thay đổi thủ công trên máy chủ khiến môi trường lệch khỏi cấu hình được quản lý.

**Cách kiểm soát:** xác định môi trường bằng cấu hình có kiểm soát và bảo vệ môi trường production bằng quyền riêng. Hiển thị rõ dịch vụ, môi trường, artifact digest và phạm vi ảnh hưởng trước khi cho phép thao tác thủ công. Job deploy nên nhận digest đã được phê duyệt thay vì nhận chuỗi tag do người vận hành nhập. Dùng tài khoản và credential tách biệt theo môi trường; không tái sử dụng quyền production trong job test.

### 3.5. Từ kiểm thử sang phê duyệt phát hành

Kết quả kiểm thử và quét bảo mật được chuyển thành bằng chứng để người có thẩm quyền quyết định phát hành.

Các lỗi dễ gặp:

- Người duyệt chỉ thấy trạng thái xanh mà không biết trạng thái đó thuộc commit nào.
- Báo cáo đã cũ nhưng vẫn được dùng để phê duyệt phiên bản mới.
- Người duyệt nhầm ticket hoặc nhầm lần chạy pipeline.
- Phê duyệt qua tin nhắn nhưng không được ghi vào hệ thống phát hành.
- Người tạo thay đổi tự phê duyệt một thay đổi có rủi ro cao dù quy trình yêu cầu người độc lập.

**Cách kiểm soát:** trang phê duyệt phải liên kết đến commit SHA, pipeline run ID, artifact digest, kết quả kiểm thử và môi trường đích. Quyết định phải được ghi nhận trong hệ thống với người duyệt, thời điểm và phạm vi phê duyệt. Phê duyệt cần hết hiệu lực hoặc phải được xem xét lại nếu artifact, cấu hình quan trọng hay phạm vi phát hành thay đổi. Áp dụng nguyên tắc hai người kiểm tra cho thao tác có tác động lớn khi chính sách tổ chức yêu cầu; không biến mọi thao tác nhỏ thành một vòng chờ phê duyệt không cần thiết.

### 3.6. Từ triển khai sang vận hành

Sau khi rollout, trách nhiệm chuyển dần từ nhóm phát hành sang nhóm vận hành hoặc người trực dịch vụ. Một thông báo “deploy thành công” chưa đủ để hoàn tất bàn giao.

Các thông tin cần chuyển:

- Dịch vụ, môi trường, artifact digest và deployment revision.
- Thời điểm triển khai, người hoặc hệ thống khởi tạo.
- Thay đổi cấu hình, feature flag và migration đã thực hiện.
- Các kiểm tra sau triển khai và kết quả quan sát ban đầu.
- Dashboard, log, trace, runbook và đầu mối chịu trách nhiệm.
- Phiên bản ổn định trước đó và cách rollback hoặc roll-forward.

Lỗi thường gặp là nhóm triển khai biết đã đổi phiên bản nhưng người trực không biết metric nào cần quan sát, tính năng nào đang bật hoặc migration nào có thể ảnh hưởng dữ liệu. Hãy tạo release record hoặc thông báo vận hành có cấu trúc, liên kết đến bằng chứng và hướng dẫn khôi phục. Không yêu cầu người trực tự tìm các thông tin quan trọng trong nhiều cuộc trò chuyện.

## 4. Những kiểu sai sót thường xuất hiện khi thao tác thủ công

Thao tác thủ công không phải lúc nào cũng sai. Con người cần tham gia vào các quyết định về rủi ro, phạm vi ảnh hưởng và thời điểm phát hành. Vấn đề xuất hiện khi một thao tác lặp lại đòi hỏi trí nhớ, nhập liệu hoặc chọn lựa dễ nhầm mà không có xác minh.

| Kiểu sai sót | Biểu hiện | Hậu quả có thể xảy ra |
|---|---|---|
| Chọn nhầm (selection) | Chọn sai nhánh, artifact, cluster hoặc môi trường | Phát hành sai phiên bản hoặc sai nơi |
| Sao chép/nhập sai (transcription) | Gõ thiếu ký tự digest, version, URL hoặc tham số | Không tìm thấy artifact hoặc dùng nhầm tài nguyên |
| Bỏ sót (omission) | Quên chạy migration, smoke test hoặc cập nhật release record | Dịch vụ lỗi hoặc thiếu dấu vết |
| Sai thứ tự (sequencing) | Deploy trước khi phê duyệt hoặc chạy migration không đúng thứ tự | Trạng thái hệ thống không tương thích |
| Dùng ngữ cảnh cũ (stale context) | Dựa vào báo cáo, ticket hoặc hướng dẫn của lần phát hành trước | Quyết định dựa trên bằng chứng không còn đúng |
| Nhầm quyền (authorization) | Dùng tài khoản cá nhân hoặc credential quá rộng | Khó truy vết, tăng phạm vi thiệt hại |
| Thử lại trùng lặp (duplicate action) | Nhấn deploy nhiều lần khi chưa biết lần trước đã hoàn tất chưa | Tạo tài nguyên hoặc thay đổi lặp |
| Xác minh hình thức | Chỉ nhìn trạng thái job xanh mà không kiểm tra dịch vụ | Sự cố bị phát hiện muộn |

### 4.1. Chọn nhầm đối tượng

Con người thường phải chọn từ danh sách dài: repository, branch, tag, artifact, cluster, namespace và environment. Tên gần giống nhau như `api-prod`, `api-preprod` và `api-preview` làm tăng khả năng chọn nhầm.

Giảm rủi ro bằng cách:

- Dùng danh sách lựa chọn có cấu trúc thay cho ô nhập tự do nếu tập giá trị đã biết.
- Hiển thị tên đầy đủ cùng tài khoản, region và môi trường.
- Tự động lấy artifact từ pipeline run đã chọn.
- Yêu cầu xác nhận bổ sung cho thao tác có tác động lớn.
- Kiểm tra mục tiêu ở phía server hoặc job deploy trước khi thực hiện.

Một hộp thoại xác nhận chỉ hữu ích khi nó hiển thị thông tin giúp phát hiện sai sót. Câu hỏi chung chung “Bạn có chắc không?” không giúp người vận hành nhận ra họ đang triển khai sai cluster.

### 4.2. Sao chép dữ liệu và nhập tham số

Sao chép digest, version, endpoint hoặc biến cấu hình qua nhiều cửa sổ tạo ra lỗi cắt thiếu, dán nhầm hoặc giữ lại giá trị cũ. Càng nhiều lần chuyển tay, xác suất sai càng tăng.

Ưu tiên truyền dữ liệu qua output có cấu trúc, API hoặc artifact metadata. Nếu phải nhập, hãy kiểm tra định dạng, hiển thị lại giá trị đã chuẩn hóa và đối chiếu với nguồn. Với định danh dài như SHA-256 digest, không yêu cầu người vận hành tự gõ. Hãy chọn artifact từ danh sách hoặc lấy trực tiếp từ lần chạy đã được phê duyệt.

### 4.3. Bỏ sót và sai thứ tự

Một checklist trên giấy có thể nhắc người vận hành nhưng vẫn có thể bị đánh dấu hoàn thành khi bước chưa thực sự chạy. Những bước quan trọng như migration, tắt/bật feature flag, smoke test và cập nhật thông tin vận hành nên được liên kết với bằng chứng.

Với bước có thể tự động hóa, để pipeline thực thi và lưu kết quả. Với bước bắt buộc do con người thực hiện, yêu cầu ghi nhận kết quả có thể kiểm tra được, ví dụ mã thay đổi, người thực hiện và thời điểm. Các phụ thuộc thứ tự nên được thể hiện trong pipeline hoặc runbook theo trình tự rõ ràng.

### 4.4. Thử lại khi chưa biết trạng thái

Khi giao diện bị treo hoặc không có phản hồi, người dùng có thể nhấn lại nút deploy hoặc chạy lại job. Nếu thao tác trước đã được hệ thống tiếp nhận, lần chạy thứ hai có thể gây ra thay đổi trùng lặp.

Trước khi thử lại, cần biết trạng thái của lần chạy trước bằng run ID hoặc deployment revision. Thiết kế job có thể lặp an toàn (idempotent) khi phù hợp; dùng khóa chống chạy đồng thời hoặc cơ chế nhận diện yêu cầu trùng. Đối với thao tác không thể lặp an toàn, hãy kiểm tra trạng thái thực tế và yêu cầu xác nhận có thông tin trước khi tiếp tục.

### 4.5. Dùng bí mật và tài khoản sai cách

Một cách làm tiện nhưng nguy hiểm là gửi token qua chat, lưu mật khẩu trong file tạm, dùng chung tài khoản quản trị hoặc đưa secret vào dòng lệnh để copy/paste. Những cách này làm lộ thông tin và khiến log khó xác định ai đã thực hiện hành động.

Cấp credential từ secret manager hoặc cơ chế định danh workload; ưu tiên credential ngắn hạn; giới hạn quyền theo job và môi trường. Không yêu cầu người vận hành dán secret vào biểu mẫu pipeline nếu nền tảng có cơ chế cấp phát an toàn. Nhật ký cần ghi danh tính và hành động nhưng không ghi giá trị bí mật.

## 5. Phân biệt quyết định cần con người với thao tác nên tự động hóa

Không nên loại bỏ mọi bước có con người tham gia. Có những quyết định cần cân nhắc tác động kinh doanh hoặc chấp nhận rủi ro, chẳng hạn thời điểm phát hành, ngoại lệ chính sách hoặc việc chuyển traffic trong sự cố. Ngược lại, sao chép digest, đổi tag, tải file và kiểm tra một điều kiện có thể biểu diễn bằng mã thường nên được tự động hóa.

| Loại công việc | Cách xử lý phù hợp | Ví dụ |
|---|---|---|
| Quyết định về rủi ro và ưu tiên | Con người quyết định, hệ thống lưu bằng chứng | Chấp nhận phát hành trong cửa sổ bảo trì |
| Kiểm tra điều kiện xác định được | Tự động hóa thành gate | Test pass, digest khớp, scan đạt ngưỡng |
| Chuyển dữ liệu giữa hệ thống | Tự động truyền qua giao diện có cấu trúc | Promote artifact theo digest |
| Ngoại lệ khẩn cấp | Con người thực hiện theo quy trình break-glass có kiểm soát | Khôi phục dịch vụ khi pipeline không khả dụng |
| Công việc lặp có quy tắc ổn định | Tự động hóa và ghi log | Deploy staging, smoke test, tạo release record |

Một bước phê duyệt có giá trị khi người duyệt có đủ thông tin và quyền hạn để đưa ra quyết định. Nếu người duyệt chỉ bấm nút để chuyển pipeline mà không xem bằng chứng, bước đó trở thành thủ tục hình thức. Hãy thiết kế màn hình phê duyệt tập trung vào thay đổi, artifact, môi trường, kiểm tra đã đạt, rủi ro còn lại và phương án khôi phục.

## 6. Biện pháp giảm lỗi tại điểm bàn giao

### 6.1. Dùng định danh bất biến

Truyền commit SHA, artifact digest và deployment revision qua các bước. Tránh dựa vào tên nhánh, tag có thể thay đổi hoặc tên file chung chung như `build.zip`. Khi một định danh thay đổi, hệ thống cần tạo bản ghi mới và làm rõ bằng chứng nào còn hiệu lực.

### 6.2. Xác thực cả phía gửi và phía nhận

Bên gửi phải chứng minh output được tạo từ nguồn nào. Bên nhận phải xác minh output đáp ứng hợp đồng trước khi sử dụng. Ví dụ, job build ghi metadata về commit; registry trả về digest đã lưu; job deploy kiểm tra digest có nằm trong danh sách artifact được phép phát hành.

### 6.3. Đưa chính sách vào mã

Các quy tắc như nhánh nào được phát hành, mức độ lỗ hổng nào chặn release, môi trường nào cần phê duyệt và ai được deploy nên được thể hiện bằng cấu hình hoặc policy có quản lý phiên bản. Nhờ đó, thay đổi chính sách có thể được review và truy vết như thay đổi mã nguồn.

### 6.4. Giới hạn quyền và tách trách nhiệm

Tách quyền build, publish và deploy khi mức độ rủi ro yêu cầu. Job test không cần quyền ghi production; người có quyền duyệt không nhất thiết phải có quyền sửa artifact; tài khoản triển khai chỉ được tác động đến dịch vụ và môi trường được giao. Với thao tác khẩn cấp, dùng cơ chế break-glass có thời hạn, ghi lý do và rà soát sau sự kiện.

### 6.5. Ghi nhận xác nhận và bằng chứng

Mỗi lần bàn giao cần có trạng thái rõ ràng: pending, accepted hoặc rejected. Lưu bên gửi, bên nhận, thời điểm, định danh đối tượng, kết quả kiểm tra và lý do từ chối. Log nên cho phép truy ngược từ production deployment về pipeline run, artifact, báo cáo và commit.

### 6.6. Làm cho thao tác có thể lặp an toàn

Thiết kế API và job để cùng một yêu cầu không tạo ra tác động phụ trùng lặp khi được gửi lại. Có thể dùng idempotency key, khóa theo môi trường/dịch vụ, kiểm tra trạng thái trước khi thay đổi hoặc giới hạn concurrency. Nếu không thể bảo đảm idempotency, phải hiển thị trạng thái lần chạy trước để người vận hành quyết định đúng.

### 6.7. Cung cấp đường xử lý ngoại lệ

Không phải lúc nào pipeline cũng hoạt động. Runbook cần nêu cách xác định trạng thái hiện tại, ai có quyền can thiệp, lệnh hoặc thao tác nào được phép, bằng chứng cần lưu và cách đưa hệ thống trở lại quy trình bình thường. Sau khi dùng đường khẩn cấp, cần đối chiếu trạng thái thực tế với cấu hình được quản lý và cập nhật release record.

## 7. Ví dụ: phát hành nhầm artifact do bàn giao thủ công

Giả sử phiên bản API `2.8.1` đã được kiểm thử trên staging. Người vận hành mở giao diện production, tìm image theo tag và chọn `api:2.8.0` do hai phiên bản nằm cạnh nhau. Job deploy thành công vì image đó tồn tại và hợp lệ về định dạng, nhưng người dùng nhận phiên bản cũ.

Lỗi này xảy ra tại điểm bàn giao từ quyết định phát hành sang thao tác triển khai. Pipeline chỉ kiểm tra image có thể tải được; nó không xác minh image có phải artifact đã được phê duyệt hay không.

Một luồng được kiểm soát tốt hơn sẽ thực hiện như sau:

1. Pipeline build image từ commit đã xác định và ghi nhận pipeline run ID.
2. Artifact được publish; registry trả về digest và metadata được lưu cùng báo cáo kiểm thử.
3. Staging được triển khai bằng digest. Kết quả kiểm tra gắn với deployment revision và digest đó.
4. Người duyệt xem đúng release record, bao gồm commit, digest, báo cáo và môi trường production dự kiến.
5. Khi phê duyệt, hệ thống lưu quyết định gắn với digest cụ thể.
6. Job production nhận digest đã được phê duyệt từ release record. Người vận hành chỉ chọn yêu cầu phát hành, không phải gõ lại tag.
7. Sau deploy, hệ thống xác minh deployment revision đang chạy sử dụng đúng digest đã duyệt và chạy smoke test.

Nếu digest trong yêu cầu deploy không khớp digest được duyệt, gate phải từ chối. Như vậy, thao tác chọn nhầm không thể âm thầm chuyển thành một lần phát hành hợp lệ.

## 8. Khi nào cần dừng và yêu cầu xác nhận?

Không phải mọi sai khác đều cần con người phê duyệt. Tuy nhiên, pipeline nên dừng khi không thể chứng minh tính đúng đắn của một điểm bàn giao quan trọng. Các tình huống điển hình gồm:

- Commit SHA hoặc artifact digest không khớp với bằng chứng trước đó.
- Không xác định được môi trường đích hoặc danh tính triển khai.
- Báo cáo kiểm thử/quét bắt buộc không tồn tại, đã hết hiệu lực hoặc thuộc lần chạy khác.
- Quyết định phê duyệt không gắn với artifact và phạm vi phát hành hiện tại.
- Một lần deploy trước chưa rõ trạng thái nhưng có yêu cầu chạy lại.
- Phát hiện drift hoặc thay đổi ngoài quy trình trên môi trường production.
- Cần dùng quyền khẩn cấp hoặc bỏ qua một gate đã được bảo vệ.

Khi dừng, thông báo phải nói rõ điều kiện nào không đạt, định danh nào đang được so sánh, bằng chứng nào thiếu và ai có thể xử lý. Tránh thông báo chung chung như “Deployment failed” khiến người vận hành phải tự dò lại toàn bộ pipeline.

## 9. Checklist rà soát điểm bàn giao

Dùng checklist sau khi thiết kế pipeline mới hoặc rà soát quy trình phát hành đang vận hành:

- [ ] Đã liệt kê các ranh giới giữa hệ thống, stage, nhóm và môi trường.
- [ ] Mỗi điểm có bên gửi, bên nhận và người chịu trách nhiệm rõ ràng.
- [ ] Dữ liệu chuyển giao có schema hoặc định dạng được xác định.
- [ ] Commit SHA, artifact digest và deployment revision được liên kết xuyên suốt.
- [ ] Bên nhận xác minh nguồn gốc và điều kiện chấp nhận trước khi sử dụng.
- [ ] Không phải gõ lại hoặc sao chép thủ công định danh artifact quan trọng.
- [ ] Phê duyệt gắn với đúng artifact, môi trường và phạm vi thay đổi.
- [ ] Quyền được giới hạn theo job, người dùng và môi trường.
- [ ] Thao tác retry có thể nhận diện trạng thái trước và tránh tác động trùng.
- [ ] Các bước thủ công có bằng chứng, người thực hiện và thời điểm.
- [ ] Nhóm vận hành nhận được release record, dashboard, runbook và cách khôi phục.
- [ ] Đường xử lý ngoại lệ và break-glass có kiểm soát, có rà soát sau sử dụng.

Khi rà soát, hãy ưu tiên những điểm vừa có tác động lớn vừa phụ thuộc vào thao tác tay: chọn artifact production, đổi cấu hình, cấp secret, chạy migration, phê duyệt và rollback. Một lỗi ở các điểm này thường ảnh hưởng rộng hơn lỗi trong một bước kiểm tra nội bộ.

## 10. Bài tập tình huống

Một nhóm phát hành dịch vụ theo quy trình: developer tạo tag, CI build image, tester xác minh trên staging, release manager phê duyệt, operator triển khai production và nhóm vận hành theo dõi.

Trong một lần phát hành, tester xác nhận staging đạt. Sau đó developer cập nhật tag để sửa một lỗi nhỏ nhưng không tạo lại báo cáo test. Release manager vẫn phê duyệt theo thông báo cũ. Operator triển khai tag hiện tại lên production. Dịch vụ gặp lỗi vì image mới chưa qua kiểm thử.

Hãy xác định:

1. Có những điểm bàn giao nào trong tình huống?
2. Định danh hoặc bằng chứng nào đã bị mất liên kết?
3. Vì sao tag có thể thay đổi làm cho phê duyệt cũ không còn đáng tin?
4. Hệ thống cần kiểm tra điều gì trước khi cho phép production deploy?
5. Nếu phát hiện lỗi sau triển khai, nhóm cần lưu thông tin nào để rollback hoặc roll-forward?

Một phương án tốt là gắn test report và approval với artifact digest bất biến. Khi tag được cập nhật và tạo ra digest mới, kết quả test và phê duyệt cũ không tự động áp dụng cho digest mới. Pipeline yêu cầu chạy lại các kiểm tra bắt buộc và phê duyệt lại theo chính sách. Bản ghi phát hành lưu cả digest mới, commit nguồn, run ID và deployment revision để nhóm vận hành xử lý nếu có sự cố.

## 11. Kết luận

Điểm bàn giao là nơi một thay đổi, sản phẩm hoặc quyết định chuyển từ bên tạo sang bên tiếp nhận. Rủi ro thường tăng khi người thực hiện phải nhớ ngữ cảnh, chọn từ các giá trị gần giống nhau, sao chép định danh, nhập secret hoặc lặp lại thao tác mà không biết trạng thái trước đó.

Một quy trình CI/CD vững chắc làm rõ hợp đồng bàn giao, truyền định danh bất biến, xác minh ở cả hai phía và lưu bằng chứng. Con người tập trung vào quyết định cần đánh giá; các bước truyền dữ liệu, kiểm tra điều kiện và thao tác lặp được tự động hóa. Khi có ngoại lệ, nhóm có thể dừng đúng chỗ, biết ai chịu trách nhiệm và khôi phục dựa trên thông tin đã được ghi nhận.

