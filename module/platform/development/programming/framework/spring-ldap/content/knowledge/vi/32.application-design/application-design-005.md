# Thiết kế idempotent command cho bind và modify

## 1. Vì sao lệnh LDAP cần tính idempotent?

Một ứng dụng có thể gọi **Spring LDAP** để tạo tài khoản directory, đổi email, cập nhật thuộc tính hồ sơ hoặc thay thành viên của nhóm. Các lệnh này thường chạy qua mạng: request có thể đến LDAP server, server đã ghi thành công nhưng kết nối bị ngắt trước khi client nhận response. Khi ứng dụng thử lại, nó cần biết **lệnh đã được áp dụng hay chưa**.

**Idempotent** (lũy đẳng) nghĩa là thực hiện cùng một lệnh nhiều lần với cùng ý định sẽ đưa hệ thống tới **cùng trạng thái đích**, trong phạm vi và các điều kiện đã quy định. Tính lũy đẳng **không mặc nhiên bảo đảm** không có thêm log, audit event, thông báo hay tác dụng phụ bên ngoài.

Ví dụ: “đặt email của tài khoản A thành **lan@example.org**” có thể lũy đẳng ở mức trạng thái của attribute **mail**. “Mỗi lần gọi thêm một quyền mới” hoặc “gửi email chào mừng khi tạo tài khoản” có thể tạo tác dụng phụ lặp lại nếu không có thiết kế riêng.

Trong chương **Thiết kế ứng dụng**, mục tiêu là thiết kế **command** mang ý nghĩa nghiệp vụ, đặt giao tiếp LDAP trong adapter Spring LDAP, phân biệt trường hợp *đã áp dụng*, *chưa áp dụng*, *xung đột* và *chưa biết kết quả*. Phạm vi gồm **DN**, schema, filter, thao tác entry bằng **LdapTemplate/LdapClient/ODM**, cấu hình **ContextSource**, xác thực, TLS, pooling, xử lý lỗi và kiểm thử an toàn.

### Một tình huống thực tế

Hệ thống quản lý nhân viên nhận một sự kiện tạo nhân viên từ HR:

1. Consumer gọi LDAP để tạo entry **uid=lan,ou=people,dc=example,dc=org**.
2. Server đã tạo entry nhưng response bị mất do timeout.
3. Consumer nhận lại cùng sự kiện hoặc tự retry.
4. Gọi tạo entry lần nữa dẫn đến lỗi **entry already exists**.

Lỗi *already exists* không đủ để kết luận thành công: một entry khác có thể đã chiếm cùng DN nhưng mang thuộc tính khác. Command phải **đọc lại và đối chiếu dữ liệu** trước khi trả “đã áp dụng”.

## 2. Trước hết: “bind” trong LDAP có hai nghĩa khác nhau

Tên **bind** xuất hiện ở hai API với mục đích khác nhau; nhầm lẫn sẽ dẫn tới thiết kế retry sai.

| Cách dùng | Ý nghĩa | Có sửa directory không? | Vấn đề idempotency |
| --- | --- | --- | --- |
| **LDAP BindRequest** trong giao thức | Xác thực và thiết lập trạng thái xác thực của kết nối LDAP | Thông thường không trực tiếp tạo/sửa entry | Không xem việc lặp lại là “không tác dụng phụ”: có thể tăng bộ đếm đăng nhập sai, trigger policy khóa tài khoản hoặc ghi audit |
| **LdapTemplate.bind(Name, Object, Attributes)** | API Spring LDAP/JNDI để **tạo hoặc bind một entry** dưới DN | Có, thêm entry | Retry có thể gặp **NameAlreadyBoundException**; phải đối chiếu entry |
| **LdapTemplate.authenticate(...)** hoặc Spring Security LDAP | Xác thực thông tin người dùng qua LDAP | Không phải thao tác tạo entry | Phân biệt mật khẩu sai với lỗi kết nối; không retry vô hạn |

**Bài này chủ yếu thiết kế lệnh tạo entry bằng LdapTemplate.bind và sửa entry bằng LdapTemplate.modifyAttributes.** Với *authentication bind*, nội dung bảo mật và xử lý retry được tách riêng ở phần sau. Đừng dùng cùng một command **CreateAccount** cho cả hai ý nghĩa.

## 3. Chọn mức bảo đảm có thể thực hiện

Cần nói rõ khi nào một command được xem là đã hoàn thành:

| Mức bảo đảm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **State idempotency** | Gọi lặp cùng dữ liệu tạo ra cùng trạng thái đích | Đặt **mail** bằng một giá trị cố định |
| **Effect idempotency** | Không lặp tác dụng phụ ngoài trạng thái đích | Cùng command ID không gửi hai thông báo |
| **Business idempotency** | Không tạo hai đối tượng nghiệp vụ cho một yêu cầu | Cùng sự kiện HR chỉ sinh một tài khoản directory |
| **Concurrency safety** | Hai request đồng thời không phá điều kiện nghiệp vụ | Không ghi đè email mới bằng một retry cũ |

**LDAP không tự cung cấp một cơ chế idempotency key chung** cho mọi lệnh. API **bind** và **modifyAttributes** không nhận trực tiếp một khóa nghiệp vụ có khả năng loại bỏ toàn bộ request trùng. Có thể kết hợp một hoặc nhiều cơ chế:

- **Tên hoặc định danh đích ổn định**, ví dụ một DN/RDN định trước cho lệnh tạo.
- **Đọc và so sánh trạng thái hiện tại** trước khi tạo, sửa và đặc biệt khi kết quả trả về không chắc chắn.
- **Thao tác có tính lũy đẳng tự nhiên** như **REPLACE_ATTRIBUTE** cùng một giá trị.
- **Ràng buộc hoặc control của LDAP server** cho thao tác điều kiện nếu cần chống ghi đè đồng thời.
- **Command ID + command ledger** trong database ứng dụng cho deduplication, audit và side effect.

Không nhầm các cơ chế này với một transaction phân tán: transaction JPA không tự bao phủ LDAP, và một bản ghi “đã gửi command” trong SQL không tự chứng minh server LDAP đã áp dụng command đó.

## 4. Sơ đồ ranh giới và luồng command

~~~mermaid
flowchart TB
    CLIENT["HR event / REST request"]
    USE["Application command handler"]
    LEDGER["Command ledger (nếu cần)"]
    PORT["DirectoryCommandPort"]
    ADAPTER["Spring LDAP command adapter"]
    READER["Đọc lại và so trạng thái"]
    TEMPLATE["LdapTemplate / LdapClient"]
    CS["ContextSource + TLS + bind account"]
    DIR[("LDAP directory")]

    CLIENT --> USE
    USE --> LEDGER
    USE --> PORT
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> TEMPLATE
    ADAPTER --> READER
    READER --> TEMPLATE
    TEMPLATE --> CS --> DIR
~~~

**Application handler** quyết định command có hợp lệ về nghiệp vụ không và có cần gửi notification/event sau khi thành công. **DirectoryCommandPort** chỉ công bố thao tác như **ensurePersonExists** và **replaceEmail**. **LDAP adapter** tạo DN/filter, đọc attribute, gọi **bind/modify**, phân loại lỗi và xác minh kết quả. Nếu cần command ledger, ledger thuộc tầng điều phối ứng dụng; không để LDAP mapper tự ghi SQL.

Một command có thể có các kết quả:

| Kết quả | Định nghĩa |
| --- | --- |
| **APPLIED** | Request hiện tại đã ghi thành công theo điều kiện đã kiểm tra |
| **ALREADY_APPLIED** | Dữ liệu hiện có phù hợp với trạng thái đích được yêu cầu |
| **CONFLICT** | Entry hiện tại khác trạng thái kỳ vọng hoặc điều kiện cập nhật không còn đúng |
| **UNKNOWN_OUTCOME** | Không đủ bằng chứng xác định lệnh đã ghi hay chưa sau sự cố mạng |
| **FAILED** | Lỗi xác định, ví dụ schema/ACL hoặc input không hợp lệ |

**APPLIED** và **ALREADY_APPLIED** thường đều có thể xem là thành công về *trạng thái đích*. Tuy nhiên application vẫn phải quyết định có phát sự kiện hay không; không tự động phát hai lần chỉ vì callback nhận hai kết quả thành công.

## 5. Thiết kế command và port độc lập với LDAP

Ví dụ sử dụng Java 17 và Spring LDAP. Các lớp/record **public** được đặt trong file Java riêng; tên package chỉ để minh họa.

~~~java
// application/DirectoryWriteOutcome.java
package com.example.directory.application;

public enum DirectoryWriteOutcome {
    APPLIED,
    ALREADY_APPLIED
}
~~~

~~~java
// application/CreatePersonCommand.java
package com.example.directory.application;

import java.util.UUID;

public record CreatePersonCommand(
        UUID commandId,
        String login,
        String surname,
        String displayName,
        String email
) {}
~~~

~~~java
// application/ReplaceEmailCommand.java
package com.example.directory.application;

import java.util.UUID;

public record ReplaceEmailCommand(
        UUID commandId,
        String login,
        String newEmail
) {}
~~~

~~~java
// application/DirectoryCommandPort.java
package com.example.directory.application;

public interface DirectoryCommandPort {
    DirectoryWriteOutcome ensurePersonExists(CreatePersonCommand command);
    DirectoryWriteOutcome replaceEmail(ReplaceEmailCommand command);
}
~~~

Hợp đồng này không chứa **javax.naming.Name**, **Attributes**, **DirContext**, **LdapTemplate** hoặc Spring LDAP exception. **commandId** gắn với **ý định nghiệp vụ** và phải giữ nguyên khi cùng yêu cầu được gửi lại. Một command ID mới chỉ dùng cho một yêu cầu nghiệp vụ mới.

Trong ví dụ, tên đăng nhập được dùng làm RDN để dễ hiểu. Sản phẩm cần định nghĩa rõ login có được đổi/tái sử dụng không. Với hệ thống có rename hoặc move OU, các command sửa thường nên nhắm tới **DirectorySubject(sourceId, stableEntryId)**; adapter tra DN hiện tại bằng **entryUUID** (OpenLDAP) hoặc **objectGUID** (Active Directory). **DN không phải khóa nghiệp vụ bất biến.**

Lựa chọn giá trị email là dữ liệu đầu vào; application/domain cần kiểm tra quy tắc quyền sửa, cú pháp và business policy. Adapter vẫn cần kiểm tra điều kiện tối thiểu trước khi gọi server.

## 6. Thiết kế ensurePersonExists bằng LdapTemplate.bind

Một lệnh tạo entry có thể được thiết kế kiểu **create-if-absent với xác minh trạng thái**:

1. Từ **login**, adapter tạo DN an toàn bằng **LdapNameBuilder**, theo search base được cấu hình.
2. Tra cứu entry đích. Nếu tồn tại và các thuộc tính **do command sở hữu** khớp, trả **ALREADY_APPLIED**.
3. Nếu tồn tại nhưng dữ liệu xung đột, báo **CONFLICT**, không ghi đè.
4. Nếu chưa tồn tại, gọi **LdapTemplate.bind** để tạo entry.
5. Nếu hai tiến trình cùng tạo, một tiến trình có thể nhận lỗi **NameAlreadyBoundException**. Tiến trình đó phải **đọc lại và so khớp**, không coi mọi trường hợp trùng DN là thành công.

Định nghĩa một lỗi ứng dụng, thay vì để người gọi bắt Spring LDAP exception:

~~~java
// application/DirectoryCommandConflict.java
package com.example.directory.application;

public final class DirectoryCommandConflict extends RuntimeException {
    public DirectoryCommandConflict(String message) {
        super(message);
    }
}
~~~

Adapter mẫu dưới đây tập trung vào **bind tạo entry**; những lỗi kết nối, xác thực và quyền cần được dịch sang exception ứng dụng ở cùng ranh giới.

~~~java
// infrastructure/ldap/SpringLdapCreatePerson.java
package com.example.directory.infrastructure.ldap;

import com.example.directory.application.CreatePersonCommand;
import com.example.directory.application.DirectoryCommandConflict;
import com.example.directory.application.DirectoryWriteOutcome;
import java.util.Objects;
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

final class SpringLdapCreatePerson {

    private final LdapTemplate ldap;

    SpringLdapCreatePerson(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    DirectoryWriteOutcome execute(CreatePersonCommand cmd) {
        validate(cmd);
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", cmd.login())
                .build();

        Optional<PersonState> current = lookup(relativeDn);
        if (current.isPresent()) {
            return classifyExisting(current.get(), cmd);
        }

        try {
            ldap.bind(relativeDn, null, attributesFor(cmd));
            return DirectoryWriteOutcome.APPLIED;
        } catch (NameAlreadyBoundException concurrentCreate) {
            // Một request khác đã tạo cùng DN: xác minh trước khi xác nhận.
            return lookup(relativeDn)
                    .map(state -> classifyExisting(state, cmd))
                    .orElseThrow(() -> new DirectoryCommandConflict(
                            "Không xác minh được entry sau xung đột tạo"));
        }
    }

    private Optional<PersonState> lookup(Name dn) {
        try {
            return Optional.of(ldap.lookup(dn,
                    (ContextMapper<PersonState>) ctx -> {
                        DirContextOperations entry =
                                (DirContextOperations) ctx;
                        return new PersonState(
                                entry.getStringAttribute("uid"),
                                entry.getStringAttribute("sn"),
                                entry.getStringAttribute("cn"),
                                entry.getStringAttribute("mail"));
                    }));
        } catch (NameNotFoundException missingDn) {
            // Chỉ xem là vắng entry tại DN đích khi OU/base đã được
            // kiểm tra tồn tại bằng cấu hình và integration test.
            return Optional.empty();
        }
    }

    private DirectoryWriteOutcome classifyExisting(
            PersonState state, CreatePersonCommand cmd) {
        boolean same = Objects.equals(state.login(), cmd.login())
                && Objects.equals(state.surname(), cmd.surname())
                && Objects.equals(state.displayName(), cmd.displayName())
                && Objects.equals(state.email(), cmd.email());
        if (!same) {
            throw new DirectoryCommandConflict(
                    "DN đã tồn tại với dữ liệu khác command");
        }
        return DirectoryWriteOutcome.ALREADY_APPLIED;
    }

    private Attributes attributesFor(CreatePersonCommand cmd) {
        Attributes attrs = new BasicAttributes(true);
        Attribute types = new BasicAttribute("objectClass");
        types.add("top");
        types.add("person");
        types.add("organizationalPerson");
        types.add("inetOrgPerson");
        attrs.put(types);
        attrs.put("uid", cmd.login());
        attrs.put("sn", cmd.surname());
        attrs.put("cn", cmd.displayName());
        attrs.put("mail", cmd.email());
        return attrs;
    }

    private void validate(CreatePersonCommand cmd) {
        Objects.requireNonNull(cmd);
        Objects.requireNonNull(cmd.commandId());
        if (isBlank(cmd.login()) || isBlank(cmd.surname())
                || isBlank(cmd.displayName()) || isBlank(cmd.email())) {
            throw new IllegalArgumentException(
                    "Thiếu trường bắt buộc của directory person");
        }
    }

    private boolean isBlank(String s) {
        return s == null || s.isBlank();
    }

    private record PersonState(
            String login, String surname,
            String displayName, String email) {}
}
~~~

Giả định của đoạn mã:

- **ContextSource** đặt base DN là **dc=example,dc=org**; **relativeDn** dùng trong LdapTemplate không lặp lại base.
- Directory hỗ trợ schema **inetOrgPerson** với những attribute này; **sn** và **cn** là bắt buộc theo lớp objectClass tương ứng.
- **ou=people** được quản lý ngoài command; trước khi vận hành cần xác nhận nhánh này tồn tại. Lỗi **NameNotFoundException** do OU bị xóa không được im lặng coi là một yêu cầu tạo entry mới.
- **Email, tên hiển thị, họ** là những giá trị command được quyền ghi khi tạo. Nếu tổ chức có canonicalization khác nhau, phải thống nhất quy tắc so sánh; đoạn mã minh họa so sánh chính xác từng chuỗi.
- Đây là **một phần adapter**, chưa có wrapper translate lỗi đầy đủ. Lỗi ACL/schema/timeout phải đi qua error boundary trung lập; không đưa Spring LDAP exception ra application.

**Đọc trước rồi bind không phải một thao tác nguyên tử.** Ràng buộc trùng DN tại server và việc bắt **NameAlreadyBoundException** giúp xử lý race của hai lệnh tạo, nhưng không giải quyết trường hợp hai danh tính có cùng login ở hai DN khác nhau hoặc DN bị đổi ngay sau khi kiểm tra. Nếu cần tính duy nhất theo một thuộc tính trên toàn cây, phải thiết kế quy tắc và cơ chế server phù hợp, không chỉ dựa vào preflight query.

## 7. Thiết kế modify idempotent bằng REPLACE_ATTRIBUTE

Với thao tác cập nhật, việc **đặt thuộc tính bằng một giá trị cụ thể** thường dễ đạt state idempotency hơn lệnh “thêm giá trị” hoặc “tăng số lần”.

Ví dụ: lệnh đặt email cho một entry với cùng DN hiện tại:

~~~java
// infrastructure/ldap/SpringLdapReplaceEmail.java
package com.example.directory.infrastructure.ldap;

import com.example.directory.application.DirectoryWriteOutcome;
import java.util.Objects;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

final class SpringLdapReplaceEmail {
    private final LdapTemplate ldap;

    SpringLdapReplaceEmail(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    DirectoryWriteOutcome execute(Name relativeDn, String newEmail) {
        Objects.requireNonNull(relativeDn);
        if (newEmail == null || newEmail.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }

        String currentEmail = readEmail(relativeDn);
        if (Objects.equals(currentEmail, newEmail)) {
            return DirectoryWriteOutcome.ALREADY_APPLIED;
        }

        ModificationItem[] modifications = {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("mail", newEmail))
        };
        ldap.modifyAttributes(relativeDn, modifications);
        return DirectoryWriteOutcome.APPLIED;
    }

    private String readEmail(Name relativeDn) {
        return ldap.lookup(relativeDn,
                (ContextMapper<String>) ctx ->
                    ((DirContextOperations) ctx)
                            .getStringAttribute("mail"));
    }
}
~~~

Đoạn mã minh họa lệnh **set-to-value**. Trong một triển khai đầy đủ, **relativeDn** phải được adapter giải quyết từ **định danh bền vững** (ví dụ **entryUUID**) hoặc một nguồn kiểm soát đủ tin cậy, thay vì cho client tự truyền DN. Cần hạn chế quyền ghi, kiểm tra email theo nghiệp vụ và chuyển exception kỹ thuật thành lỗi ứng dụng.

**REPLACE_ATTRIBUTE** với cùng giá trị thường lũy đẳng về *giá trị cuối cùng của attribute*. Nó không đồng nghĩa không phát sinh **modifyTimestamp**, audit log, sự kiện đồng bộ hay thay đổi ngầm khác mỗi lần server xử lý lệnh. Nếu ứng dụng phải bảo đảm hiệu ứng chính xác một lần, cần cơ chế riêng.

### Chọn đúng loại modification

| Lệnh | Tính lũy đẳng khi lặp cùng request | Cách xử lý |
| --- | --- | --- |
| **REPLACE_ATTRIBUTE mail=X** | Thường lũy đẳng theo giá trị cuối của **mail** | Đọc và bỏ qua khi đã bằng X |
| **ADD_ATTRIBUTE member=DN** | Phụ thuộc schema/server; có thể lỗi “đã tồn tại” hoặc trùng hiệu ứng | Dùng **ensureMembership** và kiểm tra membership hiện tại |
| **REMOVE_ATTRIBUTE member=DN** | Nếu phần tử đã vắng, có thể lỗi | Dùng **ensureAbsent** và xác minh trạng thái |
| **ADD_ATTRIBUTE** vào attribute đa trị | Không được giả định idempotent với mọi server | So sánh dạng tập giá trị và kiểm soát cập nhật đồng thời |
| **REMOVE_ATTRIBUTE** cả attribute | Khi đã không còn attribute, server có thể báo lỗi | Định nghĩa xóa nếu tồn tại như một command riêng |
| **modify DN/rename** | Tên đích có thể đã tồn tại, tên nguồn biến mất sau lần đầu | Đọc bằng ID bền vững, đối chiếu DN hiện tại và xử lý race |

**Đừng chuyển mọi command thành một mảng ModificationItem rồi tự động retry mù.** Quy tắc kiểm tra trước, kiểm tra sau và định nghĩa trạng thái đích thuộc từng command cụ thể.

## 8. Trạng thái “chưa biết kết quả” sau timeout

Khi client nhận lỗi giao tiếp từ LDAP, có ít nhất ba khả năng:

1. Request chưa đến server, **không có thay đổi**.
2. Request đến server, server **đã ghi**, nhưng response bị mất.
3. Server xử lý một phần luồng hệ thống khác trước khi lỗi; đối với **một LDAP modify trên một entry**, server áp dụng tập thay đổi theo tính nguyên tử của thao tác đó, nhưng hiệu ứng của hệ thống khác vẫn có thể riêng biệt.

Không thể suy ra một request đã thất bại chỉ từ **CommunicationException**. Với command có thể xác minh từ trạng thái cuối, thử **đọc lại entry** sau lỗi:

~~~mermaid
flowchart TB
    START["Gửi command LDAP"]
    OK{"Có response thành công?"}
    READ["Đọc lại trạng thái bằng định danh ổn định"]
    SAME{"Trạng thái đã bằng đích?"}
    DIFF{"Có xung đột với dữ liệu mới hơn?"}
    DONE["APPLIED / ALREADY_APPLIED"]
    CONFLICT["CONFLICT"]
    UNKNOWN["UNKNOWN_OUTCOME: cần đối soát"]

    START --> OK
    OK -- "Có" --> DONE
    OK -- "Timeout / mất phản hồi" --> READ
    READ --> SAME
    SAME -- "Có" --> DONE
    SAME -- "Không" --> DIFF
    DIFF -- "Có" --> CONFLICT
    DIFF -- "Không rõ / không đọc được" --> UNKNOWN
~~~

**Cần tránh kết luận quá mức:** khi đọc lại thấy giá trị đích, ta biết **trạng thái hiện tại phù hợp** với command, nhưng không nhất thiết chứng minh chính request đó là request đã ghi. Một tác nhân khác có thể đã ghi cùng giá trị. Nếu cần audit theo command ID, phải lưu bằng chứng và xử lý sự trùng lặp ở tầng ứng dụng.

Đọc lại cũng có thể trả dữ liệu cũ vì replication hoặc replica lag. Hãy xác định endpoint đọc có đủ mức nhất quán cho xác minh không; nếu cần, đọc từ writable server/nguồn nhất quán phù hợp và có timeout/giới hạn retry. Khi không xác minh được, **UNKNOWN_OUTCOME** là trạng thái hợp lệ cần đối soát, không phải lý do gửi lại lệnh ghi vô hạn.

## 9. Idempotency key và command ledger

Nếu command ngoài LDAP còn kích hoạt email, audit, sự kiện tích hợp hoặc ghi database, **state idempotency ở LDAP là chưa đủ**. Ứng dụng cần dùng **commandId** để nhận diện việc lặp lại một **ý định nghiệp vụ**.

Một bảng ledger minh họa:

| Cột | Ý nghĩa |
| --- | --- |
| **source_id** | Phân biệt các directory hoặc tenant |
| **command_id** | UUID ổn định cho cùng yêu cầu; unique cùng source |
| **command_type** | CREATE_PERSON / REPLACE_EMAIL / ENSURE_GROUP_MEMBER |
| **payload_hash** | Hash của payload đã canonicalize; chống dùng cùng ID cho payload khác |
| **status** | PENDING / APPLIED / UNKNOWN / REJECTED |
| **attempt_count** | Số lần thực thi để giám sát |
| **updated_at** | Thời điểm cập nhật trạng thái |
| **result_reference** | ID nghiệp vụ/định danh entry nếu cần |

Luồng gợi ý:

~~~mermaid
sequenceDiagram
    actor Caller
    participant Handler as Application handler
    participant Ledger as SQL command ledger
    participant Adapter as Spring LDAP adapter
    participant Dir as LDAP directory

    Caller->>Handler: commandId + payload
    Handler->>Ledger: reserve(commandId, payloadHash)
    alt Trùng ID, khác payload
      Ledger-->>Handler: CONFLICT
      Handler-->>Caller: 409 / lỗi command
    else Lệnh đã hoàn tất
      Ledger-->>Handler: APPLIED
      Handler-->>Caller: Kết quả cũ
    else PENDING hoặc mới
      Handler->>Adapter: ensure / replace
      Adapter->>Dir: bind hoặc modify
      Dir-->>Adapter: response hoặc timeout
      Adapter-->>Handler: APPLIED / ALREADY_APPLIED / UNKNOWN
      Handler->>Ledger: ghi kết quả hoặc cần đối soát
      Handler-->>Caller: kết quả được phân loại
    end
~~~

**Đừng giữ transaction SQL mở trong lúc chờ LDAP** nếu có thể tránh. Có thể reserve command bằng một transaction ngắn, thực hiện LDAP, rồi ghi kết quả bằng transaction khác. Nhưng cần chấp nhận và xử lý khoảng trống: nếu ứng dụng crash sau khi LDAP ghi thành công nhưng trước khi ledger cập nhật, ledger vẫn **PENDING**. Worker đối soát phải đọc trạng thái directory và quyết định tiếp.

Nếu nhiều node cùng nhận một **commandId**, cần cơ chế claim/lease hoặc optimistic locking trong ledger để giảm thực thi song song. Dù vậy, lease hết hạn và request LDAP chậm vẫn có thể tạo hai execution chồng nhau; **thao tác LDAP tự thân vẫn phải chịu được retry**. Đây là lý do kết hợp ledger với state comparison.

Canonicalization của **payload_hash** phải ổn định và nhất quán: thứ tự các thuộc tính đa trị có thể không có ý nghĩa, Unicode/case có thể có matching rule riêng, và password/secret không được đưa vào log. Không lưu plaintext credential trong ledger. Chỉ có command ID trùng không đủ; **cùng ID với payload khác là lỗi**, không được âm thầm trả thành công.

## 10. Cập nhật đồng thời: idempotent không có nghĩa chống mất dữ liệu

Xét hai sự kiện thay email:

1. Command A đặt **mail=old@example.org**.
2. Command B mới hơn đặt **mail=new@example.org**.
3. Do timeout hoặc queue trễ, command A bị retry sau B.

Nếu A dùng **REPLACE_ATTRIBUTE** mù, giá trị cuối trở về email cũ. A vẫn có thể lũy đẳng với chính nó, nhưng **ghi đè thay đổi mới hơn**.

Giải pháp tùy yêu cầu:

- **Expected state / version:** command có thể chứa **expectedEmail** hoặc version, adapter từ chối nếu dữ liệu đã thay đổi. Tuy nhiên **đọc trước rồi sửa không nguyên tử**, nên chỉ kiểm tra ở client không đủ bảo đảm khi có cập nhật đồng thời.
- **LDAP assertion control (RFC 4528)** nếu server và API hỗ trợ: yêu cầu điều kiện đúng ngay lúc server thực hiện modify; cần kiểm thử hỗ trợ thực tế và error code khi assertion fail.
- **Serialized commands theo subject**: application xếp các lệnh cập nhật cùng entry qua một đường xử lý tuần tự, nhưng vẫn phải giải quyết tác nhân bên ngoài có thể sửa LDAP.
- **Quy tắc nguồn dữ liệu và thứ tự sự kiện:** bỏ sự kiện cũ theo version nguồn đáng tin cậy; không tự giả định **modifyTimestamp** tạo cơ chế compare-and-swap nguyên tử.
- **Đọc lại sau ghi và đối soát** khi mất phản hồi; nếu thấy trạng thái khác, không tiếp tục retry mà không đánh giá thứ tự.

Nếu command chứa **expectedEmail**, phép kiểm tra trước khi ghi chỉ là *optimistic check ở client* trừ khi được gắn với điều kiện **server-side**. Với dữ liệu nhạy cảm hoặc cạnh tranh cao, phải xác định rõ nơi nào bảo đảm nguyên tử.

## 11. Định danh, DN, filter và schema khi thiết kế command

LDAP entry được xác định theo DN, ví dụ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

DN có thể đổi khi rename hoặc move OU; login cũng có thể đổi hoặc tái sử dụng. Vì thế command nghiệp vụ dài hạn nên dùng **directory source + stable entry ID**, trong khi LDAP adapter tìm **DN hiện tại**.

| Vấn đề | Quy tắc |
| --- | --- |
| Tạo DN từ login | Dùng **LdapNameBuilder**, không nối chuỗi từ dữ liệu người dùng |
| Tìm entry từ stable ID | Dùng **LdapQueryBuilder** với filter được escape, giới hạn search base |
| Đổi DN / OU | Đánh giá operation rename/modDN riêng, không coi như REPLACE_ATTRIBUTE |
| Thuộc tính nhiều giá trị | So sánh tập/định danh theo schema, không phụ thuộc thứ tự |
| Attribute nhị phân | Mapping **byte[]** rõ ràng; AD **objectGUID** không thể dùng cách đọc chuỗi của OpenLDAP **entryUUID** |
| Attribute tùy chọn | Phân biệt thiếu giá trị, đặt giá trị mới và xóa |
| Thuộc tính do server quản lý | Không tự ghi **entryUUID**, **modifyTimestamp** hoặc operational attribute chỉ đọc |

Ví dụ dựng DN và query đúng lớp hạ tầng:

~~~java
import javax.naming.Name;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", userProvidedLogin)
        .build();

LdapQuery lookup = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(userProvidedLogin);
~~~

**DN escaping** và **LDAP filter escaping** là hai ngữ pháp khác nhau. Không dùng **split(",")** để parse DN hoặc **String.format("(uid=%s)", input)** để dựng filter. Base DN của **ContextSource** và search base tương đối phải thống nhất để tránh truy vấn sai nhánh.

## 12. Lỗi, retry và phân loại kết quả

Command handler cần tách lỗi xác định và lỗi có thể **unknown outcome**:

| Trường hợp | Cách hiểu | Phản ứng |
| --- | --- | --- |
| **bind** thành công | Entry mới được tạo | **APPLIED**, xử lý side effect qua ledger/outbox nếu có |
| **NameAlreadyBoundException** | DN đã tồn tại, chưa biết nội dung | Đọc lại; **ALREADY_APPLIED** nếu khớp, **CONFLICT** nếu khác |
| **modify** thành công | Server xác nhận thao tác | **APPLIED** |
| Gửi **REPLACE** khi giá trị đã bằng đích | Không cần ghi | **ALREADY_APPLIED** |
| **CommunicationException** hoặc timeout khi ghi | Có thể chưa ghi hoặc đã ghi | **UNKNOWN_OUTCOME** cho đến khi đọc lại và xác minh |
| Schema violation hoặc DN sai | Yêu cầu không hợp lệ với directory | **FAILED**, sửa dữ liệu/schema |
| Account kỹ thuật bind sai / thiếu ACL | Lỗi tích hợp | **FAILED** hoặc chờ vận hành sửa cấu hình; không retry dồn dập |
| Assertion condition không còn đúng | Giá trị đã đổi bởi command khác | **CONFLICT**, không ghi đè |
| Directory không thể đọc lại sau outage | Chưa đủ bằng chứng | Giữ **UNKNOWN_OUTCOME**, đưa vào hàng đối soát |

Các exception **javax.naming.NamingException** hoặc **org.springframework.ldap.NamingException** chỉ được xử lý trong adapter/mapper và chuyển thành lỗi trung lập của ứng dụng, chẳng hạn **DirectoryUnavailable**, **DirectoryConflict**, **DirectoryInvalidData**. **Không để exception LDAP thô đi qua port hoặc trả trực tiếp vào REST API.**

Retry cần có **giới hạn số lần**, **timeout**, **exponential backoff + jitter** và quan sát được. Không áp dụng cùng chính sách cho mọi thao tác. Lỗi schema/permission không tự biến mất khi retry. Khi kết quả ghi không xác định, ưu tiên **đối soát trạng thái**; tránh retry mù những operation có hiệu ứng không lũy đẳng.

## 13. Riêng authentication BindRequest: không retry như lệnh tạo entry

**LDAP authentication bind** thường được dùng để xác minh credential người dùng, qua **ContextSource.getContext(...)**, **LdapTemplate.authenticate(...)** hoặc tích hợp **Spring Security LDAP**.

Ở mức kiểm tra credential, việc gọi lại có thể trả cùng kết quả **đúng/sai** khi trạng thái server không đổi. Nhưng server có thể ghi **audit**, áp dụng **rate limit**, tăng **failed-login counter** hoặc **khóa tài khoản**. Vì vậy **authentication bind không được coi là idempotent về tác dụng phụ**.

Đặc biệt:

1. Không đưa password vào **command ledger**, payload hash dùng chung, message queue hay log.
2. Không tự động retry liên tục khi bind thất bại do credential sai; có thể kích hoạt policy khóa account.
3. Phân biệt **invalid credentials** và **directory unavailable** ở tầng nội bộ. Response công khai phải tránh tiết lộ user có tồn tại hay không.
4. Nếu xác thực qua connection pooling, đảm bảo trạng thái bind không bị dùng nhầm giữa các principal. Chỉ dùng pool tương thích với TLS/StartTLS và cơ chế xác thực.
5. Với vấn đề thiết lập phiên hoặc cấp token, idempotency của việc **phát token/tạo session** thuộc hệ thống ứng dụng, không phải bản thân LDAP BindRequest.

Không áp dụng **ensurePersonExists** cho xác thực. Đó là hai quy trình có tác động và yêu cầu bảo mật khác nhau dù cùng xuất hiện từ “bind”.

## 14. TLS, ContextSource và bảo vệ truy cập

Tầng hạ tầng quản lý kết nối thông qua **ContextSource**, thay vì để application service tự mở **DirContext**:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các cấu hình quan trọng đối với command:

- **LDAPS** hoặc **StartTLS** phải xác minh certificate, hostname và trust chain; không tắt kiểm tra TLS để vượt qua lỗi cấu hình.
- Service account dùng cho tạo/sửa entry phải có **quyền ghi tối thiểu**, giới hạn OU và attribute được phép sửa. Có thể tách account chỉ đọc và account ghi.
- **Connection/read timeout**, giới hạn pool, max search size, referral và search scope cần được định nghĩa rõ. Tránh giữ lock/transaction SQL trong lúc đợi request mạng LDAP.
- Với **StartTLS**, connection pooling phải phù hợp lifecycle TLS. Với authentication bind của người dùng, không trộn connection mang trạng thái xác thực khác nhau.
- Command/audit log chỉ lưu **commandId**, loại thao tác, source ID, kết quả và correlation ID cần thiết. Không log password, giá trị nhạy cảm, DN chi tiết hoặc raw filter một cách tùy tiện.

**Pooling không làm command idempotent.** Ngược lại, pool hỏng hoặc kết nối đã chết có thể tạo thêm timeout, khiến yêu cầu đối soát thường xuyên hơn. Tách quan sát lỗi kết nối khỏi lỗi schema và xung đột nghiệp vụ.

## 15. Thiết kế kiểm thử đáng tin cậy

### 15.1. Unit test ở application

Use case nên chỉ phụ thuộc **DirectoryCommandPort**. Một fake port có thể ghi số lần nhận command và trả **APPLIED/ALREADY_APPLIED**; ledger fake lưu **commandId** và **payloadHash**. Test cần xác nhận:

- Cùng **commandId + payload** được gửi lại thì side effect nghiệp vụ (ví dụ phát notification) chỉ được yêu cầu một lần theo chính sách.
- Cùng **commandId** nhưng payload khác bị từ chối.
- **UNKNOWN_OUTCOME** không bị tự động xem là thành công hoặc thất bại đã xác định.
- **CONFLICT** không được retry như lỗi mạng.
- Application không import **javax.naming** hoặc **org.springframework.ldap**.

### 15.2. Integration test LDAP cho bind tạo entry

Tạo một test directory với schema và OU đã biết:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Entry chưa tồn tại, gọi **ensurePersonExists** | Tạo đúng một entry với **objectClass**, **uid**, **sn**, **cn**, **mail** |
| Gọi lại đúng command/dữ liệu | **ALREADY_APPLIED**, không tạo thêm entry |
| DN trùng nhưng **mail** hoặc **uid** khác | **CONFLICT**, không âm thầm overwrite |
| Hai request cùng tạo một DN đồng thời | Không tạo trùng; request thua kiểm tra lại trước khi trả kết quả |
| OU/base DN không tồn tại | Lỗi cấu hình rõ ràng, không bị hiểu thành người dùng chưa tồn tại |
| Login chứa dấu phẩy, dấu bằng hoặc ký tự đặc biệt | **LdapNameBuilder** tạo DN đúng, không vượt scope |
| Service account không đủ ACL hoặc schema sai | Lỗi được phân loại, không retry vô hạn |
| Server ngắt phản hồi sau khi tạo | Đối soát entry và xác định trạng thái hoặc giữ **UNKNOWN_OUTCOME** |

### 15.3. Integration test LDAP cho modify

Kiểm tra các tình huống:

1. **REPLACE_ATTRIBUTE mail=X** một lần trả thành công, lần sau nhận **ALREADY_APPLIED** nếu không có thay đổi khác.
2. **ADD_ATTRIBUTE** và **REMOVE_ATTRIBUTE** vào group được thiết kế theo dạng **ensure present / ensure absent**, không lệ thuộc thành công của phép thêm/xóa lặp.
3. Entry đã bị rename/move OU không dẫn tới sửa nhầm một entry mới tái sử dụng DN cũ.
4. Lệnh A cũ retry sau lệnh B mới không được ghi đè dữ liệu ngoài ý muốn khi hệ thống yêu cầu concurrency control.
5. Lỗi timeout sau khi server đã ghi được phân biệt với timeout trước khi server nhận request; phép đọc lại phải hoạt động trong test.
6. Nếu dùng assertion control hoặc version server-side, tạo race có kiểm soát và chứng minh điều kiện bị sai sẽ từ chối sửa.
7. Khi nhiều attribute được gửi trong một LDAP modify operation, xác minh server áp dụng thao tác cho entry đúng theo khả năng nguyên tử của giao thức và schema.

### 15.4. Test ledger và crash recovery

Giả lập crash ở bốn vị trí: sau khi reserve ledger, trước khi gọi LDAP; sau khi LDAP ghi thành công nhưng trước khi ledger cập nhật; trong lúc đọc lại sau timeout; và sau khi ledger hoàn tất nhưng trước khi trả response cho client. Yêu cầu hệ thống có thể chạy **reconciliation** mà không phát thông báo trùng hoặc tạo entry sai.

Đừng chỉ kiểm tra số lần gọi method mock. Cần một số integration test với LDAP server thật hoặc test container phù hợp, vì **NameAlreadyBoundException**, schema, escaping, timeout và concurrency phụ thuộc hành vi server.

## 16. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Thiết kế thay thế |
| --- | --- | --- |
| Coi **LdapTemplate.bind** và authentication bind là một | Retry sai, có thể gây khóa tài khoản | Phân biệt create-entry command và authentication |
| Bắt **NameAlreadyBoundException** rồi trả thành công | DN có thể thuộc đối tượng/dữ liệu khác | Đọc lại và so thuộc tính do command sở hữu |
| Retry mọi **modify** sau timeout | Thao tác ghi có thể đã thành công | Đối soát trạng thái và dùng operation lũy đẳng |
| Chỉ kiểm tra trước khi sửa rồi tin rằng không có race | Dữ liệu bị ghi đè đồng thời | Server-side assertion, locking hoặc serialization phù hợp |
| Dùng DN hoặc email làm identity bất biến | Rename, move OU hoặc tái sử dụng giá trị làm lạc liên kết | Stable ID + directory source |
| Coi ledger **APPLIED** trước khi nhận/xác minh LDAP | Crash tạo thông báo thành công giả | Ledger có **PENDING/UNKNOWN**, reconcile |
| Giữ SQL transaction trong suốt request LDAP | Tăng lock contention và thời gian giữ connection | Transaction ngắn, idempotent processing |
| Cùng commandId nhưng payload mới vẫn nhận kết quả cũ | Che thao tác khác và gây sai dữ liệu | Unique commandId + kiểm tra payload hash |
| Đưa NamingException thẳng qua port | Business phụ thuộc vào Spring/JNDI | Exception và kết quả trung lập |
| Bỏ qua TLS và ACL của service account | Lộ credential hoặc quyền ghi quá rộng | LDAPS/StartTLS hợp lệ, nguyên tắc tối thiểu quyền |

## 17. Bài tập thực hành

Một hệ thống đồng bộ nhân viên từ HR sang OpenLDAP. HR có thể phát lại cùng sự kiện vì mạng không ổn định. Khi nhân viên mới xuất hiện, ứng dụng phải tạo LDAP entry; khi email đổi, phải cập nhật thuộc tính **mail**. Đôi khi server LDAP nhận lệnh ghi nhưng client timeout, và các sự kiện về cùng nhân viên có thể đến sai thứ tự.

Hãy thực hiện:

1. Thiết kế hai command **EnsurePersonExists** và **ReplaceEmail** cùng **commandId** và hợp đồng kết quả **APPLIED / ALREADY_APPLIED / CONFLICT / UNKNOWN_OUTCOME**.
2. Định nghĩa DN của entry và ID bền vững để tránh nhầm tài khoản khi nhân viên bị chuyển OU. Dùng **LdapNameBuilder** và **LdapQueryBuilder**, không ghép chuỗi DN/filter.
3. Viết adapter **LdapTemplate.bind** tạo entry nếu chưa có; khi gặp DN trùng, so sánh các attribute do lệnh sở hữu rồi đưa ra kết luận.
4. Thiết kế **modify** email có khả năng kiểm tra trạng thái đích và xử lý lệnh cũ đến sau lệnh mới bằng một cơ chế concurrency control có kiểm chứng.
5. Thiết kế ledger SQL cho deduplication và phác họa cách hồi phục nếu crash sau khi LDAP ghi nhưng trước khi ledger ghi **APPLIED**.
6. Viết bộ test cho concurrent create, timeout sau ghi, event bị lặp, event sai thứ tự, sai schema, TLS/certificate sai, ACL thiếu và authentication bind bị thử lại.

Trước khi đưa vào sản phẩm, xác nhận bốn cam kết độc lập: **trạng thái entry cuối**, **xử lý command trùng**, **xung đột cập nhật đồng thời**, và **tác dụng phụ ngoài LDAP**. Nếu chỉ giải quyết một trong bốn, hệ thống chưa thể tuyên bố *command hoàn toàn idempotent*.

**Kết luận:** thiết kế idempotent command cho **bind tạo entry** và **modify attribute** bắt đầu từ ý nghĩa của từng thao tác, trạng thái đích và cách chứng minh kết quả sau lỗi mạng. Spring LDAP giúp thực hiện **bind**, **modify** và đọc lại entry; application cần thêm hợp đồng kết quả, command ID, chính sách xung đột và đối soát. **Authentication bind** là một trường hợp khác, có rủi ro đếm lần đăng nhập và khóa tài khoản, nên không được retry như lệnh tạo entry.
