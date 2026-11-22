# Phối hợp hoàn tác cơ sở dữ liệu với phiên bản ứng dụng

## 1. Vấn đề: rollback database không đồng nghĩa rollback hệ thống

Khi một bản phát hành ứng dụng gây lỗi, đội vận hành thường muốn quay nhanh về bản ứng dụng trước đó. Nhưng ứng dụng mới có thể đã sử dụng cấu trúc bảng, ràng buộc hoặc ý nghĩa dữ liệu mới. Nếu chỉ triển khai lại phiên bản ứng dụng cũ, nó có thể không đọc được dữ liệu vừa được tạo. Nếu chỉ chạy rollback Liquibase, ứng dụng đang hoạt động có thể mất bảng/cột mà nó cần.

Ví dụ, phiên bản ứng dụng V1 đọc và ghi cột <code>orders.legacy_status</code>. Migration thêm <code>orders.status_code</code>, ứng dụng V2 bắt đầu ghi cột mới, sau đó một changeset xóa <code>legacy_status</code>. Khi phát hiện lỗi và đưa ứng dụng trở lại V1, ứng dụng cũ sẽ lỗi nếu cột cũ đã bị xóa. Ngược lại, nếu rollback database để xóa <code>status_code</code> trong khi còn instance V2 đang chạy, các request của V2 cũng có thể lỗi và dữ liệu vừa ghi vào cột mới có thể mất.

Do đó, câu hỏi quan trọng không chỉ là **“Liquibase có chạy lệnh rollback được không?”**, mà còn là **“Sau rollback, phiên bản ứng dụng nào còn chạy đúng với schema và dữ liệu thực tế?”**.

Bài thuộc chương **Hoàn tác** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là quản lý thay đổi schema và dữ liệu bằng Liquibase thông qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài tập trung vào **hợp đồng tương thích giữa ứng dụng và database trong suốt quá trình phát hành, hoàn tác và khôi phục**.

Sau bài học, người đọc có thể:

1. Phân biệt rollback ứng dụng, rollback Liquibase, rollback transaction và khôi phục dữ liệu.
2. Thiết kế ma trận tương thích giữa phiên bản ứng dụng, schema và định dạng dữ liệu.
3. Áp dụng chiến lược expand–migrate–contract để có cửa sổ hoàn tác an toàn.
4. Xác định thứ tự dừng traffic, đổi phiên bản ứng dụng và xử lý schema khi sự cố.
5. Lập kế hoạch rollback theo tag/count, thử nghiệm rollback SQL và quyết định khi nào nên forward fix.
6. Đưa các tiêu chí an toàn, lịch sử changeset, backup và kiểm thử vào Spring Boot hoặc pipeline CI/CD.

## 2. Bốn thao tác thường bị gọi chung là “rollback”

| Thao tác | Đối tượng bị thay đổi | Nó **không** tự làm gì? |
|---|---|---|
| **Rollback phiên bản ứng dụng** | Chuyển image/JAR/config từ V2 về V1 | Không tự trả schema và dữ liệu về thời điểm V1 |
| **Rollback Liquibase** | Thực thi các change đảo ngược để hoàn tác những changeset được chọn | Không triển khai JAR cũ, không hoàn nguyên mọi dữ liệu đã bị biến đổi |
| **Rollback transaction DBMS** | Hủy các thao tác chưa commit trong transaction được DBMS hỗ trợ | Không đảo ngược DDL đã implicit commit hoặc thay đổi đã commit |
| **Restore/PITR database** | Khôi phục trạng thái dữ liệu/schema từ backup hoặc nhật ký giao dịch đến một thời điểm | Không tự điều phối phiên bản ứng dụng, client, queue và những hệ thống ngoài database |

Một vài khác biệt cần nhớ:

- Liquibase ghi lịch sử changeset vào <code>DATABASECHANGELOG</code>; bảng này **không phải bản sao lưu database**.
- Khóa <code>DATABASECHANGELOGLOCK</code> giúp phối hợp tiến trình Liquibase, nhưng **không khóa tất cả request ứng dụng** để chờ rollback.
- Một thay đổi như <code>DROP COLUMN</code> có thể có rollback cú pháp bằng <code>ADD COLUMN</code>, nhưng giá trị dữ liệu đã mất không tự xuất hiện trở lại.
- Một <code>UPDATE</code> đã commit không nhất thiết có phép đảo; phải lưu nguồn trước thay đổi nếu cần phục hồi chính xác.
- Một vài DBMS cho phép DDL giao dịch; DBMS khác có implicit commit. Kế hoạch chỉ dựa trên khả năng rollback transaction của PostgreSQL có thể thất bại khi chuyển sang MySQL hoặc Oracle.

**Kết luận:** hoàn tác toàn hệ thống là một bài toán **phối hợp phiên bản, dữ liệu, traffic và quy trình phát hành**, không phải một câu lệnh duy nhất.

## 3. Hợp đồng tương thích giữa ứng dụng và schema

Xét ba phiên bản schema minh họa:

- **S1:** bảng <code>orders</code> có <code>legacy_status</code>, chưa có <code>status_code</code>.
- **S2:** có cả hai cột; <code>status_code</code> còn nullable và dữ liệu cũ được chuyển dần.
- **S3:** <code>status_code</code> được áp ràng buộc bắt buộc; <code>legacy_status</code> vẫn còn trong giai đoạn chuyển tiếp.
- **S4:** cột <code>legacy_status</code> bị loại bỏ khi các ứng dụng cũ đã hết phụ thuộc.

Ứng dụng được thiết kế như sau:

- **A1:** chỉ đọc/ghi <code>legacy_status</code>.
- **A2:** hỗ trợ cả hai cột; đọc với logic chuyển tiếp và ghi bảo đảm tính nhất quán theo thỏa thuận.
- **A3:** đọc <code>status_code</code> làm nguồn chính, nhưng vẫn có khả năng vận hành khi cột cũ còn tồn tại.
- **A4:** chỉ dùng cột mới và không còn mã cho cột cũ.

Ma trận tương thích **minh họa**, không phải luật tự động của Liquibase:

| Phiên bản ứng dụng | S1: cột cũ | S2: hai cột, nullable | S3: cột mới bắt buộc, cột cũ còn | S4: chỉ cột mới |
|---|---|---|---|---|
| A1 — chỉ cột cũ | Có | Có, nếu thay đổi không phá hành vi cũ | Có điều kiện: các ghi của A1 không làm vi phạm ràng buộc mới | **Không** |
| A2 — hỗ trợ chuyển tiếp | Không nếu bắt buộc có cột mới | Có | Có nếu writer đáp ứng ràng buộc | Không nếu mã vẫn cần cột cũ |
| A3 — dùng cột mới | Không | Có sau khi dữ liệu sẵn sàng | Có | Có nếu không còn phụ thuộc cột cũ |
| A4 — chỉ cột mới | Không | Có điều kiện theo dữ liệu | Có | Có |

Trong bảng, từ “Có” chỉ đúng khi cả các truy vấn, quyền, kiểu dữ liệu, giá trị nghiệp vụ và các luồng ghi đều tương thích. Không được suy ra tương thích chỉ vì ORM khởi động được hoặc một trang giao diện đọc dữ liệu thành công.

### 3.1. Tương thích đọc khác tương thích ghi

Một ứng dụng A1 có thể đọc schema S3 mà không lỗi, nhưng nếu nó tạo đơn hàng mới và chỉ điền <code>legacy_status</code> trong khi <code>status_code</code> đã có NOT NULL, thao tác ghi có thể thất bại. Đây là tình huống **tương thích đọc nhưng không tương thích ghi**.

Khi review rollback, phải đánh giá ít nhất bốn dạng hoạt động:

1. Đọc bản ghi được tạo trước migration.
2. Đọc bản ghi được tạo bằng ứng dụng mới.
3. Ghi/cập nhật bản ghi từ ứng dụng cũ sau khi quay lại.
4. Các job nền, báo cáo, trigger, batch và tích hợp ngoài vẫn truy cập database.

Nếu kiểu enum, ý nghĩa tiền tệ hoặc quan hệ khóa thay đổi, một dữ liệu hợp lệ theo A3 có thể không còn ý nghĩa đối với A1, dù hai phiên bản dùng cùng tên cột.

### 3.2. Ma trận phải được chứng minh bằng thử nghiệm

Không chỉ điền ma trận bằng suy đoán. Các trường hợp thuộc **cửa sổ rollback dự kiến** phải được chạy kiểm thử tích hợp với:

- Schema đã migrate.
- Bản ứng dụng cũ và mới.
- Dữ liệu cũ, dữ liệu mới và dữ liệu biên.
- Các đường đọc/ghi chính, job nền và truy vấn SQL trực tiếp.
- Cấu hình feature flag và cách ORM mapping tên cột thực tế.

Một hợp đồng release nên ghi rõ: “A1 có thể hoạt động trên S2 trong thời gian chuyển tiếp” thay vì tuyên bố chung chung “migration backward-compatible”.

## 4. Nguyên tắc nền: mở rộng trước, thu hẹp sau

Chiến lược phổ biến để giữ đường rollback ứng dụng là **expand–migrate–contract**:

~~~text
S1 + A1
  |
  | Expand: tạo cột mới nhưng không phá cột cũ
  v
S2 + A1
  |
  | Deploy ứng dụng chuyển tiếp
  v
S2 + A2
  |
  | Backfill + kiểm tra dữ liệu
  v
S2 + A3 (chỉ khi dữ liệu sẵn sàng)
  |
  | Enforce constraint theo cửa sổ đã duyệt
  v
S3 + A3
  |
  | Hết mọi phiên bản cũ và hết cửa sổ rollback
  v
S4 + A4 (Contract)
~~~

Một giai đoạn có thể cần nhiều release cách nhau vài ngày hoặc vài tuần. **Không nên gộp mở rộng schema, chuyển ứng dụng, dọn dữ liệu và xóa cột cũ trong một lần phát hành nếu còn yêu cầu rollback ứng dụng nhanh.**

### 4.1. Expand: migration phải “chấp nhận” ứng dụng cũ

Ví dụ YAML thêm cột mới theo hướng tương thích:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 101-add-orders-status-code
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
        - not:
            - columnExists:
                tableName: orders
                columnName: status_code
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status_code
                  type: varchar(24)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: status_code
~~~

Ở đây cột mới nullable và không yêu cầu A1 ghi thêm dữ liệu. A1 thường có thể tiếp tục chạy trên S2 nếu các truy vấn cũ không bị đổi ngữ nghĩa. Tuy nhiên, ví dụ rollback <code>dropColumn</code> chỉ là **cách đảo DDL**. Nếu A2 hoặc A3 đã ghi dữ liệu vào cột mới, thực hiện rollback này có thể xóa dữ liệu. Vì thế, trong sự cố ứng dụng, **giữ cột mới và rollback ứng dụng** thường là lựa chọn ít phá hủy hơn so với rollback schema ngay lập tức.

### 4.2. Migrate: đồng bộ cách đọc/ghi, rồi chuyển dữ liệu

Trong giai đoạn chuyển tiếp, A2 có thể:

- Ghi cả <code>legacy_status</code> và <code>status_code</code> ở cùng giao dịch nếu phù hợp, hoặc dùng cơ chế đồng bộ có kiểm chứng.
- Đọc cột mới khi đã có giá trị hợp lệ, fallback sang cột cũ đối với bản ghi chưa chuyển.
- Theo dõi tỷ lệ NULL và số trường hợp hai cột không đồng nhất.
- Tiếp tục hỗ trợ những instance ứng dụng A1 còn chạy trong rolling deploy.

Nếu dữ liệu cũ cần mapping sang giá trị mới, phải xác định các giá trị có thể **khôi phục lại** và các giá trị **không thể biểu diễn** trên mô hình cũ. Một mapping nhiều giá trị mới thành một giá trị cũ làm mất thông tin; rollback ứng dụng có thể không khôi phục được ý nghĩa dữ liệu.

Backfill nên theo lô có thể tiếp tục, thay vì đặt một thay đổi dữ liệu khổng lồ trong một transaction Liquibase dài. Việc hoàn tất job cần được xác nhận bằng đối soát, không chỉ bằng trạng thái “job đã chạy xong”.

### 4.3. Enforce: ràng buộc mới phải phù hợp với các writer còn tồn tại

Sau khi chuyển dữ liệu, nhóm muốn đặt <code>NOT NULL</code> cho cột mới. Một precondition có thể bảo vệ việc enforce:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 102-enforce-orders-status-code
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: status_code
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM orders WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
      rollback:
        - dropNotNullConstraint:
            tableName: orders
            columnName: status_code
            columnDataType: varchar(24)
~~~

Điều kiện dữ liệu đạt **không tự bảo đảm ứng dụng A1 đã ngừng ghi**. Nếu A1 vẫn tạo hàng chỉ có <code>legacy_status</code>, NOT NULL có thể làm request của A1 thất bại. Vì vậy, phải bảo đảm mọi writer còn hoạt động đã hỗ trợ quy tắc mới **trước khi enforce**, hoặc có chiến lược DBMS-side tương thích đã được kiểm thử.

Trong một số DBMS, bước thêm NOT NULL có thể quét bảng và giữ khóa; cần đánh giá thời gian triển khai và cơ chế tách giai đoạn thích hợp. Rollback <code>dropNotNullConstraint</code> cho phép cột lại nullable; nó **không làm dữ liệu mới trở nên tương thích với ứng dụng cũ**.

### 4.4. Contract: bước phá vỡ khả năng hoàn tác nhanh

Chỉ xóa <code>legacy_status</code> sau khi:

1. Không còn instance A1/A2 nào phụ thuộc cột cũ.
2. Các job, báo cáo, consumer và dữ liệu được xuất ra bên ngoài đã được nâng cấp.
3. Mọi bản ghi đã có dữ liệu mới đúng nghĩa.
4. Cửa sổ rollback về A1 đã kết thúc hoặc đã có phương án restore được duyệt.
5. Có snapshot/backup nếu việc xóa cột làm mất dữ liệu không thể tái dựng.

<code>DROP COLUMN</code> không nên xuất hiện như một thao tác “dọn cho gọn” ngay trong changeset expand. **Contract là một quyết định phát hành và quản trị dữ liệu**, không chỉ là bước chỉnh changelog.

## 5. Bảng quyết định: rollback ứng dụng, database hay cả hai?

Khi xảy ra lỗi, trước hết xác định chính xác **ứng dụng đang chạy, schema hiện tại và dữ liệu mới đã được tạo**.

| Trạng thái hệ thống | Phương án thường đáng cân nhắc | Kiểm chứng bắt buộc |
|---|---|---|
| S2 mới mở rộng; A2 lỗi; A1 vẫn tương thích S2 | Quay A2 về A1, **giữ S2** | A1 đọc/ghi được các bản ghi được tạo trong thời gian A2 chạy |
| S2; A2 đã ghi dữ liệu chỉ A2 hiểu | Giữ schema, vô hiệu hóa tính năng lỗi hoặc forward fix; cần xử lý dữ liệu trước khi dùng A1 | Tính tương thích semantic của dữ liệu, không chỉ tên cột |
| S3 có NOT NULL; A1 không điền cột mới | Không rollback ứng dụng về A1 ngay | Trước hết dùng bản ứng dụng chuyển tiếp hoặc thay đổi quy tắc ghi có kiểm chứng |
| S4 đã xóa cột cũ | Không coi rollback ứng dụng về A1 là khả thi | Cần tái tạo dữ liệu/khôi phục cấu trúc hoặc forward fix |
| Migration DDL lỗi giữa chừng | Chưa vội rollback hay rerun | Đọc metadata DBMS và <code>DATABASECHANGELOG</code> |
| Lỗi chỉ nằm ở một query/feature flag của A3 | Có thể tắt tính năng hoặc hotfix mà không đổi schema | Xác nhận tính năng tắt không tiếp tục tạo dữ liệu không tương thích |

**Quy tắc ưu tiên:** lựa chọn tác động ít phá hủy nhất nhưng vẫn đưa hệ thống về trạng thái đúng hợp đồng. Trong nhiều sự cố ứng dụng, rollback image hoặc tắt feature flag **không yêu cầu rollback schema**.

## 6. Thứ tự thao tác trong sự cố

Không có một thứ tự “rollback DB trước hay app trước” phù hợp mọi tình huống. Thứ tự phụ thuộc ma trận tương thích và khả năng ngăn dữ liệu mới phát sinh.

### 6.1. Trường hợp ứng dụng cũ vẫn tương thích schema mới

Nếu A1 đã được thử nghiệm trên S2 và dữ liệu mới đọc được bởi A1, có thể:

1. Xác định vấn đề và đóng băng các rollout/changelog tiếp theo.
2. Tắt feature flag hoặc hạn chế những luồng đang tạo dữ liệu không tương thích.
3. Chuyển traffic/instance từ A2 về A1 theo cơ chế rolling/canary hoặc blue–green phù hợp.
4. Xác minh API đọc/ghi, job nền, thông điệp hàng đợi và đối soát dữ liệu.
5. **Giữ S2** để điều tra và triển khai bản sửa; chỉ rollback cột mới nếu chắc chắn không còn sử dụng và dữ liệu không cần giữ.

Đây thường là đường phục hồi ngắn hơn và ít rủi ro hơn việc đồng thời hoàn tác schema.

### 6.2. Trường hợp schema phải được hoàn tác thật

Ví dụ cần rollback một ràng buộc mới làm A1 không thể ghi. Trình tự phải được điều chỉnh theo hệ thống:

1. Xác định tất cả writer và reader còn phụ thuộc vào ràng buộc hoặc schema mới.
2. Hạn chế traffic, dừng hoặc drain các job không tương thích theo quy trình vận hành.
3. Đưa hệ thống về **phiên bản trung gian tương thích cả schema trước và sau**, nếu có.
4. Đánh giá dữ liệu phát sinh kể từ migration và lưu lại thông tin cần phục hồi.
5. Review rollback SQL, dependency, constraint, quyền và transaction behavior.
6. Thực thi rollback theo phạm vi đã được duyệt bằng cùng changelog artifact.
7. Xác minh schema, dữ liệu, lịch sử và khả năng đọc/ghi của ứng dụng mục tiêu.
8. Mở lại traffic có kiểm soát, giám sát lỗi và latency.

Không xóa cột khi còn instance đang đọc nó; không chuyển ứng dụng cũ sang schema thiếu cột mà nó bắt buộc dùng. Với hệ thống không thể dừng ghi, cần một kế hoạch tương thích trung gian hoặc forward fix; không ép một rollback mất an toàn.

### 6.3. Sự cố xảy ra khi đang rolling deployment

Trong khoảng thời gian A1 và A2 chạy đồng thời:

- Cả hai phải đọc/ghi đúng trên cùng schema trung gian.
- Feature flag có thể giúp ngăn A2 phát sinh dữ liệu chỉ A2 hiểu.
- Worker xử lý message và scheduled job phải được tính vào quá trình chuyển phiên bản; không chỉ nhìn web instances.
- Quay A2 về A1 không làm các message do A2 tạo biến mất. Payload hoặc dữ liệu mới vẫn có thể khiến A1 lỗi.
- Các thay đổi schema phá tương thích phải được tách sang release sau khi hết mọi instance A1.

Một rollback image “xong trong vài phút” không nhất thiết đưa business flow về hoạt động bình thường nếu dữ liệu hoặc message đã đi qua định dạng mới.

## 7. Sử dụng Liquibase rollback theo phạm vi

Liquibase cung cấp cơ chế rollback theo mốc tag, số changeset hoặc thời điểm trong các phiên bản/cách chạy được hỗ trợ. Cần kiểm tra **cú pháp chính xác trên CLI đang dùng**, vì cách viết lệnh/tùy chọn có thể khác theo phiên bản.

Các khái niệm chính:

| Cách chọn | Ý nghĩa | Rủi ro |
|---|---|---|
| **Rollback to tag** | Hoàn tác những changeset sau mốc được gắn tag | Tag đặt sai hoặc danh sách thay đổi sau tag chứa đối tượng không định rollback |
| **Rollback count** | Hoàn tác một số changeset đã được thực thi theo lịch sử | Không trùng số file hoặc số release; dễ lấy nhầm changeset |
| **Rollback to date** | Hoàn tác về mốc thời gian trong lịch sử triển khai | Phụ thuộc timestamp thực tế, không nhất thiết khớp thời điểm deploy app |
| **Rollback SQL preview** | Sinh SQL dự kiến để review trước hành động thật | Không bảo đảm DDL/khôi phục dữ liệu thành công khi thực thi |

Một tag trong Liquibase là **mốc lịch sử**, không phải bản snapshot schema và dữ liệu. Rollback tới tag có thể đảo nhiều changeset nằm sau tag, bao gồm cả các thay đổi không liên quan tới lỗi ứng dụng nếu đợt triển khai dùng chung changelog.

### 7.1. Gắn mốc release có chủ đích

Ví dụ changeset tạo mốc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 100-tag-before-orders-transition
      author: db-team
      changes:
        - tagDatabase:
            tag: release_before_orders_transition
~~~

Khi rollback tới tag, cần xem phiên bản Liquibase xử lý changeset <code>tagDatabase</code> và lịch sử sau mốc như thế nào; về nguyên tắc mục tiêu là đảo các changeset đã áp dụng **sau mốc được chọn**, không phải khôi phục toàn bộ database về ảnh chụp quá khứ.

Mỗi release nên ghi tag hoặc changelog version cùng image ứng dụng, commit, migration parameters và DBMS version. Mốc không đúng hoặc thiếu lịch sử tương ứng có thể khiến lệnh rollback không thực hiện đúng phạm vi mong muốn.

### 7.2. Quy trình preview và review rollback SQL

Ví dụ cách gọi **tham khảo** trên CLI hiện đại:

~~~bash
liquibase --defaults-file=./config/liquibase-staging.properties validate
liquibase --defaults-file=./config/liquibase-staging.properties history
liquibase --defaults-file=./config/liquibase-staging.properties rollback-sql --tag=release_before_orders_transition
~~~

Cần đối chiếu cú pháp của chính bản Liquibase đang sử dụng; có phiên bản/tích hợp dùng cách đặt tùy chọn hoặc tên lệnh khác. Các lệnh trên minh họa kiểm tra, **không phải lời mời chạy trực tiếp trên production**.

Trước khi thực thi rollback thật, phải kiểm tra:

- Mốc đã chọn có đúng với release và lịch sử database đó không?
- Những changeset nào thực sự sẽ bị đảo, thứ tự nào và có bao nhiêu?
- Mọi change đều có rollback hợp lệ hay có SQL thuần cần khai báo thủ công?
- SQL có xóa dữ liệu, column, index, foreign key, view hoặc làm mất tính tương thích với app không?
- Tài khoản có đủ quyền và DBMS có thể rollback loại DDL tương ứng không?
- Có phiên bản ứng dụng, job hoặc client nào sẽ bị lỗi sau mỗi bước không?

**Không thực hiện rollback count bằng cách đoán “release này có năm changeset”.** Các changeset bị lọc theo context, label, DBMS hoặc đã chạy từ trước có thể khiến số change đã ghi trong lịch sử khác số khai báo trong changelog.

### 7.3. Rollback không tự động xảy ra khi ứng dụng lỗi

Liquibase hỗ trợ lệnh rollback khi được yêu cầu, nhưng một request API lỗi hoặc ứng dụng startup lỗi không tự làm DBMS quay về tag trước phát hành. CI/CD phải có orchestration rõ ràng và kiểm soát quyền cho thao tác rollback.

Ở các môi trường có nhiều service cùng dùng database, chỉ dùng thông tin release của một service để chọn tag rollback có thể gây ảnh hưởng service khác. Cần kiểm tra phạm vi sở hữu schema và danh sách changeset thật sự sẽ bị hoàn tác.

## 8. Những thay đổi “có rollback SQL” nhưng không thể phục hồi dữ liệu

Đây là điểm dễ bị bỏ qua nhất khi phối hợp rollback với phiên bản ứng dụng.

| Thay đổi | Có thể đảo về mặt cấu trúc? | Vấn đề dữ liệu và ứng dụng |
|---|---|---|
| Thêm cột nullable | Có thể drop cột | Drop làm mất giá trị được ứng dụng mới ghi |
| Thêm NOT NULL | Có thể drop NOT NULL | Không đưa dữ liệu về kiểu/ý nghĩa mà app cũ hiểu |
| Thêm index | Có thể drop index | Thay đổi hiệu năng, kế hoạch truy vấn; không phải phục hồi dữ liệu |
| Rename column | Có thể rename ngược | App cũ/mới có thể đồng thời truy cập tên khác nhau |
| Drop column | Có thể thêm lại cột rỗng | Giá trị cũ không tự phục hồi |
| Chuyển đổi kiểu hoặc scale | Có thể có câu lệnh đổi ngược | Có thể đã làm tròn, mất chính xác hoặc không thể cast |
| UPDATE ánh xạ nhiều giá trị thành một | Có thể viết UPDATE ngược theo giả định | Không khôi phục được thông tin đã mất nếu không lưu bản gốc |
| DELETE dữ liệu | Có thể INSERT lại nếu có snapshot | Thiếu hàng, khóa, thời điểm và quan hệ nếu không lưu trạng thái trước |
| Đổi enum/ý nghĩa nghiệp vụ | Có thể giữ nguyên schema | App cũ không hiểu giá trị mới hoặc xử lý sai logic |

### 8.1. Ví dụ biến đổi không thể đảo

Giả sử V2 gom <code>legacy_status</code> nhận các giá trị <code>PENDING_REVIEW</code> và <code>PENDING_PAYMENT</code> thành <code>status_code = 'PENDING'</code>.

Sau chuyển đổi, không thể suy ra một hàng mang <code>'PENDING'</code> trước đây thuộc trạng thái nào. Một câu rollback:

~~~sql
UPDATE orders
SET legacy_status = 'PENDING_REVIEW'
WHERE status_code = 'PENDING';
~~~

không khôi phục dữ liệu đúng; nó gán tất cả hàng về một trạng thái tùy ý. Nếu cần rollback dữ liệu:

- Giữ <code>legacy_status</code> hoặc lưu mapping gốc và định danh từng hàng trong thời gian chuyển tiếp.
- Kiểm tra tính đầy đủ của dữ liệu nguồn và sự xuất hiện của các giá trị mới chưa từng có ở V1.
- Có snapshot/audit trước biến đổi, với thời gian lưu giữ phù hợp.
- Chuẩn bị phương án restore chọn lọc hoặc forward fix; không hứa “rollback một bước” khi thông tin đã mất.

### 8.2. Quyền hoàn tác phải dựa trên dữ liệu đã phát sinh

Ví dụ V2 tạo thêm loại trạng thái <code>REFUNDED_PARTIALLY</code> mà V1 không biết. Dù bảng và cột cũ vẫn còn, rollback A2 về A1 có thể gây lỗi hiển thị hoặc tính sai báo cáo nếu V1 chỉ xử lý các trạng thái cũ. Có thể cần:

1. Tạm dừng tạo loại giá trị mới.
2. Đánh giá có mapping ngược hợp lệ hay không.
3. Nếu không thể ánh xạ mà không mất nghĩa, giữ ứng dụng mới và làm forward fix hoặc triển khai adapter tương thích.
4. Bổ sung kiểm thử để phiên bản rollback xử lý chính xác dữ liệu được tạo trước khi sự cố xảy ra.

**Khả năng rollback thuộc về hợp đồng dữ liệu**, không chỉ khả năng ứng dụng chạy cùng schema.

## 9. Backup và point-in-time recovery không phải rollback release thông thường

Khi không thể đảo dữ liệu bằng SQL, có thể phải dùng backup hoặc point-in-time recovery (PITR). Tuy nhiên:

- Khôi phục cả database về một thời điểm có thể làm mất **mọi giao dịch hợp lệ** phát sinh sau thời điểm đó, không chỉ dữ liệu liên quan tới bản release.
- Các hệ thống ngoài database như queue, cache, object storage, webhook hoặc bên thanh toán không tự quay về cùng thời điểm.
- Replica và downstream consumers có thể đã nhận dữ liệu mới; cần kế hoạch khôi phục nhất quán giữa các hệ thống.
- RPO (mức mất dữ liệu chấp nhận được) và RTO (thời gian phục hồi chấp nhận được) phải được xác định trước.

### 9.1. Khi nào cần restore thay vì rollback Liquibase?

Restore có thể là giải pháp cuối cùng nếu migration xóa dữ liệu lớn và không còn cách tái dựng, hoặc trạng thái schema/dữ liệu đã bị phá hủy không thể forward fix an toàn. Quy trình phục hồi cần được kiểm thử, không nên lần đầu thao tác trên production trong lúc sự cố.

Một phương án ít mất dữ liệu hơn trong một số tình huống là khôi phục backup vào một database **riêng**, đối chiếu và phục hồi chọn lọc các hàng cần thiết. Nhưng cách này vẫn cần giải quyết khóa, transaction và những ghi mới phát sinh. Đừng tự chạy restore toàn hệ thống khi chưa đánh giá thiệt hại và phụ thuộc.

### 9.2. Backup trước migration chưa đủ

Ngoài việc có backup, phải biết:

- Có thực sự restore được trong RTO đã đặt không?
- Backup có nhất quán và được mã hóa/kiểm soát truy cập không?
- Dữ liệu và transaction nào xuất hiện sau backup cần giữ lại?
- Hệ thống ngoài DB có cần replay hoặc reconciliation không?
- Sau phục hồi, bảng <code>DATABASECHANGELOG</code> có khớp trạng thái schema và artifact changelog sẽ được dùng tiếp không?

Không suy rằng “đã chạy snapshot” đồng nghĩa có thể hoàn tác an toàn toàn bộ release bằng một thao tác.

## 10. Changeset, checksum và lịch sử sau rollback

Liquibase nhận diện một changeset thông qua <code>id</code>, <code>author</code> và đường dẫn changelog (hoặc <code>logicalFilePath</code> theo cấu hình). Bảng <code>DATABASECHANGELOG</code> ghi lịch sử thực thi và checksum của các changeset.

Khi rollback một changeset, Liquibase thường loại bỏ hoặc điều chỉnh bản ghi lịch sử theo cơ chế rollback được hỗ trợ, để sau đó một lệnh update có thể xem changeset là chưa áp dụng và có khả năng chạy lại. Điều này làm phát sinh yêu cầu thiết kế:

- Changeset có SQL rollback phải đưa database về **trạng thái cho phép thực thi lại**; chỉ xóa bản ghi lịch sử mà đối tượng vẫn tồn tại sẽ khiến lần update sau lỗi.
- Không sửa nội dung changeset đã triển khai để ép SQL mới chạy; nếu cần thay đổi, hãy tạo changeset tiếp theo và đối chiếu checksum.
- Không chỉnh <code>DATABASECHANGELOG</code> bằng tay như một cách “hoàn tác không cần SQL”.
- Nếu rollback DDL thất bại giữa chừng hoặc DBMS implicit commit, có thể phải xử lý trạng thái vật lý và lịch sử theo quy trình khắc phục riêng.
- Nếu một changeset gồm nhiều thay đổi không có transaction, một phần có thể hoàn tất dù trạng thái ghi lịch sử chưa đúng kỳ vọng; cần kiểm tra trực tiếp catalog trước retry.

### 10.1. Rollback không đồng nghĩa với chạy lại phiên bản code tương ứng

Sự kiện “Liquibase rollback tới tag T” không biết image ứng dụng nào sẽ được deploy sau đó. Pipeline phải ánh xạ **app artifact → schema contract → changelog state → dữ liệu hỗ trợ**. Nếu không có bảng ánh xạ này, tag T chỉ là một mốc trong lịch sử database, chưa đủ để quyết định hệ thống sẽ chạy đúng.

### 10.2. Tránh nhầm rerun với rollback

Các thuộc tính như <code>runAlways</code> hoặc <code>runOnChange</code> có mục đích riêng trong cơ chế thực thi changeset. Chúng không thay thế rollback và có thể làm lịch sử hoặc dữ liệu khó dự đoán nếu sử dụng để cố “đồng bộ” schema khi triển khai ứng dụng cũ. Đừng dùng các thuộc tính này như công tắc hoàn tác release.

## 11. Precondition khi rollback và sự khác biệt trước–sau

<code>preConditions</code> thường được sử dụng để bảo vệ **thay đổi tiến (forward change)** trong changelog, ví dụ:

- Bảng đã tồn tại.
- Cột chưa tồn tại.
- Dữ liệu đáp ứng điều kiện trước khi thêm constraint.
- DBMS/role phù hợp.

Không được suy rằng tất cả precondition của forward change sẽ được đánh giá y hệt và đủ để bảo vệ rollback. Đối với rollback SQL, cần **kiểm tra trạng thái thực tế tại thời điểm hoàn tác**. Ví dụ trước khi drop index, phải biết index có tồn tại, có đúng định nghĩa, được ứng dụng mới yêu cầu hay không, và có cùng tên trong schema khác không.

### 11.1. Dùng HALT thay vì đánh dấu đã xử lý khi không tương thích

Nếu schema/metadata không đúng giả định, policy tốt cho migration rủi ro là dừng và điều tra. Không dùng <code>MARK_RAN</code> để đánh dấu một thay đổi quan trọng đã xong khi thực tế chưa tạo hoặc chưa gỡ đối tượng.

Với kế hoạch rollback:

1. Dựng danh sách đối tượng do từng changeset sở hữu.
2. Truy vấn catalog để xác nhận định nghĩa thật, không chỉ sự tồn tại theo tên.
3. Đối chiếu dữ liệu mới và dependency từ app đang chạy.
4. Review rollback SQL và thử trên database clone.
5. Chỉ thực thi sau khi gate tương thích đã đạt.

Một precondition đạt tại thời điểm trước đó không thay thế bước kiểm tra khi xảy ra sự cố thực tế; dữ liệu và app version có thể đã thay đổi.

## 12. Blue–green, canary và rolling deployment

### 12.1. Blue–green không có nghĩa database được nhân đôi

Trong nhiều hệ thống blue–green, môi trường ứng dụng xanh và lam cùng truy cập **một database**. Chuyển traffic về bản ứng dụng cũ dễ hơn chuyển database về schema cũ, vì schema đã thay đổi là tài nguyên dùng chung.

Nếu A1 và A2 cùng database trong cửa sổ cutover, cả hai phải được thiết kế chạy trên S2. Không xóa một cột chỉ vì phần lớn traffic đã chuyển sang A2; vẫn có thể tồn tại request cũ, background jobs hoặc kết nối trì hoãn.

### 12.2. Canary là cơ hội đo tương thích trước khi contract

Triển khai A2 cho một tỷ lệ request nhỏ giúp quan sát lỗi với schema S2; nếu thất bại, có thể giảm traffic A2 mà không rollback schema. Tuy nhiên:

- Canary vẫn có thể tạo dữ liệu mới mà A1 sẽ đọc.
- Job nền không theo tỷ lệ traffic web có thể chạy hoàn toàn bằng code mới.
- Consumer của message, mobile client hoặc integration bên ngoài có vòng đời riêng.

Vì vậy, canary phải có **data compatibility gate** và chiến lược tắt/đảo tính năng, không chỉ giám sát HTTP errors.

### 12.3. Rolling deployment cần một cửa sổ giao thoa

Một release rolling thường có khoảng thời gian A1 và A2 đồng thời hoạt động. Giai đoạn expand phải hỗ trợ giao thoa đó. Thời điểm contract chỉ an toàn khi có bằng chứng rằng:

- Không còn instance cũ đang xử lý request.
- Các hàng đợi hoặc scheduled jobs cũ đã được drain/nâng cấp.
- External consumer vẫn hỗ trợ schema/format mới.
- Dữ liệu mới không cần chuyển ngược thành dạng cũ để phục hồi hệ thống.

Nếu không thể chứng minh, phải kéo dài giai đoạn tương thích thay vì rút ngắn vì áp lực dọn schema.

## 13. Spring Boot và trách nhiệm chạy Liquibase

Trong Spring Boot, Liquibase có thể được kích hoạt khi ứng dụng khởi động. Điều này phù hợp với một số hệ thống, nhưng khi rollback application image, bản JAR cũ có thể mang changelog cũ trong artifact. Nếu database đã ở trạng thái mới, cần biết ứng dụng cũ có cố chạy Liquibase và xảy ra bất đồng về changelog hay không.

Nguyên tắc triển khai:

- Không để rollback ứng dụng vô tình trở thành cơ chế rollback database tự động. Bình thường, Liquibase update của JAR cũ **không tự đảo những changeset mới** đã ghi trong database.
- Xác định changelog master và lịch sử có tương thích với các phiên bản JAR có thể được deploy lại.
- Với DDL rủi ro, cân nhắc chạy migration bằng job CI/CD chuyên trách và điều khiển <code>spring.liquibase.enabled</code> cho các instance ứng dụng theo kiến trúc đã chọn.
- Gắn bản migration vào release manifest độc lập với việc bật/tắt app feature.
- Hạn chế việc nhiều image ứng dụng thuộc các release khác nhau tự tìm cách chạy migration cùng lúc.

### 13.1. Ví dụ cấu hình chiến lược job chuyên trách

Trong một kiến trúc có CI/CD chịu trách nhiệm migration trước khi rollout:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Đây chỉ là cấu hình minh họa cho **instance ứng dụng** khi đã có job migration riêng. Không tắt Liquibase ở cả job lẫn ứng dụng mà không xác định ai chịu trách nhiệm cập nhật schema. Nếu chạy Liquibase qua Spring Boot riêng, job phải dùng đúng changelog, datasource, schema và bộ tham số của release.

### 13.2. Những lỗi dễ phát sinh khi rollback JAR

- A1 thiếu mapping một cột mà A2 vừa tạo nhưng A1 vẫn có thể bỏ qua an toàn: không nhất thiết cần rollback schema.
- A1 có kiểm tra schema nghiêm ngặt qua ORM hoặc công cụ khác và từ chối cấu trúc S2 dù truy vấn nghiệp vụ tương thích: cần thử thật, không suy từ quy tắc SQL.
- A1 vẫn tạo bản ghi thiếu giá trị mà S3 bắt buộc: rollback image sẽ gây lỗi ghi.
- A1 dùng stored procedure/view đã bị thay thế với contract mới: có thể lỗi dù tên bảng/cột giữ nguyên.
- Hệ thống nhiều datasource chạy Liquibase vào sai database khi đổi profile: phải kiểm tra cấu hình hiệu lực trước khi deploy.

Khả năng rollback phải được thử với **cấu hình chạy thật**, không chỉ với source code của phiên bản cũ.

## 14. Pipeline CI/CD: release manifest và các gate

Một manifest có thể ghi cả phiên bản ứng dụng và trạng thái database kỳ vọng:

~~~yaml
release: orders-service-2026.11
application:
  currentImage: orders-service:v3
  rollbackCandidate: orders-service:v2
database:
  engine: postgresql
  expectedSchemaStage: S3
  changelog: db/changelog/db.changelog-master.yaml
  lastApprovedTag: release_before_orders_transition
compatibility:
  v2WithS3: pending_verification
  v3WithS3: pending_verification
  rollbackDataMapping: pending_verification
gates:
  liquibaseValidate: pending
  rollbackSqlReviewed: pending
  compatibilityMatrixTested: pending
  restoreProcedureTested: pending
~~~

Đây là **mẫu thông tin quản trị release**, không phải định dạng cấu hình bắt buộc của Liquibase. Các trạng thái <code>pending</code> chỉ được đổi sang đạt sau khi có bằng chứng cụ thể.

### 14.1. Gate trước khi triển khai app mới

1. Chốt image, commit, changelog và phiên bản Liquibase/JDBC driver.
2. Xác nhận DBMS, URL/database, schema và parameters đã được resolve.
3. Review changeset sẽ chạy; ghi mốc phát hành được phê duyệt.
4. Kiểm tra dữ liệu hiện tại, quyền và tác động DDL.
5. Thử A1 trên schema đã expand S2.
6. Có kế hoạch tắt tính năng mới hoặc rollback app nếu A2 gặp sự cố.
7. Có backup/restore, RTO/RPO và owner quyết định cho thay đổi phá dữ liệu.

### 14.2. Gate trước khi rollback

1. Xác định chính xác thay đổi nào gây lỗi: app behavior, dữ liệu hay schema.
2. Xác minh image rollback đích và khả năng đọc/ghi trên schema hiện tại.
3. Nếu phải rollback database, chọn tag/count/date theo lịch sử thật và preview SQL.
4. Kiểm tra dữ liệu đã ghi sau release có cần bảo toàn hoặc chuyển đổi không.
5. Xác định những writer cần dừng, drain hoặc chuyển sang chế độ tương thích.
6. Có người phê duyệt, lịch thực thi, quan sát và ngưỡng dừng.
7. Sau rollback, chạy smoke test và đối soát catalog, <code>DATABASECHANGELOG</code>, dữ liệu và metrics ứng dụng.

### 14.3. Tại sao cần thử rollback ở môi trường đại diện?

Một rollback SQL hợp lệ trên database trống không chứng minh rollback an toàn khi production chứa dữ liệu mới hoặc còn phiên bản app mới chạy. Nên kiểm tra trên bản sao dữ liệu được xử lý phù hợp và trong môi trường cô lập:

- Cài release cũ → migrate tới release mới → tạo dữ liệu mới → thử rollback app.
- Test cả trạng thái chỉ expand, đang backfill, đã enforce và đã contract.
- Thử cả đường rollback app không đổi DB và đường rollback DB có kiểm soát.
- Kiểm tra bảng lịch sử, index, constraint và dữ liệu sau các lần retry.
- Đánh giá thời gian khóa/restore và ảnh hưởng tới chức năng đọc/ghi.

Không dùng test này để xóa dữ liệu thật trong production.

## 15. Khi nào nên forward fix thay vì rollback?

**Forward fix** nghĩa là triển khai changeset hoặc ứng dụng sửa lỗi dựa trên trạng thái hiện tại, thay vì cố đưa toàn bộ DB về trạng thái trước đó.

Forward fix thường đáng cân nhắc khi:

- Một số dữ liệu mới không thể chuyển ngược về định dạng cũ mà không mất thông tin.
- Migration đã drop/transform dữ liệu mà rollback cú pháp không thể phục hồi.
- Rollback sẽ ảnh hưởng quá nhiều service dùng chung database.
- DDL đã implicit commit hoặc chạy ngoài transaction và trạng thái còn lại không thể đảo đơn giản.
- Bản sửa nhỏ có thể giữ nguyên contract schema và phục hồi hoạt động nhanh, đáng tin hơn.

Nhưng forward fix cũng có rủi ro; không được xem là “luôn tốt hơn”. Với lỗi nghiêm trọng đang gây mất dữ liệu, có thể cần cô lập writer, dùng restore hoặc chuyển hệ thống vào chế độ bảo vệ trước khi áp bản sửa.

### 15.1. Ví dụ quyết định

Giả sử sau release A3, một endpoint mới trả sai JSON vì serializer lỗi, trong khi database S3 đã được migrate và tất cả writer hoạt động bình thường. Nếu A2 tương thích S3, rollback ứng dụng về A2 có thể an toàn mà không đổi DB. Nếu A2 không tương thích S3, hotfix serializer trên A3 có thể là cách ít rủi ro hơn rollback cả schema.

Quyết định phải dựa trên **ma trận tương thích đã thử, tình trạng dữ liệu và mức độ khẩn cấp**, không dựa trên thói quen “cứ lỗi là rollback tất cả”.

## 16. Multi-service, multi-tenant và môi trường nhiều phiên bản

Trong kiến trúc microservices chia sẻ database, một changeset có thể thay đổi bảng đang phục vụ nhiều service. Dù release của service A có lỗi, rollback constraint mà service B đang phụ thuộc có thể khiến B mất bảo đảm dữ liệu.

Yêu cầu cần có:

- Phân quyền sở hữu schema và chính sách phối hợp thay đổi giữa service.
- Danh sách producer/consumer dùng từng bảng, cột, view và kiểu dữ liệu.
- Kế hoạch publish/subscribe hoặc message compatibility khi dữ liệu có format mới.
- Cửa sổ hỗ trợ phiên bản API/client cũ đủ dài trước contract.
- Quy trình rollback được duyệt ở cấp phạm vi dữ liệu dùng chung, không chỉ cấp một deployment.

### 16.1. Nhiều tenant/schema

Nếu từng tenant có lịch sử migration hoặc schema riêng, không giả định một rollback tag trên một tenant là đủ cho tất cả. Cần:

1. Xác định tenant đã thực hiện changeset nào và hiện đang ở trạng thái nào.
2. Xác minh ứng dụng được rollback hỗ trợ từng trạng thái schema khác nhau.
3. Giới hạn concurrency của migration/rollback để tránh quá tải DBMS.
4. Ghi checkpoint cho tenant đã hoàn tất và tenant bị lỗi.
5. Không áp rollback hàng loạt nếu một nhóm tenant đã tạo dữ liệu mới không còn tương thích app cũ.

Một hệ thống multi-tenant có thể cần giữ ứng dụng hỗ trợ nhiều schema stage trong giai đoạn rollout. Đây là ràng buộc thiết kế ứng dụng, không phải khả năng do Liquibase tự cung cấp.

## 17. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Rollback ứng dụng về V1 khi cột V1 cần đã bị drop | V1 lỗi ngay khi đọc/ghi | Kiểm tra ma trận tương thích; dời contract sang release sau |
| Rollback DB khi còn instance V2 dùng cột mới | Request V2 lỗi, có thể mất dữ liệu mới | Drain/chuyển instance trước hoặc giữ schema mở rộng |
| Coi SQL drop/add column là rollback đầy đủ | Dữ liệu đã bị xóa không tự phục hồi | Có snapshot/mapping/restore hoặc forward fix |
| Gộp expand, backfill và drop trong một changeset | Không có điểm dừng an toàn, rollback khó | Tách theo giai đoạn và kiểm chứng |
| Thêm NOT NULL trước khi writer cũ ngừng ghi NULL | App rollback hoặc request A1 thất bại | Enforce sau khi mọi writer tương thích |
| Dùng rollback count theo số file | Hoàn tác sai changeset đã thực thi | Review lịch sử thực tế, danh sách SQL trước khi chạy |
| Coi Liquibase tag là snapshot database | Không thể khôi phục dữ liệu đã mất | Kết hợp backup/PITR và kế hoạch phục hồi |
| Không kiểm thử dữ liệu được tạo bằng app mới trên app cũ | Semantic mismatch, lỗi nghiệp vụ âm thầm | Test các mẫu dữ liệu mới và mapping ngược |
| Sửa changeset đã chạy rồi redeploy JAR cũ | Checksum/historical state lệch | Giữ changelog đã phát hành, tạo changeset mới |
| Chỉnh <code>DATABASECHANGELOG</code> để “hoàn tác” | Lịch sử khác schema thật | Dùng rollback đúng quy trình, kiểm tra catalog |
| Bỏ qua background job/consumer cũ | Ghi dữ liệu lỗi trong giai đoạn chuyển tiếp | Inventory mọi writer, drain và phối hợp version |
| Khôi phục toàn database mà không xét transaction mới | Mất dữ liệu hợp lệ và lệch hệ thống ngoài DB | Đánh giá RPO/RTO, restore chọn lọc và reconciliation |
| Chỉ test ORM startup của bản cũ | API ghi vẫn có thể vi phạm constraint | Test đọc/ghi, job, queue và trạng thái dữ liệu biên |
| Tắt Liquibase trên mọi đường deploy | Schema mới không được áp dụng | Chỉ định chủ thể chạy migration rõ ràng |
| Rollback toàn bộ schema dùng chung vì một service lỗi | Các service khác có thể mất tính tương thích | Xác định phạm vi sở hữu và phê duyệt liên service |

## 18. Bài thực hành tình huống

### Tình huống A — Ứng dụng V2 lỗi sau expand

Trạng thái: S2 đã thêm cột <code>status_code</code> nullable; A2 lỗi một endpoint. A1 đã được thử nghiệm trên S2 và chỉ dùng <code>legacy_status</code>.

**Câu hỏi:** có cần chạy <code>rollback</code> để drop <code>status_code</code> trước khi quay A1 không?

**Phân tích:** thường không cần. Nên tắt tính năng lỗi hoặc chuyển app về A1, **giữ S2** nếu cột mới không làm A1 lỗi. Cần kiểm tra dữ liệu A2 đã tạo có còn đọc/ghi được ở A1 không. Drop cột mới chỉ để khôi phục app có thể làm mất dữ liệu và tạo thêm downtime.

### Tình huống B — Đã enforce NOT NULL nhưng còn writer V1

Trạng thái: S3 có <code>status_code NOT NULL</code>, A1 chỉ điền <code>legacy_status</code>; release mới lỗi và đội vận hành muốn rollback A2 về A1.

**Câu hỏi:** lệnh rollback app có an toàn không?

**Phân tích:** không, vì A1 có thể ghi NULL vào cột mới. Cần dùng ứng dụng chuyển tiếp A2/A3 có logic ghi tương thích, hoặc có một kế hoạch rollback ràng buộc và bảo toàn dữ liệu đã được review. Trước khi tháo NOT NULL, phải kiểm tra các luồng ứng dụng mới có đang dựa vào ràng buộc đó không.

### Tình huống C — Đã contract và xóa cột cũ

Trạng thái: S4 không còn <code>legacy_status</code>, A4 chỉ dùng cột mới. Người dùng báo lỗi khiến đội muốn rollback về A1.

**Câu hỏi:** chạy rollback Liquibase rồi deploy A1 có đủ không?

**Phân tích:** thường không. Thêm lại cột cũ bằng DDL không khôi phục các giá trị cũ, còn một số giá trị mới có thể không ánh xạ ngược. Cần xác minh dữ liệu có lưu lịch sử/backup không, các client nào cần định dạng mới và một phương án forward fix hoặc phục hồi nghiệp vụ.

### Tình huống D — Rollback theo tag ảnh hưởng nhiều service

Trạng thái: sau tag T, cả service Orders và Payments đều đã chạy changesets vào cùng database. Service Orders có lỗi, muốn rollback đến T.

**Câu hỏi:** tag T có đủ làm “điểm rollback cho riêng Orders” không?

**Phân tích:** không. Rollback đến T có thể đảo cả những changeset của Payments. Phải kiểm tra danh sách changeset đã thực thi, phạm vi schema và dependency; cân nhắc một changeset sửa lỗi mục tiêu hoặc quy trình phục hồi có phối hợp thay vì rollback toàn bộ đến T.

## 19. Checklist phê duyệt rollback liên phiên bản

- [ ] Xác định **ứng dụng hiện tại, ứng dụng đích, schema hiện tại và schema đích**.
- [ ] Ma trận tương thích đã được thử cho đọc, ghi, job nền và dữ liệu tạo bằng bản mới.
- [ ] Nếu định rollback app đơn thuần, schema mới vẫn hỗ trợ app cũ.
- [ ] Nếu định rollback database, không còn writer/reader cần đối tượng sắp bị gỡ.
- [ ] Dữ liệu mới có thể được đọc bởi bản app cũ hoặc có mapping/chiến lược bảo toàn.
- [ ] Các thay đổi destructive (drop column, delete, transform lossy) có backup/restore hoặc forward fix.
- [ ] Liquibase tag/count/date đã đối chiếu với <code>DATABASECHANGELOG</code> thật; rollback SQL đã review.
- [ ] Không sửa changeset/checksum lịch sử hoặc dùng <code>MARK_RAN</code> để che lệch trạng thái.
- [ ] Đã xác minh transaction/DDL rollback behavior theo DBMS và kế hoạch khi fail giữa chừng.
- [ ] Đã điều phối traffic, instance cũ/mới, consumer, batch và các service dùng chung dữ liệu.
- [ ] RTO/RPO, owner, quyền thực thi và ngưỡng dừng đã được phê duyệt.
- [ ] Có smoke test, đối soát schema/catalog/dữ liệu và quan sát hệ thống sau hoàn tác.
- [ ] Release manifest ghi rõ artifact, changelog, tag, tham số, kết quả kiểm tra và quyết định thực thi.

## 20. Kết luận

Trong Liquibase, rollback một changeset là khả năng **hoàn tác phần thay đổi schema hoặc dữ liệu mà changelog mô tả**; nó không đảm bảo phiên bản ứng dụng cũ vẫn hoạt động hoặc mọi dữ liệu mới có thể chuyển ngược. Điểm quyết định an toàn là **hợp đồng tương thích giữa app version, schema stage và ý nghĩa dữ liệu**.

Thiết kế đáng tin cậy là **expand không phá tương thích → triển khai app chuyển tiếp → chuyển dữ liệu và kiểm chứng → enforce khi mọi writer đã sẵn sàng → contract sau khi hết cửa sổ rollback**. Khi xảy ra sự cố, hãy ưu tiên đường phục hồi đã được thử với ảnh hưởng thấp nhất: rollback ứng dụng và giữ schema mở rộng nếu có thể; chỉ rollback Liquibase khi danh sách changeset, rollback SQL, tác động dữ liệu và phiên bản ứng dụng đích đều được xác minh. Với biến đổi không thể đảo, cần phương án forward fix hoặc restore có kiểm soát. Cách phối hợp này giúp lịch sử migration bằng changelog/changeset/checksum duy trì tính tin cậy trong triển khai Spring Boot và CI/CD.
