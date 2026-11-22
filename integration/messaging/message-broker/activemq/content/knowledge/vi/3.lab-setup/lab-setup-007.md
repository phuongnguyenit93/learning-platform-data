# Quản lý cấu hình, bí mật và phiên bản image để tái lập môi trường ActiveMQ

> **Chương:** Môi trường thực hành  
> **Phạm vi:** Apache ActiveMQ Classic và Apache Artemis trong hệ thống giao tiếp bất đồng bộ bằng queue, topic và Java Messaging Service (JMS/Jakarta Messaging). Bài học xây dựng một phòng lab Docker Compose có thể dựng lại, phân biệt phần cấu hình được quản lý bằng Git với bí mật và trạng thái vận hành của broker.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Chốt chính xác **phiên bản broker image, digest, nền tảng CPU, JDK và thư viện JMS** để những lần dựng môi trường sau không âm thầm đổi phần mềm.
2. Đưa cấu hình queue, routing, redelivery, DLQ và cổng mạng vào tệp được quản lý phiên bản, thay vì chỉnh tay trong container.
3. Cấp mật khẩu qua Docker Compose secrets, hiểu giới hạn của cách khởi tạo tài khoản với image Artemis chính thức, và không đưa secret vào Git, lệnh chạy hoặc file cấu hình chia sẻ.
4. Phân tách **cấu hình** (có thể tái tạo), **bí mật** (được cấp riêng) và **dữ liệu broker** (journal, message, bindings; cần lưu/khôi phục có chủ đích).
5. Kiểm chứng phòng lab bằng chương trình Java/JMS, thử dựng lại với volume mới và ghi nhận bằng chứng về phiên bản, cấu hình cùng hành vi message.

Trong thực tế, câu “đã dùng cùng một file Compose” **chưa đủ** để khẳng định hai môi trường giống nhau. Tag `latest` có thể trỏ sang image khác; file `broker.xml` có thể bị sửa sau khi container chạy; volume cũ có thể chứa mật khẩu và queue được tạo từ nhiều tuần trước; ứng dụng có thể phụ thuộc vào một phiên bản thư viện JMS khác.

## 2. Mô hình quản lý: thứ gì phải khóa, thứ gì phải giữ riêng?

| Thành phần | Ví dụ | Cách quản lý đúng | Khi dựng lại môi trường |
|---|---|---|---|
| Image broker | `apache/artemis:2.57.0-alpine` | Chọn tag phát hành rồi **khóa bằng digest `sha256`** | Docker kéo đúng image tương ứng digest |
| Nền tảng chạy | `linux/amd64` hoặc `linux/arm64` | Ghi rõ kiến trúc và Docker Engine/Compose dùng để kiểm thử | Không so sánh thiếu thông tin kiến trúc |
| Cấu hình broker | `broker.xml`, `activemq.xml`, giới hạn memory, address, redelivery và DLQ | Tệp văn bản trong Git, review diff, gắn commit | Được gắn vào đúng đường dẫn broker sử dụng |
| Biến cấu hình không nhạy cảm | Tên user lab, cổng, tên service, đường dẫn cấu hình | `compose.yaml` hoặc tệp lock, không chứa secret | Áp dụng như nhau |
| Mật khẩu, khóa TLS | Password broker, private key, truststore password | Compose secret, secret manager, tệp cục bộ bị Git ignore và được giới hạn quyền đọc | Cấp riêng cho từng môi trường; **không** bắt buộc giữ giá trị secret giống nhau |
| Trạng thái runtime | Artemis journal/bindings, Classic KahaDB, queue đang tồn đọng | Named volume/snapshot/backup; định nghĩa quy tắc reset | Quyết định rõ “lab sạch” hay “khôi phục dữ liệu” |
| Java client | `artemis-jakarta-client:2.57.0`; JDK 17 | Ghi dependency version và JDK, khóa transitive dependency khi cần | Biên dịch/chạy cùng stack đã chốt |

**Tái lập cấu hình** nghĩa là từ cùng mã nguồn cấu hình, phiên bản phần mềm và đầu vào hợp lệ có thể tạo một broker có hành vi mong đợi. **Tái lập dữ liệu** là bài toán khác: nếu cần giữ message đang chờ, transaction, durable subscription, lịch sử nhận/gửi…, phải sao lưu và khôi phục đúng quy trình. Tạo volume trắng sẽ không tái tạo các message tồn đọng trước đó.

### Ba lớp ảnh hưởng kết quả kiểm thử

```text
Git commit + image digest + JMS/JDK versions
                  │
                  ▼
         Cấu hình broker khai báo
   (queue, topic, routing, DLQ, ACL, TLS)
                  │
         Secret được cấp riêng
                  │
                  ▼
      Broker instance và data volume
                  │
                  ▼
    Producer/consumer Java + bộ test
                  │
                  ▼
   Bằng chứng hành vi và phiên bản
```

## 3. Chọn image đúng sản phẩm và chốt phiên bản

Apache ActiveMQ **Classic** và **Artemis** là hai broker riêng. Chúng có cơ chế cấu hình, lưu trữ và client native khác nhau. Một cấu hình `activemq.xml` của Classic không thể đổi tên thành `broker.xml` để Artemis hiểu.

| Đặc tính | ActiveMQ Classic | Apache Artemis |
|---|---|---|
| Image chính thức dùng để tra cứu | `apache/activemq`; kiểm tra tag hiện có trên Docker Hub | `apache/artemis`; ví dụ tag `2.57.0-alpine` |
| Bản phát hành minh họa | Classic 6.4.0 | Artemis 2.57.0 |
| JDK broker | Classic 6.4.0 công bố Java 17, 21, 25 | Artemis 2.57.0 yêu cầu Java 17 trở lên |
| Cấu hình thông thường | `conf/activemq.xml`, JAAS, property files | `etc/broker.xml`, `bootstrap.xml`, `artemis-users.properties`, `artemis-roles.properties` |
| Persistence | Thường dùng KahaDB; cấu hình qua `persistenceAdapter` | Journal, bindings, paging… trong instance data directory |
| Java API ở ví dụ | Classic 6.x dùng `jakarta.jms`, OpenWire client `activemq-client` | Artemis Jakarta client `artemis-jakarta-client`, thường dùng Core protocol |

**Tag và digest khác nhau:**

- `apache/artemis:2.57.0-alpine` xác định một **tag có thể được registry cập nhật**; tốt hơn `latest` để biết dòng phần mềm, nhưng chưa phải khóa tuyệt đối.
- `apache/artemis@sha256:<digest>` xác định nội dung image theo digest được registry cung cấp. Nếu không có đúng digest đó, quá trình kéo image phải thất bại thay vì âm thầm chọn image mới.
- Digest có thể đại diện manifest đa kiến trúc hoặc manifest riêng của một kiến trúc. Khi điều tra kết quả khác nhau, ghi cả digest **và** `linux/amd64`/`linux/arm64`.

**Cách tạo lock tệp có thể commit vào Git:**

```bash
# Lần đầu, lấy đúng tag phát hành đã chọn.
docker pull apache/artemis:2.57.0-alpine

# Đọc repo digest thực tế sau khi pull.
docker image inspect apache/artemis:2.57.0-alpine \
  --format '{{index .RepoDigests 0}}'
```

Nếu đầu ra là `apache/artemis@sha256:...`, sao chép **đúng toàn bộ** vào `.env.lock`:

```dotenv
# .env.lock — KHÔNG chứa mật khẩu; lưu trong Git.
# Thay <DIGEST_THUC_TE> bằng 64 ký tự hex từ lệnh inspect.
ARTEMIS_IMAGE=apache/artemis@sha256:<DIGEST_THUC_TE>
```

Không dùng chuỗi placeholder trên để chạy thật; hãy thay bằng digest đã lấy. Khi nâng phiên bản, tạo thay đổi Git bao gồm digest mới và kết quả kiểm thử. Với môi trường nghiêm ngặt, khóa thêm image JDK/build tool, Maven dependencies và platform; digest của broker không tự khóa JDK đang chạy trên máy phát triển.

## 4. Cấu trúc phòng lab

Mọi khối mã ở các mục tiếp theo là **nội dung mẫu để bạn tạo trong một dự án lab riêng**. Các tên tệp trong cây dưới đây minh họa cấu trúc mong muốn; không cần chứa dữ liệu broker trong repository.

```text
activemq-repro-lab/
├── compose.yaml                    # có thể commit
├── .env.lock                      # có thể commit: IMAGE digest, không chứa secret
├── .gitignore                     # có thể commit
├── config/
│   └── artemis/
│       └── broker.xml            # có thể commit: toàn bộ file đã review
├── secrets/
│   └── artemis_admin_password    # KHÔNG commit
└── app/
    ├── pom.xml                   # khóa dependency Java và plugin Maven
    └── src/main/java/lab/
        └── RoundTrip.java        # JMS integration smoke test
```

Tệp `.gitignore` tối thiểu:

```gitignore
/secrets/
/runtime/
/.env
/.env.local
*.key
*.p12
*.jks
```

Nếu thư mục `secrets/` đã từng được commit, thêm `.gitignore` **không** xóa secret khỏi Git history. Phải thu hồi/đổi secret bị lộ, xử lý lịch sử theo quy trình của nhóm và ngăn CI/log tiếp tục phát tán giá trị đó. Với khóa TLS, cũng phải bảo đảm backup và artifact của pipeline không công khai private key.

## 5. Compose thực hành: Artemis với image khóa và secret dạng tệp

Đây là ví dụ **chạy trên máy lab**, không mặc định là mẫu production. Dùng image Artemis chính thức, một broker instance có volume lưu trạng thái, cổng chỉ xuất ra localhost, file cấu hình được mount và bí mật được cấp qua Compose secret.

**`compose.yaml`:**

```yaml
name: activemq-repro-lab

services:
  broker:
    image: ${ARTEMIS_IMAGE:?ARTEMIS_IMAGE must be set by .env.lock}
    environment:
      ARTEMIS_USER: labadmin
      ANONYMOUS_LOGIN: "false"

    # Image Artemis chờ ARTEMIS_PASSWORD, không mặc định có biến
    # ARTEMIS_PASSWORD_FILE. Wrapper đọc file secret ngay khi chạy.
    entrypoint: ["/bin/sh", "-eu", "-c"]
    command:
      - |
        ARTEMIS_PASSWORD="$$(cat /run/secrets/artemis_admin_password)"
        [ -n "$$ARTEMIS_PASSWORD" ] || {
          echo "Empty broker password" >&2
          exit 1
        }
        export ARTEMIS_PASSWORD
        exec /docker-run.sh run

    secrets:
      - artemis_admin_password

    ports:
      - "127.0.0.1:61616:61616"   # messaging: chỉ localhost của máy lab
      - "127.0.0.1:8161:8161"     # management console: chỉ localhost

    volumes:
      - artemis_instance:/var/lib/artemis-instance
      - ./config/artemis:/var/lib/artemis-instance/etc-override:ro

    restart: unless-stopped

secrets:
  artemis_admin_password:
    file: ./secrets/artemis_admin_password

volumes:
  artemis_instance:
```

**Vì sao dùng `$$` trong `command`?** Docker Compose sẽ nội suy một dấu `$` khi đọc YAML. Viết `$$ARTEMIS_PASSWORD` và `$$(...)` bảo đảm dấu `$` được truyền nguyên vẹn vào shell **bên trong** container. Trong khi đó `${ARTEMIS_IMAGE:?...}` được Compose nội suy có chủ đích từ tệp lock.

**Vì sao mount đúng hai vị trí?**

- `/var/lib/artemis-instance` chứa cả instance, cấu hình runtime, journal và bindings của Artemis; named volume giúp dữ liệu tồn tại sau khi container dừng hoặc tạo lại.
- `/var/lib/artemis-instance/etc-override` là cơ chế được image Artemis hỗ trợ để chép cấu hình người dùng lên thư mục `etc` khi startup. Thư mục `config/artemis` trên host phải chứa **file `broker.xml` hoàn chỉnh**, không phải XML rời rạc. Việc mount read-only ngăn broker sửa bản gốc trên host.
- Compose secret được mount vào `/run/secrets/artemis_admin_password`, thay vì đưa giá trị trực tiếp vào `compose.yaml` hoặc `docker compose config`. Compose cần quyền đọc file nguồn trên host để tạo mount.

**Giới hạn bảo mật phải hiểu đúng:** wrapper buộc phải chuyển secret từ file vào biến `ARTEMIS_PASSWORD` vì đây là giao diện khởi tạo image Artemis được công bố. Bí mật không trở thành giá trị khai báo trong `environment` của Compose, nhưng vẫn có thể xuất hiện trong môi trường của tiến trình và trong cơ chế khởi tạo user; nó **không** có mức cô lập giống một tích hợp secret manager native. Giữ quyền truy cập máy/daemon/container ở mức tin cậy, không bật shell tracing `set -x` và không log các biến môi trường. Với production có chính sách cấm secret trong env/process arguments, hãy cấp tài khoản bằng quy trình provisioning/secret manager riêng đã kiểm duyệt, không sử dụng wrapper minh họa này.

### 5.1. Chuẩn bị secret cục bộ

Trên Bash/Linux/macOS:

```bash
mkdir -p config/artemis secrets
umask 077
read -r -s -p 'Broker admin password: ' LAB_BROKER_PASSWORD
printf '\n'
printf '%s' "$LAB_BROKER_PASSWORD" > secrets/artemis_admin_password
unset LAB_BROKER_PASSWORD
chmod 600 secrets/artemis_admin_password
```

**Nếu chạy Docker Engine trực tiếp trên Linux:** image Artemis Alpine chạy tiến trình với user không phải root (thường UID/GID `1001`). Compose secret lấy từ `file:` giữ quyền của file nguồn do cơ chế bind mount; `chmod 600` chỉ cho chủ sở hữu trên host đọc được và có thể khiến container báo `Permission denied`. Trước khi `up`, xem UID/GID **thực tế của image đã khóa** rồi cấp quyền đọc riêng cho UID container qua ACL:

```bash
# Xem numeric UID/GID của user mặc định trong đúng image đã khóa.
docker compose --env-file .env.lock run --rm --no-deps \
  --entrypoint /bin/sh broker -c id

# Ví dụ khi id báo uid=1001; yêu cầu filesystem có hỗ trợ POSIX ACL.
setfacl -m u:1001:r secrets/artemis_admin_password
getfacl secrets/artemis_admin_password
```

Nếu máy không có `setfacl`, có thể cấp quyền đọc cho GID container bằng cách đổi group của file (chẳng hạn `sudo chgrp 1001 secrets/artemis_admin_password` và `chmod 640 secrets/artemis_admin_password`). Chỉ áp dụng sau khi xác nhận UID/GID; đừng chữa lỗi bằng `chmod 644` vì nó cho tất cả user trên host đọc mật khẩu. Với Docker rootless/user namespace hoặc Docker Desktop, quy tắc ánh xạ UID khác nhau: kiểm tra quyền đọc trong môi trường thực tế. Tương tự, bảo đảm thư mục `config/artemis` cho phép user trong container đọc file cấu hình.

Hãy dùng một mật khẩu mạnh dành riêng cho lab. Lệnh nhập ở chế độ ẩn tránh ghi chính mật khẩu vào shell history; không viết `echo 'password' > ...` trong terminal được ghi log. Trên Windows, tạo file UTF-8 **không có BOM**, kiểm tra ACL của tệp nguồn và bảo đảm Docker Desktop có quyền đọc thư mục đã chia sẻ. `chmod 600` là lệnh POSIX, không áp dụng nguyên nghĩa cho ACL Windows.

Compose secret với `file:` trên Docker Compose cục bộ được bind-mount từ file nguồn; **không** có nghĩa nội dung bí mật chỉ nằm trong bộ nhớ hoặc được mã hóa trong kho bí mật quản lý tập trung. Bảo vệ cả máy phát triển, backup, quyền đọc file và hệ thống CI.

### 5.2. Khởi chạy và lấy cấu hình chuẩn từ chính image đã khóa

Ở lần đầu, `config/artemis/` có thể rỗng; image tự tạo broker instance cùng cấu hình mặc định trong named volume. Thực hiện từ thư mục gốc lab:

```bash
# Kiểm tra cấu trúc Compose và image được tham chiếu.
docker compose --env-file .env.lock config --quiet
docker compose --env-file .env.lock config --images

# Tạo instance. Đọc log để biết broker đã khởi động xong.
docker compose --env-file .env.lock up -d
docker compose --env-file .env.lock logs --tail=100 broker

# Lấy broker.xml ĐẦY ĐỦ được sinh bởi đúng image đang chạy.
docker compose --env-file .env.lock cp \
  broker:/var/lib/artemis-instance/etc/broker.xml \
  ./config/artemis/broker.xml
```

Sau bước sao chép, **kiểm tra file trước khi commit**, đặc biệt các trường liên quan đến cluster credential, địa chỉ bind, đường dẫn, secret hoặc bất kỳ chuỗi mặc định không an toàn. Mặc định thông tin user/password thường được Artemis lưu trong các file authentication khác của instance; đừng sao chép nguyên thư mục `etc` cùng file người dùng, private key vào Git.

Sửa `config/artemis/broker.xml` như mục 6 rồi áp dụng bằng:

```bash
docker compose --env-file .env.lock restart broker
docker compose --env-file .env.lock logs --tail=100 broker
```

Ở lần khởi động kế tiếp, cơ chế `etc-override` chép file được mount sang `etc` runtime. **Đừng chỉ nhìn file host đã đổi rồi suy rằng broker hot-reload mọi thiết lập**; hãy kiểm tra log và hành vi sau restart. Với thay đổi chỉ hỗ trợ tại thời điểm khởi tạo, có thể cần tạo instance mới hoặc chạy quy trình migration riêng.

## 6. Khai báo queue, routing và DLQ có thể review

Mở **file `broker.xml` đầy đủ vừa lấy**. Bên trong khối `<core>`, bổ sung hoặc chỉnh sửa **các mục có sẵn** `<address-settings>` và `<addresses>`. Không thêm hai phần tử cấp cao trùng nhau khi file đã có các mục này.

Ví dụ nội dung **của một entry** trong `<address-settings>`:

```xml
<address-setting match="orders.#">
  <dead-letter-address>DLQ</dead-letter-address>
  <max-delivery-attempts>3</max-delivery-attempts>
  <redelivery-delay>1000</redelivery-delay>
  <auto-create-queues>false</auto-create-queues>
</address-setting>
```

Ví dụ các address **bên trong** `<addresses>`:

```xml
<address name="orders.lab">
  <anycast>
    <queue name="orders.lab"/>
  </anycast>
</address>

<address name="DLQ">
  <anycast>
    <queue name="DLQ"/>
  </anycast>
</address>
```

Nếu cấu hình mẫu đã có address `DLQ`, **chỉ sửa entry đó**; đừng tạo bản trùng tên. Trong Artemis, `ANYCAST` định tuyến tới queue, còn `MULTICAST` thường phục vụ semantics topic/subscription. Queue `orders.lab` được khai báo tường minh để phép thử không phụ thuộc vào chế độ tự tạo resource. Với `max-delivery-attempts=3` và `redelivery-delay=1000`, sau các lần phân phối thất bại theo chính sách broker, message được chuyển về DLQ thay vì được xử lý vô hạn.

Không đặt mật khẩu trong `broker.xml` hoặc `bootstrap.xml` nếu có thể cấp bằng nguồn secret được quản trị riêng. Ngoài định nghĩa queue, một môi trường đáng tin cậy cần khai báo nhất quán các phần cấu hình sau, tùy phạm vi bài kiểm thử:

| Nhóm cấu hình | Nội dung cần kiểm soát | Vì sao tác động đến kết quả |
|---|---|---|
| Acceptor/protocol | `CORE`, `OPENWIRE`, `AMQP`, cổng, host bind | Java client không kết nối được nếu protocol/port lệch |
| Security | `security-enabled`, authentication, authorization, vai trò | Queue tồn tại nhưng tài khoản không có quyền gửi/nhận |
| Address routing | `ANYCAST`/`MULTICAST`, queue, topic subscription | Message có thể đi sai loại destination |
| Redelivery | delay, max delivery attempts, DLQ | Cùng một chương trình nhưng số lần nhận khác nhau |
| Paging/memory | `max-size-bytes`, `address-full-policy` | Producer có thể bị chặn, fail hoặc paging |
| Durability | Message persistent, journal/data volume | Mất dữ liệu khi restart hoặc khi xóa volume |
| TLS | Keystore/truststore, giao thức TLS | Kết nối plaintext local khác production |

Quy tắc thực hành: trước khi áp dụng `broker.xml` mới, review diff và kiểm tra toàn bộ file XML hợp lệ với **đúng phiên bản Artemis**. Fragment trên mô tả các phần cần sửa, không phải một `broker.xml` hoàn chỉnh tự chạy.

## 7. Java/JMS: xác minh broker sau khi dựng lại

Ví dụ sử dụng **JDK 17**, `jakarta.jms` và thư viện `org.apache.artemis:artemis-jakarta-client:2.57.0`. Chương trình đọc mật khẩu trực tiếp từ file local, gửi một message persistent vào queue `orders.lab` trong transaction và đọc lại sau khi commit. Nó kiểm tra được đồng thời thông tin đăng nhập, giao thức Core, cấu hình destination và JMS transaction cơ bản.

**`app/pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.messaging</groupId>
  <artifactId>artemis-config-repro-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.apache.artemis</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.57.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
        <configuration>
          <mainClass>lab.RoundTrip</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**`app/src/main/java/lab/RoundTrip.java`:**

```java
package lab;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

public class RoundTrip {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: RoundTrip <password-file>");
        }

        // File do người chạy cung cấp; không hardcode password trong mã.
        String password = Files.readString(
            Path.of(args[0]), StandardCharsets.UTF_8);
        if (password.isEmpty()) {
            throw new IllegalArgumentException("Password file is empty");
        }

        String payload = "order-" + UUID.randomUUID();
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://localhost:61616");

        try {
            try (JMSContext context = factory.createContext(
                    "labadmin", password, JMSContext.SESSION_TRANSACTED)) {
                Queue queue = context.createQueue("orders.lab");

                context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, payload);

                // Message trong local transaction chỉ có hiệu lực sau commit.
                context.commit();

                String received = context.createConsumer(queue)
                    .receiveBody(String.class, 5_000L);
                if (!payload.equals(received)) {
                    context.rollback();
                    throw new IllegalStateException(
                        "Message mismatch or timeout: " + received);
                }

                // Ack cho message đã nhận trong session giao dịch.
                context.commit();
                System.out.println("PASS: " + payload);
            }
        } finally {
            factory.close();
        }
    }
}
```

Chạy từ **thư mục gốc lab** sau khi log broker báo sẵn sàng:

```bash
java -version
mvn -version
mvn -f app/pom.xml -q compile exec:java \
  -Dexec.args=secrets/artemis_admin_password
```

Đường dẫn secret trong lệnh nằm ở host, **không phải** `/run/secrets/...` trong container. Nếu bạn chạy Java từ một container khác, cần cấp secret cho chính container đó qua Compose và đổi URI thành `tcp://broker:61616` trên cùng mạng Docker. Ví dụ sử dụng admin user để giảm bước tạo role của lab; trong hệ thống thật cần tài khoản producer/consumer riêng với quyền tối thiểu.

Một lần in `PASS: order-...` chứng minh luồng happy-path với queue và transaction, **chưa** chứng minh redelivery/DLQ, durable topic subscription, TLS, tải nặng hay recovery khi broker crash. Các mục đó cần bộ kiểm thử tích hợp riêng.

### 7.1. Kiểm thử redelivery và DLQ sau smoke test

Tạo một consumer dùng `JMSContext.SESSION_TRANSACTED`, đọc message rồi gọi `rollback()` thay vì `commit()`. Gửi message mới, nhận và rollback lặp lại, ghi lại `JMSXDeliveryCount`, thời gian giữa các lần phân phối, sau đó dùng consumer trên queue `DLQ` để xác minh message đã được chuyển vào đó. Với cấu hình mục 6, kiểm tra tối thiểu:

- Message không biến mất ngay sau rollback đầu tiên.
- Delay và số lần phân phối không vượt kỳ vọng từ `redelivery-delay` / `max-delivery-attempts`.
- Message xuất hiện trong `DLQ` và không tiếp tục xoay vô hạn ở `orders.lab`.
- Restart broker với volume giữ nguyên không làm mất message persistent đã được commit.

Phải để broker có đủ quyền/định nghĩa DLQ, và test tạo identifier riêng để không vô tình tiêu thụ message của test khác. Không dùng `AUTO_ACKNOWLEDGE` để đánh giá rollback: chế độ đó không tạo transaction.

## 8. Phân biệt secret ban đầu và thay đổi tài khoản sau khi instance tồn tại

Đây là một điểm dễ bị bỏ sót khi đánh giá môi trường có “tái lập được” hay không.

1. Ở **lần đầu tiên** image Artemis tạo `/var/lib/artemis-instance`, các biến `ARTEMIS_USER` và `ARTEMIS_PASSWORD` được dùng để tạo user quản trị ban đầu.
2. Những lần container sau sử dụng lại named volume đã có instance; thay nội dung `secrets/artemis_admin_password` trong Compose **không đồng nghĩa** đã đổi mật khẩu nằm trong cơ sở xác thực của broker.
3. Nếu file secret trên host đổi nhưng user trong instance chưa được cập nhật tương ứng, Java smoke test có thể thất bại với lỗi authentication dù Compose đã restart bình thường.
4. Để xoay mật khẩu thực sự, cần quy trình quản trị user của Artemis (thay credential trong backend xác thực, cập nhật secret theo thứ tự an toàn, xác minh client mới, thu hồi credential cũ). Không dùng việc xóa dữ liệu để “reset mật khẩu” ở môi trường cần bảo toàn message.

Khi xây một môi trường lab **hoàn toàn mới**, có thể dùng một project name/volume mới và chạy script provisioning một lần. Trong môi trường tồn tại lâu, hãy coi identity store và dữ liệu broker là tài sản cần backup và migration có kiểm soát.

### Compose secrets không tự giải quyết mọi vấn đề bảo mật

| Rủi ro | Cách giảm |
|---|---|
| Secret lộ qua Git, CI artifact hoặc log debug | Git ignore, secret scanner, không log giá trị, không hiển thị `env`/`printenv` |
| Secret file trên host bị đọc bởi user không liên quan | ACL/permissions, ổ đĩa/backup được bảo vệ, secret manager khi triển khai thật |
| Secret được export vào env tiến trình | Chỉ dùng wrapper khởi tạo trong lab; production tích hợp credential provider phù hợp |
| Broker lộ cổng console/message ra mạng | Bind host `127.0.0.1` trong lab, firewall, TLS và auth theo role ở production |
| Credential dùng chung cho mọi producer/consumer | Tách user, role; cho phép `send`/`consume` đúng address |
| Secret bị xoay trên host nhưng broker chưa áp dụng | Quy trình cập nhật credential server và restart/refresh cần thiết; chạy lại smoke test |
| Backup lưu private key, file user, journal | Mã hóa backup, giới hạn quyền truy cập và retention |

**TLS:** Khi lab tiến tới kiểm thử mạng hoặc production, bảo đảm transport connector/acceptor yêu cầu TLS và client Java tin cậy certificate đúng hostname. Chỉ mount keystore/truststore theo nguyên tắc least privilege; không đóng gói private key vào Docker image hoặc đẩy vào Git. Mật khẩu cho keystore cũng là secret riêng, không thay bằng literal trong YAML.

## 9. Áp dụng nguyên tắc tương tự với ActiveMQ Classic

Classic không đọc `/var/lib/artemis-instance/etc-override` và không dùng format `broker.xml` của Artemis. Đường dẫn cần kiểm soát là `conf/activemq.xml` trong bản phân phối Classic, cùng các file `login.config`, `users.properties`, `groups.properties` hoặc cấu hình xác thực mà hệ thống thực sự sử dụng.

**Một đoạn `activemq.xml` minh họa, đặt trong file cấu hình Classic hoàn chỉnh của đúng bản phát hành:**

```xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-lab"
        persistent="true">
  <persistenceAdapter>
    <kahaDB directory="${activemq.data}/kahadb"/>
  </persistenceAdapter>

  <transportConnectors>
    <transportConnector name="openwire"
      uri="tcp://0.0.0.0:61616?maximumConnections=100&amp;wireFormat.maxFrameSize=10485760"/>
  </transportConnectors>
</broker>
```

Trong cấu hình Classic thực tế, file đầy đủ còn có Spring beans, security plugins, policies, management, web console…; không thay thế toàn bộ file mặc định chỉ bằng fragment trên. Nếu bật `jaasAuthenticationPlugin`, phải cấp `login.config`, file user/role và thiết lập phân quyền phù hợp, đồng thời loại bỏ credentials mặc định. Classic mặc định có thể mở OpenWire không mã hóa; chỉ dùng cổng localhost cho lab, dùng TLS khi qua mạng không tin cậy.

Java client phụ thuộc dòng Classic:

```xml
<!-- Classic 6.4.x: dùng Jakarta Messaging / jakarta.jms -->
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>6.4.0</version>
</dependency>
```

```java
import jakarta.jms.JMSContext;
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://localhost:61616");
try (JMSContext context = factory.createContext("labuser", password)) {
    context.createProducer().send(
        context.createQueue("orders.lab"), "order-001");
}
```

Với Classic **5.x**, artifact `activemq-client` thông thường sử dụng `javax.jms`, còn client `activemq-client-jakarta` là lựa chọn riêng để ứng dụng Jakarta kết nối broker Classic 5.x từ xa. Chọn sai namespace sẽ gây lỗi biên dịch/classpath dù server và cổng đúng.

Khi lập phòng lab Classic có thể tái lập, vẫn khóa `apache/activemq` image bằng digest sau khi xác nhận tag có thật; mount **đúng đường dẫn cấu hình của image cụ thể**; đặt kho KahaDB vào volume riêng; tách secret JAAS ra ngoài Git; và chạy smoke test OpenWire cùng bài kiểm thử restart/redelivery. **Không tái sử dụng Compose/image/đường dẫn của Artemis chỉ bằng cách thay tên image.**

## 10. Quy trình chạy lại và kiểm chứng khả năng tái lập

### 10.1. Từ một checkout mới

1. Checkout đúng commit chứa `compose.yaml`, `.env.lock`, `config/artemis/broker.xml`, `pom.xml` và chương trình Java.
2. Chuẩn bị Docker/Compose và JDK 17 theo phiên bản đội dự án đã chốt; xác nhận nền tảng CPU.
3. Cấp secret mới vào `secrets/artemis_admin_password` bằng kênh tin cậy; bảo đảm file không nằm trong Git.
4. Chạy `docker compose --env-file .env.lock config --quiet` rồi `config --images`; xác nhận image được trỏ tới digest dự kiến.
5. Khởi động broker với **volume trắng** cho test clean-room; đọc log startup, không nhầm trạng thái “container running” với “broker ready”.
6. Chạy `RoundTrip` và bộ test queue/topic, rollback, DLQ, restart; ghi lại kết quả và thời gian.
7. Ghi chính xác image digest, JDK, dependency Maven, hash `broker.xml` và commit Git vào báo cáo test.

### 10.2. Kiểm tra cấu hình đã áp dụng

```bash
# Xác nhận Compose trỏ tới image khóa và mount mong đợi.
docker compose --env-file .env.lock config --images
docker compose --env-file .env.lock config --quiet

# Kiểm tra logs: broker load cấu hình, queue có thể tạo, không có lỗi auth.
docker compose --env-file .env.lock logs --tail=200 broker

# Băm file host để gắn vào kết quả kiểm thử.
sha256sum config/artemis/broker.xml

# So sánh file được broker sử dụng và bản Git (sau startup).
docker compose --env-file .env.lock exec broker \
  cmp /var/lib/artemis-instance/etc/broker.xml \
      /var/lib/artemis-instance/etc-override/broker.xml
```

Lệnh `cmp` phụ thuộc tiện ích có trong image; nếu image tối giản không có `cmp`, dùng `docker compose cp` lấy bản runtime ra một thư mục kiểm thử tạm thời **bên ngoài Git** rồi so sánh trên host. Khi file host vừa sửa mà chưa restart, khác biệt này là tín hiệu cần điều tra.

### 10.3. Phân biệt restart và clean-room

| Thao tác | Cấu hình có thể thay đổi? | Message/journal cũ còn không? | Mục đích |
|---|---|---|---|
| `docker compose restart broker` | Đọc lại theo cơ chế startup/override | **Còn** trong named volume | Kiểm tra restart với state hiện có |
| `docker compose down` rồi `up -d` | Container mới theo image lock và mount | **Còn** vì volume vẫn tồn tại | Kiểm tra tái tạo container |
| Chạy cùng Compose với **project name khác** và volume mới | Dựng từ đầu bằng cấu hình nguồn | **Không** có message cũ | Kiểm tra clean-room |
| `docker compose down -v` | Xóa named volume của project | **Mất** journal, bindings, credential ban đầu | Chỉ thực hiện ở lab dữ liệu bỏ được |

Một cách thử sạch mà vẫn giữ project hiện tại là dừng project đang chiếm các cổng 61616/8161, rồi dùng project name mới:

```bash
docker compose --env-file .env.lock down

# -p tạo namespace project/volume khác dù compose.yaml có name cố định.
docker compose -p artemis-clean-check --env-file .env.lock up -d
docker compose -p artemis-clean-check --env-file .env.lock logs --tail=100 broker

# Chạy RoundTrip, kiểm tra DLQ/transaction, ghi nhận kết quả.

# Chỉ dọn project thử nghiệm sau khi xác nhận không cần giữ dữ liệu.
docker compose -p artemis-clean-check --env-file .env.lock down -v
```

Nếu mật khẩu đã được thay đổi trên host sau khi instance của project gốc ra đời, phép thử clean-room dùng mật khẩu mới sẽ hoạt động với user vừa tạo, trong khi project gốc có thể vẫn dùng credential cũ. Điều đó thể hiện **drift trạng thái**, không phải image digest bị sai.

### 10.4. Mẫu báo cáo tái lập

| Dấu vết | Giá trị mẫu cần điền | Cách xác nhận |
|---|---|---|
| Git commit | `<commit-sha>` | `git rev-parse HEAD` |
| Image broker | `apache/artemis@sha256:<digest>` | `docker compose ... config --images` |
| CPU architecture | `linux/amd64` hoặc `linux/arm64` | `docker info` hoặc inspect container |
| JDK ứng dụng | `17.x` | `java -version` |
| Java JMS dependency | `artemis-jakarta-client:2.57.0` | `mvn -f app/pom.xml dependency:tree` |
| Hash cấu hình | `sha256:<hash-cua-broker.xml>` | `sha256sum` hoặc `Get-FileHash` |
| Secret identity | `lab-admin-secret/v2` (chỉ **tên và phiên bản**, không ghi value) | Secret manager hoặc hồ sơ cấp phát |
| Runtime state | `fresh-volume` / `restored-snapshot-2026...` | Ghi nhận volume/snapshot |
| Smoke test | `PASS/FAIL` với message ID | Kết quả `RoundTrip` |
| Test behavior | ack, rollback, DLQ, restart | Log và assertion tự động |

Khi đồng đội không thể dựng lại lab, so sánh theo thứ tự: **digest image → kiến trúc/JDK → file cấu hình hash → trạng thái volume → secret identity/version → client dependency → kết quả test**. Cách này nhanh hơn chỉnh cấu hình ngẫu nhiên cho đến khi message đi qua.

## 11. Nâng image và cấu hình mà vẫn kiểm soát rủi ro

Mọi thay đổi image nên được xem là một thay đổi có thể làm biến đổi hành vi:

1. Ghi nhận trạng thái ban đầu và backup dữ liệu nếu cần giữ message/transaction; với môi trường lab có thể dùng volume mới để test trước.
2. Chọn **tag phát hành mới**, đọc release notes và migration guide của đúng Classic/Artemis, kiểm tra Java/JMS client tương thích.
3. Pull image mới, lấy digest thực, cập nhật `.env.lock`, thay đổi cấu hình cần thiết trong cùng pull request/commit.
4. Dựng **project test riêng với volume trắng**, chạy smoke test, rollback/redelivery/DLQ, TLS và restart; chạy test với bản snapshot dữ liệu nếu bản nâng cấp phải đọc journal cũ.
5. Chỉ sau khi PASS mới lên kế hoạch áp dụng cho môi trường có dữ liệu thực; tránh nâng broker trực tiếp trên volume duy nhất rồi giả định image cũ chắc chắn đọc được journal đã bị migrate.

Một ví dụ về khác biệt cấu hình thường bị bỏ sót: thay `max-delivery-attempts=3` bằng `5` là thay đổi chính sách xử lý lỗi; cùng một producer/consumer nhưng thông điệp có thể xuất hiện trong DLQ muộn hơn. Thay `ANONYMOUS_LOGIN=false` bằng `true` là thay đổi mô hình bảo mật; không được xem là “chỉ sửa Docker”.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng cao | Cách kiểm tra và sửa |
|---|---|---|
| `docker compose config` báo thiếu `ARTEMIS_IMAGE` | Chưa truyền `--env-file .env.lock` hoặc thiếu khóa | Kiểm tra tệp lock, giá trị digest và tham số Compose |
| Broker vẫn dùng cấu hình cũ | Tệp host chưa được chép vào `etc` runtime, hoặc cấu hình cần restart | Đọc `broker.xml` bên trong instance, so sánh `etc` / `etc-override`, restart |
| Image không pull được bằng digest | Digest chép thiếu/sai hoặc không còn khả dụng trên registry hay nền tảng đang dùng | Lấy lại digest từ đúng registry/tag/kiến trúc; không đổi tạm sang `latest` để “cho chạy” |
| Compose chạy nhưng không mở được 61616 | Broker chưa ready, cổng host bị chiếm, acceptor sai giao thức | Xem logs, `ports`, Core acceptor và URI Java |
| Java `JMSSecurityException` sau khi đổi file password | Instance đã tồn tại vẫn chứa credential cũ | Cập nhật user broker bằng quy trình quản trị; không xóa volume khi còn dữ liệu cần giữ |
| `AddressDoesNotExist` hoặc không nhận được message | Queue chưa được định nghĩa hoặc routing sai `ANYCAST`/`MULTICAST` | Kiểm tra `addresses`, `auto-create-queues`, quyền user |
| Tái tạo container nhưng message cũ còn | Named volume vẫn tồn tại đúng thiết kế | Dùng project/volume mới cho clean-room thay vì sửa tay message |
| Xóa container rồi mất message | Chưa gắn volume đúng hoặc đã chạy `down -v` | Dùng volume và backup, đánh dấu các lệnh xóa dữ liệu |
| Chạy Artemis client tới Classic không kết nối | Giao thức Core khác OpenWire | Dùng đúng client/giao thức hoặc AMQP bridge/provider phù hợp |
| Client lỗi `ClassNotFoundException` `jakarta.jms` | Trộn JMS `javax.jms` và Jakarta `jakarta.jms` | Kiểm tra artifact Maven và dependency tree |

## 13. Tiêu chí chấp nhận bài lab

Một môi trường có thể gọi là **tái lập được về cấu hình và hành vi** khi:

- Cùng commit + image digest + platform xác định được cùng phần mềm và cấu hình đã review; không phụ thuộc tag động `latest`.
- Không có mật khẩu/private key thật trong Git, Dockerfile, file Compose, log hoặc báo cáo; secret được cấp riêng và quyền đọc phù hợp.
- Config queue/topic, routing, redelivery và DLQ được lưu tường minh; không phụ thuộc thao tác bấm tay trong web console.
- Java producer/consumer dùng đúng API/JDK/client version đã khóa; gửi message persistent và kiểm chứng commit/receive thành công.
- Bộ test rollback, DLQ và restart xác nhận hành vi ngoài happy-path.
- Thử trên **volume mới** đạt cùng kết quả dự kiến; nếu khôi phục state thì nguồn snapshot và quy trình phục hồi được ghi nhận riêng.

Đối với ActiveMQ Classic và Artemis, cách làm này biến phòng lab từ một container “có thể chạy trên máy tôi” thành **một môi trường có nguồn cấu hình, đầu vào, phiên bản và bằng chứng kiểm thử đủ rõ để người khác tái hiện**.

## Nguồn tham khảo chính thức

1. [Apache Artemis – Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): image chính thức, `ARTEMIS_USER`/`ARTEMIS_PASSWORD`, đường dẫn instance và `etc-override`.
2. [Apache Artemis – Downloads](https://artemis.apache.org/components/artemis/download/): bản 2.57.0, yêu cầu Java 17+ và hướng dẫn xác minh distribution.
3. [Apache Artemis – Using the Server](https://artemis.apache.org/components/artemis/documentation/latest/using-server.html): bố cục broker instance, `broker.xml` và cấu hình khởi động.
4. [Docker Docs – Manage secrets securely in Compose](https://docs.docker.com/compose/how-tos/use-secrets/): mount bí mật vào `/run/secrets` và phạm vi cấp cho từng service.
5. [Apache Artemis – Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages): retry, rollback, dead-letter address và giới hạn số lần giao message.
6. [Docker Compose – Secrets specification](https://docs.docker.com/reference/compose-file/services/#secrets): hành vi bind mount, quyền trên secret file và giới hạn tùy môi trường.
7. [Apache ActiveMQ Classic – Docker image](https://activemq.apache.org/components/classic/documentation/docker-image) và [download/Java compatibility](https://activemq.apache.org/components/classic/download/).
8. [Apache ActiveMQ Classic – activemq.xml mặc định](https://github.com/apache/activemq/blob/main/assembly/src/release/conf/activemq.xml): cấu trúc broker, transportConnector, KahaDB và gợi ý security.
