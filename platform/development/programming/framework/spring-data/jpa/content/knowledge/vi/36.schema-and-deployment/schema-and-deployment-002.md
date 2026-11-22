# Ý nghĩa các chế độ ddl-auto trong từng môi trường

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Schema và triển khai

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của spring.jpa.hibernate.ddl-auto trong ứng dụng Spring Boot dùng Hibernate.
- Phân biệt none, validate, update, create và create-drop.
- Chọn cấu hình phù hợp cho local development, test, staging và production.
- Hiểu rủi ro mất dữ liệu khi Hibernate tự tạo hoặc thay đổi schema.
- Phân biệt schema generation của Hibernate với migration bằng Flyway hoặc Liquibase.
- Thiết kế quy trình triển khai schema có thể kiểm soát, lặp lại và an toàn khi nâng cấp ứng dụng.
- Kiểm tra mapping JPA, schema thực tế và migration trước khi phát hành.

## 2. ddl-auto là gì?

Trong ứng dụng Spring Boot dùng Spring Data JPA với Hibernate, thuộc tính:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

điều khiển hành vi Hibernate đối với schema database khi khởi tạo SessionFactory hoặc EntityManagerFactory. Tên ddl-auto là cách Spring Boot truyền cấu hình schema action của Hibernate.

Schema là cấu trúc lưu trữ trong database, gồm bảng, cột, kiểu dữ liệu, khóa chính, khóa ngoại, unique constraint, index và các đối tượng liên quan. Mapping JPA mô tả cách entity và thuộc tính Java tương ứng với cấu trúc đó.

Ví dụ:

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;
}
~~~

Mapping cho biết Hibernate cần một bảng customer với khóa chính id và cột name không null có độ dài tối đa 120 theo metadata JPA. Tuy nhiên, mapping này không tự bảo đảm database đang chạy đã có đúng bảng và constraint đó. Điều này phụ thuộc schema action, migration và cấu trúc database thực tế.

ddl-auto quyết định Hibernate có kiểm tra, tạo hoặc cố gắng cập nhật schema khi ứng dụng khởi động. Nó không phải công cụ quản lý lịch sử thay đổi schema và không thay thế quy trình migration có version.

## 3. Năm chế độ thường gặp

| Giá trị | Hành vi chính | Mục đích thường gặp |
|---|---|---|
| none | Không thực hiện schema action | Ứng dụng dùng schema được quản lý bên ngoài |
| validate | Kiểm tra mapping có tương thích với schema hiện tại hay không; không tạo/sửa bảng | Kiểm tra khi khởi động, thường dùng staging/production |
| update | Hibernate cố gắng điều chỉnh schema để phù hợp mapping | Tiện cho thử nghiệm local, không phải migration an toàn |
| create | Tạo schema theo mapping; có thể xóa cấu trúc hiện có trước khi tạo lại | Database dùng riêng, có thể xóa và tạo mới |
| create-drop | Tạo schema khi khởi động và xóa schema khi SessionFactory đóng | Test hoặc môi trường dùng tạm |

Chi tiết hành vi có thể phụ thuộc phiên bản Hibernate và dialect. Hãy kiểm tra phiên bản thư viện đang dùng khi cần dựa vào một hành vi cụ thể.

## 4. none: Hibernate không quản lý schema

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

Với none, Hibernate không tự tạo hoặc sửa bảng và cũng không kiểm tra schema khớp mapping. Ứng dụng kỳ vọng database đã được chuẩn bị bởi một quy trình khác.

Phù hợp khi:

- Flyway hoặc Liquibase quản lý toàn bộ schema.
- DBA hoặc pipeline triển khai chịu trách nhiệm áp dụng DDL.
- Ứng dụng không có quyền thay đổi cấu trúc database.
- Quy trình phát hành cần tách quyền DDL khỏi tài khoản chạy ứng dụng.

Ưu điểm là hành vi khởi động không âm thầm thay đổi cấu trúc database. Nhược điểm là nếu migration chưa được áp dụng, ứng dụng có thể vẫn khởi động nhưng chỉ phát hiện lỗi khi truy vấn hoặc ghi dữ liệu.

Nếu dùng none, cần có bước xác minh schema trong pipeline hoặc kiểm thử tích hợp. Không nên xem việc ứng dụng khởi động thành công là bằng chứng schema đã đúng.

## 5. validate: chỉ kiểm tra tương thích

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

validate yêu cầu Hibernate kiểm tra schema hiện tại có tương thích với mapping mà Hibernate biết hay không. Nếu phát hiện một số khác biệt không chấp nhận được, quá trình khởi tạo có thể thất bại để ứng dụng không chạy với schema sai.

Phù hợp khi:

- Database đã được tạo bằng migration.
- Muốn ứng dụng phát hiện sớm bảng hoặc cột cần thiết bị thiếu.
- Muốn staging và production không tự sửa schema khi khởi động.
- Pipeline cần bảo đảm migration được áp dụng trước khi phiên bản ứng dụng mới chạy.

Ví dụ, entity có thuộc tính được ánh xạ vào cột customer.name nhưng bảng customer chưa có cột đó. validate có thể làm ứng dụng khởi động thất bại, giúp phát hiện migration còn thiếu.

**Giới hạn của validate:** đây không phải một bộ kiểm thử toàn diện cho database. Không nên giả định nó xác minh mọi quy tắc nghiệp vụ, dữ liệu hiện có, nội dung index, hiệu năng query, mọi loại constraint hoặc mọi chi tiết DDL của từng hệ quản trị. Hãy kiểm tra schema và migration bằng công cụ phù hợp ngoài Hibernate.

validate cũng không sửa schema. Nếu thiếu cột, phải tạo migration hoặc sửa schema theo quy trình đã được quản lý, sau đó chạy lại ứng dụng.

## 6. update: tiện lợi nhưng không phải migration

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

update yêu cầu Hibernate cố gắng thay đổi schema hiện tại để phù hợp mapping. Ví dụ, khi thêm một thuộc tính mới có thể tạo thêm cột tương ứng. Hành vi chính xác phụ thuộc Hibernate, dialect và loại thay đổi.

update có thể hữu ích trong thử nghiệm local với database có thể tái tạo. Tuy nhiên, không nên dựa vào nó như công cụ migration cho môi trường dùng chung hoặc production vì:

- Không tạo lịch sử migration có version để biết thay đổi nào đã được áp dụng.
- Không thể hiện rõ ý định chuyển đổi dữ liệu từ cấu trúc cũ sang cấu trúc mới.
- Không bảo đảm tự xử lý an toàn mọi trường hợp đổi tên, tách/gộp cột, thay kiểu dữ liệu hoặc thay đổi constraint.
- Không tự biết cách backfill dữ liệu hiện có theo quy tắc nghiệp vụ.
- Có thể tạo ra khác biệt giữa các database nếu từng môi trường đã có schema không giống nhau.
- Khó review, kiểm thử, rollback và phối hợp với triển khai nhiều phiên bản ứng dụng.

Ví dụ đổi tên thuộc tính Java từ fullName sang displayName không nhất thiết khiến Hibernate hiểu rằng cần đổi tên cột. Tùy mapping và phiên bản, schema update có thể tạo cột mới hoặc để lại cột cũ. Dữ liệu cũ có thể không được chuyển sang cột mới như mong muốn.

Một migration tường minh có thể đổi tên cột, backfill dữ liệu và kiểm tra kết quả. Đó là lý do update không thay thế Flyway hoặc Liquibase.

## 7. create: tạo lại schema

~~~properties
spring.jpa.hibernate.ddl-auto=create
~~~

create yêu cầu Hibernate tạo schema từ mapping. Trong chiến lược schema generation của Hibernate, thao tác tạo có thể bao gồm xóa các đối tượng schema hiện có trước khi tạo lại. Vì vậy, dữ liệu cũ có thể bị mất.

Chỉ dùng khi database là môi trường dùng riêng và có thể tái tạo hoàn toàn, ví dụ một database local tạm thời. Không bật create trên database có dữ liệu cần giữ.

create không có nghĩa là migration từ phiên bản schema cũ sang schema mới. Nó dựng lại cấu trúc theo mapping hiện tại, không bảo toàn dữ liệu nghiệp vụ theo một kế hoạch chuyển đổi.

## 8. create-drop: tạo khi khởi động, xóa khi đóng

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

create-drop tạo schema khi khởi tạo và xóa schema khi SessionFactory đóng bình thường. Đây là lựa chọn thường dùng cho test có database riêng, dữ liệu không cần giữ sau khi kiểm thử.

Ví dụ cấu hình test:

~~~properties
# application-test.properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Khi dùng create-drop:

- Database phải được dành riêng cho test.
- Không kết nối nhầm đến database dùng chung hoặc production.
- Không phụ thuộc dữ liệu đã được lưu từ lần chạy trước.
- Test nên tự tạo fixture và kiểm tra kết quả.
- Cần hiểu vòng đời context của test; context được tái sử dụng có thể khiến thời điểm tạo/xóa schema khác với từng test method riêng lẻ.

create-drop đặc biệt hữu ích với database Testcontainers được tạo cho một test suite hoặc một nhóm test. Khi container và context kết thúc, dữ liệu kiểm thử được loại bỏ cùng môi trường tạm.

## 9. Chọn cấu hình theo môi trường

Không có một giá trị duy nhất phù hợp cho mọi môi trường. Hãy chọn theo mục đích và cách quản lý schema.

| Môi trường | Lựa chọn thường dùng | Lý do |
|---|---|---|
| Local dùng database tạm | create hoặc create-drop | Có thể dựng lại schema nhanh khi thử nghiệm |
| Local cần giữ dữ liệu | validate hoặc migration; update chỉ cho thử nghiệm có kiểm soát | Tránh vô tình mất dữ liệu và kiểm tra schema |
| Unit/integration test với database riêng | create-drop hoặc migration từ đầu | Mỗi lượt test có trạng thái xác định |
| CI | Migration + validate hoặc none | Kiểm tra migration và mapping trên database sạch |
| Staging | validate hoặc none sau khi pipeline chạy migration | Gần production, phát hiện sai lệch trước phát hành |
| Production | validate hoặc none sau migration | Ứng dụng không tự tạo/sửa schema trong lúc khởi động |

### 9.1. Local development

Nếu database local chỉ chứa dữ liệu thử nghiệm có thể xóa, create-drop giúp dựng schema sạch mỗi lần tạo mới persistence context. Nếu muốn giữ dữ liệu qua lần khởi động, có thể dùng migration và validate.

update đôi khi tiện khi đang học hoặc thử mapping mới, nhưng không nên để nó trở thành quy trình duy nhất của dự án. Hãy thử chạy migration trên local để thay đổi schema được lưu thành lịch sử có thể review.

### 9.2. Test

Với test tích hợp, có thể chọn create-drop nếu Hibernate mapping là nguồn dựng schema của test. Nếu dự án dùng Flyway/Liquibase trong thực tế, nên có test chạy migration thật trên database tương thích để phát hiện lỗi SQL hoặc thứ tự migration.

Không nên chỉ kiểm thử bằng H2 nếu production dùng PostgreSQL hoặc MySQL mà dự án phụ thuộc vào hành vi riêng của database. Testcontainers giúp chạy database cùng loại trong môi trường CI hoặc local.

### 9.3. Staging

Staging nên phản ánh quy trình production: migration được áp dụng trước, sau đó ứng dụng kiểm tra schema. validate giúp phát hiện mapping và schema lệch nhau trong quá trình khởi động. Nếu pipeline có bước kiểm tra schema độc lập và ứng dụng không cần tự validate, none cũng có thể phù hợp.

### 9.4. Production

Trong production, tránh create, create-drop và update. Các chế độ này có thể thay đổi cấu trúc ngoài kế hoạch, làm mất dữ liệu hoặc tạo schema khác nhau giữa các instance.

Thông thường, dùng Flyway/Liquibase để áp dụng migration, rồi chọn validate nếu muốn Hibernate kiểm tra tương thích lúc khởi động. Có thể dùng none nếu quy trình triển khai đã kiểm tra schema ở bước riêng và không muốn Hibernate thực hiện kiểm tra đó.

Tài khoản database mà ứng dụng dùng trong production thường chỉ nên có quyền cần thiết cho hoạt động runtime. Tách tài khoản migration có quyền DDL khỏi tài khoản ứng dụng giúp giảm nguy cơ một lần khởi động ứng dụng vô tình thay đổi schema.

## 10. Giá trị mặc định trong Spring Boot

Không nên dựa vào việc bỏ trống ddl-auto mà mặc định nó luôn là none hoặc luôn là update. Spring Boot có thể chọn giá trị mặc định dựa trên loại database và việc có schema manager hay không.

Trong cấu hình phổ biến, nếu dùng embedded database và không có schema manager, Boot có thể chọn create-drop. Với database không nhúng hoặc khi có công cụ quản lý schema, mặc định thường là none.

Hành vi còn phụ thuộc phiên bản Spring Boot, Hibernate, datasource và cấu hình SQL initialization. Để tránh bất ngờ giữa local, CI và production, hãy khai báo rõ giá trị trong profile tương ứng:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Kiểm tra cấu hình thực tế đã được áp dụng khi khởi động, đặc biệt khi có nhiều file application.properties, profile, biến môi trường hoặc cấu hình deployment ghi đè.

## 11. Hibernate ddl-auto khác gì Flyway và Liquibase?

Hibernate schema generation chủ yếu dựa trên mapping entity hiện tại để tạo, kiểm tra hoặc cố gắng cập nhật schema.

Flyway và Liquibase quản lý các thay đổi schema theo migration có version hoặc changelog. Mỗi thay đổi được mô tả rõ, lưu trong repository và áp dụng theo thứ tự.

| Tiêu chí | Hibernate ddl-auto | Flyway/Liquibase |
|---|---|---|
| Nguồn mô tả | Mapping entity | Migration SQL hoặc changelog |
| Lịch sử thay đổi | Không phải hệ thống version migration | Có lịch sử/version/checksum |
| Backfill dữ liệu | Không diễn đạt đầy đủ quy trình nghiệp vụ | Có thể viết rõ SQL hoặc change set |
| Đổi tên/tách/gộp cột | Không nên dựa vào update để suy luận | Migration mô tả tường minh |
| Review và triển khai | Hành vi phụ thuộc mapping/provider | Thay đổi được review trước |
| Rollback | Không có kế hoạch rollback nghiệp vụ đáng tin cậy | Có thể thiết kế migration bù hoặc rollback tùy công cụ |

Một quy trình phổ biến là:

1. Developer sửa entity và viết migration tương ứng.
2. Test chạy migration trên database sạch và database từ phiên bản trước.
3. Pipeline staging áp dụng migration.
4. Ứng dụng khởi động với ddl-auto=validate hoặc none.
5. Production áp dụng migration theo thứ tự triển khai đã được kiểm thử.
6. Ứng dụng mới chạy trên schema tương thích.

Không nên để cả Hibernate update và Flyway/Liquibase cùng tự thay đổi schema trong production. Hai cơ chế có thể tạo ra kết quả khó dự đoán và làm mất tính rõ ràng của migration history.

## 12. Ví dụ migration có version

Giả sử cần tạo bảng customer:

~~~sql
-- V1__create_customer.sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Sau đó cần thêm trạng thái:

~~~sql
-- V2__add_customer_status.sql
ALTER TABLE customer
ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
~~~

Đây là cú pháp ví dụ cho PostgreSQL. Với MySQL hoặc database khác, kiểu identity và một số cú pháp có thể khác.

Migration được lưu trong thư mục Flyway mặc định, thường là db/migration trong classpath. Tên file theo quy tắc versioned migration, ví dụ V1__create_customer.sql. Flyway ghi nhận migration đã chạy trong bảng lịch sử schema.

Khi thay đổi lớn, hãy cân nhắc chiến lược expand-contract:

1. Thêm cột hoặc bảng mới theo cách tương thích với phiên bản ứng dụng cũ.
2. Triển khai ứng dụng có thể đọc/ghi theo cấu trúc chuyển tiếp.
3. Backfill dữ liệu cũ theo batch có thể kiểm soát.
4. Xác minh dữ liệu đã được chuyển đầy đủ.
5. Chuyển ứng dụng sang cấu trúc mới.
6. Chỉ xóa cột cũ ở một lần phát hành sau, khi không còn instance nào cần nó.

Cách này hữu ích khi triển khai rolling deployment với nhiều instance chạy hai phiên bản ứng dụng trong một khoảng thời gian.

## 13. Phối hợp schema migration và JPA mapping

Khi sửa entity, hãy kiểm tra các phần sau:

- @Table và @Column có khớp tên bảng/cột trong migration không?
- Kiểu Java và kiểu SQL có tương thích không?
- nullable, length, precision và scale có được phản ánh trong schema không?
- @Id, @GeneratedValue và chiến lược identity/sequence có khớp database không?
- @JoinColumn có trỏ đến đúng khóa ngoại không?
- Enum được lưu dạng STRING hay ORDINAL và migration có đúng kiểu cột không?
- Converter, embedded object và inheritance có tạo cấu trúc phù hợp không?
- Index và constraint cần thiết đã được tạo trong migration chưa?

Ví dụ enum:

~~~java
@Enumerated(EnumType.STRING)
@Column(nullable = false, length = 20)
private OrderStatus status;
~~~

Với EnumType.STRING, database lưu tên enum. Đổi tên hằng enum có thể ảnh hưởng dữ liệu hiện có. Với EnumType.ORDINAL, database lưu vị trí số; chèn hoặc đổi thứ tự hằng có thể làm ý nghĩa dữ liệu cũ thay đổi. Cần cân nhắc migration dữ liệu khi thay đổi enum.

Các annotation như @Column(nullable = false) mô tả mapping và có thể ảnh hưởng schema generation. Chúng không tự thay đổi database khi ddl-auto=none hoặc validate. Hãy tạo migration để thêm NOT NULL constraint và xử lý dữ liệu null cũ trước khi áp dụng.

## 14. Quy trình kiểm tra trước khi triển khai

Một checklist có thể áp dụng cho mỗi lần phát hành:

1. Xác định phiên bản schema hiện tại và phiên bản ứng dụng đang chạy.
2. Review migration mới, SQL và tác động lên dữ liệu.
3. Chạy migration trên database sạch.
4. Chạy migration nâng cấp từ schema của phiên bản trước.
5. Kiểm tra dữ liệu sau backfill và các constraint.
6. Chạy integration test với đúng loại database hoặc Testcontainers.
7. Khởi động ứng dụng với ddl-auto=validate để phát hiện mapping không tương thích.
8. Kiểm tra thứ tự pipeline: database migration hoàn tất trước khi instance mới nhận traffic.
9. Xác định kế hoạch xử lý nếu migration hoặc deployment thất bại.
10. Theo dõi log khởi động và lỗi SQL sau phát hành.

Với bảng lớn, thêm cột, tạo index hoặc thay đổi constraint có thể khóa bảng hoặc tiêu tốn nhiều thời gian. Hãy xem xét cách tạo index online/concurrently nếu database hỗ trợ, thời gian lock, lượng dữ liệu và chiến lược backfill. Không giả định mọi câu ALTER TABLE đều nhanh và không gây gián đoạn.

## 15. Những sai lầm thường gặp

### 15.1. Dùng update trong production vì tiện

update không cung cấp migration history và không thể hiện rõ cách chuyển dữ liệu. Dùng migration có version để review và triển khai có kiểm soát.

### 15.2. Dùng create hoặc create-drop với database có dữ liệu cần giữ

Các chế độ này có thể xóa schema và dữ liệu. Chỉ dùng với database tạm, riêng cho developer hoặc test.

### 15.3. Nghĩ validate sẽ sửa schema

validate chỉ kiểm tra một số khía cạnh tương thích. Khi có sai lệch, cần migration hoặc sửa schema bên ngoài.

### 15.4. Cho rằng validate kiểm tra mọi constraint và dữ liệu

Hibernate validation không thay thế kiểm tra constraint, index, dữ liệu và execution plan bằng công cụ database. Hãy kiểm thử các yêu cầu này riêng.

### 15.5. Để mỗi instance tự thay đổi schema khi khởi động

Nhiều instance cùng khởi động với schema action có thể gây cạnh tranh DDL hoặc trạng thái không nhất quán. Để một bước migration có kiểm soát quản lý thay đổi schema trước khi ứng dụng chạy.

### 15.6. Quên profile đang được kích hoạt

Local có thể dùng create-drop trong khi production vô tình nhận cùng cấu hình do profile hoặc biến môi trường sai. Hãy kiểm tra cấu hình hiệu lực ở từng môi trường và giữ thông tin nhạy cảm ngoài file cấu hình được commit.

### 15.7. Thay đổi mapping nhưng quên migration

Ứng dụng có thể chạy ở local do update tự thêm cột nhưng thất bại ở staging/production dùng validate hoặc none. Mọi thay đổi schema cần migration tương ứng và test nâng cấp.

## 16. Checklist chọn ddl-auto

- [ ] Database có phải môi trường tạm, có thể xóa dữ liệu không?
- [ ] Schema do Hibernate hay migration tool quản lý?
- [ ] Local, test, staging và production có cấu hình tách biệt không?
- [ ] Test có chạy trên loại database tương thích production không?
- [ ] Production tránh create, create-drop và update không?
- [ ] Migration có version, được review và chạy theo thứ tự không?
- [ ] Có test migration từ schema cũ và từ database sạch không?
- [ ] validate có được dùng để kiểm tra mapping khi phù hợp không?
- [ ] Tài khoản runtime có quyền database tối thiểu không?
- [ ] Pipeline có áp dụng migration trước khi triển khai instance mới không?
- [ ] Có kế hoạch backfill, rollback/bù trừ và xử lý triển khai dở dang không?

## 17. Kết luận

ddl-auto quyết định Hibernate xử lý schema khi ứng dụng khởi động. none không can thiệp, validate kiểm tra tương thích, update cố gắng điều chỉnh schema, create tạo lại schema và create-drop còn xóa schema khi SessionFactory đóng. Local và test có thể dùng chế độ tạo schema trên database tạm; staging và production nên để migration có version quản lý thay đổi, sau đó dùng validate hoặc none theo pipeline. Hiểu rõ rủi ro từng chế độ, kiểm thử migration và tách quyền DDL khỏi tài khoản runtime giúp triển khai Spring Data JPA an toàn và có thể lặp lại.
