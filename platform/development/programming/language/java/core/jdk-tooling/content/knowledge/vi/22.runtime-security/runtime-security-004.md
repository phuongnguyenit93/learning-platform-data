# Policy runtime trong Java

**Runtime policy** là tập quy tắc quyết định một chương trình được phép thực hiện hành động nào khi đang chạy. Trong hệ sinh thái Java, thuật ngữ này từng được dùng phổ biến cho policy file của Java Security Manager: file khai báo quyền đọc/ghi file, kết nối mạng, đọc system property và các thao tác nhạy cảm khác mà code được phép thực hiện.

Tuy nhiên, cần phân biệt hai thế hệ:

- **Policy file kiểu Security Manager**: cơ chế cấp quyền cho từng code source bằng các permission như FilePermission, SocketPermission và PropertyPermission. Cơ chế này còn dùng được trên các JDK cũ, nhưng đã bị vô hiệu hóa vĩnh viễn từ JDK 24.
- **Security properties của JDK hiện đại**: cấu hình provider mật mã, thuật toán bị hạn chế, TLS, keystore và các thành phần bảo mật của runtime. Cấu hình này vẫn được hỗ trợ trong JDK 26, nhưng không phải cơ chế sandbox để giới hạn quyền đọc file hoặc truy cập mạng của từng class.

Khi thiết kế bảo mật cho ứng dụng hiện đại, cần kết hợp cấu hình bảo mật của JDK, authorization ở tầng ứng dụng và cơ chế cô lập của hệ điều hành hoặc container. Không nên triển khai mới dựa trên Security Manager.

## 1. Runtime policy giải quyết vấn đề gì?

Một ứng dụng có thể thực hiện nhiều hành động trong lúc chạy:

- Đọc hoặc ghi file.
- Mở kết nối mạng.
- Đọc system property.
- Tạo class loader.
- Truy cập một số tài nguyên nhạy cảm.
- Thực hiện thao tác theo vai trò hoặc quyền của người dùng.

Một runtime policy tốt xác định rõ hành động nào được phép, ai được phép thực hiện và tài nguyên nào nằm trong phạm vi cho phép.

Ví dụ, một dịch vụ báo cáo có thể cần:

| Thành phần | Nhu cầu |
|---|---|
| Report service | Đọc dữ liệu báo cáo |
| Export worker | Ghi file vào thư mục export |
| Notification client | Kết nối tới mail gateway |
| User không có quyền quản trị | Không được xóa báo cáo |

Trong mô hình Security Manager cũ, một số quyền truy cập tài nguyên được kiểm soát bởi permission của JVM. Trong ứng dụng hiện đại, quyền nghiệp vụ như xem hoặc xóa báo cáo thường phải được kiểm tra bởi chính ứng dụng; quyền của process đối với file và network cần được giới hạn bằng OS/container.

## 2. Lịch sử và trạng thái theo JDK release

Security Manager đã được sử dụng để áp dụng access-control policy lên code chạy trong JVM. Oracle bắt đầu deprecate cơ chế này for removal ở JDK 17 qua JEP 411. JDK 24 thực hiện bước tiếp theo: vô hiệu hóa Security Manager vĩnh viễn qua JEP 486.

| JDK release | Trạng thái Security Manager | Ý nghĩa đối với policy file |
|---|---|---|
| JDK 8 trở về trước | Được hỗ trợ | Policy file có thể cấp permission khi Security Manager được bật |
| JDK 9–16 | Được hỗ trợ | Có thể cấu hình policy file và Security Manager |
| JDK 17–23 | Deprecated for removal | Cơ chế cũ vẫn có thể hoạt động, nhưng ứng dụng cần lập kế hoạch migration |
| JDK 24 trở lên | Permanently disabled | Không thể bật Security Manager; policy file cũ không còn thực thi access control |

JDK 24 trở lên không cho phép bật Security Manager lúc khởi động. Các lệnh như sau khiến JVM báo lỗi khởi tạo và thoát:

~~~bash
java -Djava.security.manager -jar app.jar
~~~

Các dạng sau cũng không hợp lệ trên JDK 24 trở lên:

~~~bash
java -Djava.security.manager=allow -jar app.jar
java -Djava.security.manager=default -jar app.jar
java -Djava.security.manager=com.acme.CustomSecurityManager -jar app.jar
~~~

Gọi System.setSecurityManager(...) trong runtime cũng ném UnsupportedOperationException. Không có cờ JVM để khôi phục cơ chế này trong JDK 24+.

**Kết luận khi đọc tài liệu cũ:** các ví dụ dùng SecurityManager, java.security.policy, Policy.setPolicy hoặc permission-based sandbox phải được đánh dấu là legacy. Không sao chép lệnh của JDK 8/11/17 vào cấu hình production JDK 24/25/26 mà không kiểm tra trạng thái hỗ trợ.

## 3. Policy file kiểu cũ hoạt động như thế nào?

Trong mô hình cũ, Policy implementation xác định tập permission được cấp cho một CodeSource và có thể kết hợp Principal. Security Manager kiểm tra permission khi code thực hiện một số thao tác nhạy cảm.

Một policy file thường có các thành phần:

- **grant**: mở đầu một khối cấp quyền.
- **codeBase**: URL xác định vị trí code được cấp quyền.
- **signedBy**: alias signer được dùng khi cần ràng buộc code với certificate trong keystore.
- **Principal**: danh tính có thể được dùng trong policy-based authorization.
- **permission**: loại quyền, tài nguyên mục tiêu và các action được phép.

Cấu trúc tổng quát:

~~~text
grant [signedBy "signer"] [, codeBase "URL"] {
    permission permission.class "target", "actions";
};
~~~

Ví dụ policy file cho một ứng dụng legacy:

~~~java
grant codeBase "file:/opt/acme/app.jar" {
    permission java.io.FilePermission
        "/var/acme/data/-", "read,write";

    permission java.net.SocketPermission
        "api.example.com:443", "connect,resolve";

    permission java.util.PropertyPermission
        "user.timezone", "read";
};
~~~

Ý nghĩa:

- Code trong app.jar được đọc và ghi các file trong cây thư mục /var/acme/data.
- Code được phép kết nối tới api.example.com ở cổng 443 và phân giải hostname.
- Code được đọc system property user.timezone.
- Những permission khác không được cấp bởi grant này.

Đây là cú pháp của policy file truyền thống, chỉ có ý nghĩa khi Security Manager và Policy mechanism còn được hỗ trợ. Không dùng file này để sandbox ứng dụng trên JDK 24+.

## 4. Các loại Permission trong policy file legacy

Policy file cũ dùng các lớp con của java.security.Permission để biểu diễn loại quyền.

| Permission | Tài nguyên hoặc hành động | Ví dụ action |
|---|---|---|
| java.io.FilePermission | File và thư mục | read, write, execute, delete, readlink |
| java.net.SocketPermission | Kết nối socket | connect, listen, accept, resolve |
| java.util.PropertyPermission | System property | read, write |
| java.lang.RuntimePermission | Một số thao tác runtime nhạy cảm | createClassLoader, getClassLoader |
| java.lang.reflect.ReflectPermission | Thao tác reflection nhạy cảm | suppressAccessChecks |
| java.security.SecurityPermission | Thao tác quản trị security API cũ | getPolicy, setPolicy |

### FilePermission

Ví dụ:

~~~java
permission java.io.FilePermission
    "/var/acme/data/report.csv", "read";
~~~

Chỉ định một file cụ thể và action read.

Các dạng đường dẫn thường gặp:

| Target | Phạm vi |
|---|---|
| /var/acme/data/report.csv | Một file cụ thể |
| /var/acme/data/* | Các file trực tiếp trong thư mục |
| /var/acme/data/- | Các file trong thư mục và mọi thư mục con |
| <<ALL FILES>> | Tất cả file; quyền rất rộng |

Tránh cấp <<ALL FILES>> cho ứng dụng thông thường. Hãy giới hạn đường dẫn vào đúng thư mục dữ liệu cần dùng.

### SocketPermission

Ví dụ:

~~~java
permission java.net.SocketPermission
    "api.example.com:443", "connect,resolve";
~~~

Permission này cho phép kết nối tới hostname và cổng được chỉ định. Không nên cấp quyền kết nối tới mọi host nếu ứng dụng chỉ cần một vài endpoint.

### PropertyPermission

Ví dụ:

~~~java
permission java.util.PropertyPermission
    "user.home", "read";
~~~

Có thể cấp read hoặc write cho system property. Không nên cấp quyền đọc/ghi tất cả property nếu ứng dụng chỉ cần một giá trị cấu hình cụ thể.

### RuntimePermission

RuntimePermission điều khiển một số thao tác đặc biệt của runtime trong mô hình Security Manager cũ. Ví dụ createClassLoader hoặc setContextClassLoader. Đây là các quyền nhạy cảm; chỉ cấp khi ứng dụng thực sự cần và hiểu tác động.

## 5. Cấu hình policy file trong JDK 17–23

Phần này chỉ dành cho việc duy trì hoặc kiểm tra hệ thống legacy còn chạy JDK 17 đến JDK 23. Security Manager đã deprecated for removal trong giai đoạn này.

### Bật Security Manager và nạp policy bổ sung

~~~bash
java -Djava.security.manager -Djava.security.policy=/etc/acme/app.policy -jar app.jar
~~~

Với một dấu bằng trong giá trị java.security.policy, policy file chỉ định được nạp bổ sung cùng các policy file mặc định được cấu hình trong java.security.

### Thay thế policy mặc định

~~~bash
java -Djava.security.manager -Djava.security.policy==/etc/acme/app.policy -jar app.jar
~~~

Hai dấu bằng yêu cầu dùng policy file chỉ định thay cho các policy file được cấu hình mặc định. Cách này có thể loại bỏ các permission mặc định mà JDK cần, dẫn tới lỗi runtime. Chỉ dùng khi hiểu rõ toàn bộ policy đang thay thế.

### Vị trí policy mặc định trước JDK 24

Trong các JDK cũ còn hỗ trợ Security Manager, các vị trí mặc định thường gồm:

| Loại | Vị trí |
|---|---|
| System policy | $JAVA_HOME/conf/security/java.policy |
| User policy | ~/.java.policy |
| Cấu hình vị trí policy | Các security properties dạng policy.url.n trong java.security |

System policy được nạp trước, sau đó user policy được bổ sung. Cấu hình có thể được tùy chỉnh qua security properties của JDK tương ứng.

Không nhầm file java.policy với file java.security. File java.policy chứa các grant/permission của cơ chế legacy; file java.security chứa các security properties của JDK.

## 6. Giới hạn của policy file cũ

Một policy file không tự bật Security Manager. Trong JDK cũ, ứng dụng phải chạy với Security Manager được cài đặt thì các permission check mới được thực thi.

Một số giới hạn của mô hình cũ:

- Permission chỉ được kiểm tra tại các điểm mà Java Platform hoặc ứng dụng thực hiện security check.
- Policy sai hoặc cấp quyền quá rộng có thể làm mất ý nghĩa sandbox.
- Reflection, native code, thư viện bên thứ ba và các đường thực thi đặc biệt cần được đánh giá riêng.
- Việc bảo trì permission phức tạp khi ứng dụng có nhiều dependency.
- Security Manager gây chi phí tương thích và vận hành, là một trong các lý do cơ chế bị deprecate rồi disabled.

Một file policy tồn tại trên đĩa không chứng minh rằng runtime đang áp dụng nó. Cần xác định phiên bản JDK, cách khởi chạy JVM và trạng thái Security Manager trước khi kết luận.

## 7. Điều gì thay đổi từ JDK 24?

JDK 24 vô hiệu hóa Security Manager vĩnh viễn. Các thay đổi liên quan trực tiếp tới runtime policy gồm:

| Thành phần | Hành vi trên JDK 24+ |
|---|---|
| java -Djava.security.manager | JVM báo lỗi và thoát |
| System.setSecurityManager(...) | Ném UnsupportedOperationException |
| System.getSecurityManager() | Luôn trả về null |
| java.security.policy | Không còn được hỗ trợ |
| $JAVA_HOME/conf/security/java.policy | File system policy bị loại bỏ |
| java.security.Policy.setPolicy(...) | Ném UnsupportedOperationException |
| java.security.Policy.getPolicy() | Trả về Policy không cấp permission |
| AccessController.doPrivileged(...) | Thực thi action ngay, không tạo privilege boundary cũ |
| SecurityManager.check* | Không còn cơ chế permission enforcement cũ |

Policy class trong java.security được deprecated since 17 for removal. JDK 26 API ghi rõ Policy chỉ hữu ích khi có Security Manager; không còn cơ chế thay thế trực tiếp cho lớp này.

Điều này có nghĩa:

- Không dùng java.security.policy để hạn chế file/network access trên JDK 24+.
- Không dùng Policy.setPolicy để cài custom permission model.
- Không coi AccessController.doPrivileged là sandbox boundary.
- Không dựa vào SecurityManager.checkPermission để chặn hành động của code.
- Không dùng class loader hoặc module system như một thay thế tương đương cho Security Manager.

Nếu ứng dụng còn phụ thuộc cơ chế cũ, cần migration thiết kế bảo mật trước khi nâng JDK.

## 8. Phân biệt ba loại policy trong Java hiện đại

Tên gọi policy dễ gây nhầm lẫn. Trong ứng dụng Java hiện đại, nên tách rõ ba lớp sau:

| Loại policy | Nơi cấu hình | Vai trò hiện tại |
|---|---|---|
| Legacy Java permission policy | java.policy và java.security.policy | Chỉ còn ý nghĩa với JDK cũ còn Security Manager |
| JDK security properties | conf/security/java.security | Cấu hình provider, thuật toán, TLS và các thành phần security của JDK |
| Application authorization policy | Mã ứng dụng, database hoặc policy service | Quyết định user/role nào được phép thực hiện nghiệp vụ nào |

Ví dụ:

- FilePermission thuộc legacy permission policy.
- jdk.tls.disabledAlgorithms thuộc JDK security properties.
- Quy tắc "REPORT_READER được xem báo cáo nhưng không được xóa" thuộc application authorization policy.

Một loại policy không thay thế loại khác. Security properties không phải file cấp quyền đọc/ghi file; application authorization cũng không thay thế network isolation ở cấp OS.

## 9. Security properties file của JDK hiện đại

JDK 26 vẫn sử dụng master security properties file:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

Đây là file cấu hình các security properties mà JDK đọc khi khởi động hoặc khi thành phần bảo mật tương ứng được khởi tạo.

Các nhóm cấu hình thường gặp:

| Nhóm | Ví dụ property | Mục đích |
|---|---|---|
| Security providers | security.provider.n | Đăng ký và sắp thứ tự provider mật mã |
| Certificate path | jdk.certpath.disabledAlgorithms | Hạn chế thuật toán và key size khi xác minh certificate chain |
| TLS/DTLS | jdk.tls.disabledAlgorithms | Hạn chế protocol, cipher suite và thuật toán TLS |
| Cryptographic services | jdk.crypto.disabledAlgorithms | Hạn chế thuật toán trong các dịch vụ mật mã |
| JSSE | ssl.KeyManagerFactory.algorithm | Chọn implementation mặc định cho KeyManagerFactory |
| Keystore | keystore.type | Định dạng keystore mặc định |
| SecureRandom | Các property liên quan SecureRandom | Cấu hình nguồn random và implementation |

Các security properties này ảnh hưởng tới cách JDK cung cấp và kiểm tra dịch vụ bảo mật. Chúng không tạo sandbox cho từng class hoặc JAR.

### Cấu hình file bổ sung

Có thể truyền file security properties bổ sung bằng system property:

~~~bash
java -Djava.security.properties=file:/etc/acme/extra.security -jar app.jar
~~~

Một dấu bằng có nghĩa file được chỉ định được nối vào master security properties file. Các property trùng tên có thể ghi đè giá trị đã khai báo trước đó.

Nếu dùng hai dấu bằng:

~~~bash
java -Djava.security.properties==file:/etc/acme/complete.security -jar app.jar
~~~

File được chỉ định thay thế hoàn toàn master security properties file. Cách này rất dễ làm mất provider, algorithm restrictions hoặc cấu hình mặc định mà runtime cần. Chỉ sử dụng khi file thay thế được quản lý đầy đủ và đã kiểm thử trên đúng JDK release.

**Chú ý:** java.security.properties là cơ chế hiện hành để cấu hình security properties. Nó khác với java.security.policy, vốn là thuộc tính policy của Security Manager đã bị vô hiệu hóa từ JDK 24.

### Thêm custom property

Một file security properties có thể chứa property riêng mà ứng dụng tự đọc:

~~~properties
acme.security.profile=production
~~~

Đặt file này tại /etc/acme/extra.security và khởi chạy bằng:

~~~bash
java -Djava.security.properties=file:/etc/acme/extra.security -jar app.jar
~~~

Custom property không tự tạo ra quyền hoặc hạn chế nào. Mã ứng dụng phải đọc giá trị và triển khai hành vi tương ứng.

## 10. Đọc và kiểm tra security properties

Dùng tùy chọn java để xem cấu hình bảo mật hiệu lực:

~~~bash
java -XshowSettings:security -version
~~~

Chỉ xem nhóm properties:

~~~bash
java -XshowSettings:security:properties -version
~~~

Chỉ xem cấu hình TLS:

~~~bash
java -XshowSettings:security:tls -version
~~~

Có thể bật debug để xem cách JDK đọc security properties:

~~~bash
java -Djava.security.debug=properties -version
~~~

Output debug có thể chứa nhiều thông tin cấu hình; chỉ bật trong môi trường chẩn đoán có kiểm soát.

Trong Java code, có thể đọc một security property:

~~~java
String disabledAlgorithms =
        java.security.Security.getProperty("jdk.tls.disabledAlgorithms");

System.out.println(disabledAlgorithms);
~~~

Giá trị thực tế phụ thuộc JDK distribution, release và file cấu hình đang được sử dụng. Không hardcode một chuỗi thuật toán lấy từ máy khác làm chính sách chung cho mọi runtime.

### Thời điểm property được đọc

Một số security properties được đọc và cache khi java.security.Security được khởi tạo hoặc khi provider/TLS component được tạo. Gọi Security.setProperty sau thời điểm đó không bảo đảm thay đổi có hiệu lực; trong một số trường hợp không có exception dù giá trị không được áp dụng cho thành phần đã khởi tạo.

Với cấu hình runtime, nên đặt security properties trước khi JVM khởi chạy ứng dụng, kiểm tra bằng -XshowSettings:security và khởi động lại process sau khi thay đổi.

## 11. Thay thế legacy policy bằng application authorization

Quyền nghiệp vụ nên được kiểm tra ở đúng ranh giới của ứng dụng, sau khi user đã được xác thực.

Ví dụ: người có role REPORT_READER được xem báo cáo; chỉ ADMIN mới được xóa báo cáo.

Tạo file src/com/acme/security/AuthorizationDemo.java:

~~~java
package com.acme.security;

import java.util.Set;

public class AuthorizationDemo {

    enum Action {
        VIEW_REPORT,
        DELETE_REPORT
    }

    record User(String id, Set<String> roles) {
    }

    static boolean isAllowed(User user, Action action) {
        return switch (action) {
            case VIEW_REPORT ->
                    user.roles().contains("REPORT_READER")
                    || user.roles().contains("ADMIN");
            case DELETE_REPORT ->
                    user.roles().contains("ADMIN");
        };
    }

    public static void main(String[] args) {
        User analyst = new User(
                "user-42",
                Set.of("REPORT_READER"));

        System.out.println(
                "viewReport=" + isAllowed(analyst, Action.VIEW_REPORT));

        System.out.println(
                "deleteReport=" + isAllowed(analyst, Action.DELETE_REPORT));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/com/acme/security/AuthorizationDemo.java
~~~

Chạy:

~~~bash
java -cp out com.acme.security.AuthorizationDemo
~~~

Stdout:

~~~text
viewReport=true
deleteReport=false
~~~

Đây là ví dụ authorization ở tầng ứng dụng, không phải JVM sandbox. Trong production:

- User và role phải đến từ nguồn xác thực đáng tin cậy.
- Không lấy role từ request body rồi tin trực tiếp.
- Kiểm tra quyền trên từng resource, tenant và action.
- Mặc định từ chối khi không xác định được quyền.
- Thực hiện authorization ở service/API boundary trước khi đọc hoặc sửa dữ liệu.
- Ghi audit log cho các hành động nhạy cảm.

## 12. Cô lập process bằng OS và container

Khi cần chạy plugin, script hoặc code không đáng tin cậy, một process Java thông thường không nên được xem là sandbox chỉ vì nó có class loader riêng hoặc module path riêng.

Tài liệu migration của Oracle khuyến nghị xem xét các cơ chế bên ngoài JDK như container, hypervisor và cơ chế bảo vệ của hệ điều hành.

Các lớp kiểm soát có thể gồm:

| Cơ chế | Ví dụ | Mục đích |
|---|---|---|
| Process identity | User riêng, group riêng | Giới hạn quyền filesystem và process |
| Filesystem | Read-only root filesystem, mount đúng thư mục | Giới hạn nơi được đọc/ghi |
| Network | Firewall, egress allowlist, network policy | Giới hạn endpoint được kết nối |
| Container | Container runtime và security profile | Cô lập process, namespace và resource |
| OS sandbox | Linux seccomp, AppArmor, SELinux; macOS App Sandbox | Giới hạn system call và quyền tài nguyên |
| Virtual machine | Hypervisor và guest OS riêng | Tạo ranh giới cô lập mạnh hơn giữa workload |

Ví dụ một số nguyên tắc triển khai:

1. Chạy ứng dụng bằng service account không có quyền quản trị.
2. Chỉ mount thư mục dữ liệu ứng dụng cần dùng.
3. Dùng read-only filesystem nếu ứng dụng không cần ghi.
4. Giới hạn CPU, memory, process và file descriptor.
5. Chặn outbound network mặc định, chỉ mở endpoint cần thiết.
6. Tách workload không đáng tin cậy thành process hoặc container riêng.
7. Cập nhật base image, JDK và OS security patches.

Container không tự động an toàn chỉ vì đã đóng gói ứng dụng. Cần cấu hình quyền, network, filesystem và runtime profile phù hợp.

## 13. Module system và ClassLoader có thay thế policy runtime không?

Không. Java Platform Module System kiểm soát readability, exports, opens và quan hệ phụ thuộc module. ClassLoader quản lý việc nạp class. Hai cơ chế này không phải sandbox thay thế Security Manager.

Ví dụ:

- exports giới hạn package nào module khác có thể truy cập theo quy tắc module.
- opens cho phép reflective access trong các điều kiện module tương ứng.
- ClassLoader có thể tổ chức namespace và vòng đời class.
- Module path quyết định module được tìm thấy và resolve.

Những cơ chế đó không tự giới hạn process truy cập filesystem, network, native code hoặc system resource. Không chạy code không đáng tin cậy trong cùng JVM với giả định rằng module hoặc ClassLoader sẽ ngăn được mọi hành động nguy hiểm.

Nếu cần cô lập code không tin cậy, dùng process boundary và OS/container isolation.

## 14. Migration từ Security Manager sang runtime security hiện đại

Khi nâng ứng dụng từ JDK 17–23 lên JDK 24+, hãy kiểm tra cả cách khởi chạy, source code và dependency.

### Bước 1: Tìm dấu vết Security Manager

Tìm trong script và cấu hình:

- -Djava.security.manager
- -Djava.security.policy
- Các file .policy hoặc java.policy
- SecurityManager custom
- Policy.setPolicy(...)
- System.setSecurityManager(...)
- AccessController.checkPermission(...)
- AccessController.doPrivileged(...)

Các thư viện có thể gọi API này thay cho ứng dụng, nên cần kiểm tra cả dependency.

### Bước 2: Quét API deprecated

Có thể dùng jdeprscan từ JDK release 17–23 để tìm API deprecated for removal trong bytecode:

~~~bash
jdeprscan --for-removal app.jar
~~~

Kết quả cần được đánh giá cùng source và dependency tree. Việc không tìm thấy API không chứng minh ứng dụng không phụ thuộc policy file qua startup script.

### Bước 3: Phân loại từng mục đích cũ

| Mục đích cũ | Hướng thay thế cần xem xét |
|---|---|
| Chặn đọc/ghi file | OS user, filesystem permissions, container mount |
| Chặn network | Firewall, egress policy, network namespace |
| Giới hạn CPU/memory | Container resource limits hoặc process manager |
| Phân quyền user | Application authorization, role/permission service |
| Cô lập plugin không tin cậy | Process/container/VM riêng |
| Cấu hình thuật toán TLS | JDK security properties và JSSE |
| Kiểm soát provider mật mã | security.provider.n trong java.security |

Không có một API thay thế một-một cho Security Manager. Cần thiết kế lại ranh giới bảo mật theo tài nguyên và mối đe dọa thực tế.

### Bước 4: Kiểm thử trên JDK mục tiêu

- Khởi chạy trên đúng JDK 24/25/26 dự kiến phát hành.
- Xóa các cờ Security Manager khỏi startup script.
- Kiểm tra thư viện có dùng API đã deprecated/disabled.
- Kiểm tra quyền filesystem và network ở cấp OS.
- Kiểm tra authorization nghiệp vụ.
- Kiểm tra security properties, provider và TLS.
- Chạy integration test và thử các tình huống truy cập trái phép.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JVM báo Enabling a Security Manager is not supported | Startup script còn -Djava.security.manager trên JDK 24+ | Loại bỏ cờ và migration cơ chế sandbox |
| System.setSecurityManager ném UnsupportedOperationException | API bị vô hiệu hóa từ JDK 24 | Thay thiết kế phụ thuộc Security Manager |
| Policy file không có tác dụng | JDK 24+ không còn hỗ trợ java.security.policy | Phân biệt legacy policy với security properties hiện hành |
| Policy.setPolicy ném UnsupportedOperationException | java.security.Policy không còn cài đặt system-wide policy | Không dùng Policy API làm permission engine mới |
| getPolicy không trả permission mong đợi | JDK 24+ trả Policy không cấp permission | Migration khỏi API legacy |
| java.security.properties thay thế cấu hình quá nhiều | Dùng hai dấu bằng và ghi đè master file | Dùng một dấu bằng nếu chỉ cần bổ sung; kiểm tra toàn bộ properties |
| TLS vẫn cho phép thuật toán không mong muốn | Security property chưa được nạp hoặc đã bị ghi đè | Kiểm tra -XshowSettings:security và property hiệu lực |
| Security.setProperty không đổi hành vi | Property đã được đọc/cache hoặc component đã khởi tạo | Cấu hình trước khi khởi động và restart process |
| Dùng module/ClassLoader để chạy plugin không tin cậy | Nhầm module isolation với OS sandbox | Tách process/container và giới hạn OS resource |
| Authorization đúng ở UI nhưng API vẫn cho phép | Chỉ kiểm tra quyền ở frontend | Kiểm tra quyền tại server/service boundary |

## 16. Checklist xây dựng runtime security policy

- [ ] Xác định chính xác JDK release chạy production.
- [ ] Xác nhận ứng dụng không bật Security Manager trên JDK 24+.
- [ ] Tìm và loại bỏ dependency vào java.security.policy hoặc Policy.setPolicy.
- [ ] Tách quyền nghiệp vụ khỏi permission model legacy.
- [ ] Cấu hình application authorization ở service/API boundary.
- [ ] Chạy process bằng user có quyền tối thiểu.
- [ ] Giới hạn filesystem và network ở OS/container.
- [ ] Quản lý security providers và algorithm constraints qua java.security.
- [ ] Dùng java.security.properties có kiểm soát; tránh ghi đè master file ngoài chủ đích.
- [ ] Kiểm tra cấu hình hiệu lực bằng -XshowSettings:security.
- [ ] Chạy test âm tính để xác nhận thao tác trái phép bị từ chối.
- [ ] Ghi lại threat model, quyền cần thiết và người chịu trách nhiệm cập nhật policy.

## 17. Ghi nhớ

- Runtime policy mô tả hành động được phép khi ứng dụng đang chạy.
- Legacy Java Policy file dùng grant, codeBase, Principal và permission để cấp quyền cho code khi Security Manager được bật.
- Security Manager deprecated for removal từ JDK 17 và bị vô hiệu hóa vĩnh viễn từ JDK 24.
- Trên JDK 24+, không thể bật Security Manager; java.security.policy không được hỗ trợ và system java.policy đã bị loại bỏ.
- java.security.Policy deprecated for removal; setPolicy ném UnsupportedOperationException và getPolicy trả policy không cấp permission.
- java.security tại $JAVA_HOME/conf/security/java.security vẫn được hỗ trợ để cấu hình provider, thuật toán và TLS.
- java.security.properties=file bổ sung vào master security properties; java.security.properties==file thay thế toàn bộ master file.
- Security properties không phải cơ chế cấp quyền file/network cho từng class.
- Quyền nghiệp vụ nên được kiểm tra tại application boundary.
- Cô lập code không đáng tin cậy bằng process, container, OS sandbox hoặc VM; module và ClassLoader không phải sandbox.
- Migration cần rà soát startup flags, policy files, API deprecated, thư viện và quyền OS/container.

## Tài liệu tham khảo chính thức

- [The Security Manager Is Permanently Disabled — JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-manager-is-permanently-disabled.html)
- [JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [The Security Properties File — JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html)
- [java.security.Policy API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Policy.html)
- [Security Developer's Guide — JDK 17, Policy File Syntax](https://docs.oracle.com/en/java/javase/17/security/security-developer-guide.pdf)
- [Troubleshooting Security — JDK 26](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-security.html)