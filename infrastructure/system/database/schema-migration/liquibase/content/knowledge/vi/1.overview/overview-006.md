# Phạm vi sử dụng, giới hạn và lựa chọn công cụ phù hợp

Liquibase là công cụ quản lý thay đổi cơ sở dữ liệu theo phiên bản. Công cụ biến các thay đổi schema và dữ liệu thành những migration có định danh, được lưu trong source control và triển khai theo một thứ tự xác định. Nhờ đó, nhóm phát triển có thể biết thay đổi nào đã chạy trên từng database, tái tạo môi trường, phối hợp nhiều thành viên và đưa migration vào quy trình CI/CD.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, trọng tâm là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này xác định khi nào Liquibase phù hợp, những giới hạn cần tính đến và cách chọn công cụ dựa trên đặc điểm hệ thống.

## 1. Liquibase giải quyết vấn đề gì?

Khi ứng dụng phát triển, cấu trúc database cũng thay đổi: thêm bảng hoặc cột, tạo index, đổi constraint, chuyển đổi dữ liệu, thêm dữ liệu tham chiếu hay loại bỏ cấu trúc cũ. Nếu mỗi môi trường được cập nhật bằng các câu lệnh SQL thủ công, nhóm dễ gặp những tình trạng như:

- Môi trường phát triển, kiểm thử và sản xuất có schema khác nhau vì một migration bị bỏ sót.
- Một thay đổi được chạy hai lần hoặc chạy sai thứ tự.
- Không xác định được ai đã triển khai thay đổi nào và thời điểm nào.
- Mã ứng dụng mới được phát hành trong khi database chưa sẵn sàng, hoặc database đã đổi nhưng ứng dụng cũ vẫn đang chạy.
- Việc khôi phục gặp khó khăn vì không có kế hoạch rollback hoặc dữ liệu đã bị biến đổi không thể khôi phục bằng thao tác ngược đơn giản.

Liquibase đưa các thay đổi vào changelog có quản lý phiên bản. Mỗi changeset có định danh gồm ID, author và vị trí changelog; Liquibase dùng định danh đó để theo dõi việc thực thi. Khi chạy migration, Liquibase đọc changelog, xác định changeset chưa được áp dụng cho database đích, thực thi chúng theo thứ tự và ghi lịch sử vào các bảng quản lý của mình.

Thông thường, **DATABASECHANGELOG** lưu thông tin về changeset đã được áp dụng, bao gồm định danh, thời điểm thực thi và checksum. **DATABASECHANGELOGLOCK** giúp điều phối để tránh nhiều tiến trình Liquibase cùng cập nhật một database đồng thời. Đây là cơ chế theo dõi và khóa triển khai; nó không thay thế khóa nghiệp vụ, kiểm soát truy cập hay cơ chế đồng bộ của ứng dụng.

Liquibase hỗ trợ mô tả thay đổi bằng các định dạng changelog như XML, YAML, JSON và SQL có định dạng Liquibase. Có thể dùng các change type có cấu trúc để tăng tính độc lập với hệ quản trị cơ sở dữ liệu, hoặc viết SQL trực tiếp khi cần khai thác cú pháp đặc thù. Dù dùng định dạng nào, nội dung migration vẫn phải được review và kiểm thử trên hệ quản trị, phiên bản và cấu hình gần với môi trường đích.

## 2. Phạm vi sử dụng phù hợp

### 2.1. Quản lý vòng đời schema

Liquibase phù hợp khi schema thay đổi thường xuyên theo vòng đời sản phẩm và cần được triển khai nhất quán qua nhiều môi trường. Các ví dụ điển hình gồm:

- Tạo bảng, cột, khóa chính, khóa ngoại, unique constraint và index.
- Thay đổi kiểu dữ liệu, độ dài cột, giá trị mặc định hoặc khả năng null.
- Tách hoặc gộp cấu trúc bảng theo từng bước.
- Tạo view, sequence, trigger, procedure hoặc đối tượng database khác khi change type và database được hỗ trợ.
- Đánh dấu thay đổi theo môi trường bằng context hoặc label để chọn tập migration cần chạy.

Một changelog có thể được chia thành nhiều tệp theo tính năng, miền nghiệp vụ hoặc giai đoạn phát triển rồi được liên kết từ changelog gốc. Cách chia này giúp review và bảo trì dễ hơn, nhưng thứ tự include vẫn là một phần của thứ tự triển khai. Không nên dựa vào thứ tự tên tệp hoặc giả định rằng Liquibase sẽ tự sắp xếp migration theo ý nghĩa nghiệp vụ.

### 2.2. Thay đổi dữ liệu có kiểm soát

Liquibase cũng có thể quản lý dữ liệu, chẳng hạn:

- Thêm hoặc cập nhật các bản ghi danh mục, mã trạng thái và dữ liệu tham chiếu.
- Chuyển đổi dữ liệu khi schema đổi, ví dụ chuẩn hóa giá trị hoặc chuyển dữ liệu từ cột cũ sang cột mới.
- Thực hiện một lần backfill có phạm vi và điều kiện rõ ràng.
- Kết hợp thay đổi cấu trúc và thay đổi dữ liệu trong cùng một kế hoạch triển khai.

Migration dữ liệu cần được thiết kế cẩn thận hơn migration DDL đơn giản. Phải xác định số lượng bản ghi, thời gian chạy, khả năng khóa bảng, dung lượng log, tác động đến replica và khả năng chạy lại. Với bảng lớn, nên cân nhắc backfill theo lô bằng một job chuyên biệt, có checkpoint và khả năng tiếp tục; không nên mặc định một changeset duy nhất là cách tốt nhất để cập nhật hàng triệu bản ghi trong giờ cao điểm.

### 2.3. Đồng bộ nhiều môi trường và nhiều nhóm

Khi một sản phẩm có local, development, test, staging và production, changelog được quản lý trong source control giúp các môi trường nhận cùng một chuỗi thay đổi. Mỗi database vẫn giữ lịch sử thực thi riêng, vì vậy có thể kiểm tra changeset nào đã chạy và changeset nào còn chờ.

Liquibase hữu ích khi nhiều nhóm cùng đóng góp migration, miễn là nhóm thống nhất quy tắc đặt ID, author, cấu trúc thư mục, quy trình review và quyền sở hữu schema. Với nhiều database độc lập, mỗi database có thể có changelog hoặc cấu hình triển khai riêng. Với nhiều tenant dùng chung một loại schema, cần quyết định rõ cách điều phối migration theo tenant, giới hạn tốc độ và xử lý trường hợp một số tenant triển khai thất bại.

### 2.4. Tích hợp quy trình phát hành

Liquibase có thể chạy độc lập từ CLI, trong pipeline CI/CD hoặc được tích hợp vào ứng dụng Spring Boot. Điều này cho phép nhóm kiểm tra changelog, tạo trước SQL dự kiến, triển khai vào database kiểm thử và áp dụng migration trong một bước được kiểm soát của quy trình phát hành.

Đối với production, một bước migration riêng trong pipeline hoặc một deployment job có kiểm soát thường dễ quan sát và vận hành hơn việc để mọi replica ứng dụng tự khởi chạy migration. Nếu chọn chạy cùng ứng dụng, phải bảo đảm cơ chế khóa, cấu hình quyền, thứ tự khởi động và hành vi khi migration thất bại đã được kiểm thử.

## 3. Những thành phần cốt lõi cần hiểu trước khi chọn Liquibase

| Thành phần | Vai trò | Ý nghĩa khi vận hành |
|---|---|---|
| Changelog | Tập hợp hoặc điểm vào của các thay đổi database | Là lịch sử migration được quản lý trong source control |
| Changeset | Đơn vị thay đổi có ID, author và vị trí changelog | Thường được áp dụng một lần trên mỗi database; cần giữ ổn định sau khi triển khai |
| Precondition | Điều kiện phải thỏa trước khi chạy changeset hoặc changelog | Ngăn migration chạy trong trạng thái database không phù hợp |
| Checksum | Dấu kiểm tra nội dung changeset đã ghi nhận | Phát hiện nội dung đã thay đổi so với lần áp dụng trước |
| Rollback | Khai báo hoặc cơ chế đảo ngược thay đổi | Hỗ trợ khôi phục có kế hoạch; không bảo đảm mọi thay đổi đều đảo ngược được |
| DATABASECHANGELOG | Bảng lịch sử triển khai | Cho biết changeset nào đã chạy trên database |
| DATABASECHANGELOGLOCK | Bảng điều phối khóa triển khai | Giảm nguy cơ hai tiến trình Liquibase cập nhật cùng database đồng thời |
| Context và label | Bộ lọc lựa chọn changeset | Giúp điều khiển phạm vi triển khai theo môi trường hoặc mục đích |

ID của changeset cần duy nhất trong phạm vi mà nhóm quản lý, dễ truy vết và ổn định. Sau khi changeset đã được áp dụng ở bất kỳ môi trường dùng chung nào, hãy xem nội dung đó là lịch sử bất biến. Nếu cần sửa logic, tạo changeset mới để điều chỉnh trạng thái database. Việc sửa changeset đã chạy có thể làm checksum không khớp và khiến triển khai dừng lại hoặc buộc nhóm xử lý sai lệch lịch sử.

Precondition nên diễn đạt điều kiện có thể kiểm chứng, ví dụ database phải là PostgreSQL, bảng chưa tồn tại hoặc một cột cần thiết đã có. Phải chọn hành vi khi điều kiện không đạt một cách có chủ đích: dừng triển khai, bỏ qua hay đánh dấu đã chạy. Dùng **MARK_RAN** tùy tiện có thể khiến Liquibase ghi nhận changeset như đã hoàn tất trong khi cấu trúc mong muốn thực tế chưa được tạo. Với thay đổi bắt buộc, dừng bằng **HALT** thường an toàn hơn vì buộc người vận hành điều tra trạng thái database.

Checksum giúp phát hiện changeset đã thay đổi sau khi thực thi; nó không chứng minh migration đúng về mặt nghiệp vụ, không kiểm tra dữ liệu có đầy đủ hay không và không thay thế review. Không nên dùng thao tác xóa hoặc làm mới checksum như cách xử lý thường lệ cho mọi lỗi. Trước khi xử lý checksum mismatch, cần xác định changeset nào đã được triển khai, nội dung nào thay đổi và database đang ở trạng thái nào.

Rollback có thể được khai báo tường minh trong changeset hoặc được Liquibase hỗ trợ sinh tự động đối với một số change type. Khả năng tự sinh phụ thuộc loại thay đổi và database. Những thao tác như xóa dữ liệu, ghi đè dữ liệu, chuyển đổi một chiều hoặc thực thi SQL tùy biến có thể không có rollback an toàn. Với các thay đổi quan trọng, cần viết rollback có chủ đích và kiểm thử trên bản sao dữ liệu đại diện.

## 4. Giới hạn và chi phí cần tính đến

### 4.1. Không loại bỏ khác biệt giữa các hệ quản trị database

Change type có cấu trúc có thể giúp một changelog dùng được trên nhiều hệ quản trị, nhưng không bảo đảm mọi database có cùng kiểu dữ liệu, cú pháp, hành vi index, constraint, sequence, locking hoặc transaction. SQL thuần thường gắn với dialect cụ thể. Ngay cả cùng một hệ quản trị, khác biệt phiên bản và extension cũng có thể ảnh hưởng kết quả.

Nếu sản phẩm hỗ trợ nhiều database, cần xác định rõ mục tiêu tương thích: dùng chung toàn bộ changelog, dùng chung phần lớn và tách riêng các thay đổi đặc thù, hay duy trì changelog riêng theo database. Kiểm thử trên từng hệ quản trị được hỗ trợ là bắt buộc; chỉ validate cú pháp changelog không chứng minh SQL thực thi thành công trên mọi đích.

### 4.2. Không tự giải quyết mọi bài toán thiết kế schema

Liquibase quản lý và triển khai các thay đổi đã được mô tả. Công cụ không thay nhóm quyết định mô hình dữ liệu, quan hệ, chỉ mục, tính toàn vẹn, chiến lược phân vùng, khả năng mở rộng hoặc tương thích ngược của API. Các lệnh so sánh database, diff hoặc generate changelog có thể hỗ trợ khám phá khác biệt và tạo bản nháp, nhưng kết quả cần được kiểm tra và biên tập trước khi trở thành migration chính thức.

Không nên xem trạng thái database hiện tại là thiết kế chuẩn duy nhất nếu trạng thái đó có thể chứa thay đổi thủ công hoặc sai lệch ngoài quy trình. Changelog được review và quản lý trong source control mới là lịch sử thay đổi có thể tái tạo mà nhóm dự định duy trì.

### 4.3. Transaction và DDL phụ thuộc database

Không phải mọi hệ quản trị đều hỗ trợ rollback DDL giống nhau. Một số lệnh DDL có thể tự commit, không chạy trong transaction hoặc có hành vi khóa khác nhau. Một changeset chứa nhiều câu lệnh vì vậy có thể chỉ thực hiện được một phần nếu lỗi xảy ra giữa chừng, tùy database và cấu hình.

Trước khi gộp nhiều thay đổi vào một changeset, cần kiểm tra khả năng transaction của database đích, phạm vi ảnh hưởng và cách xử lý khi chỉ một phần thao tác thành công. Với thay đổi có rủi ro, chia nhỏ thành các changeset dễ quan sát và có thể xác minh độc lập.

### 4.4. Rollback không đồng nghĩa khôi phục dữ liệu

Rollback schema có thể đưa cấu trúc về trạng thái trước đó, nhưng không nhất thiết phục hồi dữ liệu đã mất. Ví dụ, nếu một changeset xóa cột chứa dữ liệu, thao tác tạo lại cột không thể tái tạo giá trị đã bị xóa. Nếu migration biến đổi dữ liệu theo cách mất thông tin, câu lệnh đảo ngược có thể không tồn tại.

Vì vậy, kế hoạch rollback cần xác định rõ có thể đảo ngược phần nào, cần backup hoặc snapshot nào, và khi nào phải dùng forward-fix thay cho rollback. Với production, phải kiểm tra quy trình khôi phục backup và thời gian phục hồi thực tế; chỉ có tệp rollback trong changelog là chưa đủ.

### 4.5. Migration lớn có thể gây tác động vận hành

Thêm index, đổi kiểu cột, cập nhật hàng loạt hoặc thêm constraint có thể khóa bảng, tăng tải I/O, tạo transaction dài hoặc làm chậm truy vấn. Hành vi cụ thể phụ thuộc database, kích thước dữ liệu, cấu hình và cách viết câu lệnh. Liquibase không tự biến một migration tốn tài nguyên thành thao tác không gián đoạn.

Cần đánh giá kế hoạch thực thi trên dữ liệu gần thực tế, thời gian chạy, lock, dung lượng đĩa, replication lag và khả năng dừng hoặc tiếp tục. Với thay đổi lớn, có thể cần migration theo nhiều đợt: thêm cấu trúc mới, backfill theo lô, chuyển ứng dụng sang cấu trúc mới rồi mới loại bỏ cấu trúc cũ.

### 4.6. Cần quản lý chặt trạng thái và quyền triển khai

Liquibase có thể bị chặn bởi lock còn sót lại sau sự cố hoặc tiến trình bị dừng bất thường. Không nên xóa lock một cách máy móc: trước hết xác nhận không còn tiến trình migration đang chạy, xem log và kiểm tra trạng thái database. Chỉ giải phóng lock sau khi hiểu nguyên nhân và xác nhận thao tác an toàn.

Tài khoản chạy migration thường cần quyền DDL rộng hơn tài khoản runtime của ứng dụng. Nên tách quyền khi có thể, lưu thông tin kết nối trong secret manager hoặc cơ chế bảo mật của nền tảng, giới hạn ai được chạy migration production và ghi lại kết quả triển khai. Context hoặc label chỉ là bộ lọc lựa chọn changeset, không phải ranh giới bảo mật.

### 4.7. Có chi phí tổ chức và bảo trì

Liquibase thêm khái niệm, cấu hình, quy ước và bước kiểm thử vào quy trình phát triển. Nếu dự án chỉ có một database nhỏ, ít thay đổi, một người chịu trách nhiệm và quy trình SQL đã được kiểm soát tốt, chi phí thiết lập có thể lớn hơn lợi ích trước mắt. Ngược lại, khi số môi trường, số nhóm hoặc tần suất phát hành tăng, giá trị của lịch sử tập trung và triển khai lặp lại thường rõ rệt hơn.

## 5. So sánh Liquibase với các lựa chọn khác

Không có công cụ migration phù hợp cho mọi dự án. Hãy chọn theo độ phức tạp của thay đổi, cách nhóm làm việc, database được hỗ trợ, yêu cầu kiểm toán và mức kiểm soát cần có.

| Lựa chọn | Phù hợp khi | Điểm mạnh | Giới hạn cần cân nhắc |
|---|---|---|---|
| Liquibase | Cần changelog có cấu trúc, precondition, context/label, lịch sử và nhiều cách mô tả migration | Quản lý thay đổi tập trung, hỗ trợ nhiều định dạng, tích hợp pipeline và nhiều môi trường | Nhiều khái niệm và cấu hình; cần quy ước nhóm; rollback và tính tương thích vẫn phải kiểm chứng |
| Flyway | Muốn quy trình migration đơn giản, chủ yếu viết SQL theo phiên bản | Mô hình migration dễ hiểu, SQL rõ ràng, phù hợp nhóm muốn kiểm soát trực tiếp câu lệnh | Các nhu cầu nâng cao và cách quản lý khác biệt theo môi trường phụ thuộc phiên bản, edition và cấu hình đang dùng |
| DDL tự động của ORM | Thử nghiệm cục bộ, tạo database tạm hoặc prototype | Khởi đầu nhanh, gắn với mô hình entity | Khó kiểm soát lịch sử production, dữ liệu chuyển đổi và khác biệt giữa các phiên bản ứng dụng; không nên để tự động cập nhật schema production thiếu review |
| SQL script thủ công | Một thay đổi đơn lẻ, có người vận hành và quy trình kiểm soát rõ | Minh bạch, trực tiếp, ít phụ thuộc công cụ | Dễ thiếu lịch sử tập trung, khó bảo đảm thứ tự và trạng thái đồng nhất nếu không có quy trình bổ trợ |
| Công cụ migration riêng của database | Dự án phụ thuộc sâu vào tính năng đặc thù của một hệ quản trị | Khai thác tốt khả năng native, có thể hỗ trợ các thao tác chuyên biệt | Giảm tính độc lập nền tảng; có thể cần công cụ khác khi đổi database hoặc mở rộng môi trường |

### 5.1. Khi nên chọn Liquibase

Liquibase là lựa chọn hợp lý nếu một hoặc nhiều điều kiện sau là quan trọng:

- Có nhiều môi trường cần nhận cùng chuỗi thay đổi và cần kiểm tra trạng thái đã áp dụng.
- Có nhiều nhóm hoặc nhiều người cùng đóng góp migration và cần lịch sử review rõ ràng.
- Migration gồm cả schema lẫn dữ liệu tham chiếu, cần precondition hoặc cần lọc changeset theo context/label.
- Cần hỗ trợ nhiều định dạng changelog hoặc muốn kết hợp change type có cấu trúc với SQL tùy biến.
- Muốn tích hợp kiểm tra, tạo SQL dự kiến, triển khai và ghi nhận kết quả vào CI/CD.
- Hệ thống cần quy trình triển khai database có thể kiểm toán và tái tạo.

### 5.2. Khi Flyway hoặc SQL migration đơn giản có thể phù hợp hơn

Nếu nhóm chủ yếu muốn viết SQL tuần tự, database mục tiêu tương đối ổn định và không cần nhiều khả năng mô tả changelog, Flyway có thể dễ tiếp cận và ít quy ước hơn. Với hệ thống rất nhỏ, SQL script được quản lý bằng source control và một quy trình chạy duy nhất cũng có thể đáp ứng nhu cầu.

Quyết định này cần xét phiên bản và edition thực tế của công cụ, các database được hỗ trợ và yêu cầu vận hành. Không nên chọn dựa trên một tính năng được nghe nói đến mà chưa xác nhận nó có trong phiên bản nhóm sẽ sử dụng.

### 5.3. Không giao quyền quản lý production schema cho ORM một cách thiếu kiểm soát

ORM giúp ánh xạ đối tượng và truy vấn dữ liệu; nó không thay thế một quy trình migration có review. Cấu hình tự động tạo hoặc cập nhật schema rất tiện trong môi trường phát triển, nhưng có thể gây thay đổi ngoài dự kiến khi ứng dụng khởi động ở production. Một lựa chọn thường an toàn hơn là để migration tool quản lý schema, còn ORM dùng chế độ kiểm tra hoặc không can thiệp DDL trong môi trường triển khai chính thức.

## 6. Cách đưa ra quyết định chọn công cụ

Có thể dùng các câu hỏi sau để thu hẹp lựa chọn:

1. **Có cần quản lý lịch sử migration theo từng database không?** Nếu có, dùng một migration tool thay vì dựa vào ghi chú hoặc thao tác thủ công.
2. **Nhóm có cần precondition, context/label, nhiều định dạng hoặc changelog có cấu trúc không?** Nếu có, Liquibase đáng được ưu tiên đánh giá.
3. **Phần lớn thay đổi có phải SQL tùy biến và nhóm muốn quy trình tối giản không?** Nếu có, hãy so sánh Flyway hoặc quy trình SQL có kiểm soát.
4. **Có nhiều hệ quản trị database hoặc nhiều phiên bản database không?** Hãy thử migration trên từng đích và đánh giá chi phí duy trì nhánh riêng.
5. **Có migration dữ liệu lớn hoặc thay đổi không thể đảo ngược không?** Hãy thiết kế backfill, backup, forward-fix và kế hoạch vận hành trước khi chọn cách tổ chức changeset.
6. **Ai thực thi migration và vào thời điểm nào?** Chọn CLI, CI/CD job hay Spring Boot integration dựa trên quyền, quan sát hệ thống, khả năng điều phối và yêu cầu phát hành.
7. **Nhóm có đủ năng lực duy trì quy ước và kiểm thử không?** Một công cụ mạnh chỉ tạo giá trị khi nhóm dùng nhất quán.

Một nguyên tắc thực tế là chọn giải pháp có mức kiểm soát vừa đủ cho rủi ro thật của hệ thống. Không nên thêm nhiều lớp cấu hình chỉ để xử lý một tình huống chưa tồn tại; cũng không nên dùng script thủ công khi số môi trường và người triển khai đã khiến sai lệch trở thành rủi ro thường xuyên.

## 7. Tích hợp Liquibase với Spring Boot và CI/CD

### 7.1. Trong Spring Boot

Spring Boot có thể tự cấu hình Liquibase khi dependency và changelog được khai báo phù hợp. Nhóm cần xác định đường dẫn changelog, thông tin kết nối, schema mặc định, context hoặc label, cũng như môi trường nào được phép chạy migration. Các giá trị nhạy cảm phải lấy từ cấu hình bảo mật của môi trường, không ghi mật khẩu vào source control.

Nếu ứng dụng có nhiều replica, cần hiểu replica nào sẽ chạy migration khi khởi động và cách các tiến trình phối hợp. Liquibase có cơ chế lock, nhưng pipeline vẫn cần kiểm soát thứ tự: migration phải hoàn tất trước khi phiên bản ứng dụng phụ thuộc vào schema mới nhận traffic. Với hệ thống có yêu cầu phát hành nghiêm ngặt, chạy migration bằng một job riêng rồi mới triển khai ứng dụng thường giúp tách log, quyền và trách nhiệm rõ hơn.

Trong môi trường phát triển, có thể bật migration tự động để rút ngắn vòng lặp. Trong production, cấu hình phải được quyết định có chủ đích; không sao chép nguyên cấu hình local sang production mà chưa đánh giá quyền database, số replica, thời điểm chạy và hành vi khi lỗi.

### 7.2. Trong CI/CD

Một pipeline migration có thể được tổ chức theo các bước sau:

1. **Kiểm tra source:** xác nhận changelog hợp lệ, các tệp được include tồn tại và quy tắc đặt changeset được tuân thủ.
2. **Xem trước thay đổi:** tạo SQL dự kiến hoặc báo cáo cập nhật để reviewer hiểu chính xác câu lệnh sẽ chạy.
3. **Triển khai vào database dùng một lần:** áp dụng migration trên database kiểm thử đúng hệ quản trị và phiên bản mục tiêu.
4. **Kiểm thử sau migration:** xác minh schema, constraint, dữ liệu chuyển đổi và khả năng tương thích của ứng dụng.
5. **Đánh giá rủi ro:** xem xét thời gian chạy, lock, backup, rollback hoặc forward-fix, cùng kế hoạch giám sát.
6. **Phê duyệt và triển khai:** chạy bằng tài khoản có quyền phù hợp, tại đúng môi trường và theo một tiến trình được điều phối.
7. **Xác minh kết quả:** kiểm tra log, lịch sử changeset, tình trạng ứng dụng và các chỉ số database sau triển khai.

Các lệnh validate hoặc updateSQL hỗ trợ kiểm tra và xem trước, nhưng không thay thế việc chạy thử trên database thật hoặc môi trường tương đương. Một pipeline thành công về mặt cú pháp vẫn có thể thất bại do quyền, dữ liệu hiện hữu, lock, khác biệt phiên bản hoặc tải thực tế.

## 8. Ví dụ minh họa: một changeset có điều kiện và rollback

Ví dụ YAML dưới đây tạo bảng customer nếu bảng chưa tồn tại. Đây là minh họa cho cấu trúc changeset; cần xác nhận kiểu dữ liệu, khả năng auto-increment và cú pháp trên hệ quản trị cùng phiên bản Liquibase của dự án.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-001-create-customer
      author: platform
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: customer
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: customer
~~~

Precondition yêu cầu bảng chưa tồn tại. Nếu bảng đã tồn tại, changeset dừng để người vận hành xác minh trạng thái. Rollback xóa bảng nên chỉ an toàn khi có thể chấp nhận mất toàn bộ dữ liệu trong bảng; trong production, phải đánh giá backup và tác động nghiệp vụ trước khi sử dụng. Ví dụ cũng cho thấy rollback được khai báo không có nghĩa là rollback luôn nên được chọn khi sự cố xảy ra.

Nếu cần migration SQL đặc thù, có thể dùng changeset định dạng SQL được Liquibase nhận diện. Dù dùng YAML hay SQL, nguyên tắc vẫn như nhau: mỗi thay đổi có mục đích rõ ràng, được review, kiểm thử trên database phù hợp và giữ bất biến sau khi đã áp dụng.

## 9. Quy tắc thực hành để sử dụng Liquibase an toàn

- **Thiết kế changeset nhỏ và có ý nghĩa:** mỗi changeset nên đại diện cho một thay đổi có thể review, kiểm thử và xác minh riêng.
- **Không sửa lịch sử đã triển khai:** tạo changeset mới để sửa sai hoặc mở rộng thay đổi cũ; xử lý checksum mismatch sau khi điều tra nguyên nhân.
- **Viết precondition theo trạng thái mong đợi:** chọn rõ hành vi khi điều kiện không đạt; tránh dùng MARK_RAN để che giấu trạng thái không rõ ràng.
- **Khai báo rollback có trách nhiệm:** kiểm tra cả cấu trúc lẫn dữ liệu; với thao tác không thể đảo ngược, ghi rõ chiến lược backup hoặc forward-fix.
- **Thử trên dữ liệu đại diện:** đặc biệt với migration đổi kiểu, thêm constraint, tạo index và cập nhật hàng loạt.
- **Tách triển khai schema khỏi phụ thuộc ứng dụng:** dùng chiến lược tương thích ngược để ứng dụng cũ và mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.
- **Quản lý context và label nhất quán:** quy định cách đặt tên và cách pipeline truyền giá trị; không coi bộ lọc là biện pháp phân quyền.
- **Giữ quyền database tối thiểu:** tài khoản migration có quyền cần thiết trong thời gian triển khai; tài khoản runtime không nên mặc nhiên có toàn bộ quyền DDL.
- **Theo dõi lock và lịch sử:** khi migration bị treo, kiểm tra tiến trình, log và trạng thái database trước khi can thiệp bảng lock.
- **Diễn tập quy trình phục hồi:** kiểm tra backup, restore và forward-fix trong môi trường phù hợp; không đợi production gặp sự cố mới thử.

## 10. Checklist trước khi đưa Liquibase vào một dự án

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Database và phiên bản có được Liquibase hỗ trợ không? | Ma trận database/phiên bản đã được xác nhận và migration mẫu chạy thành công |
| Changelog gốc và quy ước changeset đã rõ chưa? | Cấu trúc tệp, ID, author, include order và quy tắc review |
| Migration có kiểm soát trạng thái trước khi chạy không? | Precondition phù hợp và hành vi khi không đạt được xác định |
| Checksum mismatch được xử lý thế nào? | Quy trình điều tra, sửa bằng changeset mới và ngoại lệ được phê duyệt |
| Rollback có thực sự khôi phục được dữ liệu không? | Rollback đã thử, hoặc kế hoạch backup/restore/forward-fix được ghi nhận |
| Migration có ảnh hưởng hiệu năng hoặc khóa bảng không? | Kết quả thử nghiệm trên dữ liệu gần thực tế và kế hoạch thời gian triển khai |
| Ai chạy migration ở production? | Pipeline/job, tài khoản, quyền và người chịu trách nhiệm rõ ràng |
| Ứng dụng có tương thích trong giai đoạn chuyển đổi không? | Kế hoạch triển khai nhiều bước và kiểm thử với phiên bản ứng dụng liên quan |
| Có thể xác minh sau triển khai không? | Log, truy vấn kiểm tra, trạng thái DATABASECHANGELOG và chỉ số giám sát |

Liquibase phù hợp nhất khi database là một phần được quản lý của vòng đời phát hành phần mềm: thay đổi có phiên bản, có người review, có kiểm thử và có lịch sử triển khai theo từng môi trường. Công cụ mang lại khả năng tổ chức và quan sát tốt hơn, nhưng kết quả vẫn phụ thuộc chất lượng migration, hiểu biết về database và kỷ luật vận hành của nhóm.

Hãy chọn Liquibase khi những khả năng quản lý changelog, precondition, context/label và tích hợp quy trình đem lại lợi ích rõ ràng cho hệ thống. Chọn Flyway hoặc SQL migration gọn hơn nếu nhu cầu chủ yếu là thực thi SQL tuần tự và nhóm không cần thêm các khả năng đó. Dù chọn công cụ nào, migration production phải được kiểm chứng trên database mục tiêu, có kế hoạch xử lý lỗi và phù hợp với vòng đời của ứng dụng.

