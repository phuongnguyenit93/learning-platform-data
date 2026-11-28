# Ánh xạ định danh ổn định giữa LDAP và cơ sở dữ liệu ứng dụng

Một ứng dụng Spring Boot quản lý nhân sự cần đọc tài khoản từ LDAP, nhưng lịch sử đơn hàng, phiếu phê duyệt và thiết lập cá nhân lại nằm trong cơ sở dữ liệu riêng. Hôm nay nhân viên có DN `uid=lan,ou=people,dc=example,dc=org`; ngày mai bộ phận quản trị đổi tên đăng nhập hoặc di chuyển entry sang `ou=alumni`. Nếu bảng nghiệp vụ tham chiếu trực tiếp DN, email hoặc tên đăng nhập, hệ thống có thể mất liên kết với đúng người, sinh bản ghi trùng hoặc nguy hiểm hơn là gán nhầm quyền và dữ liệu cho một tài khoản khác.

Trong chương **Đồng bộ dữ liệu** của module **SPRING_DATA_LDAP**, bài này giải thích cách thiết kế **ánh xạ định danh ổn định** giữa entry LDAP và bản ghi trong cơ sở dữ liệu ứng dụng. Spring Data LDAP cung cấp `LdapRepository` và `LdapTemplate` để đọc entry theo DN, `objectClass`, schema và filter; tầng đồng bộ có trách nhiệm nhận diện **cùng một thực thể qua các lần thay đổi**, thực hiện upsert và xử lý vòng đời mà không đánh mất quan hệ dữ liệu. Đây là bài toán bổ sung cho truy vấn và CRUD LDAP, không chỉ là sao chép thuộc tính.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **khóa nội bộ của ứng dụng**, **định danh ổn định do directory cung cấp**, **DN hiện tại** và các thuộc tính có thể đổi như `uid`, `cn`, `mail`.
2. Chọn định danh phù hợp với loại directory (ví dụ `entryUUID` hoặc `objectGUID`), hiểu giới hạn của độ ổn định và phạm vi duy nhất.
3. Thiết kế bảng ánh xạ với ràng buộc duy nhất theo **nguồn LDAP + định danh ngoại**, dùng khóa nội bộ cho quan hệ nghiệp vụ.
4. Đọc entry qua Spring LDAP/Spring Data LDAP, chuẩn hóa khóa và đồng bộ theo cách **idempotent**.
5. Phân biệt rename/move, cập nhật thuộc tính, xóa rồi tạo lại entry, tài khoản bị vô hiệu hóa và việc không thấy entry do lỗi truy vấn/ACL.
6. Thiết kế kiểm tra tính đầy đủ, cơ chế đối soát, xử lý lỗi và kiểm thử để tránh ghép nhầm hai danh tính.

## 2. Vì sao DN, tên đăng nhập và email không nên là khóa liên kết bất biến?

Directory LDAP tổ chức entry thành cây phân cấp. DN (Distinguished Name) là đường dẫn định danh của entry, ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=lan
└── ou=alumni
~~~

Ban đầu:

~~~text
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Nguyen
mail: lan@example.org
~~~

Sau khi đổi tên đăng nhập hoặc di chuyển entry, DN có thể trở thành:

~~~text
dn: uid=lan.nguyen,ou=alumni,dc=example,dc=org
uid: lan.nguyen
cn: Lan Nguyen
mail: lan.nguyen@example.org
~~~

Đây vẫn có thể là **cùng một entry** nếu directory thực hiện thao tác rename/move và giữ nguyên định danh nội tại của entry.

| Giá trị | Vai trò | Có thể đổi? | Có nên dùng làm khóa bất biến giữa các hệ thống? |
| --- | --- | --- | --- |
| **DN** | Định vị entry hiện tại trong cây LDAP. | Có khi đổi RDN hoặc chuyển nhánh. | **Không**; lưu như thuộc tính vị trí có thể cập nhật. |
| **`uid` / `sAMAccountName`** | Tên đăng nhập hoặc mã nghiệp vụ theo schema. | Có thể đổi hoặc được tái sử dụng. | Chỉ khi có cam kết quản trị đủ mạnh; mặc định **không**. |
| **`mail` / `cn`** | Thuộc tính liên hệ và hiển thị. | Có thể đổi, thiếu hoặc trùng. | **Không**. |
| **`entryUUID` / `objectGUID`** | Mã nhận diện entry do server hỗ trợ. | Thường giữ nguyên qua rename/move của cùng entry; có thể thay sau xóa và tạo lại hoặc migration. | **Ưu tiên trong phạm vi nguồn phù hợp**, sau khi kiểm tra khả năng hỗ trợ. |
| **`app_user.id`** | Khóa chính do ứng dụng cấp cho bản ghi nội bộ. | Được thiết kế bất biến trong ứng dụng. | **Có**; dùng cho khóa ngoại nghiệp vụ. |

**Sai lầm thường gặp:** tạo quan hệ `order.user_dn → LDAP DN` hoặc dùng `mail` làm khóa chính của bảng `app_user`. Người dùng thay email, DN hoặc username thì quan hệ hỏng. Việc một người khác được cấp lại email/username cũ còn có thể khiến dữ liệu và quyền bị gán nhầm.

Giải pháp là lưu **mối liên hệ giữa một định danh entry ổn định của nguồn LDAP và một định danh nội bộ bất biến**; xem DN và các thuộc tính hồ sơ như dữ liệu có thể cập nhật.

## 3. Định danh ổn định trong các triển khai LDAP

LDAP là giao thức, không áp đặt một thuộc tính định danh ổn định giống nhau cho mọi server. Cần khảo sát directory và schema trước khi viết mapper.

### 3.1. `entryUUID` của các server hỗ trợ RFC 4530

RFC 4530 mô tả thuộc tính hoạt động (*operational attribute*) `entryUUID` để định danh entry một cách duy nhất trong directory hỗ trợ chuẩn này. Ví dụ LDIF minh họa:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
entryUUID: 4a146e6a-89d1-4125-9bb3-fd29ed3d51b6
uid: lan
cn: Lan Nguyen
mail: lan@example.org
~~~

Với một entry được rename/move trong cùng directory, `entryUUID` được dùng để tiếp tục nhận diện entry đó. Nếu entry bị **xóa rồi tạo lại**, entry mới thường có `entryUUID` khác, ngay cả khi trùng DN và `uid`. Đó là **hai vòng đời entry khác nhau** và không được tự động nối vào cùng tài khoản ứng dụng.

`entryUUID` là **operational attribute**, nên một truy vấn mặc định chỉ lấy user attributes có thể không trả về. Khi dùng `ldapsearch`, `LdapTemplate` hay repository, cần yêu cầu thuộc tính này một cách tường minh nếu server và ACL cho phép. Một số directory không hỗ trợ `entryUUID`; không nên tự bịa giá trị thay thế khi thiếu dữ liệu.

### 3.2. `objectGUID` trong Microsoft Active Directory

Active Directory cung cấp thuộc tính `objectGUID` để nhận diện đối tượng. Đây là giá trị **nhị phân**, không phải một chuỗi `uid` thông thường. Khi đọc qua JNDI/Spring LDAP, cần chuyển `byte[]` sang biểu diễn GUID chuẩn bằng bộ chuyển đổi đúng định dạng Active Directory, trong đó có quy tắc về thứ tự byte của một số trường.

Không dùng `new String(bytes)` hoặc diễn giải 16 byte theo quy tắc UUID chung nếu chưa xử lý định dạng GUID của AD. Khi triển khai, hãy chọn **một dạng canonical** để lưu và so sánh GUID, và kiểm thử chuyển đổi bằng GUID đã biết. `objectSID` phục vụ nhận diện security principal nhưng có ngữ nghĩa/vòng đời khác; không dùng thay `objectGUID` mà không đánh giá yêu cầu.

### 3.3. Không có một khóa nào ổn định vô hạn trong mọi trường hợp

- **Rename/move trong cùng directory:** ưu tiên giữ cùng liên kết nếu định danh entry không đổi.
- **Xóa rồi tạo lại:** mã entry mới thường khác. Không tự ghép chỉ vì DN, email hoặc username giống nhau.
- **Migration/reprovision sang directory khác:** mã do server cấp có thể đổi. Cần **quy trình ánh xạ lại có kiểm chứng** dựa trên nguồn có thẩm quyền, không nối tự động bằng tên hiển thị.
- **Nhiều directory:** cùng chuỗi external ID không nên bị xem là cùng danh tính nếu đến từ hai nguồn khác nhau.
- **Directory không cung cấp stable ID đáng tin cậy:** cần xác định khóa ngoài có cam kết quản trị rõ ràng hoặc cơ chế đối soát thủ công. Phải thể hiện rủi ro trong thiết kế; không âm thầm dùng DN làm “stable ID”.

Vì vậy, khóa ánh xạ nên là cặp **`(provider_key, external_id)`**. `provider_key` nhận diện **nguồn danh tính**, chẳng hạn một directory/forest/tenant được cấu hình; `external_id` là `entryUUID` hoặc GUID đã được chuẩn hóa theo quy tắc của nguồn đó. Định nghĩa và phạm vi của `provider_key` phải được giữ ổn định theo vòng đời tích hợp.

## 4. Kiến trúc hai định danh

Ứng dụng nên có **một ID nội bộ** độc lập với cấu trúc LDAP. Các bảng nghiệp vụ tham chiếu ID này; một bảng liên kết chuyên trách lưu định danh ngoại.

~~~mermaid
flowchart LR
    LDAP["LDAP directory<br/>entryUUID / objectGUID<br/>DN, uid, mail"] --> Reader["Spring LDAP<br/>LdapTemplate / repository"]
    Reader --> Sync["Identity reconciliation<br/>normalize + upsert"]
    Sync --> Link["directory_identity_link<br/>provider_key + external_id"]
    Link --> User["app_user<br/>id: UUID"]
    Order["orders / audit / approvals"] --> User
~~~

Một mô hình quan hệ tham khảo:

~~~text
LDAP:
  provider_key = corp-ldap
  external_id  = 4a146e6a-89d1-4125-9bb3-fd29ed3d51b6
  current_dn   = uid=lan,ou=people,dc=example,dc=org
                 |
                 | liên kết ổn định theo (provider_key, external_id)
                 v
directory_identity_link:
  app_user_id  = b5611b6f-d301-495e-8a2a-897ab2a2f38d
                 |
                 v
app_user:
  id           = b5611b6f-d301-495e-8a2a-897ab2a2f38d
                 ^
                 |
orders.created_by_user_id, approvals.assignee_id, audit.actor_user_id
~~~

Khi DN thay đổi, chỉ cần cập nhật trường biểu diễn DN trên liên kết hoặc hồ sơ, **không đổi `app_user.id`**. Nếu một ứng dụng kết nối nhiều LDAP/identity provider, cùng một `app_user` có thể liên kết với nhiều tài khoản ngoài theo chính sách liên kết rõ ràng; tuyệt đối không dựa riêng vào việc trùng email để tự hợp nhất.

## 5. Thiết kế bảng ánh xạ trong cơ sở dữ liệu

Giả sử ứng dụng đã có bảng `app_user(id UUID PRIMARY KEY, ...)`. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE directory_identity_link (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_user_id        UUID NOT NULL REFERENCES app_user(id),
    provider_key       VARCHAR(100) NOT NULL,
    external_id        VARCHAR(200) NOT NULL,
    relative_dn        TEXT,
    username_snapshot  VARCHAR(200),
    email_snapshot     VARCHAR(320),
    sync_status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_seen_run_id   UUID,
    last_seen_at       TIMESTAMPTZ,
    version            BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_directory_identity
        UNIQUE (provider_key, external_id),
    CONSTRAINT ck_directory_sync_status
        CHECK (sync_status IN ('ACTIVE', 'MISSING', 'DISABLED'))
);

CREATE INDEX idx_directory_identity_app_user
    ON directory_identity_link (app_user_id);
~~~

| Cột | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `app_user_id` | Khóa nội bộ mà nghiệp vụ sử dụng. | Không thay khi entry LDAP đổi DN/tên. |
| `provider_key` | Nguồn định danh được cấu hình. | Phải được quản trị ổn định, tránh nhập nhằng directory. |
| `external_id` | Mã entry ổn định đã chuẩn hóa. | Không rỗng; cùng nguồn + mã phải duy nhất. |
| `relative_dn` | DN hiện tại tương đối với base đã thỏa thuận của nguồn. | Chỉ là snapshot; cập nhật khi rename/move, không dùng làm khóa liên kết. |
| `username_snapshot`, `email_snapshot` | Thuộc tính để hiển thị/tìm kiếm theo nghiệp vụ. | Có thể thay đổi; không tự quyết định ghép danh tính. |
| `sync_status` | Trạng thái liên kết quan sát được từ đồng bộ. | Không đồng nghĩa trực tiếp với trạng thái đăng nhập thực tế của user. |
| `last_seen_run_id`, `last_seen_at` | Dấu vết đối soát lần đồng bộ đầy đủ. | Chỉ đánh dấu sau khi đọc được entry. |
| `version` | Hỗ trợ phát hiện cập nhật cạnh tranh nếu được sử dụng. | Không thay thế checkpoint từ nguồn LDAP. |

Trường `relative_dn` trong bảng trên giả định code Spring LDAP sử dụng chung một **context base** đã biết (ví dụ `dc=example,dc=org`). `DirContextOperations.getDn()` thường cung cấp tên tương đối với base của `ContextSource`. Nếu ứng dụng cần DN tuyệt đối, phải dựng từ context base theo API DN phù hợp và bảo đảm định nghĩa lưu trữ nhất quán. Đừng lưu lẫn DN tương đối và DN đầy đủ vào cùng cột.

Ràng buộc `UNIQUE (provider_key, external_id)` là **lớp bảo vệ bắt buộc khỏi trùng liên kết khi nhiều worker đồng bộ song song**. Nếu nghiệp vụ chỉ cho phép một account của mỗi provider trên một `app_user`, có thể bổ sung ràng buộc duy nhất `(provider_key, app_user_id)`; đừng thêm ràng buộc đó khi cho phép liên kết nhiều account cùng nguồn.

Các cột snapshot cần được quản lý theo chính sách dữ liệu cá nhân: chỉ lưu trường thực sự cần thiết và giới hạn quyền truy cập, retention/audit tương ứng.

## 6. Đọc stable ID bằng Spring LDAP

Một bộ đọc đồng bộ có thể sử dụng `LdapTemplate` của Spring LDAP (được Spring Data LDAP starter đưa vào ứng dụng Spring Boot). Repository dùng `@Entry` và `LdapRepository` cũng phù hợp để lấy entity, nhưng với **operational attribute** như `entryUUID`, `LdapTemplate` cho phép chỉ định rõ tập attribute cần đọc và mapper kiểm tra định danh ngay tại ranh giới.

### 6.1. Dependency và kết nối

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
}
~~~

`application.yml` minh họa:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Giá trị từ môi trường có thể là:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=sync-reader,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret-cua-moi-truong>
~~~

URL, base DN, tài khoản bind và ACL của server phải tương ứng với directory thật. `ldaps://` dùng TLS ngay khi kết nối; `ldap://` không tự nâng cấp thành StartTLS. Tránh dùng tài khoản quản trị directory để đồng bộ dữ liệu chỉ đọc. Quản lý mật khẩu qua secret manager hoặc cấu hình bí mật của môi trường, không commit vào Git.

### 6.2. Định nghĩa bản ghi đầu vào

Ví dụ directory hỗ trợ `entryUUID` của RFC 4530:

~~~java
public record DirectoryPerson(
        String externalId,
        String relativeDn,
        String uid,
        String commonName,
        String email) {
}
~~~

Trong DTO, `externalId` là UUID dạng canonical, `relativeDn` là DN tương đối theo context source, các trường còn lại là snapshot có thể thay đổi. Cần xử lý `mail == null` vì email là thuộc tính tùy chọn trong nhiều schema.

### 6.3. Query có yêu cầu tường minh `entryUUID`

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPersonReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Ví dụ dành cho tập dữ liệu thử nghiệm có kích thước nhỏ.
    // Đồng bộ production cần phân trang/giới hạn và cơ chế checkpoint.
    public List<DirectoryPerson> readPeople() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("entryUUID", "uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(query, this::mapPerson);
    }

    private DirectoryPerson mapPerson(Object source) {
        DirContextOperations entry = (DirContextOperations) source;
        String rawId = entry.getStringAttribute("entryUUID");
        if (rawId == null || rawId.isBlank()) {
            throw new IllegalStateException(
                    "LDAP entry khong co stable ID entryUUID");
        }

        // RFC 4530 biểu diễn UUID bằng chuỗi; chuẩn hóa, kiểm tra cú pháp.
        String externalId = UUID.fromString(rawId).toString();

        return new DirectoryPerson(
                externalId,
                entry.getDn().toString(),
                entry.getStringAttribute("uid"),
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail"));
    }
}
~~~

Trong ví dụ, `spring.ldap.base=dc=example,dc=org` và `.base("ou=people")` khiến truy vấn tìm người dưới nhánh `ou=people,dc=example,dc=org`. `entry.getDn()` được lưu như DN tương đối với base của context source; **không** dùng giá trị này làm `externalId`.

Lưu ý kỹ thuật:

- `entryUUID` không có trong mọi server. Nếu thiếu do server không hỗ trợ, ACL hoặc projection sai, **fail rõ ràng** để người vận hành sửa cấu hình. Không âm thầm rơi về `uid`/DN vì sẽ tạo liên kết sai sau này.
- `UUID.fromString(...)` phù hợp với `entryUUID` dạng chuỗi UUID. Không tái sử dụng nguyên cách này cho `objectGUID` nhị phân của Active Directory; cần adapter chuyển mã chuyên biệt.
- `LdapTemplate.search(...)` trả danh sách các entry phù hợp, không tự bảo đảm có một snapshot nhất quán nếu dữ liệu thay đổi trong lúc quét.
- Code chỉ minh họa phép đọc tập nhỏ. Directory lớn cần giới hạn dữ liệu, phân trang (nếu server hỗ trợ) và retry/checkpoint có kiểm soát; không gọi một search không giới hạn rồi giữ toàn bộ entry trong RAM.
- Nên xác minh rằng directory cho phép đọc thuộc tính định danh đặc biệt dưới tài khoản bind. Một số operational attributes chỉ trả về khi được yêu cầu tường minh.

### 6.4. Cùng nguồn LDAP, nhiều adapter định danh

Trong một hệ thống hỗ trợ cả OpenLDAP và Active Directory, hãy tách việc **đọc và chuẩn hóa stable ID theo provider** khỏi thuật toán đồng bộ chung. Ví dụ:

~~~java
public interface DirectoryIdentityAdapter {
    String providerKey();

    // Mã ổn định của entry, đã chuyển sang chuỗi canonical theo provider.
    String externalIdOf(Object directoryEntry);
}
~~~

Ý tưởng: adapter OpenLDAP đọc `entryUUID` dạng chuỗi; adapter Active Directory đọc `objectGUID` dưới dạng `byte[]` rồi chuyển đúng định dạng GUID; các bước lưu quan hệ `(provider_key, external_id)` và cập nhật snapshot dùng lại cùng một luồng xử lý.

Interface ở trên minh họa ranh giới kiến trúc, chưa phải implementation đầy đủ. Với hệ thống thực, nên dùng kiểu cụ thể như `DirContextOperations` trong adapter và xây test bằng vector giá trị GUID/UUID xác định trước.

## 7. Upsert idempotent: nhận diện trước, cập nhật sau

**Idempotent** nghĩa là đồng bộ cùng một entry nhiều lần sẽ duy trì **cùng liên kết** và không tạo thêm người dùng hoặc quan hệ trùng.

Quy trình cho mỗi entry:

1. Đọc `provider_key` từ cấu hình nguồn và `external_id` do adapter lấy/chuẩn hóa. Nếu external ID thiếu hoặc không hợp lệ, đánh lỗi.
2. Tìm `directory_identity_link` theo **`(provider_key, external_id)`**.
3. Nếu **đã tồn tại**, giữ nguyên `app_user_id`, cập nhật DN hiện tại và những snapshot được phép cập nhật, đánh dấu đã thấy ở run hiện tại.
4. Nếu **chưa tồn tại**, gọi quy trình provisioning/linking được ủy quyền để quyết định có tạo `app_user` mới hay kết nối với một user đã được xác minh. Sau đó thêm link.
5. Thực hiện trong transaction cơ sở dữ liệu, xử lý race bằng unique constraint và retry theo chính sách. Hoàn tất ghi và đánh dấu tiến độ trước khi coi entry đã xử lý xong.

~~~mermaid
flowchart TD
    A["Đọc entry LDAP"] --> B["Lấy provider_key + external_id"]
    B --> C{"Stable ID hợp lệ?"}
    C -- "Không" --> D["Ghi nhận lỗi và dừng xử lý entry"]
    C -- "Có" --> E["Tra link theo cặp khóa duy nhất"]
    E --> F{"Có link?"}
    F -- "Có" --> G["Giữ app_user_id, cập nhật snapshot"]
    F -- "Chưa" --> H["Provision hoặc link có kiểm chứng"]
    H --> I["Insert link và xử lý unique conflict"]
    G --> J["Ghi last_seen_run_id, commit"]
    I --> J
~~~

### 7.1. Ví dụ thao tác upsert ở PostgreSQL

Khi đã xác định được `:appUserId` cho một entry (từ link cũ hoặc quy trình provisioning), có thể dùng:

~~~sql
INSERT INTO directory_identity_link (
    app_user_id,
    provider_key,
    external_id,
    relative_dn,
    username_snapshot,
    email_snapshot,
    sync_status,
    last_seen_run_id,
    last_seen_at
)
VALUES (
    :appUserId,
    :providerKey,
    :externalId,
    :relativeDn,
    :uid,
    :email,
    'ACTIVE',
    :runId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (provider_key, external_id)
DO UPDATE SET
    relative_dn       = EXCLUDED.relative_dn,
    username_snapshot = EXCLUDED.username_snapshot,
    email_snapshot    = EXCLUDED.email_snapshot,
    sync_status       = 'ACTIVE',
    last_seen_run_id  = EXCLUDED.last_seen_run_id,
    last_seen_at      = CURRENT_TIMESTAMP,
    version           = directory_identity_link.version + 1
RETURNING app_user_id;
~~~

Chú ý: nhánh `ON CONFLICT DO UPDATE` **không cập nhật `app_user_id`**. Nếu một job đồng bộ lặp lại với `:appUserId` khác, database vẫn giữ liên kết cũ cho cùng `(provider_key, external_id)`. Kết quả `RETURNING app_user_id` giúp tầng service biết ID đang được liên kết.

**Đây chưa phải toàn bộ quy trình tạo user:** Không được cứ mỗi lần không tìm thấy link là tạo `app_user` rồi chạy upsert một cách mù quáng. Hai worker có thể cùng quan sát “chưa có” và tạo hai bản ghi `app_user`. Khi có cạnh tranh, cần transaction bao trọn provisioning + insert link, unique constraint, rollback và **retry từ bước tra cứu**; hoặc dùng cơ chế khóa/queue phù hợp. User mới chỉ nên trở thành bản ghi hoạt động sau khi quy trình linking hoàn tất.

### 7.2. Ghép với tài khoản nội bộ đã tồn tại

Đây là điểm dễ gây lộ dữ liệu nhất. Ví dụ một entry mới có email `lan@example.org`, trong database đã có `app_user` sử dụng email đó. **Không tự gắn entry này vào user cũ chỉ vì trùng email**, vì email có thể tái sử dụng, thay đổi hoặc không được directory xác minh.

Các cơ chế đáng tin cậy hơn gồm: mã nhân sự được bảo đảm duy nhất và bất biến bởi hệ thống nguồn có thẩm quyền; mapping do quá trình provisioning ban đầu tạo; hoặc liên kết được người quản trị/người sở hữu xác nhận theo quy trình có audit. Mỗi tổ chức phải xác định rõ chính sách linking và ai được phép thực hiện.

Nếu chưa có bằng chứng đủ mạnh, giữ trạng thái **chờ đối soát** thay vì ghép tự động. Định danh ngoài mới **không đồng nghĩa** là cùng một người với một user nội bộ có tên hoặc email giống nhau.

## 8. Các biến cố vòng đời và cách xử lý

| Sự kiện ở LDAP | Stable ID | DN / thuộc tính hiển thị | Hành động đối với liên kết nội bộ |
| --- | --- | --- | --- |
| Đổi `cn`, email | Không đổi đối với cùng entry. | Giá trị hiển thị đổi. | Cập nhật snapshot theo chính sách nguồn dữ liệu; giữ `app_user_id`. |
| Đổi `uid` hoặc RDN | Không đổi nếu chỉ rename cùng entry. | `uid` và/hoặc DN đổi. | Giữ liên kết, cập nhật DN/username. |
| Chuyển từ `ou=people` sang `ou=alumni` | Có thể vẫn giữ nguyên với cùng entry. | DN đổi, entry có thể ra khỏi search base cũ. | Phải xem lại phạm vi tìm kiếm/chính sách lifecycle, không kết luận bị xóa ngay. |
| Tài khoản LDAP bị vô hiệu hóa | Có thể không đổi. | Thuộc tính trạng thái đổi theo schema server. | Áp dụng chính sách khóa truy cập ứng dụng; không nhất thiết xóa hồ sơ nghiệp vụ. |
| Xóa entry | Entry không còn. | Không thể tìm entry nữa. | Đánh dấu mất/chờ xác nhận; tách khỏi login nếu chính sách yêu cầu, giữ audit. |
| Tạo entry mới trùng username/DN cũ | **Thường có stable ID mới**. | Có thể giống entry cũ. | Xem là identity mới; không tái sử dụng liên kết cũ chỉ theo username/DN. |
| Chuyển dữ liệu sang directory mới | Có thể đổi do import/reprovision. | Đường dẫn, schema hoặc tên có thể đổi. | Quy trình remapping có kiểm chứng; lưu audit để tránh gán nhầm. |

Trạng thái **MISSING** trong ví dụ bảng chỉ mang nghĩa “job không thấy entry theo phạm vi/quyền/điều kiện hiện tại”. Nó **không đồng nghĩa** “tài khoản đã bị xóa” và càng không đồng nghĩa người đó đã nghỉ việc.

### 8.1. Minh họa rename đúng và xóa/tạo lại sai

Giả sử ban đầu:

~~~text
provider_key = corp-ldap
external_id  = 4a146e6a-89d1-4125-9bb3-fd29ed3d51b6
DN           = uid=lan,ou=people,dc=example,dc=org
app_user_id  = b5611b6f-d301-495e-8a2a-897ab2a2f38d
~~~

**Trường hợp A — Rename:** DN đổi thành `uid=lan.nguyen,ou=people,dc=example,dc=org` nhưng `entryUUID` không đổi. Job tìm thấy link cũ qua external ID; cập nhật `relative_dn` và giữ nguyên `app_user_id`. Lịch sử đơn hàng vẫn trỏ đúng người.

**Trường hợp B — Xóa rồi tạo lại:** server tạo entry mới `uid=lan,...` nhưng `entryUUID` khác. Job không tìm thấy link theo external ID mới. Nó phải chạy quy trình provisioning/linking có kiểm chứng, không được tự sử dụng `app_user_id` cũ nhờ trùng `uid` hoặc `mail`. Việc này phòng tránh nguy cơ người mới được xem dữ liệu của người trước.

## 9. Chạy đồng bộ đầy đủ và phát hiện entry biến mất

Đồng bộ có thể theo **full scan định kỳ**, **incremental changes** hoặc kết hợp. Full scan đơn giản để hiểu và dùng để đối soát, nhưng yêu cầu cẩn trọng khi đánh dấu entry không còn.

### 9.1. Quy trình một lần full scan

1. Tạo `runId` duy nhất và ghi thông tin job, gồm `provider_key`, phạm vi nhánh, bộ lọc, thời điểm bắt đầu.
2. Đọc entry theo trang hoặc theo giới hạn phù hợp với directory; lấy stable ID và những attribute cần thiết.
3. Reconcile/upsert từng entry thành công và ghi `last_seen_run_id = runId`.
4. Xác nhận **mọi trang đều thành công**, không timeout, không bị lỗi chứng chỉ, ACL hoặc size limit, và không bị dừng giữa chừng.
5. Chỉ sau khi quét **hoàn chỉnh**, đánh dấu các liên kết thuộc phạm vi quét mà không xuất hiện trong lần này là **ứng viên MISSING**, sau đó xử lý theo chính sách grace period/tái kiểm tra.

Ví dụ câu lệnh minh họa bước 5:

~~~sql
-- Chỉ chạy sau khi xác minh full scan thành công.
-- Phải giới hạn đúng provider và phạm vi mà job thực sự bao phủ.
UPDATE directory_identity_link
SET sync_status = 'MISSING',
    version = version + 1
WHERE provider_key = :providerKey
  AND sync_status = 'ACTIVE'
  AND (last_seen_run_id IS NULL OR last_seen_run_id <> :runId);
~~~

**Giới hạn của câu lệnh:** chỉ đúng nếu job quét **toàn bộ identity thuộc provider đó**. Nếu job chỉ quét một OU, filter hoặc một tenant con, phải có cột/phạm vi quản lý riêng và thêm điều kiện để không đánh dấu nhầm những entry hợp lệ bên ngoài vùng quét.

Không chạy bước 5 khi LDAP timeout, phân trang thiếu trang, tìm kiếm bị từ chối do ACL hoặc người dùng được chuyển sang OU mà job không quét. Ngay cả một full scan thành công cũng có thể quan sát những thời điểm khác nhau nếu directory thay đổi giữa các trang, vì vậy cần chính sách grace period, double-check hoặc change feed phù hợp trước khi vô hiệu hóa liên kết.

### 9.2. Incremental sync và checkpoint

Với directory lớn, nên xem xét cơ chế thay đổi do **provider cụ thể** hỗ trợ: đồng bộ thay đổi theo cookie/changelog, DirSync ở môi trường Active Directory, syncrepl ở môi trường OpenLDAP hoặc một API đồng bộ được tổ chức cung cấp. Đừng giả định mọi server LDAP đều hỗ trợ cùng loại change feed.

Thời điểm `modifyTimestamp` có thể hữu ích cho kiểm tra hoặc truy vấn tăng dần, nhưng **không đủ để mặc định đảm bảo không bỏ sót sự kiện**: độ phân giải thời gian, replication, đồng hồ, quyền đọc, cách xóa entry và thứ tự cập nhật khác nhau theo server. Nếu dùng mốc thời gian, cần vùng chồng lấn, khử trùng lặp và full reconciliation định kỳ; cơ chế thay đổi có checkpoint của provider thường phù hợp hơn.

Quy tắc quan trọng cho checkpoint:

- Chỉ lưu checkpoint đã được xác nhận **sau khi** ghi các thay đổi tương ứng thành công.
- Chấp nhận một batch có thể xử lý lại sau crash; dùng khóa duy nhất và thao tác idempotent để replay an toàn.
- Khi sự kiện đến sai thứ tự, cần so sánh version/sequence do nguồn hỗ trợ hoặc đọc lại trạng thái hiện hành; tránh cập nhật bằng sự kiện cũ đè lên snapshot mới.
- Nếu checkpoint bị mất, không mặc định phát lại được mọi thay đổi; tùy nguồn có thể phải full scan và đối soát.

### 9.3. Không đồng nhất “thiếu entry” với “xóa vĩnh viễn”

Một search không thấy entry có thể do nhiều nguyên nhân:

- Người dùng đã chuyển OU ra ngoài search base.
- ACL của tài khoản bind bị sửa khiến entry bị ẩn.
- Filter `objectClass` hoặc thuộc tính được đổi theo schema mới.
- Replication chưa kịp đồng bộ sang replica đang đọc.
- Job chưa đọc hết trang, bị timeout hoặc gặp giới hạn server.
- Entry thực sự bị xóa.

Do đó **hard delete** bản ghi `app_user` và dữ liệu nghiệp vụ sau một kết quả search rỗng là thiết kế rất rủi ro. Giữ liên kết để phục vụ audit và quyết định tái kích hoạt; áp dụng quy trình vô hiệu hóa đăng nhập có xác minh nếu chính sách yêu cầu. Với hệ thống nhạy cảm, ưu tiên cơ chế disable tài khoản khi có tín hiệu authoritative hơn là suy từ một lần vắng mặt.

## 10. Đồng bộ nhóm và quan hệ thành viên

Không chỉ user, nhóm LDAP cũng có DN và có thể bị đổi tên hoặc di chuyển. Nhóm có thể lưu membership dưới dạng danh sách DN, ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: developers
uniqueMember: uid=lan,ou=people,dc=example,dc=org
~~~

Nếu quan hệ nhóm trong database được lưu bằng **DN thành viên**, rename user có thể làm phát sinh dữ liệu cũ hoặc không khớp. Một mô hình bền hơn là:

1. Đọc nhóm và các DN thành viên theo schema nguồn.
2. Giải quyết các DN đó thành entry thành viên và **stable external ID** tương ứng khi nguồn/ACL cho phép.
3. Ánh xạ stable ID thành `app_user.id`; lưu quan hệ nhóm–user bằng ID nội bộ.
4. Khi thành viên đổi DN, quan hệ nghiệp vụ vẫn giữ cùng user; chỉ snapshot DN thay đổi.

Membership có thể thay đổi, nhóm có thể lồng nhau và các implementation LDAP có thể dùng `member`, `uniqueMember` hoặc thuộc tính khác. Không áp đặt một schema nhóm cho mọi directory. Quan trọng hơn, **nhóm LDAP chưa tự động trở thành quyền ứng dụng**: tầng Spring Security và chính sách nghiệp vụ phải kiểm tra authority/role tương ứng, có chiến lược làm mới quyền và chống quyền cũ tồn tại quá lâu.

## 11. Bảo mật trong thiết kế đồng bộ danh tính

Đồng bộ định danh có tác động trực tiếp tới quyền và dữ liệu cá nhân, nên cần bảo vệ cả đường truyền lẫn quy tắc liên kết.

| Rủi ro | Biện pháp |
| --- | --- |
| Lộ mật khẩu tài khoản dịch vụ khi kết nối LDAP. | LDAPS hoặc StartTLS được cấu hình đúng; xác minh hostname/CA; giữ secret trong hệ thống quản lý bí mật. |
| Tài khoản đồng bộ có quyền rộng. | Tài khoản riêng với ACL đọc tối thiểu; cấp quyền ghi chỉ cho luồng quản trị thật sự cần CRUD. |
| Đầu vào người dùng sửa LDAP filter/DN. | Dùng `LdapQueryBuilder` và `LdapNameBuilder`; escape filter và DN theo quy tắc riêng. |
| Ghép nhầm hai tài khoản qua email/uid. | Ưu tiên stable external ID, quy trình linking có kiểm chứng và audit. |
| Job không hoàn chỉnh làm “xóa” hàng loạt. | Checkpoint, xác minh scan đầy đủ, trạng thái MISSING, grace period và cơ chế phục hồi. |
| Snapshot chứa PII bị truy cập quá mức. | Giảm số trường lưu, mã hóa theo chính sách hệ thống, giới hạn truy cập, retention phù hợp. |
| Retry tạo liên kết trùng hoặc mất cập nhật. | Unique constraint, transaction, upsert idempotent, kiểm soát phiên bản. |

Trong Spring Data LDAP, quyền đọc entry do **ACL của tài khoản đang bind** quyết định. Người dùng HTTP đã được Spring Security xác thực không có nghĩa thao tác `LdapTemplate`/repository tự động chạy bằng DN người đó. Tầng đồng bộ nên dùng quyền LDAP riêng, còn quyền xem/sửa tài khoản nội bộ phải được kiểm tra ở service/API.

## 12. Kiểm thử ánh xạ và quá trình đồng bộ

### 12.1. Xác minh stable ID trực tiếp trên directory thử nghiệm

Với server hỗ trợ `entryUUID`, có thể dùng `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=sync-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn entryUUID uid cn mail
~~~

`-W` nhập mật khẩu tương tác. Nếu `entryUUID` không xuất hiện, kiểm tra khả năng hỗ trợ của server, yêu cầu attribute tường minh, schema/ACL và cách diễn giải kết quả. Đừng sửa code để tự dùng `uid` khi chưa xác định nguyên nhân.

Trên một **directory thử nghiệm** được cấp quyền, thực hiện rename entry rồi đọc lại stable ID để xác nhận cùng một entry vẫn có mã tương ứng. Sau đó xóa và tạo một entry thử nghiệm mới trùng tên để xác nhận cơ chế liên kết không tự dùng nhầm link cũ. Không chạy các thao tác xóa/rename trên directory tổ chức nếu không có quy trình phù hợp.

### 12.2. Ma trận test nghiệp vụ

| Trường hợp | Kỳ vọng |
| --- | --- |
| Cùng `provider_key + external_id` được đồng bộ 10 lần. | Chỉ một link, giữ nguyên `app_user_id`; snapshot cập nhật hợp lệ. |
| Entry đổi `uid`, `mail`, DN; external ID giữ nguyên. | Không sinh user mới; cập nhật snapshot/DN. |
| Hai nguồn cùng chuỗi external ID. | Hai link khác nhau vì `provider_key` khác. |
| Entry mới dùng lại email/username của entry đã xóa. | Không tự tái sử dụng `app_user_id` cũ. |
| LDAP thiếu stable ID hoặc trả sai định dạng. | Báo lỗi có thể giám sát, không tạo link bằng DN fallback. |
| Hai worker cùng insert một external ID. | Unique constraint chặn trùng; rollback/retry an toàn. |
| Full scan thất bại ở trang cuối. | Không đánh dấu những entry chưa thấy là MISSING. |
| Search base thu hẹp hoặc ACL giảm quyền. | Job phát cảnh báo; không vô hiệu hóa hàng loạt dựa trên kết quả thiếu. |
| Entry không còn và được xác nhận bằng nguồn authoritative. | Thực hiện chính sách disable/retention, không xóa audit tùy tiện. |
| Event cũ đến sau event mới. | Không ghi đè snapshot mới bằng dữ liệu lỗi thời. |
| Directory thay đổi schema/nhóm quyền. | Cảnh báo ánh xạ, xác minh cách tính membership và authorization. |

Ngoài unit test mapper stable ID (định dạng UUID, binary GUID), cần **integration test với directory thử nghiệm** và database thật để kiểm tra transaction, unique constraint, paging, retry và hành vi rename. Tránh test chỉ so sánh chuỗi DN; hãy xác minh cả ID bất biến và các bảng nghiệp vụ còn tham chiếu đúng user.

### 12.3. Các chỉ số vận hành hữu ích

Theo dõi số entry đọc được, số link mới, số snapshot cập nhật, số identity thiếu stable ID, số candidate MISSING, lỗi ACL/TLS, tiến độ trang và độ trễ từ thời điểm LDAP thay đổi tới khi database phản ánh thay đổi. Một đợt tăng đột ngột số MISSING hoặc số link mới là dấu hiệu cần kiểm tra trước khi chạy thao tác vô hiệu hóa tự động.

Không log mật khẩu, secret hoặc toàn bộ dữ liệu cá nhân. Khi cần truy vết, log mã job, `provider_key`, kết quả xử lý và các ID được bảo vệ theo quy tắc logging của tổ chức.

## 13. Bài tập thực hành

Một hệ thống quản lý yêu cầu nội bộ dùng PostgreSQL cho `app_user` và `service_ticket`, đồng thời đồng bộ người dùng từ directory LDAP có `entryUUID`. Mã nguồn LDAP:

~~~text
provider_key:   headquarters-ldap
entryUUID:      7c4a5364-310d-4f8c-9442-d2b675e5a5d2
dn:             uid=mai,ou=staff,dc=company,dc=internal
uid:            mai
mail:           mai@company.internal
app_user.id:    617598c0-3a4c-4332-acf7-b09949ee47db
~~~

Một tháng sau, entry được chuyển thành `uid=mai.le,ou=managers,dc=company,dc=internal` và email đổi thành `mai.le@company.internal`. Sau đó hệ thống thử nghiệm xóa entry và tạo entry mới với DN cũ nhưng `entryUUID` khác.

**Yêu cầu:**

1. Thiết kế khóa cho bảng liên kết LDAP–database. Cột nào giữ vai trò định danh ổn định, cột nào là snapshot?
2. Khi entry đổi DN và email nhưng `entryUUID` không đổi, xử lý `app_user.id` và các `service_ticket.assignee_id` thế nào?
3. Khi xóa/tạo lại entry dùng DN cũ với `entryUUID` khác, có được tự liên kết với user cũ không? Vì sao?
4. Nếu job quét chỉ `ou=staff` mà user đã chuyển sang `ou=managers`, tại sao không được lập tức hard delete user?
5. Hai worker đồng bộ cùng một entry đồng thời. Những cơ chế nào tránh trùng link và trùng user?
6. Nếu directory thực tế là Active Directory, vì sao không thể dùng nguyên logic `UUID.fromString(getStringAttribute("entryUUID"))`?
7. Nêu ít nhất ba trường hợp cần kiểm thử trước khi dùng kết quả sync để vô hiệu hóa quyền đăng nhập.

**Gợi ý đáp án:**

- Dùng `(provider_key, external_id)` với unique constraint; `app_user.id` là ID nội bộ bất biến. DN, username và email là snapshot.
- Rename/move không đổi stable external ID thì giữ nguyên `app_user.id` và các khóa ngoại nghiệp vụ, chỉ cập nhật DN/thuộc tính.
- Entry bị tạo lại có ID mới phải trải qua provisioning/linking có kiểm chứng; không tái sử dụng user cũ do trùng DN/email.
- Phạm vi scan quá hẹp, ACL hoặc lỗi phân trang có thể làm “mất” entry giả. Chỉ đánh dấu ứng viên MISSING sau khi xác minh job bao phủ đúng phạm vi và hoàn tất.
- Dùng transaction, unique constraint, idempotent upsert và xử lý retry cạnh tranh; không tạo user mới vô điều kiện trước khi kiểm tra link.
- Active Directory dùng `objectGUID` dạng nhị phân với cách chuyển mã đặc thù; phải có adapter đọc/chuẩn hóa riêng.
- Test scan lỗi dở chừng, rename/move ra khỏi OU, thiếu quyền ACL, replication chậm, entry xóa/tạo lại và event đến sai thứ tự.

## 14. Ghi nhớ

**Không dùng DN, username hay email làm khóa bất biến để nối LDAP với dữ liệu nghiệp vụ.** Hãy dùng định danh entry ổn định mà directory hỗ trợ (như `entryUUID` hoặc `objectGUID`), đặt trong **namespace nguồn** rõ ràng rồi ánh xạ tới **ID nội bộ** của ứng dụng bằng một bảng có unique constraint.

Thuật toán đồng bộ cần nhận diện entry bằng stable ID trước khi cập nhật snapshot, có quy trình linking an toàn khi gặp ID mới, bảo vệ transaction khi chạy song song và chỉ kết luận entry biến mất sau khi đối soát đáng tin cậy. Kết nối LDAPS/StartTLS đúng, quyền đọc tối thiểu, filter an toàn, schema chính xác và kiểm thử với directory thực tế là những điều kiện nền tảng để Spring Data LDAP phục vụ đồng bộ danh tính mà không làm hỏng lịch sử hoặc quyền truy cập.

### Tài liệu tham khảo

- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Microsoft Active Directory Schema — objectGUID](https://learn.microsoft.com/en-us/windows/win32/adschema/a-objectguid)
