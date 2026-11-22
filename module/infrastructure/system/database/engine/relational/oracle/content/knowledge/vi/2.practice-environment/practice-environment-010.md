# Tách môi trường phát triển, kiểm thử và vận hành với Oracle Database

Trong một dự án dùng **Oracle Database**, lập trình viên cần thử SQL, thay đổi schema và tạo dữ liệu mẫu; nhóm kiểm thử cần chạy kịch bản có thể lặp lại; còn hệ thống thực tế phải bảo vệ dữ liệu, duy trì dịch vụ và khôi phục khi gặp sự cố. Nếu tất cả cùng sử dụng một database mà không phân định rõ ranh giới, một thao tác thử nghiệm như `DELETE`, `ALTER TABLE` hoặc cập nhật hàng loạt có thể tác động trực tiếp đến người dùng thật.

**Tách môi trường** là tổ chức những nơi chạy ứng dụng, lưu dữ liệu, lưu cấu hình, cấp quyền và triển khai thay đổi theo mục đích khác nhau. Trong bài này, ba môi trường cốt lõi là **phát triển (development/DEV)**, **kiểm thử (testing/TEST)** và **vận hành thực tế (production/PROD)**. Dự án có thể có thêm **staging/UAT** trước production, nhưng các nguyên tắc phân tách vẫn tương tự.

Mục tiêu không chỉ là đặt tên database khác nhau. Một ranh giới có ý nghĩa phải trả lời được: **dữ liệu nào được dùng, ai có quyền truy cập, tài nguyên nào được chia sẻ, thay đổi đi vào môi trường bằng đường nào, và nếu thao tác sai thì phạm vi ảnh hưởng đến đâu?**

## 1. Vì sao cần tách môi trường?

Giả sử nhóm xây dựng ứng dụng quản lý đơn hàng. Lập trình viên cần chạy thử một migration thêm cột trạng thái, tester muốn xóa dữ liệu để chạy lại kịch bản, và production đang xử lý giao dịch của khách hàng.

Nếu cả ba cùng kết nối tới một Oracle database:

- Lệnh `TRUNCATE TABLE` để dọn dữ liệu test có thể xóa dữ liệu thật.
- Migration chưa được kiểm chứng có thể gây lock, lỗi ứng dụng hoặc thay đổi cấu trúc bảng ngoài dự kiến.
- Dữ liệu khách hàng có thể bị đọc hoặc sao chép vào máy phát triển không đáp ứng quy định bảo vệ dữ liệu.
- Test hiệu năng tạo tải lớn, chiếm session, CPU, I/O, redo/undo và ảnh hưởng giao dịch thật.
- Các bài test phụ thuộc lẫn nhau, khó tái hiện vì nhiều người cùng sửa dữ liệu.
- Khi xảy ra lỗi, nhóm khó phân biệt nguyên nhân do code mới, dữ liệu test hay thao tác vận hành.

Khi được tách đúng, DEV có thể thay đổi nhanh; TEST có dữ liệu/kịch bản kiểm soát được; PROD chỉ nhận thay đổi đã được kiểm chứng, phê duyệt và quan sát. Việc tách còn làm rõ đường đi của một bản phát hành và tạo cơ sở cho phân quyền, sao lưu, giám sát, kiểm toán.

```text
                  Mã nguồn + migration có phiên bản
                              |
                              v
                       DEV (phát triển)
                         - thử nghiệm
                         - dữ liệu giả
                              |
                              v
                       TEST (kiểm thử)
                         - CI/integration test
                         - kịch bản lặp lại
                              |
                              v
                  STAGING / UAT (nếu có)
                         - kiểm tra release
                         - cấu hình gần PROD
                              |
                       phê duyệt phát hành
                              v
                        PROD (vận hành)
                         - người dùng thật
                         - giám sát/backup

              Dữ liệu production không tự chảy ngược
              sang DEV/TEST mà thiếu bước bảo vệ.
```

Mũi tên thể hiện **quá trình đưa thay đổi đã kiểm chứng lên môi trường tiếp theo**, không có nghĩa dữ liệu của môi trường này mặc nhiên được sao chép sang môi trường khác.

## 2. Mục đích và đặc tính của từng môi trường

| Tiêu chí | DEV | TEST | PROD |
|---|---|---|---|
| Mục đích chính | Viết code, thử SQL/PL/SQL, phát triển migration | Xác nhận tính đúng đắn, tích hợp, hồi quy và luồng nghiệp vụ | Phục vụ người dùng, bảo vệ dữ liệu và cam kết mức dịch vụ |
| Dữ liệu | Dữ liệu tổng hợp hoặc mẫu tối thiểu | Bộ dữ liệu được quản lý, tái tạo được, đủ nhiều tình huống | Dữ liệu nghiệp vụ thật, có phân loại và chính sách lưu giữ |
| Thay đổi schema | Thường xuyên, có thể reset | Qua migration và lịch test xác định | Theo pipeline, phê duyệt, cửa sổ thay đổi phù hợp |
| Quyền truy cập | Developer có quyền trong phạm vi sandbox | Test automation và người kiểm thử có quyền giới hạn | Tối thiểu quyền, audit, tách nhiệm vụ quản trị và triển khai |
| Khả năng xóa/làm mới dữ liệu | Có thể khởi tạo lại theo nhu cầu | Reset về trạng thái chuẩn theo quy trình | Không reset tùy ý; thao tác thay đổi có kiểm soát |
| Logging/monitoring | Ưu tiên khả năng chẩn đoán | Kiểm thử cả logging và cảnh báo | Theo dõi liên tục, bảo mật log, phát hiện sự cố và SLO |
| Sao lưu/khôi phục | Theo giá trị dữ liệu phát triển | Bảo đảm có thể tái lập hoặc khôi phục môi trường test | Backup/recovery được thiết kế, diễn tập theo RPO/RTO |
| Mức sẵn sàng | Có thể chấp nhận gián đoạn | Phụ thuộc lịch chạy test | Theo yêu cầu kinh doanh, có quy trình incident |

Mỗi nhóm có thể chia thêm lớp: **local DEV** cho từng lập trình viên; **shared DEV** để tích hợp sớm; **integration TEST** chạy tự động; **UAT** cho người dùng nghiệp vụ nghiệm thu; **performance TEST** cho tải; **staging/pre-production** kiểm tra phát hành gần với thực tế. Tên gọi khác nhau không quan trọng bằng mục đích và hợp đồng sử dụng từng môi trường.

### 2.1. Development không nhất thiết là bản sao production

DEV ưu tiên phản hồi nhanh. Có thể dùng Oracle Database Free hoặc một Oracle PDB được cấp cho nhóm, với dữ liệu giả và quyền chỉ áp dụng trong sandbox. Nhà phát triển được thử migration nhiều lần, nhưng mọi thứ cần tồn tại ở môi trường khác phải được ghi thành script có phiên bản thay vì chỉ lưu trong lịch sử SQL của máy cá nhân.

Nếu dùng Oracle Free tại local, cần biết giới hạn tài nguyên/tính năng của edition đó. Một bài test chạy tốt ở local không chứng minh hiệu năng, tính sẵn sàng hay hành vi của toàn bộ cấu hình production.

### 2.2. Testing cần trạng thái có thể tái lập

TEST không nên là “DEV dùng chung”. Một lần chạy integration test phải biết schema đang ở version nào, dữ liệu ban đầu ra sao, script seed nào đã chạy và cách reset sau khi kết thúc. Với kiểm thử chạy song song, có thể cần PDB/schema hoặc database riêng cho từng job để tránh các test cùng xóa/sửa dữ liệu của nhau.

Các bài performance test cần một khu vực kiểm soát riêng khi khối lượng đủ lớn; nếu dùng chung tài nguyên với những môi trường khác, kết quả dễ sai lệch và có thể ảnh hưởng tính sẵn sàng của dịch vụ.

### 2.3. Production là môi trường chịu trách nhiệm dịch vụ

PROD có dữ liệu thật, yêu cầu truy cập được ghi nhận, giới hạn thay đổi chặt chẽ và có cơ chế vận hành sự cố. Code và migration được đưa lên từ một quy trình có thể truy vết. Production nên tránh mọi script thử nghiệm, tài khoản dùng chung và dữ liệu seed dành cho bài test.

## 3. Phân tách Oracle: database, PDB hay schema?

Trong Oracle, khái niệm “môi trường khác nhau” có thể được triển khai ở nhiều cấp. Các cấp **không tương đương nhau về cách ly**.

### 3.1. Các lớp liên quan trong Oracle

- **Oracle instance:** bộ nhớ và tiến trình nền phục vụ truy cập database. Các workload cùng instance có thể tranh chấp CPU, memory và I/O.
- **CDB (container database):** kiến trúc đa tenant; quản lý tài nguyên chung và chứa các PDB. Người có quyền quản trị ở mức CDB có thể có phạm vi ảnh hưởng rộng.
- **PDB (pluggable database):** database logic bên trong CDB, có tập đối tượng và user cục bộ riêng. Ứng dụng thường kết nối bằng **service name** trỏ đến PDB được cấp.
- **Schema/user:** vùng sở hữu bảng, view, package, index và các đối tượng logic. Hai schema có thể khác quyền nhưng vẫn cùng database/PDB, instance, tầng lưu trữ và nhiều cấu hình chung.
- **Tablespace/datafile:** vùng lưu trữ logic/vật lý; tách tablespace không tạo ra biên an ninh hoặc vận hành độc lập như tách database.

### 3.2. So sánh ba mô hình

| Mô hình | Ví dụ | Ưu điểm | Giới hạn chính |
|---|---|---|---|
| Schema riêng trên cùng PDB | `APP_DEV`, `APP_TEST`, `APP_PROD` cùng một PDB | Dễ thiết lập, ít tốn tài nguyên; phù hợp bài lab nhỏ | Cùng instance/PDB, backup và cấu hình chung; nhầm quyền hoặc thao tác admin có thể ảnh hưởng nhiều môi trường |
| PDB riêng, cùng CDB | `DEV_PDB`, `TEST_PDB`, `PROD_PDB` trong một CDB | Tách đối tượng và user ở cấp PDB; dễ quản lý lifecycle riêng hơn schema | Vẫn chia sẻ instance, hạ tầng và lớp quản trị CDB; sự cố/tải ở cấp chung vẫn lan rộng |
| CDB/instance hoặc dịch vụ database độc lập | DEV, TEST, PROD dùng những deployment riêng | Ranh giới cấu hình, tài nguyên, vận hành và blast radius rõ hơn | Tăng chi phí, quản trị, yêu cầu tự động hóa và giám sát |

**Đối với thực hành cá nhân:** hai PDB hoặc hai database Oracle khác nhau đủ để chứng minh cô lập dữ liệu; nếu tài nguyên hạn chế, hai schema có thể minh họa tách quyền nhưng phải nhận thức đây là mức cách ly yếu hơn.

**Đối với hệ thống production có yêu cầu nghiêm ngặt:** thường nên cân nhắc triển khai database/CDB độc lập, kết hợp phân tách mạng, danh tính, secret, backup và quyền quản trị. Chỉ đặt DEV và PROD ở hai PDB chung CDB vẫn có thể khiến một lỗi hạ tầng hoặc thay đổi cấp CDB tác động lên cả hai.

Lựa chọn phụ thuộc vào chi phí, mức độ quan trọng, tính năng Oracle sẵn có và yêu cầu an ninh. Không có một kiểu tách phù hợp mọi tổ chức.

### 3.3. Sơ đồ môi trường đề xuất

```text
DEV application  ----> dev-db.internal:1521  / DEV_APP_SERVICE
                         Oracle DEV database/PDB
                         user: app_dev_runtime
                         data: synthetic

TEST application ----> test-db.internal:1521 / TEST_APP_SERVICE
                         Oracle TEST database/PDB
                         user: app_test_runtime
                         data: controlled fixtures

PROD application ----> prod-db.internal:1521 / PROD_APP_SERVICE
                         Oracle PROD database/PDB
                         user: app_prod_runtime
                         data: real business data
```

Tên host/service là **ví dụ giả định**. Chỉ dùng hostname hoặc TNS alias khác nhau không tạo ra cách ly nếu chúng vẫn dẫn đến cùng database hoặc nếu tài khoản có quyền truy cập chéo. Phải kiểm tra đích kết nối thật và ranh giới quyền.

## 4. Cách ứng dụng kết nối đúng môi trường

Trong Oracle, một JDBC URL kiểu Easy Connect có dạng:

```text
jdbc:oracle:thin:@//<host>:<port>/<service-name>
```

Ví dụ ba địa chỉ minh họa:

```text
DEV  jdbc:oracle:thin:@//dev-db.internal:1521/dev_app_service
TEST jdbc:oracle:thin:@//test-db.internal:1521/test_app_service
PROD jdbc:oracle:thin:@//prod-db.internal:1521/prod_app_service
```

Ứng dụng phải nhận cấu hình kết nối từ môi trường triển khai thay vì sửa source code trước mỗi lần phát hành. Với ứng dụng Java/Spring Boot, cấu hình chung có thể chỉ đọc biến môi trường hoặc secret được inject:

```yaml
# application.yml - dùng chung ở mọi môi trường
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_APP_USERNAME}
    password: ${DB_APP_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
```

Ở từng môi trường, hệ thống triển khai cung cấp `DB_JDBC_URL`, `DB_APP_USERNAME` và `DB_APP_PASSWORD` khác nhau. Giá trị mật khẩu thực tế nằm trong **secret manager hoặc cơ chế secret của nền tảng**, được cấp riêng theo môi trường; không commit vào Git, image, tài liệu hoặc log. Tệp `.env` có secret cũng cần được bảo vệ, không đưa lên repository.

Nếu dự án dùng Spring profiles (`dev`, `test`, `prod`), profile giúp chọn cấu hình tương ứng nhưng **không phải biện pháp bảo mật**. Cần kết hợp quyền database, rào cản mạng, secret riêng và giới hạn nơi workload có thể kết nối. Một process DEV không nên có khả năng truy cập endpoint PROD chỉ vì ai đó sửa biến cấu hình.

### 4.1. Kiểm tra Oracle đang kết nối tới đâu

Trước khi chạy SQL có tác động dữ liệu hoặc schema, hãy xác minh user và container của session hiện tại:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

Kết quả có thể cho thấy session đang ở một PDB và một schema khác với dự định. `CURRENT_SCHEMA` là schema được Oracle dùng để phân giải tên đối tượng không chỉ rõ owner, có thể thay đổi qua `ALTER SESSION SET CURRENT_SCHEMA`; nó **không đồng nghĩa danh tính đăng nhập** và không thay đổi quyền truy cập của user. Cần xem cả `SESSION_USER`, đích kết nối và thông tin container.

Ngoài việc xem tên, pipeline triển khai nên có **quy tắc chặn sai môi trường**: định danh deployment/secret/đường mạng riêng, chính sách phê duyệt cho production và kiểm tra database identity/target trước khi thực hiện migration. Một câu lệnh SQL kiểm tra tên chỉ là lớp phòng vệ bổ sung.

## 5. Tách dữ liệu: phần khó hơn tách tên database

DEV và TEST cần dữ liệu có ý nghĩa để tái hiện nghiệp vụ, nhưng không vì vậy mà được sao chép tùy ý dữ liệu production.

### 5.1. Ưu tiên dữ liệu tổng hợp (synthetic data)

Tạo dữ liệu giả có hình dạng phù hợp với hệ thống:

- Có khóa chính, khóa ngoại, dữ liệu tham chiếu và quan hệ nhiều bảng.
- Có trường hợp bình thường lẫn biên: `NULL`, chuỗi Unicode, số lớn, ngày/giờ theo timezone, giá trị trùng, độ dài giới hạn.
- Có dữ liệu cho các trạng thái nghiệp vụ: đơn mới, đã thanh toán, hủy, thất bại, hoàn tiền.
- Có bộ dữ liệu cho tình huống đồng thời: hai session sửa cùng bản ghi, unique constraint, rollback khi thất bại.
- Có bộ dữ liệu định lượng phục vụ đo plan/tải; dữ liệu vài chục dòng không đại diện cho truy vấn trên hàng triệu dòng.

Bộ seed phải **có phiên bản, biết kết quả mong đợi và tái tạo được**. Khi chạy nhiều lần, script nên dọn đúng dữ liệu test của mình hoặc tạo key xác định để tránh nhân bản ngoài ý muốn.

### 5.2. Khi thật sự cần bản sao production

Có những lỗi chỉ xuất hiện với phân bố dữ liệu thực tế, tính chọn lọc của index hoặc độ lớn bảng. Khi đó có thể cân nhắc **bản sao đã được phép và xử lý dữ liệu nhạy cảm**. Quy trình cần có người phê duyệt, phạm vi sao chép, hạn lưu giữ và kiểm chứng sau xử lý:

1. Xác định mục đích thử nghiệm và tập dữ liệu tối thiểu cần giữ.
2. Chọn phương án snapshot/clone/export được DBA hỗ trợ, chẳng hạn Data Pump ở mức schema hoặc công cụ nhân bản theo chính sách tổ chức.
3. Mask/tokenize/ẩn danh các trường chứa thông tin cá nhân, định danh, số liên hệ, địa chỉ, thông tin thanh toán và các nội dung nhạy cảm khác theo quy định áp dụng.
4. Duy trì quan hệ khóa ngoại và tính nhất quán của dữ liệu đã thay thế; tránh tạo bộ dữ liệu không còn chạy được nghiệp vụ.
5. Không mang theo mật khẩu, token, webhook, email recipient thật, endpoint thanh toán thật hoặc cấu hình tích hợp gửi thông điệp ra ngoài.
6. Kiểm tra quyền truy cập và khả năng kết nối bên ngoài trước khi mở bản sao cho developer/tester; đặt thời hạn xóa/refresh.

**Masking phải được áp dụng trước khi cấp dữ liệu cho người không được phép xem bản gốc.** Chỉ đổi tên schema, đặt database trong mạng nội bộ hoặc gắn nhãn “TEST” không làm dữ liệu thật trở nên an toàn. Một bản sao vẫn có thể rò rỉ thông tin qua backup, export, log, cache hoặc truy vấn báo cáo.

### 5.3. Reset và vòng đời dữ liệu

TEST nên có cơ chế trở về trạng thái chuẩn: tạo schema/PDB mới cho mỗi lần chạy khi khả thi, chạy migration từ đầu, nạp seed xác định và dọn sau khi kết thúc. Khi không thể reset toàn bộ, phải cô lập test bằng tenant/test-run ID và dùng phương án cleanup đáng tin cậy.

Production không được “refresh” bằng script xóa sạch dữ liệu để thuận tiện cho kiểm thử. Ngược lại, reset DEV/TEST cũng cần đúng quyền và guard để không vô tình nhắm sai endpoint.

## 6. Tách tài khoản và quyền truy cập Oracle

Mỗi môi trường nên có danh tính riêng cho từng loại công việc. Một cấu trúc minh họa:

| Danh tính | DEV | TEST | PROD |
|---|---|---|---|
| Ứng dụng runtime | User chỉ có quyền chạy nghiệp vụ ở DEV | User tương tự, nhưng chỉ truy cập TEST | User tối thiểu quyền DML/`EXECUTE` cần thiết, không có quyền DDL quản trị |
| Schema owner/migration | Được thay đổi schema sandbox | Pipeline migration thực thi trên TEST | Danh tính migration riêng, chỉ dùng theo quy trình được phê duyệt |
| Developer | Tự thao tác trong phạm vi sandbox | Đọc/chạy test theo nhu cầu đã cấp | Thông thường không có quyền viết dữ liệu thật trực tiếp; truy cập đặc biệt có kiểm soát |
| Tester/automation | Có thể thử tính năng | Quyền nạp/reset fixture thuộc TEST | Không sử dụng tài khoản test để kết nối production |
| DBA/operations | Quản trị theo phạm vi phụ trách | Quản trị và phục hồi TEST | Quản trị có kiểm soát, audit, quy trình khẩn cấp và phân nhiệm |

Nguyên tắc **least privilege**: ứng dụng chỉ cần `SELECT`, `INSERT`, `UPDATE`, `DELETE` hoặc `EXECUTE` trên những đối tượng thật sự sử dụng; không cấp `DBA`/`SYSDBA` hoặc quyền tạo/xóa object chỉ để tiện triển khai. Danh tính migration có thể cần quyền DDL nhưng không nên là tài khoản chạy API hằng ngày.

Tách user ở Oracle cũng chưa đủ nếu credential dùng chung trong nhiều môi trường. Cần:

- Secret riêng cho DEV, TEST, PROD; quy trình rotate và thu hồi.
- Nhóm IAM/role và approval riêng cho production; tránh chia sẻ tài khoản admin giữa cá nhân.
- Phân đoạn mạng để workload DEV/CI thông thường không thể kết nối trực tiếp tới listener/service của PROD.
- Audit và lưu dấu vết thao tác đặc quyền, deployment, truy cập dữ liệu nhạy cảm.
- Cơ chế truy cập khẩn cấp (*break-glass*) có giới hạn thời gian, lý do, người phê duyệt và ghi nhận hậu kiểm.
- Chặn job test/sandbox gọi ra hệ thống thật, ví dụ email, SMS, payment gateway hoặc hàng đợi production.

Nếu dùng Oracle multitenant, quyền ở cấp **CDB/common user** và quyền local ở từng **PDB** có phạm vi khác nhau. Khi tạo hoặc cấp quyền, DBA phải xác định chính xác container; không suy luận rằng tài khoản có cùng tên ở các PDB là cùng một identity.

## 7. Giữ schema nhất quán bằng migration có phiên bản

Tách môi trường mang lại giá trị khi một thay đổi có thể di chuyển từ DEV → TEST → PROD theo cách truy vết được. Việc chỉ mở SQL Developer rồi sửa tay từng database sẽ tạo ra **schema drift**: cùng một phiên bản ứng dụng nhưng bảng, cột, index hoặc constraint lại khác nhau.

Một quy trình thực hành:

1. Developer tạo migration dưới dạng tệp nguồn có phiên bản, ví dụ `V001__create_orders.sql`, `V002__add_order_status.sql` theo convention của công cụ đang dùng.
2. DEV chạy migration và thử nghiệp vụ; lỗi được sửa bằng thay đổi có quản lý.
3. CI khởi tạo database TEST ở trạng thái biết trước, áp dụng toàn bộ migration theo thứ tự, chạy integration/regression test và lưu log.
4. Staging (nếu có) chạy **cùng migration và cùng artifact ứng dụng** như bản phát hành dự kiến lên PROD.
5. Pipeline PROD dùng credential riêng, có kiểm tra target, phê duyệt thích hợp, ghi nhận version và quan sát sau triển khai.

Công cụ có thể là Flyway, Liquibase hoặc cơ chế migration SQL có version và audit rõ ràng. Chọn một cơ chế kiểm soát nguồn thay đổi; tránh vừa dùng migration tự động vừa thường xuyên sửa schema thủ công không được ghi nhận.

### 7.1. Oracle DDL thường tự commit

Oracle thực hiện **implicit commit** đối với nhiều lệnh DDL thông thường như `CREATE TABLE`, `ALTER TABLE` và `DROP TABLE`. Không thể coi toàn bộ chuỗi DDL là một giao dịch ứng dụng có thể hủy bằng một `ROLLBACK` đơn giản. Trước khi triển khai cần tính đến trạng thái hệ thống nếu lệnh đầu thành công nhưng lệnh sau thất bại.

Với bảng lớn hoặc ứng dụng cần không gián đoạn, cách triển khai thường là **expand → migrate → contract**:

```text
1. Expand: thêm đối tượng/cột theo cách ứng dụng cũ vẫn chạy được
2. Migrate: phát hành code mới, chuyển dữ liệu từng đợt có kiểm soát
3. Verify: kiểm tra dữ liệu, hiệu năng và tương thích
4. Contract: bỏ cấu trúc cũ sau khi không còn consumer phụ thuộc
```

Không nhất thiết migration nào cũng cần đủ bốn giai đoạn, nhưng thay đổi có thể phá tương thích (đổi tên, drop cột, thay kiểu dữ liệu) nên được thử trên TEST/staging trước, có phương án dừng hoặc sửa tiến cụ thể. Không dùng backup production làm “nút Undo” mặc định vì restore có thể làm mất các giao dịch hợp lệ phát sinh sau thời điểm khôi phục.

### 7.2. Tách dữ liệu seed khỏi migration production

DDL/schema cần thống nhất giữa các môi trường; còn **dữ liệu seed phục vụ test** chỉ thuộc DEV/TEST. Có thể chia:

```text
database/
  migrations/          # thay đổi schema chung, được kiểm soát version
  test-fixtures/       # dữ liệu giả và tình huống test, không chạy trên PROD
  environment-config/  # tham chiếu cấu hình; không chứa secret
```

Đường dẫn là ví dụ tổ chức source code. Nếu có **reference data** thật sự thuộc nghiệp vụ (như danh mục trạng thái chuẩn), phải mô tả đó là dữ liệu vận hành và có cơ chế cập nhật phù hợp; không trộn với fixture giả chứa khách hàng/đơn hàng phục vụ thử nghiệm.

## 8. Pipeline đưa thay đổi qua các môi trường

Một pipeline tốt giữ cùng nguồn code và artifact đã kiểm chứng, trong khi mỗi môi trường nhận **cấu hình, identity và dữ liệu của chính mình**.

```text
Commit / Pull Request
         |
         v
Build + unit test + review
         |
         v
Deploy DEV (schema DEV) --- developer smoke test
         |
         v
Deploy TEST (schema TEST) -- migration + integration/regression tests
         |
         v
Staging/UAT nếu có ------- xác nhận điều kiện release
         |
         v
Production approval / change window
         |
         v
Deploy PROD (schema PROD) -- smoke test + metrics + incident readiness
```

Trong thực tế, đội dự án có thể build một artifact bất biến rồi **promote chính artifact đó** từ TEST sang PROD để tránh sai khác do build lại. Đối với schema, pipeline dùng migration cùng phiên bản; không trực tiếp sao chép trạng thái database TEST sang PROD vì TEST có dữ liệu và hoạt động khác production.

Các cổng kiểm soát phù hợp gồm: kiểm tra target database/PDB, schema version hiện tại, tính tương thích giữa code và migration, kết quả test tự động, dung lượng trống, thời gian dự kiến, quyền người triển khai và tiêu chí dừng. Sau khi chạy, ghi lại ID release, version migration, người phê duyệt, thời điểm và các metric quan trọng.

### 8.1. Khi phát hành lỗi

Ví dụ release mới đọc cột `PAYMENT_STATUS` nhưng migration chưa chạy. Một hệ thống được tách đúng sẽ phát hiện việc lệch version ở TEST và chặn trước production. Nếu lỗi vẫn xuất hiện trên PROD:

- Operations xác định release, hiện trạng health/latency, cách cô lập ảnh hưởng và dừng rollout nếu cần.
- Developer xác nhận code đang yêu cầu schema nào, tính tương thích với phiên bản cũ và phương án sửa.
- DBA đánh giá trạng thái migration, transaction/lock, quyền, khả năng sửa hoặc khôi phục dữ liệu.

Quyết định rollback ứng dụng, chạy migration bổ sung hay sửa tiến cần dựa trên **trạng thái hiện tại**. Rollback binary không tự xóa DDL đã commit, và rollback database có thể ảnh hưởng dữ liệu thật.

## 9. Kiểm thử gì ở từng môi trường?

| Loại kiểm thử | Đặt ở đâu? | Bằng chứng cần quan sát |
|---|---|---|
| Unit test logic nghiệp vụ | Local/CI, có thể mock repository | Rule được thực thi đúng, không phụ thuộc Oracle thật nếu không cần |
| Integration test Oracle | TEST hoặc Oracle tách biệt cho CI | SQL chạy trên Oracle, kiểu dữ liệu, transaction, constraint, rollback, PL/SQL đúng |
| Migration test | TEST sạch và TEST đang có schema cũ | Áp dụng từ đầu và nâng cấp từ version trước đều thành công; không làm mất dữ liệu hợp lệ |
| Regression / end-to-end | TEST/staging | API và luồng nghiệp vụ hoạt động qua các service liên quan |
| Performance / concurrency | Môi trường test chuyên dụng đủ đại diện | Execution plan, p95/p99 latency, pool saturation, session, lock, CPU, I/O ở tải dự kiến |
| Backup/restore, failover | Môi trường diễn tập được kiểm soát | Thời gian khôi phục thực tế, tính nhất quán, khả năng kết nối lại và các bước runbook |
| Smoke test sau release | PROD với thao tác an toàn, giới hạn | Service đúng, truy vấn thiết yếu chạy, tỷ lệ lỗi/latency không bất thường |

Kiểm thử trên Oracle thực giúp phát hiện sự khác biệt với in-memory database hoặc cơ sở dữ liệu khác về SQL dialect, kiểu dữ liệu, sequence/identity, câu lệnh DDL, locking và hành vi transaction. Không nên kết luận “đã kiểm thử Oracle” nếu toàn bộ integration test thực tế chỉ dùng một engine khác.

### 9.1. Mức tương đồng với PROD

TEST không nhất thiết có cùng số CPU hoặc dữ liệu với PROD, nhưng với kiểm thử liên quan cần biết các khác biệt sau:

- Phiên bản Oracle, patch level, edition/tính năng có trong license.
- Cấu hình CDB/PDB, tablespace, NLS character semantics, collation, timezone và tham số liên quan.
- Định nghĩa schema, constraint, index, statistics và kích thước/phân bố dữ liệu.
- Driver JDBC, connection pool, timeout, transaction isolation và số lượng replica ứng dụng.
- Topology mạng, độ trễ, storage, backup và cơ chế HA nếu nằm trong phạm vi test.

Một execution plan tốt với bảng 100 dòng không chứng minh plan sẽ tương tự trên PROD có 100 triệu dòng. Với performance test, phải nêu rõ những yếu tố chưa tương đồng để hiểu giới hạn của kết quả.

## 10. Cách giám sát và sao lưu theo môi trường

**Giám sát cũng phải tách nhãn môi trường.** Alert của DEV không nên bị hiểu nhầm thành sự cố PROD. Dashboard/log cần có ít nhất tên môi trường, service/instance/PDB liên quan, thời điểm và release ID. Các số đo hữu ích gồm:

- Độ sẵn sàng của endpoint và thành công kết nối Oracle.
- Số session, connection pool đang dùng/chờ và lỗi tạo kết nối.
- Latency của SQL quan trọng, wait/lock và các lỗi ORA nổi bật.
- CPU, memory, I/O, tablespace/datafile và xu hướng tăng trưởng.
- Tiến độ backup, trạng thái khả năng phục hồi và ngưỡng cảnh báo đã thống nhất.

**Sao lưu khác với tách môi trường.** PDB hay schema riêng vẫn cần chiến lược backup/recovery phù hợp; cùng một hạ tầng lưu trữ hoặc chung miền quản trị có thể tạo điểm lỗi chung. Với PROD, phải thống nhất:

- **RPO (Recovery Point Objective):** lượng dữ liệu có thể chấp nhận mất nếu sự cố xảy ra.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.
- Cơ chế backup Oracle được hỗ trợ và kiểm soát (chẳng hạn RMAN), lịch lưu giữ, vị trí lưu, bảo vệ bản sao và kiểm tra restore.
- Người chịu trách nhiệm quyết định phục hồi về thời điểm nào, vì điều này có thể làm mất giao dịch được ghi sau mốc đó.

Ở DEV/TEST, có thể ưu tiên tái tạo nhanh từ migration và seed hơn là giữ mọi dữ liệu thử nghiệm. Tuy nhiên các bộ dữ liệu hoặc kết quả kiểm thử có giá trị cũng cần bảo vệ theo yêu cầu dự án.

## 11. Bài thực hành: xác nhận DEV và TEST thật sự tách nhau

Bài thực hành giả định bạn đã được DBA hoặc người quản trị cấp **hai đích Oracle riêng**, ví dụ `DEV_PDB` và `TEST_PDB`, cùng hai tài khoản chỉ có quyền cần thiết. Không cần tạo instance/PDB hoặc dùng tài khoản `SYSDBA` để làm bài. Nếu chỉ có một Oracle local, có thể tạo hai schema dưới sự hướng dẫn của quản trị viên, nhưng hãy ghi rõ bài thực hành đang kiểm tra **phân tách schema**, chưa phải cô lập database hoàn chỉnh.

### Bước 1 – Ghi nhận đích kết nối

Đăng nhập **DEV** bằng tài khoản đã cấp rồi chạy:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

Lưu thông tin để so sánh. Thoát session DEV rồi đăng nhập **TEST** và chạy cùng truy vấn. Hai môi trường dùng PDB khác nhau thì giá trị `CON_NAME` phải phản ánh hai container khác nhau; nếu là deployment Oracle độc lập, cũng cần đối chiếu đích host/service do quản trị viên cung cấp. Tên user đơn lẻ không đủ chứng minh cách ly.

### Bước 2 – Tạo dữ liệu giả chỉ trong DEV

Xác nhận lại session đang ở DEV. Trong schema thực hành đã được cấp quyền `CREATE TABLE` và quota phù hợp, chạy:

```sql
CREATE TABLE lab_environment_marker (
    marker_id   NUMBER PRIMARY KEY,
    env_name    VARCHAR2(20 CHAR) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lab_environment_marker (marker_id, env_name)
VALUES (1, 'DEV');

COMMIT;

SELECT marker_id, env_name, created_at
FROM lab_environment_marker;
```

Bản ghi `DEV` là dữ liệu minh họa; không dùng dữ liệu người dùng thật. Nếu table đã tồn tại do bài lab trước, sử dụng một schema sạch hoặc dọn theo đúng quyền và quy trình DEV, không tự chạy `DROP` trên một kết nối chưa kiểm tra.

### Bước 3 – Kiểm chứng TEST không nhận thay đổi từ DEV

Kết nối TEST bằng tài khoản tương ứng và chạy:

```sql
SELECT table_name
FROM user_tables
WHERE table_name = 'LAB_ENVIRONMENT_MARKER';
```

Nếu TEST mới được khởi tạo và chưa chạy migration tạo bảng này, kết quả mong đợi là **không có dòng nào**. `USER_TABLES` liệt kê bảng thuộc schema hiện tại; nó xác nhận trạng thái schema đang đăng nhập, không phải bằng chứng bảo mật duy nhất. Hãy đồng thời đối chiếu `DB_NAME`, `CON_NAME`, `SERVICE_NAME`, `SESSION_USER` và kiến trúc triển khai. Nếu bảng xuất hiện trên TEST, kiểm tra xem có script khác đã tạo nó hay bạn đã kết nối nhầm môi trường.

### Bước 4 – Tạo cùng cấu trúc ở TEST bằng migration

Trong thực tế, schema DEV/TEST cần được đồng bộ bằng **migration có phiên bản**. Khi chạy migration đã được kiểm chứng trên TEST, bảng có thể xuất hiện ở cả hai nơi, nhưng **mỗi môi trường có dữ liệu riêng**. Tạo thêm bản ghi `env_name = 'TEST'` tại TEST bằng fixture được quản lý, sau đó xác nhận:

```sql
SELECT env_name, COUNT(*) AS row_count
FROM lab_environment_marker
GROUP BY env_name;
```

DEV phải phản ánh dữ liệu `DEV` của riêng nó; TEST phản ánh dữ liệu `TEST` của riêng nó. **Cùng tên bảng, cùng cấu trúc, khác tập dữ liệu** là tình huống hoàn toàn bình thường khi tách môi trường.

### Bước 5 – Ghi lại bằng chứng thực hành

Trong báo cáo thực hành, ghi rõ mô hình tách được dùng (database/PDB/schema), service name, user, version migration, nguồn seed, kết quả hai lần kiểm tra môi trường và khả năng reset TEST. Không ghi mật khẩu, chuỗi kết nối chứa secret hoặc dữ liệu nhạy cảm. Hãy tự trả lời: một account TEST có thể đăng nhập PROD không, một migration DEV có thể nhắm PROD không, và một lỗi đầy disk ở DEV có thể ảnh hưởng PROD đến mức nào? Những câu hỏi đó cho thấy mức cách ly thật sự.

## 12. Tình huống vận hành: cấu hình nhầm đích PROD

Giả sử trong lúc chạy integration test, một biến cấu hình bị thay đổi thành endpoint Oracle production. Nếu quyền và mạng không được tách, bài test có lệnh xóa dữ liệu có thể gây sự cố thật dù tên job vẫn là `test`.

Một thiết kế phòng vệ nhiều lớp có thể ngăn hoặc giảm tác động:

1. Runner TEST chỉ có network route tới Oracle TEST; endpoint PROD không nằm trong tuyến kết nối được phép.
2. Runner giữ secret TEST, không có secret production.
3. Runtime account TEST không có quyền thao tác vào đối tượng PROD, dù tìm được đường kết nối.
4. Pipeline kiểm tra mục tiêu database/PDB và yêu cầu approval riêng trước migration lên PROD.
5. Các script nguy hiểm (`TRUNCATE`, backfill lớn, drop object) được review và gắn điều kiện dùng trong môi trường phù hợp.
6. Monitoring/audit phát hiện truy cập trái dự kiến; runbook nêu ai điều phối, ai xác nhận trạng thái dữ liệu và cách ngăn lỗi lan rộng.

Kết luận từ tình huống: **tên môi trường trong UI hoặc biến `APP_ENV=TEST` không đủ để bảo vệ dữ liệu**. Cần ranh giới đồng thời ở địa chỉ kết nối, network, danh tính, quyền Oracle, quy trình triển khai và khả năng quan sát.

## 13. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng chung một schema cho DEV, TEST và PROD | Đè dữ liệu, drift schema, phá test và có nguy cơ ảnh hưởng người dùng | Tách ít nhất schema theo mục đích; ưu tiên PDB/database độc lập khi yêu cầu cách ly cao |
| Tên service khác nhau nhưng trỏ vào cùng PDB | Tưởng đã tách nhưng thực chất chia sẻ dữ liệu và tài nguyên | Xác minh mapping service tới đích Oracle và thông tin session |
| DEV giữ credential DBA hoặc PROD | Lỗi hoặc lộ secret có phạm vi rất lớn | Tách identity và quyền; không phân phối secret PROD cho developer/runner DEV |
| Copy nguyên database PROD sang TEST | Rò rỉ dữ liệu, endpoint thật, secret và thông tin nhạy cảm | Phê duyệt phạm vi, masking, thay endpoint/secret, áp dụng retention và cô lập network |
| Sửa bảng bằng tay trên từng môi trường | DEV/TEST/PROD chạy schema version khác nhau | Migration có version, kiểm soát drift và lưu bằng chứng deploy |
| Integration test chỉ chạy trên database khác Oracle | Bỏ sót SQL dialect, constraint, transaction và hành vi Oracle | Dùng Oracle thật cho kiểm thử tích hợp cần fidelity |
| Đo hiệu năng bằng dữ liệu quá nhỏ | Kết luận sai về execution plan, index và độ trễ | Dùng dữ liệu/phân bố/tải đại diện, ghi giới hạn so với production |
| Nghĩ backup là rollback migration | Có nguy cơ mất dữ liệu phát sinh sau thời điểm khôi phục | Thiết kế expand/contract, phương án sửa tiến và recovery có phê duyệt |
| Trộn log/alert mọi môi trường | Phân loại sự cố sai, nhiễu cảnh báo | Gắn nhãn environment/service/release và phân tuyến cảnh báo |

## 14. Nguyên tắc áp dụng trong dự án thực tế

Khi thiết kế môi trường Oracle cho một nhóm mới, hãy bắt đầu bằng **sơ đồ đơn giản nhưng chính xác**: ứng dụng nào kết nối database/PDB nào, bằng service gì, với user/role nào, dữ liệu đến từ đâu và ai chịu trách nhiệm. Từ đó xác định chiến lược migration, tạo seed, reset TEST, bảo vệ PROD, giám sát và khôi phục. Các tiêu chí có thể dùng để nghiệm thu cấu hình môi trường:

- **Ranh giới:** DEV/TEST không ghi được vào PROD; đường mạng và tài khoản bị giới hạn theo mục đích.
- **Dữ liệu:** TEST có fixture có thể tái lập, không mang thông tin nhạy cảm chưa được xử lý.
- **Schema:** mọi môi trường biết version migration; schema không thay đổi ngầm qua thao tác thủ công.
- **Triển khai:** artifact và script được promote có kiểm soát, dùng secret riêng, biết mục tiêu trước khi chạy.
- **Kiểm thử:** có test thực trên Oracle và môi trường đủ đại diện cho những rủi ro cần chứng minh.
- **Vận hành:** dashboard, backup, runbook, người chịu trách nhiệm và ngưỡng dừng rõ ràng cho production.

**Tách DEV, TEST và PROD là tách phạm vi tác động của hành động.** Đối với Oracle, phải xét đồng thời **database/CDB/PDB, schema, user/role, service kết nối, dữ liệu, tài nguyên và quy trình triển khai**. Thiết lập đúng giúp developer thử nghiệm thoải mái trong sandbox, tester tái hiện kết quả đáng tin cậy và người vận hành bảo vệ dữ liệu cũng như tính sẵn sàng của môi trường thực tế.
