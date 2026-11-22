# Xác minh migration, cấu hình và khả năng tương thích khi triển khai

**Chương:** Phát hành và vận hành  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Một bản phát hành có thể vượt qua unit test, integration test và kiểm thử hồi quy nhưng vẫn gây sự cố khi triển khai. Nguyên nhân thường nằm ở những điều kiện chỉ xuất hiện khi phiên bản ứng dụng mới gặp schema dữ liệu hiện có, cấu hình của môi trường đích, dịch vụ phụ thuộc hoặc các phiên bản ứng dụng đang chạy song song. Migration thiếu an toàn có thể làm mất dữ liệu; cấu hình sai có thể khiến dịch vụ kết nối nhầm endpoint; thay đổi hợp đồng không tương thích có thể làm hỏng consumer chưa được cập nhật.

Xác minh migration, cấu hình và khả năng tương thích là hoạt động kiểm thử có chủ đích trước, trong và sau triển khai. Nhóm cần chứng minh rằng dữ liệu có thể chuyển đổi an toàn, ứng dụng nhận đúng cấu hình, phiên bản mới và cũ có thể phối hợp trong giai đoạn chuyển tiếp, và hệ thống có phương án phục hồi phù hợp khi triển khai không đạt yêu cầu.

Bài học này trình bày cách phân tích rủi ro migration, thiết kế thay đổi schema theo từng giai đoạn, kiểm tra cấu hình và secret, xác minh tương thích giữa phiên bản ứng dụng và dữ liệu, lựa chọn chiến lược triển khai, kiểm tra sau triển khai và chuẩn bị rollback hoặc roll-forward. Nội dung nhấn mạnh bằng chứng kiểm thử và các quyết định cần được đưa ra trước khi phát hành.

Sau bài học, người học có thể:

- Nhận diện rủi ro khi thay đổi schema, dữ liệu, cấu hình và hợp đồng tích hợp.
- Thiết kế migration có thể kiểm tra, quan sát và phục hồi.
- Xác minh khả năng tương thích giữa phiên bản ứng dụng cũ, mới và schema trong giai đoạn triển khai.
- Kiểm tra cấu hình môi trường, feature flag, secret và quyền truy cập.
- Xây dựng ma trận kiểm thử cho rolling, blue-green hoặc canary deployment.
- Phân biệt rollback ứng dụng với rollback dữ liệu và lựa chọn roll-forward khi cần.
- Thiết kế kiểm tra trước/sau triển khai, tiêu chí dừng và điều kiện chấp nhận phát hành.
- Ghi nhận bằng chứng, rủi ro còn lại và quyết định vận hành có thể truy vết.

## 1. Vì sao cần xác minh migration, cấu hình và tương thích?

Triển khai là thời điểm nhiều thành phần thay đổi hoặc tương tác đồng thời. Phiên bản mới có thể chạy cùng phiên bản cũ trong một khoảng thời gian; database có thể đang ở schema cũ hoặc đã được migration một phần; cấu hình có thể được cập nhật trước hoặc sau khi ứng dụng khởi động; consumer và provider có thể được phát hành theo lịch khác nhau.

Những tình huống này tạo ra rủi ro khác với lỗi logic đơn lẻ:

- Ứng dụng mới đọc trường dữ liệu chưa tồn tại hoặc diễn giải dữ liệu theo quy tắc mới.
- Migration làm khóa bảng lâu, vượt cửa sổ triển khai hoặc gây tải lớn.
- Backfill chỉ cập nhật một phần dữ liệu, khiến hai phiên bản ứng dụng nhìn thấy trạng thái khác nhau.
- Cấu hình thiếu hoặc sai khiến ứng dụng kết nối nhầm môi trường, dịch vụ hoặc tenant.
- Secret được xoay vòng không đồng bộ giữa ứng dụng và nhà cung cấp.
- API hoặc event schema bị thay đổi trước khi tất cả consumer sẵn sàng.
- Rollback ứng dụng không tương thích với schema mới hoặc dữ liệu đã chuyển đổi.
- Triển khai thành công về mặt kỹ thuật nhưng hành trình nghiệp vụ vẫn lỗi.

Kiểm thử trước triển khai cần bao phủ cả trạng thái trung gian, không chỉ trạng thái cuối cùng sau khi mọi thành phần đã được cập nhật. Kiểm thử sau triển khai cần xác minh hành vi thực tế trên môi trường đích và có khả năng phát hiện sớm sai lệch.

## 2. Lập bản đồ thay đổi và rủi ro triển khai

Trước khi chọn test, hãy xác định những gì thay đổi và những thành phần có thể bị ảnh hưởng.

### 2.1. Phân loại thay đổi

| Loại thay đổi | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|
| Schema database | Thêm cột, đổi kiểu, index, constraint, bảng | Tương thích phiên bản, lock, hiệu năng truy vấn, tính toàn vẹn |
| Dữ liệu | Backfill, chuẩn hóa, chuyển mã, hợp nhất bản ghi | Mất dữ liệu, sai mapping, trùng lặp, tính đầy đủ |
| Cấu hình | Endpoint, timeout, pool size, feature flag | Sai môi trường, giá trị mặc định, cấu hình thiếu hoặc lệch |
| Secret và danh tính | Xoay API key, chứng thư, quyền service account | Xác thực thất bại, quyền quá rộng, thời gian chuyển tiếp |
| API/event | Thêm hoặc đổi trường, mã trạng thái, version | Consumer cũ không tương thích, sự kiện không đọc được |
| Runtime/hạ tầng | JDK, image, broker, database version | Khác biệt runtime, giao thức, tài nguyên và vận hành |
| Chiến lược triển khai | Rolling, blue-green, canary | Phiên bản cùng tồn tại, định tuyến, rollback và quan sát |

### 2.2. Xác định trạng thái trước, trong và sau triển khai

Với mỗi thay đổi, ghi rõ:

- Trạng thái hiện tại của ứng dụng, schema, dữ liệu và cấu hình.
- Trạng thái mong muốn sau triển khai.
- Các trạng thái trung gian có thể xuất hiện.
- Phiên bản nào có thể chạy đồng thời.
- Thứ tự triển khai và điều kiện phụ thuộc.
- Những thao tác không thể đảo ngược hoặc có tác dụng phụ.
- Cách xác minh và phục hồi nếu từng bước thất bại.

Ví dụ, khi thêm trường `delivery_zone` vào bảng đơn hàng, trạng thái trung gian có thể là schema đã có cột nhưng ứng dụng cũ chưa ghi trường này; backfill đang chạy; ứng dụng mới đã đọc trường nhưng dữ liệu cũ chưa hoàn chỉnh. Test chỉ trên database đã backfill xong sẽ bỏ qua các trạng thái quan trọng đó.

### 2.3. Phân tích tác động và chủ sở hữu

Liên kết thay đổi với service, bảng dữ liệu, API, event, job nền, báo cáo, consumer và nhóm vận hành. Mỗi thay đổi rủi ro cao cần có chủ sở hữu kỹ thuật và người quyết định phát hành. Nếu không xác định được consumer hoặc phụ thuộc, mở rộng đánh giá trước khi phê duyệt.

## 3. Thiết kế migration database an toàn

Migration là thay đổi có kiểm soát đối với schema hoặc dữ liệu. Một migration tốt cần có thể kiểm tra trước, thực thi theo thứ tự, quan sát tiến độ và có phương án xử lý khi thất bại.

### 3.1. Phân biệt schema migration và data migration

- **Schema migration:** thay đổi cấu trúc như bảng, cột, kiểu dữ liệu, index, constraint hoặc view.
- **Data migration:** chuyển đổi giá trị, chuẩn hóa dữ liệu, backfill trường mới, hợp nhất hoặc phân tách bản ghi.

Hai loại có thể được triển khai cùng nhau nhưng có rủi ro khác nhau. Thêm một cột nullable có thể nhanh; cập nhật hàng triệu bản ghi hoặc tạo index trên bảng lớn có thể gây tải, lock hoặc kéo dài thời gian.

### 3.2. Ưu tiên thay đổi cộng thêm trước (expand-contract)

Với hệ thống cần triển khai liên tục hoặc có nhiều phiên bản cùng chạy, cách tiếp cận expand-contract giúp giảm phụ thuộc vào một lần phát hành nguyên khối.

1. **Expand:** thêm cấu trúc mới theo cách tương thích ngược, ví dụ thêm cột nullable hoặc trường API mới tùy chọn.
2. **Deploy compatible code:** phát hành ứng dụng có thể hoạt động với cả cấu trúc cũ và mới.
3. **Backfill:** chuyển dữ liệu cũ theo lô, có thể chạy lại an toàn và theo dõi tiến độ.
4. **Switch reads/writes:** chuyển dần ứng dụng sang dùng cấu trúc mới; xác minh dữ liệu và hành vi.
5. **Enforce:** thêm constraint hoặc loại bỏ đường ghi cũ sau khi xác nhận mọi consumer đã chuyển.
6. **Contract:** xóa cột, endpoint hoặc logic cũ ở một đợt triển khai sau khi không còn phiên bản nào cần dùng.

Không phải mọi thay đổi đều cần đủ sáu bước. Nhưng với thay đổi phá vỡ tương thích, cần chủ động chia giai đoạn và xác minh từng trạng thái.

### 3.3. Tránh đổi tên hoặc xóa trường ngay trong một lần phát hành

Nếu ứng dụng cũ vẫn đọc `customer_name` và ứng dụng mới chuyển sang `full_name`, việc đổi tên hoặc xóa cột ngay có thể làm phiên bản cũ lỗi trong lúc rolling deployment.

Một trình tự an toàn hơn:

- Thêm `full_name` mà vẫn giữ `customer_name`.
- Phát hành ứng dụng có thể đọc dữ liệu cũ và mới, đồng thời ghi theo quy tắc chuyển tiếp.
- Backfill `full_name` từ dữ liệu cũ và xác minh đầy đủ.
- Chuyển consumer sang trường mới.
- Theo dõi việc đọc/ghi trường cũ; chỉ loại bỏ sau khi mọi consumer đã ngừng dùng.

### 3.4. Thiết kế migration có thể chạy lại an toàn

Migration hoặc backfill có thể bị gián đoạn giữa chừng. Cần xác định hành vi khi chạy lại:

- Kiểm tra trạng thái hiện tại trước khi thay đổi.
- Dùng điều kiện cập nhật để tránh ghi đè dữ liệu đã được xử lý đúng.
- Chia batch có giới hạn và lưu checkpoint nếu phù hợp.
- Tránh tạo bản ghi trùng khi job chạy lại.
- Xác minh số lượng và tính nhất quán sau mỗi batch.
- Ghi nhận lỗi theo bản ghi hoặc batch để có thể tiếp tục có kiểm soát.

Idempotency không có nghĩa là bỏ qua mọi lỗi. Nếu dữ liệu đầu vào không hợp lệ, migration cần dừng hoặc đưa bản ghi vào danh sách xử lý riêng, không âm thầm coi như đã hoàn tất.

### 3.5. Quản lý lock, thời gian và tải

Migration có thể gây lock bảng, tăng I/O, làm chậm truy vấn hoặc ảnh hưởng replica. Cần kiểm tra:

- Thời gian chạy trên dữ liệu có kích thước đại diện.
- Loại lock và thời gian giữ lock.
- Tác động đến truy vấn đang chạy.
- Kích thước batch và khoảng nghỉ giữa các batch.
- Dung lượng đĩa, transaction log và replication lag.
- Khả năng tạm dừng, tiếp tục hoặc hủy an toàn.

Không giả định migration chạy nhanh trên database nhỏ sẽ có cùng hành vi trên dữ liệu production. Kiểm thử hiệu năng migration cần dùng dữ liệu tổng hợp có quy mô và phân bố gần thực tế, trong môi trường được phê duyệt.

## 4. Kiểm thử migration trước khi triển khai

Migration cần được kiểm thử trên nhiều trạng thái dữ liệu và phiên bản schema. Chỉ chạy migration trên database mới, rỗng thường không đủ.

### 4.1. Kiểm tra đường cài đặt mới

Khởi tạo database từ đầu, áp dụng toàn bộ migration theo thứ tự và xác minh:

- Schema cuối cùng đúng như mong đợi.
- Constraint, index, default, trigger và view cần thiết tồn tại.
- Seed hoặc dữ liệu khởi tạo có cấu trúc hợp lệ.
- Ứng dụng khởi động và thực hiện các thao tác cơ bản.

### 4.2. Kiểm tra nâng cấp từ các phiên bản được hỗ trợ

Tạo database từ một hoặc nhiều schema cũ đại diện, nạp dữ liệu có các trạng thái quan trọng rồi chạy chuỗi migration. Kiểm tra các đường nâng cấp mà sản phẩm cam kết hỗ trợ, không chỉ phiên bản gần nhất nếu khách hàng có thể nâng cấp từ xa hơn.

### 4.3. Kiểm tra dữ liệu biên và bất thường

Chuẩn bị dữ liệu có:

- Giá trị null, rỗng hoặc thiếu.
- Chuỗi dài, ký tự Unicode và dữ liệu không theo định dạng chuẩn.
- Giá trị trùng hoặc quan hệ tham chiếu không hợp lệ.
- Số âm, số lớn, phần thập phân và giá trị sát giới hạn kiểu dữ liệu.
- Bản ghi cũ không còn theo quy tắc hiện tại.
- Bản ghi được tạo hoặc cập nhật đồng thời trong lúc backfill.

Không tự ý sửa hoặc loại bỏ dữ liệu bất thường chỉ để migration đạt. Cần xác định quy tắc chuyển đổi, báo cáo ngoại lệ và được chủ sở hữu dữ liệu phê duyệt.

### 4.4. Kiểm tra tính đầy đủ và chính xác

Sau migration, xác minh:

- Số bản ghi trước và sau theo quy tắc chuyển đổi.
- Tổng hợp số lượng theo trạng thái hoặc nhóm quan trọng.
- Quan hệ khóa ngoại và tính duy nhất.
- Giá trị được chuyển đổi theo expected mapping độc lập.
- Không mất bản ghi hoặc tạo bản ghi trùng ngoài dự kiến.
- Các ngoại lệ được ghi nhận và có cách xử lý.

Với dữ liệu lớn, có thể dùng checksum, aggregate hoặc đối chiếu theo partition/batch. Cần hiểu giới hạn của phép kiểm tra: tổng số bản ghi bằng nhau không chứng minh từng giá trị đều đúng.

### 4.5. Kiểm tra gián đoạn và chạy lại

Thử dừng migration ở các điểm kiểm soát được, khởi động lại và xác minh:

- Không có trạng thái dữ liệu không nhất quán ngoài quy định.
- Batch đã hoàn tất không bị áp dụng sai lần nữa.
- Batch chưa hoàn tất có thể tiếp tục.
- Checkpoint và log phản ánh đúng tiến độ.
- Job không để lại lock hoặc transaction treo ngoài dự kiến.

Chỉ mô phỏng gián đoạn trong môi trường kiểm thử phù hợp. Không thử thao tác phá hoại trên dữ liệu thật nếu chưa có kế hoạch và phê duyệt riêng.

## 5. Xác minh tương thích giữa ứng dụng và schema

Trong rolling deployment, ứng dụng cũ và mới có thể cùng truy cập một database. Do đó cần kiểm tra ma trận phiên bản, không chỉ một cặp ứng dụng mới và schema mới.

### 5.1. Ma trận tương thích

Với thay đổi schema, cân nhắc các tổ hợp:

| Ứng dụng | Schema cũ | Schema mới đang expand | Schema sau contract |
|---|---|---|---|
| Phiên bản cũ | Trạng thái hiện tại cần hoạt động | Phải tiếp tục hoạt động nếu rolling yêu cầu | Không được triển khai nếu còn phụ thuộc trường đã xóa |
| Phiên bản chuyển tiếp | Có thể cần hỗ trợ để triển khai theo thứ tự | Trạng thái mục tiêu thường được xác minh | Chỉ tương thích nếu code đã ngừng dùng cấu trúc cũ |
| Phiên bản mới | Có thể cần tương thích trong giai đoạn chuyển tiếp | Phải hoạt động | Hoạt động sau khi contract hoàn tất |

Ma trận thực tế phụ thuộc kiến trúc và chiến lược phát hành. Hãy xác định tổ hợp nào có thể tồn tại đồng thời và kiểm tra chúng trên môi trường phù hợp.

### 5.2. Tương thích ngược và tương thích xuôi

- **Tương thích ngược:** phiên bản mới có thể làm việc với dữ liệu hoặc hợp đồng cũ trong phạm vi cần hỗ trợ.
- **Tương thích xuôi:** phiên bản cũ có thể tiếp tục hoạt động khi gặp dữ liệu hoặc hợp đồng mới theo quy tắc được thiết kế.

Không phải mọi hệ thống đều cần hỗ trợ cả hai hướng vô thời hạn. Nhưng trong giai đoạn chuyển tiếp, cần biết hướng nào bắt buộc và có bằng chứng.

### 5.3. Kiểm tra hành vi đọc/ghi kép

Nếu phiên bản chuyển tiếp ghi cả trường cũ và mới, cần xác minh:

- Hai giá trị được cập nhật nhất quán.
- Thất bại giữa hai thao tác được xử lý rõ.
- Không có ghi đè từ phiên bản cũ làm mất dữ liệu mới.
- Backfill không ghi đè thay đổi mới hơn.
- Có cách đối chiếu và phát hiện sai lệch.

Dual-write có thể tạo trạng thái không đồng nhất nếu hai thao tác không cùng transaction hoặc một bên thất bại. Cần thiết kế thứ tự, retry, reconciliation và quan sát phù hợp.

### 5.4. Xác minh consumer còn dùng cấu trúc cũ

Trước khi xóa cột hoặc endpoint cũ, cần có bằng chứng rằng:

- Không còn phiên bản ứng dụng đang chạy cần cấu trúc cũ.
- Job nền, báo cáo, script vận hành và công cụ hỗ trợ đã được cập nhật.
- Consumer bên ngoài đã chuyển hoặc có thời hạn hỗ trợ rõ.
- Log/metric truy cập cấu trúc cũ không còn hoạt động trong khoảng quan sát phù hợp.

Không nên chỉ dựa vào tìm kiếm mã nguồn của một repository nếu có consumer bên ngoài hoặc job được triển khai độc lập.

## 6. Xác minh cấu hình triển khai

Cấu hình ảnh hưởng trực tiếp đến hành vi ứng dụng. Cùng một artifact có thể hoạt động khác nhau khi endpoint, timeout, pool size, feature flag hoặc profile thay đổi.

### 6.1. Phân loại cấu hình

- **Cấu hình môi trường:** endpoint, tên database, broker, region hoặc storage bucket.
- **Cấu hình hành vi:** timeout, retry, batch size, giới hạn kết nối và mức song song.
- **Feature flag:** bật/tắt chức năng hoặc chuyển luồng xử lý.
- **Cấu hình bảo mật:** issuer, audience, certificate reference, quyền và chính sách xác thực.
- **Secret:** password, token, API key, private key hoặc credential.
- **Cấu hình vận hành:** log level, health check, sampling, alert và telemetry.

### 6.2. Xác minh cấu hình bắt buộc và giá trị mặc định

Ứng dụng nên kiểm tra cấu hình bắt buộc khi khởi động hoặc trước khi dùng tính năng. Thiếu endpoint hoặc credential cần tạo lỗi rõ ràng, không âm thầm dùng giá trị mặc định có thể trỏ đến môi trường sai.

Kiểm tra:

- Tên biến hoặc key cấu hình đúng.
- Kiểu dữ liệu và phạm vi giá trị hợp lệ.
- Giá trị mặc định có an toàn không.
- Cấu hình trùng hoặc xung đột được xử lý thế nào.
- Cấu hình có được áp dụng đúng tiến trình và instance không.
- Lỗi validation có thông báo đủ rõ nhưng không tiết lộ secret.

### 6.3. Kiểm tra tính nhất quán giữa môi trường

Không phải mọi giá trị phải giống nhau giữa dev, test, staging và production. Endpoint, credential và tài nguyên thường khác nhau. Điều cần thống nhất là cấu trúc cấu hình, kiểu dữ liệu, quy tắc validation và các tham số có ảnh hưởng đến hành vi cần kiểm tra.

Nên quản lý cấu hình theo phiên bản hoặc có cơ chế ghi nhận snapshot đã làm sạch để biết instance đang chạy với cấu hình nào. Không đưa giá trị secret vào snapshot hoặc log.

### 6.4. Kiểm tra feature flag

Với mỗi flag quan trọng, xác định:

- Giá trị mặc định và giá trị ở từng môi trường.
- Ai có quyền thay đổi.
- Phạm vi áp dụng: toàn hệ thống, tenant, nhóm người dùng hay phần trăm lưu lượng.
- Hành vi khi flag không đọc được.
- Cách rollback bằng flag và giới hạn của biện pháp đó.
- Thời điểm loại bỏ flag sau khi chức năng ổn định.

Test cả hai nhánh khi chúng còn được hỗ trợ. Với flag thay đổi dữ liệu hoặc hợp đồng, cần kiểm tra tương thích giữa các phiên bản và trạng thái dữ liệu.

### 6.5. Kiểm tra secret và xoay vòng credential

Secret cần được cấp từ cơ chế quản lý phù hợp, không lưu trong repository hoặc image. Khi xoay vòng:

1. Cấp credential mới theo cơ chế được hỗ trợ.
2. Xác minh ứng dụng có thể sử dụng credential mới.
3. Nếu cần chuyển tiếp, duy trì thời gian hai credential cùng hợp lệ.
4. Cập nhật các instance và job liên quan.
5. Xác minh không còn sử dụng credential cũ.
6. Thu hồi credential cũ theo quy trình.

Test cần kiểm tra lỗi xác thực, quyền tối thiểu và hành vi khi credential hết hạn. Không in secret hoặc payload xác thực trong log.

### 6.6. Phát hiện cấu hình lệch (configuration drift)

Cấu hình thực tế có thể khác cấu hình được quản lý do chỉnh sửa thủ công, cập nhật không đồng bộ hoặc secret reference cũ. Cần so sánh cấu hình đã khai báo với cấu hình instance đang chạy, nhưng phải loại bỏ giá trị nhạy cảm. Mọi thay đổi ngoài quy trình cần được điều tra và đưa về nguồn quản lý chuẩn.

## 7. Kiểm tra tương thích API, event và dữ liệu trao đổi

Tương thích không chỉ giới hạn ở database. Các service có thể được phát hành độc lập nên hợp đồng giao tiếp cần hỗ trợ giai đoạn chuyển tiếp.

### 7.1. Thêm trường và thay đổi trường

Thêm trường tùy chọn thường ít rủi ro hơn đổi tên hoặc xóa trường, nhưng vẫn cần kiểm tra consumer có xử lý trường không biết hay không. Một số consumer có thể từ chối payload chứa trường mới nếu schema hoặc parser quá chặt.

Kiểm tra:

- Trường mới có giá trị mặc định hoặc quy tắc khi thiếu không?
- Consumer cũ có bỏ qua trường lạ an toàn không?
- Provider có tiếp tục trả trường cũ trong thời gian chuyển tiếp không?
- Kiểu dữ liệu, format và nullability có thay đổi không?
- Enum mới có làm consumer cũ lỗi không?

### 7.2. Event và message schema

Với event bất đồng bộ, kiểm tra producer mới với consumer cũ và producer cũ với consumer mới nếu hai phiên bản có thể cùng tồn tại. Xem xét thứ tự, lặp, replay, dead-letter và khả năng đọc message tồn đọng sau triển khai.

Không xóa hoặc đổi nghĩa trường event khi message cũ vẫn còn trong queue hoặc có thể được replay. Cần có versioning và chính sách tương thích rõ.

### 7.3. Contract test và consumer verification

Contract test giúp xác minh provider và consumer thống nhất về request, response, schema và lỗi. Chạy contract verification trước phát hành khi có thay đổi hợp đồng. Tuy nhiên, contract test không tự chứng minh toàn bộ hành vi runtime, tải hoặc cấu hình mạng; vẫn cần integration test phù hợp.

### 7.4. Phiên bản API và thời gian ngừng hỗ trợ

Nếu cần breaking change, dùng version mới hoặc giai đoạn chuyển tiếp theo chính sách sản phẩm. Thông báo consumer, theo dõi mức sử dụng phiên bản cũ và chỉ loại bỏ khi đã đáp ứng điều kiện ngừng hỗ trợ.

## 8. Kiểm thử các chiến lược triển khai

Chiến lược triển khai quyết định những phiên bản nào cùng chạy và cách lưu lượng được chuyển đổi. Test cần mô phỏng đúng trình tự và trạng thái trung gian.

### 8.1. Rolling deployment

Rolling deployment thay thế từng nhóm instance. Trong một khoảng thời gian, phiên bản cũ và mới cùng phục vụ request.

Kiểm tra:

- Hai phiên bản có tương thích với schema và hợp đồng trong giai đoạn đồng thời không?
- Request có thể đi đến bất kỳ phiên bản nào mà vẫn xử lý nhất quán không?
- Session, cache và dữ liệu chia sẻ có tương thích không?
- Instance mới có readiness check trước khi nhận traffic không?
- Instance cũ có được drain request và kết thúc an toàn không?
- Nếu rollout dừng giữa chừng, hệ thống có trạng thái vận hành rõ không?

### 8.2. Blue-green deployment

Blue-green duy trì hai môi trường hoặc nhóm instance: môi trường đang phục vụ và môi trường mới được chuẩn bị. Khi xác minh đạt, lưu lượng được chuyển sang nhóm mới.

Kiểm tra:

- Môi trường mới có cấu hình, secret và kết nối đúng không?
- Dữ liệu hoặc schema có được chia sẻ và tương thích không?
- Health check và smoke test có chạy trước khi chuyển traffic không?
- Việc chuyển traffic có giữ session và xử lý request đang chạy không?
- Có thể chuyển traffic về môi trường cũ không?
- Môi trường cũ có còn tương thích với dữ liệu đã được ghi bởi môi trường mới không?

Blue-green không tự làm cho rollback an toàn nếu phiên bản mới đã ghi dữ liệu mà phiên bản cũ không hiểu.

### 8.3. Canary deployment

Canary chuyển một phần lưu lượng hoặc nhóm người dùng sang phiên bản mới trước khi mở rộng.

Kiểm tra:

- Cách chọn nhóm canary và khả năng định tuyến đúng.
- Tỷ lệ lỗi, latency, throughput và chỉ số nghiệp vụ được theo dõi.
- Có thể phân biệt traffic của phiên bản mới và cũ không?
- Điều kiện mở rộng hoặc dừng rollout được xác định trước không?
- Có thể chuyển traffic về phiên bản ổn định khi vượt ngưỡng không?
- Dữ liệu được ghi bởi canary có tương thích với phiên bản cũ không?

Canary cần ngưỡng và khoảng quan sát đủ đại diện. Chuyển một tỷ lệ nhỏ traffic trong vài giây có thể không phát hiện lỗi chỉ xuất hiện ở chu kỳ nghiệp vụ dài.

### 8.4. So sánh chiến lược

| Chiến lược | Đặc điểm | Rủi ro cần kiểm tra |
|---|---|---|
| Rolling | Phiên bản cũ và mới cùng chạy trong quá trình thay instance | Tương thích chéo phiên bản, drain, readiness và trạng thái giữa chừng |
| Blue-green | Chuẩn bị nhóm mới rồi chuyển traffic | Đồng bộ dữ liệu, chuyển traffic, session và rollback |
| Canary | Chuyển dần một phần traffic | Định tuyến, chỉ số theo phiên bản, ngưỡng dừng và tác động dữ liệu |
| Recreate/downtime | Dừng phiên bản cũ rồi triển khai phiên bản mới | Thời gian gián đoạn, backup, khởi động và phục hồi |

Không có chiến lược tối ưu cho mọi hệ thống. Lựa chọn cần xét kiến trúc, yêu cầu sẵn sàng, khả năng tương thích dữ liệu và năng lực vận hành.

## 9. Rollback, roll-forward và phục hồi dữ liệu

Rollback ứng dụng và rollback dữ liệu là hai hoạt động khác nhau. Một bản triển khai có thể quay lại phiên bản code cũ nhưng không thể đơn giản đảo ngược migration hoặc dữ liệu đã được chuyển đổi.

### 9.1. Xác định khả năng đảo ngược

Với mỗi bước, phân loại:

- Có thể đảo ngược trực tiếp.
- Có thể khôi phục từ backup hoặc snapshot.
- Cần migration bù (compensating migration).
- Không thể đảo ngược hoàn toàn vì đã phát sinh tác dụng phụ hoặc dữ liệu mới.

Ghi rõ điều kiện và thời gian cần để phục hồi. Không coi việc có file migration `down` là bằng chứng rollback an toàn; thao tác đảo ngược có thể mất dữ liệu hoặc không thể khôi phục ý nghĩa nghiệp vụ.

### 9.2. Rollback ứng dụng

Trước khi quay về phiên bản cũ, xác minh:

- Schema hiện tại có còn tương thích với code cũ không?
- Dữ liệu mới đã được ghi theo format mà code cũ hiểu chưa?
- Event hoặc message mới có đang tồn tại không?
- Cấu hình và secret có còn phù hợp với phiên bản cũ không?
- Có cần chuyển traffic, dừng worker hoặc drain queue không?

Nếu không bảo đảm tương thích, rollback code có thể làm sự cố nặng hơn.

### 9.3. Roll-forward

Roll-forward là phát hành bản sửa tiếp theo để đưa hệ thống về trạng thái đúng. Đây có thể là lựa chọn an toàn hơn khi schema hoặc dữ liệu đã thay đổi theo cách không thể đảo ngược.

Kế hoạch roll-forward cần có:

- Bản sửa hoặc migration bù đã được chuẩn bị và kiểm thử.
- Điều kiện triển khai và thứ tự phụ thuộc.
- Cách xác minh dữ liệu và hành vi sau sửa.
- Tiêu chí dừng nếu bản sửa tiếp tục thất bại.
- Người chịu trách nhiệm và kênh điều phối.

### 9.4. Backup và restore

Nếu phục hồi dựa vào backup, cần kiểm tra khả năng khôi phục chứ không chỉ xác nhận job backup đã chạy. Xác minh:

- Backup có đúng phạm vi và thời điểm không?
- Có thể restore vào môi trường kiểm thử không?
- Dữ liệu sau restore có đầy đủ và nhất quán không?
- Thời gian restore có đáp ứng mục tiêu phục hồi không?
- Các thay đổi phát sinh sau điểm backup được xử lý thế nào?

Không thử restore phá hủy trên production như một phần kiểm thử thông thường. Dùng môi trường và quy trình diễn tập được phê duyệt.

### 9.5. Tiêu chí kích hoạt rollback

Đặt trước các điều kiện có thể đo được, ví dụ:

- Tỷ lệ lỗi vượt ngưỡng trong khoảng quan sát.
- Lỗi dữ liệu hoặc giao dịch nghiêm trọng.
- Health check hoặc dependency readiness thất bại.
- Canary có latency hoặc error rate vượt ngưỡng đã thống nhất.
- Migration không hoàn tất trong cửa sổ cho phép.
- Không thể xác minh tính toàn vẹn dữ liệu.

Ngưỡng phải phù hợp với hệ thống và được xác định trước, không đặt tùy ý khi sự cố đang xảy ra.

## 10. Kiểm tra trước triển khai

Pre-deployment validation giúp phát hiện điều kiện thiếu trước khi thay đổi môi trường đang phục vụ.

### 10.1. Xác minh artifact và nguồn gốc

- Đúng commit, build và phiên bản đã được phê duyệt.
- Artifact không bị thay đổi sau kiểm thử.
- Dependency và image đúng phiên bản.
- Chữ ký hoặc checksum được xác minh theo quy trình nếu có.
- Release notes và danh sách thay đổi khớp với artifact.

### 10.2. Xác minh migration

- Migration đã được review và chạy thử trên dữ liệu đại diện.
- Thứ tự migration đúng và không bỏ qua phiên bản trung gian cần thiết.
- Thời gian, lock và tài nguyên nằm trong giới hạn.
- Backfill có checkpoint, log và cách chạy lại.
- Kiểm tra dữ liệu sau migration được xác định.
- Backup/restore hoặc roll-forward plan đã được chuẩn bị theo rủi ro.

### 10.3. Xác minh cấu hình

- Cấu hình bắt buộc có đủ và hợp lệ.
- Endpoint trỏ đúng môi trường.
- Secret reference và quyền truy cập hoạt động.
- Feature flag có giá trị đúng và người sở hữu rõ.
- Timeout, retry, pool và giới hạn tài nguyên phù hợp.
- Không có cấu hình debug hoặc quyền rộng ngoài dự kiến.

### 10.4. Xác minh tương thích

- Phiên bản cũ và mới có thể cùng chạy theo chiến lược đã chọn.
- API/event/schema tương thích với consumer được hỗ trợ.
- Job nền và worker tương thích với dữ liệu mới.
- Migration không loại bỏ trường còn được dùng.
- Có test cho các trạng thái chuyển tiếp quan trọng.

### 10.5. Xác minh vận hành

- Health check, readiness và liveness được cấu hình.
- Log, metric, trace và alert có thể quan sát.
- Runbook và người trực phát hành đã sẵn sàng.
- Cửa sổ triển khai và phụ thuộc được xác nhận.
- Điều kiện dừng, rollback hoặc roll-forward được thống nhất.

## 11. Kiểm tra sau triển khai

Triển khai thành công không đồng nghĩa ứng dụng hoạt động đúng. Post-deployment validation cần xác minh cả sức khỏe kỹ thuật lẫn hành vi nghiệp vụ.

### 11.1. Health check và readiness

Kiểm tra tiến trình, kết nối database, broker và dịch vụ bắt buộc. Readiness cần phản ánh instance có thể phục vụ request; không chỉ kiểm tra process còn sống.

### 11.2. Smoke test sau triển khai

Chạy một tập kiểm tra ngắn nhưng đại diện:

- Đăng nhập hoặc xác thực cơ bản.
- Đọc/ghi một dữ liệu thử nghiệm an toàn.
- Gọi API quan trọng.
- Thực hiện luồng nghiệp vụ tối thiểu trong phạm vi cho phép.
- Kiểm tra kết nối phụ thuộc và trạng thái migration.

Smoke test cần tránh tác dụng phụ lên dữ liệu hoặc khách hàng thật. Nếu phải thực hiện thao tác có tác dụng phụ, dùng tài khoản và dữ liệu được thiết kế cho kiểm tra vận hành.

### 11.3. Xác minh dữ liệu sau migration

Kiểm tra số lượng, aggregate, constraint, bản ghi ngoại lệ và các luồng đọc/ghi của ứng dụng. Với backfill dài, theo dõi tiến độ và sai lệch theo batch cho đến khi hoàn tất.

### 11.4. Theo dõi chỉ số theo phiên bản

Quan sát:

- Error rate và loại lỗi.
- Latency theo percentile.
- Throughput và số request.
- Tỷ lệ timeout, retry và lỗi dependency.
- Tỷ lệ thành công của hành vi nghiệp vụ quan trọng.
- Số lượng bản ghi lỗi, message tồn đọng hoặc dead-letter.
- Trạng thái migration, backfill và replication lag.

Phân đoạn theo phiên bản, instance hoặc nhóm canary để phát hiện lỗi chỉ xuất hiện ở phiên bản mới.

### 11.5. Kiểm tra sau khi chuyển traffic

Với blue-green hoặc canary, xác minh traffic thực sự đi đến nhóm mong muốn, phiên bản cũ được drain đúng và không có request bị xử lý hai lần. Kiểm tra session, cache và dữ liệu ghi trong giai đoạn chuyển tiếp.

### 11.6. Kết thúc theo dõi tăng cường

Chỉ kết thúc giai đoạn theo dõi tăng cường khi các tiêu chí ổn định đã đạt trong khoảng quan sát phù hợp, migration hoàn tất, cảnh báo không có bất thường và người chịu trách nhiệm xác nhận. Không kết thúc chỉ vì deployment job báo thành công.

## 12. Ví dụ migration thay đổi cấu trúc địa chỉ giao hàng

Giả sử hệ thống hiện lưu `shipping_address` dưới dạng một chuỗi. Phiên bản mới cần các trường `street`, `ward_code` và `province_code` để hỗ trợ định tuyến.

### 12.1. Phân tích rủi ro

- Ứng dụng cũ vẫn đọc và ghi `shipping_address`.
- Ứng dụng mới cần các trường tách riêng.
- Dữ liệu cũ có thể thiếu mã phường hoặc tỉnh.
- Backfill có thể không phân tích được một số địa chỉ tự do.
- Job báo cáo và dịch vụ vận chuyển có thể còn đọc trường cũ.
- Rollback code mới cần giữ khả năng đọc dữ liệu đã chuyển đổi.

### 12.2. Trình tự thay đổi

1. Thêm các cột mới ở trạng thái cho phép null.
2. Triển khai code có thể đọc dữ liệu mới nếu có, nếu không thì dùng trường cũ theo quy tắc chuyển tiếp.
3. Ghi dữ liệu mới theo cơ chế dual-write hoặc một đường ghi đã được thiết kế và kiểm tra.
4. Chạy backfill theo batch cho dữ liệu cũ.
5. Đối chiếu số bản ghi, dữ liệu phân tích được và danh sách ngoại lệ.
6. Chuyển consumer sang các trường mới và theo dõi việc đọc trường cũ.
7. Sau thời gian hỗ trợ và xác minh không còn consumer cũ, áp dụng constraint phù hợp.
8. Loại bỏ trường cũ ở một đợt triển khai riêng.

### 12.3. Các test cần có

- Migration từ database rỗng và từ schema cũ.
- Dữ liệu địa chỉ đầy đủ, thiếu, sai định dạng và Unicode.
- Backfill chạy lại sau khi bị dừng giữa batch.
- Ứng dụng cũ hoạt động khi cột mới đã được thêm.
- Ứng dụng mới đọc dữ liệu cũ và mới theo quy tắc chuyển tiếp.
- Dual-write không tạo sai lệch khi một thao tác thất bại.
- Consumer vận chuyển và báo cáo đọc đúng trường.
- Rollback code trong giai đoạn schema mở rộng.
- Contract migration sau khi không còn consumer trường cũ.

### 12.4. Tiêu chí hoàn tất

Migration chỉ được coi là hoàn tất khi dữ liệu đã được xử lý hoặc ngoại lệ được chấp nhận có chủ đích, các consumer được xác minh, chỉ số vận hành ổn định và điều kiện loại bỏ cấu trúc cũ được đáp ứng. Không chỉ dựa vào việc script backfill kết thúc với exit code thành công.

## 13. Ví dụ kiểm tra cấu hình và xoay vòng secret

Giả sử dịch vụ đơn hàng chuyển từ API đối tác `partner-v1` sang `partner-v2` và nhà cung cấp yêu cầu xoay API key.

### 13.1. Rủi ro

- Endpoint mới có thể sai môi trường.
- API key mới chưa được cấp cho tất cả instance.
- Một số instance vẫn dùng key cũ trong rolling deployment.
- Response schema mới có trường hoặc mã lỗi khác.
- Timeout hoặc retry khác có thể tạo request trùng.

### 13.2. Kiểm tra trước triển khai

- Xác minh endpoint test và credential mới trong sandbox.
- Chạy contract test với schema v2.
- Kiểm tra ứng dụng xử lý response và lỗi mới.
- Xác minh quyền key mới đúng phạm vi.
- Xác định thời gian hai key cùng hợp lệ nếu nhà cung cấp hỗ trợ.
- Xác minh cấu hình timeout và idempotency.

### 13.3. Kiểm tra trong triển khai

- Cập nhật secret reference và xác nhận instance nhận cấu hình mới.
- Theo dõi lỗi xác thực theo phiên bản/instance.
- Xác minh request thực sự dùng endpoint v2.
- Giữ khả năng chuyển về endpoint/key cũ trong khoảng chuyển tiếp được phê duyệt.
- Chỉ thu hồi key cũ sau khi xác nhận không còn sử dụng.

### 13.4. Kiểm tra sau triển khai

Chạy smoke test an toàn qua sandbox hoặc giao dịch thử nghiệm được phê duyệt, đối chiếu request/response đã làm sạch, theo dõi lỗi và xác minh không phát sinh tác dụng phụ trùng. Nếu lỗi xác thực tăng, dừng rollout theo ngưỡng đã định và thực hiện phương án phục hồi.

## 14. Ma trận kiểm thử phát hành

Ma trận giúp nhóm nhìn thấy điều kiện nào đã được kiểm tra và bằng chứng còn thiếu.

| Giai đoạn | Migration/schema | Cấu hình/secret | Tương thích | Vận hành |
|---|---|---|---|---|
| Trước triển khai | Upgrade path, dữ liệu biên, thời gian và lock | Validation, endpoint, flag, quyền | Contract, phiên bản cũ/mới | Artifact, backup, runbook, ngưỡng dừng |
| Trong triển khai | Trạng thái migration, backfill, consistency | Cấu hình instance và secret rotation | Rolling/blue-green/canary compatibility | Readiness, traffic, error rate, tiến độ |
| Sau triển khai | Đối chiếu dữ liệu và ngoại lệ | Cấu hình thực tế, drift | Consumer, API/event, job nền | Smoke, SLI, alert, rollback/roll-forward readiness |

### 14.1. Phân loại kết quả

Với từng kiểm tra, dùng trạng thái rõ ràng:

- `PASS`: đã chạy và đáp ứng tiêu chí.
- `FAIL`: đã chạy và phát hiện sai lệch.
- `BLOCKED`: không thể chạy do thiếu điều kiện.
- `NOT RUN`: chưa được thực hiện.
- `INCONCLUSIVE`: có chạy nhưng bằng chứng chưa đủ để kết luận.

Không gộp `BLOCKED`, `NOT RUN` hoặc `INCONCLUSIVE` thành `PASS`. Nếu phát hành cần tiếp tục dù có ngoại lệ, ghi rõ rủi ro, biện pháp giảm thiểu và người có thẩm quyền chấp nhận.

## 15. Tiêu chí dừng, rollback và roll-forward

Quyết định phục hồi cần được chuẩn bị trước khi triển khai. Trong sự cố, người vận hành cần biết ai có quyền dừng rollout, ngưỡng nào kích hoạt hành động và cách xác minh trạng thái sau phục hồi.

### 15.1. Ví dụ tiêu chí dừng rollout

- Migration báo lỗi hoặc trạng thái schema không xác định.
- Backfill tạo sai lệch dữ liệu vượt ngưỡng được phê duyệt.
- Error rate hoặc latency của phiên bản mới vượt ngưỡng trong khoảng quan sát.
- Lỗi xác thực hoặc kết nối dependency tăng bất thường.
- Luồng nghiệp vụ quan trọng thất bại.
- Có dấu hiệu mất dữ liệu, giao dịch trùng hoặc vi phạm quyền.

Ngưỡng số cụ thể cần lấy từ baseline và SLO của hệ thống. Không áp dụng một tỷ lệ chung cho mọi dịch vụ.

### 15.2. Bảng quyết định phục hồi

| Tình huống | Hướng xử lý có thể phù hợp | Kiểm tra bắt buộc |
|---|---|---|
| Code mới lỗi, schema mở rộng vẫn tương thích code cũ | Rollback code hoặc chuyển traffic về phiên bản cũ | Xác minh dữ liệu mới vẫn đọc được bởi code cũ |
| Migration thất bại trước khi thay đổi dữ liệu | Dừng, sửa nguyên nhân và chạy lại theo quy trình | Schema và transaction ở trạng thái xác định |
| Backfill chạy một phần | Tiếp tục hoặc chạy lại theo checkpoint | Idempotency, số lượng và tính nhất quán |
| Dữ liệu đã chuyển đổi theo format mới | Có thể cần roll-forward hoặc migration bù | Khả năng đọc dữ liệu của phiên bản đích |
| Cấu hình/secret sai | Khôi phục cấu hình đã xác minh hoặc cấp lại secret | Kết nối, quyền và trạng thái instance |
| Consumer không tương thích | Dừng mở rộng rollout, khôi phục hợp đồng hoặc phát hành consumer tương thích | Queue, message tồn đọng và dữ liệu đã ghi |

### 15.3. Xác minh sau phục hồi

Sau rollback hoặc roll-forward, kiểm tra lại health, luồng nghiệp vụ, dữ liệu, queue, trạng thái migration và các chỉ số. Ghi nhận khoảng thời gian ảnh hưởng, thao tác đã thực hiện và phần dữ liệu cần đối soát.

## 16. Bằng chứng và hồ sơ phát hành

Mỗi quyết định phát hành cần truy vết được đến phiên bản, migration, cấu hình và kết quả kiểm tra.

Hồ sơ nên có:

- Commit, build, artifact và image version/digest theo chính sách.
- Danh sách migration và thứ tự thực thi.
- Kết quả migration test trên schema/dữ liệu đại diện.
- Báo cáo kiểm tra tính đầy đủ và chính xác dữ liệu.
- Cấu hình không nhạy cảm hoặc fingerprint/snapshot đã làm sạch.
- Phiên bản contract/API và kết quả compatibility test.
- Chiến lược triển khai, tỷ lệ canary hoặc thứ tự rolling.
- Kết quả pre-deployment và post-deployment checks.
- Log, metric, trace và test run ID liên quan.
- Quyết định go/no-go, ngoại lệ và người chấp nhận rủi ro.
- Kế hoạch rollback/roll-forward và kết quả diễn tập nếu có.

Không lưu secret, token hoặc dữ liệu nhạy cảm trong artifact phát hành. Áp dụng quyền truy cập và thời hạn lưu phù hợp với chính sách tổ chức.

## 17. Quy trình xác minh triển khai từ đầu đến cuối

Một quy trình tham khảo:

1. **Tiếp nhận release candidate:** xác định artifact, commit, phạm vi và người sở hữu.
2. **Phân tích thay đổi:** liệt kê schema, dữ liệu, cấu hình, secret, API/event và phụ thuộc.
3. **Đánh giá rủi ro:** xác định hậu quả, trạng thái trung gian và phiên bản có thể cùng tồn tại.
4. **Thiết kế kiểm thử:** chọn upgrade path, data validation, compatibility, config và operational checks.
5. **Chạy thử migration:** dùng dữ liệu đại diện, đo lock/thời gian và kiểm tra khả năng chạy lại.
6. **Xác minh cấu hình:** kiểm tra endpoint, secret, flag, quyền và giá trị mặc định.
7. **Xác minh tương thích:** kiểm tra consumer/provider, schema và các tổ hợp phiên bản.
8. **Diễn tập triển khai:** chạy theo chiến lược dự kiến, bao gồm trạng thái trung gian và phục hồi.
9. **Pre-deployment gate:** xác nhận artifact, backup, runbook, quan sát và tiêu chí dừng.
10. **Triển khai có kiểm soát:** theo dõi migration, instance, traffic và lỗi.
11. **Post-deployment validation:** chạy smoke, đối chiếu dữ liệu và theo dõi chỉ số theo phiên bản.
12. **Quyết định tiếp tục hoặc phục hồi:** dựa trên ngưỡng và bằng chứng đã thống nhất.
13. **Kết thúc theo dõi:** xác nhận ổn định, lưu hồ sơ và ghi nhận vấn đề cần cải thiện.

## 18. Những sai lầm thường gặp

### 18.1. Chỉ kiểm tra migration trên database rỗng

Database mới không đại diện cho dữ liệu cũ, dữ liệu bất thường hoặc quy mô production. Cần kiểm tra upgrade path và dữ liệu có phân bố phù hợp.

### 18.2. Thêm constraint trước khi dữ liệu sẵn sàng

Constraint mới có thể thất bại hoặc chặn ghi nếu dữ liệu cũ chưa được backfill. Hãy kiểm tra dữ liệu, xử lý ngoại lệ và áp dụng constraint theo giai đoạn.

### 18.3. Xóa cấu trúc cũ trong cùng lần phát hành

Rolling deployment có thể còn instance hoặc consumer dùng trường cũ. Dùng expand-contract và xác minh không còn consumer trước khi contract.

### 18.4. Giả định migration có thể rollback tự động

Một thao tác chuyển đổi dữ liệu có thể mất thông tin hoặc không thể đảo ngược. Kiểm tra backup, restore, compensating migration và roll-forward thay vì chỉ dựa vào script down.

### 18.5. Kiểm tra cấu hình bằng cách in toàn bộ môi trường

Log có thể làm lộ credential và dữ liệu nhạy cảm. Chỉ ghi tên key, trạng thái validation và giá trị không nhạy cảm đã được phê duyệt.

### 18.6. Không kiểm tra phiên bản cùng tồn tại

Test chỉ trên phiên bản mới sau khi mọi instance đã cập nhật có thể bỏ sót lỗi trong rolling deployment. Kiểm tra các tổ hợp phiên bản và schema có thể xuất hiện thật.

### 18.7. Coi deployment job thành công là phát hành thành công

Job có thể hoàn tất trong khi hành vi nghiệp vụ, dữ liệu hoặc dependency vẫn lỗi. Cần smoke test, post-deployment checks và theo dõi chỉ số.

### 18.8. Không kiểm tra dữ liệu sau backfill

Script kết thúc không chứng minh mọi bản ghi đã được chuyển đổi đúng. Đối chiếu số lượng, mapping, ngoại lệ và tính nhất quán.

### 18.9. Canary nhưng không phân đoạn chỉ số

Nếu không phân biệt traffic của phiên bản mới và cũ, lỗi canary có thể bị che bởi tổng số liệu. Gắn version/instance vào telemetry và định nghĩa ngưỡng dừng.

### 18.10. Rollback code nhưng quên dữ liệu và message

Code cũ có thể không đọc được dữ liệu mới hoặc message mới đã phát. Đánh giá schema, payload, queue và tác dụng phụ trước khi quay lại phiên bản cũ.

## 19. Danh sách rà soát trước và sau triển khai

### 19.1. Trước triển khai

- [ ] Phạm vi thay đổi và phụ thuộc đã được lập bản đồ.
- [ ] Migration schema và data được review, chạy thử và có thứ tự rõ.
- [ ] Đã kiểm tra upgrade path từ các phiên bản được hỗ trợ.
- [ ] Dữ liệu biên, dữ liệu bất thường và tính đầy đủ được xác minh.
- [ ] Migration có giới hạn thời gian, lock và tài nguyên phù hợp.
- [ ] Backfill có checkpoint, khả năng chạy lại và báo cáo ngoại lệ.
- [ ] Ứng dụng cũ/mới tương thích trong giai đoạn cùng tồn tại.
- [ ] API, event và consumer được kiểm tra theo hợp đồng.
- [ ] Cấu hình, endpoint, feature flag và secret được xác minh an toàn.
- [ ] Artifact và image đúng phiên bản, nguồn gốc được truy vết.
- [ ] Backup/restore hoặc roll-forward plan phù hợp rủi ro.
- [ ] Health check, telemetry, runbook và người chịu trách nhiệm sẵn sàng.
- [ ] Tiêu chí go/no-go và dừng rollout được thống nhất.

### 19.2. Trong và sau triển khai

- [ ] Thứ tự migration và triển khai đúng kế hoạch.
- [ ] Trạng thái schema và backfill được theo dõi.
- [ ] Instance mới đạt readiness trước khi nhận traffic.
- [ ] Phiên bản cũ/mới hoạt động đúng trong thời gian chuyển tiếp.
- [ ] Cấu hình và secret có hiệu lực trên các instance.
- [ ] Smoke test và luồng nghiệp vụ quan trọng đạt.
- [ ] Dữ liệu sau migration được đối chiếu.
- [ ] Error rate, latency, dependency và chỉ số nghiệp vụ nằm trong ngưỡng.
- [ ] Traffic được chuyển đúng và instance cũ được drain an toàn.
- [ ] Không có message, giao dịch hoặc tác dụng phụ trùng ngoài dự kiến.
- [ ] Ngoại lệ và rủi ro còn lại được ghi nhận, có người chấp nhận.
- [ ] Hồ sơ phát hành và bằng chứng được lưu an toàn.

## 20. Kết luận

Xác minh migration, cấu hình và khả năng tương thích là phần thiết yếu của chiến lược kiểm thử phát hành. Migration cần được kiểm tra trên dữ liệu và schema đại diện, có thứ tự triển khai rõ, có khả năng chạy lại và có cách xác minh tính đầy đủ. Cấu hình cần được validation, tách theo môi trường và quản lý secret an toàn. Tương thích cần được đánh giá cho các phiên bản ứng dụng, schema, API và consumer có thể cùng tồn tại trong giai đoạn chuyển tiếp.

Nhóm cần kiểm tra trước, trong và sau triển khai; chuẩn bị tiêu chí dừng, rollback hoặc roll-forward; và theo dõi cả sức khỏe kỹ thuật lẫn hành vi nghiệp vụ. Thành công của một deployment job chỉ là một phần bằng chứng. Quyết định phát hành đáng tin cậy phải dựa trên trạng thái dữ liệu, cấu hình thực tế, khả năng tương thích, kết quả smoke/regression và các chỉ số vận hành đã được xác định trước. Khi mọi điều kiện và ngoại lệ được ghi nhận minh bạch, nhóm có thể triển khai thay đổi an toàn hơn và phục hồi có kiểm soát khi điều kiện không đạt.
