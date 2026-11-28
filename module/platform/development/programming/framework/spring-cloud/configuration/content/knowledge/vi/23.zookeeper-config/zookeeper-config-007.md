# ACL, xác thực và ranh giới với Zookeeper Service Discovery

Spring Cloud Zookeeper có thể dùng cùng một cụm ZooKeeper để lưu cấu hình và đăng ký dịch vụ. Hai chức năng này phục vụ mục đích khác nhau: Config đọc các znode chứa property của ứng dụng, còn Service Discovery đọc và đăng ký thông tin instance như tên dịch vụ, địa chỉ, port và trạng thái.

Dùng chung một cụm không có nghĩa hai vùng dữ liệu tự được cách ly. ZooKeeper kiểm soát quyền ở từng znode bằng **Access Control List (ACL)**. Ứng dụng cần xác thực để ZooKeeper gắn danh tính vào kết nối, sau đó ACL quyết định danh tính đó được đọc, ghi, tạo, xóa hoặc thay đổi quyền trên từng node hay không.

Bài học này trình bày mô hình ACL của ZooKeeper, các cơ chế xác thực, cách Spring Cloud Zookeeper cấu hình Curator client và cách tách quyền giữa cây **/config** và **/services**. Trọng tâm là giới hạn quyền theo workload, bảo vệ secrets và tránh để quyền Service Discovery mở đường truy cập cấu hình của ứng dụng khác.

Sau bài học, bạn có thể:

- Phân biệt authentication, authorization và TLS trong kết nối ZooKeeper.
- Giải thích năm quyền ACL và vì sao ACL không kế thừa xuống znode con.
- Chọn digest, SASL/Kerberos, x509 hoặc IP ACL theo yêu cầu triển khai.
- Cấu hình danh tính cho Curator client trong Spring Cloud Zookeeper.
- Phân tách quyền đọc cấu hình khỏi quyền đăng ký và khám phá dịch vụ.
- Thiết kế ACL riêng cho từng application, profile và vùng Service Discovery.
- Di chuyển ACL của znode hiện có mà không khóa nhầm quyền quản trị.
- Kiểm thử quyền được phép và bị từ chối trong môi trường staging.

## 1. Hai chức năng, hai vùng dữ liệu

Spring Cloud Zookeeper cung cấp hai integration độc lập:

- **Distributed Configuration:** đọc property từ cây cấu hình trong ZooKeeper và đưa chúng vào Spring Environment.
- **Service Discovery:** đăng ký thông tin instance và tìm các instance của dịch vụ khác.

Với cấu hình mặc định, Spring Cloud Zookeeper Config lưu dữ liệu dưới root **/config**. Service Discovery dùng root **/services**. Các root này là quy ước namespace, không tự tạo ranh giới bảo mật. Ranh giới chỉ có hiệu lực khi ACL trên các znode được cấu hình đúng.

~~~mermaid
flowchart TD
    ZK[("ZooKeeper ensemble")]
    ZK --> C["/config"]
    ZK --> S["/services"]

    C --> A["application"]
    C --> B["order-service"]
    C --> D["payment-service"]

    S --> E["order-service"]
    S --> F["payment-service"]

    A --> G["Cấu hình dùng chung"]
    B --> H["Cấu hình riêng order-service"]
    D --> I["Cấu hình riêng payment-service"]

    E --> J["Instance ID / host / port"]
    F --> K["Instance ID / host / port"]
~~~

Cây cấu hình thường có các context theo application và profile. Ví dụ ứng dụng order-service chạy profile prod có thể đọc các property source theo thứ tự cụ thể đến tổng quát:

1. config/order-service,prod
2. config/order-service
3. config/application,prod
4. config/application

Property source cụ thể hơn đứng trước. config/application có thể được nhiều ứng dụng đọc, vì vậy không đặt password hoặc token riêng của một service tại context dùng chung.

Service Discovery lưu metadata để client tìm dịch vụ. Metadata có thể gồm hostname, port, instance ID và thông tin bổ sung. Không đưa password, API key, private key hoặc dữ liệu bí mật vào metadata vì các client có quyền đọc service registry có thể nhìn thấy chúng.

Hai root riêng giúp tổ chức dữ liệu và thiết kế ACL theo chức năng. Tuy nhiên, nếu tất cả workload dùng cùng một danh tính ZooKeeper có quyền đọc cả hai root, việc tách path không ngăn workload đó đọc chéo dữ liệu.

## 2. Authentication, ACL và TLS

Ba cơ chế giải quyết ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Authentication** | Client là ai? | Digest user, Kerberos principal, X.509 certificate |
| **ACL / Authorization** | Danh tính đó được làm gì trên znode nào? | Được đọc config/order-service, không được ghi config/payment-service |
| **TLS** | Dữ liệu truyền qua mạng có được mã hóa và xác minh đầu bên kia không? | TLS client-server, mTLS |

Khi client xác thực thành công, ZooKeeper gắn các identity tương ứng với kết nối. Khi client thao tác trên znode, server so các identity đó với ACL của znode.

Gọi addAuthInfo hoặc authorization chỉ thêm thông tin xác thực vào kết nối. Thao tác này không tự thay ACL của node đã tồn tại và cũng không tự đặt ACL hạn chế cho node mới. Nếu znode vẫn có ACL mở, người không xác thực vẫn có thể truy cập theo quyền mà ACL mở cấp.

Một cài đặt ZooKeeper mới có thể khởi chạy mà chưa bật TLS, authentication hoặc ACL hạn chế. Apache ZooKeeper yêu cầu operator chủ động bật các kiểm soát này và khuyến nghị đặt ensemble trong mạng tin cậy, sau firewall. Không công khai cổng client của ZooKeeper ra Internet. Xem [Apache ZooKeeper Security](https://zookeeper.apache.org/security/).

## 3. Năm quyền ACL của ZooKeeper

ACL gắn với một znode gồm danh tính theo scheme và tập quyền được cấp cho danh tính đó.

| Quyền | Tác dụng |
|---|---|
| **READ** | Đọc dữ liệu của znode và liệt kê các znode con |
| **WRITE** | Thay đổi dữ liệu của chính znode |
| **CREATE** | Tạo znode con bên dưới znode hiện tại |
| **DELETE** | Xóa znode con bên dưới znode hiện tại |
| **ADMIN** | Đọc hoặc thay đổi ACL của znode |

CREATE và DELETE được tách riêng khỏi WRITE để cấp quyền chi tiết hơn. Ví dụ, một client có thể được phép cập nhật giá trị của znode hiện tại mà không được tạo hoặc xóa node con.

Cần chú ý phạm vi của CREATE và DELETE:

- Muốn tạo config/order-service, client cần CREATE trên node cha config.
- Muốn xóa config/order-service, client cần DELETE trên node cha config.
- Muốn sửa dữ liệu bên trong config/order-service, client cần WRITE trên chính node đó.
- Muốn liệt kê các ứng dụng con dưới config, client cần READ trên node config.
- Muốn thay ACL của config/order-service, client cần ADMIN trên chính node đó.

Một ứng dụng đọc cấu hình thường chỉ cần READ trên các node cấu hình và các node cha cần thiết để đi qua cây. Không cấp CREATE, DELETE hoặc ADMIN cho Config Client chỉ để ứng dụng có thể tải property.

## 4. ACL không kế thừa xuống znode con

Đây là quy tắc quan trọng nhất khi thiết kế quyền ZooKeeper: **ACL chỉ áp dụng cho đúng znode được gắn ACL đó**. ACL trên config không tự bảo vệ config/order-service, config/payment-service hoặc các node sâu hơn.

Ví dụ:

~~~text
/config                       ACL: chỉ config-admin được CREATE
/config/application           ACL: READ cho các ứng dụng được phép
/config/order-service         ACL: READ cho order-service, WRITE cho config-admin
/config/payment-service       ACL: READ cho payment-service, WRITE cho config-admin
~~~

Nếu config có ACL hạn chế nhưng config/order-service vẫn dùng ACL world:anyone, bất kỳ client nào có thể kết nối tới ZooKeeper đều có thể đọc node con đó. Quyền ở parent không tự che chắn child.

Ngược lại, nếu ACL của config không cho READ, client có thể không liệt kê được child dù biết chính xác đường dẫn. Vì vậy phải cấp đúng quyền trên cả node cha lẫn node chứa dữ liệu.

ACL cũng cần được đặt cho các node trung gian và node lá. Khi ứng dụng tạo cấu hình theo nhiều profile, mỗi znode phát sinh phải nhận policy phù hợp. Không chỉ kiểm tra ACL ở root rồi kết luận toàn cây đã an toàn.

## 5. Các scheme xác thực có sẵn

ZooKeeper hỗ trợ nhiều scheme cho identity. Scheme xác định cách danh tính được biểu diễn và đối chiếu trong ACL.

| Scheme | Identity | Khi phù hợp |
|---|---|---|
| **world** | world:anyone | Dữ liệu thực sự công khai; tránh dùng cho cấu hình nội bộ |
| **auth** | Danh tính đã xác thực trên kết nối | Dùng ACL gắn quyền cho identity đã xác thực, thường là creator |
| **digest** | Username/password | Môi trường nội bộ cần triển khai đơn giản; phải bảo vệ bằng TLS |
| **sasl** | Principal được xác thực qua SASL, thường là Kerberos | Hệ thống có hạ tầng Kerberos và danh tính workload |
| **x509** | X.500 principal từ client certificate | Kết nối TLS/mTLS với certificate riêng |
| **ip** | Địa chỉ IP nguồn | Lớp hạn chế mạng bổ sung, không nên là danh tính duy nhất |

### Digest

Digest dùng chuỗi username/password để xác thực client. Khi tạo ACL, identity được biểu diễn bằng digest tương ứng thay vì lưu password trực tiếp trong ACL.

Tuy nhiên, quá trình digest authentication truyền thông tin username/password trong dữ liệu xác thực. Digest không thay thế mã hóa đường truyền. Nếu dùng digest, bật TLS cho kết nối client-server và quản lý password như secret: cấp riêng cho từng workload, lưu trong secret manager, giới hạn quyền và rotation định kỳ.

### SASL/Kerberos

SASL cho phép ZooKeeper xác thực principal thông qua cơ chế SASL, thường là Kerberos/GSSAPI. Cách này phù hợp với hệ thống có Kerberos KDC, keytab và quy trình quản lý principal. Server và client phải cấu hình JAAS/SASL tương thích; ACL dùng scheme sasl với principal được xác thực.

Không chỉ bật SASL ở client rồi cho rằng server đã xác thực. Cần cấu hình provider và chính sách xác thực phía server, sau đó kiểm thử principal thực tế xuất hiện trong identity của session.

### X.509

Khi dùng secure client port với TLS client authentication, ZooKeeper có thể xác thực client certificate và tạo identity theo X.500 principal. ACL scheme x509 có thể giới hạn quyền theo đúng principal của certificate.

Certificate phải được cấp bởi CA đáng tin cậy, có thời hạn, được rotation và thu hồi theo quy trình. Cấu hình truststore/keystore và hostname verification phải được kiểm tra; TLS encryption mà không xác minh danh tính máy chủ vẫn có thể kết nối nhầm endpoint.

### IP ACL

IP ACL so địa chỉ nguồn của client với địa chỉ hoặc dải được khai báo. Nó hữu ích như một lớp giới hạn bổ sung trong mạng đã kiểm soát. Apache ZooKeeper cảnh báo IP ACL có thể bị giả mạo nếu mạng không ngăn source IP spoofing. Không dùng IP ACL thay thế authentication mạnh.

## 6. Scheme auth và quyền của creator

Scheme auth là cách thuận tiện để gắn ACL với danh tính đã xác thực trên kết nối hiện tại. Ví dụ, một client xác thực bằng digest rồi tạo node có ACL auth. ZooKeeper gắn ACL đó với identity đã xác thực thay vì lưu lại password dạng rõ.

Mô hình này hữu ích khi mỗi workload tự tạo znode riêng. Tuy nhiên, nếu một client có nhiều identity trên cùng session, cần hiểu identity nào được gắn với ACL và kiểm thử bằng đúng phiên bản ZooKeeper.

ZooKeeper cũng cung cấp ACL CREATOR_ALL_ACL, thường cấp toàn bộ quyền cho identity đã xác thực của creator. Cách này thuận tiện cho một node riêng của workload nhưng có thể quá rộng nếu creator không nên thay ACL hoặc xóa dữ liệu. Trong hệ thống cấu hình, thường nên cấp quyền writer rõ ràng và giữ ADMIN cho danh tính quản trị ACL.

Không dùng OPEN_ACL_UNSAFE trong production cho node cấu hình hoặc registry. ACL này cho world:anyone toàn bộ quyền trên node và có thể cho phép client không xác thực đọc, sửa, tạo hoặc xóa dữ liệu.

## 7. Cấu trúc quyền cho Config và Service Discovery

Hai chức năng cần các quyền khác nhau.

| Vai trò | /config | /services |
|---|---|---|
| Config Client của order-service | READ trên context dùng chung và context order-service được phép | Không cần quyền đăng ký dịch vụ nếu ứng dụng không dùng Discovery |
| Config Client của payment-service | READ trên context dùng chung và context payment-service được phép | Không cần quyền đăng ký dịch vụ nếu ứng dụng không dùng Discovery |
| Config publisher | CREATE/WRITE/DELETE theo quy trình phát hành; ADMIN ACL nếu được giao quản trị | Không cần quyền ghi registry |
| Service Discovery reader | Không cần đọc cấu hình | READ để liệt kê dịch vụ và instance |
| Service registrar | Không cần ghi cấu hình | CREATE/DELETE trên vùng đăng ký được giao; WRITE trên node instance do mình quản lý |
| ZooKeeper ACL administrator | ADMIN trên các znode thuộc phạm vi quản trị | ADMIN trên các znode thuộc phạm vi quản trị |

Một Config Client không nên được cấp quyền ghi /services chỉ vì ứng dụng có dependency Config. Một service registrar không cần quyền đọc /config/payment-service chỉ vì nó cần đăng ký hostname và port.

Service Discovery thường đăng ký thông tin instance bằng các znode ephemeral. Khi session client kết thúc, ZooKeeper tự loại ephemeral node. Client đăng ký cần quyền tạo node con dưới service path và quyền cập nhật/xóa theo cách Curator quản lý instance; client chỉ khám phá dịch vụ cần quyền đọc. Không cho một service registrar sửa hoặc xóa node của service khác nếu không có yêu cầu vận hành rõ ràng.

## 8. Cấu hình Spring Cloud Zookeeper Config và Discovery

Hai starter được dùng cho hai tính năng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

Dùng Spring Cloud BOM tương thích với Spring Boot để quản lý phiên bản. Nếu ứng dụng chỉ cần cấu hình tập trung, chỉ thêm Config starter; nếu cần đăng ký và khám phá service, thêm Discovery starter.

Ví dụ Config Data import cùng hai root tách biệt:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "zookeeper:"
  cloud:
    zookeeper:
      connect-string: "zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181"
      config:
        enabled: true
        root: config
        default-context: application
      discovery:
        enabled: true
        root: /services
~~~

Không có tiền tố optional: nghĩa là ứng dụng yêu cầu Zookeeper Config trong quá trình import; nếu không kết nối được, quá trình nạp cấu hình có thể thất bại. Nếu dùng optional:zookeeper:, ứng dụng cho phép bỏ qua nguồn này khi không khả dụng. Chọn chế độ theo yêu cầu an toàn: ứng dụng không thể chạy đúng nếu thiếu cấu hình bắt buộc thì nên fail fast.

Spring Boot Config Data sử dụng spring.config.import; không cần bootstrap.yml cho cách import này. Nếu dự án vẫn bật legacy bootstrap (spring-cloud-starter-bootstrap hoặc spring.cloud.bootstrap.enabled=true), cấu hình và customizer cần được đăng ký trong bootstrap phase theo tài liệu của release train đang dùng.

spring.cloud.zookeeper.config.root xác định root cấu hình; spring.cloud.zookeeper.config.default-context là context dùng chung. spring.cloud.zookeeper.discovery.root xác định root đăng ký dịch vụ. Thay root giúp tổ chức namespace nhưng không tự tạo ACL hoặc phân quyền.

## 9. Thêm authentication cho Curator client

Spring Cloud Zookeeper sử dụng Apache Curator để kết nối ZooKeeper. Với các phiên bản có **CuratorFrameworkCustomizer**, hãy tùy biến builder trước khi Curator client được tạo. Không thay thế bean CuratorFramework tự cấu hình chỉ để thêm credentials; điều đó có thể khiến auto-configuration lùi lại và làm mất cấu hình retry, connection hoặc namespace mặc định.

Ví dụ digest authentication:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.cloud.zookeeper.CuratorFrameworkCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ZookeeperAuthenticationConfiguration {

    @Bean
    CuratorFrameworkCustomizer digestAuthentication(Environment environment) {
        String username = environment.getRequiredProperty(
            "zookeeper.auth.username"
        );
        String password = environment.getRequiredProperty(
            "zookeeper.auth.password"
        );
        byte[] credentials = (username + ":" + password)
            .getBytes(StandardCharsets.UTF_8);

        return builder -> builder.authorization("digest", credentials);
    }
}
~~~

Username/password phải được cấp từ secret manager hoặc secret mount. Không commit password vào repository cấu hình dùng chung, không ghi credentials vào log và không dùng cùng một user cho tất cả workload nếu cần phân quyền theo ứng dụng.

authorization("digest", ...) chỉ thêm auth info vào Curator client. ACL trên znode vẫn phải được tạo hoặc cập nhật riêng. Với SASL/Kerberos hoặc X.509, cấu hình JAAS, certificate và secure client port theo tài liệu Apache ZooKeeper; không thay các cơ chế đó bằng một chuỗi digest.

### Khác biệt theo phiên bản Spring Cloud Zookeeper

Tài liệu nhánh 5.1 preview/snapshot hướng dẫn dùng **CuratorFrameworkCustomizer** để gọi CuratorFrameworkFactory.Builder.authorization(...). Tài liệu stable 5.0.2 vẫn trình bày ví dụ cũ dùng addAuthInfo trong bootstrap phase. API và bootstrap mechanism khác nhau theo phiên bản; hãy đối chiếu đúng release train của dự án và ưu tiên customizer nếu phiên bản đang dùng cung cấp API đó.

Nếu dùng legacy bootstrap, đăng ký customizer trong @BootstrapConfiguration được liệt kê trong META-INF/spring.factories để customizer tồn tại trước khi Curator client được tạo. Với Config Data import hiện đại, không thêm bootstrap chỉ để làm theo một ví dụ cũ nếu release hiện tại không yêu cầu.

## 10. Authentication không tự đặt ACL cho znode mới

Khi tạo znode, Curator cần một ACL provider để quyết định ACL gắn lên node. ACLProvider có hai phương thức chính:

- getDefaultAcl(): ACL mặc định cho path không có quy tắc riêng.
- getAclForPath(path): ACL áp dụng cho path cụ thể.

Nếu không cấu hình ACL provider phù hợp, Curator có thể sử dụng OPEN_ACL_UNSAFE làm ACL mặc định. Vì vậy, thêm digest credentials vào Curator client chưa đủ để bảo vệ các node do ứng dụng tạo.

Với Spring Cloud Zookeeper phiên bản hỗ trợ CuratorFrameworkCustomizer, có thể cấu hình ACL provider trên builder:

~~~java
@Bean
CuratorFrameworkCustomizer aclProviderCustomizer(ACLProvider pathAwareAclProvider) {
    return builder -> builder.aclProvider(pathAwareAclProvider);
}
~~~

pathAwareAclProvider là bean do ứng dụng triển khai theo chính sách của mình. Nó nên trả ACL khác nhau cho /config/**, /services/** và các path quản trị; không trả một danh sách ALL chung cho mọi znode.

Ví dụ skeleton cho provider theo path:

~~~java
public final class PathAwareAclProvider implements ACLProvider {

    @Override
    public List<ACL> getDefaultAcl() {
        return restrictedDefaultAcl();
    }

    @Override
    public List<ACL> getAclForPath(String path) {
        if (path == null) {
            return restrictedDefaultAcl();
        }

        if (path.equals("/config") || path.startsWith("/config/")) {
            return configAclFor(path);
        }

        if (path.equals("/services") || path.startsWith("/services/")) {
            return discoveryAclFor(path);
        }

        return restrictedDefaultAcl();
    }

    // Các phương thức dưới đây xây ACL theo principal và policy
    // đã được provision cho từng môi trường.
}
~~~

Đây là skeleton minh họa cách phân nhánh path; cần triển khai các hàm ACL theo identity thực tế, gồm digest ID đã được tạo đúng định dạng hoặc SASL/X.509 principal. Không trả OPEN_ACL_UNSAFE làm giá trị mặc định.

ACL provider chỉ ảnh hưởng các thao tác tạo znode đi qua Curator client có provider đó. Nó không tự sửa ACL của các znode đã tồn tại. Những node được tạo bởi CLI, công cụ quản trị hoặc client khác cũng cần được quản lý theo chính sách tương ứng.

## 11. Thiết kế ACL theo path và principal

Một mô hình mẫu có thể dùng các principal sau:

- config-admin: quản lý ACL và thay đổi cấu hình.
- config-reader-order: chỉ đọc context dùng chung và context order-service.
- config-reader-payment: chỉ đọc context dùng chung và context payment-service.
- discovery-reader: đọc danh sách dịch vụ.
- discovery-order: đăng ký và cập nhật instance order-service.
- discovery-payment: đăng ký và cập nhật instance payment-service.

Bảng quyền minh họa:

| Path | Principal | Quyền |
|---|---|---|
| /config | config-admin | ALL |
| /config | Config readers được phép | READ |
| /config/application | Config readers được phép | READ |
| /config/order-service | config-reader-order | READ |
| /config/order-service | config-admin | WRITE, CREATE, DELETE, ADMIN |
| /config/payment-service | config-reader-payment | READ |
| /config/payment-service | config-admin | WRITE, CREATE, DELETE, ADMIN |
| /services | discovery-reader | READ |
| /services/order-service | discovery-order | CREATE, DELETE, READ |
| /services/payment-service | discovery-payment | CREATE, DELETE, READ |
| Node instance do order-service sở hữu | discovery-order | READ, WRITE |
| Node instance do payment-service sở hữu | discovery-payment | READ, WRITE |
| Các node trong phạm vi quản trị | config-admin hoặc ACL admin riêng | ADMIN |

Bảng chỉ là ví dụ. Khi tạo znode con, quyền CREATE nằm trên parent; khi xóa child, quyền DELETE nằm trên parent. Để cập nhật dữ liệu, quyền WRITE nằm trên chính znode. Hãy áp dụng ACL phù hợp trên cả parent và child.

Một client có thể cần đọc config/application và config/order-service nhưng không được đọc config/payment-service. ACL phải phản ánh đúng tập path đó. Nếu ứng dụng bật nhiều profile, kiểm tra thêm các znode profile cụ thể và profile separator mà phiên bản Spring Cloud Zookeeper đang dùng.

## 12. Chia sẻ Curator client giữa Config và Discovery

Khi một ứng dụng có cả Config và Discovery starter, các integration có thể sử dụng Curator client được auto-configure chung. Nếu cùng một connection có nhiều identity, quyền hiệu lực là tổng các identity được xác thực và ACL tương ứng trên từng path.

Điều này có hai hệ quả:

1. Một workload cần đọc cấu hình và đăng ký dịch vụ phải có cả quyền READ trên config context được cấp và quyền đăng ký trong service path của nó.
2. Một workload chỉ cần Config không nên nhận thêm identity Discovery registrar; tương tự, một service registrar không nên nhận identity đọc cấu hình của các service khác.

Nếu cần ranh giới mạnh giữa hai chức năng, cân nhắc tách Curator client, danh tính hoặc cụm ZooKeeper theo khả năng integration và kiến trúc triển khai. Đừng giả định hai starter tự tạo hai security principal độc lập chỉ vì chúng có hai root path.

Trong một session ZooKeeper, các identity đã được xác thực có thể cùng được gắn với kết nối. Khi dùng nhiều credentials, phải kiểm tra chính xác ACL được đánh giá với những identity nào; một identity registrar có quyền ghi rộng có thể làm giảm hiệu quả của identity config-reader bị giới hạn.

## 13. Bảo vệ digest credentials và TLS

Digest authentication không mã hóa lưu lượng. Apache ZooKeeper ghi rõ thông tin xác thực digest được truyền dưới dạng rõ trong bước authentication, còn ACL identity dùng digest password không salt. Vì vậy:

- Bật TLS client-server khi dùng digest.
- Xác minh certificate và hostname của ZooKeeper server.
- Lưu password trong secret manager hoặc secret mount.
- Dùng credential riêng theo workload và có rotation.
- Không đưa password vào command history hoặc log.
- Không dùng digest làm cơ chế duy nhất khi hệ thống yêu cầu mức bảo vệ danh tính cao.

Nếu hạ tầng có Kerberos, SASL/GSSAPI thường phù hợp hơn cho xác thực principal. Nếu tổ chức quản lý PKI tốt, mTLS với X.509 có thể xác thực client bằng certificate. Dù dùng scheme nào, vẫn phải thiết kế ACL trên từng znode.

TLS client-server và TLS quorum là hai phạm vi khác nhau. Bảo vệ traffic giữa các node trong ensemble không tự bảo vệ traffic giữa ứng dụng và client port. Cấu hình secure client port, truststore/keystore và hostname verification theo hướng dẫn phiên bản ZooKeeper đang chạy.

## 14. Bảo vệ cây Service Discovery

Service Discovery lưu dữ liệu mà nhiều ứng dụng có thể đọc để tìm địa chỉ và port của nhau. Các giá trị đó không phải secrets nhưng vẫn là metadata nội bộ.

Một policy thường gặp:

- Client discovery có READ trên /services và các service path được phép.
- Registrar có CREATE trên parent path của service mình đăng ký.
- Registrar có WRITE trên node instance do nó quản lý nếu cần cập nhật trạng thái.
- Registrar có DELETE trên parent để xóa node con theo vòng đời đăng ký.
- Registrar của order-service không có quyền ghi/xóa node của payment-service.
- Chỉ ACL administrator mới có ADMIN nếu workload không cần tự quản lý ACL.

Không cấp WRITE/CREATE/DELETE cho tất cả client chỉ vì chúng cần gọi DiscoveryClient. Một client chỉ tra cứu dịch vụ cần READ.

Nếu dùng dependency watcher hoặc presence checker, đây là tính năng quan sát trạng thái phụ thuộc; nó không thay thế ACL và không tự phân quyền service registry. Một listener nhận trạng thái UP/DOWN không có nghĩa ứng dụng được phép ghi vào mọi service path.

## 15. Bảo vệ cây cấu hình và secrets

Cấu hình thường chứa thông tin nhạy cảm như endpoint nội bộ, username, password hoặc API token. ZooKeeper Config đưa property vào Spring Environment, nhưng ACL chỉ bảo vệ quyền truy cập znode. Nó không tự mã hóa giá trị khi ứng dụng đã đọc được.

Các nguyên tắc nên áp dụng:

- Đặt cấu hình dùng chung không nhạy cảm tại context application.
- Đặt property riêng theo service ở context của application.
- Không lưu secret dùng chung trong context mà mọi Config Client đều có READ.
- Tạo principal riêng cho từng application hoặc nhóm workload.
- Chỉ cấp READ trên context cần thiết.
- Giới hạn ai được WRITE, CREATE, DELETE và ADMIN.
- Bật TLS cho traffic và giới hạn mạng truy cập client port.
- Dùng secret manager cho password/key nếu có thể; hạn chế lưu secret dài hạn trực tiếp trong ZooKeeper.

Ví dụ, config/application có thể chứa timeout hoặc feature flag chung. Password database của order-service nên nằm trong secret store riêng hoặc path chỉ config-reader-order đọc được. Không dựa vào việc client không biết path để bảo vệ node.

## 16. Provision và migration ACL an toàn

ACL không tự áp dụng hồi tố cho toàn cây. Khi chuyển một cluster từ ACL mở sang ACL hạn chế, cần có quy trình migration:

1. **Kiểm kê cây znode:** liệt kê /config, /services và các path con hiện có.
2. **Xác định owner:** ghi nhận ứng dụng hoặc quy trình nào tạo, đọc và cập nhật từng nhánh.
3. **Tạo danh tính:** cấp digest/SASL/X.509 principal cho Config Client, config publisher, discovery reader và registrar.
4. **Thiết kế ACL:** xác định quyền cần có ở parent và child; giữ principal quản trị khẩn cấp riêng.
5. **Kiểm thử trên staging:** tạo node mới và xác nhận ACL đúng cho từng path.
6. **Áp dụng cho node hiện có:** dùng tài khoản quản trị gọi setACL trên từng znode; xử lý cả node cha và node con.
7. **Cấu hình Curator:** thêm authentication và ACLProvider trước khi ứng dụng bắt đầu tạo node.
8. **Chuyển workload:** cấp credential mới, restart/rollout theo thứ tự và xác nhận request hợp lệ.
9. **Thu hồi credential cũ:** chỉ sau khi toàn bộ workload đã dùng danh tính mới và kiểm thử thành công.

Không chạy migration chỉ thay ACL trên /config rồi cho rằng các node con đã được bảo vệ. ZooKeeper ACL không đệ quy. Cũng không thu hồi quyền quản trị cũ trước khi xác minh principal quản trị mới có thể đọc, cập nhật và sửa ACL.

Nếu migration sai, ứng dụng có thể mất quyền đọc config hoặc không xóa được ephemeral service node khi session thay đổi. Hãy có kế hoạch rollback, lưu lại ACL ban đầu và thực hiện theo từng nhánh.

## 17. Refresh cấu hình không thay thế authorization

Spring Cloud Zookeeper Config tải property vào Spring Environment khi khởi động. Có thể gửi HTTP POST tới endpoint /refresh để yêu cầu nạp lại cấu hình. Chi tiết hỗ trợ watch namespace phụ thuộc phiên bản Spring Cloud Zookeeper; kiểm tra tài liệu release train đang dùng.

Dù refresh được kích hoạt bằng HTTP endpoint hay cơ chế watch, Curator client vẫn phải có quyền READ trên các znode cấu hình cần tải. Nếu ACL thay đổi giữa lúc ứng dụng chạy, lần refresh tiếp theo có thể thất bại dù lần khởi động trước thành công.

Phân biệt:

- /refresh làm mới property source của ứng dụng.
- Service Discovery theo dõi thông tin đăng ký và trạng thái instance.
- Dependency Watcher quan sát trạng thái phụ thuộc UP/DOWN.
- ACL quyết định các thao tác ZooKeeper có được phép hay không.

Không dùng việc một service xuất hiện trong registry làm bằng chứng rằng service đó có quyền đọc config. Không dùng việc refresh thành công làm bằng chứng rằng ACL cho các path khác cũng đúng.

## 18. Kiểm thử quyền đọc và ghi

Kiểm thử phải dùng đúng principal của từng workload. Một bài test chạy bằng tài khoản admin có thể đọc và ghi mọi thứ, vì vậy không chứng minh quyền ứng dụng đã được giới hạn.

| Principal / thao tác | Kết quả mong đợi |
|---|---|
| order-service đọc /config/application | Thành công nếu được cấp config dùng chung |
| order-service đọc /config/order-service | Thành công |
| order-service đọc /config/payment-service | Bị từ chối |
| payment-service đọc /config/payment-service | Thành công |
| Config Client ghi /config/order-service | Bị từ chối |
| Config publisher cập nhật /config/order-service | Thành công theo policy |
| discovery-reader liệt kê /services | Thành công |
| discovery-reader tạo node con trong /services/order-service | Bị từ chối |
| discovery-order đăng ký instance dưới /services/order-service | Thành công |
| discovery-order xóa node của payment-service | Bị từ chối |
| Workload thường gọi setACL | Bị từ chối nếu không có ADMIN |
| Client không xác thực đọc node cấu hình riêng tư | Bị từ chối |

Có thể dùng ZooKeeper CLI hoặc Curator integration test để kiểm tra:

~~~text
getAcl /config
getAcl /config/order-service
getAcl /services
getAcl /services/order-service
~~~

Chỉ tài khoản có quyền phù hợp mới xem hoặc thay ACL được. Thực hiện test với tài khoản quản trị để kiểm tra cấu hình, sau đó chạy lại các thao tác đọc/ghi bằng từng workload principal để xác nhận kết quả thực tế.

Với digest CLI, lệnh addauth cần credentials của môi trường test. Không ghi password thật vào tài liệu, script dùng chung hoặc shell history. Nếu kiểm thử qua Java, tạo Curator client với đúng authorization và thử getData, getChildren, setData, create, delete trên các path tương ứng.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Curator kết nối được nhưng đọc config bị NOAUTH | Client chưa gửi auth info hoặc auth scheme không khớp ACL | Kiểm tra customizer, server auth provider và principal |
| Đã gọi authorization nhưng node vẫn đọc công khai | ACL node vẫn là OPEN_ACL_UNSAFE | Kiểm tra getAcl và đặt ACL cho node hiện có |
| Đã khóa /config nhưng child vẫn đọc được | ACL không kế thừa xuống child | Cập nhật ACL trên từng znode con |
| Config Client đọc được config service khác | Principal dùng chung hoặc ACL READ quá rộng | Tách principal và cấp ACL theo application/profile |
| Service registrar không tạo được ephemeral node | Thiếu CREATE trên parent hoặc quyền phù hợp trên node | Kiểm tra ACL ở service root và child path |
| Service Discovery không liệt kê được instance | Thiếu READ trên parent hoặc child | Cấp READ đúng phạm vi registry |
| Ứng dụng vừa thêm Discovery starter thì mất quyền Config | Curator identity/ACL policy chỉ cho một nhánh | Cấp cả hai quyền cần thiết hoặc tách client/identity |
| setACL bị NOAUTH | Principal không có ADMIN | Dùng ACL administrator riêng |
| Client digest xác thực lỗi khi bật TLS | Truststore, certificate hoặc secure port sai | Kiểm tra certificate chain, hostname và port |
| Ứng dụng cũ vẫn đọc node sau khi migration | ACL cũ chưa áp dụng cho mọi path hoặc session có identity cũ | Kiểm tra toàn cây, reconnect client và thu hồi credential cũ |
| Node mới lại có ACL mở | ACLProvider chưa được áp dụng cho Curator client tạo node | Kiểm tra customizer chạy trước client build và getAclForPath |

## 20. Checklist production

- Cấu hình root Config và Discovery riêng; mặc định là /config và /services.
- Dùng principal riêng cho config reader, config publisher, discovery reader và registrar.
- Không để mọi ứng dụng dùng chung một credential có quyền rộng.
- Bật authentication và TLS cho client-server connection.
- Bảo vệ quorum traffic và admin interface theo hướng dẫn ZooKeeper.
- Không dùng OPEN_ACL_UNSAFE cho cấu hình hoặc registry nội bộ.
- Cấp READ/WRITE/CREATE/DELETE/ADMIN đúng trên từng znode.
- Nhớ ACL không kế thừa; đặt ACL trên mọi parent, child và leaf cần bảo vệ.
- Dùng CuratorFrameworkCustomizer theo API của phiên bản đang chạy.
- Cấu hình ACLProvider để znode mới nhận ACL theo path.
- Migration ACL hiện có bằng tài khoản admin và kiểm tra từng nhánh.
- Không lưu secret trong context dùng chung hoặc service metadata.
- Kiểm thử từ chối đọc config service khác và từ chối ghi registry service khác.
- Theo dõi NOAUTH, session reconnect và lỗi ACL.
- Có quy trình rotation credentials và rollback ACL.

## 21. Tự kiểm tra

1. Authentication khác ACL ở điểm nào?
2. Vì sao gọi addAuthInfo không tự bảo vệ znode?
3. READ, WRITE, CREATE, DELETE và ADMIN kiểm soát những thao tác nào?
4. Vì sao ACL trên /config không bảo vệ tự động /config/order-service?
5. Một Config Client cần quyền nào để đọc context dùng chung và context riêng?
6. Service registrar cần quyền nào trên parent path và ephemeral instance node?
7. Vì sao một workload có cả Config và Discovery cần được xem xét về danh tính Curator dùng chung?
8. Digest authentication có hạn chế gì về bảo mật đường truyền?
9. Khi nào SASL/Kerberos hoặc X.509 phù hợp hơn digest?
10. Vì sao IP ACL không nên là cơ chế xác thực duy nhất?
11. Cần làm gì để các znode đã tồn tại nhận ACL mới?
12. Làm thế nào chứng minh order-service không thể đọc cấu hình của payment-service?

Hãy dựng một ZooKeeper ensemble staging với hai Spring Boot application là order-service và payment-service. Bật Spring Cloud Zookeeper Config cho cả hai; bật Service Discovery cho ít nhất một ứng dụng. Tạo danh tính riêng, đặt ACL cho /config/application, /config/order-service, /config/payment-service và /services. Kiểm thử order-service đọc cấu hình của nó nhưng bị từ chối khi đọc payment-service; kiểm thử discovery-reader đọc registry nhưng không được tạo hoặc xóa service node. Sau đó tạo một znode mới để xác minh ACLProvider áp dụng đúng policy, restart một client để kiểm tra authentication và cuối cùng kiểm tra lại ACL của các node cha lẫn node con.

## Tài liệu tham khảo

- [Spring Cloud Zookeeper — Distributed Configuration and ACLs](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)
- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Apache ZooKeeper — Security](https://zookeeper.apache.org/security/)
- [Apache ZooKeeper — Programmer's Guide and ACLs](https://zookeeper.apache.org/doc/r3.10.0/developer/programmers-guide/access-control-using-acls/)
- [Apache Curator — ACLProvider API](https://curator.apache.org/apidocs/org/apache/curator/framework/api/ACLProvider.html)
- [Spring Cloud Zookeeper 5.1 preview/snapshot — CuratorFrameworkCustomizer](https://docs.spring.io/spring-cloud-zookeeper/reference/5.1-SNAPSHOT/config.html)

