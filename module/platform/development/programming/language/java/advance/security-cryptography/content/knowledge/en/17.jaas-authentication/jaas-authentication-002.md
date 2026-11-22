# 17.2 Subject, Principal và public hoặc private credentials

Trong **JAAS (Java Authentication and Authorization Service)**, kết quả xác thực không nhất thiết được mô tả bằng một chuỗi username hoặc boolean isLoggedIn. JAAS gom các **danh tính**, thuộc tính định danh và **thông tin xác thực** liên quan vào một đối tượng **javax.security.auth.Subject**. Một Subject có thể chứa **nhiều Principal**, nhiều **public credentials** và nhiều **private credentials**. Hiểu đúng ba tập hợp này là nền tảng cho LoginContext, LoginModule, Kerberos/GSS-API và code Java dùng khóa hoặc chứng thực theo chủ thể.

Bài học tập trung vào **cấu trúc Subject và ý nghĩa Principal/public/private credentials**, đồng thời giải thích lifecycle an toàn. Hai chương trình Java 17+ bên dưới kiểm tra các API, từ getPrincipals(Class) đến setReadOnly và Destroyable.destroy, cùng một luồng JAAS login → commit → logout tối giản.

## 1. Subject là ai, Principal biểu diễn điều gì?

Theo JAAS, **Subject** đại diện cho **một thực thể** như người dùng, service hoặc process; Subject có thể có nhiều danh tính trong các hệ thống hoặc theo các vai trò khác nhau. Một **Principal** là một đối tượng triển khai java.security.Principal, đại diện cho **một danh tính hoặc khía cạnh danh tính**.

~~~text
Subject (thực thể sau xác thực)
  |
  +-- Set<Principal>
  |      UserId("alice")
  |      Role("auditor")
  |      RealmIdentity("alice@EXAMPLE.REALM")
  |
  +-- Set<Object> publicCredentials
  |      Chứng chỉ public X.509, thông tin có thể chia sẻ
  |
  +-- Set<Object> privateCredentials
         Kerberos credential nhạy cảm, secret key,
         proof of possession hoặc credential bí mật
~~~

Các lớp UserId, Role, RealmIdentity trong sơ đồ là **tên minh họa**, không phải lớp Java chuẩn. Concrete types có sẵn thường tùy JAAS LoginModule/provider, ví dụ KerberosPrincipal hoặc các principal của môi trường đăng nhập. Ví dụ runnable tự định nghĩa Java records UserId và Role.

**Các nguyên tắc chính:**

- Subject đại diện cho **chủ thể**, không phải chỉ một username.
- Principal mô tả **danh tính** thuộc Subject, không phải password, session token hoặc bản thân private key.
- Một Subject **có thể có nhiều Principal**: người dùng, role, group, realm, dịch vụ hoặc các định danh tương ứng.
- Subject **không tự xác thực** một chuỗi Principal được thêm thủ công. Code có quyền sửa Subject có thể tạo Principal; độ tin cậy đến từ **quá trình authentication**.
- Subject không phải permission engine độc lập, không thay thế RBAC/ABAC và không tự phát hành JWT hay HTTP session.

### 1.1. Principal interface nhỏ nhưng rất quan trọng

~~~java
package java.security;

public interface Principal {
    String getName();
}
~~~

Đây là hình dạng API rút gọn để giải thích, không phải toàn bộ source interface của JDK. getName() trả **tên đại diện danh tính**. Concrete implementations cần có **equals và hashCode** phù hợp, vì Principal được lưu trong **Set**. Hai object cùng định danh cần được so sánh ổn định theo chính sách của type đó; Java 17 record có equality dựa trên các thành phần record, phù hợp cho Principal minh họa.

~~~java
public record UserId(String name)
        implements java.security.Principal, java.io.Serializable {
    @Override
    public String getName() {
        return name;
    }
}
~~~

Mảnh record trên giúp hiểu interface; chương trình thực hành có class bao quanh và kiểm thử. Với production, cần xác định **issuer/realm/tenant** trong identity nếu cùng username xuất hiện ở nhiều hệ thống; không so sánh chỉ dựa trên tên hiển thị không duy nhất.

### 1.2. Principal về người dùng và role có giống nhau?

Không. UserId("alice") chỉ **người dùng cụ thể**, còn Role("admin") mô tả một **khía cạnh vai trò/nhóm** đã được gắn bởi hệ thống tin cậy. Nếu Java service thêm role từ HTTP header không tin cậy, nó không được biến thành quyền quản trị chỉ nhờ nằm trong Subject.

Phân biệt:

- **Identity Principal:** username, account ID, service account ID hoặc Kerberos principal.
- **Group/Role Principal:** nhóm/vai trò thuộc danh tính đã xác minh.
- **Realm/Tenant Principal:** ranh giới định danh, giúp tránh nhầm user trùng tên ở nhiều tenant.

**Role Principal không tự đưa ra quyết định authorization.** Code phải kiểm tra **chính sách quyền riêng**, resource, action, tenant và trạng thái yêu cầu.

## 2. Ba bộ dữ liệu trong Subject

Java SE 17 Subject duy trì ba Set:

| Tập hợp | Method Java | Kiểu trả về | Ý nghĩa |
| --- | --- | --- | --- |
| **Principals** | getPrincipals() | Set<Principal> | Danh tính/khía cạnh danh tính của Subject. |
| **Public credentials** | getPublicCredentials() | Set<Object> | Dữ liệu xác thực được thiết kế để chia sẻ theo mô hình ứng dụng, ví dụ certificate công khai. |
| **Private credentials** | getPrivateCredentials() | Set<Object> | Dữ liệu xác thực nhạy cảm cần bảo vệ riêng, như secret key hoặc token. |

Mỗi tập là **Set**, không phải List:

- Không có thứ tự có ý nghĩa ổn định để lấy “principal đầu tiên” hoặc “credential số 0”.
- Không giữ duplicate theo equals/hashCode của phần tử.
- Một tên Principal có thể trùng ở hai concrete classes mà vẫn là hai object khác nhau.
- Credential chứa Object tùy loại; ứng dụng cần biết **class được chấp nhận** và ràng buộc trust.

### 2.1. Public credential là gì?

Tài liệu JAAS nêu ví dụ **public-key certificates** hoặc một số vé dịch vụ được thiết kế để chia sẻ. Tuy nhiên chữ **public trong tên collection không có nghĩa bất kỳ ai cũng được đọc/log/chuyển ra ngoài**. An toàn công bố tùy loại credential và policy.

Ví dụ về mặt ý tưởng:

- X509Certificate là certificate công khai; private key **không** nằm trong certificate.
- Metadata của certificate/realm đã xác minh có thể hỗ trợ lựa chọn public key.
- Một public credential trong demo là PublicProfile("training-cert-label"): **chỉ là nhãn**, không phải certificate thật.

**Bearer token vẫn là bí mật** dù endpoint khác có thể “nhìn thấy” token trong giao thức. Không đặt API key/session secret vào publicCredentials chỉ vì bạn dự định truyền nó giữa services. Phân loại dựa trên khả năng **dùng lại để giả mạo** và rủi ro lộ.

### 2.2. Private credential là gì?

Private credential là thông tin cần bảo vệ bổ sung, ví dụ:

- Secret key/HMAC key có thể dùng để chứng minh danh tính hoặc thực hiện nghiệp vụ được cấp phép.
- Kerberos credential/ticket nhạy cảm theo profile, có thể thực hiện operation dưới danh tính tương ứng.
- Token/proof of possession hoặc private-key handle cần giới hạn quyền.
- Các loại credential hỗ trợ **javax.security.auth.Destroyable** hoặc **Refreshable** để quản lý vòng đời.

Private credential **không phải password hash trong database** và không nhất thiết là một PrivateKey. Nó có thể là bất kỳ object login provider dùng để chứng minh quyền. Chọn **concrete credential class** và quản lý quyền truy cập phù hợp.

### 2.3. Public/private là phân loại trong JAAS, không phải mã hóa

**Thêm object vào getPrivateCredentials không tự mã hóa object đó**, không đặt khóa vào HSM, không tự xóa memory khi session hết hạn, cũng không tự phân quyền cho mọi code trong cùng process. Trong môi trường dùng **Security Manager** (mô hình lịch sử), Java kiểm tra PrivateCredentialPermission khi truy cập private credential. Nhưng Security Manager đã **deprecated for removal trong Java 17**; kiến trúc bảo mật mới không nên dựa duy nhất vào các kiểm tra này.

Để bảo vệ thực tế cần **ranh giới trust của ứng dụng, không chia sẻ object bừa bãi, IAM/KMS/HSM, tránh logging, lifecycle logout/expiry và authorization độc lập**.

## 3. Tạo Subject và thêm Principal/credentials

Trong Java 17:

~~~java
Subject subject = new Subject();
subject.getPrincipals().add(new UserId("alice"));
subject.getPrincipals().add(new Role("reader"));
subject.getPublicCredentials().add(new PublicProfile("training"));
subject.getPrivateCredentials().add(secretCredential);
~~~

Đây là **mảnh minh họa** cần các class UserId, Role, PublicProfile và biến secretCredential; chương trình hoàn chỉnh nằm phía dưới. Constructor new Subject() tạo ba tập rỗng.

Constructor khác có dạng:

~~~java
new Subject(
    false,
    Set.of(new UserId("alice")),
    Set.of(new PublicProfile("training")),
    Set.of(secretCredential)
);
~~~

Tham số boolean đầu là **readOnly**. Constructor sao chép các phần tử vào **Set nội bộ mới**, không giữ trực tiếp Set gốc; **nhưng không deep-copy object** bên trong. Constructor và các method từ chối null collections/null elements.

**Cần phân biệt:**

- new Subject() → writable, chưa chứng thực danh tính.
- new Subject(true, ...) → có dữ liệu ban đầu nhưng các Set không cho add/remove sau đó.
- new Subject(false, ...) → có dữ liệu ban đầu và cho phép sửa theo quyền/policy.
- LoginContext.login() + LoginModule.commit() → con đường JAAS thông dụng để **gắn dữ liệu đã xác thực**, thay vì tin Subject tự lắp.

### 3.1. Add/remove và duplicate Principal

~~~java
subject.getPrincipals().add(new UserId("alice")); // phần tử mới
subject.getPrincipals().add(new UserId("alice")); // không thêm duplicate
~~~

Với Java record một trường name, hai UserId cùng "alice" có equals/hashCode tương đương. Do Set, size chỉ tăng một lần. Điều đó **không ngăn một Subject có hai UserId khác nhau**; nếu nghiệp vụ yêu cầu chỉ một account ID, ứng dụng cần validate bất biến.

Không dùng Principal.getName() đơn thuần để kết luận Principal khác type hoặc realm đều là cùng danh tính. Cần namespace/issuer/tenant rõ ràng.

## 4. Live Set và bản sao lọc theo class

Một điểm dễ hiểu sai của Java 17 Subject API:

| Method | Tập trả về được backed bởi Subject? | Hệ quả |
| --- | --- | --- |
| getPrincipals() | **Có** | add/remove trên tập trả về sửa Principal set của Subject. |
| getPublicCredentials() | **Có** | add/remove trên tập trả về sửa public credential set. |
| getPrivateCredentials() | **Có** | add/remove trên tập trả về sửa private credential set. |
| getPrincipals(UserId.class) | **Không**, tập mới đã lọc | clear/add/remove trên tập lọc không sửa Subject. |
| getPublicCredentials(MyClass.class) | **Không**, tập mới đã lọc | Tập kết quả lọc không phải cách cập nhật Subject. |
| getPrivateCredentials(MyClass.class) | **Không**, tập mới đã lọc | Không deep-copy secret object, và vẫn chịu kiểm tra quyền liên quan. |

**Tập typed mới** không tạo **bản deep copy của credential objects**: nó giữ **tham chiếu đến cùng objects**. Sửa/hủy private credential mutable có thể ảnh hưởng mọi nơi đang giữ tham chiếu, dù tập kết quả lọc không được backed bởi Subject.

### 4.1. Rủi ro nếu làm lộ live Set

Giả sử service trả thẳng subject.getPrincipals() cho plugin hoặc logic không đáng tin. Plugin có thể tự add Role("admin") khi Subject writable hoặc xóa role. Điều này làm hỏng identity data mà code phía sau có thể tin.

**Thiết kế tốt:** dùng facade chỉ đọc/DTO chỉ chứa thông tin an toàn; chỉ cho module xác thực/trust layer thêm/xóa Principal. Collections.unmodifiableSet(subject.getPrincipals()) **không phải snapshot immutable**: wrapper chặn sửa qua chính nó nhưng phản ánh thay đổi bên trong Subject. Muốn snapshot identity ổn định, tạo tập mới gồm những Principal bất biến hoặc DTO.

### 4.2. Truy xuất private credential và PrivateCredentialPermission

Trong Java 17 **nếu có Security Manager**:

- Sửa Principal/public/private sets có thể yêu cầu **AuthPermission** tương ứng.
- Lặp qua untyped getPrivateCredentials() có thể ném **SecurityException** nếu thiếu **PrivateCredentialPermission** cho một credential.
- getPrivateCredentials(SomeClass.class) yêu cầu quyền đối với các credentials phù hợp theo contract; nếu thiếu có thể ném SecurityException.

Các kiểm tra này phụ thuộc môi trường **có Security Manager** và policy. Chúng là chi tiết tương thích JAAS, **không thay thế least privilege, phân vùng process và authorization ở ứng dụng**.

## 5. Read-only Subject: khóa tập hợp, không khóa mọi object

Khi JAAS đã hoàn thành authentication và role/credentials không nên tiếp tục thay đổi, ứng dụng có thể gọi **subject.setReadOnly()**.

~~~java
subject.setReadOnly();
boolean locked = subject.isReadOnly();
~~~

Sau khi setReadOnly:

1. Không thể thêm/xóa Principal hoặc public/private credentials **qua các Set của Subject**; một thao tác sửa sẽ ném **IllegalStateException**.
2. Không có API chuyển một Subject read-only trở lại writable.
3. Những **credential objects đã có** không tự trở thành bất biến sâu. Một private credential có thể thay đổi nội dung hoặc được **Destroyable.destroy()** dù Subject read-only.
4. Object đã bị destroy vẫn **có thể còn nằm trong Set** vì destroy nội dung không tương đương remove khỏi Subject; trong Subject read-only, việc remove credential object có thể bị từ chối.
5. **Read-only không phải security boundary bảo vệ secrets**: code còn giữ tham chiếu secret object hoặc có khả năng sử dụng khóa vẫn cần kiểm soát riêng.

~~~text
Subject writable:
  + add/remove Principal
  + add/remove credentials
  + mutate/destroy credential object (theo contract của object)

subject.setReadOnly()

Subject read-only:
  - add/remove trong ba Subject sets -> IllegalStateException
  + destroy credential object (nếu class hỗ trợ)
  ? object có thể vẫn mutable nếu không bất biến
~~~

**Lưu ý khi dùng LoginContext.logout:** LoginModule thường cần remove chính những Principal/credentials mà nó đã thêm ở commit. Nếu bạn tự setReadOnly quá sớm, logout có thể **không gỡ được entry khỏi Set**; một implementation phù hợp có thể destroy được credentials nhưng không loại được object. Phải thiết kế rõ lifecycle: ai có quyền đóng phiên, khi nào làm read-only, và làm sao không biến dữ liệu phiên hết hạn thành đối tượng vẫn được ứng dụng tin tưởng.

### 5.1. Read-only khác immutable DTO

Một **DTO immutable** thường chỉ mang những field cần thiết cho nghiệp vụ, ví dụ userId, tenantId, roles, issuedAt. Nó không giữ private secret. **Subject.setReadOnly** chỉ cấm thay đổi tập hợp và vẫn chứa credential objects. Đừng đưa trực tiếp Subject vào HTTP response, Redis, JSON logger hoặc cache phân tán.

Nếu muốn xuất thông tin danh tính đã được phép, hãy **map từ Subject sang DTO an toàn theo allowlist**. Không serialize hoặc stringify toàn bộ Subject để tiết kiệm code.

## 6. Private credentials và Destroyable

**javax.security.auth.Destroyable** cung cấp hai method:

~~~java
void destroy() throws DestroyFailedException;
boolean isDestroyed();
~~~

Đây là cấu trúc giao diện minh họa, bỏ qua chi tiết về default methods. Destroyable **không bảo đảm tất cả implementations sẽ xóa bộ nhớ**, vì default destroy có thể ném **DestroyFailedException**; cần kiểm tra **implementation cụ thể**. Những object nhạy cảm có thể triển khai destroy để xóa char[]/byte[] hoặc giải phóng key handle.

**Một chiến lược quản lý credential cần:**
- Có **owner rõ ràng**: ai tạo, ai cấp, ai đóng/hủy.
- Hạn chế số bản sao, thời gian sống, nơi log hoặc truyền.
- Gọi destroy/logout/revoke khi session kết thúc theo contract của credential.
- Xử lý ngoại lệ destroy và không sử dụng credential sau khi bị hủy.
- Phân biệt **xóa reference khỏi Subject** với **xóa secret material**. Hai thao tác không tương đương.
- Không tự trông chờ JVM GC xóa ngay secret bytes; không cam kết rằng Arrays.fill đã xóa mọi bản sao trong framework/native heap.

### 6.1. Public credential vẫn cần quản lý vòng đời

Public-key certificate có thể được phép công bố nhưng vẫn có **hạn hiệu lực, key usage, issuer, revoked status** và policy. Một certificate public trong Subject không đồng nghĩa chain được xác minh tin cậy cho mọi nghiệp vụ. Ngược lại, nếu một loại "ticket" là bearer capability có thể dùng lại để đóng giả chủ thể, phải coi đó là **nhạy cảm** bất kể ví dụ JAAS tài liệu liệt kê loại vé có thể chia sẻ.

### 6.2. Không in Subject hoặc credentials bừa bãi

**Subject.toString(), Object.toString(), collection logging** có thể gọi toString của Principal hoặc credential và làm lộ thông tin. Cần:
- Tránh log toàn bộ Subject, nhất là private credentials.
- Với credential do bạn định nghĩa, override toString thành một **giá trị che giấu**.
- Audit bằng **account/tenant ID đã được phép, event type, trace ID, kết quả**; không in password, session secret, private key, token, Kerberos ticket.
- Không đưa credentials vào equals/hashCode dùng để cache hay log. Subject equality dựa trên các tập Principal/credentials; nó không phải stable account identity.

## 7. Java 17+ — chương trình 1: Subject, Principal và ba Set

Ví dụ độc lập dùng record UserId/Role, record PublicProfile và class SessionSecret triển khai Destroyable. SessionSecret **không phải credential thật**, chỉ minh họa cách hủy một char[] nội bộ. Chương trình cố ý thêm cùng một UserId hai lần để thấy Set khử duplicate, kiểm tra typed snapshot, live set và read-only.

Tạo file **SubjectCredentialDemo.java**:

~~~java
import java.io.Serializable;
import java.security.Principal;
import java.util.Arrays;
import java.util.Set;
import javax.security.auth.Destroyable;
import javax.security.auth.Subject;

public class SubjectCredentialDemo {
    public record UserId(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record Role(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record PublicProfile(String label) {}

    public static final class SessionSecret implements Destroyable {
        private char[] value;
        public SessionSecret(char[] input) { value = input.clone(); }
        @Override public synchronized void destroy() {
            if (value != null) {
                Arrays.fill(value, '\0');
                value = null;
            }
        }
        @Override public synchronized boolean isDestroyed() {
            return value == null;
        }
        @Override public String toString() {
            return "SessionSecret[REDACTED]";
        }
    }

    public static void main(String[] args) throws Exception {
        Subject subject = new Subject();
        subject.getPrincipals().add(new UserId("alice"));
        subject.getPrincipals().add(new UserId("alice"));
        subject.getPrincipals().add(new Role("reader"));
        subject.getPublicCredentials().add(new PublicProfile("training-cert-label"));

        char[] original = "fake-session-material".toCharArray();
        SessionSecret secret = new SessionSecret(original);
        Arrays.fill(original, '\0');
        subject.getPrivateCredentials().add(secret);

        System.out.println("Số Principal phân biệt: " + subject.getPrincipals().size());
        System.out.println("UserId: " + subject.getPrincipals(UserId.class).size());
        System.out.println("Public profile: " +
                subject.getPublicCredentials(PublicProfile.class).size());
        System.out.println("Private credential: " +
                subject.getPrivateCredentials(SessionSecret.class).size());

        Set<UserId> snapshot = subject.getPrincipals(UserId.class);
        snapshot.clear();
        System.out.println("Xóa snapshot không đổi Subject: " +
                (subject.getPrincipals(UserId.class).size() == 1));

        Set<Principal> live = subject.getPrincipals();
        live.add(new Role("auditor"));
        System.out.println("Live set thay đổi Subject: " +
                (subject.getPrincipals().size() == 3));

        subject.setReadOnly();
        boolean blocked = false;
        try {
            subject.getPrincipals().add(new Role("admin"));
        } catch (IllegalStateException expected) {
            blocked = true;
        }
        System.out.println("Read-only từ chối sửa set: " + blocked);
        secret.destroy();
        System.out.println("Vẫn hủy được private credential: " +
                secret.isDestroyed());
        System.out.println("Credential object còn trong set: " +
                (subject.getPrivateCredentials().size() == 1));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 SubjectCredentialDemo.java
java SubjectCredentialDemo
~~~

Stdout kiểm thử:

~~~text
Số Principal phân biệt: 2
UserId: 1
Public profile: 1
Private credential: 1
Xóa snapshot không đổi Subject: true
Live set thay đổi Subject: true
Read-only từ chối sửa set: true
Vẫn hủy được private credential: true
Credential object còn trong set: true
~~~

### 7.1. Phân tích kết quả

- **Số Principal phân biệt: 2**: UserId("alice") bị thêm trùng, nhưng Set chỉ giữ một UserId và một Role("reader").
- **Public profile: 1**: nhãn training-cert-label là metadata minh họa, không chứa certificate/secret thực.
- **Private credential: 1**: một object SessionSecret nằm trong privateCredentials; không in char[] hoặc toString có thể lộ.
- **Xóa snapshot không đổi Subject: true**: getPrincipals(UserId.class) tạo Set mới, nên clear chỉ thay đổi tập lọc.
- **Live set thay đổi Subject: true**: Set<Principal> từ getPrincipals() được backed bởi Subject; thêm Role("auditor") làm tổng 3.
- **Read-only từ chối sửa set: true**: sau setReadOnly, không thêm được Role("admin").
- **Vẫn hủy được private credential: true**: SessionSecret.destroy xóa char[] nội bộ và cập nhật trạng thái.
- **Credential object còn trong set: true**: destroy khác remove; object đã hủy còn nằm trong Subject read-only.

**Giới hạn của bài test:** các Principal được thêm thủ công để kiểm tra collection semantics, **không chứng minh người dùng alice đã đăng nhập thật**. Chương trình không triển khai Kerberos, hệ thống IAM hay policy phân quyền. Chuỗi "fake-session-material" là dữ liệu thử, không phải credential production.

### 7.2. Vì sao cần Serializable trên Principal?

Java 17 Subject có hỗ trợ Serializable; theo Javadoc, **Principal trong Subject có thể được serialize**, còn **các credential sets không được serialize**. Vì interface java.security.Principal **không tự extends Serializable**, concrete Principal phải triển khai Serializable nếu bạn muốn serialize Subject. **Không sử dụng Subject serialization làm cách sao lưu phiên đăng nhập đầy đủ hoặc vận chuyển private credential**.

Chủ động hạn chế serialization của Subject vì nó có thể chứa **danh tính nhạy cảm và những Principal classes không đáng tin**. Ưu tiên DTO đã xác minh và schema có phiên bản.

### 7.3. Thông điệp read-only thực tế

**Subject.setReadOnly không xóa bí mật** và không tự động logout. Nếu yêu cầu chấm dứt phiên, cần gọi đúng **LoginContext.logout** hoặc cơ chế revoke/credential.destroy riêng, ở một thời điểm còn có thể sửa các Set nếu LoginModule cần remove. Một credential đã destroy không nên được tiếp tục sử dụng dù một tham chiếu object còn tồn tại.

## 8. LoginContext và LoginModule: Subject nhận Principal khi nào?

Một Subject được tạo bằng new Subject rồi tự thêm Role chỉ là object data. Trong JAAS **authentication có cấu trúc**, **LoginContext** điều phối một hoặc nhiều **LoginModule** theo **Configuration**. Thông thường, module xác minh bằng cơ chế của mình trong pha login, rồi **chỉ khi toàn bộ authentication thành công** mới gắn Principal và credentials vào Subject trong pha commit.

~~~text
Application tạo LoginContext(name, Subject/handler/config)
                    |
                    v
               LoginContext.login()
                    |
                    v
      LoginModule.initialize(Subject, CallbackHandler, ...)
                    |
                    v
      LoginModule.login() -- kiểm tra bí mật/identity
                    |
             đủ module thành công?
               /              \
             Có                Không
              |                  |
              v                  v
      LoginModule.commit()   LoginModule.abort()
      gắn Principal/cred     xóa state tạm, không gắn identity sai
              |
              v
    LoginContext.getSubject()
    identity/credential được xác thực
              |
              v
    LoginContext.logout()
    LoginModule.logout() gỡ và hủy chính những
    Principal/credentials mà module đã thêm
~~~

### 8.1. Các method của LoginModule

| Method | Thời điểm | Trách nhiệm |
| --- | --- | --- |
| **initialize** | LoginContext chuẩn bị module | Nhận Subject, CallbackHandler, sharedState, options. Chưa khẳng định login thành công. |
| **login** | Pha xác thực | Nhận/kiểm tra credentials, giữ trạng thái tạm; trả true/false hoặc ném LoginException theo contract. |
| **commit** | Toàn bộ login thành công theo module flags | Gắn **đúng Principal và credentials của module** vào Subject, hủy state xác thực không cần nữa. |
| **abort** | Authentication/commit không thành công | Gỡ/destroy state tạm hoặc dữ liệu đã commit dở; không để lại identity sai. |
| **logout** | Khi ứng dụng chủ động kết thúc JAAS session | Gỡ Principal và credentials **chính module đã tạo**, hủy secret thích hợp. |

Nếu có nhiều LoginModules trong cùng một LoginContext, **mỗi module chỉ nên quản lý phần tử mình đã thêm**. Xóa sạch toàn bộ Subject trong logout của một module có thể phá dữ liệu mà module khác hoặc ứng dụng đã xác thực độc lập.

### 8.2. Các module control flags

Trong **JAAS Configuration**, mỗi LoginModule có một flag:

- **REQUIRED**: phải thành công nhưng tiếp tục chạy các modules còn lại; nếu thất bại thì tổng thể login thất bại.
- **REQUISITE**: phải thành công; nếu thất bại thì kết thúc pha login sớm.
- **SUFFICIENT**: thành công có thể khiến hệ thống bỏ qua phần modules còn lại nếu không có REQUIRED/REQUISITE trước đó đã thất bại.
- **OPTIONAL**: có thể thành công hoặc thất bại; tổng thể vẫn tuân quy tắc về các modules còn lại.

Chi tiết điều phối nhiều modules và các corner cases nên tra Javadoc Configuration và JAAS LoginModule Developer's Guide. **Không tự giải nghĩa OPTIONAL thành “mọi user đều được đăng nhập”.** Trong mọi trường hợp, code nghiệp vụ chỉ được tin Subject sau khi **LoginContext.login() trả thành công**.

### 8.3. CallbackHandler và bí mật

**NameCallback** và **PasswordCallback** là các callback hay dùng cho demo password login; ngoài đời có thể dùng Kerberos, token, PKCS#11 hay provider-specific login. **PasswordCallback** nhận char[] và hỗ trợ clearPassword; caller và LoginModule nên dọn các char[] tạm. Không log password; không lưu nó trong Subject làm Principal. Module có thể thêm một private credential **sau xác thực** nếu cần, nhưng không nhất thiết phải lưu password gốc.

**Đừng coi LoginModule là password hasher**: việc xác thực password production cần KDF/verifier phù hợp, source identity đáng tin và rate limiting chống đoán online. Ví dụ bên dưới cố ý chỉ là **in-memory training module**, so sánh một password thử để minh họa lifecycle JAAS, tuyệt đối không dùng làm hệ thống đăng nhập thực.

## 9. Java 17+ — chương trình 2: LoginContext, commit và logout

Ví dụ tự cung cấp Configuration theo code (không cần sửa global JAAS login config), một DemoLoginModule và CallbackHandler. Khi username/password test đúng, module:
- Thêm **UserId Principal** đại diện danh tính đã xác thực.
- Thêm **PublicProfile** chỉ chứa nhãn công khai minh họa.
- Thêm **PrivateProof** bọc char[] giả, hỗ trợ **Destroyable**.

Khi logout, module xóa **chính ba phần tử nó sở hữu** và hủy proof. Khi sai password, login thất bại và không có authenticated Subject từ LoginContext mới. Chương trình không giữ password người dùng trong Subject.

Tạo file **JaasLoginSubjectDemo.java**:

~~~java
import java.io.IOException;
import java.io.Serializable;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Destroyable;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasLoginSubjectDemo {
    public record UserId(String name) implements Principal, Serializable {
        @Override public String getName() { return name; }
    }
    public record PublicProfile(String source) {}
    public static final class PrivateProof implements Destroyable {
        private char[] contents;
        public PrivateProof(char[] input) { contents = input.clone(); }
        @Override public synchronized void destroy() {
            if (contents != null) {
                Arrays.fill(contents, '\0');
                contents = null;
            }
        }
        @Override public synchronized boolean isDestroyed() {
            return contents == null;
        }
        @Override public String toString() {
            return "PrivateProof[REDACTED]";
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private boolean authenticated;
        private boolean committed;
        private String account;
        private UserId principal;
        private PublicProfile profile;
        private PrivateProof proof;

        @Override public void initialize(Subject subject,
                CallbackHandler callbackHandler, Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = callbackHandler;
        }

        @Override public boolean login() throws LoginException {
            NameCallback user = new NameCallback("User");
            PasswordCallback pass = new PasswordCallback("Password", false);
            char[] supplied = null;
            try {
                handler.handle(new Callback[] { user, pass });
                supplied = pass.getPassword();
                char[] expected = "training-pass".toCharArray();
                boolean valid;
                try {
                    valid = "alice".equals(user.getName())
                            && Arrays.equals(supplied, expected);
                } finally {
                    Arrays.fill(expected, '\0');
                }
                if (!valid) {
                    throw new FailedLoginException("Invalid credentials");
                }
                account = user.getName();
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException error) {
                throw new LoginException("Credential callback failed");
            } finally {
                if (supplied != null) Arrays.fill(supplied, '\0');
                pass.clearPassword();
            }
        }

        @Override public boolean commit() {
            if (!authenticated) return false;
            principal = new UserId(account);
            profile = new PublicProfile("training-directory");
            char[] material = "not-a-real-token".toCharArray();
            try {
                proof = new PrivateProof(material);
            } finally {
                Arrays.fill(material, '\0');
            }
            subject.getPrincipals().add(principal);
            subject.getPublicCredentials().add(profile);
            subject.getPrivateCredentials().add(proof);
            account = null;
            committed = true;
            return true;
        }

        private void cleanup() {
            if (subject != null) {
                if (principal != null) subject.getPrincipals().remove(principal);
                if (profile != null) subject.getPublicCredentials().remove(profile);
                if (proof != null) {
                    subject.getPrivateCredentials().remove(proof);
                    proof.destroy();
                }
            }
            principal = null;
            profile = null;
            proof = null;
            account = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() {
            boolean hadState = authenticated || committed;
            cleanup();
            return hadState;
        }
        @Override public boolean logout() {
            boolean hadState = committed;
            cleanup();
            return hadState;
        }
    }

    private static Configuration configuration() {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"Training".equals(name)) return null;
                return new AppConfigurationEntry[] {
                        new AppConfigurationEntry(
                                DemoLoginModule.class.getName(),
                                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                                Map.of())
                };
            }
        };
    }

    private static CallbackHandler callbacks(String userName, char[] password) {
        return entries -> {
            for (Callback entry : entries) {
                if (entry instanceof NameCallback name) {
                    name.setName(userName);
                } else if (entry instanceof PasswordCallback pass) {
                    pass.setPassword(password);
                } else {
                    throw new UnsupportedCallbackException(entry);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        char[] accepted = "training-pass".toCharArray();
        try {
            LoginContext login = new LoginContext(
                    "Training", null, callbacks("alice", accepted),
                    configuration());
            login.login();
            Subject subject = login.getSubject();
            PrivateProof proof = subject.getPrivateCredentials(
                    PrivateProof.class).iterator().next();
            System.out.println("Login thành công: " + (subject != null));
            System.out.println("Principal alice: " +
                    subject.getPrincipals(UserId.class).iterator().next().getName());
            System.out.println("Public credentials: " +
                    subject.getPublicCredentials(PublicProfile.class).size());
            System.out.println("Private credentials: " +
                    subject.getPrivateCredentials(PrivateProof.class).size());
            login.logout();
            System.out.println("Logout xóa Principal: " +
                    subject.getPrincipals().isEmpty());
            System.out.println("Logout xóa credentials: " +
                    (subject.getPublicCredentials().isEmpty()
                            && subject.getPrivateCredentials().isEmpty()));
            System.out.println("Logout hủy private proof: " + proof.isDestroyed());
        } finally {
            Arrays.fill(accepted, '\0');
        }

        char[] rejected = "wrong".toCharArray();
        try {
            LoginContext bad = new LoginContext(
                    "Training", null, callbacks("alice", rejected),
                    configuration());
            boolean denied = false;
            try {
                bad.login();
            } catch (LoginException expected) {
                denied = true;
            }
            System.out.println("Sai mật khẩu bị từ chối: " + denied);
            System.out.println("Thất bại không có authenticated Subject: " +
                    (bad.getSubject() == null));
        } finally {
            Arrays.fill(rejected, '\0');
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 JaasLoginSubjectDemo.java
java JaasLoginSubjectDemo
~~~

Kết quả kiểm thử:

~~~text
Login thành công: true
Principal alice: alice
Public credentials: 1
Private credentials: 1
Logout xóa Principal: true
Logout xóa credentials: true
Logout hủy private proof: true
Sai mật khẩu bị từ chối: true
Thất bại không có authenticated Subject: true
~~~

### 9.1. Điều gì được chứng minh?

1. **Configuration** được cung cấp trực tiếp bằng overload LoginContext(name, subject, handler, config); không cần thay file cấu hình toàn cục của JVM.
2. **LoginContext.login** điều phối module với flag REQUIRED; vì chỉ có một module trong demo, login thành công khi module xác thực thành công.
3. **DemoLoginModule.login** dùng callback lấy username/password; đây là **so sánh chuỗi cố định phục vụ test**, không phải password verification an toàn cho production.
4. **commit** gắn UserId, PublicProfile và PrivateProof. Chúng nằm ở **ba Set khác nhau**, chứ không được nhập thành một Map.
5. **getSubject** trả Subject sau login thành công; không nên lấy đối tượng này trước khi login rồi tin nó đã xác thực.
6. **logout** chỉ gỡ ba phần tử DemoLoginModule đã thêm và gọi destroy() trên PrivateProof.
7. **Failed login** làm LoginContext không có authenticated Subject trong trường hợp constructor không nhận Subject và quá trình xác thực không thành công.
8. **char[] password** được clear ở PasswordCallback và caller theo phần bộ nhớ chúng sở hữu; không giả định đã xóa mọi bản sao trong JVM.

### 9.2. Mẫu tối giản cố ý thiếu gì?

- **Identity store thật, salt/password hashing KDF, rate limit, MFA, audit, anti-enumeration và account lockout**: ứng dụng production phải bổ sung qua provider/thành phần phù hợp.
- **Quản lý proof thật**: PrivateProof chỉ chứa chuỗi placeholder; không phải token/secret có thể dùng truy cập hệ thống.
- **Xử lý nhiều LoginModules**: demo một REQUIRED module; hệ thống thực có nhiều module và phải cleanup đúng cả commit/abort.
- **Transactional commit**: code demo không có rollback phức tạp nếu thêm phần tử thất bại giữa chừng. Implementation production phải đảm bảo cleanup khi commit lỗi và khi module bị gọi lại.
- **Subject read-only**: demo không đóng băng Subject trước logout vì cần remove các phần tử đã thêm.
- **Quản lý session HTTP**: JAAS Subject không tự lưu phiên trình duyệt, không cấp cookie hoặc access token.

**Quan trọng:** không copy so sánh Arrays.equals với chuỗi password hardcoded sang production. Đó chỉ là fixture chạy độc lập, không có khả năng chống dò mật khẩu. Thiết kế production phải dùng cơ chế xác thực tin cậy và kiểm soát lạm dụng.

## 10. Subject.doAs: thực thi gắn Subject và giới hạn mô hình bảo mật cũ

Trong Java SE 17, **Subject.doAs(subject, PrivilegedAction)** và **Subject.doAs(subject, PrivilegedExceptionAction)** cho phép thực thi một action trong **AccessControlContext** có gắn Subject. Mô hình lịch sử của JAAS dùng thông tin Principal này kết hợp Java Security Manager/policy để đánh giá một số quyền.

Ví dụ **mảnh code**, không phải một chương trình độc lập:

~~~java
String answer = Subject.doAs(authenticatedSubject,
        (java.security.PrivilegedAction<String>) () -> {
            // Code thực hiện operation trong ngữ cảnh JAAS của Subject.
            return "operation-finished";
        });
~~~

**Điều không được hiểu sai:**

- doAs **không tự xác thực** người dùng, không biến một Principal tự tạo thành danh tính đáng tin, và không cấp phép mọi thao tác.
- doAs **không tự động truyền bearer token/private credentials** sang dịch vụ khác. Giao thức Kerberos/GSS-API hoặc library riêng có thể sử dụng Subject credentials, nhưng cách dùng tuân API của provider.
- doAs trong Java 17 dựa trên **AccessControlContext/Security Manager**, là mô hình đã có các API deprecated-for-removal. Đặc biệt **Subject.getSubject(AccessControlContext)** bị đánh dấu deprecated-for-removal trong Java 17.
- Đừng giả định **context doAs tự truyền qua ExecutorService, CompletableFuture hoặc thread pool**. Cần xem xét behavior của API/JDK/provider cụ thể, truyền identity/authorization context qua ranh giới async một cách rõ và an toàn.
- Với service Java hiện đại, **authorization nên được kiểm tra rõ ràng theo identity, role, tenant và resource** ở tầng ứng dụng hoặc security framework đang duy trì; không coi doAs là lớp authorization phổ quát.

**Bài này chỉ dùng doAs để chỉ ra mối liên hệ của Subject với mô hình JAAS**, không yêu cầu cài Security Manager và không biến Security Manager thành tiền đề của hai ví dụ runnable.

## 11. Subject không thay thế ranh giới bảo mật của hệ thống

Một Subject có thể được sử dụng bởi code application để biết ai đang thực hiện yêu cầu. Nhưng:

1. **Đầu vào Subject phải đáng tin:** LoginModule/provider hoặc tầng xác thực đã xác minh identity; không tin dữ liệu trực tiếp từ cookie/header chưa kiểm tra.
2. **Chọn đúng Principal class:** nếu hệ thống cho nhiều realm, đừng chọn Principal đầu tiên hoặc lọc bằng tên không có namespace.
3. **Credential scope rõ ràng:** không giữ secret credential trong Subject dùng chung toàn bộ process; tránh đưa access token giữa tenant/service khác nhau.
4. **Dữ liệu trong Subject có vòng đời:** logout, session expiry, key rotation, credential refresh/revoke; một object vẫn được tham chiếu sau logout có thể tiếp tục tồn tại nếu caller giữ riêng.
5. **Kiểm tra quyền nghiệp vụ:** Subject có Role("admin") không tự bảo đảm caller có quyền xem record của tenant khác.
6. **Quản lý khóa riêng:** private-key handle từ HSM có thể không export được; chỉ thực hiện operation theo policy của provider, không cố đọc key bytes để debug.
7. **Audit tối thiểu:** ghi subject ID đã được phép, event type, issuer, action, outcome và trace ID; không log toàn bộ Subject hoặc private credentials.

### 11.1. Thiết kế ranh giới cho web service

~~~text
HTTP request (header/token/cookie chưa được tin)
             |
             v
Authentication layer (JAAS module, IdP, framework...)
       kiểm chứng chứng chỉ/ticket/token/password
             |
      xác thực thành công?
        /            \
       no             yes
       |               |
     reject            v
                  Subject + Principal(s)
                  public/private credentials đúng scope
                       |
                       v
                 Build safe identity DTO
                 userId, tenantId, roles đã kiểm chứng
                       |
                       v
                 Authorize action + resource
                       |
                       v
                    Business logic
                       |
                       v
                  session end / logout /
                  destroy secret / revoke
~~~

Nhiều hệ thống web hiện đại dùng các framework authentication/security riêng, không trực tiếp dùng JAAS LoginContext. Dù vậy, **phân biệt danh tính (Principal), chứng thực đã diễn ra (authentication) và quyền thực thi (authorization)** là kiến thức cốt lõi có thể áp dụng rộng.

### 11.2. Identity DTO khác credential store

Một DTO dành cho business logic chỉ nên mang dữ liệu cần thiết như **stable user ID, tenant ID, roles đã được phê duyệt, issuer và thời điểm xác thực khi cần**. Không chứa raw password, private key, Kerberos ticket hay bearer token. Việc tạo DTO có thể lọc theo Principal class cụ thể và kiểm tra tính duy nhất, nhưng phải nhớ typed Set **không phải deep-copy** các Principal mutable; nên chuyển sang immutable application values.

## 12. Threading, serialization và các chi tiết tinh tế

### 12.1. Không chia sẻ Subject mutable giữa request

Vì untyped sets được backed bởi Subject, hai threads có thể quan sát và sửa dữ liệu danh tính khi không có ownership rõ ràng. Với nhiều JAAS modules hoặc session lifecycle, một request đang đọc credentials có thể chạm credential vừa bị destroy/logout ở request khác.

Khuyến nghị:
- Mỗi phiên xác thực có **lifecycle riêng**; không dùng một Subject toàn cục rồi thay Principal theo request.
- Giai đoạn tạo/commit/logout phải được phối hợp phù hợp với provider/lifecycle.
- **Không dùng Subject equals/hashCode làm cache key ổn định**: các tập Principal/credentials là một phần equality và có thể thay đổi.
- Với async work, truyền **immutable security context/DTO** hoặc một handle có quyền rõ, không chia sẻ raw private credentials cho bất kỳ job nào.
- **Không trông chờ read-only ngăn credential bị destroy**: mọi consumer phải xử lý credential đã hết hạn hoặc bị hủy.

### 12.2. Serialization của Subject không có private credentials

Theo Javadoc Subject của Java 17, Subject có Serializable, **Principals được serialize** còn **credentials không được serialize**. Interface java.security.Principal không tự triển khai Serializable, nên Principal implementation cần Serializable nếu muốn serialize theo contract.

Bởi vậy:
- Serialize/deserialize Subject **không round-trip các credentials**. Không dùng như session persistence hoặc backup khóa.
- Không cho deserialization tùy tiện dữ liệu Java không đáng tin; việc deserialize object Java có những rủi ro độc lập.
- Hãy xây dựng schema DTO chuyên dụng, có version và kiểm soát field, nếu cần truyền danh tính qua service.

### 12.3. Secret bị hủy nhưng Set còn chứa object

Một credential triển khai Destroyable có thể bị hủy trong lúc Subject đang **read-only**, theo Subject contract. Object vẫn có thể nằm trong getPrivateCredentials() do không remove được. Điều đó không có nghĩa credential còn dùng được; cần tham khảo isDestroyed/lifecycle của type cụ thể. Với các lớp credentials không hỗ trợ destroy hoặc destroy thất bại, một login/logout framework cần chiến lược xử lý lỗi thích hợp, không nên im lặng và khẳng định secret đã bị xóa.

## 13. Bộ kiểm thử nên có cho Subject và LoginModule

| Nhóm | Test | Kỳ vọng |
| --- | --- | --- |
| **Subject mới** | new Subject() | Ba tập rỗng, writable ban đầu. |
| **Principal equality** | Thêm cùng UserId("alice") hai lần | Không có duplicate với record value equality. |
| **Nhiều Principal** | Thêm UserId và Role | Tập giữ cả hai concrete types. |
| **Public credential** | Thêm PublicProfile label | Đọc được từ public set; không bị nhầm với private set. |
| **Private credential** | Thêm SessionSecret | Đọc được theo type phù hợp; không log char[]/token. |
| **Live set** | Lấy getPrincipals() rồi add(Role) | Subject được cập nhật. |
| **Typed snapshot** | Lấy getPrincipals(UserId.class) rồi clear | Subject gốc không thay đổi. |
| **Reference aliasing** | Typed filtered private set trỏ đến cùng object | Hủy object được phản ánh mọi nơi giữ tham chiếu. |
| **Read-only** | setReadOnly rồi add/remove | IllegalStateException; không thể mở lại writable. |
| **Destroy** | Destroy private credential sau setReadOnly | Có thể hủy nếu type cho phép; không đồng nghĩa remove khỏi Set. |
| **Subject constructor** | Set null/null element, readOnly true | Reject null, giữ initial elements, readOnly enforcement. |
| **Login success** | Callback cung cấp thông tin đúng, login | Commit tạo Principal/public/private đúng scope. |
| **Login failure** | Callback sai password | LoginException; không có authenticated Subject khi không truyền Subject ban đầu. |
| **Abort** | Một module required thất bại hoặc commit lỗi | Xóa trạng thái tạm, không để leaked/partially committed credentials. |
| **Logout** | Login xong rồi logout | Gỡ đúng phần tử module đã thêm; destroy secret. |
| **Multi-module** | Hai LoginModules cùng dùng một Subject | Module A không xóa Principal/credential của B. |
| **Private permission** | Java 17 Security Manager + policy hạn chế | Access to private credentials được kiểm theo PrivateCredentialPermission, xử lý SecurityException. |
| **Serialization** | Subject chứa Principal Serializable và credentials | Credential không được serialize theo contract; không dùng làm session token. |
| **Concurrent logout/use** | Một thread logout/hủy, một thread đang xử lý | Không tiếp tục thao tác bằng secret bị hủy; ownership rõ. |
| **Log inspection** | Thử gọi logger với Subject | Audit không in password/private credential material. |

Với LoginModule thật, còn cần test **authentication source** (directory/Kerberos/IdP), account lockout/rate-limit, ticket expiry/refresh, permissions, revocation và audit. Hai demo chỉ kiểm tra **contracts cốt lõi của Subject/Principal/credentials**, không thay thế integration tests cho provider production.

## 14. Các lỗi phổ biến

1. **Coi Subject là một String username.** Nó có thể chứa nhiều danh tính và credentials khác nhau.
2. **Tự thêm Role("admin") rồi nghĩ người dùng đã được xác thực.** Principal chỉ đáng tin sau authentication và trust boundary phù hợp.
3. **Đặt password hoặc bearer token vào Principal.** Principal mô tả danh tính; bí mật cần quản lý ở lớp credential/secret phù hợp.
4. **Tưởng publicCredentials luôn an toàn để log.** Tùy type, một vé/token vẫn có thể là bearer capability nhạy cảm.
5. **Tưởng privateCredentials tự mã hóa hoặc khóa bí mật bằng quyền JVM hiện đại.** Subject chỉ là một tập object; bảo vệ thực sự phải được thiết kế riêng.
6. **Nhầm getPrincipals() và getPrincipals(Class).** Untyped là live; typed là tập mới không backed.
7. **Nhầm typed filtered credential set là deep copy secret.** Các phần tử là tham chiếu tới object gốc.
8. **Cho mọi layer giữ Subject mutable.** Chúng có thể sửa role/credentials nếu không có ranh giới.
9. **Dùng Subject.setReadOnly như logout.** Read-only không xóa Principal/secret.
10. **Giả định read-only khiến credential không thể destroy.** Contract cho phép destroy credential kể cả khi Subject read-only.
11. **Remove credential khỏi Set rồi nghĩ đã xóa secret bytes.** Reference removal và memory clearing là hai hành động khác nhau.
12. **Gọi destroy rồi nghĩ mọi bản sao secret trong JVM biến mất.** Vẫn có thể còn bản sao và implementation-dependent state.
13. **Ghi log Subject.toString() hoặc all credentials.** Có nguy cơ lộ identity/secret và thông tin phiên.
14. **Dùng principal.getName() không xét issuer/realm/tenant.** Dễ nhầm identity cùng tên.
15. **Dùng Subject.equals/hashCode làm user ID ổn định.** Equality phụ thuộc cả credential/Principal sets, không phải account identity.
16. **Gắn Principal vào Subject ngay trong login() trước khi overall authentication thành công.** Nên commit sau khi toàn bộ modules đáp ứng chính sách; abort dọn state.
17. **LoginModule.logout() xóa sạch Subject.** Có thể xóa thành phần thuộc module khác; chỉ dọn phần mình sở hữu.
18. **Set read-only trước khi LoginModule logout.** Có thể khiến module không remove được Principal/credential.
19. **Dùng LoginContext của một người để authenticate người khác.** Tạo LoginContext riêng cho Subject/session khác.
20. **Dùng Subject.doAs như authorization hoàn chỉnh cho web app mới.** Đây là mô hình JAAS/AccessControlContext lịch sử, không thay RBAC/ABAC của ứng dụng.
21. **Tưởng JAAS tự xử lý token refresh và network session.** Lộ trình refresh/logout/revoke phụ thuộc credential type, provider và ứng dụng.
22. **Serialize Subject để lưu trọn phiên cùng credentials.** Credentials không được serialize theo contract.

## 15. Câu hỏi tự kiểm tra

**1. Một Subject có thể có nhiều Principal không?**  
Có. Subject có Set<Principal> và mỗi Principal có thể biểu diễn identity/role/realm khác nhau.

**2. UserId("alice") và Role("alice") có nhất thiết là cùng một Principal không?**  
Không. Khác concrete type và ý nghĩa; cùng text chưa đủ để khẳng định cùng danh tính.

**3. getPrincipals(UserId.class).clear() có xóa UserId trong Subject không?**  
Không. Tập typed được trả về là tập mới, không backed bởi Subject.

**4. getPrincipals().add(new Role("admin")) có sửa Subject không?**  
Có, nếu Subject writable và caller được phép; vì đó là live set. Nhưng điều này **không làm role trở thành đã xác thực**.

**5. Private credential có tự được mã hóa vì nằm trong privateCredentials không?**  
Không. Subject tổ chức object; cách bảo vệ material tùy implementation, provider và chính sách.

**6. setReadOnly() có ngăn destroy() của credential không?**  
Không. Subject contract vẫn cho phép destroy credential; nhưng cấm add/remove trong sets.

**7. Hủy credential rồi private Set vẫn có một object, có nghĩa secret chưa bị hủy không?**  
Không nhất thiết. Object có thể vẫn tồn tại trong Set sau khi material bị destroy. Cần kiểm tra isDestroyed theo concrete type.

**8. Java 17 Security Manager bị deprecated, có nên coi PrivateCredentialPermission là hàng rào duy nhất không?**  
Không. Cần application trust boundary, least privilege, secret management và authorization rõ.

**9. LoginModule nên thêm Principal ở login() hay commit()?**  
Thông thường ở **commit() sau khi overall authentication thành công**. Abort dọn state khi login/commit thất bại.

**10. Logout có nên xóa hết mọi Principal/credential của Subject không?**  
Không. Mỗi LoginModule phải gỡ/destroy những gì **nó sở hữu**, không đụng dữ liệu của module khác.

**11. Một Principal record được tạo thủ công có chứng minh password hợp lệ không?**  
Không. Principal chỉ là object; bằng chứng đến từ kết quả authentication đáng tin.

**12. Có dùng Subject serialization để mang credentials qua network được không?**  
Không. Java 17 Subject serialize Principals nhưng không serialize credentials; cần giao thức bảo mật riêng.

## 16. Tổng kết và tài liệu tham khảo

**Subject** là container cho **Principal identities** và **public/private credentials**. Principal trả lời câu hỏi “**thực thể này được nhận diện như thế nào**”, trong khi credentials là dữ liệu phục vụ chứng thực và thao tác được phép. Phân loại public/private có ý nghĩa về quyền truy cập và độ nhạy, nhưng không tự tạo bảo mật nếu application làm lộ object hoặc quản lý secrets sai.

Những điều bắt buộc ghi nhớ trong Java 17:

- **getPrincipals/getPublicCredentials/getPrivateCredentials không typed** trả live sets; typed getters trả tập lọc mới.
- **setReadOnly** chặn sửa ba Set, nhưng **không deep-freeze** credential objects và vẫn có thể destroy credential.
- **LoginContext.login → LoginModule.commit** gắn Principal/credentials khi xác thực thành công; **abort/logout** cần cleanup.
- **Identity không đồng nghĩa authorization**; bí mật vẫn cần least privilege, lifecycle và logging an toàn.

Nguồn chính thức để đọc sâu:

- [Java SE 17 — javax.security.auth.Subject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html)
- [Java SE 17 — java.security.Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html)
- [Java SE 17 — javax.security.auth.Destroyable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html)
- [Java SE 17 — javax.security.auth.Refreshable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Refreshable.html)
- [Java SE 17 — LoginContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html)
- [Java SE 17 — LoginModule SPI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html)
- [Java SE 17 — JAAS Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html)
- [Java SE 17 — LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html)
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html)
- [Java SE 17 — PrivateCredentialPermission](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/PrivateCredentialPermission.html)