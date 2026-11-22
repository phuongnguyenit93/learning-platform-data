# Chọn migration lúc khởi động hay tác vụ triển khai riêng

## 1. Hai cách đưa Liquibase vào vòng đời ứng dụng

Spring Boot có thể tự chạy Liquibase khi khởi tạo application context. Khi ứng dụng khởi động, cấu hình datasource và changelog được dùng để kiểm tra lịch sử, lấy khóa điều phối và áp dụng các changeset còn thiếu trước khi ứng dụng hoàn tất quá trình khởi tạo. Đây là cách thuận tiện cho dịch vụ nhỏ, môi trường phát triển và những thay đổi schema ngắn, ít rủi ro.

Một lựa chọn khác là chạy Liquibase bằng **tác vụ migration riêng** trong quy trình triển khai. CI/CD hoặc nền tảng điều phối khởi chạy một job có trách nhiệm cập nhật database; sau khi job thành công và vượt qua các gate xác minh, pipeline mới rollout phiên bản ứng dụng. Cách này phù hợp hơn khi migration kéo dài, cần cửa sổ bảo trì, cần quyền DDL riêng hoặc ứng dụng chạy nhiều replica.

Không có một lựa chọn luôn đúng cho mọi hệ thống. Cần chọn theo kích thước database, loại DDL, số replica, yêu cầu sẵn sàng, quyền truy cập và cách rollback. Điều quan trọng là xác định rõ **ai là chủ thể chạy migration, chạy vào thời điểm nào và ứng dụng được phép nhận traffic ở trạng thái schema nào**.

Bài học thuộc chương **Spring Boot** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này giúp thiết kế ranh giới giữa vòng đời khởi động ứng dụng và vòng đời triển khai database.

Sau bài học, người đọc có thể:

1. Giải thích cách Spring Boot tích hợp Liquibase khi application context khởi tạo.
2. So sánh migration lúc startup với migration job riêng theo độ sẵn sàng, quyền, khả năng quan sát và failure handling.
3. Cấu hình datasource, changelog, schema, context và parameters phù hợp.
4. Tránh nhiều replica cùng chạy migration không cần thiết.
5. Thiết kế pipeline có validate, preview, approval, update và verify.
6. Phối hợp thứ tự migration với rolling deployment, backward compatibility và rollback ứng dụng.

## 2. Liquibase chạy ở đâu trong vòng đời Spring Boot?

Khi Spring Boot auto-configuration tạo bean Liquibase (thường là <code>SpringLiquibase</code>) và bean này được bật, Liquibase sử dụng datasource được cấu hình để thực hiện migration trong quá trình khởi tạo application context. Việc khởi tạo bean cần hoàn tất trước khi ứng dụng được xem là sẵn sàng theo luồng startup bình thường.

Luồng khái niệm:

~~~text
Khởi chạy JVM / Spring Boot
          |
          v
Đọc cấu hình và tạo DataSource
          |
          v
Khởi tạo SpringLiquibase
          |
          v
Kết nối database
          |
          v
Đọc DATABASECHANGELOG
          |
          v
Lấy DATABASECHANGELOGLOCK
          |
          v
Chạy các changeset pending
          |
          v
Ghi lịch sử / giải phóng lock
          |
          v
Hoàn tất application context
          |
          v
Ứng dụng tiếp tục startup và nhận traffic khi readiness đạt
~~~

Đây là sơ đồ khái niệm; thứ tự chi tiết giữa các bean phụ thuộc cấu hình Spring Boot và dependency của ứng dụng. Nếu Liquibase thất bại trong quá trình khởi tạo, application context thường không thể khởi tạo hoàn chỉnh và tiến trình startup báo lỗi. Đây có thể là hành vi fail-fast mong muốn: ứng dụng không chạy trên schema mà nó không tương thích.

### 2.1. Cấu hình tối thiểu

Ví dụ trong <code>application.yaml</code>:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/orders
    username: orders_runtime
    password: ${ORDERS_DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: orders
    liquibase-schema: migration_control
    contexts: production
~~~

Ví dụ minh họa cấu hình Spring Boot; tên property và hành vi chi tiết cần đối chiếu với phiên bản Spring Boot/Liquibase của dự án. Secret nên được cấp từ secret manager hoặc môi trường triển khai, không ghi mật khẩu trực tiếp vào repository.

Các property thường gặp:

| Property | Vai trò |
|---|---|
| <code>spring.liquibase.enabled</code> | Bật/tắt auto-configuration Liquibase |
| <code>spring.liquibase.change-log</code> | Changelog root được nạp khi startup |
| <code>spring.liquibase.default-schema</code> | Schema mặc định cho object khi change không chỉ rõ schema |
| <code>spring.liquibase.liquibase-schema</code> | Schema lưu metadata Liquibase khi DBMS/tích hợp hỗ trợ |
| <code>spring.liquibase.contexts</code> | Context được chọn khi chạy |
| <code>spring.liquibase.labels</code> | Label filter cho changeset |
| <code>spring.liquibase.parameters</code> | Các tham số changelog |
| <code>spring.liquibase.database-change-log-table</code> | Tên bảng lịch sử nếu phiên bản hỗ trợ property này |
| <code>spring.liquibase.database-change-log-lock-table</code> | Tên bảng lock nếu phiên bản hỗ trợ property này |

Không nhầm <code>default-schema</code> với schema chứa bảng lịch sử. Một schema có thể chứa object ứng dụng, trong khi metadata Liquibase nằm ở schema quản trị riêng. Cũng không coi context là cơ chế phân tách lịch sử; DATABASECHANGELOG vẫn xác định changeset đã chạy theo định danh của nó.

### 2.2. Tách runtime user và migration user

Ứng dụng thường chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ; Liquibase cần quyền DDL để tạo bảng, cột, index hoặc constraint. Dùng một tài khoản có quyền quản trị cho cả runtime và migration làm tăng phạm vi ảnh hưởng nếu ứng dụng bị lỗi hoặc lộ thông tin xác thực.

Hai cách tổ chức thường gặp:

- **Cùng một datasource/user:** đơn giản, nhưng tài khoản của ứng dụng có thể cần quyền DDL rộng hơn mức runtime thực sự cần.
- **Datasource riêng cho Liquibase:** runtime user chỉ có quyền nghiệp vụ; migration user có quyền DDL cần thiết. Có thể cấu hình bean Liquibase riêng để dùng datasource migration.

Nếu dùng datasource riêng, cần đảm bảo Liquibase hoàn tất trước khi các bean hoặc luồng startup phụ thuộc schema mới được sử dụng. Không cấu hình một migration datasource nhưng lại để auto-configuration chạy thêm một Liquibase instance trên runtime datasource.

## 3. Migration lúc startup: ưu điểm và giới hạn

### 3.1. Ưu điểm

- Cấu hình đơn giản: ứng dụng tự kiểm tra và cập nhật schema khi khởi chạy.
- Dễ tái tạo môi trường phát triển hoặc kiểm thử: chạy ứng dụng có thể tạo schema cần thiết.
- Changelog và artifact ứng dụng đi cùng nhau, giảm nguy cơ deploy code mà quên migration.
- Với migration nhỏ và tương thích ngược, không cần thêm một job triển khai riêng.
- Nếu migration thất bại, ứng dụng thường không hoàn tất startup, giúp tránh phục vụ request trên schema sai.

### 3.2. Giới hạn

- Startup phụ thuộc database và thời gian migration; database chậm có thể làm instance khởi động chậm.
- DDL cần lock hoặc backfill lớn có thể khiến deployment kéo dài và làm readiness không đạt.
- Nhiều replica có thể cùng khởi tạo Liquibase; các instance khác có thể chờ DATABASECHANGELOGLOCK.
- Tài khoản ứng dụng có thể bị cấp quyền DDL nếu dùng chung datasource.
- Khó điều phối migration cần approval, cửa sổ bảo trì hoặc thao tác thủ công.
- Lỗi migration có thể làm toàn bộ replica mới không khởi động được, trong khi replica cũ vẫn đang phục vụ.

Startup migration phù hợp nhất khi thay đổi ngắn, dễ dự đoán, không yêu cầu thao tác vận hành đặc biệt và có thể chạy an toàn trong quá trình instance khởi tạo.

### 3.3. Nhiều replica không có nghĩa mỗi replica cần tự quản lý migration

Giả sử Kubernetes tạo 8 pod của cùng một service:

~~~text
Deployment
  ├── Pod 1 → Spring Boot → Liquibase
  ├── Pod 2 → Spring Boot → Liquibase
  ├── Pod 3 → Spring Boot → Liquibase
  ├── ...
  └── Pod 8 → Spring Boot → Liquibase
                    |
                    v
              Cùng database
~~~

Liquibase dùng DATABASECHANGELOGLOCK để phối hợp các tiến trình cùng sử dụng lock table. Một tiến trình có thể giữ lock và chạy changeset; các tiến trình khác chờ, sau đó đọc lịch sử và thường không chạy lại changeset đã được ghi nhận.

Điều đó không làm cho mô hình nhiều replica trở nên miễn phí:

- Mỗi pod vẫn có thể cần tạo kết nối, khởi tạo Liquibase và kiểm tra lịch sử.
- Pod chờ lock có thể kéo dài startup và làm rollout chậm.
- Nếu changeset có lỗi, nhiều pod có thể cùng gặp trạng thái startup thất bại.
- Lock của Liquibase không điều phối mọi DDL do DBA hoặc công cụ ngoài Liquibase thực hiện.
- Nếu một changeset chạy ngoài transaction hoặc DBMS có implicit commit, phải xử lý khả năng kết quả vật lý và lịch sử lệch nhau.

Không giả định lock table là cơ chế leader election hoặc deployment orchestration đầy đủ. Khi migration phức tạp, một job chuyên trách thường dễ quan sát và điều phối hơn.

## 4. Migration bằng tác vụ triển khai riêng

Trong mô hình này, pipeline tạo một tiến trình/job chỉ chịu trách nhiệm chạy Liquibase. Ứng dụng chỉ được rollout sau khi migration đạt điều kiện.

~~~text
Build artifact ứng dụng + changelog
              |
              v
Validate changelog / kiểm tra cấu hình
              |
              v
Review SQL preview + phê duyệt
              |
              v
Chạy migration job với migration credentials
              |
              v
Verify schema, data và DATABASECHANGELOG
              |
        +-----+-----+
        |           |
      PASS        FAIL
        |           |
        v           v
Rollout app     Dừng release,
version mới     điều tra / sửa
        |
        v
Readiness + smoke test
~~~

### 4.1. Ưu điểm

- Có một chủ thể migration rõ ràng, thay vì mọi replica tự chạy.
- Có thể cấp migration credentials riêng và không cấp DDL cho runtime user.
- Dễ đặt approval, cửa sổ triển khai, giới hạn thời gian và quy tắc dừng.
- Có thể chạy trước rollout app, quan sát trạng thái DB và xử lý lỗi độc lập.
- Dễ tổ chức migration theo batch hoặc theo từng database/tenant.
- Có thể lưu log, SQL preview và kết quả verify thành artifact của pipeline.

### 4.2. Chi phí và trách nhiệm bổ sung

- Cần duy trì job definition, datasource, secret, artifact và quyền chạy.
- Pipeline phải đảm bảo changelog job và image ứng dụng thuộc cùng release.
- Nếu migration thành công nhưng rollout app thất bại, database ở trạng thái mới trong khi ứng dụng cũ vẫn chạy.
- Nếu có nhiều database, pipeline cần ghi nhận kết quả từng đích và xử lý partial success.
- Cần xác định ai chịu trách nhiệm resume hoặc forward fix sau khi job thất bại.

Migration job riêng không tự làm migration an toàn. Nó chỉ tạo một điểm điều phối rõ hơn; chất lượng changeset, transaction, lock và khả năng rollback vẫn phải được thiết kế theo DBMS.

## 5. So sánh hai lựa chọn

| Tiêu chí | Chạy khi Spring Boot startup | Tác vụ migration riêng |
|---|---|---|
| Độ phức tạp ban đầu | Thấp | Cao hơn do cần pipeline/job |
| Số tiến trình chạy Liquibase | Có thể bằng số instance khởi động | Thường một job cho mỗi đơn vị triển khai |
| Thời điểm chạy | Khi application context khởi tạo | Theo thứ tự do CI/CD/orchestrator điều phối |
| Quyền DDL | Có thể phải cấp cho app datasource | Có thể tách migration user khỏi runtime user |
| Approval/cửa sổ bảo trì | Khó điều phối chi tiết hơn | Dễ đặt gate và lịch triển khai |
| Migration dài | Có thể kéo dài startup/readiness | Có thể theo dõi độc lập trước rollout |
| Nhiều replica | Các instance có thể chờ cùng lock | Tránh lặp startup migration ở từng replica |
| Failure | Pod mới có thể không startup | Job thất bại, pipeline dừng rollout |
| Database mới nhưng app cũ | Có thể xảy ra khi startup migration chạy trên một instance mới | Có thể chủ động kiểm tra backward compatibility trước rollout |
| Multi-tenant/multi-database | Khó điều phối nếu nhiều đích | Dễ lập tiến độ riêng từng tenant/database |
| Phù hợp | Thay đổi nhỏ, đơn giản, môi trường dev/test | Production phức tạp, DDL lớn, nhiều replica, quyền tách biệt |

## 6. Quyết định theo đặc tính migration

Không chọn mô hình chỉ dựa trên kích thước đội phát triển. Hãy phân loại migration:

| Đặc tính | Startup có thể phù hợp? | Job riêng thường phù hợp hơn? |
|---|---|---|
| Thêm một bảng nhỏ, không có dữ liệu cũ | Có | Không bắt buộc |
| Thêm cột nullable, DDL nhanh đã kiểm chứng | Có thể | Có thể, tùy quy trình release |
| Thêm constraint cần quét bảng lớn | Thận trọng | Thường phù hợp hơn |
| Tạo index concurrent/online | Có thể bị giới hạn bởi transaction và thời gian | Thường phù hợp hơn |
| Backfill hàng triệu bản ghi theo lô | Không nên gắn với startup | Có; thường dùng job dữ liệu riêng phối hợp Liquibase |
| Cần DBA approval hoặc maintenance window | Khó | Có |
| Migration nhiều database theo thứ tự | Phức tạp | Có |
| Migration tenant theo batch/canary | Khó kiểm soát | Có |
| Môi trường local/test tạo schema mới | Rất phù hợp | Không nhất thiết |

Một job riêng cũng không nên chứa một transaction khổng lồ chỉ vì nó chạy ngoài startup. Backfill lớn nên có checkpoint, giới hạn batch, throttle và khả năng resume; Liquibase có thể quản lý các bước mở rộng/enforce schema trong khi job chuyên trách chuyển dữ liệu.

## 7. Tổ chức changelog cho cả startup và job riêng

Không nhất thiết phải duy trì hai bộ changelog khác nhau. Một changelog đã được review có thể dùng cho cả hai cách chạy nếu:

- Cùng một định danh changeset và nội dung không bị thay đổi tùy tiện giữa các artifact.
- Context/label và parameters được cố định rõ theo môi trường.
- Cùng một database dùng cùng lịch sử Liquibase theo thiết kế.
- Các changeset đặc thù DBMS có filter đúng.
- Những changeset không phù hợp startup được tách khỏi luồng startup theo một kế hoạch được quản lý, không bị bỏ sót.

### 7.1. Master changelog

Ví dụ cấu trúc:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-expand-orders.yaml
  - include:
      file: db/changelog/changes/002-create-order-index.yaml
  - include:
      file: db/changelog/changes/003-enforce-orders.yaml
~~~

Master changelog xác định thứ tự include. Trong thực tế, đường dẫn cần đúng với vị trí artifact đóng gói và cấu hình relativeToChangelogFile nếu dùng. Không đổi file path/logicalFilePath tùy tiện sau khi changeset đã chạy vì định danh lịch sử có thể bị ảnh hưởng.

### 7.2. Phân nhóm theo context hoặc label

Context/label có thể chọn nhóm changeset, ví dụ:

- Một nhóm migration an toàn cho startup.
- Một nhóm migration vận hành cần chạy riêng.
- Một nhóm dữ liệu test hoặc demo chỉ dùng trong môi trường phù hợp.

Nhưng filter không tự quyết định ai chạy migration. Nếu startup không chạy nhóm changeset có label vận hành, pipeline phải có job riêng chạy nhóm đó; nếu không, schema sẽ mãi ở trạng thái thiếu một phần.

Đặc biệt, context/label không tạo history riêng. Một changeset đã được ghi vào DATABASECHANGELOG sẽ được xem là đã chạy theo định danh của nó; thay đổi filter không khiến changeset tự chạy lại trên cùng history.

### 7.3. Không sửa changeset đã triển khai để chuyển từ startup sang job

Nếu một changeset trước đây chạy ở startup và nay cần chuyển sang migration job, không sửa nội dung/định danh của changeset đã triển khai để ép chạy lại. Thay đổi cách điều phối nên được thiết kế cho changeset mới hoặc cho các môi trường chưa triển khai, có kiểm tra lịch sử. Giữ changelog đã phát hành ổn định giúp checksum và DATABASECHANGELOG còn đáng tin.

## 8. Cấu hình Spring Boot cho từng mô hình

### 8.1. Mô hình A: ứng dụng tự chạy Liquibase

Ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  datasource:
    url: jdbc:postgresql://db-host:5432/orders
    username: orders_migration
    password: ${ORDERS_DB_PASSWORD}
~~~

Trong cấu hình này, datasource được dùng cho Liquibase thường là datasource chính theo auto-configuration mặc định. Cần kiểm tra nếu dự án khai báo nhiều DataSource hoặc custom bean. Hãy xác minh bean Liquibase thực sự dùng connection nào, default schema nào và user nào.

Có thể dùng profile riêng để bật startup migration ở local/test và tắt trong production khi job riêng đã chịu trách nhiệm. Tuy nhiên, profile phải được kiểm soát; nếu production vô tình bật auto-run đồng thời với migration job, hai đường thực thi sẽ cạnh tranh cùng history lock và làm khó điều tra.

### 8.2. Mô hình B: tắt auto-run ở ứng dụng, chạy CLI/job

Ở application production:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Job triển khai dùng CLI hoặc một runner riêng với cùng changelog và datasource migration:

~~~bash
liquibase --defaults-file=./config/orders-production.properties validate
liquibase --defaults-file=./config/orders-production.properties status --verbose
liquibase --defaults-file=./config/orders-production.properties update-sql
liquibase --defaults-file=./config/orders-production.properties update
~~~

Đây là ví dụ cho CLI hiện đại; cú pháp lệnh sinh SQL có thể hiển thị dưới tên <code>updateSQL</code> ở một số phiên bản. Cần kiểm tra <code>liquibase --help</code> của phiên bản dự án. Không truyền password trực tiếp trên command line nếu nó có thể xuất hiện trong process list hoặc log; dùng secrets/config an toàn.

Ứng dụng chỉ tắt auto-run khi đã xác định job riêng là chủ thể cập nhật schema. Nếu cả job và ứng dụng đều tắt Liquibase, migration sẽ không được thực hiện.

### 8.3. Mô hình C: SpringLiquibase bean riêng

Trong ứng dụng có nhiều datasource hoặc muốn dùng migration credential riêng, có thể tạo bean Liquibase tường minh:

~~~java
@Bean
SpringLiquibase ordersLiquibase(
        @Qualifier("ordersMigrationDataSource") DataSource dataSource) {
    SpringLiquibase liquibase = new SpringLiquibase();
    liquibase.setDataSource(dataSource);
    liquibase.setChangeLog(
        "classpath:/db/changelog/db.changelog-master.yaml");
    liquibase.setDefaultSchema("orders");
    liquibase.setLiquibaseSchema("migration_control");
    return liquibase;
}
~~~

Đây là ví dụ minh họa API SpringLiquibase; package import, setter và cách cấu hình có thể thay đổi theo phiên bản. Phải đảm bảo:

- Bean nhận đúng migration datasource qua @Qualifier.
- Không có auto-configured Liquibase bean chạy thêm ngoài dự kiến.
- Bean phụ thuộc được khởi tạo sau khi migration hoàn tất.
- Runtime datasource không được dùng nhầm credential DDL.
- Nếu có nhiều Liquibase bean, thứ tự giữa các database phụ thuộc được điều phối rõ.

Trong nhiều hệ thống production, chạy bean Liquibase trong application context vẫn có nghĩa migration gắn với startup. Nếu mục tiêu là tách khỏi vòng đời ứng dụng, một process/job riêng thường làm ranh giới vận hành rõ hơn.

## 9. Điều phối startup, readiness và rolling deployment

### 9.1. Readiness không thay thế migration gate

Readiness probe chỉ cho biết ứng dụng có thể nhận traffic theo logic health check. Nó không tự chứng minh tất cả database đã được migrate đúng nếu:

- Ứng dụng có nhiều datasource nhưng health check chỉ kiểm tra một nguồn.
- Migration được tách riêng nhưng pipeline rollout app không chờ job hoàn tất.
- Ứng dụng vẫn startup dù một tính năng phụ thuộc database chưa sẵn sàng.
- Một changeset được lọc bởi context/label mà pipeline không chạy ở bước khác.

Với migration job riêng, gate của pipeline phải chờ job thành công và verify schema trước khi rollout. Với startup migration, readiness của từng instance chỉ đạt sau khi quá trình khởi tạo thành công, nhưng cần tính đến những instance cũ vẫn đang phục vụ trên schema vừa thay đổi.

### 9.2. Rolling deployment và backward compatibility

Trong rolling deployment, ứng dụng V1 và V2 có thể cùng chạy trong một khoảng thời gian. Vì vậy, migration trước rollout thường cần **mở rộng schema theo hướng tương thích ngược**:

1. Thêm cột/bảng mới mà V1 có thể bỏ qua.
2. Deploy V2 có khả năng đọc/ghi cấu trúc mới và tương thích với dữ liệu cũ.
3. Backfill dữ liệu theo lô và kiểm tra.
4. Enforce constraint sau khi mọi writer đã đáp ứng quy tắc mới.
5. Xóa cấu trúc cũ ở release sau khi hết instance và job phụ thuộc.

Nếu startup migration của V2 xóa cột cũ ngay khi pod đầu tiên khởi động, các pod V1 còn lại có thể lỗi. Chạy job riêng trước rollout cũng có thể gây lỗi tương tự nếu job áp dụng DDL phá tương thích. Điểm quyết định là **tính tương thích của migration**, không chỉ nơi nó chạy.

### 9.3. Tránh migration chạy khi autoscaling

Nếu startup migration bật ở mọi instance, scale-out do tải có thể kéo theo nhiều tiến trình Liquibase khởi động. Dù lock table phối hợp các tiến trình, đây vẫn là công việc không cần thiết và có thể tăng áp lực kết nối/lock. Với production autoscaling, nên cân nhắc một job migration độc lập hoặc cơ chế đảm bảo chỉ một chủ thể chạy migration.

## 10. Xử lý lỗi theo mô hình startup hay job riêng

### 10.1. Startup migration thất bại

Khi Liquibase startup thất bại:

1. Xem lỗi gốc: kết nối, quyền, precondition, SQL, checksum, lock timeout hay DBMS.
2. Xác định application context đã hoàn tất hay chưa; không giả định pod đã sẵn sàng.
3. Kiểm tra DATABASECHANGELOG và object vật lý trong database.
4. Xác định DDL có transaction/implicit commit hoặc changeset có runInTransaction=false không.
5. Nếu có nhiều replica, kiểm tra tiến trình nào đang giữ lock và các instance khác đang chờ.
6. Không tự xóa DATABASECHANGELOGLOCK hoặc sửa DATABASECHANGELOG chỉ để pod khởi động.
7. Sửa nguyên nhân, thử trên môi trường tương ứng và triển khai lại theo kế hoạch.

Không mặc định mọi thay đổi đều được rollback hoàn toàn khi startup thất bại. DDL có thể có kết quả một phần tùy DBMS và transaction.

### 10.2. Migration job thất bại

Job riêng giúp tách lỗi migration khỏi lỗi startup ứng dụng, nhưng không làm thay đổi trạng thái DB tự động. Pipeline cần:

- Dừng rollout ứng dụng mới nếu gate migration chưa đạt.
- Giữ ứng dụng hiện tại chạy nếu schema trung gian còn tương thích.
- Lưu log, SQL, changeset id, DBMS version và connection target.
- Kiểm tra changeset đã ghi history chưa và object có tồn tại/valid không.
- Quyết định retry, forward fix, rollback hoặc restore dựa trên trạng thái thực.
- Có cơ chế resume khi nhiều tenant/database đã chạy thành công một phần.

### 10.3. Phân biệt ba trạng thái

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Job exit 0 | Process báo thành công | Vẫn verify schema, data, history và application contract |
| Job exit non-zero | Process báo lỗi | Điều tra SQL, history và object; không rerun mù quáng |
| Job bị kill/timeout | Không biết chắc câu cuối đã hoàn tất đến đâu | Đọc trạng thái vật lý và lịch sử trước khi tiếp tục |

Không dùng việc pod đã restart hoặc job đã chạy lại như bằng chứng database sạch.

## 11. Chọn quyền và bảo mật

### 11.1. Least privilege

Một cách tổ chức:

| Principal | Quyền dự kiến |
|---|---|
| Runtime user | SELECT/INSERT/UPDATE/DELETE trên object nghiệp vụ cần dùng |
| Migration user | DDL cần thiết, quyền đọc metadata và cập nhật bảng history/lock |
| Read-only/analytics user | SELECT trên tập object được phép |
| DBA/break-glass | Quyền quản trị có kiểm soát và audit riêng |

Không cấp superuser cho migration user nếu chỉ cần quyền tạo/sửa object trong schema ứng dụng. Một số thao tác extension, tablespace hoặc quyền đặc biệt có thể cần DBA; hãy tách phần provisioning đặc quyền khỏi migration ứng dụng nếu phù hợp.

### 11.2. Secret và cấu hình môi trường

- Không commit password vào <code>application.yaml</code>, changelog hoặc Docker image.
- Không ghi credential vào log CLI hoặc SQL preview.
- Tách secret theo môi trường và database.
- Hạn chế người có quyền chạy rollback/destructive changes.
- Ghi audit ai chạy job, artifact nào, database nào và thời điểm nào.
- Thu hồi hoặc xoay migration credential theo chính sách bảo mật.

Job riêng thường giúp tách credential rõ hơn, nhưng startup migration cũng có thể dùng datasource/bean riêng nếu được cấu hình cẩn thận.

## 12. Kiểm chứng changelog trước khi chạy

Cho dù migration chạy ở startup hay job riêng, vẫn cần quy trình kiểm chứng:

1. **Validate:** changelog được parse và kiểm tra theo khả năng Liquibase.
2. **Status:** xác định changeset nào pending trên database đích.
3. **SQL preview:** review SQL dự kiến cho đúng DBMS/version và parameters.
4. **Preconditions:** kiểm tra bảng, cột, dữ liệu, schema và DBMS.
5. **Test:** chạy trên database đại diện với dữ liệu gần thực tế.
6. **Rollback review:** sinh/review rollback SQL và xác nhận giới hạn phục hồi dữ liệu.
7. **Verify:** sau update, kiểm tra object, dữ liệu, lịch sử và ứng dụng.

Ví dụ lệnh CLI tham khảo:

~~~bash
liquibase --defaults-file=./config/staging.properties validate
liquibase --defaults-file=./config/staging.properties status --verbose
liquibase --defaults-file=./config/staging.properties update-sql
~~~

Tên lệnh xem trước SQL phụ thuộc phiên bản; dùng <code>updateSQL</code> nếu đó là tên được CLI của dự án hỗ trợ. Validate không chứng minh SQL chạy an toàn; status không mô phỏng lock; SQL preview không thay thế kiểm thử trên DBMS thực tế.

### 12.1. Cố định artifact giữa preview và update

Không review SQL của một commit rồi chạy update bằng image có changelog khác. Pipeline cần gắn:

- Commit hoặc release identifier.
- Digest image/artifact chứa changelog.
- Liquibase version và JDBC driver.
- DBMS/version và datasource target.
- Contexts, labels và changelog parameters.
- SQL preview và kết quả phê duyệt.

Sau khi approval, dùng chính artifact và bộ tham số đó để thực thi. Nếu thay đổi changelog, phải review lại.

## 13. Backfill và migration dài: đừng biến startup thành batch processor

Một changeset <code>UPDATE orders SET status_code = ...</code> có thể chạy trong thời gian dài trên bảng lớn. Nếu nó chạy lúc startup:

- Pod mới có thể không sẵn sàng trong nhiều phút hoặc lâu hơn.
- Các pod khác có thể chờ lock Liquibase.
- DDL/DML có thể tạo WAL/redo/binlog lớn và replication lag.
- Một timeout hoặc restart có thể làm trạng thái giữa chừng khó xác định.

Với backfill lớn, thường nên:

1. Dùng Liquibase tạo cột/structure tương thích.
2. Chạy job dữ liệu theo batch có checkpoint, throttle và retry.
3. Đối soát số hàng và mapping.
4. Dùng Liquibase enforce constraint hoặc index khi dữ liệu đã sẵn sàng.
5. Xác minh ứng dụng trước khi contract.

Job backfill không nhất thiết phải là Liquibase CLI. Có thể là batch job ứng dụng hoặc công cụ dữ liệu riêng, miễn có ownership, version, log, khả năng tiếp tục và bằng chứng hoàn tất.

Không đưa vòng lặp hàng triệu bản ghi vào một changeset startup chỉ vì muốn mọi thứ được thực hiện ở cùng thời điểm.

## 14. Nhiều datasource và nhiều database

Một Spring Boot application có thể kết nối nhiều datasource. Nếu mỗi database cần migration riêng, mỗi đích cần changelog, credentials, history và trạng thái triển khai rõ ràng.

| Cách chạy | Lưu ý |
|---|---|
| Nhiều Liquibase bean trong app | Cần gắn đúng datasource, changelog, schema/history và thứ tự khởi tạo |
| Một job cho mỗi database | Dễ ghi nhận kết quả từng database và chạy theo dependency |
| Một job điều phối nhiều database | Cần checkpoint, giới hạn concurrency và xử lý partial failure |

Không giả định nhiều database được cập nhật nguyên tử chỉ vì một application startup hoặc một pipeline gọi nhiều Liquibase instance. Nếu database A thành công và B thất bại, hệ thống ở trạng thái trung gian. Ứng dụng phải tương thích trạng thái đó hoặc pipeline phải có phương án khắc phục.

Với schema-per-tenant, một job có thể lặp cùng changelog cho từng tenant nhưng phải xác định history scope phù hợp. Dùng một DATABASECHANGELOG chung cho nhiều tenant độc lập có thể khiến changeset chỉ được ghi nhận một lần, dẫn tới các tenant sau không chạy.

## 15. Rollback ứng dụng và rollback database

Rollback image ứng dụng không tự rollback Liquibase. Tương tự, rollback Liquibase không tự deploy lại image cũ.

Một quy trình release an toàn thường ưu tiên migration tương thích ngược:

- Chạy changeset expand trước hoặc trong giai đoạn rollout.
- Đảm bảo app cũ vẫn hoạt động trên schema mới.
- Deploy app mới.
- Chỉ enforce hoặc contract sau khi hết phiên bản cũ.

Khi có lỗi:

1. Xác định lỗi nằm ở code, schema hay dữ liệu.
2. Nếu app cũ tương thích schema hiện tại, rollback app và giữ schema mở rộng.
3. Nếu cần rollback DB, xác định instance/writer nào phải dừng hoặc chuyển đổi trước.
4. Review rollback SQL, dữ liệu đã phát sinh và khả năng khôi phục.
5. Xác minh DATABASECHANGELOG, catalog, dữ liệu và app sau thao tác.

Không dùng tag Liquibase như snapshot database; rollback DDL không phục hồi giá trị đã mất do drop column, delete hoặc biến đổi không đảo được. Với dữ liệu không thể đảo, forward fix hoặc restore có kiểm soát có thể phù hợp hơn.

## 16. Các mô hình triển khai tham khảo

### 16.1. Local và test: startup migration

Phù hợp khi database có thể tạo lại, migration ngắn và mục tiêu là giảm thao tác thiết lập môi trường.

Quy trình:

1. Developer chạy ứng dụng.
2. Spring Boot tạo datasource và Liquibase.
3. Liquibase tạo/cập nhật schema.
4. Test chạy trên schema được chuẩn bị.

Nếu dùng database ephemeral, có thể bật Liquibase auto-run để mỗi lần tạo môi trường mới đều có schema đúng.

### 16.2. Production một service, migration nhỏ

Có thể giữ startup migration nếu:

- Chỉ có ít replica hoặc startup được điều phối.
- DDL đã được đo và không gây lock dài.
- Runtime/migration permission được chấp nhận hoặc tách datasource đúng.
- Thay đổi backward-compatible.
- Có quan sát và quy trình xử lý startup failure.

### 16.3. Production nhiều replica: job riêng

Một quy trình thường dễ kiểm soát:

1. Build app artifact có changelog.
2. Chạy validate/status/SQL preview.
3. Approval.
4. Chạy migration job một lần cho database/đơn vị migration.
5. Verify schema và dữ liệu.
6. Rollout các replica ứng dụng.
7. Chạy smoke test và giám sát.

Nếu migration thất bại, pipeline dừng rollout; ứng dụng cũ tiếp tục chạy nếu schema trung gian tương thích.

### 16.4. Nhiều tenant/database

Dùng một orchestration job có danh sách đích, nhưng mỗi đích cần:

- Datasource/secret chính xác.
- History/lock scope đúng.
- Checkpoint riêng.
- Kết quả validate/status/update/verify riêng.
- Giới hạn concurrency.
- Kế hoạch resume/forward fix khi partial failure.

Không đánh dấu cả đợt thành công nếu còn tenant hoặc database chưa được nâng cấp.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bật Liquibase ở mọi replica mà không đánh giá startup | Pod chờ lock, rollout chậm | Dùng migration job hoặc kiểm soát rõ startup strategy |
| Tắt auto-run nhưng không có job riêng | Schema không được cập nhật | Chỉ định một migration owner và gate triển khai |
| Job và app cùng chạy Liquibase không có điều phối | Hai đường migration cạnh tranh | Chọn một chủ thể hoặc dùng cùng history/lock với kế hoạch rõ |
| Dùng runtime user có quyền DDL rộng | Tăng blast radius khi ứng dụng bị xâm nhập | Tách migration credentials |
| Job chạy changelog khác image app | Schema và code không khớp | Gắn artifact digest và changelog version |
| Startup migration có backfill dài | Instance không ready, DB chịu tải lâu | Tách expand, batch backfill và enforce |
| Dùng lock table như deployment lock toàn hệ thống | DBA hoặc công cụ khác vẫn có thể sửa object | Điều phối DDL ngoài Liquibase riêng |
| Dựa vào readiness để biết migration đã hoàn tất cho mọi DB | Datasource phụ hoặc tenant có thể còn pending | Gate từng đích và verify history/object |
| Rollback app rồi kỳ vọng schema tự quay lại | App cũ có thể không tương thích schema mới | Thiết kế backward compatibility và rollback riêng |
| Chạy update-sql rồi đổi artifact trước update | SQL được review không còn là SQL được chạy | Cố định artifact và parameters |
| Dùng context để tách lịch sử | Changeset vẫn được ghi nhận theo history chung | Tách history theo đơn vị migration nếu cần |
| Retry ngay sau job timeout | Có thể đụng object đã tạo một phần | Kiểm tra catalog và DATABASECHANGELOG trước retry |
| Nhiều datasource nhưng không dùng Qualifier | Liquibase có thể chạy nhầm database | Gắn bean với datasource rõ ràng |
| Tắt Liquibase ở cả ứng dụng và pipeline | Không có tiến trình nào cập nhật schema | Kiểm tra trách nhiệm migration trong release manifest |
| Chạy contract cùng release đầu tiên | Rollback ứng dụng cũ bị phá tương thích | Trì hoãn contract tới khi hết phụ thuộc cũ |

## 18. Bài thực hành

### Bài A — So sánh startup và job riêng

Tạo một ứng dụng Spring Boot nhỏ dùng PostgreSQL và Liquibase với changeset tạo bảng <code>customer</code>.

1. Bật <code>spring.liquibase.enabled=true</code> và khởi động app.
2. Xác nhận DATABASECHANGELOG ghi changeset và bảng được tạo.
3. Khởi động lại app, xác nhận changeset không chạy lại.
4. Tắt auto-run, chạy cùng changelog bằng CLI trong môi trường test.
5. Xác nhận history không tạo changeset trùng và schema vẫn đúng.

Mục tiêu: hiểu auto-run và CLI có thể dùng cùng lịch sử, nhưng phải trỏ đúng datasource/changelog.

### Bài B — Mô phỏng nhiều replica

Khởi chạy hai tiến trình app cùng datasource trong môi trường thử nghiệm. Quan sát:

- Tiến trình nào lấy DATABASECHANGELOGLOCK.
- Tiến trình còn lại xử lý khi lock đang được giữ.
- Lịch sử sau khi cả hai khởi động.
- Điều gì xảy ra khi migration job bị ngắt.

Không thực hiện mô phỏng bằng cách xóa lock table hoặc can thiệp trực tiếp vào history. Dùng môi trường cô lập và đọc log/catalog.

### Bài C — Pipeline migration job

Tổ chức pipeline:

1. Build image app có changelog.
2. Chạy validate và SQL preview.
3. Chạy job migration với credential riêng.
4. Chỉ khi job thành công và verify đạt mới rollout app.
5. Mô phỏng job thất bại; xác nhận pipeline dừng rollout.
6. Kiểm tra app cũ còn tương thích schema sau expand.

Mục tiêu: tách rõ migration gate với deployment gate của ứng dụng.

### Bài D — Migration dài và rollout tương thích

Thiết kế một thay đổi thêm cột mới, backfill theo batch, enforce NOT NULL và xóa cột cũ ở release sau. Xác định:

- Bước nào có thể chạy lúc startup.
- Bước nào cần job riêng.
- Phiên bản ứng dụng nào tương thích với từng schema stage.
- Chỉ số nào khiến job phải pause.
- Khi rollback app, có cần rollback database không?

Mục tiêu: chọn nơi chạy dựa trên tính chất migration và hợp đồng tương thích, không dựa trên thói quen.

## 19. Checklist chọn mô hình

- [ ] Đã xác định DBMS/version, kích thước bảng và loại DDL/DML.
- [ ] Thời gian chạy và lock behavior đã được thử trên dữ liệu đại diện.
- [ ] Số replica và cơ chế autoscaling đã được tính đến.
- [ ] Chọn rõ startup migration hay job riêng; không có hai chủ thể không điều phối.
- [ ] Runtime user và migration user có quyền phù hợp.
- [ ] Datasource, changelog, default schema, history schema và parameters đúng môi trường.
- [ ] Context/label không làm bỏ sót changeset bắt buộc.
- [ ] Artifact được preview chính là artifact sẽ chạy update.
- [ ] Với job riêng, pipeline chỉ rollout app sau khi migration và verify đạt.
- [ ] Với startup migration, readiness/startup failure và nhiều replica đã được kiểm thử.
- [ ] Migration tương thích với phiên bản ứng dụng đang chạy trong rolling deployment.
- [ ] Backfill lớn có batch, checkpoint, throttle và khả năng resume.
- [ ] Rollback app và rollback DB có quy trình riêng, đã thử với dữ liệu mới.
- [ ] Có kiểm tra catalog, DATABASECHANGELOG, lock state và chức năng sau migration.
- [ ] Có owner xử lý partial failure và kế hoạch forward fix/restore.

## 20. Ghi nhớ

Spring Boot startup migration gắn việc cập nhật schema với vòng đời application context. Cách này đơn giản và phù hợp với thay đổi ngắn, có thể dự đoán, đặc biệt trong local/test. Migration job riêng tách database change khỏi startup của từng replica, giúp điều phối quyền, approval, thời gian chạy và thứ tự rollout; đổi lại pipeline phải quản lý artifact, checkpoint và trạng thái partial failure.

Lựa chọn nên dựa trên **đặc tính migration, số replica, mức độ khóa, quyền DDL, yêu cầu sẵn sàng và khả năng tương thích ứng dụng**. Dù chạy ở đâu, Liquibase vẫn cần changelog ổn định, preconditions phù hợp, lịch sử DATABASECHANGELOG nhất quán và kiểm chứng sau update. Quy trình production thường an toàn hơn khi mở rộng schema trước, chạy backfill riêng nếu lớn, xác thực rồi mới enforce và contract ở release sau. Khi lỗi, rollback ứng dụng không tự rollback database; phải chọn đường phục hồi theo ma trận tương thích app/schema/data đã được thử nghiệm.
