# Tích hợp liên tục (Continuous Integration): mục tiêu và cách làm

Khi nhiều người cùng phát triển một sản phẩm, rủi ro lớn thường xuất hiện ở thời điểm ghép công việc: một thay đổi hoạt động trên máy của người viết nhưng làm hỏng phần khác, hai nhánh phát triển đi quá xa nhau, hoặc lỗi chỉ được phát hiện khi chuẩn bị phát hành. Tích hợp liên tục (Continuous Integration, viết tắt là CI) giải quyết nhóm vấn đề này bằng một kỷ luật đơn giản: đưa thay đổi vào dòng phát triển chung thường xuyên và tự động kiểm tra từng thay đổi ngay sau khi nó được gửi lên hệ thống quản lý mã nguồn.

CI có hiệu quả khi cả quy trình phát triển và hệ thống tự động cùng hỗ trợ việc tích hợp nhỏ, thường xuyên, có phản hồi nhanh. Một pipeline chạy thành công là bằng chứng rằng một phiên bản mã nguồn cụ thể đã vượt qua các kiểm tra được cấu hình tại thời điểm chạy; đó là tín hiệu chất lượng hữu ích, nhưng không phải lời bảo đảm tuyệt đối rằng phần mềm không còn lỗi.

## 1. CI là gì?

CI là thực hành để các thành viên tích hợp thay đổi mã nguồn vào nhánh chung nhiều lần trong ngày hoặc theo nhịp ngắn phù hợp với nhóm. Mỗi lần đẩy mã nguồn hoặc tạo/cập nhật Pull Request (PR), hệ thống CI lấy đúng phiên bản commit, dựng môi trường, biên dịch, chạy kiểm thử và thực hiện các bước kiểm tra đã định nghĩa. Kết quả được trả về gắn với commit hoặc PR đó.

Ba thành phần tạo nên một quy trình CI hữu ích:

- **Tích hợp thường xuyên:** thay đổi có phạm vi nhỏ, được đưa về nhánh chung sớm để giảm khoảng cách giữa các nhánh.
- **Tự động hóa kiểm tra:** các bước build, test và phân tích được chạy nhất quán, không phụ thuộc vào việc một cá nhân nhớ thao tác thủ công.
- **Phản hồi có thể hành động:** khi một bước thất bại, người thực hiện biết commit nào gây ra lỗi, bước nào hỏng và có log đủ rõ để xử lý.

Chỉ có máy chủ build chưa đủ để tạo thành CI. Nếu nhóm giữ các nhánh tính năng trong nhiều tuần rồi mới ghép lại, hoặc chỉ chạy build định kỳ vào ban đêm, nhóm vẫn đang tích lũy rủi ro tích hợp. CI là một cách làm xuyên suốt, trong đó tự động hóa là công cụ hỗ trợ.

### Phân biệt CI, Continuous Delivery và Continuous Deployment

Ba khái niệm thường xuất hiện cùng nhau nhưng mô tả các mức độ khác nhau:

| Khái niệm | Trọng tâm | Kết quả mong muốn |
|---|---|---|
| Continuous Integration (CI) | Tích hợp và xác minh thay đổi thường xuyên | Mỗi thay đổi được kiểm tra nhanh; nhánh chung luôn ở trạng thái có thể tiếp tục phát triển |
| Continuous Delivery | Tự động hóa các bước sau CI để chuẩn bị phát hành | Có thể đưa phiên bản đã kiểm tra tới môi trường production theo một quyết định phát hành có kiểm soát |
| Continuous Deployment | Tự động triển khai mọi thay đổi đã vượt qua các cổng chất lượng | Thay đổi đủ điều kiện được đưa lên production mà không cần thao tác phê duyệt thủ công cho từng lần |

CI tạo nền móng cho hai thực hành còn lại. Một nhóm có thể áp dụng CI tốt mà vẫn triển khai production theo lịch hoặc cần phê duyệt. Việc tự động triển khai liên tục chỉ phù hợp khi năng lực kiểm thử, quan sát, bảo mật và khôi phục đã đủ trưởng thành.

## 2. Mục tiêu của CI

### Phát hiện lỗi khi chi phí sửa còn thấp

Lỗi thường dễ khoanh vùng hơn khi vừa được đưa vào. Nếu một PR nhỏ làm hỏng kiểm thử, phạm vi tìm kiếm thường tập trung vào vài commit gần nhất. Nếu nhóm tích hợp sau nhiều tuần, lỗi có thể đến từ tương tác giữa nhiều thay đổi và rất khó xác định nguyên nhân.

CI rút ngắn khoảng thời gian giữa lúc tạo lỗi và lúc nhận biết lỗi. Khoảng thời gian này càng ngắn, việc sửa chữa càng ít tốn công điều tra và phối hợp.

### Giảm rủi ro khi ghép mã nguồn

Những nhánh sống lâu có thể lệch xa nhánh chính về cấu trúc, thư viện, API và giả định nghiệp vụ. Tích hợp thường xuyên buộc nhóm giải quyết xung đột và khác biệt sớm, khi lượng thay đổi còn nhỏ.

CI không tự giải quyết mọi xung đột Git. Nó giúp phát hiện sớm những vấn đề xuất hiện sau khi ghép thay đổi, chẳng hạn biên dịch thất bại, kiểm thử không còn đúng hoặc một thành phần không tương thích với phần còn lại.

### Giữ nhánh chung ở trạng thái có thể sử dụng

Nhánh chính là điểm hội tụ của cả nhóm. Khi mỗi thay đổi phải vượt qua các kiểm tra bắt buộc trước khi được hợp nhất, nhóm giảm khả năng đưa một phiên bản rõ ràng đang hỏng vào nền tảng phát triển chung.

Điều này cần đi kèm quy tắc xử lý build đỏ. Một nhánh chính đang thất bại phải được ưu tiên khôi phục; tiếp tục hợp nhất thay đổi mới trong khi lỗi chưa được xử lý sẽ khiến việc xác định nguyên nhân ngày càng khó.

### Tạo cách kiểm tra nhất quán và có thể truy vết

Cùng một commit cần được kiểm tra bằng cùng một bộ lệnh, phiên bản công cụ và quy tắc chất lượng. Pipeline ghi lại commit, thời điểm chạy, kết quả từng bước và thông tin artifact nếu có. Nhờ vậy, nhóm có thể trả lời: phiên bản nào đã được kiểm tra, kiểm tra bằng cấu hình nào và vì sao một thay đổi được phép hợp nhất.

### Giải phóng thời gian cho công việc có giá trị hơn

Tự động hóa những thao tác lặp lại như biên dịch, chạy test, kiểm tra định dạng và phân tích mã giúp giảm lỗi do thao tác thủ công. Nhà phát triển có thể tập trung vào thiết kế, xử lý vấn đề và cải thiện sản phẩm thay vì lặp lại cùng một danh sách lệnh trên từng máy.

## 3. Vòng lặp CI điển hình

Một vòng lặp CI thường bắt đầu từ sự kiện Git và kết thúc bằng kết quả được gắn với commit hoặc PR:

1. Nhà phát triển tạo thay đổi nhỏ, chạy các kiểm tra phù hợp trên máy cá nhân và commit.
2. Thay đổi được push lên remote hoặc gửi qua PR.
3. Hệ thống CI nhận sự kiện, checkout đúng commit và dựng môi trường chạy.
4. Pipeline khôi phục dependency cần thiết, biên dịch và chạy các bước kiểm tra.
5. Hệ thống công bố trạng thái thành công hoặc thất bại cùng log.
6. Quy tắc bảo vệ nhánh sử dụng trạng thái này để quyết định có cho phép merge hay không.
7. Sau khi merge, pipeline trên nhánh chính tiếp tục xác minh trạng thái tích hợp.

    Thay đổi mã nguồn
          |
          v
    Commit và push / tạo PR
          |
          v
    CI nhận sự kiện Git
          |
          v
    Checkout commit và dựng môi trường
          |
          v
    Build và kiểm tra tĩnh
          |
          v
    Chạy kiểm thử tự động
          |
          v
    Tất cả kiểm tra đạt?
       /           \
     Không          Có
      |              |
      v              v
    Trả log       Công bố trạng thái
    và lỗi        thành công
      |              |
      v              v
    Sửa lỗi       Đủ điều kiện merge
    và push lại   theo chính sách nhánh
                     |
                     v
                Tích hợp vào nhánh chung

Một số dự án bổ sung bước đóng gói artifact sau khi kiểm thử. Nếu pipeline tạo artifact, nên gắn artifact với commit nguồn và lưu metadata cần thiết để truy vết. Việc triển khai artifact tới các môi trường thường thuộc phạm vi Continuous Delivery hoặc quy trình phát hành.

## 4. Tích hợp thường xuyên với Git

### Ưu tiên nhánh ngắn hạn

CI hoạt động tốt khi thay đổi được tích hợp thường xuyên. Nhóm có thể dùng trunk-based development, trong đó mọi người tích hợp trực tiếp hoặc qua PR ngắn hạn vào nhánh chính. Nếu cần nhánh tính năng, nên giữ nhánh tồn tại trong thời gian ngắn và đồng bộ với nhánh chính thường xuyên.

Không có một số ngày cố định phù hợp cho mọi nhóm. Dấu hiệu quan trọng là một nhánh có đang tích lũy quá nhiều thay đổi chưa được kiểm chứng hay không. Khi PR lớn tới mức khó hiểu, khó review hoặc cần nhiều lần sửa xung đột, nhóm nên chia nhỏ công việc.

### Chạy kiểm tra ở đúng sự kiện

Các sự kiện thường dùng gồm:

- **Pull Request:** kiểm tra thay đổi trước khi merge. Đây thường là cổng chất lượng quan trọng nhất.
- **Push lên nhánh chính:** xác minh trạng thái sau khi tích hợp.
- **Push lên nhánh làm việc:** cung cấp phản hồi sớm cho người phát triển, tùy chi phí pipeline.
- **Lịch định kỳ:** chạy các kiểm tra dài hoặc kiểm tra tương thích bổ sung. Chạy theo lịch chỉ là lớp bổ sung, không thay thế kiểm tra theo từng thay đổi.

Cần tránh tình trạng PR đã được kiểm tra nhưng nhánh chính thay đổi trước khi merge khiến kết quả cũ không còn đại diện cho trạng thái sắp tích hợp. Có thể xử lý bằng cách yêu cầu cập nhật nhánh, chạy lại kiểm tra sau khi cập nhật hoặc sử dụng merge queue tùy nền tảng.

### Thiết lập quy tắc bảo vệ nhánh

Nhánh chính nên yêu cầu các status check cần thiết phải thành công trước khi merge. Nhóm cũng có thể yêu cầu review, giới hạn quyền push trực tiếp và quy định cách xử lý ngoại lệ.

Tên status check nên ổn định và có ý nghĩa, ví dụ **build-and-test** hoặc **verify**. Khi đổi tên job, cần cập nhật chính sách bảo vệ nhánh để tránh vô tình bỏ mất một cổng kiểm tra.

## 5. Thiết kế pipeline CI

Pipeline là chuỗi công việc tự động mô tả cách xác minh một thay đổi. Nên lưu cấu hình pipeline dưới dạng mã trong cùng hệ thống quản lý phiên bản với ứng dụng. Khi thay đổi quy tắc build hoặc test, nhóm có thể review, truy vết và khôi phục thay đổi đó như với mã nguồn thông thường.

Một pipeline cơ bản thường có các nhóm bước sau:

| Nhóm bước | Mục đích | Ví dụ |
|---|---|---|
| Chuẩn bị | Lấy đúng mã nguồn và công cụ | Checkout commit, cài JDK, thiết lập biến môi trường |
| Khôi phục dependency | Có đủ thư viện để build | Gradle dependency resolution, Maven dependency resolution |
| Kiểm tra nhanh | Phát hiện lỗi cấu trúc và quy ước | Format, lint, compile, static analysis |
| Kiểm thử | Xác minh hành vi | Unit test, integration test, contract test |
| Kiểm tra chất lượng và bảo mật | Phát hiện rủi ro đã định nghĩa | Coverage gate, SAST, dependency scan, license policy |
| Đóng gói và lưu kết quả | Tạo đầu ra có thể truy vết | JAR, container image, test report, checksum |

Không phải dự án nào cũng cần tất cả bước trên trong mọi lần chạy. Hãy đặt các kiểm tra nhanh và ổn định ở đầu pipeline để phản hồi sớm. Những kiểm tra tốn thời gian hơn có thể chạy sau khi các bước cơ bản đạt, hoặc được phân tách thành job song song khi có thể.

### Giữ pipeline nhanh nhưng đáng tin cậy

Thời gian phản hồi ảnh hưởng trực tiếp đến nhịp làm việc. Nếu nhà phát triển phải chờ quá lâu cho một lỗi cú pháp hoặc lỗi biên dịch, họ có xu hướng trì hoãn việc tích hợp hoặc bỏ qua kết quả.

Một số cách cải thiện:

- Chạy các bước độc lập song song, nhưng chỉ khi chúng không tranh chấp tài nguyên hoặc phụ thuộc thứ tự.
- Cache dependency để giảm thời gian tải lại; cache chỉ là tối ưu hiệu năng, không được coi là nguồn dữ liệu đúng duy nhất.
- Chia unit test và integration test thành các nhóm có thời gian chạy phù hợp.
- Chỉ chạy lại phần kiểm tra theo phạm vi thay đổi khi hệ thống xác định phụ thuộc đủ chính xác; vẫn cần một lần kiểm tra đầy đủ phù hợp trên nhánh chính.
- Đặt timeout hợp lý để job treo không chiếm runner vô thời hạn.
- Thu thập test report và log ngay cả khi một bước thất bại để giảm thời gian điều tra.

Không nên tối ưu tốc độ bằng cách âm thầm bỏ qua test, giảm kiểm tra mà không đánh giá rủi ro hoặc đánh dấu job thành công khi lệnh thực tế thất bại.

## 6. Tổ chức kiểm thử trong CI

Kiểm thử tự động là một phần quan trọng của CI vì nó kiểm tra hành vi của phần mềm sau mỗi thay đổi. Chiến lược kiểm thử cần cân bằng giữa tốc độ, độ tin cậy và khả năng phát hiện lỗi.

| Loại kiểm thử | Phạm vi | Cách dùng trong CI |
|---|---|---|
| Unit test | Một hàm, lớp hoặc thành phần nhỏ | Chạy thường xuyên vì thường nhanh và dễ khoanh vùng |
| Integration test | Tương tác giữa nhiều thành phần hoặc với hệ thống phụ trợ | Chạy trong môi trường được kiểm soát; dùng database hoặc service thử nghiệm khi cần |
| Contract test | Cam kết giao tiếp giữa các service hoặc module | Phát hiện thay đổi API không tương thích |
| End-to-end test | Luồng nghiệp vụ xuyên suốt qua nhiều lớp | Chọn tập luồng quan trọng; kiểm soát thời gian và độ ổn định |
| Smoke test | Kiểm tra nhanh những khả năng thiết yếu | Có thể chạy sau khi dựng ứng dụng hoặc sau khi triển khai tới môi trường kiểm thử |

Unit test thường tạo lớp phản hồi nhanh nhất. Integration test và end-to-end test có thể chậm hơn vì cần khởi tạo service, dữ liệu và môi trường. Một pipeline tốt không nhất thiết chạy mọi kịch bản ở cùng một tầng; nó chọn tập kiểm tra phù hợp với rủi ro của thay đổi.

### Làm cho test có tính xác định

Một test đáng tin cậy cần cho kết quả nhất quán khi đầu vào và phiên bản mã nguồn không đổi. Các nguyên nhân thường gây test chập chờn (flaky test) gồm:

- Phụ thuộc vào thứ tự test hoặc trạng thái dùng chung.
- Dựa vào thời gian thực, múi giờ hoặc lịch hệ thống.
- Gọi mạng tới dịch vụ bên ngoài không ổn định.
- Dùng dữ liệu thử nghiệm có thể bị job khác sửa hoặc xóa.
- Không chờ đúng điều kiện bất đồng bộ.
- Chia sẻ tài nguyên giữa các job chạy song song.

Khi phát hiện flaky test, hãy ghi nhận test, tần suất lỗi và điều kiện tái hiện; sau đó sửa nguyên nhân. Retry có giới hạn có thể hỗ trợ chẩn đoán lỗi hạ tầng tạm thời, nhưng không nên biến retry thành cách che giấu test không ổn định.

## 7. Quality gate: quy định rõ điều kiện đạt

Quality gate là tập điều kiện mà thay đổi phải đáp ứng trước khi được phép đi tiếp. Một gate tốt có tiêu chí rõ, kết quả có thể đo và người chịu trách nhiệm xử lý khi thất bại.

Các điều kiện thường gặp:

- Mã nguồn biên dịch thành công.
- Các test bắt buộc đều đạt.
- Không có lỗi nghiêm trọng từ static analysis hoặc security scan theo chính sách của dự án.
- Không vi phạm quy tắc định dạng hoặc kiểm tra chất lượng đã thống nhất.
- Báo cáo coverage đáp ứng ngưỡng phù hợp, nếu nhóm đã xác định ngưỡng có ý nghĩa.
- Artifact được tạo thành công và có thông tin nguồn gốc cần thiết.

Không nên chọn ngưỡng coverage chỉ để đạt một con số đẹp. Coverage cho biết phần mã được thực thi trong test, không chứng minh test đã kiểm tra đúng hành vi. Nên xem xét thêm chất lượng assertion, các luồng nghiệp vụ quan trọng và lỗi từng xuất hiện trong thực tế.

Cổng chất lượng cần có cơ chế ngoại lệ được kiểm soát. Nếu buộc phải bỏ qua một gate trong tình huống khẩn cấp, lý do, người chấp thuận và công việc khắc phục cần được ghi nhận. Ngoại lệ không được trở thành cách làm mặc định.

## 8. Ví dụ pipeline CI cho dự án Java dùng Gradle

Ví dụ dưới đây dùng GitHub Actions để minh họa một pipeline tối thiểu. Workflow chạy khi có PR và khi push lên nhánh **main**; nó lấy mã nguồn, thiết lập JDK, cache dependency Gradle và chạy task **check**.

    name: ci

    on:
      pull_request:
      push:
        branches: [main]

    permissions:
      contents: read

    jobs:
      verify:
        name: build-and-test
        runs-on: ubuntu-latest
        timeout-minutes: 20

        steps:
          - name: Checkout source
            uses: actions/checkout@v4

          - name: Set up JDK
            uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: "21"
              cache: gradle

          - name: Verify
            run: ./gradlew --no-daemon check

Một số điểm cần hiểu khi áp dụng ví dụ:

- Phiên bản JDK phải khớp với Java toolchain hoặc yêu cầu build của dự án; giá trị **21** trong ví dụ cần được điều chỉnh nếu dự án dùng phiên bản khác.
- Với Gradle, task **check** thường gom các bước kiểm tra đã được plugin và dự án khai báo, bao gồm test. Nhóm cần xác nhận các test và quality check mong muốn thực sự được gắn vào task này.
- **cache: gradle** giúp giảm thời gian tải dependency. Cache không thay thế lock file, Gradle Wrapper hoặc việc kiểm tra dependency.
- **permissions: contents: read** giới hạn quyền mặc định của job. Nếu pipeline cần xuất bản artifact hoặc cập nhật hệ thống khác, chỉ cấp thêm quyền cần thiết cho job thực hiện hành động đó.
- Ví dụ dùng major tag để dễ đọc. Với môi trường yêu cầu kiểm soát chuỗi cung ứng chặt chẽ, nên pin action theo commit SHA đầy đủ và có quy trình cập nhật phiên bản.
- Khi đã tạo status check ổn định, cấu hình bảo vệ nhánh để yêu cầu job **build-and-test** đạt trước khi merge.

Trong dự án thực tế, có thể tách compile, unit test, integration test và static analysis thành các job riêng để dễ quan sát hoặc chạy song song. Chỉ tách khi điều đó giúp giảm thời gian phản hồi hoặc làm rõ trách nhiệm; quá nhiều job nhỏ cũng làm pipeline khó theo dõi.

## 9. Bảo mật và khả năng tái lập

CI thường chạy mã do nhiều người đóng góp gửi lên, vì vậy pipeline cần được xem như một phần của bề mặt bảo mật của hệ thống.

### Bảo vệ bí mật

- Không ghi token, mật khẩu hoặc private key trực tiếp vào file cấu hình được commit.
- Lưu bí mật trong secret manager hoặc kho secret của nền tảng CI; chỉ truyền vào job cần sử dụng.
- Không in giá trị bí mật ra log, kể cả khi bật chế độ debug.
- Giới hạn quyền token theo nguyên tắc đặc quyền tối thiểu.
- Xem xét kỹ luồng chạy từ fork hoặc mã nguồn không tin cậy; không cấp bí mật triển khai cho job kiểm tra mã bên ngoài.
- Tách job kiểm tra PR với job có quyền publish hoặc deploy khi hai loại công việc có mức tin cậy khác nhau.

### Giữ đầu vào build có thể tái lập

Kết quả build có thể thay đổi nếu môi trường, dependency hoặc công cụ thay đổi ngoài dự kiến. Để tăng khả năng tái lập:

- Commit Gradle Wrapper hoặc Maven Wrapper và sử dụng phiên bản đã thống nhất.
- Khai báo phiên bản JDK, runtime, compiler và công cụ build rõ ràng.
- Dùng lock file hoặc cơ chế cố định phiên bản dependency khi hệ sinh thái hỗ trợ.
- Hạn chế phụ thuộc vào thư viện được tải từ nguồn không đáng tin cậy.
- Ghi lại commit SHA, phiên bản công cụ và metadata cần thiết cùng kết quả build.
- Dùng container image hoặc runner image có phiên bản được kiểm soát khi tính nhất quán môi trường là yêu cầu quan trọng.

Cache cần được quản lý như dữ liệu tăng tốc, không phải bằng chứng về tính đúng đắn. Nếu cache lỗi thời hoặc bị nhiễm bẩn, pipeline vẫn cần có khả năng khôi phục và chạy đúng từ các đầu vào đã khai báo.

## 10. Xử lý khi pipeline thất bại

Khi CI báo đỏ, mục tiêu đầu tiên là khôi phục trạng thái đáng tin cậy của nhánh chung. Cách xử lý có thể theo trình tự:

1. Xác định commit và job thất bại; đọc phần log đầu tiên có lỗi thực sự thay vì chỉ nhìn dòng kết thúc.
2. Phân loại nguyên nhân: lỗi mã nguồn, test sai, dependency hoặc môi trường, runner/hạ tầng, hay cấu hình pipeline.
3. Tái hiện lỗi trong môi trường gần với CI nhất có thể.
4. Sửa nguyên nhân gốc và gửi thay đổi mới để pipeline chạy lại.
5. Nếu lỗi thuộc hạ tầng, ghi nhận phạm vi ảnh hưởng và khôi phục dịch vụ; tránh thay đổi mã nguồn chỉ để làm xanh một job đang hỏng do môi trường.
6. Sau khi pipeline đạt, kiểm tra lại trạng thái của PR hoặc nhánh chính trước khi tiếp tục merge.

Một số nguyên tắc vận hành giúp tránh tích lũy lỗi:

- Không merge khi một kiểm tra bắt buộc đang thất bại hoặc chưa có kết quả.
- Khi nhánh chính đỏ, ưu tiên sửa hoặc revert thay đổi gây lỗi.
- Giữ log và test report đủ lâu để điều tra sự cố.
- Không xóa một test thất bại chỉ vì nó làm pipeline chậm hoặc đỏ; cần xác định test sai, sản phẩm sai hay môi trường sai.
- Theo dõi flaky test như một vấn đề kỹ thuật cần xử lý, không xem đó là nhiễu bình thường.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ build theo lịch | Lỗi tích hợp được phát hiện muộn | Kích hoạt kiểm tra theo push và PR |
| Nhánh tính năng tồn tại quá lâu | Xung đột lớn, khó khoanh vùng lỗi | Chia thay đổi nhỏ và tích hợp thường xuyên |
| Pipeline chỉ kiểm tra build, không có test | Lỗi hành vi vẫn lọt qua | Bổ sung test theo rủi ro và tầng phù hợp |
| Test chập chờn nhưng thường xuyên retry | Kết quả CI mất độ tin cậy | Tìm nguyên nhân và sửa test hoặc môi trường |
| Pipeline quá chậm | Phản hồi đến muộn, nhóm ngại tích hợp | Tối ưu thứ tự, cache và mức song song |
| Cho phép merge dù gate bắt buộc thất bại | Nhánh chính dễ mất ổn định | Bảo vệ nhánh và quy định ngoại lệ rõ ràng |
| Đưa secret vào log hoặc cấu hình | Rò rỉ thông tin xác thực | Dùng secret store và quyền tối thiểu |
| Mỗi máy build một kiểu | Khó tái hiện lỗi | Chuẩn hóa toolchain và wrapper |
| Chỉ nhìn tỷ lệ coverage | Có thể tạo test chạy qua nhưng ít giá trị | Đánh giá assertion và luồng nghiệp vụ quan trọng |

## 12. Đo lường hiệu quả CI

Nên dùng số liệu để tìm điểm nghẽn và cải thiện hệ thống, không dùng chúng để xếp hạng cá nhân. Một số chỉ số có ích:

| Chỉ số | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Thời gian phản hồi CI | Từ lúc push/PR đến khi có kết quả cần thiết | Tăng kéo dài có thể cho thấy test chậm, runner thiếu tài nguyên hoặc dependency tải lâu |
| Tỷ lệ pipeline thành công | Mức độ ổn định của các lần chạy | Tỷ lệ thấp cần phân tích lỗi sản phẩm, test và hạ tầng riêng biệt |
| Thời gian nhánh chính ở trạng thái đỏ | Thời gian từ khi phát hiện lỗi đến khi khôi phục | Giá trị cao cho thấy quy trình ưu tiên sửa lỗi chưa hiệu quả |
| Tỷ lệ flaky test | Tỷ lệ test cho kết quả không ổn định với cùng đầu vào | Giúp nhận diện phần kiểm thử đang làm giảm niềm tin vào CI |
| Thời gian chờ runner | Thời gian job nằm trong hàng đợi trước khi chạy | Có thể cho thấy năng lực runner không theo kịp tải |
| Tỷ lệ PR phải sửa sau vòng CI đầu tiên | Mức độ thay đổi vượt qua kiểm tra ngay lần đầu | Dùng để tìm thiếu sót trong kiểm tra local hoặc quy tắc review, không nên tối ưu bằng cách giảm chất lượng |

Không có một ngưỡng chung phù hợp với mọi dự án. Hãy thiết lập đường cơ sở, theo dõi xu hướng theo thời gian và kết hợp số liệu với phản hồi của nhóm. Ví dụ, pipeline nhanh hơn nhưng tỷ lệ lỗi lọt sang giai đoạn sau tăng lên không phải là cải thiện thực sự.

## 13. Lộ trình áp dụng CI

Một nhóm chưa có CI hoặc đang có pipeline rời rạc có thể triển khai theo từng bước:

1. **Chuẩn hóa cách build:** thống nhất lệnh build, phiên bản runtime và wrapper để mọi máy có thể chạy cùng quy trình.
2. **Tự động hóa build trên PR:** chạy compile và các kiểm tra cơ bản mỗi khi PR được tạo hoặc cập nhật.
3. **Bổ sung test có giá trị cao:** ưu tiên unit test cho logic quan trọng, sau đó thêm integration test cho các ranh giới dễ phát sinh lỗi.
4. **Bảo vệ nhánh chính:** yêu cầu các kiểm tra bắt buộc thành công trước khi merge và quy định cách xử lý build đỏ.
5. **Thêm quality gate phù hợp:** đưa format, static analysis, dependency scan và các chính sách chất lượng vào pipeline theo mức rủi ro.
6. **Cải thiện tốc độ và độ ổn định:** đo thời gian từng job, xử lý flaky test, quản lý cache và năng lực runner.
7. **Tăng khả năng truy vết:** lưu test report, metadata commit và artifact khi cần; bảo vệ secret và giới hạn quyền của pipeline.
8. **Rà soát định kỳ:** loại bỏ bước trùng lặp, cập nhật công cụ và điều chỉnh gate khi kiến trúc hoặc rủi ro của hệ thống thay đổi.

Không cần triển khai mọi công cụ ngay từ đầu. Một pipeline nhỏ, chạy đều và được cả nhóm tin tưởng có giá trị hơn một pipeline phức tạp nhưng thường xuyên bị bỏ qua.

## 14. Checklist thực hành

Trước khi coi CI là một phần ổn định của quy trình phát triển, hãy kiểm tra các câu hỏi sau:

- [ ] Thay đổi được kiểm tra tự động khi PR được tạo hoặc cập nhật.
- [ ] Nhánh chính có pipeline xác minh sau khi tích hợp.
- [ ] Pipeline checkout đúng commit và ghi lại kết quả gắn với commit đó.
- [ ] Lệnh build và test có thể chạy lại trên môi trường đã chuẩn hóa.
- [ ] Có test tự động bao phủ các logic và luồng quan trọng.
- [ ] Các status check bắt buộc được cấu hình trong chính sách bảo vệ nhánh.
- [ ] Khi thất bại, log và test report giúp xác định nguyên nhân.
- [ ] Flaky test được theo dõi và có người chịu trách nhiệm xử lý.
- [ ] Secret không nằm trong mã nguồn hoặc log; quyền job được giới hạn.
- [ ] Cache chỉ phục vụ tăng tốc, không thay thế dependency được khai báo.
- [ ] Thời gian chạy, tỷ lệ thất bại và thời gian khôi phục được theo dõi.
- [ ] Nhóm có quy trình ưu tiên khôi phục khi nhánh chính bị lỗi.

## Kết luận

CI biến việc tích hợp mã nguồn từ một hoạt động dễ bị trì hoãn thành một vòng lặp ngắn, tự động và có thể quan sát. Giá trị của nó đến từ việc tích hợp thường xuyên, kiểm tra đáng tin cậy, phản hồi nhanh và trách nhiệm chung trong việc giữ nhánh chính ổn định. Khi nền tảng này được duy trì tốt, nhóm có thể mở rộng sang Continuous Delivery và các quy trình phát hành tự động với mức độ kiểm soát cao hơn.

