# Đặt các kiểm tra phản hồi nhanh vào giai đoạn sớm

Trong CI/CD, thời điểm một kiểm tra trả kết quả ảnh hưởng trực tiếp đến tốc độ phát triển. Nếu một lỗi định dạng, lỗi cú pháp hoặc lỗi logic đơn giản chỉ được phát hiện sau khi toàn bộ pipeline chạy xong, nhóm đã tiêu tốn thời gian chờ và tài nguyên không cần thiết. Khi các kiểm tra phản hồi nhanh được đặt ở giai đoạn sớm, người tạo thay đổi có thể nhận tín hiệu khi ngữ cảnh còn mới, sửa lỗi trước khi nó lan sang nhánh tích hợp hoặc bản phát hành.

Đặt kiểm tra sớm không có nghĩa là đưa mọi loại kiểm thử vào đầu pipeline. Cần chọn các phép kiểm tra có thời gian chạy ngắn, kết quả rõ, chi phí thấp và khả năng phát hiện vấn đề cao đối với thay đổi đang xét. Những kiểm tra cần môi trường phức tạp, dữ liệu lớn hoặc nhiều dịch vụ vẫn có vị trí phù hợp ở giai đoạn sau. Chiến lược tốt tổ chức các lớp kiểm tra theo giá trị phản hồi, độ tin cậy và phụ thuộc, đồng thời bảo đảm các rủi ro quan trọng vẫn được kiểm tra trước khi phát hành.

## 1. Vì sao cần phản hồi sớm?

Một lỗi được phát hiện càng muộn thường càng tốn công điều tra. Khi thay đổi đã đi qua nhiều commit, được tích hợp với nhiều thành phần hoặc triển khai lên môi trường dùng chung, nguyên nhân có thể khó xác định hơn. Phản hồi sớm giúp:

- Người phát triển sửa lỗi khi còn nhớ rõ mục đích và phạm vi thay đổi.
- Ngăn lỗi cơ bản đi vào nhánh tích hợp và ảnh hưởng người khác.
- Giảm thời gian chờ pipeline bằng cách loại bỏ lỗi dễ phát hiện trước.
- Tiết kiệm runner, môi trường và dịch vụ kiểm thử cho những thay đổi không đạt điều kiện cơ bản.
- Tạo thói quen nhận trách nhiệm về chất lượng ngay trong lúc viết mã.
- Rút ngắn vòng lặp giữa thay đổi, kiểm tra, sửa và xác minh.
- Cung cấp tín hiệu nhất quán để reviewer tập trung vào thiết kế và logic thay vì lỗi cơ bản.

Phản hồi sớm cũng giúp giảm chi phí chuyển ngữ cảnh. Nếu một lỗi lint được phát hiện ngay trong IDE hoặc pre-commit, người viết có thể sửa trong vài phút. Nếu lỗi đó chỉ xuất hiện sau một pipeline dài, người viết có thể đã chuyển sang công việc khác hoặc phải khôi phục ngữ cảnh.

Tuy nhiên, tốc độ không phải mục tiêu duy nhất. Một kiểm tra rất nhanh nhưng thường xuyên báo sai, bỏ sót lỗi quan trọng hoặc tạo kết quả không ổn định sẽ làm giảm niềm tin vào pipeline. Phải tối ưu cả thời gian phản hồi lẫn chất lượng tín hiệu.

## 2. Hiểu các lớp kiểm tra phù hợp với giai đoạn sớm

Các kiểm tra nên được bố trí theo đặc điểm của chúng: thời gian, độ ổn định, phạm vi và loại vấn đề có thể phát hiện.

| Loại kiểm tra | Ví dụ | Giai đoạn thường phù hợp | Đặc điểm |
|---|---|---|---|
| Kiểm tra định dạng | Formatter, kiểm tra whitespace và format | Local, pre-commit, CI đầu tiên | Rất nhanh, kết quả rõ |
| Kiểm tra tĩnh cơ bản | Lint, kiểm tra cú pháp, type checking | Local, pre-commit, pull request | Nhanh, không cần chạy toàn hệ thống |
| Kiểm tra đơn vị | Unit test cho logic thuần và thành phần nhỏ | Local, pull request | Nhanh nếu phụ thuộc được cô lập |
| Kiểm tra thành phần nhẹ | Component test với fake hoặc service test nhỏ | Pull request | Xác minh tương tác trong ranh giới hẹp |
| Kiểm tra hợp đồng | Schema validation, consumer/provider contract | Pull request, trước tích hợp | Phát hiện sai lệch giao diện giữa dịch vụ |
| Quét bí mật và dependency | Secret scan, kiểm tra dependency và license theo chính sách | Pre-commit, pull request | Có thể chạy nhanh nếu quét phạm vi thay đổi |
| Kiểm tra migration/schema | Kiểm tra tính hợp lệ của migration và tương thích cơ bản | Pull request | Phát hiện lỗi cấu trúc trước khi triển khai |
| Smoke test | Kiểm tra một số luồng tối thiểu sau khi triển khai | Sau deploy lên môi trường | Cần môi trường chạy được |
| Kiểm thử tích hợp rộng | Nhiều dịch vụ, database, queue và phụ thuộc thật | Sau khi qua kiểm tra sớm | Chạy lâu hơn, cần môi trường |
| End-to-end, tải, phục hồi | Luồng đầy đủ, workload, fault injection | Giai đoạn sau hoặc lịch riêng | Chi phí cao, phạm vi rộng |

Không có một thứ tự cố định cho mọi dự án. Một bộ unit test có phụ thuộc khởi tạo chậm có thể chạy lâu hơn một contract test. Một quét bảo mật có thể cần chạy sớm dù tốn thời gian hơn lint vì rủi ro của nó cao. Hãy đo thời gian và giá trị thực tế của từng bước thay vì chỉ dựa vào tên loại kiểm thử.

## 3. Đặt kiểm tra tại đúng điểm trong vòng lặp phát triển

Phản hồi sớm có thể xuất hiện ở nhiều điểm, từ máy của người phát triển đến pull request.

### 3.1. Trong IDE và khi phát triển cục bộ

Các kiểm tra tức thời như formatter, lint, type checking và một phần unit test giúp phát hiện lỗi trước khi tạo commit. Công cụ nên dễ chạy và có cấu hình nhất quán với CI để tránh tình trạng local pass nhưng pipeline fail vì quy tắc khác nhau.

Không nên yêu cầu mọi test phải chạy mỗi khi lưu tệp. Chạy quá nhiều việc trên mỗi thao tác có thể làm IDE chậm và khiến người phát triển tắt kiểm tra. Chọn tập nhỏ theo tệp hoặc module đang sửa, đồng thời cung cấp lệnh chạy đầy đủ khi cần.

### 3.2. Trước khi tạo commit

Pre-commit hook có thể kiểm tra định dạng, lint nhanh, secret scan và test nhỏ. Hook nên có thời gian thực thi phù hợp, thông báo lỗi dễ hiểu và cách chạy lại thủ công.

Hook cục bộ hỗ trợ thói quen nhưng không phải ranh giới bảo đảm chất lượng duy nhất. Người dùng có thể bỏ qua hook, máy có cấu hình khác hoặc hook không chạy trong một số luồng. CI phải thực hiện lại những kiểm tra bắt buộc trên môi trường được quản lý.

### 3.3. Khi mở hoặc cập nhật pull request

Pull request là điểm kiểm tra quan trọng vì thay đổi sắp được tích hợp với nhánh chung. Pipeline nên chạy các kiểm tra nhanh, ổn định và có liên quan đến thay đổi. Kết quả cần gắn với commit cụ thể và được cập nhật khi commit thay đổi.

Các kiểm tra thường phù hợp gồm build cơ bản, lint, type checking, unit test, contract test liên quan, quét bí mật và kiểm tra dependency theo chính sách.

### 3.4. Sau khi tích hợp và triển khai môi trường

Sau khi merge, có thể chạy bộ kiểm thử tích hợp rộng hơn, smoke test trên môi trường đã triển khai và các phép kiểm tra phụ thuộc vào dịch vụ thật. Giai đoạn này xác minh sự kết hợp của các thay đổi đã tích hợp.

Không nên coi kiểm tra sớm là thay thế kiểm thử sau tích hợp. Mỗi giai đoạn trả lời câu hỏi khác nhau.

## 4. Sắp xếp pipeline theo thời gian, giá trị và phụ thuộc

Một pipeline phản hồi nhanh cần cân bằng ba yếu tố:

- **Thời gian chạy:** kiểm tra nào có thể hoàn tất nhanh?
- **Giá trị phát hiện:** kiểm tra nào có khả năng tìm lỗi phổ biến hoặc rủi ro cao?
- **Phụ thuộc:** kiểm tra nào cần artifact, môi trường hoặc kết quả từ bước trước?

Một cách sắp xếp thường dùng:

1. Kiểm tra cấu trúc thay đổi, format và lint.
2. Kiểm tra cú pháp, type và build module cần thiết.
3. Chạy unit test nhanh, độc lập.
4. Chạy contract test và component test phù hợp.
5. Quét dependency, secret và policy theo yêu cầu.
6. Tạo artifact và triển khai môi trường kiểm thử.
7. Chạy smoke test và kiểm thử tích hợp.
8. Chạy end-to-end, hiệu năng, bảo mật chuyên sâu hoặc kiểm tra dài theo lịch phù hợp.

Thứ tự cụ thể cần dựa trên số liệu. Nếu quét dependency mất 20 giây và phát hiện rủi ro nghiêm trọng, có thể đặt nó sớm hơn một bộ test thành phần mất vài phút. Nếu build là điều kiện bắt buộc để chạy test, các bước phụ thuộc phải chờ artifact hợp lệ.

Các bước độc lập có thể chạy song song, nhưng cần tránh tạo quá nhiều tải khiến runner hoặc dịch vụ dùng chung bị nghẽn. Chạy song song chỉ giúp nhanh hơn khi tài nguyên và dữ liệu được cô lập.

## 5. Dùng nguyên tắc fail fast có kiểm soát

Fail fast nghĩa là dừng sớm khi đã có đủ bằng chứng rằng thay đổi không đáp ứng điều kiện bắt buộc, tránh tiếp tục các bước tốn kém không còn giá trị cho quyết định hiện tại.

Ví dụ, nếu build không biên dịch được thì không cần chạy test tích hợp phụ thuộc vào artifact đó. Nếu secret scan phát hiện khóa bí mật đã được commit và chính sách yêu cầu chặn, pipeline có thể dừng trước khi triển khai môi trường.

Tuy nhiên, fail fast cần được áp dụng có cân nhắc:

- Không dừng chỉ vì một cảnh báo không nghiêm trọng chưa được xác minh nếu chính sách cho phép tiếp tục các kiểm tra độc lập.
- Không che mất kết quả của các kiểm tra độc lập có giá trị chẩn đoán nếu chi phí chạy thấp.
- Không để lỗi môi trường bị báo như lỗi sản phẩm.
- Khi dừng, phải hiển thị nguyên nhân, bước thất bại và cách khắc phục.
- Với lỗi có thể phục hồi như runner tạm thời mất kết nối, dùng retry có giới hạn và ghi nhận lần chạy lại.
- Không dùng retry để che flaky test hoặc lỗi thật.

Có thể phân loại bước thành blocking và informational. Blocking là điều kiện bắt buộc để tiếp tục tích hợp; informational cung cấp tín hiệu để xem xét nhưng không tự động chặn. Phân loại cần được công bố và quản lý theo rủi ro.

## 6. Chọn kiểm tra nhanh dựa trên phạm vi thay đổi

Chạy toàn bộ suite cho mọi commit có thể tốn thời gian, nhưng chỉ chạy test của tệp đã sửa cũng có thể bỏ sót tác động gián tiếp. Cần có chiến lược chọn test dựa trên phụ thuộc và rủi ro.

Các nguồn thông tin có thể dùng:

- Module hoặc package bị thay đổi.
- Đồ thị phụ thuộc giữa thành phần.
- Chủ sở hữu dịch vụ và API liên quan.
- Nhãn hoặc loại thay đổi trong pull request.
- Lịch sử lỗi và vùng có rủi ro cao.
- Hợp đồng mà thành phần cung cấp hoặc tiêu thụ.
- Migration, cấu hình hoặc thư viện dùng chung bị ảnh hưởng.

Ví dụ, thay đổi một hàm tính thuế có thể chỉ cần chạy unit test module tính tiền và các test liên quan đến đơn hàng; thay đổi thư viện xác thực dùng chung có thể cần chạy test ở tất cả consumer quan trọng.

Chọn test theo phạm vi thay đổi phải có cơ chế fallback. Nếu không xác định được tác động hoặc đồ thị phụ thuộc chưa đầy đủ, chạy tập rộng hơn. Không nên giảm kiểm thử chỉ dựa trên tên tệp hoặc một quy tắc chọn test chưa được xác minh.

## 7. Giữ kiểm tra sớm nhanh và ổn định

Một kiểm tra chỉ hữu ích khi kết quả đủ đáng tin. Có một số cách cải thiện thời gian và độ ổn định.

### 7.1. Giảm thời gian khởi tạo

- Dùng cache dependency có khóa theo phiên bản và lockfile.
- Tái sử dụng artifact đã được xác minh khi phù hợp.
- Tránh cài lại công cụ hoặc dependency không cần thiết trong mỗi bước.
- Chạy test theo module hoặc nhóm nhỏ trước khi chạy toàn bộ.
- Dùng runner phù hợp với mức tải thực tế.
- Tránh khởi động dịch vụ nặng cho các test không cần chúng.

Cache phải được quản lý theo tính toàn vẹn. Cache lỗi thời hoặc dùng chung không đúng khóa có thể tạo kết quả sai. Cần có cách vô hiệu hóa và tái tạo cache khi dependency hoặc môi trường thay đổi.

### 7.2. Cải thiện tính độc lập của test

- Mỗi test tự chuẩn bị dữ liệu cần thiết.
- Không phụ thuộc thứ tự chạy.
- Cô lập database, queue, file và cache theo phạm vi phù hợp.
- Dùng fake hoặc stub cho phụ thuộc không cần xác minh ở lớp hiện tại.
- Chờ theo trạng thái thay vì sleep cố định.
- Làm sạch tài nguyên sau khi chạy và giữ dữ liệu thất bại theo chính sách điều tra.

### 7.3. Giảm flaky test

Flaky test là test có thể pass hoặc fail khi mã nguồn và điều kiện cần kiểm tra không thay đổi. Nguyên nhân thường gồm race condition, thời gian chờ, dữ liệu dùng chung, phụ thuộc mạng, môi trường không ổn định hoặc assertion quá mong manh.

Khi phát hiện flaky test:

1. Ghi nhận test, commit, môi trường và lịch sử lần chạy.
2. Xác định có thể tái hiện khi chạy riêng, chạy lặp hoặc chạy song song không.
3. Tìm nguyên nhân thay vì tăng timeout hoặc retry tùy tiện.
4. Sửa đồng bộ, dữ liệu, điều kiện chờ hoặc ranh giới phụ thuộc.
5. Chạy lại đủ lần để xác minh độ ổn định.
6. Nếu cần quarantine tạm thời, ghi chủ sở hữu, lý do, thời hạn và phạm vi ảnh hưởng.

Không nên để quarantine trở thành nơi chứa test quan trọng bị bỏ quên. Các test bị cách ly phải có kế hoạch sửa và đánh giá rủi ro nếu không còn blocking.

## 8. Xây dựng cổng chất lượng cho giai đoạn sớm

Quality gate là tập điều kiện dùng để quyết định thay đổi có thể đi tiếp hay không. Cổng chất lượng cần phản ánh rủi ro và mức tin cậy của phép kiểm tra.

Một số điều kiện có thể đặt ở pull request:

- Build hoặc type check bắt buộc thành công.
- Unit test quan trọng không có lỗi chưa xử lý.
- Contract test cho giao diện bị thay đổi đạt yêu cầu.
- Không có secret bị lộ theo chính sách.
- Không có dependency hoặc lỗ hổng vượt ngưỡng chặn đã thống nhất.
- Quy tắc lint hoặc static analysis bắt buộc được đáp ứng.
- Báo cáo coverage hoặc test result có mặt nếu dự án yêu cầu.

Không nên đặt một ngưỡng coverage chung mà không xét ý nghĩa. Coverage cao không chứng minh assertion có giá trị; coverage thấp ở một đoạn rủi ro cao có thể đáng quan tâm hơn coverage thấp ở mã chuyển đổi đơn giản. Cổng cần đo điều có ý nghĩa và tránh tạo động lực tối ưu chỉ số thay vì chất lượng.

Mỗi gate cần có:

- Mục đích và rủi ro được kiểm soát.
- Phạm vi kiểm tra.
- Ngưỡng và quy tắc pass/fail.
- Chủ sở hữu chính sách.
- Hướng xử lý khi fail hoặc không thể chạy.
- Cơ chế ngoại lệ có người phê duyệt và thời hạn.
- Lịch sử thay đổi của ngưỡng.

Nếu một bước không chạy được do sự cố hạ tầng, kết quả nên là inconclusive hoặc infrastructure failure theo mô hình trạng thái của pipeline, không tự động được xem là pass.

## 9. Hiển thị kết quả để người phát triển hành động ngay

Phản hồi nhanh chỉ có giá trị khi người nhận hiểu điều gì sai và phải làm gì tiếp theo.

Một kết quả tốt nên cung cấp:

- Trạng thái rõ: passed, failed, skipped, inconclusive hoặc infrastructure error.
- Tên bước và nhóm test thất bại.
- Commit, build và môi trường liên quan.
- Thông báo lỗi ngắn gọn, chỉ ra vị trí hoặc test case.
- Log hoặc artifact cần thiết để điều tra.
- Hướng dẫn chạy lại cục bộ hoặc trên CI.
- Liên kết đến hướng dẫn sửa lỗi hoặc chủ sở hữu khi cần.
- Phân biệt lỗi sản phẩm với lỗi test và lỗi môi trường.

Không nên chỉ hiển thị “pipeline failed”. Nếu lỗi do type checking, cần nêu tệp và vị trí. Nếu contract test fail, chỉ rõ operation hoặc trường không tương thích. Nếu secret scan fail, chỉ ra vị trí đã che giá trị nhạy cảm và hướng xử lý như thu hồi secret, không in secret vào log.

Báo cáo nên gắn với commit cụ thể. Khi có commit mới, kết quả cũ không được hiểu nhầm là đã xác minh thay đổi mới.

## 10. Tích hợp kiểm tra nhanh vào pull request và CI

Một pipeline mẫu có thể chia thành các nhóm độc lập:

~~~yaml
stages:
  - validate
  - unit
  - contract
  - build
  - integration

validate:
  script:
    - formatter-check
    - lint
    - type-check
    - secret-scan

unit:
  needs: [validate]
  script:
    - run-fast-unit-tests

contract:
  needs: [validate]
  script:
    - validate-api-schemas
    - run-contract-tests

build:
  needs: [unit, contract]
  script:
    - build-artifact

integration:
  needs: [build]
  script:
    - deploy-test-environment
    - run-smoke-and-integration-tests
~~~

Đây chỉ là cấu trúc minh họa; cú pháp và cách định nghĩa dependency phụ thuộc nền tảng CI đang sử dụng. Có thể cho validate, unit và contract chạy song song nếu chúng độc lập. Build có thể chạy sớm hơn nếu pipeline cần artifact để thực hiện các bước khác, nhưng không nên triển khai môi trường khi các gate bắt buộc đã thất bại.

Với pull request, nên hiển thị trạng thái từng nhóm kiểm tra và tổng kết gate. Nếu có nhiều nhóm sở hữu, báo cáo cần phân biệt kiểm tra nào bắt buộc và kiểm tra nào chỉ cung cấp thông tin.

## 11. Bảo vệ pipeline khỏi rủi ro và cấu hình sai

Pipeline phản hồi sớm có thể thực thi mã từ pull request, truy cập dependency và tương tác với tài nguyên thử nghiệm. Vì vậy, cần thiết kế quyền và ranh giới an toàn.

Các nguyên tắc:

- Runner của pull request từ nguồn không tin cậy không được nhận secret production.
- Dùng token ngắn hạn và quyền tối thiểu.
- Không chạy test phá hủy trên môi trường dùng chung hoặc production.
- Tách tài khoản và dữ liệu cho từng môi trường.
- Kiểm soát script và dependency được thực thi trong pipeline.
- Bảo vệ cache khỏi việc ghi dữ liệu không tin cậy rồi dùng ở ngữ cảnh có quyền cao hơn.
- Che secret khỏi log, artifact và báo cáo.
- Ghi lại người kích hoạt, commit, runner và môi trường.
- Có giới hạn tài nguyên và timeout để job không chiếm runner vô hạn.

Các kiểm tra bảo mật cơ bản nên xuất hiện sớm, nhưng cách chạy phải phù hợp với quyền của pipeline. Không cấp quyền rộng cho một bước quét chỉ vì muốn nhận kết quả sớm.

## 12. Đo lường chất lượng phản hồi sớm

Đừng chỉ đo tổng thời gian pipeline. Cần xem thời gian người phát triển nhận được tín hiệu có thể hành động và chất lượng của tín hiệu đó.

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Thời gian phản hồi đầu tiên | Từ lúc gửi thay đổi đến kết quả kiểm tra hữu ích đầu tiên | Đánh giá độ nhanh của vòng lặp |
| Thời gian hoàn tất gate sớm | Thời gian đến khi có quyết định pass/fail của các bước bắt buộc đầu tiên | Tìm bước gây chậm |
| Tỷ lệ lỗi được phát hiện sớm | Phần lỗi được tìm thấy trước tích hợp hoặc release | Đánh giá giá trị của lớp kiểm tra sớm |
| Tỷ lệ flaky | Phần lần chạy không ổn định trong điều kiện không đổi | Đánh giá niềm tin vào pipeline |
| Tỷ lệ job thất bại do hạ tầng | Lần chạy lỗi vì runner, mạng hoặc dịch vụ phụ thuộc | Phân biệt vấn đề môi trường |
| Thời gian điều tra | Từ khi có lỗi đến khi xác định được nguyên nhân | Đánh giá chất lượng báo cáo và log |
| Tỷ lệ gate bị override | Số lần bỏ qua điều kiện bắt buộc theo ngoại lệ | Tìm quy tắc không phù hợp hoặc áp lực quy trình |
| Chi phí runner trên thay đổi | Tài nguyên sử dụng cho mỗi commit hoặc pull request | Cân bằng tốc độ và chi phí |

Cần thống nhất cách tính và phạm vi. Ví dụ, “phản hồi đầu tiên” có thể là lint hoàn tất, nhưng chưa chắc là tín hiệu đủ để quyết định merge. Nên theo dõi riêng thời gian đến tín hiệu đầu tiên và thời gian đến quyết định gate.

Không dùng chỉ số để thúc đẩy nhóm giảm kiểm tra cần thiết. Nếu pipeline chậm, tìm nguyên nhân ở test, runner, cache, dữ liệu, phụ thuộc và cấu trúc job trước khi loại bỏ gate quan trọng.

## 13. Ví dụ: đặt kiểm tra sớm cho dịch vụ đặt hàng

Giả sử nhóm phát triển thay đổi quy tắc áp dụng mã giảm giá trong dịch vụ đặt hàng. Một pipeline trước đây chỉ chạy toàn bộ kiểm thử sau khi merge, mất nhiều thời gian và thường phát hiện lỗi tính toán ở giai đoạn tích hợp.

Nhóm thiết kế lại vòng phản hồi:

1. Khi lập trình, formatter và lint chạy trong IDE.
2. Trước commit, chạy unit test cho bộ tính giá và kiểm tra secret.
3. Khi mở pull request, CI chạy lint, type check, unit test và contract test của API đặt hàng.
4. Nếu các gate sớm đạt, pipeline build artifact và chạy test tích hợp với database cùng sandbox thanh toán.
5. Sau triển khai staging, smoke test xác minh tạo đơn, áp dụng mã và tổng tiền.
6. Bộ end-to-end rộng, kiểm thử tải và kiểm tra bảo mật chuyên sâu chạy theo lịch hoặc trước release candidate.

Một test đơn vị xác minh các trường hợp: mã hợp lệ, hết hạn, vượt giới hạn sử dụng, không áp dụng cho sản phẩm bị loại trừ và giá trị giảm tối đa. Contract test xác minh schema response không thay đổi ngoài dự kiến. Integration test xác minh cập nhật tổng tiền và lưu đơn hàng nhất quán.

Nếu unit test phát hiện tổng tiền sai, pipeline dừng trước khi build artifact và triển khai môi trường. Người viết nhận được tên test, dữ liệu đầu vào và kết quả mong đợi ngay trên pull request. Nếu contract test thất bại vì thay đổi trường response, nhóm phải xem xét consumer trước khi tích hợp.

Sau một thời gian, nhóm so sánh thời gian phản hồi đầu tiên, số lỗi tính giá được phát hiện trước merge, tỷ lệ flaky và chi phí runner với baseline. Nếu gate sớm đáng tin và giúp phát hiện lỗi trong phạm vi mục tiêu, nhóm có thể áp dụng mô hình tương tự cho các dịch vụ khác.

## 14. Quản lý ngoại lệ và thay đổi trong bộ kiểm tra sớm

Có lúc một gate không thể chạy do công cụ gián đoạn, test bị flaky hoặc thay đổi kiến trúc khiến kiểm tra cũ không còn phù hợp. Không nên bỏ qua gate âm thầm.

Một ngoại lệ cần có:

- Gate hoặc test bị ảnh hưởng.
- Commit, pull request và phạm vi áp dụng.
- Lý do không thể đáp ứng điều kiện.
- Rủi ro còn lại và kiểm tra thay thế.
- Người có thẩm quyền phê duyệt.
- Thời hạn hoặc điều kiện hết hiệu lực.
- Chủ sở hữu khắc phục và bằng chứng đóng.

Nếu gate bảo vệ rủi ro nghiêm trọng, ngoại lệ cần được xem xét ở cấp có thẩm quyền tương ứng. Một lỗi runner tạm thời có thể được xử lý bằng runner khác hoặc chạy lại; không nên chuyển thành pass giả. Một test flaky có thể được quarantine có thời hạn, nhưng cần giữ phần kiểm soát rủi ro khác và theo dõi sửa lỗi.

Khi yêu cầu hoặc kiến trúc thay đổi, cập nhật tập test, ngưỡng và phụ thuộc. Xóa một kiểm tra vì nó thường fail có thể làm mất khả năng phát hiện lỗi; trước khi loại bỏ, xác định vấn đề nó từng bảo vệ và phương án thay thế.

## 15. Quy trình thiết kế vòng phản hồi nhanh

Có thể áp dụng quy trình sau khi tổ chức CI/CD:

1. **Lập danh mục rủi ro và lỗi thường gặp:** xác định vấn đề nào cần được phát hiện trước tích hợp.
2. **Chọn phép kiểm tra phù hợp:** ưu tiên kiểm tra nhanh, rõ và ổn định cho giai đoạn sớm.
3. **Xác định phụ thuộc:** phân biệt bước có thể chạy song song và bước phải chờ artifact hoặc môi trường.
4. **Định nghĩa gate:** ghi rõ blocking, informational, ngưỡng và ngoại lệ.
5. **Tích hợp tại đúng điểm:** local, pre-commit, pull request, sau merge hoặc sau deploy.
6. **Tối ưu độ tin cậy:** cô lập dữ liệu, giảm thời gian khởi tạo và xử lý flaky test.
7. **Thiết kế kết quả dễ hành động:** hiển thị lỗi, log, commit và hướng dẫn sửa.
8. **Bảo vệ pipeline:** giới hạn secret, quyền, tài nguyên và phạm vi tác động.
9. **Đo lường:** theo dõi thời gian phản hồi, giá trị phát hiện, độ ổn định và chi phí.
10. **Cải tiến theo dữ liệu:** điều chỉnh thứ tự, phạm vi và gate khi có bằng chứng.

~~~mermaid
flowchart TD
    A["Thay đổi được tạo"] --> B["Kiểm tra local / pre-commit"]
    B --> C["Pull request: validate, lint, type"]
    C --> D{"Gate cơ bản đạt?"}
    D -->|Không| E["Phản hồi lỗi và sửa ngay"]
    E --> B
    D -->|Có| F["Unit, contract và component test"]
    F --> G{"Gate sớm đạt?"}
    G -->|Không| E
    G -->|Có| H["Build artifact"]
    H --> I["Deploy môi trường kiểm thử"]
    I --> J["Smoke và integration test"]
    J --> K["End-to-end, hiệu năng, bảo mật chuyên sâu"]
    K --> L["Tổng hợp bằng chứng và quyết định release"]
~~~

## 16. Checklist đặt kiểm tra phản hồi nhanh vào giai đoạn sớm

Trước khi áp dụng hoặc điều chỉnh pipeline, hãy kiểm tra:

- Các lỗi phổ biến và rủi ro cần phát hiện sớm đã được xác định chưa?
- Mỗi kiểm tra có mục đích, phạm vi và kết quả mong đợi rõ ràng không?
- Kiểm tra nhanh và ổn định đã được đặt ở local, pre-commit hoặc pull request phù hợp chưa?
- Các bước có phụ thuộc đã được sắp xếp đúng thứ tự chưa?
- Các bước độc lập có thể chạy song song mà không tranh chấp dữ liệu hoặc tài nguyên không?
- Gate blocking và informational có được phân biệt, công bố và quản lý không?
- Khi gate fail, người phát triển có biết nguyên nhân và cách xử lý không?
- Kết quả có gắn với commit, build và môi trường cụ thể không?
- Flaky test, lỗi môi trường và lỗi sản phẩm có được phân loại riêng không?
- Cache, runner và dependency có được quản lý an toàn và nhất quán không?
- Pipeline có giới hạn secret, quyền truy cập và tác động của test không?
- Ngoại lệ có người phê duyệt, lý do và thời hạn không?
- Các kiểm tra dài hoặc chuyên sâu vẫn có vị trí phù hợp trước release không?
- Nhóm có đo thời gian phản hồi, giá trị phát hiện, độ ổn định và chi phí không?

Đặt các kiểm tra phản hồi nhanh vào giai đoạn sớm giúp lỗi được phát hiện khi chi phí sửa còn thấp và người tạo thay đổi có thể hành động ngay. Để đạt hiệu quả, nhóm cần chọn phép kiểm tra dựa trên rủi ro, sắp xếp theo thời gian và phụ thuộc, giữ kết quả ổn định, hiển thị thông tin hữu ích và duy trì các lớp xác minh sâu hơn ở giai đoạn thích hợp. Một pipeline tốt không chỉ chạy nhanh; nó cung cấp tín hiệu đáng tin để quyết định thay đổi nào có thể đi tiếp.

