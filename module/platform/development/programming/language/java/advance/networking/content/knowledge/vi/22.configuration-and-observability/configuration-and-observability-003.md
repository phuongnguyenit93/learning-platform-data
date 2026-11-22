# Thuộc tính cache DNS khác với system property thông thường

## 1. Mục tiêu học tập

Trong Java Networking, việc đổi ánh xạ hostname → IP thường dẫn tới câu hỏi: **“Vì sao tôi đã đổi DNS nhưng ứng dụng Java vẫn gọi IP cũ?”** Một phần câu trả lời có thể nằm ở **DNS/address cache trong JVM**. Tuy nhiên có một chi tiết rất dễ cấu hình sai: các thuộc tính chuẩn điều khiển TTL của `InetAddress` là **Java security properties**, không phải system properties thông thường mà bạn thiết lập bằng `-Dnetworkaddress.cache.ttl=...` hoặc `System.setProperty(...)`.

Chủ đề thuộc nhóm **Cấu hình và quan sát**. Bài học giúp bạn:
1. Nhận diện hai security properties `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl`.
2. Giải thích **positive cache** (tra cứu thành công) và **negative cache** (tra cứu thất bại) cùng giá trị `-1`/`0`/TTL giây.
3. Phân biệt `Security.getProperty` với `System.getProperty`; `Security.setProperty` với `System.setProperty`.
4. Cấu hình DNS TTL **đúng cách trước khi khởi động ứng dụng** qua `conf/security/java.security` hoặc file bổ sung bằng `-Djava.security.properties=...`.
5. Hiểu vì sao `-Dnetworkaddress.cache.ttl=0` **không phải** cách chuẩn để tắt `InetAddress` DNS cache.
6. Quan sát được cache trong môi trường local độc lập DNS Internet bằng `jdk.net.hosts.file` và ba ví dụ Java 17+ đã chạy.
7. Tránh nhầm cache JVM với resolver của hệ điều hành, DNS authoritative TTL, cache ở proxy, HTTP client connection pooling hay những TCP connections đã mở.
8. Biết cách kiểm tra cấu hình khi ứng dụng nhận IP cũ hoặc giữ kết quả `UnknownHostException` trong một khoảng thời gian.

**Thông điệp chính:** `networkaddress.cache.ttl` là tên của một **security property**. `System.getProperty("networkaddress.cache.ttl")` có thể trả chuỗi đã set bằng `-D` mà **không nói lên** giá trị security policy mà `InetAddress` sử dụng. Muốn xem security property, đọc `java.security.Security.getProperty(...)`.

## 2. DNS resolution trong Java nằm ở những tầng nào?

Khi Java cần kết nối tới `api.example.com:443`, chuỗi logic có thể gồm:

```text
Ứng dụng: Socket/HttpClient/URLConnection
             │
             ▼
Hostname + service port
             │
             ▼
InetAddress / JDK name-resolution mechanism
             │
             ├─ JVM positive/negative address cache
             │     ├─ hit  -> trả kết quả đã giữ
             │     └─ miss -> hỏi name service
             ▼
Hệ điều hành / local hosts / DNS / name service provider
             │
             ▼
IP address(es): IPv4 và/hoặc IPv6
             │
             ▼
TCP connect / TLS / HTTP request
```

Đây là sơ đồ **khái niệm**, không phải lời khẳng định mọi request đều gọi `InetAddress.getByName` một lần. Ví dụ:
- Một HTTP client có thể giữ và tái sử dụng kết nối đã mở, nên **không cần tra DNS lại** cho mỗi HTTP request.
- Name service có thể dùng `hosts`, DNS, NIS, cấu hình hệ điều hành hoặc cơ chế provider khác.
- Kết quả name resolution có thể có nhiều IP. Chính sách chọn IPv4/IPv6 và retry/failover có thể ảnh hưởng IP thực dùng.
- JVM address cache và DNS cache ở hệ điều hành/recursive resolver **không phải cùng một cache**.

Điểm điều khiển trong bài là **cache phía Java name resolution**, không phải sửa authoritative DNS TTL hay xóa cache trên router.

## 3. Hai thuộc tính chuẩn: positive và negative TTL

Java SE 17 công bố hai **Java security properties** cho caching hostname resolution:

| Thuộc tính | Kết quả được cache | Default theo API Java 17 | Giá trị |
| --- | --- | --- | --- |
| `networkaddress.cache.ttl` | Tra cứu thành công: hostname → địa chỉ | **Implementation-specific** khi không có SecurityManager; **forever** nếu SecurityManager được cài đặt | Số giây, `0`, `-1` |
| `networkaddress.cache.negative.ttl` | Tra cứu thất bại: ví dụ `UnknownHostException` | **10 giây** theo tài liệu Java 17 | Số giây, `0`, `-1` |

Ý nghĩa chính:
- `0`: **không lưu kết quả** trong cache Java tương ứng.
- Số nguyên dương `n`: lưu kết quả **n giây**.
- `-1`: **cache forever** theo policy. Tài liệu networking Java 17 còn mô tả các giá trị âm khác cũng mang ý nghĩa không hết hạn; để cấu hình dễ đọc, dùng `-1`.
- Không khai báo property: dùng default của implementation/runtime; **không** suy rằng mọi JVM 17 có positive TTL cố định 30 giây.
- Negative TTL và positive TTL **độc lập**: đặt positive=60 không tự làm negative=60.

### Ví dụ tình huống

```text
t=0:   app lookup good.example -> 192.0.2.10 (success)
t=1:   DNS của nguồn đổi sang 192.0.2.11
t=10:  app lookup lại
       ├─ positive TTL=60: có thể vẫn nhận 192.0.2.10 từ JVM cache
       └─ positive TTL=0: JVM không giữ positive result,
                          nhưng các cache/resolver bên ngoài vẫn có thể giữ IP cũ

t=0:   app lookup typo.invalid -> UnknownHostException
t=2:   name service bắt đầu có record cho typo.invalid
t=3:   app lookup lại
       ├─ negative TTL=10: có thể vẫn thất bại từ JVM negative cache
       └─ negative TTL=0: JVM phải hỏi lại name service,
                          kết quả còn tùy tầng resolver bên dưới
```

Địa chỉ 192.0.2.x là dải tài liệu minh họa; đây không phải output đã chạy. Hai chương trình local ở dưới sẽ **đo sự thay đổi trong một name service kiểm thử**, không dùng DNS công khai.

## 4. Security property không phải System property

Java có **hai namespace cấu hình khác nhau**:

| Đặc điểm | Java system property | Java security property |
| --- | --- | --- |
| Đọc | `System.getProperty(key)` | `Security.getProperty(key)` |
| Ghi trong mã | `System.setProperty(key, value)` | `Security.setProperty(key, value)` |
| Nạp từ file | `-D...`, JVM/runtime config | `$JAVA_HOME/conf/security/java.security`, bổ sung security file |
| Dùng cho | Vô số thiết lập runtime/network/app | Security policy và một số tham số mạng đặc biệt |
| DNS cache TTL chuẩn Java 17? | **Không** | **Có** |

Ví dụ hai dòng này **không tương đương**:

```java
System.setProperty("networkaddress.cache.ttl", "0");
Security.setProperty("networkaddress.cache.ttl", "0");
```

Dòng đầu tạo/đổi **system property** mang đúng tên chuỗi đó. Nhưng tài liệu Java SE 17 khẳng định hai DNS cache TTL keys là **security properties, không được cấu hình qua `-Dnetworkaddress.cache.ttl=...` hay `System.setProperty`**.

Dòng thứ hai thay giá trị trong **security property namespace**, nhưng còn một điều kiện rất quan trọng: **động thái runtime không bảo đảm đổi policy thực thi nếu subsystem đã đọc/cache chính sách TTL từ trước**. Muốn có cấu hình chính xác và lặp lại được, ưu tiên thiết lập **trước khi JVM ứng dụng khởi động**.

## 5. Vì sao `-Dnetworkaddress.cache.ttl=0` dễ đánh lừa?

Một launcher có thể chạy:

```bash
java -Dnetworkaddress.cache.ttl=0 Main
```

JVM hợp lệ có thể nhận tùy chọn này và:

```java
System.getProperty("networkaddress.cache.ttl")
```

trả `"0"`. Người vận hành thấy `"0"` và tưởng rằng cache đã tắt. **Nhưng** một system property tùy ý có thể tồn tại mà không được `InetAddress` dùng làm security policy.

Đúng theo tài liệu Java 17:
- `-Dnetworkaddress.cache.ttl=0` chỉ đặt **system property** tên đó.
- `-Dnetworkaddress.cache.negative.ttl=0` cũng chỉ đặt **system property** cùng tên.
- DNS TTL chuẩn phải được cấu hình trong **security properties**.
- Kiểm tra bằng `Security.getProperty("networkaddress.cache.ttl")`, không chỉ nhìn `System.getProperties()`, JVM flags hoặc file environment variables.

**Một ngoại lệ dễ gây nhầm:** các phiên bản/implementation JDK cũ có các `sun.net.inetaddr.ttl` và `sun.net.inetaddr.negative.ttl`, là **private implementation-specific system properties**. Chúng **không** phải API/security property chuẩn; hành vi và precedence có thể thay đổi theo JDK. Không lấy phương án private đó làm tài liệu triển khai portable, đặc biệt khi viết module Java 17+.

## 6. Đặt đúng trong file java.security của runtime

JDK hiện đại thường đọc các security properties từ:

```text
$JAVA_HOME/conf/security/java.security
```

Trên Windows, đường dẫn tương ứng thường là:

```text
%JAVA_HOME%\conf\security\java.security
```

Các dòng cấu hình có thể là:

```properties
# Caching thành công tối đa 30 giây (giá trị do ứng dụng chọn)
networkaddress.cache.ttl=30

# Caching thất bại tối đa 5 giây (giá trị do ứng dụng chọn)
networkaddress.cache.negative.ttl=5
```

`30` và `5` ở đây là **giá trị cấu hình ví dụ**, không phải khẳng định default của mọi Java 17 runtime. Nếu property bị **comment** bằng `#`, `Security.getProperty(key)` có thể trả `null`; cache implementation vẫn có thể dùng default riêng.

Không nên sửa trực tiếp file của JDK hệ thống dùng chung khi không có quyền và quy trình quản trị:
- Một sửa đổi có thể ảnh hưởng **mọi ứng dụng** chạy cùng JDK installation.
- JDK update có thể thay/ghi đè file.
- Container image/JRE thực chạy production có thể không dùng `JAVA_HOME` mà shell của bạn đang nhìn thấy.
- Cùng máy có thể có nhiều runtime `java`, cần kiểm tra chính xác đường dẫn `java.home` trong process.
- Tốt hơn dùng một **file security overlay riêng cho ứng dụng**, cấu hình trong startup script/deployment manifest và kiểm thử.

## 7. File security overlay bằng `-Djava.security.properties`

Một điểm tưởng như nghịch lý: muốn đặt DNS security property, ta có thể dùng **một system property riêng** làm **đường dẫn tới security configuration file**:

```bash
java -Djava.security.properties=custom.security Main
```

Đây là cách **đúng**: `java.security.properties` là tên của **system property launcher** bảo JVM nạp thêm file chứa security properties; khác hoàn toàn với `-Dnetworkaddress.cache.ttl=30`.

Tạo file `custom.security`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

Java SE 17 security guide phân biệt:
- `-Djava.security.properties=<URL>` với **một dấu bằng sau tên property**: nạp thêm security file bên cạnh master configuration; các keys được chỉ định trong overlay có thể ghi đè giá trị tương ứng.
- `-Djava.security.properties==<URL>` với **hai dấu bằng sau tên property**: **thay toàn bộ master security properties** bằng file được chỉ định. **Không dùng tùy tiện** vì có thể làm mất các security defaults/providers/policies khác.

Trong ví dụ này, ta chỉ cần **single equals**. Không cần (và không nên) thay toàn bộ file security của JDK để chỉnh hai giá trị TTL.

Khi dùng trong Docker/CI, cần mount/copy file security overlay đúng container image, cung cấp đường dẫn tồn tại lúc JVM bắt đầu và kiểm tra file permissions. Một tên file không tồn tại có thể khiến cấu hình không được nạp như mong muốn; luôn kiểm tra giá trị security property thực.

## 8. Security.setProperty: được phép gọi nhưng không phải “reload cache” bảo đảm

Java cung cấp:

```java
import java.security.Security;

Security.setProperty("networkaddress.cache.ttl", "30");
String configured = Security.getProperty("networkaddress.cache.ttl");
```

Đây là **mảnh code**, không phải file có `main`. Mã thay security property trong **JVM process hiện tại**, nhưng:
- Đây là giá trị **global**, không phải per-thread/per-HttpClient/per-tenant.
- Nhiều security settings bị subsystem đọc một lần hoặc cache trong quá trình khởi tạo. API không bảo đảm thay giá trị **sau khi** name resolution đã được thực hiện sẽ làm cache hiện tại được vô hiệu.
- Thay policy **không** xoá các positive/negative cache entries đã tồn tại hay kết nối TCP đang mở theo một hợp đồng chuẩn có thể dựa vào.
- Với code production, ưu tiên thiết lập **ở launch time**, khởi động lại tiến trình khi thay đổi và kiểm chứng trên chính JDK đang chạy.

Phân biệt:
- `Security.getProperty(key) == "30"`: namespace security hiện ghi nhận chuỗi `"30"`.
- **Effective runtime address-cache behavior**: cần kiểm chứng thực tế trong điều kiện kiểm soát (có thể đã được JVM định trước khi chương trình thay property).

**Không** xây một endpoint HTTP cho phép người dùng tuỳ ý gọi `Security.setProperty`; đó là thay đổi global security config và có thể gây hành vi khó dự đoán giữa các requests.

## 9. Demo Java 17+ số 1: chứng minh hai namespace độc lập

Ví dụ đầu tiên cố ý đặt **hai giá trị khác nhau** cho cùng tên key trong hai namespace. Để an toàn, chỉ dùng một JVM thử nghiệm độc lập và gọi `InetAddress` với **numeric loopback**; chương trình **không** thực hiện DNS Internet.

Lưu file **`DnsNamespaceDemo.java`**:

```java
import java.net.InetAddress;
import java.security.Security;

public class DnsNamespaceDemo {
    public static void main(String[] args) throws Exception {
        String positive = "networkaddress.cache.ttl";
        String negative = "networkaddress.cache.negative.ttl";
        System.setProperty(positive, "900");
        System.setProperty(negative, "900");
        Security.setProperty(positive, "2");
        Security.setProperty(negative, "0");

        System.out.println("security-positive=" + Security.getProperty(positive));
        System.out.println("system-positive=" + System.getProperty(positive));
        System.out.println("security-negative=" + Security.getProperty(negative));
        System.out.println("system-negative=" + System.getProperty(negative));
        System.out.println("namespaces-independent=" +
                !Security.getProperty(positive).equals(System.getProperty(positive)));
        System.out.println("loopback=" +
                InetAddress.getByName("127.0.0.1").isLoopbackAddress());
    }
}
```

Lệnh trên JDK 17 trở lên:

```bash
javac DnsNamespaceDemo.java
java DnsNamespaceDemo
```

Output đã được biên dịch/chạy kiểm chứng với `javac --release 17`:

```text
security-positive=2
system-positive=900
security-negative=0
system-negative=900
namespaces-independent=true
loopback=true
```

Ý nghĩa:
1. `Security.getProperty(positive)` và `System.getProperty(positive)` đều nhận cùng tên chuỗi nhưng **trả hai giá trị khác nhau**.
2. Cả positive và negative TTL keys được chứng minh thuộc namespace riêng biệt với system properties.
3. `loopback=true` là phép kiểm tra IP literal `127.0.0.1`, **không phải phép đo thời gian DNS cache**. Một numeric IP literal không yêu cầu truy vấn public DNS.
4. Giá trị `2`/`0` cho security namespace **không chứng minh** subsystem `InetAddress` đã nhận policy động, vì test này chỉ kiểm chứng các APIs quản lý properties.

Để xem tác dụng **thực sự** của TTL lên việc name resolution, ta cần môi trường test có nguồn tên đổi được, như `jdk.net.hosts.file` ở ví dụ tiếp theo.

## 10. `jdk.net.hosts.file`: system property bình thường, dùng đúng vai trò

Java 17 cung cấp system property `jdk.net.hosts.file` cho mục đích chỉ định **file hosts riêng** khi resolve tên, hữu ích cho **tests**. Điểm đối chiếu:

```bash
java -Djdk.net.hosts.file=demo.hosts App
```

Đây là **system property thật**, dùng qua `-D` ở launch. Nội dung file có dạng giống hosts file:

```text
127.0.0.2 sample.invalid
127.0.0.3 another.invalid
```

Nó **không** phải DNS TTL security property. Nó thay **nguồn ánh xạ hostname → địa chỉ** cho Java name resolution ở môi trường test. Các ứng dụng cần name service thật trong production không nên cấu hình một file hosts thử nghiệm ngẫu nhiên.

Lợi ích của file riêng:
- Không cần sửa `/etc/hosts` hoặc file hosts của Windows.
- Không phải thiết lập authoritative DNS server.
- Không dùng public DNS, tránh kết quả ngẫu nhiên hoặc rủi ro spam query.
- Có thể thay ánh xạ local ngay trong chương trình để quan sát positive/negative cache TTL.
- Mỗi lần chạy ở một **JVM process mới**, không dính cache từ thử nghiệm trước.

**Lưu ý:** `jdk.net.hosts.file` là cơ chế name service input, còn `networkaddress.cache.ttl` là TTL của **cache**. Cần cấu hình hai thứ ở **hai namespace khác nhau**.

## 11. Hai file security config để chạy đối chứng

Tạo file **`ttl-zero.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=0
```

Tạo file **`ttl-long.security`**:

```properties
networkaddress.cache.ttl=60
networkaddress.cache.negative.ttl=0
```

Với `ttl-zero.security`, positive cache không giữ kết quả; với `ttl-long.security`, kết quả thành công có thể giữ 60 giây. Negative TTL được để `0` trong hai file để **thử nghiệm positive cache không bị ảnh hưởng bởi negative cache**.

Đây là **config cho JVM thử nghiệm**, không phải khuyến cáo dùng `TTL=0` trong production. Việc tắt cache có thể tăng lưu lượng resolver, latency và nguy cơ sự cố DNS trở thành lỗi hàng loạt.

Cả hai file sẽ được nạp bằng:

```text
-Djava.security.properties=ttl-zero.security
-Djava.security.properties=ttl-long.security
```

Dùng **một file trong mỗi lần JVM launch**, không truyền cả hai file đồng thời cho cùng thử nghiệm.

## 12. Demo Java 17+ số 2: positive TTL với hosts file thay đổi

Chương trình này tạo thay đổi có kiểm soát trong file `demo.hosts` do bạn chỉ định:
1. Ghi `127.0.0.2 sample.invalid`.
2. Resolve `sample.invalid` bằng `InetAddress.getByName`; nhận `127.0.0.2`.
3. Ghi đè file hosts thành `127.0.0.3 sample.invalid`.
4. Resolve cùng hostname một lần nữa.
5. In ra security TTL, hai IP và cờ `changed`.

Nếu positive TTL = `0`, **JDK không giữ positive result** và lần thứ hai có thể thấy file mới. Nếu TTL = `60` và làm ngay trong cùng JVM, lần thứ hai được phục vụ từ positive cache nên tiếp tục trả IP cũ.

Lưu đúng file **`DnsHostsFileCacheDemo.java`**:

```java
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Security;

public class DnsHostsFileCacheDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide hosts file path");
        }
        Path hosts = Path.of(args[0]);
        String hostname = "sample.invalid";
        Files.writeString(hosts,
                "127.0.0.2 " + hostname + "\n", StandardCharsets.UTF_8);
        String first = InetAddress.getByName(hostname).getHostAddress();

        Files.writeString(hosts,
                "127.0.0.3 " + hostname + "\n", StandardCharsets.UTF_8);
        String second = InetAddress.getByName(hostname).getHostAddress();

        System.out.println("security-ttl=" +
                Security.getProperty("networkaddress.cache.ttl"));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("changed=" + !first.equals(second));
    }
}
```

Chương trình:
- Không dùng `new Socket` hoặc gửi HTTP request; chỉ thực hiện name resolution local.
- File `demo.hosts` là **tài nguyên test có thể ghi**, nên hãy chạy trong thư mục kiểm thử riêng, không trỏ vào file cấu hình quan trọng.
- Hostname `sample.invalid` thuộc tên thử nghiệm và chỉ được resolve từ file chỉ định.
- Mọi lần chạy đều **ghi lại file hosts từ đầu**, vì vậy output không phụ thuộc thứ tự chạy trước đó.
- Mọi kết quả đo được phụ thuộc JDK 17 provider và filesystem của môi trường thử nghiệm; không suy rằng các name service providers tùy biến đều phản ứng giống hệt.

## 13. Chạy positive TTL 0 và 60

Đặt các file sau trong **cùng một thư mục thử nghiệm**:
- `DnsHostsFileCacheDemo.java`
- `ttl-zero.security`
- `ttl-long.security`

Biên dịch:

```bash
javac DnsHostsFileCacheDemo.java
```

Chạy với TTL dương bằng 0:

```bash
java -Djava.security.properties=ttl-zero.security -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Output đã kiểm chứng:

```text
security-ttl=0
first=127.0.0.2
second=127.0.0.3
changed=true
```

Chạy lại bằng **JVM process mới** với TTL 60:

```bash
java -Djava.security.properties=ttl-long.security -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Output đã kiểm chứng:

```text
security-ttl=60
first=127.0.0.2
second=127.0.0.2
changed=false
```

Giải thích:
- `-Djava.security.properties=ttl-zero.security` hoặc `ttl-long.security` là **file security config overlay**; JVM nạp chính xác TTL đã khai báo.
- `-Djdk.net.hosts.file=demo.hosts` là **system property** yêu cầu resolver của Java đọc file hosts riêng.
- Trong cùng một process, chương trình sửa mapping giữa hai lần lookup.
- TTL=0 khiến kết quả name resolution từ Java cache không giữ sang lần thứ hai, nên thấy `127.0.0.3`.
- TTL=60 giữ positive cache entry có hostname `sample.invalid`, nên lần lookup kế vẫn thấy `127.0.0.2`.

**Đây là thí nghiệm có file hosts, không phải test thay đổi bản ghi DNS Internet.** Nó cô lập ảnh hưởng của JVM cache và đưa ra output lặp lại được trong môi trường JDK 17 đã chạy.

## 14. Đối chứng quan trọng: -D trực tiếp không thắng security config

Một chương trình có thể cùng lúc có:
- Security TTL dương = `60` từ `ttl-long.security`.
- Ordinary system property `networkaddress.cache.ttl=0` từ `-Dnetworkaddress.cache.ttl=0`.

Lệnh:

```bash
java -Djava.security.properties=ttl-long.security -Dnetworkaddress.cache.ttl=0 -Djdk.net.hosts.file=demo.hosts DnsHostsFileCacheDemo demo.hosts
```

Output đã kiểm chứng trên JDK 17:

```text
security-ttl=60
first=127.0.0.2
second=127.0.0.2
changed=false
```

Điểm đặc biệt: dù command có chuỗi `-Dnetworkaddress.cache.ttl=0`, lookup thứ hai **vẫn dùng giá trị security TTL 60**. Điều này minh họa đúng bản chất **hai namespace không đồng nhất**. Giá trị system property không override giá trị từ security properties.

Không nên xem output này như một lời khẳng định rằng mọi môi trường có file hosts hệ điều hành hay một custom resolver đều cache giống nhau; nó kiểm chứng **cơ chế chuẩn và behavior của JDK trong thiết lập test local**. Mọi nâng cấp runtime nên chạy lại các regression tests liên quan.

## 15. Negative DNS cache: vì sao tên vừa tạo vẫn báo UnknownHostException?

**Negative cache** giữ kết quả tra cứu tên **thất bại** trong một khoảng thời gian. Với default Java 17 theo tài liệu là khoảng 10 giây:

```text
t=0:  lookup new-service.invalid -> UnknownHostException
      JVM có thể giữ kết quả thất bại

t=2:  service đã có bản ghi tên trong name service

t=3:  lookup lại đúng hostname
      nếu negative TTL chưa hết -> có thể vẫn UnknownHostException

t>=10: lookup sau khi TTL hết có cơ hội hỏi name service
       nhưng vẫn có thể thất bại do các tầng resolver khác
```

Đặt `networkaddress.cache.negative.ttl=0` giúp Java không giữ **negative result** trong JVM cache, nhưng không bảo đảm DNS công khai lập tức thấy record mới: authoritative zone, recursive resolvers, OS cache, network split và firewall vẫn ảnh hưởng.

**Không** đặt negative TTL quá dài hoặc forever chỉ vì muốn giảm số DNS queries. Với ứng dụng dùng service discovery/auto-scaling, việc giữ `UnknownHostException` quá lâu có thể khiến dịch vụ mới triển khai vẫn không được phát hiện.

## 16. Demo Java 17+ số 3: kiểm chứng negative TTL

Ví dụ này dùng **cùng cơ chế local hosts file** và làm điều ngược lại với positive demo:
1. File hosts ban đầu trống (chỉ có comment).
2. Lookup `missing.invalid` thất bại.
3. Program thêm `127.0.0.4 missing.invalid` vào hosts file.
4. Lookup lại hostname và in kết quả.

Lưu file **`DnsNegativeCacheDemo.java`**:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Security;

public class DnsNegativeCacheDemo {
    private static String lookup(String hostname) {
        try {
            return InetAddress.getByName(hostname).getHostAddress();
        } catch (UnknownHostException ignored) {
            return "UNKNOWN";
        }
    }

    public static void main(String[] args) throws Exception {
        Path hosts = Path.of(args[0]);
        String name = "missing.invalid";
        Files.writeString(hosts, "# initially empty\n",
                StandardCharsets.UTF_8);
        String first = lookup(name);
        Files.writeString(hosts, "127.0.0.4 " + name + "\n",
                StandardCharsets.UTF_8);
        String second = lookup(name);
        System.out.println("negative-ttl=" +
                Security.getProperty("networkaddress.cache.negative.ttl"));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

Mã `lookup` chuyển riêng `UnknownHostException` thành chuỗi dễ đọc **chỉ phục vụ demo**; trong production thường nên propagate/record type lỗi và áp retry policy, không xem `"UNKNOWN"` là IP thực.

Tạo file **`neg-zero.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=0
```

Tạo file **`neg-sixty.security`**:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=60
```

Positive TTL được giữ `0` để test tập trung vào **negative result**. Không dùng security file global của JDK, chỉ dùng overlay dành cho JVM chạy demo.

## 17. Chạy negative TTL và so sánh output

Biên dịch:

```bash
javac DnsNegativeCacheDemo.java
```

Thử với negative TTL `0`:

```bash
java -Djava.security.properties=neg-zero.security -Djdk.net.hosts.file=demo.hosts DnsNegativeCacheDemo demo.hosts
```

Output đã kiểm chứng:

```text
negative-ttl=0
first=UNKNOWN
second=127.0.0.4
```

Thử với negative TTL `60` trong **JVM process mới**:

```bash
java -Djava.security.properties=neg-sixty.security -Djdk.net.hosts.file=demo.hosts DnsNegativeCacheDemo demo.hosts
```

Output đã kiểm chứng:

```text
negative-ttl=60
first=UNKNOWN
second=UNKNOWN
```

Giải thích:
- Ở lần đầu, file hosts chưa chứa `missing.invalid`, nên lookup trả `UnknownHostException`, được in thành `UNKNOWN`.
- File sau đó được cập nhật ngay trong program.
- Khi negative TTL = `0`, lookup tiếp theo có cơ hội truy vấn lại file hosts và nhận `127.0.0.4`.
- Khi negative TTL = `60`, JVM giữ negative cache entry từ lookup đầu, nên lookup tiếp theo vẫn báo không biết host, dù file mới đã chứa mapping.

**Kết luận:** Cache không chỉ giữ IP cũ; nó còn có thể giữ cả **kết luận “hostname không tồn tại/không resolve được”**. Vì vậy deployment của service mới có thể gặp lỗi một thời gian dù DNS/hosts source đã được cập nhật.

## 18. Những điều các ví dụ đã chứng minh — và chưa chứng minh

| Thí nghiệm | Điều đã kiểm chứng | Điều không được kết luận |
| --- | --- | --- |
| `DnsNamespaceDemo` | `Security` và `System` giữ hai giá trị độc lập cho cùng key | `Security.setProperty` động luôn thay hiệu lực InetAddress cache |
| Positive TTL 0 vs 60 | JDK 17 dùng security TTL cho lookup từ file hosts riêng trong process mới | Public DNS/OS resolver luôn cho kết quả tức thì khi TTL=0 |
| Security TTL 60 + system -D TTL 0 | `-Dnetworkaddress.cache.ttl=0` không override security TTL | Không có implementation-specific property nào khác tồn tại |
| Negative TTL 0 vs 60 | JVM có thể cache thất bại name resolution và dùng lại | Tất cả lỗi HTTP đều do negative DNS cache |
| `jdk.net.hosts.file` | Có thể kiểm soát nguồn mapping trong Java 17 test mà không sửa hệ thống | Đây là giải pháp cấu hình DNS chung cho production |

Điều này giúp tránh một test thiếu kiểm soát như “lookup cùng hostname 1000 lần và so latency” rồi kết luận TTL chắc chắn bằng một giá trị. Latency còn phụ thuộc OS cache, scheduler, network, JVM JIT, GC và resolver. Các demo dùng **kết quả IP/UnknownHostException và nguồn dữ liệu có thể đổi**, nên có sức giải thích tốt hơn các con số millisecond.

## 19. Vì sao thay security property giữa chừng chưa chắc có tác dụng?

Một cách làm dễ sai là:

```java
InetAddress.getByName("my-service.internal");
// Ứng dụng đã thực hiện name resolution.
Security.setProperty("networkaddress.cache.ttl", "0");
InetAddress.getByName("my-service.internal");
// Không có contract bảo đảm lookup thứ hai bỏ qua cache đã tồn tại.
```

Đây là **mảnh code minh họa**, không có import/class, hostname chỉ là ví dụ.

Lý do:
1. Nhiều cấu hình security/runtime có thể được **đọc và lưu tại thời điểm subsystem khởi tạo**.
2. Kết quả tra cứu đã nằm trong cache có thể có **expiry đã được tính trước**; đổi property string không bắt buộc invalidate entries.
3. `Security.setProperty` cập nhật **registry**; không có API public `InetAddress.clearDnsCache()` chuẩn trong Java 17.
4. HTTP clients/sockets có thể đã mở **kết nối TCP** tới IP cũ, độc lập việc name resolution mới sẽ trả gì.

Cách chắc chắn hơn: thiết lập TTL trong file security trước startup, **khởi động JVM process mới** và test/observe behavior. Khi rollout config trong Kubernetes hoặc server deployment, restart/recreate pods/instances theo quản trị, không kỳ vọng sửa file trên disk sẽ tự cập nhật JVM đang chạy.

## 20. Defaults và SecurityManager trong Java 17

Javadoc của `InetAddress` Java 17 ghi:
- Khi **SecurityManager được cài đặt**, positive hostname resolution được cache **forever** theo default để giảm rủi ro DNS spoofing.
- Khi **không có SecurityManager**, default positive TTL **phụ thuộc implementation**; JDK không cam kết cùng một số giây cho mọi runtime/vendor.
- Negative lookup cache có default được mô tả là **10 giây**.

Do đó, bài kiểm tra kiểu:

```java
String value = Security.getProperty("networkaddress.cache.ttl");
System.out.println(value);
```

có thể in `null` nếu property không được khai báo trong file security, dù runtime vẫn có **default behavior**. `null` chỉ có nghĩa key không có giá trị trực tiếp trong security registry ở thời điểm đọc, không có nghĩa “cache tắt”.

Java 17 đã **deprecate SecurityManager for removal**; đây là bối cảnh lịch sử của API default, không phải lời khuyến cáo cài SecurityManager để đổi DNS cache. Cấu hình giá trị TTL rõ trong security file sẽ làm ý định vận hành dễ kiểm chứng hơn nhiều so với dựa vào defaults.

## 21. Ba cache khác nhau: JVM, OS và recursive DNS

Đừng xem positive TTL = 0 như phép màu làm server luôn đến IP DNS mới nhất:

```text
Java process                    OS resolver                   DNS infrastructure
  InetAddress JVM cache    ->  OS/hosts/name service    ->   recursive resolver
       TTL riêng                    cache riêng                 cache riêng
                                                                    │
                                                           authoritative zone
                                                                    │
                                                               DNS record TTL
```

Ví dụ:
- JVM TTL=0 làm Java hỏi name service nhiều hơn.
- OS hoặc recursive resolver vẫn có thể lưu bản ghi theo policy riêng.
- DNS record TTL của authoritative server không phải là giá trị bạn đã đặt trong `java.security`.
- Proxy hoặc service mesh có thể resolve hostname thay client; Java nhìn thấy proxy connection chứ không trực tiếp resolve origin.
- HTTP keep-alive/HTTP/2 có thể tái sử dụng connection dù JVM TTL hết hạn.

Do đó, muốn xác minh failover sau DNS change:
1. Kiểm tra server/process đã nhận security TTL đúng.
2. Kiểm tra hostname resolution trong đúng JVM/instance.
3. Kiểm tra OS/name service và DNS records.
4. Kiểm tra connection reuse và client pool behavior.
5. Kiểm tra network routing/firewall/proxy.

**Không** suy rằng một kết nối tới IP cũ là bằng chứng TTL property sai. Nếu connection đã tạo từ trước, cần quan sát khi nào client **mở kết nối mới**, không chỉ khi nào nó gửi một HTTP request mới.

## 22. JVM DNS cache và HTTP connection pool khác nhau

Giả sử `HttpClient` đang giữ một connection HTTP/2 tới `api.example.com` tại IP A. Khi DNS đổi sang IP B:
- Cache JVM có thể đã hết TTL.
- Một request mới có thể **vẫn sử dụng connection đang mở tới A**.
- Một kết nối mới thực sự có thể trigger resolution lại theo JVM/provider behavior.
- Việc DNS lookup trả B không bắt buộc ngay lập tức đóng connection A.
- Connection pooling, keep-alive, TLS sessions, proxy routing và retry policy có vòng đời riêng.

Tương tự với `Socket`: đã connect tới một `InetSocketAddress` được resolve thành IP A thì đổi security property không thay đổi socket hiện tại.

Vì vậy khi debug “IP không cập nhật” hãy phân biệt **lookup result**, **địa chỉ socket thực kết nối**, **DNS cache entry** và **tái sử dụng HTTP connection**. Chúng không cùng một metric.

## 23. Những system properties network thông thường để đối chiếu

Java 17 networking docs còn nêu những properties thực sự là **system properties**, có thể đặt bằng `-D`:

| Property | Loại | Ý nghĩa |
| --- | --- | --- |
| `java.net.preferIPv4Stack` | System property | Ưu tiên dùng IPv4 stack, được kiểm tra lúc khởi động |
| `java.net.preferIPv6Addresses` | System property | Thứ tự ưu tiên IPv4/IPv6 khi cả hai có sẵn, thường đọc lúc startup |
| `jdk.net.hosts.file` | System property | Chỉ định file hosts riêng cho Java name resolution khi test |
| `http.proxyHost` / `http.proxyPort` | System properties | Proxy HTTP cho handler tương ứng |
| `java.security.properties` | System property **trỏ tới file security** | Điều khiển cách nạp security configuration |
| `networkaddress.cache.ttl` | **Security property** | Positive DNS TTL |
| `networkaddress.cache.negative.ttl` | **Security property** | Negative DNS TTL |

Không nhầm **sự có mặt của `-D`** với “cấu hình này chắc chắn có hiệu lực runtime”. Một số system properties được **đọc đúng một lần ở startup**, nên `System.setProperty` sau khi network stack đã khởi tạo cũng có thể không làm đổi behavior. Java Networking Properties tài liệu phân biệt rõ các nhóm này.

Ví dụ:

```bash
java -Djava.net.preferIPv4Stack=true App
```

Đây là system property chuẩn theo Java 17, khác bản chất với:

```bash
java -Dnetworkaddress.cache.ttl=0 App
```

Dòng thứ hai **không cấu hình TTL chuẩn**.

## 24. Vì sao không nên dùng sun.net.inetaddr.ttl làm lời giải portable?

Một số bài blog hướng dẫn:

```bash
java -Dsun.net.inetaddr.ttl=30 App
java -Dsun.net.inetaddr.negative.ttl=0 App
```

Đây là **implementation-specific/private properties** đã từng tồn tại trong các Oracle/Sun JDK và có thể vẫn được một số builds hỗ trợ. Tuy nhiên:
- Không được chuẩn hóa như `networkaddress.cache.ttl` trong Java SE 17 API.
- Có thể có precedence với security properties tùy implementation.
- Có thể thay đổi hoặc bị bỏ ở một JDK tương lai.
- Một JVM khác vendor/ứng dụng đóng gói native image có thể xử lý khác.
- Khi chuyển sang Java 17+ hoặc nâng cấp runtime, nên dùng cách chuẩn: `java.security` hoặc `-Djava.security.properties=...`.

Đừng “sửa” câu lệnh bằng cách thay `networkaddress.cache.ttl` thành `sun.net.inetaddr.ttl` mà không có kế hoạch kiểm thử và ghi nhận đây là phụ thuộc vendor. Nên dùng security file và regression test local ở bài này.

## 25. Cấu hình phù hợp với loại dịch vụ

TTL không có một giá trị “tốt nhất” cho tất cả:

| Workload | Điều cần cân nhắc |
| --- | --- |
| Dịch vụ backend gọi host ổn định | TTL dương hữu hạn giúp tránh quá nhiều lookups và vẫn có khả năng cập nhật |
| Service discovery thay IP thường xuyên | Positive TTL quá dài có thể kéo dài thời gian bám IP cũ |
| Dịch vụ quan trọng cần failover | Cần kết hợp DNS TTL, connection pool, retry, idempotency và health checks |
| Cluster có nhiều short-lived jobs | Mỗi JVM mới có cache mới, phải quan sát startup resolution |
| Môi trường DNS chập chờn | TTL quá ngắn có thể làm tăng tỷ lệ lỗi/latency; negative TTL dài có thể giữ lỗi |
| DNS provider trả nhiều địa chỉ | Resolver order, client retry và address selection ảnh hưởng kết quả |
| Ứng dụng có nhiều tenants | Security TTL là **global trong JVM**, không phải per tenant/per HttpClient |

Một ví dụ chính sách có thể là positive TTL `30` giây và negative TTL `5` giây, **nếu đã được đo và chấp thuận**. Không lấy các con số đó làm chuẩn bắt buộc hoặc mặc định; thử trên staging với DNS/connection behavior thực.

Điều cần đo: DNS lookup success/failure rate, p95 latency, request connect errors, retry/reconnect count, connection pool reuse, địa chỉ socket thực, thời gian khôi phục sau DNS failover.

## 26. Rủi ro bảo mật: stale IP và DNS rebinding

TTL dài:
- Có thể giữ một mapping **đã đổi** và kéo dài việc gửi traffic tới đích cũ.
- Nếu IP cũ được tái cấp cho service khác, ảnh hưởng phụ thuộc thiết kế mạng/TLS/certificate/service identity.
- Không tự đảm bảo an toàn DNS spoofing; đây chỉ là một thành phần của hệ thống.

TTL quá ngắn:
- Gia tăng tần suất resolver calls, load và surface cho DNS failures.
- Đưa application liên tục vào luồng resolution động, cần kiểm soát nguồn DNS đáng tin.
- **Không chống SSRF** chỉ bằng cách bỏ cache.

Với URL từ nguồn không tin, một kiểm tra `InetAddress.getAllByName` rồi sau đó HTTP client tự resolve lại có thể dẫn tới **DNS rebinding/time-of-check-time-of-use**. Thêm cache TTL không đủ bảo vệ. Cần allowlist host/scheme/port, bảo vệ địa chỉ kết nối thực, egress firewall, ngăn link-local/metadata endpoints khi không được phép, TLS hostname validation và policy redirects.

**Không** gắn DNS cache TTL với việc cho phép chuyển token sang IP/host mới. Authentication và authorization vẫn phải kiểm tra service identity/audience.

## 27. Quan sát và troubleshooting khi vẫn dùng IP cũ

Quy trình gợi ý, từ ít xâm lấn đến sâu:

1. **Xác nhận JVM thực đang chạy:** `java -version`, `java.home`, container image/runtime path, app process và JDK vendor.
2. **Đọc đúng namespace:** `Security.getProperty("networkaddress.cache.ttl")` và `Security.getProperty("networkaddress.cache.negative.ttl")`.
3. **Kiểm tra system namespace riêng:** `System.getProperty(...)` chỉ để phát hiện các cấu hình `-D` sai chỗ.
4. **Đọc security file đang dùng:** master `conf/security/java.security` và overlay `java.security.properties`, quyền truy cập file và startup args.
5. **Xác nhận startup order:** nếu vừa sửa file mà JVM chưa restart, không kỳ vọng setting đổi ngay.
6. **Quan sát name resolution:** kết quả từ `InetAddress.getAllByName` trên JVM thật, theo từng hostname, tránh spam DNS.
7. **Quan sát remote socket address** khi connection thực sự được mở, phân biệt với DNS lookup result.
8. **Kiểm tra OS/recursive DNS cache**, authoritative records và thay đổi của proxy/service mesh.
9. **Kiểm tra negative cache:** hostname có từng thất bại trước khi record xuất hiện không?
10. **Chạy regression test trong môi trường cô lập** với `jdk.net.hosts.file` + security config và process mới để chứng minh JVM policy.
11. **Không xóa cache nội bộ bằng reflection/hacks** vào `java.net.InetAddress`; không có public Java 17 `clearDnsCache` chuẩn.
12. **Theo dõi side effects** khi retry network operations, đặc biệt POST, để tránh lỗi nghiệp vụ.

### Đoạn code kiểm tra namespace (mảnh code)

```java
String key = "networkaddress.cache.ttl";
String fromSecurity = Security.getProperty(key);
String fromSystem = System.getProperty(key);
System.out.println("Security property = " + fromSecurity);
System.out.println("System property   = " + fromSystem);
```

Đây là **mảnh code**, cần `import java.security.Security`; output tùy runtime hiện tại và **không** được gán một default cứng. Nếu `fromSecurity == null`, ứng dụng vẫn có thể đang dùng default TTL của JDK.

### Debug security property initialization

Java 17 security guide mô tả các công cụ:
- `-Djava.security.debug=properties` để log việc nạp các security properties, giá trị ban đầu và includes. Dùng có kiểm soát vì debug logs có thể chứa dữ liệu cấu hình nhạy cảm.
- `-XshowSettings:security` để in overview các security settings khi JDK hỗ trợ tùy chọn này. Kiểm tra version runtime trước khi dùng.
- Java Flight Recorder event `jdk.InitialSecurityProperty` có thể giúp xem cấu hình lúc khởi tạo trên JDK hỗ trợ.

**Không** log nguyên credentials/keystores/secrets trong một bug report. DNS TTL không nên đòi bật debug toàn bộ security subsystem trên production dài hạn.

## 28. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `-Dnetworkaddress.cache.ttl=0` rồi cho rằng JVM đã tắt cache | Đây là **system** property, không phải security property TTL | Đặt trong security file và kiểm tra `Security.getProperty` |
| Chỉ đọc `System.getProperty` | Có thể thấy giá trị tự tạo nhưng không phải TTL thực | Đọc cả hai namespace và phân biệt |
| Cho rằng positive TTL mặc định luôn 30s | Java 17 nói implementation-dependent khi không có SecurityManager | Khai báo TTL rõ nếu cần |
| Cho rằng negative TTL luôn bằng positive TTL | Hai policy riêng | Đặt `networkaddress.cache.negative.ttl` riêng |
| Cho rằng `-1` nghĩa cache bị tắt | `-1` là cache forever | Dùng `0` nếu muốn không cache |
| Cho rằng `0` ép OS DNS cache hết hạn | Chỉ tác động JVM cache | Kiểm tra resolver layers khác |
| Sửa `java.security` nhưng không restart JVM | Settings có thể đã được nạp/cached | Restart/recreate process với config đã kiểm chứng |
| Dùng `Security.setProperty` rồi kỳ vọng flush entries | Không có public invalidate guarantee | Dùng startup configuration và test |
| Sử dụng `-Djava.security.properties==...` chỉ để đổi 1 key | Thay toàn bộ master security config | Dùng single equals overlay |
| Dùng `sun.net.inetaddr.ttl` làm chuẩn Java SE | Private/vendor-specific | Ưu tiên `networkaddress.cache.ttl` trong security file |
| Dùng `jdk.net.hosts.file` cho production DNS service discovery | Đây là file mapping dùng được trong tests | Dùng DNS/name service đúng kiến trúc |
| Chạy demo sửa file hosts hệ thống | Có thể ảnh hưởng nhiều process | Dùng file test riêng của JVM |
| Benchmark bằng thời gian lookup một lần | Phụ thuộc OS cache/network/JIT | Test mapping/negative result có điều khiển |
| Nghĩ TTL hết sẽ cắt socket HTTP cũ | Connection lifetime khác DNS cache | Kiểm tra connection pooling/lifecycle |
| Dùng TTL=0 để “chống SSRF” | DNS rebinding và egress vẫn nguy hiểm | Validate destination + network-level policy |
| Log full host/URL/token mọi lần resolve | Dễ rò dữ liệu riêng | Log metadata cần thiết, redact secrets |
| Dùng TTL forever cho service động | Có thể giữ IP/failure rất lâu | Chọn TTL hữu hạn, failover strategy |
| Dùng property trên JVM khác process cần sửa | Không ảnh hưởng JVM khác | Cấu hình từng runtime/container/pod |
| Quên negative cache khi deploy hostname mới | UnknownHostException có thể bị giữ | Kiểm tra negative TTL và process state |

## 29. Ma trận kiểm thử khuyến nghị

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `System.setProperty` cùng key rồi `Security.getProperty` | Hai namespace độc lập |
| Positive TTL=0, hosts file đổi IP | Resolve lại thấy IP mới trong test local JDK |
| Positive TTL=60, hosts file đổi IP ngay | Resolve vẫn thấy cached IP cũ |
| Positive TTL=60 + `-Dnetworkaddress.cache.ttl=0` | Direct -D **không** override security TTL |
| Negative TTL=0, hostname ban đầu thiếu rồi thêm | Lần sau có thể resolve được |
| Negative TTL=60, hostname ban đầu thiếu rồi thêm ngay | Lần sau vẫn có thể UnknownHostException |
| Security file overlay một dấu bằng | Chỉ định và nạp các keys cần test |
| Security.getProperty key null | Không suy “cache off”, kiểm tra default implementation |
| Cấu hình thay sau startup | Không hứa cache invalidate nếu chưa kiểm chứng |
| Java HTTP connection vẫn dùng IP cũ sau DNS đổi | Kiểm tra keep-alive/pool thay vì kết luận TTL sai |
| Có proxy DNS / service mesh | Xác định ai resolve hostname cuối cùng |
| DNS rebinding giữa validate và connect | Egress/connection policy vẫn ngăn địa chỉ không được phép |
| Public DNS outage | Số DNS queries/latency/retries bị giới hạn, có monitoring |
| Upgrade JDK | Chạy lại test positive/negative TTL và read config |

Các test local từ mục 9–17 **không** đòi Internet; rất thích hợp để giữ thành smoke/regression tests khi nâng cấp JDK/container image. Với production, thêm canary tests kiểm tra service failover thực, song không tự sửa DNS global để thử nghiệm tùy tiện.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** `networkaddress.cache.ttl` là system property hay security property?  
**Đáp án:** **Security property** trong Java SE 17.

**Câu 2.** Cách đọc giá trị đã cấu hình trong security registry?  
**Đáp án:** `Security.getProperty("networkaddress.cache.ttl")`, không phải chỉ `System.getProperty`.

**Câu 3.** `-Dnetworkaddress.cache.ttl=0` có tắt positive JVM DNS cache theo API chuẩn không?  
**Đáp án:** Không; nó tạo ordinary system property, không đặt security TTL.

**Câu 4.** `-Djava.security.properties=ttl-zero.security` là gì?  
**Đáp án:** Một **system property chỉ đường dẫn file** để JVM nạp security properties từ file; không phải direct DNS TTL system setting.

**Câu 5.** Positive TTL `-1` nghĩa là gì?  
**Đáp án:** Cache forever theo policy, không phải disable.

**Câu 6.** Negative TTL Java 17 được mô tả mặc định bao nhiêu?  
**Đáp án:** Khoảng **10 giây**.

**Câu 7.** Positive TTL mặc định luôn là 30 giây?  
**Đáp án:** Không. Nếu không có SecurityManager, Java 17 mô tả default phụ thuộc implementation.

**Câu 8.** `Security.setProperty` sau một DNS lookup có chắc làm cache cũ biến mất?  
**Đáp án:** Không có guarantee. Ưu tiên cấu hình lúc startup và dùng process mới để test.

**Câu 9.** Vì sao TTL=0 nhưng HttpClient vẫn dùng IP cũ?  
**Đáp án:** Có thể tái sử dụng TCP connection đang mở, hoặc OS/recursive resolver vẫn giữ kết quả.

**Câu 10.** `jdk.net.hosts.file` là loại property nào?  
**Đáp án:** System property dùng chỉ định file hosts riêng cho Java name resolution trong test.

**Câu 11.** Positive cache và negative cache khác nhau?  
**Đáp án:** Positive giữ IP tra được; negative giữ kết quả thất bại như `UnknownHostException`.

**Câu 12.** Có nên dùng file security double equals để đặt chỉ hai TTL keys?  
**Đáp án:** Không. Double equals thay toàn bộ master security configuration; single equals overlay là cách thích hợp hơn.

**Câu 13.** Một security property có giá trị null nghĩa là no cache?  
**Đáp án:** Không. JVM có thể đang áp implementation default nếu property không khai báo.

**Câu 14.** DNS TTL=0 có đảm bảo chống DNS rebinding/SSRF?  
**Đáp án:** Không. Cần ràng buộc destination, scheme, host, network egress và bảo vệ time-of-check/time-of-use.

**Câu 15.** Tại sao không cần DNS Internet trong ba chương trình test?  
**Đáp án:** `jdk.net.hosts.file` cho phép cung cấp file name mapping riêng; chương trình điều khiển mapping trước và sau lookup, đo tác động của JVM TTL.

## 31. Tóm tắt cấu hình đúng và vận hành

**Cần điều khiển JVM DNS cache:** đặt `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` là **Java security properties** trước khi JVM start, qua `$JAVA_HOME/conf/security/java.security` hoặc **overlay file** được nạp bằng `-Djava.security.properties=path/to/file`. Kiểm tra bằng `Security.getProperty(...)`, không dựa vào ordinary `System.getProperty(...)`.

**Cần kiểm chứng behavior:** chạy chương trình trong JVM process mới, dùng local `jdk.net.hosts.file` để thay đổi mapping, so sánh TTL=0/60 và trường hợp negative lookup. Đừng thay DNS public hoặc file hosts hệ thống để phục vụ unit test.

**Cần giải quyết production “IP cũ”:** phân tích JVM address cache, OS/recursive DNS cache, connection pool, proxy/service mesh và TCP connection lifetime riêng biệt. Đặt TTL hợp lý theo throughput và failover goals, theo dõi lỗi/latency, và restart/redeploy khi sửa startup security settings.

**Một câu ghi nhớ:** **`-Dnetworkaddress.cache.ttl=...` không phải cách cấu hình DNS TTL chuẩn của Java 17; `java.security.Security` và file `java.security` mới là đúng namespace.**

## 32. Tài liệu tham khảo

- Oracle Java SE 17 — `Networking Properties` (Address Cache: security properties, không dùng direct -D): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html
- Oracle Java SE 17 — `InetAddress` (caching successful/unsuccessful lookups và defaults): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Oracle Java SE 17 — `Java Networking` (security address cache properties, hosts file configuration): https://docs.oracle.com/en/java/javase/17/core/java-networking.html
- Oracle Java SE 17 — `The Security Properties File` (java.security.properties overlay, single/double equals, dynamic caveats): https://docs.oracle.com/en/java/javase/17/security/security-properties-file.html
- Oracle Java SE 17 — `java.security.Security` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html
- Oracle Java SE 17 — `java.lang.System` getProperty/setProperty: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- Oracle Java SE 17 — `HttpClient` (HTTP connection/reuse and networking context): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 21 — `Networking Properties` (mục stale TTL xuất hiện trong tài liệu các JDK mới; **không áp đặt `networkaddress.cache.stale.ttl` như API Java 17**): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html
- RFC 6761 — Special-Use Domain Names, trong đó có `.invalid` cho ví dụ: https://www.rfc-editor.org/rfc/rfc6761
