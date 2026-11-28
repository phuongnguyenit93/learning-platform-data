# Đánh giá độ bền dữ liệu, quyền truy cập và sao lưu từng backend

Spring Cloud Config Server có thể đọc cấu hình từ nhiều loại nguồn lưu trữ. Git là lựa chọn phổ biến khi nhóm cần lịch sử commit, review và quản lý phiên bản. Tuy nhiên, một số hệ thống phù hợp hơn với filesystem, cơ sở dữ liệu quan hệ hoặc nền tảng quản lý bí mật như Vault và CredHub. Config Server cũng có thể kết hợp nhiều repository để lấy các nhóm cấu hình khác nhau.

Chọn backend không chỉ là chọn nơi đặt tệp YAML. Cần đánh giá dữ liệu có được lưu bền vững không, ai được đọc hoặc thay đổi, cách sao lưu và phục hồi, khả năng kiểm toán, hành vi khi backend mất kết nối và cách kiểm tra cấu hình sau khi khôi phục. Bài học này so sánh các backend thường gặp của Spring Cloud Config theo những tiêu chí đó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết các backend Spring Cloud Config thường dùng: Git, SVN, Native filesystem, JDBC, Vault và CredHub.
- Phân biệt độ bền dữ liệu, tính sẵn sàng, lịch sử phiên bản và khả năng phục hồi sau sự cố.
- Đánh giá quyền đọc/ghi, xác thực, phân quyền và kiểm toán cho từng backend.
- Xây dựng chiến lược backup/restore phù hợp với đặc điểm lưu trữ của backend.
- Hiểu rủi ro khi kết hợp nhiều EnvironmentRepository và khi một backend bị lỗi.
- Chọn backend dựa trên loại dữ liệu, yêu cầu vận hành và năng lực của nền tảng.

## 2. Bốn câu hỏi trước khi chọn backend

### Dữ liệu cần tồn tại lâu đến mức nào?

Hãy xác định cấu hình có phải dữ liệu quan trọng cần khôi phục chính xác sau khi mất máy, Pod hoặc vùng lưu trữ hay không. Một bản clone Git trên đĩa container có thể xóa và tạo lại từ remote; một database hoặc Vault storage cần quy trình backup riêng. Đừng nhầm bản cache cục bộ với nguồn dữ liệu chuẩn.

### Ai được đọc và ai được thay đổi?

Config Server thường cần quyền đọc cấu hình để phân phối cho client. Quyền ghi nên được giới hạn cho nhóm hoặc quy trình quản lý cấu hình. Với dữ liệu bí mật, cần phân quyền theo danh tính ứng dụng và từng secret/path, thay vì cấp quyền đọc toàn bộ kho.

### Có cần lịch sử và khả năng tái lập không?

Git/SVN có lịch sử commit và nhánh/tag. JDBC có thể lưu label hoặc mã phiên bản, nhưng quy trình tạo và bảo vệ phiên bản phải được thiết kế. Vault KV v2 và CredHub có cơ chế phiên bản cho dữ liệu tương ứng, tùy cấu hình và nền tảng. Filesystem đơn thuần không tự cung cấp lịch sử review.

### Khôi phục cần đạt RPO và RTO nào?

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ hoặc khả năng lấy cấu hình.

Ví dụ, nếu cấu hình đã duyệt không được mất sau sự cố, cần có bản sao lưu và cách xác minh commit/phiên bản. Nếu Config Server cần hoạt động trở lại trong vài phút, cần kiểm tra thời gian tạo lại clone, kết nối database hoặc mở khóa truy cập Vault trong môi trường khôi phục.

## 3. Tổng quan các backend

| Backend | Nơi lưu dữ liệu | Điểm mạnh | Điểm cần tự quản lý |
| --- | --- | --- | --- |
| Git | Repository Git từ xa và bản clone cục bộ | Lịch sử commit, branch/tag, review và rollback rõ | Bảo vệ remote, credential, backup repository và đồng bộ clone |
| SVN | Repository Subversion | Lịch sử phiên bản tập trung, quyền theo repository/path | Backup SVN, xác thực, quyền và vận hành repository |
| Native | Filesystem mà Config Server đọc được | Đơn giản, phù hợp cấu hình tĩnh hoặc được mount từ hệ thống khác | Độ bền volume, quyền file, lịch sử thay đổi và backup |
| JDBC | Bảng trong cơ sở dữ liệu quan hệ | Giao dịch, kiểm soát truy cập DB, backup và phục hồi theo nền tảng DB | Schema, quy trình versioning, audit và quản trị thay đổi |
| Vault | Secret engine của HashiCorp Vault | Phù hợp dữ liệu nhạy cảm, policy theo path và audit | Vận hành Vault, seal/unseal, storage, snapshot và replication |
| CredHub | Dịch vụ CredHub trong nền tảng Cloud Foundry | Quản lý credential tập trung, ACL và tích hợp nền tảng | Vận hành/backup dịch vụ CredHub và quyền OAuth/UAA |
| Composite | Nhiều repository được kết hợp | Tách nhóm dữ liệu theo backend và tái sử dụng nguồn | Thứ tự ưu tiên, tính sẵn sàng và backup từng nguồn |

Composite là cách phối hợp các repository, không phải một hệ thống lưu trữ độc lập. Git, SVN, Native, JDBC, Vault và CredHub có đặc điểm lưu trữ và backup riêng.

## 4. Git: lựa chọn mạnh cho cấu hình có phiên bản

### Độ bền và lịch sử

Git lưu nội dung cấu hình thành các commit trong repository. Branch và tag giúp chọn phiên bản; lịch sử commit giúp xác định thay đổi, người thực hiện và thời điểm. Khi Config Server dùng Git backend, nó tạo bản clone cục bộ để đọc dữ liệu, còn remote repository thường là nguồn chuẩn cần bảo vệ.

Nếu local clone bị mất, Config Server có thể tạo lại từ remote. Vì thế, backup quan trọng nhất là bảo vệ remote repository và metadata cần thiết để tái lập phiên bản, bao gồm commit, branch, tag và các ref được sử dụng. Không dựa vào thư mục clone trong container làm bản backup duy nhất.

### Quyền truy cập

- Config Server nên dùng credential chỉ có quyền đọc repository cần thiết.
- Chỉ nhóm được giao trách nhiệm mới có quyền push hoặc merge thay đổi cấu hình.
- Bật branch protection, review bắt buộc và kiểm tra secret scanning nếu nền tảng Git hỗ trợ.
- Dùng TLS hoặc SSH với host key được xác minh; không nhúng token hoặc private key vào URL hay repository.
- Giới hạn quyền đọc repository vì cấu hình có thể tiết lộ địa chỉ nội bộ, tên dịch vụ hoặc kiến trúc hệ thống.

### Backup và phục hồi

- Dùng cơ chế backup/mirror của nền tảng Git hoặc bản sao repository được quản lý riêng.
- Bảo đảm bản sao giữ đầy đủ commit và refs cần thiết; kiểm tra cả tag và branch dùng để phát hành.
- Với Git server tự quản lý, backup dữ liệu repository và metadata theo hướng dẫn của nền tảng Git.
- Thử clone một bản sao backup vào môi trường khôi phục và gọi endpoint Config Server với application, profile, label đã biết.
- Ghi nhận quy trình thu hồi/đổi credential nếu token hoặc SSH key bị lộ.

Git phù hợp với cấu hình kỹ thuật thông thường cần review và version control. Không nên lưu mật khẩu, token hoặc private key dạng văn bản thuần trong Git chỉ vì repository đã có quyền truy cập hạn chế.

## 5. SVN: quản lý phiên bản tập trung

Spring Cloud Config có thể sử dụng Subversion làm backend. SVN cung cấp lịch sử revision và cơ chế phân quyền repository/path. Đây có thể là lựa chọn hợp lý khi tổ chức đã chuẩn hóa SVN hoặc có quy trình kiểm soát thay đổi dựa trên nền tảng này.

### Độ bền và lịch sử

Dữ liệu chuẩn nằm trong repository SVN. Config Server truy cập repository để đọc revision phù hợp; bản làm việc cục bộ có thể được tạo hoặc cập nhật theo backend. Lịch sử revision hỗ trợ điều tra và quay lại trạng thái trước đó.

### Quyền truy cập

- Tài khoản Config Server nên chỉ có quyền đọc path chứa cấu hình cần thiết.
- Quyền commit cần giới hạn theo nhóm chịu trách nhiệm.
- Bảo vệ thông tin xác thực, dùng TLS và kiểm soát quyền truy cập theo repository/path.
- Kiểm tra log truy cập và chính sách lưu trữ credential theo nền tảng SVN.

### Backup và phục hồi

Backup repository SVN theo công cụ và quy trình của hệ thống SVN đang dùng. Kiểm tra bản backup có thể phục hồi thành repository hoạt động, giữ lịch sử revision và cấp quyền đúng. Sau restore, kiểm thử Config Server đọc được revision hoặc label dự kiến.

SVN có thể cung cấp version control tương tự Git ở mức quản lý lịch sử, nhưng quy trình branch/tag, review và tích hợp CI/CD phụ thuộc cách tổ chức SVN của nhóm. Đừng giả định quy trình Git có thể áp dụng nguyên trạng cho SVN.

## 6. Native filesystem: đơn giản nhưng cần quản trị filesystem

Native backend đọc tệp cấu hình từ filesystem mà Config Server có thể truy cập. Đây thường là lựa chọn thuận tiện cho môi trường thử nghiệm, cấu hình nhỏ hoặc hệ thống đã có quy trình phân phối file an toàn.

Ví dụ cấu hình server:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-repo
```

Ở đây, `native` là Spring profile kích hoạt backend trên Config Server. Nó khác với profile mà Config Client yêu cầu, chẳng hạn `dev` hoặc `prod`. Các tệp được đọc từ `/etc/config-repo` theo quy tắc tìm kiếm của Native EnvironmentRepository.

### Độ bền

Độ bền phụ thuộc filesystem đứng sau đường dẫn đó:

- Nếu thư mục nằm trong writable layer của container, dữ liệu có thể mất khi container được tạo lại.
- Nếu thư mục được mount từ volume, độ bền phụ thuộc loại volume, chính sách lưu trữ và vòng đời volume.
- Nếu file được đồng bộ từ Git hoặc hệ thống quản lý cấu hình khác, nguồn chuẩn và lịch sử nằm ở hệ thống đồng bộ đó.

Native backend không tự tạo lịch sử commit hoặc review. Nếu cần tái lập phiên bản, hãy quản lý thư mục nguồn bằng Git hoặc một hệ thống phát hành file có lịch sử rõ ràng.

### Quyền truy cập

- User chạy Config Server cần quyền đọc file và traverse thư mục cha.
- Nếu Config Server chỉ đọc file, ưu tiên mount read-only để giảm nguy cơ sửa cấu hình ngoài quy trình.
- Nhóm triển khai hoặc tiến trình đồng bộ file cần quyền ghi theo chính sách riêng.
- Kiểm soát quyền đọc trên host và volume; file cấu hình có thể chứa thông tin nội bộ hoặc bí mật.

### Backup và phục hồi

Backup thư mục nguồn, metadata và cấu trúc thư mục. Nếu dùng volume, xác định snapshot/backup theo nền tảng lưu trữ. Nếu dùng file được sinh từ pipeline, lưu lại artifact và phiên bản nguồn đã tạo artifact. Khi phục hồi, kiểm tra owner, mode, nội dung YAML, đường dẫn mount và endpoint Config Server.

Native backend phù hợp khi cần đọc file đơn giản và nhóm đã có cơ chế phân phối, backup, versioning bên ngoài. Nó không tự thay thế Git hoặc hệ thống quản lý bí mật.

## 7. JDBC: lưu cấu hình trong cơ sở dữ liệu quan hệ

JDBC backend đọc các property từ bảng trong database. Đây là lựa chọn khi tổ chức muốn quản lý cấu hình trong hạ tầng cơ sở dữ liệu hiện có hoặc cần thao tác dữ liệu theo quy trình nội bộ.

Ví dụ cấu hình server dùng JDBC backend:

```yaml
spring:
  profiles:
    active: jdbc
  datasource:
    url: jdbc:postgresql://config-db.internal:5432/configuration
    username: ${CONFIG_DB_USERNAME}
    password: ${CONFIG_DB_PASSWORD}
  cloud:
    config:
      server:
        jdbc:
          sql: SELECT KEY, VALUE FROM PROPERTIES WHERE APPLICATION=? AND PROFILE=? AND LABEL=?
```

Ví dụ minh họa cách cấu hình kết nối và câu truy vấn. Cần có dependency JDBC và driver database phù hợp, schema đúng với query và các tham số mà Config Server truyền vào. Hãy kiểm tra schema mặc định/tùy chỉnh theo phiên bản Spring Cloud Config đang dùng trước khi tạo bảng.

### Độ bền

Database cung cấp các cơ chế như transaction, replication, backup, point-in-time recovery và kiểm soát tính nhất quán tùy sản phẩm/cấu hình. Tuy nhiên, các tính năng đó chỉ có hiệu lực khi được cấu hình và vận hành đúng.

Nếu cột `LABEL` được dùng để phân biệt phiên bản, nhóm cần quy định cách tạo label, cách khóa phiên bản đã phát hành và cách ngăn chỉnh sửa ngoài quy trình. Bản thân việc có cột label không tự tạo lịch sử commit hoặc review như Git.

### Quyền truy cập

- Dùng tài khoản database riêng cho Config Server, ưu tiên quyền `SELECT` trên các bảng/view cần đọc.
- Dùng tài khoản hoặc vai trò khác cho pipeline/ứng dụng quản trị cấu hình cần ghi.
- Bật TLS khi kết nối database qua mạng và dùng secret manager để cấp thông tin xác thực.
- Giới hạn quyền truy cập schema, audit thay đổi và bảo vệ bản backup.
- Tránh dùng chung tài khoản quản trị database với Config Server.

### Backup và phục hồi

Backup database theo chính sách của nền tảng DB: full backup, incremental/log backup hoặc point-in-time recovery nếu được hỗ trợ. Backup cần bao gồm schema, dữ liệu, migration và metadata cần để đọc lại cấu hình. Thử restore vào môi trường riêng, xác minh số lượng bản ghi và gọi Config Server để kiểm tra application/profile/label quan trọng.

JDBC phù hợp khi cần tích hợp với quy trình dữ liệu quan hệ và nhóm có năng lực vận hành DB. Cần xây dựng thêm quy trình review, versioning và kiểm toán để việc sửa cấu hình có thể truy vết.

## 8. Vault: quản lý bí mật và cấu hình nhạy cảm

HashiCorp Vault cung cấp backend để Config Server đọc dữ liệu từ secret engine. Vault đặc biệt phù hợp với mật khẩu, token, khóa và các giá trị cần phân quyền theo path hoặc danh tính ứng dụng. Tùy thiết kế, Vault cũng có thể lưu một số thuộc tính cấu hình nhạy cảm.

Ví dụ cấu hình kết nối cơ bản:

```yaml
spring:
  profiles:
    active: vault
  cloud:
    config:
      server:
        vault:
          host: vault.internal
          port: 8200
          scheme: https
          backend: secret
          default-key: application
```

Ví dụ chưa bao gồm phương thức xác thực. Trong môi trường thực tế, nên dùng phương thức xác thực phù hợp với nền tảng như Kubernetes auth, AppRole hoặc cơ chế danh tính được tổ chức phê duyệt. Không lưu Vault token có quyền rộng trong Git hoặc image.

### Độ bền

Độ bền phụ thuộc storage backend của Vault và cấu hình vận hành. Nếu dùng Integrated Storage (Raft), cần thiết kế snapshot, replication, quorum và quy trình khôi phục theo hướng dẫn Vault. Nếu dùng storage backend khác, áp dụng quy trình backup/restore tương ứng.

Với KV v2, Vault hỗ trợ lưu phiên bản của secret và có thể cấu hình số phiên bản giữ lại. Tính năng versioning không thay thế backup toàn hệ thống: vẫn cần snapshot hoặc backup storage và thử khôi phục trong môi trường cô lập.

### Quyền truy cập

- Dùng policy giới hạn path và thao tác cần thiết; một ứng dụng chỉ đọc secret mà nó cần.
- Ưu tiên danh tính máy và token ngắn hạn hoặc có khả năng thu hồi.
- Bật TLS, audit device và theo dõi truy cập bất thường.
- Tách quyền đọc secret khỏi quyền ghi/xóa secret.
- Bảo vệ unseal/recovery key và quy trình vận hành Vault.

### Backup và phục hồi

Với Vault Raft, lập lịch snapshot và lưu bản snapshot ở nơi tách biệt, mã hóa, giới hạn quyền đọc. Kiểm tra định kỳ quy trình restore, unseal và xác nhận policy/secret cần thiết vẫn hoạt động. Nếu dùng KV v2, hiểu rõ thời hạn giữ phiên bản và thao tác xóa/khôi phục theo cấu hình của engine.

Vault phù hợp khi yêu cầu bảo mật và phân quyền bí mật là trọng tâm. Cần tính cả Vault vào kiến trúc phụ thuộc của Config Server: nếu Vault không sẵn sàng hoặc danh tính không xác thực được, việc lấy cấu hình có thể thất bại.

## 9. CredHub: quản lý credential trong Cloud Foundry

CredHub là dịch vụ quản lý credential được sử dụng trong hệ sinh thái Cloud Foundry. Spring Cloud Config có thể dùng CredHub backend để lấy dữ liệu credential theo tên và quyền được cấp.

Ví dụ khai báo endpoint CredHub:

```yaml
spring:
  profiles:
    active: credhub
  cloud:
    config:
      server:
        credhub:
          url: https://credhub.example.internal
```

Thông tin xác thực và OAuth/UAA cần được cấu hình theo cách triển khai CredHub và nền tảng Cloud Foundry. Endpoint URL không thay thế bước xác thực; Config Server phải có danh tính và scope phù hợp.

### Độ bền

CredHub thường được vận hành như một dịch vụ nền tảng. Độ bền, replication và backup phụ thuộc cách nhà cung cấp hoặc đội nền tảng triển khai backing store. Nhóm sử dụng cần biết ai chịu trách nhiệm backup, thời gian lưu giữ, RPO/RTO và cách yêu cầu restore.

CredHub quản lý credential theo tên và có thể lưu nhiều phiên bản theo tính năng của dịch vụ. Hãy xác minh chính sách version retention và khả năng phục hồi của phiên bản CredHub đang dùng; không giả định mọi triển khai đều có cùng chính sách.

### Quyền truy cập

- Dùng OAuth/UAA hoặc cơ chế xác thực được nền tảng hỗ trợ.
- Cấp quyền đọc đúng credential cho danh tính Config Server hoặc ứng dụng theo kiến trúc đã chọn.
- Tách quyền tạo/cập nhật credential khỏi quyền đọc.
- Kiểm soát scope, ACL và audit theo chính sách Cloud Foundry.
- Không sao chép credential vào Git hoặc tài liệu vận hành.

### Backup và phục hồi

Xác định rõ nhóm nền tảng hay nhà cung cấp dịch vụ chịu trách nhiệm backup CredHub. Yêu cầu bằng chứng backup, chính sách giữ bản sao, mã hóa, kiểm tra restore và quy trình phục hồi khi mất dịch vụ. Sau restore, kiểm tra Config Server có thể xác thực và đọc đúng credential cần thiết.

CredHub phù hợp khi hệ thống đã sử dụng Cloud Foundry và có dịch vụ CredHub được vận hành tốt. Với nền tảng khác, Vault hoặc secret manager do nền tảng cung cấp có thể phù hợp hơn.

## 10. Composite: kết hợp nhiều nguồn cấu hình

Composite Environment Repository cho phép Config Server đọc cấu hình từ nhiều backend. Ví dụ, cấu hình kỹ thuật thông thường có thể nằm trong Git, trong khi bí mật được lấy từ Vault. Mỗi backend chịu trách nhiệm cho nhóm dữ liệu phù hợp với nó.

Một cấu hình composite có thể được tạo bằng cách kích hoạt nhiều backend profile hoặc khai báo danh sách repository composite, tùy cách cấu hình và phiên bản Spring Cloud Config. Ví dụ minh họa ý tưởng:

```yaml
spring:
  profiles:
    active: git, vault
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
        vault:
          host: vault.internal
          port: 8200
          scheme: https
          backend: secret
```

Đây là khung cấu hình để minh họa nhiều backend cùng tham gia. Dependency, thuộc tính xác thực và quy tắc composite cần đối chiếu với tài liệu phiên bản đang dùng.

### Độ bền và tính sẵn sàng

Composite không sao chép dữ liệu của backend này sang backend khác và cũng không tạo một giao dịch backup thống nhất. Git vẫn cần backup Git; Vault vẫn cần snapshot/restore Vault. Nếu một backend không sẵn sàng, request tổng hợp có thể thất bại tùy cấu hình xử lý lỗi. Hãy xác định rõ backend nào là bắt buộc và backend nào được phép bỏ qua trong từng luồng.

### Quyền truy cập

Mỗi backend có credential và policy riêng. Config Server cần quyền đọc tối thiểu trên từng nguồn. Không nên dùng một credential có quyền quản trị rộng để truy cập tất cả backend. Kiểm toán cần liên kết request lấy cấu hình với từng nguồn dữ liệu liên quan.

### Thứ tự ưu tiên và trùng khóa

Nếu cùng một khóa xuất hiện ở nhiều repository, thứ tự repository và property source quyết định giá trị hiệu lực. Hãy tài liệu hóa backend nào là nguồn chuẩn cho từng nhóm khóa và tránh khai báo trùng khóa ngoài chủ đích. Không nên dựa vào thứ tự mặc định chưa được xác minh trong phiên bản đang chạy.

### Backup và phục hồi

Lập kế hoạch backup/restore riêng cho từng backend và kiểm tra cả kịch bản một backend được phục hồi trước backend còn lại. Sau restore, gọi API Config Server để xác nhận các property source hợp nhất đúng và không tạo ra trạng thái nửa cũ nửa mới.

Composite hữu ích khi có ranh giới dữ liệu rõ ràng, ví dụ Git quản lý cấu hình thường và Vault quản lý bí mật. Nó làm tăng số phụ thuộc, vì vậy cần giám sát từng backend và kiểm thử khi một nguồn mất kết nối.

## 11. So sánh độ bền, quyền và backup

Bảng sau là điểm khởi đầu để thiết kế, không phải cam kết mặc định của sản phẩm. Độ bền thực tế phụ thuộc cách triển khai, cấu hình và hợp đồng vận hành.

| Backend | Độ bền chủ yếu dựa vào | Quyền truy cập nên dùng | Backup/restore cần kiểm tra |
| --- | --- | --- | --- |
| Git | Git remote và dịch vụ lưu repository | Read-only cho Config Server; branch protection cho người ghi | Mirror/backup repository, refs, tag; thử clone và đọc label |
| SVN | Repository Subversion | Read-only cho Config Server; quyền commit theo path | Backup repository theo công cụ SVN; thử restore revision |
| Native | Volume/filesystem hoặc hệ thống phát hành file | Read-only mount cho Config Server nếu có thể | Snapshot/backup file tree và metadata; thử mount lại và đọc YAML |
| JDBC | Database storage, transaction và backup DB | DB role chỉ đọc cho Config Server; role ghi riêng | Full/incremental/log backup, schema và point-in-time restore |
| Vault | Storage backend, Raft snapshot/replication hoặc storage tương ứng | Policy theo path, danh tính máy, audit | Snapshot/backup mã hóa; thử restore, unseal và đọc secret |
| CredHub | Backing store và vận hành của dịch vụ CredHub | OAuth/UAA scope và ACL theo credential | Xác nhận trách nhiệm backup của nền tảng; thử restore credential và quyền |
| Composite | Từng backend thành phần | Credential riêng, quyền tối thiểu cho từng nguồn | Backup từng nguồn và kiểm tra kết quả hợp nhất sau restore |

## 12. Đừng nhầm replication với backup

Replication giúp dữ liệu hoặc dịch vụ tiếp tục hoạt động khi một node gặp sự cố. Backup giúp khôi phục trạng thái trước đó khi dữ liệu bị xóa, hỏng hoặc thay đổi sai. Một bản sao đồng bộ tức thời có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị mã hóa bởi sự cố bảo mật.

Với mọi backend, hãy xác định:

- Bản backup nằm ở đâu và có tách biệt khỏi hệ thống nguồn không.
- Ai có quyền xóa hoặc sửa bản backup.
- Dữ liệu được mã hóa khi truyền và khi lưu như thế nào.
- Lịch backup và thời gian giữ bản sao.
- Có backup metadata, schema, policy, ACL và cấu hình kết nối cần thiết không.
- Cách restore có được thử định kỳ không.
- Sau restore, làm thế nào xác minh Config Server trả đúng application/profile/label.

Một bản backup chưa từng được restore thử chỉ chứng minh rằng có file backup, chưa chứng minh hệ thống có thể phục hồi.

## 13. Kiểm soát quyền theo nguyên tắc tối thiểu

Config Server thường chỉ cần đọc dữ liệu để trả cấu hình cho client. Việc cấp quyền nên tách thành các nhóm:

1. **Quyền đọc runtime:** danh tính Config Server được đọc đúng repository, database view, Vault path hoặc CredHub credential cần thiết.
2. **Quyền thay đổi:** nhóm hoặc pipeline có quyền cập nhật nguồn cấu hình. Quyền này cần review và kiểm soát riêng.
3. **Quyền quản trị:** người quản lý backup, policy, credential, storage và cấu hình dịch vụ. Không cấp quyền quản trị này cho tiến trình Config Server.
4. **Quyền khôi phục:** người được phép truy cập backup và thực hiện restore, có thể cần phê duyệt kép với dữ liệu nhạy cảm.

Ngoài quyền ở backend, cần bảo vệ API Config Server. Nếu client có thể yêu cầu mọi application/profile/label, hãy xác thực client và giới hạn mạng/endpoint theo mô hình bảo mật. Không để endpoint chẩn đoán hoặc endpoint quản trị công khai ngoài dự kiến.

## 14. Kịch bản chọn backend

### Nhiều dịch vụ Spring Boot, cần review và rollback

Git thường là lựa chọn phù hợp cho cấu hình thông thường. Config Server dùng tài khoản read-only; thay đổi đi qua pull request, kiểm thử và tag/commit phát hành. Bí mật được lấy từ secret manager.

### Hệ thống nhỏ, cấu hình tĩnh được triển khai cùng hạ tầng

Native filesystem có thể đủ nếu file được mount read-only, nguồn phát hành được quản lý và volume có backup. Nếu cần lịch sử hoặc review, hãy đặt nguồn file dưới Git hoặc pipeline quản lý phiên bản.

### Tổ chức đã có database vận hành tập trung

JDBC có thể phù hợp khi nhóm cần lưu cấu hình trong database và đã có backup, quyền, audit và quy trình migration. Cần bổ sung cơ chế review/versioning để tránh việc sửa trực tiếp bản ghi không thể truy vết.

### Nhiều bí mật và yêu cầu phân quyền theo ứng dụng

Vault phù hợp khi cần policy chi tiết, audit, quản lý vòng đời secret và cơ chế cấp danh tính máy. Cần có đội ngũ vận hành Vault và kiểm thử snapshot/restore.

### Nền tảng Cloud Foundry có CredHub

CredHub có thể là lựa chọn tự nhiên nếu tổ chức đã vận hành Cloud Foundry và có quy trình quản lý credential, ACL, backup và phục hồi cho dịch vụ này.

### Cần kết hợp cấu hình thường và bí mật

Composite có thể kết hợp Git với Vault hoặc CredHub. Hãy xác định ranh giới khóa, thứ tự ưu tiên và cách xử lý khi một nguồn không sẵn sàng.

## 15. Quy trình đánh giá backend trước khi đưa vào production

1. **Phân loại dữ liệu:** tách cấu hình kỹ thuật, dữ liệu nghiệp vụ và bí mật. Chọn nguồn lưu tương ứng.
2. **Xác định nguồn chuẩn:** ghi rõ nơi có thể thay đổi dữ liệu và nơi chỉ là cache/bản clone.
3. **Đặt yêu cầu RPO/RTO:** thống nhất mức mất dữ liệu và thời gian phục hồi có thể chấp nhận.
4. **Thiết kế quyền:** tạo danh tính riêng cho Config Server, quyền read-only và policy theo phạm vi.
5. **Thiết kế backup:** ghi lịch, nơi lưu, mã hóa, người chịu trách nhiệm và thời gian giữ bản sao.
6. **Thử phục hồi:** khôi phục vào môi trường cô lập và kiểm tra nội dung, lịch sử, quyền, schema/policy.
7. **Kiểm tra API:** gọi Config Server với các application, profile và label quan trọng; so sánh property source và giá trị hiệu lực.
8. **Kiểm thử lỗi:** ngắt kết nối backend, hết hạn credential hoặc làm mất clone/cache để hiểu hành vi và log.
9. **Giám sát:** theo dõi độ trễ, lỗi xác thực, lỗi đọc cấu hình, dung lượng và trạng thái backup.
10. **Tài liệu hóa:** ghi chủ sở hữu backend, cách cấp quyền, backup/restore, quy trình thay đổi và phương án dự phòng.

## 16. Checklist kiểm tra độ bền và khả năng phục hồi

- [ ] Đã xác định backend và nguồn dữ liệu chuẩn.
- [ ] Đã phân biệt dữ liệu bền vững với cache/local clone.
- [ ] Đã xác định RPO và RTO cho Config Server và backend.
- [ ] Config Server dùng danh tính riêng với quyền đọc tối thiểu.
- [ ] Quyền ghi và quyền quản trị được giới hạn cho đúng nhóm.
- [ ] Credential và secret được lưu, cấp phát và xoay vòng an toàn.
- [ ] Backup bao gồm dữ liệu và metadata cần để đọc lại cấu hình.
- [ ] Bản backup được lưu tách biệt, mã hóa và giới hạn quyền truy cập.
- [ ] Đã thực hiện restore thử, không chỉ kiểm tra file backup tồn tại.
- [ ] Đã kiểm tra endpoint Config Server sau restore.
- [ ] Với Composite, đã kiểm tra từng backend và kết quả hợp nhất khi một nguồn lỗi.
- [ ] Có người chịu trách nhiệm và tài liệu vận hành cho từng backend.

## 17. Tài liệu tham khảo

- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Config — Native Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/native-backend.html)
- [Spring Cloud Config — JDBC Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/jdbc-backend.html)
- [Spring Cloud Config — Vault Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/vault-backend.html)
- [Spring Cloud Config — CredHub Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/credhub-backend.html)
- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
