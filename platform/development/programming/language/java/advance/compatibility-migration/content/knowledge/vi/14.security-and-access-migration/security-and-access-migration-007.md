# Thay đổi chính sách JNDI, RMI và nạp mã từ xa

Khi nâng cấp JDK, một ứng dụng dùng JNDI hoặc Java RMI có thể gặp lỗi dù source code, tên dịch vụ và giao diện Java không thay đổi. Những cơ chế từng cho phép ứng dụng nhận tên class, địa chỉ `codebase`, object reference hoặc dữ liệu serialized từ hệ thống khác đã được siết chặt qua nhiều bản cập nhật bảo mật. Một cấu hình từng hoạt động trên JDK cũ có thể bị từ chối trên bản mới, nhất là khi nó dựa vào việc **tải class từ URL do phía bên kia cung cấp** hoặc **khôi phục đối tượng từ dữ liệu không đáng tin cậy**.

Vấn đề này nằm ở ranh giới giữa **tương thích hành vi** và **an toàn hệ thống**. Việc JDK chặn một đường nạp mã từ xa có thể làm một tích hợp legacy ngừng hoạt động, nhưng điều đó không nhất thiết là lỗi cần bật lại chức năng cũ. Khi nghiên cứu migration, phải hiểu cơ chế đang được dùng, phân biệt code loading với object reconstruction/deserialization, kiểm tra chính sách của đúng bản JDK, rồi chuyển sang mô hình phân phối code và dữ liệu rõ ràng, có kiểm soát.

Bài học trình bày JNDI, RMI, codebase, các mốc hardening quan trọng, những thuộc tính cấu hình thường gặp, dấu hiệu lỗi runtime và một quy trình kiểm thử migration an toàn.

## 1. Phân biệt JNDI, RMI và remote code loading

Ba khái niệm có liên hệ nhưng không đồng nghĩa.

### 1.1. JNDI là API tra cứu tên

**JNDI (Java Naming and Directory Interface)** cung cấp API để tra cứu đối tượng hoặc thông tin trong hệ thống naming/directory. Một ứng dụng có thể dùng JNDI để lấy cấu hình môi trường, dữ liệu từ LDAP, đối tượng được đăng ký trong RMI registry hoặc resource do application server cung cấp.

Ví dụ, trong một Java application server, ứng dụng có thể tra cứu `DataSource` do container cấu hình:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;

public class DataSourceLookup {
    public static DataSource lookup() throws Exception {
        Context context = new InitialContext();
        try {
            return (DataSource) context.lookup(
                "java:comp/env/jdbc/Orders"
            );
        } finally {
            context.close();
        }
    }
}
~~~

Đây là một ví dụ JNDI hợp lệ và phổ biến. Nó **không có nghĩa ứng dụng đang tải mã qua mạng**: resource có thể hoàn toàn do container quản lý tại chỗ.

Một ứng dụng khác có thể dùng `InitialDirContext` để đọc thuộc tính LDAP. Ý nghĩa của kết quả lookup phụ thuộc vào provider, loại object, cấu hình factory và đường xử lý tiếp theo.

### 1.2. Java RMI là cơ chế gọi method giữa các JVM

**Java Remote Method Invocation (RMI)** cho phép đối tượng trong một JVM gọi method được export bởi JVM khác. RMI định nghĩa hợp đồng `Remote` và dùng cơ chế stub/proxy, mạng, serialization để truyền tham số hoặc kết quả theo hợp đồng giao tiếp.

Ví dụ một interface dùng chung:

~~~java
package com.example.contract;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface GreetingService extends Remote {
    String greet(String name) throws RemoteException;
}
~~~

Client có thể tra cứu dịch vụ đã đăng ký trong RMI registry rồi gọi method. Việc tra cứu/gọi method này **không bắt buộc phải tải class Java từ một URL xa**: client và server có thể phân phối cùng interface cùng các lớp dữ liệu cần thiết thông qua artifact cài đặt sẵn.

### 1.3. Remote code loading là một khả năng khác

Trong các thiết kế RMI/JNDI lịch sử, thông tin tham chiếu có thể mang một **codebase URL** chỉ ra nơi lấy class mà JVM nhận chưa có sẵn. Một phía của kết nối có thể cung cấp thông tin về class và URL để phía kia xem xét tải class.

Điểm rủi ro là đối tượng đến từ hệ thống khác có thể ảnh hưởng tới **nguồn mã được nạp vào JVM**. Nếu URL hoặc class name bị kiểm soát bởi bên không đáng tin cậy, remote code loading có thể mở rộng đáng kể bề mặt tấn công.

Luồng khái niệm:

~~~text
Ứng dụng local
      |
      | JNDI lookup / RMI exchange
      v
Naming service / RMI peer
      |
      | tên class, metadata, object reference,
      | có thể kèm codebase trong thiết kế cũ
      v
JVM local
      |
      +--> Class có sẵn trong artifact local?
      |
      +--> Cơ chế cũ có thể xét codebase URL từ xa
      |
      v
Dựng object / gọi method / xử lý dữ liệu
~~~

Các bản JDK mới đã giảm hoặc loại bỏ nhiều đường tải class từ xa. Tuy nhiên, **không được suy ra rằng việc chặn tải class từ URL đồng thời loại bỏ mọi rủi ro từ JNDI, object factory, serialized data hoặc RMI**.

| Khía cạnh | JNDI | RMI | Tải class từ codebase |
|---|---|---|---|
| Mục đích | Tra cứu tên, resource hoặc thông tin thư mục | Gọi method giữa các JVM | Lấy định nghĩa class chưa có sẵn |
| API tiêu biểu | `InitialContext`, `InitialDirContext` | `Remote`, `Registry`, `UnicastRemoteObject` | Cơ chế class loading/codebase của provider hoặc RMI |
| Có bắt buộc truy cập mạng? | Không; tùy provider | Thường có, trừ các cấu hình cục bộ | Phụ thuộc vị trí codebase |
| Có bắt buộc tải bytecode từ xa? | Không | Không | Có khi cơ chế đó được dùng và được cho phép |
| Rủi ro chính | Đầu vào lookup, kết quả, object factory, quyền truy cập | Authentication, mạng, serialization, class loading | Đưa code không đáng tin cậy vào JVM |

## 2. Vì sao chính sách thay đổi theo các bản JDK?

Trước đây Java cung cấp nhiều khả năng phân phối class động để hệ thống phân tán có thể trao đổi đối tượng linh hoạt. Theo thời gian, các nhà phát triển nền tảng nhận thấy việc để dữ liệu từ xa quyết định tải và thực thi code gây rủi ro nghiêm trọng, trong khi mô hình deploy hiện đại có thể cung cấp sẵn những class được phép.

Những thay đổi thường có các dạng:

- Chuyển giá trị mặc định của một property từ cho phép sang từ chối một đường tải mã từ xa.
- Giới hạn cách provider JNDI sử dụng URL codebase trong object reference.
- Không cho deserialize hoặc tái dựng một số loại dữ liệu/object từ LDAP nếu chưa được cho phép.
- Thêm bộ lọc để hạn chế loại object factory nào có thể được sử dụng.
- Loại bỏ hoàn toàn một đường remote code downloading hoặc property từng có thể bật lại nó.
- Loại bỏ các cơ chế cũ như RMI Activation hay giảm phụ thuộc vào Java Security Manager.

Không nên tự điền một bảng hành vi chỉ dựa trên **số phiên bản Java tính năng**. Bản cập nhật bảo mật của cùng một dòng JDK, vendor và build cụ thể cũng quan trọng. Nên kiểm tra release notes, tài liệu `java.naming`/RMI và cấu hình hiệu lực của runtime đang triển khai.

## 3. Những mốc lịch sử cần biết khi migration

### 3.1. RMI: `java.rmi.server.useCodebaseOnly` mặc định `true`

Trong các phiên bản Java cũ, RMI từng có cơ chế cho phép peer cung cấp URL phục vụ việc tải class. Property:

~~~text
java.rmi.server.useCodebaseOnly
~~~

đóng vai trò quan trọng trong chính sách này. Từ **JDK 7 Update 21**, giá trị mặc định được đổi thành `true`; tài liệu Oracle cũng ghi nhận sự thay đổi tương ứng ở một số nhánh cập nhật cũ như JDK 6 Update 45 và JDK 5 Update 45.

Ở giá trị `true`, RMI không tin dùng tùy ý URL codebase do phía bên kia cung cấp cho việc tải class theo cơ chế lịch sử. Điều này làm giảm khả năng một phía ép phía còn lại dùng mã ở địa chỉ ngoài dự kiến.

Các hệ thống đã biên dịch trước đó nhưng phụ thuộc vào việc phía từ xa cung cấp class có thể bắt đầu gặp lỗi dạng:

~~~text
java.rmi.UnmarshalException
    nested exception is:
        java.lang.ClassNotFoundException: ...
~~~

Điều cần làm không phải mặc định đổi property trở lại `false`. Khi đặt nó thành `false` trong những runtime còn hỗ trợ cơ chế tương ứng, rủi ro tải code không đáng tin cậy tăng lên. Hướng migration bền vững là **phân phối class/interface/DTO đáng tin cậy ở cả hai đầu kết nối** và quản lý phiên bản artifact.

### 3.2. JNDI LDAP/RMI: chính sách tin cậy codebase URL bị siết chặt

Các JDK đã dần thay đổi hành vi của JNDI providers khi xử lý reference chứa codebase URL. Hai property lịch sử cần nhận diện trong script và cấu hình là:

~~~text
com.sun.jndi.rmi.object.trustURLCodebase
com.sun.jndi.ldap.object.trustURLCodebase
~~~

Đây là các property cụ thể cho những cơ chế lịch sử của **JNDI RMI provider** và **JNDI LDAP provider**, không phải một cờ chung điều khiển mọi thư viện Java có thể gọi `URLClassLoader`.

Một hệ thống legacy có thể từng bật chúng để cho phép nhận object reference và tải class từ một URL ngoài môi trường triển khai. Các bản cập nhật JDK về sau đã chuyển sang mặc định thận trọng hơn.

Không nên lấy ví dụ cấu hình cũ trên Internet rồi khẳng định nó vẫn có tác dụng trên JDK hiện tại. Việc hỗ trợ và mặc định thay đổi theo thời gian; ở JDK 24, hai property này đã bị **loại bỏ**.

### 3.3. JDK 15 và JDK 17: thay đổi liên quan RMI legacy

Hai mốc khác cần phân biệt với việc tải class từ xa:

- **JDK 15:** công cụ biên dịch static stub `rmic` bị loại bỏ. Các hệ thống build cũ còn gọi `rmic` cần cập nhật quy trình; RMI vẫn tồn tại và thường dùng dynamic proxies/stubs theo cơ chế phù hợp.
- **JDK 17:** cơ chế **RMI Activation** bị loại bỏ theo JEP 407. Điều này không có nghĩa toàn bộ Java RMI bị loại bỏ. Các ứng dụng dùng `rmid` hoặc API activation cũ cần thay đổi cơ chế quản lý vòng đời remote object.

Hai thay đổi trên là vấn đề migration thực tế nhưng không phải bằng chứng rằng `Registry.lookup` thông thường hay mọi ứng dụng RMI đều ngừng hoạt động.

### 3.4. JDK 24: JNDI remote code downloading bị vô hiệu hóa vĩnh viễn

Đây là một mốc cần ghi thật rõ. Theo **JDK 24 Release Notes**, **remote code downloading của các JNDI LDAP và RMI providers bị vô hiệu hóa vĩnh viễn**. Cùng lúc, hai system property:

~~~text
com.sun.jndi.rmi.object.trustURLCodebase
com.sun.jndi.ldap.object.trustURLCodebase
~~~

đã bị loại bỏ. Do đó, **không thể dùng lại các property đó để bật chức năng remote code downloading của JNDI provider trong JDK 24**.

JDK 24 cũng loại bỏ JNDI environment property `java.naming.rmi.security.manager` từng được sử dụng để yêu cầu cài đặt `RMISecurityManager`. Điều này nằm trong quá trình loại bỏ vai trò của Security Manager khỏi nền tảng; JEP 486 đã vô hiệu hóa vĩnh viễn khả năng bật Java Security Manager trong JDK 24.

Ranh giới cần phân biệt:

- JDK 24 **không xóa JNDI API**; lookup các resource và directory entry hợp lệ vẫn là tính năng có thể sử dụng.
- JDK 24 **không xóa toàn bộ RMI**; gọi remote method dựa trên class được phân phối và cấu hình hợp lệ vẫn có thể hoạt động.
- Mốc này nói cụ thể về **tải mã từ xa qua JNDI LDAP/RMI providers**, không phải một khẳng định rằng mọi thư viện hoặc mọi `ClassLoader` của Java đều bị cấm tải dữ liệu qua mạng.
- Việc ngăn remote code downloading **không đồng nghĩa mọi kết quả lookup hoặc mọi object factory được tự động tin cậy**.

Nếu migration từ JDK cũ lên JDK 24 trở lên mà ứng dụng thực sự phụ thuộc vào tải class từ LDAP/RMI codebase, phải đổi kiến trúc: đưa các factory/class cần thiết vào các artifact local được quản lý hoặc thay cơ chế trao đổi đối tượng.

### 3.5. Bảng tóm tắt các mốc

| Mốc | Thay đổi liên quan | Hạng mục cần kiểm tra |
|---|---|---|
| JDK 7u21 và các bản cập nhật cũ tương ứng | `java.rmi.server.useCodebaseOnly` mặc định `true` | RMI client/server có dựa vào URL codebase từ peer không? |
| Các đợt hardening JNDI trong những bản cập nhật sau đó | Tin cậy URL codebase của JNDI LDAP/RMI bị giới hạn | Script có `trustURLCodebase` không; ứng dụng có cần remote class loading không? |
| JDK 15 | Loại bỏ `rmic` | Build còn tạo static stubs bằng công cụ cũ không? |
| JDK 17 | Loại bỏ RMI Activation | Có dùng `rmid` hoặc activation API không? |
| JDK 24 | JNDI LDAP/RMI remote code downloading bị vô hiệu hóa vĩnh viễn; xóa hai `trustURLCodebase` properties | Thay phụ thuộc tải class từ URL bằng class/factory cài sẵn |
| JDK 24 | Xóa `java.naming.rmi.security.manager`; Security Manager không thể bật lại | Loại bỏ cách cấu hình sandbox dựa trên cơ chế cũ |

Bảng này là những mốc trọng tâm để điều tra, không thay thế tài liệu chính thức của **đúng bản JDK, bản cập nhật và vendor**.

## 4. JNDI lookup không giống tải mã từ xa

Một lookup JNDI có thể trả về nhiều dạng kết quả tùy provider. Ví dụ, đọc attribute LDAP khác với việc yêu cầu JNDI tái dựng một Java object dựa trên `Reference`.

### 4.1. Tra cứu LDAP như dữ liệu thư mục

Ví dụ minh họa với kết nối LDAPS tới một directory thuộc quyền quản trị của tổ chức:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public class DirectoryReader {
    public Attributes readEntry(
            String ldapUrl,
            String bindDn,
            String password) throws Exception {

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, ldapUrl);
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, bindDn);
        env.put(Context.SECURITY_CREDENTIALS, password);
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        DirContext context = new InitialDirContext(env);
        try {
            return context.getAttributes(
                "uid=test-user,ou=people,dc=internal,dc=example",
                new String[] { "cn", "mail" }
            );
        } finally {
            context.close();
        }
    }
}
~~~

Giá trị `ldapUrl` trong triển khai cần được kiểm soát, ví dụ `ldaps://directory.internal.example:636`, với xác thực TLS phù hợp. Ví dụ chỉ minh họa đọc thuộc tính thư mục; không cố dựng đối tượng Java từ reference lạ hoặc tải class từ URL bên ngoài.

Trong production, tránh hard-code mật khẩu, ưu tiên cơ chế quản lý credentials an toàn và xác thực máy chủ directory. Việc dùng `ldaps://` không thay thế kiểm tra truststore và certificate identity.

### 4.2. Reference và object factory

JNDI có cơ chế `Reference` và `ObjectFactory`. Một reference có thể biểu diễn thông tin để một factory dựng lại đối tượng theo hợp đồng đã biết. Factory phù hợp có thể nằm **sẵn trong classpath/module path local**.

Đây là một chức năng khác với remote code downloading:

~~~text
JNDI lookup nhận Reference
        |
        v
Provider/JNDI xác định factory có phù hợp không
        |
        +--> Factory có sẵn local và được chính sách cho phép?
        |           |
        |           v
        |       Dựng object
        |
        +--> Cơ chế cũ muốn tải factory từ URL bên ngoài?
                    |
                    v
               Bị giới hạn / bị vô hiệu hóa
               theo JDK và provider
~~~

Khi JDK 24 chặn remote code downloading, một ứng dụng vẫn có thể dùng object factory **được cài sẵn và được phép**, tùy chính sách của JNDI provider. Điều này có nghĩa kiểm soát factory classes vẫn quan trọng: một server directory không đáng tin cậy có thể cố trả về thông tin khiến ứng dụng sử dụng một factory local không mong muốn.

### 4.3. Factory classes được chọn từ dữ liệu phía ngoài là ranh giới tin cậy

Một lỗi thiết kế là coi bất kỳ reference do naming server trả về cũng đủ đáng tin để tạo Java object. Trong kiến trúc an toàn, ứng dụng nên giới hạn:

- Naming/directory server nào được kết nối.
- Tên hoặc DN nào được tra cứu.
- Loại kết quả nào được chấp nhận.
- Factory nào được phép dựng object.
- Class nào được phép deserialize, nếu có.
- Quyền và mạng mà tiến trình ứng dụng được sử dụng.

Chính sách chặn tải class từ URL chỉ giải quyết **một** phần của chuỗi này.

## 5. Kiểm soát dựng object và deserialization trong JNDI LDAP

### 5.1. `com.sun.jndi.ldap.object.trustSerialData`

Trong JDK có thuộc tính này, `com.sun.jndi.ldap.object.trustSerialData` điều khiển một số đường **khôi phục đối tượng** trong JNDI LDAP provider. Tài liệu JDK 24 mô tả phạm vi gồm dữ liệu serialized trong `javaSerializedData`, tái dựng RMI reference từ `javaRemoteLocation` và một số binary reference addresses trong `javaReferenceAddress`.

Ở JDK 24, khi thuộc tính không được đặt, những đường tái dựng/deserialize được tài liệu liệt kê **không được cho phép** theo mặc định. Việc đặt thành `true` nới lỏng hành vi này; đó không phải cấu hình nên bật chỉ để “cho ứng dụng chạy lại”.

Một hiểu nhầm quan trọng: `trustSerialData` **không phải cùng một property** với `trustURLCodebase`.

| Thuộc tính/cơ chế | Điều gì được kiểm soát? | Cần hiểu đúng |
|---|---|---|
| `com.sun.jndi.ldap.object.trustURLCodebase` (lịch sử) | Tin cậy URL codebase cho JNDI LDAP remote class loading | Đã bị loại bỏ ở JDK 24; không thể dùng để bật lại cơ chế này |
| `com.sun.jndi.rmi.object.trustURLCodebase` (lịch sử) | Tin cậy URL codebase cho JNDI RMI remote class loading | Đã bị loại bỏ ở JDK 24 |
| `com.sun.jndi.ldap.object.trustSerialData` | Một số đường deserialization/reconstruction từ LDAP attributes | Rủi ro dữ liệu và object reconstruction; khác với tải class từ URL |
| `jdk.jndi.object.factoriesFilter` | Lọc object factory được phép dựng object từ JNDI reference | Có thể chặn factory local không được phép |
| `jdk.jndi.ldap.object.factoriesFilter` | Lọc bổ sung factory phía LDAP provider | Không nên coi cấu hình mặc định là chính sách allowlist ứng dụng |

Không sử dụng việc nới lỏng một bộ lọc để thay thế việc thiếu thư viện cục bộ, cũng không đặt các property chỉ dựa vào stack trace mà chưa xác định dữ liệu thực tế đi qua provider nào.

### 5.2. Object factory filters

Các property như `jdk.jndi.object.factoriesFilter` và `jdk.jndi.ldap.object.factoriesFilter` hỗ trợ giới hạn những object factory nào có thể được dùng để tạo đối tượng từ reference.

Chúng có thể áp dụng biểu thức lọc theo cú pháp pattern tương tự cơ chế serialization filtering, nhưng **không được đồng nhất hoàn toàn** với bộ lọc deserialize object graph. Đối với LDAP provider, chính sách của provider và bộ lọc toàn cục có thể cùng tham gia quyết định.

Một chính sách minh họa theo ý tưởng:

~~~text
Cho phép factory thuộc package nội bộ đã kiểm kê
Từ chối factory ngoài danh sách đó
Không tự bật lại bất kỳ remote codebase download nào
~~~

Trong triển khai thật, cần đọc tài liệu cụ thể của JDK đang dùng để khai báo cú pháp lọc và xác nhận kết quả bằng integration test. Tránh sao chép một filter có vẻ chặt nhưng vô tình chặn factory hợp lệ hoặc cho phép factory không nằm trong inventory.

### 5.3. Serialization filtering cho RMI và những luồng object khác

RMI thường dùng serialization để truyền tham số hoặc giá trị trả về. Rủi ro không chỉ nằm ở việc JVM có phải tải class từ mạng hay không: dữ liệu đã serialized có thể kích hoạt logic khi object được dựng lại, hoặc tạo object graph lớn gây ảnh hưởng tài nguyên.

JDK hỗ trợ các cơ chế `ObjectInputFilter` và cấu hình `jdk.serialFilter` giúp hạn chế những class, độ sâu, số lượng reference và dung lượng object graph được chấp nhận trong những đường deserialization phù hợp.

Ví dụ một chuỗi chính sách minh họa:

~~~text
maxdepth=20;maxrefs=1000;maxbytes=1048576;com.example.dto.*;!*
~~~

Đây **không phải** cấu hình có thể chèn máy móc vào mọi hệ thống: cần kiểm kê toàn bộ những kiểu dữ liệu thật sự được serialize, kiểm tra class được phép và thử cả luồng thành công lẫn luồng bị từ chối. Một bộ lọc quá hẹp có thể làm dữ liệu hợp lệ không deserialize được; một bộ lọc quá rộng lại không giải quyết đúng rủi ro.

## 6. RMI codebase và mô hình phân phối class

### 6.1. Vai trò lịch sử của `java.rmi.server.codebase`

Trong một số thiết kế RMI cũ, property `java.rmi.server.codebase` chứa URL liên quan đến cách tham chiếu remote object và việc tìm định nghĩa class. Cơ chế codebase có thể hỗ trợ bên nhận biết nơi lấy những class chưa có ở môi trường của mình.

Nhưng cách deploy hiện đại có thể tránh phụ thuộc cơ chế đó bằng cách phân phối:

- Remote interfaces dùng chung.
- DTO hoặc serializable value types được hai bên sử dụng.
- Những JAR của framework/proxy cần thiết cho runtime.
- Một tập phiên bản được kiểm thử, có khóa dependency rõ ràng.

Với `java.rmi.server.useCodebaseOnly=true`, không nên thiết kế ứng dụng dựa vào việc peer tùy ý quyết định URL nạp class. Không nên đặt `useCodebaseOnly=false` như phương án khắc phục mặc định; tài liệu Oracle cảnh báo thao tác này làm tăng rủi ro remote code loading trong những runtime còn hỗ trợ.

### 6.2. Ví dụ client RMI không cần tải mã từ xa

Giả sử cả client lẫn server đều được cung cấp sẵn cùng interface `GreetingService` trong artifact đã kiểm soát:

~~~java
package com.example.client;

import com.example.contract.GreetingService;
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public class GreetingClient {
    public static void main(String[] args) throws Exception {
        Registry registry = LocateRegistry.getRegistry(
            "rmi.internal.example", 1099
        );

        GreetingService service =
            (GreetingService) registry.lookup("GreetingService");

        System.out.println(service.greet("Java"));
    }
}
~~~

Mã minh họa giả định server và registry đã được cấu hình bởi người quản trị. Kết nối RMI có thể đòi hỏi cổng khác cổng registry tùy cách export remote object. Việc dùng host trong miền `.example` chỉ làm ví dụ, không phải endpoint hoạt động.

Trong triển khai thật, RMI giữa các máy không đáng tin phải có biện pháp xác thực, mã hóa và kiểm soát mạng phù hợp. Giao thức không nên được phơi bày công khai chỉ vì client có thể gọi `Registry.lookup`.

### 6.3. RMI hoạt động nhưng vẫn lỗi vì DTO thay đổi

Một hệ thống có thể không tải code từ xa nhưng vẫn gặp lỗi tương thích nếu bên gửi/bên nhận dùng phiên bản DTO khác nhau. Các trường hợp gồm:

- Class không nằm trên runtime classpath ở phía nhận.
- Thay đổi `serialVersionUID` hoặc serialized form không tương thích.
- Một field chứa kiểu phụ thuộc mà phía nhận chưa cài.
- Interface hoặc method signature thay đổi.
- Serialization filter từ chối kiểu hoặc kích thước object graph.
- Module hoặc class loader khiến kiểu không truy cập/ép kiểu được.

Đừng gộp tất cả thành “JDK chặn RMI”. Cần xem lớp lỗi cụ thể và nguyên nhân sâu trong stack trace.

## 7. Các dạng lỗi thường thấy sau khi nâng JDK

| Triệu chứng | Bối cảnh có thể gặp | Hướng điều tra |
|---|---|---|
| `ClassNotFoundException` lồng trong `UnmarshalException` | RMI nhận dữ liệu tham chiếu đến class chưa có local | Classpath phía nhận, version DTO/stub, codebase expectation |
| `NamingException` / `ConfigurationException` | JNDI provider hoặc resource cấu hình không đúng | Provider URL, factory, DNS/network, cấu hình JNDI |
| `NameNotFoundException` | Tên lookup không tồn tại trong naming directory | Namespace, DN, context, môi trường |
| `ServiceConfigurationError` hoặc lỗi factory | Provider/factory được chọn không hợp lệ hoặc không tạo được object | Metadata, factory class local, filter và version |
| `ClassCastException` | Lookup trả về object khác hợp đồng mong đợi | Runtime type, class loader và version API |
| `InvalidClassException` | Serialized form không tương thích hoặc bị filter từ chối theo cơ chế phù hợp | `serialVersionUID`, DTO, filter, cause |
| `ClassNotFoundException` trong object reconstruction | Provider cố tạo class không tồn tại local | Xem JNDI factory/reference và packaging |
| `NoSuchMethodException` / `IllegalAccessException` | Local factory thiếu constructor/method hoặc không đủ quyền | API, reflection, module `exports`/`opens` |
| Kết quả lookup bị từ chối nhưng kết nối LDAP vẫn thành công | Chính sách provider chặn reconstruction/factory | Phân biệt directory query thành công với dựng object thất bại |
| Lỗi khởi động `rmid`/`rmic` | Ứng dụng cũ phụ thuộc công cụ/cơ chế đã loại bỏ | Mốc JDK 15/17, migration build/lifecycle |
| `SSLHandshakeException` | TLS/certificate/hostname mismatch | Truststore, cipher suites, certificate chain |

Thông điệp thực tế có thể khác theo vendor, provider và đường code. Quan trọng là đọc **chuỗi `Caused by`** và xác định bước thất bại: kết nối, tra cứu tên, chọn factory, nạp class, deserialize, gọi method hay logic nghiệp vụ.

### 7.1. Ví dụ phân biệt lỗi tra cứu và lỗi dựng object

~~~text
Bước 1: Kết nối tới LDAP server
        |
        +-- Không kết nối / TLS lỗi --> network/SSL
        |
        v
Bước 2: Tra cứu DN và đọc attributes
        |
        +-- Tên không tồn tại --> NameNotFoundException
        |
        v
Bước 3: Giải thích kết quả như Java object
        |
        +-- Factory local không có --> factory/classpath
        +-- Filter từ chối --> chính sách JNDI
        +-- Remote codebase bị chặn --> thay kiến trúc
        +-- Serialized data bị từ chối --> trustSerialData/filter
        |
        v
Bước 4: Dùng object
        |
        +-- ClassCast/API mismatch --> hợp đồng kiểu/phiên bản
        v
Thành công
~~~

Nếu chỉ thấy `NamingException` ở lớp ngoài, hãy mở cause gốc để không nhầm lỗi chính sách với lỗi mạng.

## 8. Trường hợp migration thường gặp

### 8.1. Ứng dụng JNDI legacy trước đây dựng object từ URL codebase

**Trước nâng cấp:** một naming service trả về reference có thông tin class factory và URL; JVM cũ có cấu hình cho phép một cơ chế tải code từ xa.

**Sau nâng cấp:** property tin cậy URL có thể đã đổi mặc định hoặc ở JDK 24 bị loại bỏ. Lookup không còn được phép tải factory qua JNDI remote code downloading, nên một luồng trước đây chạy được có thể bị từ chối.

**Cách xử lý bền vững:** xác định factory thuộc nhà phát triển nào, kiểm tra độ tin cậy, đóng gói nó vào artifact local, áp dụng factory filters và thử lookup với dữ liệu đã biết. Nếu directory server có thể bị kiểm soát từ ngoài, phải giới hạn đường tạo object và nguồn dữ liệu.

Không nên đề xuất bật lại `trustURLCodebase=true` trên JDK 24 vì nó đã không còn là một cơ chế được hỗ trợ để khôi phục tải code từ xa.

### 8.2. RMI server/client chia sẻ object type không đầy đủ

**Trước nâng cấp:** một môi trường cũ có thể dựa vào remote codebase để bổ sung class thiếu trên client.

**Sau nâng cấp:** phía nhận không còn chấp nhận codebase từ peer theo chính sách mặc định, hoặc đã chuyển sang một cấu hình chặt hơn; unmarshalling thất bại.

**Cách xử lý:** công bố contract JAR và DTO JAR tương thích, cài trên hai đầu kết nối, kiểm tra serialized form và chạy cùng bộ integration test trên runtime mục tiêu. Không dùng URL từ peer như hệ thống phân phối artifact ngầm.

### 8.3. Nâng JDK nhưng không đổi application server

Một application server hoặc thư viện middleware cũ có thể có code phụ thuộc RMI Activation, static stub compiler, Security Manager hoặc những property nội bộ của JNDI. Khi JDK thay đổi, vấn đề có thể nằm ở **framework được đóng gói bên dưới** chứ không ở source nghiệp vụ.

Hướng xử lý là đọc support matrix của server/framework, nâng phiên bản được vendor hỗ trợ và kiểm thử resource lookup/RMI trên đúng runtime target. Chỉ sửa JVM flags không làm một API hoặc tool đã bị loại bỏ xuất hiện trở lại.

### 8.4. LDAP lookup vẫn trả dữ liệu nhưng object factory không hoạt động

Một directory query trả về attributes thành công không chứng minh ứng dụng vẫn dựng được mọi Java object từ attributes đó. JDK có thể hạn chế một số đường reconstruction hoặc filter factory.

Nếu mục đích thực tế chỉ là lấy thông tin người dùng, nhóm nên cân nhắc chuyển sang **đọc và ánh xạ dữ liệu LDAP một cách tường minh** thay vì để directory entry quyết định class/factory bất kỳ.

### 8.5. Ứng dụng dùng JMX qua RMI

JMX remote connector có thể dùng RMI ở tầng vận chuyển. Khi nâng JDK, cần phân biệt vấn đề của JMX, TLS, authentication, serialization và các thành phần quản lý đã bị deprecated/removed với việc tải mã JNDI từ LDAP/RMI codebase.

Không nên mở rộng RMI hoặc JMX ra mạng công cộng không kiểm soát. Với quản trị từ xa, cần giới hạn interface/cổng, xác thực và TLS theo khả năng của stack được hỗ trợ.

## 9. Chính sách bảo mật phù hợp cho ứng dụng hiện đại

### 9.1. Không tải class từ nguồn do đối tác cung cấp tùy ý

Thay việc nhận codebase URL rồi nạp class bằng phân phối artifact có phiên bản, chữ ký/kiểm tra nguồn, dependency lock và quy trình phát hành. Nếu sản phẩm thực sự cần plugin động, dùng registry plugin tin cậy, xác thực artifact, danh sách cho phép, giới hạn quyền và quy trình kiểm thử riêng.

Việc tải class từ một URL không đáng tin không phải chức năng cần bật lại chỉ để đạt tương thích hành vi với bản JDK cũ.

### 9.2. Không dùng kết quả JNDI như đầu vào thực thi code không giới hạn

Đầu vào JNDI như provider URL, tên lookup, DN, attribute và reference nên được kiểm soát theo mục đích. Đặc biệt, không đưa trực tiếp URL hoặc tên do người dùng bất kỳ cung cấp vào các luồng lookup có khả năng dựng object, gọi factory hoặc kết nối đến host tùy ý.

Thực hành phù hợp:

- Sử dụng danh sách naming/directory endpoints đáng tin.
- Giới hạn network egress đến những endpoint cần thiết.
- Xác thực TLS cho LDAP và các giao thức liên quan.
- Dùng quyền truy cập tối thiểu đối với account tra cứu.
- Chỉ đọc những object types/attributes thật sự cần.
- Sử dụng object factory filters/serialization filters phù hợp.
- Ghi log đủ để điều tra nhưng không lộ credentials, token hay dữ liệu nhạy cảm.

### 9.3. Bảo vệ RMI bằng mạng, authentication và TLS

RMI không tự động trở thành một giao thức an toàn chỉ vì remote code loading bị hạn chế. Cần đánh giá:

- Đối tượng nào được export và ai có thể gọi.
- Remote registry và service ports có thể truy cập từ đâu.
- Có cần TLS và xác thực hai chiều hoặc cơ chế xác thực phù hợp không.
- Có kiểm soát những kiểu dữ liệu được deserialize không.
- Có giới hạn kích thước, độ sâu và tài nguyên không.
- Có giám sát lỗi unmarshalling và bất thường kết nối không.

Java cung cấp `SslRMIClientSocketFactory` và `SslRMIServerSocketFactory` cho một số cấu hình RMI sử dụng SSL/TLS. Cần thiết kế truststore/keystore và cách kết nối ở cả client/server, không chỉ thêm tên factory vào source rồi cho rằng giao tiếp đã an toàn.

### 9.4. Không dựa vào Security Manager như ranh giới bảo vệ hiện đại

Security Manager là một cơ chế legacy; trong JDK 24 không thể bật lại nó. Nếu hệ thống trước đây dựa vào policy file và Security Manager để chạy code tải từ xa trong một “sandbox”, không nên xem việc chuyển JDK chỉ là chuyển property tương ứng.

Cần thay bằng ranh giới bảo vệ phù hợp kiến trúc: tiến trình riêng, container, sandbox của hệ điều hành, network policy, quyền truy cập tối thiểu và kiểm soát provenance của artifact. Những lớp bảo vệ này cũng cần được kiểm thử theo mô hình đe dọa của hệ thống.

## 10. Kiểm kê phụ thuộc trước khi đổi JDK

### 10.1. Tìm trong source, config và script

Có thể bắt đầu bằng các từ khóa sau trong repository và cấu hình triển khai:

~~~text
javax.naming
InitialContext
InitialDirContext
Context.PROVIDER_URL
ObjectFactory
Reference
ServiceLoader
Registry.lookup
LocateRegistry
UnicastRemoteObject
RMISecurityManager
java.rmi.server.codebase
java.rmi.server.useCodebaseOnly
trustURLCodebase
trustSerialData
jdk.jndi.object.factoriesFilter
jdk.jndi.ldap.object.factoriesFilter
jdk.serialFilter
rmic
rmid
java.security.manager
~~~

Dùng tìm kiếm văn bản trong source, resources, Dockerfile, shell scripts, YAML/Helm values, file cấu hình runtime và ứng dụng quản lý deployment. Các dependency ngoài repository cũng có thể mang theo cấu hình JNDI/RMI.

Không nên kết luận “không dùng” chỉ vì source ứng dụng không import `javax.naming` hoặc `java.rmi`; application server, framework và monitoring connector có thể gọi chúng gián tiếp.

### 10.2. Dùng dependency inventory và phân tích bytecode

`jdeps` giúp tìm các phụ thuộc tĩnh tới API/module Java, nhưng không phát hiện đầy đủ class name, URL hoặc factory chỉ nằm trong chuỗi cấu hình. Vì vậy, kết hợp:

- Dependency tree của build tool.
- Phân tích JAR thực tế với `jdeps` và `jar --list`.
- Tìm kiếm property, XML, YAML, JSON, service descriptors.
- Inventory của container images và middleware.
- Log runtime khi code thực sự lookup hoặc gọi remote object.

Mục đích không phải chỉ để loại bỏ một cờ JVM, mà để tìm **đường tin cậy**: dữ liệu xuất phát ở đâu, JVM nào nhận nó, rồi cơ chế gì biến dữ liệu đó thành Java object.

### 10.3. Phân loại theo mức rủi ro và tác động

| Phụ thuộc được phát hiện | Phân loại | Hướng ưu tiên |
|---|---|---|
| JNDI lookup resource local do container đăng ký | Cơ chế thông thường | Kiểm tra provider/resource trên server mới |
| LDAP query chỉ đọc attributes đã định nghĩa | Tích hợp directory | Test TLS, authentication, query và dữ liệu |
| JNDI object reference dùng factory local | Tạo object từ reference | Kiểm kê factory, filter, thử lookup |
| JNDI tải factory từ URL codebase | Phụ thuộc legacy có rủi ro cao | Loại bỏ remote downloading, đóng gói factory local |
| RMI dùng contract/DTO JAR cài sẵn | RPC phân tán | Test API, version, TLS, serialization |
| RMI mong peer cung cấp URL tải class | Phụ thuộc legacy có rủi ro cao | Phân phối contract JAR tin cậy |
| RMI Activation hoặc `rmic` | API/tool legacy đã thay đổi hoặc bị xóa | Nâng middleware, sửa lifecycle/build |
| JNDI LDAP cho phép deserialization/reconstruction từ directory ngoài | Đường dữ liệu nhạy cảm | Đánh giá trust boundary, filters và phương án thay thế |
| JMX/RMI remote management | Quản trị từ xa | Kiểm tra authentication, TLS, network exposure |

## 11. Xây dựng kế hoạch kiểm thử migration

Không nên chỉ kiểm tra ứng dụng có khởi động thành công. Những tính năng như JNDI factory, LDAP mapping hoặc RMI DTO có thể chỉ được kích hoạt ở một nhánh nghiệp vụ ít dùng.

### Bước 1: Ghi rõ môi trường nguồn và đích

Thu thập:

- JDK feature/update/build và vendor ở cả hai đầu RMI.
- Phiên bản application server, framework và directory provider.
- Runtime JVM arguments và system/security properties.
- Những JAR contract, factory, DTO và plugin được triển khai.
- Module path/classpath, class loader và container image.
- Cấu hình network, TLS, credentials và naming endpoints.

Các JDK patch-level khác nhau có thể áp dụng mặc định an toàn khác nhau; khi cần thiết phải kiểm tra trực tiếp trên build sẽ triển khai.

### Bước 2: Kiểm tra các chính sách hiệu lực

Đọc JDK release notes, migration guide và tài liệu module `java.naming` tương ứng. Xác định các property có còn được hỗ trợ không và mặc định đang là gì.

Có thể xem một số system properties được khai báo bằng cách kiểm tra startup scripts hoặc log cấu hình đã được kiểm duyệt. Chỉ biết một property có mặt trên command line chưa chứng minh JDK hiện tại vẫn sử dụng nó.

Đặc biệt với JDK 24, không được xem `trustURLCodebase` là cơ chế phục hồi JNDI remote code downloading.

### Bước 3: Chạy kiểm thử JNDI theo từng kiểu kết quả

| Test | Kết quả cần xác nhận |
|---|---|
| Tra cứu resource local có sẵn | Kết quả đúng kiểu, không tải code ngoài |
| LDAP lookup attributes thông thường | Kết nối bảo mật, dữ liệu chính xác |
| JNDI reference dùng factory local đã cho phép | Tạo object thành công từ class cài sẵn |
| Reference chỉ phụ thuộc vào class không cài local | Bị từ chối theo thiết kế, không tự tải URL ngoài |
| Factory ngoài allowlist | Bị filter từ chối; ghi nhận lỗi phù hợp |
| Dữ liệu serialized/reconstruction không được tin cậy | Không được khôi phục nếu chính sách cấm |
| Sai/thiếu naming entry | Lỗi được xử lý mà không gây tác động lan rộng |

Những trường hợp bị từ chối nên được test trong **môi trường cô lập, với dữ liệu mẫu lành tính**, không cần dùng mã khai thác hoặc endpoint không tin cậy thật.

### Bước 4: Chạy kiểm thử RMI trên đúng classpath

Dùng contract/DTO artifacts mà client và server dự kiến triển khai. Chạy test:

1. Tra cứu registry.
2. Gọi remote method cơ bản.
3. Truyền và nhận DTO thật sự được dùng.
4. Xử lý lỗi timeout hoặc mất kết nối.
5. Kiểm tra TLS/authentication.
6. Kiểm tra serialization filter.
7. Xác nhận client không cần tải code từ URL do peer chỉ định.

Nếu cần hỗ trợ nhiều phiên bản JDK, test những cặp runtime nằm trong support matrix, không chỉ Java version của máy phát triển.

### Bước 5: Thử trong môi trường giống production

Một thử nghiệm cục bộ có thể không phát hiện lỗi do firewall, cổng RMI được export khác registry port, truststore, URL DNS hoặc class loader của application server. Hãy dùng image, startup flags và topology tương đương production; cấu hình đầu vào phải được quản lý và kiểm soát.

### Bước 6: Ghi lại bằng chứng

Một báo cáo nên có:

| Trường | Ví dụ thông tin |
|---|---|
| Feature | JNDI LDAP user lookup |
| Source runtime | JDK cũ + vendor + build |
| Target runtime | JDK mới + vendor + build |
| Provider | LDAP / JNDI RMI / application server |
| Trust boundary | Directory endpoint hoặc RMI peer |
| Legacy behavior | Có/không phụ thuộc remote codebase |
| Security config | Factory filter, serial filter, TLS |
| Observed result | Thành công, bị chặn đúng chính sách, hoặc lỗi |
| Mitigation | Cài factory local, cập nhật DTO, nâng framework |
| Owner | Nhóm quản lý integration |
| Evidence | Stack trace, test report, logs đã loại dữ liệu nhạy cảm |

Mục tiêu là xác nhận **cơ chế hợp lệ còn hoạt động** và **cơ chế tải code không an toàn không bị bật lại vô tình**.

## 12. Ví dụ migration: loại bỏ phụ thuộc vào remote factory

Giả sử một dịch vụ sử dụng LDAP như nơi lưu cấu hình. Thiết kế cũ trả về một Java object reference trỏ đến factory class chưa được cài trong ứng dụng, kèm một remote codebase location.

Trước migration:

~~~text
Directory entry
    |
    +--> Tên factory class
    +--> Thông tin remote codebase
    |
    v
JNDI provider (runtime cũ / cấu hình legacy)
    |
    v
Có thể cần tải class từ URL ngoài
~~~

Sau migration, thay hợp đồng bằng một trong hai hướng rõ ràng:

**Hướng A – dùng LDAP như nguồn dữ liệu.** Directory entry chứa attributes đã có schema và ứng dụng ánh xạ chúng thành DTO qua code local. Không để LDAP quyết định class hay nơi tải code.

**Hướng B – dùng factory cài sẵn.** Nếu thật sự cần `ObjectFactory`, factory thuộc JAR đã được kiểm kê và phân phối cùng ứng dụng. Naming service chỉ trả dữ liệu reference trong phạm vi cho phép; một filter giới hạn factory được phép.

~~~text
Artifact đã kiểm soát
    |
    +--> Contract JAR
    +--> Factory JAR local
    +--> DTO / schema
    |
    v
JVM runtime
    |
    | JNDI lookup đến directory được phép
    v
Reference / attributes được kiểm tra
    |
    | Không tải class từ remote URL
    v
Factory local đã được phép
    |
    v
DTO / resource đúng hợp đồng
~~~

Cả hai hướng đều cần test logic nghiệp vụ và quyền truy cập. Lợi ích là loại bỏ mối phụ thuộc ngầm vào một URL chứa bytecode mà hệ thống khác kiểm soát.

## 13. Ví dụ migration: giữ RMI nhưng loại bỏ codebase động

Giả sử hệ thống có hai JVM, service A cung cấp remote method và service B gọi nó. Thiết kế cũ từng để B nhận những class chưa có từ codebase của A.

Mô hình mới:

- Tạo module/JAR hợp đồng riêng chứa `Remote` interface và DTO.
- Client và server cùng phụ thuộc vào một phiên bản contract tương thích.
- Đóng gói artifact vào image hoặc môi trường cài đặt đáng tin.
- Giữ chính sách `java.rmi.server.useCodebaseOnly=true` theo khuyến nghị của JDK hỗ trợ.
- Bảo vệ RMI bằng TLS, xác thực và phân đoạn mạng.
- Áp dụng serialization filtering thích hợp.
- Chạy test truyền/nhận dữ liệu trên những cặp JDK được hỗ trợ.

Nếu một interface hoặc DTO thay đổi không tương thích, việc không dùng remote code loading không giải quyết được lỗi API hay serialized form. Cần xử lý versioning của contract như mọi hợp đồng phân tán khác.

## 14. Một số hiểu nhầm phổ biến

**“JNDI là chức năng nguy hiểm nên phải xóa toàn bộ.”** Không. JNDI lookup resource local hoặc LDAP attributes vẫn có ứng dụng hợp lệ. Rủi ro nằm ở cách chọn endpoint, tin cậy kết quả, dựng Java object hoặc tải code.

**“Nếu JDK không tải class từ URL nữa thì mọi lookup đều an toàn.”** Không. Factory local, deserialization, query input, credentials và network trust vẫn cần chính sách riêng.

**“JNDI và RMI là một giao thức.”** Không. JNDI là API naming/directory; RMI là cơ chế gọi method giữa JVM. JNDI có thể dùng RMI provider nhưng hai khái niệm không tương đương.

**“`java.rmi.server.useCodebaseOnly` và `trustURLCodebase` là cùng một flag.”** Không. Chúng thuộc những cơ chế và phạm vi khác nhau; không nên đánh đồng chính sách RMI codebase với JNDI LDAP/RMI provider.

**“Đặt `trustURLCodebase=true` vẫn bật được JNDI remote code download ở JDK 24.”** Không. Hai thuộc tính JNDI LDAP/RMI `trustURLCodebase` đã bị loại bỏ ở mốc đó.

**“Nếu một ứng dụng RMI lỗi trên JDK 17 nghĩa là RMI đã bị xóa.”** Không. RMI Activation bị loại bỏ; RMI thông thường vẫn tồn tại.

**“`rmic` bị xóa nên không thể tạo RMI stub.”** Không. RMI dùng cơ chế stub/proxy phù hợp trong những phiên bản hiện đại; cần cập nhật build và tránh phụ thuộc tool cũ.

**“Bật `trustSerialData` chỉ làm LDAP đọc thêm vài thuộc tính.”** Không. Thuộc tính liên quan đến những đường khôi phục Java object từ dữ liệu LDAP; việc nới lỏng cần đánh giá rủi ro nghiêm túc.

**“Bỏ Security Manager thì dùng lại một policy file tương đương là được.”** Không. JDK 24 không cho bật lại Security Manager; cần thiết kế ranh giới bảo vệ bằng cơ chế hiện đại.

**“Có đủ JAR trên classpath là đã bảo đảm tích hợp.”** Không. Serialization compatibility, factory filter, module access, authentication, TLS và logic runtime đều có thể gây thất bại.

**“Chỉ cần test startup.”** Không. Nhiều JNDI lookup và RMI call chỉ xảy ra khi user mở một chức năng, vào nhánh dự phòng hoặc thực hiện workflow ít dùng.

## 15. Checklist khi nâng cấp hệ thống dùng JNDI/RMI

- [ ] Đã xác định JDK nguồn/đích, vendor và số build đầy đủ.
- [ ] Đã biết những JNDI providers nào đang được sử dụng: local, LDAP, RMI hoặc custom.
- [ ] Đã kiểm kê `InitialContext`, object factories, reference data và nguồn cấu hình.
- [ ] Đã xác nhận có hay không phụ thuộc vào remote codebase URL.
- [ ] Đã kiểm tra các property `useCodebaseOnly` và `trustURLCodebase` lịch sử theo đúng phiên bản.
- [ ] Nếu đích từ JDK 24 trở lên, đã loại bỏ giả định có thể bật lại JNDI LDAP/RMI remote code downloading.
- [ ] Đã kiểm tra `trustSerialData` và object factory filters theo tài liệu của provider.
- [ ] Đã đánh giá serialization filters cho RMI/luồng deserialize liên quan.
- [ ] Đã loại bỏ phụ thuộc vào `rmic` hoặc RMI Activation nếu đang nâng qua mốc loại bỏ.
- [ ] Đã đánh giá mọi giả định cũ về Security Manager.
- [ ] Đã cài sẵn contract JAR, DTO và factory cần thiết từ nguồn đáng tin.
- [ ] Đã kiểm tra TLS, credentials, truststore, registry/service ports và network policy.
- [ ] Đã thử lookup thành công, trường hợp factory bị từ chối và dữ liệu không hợp lệ.
- [ ] Đã thử RMI DTO marshalling/unmarshalling giữa các runtime mục tiêu.
- [ ] Đã kiểm thử trên môi trường cùng class loader/module path như production.
- [ ] Đã ghi lại các thay đổi hành vi được chấp nhận và cách rollback hoặc khắc phục.

## 16. Tài liệu chính thức để đối chiếu

Các nguồn sau cung cấp căn cứ cho những mốc và nguyên tắc được trình bày:

- [Oracle JDK 24 Release Notes](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html): phần thay đổi `JNDI Remote Code Downloading Is Permanently Disabled`, loại bỏ property `java.naming.rmi.security.manager` và các mục bảo mật liên quan.
- [JDK 24 Migration Guide – Removed Tools and Components](https://docs.oracle.com/en/java/javase/24/migrate/removed-tools-and-components.html): danh sách thay đổi bị loại bỏ và những vấn đề tương thích khi nâng cấp.
- [Java SE 24 `java.naming` module](https://docs.oracle.com/en/java/javase/24/docs/api/java.naming/module-summary.html): những property, object factory filters và chính sách LDAP provider được tài liệu hóa.
- [Java RMI Guide – JDK 21](https://docs.oracle.com/en/java/javase/21/rmi/): nguyên tắc bảo vệ RMI, serialization filtering, `useCodebaseOnly` và TLS.
- [Oracle RMI Enhancements in JDK 7](https://docs.oracle.com/javase/7/docs/technotes/guides/rmi/enhancements-7.html): lý do và ảnh hưởng của việc mặc định `useCodebaseOnly=true`.
- [JEP 407 – Remove RMI Activation](https://openjdk.org/jeps/407): phạm vi loại bỏ RMI Activation mà không xóa toàn bộ RMI.
- [JEP 486 – Permanently Disable the Security Manager](https://openjdk.org/jeps/486): diễn giải việc vô hiệu hóa cơ chế Security Manager ở JDK 24.

Khi làm migration trên JDK khác, hãy tra cứu release notes và Javadoc tương ứng với đúng bản feature/update/vendor mà production đang chạy. Không suy luận các mặc định của một JDK sang mọi JDK khác.

## 17. Kết luận

JNDI, RMI và remote code loading là các cơ chế có quan hệ nhưng phục vụ những mục đích khác nhau. JNDI giúp tra cứu tên và directory; RMI cho phép gọi method từ xa; tải class qua codebase là khả năng lịch sử để cung cấp code chưa có trong runtime. Những thay đổi bảo mật của JDK đã hạn chế hoặc loại bỏ nhiều đường nạp code từ phía bên ngoài, nổi bật là việc **JDK 24 vô hiệu hóa vĩnh viễn JNDI LDAP/RMI remote code downloading và xóa các `trustURLCodebase` properties tương ứng**.

Để migration thành công, không nên tìm cách khôi phục một cơ chế không an toàn chỉ vì ứng dụng legacy từng sử dụng nó. Hãy xác định các nguồn JNDI/RMI thật sự, phân phối contract và factory dưới dạng artifact local đáng tin, kiểm soát object reconstruction/deserialization, áp dụng TLS và giới hạn mạng, rồi kiểm thử cả luồng hợp lệ lẫn luồng bị từ chối. Kết quả cần đạt không chỉ là “ứng dụng chạy lại”, mà còn là **hành vi mới đúng hợp đồng và không làm suy yếu ranh giới tin cậy của hệ thống**.
