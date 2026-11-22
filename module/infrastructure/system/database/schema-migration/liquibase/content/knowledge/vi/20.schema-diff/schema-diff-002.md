# Chọn cơ sở dữ liệu tham chiếu và cơ sở dữ liệu đích

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **So sánh lược đồ** này tập trung vào một quyết định nền tảng khi dùng Liquibase **diff** hoặc **diff-changelog**: chọn đúng **cơ sở dữ liệu tham chiếu (reference database)** và **cơ sở dữ liệu đích (target database)**.

Hai kết nối này có vai trò khác nhau. Reference là trạng thái chuẩn mà nhóm muốn dùng để so sánh; target là database được kiểm tra so với trạng thái đó và thường là database cần nhận thay đổi nếu nhóm tạo rồi áp dụng changelog từ kết quả diff. Đổi nhầm hai phía có thể đảo ngược ý nghĩa của báo cáo và tạo ra changelog phá hủy đối tượng đang có.

Mục tiêu là biết chọn nguồn tham chiếu đáng tin cậy, xác định đúng target, cấu hình hai kết nối, giới hạn phạm vi schema, đọc kết quả diff, review changelog được sinh ra và bảo vệ database đích trước khi triển khai.

## 1. Reference và target khác nhau thế nào?

Liquibase so sánh hai trạng thái database:

- **Reference database**: phía cung cấp cấu trúc mong muốn để đối chiếu. Đây có thể là database phát triển đã được xác nhận, database chuẩn được dựng từ changelog, hoặc một database baseline đã được review.
- **Target database**: phía được đem ra so sánh với reference. Đây thường là môi trường đang được kiểm tra hoặc nơi sẽ nhận các thay đổi sau khi nhóm review changelog được tạo ra.

Có thể hình dung:

~~~text
REFERENCE DATABASE                     TARGET DATABASE
Trạng thái mong muốn                   Trạng thái hiện tại cần đối chiếu
        |                                         |
        +-------------------+---------------------+
                            |
                            v
                       Liquibase diff
                            |
                            v
             Báo cáo đối tượng giống/khác/thiếu/thừa
                            |
                            v
                  Review kết quả so sánh
                            |
                 Nếu cần tạo thay đổi cho target
                            |
                            v
                    diff-changelog
                            |
                            v
                  Review changelog sinh ra
                            |
                            v
                  update-sql / validate / test
                            |
                            v
                 Chỉ sau phê duyệt mới update target
~~~

Quy tắc cần nhớ: **diff-changelog tạo changelog nhằm đưa target tiến gần đến reference**. Vì vậy, trước khi chạy, hãy tự hỏi: *“Nếu áp dụng những thay đổi được sinh ra lên target, target sẽ giống reference hơn hay ngược lại?”*

Ví dụ reference có bảng **customer** và target chưa có bảng này: báo cáo cho biết bảng có ở reference nhưng thiếu ở target; changelog hướng đến target có thể tạo bảng customer. Ngược lại, nếu target có bảng **legacy_customer** nhưng reference không có, changelog hướng đến target có thể đề xuất xóa bảng thừa đó. Đây là lý do phải review các thay đổi phá hủy.

## 2. Chọn reference database đáng tin cậy

Reference không nên được chọn chỉ vì đó là môi trường mới nhất hoặc có nhiều dữ liệu nhất. Nó phải đại diện cho **trạng thái schema được mong muốn và đã được xác nhận**.

Các nguồn reference thường gặp:

| Nguồn | Khi phù hợp | Điều cần kiểm tra |
|---|---|---|
| Database development | Nhóm phát triển schema tại đây và thay đổi đã được review | Có thay đổi thử nghiệm, dữ liệu/đối tượng thủ công hoặc migration chưa commit không? |
| Database staging đã nghiệm thu | Staging đã chạy đúng release và qua kiểm tra | Có drift riêng của staging hoặc cấu hình khác production không? |
| Database được dựng từ changelog | Muốn dùng mã nguồn migration làm nguồn chuẩn | Changelog phải dựng được trên đúng DBMS/version và có đủ object |
| Database baseline đã phê duyệt | Tiếp quản hệ thống cũ, schema chuẩn được kiểm kê | Baseline có bằng chứng và được quản lý phiên bản không? |
| Bản sao production đã làm sạch dữ liệu | Muốn so sánh cấu trúc gần thực tế production | Bản sao có cùng version/schema, đã ẩn dữ liệu nhạy cảm và không bị sửa ngoài kế hoạch không? |

Một reference tốt có các đặc điểm:

- Đã được xác nhận là trạng thái schema mục tiêu.
- Dùng cùng DBMS hoặc một cặp DBMS có chiến lược so sánh/chuyển đổi đã được kiểm chứng.
- Có schema, catalog, tên đối tượng và quy tắc đặt tên được hiểu rõ.
- Không có thay đổi thử nghiệm hoặc thay đổi thủ công chưa được ghi nhận.
- Có thể truy vết về release, commit changelog hoặc quy trình baseline.
- Tài khoản đọc có quyền xem metadata cần thiết để Liquibase tạo snapshot đầy đủ.

**Không mặc định production luôn là reference.** Production có thể chứa drift, hotfix DBA, object đặc thù hoặc cấu hình riêng chưa được đưa vào changelog. Nếu lấy production làm reference rồi sinh changelog cho development, nhóm có thể vô tình đưa hotfix ngoài quy trình trở lại mã nguồn mà chưa hiểu lý do.

Ngược lại, development cũng không tự động là chuẩn: một developer có thể tạo bảng hoặc index trực tiếp để thử nghiệm. Chỉ chọn sau khi đã xác nhận trạng thái đó là điều muốn đưa sang môi trường khác.

## 3. Chọn target database đúng với mục tiêu

Target là phía sẽ được đánh giá và thường là nơi nhận thay đổi nếu dùng changelog sinh ra từ diff. Hãy chọn target theo câu hỏi vận hành:

- Muốn biết staging lệch với schema chuẩn ở đâu? Reference là schema chuẩn; target là staging.
- Muốn tạo changelog đưa một database cũ về chuẩn mới? Reference là trạng thái mới đã được review; target là database cũ.
- Muốn kiểm tra production có drift so với release? Reference là trạng thái mong đợi của release; target là production hoặc bản sao production.
- Muốn kiểm tra database mới được provision? Reference là schema chuẩn; target là database mới.

Trước khi chạy, xác nhận **đúng host, port, database, catalog, schema và role** của target. Không chỉ nhìn tên connection như `prod`, `stage` hoặc `dev`; hãy truy vấn danh tính thực tế của database.

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
~~~

Nếu kết nối qua proxy hoặc môi trường managed, một số giá trị có thể không biểu thị hostname thực tế như cấu hình. Hãy đối chiếu với thông tin định danh môi trường do hạ tầng cung cấp.

**Diff không tự sửa database target.** Lệnh `diff` chỉ báo cáo khác biệt; `diff-changelog` tạo nội dung changelog; database chỉ bị thay đổi khi nhóm thực thi một lệnh áp dụng như `update` với changelog đã review. Tuy vậy, việc chọn nhầm target vẫn nguy hiểm vì nhóm có thể tạo ra một changelog hướng sai database hoặc áp dụng nhầm ở bước sau.

## 4. Hướng so sánh và cách đọc kết quả

Giả sử reference là schema chuẩn mới nhất, target là staging đang được kiểm tra. Kết quả diff thường cần được hiểu theo ba nhóm:

| Nhóm kết quả | Ý nghĩa | Ví dụ |
|---|---|---|
| **Chỉ có trong reference** | Đối tượng mong muốn chưa có ở target | Reference có bảng invoice, target chưa có |
| **Chỉ có trong target** | Target có đối tượng không có trong reference | Target có bảng tmp_customer_test |
| **Có ở cả hai nhưng khác nhau** | Đối tượng tồn tại hai phía nhưng định nghĩa khác | Cột status khác kiểu dữ liệu hoặc index khác thuộc tính |

Tên nhóm hiển thị cụ thể có thể khác theo phiên bản Liquibase và định dạng báo cáo. Khi đọc output, luôn xác định **bên nào là reference và bên nào là target** từ phần header của báo cáo.

Ví dụ:

- Reference có cột `customer.status VARCHAR(30)`, target không có cột đó → cần xem xét thêm cột vào target.
- Reference có FK `fk_order_customer` với `ON DELETE RESTRICT`, target có cùng FK nhưng `ON DELETE CASCADE` → đây là khác biệt hành vi, có thể gây mất dữ liệu nếu thay đổi không đúng nghiệp vụ.
- Reference không có bảng `legacy_customer`, target có bảng đó → có thể là object thừa, nhưng cũng có thể là bảng riêng do một ứng dụng khác quản lý; không tự động xóa.
- Cả hai có sequence `invoice_id_seq` nhưng increment/cache khác nhau → phải xem yêu cầu ORM và cách cấp ID trước khi điều chỉnh.

Không được diễn giải “chỉ có ở target” là “chắc chắn phải xóa”. Diff phát hiện khác biệt kỹ thuật; quyết định đối tượng nào cần tồn tại thuộc về thiết kế, ownership và nghiệp vụ.

## 5. Cấu hình hai kết nối Liquibase

Với Liquibase CLI, các thuộc tính thường dùng gồm:

- `url`, `username`, `password`: kết nối **target**.
- `reference-url`, `reference-username`, `reference-password`: kết nối **reference**.
- `driver` hoặc classpath JDBC: driver cần thiết cho DBMS tương ứng.
- Các thuộc tính schema/catalog: giới hạn hoặc xác định phạm vi metadata được so sánh.

Ví dụ minh họa bằng tham số CLI:

~~~shell
liquibase \
  --url="jdbc:postgresql://target-host:5432/customer_db" \
  --username="target_reader" \
  --reference-url="jdbc:postgresql://reference-host:5432/customer_db" \
  --reference-username="reference_reader" \
  diff
~~~

Ví dụ cố ý không ghi password thật. Trong CI/CD, cấp thông tin xác thực qua secret store hoặc cơ chế bảo mật của runner; tránh đặt password trong Git, command history hoặc log hiển thị cho người không có quyền.

Có thể dùng file cấu hình properties cho mỗi kết nối:

~~~properties
url: jdbc:postgresql://target-host:5432/customer_db
username: target_reader
reference-url: jdbc:postgresql://reference-host:5432/customer_db
reference-username: reference_reader
driver: org.postgresql.Driver
~~~

Cách truyền credentials, tên thuộc tính và vị trí file cấu hình cần kiểm tra theo phiên bản CLI. Nếu dùng hai file properties riêng, phải bảo đảm không ghi đè nhầm `url` hoặc `reference-url` khi pipeline chuyển môi trường.

### Vì sao phải có hai tài khoản đọc riêng?

Reference và target có thể thuộc hai vùng bảo mật khác nhau. Tách thông tin kết nối giúp:

- Biết rõ tài khoản nào truy cập nguồn chuẩn và tài khoản nào truy cập môi trường được kiểm tra.
- Cấp quyền đọc metadata tối thiểu, không cần quyền DDL cho thao tác diff.
- Tránh dùng credential production ở máy developer.
- Thu hồi quyền hoặc xoay secret độc lập.
- Ghi log kiểm toán mà không lộ thông tin xác thực.

Đối với lệnh `diff`, tài khoản thường cần đọc metadata schema và định nghĩa đối tượng. Khi tạo changelog rồi áp dụng, tài khoản update target cần quyền thay đổi tương ứng. Không dùng một tài khoản superuser chung chỉ để tránh lỗi permission.

## 6. Chọn schema và catalog để so sánh đúng phạm vi

Một nguồn sai lệch phổ biến là so sánh **khác schema** hoặc **khác catalog** mà không nhận ra.

Ví dụ reference có schema `app`, target có schema `customer`. Nếu không cấu hình phạm vi hoặc ánh xạ phù hợp, Liquibase có thể báo rất nhiều object “chỉ có ở một phía” dù thực chất hai schema đại diện cho cùng ứng dụng.

Trước khi diff, xác định:

1. **Catalog/database**: database nào được kết nối ở mỗi phía?
2. **Schema**: chỉ so sánh schema nghiệp vụ hay cả schema hệ thống?
3. **Default schema**: tài khoản kết nối có search path mặc định nào?
4. **Tên schema khác nhau**: reference và target có chủ ý dùng tên khác không?
5. **Quyền metadata**: tài khoản có nhìn thấy đủ object hay một phần bị ẩn?
6. **Object ownership**: schema nào do ứng dụng Liquibase quản lý, schema nào thuộc extension hoặc dịch vụ khác?

Liquibase có các tham số giới hạn schema/catalog, chẳng hạn phạm vi schema của target và reference. Tên option cụ thể có thể khác theo version. Đừng chỉ truyền một schema cho target mà quên schema reference, hoặc ngược lại.

Ví dụ, khi reference dùng `public` còn target dùng `app`, cần quyết định đó là hai namespace tương đương hay là một khác biệt thực sự. Nếu là tương đương, cấu hình phạm vi/ánh xạ đúng theo công cụ và DBMS; nếu là khác biệt có chủ ý, không nên sinh changelog chỉ để đổi tên schema ngoài ý muốn.

## 7. Chỉ so sánh những đối tượng thuộc phạm vi quản lý

Một database có thể chứa nhiều đối tượng mà ứng dụng không sở hữu: bảng quản trị, extension, schema monitoring, bảng audit của nền tảng, object do DBA quản lý hoặc đối tượng của một dịch vụ khác.

Nếu đưa tất cả vào diff, báo cáo có thể rất nhiễu. Hãy xác định **scope** rõ ràng:

| Phạm vi | Có nên so sánh? | Lý do |
|---|---|---|
| Bảng nghiệp vụ của ứng dụng | Thường có | Thuộc schema do module quản lý |
| PK/FK/unique/index nghiệp vụ | Có | Ảnh hưởng toàn vẹn và hiệu năng |
| View/function/trigger của ứng dụng | Có nếu được quản lý trong changelog | Có thể ảnh hưởng hành vi ứng dụng |
| Bảng metadata Liquibase | Thường loại khỏi phạm vi so sánh nghiệp vụ | Đây là lịch sử công cụ, không phải schema ứng dụng |
| Bảng hệ thống DBMS | Thường không | Do DBMS quản lý |
| Extension hoặc object của extension | Theo ownership và chiến lược triển khai | Có thể phụ thuộc quyền hoặc version ngoài changelog |
| Bảng tạm/đối tượng thử nghiệm | Không đưa vào schema chuẩn | Tránh tạo thay đổi không mong muốn |

Liquibase hỗ trợ một số cơ chế lọc đối tượng, loại diff, schema và catalog tùy phiên bản. Hãy dùng bộ lọc được hỗ trợ và ghi nhận trong pipeline; không dựa vào việc “không thấy object trong output” để kết luận nó không tồn tại nếu tài khoản không có quyền xem.

Đặc biệt, nếu loại trừ một đối tượng khỏi diff, điều đó có nghĩa **không kiểm tra đối tượng đó trong lần so sánh**, không có nghĩa đối tượng đã tương đương.

## 8. Ví dụ chọn reference/target cho ba tình huống

### Tình huống A: đưa staging về schema release đã nghiệm thu

- **Reference:** database được dựng từ changelog release đã review hoặc database chuẩn đã nghiệm thu.
- **Target:** staging đang được kiểm tra.
- **Mục tiêu:** tìm các object thiếu, thừa hoặc khác định nghĩa ở staging.
- **Hành động:** đọc diff; xác minh từng khác biệt là drift hay cấu hình có chủ ý; chỉ tạo changelog cho những thay đổi cần thiết.

Không chọn staging làm reference chỉ vì nó đang được dùng để test. Nếu staging có hotfix thủ công, nó có thể không còn đại diện cho release chuẩn.

### Tình huống B: baseline một database cũ

- **Reference:** schema chuẩn được dựng từ changelog baseline đã kiểm chứng.
- **Target:** database cũ hiện đang chạy ứng dụng.
- **Mục tiêu:** biết database cũ lệch baseline ở đâu.
- **Hành động:** phân loại khác biệt trước khi lập kế hoạch baseline hoặc forward-fix.

Không chạy `diff-changelog` rồi áp dụng toàn bộ ngay. Database cũ có thể có object bổ sung do hệ thống khác sử dụng; changelog tự sinh có thể đề xuất xóa chúng.

### Tình huống C: kiểm tra production có drift

- **Reference:** schema mục tiêu của release đang chạy hoặc release tiếp theo, tùy câu hỏi kiểm tra.
- **Target:** production hoặc bản sao production.
- **Mục tiêu:** phát hiện thay đổi ngoài changelog, thiếu object hoặc cấu hình khác.
- **Hành động:** ưu tiên báo cáo read-only; xác minh hotfix/DBA change và quyền sở hữu trước khi tạo migration sửa drift.

Nếu mục tiêu chỉ là audit, dừng ở lệnh `diff` và lưu kết quả. Không cần tạo changelog hay áp dụng update.

## 9. Chạy lệnh diff và diff-changelog

Sau khi xác nhận hai kết nối và phạm vi schema, lệnh cơ bản:

~~~shell
liquibase diff
~~~

Lệnh này so sánh reference với target và báo cáo các khác biệt theo những loại object mà phiên bản Liquibase hỗ trợ. Nó không tự áp dụng thay đổi schema.

Để sinh changelog mô tả các thay đổi cần thiết cho target hướng tới reference:

~~~shell
liquibase diff-changelog
~~~

Lệnh này thường ghi changelog ra file được chỉ định bằng tùy chọn changelog file hoặc theo cấu hình CLI. **Đừng để output ghi đè changelog gốc đang được quản lý** nếu chưa có quy trình review và lưu artifact riêng. Trong bài thực hành, hãy dùng một file output tách biệt ở môi trường thử nghiệm; việc tạo file đó cần tuân theo quyền và quy trình repository của dự án.

Trình tự gợi ý:

~~~shell
liquibase --version
liquibase validate
liquibase diff
liquibase diff-changelog
~~~

Lệnh `validate` kiểm tra changelog hiện có; nó không thay thế việc review changelog vừa được sinh ra. Nếu output của `diff-changelog` là một changelog mới, cần xác nhận nó parse/validate được với cấu hình thích hợp và xem SQL mà nó tạo ra trước khi áp dụng.

**Không chạy `update` ngay sau `diff-changelog`** chỉ vì lệnh sinh file trả thành công. Changelog sinh tự động là một đề xuất kỹ thuật, không phải quyết định thiết kế đã được phê duyệt.

## 10. Đọc một báo cáo diff có ví dụ

Giả sử kết quả so sánh cho thấy:

~~~text
Reference: customer_schema_reference
Target:    customer_schema_stage

Objects missing from target:
  Table: invoice
  Column: customer.status
  Index: idx_order_created_at

Objects unexpected in target:
  Table: tmp_customer_import

Objects with differences:
  Column: customer.email
    Reference: VARCHAR(320), NOT NULL
    Target:    VARCHAR(255), NOT NULL

  Foreign key: fk_order_customer
    Reference: ON DELETE RESTRICT
    Target:    ON DELETE CASCADE
~~~

Cách phân tích:

1. **invoice thiếu ở target:** có thể cần tạo bảng, nhưng trước hết kiểm tra target có một bảng tương đương tên khác hay không, dữ liệu có cần backfill không và các FK phụ thuộc.
2. **customer.status thiếu:** xác định default/nullability và cách ứng dụng cũ/new xử lý trước khi thêm.
3. **idx_order_created_at thiếu:** kiểm tra cột, query workload, uniqueness và chiến lược tạo index cho bảng lớn.
4. **tmp_customer_import chỉ có ở target:** có thể là bảng staging tạm, bảng do dịch vụ khác sở hữu hoặc object sót lại; không tự động xóa.
5. **email khác độ dài:** mở rộng VARCHAR thường ít rủi ro hơn thu hẹp, nhưng cần kiểm tra giới hạn DBMS, ORM validation và dữ liệu.
6. **ON DELETE khác:** đây là khác biệt hành vi có thể làm xóa dây chuyền hoặc từ chối xóa. Cần quyết định nghiệp vụ trước khi thay.

Diff cho biết hai trạng thái khác nhau ở đâu; nó không biết **tại sao** khác nhau hoặc bên nào đúng. Mỗi khác biệt cần được phân loại thành: drift cần sửa, khác biệt có chủ ý, object ngoài phạm vi, hoặc lỗi do kết nối/quyền/schema mapping.

## 11. Vì sao diff-changelog có thể tạo thay đổi phá hủy?

Nếu reference là trạng thái chuẩn và target có object thừa, changelog hướng đến target có thể đề xuất **drop** object đó để target giống reference hơn.

Ví dụ:

- Reference không có bảng `legacy_customer`.
- Target có bảng `legacy_customer`.
- Diff nhận diện bảng này chỉ có ở target.
- Changelog được sinh để target khớp reference có thể chứa `dropTable`.

Đó có thể là hành vi đúng nếu bảng thực sự là rác thử nghiệm. Nhưng nếu bảng chứa dữ liệu lịch sử hoặc được một batch job khác sử dụng, việc áp dụng sẽ gây mất dữ liệu hoặc gián đoạn hệ thống.

Review tất cả các thay đổi có khả năng phá hủy:

- `dropTable`, `dropColumn`, `dropView`, `dropSequence`.
- Xóa hoặc thay constraint/index có ảnh hưởng uniqueness và toàn vẹn.
- Thu hẹp kiểu dữ liệu, precision, length hoặc nullability.
- Thay default, sequence hoặc identity có thể làm hỏng luồng cấp ID.
- Thay function/procedure/trigger có thể đổi logic nghiệp vụ.
- Xóa extension, type hoặc object có dependency.

Nếu không muốn tự động đề xuất hoặc áp dụng loại thay đổi nhất định, hãy giới hạn phạm vi diff và review output thủ công. Không mặc định changelog sinh ra là “an toàn vì Liquibase tạo”.

## 12. Những gì diff không nói cho bạn

Schema diff không phải kiểm tra toàn bộ trạng thái ứng dụng. Cần hiểu giới hạn:

- **Không so sánh toàn bộ dữ liệu hàng** như một công cụ đối chiếu data replication. Bảng có cùng schema nhưng dữ liệu khác nhau vẫn có thể được báo là tương đương ở cấp cấu trúc.
- **Không chứng minh dữ liệu thỏa constraint mới.** Ví dụ, thêm UNIQUE có thể thất bại nếu target có giá trị trùng.
- **Không chứng minh ứng dụng tương thích.** ORM, query, stored procedure, quyền runtime và behavior nghiệp vụ cần test riêng.
- **Không đảm bảo mọi object DBMS-specific được so sánh đầy đủ.** Trigger, package, extension, partition, policy hoặc object đặc thù có thể có giới hạn hỗ trợ tùy DBMS/version.
- **Không đảm bảo sequence runtime state tương đương.** Cấu hình sequence và giá trị đã cấp/current value là các vấn đề cần xác minh riêng.
- **Không đánh giá lock, thời gian DDL hoặc tải hệ thống.** Một thay đổi nhỏ trong báo cáo vẫn có thể rewrite/lock bảng lớn.
- **Không xác nhận object không nhìn thấy là không tồn tại.** Tài khoản thiếu quyền metadata có thể khiến snapshot thiếu thông tin.

Do đó, kết quả diff cần được kết hợp với truy vấn dữ liệu, kiểm tra metadata, test ứng dụng và review vận hành.

## 13. Reference/target khác DBMS hoặc khác version

So sánh hai database khác DBMS có thể hữu ích trong quá trình chuyển đổi nền tảng, nhưng kết quả phức tạp hơn so sánh hai database cùng loại.

Ví dụ PostgreSQL và Oracle có khác biệt về:

- Kiểu dữ liệu và cách biểu diễn precision/scale.
- Sequence/identity và cơ chế tự sinh khóa.
- Schema/catalog và cách đặt tên không phân biệt chữ hoa/thường.
- Function/procedure, trigger và package.
- Index method, partial index, expression index.
- Constraint deferrable và hành vi tham chiếu.
- Default expression, timestamp/time zone và collation.

Một khác biệt có thể do **ngữ nghĩa DBMS**, không phải drift cần sửa. Changelog sinh từ diff không tự động chuyển đổi mọi logic SQL và đối tượng đặc thù một cách chính xác.

Ngay cả cùng DBMS nhưng khác major version, metadata hoặc tính năng hỗ trợ có thể khác. Hãy dùng cùng version khi mục tiêu là kiểm tra drift schema; nếu mục tiêu là nâng cấp DBMS, coi diff là một nguồn phân tích và thực hiện thêm kiểm thử tương thích.

## 14. Quyền truy cập và chất lượng snapshot

Liquibase cần đọc metadata từ cả hai database. Nếu reference hoặc target chỉ cho phép xem một phần object, báo cáo diff có thể không đầy đủ.

Tài khoản đọc cần quyền phù hợp để xem:

- Danh sách schema/table/view/sequence.
- Định nghĩa cột, default, constraint và index.
- Định nghĩa function/procedure/trigger mà nhóm cần so sánh.
- Metadata catalog cần thiết của DBMS.
- Các schema được chỉ định trong phạm vi diff.

Không nên cấp DDL chỉ để chạy diff. Nếu lệnh `diff-changelog` chỉ sinh file, tài khoản kết nối database thường vẫn có thể là read-only; quyền ghi file thuộc môi trường chạy CLI. Khi chuyển sang `update`, target cần tài khoản có quyền thay đổi đối tượng tương ứng.

**Nếu snapshot không đầy đủ, hãy sửa quyền hoặc phạm vi trước khi kết luận.** Không thêm hàng loạt object vào filter để làm báo cáo ngắn hơn nếu chưa biết chúng có nằm ngoài ownership hay không.

## 15. Bộ lọc diff và phạm vi object

Một dự án có thể chỉ muốn so sánh schema nghiệp vụ, không so sánh toàn bộ catalog. Liquibase có các tùy chọn theo phiên bản để giới hạn:

- Schema/catalog của reference và target.
- Loại object được so sánh (diff types).
- Object được include hoặc exclude.
- Các thuộc tính kết nối và mặc định schema.

Cú pháp cụ thể cần tra theo `liquibase diff --help` và phiên bản CLI. Khi chuẩn hóa pipeline, ghi lại toàn bộ filter để lần chạy sau có thể tái hiện kết quả.

Ví dụ về nguyên tắc:

~~~text
REFERENCE_SCOPE:
  catalog: customer_db
  schema: app
  object_types: tables, columns, primary_keys, foreign_keys, indexes

TARGET_SCOPE:
  catalog: customer_db
  schema: app
  object_types: tables, columns, primary_keys, foreign_keys, indexes
~~~

Đây là mô tả phạm vi, không phải cú pháp CLI. Hai phía cần được cấu hình nhất quán về mục tiêu so sánh. Nếu reference dùng schema `app` còn target dùng `public`, cần xác định mapping rõ ràng; không dùng filter để che sự khác biệt ngoài ý muốn.

Không loại bỏ metadata Liquibase hoặc object hệ thống một cách mù quáng. Một số bảng metadata không thuộc schema nghiệp vụ nên thường không cần đưa vào diff, nhưng các object ứng dụng có tên giống object hệ thống vẫn cần được xem xét.

## 16. Quy trình an toàn để tạo và áp dụng diff-changelog

Một luồng thực tế:

1. **Chốt reference:** lấy schema chuẩn từ release/commit đã review hoặc database đã nghiệm thu.
2. **Chốt target:** xác minh database/schema đang được so sánh; ghi rõ môi trường và mục đích.
3. **Xác nhận DBMS/version:** quyết định so sánh drift hay chuyển đổi nền tảng.
4. **Kiểm tra quyền và phạm vi:** bảo đảm snapshot hai phía đầy đủ và filter đối xứng theo mục tiêu.
5. **Chạy diff:** đọc toàn bộ khác biệt; phân loại drift, khác biệt có chủ ý và object ngoài ownership.
6. **Sinh diff-changelog:** lưu output riêng để review; không ghi đè changelog gốc.
7. **Review changeset:** kiểm tra SQL phá hủy, thứ tự phụ thuộc, precondition, kiểu dữ liệu, sequence và rollback.
8. **Validate và xem SQL:** kiểm tra changelog sinh ra bằng công cụ phù hợp, sau đó tạo SQL dự kiến cho target.
9. **Thử trên database cô lập:** dùng bản sao hoặc database test cùng DBMS/version, kiểm tra dữ liệu và ứng dụng.
10. **Phê duyệt và update:** chỉ áp dụng vào target sau khi có approval theo chính sách.
11. **Postflight:** chạy diff lại hoặc các truy vấn metadata/hậu điều kiện để xác nhận target đã gần trạng thái mong muốn.
12. **Lưu bằng chứng:** ghi commit/reference release, target identity, CLI version, filters, diff report, changelog được duyệt và kết quả update.

Một lần diff thành công chỉ cho biết Liquibase đã đọc và so sánh được những gì nó nhìn thấy. Một lần update thành công cũng cần được hậu kiểm để xác nhận kết quả thực tế.

## 17. Ví dụ cấu hình CLI đầy đủ cho PostgreSQL

Giả sử:

- Reference là database `customer_reference` trên máy chủ tham chiếu.
- Target là database `customer_stage` trên máy chủ staging.
- Cả hai dùng schema nghiệp vụ `app`.
- Liquibase CLI và PostgreSQL JDBC driver đã được cài và cố định version.

Có thể cấu hình properties (minh họa, không chứa password thật):

~~~properties
url: jdbc:postgresql://stage-host:5432/customer_stage
username: liquibase_reader_stage
reference-url: jdbc:postgresql://reference-host:5432/customer_reference
reference-username: liquibase_reader_reference
driver: org.postgresql.Driver
default-schema-name: app
reference-default-schema-name: app
~~~

Sau đó chạy các lệnh theo phiên bản CLI đã xác minh:

~~~shell
liquibase diff
liquibase diff-changelog
liquibase validate
liquibase update-sql
~~~

Trong ví dụ thực tế, cần chỉ định file changelog đầu ra riêng cho `diff-changelog` và file changelog phù hợp cho validate/update-sql. Không để lệnh sinh changelog ghi đè master changelog hiện có. Nếu dùng file properties chung cho nhiều môi trường, đảm bảo target/reference URL không bị thay nhầm khi pipeline chuyển stage.

Sau khi review và thử nghiệm, khi thực thi update, target URL phải vẫn là staging đã được phê duyệt. Nếu đổi target sang production, phải chạy lại các gate xác nhận đích, review SQL và approval tương ứng; không tái sử dụng approval của staging.

## 18. Tình huống chọn nhầm chiều và hậu quả

Giả sử reference là schema chuẩn đã nghiệm thu, target là production đang thiếu một index.

**Đúng chiều:**

~~~text
Reference = schema chuẩn (có index)
Target    = production (thiếu index)

diff:
  index chỉ có trong reference

diff-changelog:
  đề xuất tạo index trên target
~~~

**Đảo chiều:**

~~~text
Reference = production (thiếu index)
Target    = schema chuẩn (có index)

diff:
  index chỉ có trong target

diff-changelog:
  có thể đề xuất xóa index khỏi target để target giống reference
~~~

Nếu không đọc header và hướng so sánh, nhóm có thể tạo changelog ngược với mục tiêu. Đó là lỗi định hướng, không phải lỗi Liquibase.

Một cách tự kiểm tra trước mỗi lệnh:

1. Ghi rõ câu “reference là trạng thái tôi muốn hướng đến”.
2. Ghi rõ câu “target là database sẽ được so sánh và có thể nhận thay đổi”.
3. Chọn một khác biệt giả định (ví dụ reference thiếu một bảng, target có bảng đó) và dự đoán diff-changelog có thể đề xuất hành động gì.
4. Chỉ chạy khi dự đoán phù hợp với ý định.

## 19. Tích hợp vào CI/CD và Spring Boot

Diff thường phù hợp với một job **read-only** trong pull request hoặc pipeline kiểm tra môi trường. Changelog sinh ra từ diff nên là artifact cần review, không phải bước tự động deploy không kiểm soát.

Luồng CI/CD tham khảo:

~~~text
Changelog commit / release candidate
          |
          v
Resolve reference and target identities
          |
          v
Check credentials + DBMS versions + schema scope
          |
          v
Liquibase diff (read-only)
          |
          v
Review difference report
          |
          v
Optional: diff-changelog to a separate artifact
          |
          v
Review generated changesets + validate + update-sql
          |
          v
Test on isolated database
          |
          v
Approval
          |
          v
Update target
          |
          v
Postflight diff + schema/data/application checks
~~~

Các quy tắc vận hành:

- Pull request có thể diff database test với database được dựng từ changelog để phát hiện thiếu migration.
- Staging có thể được so sánh với release chuẩn trước khi promotion.
- Production diff nên chạy read-only theo lịch hoặc trước release; khác biệt cần được phân loại và phê duyệt.
- Nếu tạo diff-changelog, lưu file output cùng report và commit/review theo quy trình repository; không để pipeline tự động commit hoặc apply một thay đổi phá hủy mà không có review.
- Secret của reference và target phải được cấp riêng; log không được lộ credentials.
- Cố định phiên bản Liquibase, JDBC driver, DBMS version và filter để kết quả có thể tái lập.

Với Spring Boot, Liquibase thường quản lý schema qua changelog lúc ứng dụng khởi động hoặc qua một job riêng. **Diff không nên được chạy ngầm ở mọi lần khởi động ứng dụng** để tự quyết định sửa schema. Diff là công cụ phân tích và tạo đề xuất; việc áp dụng vẫn phải qua quy trình migration có kiểm soát.

## 20. Checklist lựa chọn reference và target

Trước khi chạy diff:

- [ ] Reference là trạng thái schema mục tiêu đã được review, có release/commit hoặc baseline rõ.
- [ ] Target là đúng database cần kiểm tra hoặc nhận thay đổi.
- [ ] Đã ghi rõ câu “diff-changelog sẽ hướng target tới reference”.
- [ ] Đã xác nhận host, port, database/catalog, schema và DBMS/version của cả hai phía.
- [ ] Tài khoản reference và target có quyền đọc metadata cần thiết; không dùng credential DDL cho thao tác read-only nếu không cần.
- [ ] Schema/catalog mapping được xác định, không so sánh nhầm namespace.
- [ ] Object filters/diff types được review và có thể tái lập.
- [ ] Biết rõ các object ngoài ownership, extension và metadata có được đưa vào phạm vi không.
- [ ] Đã xác nhận giới hạn của diff: schema object, không thay thế data comparison hoặc application tests.
- [ ] Đã chạy diff và phân loại mọi khác biệt.
- [ ] Changelog sinh ra được lưu riêng, review các DROP/ALTER/constraint/index/sequence và rollback.
- [ ] Đã validate, xem SQL và thử trên DBMS/version tương đương.
- [ ] Chỉ update target sau approval; sau đó chạy postflight diff/metadata/data checks.
- [ ] Lưu bằng chứng reference, target, filter, CLI version, report và kết quả.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chọn đúng reference và target quyết định toàn bộ ý nghĩa của kết quả schema diff. Reference phải đại diện cho trạng thái mong muốn có thể tin cậy; target phải là database thực sự cần được kiểm tra hoặc đưa về trạng thái đó. Khi hiểu rõ hướng so sánh, giới hạn metadata, phạm vi schema và rủi ro của changelog sinh tự động, nhóm có thể dùng **diff** để phát hiện drift và **diff-changelog** để tạo đề xuất migration có thể review, kiểm thử và triển khai nhất quán qua Spring Boot hoặc CI/CD.
