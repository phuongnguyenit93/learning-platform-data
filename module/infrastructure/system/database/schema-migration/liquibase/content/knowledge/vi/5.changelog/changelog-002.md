# Chia changelog theo phiên bản phát hành, miền nghiệp vụ hoặc thành phần

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase giúp quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời hỗ trợ migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Changelog**, tập trung vào câu hỏi thiết kế: **nên chia các tệp changelog theo phiên bản phát hành, miền nghiệp vụ hay thành phần hệ thống?** Câu trả lời ảnh hưởng trực tiếp đến khả năng review, thứ tự migration, quyền sở hữu thay đổi, xung đột khi nhiều người cùng phát triển và độ an toàn khi triển khai.

Sau bài học, bạn cần có thể:

- Giải thích cách changelog gốc tập hợp các changelog con và vì sao thứ tự chạy quan trọng.
- So sánh ba chiến lược tổ chức: theo phiên bản phát hành, theo miền nghiệp vụ và theo thành phần.
- Chọn cấu trúc phù hợp với ứng dụng một khối, monorepo, nhiều nhóm hoặc nhiều dịch vụ.
- Dùng include, includeAll và đường dẫn ổn định để xây dựng cấu trúc có thể mở rộng.
- Tránh làm mất nhận diện changeset, gây sai lệch checksum hay phá vỡ thứ tự phụ thuộc khi tái tổ chức thư mục.
- Đưa thay đổi qua quy trình review, kiểm chứng SQL, triển khai và rollback có kiểm soát.

## 2. Các nguyên tắc cần hiểu trước khi chia tệp

### 2.1. Changelog gốc và changelog con

Một changelog là tài liệu khai báo tập hợp changeset cần được Liquibase xem xét. **Changelog gốc** (root/master changelog) là điểm vào mà Liquibase nhận khi chạy. Từ đó, nó có thể nạp các changelog con bằng include hoặc includeAll.

~~~text
db/changelog/
├── db.changelog-master.yaml          # điểm vào duy nhất
├── releases/
│   ├── 2026-11.yaml                  # changelog của một lần phát hành
│   └── 2026-12.yaml
└── ...
~~~

Một tệp con không tự chạy chỉ vì có mặt trong thư mục. Nó phải được tệp gốc hoặc một changelog đã được nạp tham chiếu đến. Vì vậy, thao tác thêm tệp mới cần đi kèm cập nhật đường dẫn nạp hoặc tuân thủ cấu hình includeAll thích hợp.

### 2.2. Tách tệp không thay đổi đơn vị thực thi

**Changeset** vẫn là đơn vị Liquibase nhận diện, kiểm tra điều kiện, chạy và ghi vào bảng DATABASECHANGELOG. Mỗi changeset được nhận diện bằng bộ ba **id + author + đường dẫn changelog** (hoặc đường dẫn logic khi dùng logicalFilePath).

Việc chia một tệp lớn thành nhiều tệp nhỏ không tạo ra ranh giới transaction mới cho cả tệp: transaction được điều khiển ở cấp changeset và chịu giới hạn của hệ quản trị cơ sở dữ liệu. Ngược lại, việc chuyển changeset sang tệp khác có thể đổi định danh và khiến Liquibase coi đó là thay đổi chưa chạy.

**Nguyên tắc thực hành:** chọn chiến lược chia tệp sớm; giữ định danh changeset ổn định sau khi chúng đã được triển khai; tạo changeset mới để sửa schema thay vì chỉnh sửa lịch sử đã chạy.

### 2.3. Thứ tự nạp và quan hệ phụ thuộc

Liquibase xử lý các changeset theo thứ tự được tạo bởi cấu trúc changelog. Nếu changeset B tạo khóa ngoại tham chiếu bảng do changeset A tạo, A phải đi trước B. Dù A và B thuộc hai miền nghiệp vụ hoặc hai thành phần khác nhau, phụ thuộc giữa chúng vẫn phải được thể hiện trong thứ tự thực thi.

Ví dụ phụ thuộc:

~~~mermaid
flowchart TD
    A["Tạo bảng customer"] --> B["Tạo bảng orders"]
    B --> C["Thêm khóa ngoại orders.customer_id"]
    C --> D["Tạo index và kiểm tra truy vấn"]
~~~

Không nên giả định rằng phân chia theo thư mục sẽ tự giải quyết phụ thuộc. Thiết kế changelog phải có một nơi thể hiện trình tự của các thay đổi liên miền.

## 3. Chiến lược A: chia theo phiên bản phát hành

Với chiến lược **theo phiên bản phát hành** (release-based), mỗi đợt phát hành có một changelog hoặc một thư mục riêng. Tên có thể dùng số phiên bản ứng dụng, ngày phát hành hoặc số thứ tự migration.

~~~text
db/changelog/
├── db.changelog-master.yaml
└── releases/
    ├── 2026-10/
    │   ├── release.yaml
    │   ├── 001-create-customer.yaml
    │   └── 002-create-orders.yaml
    ├── 2026-11/
    │   ├── release.yaml
    │   ├── 001-add-customer-status.yaml
    │   └── 002-add-order-index.yaml
    └── 2026-12/
        └── release.yaml
~~~

Changelog gốc khai báo rõ các đợt phát hành:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026-10/release.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026-11/release.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026-12/release.yaml
      relativeToChangelogFile: true
~~~

Changelog từng release lại liệt kê các changeset của đợt đó:

~~~yaml
databaseChangeLog:
  - include:
      file: 001-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: 002-add-order-index.yaml
      relativeToChangelogFile: true
~~~

**Ưu điểm:** dễ tra cứu thay đổi thuộc release nào; thuận tiện lập kế hoạch phát hành, review SQL, thiết lập điểm rollback hoặc tag theo mốc triển khai; dễ đóng băng lịch sử các release đã phát hành.

**Hạn chế:** thay đổi của nhiều miền nghiệp vụ bị gom chung trong một release; khi nhiều nhóm cùng bổ sung mục vào tệp release, xung đột merge có thể tăng; cùng một tính năng kéo dài nhiều release sẽ có các migration nằm rải rác.

**Phù hợp khi:** ứng dụng được triển khai theo phiên bản tập trung, nhóm phát hành kiểm soát thứ tự migration, hoặc có yêu cầu kiểm toán lịch sử theo release.

**Lưu ý:** tên thư mục là thông tin tổ chức, không phải cam kết rằng một release là một transaction lớn có thể rollback tất cả một cách nguyên tử. Rollback cần được thiết kế và kiểm chứng cho các changeset thực tế.

## 4. Chiến lược B: chia theo miền nghiệp vụ

Với chiến lược **theo miền nghiệp vụ** (domain-based), changelog được phân theo những phần nghiệp vụ có trách nhiệm tương đối độc lập: khách hàng, đơn hàng, thanh toán, kho hàng, v.v.

~~~text
db/changelog/
├── db.changelog-master.yaml
└── domains/
    ├── customer/
    │   ├── customer-changelog.yaml
    │   ├── 001-create-customer.yaml
    │   └── 002-add-customer-status.yaml
    ├── ordering/
    │   ├── ordering-changelog.yaml
    │   └── 001-create-orders.yaml
    └── billing/
        ├── billing-changelog.yaml
        └── 001-create-invoice.yaml
~~~

Master changelog có thể tham chiếu từng miền:

~~~yaml
databaseChangeLog:
  - include:
      file: domains/customer/customer-changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: domains/ordering/ordering-changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: domains/billing/billing-changelog.yaml
      relativeToChangelogFile: true
~~~

**Ưu điểm:** tài liệu migration gần với mã nguồn nghiệp vụ; dễ phân công ownership và reviewer; hỗ trợ phát triển lâu dài của một bounded context; một nhóm có thể quản lý phần lớn thay đổi trên các bảng của mình.

**Hạn chế:** khi các miền phụ thuộc nhau, thứ tự nạp chỉ theo toàn bộ miền sẽ trở nên khó dùng. Ví dụ, migration thứ ba của customer phụ thuộc vào bảng mới của billing nhưng tất cả customer changeset lại được nạp trước billing. Nếu chỉ tổ chức bằng thư mục, nhóm có thể không nhận ra lỗi thứ tự.

Các cách giải quyết phụ thuộc:

1. Ưu tiên thiết kế schema giảm khóa ngoại hoặc thao tác trực tiếp qua ranh giới miền nếu kiến trúc cho phép.
2. Giữ các changeset phụ thuộc ở những mốc phát hành có thứ tự nạp tường minh.
3. Kết hợp cấu trúc theo miền với một lớp điều phối release ở trên, đặc biệt khi có cross-domain migration.
4. Review sơ đồ phụ thuộc trước khi thay đổi thứ tự include; không dựa vào bảng chữ cái của tên miền.

**Phù hợp khi:** hệ thống có ranh giới nghiệp vụ rõ, mỗi miền có owner, các nhóm làm việc tương đối độc lập và có đủ quy trình xử lý migration liên miền.

## 5. Chiến lược C: chia theo thành phần kỹ thuật

Với chiến lược **theo thành phần** (component-based), changelog được đặt gần ranh giới thành phần phần mềm: service, module, plugin, bounded subsystem hoặc một thư viện có schema riêng.

~~~text
modules/
├── identity/
│   └── src/main/resources/db/changelog/identity.yaml
├── catalog/
│   └── src/main/resources/db/changelog/catalog.yaml
└── reporting/
    └── src/main/resources/db/changelog/reporting.yaml
~~~

Nếu những thành phần này **dùng chung một database** và một quy trình Liquibase, changelog gốc có thể khai báo thứ tự nạp các thành phần và chạy trên cùng một kết nối. Nếu mỗi service có **database riêng**, mỗi service thường có changelog gốc, bảng DATABASECHANGELOG và pipeline triển khai của chính nó. Không nên gom nhiều database độc lập vào một lần update như thể chúng là một transaction.

**Ưu điểm:** quyền sở hữu migration gắn với module code; dễ đóng gói, thử nghiệm và triển khai một thành phần; thuận lợi khi hệ thống phát triển thành nhiều service độc lập.

**Hạn chế:** ranh giới thành phần kỹ thuật không phải lúc nào cũng trùng với ranh giới dữ liệu. Một bảng dùng chung có thể khiến nhiều nhóm cùng muốn sửa; thứ tự migration giữa các component và các phiên bản deploy có thể không rõ.

**Phù hợp khi:** dự án có module rõ ràng, các plugin tự quản lý tài nguyên dữ liệu hoặc service sở hữu database riêng.

### Phân biệt hai tình huống hay nhầm

| Tình huống | Cách tổ chức nên cân nhắc | Điểm cần kiểm soát |
|---|---|---|
| Nhiều module cùng dùng một database | Một root changelog điều phối module, hoặc release index tập trung | Thứ tự phụ thuộc, quyền sửa bảng chung, một luồng deploy migration |
| Mỗi service có database riêng | Mỗi service sở hữu changelog và pipeline riêng | Tương thích API giữa service, thứ tự triển khai ở cấp hệ thống, không kỳ vọng rollback xuyên database |

Không nên hiểu “chia theo service” là một cơ chế Liquibase tự động chạy nhiều nguồn dữ liệu. Liquibase xử lý trên kết nối và cấu hình được chỉ định cho một lần thực thi.

## 6. Kết hợp nhiều chiến lược: release ở ngoài, domain ở trong

Đối với ứng dụng trung bình hoặc lớn dùng **một database chung**, cấu trúc kết hợp thường dễ quản lý: lớp ngoài thể hiện thứ tự phát hành; bên trong chia changeset theo miền hoặc thành phần. Nhờ vậy mỗi nhóm sở hữu tệp của mình, nhưng pipeline có một chuỗi triển khai được review tập trung.

~~~text
db/changelog/
├── db.changelog-master.yaml
└── releases/
    ├── 2026-11/
    │   ├── release.yaml
    │   ├── customer/
    │   │   ├── 001-add-loyalty-tier.yaml
    │   │   └── 002-backfill-loyalty-tier.yaml
    │   └── ordering/
    │       └── 003-create-order-item.yaml
    └── 2026-12/
        ├── release.yaml
        └── billing/
            └── 001-add-invoice-due-date.yaml
~~~

Root changelog chỉ nạp các release theo thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026-11/release.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026-12/release.yaml
      relativeToChangelogFile: true
~~~

Changelog của release thể hiện cả thứ tự giữa các miền:

~~~yaml
databaseChangeLog:
  - include:
      file: customer/001-add-loyalty-tier.yaml
      relativeToChangelogFile: true
  - include:
      file: customer/002-backfill-loyalty-tier.yaml
      relativeToChangelogFile: true
  - include:
      file: ordering/003-create-order-item.yaml
      relativeToChangelogFile: true
~~~

Ví dụ tệp customer/001-add-loyalty-tier.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-customer-001
      author: customer-team
      comment: Bổ sung phân hạng khách hàng
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: loyalty_tier
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: loyalty_tier
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: loyalty_tier
~~~

Tệp customer/002-backfill-loyalty-tier.yaml có thể là changeset riêng để điền dữ liệu hiện có. **Tách thay đổi schema và backfill** giúp đánh giá thời gian chạy, lock, cách khôi phục và khả năng triển khai từng giai đoạn. Với bảng lớn, backfill cần được thiết kế theo lô và đánh giá ảnh hưởng tới ứng dụng; không mặc định một câu UPDATE toàn bảng là an toàn.

Sự tách lớp này hỗ trợ phân quyền rõ ràng:

- **Người sở hữu domain** viết changeset, kiểm tra quy tắc dữ liệu và xây dựng rollback.
- **Người phụ trách release** xác nhận thứ tự include, khả năng tương thích, context/label và điều kiện deploy.
- **CI/CD** kiểm tra root changelog duy nhất để đảm bảo cấu trúc tổng hợp là thứ thật sự sẽ được chạy.

## 7. include và includeAll: chọn cơ chế tổng hợp

| Tiêu chí | include | includeAll |
|---|---|---|
| Cách nạp | Chỉ định từng đường dẫn | Nạp các tệp phù hợp trong một thư mục |
| Thứ tự | Tường minh theo thứ tự khai báo | Thường theo thứ tự tên tệp, hoặc comparator được cấu hình |
| Review thứ tự phụ thuộc | Dễ nhìn từ index | Phải xem toàn bộ tập tên tệp và quy tắc sắp xếp |
| Thêm migration | Cần cập nhật index | Có thể chỉ cần thêm tệp đúng thư mục |
| Rủi ro | Xung đột merge tại index | Vô tình nạp tệp không mong muốn hoặc đổi thứ tự khi đổi tên |
| Phù hợp | Release chính thức, thay đổi có phụ thuộc | Các nhóm migration độc lập với quy ước tên chặt chẽ |

Ví dụ includeAll:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: releases/2026-11/
      relativeToChangelogFile: true
~~~

Nếu dùng includeAll, cần quy định rõ tệp nào được phép nằm trong thư mục được nạp, cách đặt tên để sắp xếp, việc đọc thư mục con, và cách xử lý thay đổi thứ tự. Không đặt lẫn release index và tệp con trong cùng phạm vi includeAll nếu điều đó có thể khiến changeset bị nạp hai lần. Với một release cần thứ tự tạo bảng, nạp dữ liệu, thêm constraint, **include tường minh thường dễ kiểm toán hơn**.

Đặc biệt, tên như 1-create.yaml, 10-index.yaml, 2-data.yaml có thể được sắp xếp theo thứ tự từ điển không như mong đợi. Quy ước 001, 002, 010 ổn định hơn khi dùng thứ tự tên tệp.

Không nên đổi từ include sang includeAll hoặc ngược lại chỉ vì muốn giảm số dòng index. Hãy đánh giá số lượng changeset, thứ tự phụ thuộc, mức độ thay đổi đồng thời và mức kiểm soát cần có.

## 8. Đường dẫn, logicalFilePath và lịch sử đã triển khai

### 8.1. Vì sao di chuyển tệp là thay đổi nhạy cảm?

Liquibase theo dõi changeset trong **DATABASECHANGELOG** bằng id, author và đường dẫn tệp được dùng làm định danh. Giả sử changeset đã chạy với:

~~~text
ID:         2026-10-customer-001
AUTHOR:     customer-team
FILENAME:   db/changelog/legacy/customer.yaml
~~~

Nếu sau đó chuyển nguyên văn changeset sang releases/2026-10/customer/001-create.yaml mà không giữ đường dẫn logic, Liquibase có thể nhận diện changeset như một bản mới. Từ đó có thể phát sinh lỗi “bảng đã tồn tại”, “cột đã tồn tại”, hoặc lặp lại thao tác cập nhật dữ liệu.

**logicalFilePath** cho phép chỉ định một đường dẫn logic ổn định để giữ định danh khi vị trí vật lý thay đổi. Tuy nhiên, cách áp dụng thuộc tính này và khả năng kế thừa qua các include có thể phụ thuộc phiên bản Liquibase. Cần đối chiếu tài liệu phiên bản đang dùng và kiểm tra kết quả với bản sao DATABASECHANGELOG trước khi áp dụng cách di chuyển hàng loạt.

### 8.2. Quy trình an toàn nếu phải tái cấu trúc changelog cũ

1. Xác định các changeset đã triển khai và đường dẫn FILENAME mà Liquibase ghi nhận trong từng môi trường.
2. Sao lưu changelog hiện có và lịch sử triển khai để phục vụ review, khôi phục khi cần.
3. Giữ nguyên id, author, nội dung changeset đã chạy và định danh đường dẫn logic; chỉ thay đổi cách tổ chức nguồn theo kế hoạch.
4. Trên một cơ sở dữ liệu thử nghiệm **đã có lịch sử triển khai**, chạy validate, status và kiểm tra SQL dự kiến.
5. Kỳ vọng các changeset cũ **không** xuất hiện như pending. Nếu xuất hiện, dừng việc tái cấu trúc để sửa đường dẫn logic hoặc cấu trúc nạp.
6. Kiểm tra tiếp trên môi trường mới hoàn toàn để chắc rằng toàn bộ changelog cũng có thể chạy từ đầu.
7. Chỉ triển khai sau khi hai đường đi — nâng cấp database cũ và tạo database mới — đều đạt.

Không cập nhật thủ công DATABASECHANGELOG để che giấu lỗi nhận diện, cũng không dùng clear-checksums như giải pháp chung cho việc di chuyển tệp. Checksum giúp phát hiện nội dung lịch sử bị thay đổi; giữ được định danh vẫn chưa đủ nếu đã sửa nội dung changeset và làm checksum không khớp.

## 9. Tổ chức migration qua nhiều môi trường

Cùng một cấu trúc changelog nên được dùng cho môi trường phát triển, kiểm thử, staging và production. Đường dẫn tệp không nên mã hóa thông tin bí mật hay cấu hình máy cục bộ. URL kết nối, credential và tham số môi trường cần do cơ chế triển khai cung cấp.

**Context và label** là công cụ lọc changeset theo mục đích triển khai, không thay thế cho thiết kế thứ tự phụ thuộc. Ví dụ, dữ liệu mẫu có thể được đánh dấu chỉ chạy ở môi trường dev, nhưng changeset tạo bảng nền tảng vẫn phải có ở các môi trường cần nó. Cần kiểm tra cách xử lý context/label theo phiên bản Liquibase và cấu hình chạy thực tế.

Một quy tắc hữu ích:

- Các thay đổi cấu trúc phục vụ sản phẩm nên nằm trong dòng lịch sử được kiểm soát xuyên môi trường.
- Seed data chỉ dùng cho phát triển hoặc kiểm thử nên được đánh dấu và review rõ điều kiện chạy.
- Khi staging và production chạy các bộ lọc khác nhau, phải chấp nhận rằng lịch sử thực thi có thể khác nhau một cách có chủ đích; không được suy đoán production đã có mọi dữ liệu từ dev.

Với Spring Boot, entrypoint được chỉ rõ ở một nơi:

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Nếu CI/CD chạy migration như một bước riêng, cần thống nhất cách cấu hình ứng dụng để tránh nhiều quy trình cố thực thi thay đổi cùng lúc. Với các dịch vụ dùng chung database, một pipeline điều phối migration thường dễ kiểm soát thứ tự hơn các service tự chạy các tập changelog chồng lấn.

## 10. Quy ước đặt tên và quyền sở hữu

Một quy ước thực tế cho tên tệp có thể là:

~~~text
<release>/<domain>/<sequence>-<action>-<object>.yaml
2026-11/customer/001-add-loyalty-tier.yaml
2026-11/customer/002-backfill-loyalty-tier.yaml
2026-11/ordering/003-create-order-item.yaml
~~~

Đối với id của changeset, nên dùng giá trị ổn định, có nghĩa và không tái sử dụng trong cùng phạm vi author + đường dẫn logic. id không bắt buộc là tên tệp; nên tránh phụ thuộc vào ngày chạy thực tế vì ngày phát hành có thể thay đổi.

Nên thiết lập quy tắc:

1. Mỗi thay đổi có một changeset với mục đích rõ ràng, đủ nhỏ để review tác động và rollback.
2. Người viết ghi comment hoặc ticket khi thay đổi phức tạp; owner của domain xác nhận tính đúng đắn dữ liệu.
3. Các release đã triển khai được xem là lịch sử bất biến; sửa sai bằng changeset mới.
4. Thứ tự phụ thuộc liên domain có người chịu trách nhiệm review.
5. Changelog gốc và tệp release index phải nằm trong review của người điều phối triển khai.
6. Các thay đổi phá vỡ tương thích được triển khai theo nhiều bước khi cần, chẳng hạn expand → chuyển ứng dụng → contract.

Quy ước này giảm xung đột giữa nhóm và giúp người mới trả lời ba câu hỏi: “ai sở hữu thay đổi này?”, “nó phải chạy sau thay đổi nào?”, “release nào chứa nó?”.

## 11. Branch song song và xung đột khi merge

Khi hai nhánh cùng thêm migration vào một release, rủi ro không chỉ là conflict văn bản. Sau khi merge có thể xuất hiện thay đổi thứ tự hoặc phụ thuộc ngầm.

Ví dụ:

~~~text
Nhánh A: thêm cột customer.status
Nhánh B: tạo index customer.status
~~~

Nếu index từ nhánh B được nạp trước việc thêm cột của nhánh A, môi trường mới sẽ triển khai lỗi. Lúc review, cần kiểm tra **tập changeset sau khi merge**, không chỉ từng nhánh riêng lẻ. Hướng xử lý là đưa hai tệp vào release index theo thứ tự có chủ đích và chạy lại validate cùng SQL dự kiến từ root.

Nếu hai nhánh sửa cùng một tệp changelog đã phát hành, cần tránh hợp nhất nội dung vào changeset cũ. Mỗi thay đổi nên có changeset mới, id riêng; khi cần, dùng release index mới để giữ lịch sử theo thời gian.

Với hệ thống có nhiều nhóm, có thể giảm tranh chấp bằng cách để nhóm sở hữu tệp leaf riêng theo domain, còn người tích hợp chịu trách nhiệm file release index. Việc này chỉ hiệu quả khi CI/CD xác minh cả lịch sử nâng cấp lẫn đường đi từ database trống.

## 12. Kiểm chứng và rollback theo cấu trúc mới

Thứ tự triển khai nên được đánh giá từ **root changelog thực tế**, không từ các tệp con chạy riêng lẻ, bởi vì một tệp đơn lẻ không thể hiện đầy đủ phụ thuộc trước và sau nó.

Một chu trình kiểm chứng điển hình:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Các lệnh giả định kết nối database và đường dẫn root changelog đã được cấu hình phù hợp. validate phát hiện các vấn đề có thể kiểm tra sớm; status cho biết thay đổi đang chờ; update-sql hiển thị SQL dự kiến; update thực thi; history hỗ trợ kiểm tra lịch sử triển khai.

Trước khi chạy update ở môi trường quan trọng, cần review:

| Điểm kiểm tra | Câu hỏi cần trả lời |
|---|---|
| Thứ tự | Changeset tạo bảng/cột có đứng trước index, FK và backfill phụ thuộc không? |
| Tính toàn vẹn | Có changeset cũ đột ngột xuất hiện như pending vì đổi đường dẫn không? |
| Checksum | Có cảnh báo changeset đã chạy bị sửa nội dung không? |
| Tính tương thích | DBMS và phiên bản thực tế có hỗ trợ change type, transaction, DDL tương ứng không? |
| Dữ liệu | Backfill, update hoặc delete có ảnh hưởng lớn tới dữ liệu và thời gian khóa không? |
| Rollback | Có cách hoàn tác đã kiểm chứng không, và rollback có làm mất dữ liệu không? |
| Bộ lọc | Context, label hoặc dbms có vô tình bỏ qua migration quan trọng không? |
| Ownership | Người sở hữu bảng, miền nghiệp vụ và release đã review thay đổi chưa? |

Rollback của một release không đơn giản chỉ là “xóa thư mục release”. Liquibase dùng lịch sử changeset và cơ chế rollback phù hợp với tag, số lượng hoặc mốc triển khai để thực hiện các thao tác hoàn tác. Một số change type có thể rollback tự động; những thao tác khác cần chỉ rõ rollback và có thể không phục hồi được dữ liệu. Vì vậy, thiết kế release index nên đi cùng kế hoạch rollback và kiểm tra trên database thử nghiệm có dữ liệu tương đương.

Với các thay đổi phá vỡ tương thích (ví dụ đổi tên cột mà phiên bản ứng dụng cũ vẫn đọc), nên dùng chiến lược **expand-contract**: thêm cấu trúc mới theo hướng tương thích, chuyển dữ liệu và mã ứng dụng, xác nhận không còn người dùng cấu trúc cũ, sau đó mới xóa phần cũ bằng một changeset mới.

## 13. Chọn cấu trúc nào cho từng dự án?

| Tiêu chí | Theo release | Theo domain | Theo component |
|---|---|---|---|
| Mục tiêu chính | Truy vết từng lần phát hành | Tập trung quyền sở hữu nghiệp vụ | Gắn migration với kiến trúc module/service |
| Tổ chức nhóm | Phát hành tập trung | Nhóm theo bounded context | Nhóm theo module hoặc service |
| Thứ tự migration | Dễ điều phối tại release index | Cần xử lý phụ thuộc liên domain | Cần xử lý phụ thuộc giữa component |
| Lợi thế nổi bật | Review, audit, rollback theo đợt | Ownership và khả năng phát triển dài hạn | Triển khai và đóng gói theo thành phần |
| Thách thức nổi bật | Xung đột khi nhiều nhóm thêm vào release | Phụ thuộc chéo các miền | Module dùng chung database, ownership bảng |
| Lúc nên kết hợp | Khi release lớn có nhiều team | Khi cần mốc release tường minh | Khi nhiều component chia sẻ một database |

**Gợi ý chọn lựa:**

- **Ứng dụng nhỏ, một nhóm:** bắt đầu bằng root changelog + các tệp đánh số theo thời gian hoặc release. Tránh tạo nhiều tầng thư mục không có nhu cầu thực tế.
- **Ứng dụng lớn, một database chung:** dùng root → release index → thư mục domain/component; giữ thứ tự liên miền tường minh.
- **Nhiều service, mỗi service có database riêng:** mỗi service sở hữu changelog riêng, có kiểm tra trong pipeline của service; kiểm soát tương thích dữ liệu ở cấp giao tiếp giữa service.
- **Ứng dụng legacy nhiều lịch sử:** ưu tiên giữ nguyên các tệp đã triển khai; đưa chiến lược mới vào các release tiếp theo. Nếu cần di chuyển lịch sử, phải bảo toàn định danh và kiểm tra trên database có DATABASECHANGELOG cũ.

Đừng dùng một quy tắc thư mục cho mọi hệ thống. Cấu trúc tốt là cấu trúc có thể giải thích rõ: ai chịu trách nhiệm, thay đổi được nạp khi nào, lịch sử cũ có giữ nguyên không và CI/CD có thể kiểm chứng thứ tự thực thi hay không.

## 14. Bài tập áp dụng

Một hệ thống thương mại điện tử có ba nhóm customer, ordering và billing, cùng dùng một PostgreSQL database. Đợt phát hành mới cần:

1. Thêm cột customer.loyalty_tier.
2. Điền giá trị loyalty_tier cho khách hàng hiện có.
3. Thêm cột orders.customer_tier_snapshot lấy theo giá trị đã được chuẩn hóa.
4. Tạo index cho customer_tier_snapshot.

**Yêu cầu:** đề xuất cấu trúc thư mục và thứ tự include đủ rõ để các nhóm có thể review độc lập nhưng pipeline triển khai theo đúng thứ tự.

Một phương án:

~~~text
db/changelog/
├── db.changelog-master.yaml
└── releases/
    └── 2026-11/
        ├── release.yaml
        ├── customer/
        │   ├── 001-add-loyalty-tier.yaml
        │   └── 002-backfill-loyalty-tier.yaml
        └── ordering/
            ├── 003-add-tier-snapshot.yaml
            └── 004-index-tier-snapshot.yaml
~~~

release.yaml dùng include tường minh theo thứ tự 001 → 002 → 003 → 004. Nhóm customer sở hữu phần cột và backfill khách hàng; nhóm ordering sở hữu cột snapshot và index; người điều phối release chịu trách nhiệm kiểm chứng phụ thuộc và khả năng tương thích. Nếu dữ liệu cần đồng bộ dần trong thời gian chạy ứng dụng, phải thiết kế các bước migrate tương thích và xác định thời điểm chuyển mã ứng dụng, không giả định một lần chạy update sẽ xử lý an toàn tất cả dữ liệu lớn.

Để tự kiểm tra, hãy trả lời: nếu chuyển tệp 001 sang một đường dẫn khác sau khi đã chạy trên staging, liệu DATABASECHANGELOG còn nhận diện cùng changeset không? Điều gì sẽ xảy ra nếu 004 được nạp trước 003? Nếu rollback xóa cột loyalty_tier, dữ liệu đã điền vào cột đó có phục hồi được không? Ba câu hỏi này kiểm tra đúng các rủi ro cốt lõi của việc tổ chức changelog.

## 15. Ghi nhớ

Chia changelog là một quyết định về **thứ tự thay đổi, quyền sở hữu và tính ổn định của lịch sử**. Theo phiên bản phát hành giúp kiểm soát mốc triển khai; theo miền nghiệp vụ giúp nhóm quản lý dữ liệu mình sở hữu; theo thành phần giúp migration đi cùng kiến trúc phần mềm. Với database dùng chung và nhiều nhóm, tổ chức kết hợp root → release → domain/component thường cho mức kiểm soát rõ ràng.

Bất kể chọn cách nào, hãy giữ id/author/đường dẫn logic của changeset đã triển khai ổn định, review phụ thuộc qua root changelog, kiểm tra SQL dự kiến và rollback trên database thử nghiệm, đồng thời dùng một quy trình triển khai có thể truy vết qua DATABASECHANGELOG. Đây là nền tảng để quản lý thay đổi schema và dữ liệu bằng Liquibase an toàn qua nhiều môi trường và nhiều đợt phát hành.
