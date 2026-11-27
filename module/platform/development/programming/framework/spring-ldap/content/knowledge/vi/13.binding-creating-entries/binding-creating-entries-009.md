# Idempotent create và xử lý retry trong Spring LDAP

Khi một ứng dụng nhận yêu cầu tạo người dùng LDAP, cùng một yêu cầu có thể được gửi nhiều lần: phía gọi gặp timeout, hệ thống hàng đợi phát lại thông điệp, hoặc hai tiến trình cùng xử lý một sự kiện. Nếu mỗi lần đều tạo một entry mới với DN khác nhau, thư mục có thể chứa dữ liệu trùng lặp. Nếu coi mọi lỗi là thất bại rồi tạo lại tùy ý, ứng dụng còn có thể ghi đè hoặc làm sai dữ liệu đã tồn tại.

**Idempotent create** là cách thiết kế để việc thực hiện lại *cùng một yêu cầu hợp lệ* có kết quả cuối ổn định. Trong Spring LDAP, ta thường triển khai bằng **LdapTemplate.bind(...)** với **DN xác định trước**, sau đó kiểm tra entry hiện có nếu máy chủ báo đã tồn tại. Retry chỉ an toàn khi giữ nguyên danh tính và có khả năng phân biệt entry tương đương với entry xung đột.

> Trong bài này, “bind để tạo entry” chỉ thao tác thêm entry vào directory qua Spring LDAP/JNDI. Nó khác với thao tác **LDAP bind để xác thực** tài khoản kết nối.

## 1. Xác định chính xác điều gì phải idempotent

Giả sử Spring LDAP được cấu hình với base DN **dc=example,dc=org**, và người dùng được lưu dưới **ou=people**. Hệ thống tiếp nhận lệnh:

~~~text
CreatePerson(uid="an", cn="An Nguyen", sn="Nguyen")
DN tương đối: uid=an,ou=people
DN đầy đủ:    uid=an,ou=people,dc=example,dc=org
~~~

Mỗi lần xử lý lệnh này phải dùng **cùng một DN** và cùng dữ liệu nghiệp vụ đã thống nhất. Tập kết quả mong muốn:

| Tình huống | Hành vi đúng |
| --- | --- |
| Chưa có entry ở DN đích | Tạo entry; trả về **CREATED**. |
| Entry đã có và khớp yêu cầu | Không ghi thêm; trả về **ALREADY_PRESENT** (thành công về mặt nghiệp vụ). |
| Entry đã có nhưng dữ liệu không tương thích | Báo **CONFLICT**; không ghi đè. |
| Timeout hoặc mất kết nối, chưa biết máy chủ có tạo thành công không | Ghi nhận trạng thái **UNKNOWN**; kiểm tra lại hoặc retry có kiểm soát với **chính DN đó**. |
| DN cha chưa tồn tại, schema sai, hoặc thiếu quyền | Trả lỗi phù hợp; sửa cấu hình/dữ liệu trước khi thử lại. |

Để đạt tính chất này, cần xác định **khóa định danh ổn định** từ nghiệp vụ, chẳng hạn mã nhân viên hoặc một ID bất biến. Không dùng timestamp, UUID sinh mới trên *mỗi lần thử*, hoặc giá trị ngẫu nhiên để tạo DN; nếu cần ID ngẫu nhiên, phải sinh **một lần** khi tiếp nhận yêu cầu và lưu lại để các lần retry tái sử dụng.

Tính duy nhất của DN được máy chủ LDAP bảo vệ tại chính vị trí đó. Tuy nhiên, LDAP **không mặc nhiên đảm bảo duy nhất cho thuộc tính** như **mail** hoặc **uid** trên toàn bộ cây thư mục. Nếu cùng một người có thể bị tạo ở hai OU khác nhau, cần quy tắc ánh xạ ID → DN nhất quán hoặc ràng buộc duy nhất do hệ thống/LDAP server hỗ trợ.

## 2. Vì sao “tìm trước, rồi tạo” vẫn bị race condition?

Một cách làm dễ nghĩ đến là tìm DN, thấy chưa tồn tại thì gọi **bind**. Hai tiến trình có thể đồng thời quan sát trạng thái “chưa có”, sau đó cùng tạo:

| Thời điểm | Worker A | Worker B |
| --- | --- | --- |
| T1 | Kiểm tra: chưa có | |
| T2 | | Kiểm tra: chưa có |
| T3 | LDAP Add: thành công | |
| T4 | | LDAP Add: báo **entryAlreadyExists** |

Kiểm tra trước không giải quyết được cạnh tranh ghi. Cách phù hợp hơn là:

1. Tạo **DN ổn định**, kiểm tra đầu vào và chuẩn bị attributes.
2. Gọi **LdapTemplate.bind(...)** để tạo entry trực tiếp.
3. Nếu tạo thành công, kết thúc với **CREATED**.
4. Nếu gặp **NameAlreadyBoundException**, **đọc entry tại DN đó** và so sánh theo quy tắc nghiệp vụ: khớp → **ALREADY_PRESENT**; khác → **CONFLICT**.
5. Nếu xảy ra lỗi kết nối/timeout, xem kết quả là **chưa xác định** rồi hòa giải hoặc retry giới hạn.

~~~mermaid
flowchart TD
    A[Nhận lệnh tạo entry] --> B[Tạo DN ổn định và kiểm tra đầu vào]
    B --> C[LDAP Add qua LdapTemplate.bind]
    C -->|Thành công| D[CREATED]
    C -->|Entry đã tồn tại| E[Đọc lại DN và so sánh]
    E --> F{Có tương đương với yêu cầu?}
    F -->|Có| G[ALREADY_PRESENT]
    F -->|Không| H[CONFLICT]
    C -->|Timeout hoặc mất kết nối| I[Kết quả UNKNOWN]
    I --> J{Còn lượt retry?}
    J -->|Có| K[Backoff và dùng lại cùng DN]
    K --> C
    J -->|Không| L[Đưa vào luồng đối soát]
~~~

**LDAP Add** xử lý việc thêm *một entry* tại DN đích ở phía máy chủ; khi hai lệnh thêm cùng DN cạnh tranh, chỉ một lệnh có thể tạo thành công. Điều này **không** có nghĩa là chuỗi nhiều thao tác LDAP, ví dụ tạo người dùng rồi thêm vào nhiều nhóm, tự động có giao dịch nguyên tử.

## 3. Ví dụ triển khai với LdapTemplate

Ví dụ sau dùng Java 17+ và Spring LDAP, giả định ứng dụng đã cung cấp bean **LdapTemplate** kết nối đến directory có base DN **dc=example,dc=org**. Entry cha **ou=people** đã được tạo và tài khoản dịch vụ có quyền thêm/đọc entry tại đây. Mẫu **inetOrgPerson** yêu cầu các thuộc tính như **cn** và **sn**.

~~~java
import java.util.Objects;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class IdempotentPersonCreator {
    private final LdapTemplate ldapTemplate;

    public IdempotentPersonCreator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public enum Outcome {
        CREATED, ALREADY_PRESENT
    }

    public record PersonSpec(String uid, String cn, String sn) { }
    public record Result(Outcome outcome, Name dn) { }

    public Result create(PersonSpec request) {
        validate(request);

        // DN tương đối với base DN trong ContextSource.
        // uid đã được chuẩn hóa từ phía nghiệp vụ.
        Name dn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", request.uid())
                .build();

        Attributes attributes = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");
        attributes.put(objectClasses);
        attributes.put("uid", request.uid());
        attributes.put("cn", request.cn());
        attributes.put("sn", request.sn());

        try {
            ldapTemplate.bind(dn, null, attributes);
            return new Result(Outcome.CREATED, dn);
        } catch (NameAlreadyBoundException alreadyExists) {
            // Chỉ xác nhận thành công sau khi đã đọc và kiểm chứng.
            PersonSpec actual = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<PersonSpec>) attrs ->
                            new PersonSpec(
                                    getString(attrs, "uid"),
                                    getString(attrs, "cn"),
                                    getString(attrs, "sn"))
            );

            if (!request.equals(actual)) {
                throw new EntryConflictException(
                        "Entry đã tồn tại với thuộc tính khác tại " + dn);
            }
            return new Result(Outcome.ALREADY_PRESENT, dn);
        }
    }

    private static void validate(PersonSpec request) {
        Objects.requireNonNull(request, "request");
        if (request.uid() == null
                || !request.uid().matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        if (request.cn() == null || request.cn().isBlank()
                || request.sn() == null || request.sn().isBlank()) {
            throw new IllegalArgumentException("cn và sn không được rỗng");
        }
    }

    private static String getString(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : String.valueOf(attr.get());
    }

    public static class EntryConflictException extends RuntimeException {
        public EntryConflictException(String message) {
            super(message);
        }
    }
}
~~~

Điểm cần đọc kỹ trong ví dụ:

- **LdapNameBuilder** tạo DN từ các RDN có cấu trúc, tránh tự nối chuỗi DN bằng dữ liệu đầu vào. Biểu thức kiểm tra **uid** minh họa quy tắc ID dạng chữ thường của hệ thống này; ứng dụng thực tế cần quy tắc chuẩn hóa phù hợp.
- **BasicAttributes(true)** dùng tra cứu tên thuộc tính không phân biệt hoa/thường; danh sách **objectClass** và các thuộc tính phải phù hợp schema LDAP mà server đang áp dụng.
- **NameAlreadyBoundException** là trường hợp cần kiểm chứng, **không phải** bằng chứng rằng yêu cầu lặp đã thành công. Một entry cùng DN nhưng khác người hoặc khác dữ liệu bắt buộc phải tạo xung đột.
- **PersonSpec.equals(...)** ở đây so sánh chính xác **uid**, **cn**, **sn**, phù hợp khi cả ba được coi là bất biến đối với lệnh create. Trong hệ thống thực tế, tên hiển thị có thể thay đổi, giá trị có thể được máy chủ chuẩn hóa, và một số thuộc tính có thể là nhiều giá trị. Hãy định nghĩa tiêu chí tương đương theo **schema và nghiệp vụ** (ví dụ ID bất biến, phiên bản yêu cầu, các thuộc tính bắt buộc), thay vì áp dụng so sánh chuỗi máy móc.
- Nếu đọc lại cũng bị lỗi, hàm sẽ ném lỗi tiếp. Khi đó **chưa thể** kết luận entry khớp; tầng điều phối phải xử lý theo trạng thái chưa xác định.

Mã trên tập trung vào **tính idempotent của một entry**, chưa triển khai bộ retry, logging, phân loại lỗi hay cơ chế đối soát. Các phần này nên được đặt ở tầng dịch vụ gọi hàm **create** để chính sách thử lại nhất quán.

## 4. Retry khi kết quả tạo entry chưa chắc chắn

Một trường hợp đặc biệt quan trọng:

~~~text
Client                     LDAP server
  | -- Add uid=an ----------> |
  |                           | Tạo entry thành công
  | <---- phản hồi bị mất ---- X
  | timeout                   |
  | -- Add cùng DN ----------> |
  | <--- entryAlreadyExists -- |
  | -- Lookup cùng DN -------> |
  | <--- entry khớp --------- |
  | Kết luận ALREADY_PRESENT  |
~~~

Tại thời điểm timeout, ứng dụng **không biết** LDAP Add đã được commit hay chưa. Vì vậy không nên gắn nhãn “tạo thất bại” rồi sinh DN mới. Thử lại bằng **cùng một DN và cùng nội dung** cho phép cả hai khả năng được giải quyết: lần trước chưa tạo → lần này tạo; lần trước đã tạo → phát hiện entry có sẵn và xác minh.

Chính sách retry đề xuất:

1. **Phân loại lỗi trước khi retry.** Chỉ retry có giới hạn khi lỗi có thể tạm thời (mất kết nối, server tạm không sẵn sàng, timeout). Có thể dùng **Spring Retry** hoặc một cơ chế retry nhất quán ở tầng gọi; cấu hình chỉ retry đúng các ngoại lệ đã xác nhận phù hợp với server/provider đang dùng.
2. **Giữ nguyên request.** Không tạo lại ID, DN, thuộc tính định danh hoặc dữ liệu nghiệp vụ qua mỗi lượt.
3. **Giới hạn số lần và thời gian.** Chẳng hạn tối đa ba lần retry sau lượt đầu, với các khoảng chờ tăng dần khoảng 200 ms, 400 ms, 800 ms kèm jitter, tùy SLA thực tế. Dừng sớm khi server quá tải hoặc thời gian xử lý đã hết.
4. **Giữ kết quả UNKNOWN nếu hết lượt.** Lưu mã lệnh, DN, trạng thái và thời điểm để đối soát; khi kết nối phục hồi, đọc lại entry. Không thông báo chắc chắn “chưa tạo” chỉ vì client không nhận được phản hồi.
5. **Chú ý replica.** Nếu thao tác ghi đến một server nhưng kiểm tra tồn tại qua replica chưa đồng bộ, việc đọc có thể chưa thấy entry vừa tạo. Khi cần kết luận ngay, ưu tiên đọc lại trên cùng writable endpoint hoặc dùng cơ chế đảm bảo nhất quán của hệ thống. Không tự suy ra “chưa tồn tại” chỉ từ một kết quả đọc trễ.

Ví dụ giả mã cho tầng điều phối:

~~~text
function provision(requestWithStableId):
    repeat at most MAX_ATTEMPTS:
        try:
            return idempotentPersonCreator.create(requestWithStableId)
        catch transientConnectionOrTimeout:
            if còn lượt:
                backoffWithJitter()
                continue
            record UNKNOWN and schedule reconciliation
            return UNKNOWN

    // CREATED, ALREADY_PRESENT, CONFLICT và lỗi nghiệp vụ
    // được xử lý riêng, không retry tất cả ngoại lệ.
~~~

**Lưu ý:** Nếu timeout xảy ra khi **đọc xác minh entry trùng**, lần retry tiếp theo vẫn phải giữ nguyên DN. Lỗi tạm thời có thể xuất hiện ở cả bước thêm và bước đọc, nên tầng điều phối cần xử lý kết quả của *toàn bộ* thao tác tạo idempotent.

## 5. Phân biệt lỗi có thể retry và lỗi cần can thiệp

| Kết quả LDAP / tình huống | Cách xử lý khuyến nghị |
| --- | --- |
| **entryAlreadyExists** (result code 68) | Spring LDAP thường chuyển thành **NameAlreadyBoundException**. Đọc đúng DN, so sánh; khớp → thành công, khác → xung đột. |
| **noSuchObject** (32) khi tạo | Thường thiếu entry cha/OU hoặc sai base DN; kiểm tra cấu trúc và cấu hình. Không retry liên tục như lỗi mạng. |
| **invalidDNSyntax** (34), **objectClassViolation** (65), **constraintViolation** (19) | Sửa dữ liệu/schema hoặc cách tạo attributes; cùng payload thường sẽ tiếp tục lỗi. |
| **insufficientAccessRights** (50), **invalidCredentials** (49) | Kiểm tra ACL, cấu hình xác thực và quyền của tài khoản dịch vụ. |
| **CommunicationException**, server unavailable, timeout | Có thể retry với backoff, ngân sách thời gian và DN ổn định. Nếu chưa xác minh được, ghi nhận **UNKNOWN**. |
| **CONFLICT** do dữ liệu khác với entry có sẵn | Trả lỗi nghiệp vụ (chẳng hạn HTTP 409 ở API), chuyển sang quy trình xử lý xung đột; không tự ghi đè. |

Mã LDAP và tên exception cụ thể phụ thuộc server, JNDI và phiên bản Spring LDAP. Quan sát lỗi thực tế của môi trường triển khai để điều chỉnh chính sách; **không** catch tất cả **Exception** rồi retry vô hạn.

## 6. Các ranh giới thường bị bỏ sót

### Idempotency key tại API không thay thế khóa LDAP

Nếu API nhận header **Idempotency-Key** hoặc event ID, có thể lưu ánh xạ **(nguồn gửi, khóa yêu cầu) → ID nghiệp vụ/DN/kết quả** trong một kho bền vững có ràng buộc duy nhất. Điều này giúp nhận ra yêu cầu trùng ngay cả khi nhiều instance của ứng dụng cùng xử lý. Nếu hai payload khác nhau dùng chung một key, trả xung đột thay vì âm thầm lấy kết quả cũ. Tuy nhiên, ánh xạ này vẫn phải dẫn đến một DN ổn định ở LDAP; không thể chỉ dựa vào cache hết hạn để đảm bảo duy nhất lâu dài.

### Create không đồng nghĩa với upsert

Mục tiêu của idempotent create là **tạo nếu chưa có, xác nhận nếu đã có và tương đương**. Việc sửa **cn**, **sn**, đổi tên, di chuyển DN hoặc reset mật khẩu nên đi qua lệnh cập nhật riêng với quy tắc cạnh tranh phù hợp. Không dùng lỗi duplicate làm lý do gọi **modifyAttributes(...)** để ghi đè dữ liệu của người khác.

Với thuộc tính nhạy cảm như **userPassword**, ứng dụng thường không được phép đọc lại giá trị rõ ràng, và server có thể băm hoặc biến đổi giá trị đã ghi. Không lấy việc so sánh mật khẩu thô làm điều kiện idempotency; cần thiết kế luồng thiết lập/reset mật khẩu riêng.

### Nhiều bước provisioning cần đối soát từng bước

Ví dụ, quy trình “tạo người dùng → thêm vào nhóm → cập nhật hệ thống khác” có thể dừng sau bước đầu. Retry phần tạo user an toàn **không tự đảm bảo** các bước còn lại hoàn tất đúng một lần. Mỗi bước nên có điều kiện idempotent tương ứng, theo dõi tiến độ và cơ chế resume/reconcile. Không giả định nhiều LDAP operation có một giao dịch nguyên tử xuyên suốt.

### Bảo mật và khả năng vận hành

Tài khoản kết nối qua **ContextSource** chỉ nên có quyền cần thiết tại nhánh LDAP được quản lý. Dùng **LDAPS hoặc StartTLS** phù hợp cấu hình an toàn của directory. Khi ghi log, nên lưu mã yêu cầu, DN đã kiểm soát, loại kết quả, số lần retry và mã lỗi; hạn chế đưa mật khẩu, token, hoặc toàn bộ attributes nhạy cảm vào log. Số liệu hữu ích gồm **created**, **already_present**, **conflict**, **unknown**, số lượt retry và tỷ lệ timeout.

## 7. Các kịch bản kiểm thử bắt buộc

| Kịch bản | Kỳ vọng |
| --- | --- |
| Gọi create lần đầu với DN hợp lệ | Có đúng một entry; kết quả **CREATED**. |
| Gọi lại cùng DN và cùng dữ liệu | Không tạo thêm; **ALREADY_PRESENT**. |
| Gọi lại cùng DN nhưng thuộc tính bắt buộc khác | **CONFLICT**, dữ liệu cũ không bị thay đổi. |
| Hai request cùng lúc cho cùng DN | Chỉ một LDAP Add thành công; request còn lại xác minh duplicate; cuối cùng một entry. |
| Mô phỏng server đã tạo xong nhưng client không nhận phản hồi | Retry dùng cùng DN, tìm thấy dữ liệu khớp và trả kết quả thành công về nghiệp vụ. |
| Đứt kết nối cả khi add và khi lookup, hết lượt retry | Kết quả **UNKNOWN**; có bản ghi để kiểm tra lại. |
| DN cha không tồn tại hoặc thiếu quyền | Lỗi được phân loại, không retry vô hạn. |

Với kiểm thử tích hợp, dùng một LDAP test server có schema và hành vi đủ gần môi trường triển khai (chẳng hạn LDAP container phục vụ test). Kiểm tra **trạng thái directory sau mỗi trường hợp**, thay vì chỉ assert giá trị trả về của method. Trường hợp mất phản hồi sau commit cần mô phỏng có chủ đích: thực hiện add thành công rồi gây lỗi ở phía client; đây là ca thử giúp chứng minh retry không sinh duplicate.

## Ghi nhớ

Khả năng tạo entry idempotent trong Spring LDAP dựa vào ba điều kiện phối hợp: **DN và payload ổn định**, **bind trước rồi xác minh khi trùng**, và **retry có giới hạn khi kết quả chưa rõ**. **ALREADY_PRESENT** chỉ được xem là thành công sau khi kiểm chứng entry thực tế tương đương yêu cầu. Với quá trình tạo nhiều entry hoặc cập nhật nhiều hệ thống, cần thêm cơ chế theo dõi tiến độ và đối soát vì một lần **LdapTemplate.bind(...)** chỉ bảo vệ riêng thao tác tạo entry tại DN của nó.
